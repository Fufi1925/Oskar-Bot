# ╔══════════════════════════════════════════════════════════════════╗
# ║   Multiple ticket panels per guild                               ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Ticket panels, plural.

The original schema had `guild_configs.guild_id` as the primary key, so a
server could only ever have one ticket panel: one channel, one embed, one
set of categories. Wanting a support panel in #help and a separate
application panel in #apply was structurally impossible.

This adds a `ticket_panels` table and gives every category a `panel_id`.
Settings that really are server-wide (transcript channel, archive
category) stay in `guild_configs`, which the cog still reads.

Migration is automatic and idempotent: an existing guild_configs row
becomes panel #1 and its categories are attached to it, so nobody loses a
configuration.
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

DB_PATH = "db/ticket.db"

PANEL_COLUMNS = (
    "panel_id", "guild_id", "name", "channel_id", "message_id", "panel_type",
    "embed_title", "embed_description", "embed_color",
    "embed_image_url", "embed_thumbnail_url", "staff_roles",
)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the panel tables and migrate a single-panel setup once."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_panels (
            panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT 'Support',
            channel_id INTEGER,
            message_id INTEGER,
            panel_type TEXT DEFAULT 'button',
            embed_title TEXT,
            embed_description TEXT,
            embed_color INTEGER,
            embed_image_url TEXT,
            embed_thumbnail_url TEXT,
            staff_roles TEXT DEFAULT ''
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_panels_guild ON ticket_panels(guild_id)"
    )

    # Categories belong to a panel now.
    async with db.execute("PRAGMA table_info([ticket_categories])") as cursor:
        cat_columns = {row[1] for row in await cursor.fetchall()}
    if cat_columns and "panel_id" not in cat_columns:
        await db.execute(
            "ALTER TABLE ticket_categories ADD COLUMN panel_id INTEGER"
        )

    # guild_configs.staff_roles was written by the API but never existed in
    # the schema, so saving the global staff roles raised "no such column"
    # and took the rest of that request down with it.
    async with db.execute("PRAGMA table_info([guild_configs])") as cursor:
        cfg_columns = {row[1] for row in await cursor.fetchall()}
    if cfg_columns and "staff_roles" not in cfg_columns:
        await db.execute("ALTER TABLE guild_configs ADD COLUMN staff_roles TEXT")

    await db.commit()


async def migrate_guild(db: aiosqlite.Connection, guild_id: int) -> int | None:
    """
    Turn a legacy single-panel configuration into panel #1.

    Returns the new panel id, or None when there was nothing to migrate.
    Safe to call repeatedly.
    """
    async with db.execute(
        "SELECT COUNT(*) FROM ticket_panels WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row and row[0]:
        return None  # already migrated

    async with db.execute(
        "SELECT panel_channel_id, panel_message_id, panel_type, embed_title,"
        " embed_description, embed_color, embed_image_url, embed_thumbnail_url"
        " FROM guild_configs WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        legacy = await cursor.fetchone()

    if legacy is None:
        return None

    cursor = await db.execute(
        "INSERT INTO ticket_panels (guild_id, name, channel_id, message_id,"
        " panel_type, embed_title, embed_description, embed_color,"
        " embed_image_url, embed_thumbnail_url, staff_roles)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')",
        (guild_id, "Support", *legacy),
    )
    panel_id = cursor.lastrowid

    # Existing categories belonged to that one panel.
    await db.execute(
        "UPDATE ticket_categories SET panel_id = ?"
        " WHERE guild_id = ? AND (panel_id IS NULL OR panel_id = 0)",
        (panel_id, guild_id),
    )
    await db.commit()
    return panel_id


def _split_roles(value: Any) -> list[str]:
    if not value:
        return []
    return [p for p in str(value).split(",") if p.strip().isdigit()]


async def list_panels(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    """Every panel of a guild, categories included."""
    await ensure_schema(db)
    await migrate_guild(db, guild_id)

    async with db.execute(
        "SELECT panel_id, name, channel_id, message_id, panel_type,"
        " embed_title, embed_description, embed_color, embed_image_url,"
        " embed_thumbnail_url, staff_roles"
        " FROM ticket_panels WHERE guild_id = ? ORDER BY panel_id",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    panels = []
    for row in rows:
        panel_id = row[0]
        async with db.execute(
            "SELECT category_id, name, emoji, notified_roles, button_style,"
            " discord_category_id FROM ticket_categories"
            " WHERE guild_id = ? AND panel_id = ? ORDER BY category_id",
            (guild_id, panel_id),
        ) as cat_cursor:
            cats = await cat_cursor.fetchall()

        panels.append({
            "panel_id": panel_id,
            "name": row[1] or "Support",
            "channel_id": str(row[2]) if row[2] else None,
            "message_id": str(row[3]) if row[3] else None,
            "panel_type": row[4] or "button",
            "embed_title": row[5] or "",
            "embed_description": row[6] or "",
            "embed_color": row[7],
            "embed_image_url": row[8] or "",
            "embed_thumbnail_url": row[9] or "",
            "staff_roles": _split_roles(row[10]),
            "posted": bool(row[3]),
            "categories": [
                {
                    "category_id": c[0],
                    "name": c[1],
                    "emoji": c[2] or "",
                    "staff_roles": _split_roles(c[3]),
                    "button_style": c[4] or 2,
                    "discord_category_id": str(c[5]) if c[5] else None,
                }
                for c in cats
            ],
        })
    return panels


async def create_panel(
    db: aiosqlite.Connection, guild_id: int, name: str = "Support"
) -> int:
    await ensure_schema(db)
    cursor = await db.execute(
        "INSERT INTO ticket_panels (guild_id, name, embed_title,"
        " embed_description, embed_color)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            guild_id,
            name[:100] or "Support",
            name[:100] or "Support",
            "Klicke unten, um ein Ticket zu öffnen.",
            0x5865F2,
        ),
    )
    await db.commit()
    return cursor.lastrowid


# Columns a client may write, mapped to their database name.
_WRITABLE = {
    "name": "name",
    "channel_id": "channel_id",
    "panel_type": "panel_type",
    "embed_title": "embed_title",
    "embed_description": "embed_description",
    "embed_color": "embed_color",
    "embed_image_url": "embed_image_url",
    "embed_thumbnail_url": "embed_thumbnail_url",
}


async def update_panel(
    db: aiosqlite.Connection, guild_id: int, panel_id: int, data: dict
) -> bool:
    """
    Patch one panel. Only the keys that were sent are touched, so saving
    the appearance cannot wipe the channel.
    """
    await ensure_schema(db)

    assignments, values = [], []
    for key, column in _WRITABLE.items():
        if key in data and data[key] is not None:
            assignments.append(f"{column} = ?")
            values.append(data[key])

    if "staff_roles" in data and data["staff_roles"] is not None:
        assignments.append("staff_roles = ?")
        values.append(",".join(str(r) for r in data["staff_roles"]))

    if not assignments:
        return False

    values.extend([panel_id, guild_id])
    await db.execute(
        f"UPDATE ticket_panels SET {', '.join(assignments)}"
        " WHERE panel_id = ? AND guild_id = ?",
        values,
    )
    await db.commit()
    return True


async def delete_panel(
    db: aiosqlite.Connection, guild_id: int, panel_id: int
) -> bool:
    await ensure_schema(db)
    await db.execute(
        "DELETE FROM ticket_categories WHERE guild_id = ? AND panel_id = ?",
        (guild_id, panel_id),
    )
    cursor = await db.execute(
        "DELETE FROM ticket_panels WHERE panel_id = ? AND guild_id = ?",
        (panel_id, guild_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def set_message_id(
    db: aiosqlite.Connection, guild_id: int, panel_id: int, message_id: int | None
) -> None:
    await db.execute(
        "UPDATE ticket_panels SET message_id = ? WHERE panel_id = ? AND guild_id = ?",
        (message_id, panel_id, guild_id),
    )
    await db.commit()


# ---------------------------------------------------------------- categories


async def upsert_category(
    db: aiosqlite.Connection, guild_id: int, panel_id: int, data: dict
) -> int:
    await ensure_schema(db)

    name = str(data.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("A category needs a name.")

    emoji = str(data.get("emoji", "") or "")[:32]
    roles = ",".join(str(r) for r in (data.get("staff_roles") or []))
    try:
        style = max(1, min(int(data.get("button_style", 2)), 4))
    except (TypeError, ValueError):
        style = 2
    target = data.get("discord_category_id") or None

    category_id = data.get("category_id")
    if category_id:
        await db.execute(
            "UPDATE ticket_categories SET name = ?, emoji = ?, notified_roles = ?,"
            " button_style = ?, discord_category_id = ?, panel_id = ?"
            " WHERE category_id = ? AND guild_id = ?",
            (name, emoji, roles, style, target, panel_id, category_id, guild_id),
        )
        await db.commit()
        return int(category_id)

    cursor = await db.execute(
        "INSERT INTO ticket_categories (guild_id, panel_id, name, emoji,"
        " notified_roles, button_style, discord_category_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, panel_id, name, emoji, roles, style, target),
    )
    await db.commit()
    return cursor.lastrowid


async def delete_category(
    db: aiosqlite.Connection, guild_id: int, category_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM ticket_categories WHERE category_id = ? AND guild_id = ?",
        (category_id, guild_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0
