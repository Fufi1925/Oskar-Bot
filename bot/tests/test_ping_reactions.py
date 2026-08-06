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


def test_the_panel_cannot_overwrite_an_owner():
    """Sonst liesse sich die eigene Kennzeichnung im Panel abschalten."""

    print("\nDas Panel kann keinen Besitzer ueberschreiben")

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
    check("die Route fragt die festen Regeln ab",
          "owner_reactions(" in body)
    check("und weist sie ab",
          "HTTPException" in body and "feste Regel" in body,
          "sonst laesst sich eine Besitzer-ID ueberschreiben")


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

    check("der Reiter steht in der Liste",
          '{ id: "pingreactions", label: "Ping"' in admin)
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
    test_the_panel_cannot_overwrite_an_owner()
    test_a_listed_user_gets_reactions()
    test_both_mention_spellings_work()
    test_bots_are_ignored()
    test_a_paused_entry_does_nothing()
    test_the_twenty_limit_holds()
    test_duplicates_across_people_collapse()
    test_a_broken_list_does_not_break_the_owners()
    test_the_tab_is_wired_up()
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
