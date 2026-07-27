# ╔══════════════════════════════════════════════════════════════════╗
# ║   Nightmode: close the channels on a schedule                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Closes and reopens channels at the configured hours.

The existing nightmode cog could only be switched on and off by hand,
which is not much of a *night* mode — somebody had to be awake at 23:00
and again at 07:00. This runs the schedule.

The window normally crosses midnight (23 to 7), which is exactly the
case a naive `start <= hour < end` gets wrong, so the comparison lives
in `utils/extras_store.nightmode_should_be_closed` with a test.
"""

from __future__ import annotations

import asyncio
import logging

import aiosqlite
import discord
from discord.ext import commands, tasks

from utils import db_open
from utils import extras_store as store

logger = logging.getLogger(__name__)


class NightmodeSchedule(commands.Cog):
    """Open and close channels at the configured times."""

    def __init__(self, bot):
        self.bot = bot
        self.connection: aiosqlite.Connection | None = None

    async def cog_load(self) -> None:
        self.connection = await db_open.connect(store.NIGHTMODE_DB)
        await store.nightmode_ensure(self.connection)
        self.check_schedule.start()

    async def cog_unload(self) -> None:
        self.check_schedule.cancel()
        if self.connection is not None:
            await self.connection.close()

    async def refresh(self, guild_id: int | None = None) -> None:
        """The loop reads the database each pass, so nothing to cache."""
        return

    @tasks.loop(minutes=5)
    async def check_schedule(self) -> None:
        """
        Every five minutes is enough: the switch happens on the hour and
        a few minutes of drift is not worth a tighter loop.
        """
        if self.connection is None:
            return

        try:
            schedules = await store.nightmode_all(self.connection)
        except Exception as exc:
            logger.error(f"Nightmode: could not read the schedule: {exc}")
            return

        for settings in schedules:
            try:
                await self._apply(settings)
            except Exception as exc:
                logger.error(f"Nightmode failed for {settings['guild_id']}: {exc}")

    async def _apply(self, settings: dict) -> None:
        guild = self.bot.get_guild(settings["guild_id"])
        if guild is None:
            return

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return

        hour = self._local_hour(settings.get("timezone"))
        should_close = store.nightmode_should_be_closed(settings, hour)
        currently_closed = bool(settings.get("active"))

        # Only act on the transition, not every five minutes.
        if should_close == currently_closed:
            return

        changed = 0
        for channel_id in settings["channels"]:
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                # None, not True: setting it to True would grant writing
                # to people a role had otherwise denied it to.
                overwrite.send_messages = False if should_close else None
                await channel.set_permissions(
                    guild.default_role, overwrite=overwrite,
                    reason="Nachtmodus" if should_close else "Nachtmodus beendet",
                )
                changed += 1
                # Editing a dozen channels at once trips the rate limit.
                await asyncio.sleep(0.6)
            except discord.Forbidden:
                continue
            except Exception:
                continue

        await store.nightmode_save(
            self.connection, settings["guild_id"],
            {"active": 1 if should_close else 0},
        )

        if changed:
            logger.info(
                f"Nightmode {'closed' if should_close else 'opened'} "
                f"{changed} channels in {guild.id}"
            )

    @staticmethod
    def _local_hour(timezone_name: str | None) -> int:
        """The current hour in the guild's timezone."""
        import datetime as _dt

        try:
            from zoneinfo import ZoneInfo

            return _dt.datetime.now(ZoneInfo(timezone_name or "Europe/Berlin")).hour
        except Exception:
            # An unknown timezone must not stop the schedule entirely.
            return _dt.datetime.now(_dt.timezone.utc).hour

    @check_schedule.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(NightmodeSchedule(bot))
