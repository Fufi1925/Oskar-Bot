"""
Musik: Stammkanal, Dauerbetrieb und gespeicherte Playlists.

Was hier eingestellt wird
-------------------------
Bisher lebte die Musik nur im Chat: `>play` ruft den Bot in den Kanal,
in dem der Aufrufer gerade steht, und nach zwei Minuten Leerlauf geht
er wieder. Fuer einen Server, der dauerhaft Musik laufen lassen will,
war das nichts.

Drei Dinge kommen dazu:

  * **Stammkanal** -- ein fester Sprachkanal. Der Bot ist dort, statt
    dem Aufrufer hinterherzulaufen.
  * **Dauerbetrieb (24/7)** -- er bleibt auch dann, wenn niemand mehr
    zuhoert, statt nach zwei Minuten zu gehen.
  * **Playlists** -- gespeicherte Listen, die sich im Dashboard anlegen
    und starten lassen. Eine davon kann als Startliste markiert sein:
    sobald jemand den Stammkanal betritt, laeuft sie los.

Warum die Titel hier gespeichert werden und nicht nur die Playlist-URL
----------------------------------------------------------------------
Eine gespeicherte YouTube-Adresse waere weniger Code, aber das
Dashboard soll die Titel *zeigen*, samt Cover -- und dafuer muesste es
sonst bei jedem Seitenaufbau Lavalink befragen. Das dauert, kostet ein
Kontingent bei den oeffentlichen Knoten und schlaegt fehl, sobald kein
Knoten erreichbar ist. Einmal beim Hinzufuegen aufloesen und die Titel
behalten ist verlaesslicher.

Die Cover-Adressen sind dabei bewusst mitgespeichert: sie zeigen auf
Discords oder YouTubes CDN und aendern sich nicht.

Speicher
--------
`db/music.db`. Braucht ein Railway-Volume, sonst sind Stammkanal und
Playlists nach jedem Deploy weg.
"""

from __future__ import annotations

import json
import time

import aiosqlite

DB_PATH = "db/music.db"

# Discords Grenze fuer einen Playlist-Namen ist keine echte -- sie
# steht nur im Dashboard. 80 passt in eine Knopfbeschriftung, falls die
# Liste eines Tages als Auswahlmenue auftaucht.
MAX_NAME = 80

# Eine Playlist mit tausend Titeln waere im Dashboard unbenutzbar und
# im Speicher unnoetig gross. Discords Auswahlmenues fassen ohnehin nur
# 25 Eintraege.
MAX_TRACKS = 200
MAX_PLAYLISTS = 25

# Wie lange der Bot ohne Zuhoerer bleibt, bevor er geht. In Sekunden.
# Nur wirksam, wenn der Dauerbetrieb aus ist.
DEFAULT_IDLE_SECONDS = 120
MIN_IDLE_SECONDS = 30
MAX_IDLE_SECONDS = 3600

# Lautstaerke, mit der ein Titel startet. Lavalink erlaubt bis 1000,
# aber alles ueber 200 uebersteuert hoerbar.
DEFAULT_VOLUME = 60
MIN_VOLUME = 0
MAX_VOLUME = 200


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS music_settings (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            stay_forever INTEGER DEFAULT 0,
            autostart INTEGER DEFAULT 0,
            autostart_playlist INTEGER,
            volume INTEGER DEFAULT 60,
            idle_seconds INTEGER DEFAULT 120,
            updated_at REAL DEFAULT 0
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS music_playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            tracks TEXT NOT NULL DEFAULT '[]',
            created_at REAL DEFAULT 0,
            updated_at REAL DEFAULT 0
        )
        """
    )
    # Ohne diesen Index liest jede Abfrage die ganze Tabelle. Bei 25
    # Playlists pro Server faellt das nicht auf -- bei tausend Servern
    # schon.
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_music_playlists_guild "
        "ON music_playlists (guild_id)"
    )
    await db.commit()


DEFAULTS: dict[str, object] = {
    "channel_id": None,
    "stay_forever": 0,
    "autostart": 0,
    "autostart_playlist": None,
    "volume": DEFAULT_VOLUME,
    "idle_seconds": DEFAULT_IDLE_SECONDS,
}


async def get_settings(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Die Einstellungen eines Servers, immer vollstaendig.

    Fehlt die Zeile, kommen die Voreinstellungen zurueck -- der
    Aufrufer muss nicht zwischen "nie eingestellt" und "auf Standard
    gesetzt" unterscheiden.
    """

    async with db.execute(
        "SELECT channel_id, stay_forever, autostart, autostart_playlist, "
        "volume, idle_seconds FROM music_settings WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return dict(DEFAULTS)

    return {
        "channel_id": row[0],
        "stay_forever": int(row[1] or 0),
        "autostart": int(row[2] or 0),
        "autostart_playlist": row[3],
        "volume": int(row[4] if row[4] is not None else DEFAULT_VOLUME),
        "idle_seconds": int(row[5] or DEFAULT_IDLE_SECONDS),
    }


def clamp_volume(value) -> int:
    """Lautstaerke in einen sinnvollen Bereich zwingen.

    Ein negativer Wert oder eine 5000 kommen nicht von einem Menschen,
    der es so meint -- sie kommen von einem Tippfehler oder einem
    direkten API-Aufruf. Lavalink nimmt beides an und uebersteuert.
    """

    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME
    return max(MIN_VOLUME, min(MAX_VOLUME, number))


def clamp_idle(value) -> int:
    """Leerlaufzeit begrenzen.

    Unter 30 Sekunden wuerde der Bot mitten in einer Gespraechspause
    gehen; ueber einer Stunde ist es kein Leerlauf mehr, sondern
    Dauerbetrieb -- und dafuer gibt es den Schalter.
    """

    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_IDLE_SECONDS
    return max(MIN_IDLE_SECONDS, min(MAX_IDLE_SECONDS, number))


async def save_settings(
    db: aiosqlite.Connection, guild_id: int, patch: dict
) -> dict:
    """Einstellungen aendern und den neuen Stand zurueckgeben.

    Nur die uebergebenen Felder werden angefasst. Ein Dashboard, das
    einen Schalter umlegt, schickt nicht den ganzen Zustand mit -- und
    duerfte sonst versehentlich alles andere ueberschreiben.
    """

    current = await get_settings(db, guild_id)
    merged = dict(current)

    for key in DEFAULTS:
        if key not in patch:
            continue
        value = patch[key]
        if key in ("stay_forever", "autostart"):
            merged[key] = 1 if value else 0
        elif key == "volume":
            merged[key] = clamp_volume(value)
        elif key == "idle_seconds":
            merged[key] = clamp_idle(value)
        elif key in ("channel_id", "autostart_playlist"):
            merged[key] = int(value) if value else None
        else:
            merged[key] = value

    await db.execute(
        """
        INSERT INTO music_settings
            (guild_id, channel_id, stay_forever, autostart,
             autostart_playlist, volume, idle_seconds, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            stay_forever = excluded.stay_forever,
            autostart = excluded.autostart,
            autostart_playlist = excluded.autostart_playlist,
            volume = excluded.volume,
            idle_seconds = excluded.idle_seconds,
            updated_at = excluded.updated_at
        """,
        (
            guild_id,
            merged["channel_id"],
            merged["stay_forever"],
            merged["autostart"],
            merged["autostart_playlist"],
            merged["volume"],
            merged["idle_seconds"],
            time.time(),
        ),
    )
    await db.commit()
    return merged


# ── Playlists ────────────────────────────────────────────────────────


def _load_tracks(raw) -> list[dict]:
    """Die Titelliste aus der Spalte lesen.

    Wirft nie. Eine kaputte Zeile -- etwa aus einer aelteren Version
    oder von Hand bearbeitet -- gibt eine leere Liste, statt das ganze
    Dashboard mit einem 500er lahmzulegen.
    """

    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []

    clean: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        clean.append(
            {
                "title": str(entry.get("title") or "Unbekannt")[:200],
                "author": str(entry.get("author") or "")[:120],
                "uri": str(entry.get("uri") or ""),
                "artwork": str(entry.get("artwork") or ""),
                "length": int(entry.get("length") or 0),
            }
        )
    return clean


async def list_playlists(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    async with db.execute(
        "SELECT id, name, tracks, created_at, updated_at "
        "FROM music_playlists WHERE guild_id = ? ORDER BY name COLLATE NOCASE",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    result = []
    for row in rows:
        tracks = _load_tracks(row[2])
        result.append(
            {
                "id": row[0],
                "name": row[1],
                "tracks": tracks,
                "count": len(tracks),
                # Die Gesamtlaenge einmal hier rechnen statt in jedem
                # Aufrufer. Lavalink liefert Millisekunden.
                "length": sum(t["length"] for t in tracks),
                "created_at": row[3],
                "updated_at": row[4],
            }
        )
    return result


async def get_playlist(
    db: aiosqlite.Connection, guild_id: int, playlist_id: int
) -> dict | None:
    """Eine einzelne Liste -- mit guild_id im WHERE.

    Ohne die guild_id koennte ein Server die Playlist eines anderen
    lesen oder loeschen, indem er einfach eine fremde Nummer schickt.
    Die Nummern sind fortlaufend und damit trivial zu raten.
    """

    async with db.execute(
        "SELECT id, name, tracks, created_at, updated_at "
        "FROM music_playlists WHERE id = ? AND guild_id = ?",
        (playlist_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None

    tracks = _load_tracks(row[2])
    return {
        "id": row[0],
        "name": row[1],
        "tracks": tracks,
        "count": len(tracks),
        "length": sum(t["length"] for t in tracks),
        "created_at": row[3],
        "updated_at": row[4],
    }


async def count_playlists(db: aiosqlite.Connection, guild_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM music_playlists WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def create_playlist(
    db: aiosqlite.Connection, guild_id: int, name: str, tracks: list[dict]
) -> int:
    now = time.time()
    cursor = await db.execute(
        "INSERT INTO music_playlists (guild_id, name, tracks, created_at, "
        "updated_at) VALUES (?, ?, ?, ?, ?)",
        (
            guild_id,
            str(name or "Ohne Namen")[:MAX_NAME],
            json.dumps(tracks[:MAX_TRACKS], ensure_ascii=False),
            now,
            now,
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def update_playlist(
    db: aiosqlite.Connection,
    guild_id: int,
    playlist_id: int,
    *,
    name: str | None = None,
    tracks: list[dict] | None = None,
) -> bool:
    """Namen oder Titel aendern. False, wenn es die Liste nicht gibt."""

    existing = await get_playlist(db, guild_id, playlist_id)
    if existing is None:
        return False

    new_name = str(name if name is not None else existing["name"])[:MAX_NAME]
    new_tracks = tracks if tracks is not None else existing["tracks"]

    await db.execute(
        "UPDATE music_playlists SET name = ?, tracks = ?, updated_at = ? "
        "WHERE id = ? AND guild_id = ?",
        (
            new_name,
            json.dumps(new_tracks[:MAX_TRACKS], ensure_ascii=False),
            time.time(),
            playlist_id,
            guild_id,
        ),
    )
    await db.commit()
    return True


async def delete_playlist(
    db: aiosqlite.Connection, guild_id: int, playlist_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM music_playlists WHERE id = ? AND guild_id = ?",
        (playlist_id, guild_id),
    )
    await db.commit()

    # Eine geloeschte Startliste darf nicht als Nummer stehen bleiben --
    # der Bot suchte sie beim naechsten Start vergeblich und spielte
    # stumm nichts, ohne dass jemand den Grund saehe.
    if cursor.rowcount:
        settings = await get_settings(db, guild_id)
        if settings["autostart_playlist"] == playlist_id:
            await save_settings(db, guild_id, {"autostart_playlist": None})

    return bool(cursor.rowcount)
