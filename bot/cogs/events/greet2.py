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

import contextlib

import discord
import aiosqlite
import asyncio
from discord.ext import commands

from utils import greet_render, welcome_card
from utils.panels import Panel, from_embed

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

    async def build_banner(self, member) -> discord.File | None:
        """Das Willkommens-Bild, oder None wenn es nicht geht.

        Jeder Schritt kann scheitern -- Pillow fehlt, der Avatar-Download
        laeuft in einen Timeout, das Bild ist kaputt -- und keiner davon
        darf die Begruessung verhindern. Deshalb faengt jede Stufe fuer
        sich ab statt einmal ganz aussen.
        """

        avatar_bytes = None
        try:
            asset = getattr(member, "display_avatar", None)
            if asset is not None:
                # Discord liefert bis 4096; 256 reicht fuer 168 Pixel
                # Darstellung und laedt deutlich schneller.
                with contextlib.suppress(Exception):
                    avatar_bytes = await asyncio.wait_for(
                        asset.replace(size=256, format="png").read(), timeout=5
                    )
        except Exception:
            avatar_bytes = None

        guild = member.guild
        accent = 0x3B82F6
        try:
            # Die Farbe der Bot-Rolle, damit das Banner zum Server passt.
            me = guild.me
            if me is not None and me.colour.value:
                accent = me.colour.value
        except Exception:
            pass

        try:
            # Pillow rechnet ein paar hundert Millisekunden und blockiert
            # dabei die Event-Loop. Bei einer Beitrittswelle stockt sonst
            # der ganze Bot, also in einen Thread damit.
            buffer = await asyncio.to_thread(
                welcome_card.render,
                name=member.display_name,
                avatar_bytes=avatar_bytes,
                guild_name=guild.name,
                member_count=guild.member_count or len(guild.members),
                accent=accent,
            )
        except Exception:
            return None

        if buffer is None:
            return None
        return discord.File(buffer, filename="willkommen.png")

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

            # Das Banner mit Profilbild. Es ist Beiwerk: schlaegt das
            # Zeichnen fehl oder laesst sich der Avatar nicht laden,
            # geht die Begruessung trotzdem raus -- nur eben ohne Bild.
            # Ein Willkommensgruss, der an einem Bild scheitert, ist
            # schlimmer als einer ohne.
            banner = await self.build_banner(member)

            # Bei Components V2 muss das Bild *in* die View, nicht
            # daneben. Eine Datei einfach mitzuschicken laedt sie zwar
            # hoch, aber Discord zeigt sie nicht an -- eine V2-Nachricht
            # rendert ausschliesslich ihre Komponenten. Genau deshalb kam
            # weiterhin die alte Begruessung ohne Bild an.
            #
            # attachment:// verweist auf die Datei derselben Nachricht.
            view = from_embed(embed)
            if banner is not None:
                if view is not None:
                    view.add_image(f"attachment://{banner.filename}")
                else:
                    # Reiner Text: dann traegt das Panel das Bild allein.
                    view = Panel(
                        "",
                        content or "",
                        image_url=f"attachment://{banner.filename}",
                    )
                    content = None

            try:
                sent_message = await welcome_channel.send(
                    content=content,
                    view=view,
                    **({"file": banner} if banner is not None else {}),
                )
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

