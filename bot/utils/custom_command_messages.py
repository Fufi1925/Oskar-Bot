"""Message snapshots and render helpers for dashboard custom commands.

A snapshot deliberately stores only Discord data that can be replayed safely.
Component custom_ids from another application are never copied: link buttons
remain links, while interactive buttons/select options get local action lists.
"""
from __future__ import annotations

import io
import re
from typing import Any, Awaitable, Callable

import aiohttp
import discord

URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
DISCORD_FILE_HOSTS = ("cdn.discordapp.com", "media.discordapp.net")


def _emoji(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    name = str(raw.get("name") or "")
    ident = raw.get("id")
    return f"<{'a' if raw.get('animated') else ''}:{name}:{ident}>" if ident else name


def _text_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _text_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _text_values(nested)


def _component_dict(component: Any) -> dict:
    try:
        return component.to_dict()
    except Exception:
        return {}


def _walk_components(items: list[Any], out: dict) -> None:
    for item in items:
        raw = item if isinstance(item, dict) else _component_dict(item)
        kind = int(raw.get("type", 0) or 0)
        children = raw.get("components") or []
        if kind in (1, 9, 17):
            if kind == 17 and raw.get("accent_color") is not None:
                out["accent_color"] = raw.get("accent_color")
            _walk_components(children, out)
            if kind == 9 and raw.get("accessory"):
                _walk_components([raw["accessory"]], out)
        elif kind == 10:
            text = str(raw.get("content") or "")
            if text:
                out["blocks"].append({"type": "text", "text": text})
        elif kind == 14:
            out["blocks"].append({"type": "divider", "visible": not bool(raw.get("divider", False))})
        elif kind == 12:
            for media in raw.get("items") or []:
                url = str((media.get("media") or {}).get("url") or media.get("url") or "")
                if url:
                    out["blocks"].append({"type": "image", "url": url})
        elif kind == 11:
            url = str((raw.get("media") or {}).get("url") or "")
            if url:
                out["blocks"].append({"type": "image", "url": url})
        elif kind == 13:
            url = str((raw.get("file") or raw.get("media") or {}).get("url") or "")
            if url:
                out["blocks"].append({"type": "file", "url": url, "spoiler": bool(raw.get("spoiler"))})
        elif kind == 2:
            style = int(raw.get("style", 1) or 1)
            button = {
                "id": f"imported-{len(out['buttons']) + 1}",
                "label": str(raw.get("label") or "Button")[:80],
                "emoji": _emoji(raw.get("emoji")),
                "style": {1: "blue", 2: "gray", 3: "green", 4: "red"}.get(style, "gray"),
                "actions": [],
                "private_response": True,
            }
            if style == 5 and raw.get("url"):
                button["url"] = str(raw["url"])
            out["buttons"].append(button)
        elif kind in (3, 5, 6, 7, 8):
            options = []
            for option in raw.get("options") or []:
                options.append({
                    "id": f"option-{len(options) + 1}",
                    "label": str(option.get("label") or option.get("value") or "Option")[:100],
                    "value": str(option.get("value") or option.get("label") or "option")[:100],
                    "description": str(option.get("description") or "")[:100],
                    "emoji": _emoji(option.get("emoji")),
                    "actions": [],
                    "private_response": True,
                })
            # User/channel/role/mentionable menus do not expose static options.
            # Keep the menu recognisable and editable instead of pretending its
            # original callback can be transferred between applications.
            if not options:
                options = [{"id": "option-1", "label": "Auswahl", "value": "selection", "description": "", "emoji": "", "actions": [], "private_response": True}]
            out["selects"].append({
                "id": f"select-{len(out['selects']) + 1}",
                "placeholder": str(raw.get("placeholder") or "Auswählen …")[:150],
                "min_values": int(raw.get("min_values", 1) or 0),
                "max_values": int(raw.get("max_values", 1) or 1),
                "options": options[:25],
            })


def snapshot(message: discord.Message) -> tuple[dict, list[dict], list[dict]]:
    parsed = {"blocks": [], "buttons": [], "selects": [], "accent_color": None}
    _walk_components(list(message.components or []), parsed)
    attachments = [{
        "url": item.url,
        "filename": item.filename,
        "content_type": item.content_type or "application/octet-stream",
        "size": item.size,
        "spoiler": item.is_spoiler(),
    } for item in message.attachments]
    embeds = [embed.to_dict() for embed in message.embeds]
    urls = list(URL_RE.findall(message.content or ""))
    # Links in embed descriptions/fields and V2 text displays are just as
    # important as links in plain content, so scan every stored text value.
    for value in _text_values({"embeds": embeds, "blocks": parsed["blocks"]}):
        urls.extend(URL_RE.findall(value))
    for button in parsed["buttons"]:
        if button.get("url"):
            urls.append(button["url"])
    for attachment in attachments:
        urls.append(attachment["url"])
    for embed in embeds:
        for value in (embed.get("url"), (embed.get("image") or {}).get("url"),
                      (embed.get("thumbnail") or {}).get("url")):
            if value:
                urls.append(str(value))
    return {
        "source_url": message.jump_url,
        "source_channel_id": str(message.channel.id),
        "source_message_id": str(message.id),
        "content": message.content or "",
        "embeds": embeds[:10],
        "attachments": attachments[:10],
        "links": list(dict.fromkeys(urls))[:50],
        "components_v2": bool(getattr(message.flags, "components_v2", False)),
        "blocks": parsed["blocks"],
        "accent_color": parsed["accent_color"],
        "detected": {
            "embeds": len(embeds), "attachments": len(attachments),
            "links": len(set(urls)), "buttons": len(parsed["buttons"]),
            "selects": len(parsed["selects"]), "blocks": len(parsed["blocks"]),
        },
    }, parsed["buttons"], parsed["selects"]


def _embed(raw: dict) -> discord.Embed:
    try:
        return discord.Embed.from_dict(raw)
    except Exception:
        return discord.Embed(description=str(raw.get("description") or "")[:4096])


def _style(value: str) -> discord.ButtonStyle:
    return {"blue": discord.ButtonStyle.primary, "gray": discord.ButtonStyle.secondary,
            "green": discord.ButtonStyle.success, "red": discord.ButtonStyle.danger}.get(value, discord.ButtonStyle.primary)


def build_view(message: dict, buttons: list, selects: list,
               dispatch: Callable[..., Awaitable[None]]):
    """Build either a classic View or a Components-V2 LayoutView."""
    v2 = bool(message.get("components_v2"))
    view = discord.ui.LayoutView(timeout=900) if v2 else discord.ui.View(timeout=900)
    # Generic builders hide the originating cog behind local callbacks. Keep
    # that origin so the shared module gate can pause custom-command actions;
    # message-editor actions (a tool, not a cog) remain independent.
    from utils.guild_modules import module_for_callable
    view._university_module = module_for_callable(dispatch)
    container = None
    if v2:
        from discord.ui import Container, File, MediaGallery, Separator, TextDisplay
        color = message.get("accent_color")
        container = Container(accent_color=int(color) if isinstance(color, int) else None)
        for block in message.get("blocks") or []:
            kind = block.get("type")
            if kind == "text" and block.get("text"):
                container.add_item(TextDisplay(str(block["text"])[:4000]))
            elif kind == "divider":
                container.add_item(Separator(visible=bool(block.get("visible", True))))
            elif kind == "image" and str(block.get("url", "")).startswith(("https://", "attachment://")):
                container.add_item(MediaGallery(discord.MediaGalleryItem(str(block["url"]))))
            elif kind == "file" and str(block.get("url", "")).startswith(("https://", "attachment://")):
                container.add_item(File(str(block["url"]), spoiler=bool(block.get("spoiler"))))

    rows = []
    for start in range(0, len(buttons), 5):
        row_items = []
        for definition in buttons[start:start + 5]:
            url = str(definition.get("url") or "")
            button = discord.ui.Button(
                label=str(definition.get("label") or "Button")[:80],
                emoji=str(definition.get("emoji") or "") or None,
                style=discord.ButtonStyle.link if url else _style(str(definition.get("style") or "blue")),
                url=url or None,
            )
            if not url:
                button._university_module = view._university_module
                async def clicked(interaction: discord.Interaction, data=definition):
                    await dispatch(interaction, data.get("actions") or [], bool(data.get("private_response")))
                button.callback = clicked
            row_items.append(button)
        if row_items:
            rows.append(discord.ui.ActionRow(*row_items) if v2 else row_items)

    for definition in selects[:5]:
        options = []
        for option in (definition.get("options") or [])[:25]:
            options.append(discord.SelectOption(
                label=str(option.get("label") or "Option")[:100],
                value=str(option.get("value") or option.get("id") or "option")[:100],
                description=str(option.get("description") or "")[:100] or None,
                emoji=str(option.get("emoji") or "") or None,
            ))
        if not options:
            continue
        select = discord.ui.Select(
            placeholder=str(definition.get("placeholder") or "Auswählen …")[:150],
            min_values=max(0, min(int(definition.get("min_values", 1) or 0), len(options))),
            max_values=max(1, min(int(definition.get("max_values", 1) or 1), len(options))),
            options=options,
        )
        select._university_module = view._university_module
        async def selected(interaction: discord.Interaction, data=definition, component=select):
            chosen = set(component.values)
            actions = []
            for option in data.get("options") or []:
                if str(option.get("value") or option.get("id")) in chosen:
                    actions.extend(option.get("actions") or [])
            await dispatch(interaction, actions, True)
        select.callback = selected
        rows.append(discord.ui.ActionRow(select) if v2 else [select])

    if v2:
        for row in rows:
            container.add_item(row)
        view.add_item(container)
    else:
        for row in rows:
            for item in row:
                view.add_item(item)
    return view if (buttons or selects or (v2 and (message.get("blocks") or []))) else None


async def attachment_files(message: dict) -> list[discord.File]:
    """Re-upload imported Discord CDN attachments; never fetch arbitrary URLs."""
    files: list[discord.File] = []
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for item in (message.get("attachments") or [])[:10]:
            url = str(item.get("url") or "")
            if not any(url.startswith(f"https://{host}/") for host in DISCORD_FILE_HOSTS):
                continue
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    data = await response.read()
                    if len(data) > 25 * 1024 * 1024:
                        continue
                    files.append(discord.File(io.BytesIO(data), filename=str(item.get("filename") or "attachment"), spoiler=bool(item.get("spoiler"))))
            except (aiohttp.ClientError, TimeoutError):
                continue
    return files
