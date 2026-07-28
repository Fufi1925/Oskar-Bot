# ╔══════════════════════════════════════════════════════════════════╗
# ║   Join to Create, voice roles, custom role commands              ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The three tabs that deal with voice channels and role commands.

They used to live in guilds.py as six loosely related handlers that each
opened their own database connection and disagreed with the cogs behind
them:

  * ``/invcrole`` wrote an ``enabled`` column the cog never read, so the
    dashboard's on/off switch did nothing at all.
  * ``/customroles`` exposed only the five fixed slots and was blind to
    the ``custom_roles`` table where the actual named commands live.
  * ``/j2c`` never told the cog to re-read its cache except when it
    happened to be resending the control panel.

Every route here reports what the bot can and cannot do -- missing
permissions, roles above the bot, deleted channels -- because the most
common "I set it but nothing happens" turns out to be a permission the
dashboard silently knew about.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import voice_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    return {
        # Snowflakes as strings: a JSON number loses the last digits.
        "id": str(role_id) if role_id else None,
        "name": role.name if role else None,
        "colour": role.color.value if role else None,
        "position": role.position if role else None,
        "missing": role is None and bool(role_id),
    }


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
    return {
        "id": str(channel_id) if channel_id else None,
        "name": channel.name if channel else None,
        "missing": channel is None and bool(channel_id),
    }


def _role_problem(guild, role) -> str | None:
    """Why the bot could not hand out this role, in plain German."""
    if role is None:
        return None
    me = guild.me
    if me is None:
        return None
    if role.managed:
        return f"@{role.name} gehört zu einer Integration und ist nicht vergebbar."
    if role.is_default():
        return "@everyone kann nicht vergeben werden."
    if role >= me.top_role:
        return (f"@{role.name} steht über der Bot-Rolle — er kann sie niemandem "
                "geben. Schieb die Bot-Rolle darüber.")
    return None


async def _reload(bot, cog_name: str, guild_id: int) -> None:
    """
    Nudge the cog after a save.

    A wrong name here fails silently and looks exactly like "the
    dashboard saves but Discord ignores it", so the tests assert on it.
    """
    cog = bot.get_cog(cog_name)
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  Voice roles
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/voicerole", summary="Voice roles")
async def get_voicerole(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.VOICEROLE_DB)
    settings = await store.voicerole_get(db, guild_id)
    guild = bot.get_guild(guild_id)

    warnings: list[str] = []
    if guild is not None:
        if guild.me is not None and not guild.me.guild_permissions.manage_roles:
            warnings.append("Dem Bot fehlt das Recht „Rollen verwalten“.")
        for role_id in settings["roles"]:
            role = guild.get_role(role_id)
            if role is None:
                warnings.append(f"Eine eingetragene Rolle ({role_id}) gibt es nicht mehr.")
                continue
            problem = _role_problem(guild, role)
            if problem:
                warnings.append(problem)
        for channel_id in settings["channels"]:
            if guild.get_channel(channel_id) is None:
                warnings.append(f"Ein gewählter Kanal ({channel_id}) gibt es nicht mehr.")

    if settings["enabled"] and not settings["roles"]:
        warnings.append("Die Funktion ist an, aber es ist keine Rolle eingetragen.")

    return {
        "guild_id": str(guild_id),
        "enabled": settings["enabled"],
        "ignore_afk": settings["ignore_afk"],
        "include_stage": settings["include_stage"],
        "roles": [str(r) for r in settings["roles"]],
        "roles_info": [_role_info(guild, r) for r in settings["roles"]],
        "channels": [str(c) for c in settings["channels"]],
        "channels_info": [_channel_info(guild, c) for c in settings["channels"]],
        "has_afk_channel": bool(guild and guild.afk_channel),
        "warnings": warnings,
    }


@router.patch("/{guild_id}/voicerole", summary="Change the voice roles")
async def patch_voicerole(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.VOICEROLE_DB)

    if "roles" in data:
        for raw in data.get("roles") or []:
            if not str(raw).isdigit():
                continue
            role = guild.get_role(int(raw))
            if role is None:
                raise HTTPException(
                    status_code=404, detail="Eine der Rollen gibt es nicht mehr."
                )
            problem = _role_problem(guild, role)
            if problem:
                raise HTTPException(status_code=400, detail=problem)

    if data.get("enabled"):
        roles = data.get("roles", None)
        if roles is None:
            current = await store.voicerole_get(db, guild_id)
            roles = current["roles"]
        if not roles:
            raise HTTPException(
                status_code=400,
                detail="Wähle zuerst mindestens eine Rolle.",
            )

    settings = await store.voicerole_save(db, guild_id, data)
    await _reload(bot, "Invcrole", guild_id)

    await feature_audit.log_action(
        "voicerole_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "settings": {
            **settings,
            "roles": [str(r) for r in settings["roles"]],
            "channels": [str(c) for c in settings["channels"]],
        },
    }


# ══════════════════════════════════════════════════════════════════════
#  Custom role commands
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/customroles", summary="Custom role commands")
async def get_customroles(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.CUSTOMROLE_DB)
    config = await store.customrole_get(db, guild_id)
    guild = bot.get_guild(guild_id)

    prefix = ">"
    try:
        from utils.Tools import getConfig

        prefix = (await getConfig(guild_id)).get("prefix", ">")
    except Exception:
        pass

    entries = []
    warnings: list[str] = []
    for entry in config["entries"]:
        role = guild.get_role(entry["role_id"]) if guild else None
        problem = _role_problem(guild, role) if guild else None
        if role is None:
            problem = "Diese Rolle gibt es nicht mehr."
        if problem:
            warnings.append(f"`{prefix}{entry['name']}`: {problem}")
        entries.append({
            "name": entry["name"],
            "command": f"{prefix}{entry['name']}",
            "role": _role_info(guild, entry["role_id"]),
            "problem": problem,
        })

    if guild is not None and guild.me is not None \
            and not guild.me.guild_permissions.manage_roles:
        warnings.append("Dem Bot fehlt das Recht „Rollen verwalten“.")

    return {
        "guild_id": str(guild_id),
        "prefix": prefix,
        "entries": entries,
        "reqrole": str(config["reqrole"]) if config["reqrole"] else None,
        "reqrole_info": _role_info(guild, config["reqrole"]),
        # Names moved over from the old fixed slots on this read.
        "migrated": config["migrated"],
        "max_commands": 56,
        "warnings": warnings,
    }


@router.patch("/{guild_id}/customroles", summary="Set the required role")
async def patch_customroles(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.CUSTOMROLE_DB)

    if "reqrole" in data:
        raw = data.get("reqrole")
        if raw and str(raw).isdigit():
            if guild.get_role(int(raw)) is None:
                raise HTTPException(
                    status_code=404, detail="Die Rolle gibt es nicht mehr."
                )
        await store.customrole_set_reqrole(db, guild_id, raw)

    await _reload(bot, "Customrole", guild_id)
    return {"status": "success", "result": "Gespeichert."}


@router.post("/{guild_id}/customroles", summary="Create a role command")
async def add_customrole(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    name = str(data.get("name") or "").strip().lower()

    problem = store.customrole_check_name(name)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    # Shadowing a built-in command would make the real one unreachable.
    if bot.get_command(name):
        raise HTTPException(
            status_code=400,
            detail=f"„{name}“ ist schon ein Befehl des Bots. Nimm einen anderen Namen.",
        )

    raw_role = data.get("role_id")
    if not str(raw_role or "").isdigit():
        raise HTTPException(status_code=400, detail="Wähle eine Rolle.")

    role = guild.get_role(int(raw_role))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")
    problem = _role_problem(guild, role)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    db = await db_manager.get_connection(store.CUSTOMROLE_DB)
    config = await store.customrole_get(db, guild_id)
    if any(e["name"] == name for e in config["entries"]):
        raise HTTPException(
            status_code=409, detail=f"„{name}“ gibt es hier schon."
        )
    if len(config["entries"]) >= 56:
        raise HTTPException(
            status_code=400, detail="Mehr als 56 Rollen-Befehle gehen nicht."
        )

    await store.customrole_add(db, guild_id, name, role.id)
    await _reload(bot, "Customrole", guild_id)

    await feature_audit.log_action(
        "customrole_added", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{name} -> @{role.name}",
    )
    return {"status": "success", "result": f"„{name}“ angelegt."}


@router.delete("/{guild_id}/customroles/{name}", summary="Delete a role command")
async def delete_customrole(
    guild_id: int, name: str, bot: "universitybot" = Depends(get_bot)
):
    db = await db_manager.get_connection(store.CUSTOMROLE_DB)
    if not await store.customrole_remove(db, guild_id, name):
        raise HTTPException(status_code=404, detail=f"„{name}“ gibt es hier nicht.")

    await _reload(bot, "Customrole", guild_id)
    return {"status": "success", "result": f"„{name}“ gelöscht."}


# ══════════════════════════════════════════════════════════════════════
#  Join to Create
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/j2c", summary="Join to Create")
async def get_j2c(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.J2C_DB)
    settings = await store.j2c_get(db, guild_id)
    guild = bot.get_guild(guild_id)

    warnings: list[str] = []
    if guild is not None:
        me = guild.me
        if me is not None and not me.guild_permissions.manage_channels:
            warnings.append(
                "Dem Bot fehlt „Kanäle verwalten“ — er kann keine Kanäle anlegen."
            )
        if me is not None and not me.guild_permissions.move_members:
            warnings.append(
                "Dem Bot fehlt „Mitglieder verschieben“ — er kann niemanden "
                "in den neuen Kanal ziehen."
            )

        join_channel = (
            guild.get_channel(int(settings["join_channel_id"]))
            if settings["join_channel_id"] else None
        )
        if settings["join_channel_id"] and join_channel is None:
            warnings.append("Den Lobby-Kanal gibt es nicht mehr.")
        elif join_channel is not None and not isinstance(
            join_channel, discord.VoiceChannel
        ):
            warnings.append("Der Lobby-Kanal muss ein Sprachkanal sein.")

        control = (
            guild.get_channel(int(settings["control_channel_id"]))
            if settings["control_channel_id"] else None
        )
        if settings["control_channel_id"] and control is None:
            warnings.append("Den Kanal für das Bedienfeld gibt es nicht mehr.")

        category = (
            guild.get_channel(int(settings["category_id"]))
            if settings["category_id"] else None
        )
        if settings["category_id"] and category is None:
            warnings.append("Die gewählte Kategorie gibt es nicht mehr.")
        elif category is not None and len(category.channels) >= 50:
            # Discord refuses a 51st channel in a category.
            warnings.append(
                f"Die Kategorie „{category.name}“ ist mit "
                f"{len(category.channels)} Kanälen fast voll (Grenze: 50)."
            )

    if not store.j2c_is_configured(settings):
        warnings.append(
            "Es fehlt noch etwas: Lobby-Kanal und Bedienfeld-Kanal werden beide gebraucht."
        )

    cog = bot.get_cog("JoinToCreate")
    active = 0
    if cog is not None:
        active = sum(
            1 for data in getattr(cog, "private_channels", {}).values()
            if data.get("guild_id") == guild_id
        )

    return {
        "guild_id": str(guild_id),
        "join_channel_id": str(settings["join_channel_id"]) if settings["join_channel_id"] else None,
        "control_channel_id": str(settings["control_channel_id"]) if settings["control_channel_id"] else None,
        "category_id": str(settings["category_id"]) if settings["category_id"] else None,
        "join_channel_info": _channel_info(guild, settings["join_channel_id"]),
        "control_channel_info": _channel_info(guild, settings["control_channel_id"]),
        "category_info": _channel_info(guild, settings["category_id"]),
        "name_template": settings["name_template"],
        "default_limit": settings["default_limit"],
        "default_locked": settings["default_locked"],
        "placeholders": store.J2C_PLACEHOLDERS,
        "configured": store.j2c_is_configured(settings),
        "active_channels": active,
        "preview": store.j2c_channel_name(
            settings["name_template"], user_name="Lena",
            display_name="Lena", count=active + 1,
        ),
        "warnings": warnings,
    }


@router.patch("/{guild_id}/j2c", summary="Change Join to Create")
async def patch_j2c(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.J2C_DB)

    if data.get("join_channel_id"):
        channel = guild.get_channel(int(data["join_channel_id"])) \
            if str(data["join_channel_id"]).isdigit() else None
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if not isinstance(channel, discord.VoiceChannel):
            raise HTTPException(
                status_code=400, detail="Die Lobby muss ein Sprachkanal sein."
            )

    if data.get("control_channel_id"):
        channel = guild.get_channel(int(data["control_channel_id"])) \
            if str(data["control_channel_id"]).isdigit() else None
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if not hasattr(channel, "send"):
            raise HTTPException(
                status_code=400,
                detail="Das Bedienfeld braucht einen Textkanal.",
            )

    if "default_limit" in data:
        try:
            limit = int(data["default_limit"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Das Limit muss eine Zahl sein.")
        if not 0 <= limit <= store.MAX_VOICE_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"Discord erlaubt 0 bis {store.MAX_VOICE_LIMIT} (0 = unbegrenzt).",
            )

    if "name_template" in data and not str(data["name_template"] or "").strip():
        raise HTTPException(status_code=400, detail="Der Name darf nicht leer sein.")

    settings = await store.j2c_save(db, guild_id, data)
    await _reload(bot, "JoinToCreate", guild_id)

    await feature_audit.log_action(
        "j2c_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "settings": {
            **settings,
            "join_channel_id": str(settings["join_channel_id"]) if settings["join_channel_id"] else None,
            "control_channel_id": str(settings["control_channel_id"]) if settings["control_channel_id"] else None,
            "category_id": str(settings["category_id"]) if settings["category_id"] else None,
        },
    }


@router.post("/{guild_id}/j2c/panel", summary="Post the control panel")
async def post_j2c_panel(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Send or refresh the control panel.

    The old PATCH did this as a side effect inside a background task, so
    a failure never reached the dashboard. Here it is its own action and
    reports what went wrong.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.J2C_DB)
    settings = await store.j2c_get(db, guild_id)

    if not settings["control_channel_id"]:
        raise HTTPException(
            status_code=400, detail="Es ist kein Kanal für das Bedienfeld gesetzt."
        )
    channel = guild.get_channel(int(settings["control_channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    cog = bot.get_cog("JoinToCreate")
    if cog is None:
        raise HTTPException(status_code=503, detail="Das J2C-Modul ist nicht geladen.")

    from cogs.commands.j2c import ControlPanelView

    view = ControlPanelView(cog, guild)
    message = None

    if settings["control_message_id"]:
        try:
            message = await channel.fetch_message(int(settings["control_message_id"]))
            await message.edit(view=view)
        except discord.NotFound:
            message = None
        except discord.Forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nichts bearbeiten.",
            )

    if message is None:
        try:
            message = await channel.send(view=view)
        except discord.Forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
            )
        except discord.HTTPException as exc:
            raise HTTPException(status_code=502, detail=f"Discord lehnte ab: {exc}")

        await store.j2c_save(db, guild_id, {"control_message_id": message.id})

    await _reload(bot, "JoinToCreate", guild_id)
    return {"status": "success", "result": f"Bedienfeld in #{channel.name} gepostet."}


@router.post("/{guild_id}/j2c/reset", summary="Switch Join to Create off")
async def reset_j2c(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    db = await db_manager.get_connection(store.J2C_DB)
    await store.j2c_clear(db, guild_id)

    cog = bot.get_cog("JoinToCreate")
    if cog is not None:
        getattr(cog, "setup_data", {}).pop(guild_id, None)
    await _reload(bot, "JoinToCreate", guild_id)

    return {
        "status": "success",
        "result": "Ausgeschaltet. Bereits erstellte Kanäle bleiben bestehen.",
    }
