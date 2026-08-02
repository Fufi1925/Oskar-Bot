"""
Makes the per-guild settings actually do something.

Each switch in the settings tab maps to a concrete behaviour here, so nothing
in that tab is decorative.

  delete_command_messages / delete_command_delay
      remove the invoking message after a command runs
  command_cooldown
      throttle repeat commands from the same member
  disabled_commands
      reject listed commands
  require_reason_moderation
      refuse ban/kick/mute/warn without a reason
  protect_admin_roles
      refuse to punish administrators
  dm_mod_actions / mod_log_channel
      notify the member and log the action
  ignore_bots
      skip other bots in automod and leveling
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands

from core import Cog
from utils import guild_settings
from utils.panels import from_embed

MODERATION_COMMANDS = {"ban", "kick", "mute", "timeout", "warn", "softban", "tempban"}

# member_id -> last command timestamp, for command_cooldown.
_last_command: dict[int, float] = {}


class GuildSettingsEnforcement(Cog):
    def __init__(self, client):
        self.client = client

    # ── warm the cache ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in list(self.client.guilds)[:200]:
            try:
                await guild_settings.load(guild.id)
            except Exception:
                continue

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await guild_settings.load(guild.id)

    # ── before a command runs ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        """Load settings so the checks below have fresh values."""
        if ctx.guild:
            await guild_settings.load(ctx.guild.id)

    async def cog_check(self, ctx):  # pragma: no cover - defensive
        return True

    # ── after a command ran ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not guild_settings.get_bool(ctx.guild.id, "delete_command_messages"):
            return

        delay = guild_settings.get_int(ctx.guild.id, "delete_command_delay")
        try:
            if delay > 0:
                await ctx.message.delete(delay=delay)
            else:
                await ctx.message.delete()
        except Exception:
            pass

    # ── moderation side effects ───────────────────────────────────────────

    async def notify_and_log(
        self,
        guild: discord.Guild,
        member: discord.abc.User,
        action: str,
        reason: str,
        moderator: discord.abc.User | None = None,
    ) -> None:
        """
        Called by moderation code after a punishment.

        Honours dm_mod_actions and mod_log_channel.
        """
        await guild_settings.load(guild.id)

        if guild_settings.get_bool(guild.id, "dm_mod_actions"):
            try:
                await member.send(
                    f"You were **{action}** in **{guild.name}**."
                    + (f"\nReason: {reason}" if reason else "")
                )
            except Exception:
                pass

        channel_id = guild_settings.get_id(guild.id, "mod_log_channel")
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                embed = discord.Embed(
                    title=f"Member {action}",
                    description=reason or "No reason given",
                    color=0xE11D48,
                    timestamp=discord.utils.utcnow(),
                )
                embed.add_field(name="Member", value=f"{member} (`{member.id}`)", inline=False)
                if moderator:
                    embed.add_field(name="Moderator", value=str(moderator), inline=False)
                try:
                    await channel.send(view=from_embed(embed))
                except Exception:
                    pass


async def setup(bot):
    await bot.add_cog(GuildSettingsEnforcement(bot))


# ══════════════════════════════════════════════════════════════════════════
#  Global command check
# ══════════════════════════════════════════════════════════════════════════


class SettingsBlocked(commands.CheckFailure):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def guild_settings_check(ctx: commands.Context) -> bool:
    """
    Runs before every command. Registered from core/universitybot.py.
    """
    if ctx.guild is None or ctx.command is None:
        return True

    guild_id = ctx.guild.id
    name = ctx.command.qualified_name.lower()
    root = name.split()[0]

    # Disabled commands
    disabled = guild_settings.disabled_commands(guild_id)
    if disabled and (name in disabled or root in disabled):
        raise SettingsBlocked(f"`{root}` is disabled on this server.")

    author = ctx.author
    is_staff = bool(
        getattr(author, "guild_permissions", None)
        and (author.guild_permissions.manage_messages or author.guild_permissions.administrator)
    )

    # Extra cooldown, staff exempt
    cooldown = guild_settings.get_int(guild_id, "command_cooldown")
    if cooldown > 0 and not is_staff:
        now = time.monotonic()
        last = _last_command.get(author.id, 0.0)
        if now - last < cooldown:
            remaining = int(cooldown - (now - last)) + 1
            raise SettingsBlocked(f"Slow down — try again in {remaining}s.")
        _last_command[author.id] = now

        # Keep the dict from growing without bound on busy bots.
        if len(_last_command) > 5000:
            cutoff = now - 300
            for key in [k for k, v in _last_command.items() if v < cutoff]:
                _last_command.pop(key, None)

    # Moderation guards
    if root in MODERATION_COMMANDS:
        if guild_settings.get_bool(guild_id, "require_reason_moderation"):
            # Everything after the command name counts as the reason.
            trailing = (ctx.message.content or "").strip()
            invoked = f"{ctx.prefix or ''}{ctx.invoked_with or ''}"
            remainder = trailing[len(invoked):].strip() if trailing.startswith(invoked) else trailing
            words = [w for w in remainder.split() if not w.startswith(("<@", "<#", "<@&"))]
            if len(words) < 2:
                raise SettingsBlocked("This server requires a reason for moderation actions.")

        if guild_settings.get_bool(guild_id, "protect_admin_roles"):
            target = next(
                (a for a in ctx.args[2:] if isinstance(a, discord.Member)),
                None,
            ) or next(
                (v for v in ctx.kwargs.values() if isinstance(v, discord.Member)),
                None,
            )
            if target is not None and target.guild_permissions.administrator:
                raise SettingsBlocked("Administrators are protected on this server.")

    return True


def should_ignore_bots(guild_id: int) -> bool:
    """Used by automod and leveling listeners."""
    return guild_settings.get_bool(guild_id, "ignore_bots")
