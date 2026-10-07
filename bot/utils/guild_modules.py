"""Persistent per-guild on/off gates for every dashboard module.

Rows only record explicit choices. Missing rows are enabled so an update never
silently turns off a server's existing setup. The in-memory set contains only
disabled modules and is shared by the dashboard API and Discord bot runtime.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import aiosqlite

DB_PATH = os.path.join("db", "settings.db")

# Only real bot systems get a switch. Overview/help/settings, entitlement and
# access pages are navigation or administration and would have no meaningful
# runtime to turn off.
MODULE_KEYS = frozenset({
    "backup", "server-stats", "antinuke", "automod", "honeypot", "verification",
    "emergency", "jail", "nightmode", "welcome", "applications", "leave",
    "joindm", "autorole", "reactionroles", "customroles", "vanityroles",
    "nickname", "leveling", "giveaways", "counting", "booster", "notify",
    "autoreact", "autoresponder", "custom-commands", "anonchat", "music", "j2c",
    "invcrole", "tickets", "sticky", "invites", "tracking", "noprefix",
    "teamlist", "teamupdate", "logging",
    "supportqueue",
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
    "stickymessage": "sticky", "tracking": "tracking",
    "invites": "invites", "noprefix": "noprefix",
    "teamlist": "teamlist", "teamupdate": "teamupdate",
    "logging": "logging", "antinuke": "antinuke", "automod": "automod",
    "honeypot": "honeypot", "verification": "verification", "emergency": "emergency",
    "jail": "jail", "nightmode": "nightmode", "applications": "applications",
    "joindm": "joindm", "supportqueue": "supportqueue", "server_stats": "server-stats",
    "selfroles": "reactionroles", "verify": "verification", "backup": "backup",
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
        for guild_id, module in rows:
            key = str(module)
            # Follow-up migration: Pull and Verify now intentionally share one
            # switch; the same applies to the Leveling leaderboard page.
            if key == "verification-pull":
                key = "verification"
            elif key == "leveling-leaderboard":
                key = "leveling"
            if key in MODULE_KEYS:
                _disabled.add((int(guild_id), key))
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
    enabled = is_enabled(guild_id, key)
    if key == "verification":
        from utils import verify_store
        os.makedirs(os.path.dirname(verify_store.DB_PATH), exist_ok=True)
        async with aiosqlite.connect(verify_store.DB_PATH) as db:
            settings = await verify_store.get_settings(db, guild_id)
        enabled = enabled and bool(settings["enabled"])
    return enabled


async def get_states(guild_id: int) -> dict[str, bool]:
    """Return every real system in one request for the sidebar indicators."""
    if not _loaded:
        await load()
    states = {key: is_enabled(guild_id, key) for key in sorted(MODULE_KEYS)}
    states["verification"] = await get_enabled(guild_id, "verification")
    return states


async def set_enabled(guild_id: int, module: str, enabled: bool) -> bool:
    key = validate_key(module)
    if key == "verification":
        from utils import verify_store
        os.makedirs(os.path.dirname(verify_store.DB_PATH), exist_ok=True)
        async with aiosqlite.connect(verify_store.DB_PATH) as db:
            settings = await verify_store.get_settings(db, guild_id)
            if enabled and not verify_store.is_configured(settings):
                raise ValueError("Wähle zuerst einen Verifizierungs-Kanal und eine Rolle.")
            await verify_store.save_settings(db, guild_id, {"enabled": bool(enabled)})
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


async def initialize_guild(guild_id: int) -> None:
    """Enable module availability on join without overwriting explicit choices."""
    await ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO guild_module_states (guild_id, module, enabled) VALUES (?, ?, 1)",
            [(int(guild_id), key) for key in sorted(MODULE_KEYS)],
        )
        await db.commit()


def module_for_callable(callback: Any) -> Optional[str]:
    """Map a bound cog/listener callback to its dashboard module."""
    # discord.py decorators wrap callbacks in _ItemCallback objects. Panels
    # may move the item into a generic LayoutView, so unwrap the real callback.
    if not isinstance(callback, type):
        callback = getattr(callback, "callback", callback)
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
    module = command_module(getattr(ctx, "command", None))
    if guild is not None and not is_enabled(guild.id, module):
        from utils.interaction_notices import disabled_card
        # Slash commands receive their private response through the tree gate.
        # Prefix commands cannot create ephemeral messages; send only to the
        # invoking user's DM rather than publishing the notice in the channel.
        if getattr(ctx, "interaction", None) is not None:
            from utils.interaction_notices import notify
            await notify(ctx.interaction, module)
        else:
            import discord
            try:
                await ctx.author.send(view=disabled_card(module), allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
        return False
    return True
