"""Small cross-device preference store for the signed-in account page."""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

DB_PATH = "db/account_preferences.db"

DEFAULTS: dict[str, str] = {
    "language": "de",
    "theme": "dark",
    "timezone": "Europe/Berlin",
    "number_format": "de-DE",
    "date_format": "medium",
    "start_page": "/dashboard",
}
ALLOWED = {
    "language": {"de", "en"},
    "theme": {"dark", "light"},
    "timezone": {"Europe/Berlin", "Europe/London", "UTC", "America/New_York", "America/Los_Angeles", "Asia/Tokyo"},
    "number_format": {"de-DE", "en-GB", "en-US"},
    "date_format": {"short", "medium", "long", "iso"},
    "start_page": {"/dashboard", "/dashboard/guilds", "/konto", "/status"},
}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS account_preferences ("
            "user_id TEXT PRIMARY KEY, language TEXT NOT NULL DEFAULT 'de',"
            "theme TEXT NOT NULL DEFAULT 'dark', timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',"
            "number_format TEXT NOT NULL DEFAULT 'de-DE', date_format TEXT NOT NULL DEFAULT 'medium',"
            "start_page TEXT NOT NULL DEFAULT '/dashboard', updated_at INTEGER NOT NULL DEFAULT 0)"
        )


def get(user_id: str) -> dict[str, Any]:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT language,theme,timezone,number_format,date_format,start_page,updated_at "
            "FROM account_preferences WHERE user_id=?", (str(user_id),)
        ).fetchone()
    return {**DEFAULTS, **(dict(row) if row else {}), "user_id": str(user_id)}


def save(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    current = get(user_id)
    for key, choices in ALLOWED.items():
        if key not in values:
            continue
        value = str(values[key])
        if value not in choices:
            raise ValueError(f"Ungültige Einstellung: {key}")
        current[key] = value
    current["updated_at"] = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO account_preferences(user_id,language,theme,timezone,number_format,date_format,start_page,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "language=excluded.language,theme=excluded.theme,timezone=excluded.timezone,"
            "number_format=excluded.number_format,date_format=excluded.date_format,"
            "start_page=excluded.start_page,updated_at=excluded.updated_at",
            (str(user_id), current["language"], current["theme"], current["timezone"],
             current["number_format"], current["date_format"], current["start_page"], current["updated_at"]),
        )
    return get(user_id)


def erase_subject(user_id: str) -> int:
    ensure()
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM account_preferences WHERE user_id=?", (str(user_id),))
        return cursor.rowcount or 0
