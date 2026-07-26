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
    return {"status": "success"}

ADMIN_FEATURE_DEFAULTS = {
    "global_emergency_lockdown": False,
    "maintenance_banner": True,
    "force_dashboard_reauth": False,
    "global_command_freeze": False,
    "owner_only_mode": False,
    "cross_guild_audit_log": True,
    "global_blacklist_sync": True,
    "premium_access_control": True,
    "api_rate_limit_boost": True,
    "database_backup_scheduler": True,
    "database_integrity_scan": True,
    "orphan_data_cleanup": False,
    "cache_warmup": True,
    "shard_health_monitor": True,
    "lavalink_health_monitor": True,
    "music_node_failover": True,
    "discord_api_status_watch": True,
    "oauth_error_tracker": True,
    "session_cookie_monitor": True,
    "dashboard_performance_metrics": True,
    "slow_query_detector": False,
    "command_error_analytics": True,
    "module_load_guard": True,
    "cog_auto_recovery": True,
    "guild_join_guard": True,
    "guild_leave_audit": True,
    "suspicious_owner_action_alerts": True,
    "mass_config_push": False,
    "feature_flag_rollouts": True,
    "beta_module_access": False,
    "premium_template_manager": False,
    "global_announcement_scheduler": True,
    "staff_permission_review": True,
    "security_score_calculation": True,
    "automod_rule_recommendations": True,
    "ticket_load_balancer": True,
    "voice_session_analytics": False,
    "invite_growth_analytics": True,
    "member_retention_insights": True,
    "webhook_risk_scanner": True,
    "role_risk_scanner": True,
    "channel_risk_scanner": True,
    "export_admin_reports": True,
    "incident_timeline_builder": True,
    "global_notification_history": True,
    "admin_action_approval_queue": False,
    "two_person_rule": False,
    "deployment_health_gate": True,
    "railway_log_watch": True,
    "auto_restart_on_deadlock": True,
}

async def _ensure_admin_features_table():
    async with aiosqlite.connect(CONFIG_DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS admin_features (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for key, value in ADMIN_FEATURE_DEFAULTS.items():
            await db.execute("INSERT OR IGNORE INTO admin_features (key, value) VALUES (?, ?)", (key, str(value).lower()))
        await db.commit()

@router.get("/features")
async def get_admin_features():
    await _ensure_admin_features_table()
    async with aiosqlite.connect(CONFIG_DB) as db:
        async with db.execute("SELECT key, value FROM admin_features") as cursor:
            rows = await cursor.fetchall()
    values = {key: value.lower() == "true" for key, value in rows}
    return {**ADMIN_FEATURE_DEFAULTS, **values}

@router.patch("/features")
async def patch_admin_features(data: dict):
    await _ensure_admin_features_table()
    clean = {key: bool(value) for key, value in data.items() if key in ADMIN_FEATURE_DEFAULTS}
    async with aiosqlite.connect(CONFIG_DB) as db:
        for key, value in clean.items():
            await db.execute("INSERT OR REPLACE INTO admin_features (key, value) VALUES (?, ?)", (key, str(value).lower()))
        await db.commit()
    return {"status": "success", **clean}

@router.post("/member-action")
async def run_member_action(data: dict, bot: "universitybot" = Depends(get_bot)):
    """Run a dashboard moderation action against a guild member."""
    import datetime
    import discord

    guild_id = str(data.get("guild_id", "")).strip()
    user_id = str(data.get("user_id", "")).strip()
    action = str(data.get("action", "")).strip().lower()
    reason = str(data.get("reason", "Dashboard moderation action")).strip()[:512] or "Dashboard moderation action"
    duration_minutes = int(data.get("duration_minutes", 60) or 60)

    if not guild_id.isdigit() or not user_id.isdigit():
        raise HTTPException(status_code=400, detail="guild_id and user_id must be valid Discord IDs")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot is not in this guild")

    member = guild.get_member(int(user_id))
    if action in {"kick", "mute", "unmute"} and member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except Exception:
            raise HTTPException(status_code=404, detail="Member not found in this guild")

    try:
        if action == "ban":
            target = member or discord.Object(id=int(user_id))
            await guild.ban(target, reason=reason, delete_message_days=0)
            result = f"User {user_id} was banned from {guild.name}."
        elif action == "kick":
            await member.kick(reason=reason)
            result = f"User {user_id} was kicked from {guild.name}."
        elif action == "mute":
            until = discord.utils.utcnow() + datetime.timedelta(minutes=max(1, min(duration_minutes, 40320)))
            await member.timeout(until, reason=reason)
            result = f"User {user_id} was muted for {duration_minutes} minutes in {guild.name}."
        elif action == "unmute":
            await member.timeout(None, reason=reason)
            result = f"User {user_id} was unmuted in {guild.name}."
        else:
            raise HTTPException(status_code=400, detail="Unsupported action. Use ban, kick, mute, or unmute.")
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

    if not guild_id.isdigit():
        raise HTTPException(status_code=400, detail="guild_id must be a valid Discord ID")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot is not in this guild")

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

    return {"status": "success", "action": action, "guild_id": guild_id, "result": result}
