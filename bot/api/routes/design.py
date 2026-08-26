# ╔══════════════════════════════════════════════════════════════════╗
# ║   Design -- wie der Bot auf diesem Server aussieht               ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Design-Reiter: Nickname, Server-Avatar, Server-Banner.

Nur das Server-Profil
---------------------
Alles hier gilt ausschliesslich auf dem gewaehlten Server. Der globale
Bot-Name bleibt unangetastet -- Discord laesst davon nur zwei
Aenderungen pro Stunde zu, und eine davon traefe alle 154 Server
gleichzeitig.

Wer darf
--------
Premium am Discord-Konto (`product="main_bot"`) UND eine von zwei
Bedingungen:

  * Inhaber des Servers, oder
  * der Server steht auf der Freischaltliste des Admin-Dashboards.

Die Freischaltliste taucht in der Antwort an das Nutzer-Dashboard
nirgends auf -- weder als Feld noch als Text. Fuer den Nutzer sieht
ein freigeschalteter Server genauso aus wie einer, auf dem er Inhaber
ist. Ausdrueckliche Vorgabe.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import guild_design as store
from utils import premium_store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404, detail="Der Bot ist nicht auf diesem Server."
        )
    return guild


def _hat_premium(user_id: str) -> bool:
    """Premium fuer den Hauptbot -- am Konto, nicht am Server."""
    if not str(user_id).isdigit():
        return False
    try:
        zustand = premium_store.status(user_id, product="main_bot")
    except Exception:  # noqa: BLE001 - eine kaputte Tabelle gibt kein Premium
        return False
    return bool(zustand.get("premium"))


def _bild_daten(roh: str, feld: str) -> bytes:
    """Ein Bild aus dem Browser in Bytes verwandeln.

    Erwartet wird eine Data-URL (`data:image/png;base64,...`), so wie
    ein `<input type="file">` sie ueber `FileReader` liefert. Der
    Umweg ueber base64 ist bewusst: der Dashboard-Proxy reicht JSON
    durch, und ein zweiter Weg fuer Formulardaten waere eine weitere
    Stelle, an der etwas schieflaufen kann.
    """
    if not roh.startswith("data:"):
        raise HTTPException(
            status_code=400,
            detail=f"{feld}: erwartet wird ein hochgeladenes Bild.",
        )

    try:
        kopf, nutzdaten = roh.split(",", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{feld}: Bild unlesbar.")

    typ = kopf.split(";")[0].removeprefix("data:").lower()
    if typ not in store.ERLAUBTE_TYPEN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{feld}: {typ or 'unbekanntes Format'} geht nicht. "
                "Erlaubt sind PNG, JPEG, GIF und WebP."
            ),
        )

    try:
        daten = base64.b64decode(nutzdaten, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail=f"{feld}: Bild unlesbar.")

    if not daten:
        raise HTTPException(status_code=400, detail=f"{feld}: Bild ist leer.")
    if len(daten) > store.MAX_IMAGE_BYTES:
        grenze = store.MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"{feld}: höchstens {grenze} MB.",
        )
    return daten


def _aktuelles_aussehen(guild) -> dict:
    """Wie der Bot auf diesem Server GERADE aussieht.

    Das ist die Grundlage der Live-Vorschau: sie zeigt den echten
    Zustand, nicht den gespeicherten. Beides kann auseinanderlaufen,
    wenn jemand den Nickname von Hand in Discord aendert.
    """
    me = getattr(guild, "me", None)
    if me is None:
        return {}

    def _url(wert):
        return str(wert.url) if wert is not None else None

    return {
        "name": getattr(me, "name", ""),
        "display_name": getattr(me, "display_name", ""),
        "nickname": getattr(me, "nick", None),
        # `display_avatar` faellt auf den globalen zurueck, wenn es
        # keinen Server-Avatar gibt -- genau das zeigt Discord auch.
        "avatar": _url(getattr(me, "display_avatar", None)),
        "guild_avatar": _url(getattr(me, "guild_avatar", None)),
        "global_avatar": _url(getattr(getattr(me, "_user", me), "avatar", None)),
        "banner": _url(getattr(me, "guild_banner", None)),
    }


def _weicht_ab(guild) -> dict:
    """Sieht der Bot hier anders aus als im Developer Portal?

    Das Portal-Profil ist das GLOBALE Profil: Name, globaler Avatar,
    kein Server-Banner. Alles, was ein Server-Profil zusaetzlich
    setzt, ist eine Abweichung -- und genau dann soll der Knopf
    „Auf Standard“ erscheinen.

    Gemessen wird am echten Zustand aus Discord, nicht an der eigenen
    Tabelle. Wer den Nickname von Hand in Discord setzt, hat auch
    eine Abweichung, obwohl in der Datenbank nichts steht.
    """
    me = getattr(guild, "me", None)
    if me is None:
        return {"abweichung": False, "felder": []}

    felder = []
    if getattr(me, "nick", None):
        felder.append("nickname")
    if getattr(me, "guild_avatar", None) is not None:
        felder.append("avatar")
    if getattr(me, "guild_banner", None) is not None:
        felder.append("banner")

    return {"abweichung": bool(felder), "felder": felder}


def _rechte(guild) -> dict:
    """Kann der Bot sein eigenes Profil ueberhaupt aendern?

    Den Nickname darf er nur mit „Nickname ändern" setzen. Ohne das
    Recht wird gespeichert und nichts passiert -- der haeufigste Fall
    von „es tut sich nichts".
    """
    me = getattr(guild, "me", None)
    if me is None:
        return {"ok": False, "detail": "Der Bot ist nicht auf dem Server."}

    rechte = getattr(me, "guild_permissions", None)
    if rechte is not None and not getattr(rechte, "change_nickname", False):
        return {
            "ok": False,
            "detail": (
                "Dem Bot fehlt das Recht „Nickname ändern“. Ohne das kann er "
                "seinen Namen auf diesem Server nicht setzen."
            ),
        }
    return {"ok": True, "detail": ""}


async def _antwort(db, guild, record: dict, user_id: str) -> dict:
    """Was das Dashboard bekommt.

    Enthaelt bewusst KEIN Feld darueber, ob der Server freigeschaltet
    wurde. `may_edit` ist ein einzelnes Ja/Nein -- warum, geht das
    Nutzer-Dashboard nichts an.
    """
    premium = _hat_premium(user_id)
    darf = await store.may_edit(db, guild, user_id) if premium else False

    return {
        "guild_id": str(guild.id),
        "premium": premium,
        # Ein einziges Ja/Nein. Weder „owner" noch „unlocked" stehen
        # hier -- sonst waere die Freischaltliste aus dem Browser
        # ablesbar.
        "may_edit": bool(darf),
        "nickname": record.get("nickname"),
        "avatar_url": record.get("avatar_url"),
        "banner_url": record.get("banner_url"),
        "updated_at": record.get("updated_at") or 0,
        "current": _aktuelles_aussehen(guild),
        # Woran das Dashboard erkennt, ob „Auf Standard“ ueberhaupt
        # etwas zu tun haette.
        "deviates": _weicht_ab(guild),
        "permissions": _rechte(guild),
        "limits": {
            "nickname": store.MAX_NICK,
            "image_bytes": store.MAX_IMAGE_BYTES,
            "types": list(store.ERLAUBTE_TYPEN),
        },
        "guild_name": getattr(guild, "name", ""),
        "guild_icon": (
            str(guild.icon.url) if getattr(guild, "icon", None) else None
        ),
    }


# ══════════════════════════════════════════════════════════════════════
#  Freischaltliste -- nur fuers Admin-Dashboard
# ══════════════════════════════════════════════════════════════════════
#
# Diese Routen stehen ABSICHTLICH vor `/{guild_id}`.
#
# Starlette nimmt die erste passende Route. Stuende `/{guild_id}`
# davor, faenge es zwar `/admin/unlocked` nicht ab (weil `guild_id`
# ein int ist und "admin" keiner), aber das ist Zufall: ein spaeterer
# Wechsel auf `str` wuerde die Admin-Routen still unerreichbar
# machen, und der Fehler waere ein 422 statt einer Liste.
#
# Im Nutzer-Dashboard wird die Liste nirgends erwaehnt.


@router.get("/admin/unlocked", summary="Freigeschaltete Server")
async def list_unlocked():
    db = await _db()
    return {"servers": await store.unlocked_list(db)}


@router.post("/admin/unlocked", summary="Server freischalten")
async def add_unlocked(data: dict, bot: "universitybot" = Depends(get_bot)):
    roh = str(data.get("guild_id") or "").strip()
    if not roh.isdigit():
        raise HTTPException(status_code=400, detail="Keine gültige Server-ID.")

    db = await _db()
    await store.unlock(
        db, int(roh),
        by=str(data.get("actor") or "dashboard"),
        note=str(data.get("note") or ""),
    )
    await feature_audit.log_action(
        "design_unlocked",
        actor=str(data.get("actor") or "dashboard"),
        detail=f"guild {roh}",
    )
    return {"servers": await store.unlocked_list(db)}


@router.delete("/admin/unlocked/{guild_id}", summary="Freischaltung zurücknehmen")
async def remove_unlocked(guild_id: int, actor: str = ""):
    db = await _db()
    entfernt = await store.lock(db, guild_id)
    if not entfernt:
        raise HTTPException(status_code=404, detail="Dieser Server war nicht freigeschaltet.")

    await feature_audit.log_action(
        "design_locked", actor=actor or "dashboard", detail=f"guild {guild_id}"
    )
    return {"servers": await store.unlocked_list(db)}


@router.post("/{guild_id}/standard", summary="Zurück auf das Portal-Profil")
async def reset_design(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Server-Nickname, -Avatar und -Banner entfernen.

    Danach sieht der Bot hier wieder genau so aus wie im Developer
    Portal: globaler Name, globaler Avatar, kein Server-Banner.

    Warum eine eigene Route und nicht `POST /{guild_id}` mit lauter
    `null`: dort heisst ein fehlendes Feld „nicht anfassen“, und ein
    `null` im Bildfeld kam im Dashboard nie an -- gemessen in
    `repro/bug_design_reset.py`. Eine Route, deren einziger Zweck das
    Loeschen ist, kann man nicht versehentlich halb ausfuehren.

    Die Bio bleibt aussen vor: Discord bietet keine API, um die
    Beschreibung einer Anwendung zu aendern -- weder global noch pro
    Server. Sie steht nur im Developer Portal.
    """
    import discord

    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    actor = str(data.get("actor") or "")

    if not _hat_premium(actor):
        raise HTTPException(status_code=403, detail="Dafür wird Premium benötigt.")

    if not await store.may_edit(db, guild, actor):
        raise HTTPException(
            status_code=403,
            detail="Das Design darf hier nur der Server-Inhaber ändern.",
        )

    me = getattr(guild, "me", None)
    if me is None:
        raise HTTPException(status_code=400, detail="Der Bot ist nicht erreichbar.")

    # Alle drei auf einmal: ein halb zurueckgesetztes Profil waere
    # schlimmer als gar keins.
    try:
        await me.edit(
            nick=None, avatar=None, banner=None,
            reason=f"Auf Standard zurückgesetzt von {actor}",
        )
    except discord.Forbidden as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Discord hat abgelehnt. Meist fehlt dem Bot das Recht "
                f"„Nickname ändern“. ({exc.text or exc})"
            ),
        ) from exc
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord hat abgelehnt: {exc.text or exc}"
        ) from exc

    record = await store.clear(db, guild_id, actor=actor)

    await feature_audit.log_action(
        "design_reset", actor=actor, detail=f"guild {guild_id}"
    )
    return await _antwort(db, guild, record, actor)


@router.get("/{guild_id}", summary="Design dieses Servers")
async def get_design(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    record = await store.get(db, guild_id)
    return await _antwort(db, guild, record, actor)


@router.post("/{guild_id}", summary="Design ändern")
async def save_design(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Nickname, Server-Avatar und Server-Banner setzen.

    Geaendert wird sofort auf Discord -- eine Vorschau, die nach dem
    Speichern nicht der Wirklichkeit entspricht, waere schlimmer als
    keine.
    """
    import discord

    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    actor = str(data.get("actor") or "")

    if not _hat_premium(actor):
        raise HTTPException(
            status_code=403,
            detail="Dafür wird Premium benötigt.",
        )

    if not await store.may_edit(db, guild, actor):
        # Bewusst dieselbe knappe Auskunft in beiden Faellen: dass es
        # eine Freischaltliste gibt, steht hier nicht.
        raise HTTPException(
            status_code=403,
            detail="Das Design darf hier nur der Server-Inhaber ändern.",
        )

    me = getattr(guild, "me", None)
    if me is None:
        raise HTTPException(status_code=400, detail="Der Bot ist nicht erreichbar.")

    aenderungen: dict = {}
    felder: dict = {}

    if "nickname" in data:
        roh = data["nickname"]
        text = str(roh or "").strip()
        if len(text) > store.MAX_NICK:
            raise HTTPException(
                status_code=400,
                detail=f"Der Name darf höchstens {store.MAX_NICK} Zeichen haben.",
            )
        # Leer heisst: zurueck auf den globalen Namen.
        aenderungen["nick"] = text or None
        felder["nickname"] = text or None

    for schluessel, ziel in (("avatar", "avatar"), ("banner", "banner")):
        if schluessel not in data:
            continue
        roh = data[schluessel]
        if roh in (None, "", "null"):
            aenderungen[ziel] = None
            felder[f"{schluessel}_url"] = None
        else:
            aenderungen[ziel] = _bild_daten(str(roh), schluessel)
            # Die Adresse steht erst nach dem Setzen fest -- Discord
            # vergibt sie. Deshalb wird sie unten nachgetragen.
            felder[f"{schluessel}_url"] = None

    if not aenderungen:
        raise HTTPException(status_code=400, detail="Nichts zu ändern.")

    try:
        await me.edit(**aenderungen, reason=f"Design geändert von {actor}")
    except discord.Forbidden as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Discord hat abgelehnt. Meist fehlt dem Bot das Recht "
                f"„Nickname ändern“, oder der Server hat kein Level für "
                f"Banner. ({exc.text or exc})"
            ),
        ) from exc
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Discord hat abgelehnt: {exc.text or exc}",
        ) from exc

    # Jetzt stehen die Adressen fest.
    frisch = _aktuelles_aussehen(guild)
    if "avatar" in aenderungen:
        felder["avatar_url"] = frisch.get("guild_avatar")
    if "banner" in aenderungen:
        felder["banner_url"] = frisch.get("banner")

    record = await store.save(db, guild_id, actor=actor, **felder)

    await feature_audit.log_action(
        "design_updated",
        actor=actor,
        detail=f"guild {guild_id}: {', '.join(sorted(aenderungen))}",
    )
    return await _antwort(db, guild, record, actor)
