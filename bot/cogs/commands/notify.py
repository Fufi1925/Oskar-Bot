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
YouTube notifications.

You give it a channel name, a Discord channel and a role. It pings when
that channel uploads (Shorts included) and when it goes live.

This replaces a feature that could not do either. The old one watched
the *Discord streaming status* of members: it never saw an upload, only
worked for people who happened to be on the server, and -- because the
listener queried without a guild filter -- handed every server the first
server's role and channel. On top of that it had no edge detection, so
one stream produced a ping per presence update.

No API key. `utils/youtube_watch` reads the public RSS feed for uploads
and the channel's `/live` page for broadcasts; both were verified
against real channels.

Twitch is deliberately not here. Its API refuses everything without a
registered client id and secret (verified: HTTP 401), so a Twitch tab
without those would be a box that does nothing.
"""

import asyncio
import traceback

import aiohttp
import aiosqlite
import discord
from discord.ext import commands, tasks

from utils.Tools import *
from utils.cv2 import CV2
from utils import extras_store as store
from utils import youtube_watch as yt

# YouTube's feed updates within a few minutes of an upload. Polling
# faster than this buys nothing and multiplies the requests by the
# number of subscriptions.
POLL_MINUTES = 5


class NotifCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = store.NOTIFY_DB
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await store.yt_ensure(db)
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── the poller ───────────────────────────────────────────────

    @tasks.loop(minutes=POLL_MINUTES)
    async def poll(self):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await store.yt_ensure(db)
                subs = await store.yt_all(db)

                # One fetch per channel even if several guilds watch it.
                by_channel: dict[str, list[dict]] = {}
                for sub in subs:
                    by_channel.setdefault(sub["channel_id"], []).append(sub)

                session = await self.session()
                for channel_id, watchers in by_channel.items():
                    try:
                        await self._check(db, session, channel_id, watchers)
                    except Exception:
                        # One broken channel must not stop the others.
                        print(f"[notify] {channel_id} failed:")
                        traceback.print_exc()
                    await asyncio.sleep(1)
        except Exception:
            print("[notify] poll failed:")
            traceback.print_exc()

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    async def _check(self, db, session, channel_id, watchers):
        wants_upload = any(w["on_upload"] for w in watchers)
        wants_live = any(w["on_live"] for w in watchers)

        newest = None
        if wants_upload:
            videos = await yt.latest_videos(session, channel_id)
            newest = videos[0] if videos else None

        live = await yt.live_now(session, channel_id) if wants_live else None

        for sub in watchers:
            guild = self.bot.get_guild(sub["guild_id"])
            if guild is None:
                continue

            if sub["on_upload"] and newest is not None:
                # A live broadcast also shows up in the feed. Announcing
                # it as an upload as well would mean two pings for one
                # thing.
                same_as_live = live is not None and live.id == newest.id
                if newest.id != sub["last_video"] and not same_as_live:
                    # The id is written first: if the send fails, the
                    # video still counts as seen rather than being
                    # retried every five minutes forever.
                    await store.yt_update(
                        db, sub["guild_id"], channel_id,
                        {"last_video": newest.id},
                    )
                    await self._announce(guild, sub, newest, kind="upload")

            if sub["on_live"] and live is not None:
                if live.id != sub["last_live"]:
                    await store.yt_update(
                        db, sub["guild_id"], channel_id,
                        {"last_live": live.id},
                    )
                    await self._announce(guild, sub, live, kind="live")

    async def _announce(self, guild, sub, video, *, kind: str):
        channel = guild.get_channel(sub["post_channel"])
        if channel is None:
            return

        me = guild.me
        if me is None or not channel.permissions_for(me).send_messages:
            return

        role = guild.get_role(sub["role_id"]) if sub["role_id"] else None
        name = sub["title"] or sub["handle"]

        if kind == "live":
            embed = discord.Embed(
                title=f"{name} ist live!",
                description=video.title,
                url=video.url,
                colour=0xFF0000,
            )
        else:
            embed = discord.Embed(
                title=f"Neues Video von {name}",
                description=video.title,
                url=video.url,
                colour=0xFF0000,
            )
        embed.set_image(url=f"https://i.ytimg.com/vi/{video.id}/hqdefault.jpg")

        try:
            await channel.send(
                content=role.mention if role else None,
                embed=embed,
                # Explicit, so a role that happens to be @everyone
                # cannot ping the whole server on every upload.
                allowed_mentions=discord.AllowedMentions(
                    roles=[role] if role else [], everyone=False, users=False
                ),
            )
        except discord.Forbidden:
            return
        except discord.HTTPException as err:
            print(f"[notify] Discord refused the announcement: {err}")

    # ── commands ─────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def setnotif(self, ctx):
        prefix = ctx.prefix
        await ctx.send(view=CV2(
            "YouTube-Benachrichtigungen",
            "Der Bot meldet neue Videos, Shorts und Livestreams eines "
            f"YouTube-Kanals — höchstens {store.YT_MAX_PER_GUILD} Kanäle "
            "pro Server.",
            f"**Befehle**\n"
            f"> `{prefix}setnotif add @KanalName #kanal @Rolle`\n"
            f"> `{prefix}setnotif list`\n"
            f"> `{prefix}setnotif remove @KanalName`",
        ))

    @setnotif.command(name="add")
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def add(
        self, ctx, name: str,
        channel: discord.TextChannel, role: discord.Role = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await store.yt_ensure(db)
            if await store.yt_count(db, ctx.guild.id) >= store.YT_MAX_PER_GUILD:
                return await ctx.reply(view=CV2(
                    "Zu viele",
                    f"Höchstens {store.YT_MAX_PER_GUILD} Kanäle pro Server. "
                    "Entferne erst einen.",
                ))

            if not channel.permissions_for(ctx.guild.me).send_messages:
                return await ctx.reply(view=CV2(
                    "Geht so nicht",
                    f"Ich darf in {channel.mention} nicht schreiben.",
                ))

            session = await self.session()
            try:
                found = await yt.resolve(session, name)
            except yt.LookupError_ as err:
                return await ctx.reply(view=CV2("Nicht gefunden", str(err)))

            # Seed with what is newest right now, so adding a channel
            # does not immediately announce its last upload as new.
            videos = await yt.latest_videos(session, found.id)
            live = await yt.live_now(session, found.id)

            await store.yt_add(
                db, ctx.guild.id,
                channel_id=found.id, handle=found.handle, title=found.title,
                post_channel=channel.id, role_id=role.id if role else None,
                last_video=videos[0].id if videos else None,
                last_live=live.id if live else None,
            )

        await ctx.reply(view=CV2(
            "Eingerichtet",
            f"**{found.title}** wird beobachtet.\n"
            f"Meldungen gehen in {channel.mention}"
            + (f" und pingen {role.mention}." if role else " (ohne Ping)."),
            "Neue Videos, Shorts und Livestreams werden gemeldet — "
            "was jetzt schon online ist, nicht.",
        ))

    @setnotif.command(name="list")
    @commands.guild_only()
    async def list_(self, ctx):
        async with aiosqlite.connect(self.db_path) as db:
            await store.yt_ensure(db)
            subs = await store.yt_list(db, ctx.guild.id)

        if not subs:
            return await ctx.reply(view=CV2(
                "YouTube-Benachrichtigungen",
                "Für diesen Server ist nichts eingerichtet.",
            ))

        lines = []
        for sub in subs:
            channel = ctx.guild.get_channel(sub["post_channel"])
            role = ctx.guild.get_role(sub["role_id"]) if sub["role_id"] else None
            events = []
            if sub["on_upload"]:
                events.append("Videos")
            if sub["on_live"]:
                events.append("Live")
            lines.append(
                f"**{sub['title'] or sub['handle']}**\n"
                f"> {' + '.join(events) or 'nichts aktiv'} → "
                f"{channel.mention if channel else 'Kanal gelöscht'}"
                + (f" · {role.mention}" if role else "")
            )

        await ctx.reply(view=CV2("YouTube-Benachrichtigungen", *lines))

    @setnotif.command(name="remove")
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await store.yt_ensure(db)
            subs = await store.yt_list(db, ctx.guild.id)

            needle = (name or "").strip().lstrip("@").lower()
            match = next(
                (
                    s for s in subs
                    if s["channel_id"].lower() == needle
                    or (s["handle"] or "").lstrip("@").lower() == needle
                    or (s["title"] or "").lower() == needle
                ),
                None,
            )
            if match is None:
                return await ctx.reply(view=CV2(
                    "Nicht gefunden",
                    f"„{name}“ steht nicht auf der Liste. "
                    f"`{ctx.prefix}setnotif list` zeigt sie.",
                ))

            await store.yt_remove(db, ctx.guild.id, match["channel_id"])

        await ctx.reply(view=CV2(
            "Entfernt", f"**{match['title'] or match['handle']}** wird nicht mehr beobachtet."
        ))
