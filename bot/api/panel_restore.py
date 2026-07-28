# ╔══════════════════════════════════════════════════════════════════╗
# ║   Re-post panels after a restore                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Repost the interactive panels a restored backup refers to.

The configuration for verification and ticket panels survives a backup
just fine, but the panel *message* does not: it lives in a Discord channel
and is referenced by a message id. After a redeploy on an ephemeral host
the bot comes back with the same settings but the stored id either points
at a message nobody can use any more, or the channel was wiped along with
it. Either way the buttons are dead and somebody has to run the setup
command again by hand.

This walks the restored configuration, deletes the old panel message when
it still exists, posts a fresh one, and writes the new message id back.

Everything is best effort: a guild the bot is no longer in, a deleted
channel or a missing permission is reported and skipped rather than
aborting the whole restore.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any

import aiosqlite

TICKET_DB = "db/ticket.db"
VERIFICATION_DB = "db/verification.db"
REACTION_ROLE_DB = "rr.db"


async def _delete_old_message(guild, channel_id, message_id) -> bool:
    """Remove a stale panel so the channel does not collect dead copies."""
    if not channel_id or not message_id:
        return False
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return False
    try:
        message = await channel.fetch_message(int(message_id))
        await message.delete()
        return True
    except Exception:
        # Already gone, or we may not delete it. Not worth failing over.
        return False


async def _repost_verification(bot, guild) -> dict[str, Any] | None:
    if not os.path.exists(VERIFICATION_DB):
        return None

    async with aiosqlite.connect(VERIFICATION_DB) as db:
        try:
            async with db.execute(f"PRAGMA table_info([verification_config])") as cur:
                columns = {r[1] for r in await cur.fetchall()}
            has_panel_id = "panel_message_id" in columns

            select = (
                "SELECT verification_channel_id, verified_role_id,"
                " verification_method, enabled"
                + (", panel_message_id" if has_panel_id else "")
                + " FROM verification_config WHERE guild_id = ?"
            )
            async with db.execute(select, (guild.id,)) as cursor:
                row = await cursor.fetchone()
        except Exception:
            return None

    if not row or not row[3]:
        return None

    # The method is no longer read here -- build_panel picks the buttons
    # from the stored settings.
    channel_id, role_id = row[0], row[1]
    old_message_id = row[4] if has_panel_id and len(row) > 4 else None
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    role = guild.get_role(int(role_id)) if role_id else None

    if channel is None:
        return {"module": "verification", "status": "skipped",
                "reason": "verification channel is gone"}
    if role is None:
        return {"module": "verification", "status": "skipped",
                "reason": "verified role is gone"}

    # Rendered by the cog, not here. This used to build its own panel
    # with the English strings hard-coded, so restoring after a backup
    # silently replaced whatever texts the server had configured.
    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        return {"module": "verification", "status": "failed",
                "reason": "verification module unavailable"}

    try:
        from utils import verify_store

        async with aiosqlite.connect(verify_store.DB_PATH) as db:
            settings = await verify_store.get_settings(db, guild.id)
        panel = cog.build_panel(guild, settings, role)
    except Exception as exc:  # noqa: BLE001
        return {"module": "verification", "status": "failed",
                "reason": f"could not build the panel: {exc}"}

    # Remove the stale panel first, so the channel does not end up with a
    # dead copy sitting above the working one.
    await _delete_old_message(guild, channel_id, old_message_id)

    try:
        message = await channel.send(view=panel)
    except Exception as exc:  # noqa: BLE001
        return {"module": "verification", "status": "failed",
                "reason": f"cannot post in #{channel.name}: {exc}"}

    try:
        bot.add_view(panel, message_id=message.id)
    except Exception:
        pass

    if has_panel_id:
        try:
            async with aiosqlite.connect(VERIFICATION_DB) as db:
                await db.execute(
                    "UPDATE verification_config SET panel_message_id = ?"
                    " WHERE guild_id = ?",
                    (message.id, guild.id),
                )
                await db.commit()
        except Exception:
            pass

    return {
        "module": "verification",
        "status": "posted",
        "channel": channel.name,
        "url": message.jump_url,
    }


async def _repost_tickets(bot, guild) -> dict[str, Any] | None:
    if not os.path.exists(TICKET_DB):
        return None

    async with aiosqlite.connect(TICKET_DB) as db:
        try:
            async with db.execute(
                "SELECT panel_channel_id, panel_message_id, embed_title,"
                " embed_description, embed_color"
                " FROM guild_configs WHERE guild_id = ?",
                (guild.id,),
            ) as cursor:
                row = await cursor.fetchone()
        except Exception:
            return None

    if not row or not row[0]:
        return None

    channel = guild.get_channel(int(row[0]))
    if channel is None:
        return {"module": "tickets", "status": "skipped",
                "reason": "panel channel is gone"}

    cog = bot.get_cog("TicketCog")
    builder = getattr(cog, "create_panel_view", None) if cog else None
    if not callable(builder):
        return {"module": "tickets", "status": "skipped",
                "reason": "ticket module not loaded"}

    try:
        view = builder(guild.id)
    except Exception as exc:  # noqa: BLE001
        return {"module": "tickets", "status": "failed",
                "reason": f"cannot build panel: {exc}"}

    if view is None:
        return {"module": "tickets", "status": "skipped",
                "reason": "no ticket categories configured"}

    await _delete_old_message(guild, row[0], row[1])

    try:
        from utils.panels import ACCENT, Panel

        panel = Panel(
            row[2] or "Support",
            row[3] or "Open a ticket and the team will help you.",
            accent=int(row[4]) if row[4] else ACCENT["brand"],
            buttons=list(view.children),
        )
        message = await channel.send(view=panel)
    except Exception as exc:  # noqa: BLE001
        return {"module": "tickets", "status": "failed",
                "reason": f"cannot post in #{channel.name}: {exc}"}

    async with aiosqlite.connect(TICKET_DB) as db:
        await db.execute(
            "UPDATE guild_configs SET panel_message_id = ? WHERE guild_id = ?",
            (message.id, guild.id),
        )
        await db.commit()

    return {
        "module": "tickets",
        "status": "posted",
        "channel": channel.name,
        "url": message.jump_url,
    }


async def _verify_reaction_roles(bot, guild) -> dict[str, Any] | None:
    """
    Drop reaction role rows whose message no longer exists.

    A reaction role is only half configuration: the mapping lives in the
    database, but it is keyed by the message people react to. After a
    restore that message is often gone — the row survives and silently does
    nothing, which looks exactly like "roles were not restored properly".

    Removing the dead rows makes the dashboard show the real state instead
    of mappings that can never fire again. Rows whose message we simply
    cannot check right now (missing permission, API hiccup) are kept.
    """
    if not os.path.exists(REACTION_ROLE_DB):
        return None

    def _read():
        con = sqlite3.connect(REACTION_ROLE_DB)
        try:
            rows = con.execute(
                "SELECT DISTINCT message_id FROM reaction_roles WHERE guild_id = ?",
                (guild.id,),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        con.close()
        return [r[0] for r in rows]

    message_ids = await asyncio.to_thread(_read)
    if not message_ids:
        return None

    stale: list[int] = []
    for message_id in message_ids:
        found = False
        for channel in getattr(guild, "text_channels", []):
            try:
                await channel.fetch_message(int(message_id))
                found = True
                break
            except Exception:
                continue
        if not found:
            stale.append(message_id)

    if not stale:
        return {
            "module": "reaction_roles",
            "status": "ok",
            "checked": len(message_ids),
        }

    def _delete():
        con = sqlite3.connect(REACTION_ROLE_DB)
        marks = ",".join("?" for _ in stale)
        con.execute(
            f"DELETE FROM reaction_roles WHERE guild_id = ? AND message_id IN ({marks})",
            (guild.id, *stale),
        )
        con.commit()
        con.close()

    await asyncio.to_thread(_delete)

    return {
        "module": "reaction_roles",
        "status": "cleaned",
        "checked": len(message_ids),
        "removed": len(stale),
        "reason": (
            f"{len(stale)} reaction role message(s) no longer exist; "
            "post the message again and re-add the reactions"
        ),
    }


async def repost_all_panels(bot, guild_ids=None) -> dict[str, Any]:
    """
    Repost every panel the current configuration describes.

    guild_ids limits the work to specific servers; by default every guild
    the bot shares with the restored configuration is processed.
    """
    results: list[dict[str, Any]] = []

    if guild_ids:
        wanted = {int(g) for g in guild_ids}
        guilds = [g for g in bot.guilds if g.id in wanted]
    else:
        guilds = list(bot.guilds)

    for guild in guilds:
        for handler in (_repost_verification, _repost_tickets,
                        _verify_reaction_roles):
            try:
                outcome = await handler(bot, guild)
            except Exception as exc:  # noqa: BLE001
                outcome = {
                    "module": handler.__name__.replace("_repost_", ""),
                    "status": "failed",
                    "reason": str(exc)[:200],
                }
            if outcome:
                outcome["guild_id"] = str(guild.id)
                outcome["guild"] = guild.name
                results.append(outcome)

    return {
        "panels_posted": sum(1 for r in results if r["status"] == "posted"),
        "panels_skipped": sum(1 for r in results if r["status"] == "skipped"),
        "panels_failed": sum(1 for r in results if r["status"] == "failed"),
        "reaction_roles_removed": sum(
            r.get("removed", 0) for r in results if r["module"] == "reaction_roles"
        ),
        "details": results,
    }
