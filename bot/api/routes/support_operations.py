"""Owner-only API for the support-server operations dashboard tab."""
from __future__ import annotations

import json
import os
import time

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api.metrics import latency_milliseconds
from api.dependencies import get_bot, run_on_bot_loop
from utils import (command_stats, feature_flags, premium_membership,
                   support_operations as ops, template_store)
from utils.feature_services import runtime
from utils.server_stats_store import MAIN_SUPPORT_GUILD_ID

router = APIRouter()


def _valid_discord_id(value: str) -> bool:
    return (0 < len(value) <= 20 and value.isascii() and value.isdigit()
            and 0 < int(value) < 2**64)


def _guard(guild_id: int, actor: str) -> None:
    if guild_id != MAIN_SUPPORT_GUILD_ID:
        raise HTTPException(404, "Diese Seite existiert auf diesem Server nicht.")
    if not _valid_discord_id(actor) or not ops.is_owner(actor):
        raise HTTPException(403, "Nur globale OWNER_IDS dürfen diese Support-Konsole verwenden.")


def _guild(bot, guild_id: str) -> discord.Guild:
    if not _valid_discord_id(str(guild_id)) or not (guild := bot.get_guild(int(guild_id))):
        raise HTTPException(404, "Der Bot ist nicht mit diesem Server verbunden.")
    return guild


def _deployment() -> dict:
    snap = runtime.snapshot()
    return {
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID") or "lokal/unbekannt",
        "commit": (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unbekannt")[:12],
        "instance": os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("HOSTNAME") or "main",
        "heartbeat": int(runtime.last_heartbeat), "uptime_seconds": snap["uptime_seconds"],
        "discord_status": snap["discord_status"], "integrity": snap["integrity"],
        "failed_extensions": snap["failed_extensions"],
        "recovered_extensions": snap["recovered_extensions"],
        "last_backup_at": snap["last_backup_at"],
    }


@router.get("/{guild_id}/access")
async def access(guild_id: int, actor: str = ""):
    """Check visibility without loading operational databases or bot metrics."""
    _guard(guild_id, actor)
    return {"allowed": True}


@router.get("/{guild_id}/overview")
async def overview(guild_id: int, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor)
    error_channel = ops.get_setting("error_channel_id")
    users = sum(g.member_count or 0 for g in bot.guilds)
    errors = ops.list_errors(50)
    incidents = ops.list_incidents(25)
    counts = ops.console_counts()
    return {
        "global": {
            "guilds": len(bot.guilds), "users": users,
            "commands": await command_stats.total_uses(),
            "latency_ms": latency_milliseconds(bot.latency, 0),
            **counts,
        },
        "deployment": _deployment(),
        "settings": {"error_channel_id": error_channel},
        "errors": errors,
        "incidents": incidents,
        "audit": ops.list_audit(50),
        "features": feature_flags.describe(),
        "feature_values": feature_flags.all_values(),
        "feature_rollouts": feature_flags.all_rollouts(),
    }


@router.get("/{guild_id}/errors/{error_id}")
async def error_lookup(guild_id: int, error_id: str, actor: str = ""):
    _guard(guild_id, actor)
    row = ops.get_error(error_id.strip().upper())
    if not row:
        raise HTTPException(404, "Fehler nicht gefunden.")
    return row


@router.post("/{guild_id}/settings/error-channel")
async def configure_error_channel(guild_id: int, data: dict, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor)
    guild = _guild(bot, str(guild_id)); channel_id = str(data.get("channel_id") or "")
    channel = guild.get_channel(int(channel_id)) if _valid_discord_id(channel_id) else None
    if not isinstance(channel, discord.TextChannel):
        raise HTTPException(400, "Wähle einen Textkanal des Support-Servers.")
    if channel.permissions_for(guild.default_role).view_channel:
        raise HTTPException(400, "Der Fehlerkanal muss für @everyone unsichtbar sein.")
    me = guild.me; permissions = channel.permissions_for(me) if me else None
    if not permissions or not all((permissions.view_channel, permissions.send_messages,
                                   permissions.read_message_history,
                                   permissions.create_public_threads)):
        raise HTTPException(400, "Dem Bot fehlen Kanal-, Nachrichten-, Verlauf- oder Threadrechte.")
    ops.set_setting("error_channel_id", channel.id)
    ops.audit(actor, "error_channel_set", str(channel.id), channel.name)
    return {"status": "success", "error_channel_id": str(channel.id)}


@router.post("/{guild_id}/errors/{error_id}/status")
async def error_status(guild_id: int, error_id: str, data: dict, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor); status = str(data.get("status") or "")
    try: row = ops.set_error_status(error_id, status, actor)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if not row: raise HTTPException(404, "Fehler nicht gefunden.")
    await run_on_bot_loop(ops.refresh_error_report(bot, error_id))
    return row


@router.post("/{guild_id}/errors/{error_id}/ticket")
async def error_ticket(guild_id: int, error_id: str, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor)
    row, result = await run_on_bot_loop(ops.create_developer_ticket(bot, error_id, actor))
    if row is None: raise HTTPException(404, result)
    if result not in {"created", "already"}: raise HTTPException(400, result)
    return {"status": result, "error": row}


@router.post("/{guild_id}/incidents")
async def incident_create(guild_id: int, data: dict, actor: str = ""):
    _guard(guild_id, actor); title = str(data.get("title") or "").strip()
    if not title: raise HTTPException(400, "Ein Titel ist erforderlich.")
    severity = str(data.get("severity") or "medium")
    if severity not in ops.SEVERITIES:
        raise HTTPException(400, "Ungültiger Schweregrad.")
    if len(title) > 150 or len(str(data.get("description") or "")) > 2000:
        raise HTTPException(400, "Titel oder Beschreibung ist zu lang.")
    return ops.create_incident(title, severity,
                               str(data.get("description") or ""), actor)


@router.post("/{guild_id}/incidents/{incident_id}")
async def incident_update(guild_id: int, incident_id: str, data: dict, actor: str = ""):
    _guard(guild_id, actor)
    try: row = ops.update_incident(incident_id, str(data.get("status") or ""), str(data.get("note") or ""), actor)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if not row: raise HTTPException(404, "Incident nicht gefunden.")
    return row


@router.post("/{guild_id}/features/{key}")
async def feature_update(guild_id: int, key: str, data: dict, actor: str = ""):
    _guard(guild_id, actor)
    if key not in feature_flags.FEATURE_DEFAULTS: raise HTTPException(404, "Feature Flag nicht gefunden.")
    if "enabled" not in data and "rollout" not in data:
        raise HTTPException(400, "Aktivierung oder Rollout erforderlich.")
    if "enabled" in data and not isinstance(data["enabled"], bool):
        raise HTTPException(400, "Aktivierung muss true oder false sein.")
    if "rollout" in data:
        value = data["rollout"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise HTTPException(400, "Rollout muss eine ganze Zahl zwischen 0 und 100 sein.")
    # Validate the entire request before changing either value.
    if "enabled" in data: await run_on_bot_loop(feature_flags.set_values({key: data["enabled"]}))
    if "rollout" in data: await run_on_bot_loop(feature_flags.set_rollout(key, data["rollout"]))
    ops.audit(actor, "feature_flag_changed", key, json.dumps(data)[:500])
    return {"key": key, "enabled": feature_flags.is_enabled(key),
            "rollout": feature_flags.all_rollouts().get(key, 100)}


@router.get("/{guild_id}/diagnose/{target_guild_id}")
async def diagnose(guild_id: int, target_guild_id: str, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor); guild = _guild(bot, target_guild_id)
    return {"guild": {"id": str(guild.id), "name": guild.name}, **await run_on_bot_loop(ops.diagnose_guild(guild))}


@router.get("/{guild_id}/servers/{target_guild_id}")
async def server_lookup(guild_id: int, target_guild_id: str, actor: str = "", bot=Depends(get_bot)):
    _guard(guild_id, actor); guild = _guild(bot, target_guild_id)
    owner = guild.owner or bot.get_user(guild.owner_id); me = guild.me
    premium = premium_membership.guild_status(guild.id)
    return {"id": str(guild.id), "name": guild.name, "icon": str(guild.icon.url) if guild.icon else "",
            "owner_id": str(guild.owner_id), "owner_name": str(owner) if owner else "Unbekannt",
            "members": guild.member_count or 0, "channels": len(guild.channels), "roles": len(guild.roles),
            "joined_at": int(me.joined_at.timestamp()) if me and me.joined_at else None,
            "bot_permissions": {"administrator": bool(me and me.guild_permissions.administrator),
                                "manage_roles": bool(me and me.guild_permissions.manage_roles),
                                "send_messages": bool(me and me.guild_permissions.send_messages)},
            "premium": premium}


@router.get("/{guild_id}/premium-history")
async def premium_history(guild_id: int, server_id: str = "", user_id: str = "", actor: str = ""):
    _guard(guild_id, actor)
    if not server_id and not user_id: raise HTTPException(400, "Server-ID oder Nutzer-ID erforderlich.")
    if server_id and (not _valid_discord_id(server_id) or int(server_id) > 2**63 - 1):
        raise HTTPException(400, "Ungültige Server-ID.")
    if user_id and not _valid_discord_id(user_id): raise HTTPException(400, "Ungültige Nutzer-ID.")
    return {"server": premium_membership.guild_status(int(server_id)) if server_id else None,
            "account": premium_membership.account_status(user_id) if user_id else None}


async def _support_case(server_id: str, user_id: str):
    from api.routes.support import _ensure
    async with aiosqlite.connect("db/admin_config.db") as db:
        db.row_factory = aiosqlite.Row; await _ensure(db)
        async with db.execute("SELECT * FROM dashboard_support_cases WHERE guild_id=? AND supporter_id=? ORDER BY CASE status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, id DESC LIMIT 1", (server_id, user_id)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


@router.get("/{guild_id}/support-access")
async def support_access(guild_id: int, server_id: str, user_id: str, actor: str = ""):
    _guard(guild_id, actor)
    if not _valid_discord_id(server_id) or not _valid_discord_id(user_id): raise HTTPException(400, "Ungültige ID.")
    return {"case": await _support_case(server_id, user_id)}


@router.post("/{guild_id}/support-access/revoke")
async def support_access_revoke(guild_id: int, data: dict, actor: str = ""):
    _guard(guild_id, actor); server_id=str(data.get("server_id") or ""); user_id=str(data.get("user_id") or "")
    if not _valid_discord_id(server_id) or not _valid_discord_id(user_id):
        raise HTTPException(400, "Ungültige ID.")
    row = await _support_case(server_id, user_id)
    if not row: raise HTTPException(404, "Supportfall nicht gefunden.")
    now=int(time.time())
    async with aiosqlite.connect("db/admin_config.db") as db:
        cursor = await db.execute("UPDATE dashboard_support_cases SET status='closed',closed_at=?,updated_at=? WHERE guild_id=? AND supporter_id=? AND status IN ('pending','accepted')", (now,now,server_id,user_id))
        revoked = cursor.rowcount
        await db.commit()
    if revoked:
        ops.audit(actor, "support_access_revoked", str(row["id"]), f"guild={server_id}, supporter={user_id}, cases={revoked}")
    return {"status": "closed" if revoked else row["status"], "case_id": row["id"], "revoked": revoked}


@router.get("/{guild_id}/templates/{template_id}")
async def template_inspect(guild_id: int, template_id: int, actor: str = ""):
    _guard(guild_id, actor)
    if not 0 < template_id <= 2**63 - 1:
        raise HTTPException(400, "Ungültige Template-ID.")
    async with aiosqlite.connect(template_store.DB_PATH) as db:
        await template_store.ensure_schema(db)
        item = await template_store.get_template(db, template_id, as_admin=True)
    if not item: raise HTTPException(404, "Vorlage nicht gefunden.")
    payload = item.get("payload") or {}; raw = json.dumps(payload, ensure_ascii=False)
    # Never return the payload itself to a Discord/dashboard browser view.
    item.pop("payload", None)
    return {"template": item, "inspection": {"size": len(raw),
            "modules": list(payload.keys()) if isinstance(payload, dict) else [],
            "contains_secret": template_store.contains_secret(payload)}}
