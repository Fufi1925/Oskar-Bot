"""Configurable, isolated Discord bot used by LBoost Shop.

The configuration source is the shop dashboard's SQLite database. Discord
messages use Components V2 layouts; component custom IDs are handled globally
so tickets, role panels and giveaways continue working after restarts.
"""
from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import random
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks

from lbost_shop_app import db
from lbost_shop_app.config import Settings, get_settings

logger = logging.getLogger("lbost-shop-bot")
LINK_RE = re.compile(r"https?://[^\s]+", re.I)


def ids(raw: Any) -> set[int]:
    if isinstance(raw, list):
        raw = ",".join(map(str, raw))
    return {int(x.strip()) for x in str(raw or "").replace(";", ",").split(",") if x.strip().isdigit()}


def colour(raw: Any) -> discord.Colour:
    try:
        return discord.Colour(int(str(raw or "#5865f2").lstrip("#"), 16))
    except ValueError:
        return discord.Colour(0x5865F2)


def emoji(raw: Any) -> discord.PartialEmoji | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        parsed = discord.PartialEmoji.from_str(value)
        return parsed if parsed.id else None
    except Exception:
        return None


def layout(title: str, description: str, *, color: Any = "#5865f2", buttons: list[discord.ui.Button] | None = None,
           image_url: str = "", thumbnail_url: str = "", footer: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=colour(color))
    text = f"## {title}\n{description}"[:3900]
    container.add_item(discord.ui.TextDisplay(text))
    if thumbnail_url:
        section = discord.ui.Section(discord.ui.TextDisplay(" "), accessory=discord.ui.Thumbnail(thumbnail_url))
        container.add_item(section)
    if image_url:
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(image_url)))
    if buttons:
        for offset in range(0, min(len(buttons), 25), 5):
            row = discord.ui.ActionRow()
            for button in buttons[offset:offset + 5]:
                row.add_item(button)
            container.add_item(row)
    if footer:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {footer}"[:3900]))
    view.add_item(container)
    return view


class ShopBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.moderation = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.spam: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self.feature_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}

    def feature(self, guild_id: int, name: str) -> dict[str, Any]:
        key, now = (guild_id, name), time.monotonic()
        cached = self.feature_cache.get(key)
        if cached and now - cached[0] < 3:
            return cached[1]
        value = db.get_feature(guild_id, name, self.settings)
        self.feature_cache[key] = (now, value)
        return value

    async def setup_hook(self) -> None:
        db.init_features(self.settings)
        self.giveaway_worker.start()
        self.automation_worker.start()
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("Connected as %s (%s), %s guilds; feature runtime active", self.user, self.user.id if self.user else "?", len(self.guilds))

    async def send_layout(self, channel: discord.abc.Messageable, title: str, description: str, **kwargs: Any) -> discord.Message | None:
        try:
            return await channel.send(view=layout(title, description, **kwargs))
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send Components V2 message", exc_info=True)
            return None

    async def log(self, guild: discord.Guild, title: str, description: str, feature: str = "logging") -> None:
        cfg = self.feature(guild.id, feature)
        channel_id = int(cfg.get("channel_id") or cfg.get("log_channel_id") or 0)
        channel = guild.get_channel(channel_id)
        if channel:
            await self.send_layout(channel, title, description, color="#526dff")

    async def interaction_notice(self, interaction: discord.Interaction, title: str, text: str, *, error: bool = False) -> None:
        view = layout(title, text, color="#ed4245" if error else "#3ba55d")
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or not interaction.guild:
            return
        custom_id = str((interaction.data or {}).get("custom_id") or "")
        try:
            if custom_id.startswith("shop:ticket:create:"):
                await self.create_ticket(interaction, custom_id.rsplit(":", 1)[-1])
            elif custom_id.startswith("shop:ticket:"):
                await self.ticket_action(interaction, custom_id.rsplit(":", 1)[-1])
            elif custom_id.startswith("shop:role:"):
                await self.toggle_role(interaction, int(custom_id.rsplit(":", 1)[-1]))
            elif custom_id.startswith("shop:giveaway:"):
                await self.enter_giveaway(interaction, int(custom_id.rsplit(":", 1)[-1]))
        except Exception:
            logger.exception("Component failed: %s", custom_id)
            if not interaction.response.is_done():
                await self.interaction_notice(interaction, "Aktion fehlgeschlagen", "Die Aktion konnte nicht sicher ausgeführt werden.", error=True)

    # ── Tickets ──────────────────────────────────────────────────────
    def ticket_panel(self, guild_id: int, key: str) -> dict[str, Any]:
        cfg = self.feature(guild_id, "tickets")
        if key == "default":
            return cfg
        panels = cfg.get("panels_json") or []
        selected = next((p for p in panels if str(p.get("key")) == key), None)
        return {**cfg, **selected} if selected else cfg

    async def create_ticket(self, interaction: discord.Interaction, panel_key: str) -> None:
        guild = interaction.guild
        member = interaction.user
        cfg = self.ticket_panel(guild.id, panel_key)
        if not cfg.get("enabled", self.feature(guild.id, "tickets").get("enabled")):
            return await self.interaction_notice(interaction, "Tickets deaktiviert", "Dieses Ticket-Panel ist nicht aktiv.", error=True)
        open_roles = ids(cfg.get("open_role_ids"))
        if open_roles and not any(role.id in open_roles for role in member.roles):
            return await self.interaction_notice(interaction, "Keine Berechtigung", "Du besitzt keine Rolle, die dieses Ticket öffnen darf.", error=True)
        with db._connect(self.settings) as conn:
            existing = conn.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND owner_id=? AND status='open'", (guild.id, member.id)).fetchone()
        if existing and guild.get_channel(int(existing["channel_id"])):
            return await self.interaction_notice(interaction, "Ticket bereits offen", f"Du hast bereits <#{existing['channel_id']}>.", error=True)
        category = guild.get_channel(int(cfg.get("category_id") or 0))
        support_roles = [guild.get_role(role_id) for role_id in ids(cfg.get("support_role_ids"))]
        overwrites: dict[Any, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        for role in filter(None, support_roles):
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        name = f"ticket-{member.name}"[:90].lower().replace(" ", "-")
        channel = await guild.create_text_channel(name, category=category if isinstance(category, discord.CategoryChannel) else None, overwrites=overwrites, reason=f"LBoost ticket by {member}")
        with db._connect(self.settings) as conn:
            conn.execute("INSERT INTO tickets(guild_id,channel_id,owner_id,panel_key,created_at) VALUES(?,?,?,?,?)", (guild.id, channel.id, member.id, panel_key, int(time.time())))
        buttons = [
            discord.ui.Button(label=str(cfg.get("claim_label") or "Übernehmen")[:80], emoji=emoji(cfg.get("claim_emoji")), style=discord.ButtonStyle.primary, custom_id="shop:ticket:claim"),
            discord.ui.Button(label=str(cfg.get("close_label") or "Schließen")[:80], emoji=emoji(cfg.get("close_emoji")), style=discord.ButtonStyle.danger, custom_id="shop:ticket:close"),
        ]
        await self.send_layout(channel, str(cfg.get("ticket_title") or "Support-Ticket"), str(cfg.get("ticket_message") or f"<@{member.id}>, beschreibe bitte dein Anliegen."), color=cfg.get("color"), buttons=buttons)
        await self.interaction_notice(interaction, "Ticket erstellt", f"Dein Ticket wurde in <#{channel.id}> geöffnet.")
        await self.log(guild, "Ticket erstellt", f"Kanal: <#{channel.id}>\nNutzer: <@{member.id}>", "tickets")

    def can_manage_ticket(self, member: discord.Member, cfg: dict[str, Any]) -> bool:
        return member.guild_permissions.manage_channels or any(role.id in ids(cfg.get("support_role_ids")) for role in member.roles)

    async def ticket_action(self, interaction: discord.Interaction, action: str) -> None:
        guild, channel, member = interaction.guild, interaction.channel, interaction.user
        with db._connect(self.settings) as conn:
            ticket = conn.execute("SELECT * FROM tickets WHERE channel_id=?", (channel.id,)).fetchone()
        if not ticket:
            return await self.interaction_notice(interaction, "Kein Ticket", "Dieser Kanal ist kein aktives Ticket.", error=True)
        cfg = self.ticket_panel(guild.id, ticket["panel_key"])
        if not self.can_manage_ticket(member, cfg):
            return await self.interaction_notice(interaction, "Keine Berechtigung", "Du darfst dieses Ticket nicht verwalten.", error=True)
        if action == "claim":
            with db._connect(self.settings) as conn:
                conn.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (member.id, channel.id))
            return await self.interaction_notice(interaction, "Ticket übernommen", f"Dieses Ticket wird jetzt von <@{member.id}> bearbeitet.")
        if action == "close":
            await interaction.response.defer(ephemeral=True)
            transcript = await self.make_transcript(channel)
            log_channel = guild.get_channel(int(cfg.get("log_channel_id") or 0))
            if log_channel:
                await log_channel.send(view=layout("Ticket geschlossen", f"Ticket: {channel.name}\nGeschlossen von: <@{member.id}>"), file=discord.File(io.BytesIO(transcript), filename=f"transcript-{channel.id}.html"))
            owner = guild.get_member(int(ticket["owner_id"]))
            if owner:
                await channel.set_permissions(owner, send_messages=False, view_channel=True)
            with db._connect(self.settings) as conn:
                conn.execute("UPDATE tickets SET status='closed',closed_at=? WHERE channel_id=?", (int(time.time()), channel.id))
            buttons = [discord.ui.Button(label=str(cfg.get("delete_label") or "Löschen")[:80], emoji=emoji(cfg.get("delete_emoji")), style=discord.ButtonStyle.danger, custom_id="shop:ticket:delete")]
            await self.send_layout(channel, "Ticket geschlossen", f"Geschlossen von <@{member.id}>.", color="#ed4245", buttons=buttons)
            return await interaction.followup.send(view=layout("Ticket geschlossen", "Transkript wurde erstellt und das Ticket geschlossen."), ephemeral=True)
        if action == "delete":
            with db._connect(self.settings) as conn:
                conn.execute("UPDATE tickets SET status='deleted' WHERE channel_id=?", (channel.id,))
            await self.interaction_notice(interaction, "Ticket wird gelöscht", "Der Kanal wird in wenigen Sekunden gelöscht.")
            await asyncio.sleep(3)
            await channel.delete(reason=f"Ticket deleted by {member}")

    async def make_transcript(self, channel: discord.TextChannel) -> bytes:
        lines = ["<!doctype html><meta charset='utf-8'><title>Ticket Transcript</title><style>body{font:14px system-ui;background:#101218;color:#eee;padding:24px}.m{padding:10px;border-bottom:1px solid #2a2d36}.a{color:#8ea8ff;font-weight:bold}.t{color:#777;font-size:11px}</style><h1>Ticket Transcript</h1>"]
        async for message in channel.history(limit=2000, oldest_first=True):
            content = html.escape(message.clean_content)
            attachments = " ".join(html.escape(a.url) for a in message.attachments)
            lines.append(f"<div class='m'><span class='a'>{html.escape(str(message.author))}</span> <span class='t'>{message.created_at.isoformat()}</span><br>{content}<br>{attachments}</div>")
        return "\n".join(lines).encode("utf-8")

    async def toggle_role(self, interaction: discord.Interaction, role_id: int) -> None:
        role = interaction.guild.get_role(role_id)
        member = interaction.user
        if not role or role >= interaction.guild.me.top_role:
            return await self.interaction_notice(interaction, "Rolle nicht verfügbar", "Die Rolle kann nicht verwaltet werden.", error=True)
        if role in member.roles:
            await member.remove_roles(role, reason="LBoost reaction role")
            await self.interaction_notice(interaction, "Rolle entfernt", f"Die Rolle {role.mention} wurde entfernt.")
        else:
            await member.add_roles(role, reason="LBoost reaction role")
            await self.interaction_notice(interaction, "Rolle hinzugefügt", f"Die Rolle {role.mention} wurde hinzugefügt.")

    async def enter_giveaway(self, interaction: discord.Interaction, message_id: int) -> None:
        with db._connect(self.settings) as conn:
            giveaway = conn.execute("SELECT status FROM giveaways WHERE message_id=?", (message_id,)).fetchone()
            if not giveaway or giveaway["status"] != "active":
                return await self.interaction_notice(interaction, "Giveaway beendet", "Dieses Giveaway nimmt keine Teilnehmer mehr an.", error=True)
            conn.execute("INSERT OR IGNORE INTO giveaway_entries(message_id,user_id) VALUES(?,?)", (message_id, interaction.user.id))
        await self.interaction_notice(interaction, "Teilnahme gespeichert", "Du nimmst jetzt an diesem Giveaway teil.")

    # ── Events and automation ───────────────────────────────────────
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = self.feature(member.guild.id, "welcome")
        if cfg.get("enabled"):
            channel = member.guild.get_channel(int(cfg.get("welcome_channel_id") or 0))
            if channel:
                text = str(cfg.get("welcome_message") or "Willkommen {user} auf {server}.").replace("{user}", member.mention).replace("{server}", member.guild.name)
                await self.send_layout(channel, "Willkommen", text, image_url=str(cfg.get("welcome_image_url") or ""), color=cfg.get("color"))
        log_cfg = self.feature(member.guild.id, "logging")
        if log_cfg.get("enabled") and log_cfg.get("member_logs"):
            await self.log(member.guild, "Mitglied beigetreten", f"Nutzer: <@{member.id}>\nID: `{member.id}`")

    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = self.feature(member.guild.id, "welcome")
        if cfg.get("enabled") and cfg.get("leave_enabled"):
            channel = member.guild.get_channel(int(cfg.get("leave_channel_id") or 0))
            if channel:
                text = str(cfg.get("leave_message") or "{user} hat {server} verlassen.").replace("{user}", str(member)).replace("{server}", member.guild.name)
                await self.send_layout(channel, "Mitglied gegangen", text, image_url=str(cfg.get("leave_image_url") or ""))
        log_cfg = self.feature(member.guild.id, "logging")
        if log_cfg.get("enabled") and log_cfg.get("member_logs"):
            await self.log(member.guild, "Mitglied gegangen", f"Nutzer: {member}\nID: `{member.id}`")

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        member = message.author
        mod = self.feature(message.guild.id, "moderation")
        exempt = member.guild_permissions.manage_messages or any(r.id in ids(mod.get("exempt_role_ids")) for r in member.roles)
        if mod.get("enabled") and not exempt:
            if mod.get("anti_links") and LINK_RE.search(message.content):
                allowed = [x.strip().lower() for x in str(mod.get("allowed_domains") or "").split(",") if x.strip()]
                domains = [urlparse(x).netloc.lower() for x in LINK_RE.findall(message.content)]
                if any(not any(domain == item or domain.endswith("." + item) for item in allowed) for domain in domains):
                    await message.delete()
                    await member.timeout(timedelta(minutes=5), reason="LBoost anti-link")
                    await self.log(message.guild, "AutoMod: Link", f"Nutzer: <@{member.id}>\nKanal: <#{message.channel.id}>", "moderation")
                    return
            if mod.get("anti_spam"):
                key, now = (message.guild.id, member.id), time.monotonic()
                bucket = self.spam[key]
                while bucket and now - bucket[0] > 8:
                    bucket.popleft()
                bucket.append(now)
                if len(bucket) >= int(mod.get("spam_limit") or 6):
                    bucket.clear()
                    await message.delete()
                    await member.timeout(timedelta(minutes=5), reason="LBoost anti-spam")
                    await self.log(message.guild, "AutoMod: Spam", f"Nutzer: <@{member.id}>\nKanal: <#{message.channel.id}>", "moderation")
                    return
        automation = self.feature(message.guild.id, "automation")
        if automation.get("enabled"):
            content = message.content.strip()
            for item in automation.get("auto_responses_json") or []:
                trigger = str(item.get("trigger") or "")
                match = content.casefold() == trigger.casefold() if item.get("exact") else trigger.casefold() in content.casefold()
                if trigger and match:
                    await self.send_layout(message.channel, str(item.get("title") or "Automatische Antwort"), str(item.get("response") or ""), color=item.get("color"))
                    break
            if content.startswith("!"):
                command = content[1:].split()[0].casefold()
                for item in automation.get("custom_commands_json") or []:
                    if command == str(item.get("name") or "").casefold():
                        await self.send_layout(message.channel, str(item.get("title") or command), str(item.get("response") or ""), color=item.get("color"))
                        break

    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            cfg = self.feature(message.guild.id, "logging")
            if cfg.get("enabled") and cfg.get("message_logs"):
                await self.log(message.guild, "Nachricht gelöscht", f"Nutzer: <@{message.author.id}>\nKanal: <#{message.channel.id}>\nInhalt: {message.content[:1500] or '(leer)'}")

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild and not before.author.bot and before.content != after.content:
            cfg = self.feature(before.guild.id, "logging")
            if cfg.get("enabled") and cfg.get("message_logs"):
                await self.log(before.guild, "Nachricht bearbeitet", f"Nutzer: <@{before.author.id}>\nKanal: <#{before.channel.id}>\nVorher: {before.content[:700]}\nNachher: {after.content[:700]}")

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        cfg = self.feature(channel.guild.id, "logging")
        if cfg.get("enabled") and cfg.get("role_channel_logs"):
            await self.log(channel.guild, "Kanal erstellt", f"Kanal: {channel.name}\nID: `{channel.id}`")

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        cfg = self.feature(channel.guild.id, "logging")
        if cfg.get("enabled") and cfg.get("role_channel_logs"):
            await self.log(channel.guild, "Kanal gelöscht", f"Kanal: {channel.name}\nID: `{channel.id}`")

    async def on_guild_role_create(self, role: discord.Role) -> None:
        cfg = self.feature(role.guild.id, "logging")
        if cfg.get("enabled") and cfg.get("role_channel_logs"):
            await self.log(role.guild, "Rolle erstellt", f"Rolle: {role.name}\nID: `{role.id}`")

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        cfg = self.feature(role.guild.id, "logging")
        if cfg.get("enabled") and cfg.get("role_channel_logs"):
            await self.log(role.guild, "Rolle gelöscht", f"Rolle: {role.name}\nID: `{role.id}`")

    @tasks.loop(seconds=30)
    async def giveaway_worker(self) -> None:
        now = int(time.time())
        with db._connect(self.settings) as conn:
            rows = conn.execute("SELECT * FROM giveaways WHERE status='active' AND ends_at<=?", (now,)).fetchall()
        for row in rows:
            await self.finish_giveaway(row)

    @giveaway_worker.before_loop
    async def before_giveaways(self) -> None:
        await self.wait_until_ready()

    async def finish_giveaway(self, row: Any) -> None:
        guild = self.get_guild(int(row["guild_id"]))
        channel = guild.get_channel(int(row["channel_id"])) if guild else None
        with db._connect(self.settings) as conn:
            entrants = [int(x["user_id"]) for x in conn.execute("SELECT user_id FROM giveaway_entries WHERE message_id=?", (row["message_id"],)).fetchall()]
            winners = random.sample(entrants, min(len(entrants), int(row["winners"]))) if entrants else []
            conn.execute("UPDATE giveaways SET status='ended',winner_ids=? WHERE message_id=?", (json.dumps(winners), row["message_id"]))
        if channel:
            text = "Gewinner: " + ", ".join(f"<@{uid}>" for uid in winners) if winners else "Es gab keine gültigen Teilnehmer."
            await self.send_layout(channel, f"Giveaway beendet: {row['prize']}", text, color="#57f287")

    @tasks.loop(minutes=1)
    async def automation_worker(self) -> None:
        now = int(time.time())
        for guild in self.guilds:
            cfg = self.feature(guild.id, "automation")
            if not cfg.get("enabled"):
                continue
            changed = False
            for item in cfg.get("announcements_json") or []:
                if int(item.get("next_run") or 0) > now:
                    continue
                channel = guild.get_channel(int(item.get("channel_id") or 0))
                if channel and item.get("content"):
                    await self.send_layout(channel, str(item.get("title") or "Ankündigung"), str(item["content"]), color=item.get("color"))
                item["next_run"] = now + max(60, int(item.get("interval_minutes") or 60) * 60)
                changed = True
            if changed:
                db.set_feature(guild.id, "automation", cfg, self.user.id if self.user else 0, self.settings)

    @automation_worker.before_loop
    async def before_automation(self) -> None:
        await self.wait_until_ready()


# ── Slash commands ─────────────────────────────────────────────────────
async def require_manage(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
        bot: ShopBot = interaction.client
        await bot.interaction_notice(interaction, "Keine Berechtigung", "Du benötigst die Berechtigung Server verwalten.", error=True)
        return False
    return True


def register_commands(bot: ShopBot) -> None:
    @bot.tree.command(name="ticket-panel", description="Sendet ein konfiguriertes Ticket-Panel")
    @app_commands.describe(panel="Panel-Key aus der Dashboard-Konfiguration")
    async def ticket_panel_command(interaction: discord.Interaction, panel: str = "default"):
        if not await require_manage(interaction): return
        cfg = bot.ticket_panel(interaction.guild.id, panel)
        if not cfg.get("enabled"):
            return await bot.interaction_notice(interaction, "Tickets deaktiviert", "Aktiviere das Modul zuerst im Dashboard.", error=True)
        channel = interaction.guild.get_channel(int(cfg.get("panel_channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanal fehlt", "Wähle im Dashboard einen gültigen Textkanal.", error=True)
        button = discord.ui.Button(label=str(cfg.get("button_label") or "Ticket öffnen")[:80], emoji=emoji(cfg.get("button_emoji")), style=discord.ButtonStyle.primary, custom_id=f"shop:ticket:create:{panel}"[:100])
        message = await bot.send_layout(channel, str(cfg.get("title") or "Support"), str(cfg.get("description") or "Öffne ein Ticket, um das Team zu kontaktieren."), color=cfg.get("color"), buttons=[button], image_url=str(cfg.get("image_url") or ""), thumbnail_url=str(cfg.get("thumbnail_url") or ""), footer=str(cfg.get("footer") or ""))
        await bot.interaction_notice(interaction, "Panel gesendet", f"Das Ticket-Panel wurde in <#{channel.id}> veröffentlicht." if message else "Panel konnte nicht gesendet werden.", error=not bool(message))

    @bot.tree.command(name="reaction-panel", description="Sendet ein konfiguriertes Rollen-Panel")
    @app_commands.describe(panel="Index des Panels, beginnend mit 0")
    async def reaction_panel_command(interaction: discord.Interaction, panel: int = 0):
        if not await require_manage(interaction): return
        cfg = bot.feature(interaction.guild.id, "reaction_roles")
        panels = [{**cfg, "roles_json": cfg.get("roles_json") or []}] + list(cfg.get("panels_json") or [])
        selected = panels[panel] if 0 <= panel < len(panels) else None
        if not cfg.get("enabled") or not selected:
            return await bot.interaction_notice(interaction, "Panel nicht verfügbar", "Prüfe die Dashboard-Konfiguration.", error=True)
        channel = interaction.guild.get_channel(int(selected.get("channel_id") or cfg.get("channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanal fehlt", "Wähle im Dashboard einen gültigen Textkanal.", error=True)
        buttons = [discord.ui.Button(label=str(item.get("label") or "Rolle")[:80], emoji=emoji(item.get("emoji")), style=discord.ButtonStyle.secondary, custom_id=f"shop:role:{int(item['role_id'])}") for item in selected.get("roles_json", [])[:25] if str(item.get("role_id", "")).isdigit()]
        sent = await bot.send_layout(channel, str(selected.get("title") or "Rollen auswählen"), str(selected.get("description") or "Wähle deine Rollen über die Buttons."), color=selected.get("color"), buttons=buttons)
        await bot.interaction_notice(interaction, "Panel gesendet", f"Das Rollen-Panel wurde in <#{channel.id}> veröffentlicht." if sent else "Panel konnte nicht gesendet werden.", error=not bool(sent))

    @bot.tree.command(name="warn", description="Verwarnt ein Mitglied")
    async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
        if not bot.feature(interaction.guild.id, "moderation").get("enabled"): return await bot.interaction_notice(interaction, "Moderation deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        if not interaction.user.guild_permissions.moderate_members: return await bot.interaction_notice(interaction, "Keine Berechtigung", "Dir fehlt Mitglieder moderieren.", error=True)
        with db._connect(bot.settings) as conn:
            conn.execute("INSERT INTO warnings(guild_id,user_id,moderator_id,reason,created_at) VALUES(?,?,?,?,?)", (interaction.guild.id, member.id, interaction.user.id, reason[:1000], int(time.time())))
        await bot.interaction_notice(interaction, "Verwarnung gespeichert", f"{member.mention} wurde verwarnt.")
        await bot.log(interaction.guild, "Verwarnung", f"Mitglied: {member.mention}\nModerator: <@{interaction.user.id}>\nGrund: {reason}", "moderation")

    @bot.tree.command(name="mute", description="Versetzt ein Mitglied in Timeout")
    async def mute(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "Kein Grund angegeben"):
        if not bot.feature(interaction.guild.id, "moderation").get("enabled"): return await bot.interaction_notice(interaction, "Moderation deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        if not interaction.user.guild_permissions.moderate_members: return await bot.interaction_notice(interaction, "Keine Berechtigung", "Dir fehlt Mitglieder moderieren.", error=True)
        await member.timeout(timedelta(minutes=minutes), reason=f"{interaction.user}: {reason}")
        await bot.interaction_notice(interaction, "Timeout gesetzt", f"{member.mention} wurde für {minutes} Minuten stummgeschaltet.")
        await bot.log(interaction.guild, "Timeout", f"Mitglied: {member.mention}\nDauer: {minutes} Minuten\nGrund: {reason}", "moderation")

    @bot.tree.command(name="kick", description="Entfernt ein Mitglied")
    async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben"):
        if not bot.feature(interaction.guild.id, "moderation").get("enabled"): return await bot.interaction_notice(interaction, "Moderation deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        if not interaction.user.guild_permissions.kick_members: return await bot.interaction_notice(interaction, "Keine Berechtigung", "Dir fehlt Mitglieder kicken.", error=True)
        await member.kick(reason=f"{interaction.user}: {reason}")
        await bot.interaction_notice(interaction, "Mitglied entfernt", f"{member} wurde entfernt.")
        await bot.log(interaction.guild, "Kick", f"Mitglied: {member}\nModerator: <@{interaction.user.id}>\nGrund: {reason}", "moderation")

    @bot.tree.command(name="ban", description="Bannt ein Mitglied")
    async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben"):
        if not bot.feature(interaction.guild.id, "moderation").get("enabled"): return await bot.interaction_notice(interaction, "Moderation deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        if not interaction.user.guild_permissions.ban_members: return await bot.interaction_notice(interaction, "Keine Berechtigung", "Dir fehlt Mitglieder bannen.", error=True)
        await member.ban(reason=f"{interaction.user}: {reason}")
        await bot.interaction_notice(interaction, "Mitglied gebannt", f"{member} wurde gebannt.")
        await bot.log(interaction.guild, "Ban", f"Mitglied: {member}\nModerator: <@{interaction.user.id}>\nGrund: {reason}", "moderation")

    @bot.tree.command(name="giveaway", description="Startet ein Giveaway")
    async def giveaway(interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 525600], winners: app_commands.Range[int, 1, 20], prize: str):
        if not await require_manage(interaction): return
        cfg = bot.feature(interaction.guild.id, "giveaways")
        if not cfg.get("enabled"): return await bot.interaction_notice(interaction, "Giveaways deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        await interaction.response.defer(ephemeral=True)
        ends = int(time.time()) + minutes * 60
        pending_button = discord.ui.Button(label="Teilnehmen", style=discord.ButtonStyle.success, custom_id="shop:giveaway:pending")
        message = await interaction.channel.send(view=layout(prize, f"Endet: <t:{ends}:R>\nGewinner: {winners}", color="#57f287", buttons=[pending_button]))
        # Replace the placeholder with a fresh persistent button containing the message ID.
        active_button = discord.ui.Button(label="Teilnehmen", style=discord.ButtonStyle.success, custom_id=f"shop:giveaway:{message.id}")
        await message.edit(view=layout(prize, f"Endet: <t:{ends}:R>\nGewinner: {winners}", color="#57f287", buttons=[active_button]))
        with db._connect(bot.settings) as conn:
            conn.execute("INSERT INTO giveaways(message_id,guild_id,channel_id,prize,winners,ends_at) VALUES(?,?,?,?,?,?)", (message.id, interaction.guild.id, interaction.channel.id, prize[:500], winners, ends))
        await interaction.followup.send(view=layout("Giveaway gestartet", f"Nachricht: `{message.id}`"), ephemeral=True)

    @bot.tree.command(name="giveaway-reroll", description="Zieht Gewinner eines Giveaways neu")
    async def giveaway_reroll(interaction: discord.Interaction, message_id: str):
        if not await require_manage(interaction): return
        if not message_id.isdigit(): return await bot.interaction_notice(interaction, "Ungültige ID", "Gib eine gültige Nachrichten-ID an.", error=True)
        with db._connect(bot.settings) as conn:
            row = conn.execute("SELECT * FROM giveaways WHERE message_id=?", (int(message_id),)).fetchone()
            entrants = [int(x["user_id"]) for x in conn.execute("SELECT user_id FROM giveaway_entries WHERE message_id=?", (int(message_id),)).fetchall()]
        if not row or not entrants: return await bot.interaction_notice(interaction, "Nicht möglich", "Giveaway oder Teilnehmer wurden nicht gefunden.", error=True)
        winners_list = random.sample(entrants, min(len(entrants), int(row["winners"])))
        await bot.send_layout(interaction.channel, f"Giveaway neu gezogen: {row['prize']}", "Gewinner: " + ", ".join(f"<@{x}>" for x in winners_list), color="#57f287")
        await bot.interaction_notice(interaction, "Neu gezogen", "Die Gewinner wurden neu ermittelt.")

    @bot.tree.command(name="announce", description="Sendet eine Components-V2-Ankündigung")
    async def announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, text: str):
        if not await require_manage(interaction): return
        sent = await bot.send_layout(channel, title, text)
        await bot.interaction_notice(interaction, "Ankündigung gesendet", f"Gesendet in {channel.mention}." if sent else "Senden fehlgeschlagen.", error=not bool(sent))

    @bot.tree.error
    async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error("Slash command failed: %s", error, exc_info=(type(error), error, error.__traceback__))
        try:
            await bot.interaction_notice(interaction, "Befehl fehlgeschlagen", "Der Befehl konnte nicht sicher ausgeführt werden. Prüfe Rollen und Bot-Berechtigungen.", error=True)
        except discord.HTTPException:
            pass


def create_bot() -> ShopBot:
    settings = get_settings()
    bot = ShopBot(settings)
    register_commands(bot)
    return bot
