#!/usr/bin/env python3
"""
Warnungen: Bot und Dashboard muessen dasselbe sehen.

Zwei Fehler waren der Anlass, und danach ist dieser Test sortiert:

  1. ``>warn @user Spam`` schrieb nur einen Zaehler. Grund und
     Moderator standen nirgends, das Dashboard zeigte eine nackte Zahl.
  2. ``>clearwarns @user`` setzte den Zaehler auf 0, liess die
     Protokolleintraege aber auf ``active = 1``. Das Dashboard zeigte
     geloeschte Warnungen weiter an.

Beides kam daher, dass der Cog und ``api/routes/moderation.py`` je
eigenes SQL auf dieselbe Datei hatten. Deshalb prueft dieser Test nicht
nur das Verhalten, sondern auch, dass beide Seiten wirklich
``utils/warn_store.py`` benutzen -- sonst waechst der alte Zustand
nach.

Run:  python3 tests/test_warn_store.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

import aiosqlite

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import warn_store  # noqa: E402

failures: list[str] = []

GUILD, USER, MOD = 1530378233579704370, 1303627964734246944, 1033826242270609449


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def strip_py(src: str) -> str:
    """Kommentare und Docstrings entfernen, damit Treffer echt sind."""
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


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


async def dashboard_sicht(gid: int, uid: int) -> dict:
    """Die Abfrage aus list_warnings(), auf einen Nutzer verkuerzt."""
    async with aiosqlite.connect(warn_store.WARN_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, warns FROM warns WHERE guild_id = ? AND warns > 0", (gid,)
        ) as cur:
            counters = [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT * FROM warn_log WHERE guild_id = ? AND active = 1", (gid,)
        ) as cur:
            entries = [dict(r) for r in await cur.fetchall()]

    by_user: dict[int, dict] = {}
    for row in counters:
        by_user[int(row["user_id"])] = {"count": int(row["warns"] or 0), "entries": []}
    for e in entries:
        t = by_user.setdefault(int(e["user_id"]), {"count": 0, "entries": []})
        t["entries"].append({"reason": e["reason"], "moderator_id": e["moderator_id"]})
    return by_user.get(uid, {"count": 0, "entries": []})


# ── 1. Der Grund kommt an ────────────────────────────────────────────

async def test_grund_wird_gespeichert():
    print("\n1. >warn speichert Grund und Moderator")
    stand = await warn_store.add(
        GUILD, USER, reason="Spam im Lernkanal", moderator_id=MOD
    )
    check("gibt den neuen Stand zurueck", stand == 1, f"(bekam {stand})")

    sicht = await dashboard_sicht(GUILD, USER)
    check("Zaehler kommt im Dashboard an", sicht["count"] == 1)
    check(
        "Grund kommt im Dashboard an",
        len(sicht["entries"]) == 1
        and sicht["entries"][0]["reason"] == "Spam im Lernkanal",
        f"(sah {sicht['entries']})",
    )
    check(
        "Moderator kommt im Dashboard an",
        bool(sicht["entries"]) and sicht["entries"][0]["moderator_id"] == MOD,
    )

    # Ein zu langer Grund darf die Spalte nicht sprengen.
    await warn_store.add(GUILD, 555, reason="x" * 900, moderator_id=MOD)
    verlauf = await warn_store.history(GUILD, 555)
    check("langer Grund wird gekuerzt", len(verlauf[0]["reason"]) == 500,
          f"(war {len(verlauf[0]['reason'])})")

    # Ohne Grund darf es trotzdem funktionieren.
    stand = await warn_store.add(GUILD, 556)
    check("Warnung ohne Grund geht", stand == 1, f"(bekam {stand})")


# ── 2. clearwarns raeumt beide Seiten ────────────────────────────────

async def test_clearwarns_raeumt_alles():
    print("\n2. >clearwarns nimmt auch die Protokolleintraege zurueck")
    await warn_store.add(GUILD, 601, reason="erste", moderator_id=MOD)
    await warn_store.add(GUILD, 601, reason="zweite", moderator_id=MOD)

    vorher = await dashboard_sicht(GUILD, 601)
    check("vorher zwei Eintraege sichtbar", len(vorher["entries"]) == 2)

    entfernt = await warn_store.clear(GUILD, 601)
    check("clear meldet die Anzahl", entfernt == 2, f"(meldete {entfernt})")

    nachher = await dashboard_sicht(GUILD, 601)
    check("Zaehler ist auf 0", nachher["count"] == 0)
    check(
        "Dashboard zeigt keine Warnung mehr",
        len(nachher["entries"]) == 0,
        f"({len(nachher['entries'])} blieben stehen)",
    )
    check("count_of stimmt ueberein", await warn_store.count_of(GUILD, 601) == 0)

    # Zweimal loeschen darf nichts kaputtmachen.
    check("zweites clear meldet 0", await warn_store.clear(GUILD, 601) == 0)


# ── 3. Alte Warnungen ohne Protokoll ─────────────────────────────────

async def test_alte_warnungen_bleiben():
    print("\n3. Warnungen von vor der Umstellung zaehlen weiter")
    # So sah die Datenbank vorher aus: ein Zaehler, kein Protokoll.
    async with aiosqlite.connect(warn_store.WARN_DB) as db:
        await warn_store.ensure_schema(db)
        await db.execute(
            "INSERT OR REPLACE INTO warns (guild_id, user_id, warns) VALUES (?, ?, 4)",
            (GUILD, 700),
        )
        await db.commit()

    check("alter Zaehler bleibt sichtbar",
          await warn_store.count_of(GUILD, 700) == 4)

    neu = await warn_store.add(GUILD, 700, reason="neu", moderator_id=MOD)
    check("neue Warnung baut darauf auf", neu == 5, f"(bekam {neu})")


# ── 4. Einzelne Warnung zuruecknehmen ────────────────────────────────

async def test_einzelne_warnung():
    print("\n4. Einzelne Warnung zuruecknehmen")
    await warn_store.add(GUILD, 800, reason="erste", moderator_id=MOD)
    await warn_store.add(GUILD, 800, reason="zweite", moderator_id=MOD)

    verlauf = await warn_store.history(GUILD, 800)
    check("Verlauf ist neueste zuerst",
          [e["reason"] for e in verlauf] == ["zweite", "erste"],
          f"(war {[e['reason'] for e in verlauf]})")

    ziel = [e for e in verlauf if e["reason"] == "erste"][0]
    ergebnis = await warn_store.remove_one(GUILD, ziel["id"])
    check("meldet Nutzer und neuen Stand", ergebnis == (800, 1), f"(bekam {ergebnis})")

    rest = await warn_store.history(GUILD, 800)
    check("nur die zweite bleibt",
          len(rest) == 1 and rest[0]["reason"] == "zweite")
    check("unbekannte ID gibt None",
          await warn_store.remove_one(GUILD, 999999) is None)
    check("dieselbe ID zweimal gibt None",
          await warn_store.remove_one(GUILD, ziel["id"]) is None)


# ── 5. Server bleiben getrennt ───────────────────────────────────────

async def test_server_getrennt():
    print("\n5. Warnungen wirken nur im eigenen Server")
    ANDERER = 999888777666555
    await warn_store.add(GUILD, 900, reason="hier", moderator_id=MOD)
    await warn_store.add(ANDERER, 900, reason="woanders", moderator_id=MOD)

    check("beide Server zaehlen einzeln",
          await warn_store.count_of(GUILD, 900) == 1
          and await warn_store.count_of(ANDERER, 900) == 1)

    await warn_store.clear(GUILD, 900)

    # Hier reicht count_of NICHT. Es nimmt max(Zaehler, Protokoll) --
    # wuerde clear() das Protokoll serveruebergreifend loeschen, bliebe
    # der Zaehler des anderen Servers stehen und max() verdeckte den
    # Schaden. Sichtbar wird er erst eine Ebene tiefer, genau dort, wo
    # auch das Dashboard liest.
    check("clear trifft nur den einen Server (Zaehler)",
          await warn_store.count_of(GUILD, 900) == 0
          and await warn_store.count_of(ANDERER, 900) == 1)

    hier = await warn_store.history(GUILD, 900)
    dort = await warn_store.history(ANDERER, 900)
    check("Protokoll hier ist leer", len(hier) == 0, f"({len(hier)} uebrig)")
    check("Protokoll im anderen Server bleibt vollstaendig",
          len(dort) == 1 and dort[0]["reason"] == "woanders",
          f"(sah {dort})")

    sicht = await dashboard_sicht(ANDERER, 900)
    check("Dashboard des anderen Servers zeigt die Warnung noch",
          len(sicht["entries"]) == 1, f"(sah {sicht})")

    # Dasselbe fuer die einzelne Ruecknahme: eine ID aus Server A darf
    # in Server B nicht greifen.
    await warn_store.add(GUILD, 901, reason="A", moderator_id=MOD)
    eintrag_a = (await warn_store.history(GUILD, 901))[0]
    check("fremde Server-ID kann Eintrag nicht zuruecknehmen",
          await warn_store.remove_one(ANDERER, eintrag_a["id"]) is None)
    check("Eintrag ist unveraendert da",
          len(await warn_store.history(GUILD, 901)) == 1)


# ── 6. Beide Seiten nutzen wirklich dieselbe Schicht ─────────────────

def test_beide_seiten_verdrahtet():
    print("\n6. Cog und API gehen ueber warn_store")
    cog = strip_py(read("cogs/moderation/warn.py"))
    api = strip_py(read("api/routes/moderation.py"))

    check("Cog importiert warn_store", "warn_store" in cog)
    check("API importiert warn_store", "warn_store" in api)

    # Der eigentliche Punkt: kein eigenes SQL mehr auf warn_log/warns.
    # Sonst laufen die Seiten beim naechsten Umbau wieder auseinander.
    cog_sql = re.findall(r"(INSERT INTO warn_log|UPDATE warns|INSERT OR IGNORE INTO warns)", cog)
    check("Cog schreibt kein eigenes Warn-SQL mehr", not cog_sql, f"(fand {cog_sql})")

    api_sql = re.findall(r"INSERT INTO warn_log|UPDATE warn_log SET active", api)
    check("API schreibt kein eigenes Warn-SQL mehr", not api_sql, f"(fand {api_sql})")

    # Und der Befehl muss den Grund auch wirklich weiterreichen.
    check("’>warn’ gibt reason weiter",
          bool(re.search(r"add_warn\([^)]*reason\s*=", cog, re.S)))
    check("’>warn’ gibt den Moderator weiter",
          bool(re.search(r"add_warn\([^)]*moderator_id\s*=", cog, re.S)))

    # schema_guard muss den Index kennen, sonst ist er nur im Store.
    guard = read("api/schema_guard.py")
    check("schema_guard kennt den warn_log-Index",
          "idx_warn_log_guild_user" in guard)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)   # warn_store schreibt nach db/warn.db
        try:
            await test_grund_wird_gespeichert()
            await test_clearwarns_raeumt_alles()
            await test_alte_warnungen_bleiben()
            await test_einzelne_warnung()
            await test_server_getrennt()
        finally:
            os.chdir(alt)

    test_beide_seiten_verdrahtet()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Warnsystem: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
