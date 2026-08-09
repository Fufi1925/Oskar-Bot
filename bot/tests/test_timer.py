#!/usr/bin/env python3
"""
Der Timer-Befehl.

Fuenf Fehler waren der Anlass, und danach ist dieser Test sortiert:

  1. Eine Schleife bearbeitete die Nachricht alle sechs Sekunden --
     14.400 Bearbeitungen bei den erlaubten 24 Stunden.
  2. ``self.client`` gibt es nicht; ``__init__`` setzt ``self.bot``.
  3. ``channel.get_message()`` heisst seit discord.py 2.0
     ``fetch_message()``.
  4. ``users().flatten()`` gibt es seit 2.0 nicht mehr.
  5. Ein nacktes ``except: break`` verschluckte 2 bis 4, weshalb nie
     jemand etwas gemeldet hat.

Dazu kam, dass ein Neustart jeden laufenden Timer spurlos verschluckte.

Run:  python3 tests/test_timer.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import timer_store  # noqa: E402

failures: list[str] = []

GUILD, KANAL, USER = 1530378233579704370, 111222333, 1303627964734246944


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


SRC = strip_py(open(os.path.join(BOT, "cogs/commands/timer.py"), encoding="utf-8").read())


# ── 1. Kein Rate-Limit mehr ──────────────────────────────────────────

def test_keine_dauerbearbeitung():
    print("\n1. Der Bot bearbeitet die Nachricht nicht mehr im Takt")
    check(
        "keine while-True-Schleife mit sleep(6)",
        not ("while True" in SRC and re.search(r"asyncio\.sleep\(\s*6\s*\)", SRC)),
        "-> waren 14400 Bearbeitungen bei 24 h",
    )
    # Der Zeitstempel ist der Grund, warum es ohne geht: den zaehlt der
    # Client des Betrachters selbst herunter.
    check("nutzt Discords Zeitstempel <t:...:R>",
          bool(re.search(r"<t:\{?\w+\}?:R>", SRC)))
    # message.edit darf im Timer gar nicht mehr vorkommen.
    check("kein message.edit mehr", ".edit(" not in SRC,
          "-> jede Bearbeitung zaehlt gegen das Rate-Limit")


# ── 2 bis 5. Die Abstuerze ───────────────────────────────────────────

def test_abstuerze_weg():
    print("\n2. Die vier Abstuerze beim Ablaufen")
    check("kein self.client", not re.search(r"self\.client\b", SRC),
          "-> AttributeError, __init__ setzt self.bot")
    check("kein channel.get_message", "get_message(" not in SRC,
          "-> heisst seit discord.py 2.0 fetch_message")
    check("kein users().flatten()", ".flatten()" not in SRC,
          "-> users() ist seit 2.0 ein AsyncIterator")
    check("kein nacktes except", not re.search(r"\n\s*except\s*:\s*\n", SRC),
          "-> hat genau diese Abstuerze verschluckt")

    # Fehler sollen protokolliert werden statt zu verschwinden.
    check("Fehler werden protokolliert", "logger." in SRC)

    # Und die benutzten APIs muss es in der installierten Fassung geben.
    import discord
    check("fetch_message existiert wirklich",
          hasattr(discord.TextChannel, "fetch_message"),
          f"(discord.py {discord.__version__})")


# ── 6. Der Neustart ──────────────────────────────────────────────────

async def test_ueberlebt_neustart():
    print("\n3. Ein Neustart verliert keinen Timer mehr")
    jetzt = 1770000000

    tid = await timer_store.create(
        GUILD, KANAL, USER, title="Klausur-Lernblock", ends_at=jetzt + 600
    )
    await timer_store.attach_message(tid, 444555)
    check("Timer bekommt eine Nummer", tid >= 1)
    check("noch nicht faellig", len(await timer_store.due(jetzt)) == 0)

    # Kein gemeinsamer Zustand -- nur die Datei. Genau das fehlte vorher.
    faellig = await timer_store.due(jetzt + 601)
    check("nach dem Neustart wieder auffindbar", len(faellig) == 1)
    if faellig:
        e = faellig[0]
        check("Kanal gemerkt", e["channel_id"] == KANAL)
        check("Nachricht gemerkt", e["message_id"] == 444555)
        check("Titel gemerkt", e["title"] == "Klausur-Lernblock")
        check("Nutzer gemerkt", e["user_id"] == USER)

    await timer_store.finish(tid)
    check("nach finish nicht mehr faellig",
          len(await timer_store.due(jetzt + 601)) == 0)

    # Ein Timer ohne Nachricht (Absturz zwischen Anlegen und Senden)
    # darf trotzdem sauber ablaufen.
    t2 = await timer_store.create(GUILD, KANAL, USER, title="ohne", ends_at=jetzt)
    offen = [e for e in await timer_store.due(jetzt) if e["id"] == t2]
    check("Timer ohne Nachricht laeuft trotzdem ab",
          len(offen) == 1 and offen[0]["message_id"] is None)
    await timer_store.finish(t2)


# ── 7. Dauer-Erkennung ───────────────────────────────────────────────

def test_dauer():
    print("\n4. Dauer-Eingaben")
    gut = {
        "30": 30, "45s": 45, "10m": 600, "2h": 7200,
        "1d": 86400, "1h30m": 5400, "2d12h": 216000, "1h 30m": 5400,
    }
    for eingabe, erwartet in gut.items():
        ergebnis = timer_store.parse_duration(eingabe)
        check(f"'{eingabe}' = {erwartet} s", ergebnis == erwartet, f"(bekam {ergebnis})")

    # Die alte Fassung las nur das letzte Zeichen und warf sonst einen
    # ValueError, den das nackte except verschluckte.
    for schlecht in ("abc", "5x", "", "10mm", "m", "-5m"):
        check(f"'{schlecht}' wird abgelehnt",
              timer_store.parse_duration(schlecht) is None,
              f"(bekam {timer_store.parse_duration(schlecht)})")

    # Glatte Werte sind hier die schaerfere Probe: bei 3725 s faellt ein
    # Rechenfehler von einer Sekunde nicht auf, bei genau 3600 s schon --
    # aus "1 Stunde" wuerde "60 Minuten".
    formate = {
        45: "45 Sekunden",
        60: "1 Minute",
        3600: "1 Stunde",
        3725: "1 Stunde, 2 Minuten",
        5400: "1 Stunde, 30 Minuten",
        7200: "2 Stunden",
        86400: "1 Tag",
        172800: "2 Tage",
        90061: "1 Tag, 1 Stunde, 1 Minute",
    }
    for sekunden, erwartet in formate.items():
        ergebnis = timer_store.format_duration(sekunden)
        check(f"format_duration({sekunden}) = '{erwartet}'", ergebnis == erwartet,
              f"(war '{ergebnis}')")


# ── 8. Abbrechen ─────────────────────────────────────────────────────

async def test_abbrechen():
    print("\n5. Timer abbrechen")
    jetzt = 1770000000
    tid = await timer_store.create(GUILD, KANAL, USER, title="x", ends_at=jetzt + 900)

    # Ohne die Nutzer-Pruefung koennte jeder fremde Nummern durchprobieren.
    check("fremder Nutzer kann nicht abbrechen",
          await timer_store.cancel(tid, 424242) is False)
    check("Timer laeuft danach noch",
          len(await timer_store.active_for(USER, GUILD)) >= 1)
    check("eigener Nutzer kann abbrechen",
          await timer_store.cancel(tid, USER) is True)
    check("zweimal abbrechen geht nicht",
          await timer_store.cancel(tid, USER) is False)


# ── 9. Aufraeumen ────────────────────────────────────────────────────

async def test_aufraeumen():
    print("\n6. Alte Eintraege werden weggeraeumt")
    import time as _t
    alt = int(_t.time()) - 30 * 86400
    tid = await timer_store.create(GUILD, KANAL, USER, title="alt", ends_at=alt)
    await timer_store.finish(tid)

    neu = await timer_store.create(
        GUILD, KANAL, USER, title="neu", ends_at=int(_t.time()) + 600
    )

    entfernt = await timer_store.cleanup(older_than_days=7)
    check("alter Eintrag verschwindet", entfernt >= 1, f"(entfernte {entfernt})")
    check("laufender Timer bleibt",
          any(e["id"] == neu for e in await timer_store.active_for(USER, GUILD)))


# ── 10. Der Cog ist verdrahtet ───────────────────────────────────────

def test_registriert():
    print("\n7. Cog und Schema sind eingetragen")
    init = open(os.path.join(BOT, "cogs/__init__.py"), encoding="utf-8").read()
    check("Timer wird importiert", "from .commands.timer import Timer" in init)
    check("Timer wird hinzugefuegt", "add_cog(Timer(bot))" in init)

    guard = open(os.path.join(BOT, "api/schema_guard.py"), encoding="utf-8").read()
    check("schema_guard kennt db/timer.db", '"db/timer.db"' in guard)
    check("schema_guard kennt den Index", "idx_timers_due" in guard)

    # Der Hintergrundlauf muss auch wirklich starten. "Der Text kommt vor"
    # reicht dafuer nicht: `pass  # self.check_timers.start()` enthaelt ihn
    # ebenfalls, startet aber nichts. Deshalb wird der Syntaxbaum gefragt,
    # ob in __init__ tatsaechlich ein Aufruf steht.
    baum = ast.parse(open(os.path.join(BOT, "cogs/commands/timer.py"),
                          encoding="utf-8").read())

    def ruft_auf(funktionsname: str, methode: str) -> bool:
        for knoten in ast.walk(baum):
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and knoten.name == funktionsname:
                for unter in ast.walk(knoten):
                    if isinstance(unter, ast.Call) \
                            and isinstance(unter.func, ast.Attribute) \
                            and unter.func.attr == methode:
                        return True
        return False

    check("Hintergrundlauf wird in __init__ wirklich gestartet",
          ruft_auf("__init__", "start"),
          "-> ein auskommentierter Aufruf zaehlt nicht")
    check("Hintergrundlauf wird beim Entladen wirklich gestoppt",
          ruft_auf("cog_unload", "cancel"))
    check("Hintergrundlauf wartet auf den Bot",
          ruft_auf("before_check", "wait_until_ready"))

    # Und die Schleife muss als tasks.loop registriert sein -- eine
    # gewoehnliche Methode liefe nie.
    check("check_timers ist ein tasks.loop",
          bool(re.search(r"@tasks\.loop\([^)]*\)\s*\n\s*async def check_timers", SRC)))


async def main():
    test_keine_dauerbearbeitung()
    test_abstuerze_weg()
    test_dauer()

    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)   # timer_store schreibt nach db/timer.db
        try:
            await test_ueberlebt_neustart()
            await test_abbrechen()
            await test_aufraeumen()
        finally:
            os.chdir(alt)

    test_registriert()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Timer: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
