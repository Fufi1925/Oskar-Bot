# ╔══════════════════════════════════════════════════════════════════╗
# ║   Cookie-Zustimmungen                                            ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Nachweis, dass jemand den Cookie-Hinweis gesehen hat.

  POST   /consent          eine Bestätigung festhalten
  GET    /consents         die Liste fürs Admin-Dashboard
  GET    /consents/stats   die Zahlen und die Tageskurve
  DELETE /consents/{id}    eine einzelne löschen
  POST   /consents/user    alles zu einem Discord-Konto löschen

Wer bestätigt hat, wird hier nicht geprüft: der Proxy im Dashboard
kennt die angemeldete Sitzung und setzt ``user_id`` und ``user_name``
selbst ein. Käme beides aus dem Browser, schriebe sich jeder eine
fremde Discord-ID in den Nachweis -- und der Nachweis wäre wertlos,
weil er belegte, was sich jemand ausgedacht hat.

``POST /consent`` ist die einzige Route hier, die ohne Anmeldung
erreichbar ist. Sie muss es sein: der Hinweis erscheint auf der
öffentlichen Startseite, lange bevor sich jemand anmeldet.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from utils import cookie_consent as store
from utils import feature_audit

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/consent", summary="Eine Cookie-Bestätigung festhalten")
async def record_consent(data: dict):
    """Was das Fenster beim Klick auf „Verstanden" schickt.

    Die Browser-Kennung erzeugt die Seite selbst (``randomUUID``) und
    legt sie in einem eigenen Cookie ab. Sie ist keine Kennung einer
    Person: sie sagt „dieser Browser", mehr nicht.
    """
    besucher_id = str(data.get("besucher_id") or "").strip()
    if not store.gueltige_id(besucher_id):
        raise HTTPException(status_code=400, detail="Keine gültige Besucher-Kennung.")

    ergebnis = store.record(
        besucher_id,
        # Beide kommen vom Proxy aus der Sitzung, nicht aus dem Browser.
        user_id=str(data.get("user_id") or ""),
        user_name=str(data.get("user_name") or ""),
        version=str(data.get("version") or ""),
        pfad=str(data.get("pfad") or ""),
    )

    if not ergebnis["ok"]:
        raise HTTPException(status_code=400, detail="Keine gültige Besucher-Kennung.")

    return {
        "status": "success",
        "neu": ergebnis["neu"],
        "consent": ergebnis["consent"],
    }


@router.get("/consents", summary="Alle Bestätigungen")
async def list_consents(limit: int = 300, nur_konto: bool = False):
    return {
        "consents": store.list_all(limit, nur_konto=nur_konto),
        "stats": store.stats(),
        "keep_days": store.KEEP_DAYS,
    }


@router.get("/consents/stats", summary="Zahlen und Tageskurve")
async def consent_stats(tage: int = 30):
    return {
        "stats": store.stats(),
        "verlauf": store.per_day(tage),
        "keep_days": store.KEEP_DAYS,
    }


@router.delete("/consents/{besucher_id}", summary="Eine Bestätigung löschen")
async def delete_consent(besucher_id: str, actor: str = ""):
    """Löschen -- für einen Widerruf oder eine Auskunft.

    Der Eintrag verschwindet ganz. Ein „gelöscht"-Merker wäre hier
    falsch: er wäre selbst wieder ein Datum über eine Person, die
    gerade darum gebeten hat, keins mehr zu sein.
    """
    weg = store.delete(besucher_id)
    if not weg:
        raise HTTPException(status_code=404, detail="Diese Bestätigung gibt es nicht.")

    await feature_audit.log_action(
        "cookie_consent_deleted", actor=actor or "system",
        detail=f"besucher={besucher_id[:8]}…",
    )
    return {"status": "success", "deleted": 1}


@router.post("/consents/user", summary="Alles zu einem Konto löschen")
async def delete_for_user(data: dict, actor: str = ""):
    """Ein Löschverlangen nach Art. 17 DSGVO nennt ein Konto.

    Niemand kennt seine eigene Browser-Kennung; genannt wird die
    Discord-ID. Deshalb gibt es diesen zweiten Weg.
    """
    user_id = str(data.get("user_id") or "").strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Keine gültige Benutzer-ID.")

    anzahl = store.delete_for_user(user_id)
    await feature_audit.log_action(
        "cookie_consent_deleted_user", actor=actor or "system",
        detail=f"user={user_id}, {anzahl} Eintraege",
    )
    return {"status": "success", "deleted": anzahl}
