# ╔══════════════════════════════════════════════════════════════════╗
# ║   Sicherungen -- ein Knopf, eine Kennung                         ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Backup-Reiter im Nutzer-Dashboard.

Ein Knopf legt eine Sicherung an -- keine Rueckfragen, keine
Auswahlfelder. Was hineingehoert, steht fest: Aufbau des Servers und
Dashboard-Einstellungen.

Grenzen
-------
Gratis eine Sicherung, mit Premium zehn. Wer ohne Premium eine zweite
will, loescht die erste -- das sagt die Fehlermeldung auch.

Warum das Erstellen im Hintergrund laeuft
-----------------------------------------
Mit Nachrichten dauert es Minuten: 500 Stueck bei 50 Kanaelen sind
250 Anfragen an Discord, und die Schnittstelle bremst. Ein Browser,
der so lange auf eine Antwort wartet, laeuft in einen Zeitfehler.
Deshalb antwortet die Route sofort mit einer Kennung, und der Bot
arbeitet weiter.

Ohne Nachrichten ist es in Sekunden fertig -- dann wird trotzdem
derselbe Weg genommen, damit es nur einen gibt.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import backup_runner
from utils import feature_audit
from utils import guild_backup as store
from utils import premium_store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


# Laufende Arbeiten je Server.
#
# `asyncio` haelt auf Tasks nur schwache Referenzen -- ohne dieses
# Dict koennte die Speicherbereinigung einen laufenden Lauf
# einsammeln. Derselbe Grund wie beim Speedrun.
_LAEUFT: dict[int, dict[str, Any]] = {}
_TASKS: dict[int, asyncio.Task] = {}


def _hat_premium(user_id: str) -> bool:
    if not str(user_id).isdigit():
        return False
    try:
        return bool(premium_store.status(user_id).get("premium"))
    except Exception:  # noqa: BLE001 - eine kaputte Tabelle gibt kein Premium
        return False


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404, detail="Der Bot ist nicht auf diesem Server."
        )
    return guild


def _zustand(guild_id: int) -> dict[str, Any]:
    lauf = _LAEUFT.get(int(guild_id))
    if not lauf:
        return {"aktiv": False, "schritt": "", "art": ""}
    return {
        "aktiv": True,
        "schritt": lauf.get("schritt", ""),
        "art": lauf.get("art", ""),
        "seit": lauf.get("seit", 0),
    }


@router.get("/{guild_id}", summary="Sicherungen dieses Servers")
async def uebersicht(guild_id: int, actor: str = "",
                     bot: "universitybot" = Depends(get_bot)):
    _guild_or_404(bot, guild_id)
    premium = _hat_premium(actor)

    return {
        "guild_id": str(guild_id),
        "premium": premium,
        "backups": store.liste(guild_id),
        "grenze": store.grenze(premium),
        "auto": store.auto_zustand(guild_id),
        "limits": {
            "gratis": store.MAX_GRATIS,
            "premium": store.MAX_PREMIUM,
            "nachrichten": store.MAX_NACHRICHTEN,
            "min_auto_stunden": store.MIN_AUTO_STUNDEN,
        },
        "lauf": _zustand(guild_id),
    }


async def _arbeite(bot, guild, guild_id: int, *, actor: str,
                   mit_nachrichten: bool, quelle: str = "hand") -> None:
    """Die eigentliche Sicherung -- im Hintergrund."""

    def melde(text: str) -> None:
        eintrag = _LAEUFT.get(guild_id)
        if eintrag is not None:
            eintrag["schritt"] = text

    try:
        inhalt = await backup_runner.erstelle(
            bot, guild,
            mit_nachrichten=mit_nachrichten,
            max_nachrichten=store.MAX_NACHRICHTEN,
            fortschritt=melde,
        )
        eintrag = store.speichere(
            guild_id, inhalt,
            erstellt_von=actor,
            quelle=quelle,
            mit_nachrichten=mit_nachrichten,
        )
        await feature_audit.log_action(
            "backup_created", actor=actor,
            detail=f"guild {guild_id}: {eintrag['kennung']}",
        )
    except Exception as exc:  # noqa: BLE001
        eintrag = _LAEUFT.get(guild_id)
        if eintrag is not None:
            eintrag["fehler"] = str(exc)
        await feature_audit.log_action(
            "backup_failed", actor=actor,
            detail=f"guild {guild_id}: {exc}",
        )
    finally:
        _LAEUFT.pop(guild_id, None)
        _TASKS.pop(guild_id, None)


@router.post("/{guild_id}/create", summary="Sicherung anlegen")
async def anlegen(guild_id: int, data: dict,
                  bot: "universitybot" = Depends(get_bot)):
    """Ein Knopf, keine Rueckfragen.

    Einzige Ausnahme: Nachrichten. Die kosten Minuten statt Sekunden,
    und das muss man wollen -- deshalb ein eigenes Ja/Nein davor, und
    nur mit Premium.
    """
    guild = _guild_or_404(bot, guild_id)
    actor = str(data.get("actor") or "")
    premium = _hat_premium(actor)

    if guild_id in _LAEUFT:
        raise HTTPException(
            status_code=409,
            detail="Für diesen Server läuft schon eine Sicherung.",
        )

    vorhanden = store.anzahl(guild_id)
    erlaubt = store.grenze(premium)
    if vorhanden >= erlaubt:
        if premium:
            detail = (
                f"Mehr als {erlaubt} Sicherungen gehen nicht. Lösche eine "
                "alte, dann geht es weiter."
            )
        else:
            detail = (
                "Ohne Premium ist eine Sicherung möglich. Lösche die "
                "vorhandene, oder hol dir Premium für bis zu "
                f"{store.MAX_PREMIUM}."
            )
        raise HTTPException(status_code=409, detail=detail)

    mit_nachrichten = bool(data.get("mit_nachrichten"))
    if mit_nachrichten and not premium:
        raise HTTPException(
            status_code=403,
            detail="Nachrichten sichern geht nur mit Premium.",
        )

    _LAEUFT[guild_id] = {
        "schritt": "Wird vorbereitet",
        "art": "erstellen",
        "seit": int(time.time()),
    }
    # Die Referenz festhalten: `asyncio` haelt auf Tasks nur schwache.
    _TASKS[guild_id] = asyncio.create_task(
        _arbeite(bot, guild, guild_id, actor=actor,
                 mit_nachrichten=mit_nachrichten)
    )

    return {"status": "gestartet", "lauf": _zustand(guild_id)}


# Ab hier: feste Pfade VOR den Mustern.
#
# Starlette nimmt die erste passende Route. Stuende
# `/{guild_id}/{kennung}` davor, faenge es `/status` und `/auto`
# mit ab -- „status" ist eine gueltige Zeichenkette und passt auf
# `{kennung}`. Heute rettet die Methode (DELETE gegen GET), aber
# das ist Zufall: die naechste GET-Route unter `/{kennung}` waere
# still unerreichbar.


@router.get("/{guild_id}/status", summary="Läuft gerade etwas?")
async def lauf_status(guild_id: int):
    """Der Fortschritt -- kein Protokoll, nur der aktuelle Schritt.

    Ausdrueckliche Vorgabe: keine Live-Logs. Ein Satz reicht, damit
    man sieht, dass etwas passiert.
    """
    return _zustand(guild_id)


@router.post("/{guild_id}/auto", summary="Automatische Sicherung einstellen")
async def auto(guild_id: int, data: dict,
               bot: "universitybot" = Depends(get_bot)):
    """Nur mit Premium.

    Die Pruefung steht hier und nicht nur im Browser: eine Sperre, die
    allein im Dashboard sitzt, ist keine.
    """
    _guild_or_404(bot, guild_id)
    actor = str(data.get("actor") or "")

    if not _hat_premium(actor):
        raise HTTPException(
            status_code=403,
            detail="Automatische Sicherungen gibt es mit Premium.",
        )

    felder: dict[str, Any] = {}
    for name in ("aktiv", "alte_loeschen", "mit_nachrichten"):
        if name in data:
            felder[name] = bool(data[name])
    if "stunden" in data:
        try:
            felder["stunden"] = int(data["stunden"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="stunden muss eine Zahl sein."
            )

    zustand = store.auto_setze(guild_id, **felder)

    await feature_audit.log_action(
        "backup_auto_changed", actor=actor,
        detail=f"guild {guild_id}: {zustand}",
    )
    return {"status": "ok", "auto": zustand}


@router.delete("/{guild_id}/{kennung}", summary="Sicherung löschen")
async def entfernen(guild_id: int, kennung: str, actor: str = "",
                    bot: "universitybot" = Depends(get_bot)):
    _guild_or_404(bot, guild_id)

    if not store.loesche(guild_id, kennung):
        raise HTTPException(status_code=404, detail="Diese Sicherung gibt es nicht.")

    await feature_audit.log_action(
        "backup_deleted", actor=actor or "dashboard",
        detail=f"guild {guild_id}: {kennung}",
    )
    return {"status": "ok", "backups": store.liste(guild_id)}


async def _stelle_her(bot, guild, guild_id: int, inhalt: dict, *,
                      actor: str, alles_loeschen: bool,
                      mit_einstellungen: bool, mit_nachrichten: bool,
                      kennung: str) -> None:
    def melde(text: str) -> None:
        eintrag = _LAEUFT.get(guild_id)
        if eintrag is not None:
            eintrag["schritt"] = text

    try:
        bericht = await backup_runner.stelle_wieder_her(
            bot, guild, inhalt,
            alles_loeschen=alles_loeschen,
            mit_einstellungen=mit_einstellungen,
            mit_nachrichten=mit_nachrichten,
            fortschritt=melde,
        )
        eintrag = _LAEUFT.get(guild_id)
        if eintrag is not None:
            eintrag["bericht"] = bericht

        await feature_audit.log_action(
            "backup_restored", actor=actor,
            detail=(f"guild {guild_id}: {kennung}, "
                    f"{bericht['erstellt']['kanaele']} Kanäle, "
                    f"{bericht['erstellt']['rollen']} Rollen"),
        )
    except Exception as exc:  # noqa: BLE001
        await feature_audit.log_action(
            "backup_restore_failed", actor=actor,
            detail=f"guild {guild_id}: {exc}",
        )
    finally:
        _LAEUFT.pop(guild_id, None)
        _TASKS.pop(guild_id, None)


@router.post("/{guild_id}/{kennung}/restore", summary="Sicherung einspielen")
async def wiederherstellen(guild_id: int, kennung: str, data: dict,
                           bot: "universitybot" = Depends(get_bot)):
    """Zurueckspielen -- mit den beiden Ja/Nein-Fragen aus der Oberflaeche.

    `alles_loeschen`: erst Kanaele und Rollen entfernen, dann neu
    aufbauen. Ohne das wird nur ergaenzt, was fehlt.

    `mit_einstellungen`: die Dashboard-Konfiguration mit
    zurueckspielen.
    """
    guild = _guild_or_404(bot, guild_id)
    actor = str(data.get("actor") or "")

    if guild_id in _LAEUFT:
        raise HTTPException(
            status_code=409,
            detail="Für diesen Server läuft schon eine Sicherung.",
        )

    eintrag = store.hole(guild_id, kennung, mit_daten=True)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Diese Sicherung gibt es nicht.")

    mit_nachrichten = bool(data.get("mit_nachrichten"))
    if mit_nachrichten and not _hat_premium(actor):
        raise HTTPException(
            status_code=403,
            detail="Nachrichten zurückschreiben geht nur mit Premium.",
        )
    if mit_nachrichten and not eintrag["daten"].get("messages"):
        raise HTTPException(
            status_code=400,
            detail="In dieser Sicherung sind keine Nachrichten.",
        )

    _LAEUFT[guild_id] = {
        "schritt": "Wird vorbereitet",
        "art": "wiederherstellen",
        "seit": int(time.time()),
    }
    _TASKS[guild_id] = asyncio.create_task(
        _stelle_her(
            bot, guild, guild_id, eintrag["daten"],
            actor=actor,
            alles_loeschen=bool(data.get("alles_loeschen")),
            mit_einstellungen=bool(data.get("mit_einstellungen", True)),
            mit_nachrichten=mit_nachrichten,
            kennung=kennung,
        )
    )

    return {"status": "gestartet", "lauf": _zustand(guild_id)}


