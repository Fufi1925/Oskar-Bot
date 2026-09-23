#!/usr/bin/env python3
"""Regression checks for the main University Discord OAuth callback."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
auth = (ROOT / "dashboard/lib/auth.ts").read_text()
start = (ROOT / "start.sh").read_text()
proxy = (ROOT / "bot/api/server.py").read_text()
error_page = ROOT / "dashboard/app/auth/error/page.tsx"
failures = []


def check(label, condition):
    print(("ok   " if condition else "FAIL ") + label)
    if not condition:
        failures.append(label)


check("eigene University Client-ID", "UNIVERSITY_DISCORD_CLIENT_ID" in auth)
check("eigener University Client-Secret", "UNIVERSITY_DISCORD_CLIENT_SECRET" in auth)
check("alte Railway-Variablen bleiben kompatibel", "process.env.DISCORD_CLIENT_ID" in auth and "process.env.DISCORD_CLIENT_SECRET" in auth)
check("LBoost-Secrets werden nie als Hauptlogin benutzt", "LBOST_SHOP" not in auth)
check("OAuth Scope bleibt minimal", 'scope: "identify guilds"' in auth)
check("eigene Fehlerseite ist aktiv", 'error: "/auth/error"' in auth and error_page.is_file())
check("Fehlerseite kann OAuth wirklich neu starten", 'signIn("discord"' in error_page.read_text())
check("Produktionslogs enthalten konkrete Callback-Fehler", "[next-auth][${code}]" in auth)
check("NEXTAUTH_URL wird auf Origin normalisiert", "NORMALIZED_NEXTAUTH_URL" in start and "urlsplit" in start)
check("Callback wird beim Start sichtbar ausgegeben", "api/auth/callback/discord" in start)
check("interne NextAuth-URL zeigt direkt auf Next.js", "NEXTAUTH_URL_INTERNAL" in start and "127.0.0.1:$DASHBOARD_PORT" in start)
check("dedizierte Werte reparieren auch alte OAuth-Routen", 'export DISCORD_CLIENT_ID="$UNIVERSITY_DISCORD_CLIENT_ID"' in start and 'export DISCORD_CLIENT_SECRET="$UNIVERSITY_DISCORD_CLIENT_SECRET"' in start)
check("fehlende Haupt-Credentials werden gemeldet", "University Discord OAuth client ID is missing" in start and "University Discord OAuth client secret is missing" in start)
check("vertauschte Shop-Credentials werden erkannt", "University and LBoost use the same Discord Client ID" in start)
check("Proxy setzt oeffentlichen Host", 'headers["x-forwarded-host"]' in proxy)
check("Proxy setzt oeffentliches Protokoll", 'headers["x-forwarded-proto"]' in proxy)
check("Proxy erhaelt mehrere Set-Cookie Header", "resp.headers.raw" in proxy and "response.raw_headers" in proxy)

raise SystemExit(1 if failures else 0)
