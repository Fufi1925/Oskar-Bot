"""Small server-side OAuth session store for LBoost Shop.

Discord access and refresh tokens never enter the browser cookie. Both are
Fernet-encrypted before SQLite persistence.
"""
from __future__ import annotations

import base64
import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from lbost_shop_app.config import Settings


def _connect(settings: Settings) -> sqlite3.Connection:
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            access_token BLOB NOT NULL,
            refresh_token BLOB NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shop_sessions_user ON oauth_sessions(user_id)")
    return conn


def _fernet(settings: Settings) -> Fernet:
    raw = settings.token_encryption_key.strip() or settings.signing_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def save_oauth_session(session_id: str, user_id: int, token: dict[str, Any], settings: Settings) -> None:
    cipher = _fernet(settings)
    now = int(time.time())
    expires_at = now + max(60, int(token.get("expires_in") or 604800))
    access = cipher.encrypt(str(token.get("access_token") or "").encode())
    refresh = cipher.encrypt(str(token.get("refresh_token") or "").encode())
    with _connect(settings) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO oauth_sessions
               (session_id,user_id,access_token,refresh_token,expires_at,created_at,last_seen_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, user_id, access, refresh, expires_at, now, now),
        )


def load_oauth_session(session_id: str, user_id: int, settings: Settings) -> dict[str, Any] | None:
    with _connect(settings) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE oauth_sessions SET last_seen_at=? WHERE session_id=?", (int(time.time()), session_id))
    try:
        cipher = _fernet(settings)
        return {
            "access_token": cipher.decrypt(row["access_token"]).decode(),
            "refresh_token": cipher.decrypt(row["refresh_token"]).decode(),
            "expires_at": int(row["expires_at"]),
        }
    except (InvalidToken, UnicodeDecodeError):
        delete_oauth_session(session_id, settings)
        return None


def delete_oauth_session(session_id: str, settings: Settings) -> None:
    if not session_id:
        return
    with _connect(settings) as conn:
        conn.execute("DELETE FROM oauth_sessions WHERE session_id=?", (session_id,))


def purge_expired(settings: Settings) -> None:
    cutoff = int(time.time()) - settings.session_max_age
    with _connect(settings) as conn:
        conn.execute("DELETE FROM oauth_sessions WHERE last_seen_at < ?", (cutoff,))

# ── Feature configuration and runtime data ──────────────────────────────
_FEATURE_DBS: set[str] = set()
_FEATURE_DB_LOCK = threading.Lock()


def init_features(settings: Settings) -> None:
    key = str(Path(settings.db_path).resolve())
    if key in _FEATURE_DBS:
        return
    with _FEATURE_DB_LOCK:
        if key in _FEATURE_DBS:
            return
        _init_features(settings)
        _FEATURE_DBS.add(key)


def _init_features(settings: Settings) -> None:
    with _connect(settings) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS guild_features (
            guild_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (guild_id, feature)
        );
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL, reason TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL, channel_id INTEGER UNIQUE NOT NULL,
            owner_id INTEGER NOT NULL, panel_key TEXT NOT NULL,
            claimed_by INTEGER, status TEXT NOT NULL DEFAULT 'open',
            created_at INTEGER NOT NULL, closed_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL, prize TEXT NOT NULL,
            winners INTEGER NOT NULL, ends_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', winner_ids TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            message_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY(message_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL, kind TEXT NOT NULL,
            channel_id INTEGER NOT NULL, content TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL, next_run INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS feature_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
            action TEXT NOT NULL, details TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """)


def get_feature(guild_id: int, feature: str, settings: Settings) -> dict[str, Any]:
    import json
    init_features(settings)
    with _connect(settings) as conn:
        row = conn.execute(
            "SELECT data_json FROM guild_features WHERE guild_id=? AND feature=?",
            (guild_id, feature),
        ).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row["data_json"])
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def set_feature(guild_id: int, feature: str, data: dict[str, Any], actor_id: int, settings: Settings) -> None:
    import json
    init_features(settings)
    now = int(time.time())
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with _connect(settings) as conn:
        conn.execute(
            """INSERT INTO guild_features(guild_id,feature,data_json,updated_at)
               VALUES(?,?,?,?) ON CONFLICT(guild_id,feature)
               DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at""",
            (guild_id, feature, payload, now),
        )
        conn.execute(
            "INSERT INTO feature_audit(guild_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
            (guild_id, actor_id, f"configure:{feature}", payload[:2000], now),
        )


def all_features(guild_id: int, settings: Settings) -> dict[str, dict[str, Any]]:
    import json
    init_features(settings)
    result: dict[str, dict[str, Any]] = {}
    with _connect(settings) as conn:
        rows = conn.execute("SELECT feature,data_json FROM guild_features WHERE guild_id=?", (guild_id,)).fetchall()
    for row in rows:
        try:
            value = json.loads(row["data_json"])
            result[row["feature"]] = value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            result[row["feature"]] = {}
    return result


def feature_history(guild_id: int, settings: Settings, days: int = 14) -> list[dict[str, Any]]:
    """Daily configuration changes for the server overview chart."""
    from datetime import datetime, timedelta, timezone
    init_features(settings)
    start = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    with _connect(settings) as conn:
        rows = conn.execute(
            """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS amount
               FROM feature_audit WHERE guild_id=? AND created_at>=?
               GROUP BY day""",
            (guild_id, int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())),
        ).fetchall()
    amounts = {str(row["day"]): int(row["amount"]) for row in rows}
    points = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        points.append({"day": day.strftime("%d.%m"), "amount": amounts.get(day.isoformat(), 0)})
    maximum = max((point["amount"] for point in points), default=0) or 1
    for point in points:
        point["height"] = max(5, round(point["amount"] / maximum * 100))
    return points
