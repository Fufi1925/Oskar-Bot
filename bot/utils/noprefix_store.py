# ╔══════════════════════════════════════════════════════════════════╗
# ║   No-prefix: who may use commands without typing the prefix      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage for the no-prefix allowlist.

There was a serious bug here. The `np` table has no `guild_id` column,
so the users in it are **global** — someone added on one server could
use no-prefix commands on every server the bot is on. The dashboard
showed that global list on each guild's page, so:

  * Server A saw the no-prefix users of Server B in its own dashboard
  * pressing Save on Server B ran
    `DELETE FROM np WHERE id NOT IN (...)`, which wiped Server A's
    entries — the endpoint defaults to `replace_users=True`

Both halves are fixed by giving the table a `guild_id`, keeping the old
rows as "global" (that is what they currently are, and silently
narrowing them would take away access people have today) and letting the
dashboard manage only its own guild.

Roles were already per guild in `np_roles` and are left alone.
"""

from __future__ import annotations

import time
from typing import Any

import aiosqlite

DB_PATH = "db/np.db"

# Rows carried over from before the guild column existed. They really do
# apply everywhere, so they keep doing that until somebody removes them.
GLOBAL_GUILD = 0


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS np (
            id INTEGER PRIMARY KEY,
            expiry_time TEXT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS np_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )
        """
    )

    async with db.execute("PRAGMA table_info([np])") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if "guild_id" not in columns:
        # Existing rows are global today. Marking them GLOBAL_GUILD keeps
        # that true rather than quietly revoking access.
        await db.execute(
            f"ALTER TABLE np ADD COLUMN guild_id INTEGER DEFAULT {GLOBAL_GUILD}"
        )
        await db.execute(
            f"UPDATE np SET guild_id = {GLOBAL_GUILD} WHERE guild_id IS NULL"
        )

    if "added_at" not in columns:
        try:
            await db.execute("ALTER TABLE np ADD COLUMN added_at REAL")
        except Exception:
            pass
    if "added_by" not in columns:
        try:
            await db.execute("ALTER TABLE np ADD COLUMN added_by INTEGER")
        except Exception:
            pass

    await db.execute(
        "CREATE INDEX IF NOT EXISTS np_guild ON np (guild_id)"
    )
    await db.commit()


def _expiry_to_unix(value: Any) -> float | None:
    """The column is TEXT and has held both ISO strings and timestamps."""
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        import datetime as _dt

        return _dt.datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


async def list_users(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    """
    Everyone with no-prefix on this guild.

    Includes the global rows, marked as such, because they do apply here
    and hiding them would make the list look wrong.
    """
    async with db.execute(
        "SELECT id, expiry_time, guild_id, added_at FROM np"
        " WHERE guild_id = ? OR guild_id = ? ORDER BY id",
        (guild_id, GLOBAL_GUILD),
    ) as cursor:
        rows = await cursor.fetchall()

    now = time.time()
    out = []
    for user_id, expiry, row_guild, added_at in rows:
        expires = _expiry_to_unix(expiry)
        out.append({
            "user_id": int(user_id),
            "expires_at": expires,
            "expired": bool(expires and expires <= now),
            "global": int(row_guild or GLOBAL_GUILD) == GLOBAL_GUILD,
            "added_at": float(added_at or 0),
        })
    return out


async def add_user(
    db: aiosqlite.Connection, guild_id: int, user_id: int,
    *, expires_at: float | None = None, added_by: int = 0,
) -> None:
    await db.execute(
        "INSERT INTO np (id, expiry_time, guild_id, added_at, added_by)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        "   expiry_time = excluded.expiry_time,"
        "   guild_id = excluded.guild_id",
        (int(user_id), str(expires_at) if expires_at else None,
         int(guild_id), time.time(), int(added_by or 0)),
    )
    await db.commit()


async def remove_user(db: aiosqlite.Connection, guild_id: int, user_id: int) -> bool:
    """
    Remove a user from this guild's list.

    A global row is only removed when the caller is explicit about it, so
    one server cannot take away access another server granted.
    """
    cursor = await db.execute(
        "DELETE FROM np WHERE id = ? AND guild_id = ?", (int(user_id), int(guild_id))
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def remove_global_user(db: aiosqlite.Connection, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM np WHERE id = ? AND guild_id = ?", (int(user_id), GLOBAL_GUILD)
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def list_roles(db: aiosqlite.Connection, guild_id: int) -> list[int]:
    async with db.execute(
        "SELECT role_id FROM np_roles WHERE guild_id = ? ORDER BY role_id",
        (guild_id,),
    ) as cursor:
        return [int(row[0]) for row in await cursor.fetchall()]


async def add_role(db: aiosqlite.Connection, guild_id: int, role_id: int) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO np_roles (guild_id, role_id) VALUES (?, ?)",
        (int(guild_id), int(role_id)),
    )
    await db.commit()


async def remove_role(db: aiosqlite.Connection, guild_id: int, role_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM np_roles WHERE guild_id = ? AND role_id = ?",
        (int(guild_id), int(role_id)),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def purge_expired(db: aiosqlite.Connection) -> int:
    """Drop entries whose time is up."""
    async with db.execute(
        "SELECT id, expiry_time FROM np WHERE expiry_time IS NOT NULL"
    ) as cursor:
        rows = await cursor.fetchall()

    now = time.time()
    stale = [
        int(user_id) for user_id, expiry in rows
        if (_expiry_to_unix(expiry) or 0) <= now
    ]
    if not stale:
        return 0

    placeholders = ",".join("?" for _ in stale)
    await db.execute(f"DELETE FROM np WHERE id IN ({placeholders})", stale)
    await db.commit()
    return len(stale)
