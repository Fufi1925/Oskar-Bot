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

import aiosqlite
import discord
from discord.ext import commands, tasks

from utils import automod_store as store


class AntiSpam(commands.Cog):
    """
    Too many messages in a short window.

    All six automod modules were near-identical copies that each read
    the database themselves, which is why the same bugs appeared in all
    of them: no guard against direct messages, punishment names that did
    not match what the dashboard wrote, and `except: pass` around every
    action so a missing permission looked like the rule being off.
    """

    RULE = "spam"

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

        # Counted per (guild, member): the old dict was keyed on the
        # member alone, so three messages here plus three on another
        # server the bot shares tripped a five-message threshold.
        count = self.tracker.hit(
            guild.id, member.id, window=entry["window"]
        )
        if count <= entry["threshold"]:
            return
        self.tracker.clear(guild.id, member.id)

        action = await store.punish(
            self.bot, message, self.RULE, settings, "Spam"
        )
        if action is None:
            return

        await store.log_action(
            self.bot, message, settings, self.RULE, action, "Spam"
        )

        try:
            from utils.panels import Panel

            await message.channel.send(
                view=Panel(
                    "Automod",
                    f"{member.mention} — {action} ({'Spam'}).",
                    tone="warning",
                ),
                delete_after=15,
            )
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
