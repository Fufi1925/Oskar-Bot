# ╔══════════════════════════════════════════════════════════════════╗
# ║   Vanity roles API                                               ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The dashboard side of status-based vanity roles.

The two routes this replaces lived in guilds.py, stored the trigger
exactly as typed (so `.gg/MeinServer` and `discord.gg/meinserver` were two separate
setups that both looked correct), had no way to switch a setup off, to
see who currently holds a role, or to run a sync — and there was no
delete route at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import vanity_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")
    return guild


async def _refresh(bot, guild_id: int) -> None:
    """
    Tell the cog to reload.

    Without this the bot keeps matching against the old setups until it
    restarts, and the dashboard looks like it saved nothing.
    """
    cog = bot.get_cog("VanityRoles")
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


def _role_problem(guild, role) -> str | None:
    """Why this role cannot be handed out, in plain German."""
    if role is None:
        return "Die Rolle gibt es nicht mehr."
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        return "Dem Bot fehlt das Recht „Rollen verwalten“."
    if role.managed:
        return f"@{role.name} wird von einer Integration verwaltet und kann nicht vergeben werden."
    if role >= me.top_role:
        return (
            f"@{role.name} steht über der Rolle des Bots — er könnte sie niemandem "
            "geben. Schieb die Bot-Rolle darüber."
        )
    return None


@router.get("/{guild_id}", summary="Vanity setups with live numbers")
async def get_vanity(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    guild = bot.get_guild(guild_id)

    setups = await store.list_setups(db, guild_id)
    counts = await store.holder_counts(db, guild_id)

    entries = []
    for setup in setups:
        role = guild.get_role(setup["role_id"]) if guild else None
        channel = (
            guild.get_channel(setup["log_channel_id"])
            if guild and setup["log_channel_id"] else None
        )
        entries.append({
            "vanity": setup["vanity"],
            "display": f".gg/{setup['vanity']}",
            # IDs stay strings; Number() rounds off a snowflake's last digits.
            "role_id": str(setup["role_id"]),
            "role_name": role.name if role else None,
            "role_colour": role.color.value if role else None,
            "log_channel_id": (
                str(setup["log_channel_id"]) if setup["log_channel_id"] else None
            ),
            "log_channel_name": channel.name if channel else None,
            "enabled": setup["enabled"],
            "holders": counts.get(setup["vanity"], 0),
            "granted_total": setup["granted_total"],
            "removed_total": setup["removed_total"],
            "problem": _role_problem(guild, role) if guild else None,
        })

    return {
        "guild_id": str(guild_id),
        "setups": entries,
        "stats": store.stats(setups, counts),
        # The dashboard warns when this is off, because nothing can work
        # without it and the failure is completely silent otherwise.
        "presence_intent": bool(getattr(bot, "intents", None) and bot.intents.presences),
    }


@router.get("/{guild_id}/{vanity}/holders", summary="Who has the role right now")
async def get_holders(
    guild_id: int, vanity: str, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = bot.get_guild(guild_id)

    people = []
    for entry in await store.holders(db, guild_id, vanity):
        member = guild.get_member(entry["user_id"]) if guild else None
        people.append({
            "user_id": str(entry["user_id"]),
            "name": member.display_name if member else f"Unbekannt ({entry['user_id']})",
            "avatar": member.display_avatar.url if member else None,
            "left": member is None,
            "since": entry["since"],
        })

    return {"holders": people, "count": len(people)}


@router.post("/{guild_id}", summary="Add or update a setup")
async def save_vanity(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    trigger = store.normalise_trigger(data.get("vanity", ""))
    if not trigger:
        raise HTTPException(
            status_code=400,
            detail="Bitte einen Auslöser angeben, z. B. `.gg/dein-server`.",
        )

    role_id = str(data.get("role_id") or "")
    if not role_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine Rolle auswählen.")

    role = guild.get_role(int(role_id))
    problem = _role_problem(guild, role)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    log_channel_id = str(data.get("log_channel_id") or "")
    if log_channel_id and not log_channel_id.isdigit():
        log_channel_id = ""

    await store.save_setup(
        db, guild_id, trigger, int(role_id),
        log_channel_id=int(log_channel_id) if log_channel_id else None,
        enabled=bool(data.get("enabled", True)),
    )
    await _refresh(bot, guild_id)

    await feature_audit.log_action(
        "vanity_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f".gg/{trigger} → @{role.name}",
    )
    return {
        "status": "success",
        "result": f"Wer `.gg/{trigger}` im Status hat, bekommt @{role.name}.",
        "vanity": trigger,
    }


@router.delete("/{guild_id}/{vanity}", summary="Remove a setup")
async def delete_vanity(
    guild_id: int, vanity: str, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.delete_setup(db, guild_id, vanity):
        raise HTTPException(status_code=404, detail="Diesen Auslöser gibt es nicht.")

    await _refresh(bot, guild_id)
    await feature_audit.log_action(
        "vanity_removed", actor=actor or "dashboard",
        guild_id=guild_id, detail=vanity,
    )
    return {
        "status": "success",
        "result": "Entfernt. Bereits vergebene Rollen bleiben bestehen.",
    }


@router.post("/{guild_id}/{vanity}/sync", summary="Check every member now")
async def sync_vanity(
    guild_id: int, vanity: str, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Walk the member list once and correct every role.

    Presence events only fire on a *change*, so somebody who already had
    the trigger in their status when the setup was created would keep
    waiting until they next edited it.
    """
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    trigger = store.normalise_trigger(vanity)
    setups = {s["vanity"]: s for s in await store.list_setups(db, guild_id)}
    setup = setups.get(trigger)
    if setup is None:
        raise HTTPException(status_code=404, detail="Diesen Auslöser gibt es nicht.")

    role = guild.get_role(setup["role_id"])
    problem = _role_problem(guild, role)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    granted = removed = 0
    for member in guild.members:
        if member.bot:
            continue

        wanted = store.matches(trigger, store.status_text(member))
        held = await store.is_holder(db, guild_id, trigger, member.id)

        if wanted and not held:
            try:
                await member.add_roles(role, reason="Vanity-Abgleich")
            except Exception:
                continue
            await store.add_holder(db, guild_id, trigger, member.id)
            granted += 1
        elif not wanted and held:
            # Only take back what the bot handed out itself.
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Vanity-Abgleich")
                except Exception:
                    pass
            await store.remove_holder(db, guild_id, trigger, member.id)
            removed += 1

    if granted or removed:
        await store.bump(db, guild_id, trigger, granted=granted, removed=removed)

    await feature_audit.log_action(
        "vanity_sync", actor=str((data or {}).get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{trigger}: +{granted} / -{removed}",
    )
    return {
        "status": "success",
        "result": f"{granted} vergeben, {removed} entfernt.",
        "granted": granted,
        "removed": removed,
    }


@router.post("/{guild_id}/{vanity}/test", summary="Would this status match?")
async def test_vanity(guild_id: int, vanity: str, data: dict):
    """
    Try a status against the trigger without touching anybody.

    Saves the round trip of editing a real Discord status just to find
    out whether the wording counts.
    """
    trigger = store.normalise_trigger(vanity)
    text = str(data.get("status", ""))
    return {
        "trigger": trigger,
        "status": text,
        "matches": store.matches(trigger, text.lower()),
    }
