"""Self-service erasure requests with owner review."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import privacy_erasure as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _dm(bot, user_id: int, text: str) -> bool:
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(text)
        return True
    except Exception as exc:
        print(f"[privacy] DM an {user_id} fehlgeschlagen: {exc}")
        return False


async def notify_pending(bot) -> int:
    """Notify Fufi once per matured request, including after a restart."""
    items = store.pending_notifications()
    sent = 0
    for item in items:
        ok = await _dm(
            bot,
            store.FUFI_ID,
            "🔴 Neuer Antrag auf Datenlöschung nach Art. 17 DSGVO\n"
            f"Nutzer: {item['username'] or 'Unbekannt'}\n"
            f"Discord-ID: {item['user_id']}\n"
            f"Antrag: {item['id']}\n"
            "Bitte im Admin-Dashboard unter „Datenlöschung“ prüfen.",
        )
        store.finish_notification(item["id"], ok)
        sent += int(ok)
    return sent


async def _mature_and_notify(bot, request_id: str) -> None:
    item = store.get_request(request_id)
    if not item:
        return
    remaining = max(0, int(item["undo_until"]) - int(time.time()))
    if remaining:
        await asyncio.sleep(remaining)
    store.mature(request_id)
    await notify_pending(bot)


@router.post("/request", summary="Datenlöschung beantragen")
async def request_erasure(data: dict, bot: "universitybot" = Depends(get_bot)):
    user_id = str(data.get("user_id") or "").strip()
    username = str(data.get("username") or "").strip()
    if not user_id.isdigit() or not username:
        raise HTTPException(status_code=400, detail="Konto konnte nicht bestätigt werden.")
    item = store.create_request(user_id, username)
    asyncio.create_task(_mature_and_notify(bot, item["id"]))
    return item


@router.get("/status/{user_id}", summary="Eigener Löschantrag")
async def erasure_status(user_id: str):
    return {"request": store.status_for(user_id)}


@router.post("/cancel", summary="Löschantrag während der Frist zurücknehmen")
async def cancel_erasure(data: dict):
    ok = store.cancel(str(data.get("request_id") or ""), str(data.get("user_id") or ""))
    if not ok:
        raise HTTPException(status_code=409, detail="Die 10-Sekunden-Frist ist bereits abgelaufen.")
    return {"status": "cancelled"}


@router.get("/admin/requests", summary="Löschanträge verwalten")
async def admin_requests():
    return {"requests": store.list_requests()}


@router.post("/admin/decide", summary="Löschantrag genehmigen oder ablehnen")
async def decide_erasure(data: dict, bot: "universitybot" = Depends(get_bot)):
    request_id = str(data.get("request_id") or "")
    actor = str(data.get("actor") or "")
    action = str(data.get("action") or "")
    if action == "approve":
        before = store.get_request(request_id)
        item = store.approve(request_id, actor)
        if not item:
            raise HTTPException(status_code=409, detail="Der Antrag ist nicht mehr offen.")
        if before:
            try:
                await _dm(
                    bot, int(before["user_id"]),
                    "Dein Antrag auf Datenlöschung wurde genehmigt. "
                    "Die freigegebenen Kontodaten wurden gelöscht oder anonymisiert "
                    "und Premium wurde entfernt.",
                )
            except (TypeError, ValueError):
                pass
        return item
    if action == "reject":
        reason = str(data.get("reason") or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Bitte begründe die Ablehnung.")
        item = store.reject(request_id, actor, reason)
        if not item:
            raise HTTPException(status_code=409, detail="Der Antrag ist nicht mehr offen.")
        try:
            await _dm(bot, int(item["user_id"]), f"Dein Antrag auf Datenlöschung wurde abgelehnt.\nGrund: {reason}")
        except (TypeError, ValueError):
            pass
        return item
    raise HTTPException(status_code=400, detail="Unbekannte Entscheidung.")
