#!/usr/bin/env python3
"""
Der Support-Warteraum: der Zweitbeitritt-Bug und das neue Ping-System.

── Der Fehler, der gemeldet wurde ───────────────────────────────────

"wenn man das 2 mal in den call joint kommt bot nicht".

Nachgestellt in `repro/bug_warteraum.py` und hier: `task.cancel()`
beendet eine Task **nicht sofort**. Der Abbruch wird erst zugestellt,
wenn sie das naechste Mal wartet. In der Zwischenzeit:

  1. `_maybe_stop` nimmt den Eintrag aus `_loops` und ruft `cancel()`.
  2. Dieselbe Person kommt sofort wieder rein.
  3. `_on_arrival` sieht ein leeres `_loops` und startet eine zweite
     Schleife.
  4. **Jetzt erst** kommt der Abbruch der ersten an, ihr Callback
     feuert -- und loescht mit `_loops.pop(gid)` den Eintrag der
     ZWEITEN.

Die zweite Schleife laeuft verwaist weiter, und beim naechsten
Beitritt haelt der Bot sie fuer tot. Der Callback prueft jetzt, ob
dort noch seine eigene Task steht.

Entscheidend am Nachweis: **ohne Wartezeit** zwischen Verlassen und
Wiedereintritt. Mit Wartezeit tritt der Fehler nicht auf -- genau das
ist der Unterschied zwischen einem echten Nutzer und einem geduldigen
Test.

── Das Ping-System ──────────────────────────────────────────────────

Vorher eine Regel: "Kanal eingestellt -> bei jedem Beitritt eine
Nachricht". Drei Loecher, und jedes fuehrt dazu, dass die Erwaehnung
am Ende abgeschaltet wird -- kein Cooldown, keine Erinnerung, kein
Blick darauf, ob schon jemand vom Team da ist.

Run:  python3 tests/test_warteraum.py
"""

import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, BOT)

COG = os.path.join(BOT, "cogs", "commands", "supportqueue.py")
STORE = os.path.join(BOT, "utils", "support_queue.py")
ROUTE = os.path.join(BOT, "api", "routes", "supportqueue.py")
PANEL = os.path.join(DASH, "components", "dashboard", "support-queue-panel.tsx")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(pfad: str) -> str:
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════════════
#  Attrappen
# ══════════════════════════════════════════════════════════════════════


class Zustand:
    def __init__(self, channel):
        self.channel = channel


class Mitglied:
    def __init__(self, uid, bot=False, roles=None):
        self.id = uid
        self.bot = bot
        self.mention = f"<@{uid}>"
        self.roles = roles or []
        self.guild = None


class Kanal:
    def __init__(self, kid, guild, name="warteraum"):
        self.id = kid
        self.guild = guild
        self.name = name
        self.mention = f"<#{kid}>"
        self.verbindungen = 0
        self.members = []

    async def connect(self, cls=None, self_deaf=False):
        self.verbindungen += 1
        self.guild.voice_client = Player(self)
        return self.guild.voice_client


class Player:
    def __init__(self, channel):
        self.channel = channel
        self.playing = False

    async def play(self, track, volume=100, end=None):
        self.playing = False

    async def disconnect(self):
        self.channel.guild.voice_client = None


class Server:
    def __init__(self, gid=1):
        self.id = gid
        self.name = "Testserver"
        self.me = Mitglied(999, bot=True)
        self.voice_client = None
        self._voice_states = {}
        self._kanaele = {}
        self._rollen = {}

    def get_channel(self, cid):
        return self._kanaele.get(cid)

    def get_member(self, uid):
        return None

    def get_role(self, rid):
        return self._rollen.get(rid)


def _sofort(wert):
    async def _f():
        return wert
    return _f()


def baue_cog():
    from cogs.commands import supportqueue as modul

    guild = Server()
    kanal = Kanal(50, guild)
    guild._kanaele[50] = kanal

    cog = modul.SupportQueue.__new__(modul.SupportQueue)
    cog.client = None
    cog._connection = None
    cog._loops = {}
    cog._reminders = {}

    einstellung = {
        "enabled": True, "channel_id": 50, "greeting": "Hallo",
        "music_url": "", "music_seconds": 10,
        "notify_channel_id": None, "staff_role_id": None,
        "ping_enabled": True, "ping_cooldown": 120,
        "reminder_seconds": 0, "max_reminders": 3,
        "ping_when_staff_present": False,
    }
    cog.settings = lambda gid: _sofort(einstellung)

    async def join(channel):
        return await channel.connect()

    cog._join = join
    cog._speak_greeting = lambda p, g, r: _sofort(None)
    cog._play_music = lambda p, r, s: asyncio.sleep(0.05)
    return cog, guild, kanal, einstellung


# ══════════════════════════════════════════════════════════════════════
#  1. Der Zweitbeitritt
# ══════════════════════════════════════════════════════════════════════


def test_zweiter_beitritt():
    print("\nBeim zweiten Mal kommt der Bot wieder")

    async def lauf():
        from utils import support_queue as store

        cog, guild, kanal, _ = baue_cog()
        user = Mitglied(7)
        user.guild = guild

        # Erster Beitritt.
        guild._voice_states[7] = Zustand(kanal)
        await cog.on_voice_state_update(user, Zustand(None), Zustand(kanal))
        await asyncio.sleep(0.15)
        check("erster Beitritt: der Bot verbindet sich",
              kanal.verbindungen == 1, str(kanal.verbindungen))

        # Raus und OHNE Pause sofort wieder rein. Die Pause ist der
        # ganze Unterschied: mit ihr raeumt die alte Task auf, ohne
        # sie ueberholt sie die neue.
        guild._voice_states.pop(7, None)
        await cog.on_voice_state_update(user, Zustand(kanal), Zustand(None))
        guild._voice_states[7] = Zustand(kanal)
        await cog.on_voice_state_update(user, Zustand(None), Zustand(kanal))
        await asyncio.sleep(0.4)

        check("zweiter Beitritt: der Bot verbindet sich ERNEUT",
              kanal.verbindungen == 2,
              f"nur {kanal.verbindungen} -- der Bot kam nicht wieder")
        check("und die Schleife ist eingetragen",
              guild.id in cog._loops,
              "der Callback der alten Task hat den neuen Eintrag geloescht")

        for t in list(cog._loops.values()) + list(cog._reminders.values()):
            t.cancel()
        store.reset()

    asyncio.run(lauf())


def test_callback_loescht_nur_sich_selbst():
    print("\nDer Aufraeum-Callback fasst nur die eigene Task an")

    quelle = read(COG)
    check("es gibt eine eigene Funktion dafuer",
          "def _forget_loop" in quelle,
          "ein lambda mit pop() loescht, was gerade dasteht")
    check("sie vergleicht die Task",
          re.search(r"if self\._loops\.get\(guild_id\) is beendete:", quelle)
          is not None,
          "`is` und nicht `==`: es geht um dieselbe Task, nicht um "
          "Gleichheit")
    check("das alte lambda mit pop ist weg",
          "lambda _t, gid=guild.id: self._loops.pop(gid, None)" not in quelle)

    # Dasselbe fuer die Erinnerungen.
    check("auch die Erinnerungen haben so einen Callback",
          "def _forget_reminder" in quelle)

    # Und `_maybe_stop` muss auf das Ende warten, bevor eine neue
    # Schleife starten kann.
    check("beim Leeren wird auf das Ende gewartet",
          "asyncio.wait_for(asyncio.shield(task)" in quelle,
          "sonst laufen zwei Schleifen auf demselben Player")


# ══════════════════════════════════════════════════════════════════════
#  2. Das Ping-System
# ══════════════════════════════════════════════════════════════════════


def test_cooldown():
    print("\nDer Ping hat eine Pause")

    from utils import support_queue as store

    store.reset_pings()
    r = {
        "ping_enabled": True, "notify_channel_id": 99,
        "ping_cooldown": 120,
    }
    check("der erste Ping geht durch", store.may_ping(r, 1, now=1000))
    store.mark_pinged(1, now=1000)
    check("der zweite sofort danach nicht",
          not store.may_ping(r, 1, now=1010),
          "sonst pingt jeder Verbindungsabbruch erneut")
    check("nach 119 Sekunden noch nicht",
          not store.may_ping(r, 1, now=1119))
    check("nach 120 Sekunden wieder", store.may_ping(r, 1, now=1120))

    aus = {**r, "ping_enabled": False}
    check("abgeschaltet heisst abgeschaltet",
          not store.may_ping(aus, 1, now=99999))
    ohne = {**r, "notify_channel_id": None}
    check("ohne Meldekanal passiert nichts",
          not store.may_ping(ohne, 1, now=99999))

    # Cooldown 0 heisst: jedes Mal. Das muss moeglich bleiben, sonst
    # laesst sich das alte Verhalten nicht wiederherstellen.
    null = {**r, "ping_cooldown": 0}
    store.mark_pinged(1, now=99999)
    check("Pause 0 -> immer erlaubt", store.may_ping(null, 1, now=99999))
    store.reset_pings()


def test_erinnerungen():
    print("\nErinnerungen, solange niemand kommt")

    from utils import support_queue as store

    store.reset()
    store.reset_pings()
    r = {
        "ping_enabled": True, "notify_channel_id": 99,
        "reminder_seconds": 300, "max_reminders": 3,
    }

    check("ohne Wartende keine Erinnerung",
          not store.due_for_reminder(r, 1, now=99999))

    store.mark_waiting(1, 7)
    seit = store.waiting(1)[7]
    check("kurz nach der Ankunft noch nicht",
          not store.due_for_reminder(r, 1, now=seit + 10))
    check("nach 300 Sekunden faellig",
          store.due_for_reminder(r, 1, now=seit + 300))

    for i in range(3):
        store.mark_reminded(1, now=seit + 300 + i)
    check("nach drei Erinnerungen ist Schluss",
          not store.due_for_reminder(r, 1, now=seit + 99999),
          "ohne Grenze pingt der Bot ewig weiter")

    store.reset_pings(1)
    aus = {**r, "reminder_seconds": 0}
    check("Erinnerung 0 -> nie",
          not store.due_for_reminder(aus, 1, now=seit + 99999))

    # Der aelteste Wartende zaehlt, nicht der neueste: wer am
    # laengsten wartet, ist der Grund fuer die Erinnerung.
    store.reset(1)
    store.reset_pings(1)
    store.mark_waiting(1, 7)
    alt = store.waiting(1)[7]
    store._waiting[1][8] = alt + 250      # jemand kam spaeter dazu
    check("der aelteste Wartende gibt den Takt vor",
          store.due_for_reminder(r, 1, now=alt + 300),
          "sonst verlaengert jeder Neuankoemmling die Wartezeit der "
          "anderen")
    store.reset()
    store.reset_pings()


def test_leerer_raum_setzt_zurueck():
    print("\nEin leerer Warteraum vergisst den Cooldown")

    from utils import support_queue as store

    store.reset()
    store.reset_pings()
    r = {"ping_enabled": True, "notify_channel_id": 99, "ping_cooldown": 120}

    store.mark_pinged(1, now=1000)
    check("gesperrt", not store.may_ping(r, 1, now=1010))
    store.reset(1)
    check("nach dem Leeren wieder frei",
          store.may_ping(r, 1, now=1010),
          "sonst wird der naechste Wartende verschluckt -- der Cooldown "
          "galt einem anderen Menschen")

    check("reset nimmt den Ping-Zustand mit",
          "reset_pings(guild_id)" in read(STORE))
    store.reset_pings()


def test_team_schon_da():
    print("\nKein Ping, wenn schon jemand vom Team da ist")

    quelle = read(COG)
    check("es gibt die Pruefung", "_staff_present" in quelle)
    # Die Pruefung steht an ZWEI Stellen: beim ersten Ping und in der
    # Erinnerungsschleife. Ein Muster, das irgendeine davon findet,
    # bleibt gruen, wenn die andere ausgehebelt wird -- genau so ist
    # die Mutation zuerst entwischt. Also beide einzeln.
    treffer = re.findall(
        r'if not record\.get\("ping_when_staff_present"\):\s*\n'
        r'\s*if self\._staff_present\(guild, channel, record\):\s*\n'
        r'(?:\s*LOGGER[^\n]*\n(?:\s+[^\n]*\n)*?)?\s*return',
        quelle,
    )
    check("beide Stellen steigen wirklich aus, wenn das Team da ist",
          len(treffer) == 2,
          f"nur {len(treffer)} von 2 -- `if False:` laesst die Namen "
          "stehen und pingt trotzdem")
    check("und sie ist abschaltbar",
          "ping_when_staff_present" in quelle,
          "manche Teams wollen die Meldung trotzdem im Log")

    # Ohne eingestellte Rolle nicht beantwortbar -- dann lieber pingen.
    from cogs.commands import supportqueue as modul

    guild = Server()
    kanal = Kanal(50, guild)
    check("ohne Team-Rolle gilt: niemand da",
          not modul.SupportQueue._staff_present(guild, kanal, {}),
          "eine Meldung zu viel ist harmloser als ein uebersehener "
          "Wartender")

    class Rolle:
        def __init__(self, rid):
            self.id = rid

    rolle = Rolle(77)
    guild._rollen[77] = rolle
    kanal.members = [Mitglied(7, roles=[])]
    check("Wartender ohne Team-Rolle zaehlt nicht",
          not modul.SupportQueue._staff_present(
              guild, kanal, {"staff_role_id": 77}))

    kanal.members = [Mitglied(8, roles=[rolle])]
    check("Teammitglied wird erkannt",
          modul.SupportQueue._staff_present(
              guild, kanal, {"staff_role_id": 77}))

    kanal.members = [Mitglied(9, bot=True, roles=[rolle])]
    check("ein Bot mit der Rolle zaehlt nicht",
          not modul.SupportQueue._staff_present(
              guild, kanal, {"staff_role_id": 77}),
          "sonst haelt sich der Bot selbst fuer das Team")


def test_erinnerungsschleife_ist_getrennt():
    print("\nDie Erinnerungen laufen unabhaengig von der Musik")

    quelle = read(COG)
    check("es gibt eine eigene Schleife", "_reminder_loop" in quelle)
    check("mit eigenem Dict", "self._reminders" in quelle)
    check("sie liest die Einstellungen bei jedem Durchgang neu",
          re.search(r"while True:.*?await self\.settings\(guild\.id\)",
                    quelle, re.S) is not None,
          "wer die Erinnerung abschaltet, soll nicht bis zum Neustart "
          "warten")
    schleife = re.search(
        r"async def _reminder_loop\(.*?\n(?=    def |    async def |\Z)",
        quelle, re.S,
    )
    check("die Schleife ist lesbar", schleife is not None)
    if schleife:
        rumpf = schleife.group(0)
        # Die Wirkung, nicht das Wort: `if False:` liesse den Namen
        # stehen und die Schleife ewig laufen.
        check("sie endet, wenn niemand mehr da ist",
              re.search(
                  r"if not self\._humans_present\(channel\):\s*\n\s*return",
                  rumpf,
              ) is not None,
              "sonst erinnert der Bot an einen leeren Raum")
    check("beim Leeren wird sie abgebrochen",
          "self._reminders.pop(guild.id, None)" in quelle)


# ══════════════════════════════════════════════════════════════════════
#  3. Speicher, API, Oberflaeche
# ══════════════════════════════════════════════════════════════════════


def test_schema_wird_nachgeruestet():
    print("\nDie neuen Spalten kommen auf alte Tabellen")

    async def lauf():
        import aiosqlite
        from utils import support_queue as store

        ordner = tempfile.mkdtemp()
        pfad = os.path.join(ordner, "alt.db")
        db = await aiosqlite.connect(pfad)
        # Eine Tabelle im alten Zustand -- genau der Fall, an dem
        # `team_update` schon einmal gescheitert ist.
        await db.execute(
            "CREATE TABLE support_queue (guild_id INTEGER PRIMARY KEY,"
            " channel_id INTEGER, enabled INTEGER, greeting TEXT,"
            " music_url TEXT, music_seconds INTEGER,"
            " notify_channel_id INTEGER, staff_role_id INTEGER,"
            " updated_at REAL)"
        )
        await db.execute(
            "INSERT INTO support_queue (guild_id, enabled) VALUES (5, 1)"
        )
        await db.commit()

        await store.ensure_schema(db)
        record = await store.get(db, 5)

        check("die alte Zeile bleibt lesbar", record["enabled"] is True)
        for feld in ("ping_enabled", "ping_cooldown", "reminder_seconds",
                     "max_reminders", "ping_when_staff_present"):
            check(f"{feld} ist da", feld in record)
        check("und traegt einen Vorgabewert",
              record["ping_cooldown"] == store.DEFAULT_PING_COOLDOWN,
              str(record.get("ping_cooldown")))
        check("Ping ist dabei AN",
              record["ping_enabled"] is True,
              "ein Update darf die Meldung nicht stillschweigend "
              "abschalten")

        # Und der Fall, den `ALTER TABLE ... DEFAULT 1` NICHT abdeckt:
        # eine Zeile, in der die Spalte wirklich NULL ist.
        #
        # Gemessen: das Nachruesten fuellt bestehende Zeilen mit 1,
        # der Wert ist also nie None -- solange niemand ihn
        # ausdruecklich auf NULL setzt. Genau das passiert aber, wenn
        # eine aeltere Fassung des Bots dieselbe Datei beschreibt.
        # Ohne die Behandlung in `get()` waere `bool(None)` dann
        # False, und die Meldung waere still abgeschaltet.
        await db.execute(
            "UPDATE support_queue SET ping_enabled = NULL WHERE guild_id = 5"
        )
        await db.commit()
        record = await store.get(db, 5)
        check("auch eine NULL-Spalte bedeutet AN",
              record["ping_enabled"] is True,
              "bool(None) waere False -- die Meldung waere stumm")

        await db.execute(
            "UPDATE support_queue SET ping_cooldown = NULL WHERE guild_id = 5"
        )
        await db.commit()
        record = await store.get(db, 5)
        check("und eine NULL-Zahl faellt auf die Vorgabe",
              record["ping_cooldown"] == store.DEFAULT_PING_COOLDOWN,
              "int(None) wuerde werfen und den Warteraum stilllegen")
        await db.close()

    asyncio.run(lauf())

    # Die Spalten stehen an EINER Stelle.
    quelle = read(STORE)
    check("die Spaltenliste steht einmal", "PING_COLUMNS" in quelle,
          "zwei Listen laufen auseinander")


def test_grenzen():
    print("\nGrenzen gelten auch ohne Browser")

    async def lauf():
        import aiosqlite
        from utils import support_queue as store

        ordner = tempfile.mkdtemp()
        db = await aiosqlite.connect(os.path.join(ordner, "x.db"))
        await store.ensure_schema(db)

        r = await store.save(
            db, 1, ping_cooldown=99999, reminder_seconds=-5,
            max_reminders=500,
        )
        check("Pause gedeckelt",
              r["ping_cooldown"] == store.MAX_PING_COOLDOWN,
              str(r["ping_cooldown"]))
        check("Erinnerung nicht negativ", r["reminder_seconds"] == 0,
              str(r["reminder_seconds"]))
        check("Anzahl gedeckelt",
              r["max_reminders"] == store.MAX_MAX_REMINDERS,
              str(r["max_reminders"]))

        # Unsinn darf nicht durchrutschen -- die Route ist per HTTP
        # erreichbar, und curl fuellt kein Formular aus.
        r = await store.save(db, 1, ping_cooldown="abc")
        check("Text statt Zahl faellt auf die Vorgabe zurueck",
              r["ping_cooldown"] == store.DEFAULT_PING_COOLDOWN,
              str(r["ping_cooldown"]))
        await db.close()

    asyncio.run(lauf())


def test_api():
    print("\nDie Schnittstelle")

    quelle = read(ROUTE)

    # Nur den Speichern-Teil ansehen. Die Feldnamen stehen auch in
    # `_ping_limits` -- eine Suche ueber die ganze Datei fand sie
    # dort und blieb gruen, obwohl die Route nichts mehr annahm.
    speichern = re.search(
        r"async def save_settings\(.*?\n(?=@router\.|\Z)", quelle, re.S
    )
    check("die Speicher-Route ist lesbar", speichern is not None)
    if speichern:
        rumpf = speichern.group(0)
        for feld in ("ping_enabled", "ping_cooldown", "reminder_seconds",
                     "max_reminders", "ping_when_staff_present"):
            check(f"{feld} wird entgegengenommen", feld in rumpf,
                  "sonst laesst es sich nicht speichern")

    # Und die Grenzen muessen in der ANTWORT stehen, nicht nur als
    # Funktion existieren.
    antwort = re.search(
        r"async def get_settings\(.*?\n(?=@router\.|\Z)", quelle, re.S
    )
    check("die Lese-Route ist lesbar", antwort is not None)
    if antwort:
        check("die Grenzen kommen mit",
              '"ping_limits"' in antwort.group(0),
              "sonst pflegt der Browser sie noch einmal und weicht ab")
    if antwort:
        check("die Zahl der Erinnerungen steht drin",
              '"reminders_sent"' in antwort.group(0),
              "sonst sieht die erreichte Obergrenze wie ein Fehler aus")

    # Die Grenzen selbst gehoeren in den Speicher, nicht in die Route.
    check("die Route setzt die Grenzen nicht selbst durch",
          "MAX_PING_COOLDOWN" not in quelle.split("def _ping_limits")[-1]
          .split("@router.post")[-1],
          "zweimal dieselbe Regel laeuft auseinander")


def test_panel():
    print("\nDer Reiter im Dashboard")

    quelle = read(PANEL)
    for feld in ("pingEnabled", "pingCooldown", "reminderSeconds",
                 "maxReminders", "pingWhenStaff"):
        check(f"{feld} ist da", feld in quelle)

    check("alles wird mitgespeichert",
          "ping_cooldown: pingCooldown" in quelle
          and "reminder_seconds: reminderSeconds" in quelle)

    # Ohne gespeicherten Wert muss der Ping AN sein.
    check("fehlender Wert heisst AN",
          "answer.ping_enabled !== false" in quelle,
          "`Boolean(undefined)` waere false -- das Update haette die "
          "Meldung stillschweigend abgeschaltet")

    # Ein Warnhinweis, wenn kein Meldekanal gewaehlt ist: sonst stellt
    # jemand die Pausen ein und wundert sich, dass nichts kommt.
    check("es warnt ohne Meldekanal",
          "kein Meldekanal" in quelle,
          "sonst stellt man Pausen ein, die nie greifen")


def main() -> int:
    test_zweiter_beitritt()
    test_callback_loescht_nur_sich_selbst()
    test_cooldown()
    test_erinnerungen()
    test_leerer_raum_setzt_zurueck()
    test_team_schon_da()
    test_erinnerungsschleife_ist_getrennt()
    test_schema_wird_nachgeruestet()
    test_grenzen()
    test_api()
    test_panel()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for eintrag in failures:
            print(f"  - {eintrag}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
