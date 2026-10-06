#!/usr/bin/env python3
"""The owner operations dashboard remains support-guild and OWNER_IDS only."""
from pathlib import Path
import asyncio
import sys

ROOT = Path(__file__).resolve().parents[2]
BOT = ROOT / "bot"
sys.path.insert(0, str(BOT))

from fastapi import HTTPException
from api.routes import support_operations as route
from utils import support_operations as ops

ops.OWNER_IDS = [1]
route._guard(ops.MAIN_SUPPORT_GUILD_ID, "1")

# Visibility must not depend on a working operations database or bot metrics.
def unavailable(*args, **kwargs):
    raise AssertionError("access probe loaded operational data")

original = ops.get_setting
ops.get_setting = unavailable
try:
    assert asyncio.run(route.access(ops.MAIN_SUPPORT_GUILD_ID, "1")) == {"allowed": True}
finally:
    ops.get_setting = original
for guild_id, actor, status in ((123, "1", 404), (ops.MAIN_SUPPORT_GUILD_ID, "2", 403), (ops.MAIN_SUPPORT_GUILD_ID, "", 403)):
    try:
        asyncio.run(route.access(guild_id, actor))
        raise AssertionError("guard accepted forbidden access")
    except HTTPException as exc:
        assert exc.status_code == status

server_source = (BOT / "api/server.py").read_text()
assert 'support_operations.router, prefix="/support-operations"' in server_source

names = {item.path for item in route.router.routes}
assert f"/{{guild_id}}/access" in names
assert f"/{{guild_id}}/overview" in names
assert f"/{{guild_id}}/diagnose/{{target_guild_id}}" in names
assert f"/{{guild_id}}/errors/{{error_id}}/ticket" in names
assert f"/{{guild_id}}/support-access/revoke" in names
assert f"/{{guild_id}}/templates/{{template_id}}" in names

layout = (ROOT / "dashboard/app/dashboard/layout.tsx").read_text()
owner_at = layout.index('name: "Owner-Konsole"')
ai_at = layout.index('name: "KI"')
assert owner_at < ai_at
assert "supportOperationsAllowed" in layout
assert "api.getSupportOperationsAccess(currentGuildId)" in layout
assert 'currentGuildId === "1530378233579704370" && sessionUserId && supportOperationsAllowed' in layout
assert '["Übersicht", "Owner-Konsole", "KI", "Einstellungen"]' in layout

bff = (ROOT / "dashboard/app/api/bot/[...path]/route.ts").read_text()
assert 'scope === "support-operations"' in bff
assert "isOwnerId(session.user.id)" in bff
assert "1530378233579704370" in bff
assert 'scope === "firewall"' in bff and "!team?.is_owner" in bff

guild_auth = (ROOT / "dashboard/lib/guild-auth.ts").read_text()
admin_ids = guild_auth[guild_auth.index("export function getAdminIds"):guild_auth.index("export function getConfiguredOwnerIds")]
assert "new Set" in admin_ids and "process.env.ADMIN_IDS" in admin_ids and "process.env.OWNER_IDS" in admin_ids

page = ROOT / "dashboard/app/dashboard/guild/[guildId]/owner-operations/page.tsx"
panel = ROOT / "dashboard/components/dashboard/support-operations-panel.tsx"
assert page.exists() and panel.exists()
body = panel.read_text()
for feature in ("Globale Fehlerzentrale", "Server-Diagnose", "Incident eröffnen", "Feature Flags", "Server-Lookup", "Premium-Historie", "Supportzugriff", "Template-Inspektor"):
    assert feature in body, feature
print("support operations dashboard: all checks passed")
