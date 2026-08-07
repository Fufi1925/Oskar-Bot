#!/usr/bin/env python3
"""
Der Phantom-Ticketbot: startet er, und redet er mit dem Dashboard?

Gemeldet war "in Discord geht nichts". Vier Ursachen kamen heraus:

  1. Der Bot-Token stand fest im Quelltext. `start.sh` startet den Bot
     nur, wenn PHANTOM_BOT_TOKEN gesetzt ist -- der Bot las die
     Variable aber nie und brach mit "Bitte TOKEN eintragen" ab.
  2. Ein verstecktes Tor: alle 45 Sekunden wurde eine Textdatei aus
     einem fremden GitHub-Repo geladen. Stand dort "false", antwortete
     jeder Befehl nur noch mit einer Sperrmeldung. Die Adresse war
     base64-verschleiert, obwohl die README "Kein Remote-Control /
     Killswitch" verspricht.
  3. Die Ticketdaten lagen neben dem Quelltext statt im Volume -- nach
     jedem Deploy weg.
  4. Der Bot schrieb nie ins Dashboard. Die Anbindung existierte in
     Commit ff10684, wurde aber vom spaeteren 5653-Zeilen-Commit
     ueberschrieben. Das Dashboard blieb deshalb leer, obwohl die Doku
     genau beschreibt, wie es funktionieren soll.

Run:  python3 tests/test_phantom.py
"""

import ast
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
PH = os.path.join(ROOT, "phantom")
TICKET_BOT = os.path.join(PH, "bot", "ticket_bot.py")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def strip_py(src: str) -> str:
    """Kommentare und Docstrings raus.

    Ohne das treffen die Suchen die eigenen Erklaerungen: in
    `ticket_bot.py` steht jetzt woertlich beschrieben, was frueher
    falsch war -- inklusive der alten URL und der Variablennamen. Eine
    Suche nach `_Z0` faende den Kommentar und meldete den Kill-Switch
    als weiterhin vorhanden.
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


def source() -> str:
    return strip_py(open(TICKET_BOT, encoding="utf-8").read())


def run_probe(script: str, extra_env: dict, timeout: int = 90):
    """Ein Stueck Code in einem EIGENEN Prozess laufen lassen.

    Im selben Prozess muessten `app.db` und `bot.ticket_bot` fuer jede
    Variante neu geladen werden. Dabei bleiben halb geladene Module
    und offene aiosqlite-Threads zurueck -- ein Test lief dadurch von
    einer Sekunde auf fuenf Minuten hoch und endete in der Zeitgrenze.
    Ein Unterprozess raeumt sich selbst auf.
    """
    env = dict(os.environ)
    env.update(extra_env)
    env.setdefault("PHANTOM_BOT_TOKEN", "x")
    try:
        done = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script), PH],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=PH,
        )
    except subprocess.TimeoutExpired:
        return False, "haengt"
    ok = done.returncode == 0 and "OK" in done.stdout
    last = (done.stderr or "").strip().splitlines()
    return ok, (last[-1][:140] if last else "")


# ------------------------------------------------------------------ #
# 1. Der Bot startet
# ------------------------------------------------------------------ #
def test_the_token_comes_from_the_environment():
    print("\nDer Token kommt aus der Umgebung")

    src = source()

    check(
        "kein Platzhalter mehr im Quelltext",
        'TOKEN = "DEIN_BOT_TOKEN_HIER"' not in src,
    )
    check("PHANTOM_BOT_TOKEN wird gelesen", 'os.getenv("PHANTOM_BOT_TOKEN")' in src)
    check(
        "und `os` ist importiert",
        re.search(r"^import os$", src, re.M) is not None,
        "ohne den Import stuerzt der Bot beim Start ab",
    )

    ok, detail = run_probe(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        import bot.ticket_bot as tb
        assert tb.TOKEN == "test-token-123", repr(tb.TOKEN)
        print("OK")
        """,
        {"PHANTOM_BOT_TOKEN": "test-token-123"},
    )
    check("der Token landet wirklich im Modul", ok, detail)


def test_it_refuses_to_start_without_a_token():
    """Mit einer Meldung, die sagt, was zu tun ist."""
    print("\nOhne Token bricht er verstaendlich ab")

    src = source()
    check(
        "die alte Meldung ist weg",
        "Bitte TOKEN in ticket_bot.py eintragen" not in src,
        "sie schickte Leute in den Quelltext statt nach Railway",
    )
    check("die neue nennt die Variable", "PHANTOM_BOT_TOKEN ist nicht gesetzt" in src)


def test_the_data_survives_a_deploy():
    """Auf Railway wird der Container bei jedem Deploy neu gebaut."""
    print("\nDie Daten ueberleben einen Deploy")

    src = source()
    check("es gibt eine Pfad-Wahl", "def _data_file" in src)
    check("DATA_DIR wird beachtet", 'os.getenv("DATA_DIR")' in src)

    with tempfile.TemporaryDirectory() as tmp:
        ok, detail = run_probe(
            """
            import sys
            sys.path.insert(0, sys.argv[1])
            import os
            import bot.ticket_bot as tb
            want = os.environ["DATA_DIR"]
            assert str(tb.DATA_FILE).startswith(want), str(tb.DATA_FILE)
            assert tb.DATA_FILE.parent.is_dir()
            print("OK")
            """,
            {"DATA_DIR": tmp},
        )
        check("mit DATA_DIR liegt die Datei im Volume", ok, detail)

    ok, detail = run_probe(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        import bot.ticket_bot as tb
        assert tb.DATA_FILE.name == "ticket_data.json", str(tb.DATA_FILE)
        print("OK")
        """,
        {"DATA_DIR": ""},
    )
    check("ohne DATA_DIR faellt es auf den Code-Ordner zurueck", ok, detail)


# ------------------------------------------------------------------ #
# 2. Kein verstecktes Tor mehr
# ------------------------------------------------------------------ #
def test_there_is_no_remote_kill_switch():
    """Die README verspricht das -- jetzt stimmt es auch."""
    print("\nKeine Fernabschaltung")

    src = source()

    for gone, what in [
        ("_Z0", "verschleierte Adresse"),
        ("_Z1", "Abfrageintervall"),
        ("_Z2", "Zustandsmerker"),
        ("_xg", "base64-Entschluessler"),
        ("_rt_pull", "Netzabruf"),
        ("_rt_tick", "Zustandsabfrage"),
        ("_rt_loop", "Hintergrundschleife"),
    ]:
        check(f"{what} ({gone}) ist weg", gone not in src)

    check(
        "keine base64-Nutzlast mehr",
        "b64decode" not in src,
        "eine verschleierte Adresse gehoert nicht in einen Bot",
    )
    check(
        "kein Abruf aus dem fremden Repo",
        "raw.githubusercontent.com" not in src,
    )

    # Die Funktion bleibt -- sie hat rund 200 Aufrufstellen -- gibt
    # aber immer True. Geprueft wird die Wirkung, nicht der Name.
    ok, detail = run_probe(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        import bot.ticket_bot as tb
        assert tb.is_bot_functions_enabled() is True
        print("OK")
        """,
        {},
    )
    check("die Pruefung sagt immer ja", ok, detail)


def test_the_readme_is_honest():
    print("\nDie README stimmt")

    readme = open(os.path.join(PH, "README.md"), encoding="utf-8").read()
    # Auf die Aussage pruefen, nicht auf ein einzelnes Wort: "Entfernt"
    # stuende auch in einer Fassung, die faelschlich behauptet, es sei
    # nur "frueher anders" gewesen.
    check(
        "sie sagt, dass es jetzt stimmt",
        "Stimmt jetzt" in readme,
        "eine halbe Aussage ist schlimmer als keine",
    )
    check("und nennt den entfernten Schalter", "Entfernt" in readme)


# ------------------------------------------------------------------ #
# 3. Die Anbindung ans Dashboard
# ------------------------------------------------------------------ #
def test_the_bot_talks_to_the_dashboard():
    """Ohne das bleibt das Dashboard leer.

    Es zeigt bewusst nur Server aus `bot_guilds`, und diese Tabelle
    fuellt allein der Bot.
    """
    print("\nDer Bot fuellt das Dashboard")

    src = source()

    check("es gibt den Abgleich", "async def sync_bot_guilds_to_db" in src)

    # Auf den on_ready-Block eingrenzen: `await sync_bot_guilds_to_db()`
    # steht auch in on_guild_join, und eine Suche ueber die ganze Datei
    # blieb deshalb gruen, obwohl der Start-Aufruf fehlte.
    ready = src.split("async def on_ready")[1].split("\n@bot.event")[0]
    check(
        "er wird beim Start gerufen",
        "await sync_bot_guilds_to_db()" in ready,
        "ohne das ist das Dashboard nach einem Neustart leer",
    )
    check("es gibt eine Nachzieh-Schleife", "_phantom_guild_sync_loop" in src)

    # Die Ereignisse muessen angemeldet sein -- der blosse Name reicht
    # nicht, ohne Dekorator ruft discord.py sie nie.
    for handler in ("on_guild_join", "on_guild_remove", "on_guild_update"):
        registered = re.search(
            r"@bot\.event\s*\n\s*async def " + handler + r"\(", src
        )
        check(f"{handler} ist angemeldet", bool(registered))

    for fn in ("dash_register_ticket", "dash_claim_ticket", "dash_close_ticket"):
        check(f"{fn} gibt es", f"async def {fn}" in src)

    check(
        "register_ticket meldet ans Dashboard",
        re.search(
            r"def register_ticket\([\s\S]{0,2000}?_dash_fire\(\s*\n?\s*dash_register_ticket",
            src,
        )
        is not None,
    )

    # set_claimer UND clear_claimer einzeln pruefen. Beide rufen
    # dieselbe Melde-Funktion; eine Suche ueber die Datei blieb gruen,
    # wenn genau eine davon fehlte.
    claim_block = src.split("def set_claimer")[1].split("def clear_claimer")[0]
    check(
        "set_claimer meldet ans Dashboard",
        "_dash_fire(dash_claim_ticket(channel_id, user_id))" in claim_block,
    )
    unclaim_block = src.split("def clear_claimer")[1].split("def set_ticket_status")[0]
    check(
        "clear_claimer meldet ebenfalls",
        "_dash_fire(dash_claim_ticket(channel_id, None))" in unclaim_block,
        "sonst bleibt ein zurueckgegebenes Ticket im Dashboard geclaimt",
    )
    check(
        "pop_ticket meldet ans Dashboard",
        re.search(r"def pop_ticket\([\s\S]{0,800}?_dash_fire\(dash_close_ticket", src)
        is not None,
    )


def test_the_mirror_really_works():
    """Nicht nur den Text lesen -- ausfuehren.

    Gegen eine echte SQLite-Datei, mit einem vorgetaeuschten Bot.
    """
    print("\nDer Abgleich funktioniert wirklich")

    with tempfile.TemporaryDirectory() as tmp:
        ok, detail = run_probe(
            """
            import sys, asyncio
            sys.path.insert(0, sys.argv[1])
            import bot.ticket_bot as tb
            from app import db as dbmod

            class G:
                def __init__(self, gid, name):
                    self.id = gid
                    self.name = name
                    self.icon = None
                    self.member_count = 7
                    self.owner_id = 1

            class FakeBot:
                guilds = [G(111, "Alpha"), G(222, "Beta")]

            async def go():
                tb.bot = FakeBot()
                await tb.sync_bot_guilds_to_db()
                db = await tb._phantom_db_conn()

                names = [dict(r)["name"] for r in await dbmod.list_bot_guilds(db)]
                assert names == ["Alpha", "Beta"], names
                assert await dbmod.is_bot_in_guild(db, 111)
                assert not await dbmod.is_bot_in_guild(db, 999)

                await tb.dash_register_ticket(500, 111, 42, "support")
                rows = await dbmod.list_open_tickets(db, 111)
                assert len(rows) == 1, len(rows)

                await tb.dash_claim_ticket(500, 77)
                rows = await dbmod.list_open_tickets(db, 111)
                assert dict(rows[0]).get("claimed_by") == 77

                await tb.dash_close_ticket(500)
                assert len(await dbmod.list_open_tickets(db, 111)) == 0

                tb.bot = type("B", (), {"guilds": []})()
                await tb.sync_bot_guilds_to_db()
                assert len(await dbmod.list_bot_guilds(db)) == 0

                await db.close()

            asyncio.run(go())
            print("OK")
            """,
            {"DATA_DIR": tmp, "PHANTOM_DB_PATH": os.path.join(tmp, "t.db")},
        )
        check("Spiegeln, Ticket, Claim, Schliessen, Verlassen", ok, detail)


def test_a_broken_dashboard_does_not_stop_tickets():
    """Das Dashboard ist Beiwerk.

    Klemmt die Datenbank, muss ein Ticket trotzdem funktionieren --
    sonst legte der Bot sich durch sein eigenes Dashboard lahm.
    """
    print("\nEin kaputtes Dashboard blockiert nichts")

    src = source()
    block = src.split("async def _phantom_db_conn")[1].split("async def")[0]

    # Das `except` muss den Fehler SCHLUCKEN, nicht weiterwerfen.
    # `except Exception: raise` liesse beide Woerter stehen und legte
    # den Bot trotzdem lahm.
    swallows = re.search(r"except Exception as exc:[\s\S]{0,400}?return None", block)
    check(
        "ein Fehler wird geschluckt, nicht weitergeworfen",
        bool(swallows) and "raise" not in block,
        "ein `raise` legt den Bot durch sein eigenes Dashboard lahm",
    )
    check(
        "sie versucht es nicht endlos neu",
        "_phantom_db_broken = True" in block,
        "sonst stuende bei jedem Ticket eine Warnung im Log",
    )

    for fn in ("dash_register_ticket", "dash_claim_ticket", "dash_close_ticket"):
        body = src.split(f"async def {fn}")[1].split("async def")[0]
        check(f"{fn} bricht ohne Datenbank ab", "if db is None:" in body)

    # Und ausfuehren: mit einem unbrauchbaren Pfad darf nichts fliegen.
    ok, detail = run_probe(
        """
        import sys, asyncio
        sys.path.insert(0, sys.argv[1])
        import bot.ticket_bot as tb

        async def go():
            conn = await tb._phantom_db_conn()
            assert conn is None, repr(conn)
            await tb.dash_register_ticket(1, 2, 3, "support")
            await tb.dash_claim_ticket(1, 4)
            await tb.dash_close_ticket(1)

        asyncio.run(go())
        print("OK")
        """,
        {"PHANTOM_DB_PATH": "/proc/darf-nicht/geht.db", "DATA_DIR": ""},
    )
    check("kaputte Datenbank gibt None, Melder werfen nicht", ok, detail)


def test_the_background_tasks_are_kept():
    """asyncio sammelt eine laufende Aufgabe sonst weg."""
    print("\nDie Hintergrundaufgaben werden festgehalten")

    src = source()
    check("die Sync-Schleife hat einen Halter", "_phantom_sync_task" in src)
    check("die Dashboard-Aufrufe auch", "_dash_tasks.add(task)" in src)
    check("und werden danach freigegeben", "_dash_tasks.discard" in src)


def test_the_connection_is_closed_on_shutdown():
    """Sonst haengt der Prozess beim Beenden.

    aiosqlite fuehrt je Verbindung einen Hintergrund-Thread. Railway
    bricht nach seiner Frist hart ab -- ein laufender Schreibvorgang
    kann dabei mitten in der Datei enden.
    """
    print("\nBeim Beenden wird aufgeraeumt")

    src = source()
    registered = re.search(r"@bot\.event\s*\n\s*async def on_close\(", src)
    check("on_close ist angemeldet", bool(registered))

    block = src.split("async def on_close")[1].split("def main")[0]
    check("die Verbindung wird geschlossen", "_phantom_db.close()" in block)
    check("und der Merker geleert", "_phantom_db = None" in block)


def test_no_undefined_names():
    """Ruff findet abgeschnittene Namen, die erst zur Laufzeit fliegen.

    Konkret stand an einer Stelle ein blosses `sche` -- ein halb
    eingefuegtes `schedule_save()`, direkt an eine Kommentarzeile
    geklebt. Syntaktisch gueltig (Python liest es als Variable), aber
    beim Ausfuehren ein NameError. Ausgeloest wurde er, sobald ein
    Ticket-Besitzer in einem nicht wartenden Ticket schrieb.
    """
    print("\nKeine undefinierten Namen")

    try:
        done = subprocess.run(
            [
                sys.executable, "-m", "ruff", "check",
                "--select=E9,F821,F811", "--output-format=concise", ".",
            ],
            capture_output=True, text=True, timeout=120, cwd=PH,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"  --   ruff nicht verfuegbar ({type(exc).__name__}), uebersprungen")
        return

    hits = [
        line for line in (done.stdout or "").splitlines()
        if line.strip() and not line.startswith("All checks")
    ]
    check("ruff findet nichts", not hits, "; ".join(hits[:3]))


def test_it_still_parses_and_imports():
    print("\nDie Datei ist heil")

    raw = open(TICKET_BOT, encoding="utf-8").read()
    try:
        ast.parse(raw)
        ok = True
    except SyntaxError as exc:
        ok = False
        print(f"       {exc}")
    check("Syntax stimmt", ok)

    loaded, detail = run_probe(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        import bot.ticket_bot  # noqa
        print("OK")
        """,
        {},
    )
    check("das Modul laedt", loaded, detail)


def main() -> int:
    test_the_token_comes_from_the_environment()
    test_it_refuses_to_start_without_a_token()
    test_the_data_survives_a_deploy()
    test_there_is_no_remote_kill_switch()
    test_the_readme_is_honest()
    test_the_bot_talks_to_the_dashboard()
    test_the_mirror_really_works()
    test_a_broken_dashboard_does_not_stop_tickets()
    test_the_background_tasks_are_kept()
    test_the_connection_is_closed_on_shutdown()
    test_no_undefined_names()
    test_it_still_parses_and_imports()

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
