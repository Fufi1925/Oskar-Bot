"""Storage shared by the custom-command listener and dashboard API."""

from __future__ import annotations

import json
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
        "use_prefix INTEGER NOT NULL DEFAULT 1, "
        "use_exact INTEGER NOT NULL DEFAULT 0, "
        "use_contains INTEGER NOT NULL DEFAULT 0, "
        "use_slash INTEGER NOT NULL DEFAULT 0, "
        "config_json TEXT NOT NULL DEFAULT '{}', "
        "PRIMARY KEY (guild_id, name))"
    )
    columns = {row[1] for row in await (await db.execute("PRAGMA table_info(custom_commands)")).fetchall()}
    for column, default in (
        ("use_prefix", 1), ("use_exact", 0),
        ("use_contains", 0), ("use_slash", 0), ("config_json", "'{}'"),
    ):
        if column not in columns:
            kind = "TEXT" if column == "config_json" else "INTEGER"
            await db.execute(
                f"ALTER TABLE custom_commands ADD COLUMN {column} {kind} NOT NULL DEFAULT {default}"
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
            "SELECT guild_id, name, response, created_by, created_at, updated_at, "
            "use_prefix, use_exact, use_contains, use_slash, config_json "
            "FROM custom_commands ORDER BY guild_id, name"
        )).fetchall()
    else:
        rows = await (await db.execute(
            "SELECT guild_id, name, response, created_by, created_at, updated_at, "
            "use_prefix, use_exact, use_contains, use_slash, config_json "
            "FROM custom_commands WHERE guild_id = ? ORDER BY name", (guild_id,)
        )).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = json.loads(item.pop("config_json") or "{}")
        except (TypeError, ValueError):
            item["config"] = {}
        result.append(item)
    return result


async def save(
    db: aiosqlite.Connection, guild_id: int, name: str, response: str, actor: str,
    *, use_prefix: bool = True, use_exact: bool = False,
    use_contains: bool = False, use_slash: bool = False,
    config: dict | None = None,
) -> bool:
    now = int(time.time())
    # The limit check and insert are one SQLite statement, so concurrent
    # dashboard requests cannot both claim the final available slot.
    cursor = await db.execute(
        "INSERT INTO custom_commands "
        "(guild_id, name, response, created_by, created_at, updated_at, "
        "use_prefix, use_exact, use_contains, use_slash, config_json) "
        "SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE "
        "(SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?) < ? OR "
        "EXISTS (SELECT 1 FROM custom_commands WHERE guild_id = ? AND name = ? COLLATE NOCASE) "
        "ON CONFLICT(guild_id, name) DO UPDATE SET "
        "response = excluded.response, updated_at = excluded.updated_at, "
        "use_prefix = excluded.use_prefix, use_exact = excluded.use_exact, "
        "use_contains = excluded.use_contains, use_slash = excluded.use_slash, "
        "config_json = excluded.config_json",
        (guild_id, name, response, actor, now, now,
         int(use_prefix), int(use_exact), int(use_contains), int(use_slash),
         json.dumps(config or {}, ensure_ascii=False),
         guild_id, MAX_COMMANDS, guild_id, name),
    )
    await db.commit()
    return cursor.rowcount > 0
