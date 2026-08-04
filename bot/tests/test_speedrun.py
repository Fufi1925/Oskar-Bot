#!/usr/bin/env python3
"""
Der Speedrun-Weg im University Bot.

Das Dashboard redet nur mit diesem Bot, nie direkt mit dem
Template-Bot. Zwei Gruende, und beide sind hier festgenagelt:

  * Der Partner-Token darf den Browser nie erreichen. Ein Dashboard,
    das den Template-Bot selbst aufruft, muesste ihn entweder
    mitschicken oder eine zweite Proxy-Schicht bauen -- diese Route
    *ist* die zweite Schicht.
  * In der Beta ist nur ``community`` freigegeben. Diese Sperre gehoert
    auf den Server: eine Pruefung, die nur im Browser stattfindet, ist
    keine.

Run:  python3 tests/test_speedrun.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def test_routes_exist():
    print("\nDie Routen sind registriert")
    from api.routes import speedrun

    paths = {r.path for r in speedrun.router.routes}
    for path in ("/templates", "/{guild_id}/precheck",
                 "/{guild_id}/start", "/{guild_id}/status"):
        check(f"{path} gibt es", path in paths, str(sorted(paths)))

    # Und sie haengen wirklich unter /api/v1, nicht nur im Router.
    from fastapi.testclient import TestClient
    from api.server import create_app

    client = TestClient(create_app())
    response = client.get("/api/v1/speedrun/templates")
    check("die Route ist eingehängt", response.status_code != 404,
          f"HTTP {response.status_code} -- 404 hiesse: nicht registriert")


def test_missing_configuration_says_what_is_missing():
    """Ohne die zwei Variablen muss klar sein, welche fehlt."""

    print("\nFehlende Einrichtung")
    from fastapi.testclient import TestClient
    from api.server import create_app

    old_url = os.environ.pop("TEMPLATE_BOT_URL", None)
    old_token = os.environ.pop("PREMIUM_PARTNER_TOKEN", None)
    try:
        client = TestClient(create_app())
        response = client.get("/api/v1/speedrun/templates")
        check("es kommt 503, nicht 500", response.status_code == 503,
              f"HTTP {response.status_code}")

        detail = str(response.json().get("detail", ""))
        check("TEMPLATE_BOT_URL wird benannt", "TEMPLATE_BOT_URL" in detail, detail)
        check("PREMIUM_PARTNER_TOKEN wird benannt",
              "PREMIUM_PARTNER_TOKEN" in detail, detail)
    finally:
        if old_url is not None:
            os.environ["TEMPLATE_BOT_URL"] = old_url
        if old_token is not None:
            os.environ["PREMIUM_PARTNER_TOKEN"] = old_token


def test_beta_gate():
    print("\nDie Beta-Sperre")
    from api.routes import speedrun

    # Vier Vorlagen sind freigegeben. Die uebrigen neun sind gebaut,
    # aber noch nicht auf einem echten Server gelaufen.
    #
    # Fest verdrahtet statt "mindestens eine": eine Vorlage aus
    # Versehen freizugeben ist nicht rueckgaengig zu machen, sobald
    # jemand sie angewendet hat. Wer eine dazunimmt, aendert diese
    # Zeile mit -- und genau dann soll jemand hinsehen.
    check("die Beta-Liste stimmt",
          speedrun.BETA_TEMPLATES == {"community", "music", "dev", "minimal"},
          str(speedrun.BETA_TEMPLATES))

    source = open(
        os.path.join(BOT, "api", "routes", "speedrun.py"), encoding="utf-8"
    ).read()
    # Der Start muss selbst pruefen. Verliesse er sich darauf, dass das
    # Dashboard nur erlaubte Templates anbietet, koennte jeder mit curl
    # ein ungeprueftes Template auf einen fremden Server anwenden -- und
    # das laesst sich nicht rueckgaengig machen.
    start_block = source.split("async def start(")[1].split("async def ")[0]
    check("start prüft die Beta-Liste selbst",
          "BETA_TEMPLATES" in start_block,
          "die Sperre läge allein im Browser")


def test_wipe_needs_the_server_name():
    """
    »Alles löschen« ist der einzige Schritt, der Bestehendes zerstört.

    Ein Häkchen im Browser reicht dafür nicht: wer den Endpunkt mit curl
    aufruft, umgeht jede Rückfrage im Dashboard, und
    ``options.rebuild=true`` ist schnell getippt. Discord hat keinen
    Papierkorb — was hier gelöscht wird, ist weg.

    Also muss der Bot selbst eine Bestätigung verlangen: den Servernamen,
    genau so geschrieben.
    """

    print("\n»Alles löschen« verlangt eine Bestätigung")
    import ast

    path = os.path.join(BOT, "api", "routes", "speedrun.py")
    source = open(path, encoding="utf-8").read()

    tree = ast.parse(source)
    start = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "start"
    )
    block = ast.get_source_segment(source, start) or ""

    # Kommentare raus: eine Erklärung über den Riegel ist nicht der
    # Riegel. Genau diese Verwechslung ist in diesem Projekt mehrfach
    # passiert.
    code = "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )

    check("der Start liest options.rebuild", '"rebuild"' in code, code[:200])
    check("und verlangt dann eine Bestätigung", '"confirm"' in code)
    check("die mit dem Servernamen verglichen wird",
          "guild.name" in code,
          "ohne Vergleich wäre jede Eingabe gültig")

    # Ab hier über den Syntaxbaum statt über Textsuche. Zwei Mutationen
    # sind vorher durchgerutscht, weil "das Wort kommt vor" nichts über
    # die Wirkung sagt: `if confirm != guild.name` durch `if False`
    # ersetzt, und die Bedingung stand immer noch im Quelltext.
    start_tree = ast.parse(code.strip())
    func = start_tree.body[0]

    # Den Zweig finden, der an options["rebuild"] hängt.
    rebuild_branch = None
    for node in ast.walk(func):
        if isinstance(node, ast.If) and "rebuild" in ast.unparse(node.test):
            rebuild_branch = node
            break
    check("es gibt einen Zweig für den Lösch-Schalter", rebuild_branch is not None)
    if rebuild_branch is None:
        return

    # Er darf nicht konstant sein: `if False:` ist keine Sperre, und
    # `if True:` würde jeden normalen Aufbau blockieren.
    check("der Zweig hängt wirklich an den Optionen",
          not isinstance(rebuild_branch.test, ast.Constant),
          f"Bedingung ist konstant: {ast.unparse(rebuild_branch.test)}")

    # Innerhalb: eine Prüfung, die den Servernamen vergleicht UND
    # abbricht. Beides am selben if, sonst hängt das raise woanders.
    def raises(node) -> bool:
        return any(isinstance(inner, ast.Raise) for inner in ast.walk(node))

    inner_ifs = [n for n in ast.walk(rebuild_branch) if isinstance(n, ast.If)]

    name_checks = [
        n for n in inner_ifs
        if "guild.name" in ast.unparse(n.test)
        and not isinstance(n.test, ast.Constant)
        and raises(n)
    ]
    check("ein falscher Name bricht ab", bool(name_checks),
          "der Namensvergleich ist konstant oder ohne raise — "
          "damit käme jede Eingabe durch")

    perm_checks = [
        n for n in inner_ifs
        if "manage_channels" in ast.unparse(n.test)
        and not isinstance(n.test, ast.Constant)
        and raises(n)
    ]
    check("fehlende Löschrechte brechen ab", bool(perm_checks),
          "sonst bleibt der halbe Server stehen")

    # Und die Optionen müssen wirklich aus der Anfrage kommen. Ein
    # `options = {}` wäre still: rebuild wäre immer aus, das Häkchen
    # im Dashboard hätte keine Wirkung, und niemand bekäme einen Fehler.
    assigns = [
        n for n in ast.walk(func)
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "") == "options" for t in n.targets)
    ]
    check("options werden aus den Daten gelesen",
          any("data" in ast.unparse(n.value) for n in assigns),
          f"options kommt nicht aus data: "
          f"{[ast.unparse(n.value) for n in assigns]}")

    # Und sie werden auch weitergereicht, nicht nur gelesen.
    check("options gehen an den Template-Bot",
          '"options": options' in code,
          "die Auswahl bliebe hier hängen")


def test_premium_failure_is_closed():
    """Eine kaputte Premium-Abfrage darf nichts freischalten."""

    print("\nPremium")
    from api.routes import speedrun
    from utils import premium_store

    original = premium_store.status

    def explode(*_a, **_k):
        raise RuntimeError("Datenbank weg")

    premium_store.status = explode
    try:
        check("Fehler heißt: kein Premium",
              speedrun._has_premium("123") is False)
    finally:
        premium_store.status = original

    check("ohne Nutzer-ID kein Premium", speedrun._has_premium("") is False)


def test_template_bot_errors_become_502():
    """Ein toter Template-Bot darf keinen Traceback erzeugen."""

    print("\nTemplate-Bot nicht erreichbar")
    import asyncio
    from fastapi import HTTPException
    from api.routes import speedrun

    os.environ["TEMPLATE_BOT_URL"] = "http://127.0.0.1:1"
    os.environ["PREMIUM_PARTNER_TOKEN"] = "test-token"
    try:
        try:
            asyncio.run(
                speedrun._call_template("GET", "/internal/speedrun/templates",
                                        timeout=2)
            )
            check("es wird ein Fehler gemeldet", False, "kein Fehler")
        except HTTPException as exc:
            check("es wird ein Fehler gemeldet", True)
            check("und zwar 502", exc.status_code == 502, str(exc.status_code))
            check("mit lesbarem Text",
                  "Template-Bot" in str(exc.detail), str(exc.detail))
        except Exception as exc:
            check("es wird ein Fehler gemeldet", False,
                  f"{type(exc).__name__} statt HTTPException")
    finally:
        os.environ.pop("TEMPLATE_BOT_URL", None)
        os.environ.pop("PREMIUM_PARTNER_TOKEN", None)


def test_no_token_in_the_answer():
    """Der Partner-Token darf in keiner Antwort auftauchen."""

    print("\nDer Token bleibt hier")
    import ast

    path = os.path.join(BOT, "api", "routes", "speedrun.py")
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source)

    # Nur die HTTP-Endpunkte prüfen, nicht die Hilfsfunktionen. Ein
    # erster Versuch teilte den Quelltext an "return " und traf damit
    # _template_base() -- die den Token gar nicht anfasst.
    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorated = any(
            isinstance(d, ast.Call) and "router" in ast.unparse(d.func)
            for d in node.decorator_list
        )
        if decorated:
            endpoints.append(node)

    check("die Endpunkte wurden gefunden", len(endpoints) >= 4,
          f"{len(endpoints)} gefunden")

    leaking = []
    for node in endpoints:
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return) or inner.value is None:
                continue
            text = ast.unparse(inner.value)
            if "_partner_token" in text or "PARTNER_TOKEN" in text:
                leaking.append(f"{node.name}: {text[:60]}")

    check("kein Endpunkt gibt den Token zurück", not leaking, str(leaking))

    # Und er wird genau einmal gesetzt: im Header an den Template-Bot.
    check("der Token geht nur in den Header",
          source.count("X-Partner-Token") == 1,
          "mehr als eine Stelle benutzt ihn")


def main():
    test_routes_exist()
    test_missing_configuration_says_what_is_missing()
    test_beta_gate()
    test_wipe_needs_the_server_name()
    test_premium_failure_is_closed()
    test_template_bot_errors_become_502()
    test_no_token_in_the_answer()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
