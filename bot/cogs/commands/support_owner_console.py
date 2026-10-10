"""Owner-only Components-V2 command console for the official support guild."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Awaitable, Callable

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from utils import command_stats, feature_flags, premium_membership, support_operations as ops
from utils.feature_services import runtime
from utils.server_stats_store import MAIN_SUPPORT_GUILD_ID
from utils.emoji import (CODEBASE, CROSS, ICONS_WARNING, INFO, LOCK, TICKET,
                         TICK, TIME, UPTIME, ZBOT, ZCLOUD, ZROCKET, ZSAFE,
                         ZSETTINGS, ZWARNING, ZWRENCH)

SUPPORT_GUILD = discord.Object(id=MAIN_SUPPORT_GUILD_ID)
ACCENT = 0x5865F2
SUCCESS = 0x57F287
DANGER = 0xED4245
WARN = 0xFEE75C
logger = logging.getLogger("support_owner_console")


def panel(title: str, *sections: str, color: int = ACCENT, rows: list | None = None):
    from discord.ui import Container, LayoutView, Separator, TextDisplay
    view = LayoutView(timeout=None)
    box = Container(accent_color=color)
    box.add_item(TextDisplay(f"### {title}"))
    for section in sections:
        if not section: continue
        box.add_item(Separator(visible=True))
        box.add_item(TextDisplay(str(section)[:3900]))
    for row in rows or []:
        box.add_item(row)
    view.add_item(box)
    return view


def stamp(value) -> str:
    try: return f"<t:{int(value)}:F> (<t:{int(value)}:R>)"
    except (TypeError, ValueError): return "–"


class ConfirmView(discord.ui.LayoutView):
    """Two-step confirmation for every destructive owner operation."""
    def __init__(self, owner_id: int, title: str, summary: str,
                 action: Callable[[discord.Interaction], Awaitable[tuple[str, str]]]):
        super().__init__(timeout=120)
        self.owner_id = owner_id; self.action = action; self.done = False
        from discord.ui import ActionRow, Button, Container, Separator, TextDisplay
        confirm = Button(label="Endgültig bestätigen", emoji=TICK, style=discord.ButtonStyle.danger)
        cancel = Button(label="Abbrechen", emoji=CROSS, style=discord.ButtonStyle.secondary)
        confirm.callback = self.confirm; cancel.callback = self.cancel
        box = Container(accent_color=DANGER)
        box.add_item(TextDisplay(f"### {ICONS_WARNING} {title}"))
        box.add_item(Separator(visible=True)); box.add_item(TextDisplay(summary[:3900]))
        box.add_item(ActionRow(confirm, cancel)); self.add_item(box)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not ops.is_owner(interaction.user.id):
            await interaction.response.send_message(view=panel(f"{LOCK} Zugriff verweigert", "Nur der Owner, der die Vorschau geöffnet hat, kann diese Aktion bestätigen.", color=DANGER), ephemeral=True)
            return False
        return True

    async def confirm(self, interaction: discord.Interaction):
        if self.done: return
        self.done = True
        try:
            title, text = await self.action(interaction)
            await interaction.response.edit_message(view=panel(f"{TICK} {title}", text, color=SUCCESS))
        except Exception as exc:
            self.done = False
            await interaction.response.edit_message(view=panel(f"{CROSS} Aktion fehlgeschlagen", f"`{type(exc).__name__}: {exc}`", color=DANGER))

    async def cancel(self, interaction: discord.Interaction):
        self.done = True
        await interaction.response.edit_message(view=panel(f"{CROSS} Abgebrochen", "Es wurde nichts verändert."))


class SupportOwnerConsole(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def cog_load(self):
        ops.ensure()
        ops.install_log_reporting(self.bot)
        await ops.register_error_views(self.bot)
        # These commands are deliberately guild-scoped. A later global
        # tree.sync() does not publish guild commands, so without this explicit
        # sync Discord never receives them even though the Cog is loaded.
        try:
            synced = await self.bot.tree.sync(guild=SUPPORT_GUILD)
            logger.info("Synced %s support-owner commands to guild %s", len(synced), MAIN_SUPPORT_GUILD_ID)
        except Exception:
            logger.exception("Could not sync support-owner commands to guild %s", MAIN_SUPPORT_GUILD_ID)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != MAIN_SUPPORT_GUILD_ID or not ops.is_owner(interaction.user.id):
            if interaction.response.is_done():
                await interaction.followup.send(view=panel(f"{LOCK} Zugriff verweigert", "Diese Konsole ist ausschließlich für globale Owner im offiziellen Support-Server verfügbar.", color=DANGER), ephemeral=True)
            else:
                await interaction.response.send_message(view=panel(f"{LOCK} Zugriff verweigert", "Diese Konsole ist ausschließlich für globale Owner im offiziellen Support-Server verfügbar.", color=DANGER), ephemeral=True)
            return False
        return True

    async def _send(self, interaction: discord.Interaction, view):
        if interaction.response.is_done(): await interaction.followup.send(view=view, ephemeral=True)
        else: await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="global-status", description="Globale Live-Übersicht über Bot und Infrastruktur.")
    @app_commands.guilds(SUPPORT_GUILD)
    async def global_status(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        await interaction.response.defer(ephemeral=True)
        snapshot = runtime.snapshot(); total_users = sum(g.member_count or 0 for g in self.bot.guilds)
        commands_used = await command_stats.total_uses()
        open_errors = len(ops.list_errors(50, "new")) + len(ops.list_errors(50, "investigating"))
        incidents = [i for i in ops.list_incidents(25) if i["status"] != "resolved"]
        health = SUCCESS if not snapshot["failed_extensions"] and not incidents else WARN
        body = (
            f"{ZBOT} **Bot:** {self.bot.user.mention if self.bot.user else 'CloudTIX'} · `{round(self.bot.latency*1000)} ms`\n"
            f"{UPTIME} **Uptime:** `{int(snapshot['uptime_seconds']//3600)} h {int(snapshot['uptime_seconds']%3600//60)} min`\n"
            f"{ZSAFE} **Server:** **{len(self.bot.guilds):,}** · **{total_users:,}** Nutzer\n"
            f"{CODEBASE} **Commands gesamt:** **{commands_used:,}**\n"
            f"{ZWARNING} **Offene Fehler:** **{open_errors}** · **Incidents:** **{len(incidents)}**\n"
            f"{ZCLOUD} **Discord:** `{snapshot['discord_status']}` · fehlgeschlagene Extensions: **{len(snapshot['failed_extensions'])}**"
        )
        flags = feature_flags.all_values(); enabled = sum(1 for value in flags.values() if value)
        second = f"{ZSETTINGS} **Feature Flags:** {enabled}/{len(flags)} aktiv\n{ZWRENCH} **Datenbankprüfungen:** {len(snapshot['integrity'])}\n{TIME} **Letztes Backup:** {stamp(snapshot['last_backup_at'])}"
        await interaction.followup.send(view=panel(f"{ZROCKET} Globaler Systemstatus", body, second, color=health), ephemeral=True)

    @app_commands.command(name="server-diagnose", description="Vollständiger Health-Check eines verbundenen Servers.")
    @app_commands.guilds(SUPPORT_GUILD)
    @app_commands.describe(server_id="Discord-ID des zu prüfenden Servers")
    async def server_diagnose(self, interaction: discord.Interaction, server_id: str):
        if not await self._guard(interaction): return
        if not server_id.isdigit() or not (guild := self.bot.get_guild(int(server_id))):
            await self._send(interaction, panel(f"{CROSS} Server nicht gefunden", "Die ID gehört zu keinem aktuell verbundenen Server.", color=DANGER)); return
        await interaction.response.defer(ephemeral=True)
        result = await ops.diagnose_guild(guild)
        icons = {"critical": CROSS, "high": ZWARNING, "medium": ICONS_WARNING, "low": INFO, "ok": TICK}
        sections = []
        for finding in result["findings"]:
            sections.append(f"{icons.get(finding['severity'], INFO)} **{finding['area']}**\n{finding['problem']}\n-# Lösung: {finding['solution']}")
        chunks = ["\n\n".join(sections[i:i+5]) for i in range(0, len(sections), 5)]
        summary = f"{ZSAFE} **{guild.name}** · `{guild.id}`\n{INFO} {len(result['findings'])} Ergebnisse · {result['checked']} Konfigurationszeilen geprüft"
        await interaction.followup.send(view=panel(f"{ZWRENCH} Server-Diagnose", summary, *chunks, color=SUCCESS if result['findings'][0]['severity']=='ok' else WARN), ephemeral=True)

    @app_commands.command(name="incident", description="Incidents eröffnen, auflisten, aktualisieren oder abschließen.")
    @app_commands.guilds(SUPPORT_GUILD)
    @app_commands.choices(action=[app_commands.Choice(name="Auflisten", value="list"), app_commands.Choice(name="Eröffnen", value="open"), app_commands.Choice(name="Beobachten", value="monitor"), app_commands.Choice(name="Abschließen", value="resolve")], severity=[app_commands.Choice(name="Niedrig", value="low"), app_commands.Choice(name="Mittel", value="medium"), app_commands.Choice(name="Hoch", value="high"), app_commands.Choice(name="Kritisch", value="critical")])
    async def incident(self, interaction: discord.Interaction, action: app_commands.Choice[str], incident_id: str = "", title: str = "", severity: app_commands.Choice[str] | None = None, note: str = ""):
        if not await self._guard(interaction): return
        if action.value == "list":
            rows = ops.list_incidents(); text = "\n".join(f"{ZWARNING if r['status']!='resolved' else TICK} `{r['incident_id']}` · **{r['title']}** · {r['severity']} · {ops.INCIDENT_STATES.get(r['status'])}" for r in rows) or "Keine Incidents vorhanden."
            await self._send(interaction, panel(f"{ZWARNING} Incident-Zentrale", text)); return
        if action.value == "open":
            if not title.strip(): await self._send(interaction, panel(f"{CROSS} Titel fehlt", "Zum Eröffnen wird ein Titel benötigt.", color=DANGER)); return
            row = ops.create_incident(title, severity.value if severity else "medium", note, interaction.user.id)
            await self._send(interaction, panel(f"{ZWARNING} Incident eröffnet", f"`{row['incident_id']}` · **{row['title']}**\nSchweregrad: **{row['severity']}**\n{row['description']}", color=WARN)); return
        row = ops.get_incident(incident_id)
        if not row: await self._send(interaction, panel(f"{CROSS} Incident nicht gefunden", "Prüfe die Incident-ID.", color=DANGER)); return
        status = "monitoring" if action.value == "monitor" else "resolved"
        async def apply(_):
            updated = ops.update_incident(incident_id, status, note, interaction.user.id)
            return "Incident aktualisiert", f"`{updated['incident_id']}` steht jetzt auf **{ops.INCIDENT_STATES[status]}**."
        preview = f"`{row['incident_id']}` · **{row['title']}**\nStatus: {ops.INCIDENT_STATES[row['status']]} → **{ops.INCIDENT_STATES[status]}**\nNotiz: {note or '–'}"
        await self._send(interaction, ConfirmView(interaction.user.id, "Incident-Änderung bestätigen", preview, apply))

    @app_commands.command(name="feature-flag", description="Globales Feature Flag ansehen oder kontrolliert ändern.")
    @app_commands.guilds(SUPPORT_GUILD)
    @app_commands.describe(key="Technischer Schlüssel des Feature Flags", enabled="Optional: neuen Zustand setzen", rollout="Optional: Rollout von 0 bis 100 Prozent")
    async def feature_flag(self, interaction: discord.Interaction, key: str, enabled: bool | None = None, rollout: app_commands.Range[int, 0, 100] | None = None):
        if not await self._guard(interaction): return
        if key not in feature_flags.FEATURE_DEFAULTS:
            await self._send(interaction, panel(f"{CROSS} Unbekanntes Feature Flag", f"`{key}` existiert nicht.", color=DANGER)); return
        current = feature_flags.all_values().get(key, feature_flags.FEATURE_DEFAULTS[key]); current_rollout = feature_flags.all_rollouts().get(key, 100)
        if enabled is None and rollout is None:
            meta = feature_flags.FEATURES_BY_KEY[key]
            await self._send(interaction, panel(f"{ZSETTINGS} Feature Flag", f"**{meta.label}** · `{key}`\nStatus: **{'Aktiv' if current else 'Deaktiviert'}**\nRollout: **{current_rollout}%**\n{meta.description}")); return
        async def apply(_):
            if enabled is not None: await feature_flags.set_values({key: enabled})
            if rollout is not None: await feature_flags.set_rollout(key, rollout)
            ops.audit(interaction.user.id, "feature_flag_changed", key, f"enabled={enabled}, rollout={rollout}")
            return "Feature Flag gespeichert", f"`{key}` ist jetzt **{'aktiv' if feature_flags.is_enabled(key) else 'deaktiviert'}**, Rollout **{feature_flags.all_rollouts().get(key,100)}%**."
        preview = f"`{key}`\nStatus: **{current} → {enabled if enabled is not None else current}**\nRollout: **{current_rollout}% → {rollout if rollout is not None else current_rollout}%**\n\n{ICONS_WARNING} Diese Änderung wirkt global."
        await self._send(interaction, ConfirmView(interaction.user.id, "Globale Änderung bestätigen", preview, apply))

    @app_commands.command(name="deployment-status", description="Deployment-, Prozess-, Datenbank- und Extension-Status.")
    @app_commands.guilds(SUPPORT_GUILD)
    async def deployment_status(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        snapshot = runtime.snapshot(); commit = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unbekannt"
        deploy = os.getenv("RAILWAY_DEPLOYMENT_ID") or "lokal/unbekannt"
        integrity_bad = [f"`{k}`: {v}" for k,v in snapshot["integrity"].items() if str(v).lower() not in {"ok","healthy"}]
        body = f"{ZROCKET} **Deployment:** `{deploy}`\n{CODEBASE} **Commit:** `{commit[:12]}`\n{ZBOT} **Instanz:** `{os.getenv('RAILWAY_SERVICE_NAME') or os.getenv('HOSTNAME') or 'main'}`\n{UPTIME} **Heartbeat:** {stamp(int(snapshot['last_heartbeat']))}\n{ZCLOUD} **Discord:** `{snapshot['discord_status']}`"
        extensions = f"{TICK if not snapshot['failed_extensions'] else CROSS} **Extensions**\nFehlgeschlagen: {', '.join(snapshot['failed_extensions']) or 'keine'}\nWiederhergestellt: {', '.join(snapshot['recovered_extensions']) or 'keine'}"
        database = f"{ZSAFE} **Datenbanken**\n" + ("\n".join(integrity_bad[:20]) if integrity_bad else "Alle zuletzt geprüften Datenbanken sind unauffällig.")
        await self._send(interaction, panel(f"{ZROCKET} Deployment-Status", body, extensions, database, color=SUCCESS if not integrity_bad and not snapshot['failed_extensions'] else WARN))

    @app_commands.command(name="server-lookup", description="Geheime globale Detailansicht eines verbundenen Servers.")
    @app_commands.guilds(SUPPORT_GUILD)
    async def server_lookup(self, interaction: discord.Interaction, server_id: str):
        if not await self._guard(interaction): return
        if not server_id.isdigit() or not (guild := self.bot.get_guild(int(server_id))):
            await self._send(interaction, panel(f"{CROSS} Server nicht gefunden", "Keine verbundene Guild mit dieser ID.", color=DANGER)); return
        owner = guild.owner or self.bot.get_user(guild.owner_id)
        premium = premium_membership.guild_status(guild.id)
        me = guild.me; perms = me.guild_permissions if me else None
        body = f"{ZSAFE} **{guild.name}** · `{guild.id}`\nOwner: {owner.mention if owner else '`unbekannt`'} · `{guild.owner_id}`\nMitglieder: **{guild.member_count or 0:,}** · Kanäle: **{len(guild.channels)}** · Rollen: **{len(guild.roles)}**\nBeigetreten: {stamp(int(me.joined_at.timestamp())) if me and me.joined_at else '–'}\nPremium: **{'Aktiv' if premium.get('active') else 'Nein'}** · Quelle: `{'Admin-Freigabe' if premium.get('direct_admin_grant') else 'Account-Platz' if premium.get('assigned') else '–'}`"
        permission_text = f"{ZWRENCH} **Botrechte**\nAdministrator: **{bool(perms and perms.administrator)}** · Rollen: **{bool(perms and perms.manage_roles)}** · Nachrichten: **{bool(perms and perms.send_messages)}**"
        await self._send(interaction, panel(f"{INFO} Server-Lookup", body, permission_text))

    @app_commands.command(name="premium-history", description="Premiumstatus und unveränderte Historie eines Accounts oder Servers.")
    @app_commands.guilds(SUPPORT_GUILD)
    async def premium_history(self, interaction: discord.Interaction, server_id: str = "", user_id: str = ""):
        if not await self._guard(interaction): return
        if not server_id and not user_id:
            await self._send(interaction, panel(f"{CROSS} ID fehlt", "Gib eine Server-ID oder Nutzer-ID an.", color=DANGER)); return
        sections = []
        if server_id:
            if not server_id.isdigit(): await self._send(interaction, panel(f"{CROSS} Ungültige Server-ID", "Die ID muss numerisch sein.", color=DANGER)); return
            status = premium_membership.guild_status(int(server_id))
            source = "Admin-Freigabe" if status.get("direct_admin_grant") else "Account-Platz" if status.get("assigned") else "–"
            sections.append(f"{ZSAFE} **Server `{server_id}`**\nAktiv: **{status.get('active',False)}** · Quelle: `{source}`\nInhaber: `{status.get('account_user_id') or '–'}`\nAblauf: {stamp(status.get('expires_at'))}")
        if user_id:
            if not user_id.isdigit(): await self._send(interaction, panel(f"{CROSS} Ungültige Nutzer-ID", "Die ID muss numerisch sein.", color=DANGER)); return
            status = premium_membership.account_status(user_id)
            requests = "\n".join(f"• Anfrage #{r['id']} · {r['duration_days']} Tage · {r['status']} · {stamp(r['created_at'])}" for r in status['purchase_requests'][:8]) or "Keine Kaufanfragen."
            slots = "\n".join(f"• Platz {r['slot_no']}: Server `{r['guild_id']}` · {stamp(r['assigned_at'])}" for r in status['slots']) or "Keine Serverplätze."
            sections.append(f"{ZBOT} **Account `{user_id}`**\nAktiv: **{status['premium']}** · Lifetime: **{status['lifetime']}**\nQuelle: `{status['source'] or '–'}` · Ablauf: {stamp(status['expires_at'])}\n\n**Serverplätze**\n{slots}\n\n**Kaufhistorie**\n{requests}")
        await self._send(interaction, panel(f"{TICKET} Premium-Historie", *sections))

    @app_commands.command(name="error-lookup", description="Fehlerzentrale einrichten, durchsuchen und Status verwalten.")
    @app_commands.guilds(SUPPORT_GUILD)
    @app_commands.choices(action=[app_commands.Choice(name="Auflisten", value="list"), app_commands.Choice(name="Details", value="show"), app_commands.Choice(name="Kanal einrichten", value="setup"), app_commands.Choice(name="Untersuchung", value="investigate"), app_commands.Choice(name="Behoben", value="resolve"), app_commands.Choice(name="Wieder öffnen", value="reopen")])
    async def error_lookup(self, interaction: discord.Interaction, action: app_commands.Choice[str], error_id: str = "", channel: discord.TextChannel | None = None):
        if not await self._guard(interaction): return
        if action.value == "setup":
            if channel is None: await self._send(interaction, panel(f"{CROSS} Kanal fehlt", "Wähle einen privaten Textkanal.", color=DANGER)); return
            if channel.permissions_for(interaction.guild.default_role).view_channel:
                await self._send(interaction, panel(f"{CROSS} Kanal ist nicht privat", "Die Fehlerzentrale darf für @everyone nicht sichtbar sein. Entferne zuerst „Kanal anzeigen“ für @everyone.", color=DANGER)); return
            me = interaction.guild.me; perms = channel.permissions_for(me)
            if not all((perms.view_channel, perms.send_messages, perms.read_message_history, perms.create_public_threads)):
                await self._send(interaction, panel(f"{CROSS} Rechte fehlen", "Der Bot braucht Kanalansicht, Nachrichten, Verlauf und Thread-Erstellung.", color=DANGER)); return
            ops.set_setting("error_channel_id", channel.id); ops.audit(interaction.user.id, "error_channel_set", str(channel.id), channel.name)
            await self._send(interaction, panel(f"{TICK} Fehlerzentrale eingerichtet", f"Automatische Fehlerberichte werden ab jetzt in {channel.mention} zusammengefasst.", color=SUCCESS)); return
        if action.value == "list":
            rows = ops.list_errors(); text = "\n".join(f"{TICK if r['status']=='resolved' else ZWARNING} `{r['error_id']}` · **{ops.ERROR_STATES[r['status']]}** · {r['feature']} · {r['count']}×" for r in rows) or "Keine Fehler gespeichert."
            await self._send(interaction, panel(f"{ZWARNING} Globale Fehlerzentrale", text)); return
        row = ops.get_error(error_id)
        if not row: await self._send(interaction, panel(f"{CROSS} Fehler nicht gefunden", "Prüfe die eindeutige Fehler-ID.", color=DANGER)); return
        if action.value == "show":
            await self._send(interaction, ops.ErrorActionView(self.bot, row['error_id'])); return
        status = {"investigate":"investigating","resolve":"resolved","reopen":"new"}[action.value]
        updated = ops.set_error_status(error_id, status, interaction.user.id)
        await ops.refresh_error_report(self.bot, error_id)
        await self._send(interaction, panel(f"{TICK} Fehlerstatus aktualisiert", f"`{error_id.upper()}` → **{ops.ERROR_STATES[updated['status']]}**", color=SUCCESS))

    @app_commands.command(name="support-access", description="Zeitlich begrenzten Supportzugriff prüfen oder sicher widerrufen.")
    @app_commands.guilds(SUPPORT_GUILD)
    @app_commands.choices(action=[app_commands.Choice(name="Prüfen", value="inspect"), app_commands.Choice(name="Widerrufen", value="revoke")])
    async def support_access(self, interaction: discord.Interaction, action: app_commands.Choice[str], server_id: str, user_id: str):
        if not await self._guard(interaction): return
        if not server_id.isdigit() or not user_id.isdigit(): await self._send(interaction, panel(f"{CROSS} Ungültige ID", "Server- und Nutzer-ID müssen numerisch sein.", color=DANGER)); return
        db_path = "db/admin_config.db"
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            from api.routes.support import _ensure
            await _ensure(db)
            async with db.execute("SELECT * FROM dashboard_support_cases WHERE guild_id=? AND supporter_id=? ORDER BY id DESC LIMIT 1", (server_id,user_id)) as cur: row = await cur.fetchone()
        if not row: await self._send(interaction, panel(f"{INFO} Kein Supportzugriff", "Für diese Kombination existiert kein Supportfall.")); return
        data = dict(row)
        if action.value == "inspect":
            await self._send(interaction, panel(f"{LOCK} Supportzugriff", f"Fall **#{data['id']}** · Status **{data['status']}**\nServer: `{server_id}` · Supporter: `{user_id}`\nErstellt: {stamp(data['created_at'])}\nAkzeptiert: {stamp(data['accepted_at'])}\nGeschlossen: {stamp(data['closed_at'])}\n\nProblem: {data['problem'] or '–'}")); return
        async def apply(_):
            now=int(time.time())
            async with aiosqlite.connect(db_path) as db:
                await db.execute("UPDATE dashboard_support_cases SET status='closed',closed_at=?,updated_at=? WHERE id=? AND status IN ('pending','accepted')", (now,now,data['id'])); await db.commit()
            ops.audit(interaction.user.id,"support_access_revoked",str(data['id']),f"guild={server_id}, supporter={user_id}")
            return "Supportzugriff widerrufen", f"Fall **#{data['id']}** wurde geschlossen. Der Dashboardzugriff endet sofort."
        await self._send(interaction, ConfirmView(interaction.user.id, "Supportzugriff widerrufen?", f"Fall **#{data['id']}** · Server `{server_id}` · Supporter `{user_id}`\n\n{ICONS_WARNING} Der Zugriff endet sofort; der Audit-Verlauf bleibt erhalten.", apply))

    @app_commands.command(name="template-inspect", description="Eine Dashboard-Vorlage vollständig und sicher untersuchen.")
    @app_commands.guilds(SUPPORT_GUILD)
    async def template_inspect(self, interaction: discord.Interaction, template_id: int):
        if not await self._guard(interaction): return
        from utils import template_store
        async with aiosqlite.connect(template_store.DB_PATH) as db:
            await template_store.ensure_schema(db)
            item = await template_store.get_template(db, template_id, as_admin=True)
        if not item: await self._send(interaction, panel(f"{CROSS} Vorlage nicht gefunden", f"Keine Vorlage mit ID `{template_id}`.", color=DANGER)); return
        payload = item.get("payload") or {}
        raw = json.dumps(payload, ensure_ascii=False)
        secret = template_store.contains_secret(payload)
        modules = list(payload.keys()) if isinstance(payload, dict) else []
        body = f"{CODEBASE} **{item.get('name','Unbenannt')}** · ID `{template_id}`\nSichtbarkeit: **{item.get('visibility','–')}** · Gesperrt: **{bool(item.get('blocked'))}**\nQuelle: Server `{item.get('source_guild_id','–')}` · Nutzer `{item.get('author_id','–')}`\nErstellt: {stamp(item.get('created_at'))} · Nutzungen: **{item.get('uses',0)}**\nBewertung: **{(item.get('votes') or {}).get('score',0)}**"
        detail = f"{ZWRENCH} **Inhalt**\nModule/Bereiche: {', '.join(modules[:30]) or 'keine'}\nGröße: **{len(raw):,} Zeichen**\nSecret-Prüfung: **{'WARNUNG – möglicher geheimer Wert' if secret else 'unauffällig'}**\n\n-# Inhalte werden bewusst nicht vollständig in Discord ausgegeben, damit keine Tokens oder Kundendaten in Chatlogs gelangen."
        await self._send(interaction, panel(f"{INFO} Template-Inspektor", body, detail, color=WARN if secret else SUCCESS))
