# ╔══════════════════════════════════════════════════════════════════╗
# ║   Musik                                                          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Musik-Reiter im Dashboard.

Drei Teile, in dieser Reihenfolge:

  1. **Einstellungen** -- Stammkanal, Dauerbetrieb, Lautstaerke.
  2. **Playlists** -- anlegen, ansehen, starten, loeschen.
  3. **Live** -- was gerade laeuft, mit Cover und Fortschritt, und die
     Knoepfe dazu.

Warum die Titel beim Hinzufuegen aufgeloest werden
--------------------------------------------------
Das Dashboard soll die Titel einer Playlist *zeigen*, samt Cover. Es
koennte bei jedem Seitenaufbau Lavalink befragen -- aber das dauert,
verbraucht bei den oeffentlichen Knoten ein Kontingent (sie antworten
dann mit 429) und schlaegt komplett fehl, sobald kein Knoten laeuft.
Einmal beim Hinzufuegen aufloesen und die Titel speichern ist
verlaesslicher und kostet nichts.

Warum die Steuerung hier liegt und nicht im Browser
---------------------------------------------------
Der Browser koennte Discord nicht direkt sagen "spiel weiter" -- das
kann nur der Prozess, der den Sprachkanal haelt. Jeder Knopf im
Dashboard ist deshalb ein Aufruf hierher.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import music_store as store

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


def _voice_channels(guild) -> list[dict]:
    """Sprachkanaele -- mit der Frage, ob der Bot hinein darf.

    Ein Stammkanal, den der Bot nicht betreten kann, ist der haeufigste
    Fall von "es passiert nichts", und man sieht ihn der Einstellung
    sonst nicht an.
    """

    entries = []
    for channel in getattr(guild, "voice_channels", []):
        me = getattr(guild, "me", None)
        can_join = False
        can_speak = False
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                can_join = bool(perms.connect and perms.view_channel)
                can_speak = bool(perms.speak)
            except Exception:  # noqa: BLE001
                pass

        entries.append(
            {
                "id": str(channel.id),
                "name": channel.name,
                "category": (
                    channel.category.name if channel.category is not None else None
                ),
                "can_join": can_join,
                "can_speak": can_speak,
            }
        )

    entries.sort(key=lambda entry: (not entry["can_join"], entry["name"].lower()))
    return entries


def _lavalink_state() -> dict:
    """Gibt es einen Audio-Knoten?

    Ohne ihn bleibt der Bot stumm. Das gehoert ins Dashboard, weil es
    sonst wie ein Fehler der Musik aussieht -- dabei fehlt nur die
    Verbindung zum Audio-Dienst.
    """

    try:
        import wavelink

        nodes = list(wavelink.Pool.nodes.values())
    except Exception:  # noqa: BLE001
        return {"ready": False, "detail": "wavelink ist nicht geladen."}

    if not nodes:
        return {
            "ready": False,
            "detail": (
                "Kein Lavalink-Knoten verbunden. Ohne ihn kann der Bot keine "
                "Musik abspielen — setze LAVALINK_HOST in Railway."
            ),
        }
    return {"ready": True, "detail": f"{len(nodes)} Knoten verbunden."}


def _player_for(bot, guild_id: int):
    """Der Spieler dieses Servers, oder None.

    Ueber `voice_clients` statt `guild.voice_client`: letzteres ist bei
    wavelink nicht immer gesetzt, weil `wavelink.Player` nicht von
    `VoiceClient` erbt.
    """

    for client in getattr(bot, "voice_clients", []):
        if getattr(getattr(client, "guild", None), "id", None) == guild_id:
            return client
    return None


def _track_dict(track) -> dict:
    """Ein Lavalink-Titel in der Form, die das Dashboard braucht."""

    if track is None:
        return {}
    return {
        "title": str(getattr(track, "title", "") or "Unbekannt")[:200],
        "author": str(getattr(track, "author", "") or "")[:120],
        "uri": str(getattr(track, "uri", "") or ""),
        "artwork": str(getattr(track, "artwork", "") or ""),
        "length": int(getattr(track, "length", 0) or 0),
    }


def _live_state(bot, guild_id: int) -> dict:
    """Was gerade laeuft.

    `position` ist der Stand in Millisekunden. Das Dashboard rechnet
    daraus den Balken -- und zaehlt zwischen zwei Abfragen selbst
    weiter, damit die Zeit fluessig laeuft statt zu springen.
    """

    player = _player_for(bot, guild_id)
    if player is None:
        return {"connected": False}

    channel = getattr(player, "channel", None)
    current = getattr(player, "current", None)

    # Die Warteschlange kann gross sein. Zehn Eintraege reichen fuers
    # Dashboard; die Zahl daneben sagt, wie viele es insgesamt sind.
    upcoming: list[dict] = []
    total = 0
    queue = getattr(player, "queue", None)
    if queue is not None:
        try:
            items = list(queue)
            total = len(items)
            upcoming = [_track_dict(t) for t in items[:10]]
        except Exception:  # noqa: BLE001
            pass

    return {
        "connected": True,
        "channel_id": str(channel.id) if channel is not None else None,
        "channel_name": getattr(channel, "name", None),
        "playing": bool(getattr(player, "playing", False)),
        "paused": bool(getattr(player, "paused", False)),
        "volume": int(getattr(player, "volume", 0) or 0),
        "position": int(getattr(player, "position", 0) or 0),
        "track": _track_dict(current),
        "queue": upcoming,
        "queue_total": total,
        # Damit das Dashboard weiss, wie alt die Zahl ist -- ohne das
        # laeuft der Balken nach einem langsamen Aufruf vor.
        "measured_at": time.time(),
    }


# ── Lesen ────────────────────────────────────────────────────────────


@router.get("/{guild_id}", summary="Musik-Einstellungen und Playlists")
async def get_music(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    settings = await store.get_settings(db, guild_id)
    playlists = await store.list_playlists(db, guild_id)

    return {
        "settings": settings,
        "playlists": playlists,
        "channels": _voice_channels(guild),
        "lavalink": _lavalink_state(),
        "live": _live_state(bot, guild_id),
        "limits": {
            "max_playlists": store.MAX_PLAYLISTS,
            "max_tracks": store.MAX_TRACKS,
            "max_name": store.MAX_NAME,
            "min_volume": store.MIN_VOLUME,
            "max_volume": store.MAX_VOLUME,
            "min_idle": store.MIN_IDLE_SECONDS,
            "max_idle": store.MAX_IDLE_SECONDS,
        },
    }


@router.get("/{guild_id}/live", summary="Nur der Live-Zustand")
async def get_live(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """Getrennt vom Rest, weil das Dashboard es oft abfragt.

    Der Fortschrittsbalken braucht alle paar Sekunden einen neuen
    Stand. Die Playlists dabei jedes Mal mitzuschicken waere unnoetig.
    """

    _guild_or_404(bot, guild_id)
    return _live_state(bot, guild_id)


# ── Einstellungen ────────────────────────────────────────────────────


@router.patch("/{guild_id}", summary="Einstellungen aendern")
async def patch_music(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    patch = {k: v for k, v in (data or {}).items() if k in store.DEFAULTS}

    # Einen Kanal, den der Bot nicht betreten darf, gar nicht erst
    # annehmen. Sonst steht er im Dashboard, und der Bot erscheint nie
    # -- ohne dass irgendwo stuende, warum.
    if patch.get("channel_id"):
        channel = guild.get_channel(int(patch["channel_id"]))
        if channel is None:
            raise HTTPException(404, "Diesen Sprachkanal gibt es nicht.")
        me = getattr(guild, "me", None)
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                if not (perms.connect and perms.view_channel):
                    raise HTTPException(
                        400,
                        f"Der Bot darf »{channel.name}« nicht betreten. "
                        "Bitte die Rechte des Kanals prüfen.",
                    )
                if not perms.speak:
                    raise HTTPException(
                        400,
                        f"Der Bot darf in »{channel.name}« nicht sprechen. "
                        "Ohne dieses Recht bleibt die Musik stumm.",
                    )
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                pass

    # Eine Startliste, die es nicht gibt, waere ein stiller Fehlschlag:
    # der Bot suchte sie und spielte nichts.
    if patch.get("autostart_playlist"):
        found = await store.get_playlist(
            db, guild_id, int(patch["autostart_playlist"])
        )
        if found is None:
            raise HTTPException(404, "Diese Playlist gibt es nicht.")

    settings = await store.save_settings(db, guild_id, patch)

    # Den Puffer im Cog verwerfen, sonst wirkt der Schalter erst nach
    # bis zu einer Minute -- und der Nutzer haelt es fuer kaputt.
    cog = bot.get_cog("Music")
    if cog is not None and hasattr(cog, "forget_settings"):
        cog.forget_settings(guild_id)

    await feature_audit.log_action(
        "music_settings", guild_id=guild_id, detail=str(sorted(patch))
    )
    return {"status": "success", "settings": settings}


# ── Playlists ────────────────────────────────────────────────────────


async def _resolve(query: str) -> list[dict]:
    """Eine Suche oder Adresse in Titel aufloesen.

    Gibt eine leere Liste zurueck, wenn nichts gefunden wurde. Wirft
    eine 503, wenn ueberhaupt kein Knoten da ist -- das ist kein
    "nichts gefunden", sondern ein anderer Fehler, und die Meldung
    dafuer muss eine andere sein.
    """

    try:
        import wavelink
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Der Musik-Dienst ist nicht geladen.")

    try:
        if not wavelink.Pool.nodes:
            raise HTTPException(
                503,
                "Kein Lavalink-Knoten verbunden — ohne ihn lassen sich keine "
                "Titel suchen. Bitte LAVALINK_HOST in Railway prüfen.",
            )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Der Musik-Dienst ist nicht erreichbar.")

    try:
        results = await wavelink.Playable.search(query)
    except Exception as error:  # noqa: BLE001
        # Die oeffentlichen Knoten antworten bei zu vielen Suchen mit
        # 429. Das ist kein Fehler des Nutzers, und "nichts gefunden"
        # waere die falsche Auskunft -- er suchte sonst nach besseren
        # Suchbegriffen.
        if "429" in str(error) or "rate" in str(error).lower():
            raise HTTPException(
                429,
                "Der Musik-Dienst nimmt gerade keine weiteren Suchen an. "
                "In ein paar Minuten wieder versuchen.",
            )
        raise HTTPException(502, f"Die Suche schlug fehl: {error}")

    if not results:
        return []

    # Eine Playlist-Adresse liefert ein Playlist-Objekt, eine Suche
    # eine Liste. Beides muss hier zu einer Liste werden.
    tracks = getattr(results, "tracks", None)
    if tracks is None:
        tracks = list(results)

    return [_track_dict(track) for track in tracks[: store.MAX_TRACKS]]


@router.post("/{guild_id}/playlists", summary="Playlist anlegen")
async def create_playlist(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    name = str((data or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Die Playlist braucht einen Namen.")

    if await store.count_playlists(db, guild_id) >= store.MAX_PLAYLISTS:
        raise HTTPException(
            400,
            f"Mehr als {store.MAX_PLAYLISTS} Playlists sind nicht vorgesehen. "
            "Bitte zuerst eine löschen.",
        )

    tracks: list[dict] = []
    query = str((data or {}).get("query") or "").strip()
    if query:
        tracks = await _resolve(query)
        if not tracks:
            raise HTTPException(404, f"Zu »{query}« wurde nichts gefunden.")

    playlist_id = await store.create_playlist(db, guild_id, name, tracks)
    await feature_audit.log_action(
        "music_playlist_add", guild_id=guild_id, detail=name
    )
    return {
        "status": "success",
        "playlist": await store.get_playlist(db, guild_id, playlist_id),
    }


@router.post("/{guild_id}/playlists/{playlist_id}/tracks", summary="Titel ergaenzen")
async def add_tracks(
    guild_id: int,
    playlist_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    playlist = await store.get_playlist(db, guild_id, playlist_id)
    if playlist is None:
        raise HTTPException(404, "Diese Playlist gibt es nicht.")

    query = str((data or {}).get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Bitte einen Suchbegriff oder Link angeben.")

    found = await _resolve(query)
    if not found:
        raise HTTPException(404, f"Zu »{query}« wurde nichts gefunden.")

    combined = playlist["tracks"] + found
    if len(combined) > store.MAX_TRACKS:
        raise HTTPException(
            400,
            f"Eine Playlist fasst {store.MAX_TRACKS} Titel. "
            f"Es passen noch {store.MAX_TRACKS - len(playlist['tracks'])} hinein.",
        )

    await store.update_playlist(db, guild_id, playlist_id, tracks=combined)
    return {
        "status": "success",
        "added": len(found),
        "playlist": await store.get_playlist(db, guild_id, playlist_id),
    }


@router.patch("/{guild_id}/playlists/{playlist_id}", summary="Playlist aendern")
async def patch_playlist(
    guild_id: int,
    playlist_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    name = data.get("name")
    tracks = data.get("tracks")

    if tracks is not None:
        if not isinstance(tracks, list):
            raise HTTPException(400, "»tracks« muss eine Liste sein.")
        tracks = [t for t in tracks if isinstance(t, dict)]

    ok = await store.update_playlist(
        db,
        guild_id,
        playlist_id,
        name=str(name) if name is not None else None,
        tracks=tracks,
    )
    if not ok:
        raise HTTPException(404, "Diese Playlist gibt es nicht.")

    return {
        "status": "success",
        "playlist": await store.get_playlist(db, guild_id, playlist_id),
    }


@router.delete("/{guild_id}/playlists/{playlist_id}", summary="Playlist loeschen")
async def delete_playlist(
    guild_id: int, playlist_id: int, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    if not await store.delete_playlist(db, guild_id, playlist_id):
        raise HTTPException(404, "Diese Playlist gibt es nicht.")

    await feature_audit.log_action(
        "music_playlist_delete", guild_id=guild_id, detail=str(playlist_id)
    )
    return {"status": "success"}


# ── Steuerung ────────────────────────────────────────────────────────


@router.post("/{guild_id}/control", summary="Wiedergabe steuern")
async def control(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Pause, weiter, ueberspringen, stoppen, Lautstaerke.

    Jeder Knopf im Dashboard landet hier. Der Browser kann Discord
    nicht direkt ansprechen -- nur der Prozess, der den Sprachkanal
    haelt, kann das.
    """

    _guild_or_404(bot, guild_id)
    action = str((data or {}).get("action") or "").strip().lower()

    player = _player_for(bot, guild_id)
    if player is None:
        raise HTTPException(
            409, "Der Bot ist gerade in keinem Sprachkanal dieses Servers."
        )

    try:
        if action == "pause":
            await player.pause(True)
        elif action == "resume":
            await player.pause(False)
        elif action == "skip":
            await player.skip(force=True)
        elif action == "stop":
            # Erst die Warteschlange leeren, dann trennen. Andersherum
            # startet wavelink beim Trennen noch den naechsten Titel.
            queue = getattr(player, "queue", None)
            if queue is not None:
                try:
                    queue.clear()
                except Exception:  # noqa: BLE001
                    pass
            await player.disconnect()
        elif action == "volume":
            level = store.clamp_volume((data or {}).get("value"))
            await player.set_volume(level)
            # Und merken. Der Regler hier ist der einzige -- in den
            # Einstellungen oben stand frueher ein zweiter, was
            # verwirrte: zwei Regler fuer eine Zahl, und der obere
            # wirkte erst beim naechsten Titel.
            #
            # Ohne das Speichern waere die Lautstaerke nach dem
            # naechsten Neustart wieder auf 60, obwohl sie sichtbar
            # anders eingestellt war.
            await store.save_settings(await _db(), guild_id, {"volume": level})
            cog = bot.get_cog("Music")
            if cog is not None and hasattr(cog, "forget_settings"):
                cog.forget_settings(guild_id)
        elif action == "seek":
            # In Millisekunden, wie Lavalink es erwartet.
            try:
                position = int((data or {}).get("value") or 0)
            except (TypeError, ValueError):
                raise HTTPException(400, "»value« muss eine Zahl sein.")
            await player.seek(max(0, position))
        else:
            raise HTTPException(400, f"Unbekannte Aktion »{action}«.")
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(502, f"Das hat nicht geklappt: {error}")

    await feature_audit.log_action(
        "music_control", guild_id=guild_id, detail=action
    )
    return {"status": "success", "live": _live_state(bot, guild_id)}


@router.post("/{guild_id}/play", summary="Eine Playlist starten")
async def play_playlist(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Eine gespeicherte Liste im Stammkanal abspielen."""

    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    try:
        playlist_id = int((data or {}).get("playlist_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "»playlist_id« muss eine Zahl sein.")

    playlist = await store.get_playlist(db, guild_id, playlist_id)
    if playlist is None:
        raise HTTPException(404, "Diese Playlist gibt es nicht.")
    if not playlist["tracks"]:
        raise HTTPException(400, "Diese Playlist ist leer.")

    cog = bot.get_cog("Music")
    if cog is None or not hasattr(cog, "start_playlist"):
        raise HTTPException(503, "Der Musik-Teil des Bots ist nicht geladen.")

    settings = await store.get_settings(db, guild_id)
    channel_id = settings.get("channel_id")
    if not channel_id:
        raise HTTPException(
            400,
            "Es ist kein Stammkanal eingestellt — ohne ihn weiß der Bot "
            "nicht, wo er spielen soll.",
        )

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        raise HTTPException(404, "Den eingestellten Stammkanal gibt es nicht mehr.")

    ok, detail = await cog.start_playlist(
        guild, channel, playlist["tracks"], settings.get("volume")
    )
    if not ok:
        raise HTTPException(502, detail)

    await feature_audit.log_action(
        "music_play", guild_id=guild_id, detail=playlist["name"]
    )
    return {"status": "success", "detail": detail, "live": _live_state(bot, guild_id)}
