# ╔══════════════════════════════════════════════════════════════════╗
# ║   Vanity roles: a role for having the server in your status      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage and matching for status-based vanity roles.

What this replaces: the old cog polled
`https://discord.com/api/v10/invites/<vanity>` every fifteen seconds to
see whether the *invite* still existed, and if it did, handed the role to
**every member of the server**. That is not what a vanity role is
anywhere else — it should go to the people who put the server's invite in
their own Discord status, and come off again when they remove it.

Matching happens on `on_presence_update`, so there is no polling at all.
The trade-off is that the presence intent has to be on; it already is
(`core/universitybot.py` sets `intents.presences = True`).
"""

from __future__ import annotations

import re
import time
from typing import Any

import aiosqlite

DB_PATH = "db/vanity.db"

# How the trigger may be written in a status. All of these are the same:
#   .gg/meinserver   discord.gg/meinserver   https://discord.gg/meinserver   /meinserver
_PREFIXES = (
    "https://discord.gg/", "http://discord.gg/",
    "https://discord.com/invite/", "http://discord.com/invite/",
    "discord.gg/", "discord.com/invite/", ".gg/",
)


def normalise_trigger(text: str) -> str:
    """
    Reduce whatever was typed to the bare invite code, lowercased.

    People enter the trigger in every possible shape; storing the raw
    string meant `.gg/MeinServer` and `discord.gg/meinserver` were two different
    setups that both looked right in the dashboard.
    """
    value = str(text or "").strip().lower()
    for prefix in _PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    # Drop anything after the code itself (query strings, trailing slash).
    value = value.split("?")[0].split("/")[0].strip()
    return value


def status_text(member) -> str:
    """
    Everything a member's presence says, as one lowercase string.

    Only a custom status can hold arbitrary text, but a Spotify listen or
    a game also carry names, and reading them all means a trigger works
    no matter which activity slot Discord decided to use.
    """
    parts = []
    for activity in getattr(member, "activities", []) or []:
        for attribute in ("name", "state", "details"):
            value = getattr(activity, attribute, None)
            if isinstance(value, str) and value:
                parts.append(value)
    return " ".join(parts).lower()


def matches(trigger: str, text: str) -> bool:
    """
    Whether a status contains the trigger.

    Word boundaries matter: a trigger of `gg` must not match the word
    "gaming", and `server` should not match "servername". The invite code is
    matched with the usual prefixes optional, so anything from `.gg/x` to
    a bare `x` counts.
    """
    trigger = normalise_trigger(trigger)
    if not trigger:
        return False

    escaped = re.escape(trigger)
    pattern = (
        r"(?:^|[^\w/.])"                      # not part of a longer word
        r"(?:(?:https?://)?(?:discord\.gg|discord\.com/invite)/|\.gg/)?"
        + escaped +
        r"(?![\w-])"                          # nothing glued to the end
    )
    return re.search(pattern, text or "") is not None


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the table and add any column a newer version introduced."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vanity_roles (
            guild_id INTEGER NOT NULL,
            vanity TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            log_channel_id INTEGER,
            current_status TEXT,
            PRIMARY KEY (guild_id, vanity)
        )
        """
    )

    async with db.execute("PRAGMA table_info([vanity_roles])") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    extras = {
        "enabled": "INTEGER DEFAULT 1",
        "created_at": "REAL",
        # Counters, so the dashboard can show whether it is doing anything
        # at all. The old version left no trace of its work.
        "granted_total": "INTEGER DEFAULT 0",
        "removed_total": "INTEGER DEFAULT 0",
    }
    for name, kind in extras.items():
        if name not in columns:
            try:
                await db.execute(f"ALTER TABLE vanity_roles ADD COLUMN {name} {kind}")
            except Exception:
                pass

    # Who currently holds a role because of which trigger. Without this
    # the bot cannot tell "role granted by us" from "role given by hand",
    # and would strip roles it never handed out.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vanity_holders (
            guild_id INTEGER NOT NULL,
            vanity TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            since REAL NOT NULL,
            PRIMARY KEY (guild_id, vanity, user_id)
        )
        """
    )

    await db.commit()


# ── setups ──────────────────────────────────────────────────────────


async def list_setups(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM vanity_roles WHERE guild_id = ? ORDER BY vanity", (guild_id,)
    ) as cursor:
        rows = await cursor.fetchall()

    out = []
    for row in rows:
        data = dict(row)
        out.append({
            "vanity": data["vanity"],
            "role_id": int(data["role_id"]),
            "log_channel_id": (
                int(data["log_channel_id"]) if data.get("log_channel_id") else None
            ),
            "enabled": bool(data.get("enabled", 1)),
            "granted_total": int(data.get("granted_total") or 0),
            "removed_total": int(data.get("removed_total") or 0),
            "created_at": float(data.get("created_at") or 0),
        })
    return out


async def all_setups(db: aiosqlite.Connection) -> dict[int, list[dict]]:
    """Every setup, grouped by guild — used to prime the in-memory cache."""
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM vanity_roles WHERE COALESCE(enabled, 1) = 1"
    ) as cursor:
        rows = await cursor.fetchall()

    grouped: dict[int, list[dict]] = {}
    for row in rows:
        data = dict(row)
        grouped.setdefault(int(data["guild_id"]), []).append({
            "vanity": data["vanity"],
            "role_id": int(data["role_id"]),
            "log_channel_id": (
                int(data["log_channel_id"]) if data.get("log_channel_id") else None
            ),
        })
    return grouped


async def save_setup(
    db: aiosqlite.Connection, guild_id: int, vanity: str, role_id: int,
    *, log_channel_id: int | None = None, enabled: bool = True,
) -> str:
    """Store a setup. Returns the normalised trigger that was written."""
    trigger = normalise_trigger(vanity)
    if not trigger:
        raise ValueError("Der Auslöser darf nicht leer sein.")

    await db.execute(
        "INSERT INTO vanity_roles"
        " (guild_id, vanity, role_id, log_channel_id, enabled, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, vanity) DO UPDATE SET"
        "   role_id = excluded.role_id,"
        "   log_channel_id = excluded.log_channel_id,"
        "   enabled = excluded.enabled",
        (guild_id, trigger, int(role_id),
         int(log_channel_id) if log_channel_id else None,
         1 if enabled else 0, time.time()),
    )
    await db.commit()
    return trigger


async def delete_setup(db: aiosqlite.Connection, guild_id: int, vanity: str) -> bool:
    trigger = normalise_trigger(vanity)
    cursor = await db.execute(
        "DELETE FROM vanity_roles WHERE guild_id = ? AND vanity = ?",
        (guild_id, trigger),
    )
    await db.execute(
        "DELETE FROM vanity_holders WHERE guild_id = ? AND vanity = ?",
        (guild_id, trigger),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def bump(
    db: aiosqlite.Connection, guild_id: int, vanity: str, *, granted=0, removed=0
) -> None:
    await db.execute(
        "UPDATE vanity_roles SET granted_total = COALESCE(granted_total, 0) + ?,"
        " removed_total = COALESCE(removed_total, 0) + ?"
        " WHERE guild_id = ? AND vanity = ?",
        (granted, removed, guild_id, vanity),
    )
    await db.commit()


# ── who holds a role right now ──────────────────────────────────────


async def holders(db: aiosqlite.Connection, guild_id: int, vanity: str) -> list[dict]:
    async with db.execute(
        "SELECT user_id, since FROM vanity_holders WHERE guild_id = ? AND vanity = ?"
        " ORDER BY since",
        (guild_id, normalise_trigger(vanity)),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"user_id": int(r[0]), "since": float(r[1])} for r in rows]


async def holder_counts(db: aiosqlite.Connection, guild_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT vanity, COUNT(*) FROM vanity_holders WHERE guild_id = ?"
        " GROUP BY vanity",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return {row[0]: int(row[1]) for row in rows}


async def is_holder(
    db: aiosqlite.Connection, guild_id: int, vanity: str, user_id: int
) -> bool:
    async with db.execute(
        "SELECT 1 FROM vanity_holders WHERE guild_id = ? AND vanity = ? AND user_id = ?",
        (guild_id, normalise_trigger(vanity), user_id),
    ) as cursor:
        return await cursor.fetchone() is not None


async def add_holder(
    db: aiosqlite.Connection, guild_id: int, vanity: str, user_id: int
) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO vanity_holders (guild_id, vanity, user_id, since)"
        " VALUES (?, ?, ?, ?)",
        (guild_id, normalise_trigger(vanity), user_id, time.time()),
    )
    await db.commit()


async def remove_holder(
    db: aiosqlite.Connection, guild_id: int, vanity: str, user_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM vanity_holders WHERE guild_id = ? AND vanity = ? AND user_id = ?",
        (guild_id, normalise_trigger(vanity), user_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


def stats(setups: list[dict], counts: dict[str, int]) -> dict[str, Any]:
    return {
        "setups": len(setups),
        "active": sum(1 for s in setups if s["enabled"]),
        "holders": sum(counts.get(s["vanity"], 0) for s in setups),
        "granted_total": sum(s["granted_total"] for s in setups),
    }
