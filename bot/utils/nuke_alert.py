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

# One channel report per guild per this many seconds. A nuke fires
# dozens of events; without this the bot would spam its own alert
# channel and hit the rate limit while the attack is still running.
COOLDOWN = 20.0

# A DM is far more intrusive than a channel post, and the owner cannot
# mute it. One nuke should produce one DM, not one per 20 seconds --
# a five minute attack used to send fifteen.
DM_COOLDOWN = 900.0

# How long a burst of events counts as *one* attack. Anything within
# this window is folded into the incident that is already running.
INCIDENT_WINDOW = 300.0

_last_alert: dict[int, float] = {}
_last_dm: dict[int, float] = {}

# Open incidents, so a long attack stays one story instead of becoming
# forty unrelated notifications.
_incident: dict[int, dict] = {}

# What was done about it.
OUTCOME_STOPPED = "stopped"      # acted successfully, nothing left to do
OUTCOME_PARTIAL = "partial"      # the damage was undone, the punishment was not
OUTCOME_NO_PERMS = "no_perms"    # saw it, could not act at all
OUTCOME_DISABLED = "disabled"    # anti-nuke was off
OUTCOME_BLIND = "blind"          # cannot even check -- missing audit log access

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


# Channels this bot is deleting right now, as part of its own cleanup.
#
# Cleaning up after an attacker means deleting channels, which fires
# on_guild_channel_delete and walks straight into the anti-nuke module
# that watches for exactly that. The executor check (`is it me?`) covers
# the common case, but it depends on the audit log arriving in time --
# during a nuke the log lags, and a lagging log means the bot can flag
# its own cleanup as an attack. This set is the authoritative answer and
# needs no audit log at all.
_self_deleting: set[int] = set()

# Guilds where the bot is repairing damage. Everything it does in this
# window is its own doing.
_repairing: dict[int, float] = {}
REPAIR_WINDOW = 60.0


def mark_repairing(guild_id: int) -> None:
    _repairing[guild_id] = time.time()


def is_self_action(guild_id: int, channel_id: int | None = None) -> bool:
    """
    Whether this change came from the bot's own cleanup.

    Checked by the anti-nuke modules before they treat a deletion as an
    attack, so the bot cannot ban itself for tidying up.
    """
    if channel_id is not None and int(channel_id) in _self_deleting:
        return True
    started = _repairing.get(int(guild_id))
    return started is not None and time.time() - started < REPAIR_WINDOW


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
            _self_deleting.add(channel.id)
            mark_repairing(guild.id)
            try:
                await channel.delete(reason="Anti-Nuke: vom Angreifer erstellt")
                removed += 1
                # Deleting a dozen channels at once trips the rate limit
                # and the rest of the cleanup never happens.
                await asyncio.sleep(0.7)
            except Exception:
                continue
            finally:
                # Kept briefly after the call so the delete event, which
                # arrives after this returns, still finds it.
                asyncio.get_event_loop().call_later(
                    30, _self_deleting.discard, channel.id
                )
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

    if outcome == OUTCOME_PARTIAL:
        # This used to be reported as "could NOT stop it", which was
        # simply wrong: the channel had already been removed or
        # restored by the time the ban failed. The owner read "not
        # stopped" while the attack was, in fact, stopped.
        return (
            "Angriff gestoppt — Verursacher konnte nicht gebannt werden",
            f"**{label}** wurde rückgängig gemacht, der Angriff ist gestoppt.\n\n"
            "Nur der Bann hat nicht geklappt — die Person kann es also erneut "
            "versuchen."
            + (f"\n\n**Fehlt:** {missing}" if missing else ""),
            "warning",
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

    if outcome == OUTCOME_BLIND:
        # Nine modules bail out of fetch_audit_logs when the bot cannot
        # ban, and returned None without a word -- the one case where
        # silence is worst, because nothing is being defended at all.
        return (
            "Anti-Nuke ist blind",
            f"**{label}** ist passiert, aber ich kann nicht einmal nachsehen, "
            "wer es war.\n\n"
            + (f"**Fehlt:** {missing}\n\n" if missing else "")
            + "Ohne diese Rechte läuft der Anti-Nuke faktisch nicht, egal was "
            "im Dashboard eingestellt ist.",
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


def recovery_buttons(guild, user_id: int = 0):
    """
    The three things an owner needs after an attack, as link buttons.

    Link buttons and not callbacks on purpose: this message has to keep
    working after a restart, and Discord cannot hand a bot's OAuth flow
    to another bot without a human in a browser.
    """
    import os

    from discord import ButtonStyle
    from discord.ui import Button

    buttons = []

    client_id = os.getenv("PARTNER_BOT_CLIENT_ID", "").strip()
    if client_id:
        try:
            from utils import partner_bot

            buttons.append(Button(
                label="Server wiederherstellen",
                emoji="🛠️",
                style=ButtonStyle.link,
                url=partner_bot.invite_url(
                    client_id, guild_id=guild.id, user_id=user_id
                ),
            ))
        except Exception:
            pass

    # Was os.getenv("DASHBOARD_URL") alone, which is not set on the
    # live deployment -- so this button never appeared, silently, on the
    # one alert where reaching the settings quickly matters most.
    # utils.links falls back to NEXTAUTH_URL, which the dashboard cannot
    # work without.
    from utils.links import guild_dashboard_url

    antinuke_tab = guild_dashboard_url(guild.id, "antinuke")
    if antinuke_tab:
        buttons.append(Button(
            label="Anti-Nuke prüfen",
            emoji="🛡️",
            style=ButtonStyle.link,
            url=antinuke_tab,
        ))

    try:
        from utils.config import serverLink

        if serverLink:
            buttons.append(Button(
                label="Hilfe holen",
                emoji="💬",
                style=ButtonStyle.link,
                url=serverLink,
            ))
    except Exception:
        pass

    return buttons or None


def _incident_summary(guild_id: int) -> str:
    """What this attack has done so far, as one line."""
    entry = _incident.get(guild_id)
    if not entry:
        return ""

    counts = entry.get("actions") or {}
    if not counts:
        return ""

    parts = [
        f"{count}× {LABELS.get(name, name)}"
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return ", ".join(parts[:6])


def _track_incident(guild_id: int, action: str, outcome: str) -> dict:
    """
    Fold this event into the attack that is already running.

    Without this every deleted channel is its own "incident" and the
    owner gets a wall of near-identical notifications for what is really
    one attack.
    """
    now = time.time()
    entry = _incident.get(guild_id)
    if entry is None or now - entry["started"] > INCIDENT_WINDOW:
        entry = {"started": now, "actions": {}, "worst": outcome, "events": 0}
        _incident[guild_id] = entry

    entry["events"] += 1
    entry["actions"][action] = entry["actions"].get(action, 0) + 1
    entry["last"] = now

    # Keep the most serious outcome seen: a single "stopped" in the
    # middle of an attack must not downgrade the report.
    severity = {
        OUTCOME_STOPPED: 0, OUTCOME_PARTIAL: 1, OUTCOME_DISABLED: 2,
        OUTCOME_NO_PERMS: 3, OUTCOME_BLIND: 4,
    }
    if severity.get(outcome, 0) > severity.get(entry["worst"], 0):
        entry["worst"] = outcome

    return entry


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

        incident = _track_incident(guild.id, action, outcome)
        now = time.time()

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
            sections.append(
                f"**Aufgeräumt:** {cleaned} vom Angreifer erstellte Kanäle gelöscht."
            )

        summary = _incident_summary(guild.id)
        if incident["events"] > 1 and summary:
            sections.append(f"**Bisher in diesem Angriff:** {summary}")

        buttons = recovery_buttons(guild, getattr(guild, "owner_id", 0) or 0)

        # ── the channel post ────────────────────────────────────────
        # One per cooldown. Noisy is acceptable here: it is a log.
        if _last_alert.get(guild.id, 0) + COOLDOWN <= now:
            _last_alert[guild.id] = now

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
                        view=Panel(title, *sections, tone=tone, buttons=buttons),
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )
                    # Remembered so an arriving template bot can be told
                    # apart from somebody casually adding a bot, and so
                    # the rescue continues in this same channel.
                    remember_attack(guild.id, channel.id)
                except Exception:
                    pass

        # The recovery card goes into its own channel once per incident,
        # after the attack has had time to finish. Posting it here and
        # now would drop it into a channel that may not survive the next
        # few seconds.
        if not incident.get("panel_sent"):
            incident["panel_sent"] = True
            asyncio.create_task(schedule_backup_channel(bot, guild, cleaned))

        # ── the DM ──────────────────────────────────────────────────
        # On its own, much longer timer. The owner cannot mute a DM, and
        # a five minute attack used to arrive as fifteen separate
        # messages saying nearly the same thing.
        if not settings.get("dm_owner"):
            return
        if outcome == OUTCOME_STOPPED:
            # Nothing is required of the owner, so nothing is sent.
            return
        if _last_dm.get(guild.id, 0) + DM_COOLDOWN > now:
            return

        owner = guild.owner
        if owner is None:
            return

        _last_dm[guild.id] = now

        from utils.panels import Panel

        dm_sections = list(sections)
        dm_sections.append(
            "*Weitere Vorfälle in diesem Angriff schicke ich dir nicht "
            "einzeln — sieh im Server-Kanal oder im Dashboard nach.*"
        )

        try:
            await owner.send(view=Panel(
                f"{title} — {guild.name}", *dm_sections,
                tone=tone, buttons=buttons,
            ))
        except discord.Forbidden:
            # DMs closed. Nothing to be done, and retrying every event
            # would just burn rate limit.
            pass
        except Exception:
            pass

    except Exception:
        # Reporting must never break the defence itself.
        pass


# Guilds that were attacked recently, so the join listener knows whether
# an arriving template bot is a rescue or just somebody adding a bot.
_recent_attack: dict[int, dict] = {}

# How long after an attack an arriving template bot counts as a rescue.
RESCUE_WINDOW = 3600.0

# Where the recovery panel goes. A channel of its own, created after the
# attack, so the panel is not buried in whatever survived -- and so the
# whole rescue happens in one place the owner can find.
BACKUP_CHANNEL_NAME = "backup"

# How long to wait before creating it. A nuke is still running while the
# events arrive; building the rescue channel immediately means building
# it into an attack that may still delete it. Twenty seconds is long
# enough for the burst to end.
BACKUP_DELAY = 20.0

# What the template bot listens for. Sent by this bot, not by a human --
# the owner is busy looking at a wrecked server.
TEMPLATE_TRIGGER = "!start"

# After the ping, before the trigger. Discord has not finished setting
# the member up when on_member_join fires: permissions are still
# resolving and the other bot's command handler may not be listening.
TEMPLATE_TRIGGER_DELAY = 2.0


def remember_attack(guild_id: int, channel_id: int | None) -> None:
    """Note where the alert panel went, so the rescue can continue there."""
    _recent_attack[int(guild_id)] = {
        "at": time.time(),
        "channel_id": int(channel_id) if channel_id else None,
    }


def recent_attack(guild_id: int) -> dict | None:
    entry = _recent_attack.get(int(guild_id))
    if entry is None:
        return None
    if time.time() - entry["at"] > RESCUE_WINDOW:
        _recent_attack.pop(int(guild_id), None)
        return None
    return entry


def clear_attack(guild_id: int) -> None:
    _recent_attack.pop(int(guild_id), None)


# Guilds where a backup channel is already being prepared, so a burst of
# forty events does not start forty timers.
_backup_pending: set[int] = set()


async def ensure_backup_channel(guild, settings: dict):
    """
    A channel of its own for the rescue, created after the dust settles.

    Waiting matters: the events that trigger this arrive *while* the
    attack is running, and a channel created mid-nuke is just another
    thing for the attacker to delete. Only the bot and the server staff
    can see it, so the panel is not sitting in public during an
    incident.
    """
    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        return None

    existing = next(
        (c for c in guild.text_channels if c.name == BACKUP_CHANNEL_NAME),
        None,
    )
    if existing is not None:
        return existing

    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False, send_messages=False
            ),
            me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }
        return await guild.create_text_channel(
            BACKUP_CHANNEL_NAME,
            overwrites=overwrites,
            reason="Anti-Nuke: Kanal für die Wiederherstellung",
            topic="Hier läuft die Wiederherstellung nach dem Angriff.",
        )
    except discord.Forbidden:
        return None
    except discord.HTTPException as exc:
        # 50035 covers the 500-channel server cap.
        print(f"nuke_alert: could not create #{BACKUP_CHANNEL_NAME}: {exc}")
        return None


async def schedule_backup_channel(bot, guild, cleaned: int = 0) -> None:
    """
    Wait out the attack, then open the rescue channel and post the panel.

    Scheduled once per incident. Failing here must never take the
    defence down with it, so everything is wrapped.
    """
    if guild.id in _backup_pending:
        return
    _backup_pending.add(guild.id)

    try:
        await asyncio.sleep(BACKUP_DELAY)

        channel = await ensure_backup_channel(guild, await get_settings(guild.id))
        if channel is None:
            return

        try:
            await channel.send(view=recovery_panel(guild, cleaned))
        except discord.HTTPException:
            return

        # The handoff continues here, not wherever the alert happened to
        # land -- this channel is the one the owner was pointed at.
        remember_attack(guild.id, channel.id)
    except Exception as exc:
        print(f"nuke_alert: backup channel setup failed: {exc}")
    finally:
        _backup_pending.discard(guild.id)


def recovery_panel(guild, cleaned: int = 0):
    """
    The standalone "get your server back" card.

    Posted after an attack, separate from the incident report: the
    report is a log entry, this is the thing the owner has to act on.
    """
    from utils.panels import Panel

    sections = [
        "Der Angriff ist vorbei — der Server sieht aber vermutlich nicht "
        "mehr so aus wie vorher.",
        "**So bekommst du ihn zurück:**\n"
        "1. Unten auf **Server wiederherstellen** tippen\n"
        "2. Den Bot bestätigen — er baut Kanäle und Rollen aus einer "
        "Vorlage neu auf\n"
        "3. Danach läuft alles automatisch weiter",
        "*Der Wiederherstellungs-Bot ist beim Anti-Nuke fest freigestellt. "
        "Er legt in kurzer Zeit viele Kanäle an — das ist gewollt und löst "
        "keinen Alarm aus.*",
    ]
    if cleaned:
        sections.insert(1, f"**Bereits aufgeräumt:** {cleaned} Kanäle des Angreifers.")

    return Panel(
        "Server wiederherstellen",
        *sections,
        tone="info",
        buttons=recovery_buttons(guild, getattr(guild, "owner_id", 0) or 0),
    )


async def handle_forbidden(bot, guild, action: str, executor=None, detail="") -> None:
    """Shorthand for the `except discord.Forbidden` branches."""
    await report(bot, guild, action, OUTCOME_NO_PERMS, executor=executor, detail=detail)


async def handle_partial(bot, guild, action: str, executor=None, detail="",
                         repaired: bool = True) -> None:
    """
    The damage was undone but the ban failed.

    Previously reported through handle_forbidden, which says "could NOT
    stop it" -- flatly untrue when the channel had already been removed
    or restored. The owner saw "not stopped" for an attack that was.

    `repaired` says whether the repair itself got through. The callers
    wrap the repair and the ban in one try, so a Forbidden can come from
    either; passing False keeps the honest "could not stop it" wording
    for the case where nothing was fixed at all.
    """
    outcome = OUTCOME_PARTIAL if repaired else OUTCOME_NO_PERMS
    await report(bot, guild, action, outcome, executor=executor, detail=detail)


async def handle_blind(bot, guild, action: str, detail="") -> None:
    """
    Something happened and the bot cannot even look up who did it.

    Nine modules return early from fetch_audit_logs when the bot has no
    ban permission, and said nothing at all -- the one case where
    silence is worst, because nothing is being defended.
    """
    await report(bot, guild, action, OUTCOME_BLIND, detail=detail)


async def handle_stopped(
    bot, guild, action: str, executor=None, detail="", clean: bool = False
) -> None:
    """Shorthand for a successful defence, optionally cleaning up first."""
    cleaned = 0
    if clean and executor is not None:
        settings = await get_settings(guild.id)
        if settings.get("clean_channels"):
            # Everything the bot does from here is repair work, not an
            # attack -- the modules check this before reacting.
            mark_repairing(guild.id)
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
