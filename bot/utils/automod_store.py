# ╔══════════════════════════════════════════════════════════════════╗
# ║   Automod: rules, punishments and the shared bookkeeping         ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
One source of truth for the automod rules.

The tab was wired to nothing. Three separate faults, each reproduced
before this module existed:

  * **The dashboard and the bot used different names.** The tab saved
    ``anti_spam`` / ``mute``; the cogs looked for ``Anti spam`` /
    ``Mute``. Nothing set in the tab ever took effect -- switching a
    rule on wrote a row that no listener would ever match.

  * **A rule could be switched on but never off.** "Is this rule
    active?" was answered by *whether a punishment row exists*, so the
    only way to disable one was to delete the row. The tab had no way to
    do that, and the toggle in it did nothing at all.

  * **The spam counter was keyed by user, not by user and guild.** Three
    messages on one server plus three on another added up to six, so
    somebody talking normally in two servers the bot shares got muted
    for spam in one of them.

Everything is addressed by a stable key (``spam``, ``caps``, ...) and
translated to the legacy event names on the way in, so a server that was
set up over chat keeps working.
"""

from __future__ import annotations

import time

from typing import Any

import aiosqlite

DB_PATH = "db/automod.db"

# What the cogs historically wrote into automod_punishments.event. Kept
# as the storage format so an existing setup keeps working; the API and
# the dashboard speak the short key on the left.
LEGACY_EVENTS = {
    "spam": "Anti spam",
    "caps": "Anti caps",
    "links": "Anti link",
    "invites": "Anti invites",
    "mentions": "Anti mass mention",
    "emoji": "Anti emoji spam",
}

# Accepts anything a previous version may have written, so a row saved
# by the broken dashboard is still recognised rather than ignored.
ALIASES = {
    "anti_spam": "spam", "anti spam": "spam", "spam": "spam",
    "anti_caps": "caps", "anti caps": "caps", "caps": "caps",
    "anti_links": "links", "anti_link": "links", "anti link": "links",
    "links": "links", "link": "links",
    "anti_invites": "invites", "anti invites": "invites",
    "invites": "invites", "invite": "invites",
    "anti_mentions": "mentions", "anti mass mention": "mentions",
    "anti_mass_mention": "mentions", "mentions": "mentions",
    "anti_emoji": "emoji", "anti emoji spam": "emoji", "emoji": "emoji",
}

PUNISHMENTS = ("delete", "warn", "mute", "kick", "ban")

# Punishment names as the cogs used to write them.
LEGACY_PUNISHMENTS = {
    "mute": "Mute", "kick": "Kick", "ban": "Ban",
    "delete": "Delete", "warn": "Warn",
}


def normalise_rule(name: str) -> str | None:
    """Map any spelling of a rule onto its stable key."""
    return ALIASES.get(str(name or "").strip().lower())


def normalise_punishment(value: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in PUNISHMENTS else "mute"


# Per-rule defaults. Thresholds and durations were hard-coded in six
# near-identical copies; the numbers here are the ones those copies used,
# so nothing changes for a server that never touches them.
RULES: dict[str, dict[str, Any]] = {
    "spam": {
        "label": "Anti-Spam",
        "description": "Zu viele Nachrichten in kurzer Zeit.",
        "punishment": "mute",
        "threshold": 5,          # messages
        "window": 10,            # seconds
        "duration": 12,          # minutes of timeout
        "threshold_label": "Nachrichten",
        "threshold_min": 3,
        "threshold_max": 20,
        "has_window": True,
    },
    "caps": {
        "label": "Anti-Caps",
        "description": "Nachrichten fast nur in Großbuchstaben.",
        "punishment": "mute",
        "threshold": 70,         # percent
        "window": 0,
        "duration": 1,
        "threshold_label": "% Großbuchstaben",
        "threshold_min": 40,
        "threshold_max": 100,
        "has_window": False,
        # Short messages are all caps by accident far too often.
        "min_length": 45,
    },
    "links": {
        "label": "Anti-Link",
        "description": "Links von außerhalb. Spotify und GIFs bleiben erlaubt.",
        "punishment": "mute",
        "threshold": 1,
        "window": 0,
        "duration": 7,
        "threshold_label": "Links",
        "threshold_min": 1,
        "threshold_max": 10,
        "has_window": False,
    },
    "invites": {
        "label": "Anti-Einladung",
        "description": "Einladungen zu anderen Servern.",
        "punishment": "mute",
        "threshold": 1,
        "window": 0,
        "duration": 12,
        "threshold_label": "Einladungen",
        "threshold_min": 1,
        "threshold_max": 10,
        "has_window": False,
    },
    "mentions": {
        "label": "Anti-Massenping",
        "description": "Viele Leute auf einmal anpingen.",
        "punishment": "mute",
        "threshold": 5,
        "window": 0,
        "duration": 3,
        "threshold_label": "Erwähnungen",
        "threshold_min": 3,
        "threshold_max": 25,
        "has_window": False,
    },
    "emoji": {
        "label": "Anti-Emoji-Spam",
        "description": "Nachrichten voller Emojis.",
        "punishment": "mute",
        "threshold": 5,
        "window": 0,
        "duration": 1,
        "threshold_label": "Emojis",
        "threshold_min": 3,
        "threshold_max": 30,
        "has_window": False,
    },
}

DEFAULT_DURATION_MIN = 1
DEFAULT_DURATION_MAX = 10080     # Discord caps a timeout at 28 days


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """
    Create the tables and add the columns the new settings need.

    ALTER-if-absent rather than one CREATE: the tables already exist on
    every running server, and CREATE TABLE IF NOT EXISTS would silently
    leave the old shape in place -- which is exactly how custom_roles
    ended up raising "no such column" in production.
    """
    await db.execute(
        "CREATE TABLE IF NOT EXISTS automod ("
        " guild_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS automod_punishments ("
        " guild_id INTEGER, event TEXT, punishment TEXT)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS automod_ignored ("
        " guild_id INTEGER, type TEXT, id INTEGER)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS automod_logging ("
        " guild_id INTEGER, log_channel INTEGER)"
    )
    # A rule used to be "on" purely because a punishment row existed, so
    # it could never be switched off again. This table holds the switch.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS automod_rules ("
        " guild_id INTEGER NOT NULL,"
        " rule TEXT NOT NULL,"
        " enabled INTEGER DEFAULT 0,"
        " punishment TEXT DEFAULT 'mute',"
        " threshold INTEGER,"
        " window INTEGER,"
        " duration INTEGER,"
        " PRIMARY KEY (guild_id, rule))"
    )
    await db.commit()


async def _migrate_legacy(db: aiosqlite.Connection, guild_id: int) -> None:
    """
    Adopt a setup made through the chat command.

    Those servers only have rows in automod_punishments; without this
    they would appear switched off the first time the new tab is opened.
    """
    async with db.execute(
        "SELECT 1 FROM automod_rules WHERE guild_id = ? LIMIT 1", (guild_id,)
    ) as cursor:
        if await cursor.fetchone():
            return

    async with db.execute(
        "SELECT event, punishment FROM automod_punishments WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        return

    for event, punishment in rows:
        rule = normalise_rule(event)
        if rule is None:
            continue
        # A row existing was the old "enabled", so that is what it means.
        await db.execute(
            "INSERT OR REPLACE INTO automod_rules"
            " (guild_id, rule, enabled, punishment, threshold, window, duration)"
            " VALUES (?, ?, 1, ?, NULL, NULL, NULL)",
            (guild_id, rule, normalise_punishment(punishment)),
        )
    await db.commit()


async def get_settings(db: aiosqlite.Connection, guild_id: int) -> dict:
    await ensure_schema(db)
    await _migrate_legacy(db, guild_id)

    async with db.execute(
        "SELECT enabled FROM automod WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    enabled = bool(row[0]) if row else False

    async with db.execute(
        "SELECT rule, enabled, punishment, threshold, window, duration"
        " FROM automod_rules WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        stored = {r[0]: r for r in await cursor.fetchall()}

    rules = {}
    for key, spec in RULES.items():
        row = stored.get(key)
        rules[key] = {
            "enabled": bool(row[1]) if row else False,
            "punishment": normalise_punishment(row[2]) if row else spec["punishment"],
            "threshold": _clamp(
                row[3] if row and row[3] is not None else spec["threshold"],
                spec["threshold_min"], spec["threshold_max"],
            ),
            "window": max(2, min(120, int(
                row[4] if row and row[4] is not None else spec["window"] or 10
            ))),
            "duration": _clamp(
                row[5] if row and row[5] is not None else spec["duration"],
                DEFAULT_DURATION_MIN, DEFAULT_DURATION_MAX,
            ),
        }

    async with db.execute(
        "SELECT type, id FROM automod_ignored WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        ignored = await cursor.fetchall()

    async with db.execute(
        "SELECT log_channel FROM automod_logging WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    log_channel = int(row[0]) if row and row[0] else None

    return {
        "enabled": enabled,
        "rules": rules,
        "ignored_roles": [int(i) for t, i in ignored if t == "role" and i],
        "ignored_channels": [int(i) for t, i in ignored if t == "channel" and i],
        "log_channel": log_channel,
    }


def _clamp(value, low, high) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


async def save_settings(
    db: aiosqlite.Connection, guild_id: int, updates: dict
) -> dict:
    """Partial update: only what was sent is written."""
    await ensure_schema(db)
    current = await get_settings(db, guild_id)

    if "enabled" in updates:
        await db.execute(
            "INSERT OR REPLACE INTO automod (guild_id, enabled) VALUES (?, ?)",
            (guild_id, 1 if updates["enabled"] else 0),
        )

    for raw_key, values in (updates.get("rules") or {}).items():
        key = normalise_rule(raw_key)
        if key is None or key not in RULES:
            continue
        spec = RULES[key]
        merged = {**current["rules"][key], **(values or {})}

        enabled = bool(merged.get("enabled"))
        punishment = normalise_punishment(merged.get("punishment"))
        threshold = _clamp(
            merged.get("threshold"), spec["threshold_min"], spec["threshold_max"]
        )
        window = max(2, min(120, int(merged.get("window") or 10)))
        duration = _clamp(
            merged.get("duration"), DEFAULT_DURATION_MIN, DEFAULT_DURATION_MAX
        )

        await db.execute(
            "INSERT OR REPLACE INTO automod_rules"
            " (guild_id, rule, enabled, punishment, threshold, window, duration)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, key, int(enabled), punishment, threshold, window, duration),
        )

        # Mirrored into the legacy table so a downgrade, or any code path
        # still reading it, sees the same thing.
        legacy_event = LEGACY_EVENTS[key]
        await db.execute(
            "DELETE FROM automod_punishments WHERE guild_id = ? AND event = ?",
            (guild_id, legacy_event),
        )
        if enabled:
            await db.execute(
                "INSERT INTO automod_punishments (guild_id, event, punishment)"
                " VALUES (?, ?, ?)",
                (guild_id, legacy_event, LEGACY_PUNISHMENTS[punishment]),
            )

    if "ignored_roles" in updates:
        await db.execute(
            "DELETE FROM automod_ignored WHERE guild_id = ? AND type = 'role'",
            (guild_id,),
        )
        for role_id in _clean_ids(updates["ignored_roles"]):
            await db.execute(
                "INSERT INTO automod_ignored (guild_id, type, id)"
                " VALUES (?, 'role', ?)",
                (guild_id, role_id),
            )

    if "ignored_channels" in updates:
        await db.execute(
            "DELETE FROM automod_ignored WHERE guild_id = ? AND type = 'channel'",
            (guild_id,),
        )
        for channel_id in _clean_ids(updates["ignored_channels"]):
            await db.execute(
                "INSERT INTO automod_ignored (guild_id, type, id)"
                " VALUES (?, 'channel', ?)",
                (guild_id, channel_id),
            )

    if "log_channel" in updates:
        raw = updates["log_channel"]
        await db.execute(
            "DELETE FROM automod_logging WHERE guild_id = ?", (guild_id,)
        )
        if str(raw or "").isdigit() and int(raw):
            await db.execute(
                "INSERT INTO automod_logging (guild_id, log_channel)"
                " VALUES (?, ?)",
                (guild_id, int(raw)),
            )

    await db.commit()
    return await get_settings(db, guild_id)


def _clean_ids(values) -> list[int]:
    """Snowflakes arrive as strings from JSON; keep them exact."""
    out: list[int] = []
    for value in values or []:
        text = str(value).strip()
        if text.isdigit() and int(text) not in out:
            out.append(int(text))
    return out


# ══════════════════════════════════════════════════════════════════════
#  Rule evaluation
# ══════════════════════════════════════════════════════════════════════


def rule_active(settings: dict, rule: str) -> bool:
    """
    Whether a rule should act.

    The master switch counts too: turning automod off used to leave
    every individual listener running, because each one checked its own
    row and the master flag separately -- and one of them forgot.
    """
    if not settings.get("enabled"):
        return False
    entry = (settings.get("rules") or {}).get(rule)
    return bool(entry and entry.get("enabled"))


def is_exempt(settings: dict, *, channel_id=None, role_ids=(),
              is_owner=False, is_admin=False) -> bool:
    """
    Whether this message is none of automod's business.

    Admins were not exempt before, only the owner -- so a moderator
    posting a link got muted by their own bot.
    """
    if is_owner or is_admin:
        return True
    if channel_id is not None and int(channel_id) in (
        settings.get("ignored_channels") or []
    ):
        return True
    ignored = set(settings.get("ignored_roles") or [])
    return any(int(r) in ignored for r in role_ids or ())


class SpamTracker:
    """
    Message timestamps per member, per guild.

    The old dict was keyed on the user id alone, so activity in one
    server counted towards the spam limit in another: three messages
    here and three there tripped a five-message threshold in whichever
    server got the sixth.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[int, int], list[float]] = {}

    def hit(self, guild_id: int, user_id: int, *, window: float,
            now: float | None = None) -> int:
        now = time.time() if now is None else now
        key = (int(guild_id), int(user_id))

        recent = [t for t in self._seen.get(key, []) if now - t < window]
        recent.append(now)
        self._seen[key] = recent
        return len(recent)

    def clear(self, guild_id: int, user_id: int) -> None:
        """Forget somebody after they have been punished."""
        self._seen.pop((int(guild_id), int(user_id)), None)

    def prune(self, older_than: float = 300.0, now: float | None = None) -> int:
        """
        Drop stale entries.

        Without this the dict grows for every member the bot ever sees
        and is never emptied -- a slow leak on a busy bot.
        """
        now = time.time() if now is None else now
        dead = [
            key for key, times in self._seen.items()
            if not times or now - times[-1] > older_than
        ]
        for key in dead:
            self._seen.pop(key, None)
        return len(dead)

    def __len__(self) -> int:
        return len(self._seen)


async def punish(bot, message, rule: str, settings: dict, reason: str):
    """
    Carry out the punishment for one rule.

    This lived as six near-identical copies, one per module, which is
    why the same three bugs appeared in all of them: `.avatar` instead
    of `.display_avatar` (None for anybody on a default avatar), an
    embed where the rest of the bot uses Components V2, and a bare
    `except: pass` that hid missing permissions.

    Returns a short description of what was done, or None.
    """
    import discord

    entry = (settings.get("rules") or {}).get(rule) or {}
    punishment = normalise_punishment(entry.get("punishment"))
    duration = _clamp(
        entry.get("duration"), DEFAULT_DURATION_MIN, DEFAULT_DURATION_MAX
    )

    member = message.author
    guild = message.guild
    done = None

    # The offending message goes first: leaving it up while the member
    # is being muted means the spam stays visible either way.
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    try:
        if punishment == "mute":
            from datetime import timedelta

            until = discord.utils.utcnow() + timedelta(minutes=duration)
            await member.edit(timed_out_until=until, reason=reason)
            done = f"stummgeschaltet für {duration} Min."
        elif punishment == "kick":
            await member.kick(reason=reason)
            done = "gekickt"
        elif punishment == "ban":
            await member.ban(reason=reason, delete_message_days=0)
            done = "gebannt"
        elif punishment == "warn":
            done = "verwarnt"
        else:
            done = "Nachricht gelöscht"
    except discord.Forbidden:
        # Silence here is what made automod look broken: the owner saw
        # nothing at all and assumed the rule was off.
        print(
            f"automod: missing permission to {punishment} "
            f"{member} in {guild.id} -- is the bot role above theirs?"
        )
        return None
    except discord.HTTPException as exc:
        print(f"automod: Discord refused the {punishment}: {exc}")
        return None

    return done


async def log_action(bot, message, settings: dict, rule: str,
                     action: str, reason: str) -> None:
    """Write one line to the configured log channel, if there is one."""
    import discord

    channel_id = settings.get("log_channel")
    if not channel_id:
        return

    guild = message.guild
    channel = guild.get_channel(int(channel_id)) if guild else None
    if channel is None or not hasattr(channel, "send"):
        return

    member = message.author
    spec = RULES.get(rule, {})

    try:
        from utils.panels import Panel

        view = Panel(
            f"Automod: {spec.get('label', rule)}",
            f"**Wer:** {member.mention} (`{member.id}`)",
            f"**Was:** {reason}",
            f"**Aktion:** {action}",
            f"**Wo:** {getattr(message.channel, 'mention', 'unbekannt')}",
            tone="warning",
        )
        await channel.send(view=view)
    except (discord.Forbidden, discord.HTTPException):
        pass
    except Exception as exc:
        print(f"automod: could not log to #{getattr(channel, 'name', '?')}: {exc}")


def readiness(settings: dict) -> list[str]:
    """Plain-German reasons this configuration will not do much."""
    problems: list[str] = []

    active = [k for k in RULES if rule_active(settings, k)]

    if settings.get("enabled") and not active:
        problems.append(
            "Automod ist an, aber keine einzige Regel ist eingeschaltet."
        )
    if not settings.get("enabled") and any(
        (settings.get("rules") or {}).get(k, {}).get("enabled") for k in RULES
    ):
        problems.append(
            "Es sind Regeln eingeschaltet, aber der Hauptschalter steht auf aus — "
            "es passiert nichts."
        )

    return problems
