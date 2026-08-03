#!/usr/bin/env python3
"""
Der Speedrun-Reiter im Dashboard.

Hier gibt es keinen Browser, also wird geprüft, was sich ohne einen
prüfen lässt — und zwar die Sachen, die in diesem Projekt schon einmal
schiefgegangen sind:

  * Ein Reiter ohne Seite (oder eine Seite ohne Reiter). Genau das war
    bei „Tracking“ der Fall: die Seite existierte, der Reiter nicht, und
    der einzige Weg hinein war die URL von Hand.
  * Ein Aufruf, den der Proxy nicht kennt. Jede /api/bot-Anfrage läuft
    durch eine Bereichsregel; fehlt sie, kommt 404 statt Daten.
  * React-Hooks hinter einem frühen `return`. Das ist kein Stilfehler,
    das ist ein Absturz beim zweiten Rendern.
  * Deutsche Anführungszeichen in TypeScript-Zeichenketten: ein
    schließendes `"` beendet die Zeichenkette mitten im Satz.

Der Suchtext wird vorher von Kommentaren befreit. Ohne das findet die
Prüfung ihre eigene Erklärung wieder und meldet Erfolg — in diesem
Projekt mehr als zehnmal passiert.

Run:  python3 tests/test_speedrun_ui.py
"""

import os
import re
import sys

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


def read(*parts):
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Kommentare raus, damit eine Erklärung nicht als Code zählt."""
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


PANEL = "components/dashboard/speedrun-panel.tsx"
PAGE = "app/dashboard/guild/[guildId]/speedrun/page.tsx"
TABS = "components/guild-tabs.tsx"
PROXY = "app/api/bot/[...path]/route.ts"
API = "lib/api.ts"


def test_the_tab_and_the_page_exist_together():
    """Ein Reiter ohne Seite ist ein 404, eine Seite ohne Reiter unauffindbar."""

    print("\nReiter und Seite gehören zusammen")

    check("die Seite gibt es", bool(read(PAGE)))
    check("das Panel gibt es", bool(read(PANEL)))

    tabs = strip_comments(read(TABS))
    check("der Reiter ist eingetragen", '"speedrun"' in tabs)
    check("er ist als Beta markiert",
          bool(re.search(r'slug:\s*"speedrun"[^}]*tag:\s*"beta"', tabs, re.S)))

    # Der Reiter muss auf denselben Ordner zeigen, der auch existiert.
    page_dir = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]", "speedrun")
    check("Reiter-Ziel und Ordner stimmen überein", os.path.isdir(page_dir), page_dir)

    # Und die Seite benutzt das Panel wirklich, statt nur dazuliegen.
    page = strip_comments(read(PAGE))
    check("die Seite bindet das Panel ein", "SpeedrunPanel" in page)


def test_every_call_has_a_proxy_rule():
    """Ohne Bereichsregel antwortet der Proxy mit 404, nicht mit Daten."""

    print("\nDer Proxy kennt den Bereich")

    proxy = strip_comments(read(PROXY))
    check("es gibt eine Regel für speedrun", 'scope === "speedrun"' in proxy)

    # Sie muss vor dem Auffangbecken stehen, sonst greift sie nie.
    if 'scope === "speedrun"' in proxy:
        position = proxy.index('scope === "speedrun"')
        fallback = proxy.index('return { ok: false, response: deny(404, "Unknown API scope.") }')
        check("die Regel steht vor dem 404-Fall", position < fallback,
              f"{position} vs {fallback}")

    # Schreiben darf nicht jeder Angemeldete: ein Speedrun ist die
    # eingreifendste Aktion im Dashboard.
    block = proxy.split('scope === "speedrun"')[1].split('scope === "extras"')[0]
    check("Schreiben verlangt server.manage", '"server.manage"' in block, block[:200])
    check("der Server-Zugriff wird geprüft", "verifyGuildAccess" in block)
    check("Nichtangemeldete kommen nicht durch", "Not signed in" in block)


def test_the_api_calls_match_the_routes():
    """Jeder Aufruf im Browser muss eine Route im Bot treffen."""

    print("\nDie Aufrufe treffen echte Routen")

    from api.routes import speedrun as route_module

    # Was der Bot anbietet, mit dem Präfix aus api/server.py.
    offered = {f"/speedrun{r.path}" for r in route_module.router.routes}

    api_src = strip_comments(read(API))
    block = api_src.split("speedrunPrecheck")[1] if "speedrunPrecheck" in api_src else ""

    # Die Pfade aus den Template-Strings holen, Platzhalter normalisieren.
    called = set()
    for raw in re.findall(r"`(/speedrun[^`]*)`", block):
        path = raw.split("?")[0]
        path = re.sub(r"\$\{[^}]+\}", "{guild_id}", path)
        called.add(path)

    check("es werden Aufrufe gefunden", len(called) >= 5, str(sorted(called)))

    unknown = sorted(p for p in called if p not in offered)
    check("jeder Aufruf hat eine Route", not unknown,
          f"unbekannt: {unknown} — vorhanden: {sorted(offered)}")


def test_hooks_come_before_any_early_return():
    """Ein Hook nach einem frühen return stürzt beim zweiten Rendern ab."""

    print("\nAlle Hooks stehen vor dem ersten return")

    source = strip_comments(read(PANEL))

    # Nur die Hauptkomponente ansehen; die Hilfskomponenten darüber
    # haben ihre eigenen Hooks und ihr eigenes return.
    start = source.index("export function SpeedrunPanel")
    body = source[start:]

    early = body.find("\n    return (")
    check("die Komponente hat ein return", early > 0)

    head = body[:early]
    tail = body[early:]

    hooks_after = re.findall(r"\b(useState|useEffect|useCallback|useRef|useSession)\s*\(", tail)
    check("kein Hook nach dem ersten return", not hooks_after, str(hooks_after))

    hooks_before = re.findall(r"\b(useState|useEffect|useCallback|useRef|useSession)\s*\(", head)
    check("die Hooks stehen davor", len(hooks_before) >= 8, str(len(hooks_before)))


def test_no_german_quotes_break_a_string():
    """„…" beendet in TypeScript die Zeichenkette — „…“ nicht."""

    print("\nDeutsche Anführungszeichen sind heil")

    for name in (PANEL, PAGE):
        source = read(name)
        # Das schließende Zeichen " ist ein echtes ASCII-Anführungszeichen
        # und beendet jede Zeichenkette, in der es steht.
        broken = source.count("\u201e") - source.count("\u201c")
        check(f"{os.path.basename(name)}: öffnende und schließende passen",
              broken == 0,
              f"{source.count(chr(0x201e))} auf, {source.count(chr(0x201c))} zu")


def test_the_browser_decides_nothing():
    """Die Sperren müssen beim Bot liegen, nicht im Panel."""

    print("\nDer Browser entscheidet nichts")

    panel = strip_comments(read(PANEL))

    # Die Beta-Liste darf nicht im Panel stehen: sonst reicht die
    # Entwicklerkonsole, um ein ungeprüftes Template loszuschicken.
    check("keine Template-Liste im Panel",
          "BETA_TEMPLATES" not in panel and '"community"' not in panel,
          "die Sperre läge im Browser")

    # Das Panel liest die Freigabe vom Server, statt sie zu berechnen.
    check("die Freigabe kommt vom Bot", "template.available" in panel)

    # Und es zieht daraus auch die Folgerungen. Nur zu prüfen, dass das
    # Wort „locked_reason“ irgendwo vorkommt, wäre wertlos: es steht
    # auch dann noch da, wenn die Anzeige hinter `false &&` hängt.
    check("gesperrtes Template ist nicht anklickbar",
          "disabled={locked}" in panel,
          "ohne disabled ließe sich ein gesperrtes Template auswählen")
    check("der Grund steht am gesperrten Template",
          "{locked && template.locked_reason && (" in panel,
          "der Grund wird nicht (oder unabhängig von locked) angezeigt")

    # Der Partner-Token darf nirgends im Dashboard auftauchen.
    for name in (PANEL, PAGE, API):
        source = read(name)
        check(f"{os.path.basename(name)}: kein Partner-Token",
              "PARTNER_TOKEN" not in source and "X-Partner-Token" not in source)


def test_the_progress_poll_cannot_start_twice():
    """Sonst startet jede Abfrage eine neue Einrichtung."""

    print("\nDie zweite Hälfte startet genau einmal")

    panel = strip_comments(read(PANEL))

    check("es gibt einen Riegel", "finishedRef" in panel)
    # Er muss abgefragt werden, bevor gestartet wird -- und gesetzt,
    # bevor der Aufruf rausgeht. Andernfalls schafft es die nächste
    # Abfrage (1,5 s später) noch dazwischen.
    finish_block = panel.split("api.speedrunFinish")[0]
    check("er wird vorher geprüft", "!finishedRef.current" in finish_block)
    check("und vorher gesetzt", "finishedRef.current = true" in finish_block)

    # Zähler in Refs, nicht im State: ein State-Wert wäre in der Closure
    # des Timers eingefroren und würde dieselben Zeilen doppelt holen.
    check("die Zeilenzähler sind Refs",
          "sinceRef" in panel and "sinceMainRef" in panel)
    check("zwei getrennte Zähler",
          "since_main" in read(API) or "sinceMain" in read(API))


def test_the_console_does_not_fight_the_reader():
    """Automatisches Mitrollen darf nicht die Zeile wegreißen, die man liest."""

    print("\nDas Terminal rollt nur mit, wenn man unten steht")

    panel = strip_comments(read(PANEL))
    check("es gibt eine Haftung am unteren Rand", "stickRef" in panel)
    check("gescrollt wird nur mit ihr", "if (box && stickRef.current)" in panel)
    check("Scrollen setzt sie zurück", "onScroll" in panel)


def main():
    test_the_tab_and_the_page_exist_together()
    test_every_call_has_a_proxy_rule()
    test_the_api_calls_match_the_routes()
    test_hooks_come_before_any_early_return()
    test_no_german_quotes_break_a_string()
    test_the_browser_decides_nothing()
    test_the_progress_poll_cannot_start_twice()
    test_the_console_does_not_fight_the_reader()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
