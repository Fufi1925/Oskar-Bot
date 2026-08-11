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
    await db.commit()


async def get(guild_id: int) -> dict:
    async with db_paths.connect(GREET_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT welcome_image_enabled, welcome_image_url, leave_enabled,"
            " leave_channel_id, leave_message, leave_image_enabled,"
            " leave_image_url FROM greet_extras WHERE guild_id = ?",
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
    }


async def save(guild_id: int, data: dict) -> dict:
    """
    Einstellungen speichern und den Stand danach zurueckgeben.

    Zusammengefuehrt statt ersetzt: das Dashboard schickt beim Umlegen
    eines Schalters nur dieses eine Feld.
    """
    aktuell = await get(guild_id)

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

    async with db_paths.connect(GREET_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO greet_extras (guild_id, welcome_image_enabled,"
            " welcome_image_url, leave_enabled, leave_channel_id,"
            " leave_message, leave_image_enabled, leave_image_url)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " welcome_image_enabled = excluded.welcome_image_enabled,"
            " welcome_image_url = excluded.welcome_image_url,"
            " leave_enabled = excluded.leave_enabled,"
            " leave_channel_id = excluded.leave_channel_id,"
            " leave_message = excluded.leave_message,"
            " leave_image_enabled = excluded.leave_image_enabled,"
            " leave_image_url = excluded.leave_image_url",
            (
                guild_id,
                int(aktuell["welcome_image_enabled"]),
                aktuell["welcome_image_url"],
                int(aktuell["leave_enabled"]),
                aktuell["leave_channel_id"],
                aktuell["leave_message"],
                int(aktuell["leave_image_enabled"]),
                aktuell["leave_image_url"],
            ),
        )
        await db.commit()

    return aktuell


def render_text(vorlage: str, member, guild) -> str:
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
    return text[:2000]
