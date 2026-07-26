"""
Who is allowed to perform a dashboard action.

The problem this solves
-----------------------
`dashboard_roles.is_owner()` only knows about `OWNER_IDS` / `ADMIN_IDS`. On a
fresh deployment neither is set, so `OWNER_IDS` falls back to a hard-coded ID
that belongs to the *original* bot author — meaning the person who actually
deployed the bot is not an owner as far as the code is concerned, and every
write endpoint answered 403.

Discord already knows the answer, so we ask it instead of a config file:

    application owner   whoever owns the bot application (or the team behind
                        it). This is the deployer, always, with zero config.
    env / db owner      the existing OWNER_IDS / ADMIN_IDS mechanism.
    dashboard role      one of the 40 team roles.
    guild authority     the owner of a specific server, or a member with
                        Administrator / Manage Server there.

Actions are then gated at the right level:

    global      owner or a team permission          (blacklist, dashboard bans)
    per-guild   the above, or authority on that one server (roles, leaving)
"""

from __future__ import annotations

from utils import dashboard_roles as roles


# ── Where authority can come from ─────────────────────────────────────────


def application_owner_ids(bot) -> set[str]:
    """
    IDs Discord itself considers owners of this bot application.

    Covers both a personal application (single owner) and a team application
    (every team member). Read defensively: the attributes only exist once the
    gateway has sent READY.
    """
    ids: set[str] = set()

    owner_id = getattr(bot, "owner_id", None)
    if owner_id:
        ids.add(str(owner_id))

    for extra in getattr(bot, "owner_ids", None) or ():
        ids.add(str(extra))

    application = getattr(bot, "application", None)
    if application is not None:
        owner = getattr(application, "owner", None)
        if owner is not None and getattr(owner, "id", None):
            ids.add(str(owner.id))

        team = getattr(application, "team", None)
        if team is not None:
            for member in getattr(team, "members", None) or ():
                if getattr(member, "id", None):
                    ids.add(str(member.id))

    return ids


def is_owner(bot, user_id: str) -> bool:
    """True for a configured owner *or* the Discord application owner."""
    uid = str(user_id).strip()
    if not uid:
        return False
    if roles.is_owner(uid):
        return True
    return uid in application_owner_ids(bot)


def guild_authority(bot, user_id: str, guild_id) -> str | None:
    """
    How much say this user has in one specific server.

    Returns "owner", "administrator", "manage_guild" — or None when they have
    no standing there. Uses the bot's member cache, so it reflects Discord's
    current state rather than anything we store.
    """
    uid = str(user_id).strip()
    if not uid.isdigit():
        return None

    try:
        guild = bot.get_guild(int(guild_id))
    except (TypeError, ValueError):
        return None
    if guild is None:
        return None

    if str(guild.owner_id) == uid:
        return "owner"

    member = guild.get_member(int(uid))
    if member is None:
        return None

    permissions = member.guild_permissions
    if permissions.administrator:
        return "administrator"
    if permissions.manage_guild:
        return "manage_guild"
    return None


# ── Gates used by the routes ──────────────────────────────────────────────


def may_act_globally(bot, actor: str, permission: str) -> bool:
    """
    Global actions: the blacklist and dashboard bans.

    Deliberately *not* open to server admins — running one Discord server must
    not let somebody ban people out of the whole dashboard.
    """
    if is_owner(bot, actor):
        return True
    return roles.has_permission(actor, permission)


def may_act_on_guild(bot, actor: str, guild_id, permission: str) -> bool:
    """
    Per-guild actions: handing out roles, making the bot leave.

    Someone who owns or administrates the server can already do these things
    inside Discord, so refusing them here would be theatre.
    """
    if is_owner(bot, actor):
        return True
    if roles.has_permission(actor, permission, str(guild_id)):
        return True
    return guild_authority(bot, actor, guild_id) is not None


def may_remove_bot(bot, actor: str, guild_id) -> bool:
    """
    Removing the bot from a server.

    Stricter than `may_act_on_guild`: only a bot owner, a holder of
    `blacklist.manage`, or the *owner* of that server. A plain administrator
    should not be able to evict the bot from somebody else's community.
    """
    if is_owner(bot, actor):
        return True
    if roles.has_permission(actor, "blacklist.manage", str(guild_id)):
        return True
    return guild_authority(bot, actor, guild_id) == "owner"


def describe(bot, actor: str, guild_id=None) -> dict:
    """Explains where a user's authority comes from. Used by the UI and tests."""
    return {
        "user_id": str(actor),
        "configured_owner": roles.is_owner(actor),
        "application_owner": str(actor) in application_owner_ids(bot),
        "dashboard_roles": [r.key for r in roles.get_roles(actor)],
        "guild_authority": guild_authority(bot, actor, guild_id) if guild_id else None,
    }
