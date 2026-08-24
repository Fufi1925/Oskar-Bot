"""
Support-Warteraum.

Ein Sprachkanal wird zum Warteraum erklaert. Betritt ihn jemand, kommt
der Bot dazu und spielt Wartemusik, bis der letzte Mensch den Kanal
verlaesst. Gleichzeitig bekommt das Team eine Meldung im eingestellten
Kanal.

Vier Einstellungen, mehr nicht
------------------------------
an/aus · Warteraum-Kanal · Meldekanal · Team-Rolle.

Alles Uebrige steht fest (`utils/support_queue.py`): die Musik, ihre
Laenge, der Cooldown, die Erinnerungen. Frueher war das alles
einstellbar, und jede dieser Einstellungen war ein Weg, das System
kaputt zu konfigurieren -- eine Musik-URL, die Lavalink nicht findet,
ein Cooldown von einer Stunde. Auch die Meldung selbst ist nicht mehr
bearbeitbar.

Warum die Schleife eine eigene Task ist
---------------------------------------
Der naheliegende Weg waere `on_wavelink_track_end`. Das feuert aber
auch, wenn ein Stueck von aussen gestoppt wird (Kanal geleert, Node
weg) -- dann startet der Handler die naechste Runde, obwohl niemand
mehr zuhoert. Die Task hat den Ablauf an einer Stelle und laesst sich
sauber abbrechen.

Kein ffmpeg, kein PyNaCl
------------------------
Beides fehlt im Image, und beides wird nicht gebraucht:
`wavelink.Player` erbt **nicht** von `discord.VoiceClient` (geprueft --
die MRO ist Player -> VoiceProtocol -> object), sondern reicht die
Uebertragung an Lavalink weiter. Nur `VoiceClient` braucht nacl.

Das heisst aber: **ohne erreichbaren Lavalink-Knoten gibt es keinen
Ton.** Der Bot bleibt dann draussen, statt stumm im Kanal zu sitzen
und Anwesenheit vorzutaeuschen. Die Meldung an das Team geht trotzdem
raus -- sie ist der eigentlich wichtige Teil.
"""

from __future__ import annotations

import asyncio
import logging
import os
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
    stand dazu keine einzige Zeile.
    """

    if any(getattr(h, "_supportqueue", False) for h in LOGGER.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[supportqueue] %(levelname)s %(message)s"))
    handler._supportqueue = True  # type: ignore[attr-defined]
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


_make_logger_visible()


#: Die mitgelieferte Wartemusik, ausgeliefert vom Dashboard.
#:
#: Warum eine URL und keine Datei im Bot-Container: Lavalink laeuft als
#: eigener Dienst und sieht das Dateisystem des Bots nicht. In
#: `lavalink/application.yml` steht ausdruecklich `local: false` und
#: `http: true` -- die Datei muss also ueber HTTP erreichbar sein.
#:
#: Sie liegt in `dashboard/public/warteraum.mp3` und ist damit unter
#: `<domain>/warteraum.mp3` abrufbar. Zum Ersetzen genuegt es, die
#: Datei dort auszutauschen.
MUSIC_FILE = "warteraum.mp3"


def _music_url() -> str:
    """Die vollstaendige Adresse der Wartemusik.

    `PUBLIC_BASE_URL` erlaubt es, die Datei woanders zu hosten. Sonst
    wird die Railway-Domain genommen; lokal der eigene Port.
    """
    basis = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not basis:
        domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
        if domain:
            basis = f"https://{domain}"
        else:
            basis = f"http://127.0.0.1:{os.getenv('PORT', '8080')}"
    return f"{basis}/{MUSIC_FILE}"


#: Rueckfallebene, falls die Datei nicht erreichbar ist.
#:
#: Eine Suchanfrage statt einer festen URL: die laeuft ueber die
#: Quellen aus `lavalink/application.yml` (YouTube ist dort aus, die
#: eingebaute Quelle ist seit 2024 kaputt; SoundCloud ist an).
FALLBACK_MUSIC_QUERY = "soundcloud:lofi hip hop radio beats to relax"

#: Wie lange auf Lavalink gewartet wird, bevor der Bot stumm bleibt.
NODE_WAIT_SECONDS = 8


class SupportQueue(Cog):
    """Der Warteraum: Bot dazu, Musik, Meldung ans Team."""

    def __init__(self, client):
        self.client = client
        self._connection = None
        # guild_id -> Task der laufenden Musikschleife.
        #
        # asyncio haelt auf Tasks nur eine schwache Referenz. Ohne
        # dieses Dict kann die Schleife mitten im Lauf eingesammelt
        # werden -- der Bot sitzt dann stumm im Kanal.
        self._loops: dict[int, asyncio.Task] = {}
        # guild_id -> Task, die ans Warten erinnert. Getrennt von der
        # Musik, damit sie auch ohne Lavalink laeuft.
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
        """Jemand wartet. Team benachrichtigen, Bot dazu, Musik."""

        channel = guild.get_channel(int(record["channel_id"]))
        if channel is None:
            return

        # Zuerst das Team. Dieser Teil funktioniert auch ohne Ton --
        # und er ist der eigentlich wichtige: jemand wartet.
        await self._notify_staff(guild, member, record, channel)

        # Laeuft schon eine Schleife, ist der Bot bereits da.
        if guild.id in self._loops and not self._loops[guild.id].done():
            return

        task = asyncio.create_task(self._run_loop(guild, channel))
        self._loops[guild.id] = task
        task.add_done_callback(
            lambda beendete, gid=guild.id: self._forget_loop(gid, beendete)
        )

        # Die Erinnerungen laufen getrennt von der Musik.
        #
        # Warum nicht in derselben Schleife: die haengt an der
        # Musikdauer und wartet zwischen den Stuecken. Eine Erinnerung
        # nach fuenf Minuten kaeme dann irgendwann dazwischen -- oder
        # gar nicht, wenn Lavalink fehlt und die Musikschleife nie
        # startet. Gerade dann ist die Erinnerung aber das Einzige,
        # was noch funktioniert.
        if guild.id not in self._reminders or self._reminders[guild.id].done():
            erinnerer = asyncio.create_task(self._reminder_loop(guild, channel))
            self._reminders[guild.id] = erinnerer
            erinnerer.add_done_callback(
                lambda beendete, gid=guild.id: self._forget_reminder(gid, beendete)
            )

    def _forget_loop(self, guild_id: int, beendete: asyncio.Task) -> None:
        """Den Eintrag loeschen -- aber nur den eigenen.

        ── Der Fehler, den das behebt ──────────────────────────────

        Hier stand `self._loops.pop(gid, None)`. Das loeschte, was
        auch immer gerade unter der Server-ID stand -- auch eine
        **andere, gerade gestartete** Schleife.

        Der Ablauf:

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
        """
        if self._loops.get(guild_id) is beendete:
            self._loops.pop(guild_id, None)

    def _forget_reminder(self, guild_id: int, beendete: asyncio.Task) -> None:
        """Wie `_forget_loop`, fuer die Erinnerungen."""
        if self._reminders.get(guild_id) is beendete:
            self._reminders.pop(guild_id, None)

    # ── Die Meldung ans Team ─────────────────────────────────────────

    async def _notify_staff(self, guild, member, record: dict, channel) -> None:
        """Dem Team sagen, dass jemand wartet.

        Der Cooldown verhindert die Lawine bei wackliger Verbindung:
        wer zweimal hintereinander verbindet, loeste sonst zwei
        Meldungen aus.
        """
        if not store.may_ping(guild.id):
            return

        # Sitzt schon jemand vom Team im Warteraum? Dann ist die
        # Meldung ueberfluessig -- es ist ja bereits jemand da.
        if not store.PING_WHEN_STAFF_PRESENT:
            if self._staff_present(guild, channel, record):
                LOGGER.info(
                    "Keine Meldung in %s: es ist schon jemand vom Team da",
                    guild.id,
                )
                return

        if await self._send_notice(guild, member, record, channel):
            store.mark_pinged(guild.id)

    @staticmethod
    def _staff_present(guild, channel, record: dict) -> bool:
        """Sitzt jemand mit der Team-Rolle im Warteraum?

        Ohne eingestellte Rolle nicht beantwortbar -- dann lieber
        melden als schweigen: eine Meldung zu viel ist harmloser als
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
        """Die Meldung abschicken. True, wenn sie rausging.

        Der Text steht fest und ist nicht einstellbar. Er enthaelt
        genau das, was das Team braucht: wer wartet, wo, und seit wann.
        """

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
        except Exception as exc:  # noqa: BLE001 - darf nie den Rest kippen
            LOGGER.warning("Support-Hinweis fehlgeschlagen: %s", exc)
            return False

    async def _reminder_loop(self, guild, channel) -> None:
        """Erinnern, solange jemand wartet und niemand kommt.

        Prueft jede halbe Minute. Die Einstellungen werden bei jedem
        Durchgang neu gelesen: wer den Warteraum waehrend einer
        laufenden Wartezeit abschaltet, soll nicht bis zum naechsten
        Neustart warten muessen.
        """
        try:
            while True:
                await asyncio.sleep(30)

                if not self._humans_present(channel):
                    return

                record = await self.settings(guild.id)
                if not record.get("enabled"):
                    return

                if not store.due_for_reminder(guild.id):
                    continue

                # Sitzt inzwischen jemand vom Team drin, ist die
                # Erinnerung erledigt -- ohne sie zu schicken.
                if not store.PING_WHEN_STAFF_PRESENT:
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

    # ── Die Musikschleife ────────────────────────────────────────────

    async def _run_loop(self, guild, channel) -> None:
        """Wartemusik in Schleife -- bis niemand mehr da ist."""

        player = None
        try:
            player = await self._join(channel)
            if player is None:
                # Kein Lavalink. Der Bot bleibt draussen, statt stumm
                # im Kanal zu sitzen und Anwesenheit vorzutaeuschen.
                LOGGER.warning(
                    "Support-Warteraum ohne Lavalink -- keine Musik in %s. "
                    "Ist LAVALINK_HOST gesetzt?",
                    guild.id,
                )
                return

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
                "Warteraum #%s: Wartemusik (%ss je Durchgang)",
                getattr(channel, "name", channel.id), store.MUSIC_SECONDS,
            )

            while self._humans_present(channel):
                await self._play_music(player)

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
        leer, die Schleife wird nie betreten -- und das `finally`
        trennt die Verbindung. Aus Sicht des Wartenden: der Bot kommt
        und ist im selben Moment wieder weg.

        Der Voice-Zustand selbst kennt jeden im Kanal, auch ohne
        gecachten Member. Deshalb wird zuerst dort nachgesehen.
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
                # einmal zu lange spielen als den Wartenden abwuergen.
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
            # als waere er abgestuerzt.
            return await channel.connect(cls=wavelink.Player, self_deaf=False)
        except discord.ClientException:
            # Schon verbunden -- den vorhandenen Player nehmen.
            return channel.guild.voice_client
        except Exception as exc:  # noqa: BLE001
            # Mit print, nicht nur ueber den Logger: am Root-Logger
            # haengt in diesem Bot kein Handler.
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

    async def _find_track(self):
        """Die Wartemusik holen: erst die eigene Datei, dann die Suche."""

        url = _music_url()
        try:
            gefunden = await wavelink.Playable.search(url)
            if gefunden:
                return gefunden[0]
            LOGGER.warning(
                "Wartemusik %s nicht abrufbar -- weiche auf die Suche aus. "
                "Liegt die Datei unter dashboard/public/?", url,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Wartemusik %s nicht ladbar: %s", url, exc)

        try:
            gefunden = await wavelink.Playable.search(FALLBACK_MUSIC_QUERY)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Auch die Ersatzmusik fehlt: %s", exc)
            return None
        return gefunden[0] if gefunden else None

    async def _play_music(self, player) -> None:
        """Ein Durchgang Wartemusik."""

        sekunden = store.MUSIC_SECONDS
        track = await self._find_track()

        if track is None:
            # Keine Musik? Dann eben Stille -- aber die Schleife muss
            # trotzdem warten, sonst dreht sie bei voller Last durch.
            await asyncio.sleep(sekunden)
            return

        try:
            # `end` schneidet das Stueck hart auf die Dauer. Ohne diese
            # Angabe liefe ein zehnminuetiger Track durch, und die
            # Schleife koennte den Kanal nicht mehr pruefen.
            await player.play(track, volume=45, end=sekunden * 1000)
            await self._wait_until_idle(
                player, limit=sekunden + 5, floor=float(sekunden)
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Wartemusik fehlgeschlagen: %s", exc)
            await asyncio.sleep(sekunden)

    @staticmethod
    async def _wait_until_idle(player, *, limit: int, floor: float = 0.0) -> None:
        """Warten, bis das Stueck durch ist -- hoechstens `limit`.

        Zwei Grenzen, und beide sind noetig.

        Die **Obergrenze** ist der Notausgang: bleibt ein Stueck
        haengen (Lavalink verliert die Verbindung, der Track ist
        laenger als gedacht), stuende die Schleife sonst fuer immer.

        Die **Untergrenze** verhindert das Gegenteil. Meldet der Player
        sofort "spielt nicht" -- weil der Track nicht geladen werden
        konnte -- kehrt diese Funktion augenblicklich zurueck. Die
        Schleife darueber startet dann sofort die naechste Runde, und
        das Ganze dreht bei voller Last durch.

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
