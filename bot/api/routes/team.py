"""
Dashboard team management.

Endpoints for handing out the 40 dashboard roles to people, so the bot owner
does not have to share the owner account.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import TYPE_CHECKING

from api.dependencies import get_bot
from utils import dashboard_roles as roles
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


# ── Catalogue ─────────────────────────────────────────────────────────────


@router.get("/roles", summary="List all dashboard roles")
async def list_roles():
    await roles.load()
    return {
        "categories": list(roles.ROLE_CATEGORIES),
        "roles": roles.describe_roles(),
        "total": len(roles.ROLES),
    }


@router.get("/permissions", summary="List all dashboard permissions")
async def list_permissions():
    return {
        "groups": list(roles.PERMISSION_GROUPS),
        "permissions": roles.describe_permissions(),
        "total": len(roles.PERMISSIONS),
    }


@router.get("/roles/{role_key}", summary="Details of a single role")
async def get_role(role_key: str):
    role = roles.ROLES_BY_KEY.get(role_key)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown role.")

    await roles.load()
    return {
        "key": role.key,
        "label": role.label,
        "category": role.category,
        "description": role.description,
        "rank": role.rank,
        "color": role.color,
        "permissions": [
            {
                "key": key,
                "label": roles.PERMISSIONS_BY_KEY[key].label,
                "group": roles.PERMISSIONS_BY_KEY[key].group,
                "description": roles.PERMISSIONS_BY_KEY[key].description,
                "dangerous": roles.PERMISSIONS_BY_KEY[key].dangerous,
            }
            for key in role.permissions
        ],
        "holders": [
            member["user_id"]
            for member in roles.all_members()
            if any(r["key"] == role_key for r in member["roles"])
        ],
    }


# ── Team ──────────────────────────────────────────────────────────────────


@router.get("/members", summary="Everyone holding a dashboard role")
async def list_members(bot: "universitybot" = Depends(get_bot)):
    await roles.load()
    members = roles.all_members()

    # Enrich with Discord names so the dashboard shows more than raw IDs.
    for member in members:
        user = bot.get_user(int(member["user_id"])) if member["user_id"].isdigit() else None
        member["username"] = str(user) if user else None
        member["avatar"] = str(user.display_avatar.url) if user else None

    return {"members": members, "count": len(members)}


@router.get("/members/{user_id}", summary="Roles and permissions of one user")
async def get_member(user_id: str, bot: "universitybot" = Depends(get_bot)):
    await roles.load()

    user = bot.get_user(int(user_id)) if user_id.isdigit() else None
    permissions = sorted(roles.get_permissions(user_id))

    return {
        "user_id": user_id,
        "username": str(user) if user else None,
        "avatar": str(user.display_avatar.url) if user else None,
        "is_owner": roles.is_owner(user_id),
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
        "accessible_guilds": (
            None if roles.accessible_guilds(user_id) is None
            else sorted(roles.accessible_guilds(user_id))
        ),
    }


@router.post("/members/{user_id}/roles", summary="Give a role to a user")
async def assign_role(user_id: str, data: dict):
    if not user_id.isdigit() or not 15 <= len(user_id) <= 20:
        raise HTTPException(status_code=400, detail="user_id must be a valid Discord ID.")

    role_key = str(data.get("role", "")).strip()
    if role_key not in roles.ROLES_BY_KEY:
        raise HTTPException(status_code=404, detail=f"Unknown role: {role_key}")

    actor = str(data.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")

    await roles.load()

    # Nobody may hand out a role at or above their own rank — that would let a
    # manager promote themselves. Owners are exempt.
    target_role = roles.ROLES_BY_KEY[role_key]
    if not roles.is_owner(actor):
        if not roles.has_permission(actor, "team.assign"):
            raise HTTPException(status_code=403, detail="You may not assign dashboard roles.")
        if target_role.rank >= roles.highest_rank(actor):
            raise HTTPException(
                status_code=403,
                detail=f"'{target_role.label}' is at or above your own rank.",
            )

    if roles.is_owner(user_id):
        raise HTTPException(
            status_code=400,
            detail="This user is a bot owner and already has every permission.",
        )

    guild_ids = data.get("guild_ids") or []
    if not isinstance(guild_ids, list):
        raise HTTPException(status_code=400, detail="guild_ids must be a list.")

    assignment = await roles.assign(
        user_id,
        role_key,
        granted_by=actor,
        guild_ids=[str(g) for g in guild_ids],
        note=str(data.get("note", "")),
    )

    await feature_audit.log_action(
        "dashboard_role_assigned",
        actor=actor,
        detail=f"{role_key} -> {user_id}"
        + (f" (guilds: {','.join(assignment.guild_ids)})" if assignment.guild_ids else " (all guilds)"),
    )

    return {
        "status": "success",
        "user_id": user_id,
        "role": role_key,
        "label": target_role.label,
        "guild_ids": list(assignment.guild_ids),
    }


@router.delete("/members/{user_id}/roles/{role_key}", summary="Take a role away")
async def revoke_role(user_id: str, role_key: str, actor: str = ""):
    await roles.load()

    if not actor:
        raise HTTPException(status_code=400, detail="actor query parameter is required.")

    target_role = roles.ROLES_BY_KEY.get(role_key)
    if target_role is None:
        raise HTTPException(status_code=404, detail="Unknown role.")

    if not roles.is_owner(actor):
        if not roles.has_permission(actor, "team.assign"):
            raise HTTPException(status_code=403, detail="You may not manage dashboard roles.")
        if target_role.rank >= roles.highest_rank(actor):
            raise HTTPException(
                status_code=403,
                detail=f"'{target_role.label}' is at or above your own rank.",
            )

    removed = await roles.revoke(user_id, role_key)
    if not removed:
        raise HTTPException(status_code=404, detail="This user does not hold that role.")

    await feature_audit.log_action(
        "dashboard_role_revoked", actor=actor, detail=f"{role_key} removed from {user_id}"
    )
    return {"status": "success", "user_id": user_id, "role": role_key}


@router.delete("/members/{user_id}", summary="Remove all roles from a user")
async def revoke_all_roles(user_id: str, actor: str = ""):
    await roles.load()

    if not actor:
        raise HTTPException(status_code=400, detail="actor query parameter is required.")

    if not roles.is_owner(actor):
        if not roles.has_permission(actor, "team.assign"):
            raise HTTPException(status_code=403, detail="You may not manage dashboard roles.")
        if roles.highest_rank(user_id) >= roles.highest_rank(actor):
            raise HTTPException(
                status_code=403, detail="This user outranks you."
            )

    count = await roles.revoke_all(user_id)
    await feature_audit.log_action(
        "dashboard_roles_cleared", actor=actor, detail=f"{count} roles removed from {user_id}"
    )
    return {"status": "success", "user_id": user_id, "removed": count}


# ── Self ──────────────────────────────────────────────────────────────────


@router.get("/me/{user_id}", summary="Own roles and permissions")
async def get_own_access(user_id: str):
    """
    Used by the dashboard to decide which pages and buttons to show.
    Deliberately cheap: no Discord lookups.
    """
    await roles.load()
    permissions = sorted(roles.get_permissions(user_id))
    accessible = roles.accessible_guilds(user_id)

    return {
        "user_id": user_id,
        "is_owner": roles.is_owner(user_id),
        "roles": [
            {"key": r.key, "label": r.label, "color": r.color, "rank": r.rank}
            for r in roles.get_roles(user_id)
        ],
        "permissions": permissions,
        "highest_rank": roles.highest_rank(user_id),
        "accessible_guilds": None if accessible is None else sorted(accessible),
    }
