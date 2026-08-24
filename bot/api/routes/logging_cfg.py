# ╔══════════════════════════════════════════════════════════════════╗
# ║   Logging                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The logging tab.

Replaces the pair of handlers in guilds.py. Three things were wrong with
those:

  * The cog logs nine categories. The dashboard listed six, so emoji,
    reaction and server-update logging could only be reached with a chat
    command -- and `/log status` reported them as "not configured"
    forever.
  * `ignore_channels`, `ignore_roles` and `ignore_users` were shown as
    bare counts. There was no way to add or remove one from the web.
  * Nothing checked whether the chosen channel still existed or whether
    the bot could post in it, which is what almost every "logging is
    broken" report turns out to be.

The cog stays the source of truth: everything here goes through
`Logging._save_log_config`, the same method the chat commands call, so
the JSON file and the in-memory cache never drift apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils.panels import from_embed

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


# Keep this in step with LOG_CATEGORIES in cogs/commands/logging.py.
# A key that is not in the cog's list is silently never logged, so the
# names are asserted against it on the first request rather than trusted.
CATEGORIES: dict[str, dict[str, str]] = {
    "message_events": {
        "label": "Nachrichten",
        "description": "Bearbeitete und gelöschte Nachrichten, mit dem alten Text.",
    },
    "join_leave_events": {
        "label": "Beitritt & Austritt",
        "description": "Wer kommt, wer geht, und wie alt das Konto war.",
    },
    "member_moderation": {
        "label": "Moderation",
        "description": "Banns, Entbannungen, Timeouts und Namensänderungen.",
    },
    "voice_events": {
        "label": "Sprachkanäle",
        "description": "Betreten, Verlassen und Wechseln von Sprachkanälen.",
    },
    "channel_events": {
        "label": "Kanäle",
        "description": "Kanäle angelegt, gelöscht oder umbenannt.",
    },
    "role_events": {
        "label": "Rollen",
        "description": "Rollen angelegt, gelöscht oder in den Rechten geändert.",
    },
    "emoji_events": {
        "label": "Emojis",
        "description": "Server-Emojis hinzugefügt oder entfernt.",
    },
    "reaction_events": {
        "label": "Reaktionen",
        "description": "Reaktionen gesetzt und entfernt. Kann viel werden.",
    },
    "system_events": {
        "label": "Server",
        "description": "Servername, Symbol und andere Server-Einstellungen.",
    },
}

# The categories that fire often enough to be worth a warning.
NOISY = {"reaction_events", "message_events", "voice_events"}


def _cog(bot):
    cog = bot.get_cog("Logging")
    if cog is None:
        raise HTTPException(
            status_code=503,
            detail="Das Protokoll-Modul ist gerade nicht geladen.",
        )
    return cog


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


def _config(cog, guild_id: int) -> dict:
    raw = cog.config_cache.get(guild_id) or {}
    return {
        "log_channels": dict(raw.get("log_channels") or {}),
        "log_enabled": dict(raw.get("log_enabled") or {}),
        "ignore_channels": list(raw.get("ignore_channels") or []),
        "ignore_roles": list(raw.get("ignore_roles") or []),
        "ignore_users": list(raw.get("ignore_users") or []),
        "auto_delete_duration": raw.get("auto_delete_duration"),
    }


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None

    # Darf der Bot dort überhaupt schreiben?
    #
    # Ohne diese Angabe sieht ein Kanal ohne Schreibrecht im Dashboard
    # genauso aus wie einer mit -- angeschaltet, Kanal gewählt, alles
    # grün, und es kommt trotzdem nie ein Eintrag an. Das ist die
    # häufigste Ursache hinter "Logging geht nicht".
    cannot_post = False
    if channel is not None and guild is not None and guild.me is not None:
        try:
            permissions = channel.permissions_for(guild.me)
            cannot_post = not (
                permissions.view_channel and permissions.send_messages
            )
        except Exception:
            # Ein Kanaltyp ohne permissions_for (oder ein Fake im Test)
            # darf die ganze Antwort nicht kosten.
            cannot_post = False

    return {
        # Snowflakes travel as strings: a JSON number loses the last digits.
        "id": str(channel_id) if channel_id else None,
        "name": getattr(channel, "name", None),
        "missing": channel is None and bool(channel_id),
        "cannot_post": cannot_post,
    }


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    colour = getattr(role, "color", None)
    return {
        "id": str(role_id) if role_id else None,
        "name": getattr(role, "name", None),
        "colour": getattr(colour, "value", colour) if colour is not None else None,
        "missing": role is None and bool(role_id),
    }


def _member_info(guild, user_id):
    member = guild.get_member(int(user_id)) if guild and user_id else None
    avatar = getattr(member, "display_avatar", None)
    return {
        "id": str(user_id) if user_id else None,
        "name": getattr(member, "display_name", None),
        "avatar": str(avatar.url) if avatar is not None else None,
        "missing": member is None and bool(user_id),
    }


def _warnings(guild, config: dict) -> list[str]:
    """Everything standing between this configuration and it working."""
    problems: list[str] = []
    if guild is None:
        return problems

    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None) if me is not None else None

    if perms is not None and not getattr(perms, "view_audit_log", False):
        problems.append(
            "Ohne „Audit-Log einsehen“ steht bei Banns und gelöschten "
            "Nachrichten nicht, wer es war."
        )

    enabled = config["log_enabled"]
    channels = config["log_channels"]

    for key in CATEGORIES:
        if not enabled.get(key):
            continue
        channel_id = channels.get(key)
        label = CATEGORIES[key]["label"]

        if not channel_id:
            problems.append(f"„{label}“ ist an, aber ohne Kanal wird nichts gepostet.")
            continue

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            problems.append(f"Der Kanal für „{label}“ existiert nicht mehr.")
            continue

        if me is not None:
            channel_perms = channel.permissions_for(me)
            if not channel_perms.send_messages:
                problems.append(
                    f"Der Bot darf in #{channel.name} nicht schreiben — "
                    f"„{label}“ läuft ins Leere."
                )
            elif not channel_perms.embed_links:
                problems.append(
                    f"Ohne „Links einbetten“ in #{channel.name} bleiben die "
                    f"Einträge für „{label}“ leer."
                )

    # A category pointing at a channel but switched off is the single most
    # common "why is nothing logged" case, so it gets said out loud.
    half = [
        CATEGORIES[k]["label"]
        for k in CATEGORIES
        if channels.get(k) and not enabled.get(k)
    ]
    if half:
        problems.append(
            "Kanal gesetzt, aber ausgeschaltet: " + ", ".join(half) + "."
        )

    for channel_id in config["ignore_channels"]:
        if guild.get_channel(int(channel_id)) is None:
            problems.append(f"Ein ausgenommener Kanal ({channel_id}) existiert nicht mehr.")
    for role_id in config["ignore_roles"]:
        if guild.get_role(int(role_id)) is None:
            problems.append(f"Eine ausgenommene Rolle ({role_id}) existiert nicht mehr.")

    return problems


async def _save(cog, guild_id: int, config: dict):
    """Hand the whole configuration back to the cog in one go."""
    await cog._save_log_config(
        guild_id,
        config["log_channels"],
        config["log_enabled"],
        config["ignore_channels"],
        config["ignore_roles"],
        config["ignore_users"],
        config["auto_delete_duration"],
    )


def _as_id(value, what: str) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{what} ist keine gültige ID.")
    if number <= 0:
        raise HTTPException(status_code=400, detail=f"{what} ist keine gültige ID.")
    return number


@router.get("/{guild_id}", summary="Logging settings")
async def get_logging(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    cog = _cog(bot)
    guild = bot.get_guild(guild_id)
    config = _config(cog, guild_id)

    categories = []
    for key, spec in CATEGORIES.items():
        channel_id = config["log_channels"].get(key)
        categories.append({
            "key": key,
            "label": spec["label"],
            "description": spec["description"],
            "noisy": key in NOISY,
            "enabled": bool(config["log_enabled"].get(key)),
            "channel": str(channel_id) if channel_id else None,
            "channel_info": _channel_info(guild, channel_id),
        })

    active = sum(1 for c in categories if c["enabled"] and c["channel"])

    return {
        "guild_id": str(guild_id),
        "categories": categories,
        "active_count": active,
        "ignore_channels": [str(c) for c in config["ignore_channels"]],
        "ignore_channels_info": [
            _channel_info(guild, c) for c in config["ignore_channels"]
        ],
        "ignore_roles": [str(r) for r in config["ignore_roles"]],
        "ignore_roles_info": [_role_info(guild, r) for r in config["ignore_roles"]],
        "ignore_users": [str(u) for u in config["ignore_users"]],
        "ignore_users_info": [_member_info(guild, u) for u in config["ignore_users"]],
        "auto_delete_duration": config["auto_delete_duration"],
        "warnings": _warnings(guild, config),
    }


@router.patch("/{guild_id}", summary="Change the logging settings")
async def patch_logging(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Partial by design: only the keys actually sent are written, so two
    people editing different cards cannot overwrite each other.
    """
    cog = _cog(bot)
    _guild_or_404(bot, guild_id)
    config = _config(cog, guild_id)

    for raw_key, values in (data.get("categories") or {}).items():
        if raw_key not in CATEGORIES:
            raise HTTPException(
                status_code=400, detail=f"Unbekannte Kategorie: {raw_key}"
            )
        if not isinstance(values, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Die Kategorie {raw_key} braucht ein Objekt.",
            )

        if "enabled" in values:
            config["log_enabled"][raw_key] = bool(values["enabled"])

        if "channel" in values:
            channel = values["channel"]
            if channel in (None, "", "0"):
                config["log_channels"].pop(raw_key, None)
                # A category without a channel cannot log, so it does not
                # get to claim it is on.
                config["log_enabled"][raw_key] = False
            else:
                config["log_channels"][raw_key] = _as_id(channel, "Der Kanal")

    for field, label in (
        ("ignore_channels", "Der Kanal"),
        ("ignore_roles", "Die Rolle"),
        ("ignore_users", "Das Mitglied"),
    ):
        if field not in data:
            continue
        values = data[field]
        if not isinstance(values, list):
            raise HTTPException(
                status_code=400, detail=f"„{field}“ muss eine Liste sein."
            )
        # dict.fromkeys keeps the order the user built the list in; a set
        # would shuffle it on every save.
        config[field] = list(dict.fromkeys(_as_id(v, label) for v in values))

    if "auto_delete_duration" in data:
        value = data["auto_delete_duration"]
        if value in (None, "", 0, "0"):
            config["auto_delete_duration"] = None
        else:
            seconds = _as_id(value, "Die Löschdauer")
            if seconds > 86400:
                raise HTTPException(
                    status_code=400,
                    detail="Höchstens 86400 Sekunden (ein Tag).",
                )
            config["auto_delete_duration"] = seconds

    await _save(cog, guild_id, config)
    return {"result": "Protokoll-Einstellungen gespeichert."}


@router.post("/{guild_id}/test/{category}", summary="Post a test entry")
async def test_logging(
    guild_id: int, category: str, bot: "universitybot" = Depends(get_bot)
):
    """
    Post one real entry into the configured channel.

    Worth its own endpoint: "the channel is set and the switch is on" and
    "the message actually arrives" are different questions, and only the
    second one is the one people care about.
    """
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unbekannte Kategorie: {category}")

    cog = _cog(bot)
    guild = _guild_or_404(bot, guild_id)
    config = _config(cog, guild_id)

    channel_id = config["log_channels"].get(category)
    if not channel_id:
        raise HTTPException(
            status_code=400,
            detail=f"Für „{CATEGORIES[category]['label']}“ ist kein Kanal gesetzt.",
        )

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        raise HTTPException(status_code=400, detail="Diesen Kanal gibt es nicht mehr.")

    import discord

    embed = discord.Embed(
        title="Test",
        description=(
            f"So sieht ein Eintrag für **{CATEGORIES[category]['label']}** aus. "
            "Diese Nachricht kam aus dem Dashboard."
        ),
        colour=discord.Colour.blurple(),
    )

    try:
        await channel.send(view=from_embed(embed))
    except discord.Forbidden:
        raise HTTPException(
            status_code=400,
            detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
        )
    except discord.HTTPException as err:
        raise HTTPException(status_code=400, detail=f"Discord lehnte ab: {err}")

    return {"result": f"Testeintrag in #{channel.name} gepostet."}


@router.post("/{guild_id}/all", summary="Point every category at one channel")
async def set_all(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    The usual first setup: one #logs channel for everything.

    Doing that by hand meant nine dropdowns and nine switches.
    """
    cog = _cog(bot)
    guild = _guild_or_404(bot, guild_id)
    config = _config(cog, guild_id)

    channel_id = _as_id(data.get("channel"), "Der Kanal")
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=400, detail="Diesen Kanal gibt es nicht.")

    # Reactions fire on every single emoji click. Opting into that has to
    # be a deliberate act, not a side effect of pressing "all of them".
    include_noisy = bool(data.get("include_noisy"))

    for key in CATEGORIES:
        if key == "reaction_events" and not include_noisy:
            continue
        config["log_channels"][key] = channel_id
        config["log_enabled"][key] = True

    await _save(cog, guild_id, config)
    count = len(CATEGORIES) - (0 if include_noisy else 1)
    return {"result": f"{count} Kategorien posten jetzt in #{channel.name}."}


# ══════════════════════════════════════════════════════════════════════
#  Bot-Logs: alles, was der Bot protokolliert, an einer Stelle
# ══════════════════════════════════════════════════════════════════════
#
# Die neun Kategorien oben sind das, was auf DISCORD passiert:
# Nachrichten, Rollen, Kanäle. Daneben protokollieren einzelne Module
# das, was der BOT selbst tut -- ein Softban durch den Honeypot, eine
# bestandene Verifizierung, eine Automod-Strafe.
#
# Diese Einstellungen lagen über acht Seiten verstreut. Wer wissen
# wollte, wohin der Bot eigentlich überall schreibt, musste sie
# einzeln durchklicken. Die Registrierung in utils/bot_logs.py sammelt
# sie ein -- ohne sie zu kopieren: jedes Modul bleibt die Quelle der
# Wahrheit für seinen eigenen Kanal.


@router.get("/{guild_id}/bot", summary="Was der Bot selbst protokolliert")
async def bot_logs_overview(
    guild_id: int, bot: "universitybot" = Depends(get_bot)
):
    from utils import bot_logs

    guild = _guild_or_404(bot, guild_id)
    quellen = await bot_logs.uebersicht(guild_id, guild)

    # Wo darf der Bot nicht schreiben? Ein eingestellter Kanal ohne
    # Schreibrecht ist der häufigste Grund für "es kommt nichts an",
    # und man sieht es der Einstellung nicht an.
    me = getattr(guild, "me", None)
    for eintrag in quellen:
        eintrag["can_send"] = True
        if not eintrag["channel_id"] or me is None:
            continue
        kanal = guild.get_channel(int(eintrag["channel_id"]))
        if kanal is None:
            continue
        try:
            rechte = kanal.permissions_for(me)
            eintrag["can_send"] = bool(
                rechte.view_channel and rechte.send_messages
            )
        except Exception:  # noqa: BLE001
            pass

    gruppen: dict[str, list] = {}
    for eintrag in quellen:
        gruppen.setdefault(eintrag["gruppe"], []).append(eintrag)

    return {
        "sources": quellen,
        "groups": [
            {"name": name, "items": eintraege}
            for name, eintraege in gruppen.items()
        ],
        "active": sum(1 for q in quellen if q["aktiv"]),
        "total": len(quellen),
        "excluded": [
            {"label": label, "reason": grund}
            for label, grund in bot_logs.AUSGENOMMEN
        ],
        "channels": [
            {"id": str(k.id), "name": k.name}
            for k in getattr(guild, "text_channels", [])
        ],
    }


@router.patch("/{guild_id}/bot/{key}", summary="Einen Bot-Log umstellen")
async def bot_log_patch(
    guild_id: int, key: str, data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """Kanal setzen oder das Protokoll dieses Moduls abschalten.

    Geschrieben wird in die Tabelle des jeweiligen Moduls, nicht in
    eine eigene: sonst gäbe es zwei Wahrheiten, und sie liefen
    auseinander, sobald jemand die alte Seite benutzt.
    """
    import aiosqlite

    from utils import bot_logs

    guild = _guild_or_404(bot, guild_id)

    quelle = next((q for q in bot_logs.QUELLEN if q["key"] == key), None)
    if quelle is None:
        raise HTTPException(status_code=404, detail="Unbekannte Protokollquelle.")

    felder: dict[str, object] = {}

    if "channel_id" in data:
        roh = data["channel_id"]
        if roh in (None, "", "0"):
            felder[quelle["spalte"]] = None
        else:
            if not str(roh).isdigit():
                raise HTTPException(status_code=400, detail="Keine gültige Kanal-ID.")
            if guild.get_channel(int(roh)) is None:
                raise HTTPException(
                    status_code=400,
                    detail="Diesen Kanal gibt es auf dem Server nicht.",
                )
            felder[quelle["spalte"]] = int(roh)

    if "enabled" in data:
        if not quelle.get("schalter"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"„{quelle['label']}“ hat keinen eigenen Schalter — "
                    "leere stattdessen den Kanal."
                ),
            )
        felder[quelle["schalter"]] = 1 if data["enabled"] else 0

    if not felder:
        raise HTTPException(status_code=400, detail="Nichts zu ändern.")

    schluessel = str(guild_id) if quelle.get("id_als_text") else guild_id

    try:
        async with aiosqlite.connect(quelle["db"]) as db:
            # Die Zeile kann fehlen, wenn das Modul auf diesem Server
            # noch nie benutzt wurde. INSERT OR IGNORE legt sie an,
            # ohne eine vorhandene zu überschreiben.
            await db.execute(
                f"INSERT OR IGNORE INTO [{quelle['tabelle']}] (guild_id) VALUES (?)",
                (schluessel,),
            )
            zuweisung = ", ".join(f"[{name}] = ?" for name in felder)
            await db.execute(
                f"UPDATE [{quelle['tabelle']}] SET {zuweisung} WHERE guild_id = ?",
                (*felder.values(), schluessel),
            )
            await db.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=(
                f"„{quelle['label']}“ wurde auf diesem Server noch nie "
                f"eingerichtet. Stelle es einmal auf seiner eigenen Seite "
                f"ein. ({exc})"
            ),
        ) from exc

    await feature_audit.log_action(
        "bot_log_updated",
        actor=str(data.get("actor", "dashboard")),
        detail=f"guild {guild_id}, {key}",
    )

    return await bot_logs_overview(guild_id, bot)
