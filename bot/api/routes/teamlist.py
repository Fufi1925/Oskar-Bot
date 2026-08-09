# ╔══════════════════════════════════════════════════════════════════╗
# ║   Teamliste                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Die Teamliste einrichten, ansehen und senden.

Fuenf Routen:

  GET  /              Einstellungen, Gruppen und die Rollen des Servers
  PATCH /             Einstellungen sichern
  PUT  /groups        die Rollengruppen ersetzen
  GET  /preview       wie die Nachricht aussaehe -- ohne sie zu senden
  POST /publish       senden oder die bestehende bearbeiten
  DELETE /            alles vergessen und die Nachricht loeschen

Warum die Vorschau vom Bot kommt und nicht aus dem Browser
----------------------------------------------------------
Das Dashboard koennte den Text selbst zusammenbauen. Dann gaebe es
das Format zweimal -- einmal in Python, einmal in TypeScript -- und
spaetestens bei der dritten Aenderung liefen beide auseinander. Die
Vorschau zeigt genau das, was auch gesendet wuerde, weil es dieselbe
Funktion ist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import teamlist_render as renderer
from utils import teamlist_store as store

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
        raise HTTPException(404, "Der Bot ist nicht auf diesem Server.")
    return guild


def _roles_of(guild) -> list[dict]:
    """Die Rollen des Servers, von oben nach unten.

    @everyone und von Discord verwaltete Rollen (Bot-Rollen, Booster)
    fallen heraus: @everyone haette jeder, und eine Bot-Rolle als
    Teamgruppe ergibt keine Liste von Menschen.
    """

    out = []
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
        members = [
            m for m in renderer._members_of(guild, role)
            if not getattr(m, "bot", False)
        ]
        out.append(
            {
                # Als Text: 17-20 Ziffern sind groesser als
                # JavaScripts sicherer Zahlenbereich.
                "id": str(int(role.id)),
                "name": role.name,
                "colour": f"#{colour:06x}" if colour else None,
                "position": int(getattr(role, "position", 0)),
                "members": len(members),
            }
        )
    return out


def _channels_of(guild) -> list[dict]:
    """Textkanaele, in die der Bot schreiben darf.

    Kanaele ohne Schreibrecht auszublenden erspart die Fehlermeldung
    hinterher -- man kann gar nicht erst den falschen waehlen.
    """

    import discord

    me = getattr(guild, "me", None)
    out = []
    for channel in getattr(guild, "text_channels", []) or []:
        allowed = True
        if me is not None:
            try:
                allowed = channel.permissions_for(me).send_messages
            except Exception:
                allowed = True
        if not allowed:
            continue
        out.append(
            {
                "id": str(int(channel.id)),
                "name": channel.name,
                "category": (
                    channel.category.name
                    if getattr(channel, "category", None)
                    else None
                ),
            }
        )
    _ = discord
    return out


@router.get("/{guild_id}", summary="Einstellungen und Rollen")
async def get_all(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    config = await store.get_config(db, guild_id)
    groups = await store.get_groups(db, guild_id)

    # Die Rollennamen dazu: das Dashboard zeigt sie in der Gruppe an,
    # und ohne sie staende dort eine nackte Zahl.
    names = renderer.role_names(guild, groups)
    for group in groups:
        group["role_name"] = names.get(group["role_id"], "Gelöschte Rolle")
        group["role_exists"] = group["role_id"] in {
            r["id"] for r in _roles_of(guild)
        }

    return {
        "config": config,
        "groups": groups,
        "roles": _roles_of(guild),
        "channels": _channels_of(guild),
        "styles": list(store.STYLES),
        "limits": {
            "max_groups": store.MAX_GROUPS,
            "max_title": store.MAX_TITLE,
            "max_text": store.MAX_TEXT,
            "max_message": store.MAX_MESSAGE,
        },
        # Ob der Bot ueberhaupt Status anzeigen kann. Ohne den
        # presences-Intent waere jeder "offline" -- eine Reihe grauer
        # Punkte ist schlechter als keine Anzeige.
        "can_show_status": _has_presences(guild),
    }


def _has_presences(guild) -> bool:
    intents = getattr(getattr(guild, "_state", None), "intents", None)
    if intents is None:
        return False
    return bool(getattr(intents, "presences", False))


@router.patch("/{guild_id}", summary="Einstellungen sichern")
async def patch_config(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    await store.save_config(db, guild_id, data or {})
    await feature_audit.log_action("teamlist_config", guild_id=guild_id)

    return {"status": "success", "config": await store.get_config(db, guild_id)}


@router.put("/{guild_id}/groups", summary="Rollengruppen ersetzen")
async def put_groups(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    groups = (data or {}).get("groups")
    if not isinstance(groups, list):
        raise HTTPException(400, "»groups« muss eine Liste sein.")

    if len(groups) > store.MAX_GROUPS:
        raise HTTPException(
            400,
            f"Mehr als {store.MAX_GROUPS} Gruppen sind nicht vorgesehen — "
            "die Nachricht würde Discords Grenze von 2000 Zeichen sprengen.",
        )

    await store.save_groups(db, guild_id, groups)

    saved = await store.get_groups(db, guild_id)
    names = renderer.role_names(guild, saved)
    for group in saved:
        group["role_name"] = names.get(group["role_id"], "Gelöschte Rolle")

    return {"status": "success", "groups": saved}


@router.get("/{guild_id}/preview", summary="Wie die Nachricht aussaehe")
async def preview(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """Der fertige Text, ohne ihn zu senden.

    Dieselbe Funktion wie beim Senden -- deshalb stimmt die Vorschau
    mit dem Ergebnis ueberein, statt es nur nachzuahmen.
    """

    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    config = await store.get_config(db, guild_id)
    groups = await store.get_groups(db, guild_id)
    text = renderer.build(guild, config, groups)

    # Wie viele Personen insgesamt -- und ob jemand doppelt vorkommt.
    members = renderer.collect(guild, groups)
    everyone = [m["id"] for entries in members.values() for m in entries]
    doubled = sorted({m for m in everyone if everyone.count(m) > 1})

    return {
        "text": text,
        "length": len(text),
        "max_length": store.MAX_MESSAGE,
        # Zu lang heisst: der Text wird beim Senden gekuerzt. Besser,
        # das vorher zu wissen.
        "too_long": len(text) >= store.MAX_MESSAGE,
        "counts": {
            str(role_id): len(entries) for role_id, entries in members.items()
        },
        "total": len(set(everyone)),
        # Wer in zwei Gruppen steht, taucht zweimal auf. Das kann
        # gewollt sein -- gemeldet wird es trotzdem.
        "duplicates": doubled,
    }


@router.post("/{guild_id}/publish", summary="Senden oder bearbeiten")
async def publish(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    # Ein Kanal im Aufruf ueberschreibt den gespeicherten: so kann das
    # Dashboard "hier senden" anbieten, ohne vorher zu speichern.
    channel_id = (data or {}).get("channel_id")
    if channel_id:
        await store.save_config(db, guild_id, {"channel_id": channel_id})

    config = await store.get_config(db, guild_id)
    if not config.get("channel_id"):
        raise HTTPException(400, "Es ist kein Kanal eingestellt.")

    groups = await store.get_groups(db, guild_id)
    if not groups:
        raise HTTPException(
            400, "Es ist keine Rolle eingerichtet — die Liste wäre leer."
        )

    result = await renderer.publish(bot, guild, config, groups)
    if not result["ok"]:
        raise HTTPException(400, result["reason"])

    await store.set_message(
        db, guild_id, config["channel_id"], result["message_id"]
    )
    # Senden schaltet ein: alles andere waere ueberraschend -- die
    # Nachricht steht dann im Kanal, wuerde sich aber nie aktualisieren.
    await store.save_config(db, guild_id, {"enabled": True})

    await feature_audit.log_action(
        "teamlist_publish", guild_id=guild_id, detail=result["message_id"]
    )

    return {
        "status": "success",
        "message_id": result["message_id"],
        "config": await store.get_config(db, guild_id),
    }


@router.delete("/{guild_id}", summary="Teamliste entfernen")
async def remove(
    guild_id: int,
    delete_message: bool = True,
    bot: "universitybot" = Depends(get_bot),
):
    """Alles vergessen.

    `delete_message` entscheidet, ob die Nachricht im Kanal
    mitverschwindet. Standard ja -- eine Teamliste, die niemand mehr
    aktualisiert, ist schlimmer als keine: sie sieht richtig aus und
    ist es nicht.
    """

    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    config = await store.get_config(db, guild_id)

    if delete_message and config.get("channel_id") and config.get("message_id"):
        try:
            channel = guild.get_channel(int(config["channel_id"]))
            if channel is not None:
                message = await channel.fetch_message(int(config["message_id"]))
                await message.delete()
        except Exception:
            # Schon weg, keine Rechte, Kanal geloescht -- kein Grund,
            # das Vergessen zu verweigern.
            pass

    await store.clear(db, guild_id)
    await feature_audit.log_action("teamlist_delete", guild_id=guild_id)

    return {"status": "success"}
