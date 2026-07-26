"""
Dashboard access control: who signed in, and who is banned from the dashboard.

The dashboard knew *who may do what* (see `dashboard_roles`) but never recorded
*who actually showed up*. There was also no way to lock somebody out short of
removing every one of their roles — and that does not help against a person who
gets in through Discord's "Manage Server" permission, because that access is
granted by Discord, not by us.

This module adds the two missing pieces:

    logins   every dashboard sign-in is recorded (first seen, last seen, count)
    bans     an explicit deny-list that overrides every other access rule

A ban is checked in three places so it cannot be worked around:

    NextAuth signIn callback   → the sign-in itself is refused
    middleware.ts              → an existing session cannot open /dashboard
    BFF proxy                  → an existing session cannot call the bot API

Bans can be permanent or expire automatically.
"""

from __future__ import annotations

import asyncio
import time

import aiosqlite

from utils import db_paths

DB_PATH = "db/admin_config.db"

_lock = asyncio.Lock()

# user_id -> ban record. Kept in memory because is_banned() runs on every
# single dashboard request.
_ban_cache: dict[str, dict] = {}
_ban_cache_loaded = False


async def _ensure_tables(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_logins ("
        " user_id TEXT PRIMARY KEY,"
        " username TEXT DEFAULT '',"
        " avatar TEXT DEFAULT '',"
        " first_seen INTEGER DEFAULT 0,"
        " last_seen INTEGER DEFAULT 0,"
        " login_count INTEGER DEFAULT 0,"
        " last_path TEXT DEFAULT '')"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_bans ("
        " user_id TEXT PRIMARY KEY,"
        " banned_by TEXT DEFAULT '',"
        " banned_at INTEGER DEFAULT 0,"
        " reason TEXT DEFAULT '',"
        # 0 = permanent, otherwise a unix timestamp
        " expires_at INTEGER DEFAULT 0)"
    )
    await db.commit()


# ── Bans ──────────────────────────────────────────────────────────────────


async def load(force: bool = False) -> None:
    """Load the ban list into memory."""
    global _ban_cache_loaded

    async with _lock:
        if _ban_cache_loaded and not force:
            return

        import os

        os.makedirs("db", exist_ok=True)
        bans: dict[str, dict] = {}
        try:
            async with db_paths.connect(DB_PATH) as db:
                await _ensure_tables(db)
                async with db.execute(
                    "SELECT user_id, banned_by, banned_at, reason, expires_at"
                    " FROM dashboard_bans"
                ) as cursor:
                    async for row in cursor:
                        user_id, banned_by, banned_at, reason, expires_at = row
                        bans[str(user_id)] = {
                            "user_id": str(user_id),
                            "banned_by": banned_by or "",
                            "banned_at": int(banned_at or 0),
                            "reason": reason or "",
                            "expires_at": int(expires_at or 0),
                        }
        except Exception as exc:
            print(f"[dashboard_access] load failed: {exc}")
            _ban_cache_loaded = True
            return

        _ban_cache.clear()
        _ban_cache.update(bans)
        _ban_cache_loaded = True


def is_banned(user_id: str) -> bool:
    """True when the user is currently banned from the dashboard."""
    record = _ban_cache.get(str(user_id))
    if record is None:
        return False

    expires = record.get("expires_at") or 0
    if expires and expires <= time.time():
        # Expired: treat as lifted. The row is cleaned up by purge_expired().
        return False
    return True


def get_ban(user_id: str) -> dict | None:
    """The active ban record for a user, or None."""
    record = _ban_cache.get(str(user_id))
    if record is None:
        return None
    expires = record.get("expires_at") or 0
    if expires and expires <= time.time():
        return None
    return dict(record)


def list_bans(include_expired: bool = False) -> list[dict]:
    now = time.time()
    entries = []
    for record in _ban_cache.values():
        expires = record.get("expires_at") or 0
        expired = bool(expires and expires <= now)
        if expired and not include_expired:
            continue
        entry = dict(record)
        entry["expired"] = expired
        entries.append(entry)
    return sorted(entries, key=lambda e: e["banned_at"], reverse=True)


async def ban(
    user_id: str,
    *,
    banned_by: str,
    reason: str = "",
    duration_seconds: int = 0,
) -> dict:
    """
    Ban a user from the dashboard.

    `duration_seconds` of 0 means permanent. Re-banning an already banned user
    updates the reason and expiry.
    """
    uid = str(user_id).strip()
    if not uid.isdigit() or not 15 <= len(uid) <= 20:
        raise ValueError("user_id must be a valid Discord ID.")

    await load()

    now = int(time.time())
    expires = now + int(duration_seconds) if duration_seconds and duration_seconds > 0 else 0

    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await db.execute(
            "INSERT OR REPLACE INTO dashboard_bans"
            " (user_id, banned_by, banned_at, reason, expires_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid, str(banned_by), now, str(reason)[:400], expires),
        )
        await db.commit()

    record = {
        "user_id": uid,
        "banned_by": str(banned_by),
        "banned_at": now,
        "reason": str(reason)[:400],
        "expires_at": expires,
    }
    _ban_cache[uid] = record
    return dict(record)


async def unban(user_id: str) -> bool:
    """Lift a ban. Returns False when the user was not banned."""
    uid = str(user_id).strip()
    await load()

    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        cursor = await db.execute("DELETE FROM dashboard_bans WHERE user_id = ?", (uid,))
        await db.commit()
        removed = cursor.rowcount > 0

    _ban_cache.pop(uid, None)
    return removed


async def purge_expired() -> int:
    """Delete ban rows whose expiry has passed. Returns how many were removed."""
    now = int(time.time())
    await load()

    async with db_paths.connect(DB_PATH) as db:
        await _ensure_tables(db)
        cursor = await db.execute(
            "DELETE FROM dashboard_bans WHERE expires_at > 0 AND expires_at <= ?", (now,)
        )
        await db.commit()
        removed = cursor.rowcount or 0

    for uid in [k for k, v in _ban_cache.items() if v.get("expires_at") and v["expires_at"] <= now]:
        _ban_cache.pop(uid, None)
    return removed


# ── Logins ────────────────────────────────────────────────────────────────


async def record_login(
    user_id: str,
    *,
    username: str = "",
    avatar: str = "",
    new_session: bool = True,
    path: str = "",
) -> None:
    """
    Remember that a user used the dashboard.

    `new_session=True` counts a fresh sign-in; `False` only refreshes the
    "last seen" stamp, which is what the proxy does on ordinary requests.
    """
    uid = str(user_id).strip()
    if not uid.isdigit():
        return

    now = int(time.time())
    try:
        async with db_paths.connect(DB_PATH) as db:
            await _ensure_tables(db)
            async with db.execute(
                "SELECT login_count FROM dashboard_logins WHERE user_id = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                await db.execute(
                    "INSERT INTO dashboard_logins"
                    " (user_id, username, avatar, first_seen, last_seen, login_count, last_path)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uid, username[:100], avatar[:300], now, now, 1 if new_session else 0, path[:200]),
                )
            else:
                count = int(row[0] or 0) + (1 if new_session else 0)
                # Keep the stored name/avatar fresh, but never overwrite a known
                # name with an empty one.
                await db.execute(
                    "UPDATE dashboard_logins SET"
                    " username = CASE WHEN ? = '' THEN username ELSE ? END,"
                    " avatar = CASE WHEN ? = '' THEN avatar ELSE ? END,"
                    " last_seen = ?, login_count = ?, last_path = CASE WHEN ? = '' THEN last_path ELSE ? END"
                    " WHERE user_id = ?",
                    (
                        username, username[:100],
                        avatar, avatar[:300],
                        now, count,
                        path, path[:200],
                        uid,
                    ),
                )
            await db.commit()
    except Exception as exc:
        print(f"[dashboard_access] record_login failed: {exc}")


async def list_logins(limit: int = 500) -> list[dict]:
    """Everyone who ever signed in, most recently seen first."""
    entries: list[dict] = []
    try:
        async with db_paths.connect(DB_PATH) as db:
            await _ensure_tables(db)
            async with db.execute(
                "SELECT user_id, username, avatar, first_seen, last_seen, login_count, last_path"
                " FROM dashboard_logins ORDER BY last_seen DESC LIMIT ?",
                (max(1, min(int(limit), 5000)),),
            ) as cursor:
                async for row in cursor:
                    entries.append(
                        {
                            "user_id": str(row[0]),
                            "username": row[1] or "",
                            "avatar": row[2] or "",
                            "first_seen": int(row[3] or 0),
                            "last_seen": int(row[4] or 0),
                            "login_count": int(row[5] or 0),
                            "last_path": row[6] or "",
                        }
                    )
    except Exception as exc:
        print(f"[dashboard_access] list_logins failed: {exc}")
    return entries


async def get_login(user_id: str) -> dict | None:
    for entry in await list_logins(5000):
        if entry["user_id"] == str(user_id):
            return entry
    return None


async def forget_login(user_id: str) -> bool:
    """Remove a login record (does not affect roles or bans)."""
    uid = str(user_id).strip()
    try:
        async with db_paths.connect(DB_PATH) as db:
            await _ensure_tables(db)
            cursor = await db.execute("DELETE FROM dashboard_logins WHERE user_id = ?", (uid,))
            await db.commit()
            return (cursor.rowcount or 0) > 0
    except Exception as exc:
        print(f"[dashboard_access] forget_login failed: {exc}")
        return False
