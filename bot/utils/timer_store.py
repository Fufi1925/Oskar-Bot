"""
Laufende Timer -- damit ein Neustart sie nicht verschluckt.

Der Timer-Befehl lief vorher komplett im Arbeitsspeicher: eine
``while True``-Schleife, die alle sechs Sekunden dieselbe Nachricht neu
schrieb. Zwei Dinge folgten daraus.

**Der Neustart.** Railway startet den Container bei jedem Deploy neu.
Die Schleife war dann weg, die Nachricht blieb mit einem eingefrorenen
Zwischenstand stehen und niemand erfuhr, dass da nichts mehr kommt.

**Das Rate-Limit.** Bei den erlaubten 24 Stunden Laufzeit waren das
14.400 Bearbeitungen fuer einen einzigen Timer. Discord erlaubt grob
fuenf Bearbeitungen pro fuenf Sekunden und Kanal -- drei parallele
Timer legten den Kanal lahm.

Beides loest dieselbe Umstellung: die Faelligkeit steht in dieser
Tabelle, und die Nachricht enthaelt Discords eigenen Zeitstempel
(``<t:...:R>``). Den zaehlt der Client des Betrachters selbst herunter,
ohne dass der Bot irgendetwas tut. Aus 14.400 Bearbeitungen werden
**zwei**: eine beim Anlegen, eine beim Ablauf.

Ein Hintergrundlauf schaut alle paar Sekunden nach, was faellig ist. Das
ist dasselbe Muster wie bei den Gewinnspielen in
``cogs/commands/giveaway.py`` -- bewusst, denn es hat sich dort
bewaehrt.
"""

from __future__ import annotations

import time

from utils import db_paths

TIMER_DB = "db/timer.db"


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS timers ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " channel_id INTEGER NOT NULL,"
        " message_id INTEGER,"
        " user_id INTEGER NOT NULL,"
        " title TEXT DEFAULT '',"
        " ends_at INTEGER NOT NULL,"
        " done INTEGER DEFAULT 0)"
    )
    # Der Hintergrundlauf fragt nur nach "faellig und noch offen".
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_timers_due ON timers (done, ends_at)"
    )
    await db.commit()


async def create(
    guild_id: int,
    channel_id: int,
    user_id: int,
    *,
    title: str,
    ends_at: int,
) -> int:
    """Einen Timer vormerken. Gibt die neue ID zurueck."""
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "INSERT INTO timers (guild_id, channel_id, user_id, title, ends_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (guild_id, channel_id, user_id, (title or "")[:100], int(ends_at)),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def attach_message(timer_id: int, message_id: int) -> None:
    """
    Die Nachrichten-ID nachtragen.

    Sie steht erst fest, nachdem die Nachricht gesendet wurde -- der
    Eintrag entsteht aber vorher. Andersherum waere schlimmer: stuerzt
    der Bot zwischen Senden und Speichern ab, gibt es einen Timer, den
    niemand kennt.
    """
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "UPDATE timers SET message_id = ? WHERE id = ?", (message_id, timer_id)
        )
        await db.commit()


async def due(now: int | None = None) -> list[dict]:
    """Alle abgelaufenen, noch nicht abgeschlossenen Timer."""
    jetzt = int(now if now is not None else time.time())
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id, guild_id, channel_id, message_id, user_id, title, ends_at"
            " FROM timers WHERE done = 0 AND ends_at <= ? ORDER BY ends_at",
            (jetzt,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": int(r[0]),
            "guild_id": int(r[1]),
            "channel_id": int(r[2]),
            "message_id": int(r[3]) if r[3] else None,
            "user_id": int(r[4]),
            "title": r[5] or "Timer",
            "ends_at": int(r[6]),
        }
        for r in rows
    ]


async def finish(timer_id: int) -> None:
    """Als erledigt abhaken."""
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        await db.execute("UPDATE timers SET done = 1 WHERE id = ?", (timer_id,))
        await db.commit()


async def active_for(user_id: int, guild_id: int) -> list[dict]:
    """Die laufenden Timer eines Mitglieds -- fuer eine Uebersicht."""
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id, title, ends_at, channel_id FROM timers"
            " WHERE done = 0 AND user_id = ? AND guild_id = ?"
            " ORDER BY ends_at",
            (user_id, guild_id),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": int(r[0]),
            "title": r[1] or "Timer",
            "ends_at": int(r[2]),
            "channel_id": int(r[3]),
        }
        for r in rows
    ]


async def cancel(timer_id: int, user_id: int) -> bool:
    """
    Einen eigenen Timer abbrechen.

    ``user_id`` steht bewusst in der Bedingung: ohne sie koennte jede
    beliebige ID den Timer eines anderen beenden.
    """
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE timers SET done = 1 WHERE id = ? AND user_id = ? AND done = 0",
            (timer_id, user_id),
        )
        await db.commit()
        return bool(cursor.rowcount)


async def cleanup(older_than_days: int = 7) -> int:
    """
    Alte, erledigte Timer wegraeumen.

    Ohne das waechst die Tabelle unbegrenzt. Sieben Tage sind lang
    genug, um noch nachzusehen, was gelaufen ist.
    """
    grenze = int(time.time()) - older_than_days * 86400
    async with db_paths.connect(TIMER_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "DELETE FROM timers WHERE done = 1 AND ends_at < ?", (grenze,)
        )
        await db.commit()
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def parse_duration(text: str) -> int | None:
    """
    ``10``, ``90s``, ``5m``, ``2h``, ``1d`` -- und ``1h30m``.

    Gibt Sekunden zurueck oder ``None``, wenn die Eingabe nicht passt.
    Die alte Fassung las nur das letzte Zeichen aus und warf bei allem
    anderen einen ValueError, den ein nacktes ``except`` verschluckte.
    """
    if not text:
        return None

    text = text.strip().lower().replace(" ", "")
    einheiten = {"s": 1, "m": 60, "h": 3600, "d": 86400}

    # Reine Zahl heisst Sekunden.
    if text.isdigit():
        return int(text)

    import re

    treffer = re.findall(r"(\d+)([smhd])", text)
    if not treffer:
        return None
    # Alles muss aufgegangen sein -- "5x" oder "abc" darf nicht als 0 durchgehen.
    if "".join(f"{z}{e}" for z, e in treffer) != text:
        return None

    return sum(int(zahl) * einheiten[einheit] for zahl, einheit in treffer)


def format_duration(seconds: int) -> str:
    """``3725`` -> ``1 Stunde, 2 Minuten``. Fuer die Bestaetigung."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} Sekunden"

    teile = []
    for name_eins, name_viele, groesse in (
        ("Tag", "Tage", 86400),
        ("Stunde", "Stunden", 3600),
        ("Minute", "Minuten", 60),
    ):
        wert, seconds = divmod(seconds, groesse)
        if wert:
            teile.append(f"{wert} {name_eins if wert == 1 else name_viele}")
    return ", ".join(teile) if teile else "0 Minuten"
