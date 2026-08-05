"""
Command usage statistics.

The bot had no idea which of its 235 commands anyone actually uses, so there
was no way to tell what to improve or retire. Every invocation is counted
here, in memory for speed and flushed to SQLite so the numbers survive a
restart.

Kept deliberately small: a counter per command, per guild and per day, plus
failures. No message content, no per-user tracking.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import aiosqlite

DB_PATH = "db/admin_config.db"

# Buffered counters, flushed periodically so a busy bot does not hit SQLite
# on every single command.
_pending: dict[tuple[str, str, str], int] = defaultdict(int)
_pending_failures: dict[tuple[str, str, str], int] = defaultdict(int)
_lock = asyncio.Lock()
_last_flush = time.monotonic()

FLUSH_INTERVAL = 60  # seconds


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS command_usage ("
        " command TEXT NOT NULL,"
        " guild_id TEXT NOT NULL DEFAULT '',"
        " day TEXT NOT NULL,"
        " uses INTEGER NOT NULL DEFAULT 0,"
        " failures INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (command, guild_id, day))"
    )
    await db.commit()


def record(command: str, guild_id: int | None, failed: bool = False) -> None:
    """
    Count one invocation. Cheap and synchronous — the flush happens later.
    """
    if not command:
        return
    key = (command, str(guild_id or ""), _today())
    if failed:
        _pending_failures[key] += 1
    else:
        _pending[key] += 1


async def flush(force: bool = False) -> int:
    """Write buffered counters to disk. Returns the number of rows touched."""
    global _last_flush

    if not force and time.monotonic() - _last_flush < FLUSH_INTERVAL:
        return 0

    async with _lock:
        if not _pending and not _pending_failures:
            _last_flush = time.monotonic()
            return 0

        uses = dict(_pending)
        failures = dict(_pending_failures)
        _pending.clear()
        _pending_failures.clear()
        _last_flush = time.monotonic()

    keys = set(uses) | set(failures)
    os.makedirs("db", exist_ok=True)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await _ensure_table(db)
            for key in keys:
                command, guild_id, day = key
                await db.execute(
                    "INSERT INTO command_usage (command, guild_id, day, uses, failures)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(command, guild_id, day) DO UPDATE SET"
                    "   uses = uses + excluded.uses,"
                    "   failures = failures + excluded.failures",
                    (command, guild_id, day, uses.get(key, 0), failures.get(key, 0)),
                )
            await db.commit()
    except Exception as exc:
        print(f"[command_stats] flush failed: {exc}")
        # Put the counters back so nothing is lost.
        async with _lock:
            for key, value in uses.items():
                _pending[key] += value
            for key, value in failures.items():
                _pending_failures[key] += value
        return 0

    return len(keys)


async def summary(guild_id: int | None = None, days: int = 30) -> dict:
    """Aggregated usage for the dashboard."""
    os.makedirs("db", exist_ok=True)
    await flush(force=True)

    where = "WHERE day >= date('now', ?)"
    params: list = [f"-{max(1, min(days, 365))} days"]
    if guild_id:
        where += " AND guild_id = ?"
        params.append(str(guild_id))

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await _ensure_table(db)

            async with db.execute(
                f"SELECT command, SUM(uses), SUM(failures) FROM command_usage {where}"
                " GROUP BY command ORDER BY SUM(uses) DESC",
                params,
            ) as cursor:
                rows = await cursor.fetchall()

            async with db.execute(
                f"SELECT day, SUM(uses) FROM command_usage {where} GROUP BY day ORDER BY day",
                params,
            ) as cursor:
                daily = await cursor.fetchall()

            async with db.execute(
                f"SELECT guild_id, SUM(uses) FROM command_usage {where}"
                " GROUP BY guild_id ORDER BY SUM(uses) DESC LIMIT 15",
                params,
            ) as cursor:
                per_guild = await cursor.fetchall()
    except Exception as exc:
        return {"error": str(exc), "commands": [], "daily": [], "guilds": []}

    commands = [
        {
            "command": row[0],
            "uses": int(row[1] or 0),
            "failures": int(row[2] or 0),
            "failure_rate": (
                round((row[2] or 0) / row[1] * 100, 1) if row[1] else 0.0
            ),
        }
        for row in rows
    ]

    total_uses = sum(c["uses"] for c in commands)
    total_failures = sum(c["failures"] for c in commands)

    return {
        "days": days,
        "total_uses": total_uses,
        "total_failures": total_failures,
        "unique_commands": len(commands),
        "commands": commands,
        "daily": [{"day": d, "uses": int(u or 0)} for d, u in daily],
        "guilds": [{"guild_id": g, "uses": int(u or 0)} for g, u in per_guild if g],
    }


def all_command_names(bot) -> list[str]:
    """Jeder Befehl, den der Bot anbietet -- Prefix *und* Slash.

    ``bot.walk_commands()`` liefert ausschliesslich Prefix-Befehle. Die
    Statistik verglich die Nutzung deshalb gegen eine Gesamtzahl, in der
    die dreiundsiebzig Slash-Befehle fehlten: im Dashboard stand "x von
    235", obwohl der Bot deutlich mehr anbietet, und kein einziger
    Slash-Befehl konnte je in der Liste "nie benutzt" auftauchen -- er
    stand gar nicht erst drin.

    Slash-Befehle tragen einen fuehrenden Schraegstrich, genau so wie
    sie gezaehlt werden. ``/ban`` und ``ban`` sind derselbe Befehl, aber
    nicht dieselbe Bedienung.
    """

    names: list[str] = []

    for command in bot.walk_commands():
        if not command.hidden:
            names.append(command.qualified_name)

    # Der Baum kann bei einem noch nicht fertig gestarteten Bot leer
    # oder gar nicht vorhanden sein. Das ist kein Fehler -- dann gibt es
    # eben nur die Prefix-Befehle.
    tree = getattr(bot, "tree", None)
    if tree is not None:
        try:
            for command in tree.walk_commands():
                # Gruppen sind keine aufrufbaren Befehle. Sie zaehlen
                # mit, waeren aber nie "benutzt" -- und stuenden dann
                # fuer immer in der Liste der ungenutzten.
                if hasattr(command, "walk_commands"):
                    continue
                names.append(f"/{command.qualified_name}")
        except Exception:
            pass

    return sorted(dict.fromkeys(names))


async def unused_commands(bot, days: int = 30) -> list[str]:
    """Commands that exist but were never called in the period."""
    data = await summary(days=days)
    used = {entry["command"] for entry in data.get("commands", [])}
    return [name for name in all_command_names(bot) if name not in used]
