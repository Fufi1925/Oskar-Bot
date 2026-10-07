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


import pytest


@pytest.fixture(autouse=True)
def isolated_verification(tmp_path, monkeypatch):
    from utils import verify_store
    monkeypatch.setattr(verify_store, "DB_PATH", str(tmp_path / "verify.db"))
    monkeypatch.setattr(guild_modules, "_loaded", False)
    monkeypatch.setattr(guild_modules, "_disabled", set())


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


def test_join_defaults_enable_every_system_without_overwriting_existing_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_modules, "DB_PATH", str(tmp_path / "settings.db"))
    asyncio.run(guild_modules.set_enabled(123, "tickets", False))
    asyncio.run(guild_modules.initialize_guild(123))
    asyncio.run(guild_modules.initialize_guild(456))
    asyncio.run(guild_modules.load())
    assert guild_modules.is_enabled(123, "tickets") is False
    assert all(asyncio.run(guild_modules.get_states(456)).values())
    with sqlite3.connect(guild_modules.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM guild_module_states WHERE guild_id=456 AND enabled=1").fetchone()[0] == len(guild_modules.MODULE_KEYS)


def test_verification_has_one_persistent_activation_and_requires_setup(tmp_path, monkeypatch):
    import aiosqlite
    from utils import verify_store
    monkeypatch.setattr(guild_modules, "DB_PATH", str(tmp_path / "settings.db"))
    async def run():
        await guild_modules.set_enabled(123, "verification", False)
        assert await guild_modules.get_enabled(123, "verification") is False
        with pytest.raises(ValueError, match="Kanal"):
            await guild_modules.set_enabled(123, "verification", True)
        async with aiosqlite.connect(verify_store.DB_PATH) as db:
            await verify_store.save_settings(db, 123, {"verification_channel_id": 1, "verified_role_id": 2})
        await guild_modules.set_enabled(123, "verification", True)
        async with aiosqlite.connect(verify_store.DB_PATH) as db:
            assert (await verify_store.get_settings(db, 123))["enabled"] is True
        assert (await guild_modules.get_states(123))["verification"] is True
        guild_modules._disabled.clear()
        await guild_modules.load()
        assert await guild_modules.get_enabled(123, "verification") is True
    asyncio.run(run())


def test_tool_and_navigation_tabs_have_no_runtime_power_switch():
    for key in ["compose", "speedrun", "templates", "template-upload", "settings", "help", "premium", "owner-operations"]:
        with pytest.raises(ValueError):
            guild_modules.validate_key(key)
