# ╔══════════════════════════════════════════════════════════════════╗
# ║   Admin broadcasts API                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Owner-only: send one message to every server the bot is on.

These routes live under /admin/broadcast, so the existing owner check in
the dashboard proxy applies and nothing here is reachable from a normal
guild dashboard.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import broadcast_store as store
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _shape(row: dict) -> dict:
    """One broadcast, with ids as strings and a readable status."""
    return {
        "id": row["id"],
        "title": row.get("title") or "",
        "message": row.get("message") or "",
        "tone": row.get("tone") or "info",
        "image_url": row.get("image_url") or "",
        "target": row.get("target") or "channel",
        "status": row.get("status") or "draft",
        "send_at": row.get("send_at"),
        "created_at": row.get("created_at"),
        "created_by": row.get("created_by") or "",
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "delivered": int(row.get("delivered") or 0),
        "failed": int(row.get("failed") or 0),
        "only_guilds": [str(g) for g in row.get("only_guilds") or []],
    }


@router.get("/broadcast", summary="Past and pending broadcasts")
async def list_broadcasts(bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    rows = await store.recent(db, 25)

    return {
        "broadcasts": [_shape(row) for row in rows],
        "guild_count": len(bot.guilds),
        "targets": [
            {"id": store.TARGET_CHANNEL, "label": "In einen Kanal je Server"},
            {"id": store.TARGET_OWNER, "label": "Als DM an die Server-Inhaber"},
            {"id": store.TARGET_BOTH, "label": "Beides"},
        ],
    }


@router.get("/broadcast/{broadcast_id}", summary="One broadcast with its results")
async def get_broadcast(broadcast_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    row = await store.get(db, broadcast_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden.")

    return {
        **_shape(row),
        "results": [
            {
                "guild_id": str(entry["guild_id"]),
                "guild_name": entry.get("guild_name") or "",
                "ok": bool(entry.get("ok")),
                "detail": entry.get("detail") or "",
                "at": entry.get("at"),
            }
            for entry in await store.results(db, broadcast_id)
        ],
    }


@router.post("/broadcast/preview", summary="Where would this land?")
async def preview_broadcast(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Work out the target list without sending anything.

    A broadcast cannot be taken back once it is out, so the dashboard
    always shows exactly which servers and channels it would reach.
    """
    db = await _db()
    try:
        fields = store.clean(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    broadcast_id = await store.create(db, fields, created_by="preview")
    try:
        plan = await store.deliver(bot, db, broadcast_id, dry_run=True)
    finally:
        # A preview must not linger in the history.
        await db.execute("DELETE FROM broadcasts WHERE id = ?", (broadcast_id,))
        await db.commit()

    return plan


@router.post("/broadcast/test", summary="Send only to one server")
async def test_broadcast(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Deliver to a single guild, to see the real thing before going wide.
    """
    db = await _db()
    guild_id = str(data.get("guild_id") or "")
    if not guild_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Server auswählen.")
    if bot.get_guild(int(guild_id)) is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")

    try:
        fields = store.clean({**data, "only_guilds": [guild_id]})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    broadcast_id = await store.create(db, fields, created_by="test")
    result = await store.deliver(bot, db, broadcast_id)

    await feature_audit.log_action(
        "broadcast_test", actor=str(data.get("actor", "dashboard")),
        detail=f"#{broadcast_id} → {guild_id}",
    )
    return {
        "status": "success",
        "result": (
            "Testnachricht zugestellt." if result["delivered"]
            else "Konnte nicht zugestellt werden — siehe Ergebnis."
        ),
        "id": broadcast_id,
        **result,
    }


@router.post("/broadcast", summary="Send or schedule a broadcast")
async def send_broadcast(data: dict, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    try:
        fields = store.clean(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    send_at = data.get("send_at")
    if send_at:
        try:
            send_at = int(send_at)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Zeitpunkt muss eine Zahl sein.")
        if send_at < int(time.time()) - 60:
            raise HTTPException(
                status_code=400, detail="Der Zeitpunkt liegt in der Vergangenheit."
            )
    else:
        send_at = None

    broadcast_id = await store.create(
        db, fields, send_at=send_at,
        created_by=str(data.get("actor", "dashboard")),
    )

    if send_at:
        await feature_audit.log_action(
            "broadcast_scheduled", actor=str(data.get("actor", "dashboard")),
            detail=f"#{broadcast_id} um {send_at}",
        )
        return {
            "status": "success",
            "id": broadcast_id,
            "result": "Für später eingeplant.",
            "scheduled": True,
        }

    result = await store.deliver(bot, db, broadcast_id)
    await feature_audit.log_action(
        "broadcast_sent", actor=str(data.get("actor", "dashboard")),
        detail=f"#{broadcast_id}: {result['delivered']}/{result['guilds']}",
    )
    return {
        "status": "success",
        "id": broadcast_id,
        "result": (
            f"An {result['delivered']} von {result['guilds']} Servern zugestellt"
            + (f", {result['failed']} fehlgeschlagen." if result["failed"] else ".")
        ),
        **result,
    }


@router.post("/broadcast/{broadcast_id}/cancel", summary="Call back a scheduled one")
async def cancel_broadcast(
    broadcast_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.cancel(db, broadcast_id):
        raise HTTPException(
            status_code=400,
            detail="Nur eingeplante Nachrichten lassen sich zurücknehmen.",
        )

    await feature_audit.log_action(
        "broadcast_cancelled",
        actor=str((data or {}).get("actor", "dashboard")),
        detail=f"#{broadcast_id}",
    )
    return {"status": "success", "result": "Zurückgenommen."}


@router.post("/broadcast/{broadcast_id}/resend", summary="Retry the servers that failed")
async def resend_broadcast(
    broadcast_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Send again, only to the guilds where it did not arrive.

    A closed DM or a missing permission is usually temporary; without
    this the only option was to broadcast to everybody a second time.
    """
    db = await _db()
    row = await store.get(db, broadcast_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden.")

    failed = [
        str(entry["guild_id"])
        for entry in await store.results(db, broadcast_id)
        if not entry.get("ok")
    ]
    if not failed:
        raise HTTPException(
            status_code=400, detail="Es ist überall angekommen — nichts zu wiederholen."
        )

    fields = store.clean({**row, "only_guilds": failed})
    retry_id = await store.create(
        db, fields, created_by=str((data or {}).get("actor", "dashboard"))
    )
    result = await store.deliver(bot, db, retry_id)

    await feature_audit.log_action(
        "broadcast_resent", actor=str((data or {}).get("actor", "dashboard")),
        detail=f"#{broadcast_id} → #{retry_id}: {result['delivered']}/{len(failed)}",
    )
    return {
        "status": "success",
        "id": retry_id,
        "result": f"{result['delivered']} von {len(failed)} nachgeholt.",
        **result,
    }
