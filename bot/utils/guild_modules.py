"""Persistent per-guild on/off gates for every dashboard module.

Rows only record explicit choices. Missing rows are enabled so an update never
silently turns off a server's existing setup. The in-memory set contains only
disabled modules and is shared by the dashboard API and Discord bot runtime.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any, Optional

import aiosqlite

DB_PATH = os.path.join("db", "settings.db")

MODULE_KEYS = frozenset({
    "overview", "help", "premium", "design", "backup", "server-stats",
    "antinuke", "automod", "honeypot", "verification", "verification-pull",
    "emergency", "jail", "nightmode", "welcome", "applications", "leave",
    "joindm", "autorole", "reactionroles", "customroles", "vanityroles",
    "nickname", "leveling", "leveling-leaderboard", "giveaways", "counting",
    "booster", "notify", "autoreact", "autoresponder", "custom-commands",
    "anonchat", "music", "j2c", "invcrole", "tickets", "compose", "sticky",
    "invites", "tracking", "noprefix", "speedrun", "template-upload",
    "templates", "teamlist", "teamupdate", "logging", "botlogs",
    "admin-dashboard", "dashboard-access", "supportqueue", "settings",
})

# Python module/cog names do not always match their dashboard route.
RUNTIME_ALIASES = {
    "welcome": "welcome", "leave": "leave", "autorole": "autorole",
    "reactionroles": "reactionroles", "reaction_roles": "reactionroles",
    "customrole": "customroles", "vanity": "vanityroles", "nickname": "nickname",
    "leveling": "leveling", "giveaway": "giveaways", "giveaways": "giveaways",
    "counting": "counting", "nitro": "booster", "notify": "notify",
    "autoreact": "autoreact", "autoresponder": "autoresponder",
    "custom_commands": "custom-commands", "anonchat": "anonchat",
    "music": "music", "j2c": "j2c", "voice": "invcrole", "ticket": "tickets",
    "compose": "compose", "stickymessage": "sticky", "tracking": "tracking",
    "invites": "invites", "noprefix": "noprefix", "speedrun": "speedrun",
    "templates": "templates", "teamlist": "teamlist", "teamupdate": "teamupdate",
    "logging": "logging", "antinuke": "antinuke", "automod": "automod",
    "honeypot": "honeypot", "verification": "verification", "emergency": "emergency",
    "jail": "jail", "nightmode": "nightmode", "applications": "applications",
    "joindm": "joindm", "supportqueue": "supportqueue", "server_stats": "server-stats",
}

_disabled: set[tuple[int, str]] = set()
_loaded = False
_lock = asyncio.Lock()


def validate_key(module: str) -> str:
    key = str(module or "").strip().lower()
    if key not in MODULE_KEYS:
        raise ValueError(f"Unknown dashboard module: {module}")
    return key


async def ensure() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS guild_module_states (
                guild_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, module)
            )"""
        )
        await db.commit()


async def load() -> None:
    global _loaded
    async with _lock:
        await ensure()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, module FROM guild_module_states WHERE enabled = 0"
            ) as cursor:
                rows = await cursor.fetchall()
        _disabled.clear()
        _disabled.update((int(guild_id), str(module)) for guild_id, module in rows)
        _loaded = True


def is_enabled(guild_id: int | str | None, module: str | None) -> bool:
    """Hot-path lookup used by Discord command/listener dispatch."""
    if guild_id is None or not module:
        return True
    return (int(guild_id), str(module)) not in _disabled


async def get_enabled(guild_id: int, module: str) -> bool:
    key = validate_key(module)
    if not _loaded:
        await load()
    return is_enabled(guild_id, key)


async def set_enabled(guild_id: int, module: str, enabled: bool) -> bool:
    key = validate_key(module)
    await ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO guild_module_states (guild_id, module, enabled, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(guild_id, module) DO UPDATE SET
                 enabled = excluded.enabled,
                 updated_at = CURRENT_TIMESTAMP""",
            (int(guild_id), key, int(bool(enabled))),
        )
        await db.commit()
    marker = (int(guild_id), key)
    if enabled:
        _disabled.discard(marker)
    else:
        _disabled.add(marker)
    return bool(enabled)


def module_for_callable(callback: Any) -> Optional[str]:
    """Map a bound cog/listener callback to its dashboard module."""
    module_name = str(getattr(callback, "__module__", "")).lower()
    owner = getattr(callback, "__self__", None)
    if owner is not None:
        module_name += "." + owner.__class__.__name__.lower()
    for alias in sorted(RUNTIME_ALIASES, key=len, reverse=True):
        if alias in module_name:
            return RUNTIME_ALIASES[alias]
    return None


def guild_id_from_event(args: tuple[Any, ...]) -> Optional[int]:
    for value in args:
        guild = getattr(value, "guild", None)
        if guild is not None and getattr(guild, "id", None) is not None:
            return int(guild.id)
        if getattr(value, "guild_id", None) is not None:
            return int(value.guild_id)
    return None


def command_module(command: Any) -> Optional[str]:
    if command is None:
        return None
    binding = getattr(command, "binding", None) or getattr(command, "cog", None)
    module = module_for_callable(binding.__class__) if binding is not None else None
    if module:
        return module
    callback = getattr(command, "callback", None)
    module = module_for_callable(callback)
    if module:
        return module
    name = str(getattr(command, "qualified_name", "") or getattr(command, "name", "")).lower()
    for alias in sorted(RUNTIME_ALIASES, key=len, reverse=True):
        if alias.replace("_", "-") in name.replace("_", "-"):
            return RUNTIME_ALIASES[alias]
    return None


async def command_check(ctx: Any) -> bool:
    guild = getattr(ctx, "guild", None)
    return guild is None or is_enabled(guild.id, command_module(getattr(ctx, "command", None)))
