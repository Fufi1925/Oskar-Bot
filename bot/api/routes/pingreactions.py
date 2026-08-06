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


def _builtin_rules(bot, entries: list[dict]) -> list[dict]:
    """Die mitgelieferten Besitzer-Regeln -- jetzt auch aenderbar.

    Sie waren zuerst nur zum Ansehen da. Aenderbar heisst nicht, dass
    sie aus dem Code verschwinden: der Code bleibt der Standard, eine
    gespeicherte Zeile legt sich darueber, und "Zuruecksetzen" wirft
    die Zeile weg.

    Deshalb steht bei jedem Eintrag beides -- was gerade gilt und was
    mitgeliefert wurde. Ohne den Vergleich sieht niemand, ob er den
    Originalstand vor sich hat oder eine eigene Aenderung.
    """

    from cogs.events.react import default_owner_reactions

    from utils.config import OWNER_IDS

    by_id = {entry["user_id"]: entry for entry in entries}

    rules = []
    for user_id in OWNER_IDS:
        default = default_owner_reactions(user_id)
        if not default:
            continue

        override = by_id.get(str(user_id))
        if override is None:
            current = list(default)
            enabled = True
            note = ""
        else:
            current = override["emojis"]
            enabled = override["enabled"]
            note = override["note"]

        rules.append({
            "user_id": str(user_id),
            "emojis": [_emoji_details(e) for e in current],
            "default_emojis": [_emoji_details(e) for e in default],
            "note": note,
            "enabled": enabled,
            "builtin": True,
            # Weicht das, was gilt, vom mitgelieferten Stand ab?
            "customised": override is not None,
            **_describe(bot, str(user_id)),
        })
    return rules


@router.get("", summary="Alle Ping-Reaktionen")
async def list_rules(bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    entries = await store.all_entries(db)

    from cogs.events.react import default_owner_reactions

    builtin = _builtin_rules(bot, entries)
    builtin_ids = {rule["user_id"] for rule in builtin}

    rules = []
    for entry in entries:
        # Eine Zeile zu einer Besitzer-ID steht oben als Aenderung der
        # mitgelieferten Regel -- sie hier ein zweites Mal zu zeigen
        # waere derselbe Eintrag zweimal, mit zwei Loeschknoepfen.
        if entry["user_id"] in builtin_ids:
            continue
        rules.append({
            **entry,
            "emojis": [_emoji_details(e) for e in entry["emojis"]],
            "default_emojis": [],
            "builtin": False,
            "customised": True,
            **_describe(bot, entry["user_id"]),
        })

    _ = default_owner_reactions  # nur fuer den Import-Check
    return {
        "builtin": builtin,
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

    # Eine Besitzer-ID wird hier nicht mehr abgewiesen.
    #
    # Sie war zuerst gesperrt, damit ein Versehen im Panel die eigene
    # Kennzeichnung nicht abschalten kann. Ausdruecklich anders
    # gewuenscht -- also legt sich eine gespeicherte Zeile jetzt ueber
    # den Code-Stand. Rueckgaengig geht ueber DELETE: die Zeile
    # verschwindet, der mitgelieferte Stand gilt wieder. Verloren gehen
    # kann dabei nichts.

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


@router.delete("/{user_id}", summary="Eintrag löschen bzw. zurücksetzen")
async def delete_rule(user_id: int, actor: str = ""):
    """Die gespeicherte Zeile entfernen.

    Bei einer gewoehnlichen ID heisst das: weg, der Bot reagiert nicht
    mehr.

    Bei einer Besitzer-ID heisst dasselbe etwas anderes -- die Zeile
    war nur eine Ueberschreibung, und ohne sie gilt wieder der
    mitgelieferte Stand aus dem Code. Deshalb steht in der Antwort
    auch, was gerade passiert ist: "geloescht" waere an dieser Stelle
    schlicht falsch und wuerde jemanden glauben lassen, die
    Kennzeichnung sei nun weg.
    """

    from cogs.events.react import default_owner_reactions

    db = await _db()
    removed = await store.remove(db, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Diesen Eintrag gibt es nicht.")

    await store.load(db, force=True)

    default = default_owner_reactions(user_id)

    await feature_audit.log_action(
        "ping_reaction_reset" if default else "ping_reaction_deleted",
        actor=actor or "dashboard",
        detail=str(user_id),
    )

    if default:
        return {
            "status": "success",
            "result": (
                f"Zurückgesetzt — es gelten wieder die {len(default)} "
                "mitgelieferten Emojis."
            ),
            "reset_to_default": True,
        }
    return {"status": "success", "result": "Gelöscht.", "reset_to_default": False}


@router.post("/{user_id}/toggle", summary="Ein- oder ausschalten")
async def toggle_rule(user_id: int, data: dict | None = None):
    """Vorübergehend abschalten, ohne die Emoji-Auswahl zu verlieren.

    Loeschen und neu anlegen waere der Umweg -- und wer zehn Emojis
    zusammengeklickt hat, moechte sie nicht noch einmal suchen.
    """

    from cogs.events.react import default_owner_reactions

    db = await _db()
    entry = await store.get(db, user_id)

    if entry is None:
        # Eine mitgelieferte Besitzer-Regel hat noch keine Zeile: sie
        # steht bisher nur im Code. Zum Pausieren muss also erst eine
        # angelegt werden -- mit genau den Emojis, die gerade gelten,
        # damit beim spaeteren Wiedereinschalten nichts fehlt.
        default = default_owner_reactions(user_id)
        if not default:
            raise HTTPException(
                status_code=404, detail="Diesen Eintrag gibt es nicht."
            )
        entry = {
            "emojis": list(default),
            "note": "",
            "enabled": True,
            "added_by": "",
        }

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
