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
assert {"ticket-panel", "reaction-panel", "warn", "mute", "kick", "ban", "giveaway", "giveaway-reroll", "announce"} <= commands
assert bot.intents.members and bot.intents.message_content and bot.intents.moderation
print("ok   sieben Module, Components V2, Persistenz und Discord-Befehle")
