# ╔══════════════════════════════════════════════════════════════════╗
# ║   Server tools for the per-guild admin dashboard                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Real, per-guild security and maintenance tools.

The guild "admin dashboard" used to be twenty toggles that wrote a boolean
nobody read — nineteen of the twenty keys did not appear anywhere in the
bot's code. Flipping them looked like configuring something and did
nothing at all.

These endpoints do the opposite: every one of them inspects the live guild
through discord.py and reports what it actually found, and the actions
change something real. Nothing here stores a flag for its own sake.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

# Permissions that let a role take a server apart.
DANGEROUS_PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
    "mention_everyone",
    "manage_messages",
)


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="The bot is not on this server (or is still starting up).",
        )
    return guild


def _role_info(role: discord.Role) -> dict:
    held = [p for p in DANGEROUS_PERMISSIONS if getattr(role.permissions, p, False)]
    return {
        "id": str(role.id),
        "name": role.name,
        "colour": f"#{role.colour.value:06x}",
        "position": role.position,
        "members": len(role.members),
        "managed": role.managed,
        "mentionable": role.mentionable,
        "hoisted": role.hoist,
        "dangerous_permissions": held,
    }


# ══════════════════════════════════════════════════════════════════════
#  Overview
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/overview", summary="Live server overview")
async def server_overview(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """Numbers straight from the gateway — nothing cached, nothing stored."""
    guild = _guild_or_404(bot, guild_id)

    humans = sum(1 for m in guild.members if not m.bot)
    bots = sum(1 for m in guild.members if m.bot)

    me = guild.me
    missing = [
        name
        for name in (
            "manage_roles",
            "manage_channels",
            "kick_members",
            "ban_members",
            "manage_messages",
            "moderate_members",
            "view_audit_log",
        )
        if not getattr(me.guild_permissions, name, False)
    ]

    return {
        "guild_id": str(guild.id),
        "name": guild.name,
        "icon_url": str(guild.icon.url) if guild.icon else None,
        "owner_id": str(guild.owner_id),
        "created_at": guild.created_at.isoformat(),
        "members": {
            "total": guild.member_count or len(guild.members),
            "humans": humans,
            "bots": bots,
            "cached": len(guild.members),
        },
        "channels": {
            "text": len(guild.text_channels),
            "voice": len(guild.voice_channels),
            "categories": len(guild.categories),
        },
        "roles": len(guild.roles),
        "emojis": len(guild.emojis),
        "boost_level": guild.premium_tier,
        "boosts": guild.premium_subscription_count,
        "verification_level": str(guild.verification_level),
        "bot_role_position": me.top_role.position if me else None,
        "bot_missing_permissions": missing,
    }


# ══════════════════════════════════════════════════════════════════════
#  Security scan
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/security-scan", summary="Scan the server for risks")
async def security_scan(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    Walk roles, members, webhooks and invites and report concrete findings.

    Every finding names the object it is about, so it can be acted on
    instead of being a vague warning.
    """
    guild = _guild_or_404(bot, guild_id)
    findings: list[dict] = []

    # --- roles with dangerous permissions ---------------------------
    admin_roles = []
    for role in guild.roles:
        if role.is_default():
            continue
        if role.permissions.administrator:
            admin_roles.append(_role_info(role))

    for role in admin_roles:
        if role["members"] > 0 and not role["managed"]:
            findings.append({
                "severity": "high" if role["members"] > 3 else "medium",
                "kind": "admin_role",
                "title": f"Role “{role['name']}” grants Administrator",
                "detail": f"{role['members']} member(s) hold it.",
                "target_id": role["id"],
            })

    # --- @everyone permissions --------------------------------------
    everyone = guild.default_role
    risky_everyone = [
        p for p in ("mention_everyone", "manage_messages", "manage_webhooks")
        if getattr(everyone.permissions, p, False)
    ]
    if risky_everyone:
        findings.append({
            "severity": "high",
            "kind": "everyone_permissions",
            "title": "@everyone has elevated permissions",
            "detail": ", ".join(risky_everyone),
            "target_id": str(everyone.id),
        })

    # --- bots with administrator ------------------------------------
    for member in guild.members:
        if member.bot and member.guild_permissions.administrator:
            findings.append({
                "severity": "medium",
                "kind": "bot_admin",
                "title": f"Bot “{member.display_name}” has Administrator",
                "detail": "Grant only the permissions the bot needs.",
                "target_id": str(member.id),
            })

    # --- very new accounts ------------------------------------------
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    fresh = [m for m in guild.members if not m.bot and m.created_at > cutoff]
    if len(fresh) >= 5:
        findings.append({
            "severity": "medium",
            "kind": "new_accounts",
            "title": f"{len(fresh)} accounts younger than 7 days",
            "detail": "A sudden influx of fresh accounts can indicate a raid.",
            "target_id": None,
        })

    # --- webhooks ----------------------------------------------------
    webhook_count = 0
    if guild.me.guild_permissions.manage_webhooks:
        try:
            hooks = await guild.webhooks()
            webhook_count = len(hooks)
            if webhook_count > 10:
                findings.append({
                    "severity": "low",
                    "kind": "webhooks",
                    "title": f"{webhook_count} webhooks configured",
                    "detail": "Unused webhooks are a common backdoor.",
                    "target_id": None,
                })
        except discord.Forbidden:
            pass

    # --- permanent invites -------------------------------------------
    invite_count = 0
    permanent = 0
    if guild.me.guild_permissions.manage_guild:
        try:
            invites = await guild.invites()
            invite_count = len(invites)
            permanent = sum(1 for i in invites if i.max_age == 0)
            if permanent > 5:
                findings.append({
                    "severity": "low",
                    "kind": "invites",
                    "title": f"{permanent} invites never expire",
                    "detail": "Expiring invites are easier to keep track of.",
                    "target_id": None,
                })
        except discord.Forbidden:
            pass

    # --- 2FA / verification level ------------------------------------
    if guild.verification_level in (
        discord.VerificationLevel.none,
        discord.VerificationLevel.low,
    ):
        findings.append({
            "severity": "medium",
            "kind": "verification_level",
            "title": f"Verification level is “{guild.verification_level}”",
            "detail": "Medium or higher blocks most drive-by spam accounts.",
            "target_id": None,
        })

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))

    return {
        "guild_id": str(guild.id),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "score": max(0, 100 - sum(
            {"high": 20, "medium": 10, "low": 4}.get(f["severity"], 0)
            for f in findings
        )),
        "counts": {
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
        },
        "stats": {
            "admin_roles": len(admin_roles),
            "webhooks": webhook_count,
            "invites": invite_count,
            "permanent_invites": permanent,
            "new_accounts_7d": len(fresh),
        },
        "findings": findings,
    }


# ══════════════════════════════════════════════════════════════════════
#  Roles
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/roles/audit", summary="Role overview with risk flags")
async def role_audit(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    bot_position = guild.me.top_role.position if guild.me else 0

    roles = []
    for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
        if role.is_default():
            continue
        info = _role_info(role)
        # A role above the bot cannot be assigned or removed by it.
        info["above_bot"] = role.position >= bot_position
        info["unused"] = info["members"] == 0 and not role.managed
        roles.append(info)

    return {
        "guild_id": str(guild.id),
        "bot_role_position": bot_position,
        "roles": roles,
        "summary": {
            "total": len(roles),
            "with_admin": sum(
                1 for r in roles if "administrator" in r["dangerous_permissions"]
            ),
            "unused": sum(1 for r in roles if r["unused"]),
            "above_bot": sum(1 for r in roles if r["above_bot"]),
        },
    }


# ══════════════════════════════════════════════════════════════════════
#  Channels
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/channels/audit", summary="Channel overview")
async def channel_audit(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    everyone = guild.default_role

    channels = []
    for channel in guild.text_channels:
        overwrite = channel.overwrites_for(everyone)
        perms = channel.permissions_for(guild.me)
        channels.append({
            "id": str(channel.id),
            "name": channel.name,
            "category": channel.category.name if channel.category else None,
            "nsfw": channel.is_nsfw(),
            "slowmode": channel.slowmode_delay,
            "public": overwrite.view_channel is not False,
            "everyone_can_send": overwrite.send_messages is not False,
            "bot_can_send": perms.send_messages,
            "bot_can_read": perms.read_messages,
        })

    return {
        "guild_id": str(guild.id),
        "channels": channels,
        "summary": {
            "total": len(channels),
            "public": sum(1 for c in channels if c["public"]),
            "bot_cannot_send": sum(1 for c in channels if not c["bot_can_send"]),
            "with_slowmode": sum(1 for c in channels if c["slowmode"]),
        },
    }


# ══════════════════════════════════════════════════════════════════════
#  Invites & webhooks
# ══════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/invites/audit", summary="Active invites")
async def invite_audit(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    if not guild.me.guild_permissions.manage_guild:
        raise HTTPException(
            status_code=403,
            detail="The bot needs the Manage Server permission to read invites.",
        )

    try:
        invites = await guild.invites()
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused the request.")

    return {
        "guild_id": str(guild.id),
        "invites": [
            {
                "code": i.code,
                "url": i.url,
                "uses": i.uses,
                "max_uses": i.max_uses,
                "permanent": i.max_age == 0,
                "channel": i.channel.name if i.channel else None,
                "inviter": str(i.inviter) if i.inviter else None,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in invites
        ],
    }


@router.get("/{guild_id}/webhooks/audit", summary="Webhooks in this server")
async def webhook_audit(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    if not guild.me.guild_permissions.manage_webhooks:
        raise HTTPException(
            status_code=403,
            detail="The bot needs the Manage Webhooks permission.",
        )

    try:
        hooks = await guild.webhooks()
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused the request.")

    return {
        "guild_id": str(guild.id),
        "webhooks": [
            {
                "id": str(h.id),
                "name": h.name,
                "channel": h.channel.name if h.channel else None,
                "created_by": str(h.user) if h.user else None,
                "is_bot_owned": bool(h.user and h.user.bot),
            }
            for h in hooks
        ],
    }


@router.delete("/{guild_id}/webhooks/{webhook_id}", summary="Delete a webhook")
async def delete_webhook(
    guild_id: int,
    webhook_id: int,
    actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)
    try:
        hooks = await guild.webhooks()
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused the request.")

    target = next((h for h in hooks if h.id == webhook_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")

    name = target.name
    try:
        await target.delete(reason=f"Dashboard: removed by {actor or 'admin'}")
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="The bot may not delete it.")

    await feature_audit.log_action(
        "webhook_deleted", actor=actor or "dashboard", guild_id=guild_id, detail=name
    )
    return {"status": "success", "deleted": name}
