"""
Speedrun: einen Server in einem Rutsch aufbauen.

Das Dashboard redet nur mit dem University Bot, nie direkt mit dem
Template-Bot. Zwei Gruende:

  * Die Absicherung steht hier schon. Jede /api/v1-Route haengt hinter
    verify_api_key; der Template-Bot muesste sonst eine zweite,
    parallele Zugangspruefung bekommen.
  * Der Browser darf den Partner-Token nie sehen. Wuerde das Dashboard
    den Template-Bot direkt aufrufen, muesste der Token entweder in den
    Browser oder in eine zweite Proxy-Schicht -- diese Route ist die
    zweite Schicht.

Der Ablauf in Stufen, wie ihn das Dashboard abbildet:

  1. /precheck   Sind beide Bots auf dem Server?
  2. /templates  Welche Templates darf dieser Nutzer waehlen?
  3. /start      Template-Bot baut. Antwortet sofort.
  4. /{id}       Fortschritt, Zeile fuer Zeile, fuers Terminal.

Die Uebergabe an den University Bot -- Verify, Anti-Nuke, Tickets --
kommt als zweiter Schritt. Was hier schon vorbereitet ist: der Bau
sammelt am Ende alle Rollen- und Kanalnamen ein, damit der Hauptbot
danach nicht raten muss.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import premium_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

PARTNER_TOKEN_ENV = "PREMIUM_PARTNER_TOKEN"

# Beta: nur dieses eine Template ist freigeschaltet -- auch fuer
# Premium. Die anderen neun sind gebaut, aber noch nicht durch einen
# echten Server gelaufen, und ein halb geprueftes Template auf einem
# fremden Server anzuwenden ist nicht rueckgaengig zu machen.
BETA_TEMPLATES = {"community"}


def _template_base() -> str:
    return (os.getenv("TEMPLATE_BOT_URL") or "").strip().rstrip("/")


def _partner_token() -> str:
    return os.getenv(PARTNER_TOKEN_ENV, "").strip()


def _require_link() -> tuple[str, str]:
    """Adresse und Token, oder eine klare Fehlermeldung."""

    base = _template_base()
    token = _partner_token()
    if not base or not token:
        missing = []
        if not base:
            missing.append("TEMPLATE_BOT_URL")
        if not token:
            missing.append(PARTNER_TOKEN_ENV)
        raise HTTPException(
            status_code=503,
            detail=(
                "Die Verbindung zum Template-Bot ist nicht eingerichtet. "
                f"Fehlt in Railway: {', '.join(missing)}."
            ),
        )
    return base, token


async def _call_template(
    method: str, path: str, *, payload: dict | None = None, timeout: int = 15
) -> tuple[int, Any]:
    """Eine Anfrage an den Template-Bot.

    Netzwerkfehler werden zu 502 statt zu einem Traceback: das
    Dashboard soll "Template-Bot nicht erreichbar" anzeigen koennen,
    nicht eine leere Seite.
    """

    base, token = _require_link()
    url = f"{base}{path}"
    headers = {"X-Partner-Token": token}

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.request(
                method, url, headers=headers, json=payload
            ) as response:
                try:
                    body = await response.json()
                except Exception:
                    body = {"error": (await response.text())[:200]}
                return response.status, body
    except aiohttp.ClientError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Template-Bot nicht erreichbar: {exc}",
        ) from exc
    except Exception as exc:  # Timeout und alles Uebrige
        raise HTTPException(
            status_code=502,
            detail=f"Template-Bot antwortet nicht: {type(exc).__name__}",
        ) from exc


def _has_premium(user_id: str) -> bool:
    if not user_id:
        return False
    try:
        state = store.status(user_id, product="template_bot")
        return bool(state.get("active"))
    except Exception:
        # Im Zweifel kein Premium: eine kaputte Abfrage darf niemandem
        # etwas freischalten, das er nicht bezahlt hat.
        return False


# --------------------------------------------------------------------- #
# 1. Vorbedingungen
# --------------------------------------------------------------------- #


@router.get("/{guild_id}/precheck", summary="Sind beide Bots bereit?")
async def precheck(
    guild_id: int,
    user_id: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    """
    Prueft alles, was vor dem ersten Klick stimmen muss.

    Jede Bedingung kommt einzeln zurueck, damit das Dashboard genau
    sagen kann, was fehlt -- "irgendetwas stimmt nicht" ist die
    nutzloseste aller Fehlermeldungen.
    """

    guild = bot.get_guild(guild_id)
    main_present = guild is not None

    # Rechte des University Bots. Ohne die scheitert Schritt 2 mitten
    # drin, und dann steht der Server halb eingerichtet da.
    main_can_manage = False
    if guild is not None and guild.me is not None:
        perms = guild.me.guild_permissions
        main_can_manage = bool(
            perms.administrator
            or (perms.manage_roles and perms.manage_channels)
        )

    # Der Template-Bot wird gefragt, ob *er* auf dem Server ist -- das
    # kann der University Bot nicht von sich aus wissen.
    template_present = False
    template_reachable = False
    template_detail = ""
    try:
        status_code, body = await _call_template(
            "POST",
            "/internal/speedrun/precheck",
            payload={"guild_id": str(guild_id)},
            timeout=10,
        )
        template_reachable = True
        if status_code == 200:
            template_present = bool(body.get("present"))
            template_detail = str(body.get("detail") or "")
        else:
            template_detail = str(body.get("error") or f"HTTP {status_code}")
    except HTTPException as exc:
        template_detail = str(exc.detail)

    premium = _has_premium(str(user_id or ""))

    ready = main_present and main_can_manage and template_present

    return {
        "ready": ready,
        "checks": {
            "main_bot_present": main_present,
            "main_bot_can_manage": main_can_manage,
            "template_bot_present": template_present,
            "template_bot_reachable": template_reachable,
        },
        "premium": premium,
        "guild_name": getattr(guild, "name", ""),
        "detail": template_detail,
        # Die Einladung, damit das Dashboard direkt einen Knopf anbieten
        # kann statt "lade den Bot halt ein".
        "template_invite": _template_invite(),
    }


def _template_invite() -> str:
    client_id = (os.getenv("PARTNER_BOT_CLIENT_ID") or "").strip()
    if not client_id:
        return ""
    return (
        f"https://discord.com/oauth2/authorize?client_id={client_id}"
        "&scope=bot%20applications.commands&permissions=8"
    )


# --------------------------------------------------------------------- #
# 2. Templates
# --------------------------------------------------------------------- #


@router.get("/templates", summary="Waehlbare Templates")
async def templates(user_id: str = ""):
    """
    Die Template-Liste, angereichert um "darf dieser Nutzer das?".

    Die Sperre wird hier entschieden und nicht im Dashboard: eine
    Prüfung, die nur im Browser stattfindet, ist keine.
    """

    status_code, body = await _call_template(
        "GET", "/internal/speedrun/templates", timeout=10
    )
    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )

    premium = _has_premium(str(user_id or ""))
    items = []
    for entry in body.get("templates", []):
        key = str(entry.get("key") or "")
        in_beta = key in BETA_TEMPLATES

        if not in_beta:
            reason = "In der Beta ist erst dieses eine Template freigegeben."
        elif entry.get("premium") and not premium:
            reason = "Nur mit Premium."
        else:
            reason = ""

        items.append({**entry, "available": not reason, "locked_reason": reason})

    return {"templates": items, "premium": premium, "beta": sorted(BETA_TEMPLATES)}


# --------------------------------------------------------------------- #
# 3. Start
# --------------------------------------------------------------------- #


@router.post("/{guild_id}/start", summary="Speedrun starten")
async def start(
    guild_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """Startet den Bau beim Template-Bot. Antwortet sofort."""

    template_key = str(data.get("template") or "").strip()
    user_id = str(data.get("user_id") or "").strip()

    if template_key not in BETA_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"»{template_key}« ist in der Beta nicht freigegeben. "
                f"Verfügbar: {', '.join(sorted(BETA_TEMPLATES))}."
            ),
        )

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der University Bot ist nicht auf diesem Server.",
        )

    status_code, body = await _call_template(
        "POST",
        "/internal/speedrun/start",
        payload={
            "guild_id": str(guild_id),
            "template": template_key,
            "options": data.get("options") or {},
            "user_id": user_id,
        },
        timeout=20,
    )

    if status_code != 200:
        raise HTTPException(
            status_code=status_code if status_code in (400, 404, 409) else 502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )

    return body


# --------------------------------------------------------------------- #
# 4. Fortschritt
# --------------------------------------------------------------------- #


@router.get("/{guild_id}/status", summary="Fortschritt abholen")
async def status_route(guild_id: int, since: int = 0):
    """Reicht den Fortschritt durch. ``since`` = schon gelesene Zeilen."""

    status_code, body = await _call_template(
        "GET",
        f"/internal/speedrun/{guild_id}?since={max(since, 0)}",
        timeout=10,
    )
    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )
    return body
