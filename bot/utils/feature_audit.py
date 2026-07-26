"""
Cross-guild audit log and notification history.

Backs the `cross_guild_audit_log`, `suspicious_owner_action_alerts`,
`guild_leave_audit`, `global_notification_history`, `incident_timeline_builder`
and `admin_action_approval_queue` flags.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

from utils import feature_flags as flags

AUDIT_DB = "db/admin_config.db"

# Actions considered destructive enough to be flagged / require approval.
SUSPICIOUS_ACTIONS = {
    "ban", "kick", "delete_channel", "delete_role", "purge",
    "server_name", "mass_config_push",
}
DESTRUCTIVE_ACTIONS = {
    "ban", "kick", "delete_channel", "delete_role", "purge",
}


async def _ensure_tables(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS admin_audit_log ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " created_at INTEGER NOT NULL,"
        " actor TEXT,"
        " guild_id TEXT,"
        " action TEXT NOT NULL,"
        " detail TEXT,"
        " suspicious INTEGER DEFAULT 0)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS notification_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " created_at INTEGER NOT NULL,"
        " message TEXT)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS admin_approval_queue ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " created_at INTEGER NOT NULL,"
        " requested_by TEXT,"
        " guild_id TEXT,"
        " action TEXT NOT NULL,"
        " payload TEXT,"
        " status TEXT DEFAULT 'pending',"
        " approved_by TEXT,"
        " resolved_at INTEGER)"
    )
    await db.commit()


def is_suspicious(action: str) -> bool:
    return action.lower() in SUSPICIOUS_ACTIONS


def is_destructive(action: str) -> bool:
    return action.lower() in DESTRUCTIVE_ACTIONS


async def log_action(
    action: str,
    *,
    actor: str | None = None,
    guild_id: str | int | None = None,
    detail: str = "",
) -> None:
    """Record an admin action in the cross-guild audit log."""
    if not flags.is_enabled("cross_guild_audit_log"):
        return

    suspicious = 1 if (flags.is_enabled("suspicious_owner_action_alerts") and is_suspicious(action)) else 0

    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await _ensure_tables(db)
            await db.execute(
                "INSERT INTO admin_audit_log (created_at, actor, guild_id, action, detail, suspicious)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (int(time.time()), str(actor or "system"), str(guild_id or ""), action, detail[:1000], suspicious),
            )
            await db.commit()
    except Exception as exc:
        print(f"[feature_audit] log_action failed: {exc}")


async def fetch_audit(limit: int = 100, suspicious_only: bool = False) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM admin_audit_log"
            if suspicious_only:
                query += " WHERE suspicious = 1"
            query += " ORDER BY created_at DESC LIMIT ?"
            async with db.execute(query, (max(1, min(limit, 500)),)) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[feature_audit] fetch_audit failed: {exc}")
        return []


async def record_notification(message: str) -> None:
    if not flags.is_enabled("global_notification_history"):
        return
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await _ensure_tables(db)
            await db.execute(
                "INSERT INTO notification_history (created_at, message) VALUES (?, ?)",
                (int(time.time()), (message or "")[:1000]),
            )
            await db.commit()
    except Exception as exc:
        print(f"[feature_audit] record_notification failed: {exc}")


async def fetch_notification_history(limit: int = 50) -> list[dict[str, Any]]:
    if not flags.is_enabled("global_notification_history"):
        return []
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM notification_history ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[feature_audit] fetch_notification_history failed: {exc}")
        return []


# ── Approval queue ────────────────────────────────────────────────────────


async def queue_action(action: str, payload: dict, *, requested_by: str, guild_id: str) -> int:
    """Store an action for later approval. Returns the queue entry id."""
    async with aiosqlite.connect(AUDIT_DB) as db:
        await _ensure_tables(db)
        cursor = await db.execute(
            "INSERT INTO admin_approval_queue (created_at, requested_by, guild_id, action, payload)"
            " VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), requested_by, str(guild_id), action, json.dumps(payload)[:4000]),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def fetch_queue(status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM admin_approval_queue WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, max(1, min(limit, 200))),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[feature_audit] fetch_queue failed: {exc}")
        return []


async def resolve_queue_entry(entry_id: int, approved_by: str, approve: bool) -> dict[str, Any] | None:
    """
    Approve or reject a queued action.

    With `two_person_rule` enabled the approver must be different from the
    requester; the caller is responsible for enforcing that and passing a
    truthy `approve` only when allowed.
    """
    async with aiosqlite.connect(AUDIT_DB) as db:
        await _ensure_tables(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM admin_approval_queue WHERE id = ?", (entry_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None

        await db.execute(
            "UPDATE admin_approval_queue SET status = ?, approved_by = ?, resolved_at = ? WHERE id = ?",
            ("approved" if approve else "rejected", approved_by, int(time.time()), entry_id),
        )
        await db.commit()
        return dict(row)


# ── Incident timeline ─────────────────────────────────────────────────────


async def build_timeline(limit: int = 50) -> list[dict[str, Any]]:
    """Merge audit entries and captured log records into one timeline."""
    if not flags.is_enabled("incident_timeline_builder"):
        return []

    from utils.feature_services import runtime

    events: list[dict[str, Any]] = []

    for entry in await fetch_audit(limit=limit):
        events.append(
            {
                "timestamp": entry.get("created_at", 0),
                "kind": "audit",
                "severity": "warning" if entry.get("suspicious") else "info",
                "summary": f"{entry.get('action')} by {entry.get('actor')}",
                "detail": entry.get("detail", ""),
                "guild_id": entry.get("guild_id", ""),
            }
        )

    for record in list(runtime.log_buffer)[-limit:]:
        try:
            stamp = int(time.mktime(time.strptime(record["time"], "%Y-%m-%d %H:%M:%S")))
        except Exception:
            stamp = 0
        events.append(
            {
                "timestamp": stamp,
                "kind": "log",
                "severity": record.get("level", "INFO").lower(),
                "summary": f"{record.get('logger')}: {record.get('message', '')[:120]}",
                "detail": record.get("message", ""),
                "guild_id": "",
            }
        )

    events.sort(key=lambda item: item["timestamp"], reverse=True)
    return events[:limit]
