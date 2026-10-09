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
from utils import ticket_settings
from utils.component_emojis import label_emoji

DB_PATH = "db/ticket.db"
DEFAULT_SELECT_PLACEHOLDER = "Wähle eine Kategorie…"
DEFAULT_TICKET_WELCOME_TITLE = "Ticket #{ticket_number}"
DEFAULT_TICKET_WELCOME_MESSAGE = (
    "Welcome to your ticket, {user}.\n"
    "Our support team will reply as soon as possible.\n\n"
    "**Describe your request in detail** so we can help you."
)
DEFAULT_TICKET_CREATED_MESSAGE = "Your ticket is open: {channel}"
MAX_SELECT_PLACEHOLDER = 150
MAX_TICKET_QUESTIONS = 5

#: Woerter, die der Bot in Begruessung und Bestaetigung ersetzt.
#:
#: Eine Liste, zwei Nutzer. Der Cog ersetzt beim Schreiben ins Ticket,
#: die Vorschau im Dashboard zeigt dasselbe Ergebnis. Zwei getrennte
#: Marker-Listen sind die klassische Stelle, an der die Vorschau etwas
#: verspricht, das der Bot nie senden wuerde — und der Unterschied
#: faellt erst auf, wenn jemand beide Texte vergleicht.
WILLKOMMEN_NAMEN = ("ticket_number", "user", "category", "server", "channel")
WILLKOMMEN_WOERTER = tuple("{" + name + "}" for name in WILLKOMMEN_NAMEN)

#: Beispielswerte fuer die Vorschau. Bewusst erkennbar erfunden:
#: "#ticket-0001-support" sieht nach Beispiel aus und nach nichts, was
#: man einem Besucher zeigen wollte.
VORSCHAU_BEISPIELE = {
    "ticket_number": "0001",
    "user": "@dein.name",
    "category": "Support",
    "server": "Dein Server",
    "channel": "#ticket-0001-support",
}

PANEL_COLUMNS = (
    "panel_id", "guild_id", "name", "channel_id", "message_id", "panel_type",
    "embed_title", "embed_description", "embed_color",
    "embed_image_url", "embed_thumbnail_url", "staff_roles", "select_placeholder",
    "ticket_welcome_title", "ticket_welcome_message", "ticket_created_message",
    "ticket_questions",
)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the panel tables and migrate a single-panel setup once."""
    await db.execute(ticket_settings.SCHEMA)
    await db.execute(ticket_settings.STATE_SCHEMA)
    await db.execute(ticket_settings.RATING_SCHEMA)
    await db.execute(ticket_settings.FEEDBACK_SCHEMA)
    # guild_configs and ticket_categories are normally created by the ticket
    # cog. The dashboard must not depend on that having happened: if the cog
    # has not run yet, every read here died with "no such table" — the PATCH
    # saving a channel succeeded but the reload right after it failed, so the
    # picker snapped back and it looked like selecting a channel did nothing.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            panel_channel_id INTEGER,
            logging_channel_id INTEGER,
            panel_message_id INTEGER,
            panel_type TEXT,
            embed_title TEXT,
            embed_description TEXT,
            embed_color INTEGER,
            embed_image_url TEXT,
            embed_thumbnail_url TEXT,
            closed_category_id INTEGER,
            staff_roles TEXT,
            always_transcript INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT NOT NULL,
            emoji TEXT,
            notified_roles TEXT,
            button_style INTEGER,
            discord_category_id INTEGER,
            panel_id INTEGER,
            ticket_welcome_title TEXT NOT NULL DEFAULT '',
            ticket_welcome_message TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS open_tickets (
            channel_id INTEGER PRIMARY KEY,
            ticket_number INTEGER,
            guild_id INTEGER,
            creator_id INTEGER,
            category_db_id INTEGER,
            created_at TEXT,
            closed_by_id INTEGER,
            closed_at TEXT,
            is_locked BOOLEAN DEFAULT FALSE,
            is_claimed BOOLEAN DEFAULT FALSE,
            claimed_by_id INTEGER
        )
        """
    )

    async with db.execute('PRAGMA table_info(open_tickets)') as cursor:
        open_columns = {row[1] for row in await cursor.fetchall()}
    if 'category_db_id' not in open_columns:
        await db.execute('ALTER TABLE open_tickets ADD COLUMN category_db_id INTEGER')

    async with db.execute("PRAGMA table_info(guild_configs)") as cursor:
        guild_columns = {str(row[1]) for row in await cursor.fetchall()}
    if "always_transcript" not in guild_columns:
        await db.execute(
            "ALTER TABLE guild_configs ADD COLUMN always_transcript INTEGER NOT NULL DEFAULT 0"
        )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_transcripts (
            ticket_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            guild_name TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            ticket_number INTEGER,
            creator_id INTEGER NOT NULL,
            closed_by_id INTEGER NOT NULL,
            category_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            messages_json TEXT NOT NULL
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticket_transcripts_expiry"
        " ON ticket_transcripts(expires_at)"
    )

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
            staff_roles TEXT DEFAULT '',
            select_placeholder TEXT NOT NULL DEFAULT 'Wähle eine Kategorie…',
            ticket_welcome_title TEXT NOT NULL DEFAULT 'Ticket #{ticket_number}',
            ticket_welcome_message TEXT NOT NULL DEFAULT '',
            ticket_created_message TEXT NOT NULL DEFAULT 'Dein Ticket ist offen: {channel}',
            ticket_questions TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    async with db.execute("PRAGMA table_info(ticket_panels)") as cursor:
        panel_columns = {str(row[1]) for row in await cursor.fetchall()}
    panel_migrations = {
        "select_placeholder": (
            "TEXT NOT NULL DEFAULT 'Wähle eine Kategorie…'"
        ),
        "ticket_welcome_title": (
            "TEXT NOT NULL DEFAULT 'Ticket #{ticket_number}'"
        ),
        "ticket_welcome_message": "TEXT NOT NULL DEFAULT ''",
        "ticket_created_message": (
            "TEXT NOT NULL DEFAULT 'Dein Ticket ist offen: {channel}'"
        ),
        "ticket_questions": "TEXT NOT NULL DEFAULT '[]'",
    }
    for column, definition in panel_migrations.items():
        if column not in panel_columns:
            await db.execute(
                f"ALTER TABLE ticket_panels ADD COLUMN {column} {definition}"
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
    if cat_columns and "ticket_welcome_title" not in cat_columns:
        await db.execute(
            "ALTER TABLE ticket_categories ADD COLUMN ticket_welcome_title TEXT NOT NULL DEFAULT ''"
        )
    if cat_columns and "ticket_welcome_message" not in cat_columns:
        await db.execute(
            "ALTER TABLE ticket_categories ADD COLUMN ticket_welcome_message TEXT NOT NULL DEFAULT ''"
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


def _clean_questions(value: Any) -> list[dict]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = []
    if not isinstance(value, list):
        return []

    cleaned = []
    for item in value[:MAX_TICKET_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:45]
        if not label:
            continue
        question_type = str(item.get("type") or item.get("style") or "short")
        if question_type not in {"short", "paragraph", "image", "file", "select", "radio", "checkbox"}:
            question_type = "short"
        category_ids = []
        for raw_id in item.get("category_ids") or []:
            try:
                category_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if category_id > 0 and category_id not in category_ids:
                category_ids.append(category_id)
        cleaned.append({
            "label": label,
            "placeholder": str(item.get("placeholder") or "").strip()[:100],
            "required": bool(item.get("required", True)),
            "type": question_type,
            "category_ids": category_ids,
            "description": str(item.get('description') or '')[:100],
            "max_length": max(1, min(4000, int(item.get('max_length') or (4000 if question_type == 'paragraph' else 200)))),
            "options": [str(x).strip()[:100] for x in (item.get('options') or []) if str(x).strip()][:10 if question_type == 'checkbox' else 25],
            "public": bool(item.get('public', False)),
        })
    return cleaned


def setze_woerter(text: Any, **werte: str) -> str:
    """Die bekannten Woerter einsetzen, den Rest in Ruhe lassen.

    Kein ``str.format``: ein Text mit geschweiften Klammern — ein
    kopierter JSON-Schnipsel, ein Rest aus einem Guide — wuerde dabei
    eine Ausnahme werfen, und sie bleibt ausgerechnet hängen, wenn
    jemand ein Ticket oeffnet.
    """
    ausgabe = str(text or "")
    for name in WILLKOMMEN_NAMEN:
        if name in werte:
            ausgabe = ausgabe.replace("{" + name + "}", str(werte[name]))
    return ausgabe


def fragen_fuer_kategorie(fragen: Any, category_id: Any) -> list[dict]:
    """Die Fragen, die bei dieser Kategorie wirklich gestellt werden.

    Dieselbe Auswahl wie im Cog — die Vorschau zeigt sonst Fragen, die
    jemand nie zu Gesicht bekommt, oder lässt eine weg, die kommt.
    """
    ohne_kategorie = category_id in (None, "", 0, "0")
    ausgabe = []
    for frage in fragen or []:
        if not isinstance(frage, dict):
            continue
        # Ohne Kategorieangabe sind alle Fragen gemeint. Der Cog ruft
        # immer mit einer auf; die Vorschau im Dashboard hat keine,
        # weil sie das Panel zeigt und nicht einen einzelnen Knopf.
        ids = {str(wert) for wert in (frage.get("category_ids") or [])}
        if not ohne_kategorie and ids and str(category_id) not in ids:
            continue
        ausgabe.append(frage)
        if len(ausgabe) >= MAX_TICKET_QUESTIONS:
            break
    return ausgabe


def vorschau_willkommen(panel: dict, *, category_id: Any = None,
                        entwurf: dict | None = None) -> dict:
    """Was der Bot senden wuerde — mit dem Entwurf, nicht dem Speichern.

    Wer tippt, will sehen, was sein Text tut, bevor er speichert. Der
    Entwurf wird durchgereicht und hier ueber die gespeicherte Zeile
    gelegt; die Laengenbeschneidung ist die aus dem Cog, sonst zeigt die
    Vorschau einen Text, den Discord ablehnen wuerde.
    """
    zusammen = {**(panel or {}), **(entwurf or {})}

    titel = str(zusammen.get("ticket_welcome_title") or DEFAULT_TICKET_WELCOME_TITLE)
    nachricht = str(
        zusammen.get("ticket_welcome_message") or DEFAULT_TICKET_WELCOME_MESSAGE
    )
    bestaetigung = str(
        zusammen.get("ticket_created_message") or DEFAULT_TICKET_CREATED_MESSAGE
    )

    fragen = fragen_fuer_kategorie(
        _clean_questions(zusammen.get("ticket_questions")), category_id
    )

    return {
        "titel": setze_woerter(titel, **VORSCHAU_BEISPIELE)[:256],
        "nachricht": setze_woerter(nachricht, **VORSCHAU_BEISPIELE)[:4096],
        "bestaetigung": setze_woerter(bestaetigung, **VORSCHAU_BEISPIELE)[:1900],
        "fragen": [
            {
                "label": frage["label"],
                "typ": frage["type"],
                "pflicht": bool(frage.get("required")),
                "hinweis": frage.get("placeholder") or "",
            }
            for frage in fragen
        ],
        "woerter": list(WILLKOMMEN_WOERTER),
    }


async def list_panels(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    """Every panel of a guild, categories included."""
    await ensure_schema(db)
    await migrate_guild(db, guild_id)

    async with db.execute(
        "SELECT panel_id, name, channel_id, message_id, panel_type,"
        " embed_title, embed_description, embed_color, embed_image_url,"
        " embed_thumbnail_url, staff_roles, select_placeholder,"
        " ticket_welcome_title, ticket_welcome_message, ticket_created_message,"
        " ticket_questions FROM ticket_panels WHERE guild_id = ? ORDER BY panel_id",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    panels = []
    for row in rows:
        panel_id = row[0]
        async with db.execute(
            "SELECT category_id, name, emoji, notified_roles, button_style,"
            " discord_category_id, ticket_welcome_title, ticket_welcome_message"
            " FROM ticket_categories"
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
            "select_placeholder": row[11] or DEFAULT_SELECT_PLACEHOLDER,
            "ticket_welcome_title": row[12] or DEFAULT_TICKET_WELCOME_TITLE,
            "ticket_welcome_message": row[13] or DEFAULT_TICKET_WELCOME_MESSAGE,
            "ticket_created_message": row[14] or DEFAULT_TICKET_CREATED_MESSAGE,
            "ticket_questions": _clean_questions(row[15]),
            "posted": bool(row[3]),
            "categories": [
                {
                    "category_id": c[0],
                    "name": label_emoji(c[1], c[2], limit=80)[0],
                    "emoji": label_emoji(c[1], c[2], limit=80)[1] or "",
                    "staff_roles": _split_roles(c[3]),
                    "button_style": c[4] or 2,
                    "discord_category_id": str(c[5]) if c[5] else None,
                    "ticket_welcome_title": c[6] or "",
                    "ticket_welcome_message": c[7] or "",
                }
                for c in cats
            ],
        })
    for panel in panels:
        panel['settings'] = await ticket_settings.load(db, guild_id, 'panel', panel['panel_id'])
        for category in panel['categories']:
            category['settings'] = await ticket_settings.load(db, guild_id, 'category', category['category_id'])
            async with db.execute('SELECT COUNT(*) FROM open_tickets WHERE guild_id=? AND category_db_id=? AND closed_at IS NULL', (guild_id, category['category_id'])) as cursor:
                category['open_tickets'] = (await cursor.fetchone())[0]
    return panels


async def create_panel(
    db: aiosqlite.Connection, guild_id: int, name: str = "Support"
) -> int:
    await ensure_schema(db)
    cursor = await db.execute(
        "INSERT INTO ticket_panels (guild_id, name, embed_title,"
        " embed_description, embed_color, ticket_welcome_message, ticket_created_message)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            guild_id,
            name[:100] or "Support",
            name[:100] or "Support",
            "Choose a category below to create a ticket.",
            0x5865F2,
            DEFAULT_TICKET_WELCOME_MESSAGE,
            DEFAULT_TICKET_CREATED_MESSAGE,
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
    "select_placeholder": "select_placeholder",
    "ticket_welcome_title": "ticket_welcome_title",
    "ticket_welcome_message": "ticket_welcome_message",
    "ticket_created_message": "ticket_created_message",
    "ticket_questions": "ticket_questions",
}


async def update_panel(
    db: aiosqlite.Connection, guild_id: int, panel_id: int, data: dict
) -> bool:
    """
    Patch one panel. Only the keys that were sent are touched, so saving
    the appearance cannot wipe the channel.
    """
    await ensure_schema(db)

    async with db.execute('SELECT 1 FROM ticket_panels WHERE guild_id=? AND panel_id=?', (guild_id, panel_id)) as cursor:
        if not await cursor.fetchone():
            raise ValueError('Panel not found.')
    settings = ticket_settings.validate(data['settings']) if 'settings' in data else None
    # Fields that may legitimately be cleared. For the rest, null still
    # means "not sent" — otherwise a partial update would blank them.
    NULLABLE = {"channel_id", "embed_image_url", "embed_thumbnail_url"}

    assignments, values = [], []
    for key, column in _WRITABLE.items():
        if key not in data:
            continue
        if data[key] is None and key not in NULLABLE:
            continue
        value = data[key]
        if key == 'name':
            value = str(value).strip()[:100]
            if not value:raise ValueError('A panel needs a name.')
        elif key == 'panel_type' and value not in ('button','dropdown'):
            raise ValueError('Choose buttons or a dropdown for the panel.')
        elif key == 'channel_id' and value and not str(value).isdigit():
            raise ValueError('Select a valid panel channel.')
        elif key in ('embed_image_url','embed_thumbnail_url') and value and not str(value).startswith('https://'):
            raise ValueError('Image addresses must start with https://.')
        if key == "select_placeholder":
            value = str(value).strip()[:MAX_SELECT_PLACEHOLDER] or DEFAULT_SELECT_PLACEHOLDER
        elif key == "ticket_welcome_title":
            value = str(value).strip()[:256] or DEFAULT_TICKET_WELCOME_TITLE
        elif key == "ticket_welcome_message":
            value = str(value).strip()[:4000] or DEFAULT_TICKET_WELCOME_MESSAGE
        elif key == "ticket_created_message":
            value = str(value).strip()[:1900] or DEFAULT_TICKET_CREATED_MESSAGE
        elif key == "ticket_questions":
            ticket_settings.validate({'opening_questions': value[:5] if isinstance(value,list) else value})
            normalized = _clean_questions(value)
            ticket_settings.validate({'opening_questions': normalized})
            value = json.dumps(normalized, ensure_ascii=False)
        assignments.append(f"{column} = ?")
        values.append(value)

    if "staff_roles" in data and data["staff_roles"] is not None:
        assignments.append("staff_roles = ?")
        values.append(",".join(str(r) for r in data["staff_roles"]))

    if settings is not None:
        await ticket_settings.save(db, guild_id, 'panel', panel_id, settings)
    if not assignments:
        await db.commit()
        return settings is not None

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

    async with db.execute('SELECT 1 FROM ticket_panels WHERE guild_id=? AND panel_id=?', (guild_id, panel_id)) as cursor:
        if not await cursor.fetchone():
            raise ValueError('Panel not found.')
    preferences = ticket_settings.validate(data['settings'], category=True) if 'settings' in data else None
    if data.get('category_id'):
        async with db.execute('SELECT 1 FROM ticket_categories WHERE guild_id=? AND panel_id=? AND category_id=?', (guild_id,panel_id,data['category_id'])) as cursor:
            if not await cursor.fetchone():
                raise ValueError('Category not found in this panel.')
    raw_name = str(data.get("name", "")).strip()
    name, emoji = label_emoji(raw_name, data.get("emoji"), limit=80)
    if not raw_name:
        name = ""
    if not name:
        raise ValueError("A category needs a name.")

    if not data.get('category_id'):
        async with db.execute('SELECT COUNT(*) FROM ticket_categories WHERE guild_id=? AND panel_id=?', (guild_id,panel_id)) as cursor:
            if (await cursor.fetchone())[0] >= 25:
                raise ValueError('A ticket panel can contain up to 25 categories.')
    emoji = str(emoji or "")[:128]
    roles = ",".join(str(r) for r in (data.get("staff_roles") or []))
    try:
        style = max(1, min(int(data.get("button_style", 2)), 4))
    except (TypeError, ValueError):
        style = 2
    target = data.get("discord_category_id") or None
    category_id = data.get("category_id")
    existing_title = existing_message = ""
    if category_id and (
        "ticket_welcome_title" not in data or "ticket_welcome_message" not in data
    ):
        async with db.execute(
            "SELECT ticket_welcome_title, ticket_welcome_message"
            " FROM ticket_categories WHERE category_id = ? AND guild_id = ?",
            (category_id, guild_id),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing:
            existing_title = str(existing[0] or "")
            existing_message = str(existing[1] or "")
    welcome_title = str(
        data.get("ticket_welcome_title", existing_title) or ""
    ).strip()[:256]
    welcome_message = str(
        data.get("ticket_welcome_message", existing_message) or ""
    ).strip()[:4000]

    if category_id:
        await db.execute(
            "UPDATE ticket_categories SET name = ?, emoji = ?, notified_roles = ?,"
            " button_style = ?, discord_category_id = ?, panel_id = ?,"
            " ticket_welcome_title = ?, ticket_welcome_message = ?"
            " WHERE category_id = ? AND guild_id = ?",
            (
                name, emoji, roles, style, target, panel_id,
                welcome_title, welcome_message, category_id, guild_id,
            ),
        )
        if preferences is not None:
            await ticket_settings.save(db, guild_id, 'category', category_id, preferences)
        await db.commit()
        return int(category_id)

    cursor = await db.execute(
        "INSERT INTO ticket_categories (guild_id, panel_id, name, emoji,"
        " notified_roles, button_style, discord_category_id,"
        " ticket_welcome_title, ticket_welcome_message)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            guild_id, panel_id, name, emoji, roles, style, target,
            welcome_title, welcome_message,
        ),
    )
    category_id = cursor.lastrowid
    if preferences is not None:
        await ticket_settings.save(db, guild_id, 'category', category_id, preferences)
    await db.commit()
    return category_id


async def delete_category(
    db: aiosqlite.Connection, guild_id: int, category_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM ticket_categories WHERE category_id = ? AND guild_id = ?",
        (category_id, guild_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0
