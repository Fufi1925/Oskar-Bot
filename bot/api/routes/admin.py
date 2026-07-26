# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
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

    def get_role(required: bool = True):
        role_id = _id("role_id")
        role = guild.get_role(role_id) if role_id else None
        if required and not role:
            raise HTTPException(status_code=404, detail="Role not found")
        return role

    def get_channel(required: bool = True):
        channel_id = _id("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if required and not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return channel

    try:
        # Member tools
        if action == "nickname":
            member = await get_member()
            nick = str(data.get("nickname", "")).strip()[:32] or None
            await member.edit(nick=nick, reason=reason)
            result = f"Nickname updated for {member}."
        elif action == "add_role":
            member = await get_member(); role = get_role()
            await member.add_roles(role, reason=reason)
            result = f"Added role {role.name} to {member}."
        elif action == "remove_role":
            member = await get_member(); role = get_role()
            await member.remove_roles(role, reason=reason)
            result = f"Removed role {role.name} from {member}."
        elif action == "member_info":
            member = await get_member()
            result = f"{member} | Joined: {member.joined_at} | Roles: {len(member.roles)} | Bot: {member.bot}"
        elif action == "clear_nickname":
            member = await get_member()
            await member.edit(nick=None, reason=reason)
            result = f"Nickname cleared for {member}."

        # Role tools
        elif action == "create_role":
            name = str(data.get("name", "New Role")).strip()[:100] or "New Role"
            color_raw = str(data.get("color", "3b82f6")).replace("#", "").strip()
            color = int(color_raw, 16) if color_raw else 0x3B82F6
            role = await guild.create_role(name=name, color=discord.Color(color), reason=reason)
            result = f"Created role {role.name}."
        elif action == "delete_role":
            role = get_role()
            await role.delete(reason=reason)
            result = f"Deleted role {role.name}."
        elif action == "rename_role":
            role = get_role(); name = str(data.get("name", role.name)).strip()[:100]
            await role.edit(name=name, reason=reason)
            result = f"Renamed role to {name}."
        elif action == "color_role":
            role = get_role(); color_raw = str(data.get("color", "3b82f6")).replace("#", "").strip()
            await role.edit(color=discord.Color(int(color_raw, 16)), reason=reason)
            result = f"Updated color for {role.name}."
        elif action == "toggle_role_hoist":
            role = get_role()
            await role.edit(hoist=not role.hoist, reason=reason)
            result = f"Role hoist is now {'enabled' if not role.hoist else 'disabled'} for {role.name}."
        elif action == "toggle_role_mentionable":
            role = get_role()
            await role.edit(mentionable=not role.mentionable, reason=reason)
            result = f"Role mentionable toggled for {role.name}."

        # Channel tools
        elif action == "create_text_channel":
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

    return {
        "bot_ready": bot.is_ready(),
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
