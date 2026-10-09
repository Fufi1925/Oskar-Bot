"""Ticket forms, feedback and persisted automation state."""
import asyncio
import re
import json
import time
from datetime import datetime
from types import SimpleNamespace

import discord
from utils.component_emojis import category_text
from utils import ticket_settings, ticket_notify, guild_modules
from utils.emoji import TICK, CROSS, MESSAGE, WARNING, STAR
from utils.panels import Panel


async def remove_lock_controls(message):
    """Preserve existing ticket cards and remove only their two old buttons."""
    view_type=discord.ui.LayoutView if message.flags.components_v2 else discord.ui.View
    view=view_type.from_message(message)
    removed=False
    for item in list(view.walk_children()):
        if getattr(item,'custom_id',None) not in ('t_lock','t_unlock'):continue
        parent=getattr(item,'parent',None)
        (parent or view).remove_item(item);removed=True
        if isinstance(parent,discord.ui.ActionRow) and not parent.children:
            (parent.parent or view).remove_item(parent)
    if removed:await message.edit(view=view,allowed_mentions=discord.AllowedMentions.none())
    return removed


async def migrate_lock_controls(cog):
    semaphore=asyncio.Semaphore(3)
    async def migrate(ticket):
        guild=cog.bot.get_guild(ticket['guild_id'])
        channel=guild.get_channel(ticket['channel_id']) if guild else None
        if not channel:return
        async with semaphore:
            try:
                async with asyncio.timeout(15):
                    async for message in channel.history(limit=50,oldest_first=True):
                        if message.author.id==cog.bot.user.id:
                            await remove_lock_controls(message)
            except (discord.HTTPException,TimeoutError):pass
    await asyncio.gather(*(migrate(t) for t in cog.db.fetchall('SELECT guild_id,channel_id FROM open_tickets WHERE closed_at IS NULL')))


def staff_ids(cog, guild_id, category_id):
    cat = cog.db.fetchone('SELECT notified_roles,panel_id FROM ticket_categories WHERE category_id=? AND guild_id=?', (category_id,guild_id))
    ids = set()
    if cat:
        ids.update(int(x) for x in (cat['notified_roles'] or '').split(',') if x.isdigit())
        if cat['panel_id']:
            row = cog.db.fetchone('SELECT staff_roles FROM ticket_panels WHERE guild_id=? AND panel_id=?', (guild_id,cat['panel_id']))
            if row: ids.update(int(x) for x in (row['staff_roles'] or '').split(',') if x.isdigit())
    row = cog.db.fetchone('SELECT staff_roles FROM guild_configs WHERE guild_id=?', (guild_id,))
    if row: ids.update(int(x) for x in (row['staff_roles'] or '').split(',') if x.isdigit())
    return ids


def is_staff(cog, member, category_id):
    return member.guild_permissions.administrator or bool(staff_ids(cog,member.guild.id,category_id).intersection(r.id for r in member.roles))


def add_fields(modal, questions):
    inputs=[]
    for question in questions[:5]:
        label=str(question.get('label') or 'Question')[:45]
        kind=question.get('type','short'); required=bool(question.get('required',True))
        description=question.get('description') or None
        if kind in ('file','image'):
            field=discord.ui.FileUpload(required=required,min_values=1 if required else 0,max_values=5)
        elif kind in ('select','radio'):
            field=discord.ui.Select(options=[discord.SelectOption(label=x[:100],value=str(i)) for i,x in enumerate(question.get('options',[])[:25])],
                min_values=1 if required else 0,max_values=1,required=required,placeholder=question.get('placeholder') or None)
        elif kind=='checkbox':
            field=discord.ui.Checkbox()
        else:
            field=discord.ui.TextInput(style=discord.TextStyle.paragraph if kind=='paragraph' else discord.TextStyle.short,
                required=required,max_length=question.get('max_length',4000 if kind=='paragraph' else 200),
                placeholder=question.get('placeholder') or None)
        wrapper = discord.ui.Label(text=label,description=description,component=field)
        wrapper._university_dm_custom_copy = True
        modal.add_item(wrapper)
        inputs.append((question,field))
    return inputs


def form_answers(inputs):
    answers=[]
    for question,field in inputs:
        kind=question.get('type','short'); answer={'label':question['label'],'type':kind,'public':question.get('public',False)}
        if kind in ('image','file'):
            answer['attachments']=list(field.values or [])
        elif kind in ('select','radio'):
            choices=question.get('options',[])
            answer['value']=', '.join(choices[int(x)] for x in field.values if str(x).isdigit() and int(x)<len(choices))
        elif kind=='checkbox':
            if question.get('required',True) and not field.value:
                raise ValueError('Please confirm every required checkbox.')
            answer['value']='Yes' if field.value else 'No'
        else: answer['value']=field.value
        answers.append(answer)
    return answers


async def send_answers(channel,title,answers, *, quoted=False):
    # Separate cards keep each form answer within the Components V2 text budget.
    for answer in answers:
        value=str(answer.get('value') or 'No answer')
        if quoted: value='\n'.join('> '+line for line in value.splitlines())
        for offset in range(0,len(value),3500):
            body=value[offset:offset+3500]
            await channel.send(view=Panel(f'{MESSAGE} {title}',f"**{discord.utils.escape_markdown(answer['label'])}**\n{body}"),allowed_mentions=discord.AllowedMentions.none())
        for attachment in answer.get('attachments',[]):
            try:
                file=await attachment.to_file()
                await channel.send(file=file,allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: pass


class ActionFormModal(discord.ui.Modal):
    def __init__(self,cog,category_id,questions,title,submit):
        super().__init__(title=title,timeout=900)
        self.cog,self.category_id,self.submit=cog,category_id,submit
        self.inputs=add_fields(self,questions)

    async def on_submit(self,interaction):
        try: answers=form_answers(self.inputs)
        except ValueError as exc:
            return await interaction.response.send_message(view=Panel(f'{WARNING} Check your answers',str(exc)),ephemeral=True)
        await self.submit(interaction,answers)

    async def on_error(self,interaction,error):
        if not interaction.response.is_done():
            await interaction.response.send_message(view=Panel(f'{CROSS} Could not submit', 'Please try again or contact the support team.'),ephemeral=True)


class RatingModal(discord.ui.Modal):
    def __init__(self,cog,ticket):
        super().__init__(title='Rate your support',timeout=900)
        self.cog,self.ticket=cog,ticket
        self.settings=ticket.get('_settings') if isinstance(ticket,dict) else None
        self.settings=self.settings or cog.preferences(ticket['guild_id'],ticket['category_db_id'])
        self.score=discord.ui.Select(options=[discord.SelectOption(label=f'{x} / 5',value=str(x),emoji=STAR) for x in range(1,6)])
        self.add_item(discord.ui.Label(text='Your rating',component=self.score))
        self.inputs=add_fields(self,self.settings['rating_questions'][:4])

    async def on_submit(self,interaction):
        if not guild_modules.is_enabled(self.ticket['guild_id'],'tickets'):
            return await interaction.response.send_message(view=Panel(f'{CROSS} Ticket system disabled','Please contact the server administrators.'),ephemeral=True)
        if interaction.user.id!=self.ticket['creator_id']:
            return await interaction.response.send_message(view=Panel(f'{CROSS} Rating unavailable','Only the ticket creator can submit feedback.'),ephemeral=True)
        if not self.settings['rating_enabled']:
            return await interaction.response.send_message(view=Panel('Ratings disabled','Please contact the support team directly.'),ephemeral=True)
        try: answers=form_answers(self.inputs)
        except ValueError as exc:
            return await interaction.response.send_message(view=Panel('Check your answers',str(exc)),ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        score=int(self.score.values[0])
        cursor=self.cog.db.execute('INSERT OR IGNORE INTO ticket_ratings VALUES(?,?,?,?,?,?)',(self.ticket['channel_id'],self.ticket['guild_id'],interaction.user.id,score,'\n'.join(f"{x['label']}: {x.get('value','')}" for x in answers),time.time()))
        if not cursor.rowcount:
            return await interaction.followup.send(view=Panel(f'{WARNING} Already rated','You have already submitted feedback for this ticket.',tone='warning'),ephemeral=True)
        guild=self.cog.bot.get_guild(self.ticket['guild_id'])
        cat=self.cog.db.fetchone('SELECT name,panel_id FROM ticket_categories WHERE category_id=?',(self.ticket['category_db_id'],))
        created=datetime.fromisoformat(self.ticket['created_at']);closed=datetime.fromisoformat(self.ticket['closed_at'])
        fields={'creator':f"<@{self.ticket['creator_id']}>",'supporter':f"<@{self.ticket['closed_by_id']}>",'case':f"T-{self.ticket['guild_id']}-{self.ticket['ticket_number']:04d}",
            'category':cat['name'] if cat else (self.ticket.get('_category_name','Unknown') if isinstance(self.ticket,dict) else 'Unknown'),'panel':str(cat['panel_id']) if cat else 'Unknown','duration':str(closed-created)}
        for key,public in [('rating_channel_id',False),('rating_public_channel_id',True)]:
            channel=guild.get_channel(int(self.settings[key])) if guild and self.settings[key] else None
            if not channel: continue
            visible=self.settings['rating_values'] if public else list(fields)
            body=f"**Rating**\n> {STAR * score} **{score} / 5**\n\n**Ticket details**\n"+'\n'.join(f"> **{name.title()}:** {discord.utils.escape_markdown(fields[name])}" for name in visible)
            try:
                await channel.send(view=Panel(f'{STAR} Support feedback',body,tone='success'),allowed_mentions=discord.AllowedMentions.none())
                await send_answers(channel,'Feedback form',[x for x in answers if not public or x['public']],quoted=True)
            except discord.HTTPException: pass
        await interaction.followup.send(view=Panel(f'{TICK} Feedback submitted','Your feedback has been successfully submitted.',tone='success'),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())


async def claim(cog,channel,category_id,user):
    cursor=cog.db.execute('UPDATE open_tickets SET is_claimed=1,claimed_by_id=? WHERE channel_id=? AND closed_at IS NULL AND is_claimed=0',(user.id,channel.id))
    if not cursor.rowcount: return False
    settings=cog.preferences(channel.guild.id,category_id)
    if settings['claim_category_id']:
        target=channel.guild.get_channel(int(settings['claim_category_id']))
        if isinstance(target,discord.CategoryChannel): await channel.edit(category=target)
    if settings['restrict_claimed']:
        for role_id in staff_ids(cog,channel.guild.id,category_id):
            role=channel.guild.get_role(role_id)
            if role: await channel.set_permissions(role,send_messages=False)
        await channel.set_permissions(user,view_channel=True,send_messages=True,read_message_history=True)
    await channel.send(view=Panel(f'{TICK} Ticket claimed',f'{user.mention} is now handling this request.'))
    return True


async def release(view,interaction):
    ticket=view.cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?',(view.ch_id,))
    if not ticket or not ticket['is_claimed']:
        return await interaction.response.send_message(view=Panel('Ticket not claimed','This ticket is already available to the team.'),ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    settings=view.cog.preferences(interaction.guild.id,view.cat_id)
    await restore_claim(view.cog,interaction.channel,ticket,settings)
    await interaction.followup.send(view=Panel('Ticket released','The ticket is available to the support team again.'),ephemeral=True)


async def restore_claim(cog,channel,ticket,settings):
    if settings['restrict_claimed']:
        for role_id in staff_ids(cog,channel.guild.id,ticket['category_db_id']):
            role=channel.guild.get_role(role_id)
            if role: await channel.set_permissions(role,send_messages=True)
        owner=channel.guild.get_member(ticket['claimed_by_id'])
        if owner: await channel.set_permissions(owner,overwrite=None)
    cat=cog.db.fetchone('SELECT discord_category_id FROM ticket_categories WHERE category_id=?',(ticket['category_db_id'],))
    target=channel.guild.get_channel(cat['discord_category_id']) if cat else None
    if target and settings['claim_category_id']: await channel.edit(category=target)
    cog.db.execute('UPDATE open_tickets SET is_claimed=0,claimed_by_id=NULL WHERE channel_id=?',(channel.id,))


class ToolsView(discord.ui.View):
    def __init__(self,cog,channel_id,category_id):
        super().__init__(timeout=900)
        self.cog,self.channel_id,self.category_id=cog,channel_id,category_id
        self.settings=cog.preferences(cog.db.fetchone('SELECT guild_id FROM open_tickets WHERE channel_id=?',(channel_id,))['guild_id'],category_id)
        priority=discord.ui.Select(placeholder='Ticket priority',custom_id='ticket_tool_priority',options=[discord.SelectOption(label=x.title(),value=x) for x in ('low','normal','high','urgent')])
        priority.callback=self.priority;self.add_item(priority)
        if self.settings['snippets']:
            snippets=discord.ui.Select(placeholder='Send a saved reply',custom_id='ticket_tool_snippet',options=[discord.SelectOption(label=x['name'],value=str(i)) for i,x in enumerate(self.settings['snippets'])])
            snippets.callback=self.snippet;self.add_item(snippets)
        if self.settings['allow_participants']:
            participants=discord.ui.UserSelect(placeholder='Add a participant',custom_id='ticket_tool_participant',max_values=1)
            participants.callback=self.participant;self.add_item(participants)

    async def allowed(self,interaction,staff=True):
        ticket=self.cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?',(self.channel_id,))
        okay=ticket and not ticket['closed_at'] and (is_staff(self.cog,interaction.user,self.category_id) or (not staff and ticket['creator_id']==interaction.user.id))
        if not okay: await interaction.response.send_message(view=Panel(f'{CROSS} Action unavailable','Please ask the support team to perform this action.'),ephemeral=True)
        return okay

    async def priority(self,interaction):
        if not await self.allowed(interaction):return
        value=interaction.data['values'][0]
        if value not in ('low','normal','high','urgent'):return
        self.cog.db.execute('UPDATE ticket_workflow SET priority=? WHERE channel_id=?',(value,self.channel_id))
        await interaction.response.send_message(view=Panel('Priority updated',value.title()),ephemeral=True)

    async def snippet(self,interaction):
        if not await self.allowed(interaction):return
        item=self.settings['snippets'][int(interaction.data['values'][0])]
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(view=Panel(f'{MESSAGE} Support reply',item['text']))
        await interaction.followup.send(view=Panel('Reply sent','The saved reply was posted in this ticket.'),ephemeral=True)

    async def participant(self,interaction):
        if not await self.allowed(interaction,staff=False):return
        member=interaction.guild.get_member(int(interaction.data['values'][0]))
        if not member:return await interaction.response.send_message(view=Panel('Member unavailable','This member is no longer on the server.'),ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.set_permissions(member,view_channel=True,send_messages=True,read_message_history=True,attach_files=True)
        await interaction.followup.send(view=Panel('Participant added',member.mention),ephemeral=True)


async def activity(cog,message):
    if not message.guild or message.author.bot:return
    ticket=cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=? AND closed_at IS NULL',(message.channel.id,))
    if not ticket:return
    settings=cog.preferences(message.guild.id,ticket['category_db_id'])
    cog.db.execute('INSERT INTO ticket_workflow(channel_id,last_activity,priority) VALUES(?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_activity=excluded.last_activity,alerted=NULL,team_alerted=NULL', (message.channel.id,time.time(),settings['priority']))
    if settings['auto_claim'] and not ticket['is_claimed'] and is_staff(cog,message.author,ticket['category_db_id']):
        try:await claim(cog,message.channel,ticket['category_db_id'],message.author)
        except discord.HTTPException:pass


async def member_leave(cog,member):
    for ticket in cog.db.fetchall('SELECT * FROM open_tickets WHERE guild_id=? AND creator_id=? AND closed_at IS NULL',(member.guild.id,member.id)):
        channel=member.guild.get_channel(ticket['channel_id'])
        if not channel:continue
        settings=cog.preferences(member.guild.id,ticket['category_db_id'])
        try:
            if settings['on_leave']=='notify':await channel.send(view=Panel(f'{WARNING} Creator left',f'<@{member.id}> has left this server.'))
            elif settings['on_leave']=='delete':await channel.delete(reason='Ticket creator left the server; configured action')
        except discord.HTTPException:pass


async def tick(cog):
    from cogs.commands.ticket import TicketActionsView
    now=time.time()
    for ticket in cog.db.fetchall('SELECT * FROM open_tickets WHERE closed_at IS NULL'):
        guild=cog.bot.get_guild(ticket['guild_id']); channel=guild.get_channel(ticket['channel_id']) if guild else None
        if not channel:continue
        from utils import guild_modules
        if not guild_modules.is_enabled(guild.id, 'tickets'):continue
        settings=cog.preferences(guild.id,ticket['category_db_id'])
        state=cog.db.fetchone('SELECT * FROM ticket_workflow WHERE channel_id=?',(channel.id,))
        if not state:
            # Existing tickets start with a fresh grace period after migration.
            cog.db.execute('INSERT INTO ticket_workflow(channel_id,last_activity,priority) VALUES(?,?,?)',(channel.id,now,settings['priority']))
            continue
        elapsed=now-state['last_activity']; priority=state['priority']
        ranking={'low':0,'normal':1,'high':2,'urgent':3}
        protect=settings['no_auto_close_priority']!='off' and ranking[priority]>=ranking[settings['no_auto_close_priority']]
        try:
            if (settings['auto_alert'] or settings['close_after_alert']) and not state['alerted'] and elapsed>=settings['auto_alert_seconds']:
                await channel.send(f"<@{ticket['creator_id']}>",allowed_mentions=discord.AllowedMentions(everyone=False,users=True,roles=False))
                await channel.send(view=Panel(f'{WARNING} Waiting for your reply','Please respond to the support team so we can continue helping you.'))
                cog.db.execute('UPDATE ticket_workflow SET alerted=? WHERE channel_id=?',(now,channel.id))
            team_delay=settings['high_priority_seconds'] if priority in ('high','urgent') and settings['high_priority_seconds'] else settings['auto_team_alert_seconds']
            if ticket_settings.is_open(settings) and settings['auto_team_alert'] and not state['team_alerted'] and elapsed>=team_delay:
                ids=staff_ids(cog,guild.id,ticket['category_db_id'])
                if ids:await channel.send(' '.join(f'<@&{x}>' for x in ids),allowed_mentions=discord.AllowedMentions(everyone=False,users=False,roles=[guild.get_role(x) for x in ids if guild.get_role(x)]))
                await channel.send(view=Panel(f'{WARNING} Support reminder','This ticket is waiting for a response from the team.'))
                cog.db.execute('UPDATE ticket_workflow SET team_alerted=? WHERE channel_id=?',(now,channel.id))
            if ticket_settings.is_open(settings) and settings['auto_unclaim'] and ticket['is_claimed'] and elapsed>=settings['auto_unclaim_seconds']:
                await restore_claim(cog,channel,ticket,settings)
                await channel.send(view=Panel('Ticket released','This inactive ticket is available to the team again.'))
            close_due=settings['auto_close'] and elapsed>=settings['auto_close_seconds']
            close_due=close_due or (settings['close_after_alert'] and state['alerted'] and now-state['alerted']>=settings['auto_alert_seconds'])
            if close_due and not protect:
                async def nothing(*args,**kwargs):pass
                async def feedback(*args,**kwargs):pass
                interaction=SimpleNamespace(guild=guild,user=guild.me,channel=channel,message=None,response=SimpleNamespace(defer=nothing),followup=SimpleNamespace(send=feedback))
                view=TicketActionsView(cog,channel.id,ticket['category_db_id']);view._closing_answers=[]
                lock=cog._action_locks.setdefault(channel.id,asyncio.Lock())
                if not lock.locked():
                    async with lock:
                        await view._close(interaction,None)
        except Exception as exc:
            print(f'[tickets] Automation failed for {channel.id}: {type(exc).__name__}')
    try:
        await refresh_panels(cog)
    except Exception as exc:
        print(f'[tickets] Panel refresh failed: {type(exc).__name__}')


async def refresh_panels(cog):
    if not cog.db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_panels'"):
        return
    cache = getattr(cog, '_panel_capacity_cache', {})
    cog._panel_capacity_cache = cache
    for panel in cog.db.fetchall('SELECT * FROM ticket_panels WHERE message_id IS NOT NULL'):
        guild = cog.bot.get_guild(panel['guild_id'])
        channel = guild.get_channel(panel['channel_id']) if guild else None
        if not channel: continue
        from utils import guild_modules
        if not guild_modules.is_enabled(guild.id, 'tickets'):continue
        settings = ticket_settings.sync_settings(cog.db,guild.id,panel['panel_id'])
        lines = []
        categories = cog.db.fetchall('SELECT * FROM ticket_categories WHERE guild_id=? AND panel_id=?', (guild.id,panel['panel_id']))
        for category in categories:
            preferences = cog.preferences(guild.id,category['category_id'])
            if not preferences['active']:continue
            count = cog.db.fetchone('SELECT COUNT(*) AS n FROM open_tickets WHERE guild_id=? AND category_db_id=? AND closed_at IS NULL', (guild.id,category['category_id']))['n']
            if preferences['capacity']:
                maximum=preferences['capacity']; lines.append(f"{category_text(category['name'], category['emoji'])}: `{count}/{maximum}` ({round(count/maximum*100)}%)")
        description=panel['embed_description'] or 'Choose a category below to create a ticket.'
        if settings['show_capacity'] and lines:description=description[:2200]+'\n\n## Ticket availability\n'+'\n'.join(lines)
        signature=(description,json.dumps(dict(panel),sort_keys=True),json.dumps([{**dict(c),'settings':cog.preferences(guild.id,c['category_id'])} for c in categories],sort_keys=True),json.dumps(settings,sort_keys=True))
        if cache.get(panel['panel_id'])==signature:continue
        controls=cog.create_panel_view(guild.id,panel['panel_id'])
        try:
            message=await channel.fetch_message(panel['message_id'])
            await message.edit(view=Panel(panel['embed_title'] or panel['name'],description[:max(100,3800-len(panel['embed_title'] or panel['name']))],accent=panel['embed_color'] or 0x5865f2,
                image_url=panel['embed_image_url'] or None,thumbnail_url=panel['embed_thumbnail_url'] or None,buttons=list(controls.children) if controls else []))
            cache[panel['panel_id']]=signature
        except discord.HTTPException:pass


def protect_actions(view):
    """V2 panels keep callbacks but do not inherit a legacy View's checks."""
    for item in view.children:
        original = item.callback
        async def guarded(interaction, callback=original):
            try:
                if await view.interaction_check(interaction):
                    await callback(interaction)
            except discord.HTTPException:
                reply = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
                await reply(view=Panel(f'{CROSS} Action could not be completed', 'Please check the bot permissions and try again. The bot needs access to this ticket and permission to manage channels.'),ephemeral=True)
        guarded._university_ticket_action = True
        item.callback = guarded
