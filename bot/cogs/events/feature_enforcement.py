"""
Event-driven enforcement of the global feature flags.

Covers the flags that need Discord events rather than a polling loop:
  guild_join_guard, guild_leave_audit, cache_warmup, voice_session_analytics,
  command_error_analytics, session_cookie_monitor, module_load_guard.
"""

from __future__ import annotations

import os
import time

import discord
from discord.ext import commands

from core import Cog
from utils import feature_flags as flags
from utils import feature_audit as audit
from utils import feature_gates
from utils.feature_services import runtime, record_command_error

# A guild whose membership is almost entirely bots is treated as a bot farm.
BOT_FARM_RATIO = 0.8
BOT_FARM_MIN_MEMBERS = 20


class FeatureEnforcement(Cog):
    def __init__(self, client):
        self.client = client

    # ── startup ───────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        await flags.load()

        if flags.is_enabled("cache_warmup"):
            await self._warm_caches()

        if flags.is_enabled("session_cookie_monitor"):
            self._check_session_secret()

        if flags.is_enabled("module_load_guard") and runtime.failed_extensions:
            print(
                "[feature_enforcement] Extensions failed to load: "
                + ", ".join(runtime.failed_extensions)
            )

    async def _warm_caches(self):
        """Preload the caches that the message path depends on."""
        try:
            from utils.Tools import getConfig

            loader = getattr(self.client, "_load_no_prefix_state", None)
            if callable(loader):
                await loader()

            for guild in list(self.client.guilds)[:200]:
                await getConfig(guild.id)

            await feature_gates.refresh_blacklist()
            await feature_gates.refresh_premium_guilds()
            print(f"[feature_enforcement] Cache warmup complete for {len(self.client.guilds)} guilds")
        except Exception as exc:
            print(f"[feature_enforcement] Cache warmup failed: {exc}")

    def _check_session_secret(self):
        """
        A rotating NEXTAUTH_SECRET logs every dashboard user out on restart.
        start.sh generates a random one when nothing is configured.
        """
        if os.getenv("NEXTAUTH_SECRET") or os.getenv("DASHBOARD_API_KEY"):
            runtime.session_warning = None
        else:
            runtime.session_warning = (
                "NEXTAUTH_SECRET is not set — dashboard sessions are invalidated on every restart."
            )
            print(f"[feature_enforcement] {runtime.session_warning}")

    # ── guild lifecycle ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if not flags.is_enabled("guild_join_guard"):
            return

        reason = await self._screen_guild(guild)
        if reason is None:
            return

        await audit.log_action(
            "guild_join_blocked",
            actor="guild_join_guard",
            guild_id=guild.id,
            detail=f"{guild.name}: {reason}",
        )
        try:
            await guild.leave()
            print(f"[feature_enforcement] Left {guild.name} ({guild.id}): {reason}")
        except Exception as exc:
            print(f"[feature_enforcement] Could not leave {guild.id}: {exc}")

    async def _screen_guild(self, guild: discord.Guild) -> str | None:
        """Return a reason to leave the guild, or None to stay."""
        if not feature_gates._blacklist_loaded:
            await feature_gates.refresh_blacklist()
        if guild.id in feature_gates._blacklist_guilds:
            return "guild is blacklisted"

        members = guild.member_count or len(guild.members)
        if members >= BOT_FARM_MIN_MEMBERS:
            bots = sum(1 for member in guild.members if member.bot)
            if bots and members and (bots / members) >= BOT_FARM_RATIO:
                return f"bot farm ({bots}/{members} members are bots)"
        return None

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        if not flags.is_enabled("guild_leave_audit"):
            return
        await audit.log_action(
            "guild_removed",
            actor="system",
            guild_id=guild.id,
            detail=f"Removed from {guild.name} ({guild.member_count or 0} members)",
        )

    # ── voice analytics ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not flags.is_enabled("voice_session_analytics") or member.bot:
            return

        key = f"{member.guild.id}:{member.id}"
        now = time.time()

        if before.channel is None and after.channel is not None:
            runtime.voice_sessions[key] = now
        elif before.channel is not None and after.channel is None:
            started = runtime.voice_sessions.pop(key, None)
            if started:
                runtime.voice_totals[str(member.guild.id)] += now - started

    # ── error analytics ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        record_command_error(
            ctx.command.qualified_name if ctx.command else "unknown",
            type(error).__name__,
        )

        # Give the user a clear message when a global flag blocked them.
        if isinstance(error, feature_gates.FeatureBlocked):
            try:
                await ctx.reply(f"🚫 {error.reason}", delete_after=10)
            except Exception:
                pass
            return

        # Same for the per-guild settings check.
        from cogs.events.guild_settings_enforcement import SettingsBlocked

        if isinstance(error, SettingsBlocked):
            try:
                await ctx.reply(f"⚠️ {error.reason}", delete_after=10)
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(FeatureEnforcement(bot))
