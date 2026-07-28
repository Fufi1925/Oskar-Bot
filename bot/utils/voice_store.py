# ╔══════════════════════════════════════════════════════════════════╗
# ║   Join to Create, voice roles and custom role commands           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Storage for the three voice/role features that share this tab group.

Real bugs this module exists to fix:

  * **Voice role had a dead switch.** The API wrote an ``enabled``
    column and the dashboard showed a toggle for it, but the cog only
    ever ran ``SELECT role_id FROM vcroles`` -- it never looked at
    ``enabled``. Turning the feature off in the dashboard changed a
    number in the database and nothing else; the bot kept handing the
    role out.

  * **Voice role was capped at one role** by the cog ("VC role is
    already set in this guild"), while nothing in the schema required
    that. The table used ``guild_id INTEGER PRIMARY KEY``, so a second
    role was impossible to store even though the feature reads as a
    list.

  * **The setup overview never saw Join to Create.** It counted rows in
    ``db/block.db`` table ``j2c`` -- the blacklist database, which has
    no such table -- so the module was reported as "not configured" no
    matter how it was set up. The real data lives in ``j2c_data.db``.

Custom roles keep only the free-form ``custom_roles`` table. The five
fixed slots (staff/girl/vip/guest/frnd) are gone: they were English-only,
un-renameable, and duplicated what a named role does better. Existing
rows are migrated into named entries so nothing is lost.
"""

from __future__ import annotations

import os
import re

from typing import Any

import aiosqlite

VOICEROLE_DB = "db/invc.db"
CUSTOMROLE_DB = "db/customrole.db"
# The cog opens this from the working directory, so the API has to use
# the exact same relative path or the two see different files.
J2C_DB = "j2c_data.db"

# Discord hard limits, checked before we ask the API to do something it
# will refuse anyway.
MAX_SELECT_OPTIONS = 25
MAX_VOICE_LIMIT = 99
MAX_CHANNEL_NAME = 100


# ══════════════════════════════════════════════════════════════════════
#  Voice roles
# ══════════════════════════════════════════════════════════════════════

VOICEROLE_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "roles": [],
    # Empty means every voice channel. A non-empty list restricts the
    # feature to those channels.
    "channels": [],
    # The AFK channel is "in voice" as far as Discord is concerned, but
    # nobody there is actually talking.
    "ignore_afk": True,
    # Stage channels are broadcasts, not hangouts.
    "include_stage": True,
}


async def voicerole_ensure(db: aiosqlite.Connection) -> None:
    """
    Create the tables and migrate the old single-role layout.

    The original table was ``vcroles(guild_id PRIMARY KEY, role_id)`` --
    one role per guild, enforced by the schema. Multiple roles need a
    row per role, so the data moves to ``vcrole_roles`` and ``vcroles``
    is kept for the per-guild settings.
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vcroles (
            guild_id INTEGER PRIMARY KEY,
            role_id INTEGER NOT NULL,
            enabled INTEGER DEFAULT 0
        )
        """
    )
    for column, ddl in (
        ("enabled", "ALTER TABLE vcroles ADD COLUMN enabled INTEGER DEFAULT 0"),
        ("ignore_afk", "ALTER TABLE vcroles ADD COLUMN ignore_afk INTEGER DEFAULT 1"),
        ("include_stage",
         "ALTER TABLE vcroles ADD COLUMN include_stage INTEGER DEFAULT 1"),
    ):
        try:
            await db.execute(ddl)
        except (aiosqlite.OperationalError, Exception):
            pass

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vcrole_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vcrole_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        )
        """
    )
    await db.commit()

    # Move any legacy single role across, once.
    async with db.execute(
        "SELECT guild_id, role_id FROM vcroles WHERE role_id IS NOT NULL AND role_id != 0"
    ) as cursor:
        legacy = await cursor.fetchall()

    for row in legacy:
        guild_id, role_id = int(row[0]), int(row[1])
        await db.execute(
            "INSERT OR IGNORE INTO vcrole_roles (guild_id, role_id) VALUES (?, ?)",
            (guild_id, role_id),
        )
    if legacy:
        await db.commit()


async def voicerole_get(db: aiosqlite.Connection, guild_id: int) -> dict:
    await voicerole_ensure(db)

    async with db.execute(
        "SELECT enabled, ignore_afk, include_stage FROM vcroles WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    async with db.execute(
        "SELECT role_id FROM vcrole_roles WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        roles = [int(r[0]) for r in await cursor.fetchall()]

    async with db.execute(
        "SELECT channel_id FROM vcrole_channels WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        channels = [int(r[0]) for r in await cursor.fetchall()]

    def flag(key, default):
        if row is None:
            return default
        try:
            return bool(row[key])
        except (KeyError, IndexError, TypeError):
            return default

    return {
        **VOICEROLE_DEFAULTS,
        "enabled": flag("enabled", False),
        "ignore_afk": flag("ignore_afk", True),
        "include_stage": flag("include_stage", True),
        "roles": roles,
        "channels": channels,
    }


async def voicerole_save(
    db: aiosqlite.Connection, guild_id: int, updates: dict
) -> dict:
    """Partial update: only the keys that were sent are written."""
    await voicerole_ensure(db)
    current = await voicerole_get(db, guild_id)

    enabled = bool(updates.get("enabled", current["enabled"]))
    ignore_afk = bool(updates.get("ignore_afk", current["ignore_afk"]))
    include_stage = bool(updates.get("include_stage", current["include_stage"]))

    # vcroles.role_id is NOT NULL, so it keeps a copy of the first role
    # purely to satisfy the old schema.
    roles = current["roles"]
    if "roles" in updates:
        roles = _clean_ids(updates.get("roles"))
        await db.execute("DELETE FROM vcrole_roles WHERE guild_id = ?", (guild_id,))
        for role_id in roles:
            await db.execute(
                "INSERT OR IGNORE INTO vcrole_roles (guild_id, role_id) VALUES (?, ?)",
                (guild_id, role_id),
            )

    if "channels" in updates:
        channels = _clean_ids(updates.get("channels"))
        await db.execute("DELETE FROM vcrole_channels WHERE guild_id = ?", (guild_id,))
        for channel_id in channels:
            await db.execute(
                "INSERT OR IGNORE INTO vcrole_channels (guild_id, channel_id) "
                "VALUES (?, ?)",
                (guild_id, channel_id),
            )

    await db.execute(
        "INSERT OR REPLACE INTO vcroles "
        "(guild_id, role_id, enabled, ignore_afk, include_stage) "
        "VALUES (?, ?, ?, ?, ?)",
        (guild_id, roles[0] if roles else 0, int(enabled),
         int(ignore_afk), int(include_stage)),
    )
    await db.commit()
    return await voicerole_get(db, guild_id)


def _clean_ids(values) -> list[int]:
    """Snowflakes arrive as strings from JSON; keep them exact."""
    out: list[int] = []
    for value in values or []:
        text = str(value).strip()
        if text.isdigit() and int(text) not in out:
            out.append(int(text))
    return out


def voicerole_applies(settings: dict, channel_id, is_afk: bool,
                      is_stage: bool) -> bool:
    """
    Whether the role should be handed out for this channel.

    Pure so the rules can be tested without a Discord connection.
    """
    if not settings.get("enabled"):
        return False
    if not settings.get("roles"):
        return False
    if is_afk and settings.get("ignore_afk"):
        return False
    if is_stage and not settings.get("include_stage"):
        return False

    allowed = settings.get("channels") or []
    if not allowed:
        return True
    try:
        return int(channel_id) in [int(c) for c in allowed]
    except (TypeError, ValueError):
        return False


# ══════════════════════════════════════════════════════════════════════
#  Custom role commands
# ══════════════════════════════════════════════════════════════════════

# A command name has to survive being typed after a prefix, so no
# spaces and nothing that looks like markdown or a mention.
NAME_PATTERN = re.compile(r"^[a-z0-9_\-]{1,24}$")

LEGACY_SLOTS = ("staff", "girl", "vip", "guest", "frnd")


def customrole_check_name(name: str) -> str | None:
    """Return an error message, or None when the name is usable."""
    name = (name or "").strip().lower()
    if not name:
        return "Gib dem Befehl einen Namen."
    if len(name) > 24:
        return "Der Name darf höchstens 24 Zeichen haben."
    if not NAME_PATTERN.match(name):
        return (
            "Erlaubt sind nur Kleinbuchstaben, Zahlen, - und _ — "
            "keine Leerzeichen."
        )
    return None


async def customrole_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            guild_id INTEGER PRIMARY KEY,
            staff INTEGER,
            girl INTEGER,
            vip INTEGER,
            guest INTEGER,
            frnd INTEGER,
            reqrole INTEGER
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_roles (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, name)
        )
        """
    )
    await db.commit()


async def customrole_migrate(db: aiosqlite.Connection, guild_id: int) -> list[str]:
    """
    Turn the five fixed slots into ordinary named commands.

    The slots were hard-coded English words with no way to rename them.
    Dropping them without migrating would silently remove five working
    commands from every server that used them.
    """
    await customrole_ensure(db)

    async with db.execute(
        "SELECT staff, girl, vip, guest, frnd FROM roles WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return []

    moved: list[str] = []
    for index, slot in enumerate(LEGACY_SLOTS):
        try:
            role_id = row[index]
        except (IndexError, KeyError):
            role_id = None
        if not role_id:
            continue

        async with db.execute(
            "SELECT 1 FROM custom_roles WHERE guild_id = ? AND name = ?",
            (guild_id, slot),
        ) as cursor:
            if await cursor.fetchone():
                continue

        await db.execute(
            "INSERT INTO custom_roles (guild_id, name, role_id) VALUES (?, ?, ?)",
            (guild_id, slot, int(role_id)),
        )
        moved.append(slot)

    if moved:
        # Blank the slots so the migration cannot run twice and
        # resurrect a command the admin has since deleted.
        await db.execute(
            "UPDATE roles SET staff = NULL, girl = NULL, vip = NULL, "
            "guest = NULL, frnd = NULL WHERE guild_id = ?",
            (guild_id,),
        )
        await db.commit()
    return moved


async def customrole_get(db: aiosqlite.Connection, guild_id: int) -> dict:
    await customrole_ensure(db)
    migrated = await customrole_migrate(db, guild_id)

    async with db.execute(
        "SELECT name, role_id FROM custom_roles WHERE guild_id = ? ORDER BY name",
        (guild_id,),
    ) as cursor:
        entries = [
            {"name": str(r[0]), "role_id": int(r[1])} for r in await cursor.fetchall()
        ]

    async with db.execute(
        "SELECT reqrole FROM roles WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    reqrole = int(row[0]) if row and row[0] else None

    return {"entries": entries, "reqrole": reqrole, "migrated": migrated}


async def customrole_set_reqrole(
    db: aiosqlite.Connection, guild_id: int, role_id
) -> None:
    await customrole_ensure(db)
    value = int(role_id) if str(role_id or "").isdigit() else None
    async with db.execute(
        "SELECT 1 FROM roles WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        exists = await cursor.fetchone()
    if exists:
        await db.execute(
            "UPDATE roles SET reqrole = ? WHERE guild_id = ?", (value, guild_id)
        )
    else:
        await db.execute(
            "INSERT INTO roles (guild_id, reqrole) VALUES (?, ?)", (guild_id, value)
        )
    await db.commit()


async def customrole_add(
    db: aiosqlite.Connection, guild_id: int, name: str, role_id: int
) -> None:
    await customrole_ensure(db)
    await db.execute(
        "INSERT OR REPLACE INTO custom_roles (guild_id, name, role_id) "
        "VALUES (?, ?, ?)",
        (guild_id, name.strip().lower(), int(role_id)),
    )
    await db.commit()


async def customrole_remove(
    db: aiosqlite.Connection, guild_id: int, name: str
) -> bool:
    await customrole_ensure(db)
    cursor = await db.execute(
        "DELETE FROM custom_roles WHERE guild_id = ? AND name = ?",
        (guild_id, name.strip().lower()),
    )
    await db.commit()
    return cursor.rowcount > 0


async def customrole_lookup(
    db: aiosqlite.Connection, guild_id: int, name: str
) -> int | None:
    await customrole_ensure(db)
    async with db.execute(
        "SELECT role_id FROM custom_roles WHERE guild_id = ? AND name = ?",
        (guild_id, (name or "").strip().lower()),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


# ══════════════════════════════════════════════════════════════════════
#  Join to Create
# ══════════════════════════════════════════════════════════════════════

J2C_DEFAULTS: dict[str, Any] = {
    "join_channel_id": None,
    "control_channel_id": None,
    "control_message_id": None,
    "category_id": None,
    # "{user}'s VC" is what the cog hard-coded. Now editable, and the
    # placeholders are resolved in one place.
    "name_template": "{user}'s VC",
    "default_limit": 2,
    # Lock the new channel to its owner straight away.
    "default_locked": False,
}

J2C_PLACEHOLDERS = {
    "{user}": "Name des Erstellers",
    "{user.name}": "Name des Erstellers",
    "{user.display}": "Serverspezifischer Anzeigename",
    "{count}": "Wie viele private Kanäle gerade offen sind",
}


async def j2c_ensure(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_setup (
            guild_id INTEGER PRIMARY KEY,
            join_channel_id INTEGER,
            control_channel_id INTEGER,
            control_message_id INTEGER,
            category_id INTEGER
        )
        """
    )
    for ddl in (
        "ALTER TABLE guild_setup ADD COLUMN category_id INTEGER",
        "ALTER TABLE guild_setup ADD COLUMN name_template TEXT",
        "ALTER TABLE guild_setup ADD COLUMN default_limit INTEGER DEFAULT 2",
        "ALTER TABLE guild_setup ADD COLUMN default_locked INTEGER DEFAULT 0",
    ):
        try:
            await db.execute(ddl)
        except (aiosqlite.OperationalError, Exception):
            pass
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS private_channels (
            vc_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            owner_id INTEGER,
            member_limit INTEGER DEFAULT 2,
            region TEXT DEFAULT '',
            is_locked BOOLEAN DEFAULT FALSE,
            has_waiting_room BOOLEAN DEFAULT FALSE,
            has_thread BOOLEAN DEFAULT FALSE
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS blocked_users (
            vc_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY (vc_id, user_id)
        )
        """
    )
    await db.commit()


async def j2c_get(db: aiosqlite.Connection, guild_id: int) -> dict:
    await j2c_ensure(db)
    async with db.execute(
        "SELECT join_channel_id, control_channel_id, control_message_id, "
        "category_id, name_template, default_limit, default_locked "
        "FROM guild_setup WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return dict(J2C_DEFAULTS)

    def get(index, key):
        try:
            value = row[index]
        except (IndexError, KeyError):
            return J2C_DEFAULTS[key]
        return value if value is not None else J2C_DEFAULTS[key]

    limit = get(5, "default_limit")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 2

    return {
        "join_channel_id": get(0, "join_channel_id"),
        "control_channel_id": get(1, "control_channel_id"),
        "control_message_id": get(2, "control_message_id"),
        "category_id": get(3, "category_id"),
        "name_template": str(get(4, "name_template") or J2C_DEFAULTS["name_template"]),
        "default_limit": max(0, min(MAX_VOICE_LIMIT, limit)),
        "default_locked": bool(get(6, "default_locked")),
    }


async def j2c_save(db: aiosqlite.Connection, guild_id: int, updates: dict) -> dict:
    await j2c_ensure(db)
    current = await j2c_get(db, guild_id)
    merged = {**current, **{k: v for k, v in (updates or {}).items()
                            if k in J2C_DEFAULTS}}

    def to_id(value):
        text = str(value or "").strip()
        return int(text) if text.isdigit() else None

    try:
        limit = int(merged.get("default_limit") or 0)
    except (TypeError, ValueError):
        limit = 2

    await db.execute(
        "INSERT OR REPLACE INTO guild_setup "
        "(guild_id, join_channel_id, control_channel_id, control_message_id, "
        " category_id, name_template, default_limit, default_locked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            guild_id,
            to_id(merged.get("join_channel_id")),
            to_id(merged.get("control_channel_id")),
            to_id(merged.get("control_message_id")),
            to_id(merged.get("category_id")),
            str(merged.get("name_template") or J2C_DEFAULTS["name_template"])[:MAX_CHANNEL_NAME],
            max(0, min(MAX_VOICE_LIMIT, limit)),
            int(bool(merged.get("default_locked"))),
        ),
    )
    await db.commit()
    return await j2c_get(db, guild_id)


async def j2c_clear(db: aiosqlite.Connection, guild_id: int) -> None:
    await j2c_ensure(db)
    await db.execute("DELETE FROM guild_setup WHERE guild_id = ?", (guild_id,))
    await db.commit()


def j2c_channel_name(template: str, *, user_name: str, display_name: str = "",
                     count: int = 0) -> str:
    """
    Build the channel name.

    Discord truncates past 100 characters and rejects an empty name, so
    both ends are handled here rather than at three call sites.
    """
    text = str(template or J2C_DEFAULTS["name_template"])
    for token, value in (
        ("{user.display}", display_name or user_name),
        ("{user.name}", user_name),
        ("{user}", user_name),
        ("{count}", str(count)),
    ):
        text = text.replace(token, str(value))

    text = text.strip()[:MAX_CHANNEL_NAME]
    return text or f"{user_name}'s VC"[:MAX_CHANNEL_NAME]


def j2c_is_configured(settings: dict) -> bool:
    """Both channels are needed; one alone does nothing."""
    return bool(settings.get("join_channel_id") and settings.get("control_channel_id"))


def select_options_note(total: int) -> str:
    """
    Discord allows 25 options in a select menu; more raises 400.

    The dropdowns used to be built from every member of the server, so
    on anything above 25 people the interaction simply failed.
    """
    if total <= MAX_SELECT_OPTIONS:
        return ""
    return (
        f"Es werden die ersten {MAX_SELECT_OPTIONS} von {total} angezeigt — "
        "Discord erlaubt nicht mehr."
    )


def ensure_db_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
