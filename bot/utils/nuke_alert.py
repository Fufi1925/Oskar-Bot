# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anti-nuke: cleaning up and telling somebody about it           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
What happens after the anti-nuke modules react.

The seventeen modules in `cogs/antinuke/` all did their work in silence:
they deleted the channel, banned the executor, and on
`except discord.Forbidden: return` they gave up without a word. So the
three cases a server owner most needs to tell apart looked identical
from the outside — nothing in the server, nothing in a log:

  * the attack was stopped
  * the bot saw it but lacked the permission to stop it
  * anti-nuke was switched off entirely

This module reports all three, cleans up the channels an attacker
created, and posts into a channel that survives the attack — creating
one if the attacker deleted everything.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiosqlite
import discord

DB_PATH = "db/anti.db"

# Where the report goes. Falls through the list until something works.
ALERT_CHANNEL_NAME = "nuke-alarm"

# One report per guild per this many seconds. A nuke fires dozens of
# events; without this the bot would spam its own alert channel and hit
# the rate limit while the attack is still running.
COOLDOWN = 20.0

_last_alert: dict[int, float] = {}

# What was done about it.
OUTCOME_STOPPED = "stopped"      # acted successfully
OUTCOME_NO_PERMS = "no_perms"    # saw it, could not act
OUTCOME_DISABLED = "disabled"    # anti-nuke was off

LABELS = {
    "channel_create": "Kanal erstellt",
    "channel_delete": "Kanal gelöscht",
    "channel_update": "Kanal geändert",
    "role_create": "Rolle erstellt",
    "role_delete": "Rolle gelöscht",
    "role_update": "Rolle geändert",
    "ban": "Mitglied gebannt",
    "kick": "Mitglied gekickt",
    "prune": "Mitglieder entfernt",
    "webhook_create": "Webhook erstellt",
    "webhook_delete": "Webhook gelöscht",
    "webhook_update": "Webhook geändert",
    "bot_add": "Bot hinzugefügt",
    "everyone": "@everyone missbraucht",
    "guild_update": "Server-Einstellungen geändert",
    "integration": "Integration hinzugefügt",
    "member_update": "Rechte an Mitglied vergeben",
}


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """The alert settings and the incident history."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS nuke_alerts (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            channel_id INTEGER,
            create_channel INTEGER DEFAULT 1,
            clean_channels INTEGER DEFAULT 1,
            ping_owner INTEGER DEFAULT 1,
            dm_owner INTEGER DEFAULT 1
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS nuke_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            executor_id INTEGER,
            executor_name TEXT,
            detail TEXT,
            at REAL NOT NULL
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS nuke_incidents_guild"
        " ON nuke_incidents (guild_id, at DESC)"
    )
    await db.commit()


DEFAULTS = {
    "enabled": 1,
    "channel_id": None,
    "create_channel": 1,
    "clean_channels": 1,
    "ping_owner": 1,
    "dm_owner": 1,
}


async def get_settings(guild_id: int) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await ensure_schema(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM nuke_alerts WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
    except Exception:
        return dict(DEFAULTS)

    if row is None:
        return dict(DEFAULTS)

    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in row.keys() and row[key] is not None:
            out[key] = row[key]
    return out


async def save_settings(guild_id: int, updates: dict) -> dict:
    current = await get_settings(guild_id)
    merged = {**current, **{k: v for k, v in updates.items() if k in DEFAULTS}}

    for key in ("enabled", "create_channel", "clean_channels", "ping_owner", "dm_owner"):
        merged[key] = 1 if merged.get(key) else 0
    channel = merged.get("channel_id")
    merged["channel_id"] = int(channel) if str(channel or "").isdigit() else None

    async with aiosqlite.connect(DB_PATH) as db:
        await ensure_schema(db)
        columns = list(DEFAULTS)
        await db.execute(
            f"INSERT OR REPLACE INTO nuke_alerts (guild_id, {', '.join(columns)})"
            f" VALUES ({', '.join('?' * (len(columns) + 1))})",
            [guild_id] + [merged[name] for name in columns],
        )
        await db.commit()
    return merged


async def record(
    guild_id: int, action: str, outcome: str,
    executor_id: int = 0, executor_name: str = "", detail: str = "",
) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await ensure_schema(db)
            await db.execute(
                "INSERT INTO nuke_incidents"
                " (guild_id, action, outcome, executor_id, executor_name, detail, at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild_id, action, outcome, executor_id,
                 str(executor_name)[:100], str(detail)[:300], time.time()),
            )
            await db.commit()
    except Exception:
        pass


async def incidents(guild_id: int, limit: int = 50) -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await ensure_schema(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM nuke_incidents WHERE guild_id = ?"
                " ORDER BY at DESC LIMIT ?",
                (guild_id, max(1, min(limit, 200))),
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
    except Exception:
        return []


# ── finding somewhere to shout ──────────────────────────────────────


async def alert_channel(guild, settings: dict):
    """
    A channel the report can reach.

    Order matters during an attack: the configured channel may be the
    first thing deleted, so every step has a fallback and the last one
    creates a channel from scratch.
    """
    me = guild.me
    if me is None:
        return None

    def usable(channel):
        return (
            channel is not None
            and hasattr(channel, "send")
            and channel.permissions_for(me).send_messages
        )

    configured = settings.get("channel_id")
    if configured:
        channel = guild.get_channel(int(configured))
        if usable(channel):
            return channel

    # A channel we made earlier during another attack.
    for channel in guild.text_channels:
        if channel.name == ALERT_CHANNEL_NAME and usable(channel):
            return channel

    for name in ("mod-log", "modlog", "logs", "staff", "admin"):
        for channel in guild.text_channels:
            if name in channel.name.lower() and usable(channel):
                return channel

    if usable(guild.system_channel):
        return guild.system_channel

    existing = next((c for c in guild.text_channels if usable(c)), None)
    if existing is not None:
        return existing

    # Nothing left — the attacker deleted everything.
    if not settings.get("create_channel"):
        return None
    if not me.guild_permissions.manage_channels:
        return None

    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False, send_messages=False
            ),
            me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        return await guild.create_text_channel(
            ALERT_CHANNEL_NAME,
            overwrites=overwrites,
            reason="Anti-Nuke: kein Kanal zum Melden übrig",
            topic="Automatisch angelegt, weil beim Angriff kein Kanal übrig war.",
        )
    except Exception:
        return None


async def clean_created_channels(guild, executor_id: int, limit: int = 50) -> int:
    """
    Delete the channels the attacker created.

    A classic nuke leaves dozens of channels named the same thing. Only
    channels the audit log attributes to this executor are touched, so a
    legitimate channel created moments earlier is left alone.
    """
    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        return 0
    if not me.guild_permissions.view_audit_log:
        return 0

    removed = 0
    try:
        cutoff = discord.utils.utcnow() - __import__("datetime").timedelta(minutes=10)
        async for entry in guild.audit_logs(
            action=discord.AuditLogAction.channel_create, limit=limit, after=cutoff
        ):
            if entry.user is None or entry.user.id != executor_id:
                continue
            channel = guild.get_channel(entry.target.id) if entry.target else None
            if channel is None:
                continue
            try:
                await channel.delete(reason="Anti-Nuke: vom Angreifer erstellt")
                removed += 1
                # Deleting a dozen channels at once trips the rate limit
                # and the rest of the cleanup never happens.
                await asyncio.sleep(0.7)
            except Exception:
                continue
    except discord.Forbidden:
        return removed
    except Exception:
        return removed

    return removed


# ── the report ──────────────────────────────────────────────────────


def _describe(outcome: str, action: str, missing: str = "") -> tuple[str, str, str]:
    """(title, body, tone) for one outcome."""
    label = LABELS.get(action, action)

    if outcome == OUTCOME_STOPPED:
        return (
            "Angriff abgewehrt",
            f"**{label}** — der Verursacher wurde gebannt und die Änderung "
            "rückgängig gemacht.",
            "success",
        )

    if outcome == OUTCOME_NO_PERMS:
        return (
            "Angriff erkannt — konnte ihn NICHT stoppen",
            f"**{label}** wurde erkannt, aber mir fehlen die Rechte, um "
            "einzugreifen.\n\n"
            + (f"**Fehlt:** {missing}\n\n" if missing else "")
            + "Solange das so ist, kann ich hier nichts abwehren. Bitte gib "
            "mir die Rechte und schieb meine Rolle möglichst weit nach oben.",
            "error",
        )

    return (
        "Angriff erkannt — Anti-Nuke war AUS",
        f"**{label}** wurde erkannt, aber der Anti-Nuke ist für diesen "
        "Server ausgeschaltet. Ich habe nichts unternommen.\n\n"
        "Einschalten mit `antinuke enable` oder im Dashboard.",
        "warning",
    )


def missing_permissions(guild) -> list[str]:
    """Which permissions the bot needs and does not have."""
    me = guild.me
    if me is None:
        return []

    needed = {
        "ban_members": "Mitglieder bannen",
        "kick_members": "Mitglieder kicken",
        "manage_channels": "Kanäle verwalten",
        "manage_roles": "Rollen verwalten",
        "manage_webhooks": "Webhooks verwalten",
        "view_audit_log": "Audit-Log einsehen",
    }
    permissions = me.guild_permissions
    return [label for key, label in needed.items() if not getattr(permissions, key, False)]


async def report(
    bot, guild, action: str, outcome: str,
    executor: Any = None, detail: str = "", cleaned: int = 0,
) -> None:
    """
    Tell the server what happened.

    Never raises: this runs inside the anti-nuke handlers, and an error
    here must not stop them from doing their actual job.
    """
    try:
        settings = await get_settings(guild.id)

        await record(
            guild.id, action, outcome,
            executor_id=getattr(executor, "id", 0) or 0,
            executor_name=str(executor) if executor else "",
            detail=detail,
        )

        if not settings.get("enabled"):
            return

        # One report per attack, not one per deleted channel.
        now = time.time()
        if _last_alert.get(guild.id, 0) + COOLDOWN > now:
            return
        _last_alert[guild.id] = now

        missing = ", ".join(missing_permissions(guild))
        title, body, tone = _describe(outcome, action, missing)

        who = (
            f"{executor.mention} (`{executor.id}`)"
            if executor is not None and hasattr(executor, "mention")
            else "unbekannt"
        )
        sections = [body, f"**Verursacher:** {who}"]
        if detail:
            sections.append(f"**Details:** {detail}")
        if cleaned:
            sections.append(f"**Aufgeräumt:** {cleaned} vom Angreifer erstellte Kanäle gelöscht.")

        channel = await alert_channel(guild, settings)
        if channel is not None:
            from utils.panels import Panel

            content = None
            if settings.get("ping_owner") and outcome != OUTCOME_STOPPED:
                owner_id = guild.owner_id
                if owner_id:
                    content = f"<@{owner_id}>"

            try:
                await channel.send(
                    content=content,
                    view=Panel(title, *sections, tone=tone),
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except Exception:
                pass

        # The owner may not be watching, and during a real nuke the
        # channel might be gone a second later.
        if settings.get("dm_owner") and outcome != OUTCOME_STOPPED:
            owner = guild.owner
            if owner is not None:
                try:
                    from utils.panels import Panel

                    await owner.send(view=Panel(
                        f"{title} — {guild.name}", *sections, tone=tone
                    ))
                except Exception:
                    pass

    except Exception:
        # Reporting must never break the defence itself.
        pass


async def handle_forbidden(bot, guild, action: str, executor=None, detail="") -> None:
    """Shorthand for the `except discord.Forbidden` branches."""
    await report(bot, guild, action, OUTCOME_NO_PERMS, executor=executor, detail=detail)


async def handle_stopped(
    bot, guild, action: str, executor=None, detail="", clean: bool = False
) -> None:
    """Shorthand for a successful defence, optionally cleaning up first."""
    cleaned = 0
    if clean and executor is not None:
        settings = await get_settings(guild.id)
        if settings.get("clean_channels"):
            cleaned = await clean_created_channels(guild, executor.id)
    await report(
        bot, guild, action, OUTCOME_STOPPED,
        executor=executor, detail=detail, cleaned=cleaned,
    )


async def handle_disabled(bot, guild, action: str, executor=None) -> None:
    """
    Anti-nuke is off but something suspicious happened anyway.

    Reported at most once per cooldown so a server that deliberately runs
    without anti-nuke is not nagged constantly.
    """
    await report(bot, guild, action, OUTCOME_DISABLED, executor=executor)
