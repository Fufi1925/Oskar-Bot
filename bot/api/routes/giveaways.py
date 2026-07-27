# ╔══════════════════════════════════════════════════════════════════╗
# ║   Giveaways                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Giveaways with a join button, custom text and rerolls.

Replaces the reaction-based flow in api/routes/actions.py, which also
wrote to the wrong database file — `db/giveaway.db` instead of the
`db/giveaways.db` the cog reads — so a giveaway started from the
dashboard never ended on its own.
"""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api import giveaways as store
from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

DEFAULT_TITLE = "🎉 Gewinnspiel"
DEFAULT_DESCRIPTION = (
    "**{prize}**\n\n"
    "Drücke den Knopf, um teilzunehmen.\n"
    "**Gewinner:** {winners}\n"
    "**Endet:** {ends}"
)
DEFAULT_BUTTON = "Teilnehmen"
DEFAULT_EMOJI = "🎉"


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


def _channel_or_400(guild, channel_id):
    if not str(channel_id or "").isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal wählen.")
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        raise HTTPException(status_code=404, detail="Der Kanal existiert nicht mehr.")
    if not hasattr(channel, "send"):
        raise HTTPException(status_code=400, detail="Bitte einen Textkanal wählen.")
    return channel


def build_view(record: dict, *, entries: int, ended: bool = False, winners_text=""):
    """The giveaway message, as a Components V2 panel."""
    from utils.panels import ACCENT, Panel

    ends_at = int(record.get("ends_at") or 0)
    values = {
        "prize": record.get("prize") or "",
        "winners": record.get("winners") or 1,
        "ends": f"<t:{ends_at}:R>" if ends_at else "—",
        "ends_full": f"<t:{ends_at}:F>" if ends_at else "—",
        "host": f"<@{record.get('host_id')}>" if record.get("host_id") else "—",
        "entries": entries,
    }

    title = store.fill_placeholders(record.get("title") or DEFAULT_TITLE, values)
    body = store.fill_placeholders(
        record.get("description") or DEFAULT_DESCRIPTION, values
    )

    sections = [body]
    if ended:
        sections.append(
            f"**Gewonnen:** {winners_text}" if winners_text
            else "Niemand hat teilgenommen."
        )
    else:
        sections.append(f"**Teilnehmer:** {entries}")

    buttons = []
    if not ended:
        buttons.append(
            discord.ui.Button(
                label=(record.get("button_label") or DEFAULT_BUTTON)[:80],
                emoji=record.get("button_emoji") or DEFAULT_EMOJI,
                style=discord.ButtonStyle.success,
                custom_id=f"giveaway_join_{record['message_id']}",
            )
        )

    return Panel(
        title,
        *sections,
        accent=record.get("colour") or ACCENT["giveaway"],
        image_url=record.get("image_url") or None,
        buttons=buttons,
    )


async def _refresh_message(bot, record: dict, db) -> None:
    """Redraw the message so the entry count stays current."""
    guild = bot.get_guild(int(record["guild_id"]))
    if guild is None:
        return
    channel = guild.get_channel(int(record["channel_id"]))
    if channel is None:
        return
    try:
        message = await channel.fetch_message(int(record["message_id"]))
        entries = await store.entry_count(db, int(record["message_id"]))
        await message.edit(view=build_view(record, entries=entries))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
#  Read
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}", summary="Giveaways of a guild")
async def list_giveaways(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    guild = bot.get_guild(guild_id)

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM Giveaway WHERE guild_id = ? ORDER BY ends_at DESC LIMIT 50",
        (guild_id,),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]

    now = _time.time()
    entries = []
    for row in rows:
        message_id = int(row["message_id"])
        ends = float(row.get("ends_at") or 0)
        ended = bool(row.get("ended")) or ends <= now
        channel = guild.get_channel(int(row.get("channel_id") or 0)) if guild else None

        winner_ids = await store.past_winner_ids(db, message_id)
        entries.append({
            "message_id": str(message_id),
            "prize": row.get("prize"),
            "title": row.get("title") or "",
            "description": row.get("description") or "",
            "colour": row.get("colour"),
            "button_label": row.get("button_label") or "",
            "button_emoji": row.get("button_emoji") or "",
            "image_url": row.get("image_url") or "",
            "required_role_id": (
                str(row["required_role_id"]) if row.get("required_role_id") else None
            ),
            "dm_winners": bool(row.get("dm_winners", 1)),
            "dm_host": bool(row.get("dm_host", 1)),
            "winners": row.get("winners"),
            "ends_at": ends,
            "running": not ended,
            "entries": await store.entry_count(db, message_id),
            "winner_ids": [str(w) for w in winner_ids],
            "channel": channel.name if channel else None,
            "channel_id": str(row.get("channel_id") or ""),
            "host_id": str(row.get("host_id") or ""),
            "url": (
                f"https://discord.com/channels/{guild_id}/{row.get('channel_id')}/{message_id}"
                if row.get("channel_id")
                else None
            ),
        })

    return {
        "guild_id": str(guild_id),
        "giveaways": entries,
        "running": sum(1 for e in entries if e["running"]),
    }


@router.get("/{guild_id}/{message_id}/entries", summary="Who joined")
async def list_entries(
    guild_id: int, message_id: int, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    people = []
    for user_id in await store.entry_ids(db, message_id):
        member = guild.get_member(user_id)
        people.append({
            "id": str(user_id),
            "name": member.display_name if member else f"Unbekannt ({user_id})",
            "left": member is None,
        })

    return {"entries": people, "count": len(people)}


# ══════════════════════════════════════════════════════════════════════
#  Create
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}", summary="Start a giveaway")
async def create_giveaway(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)
    channel = _channel_or_400(guild, data.get("channel_id"))

    prize = str(data.get("prize", "")).strip()[:200]
    if not prize:
        raise HTTPException(status_code=400, detail="Bitte einen Preis eintragen.")

    try:
        winners = max(1, min(int(data.get("winners", 1)), 20))
        minutes = max(1, min(int(data.get("duration_minutes", 60)), 60 * 24 * 60))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="Gewinner und Laufzeit müssen Zahlen sein."
        )

    actor = str(data.get("actor", "0"))
    ends_at = _time.time() + minutes * 60

    record = {
        "guild_id": guild_id,
        "host_id": int(actor) if actor.isdigit() else 0,
        "start_time": _time.time(),
        "ends_at": ends_at,
        "prize": prize,
        "winners": winners,
        "message_id": 0,  # filled in after the message exists
        "channel_id": channel.id,
        "title": str(data.get("title", "") or "")[:200],
        "description": str(data.get("description", "") or "")[:2000],
        "colour": data.get("colour"),
        "button_label": str(data.get("button_label", "") or "")[:80],
        "button_emoji": str(data.get("button_emoji", "") or "")[:32],
        "image_url": str(data.get("image_url", "") or "")[:400],
        "required_role_id": (
            int(data["required_role_id"])
            if str(data.get("required_role_id") or "").isdigit()
            else None
        ),
        "dm_winners": 1 if data.get("dm_winners", True) else 0,
        "dm_host": 1 if data.get("dm_host", True) else 0,
    }

    # Post first, then store — the custom_id needs the message id, so the
    # message is sent once and edited straight after.
    try:
        message = await channel.send(view=build_view(record, entries=0))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )

    record["message_id"] = message.id

    await db.execute(
        "INSERT OR REPLACE INTO Giveaway (guild_id, host_id, start_time, ends_at,"
        " prize, winners, message_id, channel_id, title, description, colour,"
        " button_label, button_emoji, image_url, required_role_id, dm_winners,"
        " dm_host, ended)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (
            guild_id, record["host_id"], record["start_time"], ends_at, prize,
            winners, message.id, channel.id, record["title"], record["description"],
            record["colour"], record["button_label"], record["button_emoji"],
            record["image_url"], record["required_role_id"],
            record["dm_winners"], record["dm_host"],
        ),
    )
    await db.commit()

    # Re-render so the button carries the real message id.
    try:
        view = build_view(record, entries=0)
        await message.edit(view=view)
        bot.add_view(view, message_id=message.id)
    except Exception:
        pass

    await feature_audit.log_action(
        "giveaway_started", actor=actor, guild_id=guild_id,
        detail=f"{prize} in #{channel.name}",
    )

    return {
        "status": "success",
        "message_id": str(message.id),
        "url": message.jump_url,
        "result": f"Gewinnspiel für {prize} in #{channel.name} gestartet.",
    }


# ══════════════════════════════════════════════════════════════════════
#  Draw / reroll / cancel
# ══════════════════════════════════════════════════════════════════════


async def _announce(bot, record: dict, winner_ids: list[int], *, reroll=False):
    """Edit the message, reply with the result and send the DMs."""
    guild = bot.get_guild(int(record["guild_id"]))
    if guild is None:
        return
    channel = guild.get_channel(int(record["channel_id"]))
    if channel is None:
        return

    mentions = ", ".join(f"<@{w}>" for w in winner_ids)
    prize = record.get("prize")

    try:
        message = await channel.fetch_message(int(record["message_id"]))
    except Exception:
        message = None

    if message is not None and not reroll:
        try:
            await message.edit(
                view=build_view(record, entries=0, ended=True, winners_text=mentions)
            )
        except Exception:
            pass

    if winner_ids:
        text = (
            f"🎉 Neu ausgelost: {mentions} gewinnt **{prize}**!"
            if reroll
            else f"🎉 Glückwunsch {mentions}! Ihr gewinnt **{prize}**."
        )
    else:
        text = f"Niemand hat am Gewinnspiel für **{prize}** teilgenommen."

    try:
        if message is not None:
            await channel.send(text, reference=message)
        else:
            await channel.send(text)
    except Exception:
        pass

    # DM the winners — this is the part people actually notice.
    if record.get("dm_winners", 1) and winner_ids:
        url = (
            f"https://discord.com/channels/{record['guild_id']}"
            f"/{record['channel_id']}/{record['message_id']}"
        )
        for user_id in winner_ids:
            member = guild.get_member(int(user_id))
            if member is None:
                continue
            try:
                from utils.panels import StatusCard

                await member.send(view=StatusCard(
                    "Du hast gewonnen!",
                    f"**{prize}**\n\nServer: **{guild.name}**\n[Zum Gewinnspiel]({url})",
                    tone="success",
                ))
            except discord.Forbidden:
                pass  # DMs closed — not an error worth failing over
            except Exception:
                pass

    # And tell the host how it went.
    if record.get("dm_host", 1) and record.get("host_id"):
        host = guild.get_member(int(record["host_id"]))
        if host is not None:
            try:
                from utils.panels import StatusCard

                await host.send(view=StatusCard(
                    "Gewinnspiel beendet" if not reroll else "Neu ausgelost",
                    f"**{prize}** auf **{guild.name}**\n\n"
                    + (f"Gewinner: {mentions}" if winner_ids else "Keine Teilnehmer."),
                    tone="info",
                ))
            except Exception:
                pass


@router.post("/{guild_id}/{message_id}/end", summary="End and draw")
async def end_giveaway(
    guild_id: int, message_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    winner_ids = await store.draw(db, message_id, int(record.get("winners") or 1))
    await store.record_winners(db, message_id, winner_ids)
    await store.mark_ended(db, message_id)

    await _announce(bot, record, winner_ids)

    await feature_audit.log_action(
        "giveaway_ended",
        actor=str((data or {}).get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{record.get('prize')}: {len(winner_ids)} Gewinner",
    )
    return {
        "status": "success",
        "winners": [str(w) for w in winner_ids],
        "entrants": await store.entry_count(db, message_id),
        "result": f"Beendet — {len(winner_ids)} Gewinner.",
    }


@router.post("/{guild_id}/{message_id}/reroll", summary="Draw again")
async def reroll_giveaway(
    guild_id: int, message_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Draw new winners, skipping everyone who already won.

    The old reroll needed the command to be a reply to the bot's message
    and re-read the reaction; this works from the dashboard and cannot
    pick the same person twice.
    """
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    payload = data or {}
    try:
        count = max(1, min(int(payload.get("count", record.get("winners") or 1)), 20))
    except (TypeError, ValueError):
        count = int(record.get("winners") or 1)

    winner_ids = await store.draw(db, message_id, count, exclude_past=True)
    if not winner_ids:
        raise HTTPException(status_code=400, detail="Keine Teilnehmer zum Auslosen.")

    await store.record_winners(db, message_id, winner_ids, reroll=True)
    await _announce(bot, record, winner_ids, reroll=True)

    await feature_audit.log_action(
        "giveaway_rerolled",
        actor=str(payload.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{record.get('prize')}: {len(winner_ids)}",
    )
    return {
        "status": "success",
        "winners": [str(w) for w in winner_ids],
        "result": f"Neu ausgelost — {len(winner_ids)} Gewinner.",
    }


@router.delete("/{guild_id}/{message_id}", summary="Cancel a giveaway")
async def cancel_giveaway(
    guild_id: int, message_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    await db.execute(
        "DELETE FROM Giveaway WHERE guild_id = ? AND message_id = ?",
        (guild_id, message_id),
    )
    await db.execute("DELETE FROM giveaway_entries WHERE message_id = ?", (message_id,))
    await db.commit()

    guild = bot.get_guild(guild_id)
    if guild:
        channel = guild.get_channel(int(record["channel_id"]))
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except Exception:
                pass

    await feature_audit.log_action(
        "giveaway_cancelled", actor=actor or "dashboard", guild_id=guild_id,
        detail=str(record.get("prize")),
    )
    return {"status": "success", "result": "Gewinnspiel abgebrochen."}
