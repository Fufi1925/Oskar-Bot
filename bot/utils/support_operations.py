"""Exclusive support-server operations, error centre and health diagnostics.

The module intentionally has no dashboard routes. Every mutation is available
only through owner-only application commands in the fixed support guild and is
written to the audit table.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import discord

from utils.config import OWNER_IDS
from utils.server_stats_store import MAIN_SUPPORT_GUILD_ID
from utils.emoji import (CODEBASE, CROSS, INFO, LOCK, TICKET, TICK, TIME,
                         UPTIME, ZBOT, ZSAFE, ZWARNING, ZWRENCH)

DB_PATH = "db/support_operations.db"
ERROR_STATES = {"new": "Neu", "investigating": "Untersuchung", "resolved": "Behoben"}
INCIDENT_STATES = {"open": "Offen", "monitoring": "Beobachtung", "resolved": "Behoben"}
SEVERITIES = {"low", "medium", "high", "critical"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def ensure() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS support_settings(
          key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS support_errors(
          error_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
          feature TEXT NOT NULL, error_type TEXT NOT NULL,
          bot_instance TEXT NOT NULL DEFAULT '', guild_id TEXT NOT NULL DEFAULT '',
          user_id TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
          traceback TEXT NOT NULL DEFAULT '', count INTEGER NOT NULL DEFAULT 1,
          first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'new', message_id TEXT NOT NULL DEFAULT '',
          ticket_thread_id TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_support_errors_last ON support_errors(last_seen DESC);
        CREATE TABLE IF NOT EXISTS support_incidents(
          incident_id TEXT PRIMARY KEY, title TEXT NOT NULL, severity TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', description TEXT NOT NULL DEFAULT '',
          created_by TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          timeline_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS support_audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL,
          action TEXT NOT NULL, target TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL
        );
        """)


def is_owner(user_id: int | str) -> bool:
    return int(user_id) in {int(value) for value in OWNER_IDS}


def get_setting(key: str, default: str = "") -> str:
    ensure()
    with _connect() as db:
        row = db.execute("SELECT value FROM support_settings WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_setting(key: str, value: int | str) -> None:
    ensure()
    with _connect() as db:
        db.execute(
            "INSERT INTO support_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def audit(actor_id: int | str, action: str, target: str = "", detail: str = "") -> None:
    ensure()
    with _connect() as db:
        db.execute(
            "INSERT INTO support_audit(actor_id,action,target,detail,created_at) VALUES(?,?,?,?,?)",
            (str(actor_id), action[:100], target[:200], detail[:1000], int(time.time())),
        )


def _clean_trace(value: str) -> str:
    # Never put environment-style secrets or Discord tokens in a report.
    value = re.sub(r"(?i)(token|secret|password|api[_-]?key)\s*[=:]\s*[^\s,;]+", r"\1=<redacted>", value)
    value = re.sub(r"[A-Za-z\d_-]{24,}\.[A-Za-z\d_-]{6,}\.[A-Za-z\d_-]{20,}", "<redacted-token>", value)
    return value[-3500:]


def _instance() -> str:
    return (os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("BOT_INSTANCE")
            or os.getenv("HOSTNAME") or platform.node() or "main")[:100]


def _fingerprint(feature: str, exc: BaseException, trace: str) -> str:
    stable = re.sub(r'line \d+', 'line ?', trace)
    stable = re.sub(r'0x[0-9a-fA-F]+', '0x?', stable)
    raw = f"{feature}|{type(exc).__name__}|{str(exc)}|{stable[-1200:]}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


def _error_id(fingerprint: str, now: int) -> str:
    return f"ERR-{datetime.fromtimestamp(now, timezone.utc):%Y%m%d}-{fingerprint[:12].upper()}"


def upsert_error(feature: str, exc: BaseException, *, guild_id: int | None = None,
                 user_id: int | None = None, trace: str = "") -> tuple[dict, bool]:
    ensure(); now = int(time.time())
    if not trace:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    clean = _clean_trace(trace)
    fingerprint = _fingerprint(feature, exc, clean)
    with _connect() as db:
        row = db.execute("SELECT * FROM support_errors WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row:
            db.execute(
                "UPDATE support_errors SET count=count+1,last_seen=?,guild_id=?,user_id=?,"
                "summary=?,traceback=?,bot_instance=?,"
                "status=CASE WHEN status='resolved' THEN 'new' ELSE status END,"
                "updated_by=CASE WHEN status='resolved' THEN '' ELSE updated_by END "
                "WHERE fingerprint=?",
                (now, str(guild_id or ""), str(user_id or ""), str(exc)[:500], clean,
                 _instance(), fingerprint),
            )
            error_id = row["error_id"]
            created = False
        else:
            error_id = _error_id(fingerprint, now)
            db.execute(
                "INSERT INTO support_errors(error_id,fingerprint,feature,error_type,bot_instance,"
                "guild_id,user_id,summary,traceback,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (error_id, fingerprint, feature[:150], type(exc).__name__, _instance(),
                 str(guild_id or ""), str(user_id or ""), str(exc)[:500], clean, now, now),
            )
            created = True
    return get_error(error_id), created


def get_error(error_id: str) -> dict | None:
    ensure()
    with _connect() as db:
        row = db.execute("SELECT * FROM support_errors WHERE error_id=?", (error_id.upper(),)).fetchone()
    return dict(row) if row else None


def list_errors(limit: int = 10, status: str = "") -> list[dict]:
    ensure(); params: tuple[Any, ...] = ()
    query = "SELECT * FROM support_errors"
    if status in ERROR_STATES:
        query += " WHERE status=?"; params = (status,)
    query += " ORDER BY last_seen DESC LIMIT ?"; params += (max(1, min(50, int(limit))),)
    with _connect() as db:
        return [dict(row) for row in db.execute(query, params)]


def set_error_status(error_id: str, status: str, actor_id: int | str) -> dict | None:
    if status not in ERROR_STATES:
        raise ValueError("Ungültiger Fehlerstatus.")
    ensure()
    with _connect() as db:
        db.execute("UPDATE support_errors SET status=?,updated_by=? WHERE error_id=?",
                   (status, str(actor_id), error_id.upper()))
    found = get_error(error_id)
    if found:
        audit(actor_id, "error_status", error_id.upper(), status)
    return found


def attach_error_message(error_id: str, message_id: int) -> None:
    ensure()
    with _connect() as db:
        db.execute("UPDATE support_errors SET message_id=? WHERE error_id=?",
                   (str(message_id), error_id.upper()))


def attach_ticket(error_id: str, thread_id: int, actor_id: int | str) -> None:
    ensure()
    with _connect() as db:
        db.execute("UPDATE support_errors SET ticket_thread_id=? WHERE error_id=?",
                   (str(thread_id), error_id.upper()))
    audit(actor_id, "developer_ticket_created", error_id.upper(), str(thread_id))


def create_incident(title: str, severity: str, description: str, actor_id: int | str) -> dict:
    ensure(); now = int(time.time()); severity = severity if severity in SEVERITIES else "medium"
    base = hashlib.sha1(f"{now}:{title}:{actor_id}".encode()).hexdigest()[:6].upper()
    incident_id = f"INC-{datetime.fromtimestamp(now, timezone.utc):%Y%m%d}-{base}"
    timeline = [{"at": now, "actor": str(actor_id), "event": "Incident eröffnet", "note": description[:500]}]
    with _connect() as db:
        db.execute(
            "INSERT INTO support_incidents VALUES(?,?,?,?,?,?,?,?,?)",
            (incident_id, title[:150], severity, "open", description[:2000], str(actor_id), now, now,
             json.dumps(timeline, ensure_ascii=False)),
        )
    audit(actor_id, "incident_created", incident_id, severity)
    return get_incident(incident_id)


def get_incident(incident_id: str) -> dict | None:
    ensure()
    with _connect() as db:
        row = db.execute("SELECT * FROM support_incidents WHERE incident_id=?",
                         (incident_id.upper(),)).fetchone()
    return dict(row) if row else None


def list_incidents(limit: int = 10) -> list[dict]:
    ensure()
    with _connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM support_incidents ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(25, limit)),))]


def update_incident(incident_id: str, status: str, note: str, actor_id: int | str) -> dict | None:
    if status not in INCIDENT_STATES:
        raise ValueError("Ungültiger Incident-Status.")
    ensure(); now = int(time.time())
    with _connect() as db:
        row = db.execute("SELECT timeline_json FROM support_incidents WHERE incident_id=?",
                         (incident_id.upper(),)).fetchone()
        if not row:
            return None
        try: timeline = json.loads(row[0])
        except Exception: timeline = []
        timeline.append({"at": now, "actor": str(actor_id), "event": INCIDENT_STATES[status], "note": note[:500]})
        db.execute("UPDATE support_incidents SET status=?,updated_at=?,timeline_json=? WHERE incident_id=?",
                   (status, now, json.dumps(timeline, ensure_ascii=False), incident_id.upper()))
    audit(actor_id, "incident_updated", incident_id.upper(), f"{status}: {note[:300]}")
    return get_incident(incident_id)


def _fmt_ts(value: int) -> str:
    return f"<t:{int(value)}:F> (<t:{int(value)}:R>)" if value else "–"


def error_text(row: dict) -> str:
    return (
        f"{ZWARNING} **Status:** {ERROR_STATES.get(row['status'], row['status'])}\n"
        f"{ZWRENCH} **Funktion:** `{row['feature']}` · `{row['error_type']}`\n"
        f"{ZBOT} **Instanz:** `{row['bot_instance'] or 'unbekannt'}`\n"
        f"{ZSAFE} **Server-ID:** `{row['guild_id'] or 'DM/System'}`\n"
        f"{TIME} **Erstmals:** {_fmt_ts(row['first_seen'])}\n"
        f"{UPTIME} **Zuletzt:** {_fmt_ts(row['last_seen'])}\n"
        f"{INFO} **Häufigkeit:** **{row['count']}×**\n\n"
        f"**Kurzmeldung**\n```text\n{row['summary'][:700] or 'Keine Meldung'}\n```\n"
        f"**Gekürzter Stacktrace**\n```py\n{row['traceback'][-1800:] or 'Kein Stacktrace'}\n```"
    )


def _container(title: str, body: str, *, color: int = 0x5865F2, rows: list | None = None):
    from discord.ui import Container, LayoutView, Separator, TextDisplay
    view = LayoutView(timeout=None)
    box = Container(accent_color=color)
    box.add_item(TextDisplay(f"### {title}"))
    box.add_item(Separator(visible=True))
    box.add_item(TextDisplay(body[:3900]))
    for row in rows or []:
        box.add_item(row)
    view.add_item(box)
    return view


class ErrorActionView(discord.ui.LayoutView):
    """Persistent controls attached to every error report."""
    def __init__(self, bot, error_id: str):
        super().__init__(timeout=None)
        self.bot = bot; self.error_id = error_id.upper()
        from discord.ui import ActionRow, Button, Container, Separator, TextDisplay
        row = ActionRow(
            Button(label="Untersuchen", emoji=ZWRENCH, style=discord.ButtonStyle.primary,
                   custom_id=f"support:error:investigate:{self.error_id}"),
            Button(label="Beheben", emoji=TICK, style=discord.ButtonStyle.success,
                   custom_id=f"support:error:resolve:{self.error_id}"),
            Button(label="Entwickler-Ticket", emoji=TICKET, style=discord.ButtonStyle.secondary,
                   custom_id=f"support:error:ticket:{self.error_id}"),
        )
        row.children[0].callback = self._investigate
        row.children[1].callback = self._resolve
        row.children[2].callback = self._ticket
        box = Container(accent_color=0xED4245)
        box.add_item(TextDisplay(f"### {ZWARNING} Fehlerbericht · `{self.error_id}`"))
        box.add_item(Separator(visible=True))
        box.add_item(TextDisplay(error_text(get_error(self.error_id) or {})))
        box.add_item(row)
        self.add_item(box)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != MAIN_SUPPORT_GUILD_ID or not is_owner(interaction.user.id):
            await interaction.response.send_message(
                view=_container(f"{LOCK} Zugriff verweigert", "Diese Aktion ist ausschließlich für globale Owner.", color=0xED4245),
                ephemeral=True,
            )
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction, status: str):
        if not await self._guard(interaction): return
        row = set_error_status(self.error_id, status, interaction.user.id)
        if not row:
            await interaction.response.send_message(view=_container(f"{CROSS} Nicht gefunden", "Der Fehler existiert nicht mehr."), ephemeral=True); return
        await interaction.response.edit_message(view=ErrorActionView(self.bot, self.error_id))

    async def _investigate(self, interaction: discord.Interaction):
        await self._refresh(interaction, "investigating")

    async def _resolve(self, interaction: discord.Interaction):
        await self._refresh(interaction, "resolved")

    async def _ticket(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        row = get_error(self.error_id)
        if not row:
            await interaction.response.send_message(view=_container(f"{CROSS} Nicht gefunden", "Der Fehler existiert nicht mehr."), ephemeral=True); return
        if row.get("ticket_thread_id"):
            await interaction.response.send_message(view=_container(f"{TICKET} Entwickler-Ticket", f"Bereits vorhanden: <#{row['ticket_thread_id']}>") , ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        message = interaction.message
        try:
            thread = await message.create_thread(name=f"dev-{self.error_id.lower()}"[:100], auto_archive_duration=10080)
            await thread.send(view=_container(
                f"{CODEBASE} Entwickler-Ticket · {self.error_id}",
                f"{error_text(row)}\n\n{INFO} **Arbeitsbereich**\nAnalyse, Reproduktion, Fix und Verifikation werden in diesem Thread dokumentiert.",
                color=0x5865F2,
            ))
            attach_ticket(self.error_id, thread.id, interaction.user.id)
            await interaction.followup.send(view=_container(f"{TICK} Ticket erstellt", f"Interner Entwickler-Thread: {thread.mention}", color=0x57F287), ephemeral=True)
        except discord.HTTPException as exc:
            await interaction.followup.send(view=_container(f"{CROSS} Ticket fehlgeschlagen", f"Discord konnte den internen Thread nicht erstellen: `{exc}`", color=0xED4245), ephemeral=True)


class SupportErrorLogHandler(logging.Handler):
    """Forward real Python ERROR records into the deduplicating centre."""
    def __init__(self, bot):
        super().__init__(level=logging.ERROR); self.bot = bot

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("support_operations"):
            return
        try:
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
                trace = "".join(traceback.format_exception(*record.exc_info))
            else:
                exc = RuntimeError(record.getMessage())
                trace = self.format(record)
            loop = self.bot.loop
            loop.call_soon_threadsafe(
                lambda: loop.create_task(report_error(
                    self.bot, f"log:{record.name}", exc, trace=trace
                ))
            )
        except Exception:
            pass


def install_log_reporting(bot) -> SupportErrorLogHandler:
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, SupportErrorLogHandler):
            handler.bot = bot
            return handler
    handler = SupportErrorLogHandler(bot)
    root.addHandler(handler)
    return handler


async def report_error(bot, feature: str, exc: BaseException, *, guild_id: int | None = None,
                       user_id: int | None = None, trace: str = "") -> dict:
    """Deduplicate, persist and post/update one private error-centre message."""
    row, created = upsert_error(feature, exc, guild_id=guild_id, user_id=user_id, trace=trace)
    channel_id = get_setting("error_channel_id")
    guild = bot.get_guild(MAIN_SUPPORT_GUILD_ID) if hasattr(bot, "get_guild") else None
    channel = guild.get_channel(int(channel_id)) if guild and channel_id.isdigit() else None
    if channel is None or not hasattr(channel, "send"):
        return row
    try:
        view = ErrorActionView(bot, row["error_id"])
        if not created and row.get("message_id"):
            try:
                message = await channel.fetch_message(int(row["message_id"]))
                await message.edit(view=view)
                return row
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        message = await channel.send(view=view)
        attach_error_message(row["error_id"], message.id)
    except discord.HTTPException:
        pass
    return row


async def refresh_error_report(bot, error_id: str) -> bool:
    """Refresh the configured centre message after a command-side status edit."""
    row = get_error(error_id)
    channel_id = get_setting("error_channel_id")
    guild = bot.get_guild(MAIN_SUPPORT_GUILD_ID) if hasattr(bot, "get_guild") else None
    channel = guild.get_channel(int(channel_id)) if guild and channel_id.isdigit() else None
    if not row or not row.get("message_id") or channel is None:
        return False
    try:
        message = await channel.fetch_message(int(row["message_id"]))
        await message.edit(view=ErrorActionView(bot, row["error_id"]))
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
        return False


async def register_error_views(bot) -> None:
    for row in list_errors(50):
        if row["status"] != "resolved":
            bot.add_view(ErrorActionView(bot, row["error_id"]))


async def diagnose_guild(guild: discord.Guild) -> dict:
    """Run non-destructive health checks and return findings with solutions."""
    findings: list[dict] = []
    me = guild.me
    if me is None:
        findings.append({"severity": "critical", "area": "Bot", "problem": "Bot-Mitglied nicht im Cache.", "solution": "Botverbindung und Member-Intent prüfen."})
        return {"findings": findings, "checked": 1}

    required = {
        "view_channel": "Kanäle anzeigen", "send_messages": "Nachrichten senden",
        "embed_links": "Links einbetten", "read_message_history": "Nachrichtenverlauf lesen",
        "manage_roles": "Rollen verwalten", "manage_webhooks": "Webhooks verwalten",
    }
    missing = [label for key, label in required.items() if not getattr(me.guild_permissions, key, False)]
    if missing:
        findings.append({"severity": "high", "area": "Berechtigungen", "problem": ", ".join(missing), "solution": "Botrolle entsprechend ergänzen; Administrator ist nicht zwingend erforderlich."})

    above = [role.mention for role in guild.roles if role != guild.default_role and role >= me.top_role and not role.managed]
    if above:
        findings.append({"severity": "medium", "area": "Rollenhierarchie", "problem": f"{len(above)} Rollen liegen auf/über der Botrolle: " + ", ".join(above[:8]), "solution": "Botrolle über alle Rollen schieben, die der Bot vergeben oder moderieren soll."})

    # Generic reference validation catches deleted channels/roles across every
    # module without hardcoding one schema per feature.
    missing_channels: set[str] = set(); missing_roles: set[str] = set()
    unreachable_messages = 0; checked_messages = 0; config_rows = 0
    for path in sorted(__import__('glob').glob("db/*.db")):
        try:
            async with aiosqlite.connect(path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                    tables = [r[0] async for r in cur if not str(r[0]).startswith("sqlite_")]
                for table in tables[:100]:
                    async with db.execute(f'PRAGMA table_info("{table}")') as cur:
                        cols = [r[1] async for r in cur]
                    guild_col = next((c for c in cols if c in {"guild_id", "server_id"}), None)
                    refs = [c for c in cols if c.endswith("channel_id") or c.endswith("role_id") or c.endswith("message_id")]
                    if not guild_col or not refs:
                        continue
                    query_cols = ",".join(f'"{c}"' for c in refs)
                    try:
                        async with db.execute(f'SELECT {query_cols} FROM "{table}" WHERE "{guild_col}"=? LIMIT 500', (guild.id,)) as cur:
                            rows = await cur.fetchall()
                    except sqlite3.Error:
                        continue
                    config_rows += len(rows)
                    for row in rows:
                        for col in refs:
                            raw = row[col]
                            if raw in (None, "", 0, "0"): continue
                            values = re.findall(r"\d{15,22}", str(raw))
                            for value in values[:25]:
                                ident = int(value)
                                if col.endswith("channel_id") and guild.get_channel_or_thread(ident) is None:
                                    missing_channels.add(f"{os.path.basename(path)}:{table}.{col}={value}")
                                elif col.endswith("role_id") and guild.get_role(ident) is None:
                                    missing_roles.add(f"{os.path.basename(path)}:{table}.{col}={value}")
                        # For configuration tables that store a channel and a
                        # message together, verify a bounded sample against
                        # Discord. This catches deleted panels without turning
                        # a diagnosis into hundreds of API calls.
                        if checked_messages < 30:
                            channel_cols = [c for c in refs if c.endswith("channel_id")]
                            message_cols = [c for c in refs if c.endswith("message_id")]
                            target = next((guild.get_channel_or_thread(int(row[c])) for c in channel_cols if str(row[c] or "").isdigit() and guild.get_channel_or_thread(int(row[c]))), None)
                            if target is not None and hasattr(target, "fetch_message"):
                                for message_col in message_cols:
                                    if checked_messages >= 30: break
                                    raw_message = row[message_col]
                                    if not str(raw_message or "").isdigit(): continue
                                    checked_messages += 1
                                    try: await target.fetch_message(int(raw_message))
                                    except (discord.NotFound, discord.Forbidden): unreachable_messages += 1
        except (sqlite3.Error, OSError):
            continue
    if missing_channels:
        findings.append({"severity": "high", "area": "Gelöschte Kanäle", "problem": f"{len(missing_channels)} ungültige Kanalreferenzen, z. B. " + "; ".join(sorted(missing_channels)[:5]), "solution": "Betroffene Module im Dashboard öffnen und gültige Zielkanäle speichern."})
    if missing_roles:
        findings.append({"severity": "high", "area": "Gelöschte Rollen", "problem": f"{len(missing_roles)} ungültige Rollenreferenzen, z. B. " + "; ".join(sorted(missing_roles)[:5]), "solution": "Rollen in den betroffenen Modulen neu auswählen."})
    if unreachable_messages:
        findings.append({"severity": "high", "area": "Nachrichten", "problem": f"{unreachable_messages} von {checked_messages} geprüften Panel-/Konfigurationsnachrichten sind nicht erreichbar.", "solution": "Betroffene Panels oder Automationsnachrichten erneut senden und die Botrechte im Zielkanal prüfen."})

    try:
        webhooks = await guild.webhooks()
        broken = [hook for hook in webhooks if hook.channel_id and guild.get_channel(hook.channel_id) is None]
        if broken:
            findings.append({"severity": "medium", "area": "Webhooks", "problem": f"{len(broken)} Webhooks zeigen auf nicht erreichbare Kanäle.", "solution": "Ungültige Webhooks löschen und über das jeweilige Modul neu erstellen."})
    except discord.Forbidden:
        findings.append({"severity": "medium", "area": "Webhooks", "problem": "Webhooks konnten wegen fehlender Berechtigung nicht geprüft werden.", "solution": "Berechtigung „Webhooks verwalten“ ergänzen."})

    try:
        from utils import guild_modules
        states = await guild_modules.get_states(guild.id)
        disabled = [name for name, enabled in states.items() if not enabled]
        if disabled and config_rows:
            findings.append({"severity": "low", "area": "Module", "problem": f"{len(disabled)} Module deaktiviert; gespeicherte Konfiguration ist weiterhin vorhanden: " + ", ".join(disabled[:10]), "solution": "Konfiguration behalten, wenn das Modul später wieder aktiviert werden soll; sonst gezielt zurücksetzen."})
    except Exception:
        pass

    try:
        from utils import custom_commands
        db = await custom_commands.connect()
        try: commands_rows = await custom_commands.list_all(db, guild.id)
        finally: await db.close()
        invalid = [row["name"] for row in commands_rows if not custom_commands.valid_name(row["name"]) or not isinstance(row.get("config"), dict)]
        stale_components = []
        def inspect_actions(items, command_name):
            for action in items if isinstance(items, list) else []:
                for button in action.get("buttons", []) if isinstance(action, dict) else []:
                    if not button.get("url") and not button.get("actions"):
                        stale_components.append(f"/{command_name}: Button „{button.get('label','?')}“ ohne Aktion")
                    inspect_actions(button.get("actions", []), command_name)
                for menu in action.get("selects", []) if isinstance(action, dict) else []:
                    for option in menu.get("options", []):
                        if not option.get("actions"):
                            stale_components.append(f"/{command_name}: Auswahl „{option.get('label','?')}“ ohne Antwort")
                        inspect_actions(option.get("actions", []), command_name)
                inspect_actions(action.get("then", []) if isinstance(action, dict) else [], command_name)
                inspect_actions(action.get("else", []) if isinstance(action, dict) else [], command_name)
        for command in commands_rows:
            inspect_actions((command.get("config") or {}).get("actions", []), command["name"])
        if invalid:
            findings.append({"severity": "high", "area": "Custom Commands", "problem": "Ungültige Commands: " + ", ".join(invalid[:10]), "solution": "Commands im Dashboard öffnen, korrigieren und erneut speichern."})
        if stale_components:
            findings.append({"severity": "medium", "area": "Komponenten", "problem": f"{len(stale_components)} unvollständige oder veraltete Interaktionen, z. B. " + "; ".join(stale_components[:5]), "solution": "Für jeden Button und jede Auswahloption einen Link oder privaten Aktionsflow konfigurieren."})
    except Exception as exc:
        findings.append({"severity": "medium", "area": "Custom Commands", "problem": f"Prüfung fehlgeschlagen: {type(exc).__name__}", "solution": "Datenbankintegrität und Custom-Command-Dienst prüfen."})

    ticket_db = "db/ticket.db"
    if os.path.exists(ticket_db):
        try:
            async with aiosqlite.connect(ticket_db) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT panel_channel_id,panel_message_id FROM guild_configs WHERE guild_id=?", (guild.id,)) as cur:
                    panel = await cur.fetchone()
            if panel and panel["panel_channel_id"] and panel["panel_message_id"]:
                target = guild.get_channel(int(panel["panel_channel_id"]))
                if target is None:
                    findings.append({"severity": "high", "area": "Ticketpanel", "problem": "Der Panelkanal wurde gelöscht.", "solution": "Ticketpanel in einen neuen Kanal senden."})
                else:
                    try: await target.fetch_message(int(panel["panel_message_id"]))
                    except (discord.NotFound, discord.Forbidden):
                        findings.append({"severity": "high", "area": "Ticketpanel", "problem": "Die konfigurierte Panelnachricht ist nicht erreichbar.", "solution": "Ticketpanel erneut senden und Botberechtigungen prüfen."})
        except sqlite3.Error:
            pass

    if not findings:
        findings.append({"severity": "ok", "area": "Gesamtsystem", "problem": "Keine auffälligen Probleme erkannt.", "solution": "Keine Aktion erforderlich."})
    return {"findings": findings, "checked": config_rows, "message_references": checked_messages}
