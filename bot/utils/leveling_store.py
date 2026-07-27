# ╔══════════════════════════════════════════════════════════════════╗
# ║   Leveling: storage, XP curve, settings                          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The leveling system's data layer, shared by the cog and the dashboard.

Why this exists rather than the old cog owning everything:

  * The old code kept the same numbers in **two** tables, `user_xp` and
    `users`. `on_message` wrote both, `/rank` and the leaderboard read
    `user_xp`, but `resetxp`, `setxp` and `setlevel` wrote `users`. So
    the admin commands appeared to work and changed nothing at all.
    There is one table now, `levels`.
  * `min_xp` / `max_xp` were stored, shown in the setup dialog and never
    used — every message was worth exactly `xp_per_message`. XP is
    random between min and max now, which is what those fields promised.
  * `dm_level_up` was stored and never read.
  * The level-up embed computed a colour from the settings and then hard
    coded `color=0xFF0000` on the next line.
  * Settings were read by tuple index (`row[7]`, `row[11]`), so adding a
    column anywhere but at the end silently shifted every value.

Everything here works on plain dicts and one aiosqlite connection so it
can be tested without a bot.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any

import aiosqlite

DB_PATH = "db/leveling.db"

# ── XP curve ────────────────────────────────────────────────────────
#
# level = floor(sqrt(xp / 100)) — the curve the old code used. Keeping it
# means nobody loses a level when this ships.

CURVE_FACTOR = 100


def level_from_xp(xp: int) -> int:
    """Which level a given amount of XP is worth."""
    if not xp or xp < 0:
        return 0
    return int(math.sqrt(xp / CURVE_FACTOR))


def xp_for_level(level: int) -> int:
    """How much XP is needed to reach `level`."""
    if level <= 0:
        return 0
    return level * level * CURVE_FACTOR


def progress(xp: int) -> tuple[int, int, int]:
    """(level, xp into this level, xp this level needs in total)."""
    level = level_from_xp(xp)
    start = xp_for_level(level)
    end = xp_for_level(level + 1)
    return level, xp - start, end - start


# ── Settings ────────────────────────────────────────────────────────
#
# One dict describes the whole configuration. The defaults double as the
# column list, so adding a setting means adding one line here.

DEFAULTS: dict[str, Any] = {
    "enabled": 0,
    "channel_id": None,          # None = reply where the member wrote
    "announce_mode": "channel",  # channel | dm | off
    "level_message": "🎉 {user} ist jetzt **Level {level}**!",
    "embed_color": 0x5865F2,
    "level_image": None,
    "thumbnail_enabled": 1,
    "min_xp": 15,
    "max_xp": 25,
    "cooldown_seconds": 60,
    # Delete what the bot posts after N seconds. 0 = keep it.
    "delete_after": 0,           # level-up announcements
    "command_delete_after": 0,   # replies to /rank, /leaderboard, …
    "delete_command_message": 0, # also remove the member's own command
    "card_style": "image",       # image | text
    "stack_roles": 1,            # keep older reward roles when levelling
}

BOOLEAN_KEYS = {
    "enabled", "thumbnail_enabled", "delete_command_message", "stack_roles",
}
ANNOUNCE_MODES = {"channel", "dm", "off"}
CARD_STYLES = {"image", "text"}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the tables and add any column a newer version introduced."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS levels (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            messages INTEGER DEFAULT 0,
            last_message REAL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    # Ranking reads "everyone in this guild ordered by xp" on every /rank.
    await db.execute(
        "CREATE INDEX IF NOT EXISTS levels_guild_xp ON levels (guild_id, xp DESC)"
    )

    await db.execute(
        "CREATE TABLE IF NOT EXISTS leveling_settings (guild_id INTEGER PRIMARY KEY)"
    )

    # Reward roles per level.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS level_rewards (
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, level)
        )
        """
    )

    # Multipliers and exclusions, both keyed by role or channel.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS level_multipliers (
            guild_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            multiplier REAL DEFAULT 1.0,
            PRIMARY KEY (guild_id, target_id, target_type)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS level_excluded (
            guild_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            PRIMARY KEY (guild_id, target_id, target_type)
        )
        """
    )

    # Settings columns come from DEFAULTS, so a new setting is one line.
    async with db.execute("PRAGMA table_info([leveling_settings])") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}

    for name, value in DEFAULTS.items():
        if name in existing:
            continue
        if isinstance(value, str):
            kind = "TEXT"
        elif isinstance(value, float):
            kind = "REAL"
        else:
            kind = "INTEGER"
        try:
            await db.execute(
                f"ALTER TABLE leveling_settings ADD COLUMN {name} {kind}"
            )
        except Exception:
            pass

    await db.commit()
    await migrate(db)


async def migrate(db: aiosqlite.Connection) -> None:
    """
    Carry the old tables over, once.

    `user_xp` held the numbers the members actually earned; `users` held a
    copy that the admin commands wrote to and nothing read. Only `user_xp`
    is worth keeping. `leveling_settings` gains its new columns above, so
    the settings survive untouched.
    """
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cursor:
        tables = {row[0] for row in await cursor.fetchall()}

    if "user_xp" in tables:
        async with db.execute("SELECT COUNT(*) FROM levels") as cursor:
            already = (await cursor.fetchone())[0]
        if not already:
            await db.execute(
                "INSERT OR IGNORE INTO levels (guild_id, user_id, xp, messages)"
                " SELECT guild_id, user_id, COALESCE(xp, 0), COALESCE(messages, 0)"
                " FROM user_xp"
            )

    # The old reward table had a `remove_previous` flag per row; that is a
    # per-guild decision now (`stack_roles`), so only level→role moves.
    if "level_rewards" in tables:
        async with db.execute("PRAGMA table_info([level_rewards])") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "remove_previous" in columns:
            # Any row that wanted the old roles removed switches the guild
            # to non-stacking, which is the closest honest equivalent.
            await db.execute(
                "UPDATE leveling_settings SET stack_roles = 0 WHERE guild_id IN"
                " (SELECT DISTINCT guild_id FROM level_rewards WHERE remove_previous = 1)"
            )

    if "level_roles" in tables:
        await db.execute(
            "INSERT OR IGNORE INTO level_rewards (guild_id, level, role_id)"
            " SELECT guild_id, level, role_id FROM level_roles"
        )

    if "xp_multipliers" in tables:
        await db.execute(
            "INSERT OR IGNORE INTO level_multipliers"
            " (guild_id, target_id, target_type, multiplier)"
            " SELECT guild_id, target_id, target_type, multiplier"
            " FROM xp_multipliers WHERE target_type IS NOT NULL"
        )

    if "leveling_blacklist" in tables:
        async with db.execute("PRAGMA table_info([leveling_blacklist])") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "target_type" in columns:
            await db.execute(
                "INSERT OR IGNORE INTO level_excluded (guild_id, target_id, target_type)"
                " SELECT guild_id, target_id, target_type FROM leveling_blacklist"
                " WHERE target_type IS NOT NULL"
            )

    await db.commit()


def normalise(settings: dict) -> dict:
    """Clamp everything to a sane range and fix the obvious mistakes."""
    out = dict(DEFAULTS)
    out.update({k: v for k, v in settings.items() if k in DEFAULTS})

    for key in BOOLEAN_KEYS:
        out[key] = 1 if out.get(key) else 0

    out["min_xp"] = max(0, min(int(out.get("min_xp") or 0), 10_000))
    out["max_xp"] = max(0, min(int(out.get("max_xp") or 0), 10_000))
    # A max below the min would make random.randint raise.
    if out["max_xp"] < out["min_xp"]:
        out["max_xp"] = out["min_xp"]

    out["cooldown_seconds"] = max(0, min(int(out.get("cooldown_seconds") or 0), 86_400))
    out["delete_after"] = max(0, min(int(out.get("delete_after") or 0), 86_400))
    out["command_delete_after"] = max(
        0, min(int(out.get("command_delete_after") or 0), 86_400)
    )

    if out.get("announce_mode") not in ANNOUNCE_MODES:
        out["announce_mode"] = "channel"
    if out.get("card_style") not in CARD_STYLES:
        out["card_style"] = "image"

    colour = out.get("embed_color")
    if isinstance(colour, str):
        try:
            colour = int(colour.lstrip("#"), 16)
        except ValueError:
            colour = DEFAULTS["embed_color"]
    out["embed_color"] = max(0, min(int(colour or 0), 0xFFFFFF))

    out["level_message"] = str(out.get("level_message") or DEFAULTS["level_message"])[:1000]

    channel = out.get("channel_id")
    out["channel_id"] = int(channel) if str(channel or "").isdigit() else None

    image = out.get("level_image")
    out["level_image"] = str(image)[:400] if image else None

    return out


async def get_settings(db: aiosqlite.Connection, guild_id: int) -> dict:
    """
    Settings for a guild, by column name.

    The old version indexed the row by position, so inserting a column
    anywhere but the end shifted every value after it — `xp_per_message`
    could come back as the cooldown.
    """
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM leveling_settings WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return normalise({})
    return normalise({key: row[key] for key in row.keys() if key != "guild_id"})


async def save_settings(
    db: aiosqlite.Connection, guild_id: int, updates: dict
) -> dict:
    """
    Write only the keys given, leaving the rest alone.

    A PATCH that rebuilt every column from defaults is how the guild
    settings page used to wipe switches it never showed.
    """
    updates = {k: v for k, v in updates.items() if k in DEFAULTS}
    if not updates:
        return await get_settings(db, guild_id)

    current = await get_settings(db, guild_id)
    merged = normalise({**current, **updates})

    columns = list(DEFAULTS)
    await db.execute(
        f"INSERT OR REPLACE INTO leveling_settings (guild_id, {', '.join(columns)})"
        f" VALUES ({', '.join('?' * (len(columns) + 1))})",
        [guild_id] + [merged[name] for name in columns],
    )
    await db.commit()
    return merged


# ── XP ──────────────────────────────────────────────────────────────


async def is_excluded(
    db: aiosqlite.Connection, guild_id: int, *, channel_id: int = 0, role_ids=()
) -> bool:
    """Whether this channel or any of these roles is excluded from XP."""
    async with db.execute(
        "SELECT target_id, target_type FROM level_excluded WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    roles = set(role_ids)
    for target_id, target_type in rows:
        if target_type == "channel" and int(target_id) == int(channel_id):
            return True
        if target_type == "role" and int(target_id) in roles:
            return True
    return False


async def multiplier_for(
    db: aiosqlite.Connection, guild_id: int, *, channel_id: int = 0, role_ids=()
) -> float:
    """
    The XP multiplier that applies here.

    Role multipliers do not stack: the highest one wins. Multiplying them
    together meant three 2× roles turned into 8×, which is never what a
    server owner pictures.
    """
    async with db.execute(
        "SELECT target_id, target_type, multiplier FROM level_multipliers"
        " WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    roles = set(role_ids)
    best_role = 1.0
    channel_multiplier = 1.0

    for target_id, target_type, value in rows:
        value = float(value or 1.0)
        if target_type == "role" and int(target_id) in roles:
            best_role = max(best_role, value)
        elif target_type == "channel" and int(target_id) == int(channel_id):
            channel_multiplier = value

    return round(best_role * channel_multiplier, 4)


async def get_user(db: aiosqlite.Connection, guild_id: int, user_id: int) -> dict:
    """One member's row, with the level worked out."""
    async with db.execute(
        "SELECT xp, messages, last_message FROM levels"
        " WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()

    xp = int(row[0] or 0) if row else 0
    return {
        "user_id": user_id,
        "xp": xp,
        "level": level_from_xp(xp),
        "messages": int(row[1] or 0) if row else 0,
        "last_message": float(row[2] or 0) if row else 0.0,
    }


async def get_rank(db: aiosqlite.Connection, guild_id: int, user_id: int) -> int:
    """Position on the leaderboard, 1 being the top."""
    async with db.execute(
        "SELECT COUNT(*) + 1 FROM levels WHERE guild_id = ? AND xp >"
        " (SELECT COALESCE(MAX(xp), -1) FROM levels WHERE guild_id = ? AND user_id = ?)",
        (guild_id, guild_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 1


async def add_xp(
    db: aiosqlite.Connection, guild_id: int, user_id: int, amount: int
) -> tuple[int, int, int]:
    """
    Add XP and report (new xp, level before, level after).

    One UPSERT rather than SELECT-then-INSERT-or-UPDATE: two members
    talking at once could both read "no row" and the second INSERT would
    fail on the primary key.
    """
    before = await get_user(db, guild_id, user_id)
    new_xp = max(0, before["xp"] + int(amount))

    await db.execute(
        "INSERT INTO levels (guild_id, user_id, xp, messages, last_message)"
        " VALUES (?, ?, ?, 1, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET"
        "   xp = excluded.xp,"
        "   messages = levels.messages + 1,"
        "   last_message = excluded.last_message",
        (guild_id, user_id, new_xp, time.time()),
    )
    await db.commit()

    return new_xp, before["level"], level_from_xp(new_xp)


async def set_xp(
    db: aiosqlite.Connection, guild_id: int, user_id: int, xp: int
) -> dict:
    """
    Set someone's XP outright.

    This is the command that did nothing before: it wrote to `users`
    while everything else read `user_xp`.
    """
    xp = max(0, int(xp))
    await db.execute(
        "INSERT INTO levels (guild_id, user_id, xp) VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = excluded.xp",
        (guild_id, user_id, xp),
    )
    await db.commit()
    return await get_user(db, guild_id, user_id)


async def reset_user(db: aiosqlite.Connection, guild_id: int, user_id: int) -> None:
    await db.execute(
        "DELETE FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    )
    await db.commit()


async def reset_guild(db: aiosqlite.Connection, guild_id: int) -> int:
    cursor = await db.execute("DELETE FROM levels WHERE guild_id = ?", (guild_id,))
    await db.commit()
    return cursor.rowcount or 0


async def leaderboard(
    db: aiosqlite.Connection, guild_id: int, limit: int = 10, offset: int = 0
) -> list[dict]:
    async with db.execute(
        "SELECT user_id, xp, messages FROM levels WHERE guild_id = ?"
        " ORDER BY xp DESC, user_id ASC LIMIT ? OFFSET ?",
        (guild_id, max(1, min(limit, 100)), max(0, offset)),
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        {
            "rank": offset + index + 1,
            "user_id": int(row[0]),
            "xp": int(row[1] or 0),
            "level": level_from_xp(int(row[1] or 0)),
            "messages": int(row[2] or 0),
        }
        for index, row in enumerate(rows)
    ]


async def guild_stats(db: aiosqlite.Connection, guild_id: int) -> dict:
    async with db.execute(
        "SELECT COUNT(*), COALESCE(SUM(xp), 0), COALESCE(SUM(messages), 0),"
        " COALESCE(MAX(xp), 0) FROM levels WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    members, total_xp, messages, top_xp = row or (0, 0, 0, 0)
    return {
        "members": int(members),
        "total_xp": int(total_xp),
        "messages": int(messages),
        "top_level": level_from_xp(int(top_xp)),
    }


# ── Rewards ─────────────────────────────────────────────────────────


async def rewards(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT level, role_id FROM level_rewards WHERE guild_id = ? ORDER BY level",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"level": int(r[0]), "role_id": int(r[1])} for r in rows]


async def set_reward(
    db: aiosqlite.Connection, guild_id: int, level: int, role_id: int
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id)"
        " VALUES (?, ?, ?)",
        (guild_id, max(1, int(level)), int(role_id)),
    )
    await db.commit()


async def remove_reward(db: aiosqlite.Connection, guild_id: int, level: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM level_rewards WHERE guild_id = ? AND level = ?",
        (guild_id, int(level)),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def roles_for_level(
    db: aiosqlite.Connection, guild_id: int, level: int, *, stack: bool = True
) -> tuple[list[int], list[int]]:
    """
    (roles to add, roles to take away) for somebody who just hit `level`.

    With stacking off, only the highest earned role is kept — the old
    code stored that as a per-row flag and applied it inconsistently.
    """
    earned = [r for r in await rewards(db, guild_id) if r["level"] <= level]
    if not earned:
        return [], []

    if stack:
        return [r["role_id"] for r in earned], []

    keep = earned[-1]["role_id"]
    return [keep], [r["role_id"] for r in earned if r["role_id"] != keep]


# ── Multipliers and exclusions ──────────────────────────────────────


async def multipliers(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT target_id, target_type, multiplier FROM level_multipliers"
        " WHERE guild_id = ? ORDER BY target_type, multiplier DESC",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {"target_id": int(r[0]), "target_type": r[1], "multiplier": float(r[2] or 1.0)}
        for r in rows
    ]


async def set_multiplier(
    db: aiosqlite.Connection, guild_id: int, target_id: int,
    target_type: str, value: float,
) -> None:
    value = max(0.0, min(float(value), 100.0))
    await db.execute(
        "INSERT OR REPLACE INTO level_multipliers"
        " (guild_id, target_id, target_type, multiplier) VALUES (?, ?, ?, ?)",
        (guild_id, int(target_id), target_type, value),
    )
    await db.commit()


async def remove_multiplier(
    db: aiosqlite.Connection, guild_id: int, target_id: int, target_type: str
) -> bool:
    cursor = await db.execute(
        "DELETE FROM level_multipliers WHERE guild_id = ? AND target_id = ?"
        " AND target_type = ?",
        (guild_id, int(target_id), target_type),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def excluded(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT target_id, target_type FROM level_excluded WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"target_id": int(r[0]), "target_type": r[1]} for r in rows]


async def add_excluded(
    db: aiosqlite.Connection, guild_id: int, target_id: int, target_type: str
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO level_excluded (guild_id, target_id, target_type)"
        " VALUES (?, ?, ?)",
        (guild_id, int(target_id), target_type),
    )
    await db.commit()


async def remove_excluded(
    db: aiosqlite.Connection, guild_id: int, target_id: int, target_type: str
) -> bool:
    cursor = await db.execute(
        "DELETE FROM level_excluded WHERE guild_id = ? AND target_id = ?"
        " AND target_type = ?",
        (guild_id, int(target_id), target_type),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


# ── Message text ────────────────────────────────────────────────────

PLACEHOLDERS = {
    "user": "Erwähnt das Mitglied (@Name)",
    "user_name": "Der Benutzername",
    "user_nick": "Der Anzeigename",
    "level": "Das neue Level",
    "xp": "Gesamt-XP",
    "rank": "Platz auf der Bestenliste",
    "messages": "Wie viele Nachrichten geschrieben",
    "server": "Name des Servers",
    "next_level": "Das nächste Level",
    "next_xp": "XP bis zum nächsten Level",
}


def fill(text: str, values: dict[str, Any]) -> str:
    """Replace {name} with its value; unknown ones are left as they are."""
    out = str(text or "")
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def roll_xp(settings: dict) -> int:
    """
    XP for one message.

    Random between min_xp and max_xp. The old code stored both, showed
    them in the setup dialog, and then always handed out exactly
    `xp_per_message` — the randomness never existed.
    """
    low = int(settings.get("min_xp", DEFAULTS["min_xp"]))
    high = int(settings.get("max_xp", DEFAULTS["max_xp"]))
    if high < low:
        low, high = high, low
    return random.randint(low, high)
