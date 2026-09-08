"""Account session history and revocation for the stateless NextAuth JWTs.

No IP address and no browser fingerprint are stored. A shortened User-Agent is
used only to produce a human-readable device label and to warn when the broad
device class changes (for example mobile to desktop).
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "account_security.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS account_sessions ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,"
            " device TEXT NOT NULL DEFAULT '', device_class TEXT NOT NULL DEFAULT '',"
            " user_agent TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,"
            " unusual INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS account_sessions_user_time"
            " ON account_sessions(user_id, created_at DESC)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS account_revocations ("
            " user_id TEXT PRIMARY KEY, revoked_before_ms INTEGER NOT NULL DEFAULT 0)"
        )


def describe_device(user_agent: str) -> tuple[str, str]:
    ua = (user_agent or "").strip()
    low = ua.lower()
    if "iphone" in low or "ipad" in low:
        device_class, system = "mobile", "iPhone/iPad"
    elif "android" in low:
        device_class, system = "mobile", "Android"
    elif "windows" in low:
        device_class, system = "desktop", "Windows"
    elif "macintosh" in low or "mac os" in low:
        device_class, system = "desktop", "macOS"
    elif "linux" in low:
        device_class, system = "desktop", "Linux"
    else:
        device_class, system = "unknown", "Unbekanntes Gerät"

    if "edg/" in low:
        browser = "Edge"
    elif "opr/" in low or "opera" in low:
        browser = "Opera"
    elif "firefox/" in low:
        browser = "Firefox"
    elif "chrome/" in low or "crios/" in low:
        browser = "Chrome"
    elif "safari/" in low:
        browser = "Safari"
    else:
        browser = "Browser"
    return f"{browser} auf {system}", device_class


def record_session(user_id: str, user_agent: str) -> dict[str, Any]:
    ensure()
    uid = str(user_id)
    now = int(time.time())
    device, device_class = describe_device(user_agent)
    with _connect() as conn:
        previous = conn.execute(
            "SELECT * FROM account_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        # React Strict Mode or a reload of /auth/success must not create two
        # alleged logins for the same browser within a few seconds.
        if previous and previous["device"] == device and now - int(previous["created_at"]) < 30:
            return dict(previous)
        unusual = bool(
            previous
            and device_class != "unknown"
            and previous["device_class"] not in ("", "unknown", device_class)
        )
        cursor = conn.execute(
            "INSERT INTO account_sessions(user_id,device,device_class,user_agent,created_at,unusual)"
            " VALUES(?,?,?,?,?,?)",
            # The readable device label is sufficient. Do not retain the raw user agent.
            (uid, device, device_class, "", now, int(unusual)),
        )
        # Twenty entries are enough to understand account access and keep the
        # amount of personal metadata deliberately small.
        conn.execute(
            "DELETE FROM account_sessions WHERE user_id=? AND id NOT IN ("
            " SELECT id FROM account_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 20)",
            (uid, uid),
        )
        row = conn.execute("SELECT * FROM account_sessions WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row) if row else {}


def sessions_for(user_id: str) -> list[dict[str, Any]]:
    ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id,device,created_at,unusual FROM account_sessions"
            " WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (str(user_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_all(user_id: str) -> int:
    ensure()
    value = int(time.time() * 1000)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO account_revocations(user_id,revoked_before_ms) VALUES(?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET revoked_before_ms=excluded.revoked_before_ms",
            (str(user_id), value),
        )
    return value


def revoked_before(user_id: str) -> int:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT revoked_before_ms FROM account_revocations WHERE user_id=?",
            (str(user_id),),
        ).fetchone()
    return int(row[0]) if row else 0


def erase_subject(user_id: str) -> int:
    ensure()
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM account_sessions WHERE user_id=?", (str(user_id),))
        conn.execute("DELETE FROM account_revocations WHERE user_id=?", (str(user_id),))
    return cursor.rowcount or 0
