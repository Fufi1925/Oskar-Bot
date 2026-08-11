#!/usr/bin/env python3
"""
">play": der Bot joint und geht sofort wieder -- aber nur manchmal.

Genau dieses "manchmal" war der Hinweis. Der eigene Verbindungsaufbau
ist frueher fertig als der Voice-State-Frame fuer den Nutzer, der den
Befehl gegeben hat. In dem Fenster meldet ``_humans_in`` null Zuhoerer,
obwohl jemand im Kanal sitzt -- und der Waechter trennt.

``play_source`` hat den Waechter zusaetzlich SOFORT nach dem Verbinden
angeworfen. Damit entschied der Zufall, ob er vor oder nach dem
Gateway-Frame lief.

Run:  python3 tests/test_music_join.py
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []
SRC_PATH = os.path.join(BOT, "cogs/commands/music.py")


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                for i in range(first.lineno - 1, first.end_lineno):
                    lines[i] = ""
    return "\n".join(lines)


ROH = open(SRC_PATH, encoding="utf-8").read()
CODE = strip_py(ROH)
BAUM = ast.parse(ROH)


# ── 1. Kein Sofortaufruf mehr ────────────────────────────────────────

def test_kein_sofortaufruf():
    print("\n1. Der Waechter wird nicht mehr direkt nach dem Beitritt angeworfen")
    check("kein create_task(check_inactivity(...))",
          not re.search(r"create_task\(\s*self\.check_inactivity\(", CODE),
          "-> lief womoeglich vor dem Gateway-Frame")

    # Der regelmaessige Lauf muss es aber weiterhin geben, sonst bleibt
    # der Bot fuer immer in leeren Kanaelen sitzen.
    check("der regelmaessige Waechter laeuft weiter",
          "monitor_inactivity" in CODE and "check_inactivity" in CODE)


# ── 2. Die Schonfrist ────────────────────────────────────────────────

def test_schonfrist():
    print("\n2. Schonfrist nach dem Beitritt")
    check("es gibt eine Schonfrist-Konstante", "JOIN_GRACE_SECONDS" in CODE)

    treffer = re.search(r"JOIN_GRACE_SECONDS\s*=\s*(\d+)", CODE)
    check("sie ist groesser als null",
          bool(treffer) and int(treffer.group(1)) >= 5,
          f"({treffer.group(1) if treffer else 'fehlt'}s)")

    check("der Beitrittszeitpunkt wird gemerkt", "_joined_at" in CODE)

    # Die Schonfrist wird AUSGEFUEHRT, nicht gesucht.
    #
    # Nach den Namen zu suchen genuegt nicht: setzt jemand `joined` fest
    # auf None, stehen beide Namen weiterhin im Rumpf -- einmal in der
    # Zuweisung, einmal im nun toten if. Der Test bliebe gruen, waehrend
    # der Bot wieder sofort rausgeht. Also wird die echte Funktion mit
    # einem frisch betretenen, scheinbar leeren Kanal aufgerufen: sie
    # darf dann nicht trennen.
    import asyncio
    import time as _time

    from cogs.commands import music as music_modul

    class Ch:
        def __init__(self):
            self.id = 100
            self.guild = None

    class Guild:
        def __init__(self):
            self._voice_states = {}   # niemand drin -- wie vor dem Frame
            self.id = 555

        def get_member(self, uid):
            return None

    class Player:
        def __init__(self, guild, channel):
            self.guild = guild
            self.channel = channel
            self.playing = False
            self.paused = False
            self.getrennt = False

        async def disconnect(self, force=False):
            self.getrennt = True

        async def pause(self, value):
            self.paused = value

    class Client:
        def __init__(self, guild, player):
            self._guild = guild
            self.voice_clients = [player]

        def get_guild(self, gid):
            return self._guild

    guild, kanal = Guild(), Ch()
    kanal.guild = guild
    player = Player(guild, kanal)

    cog = music_modul.Music.__new__(music_modul.Music)
    cog.client = Client(guild, player)
    cog.inactivity_timeout = 120
    cog._idle_since = {}
    cog._paused_empty = set()
    cog._started_empty = set()
    cog._joined_at = {guild.id: _time.monotonic()}   # gerade betreten
    cog._settings_cache = {}

    async def keine_einstellungen(gid):
        return {}

    cog._settings_for = keine_einstellungen

    asyncio.run(cog.check_inactivity(guild.id))
    check("frisch betretener Kanal wird nicht getrennt",
          not player.getrennt,
          "-> der Bot ginge sofort wieder raus")
    check("und die Leerlaufuhr laeuft noch nicht",
          guild.id not in cog._idle_since,
          f"({cog._idle_since})")

    # Gegenprobe: liegt der Beitritt lange zurueck, muss der Waechter
    # wieder ganz normal arbeiten.
    cog._joined_at = {guild.id: _time.monotonic() - 3600}
    asyncio.run(cog.check_inactivity(guild.id))
    check("nach der Schonfrist zaehlt der Leerlauf wieder",
          guild.id in cog._idle_since,
          "-> sonst bliebe der Bot fuer immer sitzen")

    # Die Leerlaufuhr darf in der Schonfrist nicht anfangen zu laufen --
    # sonst waere der Bot nur ein paar Sekunden spaeter trotzdem weg.
    #
    # Geprueft wird der Syntaxbaum, nicht ein Textausschnitt: welche
    # Zeilen in den if-Zweig gehoeren, weiss nur der Parser.
    zweig_ok = False
    for knoten in ast.walk(BAUM):
        if not isinstance(knoten, ast.AsyncFunctionDef):
            continue
        if knoten.name != "check_inactivity":
            continue
        for unter in ast.walk(knoten):
            if not isinstance(unter, ast.If):
                continue
            quelltext = ast.unparse(unter)
            if "JOIN_GRACE_SECONDS" not in quelltext:
                continue
            # In genau diesem Zweig muss beides stehen: die Uhr
            # zuruecksetzen UND aussteigen.
            if "_idle_since.pop" in quelltext and "return" in quelltext:
                zweig_ok = True
    check("die Leerlaufuhr wird in der Schonfrist zurueckgesetzt", zweig_ok,
          "-> sonst laeuft sie mit und der Bot geht Sekunden spaeter doch")


# ── 3. Jede Verbindungsstelle meldet sich ────────────────────────────

def test_alle_stellen():
    print("\n3. Jeder Beitritt wird vermerkt")
    check("es gibt einen Helfer dafuer", "def mark_joined" in CODE)

    # Jede Stelle, die connect(cls=wavelink.Player) aufruft, muss
    # mark_joined nach sich ziehen. Eine vergessene Stelle holt den
    # alten Fehler zurueck.
    #
    # Gesucht wird im BEREINIGTEN Quelltext: `music_ready` erklaert den
    # Aufruf in ihrem Docstring, und eine Suche im Rohtext haelt diese
    # Erwaehnung faelschlich fuer eine Verbindungsstelle. Genau darauf
    # ist dieser Test beim ersten Lauf hereingefallen.
    zeilen = CODE.split("\n")
    verbindungen = [
        i for i, z in enumerate(zeilen)
        if "connect(cls=wavelink.Player)" in z and not z.strip().startswith("#")
    ]
    check("es gibt Verbindungsstellen", len(verbindungen) >= 3,
          f"({len(verbindungen)})")

    ohne = []
    for i in verbindungen:
        # In den naechsten fuenf Zeilen muss mark_joined stehen.
        umgebung = "\n".join(zeilen[i:i + 6])
        if "mark_joined" not in umgebung:
            ohne.append(i + 1)
    check("jede Verbindungsstelle meldet den Beitritt", not ohne,
          f"-> Zeilen ohne mark_joined: {ohne}")

    # Und der Aufruf darf nicht in einem toten Zweig haengen.
    #
    # `if False: self.mark_joined(...)` wuerde die Suche oben
    # zufriedenstellen und trotzdem nie ausgefuehrt. Deshalb wird die
    # Bedingung mitgeprueft: sie muss vom Zustand abhaengen, nicht
    # konstant sein.
    tot = []
    for knoten in ast.walk(BAUM):
        if not isinstance(knoten, ast.If):
            continue
        rumpf = ast.unparse(ast.Module(body=knoten.body, type_ignores=[]))
        if "mark_joined" not in rumpf:
            continue
        pruefung = ast.unparse(knoten.test)
        if pruefung in ("False", "True", "0", "1"):
            tot.append(pruefung)
    check("kein mark_joined in einem toten Zweig", not tot, f"({tot})")

    # mark_joined muss den Zeitpunkt wirklich ablegen.
    for knoten in ast.walk(BAUM):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == "mark_joined":
            rumpf = ast.unparse(knoten)
            check("mark_joined schreibt _joined_at",
                  "_joined_at[guild_id]" in rumpf and "monotonic" in rumpf,
                  f"({rumpf[:120]})")


# ── 4. Der Befehl antwortet immer ────────────────────────────────────

def test_antwortet_immer():
    print("\n4. >play antwortet auch, wenn das Verbinden scheitert")
    # play_source aus dem Syntaxbaum holen.
    quelle = None
    for knoten in ast.walk(BAUM):
        if isinstance(knoten, ast.AsyncFunctionDef) and knoten.name == "play_source":
            quelle = ast.get_source_segment(ROH, knoten)
    check("play_source gefunden", quelle is not None)
    if quelle is None:
        return

    # Der connect-Aufruf muss in einem try stehen.
    in_try = False
    for knoten in ast.walk(ast.parse(quelle.lstrip())):
        if not isinstance(knoten, ast.Try):
            continue
        if "connect(cls=wavelink.Player" in ast.unparse(knoten):
            in_try = True
    check("das Verbinden ist abgesichert", in_try,
          "-> sonst endet der Befehl als Traceback ohne Antwort")

    for name in ("TimeoutError", "ClientException", "Forbidden"):
        check(f"{name} wird beantwortet", name in quelle)
    check("und jeder andere Fehler auch",
          re.search(r"except Exception as exc:", quelle) is not None)


# ── 4b. Was vor dem Verbinden passiert ───────────────────────────────

def test_vor_dem_verbinden():
    """
    Drei Faelle, die der Timeout allein nicht abdeckt.

    Ein abgesichertes ``connect()`` faengt den Fehler -- aber es fragt
    nicht, ob die alte Verbindung noch steht, ob der Bot den Kanal
    ueberhaupt betreten darf, und es wartet die volle Vorgabe von
    dreissig Sekunden ab.
    """
    print("\n4b. Tote Verbindung, Rechte und Wartezeit")

    quelle = None
    for knoten in ast.walk(BAUM):
        if isinstance(knoten, ast.AsyncFunctionDef) and knoten.name == "play_source":
            quelle = ast.get_source_segment(ROH, knoten)
    if quelle is None:
        check("play_source gefunden", False)
        return

    # 1. Ein eigener, kuerzerer Timeout.
    check("ein eigener Timeout ist gesetzt",
          bool(re.search(r"connect\([^)]*timeout\s*=", quelle)),
          "-> sonst gelten Discords 30 s, in denen der Chat stumm bleibt")

    import inspect

    import discord
    vorgabe = inspect.signature(discord.VoiceChannel.connect).parameters["timeout"].default
    check("und er ist wirklich kuerzer als die Vorgabe",
          getattr(__import__("cogs.commands.music", fromlist=["Music"]).Music,
                  "CONNECT_TIMEOUT", 999) < vorgabe,
          f"(Vorgabe {vorgabe}s)")

    # 2. Eine tote Verbindung darf nicht weiterbenutzt werden.
    check("eine tote Verbindung wird erkannt", "_player_alive" in quelle,
          "-> der naechste >play spielt sonst ins Leere")
    check("und vorher getrennt", "disconnect(force=True)" in quelle)

    # Die Pruefung selbst muss auch stimmen -- also ausfuehren.
    from cogs.commands.music import Music

    # Zwei getrennte Faelle: einer, bei dem NUR `connected` falsch ist
    # (der Kanal steht noch), und einer ohne Kanal. Mit einer Attrappe,
    # die beides zugleich ist, deckt jede der zwei Pruefungen die andere
    # zu -- und eine davon koennte ersatzlos wegfallen.
    class NurGetrennt:
        connected = False
        channel = object()

    class OhneKanal:
        connected = True
        channel = None

    class Tot:
        connected = False
        channel = None

    class Lebt:
        connected = True
        channel = object()

    check("_player_alive: None ist tot", Music._player_alive(None) is False)
    check("_player_alive: getrennt ist tot", Music._player_alive(Tot()) is False)
    check("_player_alive: nur getrennt reicht schon",
          Music._player_alive(NurGetrennt()) is False,
          "-> die connected-Pruefung ist wirkungslos")
    check("_player_alive: ohne Kanal ist tot",
          Music._player_alive(OhneKanal()) is False)
    check("_player_alive: verbunden lebt", Music._player_alive(Lebt()) is True)

    # 3. Rechte vor dem Verbinden.
    check("die Rechte werden vorab geprueft", "permissions_for" in quelle,
          "-> Discord meldet sie sonst erst nach dem Timeout")

    # Und die beiden Zweige muessen wirklich abbrechen. "if False:"
    # laesst `permissions_for` stehen und pruefte trotzdem nichts mehr,
    # deshalb wird hier der Syntaxbaum befragt.
    baum_ps = ast.parse(quelle.lstrip())
    getestet = set()
    for knoten in ast.walk(baum_ps):
        if not isinstance(knoten, ast.If):
            continue
        bedingung = ast.unparse(knoten.test)
        # Nur Zweige, die auch aussteigen -- ein if ohne return
        # verhindert den Verbindungsversuch nicht.
        steigt_aus = any(isinstance(u, ast.Return) for u in ast.walk(knoten))
        if steigt_aus and "rechte.connect" in bedingung:
            getestet.add("connect")
        if steigt_aus and "rechte.speak" in bedingung:
            getestet.add("speak")
    check("fehlendes Verbinden-Recht bricht ab", "connect" in getestet,
          "-> der Bot laeuft sonst in den vollen Timeout")
    check("fehlendes Sprechen-Recht bricht ab", "speak" in getestet,
          "-> der Bot sitzt sonst stumm im Kanal")
    check("und die fehlende Berechtigung wird benannt",
          "**Verbinden**" in quelle and "**Sprechen**" in quelle,
          "-> sonst sucht der Betreiber an der falschen Stelle")


# ── 5. Die Zaehlung bleibt robust ────────────────────────────────────

def test_zaehlung():
    print("\n5. Zuhoerer werden nicht nur aus dem Cache gezaehlt")
    check("_humans_in nutzt _voice_states", "_voice_states" in CODE,
          "-> channel.members filtert still ueber den Cache")

    # Und die Funktion muss wirklich zaehlen, was sie soll.
    quelle = None
    for knoten in ast.walk(BAUM):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == "_humans_in":
            quelle = ast.get_source_segment(ROH, knoten)
    check("_humans_in gefunden", quelle is not None)
    if quelle is None:
        return

    ns: dict = {}
    exec(quelle.replace("@staticmethod\n", "").lstrip(), ns)
    humans = ns["_humans_in"]

    class State:
        def __init__(self, ch):
            self.channel = ch

    class Ch:
        def __init__(self, cid):
            self.id = cid
            self.guild = None

    class Guild:
        def __init__(self):
            self._voice_states = {}

        def get_member(self, uid):
            return None

    g, ch = Guild(), Ch(100)
    ch.guild = g
    check("leerer Kanal ergibt 0", humans(ch) == 0)

    g._voice_states[7] = State(ch)
    check("eine Person wird gezaehlt", humans(ch) == 1)

    # Unbekannt heisst "nicht im Cache", nicht "Bot" -- lieber bleiben
    # als jemanden mitten im Lied abschneiden.
    anderer = Ch(200)
    anderer.guild = g
    check("ein anderer Kanal zaehlt nicht mit", humans(anderer) == 0)


def main():
    test_kein_sofortaufruf()
    test_schonfrist()
    test_alle_stellen()
    test_antwortet_immer()
    test_vor_dem_verbinden()
    test_zaehlung()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Musik-Beitritt: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
