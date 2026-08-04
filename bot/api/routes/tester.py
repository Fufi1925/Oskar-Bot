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
async def list_feedback(
    user_id: str = "",
    limit: int = 100,
    state: str = "",
    kind: str = "",
):
    """
    Owner sehen alles, Tester nur ihre eigenen Meldungen.

    Ein Tester soll wissen, dass seine Meldung angekommen ist -- fremde
    gehen ihn nichts an, und in einer Fehlermeldung steht schnell mehr,
    als der Melder öffentlich sagen wollte.
    """

    uid = _require_tester(user_id)

    if roles.is_owner(uid):
        return {
            "entries": feedback.listing(
                viewer=uid, limit=limit, state=state, kind=kind
            ),
            "stats": feedback.stats(),
            "scope": "all",
        }

    return {
        "entries": feedback.listing(
            user_id=uid, viewer=uid, limit=limit, state=state, kind=kind
        ),
        "stats": {},
        "scope": "own",
    }


@router.get("/feedback/{entry_id}", summary="Eine Meldung samt Verlauf")
async def feedback_detail(entry_id: int, user_id: str = ""):
    """Die Einzelansicht -- mit allen Kommentaren."""

    uid = _require_tester(user_id)

    entry = feedback.detail(entry_id, viewer=uid)
    if entry is None:
        raise HTTPException(status_code=404, detail="Die Meldung gibt es nicht.")

    # Ein Tester sieht nur seine eigene. Ohne diese Zeile käme er über
    # /feedback/17 an jede fremde Meldung -- die Liste filtert, die
    # Einzelansicht muss es auch.
    if not roles.is_owner(uid) and str(entry["user_id"]) != uid:
        raise HTTPException(
            status_code=403, detail="Das ist nicht deine Meldung."
        )

    return entry


@router.post("/feedback", summary="Fehler oder Vorschlag einreichen")
async def create_feedback(data: dict):
    """Eine Meldung speichern."""

    uid = _require_tester(str(data.get("user_id") or ""))

    result = feedback.submit(
        uid,
        str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        kind=str(data.get("kind") or "bug"),
        area=str(data.get("area") or ""),
        priority=str(data.get("priority") or "normal"),
        user_name=str(data.get("user_name") or ""),
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])

    # `similar` mitgeben statt die Meldung abzulehnen: zwei Leute
    # können dieselbe Überschrift für verschiedene Dinge wählen, und
    # wer ein "gibt es schon" bekommt, meldet beim nächsten Mal gar
    # nichts mehr.
    return {
        "submitted": True,
        "id": result["id"],
        "similar": result["similar"],
    }


@router.post("/feedback/{entry_id}/comment", summary="Antworten")
async def add_comment(entry_id: int, data: dict):
    """
    Eine Rückfrage oder Antwort anhängen.

    Owner dürfen überall antworten, ein Tester nur in seiner eigenen
    Meldung -- sonst könnte er in fremden mitreden, die er gar nicht
    sehen darf.
    """

    uid = _require_tester(str(data.get("user_id") or ""))

    entry = feedback.detail(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Die Meldung gibt es nicht.")

    if not roles.is_owner(uid) and str(entry["user_id"]) != uid:
        raise HTTPException(
            status_code=403, detail="Das ist nicht deine Meldung."
        )

    text = str(data.get("text") or "")
    if not feedback.comment(entry_id, uid, text):
        raise HTTPException(status_code=400, detail="Der Text ist leer.")

    return {"added": True}


@router.post("/feedback/{entry_id}/vote", summary="Zustimmen")
async def vote_feedback(entry_id: int, data: dict):
    """Zustimmung geben oder zurückziehen.

    Damit sichtbar wird, welcher Vorschlag mehreren wichtig ist -- und
    welcher Fehler mehrere trifft.
    """

    uid = _require_tester(str(data.get("user_id") or ""))

    result = feedback.vote(entry_id, uid)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail="Die Meldung gibt es nicht.")

    return result


@router.post("/feedback/{entry_id}", summary="Bearbeiten")
async def update_feedback(entry_id: int, data: dict):
    """Stand, Dringlichkeit, Bearbeiter -- nur für Owner."""

    actor = _require_owner(str(data.get("user_id") or ""))

    raw_duplicate = data.get("duplicate_of")
    duplicate_of = None
    if raw_duplicate not in (None, "", 0):
        try:
            duplicate_of = int(raw_duplicate)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="»duplicate_of« muss eine Nummer sein."
            ) from None

    raw_assignee = data.get("assignee")

    result = feedback.update(
        entry_id,
        actor=actor,
        state=str(data.get("state") or ""),
        priority=str(data.get("priority") or ""),
        assignee=None if raw_assignee is None else str(raw_assignee),
        duplicate_of=duplicate_of,
        note=str(data.get("note") or ""),
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])

    return result


@router.get("/feedback-options", summary="Zustände und Dringlichkeiten")
async def feedback_options(user_id: str = ""):
    """Damit das Dashboard die Listen nicht zweitpflegen muss."""

    _require_tester(user_id)
    return {
        "states": list(feedback.STATES),
        "priorities": list(feedback.PRIORITIES),
        "kinds": list(feedback.KINDS),
        "closed": list(feedback.CLOSED),
    }


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
