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
Hand a wrecked server over to the template bot.

The owner clicks "Server wiederherstellen" on the anti-nuke panel, which
is an ordinary OAuth invite — Discord has no way for one bot to add
another. Once the template bot has actually joined, somebody still has
to type its start command, and after a nuke the owner is busy staring at
an empty server.

So this bot types it. The sequence:

  1. an attack happens; nuke_alert notes the guild and the channel its
     panel went to
  2. the template bot joins
  3. five seconds pass — Discord finishes setting up the member, its
     permissions resolve and its command handler comes up
  4. the trigger is sent into that same channel

Deliberately narrow: only after a real attack, only for the one known
bot id, and only once. Firing this on every bot join would mean poking a
stranger's bot with a command it never asked for.
"""

import asyncio

import discord
from discord.ext import commands

from utils import nuke_alert, partner_bot
from utils.panels import Panel


class PartnerHandoff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Guilds already handed over, so a reconnect or a duplicate join
        # event cannot send the trigger twice.
        self._done: set[int] = set()

    # ──────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────

    def _usable(self, channel, partner_member) -> bool:
        """Both bots have to be able to work in the channel."""
        if channel is None or not hasattr(channel, "send"):
            return False
        me = channel.guild.me
        if me is None:
            return False
        mine = channel.permissions_for(me)
        if not (mine.send_messages and mine.view_channel):
            return False
        if partner_member is not None:
            theirs = channel.permissions_for(partner_member)
            # No point sending a command the other bot cannot read.
            if not (theirs.view_channel and theirs.read_message_history):
                return False
        return True

    def _target_channel(self, guild, partner_member):
        """
        Where to send the trigger.

        The panel's channel first: that is where the owner clicked, and
        after a nuke it may be the only channel left standing.
        """
        attack = nuke_alert.recent_attack(guild.id)
        if attack and attack.get("channel_id"):
            channel = guild.get_channel(int(attack["channel_id"]))
            if self._usable(channel, partner_member):
                return channel

        # The backup channel is created for exactly this, and it is where
        # the owner was pointed, so it comes before the alert channel.
        for name in (nuke_alert.BACKUP_CHANNEL_NAME,
                     nuke_alert.ALERT_CHANNEL_NAME):
            for channel in guild.text_channels:
                if channel.name == name and self._usable(channel, partner_member):
                    return channel

        if self._usable(guild.system_channel, partner_member):
            return guild.system_channel

        return next(
            (c for c in guild.text_channels if self._usable(c, partner_member)),
            None,
        )

    # ──────────────────────────────────────────────────────────────
    #  The handoff
    # ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot or not partner_bot.is_partner(member):
            return

        guild = member.guild
        if guild is None or guild.id in self._done:
            return

        # Only as part of a rescue. Without this the bot would fire the
        # trigger any time the template bot is added for another reason.
        if nuke_alert.recent_attack(guild.id) is None:
            return

        self._done.add(guild.id)
        await self._hand_over(guild, member)

    async def _grant_access(self, guild, member) -> None:
        """
        Let the template bot into the backup channel.

        That channel is created hidden from @everyone so the rescue is
        not on public display during an incident -- which also hides it
        from the bot that is supposed to do the rescuing. Opening it for
        that one member keeps both properties.
        """
        channel = next(
            (c for c in guild.text_channels
             if c.name == nuke_alert.BACKUP_CHANNEL_NAME),
            None,
        )
        if channel is None:
            return
        me = guild.me
        if me is None or not channel.permissions_for(me).manage_channels:
            return
        if channel.permissions_for(member).view_channel:
            return

        try:
            await channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                reason="Anti-Nuke: Zugriff für den Wiederherstellungs-Bot",
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"partner handoff: could not open #{channel.name}: {exc}")

    async def _hand_over(self, guild, member):
        # Before picking a channel: the backup channel is hidden from
        # everyone by default, so without this it would be filtered out
        # as unusable and the rescue would happen somewhere else.
        await self._grant_access(guild, member)

        channel = self._target_channel(guild, member)
        if channel is None:
            print(f"partner handoff: no usable channel in {guild.id}")
            self._done.discard(guild.id)
            return

        # A real ping, not just a mention inside a card: some bots watch
        # for being mentioned before they accept commands, and it also
        # shows the owner that the right bot arrived.
        try:
            await channel.send(
                member.mention,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.Forbidden:
            print(f"partner handoff: cannot write to #{channel.name} in {guild.id}")
            self._done.discard(guild.id)
            return
        except discord.HTTPException:
            pass

        try:
            await channel.send(view=Panel(
                "Wiederherstellung läuft",
                f"{member.mention} ist da und legt gleich los.",
                f"Ich schicke in {int(nuke_alert.TEMPLATE_TRIGGER_DELAY)} Sekunden "
                f"`{nuke_alert.TEMPLATE_TRIGGER}` — du musst nichts tippen.",
                tone="info",
            ))
        except discord.HTTPException:
            pass

        # Discord has not finished setting the member up when the join
        # event fires: permissions are still resolving and the other
        # bot's command handler may not be listening yet.
        await asyncio.sleep(nuke_alert.TEMPLATE_TRIGGER_DELAY)

        # The channel can be gone by now — a nuke may still be running.
        channel = guild.get_channel(channel.id) or self._target_channel(guild, member)
        if channel is None:
            self._done.discard(guild.id)
            return

        try:
            await channel.send(nuke_alert.TEMPLATE_TRIGGER)
        except discord.Forbidden:
            print(f"partner handoff: cannot write to #{channel.name} in {guild.id}")
            self._done.discard(guild.id)
            return
        except discord.HTTPException as exc:
            print(f"partner handoff: Discord refused the trigger: {exc}")
            self._done.discard(guild.id)
            return

        # One rescue per attack. Leaving the mark would re-trigger if the
        # bot were kicked and re-added.
        nuke_alert.clear_attack(guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """If the template bot leaves, a later rescue may start over."""
        if partner_bot.is_partner(member) and member.guild is not None:
            self._done.discard(member.guild.id)


async def setup(bot):
    await bot.add_cog(PartnerHandoff(bot))
