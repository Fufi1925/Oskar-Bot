"""
Phantom Ticket Bot — nur Tickets, kein Remote-Control.
Eigener Discord-Bot-Token (PHANTOM_BOT_TOKEN).
Liest Config aus der Phantom-API / lokaler SQLite-DB.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord import ui
from discord.ext import commands
from dotenv import load_dotenv

# allow importing app.* from parent
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app import db as dbmod  # noqa: E402
from app.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("phantom.bot")

settings = get_settings()
CATEGORY_NAME = "Phantom Tickets"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

_db = None


async def get_db():
    global _db
    if _db is None:
        _db = await dbmod.connect()
    return _db


def is_staff_member(member: discord.Member, staff_role_ids: list[int]) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    ids = set(staff_role_ids or [])
    return any(r.id in ids for r in member.roles)


async def guild_cfg(guild_id: int) -> dict:
    db = await get_db()
    return await dbmod.get_guild_config(db, guild_id)


# ── UI ─────────────────────────────────────────────────────

class TicketControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Claimen", style=discord.ButtonStyle.green, custom_id="ph_ticket_claim", emoji="✋")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return
        cfg = await guild_cfg(interaction.guild.id)
        if not is_staff_member(interaction.user, cfg.get("staff_role_ids") or []):
            await interaction.response.send_message("Nur Staff kann claimen.", ephemeral=True)
            return

        db = await get_db()
        ticket = await dbmod.get_ticket(db, interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Kein Ticket-Datensatz.", ephemeral=True)
            return
        if ticket.get("owner_id") == interaction.user.id:
            await interaction.response.send_message("Du kannst dein eigenes Ticket nicht claimen.", ephemeral=True)
            return
        if ticket.get("claimed_by") and int(ticket["claimed_by"]) != interaction.user.id:
            await interaction.response.send_message(
                f"Bereits geclaimt von <@{ticket['claimed_by']}>.", ephemeral=True
            )
            return

        await dbmod.set_ticket_claim(db, interaction.channel.id, interaction.user.id)
        await dbmod.update_ticket_activity(db, interaction.channel.id)

        # perms: staff role view-only-ish optional — keep simple
        await interaction.channel.set_permissions(
            interaction.user, view_channel=True, send_messages=True, attach_files=True
        )
        await interaction.response.send_message(
            f"✅ Ticket geclaimt von {interaction.user.mention}",
        )

    @ui.button(label="Schließen", style=discord.ButtonStyle.red, custom_id="ph_ticket_close", emoji="🔒")
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return
        cfg = await guild_cfg(interaction.guild.id)
        db = await get_db()
        ticket = await dbmod.get_ticket(db, interaction.channel.id)
        member = interaction.user
        staff = isinstance(member, discord.Member) and is_staff_member(member, cfg.get("staff_role_ids") or [])
        owner = ticket and int(ticket["owner_id"]) == member.id
        if not staff and not owner:
            await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
            return

        await interaction.response.send_message("Ticket wird in 3 Sekunden geschlossen…")
        await asyncio.sleep(3)
        await dbmod.update_ticket_activity(db, interaction.channel.id)
        await dbmod.delete_ticket(db, interaction.channel.id)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {member}")
        except discord.HTTPException:
            pass


class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ticket erstellen", style=discord.ButtonStyle.primary, custom_id="ph_ticket_create", emoji="🎟️")
    async def create(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            return
        cfg = await guild_cfg(guild.id)
        db = await get_db()
        open_count = await dbmod.count_user_open_tickets(db, guild.id, user.id)
        if open_count >= 1:
            await interaction.response.send_message("Du hast bereits ein offenes Ticket.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(CATEGORY_NAME)

        staff_roles = []
        for rid in cfg.get("staff_role_ids") or []:
            role = guild.get_role(int(rid))
            if role:
                staff_roles.append(role)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True
            )

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}"[:90],
            category=category,
            overwrites=overwrites,
            topic=f"owner:{user.id}",
            reason=f"Phantom ticket by {user}",
        )
        await dbmod.register_ticket(
            db, channel_id=channel.id, guild_id=guild.id, owner_id=user.id, category="support"
        )

        # Update live activity
        await dbmod.update_ticket_activity(db, channel.id)

        embed = discord.Embed(
            title=f"Ticket von {user.display_name}",
            description=(
                f"Willkommen {user.mention}!\n\n"
                "Beschreibe dein Anliegen. Ein Teammitglied meldet sich.\n\n"
                f"-# {settings.phantom_footer}"
            ),
            color=discord.Color.blurple(),
        )
        await channel.send(embed=embed, view=TicketControlView())
        await interaction.followup.send(f"Ticket erstellt: {channel.mention}", ephemeral=True)

        # optional log
        log_id = cfg.get("log_channel_id")
        if log_id:
            log_ch = guild.get_channel(int(log_id))
            if log_ch:
                try:
                    await log_ch.send(f"🎟️ Neues Ticket {channel.mention} von {user.mention}")
                except discord.HTTPException:
                    pass


# ── Commands ──────────────────────────────────────────────

@bot.event
async def on_ready():
    bot.add_view(PanelView())
    bot.add_view(TicketControlView())
    log.info("Phantom Ticket-Bot online as %s", bot.user)

    # Sync all guilds the bot is actually a member of (CRITICAL for dashboard filtering)
    await sync_bot_guilds_to_db()
    log.info("Synced %s guilds the bot is in", len(bot.guilds))

    # Start periodic sync every 5 minutes (keeps dashboard fresh even if events missed)
    bot.loop.create_task(periodic_guild_sync())


async def periodic_guild_sync():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await sync_bot_guilds_to_db()
            log.debug("Periodic guild sync done")
        except Exception as e:
            log.warning("Periodic guild sync failed: %s", e)
        await asyncio.sleep(300)  # every 5 minutes


async def sync_bot_guilds_to_db():
    """Push current bot guilds into Phantom DB so dashboard only shows servers where bot is present."""
    db = await get_db()
    guilds_data = []
    for g in bot.guilds:
        guilds_data.append({
            "id": g.id,
            "name": g.name,
            "icon": str(g.icon) if g.icon else None,
            "member_count": getattr(g, "member_count", 0),
        })
    await dbmod.sync_bot_guilds(db, guilds_data)


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Bot joined a new server → immediately make it available in dashboard."""
    db = await get_db()
    await dbmod.sync_bot_guilds(db, [{
        "id": guild.id,
        "name": guild.name,
        "icon": str(guild.icon) if guild.icon else None,
        "member_count": guild.member_count,
    }])
    log.info("Bot joined guild %s — synced to dashboard", guild.id)


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Bot was removed from a server → remove from available list."""
    db = await get_db()
    await db.execute("DELETE FROM bot_guilds WHERE guild_id = ?", (guild.id,))
    await db.commit()
    log.info("Bot removed from guild %s — removed from dashboard", guild.id)


@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """Keep member count / name / icon up to date for the dashboard."""
    if before.member_count != after.member_count or before.name != after.name:
        db = await get_db()
        await dbmod.update_bot_guild_stats(
            db,
            after.id,
            name=after.name,
            icon=str(after.icon) if after.icon else None,
            member_count=after.member_count,
        )


@bot.command(name="panel")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def panel_cmd(ctx: commands.Context):
    """Postet das Ticket-Panel in diesen Kanal und speichert die Config."""
    assert ctx.guild
    db = await get_db()
    cfg = await dbmod.get_guild_config(db, ctx.guild.id)
    title = cfg.get("panel_title") or "Support Center"
    desc = cfg.get("panel_description") or "Klicke auf den Button, um ein Ticket zu öffnen."

    embed = discord.Embed(
        title=f"📩 {title}",
        description=f"{desc}\n\n-# {settings.phantom_footer}",
        color=discord.Color.green(),
    )
    msg = await ctx.send(embed=embed, view=PanelView())
    await dbmod.save_guild_config(
        db,
        ctx.guild.id,
        panel_channel_id=ctx.channel.id,
        panel_message_id=msg.id,
    )
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


@bot.command(name="setstaff")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def setstaff_cmd(ctx: commands.Context, *roles: discord.Role):
    if not roles:
        await ctx.send("Nutzung: `!setstaff @Rolle1 @Rolle2`")
        return
    db = await get_db()
    ids = [r.id for r in roles if not r.is_default() and not r.managed]
    await dbmod.save_guild_config(db, ctx.guild.id, staff_role_ids=ids)
    await ctx.send("Staff-Rollen gespeichert: " + ", ".join(r.mention for r in roles if r.id in ids))


@bot.command(name="setlog")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def setlog_cmd(ctx: commands.Context):
    db = await get_db()
    await dbmod.save_guild_config(db, ctx.guild.id, log_channel_id=ctx.channel.id)
    await ctx.send(f"Log-Kanal gesetzt: {ctx.channel.mention}")


def main() -> None:
    token = settings.phantom_bot_token or os.getenv("PHANTOM_BOT_TOKEN")
    if not token:
        raise SystemExit("PHANTOM_BOT_TOKEN fehlt in .env")
    bot.run(token)


if __name__ == "__main__":
    main()
