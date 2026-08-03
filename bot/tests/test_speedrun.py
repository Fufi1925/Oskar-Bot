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

    check("nur community ist frei",
          speedrun.BETA_TEMPLATES == {"community"},
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
    test_premium_failure_is_closed()
    test_template_bot_errors_become_502()
    test_no_token_in_the_answer()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
