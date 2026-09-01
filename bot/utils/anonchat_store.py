# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anonymous chat: settings and the moderation log                ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage for anonymous channels.

A channel is marked anonymous; anything a member writes there is deleted
straight away and posted again by the bot, so the original author is not
visible to anybody reading the channel.

Two things worth spelling out, because both are easy to get wrong:

  * **One webhook per channel, not per member.** Discord caps a channel
    at 15 webhooks, so a webhook per person stops working at the 16th.
    The username and avatar are overridden per message instead, which
    looks identical to a reader and has no limit.
  * **The log is the only trace.** Without it an anonymous channel is a
    free pass for harassment with nobody to hold responsible. It is
    written to a channel only staff can see, never to the anonymous one.
"""

from __future__ import annotations

import time
from typing import Any

import aiosqlite

DB_PATH = "db/anonchat.db"

# How the message is re-posted.
MODE_WEBHOOK = "webhook"   # via a webhook: custom name and avatar
MODE_BOT = "bot"           # as a normal bot message
MODES = {MODE_WEBHOOK, MODE_BOT}

DEFAULTS: dict[str, Any] = {
    "enabled": 1,
    "mode": MODE_WEBHOOK,
    "alias": "Anonym",
    "avatar_url": "",
    "log_channel_id": None,
    # Guards. All optional, all off by default.
    "min_account_days": 0,
    "min_member_days": 0,
    "required_role_id": None,
    "blocked_role_id": None,
    "cooldown_seconds": 0,
    "max_length": 2000,
    "allow_attachments": 1,
    "allow_links": 1,
    "allow_mentions": 0,      # pinging @everyone from behind a mask is nasty
    "strip_replies": 1,
    # Keep the log rows for this many days. 0 = forever.
    "log_retention_days": 30,
}

BOOLEAN_KEYS = {
    "enabled", "allow_attachments", "allow_links", "allow_mentions",
    "strip_replies",
}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS anon_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        )
        """
    )

    async with db.execute("PRAGMA table_info([anon_channels])") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}

    for name, value in DEFAULTS.items():
        if name in existing:
            continue
        kind = "TEXT" if isinstance(value, str) else "INTEGER"
        try:
            await db.execute(f"ALTER TABLE anon_channels ADD COLUMN {name} {kind}")
        except Exception:
            pass

    # Who wrote what. Staff-only; this is what makes the feature usable
    # without handing out a free pass for harassment.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS anon_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER,
            content TEXT,
            at REAL NOT NULL
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS anon_log_guild ON anon_log (guild_id, at DESC)"
    )

    # Members barred from posting anonymously.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS anon_blocked (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT,
            by_id INTEGER,
            at REAL,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    await db.commit()


def normalise(settings: dict) -> dict:
    """Clamp everything to something the bot can actually act on."""
    out = dict(DEFAULTS)
    out.update({k: v for k, v in settings.items() if k in DEFAULTS})

    for key in BOOLEAN_KEYS:
        out[key] = 1 if out.get(key) else 0

    if out.get("mode") not in MODES:
        out["mode"] = MODE_WEBHOOK

    alias = str(out.get("alias") or "").strip() or DEFAULTS["alias"]
    # Discord rejects a webhook username containing "discord", and caps
    # it at 80 characters. Failing the send over this would be silent.
    if "discord" in alias.lower():
        alias = alias.lower().replace("discord", "disc0rd")
    out["alias"] = alias[:80]

    avatar = str(out.get("avatar_url") or "").strip()
    out["avatar_url"] = avatar[:400] if avatar.startswith("http") else ""

    for key in ("min_account_days", "min_member_days"):
        out[key] = max(0, min(int(out.get(key) or 0), 3650))

    out["cooldown_seconds"] = max(0, min(int(out.get("cooldown_seconds") or 0), 86_400))
    out["log_retention_days"] = max(0, min(int(out.get("log_retention_days") or 0), 3650))
    # 2000 is Discord's own limit for a message.
    out["max_length"] = max(1, min(int(out.get("max_length") or 2000), 2000))

    for key in ("log_channel_id", "required_role_id", "blocked_role_id"):
        value = out.get(key)
        out[key] = int(value) if str(value or "").isdigit() else None

    return out


# ── channels ────────────────────────────────────────────────────────


async def get_channel(
    db: aiosqlite.Connection, guild_id: int, channel_id: int
) -> dict | None:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM anon_channels WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None
    data = {key: row[key] for key in row.keys()}
    settings = normalise(data)
    settings["channel_id"] = int(data["channel_id"])
    return settings


async def list_channels(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM anon_channels WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        rows = await cursor.fetchall()

    out = []
    for row in rows:
        data = {key: row[key] for key in row.keys()}
        settings = normalise(data)
        settings["channel_id"] = int(data["channel_id"])
        out.append(settings)
    return out


async def all_channel_ids(db: aiosqlite.Connection) -> dict[int, set[int]]:
    """{guild_id: {channel_id}} — used to prime the cog's cache."""
    async with db.execute(
        "SELECT guild_id, channel_id FROM anon_channels"
        " WHERE COALESCE(enabled, 1) = 1"
    ) as cursor:
        rows = await cursor.fetchall()

    grouped: dict[int, set[int]] = {}
    for guild_id, channel_id in rows:
        grouped.setdefault(int(guild_id), set()).add(int(channel_id))
    return grouped


async def save_channel(
    db: aiosqlite.Connection, guild_id: int, channel_id: int, updates: dict
) -> dict:
    """Write only the keys given; the rest keep their stored value."""
    current = await get_channel(db, guild_id, channel_id) or normalise({})
    merged = normalise({**current, **{
        k: v for k, v in updates.items() if k in DEFAULTS
    }})

    columns = list(DEFAULTS)
    await db.execute(
        f"INSERT OR REPLACE INTO anon_channels (guild_id, channel_id, {', '.join(columns)})"
        f" VALUES ({', '.join('?' * (len(columns) + 2))})",
        [guild_id, channel_id] + [merged[name] for name in columns],
    )
    await db.commit()

    merged["channel_id"] = channel_id
    return merged


async def delete_channel(
    db: aiosqlite.Connection, guild_id: int, channel_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM anon_channels WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


# ── blocked members ─────────────────────────────────────────────────


async def is_blocked(db: aiosqlite.Connection, guild_id: int, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM anon_blocked WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ) as cursor:
        return await cursor.fetchone() is not None


async def block(
    db: aiosqlite.Connection, guild_id: int, user_id: int,
    *, reason: str = "", by_id: int = 0,
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO anon_blocked (guild_id, user_id, reason, by_id, at)"
        " VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, str(reason or "")[:200], by_id, time.time()),
    )
    await db.commit()


async def unblock(db: aiosqlite.Connection, guild_id: int, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM anon_blocked WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def blocked_list(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT user_id, reason, at FROM anon_blocked WHERE guild_id = ?"
        " ORDER BY at DESC",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {"user_id": int(r[0]), "reason": r[1] or "", "at": float(r[2] or 0)}
        for r in rows
    ]


# ── log ─────────────────────────────────────────────────────────────


async def log_message(
    db: aiosqlite.Connection, guild_id: int, channel_id: int, user_id: int,
    content: str, message_id: int | None = None,
) -> None:
    await db.execute(
        "INSERT INTO anon_log (guild_id, channel_id, user_id, message_id, content, at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, user_id, message_id, str(content or "")[:2000],
         time.time()),
    )
    await db.commit()


async def recent_log(
    db: aiosqlite.Connection, guild_id: int, *, limit: int = 50, user_id: int = 0
) -> list[dict]:
    query = "SELECT * FROM anon_log WHERE guild_id = ?"
    params: list[Any] = [guild_id]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY at DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))

    db.row_factory = aiosqlite.Row
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "channel_id": int(row["channel_id"]),
            "user_id": int(row["user_id"]),
            "message_id": int(row["message_id"]) if row["message_id"] else None,
            "content": row["content"] or "",
            "at": float(row["at"]),
        }
        for row in rows
    ]


async def find_author(
    db: aiosqlite.Connection, guild_id: int, message_id: int
) -> int | None:
    """Who wrote the anonymous message with this id."""
    async with db.execute(
        "SELECT user_id FROM anon_log WHERE guild_id = ? AND message_id = ?",
        (guild_id, message_id),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def prune_log(db: aiosqlite.Connection, guild_id: int, days: int) -> int:
    """
    Drop log rows older than `days`.

    Keeping every anonymous message forever is both a privacy problem and
    a slowly growing database; 0 means the guild opted out of pruning.
    """
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86_400
    cursor = await db.execute(
        "DELETE FROM anon_log WHERE guild_id = ? AND at < ?", (guild_id, cutoff)
    )
    await db.commit()
    return cursor.rowcount or 0


async def stats(db: aiosqlite.Connection, guild_id: int) -> dict:
    async with db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT user_id) FROM anon_log WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        total, people = await cursor.fetchone()

    day_ago = time.time() - 86_400
    async with db.execute(
        "SELECT COUNT(*) FROM anon_log WHERE guild_id = ? AND at >= ?",
        (guild_id, day_ago),
    ) as cursor:
        today = (await cursor.fetchone())[0]

    return {
        "messages": int(total or 0),
        "people": int(people or 0),
        "last_24h": int(today or 0),
    }


# ── checks before re-posting ────────────────────────────────────────


def clean_content(text: str, settings: dict) -> str:
    """
    Strip what the guild does not allow.

    Mentions are off by default: being able to ping @everyone from behind
    a mask is exactly the kind of thing an anonymous channel gets abused
    for.
    """
    import re

    out = str(text or "")

    if not settings.get("allow_mentions"):
        # A zero-width space between the @ and the name: still readable,
        # no longer notifies anybody.
        zwsp = "\u200b"
        out = out.replace("@everyone", f"@{zwsp}everyone")
        out = out.replace("@here", f"@{zwsp}here")
        # Built by concatenation, not as an r"" literal: `\u200b` inside a
        # replacement string is parsed as a regex escape and raises
        # "bad escape \u", which took down every message with a role ping.
        out = re.sub(r"<@&(\d+)>", "<@" + zwsp + r"&\1>", out)

    if not settings.get("allow_links"):
        out = re.sub(r"https?://\S+", "[Link entfernt]", out)

    return out[: settings.get("max_length", 2000)]


async def why_not(
    db: aiosqlite.Connection, settings: dict, member, content: str,
    *, has_files: bool = False,
) -> str | None:
    """
    Why this member may not post here, in plain German. None = allowed.

    `has_files` is passed in rather than read off `member`. It used to be
    smuggled across as `member._has_files`, which works on a plain test
    double but not on the real thing: `discord.Member` defines
    `__slots__` and has no `__dict__`, so the assignment raised

        AttributeError: 'Member' object has no attribute '_has_files'
                        and no __dict__ for setting new attributes

    and took the whole relay down with it before the original message was
    even deleted -- the channel then behaved as if the feature was off.
    """
    import datetime as _dt

    guild = getattr(member, "guild", None)
    guild_id = guild.id if guild else 0

    if await is_blocked(db, guild_id, member.id):
        return "Du darfst hier nicht anonym schreiben."

    role_ids = {r.id for r in getattr(member, "roles", [])}

    required = settings.get("required_role_id")
    if required and int(required) not in role_ids:
        return "Dir fehlt die nötige Rolle für diesen Kanal."

    blocked = settings.get("blocked_role_id")
    if blocked and int(blocked) in role_ids:
        return "Mit deiner Rolle kannst du hier nicht anonym schreiben."

    now = _dt.datetime.now(_dt.timezone.utc)

    min_account = int(settings.get("min_account_days") or 0)
    created = getattr(member, "created_at", None)
    if min_account and created is not None:
        age = (now - created).days
        if age < min_account:
            return (
                f"Dein Account muss {min_account} Tage alt sein (er ist {age})."
            )

    min_member = int(settings.get("min_member_days") or 0)
    joined = getattr(member, "joined_at", None)
    if min_member and joined is not None:
        days = (now - joined).days
        if days < min_member:
            return f"Du musst {min_member} Tage auf dem Server sein (du bist {days})."

    if not settings.get("allow_attachments") and has_files:
        return "In diesem Kanal sind keine Anhänge erlaubt."

    if not str(content or "").strip():
        return "Leere Nachrichten werden nicht weitergeleitet."

    return None
