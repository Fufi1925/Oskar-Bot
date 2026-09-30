#!/usr/bin/env python3
"""University reaction-role parity: dashboard, persistence and Discord runtime."""
import os
import tempfile
from pathlib import Path

path = str(Path(tempfile.gettempdir()) / "lbost-reaction-roles.sqlite3")
for suffix in ("", "-wal", "-shm"):
    Path(path + suffix).unlink(missing_ok=True)
os.environ["LBOST_SHOP_DB_PATH"] = path
os.environ["LBOST_SHOP_SECRET_KEY"] = "rr-test-secret"
os.environ["LBOST_SHOP_TOKEN_ENCRYPTION_KEY"] = "rr-test-encryption"

from lbost_shop_app import db
from lbost_shop_app.config import get_settings
from lbost_shop_bot.client import create_bot

root = Path(__file__).resolve().parents[1]
template = (root / "lbost_shop_app/templates/reaction_roles.html").read_text(encoding="utf-8")
main = (root / "lbost_shop_app/main.py").read_text(encoding="utf-8")
client = (root / "lbost_shop_bot/client.py").read_text(encoding="utf-8")
commands = (root / "lbost_shop_bot/reaction_roles.py").read_text(encoding="utf-8")
js = (root / "lbost_shop_app/static/dashboard.js").read_text(encoding="utf-8")

assert all(text in template for text in (
    "Rolle per Reaktion", "Mitglied per DM benachrichtigen", "Neue Reaktions-Rolle",
    "Nachrichten-ID", "Server-Emojis", "Alles überprüfen", "Noch keine Reaktions-Rolle eingerichtet",
))
assert "<select" not in template and "data-picker-kind=\"channels\"" in template and "data-picker-kind=\"roles\"" in template
assert "data-rr-emoji-value" in template and "data-rr-add" in template
assert "server_emojis" in template and "/guilds/{guild_id}/emojis" in main
assert "style=" not in template
assert "message.add_reaction" in commands, "Discord command must react before storing"
assert "on_raw_reaction_add" in client and "on_raw_reaction_remove" in client
assert "member.add_roles" in client and "member.remove_roles" in client
assert "member.send(view=layout" in client, "DM must use Components V2"
assert "reaction_roles/verify" in main and "repaired" in main
assert "client.put" in main and "reaktionsrolle_anlegen" in main
assert "data-rr-dm-form" in js and "data-rr-emoji-value" in js

settings = get_settings(); db.init_features(settings)
assert db.reaktionsrollen_dm(123, settings) is True
db.reaktionsrollen_dm_setzen(123, False, settings)
assert db.reaktionsrollen_dm(123, settings) is False
db.reaktionsrolle_anlegen(123, 456, 789, "✅", 111, settings)
row = db.reaktionsrolle(123, 789, "✅", settings)
assert row and row["channel_id"] == 456 and row["role_id"] == 111
assert len(db.reaktionsrollen(123, settings)) == 1
assert db.reaktionsrolle_loeschen(123, 789, "✅", settings)
assert not db.reaktionsrollen(123, settings)

bot = create_bot()
assert bot.tree.get_command("createrr") and bot.tree.get_command("dmrr")
print("ok   Reaktions-Rollen: University-Dashboard, Discord-Reaktionen, Rollen und Reparatur")
