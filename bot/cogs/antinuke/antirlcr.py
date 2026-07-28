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

class AntiRoleCreate(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "role_create"

    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}

    async def is_blacklisted_guild(self, guild_id):
        async with aiosqlite.connect('db/block.db') as block_db:
            cursor = await block_db.execute("SELECT 1 FROM guild_blacklist WHERE guild_id = ?", (str(guild_id),))
            return await cursor.fetchone() is not None

    async def fetch_audit_logs(self, guild, action):
        if not guild.me.guild_permissions.ban_members:
            # Returning None here used to end the story in silence --
            # the anti-nuke could see nothing and said nothing, which
            # is the one case the owner most needs to hear about.
            await nuke_alert.handle_blind(self.bot, guild, self.ALERT_ACTION)
            return None
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                now = datetime.datetime.now(pytz.utc)
                created_at = entry.created_at
                difference = (now - created_at).total_seconds() * 1000

                if difference >= 3600000:
                    return None
                return entry
        except Exception:
            pass
        return None

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

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild
        if await self.is_blacklisted_guild(guild.id):
            return

        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()
            if not antinuke_status or not antinuke_status[0]:
                return

        if not self.can_fetch_audit(guild.id, 'role_create'):
            return

        log_entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.role_create)
        if log_entry is None:
            return

        executor = log_entry.user

        # The template bot rebuilds servers after an attack, which
        # looks exactly like a nuke. Banning it mid-rescue would
        # leave the server half-restored.
        if executor.id in {guild.owner_id, self.bot.user.id} \
                or partner_bot.is_partner(executor):
            return

        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", 
                                  (guild.id, executor.id)) as cursor:
                extra_owner_status = await cursor.fetchone()
            if extra_owner_status:
                return

            async with db.execute("SELECT rlcr FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", 
                                  (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()
            if whitelist_status and whitelist_status[0]:
                return

        await self.ban_executor_and_delete_role(guild, executor, role)
        await asyncio.sleep(3)

    async def ban_executor_and_delete_role(self, guild, executor, role):
        retries = 3
        while retries > 0:
            try:
                await self.ban_executor(guild, executor)
                await role.delete(reason="Role created by unwhitelisted user")
                await nuke_alert.handle_stopped(
                    self.bot, guild, "role_create", executor=executor,
                    clean=False,
                )
                return
            except discord.Forbidden:
                # Was allowed to see it, not to act on it. Reporting this
                # is the whole difference between "stopped" and "missed".
                await nuke_alert.handle_forbidden(
                    self.bot, guild, "role_create", executor=executor,
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                        retries -= 1
                else:
                    return
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                return

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="Role Create | Unwhitelisted User")
                return
            except discord.Forbidden:
                await nuke_alert.handle_partial(
                    self.bot, guild, "role_create", executor=executor,
                    # This helper only bans; a Forbidden here
                    # means nothing was undone.
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
                    return
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                return
        return
