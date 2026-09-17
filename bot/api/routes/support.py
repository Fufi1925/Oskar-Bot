"""Consent-based dashboard support cases.

A dashboard team member must never silently enter a customer's server.  A
support case starts as an invitation and grants temporary guild dashboard
access only after Discord's actual server owner accepts it.  Closing the case
revokes that access immediately; the audit trail and conversation remain.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_bot
from api.routes import servertools
from utils import dashboard_roles, db_paths

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()
DB_PATH = "db/admin_config.db"
SUPPORT_MIN_RANK_EXCLUSIVE = 90  # strictly above the Administrator role
ACTIVE = ("pending", "accepted")


async def _ensure(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_support_cases ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL,"
        " guild_name TEXT DEFAULT '', guild_icon TEXT DEFAULT '',"
        " supporter_id TEXT NOT NULL, supporter_name TEXT DEFAULT '',"
        " supporter_avatar TEXT DEFAULT '', supporter_role TEXT DEFAULT '',"
        " supporter_role_color TEXT DEFAULT '#ef4444', supporter_rank INTEGER DEFAULT 0,"
        " problem TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',"
        " owner_id TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,"
        " accepted_at INTEGER DEFAULT 0, closed_at INTEGER DEFAULT 0,"
        " rating INTEGER DEFAULT 0, rating_note TEXT DEFAULT '')"
    )
    async with db.execute("PRAGMA table_info(dashboard_support_cases)") as cur:
        columns = {str(row[1]) async for row in cur}
    if "rating" not in columns:
        await db.execute("ALTER TABLE dashboard_support_cases ADD COLUMN rating INTEGER DEFAULT 0")
    if "rating_note" not in columns:
        await db.execute("ALTER TABLE dashboard_support_cases ADD COLUMN rating_note TEXT DEFAULT ''")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dashboard_support_guild_status"
        " ON dashboard_support_cases(guild_id, status)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_support_messages ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL,"
        " actor_id TEXT NOT NULL, actor_name TEXT DEFAULT '', actor_avatar TEXT DEFAULT '',"
        " actor_role TEXT DEFAULT '', actor_kind TEXT NOT NULL, message TEXT NOT NULL,"
        " created_at INTEGER NOT NULL,"
        " FOREIGN KEY(case_id) REFERENCES dashboard_support_cases(id) ON DELETE CASCADE)"
    )
    await db.commit()


def _identity(request: Request) -> dict:
    return {
        "id": request.headers.get("x-dashboard-user-id", "").strip(),
        "name": unquote(request.headers.get("x-dashboard-user-name", "").strip())[:100],
        "avatar": unquote(request.headers.get("x-dashboard-user-avatar", "").strip())[:500],
        "role": unquote(request.headers.get("x-dashboard-user-role", "").strip())[:100],
        "kind": request.headers.get("x-dashboard-actor-kind", "").strip(),
    }


def _support_role(user_id: str) -> tuple[str, str, int]:
    if dashboard_roles.is_owner(user_id):
        return "Owner", "#fbbf24", 100
    roles = dashboard_roles.get_roles(user_id)
    if not roles:
        return "", "#64748b", 0
    role = roles[0]
    return role.label, role.color, role.rank


def _require_supporter(request: Request) -> tuple[dict, str, str, int]:
    actor = _identity(request)
    if not actor["id"].isdigit():
        raise HTTPException(401, "Dashboard identity missing.")
    role, color, rank = _support_role(actor["id"])
    if rank <= SUPPORT_MIN_RANK_EXCLUSIVE:
        raise HTTPException(403, "Only dashboard roles above Administrator may send support requests.")
    return actor, role, color, rank


async def _case(db, case_id: int):
    db.row_factory = __import__("aiosqlite").Row
    async with db.execute("SELECT * FROM dashboard_support_cases WHERE id = ?", (case_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def _messages(db, case_id: int) -> list[dict]:
    db.row_factory = __import__("aiosqlite").Row
    async with db.execute(
        "SELECT id, actor_id, actor_name, actor_avatar, actor_role, actor_kind, message, created_at"
        " FROM dashboard_support_messages WHERE case_id = ? ORDER BY id ASC",
        (case_id,),
    ) as cur:
        return [dict(row) async for row in cur]


async def _with_messages(db, rows) -> list[dict]:
    result = []
    for row in rows:
        item = dict(row)
        item["messages"] = await _messages(db, int(item["id"]))
        result.append(item)
    return result


@router.get("/access/{guild_id}/{user_id}", summary="Internal accepted-support access check")
async def support_access(guild_id: str, user_id: str):
    if not guild_id.isdigit() or not user_id.isdigit():
        return {"allowed": False}
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        async with db.execute(
            "SELECT 1 FROM dashboard_support_cases"
            " WHERE guild_id = ? AND supporter_id = ? AND status = 'accepted' LIMIT 1",
            (guild_id, user_id),
        ) as cur:
            return {"allowed": await cur.fetchone() is not None}


@router.get("/admin/cases", summary="List support cases for the admin dashboard")
async def admin_cases(request: Request, status: str = "all"):
    _require_supporter(request)
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        db.row_factory = __import__("aiosqlite").Row
        query = "SELECT * FROM dashboard_support_cases"
        params: tuple = ()
        if status in {"pending", "accepted", "declined", "closed"}:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END, updated_at DESC"
        async with db.execute(query, params) as cur:
            rows = [row async for row in cur]
        return {"cases": await _with_messages(db, rows)}


@router.post("/admin/requests", summary="Invite a guild owner to a support case")
async def create_request(data: dict, request: Request, bot: "universitybot" = Depends(get_bot)):
    actor, role, color, rank = _require_supporter(request)
    guild_id = str(data.get("guild_id", "")).strip()
    if not guild_id.isdigit() or not 17 <= len(guild_id) <= 20:
        raise HTTPException(400, "Enter a valid Discord server ID.")
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise HTTPException(404, "The bot is not on this server.")
    problem = str(data.get("problem", "")).strip()[:1000]
    now = int(time.time())
    icon = str(guild.icon.url) if getattr(guild, "icon", None) else ""

    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        async with db.execute(
            "SELECT id FROM dashboard_support_cases WHERE guild_id = ? AND status IN ('pending','accepted') LIMIT 1",
            (guild_id,),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            raise HTTPException(409, "This server already has an open support request.")
        cur = await db.execute(
            "INSERT INTO dashboard_support_cases"
            " (guild_id,guild_name,guild_icon,supporter_id,supporter_name,supporter_avatar,"
            " supporter_role,supporter_role_color,supporter_rank,problem,status,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
            (guild_id, str(guild.name)[:100], icon, actor["id"], actor["name"], actor["avatar"],
             role, color, rank, problem, now, now),
        )
        case_id = int(cur.lastrowid)
        if problem:
            await db.execute(
                "INSERT INTO dashboard_support_messages"
                " (case_id,actor_id,actor_name,actor_avatar,actor_role,actor_kind,message,created_at)"
                " VALUES (?,?,?,?,?,'supporter',?,?)",
                (case_id, actor["id"], actor["name"], actor["avatar"], role, problem, now),
            )
        await db.commit()
        case = await _case(db, case_id)
        case["messages"] = await _messages(db, case_id)
        return case


@router.get("/guild/{guild_id}", summary="List a guild owner's support cases")
async def guild_cases(guild_id: str):
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM dashboard_support_cases WHERE guild_id = ? ORDER BY updated_at DESC LIMIT 25",
            (guild_id,),
        ) as cur:
            rows = [row async for row in cur]
        cases = await _with_messages(db, rows)
        return {"cases": cases, "pending_count": sum(1 for c in cases if c["status"] == "pending")}


@router.post("/guild/{guild_id}/cases/{case_id}/respond", summary="Owner accepts or declines support")
async def respond(guild_id: str, case_id: int, data: dict, request: Request):
    actor = _identity(request)
    decision = str(data.get("decision", "")).lower()
    if decision not in {"accepted", "declined"}:
        raise HTTPException(400, "Decision must be accepted or declined.")
    now = int(time.time())
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        case = await _case(db, case_id)
        if not case or case["guild_id"] != guild_id:
            raise HTTPException(404, "Support case not found.")
        if case["status"] != "pending":
            raise HTTPException(409, "This request has already been answered.")
        await db.execute(
            "UPDATE dashboard_support_cases SET status=?, owner_id=?, updated_at=?, accepted_at=? WHERE id=?",
            (decision, actor["id"], now, now if decision == "accepted" else 0, case_id),
        )
        await db.commit()
        case = await _case(db, case_id)
        case["messages"] = await _messages(db, case_id)
        return case


async def _add_message(case_id: int, data: dict, request: Request, *, owner_guild: str = ""):
    actor = _identity(request)
    message = str(data.get("message", "")).strip()[:2000]
    if not message:
        raise HTTPException(400, "Message is required.")
    now = int(time.time())
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        case = await _case(db, case_id)
        if not case or case["status"] not in ACTIVE:
            raise HTTPException(409, "This support case is not open.")
        if owner_guild:
            if case["guild_id"] != owner_guild:
                raise HTTPException(404, "Support case not found.")
            kind, role = "owner", "Serverinhaber"
        else:
            _require_supporter(request)
            if case["supporter_id"] != actor["id"] and not dashboard_roles.is_owner(actor["id"]):
                raise HTTPException(403, "Only the assigned supporter may write to this case.")
            kind, role = "supporter", (_support_role(actor["id"])[0] or actor["role"])
        await db.execute(
            "INSERT INTO dashboard_support_messages"
            " (case_id,actor_id,actor_name,actor_avatar,actor_role,actor_kind,message,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (case_id, actor["id"], actor["name"], actor["avatar"], role, kind, message, now),
        )
        await db.execute("UPDATE dashboard_support_cases SET updated_at=? WHERE id=?", (now, case_id))
        await db.commit()
        return {"ok": True}


@router.post("/admin/cases/{case_id}/messages", summary="Supporter adds a case note")
async def admin_add_message(case_id: int, data: dict, request: Request):
    return await _add_message(case_id, data, request)


@router.post("/guild/{guild_id}/cases/{case_id}/messages", summary="Guild owner adds a case note")
async def owner_add_message(guild_id: str, case_id: int, data: dict, request: Request):
    return await _add_message(case_id, data, request, owner_guild=guild_id)


async def _close_case(case_id: int, request: Request, *, owner_guild: str = "", data: dict | None = None):
    actor = _identity(request)
    now = int(time.time())
    rating = int((data or {}).get("rating") or 0)
    rating_note = str((data or {}).get("rating_note") or "").strip()[:1000]
    if owner_guild and not 1 <= rating <= 10:
        raise HTTPException(400, "Please rate the support from 1 to 10 stars.")
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        case = await _case(db, case_id)
        if not case:
            raise HTTPException(404, "Support case not found.")
        if case["status"] != "accepted":
            raise HTTPException(409, "Only an accepted case can be closed.")
        if owner_guild:
            if case["guild_id"] != owner_guild:
                raise HTTPException(404, "Support case not found.")
        else:
            _require_supporter(request)
            if case["supporter_id"] != actor["id"] and not dashboard_roles.is_owner(actor["id"]):
                raise HTTPException(403, "Only the assigned supporter may close this case.")
        await db.execute(
            "UPDATE dashboard_support_cases SET status='closed',updated_at=?,closed_at=?,rating=?,rating_note=? WHERE id=?",
            (now, now, rating, rating_note, case_id),
        )
        await db.commit()
        return {"ok": True, "access_revoked": True}


@router.post("/admin/cases/{case_id}/close", summary="Supporter closes a case")
async def admin_close_case(case_id: int, request: Request):
    return await _close_case(case_id, request)


@router.delete("/admin/cases/{case_id}", summary="Delete a support request")
async def admin_delete_case(case_id: int, request: Request):
    _require_supporter(request)
    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        case = await _case(db, case_id)
        if not case:
            raise HTTPException(404, "Support case not found.")
        await db.execute("DELETE FROM dashboard_support_messages WHERE case_id=?", (case_id,))
        await db.execute("DELETE FROM dashboard_support_cases WHERE id=?", (case_id,))
        await db.commit()
        return {"ok": True, "access_revoked": case["status"] == "accepted"}


@router.post("/admin/cases/{case_id}/scan", summary="Read-only support diagnostics")
async def admin_support_scan(case_id: int, data: dict, request: Request, bot: "universitybot" = Depends(get_bot)):
    actor, _, _, _ = _require_supporter(request)
    scan_type = str(data.get("scan_type") or "full").lower()
    if scan_type not in {"dashboard", "discord", "full"}:
        raise HTTPException(400, "Unknown scan type.")

    async with db_paths.connect(DB_PATH) as db:
        await _ensure(db)
        case = await _case(db, case_id)
        if not case:
            raise HTTPException(404, "Support case not found.")
        if case["status"] != "accepted":
            raise HTTPException(409, "The server owner must accept support before a scan.")
        if case["supporter_id"] != actor["id"] and not dashboard_roles.is_owner(actor["id"]):
            raise HTTPException(403, "Only the assigned supporter may scan this server.")

        result: dict = {"case_id": case_id, "guild_id": case["guild_id"], "scan_type": scan_type, "scanned_at": int(time.time())}
        if scan_type in {"dashboard", "full"}:
            async with db.execute("PRAGMA quick_check") as cur:
                quick = await cur.fetchone()
            async with db.execute("SELECT COUNT(*) FROM dashboard_support_cases WHERE guild_id=?", (case["guild_id"],)) as cur:
                history = int((await cur.fetchone())[0])
            guild = bot.get_guild(int(case["guild_id"]))
            me = getattr(guild, "me", None) if guild else None
            permissions = getattr(me, "guild_permissions", None)
            checks = [
                {"key": "support_consent", "label": "Support-Freigabe", "ok": True, "detail": "Vom Serverinhaber angenommen."},
                {"key": "database", "label": "Support-Datenbank", "ok": bool(quick and str(quick[0]).lower() == "ok"), "detail": str(quick[0]) if quick else "Keine Antwort"},
                {"key": "guild_cache", "label": "Server im Bot-Cache", "ok": guild is not None, "detail": "Server erreichbar" if guild else "Server derzeit nicht im Bot-Cache"},
                {"key": "bot_member", "label": "Bot-Mitglied geladen", "ok": me is not None, "detail": "Bot-Mitglied gefunden" if me else "Bot-Mitglied fehlt"},
                {"key": "dashboard_history", "label": "Support-Verlauf", "ok": history > 0, "detail": f"{history} gespeicherte Supportfälle"},
            ]
            if permissions is not None:
                for key, label in (("view_channel", "Kanäle sehen"), ("send_messages", "Nachrichten senden"), ("manage_roles", "Rollen verwalten"), ("manage_guild", "Server verwalten")):
                    ok = bool(getattr(permissions, key, False) or getattr(permissions, "administrator", False))
                    checks.append({"key": f"permission_{key}", "label": label, "ok": ok, "detail": "Vorhanden" if ok else "Bot-Recht fehlt"})
            result["dashboard"] = {"ok": all(item["ok"] for item in checks), "checks": checks}

        if scan_type in {"discord", "full"}:
            result["discord"] = await servertools.security_scan(int(case["guild_id"]), bot)
        return result


@router.post("/guild/{guild_id}/cases/{case_id}/close", summary="Guild owner closes and rates a case")
async def owner_close_case(guild_id: str, case_id: int, data: dict, request: Request):
    return await _close_case(case_id, request, owner_guild=guild_id, data=data)
