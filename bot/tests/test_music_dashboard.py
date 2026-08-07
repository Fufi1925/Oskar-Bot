#!/usr/bin/env python3
"""
Der Musik-Reiter: Stammkanal, Dauerbetrieb, Playlists, Live-Ansicht.

Gewuenscht war: ein bestimmter Sprachkanal, in dem der Bot dauerhaft
sitzt und spielt, sobald jemand da ist; darunter Playlists zum Anlegen
und Ansehen (mit Cover); darunter eine Live-Ansicht mit Cover,
aktueller Zeit und Steuerung.

Dabei kam ein echter Fehler heraus, der schon vorher da war
-----------------------------------------------------------
``Music.inactivity_timer`` prueft nach zwei Minuten, ob noch jemand
zuhoert -- und schaut dabei auf ``guild.voice_channels[0]``. Das ist
der **erste Sprachkanal des Servers**, nicht der, in dem der Bot
sitzt. Stand dort zufaellig eine Person, trennte der Bot mitten im
Lied, obwohl nebenan zehn Leute zuhoerten.

Diese Datei prueft beides: den neuen Reiter und den behobenen Fehler.

Run:  python3 tests/test_music_dashboard.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read_dash(*parts) -> str:
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_ts(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def strip_py(src: str) -> str:
    """Kommentare UND Docstrings raus.

    Nur ``#``-Zeilen zu entfernen reicht nicht: der Fix beschreibt im
    Docstring, was frueher falsch war (``guild.voice_channels[0]``).
    Die Suche fand genau diesen Satz und meldete den Fehler als
    weiterhin vorhanden -- diese Falle ist hier schon mehrfach
    zugeschnappt.
    """
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src

    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            doc = body[0]
            for i in range(doc.lineno - 1, min(doc.end_lineno, len(lines))):
                lines[i] = ""
    return "\n".join(lines)


MUSIC_COG = os.path.join(BOT, "cogs", "commands", "music.py")


# ------------------------------------------------------------------ #
# 1. Der Speicher -- wirklich ausfuehren, nicht nur lesen
# ------------------------------------------------------------------ #
async def _with_db(func):
    """Eine echte SQLite-Datei, damit die Abfragen wirklich laufen."""

    import aiosqlite

    from utils import music_store as store

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            return await func(db, store)
    finally:
        os.unlink(path)


def test_the_settings_round_trip():
    print("\nEinstellungen speichern und lesen")

    async def body(db, store):
        # Ohne Zeile: die Voreinstellungen, nicht None.
        fresh = await store.get_settings(db, 111)
        check("frischer Server bekommt Voreinstellungen", fresh == dict(store.DEFAULTS))

        saved = await store.save_settings(
            db, 111, {"channel_id": 555, "stay_forever": True, "volume": 80}
        )
        check("Kanal gespeichert", saved["channel_id"] == 555)
        check("Dauerbetrieb als 1 gespeichert", saved["stay_forever"] == 1)
        check("Lautstaerke gespeichert", saved["volume"] == 80)

        # Nur ein Feld aendern -- der Rest muss stehen bleiben.
        again = await store.save_settings(db, 111, {"volume": 30})
        check("Teil-Aenderung laesst den Kanal stehen", again["channel_id"] == 555)
        check("und den Dauerbetrieb", again["stay_forever"] == 1)
        check("aendert aber die Lautstaerke", again["volume"] == 30)

        # Und wirklich aus der Datenbank gelesen, nicht nur
        # zurueckgegeben.
        reread = await store.get_settings(db, 111)
        check("nach dem Neulesen noch da", reread == again)

    asyncio.run(_with_db(body))


def test_absurd_values_are_clamped():
    """Eine Lautstaerke von 5000 uebersteuert, eine negative ist Unsinn."""
    print("\nUnsinnige Werte werden begrenzt")

    from utils import music_store as store

    check("5000 wird gedeckelt", store.clamp_volume(5000) == store.MAX_VOLUME)
    check("negativ wird angehoben", store.clamp_volume(-10) == store.MIN_VOLUME)
    check("Text wird zur Voreinstellung", store.clamp_volume("laut") == store.DEFAULT_VOLUME)
    check("None ebenso", store.clamp_volume(None) == store.DEFAULT_VOLUME)

    check("1 Sekunde Leerlauf wird angehoben", store.clamp_idle(1) == store.MIN_IDLE_SECONDS)
    check("ein Tag wird gedeckelt", store.clamp_idle(86400) == store.MAX_IDLE_SECONDS)


def test_playlists_belong_to_their_guild():
    """Ein Server darf die Playlist eines anderen nicht sehen.

    Die Nummern sind fortlaufend und damit trivial zu raten. Ohne
    ``guild_id`` im WHERE koennte jeder Server jede fremde Liste lesen
    oder loeschen.
    """
    print("\nPlaylists gehoeren ihrem Server")

    async def body(db, store):
        mine = await store.create_playlist(db, 111, "Meine", [])
        await store.create_playlist(db, 222, "Fremde", [])

        check("eigene Liste ist lesbar",
              (await store.get_playlist(db, 111, mine)) is not None)
        check("fremde Liste ist nicht lesbar",
              (await store.get_playlist(db, 222, mine)) is None)
        check("fremde Liste laesst sich nicht loeschen",
              (await store.delete_playlist(db, 222, mine)) is False)
        check("und existiert danach noch",
              (await store.get_playlist(db, 111, mine)) is not None)

        listed = await store.list_playlists(db, 111)
        check("die Liste zeigt nur eigene", len(listed) == 1, str(len(listed)))

    asyncio.run(_with_db(body))


def test_deleting_the_autostart_playlist_clears_the_setting():
    """Sonst sucht der Bot eine Nummer, die es nicht mehr gibt.

    Er spielte dann stumm nichts, ohne dass irgendwo stuende, warum.
    """
    print("\nGeloeschte Startliste wird ausgetragen")

    async def body(db, store):
        playlist_id = await store.create_playlist(db, 111, "Start", [])
        await store.save_settings(db, 111, {"autostart_playlist": playlist_id})

        before = await store.get_settings(db, 111)
        check("Startliste ist gesetzt", before["autostart_playlist"] == playlist_id)

        await store.delete_playlist(db, 111, playlist_id)

        after = await store.get_settings(db, 111)
        check("nach dem Loeschen ausgetragen", after["autostart_playlist"] is None,
              f"-> {after['autostart_playlist']}")

    asyncio.run(_with_db(body))


def test_a_broken_row_does_not_kill_the_page():
    """Kaputtes JSON in der Spalte gibt eine leere Liste, keinen 500er."""
    print("\nEine kaputte Zeile legt nichts lahm")

    async def body(db, store):
        playlist_id = await store.create_playlist(db, 111, "Kaputt", [])
        await db.execute(
            "UPDATE music_playlists SET tracks = ? WHERE id = ?",
            ("{das ist kein json", playlist_id),
        )
        await db.commit()

        found = await store.get_playlist(db, 111, playlist_id)
        check("die Liste ist noch lesbar", found is not None)
        check("und hat einfach keine Titel", found["tracks"] == [])

    asyncio.run(_with_db(body))


def test_tracks_are_stored_with_their_cover():
    """Das Dashboard soll die Cover zeigen, ohne Lavalink zu fragen.

    Bei jedem Seitenaufbau nachzuschlagen dauert, verbraucht bei den
    oeffentlichen Knoten ein Kontingent und schlaegt fehl, sobald kein
    Knoten laeuft.
    """
    print("\nTitel werden mit Cover gespeichert")

    async def body(db, store):
        tracks = [
            {
                "title": "Ein Lied",
                "author": "Wer",
                "uri": "https://example.invalid/1",
                "artwork": "https://example.invalid/cover.jpg",
                "length": 185000,
            }
        ]
        playlist_id = await store.create_playlist(db, 111, "Mit Cover", tracks)
        found = await store.get_playlist(db, 111, playlist_id)

        check("Titel erhalten", found["tracks"][0]["title"] == "Ein Lied")
        check("Cover erhalten",
              found["tracks"][0]["artwork"] == "https://example.invalid/cover.jpg")
        check("Laenge erhalten", found["tracks"][0]["length"] == 185000)
        check("Gesamtlaenge gerechnet", found["length"] == 185000)

    asyncio.run(_with_db(body))


# ------------------------------------------------------------------ #
# 2. Der behobene Fehler: der Bot fliegt raus, obwohl Leute zuhoeren
# ------------------------------------------------------------------ #
def test_the_idle_check_looks_at_the_right_channel():
    print("\nDie Leerlauf-Pruefung nimmt den richtigen Kanal")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())

    check(
        "nicht mehr voice_channels[0]",
        "voice_channels[0]" not in src,
        "das ist der erste Kanal des Servers, nicht der des Bots",
    )
    check(
        "sondern der Kanal des Spielers",
        'getattr(player, "channel", None)' in src,
    )

    # Die Entscheidung muss ueber `_humans_in` laufen. Ein
    # `len(channel.members) > 1` liesse das Wort anderswo stehen und
    # zaehlte trotzdem Koepfe statt Menschen -- inklusive Bots und
    # ohne ungecachte Mitglieder.
    decides = re.search(r"if self\._humans_in\(channel\)\s*>\s*0:", src)
    check("die Entscheidung nutzt _humans_in", bool(decides),
          "len(channel.members) zaehlt Bots mit und verschluckt ungecachte")
    check(
        "und channel.members wird nicht mehr direkt gezaehlt",
        re.search(r"len\(\s*getattr\(channel, .members.", src) is None
        and "len(player.channel.members)" not in src,
    )


def test_it_counts_humans_from_the_voice_states():
    """``channel.members`` filtert still ueber den Cache.

    Ist ein Mitglied nicht gecacht, fehlt es in der Liste -- der Kanal
    wirkt leerer, als er ist, und der Bot geht mitten im Lied.
    ``guild._voice_states`` ist die Liste, die Discord selbst fuehrt.
    """
    print("\nGezaehlt wird ueber die Voice-States")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())
    check("nutzt guild._voice_states", "_voice_states" in src)

    # Und wirklich ausfuehren, mit einer Attrappe.
    class FakeMember:
        def __init__(self, member_id, bot=False):
            self.id = member_id
            self.bot = bot

    class FakeState:
        def __init__(self, channel):
            self.channel = channel

    class FakeChannel:
        def __init__(self, channel_id, guild):
            self.id = channel_id
            self.guild = guild
            self.members = []

    class FakeGuild:
        def __init__(self):
            self._voice_states = {}
            self._members = {}

        def get_member(self, member_id):
            return self._members.get(member_id)

    from cogs.commands.music import Music

    guild = FakeGuild()
    musik = FakeChannel(200, guild)
    andere = FakeChannel(100, guild)

    # Bot plus drei Menschen im Musikkanal, einer davon ungecacht.
    guild._members[1] = FakeMember(1)
    guild._members[2] = FakeMember(2)
    guild._members[9] = FakeMember(9, bot=True)
    guild._voice_states = {
        1: FakeState(musik),
        2: FakeState(musik),
        3: FakeState(musik),   # nicht im Cache
        9: FakeState(musik),   # der Bot
        4: FakeState(andere),  # anderer Kanal
    }

    count = Music._humans_in(musik)
    check("drei Menschen gezaehlt", count == 3, f"-> {count}")
    check("der Bot zaehlt nicht mit", count != 4)

    # Ein ungecachtes Mitglied darf nicht verschluckt werden.
    guild._voice_states = {7: FakeState(musik)}
    guild._members = {}
    lone = Music._humans_in(musik)
    check("ungecachtes Mitglied zaehlt als Mensch", lone == 1, f"-> {lone}")

    # Leerer Kanal.
    guild._voice_states = {9: FakeState(musik)}
    guild._members = {9: FakeMember(9, bot=True)}
    empty = Music._humans_in(musik)
    check("nur der Bot heisst leer", empty == 0, f"-> {empty}")


def test_the_timers_do_not_stack():
    """Frueher startete jeder Durchlauf einen neuen schlafenden Timer.

    Nach zehn Minuten Leerlauf warteten zehn Timer parallel auf
    denselben Kanal.
    """
    print("\nDie Timer stapeln sich nicht mehr")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())
    check(
        "kein schlafender Timer pro Durchlauf",
        "await asyncio.sleep(self.inactivity_timeout)" not in src,
    )
    check("stattdessen ein Zeitstempel", "_idle_since" in src)


def test_the_stay_forever_switch_is_honoured():
    print("\nDauerbetrieb wird beachtet")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())
    check("die Pruefung liest stay_forever", "stay_forever" in src)

    # Auf die Wirkung pruefen: nach dem Lesen muss ein `return`
    # folgen, sonst geht der Bot trotzdem.
    guard = re.search(
        r'if settings\.get\("stay_forever"\):[^}]*?return', src, re.S
    )
    check("und kehrt dann zurueck", bool(guard),
          "ohne return laeuft die Pruefung weiter und trennt doch")


# ------------------------------------------------------------------ #
# 3. Die Routen
# ------------------------------------------------------------------ #
def test_the_routes_are_registered():
    print("\nDie Routen sind angemeldet")

    from fastapi.testclient import TestClient

    from api.server import create_app

    client = TestClient(create_app())
    answer = client.get("/api/v1/openapi.json")
    check("openapi ist lesbar", answer.status_code == 200)
    if answer.status_code != 200:
        return

    paths = set(answer.json()["paths"])
    for path in (
        "/music/{guild_id}",
        "/music/{guild_id}/live",
        "/music/{guild_id}/playlists",
        "/music/{guild_id}/control",
        "/music/{guild_id}/play",
    ):
        check(f"{path} gibt es", path in paths)


def test_the_proxy_knows_the_scope():
    """Ohne Zweig im Proxy kaeme 404 »Unknown API scope«.

    Genau dieser Fehler ist hier schon zweimal passiert -- bei
    command-stats und beim Support-Warteraum.
    """
    print("\nDer Proxy kennt den Bereich")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    check("es gibt den Zweig", 'scope === "music"' in proxy)

    block = proxy.split('scope === "music"')[1].split("if (scope ===")[0]
    check("Nichtangemeldete kommen nicht durch", "Not signed in" in block)
    check("Schreiben verlangt mehr als Lesen",
          "settings.edit" in block and "guild.view" in block)


def test_the_dashboard_is_wired_up():
    print("\nDas Dashboard ist verdrahtet")

    api_src = strip_ts(read_dash("lib", "api.ts"))
    for name in (
        "music:", "musicLive:", "musicSave:", "musicControl:",
        "musicPlay:", "musicPlaylistCreate:", "musicPlaylistDelete:",
    ):
        check(f"{name} gibt es", name in api_src)

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))
    check("es gibt das Panel", bool(panel))
    check("es gibt die Seite",
          bool(read_dash("app", "dashboard", "guild", "[guildId]", "music", "page.tsx")))

    tabs = strip_ts(read_dash("components", "guild-tabs.tsx"))
    check("der Reiter steht in der Navigation", 'slug: "music"' in tabs)


def test_the_panel_has_all_three_parts():
    """Einstellungen, Playlists, Live -- in dieser Reihenfolge.

    Geprueft wird, dass die Werte auch **benutzt** werden, nicht nur
    dass das Wort irgendwo steht. `src=""` liesse "artwork" im Code
    stehen und zeigte trotzdem kein Cover -- genau so sind beim ersten
    Mutationslauf vier Mutationen entwischt.
    """
    print("\nDas Panel hat alle drei Bereiche")

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))

    check("Stammkanal einstellbar", "channel_id" in panel)
    check("Dauerbetrieb einstellbar", "stay_forever" in panel)
    check("Playlists werden gezeigt", "playlists.map" in panel)

    covers = len(re.findall(r"src=\{entry\.artwork\}", panel))
    check(
        "beide Titel-Cover werden angezeigt",
        covers >= 2,
        f"nur {covers} von 2 -- Playlist und Warteschlange brauchen es",
    )
    check(
        "Live-Cover wird angezeigt",
        re.search(r"src=\{track\.artwork\}", panel) is not None,
    )
    check("Fortschrittsbalken", "percent" in panel)

    for action, label in [
        ("pause", "Pause"),
        ("resume", "Weiter"),
        ("skip", "Ueberspringen"),
        ("stop", "Verlassen"),
        ("volume", "Lautstaerke"),
    ]:
        check(
            f"{label} ruft control(»{action}«)",
            re.search(r'control\(\s*(?:live\.paused \? )?"' + action, panel)
            is not None
            or re.search(r'control\("[^"]*"\s*:\s*"' + action, panel) is not None
            or re.search(r':\s*"' + action + r'"\)', panel) is not None,
        )

    # Auf die KARTEN-Ueberschriften pruefen, nicht auf das erste
    # Vorkommen des Wortes. "Playlists" steht seit der Statusleiste
    # schon ganz oben als Kennzahl -- der alte Vergleich meldete
    # deshalb eine falsche Reihenfolge, obwohl die Karten stimmen.
    order = [
        panel.index('<h3 className="font-bold text-white">Sprachkanal</h3>'),
        panel.index('<h3 className="font-bold text-white">Playlists</h3>'),
        panel.index('<h3 className="font-bold text-white">Läuft gerade</h3>'),
    ]
    check("Reihenfolge der Karten stimmt", order == sorted(order), str(order))


def test_there_is_only_one_volume_slider():
    """Zwei Regler fuer dieselbe Zahl waren verwirrend.

    Oben in den Einstellungen stand einer, unten bei der Wiedergabe
    ein zweiter. Der obere wirkte erst beim naechsten Titel -- man zog
    ihn und nichts passierte.
    """
    print("\nEs gibt nur noch einen Lautstaerkeregler")

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))

    sliders = len(re.findall(r'type="range"', panel))
    check("genau ein Schieberegler", sliders == 1, f"-> {sliders}")

    # Und er steht unten, bei der Wiedergabe -- nicht oben.
    slider_at = panel.index('type="range"')
    check(
        "und zwar im Live-Bereich",
        slider_at > panel.index("Läuft gerade"),
        "der Regler steht noch oben in den Einstellungen",
    )

    # Er muss auch sichtbar sein. `hidden` liesse den Regler im Code
    # stehen und zeigte ihn trotzdem nie.
    #
    # Rueckwaerts vom Regler zum umschliessenden <div> suchen, nicht
    # vorwaerts vom Wort "Lautstärke": dieses steht INNERHALB des
    # Kastens, und ein Fenster ab dort verpasst genau die Klasse, die
    # ihn ausblendet. So ist diese Mutation zweimal entwischt.
    before = panel[:slider_at]
    opener = before.rindex("<div")
    wrapper = panel[opener : slider_at]
    check(
        "und ist nicht ausgeblendet",
        "hidden" not in wrapper,
        f"der Kasten darum: {wrapper[:80]}",
    )

    # Und der ganze Live-Bereich darf nicht ausgeblendet sein.
    live_block = panel[panel.index("Läuft gerade") :]
    check(
        "der Live-Bereich ist sichtbar",
        'className="hidden"' not in live_block,
    )


def test_the_volume_is_remembered():
    """Sonst steht sie nach dem Neustart wieder auf 60.

    Der Regler unten sprach frueher nur den laufenden Spieler an. Da
    er jetzt der einzige ist, muss er den Wert auch speichern.
    """
    print("\nDie Lautstaerke wird gemerkt")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "music.py"), encoding="utf-8").read()
    )
    block = route.split('elif action == "volume":')[1].split("elif action ==")[0]

    check("sie wird am Spieler gesetzt", "set_volume" in block)
    check("und gespeichert", "save_settings" in block,
          "ohne das ist sie nach dem Neustart wieder auf 60")
    check("der Puffer im Cog wird verworfen", "forget_settings" in block)


def test_the_chosen_channel_is_shown():
    """Ein <select> zeigt zu wenig.

    Es nennt den Namen, aber nicht die Kategorie und nicht, ob der Bot
    dort ueberhaupt sprechen darf -- der haeufigste Grund fuer "es
    passiert nichts".
    """
    print("\nDer gewaehlte Kanal wird angezeigt")

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))

    check("der Eintrag wird nachgeschlagen", "const chosen =" in panel)
    check(
        "und wirklich gegen die Einstellung geprueft",
        re.search(r"String\(entry\.id\) === String\(settings\.channel_id", panel)
        is not None,
    )
    check("der Name wird gezeigt", "chosen.name" in panel)
    check("die Kategorie auch", "chosen.category" in panel)
    check("und ein Hinweis, wenn er dort stumm ist", "chosen.can_speak" in panel)
    check(
        "ohne Kanal steht ein Hinweis da",
        "Noch kein Kanal gewählt" in panel,
    )


def test_stopping_is_called_leaving():
    """Die Aktion verlaesst den Kanal -- das muss draufstehen.

    "Stopp" liess erwarten, dass nur die Musik anhaelt. Man drueckte
    es und der Bot war weg. Zum Anhalten gibt es Pause.
    """
    print("\nDer Knopf heisst »Verlassen«")

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))
    check("die Beschriftung stimmt", "Verlassen" in panel)
    check("»Stopp« steht nicht mehr da", "Stopp" not in panel)

    # Und die Aktion dahinter macht wirklich beides.
    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "music.py"), encoding="utf-8").read()
    )
    block = route.split('elif action == "stop":')[1].split("elif action ==")[0]
    check("Warteschlange wird geleert", "queue.clear()" in block)
    check("und der Kanal verlassen", "disconnect()" in block)


def test_no_invisible_tailwind_classes():
    """`h-4.5` gibt es in Tailwind nicht -- die Regel entsteht nie.

    Gemessen, nicht vermutet: im gebauten CSS steht `h-4{` und `h-5{`,
    aber kein `h-4\.5{`. Ein Symbol mit dieser Klasse haette gar keine
    Groesse. Der Fehler stand hier schon in premium-admin.tsx, bevor
    ich ihn dreimal nachgebaut habe.
    """
    print("\nKeine Klassen, die es nicht gibt")

    for name in os.listdir(os.path.join(DASH, "components", "dashboard")):
        if not name.endswith(".tsx"):
            continue
        src = strip_ts(read_dash("components", "dashboard", name))
        # Tailwind kennt nur 0.5, 1.5, 2.5 und 3.5 als Bruchteile.
        bad = re.findall(r"\b[hw]-(?:[4-9]|\d\d+)\.5\b", src)
        check(f"{name} ohne erfundene Groesse", not bad, f"-> {sorted(set(bad))}")


def test_the_clock_keeps_running_between_polls():
    """Sonst springt die Zeit in Fuenf-Sekunden-Stufen.

    Der Bot schickt `measured_at` mit -- ohne diesen Zeitstempel liefe
    der Balken nach einem langsamen Aufruf vor.

    Geprueft wird, dass der gerechnete Wert auch **in die Position
    eingeht**. Eine Variable, die nur berechnet und nie benutzt wird,
    laesst alle Woerter stehen und aendert nichts.
    """
    print("\nDie Zeit laeuft fluessig")

    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))

    check("der Zeitstempel wird gelesen", "live?.measured_at" in panel)

    # Die Variable muss deklariert UND benutzt werden. Nur die
    # Verwendung zu suchen liess eine Mutation durch, die die
    # Deklaration umbenannte -- die Verwendung blieb ja stehen.
    declared = re.search(r"const measuredAgo\s*=", panel)
    check("der Abstand wird berechnet", bool(declared),
          "ohne Deklaration bleibt nur eine Verwendung ins Leere")
    check(
        "und fliesst in die Position ein",
        re.search(r"position\s*=[\s\S]{0,200}?measuredAgo", panel) is not None,
        "eine ungenutzte Variable aendert nichts am Balken",
    )
    check(
        "der Balken nutzt die gerechnete Position",
        re.search(r"percent\s*=[\s\S]{0,120}?position", panel) is not None,
    )

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "music.py"), encoding="utf-8").read()
    )
    check("der Bot schickt ihn mit", '"measured_at"' in route)


def test_a_channel_the_bot_cannot_join_is_refused():
    """Sonst steht er im Dashboard und der Bot erscheint nie.

    Geprueft wird die **Bedingung**, nicht das Wort: `if False:`
    liesse `perms.connect` im Code stehen und pruefte trotzdem nichts.
    So ist diese Mutation beim ersten Lauf entwischt.
    """
    print("\nEin unbetretbarer Kanal wird abgelehnt")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "music.py"), encoding="utf-8").read()
    )
    check("die Rechte werden geprueft", "permissions_for" in route)

    # Die Bedingung muss die Rechte wirklich lesen und danach
    # abweisen.
    joins = re.search(
        r"if not \(perms\.connect and perms\.view_channel\):"
        r"[\s\S]{0,300}?raise HTTPException",
        route,
    )
    check("kein Zutritt -> Fehler", bool(joins),
          "`if False:` laesst die Woerter stehen und prueft nichts")

    speaks = re.search(
        r"if not perms\.speak:[\s\S]{0,300}?raise HTTPException", route
    )
    check("kein Sprechrecht -> Fehler", bool(speaks))
    check("mit einer Meldung im Klartext", "nicht betreten" in route)



def test_discord_ids_travel_as_text():
    """18-stellige IDs ueberleben JavaScripts Zahlen nicht.

    Gemeldet: der Stammkanal liess sich waehlen, in Discord passierte
    es auch -- aber im Dashboard stand weiter "Noch kein Kanal
    gewaehlt".

    Der Grund: JavaScripts Zahlen sind Fliesskomma. Alles oberhalb von
    2^53-1 verliert Stellen::

        echt              1530378233579704370
        nach JSON.parse   1530378233579704300

    Die Kanalliste kam als Text, die Einstellung als Zahl -- der
    Vergleich konnte nie stimmen. Discord selbst liefert IDs aus genau
    diesem Grund als Zeichenkette.
    """
    print("\nDiscord-IDs reisen als Text")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "music.py"), encoding="utf-8").read()
    )

    check("es gibt die Umwandlung", "def _ids_as_text" in route)
    check(
        "sie wird beim Lesen benutzt",
        re.search(r'"settings": _ids_as_text\(settings\)', route) is not None,
    )
    check(
        "und beim Speichern",
        route.count("_ids_as_text(settings)") >= 2,
        f"nur {route.count('_ids_as_text(settings)')}x -- beide Wege brauchen es",
    )

    # Wirklich ausfuehren, nicht nur den Text lesen.
    sys.path.insert(0, BOT)
    from api.routes import music as music_route

    out = music_route._ids_as_text(
        {"channel_id": 1530378233579704370, "autostart_playlist": 7, "volume": 60}
    )
    check("die Kanal-ID ist eine Zeichenkette", isinstance(out["channel_id"], str))
    check(
        "und verliert keine Stelle",
        out["channel_id"] == "1530378233579704370",
        f"-> {out['channel_id']}",
    )
    check("None bleibt None", music_route._ids_as_text({"channel_id": None})["channel_id"] is None)

    # Die Gegenprobe: als Zahl waere sie kaputt.
    as_float = int(float(1530378233579704370))
    check(
        "als Zahl waere sie es nicht",
        as_float != 1530378233579704370,
        "dann waere der ganze Aufwand unnoetig",
    )

    # Und das Dashboard muss beide Seiten als Text vergleichen.
    panel = strip_ts(read_dash("components", "dashboard", "music-panel.tsx"))
    check(
        "das Dashboard vergleicht als Text",
        re.search(
            r"String\(entry\.id\)\s*===\s*String\(settings\.channel_id", panel
        )
        is not None,
    )


def test_the_idle_check_is_precise():
    """Der Takt der Schleife ist die Genauigkeit der Leerlaufzeit.

    Bei 30 Sekunden Takt griff eine eingestellte Minute erst nach 90
    Sekunden -- nachgerechnet: 45s eingestellt bedeutete 60s, 100s
    bedeutete 120s. Das war der gemeldete "geht nicht".
    """
    print("\nDie Leerlaufzeit ist genau")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())

    found = re.search(r"await asyncio\.sleep\((\d+)\)\n\n    @staticmethod", src)
    tick = int(found.group(1)) if found else 999
    check("die Schleife laeuft mindestens alle 5s", tick <= 5, f"-> {tick}s")

    # Nachrechnen, was das bedeutet.
    worst = 0
    for wanted in (30, 45, 60, 75, 90, 100, 150, 200):
        elapsed, since, left = 0, None, None
        while elapsed <= 900:
            if since is None:
                since = elapsed
            elif elapsed - since >= wanted:
                left = elapsed
                break
            elapsed += tick
        worst = max(worst, (left or 0) - wanted)
    check("hoechstens 5s Abweichung", worst <= 5, f"-> {worst}s daneben")


def test_it_pauses_when_the_channel_empties():
    """Sonst spielt die Playlist in einen leeren Kanal weiter.

    Gewuenscht: sobald niemand mehr da ist, sofort anhalten -- und bei
    der Rueckkehr an derselben Stelle weitermachen. Pausieren statt
    stoppen, damit die Stelle erhalten bleibt.
    """
    print("\nLeerer Kanal haelt die Musik an")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())

    # Die Behandler muessen als Ereignis ANGEMELDET sein. Nur den
    # Namen zu suchen reicht nicht: eine umbenannte Funktion enthaelt
    # ihn immer noch als Teilzeichenkette, und discord.py ruft sie
    # trotzdem nie. Genau so sind zwei Mutationen entwischt.
    #
    # Geprueft wird deshalb der Dekorator direkt darueber.
    for handler, what in [
        ("music_pause_on_empty", "Anhalten"),
        ("music_resume_on_join", "Weiterspielen"),
    ]:
        registered = re.search(
            r'@commands\.Cog\.listener\("on_voice_state_update"\)\s*\n'
            r"\s*async def " + handler + r"\(",
            src,
        )
        check(f"{what} ist als Ereignis angemeldet", bool(registered),
              "ohne den Dekorator ruft discord.py die Funktion nie")

    block = src.split("async def music_pause_on_empty")[1].split("async def")[0]
    check("er pausiert wirklich", "player.pause(True)" in block)
    check(
        "und beachtet den Dauerbetrieb",
        'settings.get("stay_forever")' in block,
        "sonst hielte er auch bei 24/7 an",
    )
    check("er zaehlt den Kanal nach", "_humans_in" in block)

    back = src.split("async def music_resume_on_join")[1].split("async def")[0]
    check("das Weiterspielen loest pause(False) aus", "player.pause(False)" in back)
    check("und zaehlt ebenfalls nach", "_humans_in" in back)


def test_a_hand_paused_bot_stays_paused():
    """Wer im Chat `>pause` drueckt, will keine Ueberraschung.

    Ohne Merkliste spielte der Bot beim naechsten Beitritt von selbst
    weiter -- obwohl ihn jemand ausdruecklich angehalten hatte.
    """
    print("\nVon Hand pausiert bleibt pausiert")

    src = strip_py(open(MUSIC_COG, encoding="utf-8").read())

    check("es gibt eine Merkliste", "_paused_empty" in src)

    block = src.split("async def music_pause_on_empty")[1].split("async def")[0]
    check("sie wird beim Anhalten gefuellt", "_paused_empty.add" in block)

    # Die Abfrage muss WIRKEN: `if False: return` liesse das Wort
    # stehen und spielte trotzdem immer weiter. Deshalb auf die
    # Bedingung selbst pruefen.
    back = src.split("async def music_resume_on_join")[1].split("async def")[0]
    guard = re.search(
        r"if guild\.id not in self\._paused_empty:\s*\n\s*return", back
    )
    check(
        "das Weiterspielen bricht ohne Eintrag ab",
        bool(guard),
        "`if False: return` laesst das Wort stehen und spielt doch weiter",
    )

    # Beim Verlassen aufraeumen -- sonst bleibt der Server ewig in der
    # Liste, und nach dem naechsten Beitritt spielt nichts weiter,
    # weil der Eintrag noch da ist.
    # Gezielt die Stelle direkt vor dem Verlassen pruefen.
    #
    # `check_inactivity` raeumt an vier Stellen auf; eine Suche ueber
    # die ganze Funktion bleibt gruen, wenn genau die letzte fehlt --
    # und genau die zaehlt: ohne sie bleibt der Server in der Liste,
    # und nach dem naechsten Beitritt spielt nichts weiter.
    ordered = re.search(
        r"self\._paused_empty\.discard\(guild_id\)\s*\n"
        r"\s*await self\._leave_idle",
        src,
    )
    check(
        "vor dem Verlassen wird aufgeraeumt",
        bool(ordered),
        "ein stehengebliebener Eintrag verhindert das naechste Weiterspielen",
    )


def main() -> int:
    test_the_settings_round_trip()
    test_absurd_values_are_clamped()
    test_playlists_belong_to_their_guild()
    test_deleting_the_autostart_playlist_clears_the_setting()
    test_a_broken_row_does_not_kill_the_page()
    test_tracks_are_stored_with_their_cover()
    test_discord_ids_travel_as_text()
    test_the_idle_check_is_precise()
    test_it_pauses_when_the_channel_empties()
    test_a_hand_paused_bot_stays_paused()
    test_the_idle_check_looks_at_the_right_channel()
    test_it_counts_humans_from_the_voice_states()
    test_the_timers_do_not_stack()
    test_the_stay_forever_switch_is_honoured()
    test_the_routes_are_registered()
    test_the_proxy_knows_the_scope()
    test_the_dashboard_is_wired_up()
    test_the_panel_has_all_three_parts()
    test_there_is_only_one_volume_slider()
    test_the_volume_is_remembered()
    test_the_chosen_channel_is_shown()
    test_stopping_is_called_leaving()
    test_no_invisible_tailwind_classes()
    test_the_clock_keeps_running_between_polls()
    test_a_channel_the_bot_cannot_join_is_refused()

    print()
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    print("Alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
