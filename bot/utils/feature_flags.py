"""
Global admin feature flags.

These flags used to be a decorative list: the dashboard could toggle them, the
values were stored, and nothing ever read them. This module turns them into a
real registry with:

  * metadata (category, label, description, what it actually does)
  * a cached accessor so hot paths can check a flag without touching SQLite
  * change notifications so services can start/stop when a flag is toggled

Enforcement lives close to the thing being controlled:
  * command gates          → utils/feature_gates.py  (bot-wide check)
  * background monitors    → utils/feature_services.py
  * event driven auditing  → cogs/events/feature_enforcement.py
  * analytics & reports    → utils/feature_reports.py
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import aiosqlite

CONFIG_DB = "db/admin_config.db"


# ── Registry ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeatureFlag:
    key: str
    label: str
    category: str
    description: str
    default: bool
    # Short note describing the concrete effect, surfaced in the dashboard.
    effect: str
    # Flags that only make sense together with another one.
    requires: tuple[str, ...] = field(default_factory=tuple)


CATEGORY_SAFETY = "Safety & Access"
CATEGORY_DATA = "Data & Storage"
CATEGORY_HEALTH = "Health & Monitoring"
CATEGORY_MODULES = "Modules & Recovery"
CATEGORY_GUILDS = "Guild Oversight"
CATEGORY_ROLLOUT = "Rollout & Announcements"
CATEGORY_ANALYTICS = "Analytics & Reports"
CATEGORY_WORKFLOW = "Admin Workflow"
CATEGORY_DEPLOY = "Deployment"

FEATURE_FLAGS: tuple[FeatureFlag, ...] = (
    # ── Safety & Access ───────────────────────────────────────────────────
    FeatureFlag(
        "global_emergency_lockdown", "Global Emergency Lockdown", CATEGORY_SAFETY,
        "Blocks every command in every guild except for bot owners.",
        False, "Rejects all non-owner command invocations bot-wide.",
    ),
    FeatureFlag(
        "global_command_freeze", "Global Command Freeze", CATEGORY_SAFETY,
        "Temporarily stops all non-owner commands while keeping listeners alive.",
        False, "Rejects command invocations; antinuke/automod keep running.",
    ),
    FeatureFlag(
        "owner_only_mode", "Owner Only Mode", CATEGORY_SAFETY,
        "Only bot owners may use commands. Useful while debugging in production.",
        False, "Rejects command invocations from everyone except OWNER_IDS.",
    ),
    FeatureFlag(
        "maintenance_banner", "Maintenance Banner", CATEGORY_SAFETY,
        "Shows the maintenance notice in the dashboard when maintenance mode is on.",
        True, "Dashboard renders the maintenance banner.",
    ),
    FeatureFlag(
        "force_dashboard_reauth", "Force Dashboard Re-Auth", CATEGORY_SAFETY,
        "Invalidates dashboard sessions issued before the flag was switched on.",
        False, "Sessions older than the activation timestamp are rejected.",
    ),
    FeatureFlag(
        "global_blacklist_sync", "Global Blacklist Sync", CATEGORY_SAFETY,
        "Applies the global user/guild blacklist to every command invocation.",
        True, "Blacklisted users and guilds cannot run commands.",
    ),
    FeatureFlag(
        "premium_access_control", "Premium Access Control", CATEGORY_SAFETY,
        "Restricts commands marked as premium to premium guilds.",
        True, "Premium-only commands check the premium guild list.",
    ),
    FeatureFlag(
        "two_person_rule", "Two Person Rule", CATEGORY_WORKFLOW,
        "Destructive admin actions need approval from a second admin.",
        False, "Queues destructive dashboard actions for a second approver.",
        requires=("admin_action_approval_queue",),
    ),
    FeatureFlag(
        "admin_action_approval_queue", "Admin Action Approval Queue", CATEGORY_WORKFLOW,
        "Records admin actions in a queue instead of running them immediately.",
        False, "Destructive quick-actions are queued for approval.",
    ),

    # ── Data & Storage ────────────────────────────────────────────────────
    FeatureFlag(
        "database_backup_scheduler", "Database Backup Scheduler", CATEGORY_DATA,
        "Creates periodic snapshots of every SQLite database.",
        True, "Copies every database into db/backups once a day. Keeps the "
              "newest one; the old one is deleted only after the new one "
              "has been read back and verified.",
    ),
    FeatureFlag(
        "database_integrity_scan", "Database Integrity Scan", CATEGORY_DATA,
        "Runs PRAGMA integrity_check against all databases.",
        True, "Hourly integrity check; failures appear in the health report.",
    ),
    FeatureFlag(
        "orphan_data_cleanup", "Orphan Data Cleanup", CATEGORY_DATA,
        "Removes configuration rows for guilds the bot has left.",
        False, "Daily sweep deleting rows whose guild_id is no longer joined.",
    ),
    FeatureFlag(
        "cache_warmup", "Cache Warmup", CATEGORY_DATA,
        "Preloads prefixes and no-prefix tables after startup.",
        True, "Warms the prefix/no-prefix caches once the bot is ready.",
    ),
    FeatureFlag(
        "slow_query_detector", "Slow Query Detector", CATEGORY_DATA,
        "Logs API requests that take longer than the threshold.",
        False, "Requests slower than 1000 ms are recorded.",
    ),

    # ── Health & Monitoring ───────────────────────────────────────────────
    FeatureFlag(
        "shard_health_monitor", "Shard Health Monitor", CATEGORY_HEALTH,
        "Tracks gateway latency and reconnects per shard.",
        True, "Samples shard latency every minute for the health report.",
    ),
    FeatureFlag(
        "lavalink_health_monitor", "Lavalink Health Monitor", CATEGORY_HEALTH,
        "Checks whether the music nodes are still connected.",
        True, "Samples Lavalink node status every minute.",
    ),
    FeatureFlag(
        "music_node_failover", "Music Node Failover", CATEGORY_HEALTH,
        "Reconnects Lavalink automatically when all nodes are down.",
        True, "Triggers a node reconnect when no node is reachable.",
        requires=("lavalink_health_monitor",),
    ),
    FeatureFlag(
        "discord_api_status_watch", "Discord API Status Watch", CATEGORY_HEALTH,
        "Polls the Discord status page for incidents.",
        True, "Fetches discordstatus.com every 5 minutes.",
    ),
    FeatureFlag(
        "oauth_error_tracker", "OAuth Error Tracker", CATEGORY_HEALTH,
        "Counts failed dashboard logins.",
        True, "Records OAuth failures reported by the dashboard.",
    ),
    FeatureFlag(
        "session_cookie_monitor", "Session Cookie Monitor", CATEGORY_HEALTH,
        "Warns when NEXTAUTH_SECRET is unstable across restarts.",
        True, "Checks that a stable session secret is configured.",
    ),
    FeatureFlag(
        "dashboard_performance_metrics", "Dashboard Performance Metrics", CATEGORY_HEALTH,
        "Collects request duration statistics for the API.",
        True, "Aggregates count/avg/p95 per endpoint.",
    ),
    FeatureFlag(
        "auto_restart_on_deadlock", "Auto Restart On Deadlock", CATEGORY_HEALTH,
        "Restarts the process when the event loop stops responding.",
        True, "Exits with code 1 after 90 s without a heartbeat so Railway restarts it.",
    ),

    # ── Modules & Recovery ────────────────────────────────────────────────
    FeatureFlag(
        "module_load_guard", "Module Load Guard", CATEGORY_MODULES,
        "Reports cogs that failed to load at startup.",
        True, "Compares loaded cogs against the expected list.",
    ),
    FeatureFlag(
        "cog_auto_recovery", "Cog Auto Recovery", CATEGORY_MODULES,
        "Reloads extensions that crashed during startup.",
        True, "Retries failed extensions every 10 minutes.",
        requires=("module_load_guard",),
    ),
    FeatureFlag(
        "command_error_analytics", "Command Error Analytics", CATEGORY_MODULES,
        "Aggregates command errors by type and command name.",
        True, "Counts errors from on_command_error for the reports view.",
    ),
    FeatureFlag(
        "beta_module_access", "Beta Module Access", CATEGORY_ROLLOUT,
        "Enables commands marked as beta for everyone.",
        False, "Beta-only commands become available outside the allowlist.",
    ),

    # ── Guild Oversight ───────────────────────────────────────────────────
    FeatureFlag(
        "guild_join_guard", "Guild Join Guard", CATEGORY_GUILDS,
        "Leaves servers that look like bot farms or are blacklisted.",
        True, "On join: leaves blacklisted guilds and >80% bot guilds.",
    ),
    FeatureFlag(
        "guild_leave_audit", "Guild Leave Audit", CATEGORY_GUILDS,
        "Records when the bot is removed from a server.",
        True, "Writes a row to the audit log on guild removal.",
    ),
    FeatureFlag(
        "cross_guild_audit_log", "Cross Guild Audit Log", CATEGORY_GUILDS,
        "Central log of admin actions across every guild.",
        True, "Dashboard admin actions are written to admin_audit_log.",
    ),
    FeatureFlag(
        "suspicious_owner_action_alerts", "Suspicious Owner Action Alerts", CATEGORY_GUILDS,
        "Flags risky owner actions such as mass bans or role deletions.",
        True, "Marks matching audit entries as suspicious.",
        requires=("cross_guild_audit_log",),
    ),
    FeatureFlag(
        "staff_permission_review", "Staff Permission Review", CATEGORY_ANALYTICS,
        "Finds members with dangerous permissions.",
        True, "Report lists administrator/manage-guild members per guild.",
    ),

    # ── Rollout & Announcements ───────────────────────────────────────────
    FeatureFlag(
        "feature_flag_rollouts", "Feature Flag Rollouts", CATEGORY_ROLLOUT,
        "Allows enabling flags for a percentage of guilds instead of all.",
        True, "Percentage rollouts are honoured by is_enabled_for_guild().",
    ),
    FeatureFlag(
        "mass_config_push", "Mass Config Push", CATEGORY_ROLLOUT,
        "Allows applying one configuration to many guilds at once.",
        False, "Unlocks the bulk apply endpoint.",
    ),
    FeatureFlag(
        "global_announcement_scheduler", "Global Announcement Scheduler", CATEGORY_ROLLOUT,
        "Delivers scheduled announcements to guild system channels.",
        True, "Checks the announcement queue every minute.",
    ),
    FeatureFlag(
        "global_notification_history", "Global Notification History", CATEGORY_ROLLOUT,
        "Keeps a history of every global notification that was set.",
        True, "Stores each notification change with a timestamp.",
    ),
    FeatureFlag(
        "premium_template_manager", "Premium Template Manager", CATEGORY_ROLLOUT,
        "Enables the premium server template commands.",
        False, "Template commands become available.",
    ),

    # ── Analytics & Reports ───────────────────────────────────────────────
    FeatureFlag(
        "security_score_calculation", "Security Score Calculation", CATEGORY_ANALYTICS,
        "Computes a 0-100 security score per guild.",
        True, "Report scores antinuke, automod, verification and 2FA.",
    ),
    FeatureFlag(
        "automod_rule_recommendations", "Automod Rule Recommendations", CATEGORY_ANALYTICS,
        "Suggests automod rules that are not enabled yet.",
        True, "Report lists disabled automod modules.",
    ),
    FeatureFlag(
        "ticket_load_balancer", "Ticket Load Balancer", CATEGORY_ANALYTICS,
        "Shows how open tickets are distributed across staff.",
        True, "Report groups open tickets per claimer.",
    ),
    FeatureFlag(
        "voice_session_analytics", "Voice Session Analytics", CATEGORY_ANALYTICS,
        "Tracks voice channel join/leave durations.",
        False, "Records voice session lengths per guild.",
    ),
    FeatureFlag(
        "invite_growth_analytics", "Invite Growth Analytics", CATEGORY_ANALYTICS,
        "Summarises invite performance per guild.",
        True, "Report aggregates the invite tracking tables.",
    ),
    FeatureFlag(
        "member_retention_insights", "Member Retention Insights", CATEGORY_ANALYTICS,
        "Estimates how many invited members stayed.",
        True, "Report computes retention from invite totals versus leaves.",
    ),
    FeatureFlag(
        "webhook_risk_scanner", "Webhook Risk Scanner", CATEGORY_ANALYTICS,
        "Counts webhooks per guild and flags unusual amounts.",
        True, "Report lists guilds above the webhook threshold.",
    ),
    FeatureFlag(
        "role_risk_scanner", "Role Risk Scanner", CATEGORY_ANALYTICS,
        "Finds roles with dangerous permissions.",
        True, "Report lists administrator and manage-role roles.",
    ),
    FeatureFlag(
        "channel_risk_scanner", "Channel Risk Scanner", CATEGORY_ANALYTICS,
        "Finds channels @everyone can write in.",
        True, "Report lists world-writable channels.",
    ),
    FeatureFlag(
        "export_admin_reports", "Export Admin Reports", CATEGORY_ANALYTICS,
        "Allows downloading reports as JSON.",
        True, "Enables the report export endpoint.",
    ),
    FeatureFlag(
        "incident_timeline_builder", "Incident Timeline Builder", CATEGORY_ANALYTICS,
        "Builds a chronological timeline from the audit log.",
        True, "Merges audit entries and health events into a timeline.",
        requires=("cross_guild_audit_log",),
    ),

    # ── Deployment ────────────────────────────────────────────────────────
    FeatureFlag(
        "api_rate_limit_boost", "API Rate Limit Boost", CATEGORY_DEPLOY,
        "Raises the API rate limit for authenticated dashboard traffic.",
        True, "Applies the higher limit tier to /api/v1.",
    ),
    FeatureFlag(
        "deployment_health_gate", "Deployment Health Gate", CATEGORY_DEPLOY,
        "Makes /health fail while the bot is not fully ready.",
        True, "/health returns 503 until the bot is connected.",
    ),
    FeatureFlag(
        "railway_log_watch", "Railway Log Watch", CATEGORY_DEPLOY,
        "Captures warnings and errors into a ring buffer for the dashboard.",
        True, "Keeps the last 200 warning/error log records.",
    ),
)

FEATURES_BY_KEY: dict[str, FeatureFlag] = {flag.key: flag for flag in FEATURE_FLAGS}
FEATURE_DEFAULTS: dict[str, bool] = {flag.key: flag.default for flag in FEATURE_FLAGS}
CATEGORIES: tuple[str, ...] = tuple(dict.fromkeys(flag.category for flag in FEATURE_FLAGS))


# ── State ─────────────────────────────────────────────────────────────────

_values: dict[str, bool] = dict(FEATURE_DEFAULTS)
_rollouts: dict[str, int] = {}      # key -> percentage 0..100
_loaded = False
_lock = asyncio.Lock()
_listeners: list[Callable[[str, bool], Awaitable[None] | None]] = []
# Timestamp (unix) of the last force_dashboard_reauth activation.
_reauth_epoch: int = 0


def add_listener(callback: Callable[[str, bool], Awaitable[None] | None]) -> None:
    """Register a callback invoked as callback(key, value) after a change."""
    _listeners.append(callback)


async def _notify(key: str, value: bool) -> None:
    for callback in list(_listeners):
        try:
            result = callback(key, value)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # a broken listener must not block the toggle
            print(f"[feature_flags] listener for {key} failed: {exc}")


async def _ensure_tables(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS admin_features (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS admin_feature_rollout ("
        " key TEXT PRIMARY KEY, percent INTEGER NOT NULL DEFAULT 100)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS admin_feature_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    await db.commit()


async def load(force: bool = False) -> dict[str, bool]:
    """Load flag values from the database into the in-memory cache."""
    global _loaded, _reauth_epoch

    async with _lock:
        if _loaded and not force:
            return dict(_values)

        os.makedirs("db", exist_ok=True)
        try:
            async with aiosqlite.connect(CONFIG_DB) as db:
                await _ensure_tables(db)

                for key, default in FEATURE_DEFAULTS.items():
                    await db.execute(
                        "INSERT OR IGNORE INTO admin_features (key, value) VALUES (?, ?)",
                        (key, str(default).lower()),
                    )
                await db.commit()

                async with db.execute("SELECT key, value FROM admin_features") as cursor:
                    rows = await cursor.fetchall()
                stored = {key: str(value).lower() == "true" for key, value in rows}

                async with db.execute("SELECT key, percent FROM admin_feature_rollout") as cursor:
                    rollout_rows = await cursor.fetchall()

                async with db.execute(
                    "SELECT value FROM admin_feature_meta WHERE key = 'reauth_epoch'"
                ) as cursor:
                    meta_row = await cursor.fetchone()
        except Exception as exc:
            print(f"[feature_flags] load failed, using defaults: {exc}")
            _loaded = True
            return dict(_values)

        _values.clear()
        _values.update(FEATURE_DEFAULTS)
        _values.update({k: v for k, v in stored.items() if k in FEATURE_DEFAULTS})

        _rollouts.clear()
        _rollouts.update({key: max(0, min(100, int(pct))) for key, pct in rollout_rows})

        if meta_row and str(meta_row[0]).isdigit():
            _reauth_epoch = int(meta_row[0])

        _loaded = True
        return dict(_values)


def is_enabled(key: str) -> bool:
    """
    Synchronous flag lookup used by hot paths (command checks, listeners).

    Falls back to the declared default when the cache has not been loaded yet,
    so a flag never raises just because startup is still in progress.
    """
    flag = FEATURES_BY_KEY.get(key)
    if flag is None:
        return False
    if not _loaded:
        return flag.default

    if not _values.get(key, flag.default):
        return False

    # A dependency that is switched off disables the dependent flag as well.
    for dependency in flag.requires:
        if not _values.get(dependency, FEATURE_DEFAULTS.get(dependency, False)):
            return False
    return True


def is_enabled_for_guild(key: str, guild_id: int | None) -> bool:
    """Like is_enabled(), but honours percentage rollouts when configured."""
    if not is_enabled(key):
        return False
    if guild_id is None:
        return True
    if not _values.get("feature_flag_rollouts", True):
        return True

    percent = _rollouts.get(key, 100)
    if percent >= 100:
        return True
    if percent <= 0:
        return False
    # Stable bucketing: the same guild always lands in the same bucket.
    return (int(guild_id) % 100) < percent


def all_values() -> dict[str, bool]:
    return dict(_values)


def all_rollouts() -> dict[str, int]:
    return dict(_rollouts)


def reauth_epoch() -> int:
    """Unix timestamp of the last force_dashboard_reauth activation."""
    return _reauth_epoch


def describe() -> list[dict[str, Any]]:
    """Full metadata + current values, used by the dashboard."""
    return [
        {
            "key": flag.key,
            "label": flag.label,
            "category": flag.category,
            "description": flag.description,
            "effect": flag.effect,
            "requires": list(flag.requires),
            "default": flag.default,
            "enabled": _values.get(flag.key, flag.default),
            "active": is_enabled(flag.key),
            "rollout_percent": _rollouts.get(flag.key, 100),
        }
        for flag in FEATURE_FLAGS
    ]


async def set_values(updates: dict[str, bool]) -> dict[str, bool]:
    """Persist flag changes and notify listeners about the ones that changed."""
    global _reauth_epoch

    await load()
    clean = {key: bool(value) for key, value in updates.items() if key in FEATURE_DEFAULTS}
    if not clean:
        return {}

    changed = {key: value for key, value in clean.items() if _values.get(key) != value}

    async with aiosqlite.connect(CONFIG_DB) as db:
        await _ensure_tables(db)
        for key, value in clean.items():
            await db.execute(
                "INSERT OR REPLACE INTO admin_features (key, value) VALUES (?, ?)",
                (key, str(value).lower()),
            )

        # Turning re-auth on stamps the moment older sessions become invalid.
        if changed.get("force_dashboard_reauth") is True:
            _reauth_epoch = int(time.time())
            await db.execute(
                "INSERT OR REPLACE INTO admin_feature_meta (key, value) VALUES ('reauth_epoch', ?)",
                (str(_reauth_epoch),),
            )
        await db.commit()

    _values.update(clean)

    for key, value in changed.items():
        await _notify(key, value)

    return changed


async def set_rollout(key: str, percent: int) -> int:
    """Set the percentage of guilds a flag applies to (0-100)."""
    if key not in FEATURE_DEFAULTS:
        raise KeyError(key)
    percent = max(0, min(100, int(percent)))

    await load()
    async with aiosqlite.connect(CONFIG_DB) as db:
        await _ensure_tables(db)
        await db.execute(
            "INSERT OR REPLACE INTO admin_feature_rollout (key, percent) VALUES (?, ?)",
            (key, percent),
        )
        await db.commit()

    _rollouts[key] = percent
    return percent
