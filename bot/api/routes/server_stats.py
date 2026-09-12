"""Dashboard-API für Mitgliederzähler in Sprachkanälen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import feature_gates
from utils import server_stats_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Der Bot ist nicht auf diesem Server.")
    return guild


def _has_premium(guild_id: int, *, configure: bool = False) -> bool:
    return (feature_gates.can_configure_premium_guild(guild_id) if configure
            else feature_gates.is_premium_guild(guild_id))

def _payload(guild, settings: dict, *, premium: bool) -> dict:
    members = list(getattr(guild, "members", ()) or ())
    bots = sum(1 for member in members if member.bot)
    counts = {
        "humans": len(members) - bots,
        "bots": bots,
        "boosts": int(getattr(guild, "premium_subscription_count", 0) or 0),
        "online": sum(
            1 for member in members
            if not member.bot and str(getattr(member, "status", "offline")) != "offline"
        ),
        "roles": max(0, len(getattr(guild, "roles", ()) or ()) - 1),
        "channels": len(getattr(guild, "channels", ()) or ()),
    }

    channels = {}
    for kind in store.KINDS:
        channel_id = settings[f"{kind}_channel_id"]
        channel = guild.get_channel(channel_id) if channel_id else None
        channels[kind] = {
            "id": str(channel_id) if channel_id else None,
            "name": getattr(channel, "name", None),
            "missing": bool(channel_id and channel is None),
        }

    me = guild.me
    can_manage = bool(me and me.guild_permissions.manage_channels)
    return {
        "guild_id": str(guild.id),
        "premium": premium,
        **{f"{kind}_enabled": settings[f"{kind}_enabled"] for kind in store.KINDS},
        "counts": counts,
        "channels": channels,
        "can_manage_channels": can_manage,
        "warning": "" if can_manage else "Dem Bot fehlt das Recht „Kanäle verwalten“.",
    }


@router.get("/{guild_id}", summary="Server-Stats Einstellungen")
async def get_settings(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    premium = _has_premium(guild_id)
    return _payload(guild, await store.get(guild_id), premium=premium)


@router.patch("/{guild_id}", summary="Server-Stats einstellen")
async def patch_settings(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    allowed = {f"{kind}_enabled" for kind in store.KINDS}
    updates = {key: bool(value) for key, value in data.items() if key in allowed}
    if not updates:
        raise HTTPException(400, "Keine Server-Stats-Einstellung übermittelt.")

    actor = str(data.get("actor") or "")
    premium = _has_premium(guild_id, configure=True)
    if not premium and any(
        updates.get(f"{kind}_enabled") for kind in store.PREMIUM_KINDS
    ):
        raise HTTPException(
            403,
            "Online-Nutzer, Rollen und Kanäle sind nur mit Premium verfügbar.",
        )

    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        raise HTTPException(403, "Dem Bot fehlt das Recht „Kanäle verwalten“.")

    settings = await store.save(guild_id, updates)
    cog = bot.get_cog("ServerStats")
    if cog is None:
        raise HTTPException(503, "Das Server-Stats-Modul ist noch nicht bereit.")

    try:
        await cog.sync_guild(guild)
    except Exception as exc:
        raise HTTPException(502, f"Die Statistikkanäle konnten nicht aktualisiert werden: {exc}")

    result = _payload(guild, await store.get(guild_id), premium=premium)
    await feature_audit.log_action(
        "server_stats_changed",
        actor=actor,
        detail=f"guild {guild_id}: {updates}",
    )
    return result
