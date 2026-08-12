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

"""
Der Timer-Befehl.

Die vorherige Fassung hatte fuenf Fehler auf einmal, und alle fielen
zusammen erst auf, als der Timer wirklich ablief:

  1. Eine ``while True``-Schleife bearbeitete die Nachricht alle sechs
     Sekunden -- bei den erlaubten 24 Stunden waren das 14.400
     Bearbeitungen fuer EINEN Timer. Discord erlaubt grob fuenf pro
     fuenf Sekunden und Kanal.
  2. Am Ende griff der Code auf ``self.client`` zu. Das Attribut gibt es
     nicht, ``__init__`` setzt ``self.bot``. Jeder ablaufende Timer lief
     also in einen AttributeError.
  3. ``ctx.channel.get_message()`` wurde in discord.py 2.0 zu
     ``fetch_message()`` -- der Aufruf existiert nicht mehr.
  4. ``reactions[0].users().flatten()`` gibt es seit 2.0 ebenfalls
     nicht mehr; ``users()`` ist jetzt ein AsyncIterator.
  5. Ein nacktes ``except: break`` verschluckte genau diese drei
     Abstuerze. Der Timer brach still ab, ohne dass jemand etwas
     bemerkte -- deshalb ist das nie gemeldet worden.

Der Kern der Loesung ist Discords eigener Zeitstempel: ``<t:1234:R>``
laesst den Client des Betrachters selbst herunterzaehlen. Der Bot
schreibt die Nachricht **einmal** und ruehrt sie bis zum Ablauf nicht
mehr an. Die Faelligkeit steht in ``db/timer.db``, damit ein Neustart
keinen Timer mehr verliert.
"""

import logging
import time

import discord
from discord.ext import commands, tasks

from utils.Tools import *
from utils.panels import from_embed
from utils import timer_store

logger = logging.getLogger(__name__)

# Laenger als eine Woche ergibt keinen Timer mehr, sondern einen
# Kalendereintrag. Vorher war bei 24 Stunden Schluss -- das ging nur,
# weil laengere Laufzeiten die Bearbeitungsgrenze gesprengt haetten.
# Mit dem Zeitstempel spielt die Dauer keine Rolle mehr.
MAX_DAUER = 7 * 86400
FARBE = 0xFF0000


class Timer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_timers.start()

    def cog_unload(self):
        self.check_timers.cancel()

    # ── Der Hintergrundlauf ──────────────────────────────────────────

    @tasks.loop(seconds=5)
    async def check_timers(self):
        """
        Faellige Timer abschliessen.

        Fuenf Sekunden Taktung ist dieselbe Wahl wie bei den
        Gewinnspielen. Ein Timer laeuft dadurch bis zu fuenf Sekunden
        nach -- unauffaellig, und der Preis dafuer ist eine einzige
        Abfrage auf einen indizierten Datenbankschluessel.
        """
        try:
            faellig = await timer_store.due()
        except Exception as exc:
            logger.error(f"Timer-Abfrage fehlgeschlagen: {type(exc).__name__}: {exc}")
            return

        for eintrag in faellig:
            try:
                await self._finish(eintrag)
            except Exception as exc:
                logger.error(
                    f"Timer {eintrag['id']} konnte nicht beendet werden: "
                    f"{type(exc).__name__}: {exc}"
                )
            finally:
                # Auch nach einem Fehler abhaken. Sonst versucht es der
                # Lauf alle fuenf Sekunden erneut -- fuer immer.
                await timer_store.finish(eintrag["id"])

    @check_timers.before_loop
    async def before_check(self):
        """
        Erst laufen, wenn der Bot seine Server kennt.

        Ohne das Warten liefert ``get_channel`` beim ersten Durchlauf
        noch None, und jeder Timer, der waehrend eines Neustarts faellig
        wurde, gaelte als "Kanal weg" -- also stillschweigend verloren.
        """
        await self.bot.wait_until_ready()
        try:
            entfernt = await timer_store.cleanup()
            if entfernt:
                logger.info(f"{entfernt} alte Timer-Eintraege aufgeraeumt.")
        except Exception as exc:
            logger.warning(f"Timer-Aufraeumen uebersprungen: {exc}")

    async def _finish(self, eintrag: dict):
        """Die Schlussnachricht schicken."""
        kanal = self.bot.get_channel(eintrag["channel_id"])
        if kanal is None:
            # Kanal geloescht oder Bot rausgeworfen -- nichts zu tun.
            return

        titel = eintrag["title"]
        erwaehnung = f"<@{eintrag['user_id']}>"

        embed = discord.Embed(
            title=titel,
            description="**Die Zeit ist um.**",
            color=FARBE,
        )
        embed.timestamp = discord.utils.utcnow()

        # Antwort auf die urspruengliche Nachricht, damit der Zusammenhang
        # sichtbar bleibt. Wurde sie geloescht, geht es ohne Bezug weiter --
        # deshalb steht das in einem eigenen try.
        referenz = None
        if eintrag["message_id"]:
            try:
                referenz = await kanal.fetch_message(eintrag["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                referenz = None

        try:
            if referenz is not None:
                await referenz.reply(content=erwaehnung, view=from_embed(embed))
            else:
                await kanal.send(content=erwaehnung, view=from_embed(embed))
        except discord.Forbidden:
            logger.warning(
                f"Timer {eintrag['id']}: keine Schreibrechte in Kanal "
                f"{eintrag['channel_id']}."
            )
        except discord.HTTPException as exc:
            logger.warning(f"Timer {eintrag['id']}: Discord lehnte ab: {exc}")

    # ── Die Befehle ──────────────────────────────────────────────────

    @commands.hybrid_command(
        name="timer",
        aliases=["tstart"],
        description="Startet einen Timer, der auch einen Neustart uebersteht",
        usage="timer <dauer> [titel]",
    )
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _timer(self, ctx, times: str, *, title: str = None):
        titel = (title or "Timer")[:100]

        sekunden = timer_store.parse_duration(times)
        if sekunden is None:
            return await ctx.reply(
                "Ich verstehe die Dauer nicht. Moeglich sind zum Beispiel "
                "`30s`, `10m`, `2h`, `1d` oder `1h30m`."
            )
        if sekunden <= 0:
            return await ctx.reply("Die Dauer muss groesser als null sein.")
        if sekunden > MAX_DAUER:
            return await ctx.reply(
                f"Laenger als {MAX_DAUER // 86400} Tage geht nicht."
            )

        ends_at = int(time.time()) + sekunden

        # Erst vormerken, dann senden. Bricht der Bot dazwischen ab, gibt
        # es einen Timer ohne Nachricht -- der laeuft trotzdem sauber ab.
        # Andersherum gaebe es eine Nachricht, die nie endet.
        timer_id = await timer_store.create(
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            title=titel,
            ends_at=ends_at,
        )

        embed = discord.Embed(
            title=titel,
            # <t:...:R> zaehlt im Client des Betrachters herunter. Der Bot
            # bearbeitet die Nachricht dafuer kein einziges Mal.
            description=(
                f"Endet <t:{ends_at}:R>\n"
                f"Genau: <t:{ends_at}:F>\n\n"
                f"Dauer: **{timer_store.format_duration(sekunden)}**"
            ),
            color=FARBE,
        )
        embed.set_footer(text=f"Gestartet von {ctx.author} · Nr. {timer_id}")
        embed.timestamp = discord.utils.utcnow()

        nachricht = await ctx.send(view=from_embed(embed))
        await timer_store.attach_message(timer_id, nachricht.id)

    @commands.hybrid_command(
        name="timers",
        description="Zeigt deine laufenden Timer",
        usage="timers",
    )
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _timers(self, ctx):
        laufend = await timer_store.active_for(ctx.author.id, ctx.guild.id)
        if not laufend:
            return await ctx.reply("Du hast hier gerade keinen Timer laufen.")

        zeilen = [
            f"**Nr. {e['id']}** · {e['title']} — endet <t:{e['ends_at']}:R>"
            for e in laufend
        ]
        embed = discord.Embed(
            title="Deine Timer",
            description="\n".join(zeilen),
            color=FARBE,
        )
        embed.set_footer(text="Abbrechen mit  timerstop <Nr.>")
        await ctx.send(view=from_embed(embed))

    @commands.hybrid_command(
        name="timerstop",
        aliases=["tstop"],
        description="Bricht einen deiner Timer ab",
        usage="timerstop <nummer>",
    )
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def _timerstop(self, ctx, timer_id: int):
        # cancel() prueft die Nutzer-ID mit. Ohne das koennte jeder jeden
        # fremden Timer abbrechen, indem er Nummern durchprobiert.
        if await timer_store.cancel(timer_id, ctx.author.id):
            return await ctx.reply(f"Timer Nr. {timer_id} abgebrochen.")
        await ctx.reply(
            f"Timer Nr. {timer_id} laeuft nicht — oder gehoert nicht dir."
        )
