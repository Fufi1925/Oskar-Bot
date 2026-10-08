# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 University Bot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

# cogs/commands/ticket.py

import discord
from utils.emoji import CROSS, DELETE_ALT1, HANDSHAKE, LOCK, MESSAGE, TICK, UNLOCK, ZBAN, ZMODULE, ZWRENCH
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
import re
import time
from types import SimpleNamespace
from utils.config import *
from utils.panels import Panel, container, from_embed
from utils.links import dashboard_url
from utils import dashboard_roles, feature_gates, ticket_ai, ticket_notify, ticket_settings
from discord.ui import ActionRow, LayoutView, Separator, TextDisplay

# --- Configurable Variables ---
EMBED_COLOR = 0xFF0000
# Kein Bild mehr in der Ticket-Begruessung.
#
# Hier stand eine Discord-CDN-Adresse mit Ablaufsignatur ("?ex=...").
# Solche Links verfallen nach Stunden; danach liefert der Server 403,
# Discord lehnt die Nachricht mit dem toten Bild ab, und der frisch
# erstellte Ticket-Kanal bleibt leer. Genau das ist passiert.
#
# Wer wieder ein Bild will: an einen dauerhaften Ort legen und die
# Adresse hier eintragen -- keine attachments-URL aus einem Chat.

# --- Emoji Variables ---
SUCCESS_EMOJI = TICK
ERROR_EMOJI = CROSS
LOCK_EMOJI = LOCK
UNLOCK_EMOJI = UNLOCK
CLAIM_EMOJI = HANDSHAKE
CLOSE_EMOJI = ZBAN
DELETE_EMOJI = DELETE_ALT1
REOPEN_EMOJI = ZWRENCH
TRANSCRIPT_EMOJI = ZMODULE

# --- Constants ---
if not os.path.exists('db'):
    os.makedirs('db')
DB_PATH = 'db/ticket.db'
MAX_CATEGORIES = 15
TICKET_LIMIT_PER_USER = 3

# --- Database Class ---
class TicketDatabase:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS guild_configs (guild_id INTEGER PRIMARY KEY, panel_channel_id INTEGER, logging_channel_id INTEGER, panel_message_id INTEGER, panel_type TEXT, embed_title TEXT, embed_description TEXT, embed_color INTEGER, embed_image_url TEXT, embed_thumbnail_url TEXT, closed_category_id INTEGER, always_transcript INTEGER NOT NULL DEFAULT 0)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS ticket_categories (category_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT NOT NULL, emoji TEXT, notified_roles TEXT, button_style INTEGER, discord_category_id INTEGER, panel_id INTEGER, ticket_welcome_title TEXT NOT NULL DEFAULT '', ticket_welcome_message TEXT NOT NULL DEFAULT '', FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS open_tickets (channel_id INTEGER PRIMARY KEY, ticket_number INTEGER, guild_id INTEGER, creator_id INTEGER NOT NULL, category_db_id INTEGER, created_at TEXT NOT NULL, closed_by_id INTEGER, closed_at TEXT, is_locked BOOLEAN DEFAULT FALSE, is_claimed BOOLEAN DEFAULT FALSE, claimed_by_id INTEGER, FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE, FOREIGN KEY (category_db_id) REFERENCES ticket_categories(category_id) ON DELETE SET NULL)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS user_ticket_counts (guild_id INTEGER, user_id INTEGER, ticket_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))")
            self.conn.execute("CREATE TABLE IF NOT EXISTS ticket_transcripts (ticket_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, guild_name TEXT NOT NULL, channel_name TEXT NOT NULL, ticket_number INTEGER, creator_id INTEGER NOT NULL, closed_by_id INTEGER NOT NULL, category_name TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, expires_at TEXT NOT NULL, messages_json TEXT NOT NULL)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_transcripts_expiry ON ticket_transcripts(expires_at)")
            guild_columns = {
                row[1] for row in self.conn.execute("PRAGMA table_info(guild_configs)").fetchall()
            }
            if 'staff_roles' not in guild_columns:
                self.conn.execute("ALTER TABLE guild_configs ADD COLUMN staff_roles TEXT DEFAULT ''")
            if "always_transcript" not in guild_columns:
                self.conn.execute(
                    "ALTER TABLE guild_configs ADD COLUMN always_transcript INTEGER NOT NULL DEFAULT 0"
                )
            panel_columns = {
                row[1] for row in self.conn.execute("PRAGMA table_info(ticket_panels)").fetchall()
            }
            panel_migrations = {
                "select_placeholder": "TEXT NOT NULL DEFAULT 'Wähle eine Kategorie…'",
                "ticket_welcome_title": "TEXT NOT NULL DEFAULT 'Ticket #{ticket_number}'",
                "ticket_welcome_message": "TEXT NOT NULL DEFAULT ''",
                "ticket_created_message": (
                    "TEXT NOT NULL DEFAULT 'Dein Ticket ist offen: {channel}'"
                ),
                "ticket_questions": "TEXT NOT NULL DEFAULT '[]'",
            }
            for column, definition in panel_migrations.items():
                if panel_columns and column not in panel_columns:
                    self.conn.execute(
                        f"ALTER TABLE ticket_panels ADD COLUMN {column} {definition}"
                    )
            category_columns = {
                row[1] for row in self.conn.execute(
                    "PRAGMA table_info(ticket_categories)"
                ).fetchall()
            }
            category_migrations = {
                "panel_id": "INTEGER",
                "ticket_welcome_title": "TEXT NOT NULL DEFAULT ''",
                "ticket_welcome_message": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in category_migrations.items():
                if column not in category_columns:
                    self.conn.execute(
                        f"ALTER TABLE ticket_categories ADD COLUMN {column} {definition}"
                    )
        with self.conn:
            self.conn.execute(ticket_settings.SCHEMA)
            self.conn.execute(ticket_settings.STATE_SCHEMA)
            self.conn.execute(ticket_settings.RATING_SCHEMA)
            self.conn.execute(ticket_settings.FEEDBACK_SCHEMA)
        ticket_ai.ensure_sync_schema(self.conn)

    def execute(self, q, p=()):
        with self.conn: return self.conn.execute(q, p)
    def fetchone(self, q, p=()):
        cur = self.conn.cursor(); cur.execute(q, p); return cur.fetchone()
    def fetchall(self, q, p=()):
        cur = self.conn.cursor(); cur.execute(q, p); return cur.fetchall()
    def close(self):
        if self.conn: self.conn.close()

# --- Utility Functions ---
async def get_or_create_log_channel(db, guild):
    config = db.fetchone("SELECT logging_channel_id FROM guild_configs WHERE guild_id = ?", (guild.id,))
    if config and config["logging_channel_id"] and (ch := guild.get_channel(config["logging_channel_id"])): return ch
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    try:
        ch = await guild.create_text_channel(f"{BRAND_NAME}-ticket-logs", overwrites=overwrites)
        db.execute("INSERT INTO guild_configs (guild_id, logging_channel_id) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET logging_channel_id=excluded.logging_channel_id", (guild.id, ch.id))
        return ch
    except: return None

async def log_ticket_action(db, guild, user, action, details):
    if log_channel := await get_or_create_log_channel(db, guild):
        embed = discord.Embed(title=f"Ticket Action: {action}", color=EMBED_COLOR, timestamp=datetime.now())
        embed.add_field(name="Action By", value=user.mention).add_field(name="Details", value=details, inline=False)
        try: await log_channel.send(view=from_embed(embed))
        except: pass

def _transcript_link(ticket_id: int) -> str:
    base = dashboard_url().rstrip("/")
    return f"{base}/Tickets/Transkript/{ticket_id}" if base else ""


def _message_snapshot(message) -> dict:
    """JSON-safe Discord message data used by the authenticated web transcript."""
    author = message.author
    avatar = getattr(getattr(author, "display_avatar", None), "url", "")
    reply = None
    reference = getattr(message, "reference", None)
    resolved = getattr(reference, "resolved", None) if reference else None
    if resolved is not None and hasattr(resolved, "author"):
        reply = {
            "message_id": str(getattr(resolved, "id", "")),
            "author": getattr(resolved.author, "display_name", str(resolved.author)),
            "content": str(getattr(resolved, "clean_content", ""))[:180],
        }
    elif reference and getattr(reference, "message_id", None):
        reply = {"message_id": str(reference.message_id), "author": "", "content": ""}

    embeds = []
    for embed in getattr(message, "embeds", []):
        try:
            embeds.append(embed.to_dict())
        except Exception:
            pass
    components = []
    for component in getattr(message, "components", []):
        try:
            components.append(component.to_dict())
        except Exception:
            pass

    return {
        "id": str(message.id),
        "created_at": message.created_at.isoformat(),
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "content": str(getattr(message, "clean_content", "") or ""),
        "raw_content": str(getattr(message, "content", "") or ""),
        "pinned": bool(getattr(message, "pinned", False)),
        "author": {
            "id": str(author.id),
            "username": str(author),
            "display_name": getattr(author, "display_name", str(author)),
            "avatar_url": str(avatar),
            "bot": bool(getattr(author, "bot", False)),
        },
        "reply": reply,
        "attachments": [
            {
                "id": str(attachment.id),
                "filename": attachment.filename,
                "url": attachment.url,
                "proxy_url": attachment.proxy_url,
                "content_type": attachment.content_type,
                "size": attachment.size,
                "width": attachment.width,
                "height": attachment.height,
                "description": getattr(attachment, "description", None),
            }
            for attachment in getattr(message, "attachments", [])
        ],
        "embeds": embeds,
        "components": components,
        "stickers": [
            {"name": sticker.name, "url": str(sticker.url)}
            for sticker in getattr(message, "stickers", [])
        ],
        "reactions": [
            {"emoji": str(reaction.emoji), "count": reaction.count}
            for reaction in getattr(message, "reactions", [])
        ],
    }


async def save_ticket_transcript(db, channel, ticket, closed_by, category_name: str) -> str:
    messages = [
        _message_snapshot(message)
        async for message in channel.history(limit=None, oldest_first=True)
    ]
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=90)
    db.execute("DELETE FROM ticket_transcripts WHERE expires_at <= ?", (now.isoformat(),))
    db.execute(
        "INSERT INTO ticket_transcripts"
        "(ticket_id,guild_id,guild_name,channel_name,ticket_number,creator_id,"
        "closed_by_id,category_name,created_at,expires_at,messages_json)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(ticket_id) DO UPDATE SET guild_name=excluded.guild_name,"
        " channel_name=excluded.channel_name,ticket_number=excluded.ticket_number,"
        " creator_id=excluded.creator_id,closed_by_id=excluded.closed_by_id,"
        " category_name=excluded.category_name,created_at=excluded.created_at,"
        " expires_at=excluded.expires_at,messages_json=excluded.messages_json",
        (
            channel.id, channel.guild.id, channel.guild.name, channel.name,
            ticket["ticket_number"], ticket["creator_id"], closed_by.id,
            category_name, now.isoformat(), expires.isoformat(),
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    return _transcript_link(channel.id)


def transcript_dm_view(guild_name: str, channel_name: str, ticket_number, link: str):
    button = discord.ui.Button(
        label="Open Transcript", emoji=TRANSCRIPT_EMOJI,
        style=discord.ButtonStyle.link, url=link,
    )
    return Panel(
        "Ticket Transcript",
        f"{TRANSCRIPT_EMOJI} **Ticket:** #{channel_name}\n"
        f"**Ticket ID:** `{ticket_number or channel_name}`\n"
        f"**Server:** {guild_name}",
        "This private transcript is available for **90 days**. "
        "Sign in with Discord to view the complete conversation.",
        tone="brand", buttons=[button],
    )


async def get_or_create_closed_category(db, guild):
    config = db.fetchone("SELECT closed_category_id FROM guild_configs WHERE guild_id = ?", (guild.id,))
    if config and config["closed_category_id"] and (cat := guild.get_channel(config["closed_category_id"])): return cat
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    try:
        cat = await guild.create_category("Closed Tickets", overwrites=overwrites)
        db.execute("UPDATE guild_configs SET closed_category_id = ? WHERE guild_id = ?", (cat.id, guild.id))
        return cat
    except: return None

# --- Setup Views ---
class EmbedEditorView(discord.ui.View):
    def __init__(self, cog, ctx, panel_channel, panel_type):
        super().__init__(timeout=600)
        self.cog, self.ctx, self.panel_channel, self.panel_type = cog, ctx, panel_channel, panel_type
        self.message = None
        self.embed_data = {"title": "Support Tickets", "description": "Click a button or select an option below to create a ticket.", "color": EMBED_COLOR}

    def _create_preview_embed(self):
        embed = discord.Embed.from_dict(self.embed_data)
        if img_url := self.embed_data.get("image", {}).get("url"): embed.set_image(url=img_url)
        if thumb_url := self.embed_data.get("thumbnail", {}).get("url"): embed.set_thumbnail(url=thumb_url)
        return embed

    async def start(self, interaction):
        await interaction.response.send_message("Use the buttons to customize the panel embed.", view=from_embed(self._create_preview_embed(), self), ephemeral=True)
        self.message = await interaction.original_response()

    async def _prompt(self, inter, prompt):
        await inter.response.send_message(prompt, ephemeral=True)
        try:
            msg = await self.cog.bot.wait_for("message", check=lambda m: m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id, timeout=120)
            try: await msg.delete()
            except: pass
            return msg.content
        except: return None

    @discord.ui.button(label="Title", emoji=MESSAGE, style=discord.ButtonStyle.green, row=0)
    async def edit_title(self, inter, button):
        if title := await self._prompt(inter, "Enter new title:"):
            self.embed_data["title"] = title
            await self.message.edit(view=from_embed(self._create_preview_embed()))

    @discord.ui.button(label="Description", emoji=MESSAGE, style=discord.ButtonStyle.green, row=0)
    async def edit_desc(self, inter, button):
        if desc := await self._prompt(inter, "Enter new description:"):
            self.embed_data["description"] = desc
            await self.message.edit(view=from_embed(self._create_preview_embed()))
    
    @discord.ui.button(label="Image URL", style=discord.ButtonStyle.blurple, row=1)
    async def edit_image(self, inter, button):
        if url := await self._prompt(inter, "Enter image URL (`none` to remove):"):
            self.embed_data["image"] = {"url": url} if url.lower() != 'none' else {}
            await self.message.edit(view=from_embed(self._create_preview_embed()))

    @discord.ui.button(label="Thumbnail URL", style=discord.ButtonStyle.blurple, row=1)
    async def edit_thumb(self, inter, button):
        if url := await self._prompt(inter, "Enter thumbnail URL (`none` to remove):"):
            self.embed_data["thumbnail"] = {"url": url} if url.lower() != 'none' else {}
            await self.message.edit(view=from_embed(self._create_preview_embed()))

    @discord.ui.button(label="Submit & Continue", emoji=TICK, style=discord.ButtonStyle.primary, row=2)
    async def submit(self, inter, button):
        await inter.response.defer()
        for item in self.children: item.disabled = True
        try: await self.message.edit(view=self)
        except: pass
        self.cog.db.execute("INSERT INTO guild_configs (guild_id, panel_channel_id, panel_type, embed_title, embed_description, embed_color, embed_image_url, embed_thumbnail_url) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET panel_channel_id=excluded.panel_channel_id, panel_type=excluded.panel_type, embed_title=excluded.embed_title, embed_description=excluded.embed_description, embed_color=excluded.embed_color, embed_image_url=excluded.embed_image_url, embed_thumbnail_url=excluded.embed_thumbnail_url", (self.ctx.guild.id, self.panel_channel.id, self.panel_type, self.embed_data["title"], self.embed_data["description"], self.embed_data["color"], self.embed_data.get("image",{}).get("url"), self.embed_data.get("thumbnail",{}).get("url")))
        await CategoryConfigView(self.cog, self.ctx).start(inter)
        self.stop()

class CategoryConfigView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=900)
        self.cog, self.ctx, self.message, self.categories = cog, ctx, None, []
        self._setup_buttons()

    def _setup_buttons(self):
        panel_type = self.cog.db.fetchone("SELECT panel_type FROM guild_configs WHERE guild_id=?", (self.ctx.guild.id,))['panel_type']
        self.add_item(discord.ui.Button(label=f"Add Category", style=discord.ButtonStyle.success, custom_id="add_cat"))
        self.remove_select = discord.ui.Select(placeholder="Select a category to remove...", custom_id="remove_cat")
        self.add_item(self.remove_select)
        self.add_item(discord.ui.Button(label="Finish Setup", emoji=TICK, style=discord.ButtonStyle.primary, custom_id="finish_setup", row=2))

    async def start(self, interaction):
        self._update_remove_select()
        await interaction.followup.send(view=from_embed(self._update_embed(), self), ephemeral=True)
        self.message = await interaction.original_response()
    
    def _update_embed(self):
        embed = discord.Embed(title="Category Configuration", description="Add or remove ticket categories for your panel.", color=EMBED_COLOR)
        embed.add_field(name="Current Categories", value="\n".join([f"{c['emoji'] or ''} {c['name']}" for c in self.categories]) or "None yet. Click 'Add Category' to begin.")
        return embed

    def _update_remove_select(self):
        self.remove_select.options = [discord.SelectOption(label=c['name'], value=str(i), emoji=c.get('emoji')) for i, c in enumerate(self.categories)] or [discord.SelectOption(label="No categories to remove", value="placeholder")]

    async def _prompt(self, inter: discord.Interaction, prompt_text: str, followup: bool = False):
        send_method = inter.followup.send if followup else inter.response.send_message
        await send_method(prompt_text, ephemeral=True)
        try:
            msg = await self.cog.bot.wait_for("message", check=lambda m: m.author.id == self.ctx.author.id and m.channel.id == inter.channel.id, timeout=120.0)
            try: await msg.delete()
            except discord.HTTPException: pass
            return msg.content
        except asyncio.TimeoutError:
            return None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id: return False
        custom_id = interaction.data["custom_id"]
        if custom_id == "add_cat": await self._add_category_flow(interaction)
        elif custom_id == "remove_cat": await self._remove_category(interaction, interaction.data["values"][0])
        elif custom_id == "finish_setup": await self._finish_setup(interaction)
        return True

    async def _add_category_flow(self, inter: discord.Interaction):
        await inter.response.defer()
        if len(self.categories) >= MAX_CATEGORIES:
            return await inter.followup.send(f"Max {MAX_CATEGORIES} categories reached.", ephemeral=True)

        cat_name = await self._prompt(inter, "Please type the name for the new category (e.g., General Support).", followup=True)
        if not cat_name: return await inter.followup.send("Timed out.", ephemeral=True)

        emoji = await self._prompt(inter, 'Please provide an emoji for the category, or type `skip`.', followup=True)
        if not emoji: return await inter.followup.send("Timed out.", ephemeral=True)
        if emoji.lower() == 'skip': emoji = None

        role_input = await self._prompt(inter, 'Please mention one or more staff roles to ping, separated by spaces (e.g., `@Ticket Support @Moderator`), or type `none`.', followup=True)
        if not role_input: return await inter.followup.send("Timed out.", ephemeral=True)
        
        role_ids = []
        if role_input.lower() != 'none':
            role_mentions = re.findall(r'<@&(\d+)>', role_input)
            for role_id_str in role_mentions:
                role_ids.append(int(role_id_str))
        
        self.categories.append({
            "name": cat_name, 
            "emoji": emoji,
            "notified_roles": ",".join(map(str, role_ids)) if role_ids else None, 
            "button_style": discord.ButtonStyle.secondary.value
        })
        self._update_remove_select()
        await self.message.edit(view=from_embed(self._update_embed(), self))
        await inter.followup.send(f"Category '{cat_name}' added/removed successfully.", ephemeral=True)

    async def _remove_category(self, inter, value):
        if value == "placeholder": return await inter.response.defer()
        try:
            idx = int(value)
            if 0 <= idx < len(self.categories):
                self.categories.pop(idx)
        except ValueError:
            pass
        self._update_remove_select()
        await self.message.edit(view=from_embed(self._update_embed(), self))
        await inter.response.defer()

    async def _finish_setup(self, inter):
        if not self.categories: return await inter.response.send_message("Add at least one category.", ephemeral=True)
        await inter.response.defer()
        db, guild_id = self.cog.db, self.ctx.guild.id
        db.execute("DELETE FROM ticket_categories WHERE guild_id = ?", (guild_id,))
        for cat in self.categories:
            try: cat_ch = await self.ctx.guild.create_category(f"{cat['name']} Tickets", overwrites={self.ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)})
            except: return await inter.followup.send(f"Can't create category for `{cat['name']}`.", ephemeral=True)
            db.execute('INSERT INTO ticket_categories (guild_id, name, emoji, notified_roles, button_style, discord_category_id) VALUES (?,?,?,?,?,?)', (guild_id,cat['name'],cat['emoji'],cat['notified_roles'],cat['button_style'],cat_ch.id))
        config = db.fetchone("SELECT * FROM guild_configs WHERE guild_id=?", (guild_id,))
        panel_ch = self.ctx.guild.get_channel(config['panel_channel_id'])
        panel_embed = discord.Embed(title=config['embed_title'], description=config['embed_description'], color=config['embed_color'])
        if img_url := config['embed_image_url']: panel_embed.set_image(url=img_url)
        if thumb_url := config['embed_thumbnail_url']: panel_embed.set_thumbnail(url=thumb_url)
        final_view = self.cog.create_panel_view(guild_id)
        msg = await panel_ch.send(view=from_embed(panel_embed, final_view))
        db.execute("UPDATE guild_configs SET panel_message_id = ? WHERE guild_id = ?", (msg.id, guild_id))
        await self.message.edit(content=f"{SUCCESS_EMOJI} Setup complete! Panel sent to {panel_ch.mention}.", view=None, embed=None)
        self.stop()

class TicketCog(commands.Cog, name="Ticket System"):
    def __init__(self, bot):
        self.bot, self.db = bot, TicketDatabase(DB_PATH)
        self._ai_inflight: set[int] = set()
        self._creation_locks = {}
        self._action_locks = {}
        self.ticket_automations.start()
        asyncio.create_task(ticket_ai.refresh_allowed_guilds())
        asyncio.create_task(self.load_persistent_views())
        self.purge_expired_transcripts.start()

    @tasks.loop(hours=6)
    async def purge_expired_transcripts(self):
        self.db.execute(
            "DELETE FROM ticket_transcripts WHERE expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )

    @purge_expired_transcripts.before_loop
    async def before_transcript_purge(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def ticket_automations(self):
        from cogs.commands.ticket_workflow import tick
        await tick(self)

    @ticket_automations.before_loop
    async def before_ticket_automations(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener('on_message')
    async def workflow_message(self, message):
        from cogs.commands.ticket_workflow import activity
        await activity(self, message)

    @commands.Cog.listener('on_member_remove')
    async def workflow_member_leave(self, member):
        from cogs.commands.ticket_workflow import member_leave
        await member_leave(self, member)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Answer the ticket creator until a team member claims the ticket."""
        if (
            not message.guild
            or message.author.bot
            or not message.content.strip()
            or message.channel.id in self._ai_inflight
            or not ticket_ai.pilot_available(message.guild.id)
            or not ticket_ai.api_key_configured()
        ):
            return

        ticket = self.db.fetchone(
            "SELECT creator_id, category_db_id, is_claimed, closed_at FROM open_tickets WHERE channel_id=?",
            (message.channel.id,),
        )
        if (
            not ticket
            or ticket["closed_at"] is not None
            or ticket["is_claimed"]
            or int(ticket["creator_id"]) != message.author.id
            or not ticket_ai.may_answer(self.db.conn, message.channel.id)
        ):
            return

        category_id = int(ticket["category_db_id"] or 0)
        config = self.db.fetchone(
            "SELECT s.enabled, s.fallback_text, c.enabled AS category_enabled, c.instructions, k.content"
            " FROM ticket_ai_settings s JOIN ticket_ai_knowledge k ON k.guild_id=s.guild_id"
            " LEFT JOIN ticket_ai_categories c ON c.guild_id=s.guild_id AND c.category_id=?"
            " WHERE s.guild_id=?",
            (category_id, message.guild.id),
        )
        if not config or not config["enabled"] or not config["category_enabled"]:
            return

        self._ai_inflight.add(message.channel.id)
        try:
            excerpts = ticket_ai.matching_context(message.content, config["content"])
            async with message.channel.typing():
                answer = await ticket_ai.grounded_answer(
                    message.content, excerpts, config["instructions"] or ""
                )

            # Claim can happen while the Groq request is running. Re-read immediately
            # before sending so the team always wins that race.
            current = self.db.fetchone(
                "SELECT is_claimed, closed_at FROM open_tickets WHERE channel_id=?",
                (message.channel.id,),
            )
            if not current or current["is_claimed"] or current["closed_at"] is not None:
                return

            if answer:
                view = Panel(
                    f"{ZMODULE} KI-Ticketassistent",
                    answer,
                    "*Automatische Antwort aus der Wissensdatenbank dieses Servers.*",
                    tone="info",
                )
                await message.channel.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                category = self.db.fetchone(
                    "SELECT notified_roles FROM ticket_categories WHERE category_id=? AND guild_id=?",
                    (category_id, message.guild.id),
                )
                role_ids = [
                    value for value in str((category["notified_roles"] if category else "") or "").split(",")
                    if value.isdigit()
                ]
                pings = " ".join(f"<@&{role_id}>" for role_id in role_ids)
                body = (config["fallback_text"] or "Dazu habe ich leider keine verlässliche Information gefunden.").strip()
                if pings:
                    body += f"\n\n{pings}"
                view = Panel(
                    f"{MESSAGE} Team wird benötigt",
                    body,
                    "*Die KI hat keine ausreichend sichere Antwort gefunden.*",
                    tone="warning",
                )
                await message.channel.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, users=False, roles=True, replied_user=False
                    ),
                )
            ticket_ai.record_answer(self.db.conn, message.channel.id, escalated=not bool(answer))
        except Exception as exc:
            print(f"[ticket-ai] Message handling failed: {type(exc).__name__}: {exc}")
        finally:
            self._ai_inflight.discard(message.channel.id)

    async def load_persistent_views(self):
        await self.bot.wait_until_ready()
        # Legacy single-panel rows.
        for config in self.db.fetchall("SELECT guild_id, panel_message_id FROM guild_configs WHERE panel_message_id IS NOT NULL"):
            if view := self.create_panel_view(config['guild_id']): self.bot.add_view(view, message_id=config['panel_message_id'])

        # Panels created through the dashboard. Their buttons are dispatched
        # by the on_interaction listener below (custom_id starts with
        # create_ticket_), so an empty persistent view is enough to keep
        # Discord delivering the interaction after a restart.
        try:
            panels = self.db.fetchall(
                "SELECT panel_id, guild_id, message_id FROM ticket_panels"
                " WHERE message_id IS NOT NULL"
            )
        except Exception:
            panels = []  # table not created yet on a fresh install

        for panel in panels:
            view = self.create_panel_view(panel['guild_id'], panel['panel_id'])
            if view:
                self.bot.add_view(view, message_id=panel['message_id'])

        # Die Knoepfe IN den Tickets brauchen hier nichts.
        #
        # Sie werden vom on_interaction-Listener weiter unten bedient.
        # `add_view` waere hier der naheliegende Weg und genau deshalb
        # falsch: die IDs (`t_lock`, `c_reopen`, ...) sind fuer alle
        # Tickets gleich, und ein View ohne message_id landet im
        # ViewStore unter dem Schluessel None. Der zweite ueberschreibt
        # damit den ersten, der dritte den zweiten -- am Ende reagiert
        # genau ein Ticket, und zwar ein zufaelliges. Nachgeprueft in
        # discord/ui/view.py: `dispatch_info = self._views.get(message_id)`.
        #
        # Die Nachrichten-ID, mit der es ginge, steht nirgends: die
        # Begruessung im Ticket wird gesendet und nicht gespeichert.

        # Und den Zaehler gegen die echten Kanaele abgleichen.
        await self.reconcile_counts()

    def create_panel_view(self, guild_id, panel_id=None):
        """
        Build the view for a panel.

        panel_id selects one of the dashboard panels; without it the legacy
        single-panel configuration is used, which is what the old setup
        command still writes.
        """
        if panel_id is not None:
            try:
                config = self.db.fetchone(
                    "SELECT panel_type, select_placeholder FROM ticket_panels WHERE panel_id=?",
                    (panel_id,),
                )
                categories = self.db.fetchall(
                    "SELECT * FROM ticket_categories WHERE guild_id=? AND panel_id=?",
                    (guild_id, panel_id),
                )
            except Exception:
                return None
        else:
            config = self.db.fetchone("SELECT panel_type FROM guild_configs WHERE guild_id=?", (guild_id,))
            categories = self.db.fetchall("SELECT * FROM ticket_categories WHERE guild_id=?", (guild_id,))
        categories = [c for c in categories if self.preferences(guild_id,c['category_id'])['active']]
        if not config or not categories: return None
        view_class = TicketPanelSelect if config['panel_type'] == 'dropdown' else TicketPanelButtons
        view = view_class(self)
        if config['panel_type'] == 'dropdown':
            view.children[0].options = [discord.SelectOption(label=c['name'], value=str(c['category_id']), emoji=c['emoji'] or None) for c in categories]
            if panel_id is not None:
                placeholder = 'Wähle eine Kategorie…'
                if feature_gates.can_configure_premium_guild(guild_id):
                    placeholder = str(config['select_placeholder'] or '').strip()[:150] or placeholder
                view.children[0].placeholder = placeholder
        else:
            for c in categories: view.add_item(discord.ui.Button(label=c['name'], style=discord.ButtonStyle(c['button_style']), emoji=c['emoji'] or None, custom_id=f"create_ticket_{c['category_id']}"))
        return view

    def cog_unload(self):
        self.ticket_automations.cancel()
        self.purge_expired_transcripts.cancel()
        self.db.close()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """
        Ein Ticketkanal wurde geloescht -- aufraeumen.

        Vorher sank ``user_ticket_counts`` nur beim Schliessen ueber den
        Knopf. Wer den Kanal von Hand loescht, liess den Zaehler stehen:
        nach drei solchen Tickets meldete der Bot "3 von 3 offen",
        obwohl es keinen einzigen Kanal mehr gab, und niemand konnte ein
        neues aufmachen.

        Dass das jemand tun musste, lag am Fehler daneben: die Knoepfe
        im Ticket funktionierten nach einem Deploy nicht mehr. Die
        Ursache ist behoben, aber der falsche Stand bliebe sonst fuer
        immer stehen.
        """
        ticket = self.db.fetchone(
            "SELECT creator_id, closed_at FROM open_tickets WHERE channel_id=?",
            (channel.id,),
        )
        if ticket is None:
            return

        # Nur zaehlen, was noch als offen galt. Ein geschlossenes Ticket
        # hat den Zaehler bereits gesenkt -- sonst ginge er ins Minus,
        # beziehungsweise MAX(0, ...) verschluckte einen echten Eintrag.
        if not ticket["closed_at"]:
            self.db.execute(
                "UPDATE user_ticket_counts SET ticket_count=MAX(0, ticket_count-1)"
                " WHERE guild_id=? AND user_id=?",
                (channel.guild.id, ticket["creator_id"]),
            )

        self.db.execute("DELETE FROM open_tickets WHERE channel_id=?", (channel.id,))

        try:
            from utils import ticket_notify
            await ticket_notify.forget(channel.id)
        except Exception:
            pass

    async def reconcile_counts(self):
        """
        Den Zaehler gegen die Wirklichkeit abgleichen.

        Laeuft einmal beim Start. Wer schon einen falschen Stand hat --
        etwa weil vor diesem Fix ein Kanal von Hand geloescht wurde --
        kommt sonst nie wieder auf null. Der Listener oben verhindert
        nur, dass es erneut passiert.
        """
        try:
            tickets = self.db.fetchall(
                "SELECT channel_id, guild_id, creator_id FROM open_tickets"
                " WHERE closed_at IS NULL"
            )
        except Exception:
            return

        verwaist = []
        for ticket in tickets:
            if self.bot.get_channel(ticket["channel_id"]) is None:
                verwaist.append(ticket)

        for ticket in verwaist:
            self.db.execute(
                "UPDATE user_ticket_counts SET ticket_count=MAX(0, ticket_count-1)"
                " WHERE guild_id=? AND user_id=?",
                (ticket["guild_id"], ticket["creator_id"]),
            )
            self.db.execute(
                "DELETE FROM open_tickets WHERE channel_id=?",
                (ticket["channel_id"],),
            )

        if verwaist:
            print(f"[tickets] {len(verwaist)} verwaiste Tickets aufgeraeumt.")

    # Welcher Knopf im Ticket ruft welche Methode auf. Die Zuordnung
    # steht hier, damit der Listener unten nach einem Neustart genau das
    # tun kann, was der View im laufenden Betrieb taete.
    TICKET_BUTTONS = {
        "t_lock": ("open", "b_lock"),
        "t_unlock": ("open", "b_unlock"),
        "t_claim": ("open", "b_claim"),
        "t_unclaim": ("open", "b_unclaim"),
        "t_request": ("open", "b_request"),
        "t_confirm": ("open", "b_confirm"),
        "t_cancel": ("open", "b_cancel"),
        "t_tools": ("open", "b_tools"),
        "t_close": ("open", "b_close"),
        "c_reopen": ("closed", "b_reopen"),
        "c_delete": ("closed", "b_delete"),
    }

    @commands.Cog.listener()
    async def on_interaction(self, inter):
        if inter.type != discord.InteractionType.component:
            return
        cid = inter.data.get("custom_id", "")
        if getattr(inter,'extras',{}).get('university_module_blocked'):
            return
        store = getattr(getattr(getattr(self,'bot',None),'_connection',None),'_view_store',None)
        if store is not None:
            key=((inter.data or {}).get('component_type'),cid)
            message_id=getattr(getattr(inter,'message',None),'id',None)
            item=store._views.get(message_id,{}).get(key) or store._views.get(None,{}).get(key)
            if item is not None and getattr(item.callback,'_university_ticket_action',False):
                return
        if cid.startswith('ticket_rating_') and not inter.response.is_done():
            from cogs.commands.ticket_workflow import RatingModal
            suffix = cid.removeprefix('ticket_rating_')
            if suffix.isdigit():
                request = self.db.fetchone('SELECT snapshot FROM ticket_feedback_requests WHERE channel_id=?', (int(suffix),))
                ticket = json.loads(request['snapshot']) if request else self.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?', (int(suffix),))
                if ticket and ticket['creator_id'] == inter.user.id and ticket['closed_at']:
                    return await inter.response.send_modal(RatingModal(self, ticket))
            return await inter.response.send_message(view=Panel(f'{ERROR_EMOJI} Rating unavailable', 'Only the original ticket creator can rate a closed ticket.'), ephemeral=True)

        # Die Knoepfe IM Ticket, nach einem Neustart.
        #
        # Vorher fing dieser Listener nur `create_ticket_` ab. Die
        # Knoepfe im Ticket selbst haengen an einem View, den es nach
        # einem Deploy nicht mehr gibt -- also passierte beim Klicken
        # gar nichts, und das Ticket liess sich nur noch von Hand
        # loeschen. Genau das hat dann den Zaehler ruiniert.
        #
        # Hier wird der View neu gebaut. Die Kanal-ID steht in der
        # Interaktion, die Kategorie in der Datenbank -- mehr braucht er
        # nicht.
        if cid in self.TICKET_BUTTONS:
            from utils import guild_modules, interaction_notices
            if not guild_modules.is_enabled(inter.guild_id, 'tickets'):
                if not inter.response.is_done():
                    await interaction_notices.notify(inter, 'tickets')
                return
            # Hat schon jemand geantwortet, laeuft der urspruengliche
            # View noch: dann nicht dazwischenfunken.
            if inter.response.is_done():
                return
            store = getattr(getattr(getattr(self,'bot',None), '_connection', None), '_view_store', None)
            if store is not None:
                message_id = getattr(getattr(inter, 'message', None), 'id', None)
                key = ((inter.data or {}).get('component_type'), cid)
                item = store._views.get(message_id, {}).get(key) or store._views.get(None, {}).get(key)
                if item is not None and getattr(item.callback, '_university_ticket_action', False):
                    return  # The registered callback owns permission checks and execution.
            return await self._dispatch_ticket_button(inter, cid)

        if not cid.startswith("create_ticket_"):
            return

        # Dropdown panels send a fixed custom_id and carry the chosen
        # category in `values`. Without this branch int("select") raised and
        # the dropdown did nothing at all.
        if cid == "create_ticket_select":
            values = inter.data.get("values") or []
            if not values or not str(values[0]).isdigit():
                return
            return await self.create_ticket_flow(inter, int(values[0]))

        suffix = cid.split("_")[-1]
        if suffix.isdigit():
            await self.create_ticket_flow(inter, int(suffix))

    async def _dispatch_ticket_button(self, inter, cid):
        """
        Einen Ticket-Knopf bedienen, dessen View nicht mehr existiert.

        Der View wird frisch gebaut und seine Methode aufgerufen -- also
        genau derselbe Weg wie im laufenden Betrieb. Eine zweite Fassung
        der Logik waere die Alternative gewesen und genau deshalb
        falsch: sie waere beim naechsten Umbau vergessen worden.
        """
        art, methode = self.TICKET_BUTTONS[cid]

        ticket = self.db.fetchone(
            "SELECT channel_id, category_db_id, closed_at FROM open_tickets"
            " WHERE channel_id=?",
            (inter.channel_id,),
        )
        if ticket is None:
            return await inter.response.send_message(
                "Dieses Ticket steht nicht mehr in der Datenbank. "
                "Der Kanal kann gelöscht werden.",
                ephemeral=True,
            )

        # Ein geschlossenes Ticket hat andere Knoepfe als ein offenes.
        # Passt beides nicht zusammen, steht eine alte Nachricht im
        # Kanal -- dann lieber sagen, was los ist, als etwas Falsches
        # zu tun.
        geschlossen = bool(ticket["closed_at"])
        if (art == "closed") != geschlossen:
            return await inter.response.send_message(
                "Diese Nachricht gehört zu einem anderen Stand des Tickets. "
                "Bitte die neueste Nachricht im Kanal benutzen.",
                ephemeral=True,
            )

        if geschlossen:
            view = ClosedTicketActionsView(
                self, ticket["channel_id"], ticket["category_db_id"]
            )
        else:
            view = TicketActionsView(
                self, ticket["channel_id"], ticket["category_db_id"]
            )

        # Die Rollenpruefung des Views gilt weiter -- sonst duerfte nach
        # einem Neustart jeder das Ticket schliessen.
        if not await view.interaction_check(inter):
            return

        knopf = getattr(view, methode, None)
        if knopf is None:
            return

        # `view.b_lock` ist ein Button-Objekt, keine Methode -- der
        # Dekorator ersetzt sie. Die eigentliche Funktion haengt an
        # `.callback` und nimmt nur die Interaktion; sie ist bereits an
        # den View gebunden. Nachgeprueft mit inspect.signature.
        await knopf.callback(inter)

    def _ticket_panel_config(self, guild_id, cat_info):
        config = {
            "title": "Ticket #{ticket_number}",
            "message": (
                "Welcome to your ticket, {user}.\n"
                "Our support team will reply as soon as possible.\n\n"
                "**Describe your request in detail** so we can help you."
            ),
            "created_message": "Your ticket is open: {channel}",
            "questions": [],
        }
        panel_id = cat_info["panel_id"] if "panel_id" in cat_info.keys() else None
        if not panel_id or not feature_gates.can_configure_premium_guild(guild_id):
            return config
        try:
            row = self.db.fetchone(
                "SELECT ticket_welcome_title, ticket_welcome_message,"
                " ticket_created_message, ticket_questions FROM ticket_panels"
                " WHERE panel_id=? AND guild_id=?",
                (panel_id, guild_id),
            )
            if not row:
                return config
            config["title"] = str(row["ticket_welcome_title"] or config["title"])[:256]
            config["message"] = str(row["ticket_welcome_message"] or config["message"])[:4000]
            # Premium categories may override the panel-wide greeting. Empty
            # fields intentionally inherit the advanced panel message.
            if "ticket_welcome_title" in cat_info.keys() and str(
                cat_info["ticket_welcome_title"] or ""
            ).strip():
                config["title"] = str(cat_info["ticket_welcome_title"]).strip()[:256]
            if "ticket_welcome_message" in cat_info.keys() and str(
                cat_info["ticket_welcome_message"] or ""
            ).strip():
                config["message"] = str(cat_info["ticket_welcome_message"]).strip()[:4000]
            config["created_message"] = str(
                row["ticket_created_message"] or config["created_message"]
            )[:1900]
            raw_questions = json.loads(row["ticket_questions"] or "[]")
            if isinstance(raw_questions, list):
                config["questions"] = [
                    question for question in raw_questions[:5]
                    if isinstance(question, dict)
                    and str(question.get("label") or "").strip()
                ]
        except (KeyError, TypeError, ValueError, sqlite3.Error):
            pass
        return config

    def preferences(self, guild_id, category_id):
        cat = self.db.fetchone('SELECT panel_id FROM ticket_categories WHERE guild_id=? AND category_id=?', (guild_id, category_id))
        return ticket_settings.sync_settings(self.db, guild_id, cat['panel_id'] if cat else 0, category_id)

    async def create_ticket_flow(self, inter, cat_id, answers=None, creator_id=None):
        from utils import guild_modules,interaction_notices
        if getattr(inter,'extras',{}).get('university_module_blocked'):
            return
        if not guild_modules.is_enabled(inter.guild.id,'tickets'):
            if not inter.response.is_done():await interaction_notices.notify(inter,'tickets')
            return
        key = (inter.guild.id, creator_id or inter.user.id)
        lock = self._creation_locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            return await inter.response.send_message(view=Panel(f'{ERROR_EMOJI} Please wait', 'Your ticket is already being created.'), ephemeral=True)
        async with lock:
            return await self._create_ticket_flow(inter, cat_id, answers, creator_id)

    async def _create_ticket_flow(self, inter, cat_id, answers=None, creator_id=None):
        guild, user = inter.guild, inter.user
        cat_info = self.db.fetchone("SELECT * FROM ticket_categories WHERE category_id=?", (cat_id,))
        disc_cat = guild.get_channel(cat_info['discord_category_id']) if cat_info else None
        if not cat_info or cat_info['guild_id'] != guild.id or not disc_cat:
            if not inter.response.is_done():
                return await inter.response.send_message(
                    "Diese Ticket-Kategorie wurde gelöscht oder ist falsch eingerichtet.",
                    ephemeral=True,
                )
            return await inter.followup.send(
                "Diese Ticket-Kategorie wurde gelöscht oder ist falsch eingerichtet.",
                ephemeral=True,
            )

        preferences = self.preferences(guild.id, cat_id)
        if creator_id and creator_id != inter.user.id:
            from cogs.commands.ticket_workflow import is_staff
            if not preferences['allow_on_behalf'] or not is_staff(self,inter.user,cat_id):
                return await inter.response.send_message(view=Panel(f'{ERROR_EMOJI} Staff action','This category does not allow you to open tickets for other members.'),ephemeral=True)
            user=guild.get_member(creator_id)
            if user is None:
                return await inter.response.send_message(view=Panel('Member unavailable','The selected member is no longer on the server.'),ephemeral=True)
        if not preferences['active']:
            return await inter.response.send_message(view=Panel(f'{ERROR_EMOJI} Category unavailable', 'This ticket category has been disabled. Please contact an administrator.'), ephemeral=True)
        panel_config = self._ticket_panel_config(guild.id, cat_info)
        panel_config['creator_id'] = user.id
        # Auswahl und Grenze liegen im Panel-Speicher, damit die
        # Vorschau im Dashboard exakt dieselben Fragen zeigt.
        from api import ticket_panels as regeln

        panel_config["questions"] = regeln.fragen_fuer_kategorie(
            panel_config["questions"], cat_id
        )
        if preferences['opening_questions'] is not None and feature_gates.can_configure_premium_guild(guild.id):
            panel_config['questions'] = preferences['opening_questions']
        if answers is None and panel_config["questions"]:
            return await inter.response.send_modal(
                TicketQuestionsModal(self, cat_id, panel_config)
            )
        if answers is not None and not panel_config["questions"]:
            answers = []
        for answer in answers or []:
            if answer.get("type") != "image":
                continue
            invalid = [
                attachment for attachment in answer.get("attachments", [])
                if not str(getattr(attachment, "content_type", "") or "").startswith("image/")
            ]
            if invalid:
                return await inter.response.send_message(
                    "Bitte lade bei Bildfragen ausschließlich Bilddateien hoch.",
                    ephemeral=True,
                )

        await inter.response.defer(ephemeral=True)
        count = self.db.fetchone(
            "SELECT COUNT(*) AS ticket_count FROM open_tickets WHERE guild_id=? AND creator_id=? AND closed_at IS NULL",
            (guild.id, user.id),
        )
        if (
            count
            and preferences['ticket_limit'] > 0
            and count['ticket_count'] >= preferences['ticket_limit']
            and not dashboard_roles.has_owner_privilege(user.id, "limits_bypass")
        ):
            return await inter.followup.send(
                f"You have reached the max of {preferences['ticket_limit']} open tickets.",
                ephemeral=True,
            )
        
        t_num = (self.db.fetchone("SELECT MAX(ticket_number) as n FROM open_tickets WHERE guild_id=?", (guild.id,))['n'] or 0) + 1
        
        # Die Rechte im frischen Ticket.
        #
        # Vorher stand hier ueberall nur `view_channel=True` -- also
        # "darf den Kanal sehen". Ueber das Schreiben sagte das nichts,
        # und ein PermissionOverwrite kennt drei Zustaende: ja, nein und
        # "nichts gesagt". Bei "nichts gesagt" gilt weiter, was die
        # Kategorie oder @everyone vorgibt, und die Ticket-Kategorie
        # wird mit `view_channel=False` angelegt. Ergebnis: der Ersteller
        # sah sein eigenes Ticket und konnte nichts hineinschreiben.
        #
        # Deshalb jetzt ausdruecklich. `read_message_history` gehoert
        # dazu, sonst ist der Kanal beim Oeffnen leer, und `attach_files`
        # auch -- ein Screenshot ist bei einem Ticket der Normalfall.
        teilnehmer_rechte = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            add_reactions=True,
        )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: teilnehmer_rechte,
            # Ohne send_messages scheitert schon die Begruessung, die der
            # Bot als Erstes in den Kanal schreibt.
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }

        pings = [user.mention]
        ping_roles = []
        from cogs.commands.ticket_workflow import staff_ids
        team_ids = staff_ids(self, guild.id, cat_id)
        if team_ids:
            for role_id in team_ids:
                if role := guild.get_role(int(role_id)):
                    ping_roles.append(role)
                    # Das Team braucht dieselben Rechte wie der Ersteller,
                    # sonst kann es nur zusehen.
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True,
                        add_reactions=True,
                        manage_messages=True,
                    )
                    if preferences['ping_team']:
                        pings.append(role.mention)
        
        naming = dict(prefix=preferences['prefix'],ticket_number=f'{t_num:04d}',username=user.name.lower(),user_id=str(user.id),display_name=user.display_name,case_id=f'T-{guild.id}-{t_num:04d}')
        name = preferences['name_format']
        for key, value in naming.items():
            name = name.replace('{'+key+'}', str(value))
        name = re.sub(r'[^\w-]', '-', name.lower()).strip('-')[:100] or f'ticket-{t_num:04d}'
        try: ch = await disc_cat.create_text_channel(name=name, overwrites=overwrites)
        except: return await inter.followup.send("I lack permissions to create a channel.", ephemeral=True)
        
        self.db.execute('INSERT INTO open_tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)', (ch.id,t_num,guild.id,user.id,cat_id,datetime.now().isoformat(),None,None,False,False,None))
        self.db.execute('INSERT OR REPLACE INTO ticket_workflow(channel_id,last_activity,priority) VALUES(?,?,?)', (ch.id,time.time(),preferences['priority']))
        self.db.execute('INSERT INTO user_ticket_counts VALUES (?,?,1) ON CONFLICT(guild_id,user_id) DO UPDATE SET ticket_count=ticket_count+1', (guild.id,user.id))
        await log_ticket_action(self.db, guild, user, "Ticket Created", f"Ticket {ch.mention} by {user.mention} (Category: {cat_info['name']}).")

        # Das Ticket bei den Benachrichtigungen anmelden. Ohne diese
        # Zeile kennt der Zustand den Ersteller nicht und der erste
        # Hinweis ginge an niemanden.
        try:
            await ticket_notify.register_ticket(ch.id, guild.id, user.id)
        except Exception:
            # Eine fehlende Benachrichtigung darf kein Ticket verhindern.
            pass
        
        # Die Begruessung im frischen Ticket.
        #
        # Zwei Fehler steckten hier, und zusammen sorgten sie dafuer,
        # dass der Kanal leer blieb:
        #
        #  * ``set_image(TICKET_CHANNEL_IMAGE_URL)`` -- eine
        #    Discord-CDN-Adresse mit abgelaufener Signatur. Sie liefert
        #    403, und Discord lehnt die ganze Nachricht ab.
        #  * ``content=`` zusammen mit einer Components-V2-View. Mit
        #    dem V2-Flag gibt es kein content-Feld mehr; Discord
        #    antwortet mit 50035.
        #
        # Die Erwaehnungen brauchen aber ein content-Feld, sonst
        # benachrichtigt niemand das Team. Also zwei Nachrichten: die
        # Pings als reiner Text, danach die Karte.
        # Die Woerter selbst stehen im Panel-Speicher, der Cog nennt nur
        # die Werte. Welche Marker es sind, prueft
        # tests/test_ticket_erweitert.py — ein assert hier ginge bei
        # ``python -O`` verloren und wuerde ausgerechnet das Oeffnen
        # eines Tickets zum Absturz bringen.
        replacements = {
            "ticket_number": f"{t_num:04d}",
            "user": user.mention,
            "category": str(cat_info["name"]),
            "server": guild.name,
            "channel": ch.mention,
        }
        def render_template(value):
            return regeln.setze_woerter(value, **replacements)

        full_message = render_template(panel_config["message"])[:4096]
        ticket_embed = discord.Embed(
            title=render_template(panel_config["title"])[:256],
            description=full_message[:3000],
            color=EMBED_COLOR,
        )
        ticket_embed.add_field(name='Case ID', value=f'`T-{guild.id}-{t_num:04d}`', inline=False)
        ticket_embed.add_field(name='Category', value=cat_info['name'], inline=False)
        ticket_embed.add_field(name='Creator', value=user.mention, inline=False)
        ticket_embed.add_field(name='Priority', value=preferences['priority'].title(), inline=False)
        if not ticket_settings.is_open(preferences):
            ticket_embed.add_field(name='Outside support hours', value=f"Your ticket is open. Our team will reply during its support hours ({preferences['timezone']}).", inline=False)
        if preferences['welcome_image_url']:
            ticket_embed.set_image(url=preferences['welcome_image_url'])
        if preferences['welcome_thumbnail_url']:
            ticket_embed.set_thumbnail(url=preferences['welcome_thumbnail_url'])
        ticket_embed.set_footer(text=f"University Bot · {cat_info['name']}")

        try:
            await ch.send(
                " ".join(pings),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    users=[user],
                    roles=ping_roles,
                    replied_user=False,
                ),
            )
        except discord.HTTPException:
            # Ohne Erwaehnung geht es zur Not auch -- die Karte ist
            # wichtiger als der Ping.
            pass

        await ch.send(view=from_embed(ticket_embed, TicketActionsView(self, ch.id, cat_id)))
        if len(full_message) > 3000:
            await ch.send(view=Panel('Support request', full_message[3000:]))
        from cogs.commands.ticket_workflow import send_answers
        if answers:
            await send_answers(ch, 'Opening form', answers)

        created_message = render_template(panel_config["created_message"])[:1900]
        await inter.followup.send(view=Panel(f'{SUCCESS_EMOJI} Your ticket is ready', created_message,
            buttons=[discord.ui.Button(label='Go to ticket', url=ch.jump_url, emoji=MESSAGE)]), ephemeral=True)

    @commands.hybrid_group(name="ticket", description="Main command group for the ticket system.")
    @commands.guild_only()
    async def ticket(self, ctx):
        if ctx.invoked_subcommand is None: await ctx.send_help(ctx.command)

    # `ticket setup` gibt es nicht mehr -- auf Wunsch entfernt.
    #
    # Das Ticket-System wird im Dashboard eingerichtet (Reiter
    # "Tickets"): dort lassen sich Kategorien, Rechte und das Panel
    # zusammenklicken und jederzeit wieder ändern. Der Chat-Assistent
    # konnte das nur einmal am Stück und hatte kein Zurück.
    #
    # `EmbedEditorView` (oben) hatte hier ihren einzigen Aufrufer und
    # ist damit tot. Sie bleibt trotzdem stehen: das Dashboard postet
    # Panels über /tickets/{guild}/panels/{id}/send und baut sie
    # selbst, aber die Klasse ist mehrere hundert Zeilen groß, und sie
    # im selben Zug zu löschen wäre eine zweite Änderung in einem
    # Commit, der eigentlich nur einen Befehl entfernt.

    @ticket.command(name='create', description='Open a ticket for yourself or another member.')
    @commands.guild_only()
    async def create(self, ctx, category_id: int, member: discord.Member | None = None):
        if not ctx.interaction:
            return await ctx.send(view=Panel(f'{MESSAGE} Open a ticket', 'Use /ticket create to choose a category and open a ticket.'))
        await self.create_ticket_flow(ctx.interaction,category_id,creator_id=member.id if member else None)

    @create.autocomplete('category_id')
    async def create_category_autocomplete(self, interaction, current):
        if interaction.guild_id is None:return []
        query=str(current).lower()
        rows=self.db.fetchall('SELECT category_id,name FROM ticket_categories WHERE guild_id=? ORDER BY category_id',(interaction.guild_id,))
        return [app_commands.Choice(name=row['name'][:100],value=row['category_id']) for row in rows if (query in row['name'].lower() or query in str(row['category_id'])) and self.preferences(interaction.guild_id,row['category_id'])['active']][:25]

    @ticket.command(name="close", description="Close the current ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def close(self, ctx): await self._dispatch_action(ctx, "close")
    
    @ticket.command(name="lock", description="Lock the ticket, preventing the user from sending messages.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx): await self._dispatch_action(ctx, "lock")
    
    @ticket.command(name="unlock", description="Unlock the ticket, allowing the user to send messages again.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx): await self._dispatch_action(ctx, "unlock")
    
    @ticket.command(name="claim", description="Claim the ticket to notify others that you are handling it.")
    @commands.has_permissions(manage_channels=True)
    async def claim(self, ctx): await self._dispatch_action(ctx, "claim")

class TicketQuestionsModal(discord.ui.Modal):
    def __init__(self, cog, category_id, panel_config):
        super().__init__(title='Open a ticket', timeout=900)
        from cogs.commands.ticket_workflow import add_fields
        self.cog, self.category_id = cog, category_id
        self.creator_id = panel_config.get('creator_id')
        self.inputs = add_fields(self, panel_config['questions'])

    async def on_submit(self, interaction):
        from cogs.commands.ticket_workflow import form_answers
        try:
            answers = form_answers(self.inputs)
        except ValueError as exc:
            return await interaction.response.send_message(view=Panel('Check your answers',str(exc)),ephemeral=True)
        await self.cog.create_ticket_flow(interaction,self.category_id,answers=answers,creator_id=self.creator_id)


class TicketPanelSelect(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog=cog
        original=self.children[0].callback
        async def callback(interaction):
            await original(interaction)
        callback._university_ticket_action=True
        self.children[0].callback=callback
    @discord.ui.select(placeholder="Select a category to open a ticket...", custom_id="ticket_panel_select")
    async def select_ticket(self, inter, select): await self.cog.create_ticket_flow(inter, int(select.values[0]))

class TicketPanelButtons(discord.ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog

class TicketActionsView(discord.ui.View):
    def __init__(self, cog, ch_id, cat_id):
        super().__init__(timeout=None)
        self.cog, self.ch_id, self.cat_id = cog, ch_id, cat_id
        self.remove_item(self.b_confirm)
        self.remove_item(self.b_cancel)
        from cogs.commands.ticket_workflow import protect_actions
        protect_actions(self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        ticket = self.cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?', (self.ch_id,))
        if not ticket or ticket['closed_at']:
            await interaction.response.send_message(view=Panel(f'{ERROR_EMOJI} Ticket unavailable', 'This ticket is closed or no longer exists.'), ephemeral=True)
            return False
        preferences = self.cog.preferences(interaction.guild.id, self.cat_id)
        cat = self.cog.db.fetchone('SELECT notified_roles FROM ticket_categories WHERE category_id=?', (self.cat_id,))
        from cogs.commands.ticket_workflow import staff_ids
        role_ids = staff_ids(self.cog, interaction.guild.id, self.cat_id)
        staff = interaction.user.guild_permissions.administrator or bool(role_ids.intersection(r.id for r in interaction.user.roles))
        creator = ticket['creator_id'] == interaction.user.id
        operation = (interaction.data or {}).get('custom_id', '')
        allowed = staff or (creator and (operation in ('t_request','t_confirm','t_cancel') or (operation == 't_close' and not preferences['staff_only_close']) or (operation == 't_tools' and preferences['allow_participants'])))
        if not allowed:
            await interaction.response.send_message(view=Panel(f'{ERROR_EMOJI} Staff action', 'Please ask the support team to perform this action.'), ephemeral=True)
        return allowed

    @discord.ui.button(label="Lock", emoji=LOCK_EMOJI, custom_id="t_lock", style=discord.ButtonStyle.secondary)
    async def b_lock(self, i, b):
        t = self.cog.db.fetchone("SELECT * FROM open_tickets WHERE channel_id=?", (self.ch_id,))
        if t['is_locked']: return await i.response.send_message("This ticket is already locked.", ephemeral=True)
        creator = i.guild.get_member(t['creator_id'])
        if creator: await i.channel.set_permissions(creator, send_messages=False)
        self.cog.db.execute("UPDATE open_tickets SET is_locked=1 WHERE channel_id=?", (self.ch_id,))
        await i.response.send_message(f"{LOCK_EMOJI} Ticket locked by {i.user.mention}.")
        await log_ticket_action(self.cog.db, i.guild, i.user, "Locked", f"{i.channel.mention}")

    @discord.ui.button(label="Unlock", emoji=UNLOCK_EMOJI, custom_id="t_unlock", style=discord.ButtonStyle.secondary)
    async def b_unlock(self, i, b):
        t = self.cog.db.fetchone("SELECT * FROM open_tickets WHERE channel_id=?", (self.ch_id,))
        if not t['is_locked']: return await i.response.send_message("This ticket is already unlocked.", ephemeral=True)
        creator = i.guild.get_member(t['creator_id'])
        if creator: await i.channel.set_permissions(creator, send_messages=True)
        self.cog.db.execute("UPDATE open_tickets SET is_locked=0 WHERE channel_id=?", (self.ch_id,))
        await i.response.send_message(f"{UNLOCK_EMOJI} Ticket unlocked by {i.user.mention}.")
        await log_ticket_action(self.cog.db, i.guild, i.user, "Unlocked", f"{i.channel.mention}")

    @discord.ui.button(label="Claim", emoji=CLAIM_EMOJI, custom_id="t_claim", style=discord.ButtonStyle.primary)
    async def b_claim(self, i, b):
        from cogs.commands.ticket_workflow import claim
        await i.response.defer(ephemeral=True)
        if await claim(self.cog, i.channel, self.cat_id, i.user):
            await i.followup.send(view=Panel(f'{SUCCESS_EMOJI} Ticket claimed', 'You are now handling this request.'), ephemeral=True)
        else:
            await i.followup.send(view=Panel('Already claimed', 'This ticket is already being handled or has been closed.'), ephemeral=True)

    @discord.ui.button(label="Close", emoji=CLOSE_EMOJI, style=discord.ButtonStyle.danger, custom_id="t_close")
    async def b_close(self, i, b):
        lock = self.cog._action_locks.setdefault(self.ch_id, asyncio.Lock())
        if lock.locked():
            return await i.response.send_message(view=Panel('Please wait', 'This ticket is already being updated.'), ephemeral=True)
        async with lock:
            await self._close(i, b)

    async def _close(self, i, b):
        preferences = self.cog.preferences(i.guild.id, self.cat_id)
        if preferences['closing_questions'] and not hasattr(self, '_closing_answers'):
            from cogs.commands.ticket_workflow import ActionFormModal
            return await i.response.send_modal(ActionFormModal(self.cog, self.cat_id, preferences['closing_questions'], 'Close ticket', self.finish_close))
        await i.response.defer(ephemeral=True)
        t = self.cog.db.fetchone("SELECT * FROM open_tickets WHERE channel_id=?", (self.ch_id,))
        if t is None or t['closed_at']:
            return await i.followup.send(view=Panel('Ticket already closed', 'Use the latest message in the ticket.'), ephemeral=True)
        creator = i.guild.get_member(t['creator_id'])
        if t['is_claimed'] and preferences['restrict_claimed']:
            from cogs.commands.ticket_workflow import restore_claim
            await restore_claim(self.cog,i.channel,t,preferences)
        if creator:
            await i.channel.set_permissions(creator, send_messages=False, view_channel=False)
        
        category_info = self.cog.db.fetchone("SELECT name FROM ticket_categories WHERE category_id=?", (self.cat_id,))
        category_name = category_info['name'] if category_info else "Unknown"

        closed_category = await get_or_create_closed_category(self.cog.db, i.guild)
        if closed_category: await i.channel.edit(category=closed_category)
        
        self.cog.db.execute("UPDATE open_tickets SET closed_by_id=?, closed_at=? WHERE channel_id=?", (i.user.id, datetime.now().isoformat(), self.ch_id))
        self.cog.db.execute("UPDATE user_ticket_counts SET ticket_count=MAX(0,ticket_count-1) WHERE guild_id=? AND user_id=?", (i.guild.id,t['creator_id']))
        await log_ticket_action(self.cog.db, i.guild, i.user, "Closed", f"Ticket {i.channel.mention} (Category: {category_name})")

        # Geschlossen heisst: keine offenen Erinnerungen mehr, und ein
        # etwaiges >sleep endet hier. Ohne das kaeme nach dem Schliessen
        # noch eine DM zu einer Nachricht, die niemanden mehr betrifft.
        try:
            await ticket_notify.forget(self.ch_id)
        except Exception:
            pass
        
        closed_embed = discord.Embed(
            title=f"{CLOSE_EMOJI} Ticket Closed",
            description=f"This ticket has been officially closed and archived by {i.user.mention}.\nThe user has been removed from the channel.\n\nStaff can use the buttons below to reopen or permanently delete the channel.",
            color=EMBED_COLOR,
            timestamp=datetime.now()
        )
        closed_embed.add_field(name="Ticket Creator", value=f"<@{t['creator_id']}>", inline=True)
        closed_embed.add_field(name="Closed By", value=i.user.mention, inline=True)
        closed_embed.add_field(name="Original Category", value=category_name, inline=True)
        
        await i.channel.send(view=from_embed(closed_embed, ClosedTicketActionsView(self.cog, self.ch_id, self.cat_id)))
        if getattr(i, 'message', None):
            try:
                await i.message.edit(view=None)
            except discord.HTTPException:
                pass
        if getattr(self, '_closing_answers', None):
            from cogs.commands.ticket_workflow import send_answers
            await send_answers(i.channel, 'Closing form', self._closing_answers)
        if preferences['rating_enabled']:
            closed = self.cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?',(self.ch_id,))
            snapshot = {**dict(closed),'_settings':preferences,'_category_name':category_name}
            self.cog.db.execute('INSERT OR REPLACE INTO ticket_feedback_requests VALUES(?,?,?,?)',(self.ch_id,i.guild.id,t['creator_id'],json.dumps(snapshot)))
            try:
                recipient = creator or await self.cog.bot.fetch_user(t['creator_id'])
                await recipient.send(view=Panel(f'{SUCCESS_EMOJI} How was your support?', 'Your ticket has been closed. Share your feedback with the support team.',
                    buttons=[discord.ui.Button(label='Rate support',custom_id=f'ticket_rating_{self.ch_id}',emoji=MESSAGE)]))
            except discord.HTTPException:
                pass
        await i.followup.send("Ticket successfully closed and archived.", ephemeral=True)
        self.stop()

    async def finish_close(self, interaction, answers):
        from cogs.commands.ticket_workflow import is_staff
        ticket = self.cog.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=?', (self.ch_id,))
        settings = self.cog.preferences(interaction.guild.id,self.cat_id)
        if not ticket or ticket['closed_at'] or not (is_staff(self.cog,interaction.user,self.cat_id) or (ticket['creator_id']==interaction.user.id and (not settings['staff_only_close'] or getattr(self,'_request_confirmed',False)))):
            return await interaction.response.send_message(view=Panel('Action unavailable','This ticket is closed or you no longer have permission to close it.'),ephemeral=True)
        self._closing_answers = answers
        lock=self.cog._action_locks.setdefault(self.ch_id,asyncio.Lock())
        if lock.locked():
            return await interaction.response.send_message(view=Panel('Please wait','This ticket is already being updated.'),ephemeral=True)
        async with lock:
            await self._close(interaction,None)

    @discord.ui.button(label='Release', custom_id='t_unclaim', emoji=UNLOCK_EMOJI, row=1)
    async def b_unclaim(self, i, b):
        from cogs.commands.ticket_workflow import release
        await release(self, i)

    @discord.ui.button(label='Request close', custom_id='t_request', emoji=MESSAGE, row=1)
    async def b_request(self, i, b):
        self.cog.db.execute('INSERT INTO ticket_workflow(channel_id,last_activity,close_requested_by) VALUES(?,?,?) ON CONFLICT(channel_id) DO UPDATE SET close_requested_by=excluded.close_requested_by', (self.ch_id,time.time(),i.user.id))
        await i.response.send_message(view=Panel('Close this ticket?', 'The support team or ticket creator can confirm this request.', buttons=[discord.ui.Button(label='Confirm',custom_id='t_confirm',style=discord.ButtonStyle.danger),discord.ui.Button(label='Keep open',custom_id='t_cancel')]))

    @discord.ui.button(label='Confirm close', custom_id='t_confirm', row=2)
    async def b_confirm(self, i, b):
        state = self.cog.db.fetchone('SELECT close_requested_by FROM ticket_workflow WHERE channel_id=?', (self.ch_id,))
        if not state or not state['close_requested_by']:
            return await i.response.send_message(view=Panel('No active request', 'There is no close request to confirm.'), ephemeral=True)
        if state['close_requested_by'] == i.user.id:
            return await i.response.send_message(view=Panel('Waiting for confirmation', 'The other party must confirm your request.'), ephemeral=True)
        settings = self.cog.preferences(i.guild.id,self.cat_id)
        self.cog.db.execute('UPDATE ticket_workflow SET close_requested_by=NULL WHERE channel_id=?', (self.ch_id,))
        if settings['close_after_request']:
            self._request_confirmed = True
            return await self.b_close.callback(i)
        await i.response.send_message(view=Panel('Close request accepted', 'The support team can now close this ticket.'))

    @discord.ui.button(label='Keep open', custom_id='t_cancel', row=2)
    async def b_cancel(self, i, b):
        self.cog.db.execute('UPDATE ticket_workflow SET close_requested_by=NULL WHERE channel_id=?', (self.ch_id,))
        await i.response.send_message(view=Panel('Ticket stays open', 'The close request has been cancelled.'))

    @discord.ui.button(label='Ticket options', custom_id='t_tools', emoji=ZWRENCH, row=1)
    async def b_tools(self, i, b):
        from cogs.commands.ticket_workflow import ToolsView
        await i.response.send_message(view=Panel('Ticket options', 'Manage priority, participants and saved replies.', buttons=ToolsView(self.cog,self.ch_id,self.cat_id).children), ephemeral=True)

class ClosedTicketActionsView(discord.ui.View):
    def __init__(self, cog, ch_id, cat_id):
        super().__init__(timeout=None)
        self.cog, self.ch_id, self.cat_id = cog, ch_id, cat_id
        from cogs.commands.ticket_workflow import protect_actions
        protect_actions(self)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from cogs.commands.ticket_workflow import is_staff
        if not is_staff(self.cog,interaction.user,self.cat_id):
            await interaction.response.send_message(view=Panel(f'{ERROR_EMOJI} Staff action','Only the support team can manage archived tickets.'),ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Reopen", emoji=REOPEN_EMOJI, style=discord.ButtonStyle.success, custom_id="c_reopen")
    async def b_reopen(self, i: discord.Interaction, button: discord.ui.Button):
        lock=self.cog._action_locks.setdefault(self.ch_id,asyncio.Lock())
        if lock.locked():
            return await i.response.send_message(view=Panel('Please wait','This ticket is already being updated.'),ephemeral=True)
        async with lock:
            await self._reopen(i,button)

    async def _reopen(self, i, button):
        await i.response.defer(ephemeral=True)
        t = self.cog.db.fetchone("SELECT * FROM open_tickets WHERE channel_id=?", (self.ch_id,))
        cat_info = self.cog.db.fetchone("SELECT discord_category_id FROM ticket_categories WHERE category_id=?", (self.cat_id,))
        
        if not t or not t['closed_at']:
            return await i.followup.send(view=Panel('Already open','This ticket has already been reopened.'),ephemeral=True)
        original_category = i.guild.get_channel(cat_info['discord_category_id']) if cat_info else None
        if original_category: await i.channel.edit(category=original_category)

        creator = i.guild.get_member(t['creator_id'])
        if creator:
            await i.channel.set_permissions(creator, view_channel=True, send_messages=True)
            self.cog.db.execute("INSERT INTO user_ticket_counts VALUES (?,?,1) ON CONFLICT(guild_id,user_id) DO UPDATE SET ticket_count=ticket_count+1", (i.guild.id, creator.id))
        
        self.cog.db.execute("UPDATE open_tickets SET closed_by_id=NULL, closed_at=NULL, is_claimed=0, claimed_by_id=NULL WHERE channel_id=?", (self.ch_id,))
        
        self.cog.db.execute('UPDATE ticket_workflow SET last_activity=?,alerted=NULL,team_alerted=NULL,close_requested_by=NULL WHERE channel_id=?',(time.time(),self.ch_id))
        await ticket_notify.register_ticket(self.ch_id,i.guild.id,t['creator_id'])
        reopen_embed = discord.Embed(title=f"{REOPEN_EMOJI} Ticket Reopened", description=f"This ticket has been reopened by {i.user.mention}.", color=EMBED_COLOR)
        await i.channel.send(view=from_embed(reopen_embed, TicketActionsView(self.cog, self.ch_id, self.cat_id)))
        await i.message.edit(view=None)
        await log_ticket_action(self.cog.db, i.guild, i.user, "Reopened", f"{i.channel.mention}")
        self.stop()
        
    @discord.ui.button(label="Delete", emoji=DELETE_EMOJI, style=discord.ButtonStyle.danger, custom_id="c_delete")
    async def b_delete(self, i, b):
        await i.response.send_message(
            view=DeleteTicketTranscriptChoice(self, i.user.id), ephemeral=True
        )

    async def delete_ticket(self, i: discord.Interaction, send_dms: bool):
        ch = i.guild.get_channel(self.ch_id)
        if not ch:
            return await i.followup.send("Channel not found.", ephemeral=True)
        ticket = self.cog.db.fetchone(
            "SELECT * FROM open_tickets WHERE channel_id=?", (self.ch_id,)
        )
        if not ticket:
            return await i.followup.send("Ticket data was not found.", ephemeral=True)
        category = self.cog.db.fetchone(
            "SELECT name FROM ticket_categories WHERE category_id=?", (self.cat_id,)
        )
        category_name = category["name"] if category else "Unknown"
        config = self.cog.db.fetchone(
            "SELECT always_transcript FROM guild_configs WHERE guild_id=?",
            (i.guild.id,),
        )
        always_log = bool(config and config["always_transcript"])
        link = ""
        delivery_notes = []

        if send_dms or always_log:
            try:
                link = await save_ticket_transcript(
                    self.cog.db, ch, ticket, i.user, category_name
                )
            except Exception as exc:
                await i.followup.send(
                    f"The transcript could not be saved: {type(exc).__name__}.",
                    ephemeral=True,
                )
                return
            if not link:
                await i.followup.send(
                    "The transcript link is unavailable because the dashboard URL is not configured. The ticket was not deleted.",
                    ephemeral=True,
                )
                return

        if always_log and link:
            log_channel = await get_or_create_log_channel(self.cog.db, i.guild)
            if log_channel:
                try:
                    await log_channel.send(
                        view=transcript_dm_view(
                            i.guild.name, ch.name, ticket["ticket_number"], link
                        )
                    )
                    delivery_notes.append("the ticket log")
                except Exception:
                    pass

        if send_dms and link:
            recipients = [i.user]
            creator = i.guild.get_member(ticket["creator_id"])
            if creator is None:
                try:
                    creator = await self.cog.bot.fetch_user(ticket["creator_id"])
                except Exception:
                    creator = None
            if creator and creator.id != i.user.id:
                recipients.append(creator)
            delivered = 0
            for recipient in recipients:
                try:
                    await recipient.send(
                        view=transcript_dm_view(
                            i.guild.name, ch.name, ticket["ticket_number"], link
                        )
                    )
                    delivered += 1
                except Exception:
                    pass
            if delivered:
                delivery_notes.append(
                    "your DMs and the ticket creator's DMs"
                    if len(recipients) > 1 and delivered > 1 else "DMs"
                )

        destination = ", ".join(delivery_notes) if delivery_notes else "no recipients"
        await i.followup.send(
            f"Transcript delivery: {destination}. The ticket will be permanently deleted in 10 seconds.",
            ephemeral=True,
        )
        await log_ticket_action(
            self.cog.db, i.guild, i.user, "Deletion Scheduled", f"{ch.mention}"
        )
        await asyncio.sleep(10)
        await ch.delete()
        self.cog.db.execute("DELETE FROM open_tickets WHERE channel_id=?", (self.ch_id,))
        try:
            await ticket_notify.forget(self.ch_id)
        except Exception:
            pass
        self.stop()


class DeleteTicketTranscriptChoice(LayoutView):
    """Components V2 confirmation shown only to the staff member deleting."""

    def __init__(self, closed_view: ClosedTicketActionsView, user_id: int):
        super().__init__(timeout=120)
        self.closed_view = closed_view
        self.user_id = user_id
        self.finished = False
        yes = discord.ui.Button(
            label="Yes", emoji=TICK, style=discord.ButtonStyle.success
        )
        no = discord.ui.Button(
            label="No", emoji=CROSS, style=discord.ButtonStyle.secondary
        )
        yes.callback = self._yes
        no.callback = self._no
        self.add_item(container(
            TextDisplay(f"## {TRANSCRIPT_EMOJI}  Save ticket transcript?"),
            Separator(visible=True),
            TextDisplay(
                "Would you like to send the private transcript to **you** and "
                "the **ticket creator** before this channel is deleted?\n\n"
                "The link requires a Discord login and expires after **90 days**."
            ),
            Separator(visible=True),
            ActionRow(yes, no),
            accent_color=0x5865F2,
        ))

    async def _finish(self, interaction: discord.Interaction, send_dms: bool):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Only the staff member who opened this confirmation can choose.",
                ephemeral=True,
            )
        if self.finished:
            return await interaction.response.send_message(
                "This choice has already been processed.", ephemeral=True
            )
        self.finished = True
        self.stop()
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.edit_original_response(
            view=Panel(
                "Deleting Ticket",
                "The transcript choice was saved. The ticket is being archived and deleted.",
                tone="warning",
            )
        )
        await self.closed_view.delete_ticket(interaction, send_dms)

    async def _yes(self, interaction: discord.Interaction):
        await self._finish(interaction, True)

    async def _no(self, interaction: discord.Interaction):
        await self._finish(interaction, False)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
