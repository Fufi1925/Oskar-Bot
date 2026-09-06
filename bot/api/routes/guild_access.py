"""Per-server dashboard access through Discord roles or individual members.

Server managers may delegate access to the dashboard without granting the
Discord permission "Manage Server". A grant never creates global access: it is
valid only for this guild and only while the person is still a member.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_bot
from utils import db_open, feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()
DB_PATH = "db/guild_dashboard_access.db"


class GrantRole(BaseModel):
    role_id: str
    actor: str = "dashboard"


class GrantUser(BaseModel):
    user_id: str
    actor: str = "dashboard"


async def _db() -> aiosqlite.Connection:
    db = await db_open.connect(DB_PATH)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_access_roles ("
        "guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, "
        "added_by TEXT DEFAULT '', added_at INTEGER DEFAULT 0, "
        "PRIMARY KEY (guild_id, role_id))"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_access_users ("
        "guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "added_by TEXT DEFAULT '', added_at INTEGER DEFAULT 0, "
        "PRIMARY KEY (guild_id, user_id))"
    )
    await db.commit()
    return db


def _guild(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Server nicht gefunden.")
    return guild


async def _member(guild, user_id: int):
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            member = None
    return member


async def _grants(guild_id: int) -> tuple[list[aiosqlite.Row], list[aiosqlite.Row]]:
    db = await _db()
    db.row_factory = aiosqlite.Row
    try:
        roles = await (await db.execute(
            "SELECT * FROM dashboard_access_roles WHERE guild_id = ? ORDER BY added_at",
            (guild_id,),
        )).fetchall()
        users = await (await db.execute(
            "SELECT * FROM dashboard_access_users WHERE guild_id = ? ORDER BY added_at",
            (guild_id,),
        )).fetchall()
        return roles, users
    finally:
        await db.close()


@router.get("/{guild_id}", summary="List delegated dashboard access")
async def list_access(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild(bot, guild_id)
    role_rows, user_rows = await _grants(guild_id)

    role_entries = []
    for row in role_rows:
        role = guild.get_role(int(row["role_id"]))
        role_entries.append({
            "role_id": str(row["role_id"]),
            "name": role.name if role else "Gelöschte Rolle",
            "color": role.color.value if role else 0,
            "member_count": len(role.members) if role else 0,
            "missing": role is None,
            "added_by": row["added_by"],
            "added_at": row["added_at"],
        })

    user_entries = []
    for row in user_rows:
        member = guild.get_member(int(row["user_id"]))
        user = member or bot.get_user(int(row["user_id"]))
        user_entries.append({
            "user_id": str(row["user_id"]),
            "username": str(user) if user else "Unbekannter Nutzer",
            "display_name": getattr(user, "display_name", None),
            "avatar": str(user.display_avatar.url) if user else None,
            "member": member is not None,
            "added_by": row["added_by"],
            "added_at": row["added_at"],
        })

    return {"roles": role_entries, "users": user_entries}


@router.post("/{guild_id}/roles", summary="Grant dashboard access to a role")
async def add_role(guild_id: int, data: GrantRole, bot: "universitybot" = Depends(get_bot)):
    guild = _guild(bot, guild_id)
    if not data.role_id.isdigit():
        raise HTTPException(status_code=400, detail="Ungültige Rollen-ID.")
    role = guild.get_role(int(data.role_id))
    if role is None:
        raise HTTPException(status_code=404, detail="Rolle nicht gefunden.")
    if role.is_default():
        raise HTTPException(status_code=400, detail="@everyone darf keinen Dashboard-Zugang erhalten.")
    if role.managed:
        raise HTTPException(status_code=400, detail="Verwaltete Bot- und Integrationsrollen sind nicht erlaubt.")

    db = await _db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO dashboard_access_roles "
            "(guild_id, role_id, added_by, added_at) VALUES (?, ?, ?, ?)",
            (guild_id, role.id, data.actor, int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()
    await feature_audit.log_action(
        "dashboard_access_role_added", actor=data.actor,
        guild_id=guild_id, detail=f"role {role.id} ({role.name})",
    )
    return {"status": "success", "role_id": str(role.id), "name": role.name}


@router.delete("/{guild_id}/roles/{role_id}", summary="Revoke role dashboard access")
async def remove_role(guild_id: int, role_id: int, actor: str = "dashboard"):
    db = await _db()
    try:
        cursor = await db.execute(
            "DELETE FROM dashboard_access_roles WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Diese Rolle hat keinen Dashboard-Zugang.")
    finally:
        await db.close()
    await feature_audit.log_action(
        "dashboard_access_role_removed", actor=actor,
        guild_id=guild_id, detail=f"role {role_id}",
    )
    return {"status": "success"}


@router.post("/{guild_id}/users", summary="Grant dashboard access to one member")
async def add_user(guild_id: int, data: GrantUser, bot: "universitybot" = Depends(get_bot)):
    guild = _guild(bot, guild_id)
    if not data.user_id.isdigit():
        raise HTTPException(status_code=400, detail="Ungültige Nutzer-ID.")
    member = await _member(guild, int(data.user_id))
    if member is None:
        raise HTTPException(status_code=404, detail="Der Nutzer ist kein Mitglied dieses Servers.")
    if member.bot:
        raise HTTPException(status_code=400, detail="Bots können das Dashboard nicht verwenden.")

    db = await _db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO dashboard_access_users "
            "(guild_id, user_id, added_by, added_at) VALUES (?, ?, ?, ?)",
            (guild_id, member.id, data.actor, int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()
    await feature_audit.log_action(
        "dashboard_access_user_added", actor=data.actor,
        guild_id=guild_id, detail=f"user {member.id} ({member})",
    )
    return {"status": "success", "user_id": str(member.id)}


@router.delete("/{guild_id}/users/{user_id}", summary="Revoke member dashboard access")
async def remove_user(guild_id: int, user_id: int, actor: str = "dashboard"):
    db = await _db()
    try:
        cursor = await db.execute(
            "DELETE FROM dashboard_access_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Dieser Nutzer hat keinen direkten Zugang.")
    finally:
        await db.close()
    await feature_audit.log_action(
        "dashboard_access_user_removed", actor=actor,
        guild_id=guild_id, detail=f"user {user_id}",
    )
    return {"status": "success"}


@router.get("/{guild_id}/check/{user_id}", summary="Check a delegated grant")
async def check_access(guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild(bot, guild_id)
    member = await _member(guild, user_id)
    if member is None or member.bot:
        return {"allowed": False, "source": None}

    db = await _db()
    try:
        direct = await (await db.execute(
            "SELECT 1 FROM dashboard_access_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )).fetchone()
        if direct:
            return {"allowed": True, "source": "user"}
        role_ids = {role.id for role in member.roles}
        placeholders = ",".join("?" for _ in role_ids)
        if role_ids:
            row = await (await db.execute(
                f"SELECT role_id FROM dashboard_access_roles WHERE guild_id = ? "
                f"AND role_id IN ({placeholders}) LIMIT 1",
                (guild_id, *role_ids),
            )).fetchone()
            if row:
                return {"allowed": True, "source": "role", "role_id": str(row[0])}
        return {"allowed": False, "source": None}
    finally:
        await db.close()


@router.get("/user/{user_id}/guilds", summary="Guilds reachable through delegated grants")
async def user_guilds(user_id: int, bot: "universitybot" = Depends(get_bot)):
    # One database snapshot for the whole fleet. Opening a connection for every
    # guild made the server picker needlessly slow on larger installations.
    db = await _db()
    try:
        direct_guilds = {
            int(row[0]) for row in await (await db.execute(
                "SELECT guild_id FROM dashboard_access_users WHERE user_id = ?",
                (user_id,),
            )).fetchall()
        }
        role_rows = await (await db.execute(
            "SELECT guild_id, role_id FROM dashboard_access_roles"
        )).fetchall()
    finally:
        await db.close()
    allowed_roles: dict[int, set[int]] = {}
    for guild_id, role_id in role_rows:
        allowed_roles.setdefault(int(guild_id), set()).add(int(role_id))

    entries = []
    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if member is None or member.bot:
            continue
        direct = guild.id in direct_guilds
        role_match = bool(
            {role.id for role in member.roles} & allowed_roles.get(guild.id, set())
        )
        if direct or role_match:
            entries.append({
                "id": str(guild.id), "name": guild.name,
                "icon": str(guild.icon.key) if guild.icon else None,
                "owner": guild.owner_id == user_id,
                "member_count": guild.member_count,
                "source": "user" if direct else "role",
            })
    return {"guilds": entries}
