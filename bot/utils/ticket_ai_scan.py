"""Fast, bounded local Ticket AI server reading; raw scans never go to AI."""
from __future__ import annotations
import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
import aiosqlite
from api import config_transfer
from utils import ticket_ai

DB = "db/ticket.db"
SCAN_CONCURRENCY = 4
MESSAGE_LIMIT = 300
ARCHIVE_LIMIT = 50
_SECRET_KEYS = ("token", "secret", "password", "webhook", "api_key", "apikey", "private_key", "code")
_SECRET_PATTERNS = (
    re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I),
    re.compile(r"\bgsk_[0-9A-Za-z_-]+\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"),
    re.compile(r"\b(?:mfa\.)?[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b"),
)

def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[GEHEIMNIS ENTFERNT]", text)
    return text

def _opaque(text: str) -> bool:
    return len(re.findall(r"\\x[0-9a-fA-F]{2}", text)) >= 4 or bool(re.search(r"(?:[A-Za-z0-9+/]{300,}={0,2}|data:[^;]+;base64,)", text))

def clean_draft(text: str) -> str:
    """Also filter contaminated previews cached by an older deployment."""
    return "\n".join(line for line in text.splitlines() if not _opaque(line))

def _safe_config(value: Any, path: str = "") -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            name = str(key); next_path = f"{path}.{name}" if path else name
            if any(secret in name.lower() for secret in _SECRET_KEYS) or "backup" in name.lower() or "ticket_ai_" in next_path:
                continue
            filtered = _safe_config(child, next_path)
            if filtered is not None and filtered != {} and filtered != []:
                result[name] = filtered
        return result
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _safe_config(item, path)) not in (None, {}, [])]
    if isinstance(value, str):
        return None if _opaque(value) else _redact(value[:4000])
    return value if value is None or isinstance(value, (int, float, bool)) else None

async def _set_job(guild_id: int, **fields: Any) -> None:
    if not fields:
        return
    async with aiosqlite.connect(DB, timeout=10) as db:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        await db.execute(f"UPDATE ticket_ai_scan_jobs SET {assignments}, updated_at=? WHERE guild_id=?", (*fields.values(), int(time.time()), guild_id))
        await db.commit()

def _limit_knowledge(text: str, limit: int = ticket_ai.MAX_KNOWLEDGE_BYTES) -> str:
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")

async def run_scan(guild_id: int, bot) -> None:
    warnings: list[dict] = []; warning_keys = set()
    progress = skipped = message_count = total = 0
    results: dict[int, str] = {}
    write_lock = asyncio.Lock(); semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
    configuration = ""

    def warn(code: str, channel=""):
        key = (code, str(channel)[:100])
        if key not in warning_keys and len(warnings) < 100:
            warning_keys.add(key); warnings.append({"code": key[0], "channel": key[1]})

    def bounded(text, limit):
        if len(text.encode("utf-8")) > limit: warn("source_limit")
        return _limit_knowledge(text, limit)

    try:
        guild = bot.get_guild(guild_id)
        if guild is None: raise RuntimeError("Der Bot ist nicht auf diesem Server.")
        await _set_job(guild_id, status="running", progress=0, total_channels=0, message_count=0, skipped_channels=0, warnings="[]", current_channel="preparing", error="", draft="")
        after = datetime.now(timezone.utc) - timedelta(days=30)
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT channel_id FROM open_tickets WHERE guild_id=?", (guild_id,)) as cur:
                ticket_ids = {int(row[0]) for row in await cur.fetchall()}
        channels = [c for c in getattr(guild, "text_channels", []) if c.id not in ticket_ids]
        scan_channels = list(channels); known_ids = {c.id for c in scan_channels}
        def add_thread(thread):
            if thread.id not in known_ids and thread.id not in ticket_ids and getattr(thread, "parent_id", None) not in ticket_ids:
                scan_channels.append(thread); known_ids.add(thread.id)
        for thread in getattr(guild, "threads", []): add_thread(thread)
        metadata = [f"# SERVER\n{guild.name}", str(getattr(guild, "description", None) or "")]
        metadata.append("## KANÄLE / CHANNELS\n" + "\n".join(f"- #{c.name}" + (f": {c.topic}" if getattr(c, "topic", None) else "") for c in getattr(guild, "channels", []) if c.id not in ticket_ids))
        metadata.append("## ROLLEN / ROLES\n" + ", ".join(r.name for r in getattr(guild, "roles", []) if not r.is_default()))
        metadata_text = bounded(_redact("\n\n".join(metadata)), 10000)

        async def read_config():
            nonlocal configuration
            try:
                exported = await asyncio.wait_for(config_transfer.export_guild(guild_id, include_user_data=False, readable_only=True), timeout=15)
                if exported.get("summary", {}).get("truncated_tables"): warn("config_limit")
                clean = _safe_config(exported.get("databases", {}))
                configuration = bounded("## DASHBOARD-EINSTELLUNGEN / DASHBOARD SETTINGS\n" + json.dumps(clean, ensure_ascii=False, indent=2), 15000)
            except Exception: warn("dashboard_unavailable")

        async def discover(parent):
            if parent.id in ticket_ids or not getattr(parent, "archived_threads", None): return
            async with semaphore:
                try:
                    async with asyncio.timeout(4):
                        count = 0
                        async for thread in parent.archived_threads(limit=ARCHIVE_LIMIT + 1):
                            archived_at = getattr(thread, "archive_timestamp", None)
                            if archived_at and archived_at < after: break
                            count += 1
                            if count > ARCHIVE_LIMIT: warn("archive_limit", parent.name); break
                            add_thread(thread)
                except TimeoutError: warn("archive_timeout", parent.name)
                except Exception: warn("archive_unavailable", parent.name)

        async def read_channel(index, channel):
            nonlocal progress, skipped, message_count
            async with semaphore:
                local_count = 0; await_report = True; lines = []
                try:
                    permission = channel.permissions_for(guild.me) if guild.me is not None else None
                    if permission is not None and (not getattr(permission, "view_channel", True) or not permission.read_message_history):
                        skipped += 1; warn("history_permission", channel.name)
                    elif not getattr(getattr(bot, "intents", None), "message_content", True): skipped += 1
                    else:
                        used = seen = 0
                        # Give each channel room instead of stopping the entire
                        # scan when one busy channel fills its share.
                        budget = 6000
                        async with asyncio.timeout(10):
                            async for message in channel.history(limit=MESSAGE_LIMIT + 1, after=after, oldest_first=False):
                                seen += 1
                                if seen > MESSAGE_LIMIT: warn("history_limit", channel.name); break
                                author = message.author
                                admin = bool(getattr(getattr(author, "guild_permissions", None), "administrator", False))
                                if author.bot or not (author.id == guild.owner_id or admin): continue
                                content = _redact((message.content or "").strip())
                                if not content or _opaque(content): continue
                                block = f"#{channel.name} | {message.created_at.isoformat()}\n{content}\n\n"
                                if used + len(block.encode("utf-8")) > budget:
                                    warn("channel_budget", channel.name)
                                    if not lines:
                                        lines.append(_limit_knowledge(block,budget)); local_count += 1
                                    break
                                lines.append(block); used += len(block.encode("utf-8")); local_count += 1
                except TimeoutError: skipped += 1; warn("history_timeout", channel.name)
                except asyncio.CancelledError:
                    await_report = False; raise
                except Exception: skipped += 1; warn("channel_unavailable", channel.name)
                finally:
                    results[index] = "".join(lines).strip()
                    if await_report:
                        message_count += local_count; progress += 1
                        async with write_lock:
                            await _set_job(guild_id, progress=progress, message_count=message_count, skipped_channels=skipped, current_channel=channel.name, warnings=json.dumps(warnings))

        async def collect():
            nonlocal total
            parents = channels + [p for p in getattr(guild, "forums", []) if p.id not in ticket_ids]
            initial = list(scan_channels)
            total = len(initial)
            await _set_job(guild_id, total_channels=total, current_channel="")
            if not getattr(getattr(bot, "intents", None), "message_content", True): warn("message_content_disabled")
            await asyncio.gather(read_config(), asyncio.gather(*(read_channel(i,c) for i,c in enumerate(initial))), asyncio.gather(*(discover(p) for p in parents)))
            total = len(scan_channels)
            await _set_job(guild_id, total_channels=total)
            await asyncio.gather(*(read_channel(i,c) for i,c in enumerate(scan_channels) if i >= len(initial)))
        try:
            async with asyncio.timeout(90): await collect()
        except TimeoutError: warn("read_timeout")
        if not message_count: warn("no_admin_messages")
        populated = [results[i] for i in sorted(results) if results[i]]
        share = 72000 // max(len(populated),1)
        messages = "\n\n".join(bounded(text,share) for text in populated)
        draft = _limit_knowledge("\n\n".join(part for part in ["# ADMIN-NACHRICHTEN / ADMIN MESSAGES\n" + messages if messages else "", metadata_text, configuration] if part))
        if not draft.strip(): raise RuntimeError("Keine lesbaren Serverdaten gefunden.")
        await _set_job(guild_id, status="completed", draft=draft, error="", current_channel="", progress=progress, total_channels=total, warnings=json.dumps(warnings), skipped_channels=skipped, message_count=message_count)
    except Exception as exc:
        await _set_job(guild_id, status="failed", error=_redact(str(exc))[:500], current_channel="", warnings=json.dumps(warnings), skipped_channels=skipped)
        print(f"[ticket-ai-scan] failed for {guild_id}: {type(exc).__name__}")
