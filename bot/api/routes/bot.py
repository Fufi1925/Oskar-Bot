# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_bot
from api.schemas import BotInfo, BotStatus
from typing import TYPE_CHECKING
from utils.config import *


if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

@router.get("/status", response_model=BotStatus, summary="Get bot status", description="Returns real-time health metrics, latency, and scale information.")
async def get_status(bot: "universitybot" = Depends(get_bot)):
    """
    Returns the live status of the bot.
    """
    return BotStatus(
        user=str(bot.user),
        id=str(bot.user.id) if bot.user else None,
        latency=bot.latency * 1000,
        guild_count=len(bot.guilds),
        user_count=sum(g.member_count or 0 for g in bot.guilds),
        shards=bot.shard_count
    )

@router.get("/info", response_model=BotInfo, summary="Get bot info", description="Returns general information about the bot including command count and user reach.")
async def get_bot_info(bot: "universitybot" = Depends(get_bot)):
    """
    Get general information about the Discord bot.
    """
    return BotInfo(
        name=bot.user.name if bot.user else BRAND_NAME,
        id=str(bot.user.id) if bot.user else None,
        guilds=len(bot.guilds),
        users=sum(g.member_count or 0 for g in bot.guilds),
        commands=len(bot.commands),
        latency=f"{round(bot.latency * 1000, 2)}ms"
    )


# ══════════════════════════════════════════════════════════════════════
#  Public profiles for the team page
# ══════════════════════════════════════════════════════════════════════
#
# The team page is public and wants each member's real Discord name and
# avatar. Those cannot be built from an id alone -- the CDN path needs
# the avatar hash, so cdn.discordapp.com/avatars/<id>/<hash>.png is the
# only form that works and a guessed one 404s. Only the bot can look the
# hash up, hence this route.
#
# Deliberately narrow: it takes ids the page already hard-codes and
# returns the two fields Discord shows to anybody who can see the user.
# No email, no guilds, no permissions -- this endpoint is reachable
# without a session, so it must not become a user lookup service.

# A short cache. The page is public, so this must not turn into one
# Discord request per visitor, and a display name changing a few minutes
# late is nobody's problem.
_profile_cache: dict[str, tuple[float, dict]] = {}
_PROFILE_TTL = 900.0


@router.get("/profiles", summary="Public Discord profiles by id")
async def get_profiles(ids: str, bot: "universitybot" = Depends(get_bot)):
    """
    Name and avatar for a handful of user ids, for the public team page.

    `ids` is a comma-separated list. Capped, because this is reachable
    without a session and an uncapped loop here is a way to make the bot
    hammer Discord on someone else's behalf.
    """
    import time as _time

    wanted = [part.strip() for part in ids.split(",") if part.strip().isdigit()]
    if not wanted:
        raise HTTPException(status_code=400, detail="Keine gültigen IDs.")
    if len(wanted) > 10:
        raise HTTPException(status_code=400, detail="Höchstens 10 IDs.")

    now = _time.time()
    out: dict[str, dict] = {}

    for user_id in wanted:
        cached = _profile_cache.get(user_id)
        if cached and cached[0] > now:
            out[user_id] = cached[1]
            continue

        # get_user first: it is free when the user shares a guild with
        # the bot, which the team members do.
        user = bot.get_user(int(user_id))
        if user is None:
            try:
                user = await bot.fetch_user(int(user_id))
            except Exception:
                # Unknown id, or Discord said no. The page falls back to
                # initials rather than showing a broken image.
                out[user_id] = {"id": user_id, "name": None, "avatar": None}
                continue

        profile = {
            "id": user_id,
            "name": getattr(user, "global_name", None) or user.name,
            "avatar": user.display_avatar.replace(size=128).url,
        }
        _profile_cache[user_id] = (now + _PROFILE_TTL, profile)
        out[user_id] = profile

    return {"profiles": out}
