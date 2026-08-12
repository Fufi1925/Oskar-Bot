# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Bewerbungen ueber die Website                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Bewerbungen fuer das Team hinter dem Bot.

  GET    /roles              welche Rollen offen sind, mit Fragen
  GET    /me/{user_id}       die eigene Bewerbung (oder nichts)
  POST   /submit             abgeben -- genau eine pro Person
  POST   /withdraw/{uid}     die eigene zurueckziehen
  GET    /list               alle, fuers Admin-Dashboard
  POST   /decide/{uid}       annehmen oder ablehnen
  DELETE /{uid}              freigeben, damit es ein zweiter Versuch darf
  GET    /config             Einstellungen
  PATCH  /config             Einstellungen sichern

Wer die Bewerbung abgibt, wird nicht hier geprueft: der Proxy im
Dashboard kennt die angemeldete Sitzung und setzt die Nutzer-ID
selbst ein. Diese Route bekommt sie fertig und vertraut ihr -- sie
ist nur ueber den Proxy erreichbar, nicht aus dem Netz.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import web_apply_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/roles", summary="Rollen und ihre Fragen")
async def roles():
    config = await store.get_config()
    out = []
    for eintrag in store.role_list():
        eigene = config["roles"].get(eintrag["key"], {})
        out.append({
            **eintrag,
            "open": bool(eigene.get("open", True)),
            "question_list": store.questions_of(eintrag["key"]),
        })
    return {"roles": out, "min_answer": store.MIN_ANSWER,
            "max_answer": store.MAX_ANSWER}


@router.get("/me/{user_id}", summary="Die eigene Bewerbung")
async def me(user_id: int):
    bewerbung = await store.get_application(user_id)
    return {"application": bewerbung}


@router.post("/submit", summary="Bewerbung abgeben")
async def submit(data: dict, bot: "universitybot" = Depends(get_bot)):
    user_id = str((data or {}).get("user_id", ""))
    if not user_id.isdigit():
        raise HTTPException(401, "Nicht angemeldet.")

    rolle = str((data or {}).get("role_key", ""))
    config = await store.get_config()
    if not config["roles"].get(rolle, {}).get("open", True):
        raise HTTPException(400, "Für diese Rolle nehmen wir gerade niemanden auf.")

    try:
        bewerbung = await store.submit(
            int(user_id),
            str((data or {}).get("user_name", "")),
            str((data or {}).get("avatar", "")),
            rolle,
            list((data or {}).get("answers") or []),
        )
    except store.AlreadyApplied as exc:
        vorhanden = exc.existing
        # 409, nicht 400: das ist kein Fehler in der Eingabe, sondern
        # ein Zustand. Das Dashboard zeigt daraufhin die Nummer und
        # den Fortschritt statt einer roten Fehlermeldung.
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Du hast schon eine Bewerbung laufen. Bitte hab noch "
                    "etwas Geduld — das ist deine Bewerbungsnummer, links "
                    "siehst du deinen Fortschritt."
                ),
                "ticket": vorhanden["ticket"],
                "status": vorhanden["status"],
                "role_label": vorhanden["role_label"],
                "application": vorhanden,
            },
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Das Team benachrichtigen, falls ein Kanal eingestellt ist.
    await _melden(bot, bewerbung, config)

    await feature_audit.log_action(
        "web_application", actor=user_id, detail=f"{rolle} ({bewerbung['ticket']})"
    )
    return {"status": "success", "application": bewerbung}


async def _melden(bot, bewerbung: dict, config: dict) -> None:
    """Eine Karte in den eingestellten Kanal.

    Scheitert das, ist die Bewerbung trotzdem gespeichert -- deshalb
    faengt diese Funktion alles ab und wirft nie.
    """
    kanal_id = config.get("channel_id") or ""
    if not kanal_id.isdigit():
        return
    try:
        from utils.panels import Panel

        kanal = bot.get_channel(int(kanal_id))
        if kanal is None:
            return
        await kanal.send(view=Panel(
            f"Neue Bewerbung: {bewerbung['role_label']}",
            f"**{bewerbung['user_name']}** (<@{bewerbung['user_id']}>)\n"
            f"Nummer: `{bewerbung['ticket']}`\n\n"
            f"Im Dashboard unter »Bewerbungen« ansehen und entscheiden.",
            accent=0x5865F2,
        ))
    except Exception as exc:
        logger.warning(f"[webapply] Meldung fehlgeschlagen: {exc}")


@router.post("/withdraw/{user_id}", summary="Eigene Bewerbung zurueckziehen")
async def withdraw(user_id: int):
    if not await store.withdraw(user_id):
        raise HTTPException(400, "Da ist keine offene Bewerbung.")
    return {"status": "success"}


@router.get("/list", summary="Alle Bewerbungen")
async def liste(status: str = "", limit: int = 200):
    return {
        "applications": await store.list_applications(status, limit),
        "counts": await store.counts(),
    }


@router.post("/decide/{user_id}", summary="Annehmen oder ablehnen")
async def decide(
    user_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    status = str((data or {}).get("status", ""))
    if status not in (store.STATUS_ACCEPTED, store.STATUS_DENIED):
        raise HTTPException(400, "Nur annehmen oder ablehnen.")

    grund = str((data or {}).get("reason", "")).strip()
    if not grund:
        raise HTTPException(400, "Bitte einen Grund angeben.")

    vorher = await store.get_application(user_id)
    if vorher is None:
        raise HTTPException(404, "Diese Bewerbung gibt es nicht.")

    config = await store.get_config()
    rollen_id = config["roles"].get(vorher["role_key"], {}).get("discord_role_id", "")
    # Der Server kann je Bewerbungsrolle ein anderer sein -- Tester
    # auf den Test-Server, Moderatoren auf den Support-Server.
    server_id = store.guild_for(config, vorher["role_key"])

    bewerbung = await store.decide(
        user_id, status,
        str((data or {}).get("actor", "")),
        str((data or {}).get("actor_name", "")),
        grund,
        rollen_id if status == store.STATUS_ACCEPTED else "",
    )
    if bewerbung is None:
        raise HTTPException(
            409, "Über diese Bewerbung wurde inzwischen schon entschieden."
        )

    # Die Rolle vergeben. Scheitert das, bleibt die Entscheidung
    # trotzdem stehen -- gemeldet wird es aber.
    vergeben, problem = False, ""
    if status == store.STATUS_ACCEPTED and rollen_id.isdigit():
        vergeben, problem = await _rolle_geben(
            bot, server_id, user_id, rollen_id
        )

    zugestellt = False
    if config.get("dm_applicant"):
        zugestellt = await _dm(bot, user_id, bewerbung, status)

    await feature_audit.log_action(
        f"web_application_{status}",
        actor=str((data or {}).get("actor", "")),
        detail=f"{bewerbung['ticket']}: {grund[:200]}",
    )
    return {
        "status": "success",
        "application": bewerbung,
        "role_granted": vergeben,
        "role_problem": problem,
        "dm_delivered": zugestellt,
    }


async def _rolle_geben(bot, guild_id: str, user_id: int, role_id: str):
    """Die Rolle im Support-Server vergeben.

    Gibt ``(geklappt, problem)`` zurueck. Die Rollenordnung wird
    vorher geprueft: Discord lehnt sonst mit 403 ab, und der Grund
    steht nur im Log.
    """
    import discord

    if not str(guild_id).isdigit():
        return False, "Es ist kein Server eingestellt."
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return False, "Der Bot ist nicht auf dem eingestellten Server."

    rolle = guild.get_role(int(role_id))
    if rolle is None:
        return False, "Die eingestellte Rolle gibt es nicht mehr."
    if guild.me is not None and rolle >= guild.me.top_role:
        return False, f"{rolle.name} steht über der Rolle des Bots."

    mitglied = guild.get_member(int(user_id))
    if mitglied is None:
        try:
            mitglied = await guild.fetch_member(int(user_id))
        except discord.HTTPException:
            return False, "Die Person ist nicht auf dem Server."

    try:
        await mitglied.add_roles(rolle, reason="Team-Bewerbung angenommen")
        return True, ""
    except discord.Forbidden:
        return False, "Dem Bot fehlt das Recht, Rollen zu vergeben."
    except discord.HTTPException as exc:
        return False, str(exc)


async def _dm(bot, user_id: int, bewerbung: dict, status: str) -> bool:
    import discord

    from utils.cv2 import CV2

    try:
        nutzer = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
    except discord.HTTPException:
        return False
    if nutzer is None:
        return False

    angenommen = status == store.STATUS_ACCEPTED
    try:
        await nutzer.send(view=CV2(
            "Bewerbung angenommen" if angenommen else "Bewerbung abgelehnt",
            f"Deine Bewerbung als **{bewerbung['role_label']}** "
            f"({bewerbung['ticket']}) wurde "
            f"{'angenommen' if angenommen else 'abgelehnt'}.\n\n"
            f"**Begründung:**\n{bewerbung['reason']}",
        ))
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


@router.delete("/{user_id}", summary="Bewerbung freigeben")
async def freigeben(user_id: int, actor: str = ""):
    """Loeschen, damit die Person es erneut versuchen darf."""

    if not await store.reopen(user_id):
        raise HTTPException(404, "Diese Bewerbung gibt es nicht.")
    await feature_audit.log_action(
        "web_application_reopen", actor=actor, detail=str(user_id)
    )
    return {"status": "success"}


@router.get("/config", summary="Einstellungen")
async def get_config(bot: "universitybot" = Depends(get_bot)):
    config = await store.get_config()

    def rollen_von(guild) -> list[dict]:
        """Die vergebbaren Rollen eines Servers, von oben nach unten."""
        out = []
        ich = getattr(guild, "me", None)
        oben = getattr(ich, "top_role", None) if ich else None
        for rolle in sorted(getattr(guild, "roles", []),
                            key=lambda r: getattr(r, "position", 0),
                            reverse=True):
            if rolle.is_default() or rolle.managed:
                continue
            out.append({
                "id": str(rolle.id),
                "name": rolle.name,
                # Steht sie ueber der Bot-Rolle, laesst sie sich nicht
                # vergeben. Das Dashboard zeigt es an, statt es beim
                # ersten Annehmen herauszufinden.
                "assignable": bool(oben is None or rolle < oben),
            })
        return out

    # Jeder Server, auf dem der Bot ist -- damit sich je
    # Bewerbungsrolle ein anderer auswaehlen laesst.
    server: list[dict] = []
    rollen_je_server: dict[str, list[dict]] = {}
    for guild in getattr(bot, "guilds", []) or []:
        gid = str(guild.id)
        server.append({
            "id": gid,
            "name": guild.name,
            "members": getattr(guild, "member_count", 0) or 0,
        })
        rollen_je_server[gid] = rollen_von(guild)
    server.sort(key=lambda g: -g["members"])

    # Der allgemeine Server: seine Rollen und Kanaele wie bisher,
    # damit ein Server, der nichts Eigenes eingestellt hat, weiter
    # funktioniert.
    rollen: list[dict] = []
    kanaele: list[dict] = []
    guild_id = config.get("guild_id") or ""
    if guild_id.isdigit():
        guild = bot.get_guild(int(guild_id))
        if guild is not None:
            rollen = rollen_je_server.get(guild_id, rollen_von(guild))
            for kanal in getattr(guild, "text_channels", []):
                kanaele.append({"id": str(kanal.id), "name": kanal.name})

    # Wohin jede Bewerbungsrolle tatsaechlich vergibt -- damit das
    # Dashboard es anzeigen kann, ohne dieselbe Regel nachzubauen.
    ziel = {k: store.guild_for(config, k) for k in store.ROLE_KEYS}

    return {**config, "available_roles": rollen, "available_channels": kanaele,
            "role_catalog": store.role_list(), "guilds": server,
            "roles_by_guild": rollen_je_server, "effective_guild": ziel}


@router.patch("/config", summary="Einstellungen sichern")
async def patch_config(data: dict):
    return {"status": "success", "config": await store.save_config(data or {})}
