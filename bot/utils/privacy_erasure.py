"""Reviewed account-erasure requests and narrowly scoped data removal.

This deliberately does not touch guild configuration, moderation/security
records, XP, message counts, voice activity or dashboard access granted by a
server owner. Those records have a separate purpose and deleting them through
an account button would damage other controllers' server configuration.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "privacy_erasure.db")
UNDO_SECONDS = 10
FUFI_ID = int(os.getenv("PRIVACY_REVIEWER_ID") or 1303627964734246944)
ANON_LABEL = "Nutzer löschte seine Daten nach Art. 17 DSGVO"


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _pepper() -> bytes:
    value = os.getenv("PRIVACY_HASH_PEPPER") or os.getenv("DASHBOARD_API_KEY") or "local-privacy-pepper"
    return value.encode("utf-8")


def subject_hash(user_id: str | int) -> str:
    return hmac.new(_pepper(), str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS erasure_requests ("
            " id TEXT PRIMARY KEY, user_id TEXT NOT NULL, username TEXT NOT NULL DEFAULT '',"
            " requested_at INTEGER NOT NULL, undo_until INTEGER NOT NULL,"
            " status TEXT NOT NULL DEFAULT 'undo', decided_by TEXT NOT NULL DEFAULT '',"
            " decided_at INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',"
            " completed_at INTEGER NOT NULL DEFAULT 0, notified_at INTEGER NOT NULL DEFAULT 0,"
            " result_json TEXT NOT NULL DEFAULT '{}')"
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(erasure_requests)")}
        if "notified_at" not in columns:
            conn.execute("ALTER TABLE erasure_requests ADD COLUMN notified_at INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS erasure_user ON erasure_requests(user_id, requested_at DESC)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS erased_trial_subjects ("
            " subject_hash TEXT PRIMARY KEY, erased_at INTEGER NOT NULL)"
        )


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    try:
        item["result"] = json.loads(item.pop("result_json") or "{}")
    except (TypeError, ValueError):
        item["result"] = {}
    return item


def create_request(user_id: str, username: str) -> dict[str, Any]:
    ensure()
    uid = str(user_id).strip()
    now = int(time.time())
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM erasure_requests WHERE user_id = ? AND status IN ('undo','pending')"
            " ORDER BY requested_at DESC LIMIT 1", (uid,),
        ).fetchone()
        if existing:
            return _row(existing) or {}
        request_id = secrets.token_urlsafe(18)
        conn.execute(
            "INSERT INTO erasure_requests(id,user_id,username,requested_at,undo_until,status)"
            " VALUES(?,?,?,?,?,'undo')",
            (request_id, uid, str(username)[:100], now, now + UNDO_SECONDS),
        )
        row = conn.execute("SELECT * FROM erasure_requests WHERE id = ?", (request_id,)).fetchone()
    return _row(row) or {}


def cancel(request_id: str, user_id: str) -> bool:
    ensure()
    now = int(time.time())
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE erasure_requests SET status='cancelled', decided_at=?"
            " WHERE id=? AND user_id=? AND status='undo' AND undo_until>=?",
            (now, request_id, str(user_id), now),
        )
        return (cursor.rowcount or 0) > 0


def mature(request_id: str) -> dict[str, Any] | None:
    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE erasure_requests SET status='pending'"
            " WHERE id=? AND status='undo' AND undo_until<=?", (request_id, now),
        )
        row = conn.execute("SELECT * FROM erasure_requests WHERE id=?", (request_id,)).fetchone()
    return _row(row)


def status_for(user_id: str) -> dict[str, Any] | None:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM erasure_requests WHERE user_id IN (?,?) ORDER BY requested_at DESC LIMIT 1",
            (str(user_id), f"deleted:{subject_hash(user_id)}"),
        ).fetchone()
    if row and row["status"] == "undo" and int(row["undo_until"]) <= int(time.time()):
        return mature(str(row["id"]))
    return _row(row)


def pending_notifications() -> list[dict[str, Any]]:
    """Mature overdue requests and atomically claim their owner notification."""
    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute("UPDATE erasure_requests SET status='pending' WHERE status='undo' AND undo_until<=?", (now,))
        rows = conn.execute(
            "SELECT * FROM erasure_requests WHERE status='pending'"
            " AND (notified_at=0 OR (notified_at<0 AND notified_at>?)) ORDER BY requested_at",
            (-(now - 60),),
        ).fetchall()
        if rows:
            # A negative timestamp is a short claim. A crashed worker may be
            # reclaimed after one minute; successful DMs become positive.
            conn.executemany("UPDATE erasure_requests SET notified_at=? WHERE id=?", [(-now, row["id"]) for row in rows])
    return [_row(row) or {} for row in rows]


def finish_notification(request_id: str, success: bool) -> None:
    ensure()
    with _connect() as conn:
        conn.execute(
            "UPDATE erasure_requests SET notified_at=? WHERE id=? AND notified_at<0",
            (int(time.time()) if success else 0, request_id),
        )


def get_request(request_id: str) -> dict[str, Any] | None:
    ensure()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM erasure_requests WHERE id=?", (request_id,)).fetchone()
    return _row(row)


def list_requests() -> list[dict[str, Any]]:
    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute("UPDATE erasure_requests SET status='pending' WHERE status='undo' AND undo_until<=?", (now,))
        rows = conn.execute("SELECT * FROM erasure_requests ORDER BY requested_at DESC LIMIT 500").fetchall()
    return [_row(row) or {} for row in rows]


def reject(request_id: str, actor: str, reason: str) -> dict[str, Any] | None:
    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE erasure_requests SET status='rejected',decided_by=?,decided_at=?,reason=?"
            " WHERE id=? AND status='pending'",
            (str(actor), now, str(reason)[:500], request_id),
        )
        row = conn.execute("SELECT * FROM erasure_requests WHERE id=?", (request_id,)).fetchone()
    return _row(row)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _delete(path: str, table: str, where: str, params: tuple) -> int:
    if not os.path.exists(path):
        return 0
    with _connect(path) as conn:
        if not _table_exists(conn, table):
            return 0
        cursor = conn.execute(f"DELETE FROM [{table}] WHERE {where}", params)
        return cursor.rowcount or 0


def _update(path: str, table: str, sql: str, params: tuple) -> int:
    if not os.path.exists(path):
        return 0
    with _connect(path) as conn:
        if not _table_exists(conn, table):
            return 0
        cursor = conn.execute(sql, params)
        return cursor.rowcount or 0


def erase_subject(user_id: str, username: str = "") -> dict[str, int]:
    """Remove account/profile data while preserving the documented exceptions."""
    uid = str(user_id)
    digest = subject_hash(uid)
    anon = f"deleted:{digest}"
    # SQLite INTEGER accepts text, but the web-application reader casts its key
    # to int. A stable negative surrogate keeps that old reader working without
    # retaining the Discord snowflake.
    anon_number = -(int(digest[:15], 16) or 1)
    result: dict[str, int] = {}

    result["dashboard_profile"] = _delete("db/admin_config.db", "dashboard_logins", "user_id = ?", (uid,))
    result["cookie_consents"] = _delete("db/cookie_consent.db", "cookie_consents", "user_id = ?", (uid,))

    result["web_application"] = _update(
        "db/web_apply.db", "web_applications",
        "UPDATE web_applications SET user_id=?,user_name=?,avatar='',answers='[]' WHERE CAST(user_id AS TEXT)=?",
        (anon_number, ANON_LABEL, uid),
    )
    result["beta_applications"] = _update(
        "db/beta_applications.db", "beta_applications",
        "UPDATE beta_applications SET user_id=?,user_name=?,avatar='',warum='',gut='',besser='',schluss='' WHERE user_id=?",
        (anon, ANON_LABEL, uid),
    )
    result["tester_feedback"] = _update(
        "db/tester_feedback.db", "tester_feedback",
        "UPDATE tester_feedback SET user_id=?,user_name=? WHERE user_id=?",
        (anon, ANON_LABEL, uid),
    )
    result["tester_votes"] = _delete("db/tester_feedback.db", "tester_feedback_votes", "user_id = ?", (uid,))
    result["tester_log_authors"] = _update(
        "db/tester_feedback.db", "tester_feedback_log",
        "UPDATE tester_feedback_log SET author=? WHERE author IN (?,?)",
        (ANON_LABEL, uid, str(username)),
    )

    # Premium is removed immediately. The redeemed key remains revoked for
    # accounting/abuse evidence, but its direct Discord identifier is replaced.
    result["premium_keys"] = _update(
        "db/premium.db", "premium_keys",
        "UPDATE premium_keys SET revoked=1,redeemed_by=? WHERE redeemed_by=?",
        (anon, uid),
    )
    result["premium_trial"] = _update(
        "db/premium_trial.db", "premium_trials",
        "UPDATE premium_trials SET user_id=?,guild_id=NULL,reset_by='' WHERE user_id=?",
        (anon, uid),
    )
    result["premium_trial_resets"] = _update(
        "db/premium_trial.db", "premium_trial_resets",
        "UPDATE premium_trial_resets SET user_id=?,last_by='' WHERE user_id=?",
        (anon, uid),
    )
    result["premium_notice"] = _delete("db/premium_notice.db", "premium_notice", "user_id = ?", (uid,))

    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO erased_trial_subjects(subject_hash,erased_at) VALUES(?,?)", (digest, int(time.time())))

    # Deliberately retained: levels/messages, voice data, moderation/security
    # records, bans, server settings, and dashboard access assigned by owners.
    return result


def approve(request_id: str, actor: str) -> dict[str, Any] | None:
    ensure()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM erasure_requests WHERE id=? AND status='pending'", (request_id,)).fetchone()
    if row is None:
        return None
    result = erase_subject(str(row["user_id"]), str(row["username"]))
    now = int(time.time())
    anon = f"deleted:{subject_hash(row['user_id'])}"
    with _connect() as conn:
        conn.execute(
            "UPDATE erasure_requests SET user_id=?,username=?,status='completed',"
            "decided_by=?,decided_at=?,completed_at=?,result_json=? WHERE id=?",
            (anon, ANON_LABEL, str(actor), now, now, json.dumps(result, sort_keys=True), request_id),
        )
        finished = conn.execute("SELECT * FROM erasure_requests WHERE id=?", (request_id,)).fetchone()
    return _row(finished)


def trial_already_used(user_id: str | int) -> bool:
    ensure()
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM erased_trial_subjects WHERE subject_hash=?", (subject_hash(user_id),)).fetchone() is not None
