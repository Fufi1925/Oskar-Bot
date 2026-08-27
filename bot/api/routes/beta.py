# ╔══════════════════════════════════════════════════════════════════╗
# ║   Beta-Antraege fuer Hauptbot-Premium                            ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Fuenf Fragen, ein Antrag, eine Entscheidung, eine DM.

Die Discord-ID kommt aus der Sitzung
------------------------------------
Nicht aus dem Formular. Der Dashboard-Proxy setzt `user_id` und
`user_name` serverseitig -- kaeme die ID aus dem Browser, koennte
jeder einen Antrag auf ein fremdes Konto stellen, und bei Annahme
bekaeme das fremde Konto Premium.

Was bei der Annahme passiert
----------------------------
Premium wird sofort vergeben (`premium_store.grant_direct`) und der
Bot schickt eine DM. Scheitert die DM, bleibt Premium trotzdem
bestehen -- und im Admin-Bereich steht, dass sie nicht ankam. Andersrum
waere schlimmer: jemand hat bezahlt und bekommt nichts, weil seine DMs
zu sind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import beta_applications as store
from utils import feature_audit
from utils import premium_notice
from utils import premium_store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _fragen() -> list[dict]:
    """Die Fragen fuers Formular.

    Kommen aus dem Modul, nicht aus dem Browser: sonst haette das
    Dashboard eine zweite Liste, und die naechste Aenderung waere an
    einer der beiden Stellen vergessen.
    """
    return [dict(f) for f in store.FRAGEN]


def _dm_annahme() -> discord.ui.LayoutView:
    from utils.panels import StatusCard

    return StatusCard(
        "Du bist in der Beta",
        "Dein Antrag wurde angenommen — **Premium ist ab sofort aktiv**.\n\n"
        "Du findest die neuen Möglichkeiten im Dashboard unter „Design“: "
        "eigener Name, eigenes Bild und eigenes Banner für den Bot auf "
        "deinem Server.\n\n"
        "Danke, dass du die Beta mittestest. Schreib uns, wenn dir etwas "
        "auffällt.",
        tone="success",
    )


def _dm_ablehnung(grund: str) -> discord.ui.LayoutView:
    from utils.panels import StatusCard

    text = (
        "Dein Antrag für die Beta wurde leider nicht angenommen.\n\n"
    )
    if grund:
        text += f"**Begründung:** {grund}\n\n"
    text += (
        "Das ist keine Sperre — du kannst dich später erneut bewerben."
    )
    return StatusCard("Antrag abgelehnt", text, tone="warning")


async def _schicke_dm(bot, user_id: str, view) -> str:
    """DM zustellen. Gibt ehrlich zurueck, was daraus wurde."""
    try:
        user = bot.get_user(int(user_id))
        if user is None:
            user = await bot.fetch_user(int(user_id))
    except (discord.HTTPException, ValueError, TypeError):
        return "unknown_user"

    if user is None:
        return "unknown_user"

    try:
        await user.send(view=view)
        return "sent"
    except discord.Forbidden:
        return "dms_closed"
    except discord.HTTPException:
        return "failed"


# ══════════════════════════════════════════════════════════════════════
#  Fuer den Antragsteller
# ══════════════════════════════════════════════════════════════════════


@router.get("/form", summary="Die Fragen und der eigene Stand")
async def form(user_id: str = "", user_name: str = "", avatar: str = ""):
    """Was das Formular braucht.

    `user_id` kommt vom Proxy aus der Sitzung.
    """
    letzter = store.letzter_antrag(user_id) if user_id else None
    premium = False
    if str(user_id).isdigit():
        try:
            premium = bool(
                premium_store.status(user_id).get("premium")
            )
        except Exception:  # noqa: BLE001
            premium = False

    return {
        "questions": _fragen(),
        "user": {
            "id": str(user_id or ""),
            "name": user_name or "",
            "avatar": avatar or "",
        },
        "premium": premium,
        "application": letzter,
        # Ein offener Antrag sperrt einen zweiten.
        "can_apply": letzter is None or letzter["status"] != store.STATUS_OFFEN,
    }


@router.post("/apply", summary="Antrag einreichen")
async def apply(data: dict):
    user_id = str(data.get("user_id") or "").strip()
    if not user_id.isdigit():
        raise HTTPException(
            status_code=401,
            detail="Melde dich mit Discord an, um dich zu bewerben.",
        )

    try:
        antrag = store.einreichen(
            user_id,
            str(data.get("user_name") or ""),
            str(data.get("avatar") or ""),
            {feld: data.get(feld) for feld in store.ANTWORT_FELDER},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await feature_audit.log_action(
        "beta_applied", actor=user_id, detail=f"Antrag {antrag['id']}"
    )
    return {"status": "ok", "application": antrag}


# ══════════════════════════════════════════════════════════════════════
#  Das Premium-Fenster
# ══════════════════════════════════════════════════════════════════════


@router.get("/notice", summary="Soll das Premium-Fenster erscheinen?")
async def notice(user_id: str = ""):
    if not str(user_id).isdigit():
        return {"zeigen": False, "rueckkehr": False}

    try:
        premium = bool(
            premium_store.status(user_id).get("premium")
        )
    except Exception:  # noqa: BLE001
        premium = False

    return premium_notice.zustand(user_id, premium)


@router.post("/notice/seen", summary="Fenster wurde gesehen")
async def notice_seen(data: dict):
    user_id = str(data.get("user_id") or "").strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    premium_notice.als_gesehen(user_id)
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════
#  Fuers Admin-Dashboard
# ══════════════════════════════════════════════════════════════════════


@router.get("/admin/list", summary="Alle Antraege")
async def admin_list(status: str = ""):
    return {"applications": store.liste(status), "counts": store.zahlen()}


@router.post("/admin/decide", summary="Annehmen oder ablehnen")
async def admin_decide(data: dict, bot: "universitybot" = Depends(get_bot)):
    try:
        antrag_id = int(data.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Keine gültige Antrags-ID.")

    angenommen = bool(data.get("accept"))
    grund = str(data.get("reason") or "").strip()
    admin = str(data.get("actor") or "dashboard")

    if not angenommen and not grund:
        # Eine Ablehnung ohne Begruendung ist fuer den Empfaenger
        # wertlos -- er weiss nicht, ob ein zweiter Versuch Sinn hat.
        raise HTTPException(
            status_code=400,
            detail="Eine Ablehnung braucht eine Begründung.",
        )

    antrag = store.entscheiden(
        antrag_id, angenommen=angenommen, grund=grund, admin=admin
    )
    if antrag is None:
        raise HTTPException(status_code=404, detail="Diesen Antrag gibt es nicht.")

    # Erst Premium, dann die DM: bekommt jemand die Nachricht „du bist
    # dabei" und hat kein Premium, ist das der schlimmere Fehler.
    if angenommen:
        premium_store.grant_direct(
            antrag["user_id"],
            duration_days=store.BETA_DURATION_DAYS,
            # Kein `product` mehr: es gibt nur noch eins, und es gilt
            # fuer beide Bots. Ein Antrag schaltet also University Bot
            # UND Template-Bot frei.
            note=f"Beta-Antrag {antrag['id']}",
        )
        # Damit das goldene Fenster beim naechsten Besuch erscheint.
        premium_notice.zuruecksetzen(antrag["user_id"])

    zustand = await _schicke_dm(
        bot, antrag["user_id"],
        _dm_annahme() if angenommen else _dm_ablehnung(grund),
    )
    store.merke_dm(antrag["id"], zustand)

    await feature_audit.log_action(
        "beta_decided", actor=admin,
        detail=f"Antrag {antrag['id']}: "
               f"{'angenommen' if angenommen else 'abgelehnt'}, DM {zustand}",
    )

    return {
        "status": "ok",
        "dm": zustand,
        "applications": store.liste(),
        "counts": store.zahlen(),
    }


@router.post("/admin/revoke", summary="Premium wieder entziehen")
async def admin_revoke(data: dict, bot: "universitybot" = Depends(get_bot)):
    """Einem aufgenommenen Konto das Premium nehmen.

    Der Antrag wird dabei auf „abgelehnt" gesetzt -- sonst stuende im
    Admin-Bereich weiter „angenommen", waehrend das Konto laengst kein
    Premium mehr hat.
    """
    user_id = str(data.get("user_id") or "").strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Keine gültige Discord-ID.")

    admin = str(data.get("actor") or "dashboard")
    # Ohne `product`: das eine Premium wird entzogen, damit auch
    # der Zugang zum Template-Bot.
    anzahl = premium_store.revoke_user(user_id)
    store.widerrufen(user_id, admin=admin)

    # Damit das Fenster bei einer spaeteren Neuvergabe wieder kommt.
    premium_notice.zuruecksetzen(user_id)

    await feature_audit.log_action(
        "beta_revoked", actor=admin,
        detail=f"{user_id}: {anzahl} Lizenzen gesperrt",
    )

    return {
        "status": "ok",
        "revoked": anzahl,
        "applications": store.liste(),
        "counts": store.zahlen(),
    }
