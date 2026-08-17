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

class AntiIntegration(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "integration"

    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}

    async def fetch_audit_logs(self, guild, action):
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                now = datetime.datetime.now(pytz.utc)
                created_at = entry.created_at
                difference = (now - created_at).total_seconds() * 1000

                if difference >= 3600000:
                    return None

                return entry

        except Exception:
            return None
        return None

    def can_fetch_audit(self, guild_id, event_name, max_requests=6, interval=10, cooldown_duration=300):
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

    async def is_blacklisted_guild(self, guild_id):
        async with aiosqlite.connect('db/block.db') as block_db:
            cursor = await block_db.execute("SELECT 1 FROM guild_blacklist WHERE guild_id = ?", (str(guild_id),))
            return await cursor.fetchone() is not None

    @commands.Cog.listener()
    async def on_guild_integrations_update(self, guild):
        if await self.is_blacklisted_guild(guild.id):
            return

        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()

            if not antinuke_status or not antinuke_status[0]:
                return

            # Und laeuft DIESE Wache? Die vierzehn Bereiche lassen
            # sich einzeln abschalten -- fehlt die Zeile, gilt AN.
            if not await nuke_guard.action_enabled(guild.id, "mngweb"):
                return

        if not self.can_fetch_audit(guild.id, 'integration_create'):
            return

        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.integration_create)
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

        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", 
                                  (guild.id, executor.id)) as cursor:
                extraowner_status = await cursor.fetchone()

            if extraowner_status:
                return

            async with db.execute("SELECT mngweb FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", 
                                  (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()

            if whitelist_status and whitelist_status[0]:
                return

            await self.ban_executor(guild, executor)

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="Integration Create | Unwhitelisted User")
                await nuke_alert.handle_stopped(
                    self.bot, guild, "integration", executor=executor,
                    clean=False,
                )
                return
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "integration", executor=executor,
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
                    return
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                return

    async def revert_integration_changes(self, guild):
        retries = 3
        while retries > 0:
            try:
                await guild.edit(integrations=[])
                return
            except discord.Forbidden:
                await nuke_alert.handle_forbidden(
                    self.bot, guild, "integration", executor=None,
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
            except Exception:
                return
