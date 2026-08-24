# ╔══════════════════════════════════════════════════════════════════╗
# ║   Support-Warteraum                                              ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Warteraum im Dashboard: vier Einstellungen, mehr nicht.

    an/aus · Warteraum-Kanal · Meldekanal · Team-Rolle

Alles Uebrige steht fest in `utils/support_queue.py`: die Musik, ihre
Laenge, der Cooldown, die Erinnerungen. Auch der Text der Meldung ist
nicht mehr bearbeitbar.

Warum die Kanalliste hier entsteht und nicht im Browser
-------------------------------------------------------
Das Dashboard koennte die Kanaele ueber Discords API selbst holen,
aber dann braeuchte der Browser ein Token mit Leserechten auf den
Server. Der Bot kennt sie ohnehin -- er ist drin.

Geprueft wird dabei gleich mit, ob der Bot den Kanal ueberhaupt
betreten darf. Ein Warteraum, den der Bot nicht betreten kann, ist der
haeufigste Fall von „es passiert nichts", und man sieht ihn der
Einstellung sonst nicht an.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import support_queue as store

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
    """Alle Sprachkanaele -- mit der Frage, ob der Bot hinein darf."""

    eintraege = []
    me = getattr(guild, "me", None)
    for channel in getattr(guild, "voice_channels", []):
        can_join = False
        can_speak = False
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                can_join = bool(perms.connect and perms.view_channel)
                can_speak = bool(perms.speak)
            except Exception:  # noqa: BLE001
                pass

        eintraege.append({
            "id": str(channel.id),
            "name": channel.name,
            "category": (
                channel.category.name if channel.category is not None else None
            ),
            "can_join": can_join,
            "can_speak": can_speak,
        })

    # Kanaele, in die der Bot darf, zuerst: die anderen taugen nicht.
    eintraege.sort(key=lambda e: (not e["can_join"], e["name"].lower()))
    return eintraege


def _text_channels(guild) -> list[dict]:
    """Textkanaele -- mit der Frage, ob der Bot dort schreiben darf.

    Ein Meldekanal ohne Schreibrecht ist der haeufigste Grund dafuer,
    dass das Team nichts mitbekommt, und man sieht es der Einstellung
    nicht an.
    """
    eintraege = []
    me = getattr(guild, "me", None)
    for channel in getattr(guild, "text_channels", []):
        darf = False
        if me is not None:
            try:
                rechte = channel.permissions_for(me)
                darf = bool(rechte.view_channel and rechte.send_messages)
            except Exception:  # noqa: BLE001
                pass
        eintraege.append({
            "id": str(channel.id),
            "name": channel.name,
            "can_send": darf,
        })
    return eintraege


def _roles(guild) -> list[dict]:
    eintraege = []
    for role in getattr(guild, "roles", []):
        if getattr(role, "is_default", lambda: False)():
            continue
        eintraege.append({
            "id": str(role.id),
            "name": role.name,
            "position": getattr(role, "position", 0),
        })
    eintraege.sort(key=lambda e: -e["position"])
    return eintraege


def _lavalink_state() -> dict:
    """Gibt es einen Audio-Knoten?

    Ohne ihn bleibt der Bot draussen. Das steht im Dashboard, weil es
    sonst wie ein Fehler des Warteraums aussieht -- dabei fehlt nur
    die Verbindung zum Audio-Dienst. Die Meldung an das Team geht
    trotzdem raus.
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
                "Kein Lavalink-Knoten verbunden. Ohne ihn spielt der Bot keine "
                "Wartemusik — setze LAVALINK_HOST in Railway. Die Meldung an "
                "das Team funktioniert trotzdem."
            ),
        }
    return {"ready": True, "detail": f"{len(nodes)} Knoten verbunden."}


def _antwort(guild, record: dict) -> dict:
    """Die Einstellungen, angereichert um das, was der Browser braucht."""

    from cogs.commands.supportqueue import MUSIC_FILE, _music_url

    kanal_name = None
    if record.get("channel_id"):
        gefunden = guild.get_channel(int(record["channel_id"]))
        kanal_name = gefunden.name if gefunden is not None else None

    # Wer wartet gerade -- mit Namen, damit das Team etwas anfangen kann.
    wartende = []
    for user_id, seit in store.waiting(guild.id).items():
        member = guild.get_member(int(user_id))
        wartende.append({
            "user_id": str(user_id),
            "name": getattr(member, "display_name", str(user_id)),
            "avatar": (
                str(member.display_avatar.url)
                if member is not None and member.display_avatar
                else None
            ),
            "since": seit,
        })
    wartende.sort(key=lambda e: e["since"])

    return {
        "guild_id": str(guild.id),
        "enabled": bool(record.get("enabled")),
        # IDs immer als Zeichenkette: eine Discord-ID ist groesser als
        # das, was JavaScript als Zahl noch genau darstellen kann.
        "channel_id": (
            str(record["channel_id"]) if record.get("channel_id") else None
        ),
        "notify_channel_id": (
            str(record["notify_channel_id"])
            if record.get("notify_channel_id") else None
        ),
        "staff_role_id": (
            str(record["staff_role_id"]) if record.get("staff_role_id") else None
        ),
        "channel_name": kanal_name,
        "channel_missing": bool(record.get("channel_id")) and kanal_name is None,
        "voice_channels": _voice_channels(guild),
        "text_channels": _text_channels(guild),
        "roles": _roles(guild),
        "waiting": wartende,
        "lavalink": _lavalink_state(),
        # Was fest eingestellt ist. Steht in der Antwort, damit es im
        # Dashboard nachlesbar ist, ohne dass man es aendern kann.
        "fixed": {
            "music_file": MUSIC_FILE,
            "music_url": _music_url(),
            # Keine feste Dauer mehr: das Stueck laeuft ganz durch,
            # die Zahl ist nur der Notausgang fuer haengende Tracks.
            "max_track_seconds": store.MAX_TRACK_SECONDS,
            "ping_cooldown": store.PING_COOLDOWN,
            "reminder_seconds": store.REMINDER_SECONDS,
            "max_reminders": store.MAX_REMINDERS,
        },
    }


@router.get("/{guild_id}", summary="Einstellungen des Warteraums")
async def get_settings(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    record = await store.get(await _db(), guild_id)
    return _antwort(guild, record)


@router.post("/{guild_id}", summary="Warteraum einstellen")
async def save_settings(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Die vier Felder speichern.

    Mehr gibt es nicht: Musik, Dauer, Cooldown und Erinnerungen stehen
    fest, und der Text der Meldung ist nicht bearbeitbar.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    felder: dict = {}

    if "enabled" in data:
        felder["enabled"] = bool(data["enabled"])

    if "channel_id" in data:
        roh = data["channel_id"]
        if roh in (None, "", "0"):
            felder["channel_id"] = None
        else:
            if not str(roh).isdigit():
                raise HTTPException(
                    status_code=400, detail="Der Kanal ist keine gültige ID."
                )
            kanal = guild.get_channel(int(roh))
            if kanal is None:
                raise HTTPException(
                    status_code=400,
                    detail="Diesen Kanal gibt es auf dem Server nicht.",
                )
            # Ein Textkanal als Warteraum waere ein stiller Fehlschlag:
            # gespeichert, aber der Bot kann ihn nie betreten.
            if not hasattr(kanal, "connect"):
                raise HTTPException(
                    status_code=400,
                    detail="Der Warteraum muss ein Sprachkanal sein.",
                )
            felder["channel_id"] = int(roh)

    if "notify_channel_id" in data:
        roh = data["notify_channel_id"]
        if roh in (None, "", "0"):
            felder["notify_channel_id"] = None
        else:
            if not str(roh).isdigit():
                raise HTTPException(
                    status_code=400, detail="Der Meldekanal ist keine gültige ID."
                )
            kanal = guild.get_channel(int(roh))
            if kanal is None:
                raise HTTPException(
                    status_code=400,
                    detail="Diesen Kanal gibt es auf dem Server nicht.",
                )
            if not hasattr(kanal, "send"):
                raise HTTPException(
                    status_code=400,
                    detail="Der Meldekanal muss ein Textkanal sein.",
                )
            felder["notify_channel_id"] = int(roh)

    if "staff_role_id" in data:
        roh = data["staff_role_id"]
        if roh in (None, "", "0"):
            felder["staff_role_id"] = None
        else:
            if not str(roh).isdigit():
                raise HTTPException(
                    status_code=400, detail="Die Rolle ist keine gültige ID."
                )
            if guild.get_role(int(roh)) is None:
                raise HTTPException(
                    status_code=400,
                    detail="Diese Rolle gibt es auf dem Server nicht.",
                )
            felder["staff_role_id"] = int(roh)

    # Einschalten ohne Kanal ist kein Warteraum, sondern eine
    # Einstellung, die nie greift -- und niemand sieht warum.
    if felder.get("enabled"):
        kuenftig = felder.get("channel_id", (await store.get(db, guild_id)).get("channel_id"))
        if not kuenftig:
            raise HTTPException(
                status_code=400,
                detail="Wähle zuerst einen Warteraum-Kanal aus.",
            )

    record = await store.save(db, guild_id, **felder) if felder else await store.get(db, guild_id)

    await feature_audit.log_action(
        "supportqueue_updated",
        actor=str(data.get("actor", "dashboard")),
        detail=f"guild {guild_id}",
    )
    return _antwort(guild, record)
