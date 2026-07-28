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

import discord
from utils import nuke_alert, partner_bot
from discord.ext import commands
import aiosqlite
import asyncio
import datetime
import pytz

class AntiBotAdd(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "bot_add"

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
        if not guild.me.guild_permissions.kick_members:
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
    async def on_member_join(self, member):
        if not member.bot:
            return

        # The check further down looks at *who invited* the bot. That is
        # the wrong question for the template bot: it gets invited by a
        # normal admin who is not on any whitelist, so the rescue bot was
        # kicked on arrival and the admin banned for inviting it.
        if partner_bot.is_partner(member):
            return

        guild = member.guild
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()

            if not antinuke_status or not antinuke_status[0]:
                return

            if not self.can_fetch_audit(guild.id, "bot_add"):
                return

            logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.bot_add, member.id)
            if logs is None:
                return

            executor = logs.user
            # The template bot rebuilds servers after an attack, which
            # looks exactly like a nuke. Banning it mid-rescue would
            # leave the server half-restored.
            if executor.id in {guild.owner_id, self.bot.user.id} \
                    or partner_bot.is_partner(executor):
                return

            async with db.execute("SELECT botadd FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()

            if whitelist_status and whitelist_status[0]:
                return

            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", (guild.id, executor.id)) as cursor:
                extra_owner_status = await cursor.fetchone()

            if extra_owner_status and extra_owner_status[0]:
                return

            await self.take_action_and_kick_bot(guild, executor, member, "Unwhitelisted user added a bot")

    async def take_action_and_kick_bot(self, guild, executor, bot_member, reason, retries=3):
        while retries > 0:
            try:
                await guild.kick(bot_member, reason=reason)
                await guild.ban(executor, reason=reason)
                await nuke_alert.handle_stopped(
                    self.bot, guild, "bot_add", executor=executor,
                    clean=False,
                )
                return
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "bot_add", executor=executor,
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
                await guild.ban(executor, reason=reason)
                return
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "bot_add", executor=executor,
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

async def setup(bot):
    await bot.add_cog(AntiBotAdd(bot))
