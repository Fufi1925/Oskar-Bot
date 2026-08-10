"""
Dashboard user management.

Answers the question "who can get into my dashboard, and how?" — and lets the
owner throw somebody out.

A person can reach the dashboard through three different doors:

    owner      listed in OWNER_IDS / ADMIN_IDS or in the dashboard_owners table
    team role  holds one of the 40 dashboard roles
    Discord    has Manage Server / Administrator on a guild the bot is in

The third door is the reason a plain "remove all roles" button is not enough:
that access comes from Discord, not from us. `dashboard_bans` is an explicit
deny-list that overrides all three.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import dashboard_access as access
from utils import dashboard_authority as authority
from utils import dashboard_roles as roles
from utils import feature_audit
from utils import feature_gates
from utils import user_actions
from utils import user_lookup

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8


def _decorate_user(bot, user_id: str) -> dict:
    """Name and avatar for a Discord ID, as far as the bot knows them."""
    user = None
    if str(user_id).isdigit():
        user = bot.get_user(int(user_id))
    return {
        "username": str(user) if user else None,
        "display_name": getattr(user, "display_name", None) if user else None,
        "avatar": str(user.display_avatar.url) if user else None,
    }


def _guild_admin_map(bot) -> dict[str, list[dict]]:
    """
    user_id -> guilds where that user has Manage Server or Administrator.

    Built from the member cache, so it only covers guilds the bot can see. That
    is exactly the set of guilds the dashboard can manage anyway.
    """
    result: dict[str, list[dict]] = {}
    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue
            perms = member.guild_permissions
            is_owner_of_guild = member.id == guild.owner_id
            if not (is_owner_of_guild or perms.administrator or perms.manage_guild):
                continue
            result.setdefault(str(member.id), []).append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "is_guild_owner": is_owner_of_guild,
                    "administrator": bool(perms.administrator),
                    "manage_guild": bool(perms.manage_guild),
                }
            )
    return result


# ── Overview ──────────────────────────────────────────────────────────────


@router.get("/users", summary="Everyone who authorised the bot via OAuth")
async def list_users(
    include_discord: bool = False,
    bot: "universitybot" = Depends(get_bot),
):
    """
    The people who actually signed in to this dashboard with Discord OAuth.

    That is the list you can act on: they exist because they clicked
    "Authorise", so banning one of them means something. Owners and team-role
    holders are folded in because they are the accounts that matter most, even
    before their first sign-in.

    Discord server admins are NOT included by default. There are hundreds of
    them across the servers the bot is in, they never authorised anything, and
    listing them buried the handful of real dashboard users. Pass
    `include_discord=true` to see them anyway.
    """
    await roles.load()
    await access.load()

    users: dict[str, dict] = {}

    def entry(user_id: str) -> dict:
        uid = str(user_id)
        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "sources": [],
                "is_owner": False,
                "owner_kind": None,
                "roles": [],
                "highest_rank": 0,
                "permission_count": 0,
                "guild_admin_of": [],
                "first_seen": 0,
                "last_seen": 0,
                "login_count": 0,
                "banned": False,
                "ban": None,
                "username": None,
                "display_name": None,
                "avatar": None,
                "authorised": False,
            }
        return users[uid]

    # 1. People who actually authorised the bot and signed in. This is the
    #    primary list; everything else only annotates it.
    for login in await access.list_logins(2000):
        row = entry(login["user_id"])
        row["sources"].append("login")
        row["authorised"] = True
        row["first_seen"] = login["first_seen"]
        row["last_seen"] = login["last_seen"]
        row["login_count"] = login["login_count"]
        row["last_path"] = login["last_path"]
        if login.get("username"):
            row["username"] = login["username"]
        if login.get("avatar"):
            row["avatar"] = login["avatar"]

    # 2. Owners and dashboard admins — shown even before a first sign-in,
    #    because locking yourself out by not seeing them would be worse.
    for record in roles.list_owners():
        row = entry(record["user_id"])
        row["sources"].append("owner")
        row["is_owner"] = True
        row["owner_kind"] = record.get("kind", "admin")
        row["owner_note"] = record.get("note", "")
        row["owner_source"] = record.get("source", "")

    # 3. Dashboard team roles, same reasoning.
    for member in roles.all_members():
        row = entry(member["user_id"])
        row["sources"].append("team_role")
        row["roles"] = member.get("roles", [])
        row["highest_rank"] = member.get("highest_rank", 0)
        row["permission_count"] = member.get("permission_count", 0)

    # 4. Anyone banned stays visible so the ban can be lifted again, even if
    #    their login record was deleted in the meantime.
    for ban_entry in access.list_bans(include_expired=False):
        entry(ban_entry["user_id"])["sources"].append("banned")

    # 5. Discord server admins, only when explicitly asked for.
    if include_discord:
        for user_id, guilds in _guild_admin_map(bot).items():
            row = entry(user_id)
            row["sources"].append("discord_admin")
            row["guild_admin_of"] = guilds
    else:
        # Still annotate the people we do show, so the UI can warn that a ban
        # does not touch their rights inside Discord itself.
        admin_map = _guild_admin_map(bot)
        for uid, row in users.items():
            if uid in admin_map:
                row["guild_admin_of"] = admin_map[uid]

    # 6. Bans and Discord identities
    for uid, row in users.items():
        ban = access.get_ban(uid)
        row["banned"] = ban is not None
        row["ban"] = ban
        row["sources"] = sorted(set(row["sources"]))

        info = _decorate_user(bot, uid)
        for key, value in info.items():
            if value and not row.get(key):
                row[key] = value

    ordered = sorted(
        users.values(),
        key=lambda u: (
            not u["banned"],          # banned first, they need attention
            -u["highest_rank"],
            -(u["last_seen"] or 0),
        ),
    )

    return {
        "users": ordered,
        "count": len(ordered),
        "authorised_count": sum(1 for u in ordered if u["authorised"]),
        "banned_count": sum(1 for u in ordered if u["banned"]),
        "owner_count": sum(1 for u in ordered if u["is_owner"]),
        "role_count": sum(1 for u in ordered if u["roles"]),
        "discord_admin_count": sum(1 for u in ordered if u["guild_admin_of"]),
        "includes_discord_admins": include_discord,
    }


@router.get("/users/{user_id}", summary="Everything about one dashboard user")
async def get_user(user_id: str, bot: "universitybot" = Depends(get_bot)):
    await roles.load()
    await access.load()

    permissions = sorted(roles.get_permissions(user_id))
    login = await access.get_login(user_id)
    ban = access.get_ban(user_id)

    guild_admin_of = _guild_admin_map(bot).get(str(user_id), [])

    # Which guilds this person can actually open in the dashboard.
    #
    # Two doors lead in and both have to be counted: a dashboard role, and
    # Manage Server on Discord. Looking at roles alone reported "reaches
    # nothing" for a server admin who very much reaches their own server.
    scoped = roles.accessible_guilds(user_id)
    reachable: list[dict] = []

    if scoped is None:
        # Owner, or a role with no guild restriction: everywhere.
        reachable = [
            {"guild_id": str(g.id), "guild_name": g.name, "via": "dashboard role"}
            for g in bot.guilds
        ]
        reachable_reason = "unrestricted"
    else:
        seen: set[str] = set()
        for gid in sorted(scoped):
            guild = bot.get_guild(int(gid)) if gid.isdigit() else None
            reachable.append(
                {
                    "guild_id": gid,
                    "guild_name": guild.name if guild else "Unknown",
                    "via": "dashboard role",
                }
            )
            seen.add(gid)

        for entry in guild_admin_of:
            if entry["guild_id"] in seen:
                continue
            reachable.append(
                {
                    "guild_id": entry["guild_id"],
                    "guild_name": entry["guild_name"],
                    "via": "guild owner" if entry["is_guild_owner"] else "Discord admin",
                }
            )
            seen.add(entry["guild_id"])

        if scoped and guild_admin_of:
            reachable_reason = "role scope + Discord permissions"
        elif scoped:
            reachable_reason = "role scope"
        elif guild_admin_of:
            reachable_reason = "Discord permissions"
        else:
            reachable_reason = "no access"

    return {
        "user_id": str(user_id),
        **_decorate_user(bot, user_id),
        "is_owner": roles.is_owner(user_id),
        "can_manage_owners": roles.can_manage_owners(user_id),
        "highest_rank": roles.highest_rank(user_id),
        "roles": [
            {
                "key": a.role_key,
                "label": roles.ROLES_BY_KEY[a.role_key].label,
                "color": roles.ROLES_BY_KEY[a.role_key].color,
                "rank": roles.ROLES_BY_KEY[a.role_key].rank,
                "guild_ids": list(a.guild_ids),
                "granted_by": a.granted_by,
                "granted_at": a.granted_at,
                "note": a.note,
            }
            for a in roles.get_assignments(user_id)
            if a.role_key in roles.ROLES_BY_KEY
        ],
        "permissions": permissions,
        "permission_count": len(permissions),
        "login": login,
        "banned": ban is not None,
        "ban": ban,
        "guild_admin_of": guild_admin_of,
        "reachable_guilds": reachable,
        "reachable_reason": reachable_reason,
    }


# ── Bans ──────────────────────────────────────────────────────────────────


@router.get("/bans", summary="Everyone banned from the dashboard")
async def list_bans(include_expired: bool = False, bot: "universitybot" = Depends(get_bot)):
    await access.load()
    entries = access.list_bans(include_expired=include_expired)
    for entry in entries:
        entry.update(_decorate_user(bot, entry["user_id"]))
        by = entry.get("banned_by")
        entry["banned_by_name"] = _decorate_user(bot, by)["username"] if by else None
    return {"bans": entries, "count": len(entries)}


@router.post("/bans", summary="Ban a user from the dashboard")
async def create_ban(data: dict, bot: "universitybot" = Depends(get_bot)):
    actor = str(data.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")

    await roles.load()
    await access.load()

    user_id = str(data.get("user_id", "")).strip()
    if not user_id.isdigit() or not 15 <= len(user_id) <= 20:
        raise HTTPException(status_code=400, detail="user_id must be a valid Discord ID.")

    if user_id == actor:
        raise HTTPException(status_code=400, detail="You cannot ban yourself.")

    # An owner must never be lockable out of their own dashboard. This covers
    # the Discord application owner too, not just OWNER_IDS.
    if authority.is_owner(bot, user_id):
        raise HTTPException(
            status_code=403,
            detail="This user is an owner or dashboard admin. Remove that access first.",
        )

    # Banning is global, so a single server's admin must not be able to do it.
    if not authority.is_owner(bot, actor):
        if not roles.has_permission(actor, "team.assign"):
            raise HTTPException(status_code=403, detail="You may not ban dashboard users.")
        if roles.highest_rank(user_id) >= roles.highest_rank(actor):
            raise HTTPException(status_code=403, detail="This user is at or above your own rank.")

    try:
        duration = int(data.get("duration_seconds", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    duration = max(0, min(duration, 60 * 60 * 24 * 3650))  # cap at 10 years

    reason = str(data.get("reason", "")).strip()

    # Optionally strip their roles too, so the ban survives being lifted later
    # without silently handing back old privileges.
    removed_roles = 0
    if bool(data.get("revoke_roles", False)):
        removed_roles = await roles.revoke_all(user_id)

    try:
        record = await access.ban(
            user_id, banned_by=actor, reason=reason, duration_seconds=duration
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await feature_audit.log_action(
        "dashboard_user_banned",
        actor=actor,
        detail=f"{user_id}"
        + (f" for {duration}s" if duration else " permanently")
        + (f": {reason}" if reason else "")
        + (f" (+{removed_roles} roles revoked)" if removed_roles else ""),
    )

    return {"status": "success", "ban": record, "revoked_roles": removed_roles}


@router.delete("/bans/{user_id}", summary="Lift a dashboard ban")
async def delete_ban(
    user_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    if not actor:
        raise HTTPException(status_code=400, detail="actor query parameter is required.")

    await roles.load()
    await access.load()

    if not authority.may_act_globally(bot, actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage dashboard bans.")

    removed = await access.unban(user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="This user is not banned.")

    await feature_audit.log_action(
        "dashboard_user_unbanned", actor=actor, detail=f"{user_id}"
    )
    return {"status": "success", "user_id": str(user_id)}


@router.post("/bans/purge", summary="Delete expired ban entries")
async def purge_bans(data: dict, bot: "universitybot" = Depends(get_bot)):
    actor = str(data.get("actor", "")).strip()
    await roles.load()
    if not authority.may_act_globally(bot, actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage dashboard bans.")

    removed = await access.purge_expired()
    return {"status": "success", "removed": removed}


# ── Logins ────────────────────────────────────────────────────────────────


@router.get("/logins", summary="Dashboard sign-in history")
async def list_logins(limit: int = 200, bot: "universitybot" = Depends(get_bot)):
    entries = await access.list_logins(limit)
    await access.load()
    for entry in entries:
        info = _decorate_user(bot, entry["user_id"])
        for key, value in info.items():
            if value and not entry.get(key):
                entry[key] = value
        entry["banned"] = access.is_banned(entry["user_id"])
    return {"logins": entries, "count": len(entries)}


@router.post("/logins", summary="Record a dashboard sign-in")
async def create_login(data: dict):
    """
    Called by the dashboard's NextAuth callback. Also reports back whether the
    user is banned, so the sign-in can be refused right there.
    """
    user_id = str(data.get("user_id", "")).strip()
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="user_id must be a Discord ID.")

    await access.load()
    banned = access.is_banned(user_id)
    grund = ""

    # Die Bot-Sperre aus dem Admin-Dashboard sperrt auch hier aus.
    # Vorher waren das zwei getrennte Systeme: die user_blacklist
    # blockte nur Befehle im Discord, der Login lief weiter durch --
    # ein gesperrter Nutzer konnte sich also weiter einloggen. Gemessen
    # in repro/check_blacklist_reach.py.
    if not banned:
        bot_ban = await user_lookup.get_ban(user_id)
        if bot_ban:
            banned = True
            grund = bot_ban.get("reason", "")

    if not banned:
        await access.record_login(
            user_id,
            username=str(data.get("username", ""))[:100],
            avatar=str(data.get("avatar", ""))[:300],
            new_session=bool(data.get("new_session", True)),
            path=str(data.get("path", ""))[:200],
        )

    return {
        "status": "success",
        "banned": banned,
        "ban": access.get_ban(user_id) or ({"reason": grund} if grund else None),
    }


@router.delete("/logins/{user_id}", summary="Forget a sign-in record")
async def delete_login(
    user_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    await roles.load()
    if not authority.may_act_globally(bot, actor, "team.assign"):
        raise HTTPException(status_code=403, detail="You may not manage login records.")

    removed = await access.forget_login(user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No record for this user.")
    return {"status": "success", "user_id": str(user_id)}


@router.get("/check/{user_id}", summary="Is this user banned?")
async def check_user(user_id: str):
    """Cheap endpoint used by the dashboard middleware on every request."""
    await access.load()
    ban = access.get_ban(user_id)

    # Auch hier die Bot-Sperre mitpruefen. Ohne das kaeme jemand mit
    # einer bestehenden Sitzung weiter ins Dashboard -- der Login wird
    # ja nur einmal geprueft, diese Route bei jedem Aufruf.
    if ban is None:
        bot_ban = await user_lookup.get_ban(user_id)
        if bot_ban:
            return {
                "user_id": str(user_id),
                "banned": True,
                "reason": bot_ban.get("reason", "") or "Vom Bot gesperrt.",
                "expires_at": 0,
                "checked_at": int(time.time()),
            }

    return {
        "user_id": str(user_id),
        "banned": ban is not None,
        "reason": (ban or {}).get("reason", ""),
        "expires_at": (ban or {}).get("expires_at", 0),
        "checked_at": int(time.time()),
    }


# ══════════════════════════════════════════════════════════════════════
#  Nutzer nachschlagen und Massnahmen ergreifen
# ══════════════════════════════════════════════════════════════════════
#
#  Alles hier verlangt `blacklist.manage` oder Inhaberschaft. Die
#  Uebersicht zeigt JEDEN gemeinsamen Server einer Person, auch die, auf
#  die der Betrachter sonst keinen Zugriff hat -- das ist der Sinn der
#  Sache und zugleich der Grund fuer die strenge Pruefung.


def _require_global(bot, actor: str, was: str) -> None:
    if not authority.may_act_globally(bot, actor, "blacklist.manage"):
        raise HTTPException(status_code=403, detail=f"Du darfst {was} nicht.")


def _valid_id(user_id: str) -> int:
    uid = str(user_id).strip()
    if not uid.isdigit() or not 15 <= len(uid) <= 20:
        raise HTTPException(
            status_code=400, detail="Das ist keine gueltige Discord-ID."
        )
    return int(uid)


@router.get("/lookup/{user_id}", summary="Alles zu einer Nutzer-ID")
async def lookup_user(
    user_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    await roles.load()
    _require_global(bot, actor, "Nutzer nachschlagen")
    return await user_lookup.lookup(bot, _valid_id(user_id))


@router.get("/bot-bans", summary="Wer ist vom Bot gesperrt")
async def list_bot_bans(actor: str = "", bot: "universitybot" = Depends(get_bot)):
    await roles.load()
    _require_global(bot, actor, "die Sperrliste sehen")

    eintraege = await user_lookup.list_bans()
    for eintrag in eintraege:
        eintrag.update(_decorate_user(bot, eintrag["user_id"]))
    return {"bans": eintraege, "count": len(eintraege)}


@router.post("/bot-bans", summary="Jemanden komplett vom Bot sperren")
async def create_bot_ban(data: dict, bot: "universitybot" = Depends(get_bot)):
    actor = str(data.get("actor", "")).strip()
    await roles.load()
    _require_global(bot, actor, "jemanden sperren")

    uid = _valid_id(str(data.get("user_id", "")))

    # Sich selbst oder einen Inhaber auszusperren waere ein Fehler, den
    # man nicht mehr rueckgaengig machen kann, wenn es der letzte war.
    if str(uid) == actor:
        raise HTTPException(status_code=400, detail="Du kannst dich nicht selbst sperren.")
    if authority.is_owner(bot, str(uid)):
        raise HTTPException(
            status_code=400, detail="Inhaber des Bots lassen sich nicht sperren."
        )

    ergebnis = await user_lookup.ban_from_bot(
        uid,
        reason=str(data.get("reason", "")),
        actor=actor,
        note=str(data.get("note", "")),
    )

    # Der Zwischenspeicher der Befehlspruefung muss neu geladen werden,
    # sonst greift die Sperre erst nach einem Neustart.
    feature_gates.invalidate_blacklist()
    await feature_gates.refresh_blacklist()

    await feature_audit.log_action(
        "bot_ban_added", actor=actor, detail=f"{uid}: {ergebnis['reason']}"
    )
    return {"status": "success", **ergebnis}


@router.delete("/bot-bans/{user_id}", summary="Bot-Sperre aufheben")
async def delete_bot_ban(
    user_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    await roles.load()
    _require_global(bot, actor, "Sperren aufheben")

    entfernt = await user_lookup.unban_from_bot(_valid_id(user_id))
    if not entfernt:
        raise HTTPException(status_code=404, detail="Diese Person ist nicht gesperrt.")

    feature_gates.invalidate_blacklist()
    await feature_gates.refresh_blacklist()

    await feature_audit.log_action("bot_ban_removed", actor=actor, detail=str(user_id))
    return {"status": "success", "user_id": str(user_id)}


@router.post("/mass-action", summary="Bann auf allen Servern oder Warnung an die Inhaber")
async def mass_action(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Zwei Massnahmen, beide bewusst umstaendlich auszuloesen.

    ``dry_run`` fuehrt nichts aus und meldet nur, was passieren wuerde.
    Die Oberflaeche fragt das zuerst ab, damit die Zahl im
    Bestaetigungsdialog stimmt statt geschaetzt zu sein.
    """
    actor = str(data.get("actor", "")).strip()
    await roles.load()
    _require_global(bot, actor, "diese Massnahme ausfuehren")

    uid = _valid_id(str(data.get("user_id", "")))
    kind = str(data.get("kind", "")).strip()
    if kind not in {"ban_all", "warn_owners"}:
        raise HTTPException(
            status_code=400, detail="kind muss 'ban_all' oder 'warn_owners' sein."
        )

    dry_run = bool(data.get("dry_run", False))
    reason = str(data.get("reason", "")).strip()

    # Ein Bann ohne Begruendung ist spaeter nicht mehr nachvollziehbar --
    # und steht so auch im Auditlog von Discord.
    if not dry_run and not reason:
        raise HTTPException(status_code=400, detail="Ein Grund ist erforderlich.")

    if kind == "ban_all":
        if str(uid) == actor:
            raise HTTPException(
                status_code=400, detail="Du kannst dich nicht selbst ueberall bannen."
            )
        if authority.is_owner(bot, str(uid)):
            raise HTTPException(
                status_code=400, detail="Inhaber des Bots lassen sich nicht bannen."
            )
        ergebnis = await user_actions.ban_everywhere(
            bot, uid, reason=reason, actor=actor, dry_run=dry_run
        )
    else:
        ergebnis = await user_actions.warn_owners(
            bot, uid, reason=reason, actor=actor, dry_run=dry_run
        )

    if not dry_run:
        await feature_audit.log_action(
            f"mass_{kind}", actor=actor,
            detail=f"{uid}: {ergebnis['ok_count']} ok, {ergebnis['fail_count']} fehlgeschlagen",
        )

    return {"status": "success", "kind": kind, **ergebnis}
