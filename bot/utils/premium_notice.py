"""
Wer hat den Premium-Hinweis schon gesehen?

Das Fenster
-----------
Wer Premium hat und die Seite betritt, bekommt ein goldenes Fenster:
„Denk dran — du hast Premium." Danach kommt es **alle sieben Tage**
wieder.

Vorher erschien es genau einmal und nie wieder. So gewuenscht
geaendert: es soll an Premium erinnern, ohne bei jedem Seitenaufruf im
Weg zu stehen. Sieben Tage sind der Abstand, bei dem es auffaellt,
aber nicht nervt.

Wird das Premium entzogen und spaeter neu vergeben, erscheint es
sofort -- diesmal als „Willkommen zurück".

Warum das serverseitig steht und nicht im Cookie
------------------------------------------------
Ein Cookie haengt am Browser. Wer das Dashboard am Telefon und am
Rechner oeffnet, saehe das Fenster zweimal; wer die Cookies loescht,
jedes Mal neu. Und der entscheidende Fall liesse sich damit gar nicht
loesen: „nach einem Entzug wieder zeigen" muss wissen, dass es
dazwischen einen Entzug gab.

Deshalb steht hier pro Konto, welchen *Abschnitt* jemand gesehen hat
und **wann zuletzt**. Ein Abschnitt beginnt, wenn Premium vergeben
wird, und endet mit dem Entzug. Innerhalb eines Abschnitts entscheidet
der Zeitpunkt: liegt er laenger als :data:`ABSTAND_TAGE` zurueck,
kommt das Fenster wieder.

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

#: Wie lange Ruhe ist, nachdem jemand „Verstanden" gedrueckt hat.
#:
#: Ausdrueckliche Vorgabe: das Fenster soll immer wieder kommen, aber
#: hoechstens alle sieben Tage. Bei jedem Seitenaufruf waere es eine
#: Zumutung, einmalig verpufft der Hinweis.
ABSTAND_TAGE = 7
ABSTAND_SEKUNDEN = ABSTAND_TAGE * 24 * 3600


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

        # Wann wurde zuletzt weggeklickt?
        #
        # `zuletzt_at` taugt dafuer nicht: es wird bei JEDER Aenderung
        # gesetzt, auch beim Entzug. Fuer den Sieben-Tage-Abstand
        # braucht es den Zeitpunkt des Wegklickens und sonst nichts.
        #
        # `CREATE TABLE IF NOT EXISTS` aendert an einer bestehenden
        # Tabelle NICHTS -- die Spalte muss per ALTER nachgezogen
        # werden, sonst kommt auf jeder bestehenden Installation
        # „no such column".
        try:
            conn.execute(
                "ALTER TABLE premium_notice "
                "ADD COLUMN gesehen_at INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:  # noqa: BLE001 - Spalte existiert bereits
            pass


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
            return {"zeigen": False, "rueckkehr": False,
                    "abstand_tage": ABSTAND_TAGE}

        if row is None:
            # Erstes Premium ueberhaupt.
            conn.execute(
                "INSERT INTO premium_notice (user_id, epoche, gesehen, war_weg, "
                "zuletzt_at) VALUES (?, 1, 0, 0, ?)",
                (user_id, int(time.time())),
            )
            return {"zeigen": True, "rueckkehr": False,
                    "abstand_tage": ABSTAND_TAGE}

        if row["war_weg"]:
            # Premium war weg und ist wieder da: neuer Abschnitt.
            # `gesehen_at` mit zuruecksetzen: sonst haelt der
            # Sieben-Tage-Abstand aus dem vorigen Abschnitt das
            # „Willkommen zurück" auf.
            conn.execute(
                "UPDATE premium_notice SET epoche = epoche + 1, gesehen = 0, "
                "war_weg = 0, zuletzt_at = ?, gesehen_at = 0 "
                "WHERE user_id = ?",
                (int(time.time()), user_id),
            )
            return {"zeigen": True, "rueckkehr": True,
                    "abstand_tage": ABSTAND_TAGE}

        # Unveraendert: nach sieben Tagen wieder zeigen.
        #
        # Frueher stand hier `not bool(row["gesehen"])` -- einmal
        # weggeklickt, nie wieder. Jetzt entscheidet der Abstand.
        if not row["gesehen"]:
            faellig = True
        else:
            # `gesehen_at` kann 0 sein: bei Zeilen aus der Zeit vor
            # dieser Spalte. Dann ist das Fenster faellig -- lieber
            # einmal zu viel als eine Zeile, die nie wieder meldet.
            zuletzt = int(row["gesehen_at"] or 0)
            faellig = (int(time.time()) - zuletzt) >= ABSTAND_SEKUNDEN

        return {
            "zeigen": faellig,
            # Ab dem zweiten Abschnitt ist es eine Rueckkehr.
            "rueckkehr": int(row["epoche"] or 1) > 1,
            # Damit die Oberflaeche den Abstand nicht doppelt kennt.
            "abstand_tage": ABSTAND_TAGE,
        }


def als_gesehen(user_id: str) -> None:
    """Der Nutzer hat „Verstanden" gedrueckt.

    Haelt den ZEITPUNKT fest, nicht nur das Ja/Nein: davon haengt ab,
    wann das Fenster wieder faellig ist.
    """
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO premium_notice (user_id, epoche, gesehen, war_weg, "
            "zuletzt_at, gesehen_at) VALUES (?, 1, 1, 0, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET gesehen = 1, "
            "zuletzt_at = ?, gesehen_at = ?",
            (str(user_id), jetzt, jetzt, jetzt, jetzt),
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
