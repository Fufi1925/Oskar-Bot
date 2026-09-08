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
from api.dependencies import get_bot, run_on_bot_loop
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


def _member_card(guild, user_id) -> dict:
    """
    Enough about a member for the list to show a face and a name.

    The list used to print the raw snowflake and nothing else, which is
    unreadable -- and the id stays a string here for the same reason it
    does everywhere else: a JSON number drops the last digits.
    """
    member = guild.get_member(int(user_id)) if guild and user_id else None
    if member is None:
        return {
            "id": str(user_id),
            "name": None,
            "display_name": None,
            "avatar": None,
            "left": True,
        }
    return {
        "id": str(user_id),
        "name": getattr(member, "name", None),
        "display_name": getattr(member, "display_name", None),
        # display_avatar, not avatar: the plain one is None for anybody
        # still on a default avatar.
        "avatar": getattr(getattr(member, "display_avatar", None), "url", None),
        "bot": bool(getattr(member, "bot", False)),
        "left": False,
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


@router.post("/oauth/complete", summary="Complete public OAuth verification")
async def complete_oauth_verification(
    data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Complete a verification using identity data fetched by our OAuth server.

    This endpoint is protected by the bot API key. It never accepts a role or
    success flag from the browser and never receives an OAuth access token.
    """
    raw_guild_id = str(data.get("guild_id") or "")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    raw_user_id = str(user.get("id") or "")
    oauth_guilds = data.get("guilds") if isinstance(data.get("guilds"), list) else []
    if not raw_guild_id.isdigit() or not raw_user_id.isdigit():
        raise HTTPException(status_code=400, detail="OAuth-Daten unvollständig.")
    guild_id = int(raw_guild_id)
    user_id = int(raw_user_id)
    if not guild_id or not user_id:
        raise HTTPException(status_code=400, detail="OAuth-Daten unvollständig.")

    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)
    base = {
        "guild_id": str(guild.id),
        "guild_name": guild.name,
        "guild_icon": str(guild.icon.url) if guild.icon else None,
    }
    if not settings.get("enabled") or not store.is_configured(settings):
        return {**base, "status": "error", "reason": "not_configured"}

    try:
        member = guild.get_member(user_id)
        if member is None:
            member = await run_on_bot_loop(guild.fetch_member(user_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return {**base, "status": "denied", "reason": "not_a_member", "blocked": []}

    oauth_memberships = {
        str(item.get("id")): str(item.get("name") or item.get("id"))[:100]
        for item in oauth_guilds if isinstance(item, dict) and str(item.get("id") or "").isdigit()
    }
    blocked_ids = set(settings.get("blacklisted_guild_ids") or [])
    matched_ids = sorted(blocked_ids.intersection(oauth_memberships))[:20] \
        if settings.get("server_blacklist_enabled") else []
    matched = [
        {"id": item, "name": oauth_memberships[item]} for item in matched_ids
    ]

    denial_reason = None
    if matched:
        denial_reason = "server_blacklist"
    else:
        created = getattr(member, "created_at", None)
        age_days = ((datetime.now(timezone.utc) - created).total_seconds() / 86400) \
            if created else 999999
        if store.account_too_young(settings, age_days):
            denial_reason = "account_too_young"

    if denial_reason:
        blocked_names = ", ".join(item["name"] for item in matched) or "—"
        if settings.get("blacklist_custom_message"):
            title = settings.get("blacklist_title") or "Verifizierung abgelehnt"
            description = settings.get("blacklist_text") or "Die Prüfung wurde abgelehnt."
        else:
            title = "Verifizierung abgelehnt"
            description = (
                "Du bist Mitglied eines Servers, den das Team von **{server}** "
                "gesperrt hat. Betroffener Server: **{blocked_server}**."
                if matched else
                "Dein Discord-Konto erfüllt das konfigurierte Mindestalter nicht."
            )
        description = store.render(
            description, server=guild.name, user_mention=member.mention,
            user_name=member.display_name, member_count=guild.member_count or 0,
            blocked_server=blocked_names,
        )
        embed = discord.Embed(title=title[:256], description=description[:4000], color=0xEF4444)
        embed.set_footer(text="University Bot • Sichere Verifizierung")
        try:
            await run_on_bot_loop(member.send(embed=embed))
        except (discord.Forbidden, discord.HTTPException):
            pass

        log_id = settings.get("blacklist_log_channel_id") or settings.get("log_channel_id")
        log_channel = guild.get_channel(int(log_id)) if log_id else None
        if log_channel and hasattr(log_channel, "send"):
            log_embed = discord.Embed(
                title="OAuth-Verifizierung abgelehnt",
                description=(
                    f"{member.mention} (`{member.id}`) wurde abgelehnt.\n"
                    f"Grund: **{denial_reason}**\n"
                    f"Treffer: **{blocked_names}**"
                ),
                color=0xEF4444,
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await run_on_bot_loop(log_channel.send(embed=log_embed))
            except (discord.Forbidden, discord.HTTPException):
                pass
        return {**base, "status": "denied", "reason": denial_reason, "blocked": matched}

    role = guild.get_role(int(settings["verified_role_id"]))
    problem = _role_problem(guild, role)
    if role is None or problem:
        return {**base, "status": "error", "reason": "role_unavailable"}
    try:
        if role not in member.roles:
            await run_on_bot_loop(
                member.add_roles(role, reason="One-Click-Verifizierung (Discord OAuth2)")
            )
    except (discord.Forbidden, discord.HTTPException):
        return {**base, "status": "error", "reason": "role_unavailable"}

    unverified_id = settings.get("unverified_role_id")
    if settings.get("remove_unverified_role") and unverified_id:
        unverified = guild.get_role(int(unverified_id))
        if unverified in member.roles:
            try:
                await run_on_bot_loop(
                    member.remove_roles(unverified, reason="OAuth2-verifiziert")
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    await store.log_verification(
        db, guild.id, member.id, "oauth",
        datetime.now(timezone.utc).isoformat(),
    )
    log_id = settings.get("log_channel_id")
    log_channel = guild.get_channel(int(log_id)) if log_id else None
    if log_channel and hasattr(log_channel, "send"):
        try:
            await run_on_bot_loop(log_channel.send(embed=discord.Embed(
                title="OAuth-Verifizierung erfolgreich",
                description=f"{member.mention} (`{member.id}`) hat die Rolle **{role.name}** erhalten.",
                color=0x22C55E,
                timestamp=datetime.now(timezone.utc),
            )))
        except (discord.Forbidden, discord.HTTPException):
            pass

    if settings.get("dm_on_success"):
        text = store.render(
            settings.get("dm_success_text", ""), server=guild.name,
            user_mention=member.mention, user_name=member.display_name,
            role=f"@{role.name}", member_count=guild.member_count or 0,
        )
        try:
            await run_on_bot_loop(member.send(embed=discord.Embed(
                title="Verifizierung erfolgreich", description=text[:4000], color=0x22C55E
            )))
        except (discord.Forbidden, discord.HTTPException):
            pass
    return {**base, "status": "success", "role_name": role.name}


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
        "blacklist_log_channel_info": _channel_info(guild, settings["blacklist_log_channel_id"]),
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
        "recent": [
            {**entry, "member": _member_card(guild, entry["user_id"])}
            for entry in await store.recent_logs(db, guild_id, 10)
        ],
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
            detail="Die Verifizierung unterstützt ausschließlich Discord OAuth2.",
        )

    if "blacklisted_guild_ids" in data:
        blocked = data["blacklisted_guild_ids"]
        if not isinstance(blocked, list) or len(blocked) > 250:
            raise HTTPException(status_code=400, detail="Die Server-Blacklist ist ungültig.")
        if any(not str(item).isdigit() for item in blocked):
            raise HTTPException(status_code=400, detail="Server-IDs dürfen nur Ziffern enthalten.")

    if data.get("blacklist_log_channel_id"):
        raw = str(data["blacklist_log_channel_id"])
        channel = guild.get_channel(int(raw)) if raw.isdigit() else None
        if channel is None or not hasattr(channel, "send"):
            raise HTTPException(status_code=404, detail="Den Blacklist-Logkanal gibt es nicht mehr.")

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


@router.delete("/{guild_id}/verify/{user_id}", summary="Take the role back")
async def unverify_member(
    guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)
):
    """Undo a verification -- the obvious companion to doing it by hand."""
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not settings.get("verified_role_id"):
        raise HTTPException(status_code=400, detail="Es ist keine Rolle gesetzt.")

    member = guild.get_member(user_id)
    if member is None:
        raise HTTPException(
            status_code=404, detail="Die Person ist nicht mehr auf dem Server."
        )

    role = guild.get_role(int(settings["verified_role_id"]))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")
    if role not in member.roles:
        return {
            "status": "success",
            "result": f"{member.display_name} hatte die Rolle gar nicht.",
        }

    try:
        await member.remove_roles(role, reason="Verifizierung über das Dashboard entzogen")
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf @{role.name} nicht entfernen."
        )

    return {
        "status": "success",
        "result": f"{member.display_name} ist nicht mehr verifiziert.",
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
