# ╔══════════════════════════════════════════════════════════════════╗
# ║   Ping-Reaktionen                                                ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Wer beim Erwaehnen welche Reaktion bekommt -- im Admin-Panel pflegbar.

Bisher stand das fest in ``cogs/events/react.py``: die beiden Besitzer,
mit vier beziehungsweise drei Emojis. Jeder weitere Name bedeutete eine
Codeaenderung und ein neues Deploy.

Die Besitzer bleiben dort, wo sie sind. Diese Liste kommt zusaetzlich
-- so kann ein Fehler hier die eigene Kennzeichnung nicht abschalten.
Angezeigt werden trotzdem beide, sonst steht im Panel eine Liste, in
der die zwei wichtigsten Eintraege fehlen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import ping_reactions as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _describe(bot, user_id: str) -> dict:
    """Name und Bild zu einer ID, soweit der Bot sie kennt.

    Ohne das steht im Panel eine Spalte voller Zahlen. `get_user`
    trifft nur, wenn der Bot die Person schon einmal gesehen hat --
    steht dort nichts, bleibt die ID, und das ist ehrlicher als ein
    erfundener Name.
    """

    try:
        user = bot.get_user(int(user_id))
    except Exception:  # noqa: BLE001
        user = None

    if user is None:
        return {"name": "", "avatar": None}

    return {
        "name": getattr(user, "display_name", "") or getattr(user, "name", ""),
        "avatar": (
            str(user.display_avatar.url) if getattr(user, "display_avatar", None)
            else None
        ),
    }


def _emoji_details(raw: str) -> dict:
    """Aus ``<a:name:id>`` das, was die Anzeige braucht."""

    match = store.PATTERN.match(raw)
    if match is None:
        return {"raw": raw, "name": "", "id": "", "animated": False, "url": None}

    animated = bool(match.group(1))
    emoji_id = match.group(3)
    return {
        "raw": raw,
        "name": match.group(2),
        "id": emoji_id,
        "animated": animated,
        "url": (
            f"https://cdn.discordapp.com/emojis/{emoji_id}."
            f"{'gif' if animated else 'png'}?size=48"
        ),
    }


def _builtin_rules(bot) -> list[dict]:
    """Die fest verdrahteten Besitzer-Reaktionen -- nur zum Ansehen."""

    from cogs.events.react import owner_reactions

    from utils.config import OWNER_IDS

    entries = []
    for user_id in OWNER_IDS:
        emojis = owner_reactions(user_id)
        if not emojis:
            continue
        entries.append({
            "user_id": str(user_id),
            "emojis": [_emoji_details(e) for e in emojis],
            "note": "Fest im Code — nicht über das Panel änderbar.",
            "enabled": True,
            "builtin": True,
            **_describe(bot, str(user_id)),
        })
    return entries


@router.get("", summary="Alle Ping-Reaktionen")
async def list_rules(bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    entries = await store.all_entries(db)

    rules = []
    for entry in entries:
        rules.append({
            **entry,
            "emojis": [_emoji_details(e) for e in entry["emojis"]],
            "builtin": False,
            **_describe(bot, entry["user_id"]),
        })

    return {
        "builtin": _builtin_rules(bot),
        "rules": rules,
        "count": len(rules),
        "limits": {
            "max_reactions": store.MAX_REACTIONS,
            "max_entries": store.MAX_ENTRIES,
        },
    }


@router.post("", summary="Eintrag anlegen oder ändern")
async def save_rule(data: dict, bot: "universitybot" = Depends(get_bot)):
    raw_id = str(data.get("user_id") or "").strip()

    # Auch eine Erwaehnung annehmen: wer eine ID kopiert, erwischt
    # schnell `<@123>` statt `123`.
    if raw_id.startswith("<@") and raw_id.endswith(">"):
        raw_id = raw_id[2:-1].lstrip("!&")

    if not raw_id.isdigit() or not (17 <= len(raw_id) <= 20):
        raise HTTPException(
            status_code=400,
            detail="Das ist keine gültige Discord-ID. Sie hat 17 bis 20 Ziffern.",
        )

    from cogs.events.react import owner_reactions

    if owner_reactions(int(raw_id)):
        raise HTTPException(
            status_code=400,
            detail=(
                "Für diese ID gibt es schon eine feste Regel im Code. "
                "Sie lässt sich hier nicht überschreiben."
            ),
        )

    emojis = data.get("emojis")
    if not isinstance(emojis, list):
        raise HTTPException(status_code=400, detail="»emojis« muss eine Liste sein.")

    db = await _db()
    try:
        entry = await store.save(
            db,
            int(raw_id),
            emojis,
            note=str(data.get("note") or ""),
            enabled=bool(data.get("enabled", True)),
            added_by=str(data.get("actor") or ""),
        )
    except store.RuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Der Zwischenspeicher im Cog muss die Aenderung sofort sehen --
    # sonst wirkt sie erst nach dem naechsten Neustart, und das sieht
    # aus, als haette das Speichern nicht funktioniert.
    await store.load(db, force=True)

    await feature_audit.log_action(
        "ping_reaction_saved",
        actor=str(data.get("actor", "dashboard")),
        detail=f"{raw_id}: {len(entry['emojis'])} Emojis",
    )

    return {
        "status": "success",
        "result": "Gespeichert.",
        **entry,
        "emojis": [_emoji_details(e) for e in entry["emojis"]],
        **_describe(bot, entry["user_id"]),
    }


@router.delete("/{user_id}", summary="Eintrag löschen")
async def delete_rule(user_id: int, actor: str = ""):
    db = await _db()
    removed = await store.remove(db, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Diesen Eintrag gibt es nicht.")

    await store.load(db, force=True)

    await feature_audit.log_action(
        "ping_reaction_deleted",
        actor=actor or "dashboard",
        detail=str(user_id),
    )
    return {"status": "success", "result": "Gelöscht."}


@router.post("/{user_id}/toggle", summary="Ein- oder ausschalten")
async def toggle_rule(user_id: int, data: dict | None = None):
    """Vorübergehend abschalten, ohne die Emoji-Auswahl zu verlieren.

    Loeschen und neu anlegen waere der Umweg -- und wer zehn Emojis
    zusammengeklickt hat, moechte sie nicht noch einmal suchen.
    """

    db = await _db()
    entry = await store.get(db, user_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Diesen Eintrag gibt es nicht.")

    payload = data or {}
    wanted = bool(payload.get("enabled", not entry["enabled"]))

    updated = await store.save(
        db,
        user_id,
        entry["emojis"],
        note=entry["note"],
        enabled=wanted,
        added_by=entry["added_by"],
    )
    await store.load(db, force=True)

    return {
        "status": "success",
        "result": "Aktiv." if wanted else "Pausiert.",
        **updated,
        "emojis": [_emoji_details(e) for e in updated["emojis"]],
    }
