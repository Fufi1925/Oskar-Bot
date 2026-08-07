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

    # Das Bild muss seine Quelle wirklich aus dem Titel ziehen -- und
    # zwar an BEIDEN Stellen: in der aufgeklappten Playlist und in der
    # Warteschlange. Nur eine zu pruefen liess eine Mutation durch, die
    # das erste Cover leerte; das zweite hielt den Test gruen.
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

    # Die Knoepfe muessen `control` wirklich rufen -- mit der Aktion.
    for action, label in [
        ("pause", "Pause"),
        ("resume", "Weiter"),
        ("skip", "Ueberspringen"),
        ("stop", "Stopp"),
        ("volume", "Lautstaerke"),
    ]:
        check(
            f"{label} ruft control(»{action}«)",
            re.search(r'control\(\s*(?:live\.paused \? )?"' + action, panel)
            is not None
            or re.search(r'control\("[^"]*"\s*:\s*"' + action, panel) is not None
            or re.search(r':\s*"' + action + r'"\)', panel) is not None,
        )

    order = [
        panel.index("Sprachkanal"),
        panel.index("Playlists"),
        panel.index("Läuft gerade"),
    ]
    check("Reihenfolge stimmt", order == sorted(order), str(order))


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


def main() -> int:
    test_the_settings_round_trip()
    test_absurd_values_are_clamped()
    test_playlists_belong_to_their_guild()
    test_deleting_the_autostart_playlist_clears_the_setting()
    test_a_broken_row_does_not_kill_the_page()
    test_tracks_are_stored_with_their_cover()
    test_the_idle_check_looks_at_the_right_channel()
    test_it_counts_humans_from_the_voice_states()
    test_the_timers_do_not_stack()
    test_the_stay_forever_switch_is_honoured()
    test_the_routes_are_registered()
    test_the_proxy_knows_the_scope()
    test_the_dashboard_is_wired_up()
    test_the_panel_has_all_three_parts()
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
