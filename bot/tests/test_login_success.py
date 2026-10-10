#!/usr/bin/env python3
"""The OAuth success screen must precede every dashboard popup."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
failures = 0

def check(label, ok):
    global failures
    print(("  ok   " if ok else "  FAIL ") + label)
    failures += not ok

success = (DASH / "app/auth/success/page.tsx").read_text()
gate = (DASH / "components/global-popups.tsx").read_text()
nav = (DASH / "components/site-nav.tsx").read_text()
layout = (DASH / "app/dashboard/layout.tsx").read_text()
apply = (DASH / "app/team/apply/page.tsx").read_text()
dashboard_home = (DASH / "app/dashboard/page.tsx").read_text()
guilds = (DASH / "app/dashboard/guilds/page.tsx").read_text()
navigation = (DASH / "lib/auth-navigation.ts").read_text()
login_panel = (DASH / "app/auth/login/page.tsx").read_text()
login_entry = (DASH / "lib/login-panel.ts").read_text()

check("success page exists", "Login erfolgreich! Deine Seite wird geöffnet" in success)
check("success is visible before redirect", "1800" in success and "router.replace(destination)" in success)
check("external redirect targets are rejected", "loginDestination(requested" in success and 'url.origin !== new URL(base).origin' in navigation and 'startsWith("//")' in navigation)
check("global popups are hidden on success", 'pathname.startsWith("/auth/")' in gate)
check("normal login enters through success", "openLoginPanel" in nav and "loginCallbackUrl(target" in login_panel and "/auth/success?next=" in navigation)
check("expired dashboard login enters through success", "openLoginPanel" in layout and "loginCallbackUrl(target" in login_panel and "/auth/success?next=" in navigation)
check("application login preserves destination", "openLoginPanel" in apply and "destination = window.location.href" in login_entry)
check("dashboard overview links home", 'href="/"' in dashboard_home and "Zur Startseite" in dashboard_home)
check("server overview links home", 'href="/"' in guilds and "Zur Startseite" in guilds)

print(f"\n{failures} failures")
raise SystemExit(1 if failures else 0)
