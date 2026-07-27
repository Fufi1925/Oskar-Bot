# ╔══════════════════════════════════════════════════════════════════╗
# ║   Giveaways: entries, drawing, rerolls                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Giveaway storage and draw logic.

Two problems with the previous setup:

  * The cog wrote to `db/giveaways.db` while the API wrote to
    `db/giveaway.db` — two different files. A giveaway started from the
    dashboard was invisible to the cog's timer, so it never ended by
    itself and never announced a winner.
  * Entries were counted by reading the 🎉 reaction back off the message.
    That breaks as soon as the reaction is cleared, cannot record when
    somebody joined, and makes a reroll that excludes previous winners
    impossible.

Entries now live in their own table, written when someone presses the
join button. Everything reads one file: `db/giveaways.db`, the one the
cog already used.
"""

from __future__ import annotations

import random
import time
from typing import Any

import aiosqlite

DB_PATH = "db/giveaways.db"


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the tables and add the columns newer features need."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS Giveaway (
            guild_id INTEGER,
            host_id INTEGER,
            start_time TIMESTAMP,
            ends_at TIMESTAMP,
            prize TEXT,
            winners INTEGER,
            message_id INTEGER,
            channel_id INTEGER,
            PRIMARY KEY (guild_id, message_id)
        )
        """
    )

    # Who pressed the button. Reading the reaction back was lossy.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at REAL NOT NULL,
            PRIMARY KEY (message_id, user_id)
        )
        """
    )

    # Past winners, so a reroll can skip them.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_winners (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            won_at REAL NOT NULL,
            rerolled INTEGER DEFAULT 0,
            PRIMARY KEY (message_id, user_id)
        )
        """
    )

    # Columns added after the table shipped; CREATE IF NOT EXISTS is a
    # no-op on an existing table, so these need an explicit ALTER.
    async with db.execute("PRAGMA table_info([Giveaway])") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    extras = {
        "title": "TEXT",
        "description": "TEXT",
        "colour": "INTEGER",
        "button_label": "TEXT",
        "button_emoji": "TEXT",
        "image_url": "TEXT",
        "required_role_id": "INTEGER",
        "dm_winners": "INTEGER DEFAULT 1",
        "dm_host": "INTEGER DEFAULT 1",
        "ended": "INTEGER DEFAULT 0",
    }
    for name, kind in extras.items():
        if name not in columns:
            try:
                await db.execute(f"ALTER TABLE Giveaway ADD COLUMN {name} {kind}")
            except Exception:
                pass

    await db.commit()


# ---------------------------------------------------------------- entries


async def add_entry(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    """Record a join. Returns False when the user had already entered."""
    async with db.execute(
        "SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
        (message_id, user_id),
    ) as cursor:
        if await cursor.fetchone():
            return False

    await db.execute(
        "INSERT INTO giveaway_entries (message_id, user_id, joined_at)"
        " VALUES (?, ?, ?)",
        (message_id, user_id, time.time()),
    )
    await db.commit()
    return True


async def remove_entry(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
        (message_id, user_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def entry_ids(db: aiosqlite.Connection, message_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_id FROM giveaway_entries WHERE message_id = ?", (message_id,)
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def entry_count(db: aiosqlite.Connection, message_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM giveaway_entries WHERE message_id = ?", (message_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------- winners


async def past_winner_ids(db: aiosqlite.Connection, message_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_id FROM giveaway_winners WHERE message_id = ?", (message_id,)
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def record_winners(
    db: aiosqlite.Connection, message_id: int, user_ids: list[int], *, reroll=False
) -> None:
    now = time.time()
    for user_id in user_ids:
        await db.execute(
            "INSERT OR REPLACE INTO giveaway_winners"
            " (message_id, user_id, won_at, rerolled) VALUES (?, ?, ?, ?)",
            (message_id, user_id, now, 1 if reroll else 0),
        )
    await db.commit()


async def draw(
    db: aiosqlite.Connection,
    message_id: int,
    count: int,
    *,
    exclude_past: bool = False,
) -> list[int]:
    """
    Pick winners at random from the recorded entries.

    exclude_past skips everyone who already won this giveaway, which is
    what a reroll should do — otherwise it can hand the prize to the same
    person again.
    """
    candidates = await entry_ids(db, message_id)
    if exclude_past:
        already = set(await past_winner_ids(db, message_id))
        remaining = [u for u in candidates if u not in already]
        # If everyone has won already, fall back to the full pool rather
        # than returning nobody.
        candidates = remaining or candidates

    if not candidates:
        return []
    return random.sample(candidates, min(max(1, count), len(candidates)))


# ---------------------------------------------------------------- records


async def get(db: aiosqlite.Connection, guild_id: int, message_id: int) -> dict | None:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM Giveaway WHERE guild_id = ? AND message_id = ?",
        (guild_id, message_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_ended(db: aiosqlite.Connection, message_id: int) -> None:
    """
    Flag it as finished instead of deleting the row.

    The entries and winners have to stay around for a reroll, and the
    dashboard should still be able to show what happened.
    """
    await db.execute("UPDATE Giveaway SET ended = 1 WHERE message_id = ?", (message_id,))
    await db.commit()


def fill_placeholders(text: str, values: dict[str, Any]) -> str:
    """Replace {prize}, {winners}, {ends}, {host}, {entries} in user text."""
    out = str(text or "")
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out
