# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Update                                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Das Team-Update einrichten und die Akte lesen.

Routen:

  GET    /{guild_id}                Einstellungen, Vorlagen, Rollen, Kanaele
  PATCH  /{guild_id}                Einstellungen sichern
  PUT    /{guild_id}/templates/{a}  eine Vorlage sichern
  GET    /{guild_id}/preview        wie eine Ankuendigung aussaehe
  GET    /{guild_id}/history        der Verlauf
  GET    /{guild_id}/members        wer im Team ist
  GET    /{guild_id}/warns/{user}   die Verwarnungen einer Person
  DELETE /{guild_id}/warns/{id}     eine Verwarnung aufheben
  DELETE /{guild_id}/warns/user/{u} alle Verwarnungen einer Person aufheben

Warum die Vorschau vom Bot kommt
--------------------------------
Das Dashboard koennte den Text selbst zusammensetzen. Dann gaebe es
das Format zweimal -- einmal in Python, einmal in TypeScript -- und
spaetestens bei der dritten Aenderung liefen beide auseinander. Die
Vorschau benutzt dieselbe Funktion wie das Senden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import team_update as service
from utils import team_update_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Der Bot ist nicht auf diesem Server.")
    return guild


def _roles_of(guild) -> list[dict]:
    """Die Rollen des Servers, von oben nach unten.

    ``@everyone`` und von Discord verwaltete Rollen fallen heraus:
    ``@everyone`` haette jeder, und eine Bot- oder Booster-Rolle laesst
    sich gar nicht vergeben -- sie anzubieten hiesse, einen Fehlschlag
    einzubauen.

    ``assignable`` sagt zusaetzlich, ob der Bot die Rolle anfassen
    kann. Das Dashboard zeigt es an, statt es beim ersten Befehl
    herauszufinden.
    """
    out = []
    ich = getattr(guild, "me", None)
    oben = getattr(ich, "top_role", None) if ich is not None else None

    for role in sorted(
        getattr(guild, "roles", []) or [],
        key=lambda r: getattr(r, "position", 0),
        reverse=True,
    ):
        if getattr(role, "is_default", lambda: False)():
            continue
        if getattr(role, "managed", False):
            continue

        colour = getattr(getattr(role, "colour", None), "value", 0) or 0
        out.append({
            # Als Text: 17-20 Ziffern liegen ueber JavaScripts sicherem
            # Zahlenbereich, als Zahl waere die letzte Stelle falsch.
            "id": str(int(role.id)),
            "name": role.name,
            "colour": f"#{colour:06x}" if colour else None,
            "position": int(getattr(role, "position", 0)),
            "assignable": bool(oben is None or role < oben),
        })
    return out


def _channels_of(guild) -> list[dict]:
    """Textkanaele, in die der Bot schreiben darf."""

    me = getattr(guild, "me", None)
    out = []
    for channel in getattr(guild, "text_channels", []) or []:
        allowed = True
        if me is not None:
            try:
                rechte = channel.permissions_for(me)
                allowed = rechte.send_messages and rechte.view_channel
            except Exception:
                allowed = True
        if not allowed:
            continue
        out.append({
            "id": str(int(channel.id)),
            "name": channel.name,
            "category": (
                channel.category.name
                if getattr(channel, "category", None) else None
            ),
        })
    return out


@router.get("/{guild_id}", summary="Einstellungen, Vorlagen, Rollen, Kanaele")
async def get_all(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)

    settings = await store.get_settings(guild_id)
    templates = await store.get_templates(guild_id)

    return {
        "guild_id": str(guild_id),
        "settings": settings,
        "templates": templates,
        "roles": _roles_of(guild),
        "channels": _channels_of(guild),
        "actions": [
            {"key": a, "label": store.ACTION_LABELS[a]} for a in store.ACTIONS
        ],
        "followups": list(store.FOLLOWUPS),
        "placeholders": list(store.PLACEHOLDERS),
        "counts": await store.count_events(guild_id),
        "member_count": len(await store.list_members(guild_id)),
        "limits": {
            "signers": store.MAX_SIGNERS,
            "extra_signers": store.MAX_EXTRA_SIGNERS,
            "reason": store.MAX_REASON,
            "template": store.MAX_TEMPLATE,
            "staff_roles": store.MAX_STAFF_ROLES,
            "history": store.MAX_HISTORY,
        },
    }


@router.patch("/{guild_id}", summary="Einstellungen sichern")
async def patch_settings(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)

    settings = await store.save_settings(guild_id, data or {})
    await feature_audit.log_action(
        "team_update_config",
        actor=str((data or {}).get("actor", "dashboard")),
        guild_id=guild_id,
    )
    return {"status": "success", "settings": settings}


@router.put("/{guild_id}/templates/{action}", summary="Vorlage sichern")
async def put_template(
    guild_id: int, action: str, data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)

    try:
        await store.save_template(guild_id, action, data or {})
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return {"status": "success", "templates": await store.get_templates(guild_id)}


@router.get("/{guild_id}/preview", summary="Wie eine Ankuendigung aussaehe")
async def preview(
    guild_id: int, action: str = store.ACTION_UPRANK,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Der fertige Text, ohne ihn zu senden.

    Mit Beispielwerten: eine echte Vorschau brauchte eine echte
    Befoerderung, und die soll niemand ausloesen, nur um zu sehen, wie
    es aussieht.
    """
    guild = _guild_or_404(bot, guild_id)

    if action not in store.ACTIONS:
        raise HTTPException(400, f"Unbekannte Aktion: {action}")

    settings = await store.get_settings(guild_id)
    templates = await store.get_templates(guild_id)
    vorlage = templates[action]

    # Beispielwerte. Nicht als Attrappe von Discord-Objekten, sondern
    # direkt als Platzhalter-Tabelle -- das ist genau das, was
    # store.render() verlangt.
    import time as _time

    beispiel = {
        "user": "@Beispiel",
        "user_name": "Beispiel",
        "user_id": "1303627964734246944",
        "alt": "@Supporter",
        "alt_name": "Supporter",
        "neu": "@Moderator",
        "neu_name": "Moderator",
        "grund": "Zuverlässig und hilfsbereit",
        "unterschriften": "@Du, @Kollegin",
        "actor": "@Du",
        "server": getattr(guild, "name", ""),
        "anzahl": "2",
        "datum": f"<t:{int(_time.time())}:F>",
    }

    return {
        "action": action,
        "label": store.ACTION_LABELS[action],
        "title": store.render(vorlage["title"], beispiel),
        "text": store.render(vorlage["body"], beispiel),
        "dm_text": store.render(vorlage["dm_body"], beispiel),
        "colour": vorlage["colour"],
        "enabled": vorlage["enabled"],
        "channel_id": store.channel_for(settings, action),
    }


@router.get("/{guild_id}/history", summary="Der Verlauf")
async def history(
    guild_id: int, user_id: str = "", action: str = "",
    limit: int = 50, offset: int = 0,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)

    ereignisse = await store.list_events(
        guild_id,
        user_id=int(user_id) if str(user_id).isdigit() else None,
        action=action, limit=limit, offset=offset,
    )

    # Namen dazu: ohne sie steht im Dashboard eine nackte Zahl. Der
    # Cache reicht dafuer -- ein fehlender Name ist kein Grund, die
    # Liste scheitern zu lassen.
    for eintrag in ereignisse:
        mitglied = guild.get_member(int(eintrag["user_id"]))
        eintrag["user_name"] = (
            getattr(mitglied, "display_name", "") if mitglied else ""
        )
        for feld, ziel in (("old_role_id", "old_role_name"),
                           ("new_role_id", "new_role_name")):
            rid = eintrag.get(feld)
            rolle = guild.get_role(int(rid)) if str(rid).isdigit() else None
            eintrag[ziel] = getattr(rolle, "name", "") if rolle else ""

    return {"events": ereignisse, "count": len(ereignisse)}


@router.get("/{guild_id}/members", summary="Wer im Team ist")
async def members(
    guild_id: int, include_former: bool = False,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)

    liste = await store.list_members(guild_id, active_only=not include_former)
    for eintrag in liste:
        mitglied = guild.get_member(int(eintrag["user_id"]))
        eintrag["user_name"] = (
            getattr(mitglied, "display_name", "") if mitglied else ""
        )
        # Ob die Person ueberhaupt noch auf dem Server ist. Eine Akte
        # mit Karteileichen sieht sonst aus wie ein grosses Team.
        eintrag["in_guild"] = mitglied is not None
        rolle = (
            guild.get_role(int(eintrag["role_id"]))
            if str(eintrag["role_id"]).isdigit() else None
        )
        eintrag["role_name"] = getattr(rolle, "name", "") if rolle else ""
        eintrag["warns"] = await store.count_warns(
            guild_id, int(eintrag["user_id"])
        )

    return {"members": liste, "count": len(liste)}


@router.get("/{guild_id}/warns/{user_id}", summary="Verwarnungen einer Person")
async def warns(
    guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)
    settings = await store.get_settings(guild_id)

    liste = await store.list_warns(guild_id, user_id)
    gueltig = await store.count_warns(
        guild_id, user_id,
        expire_days=int(settings.get("warn_expire_days") or 0),
    )
    return {
        "warns": liste,
        "active": gueltig,
        "threshold": int(settings.get("warn_threshold") or 0),
        "followup": store.followup_due(settings, gueltig),
    }


@router.delete("/{guild_id}/warns/{warn_id}", summary="Verwarnung aufheben")
async def clear_warn(
    guild_id: int, warn_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)

    if not await store.clear_warn(guild_id, warn_id):
        raise HTTPException(404, "Diese Verwarnung gibt es nicht (mehr).")

    await feature_audit.log_action(
        "team_warn_cleared", actor=actor, guild_id=guild_id,
        detail=f"#{warn_id}",
    )
    return {"status": "success"}


@router.delete("/{guild_id}/warns/user/{user_id}",
               summary="Alle Verwarnungen einer Person aufheben")
async def clear_all(
    guild_id: int, user_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)

    anzahl = await store.clear_all_warns(guild_id, user_id)
    await feature_audit.log_action(
        "team_warns_cleared", actor=actor, guild_id=guild_id,
        detail=f"{anzahl} bei {user_id}",
    )
    return {"status": "success", "cleared": anzahl}


@router.post("/{guild_id}/run", summary="Eine Aktion vom Dashboard ausloesen")
async def run(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Dasselbe wie der Slash-Befehl, nur vom Dashboard.

    Ueber denselben Dienst wie die Befehle -- zwei Fassungen desselben
    Ablaufs liefen frueher oder spaeter auseinander, und eine vergaesse
    die Ankuendigung oder den Akteneintrag.
    """
    guild = _guild_or_404(bot, guild_id)

    action = str((data or {}).get("action", ""))
    if action not in store.ACTIONS:
        raise HTTPException(400, f"Unbekannte Aktion: {action}")

    settings = await store.get_settings(guild_id)
    if not settings.get("enabled"):
        raise HTTPException(400, "Das Team-Update ist auf diesem Server aus.")

    user_id = str((data or {}).get("user_id", ""))
    if not user_id.isdigit():
        raise HTTPException(400, "Es fehlt die Nutzer-ID.")

    mitglied = guild.get_member(int(user_id))
    if mitglied is None:
        raise HTTPException(404, "Diese Person ist nicht auf dem Server.")

    grund = str((data or {}).get("reason", ""))
    if settings.get("require_reason") and not grund.strip():
        raise HTTPException(400, "Für diese Aktion ist ein Grund Pflicht.")

    def rolle(schluessel):
        wert = str((data or {}).get(schluessel, ""))
        return guild.get_role(int(wert)) if wert.isdigit() else None

    alt, neu = rolle("old_role_id"), rolle("new_role_id")

    # Dieselbe Vorpruefung wie im Befehl: eine Rolle, die der Bot nicht
    # anfassen kann, wird vorher gemeldet statt hinterher als halb
    # ausgefuehrte Aktion.
    for r in (alt, neu):
        if r is None:
            continue
        hindernis = service._blocked(guild, r)
        if hindernis:
            raise HTTPException(400, hindernis)

    actor = str((data or {}).get("actor", ""))
    unterschriften = [
        int(s) for s in (data or {}).get("signers") or [] if str(s).isdigit()
    ]

    templates = await store.get_templates(guild_id)
    ergebnis = await service.run_action(
        bot, guild, mitglied, action,
        old_role=alt, new_role=neu, reason=grund,
        signers=unterschriften,
        actor_id=int(actor) if actor.isdigit() else None,
        source="dashboard", settings=settings, templates=templates,
    )

    folge = None
    if action == store.ACTION_WARN and ergebnis.followup != store.FOLLOWUP_NONE:
        weiter = await service.apply_followup(
            bot, guild, mitglied, settings, templates, ergebnis,
            actor_id=int(actor) if actor.isdigit() else None,
        )
        folge = weiter.as_dict() if weiter is not None else None

    await feature_audit.log_action(
        f"team_{action}", actor=actor, guild_id=guild_id,
        detail=f"{user_id}: {grund[:200]}",
    )
    return {"status": "success", "result": ergebnis.as_dict(), "followup": folge}
