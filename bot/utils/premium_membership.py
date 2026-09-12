"""Account subscriptions with three fixed guild Premium slots."""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "premium_membership.db")
MAX_SLOTS = 3
PLANS = (30, 90, 365)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def ensure() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS premium_accounts (
          user_id TEXT PRIMARY KEY, granted_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL, duration_days INTEGER NOT NULL,
          source TEXT NOT NULL DEFAULT 'admin', note TEXT NOT NULL DEFAULT '',
          notice_pending INTEGER NOT NULL DEFAULT 1, revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS premium_slots (
          user_id TEXT NOT NULL, slot_no INTEGER NOT NULL,
          guild_id INTEGER NOT NULL UNIQUE, assigned_at INTEGER NOT NULL,
          expiry_action TEXT NOT NULL DEFAULT 'keep',
          PRIMARY KEY(user_id, slot_no)
        );
        CREATE INDEX IF NOT EXISTS premium_slots_guild ON premium_slots(guild_id);
        CREATE TABLE IF NOT EXISTS premium_purchase_requests (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          duration_days INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          created_at INTEGER NOT NULL, decided_at INTEGER, decided_by TEXT,
          note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS premium_v2_meta (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        """)


def migrate_reset_legacy() -> bool:
    """One-time cut-over requested by the owner: remove grants, keep configs."""
    ensure()
    with _connect() as db:
        done = db.execute("SELECT 1 FROM premium_v2_meta WHERE key='legacy_reset_v1'").fetchone()
        if done:
            return False
        # New account and slot state starts empty.
        db.execute("DELETE FROM premium_accounts")
        db.execute("DELETE FROM premium_slots")
        db.execute("UPDATE premium_purchase_requests SET status='cancelled' WHERE status='pending'")
        db.execute("INSERT INTO premium_v2_meta(key,value) VALUES('legacy_reset_v1',?)", (str(int(time.time())),))
    # Old account grants and old direct server grants must no longer confer Premium.
    try:
        with sqlite3.connect(os.path.join("db", "premium.db")) as old:
            old.execute("UPDATE premium_keys SET revoked=1 WHERE revoked=0")
    except sqlite3.Error:
        pass
    try:
        with sqlite3.connect(os.path.join("db", "admin_config.db")) as old:
            old.execute("DELETE FROM premium_guilds")
    except sqlite3.Error:
        pass
    return True


def account_status(user_id: int | str) -> dict[str, Any]:
    ensure(); now = int(time.time()); uid = str(user_id)
    with _connect() as db:
        row = db.execute("SELECT * FROM premium_accounts WHERE user_id=?", (uid,)).fetchone()
        slots = db.execute("SELECT * FROM premium_slots WHERE user_id=? ORDER BY slot_no", (uid,)).fetchall()
        requests = db.execute("SELECT id,duration_days,status,created_at,decided_at FROM premium_purchase_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (uid,)).fetchall()
    active = bool(row and not row["revoked"] and int(row["expires_at"]) > now)
    return {
        "user_id": uid, "product": "premium", "premium": active,
        "granted_at": int(row["granted_at"]) if row else None,
        "expires_at": int(row["expires_at"]) if row else None,
        "duration_days": int(row["duration_days"]) if row else 0,
        "source": row["source"] if row else "", "note": row["note"] if row else "",
        "notice_pending": bool(row and row["notice_pending"]),
        "lifetime": False, "via_trial": False, "via_tester": False,
        "max_slots": MAX_SLOTS,
        "slots": [dict(slot) for slot in slots],
        "purchase_requests": [dict(request) for request in requests],
    }


def grant(user_id: int | str, duration_days: int, source: str = "admin", note: str = "") -> dict[str, Any]:
    ensure(); uid = str(user_id); days = int(duration_days)
    if days not in PLANS:
        raise ValueError("Erlaubte Laufzeiten sind 30, 90 oder 365 Tage.")
    now = int(time.time())
    with _connect() as db:
        current = db.execute("SELECT expires_at FROM premium_accounts WHERE user_id=? AND revoked=0", (uid,)).fetchone()
        base = max(now, int(current[0])) if current else now
        expires = base + days * 86400
        db.execute("""INSERT INTO premium_accounts
          (user_id,granted_at,expires_at,duration_days,source,note,notice_pending,revoked)
          VALUES(?,?,?,?,?,?,1,0) ON CONFLICT(user_id) DO UPDATE SET
          granted_at=excluded.granted_at,expires_at=excluded.expires_at,duration_days=excluded.duration_days,
          source=excluded.source,note=excluded.note,notice_pending=1,revoked=0""",
          (uid, now, expires, days, source, str(note)[:200]))
    return account_status(uid)


def revoke(user_id: int | str) -> bool:
    ensure()
    with _connect() as db:
        cur = db.execute("UPDATE premium_accounts SET revoked=1, notice_pending=0 WHERE user_id=?", (str(user_id),))
        return cur.rowcount > 0


def dismiss_notice(user_id: int | str) -> None:
    ensure()
    with _connect() as db:
        db.execute("UPDATE premium_accounts SET notice_pending=0 WHERE user_id=?", (str(user_id),))


def request_purchase(user_id: int | str, duration_days: int) -> dict[str, Any]:
    ensure(); days = int(duration_days)
    if days not in PLANS:
        raise ValueError("Wähle 30, 90 oder 365 Tage.")
    uid = str(user_id); now = int(time.time())
    with _connect() as db:
        pending = db.execute("SELECT id FROM premium_purchase_requests WHERE user_id=? AND status='pending'", (uid,)).fetchone()
        if pending:
            return {"id": pending[0], "status": "pending", "already": True}
        cur = db.execute("INSERT INTO premium_purchase_requests(user_id,duration_days,created_at) VALUES(?,?,?)", (uid, days, now))
        return {"id": cur.lastrowid, "status": "pending", "already": False}


def assign_slot(user_id: int | str, guild_id: int) -> dict[str, Any]:
    status = account_status(user_id)
    if not status["premium"]:
        raise ValueError("Dein Konto hat kein aktives Premium.")
    uid = str(user_id); gid = int(guild_id); now = int(time.time())
    with _connect() as db:
        existing = db.execute("SELECT user_id,slot_no FROM premium_slots WHERE guild_id=?", (gid,)).fetchone()
        if existing:
            if existing["user_id"] == uid:
                return {"slot_no": existing["slot_no"], "guild_id": gid, "already": True}
            raise ValueError("Dieser Server ist bereits einem anderen Premium-Konto zugeordnet.")
        used = {int(r[0]) for r in db.execute("SELECT slot_no FROM premium_slots WHERE user_id=?", (uid,))}
        slot = next((n for n in range(1, MAX_SLOTS + 1) if n not in used), None)
        if slot is None:
            raise ValueError("Alle drei festen Premium-Plätze sind bereits belegt.")
        db.execute("INSERT INTO premium_slots(user_id,slot_no,guild_id,assigned_at) VALUES(?,?,?,?)", (uid, slot, gid, now))
    return {"slot_no": slot, "guild_id": gid, "already": False}


def set_expiry_action(guild_id: int, action: str) -> None:
    if action not in {"keep", "disable"}:
        raise ValueError("Ungültige Ablaufaktion.")
    ensure()
    with _connect() as db:
        db.execute("UPDATE premium_slots SET expiry_action=? WHERE guild_id=?", (action, int(guild_id)))


def guild_status(guild_id: int) -> dict[str, Any]:
    ensure(); now = int(time.time())
    with _connect() as db:
        row = db.execute("""SELECT s.*,a.expires_at,a.duration_days,a.revoked,a.user_id account_user_id
          FROM premium_slots s JOIN premium_accounts a ON a.user_id=s.user_id
          WHERE s.guild_id=?""", (int(guild_id),)).fetchone()
    if not row:
        return {"guild_id": str(guild_id), "assigned": False, "active": False, "runtime": False, "configurable": False}
    active = not row["revoked"] and int(row["expires_at"]) > now
    frozen = not active and row["expiry_action"] == "keep"
    return {"guild_id": str(guild_id), "assigned": True, "active": active,
            "runtime": active or frozen, "configurable": active,
            "frozen": frozen, "expires_at": int(row["expires_at"]),
            "duration_days": int(row["duration_days"]),
            "assigned_at": int(row["assigned_at"]),
            "expiry_action": row["expiry_action"], "slot_no": row["slot_no"],
            "account_user_id": row["account_user_id"]}


def runtime_guilds() -> tuple[set[int], dict[int, int | None]]:
    ensure(); now = int(time.time()); guilds=set(); expiry={}
    with _connect() as db:
        rows=db.execute("""SELECT s.guild_id,s.expiry_action,a.expires_at,a.revoked
          FROM premium_slots s JOIN premium_accounts a ON a.user_id=s.user_id""").fetchall()
    for row in rows:
        active=not row["revoked"] and int(row["expires_at"]) > now
        if active or row["expiry_action"] == "keep":
            gid=int(row["guild_id"]); guilds.add(gid); expiry[gid]=None if not active else int(row["expires_at"])
    return guilds, expiry


def configurable_guild(guild_id: int) -> bool:
    return bool(guild_status(guild_id).get("configurable"))


def list_requests() -> list[dict[str, Any]]:
    ensure()
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM premium_purchase_requests ORDER BY created_at DESC LIMIT 300")]


def decide_request(request_id: int, approve: bool, admin_id: str) -> dict[str, Any]:
    ensure(); now=int(time.time())
    with _connect() as db:
        row=db.execute("SELECT * FROM premium_purchase_requests WHERE id=? AND status='pending'", (int(request_id),)).fetchone()
        if not row: raise ValueError("Anfrage nicht gefunden oder bereits entschieden.")
        db.execute("UPDATE premium_purchase_requests SET status=?,decided_at=?,decided_by=? WHERE id=?", ("approved" if approve else "denied",now,str(admin_id),int(request_id)))
    if approve:
        return grant(row["user_id"], row["duration_days"], "purchase_request", f"Anfrage #{request_id}")
    return {"status":"denied", "user_id":row["user_id"]}


def active_user_ids() -> set[str]:
    ensure(); now = int(time.time())
    with _connect() as db:
        return {str(r[0]) for r in db.execute(
            "SELECT user_id FROM premium_accounts WHERE revoked=0 AND expires_at>?", (now,)
        )}


def list_accounts() -> list[dict[str, Any]]:
    ensure()
    with _connect() as db:
        rows=db.execute("SELECT * FROM premium_accounts ORDER BY granted_at DESC").fetchall()
    return [{**dict(r), **account_status(r["user_id"])} for r in rows]
