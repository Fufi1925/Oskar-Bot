"""
Warnungen -- eine Wahrheit fuer Bot und Dashboard.

Vorher gab es zwei Haelften, die nichts voneinander wussten:

  * ``cogs/moderation/warn.py`` kannte nur die Tabelle ``warns``. Die
    enthaelt eine einzige Zahl pro Mitglied. Der Grund einer Warnung
    stand nur in der DM an den Betroffenen und war danach weg.
  * ``api/routes/moderation.py`` schrieb zusaetzlich nach ``warn_log``
    -- mit Grund, Moderator und Zeitpunkt -- und las beim Anzeigen
    beide Tabellen.

Beides zeigte auf dieselbe Datei ``db/warn.db``, und daraus folgten
zwei Fehler, die sich im Betrieb widersprachen:

  1. ``>warn @user Spam`` erzeugte nur den Zaehler. Das Dashboard zeigte
     "3 Warnungen" ohne einen einzigen Grund -- die Angabe, auf die es
     bei einer Warnung eigentlich ankommt.
  2. ``>clearwarns @user`` setzte den Zaehler auf 0, ruehrte ``warn_log``
     aber nicht an. Die Eintraege blieben auf ``active = 1``, also zeigte
     das Dashboard geloeschte Warnungen weiter an.

Der naheliegende Fix waere gewesen, die fehlenden Zeilen im Cog
nachzutragen. Das haette genau bis zur naechsten Aenderung gehalten:
zwei Stellen, die dasselbe tun muessen, laufen wieder auseinander.
Deshalb steht das Schreiben jetzt hier, und beide Seiten rufen dieselbe
Funktion auf. Zaehler und Protokoll koennen sich nicht mehr
widersprechen, weil sie in derselben Transaktion geschrieben werden.

Der Zaehler bleibt trotzdem erhalten. Er liesse sich aus ``warn_log``
errechnen, aber dann waeren alle Warnungen weg, die vor dieser Aenderung
vergeben wurden -- die existieren nur als Zahl. ``count_of()`` nimmt
deshalb den hoeheren der beiden Werte.
"""

from __future__ import annotations

import time

from utils import db_paths

WARN_DB = "db/warn.db"


async def ensure_schema(db) -> None:
    """Beide Tabellen anlegen, falls sie fehlen."""
    await db.execute(
        "CREATE TABLE IF NOT EXISTS warns ("
        " guild_id INTEGER, user_id INTEGER, warns INTEGER,"
        " PRIMARY KEY (guild_id, user_id))"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS warn_log ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " moderator_id INTEGER,"
        " reason TEXT DEFAULT '',"
        " created_at INTEGER NOT NULL,"
        " active INTEGER DEFAULT 1)"
    )
    # Ohne diesen Index geht jede Abfrage ueber die ganze Tabelle. Bei
    # einem Server mit langer Historie ist das der Unterschied zwischen
    # sofort und spuerbar.
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_warn_log_guild_user"
        " ON warn_log (guild_id, user_id, active)"
    )
    await db.commit()


async def add(
    guild_id: int,
    user_id: int,
    *,
    reason: str = "",
    moderator_id: int | None = None,
) -> int:
    """
    Eine Warnung eintragen -- Zaehler und Protokoll zusammen.

    Gibt die neue Gesamtzahl zurueck.
    """
    now = int(time.time())
    reason = (reason or "").strip()[:500]

    async with db_paths.connect(WARN_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO warn_log"
            " (guild_id, user_id, moderator_id, reason, created_at, active)"
            " VALUES (?, ?, ?, ?, ?, 1)",
            (guild_id, user_id, moderator_id, reason, now),
        )
        await db.execute(
            "INSERT OR IGNORE INTO warns (guild_id, user_id, warns) VALUES (?, ?, 0)",
            (guild_id, user_id),
        )
        await db.execute(
            "UPDATE warns SET warns = warns + 1 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return await _count(db, guild_id, user_id)


async def clear(guild_id: int, user_id: int) -> int:
    """
    Alle Warnungen eines Mitglieds zuruecknehmen.

    Die Protokolleintraege werden auf ``active = 0`` gesetzt, nicht
    geloescht: wer wann warum gewarnt wurde, bleibt nachvollziehbar --
    es zaehlt nur nicht mehr. Gibt zurueck, wie viele Eintraege
    betroffen waren.
    """
    async with db_paths.connect(WARN_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE warn_log SET active = 0"
            " WHERE guild_id = ? AND user_id = ? AND active = 1",
            (guild_id, user_id),
        )
        betroffen = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        await db.execute(
            "UPDATE warns SET warns = 0 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
    return betroffen


async def remove_one(guild_id: int, entry_id: int) -> tuple[int, int] | None:
    """
    Eine einzelne Warnung zuruecknehmen.

    Gibt ``(user_id, neuer_zaehler)`` zurueck oder ``None``, wenn es den
    Eintrag nicht gibt.
    """
    async with db_paths.connect(WARN_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id FROM warn_log WHERE id = ? AND guild_id = ? AND active = 1",
            (entry_id, guild_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None

        user_id = int(row[0])
        await db.execute("UPDATE warn_log SET active = 0 WHERE id = ?", (entry_id,))
        await db.execute(
            "UPDATE warns SET warns = MAX(0, warns - 1)"
            " WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return user_id, await _count(db, guild_id, user_id)


async def count_of(guild_id: int, user_id: int) -> int:
    """Wie viele Warnungen zaehlen aktuell fuer dieses Mitglied."""
    async with db_paths.connect(WARN_DB) as db:
        await ensure_schema(db)
        return await _count(db, guild_id, user_id)


async def history(guild_id: int, user_id: int, limit: int = 50) -> list[dict]:
    """Die aktiven Warnungen eines Mitglieds, neueste zuerst."""
    async with db_paths.connect(WARN_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id, moderator_id, reason, created_at FROM warn_log"
            " WHERE guild_id = ? AND user_id = ? AND active = 1"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            (guild_id, user_id, max(1, min(limit, 200))),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": int(r[0]),
            "moderator_id": int(r[1]) if r[1] else None,
            "reason": r[2] or "",
            "created_at": int(r[3] or 0),
        }
        for r in rows
    ]


async def _count(db, guild_id: int, user_id: int) -> int:
    """
    Der Zaehler -- der hoehere von Tabelle und Protokoll.

    Warnungen aus der Zeit vor dieser Datei stehen nur im Zaehler, es
    gibt keine Protokollzeile dazu. Wuerde hier nur ``warn_log``
    gezaehlt, faenden alte Warnungen still unter den Tisch. Umgekehrt
    kann der Zaehler zu niedrig sein, wenn jemand direkt in der
    Datenbank aufgeraeumt hat. Das Maximum ist in beiden Faellen die
    Angabe, die niemanden ueberrascht.
    """
    async with db.execute(
        "SELECT warns FROM warns WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    zaehler = int(row[0]) if row and row[0] else 0

    async with db.execute(
        "SELECT COUNT(*) FROM warn_log"
        " WHERE guild_id = ? AND user_id = ? AND active = 1",
        (guild_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    protokoll = int(row[0]) if row and row[0] else 0

    return max(zaehler, protokoll)
