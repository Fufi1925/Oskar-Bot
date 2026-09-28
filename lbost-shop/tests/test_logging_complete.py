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
from lbost_shop_app.main import LOG_CATEGORIES, normalise_logging

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
assert "Schnelle Einrichtung" in template
assert "Ausnahmen und Aufbewahrung" in template
assert "Testeintrag posten" in template
assert "{% for group in groups %}" in template

print("ok   neun Kategorien, vollständige Discord-Events, Components V2 und University-Dashboard")
