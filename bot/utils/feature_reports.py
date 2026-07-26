"""
Analytics reports behind the admin feature flags.

Each function is gated by its own flag and returns plain dictionaries so the
API can hand them straight to the dashboard.
"""

from __future__ import annotations

import os
from typing import Any

import aiosqlite

from utils import feature_flags as flags

WEBHOOK_WARN_THRESHOLD = 10


def _disabled(key: str) -> dict[str, Any]:
    return {"enabled": False, "reason": f"Feature '{key}' is disabled."}


# ── Security score ────────────────────────────────────────────────────────


async def security_score(bot) -> dict[str, Any]:
    """Score each guild from 0-100 based on the protections it has enabled."""
    if not flags.is_enabled("security_score_calculation"):
        return _disabled("security_score_calculation")

    antinuke_guilds: set[int] = set()
    automod_counts: dict[int, int] = {}
    verification_guilds: set[int] = set()

    try:
        async with aiosqlite.connect("db/anti.db") as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='antinuke'"
            ) as cursor:
                if await cursor.fetchone():
                    async with db.execute(
                        "SELECT guild_id FROM antinuke WHERE status = 'true' OR status = 1"
                    ) as rows:
                        antinuke_guilds = {int(r[0]) async for r in rows}
    except Exception:
        pass

    try:
        async with aiosqlite.connect("db/automod.db") as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [r[0] for r in await cursor.fetchall()]
            for table in tables:
                async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                    columns = [r[1] for r in await cursor.fetchall()]
                if "guild_id" not in columns:
                    continue
                async with db.execute(f"SELECT DISTINCT guild_id FROM [{table}]") as rows:
                    async for row in rows:
                        try:
                            gid = int(row[0])
                        except (TypeError, ValueError):
                            continue
                        automod_counts[gid] = automod_counts.get(gid, 0) + 1
    except Exception:
        pass

    try:
        async with aiosqlite.connect("db/verification.db") as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [r[0] for r in await cursor.fetchall()]
            if tables:
                async with db.execute(f"SELECT DISTINCT guild_id FROM [{tables[0]}]") as rows:
                    verification_guilds = {int(r[0]) async for r in rows if str(r[0]).isdigit()}
    except Exception:
        pass

    results = []
    for guild in bot.guilds:
        score = 0
        reasons = []

        if guild.id in antinuke_guilds:
            score += 35
        else:
            reasons.append("Antinuke disabled")

        modules = min(automod_counts.get(guild.id, 0), 6)
        score += modules * 5
        if modules < 3:
            reasons.append(f"Only {modules} automod modules configured")

        if guild.id in verification_guilds:
            score += 15
        else:
            reasons.append("No verification configured")

        if getattr(guild, "mfa_level", 0):
            score += 10
        else:
            reasons.append("Server 2FA requirement off")

        verification_level = str(getattr(guild.verification_level, "name", "none"))
        if verification_level in {"medium", "high", "highest"}:
            score += 10
        else:
            reasons.append(f"Discord verification level is {verification_level}")

        results.append(
            {
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "score": min(score, 100),
                "issues": reasons,
            }
        )

    results.sort(key=lambda item: item["score"])
    return {"enabled": True, "guilds": results}


# ── Automod recommendations ───────────────────────────────────────────────

AUTOMOD_MODULES = (
    "antispam", "anticaps", "antilink", "antiinvite", "antimassmention", "antiemojispam",
)


async def automod_recommendations(bot) -> dict[str, Any]:
    if not flags.is_enabled("automod_rule_recommendations"):
        return _disabled("automod_rule_recommendations")

    configured: dict[int, set[str]] = {}
    try:
        async with aiosqlite.connect("db/automod.db") as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [r[0] for r in await cursor.fetchall()]
            for table in tables:
                async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                    columns = [r[1] for r in await cursor.fetchall()]
                if "guild_id" not in columns:
                    continue
                async with db.execute(f"SELECT DISTINCT guild_id FROM [{table}]") as rows:
                    async for row in rows:
                        try:
                            gid = int(row[0])
                        except (TypeError, ValueError):
                            continue
                        configured.setdefault(gid, set()).add(table.lower())
    except Exception as exc:
        return {"enabled": True, "error": str(exc), "guilds": []}

    guilds = []
    for guild in bot.guilds:
        active = configured.get(guild.id, set())
        missing = [
            module for module in AUTOMOD_MODULES
            if not any(module in table for table in active)
        ]
        if missing:
            guilds.append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "missing_modules": missing,
                }
            )
    return {"enabled": True, "guilds": guilds}


# ── Permission / risk scanners ────────────────────────────────────────────


async def staff_permission_review(bot) -> dict[str, Any]:
    if not flags.is_enabled("staff_permission_review"):
        return _disabled("staff_permission_review")

    guilds = []
    for guild in bot.guilds:
        admins = []
        for member in guild.members:
            if member.bot:
                continue
            perms = member.guild_permissions
            if perms.administrator:
                admins.append({"id": str(member.id), "name": member.display_name, "level": "administrator"})
            elif perms.manage_guild or perms.ban_members:
                admins.append({"id": str(member.id), "name": member.display_name, "level": "moderator"})
        if admins:
            guilds.append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "staff_count": len(admins),
                    "members": admins[:50],
                }
            )
    guilds.sort(key=lambda item: item["staff_count"], reverse=True)
    return {"enabled": True, "guilds": guilds}


async def role_risk_scan(bot) -> dict[str, Any]:
    if not flags.is_enabled("role_risk_scanner"):
        return _disabled("role_risk_scanner")

    guilds = []
    for guild in bot.guilds:
        risky = []
        for role in guild.roles:
            if role.is_default():
                continue
            perms = role.permissions
            if perms.administrator:
                risky.append({"id": str(role.id), "name": role.name, "risk": "administrator", "members": len(role.members)})
            elif perms.manage_roles or perms.manage_channels or perms.manage_webhooks:
                risky.append({"id": str(role.id), "name": role.name, "risk": "management", "members": len(role.members)})
        if risky:
            guilds.append({"guild_id": str(guild.id), "guild_name": guild.name, "roles": risky[:50]})
    return {"enabled": True, "guilds": guilds}


async def channel_risk_scan(bot) -> dict[str, Any]:
    if not flags.is_enabled("channel_risk_scanner"):
        return _disabled("channel_risk_scanner")

    guilds = []
    for guild in bot.guilds:
        open_channels = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.default_role)
            if perms.send_messages and perms.view_channel:
                open_channels.append({"id": str(channel.id), "name": channel.name})
        if open_channels:
            guilds.append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "open_channel_count": len(open_channels),
                    "channels": open_channels[:50],
                }
            )
    return {"enabled": True, "guilds": guilds}


async def webhook_risk_scan(bot) -> dict[str, Any]:
    if not flags.is_enabled("webhook_risk_scanner"):
        return _disabled("webhook_risk_scanner")

    guilds = []
    for guild in bot.guilds:
        if not guild.me or not guild.me.guild_permissions.manage_webhooks:
            continue
        try:
            hooks = await guild.webhooks()
        except Exception:
            continue
        if len(hooks) >= WEBHOOK_WARN_THRESHOLD:
            guilds.append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "webhook_count": len(hooks),
                    "flagged": True,
                }
            )
        elif hooks:
            guilds.append(
                {
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "webhook_count": len(hooks),
                    "flagged": False,
                }
            )
    guilds.sort(key=lambda item: item["webhook_count"], reverse=True)
    return {"enabled": True, "threshold": WEBHOOK_WARN_THRESHOLD, "guilds": guilds}


# ── Tickets / invites / retention / voice ─────────────────────────────────


async def ticket_load(bot) -> dict[str, Any]:
    if not flags.is_enabled("ticket_load_balancer"):
        return _disabled("ticket_load_balancer")

    if not os.path.exists("db/ticket.db"):
        return {"enabled": True, "staff": [], "note": "No ticket database yet."}

    counts: dict[str, int] = {}
    try:
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [r[0] for r in await cursor.fetchall()]
            for table in tables:
                async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                    columns = [r[1] for r in await cursor.fetchall()]
                claim_column = next(
                    (c for c in columns if c.lower() in {"claimed_by", "claimer", "staff_id"}), None
                )
                if not claim_column:
                    continue
                async with db.execute(
                    f"SELECT [{claim_column}], COUNT(*) FROM [{table}] "
                    f"WHERE [{claim_column}] IS NOT NULL GROUP BY [{claim_column}]"
                ) as rows:
                    async for row in rows:
                        counts[str(row[0])] = counts.get(str(row[0]), 0) + int(row[1])
    except Exception as exc:
        return {"enabled": True, "error": str(exc), "staff": []}

    staff = [{"staff_id": key, "open_tickets": value} for key, value in counts.items()]
    staff.sort(key=lambda item: item["open_tickets"], reverse=True)
    return {"enabled": True, "staff": staff}


async def invite_growth(bot) -> dict[str, Any]:
    if not flags.is_enabled("invite_growth_analytics"):
        return _disabled("invite_growth_analytics")

    guilds = []
    try:
        async with aiosqlite.connect("db/invite.db") as db:
            for guild in bot.guilds:
                table = f"invites_{guild.id}"
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
                ) as cursor:
                    if not await cursor.fetchone():
                        continue
                async with db.execute(
                    f"SELECT COALESCE(SUM(total),0), COALESCE(SUM(fake),0), "
                    f"COALESCE(SUM(left),0), COUNT(*) FROM [{table}]"
                ) as cursor:
                    row = await cursor.fetchone()
                total, fake, left, inviters = (row or (0, 0, 0, 0))
                guilds.append(
                    {
                        "guild_id": str(guild.id),
                        "guild_name": guild.name,
                        "total_invites": int(total),
                        "fake_invites": int(fake),
                        "left": int(left),
                        "inviters": int(inviters),
                    }
                )
    except Exception as exc:
        return {"enabled": True, "error": str(exc), "guilds": []}

    guilds.sort(key=lambda item: item["total_invites"], reverse=True)
    return {"enabled": True, "guilds": guilds}


async def member_retention(bot) -> dict[str, Any]:
    if not flags.is_enabled("member_retention_insights"):
        return _disabled("member_retention_insights")

    source = await invite_growth(bot)
    if not source.get("enabled") or source.get("error"):
        # Retention builds on the same tables; surface the same problem.
        return {"enabled": True, "guilds": [], "note": "Invite data unavailable."}

    guilds = []
    for entry in source.get("guilds", []):
        total = entry["total_invites"]
        left = entry["left"]
        retention = round(((total - left) / total) * 100, 1) if total else 0.0
        guilds.append(
            {
                "guild_id": entry["guild_id"],
                "guild_name": entry["guild_name"],
                "joined": total,
                "left": left,
                "retention_percent": retention,
            }
        )
    guilds.sort(key=lambda item: item["retention_percent"])
    return {"enabled": True, "guilds": guilds}


async def voice_analytics() -> dict[str, Any]:
    if not flags.is_enabled("voice_session_analytics"):
        return _disabled("voice_session_analytics")

    from utils.feature_services import runtime

    totals = [
        {"guild_id": key, "total_minutes": round(value / 60, 1)}
        for key, value in runtime.voice_totals.items()
    ]
    totals.sort(key=lambda item: item["total_minutes"], reverse=True)
    return {"enabled": True, "guilds": totals}
