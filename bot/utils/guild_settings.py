"""
Per-guild behaviour settings.

The settings tab used to offer ten switches of which seven were decorative:
they were stored and read back, but no code ever looked at them. This module
is the registry for settings that actually change what the bot does, plus the
enforcement helpers the cogs call.

Everything lives in one table so a single query loads a guild's whole
behaviour profile, and it is cached because some of these are checked on
every message.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import aiosqlite

DB_PATH = "db/settings.db"
TABLE = "guild_behaviour"


@dataclass(frozen=True)
class GuildSetting:
    key: str
    label: str
    group: str
    description: str
    kind: str            # "bool" | "number" | "text" | "choice"
    default: Any
    # What the setting concretely changes, shown under the switch.
    effect: str
    choices: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 0


GROUP_COMMANDS = "Commands"
GROUP_MODERATION = "Moderation"
GROUP_APPEARANCE = "Appearance"
GROUP_MUSIC = "Music"
GROUP_PRIVACY = "Privacy & Safety"

SETTINGS: tuple[GuildSetting, ...] = (
    # ── Commands ──────────────────────────────────────────────────────────
    GuildSetting(
        "delete_command_messages", "Delete command messages", GROUP_COMMANDS,
        "Remove the message a member sent to run a command.",
        "bool", False,
        "The invoking message is deleted right after the command finishes.",
    ),
    GuildSetting(
        "mention_prefix_response", "Reply to mentions", GROUP_COMMANDS,
        "Answer with the current prefix when somebody just pings the bot.",
        "bool", True,
        "A plain @mention gets 'My prefix here is …' as a reply.",
    ),
    GuildSetting(
        "delete_command_delay", "Delete after", GROUP_COMMANDS,
        "Seconds to wait before deleting the command message.",
        "number", 0,
        "0 deletes immediately. Only applies when deletion is on.",
        minimum=0, maximum=60,
    ),
    GuildSetting(
        "disabled_commands", "Disabled commands", GROUP_COMMANDS,
        "Command names that cannot be used on this server, comma separated.",
        "text", "",
        "Listed commands are rejected with a short notice.",
    ),
    GuildSetting(
        "command_cooldown", "Command cooldown", GROUP_COMMANDS,
        "Minimum seconds between two commands from the same member.",
        "number", 0,
        "0 disables the extra cooldown. Staff with Manage Messages bypass it.",
        minimum=0, maximum=60,
    ),

    # ── Moderation ────────────────────────────────────────────────────────
    GuildSetting(
        "dm_mod_actions", "Notify on punishment", GROUP_MODERATION,
        "Send the member a DM when they are warned, muted, kicked or banned.",
        "bool", True,
        "The member receives the action, the server name and the reason.",
    ),
    GuildSetting(
        "require_reason_moderation", "Require a reason", GROUP_MODERATION,
        "Moderation commands refuse to run without a reason.",
        "bool", False,
        "Ban, kick, mute and warn abort when no reason is given.",
    ),
    GuildSetting(
        "protect_admin_roles", "Protect staff", GROUP_MODERATION,
        "Members with administrator permission cannot be punished through the bot.",
        "bool", True,
        "Moderation commands and dashboard actions refuse to target admins.",
    ),
    GuildSetting(
        "mod_log_channel", "Moderation log", GROUP_MODERATION,
        "Channel that receives a message for every moderation action.",
        "text", "",
        "Leave empty to disable. Enter a channel ID.",
    ),
    GuildSetting(
        "warn_threshold", "Warnings before action", GROUP_MODERATION,
        "How many warnings trigger the automatic punishment below.",
        "number", 0,
        "0 disables escalation.",
        minimum=0, maximum=20,
    ),
    GuildSetting(
        "warn_action", "Escalation", GROUP_MODERATION,
        "What happens when a member reaches the warning threshold.",
        "choice", "none",
        "Applied automatically once the threshold is hit.",
        choices=("none", "mute", "kick", "ban"),
    ),

    # ── Appearance ────────────────────────────────────────────────────────
    GuildSetting(
        "embed_color", "Embed colour", GROUP_APPEARANCE,
        "Accent colour for the bot's embeds on this server.",
        "text", "",
        "Hex value such as 5865F2. Empty keeps the default.",
    ),
    GuildSetting(
        "compact_embeds", "Compact embeds", GROUP_APPEARANCE,
        "Use shorter embeds without thumbnails and footers.",
        "bool", False,
        "Saves vertical space in busy channels.",
    ),
    GuildSetting(
        "show_command_footer", "Show command footer", GROUP_APPEARANCE,
        "Add 'requested by …' underneath command responses.",
        "bool", True,
        "Turn off for a cleaner look.",
    ),

    # ── Music ─────────────────────────────────────────────────────────────
    GuildSetting(
        "same_voice_only", "Same channel only", GROUP_MUSIC,
        "Only members in the bot's voice channel may control playback.",
        "bool", True,
        "Skip, pause and stop are rejected from elsewhere.",
    ),
    GuildSetting(
        "dj_role", "DJ role", GROUP_MUSIC,
        "Role required for playback control. Empty means everyone.",
        "text", "",
        "Enter a role ID.",
    ),
    GuildSetting(
        "max_queue_size", "Queue limit", GROUP_MUSIC,
        "How many tracks the queue may hold.",
        "number", 100,
        "Additional tracks are rejected once the limit is reached.",
        minimum=10, maximum=500,
    ),

    # ── Privacy & safety ──────────────────────────────────────────────────
    GuildSetting(
        "log_dashboard_changes", "Log dashboard changes", GROUP_PRIVACY,
        "Record configuration changes made through the dashboard.",
        "bool", True,
        "Entries appear under Admin → Audit.",
    ),
    GuildSetting(
        "auto_cleanup_invites", "Clean up bot invites", GROUP_PRIVACY,
        "Delete invite links the bot itself posts after they are used.",
        "bool", False,
        "Applies to invites created through dashboard actions.",
    ),
    GuildSetting(
        "ignore_bots", "Ignore other bots", GROUP_PRIVACY,
        "Skip messages from other bots in automod and leveling.",
        "bool", True,
        "Prevents bot loops and inflated XP.",
    ),
)

SETTINGS_BY_KEY: dict[str, GuildSetting] = {s.key: s for s in SETTINGS}
SETTING_GROUPS: tuple[str, ...] = tuple(dict.fromkeys(s.group for s in SETTINGS))
DEFAULTS: dict[str, Any] = {s.key: s.default for s in SETTINGS}

# guild_id -> {key: value}
_cache: dict[int, dict[str, Any]] = {}
_lock = asyncio.Lock()


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} ("
        " guild_id INTEGER NOT NULL,"
        " key TEXT NOT NULL,"
        " value TEXT,"
        " PRIMARY KEY (guild_id, key))"
    )
    await db.commit()


def _coerce(setting: GuildSetting, raw: Any) -> Any:
    """Turn a stored string back into the declared type."""
    if raw is None:
        return setting.default
    if setting.kind == "bool":
        return str(raw).strip().lower() in ("true", "1", "yes", "on")
    if setting.kind == "number":
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return setting.default
        if setting.maximum:
            value = max(setting.minimum, min(value, setting.maximum))
        return value
    if setting.kind == "choice":
        return raw if raw in setting.choices else setting.default
    return str(raw)


async def load(guild_id: int, force: bool = False) -> dict[str, Any]:
    """Load one guild's settings, cached."""
    gid = int(guild_id)

    async with _lock:
        if gid in _cache and not force:
            return dict(_cache[gid])

        values = dict(DEFAULTS)
        os.makedirs("db", exist_ok=True)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await _ensure_table(db)
                async with db.execute(
                    f"SELECT key, value FROM {TABLE} WHERE guild_id = ?", (gid,)
                ) as cursor:
                    async for key, raw in cursor:
                        setting = SETTINGS_BY_KEY.get(key)
                        if setting:
                            values[key] = _coerce(setting, raw)

                # Carry over the three switches that already existed in the
                # old table, so nobody loses their configuration.
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name='guild_extra_settings'"
                ) as cursor:
                    if await cursor.fetchone():
                        async with db.execute(
                            "SELECT delete_command_messages, mention_prefix_response,"
                            " same_voice_only FROM guild_extra_settings WHERE guild_id = ?",
                            (gid,),
                        ) as legacy:
                            row = await legacy.fetchone()
                        if row:
                            stored_keys = set()
                            async with db.execute(
                                f"SELECT key FROM {TABLE} WHERE guild_id = ?", (gid,)
                            ) as known:
                                stored_keys = {k async for (k,) in known}
                            for index, key in enumerate(
                                ("delete_command_messages", "mention_prefix_response", "same_voice_only")
                            ):
                                if key not in stored_keys and row[index] is not None:
                                    values[key] = bool(row[index])
        except Exception as exc:
            print(f"[guild_settings] load failed for {gid}: {exc}")

        _cache[gid] = values
        return dict(values)


def get(guild_id: int, key: str, fallback: Any = None) -> Any:
    """
    Synchronous read for hot paths.

    Falls back to the declared default when the guild is not cached yet, so
    a listener never blocks or raises just because nothing was loaded.
    """
    setting = SETTINGS_BY_KEY.get(key)
    if setting is None:
        return fallback

    cached = _cache.get(int(guild_id))
    if cached is None:
        return setting.default if fallback is None else fallback
    return cached.get(key, setting.default)


def get_bool(guild_id: int, key: str) -> bool:
    return bool(get(guild_id, key))


def get_int(guild_id: int, key: str) -> int:
    value = get(guild_id, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_id(guild_id: int, key: str) -> int:
    """Read a setting that holds a Discord snowflake."""
    raw = str(get(guild_id, key) or "").strip()
    return int(raw) if raw.isdigit() else 0


def disabled_commands(guild_id: int) -> set[str]:
    raw = str(get(guild_id, "disabled_commands") or "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


async def set_values(guild_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    """Persist changes and refresh the cache."""
    gid = int(guild_id)
    await load(gid)

    clean: dict[str, Any] = {}
    for key, value in updates.items():
        setting = SETTINGS_BY_KEY.get(key)
        if setting is None:
            continue
        clean[key] = _coerce(setting, value)

    if not clean:
        return {}

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        for key, value in clean.items():
            stored = str(value).lower() if isinstance(value, bool) else str(value)
            await db.execute(
                f"INSERT OR REPLACE INTO {TABLE} (guild_id, key, value) VALUES (?, ?, ?)",
                (gid, key, stored),
            )
        await db.commit()

    _cache.setdefault(gid, dict(DEFAULTS)).update(clean)
    return clean


def invalidate(guild_id: int | None = None) -> None:
    if guild_id is None:
        _cache.clear()
    else:
        _cache.pop(int(guild_id), None)


def describe(values: dict[str, Any]) -> list[dict]:
    """Settings plus current values, for the dashboard."""
    return [
        {
            "key": s.key,
            "label": s.label,
            "group": s.group,
            "description": s.description,
            "effect": s.effect,
            "kind": s.kind,
            "default": s.default,
            "value": values.get(s.key, s.default),
            "choices": list(s.choices),
            "min": s.minimum,
            "max": s.maximum,
        }
        for s in SETTINGS
    ]
