"""Small server-side OAuth session store for LBoost Shop.

Discord access and refresh tokens never enter the browser cookie. Both are
Fernet-encrypted before SQLite persistence.
"""
from __future__ import annotations

import base64
import hashlib
import sqlite3
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
