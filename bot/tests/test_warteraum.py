#!/usr/bin/env python3
"""
Der Support-Warteraum, nach dem Umbau auf vier Einstellungen.

Was sich geaendert hat
----------------------
Vorher acht Felder im Dashboard: eigene Ansage, Musik-URL, Dauer,
Cooldown, Erinnerungsabstand, Zahl der Erinnerungen,
Ping-trotz-Team, Meldekanal. Jetzt vier:

    an/aus · Warteraum-Kanal · Meldekanal · Team-Rolle

Alles Uebrige steht fest in `utils/support_queue.py`. Die Ansage per
Sprachausgabe ist ganz entfallen -- es laeuft nur noch die
mitgelieferte Wartemusik.

Was hier geprueft wird
----------------------
1. Der Beitritt, auch beim zweiten und dritten Mal ohne Pause.
   Das war der gemeldete Fehler: `_loops.pop(gid)` im done_callback
   loeschte den Eintrag einer *anderen* Task.
2. Die vier Einstellungen -- und dass die alten Felder nicht mehr
   gespeichert werden.
3. Das Ping-System: Cooldown, Erinnerungen, Obergrenze.
4. Die Wartemusik: gueltige MP3, ueber HTTP erreichbar, im Image.
5. Das Dashboard zeigt genau vier Einstellungen.

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

failures: list[str] = []
START = os.getcwd()

GILDE = 1530378233579704370
KANAL = 900001


def check(name: str, ok: bool, hinweis: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        failures.append(name)


def linie(t: str) -> None:
    print()
    print("=" * 66)
    print(t)
    print("=" * 66)


def strip_ts(src: str) -> str:
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare."""
    ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


def strip_py(src: str) -> str:
    ohne_doc = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"#[^\n]*", "", ohne_doc)


# ── Attrappen ────────────────────────────────────────────────────────

class FakeState:
    def __init__(self, channel):
        self.channel = channel


class FakeMember:
    def __init__(self, mid, bot=False, rollen=None):
        self.id = mid
        self.bot = bot
        self.roles = rollen or []
        self.mention = f"<@{mid}>"
        self.display_name = f"User{mid}"
        self.display_avatar = None
        self.guild = None


class FakeChannel:
    def __init__(self, cid, guild, name="warteraum"):
        self.id = cid
        self.guild = guild
        self.name = name
        self.mention = f"<#{cid}>"

    @property
    def members(self):
        raus = []
        for uid, st in self.guild._voice_states.items():
            if st.channel is not None and st.channel.id == self.id:
                m = self.guild.get_member(uid)
                if m is not None:
                    raus.append(m)
        return raus


class FakeGuild:
    def __init__(self):
        self.id = GILDE
        self.name = "Testserver"
        self._voice_states = {}
        self._members = {}
        self._channels = {}
        self.me = FakeMember(999999, bot=True)
        self.voice_client = None

    def get_member(self, uid):
        return self._members.get(uid)

    def get_channel(self, cid):
        return self._channels.get(cid)

    def get_role(self, rid):
        return None


def baue_cog():
    """Der Cog mit abgeschaltetem Audio."""
    from cogs.commands.supportqueue import SupportQueue

    cog = SupportQueue.__new__(SupportQueue)
    cog.client = None
    cog._connection = None
    cog._loops = {}
    cog._reminders = {}
    cog.beitritte = 0

    class FakePlayer:
        def __init__(self):
            self.playing = False

        async def play(self, *a, **kw):
            self.playing = False

        async def disconnect(self):
            pass

    async def fake_join(channel):
        cog.beitritte += 1
        p = FakePlayer()
        channel.guild.voice_client = p
        return p

    async def fake_track():
        return None

    cog._join = fake_join
    cog._find_track = fake_track
    return cog


# ── 1. Der Beitritt ──────────────────────────────────────────────────

def test_beitritt() -> None:
    linie("1  Der Beitritt -- auch beim zweiten und dritten Mal")

    import aiosqlite

    from utils import support_queue as store

    ordner = tempfile.mkdtemp(prefix="wr-")
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)

    async def lauf():
        db = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(db)
        await store.save(db, GILDE, enabled=True, channel_id=KANAL)

        cog = baue_cog()
        cog._connection = db

        g = FakeGuild()
        k = FakeChannel(KANAL, g)
        g._channels[KANAL] = k
        person = FakeMember(111)
        person.guild = g
        g._members[111] = person

        rec = await store.get(db, GILDE)

        for runde in (1, 2, 3):
            # Beitritt
            g._voice_states[111] = FakeState(k)
            await cog._on_arrival(g, person, rec)
            await asyncio.sleep(0.35)

            check(f"Runde {runde}: der Bot kommt",
                  cog.beitritte == runde,
                  f"Beitritte: {cog.beitritte}, erwartet {runde}")
            check(f"Runde {runde}: die Schleife lebt",
                  GILDE in cog._loops and not cog._loops[GILDE].done(),
                  str(list(cog._loops)))

            # Sofort wieder raus -- OHNE Wartezeit. Genau daran ist
            # die alte Fassung gescheitert.
            g._voice_states.pop(111, None)
            await cog._maybe_stop(g, KANAL)

        check("nach dem Letzten ist die Schleife weg",
              GILDE not in cog._loops, str(list(cog._loops)))

        # Zwei Personen: der Bot darf nicht zweimal kommen.
        cog.beitritte = 0
        p2 = FakeMember(222)
        p2.guild = g
        g._members[222] = p2

        g._voice_states[111] = FakeState(k)
        await cog._on_arrival(g, person, rec)
        await asyncio.sleep(0.3)
        g._voice_states[222] = FakeState(k)
        await cog._on_arrival(g, p2, rec)
        await asyncio.sleep(0.2)

        check("bei zwei Wartenden kommt der Bot nur einmal",
              cog.beitritte == 1, f"Beitritte: {cog.beitritte}")

        # Einer geht, der andere bleibt.
        g._voice_states.pop(111, None)
        await cog._maybe_stop(g, KANAL)
        check("der Bot bleibt, solange noch jemand da ist",
              GILDE in cog._loops,
              "die Schleife wurde beendet, obwohl noch jemand wartet")

        # `_maybe_stop` muss auf das Ende der alten Schleife WARTEN.
        #
        # Ohne das laeuft sie noch, waehrend schon eine neue startet
        # -- zwei Schleifen auf demselben Player, und das `finally`
        # der alten trennt die Verbindung der neuen. Der Bot kaeme
        # rein und sofort wieder raus.
        #
        # Nachweisbar am Zustand der Task direkt nach dem Aufruf: ist
        # sie danach noch nicht beendet, wurde nicht gewartet.
        g._voice_states.clear()
        laufende = cog._loops.get(GILDE)
        await cog._maybe_stop(g, KANAL)
        check("_maybe_stop wartet, bis die alte Schleife wirklich aus ist",
              laufende is None or laufende.done(),
              "sonst treffen zwei Schleifen auf denselben Player")

        await db.close()

    asyncio.run(lauf())
    os.chdir(START)


def test_callback_loescht_nur_sich_selbst() -> None:
    """Der eigentliche Fix, isoliert.

    `_forget_loop` darf nur den EIGENEN Eintrag entfernen. Sonst
    loescht der verspaetete Abbruch der ersten Schleife den Eintrag
    der zweiten -- und beim naechsten Beitritt haelt der Bot sie fuer
    tot.
    """
    linie("2  Der Callback loescht nur seinen eigenen Eintrag")

    async def lauf():
        cog = baue_cog()

        async def nichts():
            await asyncio.sleep(3600)

        erste = asyncio.create_task(nichts())
        zweite = asyncio.create_task(nichts())

        # Die zweite steht drin -- die erste ist Vergangenheit.
        cog._loops[GILDE] = zweite

        cog._forget_loop(GILDE, erste)
        check("ein fremder Callback loescht nichts",
              cog._loops.get(GILDE) is zweite,
              "der Eintrag der zweiten Schleife wurde entfernt")

        cog._forget_loop(GILDE, zweite)
        check("der eigene Callback loescht", GILDE not in cog._loops)

        erste.cancel()
        zweite.cancel()

    asyncio.run(lauf())


# ── 3. Die vier Einstellungen ────────────────────────────────────────

def test_einstellungen() -> None:
    linie("3  Nur noch vier Einstellungen")

    import aiosqlite

    from utils import support_queue as store

    ordner = tempfile.mkdtemp(prefix="wrset-")
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)

    async def lauf():
        db = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(db)

        leer = await store.get(db, GILDE)
        check("ein unbekannter Server liefert Voreinstellungen",
              leer["enabled"] is False and leer["channel_id"] is None)

        rec = await store.save(
            db, GILDE, enabled=True, channel_id=KANAL,
            notify_channel_id=777, staff_role_id=888,
        )
        check("die vier Felder werden gespeichert",
              rec["enabled"] and rec["channel_id"] == KANAL
              and rec["notify_channel_id"] == 777
              and rec["staff_role_id"] == 888,
              str(rec))

        # Die alten Felder darf es nicht mehr geben.
        for alt in ("greeting", "music_url", "music_seconds",
                    "ping_cooldown", "reminder_seconds", "max_reminders",
                    "ping_enabled", "ping_when_staff_present"):
            check(f"'{alt}' ist aus der Antwort verschwunden",
                  alt not in rec,
                  "es soll nicht mehr einstellbar sein")

        # Und sie duerfen sich auch nicht mehr setzen lassen.
        vorher = dict(rec)
        rec2 = await store.save(db, GILDE, greeting="Hallo", music_url="x",
                                music_seconds=999)
        check("unbekannte Felder werden ignoriert",
              rec2["channel_id"] == vorher["channel_id"]
              and "greeting" not in rec2)

        # Ein Feld aendern laesst die anderen stehen.
        rec3 = await store.save(db, GILDE, staff_role_id=None)
        check("ein einzelnes Feld aendern loescht nichts anderes",
              rec3["channel_id"] == KANAL and rec3["notify_channel_id"] == 777
              and rec3["staff_role_id"] is None)

        await db.close()

    asyncio.run(lauf())
    os.chdir(START)


# ── 4. Das Ping-System ───────────────────────────────────────────────

def test_ping() -> None:
    linie("4  Das Ping-System")

    from utils import support_queue as store

    store.reset(GILDE)

    check("die erste Meldung darf sofort raus", store.may_ping(GILDE))

    store.mark_pinged(GILDE, now=1000.0)
    check("direkt danach nicht noch einmal",
          not store.may_ping(GILDE, now=1000.0 + 1))
    check("kurz vor Ablauf immer noch nicht",
          not store.may_ping(GILDE, now=1000.0 + store.PING_COOLDOWN - 1))
    check("nach dem Cooldown wieder",
          store.may_ping(GILDE, now=1000.0 + store.PING_COOLDOWN))

    # Erinnerungen.
    store.reset(GILDE)
    check("ohne erste Meldung gibt es nichts zu erinnern",
          not store.due_for_reminder(GILDE, now=99999.0),
          "sonst erinnert der Bot an etwas, das nie gemeldet wurde")

    store.mark_pinged(GILDE, now=1000.0)
    check("kurz danach ist nichts faellig",
          not store.due_for_reminder(GILDE, now=1000.0 + 10))
    check("nach der Wartezeit schon",
          store.due_for_reminder(GILDE, now=1000.0 + store.REMINDER_SECONDS))

    # Obergrenze.
    jetzt = 1000.0
    for i in range(store.MAX_REMINDERS):
        jetzt += store.REMINDER_SECONDS
        check(f"Erinnerung {i + 1} ist faellig",
              store.due_for_reminder(GILDE, now=jetzt))
        store.mark_reminded(GILDE, now=jetzt)

    jetzt += store.REMINDER_SECONDS
    check("nach der Obergrenze ist Ruhe",
          not store.due_for_reminder(GILDE, now=jetzt),
          f"{store.reminders_sent(GILDE)} von {store.MAX_REMINDERS} geschickt")

    # Der Ping-Zustand muss beim Leeren mitgehen.
    store.reset(GILDE)
    check("nach dem Zuruecksetzen darf sofort wieder gemeldet werden",
          store.may_ping(GILDE),
          "sonst haengt der naechste Wartende im Cooldown des Vorgaengers")
    check("und der Erinnerungszaehler steht auf null",
          store.reminders_sent(GILDE) == 0)


# ── 5. Die Wartemusik ────────────────────────────────────────────────

def test_musik() -> None:
    linie("5  Die Wartemusik")

    pfad = os.path.join(DASH, "public", "warteraum.mp3")
    check("die Datei liegt in dashboard/public/", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    daten = open(pfad, "rb").read()
    check("sie ist nicht leer", len(daten) > 10000, f"{len(daten)} Bytes")

    # Ein echter MPEG-Rahmen faengt mit 0xFF 0xEx an, eine Datei mit
    # ID3-Kopf mit "ID3". Alles andere ist keine MP3.
    ist_mpeg = daten[:2] == b"\xff\xfb" or daten[0] == 0xFF and (daten[1] & 0xE0) == 0xE0
    ist_id3 = daten[:3] == b"ID3"
    check("sie ist eine echte MP3", ist_mpeg or ist_id3,
          f"Anfang: {daten[:4].hex()}")

    # Rahmen zaehlen -- eine abgeschnittene Datei haette keine
    # durchgehende Kette.
    BITRATE = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    RATE = [44100, 48000, 32000, 0]
    i, rahmen = 0, 0
    while i < len(daten) - 4:
        if daten[i] == 0xFF and (daten[i + 1] & 0xE0) == 0xE0:
            br = BITRATE[(daten[i + 2] >> 4) & 0xF]
            sr = RATE[(daten[i + 2] >> 2) & 0x3]
            if br and sr:
                i += int(144000 * br / sr) + ((daten[i + 2] >> 1) & 1)
                rahmen += 1
                continue
        i += 1

    dauer = rahmen * 1152 / 44100
    check("sie ist abspielbar (durchgehende Rahmenkette)",
          rahmen > 500, f"{rahmen} Rahmen")
    # Keine feste Erwartung an die Laenge mehr: der Nutzer tauscht
    # die Datei aus, und sie laeuft jetzt ganz durch statt nach einer
    # festen Zeit abgeschnitten zu werden. Nur die Obergrenze zaehlt.
    from utils import support_queue as _sq
    check("sie ist laenger als ein Augenblick und kuerzer als die Obergrenze",
          5 < dauer <= _sq.MAX_TRACK_SECONDS,
          f"{dauer:.1f}s gegen Obergrenze {_sq.MAX_TRACK_SECONDS}s")

    # Der Weg ins Image.
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    check("das Dockerfile kopiert public/ in den Container",
          re.search(r"COPY\s+--from=dashboard-builder\s+\S*dashboard/public",
                    dockerfile) is not None,
          "ohne das fehlt die Musik im Betrieb")

    # .gitignore darf sie nicht schlucken.
    ignore = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    zeilen = [z.strip() for z in ignore.splitlines()
              if z.strip() and not z.strip().startswith("#")]
    check("keine .gitignore-Regel schluckt die MP3",
          not any(z in ("*.mp3", "public/", "dashboard/public/") for z in zeilen),
          str([z for z in zeilen if "mp3" in z or "public" in z]))

    # Der Cog muss sie ueber HTTP holen -- Lavalink laeuft als eigener
    # Dienst und sieht das Dateisystem des Bots nicht.
    quelle = open(os.path.join(BOT, "cogs", "commands", "supportqueue.py"),
                  encoding="utf-8").read()
    ohne = strip_py(quelle)
    check("der Cog kennt die Datei", "warteraum.mp3" in quelle)
    # Auf die Benutzung zielen, nicht auf das Vorkommen: die Funktion
    # muss auch AUFGERUFEN werden. Wird sie nur definiert und nie
    # benutzt, sucht der Bot die Datei nirgends -- und Lavalink kann
    # sie ohnehin nicht lokal lesen (local: false).
    check("die Adresse wird gebaut", "def _music_url" in ohne)

    # Und der Name muss wirklich aufloesbar sein.
    #
    # Eine Umbenennung der Definition -- ohne den Aufruf mitzuziehen
    # -- liesse den Text oben unveraendert aussehen, waere zur
    # Laufzeit aber ein NameError beim ersten Wartenden. Der Import
    # allein faengt das nicht: die Funktion wird erst beim Abspielen
    # gerufen. Also ausdruecklich nachsehen, ob es sie gibt.
    from cogs.commands import supportqueue as cog_modul

    check("_music_url ist im Modul wirklich vorhanden",
          callable(getattr(cog_modul, "_music_url", None)),
          "der Aufruf liefe sonst in einen NameError")

    adresse = cog_modul._music_url()
    check("sie liefert eine HTTP-Adresse auf die Datei",
          adresse.startswith("http") and adresse.endswith(cog_modul.MUSIC_FILE),
          adresse)
    check("und auch benutzt",
          re.search(r"=\s*_music_url\(\)", ohne) is not None,
          "sonst wird die feste Datei nie abgerufen")
    check("die Adresse ist eine HTTP-Adresse",
          re.search(r"https?://", ohne) is not None,
          "local: false in application.yml -- Lavalink kann keine "
          "Datei aus dem Bot-Container lesen")

    yml = os.path.join(ROOT, "lavalink", "application.yml")
    if os.path.isfile(yml):
        inhalt = open(yml, encoding="utf-8").read()
        check("Lavalink darf HTTP-Quellen abspielen",
              re.search(r"http:\s*true", inhalt) is not None,
              "sonst kann es die MP3 nicht laden")


# ── 6. Keine eigene Musik, keine eigene Nachricht ────────────────────

def test_nichts_mehr_einstellbar() -> None:
    linie("6  Musik und Nachricht sind nicht mehr einstellbar")

    cog = open(os.path.join(BOT, "cogs", "commands", "supportqueue.py"),
               encoding="utf-8").read()
    ohne_cog = strip_py(cog)

    check("keine Sprachausgabe mehr",
          "_speak_greeting" not in ohne_cog and "_tts_track" not in ohne_cog,
          "die Ansage ist entfallen")
    check("keine translate-URL mehr",
          "translate.google" not in ohne_cog)

    # Die Musik darf nicht mehr aus dem Datensatz kommen.
    check("die Musik kommt nicht aus den Einstellungen",
          'record.get("music_url")' not in ohne_cog
          and "record.get('music_url')" not in ohne_cog,
          "sie soll fest sein")
    # Die Dauer kommt jetzt vom Track selbst -- eine feste Zahl
    # schnitt die 85-Sekunden-Datei nach 30 Sekunden ab.
    check("die Dauer kommt vom Track, nicht aus dem Datensatz",
          "_track_seconds" in ohne_cog
          and 'record.get("music_seconds")' not in ohne_cog)

    # Und `_play_music` muss sie auch BENUTZEN. Ein fest verdrahtetes
    # `sekunden = 30` haette die Pruefung oben ueberlebt -- die
    # Funktion existiert ja weiterhin.
    rumpf_play = ohne_cog[ohne_cog.find("async def _play_music"):]
    rumpf_play = rumpf_play[:rumpf_play.find("@staticmethod\n    async def _wait_until_idle")]
    check("_play_music fragt den Track nach seiner Laenge",
          "self._track_seconds(track)" in rumpf_play,
          "sonst wird die Datei wieder nach fester Zeit abgeschnitten")
    check("keine fest verdrahtete Sekundenzahl in _play_music",
          not re.search(r"sekunden\s*=\s*\d+", rumpf_play),
          "die Laenge muss vom Stueck kommen")
    check("es gibt nur noch eine Obergrenze",
          "store.MAX_TRACK_SECONDS" in ohne_cog)

    routen = open(os.path.join(BOT, "api", "routes", "supportqueue.py"),
                  encoding="utf-8").read()
    ohne_routen = strip_py(routen)

    for feld in ("greeting", "music_url", "music_seconds", "ping_cooldown",
                 "reminder_seconds", "max_reminders", "ping_enabled"):
        check(f"die Route nimmt '{feld}' nicht mehr entgegen",
              f'"{feld}" in data' not in ohne_routen,
              "es soll nicht mehr einstellbar sein")

    check("es gibt keine Probe-Route mehr",
          "/test" not in ohne_routen,
          "ohne Ansage gibt es nichts probezuhoeren")

    store_py = open(os.path.join(BOT, "utils", "support_queue.py"),
                    encoding="utf-8").read()
    ohne_store = strip_py(store_py)
    spalten = re.search(r"COLUMNS[^=]*=\s*\((.*?)\n\)", ohne_store, re.S)
    check("die Spaltenliste ist auffindbar", spalten is not None)
    if spalten:
        namen = re.findall(r'\("(\w+)"', spalten.group(1))
        check("genau die vier Felder plus Zeitstempel",
              set(namen) == {"channel_id", "enabled", "notify_channel_id",
                             "staff_role_id", "updated_at"},
              str(namen))


# ── 7. Das Dashboard ─────────────────────────────────────────────────

def test_dashboard() -> None:
    linie("7  Das Dashboard")

    panel = os.path.join(DASH, "components", "dashboard",
                         "support-queue-panel.tsx")
    check("das Panel gibt es", os.path.isfile(panel))
    if not os.path.isfile(panel):
        return

    p = strip_ts(open(panel, encoding="utf-8").read())

    # Die vier Felder muessen da sein.
    for feld in ("enabled", "channel_id", "notify_channel_id", "staff_role_id"):
        check(f"das Panel kennt {feld}", feld in p)

    # Und die alten duerfen nicht mehr EINSTELLBAR sein.
    #
    # Auf die Wirkung zielen, nicht auf das Wort: `music_seconds`
    # steht weiterhin im Panel -- aber nur als Anzeige im Block
    # „Fest eingestellt" (`fest.music_seconds`). Eine Pruefung auf
    # blosses Vorkommen schlug deshalb faelschlich an. Entscheidend
    # ist, ob es einen Zustand dafuer gibt oder ob es mitgespeichert
    # wird.
    for alt in ("greeting", "music_url", "musicUrl", "music_seconds",
                "ping_cooldown", "reminder_seconds", "max_reminders"):
        hat_zustand = re.search(rf"useState[^\n]*\b{re.escape(alt)}\b", p) \
            or re.search(rf"set[A-Z]\w*\s*\]\s*=\s*useState[^\n]*{re.escape(alt)}", p)
        wird_gesendet = re.search(rf"^\s*{re.escape(alt)}\s*[,:]", p, re.M)
        check(f"'{alt}' ist nicht mehr einstellbar",
              not hat_zustand and not wird_gesendet,
              "es darf hoechstens als Anzeige vorkommen")

    # Kein Eingabefeld darf an einen der alten Werte gebunden sein.
    check("keine Eingabefelder fuer die festen Werte",
          not re.search(r"<input[^>]*value=\{(greeting|musicUrl|seconds)", p),
          "sie sollen nicht mehr aenderbar sein")

    # Und es darf ueberhaupt keinen Zustand fuer Musik oder Ansage
    # geben. Die Pruefung oben sucht nach dem Namen des alten Feldes;
    # jemand koennte ihn aber anders nennen. Deshalb hier auf die
    # Sache zielen: kein useState, in dem "music" oder "greeting"
    # vorkommt.
    zustaende = re.findall(r"const \[(\w+),\s*set\w+\]\s*=\s*useState", p)
    verboten = [z for z in zustaende
                if re.search(r"music|greeting|ansage|sekund|cooldown|remind",
                             z, re.I)]
    check("kein Zustand fuer Musik, Ansage oder Zeiten",
          not verboten, f"gefunden: {verboten}")

    erlaubt = {"daten", "laedt", "beschaeftigt", "an", "kanal",
               "meldeKanal", "rolle"}
    check("nur die vier Einstellungen haben einen Zustand",
          set(zustaende) <= erlaubt,
          f"unerwartet: {sorted(set(zustaende) - erlaubt)}")

    check("es gibt kein Textfeld fuer die Nachricht",
          "<textarea" not in p,
          "die Meldung ist nicht bearbeitbar")

    check("das Panel nennt die feste Musikdatei",
          "music_file" in p or "warteraum.mp3" in p)

    api_ts = open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read()
    check("die tote Probe-Route ist aus api.ts raus",
          "supportQueueTest" not in api_ts)
    check("Laden und Speichern gibt es noch",
          "supportQueue:" in api_ts and "supportQueueSave:" in api_ts)



def test_ping_kommt_wirklich_an() -> None:
    """Die Meldung darf `content` NICHT neben einer V2-View benutzen.

    ── Der Fehler, den das absichert ───────────────────────────────

    Es kam keine einzige Ping-Nachricht an, und im Log stand nichts.
    Der Grund steckt in discord.py 2.7.1 (discord/http.py,
    handle_message_parameters):

        if view.has_components_v2():
            flags = MessageFlags(components_v2=True)

    `StatusCard` erbt von `LayoutView`, hat also V2-Komponenten.
    Discord verbietet bei gesetztem `components_v2` jedes `content`
    und antwortet mit HTTP 400. Der Fehler wurde abgefangen, und die
    Warnung verschwand am Root-Logger ohne Handler.

    Geprueft wird hier am ECHTEN Payload, den discord.py abschicken
    wuerde -- nicht am Quelltext.
    """
    linie("8  Die Ping-Nachricht kommt wirklich an")

    import discord
    import discord.http as dhttp

    from utils.panels import StatusCard

    karte = StatusCard("Jemand wartet", "<@&123>\n<@1> wartet in <#2>.")
    check("StatusCard ist eine V2-Ansicht", karte.has_components_v2(),
          "sonst greift die ganze Ueberlegung nicht")

    # So sendet der Warteraum jetzt: ohne content.
    params = dhttp.handle_message_parameters(
        view=karte, allowed_mentions=discord.AllowedMentions(roles=True)
    )
    flags = discord.MessageFlags._from_value(params.payload.get("flags", 0))
    check("kein content im Payload",
          "content" not in params.payload or not params.payload["content"],
          "content + components_v2 wird von Discord mit 400 abgelehnt")
    check("die V2-Kennzeichnung ist gesetzt", flags.components_v2)

    import json
    check("die Erwaehnung steckt in den Komponenten",
          "<@&123>" in json.dumps(params.payload.get("components", [])),
          "sonst pingt die Nachricht niemanden")

    # Und der Beweis andersherum: MIT content waere es kaputt.
    kaputt = dhttp.handle_message_parameters(content="<@&123>", view=StatusCard("T", "B"))
    kaputt_flags = discord.MessageFlags._from_value(kaputt.payload.get("flags", 0))
    check("der alte Weg waere nachweislich kaputt",
          bool(kaputt.payload.get("content")) and kaputt_flags.components_v2,
          "wenn das nicht mehr stimmt, hat discord.py sich geaendert")

    # Der Cog darf content nicht mehr benutzen.
    quelle = open(os.path.join(BOT, "cogs", "commands", "supportqueue.py"),
                  encoding="utf-8").read()
    ohne = strip_py(quelle)
    versand = ohne[ohne.find("async def _send_notice"):]
    versand = versand[:versand.find("async def _reminder_loop")]
    check("der Versand benutzt kein content=",
          "content=" not in versand,
          "genau das war der Fehler")
    # Auf die Wirkung zielen, nicht auf das Vorkommen der Woerter:
    # `_send_notice` wirklich aufrufen und nachsehen, was an
    # `target.send` uebergeben wird. Eine Pruefung auf "mention kommt
    # im Quelltext vor" blieb gruen, als die Zeile entfernt wurde --
    # im Mutationstest nachgestellt.
    import asyncio as _asyncio

    gesendet = {}

    class _Ziel:
        async def send(self, **kw):
            gesendet.update(kw)

    class _Rolle:
        mention = "<@&555>"

    class _Guild:
        id = GILDE

        def get_channel(self, cid):
            return _Ziel()

        def get_role(self, rid):
            return _Rolle()

    class _Kanal:
        mention = "<#900001>"

    class _Wer:
        mention = "<@111>"

    from cogs.commands.supportqueue import SupportQueue

    cog_pruef = SupportQueue.__new__(SupportQueue)
    ok = _asyncio.run(cog_pruef._send_notice(
        _Guild(), _Wer(), {"notify_channel_id": 1, "staff_role_id": 555},
        _Kanal(),
    ))

    check("die Meldung geht raus", ok is True)
    check("sie wird OHNE content gesendet",
          "content" not in gesendet or not gesendet.get("content"),
          f"gesendet: {sorted(gesendet)}")

    inhalt = str(gesendet.get("view"))
    import json as _json
    try:
        roh = _json.dumps(gesendet["view"].to_components())
    except Exception:
        roh = inhalt
    check("die Rollen-Erwaehnung steckt wirklich in der Nachricht",
          "<@&555>" in roh,
          "ohne sie pingt die Meldung niemanden")
    check("allowed_mentions erlaubt Rollen",
          getattr(gesendet.get("allowed_mentions"), "roles", False) is True,
          "sonst wird die Erwaehnung nicht zugestellt")


def test_leave_bei_hinkendem_cache() -> None:
    """Der Bot muss gehen, auch wenn der Voice-Cache hinterherhinkt.

    `on_voice_state_update` feuert, BEVOR discord.py
    `guild._voice_states` nachgezogen hat. Die gerade gegangene
    Person steht dort noch -- ohne Gegenmassnahme meldet
    `_humans_present` "es ist noch jemand da" und der Bot bleibt fuer
    immer sitzen. Das war gemeldet als "joint, leavt nicht".
    """
    linie("9  Verlassen trotz hinkendem Voice-Cache")

    import aiosqlite

    from utils import support_queue as store

    ordner = tempfile.mkdtemp(prefix="wrleave-")
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)

    async def lauf():
        db = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(db)
        await store.save(db, GILDE, enabled=True, channel_id=KANAL)
        rec = await store.get(db, GILDE)

        cog = baue_cog()
        cog._connection = db

        g = FakeGuild()
        k = FakeChannel(KANAL, g)
        g._channels[KANAL] = k
        person = FakeMember(111)
        person.guild = g
        g._members[111] = person

        g._voice_states[111] = FakeState(k)
        await cog._on_arrival(g, person, rec)
        await asyncio.sleep(0.35)
        check("der Bot ist drin", GILDE in cog._loops)

        # Das Ereignis feuern, OHNE den Cache zu leeren -- genau so
        # verhaelt sich discord.py.
        class VS:
            def __init__(self, ch):
                self.channel = ch

        await cog.on_voice_state_update(person, VS(k), VS(None))
        await asyncio.sleep(0.3)

        check("der Bot geht trotzdem raus",
              GILDE not in cog._loops,
              "der Cache zeigte die Person noch -- der Bot blieb sitzen")

        # Gegenprobe: sitzt WIRKLICH noch jemand drin, bleibt er.
        cog2 = baue_cog()
        cog2._connection = db
        g2 = FakeGuild()
        k2 = FakeChannel(KANAL, g2)
        g2._channels[KANAL] = k2
        a = FakeMember(111)
        b = FakeMember(222)
        a.guild = b.guild = g2
        g2._members[111] = a
        g2._members[222] = b
        g2._voice_states[111] = FakeState(k2)
        g2._voice_states[222] = FakeState(k2)

        await cog2._on_arrival(g2, a, rec)
        await asyncio.sleep(0.35)
        await cog2.on_voice_state_update(a, VS(k2), VS(None))
        await asyncio.sleep(0.2)

        check("mit einer zweiten Person bleibt er",
              GILDE in cog2._loops,
              "er ging, obwohl noch jemand wartet")

        g2._voice_states.clear()
        await cog2._maybe_stop(g2, KANAL)
        await db.close()

    asyncio.run(lauf())
    os.chdir(START)


def test_musik_laeuft_ganz_durch() -> None:
    """Die Laenge kommt vom Track, nicht aus einer festen Zahl.

    Vorher war sie auf 30 Sekunden festgenagelt und das Stueck wurde
    hart abgeschnitten. Bei der hochgeladenen Datei (85 Sekunden)
    hiess das: nach einem Drittel Abbruch, dann von vorn.
    """
    linie("10  Die Musik laeuft ganz durch")

    from cogs.commands.supportqueue import SupportQueue
    from utils import support_queue as store

    class Track:
        def __init__(self, ms):
            self.length = ms

    check("eine 85-Sekunden-Datei wird nicht gekuerzt",
          SupportQueue._track_seconds(Track(85_300)) == 85,
          str(SupportQueue._track_seconds(Track(85_300))))
    check("eine kurze Datei ebenso",
          SupportQueue._track_seconds(Track(30_000)) == 30)
    check("ein Livestream (Laenge 0) faellt auf die Obergrenze",
          SupportQueue._track_seconds(Track(0)) == store.MAX_TRACK_SECONDS)
    check("eine absurde Laenge ebenfalls",
          SupportQueue._track_seconds(Track(99_999_999)) == store.MAX_TRACK_SECONDS)
    check("eine fehlende Angabe ebenfalls",
          SupportQueue._track_seconds(object()) == store.MAX_TRACK_SECONDS)

    # Die echte Datei muss unter der Obergrenze liegen.
    pfad = os.path.join(DASH, "public", "warteraum.mp3")
    if os.path.isfile(pfad):
        d = open(pfad, "rb").read()
        BITRATE = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
        RATE = [44100, 48000, 32000, 0]
        i = 0
        if d[:3] == b"ID3":
            i = 10 + ((d[6] << 21) | (d[7] << 14) | (d[8] << 7) | d[9])
        rahmen, sr = 0, 44100
        while i < len(d) - 4:
            if d[i] == 0xFF and (d[i + 1] & 0xE0) == 0xE0:
                br = BITRATE[(d[i + 2] >> 4) & 0xF]
                s = RATE[(d[i + 2] >> 2) & 0x3]
                if br and s:
                    sr = s
                    i += int(144000 * br / s) + ((d[i + 2] >> 1) & 1)
                    rahmen += 1
                    continue
            i += 1
        laenge = rahmen * 1152 / sr
        check("die hochgeladene Datei passt unter die Obergrenze",
              laenge <= store.MAX_TRACK_SECONDS,
              f"{laenge:.0f}s gegen {store.MAX_TRACK_SECONDS}s")


def main() -> int:
    try:
        test_beitritt()
        test_callback_loescht_nur_sich_selbst()
        test_einstellungen()
        test_ping()
        test_musik()
        test_nichts_mehr_einstellbar()
        test_dashboard()
        test_ping_kommt_wirklich_an()
        test_leave_bei_hinkendem_cache()
        test_musik_laeuft_ganz_durch()
    finally:
        os.chdir(START)

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
