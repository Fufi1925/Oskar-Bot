# ╔══════════════════════════════════════════════════════════════════╗
# ║   Verification                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The verification tab.

Replaces the pair of handlers in guilds.py, which knew five columns and
had two bugs of their own:

  * ``verification_channel_id or 0`` stored 0 for "not set". Zero is not
    null, so the read side handed ``"0"`` back to the dashboard as
    though it were a channel id.
  * The INSERT branch defaulted every column it was not given, so the
    first save from the dashboard wiped a setup made through the chat
    command.

Everything here reports what the bot can and cannot do -- missing
permissions, a role above the bot, a deleted channel -- because that is
almost always the answer to "I set it and nothing happens".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import verify_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
    return {
        # Snowflakes travel as strings: a JSON number loses the last digits.
        "id": str(channel_id) if channel_id else None,
        "name": channel.name if channel else None,
        "missing": channel is None and bool(channel_id),
    }


def _colour_of(role):
    """
    A role colour as a plain int.

    discord.py hands back a Colour object, but not every code path does
    -- reading .value unconditionally turned one odd role into a 500 for
    the whole page.
    """
    colour = getattr(role, "color", None) if role is not None else None
    if colour is None:
        return None
    return getattr(colour, "value", colour) if not isinstance(colour, int) else colour


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    return {
        "id": str(role_id) if role_id else None,
        "name": getattr(role, "name", None) if role else None,
        "colour": _colour_of(role),
        "missing": role is None and bool(role_id),
    }


def _role_problem(guild, role) -> str | None:
    if role is None:
        return None
    me = getattr(guild, "me", None)
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


def _warnings(guild, settings: dict) -> list[str]:
    """Everything standing between this config and it actually working."""
    problems = list(store.readiness(settings))
    if guild is None:
        return problems

    # getattr, not guild.me: the attribute is missing entirely while the
    # bot is still connecting, and a warnings helper must never be the
    # thing that takes the whole page down with a 500.
    me = getattr(guild, "me", None)
    if me is not None and not me.guild_permissions.manage_roles:
        problems.append("Dem Bot fehlt das Recht „Rollen verwalten“.")

    channel = (
        guild.get_channel(int(settings["verification_channel_id"]))
        if settings.get("verification_channel_id") else None
    )
    if settings.get("verification_channel_id") and channel is None:
        problems.append("Den Verifizierungs-Kanal gibt es nicht mehr.")
    elif channel is not None and me is not None and hasattr(channel, "permissions_for"):
        perms = channel.permissions_for(me)
        if not perms.send_messages:
            problems.append(f"Der Bot darf in #{channel.name} nicht schreiben.")
        if settings.get("delete_messages") and not perms.manage_messages:
            problems.append(
                "Ohne „Nachrichten verwalten“ bleiben fremde Nachrichten "
                f"in #{channel.name} stehen."
            )

    for key, label in (
        ("verified_role_id", "Verifiziert-Rolle"),
        ("unverified_role_id", "Unverifiziert-Rolle"),
    ):
        if not settings.get(key):
            continue
        role = guild.get_role(int(settings[key]))
        if role is None:
            problems.append(f"Die {label} gibt es nicht mehr.")
            continue
        problem = _role_problem(guild, role)
        if problem:
            problems.append(problem)

    log_id = settings.get("log_channel_id")
    if log_id and guild.get_channel(int(log_id)) is None:
        problems.append("Den Log-Kanal gibt es nicht mehr.")

    return problems


async def _reload(bot, guild_id: int) -> None:
    """
    Nudge the cog after a save.

    A wrong cog name here fails silently and looks exactly like "the
    dashboard saves but Discord ignores it", so the tests assert on it.
    """
    cog = bot.get_cog("Verification")
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


@router.get("/{guild_id}", summary="Verification settings")
async def get_verification(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)
    guild = bot.get_guild(guild_id)

    panel_alive = None
    if settings.get("panel_message_id") and settings.get("panel_channel_id"):
        channel = (
            guild.get_channel(int(settings["panel_channel_id"])) if guild else None
        )
        panel_alive = channel is not None

    preview_role = "@Verifiziert"
    if guild and settings.get("verified_role_id"):
        role = guild.get_role(int(settings["verified_role_id"]))
        if role:
            preview_role = f"@{role.name}"

    def preview(key):
        return store.render(
            settings[key],
            server=guild.name if guild else "Dein Server",
            user_mention="@Lena", user_name="Lena", role=preview_role,
            member_count=guild.member_count if guild else 0,
        )

    return {
        "guild_id": str(guild_id),
        **{k: v for k, v in settings.items() if k not in store.ID_KEYS},
        **{k: (str(settings[k]) if settings[k] else None) for k in store.ID_KEYS},
        "channel_info": _channel_info(guild, settings["verification_channel_id"]),
        "role_info": _role_info(guild, settings["verified_role_id"]),
        "log_channel_info": _channel_info(guild, settings["log_channel_id"]),
        "unverified_role_info": _role_info(guild, settings["unverified_role_id"]),
        "methods": store.methods_for(settings),
        "configured": store.is_configured(settings),
        "panel_posted": panel_alive,
        "placeholders": store.PLACEHOLDERS,
        "preview": {
            "title": preview("panel_title"),
            "text": preview("panel_text"),
            "footer": preview("panel_footer"),
            "success": preview("success_text"),
            "dm_success": preview("dm_success_text"),
        },
        "verified_count": await store.count_verified(db, guild_id),
        "recent": await store.recent_logs(db, guild_id, 10),
        "warnings": _warnings(guild, settings),
    }


@router.patch("/{guild_id}", summary="Change the verification settings")
async def patch_verification(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    current = await store.get_settings(db, guild_id)

    if data.get("verification_channel_id"):
        raw = str(data["verification_channel_id"])
        channel = guild.get_channel(int(raw)) if raw.isdigit() else None
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if not hasattr(channel, "send"):
            raise HTTPException(
                status_code=400, detail="Die Verifizierung braucht einen Textkanal."
            )

    for key, label in (
        ("verified_role_id", "Verifiziert-Rolle"),
        ("unverified_role_id", "Unverifiziert-Rolle"),
    ):
        if not data.get(key):
            continue
        raw = str(data[key])
        role = guild.get_role(int(raw)) if raw.isdigit() else None
        if role is None:
            raise HTTPException(
                status_code=404, detail=f"Die {label} gibt es nicht mehr."
            )
        problem = _role_problem(guild, role)
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    if "verification_method" in data \
            and data["verification_method"] not in store.METHODS:
        raise HTTPException(
            status_code=400,
            detail="Unbekannte Methode — erlaubt sind button, captcha oder both.",
        )

    # Switching it on without the two things it needs would look broken.
    if data.get("enabled"):
        channel_id = data.get("verification_channel_id") \
            or current["verification_channel_id"]
        role_id = data.get("verified_role_id") or current["verified_role_id"]
        if not channel_id or not role_id:
            raise HTTPException(
                status_code=400,
                detail="Wähle zuerst einen Kanal und eine Rolle.",
            )

    for key in store.TEXT_KEYS:
        if key in data and not str(data[key] or "").strip():
            raise HTTPException(
                status_code=400, detail=f"„{key}“ darf nicht leer sein."
            )

    for key in store.INT_KEYS:
        if key not in data:
            continue
        try:
            value = int(data[key])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"„{key}“ muss eine Zahl sein.")
        if value < 0:
            raise HTTPException(status_code=400, detail=f"„{key}“ kann nicht negativ sein.")

    settings = await store.save_settings(db, guild_id, data)
    await _reload(bot, guild_id)

    await feature_audit.log_action(
        "verification_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "warnings": _warnings(guild, settings),
    }


@router.post("/{guild_id}/panel", summary="Post or refresh the panel")
async def post_panel(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not store.is_configured(settings):
        raise HTTPException(
            status_code=400,
            detail="Es fehlt noch ein Kanal oder eine Rolle.",
        )

    channel = guild.get_channel(int(settings["verification_channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        raise HTTPException(
            status_code=503, detail="Das Verifizierungs-Modul ist nicht geladen."
        )

    role = guild.get_role(int(settings["verified_role_id"]))
    view = cog.build_panel(guild, settings, role)

    message = None
    if settings.get("panel_message_id") and settings.get("panel_channel_id"):
        old = guild.get_channel(int(settings["panel_channel_id"]))
        if old is not None:
            try:
                message = await old.fetch_message(int(settings["panel_message_id"]))
                await message.edit(view=view)
            except discord.NotFound:
                message = None
            except discord.Forbidden:
                message = None

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

        await store.save_settings(db, guild_id, {
            "panel_message_id": message.id, "panel_channel_id": channel.id,
        })

    await _reload(bot, guild_id)
    return {"status": "success", "result": f"Panel in #{channel.name} gepostet."}


@router.post("/{guild_id}/preview", summary="Preview the panel privately")
async def preview_panel(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Send the panel as it would look, without replacing the live one.

    Uses the cog's own renderer so what is previewed is what gets
    posted -- a second implementation is how a preview starts lying.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    # Preview whatever is in the form, not only what is saved.
    settings = store.normalise({**settings, **{
        k: v for k, v in (data or {}).items() if k in store.DEFAULTS
    }})

    raw = str(data.get("channel_id") or settings.get("verification_channel_id") or "")
    channel = guild.get_channel(int(raw)) if raw.isdigit() else None
    if channel is None:
        raise HTTPException(status_code=400, detail="Wähle einen Kanal für die Vorschau.")

    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        raise HTTPException(
            status_code=503, detail="Das Verifizierungs-Modul ist nicht geladen."
        )

    role = (
        guild.get_role(int(settings["verified_role_id"]))
        if settings.get("verified_role_id") else None
    )
    try:
        await channel.send(view=cog.build_panel(guild, settings, role, preview=True))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=502, detail=f"Discord lehnte ab: {exc}")

    return {
        "status": "success",
        "result": f"Vorschau in #{channel.name} — die Knöpfe sind dort ohne Funktion.",
    }


@router.post("/{guild_id}/reset", summary="Switch verification off")
async def reset_verification(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    keep_texts = True
    if isinstance(data, dict):
        keep_texts = bool(data.get("keep_texts", True))

    db = await db_manager.get_connection(store.DB_PATH)
    updates = {"enabled": False, "panel_message_id": None, "panel_channel_id": None}
    if not keep_texts:
        updates.update({key: store.DEFAULTS[key] for key in store.TEXT_KEYS})

    await store.save_settings(db, guild_id, updates)
    await _reload(bot, guild_id)

    return {
        "status": "success",
        "result": (
            "Ausgeschaltet. Deine Texte bleiben gespeichert."
            if keep_texts else "Ausgeschaltet und Texte zurückgesetzt."
        ),
    }


@router.post("/{guild_id}/verify/{user_id}", summary="Verify somebody by hand")
async def verify_member(
    guild_id: int, user_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not settings.get("verified_role_id"):
        raise HTTPException(status_code=400, detail="Es ist keine Rolle gesetzt.")

    member = guild.get_member(user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Die Person ist nicht auf dem Server.")

    role = guild.get_role(int(settings["verified_role_id"]))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")
    problem = _role_problem(guild, role)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if role in member.roles:
        return {"status": "success", "result": f"{member.display_name} war schon verifiziert."}

    try:
        await member.add_roles(role, reason="Verifizierung über das Dashboard")
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf @{role.name} nicht vergeben."
        )

    await store.log_verification(
        db, guild_id, user_id, "manual",
        datetime.now(timezone.utc).isoformat(),
    )
    return {"status": "success", "result": f"{member.display_name} ist jetzt verifiziert."}
