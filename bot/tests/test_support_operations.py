#!/usr/bin/env python3
"""Support-server owner console: persistence, dedupe and command exposure."""
import asyncio
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import support_operations as ops


def main():
    ops.DB_PATH = os.path.join(tempfile.mkdtemp(), "support.db")
    ops.ensure()
    ops.set_setting("error_channel_id", "123")
    assert ops.get_setting("error_channel_id") == "123"

    try:
        raise RuntimeError("database exploded")
    except RuntimeError as exc:
        first, created = ops.upsert_error("test:database", exc, guild_id=77, user_id=42)
    assert created and first["count"] == 1 and first["status"] == "new"

    try:
        raise RuntimeError("database exploded")
    except RuntimeError as exc:
        second, created = ops.upsert_error("test:database", exc, guild_id=77, user_id=42)
    assert not created and second["error_id"] == first["error_id"] and second["count"] == 2
    assert ops.set_error_status(first["error_id"], "investigating", 1)["status"] == "investigating"
    assert ops.set_error_status(first["error_id"], "resolved", 1)["status"] == "resolved"
    try:
        raise RuntimeError("database exploded")
    except RuntimeError as exc:
        reopened, created = ops.upsert_error("test:database", exc, guild_id=77, user_id=42)
    assert not created and reopened["count"] == 3 and reopened["status"] == "new"
    view = ops.ErrorActionView(None, first["error_id"])
    assert len(view.children) == 1 and len(view.children[0].children) == 4

    incident = ops.create_incident("API gestört", "critical", "Tests schlagen fehl", 1)
    assert incident["status"] == "open"
    assert ops.update_incident(incident["incident_id"], "monitoring", "Fix läuft", 1)["status"] == "monitoring"
    assert len(ops.list_incidents()) == 1

    path = os.path.join(BOT, "cogs", "commands", "support_owner_console.py")
    spec = importlib.util.spec_from_file_location("support_owner_console_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {command.name for command in module.SupportOwnerConsole.__cog_app_commands__}
    assert names == {
        "global-status", "server-diagnose", "incident", "feature-flag",
        "deployment-status", "server-lookup", "premium-history",
        "error-lookup", "support-access", "template-inspect",
    }
    for command in module.SupportOwnerConsole.__cog_app_commands__:
        assert command._guild_ids == [ops.MAIN_SUPPORT_GUILD_ID], (command.name, command._guild_ids)
    print("support operations: all checks passed")


if __name__ == "__main__":
    main()
