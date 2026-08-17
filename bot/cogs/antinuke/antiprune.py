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
import datetime
import asyncio
import pytz

class AntiPrune(commands.Cog):
    # Which anti-nuke action this module reports on.
    ALERT_ACTION = "prune"

    def __init__(self, bot):
        self.bot = bot

    async def fetch_audit_logs(self, guild, action):
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                now = datetime.datetime.now(pytz.utc)
                created_at = entry.created_at
                difference = (now - created_at).total_seconds() * 1000
                    
                if difference >= 3600000:
                    return  None

                return entry
    
        except Exception:
            pass
        return None

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)) as cursor:
                antinuke_status = await cursor.fetchone()

            if not antinuke_status or not antinuke_status[0]:
                return

            # Und laeuft DIESE Wache? Die vierzehn Bereiche lassen
            # sich einzeln abschalten -- fehlt die Zeile, gilt AN.
            if not await nuke_guard.action_enabled(guild.id, "prune"):
                return

            log_entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.member_prune)
            if log_entry is None:
                return

            executor = log_entry.user
            

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

            async with db.execute("SELECT prune FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (guild.id, executor.id)) as cursor:
                whitelist_status = await cursor.fetchone()

            if whitelist_status and whitelist_status[0]:
                return

            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", (guild.id, executor.id)) as cursor:
                extra_owner_status = await cursor.fetchone()

            if extra_owner_status:
                return

            await self.ban_executor(guild, executor)

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="Member Prune | Unwhitelisted User")
                await nuke_alert.handle_stopped(
                    self.bot, guild, "prune", executor=executor,
                    clean=False,
                )
                return
            except discord.Forbidden:
                print(f"Failed to ban {executor.id} due to missing permissions.")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        print(f"Rate limit encountered. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                else:
                    print(f"HTTPException encountered: {e}")
                    return
            except discord.errors.RateLimited as e:
                print(f"Rate limit encountered while banning: {e}. Retrying in {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception as e:
                print(f"An unexpected error occurred while banning {executor.id}: {e}")
                return

        print(f"Failed to ban {executor.id} after multiple attempts due to rate limits.")
