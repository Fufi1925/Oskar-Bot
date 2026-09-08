"""Regression test for six-digit, guild-scoped Premium giveaway codes."""
from __future__ import annotations
import importlib.util
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("premium_codes_store", ROOT / "bot/utils/premium_codes_store.py")
store = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(store)
errors = []

def check(label, value):
    print(("  ok   " if value else "  FAIL ") + label)
    if not value: errors.append(label)

with tempfile.TemporaryDirectory() as tmp:
    store.DB_PATH = os.path.join(tmp, "admin_config.db")
    first = store.create(premium_days=14, max_uses=2, valid_hours=24, created_by="owner")
    code = first["code"]
    check("code has exactly six digits", len(code) == 6 and code.isdigit())
    check("code starts open", store.inspect(code, "100")["ok"])
    one = store.redeem(code, "100", 1000)
    check("first server receives premium", one["ok"] and one["premium_days"] == 14)
    check("same user cannot consume another place", store.redeem(code, "100", 1001).get("error") == "already_used")
    two = store.redeem(code, "200", 2000)
    check("configured number of users can redeem", two["ok"])
    check("usage limit closes the code", store.inspect(code, "300").get("error") == "used_up")
    rows = store.list_codes()
    check("admin sees users below the code", len(rows[0]["redemptions"]) == 2)
    revoked = store.revoke_redemption(rows[0]["redemptions"][0]["id"])
    check("admin can immediately revoke server premium", revoked["ok"])

route = (ROOT / "bot/api/routes/premium.py").read_text()
proxy = (ROOT / "dashboard/app/api/bot/[...path]/route.ts").read_text()
admin = (ROOT / "dashboard/components/dashboard/premium-codes.tsx").read_text()
customer = (ROOT / "dashboard/components/dashboard/premium-panel.tsx").read_text()
check("API verifies server management", "member.guild_permissions.manage_guild" in route)
check("browser cannot forge the actor", "parsed.actor = actorId" in proxy)
check("admin can set uses, premium duration and validity", all(word in admin for word in ("max_uses", "premium_days", "valid_hours")))
check("customer gets a custom server picker", "serverOpen" in customer and "<select" not in customer)
check("customer confirms before redemption", "Bestätigen und einlösen" in customer)

print(f"\n{len(errors)} Fehler")
raise SystemExit(1 if errors else 0)
