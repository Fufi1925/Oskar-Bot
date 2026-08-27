"""
Das Support-Server-Fenster: „Tritt unserem Discord bei."

Wer sich am Dashboard anmeldet, bekommt es zu sehen -- danach sieben
Tage Ruhe, dann wieder. Fuer jeden, nicht nur fuer Premium-Konten.

Warum ein Abstand und nicht einmalig
------------------------------------
Einmalig verpufft: wer es in der ersten Woche wegklickt, sieht es nie
wieder und tritt nie bei. Bei jedem Aufruf waere es eine Zumutung.
Sieben Tage sind der Abstand, bei dem es auffaellt, ohne zu nerven --
ausdrueckliche Vorgabe.

Warum das serverseitig steht und nicht im Cookie
------------------------------------------------
Ein Cookie haengt am Browser. Wer das Dashboard am Telefon und am
Rechner oeffnet, saehe es zweimal; wer die Cookies loescht, jedes Mal
neu. Genau daran ist das Cookie-Banner nicht schuld -- das MUSS im
Browser stehen. Diese Frage haengt aber am Konto.

Warum nicht geprueft wird, ob jemand schon im Server ist
--------------------------------------------------------
Das ginge ueber die Discord-API (`/users/@me/guilds`), kostet aber
einen Aufruf bei jedem Seitenaufruf und ein weiteres Token-Scope. Wer
schon drin ist, klickt „Nein danke" und hat sieben Tage Ruhe -- das
ist billiger als die Abfrage.

Speicher
--------
`db/support_notice.db`. Braucht ein Railway-Volume, sonst sieht jeder
das Fenster nach jedem Deploy erneut.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "support_notice.db")

#: Wie lange Ruhe ist, nachdem jemand das Fenster weggeklickt hat.
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
            CREATE TABLE IF NOT EXISTS support_notice (
                user_id      TEXT PRIMARY KEY,
                gesehen_at   INTEGER NOT NULL DEFAULT 0,
                beigetreten  INTEGER NOT NULL DEFAULT 0,
                mal_gezeigt  INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def zustand(user_id: str) -> dict[str, Any]:
    """Soll das Fenster erscheinen?

    Reine Abfrage, ohne Nebenwirkung: gezaehlt wird erst, wenn das
    Fenster wirklich weggeklickt wurde. Wer die Seite dreimal
    neulaedt, soll es dreimal sehen und nicht nach dem ersten Laden
    sieben Tage Ruhe haben, ohne es gelesen zu haben.
    """
    ensure()
    user_id = str(user_id)

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM support_notice WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row is None:
        # Noch nie gesehen.
        return {
            "zeigen": True,
            "abstand_tage": ABSTAND_TAGE,
            "beigetreten": False,
        }

    # Wer auf „Ja, beitreten" gedrueckt hat, bekommt es nicht mehr.
    #
    # Ob er wirklich beigetreten ist, wissen wir nicht -- aber er hat
    # den Weg gesehen und den Link geoeffnet. Ihn weiter zu fragen
    # waere aufdringlich.
    if row["beigetreten"]:
        return {"zeigen": False, "abstand_tage": ABSTAND_TAGE,
                "beigetreten": True}

    zuletzt = int(row["gesehen_at"] or 0)
    faellig = (int(time.time()) - zuletzt) >= ABSTAND_SEKUNDEN

    return {
        "zeigen": faellig,
        "abstand_tage": ABSTAND_TAGE,
        "beigetreten": False,
    }


def weggeklickt(user_id: str, *, beigetreten: bool = False) -> None:
    """Das Fenster wurde geschlossen -- ab jetzt sieben Tage Ruhe.

    `beigetreten=True` bei „Ja, beitreten": dann kommt es gar nicht
    mehr wieder.
    """
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO support_notice (user_id, gesehen_at, beigetreten, "
            "mal_gezeigt) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET gesehen_at = ?, "
            "beigetreten = MAX(beigetreten, ?), "
            "mal_gezeigt = mal_gezeigt + 1",
            (str(user_id), jetzt, int(bool(beigetreten)),
             jetzt, int(bool(beigetreten))),
        )


def zuruecksetzen(user_id: str) -> None:
    """Das Fenster wieder faellig machen -- fuer Tests und Support."""
    ensure()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM support_notice WHERE user_id = ?", (str(user_id),)
        )


def zahlen() -> dict[str, int]:
    """Wie oft wurde es gezeigt, wie oft fuehrte es zum Beitritt?"""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS konten, "
            "COALESCE(SUM(mal_gezeigt), 0) AS gezeigt, "
            "COALESCE(SUM(beigetreten), 0) AS beigetreten "
            "FROM support_notice"
        ).fetchone()
    return {
        "konten": int(row["konten"] or 0),
        "gezeigt": int(row["gezeigt"] or 0),
        "beigetreten": int(row["beigetreten"] or 0),
    }
