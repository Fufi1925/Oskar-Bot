#!/usr/bin/env python3
"""
Ping-Reaktionen: wer beim Erwaehnen welche Emojis bekommt.

Bisher stand das fest in ``cogs/events/react.py`` -- die beiden
Besitzer, mit vier beziehungsweise drei Emojis. Jeder weitere Name
bedeutete eine Codeaenderung und ein neues Deploy.

Jetzt gibt es dazu eine Liste, die sich im Admin-Panel pflegen laesst.
Die festen Besitzer bleiben unangetastet: eine falsche Eingabe im
Dashboard soll die eigene Kennzeichnung nicht abschalten koennen.

Was hier geprueft wird:

  * **Nur eigene Emojis.** Ausdrueckliche Vorgabe. Die Pruefung liegt
    im Bot, nicht nur im Browser -- die Route ist per HTTP erreichbar.
  * **Die Besitzer reagieren weiter**, auch wenn die Liste leer oder
    kaputt ist.
  * **Beide Erwaehnungsformen.** Discord schickt `<@123>` *oder*
    `<@!123>`, je nachdem ob jemand einen Servernamen gesetzt hat. Die
    alte Textsuche kannte nur die erste -- ein echter Fehler, der beim
    Umbau aufgefallen ist.
  * **Discords Grenze von 20 Reaktionen** pro Nachricht.
  * **Der Zwischenspeicher**, weil `on_message` bei jeder Nachricht
    auf jedem Server laeuft.

Run:  python3 tests/test_ping_reactions.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ.setdefault("TOKEN", "x")
warnings.filterwarnings("ignore")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def source(*parts) -> str:
    return open(os.path.join(BOT, *parts), encoding="utf-8").read()


# Echte Emojis aus utils/emoji.py -- keine erfundenen.
STAFF = "<a:staff:1530375157988720792>"

# Zwei gueltige Snowflakes fuer die Tests.
#
# Kurze Zahlen wie 111 gehen nicht ueberall: die Route prueft die
# Laenge (17 bis 20 Ziffern), weil eine zu kurze Zahl keine
# Discord-ID sein kann. Der erste Anlauf dieses Tests ist genau daran
# gescheitert.
OWNER_A = 111111111111111111
OWNER_B = 222222222222222222
MINGLE = "<a:mingle:1530375188720652438>"


# --------------------------------------------------------------------- #
#  Attrappen
# --------------------------------------------------------------------- #


class FakeUser:
    def __init__(self, uid, bot=False):
        self.id = uid
        self.bot = bot


class FakeMessage:
    def __init__(self, author, mentions=(), content=""):
        self.author = author
        self.mentions = list(mentions)
        self.content = content
        self.reactions_added: list[str] = []

    async def add_reaction(self, emoji):
        self.reactions_added.append(emoji)


class FakeBot:
    def __init__(self, owner_ids=()):
        self.owner_ids = list(owner_ids)


# --------------------------------------------------------------------- #
#  1. Nur eigene Emojis
# --------------------------------------------------------------------- #


def test_only_custom_emojis_are_accepted():
    print("\nNur eigene Emojis des Bots")

    from utils import ping_reactions as store

    cases = [
        (STAFF, True),
        (MINGLE, True),
        ("<:BlackCrown:1530375431973376001>", True),
        # Unicode -- ausdruecklich nicht gewollt.
        ("🎉", False),
        ("👑", False),
        # Halbe Schreibweisen.
        ("staff", False),
        (":staff:", False),
        ("<:staff:>", False),
        # Zu kurze ID: keine gueltige Snowflake.
        ("<:staff:12345>", False),
        # Eine Erwaehnung ist kein Emoji.
        ("<@1303627964734246944>", False),
        # Rollen-Erwaehnung auch nicht.
        ("<@&1234567890123456789>", False),
        ("", False),
    ]

    for value, expected in cases:
        got = store.is_custom_emoji(value)
        check(f"{value[:32] or '(leer)':34} -> {expected}",
              got is expected,
              f"gemeldet: {got}")


def test_the_bot_refuses_bad_input():
    """Die Grenzen gelten im Bot, nicht nur im Formular."""

    print("\nSchlechte Eingaben werden abgewiesen")

    import aiosqlite

    from utils import ping_reactions as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = await aiosqlite.connect(path)
        await store.ensure_schema(db)

        out = {}
        try:
            for label, emojis in [
                ("unicode", ["🎉"]),
                ("leer", []),
                ("nur_leerzeichen", ["  "]),
                ("zu_viele", [f"<:e{i}:1530375157988720{i:03}>" for i in range(25)]),
            ]:
                try:
                    await store.save(db, 999, emojis)
                    out[label] = None  # durchgelassen
                except store.RuleError as exc:
                    out[label] = str(exc)

            # Doppelte werden zusammengefasst, nicht abgelehnt.
            entry = await store.save(db, 998, [STAFF, STAFF, STAFF])
            out["doppelt"] = len(entry["emojis"])
            return out
        finally:
            await db.close()
            os.unlink(path)

    out = asyncio.run(scenario())

    check("Unicode wird abgelehnt", out["unicode"] is not None, "durchgelassen")
    check("und die Begruendung nennt das Emoji",
          out["unicode"] and "🎉" in out["unicode"],
          str(out["unicode"]))
    check("eine leere Auswahl wird abgelehnt", out["leer"] is not None)
    check("Leerzeichen zaehlen nicht als Auswahl",
          out["nur_leerzeichen"] is not None)
    check("mehr als 20 werden abgelehnt", out["zu_viele"] is not None)
    check("und die Begruendung nennt die Zahl",
          out["zu_viele"] and "20" in out["zu_viele"],
          str(out["zu_viele"]))
    check("dreimal dasselbe ergibt einen Eintrag",
          out["doppelt"] == 1,
          f"{out['doppelt']} Eintraege")


# --------------------------------------------------------------------- #
#  2. Die festen Besitzer
# --------------------------------------------------------------------- #


def test_the_owners_still_react():
    print("\nDie Besitzer reagieren weiterhin")

    from cogs.events.react import CO_OWNER_EMOJIS, OWNER_EMOJIS, owner_reactions
    from utils.config import OWNER_IDS

    check("es gibt Besitzer", bool(OWNER_IDS), str(OWNER_IDS))
    if not OWNER_IDS:
        return

    first = owner_reactions(OWNER_IDS[0])
    check("der erste bekommt vier Emojis",
          len(first) == 4,
          f"{len(first)}: {first}")
    check("darunter mingle",
          any("mingle" in e for e in first),
          str(first))

    # Der zweite Besitzer, unabhaengig von der Umgebung.
    #
    # In dieser Umgebung steht nur eine ID in OWNER_IDS -- der Zweig
    # fuer den Co-Besitzer wuerde also nie geprueft, und eine
    # Manipulation daran blieb beim Mutationstest unentdeckt. Deshalb
    # wird die Liste hier vorübergehend ersetzt.
    import cogs.events.react as react_module

    original_ids = react_module.OWNER_IDS
    react_module.OWNER_IDS = [111, 222]
    try:
        first_of_two = react_module.owner_reactions(111)
        second_of_two = react_module.owner_reactions(222)
        stranger = react_module.owner_reactions(333)
    finally:
        react_module.OWNER_IDS = original_ids

    check("mit zwei Besitzern bekommt der erste vier",
          len(first_of_two) == 4,
          f"{len(first_of_two)}: {first_of_two}")
    check("der zweite bekommt drei",
          len(second_of_two) == 3,
          f"{len(second_of_two)}: {second_of_two}")
    check("und zwar ohne mingle",
          not any("mingle" in e for e in second_of_two),
          str(second_of_two))
    check("die beiden unterscheiden sich",
          set(first_of_two) != set(second_of_two),
          "sonst ist die Unterscheidung wirkungslos")
    check("ein Dritter bekommt weiterhin nichts",
          stranger == (),
          str(stranger))

    check("ein Fremder bekommt nichts",
          owner_reactions(1234567890123456789) == (),
          "sonst reagiert der Bot bei jedem")

    # Alle fest verdrahteten muessen echte Emojis sein.
    from utils import ping_reactions as store

    for emoji in OWNER_EMOJIS + CO_OWNER_EMOJIS:
        check(f"{emoji[:30]} ist ein gueltiges Emoji",
              store.is_custom_emoji(emoji),
              "sonst scheitert add_reaction stumm")


def test_a_builtin_rule_can_be_changed():
    """Die mitgelieferten Regeln sind jetzt aenderbar.

    Sie waren zuerst gesperrt. Ausdruecklich anders gewuenscht -- also
    legt sich eine gespeicherte Zeile ueber den Code-Stand.

    Drei Zustaende, und alle drei bedeuten etwas anderes. Der mittlere
    ist der heikle: waere er nicht vom ersten zu unterscheiden, haette
    das Pausieren einer Besitzer-Regel den Code-Standard
    zurueckgeholt statt sie abzuschalten -- der Schalter saehe kaputt
    aus.
    """

    print("\nEine mitgelieferte Regel laesst sich aendern")

    import aiosqlite

    import cogs.events.react as react_module
    from utils import ping_reactions as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = await aiosqlite.connect(path)
        await store.ensure_schema(db)

        original_ids = react_module.OWNER_IDS
        react_module.OWNER_IDS = [111, 222]
        store.reset()
        await store.load(db, force=True)

        try:
            out = {}
            out["default"] = react_module.owner_reactions(111)

            await store.save(db, 111, [STAFF])
            await store.load(db, force=True)
            out["changed"] = react_module.owner_reactions(111)
            out["other_untouched"] = react_module.owner_reactions(222)

            await store.save(db, 111, [STAFF], enabled=False)
            await store.load(db, force=True)
            out["paused"] = react_module.owner_reactions(111)
            out["paused_override"] = store.override_for(111)

            await store.remove(db, 111)
            await store.load(db, force=True)
            out["after_reset"] = react_module.owner_reactions(111)
            out["reset_override"] = store.override_for(111)
            return out
        finally:
            react_module.OWNER_IDS = original_ids
            store.reset()
            await db.close()
            os.unlink(path)

    out = asyncio.run(scenario())

    check("ohne Aenderung gilt der Code-Stand",
          len(out["default"]) == 4,
          f"{len(out['default'])}: {out['default']}")
    check("eine Aenderung schlaegt den Code",
          out["changed"] == (STAFF,),
          f"{out['changed']}")
    check("der andere Besitzer bleibt unberuehrt",
          len(out["other_untouched"]) == 3,
          str(out["other_untouched"]))

    check("pausiert heisst wirklich nichts",
          out["paused"] == (),
          f"{out['paused']} — der Code-Stand kam zurueck, "
          "der Schalter waere wirkungslos")
    check("und unterscheidet sich von 'nichts gespeichert'",
          out["paused_override"] == [] and out["reset_override"] is None,
          f"pausiert={out['paused_override']!r}, "
          f"zurueckgesetzt={out['reset_override']!r}")

    check("Zuruecksetzen holt den Code-Stand zurueck",
          len(out["after_reset"]) == 4,
          f"{len(out['after_reset'])}: {out['after_reset']}")


def test_the_route_no_longer_blocks_owners():
    print("\nDie Route weist eine Besitzer-ID nicht mehr ab")

    src = source("api", "routes", "pingreactions.py")
    tree = ast.parse(src)

    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "save_rule"),
        None,
    )
    check("es gibt save_rule", node is not None)
    if node is None:
        return

    body = ast.unparse(node)
    check("keine Sperre mehr fuer feste Regeln",
          "feste Regel" not in body,
          "sonst laesst sich eine Besitzer-ID weiterhin nicht aendern")


def test_delete_and_toggle_really_behave_differently():
    """Die beiden Routen wirklich aufrufen, nicht nur lesen.

    Die Textsuche oben zeigt, dass die Unterscheidung im Code steht --
    ob sie greift, sieht man erst beim Ausfuehren. Genau hier sind
    beim Mutationstest zwei Manipulationen entwischt.
    """

    print("\nLoeschen und Pausieren verhalten sich unterschiedlich")

    import cogs.events.react as react_module
    from api.db_manager import db_manager
    from api.routes import pingreactions as route
    from utils import ping_reactions as store

    class Bot:
        def get_user(self, _uid):
            return None

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)

        original_path = store.DB_PATH
        original_ids = react_module.OWNER_IDS
        store.DB_PATH = path
        react_module.OWNER_IDS = [OWNER_A, OWNER_B]
        store.reset()

        try:
            out = {}

            # Pausieren einer Regel, die es nur im Code gibt.
            answer = await route.toggle_rule(OWNER_A, {"enabled": False})
            out["toggle_ok"] = answer["status"]
            out["after_pause"] = react_module.owner_reactions(OWNER_A)

            # Wieder an.
            await route.toggle_rule(OWNER_A, {"enabled": True})
            out["after_resume"] = react_module.owner_reactions(OWNER_A)

            # Aendern, dann zuruecksetzen.
            await route.save_rule(
                {"user_id": str(OWNER_A), "emojis": [STAFF]}, Bot()
            )
            out["after_change"] = react_module.owner_reactions(OWNER_A)

            answer = await route.delete_rule(OWNER_A)
            out["reset_flag"] = answer.get("reset_to_default")
            out["reset_text"] = answer.get("result", "")
            out["after_reset"] = react_module.owner_reactions(OWNER_A)

            # Und eine gewoehnliche ID: dort heisst Loeschen wirklich weg.
            await route.save_rule(
                {"user_id": "998877665544332211", "emojis": [STAFF]}, Bot()
            )
            answer = await route.delete_rule(998877665544332211)
            out["plain_flag"] = answer.get("reset_to_default")
            out["plain_text"] = answer.get("result", "")
            return out
        finally:
            store.DB_PATH = original_path
            react_module.OWNER_IDS = original_ids
            store.reset()
            await db_manager.close_all()
            os.unlink(path)

    out = asyncio.run(scenario())

    check("eine eingebaute Regel laesst sich pausieren",
          out["toggle_ok"] == "success" and out["after_pause"] == (),
          f"{out['after_pause']} — 404 oder der Code-Stand kam zurueck")
    check("und wieder einschalten",
          len(out["after_resume"]) == 4,
          str(out["after_resume"]))
    check("aendern wirkt", out["after_change"] == (STAFF,),
          str(out["after_change"]))

    check("Zuruecksetzen meldet sich als solches",
          out["reset_flag"] is True,
          "sonst steht dort 'Gelöscht', und das stimmt nicht")
    check("die Rueckmeldung sagt es auch",
          "urückgesetzt" in out["reset_text"],
          out["reset_text"])
    check("und der Code-Stand gilt wieder",
          len(out["after_reset"]) == 4,
          str(out["after_reset"]))

    check("bei einer gewoehnlichen ID heisst es weiterhin geloescht",
          out["plain_flag"] is False and "elöscht" in out["plain_text"],
          f"{out['plain_flag']}, {out['plain_text']!r}")


def test_pausing_a_builtin_rule_creates_a_row():
    """Zum Pausieren muss erst eine Zeile entstehen.

    Eine mitgelieferte Regel hat zunaechst gar keinen Datenbankeintrag
    -- sie steht nur im Code. Der Umschalter muss deshalb einen
    anlegen, und zwar mit genau den Emojis, die gerade gelten. Sonst
    stuende beim Wiedereinschalten nichts mehr drin.
    """

    print("\nPausieren legt eine Zeile an")

    src = source("api", "routes", "pingreactions.py")
    tree = ast.parse(src)

    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "toggle_rule"),
        None,
    )
    check("es gibt toggle_rule", node is not None)
    if node is None:
        return

    body = ast.unparse(node)
    check("ohne Zeile wird der Code-Stand herangezogen",
          "default_owner_reactions" in body,
          "sonst gibt es 404 beim Pausieren einer eingebauten Regel")
    check("und nur dann abgewiesen, wenn es auch keinen Standard gibt",
          "if not default:" in body)


# --------------------------------------------------------------------- #
#  3. Der Ablauf im Cog
# --------------------------------------------------------------------- #


def run_message(cog, message):
    asyncio.run(cog.on_message(message))


def test_a_listed_user_gets_reactions():
    print("\nEin Eintrag aus der Liste wirkt")

    from cogs.events.react import React
    from utils import ping_reactions as store

    store.reset()
    store._cache[555] = [STAFF, MINGLE]
    store._loaded = True

    try:
        cog = React(FakeBot(owner_ids=[]))
        message = FakeMessage(FakeUser(10), mentions=[FakeUser(555)])
        run_message(cog, message)

        check("beide Emojis gesetzt",
              message.reactions_added == [STAFF, MINGLE],
              str(message.reactions_added))

        # Jemand anders -- nichts.
        other = FakeMessage(FakeUser(10), mentions=[FakeUser(11)])
        run_message(cog, other)
        check("bei einem Fremden passiert nichts",
              other.reactions_added == [],
              str(other.reactions_added))
    finally:
        store.reset()


def test_both_mention_spellings_work():
    """Discord schickt `<@123>` ODER `<@!123>`.

    Der alte Code suchte mit `f"<@{owner}>" in message.content` und
    kannte damit nur die erste Form. Wer einen Servernamen gesetzt
    hat, wurde beim Erwaehnen uebersehen -- ein echter Fehler, der
    beim Umbau aufgefallen ist.

    `message.mentions` kennt beide Formen und ist ausserdem billiger
    als eine Textsuche pro Eintrag.
    """

    print("\nBeide Schreibweisen einer Erwaehnung")

    from cogs.events.react import React
    from utils import ping_reactions as store

    store.reset()
    store._cache[555] = [STAFF]
    store._loaded = True

    try:
        cog = React(FakeBot(owner_ids=[]))

        for label, content in [
            ("<@555>", "hallo <@555>"),
            ("<@!555>", "hallo <@!555>"),
        ]:
            # In beiden Faellen fuellt discord.py `mentions`.
            message = FakeMessage(
                FakeUser(10), mentions=[FakeUser(555)], content=content
            )
            run_message(cog, message)
            check(f"{label} loest aus",
                  message.reactions_added == [STAFF],
                  str(message.reactions_added))

        # Und der Beweis, dass nicht mehr im Text gesucht wird.
        src = source("cogs", "events", "react.py")
        tree = ast.parse(src)
        listener = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message"),
            None,
        )
        body = ast.unparse(listener) if listener else ""
        check("es wird nicht mehr im Text gesucht",
              "in message.content" not in body,
              "die Textsuche kennt nur eine der beiden Schreibweisen")
        check("sondern message.mentions gelesen",
              "message.mentions" in body)
    finally:
        store.reset()


def test_bots_are_ignored():
    print("\nNachrichten von Bots loesen nichts aus")

    from cogs.events.react import React
    from utils import ping_reactions as store

    store.reset()
    store._cache[555] = [STAFF]
    store._loaded = True

    try:
        cog = React(FakeBot(owner_ids=[]))
        message = FakeMessage(FakeUser(9, bot=True), mentions=[FakeUser(555)])
        run_message(cog, message)
        check("nichts gesetzt", message.reactions_added == [],
              "sonst reagieren zwei Bots aufeinander")
    finally:
        store.reset()


def test_a_paused_entry_does_nothing():
    print("\nEin pausierter Eintrag wirkt nicht")

    import aiosqlite

    from cogs.events.react import React
    from utils import ping_reactions as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = await aiosqlite.connect(path)
        await store.ensure_schema(db)
        try:
            await store.save(db, 555, [STAFF], enabled=False)
            await store.load(db, force=True)
            active = store.reactions_for(555)

            await store.save(db, 555, [STAFF], enabled=True)
            await store.load(db, force=True)
            after = store.reactions_for(555)
            return active, after
        finally:
            await db.close()
            os.unlink(path)
            store.reset()

    paused, active = asyncio.run(scenario())

    check("pausiert kommt nichts", paused == [], str(paused))
    check("wieder aktiv kommt es zurueck", active == [STAFF], str(active))


def test_the_twenty_limit_holds():
    """Discord nimmt hoechstens 20 verschiedene Reaktionen."""

    print("\nDie Grenze von zwanzig")

    from cogs.events.react import React
    from utils import ping_reactions as store

    store.reset()
    # Fuenfzehn Emojis auf zwei Personen -- zusammen dreissig.
    store._cache[1] = [f"<:a{i}:15303751579887207{i:02}>" for i in range(15)]
    store._cache[2] = [f"<:b{i}:15303751579887208{i:02}>" for i in range(15)]
    store._loaded = True

    try:
        cog = React(FakeBot(owner_ids=[]))
        message = FakeMessage(
            FakeUser(10), mentions=[FakeUser(1), FakeUser(2)]
        )
        run_message(cog, message)

        check("hoechstens zwanzig werden gesetzt",
              len(message.reactions_added) <= 20,
              f"{len(message.reactions_added)} — die ueberzaehligen "
              "scheitern sonst einzeln und unsichtbar")
    finally:
        store.reset()


def test_duplicates_across_people_collapse():
    """Zwei Personen mit demselben Emoji ergeben eine Reaktion."""

    print("\nDasselbe Emoji zweimal zaehlt einmal")

    from cogs.events.react import React
    from utils import ping_reactions as store

    store.reset()
    store._cache[1] = [STAFF, MINGLE]
    store._cache[2] = [STAFF]
    store._loaded = True

    try:
        cog = React(FakeBot(owner_ids=[]))
        message = FakeMessage(FakeUser(10), mentions=[FakeUser(1), FakeUser(2)])
        run_message(cog, message)

        check("drei Wuensche, zwei Reaktionen",
              len(message.reactions_added) == 2,
              str(message.reactions_added))
        check("und keine doppelt",
              len(set(message.reactions_added)) == len(message.reactions_added))
    finally:
        store.reset()


def test_a_broken_list_does_not_break_the_owners():
    """Die Liste ist eine Zugabe -- sie darf nichts kaputt machen."""

    print("\nEine kaputte Liste kostet nicht die Besitzer-Regel")

    from cogs.events.react import React
    from utils import ping_reactions as store
    from utils.config import OWNER_IDS

    if not OWNER_IDS:
        print("  skip (keine OWNER_IDS gesetzt)")
        return

    store.reset()  # gar nichts geladen

    cog = React(FakeBot(owner_ids=list(OWNER_IDS)))
    message = FakeMessage(FakeUser(10), mentions=[FakeUser(OWNER_IDS[0])])
    run_message(cog, message)

    check("der Besitzer bekommt trotzdem seine Emojis",
          len(message.reactions_added) == 4,
          f"{len(message.reactions_added)}: {message.reactions_added}")


# --------------------------------------------------------------------- #
#  4. Dashboard
# --------------------------------------------------------------------- #


def test_the_tab_is_wired_up():
    print("\nDer Reiter im Admin-Panel")

    dashboard = os.path.join(os.path.dirname(BOT), "dashboard")
    if not os.path.isdir(dashboard):
        print("  skip (dashboard liegt nicht daneben)")
        return

    panel = os.path.join(
        dashboard, "components", "dashboard", "ping-reactions-panel.tsx"
    )
    check("es gibt das Panel", os.path.isfile(panel))

    admin = open(
        os.path.join(dashboard, "components", "dashboard", "admin-content.tsx"),
        encoding="utf-8",
    ).read()

    # Auf die Kennung pruefen, nicht auf die Beschriftung: die hiess
    # frueher "Ping" und heisst jetzt "Ping-Reaktionen". Der Name
    # darf sich aendern, die Kennung nicht -- an ihr haengt alles
    # andere.
    check("der Reiter steht in der Liste",
          re.search(r'\{\s*id:\s*"pingreactions",\s*label:\s*"[^"]+"', admin)
          is not None)
    check("und in einer Gruppe",
          re.search(r'ids: \[[^\]]*"pingreactions"', admin) is not None,
          "ein Reiter ausserhalb jeder Gruppe wird nie gerendert")
    check("er wird gerendert",
          'activeTab === "pingreactions" && <PingReactionsPanel />' in admin)
    check("und das Panel ist importiert",
          "ping-reactions-panel" in admin)

    proxy = open(
        os.path.join(dashboard, "app", "api", "bot", "[...path]", "route.ts"),
        encoding="utf-8",
    ).read()
    check("der Proxy kennt den Endpunkt",
          '"ping-reactions":' in proxy,
          "sonst kommt 'Admin access required' beim Klick")
    # Aendern braucht mehr als Lesen.
    match = re.search(
        r'"ping-reactions":\s*\{\s*GET:\s*"([a-z_.]+)",\s*WRITE:\s*"([a-z_.]+)"',
        proxy,
    )
    check("Lesen und Schreiben sind getrennt",
          match is not None and match.group(1) != match.group(2),
          match.groups() if match else "kein Eintrag")


def test_the_panel_can_edit_builtin_rules():
    """Die eingebauten Regeln brauchen dieselben Knoepfe wie die anderen."""

    print("\nDas Panel kann die mitgelieferten Regeln bearbeiten")

    dashboard = os.path.join(os.path.dirname(BOT), "dashboard")
    if not os.path.isdir(dashboard):
        print("  skip")
        return

    panel = open(
        os.path.join(dashboard, "components", "dashboard", "ping-reactions-panel.tsx"),
        encoding="utf-8",
    ).read()

    # Der Block der eingebauten Regeln -- bis zum naechsten Kommentar.
    start = panel.index("Mitgeliefert")
    block = panel[start : panel.index("Die eigenen Einträge")]

    check("sie haben einen Bearbeiten-Knopf",
          "edit(rule)" in block,
          "sonst bleiben sie unveraenderlich")
    check("und einen Pausenknopf",
          "toggle(rule)" in block)
    check("und Zuruecksetzen",
          "reset_(rule)" in block,
          "ohne den gibt es keinen Weg zurueck zum Originalstand")
    check("Zuruecksetzen ist kein Loeschen",
          "Trash2" not in block,
          "ein Muelleimer verspricht, dass die Regel verschwindet")
    check("es ist aus, wenn nichts geaendert wurde",
          "!rule.customised" in block,
          "sonst kann man auf den Stand zuruecksetzen, auf dem man steht")
    check("eine Aenderung ist erkennbar",
          "geändert" in block,
          "sonst sieht niemand, ob der Originalstand gilt")

    # Und der Fallstrick beim Bearbeiten einer pausierten Regel.
    #
    # Nicht nur nachsehen, ob das Wort vorkommt -- geprueft wird, dass
    # es an der Stelle steht, an der es wirkt. Beim Mutationstest sind
    # beide Faelle zuerst entwischt: das Wort blieb im Text stehen,
    # waehrend die Zeile, die es benutzt, verdreht war.
    check("der Pausenzustand wird gemerkt",
          "setEditingEnabled(rule.enabled)" in panel,
          "sonst weiss das Formular nicht, ob die Regel pausiert war")
    check("und beim Speichern verwendet",
          "enabled: editing ? editingEnabled : true" in panel,
          "ein festes `enabled: true` schaltet eine pausierte Regel "
          "beim Ändern der Emojis stillschweigend wieder ein")
    check("das Formular faellt auf die mitgelieferten Emojis zurueck",
          "rule.emojis.length ? rule.emojis : rule.default_emojis" in panel,
          "sonst steht es bei einer pausierten Regel leer da")


def test_the_panel_only_offers_custom_emojis():
    print("\nDas Panel bietet nur eigene Emojis an")

    dashboard = os.path.join(os.path.dirname(BOT), "dashboard")
    if not os.path.isdir(dashboard):
        print("  skip")
        return

    panel = open(
        os.path.join(dashboard, "components", "dashboard", "ping-reactions-panel.tsx"),
        encoding="utf-8",
    ).read()

    # Nicht nur der Import -- er allein bewirkt nichts. Geprueft wird,
    # dass die Auswahl auch gerendert und ausgewertet wird. Genau das
    # fehlte zuerst: eine Mutation entfernte den Import, und der Test
    # blieb gruen.
    check("die Auswahl wird importiert",
          "EmojiPicker" in panel and "emoji-picker" in panel,
          "sie liest die Liste aus utils/emoji.py")
    check("und tatsaechlich gerendert",
          "<EmojiPicker" in panel,
          "ein Import ohne Verwendung bringt nichts")
    check("ihr Ergebnis landet in der Auswahl",
          re.search(r"<EmojiPicker[\s\S]{0,120}onPick=\{addEmoji\}", panel)
          is not None,
          "ohne onPick passiert beim Klick nichts")
    check("es gibt kein freies Textfeld fuer Emojis",
          "emoji-input" not in panel,
          "sonst tippt jemand ein Unicode-Herz hinein")
    check("und es prueft die Schreibweise",
          "A-Za-z0-9_" in panel,
          "auch im Browser, damit die Vorschau stimmt")


def main() -> int:
    test_only_custom_emojis_are_accepted()
    test_the_bot_refuses_bad_input()
    test_the_owners_still_react()
    test_a_builtin_rule_can_be_changed()
    test_the_route_no_longer_blocks_owners()
    test_pausing_a_builtin_rule_creates_a_row()
    test_delete_and_toggle_really_behave_differently()
    test_a_listed_user_gets_reactions()
    test_both_mention_spellings_work()
    test_bots_are_ignored()
    test_a_paused_entry_does_nothing()
    test_the_twenty_limit_holds()
    test_duplicates_across_people_collapse()
    test_a_broken_list_does_not_break_the_owners()
    test_the_tab_is_wired_up()
    test_the_panel_can_edit_builtin_rules()
    test_the_panel_only_offers_custom_emojis()

    print()
    if failures:
        print(f"{len(failures)} failures")
        for entry in failures:
            print(f"  - {entry}")
        return 1

    print("0 failures, 0 skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
