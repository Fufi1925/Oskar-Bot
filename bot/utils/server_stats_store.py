"""Persistente Einstellungen für die Mitgliederzähler eines Servers.

Jeder aktivierte Zähler besitzt genau einen vom Bot verwalteten
Sprachkanal. Die Kanal-IDs werden gespeichert, damit deaktivierte Zähler
nur ihre eigenen Kanäle entfernen und niemals einen fremden Kanal.
"""

from __future__ import annotations

import aiosqlite

DB_PATH = "db/server_stats.db"
KINDS = ("humans", "bots", "total")
DEFAULTS = {
    "humans_enabled": False,
    "bots_enabled": False,
    "total_enabled": False,
    "humans_channel_id": None,
    "bots_channel_id": None,
    "total_channel_id": None,
}


async def _ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS server_stats (
            guild_id INTEGER PRIMARY KEY,
            humans_enabled INTEGER NOT NULL DEFAULT 0,
            bots_enabled INTEGER NOT NULL DEFAULT 0,
            total_enabled INTEGER NOT NULL DEFAULT 0,
            humans_channel_id INTEGER,
            bots_channel_id INTEGER,
            total_channel_id INTEGER
        )
        """
    )
    await db.commit()


async def get(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure(db)
        async with db.execute(
            "SELECT * FROM server_stats WHERE guild_id = ?", (int(guild_id),)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return dict(DEFAULTS)

    result = dict(DEFAULTS)
    for kind in KINDS:
        result[f"{kind}_enabled"] = bool(row[f"{kind}_enabled"])
        channel_id = row[f"{kind}_channel_id"]
        result[f"{kind}_channel_id"] = int(channel_id) if channel_id else None
    return result


async def save(guild_id: int, updates: dict) -> dict:
    """Speichert nur übermittelte Schalter; Kanal-IDs bleiben erhalten."""
    current = await get(guild_id)
    for kind in KINDS:
        key = f"{kind}_enabled"
        if key in updates:
            current[key] = bool(updates[key])

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        await db.execute(
            """
            INSERT INTO server_stats (
                guild_id, humans_enabled, bots_enabled, total_enabled,
                humans_channel_id, bots_channel_id, total_channel_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                humans_enabled = excluded.humans_enabled,
                bots_enabled = excluded.bots_enabled,
                total_enabled = excluded.total_enabled
            """,
            (
                int(guild_id),
                int(current["humans_enabled"]),
                int(current["bots_enabled"]),
                int(current["total_enabled"]),
                current["humans_channel_id"],
                current["bots_channel_id"],
                current["total_channel_id"],
            ),
        )
        await db.commit()
    return await get(guild_id)


async def set_channel(guild_id: int, kind: str, channel_id: int | None) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unbekannter Server-Stats-Typ: {kind}")
    # Die Zeile muss existieren, bevor nur eine Kanal-ID aktualisiert wird.
    current = await get(guild_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        await db.execute(
            """
            INSERT OR IGNORE INTO server_stats (
                guild_id, humans_enabled, bots_enabled, total_enabled
            ) VALUES (?, ?, ?, ?)
            """,
            (
                int(guild_id),
                int(current["humans_enabled"]),
                int(current["bots_enabled"]),
                int(current["total_enabled"]),
            ),
        )
        await db.execute(
            f"UPDATE server_stats SET {kind}_channel_id = ? WHERE guild_id = ?",
            (int(channel_id) if channel_id else None, int(guild_id)),
        )
        await db.commit()


async def enabled_guild_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        async with db.execute(
            """
            SELECT guild_id FROM server_stats
            WHERE humans_enabled = 1 OR bots_enabled = 1 OR total_enabled = 1
            """
        ) as cursor:
            return [int(row[0]) for row in await cursor.fetchall()]
