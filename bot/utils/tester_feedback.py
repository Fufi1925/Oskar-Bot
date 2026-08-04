"""
Was Tester melden -- Fehler und Vorschlaege.

Eine kleine Tabelle, mehr braucht es nicht. Wichtig ist nur, dass
nichts verlorengeht und dass sichtbar bleibt, wer was wann geschrieben
hat.

Die Eintraege sehen **nur die Owner**. Ein Tester sieht seine eigenen
-- damit er weiss, dass die Meldung angekommen ist, und nicht dieselbe
Sache dreimal schickt.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "tester_feedback.db")

# Was gemeldet werden kann.
KINDS = ("bug", "idea")

# Bearbeitungsstand. Owner setzen ihn; der Tester sieht ihn.
STATES = ("open", "planned", "done", "rejected")

MAX_TITLE = 120
MAX_BODY = 2000


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tester_feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                user_name  TEXT NOT NULL DEFAULT '',
                kind       TEXT NOT NULL DEFAULT 'bug',
                title      TEXT NOT NULL,
                body       TEXT NOT NULL DEFAULT '',
                state      TEXT NOT NULL DEFAULT 'open',
                note       TEXT NOT NULL DEFAULT '',
                at         INTEGER NOT NULL,
                updated_at INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS tester_feedback_user "
            "ON tester_feedback (user_id, id DESC)"
        )


def submit(
    user_id: str,
    title: str,
    *,
    body: str = "",
    kind: str = "bug",
    user_name: str = "",
) -> dict[str, Any]:
    """Eine Meldung speichern.

    Gibt ``{"ok": bool, "reason": str, "id": int}`` zurueck statt zu
    werfen: der Aufrufer soll die Meldung weiterreichen koennen.
    """

    ensure()

    clean_title = " ".join(str(title or "").split())[:MAX_TITLE]
    if len(clean_title) < 3:
        return {"ok": False, "reason": "Der Titel ist zu kurz.", "id": 0}

    if kind not in KINDS:
        kind = "bug"

    clean_body = str(body or "").strip()[:MAX_BODY]

    now = int(time.time())
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO tester_feedback "
            "(user_id, user_name, kind, title, body, at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(user_id), str(user_name or ""), kind, clean_title,
             clean_body, now),
        )
        entry_id = int(cursor.lastrowid or 0)

    return {"ok": True, "reason": "", "id": entry_id}


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_name": row["user_name"] or "",
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"] or "",
        "state": row["state"],
        "note": row["note"] or "",
        "at": row["at"],
        "updated_at": row["updated_at"],
    }


def listing(user_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Meldungen -- alle, oder die eines Nutzers.

    Ohne ``user_id`` kommt alles zurueck; das ist die Owner-Sicht. Wer
    das aufruft, muss die Rechte vorher geprueft haben -- diese Datei
    kennt keine Rollen.
    """

    ensure()
    capped = max(1, min(int(limit or 100), 500))

    with _connect() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM tester_feedback WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (str(user_id), capped),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tester_feedback ORDER BY id DESC LIMIT ?",
                (capped,),
            ).fetchall()

    return [_row(row) for row in rows]


def set_state(entry_id: int, state: str, note: str = "") -> bool:
    """Bearbeitungsstand setzen. Nur Owner rufen das auf."""

    if state not in STATES:
        return False

    ensure()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE tester_feedback SET state = ?, note = ?, updated_at = ? "
            "WHERE id = ?",
            (state, str(note or "")[:MAX_BODY], int(time.time()), int(entry_id)),
        )
        return cursor.rowcount > 0


def stats() -> dict[str, int]:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN state = 'open' THEN 1 ELSE 0 END) AS open, "
            "  SUM(CASE WHEN kind = 'bug' THEN 1 ELSE 0 END) AS bugs, "
            "  SUM(CASE WHEN kind = 'idea' THEN 1 ELSE 0 END) AS ideas "
            "FROM tester_feedback"
        ).fetchone()

    return {
        "total": row["total"] or 0,
        "open": row["open"] or 0,
        "bugs": row["bugs"] or 0,
        "ideas": row["ideas"] or 0,
    }
