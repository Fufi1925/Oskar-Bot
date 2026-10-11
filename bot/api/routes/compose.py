# ╔══════════════════════════════════════════════════════════════════╗
# ║   Compose: send a freely designed message as the bot             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Build a message in the dashboard and post it into a channel.

Plain text, a classic embed, or a Components V2 layout assembled from
blocks the author arranges themselves.

The existing `/actions/{guild}/message/send` route managed a title, a
body and a colour in one fixed shape. Everything past that meant editing
Python.

Messages can also be edited afterwards, which matters more than it
sounds: a rules post with a typo otherwise has to be deleted and posted
again, losing its pins, links and reactions.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from typing import TYPE_CHECKING

import discord
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_bot
from utils import feature_audit
from utils import message_builder as builder

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

COMPOSE_CODES_DB = os.path.join("db", "compose_codes.db")


def _compose_codes_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(COMPOSE_CODES_DB), exist_ok=True)
    db = sqlite3.connect(COMPOSE_CODES_DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS compose_codes ("
        " code TEXT PRIMARY KEY, guild_id TEXT NOT NULL, payload_json TEXT NOT NULL,"
        " created_by TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,"
        " used_by TEXT, used_at INTEGER)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS compose_codes_guild_created ON compose_codes(guild_id,created_at DESC,code DESC)")
    return db


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


def _channel(guild, raw) -> object:
    channel_id = str(raw or "")
    if not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal auswählen.")

    channel = guild.get_channel(int(channel_id))
    # hasattr rather than isinstance: a thread can be posted in too, but
    # is not a TextChannel.
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    me = guild.me
    if me is not None:
        permissions = channel.permissions_for(me)
        if not permissions.send_messages:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
            )
        if not permissions.embed_links:
            raise HTTPException(
                status_code=403,
                detail=f"In #{channel.name} fehlt „Links einbetten“ — Embeds und "
                       "Karten kämen dort leer an.",
            )
    return channel


@router.get("/{guild_id}/codes", summary="List this server's saved message codes")
async def list_compose_codes(guild_id: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    db = _compose_codes_db()
    try:
        total = db.execute("SELECT COUNT(*) FROM compose_codes WHERE guild_id=?", (str(guild_id),)).fetchone()[0]
        rows = db.execute("SELECT code,payload_json,created_at FROM compose_codes WHERE guild_id=? ORDER BY created_at DESC,code DESC LIMIT ? OFFSET ?", (str(guild_id), limit, offset)).fetchall()
        codes = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            embed = payload.get("embed") if isinstance(payload.get("embed"), dict) else {}
            blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else []
            text = str(payload.get("content") or embed.get("description") or next((block.get("text") for block in blocks if isinstance(block, dict) and block.get("type") == "text" and block.get("text")), ""))
            title = str(embed.get("title") or (text.splitlines()[0] if text else ""))
            codes.append({"code": row["code"], "kind": payload.get("kind", "text"), "title": title[:120], "excerpt": text[:200], "created_at": row["created_at"]})
        return {"codes": codes, "total": total, "next_offset": offset + len(codes) if offset + len(codes) < total else None}
    finally:
        db.close()


@router.get("/{guild_id}/codes/{code}", summary="Preview one of this server's message codes")
async def preview_compose_code(guild_id: int, code: str):
    db = _compose_codes_db()
    try:
        row = db.execute("SELECT payload_json,created_at FROM compose_codes WHERE guild_id=? AND code=?", (str(guild_id), code)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dieser Code existiert auf diesem Server nicht.")
        return {"code": code, "created_at": row["created_at"], "payload": json.loads(row["payload_json"])}
    finally:
        db.close()


@router.post("/{guild_id}/codes", summary="Create a reusable message design code")
async def create_compose_code(guild_id: int, data: dict, actor: str = ""):
    payload = {
        key: value for key, value in data.items()
        if key in {
            "kind", "channel_id", "content", "embed", "color", "blocks",
            "allow_mentions", "pin", "sender",
        }
    }
    problems = builder.validate(payload)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 100_000:
        raise HTTPException(status_code=400, detail="Die Nachricht ist zu groß zum Speichern.")

    created_by = str(actor or data.get("actor") or "dashboard")
    now = int(time.time())
    db = _compose_codes_db()
    try:
        with db:
            for _ in range(40):
                code = str(10_000_000 + secrets.randbelow(90_000_000))
                try:
                    db.execute(
                        "INSERT INTO compose_codes"
                        "(code,guild_id,payload_json,created_by,created_at) VALUES(?,?,?,?,?)",
                        (code, str(guild_id), encoded, created_by, now),
                    )
                    break
                except sqlite3.IntegrityError:
                    continue
            else:  # pragma: no cover - requires dozens of random collisions
                raise HTTPException(status_code=503, detail="Code konnte nicht erzeugt werden.")
    finally:
        db.close()
    return {"code": code, "digits": 8, "single_use": False}


@router.post("/{guild_id}/codes/import", summary="Import a reusable message design code")
async def import_compose_code(guild_id: int, data: dict, actor: str = ""):
    code = str(data.get("code") or "").strip()
    if len(code) != 8 or not code.isdigit():
        raise HTTPException(status_code=400, detail="Der Code muss genau 8 Zahlen enthalten.")

    db = _compose_codes_db()
    try:
        with db:
            row = db.execute("SELECT * FROM compose_codes WHERE code=?", (code,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Dieser Code existiert nicht.")
            db.execute(
                "UPDATE compose_codes SET used_by=?,used_at=? WHERE code=?",
                (str(actor or data.get("actor") or "dashboard"), int(time.time()), code),
            )
            payload = json.loads(row["payload_json"])
            cross_server = str(row["guild_id"]) != str(guild_id)
            if cross_server:
                # A source guild's channel and support-only alternate bot are
                # not valid delivery targets on the destination guild.
                payload["channel_id"] = ""
                payload["sender"] = "main"
    finally:
        db.close()
    return {"code": code, "consumed": False, "cross_server": cross_server, "payload": payload}


@router.post("/{guild_id}/check", summary="Is this message sendable?")
async def check(guild_id: int, data: dict):
    """
    Report everything wrong at once.

    Discord answers a malformed message with a terse 400 that names no
    field, so the checks happen here where they can say which one.
    """
    problems = builder.validate(data)
    return {
        "ok": not problems,
        "problems": problems,
        "summary": builder.describe(data),
        "limits": builder.LIMITS,
    }


# The support server, and the second bot that also lives there.
#
# Sending "the bot is down" through the bot that is down does not work,
# so the status bot can post too. It runs as its own Railway service and
# is reached over HTTP; when STATUS_BOT_URL is unset the option simply
# does not appear.
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID") or 1530378233579704370)


def _status_bot_url() -> str:
    return (os.getenv("STATUS_BOT_URL") or "").strip().rstrip("/")


@router.get("/{guild_id}/senders", summary="Which bots can post here")
async def senders(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    The dashboard asks this to decide whether to offer a choice.

    Everywhere except the support server there is exactly one answer, so
    the picker is hidden rather than shown with a single option.
    """
    options = [{
        "id": "main",
        "name": getattr(bot.user, "name", "CloudTIX"),
        "description": "Der Hauptbot. Für alles Normale.",
    }]

    if guild_id == HOME_GUILD_ID and _status_bot_url():
        options.append({
            "id": "status",
            "name": "CloudTIX Status",
            "description": (
                "Der Status-Bot. Läuft in einem eigenen Container und kann "
                "auch dann posten, wenn der Hauptbot gerade weg ist."
            ),
        })

    return {"guild_id": str(guild_id), "options": options}


async def _send_via_status(guild_id: int, data: dict) -> dict:
    """Hand the message to the status bot's own endpoint."""
    url = _status_bot_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Der Status-Bot ist nicht eingerichtet (STATUS_BOT_URL fehlt).",
        )
    if guild_id != HOME_GUILD_ID:
        raise HTTPException(
            status_code=403,
            detail="Der Status-Bot postet nur im Support-Server.",
        )

    key = (os.getenv("DASHBOARD_API_KEY") or "").strip()
    payload = {k: v for k, v in data.items() if k != "sender"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{url}/send", json=payload, headers={"X-API-Key": key}
            )
    except httpx.HTTPError as err:
        # The one case worth naming precisely: if the status bot is also
        # unreachable, saying so beats a generic failure.
        raise HTTPException(
            status_code=502,
            detail=f"Der Status-Bot antwortet nicht ({type(err).__name__}).",
        )

    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=body.get("detail") or "Der Status-Bot hat abgelehnt.",
        )
    return body


@router.post("/{guild_id}/send", summary="Post the message")
async def send(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    # Which bot should post. Anything other than "status" is the main
    # one, so an unknown value falls back to the safe default rather
    # than failing.
    if str(data.get("sender") or "main") == "status":
        problems = builder.validate(data)
        if problems:
            raise HTTPException(status_code=400, detail=" ".join(problems))
        return await _send_via_status(guild_id, data)

    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, data.get("channel_id"))

    problems = builder.validate(data)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    kwargs = builder.build(data)

    # Mentions are off unless asked for: a bot posting @everyone because
    # somebody pasted it into a rules text is a bad afternoon.
    if not data.get("allow_mentions"):
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()

    try:
        message = await channel.send(**kwargs)
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord hat die Nachricht abgelehnt: {exc}"
        )

    if data.get("pin"):
        try:
            await message.pin(reason="Über das Dashboard angepinnt")
        except Exception:
            pass  # a full pin list is not worth failing the send over

    await feature_audit.log_action(
        "message_sent", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{data.get('kind', 'text')} in #{channel.name}",
    )
    return {
        "status": "success",
        "result": f"Gesendet in #{channel.name}.",
        "message_id": str(message.id),
        "url": message.jump_url,
    }


@router.post("/{guild_id}/edit", summary="Change a message the bot sent")
async def edit(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Rewrite an existing message.

    Only messages the bot itself sent can be edited — Discord does not
    allow anything else, and saying so up front beats a confusing 403.
    """
    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, data.get("channel_id"))

    message_id = str(data.get("message_id") or "")
    if not message_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte die Nachrichten-ID angeben.")

    problems = builder.validate(data)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        raise HTTPException(
            status_code=404,
            detail="In diesem Kanal gibt es keine Nachricht mit dieser ID.",
        )
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail="Der Bot darf diesen Kanal nicht lesen."
        )

    if message.author.id != bot.user.id:
        raise HTTPException(
            status_code=400,
            detail="Diese Nachricht stammt nicht vom Bot — fremde Nachrichten "
                   "kann Discord nicht bearbeiten lassen.",
        )

    kwargs = builder.build(data)
    # An edit has to clear whatever the message had before, otherwise a
    # switch from embed to plain text leaves the old embed sitting there.
    payload = {
        "content": kwargs.get("content"),
        "embed": kwargs.get("embed"),
        "view": kwargs.get("view"),
    }
    if "view" in kwargs:
        payload = {"view": kwargs["view"]}
    else:
        payload.setdefault("content", None)
        payload["embeds"] = [kwargs["embed"]] if kwargs.get("embed") else []
        payload.pop("embed", None)
        payload.pop("view", None)

    try:
        await message.edit(**payload)
    except discord.HTTPException as exc:
        raise HTTPException(
            status_code=400, detail=f"Discord hat die Änderung abgelehnt: {exc}"
        )

    await feature_audit.log_action(
        "message_edited", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{message_id} in #{channel.name}",
    )
    return {
        "status": "success",
        "result": "Nachricht geändert.",
        "url": message.jump_url,
    }


@router.get("/{guild_id}/fetch", summary="Read a message back for editing")
async def fetch(
    guild_id: int, channel_id: str, message_id: str,
    bot: "universitybot" = Depends(get_bot),
):
    """Load an existing bot message so it can be edited in the dashboard."""
    guild = _guild_or_404(bot, guild_id)
    channel = _channel(guild, channel_id)

    if not message_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine gültige ID angeben.")

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden.")

    embeds = []
    for embed in message.embeds:
        embeds.append({
            "title": embed.title or "",
            "description": embed.description or "",
            "color": f"#{embed.color.value:06x}" if embed.color else "",
            "footer_text": embed.footer.text if embed.footer else "",
            "author_name": embed.author.name if embed.author else "",
            "image": embed.image.url if embed.image else "",
            "thumbnail": embed.thumbnail.url if embed.thumbnail else "",
            "fields": [
                {"name": f.name, "value": f.value, "inline": f.inline}
                for f in embed.fields
            ],
        })

    return {
        "message_id": str(message.id),
        "content": message.content or "",
        "embeds": embeds,
        "is_ours": message.author.id == bot.user.id,
        "url": message.jump_url,
        # V2 layouts cannot be read back into blocks, so say so rather
        # than silently offering a broken editor.
        "editable": message.author.id == bot.user.id and not message.components,
        "note": (
            "Diese Nachricht enthält Knöpfe oder eine Karte — sie lässt sich "
            "hier nicht zurücklesen, nur überschreiben."
            if message.components else ""
        ),
    }


# --------------------------------------------------------------------- #
# Die Emoji-Auswahl
# --------------------------------------------------------------------- #
#
# Only the dashboard-enabled CloudTIX pack is offered for bot messages.
# Cached application IDs supply the insertable Discord codes.

@router.get("/{guild_id}/emojis", summary="Custom emojis available on this server")
async def guild_emojis(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    items = []
    for emoji in sorted(guild.emojis, key=lambda item: item.name.lower()):
        if not bool(getattr(emoji, "available", True)):
            continue
        animated = bool(getattr(emoji, "animated", False))
        items.append({
            "key": f"SERVER_{emoji.id}",
            "name": emoji.name,
            "id": str(emoji.id),
            "animated": animated,
            "raw": f"<{'a' if animated else ''}:{emoji.name}:{emoji.id}>",
            "group": "Server-Emojis",
            "url": str(emoji.url),
        })
    return {"emojis": items, "groups": ["Server-Emojis"] if items else [], "count": len(items)}


@router.get("/emojis", summary="Die eigenen Emojis des Bots")
async def emojis(bot: "universitybot" = Depends(get_bot)):
    """Colorful/gray previews and real IDs, without retired bot emojis.

    Pending assets remain visible until Discord assigns an insertable ID.
    """
    import re as _re
    from utils.application_emojis import catalog

    application_id = bot.application_id or (bot.user.id if bot.user else None)
    pack = catalog(application_id)["emojis"]
    category_labels = {
        "Security": "Sicherheit",
        "Support": "Support",
        "Community": "Community",
        "Music": "Musik",
        "UI": "Oberfläche",
        "Badges": "Abzeichen",
        "Status": "Status",
        "Server": "Server",
        "Moderation": "Moderation",
        "Economy": "Wirtschaft",
        "Media": "Medien",
        "Regelwerk": "Regelwerk",
    }
    pattern = _re.compile(r"^<(a?):([A-Za-z0-9_]+):(\d+)>$")
    items: list[dict] = []

    # All bundled assets appear even when an upload is still missing. The
    # local preview needs no Discord ID and remains available on mobile too.
    for entry in pack:
        raw = entry["discord_code"]
        match = pattern.fullmatch(raw) if raw else None
        style = "Grau" if entry.get("provider") == "CloudTIX Gray" else "Farbe"
        items.append({
            "key": f"CT_{entry['key'].upper()}",
            "name": entry["name"],
            "id": match.group(3) if match else None,
            "animated": bool(match.group(1)) if match else entry["animated"],
            "raw": raw,
            "group": f"CloudTIX {style} · {category_labels.get(entry['category'], entry['category'])}",
            "url": f"/emojis/cloudtix/{entry['file']}",
            "source": "cloudtix",
            "style": entry.get("style", "gray" if style == "Grau" else "color"),
            "label": entry.get("label", entry["key"]),
            "keywords": entry.get("keywords", []),
            "category": category_labels.get(entry["category"], entry["category"]),
        })

    groups = list(dict.fromkeys(entry["group"] for entry in items))
    return {"emojis": items, "groups": groups, "count": len(items),
            "cloudtix_count": len(pack),
            "cloudtix_ready": sum(entry["discord_code"] is not None for entry in pack)}


# ── Vorgefertigte Texte ───────────────────────────────────────────────
#
# Die Begruessungs-Vorlagen standen frueher fest im Dashboard, mitsamt
# ihren Emojis als Unicode-Zeichen ("🎉"). Zwei Probleme damit:
#
#   1. Ein Unicode-Zeichen sieht auf jedem Geraet anders aus. Windows,
#      iOS und Android bringen eigene Saetze mit, und was ein Geraet
#      nicht kennt, zeigt es als leeres Rechteck.
#   2. Wollte man stattdessen die eigenen Emojis des Bots nehmen,
#      muesste die Schreibweise `<a:TADAA:1530375414575529984>` ins
#      Dashboard kopiert werden -- eine zweite Stelle, die beim ersten
#      neuen Emoji auseinanderlaeuft. Genau dieser Fehler stand hier
#      schon einmal im Changelog: vier Emojis zeigten auf geloeschte
#      IDs und erschienen als roher Text.
#
# Deshalb kommen die Vorlagen jetzt von hier. Die Codes werden aus
# `utils/emoji.py` gelesen -- derselben Quelle, aus der auch die
# Auswahl im Dashboard gespeist wird.
#
# Wichtig: Emojis gehoeren nur in Felder, die Discord auch als
# Nachricht rendert. In Kanal-, Rollen- oder Webhook-Namen erscheint
# der rohe Code als Text; solche Felder bleiben hier aussen vor.


@router.get("/templates/welcome", summary="Vorgefertigte Begruessungen")
async def welcome_templates():
    """Die Vorlagen fuer die Begruessung, mit den Emojis des Bots.

    Gelesen wird ``utils/emoji.py``. Faellt ein Emoji eines Tages weg,
    steht hier ein leerer String statt eines kaputten Codes -- eine
    Vorlage ohne Emoji ist immer noch brauchbar, ein
    ``<:weg:123>`` mitten im Satz nicht.
    """

    from utils import emoji as bot_emoji

    def pick(name: str) -> str:
        return str(getattr(bot_emoji, name, "") or "")

    party = pick("TADAA")
    wave = pick("MINGLE")
    star = pick("STAR")

    return {
        "templates": [
            {
                "name": "Kurz & freundlich",
                "type": "simple",
                "message": (
                    f"Willkommen {{user}} auf **{{server_name}}**! {party} "
                    "Du bist Mitglied Nummer {server_membercount}."
                ),
            },
            {
                "name": "Mit Bild",
                "type": "embed",
                "embed": {
                    "title": f"{wave} Willkommen auf {{server_name}}!",
                    "description": (
                        "Schön, dass du da bist, {user}!\n\n"
                        "Schau dich ruhig um — du bist unser "
                        "{server_membercount}. Mitglied."
                    ),
                    "color": "#5865f2",
                    "thumbnail": "{user_avatar}",
                    "footer_text": "Beigetreten am {user_joindate}",
                },
            },
            {
                "name": "Sachlich",
                "type": "embed",
                "embed": {
                    "title": "Neues Mitglied",
                    "description": "{user} ist dem Server beigetreten.",
                    "color": "#2f3136",
                    "footer_text": "Mitglied #{server_membercount}",
                },
            },
            {
                "name": "Mit Sternen",
                "type": "embed",
                "embed": {
                    "title": f"{star} Willkommen, {{user_name}}!",
                    "description": (
                        f"{party} Schön, dass du zu **{{server_name}}** "
                        "gefunden hast.\n\n"
                        "Du bist unser {server_membercount}. Mitglied."
                    ),
                    "color": "#fbbf24",
                    "thumbnail": "{user_avatar}",
                    "footer_text": "Beigetreten am {user_joindate}",
                },
            },
        ]
    }
