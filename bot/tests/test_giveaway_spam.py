#!/usr/bin/env python3
"""
Gewinnspiele: der Abschluss laeuft genau einmal.

Der gemeldete Fehler: "sobald eins zu Ende ist, spammt er DMs und
knallt den Chat voll".

Die Ursache war eine Endlosschleife im Abschluss.

  * `GiveawayEnd` laeuft alle fuenf Sekunden und holte jede Zeile mit
    `ends_at <= jetzt`. Nach `ended` wurde **nicht** gefiltert.
  * Der Dashboard-Zweig setzte am Ende zwar `ended = 1`, loeschte die
    Zeile aber nicht -- und stand damit fuenf Sekunden spaeter wieder
    in derselben Auswahl.
  * Ergebnis: auslosen, ankuendigen, DM an jeden Gewinner, DM an den
    Host. Zwoelfmal pro Minute, 720-mal pro Stunde.

Dagegen stehen jetzt drei Riegel, und jeder wird hier einzeln
geprueft:

  1. Die Abfrage filtert nach `ended`.
  2. `mark_ended` meldet, ob *dieser* Aufruf den Abschluss bewirkt hat
     -- ein einzelnes `UPDATE ... WHERE ended = 0`, also atomar.
  3. `giveaway_dms` laesst pro Nutzer und Gewinnspiel genau eine DM zu.
     Die Sperre liegt in der Datenbank, nicht im Ablauf: sie haelt auch
     dann, wenn zwei Wege gleichzeitig ankuendigen.

Dazu die uebrigen Fehler, die beim Nachsehen auffielen -- alle im
Reaktions-Weg, der jetzt ganz weg ist.

Run:  python3 tests/test_giveaway_spam.py
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

os.environ["ALLOW_KEYLESS_API"] = "true"
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


def strip_python(src: str) -> str:
    """Kommentare UND Docstrings raus.

    Sonst treffen die Suchen die eigenen Erklaerungen: in den
    Docstrings steht woertlich, was frueher falsch war
    ("message.reactions[0] ohne Pruefung"). Genau das ist beim Bauen
    dieses Tests passiert -- er meldete Fehler, die es nicht mehr gab.
    """

    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)

    tree = ast.parse(src)
    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
        ):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        first = node.body[0]
        for index in range(first.lineno - 1, first.end_lineno):
            lines[index] = ""
    return "\n".join(lines)


def loop_query() -> str:
    """Die Abfrage der Timer-Schleife, aus dem Cog gelesen."""

    tree = ast.parse(source("cogs", "commands", "giveaway.py"))
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Giveaway"
    )
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SELECT_DUE":
                    return ast.literal_eval(node.value)
    return ""


# --------------------------------------------------------------------- #
# 1. Die Schleife holt ein beendetes Gewinnspiel nicht erneut
# --------------------------------------------------------------------- #


def test_the_timer_skips_finished_giveaways():
    print("\nDie Schleife laesst beendete Gewinnspiele liegen")

    import aiosqlite

    from api import giveaways as store

    query = loop_query()
    check("es gibt eine gemeinsame Abfrage", bool(query))
    if not query:
        return

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)

            import time as clock

            past = clock.time() - 60
            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id)"
                " VALUES (1, 42, ?, ?, 'Nitro', 1, 999, 5)",
                (past - 600, past),
            )
            await store.add_entry(db, 999, 111)
            await store.add_entry(db, 999, 222)
            await db.commit()

            async def due() -> int:
                async with db.execute(query, (clock.time(),)) as cursor:
                    return len(await cursor.fetchall())

            before = await due()
            claimed = await store.mark_ended(db, 999)
            after = [await due() for _ in range(4)]

            await db.close()
            return before, claimed, after
        finally:
            os.unlink(path)

    before, claimed, after = asyncio.run(scenario())

    check("ein faelliges Gewinnspiel wird gefunden", before == 1, str(before))
    check("mark_ended meldet den Abschluss", claimed is True)
    check("danach findet die Schleife nichts mehr",
          after == [0, 0, 0, 0],
          f"weitere Durchlaeufe: {after} — jeder waere eine Runde DMs")


def test_only_one_caller_wins_the_race():
    """Zwei Wege koennen gleichzeitig beenden wollen."""

    print("\nNur ein Aufrufer bekommt den Abschluss")

    import aiosqlite

    from api import giveaways as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)
            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id)"
                " VALUES (1, 42, 0, 0, 'X', 1, 999, 5)"
            )
            await db.commit()

            results = await asyncio.gather(
                *[store.mark_ended(db, 999) for _ in range(10)]
            )
            await db.close()
            return results
        finally:
            os.unlink(path)

    results = asyncio.run(scenario())
    check("von zehn gleichzeitigen Aufrufen gewinnt genau einer",
          sum(results) == 1,
          f"{sum(results)} bekamen den Zuschlag")


# --------------------------------------------------------------------- #
# 2. Eine DM pro Nutzer und Gewinnspiel
# --------------------------------------------------------------------- #


def test_one_dm_per_user_per_giveaway():
    print("\nJeder bekommt hoechstens eine DM")

    import aiosqlite

    from api import giveaways as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)
            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id)"
                " VALUES (1, 42, 0, 0, 'X', 1, 999, 5)"
            )
            await db.commit()

            out = {
                "first": await store.claim_dm(db, 999, 111),
                "second": await store.claim_dm(db, 999, 111),
                "other_user": await store.claim_dm(db, 999, 222),
                # Der Host bekommt eine eigene Nachricht, auch wenn er
                # selbst gewonnen hat.
                "host": await store.claim_host_dm(db, 999, 111),
                "host_again": await store.claim_host_dm(db, 999, 111),
                # Ein anderes Gewinnspiel ist ein neuer Anlass.
                "other_giveaway": await store.claim_dm(db, 1000, 111),
            }

            # Und unter Last.
            racing = await asyncio.gather(
                *[store.claim_dm(db, 1000, 777) for _ in range(20)]
            )
            out["racing"] = sum(racing)

            await db.close()
            return out
        finally:
            os.unlink(path)

    out = asyncio.run(scenario())

    check("die erste DM geht raus", out["first"] is True)
    check("die zweite nicht mehr", out["second"] is False,
          "genau das war der Spam")
    check("ein anderer Gewinner bekommt trotzdem seine",
          out["other_user"] is True)
    check("die Host-Nachricht ist davon getrennt", out["host"] is True,
          "ein Host, der selbst gewinnt, braucht beide")
    check("aber auch sie nur einmal", out["host_again"] is False)
    check("ein anderes Gewinnspiel zaehlt eigenstaendig",
          out["other_giveaway"] is True)
    check("auch 20 gleichzeitige Versuche ergeben eine DM",
          out["racing"] == 1,
          f"{out['racing']} kamen durch")


def test_ending_twice_sends_nothing_twice():
    """Der eigentliche Beweis: end_giveaway wirklich zweimal laufen lassen.

    Die Textpruefungen oben zeigen nur, dass die Riegel im Code
    stehen. Ob sie wirken, sieht man erst, wenn man den Abschluss
    zweimal ausfuehrt und die DMs zaehlt -- so wie es die Schleife
    getan haette.

    Genau hier entwischten beim Mutationstest drei Manipulationen: der
    Riegel liess sich entfernen, ohne dass ein Test ansprang.
    """

    print("\nZweimal beenden schickt nicht zweimal")

    import aiosqlite

    import api.dependencies as dep
    from api import giveaways as store
    from cogs.commands.giveaway import Giveaway

    from test_giveaways import FakeBot  # dieselben Attrappen

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            bot = FakeBot()
            dep.set_bot(bot)
            guild = bot.guilds[0]

            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)

            import time as clock

            channel_id = int(guild.channel.id)
            past = clock.time() - 60
            message = await guild.channel.send(view=object())

            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id, dm_winners, dm_host)"
                " VALUES (?, 99, ?, ?, 'Nitro', 2, ?, ?, 1, 1)",
                (guild.id, past - 600, past, message.id, channel_id),
            )
            # Drei Teilnehmer, zwei Gewinner.
            for uid in (10, 11, 12):
                await store.add_entry(db, message.id, uid)
            await db.commit()

            # Den Cog ohne cog_load aufbauen: der wuerde eine eigene
            # Verbindung zur echten Datei oeffnen.
            cog = Giveaway(bot)
            cog.connection = db
            cog.cursor = await db.cursor()

            row = (past, guild.id, message.id, 99, 2, "Nitro", channel_id)

            # Fuenf Durchlaeufe -- so oft haette die Schleife in
            # fuenfundzwanzig Sekunden zugeschlagen.
            for _ in range(5):
                await cog.end_giveaway(row)

            dms = {uid: len(member.dms) for uid, member in guild.members.items()}
            replies = len(guild.channel.replies)

            await db.close()
            return dms, replies
        finally:
            os.unlink(path)

    dms, replies = asyncio.run(scenario())

    winner_dms = sum(count for uid, count in dms.items() if uid != 99)
    print(f"       DMs je Nutzer: {dms}, Nachrichten im Kanal: {replies}")

    check("kein Gewinner bekommt mehr als eine DM",
          all(count <= 1 for uid, count in dms.items() if uid != 99),
          f"{dms} — genau das war der gemeldete Spam")
    check("zwei Gewinner, also zwei DMs", winner_dms == 2, str(dms))
    check("der Host bekommt genau eine", dms.get(99, 0) == 1, str(dms))
    check("und der Kanal genau eine Nachricht",
          replies == 1,
          f"{replies} Nachrichten — der Chat lief sonst voll")


def test_an_empty_giveaway_announces_exactly_once():
    """Auch ohne Teilnehmer: eine Nachricht, keine, die fehlt."""

    print("\nOhne Teilnehmer genau eine Nachricht")

    import aiosqlite

    import api.dependencies as dep
    from api import giveaways as store
    from cogs.commands.giveaway import Giveaway

    from test_giveaways import FakeBot

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            bot = FakeBot()
            dep.set_bot(bot)
            guild = bot.guilds[0]

            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)

            import time as clock

            channel_id = int(guild.channel.id)
            past = clock.time() - 60
            message = await guild.channel.send(view=object())

            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id, dm_winners, dm_host,"
                " msg_no_entries)"
                " VALUES (?, 99, ?, ?, 'Nitro', 1, ?, ?, 1, 1,"
                " 'Schade, niemand wollte {prize}.')",
                (guild.id, past - 600, past, message.id, channel_id),
            )
            await db.commit()

            cog = Giveaway(bot)
            cog.connection = db
            cog.cursor = await db.cursor()

            row = (past, guild.id, message.id, 99, 1, "Nitro", channel_id)
            for _ in range(3):
                await cog.end_giveaway(row)

            replies = list(guild.channel.replies)
            host_dms = len(guild.members[99].dms)
            still_there = await store.get(db, guild.id, message.id)

            await db.close()
            return replies, host_dms, still_there
        finally:
            os.unlink(path)

    replies, host_dms, still_there = asyncio.run(scenario())

    check("es kommt genau eine Nachricht", len(replies) == 1, str(replies))
    check("und zwar der Text des Hosts",
          bool(replies) and "Schade" in replies[0],
          str(replies))
    check("der Preis wird eingesetzt",
          bool(replies) and "Nitro" in replies[0],
          str(replies))
    check("der Host wird einmal benachrichtigt", host_dms == 1, str(host_dms))
    check("das Gewinnspiel bleibt erhalten",
          still_there is not None,
          "frueher lief der leere Fall in den IndexError, der es loeschte")


def test_deleting_one_message_keeps_the_other():
    """Zwei laufende Gewinnspiele -- nur das geloeschte darf verschwinden."""

    print("\nDas Loeschen trifft nur das eine")

    import aiosqlite

    import api.dependencies as dep
    from api import giveaways as store
    from cogs.commands.giveaway import Giveaway

    from test_giveaways import FakeBot

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            bot = FakeBot()
            dep.set_bot(bot)
            guild = bot.guilds[0]

            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)

            channel_id = int(guild.channel.id)
            first = await guild.channel.send(view=object())
            second = await guild.channel.send(view=object())

            for message in (first, second):
                await db.execute(
                    "INSERT INTO Giveaway (guild_id, host_id, start_time,"
                    " ends_at, prize, winners, message_id, channel_id)"
                    " VALUES (?, 99, 0, 99999999999, 'X', 1, ?, ?)",
                    (guild.id, message.id, channel_id),
                )
            await db.commit()

            cog = Giveaway(bot)
            cog.connection = db
            cog.cursor = await db.cursor()

            # Die ZWEITE Nachricht wird geloescht. Der alte Code las mit
            # fetchone() irgendeine Zeile -- meist die erste -- und
            # verglich sie mit dieser hier: kein Treffer, nichts
            # passierte, und die geloeschte blieb stehen.
            second.author = bot.user
            second.guild = guild
            await cog.GiveawayMessageDelete(second)

            async with db.execute(
                "SELECT message_id FROM Giveaway WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                remaining = {row[0] for row in await cursor.fetchall()}

            await db.close()
            return remaining, first.id, second.id
        finally:
            os.unlink(path)

    remaining, first_id, second_id = asyncio.run(scenario())

    check("das geloeschte Gewinnspiel ist weg",
          second_id not in remaining,
          f"noch da: {remaining}")
    check("das andere steht noch",
          first_id in remaining,
          f"noch da: {remaining} — es haette nicht angefasst werden duerfen")


def test_deleting_an_unrelated_message_changes_nothing():
    """Der Bot schreibt staendig Nachrichten, die keine Gewinnspiele sind.

    Der alte Listener las mit `fetchone()` irgendeine Zeile des Servers
    und verglich sie mit der geloeschten Nachricht. Loeschte jemand
    eine beliebige andere Bot-Nachricht, war der Vergleich zwar
    negativ -- aber die Abfrage selbst war schon falsch: sie stellte
    gar nicht fest, ob DIESE Nachricht ein Gewinnspiel ist.

    Hier wird deshalb geprueft, was passiert, wenn eine fremde
    Bot-Nachricht verschwindet: das Gewinnspiel muss unangetastet
    bleiben, und die Teilnehmer auch.
    """

    print("\nEine fremde Nachricht laesst das Gewinnspiel in Ruhe")

    import aiosqlite

    import api.dependencies as dep
    from api import giveaways as store
    from cogs.commands.giveaway import Giveaway

    from test_giveaways import FakeBot

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            bot = FakeBot()
            dep.set_bot(bot)
            guild = bot.guilds[0]

            db = await aiosqlite.connect(path)
            await store.ensure_schema(db)

            channel_id = int(guild.channel.id)
            giveaway_message = await guild.channel.send(view=object())

            await db.execute(
                "INSERT INTO Giveaway (guild_id, host_id, start_time, ends_at,"
                " prize, winners, message_id, channel_id)"
                " VALUES (?, 99, 0, 99999999999, 'X', 1, ?, ?)",
                (guild.id, giveaway_message.id, channel_id),
            )
            await store.add_entry(db, giveaway_message.id, 10)
            await store.add_entry(db, giveaway_message.id, 11)
            await db.commit()

            cog = Giveaway(bot)
            cog.connection = db
            cog.cursor = await db.cursor()

            # Irgendeine andere Nachricht des Bots -- kein Gewinnspiel.
            other = await guild.channel.send(view=object())
            other.author = bot.user
            other.guild = guild
            await cog.GiveawayMessageDelete(other)

            async with db.execute(
                "SELECT message_id FROM Giveaway WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                remaining = {row[0] for row in await cursor.fetchall()}

            entries = await store.entry_count(db, giveaway_message.id)

            await db.close()
            return remaining, entries, giveaway_message.id
        finally:
            os.unlink(path)

    remaining, entries, giveaway_id = asyncio.run(scenario())

    check("das Gewinnspiel steht noch",
          giveaway_id in remaining,
          f"noch da: {remaining} — eine fremde Nachricht hat es geloescht")
    check("und seine Teilnehmer auch",
          entries == 2,
          f"{entries} statt 2")


def test_the_announcement_uses_the_lock():
    """Die Sperre nuetzt nichts, wenn _announce daran vorbei sendet."""

    print("\nDie Ankuendigung benutzt die Sperre")

    src = strip_python(source("api", "routes", "giveaways.py"))
    tree = ast.parse(src)

    announce = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_announce"
        ),
        None,
    )
    check("es gibt _announce", announce is not None)
    if announce is None:
        return

    body = ast.unparse(announce)

    # Kein direktes member.send mehr -- alles laeuft ueber _send_dm.
    check("kein direktes member.send",
          "member.send(" not in body,
          "eine DM am Anspruch vorbei waere wieder Spam")
    check("kein direktes host.send", "host.send(" not in body)
    check("die Gewinner-DM laeuft ueber _send_dm", "_send_dm(" in body)
    check("die Host-DM auch", "host=True" in body)

    # Und _send_dm muss den Anspruch wirklich einholen.
    sender = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_send_dm"
        ),
        None,
    )
    check("es gibt _send_dm", sender is not None)
    if sender is None:
        return

    sender_body = ast.unparse(sender)
    check("_send_dm fragt vorher nach", "claim(" in sender_body)
    check("und bricht ohne Anspruch ab", "return False" in sender_body)
    check("die Bremse zwischen zwei DMs steht", "DM_DELAY" in body,
          "fuenfzehn DMs am Stueck laufen ins Rate-Limit")


# --------------------------------------------------------------------- #
# 3. Der Reaktions-Weg ist weg -- mit ihm seine Abstuerze
# --------------------------------------------------------------------- #


def test_the_reaction_path_is_gone():
    """Alles laeuft ueber den Knopf, wie besprochen."""

    print("\nAlle Gewinnspiele laufen ueber den Knopf")

    src = strip_python(source("cogs", "commands", "giveaway.py"))

    check("keine Reaktion wird mehr ausgelesen",
          "reactions[0]" not in src,
          "leer, sobald jemand die Reaktion entfernt -> IndexError")
    check("keine Reaktion wird mehr gesetzt",
          "add_reaction" not in src,
          "der Knopf ersetzt sie")
    check("kein ungeschuetztes remove mehr",
          "users.remove(" not in src,
          "ValueError, wenn der Bot nicht in der Liste steht")
    check("gstart legt den Knopf an",
          "build_view(" in src,
          "sonst kann niemand teilnehmen")


def test_a_failure_does_not_delete_the_giveaway():
    """Der alte Faenger loeschte bei IndexError das ganze Gewinnspiel."""

    print("\nEin Fehler kostet nicht das Gewinnspiel")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)

    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "end_giveaway"
        ),
        None,
    )
    check("es gibt end_giveaway", node is not None)
    if node is None:
        return

    # Jeden except-Zweig einzeln ansehen: loescht einer?
    deleting_handlers = []
    for handler in [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)]:
        text = ast.unparse(handler)
        if "DELETE FROM Giveaway" in text or "drop()" in text:
            deleting_handlers.append(ast.unparse(handler.type) if handler.type else "bare")

    check("kein Fehlerzweig loescht das Gewinnspiel",
          not deleting_handlers,
          f"loeschende Zweige: {deleting_handlers}")

    body = ast.unparse(node)
    check("ein Abbruch wird durchgereicht",
          "CancelledError" in body,
          "sonst frisst der Faenger den Abbruch des Bots")


def test_an_empty_giveaway_still_announces():
    """Ohne Teilnehmer fiel es frueher stumm in den Reaktions-Pfad."""

    print("\nAuch ohne Teilnehmer wird angekuendigt")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "end_giveaway"
        ),
        None,
    )
    if node is None:
        check("es gibt end_giveaway", False)
        return

    body = ast.unparse(node)

    check("_announce wird immer gerufen", "_announce(" in body)
    # Und nicht nur hinter "if entries".
    check("nicht nur bei vorhandenen Teilnehmern",
          "if entries:" not in body,
          "der leere Fall lief frueher in den Reaktions-Pfad und dort "
          "in den IndexError, der das Gewinnspiel loeschte")


def test_the_start_waits_for_the_bot():
    """Vor `ready` gibt `get_guild` None -- und der Aufraeumzweig loescht."""

    print("\nDer Nachhol-Durchlauf wartet auf den Bot")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)

    load = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "cog_load"
        ),
        None,
    )
    check("es gibt cog_load", load is not None)
    if load is not None:
        check("cog_load beendet nichts direkt",
              "check_for_ended_giveaways()" not in ast.unparse(load),
              "zu dem Zeitpunkt kennt der Bot seine Server nicht -- "
              "jedes faellige Gewinnspiel waere geloescht worden")

    before = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "before_giveaway_end"
        ),
        None,
    )
    check("die Schleife wartet auf wait_until_ready",
          before is not None and "wait_until_ready" in ast.unparse(before))


# --------------------------------------------------------------------- #
# 4. Die reparierten Befehle
# --------------------------------------------------------------------- #


def test_gend_and_greroll_are_sane():
    print("\ngend und greroll")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)

    gend = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "gend"),
        None,
    )
    check("es gibt gend", gend is not None)
    if gend is not None:
        body = ast.unparse(gend)
        check("gend benutzt denselben Abschluss wie der Timer",
              "self.end_giveaway(" in body,
              "sonst gibt es zwei Wege mit zwei Riegeln")
        check("gend lost nicht mehr selbst aus",
              "random.sample" not in body,
              "das war der ValueError bei mehr Gewinnern als Teilnehmern")
        # ast.unparse normalisiert auf einfache Anfuehrungszeichen --
        # deshalb wird beides akzeptiert, sonst prueft der Test die
        # Schreibweise statt der Wirkung.
        check("gend lehnt ein beendetes Gewinnspiel ab",
              "record.get('ended')" in body or 'record.get("ended")' in body)

    greroll = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "greroll"),
        None,
    )
    check("es gibt greroll", greroll is not None)
    if greroll is not None:
        body = ast.unparse(greroll)
        # Die alte Bedingung war verdreht: gefunden -> Abbruch.
        check("greroll verlangt ein beendetes Gewinnspiel",
              "if not record.get('ended')" in body
              or 'if not record.get("ended")' in body,
              "frueher brach es ab, wenn es das Gewinnspiel FAND")
        check("greroll ueberspringt bisherige Gewinner",
              "exclude_past=True" in body)
        check("greroll zieht so viele wie vorgesehen",
              "record.get('winners')" in body
              or 'record.get("winners")' in body,
              "frueher immer genau einen, egal was eingestellt war")


def test_the_running_count_ignores_finished_ones():
    """Sonst blockieren fuenf beendete Gewinnspiele jedes neue."""

    print("\nBeendete zaehlen nicht gegen das Limit")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)

    gstart = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "gstart"),
        None,
    )
    check("es gibt gstart", gstart is not None)
    if gstart is None:
        return

    body = ast.unparse(gstart)
    check("die Zaehlung filtert nach ended",
          "COALESCE(ended, 0) = 0" in body,
          "die Zeilen bleiben nach dem Ende stehen -- ohne Filter waeren "
          "nach fuenf Gewinnspielen keine neuen mehr moeglich")

    glist = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "glist"),
        None,
    )
    if glist is not None:
        listing = ast.unparse(glist)
        check("glist zeigt nur laufende",
              "COALESCE(ended, 0) = 0" in listing,
              'die Liste heisst "Ongoing"')
        check("und verlinkt den richtigen Kanal",
              "ctx.channel.id" not in listing,
              "der Link nahm den Kanal, in dem der Befehl stand")


def test_the_delete_listener_matches_the_message():
    print("\nDas Loeschen trifft die richtige Zeile")

    src = strip_python(source("cogs", "commands", "giveaway.py"))
    tree = ast.parse(src)

    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef)
         and n.name == "GiveawayMessageDelete"),
        None,
    )
    check("es gibt den Listener", node is not None)
    if node is None:
        return

    body = ast.unparse(node)
    check("gesucht wird nach dieser Nachricht",
          "message_id = ?" in body,
          "frueher las fetchone() irgendeine Zeile des Servers")
    check("Direktnachrichten fallen raus",
          "message.guild is None" in body,
          "eine DM hat keinen Server -- .guild.id waere AttributeError")
    check("die Teilnehmer werden mit aufgeraeumt",
          "giveaway_entries" in body)


def main() -> int:
    test_the_timer_skips_finished_giveaways()
    test_only_one_caller_wins_the_race()
    test_one_dm_per_user_per_giveaway()
    test_ending_twice_sends_nothing_twice()
    test_an_empty_giveaway_announces_exactly_once()
    test_deleting_one_message_keeps_the_other()
    test_deleting_an_unrelated_message_changes_nothing()
    test_the_announcement_uses_the_lock()
    test_the_reaction_path_is_gone()
    test_a_failure_does_not_delete_the_giveaway()
    test_an_empty_giveaway_still_announces()
    test_the_start_waits_for_the_bot()
    test_gend_and_greroll_are_sane()
    test_the_running_count_ignores_finished_ones()
    test_the_delete_listener_matches_the_message()

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
