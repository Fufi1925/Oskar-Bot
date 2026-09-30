"""Configurable, isolated Discord bot used by LBoost Shop.

The configuration source is the shop dashboard's SQLite database. Discord
messages use Components V2 layouts; component custom IDs are handled globally
so tickets, role panels and giveaways continue working after restarts.

Text rules (placeholders, question filtering, channel naming) live in
``lbost_shop_app.regeln`` so the dashboard preview and this bot calculate the
same output — the same split University Bot uses.
"""
from __future__ import annotations

import asyncio
import html
import io
import logging
import random
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from lbost_shop_app import db, regeln
from lbost_shop_app.config import Settings, get_settings

logger = logging.getLogger("lbost-shop-bot")
LINK_RE = re.compile(r"https?://[^\s]+", re.I)
LOG_CATEGORIES = (
    "message_events", "join_leave_events", "member_moderation",
    "voice_events", "channel_events", "role_events", "emoji_events",
    "reaction_events", "system_events",
)
OLD_LOG_FLAGS = {
    "message_events": "message_logs", "join_leave_events": "member_logs",
    "member_moderation": "moderation_logs", "voice_events": "member_logs",
    "channel_events": "role_channel_logs", "role_events": "role_channel_logs",
    "emoji_events": "role_channel_logs", "reaction_events": "message_logs",
    "system_events": "role_channel_logs",
}

#: Wie alt ein Zeitstempel im Spam-Eimer sein darf, bevor er verworfen wird.
SPAM_FENSTER = 8.0
#: Hochstens so viele Nutzer gleichzeitig im Spam-Zähler (Speicherbremse).
SPAM_MAX_EINTRAEGE = 4000


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
           image_url: str = "", extra_image_url: str = "", thumbnail_url: str = "", footer: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=colour(color))
    text = f"## {title}\n{description}"[:3900]
    container.add_item(discord.ui.TextDisplay(text))
    if thumbnail_url:
        section = discord.ui.Section(discord.ui.TextDisplay(" "), accessory=discord.ui.Thumbnail(thumbnail_url))
        container.add_item(section)
    if image_url or extra_image_url:
        gallery = discord.ui.MediaGallery()
        if image_url:
            gallery.add_item(media=image_url)
        if extra_image_url:
            gallery.add_item(media=extra_image_url)
        container.add_item(gallery)
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


class LogDescription(str):
    """String for the archive plus the original University field sections."""

    def __new__(cls, fields: list[tuple[str, Any]]):
        sections = [f"**{name}**\n{value}" for name, value in fields if value not in (None, "")]
        value = "\n\n".join(sections)
        instance = super().__new__(cls, value)
        instance.sections = sections
        return instance


def university_log_layout(title: str, description: str, *, footer: str = "") -> discord.ui.LayoutView:
    """Exact Components-V2 structure produced by University's log adapter."""
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xFF0000)
    container.add_item(discord.ui.TextDisplay(f"**{title}**"))
    sections = list(getattr(description, "sections", None) or [str(description)])
    if footer:
        sections.append(f"*{footer}*")
    for section in sections:
        if not section:
            continue
        container.add_item(discord.ui.Separator(visible=True))
        container.add_item(discord.ui.TextDisplay(str(section)[:4000]))
    view.add_item(container)
    return view


def taugliche_teilnehmer(teilnehmer: list[int], mitglieder: set[int]) -> list[int]:
    """Nur wer auf dem Server ist, kann gewinnen.

    Vorher landeten Ausgetretene und Gebannte in der Ziehung; die Erwähnung
    ins Leere, der Gewinner offiziell vorhanden. Der Filter ist eine eigene
    Funktion, damit er ohne Discord-Objekte prüfbar ist.
    """
    tauglich: list[int] = []
    for uid in teilnehmer or []:
        try:
            nummer = int(uid)
        except (TypeError, ValueError):
            continue
        if nummer in mitglieder:
            tauglich.append(nummer)
    return tauglich


def _zeit(stempel: int) -> str:
    if not stempel:
        return "—"
    return datetime.fromtimestamp(int(stempel), timezone.utc).astimezone().strftime("%d.%m. %H:%M")


class TicketFragenModal(discord.ui.Modal):
    """Fragen vor dem Öffnen — dieselbe Regel wie die Dashboard-Vorschau."""

    def __init__(self, bot: "ShopBot", panel_key: str, fragen: list[dict[str, Any]]):
        super().__init__(title="Ticket erstellen", timeout=300)
        self.bot = bot
        self.panel_key = panel_key
        self.fragen = fragen
        self.eingaben: list[tuple[str, str, Any]] = []
        for frage in fragen[:regeln.MAX_TICKET_QUESTIONS]:
            label = str(frage.get("label") or "Frage")[:regeln.MAX_FRAGE_LABEL]
            typ = str(frage.get("type") or "short")
            pflicht = bool(frage.get("required", True))
            if typ == "image":
                feld = discord.ui.FileUpload(required=pflicht, min_values=1 if pflicht else 0, max_values=1)
                self.eingaben.append((label, "image", feld))
                self.add_item(discord.ui.Label(
                    text=label,
                    description=str(frage.get("placeholder") or "Bild hochladen")[:regeln.MAX_FRAGE_HINWEIS],
                    component=feld,
                ))
                continue
            feld = discord.ui.TextInput(
                label=label,
                placeholder=str(frage.get("placeholder") or "").strip()[:regeln.MAX_FRAGE_HINWEIS] or None,
                required=pflicht,
                style=discord.TextStyle.paragraph if typ == "paragraph" else discord.TextStyle.short,
                max_length=regeln.MAX_ANTWORT_LANG if typ == "paragraph" else regeln.MAX_ANTWORT_KURZ,
            )
            self.eingaben.append((label, typ, feld))
            self.add_item(feld)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        antworten = []
        for label, typ, feld in self.eingaben:
            if typ == "image":
                antworten.append({"label": label, "type": "image", "attachments": list(feld.values or [])})
            else:
                antworten.append({"label": label, "type": typ, "value": feld.value})
        await self.bot.create_ticket(interaction, self.panel_key, antworten=antworten)


class ShopBot(commands.Bot):
    def __init__(self, settings: Settings, *, privileged_intents: bool = True):
        intents = discord.Intents.none()
        intents.guilds = True
        # These two intents must be switched on in Discord's Developer Portal.
        # A fresh application commonly has them disabled. The launcher first
        # tries the complete mode and, if Discord rejects it with gateway code
        # 4014, reconnects without only these privileged intents so the bot is
        # online instead of entering an endless crash loop.
        intents.members = privileged_intents
        intents.message_content = privileged_intents
        intents.moderation = True
        intents.messages = True
        intents.reactions = True
        intents.voice_states = True
        intents.emojis_and_stickers = True
        intents.invites = True
        async def shop_prefix(_bot: commands.Bot, message: discord.Message) -> str:
            if not message.guild:
                return "!"
            cfg = self.feature(message.guild.id, "moderation")
            value = str(cfg.get("prefix") or "!").strip()
            return value[:10] if value else "!"

        super().__init__(command_prefix=shop_prefix, intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.privileged_intents = privileged_intents
        self.spam: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._cooldowns: dict[str, float] = {}
        self._audit_cache: dict[tuple[int, str, int | None], tuple[Any, float]] = {}
        self.feature_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}

    def feature(self, guild_id: int, name: str) -> dict[str, Any]:
        key, now = (guild_id, name), time.monotonic()
        cached = self.feature_cache.get(key)
        if cached and now - cached[0] < 3:
            return cached[1]
        value = db.get_feature(guild_id, name, self.settings)
        self.feature_cache[key] = (now, value)
        if len(self.feature_cache) > 4000:  # Server, die niemand mehr sieht, rauswerfen
            self.feature_cache = {k: v for k, v in self.feature_cache.items() if now - v[0] < 30}
        return value

    async def setup_hook(self) -> None:
        db.init_features(self.settings)
        db.prune_audit(self.settings)
        self.giveaway_worker.start()
        self.automation_worker.start()
        self.heartbeat.start()
        await self.tree.sync()

    async def on_ready(self) -> None:
        mode = "complete" if self.privileged_intents else "online (privileged intents disabled in Developer Portal)"
        logger.info("Connected as %s (%s), %s guilds; feature runtime %s", self.user, self.user.id if self.user else "?", len(self.guilds), mode)
        # Do not wait for the 20-second task interval before the dashboard can
        # see a successful login.
        self.write_heartbeat()

    def write_heartbeat(self) -> None:
        db.set_state(0, "bot_heartbeat", {
            "zeit": int(time.time()),
            "gilden": len(self.guilds),
            "name": str(self.user) if self.user else "",
            "vollstaendig": self.privileged_intents,
        }, self.settings)

    # ── Hilfen ────────────────────────────────────────────────────────
    async def send_layout(self, channel: discord.abc.Messageable, title: str, description: str, **kwargs: Any) -> discord.Message | None:
        try:
            return await channel.send(view=layout(title, description, **kwargs))
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send Components V2 message", exc_info=True)
            return None

    def logging_config(self, guild_id: int) -> dict[str, Any]:
        raw = dict(self.feature(guild_id, "logging") or {})
        fallback = int(raw.get("channel_id") or 0)
        channels = dict(raw.get("log_channels") or {})
        enabled = dict(raw.get("log_enabled") or {})
        for category in LOG_CATEGORIES:
            if fallback and not channels.get(category):
                channels[category] = fallback
            if category not in enabled:
                enabled[category] = bool(raw.get(OLD_LOG_FLAGS[category], False))
        return {
            "enabled": bool(raw.get("enabled")),
            "log_channels": channels,
            "log_enabled": enabled,
            "ignore_channels": ids(raw.get("ignore_channels")),
            "ignore_roles": ids(raw.get("ignore_roles")),
            "ignore_users": ids(raw.get("ignore_users")),
            "auto_delete_duration": max(0, min(86400, int(raw.get("auto_delete_duration") or 0))),
        }

    def logging_ignored(
        self,
        cfg: dict[str, Any],
        *,
        channel_id: int | None = None,
        user: discord.abc.User | None = None,
    ) -> bool:
        if channel_id and channel_id in cfg["ignore_channels"]:
            return True
        if user and user.id in cfg["ignore_users"]:
            return True
        return bool(
            isinstance(user, discord.Member)
            and any(role.id in cfg["ignore_roles"] for role in user.roles)
        )

    async def audit_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int | None = None,
    ) -> discord.AuditLogEntry | None:
        """University-compatible audit lookup with a short per-target cache."""
        me = getattr(guild, "me", None)
        if me is not None and not me.guild_permissions.view_audit_log:
            return None
        cache_key = (guild.id, str(action), target_id)
        cached = self._audit_cache.get(cache_key)
        if cached and time.monotonic() - cached[1] < 10:
            return cached[0]
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if target_id is None or int(getattr(entry.target, "id", 0)) == int(target_id):
                    self._audit_cache[cache_key] = (entry, time.monotonic())
                    if len(self._audit_cache) > 1000:
                        self._audit_cache = {
                            key: value for key, value in self._audit_cache.items()
                            if time.monotonic() - value[1] < 300
                        }
                    return entry
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            return None
        return None

    async def audit_actor(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int | None = None,
    ) -> discord.User | discord.Member | None:
        entry = await self.audit_entry(guild, action, target_id)
        return entry.user if entry is not None else None

    @staticmethod
    def log_fields(*fields: tuple[str, Any]) -> LogDescription:
        """Keep fields separate exactly like University's CV2 adapter."""
        return LogDescription(list(fields))

    async def log_event(
        self,
        guild: discord.Guild,
        category: str,
        title: str,
        description: str,
        *,
        channel_id: int | None = None,
        user: discord.abc.User | None = None,
        footer: str = "",
    ) -> None:
        cfg = self.logging_config(guild.id)
        if (
            category not in LOG_CATEGORIES
            or not cfg["log_enabled"].get(category)
            or self.logging_ignored(cfg, channel_id=channel_id, user=user)
        ):
            return
        db.add_event_log(
            guild.id,
            category,
            title,
            description,
            channel_id,
            getattr(user, "id", None),
            self.settings,
        )
        target_id = int(cfg["log_channels"].get(category) or 0)
        channel = guild.get_channel(target_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            await channel.send(
                view=university_log_layout(title, description, footer=footer),
                delete_after=cfg["auto_delete_duration"] or None,
                allowed_mentions=None,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Logging failed for guild=%s category=%s", guild.id, category)

    async def log(self, guild: discord.Guild, title: str, description: str, feature: str = "logging") -> None:
        """Module-specific logs stay isolated; Discord events use log_event."""
        if feature == "logging":
            await self.log_event(guild, "system_events", title, description)
            return
        cfg = self.feature(guild.id, feature)
        channel_id = int(cfg.get("channel_id") or cfg.get("log_channel_id") or 0)
        channel = guild.get_channel(channel_id)
        if channel:
            await self.send_layout(channel, title, description, color="#526dff")

    async def interaction_notice(self, interaction: discord.Interaction, title: str, text: str, *, error: bool = False) -> None:
        view = layout(title, text, color="#ed4245" if error else "#3ba55d")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(view=view, ephemeral=True)
            else:
                await interaction.response.send_message(view=view, ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            logger.warning("Could not answer interaction", exc_info=True)

    async def safe_delete(self, message: discord.Message, grund: str) -> bool:
        """Löschen, ohne an fehlenden Rechten zu zerbrechen.

        Ohne Abfrage warf ``Forbidden`` und der ganze Event-Handler starb —
        das nächste Mitglied hätte keinen Spam-Schutz mehr abbekommen, solange
        niemand den Bot neu startet.
        """
        try:
            await message.delete()
            return True
        except discord.Forbidden:
            logger.info("Missing permissions to delete a message in #%s (%s)", getattr(message.channel, "name", "?"), grund)
        except discord.HTTPException:
            logger.warning("Deleting message failed (%s)", grund, exc_info=True)
        return False

    async def safe_timeout(self, member: discord.Member, minuten: int, grund: str) -> bool:
        try:
            await member.timeout(timedelta(minutes=minuten), reason=f"LBoost Shop: {grund}")
            return True
        except discord.Forbidden:
            logger.info("Missing permissions to time out %s (%s)", member, grund)
        except discord.HTTPException:
            logger.warning("Timeout failed for %s (%s)", member, grund, exc_info=True)
        return False

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or not interaction.guild:
            return
        custom_id = str((interaction.data or {}).get("custom_id") or "")
        try:
            if custom_id.startswith("shop:ticket:create:"):
                await self.start_ticket(interaction, custom_id.rsplit(":", 1)[-1])
            elif custom_id.startswith("shop:ticket:"):
                await self.ticket_action(interaction, custom_id.rsplit(":", 1)[-1])
            elif custom_id.startswith("shop:role:"):
                await self.toggle_role(interaction, int(custom_id.rsplit(":", 1)[-1]))
            elif custom_id.startswith("shop:giveaway:"):
                await self.enter_giveaway(interaction, int(custom_id.rsplit(":", 1)[-1]))
        except Exception:
            logger.exception("Component failed: %s", custom_id)
            await self.interaction_notice(interaction, "Aktion fehlgeschlagen", "Die Aktion konnte nicht sicher ausgeführt werden.", error=True)

    # ── University reaction roles ───────────────────────────────────
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == (self.user.id if self.user else 0):
            return
        mapping = db.reaktionsrolle(payload.guild_id, payload.message_id, str(payload.emoji), self.settings)
        if not mapping:
            return
        guild = self.get_guild(payload.guild_id)
        if not guild:
            return
        member = payload.member or guild.get_member(payload.user_id)
        role = guild.get_role(int(mapping["role_id"]))
        if not member or member.bot or not role or role.managed or not guild.me or role >= guild.me.top_role:
            return
        try:
            await member.add_roles(role, reason="LBoost reaction role added")
            if db.reaktionsrollen_dm(guild.id, self.settings):
                try:
                    await member.send(view=layout("Rolle erhalten", f"Du hast auf **{guild.name}** die Rolle **{role.name}** erhalten."))
                except (discord.Forbidden, discord.HTTPException):
                    pass
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not add reaction role %s in guild %s", role.id, guild.id)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == (self.user.id if self.user else 0):
            return
        mapping = db.reaktionsrolle(payload.guild_id, payload.message_id, str(payload.emoji), self.settings)
        if not mapping:
            return
        guild = self.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(mapping["role_id"]))
        if not member or member.bot or not role or role.managed or not guild.me or role >= guild.me.top_role:
            return
        try:
            await member.remove_roles(role, reason="LBoost reaction role removed")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not remove reaction role %s in guild %s", role.id, guild.id)

    # ── Tickets ──────────────────────────────────────────────────────
    def ticket_panel(self, guild_id: int, key: str) -> dict[str, Any]:
        cfg = self.feature(guild_id, "tickets")
        if key == "default":
            return cfg
        panels = cfg.get("panels_json") or []
        selected = next((p for p in panels if isinstance(p, dict) and str(p.get("key")) == key), None)
        return {**cfg, **selected} if selected else cfg

    async def start_ticket(self, interaction: discord.Interaction, panel_key: str) -> None:
        """Knopfdruck: erst das Fragen-Modal, sonst direkt das Ticket.

        Das Modal muss die *erste* Antwort auf die Interaktion sein — wer
        vorher ``defer`` aufruft, kann kein Modal mehr senden und der Knopf
        wirkt kaputt.
        """
        cfg = self.ticket_panel(interaction.guild.id, panel_key)
        fragen = regeln.fragen_bereinigen(cfg.get("questions_json"))
        if fragen:
            await interaction.response.send_modal(TicketFragenModal(self, panel_key, fragen))
            return
        await interaction.response.defer(ephemeral=True)
        await self.create_ticket(interaction, panel_key)

    async def create_ticket(self, interaction: discord.Interaction, panel_key: str,
                            antworten: list[dict[str, Any]] | None = None) -> None:
        guild = interaction.guild
        member = interaction.user
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        cfg = self.ticket_panel(guild.id, panel_key)
        if not cfg.get("enabled", self.feature(guild.id, "tickets").get("enabled")):
            return await self.interaction_notice(interaction, "Tickets deaktiviert", "Dieses Ticket-Panel ist nicht aktiv.", error=True)
        offene_rollen = ids(cfg.get("open_role_ids"))
        if offene_rollen and not any(role.id in offene_rollen for role in member.roles):
            return await self.interaction_notice(interaction, "Keine Berechtigung", "Du besitzt keine Rolle, die dieses Ticket öffnen darf.", error=True)
        bereits = db.offene_tickets_fuer_nutzer(guild.id, member.id, self.settings)
        if bereits and guild.get_channel(int(bereits)):
            return await self.interaction_notice(interaction, "Ticket bereits offen", f"Du hast bereits <#{bereits}>.", error=True)

        kategorie = guild.get_channel(int(cfg.get("category_id") or 0))
        support_rollen = [guild.get_role(role_id) for role_id in ids(cfg.get("support_role_ids"))]
        overwrites: dict[Any, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True, attach_files=True),
        }
        for role in filter(None, support_rollen):
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)

        nummer = db.naechste_ticket_nummer(guild.id, self.settings)
        anzeige = str(getattr(member, "global_name", None) or member.name or "nutzer")
        name = regeln.kanal_name(nummer, anzeige, str(cfg.get("channel_name_format") or ""))
        try:
            channel = await guild.create_text_channel(
                name,
                category=kategorie if isinstance(kategorie, discord.CategoryChannel) else None,
                overwrites=overwrites,
                slowmode_seconds=max(0, min(30, int(cfg.get("slowmode_seconds") or 0))),
                reason=f"LBoost Shop ticket by {member}",
            )
        except discord.Forbidden:
            return await self.interaction_notice(interaction, "Keine Rechte", "Der Bot darf in dieser Kategorie keine Kanäle anlegen. Prüfe die Rollenberechtigung.", error=True)
        except discord.HTTPException as fehler:
            return await self.interaction_notice(interaction, "Ticket nicht möglich", f"Discord hat den Kanal abgelehnt: {getattr(fehler, 'text', 'unbekannter Fehler')}", error=True)

        db.ticket_anlegen(guild.id, channel.id, member.id, panel_key, nummer, antworten or [], self.settings)
        worte = regeln.ersetzungen(
            ticket_number=f"{nummer:04d}",
            user=f"<@{member.id}>",
            category=kategorie.name if isinstance(kategorie, discord.CategoryChannel) else "Support",
            server=guild.name,
            channel=f"#{channel.name}",
        )
        texte = regeln.ticket_texte(cfg, worte, antworten=antworten)
        titel = texte["titel"]
        text = texte["nachricht"]
        buttons = [
            discord.ui.Button(label=str(cfg.get("claim_label") or "Übernehmen")[:80], emoji=emoji(cfg.get("claim_emoji")), style=discord.ButtonStyle.primary, custom_id="shop:ticket:claim"),
            discord.ui.Button(label=str(cfg.get("close_label") or "Schließen")[:80], emoji=emoji(cfg.get("close_emoji")), style=discord.ButtonStyle.danger, custom_id="shop:ticket:close"),
        ]
        await self.send_layout(channel, titel, text, color=cfg.get("color"), buttons=buttons,
                               image_url=str(cfg.get("ticket_image_url") or ""),
                               thumbnail_url=str(cfg.get("ticket_thumbnail_url") or ""))

        bestaetigung = texte["bestaetigung"]
        await interaction.followup.send(view=layout("Ticket erstellt", bestaetigung, color="#3ba55d"), ephemeral=True)
        if support_rollen and cfg.get("mention_support", True):
            erwahnung = " ".join(role.mention for role in filter(None, support_rollen))
            if erwahnung:
                await self.send_layout(channel, "Support angefragt", f"{erwahnung} — ein neues Ticket ist offen.", color="#5865f2")
        await self.log(guild, "Ticket erstellt", f"Kanal: <#{channel.id}>\nNutzer: <@{member.id}>\nNummer: `#{nummer:04d}`", "tickets")

    def can_manage_ticket(self, member: discord.Member, cfg: dict[str, Any]) -> bool:
        return member.guild_permissions.manage_channels or any(role.id in ids(cfg.get("support_role_ids")) for role in member.roles)

    async def ticket_action(self, interaction: discord.Interaction, action: str) -> None:
        guild, channel, member = interaction.guild, interaction.channel, interaction.user
        ticket = db.ticket_fuer_kanal(channel.id, self.settings)
        if not ticket:
            return await self.interaction_notice(interaction, "Kein Ticket", "Dieser Kanal ist kein aktives Ticket.", error=True)
        cfg = self.ticket_panel(guild.id, str(ticket["panel_key"]))
        if not self.can_manage_ticket(member, cfg):
            return await self.interaction_notice(interaction, "Keine Berechtigung", "Du darfst dieses Ticket nicht verwalten.", error=True)
        if action == "claim":
            db.ticket_setzen(channel.id, self.settings, claimed_by=member.id)
            return await self.interaction_notice(interaction, "Ticket übernommen", f"Dieses Ticket wird jetzt von <@{member.id}> bearbeitet.")
        if action == "close":
            await interaction.response.defer(ephemeral=True)
            transcript = await self.make_transcript(channel)
            log_channel = guild.get_channel(int(cfg.get("log_channel_id") or 0))
            abgelegt = False
            if log_channel and transcript:
                try:
                    await log_channel.send(
                        view=layout("Ticket geschlossen", f"Ticket: {channel.name}\nGeschlossen von: <@{member.id}>\nNachrichten: {transcript[1]}", color="#ed4245"),
                        file=discord.File(io.BytesIO(transcript[0]), filename=f"transcript-{channel.id}.html"),
                    )
                    abgelegt = True
                except discord.HTTPException:
                    logger.warning("Transcript upload failed", exc_info=True)
            owner = guild.get_member(int(ticket["owner_id"]))
            if owner:
                try:
                    await channel.set_permissions(owner, send_messages=False, view_channel=True)
                except discord.HTTPException:
                    logger.warning("Could not lock ticket channel", exc_info=True)
            db.ticket_setzen(channel.id, self.settings, status="closed", closed_at=int(time.time()), closed_by=member.id)
            buttons = [discord.ui.Button(label=str(cfg.get("delete_label") or "Löschen")[:80], emoji=emoji(cfg.get("delete_emoji")), style=discord.ButtonStyle.danger, custom_id="shop:ticket:delete")]
            await self.send_layout(channel, "Ticket geschlossen",
                                   f"Geschlossen von <@{member.id}>. Transkript: {'abgelegt' if abgelegt else 'nicht abgelegt (Log-Kanal prüfen)'}",
                                   color="#ed4245", buttons=buttons)
            return await interaction.followup.send(view=layout("Ticket geschlossen", "Das Ticket wurde geschlossen."), ephemeral=True)
        if action == "delete":
            db.ticket_setzen(channel.id, self.settings, status="deleted")
            await self.interaction_notice(interaction, "Ticket wird gelöscht", "Der Kanal wird in wenigen Sekunden gelöscht.")
            await asyncio.sleep(3)
            try:
                await channel.delete(reason=f"LBoost Shop ticket deleted by {member}")
            except discord.HTTPException:
                logger.warning("Ticket channel delete failed", exc_info=True)

    async def make_transcript(self, channel: discord.TextChannel) -> tuple[bytes, int] | None:
        """HTML-Transkript plus Nachrichtenanzahl.

        Kein Limit mehr „2000 und Hoffen": lange Tickets wurden abgeschnitten,
        ohne dass jemand das merkte. Jetzt läuft die Paginierung durch und die
        Kopfzeile sagt, wie viele Nachrichten wirklich drin stehen.
        """
        zeilen = ["<!doctype html><meta charset='utf-8'><title>Transkript</title>",
                  "<style>body{font:14px system-ui;background:#101218;color:#eee;padding:24px}"
                  ".m{padding:10px;border-bottom:1px solid #2a2d36}.a{color:#8ea8ff;font-weight:bold}"
                  ".t{color:#777;font-size:11px}</style>"]
        anzahl = 0
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                anzahl += 1
                if anzahl > 10000:
                    zeilen.append("<p><i>Transkript nach 10000 Nachrichten beendet.</i></p>")
                    break
                anhaenge = " ".join(
                    f"<a href=\"{html.escape(a.url, quote=True)}\">{html.escape(a.filename)}</a>"
                    for a in message.attachments
                )
                text = html.escape(message.content or "")
                zeilen.append(
                    f"<div class='m'><span class='a'>{html.escape(str(message.author))}</span> "
                    f"<span class='t'>{message.created_at:%d.%m.%Y %H:%M}</span><br>{text}<br>{anhaenge}</div>"
                )
        except discord.HTTPException:
            logger.warning("Transcript failed for #%s", getattr(channel, "name", "?"), exc_info=True)
            if anzahl == 0:
                return None
        return "\n".join(zeilen).encode("utf-8"), anzahl

    async def toggle_role(self, interaction: discord.Interaction, role_id: int) -> None:
        role = interaction.guild.get_role(role_id)
        member = interaction.user
        if not role:
            return await self.interaction_notice(interaction, "Rolle fehlt", "Die Rolle existiert nicht mehr. Bitte das Panel neu senden.", error=True)
        if role >= interaction.guild.me.top_role or role.is_default() or role.managed:
            return await self.interaction_notice(interaction, "Rolle nicht verfügbar", "Diese Rolle darf der Bot nicht vergeben.", error=True)
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="LBoost Shop reaction role")
                await self.interaction_notice(interaction, "Rolle entfernt", f"Die Rolle {role.mention} wurde entfernt.")
            else:
                await member.add_roles(role, reason="LBoost Shop reaction role")
                await self.interaction_notice(interaction, "Rolle hinzugefügt", f"Die Rolle {role.mention} wurde hinzugefügt.")
        except discord.Forbidden:
            await self.interaction_notice(interaction, "Keine Berechtigung", "Der Bot steht mit seiner Rolle unter der Zielrolle.", error=True)

    async def enter_giveaway(self, interaction: discord.Interaction, message_id: int) -> None:
        cfg = self.feature(interaction.guild.id, "giveaways")
        required = int(cfg.get("required_role_id") or 0)
        if required and not any(role.id == required for role in interaction.user.roles):
            return await self.interaction_notice(interaction, "Rolle fehlt", f"Für dieses Giveaway brauchst du {interaction.guild.get_role(required).mention if interaction.guild.get_role(required) else 'eine Rolle'}.", error=True)
        ergebnis = db.giveaway_beitreten(message_id, interaction.user.id, self.settings)
        meldungen = {
            "unbekannt": ("Giveaway unbekannt", "Dieses Giveaway ist nicht mehr gespeichert.", True),
            "beendet": ("Giveaway beendet", "Dieses Giveaway nimmt keine Teilnehmer mehr an.", True),
            "bereits": ("Schon dabei", "Du nimmst bereits teil.", False),
            "beitritt": ("Teilnahme gespeichert", "Du nimmst jetzt an diesem Giveaway teil.", False),
        }
        titel, text, fehler = meldungen[ergebnis]
        await self.interaction_notice(interaction, titel, text, error=fehler)

    # ── Welcome / leave: shared University renderer ─────────────────
    def greet_values(self, member: discord.Member) -> dict[str, str]:
        guild = member.guild
        joined = getattr(member, "joined_at", None)
        created = getattr(member, "created_at", None)
        count = guild.member_count or len(guild.members)
        return {
            "user": member.mention, "user_name": member.name,
            "user_nick": member.display_name, "user_id": str(member.id),
            "user_avatar": str(member.display_avatar.url),
            "user_joindate": joined.strftime("%a, %b %d, %Y") if joined else "—",
            "user_createdate": created.strftime("%a, %b %d, %Y") if created else "—",
            "server_name": guild.name, "server_id": str(guild.id),
            "server_membercount": str(count),
            "server_icon": str(guild.icon.url) if guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png",
            "timestamp": discord.utils.format_dt(discord.utils.utcnow()),
            # Existing LBoost aliases remain valid during migration.
            "server": guild.name, "member_count": str(count), "count": str(count),
            "channel": "",
        }

    def greet_fill(self, value: Any, member: discord.Member) -> str:
        values = self.greet_values(member)
        return re.sub(r"\{(\w+)\}", lambda match: values.get(match.group(1).lower(), match.group(0)), str(value or ""))

    async def greet_banner(self, member: discord.Member, cfg: dict[str, Any], kind: str) -> discord.File | None:
        if not cfg.get(f"{kind}_image_enabled", True):
            return None
        background = b""
        url = str(cfg.get(f"{kind}_image_url") or "").strip()
        if url:
            try:
                timeout = aiohttp.ClientTimeout(total=6)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status == 200 and int(response.headers.get("Content-Length", "0") or 0) <= 8 * 1024 * 1024:
                            background = await response.content.read(8 * 1024 * 1024 + 1)
                            if len(background) > 8 * 1024 * 1024:
                                background = b""
            except Exception:
                background = b""
        avatar = b""
        try:
            avatar = await asyncio.wait_for(member.display_avatar.replace(size=256, format="png").read(), timeout=5)
        except Exception:
            pass
        try:
            from lbost_shop_bot import welcome_card
            count = member.guild.member_count or len(member.guild.members)
            buffer = await asyncio.to_thread(
                welcome_card.render, name=member.display_name, avatar_bytes=avatar or None,
                guild_name=member.guild.name, member_count=count,
                accent=member.guild.me.colour.value if member.guild.me and member.guild.me.colour.value else 0x3B82F6,
                background_bytes=background or None,
                label="WILLKOMMEN" if kind == "welcome" else "TSCHUESS",
                subtitle=None if kind == "welcome" else f"hat {member.guild.name} verlassen",
                counter_text=None if kind == "welcome" else f"Noch {count:,} Mitglieder".replace(",", "."),
            )
            return discord.File(buffer, filename="willkommen.png" if kind == "welcome" else "tschuess.png") if buffer else None
        except Exception:
            logger.warning("Could not render %s card", kind, exc_info=True)
            return None

    async def send_greeting(self, member: discord.Member, kind: str) -> None:
        cfg = self.feature(member.guild.id, "welcome")
        enabled = cfg.get("enabled") if kind == "welcome" else cfg.get("leave_enabled")
        if not enabled or (kind == "leave" and member.bot):
            return
        channel = member.guild.get_channel(int(cfg.get(f"{kind}_channel_id") or 0))
        if not isinstance(channel, discord.TextChannel):
            return
        banner = await self.greet_banner(member, cfg, kind)
        image = f"attachment://{banner.filename}" if banner else ""
        if kind == "welcome" and str(cfg.get("welcome_type") or "simple") == "embed":
            title = self.greet_fill(cfg.get("welcome_embed_title") or "Willkommen", member)
            sections = []
            above = self.greet_fill(cfg.get("welcome_embed_message"), member)
            if above: sections.append(above)
            author = self.greet_fill(cfg.get("welcome_embed_author_name"), member)
            if author: sections.append(f"**{author}**")
            description = self.greet_fill(cfg.get("welcome_embed_description"), member)
            if description: sections.append(description)
            footer = self.greet_fill(cfg.get("welcome_embed_footer_text"), member)
            text = "\n\n".join(sections) or self.greet_fill(cfg.get("welcome_message"), member)
            embed_image = self.greet_fill(cfg.get("welcome_embed_image"), member)
            thumbnail = self.greet_fill(cfg.get("welcome_embed_thumbnail") or cfg.get("welcome_embed_author_icon"), member)
            view = layout(title, text, color=cfg.get("color"), image_url=embed_image or image,
                          extra_image_url=image if image and embed_image else "", thumbnail_url=thumbnail, footer=footer)
        else:
            template = cfg.get(f"{kind}_message") or ("Willkommen {user} auf **{server_name}**!" if kind == "welcome" else "**{user_nick}** hat den Server verlassen.")
            view = layout("Willkommen" if kind == "welcome" else "Abschied", self.greet_fill(template, member),
                          color=cfg.get("color"), image_url=image)
        try:
            message = await channel.send(view=view, **({"file": banner} if banner else {}))
            duration = int(cfg.get(f"{kind}_auto_delete_duration") or 0)
            if duration:
                await message.delete(delay=duration)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send %s message in guild %s", kind, member.guild.id, exc_info=True)

    # ── Events and automation ───────────────────────────────────────
    async def on_member_join(self, member: discord.Member) -> None:
        await self.send_greeting(member, "welcome")
        await self.log_event(
            member.guild, "join_leave_events", "Member Joined",
            self.log_fields(
                ("User", member.mention),
                ("Account Created", discord.utils.format_dt(member.created_at, "R")),
                ("Member Count", str(member.guild.member_count)),
            ),
            user=member, footer=f"User ID: {member.id}",
        )

    async def on_member_remove(self, member: discord.Member) -> None:
        await self.send_greeting(member, "leave")
        fields = [
            ("User", f"{member.mention} ({member})"),
            ("Joined", discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown"),
            ("Member Count", str(member.guild.member_count)),
        ]
        if member.roles[1:]:
            fields.append(("Roles", ", ".join(role.mention for role in member.roles[1:][:10])))
        await self.log_event(
            member.guild, "join_leave_events", "Member Left", self.log_fields(*fields),
            user=member, footer=f"User ID: {member.id}",
        )

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        member = message.author
        # ``roles`` und ``guild_permissions`` hängen am Mitglied, nicht am
        # Nutzer-Objekt; über getattr läuft der Pfad auch, wenn das Mitglied
        # gerade erst geladen wurde, statt mit AttributeError zu sterben.
        rollen = list(getattr(member, "roles", None) or [])
        rechte = getattr(member, "guild_permissions", None)
        mod = self.feature(message.guild.id, "moderation")
        if mod.get("enabled"):
            exempt = bool(getattr(rechte, "manage_messages", False)) or any(r.id in ids(mod.get("exempt_role_ids")) for r in rollen)
            if not exempt:
                if mod.get("anti_links") and message.content:
                    erlaubnis = [x.strip().lower() for x in str(mod.get("allowed_domains") or "").split(",") if x.strip()]
                    domains = [urlparse(link).netloc.lower() for link in LINK_RE.findall(message.content)]
                    verboten = [d for d in domains if not any(d == eintrag or d.endswith("." + eintrag) for eintrag in erlaubnis)]
                    if verboten and await self.safe_delete(message, "anti-link"):
                        bestraft = await self.safe_timeout(member, int(mod.get("spam_timeout_minuten") or 5), "anti-link") if mod.get("link_timeout") else False
                        await self.log(message.guild, "AutoMod: Link",
                                       f"Nutzer: <@{member.id}>\nKanal: <#{message.channel.id}>\nDomains: {', '.join(verboten[:5])}\nTimeout: {'ja' if bestraft else 'nein'}", "moderation")
                        return
                if mod.get("anti_spam"):
                    loeschen = await self.sammle_spam(message, mod)
                    if loeschen:
                        await self.log(message.guild, "AutoMod: Spam",
                                       f"Nutzer: <@{member.id}>\nKanal: <#{message.channel.id}>\nGelöschte Nachrichten: {loeschen}", "moderation")
                        return
        automation = self.feature(message.guild.id, "automation")
        if automation.get("enabled") and message.content:
            content = message.content.strip()
            for item in automation.get("auto_responses_json") or []:
                if not isinstance(item, dict):
                    continue
                trigger = str(item.get("trigger") or "")
                match = content.casefold() == trigger.casefold() if item.get("exact") else trigger.casefold() in content.casefold()
                if trigger and match and await self.cooldown_frei(message, f"auto:{trigger}", int(item.get("cooldown_seconds") or 0)):
                    await self.send_layout(message.channel, str(item.get("title") or "Automatische Antwort"), str(item.get("response") or ""), color=item.get("color"))
                    break
            if content.startswith("!") and len(content) > 1:
                command = content[1:].split()[0].casefold()
                for item in automation.get("custom_commands_json") or []:
                    if isinstance(item, dict) and command == str(item.get("name") or "").casefold():
                        await self.send_layout(message.channel, str(item.get("title") or command), str(item.get("response") or ""), color=item.get("color"))
                        break
        # Overriding on_message disables prefix/hybrid commands unless the
        # command processor is called explicitly. Slash commands were working,
        # while University-style !warn / !ban silently did nothing.
        if isinstance(message, discord.Message):
            await self.process_commands(message)

    async def sammle_spam(self, message: discord.Message, mod: dict[str, Any]) -> int:
        """Spam-Eimer pro Nutzer und Kanal; gibt die Anzahl gelöschter Nachrichten zurück."""
        if not mod.get("anti_spam"):
            return 0
        jetzt = time.monotonic()
        schluessel = (message.guild.id, message.author.id, message.channel.id)
        eimer = self.spam[schluessel]
        while eimer and jetzt - eimer[0] > SPAM_FENSTER:
            eimer.popleft()
        eimer.append(jetzt)
        # Der Eintrag für die ausgelöste Nachricht wird mitgezählt.
        grenze = max(3, min(1000, int(mod.get("spam_limit") or 6)))
        if len(eimer) < grenze:
            if len(self.spam) > SPAM_MAX_EINTRAEGE:
                self.spam = {k: v for k, v in self.spam.items() if v and jetzt - v[-1] < SPAM_FENSTER * 2}
            return 0
        self.spam.pop(schluessel, None)
        geloescht = 0
        zu_loeschen = [message]
        try:
            async for aeltere in message.channel.history(limit=grenze, before=message):
                if aeltere.author.id != message.author.id:
                    continue
                if jetzt - aeltere.created_at.timestamp() > SPAM_FENSTER:
                    break
                zu_loeschen.append(aeltere)
        except discord.HTTPException:
            pass
        for nachricht in zu_loeschen:
            if await self.safe_delete(nachricht, "anti-spam"):
                geloescht += 1
        if mod.get("spam_timeout") and geloescht:
            await self.safe_timeout(message.author, int(mod.get("spam_timeout_minuten") or 5), "anti-spam")
        return geloescht

    async def cooldown_frei(self, message: discord.Message, schluessel: str, sekunden: int) -> bool:
        """Auto-Antworten nicht bei jeder Nachricht duplizieren."""
        if sekunden <= 0:
            return True
        selbst = f"{message.channel.id}:{schluessel}"
        state = self._cooldowns.get(selbst, 0)
        jetzt = time.monotonic()
        if jetzt - state < sekunden:
            return False
        self._cooldowns[selbst] = jetzt
        if len(self._cooldowns) > 5000:
            self._cooldowns = {k: v for k, v in self._cooldowns.items() if jetzt - v < max(60, sekunden)}
        return True

    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        fields = [
            ("Content", f"```{(message.content or 'No content')[:1000]}```"),
            ("Channel", message.channel.mention),
            ("User", message.author.mention),
        ]
        if message.attachments:
            fields.append(("Attachments", "\n".join(f"• {item.filename}" for item in message.attachments[:5])))
        await self.log_event(
            message.guild, "message_events", "Message Deleted", self.log_fields(*fields),
            channel_id=message.channel.id, user=message.author,
            footer=f"User ID: {message.author.id} • Message ID: {message.id}",
        )

    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return
        first = messages[0]
        entry = await self.audit_entry(first.guild, discord.AuditLogAction.message_bulk_delete)
        fields = [("Count", str(len(messages))), ("Channel", first.channel.mention)]
        if entry is not None and entry.user is not None:
            fields.append(("Deleted by", entry.user.mention))
        sample = [
            f"**{item.author.display_name}:** {(item.content or '')[:80]}"
            for item in messages[:5] if getattr(item, "content", None)
        ]
        if sample:
            fields.append(("First few", "\n".join(sample)[:1000]))
        await self.log_event(
            first.guild, "message_events", "Messages Purged", self.log_fields(*fields),
            channel_id=first.channel.id,
        )

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or before.content == after.content:
            return
        description = self.log_fields(
            ("Before", f"```{(before.content or 'No content')[:1000]}```"),
            ("After", f"```{(after.content or 'No content')[:1000]}```"),
            ("Channel", before.channel.mention),
            ("User", before.author.mention),
            ("Jump to Message", f"[Click here]({after.jump_url})"),
        )
        await self.log_event(
            before.guild, "message_events", "Message Edited", description,
            channel_id=before.channel.id, user=before.author,
            footer=f"User ID: {before.author.id} • Message ID: {before.id}",
        )

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        entry = await self.audit_entry(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        fields = [
            ("Channel", channel.mention),
            ("Type", str(channel.type).title()),
            ("Category", channel.category.name if channel.category else "None"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Created by", entry.user.mention))
        await self.log_event(
            channel.guild, "channel_events", "Channel Created", self.log_fields(*fields),
            channel_id=channel.id, footer=f"Channel ID: {channel.id}",
        )

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        entry = await self.audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        fields = [
            ("Channel", f"#{channel.name}"),
            ("Type", str(channel.type).title()),
            ("Category", channel.category.name if channel.category else "None"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Deleted by", entry.user.mention))
        await self.log_event(
            channel.guild, "channel_events", "Channel Deleted", self.log_fields(*fields),
            channel_id=channel.id, footer=f"Channel ID: {channel.id}",
        )

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"Topic: {getattr(before, 'topic', None) or 'None'} → {getattr(after, 'topic', None) or 'None'}")
        if before.category != after.category:
            changes.append(
                f"Category: {before.category.name if before.category else 'None'} → "
                f"{after.category.name if after.category else 'None'}"
            )
        if not changes:
            return
        entry = await self.audit_entry(after.guild, discord.AuditLogAction.channel_update, after.id)
        fields = [("Channel", after.mention), ("Changes", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Updated by", entry.user.mention))
        await self.log_event(
            after.guild, "channel_events", "Channel Updated", self.log_fields(*fields),
            channel_id=after.id, footer=f"Channel ID: {after.id}",
        )

    async def on_guild_role_create(self, role: discord.Role) -> None:
        entry = await self.audit_entry(role.guild, discord.AuditLogAction.role_create, role.id)
        fields = [
            ("Role", role.mention),
            ("Color", str(role.color)),
            ("Mentionable", "Yes" if role.mentionable else "No"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Created by", entry.user.mention))
        await self.log_event(
            role.guild, "role_events", "Role Created", self.log_fields(*fields),
            footer=f"Role ID: {role.id}",
        )

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        entry = await self.audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)
        fields = [
            ("Role", f"@{role.name}"),
            ("Color", str(role.color)),
            ("Members", str(len(role.members))),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Deleted by", entry.user.mention))
        await self.log_event(
            role.guild, "role_events", "Role Deleted", self.log_fields(*fields),
            footer=f"Role ID: {role.id}",
        )

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if before.color != after.color:
            changes.append(f"Color: {before.color} → {after.color}")
        if before.mentionable != after.mentionable:
            changes.append(f"Mentionable: {before.mentionable} → {after.mentionable}")
        if before.permissions != after.permissions:
            changes.append("Permissions updated")
        if not changes:
            return
        entry = await self.audit_entry(after.guild, discord.AuditLogAction.role_update, after.id)
        fields = [("Role", after.mention), ("Changes", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Updated by", entry.user.mention))
        await self.log_event(
            after.guild, "role_events", "Role Updated", self.log_fields(*fields),
            footer=f"Role ID: {after.id}",
        )

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles:
            added = set(after.roles) - set(before.roles)
            removed = set(before.roles) - set(after.roles)
            fields = [("User", after.mention)]
            if added:
                fields.append(("Roles Added", ", ".join(role.mention for role in added)))
            if removed:
                fields.append(("Roles Removed", ", ".join(role.mention for role in removed)))
            entry = await self.audit_entry(after.guild, discord.AuditLogAction.member_role_update, after.id)
            if entry is not None and entry.user is not None:
                fields.append(("Changed by", entry.user.mention))
            await self.log_event(
                after.guild, "role_events", "Member Roles Updated", self.log_fields(*fields),
                user=after, footer=f"User ID: {after.id}",
            )
        if before.nick != after.nick:
            await self.log_event(
                after.guild, "member_moderation", "Nickname Changed",
                self.log_fields(
                    ("User", after.mention),
                    ("Before", before.nick or "No nickname"),
                    ("After", after.nick or "No nickname"),
                ),
                user=after, footer=f"User ID: {after.id}",
            )

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        entry = await self.audit_entry(guild, discord.AuditLogAction.ban, user.id)
        fields = [("User", f"{user.mention} ({user})")]
        if entry is not None:
            if entry.user is not None:
                fields.append(("Banned by", entry.user.mention))
            if entry.reason:
                fields.append(("Reason", entry.reason[:1024]))
        await self.log_event(
            guild, "member_moderation", "Member Banned", self.log_fields(*fields),
            user=user, footer=f"User ID: {user.id}",
        )

    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        entry = await self.audit_entry(guild, discord.AuditLogAction.unban, user.id)
        fields = [("User", f"{user.mention} ({user})")]
        if entry is not None:
            if entry.user is not None:
                fields.append(("Unbanned by", entry.user.mention))
            if entry.reason:
                fields.append(("Reason", entry.reason[:1024]))
        await self.log_event(
            guild, "member_moderation", "Member Unbanned", self.log_fields(*fields),
            user=user, footer=f"User ID: {user.id}",
        )

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        fields = [("User", member.mention)]
        if before.channel and after.channel:
            fields.extend((("Action", "Moved channels"), ("From", before.channel.mention), ("To", after.channel.mention)))
        elif after.channel:
            fields.extend((("Action", "Joined voice"), ("Channel", after.channel.mention)))
        elif before.channel:
            fields.extend((("Action", "Left voice"), ("Channel", before.channel.mention)))
        await self.log_event(
            member.guild, "voice_events", "Voice State Changed", self.log_fields(*fields),
            user=member, footer=f"User ID: {member.id}",
        )

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if before.description != after.description:
            changes.append("Description updated")
        if before.verification_level != after.verification_level:
            changes.append(f"Verification Level: {before.verification_level} → {after.verification_level}")
        if not changes:
            return
        entry = await self.audit_entry(after, discord.AuditLogAction.guild_update)
        fields = [("Changes", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Updated by", entry.user.mention))
        await self.log_event(
            after, "system_events", "Server Updated", self.log_fields(*fields),
            footer=f"Guild ID: {after.id}",
        )

    async def on_guild_emojis_update(self, guild: discord.Guild, before: tuple[discord.Emoji, ...], after: tuple[discord.Emoji, ...]) -> None:
        for item in set(after) - set(before):
            entry = await self.audit_entry(guild, discord.AuditLogAction.emoji_create, item.id)
            fields = [
                ("Emoji", f"{item} :{item.name}:"),
                ("ID", str(item.id)),
                ("Animated", "Yes" if item.animated else "No"),
            ]
            if entry is not None and entry.user is not None:
                fields.append(("Created by", entry.user.mention))
            await self.log_event(
                guild, "emoji_events", "Emoji Added", self.log_fields(*fields),
                footer=f"Emoji ID: {item.id}",
            )
        for item in set(before) - set(after):
            entry = await self.audit_entry(guild, discord.AuditLogAction.emoji_delete, item.id)
            fields = [
                ("Emoji", f":{item.name}:"),
                ("ID", str(item.id)),
                ("Animated", "Yes" if item.animated else "No"),
            ]
            if entry is not None and entry.user is not None:
                fields.append(("Deleted by", entry.user.mention))
            await self.log_event(
                guild, "emoji_events", "Emoji Removed", self.log_fields(*fields),
                footer=f"Emoji ID: {item.id}",
            )

    async def on_thread_create(self, thread: discord.Thread) -> None:
        fields = [("Thread", thread.mention)]
        if thread.parent is not None:
            fields.append(("In", thread.parent.mention))
        if thread.owner is not None:
            fields.append(("By", thread.owner.mention))
        await self.log_event(
            thread.guild, "channel_events", "Thread Created", self.log_fields(*fields),
            channel_id=thread.parent_id, footer=f"Thread ID: {thread.id}",
        )

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        fields = [("Thread", f"#{thread.name}")]
        if thread.parent is not None:
            fields.append(("In", thread.parent.mention))
        await self.log_event(
            thread.guild, "channel_events", "Thread Deleted", self.log_fields(*fields),
            channel_id=thread.parent_id, footer=f"Thread ID: {thread.id}",
        )

    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None or not isinstance(invite.guild, discord.Guild):
            return
        fields = [("Code", f"`{invite.code}`")]
        if invite.inviter is not None:
            fields.append(("By", invite.inviter.mention))
        if invite.channel is not None:
            fields.append(("Channel", getattr(invite.channel, "mention", "?")))
        fields.extend((
            ("Expires", "never" if not invite.max_age else f"{invite.max_age}s"),
            ("Uses", "unlimited" if not invite.max_uses else str(invite.max_uses)),
        ))
        await self.log_event(invite.guild, "system_events", "Invite Created", self.log_fields(*fields))

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None or not isinstance(invite.guild, discord.Guild):
            return
        await self.log_event(
            invite.guild, "system_events", "Invite Deleted",
            self.log_fields(("Code", f"`{invite.code}`")),
        )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction_log(payload, added=True)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction_log(payload, added=False)

    async def _reaction_log(self, payload: discord.RawReactionActionEvent, *, added: bool) -> None:
        if payload.guild_id is None:
            return
        guild = self.get_guild(payload.guild_id)
        if guild is None:
            return
        user = payload.member or guild.get_member(payload.user_id)
        if user is None:
            try:
                user = await self.fetch_user(payload.user_id)
            except (discord.HTTPException, discord.NotFound):
                user = None
        if user is not None and getattr(user, "bot", False):
            return
        channel = guild.get_channel_or_thread(payload.channel_id)
        fields = [
            ("User", user.mention if user is not None else f"<@{payload.user_id}>"),
            ("Reaction", str(payload.emoji)),
            ("Message", f"[Jump to message](https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id})"),
        ]
        if channel is not None:
            fields.append(("Channel", channel.mention))
        await self.log_event(
            guild, "reaction_events", "Reaction Added" if added else "Reaction Removed",
            self.log_fields(*fields), channel_id=payload.channel_id, user=user,
            footer=f"User ID: {payload.user_id} • Message ID: {payload.message_id}",
        )

    @tasks.loop(seconds=30)
    async def giveaway_worker(self) -> None:
        now = int(time.time())
        for guild in self.guilds:
            cfg = self.feature(guild.id, "giveaways")
            if not cfg.get("enabled"):
                continue
            for zeile in db.giveaways_fuer_gilde(guild.id, self.settings, 25):
                if str(zeile["status"]) != "active" or int(zeile["ends_at"]) > now:
                    continue
                belegt = db.giveaway_belegen(int(zeile["message_id"]), self.settings)
                if not belegt:
                    continue
                await self.finish_giveaway(guild, belegt)

    @giveaway_worker.before_loop
    async def before_giveaways(self) -> None:
        await self.wait_until_ready()

    async def finish_giveaway(self, guild: discord.Guild, zeile: dict[str, Any]) -> None:
        channel = guild.get_channel(int(zeile["channel_id"]))
        teilnehmer = db.giveaway_teilnehmer(int(zeile["message_id"]), self.settings)
        # Wer den Server verlassen oder einen Bann bekommen hat, kann nicht
        # gewinnen; die alte Fassung erwähnte Leute, die gar nicht mehr da sind.
        tauglich = taugliche_teilnehmer(teilnehmer, {m.id for m in guild.members})
        anzahl = max(1, int(zeile["winners"] or 1))
        gewinner = random.sample(tauglich, min(len(tauglich), anzahl)) if tauglich else []
        db.giveaway_abschliessen(int(zeile["message_id"]), gewinner, self.settings)
        text = ("Gewinner: " + ", ".join(f"<@{uid}>" for uid in gewinner)) if gewinner else "Es gab keine gültigen Teilnehmer."
        if channel:
            await self.send_layout(channel, f"Giveaway beendet: {zeile['prize']}", text, color="#57f287")
        await self.log(guild, "Giveaway beendet", f"Preis: {zeile['prize']}\nGewinner: {len(gewinner)}", "giveaways")

    @tasks.loop(minutes=1)
    async def automation_worker(self) -> None:
        """Geplante Ankündigungen.

        Der nächste Lauf liegt in ``guild_state``, nicht mehr in der
        Benutzer-Konfiguration. Zuvor schrieb der Worker die gesamte
        Modul-Konfiguration zurück — fiel das mit einem Speichern im
        Dashboard zusammen, war die Änderung des Nutzers weg.
        """
        now = int(time.time())
        for guild in self.guilds:
            cfg = self.feature(guild.id, "automation")
            if not cfg.get("enabled"):
                continue
            eintraege = [item for item in (cfg.get("announcements_json") or []) if isinstance(item, dict)]
            if not eintraege:
                continue
            state_key = f"announce:{guild.id}"
            faellig = db.get_state(0, state_key, self.settings) or {"wert": {}, "updated_at": 0}
            zeitstempel = faellig["wert"] if isinstance(faellig["wert"], dict) else {}
            aktualisiert = False
            for index, item in enumerate(eintraege):
                schluessel = str(index)
                if int(zeitstempel.get(schluessel) or 0) > now:
                    continue
                channel = guild.get_channel(int(item.get("channel_id") or 0))
                if channel and item.get("content"):
                    await self.send_layout(channel, str(item.get("title") or "Ankündigung"), str(item["content"]), color=item.get("color"))
                zeitstempel[schluessel] = now + max(60, int(item.get("interval_minutes") or 60) * 60)
                aktualisiert = True
            if aktualisiert:
                db.set_state(0, state_key, zeitstempel, self.settings)

    @automation_worker.before_loop
    async def before_automation(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=20)
    async def heartbeat(self) -> None:
        """Dem Dashboard zeigen, dass der Bot lebt.

        Die Überschrift „Shop-Bot: Online“ war vorher hartgeschrieben — sie
        blieb auch dann grün, wenn der Bot-Prozess längst tot war.
        """
        self.write_heartbeat()

    @heartbeat.before_loop
    async def before_heartbeat(self) -> None:
        await self.wait_until_ready()

# ── Slash commands ─────────────────────────────────────────────────────
async def require_manage(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
        bot: ShopBot = interaction.client
        await bot.interaction_notice(interaction, "Keine Berechtigung", "Du benötigst die Berechtigung Server verwalten.", error=True)
        return False
    return True


def hat_mod_rechte(interaction: discord.Interaction, benoetigt: str) -> bool:
    recht = getattr(interaction.user.guild_permissions, benoetigt, False)
    return bool(recht)


def register_commands(bot: ShopBot) -> None:
    @bot.tree.command(name="log-setup", description="Richtet das vollständige Logging in einem Kanal ein")
    async def log_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        reaktionen: bool = False,
    ):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        cfg["enabled"] = True
        for category in LOG_CATEGORIES:
            if category == "reaction_events" and not reaktionen:
                cfg["log_enabled"][category] = False
                continue
            cfg["log_channels"][category] = str(channel.id)
            cfg["log_enabled"][category] = True
        db.set_feature(interaction.guild.id, "logging", cfg, interaction.user.id, bot.settings)
        bot.feature_cache.pop((interaction.guild.id, "logging"), None)
        count = len(LOG_CATEGORIES) if reaktionen else len(LOG_CATEGORIES) - 1
        await bot.interaction_notice(
            interaction,
            "Logging eingerichtet",
            f"{count} Kategorien schreiben jetzt in {channel.mention}. Reaktions-Logs: `{'an' if reaktionen else 'aus'}`.",
        )

    @bot.tree.command(name="log-status", description="Zeigt den Zustand aller Logging-Kategorien")
    async def log_status(interaction: discord.Interaction):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        lines = []
        for category in LOG_CATEGORIES:
            channel_id = int(cfg["log_channels"].get(category) or 0)
            channel = interaction.guild.get_channel(channel_id)
            state = "aktiv" if cfg["log_enabled"].get(category) and channel else "aus"
            lines.append(f"**{category.replace('_', ' ').title()}** — `{state}`" + (f" in {channel.mention}" if channel else ""))
        await bot.interaction_notice(interaction, "Logging-Status", "\n".join(lines))

    @bot.tree.command(name="log-test", description="Postet einen Testeintrag für eine Logging-Kategorie")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def log_test(interaction: discord.Interaction, category: app_commands.Choice[str]):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        channel_id = int(cfg["log_channels"].get(category.value) or 0)
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kein Log-Kanal", "Für diese Kategorie wurde kein gültiger Textkanal gewählt.", error=True)
        await interaction.response.defer(ephemeral=True)
        sent = await bot.send_layout(channel, "Testeintrag", f"Das Logging für **{category.name}** funktioniert.", color="#526dff")
        await interaction.followup.send(view=layout("Test abgeschlossen", f"Der Eintrag wurde in {channel.mention} gepostet." if sent else "Der Bot konnte dort nicht schreiben.", color="#3ba55d" if sent else "#ed4245"), ephemeral=True)

    @bot.tree.command(name="log-toggle", description="Schaltet eine Logging-Kategorie ein oder aus")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def log_toggle(interaction: discord.Interaction, category: app_commands.Choice[str], aktiviert: bool):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        cfg["enabled"] = True
        cfg["log_enabled"][category.value] = aktiviert
        db.set_feature(interaction.guild.id, "logging", cfg, interaction.user.id, bot.settings)
        bot.feature_cache.pop((interaction.guild.id, "logging"), None)
        await bot.interaction_notice(interaction, "Kategorie geändert", f"**{category.name}** ist jetzt `{'aktiv' if aktiviert else 'aus'}`.")

    @bot.tree.command(name="log-ignore", description="Verwaltet ignorierte Kanäle, Rollen und Nutzer")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Kanal", value="channel"),
        app_commands.Choice(name="Rolle", value="role"),
        app_commands.Choice(name="Nutzer", value="user"),
    ])
    async def log_ignore(
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        discord_id: str,
        entfernen: bool = False,
    ):
        if not await require_manage(interaction):
            return
        if not discord_id.isdigit():
            return await bot.interaction_notice(interaction, "Ungültige ID", "Gib eine numerische Discord-ID an.", error=True)
        cfg = bot.logging_config(interaction.guild.id)
        field = {"channel": "ignore_channels", "role": "ignore_roles", "user": "ignore_users"}[kind.value]
        values = set(cfg[field])
        value = int(discord_id)
        if entfernen:
            values.discard(value)
        else:
            values.add(value)
        cfg[field] = sorted(values)
        db.set_feature(interaction.guild.id, "logging", cfg, interaction.user.id, bot.settings)
        bot.feature_cache.pop((interaction.guild.id, "logging"), None)
        await bot.interaction_notice(interaction, "Ausnahmen aktualisiert", f"Die {kind.name}-ID `{discord_id}` wurde {'entfernt' if entfernen else 'hinzugefügt'}.")

    @bot.tree.command(name="log-search", description="Durchsucht die gespeicherten Discord-Ereignisse")
    async def log_search(
        interaction: discord.Interaction,
        suche: str = "",
        tage: app_commands.Range[int, 1, 30] = 7,
    ):
        if not await require_manage(interaction):
            return
        rows = db.search_event_logs(
            interaction.guild.id,
            bot.settings,
            query=suche,
            since=int(time.time()) - tage * 86400,
            limit=20,
        )
        if not rows:
            return await bot.interaction_notice(interaction, "Keine Treffer", "Für diese Suche wurden keine gespeicherten Ereignisse gefunden.")
        lines = [f"<t:{row['created_at']}:R> **{row['title']}** — {row['description'].replace(chr(10), ' ')[:160]}" for row in rows]
        await bot.interaction_notice(interaction, f"Log-Suche · {len(rows)} Treffer", "\n".join(lines)[:3800])

    @bot.tree.command(name="log-export", description="Exportiert gespeicherte Discord-Ereignisse als Textdatei")
    async def log_export(interaction: discord.Interaction, tage: app_commands.Range[int, 1, 30] = 7):
        if not await require_manage(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        rows = db.search_event_logs(
            interaction.guild.id,
            bot.settings,
            since=int(time.time()) - tage * 86400,
            limit=1000,
        )
        content = "\n\n".join(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(row['created_at']))} UTC] {row['category']} | {row['title']}\n{row['description']}"
            for row in reversed(rows)
        ) or "Keine Ereignisse im gewählten Zeitraum."
        await interaction.followup.send(
            view=layout("Log-Export", f"{len(rows)} Ereignisse aus den letzten {tage} Tagen."),
            file=discord.File(io.BytesIO(content.encode("utf-8")), filename=f"lbost-logs-{interaction.guild.id}-{tage}d.txt"),
            ephemeral=True,
        )

    @bot.tree.command(name="log-reset", description="Setzt die vollständige Logging-Konfiguration zurück")
    async def log_reset(interaction: discord.Interaction):
        if not await require_manage(interaction):
            return
        empty = {
            "enabled": False,
            "log_channels": {},
            "log_enabled": {key: False for key in LOG_CATEGORIES},
            "ignore_channels": [],
            "ignore_roles": [],
            "ignore_users": [],
            "auto_delete_duration": 0,
        }
        db.set_feature(interaction.guild.id, "logging", empty, interaction.user.id, bot.settings)
        bot.feature_cache.pop((interaction.guild.id, "logging"), None)
        await bot.interaction_notice(interaction, "Logging zurückgesetzt", "Alle Kanäle, Schalter und Ausnahmen wurden entfernt. Das Ereignisarchiv bleibt erhalten.")

    # University exposes logging as one `/log` command group.  The old
    # hyphenated commands stay registered for existing LBoost servers, while
    # these aliases provide the same command structure and behaviour.
    log_group = app_commands.Group(name="log", description="Vollständiges Server-Logging verwalten")

    @log_group.command(name="setup", description="Richtet das vollständige Logging in einem Kanal ein")
    async def grouped_log_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        reaktionen: bool = False,
    ):
        await log_setup.callback(interaction, channel, reaktionen)

    @log_group.command(name="status", description="Zeigt den Zustand aller Logging-Kategorien")
    async def grouped_log_status(interaction: discord.Interaction):
        await log_status.callback(interaction)

    @log_group.command(name="config", description="Zeigt die vollständige Logging-Konfiguration")
    async def grouped_log_config(interaction: discord.Interaction):
        await log_status.callback(interaction)

    @log_group.command(name="test", description="Sendet Testeinträge an konfigurierte Kanäle")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def grouped_log_test(
        interaction: discord.Interaction,
        category: app_commands.Choice[str] | None = None,
    ):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        categories = [category.value] if category else list(LOG_CATEGORIES)
        await interaction.response.defer(ephemeral=True)
        sent = 0
        for key in categories:
            if not cfg["log_enabled"].get(key) or not cfg["log_channels"].get(key):
                continue
            await bot.log_event(
                interaction.guild,
                key,
                f"Test Log - {key.replace('_', ' ').title()}",
                bot.log_fields(
                    ("Category", key),
                    ("Test User", interaction.user.mention),
                    ("Timestamp", discord.utils.format_dt(discord.utils.utcnow(), "f")),
                ),
                channel_id=interaction.channel_id,
                user=interaction.user,
                footer=f"Test message • User ID: {interaction.user.id}",
            )
            sent += 1
        await interaction.followup.send(
            view=layout(
                "Test Messages Sent" if sent else "No Test Messages Sent",
                f"Sent {sent} test log messages to configured channels."
                if sent else "No logging categories are enabled or configured.",
            ),
            ephemeral=True,
        )

    @log_group.command(name="toggle", description="Schaltet eine Logging-Kategorie ein oder aus")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def grouped_log_toggle(
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        aktiviert: bool,
    ):
        await log_toggle.callback(interaction, category, aktiviert)

    @log_group.command(name="ignore", description="Verwaltet ignorierte Kanäle, Rollen und Nutzer")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Kanal", value="channel"),
        app_commands.Choice(name="Rolle", value="role"),
        app_commands.Choice(name="Nutzer", value="user"),
    ])
    async def grouped_log_ignore(
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        discord_id: str,
        entfernen: bool = False,
    ):
        await log_ignore.callback(interaction, kind, discord_id, entfernen)

    @log_group.command(name="search", description="Durchsucht die gespeicherten Discord-Ereignisse")
    async def grouped_log_search(
        interaction: discord.Interaction,
        suche: str = "",
        tage: app_commands.Range[int, 1, 30] = 7,
    ):
        await log_search.callback(interaction, suche, tage)

    @log_group.command(name="export", description="Exportiert gespeicherte Discord-Ereignisse als Textdatei")
    async def grouped_log_export(
        interaction: discord.Interaction,
        tage: app_commands.Range[int, 1, 30] = 7,
    ):
        await log_export.callback(interaction, tage)

    @log_group.command(name="reset", description="Setzt die vollständige Logging-Konfiguration zurück")
    async def grouped_log_reset(interaction: discord.Interaction):
        await log_reset.callback(interaction)

    bot.tree.add_command(log_group)

    @bot.tree.command(name="ticket-panel", description="Sendet ein konfiguriertes Ticket-Panel")
    @app_commands.describe(panel="Panel-Key aus der Dashboard-Konfiguration")
    async def ticket_panel_command(interaction: discord.Interaction, panel: str = "default"):
        if not await require_manage(interaction):
            return
        cfg = bot.ticket_panel(interaction.guild.id, panel)
        if not cfg.get("enabled"):
            return await bot.interaction_notice(interaction, "Tickets deaktiviert", "Aktiviere das Modul zuerst im Dashboard.", error=True)
        channel = interaction.guild.get_channel(int(cfg.get("panel_channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanal fehlt", "Wähle im Dashboard einen gültigen Textkanal.", error=True)
        button = discord.ui.Button(
            label=str(cfg.get("button_label") or "Ticket öffnen")[:80],
            emoji=emoji(cfg.get("button_emoji")),
            style=discord.ButtonStyle.primary,
            custom_id=f"shop:ticket:create:{panel}"[:100],
        )
        message = await bot.send_layout(
            channel,
            regeln.PANEL_TITEL if not cfg.get("title") else str(cfg.get("title"))[:256],
            (regeln.PANEL_BESCHREIBUNG if not cfg.get("description") else str(cfg.get("description")))[:3900],
            color=cfg.get("color"),
            buttons=[button],
            image_url=str(cfg.get("image_url") or ""),
            thumbnail_url=str(cfg.get("thumbnail_url") or ""),
            footer=str(cfg.get("footer") or ""),
        )
        await bot.interaction_notice(
            interaction, "Panel gesendet",
            f"Das Ticket-Panel wurde in <#{channel.id}> veröffentlicht." if message else "Panel konnte nicht gesendet werden.",
            error=not bool(message),
        )

    @bot.tree.command(name="reaction-panel", description="Sendet ein konfiguriertes Rollen-Panel")
    @app_commands.describe(panel="Index des Panels, beginnend mit 0")
    async def reaction_panel_command(interaction: discord.Interaction, panel: int = 0):
        if not await require_manage(interaction):
            return
        cfg = bot.feature(interaction.guild.id, "reaction_roles")
        panels = [{**cfg, "roles_json": cfg.get("roles_json") or []}] + [p for p in (cfg.get("panels_json") or []) if isinstance(p, dict)]
        selected = panels[panel] if 0 <= panel < len(panels) else None
        if not cfg.get("enabled") or not selected:
            return await bot.interaction_notice(interaction, "Panel nicht verfügbar", "Prüfe die Dashboard-Konfiguration.", error=True)
        channel = interaction.guild.get_channel(int(selected.get("channel_id") or cfg.get("channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanal fehlt", "Wähle im Dashboard einen gültigen Textkanal.", error=True)
        buttons = []
        for item in selected.get("roles_json", [])[:25]:
            if not isinstance(item, dict) or not str(item.get("role_id", "")).isdigit():
                continue
            ziel = interaction.guild.get_role(int(item["role_id"]))
            buttons.append(discord.ui.Button(
                label=str(item.get("label") or (ziel.name if ziel else "Rolle"))[:80],
                emoji=emoji(item.get("emoji")),
                style=discord.ButtonStyle.secondary,
                custom_id=f"shop:role:{int(item['role_id'])}",
            ))
        if not buttons:
            return await bot.interaction_notice(interaction, "Keine Buttons", "Das Panel hat keine gültigen Rollen-Einträge.", error=True)
        sent = await bot.send_layout(channel, str(selected.get("title") or "Rollen auswählen"), str(selected.get("description") or "Wähle deine Rollen über die Buttons."), color=selected.get("color"), buttons=buttons)
        await bot.interaction_notice(interaction, "Panel gesendet", f"Das Rollen-Panel wurde in <#{channel.id}> veröffentlicht." if sent else "Panel konnte nicht gesendet werden.", error=not bool(sent))

    async def mod_zugriff(interaction: discord.Interaction, recht: str, modul: str = "Moderation") -> bool:
        if modul == "Moderation" and not bot.feature(interaction.guild.id, "moderation").get("enabled"):
            await bot.interaction_notice(interaction, "Moderation deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
            return False
        if not hat_mod_rechte(interaction, recht):
            await bot.interaction_notice(interaction, "Keine Berechtigung", f"Dir fehlt die Discord-Berechtigung „{recht.replace('_', ' ')}“.", error=True)
            return False
        return True

    # The complete hybrid University moderation suite is registered below.

    @bot.tree.command(name="giveaway", description="Startet ein Giveaway")
    @app_commands.describe(minuten="Laufzeit", gewinner="Anzahl Gewinner", preis="Was wird verlost")
    async def giveaway(interaction: discord.Interaction, minuten: app_commands.Range[int, 1, 525600],
                       gewinner: app_commands.Range[int, 1, 20], preis: str):
        if not await require_manage(interaction):
            return
        cfg = bot.feature(interaction.guild.id, "giveaways")
        if not cfg.get("enabled"):
            return await bot.interaction_notice(interaction, "Giveaways deaktiviert", "Aktiviere das Modul im Dashboard.", error=True)
        await interaction.response.defer(ephemeral=True)
        ends = int(time.time()) + minuten * 60
        text = f"Endet: <t:{ends}:R>\nGewinner: {gewinner}\nTeilnahme über den Knopf."
        knopf = discord.ui.Button(label="Teilnehmen", style=discord.ButtonStyle.success, custom_id="shop:giveaway:0")
        nachricht = await interaction.channel.send(view=layout(preis[:200], text, color="#57f287", buttons=[knopf]))
        db.giveaway_anlegen(nachricht.id, interaction.guild.id, interaction.channel.id, preis, gewinner, ends, bot.settings,
                            int(cfg.get("required_role_id") or 0))
        # Der Knopf braucht die endgültige Nachrichten-ID, also einmal nachziehen.
        endgueltig = discord.ui.Button(label="Teilnehmen", style=discord.ButtonStyle.success, custom_id=f"shop:giveaway:{nachricht.id}")
        await nachricht.edit(view=layout(preis[:200], text, color="#57f287", buttons=[endgueltig]))
        await interaction.followup.send(view=layout("Giveaway gestartet", f"Nachricht: `{nachricht.id}`"), ephemeral=True)

    @bot.tree.command(name="giveaway-reroll", description="Zieht Gewinner eines Giveaways neu")
    async def giveaway_reroll(interaction: discord.Interaction, nachrichten_id: str):
        if not await require_manage(interaction):
            return
        if not nachrichten_id.isdigit():
            return await bot.interaction_notice(interaction, "Ungültige ID", "Gib eine gültige Nachrichten-ID an.", error=True)
        row = next((g for g in db.giveaways_fuer_gilde(interaction.guild.id, bot.settings, 100) if int(g["message_id"]) == int(nachrichten_id)), None)
        teilnehmer = db.giveaway_teilnehmer(int(nachrichten_id), bot.settings) if row else []
        tauglich = taugliche_teilnehmer(teilnehmer, {m.id for m in interaction.guild.members})
        if not row or not tauglich:
            return await bot.interaction_notice(interaction, "Nicht möglich", "Giveaway oder Teilnehmer wurden nicht gefunden.", error=True)
        gewinner = random.sample(tauglich, min(len(tauglich), max(1, int(row["winners"]))))
        await bot.send_layout(interaction.channel, f"Giveaway neu gezogen: {row['prize']}", "Gewinner: " + ", ".join(f"<@{x}>" for x in gewinner), color="#57f287")
        await bot.interaction_notice(interaction, "Neu gezogen", f"{len(gewinner)} Gewinner ermittelt ({len(tauglich)} Teilnehmer).")

    @bot.tree.command(name="announce", description="Sendet eine Components-V2-Ankündigung")
    async def announce(interaction: discord.Interaction, kanal: discord.TextChannel, titel: str, text: str):
        if not await require_manage(interaction):
            return
        sent = await bot.send_layout(kanal, titel[:256], text[:3900])
        await bot.interaction_notice(interaction, "Ankündigung gesendet", f"Gesendet in {kanal.mention}." if sent else "Senden fehlgeschlagen.", error=not bool(sent))

    @bot.tree.error
    async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error("Slash command failed: %s", error, exc_info=(type(error), error, error.__traceback__))
        try:
            await bot.interaction_notice(interaction, "Befehl fehlgeschlagen", "Der Befehl konnte nicht sicher ausgeführt werden. Prüfe Rollen und Bot-Berechtigungen.", error=True)
        except discord.HTTPException:
            pass


    # Separate module keeps the complete University-compatible moderation
    # command surface isolated from tickets/logging.
    from lbost_shop_bot.moderation import register_moderation
    from lbost_shop_bot.reaction_roles import register_reaction_roles
    register_moderation(bot)
    register_reaction_roles(bot)


def create_bot(*, privileged_intents: bool = True) -> ShopBot:
    settings = get_settings()
    db.init_features(settings)
    bot = ShopBot(settings, privileged_intents=privileged_intents)
    register_commands(bot)
    return bot
