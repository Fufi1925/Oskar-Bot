# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_bot
from api.schemas import AdminStats, AdminNodeStatus, AdminConfig, AdminConfigUpdate
from typing import TYPE_CHECKING, List
import os
import aiosqlite

from utils import feature_flags
from utils import feature_audit
from utils import feature_reports
from utils import feature_gates
from utils import bot_settings
from utils.feature_services import runtime

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

CONFIG_DB = "db/admin_config.db"

async def init_db():
    async with aiosqlite.connect(CONFIG_DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
        # Default values
        await db.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('maintenance_mode', 'false')")
        await db.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('global_notification', '')")
        await db.commit()

import psutil
import time

@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(bot: "universitybot" = Depends(get_bot)):
    # Calculate DB size and shard info
    total_size: float = 0.0
    db_count = 0
    db_dir = "db"
    if os.path.exists(db_dir):
        for f in os.listdir(db_dir):
            if f.endswith(".db"):
                total_size += float(os.path.getsize(os.path.join(db_dir, f)))
                db_count += 1
    
    mb_size = total_size / (1024 * 1024)
    db_size_str = f"{mb_size:.2f} MB"
    if mb_size > 1024:
        db_size_str = f"{(mb_size / 1024):.2f} GB"

    # System Metrics
    process = psutil.Process(os.getpid())
    # Use a non-blocking interval check or global state for CPU
    cpu_usage = psutil.cpu_percent() 
    ram_raw = process.memory_info().rss
    ram_mb = ram_raw / (1024 * 1024)
    
    total_commands = len(bot.commands)
    loaded_cogs = len(bot.cogs or {})

    # Node Healths
    nodes = [
        AdminNodeStatus(
            name="Primary API Cluster", 
            status="Healthy", 
            load=f"CPU: {cpu_usage}% | RAM: {ram_mb:.1f}MB", 
            icon="Globe"
        ),
        AdminNodeStatus(
            name="Database Shards", 
            status="Healthy" if db_count > 0 else "Warning", 
            load=f"{db_count} SQLite DBs | {db_size_str}", 
            icon="Database"
        ),
        AdminNodeStatus(
            name="Bot Microservices", 
            status="Healthy" if bot.is_ready() else "Booting", 
            load=f"{loaded_cogs} Modules", 
            icon="Cpu"
        ),
        AdminNodeStatus(
            name="Auth Sockets", 
            status="Healthy", 
            load=f"Shard: {bot.shard_count} | Latency: {round(bot.latency * 1000)}ms", 
            icon="Lock"
        )
    ]

    total_members = sum(g.member_count or 0 for g in bot.guilds)

    return AdminStats(
        total_users=str(total_members),
        active_servers=str(len(bot.guilds)),
        api_latency=f"{round(bot.latency * 1000, 2)}ms",
        db_size=db_size_str,
        nodes=nodes
    )

@router.get("/config", response_model=AdminConfig)
async def get_admin_config():
    await init_db()
    async with aiosqlite.connect(CONFIG_DB) as db:
        async with db.execute("SELECT value FROM config WHERE key = 'maintenance_mode'") as cursor:
            mm = await cursor.fetchone()
        async with db.execute("SELECT value FROM config WHERE key = 'global_notification'") as cursor:
            gn = await cursor.fetchone()
            
    return AdminConfig(
        maintenance_mode=mm[0].lower() == 'true' if mm else False,
        global_notification=gn[0] if gn else None
    )

@router.patch("/config")
async def patch_admin_config(data: AdminConfigUpdate):
    await init_db()
    async with aiosqlite.connect(CONFIG_DB) as db:
        if data.maintenance_mode is not None:
            await db.execute("UPDATE config SET value = ? WHERE key = 'maintenance_mode'", (str(data.maintenance_mode).lower(),))
        if data.global_notification is not None:
            await db.execute("UPDATE config SET value = ? WHERE key = 'global_notification'", (data.global_notification,))
        await db.commit()

    # Maintenance mode is no longer just a stored value: switching it on also
    # freezes commands for everyone except the bot owners.
    if data.maintenance_mode is not None:
        await feature_flags.set_values({"global_command_freeze": bool(data.maintenance_mode)})
        await feature_audit.log_action(
            "maintenance_mode",
            actor="dashboard",
            detail="enabled" if data.maintenance_mode else "disabled",
        )

    if data.global_notification is not None:
        await feature_audit.record_notification(data.global_notification)

    return {"status": "success"}


@router.get("/notifications/history", summary="Global notification history")
async def get_notification_history(limit: int = 50):
    return {"history": await feature_audit.fetch_notification_history(limit)}

# ── Feature flags ─────────────────────────────────────────────────────────
# The flag registry, its metadata and all enforcement live in
# utils/feature_flags.py and the feature_* helper modules. These endpoints are
# a thin layer on top of it.

@router.get("/features", summary="Get feature flag values")
async def get_admin_features():
    """Flat key -> bool mapping (kept for backwards compatibility)."""
    return await feature_flags.load()


@router.get("/features/detail", summary="Get feature flags with metadata")
async def get_admin_features_detail():
    """Full metadata: category, description, effect, dependencies, rollout."""
    await feature_flags.load()
    return {
        "categories": list(feature_flags.CATEGORIES),
        "features": feature_flags.describe(),
    }


@router.patch("/features", summary="Update feature flags")
async def patch_admin_features(data: dict, bot: "universitybot" = Depends(get_bot)):
    changed = await feature_flags.set_values(data)

    for key, value in changed.items():
        await feature_audit.log_action(
            "feature_flag_changed",
            actor="dashboard",
            detail=f"{key} -> {'on' if value else 'off'}",
        )

    return {"status": "success", "changed": changed, **feature_flags.all_values()}


@router.patch("/features/{key}/rollout", summary="Set percentage rollout for a flag")
async def patch_feature_rollout(key: str, data: dict):
    if key not in feature_flags.FEATURE_DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown feature flag.")
    try:
        percent = int(data.get("percent", 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="percent must be a number between 0 and 100.")

    applied = await feature_flags.set_rollout(key, percent)
    await feature_audit.log_action(
        "feature_rollout_changed", actor="dashboard", detail=f"{key} -> {applied}%"
    )
    return {"status": "success", "key": key, "percent": applied}

@router.post("/member-action")
async def run_member_action(data: dict, bot: "universitybot" = Depends(get_bot)):
    """Run a reliable dashboard moderation action against a guild member/user."""
    import datetime
    import discord

    guild_id = str(data.get("guild_id", "")).strip()
    user_id = str(data.get("user_id", "")).strip()
    action = str(data.get("action", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()[:512]

    try:
        duration_minutes = int(data.get("duration_minutes", 60) or 60)
    except (TypeError, ValueError):
        duration_minutes = 60
    duration_minutes = max(1, min(duration_minutes, 40320))

    if not guild_id.isdigit() or not user_id.isdigit():
        raise HTTPException(status_code=400, detail="guild_id and user_id must be valid Discord IDs")
    if action not in {"ban", "kick", "mute", "unmute"}:
        raise HTTPException(status_code=400, detail="Unsupported action. Use ban, kick, mute, or unmute.")
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot is not in this guild")

    me = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
    if not me:
        raise HTTPException(status_code=503, detail="Bot member is not cached yet. Try again in a moment.")

    required_permission = {
        "ban": "ban_members",
        "kick": "kick_members",
        "mute": "moderate_members",
        "unmute": "moderate_members",
    }[action]
    if not getattr(me.guild_permissions, required_permission, False):
        raise HTTPException(status_code=403, detail=f"Bot is missing Discord permission: {required_permission}")

    member = guild.get_member(int(user_id))
    if member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except Exception:
            member = None

    if action in {"kick", "mute", "unmute"} and member is None:
        raise HTTPException(status_code=404, detail="Member not found in this guild")

    if member is not None:
        if member.id == guild.owner_id:
            raise HTTPException(status_code=403, detail="The server owner cannot be moderated")
        if member.id == me.id:
            raise HTTPException(status_code=403, detail="The bot cannot moderate itself")
        if member.top_role >= me.top_role and guild.owner_id != me.id:
            raise HTTPException(status_code=403, detail="Bot role is too low. Move the bot role above the target member's highest role")

    try:
        if action == "ban":
            if member is not None:
                await member.ban(reason=reason, delete_message_seconds=0)
            else:
                user = discord.Object(id=int(user_id))
                await guild.ban(user, reason=reason, delete_message_seconds=0)
            result = f"User {user_id} was banned from {guild.name}."
        elif action == "kick":
            await member.kick(reason=reason)
            result = f"User {user_id} was kicked from {guild.name}."
        elif action == "mute":
            until = discord.utils.utcnow() + datetime.timedelta(minutes=duration_minutes)
            await member.timeout(until, reason=reason)
            result = f"User {user_id} was muted for {duration_minutes} minutes in {guild.name}."
        else:  # unmute
            await member.timeout(None, reason=reason)
            result = f"User {user_id} was unmuted in {guild.name}."
    except TypeError:
        # Compatibility fallback for older discord.py variants.
        if action == "ban":
            await guild.ban(member or discord.Object(id=int(user_id)), reason=reason)
            result = f"User {user_id} was banned from {guild.name}."
        else:
            raise
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Bot is missing permissions or its role is too low for this action")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    return {"status": "success", "action": action, "guild_id": guild_id, "user_id": user_id, "result": result}

@router.post("/quick-action")
async def run_admin_quick_action(data: dict, bot: "universitybot" = Depends(get_bot)):
    """Run dashboard admin utility actions.

    This endpoint powers the simplified tab-based admin dashboard. It supports
    moderation helpers, role/channel/server tools, and read-only security scans.
    """
    import datetime
    import discord

    action = str(data.get("action", "")).strip().lower()
    guild_id = str(data.get("guild_id", "")).strip()
    reason = str(data.get("reason", "Dashboard admin action")).strip()[:512] or "Dashboard admin action"
    actor = str(data.get("actor", "dashboard")).strip()[:64] or "dashboard"

    if not guild_id.isdigit():
        raise HTTPException(status_code=400, detail="guild_id must be a valid Discord ID")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot is not in this guild")

    # Destructive actions can be routed through an approval queue instead of
    # executing straight away (admin_action_approval_queue / two_person_rule).
    if feature_audit.is_destructive(action) and feature_flags.is_enabled("admin_action_approval_queue"):
        if not data.get("approved_entry_id"):
            entry_id = await feature_audit.queue_action(
                action, data, requested_by=actor, guild_id=guild_id
            )
            await feature_audit.log_action(
                "action_queued", actor=actor, guild_id=guild_id, detail=f"{action} queued as #{entry_id}"
            )
            return {
                "status": "queued",
                "action": action,
                "guild_id": guild_id,
                "queue_id": entry_id,
                "result": f"Action '{action}' was queued for approval (#{entry_id}).",
            }

    def _id(name: str) -> int | None:
        value = str(data.get(name, "")).strip()
        return int(value) if value.isdigit() else None

    async def get_member(required: bool = True):
        user_id = _id("user_id")
        if not user_id:
            if required:
                raise HTTPException(status_code=400, detail="user_id is required")
            return None
        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                if required:
                    raise HTTPException(status_code=404, detail="Member not found in this guild")
                return None
        return member

    def get_channel(required: bool = True):
        channel_id = _id("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if required and not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return channel

    try:
        # Channel tools
        if action == "create_text_channel":
            name = str(data.get("name", "new-channel")).strip()[:100] or "new-channel"
            channel = await guild.create_text_channel(name=name, reason=reason)
            result = f"Created text channel #{channel.name}."
        elif action == "create_voice_channel":
            name = str(data.get("name", "New Voice")).strip()[:100] or "New Voice"
            channel = await guild.create_voice_channel(name=name, reason=reason)
            result = f"Created voice channel {channel.name}."
        elif action == "create_category":
            name = str(data.get("name", "New Category")).strip()[:100] or "New Category"
            category = await guild.create_category(name=name, reason=reason)
            result = f"Created category {category.name}."
        elif action == "rename_channel":
            channel = get_channel(); name = str(data.get("name", channel.name)).strip()[:100]
            await channel.edit(name=name, reason=reason)
            result = f"Renamed channel to {name}."
        elif action == "delete_channel":
            channel = get_channel(); name = channel.name
            await channel.delete(reason=reason)
            result = f"Deleted channel {name}."
        elif action == "clone_channel":
            channel = get_channel(); clone = await channel.clone(reason=reason)
            result = f"Cloned channel to {clone.name}."
        elif action == "lock_channel":
            channel = get_channel(); overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            result = f"Locked channel {channel.name}."
        elif action == "unlock_channel":
            channel = get_channel(); overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = None
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            result = f"Unlocked channel {channel.name}."
        elif action == "slowmode":
            channel = get_channel(); seconds = int(data.get("seconds", 5) or 5)
            await channel.edit(slowmode_delay=max(0, min(seconds, 21600)), reason=reason)
            result = f"Set slowmode in {channel.name} to {seconds}s."
        elif action == "purge":
            channel = get_channel(); amount = int(data.get("amount", 10) or 10)
            deleted = await channel.purge(limit=max(1, min(amount, 100)), reason=reason)
            result = f"Deleted {len(deleted)} messages in {channel.name}."

        # Server tools
        elif action == "server_name":
            name = str(data.get("name", guild.name)).strip()[:100]
            await guild.edit(name=name, reason=reason)
            result = f"Server renamed to {name}."
        elif action == "verification_level_low":
            await guild.edit(verification_level=discord.VerificationLevel.low, reason=reason)
            result = "Verification level set to low."
        elif action == "verification_level_medium":
            await guild.edit(verification_level=discord.VerificationLevel.medium, reason=reason)
            result = "Verification level set to medium."
        elif action == "default_notifications_mentions":
            await guild.edit(default_notifications=discord.NotificationLevel.only_mentions, reason=reason)
            result = "Default notifications set to only mentions."
        elif action == "default_notifications_all":
            await guild.edit(default_notifications=discord.NotificationLevel.all_messages, reason=reason)
            result = "Default notifications set to all messages."

        # Scans / reports
        elif action == "scan_admin_roles":
            roles = [r.name for r in guild.roles if r.permissions.administrator]
            result = f"Administrator roles ({len(roles)}): {', '.join(roles[:25]) or 'none'}"
        elif action == "scan_dangerous_roles":
            roles = [r.name for r in guild.roles if r.permissions.manage_roles or r.permissions.manage_channels or r.permissions.ban_members]
            result = f"Dangerous roles ({len(roles)}): {', '.join(roles[:25]) or 'none'}"
        elif action == "list_bots":
            bots = [m.display_name for m in guild.members if m.bot]
            result = f"Bots ({len(bots)}): {', '.join(bots[:30]) or 'none'}"
        elif action == "list_staff":
            staff = [m.display_name for m in guild.members if m.guild_permissions.manage_messages or m.guild_permissions.administrator]
            result = f"Staff-like members ({len(staff)}): {', '.join(staff[:30]) or 'none'}"
        elif action == "server_stats":
            result = f"{guild.name}: {guild.member_count or 0} members, {len(guild.roles)} roles, {len(guild.channels)} channels."
        elif action == "scan_public_channels":
            channels = [c.name for c in guild.text_channels if c.permissions_for(guild.default_role).view_channel]
            result = f"Public text channels ({len(channels)}): {', '.join(channels[:30]) or 'none'}"
        elif action == "scan_webhooks":
            count = 0
            names = []
            for channel in guild.text_channels[:50]:
                try:
                    hooks = await channel.webhooks()
                    count += len(hooks)
                    names.extend([f"{channel.name}:{hook.name}" for hook in hooks])
                except Exception:
                    pass
            result = f"Webhooks ({count}): {', '.join(names[:25]) or 'none'}"
        elif action == "scan_invites":
            try:
                invites = await guild.invites()
                result = f"Invites ({len(invites)}): {', '.join([i.code for i in invites[:30]]) or 'none'}"
            except discord.Forbidden:
                raise HTTPException(status_code=403, detail="Bot needs Manage Guild to view invites")
        elif action == "audit_summary":
            entries = []
            try:
                async for entry in guild.audit_logs(limit=10):
                    entries.append(f"{entry.action.name} by {entry.user}")
            except discord.Forbidden:
                raise HTTPException(status_code=403, detail="Bot needs View Audit Log")
            result = "Recent audit entries: " + (" | ".join(entries) if entries else "none")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported quick action: {action}")

    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Bot is missing permissions or its role is too low for this action")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid numeric/color value")

    await feature_audit.log_action(action, actor=actor, guild_id=guild_id, detail=result)

    return {"status": "success", "action": action, "guild_id": guild_id, "result": result}


# ══════════════════════════════════════════════════════════════════════════
#  Feature-flag backed endpoints
# ══════════════════════════════════════════════════════════════════════════


@router.get("/health", summary="Runtime health collected by the monitoring flags")
async def get_admin_health(bot: "universitybot" = Depends(get_bot)):
    """
    Aggregated output of shard_health_monitor, lavalink_health_monitor,
    discord_api_status_watch, database_integrity_scan, module_load_guard,
    session_cookie_monitor and railway_log_watch.
    """
    await feature_flags.load()
    snapshot = runtime.snapshot()

    # Whether the data survives a deploy. This is the one health fact
    # nobody notices until it is too late: everything works fine right
    # up to the next deploy, and then every server's settings are gone.
    from utils import storage
    persistence = storage.describe()

    return {
        "bot_ready": bot.is_ready(),
        "storage": {
            **persistence,
            "safe": persistence["persistent"] and persistence["mounted"],
            "hint": (
                "Alles in Ordnung — die Daten liegen auf einem Volume."
                if persistence["persistent"] and persistence["mounted"]
                else "DATA_DIR ist gesetzt, aber dort ist kein Volume "
                     "eingehängt. Die Daten sind beim nächsten Deploy weg."
                if persistence["persistent"]
                else "Kein Volume: Die Datenbanken liegen neben dem Code "
                     "und gehen bei jedem Deploy verloren."
            ),
        },
        "flags": {
            key: feature_flags.is_enabled(key)
            for key in (
                "shard_health_monitor", "lavalink_health_monitor", "music_node_failover",
                "discord_api_status_watch", "database_integrity_scan",
                "database_backup_scheduler", "orphan_data_cleanup",
                "module_load_guard", "cog_auto_recovery", "session_cookie_monitor",
                "railway_log_watch", "auto_restart_on_deadlock",
            )
        },
        **snapshot,
    }


@router.get("/logs", summary="Recent warnings and errors (railway_log_watch)")
async def get_admin_logs(limit: int = 100):
    if not feature_flags.is_enabled("railway_log_watch"):
        raise HTTPException(status_code=403, detail="Feature 'railway_log_watch' is disabled.")
    entries = list(runtime.log_buffer)[-max(1, min(limit, 200)):]
    return {"count": len(entries), "entries": list(reversed(entries))}


@router.get("/metrics", summary="API performance metrics")
async def get_admin_metrics():
    if not feature_flags.is_enabled("dashboard_performance_metrics"):
        raise HTTPException(status_code=403, detail="Feature 'dashboard_performance_metrics' is disabled.")
    return {
        "endpoints": {k: dict(v) for k, v in runtime.request_stats.items()},
        "slow_requests": list(runtime.slow_requests),
        "slow_query_detector": feature_flags.is_enabled("slow_query_detector"),
        "command_errors": dict(runtime.command_errors),
        "oauth_errors": runtime.oauth_errors,
    }


@router.get("/audit", summary="Cross-guild audit log")
async def get_admin_audit(limit: int = 100, suspicious_only: bool = False):
    if not feature_flags.is_enabled("cross_guild_audit_log"):
        raise HTTPException(status_code=403, detail="Feature 'cross_guild_audit_log' is disabled.")
    return {"entries": await feature_audit.fetch_audit(limit, suspicious_only)}


@router.get("/timeline", summary="Incident timeline")
async def get_admin_timeline(limit: int = 50):
    if not feature_flags.is_enabled("incident_timeline_builder"):
        raise HTTPException(status_code=403, detail="Feature 'incident_timeline_builder' is disabled.")
    return {"events": await feature_audit.build_timeline(limit)}


@router.get("/approvals", summary="Pending admin actions")
async def get_admin_approvals(status: str = "pending"):
    if not feature_flags.is_enabled("admin_action_approval_queue"):
        raise HTTPException(status_code=403, detail="Feature 'admin_action_approval_queue' is disabled.")
    return {"entries": await feature_audit.fetch_queue(status)}


@router.post("/approvals/{entry_id}", summary="Approve or reject a queued action")
async def resolve_admin_approval(entry_id: int, data: dict):
    if not feature_flags.is_enabled("admin_action_approval_queue"):
        raise HTTPException(status_code=403, detail="Feature 'admin_action_approval_queue' is disabled.")

    approver = str(data.get("approver", "")).strip()
    approve = bool(data.get("approve", False))
    if not approver:
        raise HTTPException(status_code=400, detail="approver is required")

    entries = await feature_audit.fetch_queue("pending", limit=200)
    entry = next((e for e in entries if int(e["id"]) == entry_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Queue entry not found or already resolved.")

    # The two person rule forbids approving your own request.
    if approve and feature_flags.is_enabled("two_person_rule"):
        if str(entry.get("requested_by", "")) == approver:
            raise HTTPException(
                status_code=403,
                detail="Two person rule: this action must be approved by a different admin.",
            )

    resolved = await feature_audit.resolve_queue_entry(entry_id, approver, approve)
    await feature_audit.log_action(
        "approval_resolved",
        actor=approver,
        guild_id=entry.get("guild_id", ""),
        detail=f"#{entry_id} {'approved' if approve else 'rejected'}",
    )
    return {"status": "success", "approved": approve, "entry": resolved}


@router.get("/reports/{name}", summary="Run an analytics report")
async def get_admin_report(name: str, bot: "universitybot" = Depends(get_bot)):
    """Analytics reports backed by the corresponding feature flags."""
    reports = {
        "security-score": lambda: feature_reports.security_score(bot),
        "automod-recommendations": lambda: feature_reports.automod_recommendations(bot),
        "staff-permissions": lambda: feature_reports.staff_permission_review(bot),
        "role-risk": lambda: feature_reports.role_risk_scan(bot),
        "channel-risk": lambda: feature_reports.channel_risk_scan(bot),
        "webhook-risk": lambda: feature_reports.webhook_risk_scan(bot),
        "ticket-load": lambda: feature_reports.ticket_load(bot),
        "invite-growth": lambda: feature_reports.invite_growth(bot),
        "member-retention": lambda: feature_reports.member_retention(bot),
        "voice-analytics": lambda: feature_reports.voice_analytics(),
    }

    runner = reports.get(name)
    if runner is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown report. Available: {', '.join(sorted(reports))}",
        )

    result = await runner()
    if not result.get("enabled", True):
        raise HTTPException(status_code=403, detail=result.get("reason", "Feature disabled."))
    return result


@router.get("/reports/{name}/export", summary="Export a report as JSON")
async def export_admin_report(name: str, bot: "universitybot" = Depends(get_bot)):
    if not feature_flags.is_enabled("export_admin_reports"):
        raise HTTPException(status_code=403, detail="Feature 'export_admin_reports' is disabled.")

    from fastapi.responses import JSONResponse

    payload = await get_admin_report(name, bot)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{name}-report.json"'},
    )


@router.post("/announcements", summary="Schedule a global announcement")
async def schedule_announcement(data: dict):
    if not feature_flags.is_enabled("global_announcement_scheduler"):
        raise HTTPException(status_code=403, detail="Feature 'global_announcement_scheduler' is disabled.")

    import time

    message = str(data.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        send_at = int(data.get("send_at", time.time()))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="send_at must be a unix timestamp")

    async with aiosqlite.connect(CONFIG_DB) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS scheduled_announcements ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " message TEXT NOT NULL,"
            " send_at INTEGER NOT NULL,"
            " sent_at INTEGER)"
        )
        cursor = await db.execute(
            "INSERT INTO scheduled_announcements (message, send_at) VALUES (?, ?)",
            (message[:1900], send_at),
        )
        await db.commit()
        announcement_id = cursor.lastrowid

    await feature_audit.log_action(
        "announcement_scheduled", actor="dashboard", detail=f"#{announcement_id} at {send_at}"
    )
    return {"status": "success", "id": announcement_id, "send_at": send_at}


@router.post("/mass-config", summary="Apply one setting to many guilds")
async def mass_config_push(data: dict, bot: "universitybot" = Depends(get_bot)):
    if not feature_flags.is_enabled("mass_config_push"):
        raise HTTPException(status_code=403, detail="Feature 'mass_config_push' is disabled.")

    setting = str(data.get("setting", "")).strip().lower()
    value = data.get("value")
    guild_ids = [str(g).strip() for g in data.get("guild_ids", []) if str(g).strip().isdigit()]

    if setting != "prefix":
        raise HTTPException(status_code=400, detail="Only 'prefix' is supported right now.")
    if not isinstance(value, str) or not 1 <= len(value) <= 10:
        raise HTTPException(status_code=400, detail="prefix must be 1-10 characters")

    targets = guild_ids or [str(g.id) for g in bot.guilds]

    from utils.Tools import updateConfig

    applied = 0
    for guild_id in targets:
        try:
            await updateConfig(int(guild_id), {"prefix": value})
            applied += 1
        except Exception:
            continue

    await feature_audit.log_action(
        "mass_config_push", actor="dashboard", detail=f"prefix={value} on {applied} guilds"
    )
    return {"status": "success", "applied": applied, "setting": setting, "value": value}


@router.post("/premium/{guild_id}", summary="Grant or revoke premium for a guild")
async def set_guild_premium(guild_id: int, data: dict):
    if not feature_flags.is_enabled("premium_access_control"):
        raise HTTPException(status_code=403, detail="Feature 'premium_access_control' is disabled.")

    import time

    grant = bool(data.get("premium", True))
    async with aiosqlite.connect(CONFIG_DB) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS premium_guilds ("
            " guild_id INTEGER PRIMARY KEY, granted_at INTEGER)"
        )
        if grant:
            await db.execute(
                "INSERT OR REPLACE INTO premium_guilds (guild_id, granted_at) VALUES (?, ?)",
                (guild_id, int(time.time())),
            )
        else:
            await db.execute("DELETE FROM premium_guilds WHERE guild_id = ?", (guild_id,))
        await db.commit()

    await feature_gates.refresh_premium_guilds()
    await feature_audit.log_action(
        "premium_changed", actor="dashboard", guild_id=guild_id, detail="granted" if grant else "revoked"
    )
    return {"status": "success", "guild_id": str(guild_id), "premium": grant}


@router.post("/blacklist/refresh", summary="Reload the global blacklist cache")
async def refresh_blacklist_cache():
    if not feature_flags.is_enabled("global_blacklist_sync"):
        raise HTTPException(status_code=403, detail="Feature 'global_blacklist_sync' is disabled.")
    await feature_gates.refresh_blacklist()
    return {
        "status": "success",
        "users": len(feature_gates._blacklist_users),
        "guilds": len(feature_gates._blacklist_guilds),
    }


@router.post("/oauth-error", summary="Report a dashboard OAuth failure")
async def report_oauth_error(data: dict):
    """Called by the dashboard so oauth_error_tracker can count failures."""
    from utils.feature_services import record_oauth_error

    record_oauth_error(str(data.get("detail", ""))[:200])
    return {"status": "recorded", "total": runtime.oauth_errors}


@router.get("/backups", summary="List database backups")
async def list_backups():
    """
    Backups live on Railway's ephemeral filesystem and are lost on redeploy.
    Downloading them is the only way to keep a copy.
    """
    import glob

    backup_dir = "db/backups"
    snapshots = []

    if os.path.isdir(backup_dir):
        for path in sorted(glob.glob(os.path.join(backup_dir, "*")), reverse=True):
            if not os.path.isdir(path):
                continue
            # Count the JSON config too, otherwise a snapshot looks smaller
            # than it is and the file count is misleading.
            files = [f for f in glob.glob(os.path.join(path, "*")) if os.path.isfile(f)]
            snapshots.append(
                {
                    "name": os.path.basename(path),
                    "created_at": int(os.path.getmtime(path)),
                    "file_count": len(files),
                    "size_bytes": sum(os.path.getsize(f) for f in files),
                }
            )

    live_size = 0
    live_count = 0
    if os.path.isdir("db"):
        for f in glob.glob("db/*.db"):
            live_size += os.path.getsize(f)
            live_count += 1

    from utils.feature_services import BACKUP_INTERVAL, BACKUP_KEEP

    return {
        "snapshots": snapshots,
        "live": {"file_count": live_count, "size_bytes": live_size},
        "scheduler_enabled": feature_flags.is_enabled("database_backup_scheduler"),
        "scheduler": {
            "interval_seconds": BACKUP_INTERVAL,
            "interval_hours": round(BACKUP_INTERVAL / 3600, 2),
            "keep": BACKUP_KEEP,
            "last_backup_at": int(runtime.last_backup_at or 0),
        },
        "warning": (
            "Railway's filesystem is ephemeral: every redeploy wipes these "
            "snapshots. Download anything you want to keep."
        ),
    }


async def _create_snapshot(prefix: str = "") -> dict:
    """
    Copy every live database into db/backups/<stamp>.

    Shared by the manual backup button and by the restore/import routes,
    which take a safety copy before overwriting anything.

    The copying itself lives in config_transfer.write_snapshot, which is
    also what the background scheduler calls. Two separate copies of
    "what belongs in a backup" is how the automatic one ended up
    skipping rr.db and j2c_data.db.
    """
    import time as _time

    from api.config_transfer import write_snapshot

    stamp = _time.strftime("%Y%m%d-%H%M%S")
    if prefix:
        stamp = f"{prefix}-{stamp}"

    target = os.path.join("db", "backups", stamp)
    copied, json_copied = await write_snapshot(target)

    return {"name": stamp, "file_count": copied, "json_count": json_copied}


@router.post("/backups", summary="Create a backup right now")
async def create_backup():
    result = await _create_snapshot()
    await feature_audit.log_action(
        "backup_created",
        actor="dashboard",
        detail=f"{result['name']}: {result['file_count']} databases",
    )
    return {"status": "success", **result}


@router.get("/backups/live/download", summary="Download the current databases")
async def download_live():
    import io
    import zipfile
    import glob

    from fastapi.responses import StreamingResponse

    from api.config_transfer import JSON_CONFIG_FILES, iter_database_files

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # Keep the real relative path so the archive mirrors the layout.
        for file_path in iter_database_files():
            archive.write(file_path, file_path)
        # The JSON config is part of a complete backup too.
        for name in JSON_CONFIG_FILES:
            if os.path.exists(name):
                archive.write(name, name)
    buffer.seek(0)

    import time as _time

    stamp = _time.strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="live-{stamp}.zip"'},
    )


@router.get("/backups/{name}/download", summary="Download a backup as a zip")
async def download_backup(name: str):
    import io
    import zipfile
    import glob

    from fastapi.responses import StreamingResponse

    # Reject anything that could escape the backup directory.
    if not name.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid backup name.")

    path = os.path.join("db", "backups", name)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail="Backup not found.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in glob.glob(os.path.join(path, "*")):
            if os.path.isfile(file_path):
                # JSON config was stored with "/" flattened to "__".
                archive.write(file_path, os.path.basename(file_path))
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="backup-{name}.zip"'},
    )


@router.delete("/backups/{name}", summary="Delete a backup")
async def delete_backup(name: str):
    import shutil

    if not name.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid backup name.")

    path = os.path.join("db", "backups", name)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail="Backup not found.")

    shutil.rmtree(path, ignore_errors=True)
    await feature_audit.log_action("backup_deleted", actor="dashboard", detail=name)
    return {"status": "success", "name": name}


# ══════════════════════════════════════════════════════════════════════════
#  Full backup — everything, every server, in one file
# ══════════════════════════════════════════════════════════════════════════


@router.get("/backups/export-all", summary="Download the complete configuration")
async def export_all_config(include_user_data: bool = False):
    """
    One JSON file containing EVERYTHING: every server's settings for every
    module, plus the global tables (dashboard team and roles, feature flags,
    bot settings, blacklist, premium, announcements).

    This replaces having to export each server separately.
    """
    from api.config_transfer import export_everything
    from fastapi.responses import StreamingResponse
    import json as _json
    import time as _time

    payload = await export_everything(include_user_data=include_user_data)

    stamp = _time.strftime("%Y%m%d-%H%M%S")
    filename = f"full-backup-{stamp}.json"

    await feature_audit.log_action(
        "full_backup_exported",
        actor="dashboard",
        detail=(
            f"{payload['summary']['guild_count']} guilds, "
            f"{payload['summary']['row_count']} rows"
        ),
    )

    def _chunks():
        # JSONResponse serialises into one bytes object and holds both the
        # dict and the encoded copy in memory. Streaming in slices keeps the
        # peak far lower, so an export stays possible on a small container
        # no matter how large the installation gets.
        encoder = _json.JSONEncoder(ensure_ascii=False)
        for piece in encoder.iterencode(payload):
            yield piece.encode("utf-8")

    return StreamingResponse(
        _chunks(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backups/preview-all", summary="Check a full backup before importing")
async def preview_all_config(data: dict):
    """Validate an uploaded backup and describe what it would change."""
    from api.config_transfer import preview_global_import

    payload = data.get("config") if isinstance(data.get("config"), dict) else data
    try:
        return await preview_global_import(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/backups/import-all", summary="Restore a complete backup")
async def import_all_config(data: dict):
    """
    Write a full backup back into the databases.

    merge=true keeps existing rows and adds the file's on top; the default
    replaces the contents of every imported table.
    include_global=false leaves the dashboard team, feature flags and bot
    settings alone and restores only the per-server configuration.
    """
    from api.config_transfer import import_everything

    payload = data.get("config") if isinstance(data.get("config"), dict) else data
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="No configuration supplied.")

    replace = not bool(data.get("merge", False))
    include_global = bool(data.get("include_global", True))

    # A restore overwrites live data, so keep a safety copy first.
    safety = None
    try:
        safety = await _create_snapshot(prefix="pre-import")
    except Exception as exc:
        print(f"[admin] safety backup before import failed: {exc}")

    try:
        result = await import_everything(
            payload, replace=replace, include_global=include_global
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Caches hold the old values until they are told otherwise.
    try:
        await feature_flags.load()
        feature_gates.invalidate_blacklist()
        await feature_gates.refresh_blacklist()
        await feature_gates.refresh_premium_guilds()
        await bot_settings.load()
        from utils import dashboard_roles, dashboard_access

        await dashboard_roles.load()
        await dashboard_access.load()
    except Exception as exc:
        print(f"[admin] cache refresh after import failed: {exc}")

    result["safety_backup"] = safety

    # The settings come back from the file, but the panel messages live in
    # Discord and their stored message ids point at messages that no longer
    # work after a redeploy. Repost them so the buttons are alive again
    # without anyone re-running the setup commands.
    if bool(data.get("repost_panels", True)):
        try:
            from api.panel_restore import repost_all_panels

            bot = get_bot()
            result["panels"] = await repost_all_panels(bot)
        except HTTPException:
            result["panels"] = {"error": "bot not ready, panels not reposted"}
        except Exception as exc:  # noqa: BLE001
            result["panels"] = {"error": str(exc)[:200]}

    await feature_audit.log_action(
        "full_backup_imported",
        actor="dashboard",
        detail=f"{result['rows_written']} rows into {result['tables_written']} tables",
    )
    return {"status": "success", **result}


@router.post("/backups/{name}/restore", summary="Restore a stored snapshot")
async def restore_backup(name: str):
    """
    Copy a snapshot from db/backups/<name> back over the live databases.

    The current state is saved as a "pre-restore" snapshot first, so this
    can be undone.
    """
    import glob
    import shutil

    if not name.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid backup name.")

    source_dir = os.path.join("db", "backups", name)
    if not os.path.isdir(source_dir):
        raise HTTPException(status_code=404, detail="Backup not found.")

    files = glob.glob(os.path.join(source_dir, "*.db"))
    if not files:
        raise HTTPException(status_code=400, detail="That snapshot has no databases.")

    safety = None
    try:
        safety = await _create_snapshot(prefix="pre-restore")
    except Exception as exc:
        print(f"[admin] safety backup before restore failed: {exc}")

    from api.config_transfer import db_path_from_key

    restored = 0
    failed: list[str] = []
    for path in files:
        # Databases outside db/ are stored with their path flattened.
        target = db_path_from_key(os.path.basename(path))
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        try:
            # sqlite's backup API writes a consistent copy even while the
            # bot keeps using the destination file.
            async with aiosqlite.connect(path) as source:
                async with aiosqlite.connect(target) as destination:
                    await source.backup(destination)
            restored += 1
        except Exception:
            try:
                shutil.copy2(path, target)
                restored += 1
            except Exception as exc:
                failed.append(f"{os.path.basename(path)} ({exc})")

    # Snapshots store the JSON config with "/" flattened to "__".
    from api.config_transfer import JSON_CONFIG_FILES

    json_restored = 0
    for name in JSON_CONFIG_FILES:
        stored = os.path.join(source_dir, name.replace("/", "__"))
        if not os.path.exists(stored):
            continue
        try:
            os.makedirs(os.path.dirname(name) or ".", exist_ok=True)
            shutil.copy2(stored, name)
            json_restored += 1
        except Exception as exc:
            failed.append(f"{name} ({exc})")

    try:
        await feature_flags.load()
        feature_gates.invalidate_blacklist()
        await feature_gates.refresh_blacklist()
        await feature_gates.refresh_premium_guilds()
        await bot_settings.load()
        from utils import dashboard_roles, dashboard_access

        await dashboard_roles.load()
        await dashboard_access.load()
    except Exception as exc:
        print(f"[admin] cache refresh after restore failed: {exc}")

    # Same reasoning as the import route: the panel messages themselves are
    # not part of a snapshot, only the configuration describing them.
    panels = None
    try:
        from api.panel_restore import repost_all_panels

        panels = await repost_all_panels(get_bot())
    except HTTPException:
        panels = {"error": "bot not ready, panels not reposted"}
    except Exception as exc:  # noqa: BLE001
        panels = {"error": str(exc)[:200]}

    await feature_audit.log_action(
        "backup_restored", actor="dashboard", detail=f"{name}: {restored} databases"
    )
    return {
        "status": "success",
        "name": name,
        "restored": restored,
        "json_restored": json_restored,
        "failed": failed,
        "safety_backup": safety,
        "panels": panels,
    }


@router.get("/settings", summary="Bot-wide settings")
async def get_bot_settings():
    """Settings that used to be hardcoded in university_bot.py."""
    await bot_settings.load()
    return {
        "groups": list(bot_settings.SETTING_GROUPS),
        "settings": bot_settings.describe(),
    }


@router.patch("/settings", summary="Update bot-wide settings")
async def patch_bot_settings(data: dict):
    payload = {k: v for k, v in data.items() if k != "actor"}
    changed = await bot_settings.set_values(payload)

    if changed:
        await feature_audit.log_action(
            "bot_settings_changed",
            actor=str(data.get("actor", "dashboard")),
            detail=", ".join(f"{k}={v}" for k, v in changed.items())[:400],
        )

    return {"status": "success", "changed": changed}


@router.get("/session-policy", summary="Session validity policy")
async def get_session_policy():
    """
    Used by the dashboard to honour force_dashboard_reauth: sessions issued
    before `reauth_epoch` must be rejected.
    """
    await feature_flags.load()
    return {
        "force_reauth": feature_flags.is_enabled("force_dashboard_reauth"),
        "reauth_epoch": feature_flags.reauth_epoch(),
        "maintenance_banner": feature_flags.is_enabled("maintenance_banner"),
    }


@router.get("/command-stats", summary="Which commands are actually used")
async def get_command_stats(
    days: int = 30,
    guild_id: int = 0,
    actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    """
    Usage counts per command. The bot had no visibility into this at all.

    Seit dieser Runde darf jede Dashboard-Rolle die Statistik lesen --
    vorher haengt der Reiter an `metrics.view`, und die hatten sechs von
    einundvierzig Rollen.

    Eine Angabe darin ist aber nicht fuer jeden bestimmt: die Liste der
    meistgenutzten Server nennt die Namen *jedes* Servers, auf dem der
    Bot ist. Das ist Kundschaft, keine Betriebszahl. Fuer alle ausser
    Ownern und Admins werden Name und Bild deshalb maskiert; die
    Zaehlerstaende bleiben stehen, denn genau um die geht es.

    Maskiert wird hier und nicht im Browser. Was der Server ausliefert,
    steht in den Entwicklerwerkzeugen -- eine Sperre, die nur die
    Anzeige ausblendet, ist keine.
    """
    from utils import command_stats
    from utils import dashboard_roles

    data = await command_stats.summary(guild_id or None, days)

    # Darf der Anfragende die Servernamen sehen?
    #
    # Im Zweifel nein: ohne `actor` -- etwa bei einem direkten Aufruf
    # mit dem API-Schluessel ohne Sitzung -- wird maskiert. Lieber ein
    # Sternchen zu viel als ein Servername zu viel.
    try:
        await dashboard_roles.load()
    except Exception:
        pass
    may_see_guilds = bool(actor) and dashboard_roles.is_owner(str(actor))

    # Enrich with the guild names so the dashboard shows more than IDs.
    for entry in data.get("guilds", []):
        guild = bot.get_guild(int(entry["guild_id"])) if entry["guild_id"].isdigit() else None

        if may_see_guilds:
            entry["guild_name"] = guild.name if guild else None
            entry["guild_icon"] = (
                str(guild.icon.url) if guild is not None and guild.icon else None
            )
            continue

        # Die ID muss genauso weg wie der Name: mit ihr laesst sich der
        # Server ueber die Discord-API nachschlagen, und dann waere die
        # Maskierung eine reine Geste.
        entry["guild_id"] = ""
        entry["guild_name"] = "•••••"
        entry["guild_icon"] = None
        entry["masked"] = True

    data["guilds_masked"] = not may_see_guilds

    try:
        data["unused"] = await command_stats.unused_commands(bot, days)
    except Exception:
        data["unused"] = []

    # Prefix *und* Slash. `walk_commands()` allein kennt nur die
    # Prefix-Befehle, und die Statistik verglich die Nutzung dann gegen
    # eine Gesamtzahl, in der die Slash-Befehle fehlten.
    data["registered_commands"] = len(command_stats.all_command_names(bot))
    return data
