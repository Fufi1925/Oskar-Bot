# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anonymous chat API                                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The dashboard side of anonymous channels.

Everything a server owner needs without touching chat commands: which
channels are anonymous, how the messages look, who may write, and the
staff-only log of who actually wrote what.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import anonchat_store as store
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


async def _refresh(bot, guild_id: int) -> None:
    """
    Tell the cog to reload.

    Without this the bot keeps relaying with the old settings until it
    restarts, and the dashboard looks like it saved nothing.
    """
    cog = bot.get_cog("AnonChat")
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


def _permission_problem(guild, channel, mode: str) -> str | None:
    """What is missing for this channel to work, in plain German."""
    if channel is None:
        return "Den Kanal gibt es nicht mehr."

    me = guild.me
    if me is None:
        return None
    permissions = channel.permissions_for(me)

    if not permissions.manage_messages:
        return (
            "Dem Bot fehlt „Nachrichten verwalten“ — die Originalnachricht "
            "bliebe stehen und der Kanal wäre nicht anonym."
        )
    if not permissions.send_messages:
        return "Der Bot darf in diesem Kanal nicht schreiben."
    if mode == store.MODE_WEBHOOK and not permissions.manage_webhooks:
        return (
            "Für den Webhook-Modus fehlt „Webhooks verwalten“. Ohne das "
            "schreibt der Bot unter seinem eigenen Namen."
        )
    return None


def _shape(guild, setup: dict) -> dict:
    channel = guild.get_channel(setup["channel_id"]) if guild else None
    log_channel = (
        guild.get_channel(setup["log_channel_id"])
        if guild and setup.get("log_channel_id") else None
    )

    return {
        **{k: v for k, v in setup.items() if k not in (
            "channel_id", "log_channel_id", "required_role_id", "blocked_role_id",
        )},
        # IDs stay strings; Number() rounds a snowflake's last digits off.
        "channel_id": str(setup["channel_id"]),
        "channel_name": channel.name if channel else None,
        "log_channel_id": (
            str(setup["log_channel_id"]) if setup.get("log_channel_id") else None
        ),
        "log_channel_name": log_channel.name if log_channel else None,
        "required_role_id": (
            str(setup["required_role_id"]) if setup.get("required_role_id") else None
        ),
        "blocked_role_id": (
            str(setup["blocked_role_id"]) if setup.get("blocked_role_id") else None
        ),
        "enabled": bool(setup.get("enabled")),
        "allow_attachments": bool(setup.get("allow_attachments")),
        "allow_links": bool(setup.get("allow_links")),
        "allow_mentions": bool(setup.get("allow_mentions")),
        "strip_replies": bool(setup.get("strip_replies")),
        "problem": _permission_problem(guild, channel, setup.get("mode")) if guild else None,
    }


@router.get("/{guild_id}", summary="Anonymous channels and their settings")
async def get_anonchat(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    guild = bot.get_guild(guild_id)

    setups = [_shape(guild, s) for s in await store.list_channels(db, guild_id)]

    blocked = []
    for entry in await store.blocked_list(db, guild_id):
        member = guild.get_member(entry["user_id"]) if guild else None
        blocked.append({
            "user_id": str(entry["user_id"]),
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "reason": entry["reason"],
            "at": entry["at"],
        })

    return {
        "guild_id": str(guild_id),
        "channels": setups,
        "blocked": blocked,
        "stats": await store.stats(db, guild_id),
        "defaults": store.DEFAULTS,
        "modes": [
            {
                "id": store.MODE_WEBHOOK,
                "label": "Über einen Webhook",
                "description": "Eigener Name und eigenes Bild — sieht aus wie ein "
                               "echter Nutzer. Empfohlen.",
            },
            {
                "id": store.MODE_BOT,
                "label": "Als Bot-Nachricht",
                "description": "Der Bot postet unter seinem eigenen Namen. "
                               "Braucht kein Webhook-Recht.",
            },
        ],
    }


@router.post("/{guild_id}", summary="Make a channel anonymous, or change it")
async def save_anonchat(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Only the keys actually sent are written."""
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    channel_id = str(data.get("channel_id") or "")
    if not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal auswählen.")

    channel = guild.get_channel(int(channel_id))
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    # Refuse up front rather than swallowing every message later. A
    # missing webhook right only downgrades the look, so it is a warning
    # further down; a missing "manage messages" breaks the anonymity
    # itself and is refused here.
    me = guild.me
    if me is not None and not channel.permissions_for(me).manage_messages:
        raise HTTPException(
            status_code=400,
            detail=f"In #{channel.name} fehlt dem Bot „Nachrichten verwalten“. "
                   "Ohne das bliebe die Originalnachricht stehen und der Kanal "
                   "wäre nicht anonym.",
        )

    updates = {key: data[key] for key in store.DEFAULTS if key in data}
    if not updates:
        updates = {"enabled": 1}

    merged = await store.save_channel(db, guild_id, int(channel_id), updates)
    await _refresh(bot, guild_id)

    await feature_audit.log_action(
        "anonchat_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"#{channel.name}: {', '.join(sorted(updates))}",
    )

    warning = _permission_problem(guild, channel, merged.get("mode"))
    return {
        "status": "success",
        "result": f"#{channel.name} ist anonym." if merged["enabled"]
                  else f"#{channel.name} gespeichert (aus).",
        "warning": warning,
        "channel": _shape(guild, merged),
    }


@router.delete("/{guild_id}/{channel_id}", summary="Make a channel normal again")
async def delete_anonchat(
    guild_id: int, channel_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.delete_channel(db, guild_id, channel_id):
        raise HTTPException(status_code=404, detail="Dieser Kanal war nicht anonym.")

    await _refresh(bot, guild_id)
    await feature_audit.log_action(
        "anonchat_removed", actor=actor or "dashboard",
        guild_id=guild_id, detail=str(channel_id),
    )
    return {"status": "success", "result": "Der Kanal ist wieder normal."}


# ══════════════════════════════════════════════════════════════════════
#  The staff-only log
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/log", summary="Who wrote what")
async def get_log(
    guild_id: int, limit: int = 50, user_id: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    """
    The moderation trail.

    Anonymous towards other members, not towards the people running the
    server — without this, an anonymous channel is a free pass for
    harassment with nobody to hold responsible.
    """
    db = await _db()
    guild = bot.get_guild(guild_id)

    entries = await store.recent_log(
        db, guild_id, limit=limit,
        user_id=int(user_id) if user_id.isdigit() else 0,
    )

    out = []
    for entry in entries:
        member = guild.get_member(entry["user_id"]) if guild else None
        channel = guild.get_channel(entry["channel_id"]) if guild else None
        out.append({
            "id": entry["id"],
            "user_id": str(entry["user_id"]),
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "channel_id": str(entry["channel_id"]),
            "channel_name": channel.name if channel else None,
            "content": entry["content"],
            "at": entry["at"],
            "url": (
                f"https://discord.com/channels/{guild_id}/{entry['channel_id']}"
                f"/{entry['message_id']}"
                if entry["message_id"] else None
            ),
        })

    return {"entries": out, "count": len(out)}


@router.get("/{guild_id}/log/{message_id}", summary="Who wrote this message")
async def who_wrote(
    guild_id: int, message_id: int, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = bot.get_guild(guild_id)

    author_id = await store.find_author(db, guild_id, message_id)
    if author_id is None:
        raise HTTPException(
            status_code=404,
            detail="Zu dieser Nachricht gibt es keinen Eintrag — vielleicht ist "
                   "sie älter als die Aufbewahrungszeit.",
        )

    member = guild.get_member(author_id) if guild else None
    return {
        "user_id": str(author_id),
        "name": member.display_name if member else f"Unbekannt ({author_id})",
        "avatar": member.display_avatar.url if member else None,
    }


# ══════════════════════════════════════════════════════════════════════
#  Blocked members
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/blocked", summary="Bar somebody from posting")
async def block_user(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    user_id = str(data.get("user_id") or "")
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte ein Mitglied auswählen.")

    await store.block(
        db, guild_id, int(user_id),
        reason=str(data.get("reason") or ""),
        by_id=int(str(data.get("actor", "0")))
        if str(data.get("actor", "0")).isdigit() else 0,
    )
    await feature_audit.log_action(
        "anonchat_block", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=user_id,
    )
    return {"status": "success", "result": "Kann nicht mehr anonym schreiben."}


@router.delete("/{guild_id}/blocked/{user_id}", summary="Lift a block")
async def unblock_user(
    guild_id: int, user_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.unblock(db, guild_id, user_id):
        raise HTTPException(status_code=404, detail="Diese Person war nicht gesperrt.")

    await feature_audit.log_action(
        "anonchat_unblock", actor=actor or "dashboard",
        guild_id=guild_id, detail=str(user_id),
    )
    return {"status": "success", "result": "Darf wieder anonym schreiben."}


@router.post("/{guild_id}/preview", summary="How a message would look")
async def preview(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Run the text through the same filters the relay uses.

    Saves posting into a live channel just to find out that links get
    stripped or the message is too long.
    """
    settings = store.normalise(data.get("settings") or {})
    text = str(data.get("content", ""))

    cleaned = store.clean_content(text, settings)
    return {
        "alias": settings["alias"],
        "avatar_url": settings["avatar_url"],
        "original": text,
        "result": cleaned,
        "changed": cleaned != text,
        "notes": [
            note for note in [
                "Links werden entfernt." if not settings["allow_links"] else None,
                "Erwähnungen benachrichtigen niemanden."
                if not settings["allow_mentions"] else None,
                f"Gekürzt auf {settings['max_length']} Zeichen."
                if len(text) > settings["max_length"] else None,
            ] if note
        ],
    }
