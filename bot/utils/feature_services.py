"""
Background workers behind the global feature flags.

Every loop checks its own flag on each iteration, so toggling a flag in the
dashboard takes effect without restarting the bot. All state is kept in a
single `runtime` object that the /admin/health endpoint reads.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
import aiohttp

from utils import feature_flags as flags

DB_DIR = "db"
BACKUP_DIR = os.path.join(DB_DIR, "backups")


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read a positive integer from the environment, falling back safely."""
    try:
        return max(minimum, int(os.getenv(name, "").strip() or default))
    except (TypeError, ValueError):
        return default


# How many automatic snapshots to keep, and how often to take one.
# Configurable so a deployment with a persistent volume can keep more
# history than the default ephemeral setup.
BACKUP_KEEP = _env_int("BACKUP_KEEP", 3, 1)
BACKUP_INTERVAL = _env_int("BACKUP_INTERVAL_SECONDS", 21600, 300)


# ── Shared runtime state ──────────────────────────────────────────────────


@dataclass
class RuntimeState:
    started_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    shard_latency: dict[str, float] = field(default_factory=dict)
    lavalink_nodes: dict[str, str] = field(default_factory=dict)
    lavalink_reconnects: int = 0

    discord_status: str = "unknown"
    discord_incidents: list[str] = field(default_factory=list)

    integrity: dict[str, str] = field(default_factory=dict)
    last_backup_at: float | None = None
    last_cleanup_removed: int = 0

    failed_extensions: list[str] = field(default_factory=list)
    recovered_extensions: list[str] = field(default_factory=list)

    oauth_errors: int = 0
    session_warning: str | None = None

    command_errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    request_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    slow_requests: deque = field(default_factory=lambda: deque(maxlen=100))
    log_buffer: deque = field(default_factory=lambda: deque(maxlen=200))

    voice_sessions: dict[str, float] = field(default_factory=dict)
    voice_totals: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def snapshot(self) -> dict[str, Any]:
        return {
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "shard_latency": dict(self.shard_latency),
            "lavalink_nodes": dict(self.lavalink_nodes),
            "lavalink_reconnects": self.lavalink_reconnects,
            "discord_status": self.discord_status,
            "discord_incidents": list(self.discord_incidents),
            "integrity": dict(self.integrity),
            "last_backup_at": self.last_backup_at,
            "last_cleanup_removed": self.last_cleanup_removed,
            "failed_extensions": list(self.failed_extensions),
            "recovered_extensions": list(self.recovered_extensions),
            "oauth_errors": self.oauth_errors,
            "session_warning": self.session_warning,
            "command_errors": dict(self.command_errors),
            "request_stats": {k: dict(v) for k, v in self.request_stats.items()},
            "slow_requests": list(self.slow_requests),
            "voice_totals": dict(self.voice_totals),
        }


runtime = RuntimeState()


# ── Log capture (railway_log_watch) ───────────────────────────────────────


class RingBufferLogHandler(logging.Handler):
    """Keeps the most recent warnings and errors for the dashboard."""

    def emit(self, record: logging.LogRecord) -> None:
        if not flags.is_enabled("railway_log_watch"):
            return
        try:
            runtime.log_buffer.append(
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage()[:500],
                }
            )
        except Exception:
            pass


def install_log_capture() -> None:
    handler = RingBufferLogHandler(level=logging.WARNING)
    root = logging.getLogger()
    if not any(isinstance(h, RingBufferLogHandler) for h in root.handlers):
        root.addHandler(handler)


# ── API metrics (dashboard_performance_metrics / slow_query_detector) ─────

SLOW_REQUEST_MS = 1000.0


def record_request(path: str, duration_ms: float, status_code: int) -> None:
    if flags.is_enabled("dashboard_performance_metrics"):
        stats = runtime.request_stats.setdefault(
            path, {"count": 0, "total_ms": 0.0, "max_ms": 0.0, "errors": 0}
        )
        stats["count"] += 1
        stats["total_ms"] += duration_ms
        stats["max_ms"] = max(stats["max_ms"], duration_ms)
        stats["avg_ms"] = round(stats["total_ms"] / stats["count"], 2)
        if status_code >= 500:
            stats["errors"] += 1

    if flags.is_enabled("slow_query_detector") and duration_ms >= SLOW_REQUEST_MS:
        runtime.slow_requests.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "path": path,
                "duration_ms": round(duration_ms, 2),
                "status": status_code,
            }
        )


def record_oauth_error(detail: str = "") -> None:
    if flags.is_enabled("oauth_error_tracker"):
        runtime.oauth_errors += 1
        runtime.log_buffer.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "level": "WARNING",
                "logger": "oauth",
                "message": f"OAuth failure: {detail}"[:500],
            }
        )


def record_command_error(command_name: str, error_type: str) -> None:
    if flags.is_enabled("command_error_analytics"):
        runtime.command_errors[f"{command_name or 'unknown'}:{error_type}"] += 1


# ── Service implementation ────────────────────────────────────────────────


class FeatureServices:
    """Owns all flag-driven background tasks."""

    def __init__(self, bot):
        self.bot = bot
        self._tasks: list[asyncio.Task] = []
        self._expected_extensions: list[str] = []

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        install_log_capture()
        loops = (
            (self._heartbeat_loop, 15),
            (self._health_loop, 60),
            (self._discord_status_loop, 300),
            (self._integrity_loop, 3600),
            (self._backup_loop, BACKUP_INTERVAL),
            (self._cleanup_loop, 86400),
            (self._recovery_loop, 600),
            (self._announcement_loop, 60),
        )
        for coro, interval in loops:
            self._tasks.append(asyncio.create_task(self._runner(coro, interval)))

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def _runner(self, coro, interval: int) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await coro()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[feature_services] {coro.__name__} failed: {exc}")
            await asyncio.sleep(interval)

    # -- individual services ----------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """
        Liveness marker for auto_restart_on_deadlock.

        A separate watchdog thread compares this timestamp against wall clock
        time; if the event loop stalls the process exits so Railway restarts it.
        """
        runtime.last_heartbeat = time.time()

    async def _health_loop(self) -> None:
        if flags.is_enabled("shard_health_monitor"):
            latencies = {}
            try:
                for shard_id, shard in (self.bot.shards or {}).items():
                    latencies[str(shard_id)] = round(shard.latency * 1000, 2)
            except Exception:
                pass
            if not latencies:
                latencies = {"0": round(self.bot.latency * 1000, 2)}
            runtime.shard_latency = latencies

        if flags.is_enabled("lavalink_health_monitor"):
            await self._check_lavalink()

    async def _check_lavalink(self) -> None:
        try:
            import wavelink
        except ImportError:
            runtime.lavalink_nodes = {}
            return

        nodes: dict[str, str] = {}
        try:
            pool = getattr(wavelink, "Pool", None)
            node_map = getattr(pool, "nodes", {}) if pool else {}
            for identifier, node in dict(node_map).items():
                status = getattr(node, "status", None)
                nodes[str(identifier)] = getattr(status, "name", str(status))
        except Exception as exc:
            print(f"[feature_services] lavalink check failed: {exc}")
            return

        runtime.lavalink_nodes = nodes

        if not flags.is_enabled("music_node_failover"):
            return

        connected = any("connect" in state.lower() for state in nodes.values())
        if nodes and not connected:
            await self._reconnect_lavalink()

    async def _reconnect_lavalink(self) -> None:
        music = self.bot.get_cog("Music")
        connector = getattr(music, "connect_nodes", None) or getattr(music, "start_nodes", None)
        if not callable(connector):
            return
        try:
            result = connector()
            if asyncio.iscoroutine(result):
                await result
            runtime.lavalink_reconnects += 1
            print("[feature_services] Lavalink reconnect triggered by music_node_failover")
        except Exception as exc:
            print(f"[feature_services] lavalink reconnect failed: {exc}")

    async def _discord_status_loop(self) -> None:
        if not flags.is_enabled("discord_api_status_watch"):
            return
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://discordstatus.com/api/v2/summary.json") as resp:
                    if resp.status != 200:
                        runtime.discord_status = f"http {resp.status}"
                        return
                    payload = await resp.json()
        except Exception as exc:
            runtime.discord_status = "unreachable"
            print(f"[feature_services] discord status check failed: {exc}")
            return

        runtime.discord_status = payload.get("status", {}).get("description", "unknown")
        runtime.discord_incidents = [
            incident.get("name", "incident")
            for incident in payload.get("incidents", [])[:5]
        ]

    async def _integrity_loop(self) -> None:
        if not flags.is_enabled("database_integrity_scan"):
            return
        results: dict[str, str] = {}
        for path in sorted(glob.glob(os.path.join(DB_DIR, "*.db"))):
            name = os.path.basename(path)
            try:
                async with aiosqlite.connect(path) as db:
                    async with db.execute("PRAGMA integrity_check") as cursor:
                        row = await cursor.fetchone()
                results[name] = row[0] if row else "unknown"
            except Exception as exc:
                results[name] = f"error: {exc}"
        runtime.integrity = results

        broken = [name for name, value in results.items() if value != "ok"]
        if broken:
            logging.getLogger("feature_services").warning(
                "Database integrity problems: %s", ", ".join(broken)
            )

    async def _backup_loop(self) -> None:
        if not flags.is_enabled("database_backup_scheduler"):
            return

        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = os.path.join(BACKUP_DIR, stamp)
        os.makedirs(target, exist_ok=True)

        copied = 0
        for path in glob.glob(os.path.join(DB_DIR, "*.db")):
            try:
                # sqlite's own backup API keeps the copy consistent while the
                # bot keeps writing.
                async with aiosqlite.connect(path) as source:
                    async with aiosqlite.connect(
                        os.path.join(target, os.path.basename(path))
                    ) as destination:
                        await source.backup(destination)
                copied += 1
            except Exception:
                try:
                    shutil.copy2(path, target)
                    copied += 1
                except Exception as exc:
                    print(f"[feature_services] backup of {path} failed: {exc}")

        runtime.last_backup_at = time.time()

        # Retention: keep only the newest BACKUP_KEEP automatic snapshots.
        #
        # Safety copies taken before a restore or import are named
        # "pre-restore-*" / "pre-import-*". They are the user's undo and must
        # survive rotation, so they are excluded here. Sorting is by mtime
        # rather than by name, because the prefixes break lexical ordering.
        try:
            candidates = [
                d for d in glob.glob(os.path.join(BACKUP_DIR, "*"))
                if os.path.isdir(d) and not os.path.basename(d).startswith("pre-")
            ]
            candidates.sort(key=os.path.getmtime)
            for old in candidates[:-BACKUP_KEEP]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception as exc:
            print(f"[feature_services] backup rotation failed: {exc}")

        print(f"[feature_services] Backup complete: {copied} databases -> {target}")

    async def _cleanup_loop(self) -> None:
        if not flags.is_enabled("orphan_data_cleanup"):
            return

        active = {guild.id for guild in self.bot.guilds}
        if not active:
            return

        removed = 0
        for path in glob.glob(os.path.join(DB_DIR, "*.db")):
            try:
                async with aiosqlite.connect(path) as db:
                    async with db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ) as cursor:
                        tables = [row[0] for row in await cursor.fetchall()]

                    for table in tables:
                        async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                            columns = [row[1] for row in await cursor.fetchall()]
                        if "guild_id" not in columns:
                            continue

                        async with db.execute(
                            f"SELECT DISTINCT guild_id FROM [{table}]"
                        ) as cursor:
                            stored = [row[0] for row in await cursor.fetchall()]

                        stale = [
                            gid for gid in stored
                            if str(gid).isdigit() and int(gid) not in active
                        ]
                        for gid in stale:
                            await db.execute(f"DELETE FROM [{table}] WHERE guild_id = ?", (gid,))
                            removed += 1
                    await db.commit()
            except Exception as exc:
                print(f"[feature_services] cleanup of {path} failed: {exc}")

        runtime.last_cleanup_removed = removed
        if removed:
            print(f"[feature_services] Orphan cleanup removed {removed} guild rows")

    # -- module guard / recovery ------------------------------------------

    def record_expected_extensions(self, names: list[str]) -> None:
        self._expected_extensions = list(names)

    def record_failed_extension(self, name: str) -> None:
        if name not in runtime.failed_extensions:
            runtime.failed_extensions.append(name)

    async def _recovery_loop(self) -> None:
        if not flags.is_enabled("module_load_guard"):
            return
        if not runtime.failed_extensions:
            return
        if not flags.is_enabled("cog_auto_recovery"):
            return

        for name in list(runtime.failed_extensions):
            try:
                await self.bot.load_extension(name)
                runtime.failed_extensions.remove(name)
                runtime.recovered_extensions.append(name)
                print(f"[feature_services] Recovered extension {name}")
            except Exception as exc:
                print(f"[feature_services] Recovery of {name} still failing: {exc}")

    # -- announcements -----------------------------------------------------

    async def _announcement_loop(self) -> None:
        if not flags.is_enabled("global_announcement_scheduler"):
            return

        now = int(time.time())
        try:
            async with aiosqlite.connect("db/admin_config.db") as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS scheduled_announcements ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " message TEXT NOT NULL,"
                    " send_at INTEGER NOT NULL,"
                    " sent_at INTEGER)"
                )
                await db.commit()

                async with db.execute(
                    "SELECT id, message FROM scheduled_announcements "
                    "WHERE sent_at IS NULL AND send_at <= ? ORDER BY send_at LIMIT 3",
                    (now,),
                ) as cursor:
                    due = await cursor.fetchall()

                for announcement_id, message in due:
                    delivered = await self._broadcast(message)
                    await db.execute(
                        "UPDATE scheduled_announcements SET sent_at = ? WHERE id = ?",
                        (now, announcement_id),
                    )
                    print(f"[feature_services] Announcement {announcement_id} sent to {delivered} guilds")
                await db.commit()
        except Exception as exc:
            print(f"[feature_services] announcement loop failed: {exc}")

    async def _broadcast(self, message: str) -> int:
        delivered = 0
        for guild in list(self.bot.guilds):
            channel = guild.system_channel
            if channel is None or not channel.permissions_for(guild.me).send_messages:
                channel = next(
                    (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                    None,
                )
            if channel is None:
                continue
            try:
                await channel.send(message[:1900])
                delivered += 1
            except Exception:
                continue
            await asyncio.sleep(0.5)  # stay well inside the global rate limit
        return delivered


# ── Deadlock watchdog ─────────────────────────────────────────────────────


def start_deadlock_watchdog(threshold_seconds: int = 90) -> None:
    """
    Exit the process when the event loop stops updating the heartbeat.

    Runs in a plain OS thread so a blocked event loop cannot stall it.
    Railway's restart policy brings the container back up.
    """
    import threading

    def watch() -> None:
        while True:
            time.sleep(15)
            if not flags.is_enabled("auto_restart_on_deadlock"):
                continue
            stalled_for = time.time() - runtime.last_heartbeat
            if stalled_for > threshold_seconds:
                print(
                    f"[feature_services] Event loop stalled for {stalled_for:.0f}s — "
                    "restarting process (auto_restart_on_deadlock)"
                )
                os._exit(1)

    threading.Thread(target=watch, name="deadlock-watchdog", daemon=True).start()
