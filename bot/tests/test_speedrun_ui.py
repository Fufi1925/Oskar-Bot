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

    # Jede *bedingte* Rückkehr, nicht das Schluss-return.
    #
    # Ein erster Versuch suchte die erste Zeile `    return (` und
    # verglich, was danach kommt. Das traf den Loading-Zweig, der
    # mitten in der Komponente steht -- der Test war rot, obwohl alle
    # Hooks davor lagen. Was zählt, ist die Reihenfolge: kein Hook darf
    # *nach* einem frühen return kommen, denn beim nächsten Rendern
    # würde er übersprungen und React zählt anders durch.
    hook_pattern = r"\b(?:useState|useEffect|useCallback|useRef|useSession)\s*\("
    hooks = [m.start() for m in re.finditer(hook_pattern, body)]
    check("die Komponente ruft Hooks auf", len(hooks) >= 8, str(len(hooks)))

    # Frühe Rückkehr = ein `return` innerhalb eines if-Blocks der
    # Komponente. Genau vier Leerzeichen: der Loading-Zweig steht auf
    # dieser Ebene.
    #
    # Ein Versuch mit `{6,}` traf ihn nicht -- er hat vier -- sondern
    # ein verschachteltes JSX-Return tief in der Ausgabe. Damit stand
    # der Vergleichspunkt hinter allen Hooks und der Test konnte gar
    # nichts mehr finden.
    early_returns = [
        m.start()
        for m in re.finditer(r"\n {4}return \(", body)
        if "if (" in body[max(0, m.start() - 120):m.start()]
    ]
    check("es gibt eine frühe Rückkehr", bool(early_returns),
          "ohne die sagt der Test nichts aus")

    if early_returns and hooks:
        first_early = min(early_returns)
        # Jeder Hook hinter der ersten frühen Rückkehr ist ein Fehler --
        # egal wie eingerückt. Ein Versuch, hier nach Einrückung zu
        # filtern, ließ genau den Fall durch, den der Test finden soll:
        # ein `const [x] = useState()` direkt nach dem Loading-Zweig.
        offenders = []
        for pos in hooks:
            if pos <= first_early:
                continue
            line_start = body.rfind("\n", 0, pos) + 1
            line = body[line_start:body.find("\n", pos)]
            offenders.append(line.strip()[:60])

        check("kein Hook nach der ersten frühen Rückkehr",
              not offenders,
              f"{len(offenders)} dahinter: {offenders[:3]}")


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


def test_the_handover_does_not_hang_on_an_open_tab():
    """
    Der schwerste Fehler dieses Reiters.

    Früher stieß das Panel die zweite Hälfte an: es fragte den
    Fortschritt ab, sah „Bau fertig“ und rief `/finish`. Damit hing die
    halbe Einrichtung am offenen Browser-Tab. Wer während des Baus den
    Tab schloss, das Handy sperrte oder unterwegs das Netz verlor, bekam
    Rollen und Kanäle — aber kein Verify, keine Tickets, keine Logs,
    keine Anti-Nuke, keine Begrüßung. Ohne Meldung. Ein Bau dauert über
    eine Minute; einen Tab so lange offen zu halten ist keine Bedingung,
    die man jemandem stellen kann.

    Jetzt übernimmt der Bot selbst. Geprüft wird beides: dass der
    Browser es *nicht* mehr tut, und dass der Bot es *wirklich* tut.
    """

    print("\nDie Übergabe hängt nicht am offenen Tab")

    import ast

    panel = strip_comments(read(PANEL))

    # 1. Der Browser darf die Einrichtung nicht mehr auslösen.
    check("das Panel ruft /finish nicht mehr auf",
          "api.speedrunFinish" not in panel,
          "damit hinge die zweite Hälfte wieder am offenen Tab")

    # 2. Der Bot muss es stattdessen tun -- über den Syntaxbaum, denn
    #    „das Wort kommt vor“ sagt nichts darüber, ob der Wächter auch
    #    gestartet wird.
    route_src = open(
        os.path.join(BOT, "api", "routes", "speedrun.py"), encoding="utf-8"
    ).read()
    tree = ast.parse(route_src)

    start = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "start"),
        None,
    )
    check("es gibt die Start-Route", start is not None)
    if start is not None:
        check("der Start setzt den Wächter an",
              "_watch_build" in ast.unparse(start),
              "ohne ihn wartet niemand auf das Ende des Baus")

    watcher = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_watch_build"),
        None,
    )
    check("es gibt den Wächter", watcher is not None)
    if watcher is not None:
        body = ast.unparse(watcher)
        check("er wartet in einer Schleife",
              any(isinstance(n, ast.While) for n in ast.walk(watcher)),
              "ohne Schleife fragt er genau einmal und gibt auf")
        check("und übergibt danach", "_begin_handover" in body)
        # Ein Abbruch muss ihn erreichen, sonst richtet er nach dem
        # Klick auf „Abbrechen“ trotzdem noch ein.
        check("ein Abbruch stoppt ihn", "cancelled" in body)

    # 3. Die Schritte müssen beim Start mitgehen -- der Browser wird ja
    #    nicht mehr gefragt. Ohne sie richtete der Bot immer den
    #    Standard ein und die Auswahl im Reiter wäre wirkungslos.
    check("die Auswahl geht beim Start mit", "steps: options" in panel,
          "sonst ignoriert der Bot, was im Umfang abgewählt wurde")

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


def test_the_poll_cannot_overlap_itself():
    """Der Bug, der doppelte Zeilen erzeugte.

    Mit `setInterval` startet die nächste Abfrage, egal ob die vorige
    fertig ist. Dauert eine Antwort länger als der Takt, liest die
    zweite denselben Zähler wie die erste und holt dieselben Zeilen noch
    einmal. Nachgestellt: 2,5s Antwort bei 1,5s Takt ergab 10 Zeilen
    statt 5, jede doppelt.
    """

    print("\nDie Abfragen überholen sich nicht")

    panel = strip_comments(read(PANEL))

    # Kein setInterval *in der Abfrageschleife*. Anderswo ist er
    # harmlos: die Laufzeit-Uhr tickt einmal pro Sekunde und ruft
    # nichts ab. Deshalb wird hier der Effekt der Schleife angesehen,
    # nicht die ganze Datei -- ein pauschales Verbot hätte die Uhr
    # verboten und mit dem Fehler nichts zu tun gehabt.
    poll_effect = panel.split("if (!isRunning) return;")[1].split("}, [")[0]
    check("die Abfrageschleife nutzt kein setInterval",
          "setInterval" not in poll_effect,
          "setInterval startet die nächste Abfrage ungefragt")
    check("es wird neu geplant statt getaktet", "setTimeout(tick" in panel)
    check("eine laufende Abfrage sperrt", "pollingRef" in panel)

    # Der Riegel muss *abgefragt* werden, nicht nur vorkommen.
    #
    # Ein erster Versuch suchte "pollingRef.current" im Rumpf. Das
    # blieb auch nach dem Entfernen der Abfrage grün, weil das Lösen im
    # finally-Zweig dieselbe Zeichenfolge enthält. Also gezielt nach
    # der Abfrage und nach dem Setzen suchen.
    tick = panel.split("const tick = async ()")[1].split("};")[0]
    check("der Riegel wird abgefragt",
          "|| pollingRef.current) return" in tick,
          "ohne die Abfrage überholen sich die Aufrufe weiterhin")
    check("er wird gesetzt", "pollingRef.current = true" in tick)
    check("und wieder gelöst", "pollingRef.current = false" in tick)

    # Die Zähler direkt nach dem Lesen setzen, nicht später: die
    # nächste Abfrage muss den neuen Stand sehen.
    apply = panel.split("const applyStatus")[1].split("const tick")[0]
    check("die Zähler werden im selben Durchlauf gesetzt",
          "sinceRef.current =" in apply and "sinceMainRef.current =" in apply)


def test_a_reload_finds_a_running_build():
    """Nach F5 stand man auf Schritt 1, während im Hintergrund gebaut wurde."""

    print("\nEin Neuladen findet den laufenden Bau")

    panel = strip_comments(read(PANEL))
    load = panel.split("const load = useCallback")[1].split("useEffect")[0]

    check("beim Laden wird der Status abgefragt",
          "api.speedrunStatus" in load,
          "ohne das ist ein laufender Bau unsichtbar")
    check("ein laufender Bau springt zum Terminal",
          "setStage(3)" in load)
    check("die alten Zeilen werden nachgeholt",
          "setLines(past)" in load,
          "sonst beginnt die Ausgabe mitten im Satz")
    check("es wird sichtbar gemacht", "setResumed(true)" in load)

    # Der Zustand zwischen fertigem Bau und begonnener Einrichtung
    # zählt ausdrücklich als „läuft“.
    #
    # Er fehlte hier: „waiting“ war weder running noch done, also galt
    # der Lauf beim Neuladen als beendet. Wer genau in diesem Fenster
    # neu lud -- es dauert bis zu drei Sekunden -- landete wieder auf
    # Schritt 1, während der Bot im Hintergrund einrichtete. Der
    # Startknopf hätte einen zweiten Lauf angestoßen.
    check("ein wartender Lauf gilt als laufend",
          'mainState === "waiting"' in load,
          "sonst ist die Übergabe im Moment des Neuladens unsichtbar")


def test_the_handover_is_tied_to_this_run():
    """Ein alter Bau darf die Einrichtung nicht erneut auslösen.

    Ein fertiger Job bleibt beim Template-Bot 15 Minuten abrufbar. Die
    Bedingung war nur "fertig und noch nicht übergeben" -- das erfüllt
    auch ein Bau von vorhin.
    """

    print("\nDie Übergabe gehört zu genau diesem Lauf")

    panel = strip_comments(read(PANEL))
    api_src = strip_comments(read(API))

    check("das Panel merkt sich die Lauf-Kennung", "runIdRef" in panel)
    check("sie wird beim Start übernommen",
          "runIdRef.current = answer?.run_id" in panel)
    check("die API reicht sie durch", "run_id: runId" in api_src)

    # Seit der Bot die Übergabe selbst anstößt, muss *er* prüfen, ob
    # der fertige Bau noch zu seinem Lauf gehört. Der Browser kann das
    # nicht mehr tun -- er ist beim Abschluss womöglich gar nicht offen.
    import ast

    route_src = open(
        os.path.join(BOT, "api", "routes", "speedrun.py"), encoding="utf-8"
    ).read()
    watcher = next(
        (n for n in ast.walk(ast.parse(route_src))
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_watch_build"),
        None,
    )
    check("der Wächter kennt die Lauf-Kennung", watcher is not None)
    if watcher is not None:
        body = ast.unparse(watcher)
        check("er vergleicht sie mit dem laufenden Bau",
              "actual_run != run_id" in body or "run_id != actual_run" in body,
              "sonst richtet er nach einem fremden Bau ein")

    # Und der Bot prüft sie -- eine Sperre nur im Browser ist keine.
    route = strip_comments(
        open(os.path.join(BOT, "api", "routes", "speedrun.py"),
             encoding="utf-8").read().replace("# ", "")
    )
    check("der Bot vergleicht die Kennung",
          'wanted_run != actual_run' in route,
          "sonst liegt die Sperre allein im Browser")


def test_the_timer_does_not_restart_on_every_toggle():
    """poll hing an `options` -- jeder Klick setzte den Timer neu auf."""

    print("\nEin Schalter setzt den Timer nicht zurück")

    panel = strip_comments(read(PANEL))

    check("die Optionen liegen in einem Ref", "optionsRef" in panel)
    check("die Schleife liest das Ref",
          "optionsRef.current" in panel)

    # Der Effekt darf nicht von `options` abhängen.
    effect = panel.split("if (!isRunning) return;")[1].split("}, [")[1].split("]")[0]
    check("options steht nicht in den Abhängigkeiten",
          "options" not in effect,
          f"Abhängigkeiten: [{effect}]")


def test_partial_is_not_shown_as_done():
    """Ein Lauf mit Lücken darf nicht wie ein sauberer aussehen."""

    print("\n„Teilweise fertig“ wird als solches gezeigt")

    panel = strip_comments(read(PANEL))

    check("die Phase kennt partial", '"partial"' in panel)
    check("sie wird gesetzt", 'setPhase("partial")' in panel)
    check("und angezeigt", "Fertig, mit Lücken" in panel)
    check("mit einer Erklärung",
          "Einzelne Schritte sind nicht durchgelaufen" in panel,
          "sonst rätselt man, was fehlt")


def test_a_stuck_build_can_be_cancelled():
    """Ohne Abbrechen hängt der Reiter für immer auf „läuft“."""

    print("\nEin hängender Bau lässt sich abbrechen")

    panel = strip_comments(read(PANEL))
    api_src = strip_comments(read(API))

    check("es gibt einen Abbrechen-Knopf", "Abbrechen" in panel)
    check("er ruft die API", "api.speedrunCancel" in panel)
    check("die API kennt den Weg", "speedrunCancel:" in api_src)

    # Und er sagt vorher, was passiert: der Server bleibt halb gebaut.
    check("die Folge wird genannt",
          "bleibt so stehen" in panel,
          "ein Abbruch räumt nichts auf -- das muss dastehen")

    from api.routes import speedrun as route_module

    paths = {r.path for r in route_module.router.routes}
    check("der Bot hat die Route", "/{guild_id}/cancel" in paths, str(sorted(paths)))


def test_motion_respects_the_system_setting():
    """Wer Bewegung abgestellt hat, darf keine bekommen."""

    print("\nAnimationen achten auf prefers-reduced-motion")

    panel = read(PANEL)

    check("es gibt Animationen", "@keyframes sr-" in panel)
    check("prefers-reduced-motion wird beachtet",
          "prefers-reduced-motion: reduce" in panel,
          "für manche ist Bewegung nicht Geschmack, sondern Übelkeit")

    # Und die Abschaltung muss alle Animationen treffen, nicht eine.
    block = panel.split("prefers-reduced-motion: reduce")[1].split("}\n      }")[0]
    for name in ("sr-rise", "sr-sheen", "sr-caret", "sr-pulse"):
        check(f"{name} wird abgeschaltet", name in block, block[:150])


def test_the_sidebar_row_stands_out():
    """Der Speedrun baut einen ganzen Server -- er darf nicht aussehen
    wie „Nickname“ drei Zeilen darüber.

    Premium ist bernstein und pulst, Admin ist indigo mit Kachel. Dieser
    hier nimmt cyan und das, was keiner der beiden hat: ein Licht, das
    über die Oberkante läuft.
    """

    print("\nDie Sidebar-Zeile hebt sich ab")

    css = read("app/globals.css")
    layout = strip_comments(read("app/dashboard/layout.tsx"))

    check("es gibt einen eigenen Stil", ".speedrun-link {" in css)
    check("mit eigenem Symbol-Feld", ".speedrun-badge {" in css)
    # Der Keyframe muss existieren *und* benutzt werden. Nur nach dem
    # Namen zu suchen hat eine Mutation durchgelassen, die ihn
    # umbenannte: die Regel stand noch da, die animation-Zeile zeigte
    # ins Leere, und der Streif war weg.
    check("es gibt einen Keyframe", "@keyframes speedrun-sweep" in css)
    before_block = css.split(".speedrun-link::before {")
    check("es gibt eine Streif-Regel", len(before_block) > 1)
    if len(before_block) > 1:
        rule = before_block[1].split("}")[0]
        check("der Streif ist animiert",
              "animation: speedrun-sweep " in rule,
              f"animation-Zeile: {rule.strip()[:100]}")

        # Und der Name muss auf einen Keyframe zeigen, den es gibt.
        import re as _re

        used = _re.search(r"animation:\s*([\w-]+)", rule)
        if used:
            name = used.group(1)
            check("der Keyframe existiert wirklich",
                  f"@keyframes {name} " in css or f"@keyframes {name}{{" in css,
                  f"animation: {name} zeigt ins Leere")

    # Die Farbe muss sich von den beiden anderen unterscheiden -- sonst
    # ist die Hervorhebung keine.
    check("die Farbe ist nicht die von Premium",
          "rgba(34, 211, 238" in css and "amber" not in css.split(".speedrun-link {")[1][:400])
    check("und nicht die von Admin",
          "99, 102, 241" not in css.split(".speedrun-link {")[1][:400])

    # Und das Ganze muss auch verdrahtet sein, nicht nur im CSS stehen.
    check("die Sidebar erkennt die Zeile", "isSpeedrun" in layout)
    check("sie vergibt die Klasse", '"speedrun-link"' in layout)
    check("und das Symbol-Feld", "speedrun-badge" in layout)

    # Der Stil muss in dem Zweig stehen, der die Zeile wirklich
    # rendert.
    #
    # Hier lag ein Fehler, den dieser Test nicht gesehen hat: die
    # Sidebar hat zwei Renderpfade -- einen für Einträge der obersten
    # Ebene (Premium, Admin) und einen für Untereinträge einer Gruppe.
    # „Speedrun (Beta)“ steht in der Gruppe „Verwaltung“, läuft also
    # durch den zweiten. Der Stil stand nur im ersten. Im Dashboard sah
    # die Zeile deshalb aus wie jede andere, während dieser Test grün
    # blieb: „isSpeedrun kommt in der Datei vor“ sagt nichts darüber,
    # ob es an der Stelle steht, die zählt.
    in_group = bool(
        re.search(r'name:\s*"Verwaltung",\s*items:\s*\[[^\]]*speedrun',
                  layout, re.S)
    )
    check("der Reiter steht in einer Gruppe", in_group,
          "wenn er auf die oberste Ebene wandert, muss dieser Test angepasst "
          "werden -- dann greift der andere Zweig")

    if in_group and "item.items.map((subItem: any) =>" in layout:
        branch = layout.split("item.items.map((subItem: any) =>")[1]
        # Der Zweig endet, wo die Gruppe geschlossen wird.
        branch = branch.split("})}")[0]
        check("der Gruppen-Zweig kennt den Speedrun",
              "isSpeedrun" in branch,
              "der Stil steht im falschen Zweig und wird nie vergeben")

        # Und er muss ihn am Pfad erkennen, nicht an einer Konstanten.
        #
        # `const isSpeedrun = false` ließe alle Prüfungen oben grün:
        # die Wörter stehen weiter da, die Zeile bekommt trotzdem nie
        # einen eigenen Stil. Ein Mutationstest hat genau das
        # durchgelassen.
        # Seit dem Support-Warteraum teilen sich zwei Beta-Reiter
        # denselben Stil, und die Erkennung läuft über eine Liste:
        #
        #     ["/speedrun", "/supportqueue"].some((p) => href.endsWith(p))
        #
        # Geprüft wird deshalb beides -- die alte direkte Form und die
        # Liste. Was die Prüfung weiterhin ausschließt, ist der Fall,
        # der sie ursprünglich nötig machte: eine feste Konstante
        # (`const isSpeedrun = false`), die alle Wortsuchen grün lässt
        # und trotzdem nie einen Stil vergibt.
        by_path = (
            'subItem.href.endsWith("/speedrun")' in branch
            or (
                '"/speedrun"' in branch
                and "subItem.href.endsWith(path)" in branch
            )
        )
        check("er erkennt ihn am Pfad",
              by_path,
              "die Erkennung hängt an einer Konstanten statt am Link")
        check("er vergibt dort die Klasse",
              "speedrun-link" in branch,
              "die Zeile bekommt im Dashboard keine eigene Gestaltung")
        check("und dort das Symbol-Feld",
              "speedrun-badge" in branch)
        check("und das BETA-Zeichen",
              "speedrun-beta" in branch)

    # Wer Bewegung abgestellt hat, bekommt keine.
    reduced = css.split("prefers-reduced-motion: reduce")
    check("der Streif achtet auf prefers-reduced-motion",
          any(".speedrun-link::before" in block for block in reduced[1:]),
          "eine stehende helle Linie sieht nach Darstellungsfehler aus")


def test_the_console_does_not_fight_the_reader():
    """Automatisches Mitrollen darf nicht die Zeile wegreißen, die man liest."""

    print("\nDas Terminal rollt nur mit, wenn man unten steht")

    panel = strip_comments(read(PANEL))
    check("es gibt eine Haftung am unteren Rand", "stickRef" in panel)
    check("gescrollt wird nur mit ihr", "if (box && stickRef.current)" in panel)
    check("Scrollen setzt sie zurück", "onScroll" in panel)


def test_the_locked_tab_shows_nothing_but_the_code_field():
    """
    Ein gesperrter Reiter darf nicht bedienbar sein.

    Die eigentliche Sperre sitzt im Bot -- ein Overlay im Browser hält
    niemanden auf, der curl bedienen kann. Trotzdem muss die Anzeige
    stimmen: wer nicht freigeschaltet ist, soll das Eingabefeld sehen
    und sonst nichts, nicht einen voll bedienbaren Reiter, dessen
    Knöpfe alle in 403 laufen.
    """

    print("\nOhne Code zeigt der Reiter nur das Eingabefeld")

    panel = strip_comments(read(PANEL))

    check("der Reiter fragt den Zustand ab", "api.speedrunAccess" in panel)
    check("es gibt ein Eingabefeld", "api.speedrunUnlock" in panel)

    # Die frühe Rückgabe muss an den Zustand gebunden sein. Nur zu
    # prüfen, dass das Wort vorkommt, wäre wertlos: ein `if (false)`
    # ließe die Zeile stehen und den Reiter offen. Ein Mutationstest
    # hat genau das durchgelassen.
    check("ein nicht freigeschalteter Server sieht den Reiter nicht",
          "if (!gate.unlocked) {" in panel,
          "die Sperre hängt nicht am Zustand -- der Reiter ist offen")
    check("ein gebannter Server bekommt eine eigene Ansicht",
          "if (gate.banned) {" in panel)

    # Die Reihenfolge zählt: die Sperre muss *vor* dem eigentlichen
    # Reiter greifen, sonst rendert er kurz mit.
    if "if (!gate.unlocked) {" in panel and "stage === 0" in panel:
        check("die Sperre steht vor dem Reiter",
              panel.index("if (!gate.unlocked) {") < panel.index("stage === 0"),
              "der Reiter wird gerendert, bevor die Sperre greift")

    # Und die Daten dürfen erst nach der Freischaltung geholt werden --
    # sonst steht die Seite hinter dem Code-Feld voller 403-Meldungen.
    check("geladen wird erst nach der Freischaltung",
          "gate.unlocked) load()" in panel or "userId && gate.unlocked" in panel,
          "die Aufrufe laufen schon vor der Freischaltung los")

    # Im Zweifel zu. Eine gescheiterte Abfrage darf nichts freischalten.
    catch_block = panel.split("} catch (err: any) {")
    gate_catch = [b for b in catch_block if "setGate({" in b[:200]]
    check("eine kaputte Abfrage schaltet nicht frei",
          bool(gate_catch) and "unlocked: false" in gate_catch[0][:300],
          "ein Aussetzer reicht, um an der Sperre vorbeizukommen")


def test_the_switches_follow_the_chosen_template():
    """
    Kein Schalter für etwas, das die Vorlage nicht baut.

    Vorher holte der Reiter die Schritt-Liste einmal beim Öffnen und
    ließ sie dann stehen -- mit allen dreizehn auf „an“, egal welche
    Vorlage gewählt war. Bei zwölf von dreizehn standen dadurch
    Schalter für Sachen an, die nie entstehen: „minimal“ hat weder
    Verify noch Tickets noch Rollen-Vergabe. Wer sie anließ, las
    hinterher im Bericht „Übersprungen“.
    """

    print("\nDie Schalter folgen der gewählten Vorlage")

    panel = strip_comments(read(PANEL))

    # Die Liste muss *mit* der Vorlage geholt werden. Ein Aufruf ohne
    # Argument liefert wieder die starre Liste von früher.
    check("die Schritte werden zur Vorlage geholt",
          "api.speedrunSteps(chosen)" in panel,
          "ohne die Vorlage kommt die alte, starre Liste zurück")

    # Und erneut, wenn die Vorlage wechselt. Steht `chosen` nicht in
    # den Abhängigkeiten, bleibt die Liste der ersten Wahl stehen.
    if "api.speedrunSteps(chosen)" in panel:
        after = panel.split("api.speedrunSteps(chosen)")[1]
        deps = after.split("}, [")[1].split("]")[0] if "}, [" in after else ""
        check("ein Wechsel der Vorlage lädt sie neu",
              "chosen" in deps,
              f"Abhängigkeiten: [{deps}] — die Liste bleibt sonst stehen")

    # Der Schalter muss wirklich gesperrt werden.
    #
    # Nur zu prüfen, dass „supported“ vorkommt, wäre wertlos: ein
    # `const possible = true` ließe das Wort stehen und den Schalter
    # anklickbar. Also die Herkunft mitlesen.
    check("gesperrt wird anhand der Auskunft",
          "step.supported !== false" in panel,
          "die Sperre hängt nicht an dem, was die Vorlage meldet")
    check("und der Schalter ist dann wirklich aus",
          "disabled={!possible}" in panel,
          "ohne disabled bleibt er anklickbar")
    check("ein gesperrter Schalter gilt als nicht gewählt",
          "checked={possible && Boolean(options[step.key])}" in panel,
          "sonst wird ein unmöglicher Schritt mitgeschickt")
    check("und es steht dabei, warum",
          "legt dafür keinen Kanal an" in panel,
          "ein grauer Schalter ohne Grund ist ein Rätsel")


def test_the_template_bot_reports_what_it_can_build():
    """Ohne diese Auskunft kann der Hauptbot nichts ausgrauen."""

    print("\nDer Template-Bot meldet, was er baut")

    import os as _os

    web_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(BOT)), "University-Template", "web.py"
    )
    if not _os.path.isfile(web_path):
        print("  skip (University-Template liegt nicht daneben)")
        return

    web = open(web_path, encoding="utf-8").read()
    web = re.sub(r"^\s*#.*$", "", web, flags=re.M)

    check("die Vorlagenliste enthält die Auskunft",
          '"capabilities": template.capabilities' in web,
          "der Hauptbot erfährt nie, was die Vorlage kann")


def test_only_admins_reach_the_access_management():
    """
    Die Verwaltung zeigt jeden Server -- das ist nichts für Moderatoren.

    Sie listet Namen, Mitgliederzahlen und wer wann freigeschaltet hat,
    und sie kann jedem Server den Zugang nehmen. Ein Server-Moderator
    hat dort nichts zu suchen, auch nicht für den eigenen Server.
    """

    print("\nAn die Zugangsverwaltung kommen nur Admins")

    proxy = strip_comments(read(PROXY))

    block = proxy.split('scope === "speedrun"')[1].split('scope === "extras"')[0]

    check("es gibt eine Regel für die Verwaltung",
          'first === "admin"' in block,
          "die Admin-Routen laufen in die normale guild_id-Prüfung")

    # Nur den *Zweig* ansehen, nicht den Rest des Blocks.
    #
    # Ein erster Versuch suchte "isGlobalAdmin" in den 400 Zeichen nach
    # `first === "admin"`. Das blieb grün, als die Prüfung ersatzlos
    # entfiel: weiter unten steht für den normalen Server-Fall noch ein
    # `isGlobalAdmin`, und das lag im Fenster. Also den Zweig genau
    # abgrenzen -- von der Bedingung bis zu seiner schließenden Klammer.
    if 'first === "admin"' in block:
        branch = block.split('first === "admin"')[1].split("\n    }")[0]
        check("der Zweig verlangt einen globalen Admin",
              "isGlobalAdmin" in branch,
              "jeder Angemeldete käme an die Verwaltung")
        check("und weist sonst ab",
              "deny(403" in branch,
              "ohne Absage läuft der Aufruf einfach durch")

    # Die Regel muss *vor* der guild_id-Prüfung stehen: "admin" ist
    # keine achtzehnstellige Zahl und würde sonst als fehlende
    # guild_id abgewiesen, bevor sie jemand erreichen kann.
    if 'first === "admin"' in block and "guild_id missing" in block:
        check("die Regel steht vor der ID-Prüfung",
              block.index('first === "admin"') < block.index("guild_id missing"),
              "die Admin-Routen antworten mit 400 statt zu funktionieren")


def main():
    test_the_tab_and_the_page_exist_together()
    test_the_locked_tab_shows_nothing_but_the_code_field()
    test_the_switches_follow_the_chosen_template()
    test_the_template_bot_reports_what_it_can_build()
    test_only_admins_reach_the_access_management()
    test_every_call_has_a_proxy_rule()
    test_the_api_calls_match_the_routes()
    test_hooks_come_before_any_early_return()
    test_no_german_quotes_break_a_string()
    test_the_browser_decides_nothing()
    test_the_handover_does_not_hang_on_an_open_tab()
    test_one_failed_call_does_not_blank_the_others()
    test_the_server_says_why_it_cannot_reach_the_template_bot()
    test_the_wipe_switch_is_hard_to_hit_by_accident()
    test_the_poll_cannot_overlap_itself()
    test_a_reload_finds_a_running_build()
    test_the_handover_is_tied_to_this_run()
    test_the_timer_does_not_restart_on_every_toggle()
    test_partial_is_not_shown_as_done()
    test_a_stuck_build_can_be_cancelled()
    test_motion_respects_the_system_setting()
    test_the_sidebar_row_stands_out()
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
