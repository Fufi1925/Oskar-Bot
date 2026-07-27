# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anti-nuke alerts API                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Settings and history for the anti-nuke reporting.

Before this the seventeen anti-nuke modules did everything in silence:
whether an attack was stopped, whether the bot lacked the permission to
stop it, or whether anti-nuke was switched off entirely all looked the
same from outside — nothing anywhere.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import nuke_alert
from utils import partner_bot

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


@router.get("/{guild_id}", summary="Alert settings, history and readiness")
async def get_alerts(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    settings = await nuke_alert.get_settings(guild_id)

    entries = []
    for row in await nuke_alert.incidents(guild_id, 50):
        entries.append({
            "id": row["id"],
            "action": row["action"],
            "action_label": nuke_alert.LABELS.get(row["action"], row["action"]),
            "outcome": row["outcome"],
            # IDs stay strings; Number() rounds a snowflake's tail off.
            "executor_id": str(row["executor_id"] or ""),
            "executor_name": row["executor_name"] or "",
            "detail": row["detail"] or "",
            "at": row["at"],
        })

    channel = (
        guild.get_channel(int(settings["channel_id"]))
        if guild and settings.get("channel_id") else None
    )

    return {
        "guild_id": str(guild_id),
        **{k: v for k, v in settings.items() if k != "channel_id"},
        "enabled": bool(settings["enabled"]),
        "create_channel": bool(settings["create_channel"]),
        "clean_channels": bool(settings["clean_channels"]),
        "ping_owner": bool(settings["ping_owner"]),
        "dm_owner": bool(settings["dm_owner"]),
        "channel_id": str(settings["channel_id"]) if settings["channel_id"] else None,
        "channel_name": channel.name if channel else None,
        "incidents": entries,
        # The single most useful number here: without these permissions
        # the bot can watch an attack and do nothing about it.
        "missing_permissions": nuke_alert.missing_permissions(guild) if guild else [],
        "partner_configured": bool(
            os.getenv("PARTNER_BOT_CLIENT_ID") and partner_bot.is_configured()
        ),
    }


@router.patch("/{guild_id}", summary="Change the alert settings")
async def patch_alerts(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    updates = {k: v for k, v in data.items() if k in nuke_alert.DEFAULTS}
    if not updates:
        return {"status": "success", "result": "Nichts zu ändern."}

    merged = await nuke_alert.save_settings(guild_id, updates)
    await feature_audit.log_action(
        "nuke_alert_settings", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=", ".join(sorted(updates)),
    )
    return {"status": "success", "result": "Gespeichert.", "settings": merged}


@router.post("/{guild_id}/test", summary="Send a test alert")
async def test_alert(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Post a sample report.

    Worth having: the alert channel is chosen at the moment of an attack,
    and finding out then that the bot cannot write anywhere is too late.
    """
    guild = _guild_or_404(bot, guild_id)
    settings = await nuke_alert.get_settings(guild_id)

    channel = await nuke_alert.alert_channel(guild, settings)
    if channel is None:
        raise HTTPException(
            status_code=400,
            detail="Es gibt keinen Kanal, in den ich schreiben könnte — und ich "
                   "darf auch keinen anlegen. Gib mir „Kanäle verwalten“ oder "
                   "wähle oben einen Kanal aus.",
        )

    from utils.panels import Panel

    missing = nuke_alert.missing_permissions(guild)
    await channel.send(view=Panel(
        "Testmeldung",
        "So würde eine Anti-Nuke-Meldung aussehen. Es ist nichts passiert.",
        (
            "**Mir fehlen gerade:** " + ", ".join(missing)
            + "\n\nMit diesen Lücken könnte ich einen echten Angriff nicht stoppen."
            if missing else
            "**Rechte:** vollständig — ich könnte eingreifen."
        ),
        tone="warning" if missing else "success",
    ))

    return {
        "status": "success",
        "result": f"Testmeldung in #{channel.name} gesendet.",
        "channel": channel.name,
        "missing_permissions": missing,
    }


@router.get("/{guild_id}/partner-invite", summary="Invite link for the template bot")
async def partner_invite(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    """
    A one-click link that adds the second bot and tells it we sent it.

    Deliberately a link and not an automatic action: Discord has no API
    for one bot to add another. The OAuth flow needs a signed-in human,
    on purpose — otherwise a compromised bot could pull in a dozen more.
    """
    guild = _guild_or_404(bot, guild_id)

    client_id = os.getenv("PARTNER_BOT_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="PARTNER_BOT_CLIENT_ID ist nicht gesetzt — ohne die Client-ID "
                   "des zweiten Bots kann ich keinen Link bauen.",
        )

    if not partner_bot.is_configured():
        # Without the shared secret the other bot cannot tell our link
        # apart from anybody else's, so say so rather than pretending.
        return {
            "url": partner_bot.invite_url(
                client_id, guild_id=guild_id,
                user_id=int(actor) if actor.isdigit() else 0,
            ),
            "signed": False,
            "warning": (
                "PARTNER_HANDSHAKE_SECRET ist nicht gesetzt. Der Link "
                "funktioniert, aber der zweite Bot kann nicht überprüfen, dass "
                "er wirklich von hier kommt."
            ),
        }

    return {
        "url": partner_bot.invite_url(
            client_id, guild_id=guild_id,
            user_id=int(actor) if actor.isdigit() else 0,
            extra={"guild_name": guild.name[:80]},
        ),
        "signed": True,
        "expires_in": partner_bot.MAX_AGE,
        "warning": "",
    }
