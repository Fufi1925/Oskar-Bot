"""
Fehler und Vorschlaege von Testern.

Neu gebaut, nachdem die erste Fassung nur Titel, Text und einen
Zustand kannte. Was im Betrieb fehlte:

  * **Ein Verlauf.** Der Owner konnte den Zustand setzen und einen
    Vermerk hinterlassen -- aber nur einen. Die zweite Antwort
    ueberschrieb die erste, und niemand konnte nachlesen, was
    besprochen wurde.
  * **Eine Rueckfrage.** Bei "geht nicht" muss man nachfragen koennen,
    und der Melder muss antworten koennen. Vorher war die Meldung ein
    Einwegzettel.
  * **Dringlichkeit.** Ein Absturz und ein Schreibfehler standen
    gleichberechtigt untereinander.
  * **Doppelte Meldungen.** Drei Leute melden denselben Fehler; ohne
    Hinweis liest der Owner ihn dreimal.
  * **Zustimmung.** Welcher Vorschlag mehreren wichtig ist, war nicht
    zu erkennen.

Zwei Tabellen: die Meldung selbst und ihr Verlauf. Der Verlauf ist
anhaengend -- Eintraege werden nie geaendert, nur ergaenzt. Wer
wissen will, warum etwas abgelehnt wurde, findet die Begruendung auch
nach der dritten Statusaenderung noch.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "tester_feedback.db")

# Was gemeldet werden kann.
KINDS = ("bug", "idea")

# Bearbeitungsstand.
#
# "duplicate" ist neu: eine Meldung, die es schon gibt. Sie einfach
# abzulehnen waere unhoeflich und verliert die Spur zum Original.
STATES = ("open", "confirmed", "in_progress", "done", "rejected", "duplicate")

# Wie dringend. Nur bei Fehlern sinnvoll, bei Vorschlaegen bleibt es
# auf "normal".
PRIORITIES = ("low", "normal", "high", "critical")

# Zustaende, die als erledigt gelten -- fuer Zaehlungen und Sortierung.
CLOSED = ("done", "rejected", "duplicate")

MAX_TITLE = 120
MAX_BODY = 4000
MAX_COMMENT = 2000


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
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                user_name   TEXT NOT NULL DEFAULT '',
                kind        TEXT NOT NULL DEFAULT 'bug',
                title       TEXT NOT NULL,
                body        TEXT NOT NULL DEFAULT '',
                -- Wo es passiert ist. Freitext, weil eine feste Liste
                -- beim naechsten neuen Reiter unvollstaendig waere.
                area        TEXT NOT NULL DEFAULT '',
                state       TEXT NOT NULL DEFAULT 'open',
                priority    TEXT NOT NULL DEFAULT 'normal',
                -- Wer sich darum kuemmert.
                assignee    TEXT NOT NULL DEFAULT '',
                -- Auf welche Meldung sich ein Duplikat bezieht.
                duplicate_of INTEGER,
                -- Fingerabdruck des Titels, um Dubletten zu erkennen.
                fingerprint TEXT NOT NULL DEFAULT '',
                at          INTEGER NOT NULL,
                updated_at  INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tester_feedback_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                author   TEXT NOT NULL,
                -- "comment", "state", "priority", "assign"
                kind     TEXT NOT NULL DEFAULT 'comment',
                text     TEXT NOT NULL DEFAULT '',
                at       INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tester_feedback_votes (
                entry_id INTEGER NOT NULL,
                user_id  TEXT NOT NULL,
                at       INTEGER NOT NULL,
                PRIMARY KEY (entry_id, user_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS tester_feedback_user "
            "ON tester_feedback (user_id, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS tester_feedback_log_entry "
            "ON tester_feedback_log (entry_id, id)"
        )

        # Aeltere Datenbanken nachziehen. Die erste Fassung hatte
        # weniger Spalten; ohne das schlaegt jede Abfrage fehl, und die
        # bereits gemeldeten Sachen waeren verloren.
        existing = {row["name"] for row in conn.execute(
            "PRAGMA table_info(tester_feedback)"
        )}
        for column, ddl in (
            ("area", "TEXT NOT NULL DEFAULT ''"),
            ("priority", "TEXT NOT NULL DEFAULT 'normal'"),
            ("assignee", "TEXT NOT NULL DEFAULT ''"),
            ("duplicate_of", "INTEGER"),
            ("fingerprint", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE tester_feedback ADD COLUMN {column} {ddl}"
                )

        # Die alte Spalte `note` wanderte in den Verlauf. Sie bleibt
        # stehen -- eine Spalte zu loeschen ist in SQLite eine
        # Tabellenkopie, und der eine ungenutzte Text schadet nicht.


def _fingerprint(title: str) -> str:
    """Ein grober Fingerabdruck des Titels, um Dubletten zu finden.

    Kleinschreibung, keine Satzzeichen, sortierte Woerter. "Der Knopf
    tut nichts!" und "knopf tut nichts" ergeben denselben Wert. Das ist
    absichtlich grob: der Hinweis soll auffallen, nicht beweisen.
    """

    words = re.findall(r"[a-zäöüß0-9]+", str(title or "").lower())
    # Fuellwoerter raus -- sonst haengt die Aehnlichkeit an "der/die/das".
    stop = {"der", "die", "das", "ein", "eine", "und", "oder", "ist", "im",
            "in", "bei", "mit", "von", "zu", "the", "a", "an", "is", "at"}
    core = sorted(w for w in words if w not in stop and len(w) > 2)
    if not core:
        return ""
    return hashlib.sha256(" ".join(core).encode("utf-8")).hexdigest()[:16]


def find_similar(title: str, limit: int = 3) -> list[dict[str, Any]]:
    """Offene Meldungen mit demselben Fingerabdruck."""

    ensure()
    mark = _fingerprint(title)
    if not mark:
        return []

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, state, kind FROM tester_feedback "
            "WHERE fingerprint = ? AND state NOT IN ('done', 'rejected') "
            "ORDER BY id DESC LIMIT ?",
            (mark, max(1, min(limit, 10))),
        ).fetchall()

    return [dict(row) for row in rows]


def submit(
    user_id: str,
    title: str,
    *,
    body: str = "",
    kind: str = "bug",
    area: str = "",
    priority: str = "normal",
    user_name: str = "",
) -> dict[str, Any]:
    """Eine Meldung speichern.

    Gibt ``{"ok", "reason", "id", "similar"}`` zurueck. ``similar``
    nennt bereits offene Meldungen mit demselben Fingerabdruck -- die
    Meldung wird trotzdem angelegt. Sie zu verweigern waere falsch:
    zwei Leute koennen dieselbe Ueberschrift fuer verschiedene Dinge
    waehlen, und ein Melder, dem gesagt wird "gibt es schon", meldet
    beim naechsten Mal gar nichts mehr.
    """

    ensure()

    clean_title = " ".join(str(title or "").split())[:MAX_TITLE]
    if len(clean_title) < 5:
        return {"ok": False, "reason": "Der Titel ist zu kurz.", "id": 0,
                "similar": []}

    if kind not in KINDS:
        kind = "bug"
    if priority not in PRIORITIES:
        priority = "normal"
    # Ein Vorschlag hat keine Dringlichkeit -- er ist ein Wunsch.
    if kind == "idea":
        priority = "normal"

    clean_body = str(body or "").strip()[:MAX_BODY]
    clean_area = " ".join(str(area or "").split())[:60]

    similar = find_similar(clean_title)

    now = int(time.time())
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO tester_feedback "
            "(user_id, user_name, kind, title, body, area, priority, "
            " fingerprint, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(user_id), str(user_name or ""), kind, clean_title,
             clean_body, clean_area, priority, _fingerprint(clean_title), now),
        )
        entry_id = int(cursor.lastrowid or 0)

    return {"ok": True, "reason": "", "id": entry_id, "similar": similar}


def comment(entry_id: int, author: str, text: str,
            *, kind: str = "comment") -> bool:
    """Einen Eintrag an den Verlauf haengen.

    Nie aendern, nur anhaengen: wer wissen will, warum etwas abgelehnt
    wurde, soll die Begruendung auch nach der dritten Statusaenderung
    noch finden.
    """

    ensure()
    clean = str(text or "").strip()[:MAX_COMMENT]
    if not clean:
        return False

    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM tester_feedback WHERE id = ?", (int(entry_id),)
        ).fetchone()
        if row is None:
            return False

        conn.execute(
            "INSERT INTO tester_feedback_log (entry_id, author, kind, text, at) "
            "VALUES (?, ?, ?, ?, ?)",
            (int(entry_id), str(author), kind, clean, now),
        )
        conn.execute(
            "UPDATE tester_feedback SET updated_at = ? WHERE id = ?",
            (now, int(entry_id)),
        )
    return True


def vote(entry_id: int, user_id: str) -> dict[str, Any]:
    """Zustimmung geben oder zurueckziehen. Gibt den neuen Stand zurueck."""

    ensure()
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM tester_feedback WHERE id = ?", (int(entry_id),)
        ).fetchone()
        if row is None:
            return {"ok": False, "votes": 0, "voted": False}

        existing = conn.execute(
            "SELECT 1 FROM tester_feedback_votes "
            "WHERE entry_id = ? AND user_id = ?",
            (int(entry_id), str(user_id)),
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM tester_feedback_votes "
                "WHERE entry_id = ? AND user_id = ?",
                (int(entry_id), str(user_id)),
            )
            voted = False
        else:
            conn.execute(
                "INSERT INTO tester_feedback_votes (entry_id, user_id, at) "
                "VALUES (?, ?, ?)",
                (int(entry_id), str(user_id), now),
            )
            voted = True

        count = conn.execute(
            "SELECT COUNT(*) AS n FROM tester_feedback_votes WHERE entry_id = ?",
            (int(entry_id),),
        ).fetchone()["n"]

    return {"ok": True, "votes": count, "voted": voted}


def update(
    entry_id: int,
    *,
    actor: str,
    state: str = "",
    priority: str = "",
    assignee: str | None = None,
    duplicate_of: int | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Zustand, Dringlichkeit oder Bearbeiter aendern.

    Jede Aenderung landet zusaetzlich im Verlauf -- sonst steht am Ende
    ein Zustand da, den niemand erklaeren kann.
    """

    ensure()

    if state and state not in STATES:
        return {"ok": False, "reason": f"Unbekannter Stand: {state}."}
    if priority and priority not in PRIORITIES:
        return {"ok": False, "reason": f"Unbekannte Dringlichkeit: {priority}."}

    now = int(time.time())
    changes: list[str] = []

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tester_feedback WHERE id = ?", (int(entry_id),)
        ).fetchone()
        if row is None:
            return {"ok": False, "reason": "Die Meldung gibt es nicht."}

        if state and state != row["state"]:
            conn.execute(
                "UPDATE tester_feedback SET state = ?, updated_at = ? WHERE id = ?",
                (state, now, int(entry_id)),
            )
            changes.append(f"Stand: {row['state']} → {state}")

        if priority and priority != row["priority"]:
            conn.execute(
                "UPDATE tester_feedback SET priority = ?, updated_at = ? "
                "WHERE id = ?",
                (priority, now, int(entry_id)),
            )
            changes.append(f"Dringlichkeit: {row['priority']} → {priority}")

        if assignee is not None and str(assignee) != (row["assignee"] or ""):
            conn.execute(
                "UPDATE tester_feedback SET assignee = ?, updated_at = ? "
                "WHERE id = ?",
                (str(assignee), now, int(entry_id)),
            )
            changes.append(
                f"Bearbeiter: {assignee or '—'}" if assignee else "Bearbeiter entfernt"
            )

        if duplicate_of is not None:
            # Auf sich selbst zu verweisen ergibt eine Schleife, die
            # die Anzeige nie aufloest.
            if int(duplicate_of) == int(entry_id):
                return {"ok": False,
                        "reason": "Eine Meldung kann kein Duplikat ihrer selbst sein."}
            conn.execute(
                "UPDATE tester_feedback SET duplicate_of = ?, state = ?, "
                "updated_at = ? WHERE id = ?",
                (int(duplicate_of) or None, "duplicate", now, int(entry_id)),
            )
            changes.append(f"Duplikat von #{duplicate_of}")

    for line in changes:
        comment(entry_id, actor, line, kind="state")
    if note.strip():
        comment(entry_id, actor, note, kind="comment")

    return {"ok": True, "reason": "", "changes": changes}


def _row(row: sqlite3.Row, votes: int = 0, voted: bool = False) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_name": row["user_name"] or "",
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"] or "",
        "area": row["area"] or "",
        "state": row["state"],
        "priority": row["priority"] or "normal",
        "assignee": row["assignee"] or "",
        "duplicate_of": row["duplicate_of"],
        "at": row["at"],
        "updated_at": row["updated_at"],
        "votes": votes,
        "voted": voted,
        "closed": row["state"] in CLOSED,
    }


def listing(
    user_id: str = "",
    *,
    viewer: str = "",
    limit: int = 100,
    state: str = "",
    kind: str = "",
) -> list[dict[str, Any]]:
    """Meldungen -- alle oder die eines Nutzers.

    ``viewer`` entscheidet nur, ob "habe ich zugestimmt?" gesetzt wird.
    Die Rechtefrage steht in der Route, nicht hier.
    """

    ensure()
    capped = max(1, min(int(limit or 100), 500))

    where, params = [], []
    if user_id:
        where.append("user_id = ?")
        params.append(str(user_id))
    if state and state in STATES:
        where.append("state = ?")
        params.append(state)
    if kind and kind in KINDS:
        where.append("kind = ?")
        params.append(kind)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(capped)

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tester_feedback {clause} "
            # Offene zuerst, dann die dringendsten, dann die neuesten.
            # Ohne die erste Spalte verschwindet eine offene Meldung
            # unter zwanzig erledigten.
            "ORDER BY (state IN ('done','rejected','duplicate')) ASC, "
            "CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "  WHEN 'normal' THEN 2 ELSE 3 END ASC, "
            "id DESC LIMIT ?",
            params,
        ).fetchall()

        counts = {
            row["entry_id"]: row["n"]
            for row in conn.execute(
                "SELECT entry_id, COUNT(*) AS n FROM tester_feedback_votes "
                "GROUP BY entry_id"
            )
        }
        mine = set()
        if viewer:
            mine = {
                row["entry_id"]
                for row in conn.execute(
                    "SELECT entry_id FROM tester_feedback_votes WHERE user_id = ?",
                    (str(viewer),),
                )
            }

    return [
        _row(row, votes=counts.get(row["id"], 0), voted=row["id"] in mine)
        for row in rows
    ]


def detail(entry_id: int, viewer: str = "") -> dict[str, Any] | None:
    """Eine Meldung samt Verlauf."""

    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tester_feedback WHERE id = ?", (int(entry_id),)
        ).fetchone()
        if row is None:
            return None

        votes = conn.execute(
            "SELECT COUNT(*) AS n FROM tester_feedback_votes WHERE entry_id = ?",
            (int(entry_id),),
        ).fetchone()["n"]

        voted = False
        if viewer:
            voted = conn.execute(
                "SELECT 1 FROM tester_feedback_votes "
                "WHERE entry_id = ? AND user_id = ?",
                (int(entry_id), str(viewer)),
            ).fetchone() is not None

        log = [
            {
                "id": item["id"],
                "author": item["author"],
                "kind": item["kind"],
                "text": item["text"],
                "at": item["at"],
            }
            for item in conn.execute(
                "SELECT * FROM tester_feedback_log WHERE entry_id = ? "
                "ORDER BY id ASC",
                (int(entry_id),),
            )
        ]

    entry = _row(row, votes=votes, voted=voted)
    entry["log"] = log
    return entry


def stats() -> dict[str, int]:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN state = 'open' THEN 1 ELSE 0 END) AS open, "
            "  SUM(CASE WHEN state = 'in_progress' THEN 1 ELSE 0 END) AS working, "
            "  SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) AS done, "
            "  SUM(CASE WHEN kind = 'bug' THEN 1 ELSE 0 END) AS bugs, "
            "  SUM(CASE WHEN kind = 'idea' THEN 1 ELSE 0 END) AS ideas, "
            "  SUM(CASE WHEN priority = 'critical' AND "
            "      state NOT IN ('done','rejected','duplicate') "
            "      THEN 1 ELSE 0 END) AS critical "
            "FROM tester_feedback"
        ).fetchone()

    return {key: (row[key] or 0) for key in
            ("total", "open", "working", "done", "bugs", "ideas", "critical")}
