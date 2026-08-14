# ╔══════════════════════════════════════════════════════════════════╗
# ║   Probewoche                                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Die 7-Tage-Probewoche für Premium.

Woher sie kommt
---------------
Der Template-Bot vergibt persönliche Keys, die genau sieben Tage
gelten. Beim Einlösen meldet er das hierher:

    POST /api/v1/premium/grant
    X-Partner-Token: <PREMIUM_PARTNER_TOKEN>
    {user_id, guild_id, expires_at, duration_days}

Ohne diese Meldung wüsste der University Bot nichts davon — er kennt
nur seine eigenen gekauften Keys. Im Dashboard stünde dann „kein
Premium“, obwohl der Nutzer welches hat.

Die eine Regel, die den Aufbau erklärt
--------------------------------------
**Eine Probewoche pro Konto, und zwar für immer.** Deshalb wird die
Zeile beim Ablauf *nicht* gelöscht: sie ist der Beleg dafür, dass
dieses Konto seine Probewoche schon hatte. Ein Aufräumlauf, der alte
Zeilen entfernt, würde die Sperre stillschweigend aufheben — und
plötzlich hätte jeder unbegrenzt Probewochen.

Wer eine zweite braucht (Support-Fall, Fehler bei der ersten), bekommt
sie vom Team: ``reset()`` im Admin-Bereich macht den Weg wieder frei.

Was hier NICHT passiert
-----------------------
Premium selbst wird nicht hier entschieden. ``premium_store.status()``
ist die eine Stelle, die „hat dieser Nutzer Premium?“ beantwortet;
diese Datei liefert ihr nur einen weiteren Grund. Zwei Stellen, die
dieselbe Frage beantworten, laufen auseinander.

Speicher
--------
``db/premium_trial.db``. Braucht ein Railway-Volume — ohne das ist
nach jedem Deploy jede Probewoche vergessen, und dann kann sich jeder
beliebig oft eine neue holen.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "premium_trial.db")

#: Wie lange die Probewoche läuft. Der Template-Bot schickt sein eigenes
#: `expires_at` mit; dieser Wert greift nur, wenn keins ankommt.
TRIAL_DAYS = 7

# Die Spalten stehen **einmal** hier. CREATE TABLE und die Nachrüstung
# fehlender Spalten leiten sich beide daraus ab.
#
# Zwei handgepflegte Listen laufen auseinander -- bei `team_update` ist
# genau das passiert: `updated_at` fehlte in der zweiten, und auf einer
# bestehenden Installation kam „no such column".
COLUMNS: tuple[tuple[str, str], ...] = (
    ("user_id", "TEXT PRIMARY KEY"),
    ("guild_id", "TEXT"),
    ("product", "TEXT NOT NULL DEFAULT 'template_bot'"),
    ("granted_at", "INTEGER NOT NULL DEFAULT 0"),
    ("expires_at", "INTEGER NOT NULL DEFAULT 0"),
    ("duration_days", "INTEGER NOT NULL DEFAULT 7"),
    # Wie oft dieses Konto schon eine Probewoche hatte. Steht hier und
    # nicht als Zeilenzahl: die Zeile wird beim Zurücksetzen
    # überschrieben, nicht vervielfacht.
    ("times_granted", "INTEGER NOT NULL DEFAULT 1"),
    # Wer zurückgesetzt hat und wann -- sonst lässt sich später nicht
    # sagen, warum jemand zwei Probewochen hatte.
    ("reset_by", "TEXT DEFAULT ''"),
    ("reset_at", "INTEGER NOT NULL DEFAULT 0"),
    # Ob die Ablauf-Nachricht schon raus ist. Ohne dieses Feld schickt
    # der Hintergrundlauf sie bei jedem Durchgang erneut.
    ("expiry_dm_sent", "INTEGER NOT NULL DEFAULT 0"),
)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    """Tabelle anlegen und fehlende Spalten nachrüsten."""
    spalten = ", ".join(f"{name} {typ}" for name, typ in COLUMNS)
    with _connect() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS premium_trials ({spalten})")

        # CREATE TABLE IF NOT EXISTS ändert an einer bestehenden Tabelle
        # nichts. Kommt später eine Spalte dazu, fehlt sie auf jeder
        # laufenden Installation -- und jede Abfrage scheitert.
        vorhanden = {
            row[1] for row in conn.execute("PRAGMA table_info(premium_trials)")
        }
        for name, typ in COLUMNS:
            if name in vorhanden:
                continue
            # PRIMARY KEY lässt sich per ALTER TABLE nicht nachrüsten --
            # aber die Spalte gibt es dann ohnehin, weil sie im CREATE
            # steht. NOT NULL braucht einen Vorgabewert.
            nachtrag = typ.replace("PRIMARY KEY", "").strip()
            if "DEFAULT" not in nachtrag.upper():
                nachtrag = nachtrag.replace("NOT NULL", "").strip()
            conn.execute(
                f"ALTER TABLE premium_trials ADD COLUMN {name} {nachtrag}"
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS premium_trials_expiry "
            "ON premium_trials (expires_at)"
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    jetzt = int(time.time())
    ablauf = int(row["expires_at"] or 0)
    return {
        "user_id": str(row["user_id"]),
        "guild_id": str(row["guild_id"]) if row["guild_id"] else None,
        "product": row["product"] or "template_bot",
        "granted_at": int(row["granted_at"] or 0),
        "expires_at": ablauf,
        "duration_days": int(row["duration_days"] or TRIAL_DAYS),
        "times_granted": int(row["times_granted"] or 1),
        "reset_by": row["reset_by"] or "",
        "reset_at": int(row["reset_at"] or 0),
        "expiry_dm_sent": bool(row["expiry_dm_sent"]),
        # Abgeleitet, nicht gespeichert: ein gespeicherter Zustand wäre
        # in der Sekunde nach dem Schreiben schon falsch.
        "active": ablauf > jetzt,
        "seconds_left": max(0, ablauf - jetzt),
    }


def get(user_id: int | str) -> Optional[dict[str, Any]]:
    """Die Probewoche eines Kontos -- auch die abgelaufene."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM premium_trials WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return _row_to_dict(row) if row else None


def is_active(user_id: int | str) -> bool:
    """Läuft die Probewoche gerade?"""
    eintrag = get(user_id)
    return bool(eintrag and eintrag["active"])


def had_trial(user_id: int | str) -> bool:
    """Hatte dieses Konto **jemals** eine Probewoche?

    Das ist die Frage, die über „noch eine“ entscheidet -- nicht
    ``is_active``. Eine abgelaufene Probewoche zählt genauso.
    """
    return get(user_id) is not None


def grant(
    user_id: int | str,
    *,
    guild_id: int | str | None = None,
    expires_at: int | float | None = None,
    duration_days: int = TRIAL_DAYS,
    product: str = "template_bot",
) -> dict[str, Any]:
    """Eine Probewoche eintragen.

    Gibt ``{"ok": False, "error": "already_used"}`` zurück, wenn das
    Konto schon eine hatte. Der Aufrufer -- der Template-Bot -- kann
    dem Nutzer dann sagen, dass die Probewoche verbraucht ist, statt
    ihm eine zweite zu geben.

    **Nicht** ``INSERT OR REPLACE``: das würde die Sperre bei jeder
    Meldung stillschweigend aufheben.
    """
    ensure()
    jetzt = int(time.time())

    vorhanden = get(user_id)
    if vorhanden is not None:
        return {
            "ok": False,
            "error": "already_used",
            "trial": vorhanden,
        }

    ablauf = int(expires_at) if expires_at else jetzt + duration_days * 86400
    tage = int(duration_days or TRIAL_DAYS)

    with _connect() as conn:
        conn.execute(
            "INSERT INTO premium_trials"
            " (user_id, guild_id, product, granted_at, expires_at,"
            "  duration_days, times_granted, expiry_dm_sent)"
            " VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
            (
                str(user_id),
                str(guild_id) if guild_id else None,
                product,
                jetzt,
                ablauf,
                tage,
            ),
        )

    return {"ok": True, "trial": get(user_id)}


def reset(user_id: int | str, actor: str = "") -> bool:
    """Die Probewoche freigeben -- das Konto darf noch einmal.

    Der Zähler bleibt stehen und wächst weiter: so ist später zu
    sehen, dass jemand seine dritte Probewoche hat, und wer sie
    freigegeben hat.
    """
    ensure()
    vorhanden = get(user_id)
    if vorhanden is None:
        return False

    with _connect() as conn:
        conn.execute(
            "DELETE FROM premium_trials WHERE user_id = ?", (str(user_id),)
        )
        # Der Zähler überlebt die Löschung: er wandert in die nächste
        # Zeile, sobald eine neue Probewoche vergeben wird. Damit das
        # geht, wird er hier zwischengeparkt.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS premium_trial_resets ("
            " user_id TEXT PRIMARY KEY,"
            " times INTEGER NOT NULL DEFAULT 0,"
            " last_by TEXT DEFAULT '',"
            " last_at INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO premium_trial_resets (user_id, times, last_by, last_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            "   times = times + 1, last_by = excluded.last_by,"
            "   last_at = excluded.last_at",
            (str(user_id), vorhanden["times_granted"], str(actor), int(time.time())),
        )
    return True


def revoke(user_id: int | str) -> bool:
    """Eine laufende Probewoche sofort beenden.

    Die Zeile bleibt -- das Konto hat seine Probewoche verbraucht. Nur
    das Ablaufdatum wird auf jetzt gesetzt.
    """
    ensure()
    if get(user_id) is None:
        return False
    with _connect() as conn:
        conn.execute(
            "UPDATE premium_trials SET expires_at = ? WHERE user_id = ?",
            (int(time.time()), str(user_id)),
        )
    return True


def mark_dm_sent(user_id: int | str) -> None:
    """Merken, dass die Ablauf-Nachricht raus ist."""
    ensure()
    with _connect() as conn:
        conn.execute(
            "UPDATE premium_trials SET expiry_dm_sent = 1 WHERE user_id = ?",
            (str(user_id),),
        )


def due_for_expiry_dm() -> list[dict[str, Any]]:
    """Abgelaufene Probewochen, deren Nachricht noch aussteht."""
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM premium_trials"
            " WHERE expires_at <= ? AND expiry_dm_sent = 0"
            " ORDER BY expires_at",
            (jetzt,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all(limit: int = 200) -> list[dict[str, Any]]:
    """Alle Probewochen für den Admin-Bereich, neueste zuerst."""
    ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM premium_trials ORDER BY granted_at DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def stats() -> dict[str, int]:
    """Wie viele Probewochen laufen, wie viele sind vorbei."""
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS gesamt,"
            " SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) AS aktiv"
            " FROM premium_trials",
            (jetzt,),
        ).fetchone()
    gesamt = int(row["gesamt"] or 0)
    aktiv = int(row["aktiv"] or 0)
    return {"total": gesamt, "active": aktiv, "expired": gesamt - aktiv}
