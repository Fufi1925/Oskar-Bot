"""
Live actions from the dashboard into Discord.

Configuring a module in the dashboard writes to the database, but some
modules also need something to happen *in* Discord — a verification panel
posted into a channel, a ticket panel, a test message. Those used to require
running a bot command by hand.

These endpoints let the dashboard do it directly, and report what actually
happened instead of silently succeeding.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils.panels import Panel, StatusCard, ACCENT
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _require_channel(guild: discord.Guild, channel_id: str) -> discord.TextChannel:
    if not str(channel_id).isdigit():
        raise HTTPException(status_code=400, detail="A channel must be selected.")

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        raise HTTPException(status_code=404, detail="That channel no longer exists.")
    if not isinstance(channel, discord.TextChannel):
        raise HTTPException(status_code=400, detail="Please pick a text channel.")

    me = guild.me
    if me is not None:
        perms = channel.permissions_for(me)
        missing = [
            name
            for name, ok in (
                ("View Channel", perms.view_channel),
                ("Send Messages", perms.send_messages),
                ("Embed Links", perms.embed_links),
            )
            if not ok
        ]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"The bot is missing these permissions in #{channel.name}: {', '.join(missing)}",
            )

    return channel


def _guild_or_404(bot, guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")
    return guild


def _colour(raw, fallback: int = 0x5865F2) -> discord.Colour:
    try:
        if isinstance(raw, int):
            return discord.Colour(raw)
        text = str(raw or "").replace("#", "").strip()
        return discord.Colour(int(text, 16)) if text else discord.Colour(fallback)
    except Exception:
        return discord.Colour(fallback)


# ══════════════════════════════════════════════════════════════════════════
#  Verification
# ══════════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/verification/send", summary="Post the verification panel")
async def send_verification_panel(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Post the verification message with its buttons into a channel.

    Previously only reachable through a bot command, which meant configuring
    verification in the dashboard left you without a panel.
    """
    guild = _guild_or_404(bot, guild_id)

    async with aiosqlite.connect("db/verification.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS verification_config ("
            " guild_id INTEGER PRIMARY KEY, verification_channel_id INTEGER NOT NULL,"
            " verified_role_id INTEGER NOT NULL, log_channel_id INTEGER,"
            " verification_method TEXT DEFAULT 'both', enabled BOOLEAN DEFAULT 1,"
            " created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        await db.commit()
        async with db.execute(
            "SELECT verification_channel_id, verified_role_id, verification_method, enabled"
            " FROM verification_config WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=400,
            detail="Configure and save verification first, then send the panel.",
        )

    channel_id = str(data.get("channel_id") or row[0] or "")
    role_id = int(row[1] or 0)
    method = (row[2] or "both").lower()

    if not role_id or guild.get_role(role_id) is None:
        raise HTTPException(
            status_code=400,
            detail="The verified role is missing. Pick an existing role and save again.",
        )

    channel = _require_channel(guild, channel_id)

    # Reuse the cog's view so the buttons keep working after a restart.
    view = None
    try:
        from cogs.commands.verification import VerificationView

        view = VerificationView(bot)

        # Hide the button the configured method does not use.
        if method in ("quick", "button"):
            for item in list(view.children):
                if getattr(item, "custom_id", "") == "verify_captcha_secure":
                    view.remove_item(item)
        elif method == "captcha":
            for item in list(view.children):
                if getattr(item, "custom_id", "") == "verify_button_quick":
                    view.remove_item(item)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Verification module unavailable: {exc}"
        )

    # Components V2, so a panel posted from the dashboard is identical to the
    # one the cog posts itself instead of being a plain embed.
    panel = Panel(
        str(data.get("title") or "Verification required"),
        str(
            data.get("description")
            or f"Welcome to **{guild.name}**.\n"
            "Verify yourself to unlock the rest of the server."
        ),
        accent=_colour(data.get("color")).value if data.get("color") else ACCENT["brand"],
        buttons=list(view.children),
    )

    try:
        message = await channel.send(view=panel)
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"The bot may not post in #{channel.name}."
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord rejected the message: {exc}")

    # Keep the view alive across restarts.
    try:
        # Register the layout that was actually sent, not the source view —
        # otherwise the buttons stop responding after a restart.
        bot.add_view(panel, message_id=message.id)
    except Exception:
        pass

    await feature_audit.log_action(
        "verification_panel_sent",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"#{channel.name}",
    )

    return {
        "status": "success",
        "channel": channel.name,
        "message_id": str(message.id),
        "url": message.jump_url,
        "result": f"Verification panel posted in #{channel.name}.",
    }


# ══════════════════════════════════════════════════════════════════════════
#  Tickets
# ══════════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/tickets/send", summary="Post the ticket panel")
async def send_ticket_panel(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    cog = bot.get_cog("TicketCog")
    if cog is None:
        raise HTTPException(status_code=503, detail="The ticket module is not loaded.")

    async with aiosqlite.connect("db/ticket.db") as db:
        async with db.execute(
            "SELECT panel_channel_id, embed_title, embed_description, embed_color"
            " FROM guild_configs WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=400, detail="Set up the ticket system first, then send the panel."
        )

    channel = _require_channel(guild, str(data.get("channel_id") or row[0] or ""))

    view = None
    builder = getattr(cog, "create_panel_view", None)
    if callable(builder):
        try:
            view = builder(guild_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not build the panel: {exc}")

    if view is None:
        raise HTTPException(
            status_code=400,
            detail="Add at least one ticket category before sending the panel.",
        )

    # The ticket buttons are dispatched by the cog's global on_interaction
    # listener (custom_id starts with create_ticket_), so moving the
    # components into a V2 container keeps them working.
    panel = Panel(
        row[1] or "Support",
        row[2] or "Open a ticket and the team will help you.",
        accent=_colour(row[3]).value if row[3] else ACCENT["brand"],
        buttons=list(view.children),
    )

    try:
        message = await channel.send(view=panel)
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail=f"The bot may not post in #{channel.name}.")

    async with aiosqlite.connect("db/ticket.db") as db:
        await db.execute(
            "UPDATE guild_configs SET panel_message_id = ?, panel_channel_id = ? WHERE guild_id = ?",
            (message.id, channel.id, guild_id),
        )
        await db.commit()

    try:
        bot.add_view(view, message_id=message.id)
    except Exception:
        pass

    await feature_audit.log_action(
        "ticket_panel_sent",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"#{channel.name}",
    )

    return {
        "status": "success",
        "channel": channel.name,
        "message_id": str(message.id),
        "url": message.jump_url,
        "result": f"Ticket panel posted in #{channel.name}.",
    }


# ══════════════════════════════════════════════════════════════════════════
#  Welcome preview
# ══════════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/welcome/test", summary="Send a welcome preview")
async def test_welcome(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """Post the configured welcome message as if the caller had just joined."""
    guild = _guild_or_404(bot, guild_id)

    async with aiosqlite.connect("db/welcome.db") as db:
        async with db.execute(
            "SELECT welcome_type, welcome_message, channel_id, embed_data"
            " FROM welcome WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=400, detail="No welcome message configured yet.")

    welcome_type, message_text, channel_id, embed_raw = row
    channel = _require_channel(guild, str(data.get("channel_id") or channel_id or ""))

    # Resolve the same placeholders the live greeter uses.
    member = None
    actor = str(data.get("actor", ""))
    if actor.isdigit():
        member = guild.get_member(int(actor))
    member = member or guild.me

    def fill(text: str) -> str:
        return (
            (text or "")
            .replace("{user}", member.mention if member else "@member")
            .replace("{user.name}", member.display_name if member else "member")
            .replace("{server}", guild.name)
            .replace("{guild}", guild.name)
            .replace("{count}", str(guild.member_count or 0))
            .replace("{membercount}", str(guild.member_count or 0))
        )

    card = None
    if embed_raw:
        try:
            parsed = json.loads(embed_raw)
            sections = [
                fill(parsed.get("description", "")),
                fill(parsed.get("footer", "")),
            ]
            card = Panel(
                fill(parsed.get("title", "")) or "Welcome",
                *[s for s in sections if s],
                accent=_colour(parsed.get("color")).value
                if parsed.get("color")
                else ACCENT["brand"],
                image_url=parsed.get("image") or parsed.get("thumbnail") or None,
            )
        except Exception:
            card = None

    content = fill(message_text) if message_text else None
    if not content and card is None:
        raise HTTPException(status_code=400, detail="The welcome message is empty.")

    try:
        if card is not None:
            # A V2 layout cannot be combined with `content`, so the preview
            # marker becomes part of the card.
            message = await channel.send(view=card)
        else:
            message = await channel.send(content=f"**Preview**\n{content}")
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail=f"The bot may not post in #{channel.name}.")

    return {
        "status": "success",
        "channel": channel.name,
        "url": message.jump_url,
        "result": f"Preview sent to #{channel.name}.",
    }


# ══════════════════════════════════════════════════════════════════════════
#  Free-form message
# ══════════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/message/send", summary="Send a message as the bot")
async def send_message(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    channel = _require_channel(guild, str(data.get("channel_id", "")))

    content = str(data.get("content", "")).strip()
    as_embed = bool(data.get("embed", False))
    title = str(data.get("title", "")).strip()

    if not content and not title:
        raise HTTPException(status_code=400, detail="The message is empty.")
    if len(content) > 4000:
        raise HTTPException(status_code=400, detail="The message is too long (max 4000).")

    try:
        if as_embed:
            message = await channel.send(view=Panel(
                title or "",
                content or "",
                accent=_colour(data.get("color")).value
                if data.get("color")
                else ACCENT["brand"],
            ))
        else:
            message = await channel.send(content=content[:2000])
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail=f"The bot may not post in #{channel.name}.")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord rejected the message: {exc}")

    await feature_audit.log_action(
        "message_sent",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"#{channel.name}: {content[:80]}",
    )

    return {
        "status": "success",
        "channel": channel.name,
        "url": message.jump_url,
        "result": f"Message sent to #{channel.name}.",
    }


# ══════════════════════════════════════════════════════════════════════════
#  Automod verification
# ══════════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/automod/status", summary="What automod is actually doing")
async def automod_status(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    Confirms that the saved automod configuration is live.

    The cogs read the database on every message, so a saved change applies
    immediately — this endpoint shows exactly what they will read, so the
    dashboard can prove it rather than just claiming it.
    """
    guild = _guild_or_404(bot, guild_id)

    modules = {
        "Anti spam": "AntiSpam",
        "Anti caps": "AntiCaps",
        "Anti links": "AntiLink",
        "Anti invites": "AntiInvite",
        "Anti mass mention": "AntiMassMention",
        "Anti emoji spam": "AntiEmojiSpam",
    }

    async with aiosqlite.connect("db/automod.db") as db:
        async with db.execute(
            "SELECT enabled FROM automod WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        master = bool(row[0]) if row else False

        async with db.execute(
            "SELECT event, punishment FROM automod_punishments WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            punishments = {event: punishment for event, punishment in await cursor.fetchall()}

        async with db.execute(
            "SELECT type, id FROM automod_ignored WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            ignored = await cursor.fetchall()

        async with db.execute(
            "SELECT log_channel FROM automod_logging WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            log_row = await cursor.fetchone()

    entries = []
    for event, cog_name in modules.items():
        punishment = punishments.get(event)
        loaded = bot.get_cog(cog_name) is not None
        entries.append(
            {
                "event": event,
                "punishment": punishment,
                "active": bool(master and punishment),
                "listener_loaded": loaded,
            }
        )

    log_channel = guild.get_channel(int(log_row[0])) if log_row and log_row[0] else None

    # Permissions the punishments need to work at all.
    me = guild.me
    missing = []
    if me is not None:
        used = {p for p in punishments.values() if p}
        if not me.guild_permissions.manage_messages:
            missing.append("Manage Messages")
        if any(p in ("mute", "timeout") for p in used) and not me.guild_permissions.moderate_members:
            missing.append("Timeout Members")
        if "kick" in used and not me.guild_permissions.kick_members:
            missing.append("Kick Members")
        if "ban" in used and not me.guild_permissions.ban_members:
            missing.append("Ban Members")

    return {
        "guild_id": str(guild_id),
        "master_enabled": master,
        "modules": entries,
        "active_count": sum(1 for e in entries if e["active"]),
        "ignored_channels": [str(i) for t, i in ignored if t == "channel"],
        "ignored_roles": [str(i) for t, i in ignored if t == "role"],
        "log_channel": log_channel.name if log_channel else None,
        "missing_permissions": missing,
        "live": "Changes apply to the next message — the listeners read this on every message.",
    }


# ══════════════════════════════════════════════════════════════════════════
#  Giveaways
# ══════════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/giveaways", summary="Running giveaways")
async def list_giveaways(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    import time as _time

    async with aiosqlite.connect("db/giveaway.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS Giveaway ("
            " guild_id INTEGER, host_id INTEGER, start_time TIMESTAMP,"
            " ends_at TIMESTAMP, prize TEXT, winners INTEGER,"
            " message_id INTEGER, channel_id INTEGER,"
            " PRIMARY KEY (guild_id, message_id))"
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Giveaway WHERE guild_id = ? ORDER BY ends_at DESC LIMIT 50",
            (guild_id,),
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]

    now = _time.time()
    entries = []
    for row in rows:
        try:
            ends = float(row.get("ends_at") or 0)
        except (TypeError, ValueError):
            ends = 0
        channel = guild.get_channel(int(row.get("channel_id") or 0))
        host = bot.get_user(int(row.get("host_id") or 0))
        entries.append(
            {
                "message_id": str(row.get("message_id")),
                "prize": row.get("prize"),
                "winners": row.get("winners"),
                "ends_at": ends,
                "running": ends > now,
                "channel": channel.name if channel else None,
                "channel_id": str(row.get("channel_id") or ""),
                "host": str(host) if host else None,
                "url": (
                    f"https://discord.com/channels/{guild_id}/{row.get('channel_id')}/{row.get('message_id')}"
                    if row.get("channel_id") and row.get("message_id")
                    else None
                ),
            }
        )

    return {
        "guild_id": str(guild_id),
        "giveaways": entries,
        "running": sum(1 for e in entries if e["running"]),
    }


@router.post("/{guild_id}/giveaways", summary="Start a giveaway")
async def create_giveaway(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    import time as _time

    guild = _guild_or_404(bot, guild_id)
    channel = _require_channel(guild, str(data.get("channel_id", "")))

    prize = str(data.get("prize", "")).strip()[:200]
    if not prize:
        raise HTTPException(status_code=400, detail="Enter what is being given away.")

    try:
        winners = max(1, min(int(data.get("winners", 1)), 20))
        minutes = max(1, min(int(data.get("duration_minutes", 60)), 60 * 24 * 30))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Winners and duration must be numbers.")

    ends_at = _time.time() + minutes * 60

    panel = Panel(
        "🎉 Giveaway",
        f"### {prize}",
        (
            f"React with 🎉 to enter.\n"
            f"**Winners:** {winners}\n"
            f"**Ends:** <t:{int(ends_at)}:R>"
        ),
        accent=_colour(data.get("color", "f59e0b")).value,
    )

    try:
        message = await channel.send(view=panel)
        await message.add_reaction("🎉")
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail=f"The bot needs Send Messages and Add Reactions in #{channel.name}.",
        )

    async with aiosqlite.connect("db/giveaway.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS Giveaway ("
            " guild_id INTEGER, host_id INTEGER, start_time TIMESTAMP,"
            " ends_at TIMESTAMP, prize TEXT, winners INTEGER,"
            " message_id INTEGER, channel_id INTEGER,"
            " PRIMARY KEY (guild_id, message_id))"
        )
        actor = str(data.get("actor", "0"))
        await db.execute(
            "INSERT OR REPLACE INTO Giveaway"
            " (guild_id, host_id, start_time, ends_at, prize, winners, message_id, channel_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild_id,
                int(actor) if actor.isdigit() else 0,
                _time.time(),
                ends_at,
                prize,
                winners,
                message.id,
                channel.id,
            ),
        )
        await db.commit()

    await feature_audit.log_action(
        "giveaway_started",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{prize} in #{channel.name}",
    )

    return {
        "status": "success",
        "message_id": str(message.id),
        "url": message.jump_url,
        "ends_at": ends_at,
        "result": f"Giveaway for {prize} started in #{channel.name}.",
    }


@router.post("/{guild_id}/giveaways/{message_id}/end", summary="End a giveaway now")
async def end_giveaway(
    guild_id: int, message_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    import random

    guild = _guild_or_404(bot, guild_id)

    async with aiosqlite.connect("db/giveaway.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Giveaway WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Giveaway not found.")

    channel = guild.get_channel(int(row["channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="The giveaway channel no longer exists.")

    try:
        message = await channel.fetch_message(message_id)
    except Exception:
        raise HTTPException(status_code=404, detail="The giveaway message was deleted.")

    # Collect entrants from the reaction.
    users = []
    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            users = [u async for u in reaction.users() if not u.bot]
            break

    count = int(row["winners"] or 1)
    winners = random.sample(users, min(count, len(users))) if users else []

    if winners:
        names = ", ".join(w.mention for w in winners)
        text = f"🎉 Congratulations {names}! You won **{row['prize']}**."
    else:
        text = f"🎉 Nobody entered the giveaway for **{row['prize']}**."

    try:
        await channel.send(text, reference=message)
    except Exception:
        await channel.send(text)

    async with aiosqlite.connect("db/giveaway.db") as db:
        await db.execute(
            "DELETE FROM Giveaway WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        await db.commit()

    await feature_audit.log_action(
        "giveaway_ended",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{row['prize']}: {len(winners)} winner(s)",
    )

    return {
        "status": "success",
        "winners": [str(w) for w in winners],
        "entrants": len(users),
        "result": f"Giveaway ended with {len(winners)} winner(s) out of {len(users)} entrants.",
    }


@router.delete("/{guild_id}/giveaways/{message_id}", summary="Cancel a giveaway")
async def cancel_giveaway(guild_id: int, message_id: int, actor: str = ""):
    async with aiosqlite.connect("db/giveaway.db") as db:
        cursor = await db.execute(
            "DELETE FROM Giveaway WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Giveaway not found.")

    await feature_audit.log_action(
        "giveaway_cancelled", actor=actor, guild_id=guild_id, detail=str(message_id)
    )
    return {"status": "success", "result": "Giveaway cancelled."}


# ══════════════════════════════════════════════════════════════════════════
#  Autoresponder
# ══════════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/autoresponder", summary="Autoresponder triggers")
async def list_autoresponders(guild_id: int):
    async with aiosqlite.connect("db/autoresponder.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS autoresponses ("
            " guild_id INTEGER, name TEXT, message TEXT,"
            " PRIMARY KEY (guild_id, name))"
        )
        await db.commit()
        async with db.execute(
            "SELECT name, message FROM autoresponses WHERE guild_id = ? ORDER BY name",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return {
        "guild_id": str(guild_id),
        "responses": [{"trigger": n, "response": m} for n, m in rows],
        "count": len(rows),
    }


@router.post("/{guild_id}/autoresponder", summary="Add or update an autoresponder")
async def upsert_autoresponder(guild_id: int, data: dict):
    trigger = str(data.get("trigger", "")).strip()[:100]
    response = str(data.get("response", "")).strip()[:1900]

    if not trigger:
        raise HTTPException(status_code=400, detail="Enter a trigger word.")
    if not response:
        raise HTTPException(status_code=400, detail="Enter what the bot should reply.")

    async with aiosqlite.connect("db/autoresponder.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS autoresponses ("
            " guild_id INTEGER, name TEXT, message TEXT,"
            " PRIMARY KEY (guild_id, name))"
        )
        await db.execute(
            "INSERT OR REPLACE INTO autoresponses (guild_id, name, message) VALUES (?, ?, ?)",
            (guild_id, trigger, response),
        )
        await db.commit()

    await feature_audit.log_action(
        "autoresponder_saved",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=trigger,
    )
    return {"status": "success", "trigger": trigger}


@router.delete("/{guild_id}/autoresponder/{trigger}", summary="Delete an autoresponder")
async def delete_autoresponder(guild_id: int, trigger: str, actor: str = ""):
    async with aiosqlite.connect("db/autoresponder.db") as db:
        cursor = await db.execute(
            "DELETE FROM autoresponses WHERE guild_id = ? AND name = ?", (guild_id, trigger)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trigger not found.")

    await feature_audit.log_action(
        "autoresponder_deleted", actor=actor, guild_id=guild_id, detail=trigger
    )
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════════
#  Emergency lockdown
# ══════════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/emergency", summary="Emergency lockdown state")
async def emergency_status(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)

    async with aiosqlite.connect("db/emergency.db") as db:
        for statement in (
            "CREATE TABLE IF NOT EXISTS authorised_users (guild_id INTEGER, user_id INTEGER)",
            "CREATE TABLE IF NOT EXISTS restore_roles (guild_id INTEGER NOT NULL,"
            " role_id INTEGER NOT NULL, disabled_perms TEXT NOT NULL,"
            " PRIMARY KEY (guild_id, role_id))",
        ):
            await db.execute(statement)
        await db.commit()

        async with db.execute(
            "SELECT user_id FROM authorised_users WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            authorised = [str(r[0]) for r in await cursor.fetchall()]

        async with db.execute(
            "SELECT role_id FROM restore_roles WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            locked_roles = [int(r[0]) for r in await cursor.fetchall()]

    users = []
    for uid in authorised:
        user = bot.get_user(int(uid)) if uid.isdigit() else None
        users.append({"id": uid, "name": str(user) if user else None})

    return {
        "guild_id": str(guild_id),
        "active": len(locked_roles) > 0,
        "locked_roles": [
            {"id": str(rid), "name": (guild.get_role(rid).name if guild.get_role(rid) else "deleted role")}
            for rid in locked_roles
        ],
        "authorised_users": users,
    }


@router.post("/{guild_id}/emergency", summary="Start or stop emergency lockdown")
async def toggle_emergency(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Lockdown strips dangerous permissions from every non-managed role and
    remembers what it removed, so it can be undone exactly.
    """
    guild = _guild_or_404(bot, guild_id)
    enable = bool(data.get("enable", True))
    actor = str(data.get("actor", "dashboard"))

    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        raise HTTPException(
            status_code=403, detail="The bot needs the Manage Roles permission."
        )

    # Permissions a raider would need. Everything else is left untouched so
    # the server keeps working during a lockdown.
    DANGEROUS = (
        "administrator", "ban_members", "kick_members", "manage_channels",
        "manage_guild", "manage_roles", "manage_webhooks", "mention_everyone",
        "manage_messages", "moderate_members",
    )
    changed = 0

    async with aiosqlite.connect("db/emergency.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS restore_roles (guild_id INTEGER NOT NULL,"
            " role_id INTEGER NOT NULL, disabled_perms TEXT NOT NULL,"
            " PRIMARY KEY (guild_id, role_id))"
        )
        await db.commit()

        if enable:
            for role in guild.roles:
                if role.is_default() or role.managed or role >= me.top_role:
                    continue

                removed = [
                    name for name in DANGEROUS if getattr(role.permissions, name, False)
                ]
                if not removed:
                    continue

                perms = discord.Permissions(role.permissions.value)
                for name in removed:
                    setattr(perms, name, False)

                try:
                    await role.edit(permissions=perms, reason=f"Emergency lockdown by {actor}")
                except Exception:
                    continue

                await db.execute(
                    "INSERT OR REPLACE INTO restore_roles (guild_id, role_id, disabled_perms)"
                    " VALUES (?, ?, ?)",
                    (guild_id, role.id, ",".join(removed)),
                )
                changed += 1
        else:
            async with db.execute(
                "SELECT role_id, disabled_perms FROM restore_roles WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                saved = await cursor.fetchall()

            for role_id, perm_list in saved:
                role = guild.get_role(int(role_id))
                if role is None:
                    continue
                perms = discord.Permissions(role.permissions.value)
                for name in (perm_list or "").split(","):
                    if name:
                        setattr(perms, name, True)
                try:
                    await role.edit(permissions=perms, reason=f"Lockdown lifted by {actor}")
                    changed += 1
                except Exception:
                    continue

            await db.execute("DELETE FROM restore_roles WHERE guild_id = ?", (guild_id,))

        await db.commit()

    await feature_audit.log_action(
        "emergency_lockdown" if enable else "emergency_lifted",
        actor=actor,
        guild_id=guild_id,
        detail=f"{changed} roles affected",
    )

    return {
        "status": "success",
        "active": enable,
        "roles_changed": changed,
        "result": (
            f"Lockdown active — dangerous permissions removed from {changed} roles."
            if enable
            else f"Lockdown lifted — permissions restored on {changed} roles."
        ),
    }
