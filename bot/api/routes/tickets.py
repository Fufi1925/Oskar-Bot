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
import time

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api import ticket_panels as panels
from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit, ticket_ai, ticket_notify

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

    # Dropdown or buttons, per panel. A dropdown keeps a long list readable
    # and is the only workable option past five categories, since Discord
    # allows at most five buttons per row.
    if (panel["panel_type"] or "button") == "dropdown":
        select = discord.ui.Select(
            placeholder="Wähle eine Kategorie…",
            custom_id="create_ticket_select",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=category["name"][:100],
                    value=str(category["category_id"]),
                    emoji=category["emoji"] or None,
                )
                for category in panel["categories"][:25]
            ],
        )
        controls = [select]
    else:
        controls = []
        for category in panel["categories"]:
            try:
                style = discord.ButtonStyle(int(category["button_style"]))
            except (ValueError, TypeError):
                style = discord.ButtonStyle.secondary
            controls.append(
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
        buttons=controls,
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


# ══════════════════════════════════════════════════════════════════════
#  Private Ticket AI pilot
# ══════════════════════════════════════════════════════════════════════


def _ai_or_404(guild_id: int) -> None:
    # Deliberately return 404 outside the pilot so other guilds do not even
    # learn that an unreleased feature exists.
    if not ticket_ai.is_allowlisted(guild_id):
        raise HTTPException(status_code=404, detail="Not found.")
    if not ticket_ai.pilot_available(guild_id):
        raise HTTPException(status_code=402, detail="Ticket-KI benötigt Server-Premium.")


async def _ensure_ai_schema(db) -> None:
    for statement in ticket_ai.SCHEMA:
        await db.execute(statement)
    async with db.execute("PRAGMA table_info(ticket_ai_usage)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if "escalated" not in columns:
        await db.execute("ALTER TABLE ticket_ai_usage ADD COLUMN escalated BOOLEAN NOT NULL DEFAULT FALSE")
    await db.commit()


@router.get("/{guild_id}/ai", summary="Private Ticket AI settings")
async def get_ticket_ai(guild_id: int):
    _ai_or_404(guild_id)
    db = await _db()
    await _ensure_ai_schema(db)
    async with db.execute(
        "SELECT enabled, fallback_text FROM ticket_ai_settings WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        settings = await cursor.fetchone()
    async with db.execute(
        "SELECT filename, length(content), updated_at FROM ticket_ai_knowledge WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        knowledge = await cursor.fetchone()
    async with db.execute(
        "SELECT c.category_id, c.name, COALESCE(a.enabled, 0), COALESCE(a.instructions, '')"
        " FROM ticket_categories c LEFT JOIN ticket_ai_categories a"
        " ON a.guild_id = c.guild_id AND a.category_id = c.category_id"
        " WHERE c.guild_id = ? ORDER BY c.category_id",
        (guild_id,),
    ) as cursor:
        categories = await cursor.fetchall()
    return {
        "available": True,
        "api_key_configured": ticket_ai.api_key_configured(),
        "enabled": bool(settings[0]) if settings else False,
        "fallback_text": settings[1] if settings else "Dazu habe ich leider keine verlässliche Information in der Wissensdatenbank gefunden.",
        "knowledge": ({"filename": knowledge[0], "characters": knowledge[1], "updated_at": knowledge[2]} if knowledge else None),
        "categories": [
            {"category_id": row[0], "name": row[1], "enabled": bool(row[2]), "instructions": row[3]}
            for row in categories
        ],
    }


@router.put("/{guild_id}/ai/knowledge", summary="Upload private Ticket AI knowledge")
async def put_ticket_ai_knowledge(guild_id: int, data: dict):
    _ai_or_404(guild_id)
    filename = str(data.get("filename") or "wissen.txt").strip()[:120]
    content = str(data.get("content") or "").replace("\x00", "").strip()
    if not filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Nur .txt-Dateien sind erlaubt.")
    if not content:
        raise HTTPException(status_code=400, detail="Die Wissensdatei ist leer.")
    if len(content.encode("utf-8")) > ticket_ai.MAX_KNOWLEDGE_BYTES:
        raise HTTPException(status_code=413, detail="Die Wissensdatei darf höchstens 100 KB groß sein.")
    db = await _db()
    await _ensure_ai_schema(db)
    await db.execute(
        "INSERT INTO ticket_ai_knowledge (guild_id, filename, content, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET filename=excluded.filename, content=excluded.content, updated_at=excluded.updated_at",
        (guild_id, filename, content, int(time.time())),
    )
    await db.commit()
    return {"status": "success", "filename": filename, "characters": len(content)}


@router.delete("/{guild_id}/ai/knowledge", summary="Delete private Ticket AI knowledge")
async def delete_ticket_ai_knowledge(guild_id: int):
    _ai_or_404(guild_id)
    db = await _db()
    await _ensure_ai_schema(db)
    await db.execute("DELETE FROM ticket_ai_knowledge WHERE guild_id = ?", (guild_id,))
    await db.execute("UPDATE ticket_ai_settings SET enabled = 0 WHERE guild_id = ?", (guild_id,))
    await db.commit()
    return {"status": "success"}


@router.patch("/{guild_id}/ai", summary="Update private Ticket AI settings")
async def update_ticket_ai(guild_id: int, data: dict):
    _ai_or_404(guild_id)
    db = await _db()
    await _ensure_ai_schema(db)
    fallback = str(data.get("fallback_text") or "").strip()[:500]
    enabled = bool(data.get("enabled"))
    if enabled:
        async with db.execute("SELECT 1 FROM ticket_ai_knowledge WHERE guild_id = ?", (guild_id,)) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Lade zuerst eine Wissensdatei hoch.")
        if not ticket_ai.api_key_configured():
            raise HTTPException(status_code=503, detail=f"Railway-Variable {ticket_ai.API_KEY_ENV} fehlt.")
    await db.execute(
        "INSERT INTO ticket_ai_settings (guild_id, enabled, fallback_text, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET enabled=excluded.enabled, fallback_text=excluded.fallback_text, updated_at=excluded.updated_at",
        (guild_id, enabled, fallback or "Dazu habe ich leider keine verlässliche Information in der Wissensdatenbank gefunden.", int(time.time())),
    )
    categories = data.get("categories") or []
    valid_ids: set[int] = set()
    async with db.execute("SELECT category_id FROM ticket_categories WHERE guild_id = ?", (guild_id,)) as cursor:
        valid_ids = {int(row[0]) for row in await cursor.fetchall()}
    for item in categories:
        try:
            category_id = int(item.get("category_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        if category_id not in valid_ids:
            raise HTTPException(status_code=400, detail="Ungültige Ticket-Kategorie.")
        instructions = str(item.get("instructions") or "").strip()[:1000]
        await db.execute(
            "INSERT INTO ticket_ai_categories (guild_id, category_id, enabled, instructions) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, category_id) DO UPDATE SET enabled=excluded.enabled, instructions=excluded.instructions",
            (guild_id, category_id, bool(item.get("enabled")), instructions),
        )
    await db.commit()
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════
#  Benachrichtigungen
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/notify", summary="DM-Benachrichtigungen: Einstellungen")
async def get_notify(guild_id: int):
    """
    Die Einstellungen plus eine Uebersicht, was gerade ansteht.

    Die offenen Erinnerungen stehen mit dabei, damit im Dashboard
    sichtbar ist, dass das System arbeitet -- sonst ist ein Schalter,
    der stumm bleibt, nicht von einem kaputten Schalter zu
    unterscheiden.
    """
    settings = await ticket_notify.get_settings(guild_id)
    offen = [t for t in await ticket_notify.due_tickets() if t["guild_id"] == guild_id]

    return {
        "guild_id": str(guild_id),
        "settings": settings,
        "pending": {
            "user": sum(1 for t in offen if t["pending_user"]),
            "staff": sum(1 for t in offen if t["pending_staff"]),
        },
        "limits": {
            key: {"min": lo, "max": hi}
            for key, (lo, hi) in ticket_notify.LIMITS.items()
        },
    }


@router.patch("/{guild_id}/notify", summary="DM-Benachrichtigungen speichern")
async def save_notify(guild_id: int, data: dict, actor: str = ""):
    settings = await ticket_notify.save_settings(guild_id, data or {})

    await feature_audit.log_action(
        "ticket_notify_updated",
        actor=actor,
        guild_id=guild_id,
        detail=(
            f"Nutzer-DM {'an' if settings['user_dm_enabled'] else 'aus'}, "
            f"Team-DM {'an' if settings['staff_dm_enabled'] else 'aus'}"
        ),
    )
    return {"status": "success", "settings": settings}
