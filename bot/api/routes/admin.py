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
