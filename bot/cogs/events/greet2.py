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
import aiosqlite
import asyncio
from discord.ext import commands

from utils import greet_render
from utils.panels import from_embed

class greet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_queue = {}
        self.processing = set()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id not in self.join_queue:
            self.join_queue[member.guild.id] = []
        self.join_queue[member.guild.id].append(member)
        if member.guild.id not in self.processing:
            self.processing.add(member.guild.id)
            await self.process_queue(member.guild)

    async def process_queue(self, guild):
        while self.join_queue[guild.id]:
            member = self.join_queue[guild.id].pop(0)
            async with aiosqlite.connect("db/welcome.db") as db:
                async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration FROM welcome WHERE guild_id = ?", (guild.id,)) as cursor:
                    row = await cursor.fetchone()
            if row is None:
                continue
            welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration = row
            welcome_channel = self.bot.get_channel(channel_id)
            if not welcome_channel:
                continue

            # Rendering lives in utils/greet_render so the dashboard
            # preview is byte-for-byte what the members get. The two used
            # to fill different placeholders.
            content, embed = greet_render.render(
                {
                    "welcome_type": welcome_type,
                    "welcome_message": welcome_message,
                    "embed_data": embed_data,
                },
                member,
            )
            if content is None and embed is None:
                continue

            try:
                sent_message = await welcome_channel.send(content=content, view=from_embed(embed))
                if auto_delete_duration:
                    await sent_message.delete(delay=auto_delete_duration)
            except discord.Forbidden:
                continue
            except discord.HTTPException as e:
                if e.code == 50035 or e.status == 429:
                    await asyncio.sleep(1)
                    self.join_queue[guild.id].append(member)
                    continue
            await asyncio.sleep(2)
        self.processing.remove(guild.id)

