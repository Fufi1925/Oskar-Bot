"""Configurable, isolated Discord bot used by LBoost Shop.

The configuration source is the shop dashboard's SQLite database. Discord
messages use Components V2 layouts; component custom IDs are handled globally
so tickets, role panels and giveaways continue working after restarts.

Text rules (placeholders, question filtering, channel naming) live in
``lbost_shop_app.regeln`` so the dashboard preview and this bot calculate the
same output — the same split CloudTIX uses.
"""
from __future__ import annotations

import asyncio
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
from lbost_shop_app import giveaways as giveaway_store
from lbost_shop_app import automation as automation_store
from lbost_shop_app.config import Settings, get_settings
from lbost_shop_bot.custom_commands import CustomCommandsService

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

    def __init__(self, bot: "ShopBot", panel_key: str, category_key: str, fragen: list[dict[str, Any]]):
        super().__init__(title="Ticket aanmaken", timeout=300)
        self.bot = bot
        self.panel_key = panel_key
        self.category_key = category_key
        self.fragen = fragen
        self.eingaben: list[tuple[str, str, Any]] = []
        for frage in fragen[:regeln.MAX_TICKET_QUESTIONS]:
            label = str(frage.get("label") or "Vraag")[:regeln.MAX_FRAGE_LABEL]
            typ = str(frage.get("type") or "short")
            pflicht = bool(frage.get("required", True))
            if typ == "image":
                feld = discord.ui.FileUpload(required=pflicht, min_values=1 if pflicht else 0, max_values=1)
                self.eingaben.append((label, "image", feld))
                self.add_item(discord.ui.Label(
                    text=label,
                    description=str(frage.get("placeholder") or "Afbeelding uploaden")[:regeln.MAX_FRAGE_HINWEIS],
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
        await self.bot.create_ticket(interaction, self.panel_key, self.category_key, antworten=antworten)


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
        self.custom_commands_service = CustomCommandsService(self)

    def feature(self, guild_id: int, name: str) -> dict[str, Any]:
        key, now = (guild_id, name), time.monotonic()
        cached = self.feature_cache.get(key)
        if cached and now - cached[0] < 3:
            return cached[1]
        value = db.get_feature(guild_id, name, self.settings)
        if name in {"tickets", "moderation", "welcome", "reaction_roles", "giveaways", "custom_commands", "automation", "logging"} and "enabled" not in value:
            value["enabled"] = True
        self.feature_cache[key] = (now, value)
        if len(self.feature_cache) > 4000:  # Server, die niemand mehr sieht, rauswerfen
            self.feature_cache = {k: v for k, v in self.feature_cache.items() if now - v[0] < 30}
        return value

    async def setup_hook(self) -> None:
        db.init_features(self.settings)
        db.prune_audit(self.settings)
        automation_store.ensure_schema(self.settings)
        self.giveaway_worker.start()
        self.automation_worker.start()
        self.ticket_notify_worker.start()
        self.heartbeat.start()
        await self.custom_commands_service.start()
        await self.tree.sync()

    async def on_ready(self) -> None:
        mode = "complete" if self.privileged_intents else "online (bevoorrechte intenties uitgeschakeld in Developer Portal)"
        logger.info("Verbonden als %s (%s), %s gilden; functieruntime %s", self.user, self.user.id if self.user else "?", len(self.guilds), mode)
        # Import the old JSON automations exactly once without deleting their
        # source configuration, then use only the dedicated tables.
        for guild in self.guilds:
            automation_store.migrate_legacy(self.settings,guild.id,self.feature(guild.id,"automation"))
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
            logger.warning("Kon het Components V2-bericht niet verzenden", exc_info=True)
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
            logger.warning("Loggen mislukt voor gilde=%s categorie=%s", guild.id, category)

    async def log(self, guild: discord.Guild, title: str, description: str, feature: str = "logging") -> None:
        """Module-specific logs stay isolated; Discord events use log_event."""
        if feature == "logging":
            await self.log_event(guild, "system_events", title, description)
            return
        cfg = self.feature(guild.id, feature)
        channel_id = int(cfg.get("channel_id") or cfg.get("log_channel_id") or 0)
        channel = guild.get_channel(channel_id)
        if not channel and feature == "tickets":
            try:
                channel = await guild.create_text_channel(
                    (re.sub(r"[^a-z0-9-]+", "-", self.settings.brand_name.lower()).strip("-") + "-ticket-logs")[:90] or "ticket-logs",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="LBoost Shop-ticketregistratie",
                )
                cfg["log_channel_id"] = str(channel.id)
                db.set_feature(guild.id, "tickets", cfg, 0, self.settings, audit=False)
                self.feature_cache.pop((guild.id, "tickets"), None)
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                channel = None
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
            logger.warning("Kan de interactie niet beantwoorden", exc_info=True)

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
            logger.warning("Bericht verwijderen mislukt (%s)", grund, exc_info=True)
        return False

    async def safe_timeout(self, member: discord.Member, minuten: int, grund: str) -> bool:
        try:
            await member.timeout(timedelta(minutes=minuten), reason=f"LBoost Shop: {grund}")
            return True
        except discord.Forbidden:
            logger.info("Ontbrekende machtigingen voor time-out %s (%s)", member, grund)
        except discord.HTTPException:
            logger.warning("Time-out mislukt voor %s (%s)", member, grund, exc_info=True)
        return False

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or not interaction.guild:
            return
        custom_id = str((interaction.data or {}).get("custom_id") or "")
        try:
            if custom_id.startswith("shop:ticket:create:"):
                value = custom_id.removeprefix("shop:ticket:create:")
                panel_key, _, category_key = value.partition("~")
                await self.start_ticket(interaction, panel_key, category_key)
            elif custom_id.startswith("shop:ticket:select:"):
                panel_key = custom_id.removeprefix("shop:ticket:select:")
                values = list((interaction.data or {}).get("values") or [])
                if values:
                    await self.start_ticket(interaction, panel_key, str(values[0]))
            elif custom_id.startswith("shop:ticket:"):
                await self.ticket_action(interaction, custom_id.rsplit(":", 1)[-1])
            elif custom_id.startswith("shop:role:"):
                await self.toggle_role(interaction, int(custom_id.rsplit(":", 1)[-1]))
            elif custom_id.startswith("shop:giveaway:"):
                await self.enter_giveaway(interaction, int(custom_id.rsplit(":", 1)[-1]))
            elif custom_id.startswith("giveaway_join_"):
                await self.enter_giveaway(interaction, int(custom_id.rsplit("_", 1)[-1]))
        except Exception:
            logger.exception("Component mislukt: %s", custom_id)
            await self.interaction_notice(interaction, "Actie fehlgeschlagen", "De actie kan niet langer worden uitgevoerd.", error=True)

    # ── University reaction roles ───────────────────────────────────
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == (self.user.id if self.user else 0):
            return
        if not self.feature(payload.guild_id, "reaction_roles").get("enabled", True):
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
            await member.add_roles(role, reason="LBoost-reactierol toegevoegd")
            if db.reaktionsrollen_dm(guild.id, self.settings):
                try:
                    await member.send(view=layout("Rol erhalten", f"Je hebt op **{guild.name}** de rol **{role.name}** erhalten."))
                except (discord.Forbidden, discord.HTTPException):
                    pass
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Kan reactierol %s niet toevoegen aan gilde %s", role.id, guild.id)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == (self.user.id if self.user else 0):
            return
        if not self.feature(payload.guild_id, "reaction_roles").get("enabled", True):
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
            await member.remove_roles(role, reason="LBoost-reactierol verwijderd")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Kan reactierol %s in gilde %s niet verwijderen", role.id, guild.id)

    # ── Tickets ──────────────────────────────────────────────────────
    def ticket_panel(self, guild_id: int, key: str, category_key: str = "") -> dict[str, Any]:
        cfg = self.feature(guild_id, "tickets")
        panels = cfg.get("panels_json") or []
        selected: dict[str, Any] = next(
            (p for p in panels if isinstance(p, dict) and str(p.get("key")) == key), {}
        )
        merged = {**cfg, **selected}
        if category_key:
            category = next(
                (item for item in (merged.get("categories") or [])
                 if isinstance(item, dict) and str(item.get("key")) == category_key),
                {},
            )
            merged = {**merged, **category, "selected_category_key": category_key}
        return merged

    async def start_ticket(self, interaction: discord.Interaction, panel_key: str, category_key: str = "") -> None:
        """Knopfdruck: erst das Fragen-Modal, sonst direkt das Ticket.

        Das Modal muss die *erste* Antwort auf die Interaktion sein — wer
        vorher ``defer`` aufruft, kann kein Modal mehr senden und der Knopf
        wirkt kaputt.
        """
        cfg = self.ticket_panel(interaction.guild.id, panel_key, category_key)
        fragen = regeln.fragen_bereinigen(cfg.get("questions_json"))
        if category_key:
            fragen = [frage for frage in fragen if not frage.get("category_keys") or category_key in frage.get("category_keys", [])]
        if fragen:
            await interaction.response.send_modal(TicketFragenModal(self, panel_key, category_key, fragen))
            return
        await interaction.response.defer(ephemeral=True)
        await self.create_ticket(interaction, panel_key, category_key)

    async def create_ticket(self, interaction: discord.Interaction, panel_key: str,
                            category_key: str = "", antworten: list[dict[str, Any]] | None = None) -> None:
        guild = interaction.guild
        member = interaction.user
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        cfg = self.ticket_panel(guild.id, panel_key, category_key)
        if not cfg.get("enabled", self.feature(guild.id, "tickets").get("enabled")):
            return await self.interaction_notice(interaction, "Kaartjes uitgeschakeld", "Dit ticketpaneel is niet actief.", error=True)
        offene_rollen = ids(cfg.get("open_role_ids"))
        if offene_rollen and not any(role.id in offene_rollen for role in member.roles):
            return await self.interaction_notice(interaction, "Geen toestemming", "U heeft geen rol die dit ticket kan openen.", error=True)
        vorhandene = [
            channel_id for channel_id in db.offene_ticket_kanale(guild.id, member.id, self.settings)
            if guild.get_channel(channel_id)
        ]
        maximum = max(1, min(10, int(cfg.get("max_open_tickets") or 1)))
        if len(vorhandene) >= maximum:
            links = ", ".join(f"<#{channel_id}>" for channel_id in vorhandene[:5])
            return await self.interaction_notice(
                interaction, "Ticketlimiet bereikt",
                f"Du hast bereits {len(vorhandene)} von {maximum} Tickets offen: {links}.", error=True,
            )

        kategorie = guild.get_channel(int(cfg.get("category_id") or 0))
        support_ids = ids(cfg.get("support_role_ids")) | ids(cfg.get("staff_role_ids"))
        support_rollen = [guild.get_role(role_id) for role_id in support_ids]
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
            return await self.interaction_notice(interaction, "Geen rechten", "De bot mag geen kanalen in deze categorie maken. Controleer de rolmachtigingen.", error=True)
        except discord.HTTPException as fehler:
            return await self.interaction_notice(interaction, "Ticket niet mogelijk", f"Discord heeft het kanaal geweigerd: {getattr(fehler, 'text', 'onbekende fout')}", error=True)

        stored_panel_key = f"{panel_key}~{category_key}" if category_key else panel_key
        db.ticket_anlegen(guild.id, channel.id, member.id, stored_panel_key, nummer, antworten or [], self.settings)
        worte = regeln.ersetzungen(
            ticket_number=f"{nummer:04d}",
            user=f"<@{member.id}>",
            category=str(cfg.get("name") or (kategorie.name if isinstance(kategorie, discord.CategoryChannel) else "Ondersteuning")),
            server=guild.name,
            channel=f"#{channel.name}",
        )
        texte = regeln.ticket_texte(cfg, worte, antworten=antworten)
        titel = texte["titel"]
        text = texte["nachricht"]
        action_emoji = emoji(cfg.get("emoji") or cfg.get("button_emoji"))
        buttons = [
            discord.ui.Button(label=str(cfg.get("claim_label") or "Overnemen")[:80], emoji=emoji(cfg.get("claim_emoji")) or action_emoji, style=discord.ButtonStyle.primary, custom_id="shop:ticket:claim"),
            discord.ui.Button(label="Niet geclaimd", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:unclaim"),
            discord.ui.Button(label="Vergrendelen", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:lock"),
            discord.ui.Button(label="Ontgrendelen", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:unlock"),
            discord.ui.Button(label=str(cfg.get("close_label") or "Sluiten")[:80], emoji=emoji(cfg.get("close_emoji")) or action_emoji, style=discord.ButtonStyle.danger, custom_id="shop:ticket:close"),
        ]
        await self.send_layout(channel, titel, text, color=cfg.get("color"), buttons=buttons,
                               image_url=str(cfg.get("ticket_image_url") or ""),
                               thumbnail_url=str(cfg.get("ticket_thumbnail_url") or ""))

        bestaetigung = texte["bestaetigung"]
        await interaction.followup.send(view=layout("Ticket aangemaakt", bestaetigung, color="#3ba55d"), ephemeral=True)
        if support_rollen and cfg.get("mention_support", True):
            erwahnung = " ".join(role.mention for role in filter(None, support_rollen))
            if erwahnung:
                await self.send_layout(channel, "Ondersteuning gevraagd", f"{erwahnung} — er is een nieuw ticket geopend.", color="#5865f2")
        await self.log(guild, "Ticket aangemaakt", f"Kanaal: <#{channel.id}>\nGebruiker: <@{member.id}>\nNummer: `#{nummer:04d}`", "tickets")

    def can_manage_ticket(self, member: discord.Member, cfg: dict[str, Any]) -> bool:
        allowed = ids(cfg.get("support_role_ids")) | ids(cfg.get("staff_role_ids"))
        return member.guild_permissions.manage_channels or any(role.id in allowed for role in member.roles)

    async def ticket_action(self, interaction: discord.Interaction, action: str) -> None:
        guild, channel, member = interaction.guild, interaction.channel, interaction.user
        ticket = db.ticket_fuer_kanal(channel.id, self.settings)
        if not ticket:
            return await self.interaction_notice(interaction, "Geen kaartje", "Dit kanaal is geen actief ticket.", error=True)
        stored_key = str(ticket["panel_key"])
        panel_key, _, category_key = stored_key.partition("~")
        cfg = self.ticket_panel(guild.id, panel_key, category_key)
        if not self.can_manage_ticket(member, cfg):
            return await self.interaction_notice(interaction, "Geen toestemming", "U mag dit ticket niet beheren.", error=True)
        if action == "claim":
            if ticket.get("claimed_by"):
                return await self.interaction_notice(interaction, "Al aangenomen", f"Dit ticket wordt al behandeld door <@{ticket['claimed_by']}> bearbeitet.", error=True)
            db.ticket_setzen(channel.id, self.settings, claimed_by=member.id)
            await self.log(guild, "Ticket geaccepteerd", f"Kanaal: <#{channel.id}>\nTeamlid: <@{member.id}>", "tickets")
            return await self.interaction_notice(interaction, "Ticket geaccepteerd", f"Dit ticket wordt nu behandeld door <@{member.id}> bearbeitet.")
        if action == "unclaim":
            if not ticket.get("claimed_by"):
                return await self.interaction_notice(interaction, "Niet aangenomen", "Dit ticket is momenteel aan niemand toegewezen.", error=True)
            db.ticket_setzen(channel.id, self.settings, claimed_by=None)
            await self.log(guild, "Kaartje vrijgegeven", f"Kanaal: <#{channel.id}>\nTeamlid: <@{member.id}>", "tickets")
            return await self.interaction_notice(interaction, "Kaartje vrijgegeven", f"Vrijgegeven door <@{member.id}>.")
        if action in {"lock", "unlock"}:
            owner = guild.get_member(int(ticket["owner_id"]))
            locked = action == "lock"
            if owner:
                try:
                    await channel.set_permissions(owner, view_channel=True, send_messages=not locked)
                except discord.HTTPException:
                    return await self.interaction_notice(interaction, "Discord-fout", "De ticketrechten konden niet worden gewijzigd.", error=True)
            db.ticket_setzen(channel.id, self.settings, is_locked=1 if locked else 0)
            await self.log(guild, "Ticket geblokkeerd" if locked else "Ticket ontgrendeld", f"Kanaal: <#{channel.id}>\nTeamlid: <@{member.id}>", "tickets")
            return await self.interaction_notice(interaction, "Ticket vergrendeld" if locked else "Ticket ontgrendeld", f"Changed by <@{member.id}>.")
        if action == "reopen":
            await interaction.response.defer(ephemeral=True)
            owner = guild.get_member(int(ticket["owner_id"]))
            if owner:
                await channel.set_permissions(owner, view_channel=True, send_messages=True)
            category = guild.get_channel(int(cfg.get("category_id") or 0))
            if isinstance(category, discord.CategoryChannel):
                await channel.edit(category=category)
            db.ticket_setzen(channel.id, self.settings, status="open", closed_at=None, closed_by=None, is_locked=0, claimed_by=None, notify_sleep=0)
            action_emoji = emoji(cfg.get("emoji") or cfg.get("button_emoji"))
            buttons = [
                discord.ui.Button(label="Overnemen", emoji=action_emoji, style=discord.ButtonStyle.primary, custom_id="shop:ticket:claim"),
                discord.ui.Button(label="Niet geclaimd", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:unclaim"),
                discord.ui.Button(label="Vergrendelen", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:lock"),
                discord.ui.Button(label="Ontgrendelen", emoji=action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:unlock"),
                discord.ui.Button(label="Sluiten", emoji=action_emoji, style=discord.ButtonStyle.danger, custom_id="shop:ticket:close"),
            ]
            await self.send_layout(channel, "Kaartje heropend", f"Heropend door <@{member.id}>.", color="#3ba55d", buttons=buttons)
            await self.log(guild, "Kaartje heropend", f"Kanaal: <#{channel.id}>\nTeamlid: <@{member.id}>", "tickets")
            return await interaction.followup.send(view=layout("Kaartje heropend", "Het kaartje is weer open.", color="#3ba55d"), ephemeral=True)
        if action == "close":
            await interaction.response.defer(ephemeral=True)
            owner = guild.get_member(int(ticket["owner_id"]))
            if owner:
                try:
                    await channel.set_permissions(owner, send_messages=False, view_channel=False)
                except discord.HTTPException:
                    logger.warning("Kan ticketkanaal niet vergrendelen", exc_info=True)
            archive = guild.get_channel(int(cfg.get("closed_category_id") or 0))
            if not isinstance(archive, discord.CategoryChannel):
                try:
                    archive = await guild.create_category(
                        "Gesloten kaartjes",
                        overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                        reason="LBoost Shop ticketarchief",
                    )
                    server_cfg = self.feature(guild.id, "tickets")
                    server_cfg["closed_category_id"] = str(archive.id)
                    db.set_feature(guild.id, "tickets", server_cfg, 0, self.settings, audit=False)
                    self.feature_cache.pop((guild.id, "tickets"), None)
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    archive = None
            if isinstance(archive, discord.CategoryChannel):
                try:
                    await channel.edit(category=archive)
                except discord.HTTPException:
                    pass
            db.ticket_setzen(channel.id, self.settings, status="closed", closed_at=int(time.time()), closed_by=member.id)
            action_emoji = emoji(cfg.get("emoji") or cfg.get("button_emoji"))
            buttons = [
                discord.ui.Button(label="Heropenen", emoji=action_emoji, style=discord.ButtonStyle.success, custom_id="shop:ticket:reopen"),
                discord.ui.Button(label=str(cfg.get("delete_label") or "Delete")[:80], emoji=emoji(cfg.get("delete_emoji")) or action_emoji, style=discord.ButtonStyle.danger, custom_id="shop:ticket:delete"),
            ]
            await self.send_layout(channel, "Kaartjes gesloten",
                                   f"Closed by <@{member.id}>. The ticket creator was removed.",
                                   color="#ed4245", buttons=buttons)
            await self.log(guild, "Kaartje gesloten", f"Kanaal: <#{channel.id}>\nGesloten door: <@{member.id}>", "tickets")
            return await interaction.followup.send(view=layout("Kaartjes gesloten", "Het ticket is gearchiveerd."), ephemeral=True)
        if action == "delete":
            action_emoji = emoji(cfg.get("emoji") or cfg.get("button_emoji"))
            yes = discord.ui.Button(label="Ja", emoji=action_emoji, style=discord.ButtonStyle.success, custom_id="shop:ticket:delete_yes")
            no = discord.ui.Button(label="No", emoji=emoji(cfg.get("delete_emoji")) or action_emoji, style=discord.ButtonStyle.secondary, custom_id="shop:ticket:delete_no")
            return await interaction.response.send_message(
                view=layout(
                    "Tickettranscript opslaan?",
                    "Wil je het privétranscriptie naar **jij** en de **ticketmaker** sturen voordat dit kanaal wordt verwijderd?\n\nVoor de link is een Discord-login vereist en deze verloopt na **90 dagen**.",
                    color="#5865f2", buttons=[yes, no],
                ), ephemeral=True,
            )
        if action in {"delete_yes", "delete_no"}:
            await interaction.response.defer(ephemeral=True)
            wants_dm = action == "delete_yes"
            always_log = bool(cfg.get("always_transcript"))
            link = f"{self.settings.base_url.rstrip('/')}/Tickets/Transkript/{channel.id}"
            if wants_dm or always_log:
                messages = await self.transcript_messages(channel)
                db.transcript_speichern(
                    channel.id, guild.id, guild.name, channel.name, int(ticket["owner_id"]),
                    member.id, str(ticket["panel_key"]), messages, self.settings,
                )
                open_button = discord.ui.Button(label="Afschrift openen", style=discord.ButtonStyle.link, url=link)
                transcript_view = layout(
                    "Tickettranscript",
                    f"**Ticket:** #{channel.name}\n**Server:** {guild.name}\n\nDit privétranscript blijft **90 dagen** beschikbaar. Log in met Discord om het te bekijken.",
                    color=cfg.get("color"), buttons=[open_button],
                )
                if always_log:
                    log_channel = guild.get_channel(int(cfg.get("log_channel_id") or 0))
                    if log_channel:
                        try:
                            await log_channel.send(view=transcript_view)
                        except discord.HTTPException:
                            pass
                if wants_dm:
                    recipients = [member]
                    owner = guild.get_member(int(ticket["owner_id"]))
                    if owner and owner.id != member.id:
                        recipients.append(owner)
                    for recipient in recipients:
                        try:
                            await recipient.send(view=layout(
                                "Tickettranscript",
                                f"**Ticket:** #{channel.name}\n**Server:** {guild.name}\n\nDit privétranscript blijft **90 dagen** beschikbaar. Log in met Discord om het te bekijken.",
                                color=cfg.get("color"), buttons=[discord.ui.Button(label="Afschrift openen", style=discord.ButtonStyle.link, url=link)],
                            ))
                        except Exception:
                            pass
            db.ticket_setzen(channel.id, self.settings, status="deleted", notify_sleep=1)
            await self.log(guild, "Ticketverwijdering gepland", f"Kanaal: <#{channel.id}>\nTeamlid: <@{member.id}>\nTranscript: {'ja' if wants_dm or always_log else 'nee'}", "tickets")
            await interaction.followup.send(view=layout("Verwijdering van kaartjes", "Het kanaal wordt binnen enkele seconden verwijderd.", color="#ed4245"), ephemeral=True)
            await asyncio.sleep(3)
            try:
                await channel.delete(reason=f"LBoost Shop ticket deleted by {member}")
            except discord.HTTPException:
                logger.warning("Ticket channel delete failed", exc_info=True)

    async def transcript_messages(self, channel: discord.TextChannel) -> list[dict[str, Any]]:
        """Store the complete ordered Discord message shape for the private web archive."""
        messages: list[dict[str, Any]] = []
        async for message in channel.history(limit=None, oldest_first=True):
            embeds = []
            for item in getattr(message, "embeds", []):
                try:
                    embeds.append(item.to_dict())
                except Exception:
                    pass
            components = []
            for item in getattr(message, "components", []):
                try:
                    components.append(item.to_dict())
                except Exception:
                    pass
            messages.append({
                "id": str(message.id), "content": getattr(message, "clean_content", message.content) or "",
                "raw_content": message.content or "", "created_at": message.created_at.isoformat(),
                "edited_at": getattr(message, "edited_at", None).isoformat() if getattr(message, "edited_at", None) else None,
                "author": {
                    "id": str(message.author.id), "display_name": str(getattr(message.author, "display_name", None) or getattr(message.author, "global_name", None) or getattr(message.author, "name", message.author)),
                    "username": str(message.author), "avatar_url": str(getattr(getattr(message.author, "display_avatar", None), "url", "")),
                    "bot": bool(message.author.bot),
                },
                "attachments": [{
                    "id": str(item.id), "filename": item.filename, "url": item.url,
                    "proxy_url": item.proxy_url, "content_type": item.content_type,
                    "size": item.size,
                } for item in getattr(message, "attachments", [])],
                "embeds": embeds, "components": components,
                "reactions": [{"emoji": str(item.emoji), "count": item.count} for item in getattr(message, "reactions", [])],
                "stickers": [{"name": item.name, "url": str(item.url)} for item in getattr(message, "stickers", [])],
            })
        return messages

    async def toggle_role(self, interaction: discord.Interaction, role_id: int) -> None:
        if not self.feature(interaction.guild.id, "reaction_roles").get("enabled", True):
            return await self.interaction_notice(interaction, "Module uitgeschakeld", "Reactierollen zijn uitgeschakeld op deze server.", error=True)
        role = interaction.guild.get_role(role_id)
        member = interaction.user
        if not role:
            return await self.interaction_notice(interaction, "Rol ontbreekt", "De rol bestaat niet meer. Stuur het paneel opnieuw.", error=True)
        if role >= interaction.guild.me.top_role or role.is_default() or role.managed:
            return await self.interaction_notice(interaction, "Rol niet beschikbaar", "De bot mag deze rol niet toewijzen.", error=True)
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="LBoost Shop-reactierol")
                await self.interaction_notice(interaction, "Rol verwijderd", f"De rol {role.mention} is verwijderd.")
            else:
                await member.add_roles(role, reason="LBoost Shop-reactierol")
                await self.interaction_notice(interaction, "Rol toegevoegd", f"De rol {role.mention} is toegevoegd.")
        except discord.Forbidden:
            await self.interaction_notice(interaction, "Geen toestemming", "De rol van de bot ligt onder de doelrol.", error=True)

    def giveaway_view(self, record: dict[str, Any], entries: int, *, ended: bool = False, winners: str = ""):
        values = giveaway_store.values(record, entries)
        title = giveaway_store.fill(record.get("title") or giveaway_store.DEFAULT_TITLE, values)
        body = giveaway_store.fill(record.get("description") or giveaway_store.DEFAULT_DESCRIPTION, values)
        rules = giveaway_store.requirement_lines(record)
        if rules and not ended:
            body += "\n\n**Voorwaarden:**" + " · ".join(rules)
        body += (f"\n\n**Gewonnen:** {winners}" if winners else "\n\nNiemand nam deel.") if ended else f"\n\n**Deelnemers:** {entries}"
        buttons = []
        if not ended:
            try: emoji = record.get("button_emoji") or None
            except Exception: emoji = None
            buttons.append(discord.ui.Button(label=(record.get("button_label") or "Doe mee")[:80], emoji=emoji, style=discord.ButtonStyle.success, custom_id=f"giveaway_join_{record['message_id']}"))
        return layout(title[:256], body[:3900], color=f"#{int(record.get('colour') or 0xF59E0B):06x}", buttons=buttons, image_url=str(record.get("image_url") or ""))

    async def enter_giveaway(self, interaction: discord.Interaction, message_id: int) -> None:
        if not self.feature(interaction.guild.id, "giveaways").get("enabled", True):
            return await self.interaction_notice(interaction, "Module uitgeschakeld", "Giveaways zijn uitgeschakeld op deze server.", error=True)
        record = giveaway_store.get(interaction.guild.id, message_id, self.settings)
        if not record or record.get("status") != "active" or int(record.get("ends_at") or 0) <= int(time.time()):
            text = giveaway_store.message(record or {}, "msg_ended", giveaway_store.values(record or {}))
            return await self.interaction_notice(interaction, "De winactie is afgelopen", text, error=True)
        failed = giveaway_store.failed_requirements(record, interaction.user, self.settings)
        if failed:
            text = giveaway_store.message(record, "msg_denied", giveaway_store.values(record)) + "\n" + "\n".join(f"• {item}" for item in failed)
            return await self.interaction_notice(interaction, "Deelname niet mogelijk", text, error=True)
        result, total = giveaway_store.toggle_entry(message_id, interaction.user.id, bool(record.get("allow_leave", 1)), self.settings)
        data = giveaway_store.values(record, total)
        if result == "already": title, text = "Ben er al", giveaway_store.message(record, "msg_joined", data)
        elif result == "left": title, text = "Deelname beëindigd", giveaway_store.message(record, "msg_left", data)
        else: title, text = "Deelname opgeslagen", giveaway_store.message(record, "msg_joined", data)
        await self.interaction_notice(interaction, title, text)
        try:
            message = interaction.message or await interaction.channel.fetch_message(message_id)
            await message.edit(view=self.giveaway_view(record, total))
        except Exception:
            pass

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
                label="WELKOM" if kind == "welcome" else "TSCHUESS",
                subtitle=None if kind == "welcome" else f"hat {member.guild.name} verlassen",
                counter_text=None if kind == "welcome" else f"Noch {count:,} Mitglieder".replace(",", "."),
            )
            return discord.File(buffer, filename="willkommen.png" if kind == "welcome" else "tschuess.png") if buffer else None
        except Exception:
            logger.warning("Kon %s kaart niet weergeven", kind, exc_info=True)
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
            title = self.greet_fill(cfg.get("welcome_embed_title") or "Welkom", member)
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
            template = cfg.get(f"{kind}_message") or ("Welkom {user} bij **{server_name}**!" if kind == "welcome" else "**{user_nick}** heeft de server verlaten.")
            view = layout("Welkom" if kind == "welcome" else "Vaarwel", self.greet_fill(template, member),
                          color=cfg.get("color"), image_url=image)
        try:
            message = await channel.send(view=view, **({"file": banner} if banner else {}))
            duration = int(cfg.get(f"{kind}_auto_delete_duration") or 0)
            if duration:
                await message.delete(delay=duration)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Kan %s bericht niet verzenden naar gilde %s", kind, member.guild.id, exc_info=True)

    # ── Events and automation ───────────────────────────────────────
    async def on_member_join(self, member: discord.Member) -> None:
        await self.send_greeting(member, "welcome")
        await self.log_event(
            member.guild, "join_leave_events", "Lid is lid geworden",
            self.log_fields(
                ("gebruikers", member.mention),
                ("Account aangemaakt", discord.utils.format_dt(member.created_at, "R")),
                ("Aantal leden", str(member.guild.member_count)),
            ),
            user=member, footer=f"Gebruikers-ID: {member.id}",
        )

    async def on_member_remove(self, member: discord.Member) -> None:
        await self.send_greeting(member, "leave")
        fields = [
            ("gebruikers", f"{member.mention} ({member})"),
            ("Aangesloten", discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Onbekend"),
            ("Aantal leden", str(member.guild.member_count)),
        ]
        if member.roles[1:]:
            fields.append(("Rollen", ", ".join(role.mention for role in member.roles[1:][:10])))
        await self.log_event(
            member.guild, "join_leave_events", "Lid links", self.log_fields(*fields),
            user=member, footer=f"Gebruikers-ID: {member.id}",
        )

    async def record_ticket_activity(self, message: discord.Message) -> None:
        ticket = db.ticket_fuer_kanal(message.channel.id, self.settings)
        if not ticket or ticket.get("status") != "open":
            return
        now = int(time.time())
        stored = str(ticket.get("panel_key") or "")
        panel_key, _, category_key = stored.partition("~")
        cfg = self.ticket_panel(message.guild.id, panel_key, category_key)
        is_owner = message.author.id == int(ticket["owner_id"])
        is_staff = self.can_manage_ticket(message.author, cfg)
        command = (message.content or "").strip().casefold()
        if is_staff and command in {">sleep", ">wake"}:
            sleeping = command == ">sleep"
            db.ticket_setzen(message.channel.id, self.settings, notify_sleep=1 if sleeping else 0)
            await self.send_layout(
                message.channel,
                "Ticketmeldingen zijn onderbroken" if sleeping else "Ticketmeldingen zijn hervat",
                "Voor dit ticket worden geen herinnerings-DM's verzonden." if sleeping else "Herinnerings-DM's zijn weer actief.",
                color="#5865f2",
            )
            return
        if is_owner:
            db.ticket_setzen(message.channel.id, self.settings, last_owner_message=now)
        elif is_staff:
            db.ticket_setzen(message.channel.id, self.settings, last_staff_message=now, last_staff_id=message.author.id)

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        giveaway_store.add_activity(message.guild.id, message.author.id, self.settings)
        await self.record_ticket_activity(message)
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
                        await self.log(message.guild, "AutoMod: koppeling",
                                       f"Nutzer: <@{member.id}>\nKanaal: <#{message.channel.id}>\nDomains: {', '.join(verboten[:5])}\nTimeout: {'ja' if bestraft else 'nein'}", "moderation")
                        return
                if mod.get("anti_spam"):
                    loeschen = await self.sammle_spam(message, mod)
                    if loeschen:
                        await self.log(message.guild, "AutoMod: Spam",
                                       f"Nutzer: <@{member.id}>\nKanaal: <#{message.channel.id}>\nVerwijderde berichten: {loeschen}", "moderation")
                        return
        automation = self.feature(message.guild.id, "automation")
        if automation.get("enabled") and message.content:
            # Also covers the first message after an offline migration or test
            # harness where on_ready has not run yet. The migration is idempotent.
            automation_store.migrate_legacy(self.settings,message.guild.id,automation)
            content = message.content.strip()
            for item in automation_store.responses(self.settings,message.guild.id):
                trigger=str(item.get("trigger") or "")
                match=content.casefold()==trigger.casefold() if item.get("exact") else trigger.casefold() in content.casefold()
                if trigger and match and await self.cooldown_frei(message,f"auto-response:{item['id']}",int(item.get("cooldown_seconds") or 0)):
                    values={"user":getattr(message.author,"mention",f"<@{message.author.id}>"),"user_name":getattr(message.author,"display_name",getattr(message.author,"name",str(message.author))),"server":message.guild.name,"channel":getattr(message.channel,"mention",f"<#{message.channel.id}>"),"member_count":getattr(message.guild,"member_count",0) or len(getattr(message.guild,"members",[])),"date":datetime.now().strftime("%d.%m.%Y"),"time":datetime.now().strftime("%H:%M")}
                    title=str(item.get("title") or "Automatisch Antwort");text=str(item.get("response") or "")
                    for key,value in values.items():title=title.replace("{"+key+"}",str(value));text=text.replace("{"+key+"}",str(value))
                    await message.channel.send(view=layout(title,text,color=item.get("color"),image_url=item.get("image_url") or ""))
                    break
        # The dedicated University-style service handles prefix, slash, exact
        # and contains triggers with the complete flow/action system.
        await self.custom_commands_service.handle_message(message)
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
            ("Inhoud", f"```{(message.content or 'Geen inhoud')[:1000]}```"),
            ("Kanaal", message.channel.mention),
            ("gebruikers", message.author.mention),
        ]
        if message.attachments:
            fields.append(("Bijlagen", "\n".join(f"• {item.filename}" for item in message.attachments[:5])))
        await self.log_event(
            message.guild, "message_events", "Bericht verwijderd", self.log_fields(*fields),
            channel_id=message.channel.id, user=message.author,
            footer=f"Gebruikers-ID: {message.author.id} • Bericht-ID: {message.id}",
        )

    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return
        first = messages[0]
        entry = await self.audit_entry(first.guild, discord.AuditLogAction.message_bulk_delete)
        fields = [("Tel", str(len(messages))), ("Kanaal", first.channel.mention)]
        if entry is not None and entry.user is not None:
            fields.append(("Verwijderd door", entry.user.mention))
        sample = [
            f"**{item.author.display_name}:** {(item.content or '')[:80]}"
            for item in messages[:5] if getattr(item, "content", None)
        ]
        if sample:
            fields.append(("Eerste paar", "\n".join(sample)[:1000]))
        await self.log_event(
            first.guild, "message_events", "Berichten gewist", self.log_fields(*fields),
            channel_id=first.channel.id,
        )

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or before.content == after.content:
            return
        description = self.log_fields(
            ("Voor", f"```{(before.content or 'Geen inhoud')[:1000]}```"),
            ("Na", f"```{(after.content or 'Geen inhoud')[:1000]}```"),
            ("Kanaal", before.channel.mention),
            ("gebruikers", before.author.mention),
            ("Ga naar bericht", f"[Click here]({after.jump_url})"),
        )
        await self.log_event(
            before.guild, "message_events", "Bericht bewerkt", description,
            channel_id=before.channel.id, user=before.author,
            footer=f"Gebruikers-ID: {before.author.id} • Bericht-ID: {before.id}",
        )

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        entry = await self.audit_entry(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        fields = [
            ("Kanaal", channel.mention),
            ("Typ", str(channel.type).title()),
            ("Categorie", channel.category.name if channel.category else "Geen"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Gemaakt door", entry.user.mention))
        await self.log_event(
            channel.guild, "channel_events", "Kanaal gemaakt", self.log_fields(*fields),
            channel_id=channel.id, footer=f"Kanaal-ID: {channel.id}",
        )

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        entry = await self.audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        fields = [
            ("Kanaal", f"#{channel.name}"),
            ("Typ", str(channel.type).title()),
            ("Categorie", channel.category.name if channel.category else "Geen"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Verwijderd door", entry.user.mention))
        await self.log_event(
            channel.guild, "channel_events", "Kanaal verwijderd", self.log_fields(*fields),
            channel_id=channel.id, footer=f"Kanaal-ID: {channel.id}",
        )

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"Topic: {getattr(before, 'topic', None) or 'Geen'} → {getattr(after, 'topic', None) or 'Geen'}")
        if before.category != after.category:
            changes.append(
                f"Category: {before.category.name if before.category else 'Geen'} → "
                f"{after.category.name if after.category else 'Geen'}"
            )
        if not changes:
            return
        entry = await self.audit_entry(after.guild, discord.AuditLogAction.channel_update, after.id)
        fields = [("Kanaal", after.mention), ("Veranderingen", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Bijgewerkt door", entry.user.mention))
        await self.log_event(
            after.guild, "channel_events", "Kanaal bijgewerkt", self.log_fields(*fields),
            channel_id=after.id, footer=f"Kanaal-ID: {after.id}",
        )

    async def on_guild_role_create(self, role: discord.Role) -> None:
        entry = await self.audit_entry(role.guild, discord.AuditLogAction.role_create, role.id)
        fields = [
            ("Rol", role.mention),
            ("Kleur", str(role.color)),
            ("Vermeldbaar", "Ja" if role.mentionable else "No"),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Gemaakt door", entry.user.mention))
        await self.log_event(
            role.guild, "role_events", "Rol gemaakt", self.log_fields(*fields),
            footer=f"Role ID: {role.id}",
        )

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        entry = await self.audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)
        fields = [
            ("Rol", f"@{role.name}"),
            ("Kleur", str(role.color)),
            ("Leden", str(len(role.members))),
        ]
        if entry is not None and entry.user is not None:
            fields.append(("Verwijderd door", entry.user.mention))
        await self.log_event(
            role.guild, "role_events", "Rol verwijderd", self.log_fields(*fields),
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
            changes.append("Machtigingen bijgewerkt")
        if not changes:
            return
        entry = await self.audit_entry(after.guild, discord.AuditLogAction.role_update, after.id)
        fields = [("Rol", after.mention), ("Veranderingen", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Bijgewerkt door", entry.user.mention))
        await self.log_event(
            after.guild, "role_events", "Rol bijgewerkt", self.log_fields(*fields),
            footer=f"Role ID: {after.id}",
        )

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles:
            added = set(after.roles) - set(before.roles)
            removed = set(before.roles) - set(after.roles)
            fields = [("gebruikers", after.mention)]
            if added:
                fields.append(("Rollen toegevoegd", ", ".join(role.mention for role in added)))
            if removed:
                fields.append(("Rollen verwijderd", ", ".join(role.mention for role in removed)))
            entry = await self.audit_entry(after.guild, discord.AuditLogAction.member_role_update, after.id)
            if entry is not None and entry.user is not None:
                fields.append(("Gewijzigd door", entry.user.mention))
            await self.log_event(
                after.guild, "role_events", "Ledenrollen bijgewerkt", self.log_fields(*fields),
                user=after, footer=f"Gebruikers-ID: {after.id}",
            )
        if before.nick != after.nick:
            await self.log_event(
                after.guild, "member_moderation", "Bijnaam gewijzigd",
                self.log_fields(
                    ("gebruikers", after.mention),
                    ("Voor", before.nick or "Geen bijnaam"),
                    ("Na", after.nick or "Geen bijnaam"),
                ),
                user=after, footer=f"Gebruikers-ID: {after.id}",
            )

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        entry = await self.audit_entry(guild, discord.AuditLogAction.ban, user.id)
        fields = [("gebruikers", f"{user.mention} ({user})")]
        if entry is not None:
            if entry.user is not None:
                fields.append(("Verboden door", entry.user.mention))
            if entry.reason:
                fields.append(("Reden", entry.reason[:1024]))
        await self.log_event(
            guild, "member_moderation", "Lid verbannen", self.log_fields(*fields),
            user=user, footer=f"Gebruikers-ID: {user.id}",
        )

    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        entry = await self.audit_entry(guild, discord.AuditLogAction.unban, user.id)
        fields = [("gebruikers", f"{user.mention} ({user})")]
        if entry is not None:
            if entry.user is not None:
                fields.append(("Opgeheven door", entry.user.mention))
            if entry.reason:
                fields.append(("Reden", entry.reason[:1024]))
        await self.log_event(
            guild, "member_moderation", "Lid opgeheven", self.log_fields(*fields),
            user=user, footer=f"Gebruikers-ID: {user.id}",
        )

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        fields = [("gebruikers", member.mention)]
        if before.channel and after.channel:
            fields.extend((("Actie", "Verplaatste kanalen"), ("Van", before.channel.mention), ("Naar", after.channel.mention)))
        elif after.channel:
            fields.extend((("Actie", "Spraakkanaal betreden"), ("Kanaal", after.channel.mention)))
        elif before.channel:
            fields.extend((("Actie", "Spraakkanaal verlaten"), ("Kanaal", before.channel.mention)))
        await self.log_event(
            member.guild, "voice_events", "Stemstatus gewijzigd", self.log_fields(*fields),
            user=member, footer=f"Gebruikers-ID: {member.id}",
        )

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if before.description != after.description:
            changes.append("Beschrijving bijgewerkt")
        if before.verification_level != after.verification_level:
            changes.append(f"Verification Level: {before.verification_level} → {after.verification_level}")
        if not changes:
            return
        entry = await self.audit_entry(after, discord.AuditLogAction.guild_update)
        fields = [("Veranderingen", "\n".join(changes))]
        if entry is not None and entry.user is not None:
            fields.append(("Bijgewerkt door", entry.user.mention))
        await self.log_event(
            after, "system_events", "Server bijgewerkt", self.log_fields(*fields),
            footer=f"Guild ID: {after.id}",
        )

    async def on_guild_emojis_update(self, guild: discord.Guild, before: tuple[discord.Emoji, ...], after: tuple[discord.Emoji, ...]) -> None:
        for item in set(after) - set(before):
            entry = await self.audit_entry(guild, discord.AuditLogAction.emoji_create, item.id)
            fields = [
                ("Emoji", f"{item} :{item.name}:"),
                ("ID", str(item.id)),
                ("Geanimeerd", "Ja" if item.animated else "No"),
            ]
            if entry is not None and entry.user is not None:
                fields.append(("Gemaakt door", entry.user.mention))
            await self.log_event(
                guild, "emoji_events", "Emoji toegevoegd", self.log_fields(*fields),
                footer=f"Emoji ID: {item.id}",
            )
        for item in set(before) - set(after):
            entry = await self.audit_entry(guild, discord.AuditLogAction.emoji_delete, item.id)
            fields = [
                ("Emoji", f":{item.name}:"),
                ("ID", str(item.id)),
                ("Geanimeerd", "Ja" if item.animated else "No"),
            ]
            if entry is not None and entry.user is not None:
                fields.append(("Verwijderd door", entry.user.mention))
            await self.log_event(
                guild, "emoji_events", "Emoji verwijderd", self.log_fields(*fields),
                footer=f"Emoji ID: {item.id}",
            )

    async def on_thread_create(self, thread: discord.Thread) -> None:
        fields = [("Draad", thread.mention)]
        if thread.parent is not None:
            fields.append(("In", thread.parent.mention))
        if thread.owner is not None:
            fields.append(("Door", thread.owner.mention))
        await self.log_event(
            thread.guild, "channel_events", "Onderwerp gemaakt", self.log_fields(*fields),
            channel_id=thread.parent_id, footer=f"Thread-ID: {thread.id}",
        )

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        fields = [("Draad", f"#{thread.name}")]
        if thread.parent is not None:
            fields.append(("In", thread.parent.mention))
        await self.log_event(
            thread.guild, "channel_events", "Onderwerp verwijderd", self.log_fields(*fields),
            channel_id=thread.parent_id, footer=f"Thread-ID: {thread.id}",
        )

    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None or not isinstance(invite.guild, discord.Guild):
            return
        fields = [("Code", f"`{invite.code}`")]
        if invite.inviter is not None:
            fields.append(("Door", invite.inviter.mention))
        if invite.channel is not None:
            fields.append(("Kanaal", getattr(invite.channel, "mention", "?")))
        fields.extend((
            ("Verloopt", "nooit" if not invite.max_age else f"{invite.max_age}s"),
            ("Gebruik", "onbeperkt" if not invite.max_uses else str(invite.max_uses)),
        ))
        await self.log_event(invite.guild, "system_events", "Uitnodiging gemaakt", self.log_fields(*fields))

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None or not isinstance(invite.guild, discord.Guild):
            return
        await self.log_event(
            invite.guild, "system_events", "Uitnodiging verwijderd",
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
            ("gebruikers", user.mention if user is not None else f"<@{payload.user_id}>"),
            ("reactie", str(payload.emoji)),
            ("Bericht", f"[Jump to message](https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id})"),
        ]
        if channel is not None:
            fields.append(("Kanaal", channel.mention))
        await self.log_event(
            guild, "reaction_events", "Reactie toegevoegd" if added else "Reactie verwijderd",
            self.log_fields(*fields), channel_id=payload.channel_id, user=user,
            footer=f"Gebruikers-ID: {payload.user_id} • Bericht-ID: {payload.message_id}",
        )

    @tasks.loop(seconds=30)
    async def giveaway_worker(self) -> None:
        now = int(time.time())
        for guild in self.guilds:
            cfg = self.feature(guild.id, "giveaways")
            if not cfg.get("enabled"):
                continue
            for zeile in giveaway_store.list_all(guild.id, self.settings, 50):
                if str(zeile["status"]) != "active" or int(zeile["ends_at"]) > now:
                    continue
                await self.finish_giveaway(guild, zeile)

    @giveaway_worker.before_loop
    async def before_giveaways(self) -> None:
        await self.wait_until_ready()

    async def finish_giveaway(self, guild: discord.Guild, zeile: dict[str, Any], *, reroll: bool = False) -> list[int]:
        message_id = int(zeile["message_id"])
        if not reroll and not giveaway_store.mark_ended(message_id, self.settings):
            return []
        channel = guild.get_channel(int(zeile["channel_id"]))
        eligible_members = {m.id for m in guild.members if not m.bot and not giveaway_store.failed_requirements(zeile, m, self.settings)}
        eligible = set(taugliche_teilnehmer(giveaway_store.entries(message_id, self.settings), eligible_members))
        winners = giveaway_store.draw(message_id, max(1, int(zeile["winners"] or 1)), self.settings, exclude_past=reroll, eligible=eligible)
        giveaway_store.record_winners(message_id, winners, self.settings, reroll=reroll)
        mentions = ", ".join(f"<@{uid}>" for uid in winners)
        values = giveaway_store.values(zeile, len(giveaway_store.entries(message_id, self.settings)), winners_mentions=mentions or "—", server=guild.name)
        announce = giveaway_store.message(zeile, "msg_announce" if winners else "msg_no_entries", values)
        if channel:
            await self.send_layout(channel, "Nieuwe winactie getrokken" if reroll else "De winactie is afgelopen", announce, color=f"#{int(zeile.get('colour') or 0xF59E0B):06x}")
            if not reroll:
                try:
                    original = await channel.fetch_message(message_id)
                    await original.edit(view=self.giveaway_view(zeile, len(giveaway_store.entries(message_id, self.settings)), ended=True, winners=mentions))
                except Exception:
                    pass
        if zeile.get("dm_winners"):
            for uid in winners:
                member = guild.get_member(uid)
                kind = "winner-reroll" if reroll else "winner"
                if member and giveaway_store.claim_dm(message_id, uid, kind, self.settings):
                    try: await member.send(view=layout("Jij hebt gewonnen", giveaway_store.message(zeile, "msg_winner_dm", values), color=f"#{int(zeile.get('colour') or 0xF59E0B):06x}"))
                    except (discord.Forbidden, AttributeError): pass
                    await asyncio.sleep(.75)
        host = guild.get_member(int(zeile.get("host_id") or 0))
        host_kind = "host-reroll" if reroll else "host"
        if host and zeile.get("dm_host") and giveaway_store.claim_dm(message_id, host.id, host_kind, self.settings):
            try: await host.send(view=layout("Giveaway-Zusammenfassung", f"Preis: **{zeile['prize']}**\nWinnaars: {mentions or 'Niemand'}"))
            except (discord.Forbidden, AttributeError): pass
        await self.log(guild, "De winactie is afgelopen", f"Preis: {zeile['prize']}\nGewinner: {len(winners)}", "giveaways")
        return winners

    @tasks.loop(seconds=30)
    async def automation_worker(self) -> None:
        """Atomically send one-time/repeating messages and announcements."""
        now=int(time.time())
        for guild in self.guilds:
            if not self.feature(guild.id,"automation").get("enabled"):continue
            for kind in ("messages","announcements"):
                for item in automation_store.claim_due(self.settings,kind,now,guild_id=guild.id):
                    channel=guild.get_channel(int(item.get("channel_id") or 0))
                    if channel is None:continue
                    values={"server":guild.name,"member_count":guild.member_count or len(guild.members),"channel":channel.mention,"date":datetime.now().strftime("%d.%m.%Y"),"time":datetime.now().strftime("%H:%M"),"user":"@User","user_name":"gebruikers"}
                    title=str(item.get("title") or ("Automatisch rapporteren" if kind=="messages" else "Aankondiging"));text=str(item.get("content") or "")
                    for key,value in values.items():title=title.replace("{"+key+"}",str(value));text=text.replace("{"+key+"}",str(value))
                    role=guild.get_role(int(item.get("mention_role_id") or 0)) if kind=="announcements" else None
                    try:
                        body=f"{role.mention}\n{text}" if role else text
                        sent=await channel.send(view=layout(title,body,color=item.get("color"),image_url=item.get("image_url") or ""),allowed_mentions=discord.AllowedMentions(roles=True,users=False,everyone=False))
                        delay=int(item.get("delete_after") or 0)
                        if kind=="messages" and delay>0:await sent.delete(delay=delay)
                    except discord.HTTPException:logger.exception("Automatiseringsverzending mislukt voor %s",item.get("id"))

    @automation_worker.before_loop
    async def before_automation(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=30)
    async def ticket_notify_worker(self) -> None:
        now = int(time.time())
        hour = datetime.now(timezone.utc).hour
        for ticket in db.offene_tickets_fuer_benachrichtigung(self.settings):
            guild = self.get_guild(int(ticket["guild_id"]))
            if not guild:
                continue
            cfg = self.feature(guild.id, "tickets")
            if not cfg.get("enabled", True):
                continue
            if cfg.get("notify_quiet_enabled"):
                start = max(0, min(23, int(cfg.get("notify_quiet_start") or 22)))
                end = max(0, min(23, int(cfg.get("notify_quiet_end") or 7)))
                quiet = start <= hour < end if start < end else hour >= start or hour < end
                if quiet:
                    continue
            channel = guild.get_channel(int(ticket["channel_id"]))
            if not channel:
                continue
            last_owner = int(ticket.get("last_owner_message") or 0)
            last_staff = int(ticket.get("last_staff_message") or 0)
            if cfg.get("notify_user_enabled") and last_staff > last_owner:
                delay = max(30, min(86400, int(cfg.get("notify_user_delay") or 900)))
                cooldown = max(60, min(604800, int(cfg.get("notify_user_cooldown") or 21600)))
                if now - last_staff >= delay and now - int(ticket.get("user_dm_at") or 0) >= cooldown:
                    recipient = guild.get_member(int(ticket["owner_id"]))
                    if recipient:
                        try:
                            await recipient.send(view=layout("Nieuw antwoord in uw ticket", f"The team replied in <#{channel.id}> on **{guild.name}**. Your ticket is waiting for you.", color="#5865f2"))
                            db.ticket_setzen(channel.id, self.settings, user_dm_at=now)
                        except (discord.Forbidden, discord.HTTPException):
                            pass
            if cfg.get("notify_staff_enabled") and last_staff > 0 and last_owner > last_staff:
                delay = max(30, min(86400, int(cfg.get("notify_staff_delay") or 900)))
                cooldown = max(60, min(604800, int(cfg.get("notify_staff_cooldown") or 21600)))
                if now - last_owner >= delay and now - int(ticket.get("staff_dm_at") or 0) >= cooldown:
                    recipient = guild.get_member(int(ticket.get("last_staff_id") or 0))
                    if recipient:
                        try:
                            await recipient.send(view=layout("Ticket wacht", f"The creator replied in <#{channel.id}> on **{guild.name}** and is waiting for the team.", color="#f0b232"))
                            db.ticket_setzen(channel.id, self.settings, staff_dm_at=now)
                        except (discord.Forbidden, discord.HTTPException):
                            pass

    @ticket_notify_worker.before_loop
    async def before_ticket_notify(self) -> None:
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
        await bot.interaction_notice(interaction, "Geen toestemming", "U heeft de machtiging Server beheren nodig.", error=True)
        return False
    return True


def hat_mod_rechte(interaction: discord.Interaction, benoetigt: str) -> bool:
    recht = getattr(interaction.user.guild_permissions, benoetigt, False)
    return bool(recht)


def register_commands(bot: ShopBot) -> None:
    @bot.tree.command(name="log-instellen", description="Stelt volledige logboekregistratie in een kanaal in")
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
            "Logboekregistratie ingesteld",
            f"{count} Kategorien schreiben jetzt in {channel.mention}. Reaktions-Logs: `{'an' if reaktionen else 'aus'}`.",
        )

    @bot.tree.command(name="log-status", description="Toont de status van alle logboekcategorieën")
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

    @bot.tree.command(name="log-test", description="Plaatst een testinvoer voor een logboekcategorie")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def log_test(interaction: discord.Interaction, category: app_commands.Choice[str]):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        channel_id = int(cfg["log_channels"].get(category.value) or 0)
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Geen logkanaal", "Voor deze categorie is geen geldig tekstkanaal geselecteerd.", error=True)
        await interaction.response.defer(ephemeral=True)
        sent = await bot.send_layout(channel, "Testinvoer", f"De logging voor **{category.name}** funktioniert.", color="#526dff")
        await interaction.followup.send(view=layout("Test voltooid", f"De vermelding is geplaatst in {channel.mention} gepostet." if sent else "De bot kon daar niet schrijven.", color="#3ba55d" if sent else "#ed4245"), ephemeral=True)

    @bot.tree.command(name="log-schakelen", description="Schakelt een logboekcategorie in of uit")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def log_toggle(interaction: discord.Interaction, category: app_commands.Choice[str], aktiviert: bool):
        if not await require_manage(interaction):
            return
        cfg = bot.logging_config(interaction.guild.id)
        cfg["enabled"] = True
        cfg["log_enabled"][category.value] = aktiviert
        db.set_feature(interaction.guild.id, "logging", cfg, interaction.user.id, bot.settings)
        bot.feature_cache.pop((interaction.guild.id, "logging"), None)
        await bot.interaction_notice(interaction, "Categorie gewijzigd", f"**{category.name}** is nu `{'aktiv' if aktiviert else 'aus'}`.")

    @bot.tree.command(name="log-negeren", description="Beheert genegeerde kanalen, rollen en gebruikers")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Kanaal", value="channel"),
        app_commands.Choice(name="rol", value="role"),
        app_commands.Choice(name="Gebruiker", value="user"),
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
            return await bot.interaction_notice(interaction, "Ongeldige identiteitskaart", "Voer een numerieke Discord-ID in.", error=True)
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
        await bot.interaction_notice(interaction, "Uitzonderingen bijgewerkt", f"Die {kind.name}-ID `{discord_id}` is {'entfernt' if entfernen else 'toegevoegd'}.")

    @bot.tree.command(name="log-zoeken", description="Zoekt naar opgeslagen Discord-evenementen")
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
            return await bot.interaction_notice(interaction, "Geen treffers", "Er zijn geen opgeslagen evenementen gevonden voor deze zoekopdracht.")
        lines = [f"<t:{row['created_at']}:R> **{row['title']}** — {row['description'].replace(chr(10), ' ')[:160]}" for row in rows]
        await bot.interaction_notice(interaction, f"Log-Suche · {len(rows)} Treffer", "\n".join(lines)[:3800])

    @bot.tree.command(name="log-exporteren", description="Exporteert opgeslagen Discord-evenementen als tekstbestand")
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
        ) or "Geen evenementen in de geselecteerde periode."
        await interaction.followup.send(
            view=layout("Log-Export", f"{len(rows)} Ereignisse aus den letzten {tage} dagenn."),
            file=discord.File(io.BytesIO(content.encode("utf-8")), filename=f"lbost-logs-{interaction.guild.id}-{tage}d.txt"),
            ephemeral=True,
        )

    @bot.tree.command(name="log-resetten", description="Reset de volledige logconfiguratie")
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
        await bot.interaction_notice(interaction, "Logboek resetten", "Alle kanalen, schakelaars en uitzonderingen zijn verwijderd. Het evenementenarchief blijft behouden.")

    # University exposes logging as one `/log` command group.  The old
    # hyphenated commands stay registered for existing LBoost servers, while
    # these aliases provide the same command structure and behaviour.
    log_group = app_commands.Group(name="log", description="Beheer de volledige serverlogboekregistratie")

    @log_group.command(name="instellen", description="Stelt volledige logboekregistratie in een kanaal in")
    async def grouped_log_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        reaktionen: bool = False,
    ):
        await log_setup.callback(interaction, channel, reaktionen)

    @log_group.command(name="status", description="Toont de status van alle logboekcategorieën")
    async def grouped_log_status(interaction: discord.Interaction):
        await log_status.callback(interaction)

    @log_group.command(name="configuratie", description="Toont de volledige logconfiguratie")
    async def grouped_log_config(interaction: discord.Interaction):
        await log_status.callback(interaction)

    @log_group.command(name="test", description="Verzendt testinvoer naar geconfigureerde kanalen")
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
                    ("Categorie", key),
                    ("Testgebruikers", interaction.user.mention),
                    ("Tijdstempel", discord.utils.format_dt(discord.utils.utcnow(), "f")),
                ),
                channel_id=interaction.channel_id,
                user=interaction.user,
                footer=f"Test message • Gebruikers-ID: {interaction.user.id}",
            )
            sent += 1
        await interaction.followup.send(
            view=layout(
                "Testberichten verzonden" if sent else "Geen testberichten verzonden",
                f"Sent {sent} test log messages to configured channels."
                if sent else "Er zijn geen logboekcategorieën ingeschakeld of geconfigureerd.",
            ),
            ephemeral=True,
        )

    @log_group.command(name="schakelen", description="Schakelt een logboekcategorie in of uit")
    @app_commands.choices(category=[app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in LOG_CATEGORIES])
    async def grouped_log_toggle(
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        aktiviert: bool,
    ):
        await log_toggle.callback(interaction, category, aktiviert)

    @log_group.command(name="negeren", description="Beheert genegeerde kanalen, rollen en gebruikers")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Kanaal", value="channel"),
        app_commands.Choice(name="rol", value="role"),
        app_commands.Choice(name="Gebruiker", value="user"),
    ])
    async def grouped_log_ignore(
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        discord_id: str,
        entfernen: bool = False,
    ):
        await log_ignore.callback(interaction, kind, discord_id, entfernen)

    @log_group.command(name="zoeken", description="Zoekt naar opgeslagen Discord-evenementen")
    async def grouped_log_search(
        interaction: discord.Interaction,
        suche: str = "",
        tage: app_commands.Range[int, 1, 30] = 7,
    ):
        await log_search.callback(interaction, suche, tage)

    @log_group.command(name="exporteren", description="Exporteert opgeslagen Discord-evenementen als tekstbestand")
    async def grouped_log_export(
        interaction: discord.Interaction,
        tage: app_commands.Range[int, 1, 30] = 7,
    ):
        await log_export.callback(interaction, tage)

    @log_group.command(name="resetten", description="Reset de volledige logconfiguratie")
    async def grouped_log_reset(interaction: discord.Interaction):
        await log_reset.callback(interaction)

    bot.tree.add_command(log_group)

    @bot.tree.command(name="ticket-paneel", description="Verzendt een geconfigureerd ticketpaneel")
    @app_commands.describe(panel="Paneelsleutel uit de dashboardconfiguratie")
    async def ticket_panel_command(interaction: discord.Interaction, panel: str = "default"):
        if not await require_manage(interaction):
            return
        cfg = bot.ticket_panel(interaction.guild.id, panel)
        if not cfg.get("enabled"):
            return await bot.interaction_notice(interaction, "Kaartjes uitgeschakeld", "Activeer eerst de module in het dashboard.", error=True)
        channel = interaction.guild.get_channel(int(cfg.get("panel_channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanaal ontbreekt", "Kies een geldig tekstkanaal in het dashboard.", error=True)
        categories = [item for item in (cfg.get("categories") or []) if isinstance(item, dict)][:15]
        buttons = []
        if categories:
            for index, category in enumerate(categories):
                key = re.sub(r"[^a-zA-Z0-9_-]", "", str(category.get("key") or f"category-{index + 1}"))[:28]
                try:
                    style = discord.ButtonStyle(int(category.get("button_style") or 1))
                except (TypeError, ValueError):
                    style = discord.ButtonStyle.primary
                buttons.append(discord.ui.Button(
                    label=str(category.get("name") or "Ondersteuning")[:80],
                    emoji=emoji(category.get("emoji")), style=style,
                    custom_id=f"shop:ticket:create:{panel}~{key}"[:100],
                ))
        else:
            buttons.append(discord.ui.Button(
                label=str(cfg.get("button_label") or "Ticket openen")[:80],
                emoji=emoji(cfg.get("button_emoji")), style=discord.ButtonStyle.primary,
                custom_id=f"shop:ticket:create:{panel}"[:100],
            ))
        message = await bot.send_layout(
            channel,
            regeln.PANEL_TITEL if not cfg.get("title") else str(cfg.get("title"))[:256],
            (regeln.PANEL_BESCHREIBUNG if not cfg.get("description") else str(cfg.get("description")))[:3900],
            color=cfg.get("color"),
            buttons=buttons,
            image_url=str(cfg.get("image_url") or ""),
            thumbnail_url=str(cfg.get("thumbnail_url") or ""),
            footer=str(cfg.get("footer") or ""),
        )
        await bot.interaction_notice(
            interaction, "Paneel verzonden",
            f"Het ticketpaneel is gepubliceerd in <#{channel.id}> gepubliceerd." if message else "Paneel kon niet worden verzonden.",
            error=not bool(message),
        )

    @bot.tree.command(name="rollen-paneel", description="Verzendt een geconfigureerd rollenpaneel")
    @app_commands.describe(panel="Index van het paneel, beginnend met 0")
    async def reaction_panel_command(interaction: discord.Interaction, panel: int = 0):
        if not await require_manage(interaction):
            return
        cfg = bot.feature(interaction.guild.id, "reaction_roles")
        panels = [{**cfg, "roles_json": cfg.get("roles_json") or []}] + [p for p in (cfg.get("panels_json") or []) if isinstance(p, dict)]
        selected = panels[panel] if 0 <= panel < len(panels) else None
        if not cfg.get("enabled") or not selected:
            return await bot.interaction_notice(interaction, "Paneel niet beschikbaar", "Controleer de dashboardconfiguratie.", error=True)
        channel = interaction.guild.get_channel(int(selected.get("channel_id") or cfg.get("channel_id") or interaction.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await bot.interaction_notice(interaction, "Kanaal ontbreekt", "Kies een geldig tekstkanaal in het dashboard.", error=True)
        buttons = []
        for item in selected.get("roles_json", [])[:25]:
            if not isinstance(item, dict) or not str(item.get("role_id", "")).isdigit():
                continue
            ziel = interaction.guild.get_role(int(item["role_id"]))
            buttons.append(discord.ui.Button(
                label=str(item.get("label") or (ziel.name if ziel else "rol"))[:80],
                emoji=emoji(item.get("emoji")),
                style=discord.ButtonStyle.secondary,
                custom_id=f"shop:role:{int(item['role_id'])}",
            ))
        if not buttons:
            return await bot.interaction_notice(interaction, "Geen knoppen", "Het paneel heeft geen geldige rolinvoer.", error=True)
        sent = await bot.send_layout(channel, str(selected.get("title") or "Selecteer rollen"), str(selected.get("description") or "Kies uw rollen met behulp van de knoppen."), color=selected.get("color"), buttons=buttons)
        await bot.interaction_notice(interaction, "Paneel verzonden", f"Het rollenpaneel is gepubliceerd in <#{channel.id}> gepubliceerd." if sent else "Paneel kon niet worden verzonden.", error=not bool(sent))

    async def mod_zugriff(interaction: discord.Interaction, recht: str, modul: str = "Matiging") -> bool:
        if modul == "Matiging" and not bot.feature(interaction.guild.id, "moderation").get("enabled"):
            await bot.interaction_notice(interaction, "Moderatie uitgeschakeld", "Activeer de module in het dashboard.", error=True)
            return False
        if not hat_mod_rechte(interaction, recht):
            await bot.interaction_notice(interaction, "Geen toestemming", f"Je mist de Discord-machtiging ‘{recht.replace('_', ' ')}’.", error=True)
            return False
        return True

    # The complete hybrid University moderation suite is registered below.

    @bot.tree.command(name="winactie", description="Start een winactie")
    @app_commands.describe(minuten="Duur", gewinner="Aantal winnaars", preis="Wat wordt er verloot?")
    async def giveaway(interaction: discord.Interaction, minuten: app_commands.Range[int, 1, 525600],
                       gewinner: app_commands.Range[int, 1, 20], preis: str):
        if not await require_manage(interaction):
            return
        cfg = bot.feature(interaction.guild.id, "giveaways")
        if not cfg.get("enabled"):
            return await bot.interaction_notice(interaction, "Giveaways uitgeschakeld", "Activeer de module in het dashboard.", error=True)
        await interaction.response.defer(ephemeral=True)
        ends = int(time.time()) + minuten * 60
        text = f"Endet: <t:{ends}:R>\nGewinner: {gewinner}\nDeelname via de knop."
        knopf = discord.ui.Button(label="Doe mee", style=discord.ButtonStyle.success, custom_id="shop:giveaway:0")
        nachricht = await interaction.channel.send(view=layout(preis[:200], text, color="#57f287", buttons=[knopf]))
        giveaway_store.create({
            "message_id": nachricht.id, "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id, "prize": preis[:200], "winners": gewinner,
            "ends_at": ends, "status": "active", "winner_ids": "[]",
            "host_id": interaction.user.id, "start_time": int(time.time()),
            "title": "", "description": "", "colour": 0xF59E0B,
            "button_label": "Doe mee", "button_emoji": "", "image_url": "",
            "required_role_id": int(cfg.get("required_role_id") or 0), "blocked_role_id": 0,
            "min_messages": 0, "min_level": 0, "min_account_days": 0, "min_member_days": 0,
            "dm_winners": 1, "dm_host": 1, "allow_leave": 1,
            **{key: "" for key in giveaway_store.DEFAULT_MESSAGES},
        }, bot.settings)
        # Der Knopf braucht die endgültige Nachrichten-ID, also einmal nachziehen.
        record = giveaway_store.get(interaction.guild.id, nachricht.id, bot.settings)
        await nachricht.edit(view=bot.giveaway_view(record, 0))
        await interaction.followup.send(view=layout("De winactie is begonnen", f"Bericht: `{nachricht.id}`"), ephemeral=True)

    @bot.tree.command(name="winactie-opnieuw", description="Winnaars van de weggeefactie opnieuw getrokken")
    async def giveaway_reroll(interaction: discord.Interaction, nachrichten_id: str):
        if not await require_manage(interaction):
            return
        if not nachrichten_id.isdigit():
            return await bot.interaction_notice(interaction, "Ongeldige identiteitskaart", "Geef een geldige bericht-ID op.", error=True)
        row = giveaway_store.get(interaction.guild.id, int(nachrichten_id), bot.settings)
        eligible_now = taugliche_teilnehmer(giveaway_store.entries(int(nachrichten_id), bot.settings), {m.id for m in interaction.guild.members}) if row else []
        if not row or not eligible_now:
            return await bot.interaction_notice(interaction, "Niet mogelijk", "Giveaway of deelnemers zijn niet gevonden.", error=True)
        winners = await bot.finish_giveaway(interaction.guild, row, reroll=True)
        await bot.interaction_notice(interaction, "Nieuw getekend", f"{len(winners)} nieuwe winnaars getrokken. Eerdere winnaars zijn overgeslagen.")

    @bot.command(name="winactie", aliases=["giveaway"])
    async def giveaway_prefix(ctx: commands.Context, minuten: int, gewinner: int, *, preis: str):
        """Prefix counterpart of /giveaway: !giveaway <minutes> <winners> <prize>."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not ctx.author.guild_permissions.manage_guild:
            return
        minuten=max(1,min(525600,minuten)); gewinner=max(1,min(20,gewinner)); ends=int(time.time())+minuten*60
        record={"message_id":0,"guild_id":ctx.guild.id,"channel_id":ctx.channel.id,"prize":preis[:200],"winners":gewinner,"ends_at":ends,"status":"active","winner_ids":"[]","host_id":ctx.author.id,"start_time":int(time.time()),"title":"","description":"","colour":0xF59E0B,"button_label":"Doe mee","button_emoji":"","image_url":"","required_role_id":0,"blocked_role_id":0,"min_messages":0,"min_level":0,"min_account_days":0,"min_member_days":0,"dm_winners":1,"dm_host":1,"allow_leave":1,**{key:"" for key in giveaway_store.DEFAULT_MESSAGES}}
        message=await ctx.send(view=bot.giveaway_view(record,0)); record["message_id"]=message.id; giveaway_store.create(record,bot.settings); await message.edit(view=bot.giveaway_view(record,0))

    @bot.command(name="winactie-opnieuw", aliases=["giveaway-reroll", "greroll"])
    async def giveaway_reroll_prefix(ctx: commands.Context, message_id: int):
        """Prefix counterpart of /giveaway-reroll."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not ctx.author.guild_permissions.manage_guild:return
        record=giveaway_store.get(ctx.guild.id,message_id,bot.settings)
        if record: await bot.finish_giveaway(ctx.guild,record,reroll=True)

    @bot.tree.command(name="aankondiging", description="Verzendt een Components V2-aankondiging")
    async def announce(interaction: discord.Interaction, kanal: discord.TextChannel, titel: str, text: str):
        if not await require_manage(interaction):
            return
        sent = await bot.send_layout(kanal, titel[:256], text[:3900])
        await bot.interaction_notice(interaction, "Aankondiging verzonden", f"Gesendet in {kanal.mention}." if sent else "Verzenden is mislukt.", error=not bool(sent))

    @bot.tree.error
    async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error("Slash-opdracht mislukt: %s", error, exc_info=(type(error), error, error.__traceback__))
        try:
            await bot.interaction_notice(interaction, "Commando mislukt", "Het commando kon niet veilig worden uitgevoerd. Controleer rollen en botrechten.", error=True)
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
