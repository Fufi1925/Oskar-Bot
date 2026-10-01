import asyncio
import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace


SPEC = importlib.util.spec_from_file_location(
    "guild_modules_under_test",
    Path(__file__).parents[1] / "utils" / "guild_modules.py",
)
assert SPEC and SPEC.loader
guild_modules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guild_modules)


def test_module_states_default_enabled_and_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_modules, "DB_PATH", str(tmp_path / "settings.db"))
    guild_modules._disabled.clear()
    guild_modules._loaded = False

    assert asyncio.run(guild_modules.get_enabled(123, "welcome")) is True
    assert asyncio.run(guild_modules.set_enabled(123, "welcome", False)) is False
    assert guild_modules.is_enabled(123, "welcome") is False

    # Prove this is persistent rather than only a process-local UI switch.
    guild_modules._disabled.clear()
    guild_modules._loaded = False
    asyncio.run(guild_modules.load())
    assert guild_modules.is_enabled(123, "welcome") is False

    states = asyncio.run(guild_modules.get_states(123))
    assert states["welcome"] is False
    assert "overview" not in states
    assert "settings" not in states

    assert asyncio.run(guild_modules.set_enabled(123, "welcome", True)) is True
    assert guild_modules.is_enabled(123, "welcome") is True


def test_unknown_modules_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_modules, "DB_PATH", str(tmp_path / "settings.db"))
    try:
        asyncio.run(guild_modules.set_enabled(1, "not-a-real-tab", False))
    except ValueError:
        pass
    else:
        raise AssertionError("unknown module key was accepted")


def test_old_pull_switch_migrates_to_shared_verification(tmp_path, monkeypatch):
    path = tmp_path / "settings.db"
    monkeypatch.setattr(guild_modules, "DB_PATH", str(path))
    asyncio.run(guild_modules.ensure())
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO guild_module_states (guild_id, module, enabled) VALUES (?, ?, 0)",
            (77, "verification-pull"),
        )
    guild_modules._disabled.clear()
    guild_modules._loaded = False
    asyncio.run(guild_modules.load())
    assert guild_modules.is_enabled(77, "verification") is False


def test_runtime_mapping_and_event_guild_detection():
    async def callback():
        return None

    callback.__module__ = "cogs.events.custom_commands_service"
    assert guild_modules.module_for_callable(callback) == "custom-commands"

    guild = SimpleNamespace(id=999)
    message = SimpleNamespace(guild=guild)
    assert guild_modules.guild_id_from_event((message,)) == 999
