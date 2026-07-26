"""
Command-level enforcement of the global feature flags.

A single bot-wide check runs before every command and applies the safety
flags. Without this the flags would just be values in a table — this is the
piece that makes them actually do something.

Order matters: the cheapest and most restrictive checks run first.
"""

from __future__ import annotations

import aiosqlite
from discord.ext import commands

from utils import feature_flags as flags
from utils.config import OWNER_IDS


class FeatureBlocked(commands.CheckFailure):
    """Raised when a global feature flag blocks a command."""

    def __init__(self, reason: str, flag_key: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.flag_key = flag_key


# ── Blacklist lookup ──────────────────────────────────────────────────────
# Cached because global_blacklist_sync runs on every command invocation.

_blacklist_users: set[int] = set()
_blacklist_guilds: set[int] = set()
_blacklist_loaded = False


async def refresh_blacklist() -> None:
    """Reload the global blacklist into memory."""
    global _blacklist_loaded

    users: set[int] = set()
    guilds: set[int] = set()
    try:
        async with aiosqlite.connect("db/block.db") as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT PRIMARY KEY)"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)"
            )
            await db.commit()

            async with db.execute("SELECT user_id FROM user_blacklist") as cursor:
                async for row in cursor:
                    try:
                        users.add(int(row[0]))
                    except (TypeError, ValueError):
                        continue

            async with db.execute("SELECT guild_id FROM guild_blacklist") as cursor:
                async for row in cursor:
                    try:
                        guilds.add(int(row[0]))
                    except (TypeError, ValueError):
                        continue
    except Exception as exc:
        print(f"[feature_gates] blacklist refresh failed: {exc}")
        return

    _blacklist_users.clear()
    _blacklist_users.update(users)
    _blacklist_guilds.clear()
    _blacklist_guilds.update(guilds)
    _blacklist_loaded = True


def invalidate_blacklist() -> None:
    global _blacklist_loaded
    _blacklist_loaded = False


# ── Premium / beta registries ─────────────────────────────────────────────
# Commands opt in by name; the flags decide whether the restriction applies.

PREMIUM_COMMANDS: set[str] = set()
BETA_COMMANDS: set[str] = set()
_premium_guilds: set[int] = set()


async def refresh_premium_guilds() -> None:
    """Load the premium guild allowlist (table is optional)."""
    guilds: set[int] = set()
    try:
        async with aiosqlite.connect("db/admin_config.db") as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS premium_guilds ("
                " guild_id INTEGER PRIMARY KEY, granted_at INTEGER)"
            )
            await db.commit()
            async with db.execute("SELECT guild_id FROM premium_guilds") as cursor:
                async for row in cursor:
                    guilds.add(int(row[0]))
    except Exception as exc:
        print(f"[feature_gates] premium refresh failed: {exc}")
        return

    _premium_guilds.clear()
    _premium_guilds.update(guilds)


def is_premium_guild(guild_id: int | None) -> bool:
    return guild_id is not None and int(guild_id) in _premium_guilds


# ── The global check ──────────────────────────────────────────────────────


def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


async def global_feature_check(ctx: commands.Context) -> bool:
    """
    Bot-wide command gate.

    Returns True to allow the command, raises FeatureBlocked to reject it with
    a message the error handler can show.
    """
    author_id = ctx.author.id
    guild_id = ctx.guild.id if ctx.guild else None

    # Owners bypass every global restriction so the bot stays recoverable.
    if is_owner(author_id):
        return True

    if flags.is_enabled("global_emergency_lockdown"):
        raise FeatureBlocked(
            "The bot is in emergency lockdown. Only the bot owners can run commands right now.",
            "global_emergency_lockdown",
        )

    if flags.is_enabled("global_command_freeze"):
        raise FeatureBlocked(
            "Commands are temporarily frozen while maintenance is in progress.",
            "global_command_freeze",
        )

    if flags.is_enabled("owner_only_mode"):
        raise FeatureBlocked(
            "The bot is in owner-only mode.",
            "owner_only_mode",
        )

    if flags.is_enabled("global_blacklist_sync"):
        if not _blacklist_loaded:
            await refresh_blacklist()
        if author_id in _blacklist_users:
            raise FeatureBlocked("You are blacklisted from using this bot.", "global_blacklist_sync")
        if guild_id is not None and guild_id in _blacklist_guilds:
            raise FeatureBlocked("This server is blacklisted from using this bot.", "global_blacklist_sync")

    command_name = ctx.command.qualified_name if ctx.command else ""

    if command_name in PREMIUM_COMMANDS and flags.is_enabled("premium_access_control"):
        if not is_premium_guild(guild_id):
            raise FeatureBlocked(
                "This is a premium command and this server does not have premium.",
                "premium_access_control",
            )

    if command_name in BETA_COMMANDS and not flags.is_enabled("beta_module_access"):
        raise FeatureBlocked(
            "This command is currently in closed beta.",
            "beta_module_access",
        )

    return True


def setup_gates(bot) -> None:
    """Attach the global check to the bot."""
    bot.add_check(global_feature_check)
