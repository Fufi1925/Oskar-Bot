# ╔══════════════════════════════════════════════════════════════════╗
# ║   Verification: settings, texts and the rules                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Everything the verification tab can configure.

The old version stored five columns and hard-coded the rest, so a server
could pick a channel and a role and nothing else. Every word the bot
said during verification was baked into the cog in English, there was no
way to turn the direct messages off, and the dashboard could not see any
of it.

Real bugs this module exists around:

  * **``on_message`` had no DM guard.** It read ``message.guild.id``
    straight away, so every direct message the bot received raised
    AttributeError before the handler could return -- the same shape of
    bug already found in counting and customrole.

  * **The API wrote ``0`` for "not set".** ``verification_channel_id or 0``
    turns an unset channel into the id 0, which is not null and not a
    channel; the read side then handed ``"0"`` back to the dashboard as
    if it were a real snowflake.

  * **A partial save wiped the panel.** The PATCH used COALESCE on every
    column, which is right, but the INSERT branch defaulted the others
    to 0 -- so the first save from the dashboard dropped whatever the
    chat command had set up.

Placeholders are resolved in one place so the preview in the dashboard
and the message in Discord cannot drift apart.
"""

from __future__ import annotations

import re

from typing import Any

import aiosqlite

DB_PATH = "db/verification.db"

# Discord's own limits, checked before we send something it will refuse.
MAX_BUTTON_LABEL = 80
MAX_TEXT = 3800          # a V2 container tops out around 4000
MAX_TITLE = 200

METHODS = ("button", "captcha", "both")

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "verification_channel_id": None,
    "verified_role_id": None,
    "log_channel_id": None,
    "unverified_role_id": None,
    "verification_method": "both",
    "panel_message_id": None,
    "panel_channel_id": None,

    # ── the texts ────────────────────────────────────────────────
    "panel_title": "Verifizierung",
    "panel_text": (
        "Willkommen auf **{server}**!\n"
        "Verifiziere dich, um den Rest des Servers zu sehen."
    ),
    "panel_footer": "Du bekommst danach die Rolle {role}.",
    "button_label": "Verifizieren",
    "captcha_label": "Mit CAPTCHA",
    "success_text": (
        "Willkommen auf **{server}**, {user}!\n"
        "Du hast jetzt Zugriff auf alle Kanäle."
    ),

    # ── direct messages ──────────────────────────────────────────
    # The CAPTCHA image has to go somewhere private, so that one is not
    # optional -- but whether the bot congratulates people afterwards is.
    "dm_on_success": False,
    "dm_success_text": (
        "Du bist jetzt auf **{server}** verifiziert. Viel Spaß!"
    ),
    # The nag when somebody writes in the verification channel.
    "dm_on_delete": True,

    # ── extra rules, off unless asked for ────────────────────────
    "min_account_age_days": 0,
    "verify_timeout_minutes": 0,
    # Remove the unverified role once they pass, if one is set.
    "remove_unverified_role": True,
    "delete_messages": True,
}

# Which keys hold a snowflake. JSON numbers lose the last digits of an
# id, so these travel as strings and are converted here.
ID_KEYS = (
    "verification_channel_id", "verified_role_id", "log_channel_id",
    "unverified_role_id", "panel_message_id", "panel_channel_id",
)

TEXT_KEYS = (
    "panel_title", "panel_text", "panel_footer", "button_label",
    "captcha_label", "success_text", "dm_success_text",
)

BOOL_KEYS = (
    "enabled", "dm_on_success", "dm_on_delete", "remove_unverified_role",
    "delete_messages",
)

INT_KEYS = ("min_account_age_days", "verify_timeout_minutes")

PLACEHOLDERS = {
    "{server}": "Name des Servers",
    "{user}": "Erwähnt die Person",
    "{user.name}": "Name ohne Erwähnung",
    "{role}": "Die Rolle, die vergeben wird",
    "{member_count}": "Wie viele Mitglieder der Server hat",
}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """
    Create the table and add whatever columns are missing.

    Written as ALTER-if-absent rather than one CREATE, because the table
    already exists on every running server and CREATE TABLE IF NOT
    EXISTS would silently leave the old five-column shape in place --
    exactly how the custom_roles mismatch happened.
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_config (
            guild_id INTEGER PRIMARY KEY,
            verification_channel_id INTEGER,
            verified_role_id INTEGER,
            log_channel_id INTEGER,
            verification_method TEXT DEFAULT 'both',
            enabled BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            verification_method TEXT NOT NULL,
            verified_at TEXT NOT NULL
        )
        """
    )

    async with db.execute("PRAGMA table_info(verification_config)") as cursor:
        info = await cursor.fetchall()
    existing = {row[1] for row in info}

    # An older table declared the channel and role NOT NULL, so saving
    # any other setting before picking them failed with an IntegrityError.
    # SQLite cannot drop a constraint, so the table is rebuilt once.
    required = {
        row[1] for row in info
        if row[1] in ("verification_channel_id", "verified_role_id") and row[3]
    }
    if required:
        columns = ", ".join(existing)
        await db.execute("ALTER TABLE verification_config RENAME TO _vc_old")
        await db.execute(
            """
            CREATE TABLE verification_config (
                guild_id INTEGER PRIMARY KEY,
                verification_channel_id INTEGER,
                verified_role_id INTEGER,
                log_channel_id INTEGER,
                verification_method TEXT DEFAULT 'both',
                enabled BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        shared = [c for c in existing if c in {
            "guild_id", "verification_channel_id", "verified_role_id",
            "log_channel_id", "verification_method", "enabled", "created_at",
        }]
        await db.execute(
            f"INSERT INTO verification_config ({', '.join(shared)})"
            f" SELECT {', '.join(shared)} FROM _vc_old"
        )
        await db.execute("DROP TABLE _vc_old")
        await db.commit()
        print(
            "[verify_store] verification_config had NOT NULL on its channel "
            f"and role ({columns}); rebuilt so partial saves work."
        )

        async with db.execute("PRAGMA table_info(verification_config)") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}

    wanted = {
        "unverified_role_id": "INTEGER",
        "panel_message_id": "INTEGER",
        "panel_channel_id": "INTEGER",
        "panel_title": "TEXT",
        "panel_text": "TEXT",
        "panel_footer": "TEXT",
        "button_label": "TEXT",
        "captcha_label": "TEXT",
        "success_text": "TEXT",
        "dm_on_success": "INTEGER DEFAULT 0",
        "dm_success_text": "TEXT",
        "dm_on_delete": "INTEGER DEFAULT 1",
        "min_account_age_days": "INTEGER DEFAULT 0",
        "verify_timeout_minutes": "INTEGER DEFAULT 0",
        "remove_unverified_role": "INTEGER DEFAULT 1",
        "delete_messages": "INTEGER DEFAULT 1",
    }
    for column, ddl in wanted.items():
        if column in existing:
            continue
        try:
            await db.execute(
                f"ALTER TABLE verification_config ADD COLUMN {column} {ddl}"
            )
        except Exception:
            # Another worker got there first; harmless.
            pass

    await db.commit()


async def get_settings(db: aiosqlite.Connection, guild_id: int) -> dict:
    await ensure_schema(db)
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM verification_config WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    settings = dict(DEFAULTS)
    if row is None:
        return settings

    keys = row.keys()
    for key in DEFAULTS:
        if key not in keys:
            continue
        value = row[key]
        if value is None:
            continue
        # 0 means "not set" for an id: the old API wrote it for an unset
        # channel, and reading it back as a real id gave the dashboard a
        # channel that never existed.
        if key in ID_KEYS and not value:
            continue
        if key in TEXT_KEYS and not str(value).strip():
            continue
        settings[key] = value

    return normalise(settings)


def normalise(settings: dict) -> dict:
    """Force every field into the type the rest of the code expects."""
    out = {**DEFAULTS, **(settings or {})}

    for key in ID_KEYS:
        value = out.get(key)
        out[key] = int(value) if str(value or "").isdigit() and int(value) else None

    for key in BOOL_KEYS:
        out[key] = bool(out.get(key))

    for key in INT_KEYS:
        try:
            out[key] = max(0, int(out.get(key) or 0))
        except (TypeError, ValueError):
            out[key] = 0
    # A week is plenty; beyond that people just think it is broken.
    out["min_account_age_days"] = min(365, out["min_account_age_days"])
    out["verify_timeout_minutes"] = min(10080, out["verify_timeout_minutes"])

    if out.get("verification_method") not in METHODS:
        out["verification_method"] = "both"

    for key in TEXT_KEYS:
        text = str(out.get(key) or "").strip()
        if not text:
            text = DEFAULTS[key]
        limit = MAX_BUTTON_LABEL if key.endswith("_label") else (
            MAX_TITLE if key == "panel_title" else MAX_TEXT
        )
        out[key] = text[:limit]

    return out


async def save_settings(
    db: aiosqlite.Connection, guild_id: int, updates: dict
) -> dict:
    """
    Partial update: only the keys that were sent are written.

    The old handler inserted zeros for everything it was not given, so
    the first save from the dashboard erased a setup made over chat.
    """
    current = await get_settings(db, guild_id)
    merged = normalise({
        **current,
        **{k: v for k, v in (updates or {}).items() if k in DEFAULTS},
    })

    columns = list(DEFAULTS)
    placeholders = ", ".join("?" * (len(columns) + 1))
    values = [guild_id]
    for name in columns:
        value = merged[name]
        values.append(int(value) if isinstance(value, bool) else value)

    await db.execute(
        f"INSERT OR REPLACE INTO verification_config "
        f"(guild_id, {', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    await db.commit()
    return merged


async def clear_panel(db: aiosqlite.Connection, guild_id: int) -> None:
    await save_settings(db, guild_id, {
        "panel_message_id": None, "panel_channel_id": None,
    })


# ══════════════════════════════════════════════════════════════════════
#  Text rendering
# ══════════════════════════════════════════════════════════════════════


def render(text: str, *, server: str = "", user_mention: str = "",
           user_name: str = "", role: str = "", member_count: int = 0) -> str:
    """
    Fill in the placeholders.

    One implementation so the dashboard preview and what Discord shows
    cannot disagree -- two copies of this is how a preview ends up
    lying.
    """
    out = str(text or "")
    for token, value in (
        ("{server}", server),
        ("{user.name}", user_name),
        ("{user}", user_mention or user_name),
        ("{role}", role),
        ("{member_count}", str(member_count)),
    ):
        out = out.replace(token, str(value))
    return out


UNKNOWN_PLACEHOLDER = re.compile(r"\{[a-z_.]+\}")


def unknown_placeholders(text: str) -> list[str]:
    """
    Placeholders that will not be replaced, so the dashboard can warn.

    Typing {username} instead of {user.name} otherwise ships the literal
    braces to Discord, and nobody notices until a member reads it.
    """
    found = UNKNOWN_PLACEHOLDER.findall(str(text or ""))
    return sorted({f for f in found if f not in PLACEHOLDERS})


# ══════════════════════════════════════════════════════════════════════
#  The rules
# ══════════════════════════════════════════════════════════════════════


def account_too_young(settings: dict, account_age_days: float) -> bool:
    """Whether this account is below the configured minimum age."""
    minimum = int(settings.get("min_account_age_days") or 0)
    if minimum <= 0:
        return False
    return account_age_days < minimum


def methods_for(settings: dict) -> list[str]:
    """Which buttons the panel should carry."""
    method = settings.get("verification_method")
    if method == "button":
        return ["button"]
    if method == "captcha":
        return ["captcha"]
    return ["button", "captcha"]


def is_configured(settings: dict) -> bool:
    """Both a channel and a role are needed; one alone does nothing."""
    return bool(
        settings.get("verification_channel_id")
        and settings.get("verified_role_id")
    )


def readiness(settings: dict) -> list[str]:
    """Plain-German reasons the feature will not work as set up."""
    problems: list[str] = []

    if settings.get("enabled") and not settings.get("verification_channel_id"):
        problems.append("Verifizierung ist an, aber es ist kein Kanal gesetzt.")
    if settings.get("enabled") and not settings.get("verified_role_id"):
        problems.append("Verifizierung ist an, aber es ist keine Rolle gesetzt.")

    if settings.get("dm_on_success") and not str(
        settings.get("dm_success_text") or ""
    ).strip():
        problems.append("Die Erfolgs-DM ist an, aber der Text ist leer.")

    if settings.get("remove_unverified_role") \
            and not settings.get("unverified_role_id"):
        # Not an error, just pointless -- say so rather than silently
        # doing nothing.
        problems.append(
            "„Unverifiziert-Rolle entfernen“ ist an, aber es ist keine gesetzt."
        )

    for key, label in (
        ("panel_title", "Panel-Überschrift"),
        ("panel_text", "Panel-Text"),
        ("button_label", "Knopf-Beschriftung"),
        ("success_text", "Erfolgsmeldung"),
        ("dm_success_text", "Erfolgs-DM"),
    ):
        for bad in unknown_placeholders(settings.get(key, "")):
            problems.append(f"{label}: {bad} gibt es nicht — bleibt so stehen.")

    return problems


async def log_verification(
    db: aiosqlite.Connection, guild_id: int, user_id: int, method: str,
    when: str,
) -> None:
    await ensure_schema(db)
    await db.execute(
        "INSERT INTO verification_logs"
        " (guild_id, user_id, verification_method, verified_at)"
        " VALUES (?, ?, ?, ?)",
        (guild_id, user_id, method, when),
    )
    await db.commit()


async def recent_logs(
    db: aiosqlite.Connection, guild_id: int, limit: int = 25
) -> list[dict]:
    await ensure_schema(db)
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT user_id, verification_method, verified_at"
        " FROM verification_logs WHERE guild_id = ?"
        " ORDER BY id DESC LIMIT ?",
        (guild_id, max(1, min(limit, 100))),
    ) as cursor:
        return [
            {
                "user_id": str(row["user_id"]),
                "method": row["verification_method"],
                "at": row["verified_at"],
            }
            for row in await cursor.fetchall()
        ]


async def count_verified(db: aiosqlite.Connection, guild_id: int) -> int:
    await ensure_schema(db)
    async with db.execute(
        "SELECT COUNT(*) FROM verification_logs WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0
