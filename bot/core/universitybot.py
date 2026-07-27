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

from __future__ import annotations
from discord.ext import commands, tasks
import discord
import aiohttp
import json
import jishaku
import asyncio
import random
import typing
from typing import List
import aiosqlite
from utils.config import OWNER_IDS, BotName
from utils import getConfig, updateConfig
from .Context import Context
from colorama import Fore, Style, init
import importlib
import inspect

init(autoreset=True)

# Corrected the extensions list
extensions: List[str] = [
    "cogs"
]

class universitybot(commands.AutoShardedBot):
    def __init__(self, *arg, **kwargs):
        intents = discord.Intents.all()
        intents.presences = True
        intents.members = True
        super().__init__(command_prefix=self.get_prefix,
                         case_insensitive=True,
                         intents=intents,
                         # The status is already set to Do Not Disturb here
                         status=discord.Status.do_not_disturb,
                         strip_after_prefix=True,
                         owner_ids=OWNER_IDS,
                         allowed_mentions=discord.AllowedMentions(
                             everyone=False, replied_user=False, roles=False),
                         sync_commands_debug=True,
                         sync_commands=True,
                         shard_count=1)
        self.status_index = 0
        self.status_list = []
        # No-prefix caches, populated by _load_no_prefix_state().
        self._np_users: set[int] = set()
        self._np_roles: set[tuple[int, int]] = set()
        self._np_loaded = False

    async def setup_hook(self):
        # Global admin feature flags must be available before the first command
        # or listener runs, otherwise the safety gates would be bypassed during
        # startup.
        from utils import feature_flags
        from utils import feature_gates
        from utils import bot_settings
        from utils.feature_services import FeatureServices, start_deadlock_watchdog

        await bot_settings.load()
        await feature_flags.load()
        feature_gates.setup_gates(self)

        # Per-guild behaviour settings (disabled commands, cooldowns,
        # moderation guards) are enforced by their own global check.
        from cogs.events.guild_settings_enforcement import guild_settings_check
        self.add_check(guild_settings_check)
        await feature_gates.refresh_blacklist()
        await feature_gates.refresh_premium_guilds()

        await self.load_extensions()
        await self._load_no_prefix_state()

        self.feature_services = FeatureServices(self)
        self.feature_services.record_expected_extensions(extensions)
        self.feature_services.start()
        start_deadlock_watchdog()

        self.status_task.start()
        self.np_refresh_task.start()

    async def load_extensions(self):
        from utils.feature_services import runtime

        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(Fore.GREEN + Style.BRIGHT + f"Loaded extension: {extension}")
            except Exception as e:
                print(f"{Fore.RED}{Style.BRIGHT}Failed to load extension {extension}. {e}")
                # Remembered so module_load_guard can report it and
                # cog_auto_recovery can retry the load later.
                if extension not in runtime.failed_extensions:
                    runtime.failed_extensions.append(extension)
        print(Fore.GREEN + Style.BRIGHT + "*" * 20)

    # Discord allows 5 presence updates per 60 seconds per session, so the
    # hard floor is one every 12 seconds. 15s keeps a safety margin while
    # still feeling lively — the old 30s made the status look frozen.
    @tasks.loop(seconds=15)
    async def status_task(self):
        await self.wait_until_ready()
        if not self.guilds:
            return

        guild = self.guilds[0]  # Use first available guild for prefix
        try:
            config = await getConfig(guild.id)
            prefix = config.get("prefix", ">")
        except Exception:
            prefix = ">"

        user_count = sum(g.member_count or 0 for g in self.guilds)
        guild_count = len(self.guilds)
        channel_count = sum(len(g.channels) for g in self.guilds)
        shard_count = self.shard_count or 1
        latency_ms = round(self.latency * 1000) if self.latency else 0

        P = discord.ActivityType.playing
        W = discord.ActivityType.watching
        L = discord.ActivityType.listening
        C = discord.ActivityType.competing

        # Emoji live in the activity name; Discord renders them fine there.
        # Entries are (type, text) and are shuffled once per full cycle so
        # the sequence is not identical every time round.
        self.status_list = [
            (P, f"🛡️ {prefix}help │ Server-Schutz"),
            (W, f"👥 {user_count:,} Mitglieder".replace(",", ".")),
            (W, f"🌍 {guild_count} Server"),
            (W, f"💬 {channel_count:,} Kanäle".replace(",", ".")),
            (L, "🚨 Anti-Nuke läuft"),
            (P, f"⚡ {BotName}"),
            (W, f"📊 {prefix}stats"),
            (L, "🎵 deiner Musik"),
            (P, "🎮 12 Spiele │ /games"),
            (W, "🎫 Tickets & Support"),
            (P, "🔐 Verifizierung aktiv"),
            (W, f"📈 Level & XP │ {prefix}rank"),
            (C, "🏆 dem Leaderboard"),
            (L, "🤖 Automod filtert mit"),
            (W, f"🛰️ {shard_count} Shard{'s' if shard_count != 1 else ''} │ {latency_ms}ms"),
            (P, "🎉 Giveaways am Laufen"),
            (W, "🔎 Logs & Audit-Trail"),
            (P, f"⚙️ Dashboard │ {prefix}dashboard"),
        ]

        # Reshuffle whenever a full pass is done, so the order varies.
        if self.status_index % len(self.status_list) == 0:
            random.shuffle(self.status_list)

        current = self.status_list[self.status_index % len(self.status_list)]
        # This task only changes the activity, not the online status (dnd, idle, etc.)
        try:
            await self.change_presence(
                activity=discord.Activity(type=current[0], name=current[1])
            )
        except discord.HTTPException:
            # A rate limited presence update is not worth crashing the loop
            # over; the next tick simply tries again.
            pass
        self.status_index += 1

    async def send_raw(self, channel_id: int, content: str, **kwargs) -> typing.Optional[discord.Message]:
        await self.http.send_message(channel_id, content, **kwargs)

    async def invoke_help_command(self, ctx: Context) -> None:
        return await ctx.send_help(ctx.command)

    async def fetch_message_by_channel(self, channel: discord.TextChannel, messageID: int) -> typing.Optional[discord.Message]:
        async for msg in channel.history(limit=1, before=discord.Object(messageID + 1), after=discord.Object(messageID - 1)):
            return msg

    async def _load_no_prefix_state(self):
        """
        Load the no-prefix allowlist into memory.

        get_prefix() runs on every single message. Querying db/np.db twice per
        message (once for users, once for roles) meant opening the database
        file several thousand times a minute on an active bot. The tables are
        tiny and change rarely, so they are cached and refreshed periodically.
        """
        users: set[int] = set()
        roles: set[tuple[int, int]] = set()

        try:
            async with aiosqlite.connect('db/np.db') as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS np (
                        id INTEGER PRIMARY KEY
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS np_roles (
                        guild_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        PRIMARY KEY (guild_id, role_id)
                    )
                ''')
                await db.commit()

                async with db.execute("SELECT id FROM np") as cursor:
                    users = {int(row[0]) async for row in cursor}

                async with db.execute("SELECT guild_id, role_id FROM np_roles") as cursor:
                    roles = {(int(row[0]), int(row[1])) async for row in cursor}
        except Exception as exc:
            print(f"No-prefix cache refresh failed: {exc}")
            return

        self._np_users = users
        self._np_roles = roles
        self._np_loaded = True

    def invalidate_no_prefix_cache(self):
        """Force the next get_prefix() call to reload the no-prefix tables."""
        self._np_loaded = False

    @tasks.loop(seconds=60)
    async def np_refresh_task(self):
        await self._load_no_prefix_state()

    async def _is_no_prefix(self, message: discord.Message) -> bool:
        if not self._np_loaded:
            await self._load_no_prefix_state()

        if message.author.id in self._np_users:
            return True

        if message.guild is None or not self._np_roles:
            return False

        guild_id = message.guild.id
        return any(
            (guild_id, role.id) in self._np_roles
            for role in getattr(message.author, 'roles', [])
        )

    async def get_prefix(self, message: discord.Message):
        no_prefix = await self._is_no_prefix(message)

        if message.guild:
            data = await getConfig(message.guild.id)
            prefix = data["prefix"]
            if no_prefix:
                return commands.when_mentioned_or(prefix, '')(self, message)
            return commands.when_mentioned_or(prefix)(self, message)

        if no_prefix:
            return commands.when_mentioned_or('?', '')(self, message)
        return commands.when_mentioned_or('')(self, message)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild and self.user and self.user in message.mentions and message.content.strip() in {self.user.mention, f"<@!{self.user.id}>"}:
            try:
                enabled = True
                async with aiosqlite.connect('db/settings.db') as db:
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS guild_extra_settings (
                            guild_id INTEGER PRIMARY KEY,
                            delete_command_messages INTEGER DEFAULT 0,
                            mention_prefix_response INTEGER DEFAULT 1,
                            same_voice_only INTEGER DEFAULT 1
                        )
                    ''')
                    async with db.execute("SELECT mention_prefix_response FROM guild_extra_settings WHERE guild_id = ?", (message.guild.id,)) as cursor:
                        row = await cursor.fetchone()
                        if row is not None:
                            enabled = bool(row[0])
                if enabled:
                    config = await getConfig(message.guild.id)
                    await message.channel.send(f"My prefix here is `{config.get('prefix', '>')}`")
            except Exception:
                pass
        await self.process_commands(message)

    async def on_message_edit(self, before, after):
        ctx: Context = await self.get_context(after, cls=Context)
        if before.content != after.content:
            if after.guild is None or after.author.bot:
                return
            if ctx.command is None:
                return
            if type(ctx.channel) == "public_thread":
                return
            await self.invoke(ctx)

def setup_bot():
    intents = discord.Intents.all()
    bot = universitybot(intents=intents)
    return bot
