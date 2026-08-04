"""
Der Tester-Bereich.

Wer die Rolle **Tester** hat, sieht im Admin-Panel genau einen Reiter:
was zuletzt ausgeliefert wurde, und ein Formular fuer Fehler und
Vorschlaege. Sonst nichts -- ein Tester soll Funktionen ausprobieren,
nicht den Server verwalten.

Dazu bekommt er alle Premium-Funktionen frei, ohne Key. Das passiert
nicht hier, sondern in ``utils/premium_store.status()``: das ist die
eine Stelle, an der "hat dieser Nutzer Premium?" beantwortet wird.

Die Rechte werden **hier** geprueft und nicht nur im Dashboard. Wer die
Rolle verliert, verliert Reiter und Premium sofort -- die Antwort haengt
an ``dashboard_roles``, nicht an einer Sitzung, die noch offen ist.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from utils import changelog
from utils import dashboard_roles as roles
from utils import tester_feedback as feedback

router = APIRouter()


def _require_tester(user_id: str) -> str:
    """Abbrechen, wenn der Aufrufer weder Tester noch Owner ist."""

    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")

    # Owner sehen alles -- sie verwalten den Bereich ja.
    if roles.is_owner(uid):
        return uid
    if roles.has_permission(uid, "tester.access"):
        return uid

    raise HTTPException(
        status_code=403, detail="Dieser Bereich ist für Tester."
    )


def _require_owner(user_id: str) -> str:
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    if not roles.is_owner(uid):
        raise HTTPException(
            status_code=403, detail="Das dürfen nur Owner."
        )
    return uid


@router.get("/status", summary="Ist dieser Nutzer Tester?")
async def status(user_id: str = ""):
    """Was der Reiter beim Öffnen fragt.

    Auch ohne Tester-Rolle eine gültige Antwort -- das Dashboard
    entscheidet daran, ob es den Reiter überhaupt zeigt.
    """

    uid = str(user_id or "").strip()
    if not uid:
        return {"tester": False, "owner": False, "premium_bypass": False}

    owner = roles.is_owner(uid)
    tester = roles.is_tester(uid)

    return {
        "tester": tester or owner,
        "owner": owner,
        # Die Premium-Freischaltung haengt an der Rolle, nicht am
        # Owner-Status: Owner haben ihre Rechte ohnehin anders.
        "premium_bypass": tester,
        "role_label": "Tester" if tester else ("Owner" if owner else ""),
    }


@router.get("/changelog", summary="Was zuletzt ausgeliefert wurde")
async def deploy_changelog(user_id: str = "", limit: int = 40):
    """Die Änderungen des letzten Deploys, aus den Git-Commits."""

    _require_tester(user_id)
    return changelog.recent(limit)


@router.get("/feedback", summary="Gemeldete Fehler und Vorschläge")
async def list_feedback(user_id: str = "", limit: int = 100):
    """
    Owner sehen alles, Tester nur ihre eigenen Meldungen.

    Ein Tester soll wissen, dass seine Meldung angekommen ist -- fremde
    Meldungen gehen ihn nichts an, und in einer Fehlermeldung steht
    schnell mehr, als der Melder öffentlich sagen wollte.
    """

    uid = _require_tester(user_id)

    if roles.is_owner(uid):
        return {
            "entries": feedback.listing(limit=limit),
            "stats": feedback.stats(),
            "scope": "all",
        }

    return {
        "entries": feedback.listing(user_id=uid, limit=limit),
        "stats": {},
        "scope": "own",
    }


@router.post("/feedback", summary="Fehler oder Vorschlag einreichen")
async def create_feedback(data: dict):
    """Eine Meldung speichern."""

    uid = _require_tester(str(data.get("user_id") or ""))

    result = feedback.submit(
        uid,
        str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        kind=str(data.get("kind") or "bug"),
        user_name=str(data.get("user_name") or ""),
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])

    return {"submitted": True, "id": result["id"]}


@router.post("/feedback/{entry_id}", summary="Bearbeitungsstand setzen")
async def update_feedback(entry_id: int, data: dict):
    """Owner setzen den Stand: offen, geplant, erledigt, abgelehnt."""

    _require_owner(str(data.get("user_id") or ""))

    state = str(data.get("state") or "").strip()
    if state not in feedback.STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannter Stand. Möglich: {', '.join(feedback.STATES)}.",
        )

    if not feedback.set_state(entry_id, state, str(data.get("note") or "")):
        raise HTTPException(status_code=404, detail="Die Meldung gibt es nicht.")

    return {"updated": True, "state": state}


@router.get("/members", summary="Wer die Tester-Rolle hat")
async def members(user_id: str = ""):
    """
    Die Liste der Tester -- nur für Owner.

    Sie zeigt, wer gerade Premium ohne Key hat. Das ist nichts, was ein
    Tester über andere wissen muss.
    """

    _require_owner(user_id)

    # Über all_members() statt über eine eigene Abfrage: die Funktion
    # gibt es schon, sie liest denselben Cache, und eine zweite
    # Leseroutine wäre eine zweite Stelle, die bei einer Schema-
    # Änderung nachgezogen werden müsste.
    # Über all_members() statt über eine eigene Abfrage: die Funktion
    # gibt es schon, sie liest denselben Cache, und eine zweite
    # Leseroutine wäre eine zweite Stelle, die bei einer
    # Schema-Änderung nachgezogen werden müsste.
    entries = []
    for member in roles.all_members():
        assigned = [
            entry
            for entry in member.get("roles", [])
            if entry.get("key") == roles.TESTER_ROLE_KEY
        ]
        if not assigned:
            continue

        tester_role = assigned[0]
        entries.append(
            {
                "user_id": member.get("user_id", ""),
                "granted_by": tester_role.get("granted_by", ""),
                "granted_at": tester_role.get("granted_at", 0),
                "note": tester_role.get("note", ""),
                # Weitere Rollen mitgeben: wer neben Tester noch
                # Moderator ist, hat den Premium-Bypass zusätzlich zu
                # allem anderen -- das sollte man sehen.
                "other_roles": [
                    entry.get("label", "")
                    for entry in member.get("roles", [])
                    if entry.get("key") != roles.TESTER_ROLE_KEY
                ],
            }
        )

    return {"members": entries, "count": len(entries)}
