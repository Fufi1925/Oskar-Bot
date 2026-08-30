#!/usr/bin/env python3
"""
Louckup — der abgetrennte Bereich unter <url>/louckup.

Der Bereich ist gemountet, nicht eingebunden. Genau daran kann leise
viel kaputtgehen, und genau das prueft diese Datei:

  * Das Paket heisst `louckup_app`. Phantom traegt sein Verzeichnis in
    sys.path ein und belegt den Namen `app` bereits — ein zweites Paket
    namens `app` wuerde bedeuten, dass unter /louckup still die
    Phantom-App haengt.
  * Der Mount steht VOR dem Catch-All-Proxy zum Dashboard. Danach wuerde
    jede Anfrage an /louckup von Next.js beantwortet und kaeme nie an.
  * Ein Fehler beim Mounten darf den Bot-Start nicht verhindern.
  * Container und Startskript muessen den Bereich mitnehmen, sonst ist
    er im Code da und in Produktion nicht.
  * Kein Import aus phantom/, bot/ oder dashboard/ — die Isolation ist
    der ganze Zweck der Uebung.

Run:  python3 tests/test_louckup_mount.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
LOUCKUP = os.path.join(ROOT, "louckup")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def test_files_exist():
    print("\nDateien")
    expected = [
        "louckup_app/__init__.py",
        "louckup_app/config.py",
        "louckup_app/auth.py",
        "louckup_app/db.py",
        "louckup_app/main.py",
        "louckup_app/templates/base.html",
        "louckup_app/templates/login.html",
        "louckup_app/templates/dashboard.html",
        "louckup_app/static/css/louckup.css",
        "requirements.txt",
        ".env.example",
        "README.md",
        "tests/test_louckup_flow.py",
    ]
    for rel in expected:
        check(rel, os.path.isfile(os.path.join(LOUCKUP, rel)))

    # Der allgemeine Paketname wuerde mit Phantom kollidieren.
    check(
        "kein Paket namens app/ (Kollision mit Phantom)",
        not os.path.isdir(os.path.join(LOUCKUP, "app")),
    )


def test_mount_in_server():
    print("\nMount in bot/api/server.py")
    src = read(os.path.join(BOT, "api", "server.py"))
    check("Datei gelesen", bool(src))

    check('Mount auf "/louckup"', 'app.mount("/louckup"' in src)
    check(
        "nutzt louckup_app.main (nicht app.main)",
        "from louckup_app.main import create_app as create_louckup_app" in src,
    )
    check(
        "kein Import von app.main als Louckup",
        not re.search(r"from app\.main import create_app as create_louckup", src),
    )

    mount_at = src.find('app.mount("/louckup"')
    proxy_at = src.find('@app.api_route("/{path:path}"')
    check("Mount vor dem Dashboard-Catch-All", -1 < mount_at < proxy_at, f"{mount_at} / {proxy_at}")

    # Ein fehlgeschlagener Mount darf den Bot nicht mit in den Abgrund reissen.
    block = src[src.find("# Louckup") : src.find('@app.api_route("/{path:path}"')]
    check("Mount in try/except", "try:" in block and "except Exception" in block)
    check("Fehler wird geloggt", "logger.error" in block)


def test_deployment_wiring():
    print("\nDeployment")
    docker = read(os.path.join(ROOT, "Dockerfile"))
    check("Dockerfile kopiert louckup/", "COPY louckup/" in docker)
    check(
        "Dockerfile installiert louckup-requirements",
        "pip install --no-cache-dir -r ./louckup/requirements.txt" in docker,
    )

    start = read(os.path.join(ROOT, "start.sh"))
    check("start.sh setzt LOUCKUP_BASE_URL", "LOUCKUP_BASE_URL" in start)
    check(
        "start.sh leitet sie aus RAILWAY_PUBLIC_DOMAIN ab",
        'LOUCKUP_BASE_URL="https://$RAILWAY_PUBLIC_DOMAIN/louckup"' in start,
    )
    check("start.sh setzt Cookie-Pfad", 'LOUCKUP_COOKIE_PATH="${LOUCKUP_COOKIE_PATH:-/louckup}"' in start)
    check(
        "start.sh legt die DB ins Volume",
        '$DATA_DIR/louckup' in start and "LOUCKUP_DB_PATH" in start,
    )
    check(
        "start.sh faellt auf OWNER_IDS zurueck",
        'export LOUCKUP_OWNER_IDS="$OWNER_IDS"' in start,
    )

    env = read(os.path.join(ROOT, ".env.example"))
    for var in (
        "LOUCKUP_BASE_URL",
        "LOUCKUP_SECRET_KEY",
        "LOUCKUP_DISCORD_CLIENT_ID",
        "LOUCKUP_DISCORD_CLIENT_SECRET",
        "LOUCKUP_OWNER_IDS",
        "LOUCKUP_FALLBACK_URL",
    ):
        check(f".env.example dokumentiert {var}", var in env)


def test_isolation():
    print("\nIsolation")
    app_dir = os.path.join(LOUCKUP, "louckup_app")
    sources = [
        os.path.join(app_dir, name)
        for name in sorted(os.listdir(app_dir))
        if name.endswith(".py")
    ]
    check("Python-Dateien gefunden", len(sources) >= 4, str(len(sources)))

    bad = []
    for path in sources:
        text = read(path)
        for forbidden in ("from phantom", "import phantom", "from bot.", "import bot.", "from dashboard"):
            if forbidden in text:
                bad.append(f"{os.path.basename(path)}: {forbidden}")
    check("kein Import aus phantom/bot/dashboard", not bad, "; ".join(bad))

    # Alle Konfiguration ueber LOUCKUP_*, nichts aus utils.config des Bots.
    config = read(os.path.join(app_dir, "config.py"))
    check("eigene Settings-Klasse", "class Settings(BaseSettings)" in config)
    check("liest louckup/.env", '"utf-8"' in config and "ROOT / \".env\"" in config)


def test_trailing_slash():
    print("\nNackte Adresse ohne Slash")
    # Seit Starlette 1.x passt ein Mount nur noch auf "<pfad>/". Ohne
    # eigene Route faellt "/louckup" bis zum Catch-All-Proxy durch, und
    # der Browser bekommt die 404-Seite von Next.js — waehrend
    # "/louckup/healthz" ganz normal funktioniert. Genau so war es.
    src = read(os.path.join(BOT, "api", "server.py"))

    check('Route fuer "/louckup"', '@app.get("/louckup", include_in_schema=False)' in src)
    check('Route fuer "/phantom"', '@app.get("/phantom", include_in_schema=False)' in src)
    check(
        "leitet auf die Slash-Variante",
        'RedirectResponse(url="/louckup/"' in src and 'RedirectResponse(url="/phantom/"' in src,
    )
    check("RedirectResponse importiert", "RedirectResponse" in src.splitlines()[8] or "from starlette.responses import Response, RedirectResponse" in src)

    route_at = src.find('@app.get("/louckup", include_in_schema=False)')
    proxy_at = src.find('@app.api_route("/{path:path}"')
    check("Route vor dem Catch-All-Proxy", -1 < route_at < proxy_at, f"{route_at} / {proxy_at}")


def test_owner_gate():
    print("\nOwner-Pruefung")
    main_src = read(os.path.join(LOUCKUP, "louckup_app", "main.py"))
    auth_src = read(os.path.join(LOUCKUP, "louckup_app", "auth.py"))

    check("Callback prueft owner_ids", "user_id in settings.owner_ids" in main_src)
    check(
        "Dashboard prueft owner_ids erneut",
        main_src.count("not in settings.owner_ids") >= 1,
    )
    check(
        "Nicht-Owner bekommt kein Session-Cookie",
        "if not is_owner:" in main_src and "clear_session(resp)" in main_src,
    )
    check(
        "Weiterleitung aufs normale Dashboard",
        "settings.louckup_fallback_url" in main_src,
    )
    check("Loginversuche werden protokolliert", "record_attempt" in main_src)

    for scope in ("identify", "email", "guilds", "guilds.join", "gdm.join"):
        check(f"Scope {scope} voreingestellt", scope in auth_src)

    check(
        "eigener Session-Salt",
        'salt="louckup-session-v1"' in auth_src or "SESSION_SALT" in auth_src,
    )


def test_routes():
    print("\nRouten")
    src = read(os.path.join(LOUCKUP, "louckup_app", "main.py"))
    for route in ('"/"', '"/login"', '"/auth/discord"', '"/auth/callback"', '"/dashboard"', '"/logout"', '"/healthz"'):
        check(f"Route {route}", f'@app.get({route}' in src)

    check("Redirect von / auf login", 'href("/login")' in src)
    check("OAuth-State wird geprueft", "louckup_oauth_state" in src)


def main():
    test_files_exist()
    test_mount_in_server()
    test_trailing_slash()
    test_deployment_wiring()
    test_isolation()
    test_owner_gate()
    test_routes()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
