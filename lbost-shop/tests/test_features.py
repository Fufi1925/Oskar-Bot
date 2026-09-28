#!/usr/bin/env python3
"""Offline coverage for the complete shop feature runtime."""
import os
import tempfile
from pathlib import Path

path = str(Path(tempfile.gettempdir()) / "lbost-features-test.sqlite3")
for suffix in ("", "-wal", "-shm"):
    Path(path + suffix).unlink(missing_ok=True)
os.environ["LBOST_SHOP_DB_PATH"] = path
os.environ["LBOST_SHOP_SECRET_KEY"] = "test-session-secret"
os.environ["LBOST_SHOP_TOKEN_ENCRYPTION_KEY"] = "test-encryption-secret"

import discord
from lbost_shop_app import db
from lbost_shop_app.config import get_settings
from lbost_shop_app.main import FEATURES
from lbost_shop_bot.client import create_bot, layout

settings = get_settings()
db.init_features(settings)
for feature in FEATURES:
    db.set_feature(123, feature, {"enabled": True, "marker": feature}, 999, settings)
loaded = db.all_features(123, settings)
assert set(loaded) == set(FEATURES)
assert all(loaded[name]["enabled"] for name in FEATURES)

view = layout("Title", "Components V2", buttons=[discord.ui.Button(label="Open", custom_id="test")])
assert isinstance(view, discord.ui.LayoutView)

bot = create_bot()
commands = {command.name for command in bot.tree.get_commands()}
erwartet = {"ticket-panel", "reaction-panel", "warn", "warnings", "clearwarnings", "mute", "kick", "ban",
            "giveaway", "giveaway-reroll", "announce", "log-setup", "log-status", "log-test",
            "log-toggle", "log-ignore", "log-search", "log-export", "log-reset", "log"}
assert erwartet <= commands, f"es fehlen: {sorted(erwartet - commands)}"
assert len(commands - erwartet) == 0, f"unerwartete Befehle: {sorted(commands - erwartet)}"
log_group = bot.tree.get_command("log")
assert [command.name for command in log_group.commands] == [
    "setup", "status", "config", "test", "toggle", "ignore", "search", "export", "reset"
]
assert bot.intents.members and bot.intents.message_content and bot.intents.moderation
from lbost_shop_bot.client import taugliche_teilnehmer  # noqa: E402

# Gewinner können nur Anwesende sein
assert taugliche_teilnehmer([1, 2, 3], {1, 3}) == [1, 3]
assert taugliche_teilnehmer([5, 6], set()) == []
assert taugliche_teilnehmer(None, {1}) == []
assert taugliche_teilnehmer(["7"], {7}) == [7], "IDs kommen als Text an"
# Beide Stellen, die Gewinner ziehen, müssen den Filter benutzen
quelletext = (Path(__file__).resolve().parents[1] / "lbost_shop_bot" / "client.py").read_text()
assert quelletext.count("taugliche_teilnehmer(") == 3, "eine Ziehungsstelle umgeht den Teilnehmerfilter"

print("ok   sieben Module, Components V2, Persistenz und Discord-Befehle")
