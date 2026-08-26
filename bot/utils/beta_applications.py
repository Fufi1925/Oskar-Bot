"""
Beta-Antraege fuer Hauptbot-Premium.

Wie es laeuft
-------------
1. Jemand klickt im Premium-Reiter auf „Beta -- 20 % Rabatt".
2. Er fuellt fuenf Fragen aus. Die erste ist sein Discord-Konto und
   laesst sich nicht eintippen -- sie kommt aus der Anmeldung.
3. Der Antrag landet hier.
4. Ein Admin nimmt an oder lehnt mit Begruendung ab.
5. Der Bot schickt eine DM. Bei Annahme gibt es Premium automatisch.

Warum die Discord-ID nicht aus dem Formular kommt
-------------------------------------------------
Sie wird serverseitig aus der Sitzung gesetzt. Kaeme sie aus dem
Browser, koennte jeder einen Antrag auf ein fremdes Konto stellen --
und bei Annahme bekaeme das fremde Konto Premium. Derselbe Grund, aus
dem der Dashboard-Proxy `actor` ueberschreibt.

Ein Antrag pro Konto
--------------------
Wer schon einen offenen Antrag hat, kann keinen zweiten stellen.
Abgelehnte duerfen es erneut versuchen -- eine Ablehnung ist keine
Sperre. Angenommene brauchen keinen zweiten.

Speicher
--------
`db/beta_applications.db`. Braucht ein Railway-Volume.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "beta_applications.db")

#: Die fuenf Fragen. Reihenfolge und Wortlaut stehen hier, damit
#: Formular, Auswertung und Test dieselbe Quelle haben -- zwei
#: handgepflegte Listen laufen auseinander.
#:
#: Die erste ist besonders: sie wird nicht ausgefuellt, sondern
#: angezeigt. Deshalb `readonly`.
FRAGEN: tuple[dict[str, Any], ...] = (
    {
        "key": "discord",
        "frage": "Dein Discord-Konto",
        "hinweis": "Kommt aus deiner Anmeldung und lässt sich hier nicht ändern.",
        "readonly": True,
        "min": 0,
        "max": 0,
    },
    {
        "key": "warum",
        "frage": "Warum möchtest du in die Beta?",
        "hinweis": "Was erhoffst du dir davon?",
        "readonly": False,
        "min": 20,
        "max": 1000,
    },
    {
        "key": "gut",
        "frage": "Was findest du am Bot gut?",
        "hinweis": "Was benutzt du am meisten?",
        "readonly": False,
        "min": 20,
        "max": 1000,
    },
    {
        "key": "besser",
        "frage": "Was kann der Bot besser machen?",
        "hinweis": "Ehrlich — daran arbeiten wir.",
        "readonly": False,
        "min": 20,
        "max": 1000,
    },
    {
        "key": "schluss",
        "frage": "Möchtest du uns noch etwas sagen?",
        "hinweis": "Dein Schlusssatz.",
        "readonly": False,
        "min": 0,
        "max": 1000,
    },
)

#: Die Antwortfelder, die wirklich gespeichert werden.
ANTWORT_FELDER = tuple(f["key"] for f in FRAGEN if not f["readonly"])

STATUS_OFFEN = "offen"
STATUS_ANGENOMMEN = "angenommen"
STATUS_ABGELEHNT = "abgelehnt"

#: Wie lange Premium bei Annahme gilt. 0 = unbegrenzt.
#: Die Beta laeuft ohne festes Ende -- entzogen wird von Hand.
BETA_DURATION_DAYS = 0


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS beta_applications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                user_name    TEXT NOT NULL DEFAULT '',
                avatar       TEXT NOT NULL DEFAULT '',
                warum        TEXT NOT NULL DEFAULT '',
                gut          TEXT NOT NULL DEFAULT '',
                besser       TEXT NOT NULL DEFAULT '',
                schluss      TEXT NOT NULL DEFAULT '',
                status       TEXT NOT NULL DEFAULT 'offen',
                grund        TEXT NOT NULL DEFAULT '',
                created_at   INTEGER NOT NULL,
                decided_at   INTEGER,
                decided_by   TEXT NOT NULL DEFAULT '',
                dm_state     TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS beta_applications_user "
            "ON beta_applications (user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS beta_applications_status "
            "ON beta_applications (status)"
        )


def _zeile(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        # Als Zeichenkette: eine Discord-ID ist groesser als das, was
        # JavaScript als Zahl noch genau darstellen kann.
        "user_id": str(row["user_id"]),
        "user_name": row["user_name"] or "",
        "avatar": row["avatar"] or "",
        "warum": row["warum"] or "",
        "gut": row["gut"] or "",
        "besser": row["besser"] or "",
        "schluss": row["schluss"] or "",
        "status": row["status"] or STATUS_OFFEN,
        "grund": row["grund"] or "",
        "created_at": int(row["created_at"] or 0),
        "decided_at": int(row["decided_at"] or 0) or None,
        "decided_by": row["decided_by"] or "",
        "dm_state": row["dm_state"] or "",
    }


def offener_antrag(user_id: str) -> Optional[dict[str, Any]]:
    """Der offene Antrag dieses Kontos, falls es einen gibt."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM beta_applications WHERE user_id = ? AND status = ? "
            "ORDER BY id DESC LIMIT 1",
            (str(user_id), STATUS_OFFEN),
        ).fetchone()
    return _zeile(row) if row else None


def letzter_antrag(user_id: str) -> Optional[dict[str, Any]]:
    """Der zuletzt gestellte Antrag -- egal in welchem Zustand."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM beta_applications WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (str(user_id),),
        ).fetchone()
    return _zeile(row) if row else None


def einreichen(user_id: str, user_name: str, avatar: str,
               antworten: dict[str, str]) -> dict[str, Any]:
    """Einen Antrag anlegen.

    `user_id` kommt aus der Sitzung, nicht aus dem Formular.
    """
    ensure()

    vorhanden = offener_antrag(user_id)
    if vorhanden:
        raise ValueError("Du hast bereits einen offenen Antrag.")

    werte = {feld: str(antworten.get(feld) or "").strip() for feld in ANTWORT_FELDER}

    for frage in FRAGEN:
        if frage["readonly"]:
            continue
        text = werte.get(frage["key"], "")
        if len(text) < frage["min"]:
            raise ValueError(
                f"„{frage['frage']}“ braucht mindestens {frage['min']} Zeichen."
            )
        if len(text) > frage["max"]:
            raise ValueError(
                f"„{frage['frage']}“ darf höchstens {frage['max']} Zeichen haben."
            )

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO beta_applications "
            "(user_id, user_name, avatar, warum, gut, besser, schluss, "
            " status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(user_id), str(user_name or "")[:100], str(avatar or "")[:300],
                werte["warum"], werte["gut"], werte["besser"], werte["schluss"],
                STATUS_OFFEN, int(time.time()),
            ),
        )
        neu = conn.execute(
            "SELECT * FROM beta_applications WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _zeile(neu)


def entscheiden(antrag_id: int, *, angenommen: bool, grund: str,
                admin: str) -> Optional[dict[str, Any]]:
    """Annehmen oder ablehnen."""
    ensure()
    status = STATUS_ANGENOMMEN if angenommen else STATUS_ABGELEHNT

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM beta_applications WHERE id = ?", (int(antrag_id),)
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            "UPDATE beta_applications SET status = ?, grund = ?, "
            "decided_at = ?, decided_by = ? WHERE id = ?",
            (status, str(grund or "")[:1000], int(time.time()),
             str(admin or ""), int(antrag_id)),
        )
        frisch = conn.execute(
            "SELECT * FROM beta_applications WHERE id = ?", (int(antrag_id),)
        ).fetchone()
    return _zeile(frisch)


def merke_dm(antrag_id: int, zustand: str) -> None:
    """Festhalten, ob die DM ankam.

    Ehrlich statt schoen: wer seine DMs zu hat, erfaehrt sonst nie von
    der Entscheidung, und im Admin-Bereich sieht es aus, als waere
    alles erledigt.
    """
    ensure()
    with _connect() as conn:
        conn.execute(
            "UPDATE beta_applications SET dm_state = ? WHERE id = ?",
            (str(zustand)[:40], int(antrag_id)),
        )


def liste(status: str = "", limit: int = 200) -> list[dict[str, Any]]:
    ensure()
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM beta_applications WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM beta_applications ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    return [_zeile(r) for r in rows]


def zahlen() -> dict[str, int]:
    ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM beta_applications GROUP BY status"
        ).fetchall()
    gezaehlt = {r["status"]: int(r["n"]) for r in rows}
    return {
        "offen": gezaehlt.get(STATUS_OFFEN, 0),
        "angenommen": gezaehlt.get(STATUS_ANGENOMMEN, 0),
        "abgelehnt": gezaehlt.get(STATUS_ABGELEHNT, 0),
        "gesamt": sum(gezaehlt.values()),
    }


def widerrufen(user_id: str, *, admin: str = "") -> int:
    """Angenommene Antraege dieses Kontos zurueckziehen.

    Das eigentliche Premium entzieht der Aufrufer -- hier wird nur
    festgehalten, dass die Aufnahme nicht mehr gilt. Sonst stuende im
    Admin-Bereich weiter „angenommen", waehrend das Konto laengst kein
    Premium mehr hat.
    """
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE beta_applications SET status = ?, "
            "grund = 'Premium wurde entzogen.', decided_at = ?, decided_by = ? "
            "WHERE user_id = ? AND status = ?",
            (STATUS_ABGELEHNT, int(time.time()), str(admin or ""),
             str(user_id), STATUS_ANGENOMMEN),
        )
        return cur.rowcount or 0
