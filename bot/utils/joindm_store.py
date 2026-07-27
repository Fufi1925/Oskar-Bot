# ╔══════════════════════════════════════════════════════════════════╗
# ║   Join DM: the message new members get privately                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage for the private message sent to somebody who joins.

Two real problems with the previous version:

  * `joindm enable` called `bot.add_listener(...)` at runtime. That does
    not survive a restart — after every deploy the feature was silently
    off while the dashboard still showed the configured text. Calling
    `enable` twice registered the listener twice, so new members got the
    DM two or three times.
  * The message was a bare string in `jsondb/joindm_messages.json` with
    no placeholders, no title, no colour and no way to test it against
    a real member.

The listener is now always registered and checks a stored `enabled`
flag, which is the part that actually persists.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import aiosqlite

DB_PATH = "db/joindm.db"
LEGACY_JSON = "jsondb/joindm_messages.json"

DEFAULTS: dict[str, Any] = {
    "enabled": 0,
    "title": "Willkommen!",
    "message": "Hey {user_name}, schön dass du auf **{server}** bist!",
    "colour": 0x5865F2,
    "image_url": "",
    "footer": "",
    # A button leading somewhere useful — rules, a support server, a site.
    "button_label": "",
    "button_url": "",
    # Wait this many seconds before sending. Sending the instant somebody
    # joins looks robotic and lands above the welcome message.
    "delay_seconds": 0,
    # Skip members whose account is younger than this. Raid accounts get
    # a DM they never read, and mass-DMing is how a bot gets flagged.
    "min_account_days": 0,
}

BOOLEAN_KEYS = {"enabled"}

PLACEHOLDERS = {
    "user": "Erwähnt das Mitglied (@Name)",
    "user_name": "Der Benutzername",
    "user_id": "Die ID des Mitglieds",
    "server": "Name des Servers",
    "membercount": "Wie viele Mitglieder der Server hat",
    "owner": "Name des Server-Inhabers",
}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS joindm (guild_id INTEGER PRIMARY KEY)"
    )

    async with db.execute("PRAGMA table_info([joindm])") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}

    for name, value in DEFAULTS.items():
        if name in existing:
            continue
        kind = "TEXT" if isinstance(value, str) else "INTEGER"
        try:
            await db.execute(f"ALTER TABLE joindm ADD COLUMN {name} {kind}")
        except Exception:
            pass

    # How often it actually went out, so the dashboard can show whether
    # the feature does anything at all.
    for name in ("sent_total", "failed_total", "last_sent"):
        if name not in existing:
            try:
                await db.execute(f"ALTER TABLE joindm ADD COLUMN {name} INTEGER DEFAULT 0")
            except Exception:
                pass

    await db.commit()
    await migrate_json(db)


async def migrate_json(db: aiosqlite.Connection) -> None:
    """
    Carry the old JSON file over, once.

    The messages in it were configured by hand and losing them on the
    switch would be worse than the bug being fixed.
    """
    if not os.path.exists(LEGACY_JSON):
        return

    async with db.execute("SELECT COUNT(*) FROM joindm") as cursor:
        if (await cursor.fetchone())[0]:
            return  # already migrated

    try:
        with open(LEGACY_JSON, "r") as handle:
            content = handle.read().strip()
        messages = json.loads(content) if content else {}
        if not isinstance(messages, dict):
            return
    except Exception:
        return

    for guild_id, message in messages.items():
        if not str(guild_id).isdigit() or not message:
            continue
        # The old feature had no on/off that survived a restart, so
        # anything configured was meant to be active.
        await save(db, int(guild_id), {"message": str(message), "enabled": 1})


def normalise(settings: dict) -> dict:
    out = dict(DEFAULTS)
    out.update({k: v for k, v in settings.items() if k in DEFAULTS})

    for key in BOOLEAN_KEYS:
        out[key] = 1 if out.get(key) else 0

    out["title"] = str(out.get("title") or "")[:200]
    out["message"] = str(out.get("message") or "")[:2000]
    out["footer"] = str(out.get("footer") or "")[:300]
    out["button_label"] = str(out.get("button_label") or "")[:80]

    for key in ("image_url", "button_url"):
        value = str(out.get(key) or "").strip()
        out[key] = value[:400] if value.startswith(("http://", "https://")) else ""

    colour = out.get("colour")
    if isinstance(colour, str):
        try:
            colour = int(colour.lstrip("#"), 16)
        except ValueError:
            colour = DEFAULTS["colour"]
    out["colour"] = max(0, min(int(colour or 0), 0xFFFFFF))

    out["delay_seconds"] = max(0, min(int(out.get("delay_seconds") or 0), 3600))
    out["min_account_days"] = max(0, min(int(out.get("min_account_days") or 0), 3650))

    return out


async def get(db: aiosqlite.Connection, guild_id: int) -> dict:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM joindm WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return {**normalise({}), "sent_total": 0, "failed_total": 0, "last_sent": 0}

    data = {key: row[key] for key in row.keys()}
    out = normalise(data)
    out["sent_total"] = int(data.get("sent_total") or 0)
    out["failed_total"] = int(data.get("failed_total") or 0)
    out["last_sent"] = int(data.get("last_sent") or 0)
    return out


async def save(db: aiosqlite.Connection, guild_id: int, updates: dict) -> dict:
    """Write only the keys given; the rest keep their stored value."""
    current = await get(db, guild_id)
    merged = normalise({**current, **{
        k: v for k, v in updates.items() if k in DEFAULTS
    }})

    columns = list(DEFAULTS)
    await db.execute(
        f"INSERT INTO joindm (guild_id, {', '.join(columns)})"
        f" VALUES ({', '.join('?' * (len(columns) + 1))})"
        " ON CONFLICT(guild_id) DO UPDATE SET "
        + ", ".join(f"{name} = excluded.{name}" for name in columns),
        [guild_id] + [merged[name] for name in columns],
    )
    await db.commit()
    return merged


async def all_enabled(db: aiosqlite.Connection) -> set[int]:
    """Guilds with the feature on — used to prime the cog's cache."""
    async with db.execute(
        "SELECT guild_id FROM joindm WHERE COALESCE(enabled, 0) = 1"
    ) as cursor:
        return {int(row[0]) for row in await cursor.fetchall()}


async def bump(db: aiosqlite.Connection, guild_id: int, *, ok: bool) -> None:
    column = "sent_total" if ok else "failed_total"
    await db.execute(
        f"UPDATE joindm SET {column} = COALESCE({column}, 0) + 1,"
        " last_sent = ? WHERE guild_id = ?",
        (int(time.time()), guild_id),
    )
    await db.commit()


def fill(text: str, member, guild) -> str:
    """Replace the placeholders. Unknown ones are left as they are."""
    values = {
        "user": getattr(member, "mention", ""),
        "user_name": getattr(member, "name", ""),
        "user_id": getattr(member, "id", ""),
        "server": getattr(guild, "name", ""),
        "membercount": getattr(guild, "member_count", 0) or 0,
        "owner": str(getattr(guild, "owner", "") or ""),
    }
    out = str(text or "")
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def build_view(settings: dict, member, guild):
    """The DM as a Components V2 card."""
    from utils.panels import Panel

    buttons = []
    url = settings.get("button_url")
    if url and settings.get("button_label"):
        import discord

        buttons.append(discord.ui.Button(
            label=settings["button_label"][:80],
            url=url,
            style=discord.ButtonStyle.link,
        ))

    sections = [fill(settings.get("message"), member, guild)]
    footer = fill(settings.get("footer"), member, guild)
    if footer:
        sections.append(footer)

    return Panel(
        fill(settings.get("title"), member, guild) or "Willkommen",
        *sections,
        accent=settings.get("colour") or DEFAULTS["colour"],
        image_url=settings.get("image_url") or None,
        buttons=buttons,
    )


def may_send(settings: dict, member) -> str | None:
    """Why this member should not get a DM. None means send it."""
    import datetime as _dt

    if not settings.get("enabled"):
        return "Join-DM ist für diesen Server aus."
    if not str(settings.get("message") or "").strip():
        return "Es ist keine Nachricht eingetragen."
    if getattr(member, "bot", False):
        return "Bots bekommen keine DM."

    minimum = int(settings.get("min_account_days") or 0)
    created = getattr(member, "created_at", None)
    if minimum and created is not None:
        age = (_dt.datetime.now(_dt.timezone.utc) - created).days
        if age < minimum:
            return f"Account ist erst {age} Tage alt (nötig: {minimum})."

    return None
