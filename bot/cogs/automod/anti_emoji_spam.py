# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import re

import aiosqlite
import discord
from discord.ext import commands, tasks

from utils import automod_store as store

CUSTOM_EMOJI = re.compile(r"<a?:\w+:\d+>")

# The blocks Discord actually renders as emoji. A plain "is this
# non-ASCII" check counted every accented letter, so a German sentence
# tripped the rule.
UNICODE_EMOJI_RANGES = frozenset(
    chr(c)
    for start, end in (
        (0x1F300, 0x1F5FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF),
        (0x1F900, 0x1F9FF), (0x2600, 0x26FF), (0x2700, 0x27BF),
    )
    for c in range(start, end + 1)
)


class AntiEmojiSpam(commands.Cog):
    """
    Messages made mostly of emoji.

    All six automod modules were near-identical copies that each read
    the database themselves, which is why the same bugs appeared in all
    of them: no guard against direct messages, punishment names that did
    not match what the dashboard wrote, and `except: pass` around every
    action so a missing permission looked like the rule being off.
    """

    RULE = "emoji"

    def __init__(self, bot):
        self.bot = bot
        self.tracker = store.SpamTracker()
        self.cleanup.start()

    def cog_unload(self):
        self.cleanup.cancel()

    @tasks.loop(minutes=5)
    async def cleanup(self):
        # Without this the tracker keeps an entry for every member the
        # bot has ever seen talk.
        self.tracker.prune()

    @cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def settings(self, guild_id: int) -> dict:
        async with aiosqlite.connect(store.DB_PATH) as db:
            return await store.get_settings(db, guild_id)

    @commands.Cog.listener()
    async def on_message(self, message):
        # A direct message has no guild. Reading message.guild.id
        # straight away raised AttributeError on every DM the bot got.
        if message.guild is None or message.author.bot:
            return
        if message.webhook_id is not None:
            return

        guild = message.guild
        member = message.author

        try:
            settings = await self.settings(guild.id)
        except Exception as exc:
            print(f"automod ({self.RULE}): could not read settings: {exc}")
            return

        if not store.rule_active(settings, self.RULE):
            return

        perms = getattr(member, "guild_permissions", None)
        if store.is_exempt(
            settings,
            channel_id=message.channel.id,
            role_ids=[r.id for r in getattr(member, "roles", [])],
            is_owner=member.id == guild.owner_id,
            # Moderators were not exempt before -- only the owner -- so
            # a moderator posting a link was muted by their own bot.
            is_admin=bool(
                perms and (perms.administrator or perms.manage_messages)
            ),
        ):
            return
        if member.id == self.bot.user.id:
            return

        entry = settings["rules"][self.RULE]

        content = message.content or ""
        count = len(CUSTOM_EMOJI.findall(content))
        count += sum(1 for c in content if c in UNICODE_EMOJI_RANGES)
        if count <= entry["threshold"]:
            return

        action = await store.punish(
            self.bot, message, self.RULE, settings, "Zu viele Emojis"
        )
        if action is None:
            return

        await store.log_action(
            self.bot, message, settings, self.RULE, action, "Zu viele Emojis"
        )

        try:
            from utils.panels import Panel

            await message.channel.send(
                view=Panel(
                    "Automod",
                    f"{member.mention} — {action} ({'Zu viele Emojis'}).",
                    tone="warning",
                ),
                delete_after=15,
            )
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot):
    await bot.add_cog(AntiEmojiSpam(bot))
