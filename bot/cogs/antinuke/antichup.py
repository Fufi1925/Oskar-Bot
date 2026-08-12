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
from utils import nuke_alert, partner_bot
from discord.ext import commands
import aiosqlite
import asyncio
import datetime
import pytz

class AntiChannelUpdate(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "channel_update"

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
    async def on_guild_channel_update(self, before, after):
        # The bot deletes channels itself when cleaning up after an
        # attacker. Without this it can walk into its own repair work
        # and flag it as a nuke.
        if nuke_alert.is_self_action(
            after.guild.id, getattr(after, "id", None)
        ):
            return

        guild = before.guild
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()
            if not antinuke_status or not antinuke_status[0]:
                return

            if not self.can_fetch_audit(guild.id, "channel_update"):
                return

            logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_update, after.id)
            if logs is None:
                return

            executor = logs.user
            # The template bot rebuilds servers after an attack, which
            # looks exactly like a nuke. Banning it mid-rescue would
            # leave the server half-restored.
            if executor.id in {guild.owner_id, self.bot.user.id} \
                    or partner_bot.is_partner(executor):
                return

            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", (guild.id, executor.id)) as cursor:
                if await cursor.fetchone():
                    return

            async with db.execute("SELECT chup FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()
            if whitelist_status and whitelist_status[0]:
                return

            await self.revert_channel_update_and_ban(before, after, executor)
            await asyncio.sleep(3)

    async def revert_channel_update_and_ban(self, before, after, executor, retries=3):
        # The reporting helpers need the guild; this function only
        # receives the object it acts on.
        guild = after.guild
        repaired = False
        while retries > 0:
            try:
                await after.edit(
                    name=before.name,
                    topic=before.topic,
                    position=before.position,
                    nsfw=before.nsfw,
                    bitrate=before.bitrate if hasattr(before, 'bitrate') else None,
                    user_limit=before.user_limit if hasattr(before, 'user_limit') else None,
                    reason="Channel Update | Unwhitelisted User"
                )
                # The settings are back to what they were: undone.
                repaired = True
                break
            except discord.Forbidden:
                # Was allowed to see it, not to act on it. Reporting this
                # is the whole difference between "stopped" and "missed".
                await nuke_alert.handle_forbidden(
                    self.bot, guild, "channel_update", executor=executor,
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

        if retries == 0:
            return

        retries = 3  
        while retries > 0:
            try:
                await before.guild.ban(executor, reason="Channel Update | Unwhitelisted User")
                # This module never reported success -- it only ever
                # spoke up on failure, so a handled attack was silent.
                await nuke_alert.handle_stopped(
                    self.bot, guild, "channel_update", executor=executor,
                )
                return  
            except discord.Forbidden:
                # Reached only after the repair above. Reporting a failed
                # ban as "could not stop it" told owners their server was
                # still being nuked when it was not.
                await nuke_alert.handle_partial(
                    self.bot, guild, "channel_update", executor=executor,
                    repaired=repaired,
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