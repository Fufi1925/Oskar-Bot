# ╔══════════════════════════════════════════════════════════════════╗
# ║   Verabschiedung                                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Wenn jemand den Server verlaesst.

Das Gegenstueck zur Begruessung in ``greet2.py``, bewusst nach demselben
Muster gebaut: dieselben Platzhalter, dieselbe Warteschlange, dasselbe
Bild -- nur in Rot und mit anderer Beschriftung.

Die Warteschlange ist kein Zierrat. Bei einem Raid, bei dem dreissig
Konten gleichzeitig fliegen, wuerden dreissig einzelne Sendeversuche
sofort in Discords Ratenbegrenzung laufen und die Haelfte davon
verlieren. Nacheinander mit einer kurzen Pause kommt alles an.

Warum ``on_member_remove`` und nicht ``on_raw_member_remove``: der
gecachte Member traegt Anzeigename und Avatar, und genau die braucht
das Bild. Ohne Cache gibt es kein Bild -- dann geht der Text allein
raus, was immer noch besser ist als nichts.
"""

import asyncio
import contextlib
import logging

import discord
from discord.ext import commands

from utils import leave_store, welcome_card
from utils.panels import Panel, from_embed

logger = logging.getLogger(__name__)

# Rot, damit man Beitritt und Austritt im selben Kanal ohne Lesen
# unterscheidet.
LEAVE_ACCENT = 0xEF4444


class LeaveMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue: dict[int, list] = {}
        self.processing: set[int] = set()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Bots verabschiedet man nicht.
        if member.bot:
            return

        self.queue.setdefault(member.guild.id, []).append(member)
        if member.guild.id not in self.processing:
            self.processing.add(member.guild.id)
            try:
                await self.process_queue(member.guild)
            finally:
                # Ohne finally bliebe der Server nach einem Fehler fuer
                # immer als "wird gerade abgearbeitet" markiert, und es
                # ginge nie wieder eine Verabschiedung raus.
                self.processing.discard(member.guild.id)

    async def build_card(self, member, settings: dict) -> discord.File | None:
        """
        Das Abschiedsbild, oder ``None``.

        Jede Stufe faengt fuer sich ab: fehlt Pillow, haengt der
        Avatar-Download oder ist das Bild kaputt, geht die
        Verabschiedung trotzdem raus -- nur ohne Bild. Eine
        Verabschiedung, die an einem Bild scheitert, ist schlimmer als
        eine ohne.
        """
        if not settings.get("card_enabled"):
            return None

        # Ein eigenes Bild ersetzt das gezeichnete. Es wird als URL in
        # das Panel gehaengt, nicht heruntergeladen -- Discord holt es
        # selbst, und der Bot laedt keine fremden Dateien.
        if settings.get("card_image_url"):
            return None

        avatar_bytes = None
        with contextlib.suppress(Exception):
            asset = getattr(member, "display_avatar", None)
            if asset is not None:
                avatar_bytes = await asyncio.wait_for(
                    asset.replace(size=256, format="png").read(), timeout=5
                )

        guild = member.guild
        verbleibend = max(0, (guild.member_count or len(guild.members)))

        try:
            # Pillow rechnet ein paar hundert Millisekunden und blockiert
            # dabei die Ereignisschleife. Bei einer Austrittswelle stockt
            # sonst der ganze Bot.
            buffer = await asyncio.to_thread(
                welcome_card.render,
                name=member.display_name,
                avatar_bytes=avatar_bytes,
                guild_name=guild.name,
                member_count=verbleibend,
                accent=LEAVE_ACCENT,
                label="AUF WIEDERSEHEN",
                preposition="verlässt",
                counter_text=f"Noch {verbleibend:,} Mitglieder".replace(",", "."),
            )
        except Exception as exc:
            logger.debug(f"Abschiedsbild fehlgeschlagen: {exc}")
            return None

        if buffer is None:
            return None
        return discord.File(buffer, filename="abschied.png")

    async def process_queue(self, guild: discord.Guild):
        while self.queue.get(guild.id):
            member = self.queue[guild.id].pop(0)

            try:
                settings = await leave_store.get(guild.id)
            except Exception as exc:
                logger.error(f"Leave-Einstellungen nicht lesbar: {exc}")
                return

            if not settings.get("enabled"):
                # Aus. Die Warteschlange trotzdem leeren, sonst staut
                # sich alles bis zum naechsten Einschalten.
                self.queue[guild.id].clear()
                return

            channel_id = settings.get("channel_id")
            channel = self.bot.get_channel(int(channel_id)) if channel_id else None
            if channel is None:
                self.queue[guild.id].clear()
                return

            verbleibend = guild.member_count or len(guild.members)
            text = leave_store.fill(
                settings.get("leave_message")
                or "**{user.name}** hat den Server verlassen.",
                member,
                verbleibend,
            )

            embed = None
            if settings.get("leave_type") == "embed" and settings.get("embed_data"):
                embed = self._build_embed(settings["embed_data"], member, verbleibend)

            card = await self.build_card(member, settings)
            eigenes_bild = (
                settings.get("card_image_url") if settings.get("card_enabled") else None
            )

            # Bei Components V2 muss das Bild *in* die View, nicht
            # daneben. Eine Datei mitzuschicken laedt sie zwar hoch,
            # aber eine V2-Nachricht rendert ausschliesslich ihre
            # Komponenten -- die Datei bliebe unsichtbar.
            view = from_embed(embed) if embed is not None else None
            bild_quelle = (
                f"attachment://{card.filename}" if card is not None else eigenes_bild
            )

            if bild_quelle:
                if view is not None:
                    view.add_image(bild_quelle)
                else:
                    view = Panel("", text or "", image_url=bild_quelle)
                    text = None

            try:
                if view is not None:
                    nachricht = await channel.send(
                        content=text,
                        view=view,
                        **({"file": card} if card is not None else {}),
                    )
                else:
                    nachricht = await channel.send(content=text)

                dauer = settings.get("auto_delete_duration")
                if dauer:
                    await nachricht.delete(delay=dauer)
            except discord.Forbidden:
                # Keine Schreibrechte -- daran aendert der naechste
                # Austritt nichts, also nicht erneut versuchen.
                self.queue[guild.id].clear()
                return
            except discord.HTTPException as exc:
                if exc.status == 429:
                    await asyncio.sleep(2)
                    self.queue[guild.id].append(member)
                    continue
                logger.warning(f"Verabschiedung fehlgeschlagen: {exc}")

            # Zwei Sekunden zwischen zwei Nachrichten. Discord erlaubt
            # grob fuenf pro fuenf Sekunden je Kanal.
            await asyncio.sleep(2)

    def _build_embed(self, embed_data, member, member_count: int):
        """Ein Embed aus den gespeicherten Angaben."""
        import json

        try:
            daten = json.loads(embed_data) if isinstance(embed_data, str) else embed_data
        except (ValueError, TypeError):
            return None
        if not isinstance(daten, dict):
            return None

        def ersetze(wert):
            return leave_store.fill(wert, member, member_count) if wert else None

        embed = discord.Embed(
            title=ersetze(daten.get("title")),
            description=ersetze(daten.get("description")),
            color=daten.get("color") or LEAVE_ACCENT,
        )
        if daten.get("footer"):
            embed.set_footer(text=ersetze(daten["footer"]) or "")
        if daten.get("thumbnail"):
            with contextlib.suppress(Exception):
                embed.set_thumbnail(url=daten["thumbnail"])
        return embed
