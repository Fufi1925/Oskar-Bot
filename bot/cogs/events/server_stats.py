"""Sprachkanäle mit aktuellen Mitgliederzahlen.

Aktualisiert ereignisgesteuert, aber gebündelt: Bei einem Raid sollen nicht
hundert Kanaländerungen in derselben Sekunde an Discord gehen. Ein
zehnminütiger Abgleich korrigiert verpasste Gateway-Ereignisse und erstellt
versehentlich gelöschte aktivierte Kanäle neu.
"""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands, tasks

from core import Cog, universitybot
from utils import server_stats_store as store

NAMES = {
    "humans": "👤 Nutzer: {count}",
    "bots": "🤖 Bots: {count}",
    "total": "👥 Mitglieder: {count}",
}


class ServerStats(Cog):
    def __init__(self, client: universitybot):
        self.client = client
        self._pending: dict[int, asyncio.Task] = {}
        self.refresh_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()
        for task in self._pending.values():
            task.cancel()
        self._pending.clear()

    @staticmethod
    def counts(guild: discord.Guild) -> dict[str, int]:
        members = list(getattr(guild, "members", ()) or ())
        bots = sum(1 for member in members if member.bot)
        humans = len(members) - bots
        # Mit aktiviertem Members-Intent ist der Cache vollständig und gibt
        # zugleich die einzige belastbare Aufteilung Mensch/Bot her.
        return {"humans": humans, "bots": bots, "total": humans + bots}

    async def sync_guild(self, guild: discord.Guild) -> dict:
        settings = await store.get(guild.id)
        counts = self.counts(guild)
        created: list[str] = []
        deleted: list[str] = []

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            raise RuntimeError("Dem Bot fehlt das Recht „Kanäle verwalten“.")

        # Niemand soll diese Zähler als normale Sprachkanäle verwenden. Der
        # Bot kann sie dank Administrator/Manage Channels trotzdem umbenennen.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False)
        }

        for kind in store.KINDS:
            enabled = settings[f"{kind}_enabled"]
            saved_id = settings[f"{kind}_channel_id"]
            channel = guild.get_channel(saved_id) if saved_id else None
            if channel is not None and not isinstance(channel, discord.VoiceChannel):
                channel = None

            if not enabled:
                if channel is not None:
                    await channel.delete(reason="Server-Stats im Dashboard deaktiviert")
                    deleted.append(kind)
                if saved_id:
                    await store.set_channel(guild.id, kind, None)
                continue

            wanted = NAMES[kind].format(count=counts[kind])
            if channel is None:
                channel = await guild.create_voice_channel(
                    wanted,
                    overwrites=overwrites,
                    reason="Server-Stats im Dashboard aktiviert",
                )
                await store.set_channel(guild.id, kind, channel.id)
                created.append(kind)
            elif channel.name != wanted:
                await channel.edit(name=wanted, reason="Server-Stats aktualisiert")

        return {"counts": counts, "created": created, "deleted": deleted}

    def schedule(self, guild: discord.Guild) -> None:
        old = self._pending.pop(guild.id, None)
        if old is not None:
            old.cancel()

        async def later():
            try:
                # Bündelt schnelle Join-/Leave-Wellen in eine Änderung.
                await asyncio.sleep(15)
                await self.sync_guild(guild)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"[server_stats] {guild.id}: {exc}")
            finally:
                self._pending.pop(guild.id, None)

        self._pending[guild.id] = asyncio.create_task(later())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self.schedule(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self.schedule(member.guild)

    @tasks.loop(minutes=10)
    async def refresh_loop(self):
        for guild_id in await store.enabled_guild_ids():
            guild = self.client.get_guild(guild_id)
            if guild is None:
                continue
            try:
                await self.sync_guild(guild)
            except Exception as exc:
                print(f"[server_stats] Abgleich {guild_id}: {exc}")
            await asyncio.sleep(0)

    @refresh_loop.before_loop
    async def before_refresh(self):
        await self.client.wait_until_ready()
