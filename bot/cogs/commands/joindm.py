# ╔══════════════════════════════════════════════════════════════════╗
# ║   Join DM                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
A private message for people who join the server.

Rewritten because the old version had two bugs that made it unreliable
in a way nobody could see from the dashboard:

  * `joindm enable` called `bot.add_listener(...)` at runtime. That is
    gone after a restart, so following every deploy the feature was off
    while the dashboard happily showed the configured text. And calling
    `enable` twice registered the listener twice — new members then got
    the same DM two or three times.
  * The message was a bare string with no placeholders, no title, no
    colour and no way to try it out.

The listener is registered once, the way every other cog does it, and
checks a stored flag. That flag is the thing that persists.
"""

from __future__ import annotations

import asyncio
import logging

import aiosqlite
import discord
from discord.ext import commands

from utils import db_open
from utils import joindm_store as store
from utils.panels import ACCENT, Panel, StatusCard
from utils.Tools import blacklist_check, ignore_check

logger = logging.getLogger(__name__)


class JoinDM(commands.Cog):
    """Send a private welcome to new members."""

    def __init__(self, bot):
        self.bot = bot
        self.connection: aiosqlite.Connection | None = None
        # Guilds with the feature on. on_member_join fires for every
        # join the bot can see; a database read per event would be
        # wasteful for something that changes once a month.
        self._enabled: set[int] = set()

    async def cog_load(self) -> None:
        self.connection = await db_open.connect(store.DB_PATH)
        await store.ensure_schema(self.connection)
        self._enabled = await store.all_enabled(self.connection)

    async def cog_unload(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def refresh(self, guild_id: int | None = None) -> None:
        """Reload the cache after a change from chat or the dashboard."""
        if self.connection is not None:
            self._enabled = await store.all_enabled(self.connection)

    # ── the listener ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Registered once at load. The old code added it at runtime,
        # which is why it vanished on restart and stacked up on repeat.
        if member.bot or self.connection is None:
            return
        if member.guild.id not in self._enabled:
            return

        try:
            settings = await store.get(self.connection, member.guild.id)
            if store.may_send(settings, member):
                return

            delay = int(settings.get("delay_seconds") or 0)
            if delay:
                await asyncio.sleep(delay)
                # They may have left again in the meantime.
                if member.guild.get_member(member.id) is None:
                    return

            view = store.build_view(settings, member, member.guild)
            try:
                await member.send(view=view)
                await store.bump(self.connection, member.guild.id, ok=True)
            except discord.Forbidden:
                # Closed DMs are the normal case, not an error.
                await store.bump(self.connection, member.guild.id, ok=False)
            except discord.HTTPException:
                await store.bump(self.connection, member.guild.id, ok=False)

        except Exception as exc:
            logger.error(f"Join DM failed in {member.guild.id}: {exc}")

    # ── commands ────────────────────────────────────────────────────

    @commands.group(name="joindm", invoke_without_command=True,
                    description="Private Willkommensnachricht.")
    @blacklist_check()
    @ignore_check()
    async def joindm(self, ctx):
        settings = await store.get(self.connection, ctx.guild.id)
        state = "an" if settings["enabled"] else "aus"

        await ctx.send(view=Panel(
            "Join-DM",
            f"**Status:** {state}\n"
            f"**Verschickt:** {settings['sent_total']}\n"
            f"**Nicht zustellbar:** {settings['failed_total']} "
            "(meist geschlossene DMs)",
            settings["message"] or "*Noch keine Nachricht eingetragen.*",
            f"`{ctx.prefix}joindm on` / `off`\n"
            f"`{ctx.prefix}joindm message <text>`\n"
            f"`{ctx.prefix}joindm test`\n\n"
            "Alles Weitere im Dashboard.",
            accent=settings["colour"] or ACCENT["brand"],
        ))

    @joindm.command(name="on", aliases=["enable"], description="Join-DM einschalten.")
    @commands.has_permissions(manage_guild=True)
    async def joindm_on(self, ctx):
        settings = await store.get(self.connection, ctx.guild.id)
        if not str(settings.get("message") or "").strip():
            return await ctx.send(view=StatusCard(
                "Erst eine Nachricht",
                f"Trag zuerst einen Text ein: `{ctx.prefix}joindm message <text>`",
                tone="warning",
            ))

        await store.save(self.connection, ctx.guild.id, {"enabled": 1})
        await self.refresh(ctx.guild.id)
        await ctx.send(view=StatusCard(
            "Eingeschaltet",
            "Neue Mitglieder bekommen ab jetzt eine private Nachricht.",
            tone="success",
        ))

    @joindm.command(name="off", aliases=["disable"], description="Join-DM ausschalten.")
    @commands.has_permissions(manage_guild=True)
    async def joindm_off(self, ctx):
        await store.save(self.connection, ctx.guild.id, {"enabled": 0})
        await self.refresh(ctx.guild.id)
        await ctx.send(view=StatusCard(
            "Ausgeschaltet", "Es werden keine Join-DMs mehr verschickt.", tone="info"
        ))

    @joindm.command(name="message", aliases=["set"], description="Text festlegen.")
    @commands.has_permissions(manage_guild=True)
    async def joindm_message(self, ctx, *, text: str):
        await store.save(self.connection, ctx.guild.id, {"message": text})
        settings = await store.get(self.connection, ctx.guild.id)

        await ctx.send(view=Panel(
            "Gespeichert",
            store.fill(text, ctx.author, ctx.guild),
            "Platzhalter: " + " ".join(f"`{{{k}}}`" for k in store.PLACEHOLDERS)
            + (f"\n\nNoch aus — einschalten mit `{ctx.prefix}joindm on`."
               if not settings["enabled"] else ""),
            accent=ACCENT["success"],
        ))

    @joindm.command(name="test", description="Sich selbst die DM schicken.")
    @commands.has_permissions(manage_guild=True)
    async def joindm_test(self, ctx):
        settings = await store.get(self.connection, ctx.guild.id)
        if not str(settings.get("message") or "").strip():
            return await ctx.send(view=StatusCard(
                "Nichts eingetragen",
                f"`{ctx.prefix}joindm message <text>` legt den Text fest.",
                tone="warning",
            ))

        try:
            await ctx.author.send(
                view=store.build_view(settings, ctx.author, ctx.guild)
            )
            await ctx.send(view=StatusCard(
                "Geschickt", "Schau in deine DMs.", tone="success"
            ))
        except discord.Forbidden:
            await ctx.send(view=StatusCard(
                "Deine DMs sind zu",
                "Ich kann dir nicht schreiben. Genau das passiert auch bei "
                "Mitgliedern, die DMs für diesen Server gesperrt haben.",
                tone="error",
            ))


async def setup(bot):
    await bot.add_cog(JoinDM(bot))
