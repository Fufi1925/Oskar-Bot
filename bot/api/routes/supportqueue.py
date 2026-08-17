# ╔══════════════════════════════════════════════════════════════════╗
# ║   Support-Warteraum                                              ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der Warteraum im Dashboard: Kanal waehlen, Ansage schreiben, fertig.

Warum die Kanalliste hier entsteht und nicht im Browser
-------------------------------------------------------
Das Dashboard koennte die Kanaele ueber Discords API selbst holen, aber
dann braeuchte der Browser ein Token mit Leserechten auf den Server.
Der Bot kennt sie ohnehin -- er ist drin.

Geprueft wird dabei gleich mit, ob der Bot den Kanal ueberhaupt
betreten darf. Ein Warteraum, den der Bot nicht betreten kann, ist der
haeufigste Fall von "es passiert nichts", und man sieht ihn der
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

    import discord

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

        entries.append({
            "id": str(channel.id),
            "name": channel.name,
            "category": (
                channel.category.name if channel.category is not None else None
            ),
            "user_limit": getattr(channel, "user_limit", 0),
            "can_join": can_join,
            "can_speak": can_speak,
        })

    # Kanaele, in die der Bot darf, zuerst: die anderen taugen nicht.
    entries.sort(key=lambda entry: (not entry["can_join"], entry["name"].lower()))
    _ = discord  # nur fuer den Import-Check
    return entries


def _text_channels(guild) -> list[dict]:
    entries = []
    for channel in getattr(guild, "text_channels", []):
        entries.append({"id": str(channel.id), "name": channel.name})
    return entries


def _roles(guild) -> list[dict]:
    entries = []
    for role in getattr(guild, "roles", []):
        if getattr(role, "is_default", lambda: False)():
            continue
        entries.append({"id": str(role.id), "name": role.name})
    return entries


def _lavalink_state() -> dict:
    """Gibt es einen Audio-Knoten?

    Ohne ihn bleibt der Bot stumm. Das steht im Dashboard, weil es
    sonst wie ein Fehler des Warteraums aussieht -- dabei fehlt nur
    die Verbindung zum Audio-Dienst.
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
                "Kein Lavalink-Knoten verbunden. Ohne ihn betritt der Bot den "
                "Kanal nicht — setze LAVALINK_HOST in Railway."
            ),
        }
    return {"ready": True, "detail": f"{len(nodes)} Knoten verbunden."}


def _ping_limits() -> dict:
    """Die Grenzen, damit das Dashboard sie nicht doppelt pflegt.

    Stuenden sie im Browser noch einmal, waere die naechste Aenderung
    an einer der beiden Stellen still falsch -- der Nutzer bekaeme
    einen Wert angeboten, den der Server abschneidet.
    """
    return {
        "ping_cooldown": {
            "min": store.MIN_PING_COOLDOWN,
            "max": store.MAX_PING_COOLDOWN,
            "default": store.DEFAULT_PING_COOLDOWN,
        },
        "reminder_seconds": {
            "min": store.MIN_REMINDER_SECONDS,
            "max": store.MAX_REMINDER_SECONDS,
            "default": store.DEFAULT_REMINDER_SECONDS,
        },
        "max_reminders": {
            "min": 0,
            "max": store.MAX_MAX_REMINDERS,
            "default": store.DEFAULT_MAX_REMINDERS,
        },
    }


@router.get("/{guild_id}", summary="Einstellungen des Warteraums")
async def get_settings(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    record = await store.get(db, guild_id)

    channel = None
    if record.get("channel_id"):
        found = guild.get_channel(int(record["channel_id"]))
        channel = found.name if found is not None else None

    # Wer wartet gerade -- mit Namen, damit das Team etwas anfangen kann.
    people = []
    for user_id, since in store.waiting(guild_id).items():
        member = guild.get_member(int(user_id))
        people.append({
            "user_id": str(user_id),
            "name": getattr(member, "display_name", str(user_id)),
            "avatar": (
                str(member.display_avatar.url)
                if member is not None and member.display_avatar
                else None
            ),
            "since": since,
        })
    people.sort(key=lambda entry: entry["since"])

    return {
        **record,
        "guild_id": str(guild_id),
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
        "channel_name": channel,
        "channel_missing": bool(record.get("channel_id")) and channel is None,
        "waiting": people,
        "voice_channels": _voice_channels(guild),
        "text_channels": _text_channels(guild),
        "roles": _roles(guild),
        "audio": _lavalink_state(),
        "defaults": {
            "greeting": store.DEFAULT_GREETING,
            "music_seconds": store.DEFAULT_MUSIC_SECONDS,
            "min_seconds": store.MIN_MUSIC_SECONDS,
            "max_seconds": store.MAX_MUSIC_SECONDS,
            "max_greeting": store.MAX_GREETING,
        },
        # Die Grenzen des Ping-Systems -- damit der Browser sie nicht
        # noch einmal fuehrt und dabei irgendwann abweicht.
        "ping_limits": _ping_limits(),
        # Wie oft in diesem Wartelauf schon erinnert wurde. Steht im
        # Reiter, damit "es kam nichts mehr" nicht wie ein Fehler
        # aussieht, wenn nur die Obergrenze erreicht ist.
        "reminders_sent": store.reminders_sent(guild_id),
    }


@router.post("/{guild_id}", summary="Warteraum einstellen")
async def save_settings(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    fields: dict = {}

    if "channel_id" in data:
        raw = str(data.get("channel_id") or "").strip()
        if raw:
            if not raw.isdigit():
                raise HTTPException(status_code=400, detail="Ungültige Kanal-ID.")
            channel = guild.get_channel(int(raw))
            if channel is None:
                raise HTTPException(
                    status_code=404, detail="Diesen Kanal gibt es nicht mehr."
                )
            if not hasattr(channel, "connect"):
                raise HTTPException(
                    status_code=400, detail="Bitte einen Sprachkanal wählen."
                )

            # Darf der Bot da rein? Wird hier geprueft und nicht erst,
            # wenn der erste Mensch wartet -- dann faellt es niemandem
            # auf ausser dem, der vergeblich wartet.
            me = getattr(guild, "me", None)
            if me is not None:
                perms = channel.permissions_for(me)
                if not (perms.view_channel and perms.connect):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Der Bot darf »{channel.name}« nicht betreten. "
                            "Er braucht »Kanal ansehen« und »Verbinden«."
                        ),
                    )
                if not perms.speak:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Der Bot darf in »{channel.name}« nicht sprechen. "
                            "Ohne »Sprechen« gibt es weder Ansage noch Musik."
                        ),
                    )
            fields["channel_id"] = int(raw)
        else:
            fields["channel_id"] = None

    for key in ("notify_channel_id", "staff_role_id"):
        if key in data:
            raw = str(data.get(key) or "").strip()
            fields[key] = int(raw) if raw.isdigit() else None

    if "enabled" in data:
        fields["enabled"] = bool(data.get("enabled"))
    if "greeting" in data:
        fields["greeting"] = str(data.get("greeting") or "")
    if "music_url" in data:
        fields["music_url"] = str(data.get("music_url") or "").strip()
    if "music_seconds" in data:
        fields["music_seconds"] = data.get("music_seconds")

    # ── Das Ping-System ──────────────────────────────────────────────
    #
    # Die Grenzen setzt `store.save` durch -- hier wird nur
    # weitergereicht, was ankam. Zweimal dieselbe Regel zu pflegen
    # heisst, dass sie irgendwann auseinanderlaeuft.
    for schalter in ("ping_enabled", "ping_when_staff_present"):
        if schalter in data:
            fields[schalter] = bool(data.get(schalter))
    for zahl in ("ping_cooldown", "reminder_seconds", "max_reminders"):
        if zahl in data:
            fields[zahl] = data.get(zahl)

    # Anschalten ohne Kanal ergibt nichts.
    merged = {**(await store.get(db, guild_id)), **fields}
    if merged.get("enabled") and not merged.get("channel_id"):
        raise HTTPException(
            status_code=400,
            detail="Wähle erst einen Sprachkanal, dann kannst du einschalten.",
        )

    record = await store.save(db, guild_id, **fields)

    await feature_audit.log_action(
        "support_queue_saved",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=("an" if record["enabled"] else "aus")
        + f", Kanal {record.get('channel_id')}",
    )

    return {"status": "success", "result": "Gespeichert.", **record}


@router.post("/{guild_id}/test", summary="Ansage einmal abspielen")
async def test_greeting(
    guild_id: int, data: dict | None = None, bot: "universitybot" = Depends(get_bot)
):
    """Den Ablauf einmal starten, ohne auf einen Wartenden zu warten.

    Sonst muss zum Ausprobieren jemand in den Kanal gehen -- und wenn
    es nicht klappt, weiss man nicht, ob die Einstellung falsch ist
    oder der Ton fehlt.
    """

    guild = _guild_or_404(bot, guild_id)
    db = await _db()
    record = await store.get(db, guild_id)

    if not record.get("channel_id"):
        raise HTTPException(status_code=400, detail="Es ist kein Kanal gewählt.")

    channel = guild.get_channel(int(record["channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Der Kanal existiert nicht mehr.")

    audio = _lavalink_state()
    if not audio["ready"]:
        raise HTTPException(status_code=503, detail=audio["detail"])

    cog = bot.get_cog("SupportQueue")
    if cog is None:
        raise HTTPException(
            status_code=503, detail="Der Warteraum ist gerade nicht geladen."
        )

    import asyncio

    async def once():
        player = await cog._join(channel)
        if player is None:
            return
        try:
            await cog._speak_greeting(player, guild, record)
        finally:
            try:
                await player.disconnect()
            except Exception:  # noqa: BLE001
                pass

    asyncio.create_task(once())
    return {
        "status": "success",
        "result": f"Der Bot kommt gleich in »{channel.name}« und sagt es einmal auf.",
    }
