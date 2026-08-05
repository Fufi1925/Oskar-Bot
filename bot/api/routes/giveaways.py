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

import asyncio
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

# Every message the giveaway can send. The host may overwrite each one in
# the dashboard; an empty field falls back to the text here.
DEFAULT_MESSAGES = {
    "msg_joined": "Du bist dabei! Teilnehmer: **{entries}**",
    "msg_left": "Du nimmst nicht mehr teil. Teilnehmer: **{entries}**",
    "msg_ended": "Dieses Gewinnspiel ist bereits beendet.",
    "msg_denied": "Du erfüllst die Bedingungen noch nicht:",
    "msg_winner_dm": "**{prize}**\n\nServer: **{server}**",
    "msg_announce": "🎉 Glückwunsch {winners_mentions}! Ihr gewinnt **{prize}**.",
    "msg_no_entries": "Niemand hat am Gewinnspiel für **{prize}** teilgenommen.",
}


def message_text(record: dict, key: str, values: dict) -> str:
    """The host's own wording for `key`, or the built-in default."""
    raw = str(record.get(key) or "").strip() or DEFAULT_MESSAGES[key]
    return store.fill_placeholders(raw, values)


# Fields a host may set when creating, and change afterwards. Kept in one
# place so create and edit cannot drift apart — that is how the ticket tab
# ended up silently dropping half its inputs.
TEXT_FIELDS = {
    "title": 200, "description": 2000, "button_label": 80, "button_emoji": 32,
    "image_url": 400,
    "msg_joined": 500, "msg_left": 500, "msg_ended": 500, "msg_denied": 500,
    "msg_winner_dm": 1000, "msg_announce": 1000, "msg_no_entries": 500,
}
NUMBER_FIELDS = {
    "min_messages": (0, 1_000_000),
    "min_level": (0, 1000),
    "min_account_days": (0, 3650),
    "min_member_days": (0, 3650),
}
ID_FIELDS = ("required_role_id", "blocked_role_id")
FLAG_FIELDS = ("dm_winners", "dm_host", "allow_leave")


def read_fields(data: dict, *, partial: bool) -> dict:
    """
    Pull the editable fields out of a request body.

    With partial=True only the keys actually present are returned, so a
    dashboard tab that shows five of twenty fields cannot wipe the other
    fifteen by omitting them.
    """
    out: dict = {}

    for name, limit in TEXT_FIELDS.items():
        if partial and name not in data:
            continue
        out[name] = str(data.get(name, "") or "")[:limit]

    for name, (low, high) in NUMBER_FIELDS.items():
        if partial and name not in data:
            continue
        try:
            out[name] = max(low, min(int(data.get(name) or 0), high))
        except (TypeError, ValueError):
            out[name] = 0

    for name in ID_FIELDS:
        if partial and name not in data:
            continue
        raw = str(data.get(name) or "")
        out[name] = int(raw) if raw.isdigit() else None

    for name in FLAG_FIELDS:
        if partial and name not in data:
            continue
        out[name] = 1 if data.get(name, True) else 0

    if not partial or "colour" in data:
        colour = data.get("colour")
        try:
            out["colour"] = int(colour) if colour is not None else None
        except (TypeError, ValueError):
            out["colour"] = None

    return out


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


def placeholder_values(record: dict, *, entries: int = 0, **extra) -> dict:
    """The values behind {prize}, {ends}, {entries} … in every text."""
    ends_at = int(record.get("ends_at") or 0)
    values = {
        "prize": record.get("prize") or "",
        "winners": record.get("winners") or 1,
        "ends": f"<t:{ends_at}:R>" if ends_at else "—",
        "ends_full": f"<t:{ends_at}:F>" if ends_at else "—",
        "host": f"<@{record.get('host_id')}>" if record.get("host_id") else "—",
        "entries": entries,
    }
    values.update(extra)
    return values


def build_view(
    record: dict, *, entries: int, ended: bool = False, winners_text="", guild=None
):
    """The giveaway message, as a Components V2 panel."""
    from utils.panels import ACCENT, Panel

    values = placeholder_values(record, entries=entries)

    title = store.fill_placeholders(record.get("title") or DEFAULT_TITLE, values)
    body = store.fill_placeholders(
        record.get("description") or DEFAULT_DESCRIPTION, values
    )

    sections = [body]

    # Say up front what is needed — being told only after pressing the
    # button is the thing people complain about.
    rules = store.requirement_lines(record, guild)
    if rules and not ended:
        sections.append("**Bedingungen:** " + " · ".join(rules))

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
        await message.edit(view=build_view(record, entries=entries, guild=guild))
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
            "blocked_role_id": (
                str(row["blocked_role_id"]) if row.get("blocked_role_id") else None
            ),
            "min_messages": int(row.get("min_messages") or 0),
            "min_level": int(row.get("min_level") or 0),
            "min_account_days": int(row.get("min_account_days") or 0),
            "min_member_days": int(row.get("min_member_days") or 0),
            "allow_leave": bool(row.get("allow_leave", 1)),
            **{key: row.get(key) or "" for key in DEFAULT_MESSAGES},
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


@router.get("/{guild_id}/{message_id}", summary="One giveaway in full")
async def giveaway_detail(
    guild_id: int, message_id: int, bot: "universitybot" = Depends(get_bot)
):
    """
    Everything about a single giveaway: settings, entrants, who was
    favoured and the resulting chance per person.

    The chance is worked out here rather than in the browser because the
    weights must never reach the entrants — only somebody who may open
    the dashboard gets to see this response.
    """
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    guild = bot.get_guild(guild_id)
    tuning = await store.boosts(db, message_id)
    ids = await store.entry_ids(db, message_id)
    won = set(await store.past_winner_ids(db, message_id))

    # Guaranteed people take slots off the top; the rest share what is left.
    slots = int(record.get("winners") or 1)
    sure = [u for u in ids if tuning.get(u, {}).get("guaranteed")]
    open_slots = max(0, slots - len(sure))
    pool = [u for u in ids if u not in sure]
    total_weight = sum(tuning.get(u, {}).get("weight", 1) for u in pool) or 1

    people = []
    for user_id in ids:
        boost = tuning.get(user_id, {})
        member = guild.get_member(user_id) if guild else None
        if boost.get("guaranteed"):
            chance = 100.0
        elif not open_slots:
            chance = 0.0
        else:
            share = boost.get("weight", 1) / total_weight
            chance = min(100.0, share * open_slots * 100)

        people.append({
            "id": str(user_id),
            "name": member.display_name if member else f"Unbekannt ({user_id})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
            "weight": boost.get("weight", 1),
            "guaranteed": bool(boost.get("guaranteed")),
            "note": boost.get("note", ""),
            "won": str(user_id) in {str(w) for w in won},
            "chance": round(chance, 2),
        })

    # Favoured people who never pressed the button — easy to miss otherwise.
    for user_id, boost in tuning.items():
        if user_id in ids:
            continue
        member = guild.get_member(user_id) if guild else None
        people.append({
            "id": str(user_id),
            "name": member.display_name if member else f"Unbekannt ({user_id})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
            "weight": boost.get("weight", 1),
            "guaranteed": bool(boost.get("guaranteed")),
            "note": boost.get("note", ""),
            "won": False,
            "chance": 0.0,
            "not_entered": True,
        })

    now = _time.time()
    ends = float(record.get("ends_at") or 0)
    channel = guild.get_channel(int(record.get("channel_id") or 0)) if guild else None
    host = guild.get_member(int(record.get("host_id") or 0)) if guild else None

    return {
        "message_id": str(message_id),
        "guild_id": str(guild_id),
        "prize": record.get("prize"),
        "winners": record.get("winners"),
        "ends_at": ends,
        "start_time": float(record.get("start_time") or 0),
        "running": not (record.get("ended") or ends <= now),
        "channel": channel.name if channel else None,
        "channel_id": str(record.get("channel_id") or ""),
        "host_id": str(record.get("host_id") or ""),
        "host_name": host.display_name if host else None,
        "title": record.get("title") or "",
        "description": record.get("description") or "",
        "colour": record.get("colour"),
        "button_label": record.get("button_label") or "",
        "button_emoji": record.get("button_emoji") or "",
        "image_url": record.get("image_url") or "",
        "required_role_id": (
            str(record["required_role_id"]) if record.get("required_role_id") else None
        ),
        "blocked_role_id": (
            str(record["blocked_role_id"]) if record.get("blocked_role_id") else None
        ),
        "min_messages": int(record.get("min_messages") or 0),
        "min_level": int(record.get("min_level") or 0),
        "min_account_days": int(record.get("min_account_days") or 0),
        "min_member_days": int(record.get("min_member_days") or 0),
        "allow_leave": bool(record.get("allow_leave", 1)),
        "dm_winners": bool(record.get("dm_winners", 1)),
        "dm_host": bool(record.get("dm_host", 1)),
        **{key: record.get(key) or "" for key in DEFAULT_MESSAGES},
        "defaults": DEFAULT_MESSAGES,
        "entries": people,
        "entry_count": len(ids),
        "winner_ids": [str(w) for w in won],
        "requirements": store.requirement_lines(record, guild),
        "url": (
            f"https://discord.com/channels/{guild_id}"
            f"/{record.get('channel_id')}/{message_id}"
            if record.get("channel_id") else None
        ),
    }


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
        **read_fields(data, partial=False),
    }

    # Post first, then store — the custom_id needs the message id, so the
    # message is sent once and edited straight after.
    try:
        message = await channel.send(view=build_view(record, entries=0, guild=guild))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Der Bot darf in #{channel.name} nicht schreiben."
        )

    record["message_id"] = message.id

    columns = [
        "guild_id", "host_id", "start_time", "ends_at", "prize", "winners",
        "message_id", "channel_id", "ended",
    ] + list(read_fields(data, partial=False))
    values = [
        guild_id, record["host_id"], record["start_time"], ends_at, prize,
        winners, message.id, channel.id, 0,
    ] + [record[name] for name in read_fields(data, partial=False)]

    await db.execute(
        f"INSERT OR REPLACE INTO Giveaway ({', '.join(columns)})"
        f" VALUES ({', '.join('?' * len(columns))})",
        values,
    )
    await db.commit()

    # Re-render so the button carries the real message id.
    try:
        view = build_view(record, entries=0, guild=guild)
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
#  Edit while it runs
# ══════════════════════════════════════════════════════════════════════


@router.patch("/{guild_id}/{message_id}", summary="Change a running giveaway")
async def update_giveaway(
    guild_id: int, message_id: int, data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Change texts, requirements, the number of winners or the end time
    while the giveaway is live, and redraw the message.

    Only the keys that were actually sent are written — a tab that shows
    one section must not blank out the rest.
    """
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    updates = read_fields(data, partial=True)

    if "prize" in data:
        prize = str(data["prize"] or "").strip()[:200]
        if not prize:
            raise HTTPException(status_code=400, detail="Der Preis darf nicht leer sein.")
        updates["prize"] = prize

    if "winners" in data:
        try:
            updates["winners"] = max(1, min(int(data["winners"]), 20))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Gewinnerzahl muss eine Zahl sein.")

    # Extending: "+30 minutes" is what a host actually wants, rather than
    # working out an absolute timestamp.
    if "extend_minutes" in data:
        try:
            extra = int(data["extend_minutes"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Verlängerung muss eine Zahl sein.")
        base = max(float(record.get("ends_at") or 0), _time.time())
        new_end = base + extra * 60
        if new_end <= _time.time():
            raise HTTPException(
                status_code=400,
                detail="So weit kann nicht gekürzt werden — das Ende läge in der Vergangenheit.",
            )
        updates["ends_at"] = new_end
        # Reopen a giveaway that had already run out.
        updates["ended"] = 0

    elif "duration_minutes" in data:
        try:
            minutes = max(1, min(int(data["duration_minutes"]), 60 * 24 * 60))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Laufzeit muss eine Zahl sein.")
        updates["ends_at"] = _time.time() + minutes * 60
        updates["ended"] = 0

    if not updates:
        return {"status": "success", "result": "Nichts zu ändern."}

    assignments = ", ".join(f"{name} = ?" for name in updates)
    await db.execute(
        f"UPDATE Giveaway SET {assignments} WHERE guild_id = ? AND message_id = ?",
        list(updates.values()) + [guild_id, message_id],
    )
    await db.commit()

    fresh = await store.get(db, guild_id, message_id)
    await _refresh_message(bot, fresh, db)

    await feature_audit.log_action(
        "giveaway_edited", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{record.get('prize')}: {', '.join(sorted(updates))}",
    )

    changed = "Verlängert." if "ends_at" in updates else "Gespeichert."
    return {"status": "success", "result": changed, "changed": sorted(updates)}


# ══════════════════════════════════════════════════════════════════════
#  Per-user odds — never visible to entrants
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/{message_id}/boost", summary="Favour one entrant")
async def boost_entrant(
    guild_id: int, message_id: int, data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Hand one user extra tickets, or a guaranteed win.

    Kept out of the giveaway message entirely: the channel only ever
    shows the plain entrant count, so there is nothing for the others to
    read off. Only a dashboard user with settings rights can call this.
    """
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    user_id = str(data.get("user_id") or "")
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte ein Mitglied auswählen.")

    mode = str(data.get("mode") or "weight")
    if mode == "clear":
        removed = await store.clear_boost(db, message_id, int(user_id))
        return {
            "status": "success",
            "result": "Zurückgesetzt." if removed else "War nichts gesetzt.",
        }

    guaranteed = mode == "guaranteed"
    try:
        weight = max(1, min(int(data.get("weight", 1) or 1), 1_000_000))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Lose müssen eine Zahl sein.")

    if not guaranteed and weight <= 1:
        raise HTTPException(
            status_code=400,
            detail="Bei einem Los ändert sich nichts — mehr Lose eintragen oder „garantiert“ wählen.",
        )

    await store.set_boost(
        db, message_id, int(user_id),
        weight=weight, guaranteed=guaranteed,
        note=str(data.get("note") or ""),
        set_by=int(str(data.get("actor", "0")) or 0)
        if str(data.get("actor", "0")).isdigit() else 0,
    )

    # Logged so it is at least traceable for whoever owns the server,
    # even though the entrants never see it.
    await feature_audit.log_action(
        "giveaway_boost", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=(
            f"{record.get('prize')}: {user_id} "
            + ("garantiert" if guaranteed else f"{weight} Lose")
        ),
    )

    return {
        "status": "success",
        "result": (
            "Gewinnt garantiert." if guaranteed
            else f"Hat jetzt {weight} Lose."
        ),
    }


# ══════════════════════════════════════════════════════════════════════
#  Draw / reroll / cancel
# ══════════════════════════════════════════════════════════════════════


# Pause zwischen zwei DMs.
#
# Discord drosselt Direktnachrichten scharf; fuenfzehn Gewinner am
# Stueck laufen ins Rate-Limit, und discord.py wartet die Strafe dann
# blockierend ab -- der Bot wirkt in dieser Zeit eingefroren. Eine
# Dreiviertelsekunde Abstand bleibt darunter und kostet bei fuenfzehn
# Gewinnern gut zehn Sekunden, die niemandem auffallen.
DM_DELAY = 0.75


async def _send_dm(db, member, message_id: int, view, *, host: bool = False) -> bool:
    """Eine DM -- aber nur, wenn dieser Nutzer noch keine bekommen hat.

    Die Sperre liegt in der Datenbank, nicht im Ablauf: sie haelt auch
    dann, wenn derselbe Abschluss aus zwei Richtungen kommt.
    """

    claim = store.claim_host_dm if host else store.claim_dm
    if not await claim(db, message_id, int(member.id)):
        return False

    try:
        await member.send(view=view)
        return True
    except discord.Forbidden:
        # DMs zu. Kein Fehler, der irgendwo auffallen muesste -- der
        # Eintrag bleibt trotzdem stehen, sonst wird es bei jedem
        # weiteren Versuch erneut probiert.
        return False
    except Exception:
        return False


async def _announce(bot, record: dict, winner_ids: list[int], *, reroll=False, db=None):
    """Edit the message, reply with the result and send the DMs.

    ``db`` wird durchgereicht, damit die DM-Sperre dieselbe Verbindung
    benutzt wie der Aufrufer. Ohne Angabe wird die uebliche geholt.
    """
    if db is None:
        db = await _db()

    guild = bot.get_guild(int(record["guild_id"]))
    if guild is None:
        return
    channel = guild.get_channel(int(record["channel_id"]))
    if channel is None:
        return

    mentions = ", ".join(f"<@{w}>" for w in winner_ids)
    prize = record.get("prize")
    values = placeholder_values(
        record,
        winners_mentions=mentions,
        winner_count=len(winner_ids),
        server=guild.name,
    )

    try:
        message = await channel.fetch_message(int(record["message_id"]))
    except Exception:
        message = None

    if message is not None and not reroll:
        try:
            await message.edit(
                view=build_view(
                    record, entries=0, ended=True, winners_text=mentions, guild=guild
                )
            )
        except Exception:
            pass

    if winner_ids:
        text = (
            f"🎉 Neu ausgelost: {mentions} gewinnt **{prize}**!"
            if reroll
            else message_text(record, "msg_announce", values)
        )
    else:
        text = message_text(record, "msg_no_entries", values)

    try:
        if message is not None:
            await channel.send(text, reference=message)
        else:
            await channel.send(text)
    except Exception:
        pass

    # DM the winners — this is the part people actually notice.
    #
    # Und genau hier lag der Spam. Jede DM geht jetzt durch `_send_dm`,
    # das in `giveaway_dms` einen Anspruch eintraegt: pro Nutzer und
    # Gewinnspiel genau eine. Selbst wenn dieser Abschluss ein zweites
    # Mal durchlaeuft, kommt keine zweite Nachricht an.
    #
    # Ein Reroll ist ausdruecklich ein neuer Anlass -- wer neu gezogen
    # wurde, hat vorher keine bekommen und ist deshalb noch nicht
    # eingetragen.
    message_id = int(record["message_id"])

    if record.get("dm_winners", 1) and winner_ids:
        from utils.panels import StatusCard

        url = (
            f"https://discord.com/channels/{record['guild_id']}"
            f"/{record['channel_id']}/{record['message_id']}"
        )
        for index, user_id in enumerate(winner_ids):
            member = guild.get_member(int(user_id))
            if member is None:
                continue

            body = message_text(
                record, "msg_winner_dm",
                {
                    **values,
                    "user": getattr(member, "mention", f"<@{user_id}>"),
                    "user_name": getattr(member, "display_name", ""),
                },
            )
            sent = await _send_dm(
                db, member, message_id,
                StatusCard(
                    "Du hast gewonnen!",
                    f"{body}\n\n[Zum Gewinnspiel]({url})",
                    tone="success",
                ),
            )

            # Nur zwischen tatsaechlich verschickten Nachrichten warten,
            # und nicht hinter der letzten: sonst kostet ein Abschluss
            # ohne eine einzige DM trotzdem Sekunden.
            if sent and index < len(winner_ids) - 1:
                await asyncio.sleep(DM_DELAY)

    # And tell the host how it went.
    if record.get("dm_host", 1) and record.get("host_id"):
        host = guild.get_member(int(record["host_id"]))
        if host is not None:
            from utils.panels import StatusCard

            await _send_dm(
                db, host, message_id,
                StatusCard(
                    "Gewinnspiel beendet" if not reroll else "Neu ausgelost",
                    f"**{prize}** auf **{guild.name}**\n\n"
                    + (f"Gewinner: {mentions}" if winner_ids else "Keine Teilnehmer."),
                    tone="info",
                ),
                host=True,
            )


@router.post("/{guild_id}/{message_id}/end", summary="End and draw")
async def end_giveaway(
    guild_id: int, message_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    record = await store.get(db, guild_id, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Gewinnspiel nicht gefunden.")

    # Erst den Riegel umlegen, dann auslosen.
    #
    # `mark_ended` meldet False, wenn das Gewinnspiel schon beendet war
    # -- dann hat es ein anderer Weg bereits abgeschlossen (der Timer,
    # oder ein zweiter Klick), und alles Weitere waere eine zweite
    # Ankuendigung mit einer zweiten Runde DMs.
    #
    # Die Reihenfolge ist Absicht: wird zuerst ausgelost und danach
    # gesperrt, koennen zwei gleichzeitige Aufrufe beide ziehen.
    if not await store.mark_ended(db, message_id):
        winners = await store.past_winner_ids(db, message_id)
        return {
            "status": "success",
            "winners": [str(w) for w in winners],
            "entrants": await store.entry_count(db, message_id),
            "result": "War schon beendet.",
        }

    winner_ids = await store.draw(db, message_id, int(record.get("winners") or 1))
    await store.record_winners(db, message_id, winner_ids)

    await _announce(bot, record, winner_ids, db=db)

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
    await _announce(bot, record, winner_ids, reroll=True, db=db)

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
