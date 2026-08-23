# ╔══════════════════════════════════════════════════════════════════╗
# ║   Honeypot -- Routen                                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Honeypot im Dashboard: einschalten, fertig.

Beim Einschalten legt der Bot den Kanal selbst an und schiebt ihn
ganz nach oben. Alles Weitere ist freiwillig: eigener Kanal statt des
angelegten, Log-Kanal, eigener Text, Rollen-Whitelist.

Warum das Einschalten hier passiert und nicht im Browser
--------------------------------------------------------
Einen Kanal anzulegen, Rechte zu setzen und ihn auf Position 0 zu
schieben, geht nur mit dem Bot-Token. Der Browser hat es nicht -- und
soll es nicht haben.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import honeypot as store

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


def _cog(bot):
    """Der Cog macht die Arbeit -- er hat den Discord-Zugriff.

    Fehlt er, ist der Bot noch nicht fertig geladen. Dann eine klare
    Meldung statt eines Absturzes.
    """
    cog = bot.get_cog("Honeypot")
    if cog is None:
        raise HTTPException(
            status_code=503,
            detail="Der Honeypot-Teil des Bots ist noch nicht bereit.",
        )
    return cog


def _text_channels(guild) -> list[dict]:
    """Textkanaele -- mit der Frage, ob der Bot darin schreiben darf.

    Die Angabe steht dabei, weil ein Log-Kanal ohne Schreibrecht der
    haeufigste Fall von „es kommt nichts an" ist, und man ihn der
    Einstellung sonst nicht ansieht.
    """
    eintraege = []
    me = getattr(guild, "me", None)
    for kanal in getattr(guild, "text_channels", []):
        darf = False
        if me is not None:
            try:
                rechte = kanal.permissions_for(me)
                darf = bool(rechte.view_channel and rechte.send_messages)
            except Exception:  # noqa: BLE001
                pass
        eintraege.append({
            "id": str(kanal.id),
            "name": kanal.name,
            "category": kanal.category.name if kanal.category else None,
            "can_send": darf,
        })
    return eintraege


def _roles(guild) -> list[dict]:
    """Rollen fuer die Whitelist -- ohne @everyone.

    @everyone waere sinnlos: sie hat jeder, die Falle waere aus.
    """
    eintraege = []
    for rolle in getattr(guild, "roles", []):
        if getattr(rolle, "is_default", lambda: False)():
            continue
        eintraege.append({
            "id": str(rolle.id),
            "name": rolle.name,
            "position": getattr(rolle, "position", 0),
        })
    eintraege.sort(key=lambda e: -e["position"])
    return eintraege


def _kann_bannen(guild) -> dict:
    """Darf der Bot ueberhaupt bannen?

    Ohne das Recht laeuft der Honeypot ins Leere: der Koeder steht da,
    aber nichts passiert. Und weil bei einem Fehlschlag ausdruecklich
    **nichts** gemeldet wird, saehe man es sonst nirgends.
    """
    me = getattr(guild, "me", None)
    if me is None:
        return {"ok": False, "detail": "Der Bot ist nicht auf dem Server."}
    if not me.guild_permissions.ban_members:
        return {
            "ok": False,
            "detail": (
                "Dem Bot fehlt das Recht „Mitglieder bannen“. Ohne das "
                "passiert bei einem Treffer nichts."
            ),
        }
    if not me.guild_permissions.manage_channels:
        return {
            "ok": True,
            "detail": (
                "Der Bot darf bannen, aber keine Kanäle verwalten — er kann "
                "den Köder-Kanal nicht selbst anlegen. Wähle unten einen "
                "eigenen Kanal."
            ),
        }
    return {"ok": True, "detail": ""}


def _antwort(guild, record: dict) -> dict:
    """Die Einstellungen, angereichert um das, was der Browser nicht weiss."""
    kanal_name = None
    if record.get("channel_id"):
        gefunden = guild.get_channel(int(record["channel_id"]))
        kanal_name = gefunden.name if gefunden is not None else None

    return {
        **record,
        # IDs immer als Zeichenkette. Eine Discord-ID ist groesser als
        # das, was JavaScript als Zahl noch genau darstellen kann --
        # sonst kommt eine um eins verschobene ID im Browser an.
        "channel_id": (
            str(record["channel_id"]) if record.get("channel_id") else None
        ),
        "message_id": (
            str(record["message_id"]) if record.get("message_id") else None
        ),
        "custom_channel_id": (
            str(record["custom_channel_id"])
            if record.get("custom_channel_id") else None
        ),
        "log_channel_id": (
            str(record["log_channel_id"])
            if record.get("log_channel_id") else None
        ),
        "whitelist_roles": [str(r) for r in record.get("whitelist_roles", [])],
        "channel_name": kanal_name,
        "channel_missing": bool(record.get("channel_id")) and kanal_name is None,
        "channels": _text_channels(guild),
        "roles": _roles(guild),
        "permissions": _kann_bannen(guild),
        "defaults": {
            "channel_name": store.DEFAULT_CHANNEL_NAME,
            "title": store.DEFAULT_TITLE,
            "text": store.DEFAULT_TEXT,
            "delete_days": store.DEFAULT_DELETE_DAYS,
        },
        "limits": {
            "title": store.MAX_TITLE,
            "text": store.MAX_TEXT,
            "delete_days": store.MAX_DELETE_DAYS,
        },
    }


@router.get("/{guild_id}", summary="Honeypot-Einstellungen")
async def get_settings(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    record = await store.get(await _db(), guild_id)
    return _antwort(guild, record)


@router.patch("/{guild_id}", summary="Honeypot einstellen")
async def patch_settings(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    vorher = await store.get(db, guild_id)

    felder: dict = {}

    if "title" in data:
        felder["title"] = data["title"]
    if "text" in data:
        felder["text"] = data["text"]
    if "delete_days" in data:
        felder["delete_days"] = data["delete_days"]

    for schluessel in ("custom_channel_id", "log_channel_id"):
        if schluessel in data:
            roh = data[schluessel]
            if roh in (None, "", "0"):
                felder[schluessel] = None
            else:
                if not str(roh).isdigit():
                    raise HTTPException(
                        status_code=400, detail=f"{schluessel} ist keine gültige ID."
                    )
                if guild.get_channel(int(roh)) is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Diesen Kanal gibt es auf dem Server nicht.",
                    )
                felder[schluessel] = int(roh)

    if "whitelist_roles" in data:
        roh = data["whitelist_roles"] or []
        if not isinstance(roh, (list, tuple)):
            raise HTTPException(
                status_code=400, detail="whitelist_roles muss eine Liste sein."
            )
        gueltig = []
        for eintrag in roh:
            if not str(eintrag).isdigit():
                continue
            if guild.get_role(int(eintrag)) is not None:
                gueltig.append(int(eintrag))
        felder["whitelist_roles"] = gueltig

    record = await store.save(db, guild_id, **felder) if felder else vorher

    # Laeuft der Honeypot bereits, muss die Nachricht die Aenderung
    # sofort zeigen -- sonst steht im Kanal weiter der alte Text und
    # niemand weiss, ob das Speichern gewirkt hat.
    if record.get("enabled") and record.get("channel_id"):
        try:
            await _cog(bot).sende_oder_aktualisiere(guild, record)
        except HTTPException:
            pass

    await feature_audit.log_action(
        "honeypot_updated",
        actor=str(data.get("actor", "dashboard")),
        detail=f"guild {guild_id}",
    )
    return _antwort(guild, record)


@router.post("/{guild_id}/toggle", summary="Honeypot ein- oder ausschalten")
async def toggle(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Einschalten legt den Kanal an, Ausschalten laesst ihn stehen.

    Der Kanal wird bewusst **nicht** geloescht: er kann inzwischen
    Verlauf enthalten, und ein Modul, das beim Ausschalten einen Kanal
    entfernt, ist eine unangenehme Ueberraschung. Beim naechsten
    Einschalten wird er wiedererkannt und weiterbenutzt.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    an = bool(data.get("enabled"))

    if not an:
        record = await store.save(db, guild_id, enabled=False)
        await feature_audit.log_action(
            "honeypot_disabled",
            actor=str(data.get("actor", "dashboard")),
            detail=f"guild {guild_id}",
        )
        return _antwort(guild, record)

    ergebnis = await _cog(bot).aktiviere(guild)
    if not ergebnis.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=(
                ergebnis.get("grund")
                or "Der Köder-Kanal konnte nicht angelegt werden."
            ),
        )

    record = await store.get(db, guild_id)
    await feature_audit.log_action(
        "honeypot_enabled",
        actor=str(data.get("actor", "dashboard")),
        detail=f"guild {guild_id}, Kanal {ergebnis.get('channel_id')}",
    )
    return _antwort(guild, record)


@router.post("/{guild_id}/resend", summary="Köder-Nachricht neu senden")
async def resend(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """Falls die Nachricht geloescht wurde."""
    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    record = await store.get(db, guild_id)

    if not record.get("enabled"):
        raise HTTPException(
            status_code=400, detail="Der Honeypot ist ausgeschaltet."
        )

    nachricht = await _cog(bot).sende_oder_aktualisiere(guild, record)
    if nachricht is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Die Nachricht konnte nicht gesendet werden. "
                "Darf der Bot dort schreiben?"
            ),
        )

    return _antwort(guild, await store.get(db, guild_id))
