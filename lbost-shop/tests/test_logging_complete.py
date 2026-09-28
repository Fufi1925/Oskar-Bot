#!/usr/bin/env python3
"""Regression checks for the University-parity LBoost logging system."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["LBOST_SHOP_DB_PATH"] = str(Path(tempfile.gettempdir()) / "lbost-logging-test.sqlite3")
os.environ["LBOST_SHOP_SECRET_KEY"] = "logging-test-secret"
os.environ["LBOST_SHOP_TOKEN_ENCRYPTION_KEY"] = "logging-test-encryption"

from lbost_shop_app import db
from lbost_shop_app.config import get_settings
from lbost_shop_app.main import LOG_CATEGORIES, _channel_permissions, normalise_logging
from lbost_shop_bot.client import LogDescription, university_log_layout

root = Path(__file__).resolve().parents[1]
client = (root / "lbost_shop_bot" / "client.py").read_text(encoding="utf-8")
template = (root / "lbost_shop_app" / "templates" / "logging.html").read_text(encoding="utf-8")
main = (root / "lbost_shop_app" / "main.py").read_text(encoding="utf-8")

assert len(LOG_CATEGORIES) == 9
assert set(LOG_CATEGORIES) == {
    "message_events", "join_leave_events", "member_moderation", "voice_events",
    "channel_events", "role_events", "emoji_events", "reaction_events", "system_events",
}

legacy = normalise_logging({
    "enabled": True,
    "channel_id": "123456789012345678",
    "member_logs": True,
    "message_logs": True,
    "moderation_logs": True,
    "role_channel_logs": True,
})
assert legacy["enabled"] is True
assert all(legacy["log_channels"].get(key) == "123456789012345678" for key in LOG_CATEGORIES)
assert all(legacy["log_enabled"].values())

# Discord-Ausgabe: derselbe Container-, Trenner- und Feldaufbau wie beim
# CV2EmbedAdapter des University-Logging-Cogs.
log_view = university_log_layout(
    "Message Deleted",
    LogDescription([("Content", "```Text```"), ("Channel", "<#123>")]),
    footer="User ID: 1 • Message ID: 2",
)
assert len(log_view.children) == 1
log_container = log_view.children[0]
assert int(log_container.accent_color) == 0xFF0000
assert [type(item).__name__ for item in log_container.children] == [
    "TextDisplay", "Separator", "TextDisplay", "Separator", "TextDisplay",
    "Separator", "TextDisplay",
]
assert log_container.children[0].content == "**Message Deleted**"
assert log_container.children[-1].content == "*User ID: 1 • Message ID: 2*"

# Das Dashboard muss denselben kaputten Zustand erkennen wie University:
# Kanal vorhanden, aber der Bot darf dort nicht schreiben.
base_permissions = (1 << 10) | (1 << 11) | (1 << 14)
permission_roles = [{"id": "4401", "permissions": str(base_permissions)}]
permission_member = {"user": {"id": "99"}, "roles": []}
denied = _channel_permissions(4401, {
    "permission_overwrites": [{"id": "4401", "type": 0, "allow": "0", "deny": str(1 << 11)}]
}, permission_roles, permission_member)
assert denied is not None and denied & (1 << 10) and not denied & (1 << 11)
allowed = _channel_permissions(4401, {"permission_overwrites": []}, permission_roles, permission_member)
assert allowed is not None and allowed & (1 << 11) and allowed & (1 << 14)

settings = get_settings()
db.init_features(settings)
db.clear_event_logs(123, settings)
db.add_event_log(123, "message_events", "Nachricht gelöscht", "Inhalt", 456, 789, settings)
rows = db.search_event_logs(123, settings, query="gelöscht", limit=10)
assert len(rows) == 1 and rows[0]["category"] == "message_events"
db.clear_event_logs(123, settings)
assert not db.search_event_logs(123, settings)

for listener in (
    "on_message_edit", "on_message_delete", "on_bulk_message_delete",
    "on_member_join", "on_member_remove", "on_member_update", "on_member_ban",
    "on_member_unban", "on_voice_state_update", "on_guild_channel_create",
    "on_guild_channel_delete", "on_guild_channel_update", "on_guild_role_create",
    "on_guild_role_delete", "on_guild_role_update", "on_guild_update",
    "on_guild_emojis_update", "on_thread_create", "on_thread_delete",
    "on_invite_create", "on_invite_delete", "on_raw_reaction_add",
    "on_raw_reaction_remove",
):
    assert f"def {listener}" in client, listener

# Ereigniszuordnung und Inhalt entsprechen dem aktuellen University-Cog.
member_update = client.split("async def on_member_update", 1)[1].split("async def on_member_ban", 1)[0]
assert '"role_events", "Member Roles Updated"' in member_update
assert '"member_moderation", "Nickname Changed"' in member_update
invite_block = client.split("async def on_invite_create", 1)[1].split("async def on_raw_reaction_add", 1)[0]
assert invite_block.count('"system_events"') >= 2
assert "async def _reaction_log" in client and client.count("await self._reaction_log(") == 2
assert "fetch_user(payload.user_id)" in client
for title in (
    "Message Edited", "Message Deleted", "Messages Purged", "Member Joined",
    "Member Left", "Member Banned", "Member Unbanned", "Voice State Changed",
    "Channel Created", "Channel Deleted", "Channel Updated", "Role Created",
    "Role Deleted", "Role Updated", "Server Updated", "Emoji Added", "Emoji Removed",
    "Thread Created", "Thread Deleted", "Invite Created", "Invite Deleted",
    "Reaction Added", "Reaction Removed",
):
    assert title in client, title
assert "def university_log_layout" in client
assert "discord.ui.Container(accent_color=0xFF0000)" in client
assert 'discord.ui.TextDisplay(f"**{title}**")' in client
assert "discord.ui.Separator(visible=True)" in client
assert "not cfg[\"enabled\"]" not in client
assert 'app_commands.Group(name="log"' in client
for subcommand in ("setup", "status", "config", "test", "toggle", "ignore", "search", "export", "reset"):
    assert f'@log_group.command(name="{subcommand}"' in client

for command in (
    "log-setup", "log-status", "log-test", "log-toggle", "log-ignore",
    "log-search", "log-export", "log-reset",
):
    assert f'name="{command}"' in client

assert "discord_event_logs" in (root / "lbost_shop_app" / "db.py").read_text(encoding="utf-8")
assert "add_event_log" in client
assert "discord.ui.LayoutView" in client
assert "auto_delete_duration" in client
assert "ignore_channels" in client and "ignore_roles" in client and "ignore_users" in client
assert "audit_logs" in client
assert "logging/test/{category}" in main
assert "flags\": 32768" in main
assert '"accent_color": 0x5865F2' in main
assert '"content": "## Test"' in main
assert "Diese Nachricht kam aus dem Dashboard." in main
# Das Shop-Panel folgt der aktuellen University-Struktur: Überblick,
# Entwurfs-Presets, einklappbare Gruppen, eigene Picker und Sticky-Save-Bar.
assert "ub-log-stats" in template
assert "Nach Bereich" in template
assert "Eine Voreinstellung setzt alles auf einmal" in template
assert "data-log-preset=\"essential\"" in template
assert "data-log-group-expand" in template
assert "data-log-exceptions-toggle" in template
assert "data-log-save-bar" in template
assert "Testeintrag posten" in template
assert "{% for group in groups %}" in template
for kind in ("channels", "roles", "members"):
    assert f'data-picker-source="{kind}"' in template
assert "data-picker-modal" in template
assert "data-picker-search" in template
assert "<select" not in template
assert "<textarea" not in template
assert "guild_members" in main

script = (root / "lbost_shop_app" / "static" / "dashboard.js").read_text(encoding="utf-8")
style = (root / "lbost_shop_app" / "static" / "css" / "university-dashboard.css").read_text(encoding="utf-8")
for marker in ("data-picker-open", "data-log-group-all", "data-log-dirty-count", "data-log-add-user"):
    assert marker in script
assert "data-can-post" in template and "Der Bot darf dort nicht schreiben" in template
assert "Discord-ID verwenden" in script and "getBoundingClientRect" in script
assert "button.dataset.logPreset === 'everything'" in script and "body.set('action', 'everything')" in script
assert ".ub-picker-modal" in style and ".ub-log-save-bar" in style
assert "@media(max-width:700px)" in style

print("ok   neun Kategorien, vollständige Discord-Events, Components V2 und aktuelles University-Panel")
