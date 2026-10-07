import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from utils import command_stats, global_stats, honeypot


def test_live_history_preserves_totals_and_counts_distinct_servers(tmp_path):
    async def scenario():
        async with aiosqlite.connect(tmp_path / "honeypot.db") as db:
            await honeypot.ensure_schema(db)
            today = datetime.now(timezone.utc).date()
            await honeypot.save(db, 1, kicks=100, enabled=True)
            for guild_id in (1, 1, 2):
                await honeypot.bump_kicks(db, guild_id)
            # Yesterday and today share a server: count it once for the week.
            yesterday = (today - timedelta(days=1)).isoformat()
            await db.execute("INSERT INTO honeypot_daily VALUES (?,1,4)", (yesterday,))
            since = datetime.now(timezone.utc) - timedelta(days=1)
            await db.execute("UPDATE honeypot_tracking SET started_at=?", (since.timestamp(),))
            await db.commit()
            stats = await honeypot.live_statistics(db, total_servers=7)
            assert stats["total_moderations"] == 103
            assert stats["total_servers"] == 7
            assert stats["moderations_7d"] == 7
            assert stats["triggered_servers_7d"] == 2
            assert len(stats["history"]) == 14
            assert stats["history"][-1] == {"day": today.isoformat(), "moderations": 3, "servers": 2}
            assert stats["history"][-2]["moderations"] == 4
            assert all(point["moderations"] is None for point in stats["history"][:-2])
            assert all("guild_id" not in point for point in stats["history"])
            # Repeated schema checks never reset the collection start date.
            await honeypot.ensure_schema(db)
            assert (await honeypot.live_statistics(db, total_servers=7))["tracking_since"] == stats["tracking_since"]
    asyncio.run(scenario())


def test_daily_write_failure_rolls_back_total_counter(tmp_path, monkeypatch):
    async def scenario():
        async with aiosqlite.connect(tmp_path / "honeypot.db") as db:
            await honeypot.ensure_schema(db)
            await honeypot.save(db, 1, kicks=8)
            original = db.execute
            async def fail_daily(sql, parameters=()):
                if "INSERT INTO honeypot_daily" in sql:
                    raise sqlite3.OperationalError("database or disk is full")
                return await original(sql, parameters)
            monkeypatch.setattr(db, "execute", fail_daily)
            with pytest.raises(sqlite3.OperationalError):
                await honeypot.bump_kicks(db, 1)
            monkeypatch.setattr(db, "execute", original)
            assert (await honeypot.get(db, 1))["kicks"] == 8
            assert (await honeypot.live_statistics(db, total_servers=1))["moderations_7d"] == 0
    asyncio.run(scenario())


def test_global_users_are_complete_deduplicated_and_exclude_foreign_cache(monkeypatch):
    first = SimpleNamespace(member_count=2, members=[SimpleNamespace(id=1)])
    async def chunk(*, cache):
        assert cache
        first.members.append(SimpleNamespace(id=2))
    first.chunk = AsyncMock(side_effect=chunk)
    second = SimpleNamespace(member_count=2, members=[SimpleNamespace(id=2), SimpleNamespace(id=3)])
    bot = SimpleNamespace(guilds=[first, second], users=[SimpleNamespace(id=99)])
    monkeypatch.setattr(command_stats, "total_uses", AsyncMock(return_value=42))
    monkeypatch.setattr(global_stats, "_members_lock", asyncio.Lock())
    result = asyncio.run(global_stats.global_counts(bot))
    assert result == {"global_servers": 2, "global_users": 3, "global_commands": 42}
    first.chunk.assert_awaited_once()


def test_incomplete_members_are_unavailable_instead_of_an_estimated_number(monkeypatch):
    guild = SimpleNamespace(member_count=5, members=[], chunk=AsyncMock())
    monkeypatch.setattr(global_stats, "_members_lock", asyncio.Lock())
    with pytest.raises(RuntimeError, match="incomplete"):
        asyncio.run(global_stats.global_counts(SimpleNamespace(guilds=[guild])))


def test_command_total_includes_buffer_when_flush_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(command_stats, "DB_PATH", str(tmp_path / "commands.db"))
    monkeypatch.setattr(command_stats, "_pending", {( "ping", "1", "2026-10-07"): 7})
    monkeypatch.setattr(command_stats, "_lock", asyncio.Lock())
    monkeypatch.setattr(command_stats, "flush", AsyncMock(return_value=0))
    async def scenario():
        async with aiosqlite.connect(command_stats.DB_PATH) as db:
            await command_stats._ensure_table(db)
            await db.execute("INSERT INTO command_usage VALUES ('help','1','2026-10-06',5,0)")
            await db.commit()
        assert await command_stats.total_uses(strict=True) == 12
    asyncio.run(scenario())
