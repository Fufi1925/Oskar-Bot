# ╔══════════════════════════════════════════════════════════════════╗
# ║   Admin broadcasts: storage and delivery                         ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Sending one message to every server the bot is on.

What this replaces:

  * The dashboard's "Global Broadcast" tab did not send anything to
    Discord at all — it wrote `global_notification`, which only ever
    showed a banner inside the dashboard. The name promised something
    the button did not do.
  * The route that really sent, `POST /admin/announcements`, had no user
    interface whatsoever. It was reachable with curl and nothing else.
  * Delivery reported its result with `print()`. There was no way to see
    which servers got the message, which refused it, or why.
  * The text went out as a raw string while everything else the bot
    posts is a Components V2 panel.

A broadcast now has a lifecycle — draft, scheduled, sending, sent — and
every guild it touched is recorded with the outcome.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiosqlite

DB_PATH = "db/admin_config.db"

# Where a broadcast can go.
TARGET_CHANNEL = "channel"   # a channel in each guild
TARGET_OWNER = "owner"       # a DM to each guild's owner
TARGET_BOTH = "both"
TARGETS = {TARGET_CHANNEL, TARGET_OWNER, TARGET_BOTH}

STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_CANCELLED = "cancelled"

TONES = {"info", "success", "warning", "error", "brand"}

# Discord's global rate limit is generous, but a few hundred guilds in a
# tight loop still trips it. One message every 0.6s is comfortably safe.
SEND_DELAY = 0.6


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            message TEXT NOT NULL,
            tone TEXT DEFAULT 'info',
            image_url TEXT,
            target TEXT DEFAULT 'channel',
            status TEXT DEFAULT 'draft',
            send_at INTEGER,
            created_at REAL,
            created_by TEXT,
            started_at REAL,
            finished_at REAL,
            delivered INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            -- JSON list of guild ids; empty means every guild
            only_guilds TEXT
        )
        """
    )

    # Per-guild outcome, so "it did not arrive" can actually be answered.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_targets (
            broadcast_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            guild_name TEXT,
            ok INTEGER DEFAULT 0,
            channel_id INTEGER,
            detail TEXT,
            at REAL,
            PRIMARY KEY (broadcast_id, guild_id)
        )
        """
    )

    # The old table, kept so anything already queued still goes out.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS scheduled_announcements ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " message TEXT NOT NULL,"
        " send_at INTEGER NOT NULL,"
        " sent_at INTEGER)"
    )

    await db.commit()


def clean(data: dict) -> dict:
    """Validate and clamp what came in from the dashboard."""
    message = str(data.get("message", "")).strip()
    if not message:
        raise ValueError("Die Nachricht darf nicht leer sein.")

    target = str(data.get("target", TARGET_CHANNEL))
    if target not in TARGETS:
        target = TARGET_CHANNEL

    tone = str(data.get("tone", "info"))
    if tone not in TONES:
        tone = "info"

    only = data.get("only_guilds") or []
    if not isinstance(only, (list, tuple)):
        only = []
    only = [str(g) for g in only if str(g).strip().isdigit()]

    return {
        "title": str(data.get("title", "") or "")[:200],
        "message": message[:3500],
        "tone": tone,
        "image_url": str(data.get("image_url", "") or "")[:400],
        "target": target,
        "only_guilds": only,
    }


async def create(
    db: aiosqlite.Connection, fields: dict, *, send_at: int | None = None,
    created_by: str = "dashboard",
) -> int:
    import json

    status = STATUS_SCHEDULED if send_at else STATUS_DRAFT
    cursor = await db.execute(
        "INSERT INTO broadcasts (title, message, tone, image_url, target, status,"
        " send_at, created_at, created_by, only_guilds)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fields["title"], fields["message"], fields["tone"], fields["image_url"],
            fields["target"], status, send_at, time.time(), created_by,
            json.dumps(fields["only_guilds"]),
        ),
    )
    await db.commit()
    return cursor.lastrowid


async def get(db: aiosqlite.Connection, broadcast_id: int) -> dict | None:
    import json

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None
    data = dict(row)
    try:
        data["only_guilds"] = json.loads(data.get("only_guilds") or "[]")
    except ValueError:
        data["only_guilds"] = []
    return data


async def recent(db: aiosqlite.Connection, limit: int = 25) -> list[dict]:
    import json

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)
    ) as cursor:
        rows = await cursor.fetchall()

    out = []
    for row in rows:
        data = dict(row)
        try:
            data["only_guilds"] = json.loads(data.get("only_guilds") or "[]")
        except ValueError:
            data["only_guilds"] = []
        out.append(data)
    return out


async def due(db: aiosqlite.Connection, now: int | None = None) -> list[dict]:
    """Scheduled broadcasts whose time has come."""
    now = now if now is not None else int(time.time())
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT id FROM broadcasts WHERE status = ? AND send_at IS NOT NULL"
        " AND send_at <= ? ORDER BY send_at LIMIT 3",
        (STATUS_SCHEDULED, now),
    ) as cursor:
        ids = [row[0] for row in await cursor.fetchall()]

    return [await get(db, i) for i in ids]


async def set_status(
    db: aiosqlite.Connection, broadcast_id: int, status: str, **fields
) -> None:
    columns = ["status = ?"]
    values: list[Any] = [status]
    for name, value in fields.items():
        columns.append(f"{name} = ?")
        values.append(value)
    values.append(broadcast_id)

    await db.execute(
        f"UPDATE broadcasts SET {', '.join(columns)} WHERE id = ?", values
    )
    await db.commit()


async def cancel(db: aiosqlite.Connection, broadcast_id: int) -> bool:
    """Only something that has not gone out yet can be called back."""
    cursor = await db.execute(
        "UPDATE broadcasts SET status = ? WHERE id = ? AND status IN (?, ?)",
        (STATUS_CANCELLED, broadcast_id, STATUS_DRAFT, STATUS_SCHEDULED),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def record(
    db: aiosqlite.Connection, broadcast_id: int, guild_id: int, guild_name: str,
    *, ok: bool, channel_id: int | None = None, detail: str = "",
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO broadcast_targets"
        " (broadcast_id, guild_id, guild_name, ok, channel_id, detail, at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (broadcast_id, guild_id, guild_name, 1 if ok else 0,
         channel_id, detail[:200], time.time()),
    )
    await db.commit()


async def results(db: aiosqlite.Connection, broadcast_id: int) -> list[dict]:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM broadcast_targets WHERE broadcast_id = ?"
        " ORDER BY ok, guild_name",
        (broadcast_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


# ── delivery ────────────────────────────────────────────────────────


def pick_channel(guild):
    """
    Where to post in a guild.

    Preference order: the system channel, then anything named like an
    announcement or general channel, then the first channel the bot may
    write in. Picking blindly meant broadcasts landed in log channels.
    """
    me = guild.me
    if me is None:
        return None

    def usable(channel):
        return channel is not None and channel.permissions_for(me).send_messages

    if usable(guild.system_channel):
        return guild.system_channel

    preferred = ("announcement", "ankündigung", "ankuendigung", "news",
                 "allgemein", "general", "chat")
    for name in preferred:
        for channel in guild.text_channels:
            if name in channel.name.lower() and usable(channel):
                return channel

    return next((c for c in guild.text_channels if usable(c)), None)


def build_view(record_row: dict):
    """The broadcast as a Components V2 panel."""
    from utils.panels import ACCENT, Panel

    return Panel(
        record_row.get("title") or "Nachricht vom Bot-Team",
        record_row.get("message") or "",
        tone=record_row.get("tone") or "info",
        accent=ACCENT.get(record_row.get("tone") or "info"),
        image_url=record_row.get("image_url") or None,
    )


async def deliver(
    bot, db: aiosqlite.Connection, broadcast_id: int, *, dry_run: bool = False
) -> dict:
    """
    Send one broadcast and record what happened in each guild.

    `dry_run` works out the targets and reports them without sending, so
    the dashboard can show exactly where a message would land before it
    is too late to take it back.
    """
    row = await get(db, broadcast_id)
    if row is None:
        raise ValueError("Diese Nachricht gibt es nicht.")
    if row["status"] in (STATUS_SENT, STATUS_SENDING) and not dry_run:
        raise ValueError("Diese Nachricht wurde bereits verschickt.")

    only = {int(g) for g in row.get("only_guilds") or []}
    guilds = [g for g in bot.guilds if not only or g.id in only]
    target = row.get("target") or TARGET_CHANNEL

    if dry_run:
        plan = []
        for guild in guilds:
            channel = pick_channel(guild) if target in (TARGET_CHANNEL, TARGET_BOTH) else None
            owner = guild.owner if target in (TARGET_OWNER, TARGET_BOTH) else None
            reachable = channel is not None or owner is not None
            plan.append({
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "channel": channel.name if channel else None,
                "owner": str(owner) if owner else None,
                "reachable": reachable,
            })
        return {
            "dry_run": True,
            "guilds": len(guilds),
            "reachable": sum(1 for p in plan if p["reachable"]),
            "plan": plan,
        }

    await set_status(db, broadcast_id, STATUS_SENDING, started_at=time.time())

    delivered = failed = 0
    for guild in guilds:
        ok = False
        details = []
        used_channel = None

        if target in (TARGET_CHANNEL, TARGET_BOTH):
            channel = pick_channel(guild)
            if channel is None:
                details.append("kein beschreibbarer Kanal")
            else:
                try:
                    await channel.send(view=build_view(row))
                    ok = True
                    used_channel = channel.id
                except Exception as exc:
                    details.append(f"Kanal: {type(exc).__name__}")
                await asyncio.sleep(SEND_DELAY)

        if target in (TARGET_OWNER, TARGET_BOTH):
            owner = guild.owner
            if owner is None:
                details.append("Inhaber unbekannt")
            else:
                try:
                    await owner.send(view=build_view(row))
                    ok = True
                except Exception as exc:
                    # Closed DMs are the normal case, not a bug.
                    details.append(f"DM: {type(exc).__name__}")
                await asyncio.sleep(SEND_DELAY)

        await record(
            db, broadcast_id, guild.id, guild.name,
            ok=ok, channel_id=used_channel, detail=", ".join(details),
        )
        delivered += 1 if ok else 0
        failed += 0 if ok else 1

    await set_status(
        db, broadcast_id, STATUS_SENT,
        finished_at=time.time(), delivered=delivered, failed=failed,
    )
    return {"delivered": delivered, "failed": failed, "guilds": len(guilds)}
