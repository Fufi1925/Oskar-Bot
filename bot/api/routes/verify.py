# ╔══════════════════════════════════════════════════════════════════╗
# ║   Verification                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The verification tab.

Replaces the pair of handlers in guilds.py, which knew five columns and
had two bugs of their own:

  * ``verification_channel_id or 0`` stored 0 for "not set". Zero is not
    null, so the read side handed ``"0"`` back to the dashboard as
    though it were a channel id.
  * The INSERT branch defaulted every column it was not given, so the
    first save from the dashboard wiped a setup made through the chat
    command.

Everything here reports what the bot can and cannot do -- missing
permissions, a role above the bot, a deleted channel -- because that is
almost always the answer to "I set it and nothing happens".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import asyncio
import hashlib
import hmac
import os
import secrets
from typing import TYPE_CHECKING

import aiohttp

import discord
from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot, get_bot_loop, run_on_bot_loop
from utils import feature_audit, feature_gates
from utils import emoji as bot_emoji
from utils import verify_store as store
from utils.panels import Panel, StatusCard

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


def _channel_info(guild, channel_id):
    channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
    return {
        # Snowflakes travel as strings: a JSON number loses the last digits.
        "id": str(channel_id) if channel_id else None,
        "name": channel.name if channel else None,
        "missing": channel is None and bool(channel_id),
    }


def _member_card(guild, user_id) -> dict:
    """
    Enough about a member for the list to show a face and a name.

    The list used to print the raw snowflake and nothing else, which is
    unreadable -- and the id stays a string here for the same reason it
    does everywhere else: a JSON number drops the last digits.
    """
    member = guild.get_member(int(user_id)) if guild and user_id else None
    if member is None:
        return {
            "id": str(user_id),
            "name": None,
            "display_name": None,
            "avatar": None,
            "left": True,
        }
    return {
        "id": str(user_id),
        "name": getattr(member, "name", None),
        "display_name": getattr(member, "display_name", None),
        # display_avatar, not avatar: the plain one is None for anybody
        # still on a default avatar.
        "avatar": getattr(getattr(member, "display_avatar", None), "url", None),
        "bot": bool(getattr(member, "bot", False)),
        "left": False,
    }


def _colour_of(role):
    """
    A role colour as a plain int.

    discord.py hands back a Colour object, but not every code path does
    -- reading .value unconditionally turned one odd role into a 500 for
    the whole page.
    """
    colour = getattr(role, "color", None) if role is not None else None
    if colour is None:
        return None
    return getattr(colour, "value", colour) if not isinstance(colour, int) else colour


def _role_info(guild, role_id):
    role = guild.get_role(int(role_id)) if guild and role_id else None
    return {
        "id": str(role_id) if role_id else None,
        "name": getattr(role, "name", None) if role else None,
        "colour": _colour_of(role),
        "missing": role is None and bool(role_id),
    }


def _role_problem(guild, role) -> str | None:
    if role is None:
        return None
    me = getattr(guild, "me", None)
    if me is None:
        return None
    if role.managed:
        return f"@{role.name} gehört zu einer Integration und ist nicht vergebbar."
    if role.is_default():
        return "@everyone kann nicht vergeben werden."
    if role >= me.top_role:
        return (f"@{role.name} steht über der Bot-Rolle — er kann sie niemandem "
                "geben. Schieb die Bot-Rolle darüber.")
    return None


def _warnings(guild, settings: dict) -> list[str]:
    """Everything standing between this config and it actually working."""
    problems = list(store.readiness(settings))
    if guild is None:
        return problems

    # getattr, not guild.me: the attribute is missing entirely while the
    # bot is still connecting, and a warnings helper must never be the
    # thing that takes the whole page down with a 500.
    me = getattr(guild, "me", None)
    if me is not None and not me.guild_permissions.manage_roles:
        problems.append("Dem Bot fehlt das Recht „Rollen verwalten“.")

    channel = (
        guild.get_channel(int(settings["verification_channel_id"]))
        if settings.get("verification_channel_id") else None
    )
    if settings.get("verification_channel_id") and channel is None:
        problems.append("Den Verifizierungs-Kanal gibt es nicht mehr.")
    elif channel is not None and me is not None and hasattr(channel, "permissions_for"):
        perms = channel.permissions_for(me)
        if not perms.send_messages:
            problems.append(f"Der Bot darf in #{channel.name} nicht schreiben.")
        if settings.get("delete_messages") and not perms.manage_messages:
            problems.append(
                "Ohne „Nachrichten verwalten“ bleiben fremde Nachrichten "
                f"in #{channel.name} stehen."
            )

    for key, label in (
        ("verified_role_id", "Verifiziert-Rolle"),
        ("unverified_role_id", "Unverifiziert-Rolle"),
    ):
        if not settings.get(key):
            continue
        role = guild.get_role(int(settings[key]))
        if role is None:
            problems.append(f"Die {label} gibt es nicht mehr.")
            continue
        problem = _role_problem(guild, role)
        if problem:
            problems.append(problem)

    for role_id in settings.get("verified_role_ids", [])[1:]:
        role = guild.get_role(int(role_id))
        if role is None:
            problems.append("Eine zusätzliche Verifiziert-Rolle gibt es nicht mehr.")
            continue
        problem = _role_problem(guild, role)
        if problem:
            problems.append(problem)

    log_id = settings.get("log_channel_id")
    if log_id and guild.get_channel(int(log_id)) is None:
        problems.append("Den Log-Kanal gibt es nicht mehr.")

    return problems


async def _reload(bot, guild_id: int) -> None:
    """
    Nudge the cog after a save.

    A wrong cog name here fails silently and looks exactly like "the
    dashboard saves but Discord ignores it", so the tests assert on it.
    """
    cog = bot.get_cog("Verification")
    if cog is not None and hasattr(cog, "refresh"):
        try:
            await cog.refresh(guild_id)
        except Exception:
            pass


def _owner_or_403(guild, actor: str):
    if not str(actor or "").isdigit() or int(actor) != int(getattr(guild, "owner_id", 0)):
        raise HTTPException(status_code=403, detail="Nur der tatsächliche Discord-Serverinhaber darf User Pull verwalten.")
    # Pull is entirely guild-scoped Premium: opening its data, enabling the
    # OAuth scope, configuring a target and moving members all use this one
    # guard. A UI lock alone would be bypassable with a direct API request.
    if not feature_gates.is_premium_guild(getattr(guild, "id", None)):
        raise HTTPException(status_code=402, detail="User Pull benötigt Premium auf diesem Server.")


async def _actor_can_access_target(guild, actor: int, bot) -> bool:
    member = guild.get_member(actor)
    perms = getattr(member, "guild_permissions", None)
    if (
        int(getattr(guild, "owner_id", 0)) == actor
        or bool(getattr(perms, "administrator", False))
        or bool(getattr(perms, "manage_guild", False))
    ):
        return True
    try:
        from api.routes.guild_access import check_access
        result = await check_access(guild.id, actor, bot)
        return bool(result.get("allowed"))
    except Exception:
        return False


async def _ensure_pull_tables(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS verification_pull_challenges ("
        " source_guild_id INTEGER PRIMARY KEY, target_guild_id INTEGER NOT NULL,"
        " role_id INTEGER, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,"
        " confirmed INTEGER DEFAULT 0, message_id INTEGER, channel_id INTEGER)"
    )
    async with db.execute("PRAGMA table_info(verification_pull_challenges)") as cursor:
        challenge_columns = {row[1] for row in await cursor.fetchall()}
    if "channel_id" not in challenge_columns:
        await db.execute("ALTER TABLE verification_pull_challenges ADD COLUMN channel_id INTEGER")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS verification_pull_events ("
        " source_guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
        " target_guild_id INTEGER NOT NULL, status TEXT NOT NULL,"
        " created_at TEXT NOT NULL, PRIMARY KEY (source_guild_id, user_id))"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS verification_pull_authorizations ("
        " source_guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
        " refresh_token_encrypted TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " scope TEXT DEFAULT 'guilds.join', last_checked TEXT,"
        " PRIMARY KEY (source_guild_id, user_id))"
    )
    async with db.execute("PRAGMA table_info(verification_pull_authorizations)") as cursor:
        auth_columns = {row[1] for row in await cursor.fetchall()}
    if "scope" not in auth_columns:
        await db.execute("ALTER TABLE verification_pull_authorizations ADD COLUMN scope TEXT DEFAULT 'guilds.join'")
    if "last_checked" not in auth_columns:
        await db.execute("ALTER TABLE verification_pull_authorizations ADD COLUMN last_checked TEXT")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS verification_pull_jobs ("
        " source_guild_id INTEGER PRIMARY KEY, target_guild_id INTEGER NOT NULL,"
        " status TEXT NOT NULL, total INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,"
        " succeeded INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, updated_at TEXT NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS verification_pull_audits ("
        " source_guild_id INTEGER PRIMARY KEY, status TEXT NOT NULL,"
        " total INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,"
        " authorized INTEGER DEFAULT 0, revoked INTEGER DEFAULT 0,"
        " updated_at TEXT NOT NULL)"
    )
    await db.commit()


def _oauth_token_key() -> bytes:
    secret = (os.getenv("OAUTH_TOKEN_SECRET") or os.getenv("DASHBOARD_API_KEY") or "").strip()
    if not secret:
        raise RuntimeError("OAUTH_TOKEN_SECRET or DASHBOARD_API_KEY is required")
    return hashlib.sha256(("university-pull:" + secret).encode()).digest()


def _token_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:length])


def _encrypt_refresh_token(token: str) -> str:
    key = _oauth_token_key()
    nonce = secrets.token_bytes(16)
    plain = token.encode()
    cipher = bytes(a ^ b for a, b in zip(plain, _token_keystream(key, nonce, len(plain))))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode()


def _decrypt_refresh_token(blob: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(blob.encode())
    except (ValueError, UnicodeError):
        return None
    if len(raw) < 48:
        return None
    nonce, tag, cipher = raw[:16], raw[16:48], raw[48:]
    key = _oauth_token_key()
    if not hmac.compare_digest(tag, hmac.new(key, nonce + cipher, hashlib.sha256).digest()):
        return None
    try:
        return bytes(a ^ b for a, b in zip(cipher, _token_keystream(key, nonce, len(cipher)))).decode()
    except UnicodeDecodeError:
        return None


async def _save_pull_authorization(db, source_id: int, user_id: int, refresh_token: str):
    encrypted = _encrypt_refresh_token(refresh_token)
    await db.execute(
        "INSERT OR REPLACE INTO verification_pull_authorizations"
        " (source_guild_id, user_id, refresh_token_encrypted, updated_at, scope, last_checked)"
        " VALUES (?, ?, ?, ?, 'guilds.join', ?)",
        (
            source_id, user_id, encrypted,
            datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()


def _schedule_on_bot_loop(coro) -> bool:
    """Schedule long Pull work on the bot's persistent loop.

    FastAPI test requests use short-lived event loops; attaching ten-minute
    tasks to those loops leaks pending tasks and can hang the suite. Production
    has the bot loop registered, which is exactly where Discord work belongs.
    """
    loop = get_bot_loop()
    if loop is None or loop.is_closed() or not loop.is_running():
        coro.close()
        return False
    asyncio.run_coroutine_threadsafe(coro, loop)
    return True


def _pull_code_hash(source_id: int, target_id: int, code: str) -> str:
    key = (os.getenv("DASHBOARD_API_KEY") or "local-pull-confirmation").encode()
    value = f"{source_id}:{target_id}:{code}".encode()
    return hmac.new(key, value, hashlib.sha256).hexdigest()


async def _record_pull_event(db, source_id: int, user_id: int, target_id: int, status: str):
    await _ensure_pull_tables(db)
    await db.execute(
        "INSERT OR REPLACE INTO verification_pull_events"
        " (source_guild_id, user_id, target_guild_id, status, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (source_id, user_id, target_id, status[:40], datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


@router.post("/oauth/complete", summary="Complete public OAuth verification")
async def complete_oauth_verification(
    data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Complete a verification using identity data fetched by our OAuth server.

    This endpoint is protected by the bot API key. It never accepts a role or
    success flag from the browser and never receives an OAuth access token.
    """
    raw_guild_id = str(data.get("guild_id") or "")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    raw_user_id = str(user.get("id") or "")
    oauth_guilds = data.get("guilds") if isinstance(data.get("guilds"), list) else []
    if not raw_guild_id.isdigit() or not raw_user_id.isdigit():
        raise HTTPException(status_code=400, detail="OAuth-Daten unvollständig.")
    guild_id = int(raw_guild_id)
    user_id = int(raw_user_id)
    if not guild_id or not user_id:
        raise HTTPException(status_code=400, detail="OAuth-Daten unvollständig.")

    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)
    base = {
        "guild_id": str(guild.id),
        "guild_name": guild.name,
        "guild_icon": str(guild.icon.url) if guild.icon else None,
    }
    if not settings.get("enabled") or not store.is_configured(settings):
        return {**base, "status": "error", "reason": "not_configured"}

    try:
        member = guild.get_member(user_id)
        if member is None:
            member = await run_on_bot_loop(guild.fetch_member(user_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return {**base, "status": "denied", "reason": "not_a_member", "blocked": []}

    oauth_memberships = {
        str(item.get("id")): str(item.get("name") or item.get("id"))[:100]
        for item in oauth_guilds if isinstance(item, dict) and str(item.get("id") or "").isdigit()
    }
    blocked_ids = set(settings.get("blacklisted_guild_ids") or [])
    matched_ids = sorted(blocked_ids.intersection(oauth_memberships))[:20] \
        if settings.get("server_blacklist_enabled") else []
    matched = [
        {"id": item, "name": oauth_memberships[item]} for item in matched_ids
    ]

    denial_reason = None
    if matched:
        denial_reason = "server_blacklist"
    else:
        created = getattr(member, "created_at", None)
        age_days = ((datetime.now(timezone.utc) - created).total_seconds() / 86400) \
            if created else 999999
        if store.account_too_young(settings, age_days):
            denial_reason = "account_too_young"

    if denial_reason:
        blocked_names = ", ".join(item["name"] for item in matched) or "—"
        if settings.get("blacklist_custom_message"):
            title = settings.get("blacklist_title") or "Verifizierung abgelehnt"
            description = settings.get("blacklist_text") or "Die Prüfung wurde abgelehnt."
        else:
            title = "Verifizierung blockiert — Server-Blacklist" if matched \
                else "Verifizierung abgelehnt"
            description = (
                "Deine Verifizierung auf **{server}** wurde abgelehnt, weil du Mitglied "
                "eines Servers bist, den das Serverteam eingeschränkt hat.\n\n"
                "Server: `{blocked_server}`\n\n"
                "**Diese Einschränkung wird ausschließlich von den Administratoren von "
                "{server} verwaltet. University Bot trifft keine eigene "
                "Moderationsentscheidung.**"
                if matched else
                "Dein Discord-Konto erfüllt das konfigurierte Mindestalter dieses Servers nicht."
            )
        description = store.render(
            description, server=guild.name, user_mention=member.mention,
            user_name=member.display_name, member_count=guild.member_count or 0,
            blocked_server=blocked_names,
        )
        denial_card = Panel(
            f"{bot_emoji.CROSS} {title}"[:256],
            description[:3800],
            "Bereitgestellt von University Bot",
            tone="error",
        )
        try:
            await run_on_bot_loop(member.send(view=denial_card))
        except (discord.Forbidden, discord.HTTPException):
            pass

        log_id = settings.get("blacklist_log_channel_id") or settings.get("log_channel_id")
        log_channel = guild.get_channel(int(log_id)) if log_id else None
        if log_channel and hasattr(log_channel, "send"):
            log_card = StatusCard(
                "OAuth2-Verifizierung abgelehnt",
                f"{member.mention} (`{member.id}`) wurde abgelehnt.\n"
                f"Grund: **{denial_reason}**\n"
                f"Treffer: **{blocked_names}**",
                tone="error",
            )
            try:
                await run_on_bot_loop(log_channel.send(view=log_card))
            except (discord.Forbidden, discord.HTTPException):
                pass
        return {**base, "status": "denied", "reason": denial_reason, "blocked": matched}

    configured_role_ids = settings.get("verified_role_ids", [])
    configured_roles = [guild.get_role(int(role_id)) for role_id in configured_role_ids]
    # The first role is the required primary role. A deleted or newly moved
    # optional extra role must not break verification for everybody; simply
    # skip extras the bot can no longer manage and keep assigning the primary.
    if not configured_roles or configured_roles[0] is None \
            or _role_problem(guild, configured_roles[0]):
        return {**base, "status": "error", "reason": "role_unavailable"}
    roles = [
        role for role in configured_roles
        if role is not None and not _role_problem(guild, role)
    ]
    try:
        missing_roles = [role for role in roles if role not in member.roles]
        if missing_roles:
            await run_on_bot_loop(
                member.add_roles(*missing_roles, reason="One-Click-Verifizierung (Discord OAuth2)")
            )
    except (discord.Forbidden, discord.HTTPException):
        return {**base, "status": "error", "reason": "role_unavailable"}

    role_names = ", ".join(role.name for role in roles)
    role_mentions = ", ".join(f"@{role.name}" for role in roles)

    pull_status = None
    # A stale enabled setting must never keep requesting or storing the
    # powerful guilds.join scope after Premium expired.
    if settings.get("user_pull_enabled") and feature_gates.is_premium_guild(guild.id):
        target_id = int(settings.get("user_pull_target_guild_id") or 0)
        refresh_token = str(data.get("refresh_token") or "")
        authorized = bool(data.get("guilds_join_authorized"))
        if not refresh_token or not authorized:
            pull_status = "scope_missing"
        else:
            # Verification only records the explicit authorization. Joining a
            # target is always a later, owner-triggered action from the Pull
            # member list. A storage problem must never make Verify fail.
            try:
                await _ensure_pull_tables(db)
                await _save_pull_authorization(db, guild.id, member.id, refresh_token)
                pull_status = "authorized"
            except Exception:
                # Never leave the shared SQLite connection inside a failed
                # transaction: the normal verification log below must still be
                # able to commit even when optional Pull persistence fails.
                try:
                    await db.rollback()
                except Exception:
                    pass
                pull_status = "authorization_store_failed"
        try:
            await _record_pull_event(db, guild.id, member.id, target_id, pull_status)
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    unverified_id = settings.get("unverified_role_id")
    if settings.get("remove_unverified_role") and unverified_id:
        unverified = guild.get_role(int(unverified_id))
        if unverified in member.roles:
            try:
                await run_on_bot_loop(
                    member.remove_roles(unverified, reason="OAuth2-verifiziert")
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    await store.log_verification(
        db, guild.id, member.id, "oauth",
        datetime.now(timezone.utc).isoformat(),
    )
    log_id = settings.get("log_channel_id")
    log_channel = guild.get_channel(int(log_id)) if log_id else None
    if log_channel and hasattr(log_channel, "send"):
        try:
            await run_on_bot_loop(log_channel.send(view=StatusCard(
                "OAuth2-Verifizierung erfolgreich",
                f"{member.mention} (`{member.id}`) hat **{role_names}** erhalten.",
                tone="success",
            )))
        except (discord.Forbidden, discord.HTTPException):
            pass

    if settings.get("dm_on_success"):
        text = store.render(
            settings.get("dm_success_text", ""), server=guild.name,
            user_mention=member.mention, user_name=member.display_name,
            role=role_mentions, member_count=guild.member_count or 0,
        )
        try:
            await run_on_bot_loop(member.send(view=StatusCard(
                "Verifizierung erfolgreich", text[:3800], tone="success"
            )))
        except (discord.Forbidden, discord.HTTPException):
            pass
    return {
        **base, "status": "success", "role_name": roles[0].name,
        "role_names": [role.name for role in roles], "pull_status": pull_status,
    }


@router.get("/{guild_id}/pull/targets", summary="Owner-only User Pull targets")
async def pull_targets(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    # Same set as the dashboard server picker: Discord owner/manage rights plus
    # explicit per-server dashboard grants. Never expose the bot's full fleet.
    try:
        from api.routes.guild_access import user_guilds as delegated_user_guilds
        delegated_entries = await delegated_user_guilds(int(actor), bot)
        delegated_ids = {int(item["id"]) for item in delegated_entries}
    except Exception:
        delegated_ids = set()
    targets = []
    for guild in bot.guilds:
        if guild.id == source.id:
            continue
        member = guild.get_member(int(actor))
        perms = getattr(member, "guild_permissions", None)
        discord_access = (
            int(getattr(guild, "owner_id", 0)) == int(actor)
            or bool(getattr(perms, "administrator", False))
            or bool(getattr(perms, "manage_guild", False))
        )
        if not discord_access and guild.id not in delegated_ids:
            continue
        roles = []
        for role in reversed(guild.roles):
            if role.is_default() or role.managed or _role_problem(guild, role):
                continue
            roles.append({"id": str(role.id), "name": role.name, "colour": _colour_of(role)})
        targets.append({
            "id": str(guild.id), "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None,
            "member_count": guild.member_count or 0,
            "system_channel": (
                {"id": str(guild.system_channel.id), "name": guild.system_channel.name}
                if guild.system_channel else None
            ),
            "roles": roles,
        })
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    active_challenge = None
    async with db.execute(
        "SELECT target_guild_id, expires_at, role_id FROM verification_pull_challenges"
        " WHERE source_guild_id = ? AND confirmed = 0", (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        try:
            expires = datetime.fromisoformat(row[1])
        except (TypeError, ValueError):
            expires = datetime.now(timezone.utc)
        if expires > datetime.now(timezone.utc):
            active_target = bot.get_guild(int(row[0]))
            active_role = active_target.get_role(int(row[2])) if active_target and row[2] else None
            active_challenge = {
                "target_guild_id": str(row[0]),
                "target_name": active_target.name if active_target else str(row[0]),
                "role_id": str(row[2]) if row[2] else None,
                "role_name": active_role.name if active_role else None,
                "expires_at": expires.isoformat(),
                "message": "Der Code wurde bereits gesendet.",
            }
    return {
        "owner_only": True, "targets": targets,
        "active_challenge": active_challenge,
    }


@router.post("/{guild_id}/pull/challenge/cancel", summary="Cancel unfinished Pull challenge")
async def cancel_pull_challenge(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    async with db.execute(
        "SELECT target_guild_id, channel_id, confirmed FROM verification_pull_challenges"
        " WHERE source_guild_id = ?", (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row and not row[2]:
        target = bot.get_guild(int(row[0]))
        channel = target.get_channel(int(row[1])) if target and row[1] else None
        if channel:
            try:
                await run_on_bot_loop(channel.delete(reason="User-Pull-Einrichtung neu gestartet"))
            except (discord.Forbidden, discord.HTTPException):
                pass
        await db.execute(
            "DELETE FROM verification_pull_challenges WHERE source_guild_id = ?",
            (guild_id,),
        )
        await db.commit()
    return {"status": "cancelled", "result": "Die offene Pull-Einrichtung wurde verworfen."}


@router.post("/{guild_id}/pull/challenge", summary="Send User Pull owner challenge")
async def create_pull_challenge(
    guild_id: int, data: dict, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    raw_target = str(data.get("target_guild_id") or "")
    if not raw_target.isdigit():
        raise HTTPException(status_code=400, detail="Wähle einen Zielserver.")
    target = _guild_or_404(bot, int(raw_target))
    if target.id == source.id or not await _actor_can_access_target(target, int(actor), bot):
        raise HTTPException(status_code=403, detail="Du hast keinen Dashboard-Zugriff auf den Zielserver.")

    role_id = None
    raw_role = str(data.get("role_id") or "")
    if raw_role:
        role = target.get_role(int(raw_role)) if raw_role.isdigit() else None
        if role is None:
            raise HTTPException(status_code=404, detail="Die Zielrolle gibt es nicht mehr.")
        problem = _role_problem(target, role)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        role_id = role.id

    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    now = datetime.now(timezone.utc)
    async with db.execute(
        "SELECT target_guild_id, expires_at, confirmed, channel_id"
        " FROM verification_pull_challenges WHERE source_guild_id = ?", (guild_id,),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing and not existing[2]:
        try:
            expires = datetime.fromisoformat(existing[1])
        except (TypeError, ValueError):
            expires = now
        if expires > now:
            return {
                "status": "already_sent", "expires_at": expires.isoformat(),
                "target_guild_id": str(existing[0]),
                "channel_id": str(existing[3]) if existing[3] else None,
                "message": "Der Code wurde bereits gesendet.",
            }
        old_target = bot.get_guild(int(existing[0]))
        old_channel = old_target.get_channel(int(existing[3])) if old_target and existing[3] else None
        if old_channel:
            try:
                await run_on_bot_loop(old_channel.delete(reason="User-Pull-Code abgelaufen"))
            except (discord.Forbidden, discord.HTTPException):
                pass

    owner_member = target.owner or target.get_member(int(target.owner_id))
    if owner_member is None:
        try:
            owner_member = await run_on_bot_loop(target.fetch_member(int(target.owner_id)))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            owner_member = None
    overwrites = {
        target.default_role: discord.PermissionOverwrite(view_channel=False),
        target.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if owner_member:
        overwrites[owner_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    actor_member = target.get_member(int(actor))
    if actor_member:
        overwrites[actor_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    try:
        channel = await run_on_bot_loop(target.create_text_channel(
            "university-pull-code", overwrites=overwrites,
            reason="Temporäre User-Pull-Bestätigung (10 Minuten)",
        ))
    except (discord.Forbidden, discord.HTTPException):
        raise HTTPException(status_code=403, detail="Der Bot darf keinen temporären Code-Kanal erstellen.")

    code = f"{secrets.randbelow(10000):04d}"
    expires = now + timedelta(minutes=10)
    await db.execute(
        "INSERT OR REPLACE INTO verification_pull_challenges"
        " (source_guild_id, target_guild_id, role_id, code_hash, expires_at, confirmed, message_id, channel_id)"
        " VALUES (?, ?, ?, ?, ?, 0, NULL, ?)",
        (guild_id, target.id, role_id, _pull_code_hash(guild_id, target.id, code), expires.isoformat(), channel.id),
    )
    await db.commit()

    owner_mention = getattr(getattr(target, "owner", None), "mention", f"<@{actor}>")
    card = Panel(
        f"{bot_emoji.WARNING} User Pull bestätigen",
        f"{owner_mention}\n\nUniversity Bot soll die ausdrücklich autorisierten Mitglieder "
        f"von **{source.name}** zu **{target.name}** hinzufügen.",
        f"### {bot_emoji.LOCK} Bestätigungscode\n`{code}`\n\n"
        "Trage diesen vierstelligen Code innerhalb von **10 Minuten** im Dashboard ein.",
        "Der Code kann nur einmal verwendet werden.",
        tone="warning",
    )
    try:
        message = await run_on_bot_loop(channel.send(view=card))
    except (discord.Forbidden, discord.HTTPException):
        await db.execute(
            "DELETE FROM verification_pull_challenges WHERE source_guild_id = ?",
            (guild_id,),
        )
        await db.commit()
        try:
            await run_on_bot_loop(channel.delete(reason="Code-Nachricht fehlgeschlagen"))
        except (discord.Forbidden, discord.HTTPException):
            pass
        raise HTTPException(status_code=403, detail="Der Bot darf nicht in den temporären Kanal schreiben.")
    await db.execute(
        "UPDATE verification_pull_challenges SET message_id = ? WHERE source_guild_id = ?",
        (message.id, guild_id),
    )
    await db.commit()

    async def delete_temporary_channel():
        await asyncio.sleep(600)
        current = target.get_channel(channel.id)
        if current:
            try:
                await run_on_bot_loop(current.delete(reason="User-Pull-Code nach 10 Minuten gelöscht"))
            except (discord.Forbidden, discord.HTTPException):
                pass
        try:
            await db.execute(
                "UPDATE verification_pull_challenges SET channel_id = NULL"
                " WHERE source_guild_id = ? AND channel_id = ?", (guild_id, channel.id),
            )
            await db.commit()
        except Exception:
            pass

    _schedule_on_bot_loop(delete_temporary_channel())
    return {
        "status": "sent", "expires_at": expires.isoformat(),
        "target_guild_id": str(target.id), "channel_id": str(channel.id),
        "message": "Temporärer Code-Kanal erstellt.",
    }


@router.post("/{guild_id}/pull/confirm", summary="Confirm User Pull challenge")
async def confirm_pull_challenge(
    guild_id: int, data: dict, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    code = str(data.get("code") or "").strip()
    target_id = str(data.get("target_guild_id") or "")
    if not target_id.isdigit() or not code.isdigit() or len(code) != 4:
        raise HTTPException(status_code=400, detail="Gib den vierstelligen Code ein.")
    target = _guild_or_404(bot, int(target_id))
    if not await _actor_can_access_target(target, int(actor), bot):
        raise HTTPException(status_code=403, detail="Der Dashboard-Zugriff auf den Zielserver fehlt.")

    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    async with db.execute(
        "SELECT role_id, code_hash, expires_at, confirmed, target_guild_id"
        " FROM verification_pull_challenges WHERE source_guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None or int(row[4]) != target.id:
        raise HTTPException(status_code=404, detail="Es wurde kein passender Code angefordert.")
    if row[3]:
        return {"status": "already_confirmed", "message": "User Pull ist bereits bestätigt."}
    if datetime.fromisoformat(row[2]) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Der Code ist abgelaufen. Fordere einen neuen an.")
    expected = _pull_code_hash(guild_id, target.id, code)
    if not hmac.compare_digest(expected, row[1]):
        raise HTTPException(status_code=400, detail="Der Code ist nicht korrekt.")
    if row[0]:
        role = target.get_role(int(row[0]))
        if role is None:
            raise HTTPException(status_code=410, detail="Die ausgewählte Zielrolle gibt es nicht mehr.")
        problem = _role_problem(target, role)
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    await store.save_settings(db, guild_id, {
        "user_pull_enabled": True,
        "user_pull_target_guild_id": target.id,
        "user_pull_role_id": row[0],
    })
    await db.execute(
        "UPDATE verification_pull_challenges SET confirmed = 1 WHERE source_guild_id = ?",
        (guild_id,),
    )
    async with db.execute(
        "SELECT user_id FROM verification_pull_authorizations"
        " WHERE source_guild_id = ? AND scope = 'guilds.join'",
        (guild_id,),
    ) as cursor:
        authorized_ids = [int(row[0]) for row in await cursor.fetchall()]
    await db.execute(
        "INSERT OR REPLACE INTO verification_pull_jobs"
        " (source_guild_id, target_guild_id, status, total, completed, succeeded, failed, updated_at)"
        " VALUES (?, ?, 'running', ?, 0, 0, 0, ?)",
        (guild_id, target.id, len(authorized_ids), datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()
    job_status = "running"
    if authorized_ids:
        if not _schedule_on_bot_loop(_run_pull_all_job(
            guild_id, int(actor), target.id, authorized_ids, bot,
        )):
            job_status = "failed"
            await db.execute(
                "UPDATE verification_pull_jobs SET status = 'failed', updated_at = ?"
                " WHERE source_guild_id = ?",
                (datetime.now(timezone.utc).isoformat(), guild_id),
            )
            await db.commit()
    else:
        job_status = "completed"
        await db.execute(
            "UPDATE verification_pull_jobs SET status = 'completed' WHERE source_guild_id = ?",
            (guild_id,),
        )
        await db.commit()
    return {
        "status": "confirmed", "job_status": job_status,
        "total": len(authorized_ids),
        "message": "Code bestätigt. Pull all wurde gestartet.",
    }


@router.post("/{guild_id}/pull/toggle", summary="Toggle User Pull OAuth scope")
async def toggle_user_pull(
    guild_id: int, data: dict, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    enabled = bool(data.get("enabled"))
    db = await db_manager.get_connection(store.DB_PATH)
    await store.save_settings(db, guild_id, {"user_pull_enabled": enabled})
    if not enabled:
        await _ensure_pull_tables(db)
        await db.execute(
            "DELETE FROM verification_pull_authorizations WHERE source_guild_id = ?",
            (guild_id,),
        )
        await db.execute(
            "UPDATE verification_pull_events SET status = 'authorization_revoked'"
            " WHERE source_guild_id = ? AND status = 'authorized'", (guild_id,),
        )
        await db.commit()
    return {
        "status": "enabled" if enabled else "disabled",
        "result": "User Pull aktiviert." if enabled else "User Pull deaktiviert.",
        "needs_target": enabled and not bool(
            (await store.get_settings(db, guild_id)).get("user_pull_target_guild_id")
        ),
    }


@router.post("/{guild_id}/pull/disable", summary="Disable User Pull")
async def disable_user_pull(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    return await toggle_user_pull(guild_id, {"enabled": False}, actor, bot)


@router.post("/{guild_id}/pull/members/{user_id}", summary="Manually pull an authorized member")
async def pull_authorized_member(
    guild_id: int, user_id: int, actor: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    settings = await store.get_settings(db, guild_id)
    if not settings.get("user_pull_enabled"):
        raise HTTPException(status_code=400, detail="Schalte User Pull zuerst ein.")
    target_id = int(settings.get("user_pull_target_guild_id") or 0)
    target = bot.get_guild(target_id) if target_id else None
    if target is None:
        raise HTTPException(status_code=400, detail="Bestätige zuerst einen Zielserver.")

    async with db.execute(
        "SELECT refresh_token_encrypted FROM verification_pull_authorizations"
        " WHERE source_guild_id = ? AND user_id = ? AND scope = 'guilds.join'", (guild_id, user_id),
    ) as cursor:
        authorization = await cursor.fetchone()
    if authorization is None:
        raise HTTPException(status_code=409, detail="Diese Person hat guilds.join noch nicht autorisiert.")
    try:
        refresh_token = _decrypt_refresh_token(authorization[0])
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Die Token-Verschlüsselung ist nicht konfiguriert.")
    if not refresh_token:
        raise HTTPException(status_code=409, detail="Die Autorisierung ist nicht mehr verwendbar.")

    client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Discord OAuth ist nicht konfiguriert.")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": client_id, "client_secret": client_secret,
                "grant_type": "refresh_token", "refresh_token": refresh_token,
            },
        ) as response:
            if response.status >= 400:
                if response.status in {400, 401}:
                    await db.execute(
                        "DELETE FROM verification_pull_authorizations"
                        " WHERE source_guild_id = ? AND user_id = ?", (guild_id, user_id),
                    )
                    await db.commit()
                    await _record_pull_event(db, guild_id, user_id, target_id, "authorization_expired")
                    raise HTTPException(status_code=409, detail="Die Person muss User Pull erneut autorisieren.")
                raise HTTPException(status_code=503, detail="Discord ist vorübergehend nicht erreichbar.")
            token_data = await response.json()
    access_token = str(token_data.get("access_token") or "")
    rotated_refresh = str(token_data.get("refresh_token") or refresh_token)
    scopes = str(token_data.get("scope") or "").split()
    if not access_token or "guilds.join" not in scopes:
        raise HTTPException(status_code=409, detail="Discord hat guilds.join nicht bestätigt.")

    payload = {"access_token": access_token}
    role_id = settings.get("user_pull_role_id")
    if role_id:
        role = target.get_role(int(role_id))
        problem = _role_problem(target, role) if role else "Die Zielrolle gibt es nicht mehr."
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        payload["roles"] = [str(role_id)]
    try:
        route = discord.http.Route(
            "PUT", "/guilds/{guild_id}/members/{user_id}",
            guild_id=target_id, user_id=user_id,
        )
        await run_on_bot_loop(bot.http.request(route, json=payload))
    except (discord.Forbidden, discord.HTTPException):
        await _record_pull_event(db, guild_id, user_id, target_id, "join_failed")
        raise HTTPException(status_code=409, detail="Discord konnte die Person nicht hinzufügen.")

    await _save_pull_authorization(db, guild_id, user_id, rotated_refresh)
    await _record_pull_event(db, guild_id, user_id, target_id, "joined")
    return {"status": "joined", "result": "Mitglied wurde erfolgreich gepullt."}


async def _run_pull_all_job(
    guild_id: int, actor: int, target_id: int, user_ids: list[int], bot,
):
    db = await db_manager.get_connection(store.DB_PATH)
    succeeded = failed = 0
    for completed, user_id in enumerate(user_ids, start=1):
        try:
            await pull_authorized_member(guild_id, user_id, str(actor), bot)
            succeeded += 1
        except Exception:
            failed += 1
        # Keep the OAuth and guild-join endpoints comfortably below burst
        # limits during large Pull-all runs.
        await asyncio.sleep(0.15)
        try:
            await db.execute(
                "UPDATE verification_pull_jobs SET completed = ?, succeeded = ?, failed = ?, updated_at = ?"
                " WHERE source_guild_id = ?",
                (completed, succeeded, failed, datetime.now(timezone.utc).isoformat(), guild_id),
            )
            await db.commit()
        except Exception:
            pass
    await db.execute(
        "UPDATE verification_pull_jobs SET status = 'completed', updated_at = ?"
        " WHERE source_guild_id = ?",
        (datetime.now(timezone.utc).isoformat(), guild_id),
    )
    await db.commit()


@router.get("/{guild_id}/pull/job", summary="Current Pull all progress")
async def pull_job(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    async with db.execute(
        "SELECT target_guild_id, status, total, completed, succeeded, failed, updated_at"
        " FROM verification_pull_jobs WHERE source_guild_id = ?", (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return {"job": None}
    return {"job": {
        "target_guild_id": str(row[0]), "status": row[1], "total": row[2],
        "completed": row[3], "succeeded": row[4], "failed": row[5],
        "updated_at": row[6],
    }}


async def _run_scope_audit(guild_id: int, authorizations: list[tuple[int, str]]):
    db = await db_manager.get_connection(store.DB_PATH)
    client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    authorized = revoked = 0
    if not client_id or not client_secret:
        await db.execute(
            "UPDATE verification_pull_audits SET status = 'failed', updated_at = ?"
            " WHERE source_guild_id = ?", (datetime.now(timezone.utc).isoformat(), guild_id),
        )
        await db.commit()
        return
    async with aiohttp.ClientSession() as session:
        for completed, (user_id, encrypted) in enumerate(authorizations, start=1):
            valid = True
            try:
                refresh_token = _decrypt_refresh_token(encrypted)
                if not refresh_token:
                    valid = False
                else:
                    async with session.post(
                        "https://discord.com/api/v10/oauth2/token",
                        data={
                            "client_id": client_id, "client_secret": client_secret,
                            "grant_type": "refresh_token", "refresh_token": refresh_token,
                        },
                    ) as response:
                        if response.status in {400, 401}:
                            valid = False
                        elif response.status < 400:
                            token_data = await response.json()
                            scopes = set(str(token_data.get("scope") or "").replace(",", " ").split())
                            valid = "guilds.join" in scopes
                            if valid and token_data.get("refresh_token"):
                                await _save_pull_authorization(
                                    db, guild_id, user_id, str(token_data["refresh_token"]),
                                )
                        # 429/5xx are temporary: retain the last known grant.
            except Exception:
                valid = True
            if valid:
                authorized += 1
                await db.execute(
                    "UPDATE verification_pull_events"
                    " SET status = CASE WHEN status = 'joined' THEN status ELSE 'authorized' END, created_at = ?"
                    " WHERE source_guild_id = ? AND user_id = ?",
                    (datetime.now(timezone.utc).isoformat(), guild_id, user_id),
                )
            else:
                revoked += 1
                await db.execute(
                    "DELETE FROM verification_pull_authorizations"
                    " WHERE source_guild_id = ? AND user_id = ?", (guild_id, user_id),
                )
                await db.execute(
                    "UPDATE verification_pull_events SET status = 'authorization_revoked', created_at = ?"
                    " WHERE source_guild_id = ? AND user_id = ?",
                    (datetime.now(timezone.utc).isoformat(), guild_id, user_id),
                )
                await db.commit()
            await db.execute(
                "UPDATE verification_pull_audits SET completed = ?, authorized = ?, revoked = ?, updated_at = ?"
                " WHERE source_guild_id = ?",
                (completed, authorized, revoked, datetime.now(timezone.utc).isoformat(), guild_id),
            )
            await db.commit()
            await asyncio.sleep(0.15)
    await db.execute(
        "UPDATE verification_pull_audits SET status = 'completed', updated_at = ?"
        " WHERE source_guild_id = ?", (datetime.now(timezone.utc).isoformat(), guild_id),
    )
    await db.commit()


@router.post("/{guild_id}/pull/authorizations/check", summary="Check guilds.join grants")
async def start_scope_audit(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    async with db.execute(
        "SELECT status FROM verification_pull_audits WHERE source_guild_id = ?",
        (guild_id,),
    ) as cursor:
        running = await cursor.fetchone()
    if running and running[0] == "running":
        return {"status": "running"}
    async with db.execute(
        "SELECT user_id, refresh_token_encrypted FROM verification_pull_authorizations"
        " WHERE source_guild_id = ? AND scope = 'guilds.join'", (guild_id,),
    ) as cursor:
        rows = [(int(row[0]), str(row[1])) for row in await cursor.fetchall()]
    status = "running" if rows else "completed"
    await db.execute(
        "INSERT OR REPLACE INTO verification_pull_audits"
        " (source_guild_id, status, total, completed, authorized, revoked, updated_at)"
        " VALUES (?, ?, ?, 0, 0, 0, ?)",
        (guild_id, status, len(rows), datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()
    if rows and not _schedule_on_bot_loop(_run_scope_audit(guild_id, rows)):
        status = "failed"
        await db.execute(
            "UPDATE verification_pull_audits SET status = 'failed' WHERE source_guild_id = ?",
            (guild_id,),
        )
        await db.commit()
    return {"status": status, "total": len(rows)}


@router.get("/{guild_id}/pull/authorizations/check", summary="guilds.join check progress")
async def scope_audit_status(
    guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await _ensure_pull_tables(db)
    async with db.execute(
        "SELECT status, total, completed, authorized, revoked FROM verification_pull_audits"
        " WHERE source_guild_id = ?", (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return {"audit": None if row is None else {
        "status": row[0], "total": row[1], "completed": row[2],
        "authorized": row[3], "revoked": row[4],
    }}


@router.get("/{guild_id}/pull/members", summary="Verified member list with Pull status")
async def pull_members(
    guild_id: int, actor: str = "", query: str = "", limit: int = 100, offset: int = 0,
    bot: "universitybot" = Depends(get_bot),
):
    source = _guild_or_404(bot, guild_id)
    _owner_or_403(source, actor)
    db = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(db)
    await _ensure_pull_tables(db)
    limit = min(5000, max(1, limit))
    offset = max(0, offset)
    async with db.execute(
        "SELECT l.user_id, MAX(l.verified_at) AS verified_at,"
        " CASE WHEN a.user_id IS NOT NULL AND a.scope = 'guilds.join'"
        " THEN COALESCE(e.status, 'authorized')"
        " WHEN e.status = 'authorization_revoked' THEN e.status ELSE 'not_requested' END,"
        " e.created_at FROM verification_logs l"
        " LEFT JOIN verification_pull_events e"
        " ON e.source_guild_id = l.guild_id AND e.user_id = l.user_id"
        " LEFT JOIN verification_pull_authorizations a"
        " ON a.source_guild_id = l.guild_id AND a.user_id = l.user_id"
        " WHERE l.guild_id = ? GROUP BY l.user_id"
        " ORDER BY verified_at DESC LIMIT ? OFFSET ?",
        (guild_id, limit, offset),
    ) as cursor:
        rows = await cursor.fetchall()
    members = []
    needle = query.casefold().strip()
    for row in rows:
        member = source.get_member(int(row[0]))
        name = getattr(member, "display_name", None) or getattr(member, "name", None) or "Server verlassen"
        if needle and needle not in name.casefold() and needle not in str(row[0]):
            continue
        members.append({
            "id": str(row[0]), "name": name,
            "username": getattr(member, "name", None),
            "avatar": str(member.display_avatar.url) if member else None,
            "verified_at": row[1], "pull_status": row[2] or "not_requested",
            "pulled_at": row[3], "left": member is None,
        })
    settings = await store.get_settings(db, guild_id)
    target = bot.get_guild(int(settings["user_pull_target_guild_id"])) \
        if settings.get("user_pull_target_guild_id") else None
    return {
        "members": members, "offset": offset, "limit": limit,
        "pull_enabled": settings.get("user_pull_enabled", False),
        "target": ({"id": str(target.id), "name": target.name} if target else None),
    }


@router.get("/{guild_id}", summary="Verification settings")
async def get_verification(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)
    guild = bot.get_guild(guild_id)

    panel_alive = None
    if settings.get("panel_message_id") and settings.get("panel_channel_id"):
        channel = (
            guild.get_channel(int(settings["panel_channel_id"])) if guild else None
        )
        panel_alive = channel is not None

    preview_role = "@Verifiziert"
    if guild and settings.get("verified_role_id"):
        role = guild.get_role(int(settings["verified_role_id"]))
        if role:
            preview_role = f"@{role.name}"

    def preview(key):
        return store.render(
            settings[key],
            server=guild.name if guild else "Dein Server",
            user_mention="@Lena", user_name="Lena", role=preview_role,
            member_count=guild.member_count if guild else 0,
        )

    return {
        "guild_id": str(guild_id),
        "guild_name": guild.name if guild else None,
        **{k: v for k, v in settings.items() if k not in store.ID_KEYS},
        **{k: (str(settings[k]) if settings[k] else None) for k in store.ID_KEYS},
        "pull_premium": feature_gates.is_premium_guild(guild_id),
        "user_pull_enabled": bool(settings.get("user_pull_enabled")) and feature_gates.is_premium_guild(guild_id),
        "channel_info": _channel_info(guild, settings["verification_channel_id"]),
        "role_info": _role_info(guild, settings["verified_role_id"]),
        "role_infos": [
            _role_info(guild, role_id) for role_id in settings.get("verified_role_ids", [])
        ],
        "log_channel_info": _channel_info(guild, settings["log_channel_id"]),
        "blacklist_log_channel_info": _channel_info(guild, settings["blacklist_log_channel_id"]),
        "unverified_role_info": _role_info(guild, settings["unverified_role_id"]),
        "methods": store.methods_for(settings),
        "configured": store.is_configured(settings),
        "panel_posted": panel_alive,
        "placeholders": store.PLACEHOLDERS,
        "preview": {
            "title": preview("panel_title"),
            "text": preview("panel_text"),
            "footer": preview("panel_footer"),
            "success": preview("success_text"),
            "dm_success": preview("dm_success_text"),
        },
        "verified_count": await store.count_verified(db, guild_id),
        "recent": [
            {**entry, "member": _member_card(guild, entry["user_id"])}
            for entry in await store.recent_logs(db, guild_id, 10)
        ],
        "warnings": _warnings(guild, settings),
    }


@router.patch("/{guild_id}", summary="Change the verification settings")
async def patch_verification(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    current = await store.get_settings(db, guild_id)

    protected_pull_keys = {
        "user_pull_enabled", "user_pull_target_guild_id", "user_pull_role_id",
    }
    if protected_pull_keys.intersection(data):
        raise HTTPException(
            status_code=403,
            detail="User Pull kann nur über die Inhaber-Bestätigung geändert werden.",
        )

    if data.get("verification_channel_id"):
        raw = str(data["verification_channel_id"])
        channel = guild.get_channel(int(raw)) if raw.isdigit() else None
        if channel is None:
            raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")
        if not hasattr(channel, "send"):
            raise HTTPException(
                status_code=400, detail="Die Verifizierung braucht einen Textkanal."
            )

    if "verified_role_ids" in data:
        role_ids = data["verified_role_ids"]
        if not isinstance(role_ids, list) or len(role_ids) > 3:
            raise HTTPException(status_code=400, detail="Du kannst höchstens drei Verifiziert-Rollen wählen.")
        role_ids = list(dict.fromkeys(str(item) for item in role_ids))
        for raw in role_ids:
            role = guild.get_role(int(raw)) if raw.isdigit() else None
            if role is None:
                raise HTTPException(status_code=404, detail="Eine der Verifiziert-Rollen gibt es nicht mehr.")
            problem = _role_problem(guild, role)
            if problem:
                raise HTTPException(status_code=400, detail=problem)
        data["verified_role_ids"] = role_ids
        data["verified_role_id"] = role_ids[0] if role_ids else None

    for key, label in (
        ("verified_role_id", "Verifiziert-Rolle"),
        ("unverified_role_id", "Unverifiziert-Rolle"),
    ):
        if not data.get(key):
            continue
        raw = str(data[key])
        role = guild.get_role(int(raw)) if raw.isdigit() else None
        if role is None:
            raise HTTPException(
                status_code=404, detail=f"Die {label} gibt es nicht mehr."
            )
        problem = _role_problem(guild, role)
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    if "verification_method" in data \
            and data["verification_method"] not in store.METHODS:
        raise HTTPException(
            status_code=400,
            detail="Die Verifizierung unterstützt ausschließlich Discord OAuth2.",
        )

    if "blacklisted_guild_ids" in data:
        blocked = data["blacklisted_guild_ids"]
        if not isinstance(blocked, list) or len(blocked) > 250:
            raise HTTPException(status_code=400, detail="Die Server-Blacklist ist ungültig.")
        if any(not str(item).isdigit() for item in blocked):
            raise HTTPException(status_code=400, detail="Server-IDs dürfen nur Ziffern enthalten.")

    if data.get("blacklist_log_channel_id"):
        raw = str(data["blacklist_log_channel_id"])
        channel = guild.get_channel(int(raw)) if raw.isdigit() else None
        if channel is None or not hasattr(channel, "send"):
            raise HTTPException(status_code=404, detail="Den Blacklist-Logkanal gibt es nicht mehr.")

    # Switching it on without the two things it needs would look broken.
    if data.get("enabled"):
        channel_id = data.get("verification_channel_id") \
            or current["verification_channel_id"]
        role_id = (
            (data.get("verified_role_ids") or [None])[0]
            if "verified_role_ids" in data
            else data.get("verified_role_id") or current["verified_role_id"]
        )
        if not channel_id or not role_id:
            raise HTTPException(
                status_code=400,
                detail="Wähle zuerst einen Kanal und eine Rolle.",
            )

    for key in store.TEXT_KEYS:
        if key in data and not str(data[key] or "").strip():
            raise HTTPException(
                status_code=400, detail=f"„{key}“ darf nicht leer sein."
            )

    for key in store.INT_KEYS:
        if key not in data:
            continue
        try:
            value = int(data[key])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"„{key}“ muss eine Zahl sein.")
        if value < 0:
            raise HTTPException(status_code=400, detail=f"„{key}“ kann nicht negativ sein.")

    settings = await store.save_settings(db, guild_id, data)
    await _reload(bot, guild_id)

    await feature_audit.log_action(
        "verification_saved", actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=", ".join(sorted(k for k in data if k != "actor")),
    )
    return {
        "status": "success",
        "result": "Gespeichert.",
        "warnings": _warnings(guild, settings),
    }


@router.post("/{guild_id}/panel", summary="Post or refresh the panel")
async def post_panel(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not store.is_configured(settings):
        raise HTTPException(
            status_code=400,
            detail="Es fehlt noch ein Kanal oder eine Rolle.",
        )

    channel = guild.get_channel(int(settings["verification_channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Den Kanal gibt es nicht mehr.")

    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        raise HTTPException(
            status_code=503, detail="Das Verifizierungs-Modul ist nicht geladen."
        )

    role = guild.get_role(int(settings["verified_role_id"]))
    settings["verified_count"] = await store.count_verified(db, guild_id)
    view = cog.build_panel(guild, settings, role)

    message = None
    if settings.get("panel_message_id") and settings.get("panel_channel_id"):
        old = guild.get_channel(int(settings["panel_channel_id"]))
        if old is not None:
            try:
                message = await old.fetch_message(int(settings["panel_message_id"]))
                await message.edit(view=view)
            except discord.NotFound:
                message = None
            except discord.Forbidden:
                message = None

    if message is None:
        try:
            message = await channel.send(view=view)
        except discord.Forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
            )
        except discord.HTTPException as exc:
            raise HTTPException(status_code=502, detail=f"Discord lehnte ab: {exc}")

        await store.save_settings(db, guild_id, {
            "panel_message_id": message.id, "panel_channel_id": channel.id,
        })

    await _reload(bot, guild_id)
    return {"status": "success", "result": f"Panel in #{channel.name} gepostet."}


@router.post("/{guild_id}/preview", summary="Preview the panel privately")
async def preview_panel(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """
    Send the panel as it would look, without replacing the live one.

    Uses the cog's own renderer so what is previewed is what gets
    posted -- a second implementation is how a preview starts lying.
    """
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    # Preview whatever is in the form, not only what is saved.
    settings = store.normalise({**settings, **{
        k: v for k, v in (data or {}).items() if k in store.DEFAULTS
    }})

    raw = str(data.get("channel_id") or settings.get("verification_channel_id") or "")
    channel = guild.get_channel(int(raw)) if raw.isdigit() else None
    if channel is None:
        raise HTTPException(status_code=400, detail="Wähle einen Kanal für die Vorschau.")

    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        raise HTTPException(
            status_code=503, detail="Das Verifizierungs-Modul ist nicht geladen."
        )

    role = (
        guild.get_role(int(settings["verified_role_id"]))
        if settings.get("verified_role_id") else None
    )
    settings["verified_count"] = await store.count_verified(db, guild_id)
    try:
        await channel.send(view=cog.build_panel(guild, settings, role, preview=True))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=502, detail=f"Discord lehnte ab: {exc}")

    return {
        "status": "success",
        "result": f"Vorschau in #{channel.name} — die Knöpfe sind dort ohne Funktion.",
    }


@router.post("/{guild_id}/reset", summary="Switch verification off")
async def reset_verification(
    guild_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    keep_texts = True
    if isinstance(data, dict):
        keep_texts = bool(data.get("keep_texts", True))

    db = await db_manager.get_connection(store.DB_PATH)
    updates = {"enabled": False, "panel_message_id": None, "panel_channel_id": None}
    if not keep_texts:
        updates.update({key: store.DEFAULTS[key] for key in store.TEXT_KEYS})

    await store.save_settings(db, guild_id, updates)
    await _reload(bot, guild_id)

    return {
        "status": "success",
        "result": (
            "Ausgeschaltet. Deine Texte bleiben gespeichert."
            if keep_texts else "Ausgeschaltet und Texte zurückgesetzt."
        ),
    }


@router.delete("/{guild_id}/verify/{user_id}", summary="Take the role back")
async def unverify_member(
    guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)
):
    """Undo a verification -- the obvious companion to doing it by hand."""
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not settings.get("verified_role_id"):
        raise HTTPException(status_code=400, detail="Es ist keine Rolle gesetzt.")

    member = guild.get_member(user_id)
    if member is None:
        raise HTTPException(
            status_code=404, detail="Die Person ist nicht mehr auf dem Server."
        )

    roles = [
        guild.get_role(int(role_id))
        for role_id in settings.get("verified_role_ids", [])
    ]
    roles = [role for role in roles if role is not None and role in member.roles]
    if not roles:
        return {
            "status": "success",
            "result": f"{member.display_name} hatte keine Verifiziert-Rolle.",
        }

    try:
        await member.remove_roles(*roles, reason="Verifizierung über das Dashboard entzogen")
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail="Der Bot darf mindestens eine Verifiziert-Rolle nicht entfernen."
        )

    return {
        "status": "success",
        "result": f"{member.display_name} ist nicht mehr verifiziert.",
    }


@router.post("/{guild_id}/verify/{user_id}", summary="Verify somebody by hand")
async def verify_member(
    guild_id: int, user_id: int, data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    guild = _guild_or_404(bot, guild_id)
    db = await db_manager.get_connection(store.DB_PATH)
    settings = await store.get_settings(db, guild_id)

    if not settings.get("verified_role_id"):
        raise HTTPException(status_code=400, detail="Es ist keine Rolle gesetzt.")

    member = guild.get_member(user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Die Person ist nicht auf dem Server.")

    roles = [
        guild.get_role(int(role_id))
        for role_id in settings.get("verified_role_ids", [])
    ]
    if not roles or any(role is None for role in roles):
        raise HTTPException(status_code=404, detail="Eine Verifiziert-Rolle gibt es nicht mehr.")
    for role in roles:
        problem = _role_problem(guild, role)
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    missing_roles = [role for role in roles if role not in member.roles]
    if not missing_roles:
        return {"status": "success", "result": f"{member.display_name} war schon verifiziert."}

    try:
        await member.add_roles(*missing_roles, reason="Verifizierung über das Dashboard")
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail="Der Bot darf mindestens eine Verifiziert-Rolle nicht vergeben."
        )

    await store.log_verification(
        db, guild_id, user_id, "manual",
        datetime.now(timezone.utc).isoformat(),
    )
    return {"status": "success", "result": f"{member.display_name} ist jetzt verifiziert."}
