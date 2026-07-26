"""
Dashboard user management.

Answers the question "who can get into my dashboard, and how?" — and lets the
owner throw somebody out.

A person can reach the dashboard through three different doors:

    owner      listed in OWNER_IDS / ADMIN_IDS or in the dashboard_owners table
    team role  holds one of the 40 dashboard roles
    Discord    has Manage Server / Administrator on a guild the bot is in

The third door is the reason a plain "remove all roles" button is not enough:
that access comes from Discord, not from us. `dashboard_bans` is an explicit
deny-list that overrides all three.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import dashboard_access as access
from utils import dashboard_roles as roles
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8


def _decorate_user(bot, user_id: str) -> dict:
    """Name and avatar for a Discord ID, as far as the bot knows them."""
    user = None
    if str(user_id).isdigit():
        user = bot.get_user(int(user_id))
    return {
        "username": str(user) if user else None,
        "display_name": getattr(user, "display_name", None) if user else None,
        "avatar": str(user.display_avatar.url) if user else None,
    }


def _guild_admin_map(bot) -> dict[str, list[dict]]:
    """
    user_id -> guilds where that user has Manage Server or Administrator.

    Built from the member cache, so it only covers guilds the bot can see. That
    is exactly the set of guilds the dashboard can manage anyway.
    """
    result: dict[str, list[dict]] = {}
    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue
            perms = member.guild_permissions
            is_owner_of_guild = member.id == guild.owner_id
            if not (is_owner_of_guild or perms.administrator or perms.manage_guild):
                continue
            result.setdefault(str(member.id), []).append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "is_guild_owner": is_owner_of_guild,
                    "administrator": bool(perms.administrator),
                    "manage_guild": bool(perms.manage_guild),
                }
            )
    return result


# ── Overview ──────────────────────────────────────────────────────────────


@router.get("/users", summary="Everyone who can reach the dashboard")
async def list_users(
    include_discord: bool = True,
    bot: "universitybot" = Depends(get_bot),
):
    """
    One row per person, merged from all four sources: owners, team roles,
    recorded logins and (optionally) Discord server admins.
    """
    await roles.load()
    await access.load()

    users: dict[str, dict] = {}

    def entry(user_id: str) -> dict:
        uid = str(user_id)
        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "sources": [],
                "is_owner": False,
                "owner_kind": None,
                "roles": [],
                "highest_rank": 0,
                "permission_count": 0,
                "guild_admin_of": [],
                "first_seen": 0,
                "last_seen": 0,
                "login_count": 0,
                "banned": False,
                "ban": None,
                "username": None,
                "display_name": None,
                "avatar": None,
            }
        return users[uid]

    # 1. Owners and dashboard admins
    for record in roles.list_owners():
        row = entry(record["user_id"])
        row["sources"].append("owner")
        row["is_owner"] = True
        row["owner_kind"] = record.get("kind", "admin")
        row["owner_note"] = record.get("note", "")
        row["owner_source"] = record.get("source", "")

    # 2. Dashboard team roles
    for member in roles.all_members():
        row = entry(member["user_id"])
        row["sources"].append("team_role")
        row["roles"] = member.get("roles", [])
        row["highest_rank"] = member.get("highest_rank", 0)
        row["permission_count"] = member.get("permission_count", 0)

    # 3. People who actually signed in
    for login in await access.list_logins(2000):
        row = entry(login["user_id"])
        row["sources"].append("login")
        row["first_seen"] = login["first_seen"]
        row["last_seen"] = login["last_seen"]
        row["login_count"] = login["login_count"]
        row["last_path"] = login["last_path"]
        if login.get("username"):
            row["username"] = login["username"]
        if login.get("avatar"):
            row["avatar"] = login["avatar"]

    # 4. Discord server admins — potential access even without a role here
    if include_discord:
        for user_id, guilds in _guild_admin_map(bot).items():
            row = entry(user_id)
            row["sources"].append("discord_admin")
            row["guild_admin_of"] = guilds

    # 5. Bans and Discord identities
    for uid, row in users.items():
        ban = access.get_ban(uid)
        row["banned"] = ban is not None
        row["ban"] = ban
        row["sources"] = sorted(set(row["sources"]))

        info = _decorate_user(bot, uid)
        for key, value in info.items():
            if value and not row.get(key):
                row[key] = value

    ordered = sorted(
        users.values(),
        key=lambda u: (
            not u["banned"],          # banned first, they need attention
            -u["highest_rank"],
            -(u["last_seen"] or 0),
        ),
    )

    return {
        "users": ordered,
        "count": len(ordered),
        "banned_count": sum(1 for u in ordered if u["banned"]),
        "owner_count": sum(1 for u in ordered if u["is_owner"]),
        "role_count": sum(1 for u in ordered if u["roles"]),
        "discord_admin_count": sum(1 for u in ordered if u["guild_admin_of"]),
    }


@router.get("/users/{user_id}", summary="Everything about one dashboard user")
async def get_user(user_id: str, bot: "universitybot" = Depends(get_bot)):
    await roles.load()
    await access.load()

    permissions = sorted(roles.get_permissions(user_id))
    login = await access.get_login(user_id)
    ban = access.get_ban(user_id)

    guild_admin_of = _guild_admin_map(bot).get(str(user_id), [])

    # Which guilds this person can actually open in the dashboard.
    #
    # Two doors lead in and both have to be counted: a dashboard role, and
    # Manage Server on Discord. Looking at roles alone reported "reaches
    # nothing" for a server admin who very much reaches their own server.
    scoped = roles.accessible_guilds(user_id)
    reachable: list[dict] = []

    if scoped is None:
        # Owner, or a role with no guild restriction: everywhere.
        reachable = [
            {"guild_id": str(g.id), "guild_name": g.name, "via": "dashboard role"}
            for g in bot.guilds
        ]
        reachable_reason = "unrestricted"
    else:
        seen: set[str] = set()
        for gid in sorted(scoped):
            guild = bot.get_guild(int(gid)) if gid.isdigit() else None
            reachable.append(
                {
                    "guild_id": gid,
                    "guild_name": guild.name if guild else "Unknown",
                    "via": "dashboard role",
                }
            )
            seen.add(gid)

        for entry in guild_admin_of:
            if entry["guild_id"] in seen:
                continue
            reachable.append(
                {
                    "guild_id": entry["guild_id"],
                    "guild_name": entry["guild_name"],
                    "via": "guild owner" if entry["is_guild_owner"] else "Discord admin",
                }
            )
            seen.add(entry["guild_id"])

        if scoped and guild_admin_of:
            reachable_reason = "role scope + Discord permissions"
        elif scoped:
            reachable_reason = "role scope"
        elif guild_admin_of:
            reachable_reason = "Discord permissions"
        else:
            reachable_reason = "no access"

    return {
        "user_id": str(user_id),
        **_decorate_user(bot, user_id),
        "is_owner": roles.is_owner(user_id),
        "can_manage_owners": roles.can_manage_owners(user_id),
        "highest_rank": roles.highest_rank(user_id),
        "roles": [
            {
                "key": a.role_key,
                "label": roles.ROLES_BY_KEY[a.role_key].label,
                "color": roles.ROLES_BY_KEY[a.role_key].color,
                "rank": roles.ROLES_BY_KEY[a.role_key].rank,
                "guild_ids": list(a.guild_ids),
                "granted_by": a.granted_by,
                "granted_at": a.granted_at,
                "note": a.note,
            }
            for a in roles.get_assignments(user_id)
            if a.role_key in roles.ROLES_BY_KEY
        ],
        "permissions": permissions,
        "permission_count": len(permissions),
        "login": login,
        "banned": ban is not None,
        "ban": ban,
        "guild_admin_of": guild_admin_of,
        "reachable_guilds": reachable,
        "reachable_reason": reachable_reason,
    }


# ── Bans ──────────────────────────────────────────────────────────────────


@router.get("/bans", summary="Everyone banned from the dashboard")
async def list_bans(include_expired: bool = False, bot: "universitybot" = Depends(get_bot)):
    await access.load()
    entries = access.list_bans(include_expired=include_expired)
    for entry in entries:
        entry.update(_decorate_user(bot, entry["user_id"]))
        by = entry.get("banned_by")
        entry["banned_by_name"] = _decorate_user(bot, by)["username"] if by else None
    return {"bans": entries, "count": len(entries)}


@router.post("/bans", summary="Ban a user from the dashboard")
async def create_ban(data: dict):
    actor = str(data.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")

    await roles.load()
    await access.load()

    user_id = str(data.get("user_id", "")).strip()
    if not user_id.isdigit() or not 15 <= len(user_id) <= 20:
        raise HTTPException(status_code=400, detail="user_id must be a valid Discord ID.")

    if user_id == actor:
        raise HTTPException(status_code=400, detail="You cannot ban yourself.")

    # An owner must never be lockable out of their own dashboard.
    if roles.is_owner(user_id):
        raise HTTPException(
            status_code=403,
            detail="This user is an owner or dashboard admin. Remove that access first.",
        )

    # Only owners, or holders of team.assign who outrank the target.
    if not roles.is_owner(actor):
        if not roles.has_permission(actor, "team.assign"):
            raise HTTPException(status_code=403, detail="You may not ban dashboard users.")
        if roles.highest_rank(user_id) >= roles.highest_rank(actor):
            raise HTTPException(status_code=403, detail="This user is at or above your own rank.")

    try:
        duration = int(data.get("duration_seconds", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    duration = max(0, min(duration, 60 * 60 * 24 * 3650))  # cap at 10 years

    reason = str(data.get("reason", "")).strip()

    # Optionally strip their roles too, so the ban survives being lifted later
    # without silently handing back old privileges.
    removed_roles = 0
    if bool(data.get("revoke_roles", False)):
        removed_roles = await roles.revoke_all(user_id)

    try:
        record = await access.ban(
            user_id, banned_by=actor, reason=reason, duration_seconds=duration
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await feature_audit.log_action(
        "dashboard_user_banned",
        actor=actor,
        detail=f"{user_id}"
        + (f" for {duration}s" if duration else " permanently")
        + (f": {reason}" if reason else "")
        + (f" (+{removed_roles} roles revoked)" if removed_roles else ""),
    )

    return {"status": "success", "ban": record, "revoked_roles": removed_roles}


@router.delete("/bans/{user_id}", summary="Lift a dashboard ban")
async def delete_ban(user_id: str, actor: str = ""):
    if not actor:
        raise HTTPException(status_code=400, detail="actor query parameter is required.")

    await roles.load()
    await access.load()

    if not roles.is_owner(actor) and not roles.has_permission(actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage dashboard bans.")

    removed = await access.unban(user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="This user is not banned.")

    await feature_audit.log_action(
        "dashboard_user_unbanned", actor=actor, detail=f"{user_id}"
    )
    return {"status": "success", "user_id": str(user_id)}


@router.post("/bans/purge", summary="Delete expired ban entries")
async def purge_bans(data: dict):
    actor = str(data.get("actor", "")).strip()
    await roles.load()
    if not roles.is_owner(actor) and not roles.has_permission(actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage dashboard bans.")

    removed = await access.purge_expired()
    return {"status": "success", "removed": removed}


# ── Logins ────────────────────────────────────────────────────────────────


@router.get("/logins", summary="Dashboard sign-in history")
async def list_logins(limit: int = 200, bot: "universitybot" = Depends(get_bot)):
    entries = await access.list_logins(limit)
    await access.load()
    for entry in entries:
        info = _decorate_user(bot, entry["user_id"])
        for key, value in info.items():
            if value and not entry.get(key):
                entry[key] = value
        entry["banned"] = access.is_banned(entry["user_id"])
    return {"logins": entries, "count": len(entries)}


@router.post("/logins", summary="Record a dashboard sign-in")
async def create_login(data: dict):
    """
    Called by the dashboard's NextAuth callback. Also reports back whether the
    user is banned, so the sign-in can be refused right there.
    """
    user_id = str(data.get("user_id", "")).strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="user_id must be a Discord ID.")

    await access.load()
    banned = access.is_banned(user_id)

    if not banned:
        await access.record_login(
            user_id,
            username=str(data.get("username", ""))[:100],
            avatar=str(data.get("avatar", ""))[:300],
            new_session=bool(data.get("new_session", True)),
            path=str(data.get("path", ""))[:200],
        )

    return {"status": "success", "banned": banned, "ban": access.get_ban(user_id)}


@router.delete("/logins/{user_id}", summary="Forget a sign-in record")
async def delete_login(user_id: str, actor: str = ""):
    await roles.load()
    if not roles.is_owner(actor) and not roles.has_permission(actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage login records.")

    removed = await access.forget_login(user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No record for this user.")
    return {"status": "success", "user_id": str(user_id)}


@router.get("/check/{user_id}", summary="Is this user banned?")
async def check_user(user_id: str):
    """Cheap endpoint used by the dashboard middleware on every request."""
    await access.load()
    ban = access.get_ban(user_id)
    return {
        "user_id": str(user_id),
        "banned": ban is not None,
        "reason": (ban or {}).get("reason", ""),
        "expires_at": (ban or {}).get("expires_at", 0),
        "checked_at": int(time.time()),
    }
