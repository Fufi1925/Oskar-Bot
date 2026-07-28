# ╔══════════════════════════════════════════════════════════════════╗
# ║   Automod                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The automod tab.

Replaces the pair of handlers in guilds.py, which stored whatever key
the dashboard sent -- and the dashboard sent names no listener used:

    dashboard wrote   anti_spam / mute
    the cogs read     "Anti spam" / "Mute"

So every switch in the tab wrote a row that nothing would ever match.
Turning a rule on did nothing, and turning it off was impossible because
"is this rule on?" was answered by whether a punishment row existed at
all.

Rules are addressed by a short stable key here; the store translates to
the legacy names on the way to the database so a server set up over chat
keeps working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import automod_store as store
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
    return {
        # Snowflakes travel as strings: a JSON number loses the last digits.
        "id": str(channel_id) if channel_id else None,
        "name": getattr(channel, "name", None),
        "missing": channel is None and bool(channel_id),
    }


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    colour = getattr(role, "color", None)
    return {
        "id": str(role_id) if role_id else None,
        "name": getattr(role, "name", None),
        "colour": getattr(colour, "value", colour) if colour is not None else None,
        "missing": role is None and bool(role_id),
    }


def _warnings(guild, settings: dict) -> list[str]:
    """Everything standing between this configuration and it working."""
    problems = list(store.readiness(settings))
    if guild is None:
        return problems

    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None) if me is not None else None

    if perms is not None:
        needed = {
            "mute": ("moderate_members", "Mitglieder timeouten"),
            "kick": ("kick_members", "Mitglieder kicken"),
            "ban": ("ban_members", "Mitglieder bannen"),
        }
        wanted = {
            entry.get("punishment")
            for key, entry in (settings.get("rules") or {}).items()
            if store.rule_active(settings, key)
        }
        for punishment in sorted(wanted):
            pair = needed.get(punishment)
            if pair and not getattr(perms, pair[0], False):
                problems.append(
                    f"Eine Regel bestraft mit „{punishment}“, aber dem Bot "
                    f"fehlt „{pair[1]}“."
                )

        if not getattr(perms, "manage_messages", False) and any(
            store.rule_active(settings, k) for k in store.RULES
        ):
            problems.append(
                "Ohne „Nachrichten verwalten“ bleibt die auffällige Nachricht stehen."
            )

    log_id = settings.get("log_channel")
    if log_id and guild.get_channel(int(log_id)) is None:
        problems.append("Den Log-Kanal gibt es nicht mehr.")

    for role_id in settings.get("ignored_roles") or []:
        if guild.get_role(int(role_id)) is None:
            problems.append(f"Eine ausgenommene Rolle ({role_id}) gibt es nicht mehr.")

    return problems


@router.get("/{guild_id}", summary="Automod settings")
async def get_automod(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)
    guild = bot.get_guild(guild_id)

    rules = []
    for key, spec in store.RULES.items():
        entry = settings["rules"][key]
        rules.append({
            "key": key,
            "label": spec["label"],
            "description": spec["description"],
            "threshold_label": spec["threshold_label"],
            "threshold_min": spec["threshold_min"],
            "threshold_max": spec["threshold_max"],
            "has_window": spec["has_window"],
            "defaults": {
                "threshold": spec["threshold"],
                "duration": spec["duration"],
                "punishment": spec["punishment"],
            },
            **entry,
        })

    return {
        "guild_id": str(guild_id),
        "enabled": settings["enabled"],
        "rules": rules,
        "active_count": sum(1 for k in store.RULES if store.rule_active(settings, k)),
        "punishments": list(store.PUNISHMENTS),
        "ignored_roles": [str(r) for r in settings["ignored_roles"]],
        "ignored_roles_info": [
            _role_info(guild, r) for r in settings["ignored_roles"]
        ],
        "ignored_channels": [str(c) for c in settings["ignored_channels"]],
        "ignored_channels_info": [
            _channel_info(guild, c) for c in settings["ignored_channels"]
        ],
        "log_channel": str(settings["log_channel"]) if settings["log_channel"] else None,
        "log_channel_info": _channel_info(guild, settings["log_channel"]),
        "warnings": _warnings(guild, settings),
    }


@router.patch("/{guild_id}", summary="Change the automod settings")
async def patch_automod(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)

    for raw_key, values in (data.get("rules") or {}).items():
        key = store.normalise_rule(raw_key)
        if key is None:
            raise HTTPException(
                status_code=400, detail=f"Unbekannte Regel: {raw_key}"
            )
        if not isinstance(values, dict):
            raise HTTPException(
                status_code=400, detail=f"Die Regel {raw_key} braucht ein Objekt."
            )
        punishment = values.get("punishment")
        if punishment is not None and punishment not in store.PUNISHMENTS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unbekannte Strafe: {punishment}. Erlaubt sind "
                    + ", ".join(store.PUNISHMENTS)
                ),
            )
        for field in ("threshold", "duration", "window"):
            if field not in values or values[field] is None:
                continue
            try:
                number = int(values[field])
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400, detail=f"„{field}“ muss eine Zahl sein."
                )
            if number < 0:
                raise HTTPException(
                    status_code=400, detail=f"„{field}“ kann nicht negativ sein."
                )

    if data.get("log_channel"):
        raw = str(data["log_channel"])
        channel = guild.get_channel(int(raw)) if raw.isdigit() else None
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if not hasattr(channel, "send"):
            raise HTTPException(
                status_code=400, detail="Der Log braucht einen Textkanal."
            )

    for role_id in data.get("ignored_roles") or []:
        if str(role_id).isdigit() and guild.get_role(int(role_id)) is None:
            raise HTTPException(
                status_code=404, detail="Eine der Rollen gibt es nicht mehr."
            )

    settings = await store.save_settings(db, guild_id, data)

    await feature_audit.log_action(
        "automod_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "warnings": _warnings(guild, settings),
    }


@router.post("/{guild_id}/reset", summary="Switch automod off")
async def reset_automod(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    keep_rules = True
    if isinstance(data, dict):
        keep_rules = bool(data.get("keep_rules", True))

    db = await db_manager.get_connection(store.DB_PATH)
    updates: dict = {"enabled": False}
    if not keep_rules:
        updates["rules"] = {key: {"enabled": False} for key in store.RULES}

    await store.save_settings(db, guild_id, updates)

    return {
        "status": "success",
        "result": (
            "Ausgeschaltet. Deine Regeln bleiben gespeichert."
            if keep_rules else "Ausgeschaltet und alle Regeln zurückgesetzt."
        ),
    }
