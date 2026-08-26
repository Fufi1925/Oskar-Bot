"""
Wer hat den Premium-Hinweis schon gesehen?

Das Fenster
-----------
Wer Premium hat und die Seite betritt, bekommt einmal ein goldenes
Fenster: „Denk dran — du hast Premium." Danach nie wieder.

Wird das Premium entzogen und spaeter neu vergeben, erscheint es
erneut -- diesmal als „Willkommen zurück".

Warum das serverseitig steht und nicht im Cookie
------------------------------------------------
Ein Cookie haengt am Browser. Wer das Dashboard am Telefon und am
Rechner oeffnet, saehe das Fenster zweimal; wer die Cookies loescht,
jedes Mal neu. Und der entscheidende Fall liesse sich damit gar nicht
loesen: „nach einem Entzug wieder zeigen" muss wissen, dass es
dazwischen einen Entzug gab.

Deshalb steht hier pro Konto, welchen *Abschnitt* jemand gesehen hat.
Ein Abschnitt beginnt, wenn Premium vergeben wird, und endet mit dem
Entzug. Solange die Nummer gleich bleibt, ist das Fenster erledigt.

Speicher
--------
`db/premium_notice.db`. Braucht ein Railway-Volume, sonst sieht jeder
das Fenster nach jedem Deploy erneut.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "premium_notice.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS premium_notice (
                user_id     TEXT PRIMARY KEY,
                epoche      INTEGER NOT NULL DEFAULT 1,
                gesehen     INTEGER NOT NULL DEFAULT 0,
                war_weg     INTEGER NOT NULL DEFAULT 0,
                zuletzt_at  INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def _hole(conn, user_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM premium_notice WHERE user_id = ?", (str(user_id),)
    ).fetchone()


def zustand(user_id: str, hat_premium: bool) -> dict[str, Any]:
    """Soll das Fenster erscheinen -- und in welcher Fassung?

    Nebenwirkung mit Absicht: ein Entzug wird hier festgehalten. Diese
    Funktion laeuft bei jedem Seitenaufruf, und das ist der einzige
    Zeitpunkt, an dem beides bekannt ist -- der gespeicherte Stand und
    ob gerade Premium besteht.
    """
    ensure()
    user_id = str(user_id)

    with _connect() as conn:
        row = _hole(conn, user_id)

        if not hat_premium:
            # Kein Premium: nichts zeigen. Aber merken, dass es weg
            # ist -- sonst wuesste der naechste Aufruf nicht, dass es
            # dazwischen einen Entzug gab.
            if row is not None and not row["war_weg"]:
                conn.execute(
                    "UPDATE premium_notice SET war_weg = 1, zuletzt_at = ? "
                    "WHERE user_id = ?",
                    (int(time.time()), user_id),
                )
            return {"zeigen": False, "rueckkehr": False}

        if row is None:
            # Erstes Premium ueberhaupt.
            conn.execute(
                "INSERT INTO premium_notice (user_id, epoche, gesehen, war_weg, "
                "zuletzt_at) VALUES (?, 1, 0, 0, ?)",
                (user_id, int(time.time())),
            )
            return {"zeigen": True, "rueckkehr": False}

        if row["war_weg"]:
            # Premium war weg und ist wieder da: neuer Abschnitt.
            conn.execute(
                "UPDATE premium_notice SET epoche = epoche + 1, gesehen = 0, "
                "war_weg = 0, zuletzt_at = ? WHERE user_id = ?",
                (int(time.time()), user_id),
            )
            return {"zeigen": True, "rueckkehr": True}

        # Unveraendert: nur zeigen, wenn noch nicht gesehen.
        return {
            "zeigen": not bool(row["gesehen"]),
            # Ab dem zweiten Abschnitt ist es eine Rueckkehr.
            "rueckkehr": int(row["epoche"] or 1) > 1,
        }


def als_gesehen(user_id: str) -> None:
    """Der Nutzer hat „Verstanden" gedrueckt."""
    ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO premium_notice (user_id, epoche, gesehen, war_weg, "
            "zuletzt_at) VALUES (?, 1, 1, 0, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET gesehen = 1, zuletzt_at = ?",
            (str(user_id), int(time.time()), int(time.time())),
        )


def zuruecksetzen(user_id: str) -> None:
    """Dafuer sorgen, dass das Fenster (wieder) erscheint.

    Aufgerufen beim Entzug -- und bei der Aufnahme in die Beta, damit
    der Hinweis auf jeden Fall kommt.

    ── Der Fehler, den `nur_wenn_bekannt` behebt ───────────────────

    Vorher setzte diese Funktion immer `war_weg = 1`. Bei der ERSTEN
    Aufnahme legte sie damit eine Zeile an, die aussah wie „hatte
    schon einmal Premium und hat es verloren". Der naechste Aufruf
    von `zustand()` erhoehte daraufhin die Epoche und meldete
    `rueckkehr: True` -- im Fenster stand „Willkommen zurück" bei
    jemandem, der zum ersten Mal Premium bekommt.

    Nachgemessen: nach `zustand(u, False)` + `zuruecksetzen(u)` stand
    epoche=2, obwohl es nie einen Entzug gab.

    Deshalb wird eine noch nicht vorhandene Zeile jetzt als
    Erst-Vergabe angelegt: `war_weg = 0`. Nur wer schon bekannt ist,
    kann zurueckkehren.
    """
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        bekannt = _hole(conn, str(user_id)) is not None
        if bekannt:
            conn.execute(
                "UPDATE premium_notice SET war_weg = 1, zuletzt_at = ? "
                "WHERE user_id = ?",
                (jetzt, str(user_id)),
            )
        else:
            # Erste Vergabe: kein Entzug in der Vergangenheit.
            conn.execute(
                "INSERT INTO premium_notice (user_id, epoche, gesehen, "
                "war_weg, zuletzt_at) VALUES (?, 1, 0, 0, ?)",
                (str(user_id), jetzt),
            )
