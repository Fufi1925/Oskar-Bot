"""
Das Bild bei Begruessung und Abschied -- und der Abschied selbst.

Drei Dinge, die zusammengehoeren:

  * **Ein Schalter fuers Willkommensbild.** Das gezeichnete Banner ging
    bisher immer mit, sobald eine Begruessung eingestellt war. Wer nur
    eine Textzeile wollte, konnte das nicht abstellen.
  * **Ein eigenes Hintergrundbild.** Statt des gezeichneten Verlaufs
    laesst sich eine Adresse hinterlegen; Name, Avatar und Mitgliedszahl
    werden darauf geschrieben.
  * **Dasselbe fuer den Abschied.** Den gab es bisher gar nicht --
    ``on_member_remove`` wurde im Begruessungs-Cog nirgends behandelt.

Warum eine eigene Tabelle und nicht ``db/welcome.db`` erweitern: die
alte Tabelle hat sechs Spalten, und sowohl der Cog als auch die
Dashboard-Route lesen sie mit ``SELECT`` in fester Reihenfolge und
entpacken das Ergebnis in genau sechs Namen. Eine siebte Spalte haette
beide Stellen still verschoben. Eine getrennte Tabelle mit eigenem
Zugriff kann das nicht.
"""

from __future__ import annotations

import re
import json

from utils import db_paths

GREET_DB = "db/greet_extras.db"

# Nur Bild-Adressen, und nur ueber HTTPS. Ohne diese Pruefung koennte
# jemand eine beliebige Adresse hinterlegen -- Discord laedt sie beim
# Anzeigen, und der Server sieht die Anfrage.
_URL = re.compile(r"^https://[^\s<>\"']{5,500}$", re.I)
_BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def valid_image_url(url: str) -> bool:
    """
    Sieht das nach einer Bildadresse aus?

    Die Endung wird ohne Abfrageteil geprueft: Discords eigene CDN-
    Adressen tragen eine Signatur hinter dem ``?``, und ohne dieses
    Abschneiden waere jede davon ungueltig.
    """
    url = (url or "").strip()
    if not url or not _URL.match(url):
        return False
    pfad = url.split("?", 1)[0].split("#", 1)[0].lower()
    return pfad.endswith(_BILD_ENDUNGEN)


DEFAULTS = {
    "welcome_image_enabled": True,   # bisheriges Verhalten
    "welcome_image_url": "",
    "leave_enabled": False,
    "leave_channel_id": 0,
    "leave_message": "",
    "leave_image_enabled": True,
    "leave_image_url": "",
    "leave_type": "simple",
    "leave_embed_data": {},
    "leave_auto_delete_duration": 0,
}


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS greet_extras ("
        " guild_id INTEGER PRIMARY KEY,"
        " welcome_image_enabled INTEGER DEFAULT 1,"
        " welcome_image_url TEXT DEFAULT '',"
        " leave_enabled INTEGER DEFAULT 0,"
        " leave_channel_id INTEGER DEFAULT 0,"
        " leave_message TEXT DEFAULT '',"
        " leave_image_enabled INTEGER DEFAULT 1,"
        " leave_image_url TEXT DEFAULT '')"
    )
    # Existing installations keep their channel, text and image settings.
    async with db.execute("PRAGMA table_info(greet_extras)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    for name, declaration in {
        "leave_type": "TEXT DEFAULT 'simple'",
        "leave_embed_data": "TEXT DEFAULT '{}'",
        "leave_auto_delete_duration": "INTEGER DEFAULT 0",
    }.items():
        if name not in columns:
            await db.execute(f"ALTER TABLE greet_extras ADD COLUMN {name} {declaration}")
    await db.commit()


async def get(guild_id: int) -> dict:
    async with db_paths.connect(GREET_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT welcome_image_enabled, welcome_image_url, leave_enabled,"
            " leave_channel_id, leave_message, leave_image_enabled,"
            " leave_image_url, leave_type, leave_embed_data, leave_auto_delete_duration"
            " FROM greet_extras WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return dict(DEFAULTS)

    return {
        "welcome_image_enabled": bool(row[0]),
        "welcome_image_url": row[1] or "",
        "leave_enabled": bool(row[2]),
        "leave_channel_id": int(row[3] or 0),
        "leave_message": row[4] or "",
        "leave_image_enabled": bool(row[5]),
        "leave_image_url": row[6] or "",
        "leave_type": row[7] or "simple",
        "leave_embed_data": json.loads(row[8] or "{}"),
        "leave_auto_delete_duration": int(row[9] or 0),
    }


def validate_update(current: dict, data: dict) -> dict:
    aktuell = dict(current)

    for schluessel in ("welcome_image_enabled", "leave_enabled",
                       "leave_image_enabled"):
        if schluessel in data:
            aktuell[schluessel] = bool(data[schluessel])

    for schluessel in ("welcome_image_url", "leave_image_url"):
        if schluessel in data:
            wert = str(data[schluessel] or "").strip()
            # Leer heisst "kein eigenes Bild" und ist immer erlaubt.
            if wert and not valid_image_url(wert):
                raise ValueError(
                    "Das muss eine https-Adresse sein, die auf .png, .jpg, "
                    ".gif oder .webp endet."
                )
            aktuell[schluessel] = wert

    if "leave_channel_id" in data:
        roh = str(data["leave_channel_id"] or "0").strip()
        aktuell["leave_channel_id"] = int(roh) if roh.isdigit() else 0

    if "leave_message" in data:
        aktuell["leave_message"] = str(data["leave_message"] or "")[:2000]

    if "leave_type" in data:
        if data["leave_type"] not in ("simple", "embed"):
            raise ValueError("Unbekannter Nachrichtentyp.")
        aktuell["leave_type"] = data["leave_type"]
    if "leave_embed_data" in data:
        embed = data["leave_embed_data"] if data["leave_embed_data"] is not None else {}
        if not isinstance(embed, dict):
            raise ValueError("Die Embed-Einstellungen sind ungültig.")
        limits = {"message": 2000, "title": 256, "description": 4096, "author_name": 256, "footer_text": 2048,
                  "author_icon": 2048, "footer_icon": 2048, "image": 2048, "thumbnail": 2048, "color": 16}
        clean = {key: str(value or "") for key, value in embed.items() if key in limits}
        if any(len(value) > limits[key] for key, value in clean.items()):
            raise ValueError("Ein Embed-Feld überschreitet das Zeichenlimit.")
        if sum(len(clean.get(key, "")) for key in ("title", "description", "author_name", "footer_text")) > 6000:
            raise ValueError("Das Embed darf insgesamt höchstens 6000 Zeichen enthalten.")
        aktuell["leave_embed_data"] = clean
    if "leave_auto_delete_duration" in data:
        duration = data["leave_auto_delete_duration"]
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 86400:
            raise ValueError("Die Löschzeit muss zwischen 0 und 86400 Sekunden liegen.")
        aktuell["leave_auto_delete_duration"] = duration

    return aktuell


async def save(guild_id: int, data: dict) -> dict:
    """
    Einstellungen speichern und den Stand danach zurueckgeben.

    Zusammengefuehrt statt ersetzt: das Dashboard schickt beim Umlegen
    eines Schalters nur dieses eine Feld.
    """
    aktuell = validate_update(await get(guild_id), data)

    async with db_paths.connect(GREET_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO greet_extras (guild_id, welcome_image_enabled,"
            " welcome_image_url, leave_enabled, leave_channel_id,"
            " leave_message, leave_image_enabled, leave_image_url,"
            " leave_type, leave_embed_data, leave_auto_delete_duration)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " welcome_image_enabled = excluded.welcome_image_enabled,"
            " welcome_image_url = excluded.welcome_image_url,"
            " leave_enabled = excluded.leave_enabled,"
            " leave_channel_id = excluded.leave_channel_id,"
            " leave_message = excluded.leave_message,"
            " leave_image_enabled = excluded.leave_image_enabled,"
            " leave_image_url = excluded.leave_image_url,"
            " leave_type = excluded.leave_type,"
            " leave_embed_data = excluded.leave_embed_data,"
            " leave_auto_delete_duration = excluded.leave_auto_delete_duration",
            (
                guild_id,
                int(aktuell["welcome_image_enabled"]),
                aktuell["welcome_image_url"],
                int(aktuell["leave_enabled"]),
                aktuell["leave_channel_id"],
                aktuell["leave_message"],
                int(aktuell["leave_image_enabled"]),
                aktuell["leave_image_url"],
                aktuell["leave_type"],
                json.dumps(aktuell["leave_embed_data"]),
                aktuell["leave_auto_delete_duration"],
            ),
        )
        await db.commit()

    return aktuell


def render_text(vorlage: str, member, guild, *, limit: int | None = 2000) -> str:
    """
    Platzhalter fuellen -- dieselben wie bei der Begruessung.

    Bewusst dieselbe Liste: wer ``{user}`` bei der Begruessung kennt,
    soll beim Abschied nicht raten muessen.
    """
    if not vorlage:
        return ""

    anzahl = getattr(guild, "member_count", None) or len(
        getattr(guild, "members", []) or []
    )
    ersetzungen = {
        "{user}": getattr(member, "mention", str(member)),
        "{user.name}": getattr(member, "name", str(member)),
        "{user.display}": getattr(member, "display_name", str(member)),
        "{user.id}": str(getattr(member, "id", "")),
        "{server}": getattr(guild, "name", ""),
        "{guild}": getattr(guild, "name", ""),
        "{count}": str(anzahl),
        "{membercount}": str(anzahl),
    }
    text = vorlage
    for platzhalter, wert in ersetzungen.items():
        text = text.replace(platzhalter, wert)
    return text[:limit] if limit is not None else text


def api_settings(settings: dict) -> dict:
    """Discord snowflakes must stay strings across JSON and JavaScript."""
    return {**settings, "leave_channel_id": str(settings.get("leave_channel_id") or "")}


def message_payload(settings: dict, member, banner=None) -> dict:
    """The real departure and its preview share every field and image."""
    from utils import greet_render
    from utils.panels import Panel, embed_sections

    text = settings.get("leave_message") or "**{user.display}** hat den Server verlassen."
    if settings.get("leave_type") == "embed":
        values = greet_render.placeholders(member)
        # Keep legacy dotted placeholders working in existing messages.
        info = {key: render_text(str(value), member, member.guild, limit=None)
                for key, value in (settings.get("leave_embed_data") or {}).items()}
        embed = greet_render.build_embed(info, values)
        content = greet_render.fill(info.get("message", ""), values)
        title, sections, image, thumbnail = embed_sections(embed)
        view = Panel(title, content, *sections, accent=embed.colour.value,
                     image_url=image, thumbnail_url=thumbnail)
        if banner is not None:
            view.add_image(f"attachment://{banner.filename}")
    else:
        content = greet_render.fill(render_text(text, member, member.guild), greet_render.placeholders(member))
        view = Panel("", content, image_url=f"attachment://{banner.filename}" if banner else None)
    payload = {"view": view}
    if banner is not None:
        payload["file"] = banner
    if settings.get("leave_auto_delete_duration"):
        payload["delete_after"] = settings["leave_auto_delete_duration"]
    return payload
