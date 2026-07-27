# ╔══════════════════════════════════════════════════════════════════╗
# ║   Ticket panels                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Panel-based ticket configuration.

Each endpoint touches exactly one thing — a panel, a category, the
server-wide settings — so switching tabs in the dashboard cannot lose
half the form. The old single PATCH wrote every field of every section at
once and aborted midway when one column was missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api import ticket_panels as panels
from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

DB = "db/ticket.db"


async def _db():
    connection = await db_manager.get_connection(DB)
    await panels.ensure_schema(connection)
    return connection


# ══════════════════════════════════════════════════════════════════════
#  Overview
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/panels", summary="All ticket panels of a guild")
async def get_panels(guild_id: int):
    db = await _db()

    async with db.execute(
        "SELECT logging_channel_id, closed_category_id, staff_roles"
        " FROM guild_configs WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    async with db.execute(
        "SELECT COUNT(*) FROM open_tickets WHERE guild_id = ? AND closed_at IS NULL",
        (guild_id,),
    ) as cursor:
        open_row = await cursor.fetchone()

    return {
        "guild_id": str(guild_id),
        "panels": await panels.list_panels(db, guild_id),
        "server": {
            "logging_channel": str(row[0]) if row and row[0] else None,
            "closed_category": str(row[1]) if row and row[1] else None,
            "staff_roles": [
                r for r in str((row[2] if row else "") or "").split(",") if r.isdigit()
            ],
        },
        "open_tickets": open_row[0] if open_row else 0,
    }


@router.patch("/{guild_id}/server", summary="Server-wide ticket settings")
async def update_server_settings(guild_id: int, data: dict):
    """
    Transcript channel, archive category and the global staff roles.

    Separate from the panels on purpose: these apply to every ticket, and
    saving them should not require touching a panel.
    """
    db = await _db()

    async with db.execute(
        "SELECT guild_id FROM guild_configs WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO guild_configs (guild_id) VALUES (?)", (guild_id,)
            )

    mapping = {
        "logging_channel": "logging_channel_id",
        "closed_category": "closed_category_id",
    }
    assignments, values = [], []
    for key, column in mapping.items():
        if key in data:
            assignments.append(f"{column} = ?")
            values.append(data[key] or None)

    if "staff_roles" in data:
        assignments.append("staff_roles = ?")
        values.append(",".join(str(r) for r in (data["staff_roles"] or [])))

    if assignments:
        values.append(guild_id)
        await db.execute(
            f"UPDATE guild_configs SET {', '.join(assignments)} WHERE guild_id = ?",
            values,
        )
        await db.commit()

    return {"status": "success", "updated": len(assignments)}


# ══════════════════════════════════════════════════════════════════════
#  Panels
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/panels", summary="Create a panel")
async def create_panel(guild_id: int, data: dict | None = None):
    db = await _db()
    name = str((data or {}).get("name", "Support")).strip()[:100] or "Support"
    panel_id = await panels.create_panel(db, guild_id, name)
    await feature_audit.log_action(
        "ticket_panel_created",
        actor=str((data or {}).get("actor", "dashboard")),
        guild_id=guild_id,
        detail=name,
    )
    return {"status": "success", "panel_id": panel_id}


@router.patch("/{guild_id}/panels/{panel_id}", summary="Update one panel")
async def update_panel(guild_id: int, panel_id: int, data: dict):
    db = await _db()
    changed = await panels.update_panel(db, guild_id, panel_id, data)
    if not changed:
        return {"status": "success", "changed": False}
    return {"status": "success", "changed": True}


@router.delete("/{guild_id}/panels/{panel_id}", summary="Delete a panel")
async def delete_panel(guild_id: int, panel_id: int, actor: str = ""):
    db = await _db()
    if not await panels.delete_panel(db, guild_id, panel_id):
        raise HTTPException(status_code=404, detail="Panel not found.")
    await feature_audit.log_action(
        "ticket_panel_deleted",
        actor=actor or "dashboard",
        guild_id=guild_id,
        detail=str(panel_id),
    )
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════
#  Categories
# ══════════════════════════════════════════════════════════════════════


@router.put("/{guild_id}/panels/{panel_id}/categories", summary="Add or edit a category")
async def upsert_category(guild_id: int, panel_id: int, data: dict):
    db = await _db()
    try:
        category_id = await panels.upsert_category(db, guild_id, panel_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "category_id": category_id}


@router.delete(
    "/{guild_id}/categories/{category_id}", summary="Delete a category"
)
async def delete_category(guild_id: int, category_id: int):
    db = await _db()
    if not await panels.delete_category(db, guild_id, category_id):
        raise HTTPException(status_code=404, detail="Category not found.")
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════
#  Posting
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/panels/{panel_id}/send", summary="Post a panel")
async def send_panel(
    guild_id: int,
    panel_id: int,
    data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Post the panel, replacing the previous message if there is one.

    Refuses early with a clear reason rather than posting something
    unusable: no channel picked, no categories, or the bot cannot post.
    """
    actor = str((data or {}).get("actor", "dashboard"))
    db = await _db()

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not on this server.")

    all_panels = await panels.list_panels(db, guild_id)
    panel = next((p for p in all_panels if p["panel_id"] == panel_id), None)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel not found.")

    if not panel["channel_id"]:
        raise HTTPException(
            status_code=400, detail="Pick a channel for this panel first."
        )
    if not panel["categories"]:
        raise HTTPException(
            status_code=400,
            detail="Add at least one category before posting the panel.",
        )

    channel = guild.get_channel(int(panel["channel_id"]))
    if channel is None:
        raise HTTPException(
            status_code=400, detail="The selected channel no longer exists."
        )

    permissions = channel.permissions_for(guild.me)
    if not permissions.send_messages:
        raise HTTPException(
            status_code=403, detail=f"The bot may not post in #{channel.name}."
        )

    # Replace the old message so a channel does not fill up with panels.
    if panel["message_id"]:
        try:
            old = await channel.fetch_message(int(panel["message_id"]))
            await old.delete()
        except Exception:
            pass

    from utils.panels import ACCENT, Panel

    buttons = []
    for category in panel["categories"]:
        try:
            style = discord.ButtonStyle(int(category["button_style"]))
        except (ValueError, TypeError):
            style = discord.ButtonStyle.secondary
        buttons.append(
            discord.ui.Button(
                label=category["name"][:80],
                emoji=category["emoji"] or None,
                style=style,
                custom_id=f"create_ticket_{category['category_id']}",
            )
        )

    view = Panel(
        panel["embed_title"] or panel["name"],
        panel["embed_description"] or "Klicke unten, um ein Ticket zu öffnen.",
        accent=panel["embed_color"] or ACCENT["brand"],
        image_url=panel["embed_image_url"] or None,
        buttons=buttons,
    )

    try:
        message = await channel.send(view=view)
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord rejected the message: {exc}"
        ) from exc

    await panels.set_message_id(db, guild_id, panel_id, message.id)

    try:
        bot.add_view(view, message_id=message.id)
    except Exception:
        pass

    await feature_audit.log_action(
        "ticket_panel_sent",
        actor=actor,
        guild_id=guild_id,
        detail=f"#{channel.name}",
    )
    return {
        "status": "success",
        "channel": channel.name,
        "url": message.jump_url,
        "result": f"Panel posted in #{channel.name}.",
    }
