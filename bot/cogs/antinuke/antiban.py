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

class AntiBan(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "ban"

    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}

    def can_fetch_audit(self, guild_id, event_name, max_requests=5, interval=10, cooldown_duration=300):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)

        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if guild_id in self.cooldowns and event_name in self.cooldowns[guild_id]:
            if (now - self.cooldowns[guild_id][event_name]).total_seconds() < cooldown_duration:
                return False
            del self.cooldowns[guild_id][event_name]

        if len(timestamps) > max_requests:
            self.cooldowns.setdefault(guild_id, {})[event_name] = now
            return False
        return True

    async def fetch_audit_logs(self, guild, action, target_id):
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
                    return entry
        except Exception:
            pass
        return None

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()
            if not antinuke_status or not antinuke_status[0]:
                return

            if not self.can_fetch_audit(guild.id, "member_ban"):
                return

            entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.ban, user.id)
            if not entry:
                return

            executor = entry.user
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

            async with db.execute("SELECT ban FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()
            if whitelist_status and whitelist_status[0]:
                return

            await self.ban_executor(guild, executor, user)

    async def ban_executor(self, guild, executor, user, retries=3):
        while retries > 0:
            try:
                await guild.ban(executor, reason="Member Ban | Unwhitelisted User")
                await guild.unban(user, reason="Reverting ban by unwhitelisted user")
                await nuke_alert.handle_stopped(
                    self.bot, guild, "ban", executor=executor,
                    clean=False,
                )
                return
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "ban", executor=executor,
                    # The ban is the first thing tried here, so a
                    # Forbidden means nothing was undone at all.
                    repaired=False,
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                        retries -= 1
                    else:
                        break
            except Exception:
                return

        retries = 3 
        while retries > 0:
            try:
                await guild.unban(user, reason="Reverting ban by unwhitelisted user")
                return
            except discord.Forbidden:
                # Was allowed to see it, not to act on it. Reporting this
                # is the whole difference between "stopped" and "missed".
                await nuke_alert.handle_forbidden(
                    self.bot, guild, "ban", executor=executor,
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                        retries -= 1
                    else:
                        break
            except Exception:
                return

