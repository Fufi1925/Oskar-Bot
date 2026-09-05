"""Persistente Einstellungen für die Statistik-Sprachkanäle eines Servers.

Jeder aktivierte Zähler besitzt genau einen vom Bot verwalteten
Sprachkanal. Die Kanal-IDs werden gespeichert, damit deaktivierte Zähler
nur ihre eigenen Kanäle entfernen und niemals einen fremden Kanal.
"""

from __future__ import annotations

import aiosqlite

DB_PATH = "db/server_stats.db"
FREE_KINDS = ("humans", "bots", "boosts")
PREMIUM_KINDS = ("online", "roles", "channels")
KINDS = FREE_KINDS + PREMIUM_KINDS
DEFAULTS = {
    **{f"{kind}_enabled": False for kind in KINDS},
    **{f"{kind}_channel_id": None for kind in KINDS},
}


async def _ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS server_stats (
            guild_id INTEGER PRIMARY KEY,
            humans_enabled INTEGER NOT NULL DEFAULT 0,
            bots_enabled INTEGER NOT NULL DEFAULT 0,
            boosts_enabled INTEGER NOT NULL DEFAULT 0,
            online_enabled INTEGER NOT NULL DEFAULT 0,
            roles_enabled INTEGER NOT NULL DEFAULT 0,
            channels_enabled INTEGER NOT NULL DEFAULT 0,
            humans_channel_id INTEGER,
            bots_channel_id INTEGER,
            boosts_channel_id INTEGER,
            online_channel_id INTEGER,
            roles_channel_id INTEGER,
            channels_channel_id INTEGER
        )
        """
    )

    # Jede neue Statistik lässt sich ohne Datenverlust an eine bereits
    # bestehende Installation anhängen.
    async with db.execute("PRAGMA table_info(server_stats)") as cursor:
        columns = {str(row[1]) for row in await cursor.fetchall()}
    for kind in KINDS:
        enabled = f"{kind}_enabled"
        channel = f"{kind}_channel_id"
        if enabled not in columns:
            await db.execute(
                f"ALTER TABLE server_stats ADD COLUMN {enabled} INTEGER NOT NULL DEFAULT 0"
            )
            columns.add(enabled)
        if channel not in columns:
            await db.execute(f"ALTER TABLE server_stats ADD COLUMN {channel} INTEGER")
            columns.add(channel)

    # Migration der kurzzeitig ausgelieferten Variante mit `total_*`:
    # Der vorhandene Kanal wird zum Boost-Zähler, statt unverwaltet auf
    # dem Server zurückzubleiben.
    if "total_enabled" in columns:
        await db.execute(
            """UPDATE server_stats SET boosts_enabled = total_enabled
               WHERE boosts_enabled = 0 AND total_enabled = 1"""
        )
    if "total_channel_id" in columns:
        await db.execute(
            """UPDATE server_stats SET boosts_channel_id = total_channel_id
               WHERE boosts_channel_id IS NULL AND total_channel_id IS NOT NULL"""
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

    enabled_columns = [f"{kind}_enabled" for kind in KINDS]
    channel_columns = [f"{kind}_channel_id" for kind in KINDS]
    columns = ["guild_id", *enabled_columns, *channel_columns]
    values = [int(guild_id)]
    values.extend(int(current[name]) for name in enabled_columns)
    values.extend(current[name] for name in channel_columns)
    assignments = ", ".join(f"{name} = excluded.{name}" for name in enabled_columns)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        await db.execute(
            f"""
            INSERT INTO server_stats ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(guild_id) DO UPDATE SET {assignments}
            """,
            values,
        )
        await db.commit()
    return await get(guild_id)


async def set_channel(guild_id: int, kind: str, channel_id: int | None) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unbekannter Server-Stats-Typ: {kind}")
    # `save` legt die Zeile an, ohne bestehende Schalter zurückzusetzen.
    await save(guild_id, {})
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        await db.execute(
            f"UPDATE server_stats SET {kind}_channel_id = ? WHERE guild_id = ?",
            (int(channel_id) if channel_id else None, int(guild_id)),
        )
        await db.commit()


async def enabled_guild_ids() -> list[int]:
    where = " OR ".join(f"{kind}_enabled = 1" for kind in KINDS)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        async with db.execute(
            f"SELECT guild_id FROM server_stats WHERE {where}"
        ) as cursor:
            return [int(row[0]) for row in await cursor.fetchall()]
