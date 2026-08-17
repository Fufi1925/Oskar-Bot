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

import discord
from utils import nuke_alert, partner_bot, nuke_guard
from discord.ext import commands
import aiosqlite
import asyncio
import datetime
import pytz

class AntiChannelCreate(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "channel_create"

    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}

    def can_fetch_audit(self, guild_id, event_name, max_requests=6, interval=10, cooldown_duration=300):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)

        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if len(timestamps) > max_requests:
            self.cooldowns.setdefault(guild_id, {})[event_name] = now
            return False
        return True

    async def fetch_audit_logs(self, guild, action, target_id, delay=1):
        if not guild.me.guild_permissions.ban_members:
            # Returning None here used to end the story in silence --
            # the anti-nuke could see nothing and said nothing, which
            # is the one case the owner most needs to hear about.
            await nuke_alert.handle_blind(self.bot, guild, self.ALERT_ACTION)
            return None
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                if entry.target.id == target_id:
                    now = datetime.datetime.now(pytz.utc)
                    if (now - entry.created_at).total_seconds() * 1000 >= 3600000:
                        return None
                    await asyncio.sleep(delay)
                    return entry
        except Exception:
            pass
        return None

    async def move_role_below_bot(self, guild):
        bot_top_role = guild.me.top_role
        most_populated_role = max(
            [role for role in guild.roles if role.position < bot_top_role.position and not role.managed and role != guild.default_role],
            key=lambda r: len(r.members),
            default=None
        )
        if most_populated_role:
            try:
                await most_populated_role.edit(position=bot_top_role.position - 1, reason="Emergency: Adjusting roles for security")
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

    async def delete_channel_and_ban(self, channel, executor, delay=2, retries=3):
        # The reporting helpers need the guild; this function only
        # receives the object it acts on.
        guild = channel.guild
        repaired = False
        while retries > 0:
            try:
                await channel.delete(reason="Channel created by unwhitelisted user")
                # Past this point the attack is undone. A Forbidden from
                # here on is only about the ban, which is a different
                # message -- see handle_partial(repaired=...).
                repaired = True
                await channel.guild.ban(executor, reason="Channel Create | Unwhitelisted User")
                await nuke_alert.handle_stopped(
                    self.bot, guild, "channel_create", executor=executor,
                    clean=True,
                )
                return
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "channel_create", executor=executor,
                    repaired=repaired,
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After', delay)
                    await asyncio.sleep(float(retry_after))
                    retries -= 1
            except Exception:
                return

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        # The bot deletes channels itself when cleaning up after an
        # attacker. Without this it can walk into its own repair work
        # and flag it as a nuke.
        if nuke_alert.is_self_action(
            channel.guild.id, getattr(channel, "id", None)
        ):
            return

        guild = channel.guild

        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()
            if not antinuke_status or not antinuke_status[0]:
                return

            # Und laeuft DIESE Wache? Die vierzehn Bereiche lassen
            # sich einzeln abschalten -- fehlt die Zeile, gilt AN.
            if not await nuke_guard.action_enabled(guild.id, "chcr"):
                return

            if not self.can_fetch_audit(guild.id, "channel_create"):
                await self.move_role_below_bot(guild)
                await asyncio.sleep(5)

            logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_create, channel.id, delay=2)
            if logs is None:
                return

            executor = logs.user
            # Aussteigen, wenn der Bot nicht darf ODER nicht kann.
            #
            # Frueher stand hier nur die Freigabe-Liste (Inhaber,
            # eigener Bot, Partner-Bot). Was fehlte: die Frage, ob die
            # eigene Rolle ueberhaupt ueber der des Angreifers steht.
            # Stand sie darunter, lief der Bot in den Ban, bekam ein
            # Forbidden und meldete das -- bei einem Angriff mit vierzig
            # Kanaelen vierzigmal. Jetzt: nichts tun, nichts melden.
            #
            # `TRUSTED_BOTS` ist hier ebenfalls abgedeckt.
            if nuke_guard.should_skip(guild, executor, self.bot.user.id):
                return

            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", (guild.id, executor.id)) as cursor:
                if await cursor.fetchone():
                    return

            async with db.execute("SELECT chcr FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()
            if whitelist_status and whitelist_status[0]:
                return

            await self.delete_channel_and_ban(channel, executor, delay=2)