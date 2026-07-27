# ╔══════════════════════════════════════════════════════════════════╗
# ║   Vanity roles                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
A role for members who put the server's invite in their Discord status.

The previous version did something else entirely despite the name: every
fifteen seconds it asked Discord whether the *invite* still existed, and
when it did, gave the role to **every member of the guild** — then took
it off everyone again if the request ever failed. A blip in the network
was enough to strip the role from the whole server.

What changed:

  * Matching runs on `on_presence_update`, so there is no polling, no
    unauthenticated HTTP call every fifteen seconds, and no new
    `aiohttp.ClientSession` per check.
  * The role goes to the member whose status contains the trigger, not
    to everybody.
  * Who received a role is recorded, so the bot only ever removes roles
    it handed out itself and leaves manual assignments alone.
  * A missing log channel or a role above the bot no longer aborts the
    run for every other guild.
"""

from __future__ import annotations

import asyncio
import logging

import aiosqlite
import discord
from discord.ext import commands

from utils import vanity_store as store
from utils.panels import ACCENT, Panel, StatusCard
from utils.Tools import blacklist_check, ignore_check

logger = logging.getLogger(__name__)


class VanityRoles(commands.Cog):
    """Give a role to members advertising the server in their status."""

    def __init__(self, bot):
        self.bot = bot
        self.connection: aiosqlite.Connection | None = None
        # guild_id -> [setup, ...]. on_presence_update fires for every
        # member of every guild; hitting the database each time would be
        # the busiest query in the bot by a wide margin.
        self._cache: dict[int, list[dict]] = {}
        self._ready = asyncio.Event()

    async def cog_load(self) -> None:
        self.connection = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(self.connection)
        self._cache = await store.all_setups(self.connection)
        self._ready.set()

    async def cog_unload(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def refresh(self, guild_id: int | None = None) -> None:
        """Reload the cache after a change from chat or the dashboard."""
        if self.connection is None:
            return
        self._cache = await store.all_setups(self.connection)

    # ── the actual matching ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_presence_update(self, before, after) -> None:
        if after.bot or after.guild is None:
            return

        setups = self._cache.get(after.guild.id)
        if not setups:
            return

        # Presence events fire for far more than status changes; skip the
        # ones where the text did not move.
        old_text = store.status_text(before)
        new_text = store.status_text(after)
        if old_text == new_text:
            return

        for setup in setups:
            try:
                await self._apply(after, setup, new_text)
            except Exception as exc:
                logger.error(f"Vanity: {setup['vanity']} in {after.guild.id}: {exc}")

    @commands.Cog.listener()
    async def on_member_join(self, member) -> None:
        """Somebody may join with the trigger already in their status."""
        if member.bot:
            return
        setups = self._cache.get(member.guild.id)
        if not setups:
            return
        text = store.status_text(member)
        for setup in setups:
            try:
                await self._apply(member, setup, text)
            except Exception:
                pass

    async def _apply(self, member, setup: dict, text: str) -> None:
        """Grant or take back one role for one member."""
        guild = member.guild
        role = guild.get_role(setup["role_id"])
        if role is None:
            return

        wanted = store.matches(setup["vanity"], text)
        held = await store.is_holder(
            self.connection, guild.id, setup["vanity"], member.id
        )

        if wanted and not held:
            if not self._can_manage(guild, role):
                return
            try:
                await member.add_roles(role, reason="Vanity im Status")
            except discord.Forbidden:
                return
            await store.add_holder(self.connection, guild.id, setup["vanity"], member.id)
            await store.bump(self.connection, guild.id, setup["vanity"], granted=1)
            await self._log(guild, setup, member, role, granted=True)

        elif not wanted and held:
            # Only ever remove what we handed out; the holder table is
            # what keeps a manually given role safe.
            if self._can_manage(guild, role) and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Vanity nicht mehr im Status")
                except discord.Forbidden:
                    pass
            await store.remove_holder(
                self.connection, guild.id, setup["vanity"], member.id
            )
            await store.bump(self.connection, guild.id, setup["vanity"], removed=1)
            await self._log(guild, setup, member, role, granted=False)

    @staticmethod
    def _can_manage(guild, role) -> bool:
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return False
        # A managed role belongs to an integration and cannot be assigned;
        # one above the bot's own top role raises Forbidden every time.
        return not role.managed and role < me.top_role

    async def _log(self, guild, setup, member, role, *, granted: bool) -> None:
        channel_id = setup.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            return
        try:
            await channel.send(view=StatusCard(
                "Vanity-Rolle vergeben" if granted else "Vanity-Rolle entfernt",
                f"{member.mention} — {role.mention}\n"
                f"Auslöser: `{setup['vanity']}`",
                tone="success" if granted else "info",
            ))
        except Exception:
            # A missing permission here used to abort the whole run.
            pass

    # ── commands ────────────────────────────────────────────────────

    @commands.group(name="vanity", aliases=["vanityroles"],
                    invoke_without_command=True,
                    description="Rolle für Werbung im Status.")
    @blacklist_check()
    @ignore_check()
    async def vanity(self, ctx):
        setups = await store.list_setups(self.connection, ctx.guild.id)
        counts = await store.holder_counts(self.connection, ctx.guild.id)

        if not setups:
            return await ctx.send(view=Panel(
                "Vanity-Rollen",
                "Mitglieder, die den Server in ihrem Discord-Status erwähnen, "
                "bekommen automatisch eine Rolle.",
                f"`{ctx.prefix}vanity add <.gg/dein-server> <@rolle> [#log]`\n"
                f"`{ctx.prefix}vanity remove <auslöser>`\n"
                f"`{ctx.prefix}vanity sync` — jetzt alle prüfen\n\n"
                "Geht auch komplett im Dashboard.",
                accent=ACCENT["brand"],
            ))

        lines = []
        for setup in setups:
            role = ctx.guild.get_role(setup["role_id"])
            lines.append(
                f"`.gg/{setup['vanity']}` → "
                + (role.mention if role else "*Rolle gelöscht*")
                + f" — **{counts.get(setup['vanity'], 0)}** Mitglieder"
                + ("" if setup["enabled"] else "  *(aus)*")
            )

        await ctx.send(view=Panel(
            "Vanity-Rollen", "\n".join(lines),
            f"`{ctx.prefix}vanity sync` prüft alle Mitglieder auf einmal.",
            accent=ACCENT["brand"],
        ))

    @vanity.command(name="add", aliases=["setup"], description="Auslöser anlegen.")
    @commands.has_permissions(manage_guild=True)
    async def vanity_add(
        self, ctx, trigger: str, role: discord.Role,
        log_channel: discord.TextChannel = None,
    ):
        code = store.normalise_trigger(trigger)
        if not code:
            return await ctx.send(view=StatusCard(
                "Kein Auslöser",
                "Gib etwas an wie `.gg/dein-server` oder den Einladungscode.",
                tone="error",
            ))

        if not self._can_manage(ctx.guild, role):
            return await ctx.send(view=StatusCard(
                "Rolle nicht vergebbar",
                f"{role.mention} steht über meiner eigenen Rolle oder wird von "
                "einer Integration verwaltet. Schieb meine Rolle darüber.",
                tone="error",
            ))

        await store.save_setup(
            self.connection, ctx.guild.id, code, role.id,
            log_channel_id=log_channel.id if log_channel else None,
        )
        await self.refresh(ctx.guild.id)

        await ctx.send(view=Panel(
            "Vanity-Rolle eingerichtet",
            f"Wer **`.gg/{code}`** in seinen Discord-Status schreibt, bekommt "
            f"{role.mention}.",
            f"Protokoll: {log_channel.mention if log_channel else '—'}\n\n"
            f"`{ctx.prefix}vanity sync` trägt die Rolle bei allen nach, die sie "
            "schon jetzt verdient hätten.",
            accent=ACCENT["success"],
        ))

    @vanity.command(name="remove", aliases=["delete"], description="Auslöser entfernen.")
    @commands.has_permissions(manage_guild=True)
    async def vanity_remove(self, ctx, trigger: str):
        if await store.delete_setup(self.connection, ctx.guild.id, trigger):
            await self.refresh(ctx.guild.id)
            await ctx.send(view=StatusCard(
                "Entfernt",
                f"`{store.normalise_trigger(trigger)}` wird nicht mehr beachtet. "
                "Bereits vergebene Rollen bleiben.",
                tone="success",
            ))
        else:
            await ctx.send(view=StatusCard(
                "Nichts gefunden", "Diesen Auslöser gibt es nicht.", tone="warning"
            ))

    @vanity.command(name="sync", description="Alle Mitglieder jetzt prüfen.")
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def vanity_sync(self, ctx):
        """
        Walk every member once.

        Needed after adding a setup, because presence events only fire on
        a *change* — somebody who already had the trigger in their status
        would otherwise wait until they next edited it.
        """
        setups = self._cache.get(ctx.guild.id) or []
        if not setups:
            return await ctx.send(view=StatusCard(
                "Nichts eingerichtet",
                f"Lege zuerst einen Auslöser an: `{ctx.prefix}vanity add`",
                tone="warning",
            ))

        notice = await ctx.send(view=StatusCard(
            "Wird geprüft", "Das kann bei großen Servern einen Moment dauern.",
            tone="info",
        ))

        changed = 0
        for index, member in enumerate(ctx.guild.members):
            if member.bot:
                continue
            text = store.status_text(member)
            for setup in setups:
                before = await store.is_holder(
                    self.connection, ctx.guild.id, setup["vanity"], member.id
                )
                try:
                    await self._apply(member, setup, text)
                except Exception:
                    continue
                after = await store.is_holder(
                    self.connection, ctx.guild.id, setup["vanity"], member.id
                )
                if before != after:
                    changed += 1

            # Role edits are rate limited per guild; a short pause every
            # so often keeps a large server from stalling the bot.
            if index % 25 == 24:
                await asyncio.sleep(1)

        try:
            await notice.edit(view=StatusCard(
                "Fertig", f"**{changed}** Änderungen vorgenommen.", tone="success"
            ))
        except Exception:
            await ctx.send(view=StatusCard(
                "Fertig", f"**{changed}** Änderungen vorgenommen.", tone="success"
            ))


async def setup(bot):
    await bot.add_cog(VanityRoles(bot))
