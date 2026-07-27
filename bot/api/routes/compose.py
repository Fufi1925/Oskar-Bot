# ╔══════════════════════════════════════════════════════════════════╗
# ║   Compose: send a freely designed message as the bot             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Build a message in the dashboard and post it into a channel.

Plain text, a classic embed, or a Components V2 layout assembled from
blocks the author arranges themselves.

The existing `/actions/{guild}/message/send` route managed a title, a
body and a colour in one fixed shape. Everything past that meant editing
Python.

Messages can also be edited afterwards, which matters more than it
sounds: a rules post with a typo otherwise has to be deleted and posted
again, losing its pins, links and reactions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import message_builder as builder

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


def _channel(guild, raw) -> object:
    channel_id = str(raw or "")
    if not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal auswählen.")

    channel = guild.get_channel(int(channel_id))
    # hasattr rather than isinstance: a thread can be posted in too, but
    # is not a TextChannel.
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    me = guild.me
    if me is not None:
        permissions = channel.permissions_for(me)
        if not permissions.send_messages:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
            )
        if not permissions.embed_links:
            raise HTTPException(
                status_code=403,
                detail=f"In #{channel.name} fehlt „Links einbetten“ — Embeds und "
                       "Karten kämen dort leer an.",
            )
    return channel


@router.post("/{guild_id}/check", summary="Is this message sendable?")
async def check(guild_id: int, data: dict):
    """
    Report everything wrong at once.

    Discord answers a malformed message with a terse 400 that names no
    field, so the checks happen here where they can say which one.
    """
    problems = builder.validate(data)
    return {
        "ok": not problems,
        "problems": problems,
        "summary": builder.describe(data),
        "limits": builder.LIMITS,
    }


@router.post("/{guild_id}/send", summary="Post the message")
async def send(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, data.get("channel_id"))

    problems = builder.validate(data)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    kwargs = builder.build(data)

    # Mentions are off unless asked for: a bot posting @everyone because
    # somebody pasted it into a rules text is a bad afternoon.
    if not data.get("allow_mentions"):
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()

    try:
        message = await channel.send(**kwargs)
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord hat die Nachricht abgelehnt: {exc}"
        )

    if data.get("pin"):
        try:
            await message.pin(reason="Über das Dashboard angepinnt")
        except Exception:
            pass  # a full pin list is not worth failing the send over

    await feature_audit.log_action(
        "message_sent", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{data.get('kind', 'text')} in #{channel.name}",
    )
    return {
        "status": "success",
        "result": f"Gesendet in #{channel.name}.",
        "message_id": str(message.id),
        "url": message.jump_url,
    }


@router.post("/{guild_id}/edit", summary="Change a message the bot sent")
async def edit(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Rewrite an existing message.

    Only messages the bot itself sent can be edited — Discord does not
    allow anything else, and saying so up front beats a confusing 403.
    """
    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, data.get("channel_id"))

    message_id = str(data.get("message_id") or "")
    if not message_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte die Nachrichten-ID angeben.")

    problems = builder.validate(data)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        raise HTTPException(
            status_code=404,
            detail="In diesem Kanal gibt es keine Nachricht mit dieser ID.",
        )
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail="Der Bot darf diesen Kanal nicht lesen."
        )

    if message.author.id != bot.user.id:
        raise HTTPException(
            status_code=400,
            detail="Diese Nachricht stammt nicht vom Bot — fremde Nachrichten "
                   "kann Discord nicht bearbeiten lassen.",
        )

    kwargs = builder.build(data)
    # An edit has to clear whatever the message had before, otherwise a
    # switch from embed to plain text leaves the old embed sitting there.
    payload = {
        "content": kwargs.get("content"),
        "embed": kwargs.get("embed"),
        "view": kwargs.get("view"),
    }
    if "view" in kwargs:
        payload = {"view": kwargs["view"]}
    else:
        payload.setdefault("content", None)
        payload["embeds"] = [kwargs["embed"]] if kwargs.get("embed") else []
        payload.pop("embed", None)
        payload.pop("view", None)

    try:
        await message.edit(**payload)
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord hat die Änderung abgelehnt: {exc}"
        )

    await feature_audit.log_action(
        "message_edited", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{message_id} in #{channel.name}",
    )
    return {
        "status": "success",
        "result": "Nachricht geändert.",
        "url": message.jump_url,
    }


@router.get("/{guild_id}/fetch", summary="Read a message back for editing")
async def fetch(
    guild_id: int, channel_id: str, message_id: str,
    bot: "universitybot" = Depends(get_bot),
):
    """Load an existing bot message so it can be edited in the dashboard."""
    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, channel_id)

    if not message_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine gültige ID angeben.")

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden.")

    embeds = []
    for embed in message.embeds:
        embeds.append({
            "title": embed.title or "",
            "description": embed.description or "",
            "color": f"#{embed.color.value:06x}" if embed.color else "",
            "footer_text": embed.footer.text if embed.footer else "",
            "author_name": embed.author.name if embed.author else "",
            "image": embed.image.url if embed.image else "",
            "thumbnail": embed.thumbnail.url if embed.thumbnail else "",
            "fields": [
                {"name": f.name, "value": f.value, "inline": f.inline}
                for f in embed.fields
            ],
        })

    return {
        "message_id": str(message.id),
        "content": message.content or "",
        "embeds": embeds,
        "is_ours": message.author.id == bot.user.id,
        "url": message.jump_url,
        # V2 layouts cannot be read back into blocks, so say so rather
        # than silently offering a broken editor.
        "editable": message.author.id == bot.user.id and not message.components,
        "note": (
            "Diese Nachricht enthält Knöpfe oder eine Karte — sie lässt sich "
            "hier nicht zurücklesen, nur überschreiben."
            if message.components else ""
        ),
    }
