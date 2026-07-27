# ╔══════════════════════════════════════════════════════════════════╗
# ║   Seven features that had no dashboard                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Booster, sticky messages, nightmode, jail, counting, notify, birthdays.

All seven already worked over chat commands; none had a dashboard, so
most servers never found them. Two carried real bugs that only show up
once a second server uses them — see utils/extras_store.py.

Every write tells the owning cog to reload, because several of them keep
their state in memory and would otherwise ignore the dashboard until the
next restart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import extras_store as store
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


async def _reload(bot, cog_name: str, guild_id: int) -> None:
    """Several of these cogs cache their state; nudge them."""
    cog = bot.get_cog(cog_name)
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


def _role_problem(guild, role) -> str | None:
    if role is None:
        return "Die Rolle gibt es nicht mehr."
    me = guild.me
    if me is None:
        return None
    if not me.guild_permissions.manage_roles:
        return "Dem Bot fehlt „Rollen verwalten“."
    if role.managed:
        return f"@{role.name} gehört einer Integration und kann nicht vergeben werden."
    if role >= me.top_role:
        return (
            f"@{role.name} steht über der Bot-Rolle — er könnte sie niemandem "
            "geben. Schieb die Bot-Rolle darüber."
        )
    return None


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
    return {
        "id": str(channel_id) if channel_id else None,
        "name": channel.name if channel else None,
        "missing": channel is None and bool(channel_id),
    }


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    return {
        "id": str(role_id) if role_id else None,
        "name": role.name if role else None,
        "colour": role.color.value if role else None,
        "missing": role is None and bool(role_id),
    }


# ══════════════════════════════════════════════════════════════════════
#  Booster
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/booster", summary="Boost rewards and announcement")
async def get_booster(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.BOOST_DB)
    await store.boost_ensure(db)
    guild = bot.get_guild(guild_id)
    config = await store.boost_get(db, guild_id)

    return {
        "guild_id": str(guild_id),
        "boost": {
            **config["boost"],
            "channel": [str(c) for c in config["boost"]["channel"]],
            "channels_info": [
                _channel_info(guild, c) for c in config["boost"]["channel"]
            ],
        },
        "roles": [str(r) for r in config["boost_roles"]["roles"]],
        "roles_info": [_role_info(guild, r) for r in config["boost_roles"]["roles"]],
        "placeholders": store.BOOST_PLACEHOLDERS,
        # Shows whether the feature has anything to react to at all.
        "boost_count": guild.premium_subscription_count if guild else 0,
        "boost_level": guild.premium_tier if guild else 0,
        "boosters": (
            [
                {
                    "user_id": str(m.id),
                    "name": m.display_name,
                    "avatar": m.display_avatar.url,
                }
                for m in guild.premium_subscribers
            ]
            if guild else []
        ),
    }


@router.patch("/{guild_id}/booster", summary="Change the boost settings")
async def patch_booster(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.BOOST_DB)
    await store.boost_ensure(db)

    updates: dict = {}
    boost: dict = {}
    for key in ("message", "embed", "ping", "image", "thumbnail", "autodel"):
        if key in data:
            boost[key] = data[key]
    if "channels" in data:
        boost["channel"] = data["channels"]
    if boost:
        updates["boost"] = boost

    if "roles" in data:
        # Refuse a role the bot could never hand out, rather than failing
        # silently every time somebody boosts.
        for role_id in data["roles"]:
            if not str(role_id).isdigit():
                continue
            problem = _role_problem(guild, guild.get_role(int(role_id)))
            if problem:
                raise HTTPException(status_code=400, detail=problem)
        updates["boost_roles"] = {"roles": data["roles"]}

    if not updates:
        return {"status": "success", "result": "Nichts zu ändern."}

    config = await store.boost_save(db, guild_id, updates)
    await _reload(bot, "Booster", guild_id)

    await feature_audit.log_action(
        "booster_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=", ".join(sorted(updates)),
    )
    return {"status": "success", "result": "Gespeichert.", "config": config}


@router.post("/{guild_id}/booster/test", summary="Preview the boost message")
async def test_booster(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.BOOST_DB)
    await store.boost_ensure(db)
    config = await store.boost_get(db, guild_id)

    channel_id = str(data.get("channel_id") or "")
    if not channel_id.isdigit():
        channels = config["boost"]["channel"]
        if not channels:
            raise HTTPException(
                status_code=400, detail="Es ist kein Ankündigungs-Kanal gesetzt."
            )
        channel_id = str(channels[0])

    channel = guild.get_channel(int(channel_id))
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    actor = str(data.get("actor", ""))
    member = guild.get_member(int(actor)) if actor.isdigit() else None
    member = member or guild.me

    message = str(data.get("message") or config["boost"]["message"])
    for token, value in (
        ("{user.mention}", member.mention),
        ("{user.name}", member.display_name),
        ("{user.tag}", str(member)),
        ("{server.name}", guild.name),
        ("{server.boost_count}", str(guild.premium_subscription_count)),
        ("{server.boost_level}", f"Level {guild.premium_tier}"),
        ("{server.member_count}", str(guild.member_count or 0)),
    ):
        message = message.replace(token, value)

    from utils.panels import ACCENT, Panel

    try:
        posted = await channel.send(view=Panel(
            "Server geboostet!", message,
            accent=ACCENT["brand"],
            image_url=config["boost"].get("image") or None,
        ))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )

    return {
        "status": "success",
        "result": f"Vorschau in #{channel.name} gesendet.",
        "url": posted.jump_url,
    }


# ══════════════════════════════════════════════════════════════════════
#  Sticky messages
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/sticky", summary="Sticky messages")
async def get_sticky(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.STICKY_DB)
    await store.sticky_ensure(db)
    guild = bot.get_guild(guild_id)

    entries = []
    for row in await store.sticky_list(db, guild_id):
        channel = guild.get_channel(row["channel_id"]) if guild else None
        entries.append({
            "channel_id": str(row["channel_id"]),
            "channel_name": channel.name if channel else None,
            "missing": channel is None,
            "message": row["message"],
            "can_post": (
                bool(channel and guild.me
                     and channel.permissions_for(guild.me).send_messages)
                if channel else False
            ),
        })

    return {"guild_id": str(guild_id), "entries": entries}


@router.post("/{guild_id}/sticky", summary="Pin a message to the bottom")
async def set_sticky(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    channel_id = str(data.get("channel_id") or "")
    message = str(data.get("message") or "").strip()
    if not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal auswählen.")
    if not message:
        raise HTTPException(status_code=400, detail="Die Nachricht darf nicht leer sein.")

    channel = guild.get_channel(int(channel_id))
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    me = guild.me
    if me is not None:
        permissions = channel.permissions_for(me)
        if not permissions.send_messages:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
            )
        # Without this the old copy stays and the channel fills up with
        # duplicates of the sticky message.
        if not permissions.manage_messages:
            raise HTTPException(
                status_code=403,
                detail=f"In #{channel.name} fehlt „Nachrichten verwalten“ — die "
                       "alte Kopie bliebe stehen und der Kanal würde zulaufen.",
            )

    db = await db_manager.get_connection(store.STICKY_DB)
    await store.sticky_ensure(db)
    await store.sticky_set(db, guild_id, int(channel_id), message)
    await _reload(bot, "StickyMessage", guild_id)

    await feature_audit.log_action(
        "sticky_set", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"#{channel.name}",
    )
    return {"status": "success", "result": f"Bleibt jetzt unten in #{channel.name}."}


@router.delete("/{guild_id}/sticky/{channel_id}", summary="Remove a sticky")
async def delete_sticky(
    guild_id: int, channel_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await db_manager.get_connection(store.STICKY_DB)
    await store.sticky_ensure(db)

    last_id = await store.sticky_remove(db, guild_id, channel_id)
    if last_id is None:
        raise HTTPException(status_code=404, detail="Dort war keine Sticky-Nachricht.")

    # Clean up the copy still sitting in the channel.
    guild = bot.get_guild(guild_id)
    if guild and last_id:
        channel = guild.get_channel(channel_id)
        if channel is not None:
            try:
                message = await channel.fetch_message(last_id)
                await message.delete()
            except Exception:
                pass

    await _reload(bot, "StickyMessage", guild_id)
    return {"status": "success", "result": "Entfernt."}


# ══════════════════════════════════════════════════════════════════════
#  Nightmode
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/nightmode", summary="Nightmode schedule")
async def get_nightmode(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.NIGHTMODE_DB)
    await store.nightmode_ensure(db)
    guild = bot.get_guild(guild_id)
    settings = await store.nightmode_get(db, guild_id)

    return {
        "guild_id": str(guild_id),
        **settings,
        "enabled": bool(settings["enabled"]),
        "active": bool(settings["active"]),
        "channels": [str(c) for c in settings["channels"]],
        "channels_info": [_channel_info(guild, c) for c in settings["channels"]],
        "can_manage": bool(
            guild and guild.me and guild.me.guild_permissions.manage_channels
        ),
    }


@router.patch("/{guild_id}/nightmode", summary="Change the nightmode schedule")
async def patch_nightmode(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    if data.get("enabled"):
        me = guild.me
        if me is not None and not me.guild_permissions.manage_channels:
            raise HTTPException(
                status_code=400,
                detail="Dem Bot fehlt „Kanäle verwalten“ — er könnte nichts "
                       "schließen oder öffnen.",
            )
        channels = data.get("channels", [])
        if not channels:
            db = await db_manager.get_connection(store.NIGHTMODE_DB)
            await store.nightmode_ensure(db)
            channels = (await store.nightmode_get(db, guild_id))["channels"]
        if not channels:
            raise HTTPException(
                status_code=400,
                detail="Wähle zuerst die Kanäle aus, die nachts zugehen sollen.",
            )

    db = await db_manager.get_connection(store.NIGHTMODE_DB)
    await store.nightmode_ensure(db)
    settings = await store.nightmode_save(db, guild_id, data)
    await _reload(bot, "Nightmode", guild_id)

    await feature_audit.log_action(
        "nightmode_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{settings['start_hour']}–{settings['end_hour']} Uhr",
    )
    return {"status": "success", "result": "Gespeichert.", "settings": settings}


@router.post("/{guild_id}/nightmode/toggle", summary="Open or close right now")
async def toggle_nightmode(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Close or open the channels immediately, ignoring the schedule."""
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.NIGHTMODE_DB)
    await store.nightmode_ensure(db)
    settings = await store.nightmode_get(db, guild_id)

    close = bool(data.get("close"))
    changed = 0
    failed = []

    for channel_id in settings["channels"]:
        channel = guild.get_channel(channel_id)
        if channel is None:
            continue
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = False if close else None
            await channel.set_permissions(
                guild.default_role, overwrite=overwrite,
                reason="Nachtmodus" if close else "Nachtmodus beendet",
            )
            changed += 1
        except Exception:
            failed.append(channel.name)

    await store.nightmode_save(db, guild_id, {"active": 1 if close else 0})

    note = f" ({len(failed)} fehlgeschlagen)" if failed else ""
    return {
        "status": "success",
        "result": (
            f"{changed} Kanäle geschlossen{note}." if close
            else f"{changed} Kanäle wieder geöffnet{note}."
        ),
        "failed": failed,
    }


# ══════════════════════════════════════════════════════════════════════
#  Jail
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/jail", summary="Jail settings and who is in there")
async def get_jail(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.JAIL_DB)
    await store.jail_ensure(db)
    guild = bot.get_guild(guild_id)
    settings = await store.jail_settings(db, guild_id)

    inmates = []
    for entry in await store.jail_inmates(db, guild_id):
        member = guild.get_member(entry["user_id"]) if guild else None
        moderator = guild.get_member(entry["mod_id"]) if guild else None
        inmates.append({
            **entry,
            "user_id": str(entry["user_id"]),
            "mod_id": str(entry["mod_id"]),
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
            "mod_name": moderator.display_name if moderator else None,
        })

    return {
        "guild_id": str(guild_id),
        "jail_role": _role_info(guild, settings["jail_role"]),
        "jail_channel": _channel_info(guild, settings["jail_channel"]),
        "mod_role": _role_info(guild, settings["mod_role"]),
        "log_channel": _channel_info(guild, settings["log_channel"]),
        "inmates": inmates,
        "configured": bool(settings["jail_role"]),
        "problem": (
            _role_problem(guild, guild.get_role(settings["jail_role"]))
            if guild and settings["jail_role"] else None
        ),
    }


@router.patch("/{guild_id}/jail", summary="Change the jail settings")
async def patch_jail(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    if str(data.get("jail_role") or "").isdigit():
        problem = _role_problem(guild, guild.get_role(int(data["jail_role"])))
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    db = await db_manager.get_connection(store.JAIL_DB)
    await store.jail_ensure(db)
    settings = await store.jail_save(db, guild_id, data)
    await _reload(bot, "Jail", guild_id)

    return {"status": "success", "result": "Gespeichert.", "settings": settings}


@router.post("/{guild_id}/jail/setup", summary="Create the jail role and channel")
async def setup_jail(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Create a jail role and a channel only that role can see.

    Doing this by hand means creating the role, then editing the
    permission overwrite on every single channel. On a server with fifty
    channels nobody does that correctly.
    """
    guild = _guild_or_404(bot, guild_id)
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        raise HTTPException(status_code=400, detail="Dem Bot fehlt „Rollen verwalten“.")
    if not me.guild_permissions.manage_channels:
        raise HTTPException(status_code=400, detail="Dem Bot fehlt „Kanäle verwalten“.")

    db = await db_manager.get_connection(store.JAIL_DB)
    await store.jail_ensure(db)
    settings = await store.jail_settings(db, guild_id)

    role = guild.get_role(settings["jail_role"]) if settings["jail_role"] else None
    created_role = False
    if role is None:
        try:
            role = await guild.create_role(
                name="Jailed",
                colour=discord.Colour(0x555555),
                reason="Jail eingerichtet",
            )
            created_role = True
        except discord.Forbidden:
            raise HTTPException(status_code=403, detail="Der Bot darf keine Rollen anlegen.")

    # Take the role's access away everywhere.
    blocked = 0
    skipped = 0
    for channel in guild.channels:
        try:
            overwrite = channel.overwrites_for(role)
            overwrite.view_channel = False
            overwrite.send_messages = False
            await channel.set_permissions(role, overwrite=overwrite, reason="Jail")
            blocked += 1
        except Exception:
            skipped += 1

    channel = (
        guild.get_channel(settings["jail_channel"])
        if settings["jail_channel"] else None
    )
    created_channel = False
    if channel is None:
        try:
            channel = await guild.create_text_channel(
                "jail",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    role: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True
                    ),
                    me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True
                    ),
                },
                reason="Jail eingerichtet",
            )
            created_channel = True
        except Exception:
            channel = None

    await store.jail_save(db, guild_id, {
        "jail_role": role.id,
        "jail_channel": channel.id if channel else settings["jail_channel"],
    })
    await _reload(bot, "Jail", guild_id)

    parts = []
    if created_role:
        parts.append("Rolle angelegt")
    if created_channel:
        parts.append("Kanal angelegt")
    parts.append(f"{blocked} Kanäle gesperrt")
    if skipped:
        parts.append(f"{skipped} übersprungen")

    return {"status": "success", "result": ", ".join(parts) + "."}


# ══════════════════════════════════════════════════════════════════════
#  Counting
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/counting", summary="Counting game")
async def get_counting(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    settings = store.counting_get(guild_id)
    last = (
        guild.get_member(int(settings["last_user"]))
        if guild and settings.get("last_user") else None
    )

    # Permission warnings: without these the game half-works and it is
    # not obvious why. Reported per channel because that is where the
    # overwrites bite.
    warnings: list[str] = []
    channel = (
        guild.get_channel(int(settings["channel"]))
        if guild and settings.get("channel") else None
    )
    if guild and settings.get("channel") and channel is None:
        warnings.append("Den eingestellten Kanal gibt es nicht mehr.")
    elif channel is not None and guild.me is not None:
        perms = channel.permissions_for(guild.me)
        if not perms.view_channel:
            warnings.append(f"Der Bot sieht #{channel.name} nicht.")
        if not perms.send_messages:
            warnings.append(f"Der Bot darf in #{channel.name} nicht schreiben.")
        if not perms.manage_messages:
            warnings.append(
                "Ohne „Nachrichten verwalten“ bleiben falsche Zahlen stehen."
            )
        if not perms.add_reactions:
            warnings.append(
                "Ohne „Reaktionen hinzufügen“ gibt es keinen Haken bei richtigen Zahlen."
            )
    if settings.get("enabled") and not settings.get("channel"):
        warnings.append("Zählen ist an, aber es ist kein Kanal gesetzt.")

    return {
        "guild_id": str(guild_id),
        **settings,
        # Snowflakes as strings: JSON numbers lose the last digits.
        "channel": str(settings["channel"]) if settings["channel"] else None,
        "channel_info": _channel_info(guild, settings["channel"]),
        "last_user": str(settings["last_user"]) if settings["last_user"] else None,
        "last_user_name": last.display_name if last else None,
        "last_user_avatar": last.display_avatar.url if last else None,
        "next_number": int(settings["current"]) + 1,
        "warnings": warnings,
    }


@router.patch("/{guild_id}/counting", summary="Change the counting game")
async def patch_counting(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    current = store.counting_get(guild_id)

    if data.get("enabled"):
        channel_id = data.get("channel") or current["channel"]
        if not channel_id:
            raise HTTPException(
                status_code=400, detail="Wähle zuerst einen Kanal fürs Zählen."
            )
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if guild.me is not None:
            perms = channel.permissions_for(guild.me)
            if not perms.send_messages:
                raise HTTPException(
                    status_code=400,
                    detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
                )

    if "current" in data:
        try:
            value = int(data["current"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Der Stand muss eine Zahl sein.")
        if value < 0:
            raise HTTPException(status_code=400, detail="Der Stand kann nicht negativ sein.")
        # Setting the counter by hand clears the last counter too,
        # otherwise "alternate" can lock out the person who last typed.
        data = {**data, "current": value, "last_user": None}

    settings = store.counting_save(guild_id, data)
    # The cog reads the file per message, but the reload hook stays so a
    # cog that does cache is still told.
    await _reload(bot, "Counting", guild_id)

    await feature_audit.log_action(
        "counting_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {"status": "success", "result": "Gespeichert.", "settings": settings}


@router.post("/{guild_id}/counting/reset", summary="Back to zero")
async def reset_counting(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    keep_record = True
    if isinstance(data, dict):
        keep_record = bool(data.get("keep_record", True))

    updates: dict = {"current": 0, "last_user": None}
    if not keep_record:
        updates["high_score"] = 0

    settings = store.counting_save(guild_id, updates)
    await _reload(bot, "Counting", guild_id)
    return {
        "status": "success",
        "result": (
            "Zurückgesetzt. Der Rekord bleibt stehen."
            if keep_record else "Zurückgesetzt, Rekord gelöscht."
        ),
        "high_score": settings["high_score"],
    }


@router.post("/{guild_id}/counting/announce", summary="Post the counting rules")
async def announce_counting(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Drop a rules card into the counting channel.

    Uses the cog's own renderer so the dashboard cannot drift away from
    what the bot posts during the game.
    """
    guild = _guild_or_404(bot, guild_id)
    settings = store.counting_get(guild_id)

    if not settings.get("channel"):
        raise HTTPException(status_code=400, detail="Es ist kein Kanal gesetzt.")
    channel = guild.get_channel(int(settings["channel"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    cog = bot.get_cog("Counting")
    if cog is None or not hasattr(cog, "rules_view"):
        raise HTTPException(status_code=503, detail="Das Zähl-Modul ist nicht geladen.")

    try:
        await channel.send(view=cog.rules_view(settings))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=502, detail=f"Discord lehnte ab: {exc}")

    return {"status": "success", "result": f"Regeln in #{channel.name} gepostet."}


# ══════════════════════════════════════════════════════════════════════
#  Notify
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/notify", summary="Stream and upload notifications")
async def get_notify(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.NOTIFY_DB)
    await store.notify_ensure(db)
    guild = bot.get_guild(guild_id)

    entries = []
    for row in await store.notify_list(db, guild_id):
        entries.append({
            "type": row["type"],
            "role": _role_info(guild, row["role_id"]),
            "channel": _channel_info(guild, row["channel_id"]),
            "legacy": row["legacy"],
        })

    return {
        "guild_id": str(guild_id),
        "entries": entries,
        "types": list(store.NOTIFY_TYPES),
        "has_legacy": any(e["legacy"] for e in entries),
    }


@router.post("/{guild_id}/notify", summary="Set up a notification")
async def set_notify(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    kind = str(data.get("type") or "").lower()
    if kind not in store.NOTIFY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannter Typ. Möglich: {', '.join(store.NOTIFY_TYPES)}",
        )

    role_id = str(data.get("role_id") or "")
    channel_id = str(data.get("channel_id") or "")
    if not role_id.isdigit() or not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte Rolle und Kanal auswählen.")

    if guild.get_channel(int(channel_id)) is None:
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
    if guild.get_role(int(role_id)) is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")

    db = await db_manager.get_connection(store.NOTIFY_DB)
    await store.notify_ensure(db)
    await store.notify_set(db, guild_id, kind, int(role_id), int(channel_id))

    return {"status": "success", "result": f"{kind}-Benachrichtigung gespeichert."}


@router.delete("/{guild_id}/notify/{kind}", summary="Remove a notification")
async def delete_notify(
    guild_id: int, kind: str, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await db_manager.get_connection(store.NOTIFY_DB)
    await store.notify_ensure(db)

    if not await store.notify_remove(db, guild_id, kind.lower()):
        raise HTTPException(status_code=404, detail="Dafür war nichts eingerichtet.")
    return {"status": "success", "result": "Entfernt."}


# ══════════════════════════════════════════════════════════════════════
#  Birthdays
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/birthday", summary="Birthdays on this server")
async def get_birthdays(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    entries = store.birthday_list(guild_id)

    people = []
    for entry in entries:
        member = guild.get_member(entry["user_id"]) if guild else None
        people.append({
            "user_id": str(entry["user_id"]),
            "date": entry["date"],
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
        })

    upcoming = store.birthday_upcoming(entries, days=60)
    for item in upcoming:
        member = guild.get_member(item["user_id"]) if guild else None
        item["user_id"] = str(item["user_id"])
        item["name"] = member.display_name if member else str(item["user_id"])

    return {
        "guild_id": str(guild_id),
        "entries": sorted(people, key=lambda p: p["name"].lower()),
        "upcoming": upcoming,
        "total": len(people),
    }


@router.post("/{guild_id}/birthday", summary="Add or change a birthday")
async def set_birthday(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)

    user_id = str(data.get("user_id") or "")
    date = str(data.get("date") or "").strip()

    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte ein Mitglied auswählen.")
    if not store.birthday_valid(date):
        raise HTTPException(
            status_code=400,
            detail="Datum bitte als TT.MM oder TT.MM.JJJJ, zum Beispiel 15.03.",
        )

    store.birthday_set(guild_id, int(user_id), date)
    await _reload(bot, "Birthdays", guild_id)

    return {"status": "success", "result": f"Geburtstag am {date} gespeichert."}


@router.delete("/{guild_id}/birthday/{user_id}", summary="Remove a birthday")
async def delete_birthday(
    guild_id: int, user_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    if not store.birthday_remove(guild_id, user_id):
        raise HTTPException(status_code=404, detail="Dafür war nichts gespeichert.")
    await _reload(bot, "Birthdays", guild_id)
    return {"status": "success", "result": "Entfernt."}
