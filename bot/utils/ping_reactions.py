"""
Wer beim Erwaehnen welche Reaktion bekommt.

Bisher stand das fest im Code (``cogs/events/react.py``): die beiden
Besitzer, mit vier beziehungsweise drei Emojis. Wer jemanden dazunehmen
wollte, musste die Datei aendern und neu ausliefern.

Hier liegt dieselbe Regel als Liste, die sich im Admin-Panel pflegen
laesst. Die fest verdrahteten Besitzer bleiben unangetastet -- sie
kommen weiterhin aus ``react.py``, und diese Liste wirkt zusaetzlich.
So kann ein Fehler im Dashboard die eigene Kennzeichnung nicht
versehentlich abschalten.

Nur eigene Emojis
-----------------
Ausdruecklich so gewuenscht, und es passt zur Sache: die Auswahl im
Dashboard zeigt die rund 140 Emojis des Bots. Ein Unicode-Herz koennte
jeder Server selbst setzen; interessant sind die eigenen.

Geprueft wird das hier und nicht nur im Browser. ``PATTERN`` verlangt
die vollstaendige Discord-Schreibweise ``<:name:id>`` beziehungsweise
``<a:name:id>`` -- alles andere wird abgewiesen, bevor es in der
Datenbank landet.
"""

from __future__ import annotations

import re
import time

import aiosqlite

DB_PATH = "db/ping_reactions.db"

# Die vollstaendige Schreibweise eines Custom-Emojis.
#
# `a` am Anfang heisst animiert. Die ID ist eine Snowflake, also
# mindestens 17 Stellen -- kuerzere Zahlen sind keine gueltigen IDs und
# wuerden von Discord ohnehin abgelehnt.
PATTERN = re.compile(r"^<(a?):([A-Za-z0-9_]{2,32}):(\d{17,20})>$")

# Discord nimmt hoechstens zwanzig verschiedene Reaktionen pro
# Nachricht an. Mehr einzutragen hiesse, dass die letzten stillschweigend
# scheitern -- besser vorher sagen.
MAX_REACTIONS = 20

# Wie viele Eintraege insgesamt. Jede Erwaehnung geht die Liste durch;
# bei tausend Eintraegen waere das bei jeder Nachricht spuerbar.
MAX_ENTRIES = 200


def is_custom_emoji(value: str) -> bool:
    """Ist das ein eigenes Emoji in voller Schreibweise?"""

    return bool(PATTERN.match(str(value or "").strip()))


def emoji_name(value: str) -> str:
    """Der Name aus ``<:name:id>`` -- fuer die Anzeige."""

    match = PATTERN.match(str(value or "").strip())
    return match.group(2) if match else ""


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ping_reactions (
            user_id INTEGER PRIMARY KEY,
            emojis TEXT NOT NULL DEFAULT '',
            note TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            added_by TEXT DEFAULT '',
            added_at REAL DEFAULT 0
        )
        """
    )
    await db.commit()


def _split(raw: str) -> list[str]:
    """Die gespeicherte Zeichenkette zurueck in eine Liste.

    Getrennt wird mit ``\\n``: ein Emoji enthaelt weder Zeilenumbruch
    noch Komma, aber ein Komma waere trotzdem die schlechtere Wahl --
    es kommt in Discord-Namen zwar nicht vor, in kuenftigen Feldern
    aber vielleicht schon.
    """

    return [part for part in str(raw or "").split("\n") if part.strip()]


async def all_entries(db: aiosqlite.Connection) -> list[dict]:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM ping_reactions ORDER BY added_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        {
            "user_id": str(row["user_id"]),
            "emojis": _split(row["emojis"]),
            "note": row["note"] or "",
            "enabled": bool(row["enabled"]),
            "added_by": row["added_by"] or "",
            "added_at": row["added_at"] or 0,
        }
        for row in rows
    ]


async def get(db: aiosqlite.Connection, user_id: int) -> dict | None:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM ping_reactions WHERE user_id = ?", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "user_id": str(row["user_id"]),
        "emojis": _split(row["emojis"]),
        "note": row["note"] or "",
        "enabled": bool(row["enabled"]),
        "added_by": row["added_by"] or "",
        "added_at": row["added_at"] or 0,
    }


class RuleError(ValueError):
    """Die Eingabe taugt nicht -- mit einem Satz, den man lesen kann."""


async def save(
    db: aiosqlite.Connection,
    user_id: int,
    emojis: list[str],
    *,
    note: str = "",
    enabled: bool = True,
    added_by: str = "",
) -> dict:
    """Einen Eintrag anlegen oder aendern.

    Wirft ``RuleError`` mit einer verstaendlichen Begruendung, statt
    still etwas Halbes zu speichern.
    """

    cleaned: list[str] = []
    for entry in emojis or []:
        value = str(entry or "").strip()
        if not value:
            continue
        if not is_custom_emoji(value):
            raise RuleError(
                f"»{value[:40]}« ist kein eigenes Emoji des Bots. "
                "Nimm eines aus der Auswahl."
            )
        # Zweimal dasselbe Emoji nimmt Discord ohnehin nur einmal an.
        if value not in cleaned:
            cleaned.append(value)

    if not cleaned:
        raise RuleError("Wähle mindestens ein Emoji aus.")

    if len(cleaned) > MAX_REACTIONS:
        raise RuleError(
            f"Discord erlaubt höchstens {MAX_REACTIONS} Reaktionen pro "
            f"Nachricht — du hast {len(cleaned)} gewählt."
        )

    existing = await get(db, user_id)
    if existing is None:
        async with db.execute("SELECT COUNT(*) FROM ping_reactions") as cursor:
            (count,) = await cursor.fetchone()
        if count >= MAX_ENTRIES:
            raise RuleError(
                f"Es sind schon {MAX_ENTRIES} Einträge gespeichert. "
                "Lösche erst einen."
            )

    await db.execute(
        """
        INSERT INTO ping_reactions (user_id, emojis, note, enabled, added_by, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            emojis = excluded.emojis,
            note = excluded.note,
            enabled = excluded.enabled
        """,
        (
            int(user_id),
            "\n".join(cleaned),
            str(note or "")[:200],
            1 if enabled else 0,
            str(added_by or "")[:32],
            time.time(),
        ),
    )
    await db.commit()

    result = await get(db, user_id)
    assert result is not None
    return result


async def remove(db: aiosqlite.Connection, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM ping_reactions WHERE user_id = ?", (int(user_id),)
    )
    await db.commit()
    return cursor.rowcount > 0


# --------------------------------------------------------------------- #
#  Der Zwischenspeicher
# --------------------------------------------------------------------- #
#
# `on_message` laeuft bei *jeder* Nachricht auf *jedem* Server. Dort bei
# jedem Aufruf die Datenbank zu fragen waere die teuerste Stelle im
# ganzen Bot -- deshalb liegt die Liste im Arbeitsspeicher und wird nur
# nach einer Aenderung neu geladen.

_cache: dict[int, list[str]] = {}
_loaded = False


async def load(db: aiosqlite.Connection, *, force: bool = False) -> None:
    global _loaded

    if _loaded and not force:
        return

    entries = await all_entries(db)
    _cache.clear()
    for entry in entries:
        if entry["enabled"] and entry["emojis"]:
            _cache[int(entry["user_id"])] = list(entry["emojis"])
    _loaded = True


def reactions_for(user_id: int) -> list[str]:
    """Was dieser Nutzer bekommt. Leer heisst: kein Eintrag."""

    return list(_cache.get(int(user_id), []))


def known_users() -> list[int]:
    return list(_cache)


def reset() -> None:
    """Fuer Tests und beim Entladen."""

    global _loaded
    _cache.clear()
    _loaded = False
