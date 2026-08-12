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

import contextlib

import aiohttp
import discord
import aiosqlite
import asyncio
from discord.ext import commands

from utils import greet_extras, greet_render, welcome_card
from utils.panels import Panel, from_embed

# Groessengrenze fuer ein eigenes Hintergrundbild. Acht Megabyte sind
# grosszuegig fuer ein Banner und klein genug, dass ein Versehen den
# Speicher nicht sprengt.
MAX_BACKGROUND_BYTES = 8 * 1024 * 1024

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

    async def _fetch_image(self, url: str) -> bytes | None:
        """Ein eigenes Hintergrundbild laden.

        Mit Groessen- und Zeitgrenze: eine Adresse, die 80 MB liefert
        oder nie antwortet, darf die Begruessung nicht aufhalten.
        """
        if not url:
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as antwort:
                    if antwort.status != 200:
                        return None
                    laenge = antwort.headers.get("Content-Length")
                    if laenge and int(laenge) > MAX_BACKGROUND_BYTES:
                        return None
                    daten = await antwort.content.read(MAX_BACKGROUND_BYTES + 1)
                    if len(daten) > MAX_BACKGROUND_BYTES:
                        return None
                    return daten
        except Exception:
            return None

    async def build_banner(
        self, member, *, kind: str = "welcome", extras: dict | None = None
    ) -> discord.File | None:
        """Das Bild zur Begruessung oder zum Abschied, oder None.

        Jeder Schritt kann scheitern -- Pillow fehlt, der Avatar-Download
        laeuft in einen Timeout, das Bild ist kaputt -- und keiner davon
        darf die Begruessung verhindern. Deshalb faengt jede Stufe fuer
        sich ab statt einmal ganz aussen.

        ``extras`` kommt aus ``utils/greet_extras.py``: dort steht, ob
        das Bild ueberhaupt gewuenscht ist und ob ein eigener
        Hintergrund hinterlegt wurde.
        """

        if extras is None:
            extras = await greet_extras.get(member.guild.id)

        # Der Schalter. Vorher ging das Banner immer mit, sobald eine
        # Begruessung eingestellt war -- abstellen ging nicht.
        an = extras.get(
            "welcome_image_enabled" if kind == "welcome" else "leave_image_enabled",
            True,
        )
        if not an:
            return None

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
            hintergrund = await self._fetch_image(
                extras.get(
                    "welcome_image_url" if kind == "welcome" else "leave_image_url",
                    "",
                )
            )

            anzahl = guild.member_count or len(guild.members)
            if kind == "welcome":
                beschriftung = "WILLKOMMEN"
                unterzeile = None
                zaehler = None
            else:
                beschriftung = "TSCHUESS"
                unterzeile = f"hat {guild.name} verlassen"
                zaehler = f"Noch {anzahl:,} Mitglieder".replace(",", ".")

            buffer = await asyncio.to_thread(
                welcome_card.render,
                name=member.display_name,
                avatar_bytes=avatar_bytes,
                guild_name=guild.name,
                member_count=anzahl,
                accent=accent,
                background_bytes=hintergrund,
                label=beschriftung,
                subtitle=unterzeile,
                counter_text=zaehler,
            )
        except Exception:
            return None

        if buffer is None:
            return None
        dateiname = "willkommen.png" if kind == "welcome" else "tschuess.png"
        return discord.File(buffer, filename=dateiname)

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

    # ── Abschied ─────────────────────────────────────────────────────
    #
    # Den gab es bisher nicht: `on_member_remove` wurde in diesem Cog
    # nirgends behandelt. Aufgebaut wie die Begruessung, damit sich
    # beides gleich verhaelt -- gleiche Platzhalter, gleiche Karte,
    # gleicher Schalter fuers Bild.

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Bots kommen und gehen staendig; darueber will niemand eine
        # Nachricht im Kanal.
        if getattr(member, "bot", False):
            return

        guild = member.guild
        if guild is None:
            return

        try:
            extras = await greet_extras.get(guild.id)
        except Exception:
            return

        if not extras.get("leave_enabled"):
            return

        kanal_id = extras.get("leave_channel_id") or 0
        if not kanal_id:
            return
        kanal = self.bot.get_channel(int(kanal_id))
        if kanal is None:
            return

        text = greet_extras.render_text(
            extras.get("leave_message") or "**{user.display}** hat den Server verlassen.",
            member,
            guild,
        )

        banner = await self.build_banner(member, kind="leave", extras=extras)

        # Wie bei der Begruessung: bei Components V2 muss das Bild *in*
        # die View. Eine Datei danebenzulegen laedt sie hoch, zeigt sie
        # aber nicht an.
        view = None
        if banner is not None:
            view = Panel("", text, image_url=f"attachment://{banner.filename}")
            inhalt = None
        else:
            inhalt = text

        try:
            await kanal.send(
                content=inhalt,
                view=view,
                **({"file": banner} if banner is not None else {}),
            )
        except (discord.Forbidden, discord.HTTPException):
            # Kein Recht im Kanal oder Discord lehnt ab -- ein
            # Abschiedsgruss ist das nicht wert, den Listener platzen zu
            # lassen.
            return
