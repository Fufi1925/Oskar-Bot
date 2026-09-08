"""Six-digit, multi-use promo codes for guild-scoped Premium."""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "admin_config.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def ensure(db: sqlite3.Connection | None = None) -> None:
    own = db is None
    db = db or _connect()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS premium_codes (
            code TEXT PRIMARY KEY,
            premium_days INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            redeem_until INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS premium_code_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL REFERENCES premium_codes(code),
            guild_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            redeemed_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(code, guild_id),
            UNIQUE(code, user_id)
        );
        CREATE TABLE IF NOT EXISTS premium_code_attempts (
            user_id TEXT NOT NULL,
            attempted_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS premium_code_attempt_user
            ON premium_code_attempts(user_id, attempted_at);
        CREATE TABLE IF NOT EXISTS premium_guilds (
            guild_id INTEGER PRIMARY KEY,
            granted_at INTEGER,
            expires_at INTEGER
        );
    """)
    try:
        db.execute("ALTER TABLE premium_guilds ADD COLUMN expires_at INTEGER")
    except sqlite3.OperationalError:
        pass
    if own:
        db.commit()
        db.close()


def _new_code(db: sqlite3.Connection) -> str:
    for _ in range(100):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not db.execute("SELECT 1 FROM premium_codes WHERE code=?", (code,)).fetchone():
            return code
    raise RuntimeError("Es konnte kein freier Code erzeugt werden.")


def create(*, premium_days: int, max_uses: int, valid_hours: int,
           created_by: str) -> dict[str, Any]:
    now = int(time.time())
    with _connect() as db:
        ensure(db)
        code = _new_code(db)
        db.execute(
            "INSERT INTO premium_codes(code,premium_days,max_uses,redeem_until,created_at,created_by) VALUES(?,?,?,?,?,?)",
            (code, premium_days, max_uses, now + valid_hours * 3600, now, created_by),
        )
    return get(code) or {}


def get(code: str) -> dict[str, Any] | None:
    with _connect() as db:
        ensure(db)
        row = db.execute("SELECT * FROM premium_codes WHERE code=?", (str(code),)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["uses"] = db.execute(
            "SELECT COUNT(*) FROM premium_code_redemptions WHERE code=? AND revoked=0", (code,)
        ).fetchone()[0]
        return result


def list_codes(limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as db:
        ensure(db)
        rows = db.execute("SELECT * FROM premium_codes ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            uses = db.execute(
                "SELECT * FROM premium_code_redemptions WHERE code=? ORDER BY redeemed_at DESC", (row["code"],)
            ).fetchall()
            item["redemptions"] = [dict(use) for use in uses]
            item["uses"] = sum(not bool(use["revoked"]) for use in uses)
            result.append(item)
        return result


def _record_failed(db: sqlite3.Connection, user_id: str, now: int) -> None:
    db.execute("INSERT INTO premium_code_attempts(user_id,attempted_at) VALUES(?,?)", (user_id, now))
    db.execute("DELETE FROM premium_code_attempts WHERE attempted_at < ?", (now - 86400,))


def inspect(code: str, user_id: str) -> dict[str, Any]:
    code = str(code or "").strip()
    now = int(time.time())
    with _connect() as db:
        ensure(db)
        recent = db.execute(
            "SELECT COUNT(*) FROM premium_code_attempts WHERE user_id=? AND attempted_at>?",
            (user_id, now - 600),
        ).fetchone()[0]
        if recent >= 8:
            return {"ok": False, "error": "rate_limited"}
        row = db.execute("SELECT * FROM premium_codes WHERE code=?", (code,)).fetchone()
        if not row:
            _record_failed(db, user_id, now)
            return {"ok": False, "error": "unknown"}
        item = dict(row)
        uses = db.execute(
            "SELECT COUNT(*) FROM premium_code_redemptions WHERE code=? AND revoked=0", (code,)
        ).fetchone()[0]
        if item["revoked"]:
            return {"ok": False, "error": "revoked"}
        if item["redeem_until"] <= now:
            return {"ok": False, "error": "expired"}
        if uses >= item["max_uses"]:
            return {"ok": False, "error": "used_up"}
        if db.execute("SELECT 1 FROM premium_code_redemptions WHERE code=? AND user_id=?", (code, user_id)).fetchone():
            return {"ok": False, "error": "already_used"}
        return {"ok": True, "code": code, "premium_days": item["premium_days"],
                "remaining_uses": item["max_uses"] - uses, "redeem_until": item["redeem_until"]}


def redeem(code: str, user_id: str, guild_id: int) -> dict[str, Any]:
    now = int(time.time())
    code = str(code or "").strip()
    with _connect() as db:
        ensure(db)
        db.execute("BEGIN IMMEDIATE")
        recent = db.execute("SELECT COUNT(*) FROM premium_code_attempts WHERE user_id=? AND attempted_at>?", (user_id, now - 600)).fetchone()[0]
        if recent >= 8:
            return {"ok": False, "error": "rate_limited"}
        row = db.execute("SELECT * FROM premium_codes WHERE code=?", (code,)).fetchone()
        if not row:
            _record_failed(db, user_id, now)
            return {"ok": False, "error": "unknown"}
        uses = db.execute("SELECT COUNT(*) FROM premium_code_redemptions WHERE code=? AND revoked=0", (code,)).fetchone()[0]
        error = ""
        if row["revoked"]: error = "revoked"
        elif row["redeem_until"] <= now: error = "expired"
        elif uses >= row["max_uses"]: error = "used_up"
        elif db.execute("SELECT 1 FROM premium_code_redemptions WHERE code=? AND user_id=?", (code, user_id)).fetchone(): error = "already_used"
        elif db.execute("SELECT 1 FROM premium_code_redemptions WHERE code=? AND guild_id=?", (code, guild_id)).fetchone(): error = "guild_used"
        if error:
            return {"ok": False, "error": error}

        existing = db.execute("SELECT expires_at FROM premium_guilds WHERE guild_id=?", (guild_id,)).fetchone()
        if existing and existing["expires_at"] is None:
            return {"ok": False, "error": "already_lifetime"}
        base = max(now, int(existing["expires_at"] or 0)) if existing else now
        expires = base + int(row["premium_days"]) * 86400
        db.execute("INSERT INTO premium_code_redemptions(code,guild_id,user_id,redeemed_at,expires_at) VALUES(?,?,?,?,?)", (code, guild_id, user_id, now, expires))
        db.execute("INSERT OR REPLACE INTO premium_guilds(guild_id,granted_at,expires_at) VALUES(?,?,?)", (guild_id, now, expires))
        return {"ok": True, "expires_at": expires, "premium_days": row["premium_days"]}


def revoke_code(code: str) -> bool:
    with _connect() as db:
        ensure(db)
        return db.execute("UPDATE premium_codes SET revoked=1 WHERE code=?", (code,)).rowcount > 0


def revoke_redemption(redemption_id: int) -> dict[str, Any]:
    with _connect() as db:
        ensure(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM premium_code_redemptions WHERE id=?", (redemption_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if row["revoked"]:
            return {"ok": True, "already": True, "guild_id": row["guild_id"]}
        db.execute("UPDATE premium_code_redemptions SET revoked=1 WHERE id=?", (redemption_id,))
        current = db.execute("SELECT expires_at FROM premium_guilds WHERE guild_id=?", (row["guild_id"],)).fetchone()
        # Never remove a permanent/manual grant or a newer entitlement.
        if current and current["expires_at"] == row["expires_at"]:
            other = db.execute("SELECT MAX(expires_at) FROM premium_code_redemptions WHERE guild_id=? AND revoked=0 AND expires_at>?", (row["guild_id"], int(time.time()))).fetchone()[0]
            if other:
                db.execute("UPDATE premium_guilds SET expires_at=? WHERE guild_id=?", (other, row["guild_id"]))
            else:
                db.execute("DELETE FROM premium_guilds WHERE guild_id=?", (row["guild_id"],))
        return {"ok": True, "guild_id": row["guild_id"]}
