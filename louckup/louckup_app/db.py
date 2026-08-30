"""Eigene SQLite-Datenbank für Louckup.

Nur zwei Tabellen: bekannte Konten und ein Protokoll der Loginversuche.
Letzteres ist der Grund, warum die Datei überhaupt existiert: wer nicht
auf der Owner-Liste steht, wird stumm weitergeleitet — ohne Protokoll
wüsste niemand, dass sich da jemand probiert hat.
"""

from __future__ import annotations

import time
from typing import Any

import aiosqlite

from louckup_app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    username         TEXT NOT NULL,
    global_name      TEXT,
    avatar           TEXT,
    email            TEXT,
    verified         INTEGER DEFAULT 0,
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at INTEGER,
    scopes           TEXT,
    is_owner         INTEGER DEFAULT 0,
    last_login_at    INTEGER,
    updated_at       INTEGER NOT NULL
);

-- Die Server, die der User beim Login mit `guilds` freigegeben hat.
-- Pro User getrennt: auf dem Self-Reiter sieht jeder nur seine eigenen.
CREATE TABLE IF NOT EXISTS user_guilds (
    user_id      INTEGER NOT NULL,
    guild_id     INTEGER NOT NULL,
    name         TEXT,
    icon         TEXT,
    owner        INTEGER DEFAULT 0,
    permissions  TEXT,
    member_count INTEGER,
    updated_at   INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);

-- Zusaetzliche Bots fuer die Suche. Der Hauptbot steht nicht hier:
-- sein Token kommt aus der Umgebung und ist nicht entfernbar.
CREATE TABLE IF NOT EXISTS bots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    label           TEXT NOT NULL,
    discord_id      INTEGER,
    username        TEXT,
    application     TEXT,
    avatar          TEXT,
    token_cipher    TEXT NOT NULL,
    scope_hinweis   TEXT,
    added_by        INTEGER,
    last_checked_at INTEGER,
    last_check_ok   INTEGER DEFAULT 0,
    last_check_text TEXT,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    username     TEXT,
    is_owner     INTEGER DEFAULT 0,
    outcome      TEXT NOT NULL,
    detail       TEXT,
    created_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_user ON login_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON login_attempts(created_at);
"""


async def connect() -> aiosqlite.Connection:
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(_SCHEMA)
    await db.commit()
    return db


async def upsert_user(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    username: str,
    global_name: str | None,
    avatar: str | None,
    email: str | None = None,
    verified: bool | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: int | None = None,
    scopes: str | None = None,
    is_owner: bool = False,
) -> None:
    now = int(time.time())
    await db.execute(
        """
        INSERT INTO users (
            user_id, username, global_name, avatar, email, verified,
            access_token, refresh_token, token_expires_at, scopes,
            is_owner, last_login_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            global_name=excluded.global_name,
            avatar=excluded.avatar,
            email=COALESCE(excluded.email, users.email),
            verified=COALESCE(excluded.verified, users.verified),
            access_token=COALESCE(excluded.access_token, users.access_token),
            refresh_token=COALESCE(excluded.refresh_token, users.refresh_token),
            token_expires_at=COALESCE(excluded.token_expires_at, users.token_expires_at),
            scopes=COALESCE(excluded.scopes, users.scopes),
            is_owner=excluded.is_owner,
            last_login_at=excluded.last_login_at,
            updated_at=excluded.updated_at
        """,
        (
            user_id,
            username,
            global_name,
            avatar,
            email,
            None if verified is None else int(verified),
            access_token,
            refresh_token,
            token_expires_at,
            scopes,
            int(is_owner),
            now,
            now,
        ),
    )
    await db.commit()


async def get_user(db: aiosqlite.Connection, user_id: int) -> dict[str, Any] | None:
    cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def replace_user_guilds(
    db: aiosqlite.Connection, user_id: int, guilds: list[dict[str, Any]]
) -> int:
    now = int(time.time())
    await db.execute("DELETE FROM user_guilds WHERE user_id = ?", (user_id,))
    saved = 0
    for g in guilds:
        try:
            gid = int(g.get("id"))
        except (TypeError, ValueError):
            continue
        await db.execute(
            """
            INSERT INTO user_guilds (user_id, guild_id, name, icon, owner, permissions, member_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                name=excluded.name, icon=excluded.icon, owner=excluded.owner,
                permissions=excluded.permissions, member_count=excluded.member_count,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                gid,
                g.get("name"),
                g.get("icon"),
                1 if g.get("owner") else 0,
                str(g.get("permissions") or "0"),
                g.get("approximate_member_count"),
                now,
            ),
        )
        saved += 1
    await db.commit()
    return saved


async def list_user_guilds(db: aiosqlite.Connection, user_id: int) -> list[dict[str, Any]]:
    cur = await db.execute(
        "SELECT * FROM user_guilds WHERE user_id = ? ORDER BY name COLLATE NOCASE",
        (user_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def record_attempt(
    db: aiosqlite.Connection,
    *,
    user_id: int | None,
    username: str | None,
    is_owner: bool,
    outcome: str,
    detail: str | None = None,
) -> None:
    await db.execute(
        """
        INSERT INTO login_attempts (user_id, username, is_owner, outcome, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, int(is_owner), outcome, (detail or "")[:300], int(time.time())),
    )
    await db.commit()


async def own_attempts(
    db: aiosqlite.Connection, user_id: int, limit: int = 10
) -> list[dict[str, Any]]:
    """Nur die Loginversuche dieses einen Kontos.

    Die Tabelle enthaelt auch die der anderen Owner — die gehen
    niemanden etwas an und werden hier gar nicht erst geholt.
    """
    cur = await db.execute(
        "SELECT * FROM login_attempts WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    )
    return [dict(r) for r in await cur.fetchall()]


async def recent_attempts(db: aiosqlite.Connection, limit: int = 10) -> list[dict[str, Any]]:
    cur = await db.execute(
        "SELECT * FROM login_attempts ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def known_user_count(db: aiosqlite.Connection) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM users")
    return (await cur.fetchone())[0] or 0


# ── Bots ──────────────────────────────────────────────────────────


async def add_bot(
    db: aiosqlite.Connection,
    *,
    label: str,
    discord_id: int | None,
    username: str | None,
    application: str | None,
    avatar: str | None,
    token_cipher: str,
    added_by: int | None = None,
) -> int:
    cur = await db.execute(
        """
        INSERT INTO bots (label, discord_id, username, application, avatar,
                          token_cipher, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (label, discord_id, username, application, avatar, token_cipher, added_by, int(time.time())),
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_bots(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cur = await db.execute("SELECT * FROM bots ORDER BY created_at, id")
    return [dict(r) for r in await cur.fetchall()]


async def get_bot(db: aiosqlite.Connection, bot_id: int) -> dict[str, Any] | None:
    cur = await db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def remove_bot(db: aiosqlite.Connection, bot_id: int) -> bool:
    cur = await db.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
    await db.commit()
    return cur.rowcount > 0


async def note_check(
    db: aiosqlite.Connection,
    bot_id: int,
    *,
    ok: bool,
    text: str,
    discord_id: int | None = None,
    username: str | None = None,
    application: str | None = None,
    avatar: str | None = None,
    label: str | None = None,
) -> None:
    """Ergebnis einer Token-Pruefung festhalten.

    Name und Bild kommen von selbst mit — wer den Bot umbenennt, hat
    ihn ja gerade geprueft. `label` wird nur geschrieben, wenn einer
    uebergeben wird; so bleibt ein von Hand vergebener Name unangetastet,
    waehrend ein automatisch geholter sich mit dem Konto mitaendert.
    """
    # `COALESCE` heisst hier: was Discord nicht liefert, bleibt, wie es
    # war. Nur der Avatar wird ersetzt, auch durch „keiner", damit ein
    # geloeschtes Bild nicht als altes weiter angezeigt wird.
    await db.execute(
        """
        UPDATE bots
        SET last_checked_at = ?, last_check_ok = ?, last_check_text = ?,
            discord_id  = COALESCE(?, discord_id),
            username    = COALESCE(?, username),
            application = COALESCE(?, application),
            avatar      = ?,
            label       = COALESCE(?, label)
        WHERE id = ?
        """,
        (
            int(time.time()), int(ok), text[:300],
            discord_id, username, application, avatar,
            (label[:120] if label else None), bot_id,
        ),
    )
    await db.commit()
