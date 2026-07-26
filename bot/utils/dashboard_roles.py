"""
Dashboard team roles.

Lets the bot owner hand out dashboard access to other people without giving
them the owner account. A role bundles a set of fine-grained permissions;
a person can hold several roles and gets the union of their permissions.

Model
-----
    permission   smallest unit, e.g. "tickets.manage"
    role         a named bundle of permissions, e.g. "Support Agent"
    assignment   user X holds role Y, optionally limited to certain guilds

Owners (OWNER_IDS / ADMIN_IDS) always have every permission and cannot be
locked out by a misconfigured role.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import aiosqlite

from utils import db_paths

DB_PATH = "db/admin_config.db"


# ══════════════════════════════════════════════════════════════════════════
#  Permissions
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    group: str
    description: str
    # Destructive permissions are highlighted in the UI.
    dangerous: bool = False


PERMISSIONS: tuple[Permission, ...] = (
    # ── Access ────────────────────────────────────────────────────────────
    Permission("dashboard.access", "Dashboard Access", "Access",
               "Sign in to the dashboard at all. Every role includes this."),
    Permission("guild.view", "View Servers", "Access",
               "See the server list and overview pages."),

    # ── Server configuration ──────────────────────────────────────────────
    Permission("settings.view", "View Settings", "Configuration",
               "Read general server settings."),
    Permission("settings.edit", "Edit Settings", "Configuration",
               "Change general server settings and the command prefix."),
    Permission("welcome.edit", "Edit Welcome", "Configuration",
               "Configure greet messages and welcome embeds."),
    Permission("joindm.edit", "Edit Join DM", "Configuration",
               "Configure the direct message new members receive."),
    Permission("autorole.edit", "Edit Autorole", "Configuration",
               "Configure roles handed out automatically on join."),
    Permission("reactionroles.edit", "Edit Reaction Roles", "Configuration",
               "Create and change reaction role menus."),
    Permission("vanityroles.edit", "Edit Vanity Roles", "Configuration",
               "Configure roles granted for a status/vanity URL."),
    Permission("customroles.edit", "Edit Custom Roles", "Configuration",
               "Configure the booster/custom role system."),
    Permission("autoreact.edit", "Edit Auto Reactions", "Configuration",
               "Configure automatic reactions on trigger words."),
    Permission("j2c.edit", "Edit Join-to-Create", "Configuration",
               "Configure temporary voice channels."),
    Permission("invcrole.edit", "Edit Voice Roles", "Configuration",
               "Configure roles granted while in a voice channel."),
    Permission("noprefix.edit", "Edit No-Prefix", "Configuration",
               "Manage users and roles that may run commands without a prefix.",
               dangerous=True),
    Permission("nickname.edit", "Edit Nickname Rules", "Configuration",
               "Configure automatic nickname prefixes and suffixes."),
    Permission("sticky.edit", "Edit Sticky Messages", "Configuration",
               "Configure sticky messages in channels."),

    # ── Security ──────────────────────────────────────────────────────────
    Permission("automod.view", "View Automod", "Security",
               "Read the automod configuration."),
    Permission("automod.edit", "Edit Automod", "Security",
               "Change automod rules and punishments."),
    Permission("antinuke.view", "View Anti-Nuke", "Security",
               "Read the anti-nuke configuration and whitelist."),
    Permission("antinuke.edit", "Edit Anti-Nuke", "Security",
               "Change anti-nuke protection and the whitelist.", dangerous=True),
    Permission("verification.view", "View Verification", "Security",
               "Read the verification setup."),
    Permission("verification.edit", "Edit Verification", "Security",
               "Change the verification setup."),
    Permission("security.scan", "Run Security Scans", "Security",
               "Run role, channel, webhook and invite scans."),

    # ── Moderation ────────────────────────────────────────────────────────
    Permission("moderation.warn", "Warn Members", "Moderation",
               "Issue warnings to members."),
    Permission("moderation.mute", "Mute Members", "Moderation",
               "Time members out and remove timeouts."),
    Permission("moderation.kick", "Kick Members", "Moderation",
               "Remove members from a server.", dangerous=True),
    Permission("moderation.ban", "Ban Members", "Moderation",
               "Ban users from a server.", dangerous=True),
    Permission("moderation.purge", "Purge Messages", "Moderation",
               "Bulk delete messages in a channel.", dangerous=True),
    Permission("members.view", "View Members", "Moderation",
               "Look up member information."),
    Permission("members.manage", "Manage Members", "Moderation",
               "Change nicknames and assign roles to members."),

    # ── Structure ─────────────────────────────────────────────────────────
    Permission("channels.view", "View Channels", "Structure",
               "List channels and their permissions."),
    Permission("channels.manage", "Manage Channels", "Structure",
               "Create, rename, lock and delete channels.", dangerous=True),
    Permission("roles.view", "View Roles", "Structure",
               "List server roles."),
    Permission("roles.manage", "Manage Roles", "Structure",
               "Create, edit and delete server roles.", dangerous=True),
    Permission("server.manage", "Manage Server", "Structure",
               "Rename the server and change verification levels.", dangerous=True),

    # ── Support ───────────────────────────────────────────────────────────
    Permission("tickets.view", "View Tickets", "Support",
               "Read the ticket configuration and open tickets."),
    Permission("tickets.manage", "Manage Tickets", "Support",
               "Change the ticket system and handle tickets."),

    # ── Engagement ────────────────────────────────────────────────────────
    Permission("leveling.view", "View Leveling", "Engagement",
               "Read leveling settings and the leaderboard."),
    Permission("leveling.edit", "Edit Leveling", "Engagement",
               "Change XP rates, rewards and rank cards."),
    Permission("invites.view", "View Invites", "Engagement",
               "See the invite leaderboard."),
    Permission("tracking.view", "View Tracking", "Engagement",
               "Read invite tracking settings."),
    Permission("tracking.edit", "Edit Tracking", "Engagement",
               "Change invite tracking settings."),

    # ── Logging & analytics ───────────────────────────────────────────────
    Permission("logging.view", "View Logging", "Analytics",
               "Read the event logging configuration."),
    Permission("logging.edit", "Edit Logging", "Analytics",
               "Change which events are logged and where."),
    Permission("reports.view", "View Reports", "Analytics",
               "Run analytics reports such as the security score."),
    Permission("reports.export", "Export Reports", "Analytics",
               "Download reports as JSON."),
    Permission("audit.view", "View Audit Log", "Analytics",
               "Read the cross-guild admin audit log and timeline."),

    # ── Operations ────────────────────────────────────────────────────────
    Permission("health.view", "View Health", "Operations",
               "See shard, Lavalink, database and Discord API health."),
    Permission("logs.view", "View Logs", "Operations",
               "Read captured warnings and errors."),
    Permission("metrics.view", "View Metrics", "Operations",
               "See API performance and command error statistics."),
    Permission("features.view", "View Feature Flags", "Operations",
               "See the global feature flags and their state."),
    Permission("features.edit", "Edit Feature Flags", "Operations",
               "Toggle global feature flags and rollouts.", dangerous=True),
    Permission("maintenance.toggle", "Toggle Maintenance", "Operations",
               "Put the bot into maintenance mode.", dangerous=True),
    Permission("announcements.send", "Send Announcements", "Operations",
               "Schedule announcements to every server.", dangerous=True),
    Permission("broadcast.send", "Set Broadcast Banner", "Operations",
               "Change the global notification shown in the dashboard."),
    Permission("premium.manage", "Manage Premium", "Operations",
               "Grant and revoke premium for servers."),
    Permission("blacklist.manage", "Manage Blacklist", "Operations",
               "Add and remove users or servers from the blacklist.", dangerous=True),
    Permission("massconfig.push", "Mass Config Push", "Operations",
               "Apply one setting to many servers at once.", dangerous=True),
    Permission("approvals.view", "View Approvals", "Operations",
               "See queued admin actions waiting for approval."),
    Permission("approvals.resolve", "Resolve Approvals", "Operations",
               "Approve or reject queued admin actions.", dangerous=True),

    # ── Team management ───────────────────────────────────────────────────
    Permission("team.view", "View Team", "Team",
               "See who holds which dashboard role."),
    Permission("team.assign", "Assign Roles", "Team",
               "Give and take dashboard roles from people.", dangerous=True),
)

PERMISSIONS_BY_KEY: dict[str, Permission] = {p.key: p for p in PERMISSIONS}
PERMISSION_GROUPS: tuple[str, ...] = tuple(dict.fromkeys(p.group for p in PERMISSIONS))

# Shorthand bundles used when defining roles below.
_VIEW_BASE = ("dashboard.access", "guild.view")


def _perms(*keys: str) -> tuple[str, ...]:
    """Build a permission tuple, always including the view baseline."""
    combined = list(_VIEW_BASE)
    for key in keys:
        if key not in PERMISSIONS_BY_KEY:
            raise KeyError(f"Unknown permission: {key}")
        if key not in combined:
            combined.append(key)
    return tuple(combined)


# ══════════════════════════════════════════════════════════════════════════
#  Roles
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    category: str
    description: str
    permissions: tuple[str, ...]
    # 100 = highest. Used for sorting and to stop people handing out roles
    # more powerful than their own.
    rank: int
    color: str = "#3b82f6"


CAT_LEADERSHIP = "Leadership"
CAT_MODERATION = "Moderation"
CAT_SECURITY = "Security"
CAT_SUPPORT = "Support"
CAT_COMMUNITY = "Community"
CAT_CONTENT = "Content"
CAT_TECHNICAL = "Technical"
CAT_ANALYTICS = "Analytics"

ALL_PERMISSION_KEYS = tuple(p.key for p in PERMISSIONS)


ROLES: tuple[Role, ...] = (
    # ── Leadership (5) ────────────────────────────────────────────────────
    Role("co_owner", "Co-Owner", CAT_LEADERSHIP,
         "Full access to everything, including handing out dashboard roles.",
         ALL_PERMISSION_KEYS, rank=95, color="#f43f5e"),
    Role("administrator", "Administrator", CAT_LEADERSHIP,
         "Everything except managing the dashboard team.",
         tuple(k for k in ALL_PERMISSION_KEYS if k != "team.assign"),
         rank=90, color="#ef4444"),
    Role("head_of_staff", "Head of Staff", CAT_LEADERSHIP,
         "Oversees the whole staff team: moderation, support and the team list.",
         _perms("settings.view", "members.view", "members.manage",
                "moderation.warn", "moderation.mute", "moderation.kick", "moderation.ban",
                "moderation.purge", "tickets.view", "tickets.manage",
                "audit.view", "reports.view", "team.view", "channels.view", "roles.view"),
         rank=80, color="#f97316"),
    Role("server_manager", "Server Manager", CAT_LEADERSHIP,
         "Full configuration rights for every server module.",
         _perms("settings.view", "settings.edit", "welcome.edit", "joindm.edit",
                "autorole.edit", "reactionroles.edit", "vanityroles.edit",
                "customroles.edit", "autoreact.edit", "j2c.edit", "invcrole.edit",
                "nickname.edit", "sticky.edit", "leveling.view", "leveling.edit",
                "logging.view", "logging.edit", "channels.view", "roles.view"),
         rank=75, color="#f59e0b"),
    Role("deputy_manager", "Deputy Manager", CAT_LEADERSHIP,
         "Configuration rights, but nothing destructive.",
         _perms("settings.view", "settings.edit", "welcome.edit", "joindm.edit",
                "autorole.edit", "autoreact.edit", "leveling.view", "leveling.edit",
                "logging.view", "channels.view", "roles.view", "members.view"),
         rank=70, color="#eab308"),

    # ── Moderation (6) ────────────────────────────────────────────────────
    Role("head_moderator", "Head Moderator", CAT_MODERATION,
         "All moderation actions plus the audit log.",
         _perms("moderation.warn", "moderation.mute", "moderation.kick",
                "moderation.ban", "moderation.purge", "members.view", "members.manage",
                "automod.view", "automod.edit", "audit.view", "channels.view", "roles.view"),
         rank=65, color="#dc2626"),
    Role("senior_moderator", "Senior Moderator", CAT_MODERATION,
         "Ban, kick, mute, warn and purge.",
         _perms("moderation.warn", "moderation.mute", "moderation.kick",
                "moderation.ban", "moderation.purge", "members.view", "automod.view"),
         rank=60, color="#e11d48"),
    Role("moderator", "Moderator", CAT_MODERATION,
         "Kick, mute and warn. No bans.",
         _perms("moderation.warn", "moderation.mute", "moderation.kick",
                "moderation.purge", "members.view"),
         rank=50, color="#be123c"),
    Role("junior_moderator", "Junior Moderator", CAT_MODERATION,
         "Mute and warn only.",
         _perms("moderation.warn", "moderation.mute", "members.view"),
         rank=40, color="#9f1239"),
    Role("trial_moderator", "Trial Moderator", CAT_MODERATION,
         "Warnings only, for staff still in training.",
         _perms("moderation.warn", "members.view"),
         rank=30, color="#881337"),
    Role("chat_moderator", "Chat Moderator", CAT_MODERATION,
         "Cleans up chat: purge messages and read automod.",
         _perms("moderation.purge", "moderation.warn", "automod.view", "channels.view"),
         rank=35, color="#a21caf"),

    # ── Security (5) ──────────────────────────────────────────────────────
    Role("security_chief", "Security Chief", CAT_SECURITY,
         "Owns anti-nuke, automod and verification.",
         _perms("antinuke.view", "antinuke.edit", "automod.view", "automod.edit",
                "verification.view", "verification.edit", "security.scan",
                "audit.view", "reports.view", "roles.view", "channels.view"),
         rank=72, color="#7c3aed"),
    Role("antinuke_officer", "Anti-Nuke Officer", CAT_SECURITY,
         "Manages anti-nuke protection and the whitelist.",
         _perms("antinuke.view", "antinuke.edit", "security.scan", "audit.view", "roles.view"),
         rank=62, color="#6d28d9"),
    Role("automod_engineer", "Automod Engineer", CAT_SECURITY,
         "Builds and tunes the automod rules.",
         _perms("automod.view", "automod.edit", "reports.view", "channels.view"),
         rank=55, color="#5b21b6"),
    Role("verification_officer", "Verification Officer", CAT_SECURITY,
         "Runs the member verification system.",
         _perms("verification.view", "verification.edit", "members.view", "roles.view"),
         rank=45, color="#4c1d95"),
    Role("threat_analyst", "Threat Analyst", CAT_SECURITY,
         "Read-only: runs security scans and reads the audit log.",
         _perms("security.scan", "audit.view", "reports.view", "antinuke.view",
                "automod.view", "roles.view", "channels.view"),
         rank=38, color="#8b5cf6"),

    # ── Support (4) ───────────────────────────────────────────────────────
    Role("support_lead", "Support Lead", CAT_SUPPORT,
         "Runs the support team and the ticket system.",
         _perms("tickets.view", "tickets.manage", "members.view", "reports.view",
                "team.view", "channels.view"),
         rank=58, color="#0ea5e9"),
    Role("support_agent", "Support Agent", CAT_SUPPORT,
         "Handles tickets day to day.",
         _perms("tickets.view", "tickets.manage", "members.view"),
         rank=42, color="#0284c7"),
    Role("ticket_reviewer", "Ticket Reviewer", CAT_SUPPORT,
         "Reads tickets without being able to change anything.",
         _perms("tickets.view", "members.view"),
         rank=25, color="#0369a1"),
    Role("onboarding_guide", "Onboarding Guide", CAT_SUPPORT,
         "Shapes the first impression: welcome messages and join DMs.",
         _perms("welcome.edit", "joindm.edit", "verification.view", "members.view"),
         rank=40, color="#075985"),

    # ── Community (5) ─────────────────────────────────────────────────────
    Role("community_manager", "Community Manager", CAT_COMMUNITY,
         "Owns everything the members interact with.",
         _perms("leveling.view", "leveling.edit", "welcome.edit", "autorole.edit",
                "reactionroles.edit", "autoreact.edit", "invites.view",
                "tracking.view", "members.view"),
         rank=60, color="#10b981"),
    Role("engagement_manager", "Engagement Manager", CAT_COMMUNITY,
         "Keeps members active: leveling and reactions.",
         _perms("leveling.view", "leveling.edit", "autoreact.edit", "invites.view",
                "reports.view"),
         rank=48, color="#059669"),
    Role("event_manager", "Event Manager", CAT_COMMUNITY,
         "Announces and runs events across all servers.",
         _perms("announcements.send", "broadcast.send", "channels.view", "members.view"),
         rank=52, color="#047857"),
    Role("level_operator", "Level System Operator", CAT_COMMUNITY,
         "Tunes XP rates, rewards and rank cards.",
         _perms("leveling.view", "leveling.edit"),
         rank=35, color="#065f46"),
    Role("role_curator", "Role Curator", CAT_COMMUNITY,
         "Manages every role-granting module.",
         _perms("reactionroles.edit", "vanityroles.edit", "customroles.edit",
                "autorole.edit", "invcrole.edit", "roles.view"),
         rank=46, color="#34d399"),

    # ── Content (4) ───────────────────────────────────────────────────────
    Role("content_manager", "Content Manager", CAT_CONTENT,
         "Owns the written content the bot posts.",
         _perms("welcome.edit", "joindm.edit", "sticky.edit", "autoreact.edit",
                "channels.view"),
         rank=44, color="#ec4899"),
    Role("media_moderator", "Media Moderator", CAT_CONTENT,
         "Watches media and links, cleans up violations.",
         _perms("automod.view", "automod.edit", "moderation.purge", "moderation.warn",
                "channels.view"),
         rank=41, color="#db2777"),
    Role("announcement_publisher", "Announcement Publisher", CAT_CONTENT,
         "May only publish announcements — nothing else.",
         _perms("announcements.send", "broadcast.send"),
         rank=28, color="#be185d"),
    Role("branding_manager", "Branding Manager", CAT_CONTENT,
         "Server identity: name, prefix and general settings.",
         _perms("settings.view", "settings.edit", "server.manage"),
         rank=50, color="#9d174d"),

    # ── Technical (6) ─────────────────────────────────────────────────────
    Role("technical_lead", "Technical Lead", CAT_TECHNICAL,
         "Owns the technical side: features, health, logs and metrics.",
         _perms("features.view", "features.edit", "health.view", "logs.view",
                "metrics.view", "audit.view", "reports.view", "maintenance.toggle"),
         rank=78, color="#6366f1"),
    Role("devops_engineer", "DevOps Engineer", CAT_TECHNICAL,
         "Watches the deployment and can put the bot into maintenance.",
         _perms("health.view", "logs.view", "metrics.view", "maintenance.toggle",
                "features.view"),
         rank=66, color="#4f46e5"),
    Role("feature_manager", "Feature Manager", CAT_TECHNICAL,
         "Toggles feature flags and runs percentage rollouts.",
         _perms("features.view", "features.edit", "health.view"),
         rank=64, color="#4338ca"),
    Role("database_steward", "Database Steward", CAT_TECHNICAL,
         "Watches database health, integrity scans and backups.",
         _perms("health.view", "logs.view", "reports.view"),
         rank=47, color="#3730a3"),
    Role("integration_manager", "Integration Manager", CAT_TECHNICAL,
         "Owns voice, no-prefix and nickname integrations.",
         _perms("j2c.edit", "invcrole.edit", "noprefix.edit", "nickname.edit",
                "channels.view", "roles.view"),
         rank=54, color="#312e81"),
    Role("bot_operator", "Bot Operator", CAT_TECHNICAL,
         "Day-to-day operation: health, blacklist and premium.",
         _perms("health.view", "logs.view", "blacklist.manage", "premium.manage",
                "maintenance.toggle"),
         rank=68, color="#818cf8"),

    # ── Analytics (5) ─────────────────────────────────────────────────────
    Role("analytics_lead", "Analytics Lead", CAT_ANALYTICS,
         "All reports including export.",
         _perms("reports.view", "reports.export", "metrics.view", "invites.view",
                "tracking.view", "leveling.view", "audit.view"),
         rank=56, color="#14b8a6"),
    Role("data_analyst", "Data Analyst", CAT_ANALYTICS,
         "Reads reports without export rights.",
         _perms("reports.view", "metrics.view", "leveling.view", "invites.view"),
         rank=33, color="#0d9488"),
    Role("growth_analyst", "Growth Analyst", CAT_ANALYTICS,
         "Focused on invites, tracking and member retention.",
         _perms("invites.view", "tracking.view", "tracking.edit", "reports.view",
                "leveling.view"),
         rank=37, color="#0f766e"),
    Role("audit_officer", "Audit Officer", CAT_ANALYTICS,
         "Reads the cross-guild audit log and incident timeline.",
         _perms("audit.view", "reports.view", "logs.view", "team.view"),
         rank=49, color="#115e59"),
    Role("compliance_officer", "Compliance Officer", CAT_ANALYTICS,
         "Reviews the audit log and resolves queued admin actions.",
         _perms("audit.view", "approvals.view", "approvals.resolve", "reports.view",
                "reports.export", "team.view"),
         rank=71, color="#134e4a"),
)

ROLES_BY_KEY: dict[str, Role] = {r.key: r for r in ROLES}
ROLE_CATEGORIES: tuple[str, ...] = tuple(dict.fromkeys(r.category for r in ROLES))

assert len(ROLES) == 40, f"expected 40 roles, got {len(ROLES)}"


# ══════════════════════════════════════════════════════════════════════════
#  Storage
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class Assignment:
    user_id: str
    role_key: str
    # Empty tuple means: applies to every guild.
    guild_ids: tuple[str, ...] = field(default_factory=tuple)
    granted_by: str = ""
    granted_at: int = 0
    note: str = ""


_lock = asyncio.Lock()
# user_id -> list[Assignment]
_cache: dict[str, list[Assignment]] = {}
_loaded = False
# Owners/admins stored in the database: user_id -> record
_owner_cache: dict[str, dict] = {}


async def _ensure_tables(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_role_assignments ("
        " user_id TEXT NOT NULL,"
        " role_key TEXT NOT NULL,"
        " guild_ids TEXT DEFAULT '',"
        " granted_by TEXT DEFAULT '',"
        " granted_at INTEGER DEFAULT 0,"
        " note TEXT DEFAULT '',"
        " PRIMARY KEY (user_id, role_key))"
    )
    # Owners and admins added through the dashboard, on top of the ones from
    # the environment. Lets the team be managed without redeploying.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_owners ("
        " user_id TEXT PRIMARY KEY,"
        " kind TEXT NOT NULL DEFAULT 'admin',"      # 'owner' or 'admin'
        " added_by TEXT DEFAULT '',"
        " added_at INTEGER DEFAULT 0,"
        " note TEXT DEFAULT '')"
    )
    await db.commit()


async def load(force: bool = False) -> None:
    """Load all assignments into memory."""
    global _loaded

    async with _lock:
        if _loaded and not force:
            return

        os.makedirs("db", exist_ok=True)
        entries: dict[str, list[Assignment]] = {}
        owners: dict[str, dict] = {}
        try:
            async with db_paths.connect(DB_PATH) as db:
                await _ensure_tables(db)
                async with db.execute(
                    "SELECT user_id, role_key, guild_ids, granted_by, granted_at, note"
                    " FROM dashboard_role_assignments"
                ) as cursor:
                    async for row in cursor:
                        user_id, role_key, guild_ids, granted_by, granted_at, note = row
                        if role_key not in ROLES_BY_KEY:
                            continue  # role was removed from the registry
                        entries.setdefault(str(user_id), []).append(
                            Assignment(
                                user_id=str(user_id),
                                role_key=role_key,
                                guild_ids=tuple(g for g in (guild_ids or "").split(",") if g),
                                granted_by=granted_by or "",
                                granted_at=int(granted_at or 0),
                                note=note or "",
                            )
                        )

                async with db.execute(
                    "SELECT user_id, kind, added_by, added_at, note FROM dashboard_owners"
                ) as cursor:
                    async for row in cursor:
                        user_id, kind, added_by, added_at, note = row
                        owners[str(user_id)] = {
                            "user_id": str(user_id),
                            "kind": kind or "admin",
                            "added_by": added_by or "",
                            "added_at": int(added_at or 0),
                            "note": note or "",
                        }
        except Exception as exc:
            print(f"[dashboard_roles] load failed: {exc}")
            _loaded = True
            return

        _cache.clear()
        _cache.update(entries)
        _owner_cache.clear()
        _owner_cache.update(owners)
        _loaded = True


def env_owner_ids() -> set[str]:
    """Owner/admin IDs coming from the environment. These cannot be removed."""
    from utils.config import OWNER_IDS_STR

    admin_env = os.getenv("ADMIN_IDS") or os.getenv("NEXT_PUBLIC_ADMIN_IDS") or ""
    ids = {part.strip() for part in admin_env.split(",") if part.strip()}
    ids.update(OWNER_IDS_STR)
    return ids


def db_owner_ids() -> set[str]:
    """Owner/admin IDs added through the dashboard."""
    return set(_owner_cache)


def is_owner(user_id: str) -> bool:
    """Owners bypass the role system entirely."""
    uid = str(user_id)
    return uid in env_owner_ids() or uid in _owner_cache


def can_manage_owners(user_id: str) -> bool:
    """
    Who may add or remove owners and admins.

    Only environment owners and dashboard entries of kind 'owner'. A plain
    'admin' has full feature access but must not be able to widen the circle
    of people who can — otherwise the distinction between the two levels
    would be meaningless.
    """
    uid = str(user_id)
    if uid in env_owner_ids():
        return True
    record = _owner_cache.get(uid)
    return bool(record and record.get("kind") == "owner")


def list_owners() -> list[dict]:
    """
    Everyone with full access, from both sources.

    Environment entries are marked as locked so the dashboard can grey out
    their delete button — removing them there would have no effect anyway.
    """
    entries: list[dict] = []

    for uid in sorted(env_owner_ids()):
        entries.append(
            {
                "user_id": uid,
                "kind": "owner",
                "source": "env",
                "locked": True,
                "added_by": "",
                "added_at": 0,
                "note": "Configured through OWNER_IDS / ADMIN_IDS",
            }
        )

    for uid, record in sorted(_owner_cache.items()):
        if uid in env_owner_ids():
            continue  # already listed above
        entries.append({**record, "source": "dashboard", "locked": False})

    return entries


async def add_owner(
    user_id: str, *, kind: str = "admin", added_by: str, note: str = ""
) -> dict:
    """Grant somebody full dashboard access."""
    uid = str(user_id).strip()
    if not uid.isdigit() or not 15 <= len(uid) <= 20:
        raise ValueError("user_id must be a valid Discord ID")
    if kind not in ("owner", "admin"):
        raise ValueError("kind must be 'owner' or 'admin'")

    await load()
    now = int(time.time())

    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await db.execute(
            "INSERT OR REPLACE INTO dashboard_owners"
            " (user_id, kind, added_by, added_at, note) VALUES (?, ?, ?, ?, ?)",
            (uid, kind, str(added_by), now, note[:200]),
        )
        await db.commit()

    record = {
        "user_id": uid,
        "kind": kind,
        "added_by": str(added_by),
        "added_at": now,
        "note": note[:200],
    }
    _owner_cache[uid] = record
    return record


async def remove_owner(user_id: str) -> bool:
    """
    Revoke full access.

    Entries from the environment cannot be removed here — they would come
    back on the next restart, so we reject them instead of pretending.
    """
    uid = str(user_id).strip()
    if uid in env_owner_ids():
        raise PermissionError(
            "This ID comes from OWNER_IDS / ADMIN_IDS and must be changed in the "
            "environment variables."
        )

    await load()
    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        cursor = await db.execute("DELETE FROM dashboard_owners WHERE user_id = ?", (uid,))
        await db.commit()
        removed = cursor.rowcount > 0

    _owner_cache.pop(uid, None)
    return removed


def get_assignments(user_id: str) -> list[Assignment]:
    return list(_cache.get(str(user_id), []))


def get_roles(user_id: str) -> list[Role]:
    """Roles a user holds, strongest first."""
    roles = [ROLES_BY_KEY[a.role_key] for a in get_assignments(user_id) if a.role_key in ROLES_BY_KEY]
    return sorted(roles, key=lambda r: r.rank, reverse=True)


def get_permissions(user_id: str, guild_id: str | None = None) -> set[str]:
    """
    Every permission a user has, optionally narrowed to one guild.

    An assignment with no guild_ids applies everywhere; one with guild_ids
    only counts for those guilds.
    """
    if is_owner(user_id):
        return set(ALL_PERMISSION_KEYS)

    granted: set[str] = set()
    for assignment in get_assignments(user_id):
        if assignment.guild_ids and guild_id is not None:
            if str(guild_id) not in assignment.guild_ids:
                continue
        role = ROLES_BY_KEY.get(assignment.role_key)
        if role:
            granted.update(role.permissions)
    return granted


def has_permission(user_id: str, permission: str, guild_id: str | None = None) -> bool:
    return permission in get_permissions(user_id, guild_id)


def highest_rank(user_id: str) -> int:
    if is_owner(user_id):
        return 100
    roles = get_roles(user_id)
    return roles[0].rank if roles else 0


def accessible_guilds(user_id: str) -> set[str] | None:
    """
    Which guilds a user may touch through their roles.

    None means "no restriction" (owner, or at least one unrestricted role).
    """
    if is_owner(user_id):
        return None

    guilds: set[str] = set()
    for assignment in get_assignments(user_id):
        if not assignment.guild_ids:
            return None
        guilds.update(assignment.guild_ids)
    return guilds


async def assign(
    user_id: str,
    role_key: str,
    *,
    granted_by: str,
    guild_ids: list[str] | None = None,
    note: str = "",
) -> Assignment:
    """Give a role to a user. Re-assigning updates the existing entry."""
    if role_key not in ROLES_BY_KEY:
        raise KeyError(f"Unknown role: {role_key}")

    await load()
    clean_guilds = tuple(str(g).strip() for g in (guild_ids or []) if str(g).strip().isdigit())
    now = int(time.time())

    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await db.execute(
            "INSERT OR REPLACE INTO dashboard_role_assignments"
            " (user_id, role_key, guild_ids, granted_by, granted_at, note)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (str(user_id), role_key, ",".join(clean_guilds), str(granted_by), now, note[:200]),
        )
        await db.commit()

    assignment = Assignment(
        user_id=str(user_id),
        role_key=role_key,
        guild_ids=clean_guilds,
        granted_by=str(granted_by),
        granted_at=now,
        note=note[:200],
    )
    existing = [a for a in _cache.get(str(user_id), []) if a.role_key != role_key]
    existing.append(assignment)
    _cache[str(user_id)] = existing
    return assignment


async def revoke(user_id: str, role_key: str) -> bool:
    """Take a role away. Returns True when something was removed."""
    await load()
    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        cursor = await db.execute(
            "DELETE FROM dashboard_role_assignments WHERE user_id = ? AND role_key = ?",
            (str(user_id), role_key),
        )
        await db.commit()
        removed = cursor.rowcount > 0

    remaining = [a for a in _cache.get(str(user_id), []) if a.role_key != role_key]
    if remaining:
        _cache[str(user_id)] = remaining
    else:
        _cache.pop(str(user_id), None)
    return removed


async def revoke_all(user_id: str) -> int:
    """Remove every role from a user."""
    await load()
    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        cursor = await db.execute(
            "DELETE FROM dashboard_role_assignments WHERE user_id = ?", (str(user_id),)
        )
        await db.commit()
        count = cursor.rowcount

    _cache.pop(str(user_id), None)
    return count


def all_members() -> list[dict]:
    """Everyone who holds at least one dashboard role."""
    members = []
    for user_id, assignments in _cache.items():
        roles = [ROLES_BY_KEY[a.role_key] for a in assignments if a.role_key in ROLES_BY_KEY]
        roles.sort(key=lambda r: r.rank, reverse=True)
        members.append(
            {
                "user_id": user_id,
                "roles": [
                    {
                        "key": a.role_key,
                        "label": ROLES_BY_KEY[a.role_key].label,
                        "color": ROLES_BY_KEY[a.role_key].color,
                        "guild_ids": list(a.guild_ids),
                        "granted_by": a.granted_by,
                        "granted_at": a.granted_at,
                        "note": a.note,
                    }
                    for a in assignments
                    if a.role_key in ROLES_BY_KEY
                ],
                "permission_count": len(get_permissions(user_id)),
                "highest_rank": roles[0].rank if roles else 0,
            }
        )
    members.sort(key=lambda m: m["highest_rank"], reverse=True)
    return members


def describe_roles() -> list[dict]:
    """Role catalogue for the dashboard."""
    holders: dict[str, int] = {}
    for assignments in _cache.values():
        for assignment in assignments:
            holders[assignment.role_key] = holders.get(assignment.role_key, 0) + 1

    return [
        {
            "key": role.key,
            "label": role.label,
            "category": role.category,
            "description": role.description,
            "rank": role.rank,
            "color": role.color,
            "permissions": list(role.permissions),
            "permission_count": len(role.permissions),
            "dangerous_count": sum(
                1 for k in role.permissions
                if PERMISSIONS_BY_KEY[k].dangerous
            ),
            "holders": holders.get(role.key, 0),
        }
        for role in sorted(ROLES, key=lambda r: (-r.rank, r.label))
    ]


def describe_permissions() -> list[dict]:
    return [
        {
            "key": p.key,
            "label": p.label,
            "group": p.group,
            "description": p.description,
            "dangerous": p.dangerous,
        }
        for p in PERMISSIONS
    ]
