"""Build a reviewable Ticket-AI knowledge draft from one Discord server."""

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


def _safe_config(value: Any, path: str = "") -> Any:
    """Remove credentials and Ticket-AI's own old knowledge from the snapshot."""
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            name = str(key)
            low = name.lower()
            next_path = f"{path}.{name}" if path else name
            if any(secret in low for secret in _SECRET_KEYS):
                continue
            if "ticket_ai_" in next_path:
                continue
            result[name] = _safe_config(child, next_path)
        return result
    if isinstance(value, list):
        return [_safe_config(item, path) for item in value]
    if isinstance(value, str):
        return _redact(value[:4000])
    return value


async def _set_job(guild_id: int, **fields: Any) -> None:
    if not fields:
        return
    async with aiosqlite.connect(DB) as db:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        await db.execute(
            f"UPDATE ticket_ai_scan_jobs SET {assignments}, updated_at = ? WHERE guild_id = ?",
            (*fields.values(), int(time.time()), guild_id),
        )
        await db.commit()


def _limit_knowledge(text: str) -> str:
    raw = text.encode("utf-8")[:ticket_ai.MAX_KNOWLEDGE_BYTES]
    return raw.decode("utf-8", errors="ignore")


async def run_scan(guild_id: int, bot) -> None:
    """Read a reviewable local draft. Raw server data never leaves this process."""
    warnings: list[dict] = []
    parts: list[str] = []
    message_count = skipped = source_size = 0

    def warn(code, channel=""):
        if len(warnings) < 100: warnings.append({"code": code, "channel": str(channel)[:100]})

    def append_source(label, text):
        nonlocal source_size
        remaining = ticket_ai.MAX_KNOWLEDGE_BYTES - source_size
        raw = (f"{label}\n" + _redact(text) + "\n\n").encode("utf-8")
        if len(raw) > remaining: warn("source_limit")
        text = raw[:max(0, remaining)].decode("utf-8", errors="ignore")
        source_size += len(text.encode("utf-8"))
        if text: parts.append(text.rstrip())

    try:
        guild = bot.get_guild(guild_id)
        if guild is None: raise RuntimeError("Der Bot ist nicht auf diesem Server.")
        await _set_job(guild_id, status="running", progress=0, total_channels=0,
                       message_count=0, skipped_channels=0, warnings="[]", current_channel="preparing", error="", draft="")
        after = datetime.now(timezone.utc) - timedelta(days=30)
        ticket_ids: set[int] = set()
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                tables = {row[0] for row in await cur.fetchall()}
            if "open_tickets" in tables:
                async with db.execute("SELECT channel_id FROM open_tickets WHERE guild_id=?", (guild_id,)) as cur:
                    ticket_ids = {int(row[0]) for row in await cur.fetchall()}
        channels = list(getattr(guild, "text_channels", []) or [])
        scan_channels = [c for c in channels if c.id not in ticket_ids]
        known_ids = {c.id for c in scan_channels}
        for thread in list(getattr(guild, "threads", []) or []):
            if thread.id not in known_ids and thread.id not in ticket_ids and getattr(thread, "parent_id", None) not in ticket_ids:
                scan_channels.append(thread); known_ids.add(thread.id)
        metadata = {
            "server_name": guild.name, "server_id": str(guild.id),
            "description": getattr(guild, "description", None),
            "roles": [r.name for r in getattr(guild, "roles", []) if not r.is_default()],
            "channels": [{"name": c.name, "topic": getattr(c, "topic", None),
                          "category": getattr(getattr(c, "category", None), "name", None)}
                         for c in getattr(guild, "channels", []) if c.id not in ticket_ids],
        }
        append_source("SERVER-METADATEN", json.dumps(metadata, ensure_ascii=False, indent=2, default=str))
        try:
            exported = await asyncio.wait_for(config_transfer.export_guild(guild_id, include_user_data=False), timeout=25)
            append_source("DASHBOARD-EINSTELLUNGEN", json.dumps(_safe_config(exported.get("databases", {})), ensure_ascii=False, indent=2, default=str))
        except Exception: warn("dashboard_unavailable")
        if not getattr(getattr(bot, "intents", None), "message_content", True): warn("message_content_disabled")

        async def read_server():
            nonlocal message_count, skipped
            for parent in channels + list(getattr(guild, "forums", []) or []):
                if parent.id in ticket_ids: continue
                archived = getattr(parent, "archived_threads", None)
                if not archived: continue
                async def discover():
                    try:
                        async for thread in archived(limit=None):
                            archived_at = getattr(thread, "archive_timestamp", None)
                            if archived_at and archived_at < after: break
                            if thread.id not in known_ids and thread.id not in ticket_ids:
                                scan_channels.append(thread); known_ids.add(thread.id)
                    except Exception: warn("archive_unavailable", parent.name)
                try: await asyncio.wait_for(discover(), timeout=5)
                except TimeoutError: warn("archive_timeout", parent.name)
            await _set_job(guild_id, total_channels=len(scan_channels))
            for index, channel in enumerate(scan_channels):
                await _set_job(guild_id, current_channel=channel.name)
                try:
                    permission = channel.permissions_for(guild.me) if guild.me is not None else None
                    if permission is not None and (not getattr(permission, "view_channel", True) or not permission.read_message_history):
                        skipped += 1; warn("history_permission", channel.name)
                    else:
                        async def read_channel():
                            nonlocal message_count
                            async for message in channel.history(limit=None, after=after, oldest_first=True):
                                author = message.author
                                is_admin = bool(getattr(getattr(author, "guild_permissions", None), "administrator", False))
                                if author.bot or not (author.id == guild.owner_id or is_admin): continue
                                content = _redact((message.content or "").strip())
                                if not content: continue
                                append_source("ADMIN-NACHRICHTEN", f"#{channel.name} | {message.created_at.isoformat()}\n{content}")
                                message_count += 1
                                if source_size >= ticket_ai.MAX_KNOWLEDGE_BYTES: return
                        try: await asyncio.wait_for(read_channel(), timeout=20)
                        except TimeoutError: skipped += 1; warn("history_timeout", channel.name)
                except Exception:
                    skipped += 1; warn("channel_unavailable", channel.name)
                await _set_job(guild_id, progress=index+1, message_count=message_count,
                               skipped_channels=skipped, warnings=json.dumps(warnings))
                if source_size >= ticket_ai.MAX_KNOWLEDGE_BYTES:
                    warn("source_limit"); break
        try: await asyncio.wait_for(read_server(), timeout=240)
        except TimeoutError: warn("read_timeout")
        if not message_count: warn("no_admin_messages")
        draft = _limit_knowledge("\n\n".join(parts))
        if not draft.strip(): raise RuntimeError("Keine lesbaren Serverdaten gefunden.")
        await _set_job(guild_id, status="completed", draft=draft, error="", current_channel="",
                       warnings=json.dumps(warnings), skipped_channels=skipped, message_count=message_count)
    except Exception as exc:
        await _set_job(guild_id, status="failed", error=_redact(str(exc))[:500], current_channel="",
                       warnings=json.dumps(warnings), skipped_channels=skipped)
        print(f"[ticket-ai-scan] failed for {guild_id}: {type(exc).__name__}")
