# ╔══════════════════════════════════════════════════════════════════╗
# ║   Join DM, no-prefix and reaction roles                          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Three tabs that each had a single GET/PATCH pair and no way to see what
the bot was really doing.

The bugs behind the rewrite:

  * **No-prefix leaked across servers.** The `np` table has no guild
    column, so every server's dashboard showed the same global list —
    and saving on one server ran `DELETE FROM np WHERE id NOT IN (...)`,
    wiping the entries another server had made.
  * **Join DM was off after every restart.** `joindm enable` registered
    a listener at runtime instead of storing a flag.
  * **Reaction roles never got their reaction.** The chat command calls
    `message.add_reaction(...)`; the API route only wrote a database row,
    so an entry created in the dashboard left members with nothing to
    click on.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import joindm_store as joindm
from utils import noprefix_store as noprefix

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

RR_DB = "rr.db"


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


async def _notify_cog(bot, name: str, guild_id: int) -> None:
    """
    Tell a cog to reload its cache.

    Without this the bot keeps using the old settings until it restarts,
    and the dashboard looks like it saved nothing.
    """
    cog = bot.get_cog(name)
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  Join DM
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/joindm", summary="Join DM settings")
async def get_joindm(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(joindm.DB_PATH)
    await joindm.ensure_schema(db)
    settings = await joindm.get(db, guild_id)

    return {
        "guild_id": str(guild_id),
        **settings,
        "enabled": bool(settings["enabled"]),
        "colour_hex": f"#{settings['colour']:06x}",
        "placeholders": joindm.PLACEHOLDERS,
    }


@router.patch("/{guild_id}/joindm", summary="Change the Join DM")
async def patch_joindm(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await db_manager.get_connection(joindm.DB_PATH)
    await joindm.ensure_schema(db)

    updates = {k: v for k, v in data.items() if k in joindm.DEFAULTS}
    if "colour_hex" in data and "colour" not in updates:
        try:
            updates["colour"] = int(str(data["colour_hex"]).lstrip("#"), 16)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Ungültige Farbe.")

    if not updates:
        return {"status": "success", "result": "Nichts zu ändern."}

    # Switching it on without a text would look like it works and send
    # nothing, which is the failure mode this rewrite exists to remove.
    if updates.get("enabled"):
        current = await joindm.get(db, guild_id)
        text = str(updates.get("message", current.get("message")) or "").strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Ohne Nachricht kann nichts verschickt werden — trag "
                       "zuerst einen Text ein.",
            )

    merged = await joindm.save(db, guild_id, updates)
    await _notify_cog(bot, "JoinDM", guild_id)

    await feature_audit.log_action(
        "joindm_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=", ".join(sorted(updates)),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "settings": {**merged, "colour_hex": f"#{merged['colour']:06x}"},
    }


@router.post("/{guild_id}/joindm/test", summary="Send the Join DM to yourself")
async def test_joindm(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Deliver the DM to the person clicking, exactly as a new member gets
    it — including whether their own DMs are even open.
    """
    guild = _guild_or_404(bot, guild_id)

    actor = str(data.get("actor", ""))
    if not actor.isdigit():
        raise HTTPException(status_code=400, detail="Wer soll die Testnachricht bekommen?")

    member = guild.get_member(int(actor))
    if member is None:
        raise HTTPException(
            status_code=404, detail="Du bist auf diesem Server nicht zu finden."
        )

    db = await db_manager.get_connection(joindm.DB_PATH)
    await joindm.ensure_schema(db)
    settings = await joindm.get(db, guild_id)

    # Use the unsaved draft if one was sent, so a preview does not force
    # a save first.
    draft = {k: v for k, v in data.items() if k in joindm.DEFAULTS}
    if draft:
        settings = joindm.normalise({**settings, **draft})

    if not str(settings.get("message") or "").strip():
        raise HTTPException(status_code=400, detail="Es ist keine Nachricht eingetragen.")

    try:
        await member.send(view=joindm.build_view(settings, member, guild))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail="Deine DMs sind zu. Genau das passiert auch bei Mitgliedern, "
                   "die private Nachrichten für diesen Server gesperrt haben — "
                   "die bekommen dann nichts.",
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord lehnte ab: {exc}")

    return {"status": "success", "result": "Testnachricht ist in deinen DMs."}


# ══════════════════════════════════════════════════════════════════════
#  No prefix
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/noprefix", summary="Who may skip the prefix")
async def get_noprefix(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(noprefix.DB_PATH)
    await noprefix.ensure_schema(db)
    guild = bot.get_guild(guild_id)

    users = []
    for entry in await noprefix.list_users(db, guild_id):
        member = guild.get_member(entry["user_id"]) if guild else None
        users.append({
            # A snowflake as a JS number loses its last digits.
            "user_id": str(entry["user_id"]),
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
            "expires_at": entry["expires_at"],
            "expired": entry["expired"],
            "global": entry["global"],
        })

    roles = []
    for role_id in await noprefix.list_roles(db, guild_id):
        role = guild.get_role(role_id) if guild else None
        roles.append({
            "role_id": str(role_id),
            "name": role.name if role else None,
            "colour": role.color.value if role else None,
            "members": len(role.members) if role else 0,
            "missing": role is None,
        })

    return {
        "guild_id": str(guild_id),
        "users": users,
        "roles": roles,
        # Explains the "global" badge in the UI rather than leaving it
        # looking like a bug.
        "has_global": any(u["global"] for u in users),
    }


@router.post("/{guild_id}/noprefix/users", summary="Grant no-prefix to a member")
async def add_noprefix_user(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    user_id = str(data.get("user_id") or "")
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte ein Mitglied auswählen.")

    expires_at = None
    if data.get("days"):
        try:
            days = max(1, min(int(data["days"]), 3650))
            expires_at = time.time() + days * 86400
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Die Dauer muss eine Zahl sein.")

    db = await db_manager.get_connection(noprefix.DB_PATH)
    await noprefix.ensure_schema(db)
    await noprefix.add_user(
        db, guild_id, int(user_id), expires_at=expires_at,
        added_by=int(str(data.get("actor", "0")))
        if str(data.get("actor", "0")).isdigit() else 0,
    )

    invalidate = getattr(bot, "invalidate_no_prefix_cache", None)
    if callable(invalidate):
        invalidate()

    member = guild.get_member(int(user_id))
    await feature_audit.log_action(
        "noprefix_add", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=user_id,
    )
    return {
        "status": "success",
        "result": f"{member.display_name if member else user_id} braucht hier "
                  "keinen Prefix mehr.",
    }


@router.delete("/{guild_id}/noprefix/users/{user_id}", summary="Revoke no-prefix")
async def remove_noprefix_user(
    guild_id: int, user_id: int, scope: str = "guild", actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    """
    `scope=guild` removes the entry for this server. `scope=global`
    removes a legacy entry that applies everywhere — separate on purpose,
    so one server cannot silently revoke what another granted.
    """
    db = await db_manager.get_connection(noprefix.DB_PATH)
    await noprefix.ensure_schema(db)

    if scope == "global":
        removed = await noprefix.remove_global_user(db, user_id)
        note = "Der serverübergreifende Eintrag wurde entfernt."
    else:
        removed = await noprefix.remove_user(db, guild_id, user_id)
        note = "Entfernt."

    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Dieser Eintrag gehört einem anderen Server oder gibt es nicht.",
        )

    invalidate = getattr(bot, "invalidate_no_prefix_cache", None)
    if callable(invalidate):
        invalidate()

    await feature_audit.log_action(
        "noprefix_remove", actor=actor or "dashboard",
        guild_id=guild_id, detail=f"{user_id} ({scope})",
    )
    return {"status": "success", "result": note}


@router.post("/{guild_id}/noprefix/roles", summary="Grant no-prefix to a role")
async def add_noprefix_role(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)

    role_id = str(data.get("role_id") or "")
    if not role_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine Rolle auswählen.")

    role = guild.get_role(int(role_id))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")

    # @everyone here would hand the whole server no-prefix, which is
    # almost never what somebody means to click.
    if role.is_default():
        raise HTTPException(
            status_code=400,
            detail="@everyone würde jedem auf dem Server No-Prefix geben.",
        )

    db = await db_manager.get_connection(noprefix.DB_PATH)
    await noprefix.ensure_schema(db)
    await noprefix.add_role(db, guild_id, int(role_id))

    invalidate = getattr(bot, "invalidate_no_prefix_cache", None)
    if callable(invalidate):
        invalidate()

    await feature_audit.log_action(
        "noprefix_role_add", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"@{role.name}",
    )
    return {
        "status": "success",
        "result": f"@{role.name} ({len(role.members)} Mitglieder) braucht keinen Prefix.",
    }


@router.delete("/{guild_id}/noprefix/roles/{role_id}", summary="Revoke from a role")
async def remove_noprefix_role(
    guild_id: int, role_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await db_manager.get_connection(noprefix.DB_PATH)
    await noprefix.ensure_schema(db)

    if not await noprefix.remove_role(db, guild_id, role_id):
        raise HTTPException(status_code=404, detail="Diese Rolle war nicht eingetragen.")

    invalidate = getattr(bot, "invalidate_no_prefix_cache", None)
    if callable(invalidate):
        invalidate()

    return {"status": "success", "result": "Entfernt."}


# ══════════════════════════════════════════════════════════════════════
#  Reaction roles
# ══════════════════════════════════════════════════════════════════════


async def _rr_db():
    db = await db_manager.get_connection(RR_DB)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id INTEGER,
            message_id INTEGER,
            emoji TEXT,
            role_id INTEGER
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS rr_settings (
            guild_id INTEGER PRIMARY KEY,
            dm_enabled INTEGER DEFAULT 1
        )
        """
    )
    await db.commit()
    return db


@router.get("/{guild_id}/reactionroles", summary="Reaction roles, grouped by message")
async def get_reactionroles(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    Grouped by message rather than a flat list: that is how people think
    about them ("this post hands out these four roles"), and it makes a
    dead message obvious at a glance.
    """
    db = await _rr_db()
    guild = bot.get_guild(guild_id)

    async with db.execute(
        "SELECT dm_enabled FROM rr_settings WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    dm_enabled = bool(row[0]) if row else True

    async with db.execute(
        "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    grouped: dict[int, list] = {}
    for message_id, emoji, role_id in rows:
        grouped.setdefault(int(message_id), []).append((emoji, int(role_id)))

    messages = []
    for message_id, entries in grouped.items():
        items = []
        for emoji, role_id in entries:
            role = guild.get_role(role_id) if guild else None
            items.append({
                "emoji": emoji,
                "role_id": str(role_id),
                "role_name": role.name if role else None,
                "role_colour": role.color.value if role else None,
                "missing_role": role is None,
            })
        messages.append({
            "message_id": str(message_id),
            "entries": items,
            "url": (
                f"https://discord.com/channels/{guild_id}/0/{message_id}"
                if guild else None
            ),
        })

    return {
        "guild_id": str(guild_id),
        "dm_enabled": dm_enabled,
        "messages": messages,
        "total": len(rows),
    }


@router.post("/{guild_id}/reactionroles", summary="Add a reaction role")
async def add_reactionrole(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Store the pair **and put the reaction on the message**.

    The old route only wrote the database row. The chat command calls
    `add_reaction`, the API did not — so an entry created in the
    dashboard left members with nothing to click.
    """
    guild = _guild_or_404(bot, guild_id)

    channel_id = str(data.get("channel_id") or "")
    message_id = str(data.get("message_id") or "")
    role_id = str(data.get("role_id") or "")
    emoji = str(data.get("emoji") or "").strip()

    if not message_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte die Nachrichten-ID angeben.")
    if not role_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine Rolle auswählen.")
    if not emoji:
        raise HTTPException(status_code=400, detail="Bitte ein Emoji angeben.")

    role = guild.get_role(int(role_id))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")

    # Checking now avoids a row that can never work.
    me = guild.me
    if me is not None:
        if not me.guild_permissions.manage_roles:
            raise HTTPException(
                status_code=400, detail="Dem Bot fehlt „Rollen verwalten“."
            )
        if role >= me.top_role:
            raise HTTPException(
                status_code=400,
                detail=f"@{role.name} steht über der Rolle des Bots — er könnte "
                       "sie niemandem geben. Schieb die Bot-Rolle darüber.",
            )
        if role.managed:
            raise HTTPException(
                status_code=400,
                detail=f"@{role.name} wird von einer Integration verwaltet.",
            )

    # Find the message. Without a channel we have to search, which is why
    # the dashboard asks for one.
    message = None
    if channel_id.isdigit():
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "fetch_message"):
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        try:
            message = await channel.fetch_message(int(message_id))
        except discord.NotFound:
            raise HTTPException(
                status_code=404,
                detail="In diesem Kanal gibt es keine Nachricht mit dieser ID.",
            )
        except discord.Forbidden:
            raise HTTPException(
                status_code=403, detail="Der Bot darf diesen Kanal nicht lesen."
            )
    else:
        raise HTTPException(status_code=400, detail="Bitte den Kanal auswählen.")

    db = await _rr_db()
    async with db.execute(
        "SELECT 1 FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
        (guild_id, int(message_id), emoji),
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"{emoji} ist auf dieser Nachricht schon vergeben.",
            )

    # React first: if Discord rejects the emoji there is no point storing
    # a row nobody can ever trigger.
    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        raise HTTPException(
            status_code=400,
            detail=f"Discord kennt {emoji} nicht oder der Bot kann es nicht "
                   "benutzen. Server-Emojis gehen nur von Servern, auf denen "
                   "der Bot ist.",
        )
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail="Dem Bot fehlt „Reaktionen hinzufügen“ in diesem Kanal.",
        )

    await db.execute(
        "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id)"
        " VALUES (?, ?, ?, ?)",
        (guild_id, int(message_id), emoji, int(role_id)),
    )
    await db.commit()

    await feature_audit.log_action(
        "reactionrole_add", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{emoji} → @{role.name}",
    )
    return {
        "status": "success",
        "result": f"{emoji} gibt jetzt @{role.name}.",
        "url": message.jump_url,
    }


@router.delete("/{guild_id}/reactionroles", summary="Remove a reaction role")
async def remove_reactionrole(
    guild_id: int, message_id: str, emoji: str, channel_id: str = "",
    actor: str = "", bot: "universitybot" = Depends(get_bot),
):
    db = await _rr_db()
    cursor = await db.execute(
        "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
        (guild_id, int(message_id), emoji),
    )
    await db.commit()

    if not (cursor.rowcount or 0):
        raise HTTPException(status_code=404, detail="Diesen Eintrag gibt es nicht.")

    # Take the reaction off too, otherwise the message keeps inviting
    # clicks that no longer do anything.
    guild = bot.get_guild(guild_id)
    if guild and channel_id.isdigit():
        channel = guild.get_channel(int(channel_id))
        if channel is not None and hasattr(channel, "fetch_message"):
            try:
                message = await channel.fetch_message(int(message_id))
                await message.clear_reaction(emoji)
            except Exception:
                pass

    await feature_audit.log_action(
        "reactionrole_remove", actor=actor or "dashboard",
        guild_id=guild_id, detail=f"{emoji} auf {message_id}",
    )
    return {"status": "success", "result": "Entfernt."}


@router.patch("/{guild_id}/reactionroles", summary="Reaction role settings")
async def patch_reactionroles(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _rr_db()

    if "dm_enabled" in data:
        await db.execute(
            "INSERT OR REPLACE INTO rr_settings (guild_id, dm_enabled) VALUES (?, ?)",
            (guild_id, 1 if data["dm_enabled"] else 0),
        )
        await db.commit()

    return {"status": "success", "result": "Gespeichert."}


@router.post("/{guild_id}/reactionroles/verify", summary="Check every entry")
async def verify_reactionroles(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Walk every stored pair and report what is broken.

    Messages get deleted, roles get deleted, reactions get cleared — and
    all three leave a row that looks fine in the dashboard and does
    nothing in Discord.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await _rr_db()

    async with db.execute(
        "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    problems = []
    checked = 0
    repaired = 0

    # Cache per message so ten entries on one post are one fetch.
    seen: dict[int, object] = {}

    for message_id, emoji, role_id in rows:
        checked += 1
        role = guild.get_role(int(role_id))
        if role is None:
            problems.append(f"{emoji}: die Rolle wurde gelöscht")
            continue

        if int(message_id) not in seen:
            found = None
            for channel in guild.text_channels:
                try:
                    found = await channel.fetch_message(int(message_id))
                    break
                except (discord.NotFound, discord.Forbidden):
                    continue
                except Exception:
                    continue
            seen[int(message_id)] = found

        message = seen[int(message_id)]
        if message is None:
            problems.append(f"{emoji} → @{role.name}: Nachricht nicht gefunden")
            continue

        # Missing reaction: nothing to click on.
        has_reaction = any(str(r.emoji) == emoji for r in message.reactions)
        if not has_reaction:
            try:
                await message.add_reaction(emoji)
                repaired += 1
            except Exception:
                problems.append(f"{emoji}: Reaktion fehlt und konnte nicht gesetzt werden")

        me = guild.me
        if me is not None and role >= me.top_role:
            problems.append(f"@{role.name} steht über der Bot-Rolle")

    return {
        "status": "success",
        "checked": checked,
        "repaired": repaired,
        "problems": problems,
        "result": (
            f"{checked} geprüft, {repaired} Reaktion(en) nachgetragen"
            + (f", {len(problems)} Problem(e)." if problems else ", alles in Ordnung.")
        ),
    }
