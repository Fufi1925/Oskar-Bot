"""
Die Verabschiedung -- Einstellungen pro Server.

Gegenstueck zur Begruessung in ``db/welcome.db``, mit demselben Aufbau:
Kanal, Art der Nachricht, Text, optional ein Embed. Zwei Dinge kommen
dazu, und die gibt es jetzt auf beiden Seiten:

  * **``card_enabled``** -- ob das gezeichnete Bild mitgeschickt wird.
    Vorher war das Willkommensbild fest an: wer es nicht wollte, konnte
    es nicht abschalten.
  * **``card_image_url``** -- ein eigenes Bild statt des gezeichneten.
    Wer ein fertiges Banner hat, haengt es hier ein.

Eine eigene Datei statt einer zweiten Tabelle in ``welcome.db``: die
Begruessung wird an sechs Stellen gelesen, teils mit ``SELECT`` ueber
feste Spaltenlisten. Eine Tabelle danebenzusetzen waere harmlos, aber
die Datei sauber zu trennen macht ein Volume-Problem sichtbar, statt
es zu verstecken.
"""

from __future__ import annotations

import json

from utils import db_paths

LEAVE_DB = "db/leave.db"

# Was in einer Verabschiedung ersetzt wird. Absichtlich dieselben
# Platzhalter wie bei der Begruessung -- wer den einen Text kennt, kann
# auch den anderen schreiben.
PLACEHOLDERS = {
    "{user}": "Erwaehnung des Mitglieds",
    "{user.name}": "Name ohne Erwaehnung",
    "{user.mention}": "Erwaehnung des Mitglieds",
    "{user.id}": "ID des Mitglieds",
    "{server}": "Name des Servers",
    "{guild}": "Name des Servers",
    "{membercount}": "Mitglieder nach dem Austritt",
}


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS leave ("
        " guild_id INTEGER PRIMARY KEY,"
        " enabled INTEGER DEFAULT 0,"
        " leave_type TEXT DEFAULT 'simple',"
        " leave_message TEXT,"
        " channel_id INTEGER,"
        " embed_data TEXT,"
        " auto_delete_duration INTEGER,"
        " card_enabled INTEGER DEFAULT 1,"
        " card_image_url TEXT)"
    )
    await db.commit()


DEFAULT = {
    "enabled": False,
    "leave_type": "simple",
    "leave_message": None,
    "channel_id": None,
    "embed_data": None,
    "auto_delete_duration": None,
    "card_enabled": True,
    "card_image_url": None,
}


async def get(guild_id: int) -> dict:
    async with db_paths.connect(LEAVE_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT enabled, leave_type, leave_message, channel_id, embed_data,"
            " auto_delete_duration, card_enabled, card_image_url"
            " FROM leave WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return {"guild_id": str(guild_id), **DEFAULT}

    return {
        "guild_id": str(guild_id),
        "enabled": bool(row[0]),
        "leave_type": row[1] or "simple",
        "leave_message": row[2],
        # Als String: Discord-IDs sind groesser als was JavaScript
        # unfallfrei als Zahl haelt.
        "channel_id": str(row[3]) if row[3] else None,
        "embed_data": row[4],
        "auto_delete_duration": row[5],
        "card_enabled": bool(row[6]) if row[6] is not None else True,
        "card_image_url": row[7],
    }


async def save(guild_id: int, data: dict) -> dict:
    """Teilweise speichern -- nur was mitgeschickt wurde."""
    aktuell = await get(guild_id)

    for schluessel in ("enabled", "card_enabled"):
        if schluessel in data:
            aktuell[schluessel] = bool(data[schluessel])

    if "leave_type" in data:
        art = str(data["leave_type"] or "simple").strip().lower()
        aktuell["leave_type"] = art if art in ("simple", "embed") else "simple"

    if "leave_message" in data:
        wert = data["leave_message"]
        aktuell["leave_message"] = str(wert)[:2000] if wert else None

    if "channel_id" in data:
        wert = str(data["channel_id"] or "").strip()
        aktuell["channel_id"] = wert if wert.isdigit() else None

    if "embed_data" in data:
        wert = data["embed_data"]
        if wert is None:
            aktuell["embed_data"] = None
        elif isinstance(wert, str):
            aktuell["embed_data"] = wert
        else:
            aktuell["embed_data"] = json.dumps(wert)

    if "auto_delete_duration" in data:
        try:
            dauer = int(data["auto_delete_duration"] or 0)
        except (TypeError, ValueError):
            dauer = 0
        # Null heisst "nicht loeschen". Alles ueber einer Stunde ist
        # kein automatisches Aufraeumen mehr.
        aktuell["auto_delete_duration"] = max(0, min(3600, dauer)) or None

    if "card_image_url" in data:
        url = str(data["card_image_url"] or "").strip()
        # Nur http(s). Ein anderes Schema laesst Discord ohnehin nicht
        # zu, und es waere eine offene Tuer fuer merkwuerdige Eingaben.
        aktuell["card_image_url"] = url[:500] if url.startswith(("http://", "https://")) else None

    async with db_paths.connect(LEAVE_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO leave (guild_id, enabled, leave_type, leave_message,"
            " channel_id, embed_data, auto_delete_duration, card_enabled,"
            " card_image_url)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " enabled = excluded.enabled,"
            " leave_type = excluded.leave_type,"
            " leave_message = excluded.leave_message,"
            " channel_id = excluded.channel_id,"
            " embed_data = excluded.embed_data,"
            " auto_delete_duration = excluded.auto_delete_duration,"
            " card_enabled = excluded.card_enabled,"
            " card_image_url = excluded.card_image_url",
            (
                guild_id,
                int(aktuell["enabled"]),
                aktuell["leave_type"],
                aktuell["leave_message"],
                int(aktuell["channel_id"]) if aktuell["channel_id"] else None,
                aktuell["embed_data"],
                aktuell["auto_delete_duration"],
                int(aktuell["card_enabled"]),
                aktuell["card_image_url"],
            ),
        )
        await db.commit()

    return aktuell


def fill(text: str | None, member, member_count: int) -> str | None:
    """Platzhalter ersetzen. Gibt ``None`` zurueck, wenn nichts da ist."""
    if not text:
        return None

    guild_name = getattr(getattr(member, "guild", None), "name", "")
    ersetzungen = {
        "{user}": getattr(member, "mention", str(member)),
        "{user.mention}": getattr(member, "mention", str(member)),
        "{user.name}": getattr(member, "display_name", str(member)),
        "{user.id}": str(getattr(member, "id", "")),
        "{server}": guild_name,
        "{guild}": guild_name,
        "{membercount}": f"{member_count:,}".replace(",", "."),
    }
    for platzhalter, wert in ersetzungen.items():
        text = text.replace(platzhalter, wert)
    return text
