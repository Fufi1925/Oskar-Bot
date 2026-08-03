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


def test_one_failed_call_does_not_blank_the_others():
    """
    Der Bug, den der Nutzer gemeldet hat.

    Das Laden holt drei Sachen auf einmal: die Voraussetzungen, die
    Vorlagen und die Schritte. Mit `Promise.all` wirft der ganze Block,
    sobald *einer* davon scheitert -- und dann wird auch das Ergebnis
    der geglückten verworfen.

    Im Betrieb war der Template-Bot nicht erreichbar, /templates gab
    502, und weil damit auch die erfolgreiche Antwort von /precheck
    weggeworfen wurde, blieb `pre` null. Die Oberfläche las daraus
    lauter Kreuze und behauptete, beide Bots fehlten -- obwohl sie da
    waren. Die Ursache lag beim zweiten Bot, die Anzeige zeigte auf den
    ersten.
    """

    print("\nEin gescheiterter Aufruf macht nicht alles leer")

    panel = strip_comments(read(PANEL))

    check("die drei Aufrufe laufen mit allSettled",
          "Promise.allSettled" in panel,
          "mit Promise.all verwirft ein Fehlschlag auch die geglückten Antworten")
    check("kein Promise.all mehr im Ladeweg",
          "Promise.all(" not in panel,
          "Promise.all( gefunden")

    # Jeder der drei muss einzeln ausgewertet werden.
    for name in ("precheck", "list", "stepList"):
        check(f"„{name}“ wird einzeln geprüft",
              f'{name}.status === "fulfilled"' in panel,
              f"{name} wird nicht auf fulfilled geprüft")

    # Und der Fehler muss sichtbar werden, statt sich als "fehlt"
    # auszugeben. Getrennt, denn eine kaputte Vorlagenliste sagt nichts
    # über die Voraussetzungen aus.
    check("es gibt einen eigenen Fehler für die Prüfung", "preError" in panel)
    check("und einen für die Vorlagen", "templateError" in panel)
    check("der Prüf-Fehler wird angezeigt",
          "{preError && (" in panel,
          "der Fehler wird gespeichert, aber nie gezeigt")
    check("der Vorlagen-Fehler wird angezeigt",
          "{templateError && (" in panel)

    # Und die Meldung muss die häufigste Ursache benennen. "Konnte nicht
    # geladen werden" hat den Nutzer eine Runde gekostet.
    check("die Meldung nennt TEMPLATE_BOT_URL",
          "TEMPLATE_BOT_URL" in panel)
    check("und weist auf IPv6 hin",
          "IPv6" in panel,
          "Railways internes Netz ist IPv6-only — das ist die häufigste Ursache")


def test_the_server_says_why_it_cannot_reach_the_template_bot():
    """Drei Ursachen dürfen nicht denselben Namen tragen."""

    print("\nDie 502-Meldung nennt die Ursache")

    import asyncio

    from fastapi import HTTPException

    from api.routes import speedrun

    old_url = os.environ.get("TEMPLATE_BOT_URL")
    old_token = os.environ.get("PREMIUM_PARTNER_TOKEN")
    os.environ["PREMIUM_PARTNER_TOKEN"] = "test-token"

    try:
        # 1. Niemand nimmt ab (der IPv6-Fall sieht genau so aus).
        os.environ["TEMPLATE_BOT_URL"] = "http://127.0.0.1:1"
        try:
            asyncio.run(speedrun._call_template("GET", "/x", timeout=3))
            check("abgelehnte Verbindung meldet einen Fehler", False, "kein Fehler")
        except HTTPException as exc:
            detail = str(exc.detail)
            check("abgelehnte Verbindung wird zu 502", exc.status_code == 502)
            check("und erklärt den IPv6-Fall", "IPv6" in detail, detail)

        # 2. Den Namen gibt es nicht -- falsche TEMPLATE_BOT_URL.
        os.environ["TEMPLATE_BOT_URL"] = "http://kein-solcher-dienst.railway.internal:8080"
        try:
            asyncio.run(speedrun._call_template("GET", "/x", timeout=5))
            check("unbekannter Name meldet einen Fehler", False, "kein Fehler")
        except HTTPException as exc:
            detail = str(exc.detail)
            check("unbekannter Name wird zu 502", exc.status_code == 502)
            check("und nennt TEMPLATE_BOT_URL", "TEMPLATE_BOT_URL" in detail, detail)
            check("und erwähnt den fehlenden Port",
                  "Port" in detail, detail)

        # Die beiden Meldungen dürfen nicht dieselbe sein: sie brauchen
        # verschiedene Handgriffe.
        messages = []
        for url in ("http://127.0.0.1:1", "http://kein-solcher-dienst.railway.internal:8080"):
            os.environ["TEMPLATE_BOT_URL"] = url
            try:
                asyncio.run(speedrun._call_template("GET", "/x", timeout=5))
            except HTTPException as exc:
                messages.append(str(exc.detail))
        check("die zwei Ursachen bekommen verschiedene Meldungen",
              len(messages) == 2 and messages[0] != messages[1],
              str(messages))
    finally:
        for key, value in (("TEMPLATE_BOT_URL", old_url),
                           ("PREMIUM_PARTNER_TOKEN", old_token)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_the_wipe_switch_is_hard_to_hit_by_accident():
    """
    »Alles löschen« darf niemandem versehentlich passieren.

    Es ist der einzige Schalter, der Bestehendes zerstört statt etwas
    hinzuzufügen, und Discord hat keinen Papierkorb.
    """

    print("\n»Alles löschen« ist kein Versehen")

    panel = strip_comments(read(PANEL))

    check("es gibt den Schalter", "setWipe" in panel)
    check("er ist standardmäßig aus",
          "useState(false)" in panel.split("const [wipe,")[1][:40],
          "ein Löschen, das man nur nicht abwählt, ist eine Falle")

    # Bestätigung durch Abtippen des Servernamens.
    check("es wird eine Bestätigung getippt", "wipeConfirm" in panel)
    check("sie wird mit dem Servernamen verglichen",
          "pre.guild_name" in panel or "pre?.guild_name" in panel)

    # Und der Knopf sperrt, bis sie stimmt. Sonst käme die Absage erst
    # nach dem Klick vom Server.
    check("der Startknopf sperrt ohne Bestätigung", "wipeReady" in panel)
    check("und zwar wirklich am disabled",
          "disabled={busy || !wipeReady}" in panel,
          "wipeReady wird berechnet, aber nicht benutzt")

    # Ein Abwählen darf keine getippte Bestätigung stehen lassen --
    # sonst reicht ein zweiter Klick auf den Schalter zum Auslösen.
    #
    # Nur zu prüfen, dass `setWipeConfirm("")` irgendwo vorkommt, wäre
    # wertlos: der Aufruf steht auch dann noch da, wenn er hinter
    # `if (false)` hängt. Ein Mutationstest hat genau das durchgelassen.
    # Also die Bedingung mitlesen.
    handler = panel.split("onCheckedChange={(value) => {")
    check("der Schalter hat einen eigenen Handler", len(handler) > 1)
    if len(handler) > 1:
        body = handler[1].split("}}")[0]
        check("Abwählen löscht die Bestätigung",
              'if (!value) setWipeConfirm("")' in body,
              f"Handler-Rumpf: {body.strip()[:120]}")

    # Der Wert muss auch wirklich beim Bot ankommen. `rebuild: false`
    # fest verdrahtet war der Zustand vorher.
    check("der Schalter wird mitgeschickt", "rebuild: wipe" in panel,
          "rebuild wird nicht aus dem Schalter gespeist")
    check("die Bestätigung wird mitgeschickt", "confirm:" in panel)

    # Und es steht klar da, was passiert -- vor dem Klick.
    check("die Folgen werden benannt",
          "endgültig" in panel and "Papierkorb" in panel,
          "der Text verharmlost, was das Löschen anrichtet")
    check("der Knopf sagt, dass er löscht",
          "Alles löschen und neu bauen" in panel,
          "der Knopf muss beschriften, was er tut")


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
    test_one_failed_call_does_not_blank_the_others()
    test_the_server_says_why_it_cannot_reach_the_template_bot()
    test_the_wipe_switch_is_hard_to_hit_by_accident()
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
