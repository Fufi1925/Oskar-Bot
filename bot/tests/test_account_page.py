#!/usr/bin/env python3
"""Contract checks for the real, session-bound /konto page."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
BOT = ROOT / "bot"
failures = []


def check(name, ok):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        failures.append(name)


page = (DASH / "app/konto/page.tsx").read_text(encoding="utf-8")
gate = (DASH / "components/account-login-gate.tsx").read_text(encoding="utf-8")
actions = (DASH / "components/account-actions.tsx").read_text(encoding="utf-8")
proxy = (DASH / "app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")
api = (DASH / "lib/api.ts").read_text(encoding="utf-8")
route = (BOT / "api/routes/bot.py").read_text(encoding="utf-8")
store = (BOT / "utils/leveling_store.py").read_text(encoding="utf-8")
nav = (DASH / "components/site-nav.tsx").read_text(encoding="utf-8")

check("unauthenticated visitors get a login dialog", "<AccountLoginGate />" in page and 'role="dialog"' in gate)
check("login returns through the success screen", "/auth/success?next=%2Fkonto" in gate)
check("Discord identity comes from the session", "getServerSession(authOptions)" in page and "session.user.id" in page)
check("Discord profile and guilds are fetched live", "/api/users/@me" in page and "/api/users/@me/guilds?with_counts=true" in page)
check("premium is loaded from the real premium endpoint", "api.getMyPremium(userId)" in page)
check("leveling totals come from the bot API", "api.getMyAccountStats(userId)" in page and "/bot/account/${userId}" in api)
check("the bot aggregates real leveling rows", "SUM(xp)" in store and "SUM(messages)" in store and "MAX(xp)" in store)
check("the backend exposes the account aggregate", '@router.get("/account/{user_id}"' in route)
check("the proxy binds account data to the session id", 'rest[1] !== session.user.id' in proxy and "Only your own account" in proxy)
check("five useful actions are rendered", actions.count("label:") == 4 and "Abmelden" in actions)
check("the account page is reachable from navigation", 'href="/konto"' in nav and 'label="Mein Konto"' in nav)
check("no reference-site demo statistics remain", "Total wealth" not in page and "Commands used" not in page and "Dragon Pearls" not in page)

print(f"\n{len(failures)} failures")
for failure in failures:
    print(f"  {failure}")
sys.exit(1 if failures else 0)
