# ╔══════════════════════════════════════════════════════════════════╗
# ║   Leveling API                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Everything the dashboard needs for the leveling system.

There were two routes before — GET and PATCH on `/guilds/{id}/leveling` —
and they exposed five of the twelve settings. Reward roles, multipliers,
exclusions, the level-up text and the whole member list could only be
managed with chat commands.

They also read the settings row by tuple index, so the values shifted as
soon as a column was added, and the PATCH wrote each field with its own
UPDATE statement without checking that the row existed first.

All of this shares `utils/leveling_store.py` with the cog, so the
dashboard and the chat commands cannot drift apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import leveling_store as store

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


def _forget(bot, guild_id: int) -> None:
    """
    Drop the cog's settings cache after a write.

    Without this the bot keeps handing out XP using the old numbers until
    it restarts, and the dashboard looks like it saved nothing.
    """
    cog = bot.get_cog("Leveling")
    if cog is not None and hasattr(cog, "forget"):
        cog.forget(guild_id)


def _member_name(guild, user_id: int) -> str:
    member = guild.get_member(user_id) if guild else None
    return member.display_name if member else f"Unbekannt ({user_id})"


def _avatar(guild, user_id: int):
    member = guild.get_member(user_id) if guild else None
    return member.display_avatar.url if member else None


# ══════════════════════════════════════════════════════════════════════
#  Settings
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}", summary="Leveling settings and stats")
async def get_leveling(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await _db()
    guild = bot.get_guild(guild_id)

    settings = await store.get_settings(db, guild_id)
    stats = await store.guild_stats(db, guild_id)

    rewards = []
    for entry in await store.rewards(db, guild_id):
        role = guild.get_role(entry["role_id"]) if guild else None
        rewards.append({
            "level": entry["level"],
            # IDs stay strings: Number("1327995167345819721") rounds off
            # the last digits and silently points at nothing.
            "role_id": str(entry["role_id"]),
            "role_name": role.name if role else None,
            "role_colour": role.color.value if role else None,
            "missing": role is None,
        })

    multipliers = []
    for entry in await store.multipliers(db, guild_id):
        target = (
            guild.get_role(entry["target_id"])
            if entry["target_type"] == "role" and guild
            else guild.get_channel(entry["target_id"]) if guild else None
        )
        multipliers.append({
            "target_id": str(entry["target_id"]),
            "target_type": entry["target_type"],
            "multiplier": entry["multiplier"],
            "name": getattr(target, "name", None),
            "missing": target is None,
        })

    excluded = []
    for entry in await store.excluded(db, guild_id):
        target = (
            guild.get_role(entry["target_id"])
            if entry["target_type"] == "role" and guild
            else guild.get_channel(entry["target_id"]) if guild else None
        )
        excluded.append({
            "target_id": str(entry["target_id"]),
            "target_type": entry["target_type"],
            "name": getattr(target, "name", None),
            "missing": target is None,
        })

    return {
        "guild_id": str(guild_id),
        **{k: v for k, v in settings.items() if k not in ("channel_id", "embed_color")},
        "channel_id": str(settings["channel_id"]) if settings["channel_id"] else None,
        "embed_color": settings["embed_color"],
        "embed_color_hex": f"#{settings['embed_color']:06x}",
        "enabled": bool(settings["enabled"]),
        "thumbnail_enabled": bool(settings["thumbnail_enabled"]),
        "delete_command_message": bool(settings["delete_command_message"]),
        "stack_roles": bool(settings["stack_roles"]),
        "rewards": rewards,
        "multipliers": multipliers,
        "excluded": excluded,
        "stats": stats,
        "placeholders": store.PLACEHOLDERS,
    }


@router.patch("/{guild_id}", summary="Change leveling settings")
async def patch_leveling(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Only the keys actually sent are written."""
    db = await _db()

    updates = {}
    for key in store.DEFAULTS:
        if key not in data:
            continue
        value = data[key]
        if key in store.BOOLEAN_KEYS:
            updates[key] = 1 if value else 0
        elif key == "channel_id":
            updates[key] = int(value) if str(value or "").isdigit() else None
        else:
            updates[key] = value

    # The colour may arrive as "#5865f2" from a colour input.
    if "embed_color_hex" in data and "embed_color" not in updates:
        try:
            updates["embed_color"] = int(str(data["embed_color_hex"]).lstrip("#"), 16)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Ungültige Farbe.")

    if not updates:
        return {"status": "success", "result": "Nichts zu ändern."}

    merged = await store.save_settings(db, guild_id, updates)
    _forget(bot, guild_id)

    await feature_audit.log_action(
        "leveling_settings", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=", ".join(sorted(updates)),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "settings": {**merged, "embed_color_hex": f"#{merged['embed_color']:06x}"},
    }


# ══════════════════════════════════════════════════════════════════════
#  Members
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/leaderboard", summary="Ranked members")
async def get_leaderboard(
    guild_id: int, page: int = 1, per_page: int = 25,
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    guild = bot.get_guild(guild_id)

    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    entries = await store.leaderboard(
        db, guild_id, limit=per_page, offset=(page - 1) * per_page
    )
    stats = await store.guild_stats(db, guild_id)

    return {
        "page": page,
        "per_page": per_page,
        "total": stats["members"],
        "entries": [
            {
                "rank": entry["rank"],
                "user_id": str(entry["user_id"]),
                "name": _member_name(guild, entry["user_id"]),
                "avatar": _avatar(guild, entry["user_id"]),
                "left": guild.get_member(entry["user_id"]) is None if guild else True,
                "xp": entry["xp"],
                "level": entry["level"],
                "messages": entry["messages"],
                "next_level_xp": store.xp_for_level(entry["level"] + 1),
            }
            for entry in entries
        ],
    }


@router.post("/{guild_id}/members/{user_id}", summary="Set a member's XP or level")
async def set_member(
    guild_id: int, user_id: int, data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Give, take or set XP for one member.

    The equivalent chat commands used to write to a different table than
    everything else read, so they appeared to work and did nothing.
    """
    db = await _db()

    if "level" in data:
        try:
            level = max(0, min(int(data["level"]), 10_000))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Level muss eine Zahl sein.")
        result = await store.set_xp(db, guild_id, user_id, store.xp_for_level(level))
        detail = f"Level {level}"

    elif "xp" in data:
        try:
            xp = max(0, int(data["xp"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="XP muss eine Zahl sein.")
        result = await store.set_xp(db, guild_id, user_id, xp)
        detail = f"{xp} XP"

    elif "add_xp" in data:
        try:
            amount = int(data["add_xp"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="XP muss eine Zahl sein.")
        await store.add_xp(db, guild_id, user_id, amount)
        result = await store.get_user(db, guild_id, user_id)
        detail = f"{amount:+d} XP"

    else:
        raise HTTPException(
            status_code=400, detail="Bitte xp, add_xp oder level angeben."
        )

    await feature_audit.log_action(
        "leveling_member", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{user_id}: {detail}",
    )
    return {
        "status": "success",
        "result": f"Jetzt Level {result['level']} mit {result['xp']:,} XP.".replace(",", "."),
        "member": {**result, "user_id": str(result["user_id"])},
    }


@router.delete("/{guild_id}/members/{user_id}", summary="Reset one member")
async def reset_member(
    guild_id: int, user_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    await store.reset_user(db, guild_id, user_id)
    await feature_audit.log_action(
        "leveling_reset_member", actor=actor or "dashboard",
        guild_id=guild_id, detail=str(user_id),
    )
    return {"status": "success", "result": "Zurückgesetzt."}


@router.delete("/{guild_id}/members", summary="Reset everyone")
async def reset_all(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    removed = await store.reset_guild(db, guild_id)
    await feature_audit.log_action(
        "leveling_reset_all", actor=actor or "dashboard",
        guild_id=guild_id, detail=f"{removed} Mitglieder",
    )
    return {"status": "success", "result": f"{removed} Mitglieder zurückgesetzt."}


# ══════════════════════════════════════════════════════════════════════
#  The XP table
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/curve", summary="How much XP each level costs")
async def get_curve(
    guild_id: int, up_to: int = 50, bot: "universitybot" = Depends(get_bot)
):
    """
    What every level costs, worked out from the same curve the bot uses.

    Server owners kept asking how long level 10 takes; the answer depends
    on the guild's XP-per-message and cooldown, so it is worked out here
    from the live settings rather than printed as a fixed table.
    """
    db = await _db()
    guild = bot.get_guild(guild_id)
    settings = await store.get_settings(db, guild_id)

    up_to = max(1, min(up_to, 200))

    average_xp = (settings["min_xp"] + settings["max_xp"]) / 2 or 1
    cooldown = settings["cooldown_seconds"]

    rewards = {r["level"]: r["role_id"] for r in await store.rewards(db, guild_id)}

    rows = []
    previous = 0
    for level in range(1, up_to + 1):
        total = store.xp_for_level(level)
        step = total - previous
        previous = total

        messages = round(step / average_xp) if average_xp else 0
        role = guild.get_role(rewards[level]) if guild and level in rewards else None

        rows.append({
            "level": level,
            "total_xp": total,
            "step_xp": step,
            "messages": messages,
            "total_messages": round(total / average_xp) if average_xp else 0,
            # Fastest possible, if somebody writes exactly on every cooldown.
            "min_seconds": messages * cooldown,
            "role_id": str(rewards[level]) if level in rewards else None,
            "role_name": role.name if role else None,
        })

    return {
        "curve": "level = floor(sqrt(xp / 100))",
        "average_xp_per_message": average_xp,
        "cooldown_seconds": cooldown,
        "levels": rows,
    }


# ══════════════════════════════════════════════════════════════════════
#  Reward roles
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/rewards", summary="Add a reward role")
async def add_reward(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    try:
        level = max(1, min(int(data.get("level", 0)), 10_000))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Level muss eine Zahl sein.")

    role_id = str(data.get("role_id") or "")
    if not role_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine Rolle auswählen.")

    role = guild.get_role(int(role_id))
    if role is None:
        raise HTTPException(status_code=404, detail="Die Rolle gibt es nicht mehr.")

    # Checking now saves a stream of Forbidden errors later, when nobody
    # is watching the log.
    me = guild.me
    if me and role >= me.top_role:
        raise HTTPException(
            status_code=400,
            detail=f"@{role.name} steht über der Rolle des Bots — er könnte sie "
                   "niemandem geben. Schieb die Bot-Rolle darüber.",
        )
    if role.managed:
        raise HTTPException(
            status_code=400,
            detail=f"@{role.name} wird von einer Integration verwaltet und kann "
                   "nicht vergeben werden.",
        )

    await store.set_reward(db, guild_id, level, role.id)
    await feature_audit.log_action(
        "leveling_reward_add", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"Level {level} → @{role.name}",
    )
    return {"status": "success", "result": f"Ab Level {level} gibt es @{role.name}."}


@router.delete("/{guild_id}/rewards/{level}", summary="Remove a reward role")
async def delete_reward(
    guild_id: int, level: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.remove_reward(db, guild_id, level):
        raise HTTPException(status_code=404, detail="Für dieses Level war nichts eingetragen.")

    await feature_audit.log_action(
        "leveling_reward_remove", actor=actor or "dashboard",
        guild_id=guild_id, detail=f"Level {level}",
    )
    return {"status": "success", "result": "Entfernt."}


@router.post("/{guild_id}/rewards/sync", summary="Hand out missing reward roles")
async def sync_rewards(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Give everyone the roles their level already earns them.

    Needed after adding a reward: without it only members who level up
    again would ever receive the new role.
    """
    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    settings = await store.get_settings(db, guild_id)
    stack = bool(settings.get("stack_roles", 1))
    entries = await store.leaderboard(db, guild_id, limit=100)

    changed = 0
    skipped = 0
    me = guild.me
    top = me.top_role if me else None

    for entry in entries:
        member = guild.get_member(entry["user_id"])
        if member is None:
            continue

        add_ids, remove_ids = await store.roles_for_level(
            db, guild_id, entry["level"], stack=stack
        )
        held = {r.id for r in member.roles}

        def usable(role):
            return role is not None and not role.managed and (
                top is None or role < top
            )

        to_add = [
            role for role in (guild.get_role(r) for r in add_ids)
            if usable(role) and role.id not in held
        ]
        to_remove = [
            role for role in (guild.get_role(r) for r in remove_ids)
            if usable(role) and role.id in held
        ]

        if not to_add and not to_remove:
            continue
        try:
            if to_add:
                await member.add_roles(*to_add, reason="Level-Belohnung nachgetragen")
            if to_remove:
                await member.remove_roles(*to_remove, reason="Level-Belohnung angepasst")
            changed += 1
        except Exception:
            skipped += 1

    note = f" ({skipped} übersprungen)" if skipped else ""
    return {
        "status": "success",
        "result": f"{changed} Mitglieder angepasst{note}.",
        "changed": changed,
    }


# ══════════════════════════════════════════════════════════════════════
#  Automatic role ladder
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/ladder/options", summary="Choices for the role ladder")
async def ladder_options(guild_id: int):
    """The colour ramps, name styles and spacings the dashboard offers."""
    from utils import level_presets as presets

    return {
        "ramps": [
            {
                "id": key,
                "label": value["label"],
                "description": value["description"],
                # A few swatches so the dashboard can show the ramp.
                "preview": [
                    f"#{c:06x}" for c in presets.ramp_colours(key, 5)
                ],
            }
            for key, value in presets.RAMPS.items()
        ],
        "styles": [
            {"id": key, "label": value["label"]}
            for key, value in presets.NAME_STYLES.items()
        ],
        "spacings": [
            {"id": key, "label": value["label"], "description": value["description"]}
            for key, value in presets.SPACINGS.items()
        ],
    }


@router.post("/{guild_id}/ladder/preview", summary="What the ladder would look like")
async def ladder_preview(guild_id: int, data: dict):
    """
    Work out the ladder without creating anything.

    Creating a dozen roles is hard to undo by hand, so nothing happens
    until somebody has seen exactly what they are going to get.
    """
    from utils import level_presets as presets

    try:
        count = max(1, min(int(data.get("count", 5)), 25))
        step = max(1, min(int(data.get("step", 5)), 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Anzahl und Abstand müssen Zahlen sein.")

    return {
        "rungs": presets.build_ladder(
            ramp=str(data.get("ramp", "sunrise")),
            style=str(data.get("style", "level")),
            spacing=str(data.get("spacing", "linear")),
            count=count, step=step,
        )
    }


@router.post("/{guild_id}/ladder", summary="Create the roles and wire them up")
async def create_ladder(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Create one Discord role per rung, colour it, order it and register it
    as the reward for that level.

    `full_setup` additionally applies sensible leveling settings, for a
    server that has not configured anything yet.
    """
    import discord

    from utils import level_presets as presets

    db = await _db()
    guild = _guild_or_404(bot, guild_id)

    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        raise HTTPException(
            status_code=403,
            detail="Dem Bot fehlt das Recht „Rollen verwalten“.",
        )

    try:
        count = max(1, min(int(data.get("count", 5)), 25))
        step = max(1, min(int(data.get("step", 5)), 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Anzahl und Abstand müssen Zahlen sein.")

    rungs = presets.build_ladder(
        ramp=str(data.get("ramp", "sunrise")),
        style=str(data.get("style", "level")),
        spacing=str(data.get("spacing", "linear")),
        count=count, step=step,
    )

    # Discord caps a guild at 250 roles; failing halfway would leave a
    # mess, so check before creating the first one.
    if len(guild.roles) + len(rungs) > 250:
        raise HTTPException(
            status_code=400,
            detail=f"Der Server hat {len(guild.roles)} Rollen. {len(rungs)} weitere "
                   "würden über das Limit von 250 gehen.",
        )

    existing = {role.name.lower(): role for role in guild.roles}
    reuse = bool(data.get("reuse_existing", True))

    created, reused, failed = [], [], []
    for rung in rungs:
        role = existing.get(rung["name"].lower()) if reuse else None

        if role is None:
            try:
                role = await guild.create_role(
                    name=rung["name"],
                    colour=discord.Colour(rung["colour"]),
                    hoist=bool(data.get("hoist", False)),
                    mentionable=False,
                    reason="Level-Rollen automatisch angelegt",
                )
                created.append(role)
            except discord.Forbidden:
                raise HTTPException(
                    status_code=403,
                    detail="Der Bot darf keine Rollen anlegen.",
                )
            except discord.HTTPException as exc:
                failed.append(f"{rung['name']}: {exc}")
                continue
        else:
            reused.append(role)

        await store.set_reward(db, guild_id, rung["level"], role.id)
        rung["role_id"] = str(role.id)

    # Order them so the highest level sits on top, all below the bot.
    # Without this they land in creation order at the very bottom and the
    # colour ramp reads backwards in the member list.
    try:
        made = [r for r in created if r in guild.roles or True]
        if made:
            base = max(1, me.top_role.position - len(made) - 1)
            positions = {
                role: base + index for index, role in enumerate(made)
            }
            await guild.edit_role_positions(
                positions=positions, reason="Level-Rollen sortiert"
            )
    except discord.Forbidden:
        failed.append("Die Rollen konnten nicht sortiert werden (fehlende Rechte).")
    except Exception as exc:
        failed.append(f"Sortieren fehlgeschlagen: {exc}")

    applied_settings = None
    if data.get("full_setup"):
        # Do not switch the announcement channel to something the caller
        # did not ask for; everything else gets a sane starting value.
        starter = dict(presets.STARTER_SETTINGS)
        if str(data.get("channel_id") or "").isdigit():
            starter["channel_id"] = int(data["channel_id"])
        applied_settings = await store.save_settings(db, guild_id, starter)
        _forget(bot, guild_id)

    await feature_audit.log_action(
        "leveling_ladder", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{len(created)} Rollen angelegt, {len(reused)} übernommen",
    )

    parts = []
    if created:
        parts.append(f"{len(created)} Rollen angelegt")
    if reused:
        parts.append(f"{len(reused)} vorhandene übernommen")
    if applied_settings:
        parts.append("Einstellungen gesetzt")

    return {
        "status": "success",
        "result": ", ".join(parts) + "." if parts else "Nichts zu tun.",
        "created": len(created),
        "reused": len(reused),
        "warnings": failed,
        "rungs": rungs,
        "settings_applied": bool(applied_settings),
    }


# ══════════════════════════════════════════════════════════════════════
#  Multipliers and exclusions
# ══════════════════════════════════════════════════════════════════════


def _target(data: dict, guild):
    """Resolve a role or channel from the request body."""
    target_id = str(data.get("target_id") or "")
    target_type = str(data.get("target_type") or "")

    if not target_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte eine Rolle oder einen Kanal wählen.")
    if target_type not in ("role", "channel"):
        raise HTTPException(status_code=400, detail="target_type muss role oder channel sein.")

    found = (
        guild.get_role(int(target_id)) if target_type == "role"
        else guild.get_channel(int(target_id))
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Das gibt es nicht mehr.")
    return int(target_id), target_type, found


@router.post("/{guild_id}/multipliers", summary="Set an XP multiplier")
async def add_multiplier(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)
    target_id, target_type, found = _target(data, guild)

    try:
        value = float(data.get("multiplier", 1))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Der Faktor muss eine Zahl sein.")
    if value <= 0 or value > 100:
        raise HTTPException(status_code=400, detail="Der Faktor muss zwischen 0 und 100 liegen.")

    await store.set_multiplier(db, guild_id, target_id, target_type, value)
    await feature_audit.log_action(
        "leveling_multiplier", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=f"{found.name}: {value}x",
    )
    return {"status": "success", "result": f"{found.name} bekommt {value}× XP."}


@router.delete("/{guild_id}/multipliers/{target_type}/{target_id}",
               summary="Remove a multiplier")
async def delete_multiplier(
    guild_id: int, target_type: str, target_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.remove_multiplier(db, guild_id, target_id, target_type):
        raise HTTPException(status_code=404, detail="Da war kein Multiplikator.")
    return {"status": "success", "result": "Entfernt."}


@router.post("/{guild_id}/excluded", summary="Exclude a role or channel from XP")
async def add_excluded(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    db = await _db()
    guild = _guild_or_404(bot, guild_id)
    target_id, target_type, found = _target(data, guild)

    await store.add_excluded(db, guild_id, target_id, target_type)
    await feature_audit.log_action(
        "leveling_exclude", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id, detail=found.name,
    )
    return {"status": "success", "result": f"{found.name} bekommt kein XP mehr."}


@router.delete("/{guild_id}/excluded/{target_type}/{target_id}",
               summary="Remove an exclusion")
async def delete_excluded(
    guild_id: int, target_type: str, target_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    db = await _db()
    if not await store.remove_excluded(db, guild_id, target_id, target_type):
        raise HTTPException(status_code=404, detail="Das war nicht ausgenommen.")
    return {"status": "success", "result": "Aufgehoben."}


# ══════════════════════════════════════════════════════════════════════
#  Preview
# ══════════════════════════════════════════════════════════════════════


@router.post("/{guild_id}/preview", summary="Post a level-up preview")
async def preview(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Send the level-up message into a channel, filled in as if the caller
    had just levelled up. Unsaved text can be passed along.
    """
    from utils.panels import Panel

    db = await _db()
    guild = _guild_or_404(bot, guild_id)
    settings = await store.get_settings(db, guild_id)

    channel_id = str(data.get("channel_id") or settings.get("channel_id") or "")
    if not channel_id.isdigit():
        raise HTTPException(status_code=400, detail="Bitte einen Kanal wählen.")

    channel = guild.get_channel(int(channel_id))
    if channel is None or not hasattr(channel, "send"):
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    actor = str(data.get("actor", ""))
    member = guild.get_member(int(actor)) if actor.isdigit() else None
    member = member or guild.me

    stats = await store.get_user(db, guild_id, member.id)
    level = max(1, stats["level"] or 1)

    text = store.fill(data.get("level_message") or settings["level_message"], {
        "user": member.mention,
        "user_name": member.name,
        "user_nick": member.display_name,
        "level": level,
        "xp": stats["xp"],
        "rank": await store.get_rank(db, guild_id, member.id),
        "messages": stats["messages"],
        "server": guild.name,
        "next_level": level + 1,
        "next_xp": store.xp_for_level(level + 1) - stats["xp"],
    })

    try:
        colour = data.get("embed_color", settings["embed_color"])
        if isinstance(colour, str):
            colour = int(colour.lstrip("#"), 16)
        message = await channel.send(view=Panel(
            "Level aufgestiegen", text,
            accent=int(colour),
            image_url=data.get("level_image") or settings.get("level_image") or None,
        ))
    except Exception as exc:
        raise HTTPException(status_code=403, detail=f"Konnte nicht senden: {exc}")

    return {
        "status": "success",
        "result": f"Vorschau in #{channel.name} gesendet.",
        "url": message.jump_url,
    }
