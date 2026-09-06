"""Storage shared by the custom-command listener and dashboard API."""

from __future__ import annotations

import json
import re
import time

import aiosqlite

from utils import db_open

DB_PATH = "db/custom_commands.db"
FREE_MAX_COMMANDS = 3
PREMIUM_MAX_COMMANDS = 20
# Kept for callers/tests that explicitly mean the free plan.
MAX_COMMANDS = FREE_MAX_COMMANDS
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
    await db.execute(
        "CREATE TABLE IF NOT EXISTS custom_command_marketplace ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, source_guild_id INTEGER NOT NULL, "
        "command_name TEXT NOT NULL COLLATE NOCASE, payload_json TEXT NOT NULL, "
        "description TEXT NOT NULL, category TEXT NOT NULL, screenshots_json TEXT NOT NULL DEFAULT '[]', "
        "author_name TEXT NOT NULL DEFAULT '', downloads INTEGER NOT NULL DEFAULT 0, "
        "published_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, "
        "UNIQUE(source_guild_id, command_name))"
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
    config: dict | None = None, max_commands: int = FREE_MAX_COMMANDS,
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
         guild_id, max(1, int(max_commands)), guild_id, name),
    )
    await db.commit()
    return cursor.rowcount > 0

async def marketplace_list(db: aiosqlite.Connection, category: str = "", query: str = "") -> list[dict]:
    db.row_factory = aiosqlite.Row
    where, params = [], []
    if category and category != "Alle":
        where.append("category = ?"); params.append(category)
    if query:
        where.append("(command_name LIKE ? OR description LIKE ? OR author_name LIKE ?)")
        needle = f"%{query[:80]}%"; params.extend([needle, needle, needle])
    sql = ("SELECT id, source_guild_id, command_name, description, category, screenshots_json, "
           "author_name, downloads, published_at, payload_json FROM custom_command_marketplace")
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY downloads DESC, updated_at DESC LIMIT 100"
    rows = await (await db.execute(sql, params)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item.pop("source_guild_id", None)
        try: item["screenshots"] = json.loads(item.pop("screenshots_json") or "[]")
        except (TypeError, ValueError): item["screenshots"] = []
        try: item["command"] = json.loads(item.pop("payload_json"))
        except (TypeError, ValueError): item["command"] = {}
        result.append(item)
    return result


async def published_names(db: aiosqlite.Connection, guild_id: int) -> set[str]:
    rows = await (await db.execute(
        "SELECT command_name FROM custom_command_marketplace WHERE source_guild_id = ?", (guild_id,)
    )).fetchall()
    return {str(row[0]).lower() for row in rows}


async def publish(db: aiosqlite.Connection, guild_id: int, name: str, description: str,
                  category: str, screenshots: list[str], author_name: str) -> bool:
    rows = await list_all(db, guild_id)
    command = next((row for row in rows if row["name"].lower() == name.lower()), None)
    if command is None: return False
    # Marketplace snapshots never expose dashboard actor IDs or internal dates.
    command = {key: value for key, value in command.items()
               if key not in {"guild_id", "created_by", "created_at", "updated_at", "published"}}
    config = command.get("config") if isinstance(command.get("config"), dict) else {}
    config["allowed_roles"], config["allowed_users"] = [], []
    config["deny_without_role"] = False
    def clear_server_ids(actions):
        for action in actions if isinstance(actions, list) else []:
            if not isinstance(action, dict): continue
            action.pop("role_id", None); action.pop("channel_id", None)
            clear_server_ids(action.get("then", [])); clear_server_ids(action.get("else", []))
            for button in action.get("buttons", []) if isinstance(action.get("buttons"), list) else []:
                if isinstance(button, dict): clear_server_ids(button.get("actions", []))
    clear_server_ids(config.get("actions", []))
    command["config"] = config
    now = int(time.time())
    await db.execute(
        "INSERT INTO custom_command_marketplace "
        "(source_guild_id, command_name, payload_json, description, category, screenshots_json, author_name, published_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(source_guild_id, command_name) DO UPDATE SET "
        "payload_json=excluded.payload_json, description=excluded.description, category=excluded.category, "
        "screenshots_json=excluded.screenshots_json, author_name=excluded.author_name, updated_at=excluded.updated_at",
        (guild_id, name, json.dumps(command, ensure_ascii=False), description, category,
         json.dumps(screenshots, ensure_ascii=False), author_name, now, now),
    )
    await db.commit(); return True
