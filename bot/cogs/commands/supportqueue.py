"""
Support-Warteraum.

Ein Sprachkanal wird zum Warteraum erklaert. Betritt ihn jemand, kommt
der Bot dazu, spricht eine Begruessung und spielt danach Wartemusik.
Nach der eingestellten Zeit wiederholt sich beides, bis der letzte
Mensch den Kanal verlaesst.

Warum die Schleife eine eigene Task ist
---------------------------------------
Der naheliegende Weg waere `on_wavelink_track_end`: Ansage endet ->
Musik starten, Musik endet -> Ansage starten. Das haette zwei Haken.

Erstens feuert das Ereignis auch, wenn ein Stueck von aussen gestoppt
wird (Kanal geleert, Node weg) -- dann startet der Handler die naechste
Runde, obwohl niemand mehr zuhoert. Zweitens ist ein Ablauf, der ueber
zwei Ereignisse verteilt ist, schwer zu lesen und noch schwerer zu
testen: nirgends steht der Ablauf am Stueck.

Die Task hat beides an einer Stelle und laesst sich sauber abbrechen.

Kein ffmpeg, kein PyNaCl
------------------------
Beides fehlt im Image, und beides wird auch nicht gebraucht:
`wavelink.Player` erbt **nicht** von `discord.VoiceClient` (geprueft --
die MRO ist Player -> VoiceProtocol -> object), sondern reicht die
Audio-Uebertragung an Lavalink weiter. Nur `VoiceClient` braucht nacl
zum Verschluesseln der Pakete, und der wird hier nie angelegt.

Das heisst aber auch: **ohne erreichbaren Lavalink-Knoten gibt es
keinen Ton.** Der Bot betritt den Kanal dann trotzdem und schreibt die
Begruessung in den Textkanal -- eine stumme Anwesenheit ist besser als
gar keine, und im Dashboard steht, woran es liegt.
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
import wavelink
from discord.ext import commands

from core import Cog
from utils import support_queue as store

LOGGER = logging.getLogger("universitybot.supportqueue")


def _make_logger_visible() -> None:
    """Dafuer sorgen, dass Meldungen dieses Cogs auch ankommen.

    Am Root-Logger dieses Bots haengt kein Handler -- nachgesehen:
    ``logging.getLogger().handlers`` ist leer. Alles, was hier ueber
    ``LOGGER.warning`` ginge, verschwaende damit spurlos.

    Das war beim ersten Fehlerbericht das eigentliche Problem: der Bot
    kam in den Kanal und ging sofort wieder raus, und im Railway-Log
    stand dazu keine einzige Zeile. Ohne Hinweis laesst sich so etwas
    nur raten.

    Der Handler haengt am Modul-Logger und nicht am Root, damit er die
    Ausgabe der uebrigen Module nicht veraendert. ``propagate`` bleibt
    an: kommt spaeter doch eine zentrale Konfiguration, sieht sie die
    Meldungen weiterhin.
    """

    if any(getattr(h, "_supportqueue", False) for h in LOGGER.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[supportqueue] %(levelname)s %(message)s"))
    handler._supportqueue = True  # type: ignore[attr-defined]
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


_make_logger_visible()

# Die mitgelieferte Wartemusik.
#
# Bewusst eine Suchanfrage und keine feste URL: eine URL zu einer
# konkreten Datei geht irgendwann tot, und dann steht der Warteraum
# still. Die Suche laeuft ueber die Quellen, die in
# lavalink/application.yml eingeschaltet sind -- YouTube ist dort aus
# (die eingebaute Quelle ist seit 2024 kaputt), SoundCloud an.
DEFAULT_MUSIC_QUERY = "soundcloud:lofi hip hop radio beats to relax"

# Wie lange auf Lavalink gewartet wird, bevor der Bot stumm bleibt.
NODE_WAIT_SECONDS = 8


class SupportQueue(Cog):
    """Der Warteraum: Bot dazu, Ansage, Musik, von vorn."""

    def __init__(self, client):
        self.client = client
        self._connection = None
        # guild_id -> Task der laufenden Schleife.
        #
        # asyncio haelt auf Tasks nur eine schwache Referenz. Ohne
        # dieses Dict kann die Schleife mitten im Lauf eingesammelt
        # werden -- der Bot sitzt dann stumm im Kanal.
        self._loops: dict[int, asyncio.Task] = {}
        # guild_id -> Task, die ans Warten erinnert. Getrennt von der
        # Musikschleife, damit sie auch ohne Lavalink laeuft.
        self._reminders: dict[int, asyncio.Task] = {}

    async def cog_load(self) -> None:
        import aiosqlite

        self._connection = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(self._connection)

    async def cog_unload(self) -> None:
        for task in list(self._loops.values()):
            task.cancel()
        self._loops.clear()
        for task in list(self._reminders.values()):
            task.cancel()
        self._reminders.clear()
        store.reset()
        if self._connection is not None:
            await self._connection.close()

    # ── Einstellungen ────────────────────────────────────────────────

    async def settings(self, guild_id: int) -> dict:
        if self._connection is None:
            return await store.get(await self._fallback_db(), guild_id)
        return await store.get(self._connection, guild_id)

    async def _fallback_db(self):
        import aiosqlite

        self._connection = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(self._connection)
        return self._connection

    # ── Das Ereignis ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        guild = member.guild
        if guild is None:
            return

        record = await self.settings(guild.id)
        if not record.get("enabled") or not record.get("channel_id"):
            return

        watched = int(record["channel_id"])
        came = after.channel is not None and after.channel.id == watched
        left = before.channel is not None and before.channel.id == watched

        # Ein Wechsel *innerhalb* desselben Kanals -- stummschalten,
        # Video an -- feuert dieses Ereignis ebenfalls. Dann ist beides
        # wahr und nichts hat sich geaendert.
        if came and left:
            return

        if came:
            store.mark_waiting(guild.id, member.id)
            await self._on_arrival(guild, member, record)
        elif left:
            store.clear_waiting(guild.id, member.id)
            await self._maybe_stop(guild, watched)

    async def _on_arrival(self, guild, member, record: dict) -> None:
        """Jemand wartet. Bot dazu, Ansage, Musik."""

        channel = guild.get_channel(int(record["channel_id"]))
        if channel is None:
            return

        # Dem Team Bescheid sagen. Das ist der Teil, der auch ohne Ton
        # funktioniert -- und der eigentlich wichtige: jemand wartet.
        await self._notify_staff(guild, member, record, channel)

        # Laeuft schon eine Schleife, ist der Bot bereits da.
        if guild.id in self._loops and not self._loops[guild.id].done():
            return

        task = asyncio.create_task(self._run_loop(guild, channel, record))
        self._loops[guild.id] = task
        task.add_done_callback(
            lambda beendete, gid=guild.id: self._forget_loop(gid, beendete)
        )

        # Die Erinnerungen laufen getrennt von der Musik.
        #
        # Warum nicht in derselben Schleife: die haengt an der
        # Musikdauer und wartet zwischen Ansage und Stueck. Eine
        # Erinnerung nach fuenf Minuten kaeme dann irgendwann
        # dazwischen -- oder gar nicht, wenn Lavalink fehlt und die
        # Musikschleife nie startet. Gerade dann ist die Erinnerung
        # aber das Einzige, was noch funktioniert.
        if guild.id not in self._reminders or self._reminders[guild.id].done():
            erinnerer = asyncio.create_task(
                self._reminder_loop(guild, channel)
            )
            self._reminders[guild.id] = erinnerer
            erinnerer.add_done_callback(
                lambda beendete, gid=guild.id: self._forget_reminder(gid, beendete)
            )

    def _forget_reminder(self, guild_id: int, beendete: asyncio.Task) -> None:
        """Wie `_forget_loop`, fuer die Erinnerungen."""
        if self._reminders.get(guild_id) is beendete:
            self._reminders.pop(guild_id, None)

    async def _reminder_loop(self, guild, channel) -> None:
        """Erinnern, solange jemand wartet und niemand kommt.

        Prueft jede halbe Minute. Haeufiger waere sinnlos -- die
        kleinste einstellbare Erinnerung liegt bei einer Minute --,
        seltener wuerde die Einstellung ungenau.

        Die Einstellungen werden bei jedem Durchgang neu gelesen: wer
        die Erinnerung waehrend einer laufenden Wartezeit abschaltet,
        soll nicht bis zum naechsten Neustart warten muessen.
        """
        try:
            while True:
                await asyncio.sleep(30)

                if not self._humans_present(channel):
                    return

                record = await self.settings(guild.id)
                if not record.get("enabled"):
                    return

                if not store.due_for_reminder(record, guild.id):
                    continue

                # Sitzt inzwischen jemand vom Team drin, ist die
                # Erinnerung erledigt -- ohne sie zu schicken.
                if not record.get("ping_when_staff_present"):
                    if self._staff_present(guild, channel, record):
                        return

                if await self._send_notice(
                    guild, None, record, channel, erinnerung=True
                ):
                    store.mark_reminded(guild.id)
                    LOGGER.info(
                        "Erinnerung %s in %s geschickt",
                        store.reminders_sent(guild.id), guild.id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Erinnerungsschleife in %s: %s", guild.id, exc)

    def _forget_loop(self, guild_id: int, beendete: asyncio.Task) -> None:
        """Den Eintrag loeschen -- aber nur den eigenen.

        ── Der Fehler, den das behebt ──────────────────────────────

        Hier stand `self._loops.pop(gid, None)`. Das loeschte, was
        auch immer gerade unter der Server-ID stand -- auch eine
        **andere, gerade gestartete** Schleife.

        Der Ablauf, nachgestellt in `repro/bug_warteraum.py`:

          1. Jemand verlaesst den Warteraum. `_maybe_stop` ruft
             `task.cancel()` und nimmt den Eintrag heraus.
          2. `cancel()` beendet eine Task **nicht sofort** -- der
             Abbruch wird erst zugestellt, wenn sie das naechste Mal
             wartet.
          3. Dieselbe Person kommt sofort wieder rein. `_on_arrival`
             sieht ein leeres `_loops`, startet eine zweite Schleife
             und traegt sie ein.
          4. Jetzt erst kommt der Abbruch der ERSTEN an, ihr Callback
             feuert -- und loescht den Eintrag der ZWEITEN.

        Ergebnis: die zweite Schleife laeuft verwaist weiter, und beim
        naechsten Beitritt haelt der Bot sie fuer tot. Aus Sicht des
        Wartenden: **beim zweiten Mal kommt der Bot nicht.**

        Gemessen, nicht vermutet: ohne Wartezeit zwischen Verlassen
        und Wiedereintritt schlaegt die Pruefung fehl, mit Wartezeit
        nicht. Genau das ist der Unterschied zwischen einem echten
        Nutzer und einem geduldigen Test.
        """
        if self._loops.get(guild_id) is beendete:
            self._loops.pop(guild_id, None)

    async def _notify_staff(self, guild, member, record: dict, channel) -> None:
        """Dem Team sagen, dass jemand wartet.

        ── Was am alten Ping falsch war ────────────────────────────

        Eine einzige Regel: "Kanal eingestellt -> bei jedem Beitritt
        eine Nachricht". Drei Loecher, und jedes fuehrt dazu, dass die
        Erwaehnung am Ende abgeschaltet wird:

          * **Kein Cooldown.** Wer zweimal verbindet -- oder dessen
            Netz kurz wackelt -- loeste zwei Pings aus. Bei einer
            instabilen Leitung wird das Team im Sekundentakt
            erwaehnt.
          * **Keine Erinnerung.** Sah niemand die erste Meldung,
            wartete die Person, bis sie aufgab.
          * **Kein Blick auf den Kanal.** Sass schon ein Teammitglied
            im Warteraum, wurde trotzdem gepingt.

        Jetzt entscheidet `support_queue.may_ping` -- mit Cooldown,
        und die Erinnerungen laufen als eigene Schleife.
        """
        if not store.may_ping(record, guild.id):
            return

        # Sitzt schon jemand vom Team im Warteraum? Dann ist der Ping
        # ueberfluessig -- es ist ja bereits jemand da. Abschaltbar,
        # weil manche Teams die Meldung trotzdem im Log haben wollen.
        if not record.get("ping_when_staff_present"):
            if self._staff_present(guild, channel, record):
                LOGGER.info(
                    "Kein Ping in %s: es ist schon jemand vom Team da",
                    guild.id,
                )
                return

        if await self._send_notice(guild, member, record, channel):
            store.mark_pinged(guild.id)

    @staticmethod
    def _staff_present(guild, channel, record: dict) -> bool:
        """Sitzt jemand mit der Team-Rolle im Warteraum?

        Ohne eingestellte Rolle nicht beantwortbar -- dann lieber
        pingen als schweigen: eine Meldung zu viel ist harmloser als
        ein Wartender, den niemand bemerkt.
        """
        role_id = record.get("staff_role_id")
        if not role_id:
            return False

        try:
            rolle = guild.get_role(int(role_id))
        except (TypeError, ValueError):
            return False
        if rolle is None:
            return False

        for mitglied in getattr(channel, "members", []) or []:
            if getattr(mitglied, "bot", False):
                continue
            if rolle in getattr(mitglied, "roles", []):
                return True
        return False

    async def _send_notice(
        self, guild, member, record: dict, channel, *, erinnerung: bool = False
    ) -> bool:
        """Die Nachricht wirklich abschicken. True, wenn sie rausging."""

        target_id = record.get("notify_channel_id")
        if not target_id:
            return False
        target = guild.get_channel(int(target_id))
        if target is None or not hasattr(target, "send"):
            LOGGER.warning(
                "Meldekanal %s nicht erreichbar -- niemand erfaehrt vom "
                "Wartenden", target_id,
            )
            return False

        mention = ""
        role_id = record.get("staff_role_id")
        if role_id:
            role = guild.get_role(int(role_id))
            if role is not None:
                mention = role.mention

        if erinnerung:
            wartende = store.waiting(guild.id)
            anzahl = len(wartende)
            seit = 0
            if wartende:
                seit = int(time.time() - min(wartende.values())) // 60
            titel = "Es wartet immer noch jemand"
            text = (
                f"{anzahl} {'Person' if anzahl == 1 else 'Personen'} "
                f"in {channel.mention}"
                + (f" — seit {seit} Minuten." if seit else ".")
            )
        else:
            titel = "Jemand wartet im Support"
            text = f"{member.mention} wartet in {channel.mention}."

        try:
            from utils.panels import StatusCard

            await target.send(
                content=mention or None,
                view=StatusCard(titel, text, tone="info"),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            return True
        except Exception as exc:  # noqa: BLE001 - Hinweis darf nie den Rest kippen
            LOGGER.warning("Support-Hinweis fehlgeschlagen: %s", exc)
            return False

    # ── Die Schleife ─────────────────────────────────────────────────

    async def _run_loop(self, guild, channel, record: dict) -> None:
        """Ansage, Musik, von vorn -- bis niemand mehr da ist."""

        player = None
        try:
            player = await self._join(channel)
            if player is None:
                # Kein Lavalink. Der Bot bleibt draussen, statt stumm
                # im Kanal zu sitzen und Anwesenheit vorzutaeuschen.
                LOGGER.warning(
                    "Support-Warteraum ohne Lavalink -- keine Ansage in %s",
                    guild.id,
                )
                return

            seconds = int(record.get("music_seconds") or store.DEFAULT_MUSIC_SECONDS)

            # Eine Zeile, wenn es losgeht -- und eine, wenn es nicht
            # losgeht. Ohne die zweite sieht ein sofortiges Verlassen
            # im Log genauso aus wie gar kein Ereignis.
            if not self._humans_present(channel):
                LOGGER.warning(
                    "Niemand in #%s gesehen, obwohl gerade jemand beigetreten "
                    "ist — der Bot geht wieder. Steht der Member im Cache?",
                    getattr(channel, "name", channel.id),
                )
                return

            LOGGER.info(
                "Warteraum #%s: Ansage, dann %ss Musik",
                getattr(channel, "name", channel.id), seconds,
            )

            while self._humans_present(channel):
                await self._speak_greeting(player, guild, record)
                if not self._humans_present(channel):
                    break
                await self._play_music(player, record, seconds)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Support-Warteraum in %s: %s", guild.id, exc)
        finally:
            if player is not None:
                try:
                    await player.disconnect()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _humans_present(channel) -> bool:
        """Sitzt noch jemand drin, der kein Bot ist?

        Ohne diese Frage laeuft die Schleife weiter, wenn der letzte
        Mensch gegangen ist -- der Bot spielt dann sich selbst etwas
        vor.

        Warum das hier nicht einfach `channel.members` liest
        ---------------------------------------------------
        Genau daran ist die erste Fassung gescheitert: der Bot kam in
        den Kanal und ging sofort wieder raus. `channel.members` ist
        keine gespeicherte Liste, sondern wird bei jedem Zugriff neu
        berechnet -- und filtert dabei stillschweigend:

            for user_id, state in self.guild._voice_states.items():
                if state.channel and state.channel.id == self.id:
                    member = self.guild.get_member(user_id)
                    if member is not None:      # <-- hier faellt es raus
                        ret.append(member)

        Kennt der Member-Cache den Nutzer nicht, gibt `get_member()`
        None und die Person verschwindet aus der Liste. Der Kanal wirkt
        leer, `while self._humans_present(...)` ist sofort falsch, die
        Schleife wird nie betreten -- und das `finally` trennt die
        Verbindung. Aus Sicht des Wartenden: der Bot kommt und ist im
        selben Moment wieder weg.

        Der Voice-Zustand selbst kennt jeden im Kanal, auch ohne
        gecachten Member. Deshalb wird zuerst dort nachgesehen und
        `channel.members` nur als Rueckfallebene benutzt.
        """

        guild = getattr(channel, "guild", None)
        states = getattr(guild, "_voice_states", None)

        if isinstance(states, dict) and states:
            bot_id = getattr(getattr(guild, "me", None), "id", None)
            for user_id, state in states.items():
                target = getattr(state, "channel", None)
                if target is None or getattr(target, "id", None) != channel.id:
                    continue
                if bot_id is not None and user_id == bot_id:
                    continue

                # Ist es ein Bot? Nur beantwortbar, wenn der Member
                # bekannt ist. Im Zweifel als Mensch zaehlen: lieber
                # einmal zu lange spielen als den Wartenden abwuergen
                # -- und ein zweiter Bot im Support-Warteraum ist der
                # deutlich seltenere Fall.
                member = None
                if guild is not None:
                    try:
                        member = guild.get_member(user_id)
                    except Exception:  # noqa: BLE001
                        member = None
                if member is None or not getattr(member, "bot", False):
                    return True
            return False

        # Kein Voice-Zustand verfuegbar (Attrappen im Test, aeltere
        # Bibliothek): dann eben die uebliche Liste.
        return any(not m.bot for m in getattr(channel, "members", []))

    async def _join(self, channel):
        """In den Kanal, ueber Lavalink. None, wenn kein Knoten da ist."""

        if not await self._wait_for_node():
            return None

        try:
            # `self_deaf=False`: ein Bot, der sich selbst taub stellt,
            # wird auf manchen Servern von Moderations-Regeln aus dem
            # Kanal geworfen -- und es sieht fuer die Wartenden aus,
            # als waere er abgestuerzt. Zu hoeren braucht er nichts,
            # aber taub muss er dafuer nicht sein.
            return await channel.connect(cls=wavelink.Player, self_deaf=False)
        except discord.ClientException:
            # Schon verbunden -- den vorhandenen Player nehmen.
            return channel.guild.voice_client
        except Exception as exc:  # noqa: BLE001
            # Mit print, nicht nur ueber den Logger.
            #
            # Am Root-Logger haengt in diesem Bot kein Handler
            # (nachgesehen: `logging.getLogger().handlers` ist leer).
            # Eine Warnung von hier landete deshalb nirgends -- und
            # ein fehlgeschlagener Beitritt sah aus wie "der Bot geht
            # sofort wieder raus", ohne eine Zeile im Railway-Log.
            print(f"[supportqueue] Beitritt fehlgeschlagen: {exc!r}")
            LOGGER.warning("Beitritt zum Warteraum fehlgeschlagen: %s", exc)
            return None

    @staticmethod
    async def _wait_for_node() -> bool:
        """Ist ein Lavalink-Knoten da?

        Beim Start kann der Knoten noch fehlen, weil die Verbindung im
        Musik-Cog nebenher aufgebaut wird. Ein paar Sekunden warten ist
        besser, als den ersten Wartenden stumm zu lassen.
        """

        for _ in range(NODE_WAIT_SECONDS * 2):
            if wavelink.Pool.nodes:
                return True
            await asyncio.sleep(0.5)
        return bool(wavelink.Pool.nodes)

    async def _speak_greeting(self, player, guild, record: dict) -> None:
        """Die Ansage. Stumm bleiben ist besser als abstuerzen."""

        text = store.greeting_text(record, guild_name=guild.name)
        if not text:
            return

        track = await self._tts_track(text)
        if track is None:
            return

        try:
            await player.play(track, volume=100)
            # `floor`: auch wenn der Player sofort "fertig" meldet,
            # wird kurz gewartet. Sonst folgt die Musik der Ansage
            # ohne Atempause -- und bei einem Fehlschlag dreht die
            # Schleife durch.
            await self._wait_until_idle(player, limit=60, floor=1.0)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Ansage fehlgeschlagen: %s", exc)

    @staticmethod
    async def _tts_track(text: str):
        """Den gesprochenen Satz als abspielbares Stueck.

        Google Translate liefert die Sprachausgabe als MP3 ueber eine
        einfache URL. Lavalinks http-Quelle ist eingeschaltet
        (lavalink/application.yml), kann sie also direkt abspielen --
        ohne ffmpeg im Bot-Image und ohne PyNaCl.

        Die Laenge ist begrenzt: Google nimmt nur etwa 200 Zeichen pro
        Aufruf. Laengere Ansagen werden abgeschnitten, statt still zu
        scheitern.
        """

        from urllib.parse import quote

        snippet = text[:200]
        url = (
            "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob"
            f"&tl=de&q={quote(snippet)}"
        )

        try:
            found = await wavelink.Playable.search(url)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Sprachausgabe nicht abrufbar: %s", exc)
            return None

        if not found:
            return None
        return found[0]

    async def _play_music(self, player, record: dict, seconds: int) -> None:
        """Wartemusik fuer die eingestellte Dauer."""

        query = str(record.get("music_url") or "").strip() or DEFAULT_MUSIC_QUERY

        try:
            found = await wavelink.Playable.search(query)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Wartemusik nicht gefunden: %s", exc)
            found = None

        if not found:
            # Keine Musik? Dann eben Stille -- aber die Schleife muss
            # trotzdem warten, sonst wiederholt sie die Ansage sofort
            # und der Wartende hoert sie im Sekundentakt.
            await asyncio.sleep(seconds)
            return

        track = found[0]
        try:
            # `end` schneidet das Stueck hart auf die eingestellte
            # Dauer. Ohne diese Angabe liefe ein zehnminuetiger Track
            # durch, und die Ansage kaeme nie wieder.
            await player.play(track, volume=45, end=seconds * 1000)
            # Die Musik soll ihre volle Zeit bekommen. Ohne `floor`
            # reichte ein Player, der sofort "spielt nicht" meldet, um
            # die Ansage im Sekundentakt zu wiederholen.
            await self._wait_until_idle(
                player, limit=seconds + 5, floor=float(seconds)
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Wartemusik fehlgeschlagen: %s", exc)
            await asyncio.sleep(seconds)

    @staticmethod
    async def _wait_until_idle(player, *, limit: int, floor: float = 0.0) -> None:
        """Warten, bis das Stueck durch ist -- hoechstens `limit`.

        Zwei Grenzen, und beide sind noetig.

        Die **Obergrenze** ist der Notausgang: bleibt ein Stueck
        haengen (Lavalink verliert die Verbindung, der Track ist
        laenger als gedacht), stuende die Schleife sonst fuer immer.

        Die **Untergrenze** verhindert das Gegenteil. Meldet der Player
        sofort "spielt nicht" -- weil der Track nicht geladen werden
        konnte, oder weil er null Sekunden lang ist -- kehrt diese
        Funktion augenblicklich zurueck. Die Schleife darueber startet
        dann sofort die naechste Runde, und das Ganze dreht bei voller
        Last durch, ohne dass ein einziger Ton faellt.

        Gemessen: ohne `floor` lief die Schleife so schnell, dass sich
        die Task nicht einmal mehr abbrechen liess -- sie kam nie an
        einen Wartepunkt, an dem asyncio den Abbruch haette zustellen
        koennen. Auf einem echten Server waere das ein Kern auf
        Anschlag.
        """

        waited = 0.0
        while waited < limit:
            if not getattr(player, "playing", False) and waited >= floor:
                return
            await asyncio.sleep(0.5)
            waited += 0.5

    async def _maybe_stop(self, guild, channel_id: int) -> None:
        """Der Letzte macht das Licht aus."""

        channel = guild.get_channel(channel_id)
        if channel is not None and self._humans_present(channel):
            return

        # `store.reset` nimmt den Ping-Zustand mit: der naechste
        # Wartende soll sofort gemeldet werden und nicht in einem
        # Cooldown haengen, der noch dem Vorgaenger galt.
        store.reset(guild.id)

        erinnerer = self._reminders.pop(guild.id, None)
        if erinnerer is not None:
            erinnerer.cancel()

        task = self._loops.pop(guild.id, None)
        if task is not None:
            task.cancel()
            # Auf das Ende warten, bevor hier weitergemacht wird.
            #
            # Sonst laeuft die alte Schleife noch, waehrend schon eine
            # neue startet -- zwei Schleifen auf demselben Player, und
            # das `finally` der alten trennt die Verbindung der neuen.
            # Der Bot kaeme dann rein und sofort wieder raus.
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:  # noqa: BLE001
                pass

        voice = guild.voice_client
        if voice is not None:
            try:
                await voice.disconnect()
            except Exception:  # noqa: BLE001
                pass


async def setup(bot):
    await bot.add_cog(SupportQueue(bot))
