#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOP = ROOT / "lbost-shop"
failures = []

def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: failures.append(name)

main = (SHOP / "lbost_shop_app/main.py").read_text()
config = (SHOP / "lbost_shop_app/config.py").read_text()
auth = (SHOP / "lbost_shop_app/auth.py").read_text()
landing = (SHOP / "lbost_shop_app/templates/landing.html").read_text()
login = (SHOP / "lbost_shop_app/templates/login.html").read_text()
dash = (SHOP / "lbost_shop_app/templates/dashboard.html").read_text()
success = (SHOP / "lbost_shop_app/templates/success.html").read_text()
server = (ROOT / "bot/api/server.py").read_text()
start = (ROOT / "start.sh").read_text()
docker = (ROOT / "Dockerfile").read_text()

check("separater Ordner", SHOP.is_dir())
check("Einordnung University Bot", "Unterbereich von University Bot" in landing)
check("Login exakt gross geschrieben", '@app.get("/Login"' in main)
check("eigene OAuth Daten", "LBOST_SHOP_DISCORD_CLIENT_ID" in (SHOP / ".env.example").read_text())
check("eigene Session", "lbost_shop_session" in config and "lbost-shop-session-v1" in auth)
check("explizite Freigabeliste", "authorized_ids" in config)
check("Owner ebenfalls erlaubt", "explicit | owners" in config)
check("Pruefung bei Login", "user_id not in settings.allowed_ids" in main)
check("Pruefung bei jedem Dashboardaufruf", "current_user(request)" in main)
check("Erfolgsmeldung vor Dashboard", "Anmeldung erfolgreich" in success and 'response.headers["Refresh"]' in main)
check("Fremde zur University-Startseite", "settings.fallback_url or \"/\"" in main)
check("kein Cookie fuer Fremde", "clear_session(response)" in main)
check("Dashboard Platzhalter", "Hier ist das Dashboard" in dash and "Weitere" in dash)
check("Mount vor Catch-all", 'app.mount("/lbost-shop"' in server and server.find('app.mount("/lbost-shop"') < server.find('async def proxy_to_dashboard'))
check("Docker kopiert Bereich", "COPY lbost-shop/ ./lbost-shop/" in docker)
check("Start setzt Base URL", "LBOST_SHOP_BASE_URL" in start)

raise SystemExit(1 if failures else 0)
