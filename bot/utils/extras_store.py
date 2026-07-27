# ╔══════════════════════════════════════════════════════════════════╗
# ║   Booster, sticky, nightmode, jail, counting, notify, birthday   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage for seven features that worked but had no dashboard.

Two of them carry real bugs, found while writing this:

  * **notify** declared `type TEXT NOT NULL UNIQUE` with no guild
    column. The moment one server set up a "youtube" notification, no
    other server could — the insert fails on the unique constraint — and
    every server read the same row. Fixed by making the key
    (guild_id, type).
  * **counting** keeps its whole state in `self.counting_data`, loaded
    once at startup. Anything the dashboard writes to the file is
    invisible until the bot restarts, and the cog overwrites it on its
    next save. It needs a reload hook, which is why `counting_reload`
    exists below.

Everything here works on plain dicts so the API and the cogs share one
implementation.
"""

from __future__ import annotations

import json
import os

from typing import Any

import aiosqlite

BOOST_DB = "db/boost.db"
STICKY_DB = "db/stickymessages.db"
NIGHTMODE_DB = "db/nightmode.db"
JAIL_DB = "db/jail.db"
NOTIFY_DB = "db/notify.db"
COUNTING_JSON = "db/counting.json"
BIRTHDAY_JSON = "jsondb/birthdays.json"


# ══════════════════════════════════════════════════════════════════════
#  Booster
# ══════════════════════════════════════════════════════════════════════

BOOST_DEFAULTS: dict[str, Any] = {
    "boost": {
        "channel": [],
        "message": "{user.mention} just boosted {server.name}! 🎉",
        "embed": True,
        "ping": False,
        "image": "",
        "thumbnail": "",
        "autodel": 0,
    },
    "boost_roles": {"roles": []},
}

BOOST_PLACEHOLDERS = {
    "{user.mention}": "Erwähnt den Booster",
    "{user.name}": "Anzeigename",
    "{user.tag}": "Name mit Tag",
    "{server.name}": "Servername",
    "{server.boost_count}": "Wie viele Boosts der Server hat",
    "{server.boost_level}": "Boost-Stufe",
    "{server.member_count}": "Mitgliederzahl",
}


async def boost_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS boost_config ("
        " guild_id INTEGER PRIMARY KEY, config TEXT NOT NULL)"
    )
    await db.commit()


async def boost_get(db: aiosqlite.Connection, guild_id: int) -> dict:
    async with db.execute(
        "SELECT config FROM boost_config WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return json.loads(json.dumps(BOOST_DEFAULTS))  # deep copy

    try:
        stored = json.loads(row[0])
    except (ValueError, TypeError):
        return json.loads(json.dumps(BOOST_DEFAULTS))

    # Merge over the defaults so a config written by an older version
    # does not miss keys the dashboard expects.
    config = json.loads(json.dumps(BOOST_DEFAULTS))
    for section, values in stored.items():
        if isinstance(values, dict) and section in config:
            config[section].update(values)
        else:
            config[section] = values
    return config


async def boost_save(db: aiosqlite.Connection, guild_id: int, updates: dict) -> dict:
    current = await boost_get(db, guild_id)

    for section, values in (updates or {}).items():
        if section not in current:
            continue
        if isinstance(values, dict):
            current[section].update(values)
        else:
            current[section] = values

    boost = current["boost"]
    boost["message"] = str(boost.get("message") or "")[:2000]
    boost["autodel"] = max(0, min(int(boost.get("autodel") or 0), 86400))
    for key in ("image", "thumbnail"):
        value = str(boost.get(key) or "").strip()
        boost[key] = value[:400] if value.startswith(("http://", "https://")) else ""
    boost["embed"] = bool(boost.get("embed"))
    boost["ping"] = bool(boost.get("ping"))
    boost["channel"] = [
        int(c) for c in (boost.get("channel") or []) if str(c).isdigit()
    ][:10]

    current["boost_roles"]["roles"] = [
        int(r) for r in (current["boost_roles"].get("roles") or []) if str(r).isdigit()
    ][:25]

    await db.execute(
        "INSERT OR REPLACE INTO boost_config (guild_id, config) VALUES (?, ?)",
        (guild_id, json.dumps(current)),
    )
    await db.commit()
    return current


# ══════════════════════════════════════════════════════════════════════
#  Sticky messages
# ══════════════════════════════════════════════════════════════════════


async def sticky_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            message TEXT,
            last_message_id INTEGER
        )
        """
    )
    await db.commit()


async def sticky_list(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT channel_id, message, last_message_id FROM sticky_messages"
        " WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {
            "channel_id": int(r[0]),
            "message": r[1] or "",
            "last_message_id": int(r[2]) if r[2] else None,
        }
        for r in rows
    ]


async def sticky_set(
    db: aiosqlite.Connection, guild_id: int, channel_id: int, message: str
) -> None:
    await db.execute(
        "INSERT INTO sticky_messages (channel_id, guild_id, message, last_message_id)"
        " VALUES (?, ?, ?, NULL)"
        " ON CONFLICT(channel_id) DO UPDATE SET"
        "   guild_id = excluded.guild_id, message = excluded.message",
        (channel_id, guild_id, str(message)[:2000]),
    )
    await db.commit()


async def sticky_remove(
    db: aiosqlite.Connection, guild_id: int, channel_id: int
) -> int | None:
    """Returns the id of the last posted message so the caller can delete it."""
    async with db.execute(
        "SELECT last_message_id FROM sticky_messages"
        " WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None

    await db.execute(
        "DELETE FROM sticky_messages WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    await db.commit()
    return int(row[0]) if row[0] else 0


# ══════════════════════════════════════════════════════════════════════
#  Nightmode
# ══════════════════════════════════════════════════════════════════════


async def nightmode_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS Nightmode (
            guildId TEXT,
            roleId TEXT,
            adminPermissions INTEGER
        )
        """
    )
    # A schedule the old version did not have: it could only be switched
    # on and off by hand, which is not much of a "night" mode.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS nightmode_schedule (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            start_hour INTEGER DEFAULT 23,
            end_hour INTEGER DEFAULT 7,
            timezone TEXT DEFAULT 'Europe/Berlin',
            channels TEXT DEFAULT '[]',
            active INTEGER DEFAULT 0
        )
        """
    )
    await db.commit()


NIGHTMODE_DEFAULTS = {
    "enabled": 0,
    "start_hour": 23,
    "end_hour": 7,
    "timezone": "Europe/Berlin",
    "channels": [],
    "active": 0,
}


async def nightmode_get(db: aiosqlite.Connection, guild_id: int) -> dict:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM nightmode_schedule WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return dict(NIGHTMODE_DEFAULTS)

    data = dict(row)
    try:
        channels = json.loads(data.get("channels") or "[]")
    except ValueError:
        channels = []

    return {
        "enabled": int(data.get("enabled") or 0),
        "start_hour": int(data.get("start_hour") or 23),
        "end_hour": int(data.get("end_hour") or 7),
        "timezone": data.get("timezone") or "Europe/Berlin",
        "channels": [int(c) for c in channels if str(c).isdigit()],
        "active": int(data.get("active") or 0),
    }


async def nightmode_save(
    db: aiosqlite.Connection, guild_id: int, updates: dict
) -> dict:
    current = await nightmode_get(db, guild_id)
    merged = {**current, **{
        k: v for k, v in updates.items() if k in NIGHTMODE_DEFAULTS
    }}

    merged["enabled"] = 1 if merged.get("enabled") else 0
    merged["active"] = 1 if merged.get("active") else 0
    merged["start_hour"] = max(0, min(int(merged.get("start_hour") or 0), 23))
    merged["end_hour"] = max(0, min(int(merged.get("end_hour") or 0), 23))
    merged["channels"] = [
        int(c) for c in (merged.get("channels") or []) if str(c).isdigit()
    ][:50]

    await db.execute(
        "INSERT OR REPLACE INTO nightmode_schedule"
        " (guild_id, enabled, start_hour, end_hour, timezone, channels, active)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, merged["enabled"], merged["start_hour"], merged["end_hour"],
         merged["timezone"], json.dumps(merged["channels"]), merged["active"]),
    )
    await db.commit()
    return merged


def nightmode_should_be_closed(settings: dict, now_hour: int) -> bool:
    """
    Whether the channels should be shut at this hour.

    The window usually crosses midnight (23 to 7), so a plain
    `start <= hour < end` is wrong for exactly the case this feature is
    for.
    """
    if not settings.get("enabled"):
        return False

    start = int(settings.get("start_hour", 23))
    end = int(settings.get("end_hour", 7))

    if start == end:
        return False
    if start < end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end


async def nightmode_all(db: aiosqlite.Connection) -> list[dict]:
    """Every guild with a schedule, for the loop that opens and closes."""
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT guild_id FROM nightmode_schedule WHERE enabled = 1"
    ) as cursor:
        ids = [int(row[0]) for row in await cursor.fetchall()]

    out = []
    for guild_id in ids:
        settings = await nightmode_get(db, guild_id)
        settings["guild_id"] = guild_id
        out.append(settings)
    return out


# ══════════════════════════════════════════════════════════════════════
#  Jail
# ══════════════════════════════════════════════════════════════════════


async def jail_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS jail_settings (
            guild_id TEXT PRIMARY KEY,
            jail_role TEXT,
            jail_channel TEXT,
            mod_role TEXT,
            log_channel TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS jailed (
            guild_id TEXT,
            user_id TEXT,
            mod_id TEXT,
            reason TEXT,
            jailed_at TEXT,
            duration INTEGER,
            roles TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    await db.commit()


async def jail_settings(db: aiosqlite.Connection, guild_id: int) -> dict:
    async with db.execute(
        "SELECT jail_role, jail_channel, mod_role, log_channel FROM jail_settings"
        " WHERE guild_id = ?",
        (str(guild_id),),
    ) as cursor:
        row = await cursor.fetchone()

    keys = ("jail_role", "jail_channel", "mod_role", "log_channel")
    if row is None:
        return {key: None for key in keys}
    return {
        key: int(value) if str(value or "").isdigit() else None
        for key, value in zip(keys, row)
    }


async def jail_save(db: aiosqlite.Connection, guild_id: int, updates: dict) -> dict:
    current = await jail_settings(db, guild_id)
    merged = {**current, **{
        k: v for k, v in updates.items() if k in current
    }}
    for key, value in merged.items():
        merged[key] = int(value) if str(value or "").isdigit() else None

    await db.execute(
        "INSERT OR REPLACE INTO jail_settings"
        " (guild_id, jail_role, jail_channel, mod_role, log_channel)"
        " VALUES (?, ?, ?, ?, ?)",
        (str(guild_id),
         str(merged["jail_role"]) if merged["jail_role"] else None,
         str(merged["jail_channel"]) if merged["jail_channel"] else None,
         str(merged["mod_role"]) if merged["mod_role"] else None,
         str(merged["log_channel"]) if merged["log_channel"] else None),
    )
    await db.commit()
    return merged


async def jail_inmates(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT user_id, mod_id, reason, jailed_at, duration FROM jailed"
        " WHERE guild_id = ?",
        (str(guild_id),),
    ) as cursor:
        rows = await cursor.fetchall()

    out = []
    for user_id, mod_id, reason, jailed_at, duration in rows:
        out.append({
            "user_id": int(user_id),
            "mod_id": int(mod_id) if str(mod_id or "").isdigit() else 0,
            "reason": reason or "",
            "jailed_at": jailed_at or "",
            "duration": int(duration or 0),
        })
    return out


# ══════════════════════════════════════════════════════════════════════
#  Counting
# ══════════════════════════════════════════════════════════════════════

COUNTING_DEFAULTS = {
    "enabled": False,
    "channel": None,
    "current": 0,
    "last_user": None,
    "mode": "reset",            # reset | continue
    "high_score": 0,
    "high_score_at": None,
    # Require a different member for each number. This is the classic
    # "no double counting" rule; off by default so small servers where
    # one person counts alone are not locked out.
    "require_alternate": False,
    # What happens on a broken rule. Kept separate because a server may
    # want a wrong number to be fatal while a double post is only
    # rejected, or the other way round.
    "wrong_number_mode": None,  # None -> follow "mode"
    "double_post_mode": None,   # None -> follow "mode"
    # Delete the offending message instead of leaving it in the channel.
    "delete_wrong": True,
    # Let normal chat stay. When off, anything that is not a number is
    # removed. Prefix commands are always left alone either way.
    "allow_chat": True,
    # React to a correct number.
    "react_success": True,
    "success_emoji": "",        # "" -> the bot's tick emoji
    # Celebrate every N numbers with a milestone note.
    "milestone_every": 100,
    "save_record": True,
}

# Keys the old cog used before the dashboard existed. The cog wrote
# "count" and "reset_on_fail" while the dashboard reads "current" and
# "mode" — a server configured through chat commands looked empty in the
# dashboard, and saving from the dashboard reset the counter in chat.
COUNTING_LEGACY_KEYS = {"count": "current", "reset_on_fail": "mode"}


def counting_migrate(entry: dict) -> dict:
    """
    Fold pre-dashboard keys into the current shape.

    Returns a new dict; the caller decides whether to write it back.
    """
    entry = dict(entry or {})

    if "current" not in entry and "count" in entry:
        entry["current"] = entry.get("count") or 0
    if "mode" not in entry and "reset_on_fail" in entry:
        entry["mode"] = "reset" if entry.get("reset_on_fail") else "continue"

    entry.pop("count", None)
    entry.pop("reset_on_fail", None)
    return entry


def counting_load() -> dict:
    if not os.path.exists(COUNTING_JSON):
        return {}
    try:
        with open(COUNTING_JSON, "r") as handle:
            content = handle.read().strip()
        data = json.loads(content) if content else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def counting_save_all(data: dict) -> None:
    os.makedirs(os.path.dirname(COUNTING_JSON) or ".", exist_ok=True)
    tmp = f"{COUNTING_JSON}.tmp"
    # Written to a temp file first: the cog reads this file on every
    # dashboard change, and a half-written file would make json.load
    # raise and silently drop the whole server's settings.
    with open(tmp, "w") as handle:
        json.dump(data, handle, indent=4)
    os.replace(tmp, COUNTING_JSON)


def counting_get(guild_id: int) -> dict:
    data = counting_load()
    entry = counting_migrate(data.get(str(guild_id)) or {})
    return {**COUNTING_DEFAULTS, **entry}


def _counting_mode(value, fallback: str = "reset") -> str:
    return value if value in ("reset", "continue") else fallback


def counting_normalise(entry: dict) -> dict:
    """Force every field into the type the rest of the code expects."""
    entry = {**COUNTING_DEFAULTS, **counting_migrate(entry)}

    entry["enabled"] = bool(entry.get("enabled"))
    entry["current"] = max(0, int(entry.get("current") or 0))
    entry["high_score"] = max(0, int(entry.get("high_score") or 0))
    entry["mode"] = _counting_mode(entry.get("mode"))

    for key in ("wrong_number_mode", "double_post_mode"):
        value = entry.get(key)
        entry[key] = value if value in ("reset", "continue") else None

    for key in ("require_alternate", "delete_wrong", "allow_chat",
                "react_success", "save_record"):
        entry[key] = bool(entry.get(key))

    milestone = entry.get("milestone_every")
    try:
        milestone = int(milestone)
    except (TypeError, ValueError):
        milestone = 100
    # 0 disables milestones; anything above 10000 just spams.
    entry["milestone_every"] = min(10000, max(0, milestone))

    entry["success_emoji"] = str(entry.get("success_emoji") or "")[:64]

    channel = entry.get("channel")
    entry["channel"] = int(channel) if str(channel or "").isdigit() else None

    last = entry.get("last_user")
    entry["last_user"] = int(last) if str(last or "").isdigit() else None

    at = entry.get("high_score_at")
    entry["high_score_at"] = str(at) if at else None

    return entry


def counting_save(guild_id: int, updates: dict) -> dict:
    data = counting_load()
    entry = {**COUNTING_DEFAULTS, **counting_migrate(data.get(str(guild_id)) or {})}
    entry.update({k: v for k, v in (updates or {}).items() if k in COUNTING_DEFAULTS})

    entry = counting_normalise(entry)
    data[str(guild_id)] = entry
    counting_save_all(data)
    return entry


def counting_effective_mode(settings: dict, kind: str) -> str:
    """
    Which punishment applies to `kind` ("wrong" or "double").

    A per-rule setting wins; otherwise the shared "mode" is used.
    """
    key = "wrong_number_mode" if kind == "wrong" else "double_post_mode"
    return _counting_mode(settings.get(key), _counting_mode(settings.get("mode")))


def counting_judge(settings: dict, author_id: int, content: str) -> dict:
    """
    Decide what to do with one message in the counting channel.

    Pure function so the rules can be tested without a Discord
    connection. Returns a dict with:

      action  -- "ignore" | "count" | "wrong" | "double"
      number  -- the accepted number, when action == "count"
      expected-- the number that was due
      reset   -- whether the counter goes back to 0
      reason  -- short German text for the user
    """
    settings = {**COUNTING_DEFAULTS, **(settings or {})}
    expected = int(settings.get("current") or 0) + 1
    text = (content or "").strip()

    def out(action, **extra):
        return {"action": action, "number": None, "expected": expected,
                "reset": False, "reason": "", **extra}

    if not text:
        return out("ignore")

    number = counting_parse_number(text)

    if number is None:
        # Not a number at all. Either it is chat the server allows, or
        # it gets cleaned up — but it never breaks the streak.
        return out("ignore" if settings.get("allow_chat") else "cleanup")

    if settings.get("require_alternate"):
        last = settings.get("last_user")
        if last is not None and int(last) == int(author_id):
            mode = counting_effective_mode(settings, "double")
            return out(
                "double",
                reset=(mode == "reset"),
                reason="Du warst gerade schon dran — jemand anders muss weiterzählen.",
            )

    if number != expected:
        mode = counting_effective_mode(settings, "wrong")
        return out(
            "wrong",
            reset=(mode == "reset"),
            reason=f"Falsche Zahl. Erwartet war **{expected}**.",
        )

    return out("count", number=number)


def counting_parse_number(text: str) -> int | None:
    """
    Read the number out of a message.

    Only a bare number counts. "5" works, "5!" and "5 lets go" do not —
    accepting those would make it impossible to tell a typo from chat.
    A leading "+" is allowed because phone keyboards insert it.
    """
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("+"):
        text = text[1:].strip()
    # No thousands separators: "1,000" is ambiguous across locales.
    if not text.isdigit():
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def counting_apply(guild_id: int, settings: dict, verdict: dict,
                   author_id: int) -> dict:
    """Persist the outcome of `counting_judge` and report what changed."""
    updates: dict[str, Any] = {}
    record_broken = False

    if verdict["action"] == "count":
        number = int(verdict["number"])
        updates["current"] = number
        updates["last_user"] = int(author_id)
        if settings.get("save_record") and number > int(settings.get("high_score") or 0):
            updates["high_score"] = number
            record_broken = True
    elif verdict["reset"]:
        updates["current"] = 0
        # Cleared so the next counter is never blocked by the person who
        # broke the streak.
        updates["last_user"] = None

    if not updates:
        return {"settings": settings, "record": False}

    saved = counting_save(guild_id, updates)
    return {"settings": saved, "record": record_broken}


# ══════════════════════════════════════════════════════════════════════
#  Notify
# ══════════════════════════════════════════════════════════════════════

NOTIFY_TYPES = ("youtube", "twitch")


async def notify_ensure(db: aiosqlite.Connection) -> None:
    """
    Create the table and add the guild column.

    The original schema was `type TEXT NOT NULL UNIQUE` with no guild at
    all: the first server to configure "youtube" locked every other
    server out of that type, and all of them read the same row.
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL UNIQUE,
            role_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL
        )
        """
    )

    async with db.execute("PRAGMA table_info([notifications])") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if "guild_id" not in columns:
        # SQLite cannot drop a UNIQUE constraint, so the table is rebuilt.
        # Existing rows have no guild; they are kept under guild 0 rather
        # than thrown away, and the dashboard treats those as legacy.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications_new (
                guild_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, type)
            )
            """
        )
        await db.execute(
            "INSERT OR IGNORE INTO notifications_new (guild_id, type, role_id, channel_id)"
            " SELECT 0, type, role_id, channel_id FROM notifications"
        )
        await db.execute("DROP TABLE notifications")
        await db.execute("ALTER TABLE notifications_new RENAME TO notifications")

    await db.commit()


async def notify_list(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT type, role_id, channel_id, guild_id FROM notifications"
        " WHERE guild_id = ? OR guild_id = 0",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {
            "type": r[0],
            "role_id": int(r[1]),
            "channel_id": int(r[2]),
            "legacy": int(r[3] or 0) == 0,
        }
        for r in rows
    ]


async def notify_set(
    db: aiosqlite.Connection, guild_id: int, kind: str,
    role_id: int, channel_id: int,
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO notifications (guild_id, type, role_id, channel_id)"
        " VALUES (?, ?, ?, ?)",
        (guild_id, kind, int(role_id), int(channel_id)),
    )
    await db.commit()


async def notify_remove(db: aiosqlite.Connection, guild_id: int, kind: str) -> bool:
    cursor = await db.execute(
        "DELETE FROM notifications WHERE guild_id = ? AND type = ?",
        (guild_id, kind),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


# ══════════════════════════════════════════════════════════════════════
#  Birthdays
# ══════════════════════════════════════════════════════════════════════


def birthday_load() -> dict:
    if not os.path.exists(BIRTHDAY_JSON):
        return {}
    try:
        with open(BIRTHDAY_JSON, "r") as handle:
            content = handle.read().strip()
        data = json.loads(content) if content else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def birthday_save_all(data: dict) -> None:
    os.makedirs(os.path.dirname(BIRTHDAY_JSON) or ".", exist_ok=True)
    with open(BIRTHDAY_JSON, "w") as handle:
        json.dump(data, handle, indent=2)


def birthday_list(guild_id: int) -> list[dict]:
    """
    Everyone's birthday on this guild.

    The file is keyed by user id at the top level in some versions and by
    guild in others, so both shapes are read.
    """
    data = birthday_load()
    out = []

    guild_block = data.get(str(guild_id))
    if isinstance(guild_block, dict):
        for user_id, value in guild_block.items():
            if str(user_id).isdigit():
                out.append({"user_id": int(user_id), "date": str(value)})
        return out

    for user_id, value in data.items():
        if not str(user_id).isdigit():
            continue
        if isinstance(value, dict):
            date = value.get("date") or value.get("birthday")
            if value.get("guild_id") and int(value["guild_id"]) != guild_id:
                continue
        else:
            date = value
        if date:
            out.append({"user_id": int(user_id), "date": str(date)})
    return out


def birthday_set(guild_id: int, user_id: int, date: str) -> None:
    data = birthday_load()
    block = data.get(str(guild_id))
    if not isinstance(block, dict):
        block = {}
    block[str(user_id)] = date
    data[str(guild_id)] = block
    birthday_save_all(data)


def birthday_remove(guild_id: int, user_id: int) -> bool:
    data = birthday_load()
    block = data.get(str(guild_id))
    if isinstance(block, dict) and str(user_id) in block:
        del block[str(user_id)]
        data[str(guild_id)] = block
        birthday_save_all(data)
        return True

    if str(user_id) in data:
        del data[str(user_id)]
        birthday_save_all(data)
        return True
    return False


def birthday_valid(date: str) -> bool:
    """Accepts DD.MM and DD.MM.YYYY."""
    import re

    text = str(date or "").strip()
    if not re.fullmatch(r"\d{1,2}\.\d{1,2}(\.\d{4})?", text):
        return False
    parts = text.split(".")
    day, month = int(parts[0]), int(parts[1])
    if not 1 <= month <= 12:
        return False
    # 29 February has to stay valid even in a non-leap year.
    limits = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
              7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    return 1 <= day <= limits[month]


def birthday_upcoming(entries: list[dict], days: int = 30) -> list[dict]:
    """Sort by how soon the birthday is, wrapping around the year."""
    import datetime as _dt

    today = _dt.date.today()
    out = []
    for entry in entries:
        parts = str(entry["date"]).split(".")
        if len(parts) < 2:
            continue
        try:
            day, month = int(parts[0]), int(parts[1])
        except ValueError:
            continue

        try:
            this_year = _dt.date(today.year, month, day)
        except ValueError:
            # 29 February in a non-leap year: treat as the 28th.
            try:
                this_year = _dt.date(today.year, month, 28)
            except ValueError:
                continue

        delta = (this_year - today).days
        if delta < 0:
            try:
                delta = (_dt.date(today.year + 1, month, day) - today).days
            except ValueError:
                delta = (_dt.date(today.year + 1, month, 28) - today).days

        out.append({**entry, "in_days": delta})

    out.sort(key=lambda e: e["in_days"])
    return [e for e in out if e["in_days"] <= days]
