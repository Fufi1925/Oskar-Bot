"""Regression coverage for full-volume error recursion and backup pressure."""
import asyncio
import errno
import logging
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import support_operations as ops
from api import config_transfer


@pytest.fixture(autouse=True)
def isolated_reporting(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "DB_PATH", str(tmp_path / "support.db"))
    monkeypatch.setattr(ops, "_report_retry_at", 0.0)
    monkeypatch.setattr(ops, "_report_lock", asyncio.Lock())


async def drain(handler):
    await asyncio.sleep(0)
    if handler._tasks:
        await asyncio.wait_for(asyncio.gather(*handler._tasks), timeout=3)
    await asyncio.sleep(0)


def test_full_database_does_not_recursively_report_and_recovers(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        unhandled = []
        loop.set_exception_handler(lambda loop, context: unhandled.append(context))
        handler = ops.SupportErrorLogHandler(SimpleNamespace(loop=loop))
        root = logging.getLogger()
        root.addHandler(handler)
        persist = ops.upsert_error
        failing = Mock(side_effect=sqlite3.OperationalError("database or disk is full"))
        monkeypatch.setattr(ops, "upsert_error", failing)
        try:
            logging.getLogger("api_request_logs").error("Original API failure")
            await drain(handler)
            assert failing.call_count == 1
            assert not handler._tasks and not unhandled
            for _ in range(100):
                logging.getLogger("api_request_logs").error("Another API failure")
            await drain(handler)
            assert failing.call_count == 1
            # Once storage is healthy and the cooldown expires, persist again.
            monkeypatch.setattr(ops, "upsert_error", persist)
            monkeypatch.setattr(ops, "_report_retry_at", 0.0)
            logging.getLogger("api_request_logs").error("Recovered API failure")
            await drain(handler)
            assert len(ops.list_errors()) == 1
            assert not unhandled
        finally:
            root.removeHandler(handler)
    asyncio.run(scenario())


def test_error_burst_is_bounded_and_internal_logs_are_not_forwarded(monkeypatch):
    async def scenario():
        handler = ops.SupportErrorLogHandler(SimpleNamespace(loop=asyncio.get_running_loop()))
        calls = []
        original = ops.upsert_error
        def persist(*args, **kwargs):
            calls.append(threading.get_ident())
            # This reaches the root handler from the worker thread.
            logging.getLogger("database").error("Nested persistence error")
            return original(*args, **kwargs)
        monkeypatch.setattr(ops, "upsert_error", persist)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            for _ in range(100):
                logging.getLogger("api_request_logs").error("Repeated error")
            await drain(handler)
            assert len(calls) == 8
            assert all(thread != threading.get_ident() for thread in calls)
            assert ops.list_errors()[0]["count"] == 8
            assert not handler._tasks
            assert handler._slots.acquire(blocking=False)
            handler._slots.release()
        finally:
            root.removeHandler(handler)
    asyncio.run(scenario())


def test_locked_database_does_not_block_event_loop():
    ops.ensure()
    async def scenario():
        with sqlite3.connect(ops.DB_PATH) as blocker:
            blocker.execute("BEGIN EXCLUSIVE")
            task = asyncio.create_task(ops.report_error(SimpleNamespace(), "test", RuntimeError("API failure")))
            # The SQLite busy timeout is one second; the loop must still serve
            # another coroutine while the database is locked.
            await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.2)
            assert not task.done()
            assert await asyncio.wait_for(task, timeout=2) == {}
            assert ops._report_retry_at > 0
    asyncio.run(scenario())


def test_real_sqlite_full_error_is_contained_and_reporting_resumes(monkeypatch):
    ops.ensure()
    connect = ops._connect
    @contextmanager
    def full_database():
        with connect() as db:
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={pages}")
            yield db
    monkeypatch.setattr(ops, "_connect", full_database)
    # Force SQLite to need more pages while existing pages remain available
    # for reads; no actual filesystem needs to be filled for this regression.
    with pytest.raises(sqlite3.OperationalError, match="database or disk is full"):
        ops.upsert_error("test", RuntimeError("x" * 2000), trace="y" * 3500)
    async def scenario():
        assert await ops.report_error(SimpleNamespace(), "test", RuntimeError("x" * 2000), trace="y" * 3500) == {}
        assert ops._report_retry_at > 0
        monkeypatch.setattr(ops, "_connect", connect)
        monkeypatch.setattr(ops, "_report_retry_at", 0.0)
        recovered = await ops.report_error(SimpleNamespace(), "test", RuntimeError("Recovered"))
        assert recovered["count"] == 1
    asyncio.run(scenario())


def test_connection_is_closed_and_failed_transactions_roll_back():
    ops.ensure()
    with pytest.raises(RuntimeError):
        with ops._connect() as connection:
            connection.execute("INSERT INTO support_settings VALUES ('test', 'value')")
            raise RuntimeError("abort")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert ops.get_setting("test") == ""


def test_discord_report_send_and_deduplication_still_work(monkeypatch):
    ops.set_setting("error_channel_id", "123")
    async def scenario():
        sent, edited = [], []
        class Message:
            id = 456
            async def edit(self, **kwargs):
                edited.append(kwargs["view"])
        class Channel:
            async def send(self, **kwargs):
                sent.append(kwargs["view"])
                return Message()
            async def fetch_message(self, message_id):
                assert message_id == 456
                return Message()
        bot = SimpleNamespace(get_guild=lambda guild_id: SimpleNamespace(get_channel=lambda channel_id: Channel()))
        first = await ops.report_error(bot, "test", RuntimeError("Same failure"))
        second = await ops.report_error(bot, "test", RuntimeError("Same failure"))
        assert first["error_id"] == second["error_id"]
        assert second["count"] == 2 and second["message_id"] == "456"
        assert len(sent) == 1 and len(edited) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("free", [0, 64 * 1024 * 1024 + 1024])
def test_backup_disk_preflight_preserves_live_data_and_last_backup(tmp_path, monkeypatch, free):
    monkeypatch.chdir(tmp_path)
    live = tmp_path / "db" / "live.db"
    live.parent.mkdir()
    with sqlite3.connect(live) as db:
        db.execute("CREATE TABLE data(value)")
        db.execute("INSERT INTO data VALUES ('keep')")
    wal = Path(str(live) + "-wal")
    wal.write_bytes(b"pending writes" * 100)
    previous = tmp_path / "db" / "backups" / "last-good" / "live.db"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(live.read_bytes())
    before = (live.read_bytes(), wal.read_bytes(), previous.read_bytes())
    monkeypatch.setattr("shutil.disk_usage", lambda path: SimpleNamespace(free=free))
    target = tmp_path / "db" / "backups" / "new"
    with pytest.raises(OSError) as failure:
        asyncio.run(config_transfer.write_snapshot(str(target)))
    assert failure.value.errno == errno.ENOSPC
    assert not target.exists()
    assert (live.read_bytes(), wal.read_bytes(), previous.read_bytes()) == before
