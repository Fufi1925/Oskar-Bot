# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Live notifications.

Rewritten. Four things were wrong with the old version, all of them
reproduced before the rewrite:

  * **Every server shared one setting.** The listener ran
    ``SELECT role_id, channel_id FROM notifications WHERE type = ?``
    with no guild in it. The dashboard had already migrated the table to
    be per-guild, but the listener never learnt: whichever row SQLite
    returned first was used for *every* server, so server B pinged
    server A's role in a channel it cannot even see.

  * **The chat commands were broken outright.** The migration added
    ``guild_id NOT NULL``; the commands still inserted without it, so
    ``>setnotif youtube`` died with an IntegrityError. ``list`` and
    ``reset`` were worse than broken -- they read and deleted rows
    belonging to other servers.

  * **It announced the same stream over and over.** ``before`` was
    accepted and never looked at, so there was no edge detection.
    Discord sends a presence update for any change at all while
    somebody is live, and each one posted a fresh ping.

  * **It never noticed a stream ending**, so nothing could ever be
    cleaned up or reported.

What it actually does is worth being precise about, because the old
dashboard tab was not: this watches the **Discord streaming status** of
members of this server. It is not a YouTube or Twitch subscription --
nothing here polls either site, so an upload by somebody who is not in
the server, or not streaming through Discord, will never be seen.
"""

import time

import aiosqlite
import discord
from discord.ext import commands

from utils.Tools import *
from utils.cv2 import CV2
from utils import extras_store as store

# How long the same person + platform stays quiet after an announcement.
# A stream that drops and reconnects should not ping twice; a genuinely
# new stream hours later should.
REANNOUNCE_AFTER = 6 * 60 * 60

# Entries older than this are dropped from the in-memory record so a
# long-running bot does not grow one entry per member forever.
FORGET_AFTER = 24 * 60 * 60


class NotifCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = store.NOTIFY_DB
        # (guild_id, user_id, platform) -> when it was last announced.
        self._announced: dict[tuple[int, int, str], float] = {}

    async def cog_load(self):
        """
        Let the shared store own the schema.

        The cog used to CREATE TABLE with the old `type TEXT UNIQUE`
        shape. On a fresh database whichever ran first won, and if that
        was the cog the dashboard's migration had to rebuild the table
        underneath it.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await store.notify_ensure(db)

    # ── helpers ──────────────────────────────────────────────────

    def _forget_old(self, now: float) -> None:
        stale = [k for k, seen in self._announced.items() if now - seen > FORGET_AFTER]
        for key in stale:
            del self._announced[key]

    @staticmethod
    def _platform(activity: discord.Streaming) -> str | None:
        """Which platform a Discord streaming status points at."""
        url = (activity.url or "").lower()
        if "twitch.tv" in url:
            return "twitch"
        if "youtube.com" in url or "youtu.be" in url:
            return "youtube"
        return None

    @staticmethod
    def _streaming(member) -> discord.Streaming | None:
        for activity in getattr(member, "activities", ()) or ():
            if isinstance(activity, discord.Streaming):
                return activity
        return None

    # ── commands ─────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def setnotif(self, ctx):
        prefix = ctx.prefix
        await ctx.send(view=CV2(
            "Live-Benachrichtigungen",
            "Pingt eine Rolle, sobald jemand **auf diesem Server** einen "
            "Stream in seinem Discord-Status hat.\n\n"
            "Das ist kein YouTube-Abo: Uploads von Leuten, die nicht hier "
            "sind, werden nicht bemerkt.",
            f"**Befehle**\n"
            f"> `{prefix}setnotif twitch @Rolle #kanal`\n"
            f"> `{prefix}setnotif youtube @Rolle #kanal`\n"
            f"> `{prefix}setnotif list`\n"
            f"> `{prefix}setnotif reset`",
        ))

    async def _set(self, ctx, kind: str, role: discord.Role, channel):
        me = ctx.guild.me
        problems = []
        if not channel.permissions_for(me).send_messages:
            problems.append(f"Ich darf in {channel.mention} nicht schreiben.")
        if not role.is_assignable() and role.is_default():
            problems.append("@everyone lässt sich nicht als Ping-Rolle nutzen.")
        if problems:
            return await ctx.reply(view=CV2("Geht so nicht", *problems))

        async with aiosqlite.connect(self.db_path) as db:
            await store.notify_ensure(db)
            await store.notify_set(db, ctx.guild.id, kind, role.id, channel.id)

        await ctx.reply(view=CV2(
            "Gespeichert",
            f"{kind.capitalize()}: {role.mention} wird in {channel.mention} "
            "gepingt, sobald jemand hier live geht.",
        ))

    @setnotif.command()
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def twitch(self, ctx, role: discord.Role, channel: discord.TextChannel):
        # Overwrites instead of refusing. The old version told you to
        # remove it first, which meant three commands to change a channel.
        await self._set(ctx, "twitch", role, channel)

    @setnotif.command()
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def youtube(self, ctx, role: discord.Role, channel: discord.TextChannel):
        await self._set(ctx, "youtube", role, channel)

    @setnotif.command(name="list")
    @commands.guild_only()
    async def list_(self, ctx):
        async with aiosqlite.connect(self.db_path) as db:
            await store.notify_ensure(db)
            rows = await store.notify_list(db, ctx.guild.id)

        if not rows:
            return await ctx.reply(view=CV2(
                "Live-Benachrichtigungen", "Für diesen Server ist nichts eingerichtet."
            ))

        lines = []
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            channel = ctx.guild.get_channel(row["channel_id"])
            state = (
                f"{role.mention} in {channel.mention}"
                if role and channel
                else "Rolle oder Kanal gelöscht"
            )
            lines.append(f"**{row['type'].capitalize()}**\n> {state}")

        await ctx.reply(view=CV2("Live-Benachrichtigungen", *lines))

    @setnotif.command()
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        # Scoped to this guild. The old one deleted every server's rows.
        async with aiosqlite.connect(self.db_path) as db:
            await store.notify_ensure(db)
            removed = 0
            for kind in store.NOTIFY_TYPES:
                if await store.notify_remove(db, ctx.guild.id, kind):
                    removed += 1

        await ctx.send(view=CV2(
            "Zurückgesetzt",
            f"{removed} Einstellung(en) für diesen Server entfernt."
            if removed else "Es war nichts eingerichtet.",
        ))

    # ── listener ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Announce once when somebody starts streaming."""
        guild = getattr(after, "guild", None)
        if guild is None or getattr(after, "bot", False):
            return

        activity = self._streaming(after)
        if activity is None:
            # Stream ended: let them be announced again next time.
            was = self._streaming(before)
            if was is not None:
                platform = self._platform(was)
                if platform:
                    self._announced.pop((guild.id, after.id, platform), None)
            return

        platform = self._platform(activity)
        if platform is None:
            return

        # Edge detection. Discord sends a presence update for any change
        # while somebody is live -- game, status, avatar -- and the old
        # version posted a fresh ping for every one of them.
        previous = self._streaming(before)
        if previous is not None and self._platform(previous) == platform:
            return

        now = time.time()
        self._forget_old(now)
        key = (guild.id, after.id, platform)
        last = self._announced.get(key)
        if last is not None and now - last < REANNOUNCE_AFTER:
            return

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await store.notify_ensure(db)
                row = await store.notify_get(db, guild.id, platform)
        except Exception as err:
            print(f"[notify] could not read the settings: {err}")
            return

        if not row:
            return

        role = guild.get_role(row["role_id"])
        channel = guild.get_channel(row["channel_id"])
        if role is None or channel is None:
            return

        me = guild.me
        if me is None or not channel.permissions_for(me).send_messages:
            return

        embed = discord.Embed(
            title=f"{after.display_name} ist live!",
            description=f"{after.mention} streamt gerade auf {platform.capitalize()}.",
            colour=0x9146FF if platform == "twitch" else 0xFF0000,
        )
        if activity.name:
            embed.add_field(name="Titel", value=activity.name[:1024], inline=False)
        if activity.url:
            embed.add_field(name="Zuschauen", value=activity.url, inline=False)
        avatar = getattr(after, "display_avatar", None)
        if avatar is not None:
            embed.set_thumbnail(url=avatar.url)

        try:
            await channel.send(
                content=role.mention,
                embed=embed,
                # Without this an @everyone ping role would ping everyone
                # on every stream.
                allowed_mentions=discord.AllowedMentions(
                    roles=[role], everyone=False, users=False
                ),
            )
        except discord.Forbidden:
            return
        except discord.HTTPException as err:
            print(f"[notify] Discord refused the announcement: {err}")
            return

        # Only remember it once it actually went out, so a failed send
        # is retried rather than silently swallowed for six hours.
        self._announced[key] = now
