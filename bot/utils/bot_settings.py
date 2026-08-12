"""
Bot-wide settings that used to be hardcoded.

university_bot.py had the stats and log channel IDs written directly into the
source, pointing at the original developer's server. On any other deployment
they silently did nothing.

Values are stored in SQLite, cached in memory and editable from the dashboard.
An environment variable of the same name still wins, so existing setups keep
working without a migration.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import aiosqlite

DB_PATH = "db/admin_config.db"


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str
    description: str
    kind: str          # "channel" | "text" | "bool" | "number"
    default: str = ""
    env_var: str = ""


SETTINGS: tuple[Setting, ...] = (
    Setting(
        "stats_server_channel", "Server Count Channel", "Statistics",
        "Voice or text channel renamed to 'Servers: N' every 10 minutes.",
        "channel", env_var="SERVER_COUNT_CHANNEL_ID",
    ),
    Setting(
        "stats_user_channel", "User Count Channel", "Statistics",
        "Channel renamed to 'Users: N' every 10 minutes.",
        "channel", env_var="USER_COUNT_CHANNEL_ID",
    ),
    Setting(
        "stats_interval", "Update Interval", "Statistics",
        "How often the counters refresh, in seconds. Discord rate limits "
        "channel renames to roughly twice per 10 minutes.",
        "number", default="600",
    ),
    Setting(
        "guild_log_channel", "Guild Join/Leave Log", "Logging",
        "Channel that receives a message when the bot joins or leaves a server.",
        "channel", env_var="LOG_CHANNEL_ID",
    ),
    Setting(
        "command_log_webhook", "Command Log Webhook", "Logging",
        "Webhook URL that receives every executed command. Leave empty to disable.",
        "text", env_var="CMD_WEBHOOK_URL",
    ),
    Setting(
        "error_log_channel", "Error Log Channel", "Logging",
        "Channel for unhandled command errors.",
        "channel",
    ),
    Setting(
        "report_channel", "Bug Report Channel", "Logging",
        "Where /report sends bug reports. Without one the command tells "
        "the reporter it could not be delivered instead of failing "
        "silently.",
        "channel", env_var="REPORT_CHANNEL_ID",
    ),
    Setting(
        "premium_role", "Premium Role", "Premium",
        "Role given to anyone with an active licence, on the support "
        "server. It is taken away again when the licence expires or is "
        "revoked. Leave empty to hand out no role at all.",
        "text", env_var="PREMIUM_ROLE_ID",
    ),
    Setting(
        "support_server_invite", "Support Server", "Branding",
        "Invite link shown in help messages and the dashboard footer.",
        "text", default="https://discord.gg/F3TedBAVZT",
    ),
    Setting(
        "bot_invite_url", "Bot Invite URL", "Branding",
        "Link used by the 'Add to Server' buttons.",
        "text", env_var="NEXT_PUBLIC_BOT_INVITE_URL",
    ),
    Setting(
        "default_prefix", "Default Prefix", "Behaviour",
        "Prefix new servers start with.",
        "text", default=">",
    ),
    Setting(
        "status_rotation", "Rotate Status", "Behaviour",
        "Cycle through the presence messages every 30 seconds.",
        "bool", default="true",
    ),
)

SETTINGS_BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}
SETTING_GROUPS: tuple[str, ...] = tuple(dict.fromkeys(s.group for s in SETTINGS))

_values: dict[str, str] = {}
_loaded = False
_lock = asyncio.Lock()


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS bot_settings ("
        " key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')"
    )
    await db.commit()


async def load(force: bool = False) -> dict[str, str]:
    global _loaded

    async with _lock:
        if _loaded and not force:
            return dict(_values)

        os.makedirs("db", exist_ok=True)
        stored: dict[str, str] = {}
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await _ensure_table(db)
                async with db.execute("SELECT key, value FROM bot_settings") as cursor:
                    async for key, value in cursor:
                        if key in SETTINGS_BY_KEY:
                            stored[key] = value
        except Exception as exc:
            print(f"[bot_settings] load failed: {exc}")

        _values.clear()
        for setting in SETTINGS:
            _values[setting.key] = stored.get(setting.key, setting.default)
        _loaded = True
        return dict(_values)


def get(key: str, fallback: str = "") -> str:
    """
    Read a setting.

    Precedence: environment variable > dashboard value > declared default.
    The environment keeps winning so existing deployments are not surprised
    by a value someone typed into the dashboard.
    """
    setting = SETTINGS_BY_KEY.get(key)
    if setting is None:
        return fallback

    if setting.env_var:
        env_value = os.getenv(setting.env_var, "").strip()
        if env_value:
            return env_value

    value = _values.get(key, setting.default)
    return value if value else fallback


def get_int(key: str, fallback: int = 0) -> int:
    raw = get(key, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def get_bool(key: str, fallback: bool = False) -> bool:
    raw = get(key, "").strip().lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    return fallback


async def set_values(updates: dict[str, str]) -> dict[str, str]:
    await load()
    clean = {k: str(v) for k, v in updates.items() if k in SETTINGS_BY_KEY}
    if not clean:
        return {}

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        for key, value in clean.items():
            await db.execute(
                "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()

    _values.update(clean)
    return clean


def describe() -> list[dict]:
    """Settings plus their current state, for the dashboard."""
    entries = []
    for setting in SETTINGS:
        env_value = os.getenv(setting.env_var, "").strip() if setting.env_var else ""
        entries.append(
            {
                "key": setting.key,
                "label": setting.label,
                "group": setting.group,
                "description": setting.description,
                "kind": setting.kind,
                "default": setting.default,
                "value": _values.get(setting.key, setting.default),
                "effective": get(setting.key),
                # When an env var is set it overrides the dashboard, so the
                # field is shown read-only with an explanation.
                "env_var": setting.env_var,
                "env_override": bool(env_value),
            }
        )
    return entries
