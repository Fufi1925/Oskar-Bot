"""One DM envelope for every sender, with a restart-safe language picker."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import functools
import logging
import re
import time
import weakref

import discord
from discord.utils import MISSING
from utils import dm_preferences as preferences
from utils.dm_i18n import translate
from utils.emoji import MESSAGE, INFO, TICK, CROSS, WARNING, LOCK, UNLOCK, TICKET, ZSAFE, PREMIUM, ZWRENCH, STAR
from utils.panels import Panel, container, from_embed, from_embeds, from_view
from utils.component_emojis import normalize_controls

log = logging.getLogger(__name__)
_LOCKS = weakref.WeakKeyDictionary()
_VIEW_LOCKS = weakref.WeakKeyDictionary()
_INSTALLED = False
_BOT = None
_FOLLOWUPS = {}


def _lock(user_id):
    locks = _LOCKS.setdefault(asyncio.get_running_loop(), weakref.WeakValueDictionary())
    return locks.setdefault(user_id, asyncio.Lock())


@asynccontextmanager
async def _view_lock(view):
    if view is None or view is MISSING:
        yield
        return
    locks = _VIEW_LOCKS.setdefault(asyncio.get_running_loop(), weakref.WeakKeyDictionary())
    async with locks.setdefault(view, asyncio.Lock()):
        yield


@asynccontextmanager
async def _delivery_lock(user_id, editing=False):
    if editing:
        yield
    else:
        async with _lock(user_id):
            yield


def is_language_command(content):
    word = re.sub(r'[^a-zäöüß]', '', str(content or '').strip().casefold())
    if word in {'language', 'languages', 'lang', 'sprache', 'spracheändern', 'changelanguage'}:
        return True
    # Damerau-Levenshtein also accepts transposed neighbouring letters.
    if not 6 <= len(word) <= 10:
        return False
    target = 'language'
    rows = [[0] * (len(target) + 1) for _ in range(len(word) + 1)]
    for i in range(len(word) + 1): rows[i][0] = i
    for j in range(len(target) + 1): rows[0][j] = j
    for i in range(1, len(word) + 1):
        for j in range(1, len(target) + 1):
            rows[i][j] = min(rows[i-1][j]+1, rows[i][j-1]+1, rows[i-1][j-1]+(word[i-1] != target[j-1]))
            if i > 1 and j > 1 and word[i-1] == target[j-2] and word[i-2] == target[j-1]:
                rows[i][j] = min(rows[i][j], rows[i-2][j-2]+1)
    return rows[-1][-1] <= 2


class LanguageView(Panel):
    def __init__(self, user_id=None, language='en', *, selected=False):
        self.user_id = user_id
        title = 'DM language' if language == 'en' else 'Sprache für Direktnachrichten'
        body = ('Which language should I use for your direct messages?\n**English** is the default. Choose a language below.\n\nYou can change it anytime by sending me **Language**.\nServer-written messages keep their original wording.' if language == 'en' else
                'In welcher Sprache möchtest du meine Direktnachrichten erhalten?\nStandardmäßig verwende ich **Englisch**. Wähle unten deine Sprache aus.\n\nDu kannst sie jederzeit ändern, indem du mir **Language** schreibst.\nEigene Servernachrichten behalten ihren ursprünglichen Text.')
        if selected:
            body = ('Your DM language is now **English**.\n\n' + body) if language == 'en' else ('Deine DM-Sprache ist jetzt **Deutsch**.\n\n' + body)
        buttons = []
        for code, label in [('en', 'English'), ('de', 'Deutsch')]:
            button = discord.ui.Button(label=label, emoji=MESSAGE, style=discord.ButtonStyle.primary if code == language else discord.ButtonStyle.secondary, custom_id='university_dm_language:' + code)
            async def choose(interaction, code=code):
                if interaction.guild_id is not None or (self.user_id is not None and interaction.user.id != self.user_id):
                    await interaction.response.send_message(view=Panel(f'{CROSS} Private setting', 'This language selector belongs to another user.'), ephemeral=True)
                    return
                preferences.select(interaction.user.id, code)
                await interaction.response.edit_message(view=LanguageView(interaction.user.id, code, selected=True))
            choose._university_dm_language = True
            button.callback = choose
            buttons.append(button)
        super().__init__(f'{INFO} {title}', body, buttons=buttons, timeout=None)
        self._university_dm_language_picker = True


async def handle_message(message):
    if message.guild is not None or message.author.bot or not is_language_command(message.content):
        return False
    async with _lock(message.author.id):
        await _ORIGINAL_SEND(message.channel, view=LanguageView(message.author.id, preferences.language(message.author.id)))
        preferences.mark_offered(message.author.id)
    return True


def _source(item, attr):
    value = getattr(item, attr)
    if value != getattr(item, '_dm_rendered_' + attr, None):
        setattr(item, '_dm_source_' + attr, value)
    return getattr(item, '_dm_source_' + attr, value)


def _render(item, attr, language):
    source = _source(item, attr)
    value = translate(source, language)
    if isinstance(item, discord.ui.Button) and attr == 'label':
        value = value[:80]
    if isinstance(item, discord.ui.Select) and attr == 'placeholder':
        value = value[:150]
    setattr(item, attr, value)
    setattr(item, '_dm_rendered_' + attr, value)


def _custom(item):
    while item is not None:
        if getattr(item, '_university_dm_custom_copy', False):return True
        item = getattr(item, 'parent', None)
    return False


def localize_modal(modal, language):
    _render(modal, 'title', language)
    modal.title = modal.title[:45]
    protected = set()
    for item in modal.walk_children():
        if _custom(item):
            protected.add(id(item))
            protected.update(id(child) for child in getattr(item, 'walk_children', lambda: [])())
    for item in modal.walk_children():
        if id(item) in protected:continue
        for attr, limit in [('text', 45), ('label', 45), ('placeholder', 100), ('description', 100)]:
            if hasattr(item, attr) and getattr(item, attr):
                _render(item, attr, language)
                setattr(item, attr, getattr(item, attr)[:limit])
    return modal


def localize(view, language):
    if getattr(view, '_university_dm_language_picker', False):
        return view
    custom = getattr(view, '_university_dm_custom_copy', False)
    icon_map = {'✅': TICK, '❌': CROSS, '⚠️': WARNING, '🔒': LOCK, '🔓': UNLOCK, '🎫': TICKET, '🔐': ZSAFE, '💎': PREMIUM, '📢': MESSAGE, '🔴': WARNING, '📝': MESSAGE, '⏰': INFO, '🎁': STAR, '📑': MESSAGE}
    for item in view.walk_children():
        if isinstance(item, discord.ui.TextDisplay) and not custom and not _custom(item):
            _render(item, 'content', language)
            # Replace standard status icons only in bot-authored copy.
            for old, new in icon_map.items():
                item.content = re.sub(r'^(\s*(?:#{1,3} )?)' + re.escape(old), lambda m: m[1] + new, item.content)
            item._dm_rendered_content = item.content
        if isinstance(item, discord.ui.Button) and not custom and not _custom(item):
            if item.label:
                _render(item, 'label', language)
            if item.emoji is None and not item.url:
                item.emoji = MESSAGE
        if isinstance(item, discord.ui.Select) and not custom and not _custom(item):
            if item.placeholder:
                _render(item, 'placeholder', language)
            for option in item.options:
                if not getattr(option, '_university_dm_custom_copy', False):
                    # SelectOption uses slots; cannot attach source attributes.
                    option.label = translate(option.label, language)
                    if option.description: option.description = translate(option.description, language)
    if not custom:
        # Every card gets an app-owned marker; existing markers stay intact.
        heading = next((x for x in view.walk_children() if isinstance(x, discord.ui.TextDisplay)), None)
        if heading is not None and not getattr(heading, '_university_dm_custom_copy', False) and not re.search(r'<a?:\w+:\d+>', heading.content):
            heading.content = re.sub(r'^(#{1,3}\s+)?', lambda m: (m[1] or '') + MESSAGE + ' ', heading.content, count=1)
            heading._dm_rendered_content = heading.content
    if not re.search(r'<a?:\w+:\d+>', str(view.to_components())):
        view.add_item(container(discord.ui.TextDisplay(f'-# {MESSAGE} CloudTIX')))
    return normalize_controls(view)


def prepare(content, kwargs, user_id, *, editing=False, message=None):
    result = dict(kwargs)
    custom = result.pop('_university_dm_custom_copy', False)
    language = preferences.language(user_id)
    view = result.pop('view', MISSING)
    legacy_view = view if view is not MISSING and view is not None and not isinstance(view, discord.ui.LayoutView) else None
    embed = result.pop('embed', MISSING)
    embeds = result.pop('embeds', MISSING)
    actual_embeds = list(embeds) if embeds is not MISSING and embeds else ([embed] if embed is not MISSING and embed else [])
    text = str(content) if content is not MISSING and content is not None else ''
    if editing and view is MISSING and message is not None and message.components:
        store = getattr(getattr(message, '_state', None), '_view_store', None)
        registered = getattr(store, '_views', {}).get(message.id, {})
        view = next((item.view for item in registered.values() if item.view is not None), None)
        if view is None:
            view = discord.ui.LayoutView.from_message(message, timeout=None)
    if view is MISSING: view = None
    if actual_embeds:
        view = from_embeds(actual_embeds, view)
    elif view is not None and not isinstance(view, discord.ui.LayoutView):
        view = from_view(view)
    if legacy_view is not None and view is not None:
        view.timeout = legacy_view.timeout
        view.interaction_check = legacy_view.interaction_check
        view.on_error = legacy_view.on_error
        view.on_timeout = legacy_view.on_timeout
        for key, value in legacy_view.__dict__.items():
            if key not in view.__dict__:setattr(view, key, value)
        # Callers and callbacks may still await/stop the original plain View.
        legacy_view.wait = lambda: view.wait()
        legacy_view.stop = lambda: view.stop()
        legacy_view.is_finished = lambda: view.is_finished()
    if view is None:
        view = Panel(f'{MESSAGE} CloudTIX', text if text else ('Attached files' if result.get('file') or result.get('files') or result.get('attachments') else ''))
    elif text:
        # content is forbidden beside a V2 view; keep it inside the card.
        view.add_item(container(discord.ui.TextDisplay(text)))
    if custom: view._university_dm_custom_copy = True
    files = list(result.get('files') or []) + ([result['file']] if result.get('file') else [])
    files += [x for x in result.get('attachments') or [] if isinstance(x, discord.File)]
    existing = str(view.to_components())
    for file in files:
        url = 'attachment://' + file.filename
        if url in existing:continue
        if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            view.add_image(url) if isinstance(view, Panel) else view.add_item(container(discord.ui.MediaGallery(discord.MediaGalleryItem(url))))
        else:
            view.add_item(container(discord.ui.File(url)))
    result['view'] = localize(view, language)
    if editing:
        result['content'] = None
        result['embeds'] = []
    else:
        result.pop('tts', None)
        result.pop('suppress_embeds', None)
    return result


def paginate(payload):
    """A V2 message has a 4,000-character total text budget, not per block."""
    view = payload['view']
    blocks = list(view.walk_children())
    length = sum(len(x.content) for x in blocks if isinstance(x, discord.ui.TextDisplay))
    if length <= 4000 and len(blocks) + len(view.children) <= 40:return [payload]
    items, controls = [], []
    accent = None
    def collect(item):
        nonlocal accent
        if isinstance(item, discord.ui.Container):
            if accent is None:accent = item.accent_colour
            for child in item.children:collect(child)
        elif isinstance(item, discord.ui.ActionRow):
            controls.append(item)
        elif isinstance(item, discord.ui.TextDisplay):
            start = 0
            while start < len(item.content):
                end = min(start + 3500, len(item.content))
                for token in re.finditer(r'<a?:\w+:\d+>', item.content):
                    if token.start() < end < token.end():
                        end = token.start()
                        break
                items.append(discord.ui.TextDisplay(item.content[start:end]))
                start = end
        elif isinstance(item, discord.ui.Section):
            for child in item.children:collect(child)
            accessory = item.accessory
            if isinstance(accessory, discord.ui.Thumbnail):
                items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(accessory.media.url)))
            elif isinstance(accessory, discord.ui.Button):
                controls.append(discord.ui.ActionRow(accessory))
        elif not isinstance(item, discord.ui.Separator):
            items.append(item)
    for item in view.children:collect(item)
    groups, current, total, count = [], [], 0, 0
    for item in items + controls:
        size = len(item.content) if isinstance(item, discord.ui.TextDisplay) else 0
        weight = 1 + sum(1 for _ in getattr(item, 'walk_children', lambda: [])())
        if current and (total + size > 3800 or count + weight > 35):
            groups.append(current);current=[];total=0;count=0
        current.append(item);total+=size;count+=weight
    if current:groups.append(current)
    output = []
    uploads = list(payload.get('files') or []) + ([payload['file']] if payload.get('file') else [])
    uploads += [x for x in payload.get('attachments') or [] if isinstance(x, discord.File)]
    for index, group in enumerate(groups):
        page = discord.ui.LayoutView(timeout=view.timeout if index == len(groups)-1 else None)
        if index:
            group = [discord.ui.TextDisplay(f'-# {MESSAGE} CloudTIX')] + group
        page.add_item(container(*group, accent_color=accent))
        packet = dict(payload);packet['view']=page
        packet.pop('file',None);packet.pop('files',None)
        urls = str(page.to_components())
        files = [file for file in uploads if 'attachment://' + file.filename in urls]
        if 'attachments' in packet:
            packet['attachments'] = [x for x in packet['attachments'] if not isinstance(x,discord.File)] + files
        elif files:packet['files']=files
        output.append(packet)
    final = output[-1]['view']
    final.interaction_check = view.interaction_check
    final.on_error = view.on_error;final.on_timeout = view.on_timeout
    for key, value in view.__dict__.items():
        if key not in final.__dict__:setattr(final,key,value)
    view.wait = final.wait;view.stop = final.stop;view.is_finished = final.is_finished
    return output


def _continuation(packet):
    """Edit-only keywords are not valid when sending additional pages."""
    result = dict(packet)
    result.pop('content',None);result.pop('embeds',None)
    attachments = result.pop('attachments',[])
    files = [x for x in attachments if isinstance(x,discord.File)]
    if files:result['files']=files
    result.pop('suppress',None)
    for key in ('ephemeral','username','avatar_url','wait','thread','thread_name','applied_tags','suppress_embeds'):
        result.pop(key,None)
    return result


async def _offer(channel, user_id):
    if preferences.was_offered(user_id):return
    try:
        await _ORIGINAL_SEND(channel, view=LanguageView(user_id, preferences.language(user_id)))
    except discord.HTTPException:
        # The original DM was delivered. A failed optional picker must not
        # trigger retries of a ban/ticket/key notification; try next time.
        log.info('DM language picker could not be delivered to %s', user_id)
        return
    preferences.mark_offered(user_id)


def _recipient(channel):
    return getattr(getattr(channel, 'recipient', None), 'id', None) if isinstance(channel, discord.DMChannel) else None


_ORIGINAL_SEND = discord.abc.Messageable.send


def install(bot):
    global _INSTALLED, _BOT
    _BOT = bot
    bot.add_view(LanguageView())
    if _INSTALLED:return
    _INSTALLED = True

    original_send = discord.abc.Messageable.send
    @functools.wraps(original_send)
    async def send(self, content=None, **kwargs):
        channel = await self._get_channel()
        user_id = _recipient(channel)
        if user_id is None:
            return await original_send(self, content, **kwargs)
        async with _lock(user_id), _view_lock(kwargs.get('view')):
            packets = paginate(prepare(content, kwargs, user_id))
            result = None
            for index, packet in enumerate(packets):
                result = await original_send(self, **packet)
                if index == 0:await _offer(channel, user_id)
            return result
    discord.abc.Messageable.send = send

    original_edit = discord.Message.edit
    @functools.wraps(original_edit)
    async def edit(self, **kwargs):
        user_id = _recipient(self.channel)
        if user_id is None:return await original_edit(self, **kwargs)
        async with _view_lock(kwargs.get('view')):
            content = kwargs.pop('content', MISSING)
            packets = paginate(prepare(content, kwargs, user_id, editing=True, message=self))
            result = await original_edit(self, **packets[0])
            for packet in packets[1:]:await _ORIGINAL_SEND(self.channel, **_continuation(packet))
            return result
    discord.Message.edit = edit

    def response_patch(name, editing=False):
        original = getattr(discord.InteractionResponse, name)
        @functools.wraps(original)
        async def response(self, *args, **kwargs):
            interaction = self._parent
            if interaction.guild_id is not None:return await original(self, *args, **kwargs)
            user_id = interaction.user.id
            register_interaction(interaction)
            content = args[0] if args else kwargs.pop('content', MISSING)
            async with _delivery_lock(user_id, editing), _view_lock(kwargs.get('view')):
                packets = paginate(prepare(content, kwargs, user_id, editing=editing, message=interaction.message))
                result = await original(self, **packets[0])
                if not editing:
                    await _offer(interaction.channel, user_id)
                for packet in packets[1:]:await _ORIGINAL_SEND(interaction.channel, **_continuation(packet))
            return result
        setattr(discord.InteractionResponse, name, response)
    original_defer = discord.InteractionResponse.defer
    @functools.wraps(original_defer)
    async def defer(self, *args, **kwargs):
        register_interaction(self._parent)
        return await original_defer(self, *args, **kwargs)
    discord.InteractionResponse.defer = defer

    original_modal = discord.InteractionResponse.send_modal
    @functools.wraps(original_modal)
    async def send_modal(self, modal):
        interaction = self._parent
        if interaction.guild_id is None:
            register_interaction(interaction)
            localize_modal(modal, preferences.language(interaction.user.id))
        return await original_modal(self, modal)
    discord.InteractionResponse.send_modal = send_modal

    response_patch('send_message')
    response_patch('edit_message', True)

    original_interaction_edit = discord.Interaction.edit_original_response
    @functools.wraps(original_interaction_edit)
    async def interaction_edit(self, **kwargs):
        if self.guild_id is not None:return await original_interaction_edit(self, **kwargs)
        register_interaction(self)
        async with _view_lock(kwargs.get('view')):
            packets = paginate(prepare(kwargs.pop('content', MISSING), kwargs, self.user.id, editing=True, message=self.message))
            result = await original_interaction_edit(self, **packets[0])
            for packet in packets[1:]:await _ORIGINAL_SEND(self.channel, **_continuation(packet))
            return result
    discord.Interaction.edit_original_response = interaction_edit

    for name, editing in [('send', False), ('edit_message', True)]:
        original = getattr(discord.Webhook, name)
        def make_webhook(original, editing):
            @functools.wraps(original)
            async def webhook(self, *args, **kwargs):
                destination = _FOLLOWUPS.get(self.token)
                if destination and destination[2] < time.monotonic():
                    _FOLLOWUPS.pop(self.token, None)
                    destination = None
                if not destination:return await original(self, *args, **kwargs)
                channel, user_id, _ = destination
                if editing:
                    message_id = args[0] if args else kwargs.pop('message_id')
                    packets = paginate(prepare(kwargs.pop('content', MISSING), kwargs, user_id, editing=True))
                    result = await original(self, message_id, **packets[0])
                    for packet in packets[1:]:await _ORIGINAL_SEND(channel, **_continuation(packet))
                    return result
                content = args[0] if args else kwargs.pop('content', MISSING)
                async with _lock(user_id), _view_lock(kwargs.get('view')):
                    packets = paginate(prepare(content, kwargs, user_id))
                    result = await original(self, **packets[0])
                    await _offer(channel, user_id)
                    for packet in packets[1:]:await _ORIGINAL_SEND(channel, **_continuation(packet))
                    return result
            return webhook
        setattr(discord.Webhook, name, make_webhook(original, editing))


def register_interaction(interaction):
    # Deferred interactions may send only a followup, without send_message.
    if interaction.guild_id is None:
        now = time.monotonic()
        for token in list(_FOLLOWUPS):
            if _FOLLOWUPS[token][2] < now: _FOLLOWUPS.pop(token, None)
        _FOLLOWUPS[interaction.followup.token] = (interaction.channel, interaction.user.id, now + 900)
