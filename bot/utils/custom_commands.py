"""Storage shared by the custom-command listener and dashboard API."""

from __future__ import annotations

import re
import time

import aiosqlite

from utils import db_open

DB_PATH = "db/custom_commands.db"
MAX_COMMANDS = 3
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


async def connect() -> aiosqlite.Connection:
    db = await db_open.connect(DB_PATH)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS custom_commands ("
        "guild_id INTEGER NOT NULL, name TEXT NOT NULL COLLATE NOCASE, "
        "response TEXT NOT NULL, created_by TEXT DEFAULT '', "
        "created_at INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0, "
        "PRIMARY KEY (guild_id, name))"
    )
    await db.commit()
    return db


def normalise_name(value: str) -> str:
    return str(value or "").strip().lower().lstrip("!>?.")


def valid_name(value: str) -> bool:
    return bool(NAME_RE.fullmatch(value))


async def list_all(db: aiosqlite.Connection, guild_id: int | None = None) -> list[dict]:
    db.row_factory = aiosqlite.Row
    if guild_id is None:
        rows = await (await db.execute(
            "SELECT guild_id, name, response, created_by, created_at, updated_at "
            "FROM custom_commands ORDER BY guild_id, name"
        )).fetchall()
    else:
        rows = await (await db.execute(
            "SELECT guild_id, name, response, created_by, created_at, updated_at "
            "FROM custom_commands WHERE guild_id = ? ORDER BY name", (guild_id,)
        )).fetchall()
    return [dict(row) for row in rows]


async def save(db: aiosqlite.Connection, guild_id: int, name: str, response: str, actor: str) -> bool:
    now = int(time.time())
    # The limit check and insert are one SQLite statement, so concurrent
    # dashboard requests cannot both claim the final available slot.
    cursor = await db.execute(
        "INSERT INTO custom_commands (guild_id, name, response, created_by, created_at, updated_at) "
        "SELECT ?, ?, ?, ?, ?, ? WHERE "
        "(SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?) < ? OR "
        "EXISTS (SELECT 1 FROM custom_commands WHERE guild_id = ? AND name = ? COLLATE NOCASE) "
        "ON CONFLICT(guild_id, name) DO UPDATE SET "
        "response = excluded.response, updated_at = excluded.updated_at",
        (guild_id, name, response, actor, now, now,
         guild_id, MAX_COMMANDS, guild_id, name),
    )
    await db.commit()
    return cursor.rowcount > 0
