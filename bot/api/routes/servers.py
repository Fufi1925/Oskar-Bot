"""
Global server management.

The per-guild pages configure one server at a time. This is the view from
above: every server the bot is in, with the things an owner actually needs —
an invite link, who owns it, how healthy it is, and a leave button.

Everything here is global-admin territory, never per-guild staff.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import dashboard_authority as authority
from utils import dashboard_roles as roles
from utils import feature_audit
from utils import feature_gates

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

CONFIG_DB = "db/admin_config.db"
BLOCK_DB = "db/block.db"

# Invites created by the dashboard are cached so repeated clicks do not spam
# Discord with new invites for the same channel.
_invite_cache: dict[int, tuple[str, float]] = {}
INVITE_CACHE_TTL = 3600.0


async def _premium_guild_ids() -> set[str]:
    ids: set[str] = set()
    try:
        async with aiosqlite.connect(CONFIG_DB) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS premium_guilds ("
                " guild_id INTEGER PRIMARY KEY, granted_at INTEGER)"
            )
            await db.commit()
            async with db.execute("SELECT guild_id FROM premium_guilds") as cursor:
                async for row in cursor:
                    ids.add(str(row[0]))
    except Exception as exc:
        print(f"[servers] premium lookup failed: {exc}")
    return ids


async def _blacklisted_guild_ids() -> set[str]:
    ids: set[str] = set()
    try:
        async with aiosqlite.connect(BLOCK_DB) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)"
            )
            await db.commit()
            async with db.execute("SELECT guild_id FROM guild_blacklist") as cursor:
                async for row in cursor:
                    ids.add(str(row[0]))
    except Exception as exc:
        print(f"[servers] blacklist lookup failed: {exc}")
    return ids


def _permission_report(guild: discord.Guild) -> dict:
    """Which Discord permissions the bot is missing in this guild."""
    me = guild.me
    if me is None:
        return {"known": False, "missing": [], "administrator": False, "top_role_position": 0}

    perms = me.guild_permissions
    wanted = {
        "administrator": "Administrator",
        "manage_guild": "Manage Server",
        "manage_roles": "Manage Roles",
        "manage_channels": "Manage Channels",
        "ban_members": "Ban Members",
        "kick_members": "Kick Members",
        "moderate_members": "Timeout Members",
        "manage_messages": "Manage Messages",
        "create_instant_invite": "Create Invite",
        "view_audit_log": "View Audit Log",
        "manage_webhooks": "Manage Webhooks",
        "manage_nicknames": "Manage Nicknames",
        "embed_links": "Embed Links",
        "attach_files": "Attach Files",
        "add_reactions": "Add Reactions",
    }
    missing = [label for attr, label in wanted.items() if not getattr(perms, attr, False)]
    # With Administrator nothing is really missing.
    if perms.administrator:
        missing = []

    return {
        "known": True,
        "administrator": bool(perms.administrator),
        "missing": missing,
        "top_role_position": me.top_role.position,
        "highest_role_name": me.top_role.name,
    }


def _summarise(guild: discord.Guild, premium: set[str], blacklisted: set[str]) -> dict:
    members = guild.member_count or len(guild.members)
    bots = sum(1 for m in guild.members if m.bot)
    humans = max(0, members - bots) if members else len(guild.members) - bots

    owner = guild.owner
    joined = guild.me.joined_at if guild.me else None

    return {
        "id": str(guild.id),
        "name": guild.name,
        "icon_url": str(guild.icon.url) if guild.icon else None,
        "banner_url": str(guild.banner.url) if guild.banner else None,
        "description": guild.description or "",
        "owner_id": str(guild.owner_id),
        "owner_name": str(owner) if owner else None,
        "owner_avatar": str(owner.display_avatar.url) if owner else None,
        "member_count": members,
        "bot_count": bots,
        "human_count": humans,
        # A high bot ratio is the classic bot-farm signal.
        "bot_ratio": round(bots / members, 3) if members else 0.0,
        "channel_count": len(guild.channels),
        "text_channels": len(guild.text_channels),
        "voice_channels": len(guild.voice_channels),
        "role_count": len(guild.roles),
        "emoji_count": len(guild.emojis),
        "boost_level": guild.premium_tier,
        "boost_count": guild.premium_subscription_count or 0,
        "verification_level": str(guild.verification_level),
        "created_at": int(guild.created_at.timestamp()) if guild.created_at else 0,
        "joined_at": int(joined.timestamp()) if joined else 0,
        "vanity_url": guild.vanity_url_code or "",
        "shard_id": guild.shard_id or 0,
        "large": guild.large,
        "premium": str(guild.id) in premium,
        "blacklisted": str(guild.id) in blacklisted,
        "unavailable": guild.unavailable,
        "permissions": _permission_report(guild),
        "features": list(guild.features),
    }


# ── Listing ───────────────────────────────────────────────────────────────


@router.get("/", summary="Every server the bot is in")
async def list_servers(
    sort: str = "members",
    bot: "universitybot" = Depends(get_bot),
):
    premium = await _premium_guild_ids()
    blacklisted = await _blacklisted_guild_ids()

    servers = [_summarise(g, premium, blacklisted) for g in bot.guilds]

    sorters = {
        "members": lambda s: -s["member_count"],
        "name": lambda s: s["name"].lower(),
        "joined": lambda s: -s["joined_at"],
        "created": lambda s: -s["created_at"],
        "bots": lambda s: -s["bot_ratio"],
        "boosts": lambda s: -s["boost_count"],
    }
    servers.sort(key=sorters.get(sort, sorters["members"]))

    total_members = sum(s["member_count"] for s in servers)
    return {
        "servers": servers,
        "count": len(servers),
        "total_members": total_members,
        "total_humans": sum(s["human_count"] for s in servers),
        "total_bots": sum(s["bot_count"] for s in servers),
        "total_channels": sum(s["channel_count"] for s in servers),
        "premium_count": sum(1 for s in servers if s["premium"]),
        "blacklisted_count": sum(1 for s in servers if s["blacklisted"]),
        "missing_permissions_count": sum(1 for s in servers if s["permissions"]["missing"]),
        "average_members": round(total_members / len(servers)) if servers else 0,
        "largest": servers[0]["name"] if servers and sort == "members" else None,
    }


@router.get("/{guild_id}", summary="Detailed view of one server")
async def get_server(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    premium = await _premium_guild_ids()
    blacklisted = await _blacklisted_guild_ids()
    summary = _summarise(guild, premium, blacklisted)

    # Admins and staff of that server, useful for "who do I contact".
    staff = []
    for member in guild.members:
        if member.bot:
            continue
        perms = member.guild_permissions
        if member.id == guild.owner_id or perms.administrator or perms.manage_guild:
            staff.append(
                {
                    "user_id": str(member.id),
                    "name": str(member),
                    "display_name": member.display_name,
                    "avatar": str(member.display_avatar.url),
                    "is_owner": member.id == guild.owner_id,
                    "administrator": bool(perms.administrator),
                    "top_role": member.top_role.name,
                }
            )
    staff.sort(key=lambda s: (not s["is_owner"], not s["administrator"], s["name"].lower()))

    summary["staff"] = staff[:50]
    summary["staff_count"] = len(staff)

    # Cached invite, if we made one earlier.
    cached = _invite_cache.get(guild.id)
    summary["cached_invite"] = cached[0] if cached and cached[1] > time.time() else None

    return summary


# ── Invites ───────────────────────────────────────────────────────────────


@router.post("/{guild_id}/invite", summary="Create an invite link for a server")
async def create_invite(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Returns a usable invite for the server so the owner can jump in without
    asking anyone. Existing invites are reused before creating a new one.
    """
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    force_new = bool(data.get("force_new", False))
    actor = str(data.get("actor", "dashboard")).strip()[:64] or "dashboard"

    if not force_new:
        cached = _invite_cache.get(guild.id)
        if cached and cached[1] > time.time():
            return {"status": "success", "invite": cached[0], "source": "cache"}

    me = guild.me
    if me is None:
        raise HTTPException(status_code=503, detail="Bot member is not cached yet.")

    # 1. A vanity URL is the nicest link if the server has one.
    if guild.vanity_url_code and not force_new:
        url = f"https://discord.gg/{guild.vanity_url_code}"
        _invite_cache[guild.id] = (url, time.time() + INVITE_CACHE_TTL)
        return {"status": "success", "invite": url, "source": "vanity"}

    # 2. Reuse an existing permanent invite before making another one.
    if not force_new and me.guild_permissions.manage_guild:
        try:
            existing = await guild.invites()
            permanent = [i for i in existing if i.max_age == 0 and i.max_uses == 0]
            if permanent:
                url = permanent[0].url
                _invite_cache[guild.id] = (url, time.time() + INVITE_CACHE_TTL)
                return {"status": "success", "invite": url, "source": "existing"}
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

    # 3. Create a fresh one in the first channel where we are allowed to.
    if not me.guild_permissions.create_instant_invite:
        raise HTTPException(
            status_code=403,
            detail="Bot is missing the 'Create Invite' permission in this server.",
        )

    try:
        max_age = int(data.get("max_age", 0) or 0)
    except (TypeError, ValueError):
        max_age = 0
    max_age = max(0, min(max_age, 604800))  # Discord's ceiling is 7 days

    target = None
    candidates = [guild.rules_channel, guild.system_channel] if hasattr(guild, "rules_channel") else []
    candidates = [c for c in candidates if c is not None]
    candidates += sorted(guild.text_channels, key=lambda c: c.position)

    for channel in candidates:
        try:
            if channel.permissions_for(me).create_instant_invite:
                target = channel
                break
        except Exception:
            continue

    if target is None:
        raise HTTPException(
            status_code=403,
            detail="No channel in this server allows the bot to create an invite.",
        )

    try:
        invite = await target.create_invite(
            max_age=max_age,
            max_uses=0,
            unique=force_new,
            reason=f"Dashboard invite requested by {actor}",
        )
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused: missing permissions.")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    _invite_cache[guild.id] = (invite.url, time.time() + INVITE_CACHE_TTL)

    await feature_audit.log_action(
        "server_invite_created", actor=actor, guild_id=guild_id, detail=f"#{target.name}"
    )

    return {
        "status": "success",
        "invite": invite.url,
        "code": invite.code,
        "channel": target.name,
        "source": "created",
        "expires_in": max_age,
    }


@router.get("/{guild_id}/invites", summary="Existing invites of a server")
async def list_invites(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    me = guild.me
    if me is None or not me.guild_permissions.manage_guild:
        raise HTTPException(
            status_code=403, detail="Bot needs 'Manage Server' to read invites."
        )

    try:
        invites = await guild.invites()
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused: missing permissions.")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    return {
        "invites": [
            {
                "code": i.code,
                "url": i.url,
                "uses": i.uses or 0,
                "max_uses": i.max_uses or 0,
                "max_age": i.max_age or 0,
                "temporary": bool(i.temporary),
                "channel": i.channel.name if i.channel else "",
                "inviter": str(i.inviter) if i.inviter else "",
                "created_at": int(i.created_at.timestamp()) if i.created_at else 0,
            }
            for i in invites
        ],
        "count": len(invites),
    }


# ── Leaving ───────────────────────────────────────────────────────────────


@router.post("/{guild_id}/leave", summary="Make the bot leave a server")
async def leave_server(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Removes the bot from a server. Optionally sends a goodbye message first and
    blacklists the server so it cannot simply re-invite the bot.
    """
    actor = str(data.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")

    await roles.load()
    if not authority.may_remove_bot(bot, actor, guild_id):
        raise HTTPException(
            status_code=403,
            detail="Only a bot owner or the owner of this server may remove the bot.",
        )

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    # Typing the server name is the safety net against a mis-click that kicks
    # the bot out of the wrong server.
    confirm = str(data.get("confirm_name", "")).strip()
    if confirm and confirm.lower() != guild.name.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation does not match. Type the exact server name: {guild.name}",
        )

    name = guild.name
    reason = str(data.get("reason", "")).strip()[:400]
    farewell = str(data.get("message", "")).strip()[:1800]
    blacklist = bool(data.get("blacklist", False))

    sent = False
    if farewell:
        channel = guild.system_channel
        if channel is None or not channel.permissions_for(guild.me).send_messages:
            channel = next(
                (c for c in sorted(guild.text_channels, key=lambda c: c.position)
                 if c.permissions_for(guild.me).send_messages),
                None,
            )
        if channel is not None:
            try:
                await channel.send(farewell)
                sent = True
            except Exception:
                sent = False

    if blacklist:
        try:
            async with aiosqlite.connect(BLOCK_DB) as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO guild_blacklist (guild_id) VALUES (?)",
                    (str(guild_id),),
                )
                await db.commit()
            feature_gates.invalidate_blacklist()
            await feature_gates.refresh_blacklist()
        except Exception as exc:
            print(f"[servers] blacklist insert failed: {exc}")

    try:
        await guild.leave()
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    _invite_cache.pop(guild_id, None)

    await feature_audit.log_action(
        "bot_left_guild",
        actor=actor,
        guild_id=guild_id,
        detail=f"{name}" + (f": {reason}" if reason else "") + (" (blacklisted)" if blacklist else ""),
    )

    return {
        "status": "success",
        "guild_id": str(guild_id),
        "name": name,
        "farewell_sent": sent,
        "blacklisted": blacklist,
    }


# ── Blacklist ─────────────────────────────────────────────────────────────


@router.get("/blacklist/entries", summary="Blacklisted servers and users")
async def list_blacklist(bot: "universitybot" = Depends(get_bot)):
    guilds: list[dict] = []
    users: list[dict] = []
    try:
        async with aiosqlite.connect(BLOCK_DB) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT PRIMARY KEY)"
            )
            await db.commit()

            async with db.execute("SELECT guild_id FROM guild_blacklist") as cursor:
                async for row in cursor:
                    gid = str(row[0])
                    guild = bot.get_guild(int(gid)) if gid.isdigit() else None
                    guilds.append(
                        {
                            "guild_id": gid,
                            "name": guild.name if guild else None,
                            "still_joined": guild is not None,
                        }
                    )

            async with db.execute("SELECT user_id FROM user_blacklist") as cursor:
                async for row in cursor:
                    uid = str(row[0])
                    user = bot.get_user(int(uid)) if uid.isdigit() else None
                    users.append({"user_id": uid, "name": str(user) if user else None})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Blacklist read failed: {exc}")

    return {"guilds": guilds, "users": users, "guild_count": len(guilds), "user_count": len(users)}


@router.post("/blacklist/entries", summary="Add a server or user to the blacklist")
async def add_blacklist(data: dict, bot: "universitybot" = Depends(get_bot)):
    actor = str(data.get("actor", "")).strip()
    await roles.load()
    if not authority.may_act_globally(bot, actor, "blacklist.manage"):
        raise HTTPException(status_code=403, detail="You may not manage the blacklist.")

    kind = str(data.get("kind", "guild")).strip().lower()
    target = str(data.get("id", "")).strip()
    if kind not in {"guild", "user"}:
        raise HTTPException(status_code=400, detail="kind must be 'guild' or 'user'.")
    if not target.isdigit() or not 15 <= len(target) <= 20:
        raise HTTPException(status_code=400, detail="id must be a valid Discord ID.")

    table = "guild_blacklist" if kind == "guild" else "user_blacklist"
    column = "guild_id" if kind == "guild" else "user_id"

    async with aiosqlite.connect(BLOCK_DB) as db:
        await db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({column} TEXT PRIMARY KEY)")
        await db.execute(f"INSERT OR IGNORE INTO {table} ({column}) VALUES (?)", (target,))
        await db.commit()

    feature_gates.invalidate_blacklist()
    await feature_gates.refresh_blacklist()
    await feature_audit.log_action(
        "blacklist_added", actor=actor, detail=f"{kind}: {target}"
    )
    return {"status": "success", "kind": kind, "id": target}


@router.delete("/blacklist/entries/{kind}/{target_id}", summary="Remove a blacklist entry")
async def remove_blacklist(
    kind: str, target_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    await roles.load()
    if not authority.may_act_globally(bot, actor, "blacklist.manage"):
        raise HTTPException(status_code=403, detail="You may not manage the blacklist.")

    kind = kind.strip().lower()
    if kind not in {"guild", "user"}:
        raise HTTPException(status_code=400, detail="kind must be 'guild' or 'user'.")

    table = "guild_blacklist" if kind == "guild" else "user_blacklist"
    column = "guild_id" if kind == "guild" else "user_id"

    async with aiosqlite.connect(BLOCK_DB) as db:
        await db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({column} TEXT PRIMARY KEY)")
        cursor = await db.execute(f"DELETE FROM {table} WHERE {column} = ?", (str(target_id),))
        await db.commit()
        removed = (cursor.rowcount or 0) > 0

    if not removed:
        raise HTTPException(status_code=404, detail="Not on the blacklist.")

    feature_gates.invalidate_blacklist()
    await feature_gates.refresh_blacklist()
    await feature_audit.log_action(
        "blacklist_removed", actor=actor, detail=f"{kind}: {target_id}"
    )
    return {"status": "success", "kind": kind, "id": str(target_id)}


# ── Roles in a server ─────────────────────────────────────────────────────


@router.get("/{guild_id}/roles", summary="Roles of a server, with what the bot can do")
async def list_server_roles(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    me = guild.me
    bot_top = me.top_role.position if me else 0
    can_manage = bool(me and me.guild_permissions.manage_roles)

    entries = []
    for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
        if role.is_default():
            continue

        # Discord refuses in three distinct cases, and the UI needs to tell
        # them apart — "hidden: 99 roles" was useless because it did not say
        # which problem to fix.
        if me is not None and role.id == me.top_role.id:
            # The bot's own top role. Counting it as "sits above the bot"
            # made the numbers read one too high and made no sense to anyone.
            blocked = "own_role"
            hint = "This is the bot's own role and cannot be handed out."
        elif role.managed:
            blocked = "managed"
            hint = "Managed by an integration or bot; Discord does not allow handing it out."
        elif not can_manage:
            blocked = "no_permission"
            hint = "The bot is missing the 'Manage Roles' permission in this server."
        elif role.position >= bot_top:
            blocked = "too_high"
            hint = (
                f"Sits above the bot's own role. Drag '{me.top_role.name}' above "
                f"'{role.name}' in Server Settings → Roles."
            )
        else:
            blocked = None
            hint = ""

        entries.append(
            {
                "id": str(role.id),
                "name": role.name,
                "color": f"#{role.color.value:06x}" if role.color.value else "#99aab5",
                "position": role.position,
                "members": len(role.members),
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "managed": role.managed,
                "administrator": role.permissions.administrator,
                "assignable": blocked is None,
                "blocked_reason": blocked,
                "hint": hint,
            }
        )

    assignable = [e for e in entries if e["assignable"]]
    too_high = [e for e in entries if e["blocked_reason"] == "too_high"]

    return {
        "roles": entries,
        "count": len(entries),
        "assignable_count": len(assignable),
        "too_high_count": len(too_high),
        "managed_count": sum(1 for e in entries if e["blocked_reason"] == "managed"),
        "bot_top_position": bot_top,
        "bot_role_name": me.top_role.name if me else None,
        "bot_can_manage_roles": can_manage,
        # A single, actionable sentence for the dashboard to show. Whenever
        # roles are blocked by position it names the bot role and the fix,
        # because "99 hidden" on its own told nobody what to do.
        "advice": (
            "The bot is missing the 'Manage Roles' permission in this server."
            if not can_manage
            else (
                f"The bot's role '{me.top_role.name}' sits too low: {len(too_high)} role(s) "
                f"are above it and cannot be assigned. Move it up in "
                f"Server Settings → Roles."
                if too_high
                else ""
            )
        ),
    }


@router.post("/{guild_id}/members/{user_id}/roles", summary="Give somebody a role")
async def grant_role(
    guild_id: int, user_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Hands a Discord role to a member. Used for "give me the admin role on that
    server" without having to open Discord.
    """
    actor = str(data.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")

    await roles.load()
    if not authority.may_act_on_guild(bot, actor, guild_id, "roles.manage"):
        raise HTTPException(
            status_code=403,
            detail="You need Manage Server on this server, or the 'roles.manage' permission.",
        )

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    me = guild.me
    if me is None:
        raise HTTPException(status_code=503, detail="Bot member is not cached yet.")
    if not me.guild_permissions.manage_roles:
        raise HTTPException(
            status_code=403, detail="Bot is missing the 'Manage Roles' permission."
        )

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            raise HTTPException(status_code=404, detail="That user is not in this server.")

    role_id = str(data.get("role_id", "")).strip()
    role_name = str(data.get("role_name", "")).strip()[:100]
    role = None

    if role_id.isdigit():
        role = guild.get_role(int(role_id))
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found in this server.")
    elif role_name:
        # Create the role on demand — that is what makes "give me admin here"
        # work on a server where no suitable role exists yet.
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            permissions = discord.Permissions.none()
            if bool(data.get("administrator", False)):
                if not me.guild_permissions.administrator:
                    raise HTTPException(
                        status_code=403,
                        detail="Bot needs Administrator itself to create an admin role.",
                    )
                permissions = discord.Permissions(administrator=True)
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=permissions,
                    colour=discord.Colour(int(str(data.get("color", "3b82f6")).lstrip("#"), 16)),
                    hoist=bool(data.get("hoist", False)),
                    reason=f"Dashboard role creation by {actor}",
                )
            except ValueError:
                raise HTTPException(status_code=400, detail="color must be a hex value.")
            except discord.Forbidden:
                raise HTTPException(status_code=403, detail="Discord refused to create the role.")
            except discord.HTTPException as exc:
                raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")
    else:
        raise HTTPException(status_code=400, detail="Provide role_id or role_name.")

    if role.managed:
        raise HTTPException(status_code=400, detail="Managed roles cannot be assigned by hand.")
    if role.position >= me.top_role.position:
        raise HTTPException(
            status_code=403,
            detail=f"'{role.name}' sits above the bot's highest role. Move the bot role up first.",
        )

    try:
        await member.add_roles(role, reason=f"Dashboard: granted by {actor}")
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused: missing permissions.")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    await feature_audit.log_action(
        "server_role_granted",
        actor=actor,
        guild_id=guild_id,
        detail=f"{role.name} -> {member} ({member.id})",
    )

    return {
        "status": "success",
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "role": {"id": str(role.id), "name": role.name},
        "result": f"{member.display_name} now has '{role.name}' in {guild.name}.",
    }


@router.delete("/{guild_id}/members/{user_id}/roles/{role_id}", summary="Take a role away")
async def revoke_server_role(
    guild_id: int,
    user_id: int,
    role_id: int,
    actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    if not actor:
        raise HTTPException(status_code=400, detail="actor query parameter is required.")

    await roles.load()
    if not authority.may_act_on_guild(bot, actor, guild_id, "roles.manage"):
        raise HTTPException(
            status_code=403,
            detail="You need Manage Server on this server, or the 'roles.manage' permission.",
        )

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    member = guild.get_member(user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="That user is not in this server.")

    role = guild.get_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found.")

    me = guild.me
    if me is None or role.position >= me.top_role.position:
        raise HTTPException(status_code=403, detail="That role sits above the bot's highest role.")

    try:
        await member.remove_roles(role, reason=f"Dashboard: revoked by {actor}")
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Discord refused: missing permissions.")
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord API error: {exc}")

    await feature_audit.log_action(
        "server_role_revoked",
        actor=actor,
        guild_id=guild_id,
        detail=f"{role.name} removed from {member} ({member.id})",
    )
    return {
        "status": "success",
        "result": f"'{role.name}' removed from {member.display_name}.",
    }


@router.get("/{guild_id}/members/{user_id}", summary="What roles somebody has here")
async def get_server_member(
    guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)
):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="The bot is not in this server.")

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return {"in_guild": False, "user_id": str(user_id), "guild_id": str(guild_id)}

    perms = member.guild_permissions
    return {
        "in_guild": True,
        "user_id": str(member.id),
        "guild_id": str(guild_id),
        "name": str(member),
        "display_name": member.display_name,
        "avatar": str(member.display_avatar.url),
        "joined_at": int(member.joined_at.timestamp()) if member.joined_at else 0,
        "is_owner": member.id == guild.owner_id,
        "administrator": bool(perms.administrator),
        "roles": [
            {
                "id": str(r.id),
                "name": r.name,
                "color": f"#{r.color.value:06x}" if r.color.value else "#99aab5",
                "position": r.position,
                "managed": r.managed,
            }
            for r in sorted(member.roles, key=lambda r: r.position, reverse=True)
            if not r.is_default()
        ],
    }


# ── Bot install link ──────────────────────────────────────────────────────


@router.get("/meta/install-link", summary="OAuth link to add the bot somewhere")
async def install_link(permissions: int = 8, bot: "universitybot" = Depends(get_bot)):
    """The 'add to server' link, built from the bot's own application ID."""
    import os

    client_id = os.getenv("DISCORD_CLIENT_ID") or (str(bot.user.id) if bot.user else "")
    if not client_id:
        raise HTTPException(status_code=503, detail="Bot application ID is not known yet.")

    permissions = max(0, min(int(permissions), 0xFFFFFFFFFFFFFFF))
    return {
        "url": (
            f"https://discord.com/oauth2/authorize?client_id={client_id}"
            f"&permissions={permissions}&scope=bot%20applications.commands"
        ),
        "client_id": client_id,
        "permissions": permissions,
    }
