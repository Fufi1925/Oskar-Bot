"""
Moderation history for the dashboard.

Reading and writing both go through ``utils/warn_store.py``. That module
is also what ``cogs/moderation/warn.py`` uses, which is the point: these
endpoints and the ``>warn`` command used to keep their own SQL, so a
warning issued in Discord arrived here without a reason and a
``>clearwarns`` in Discord left the entries visible in the dashboard.
"""

from typing import TYPE_CHECKING

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit, warn_store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

WARN_DB = "db/warn.db"


async def _ensure(db: aiosqlite.Connection) -> None:
    """Das Schema kommt aus warn_store, damit es nur eine Fassung gibt."""
    await warn_store.ensure_schema(db)


@router.get("/{guild_id}/warnings", summary="All warnings in a guild")
async def list_warnings(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    async with aiosqlite.connect(WARN_DB) as db:
        await _ensure(db)
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT user_id, warns FROM warns WHERE guild_id = ? AND warns > 0"
            " ORDER BY warns DESC",
            (guild_id,),
        ) as cursor:
            counters = [dict(row) for row in await cursor.fetchall()]

        async with db.execute(
            "SELECT * FROM warn_log WHERE guild_id = ? AND active = 1"
            " ORDER BY created_at DESC LIMIT 300",
            (guild_id,),
        ) as cursor:
            entries = [dict(row) for row in await cursor.fetchall()]

    guild = bot.get_guild(guild_id)

    def name_of(user_id: int) -> str | None:
        member = guild.get_member(user_id) if guild else None
        if member:
            return member.display_name
        user = bot.get_user(user_id)
        return str(user) if user else None

    # Merge the counter with the detailed entries so the UI can show both.
    by_user: dict[int, dict] = {}
    for row in counters:
        uid = int(row["user_id"])
        by_user[uid] = {
            "user_id": str(uid),
            "username": name_of(uid),
            "count": int(row["warns"] or 0),
            "entries": [],
        }

    for entry in entries:
        uid = int(entry["user_id"])
        target = by_user.setdefault(
            uid,
            {"user_id": str(uid), "username": name_of(uid), "count": 0, "entries": []},
        )
        target["entries"].append(
            {
                "id": entry["id"],
                "moderator_id": str(entry["moderator_id"] or ""),
                "moderator": name_of(int(entry["moderator_id"])) if entry["moderator_id"] else None,
                "reason": entry["reason"] or "",
                "created_at": entry["created_at"],
            }
        )

    users = sorted(by_user.values(), key=lambda u: u["count"], reverse=True)
    return {"guild_id": str(guild_id), "users": users, "total": sum(u["count"] for u in users)}


@router.post("/{guild_id}/warnings", summary="Add a warning")
async def add_warning(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    user_id = str(data.get("user_id", "")).strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="user_id must be a valid Discord ID.")

    reason = str(data.get("reason", "")).strip()[:500]
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")

    actor = str(data.get("actor", "")).strip()

    # Dieselbe Funktion, die auch >warn im Discord aufruft.
    neuer_stand = await warn_store.add(
        guild_id,
        int(user_id),
        reason=reason,
        moderator_id=int(actor) if actor.isdigit() else None,
    )

    await feature_audit.log_action(
        "warning_added", actor=actor, guild_id=guild_id, detail=f"{user_id}: {reason}"
    )

    # Best effort: let the member know why they were warned.
    guild = bot.get_guild(guild_id)
    member = guild.get_member(int(user_id)) if guild else None
    if member:
        try:
            await member.send(f"You were warned in **{guild.name}**: {reason}")
        except Exception:
            pass

    return {"status": "success", "user_id": user_id, "count": neuer_stand}


@router.delete("/{guild_id}/warnings/{entry_id}", summary="Remove a single warning")
async def remove_warning(guild_id: int, entry_id: int, actor: str = ""):
    ergebnis = await warn_store.remove_one(guild_id, entry_id)
    if ergebnis is None:
        raise HTTPException(status_code=404, detail="Warning not found.")
    user_id, remaining = ergebnis

    await feature_audit.log_action(
        "warning_removed", actor=actor, guild_id=guild_id, detail=f"entry #{entry_id}"
    )
    return {"status": "success", "user_id": str(user_id), "count": remaining}


@router.delete("/{guild_id}/warnings/user/{user_id}", summary="Clear all warnings of a user")
async def clear_warnings(guild_id: int, user_id: int, actor: str = ""):
    # Dieselbe Funktion, die auch >clearwarns im Discord aufruft.
    await warn_store.clear(guild_id, user_id)

    await feature_audit.log_action(
        "warnings_cleared", actor=actor, guild_id=guild_id, detail=f"user {user_id}"
    )
    return {"status": "success", "user_id": str(user_id)}


# ── Member lookup ─────────────────────────────────────────────────────────


@router.get("/{guild_id}/members/search", summary="Search members by name or ID")
async def search_members(guild_id: int, q: str = "", limit: int = 25, bot: "universitybot" = Depends(get_bot)):
    """
    Powers the user picker in the dashboard so nobody has to copy raw IDs.
    """
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")

    needle = q.strip().lower()
    limit = max(1, min(limit, 50))
    results = []

    # A plain ID should resolve even when the member is not cached.
    if needle.isdigit():
        member = guild.get_member(int(needle))
        if member is None:
            try:
                member = await guild.fetch_member(int(needle))
            except Exception:
                member = None
        if member:
            results.append(member)

    if not results:
        for member in guild.members:
            if len(results) >= limit:
                break
            if not needle:
                results.append(member)
                continue
            if (
                needle in member.name.lower()
                or needle in member.display_name.lower()
                or needle in str(member.id)
            ):
                results.append(member)

    return {
        "members": [
            {
                "id": str(m.id),
                "name": m.name,
                "display_name": m.display_name,
                "avatar": str(m.display_avatar.url),
                "bot": m.bot,
                "top_role": m.top_role.name if m.top_role else None,
            }
            for m in results[:limit]
        ]
    }
