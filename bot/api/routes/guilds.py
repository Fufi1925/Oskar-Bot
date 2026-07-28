# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from api.dependencies import get_bot, limiter
from api.db_manager import db_manager
from api.patch_utils import merge_partial, model_updates, changed_fields
from api.schemas import (
    GuildSummary, GuildDetails, PrefixConfig,
# NOTE: automod moved to api/routes/verify.py's sibling,
# api/routes/automod.py. The pair here stored whatever key the dashboard
# sent -- and it sent "anti_spam" while the cogs read "Anti spam", so
# nothing configured in the tab ever reached the bot.
    TicketConfig, TicketEmbed,
    TicketCategory, PrefixUpdate,
    TicketUpdate,
    DiscordChannel, DiscordRole, WelcomeConfig, WelcomeEmbedData, WelcomeUpdate,
# NOTE: logging moved to api/routes/logging_cfg.py, anti-nuke to
# api/routes/antinuke.py. Their schemas went with them.
# NOTE: verification moved to api/routes/verify.py. The pair here knew
# five columns and stored 0 for "not set" -- zero is not null, so the
# read side handed "0" back to the dashboard as though it were a real
# channel id, and the INSERT branch wiped a setup made over chat.
    AutoRoleConfig, AutoRoleUpdate,
    TrackingConfig, TrackingUpdate,
    AutoReactConfig, AutoReactUpdate, AutoReactTrigger,
    InviteStat, InvitesLeaderboard
)
from typing import TYPE_CHECKING, List, Optional
import aiosqlite
import json
import os

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


def _member_count(guild) -> int:
    """
    Best available member count for a guild.

    `guild.member_count` is populated from the gateway, but it can be None
    before the member chunk for that guild has arrived. Falling back to the
    cached member list (and then to approximate_member_count) keeps the
    dashboard from showing 0 or a dash right after a restart.
    """
    if guild is None:
        return 0
    count = getattr(guild, "member_count", None)
    if count:
        return int(count)
    cached = len(getattr(guild, "members", ()) or ())
    if cached:
        return cached
    return int(getattr(guild, "approximate_member_count", 0) or 0)


@router.get("/", response_model=List[GuildSummary], summary="List all guilds", description="Returns a summary of all guilds the bot is currently in.")
async def list_guilds(bot: "universitybot" = Depends(get_bot)):
    """
    Lists detailed information about all guilds the bot is currently in.
    """
    guilds_list = []
    for guild in bot.guilds:
        guilds_list.append(GuildSummary(
            id=str(guild.id),
            name=guild.name,
            icon_url=str(guild.icon.url) if guild.icon else None,
            owner_id=str(guild.owner_id),
            member_count=_member_count(guild),
        ))
    return guilds_list

@router.get("/{guild_id}", response_model=GuildDetails, summary="Get guild details", description="Returns detailed metrics and metadata for a specific Discord guild.")
async def get_guild_details(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    Returns detailed info for a specific guild by its ID.
    """
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    return GuildDetails(
        id=str(guild.id),
        name=guild.name,
        icon=str(guild.icon.url) if guild.icon else None,
        owner_id=str(guild.owner_id),
        member_count=_member_count(guild),
        role_count=len(guild.roles),
        channel_count=len(guild.channels)
    )

@router.get("/{guild_id}/prefix", response_model=PrefixConfig, summary="Get guild prefix", description="Retrieves the custom command prefix configured for the guild.")
async def get_guild_prefix(guild_id: int):
    """
    Retrieves the custom prefix for a specific guild.
    """
    db = await db_manager.get_connection('db/prefix.db')
    cursor = await db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (guild_id,))
    row = await cursor.fetchone()
    prefix = row[0] if row else ">"
    return PrefixConfig(guild_id=guild_id, prefix=prefix)

@router.post("/{guild_id}/prefix", summary="Update guild prefix", description="Updates or resets the custom command prefix for the specified guild.")
async def update_guild_prefix(guild_id: int, data: PrefixUpdate):
    """
    Updates the custom prefix for a specific guild.
    """
    if not data.prefix or len(data.prefix) > 10:
        raise HTTPException(status_code=400, detail="Invalid prefix. Must be 1-10 characters.")

    db = await db_manager.get_connection('db/prefix.db')
    await db.execute(
        "INSERT OR REPLACE INTO prefixes (guild_id, prefix) VALUES (?, ?)",
        (guild_id, data.prefix)
    )
    await db.commit()

    # The bot caches prefixes in memory to avoid a database hit per message.
    from utils.Tools import invalidate_prefix_cache
    invalidate_prefix_cache(guild_id)

    return {"status": "success", "guild_id": guild_id, "new_prefix": data.prefix}





@router.get("/{guild_id}/tickets", response_model=TicketConfig, summary="Get Ticket config", description="Retrieves the support ticket system setup, categories, and staff roles.")
async def get_guild_tickets(guild_id: int):
    """
    Retrieves the ticket system configuration for a specific guild.
    """
    db = await db_manager.get_connection('db/ticket.db')
    
    # Get basic config
    cursor = await db.execute(
        "SELECT panel_channel_id, panel_message_id, logging_channel_id, panel_type, embed_title, embed_description, embed_color, embed_image_url, embed_thumbnail_url, closed_category_id FROM guild_configs WHERE guild_id = ?", 
        (guild_id,)
    )
    config_row = await cursor.fetchone()
    
    # Get categories and identify staff roles
    cursor = await db.execute(
        "SELECT name, emoji, notified_roles, button_style, discord_category_id FROM ticket_categories WHERE guild_id = ?", 
        (guild_id,)
    )
    categories_rows = await cursor.fetchall()
    categories = []
    staff_roles = set()
    for row in categories_rows:
        if row["notified_roles"]:
            roles = [int(r.strip()) for r in row["notified_roles"].split(",") if r.strip()]
            category_roles = roles
            for r in roles:
                staff_roles.add(r)
        else:
            category_roles = []

        categories.append(TicketCategory(
            name=row["name"],
            emoji=row["emoji"],
            staff_roles=category_roles,
            button_style=row["button_style"],
            discord_category_id=row["discord_category_id"]
        ))

    # Get open ticket count
    cursor = await db.execute(
        "SELECT COUNT(*) FROM open_tickets WHERE guild_id = ?", 
        (guild_id,)
    )
    count_row = await cursor.fetchone()
    open_ticket_count = count_row[0] if count_row else 0

    return TicketConfig(
        guild_id=guild_id,
        panel_channel=config_row["panel_channel_id"] if config_row else None,
        panel_message=config_row["panel_message_id"] if config_row else None,
        logging_channel=config_row["logging_channel_id"] if config_row else None,
        closed_category=config_row["closed_category_id"] if config_row else None,
        panel_type=config_row["panel_type"] if config_row else "button",
        embed=TicketEmbed(
            title=config_row["embed_title"] if config_row else "Support Department",
            description=config_row["embed_description"] if config_row else "Open a ticket below to talk to our staff.",
            color=config_row["embed_color"] if config_row else None,
            image_url=config_row["embed_image_url"] if config_row else None,
            thumbnail_url=config_row["embed_thumbnail_url"] if config_row else None
        ),
        categories=categories,
        staff_roles=list(staff_roles),
        open_ticket_count=open_ticket_count
    )

@router.patch("/{guild_id}/tickets", summary="Update Ticket config", description="Updates the ticket system configuration, including categories and embed details.")
async def patch_guild_tickets(guild_id: int, data: TicketUpdate):
    """
    Updates the ticket system configuration for a specific guild.
    """
    db = await db_manager.get_connection('db/ticket.db')
    
    # Initialize config row if not exists
    cursor = await db.execute("SELECT guild_id FROM guild_configs WHERE guild_id = ?", (guild_id,))
    if not await cursor.fetchone():
        await db.execute("INSERT INTO guild_configs (guild_id) VALUES (?)", (guild_id,))

    if data.panel_channel is not None:
        await db.execute("UPDATE guild_configs SET panel_channel_id = ? WHERE guild_id = ?", (data.panel_channel, guild_id))
    
    if data.logging_channel is not None:
        await db.execute("UPDATE guild_configs SET logging_channel_id = ? WHERE guild_id = ?", (data.logging_channel, guild_id))
        
    if data.closed_category is not None:
        await db.execute("UPDATE guild_configs SET closed_category_id = ? WHERE guild_id = ?", (data.closed_category, guild_id))

    if data.panel_type is not None:
        await db.execute("UPDATE guild_configs SET panel_type = ? WHERE guild_id = ?", (data.panel_type, guild_id))
        
    if data.embed_title is not None:
        await db.execute("UPDATE guild_configs SET embed_title = ? WHERE guild_id = ?", (data.embed_title, guild_id))

    if data.embed_description is not None:
        await db.execute("UPDATE guild_configs SET embed_description = ? WHERE guild_id = ?", (data.embed_description, guild_id))

    if data.embed_color is not None:
        await db.execute("UPDATE guild_configs SET embed_color = ? WHERE guild_id = ?", (data.embed_color, guild_id))

    if data.embed_image_url is not None:
        await db.execute("UPDATE guild_configs SET embed_image_url = ? WHERE guild_id = ?", (data.embed_image_url, guild_id))

    if data.embed_thumbnail_url is not None:
        await db.execute("UPDATE guild_configs SET embed_thumbnail_url = ? WHERE guild_id = ?", (data.embed_thumbnail_url, guild_id))

    if data.staff_roles is not None:
        roles_str = ",".join(map(str, data.staff_roles))
        await db.execute("UPDATE guild_configs SET staff_roles = ? WHERE guild_id = ?", (roles_str, guild_id))

    if data.categories is not None:
        # Clear existing categories
        await db.execute("DELETE FROM ticket_categories WHERE guild_id = ?", (guild_id,))
        for cat in data.categories:
            roles_str = ",".join(map(str, cat.staff_roles))
            await db.execute(
                "INSERT INTO ticket_categories (guild_id, name, emoji, notified_roles, button_style, discord_category_id) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, cat.name, cat.emoji, roles_str, cat.button_style, cat.discord_category_id)
            )

    await db.commit()
    return {"status": "success", "guild_id": guild_id}
    return {"status": "success", "guild_id": guild_id}



# NOTE: the leveling settings moved to api/routes/leveling.py.
# The pair of routes that lived here exposed five of twelve settings, read
# the settings row by tuple index (so a new column shifted every value),
# and wrote each field with its own UPDATE without checking the row
# existed. The dashboard now shares utils/leveling_store.py with the cog.


@router.get("/{guild_id}/welcome", response_model=WelcomeConfig, summary="Get Welcome config", description="Retrieves the greet/welcome messages setup.")
async def get_guild_welcome(guild_id: int):
    import aiosqlite
    import json
    
    async with aiosqlite.connect("db/welcome.db") as db:
        async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration FROM welcome WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        return WelcomeConfig(
            guild_id=guild_id,
        )
        
    welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration = row
    
    embed_parsed = None
    if embed_data:
        try:
            embed_parsed = WelcomeEmbedData(**json.loads(embed_data))
        except:
            pass
            
    return WelcomeConfig(
        guild_id=guild_id,
        welcome_type=welcome_type,
        welcome_message=welcome_message,
        # Stored as INTEGER, declared as a string. Handing the raw int to
        # Pydantic raised and turned the whole welcome page into a 500.
        channel_id=str(channel_id) if channel_id not in (None, 0) else None,
        embed_data=embed_parsed,
        auto_delete_duration=auto_delete_duration
    )

@router.patch("/{guild_id}/welcome", summary="Update Welcome config", description="Updates welcome/greet configuration.")
async def patch_guild_welcome(guild_id: int, data: WelcomeUpdate):
    import aiosqlite
    import json
    
    async with aiosqlite.connect("db/welcome.db") as db:
        # Get existing or create
        async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration FROM welcome WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            
        if not row:
            await db.execute(
                "INSERT INTO welcome (guild_id, welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, data.welcome_type or "simple", data.welcome_message, data.channel_id, json.dumps(data.embed_data.dict()) if data.embed_data else None, data.auto_delete_duration)
            )
        else:
            current = dict(zip(
                ("welcome_type", "welcome_message", "channel_id",
                 "embed_data", "auto_delete_duration"),
                row,
            ))

            updates = model_updates(data)
            # embed_data arrives as a model and is stored as JSON.
            if data.embed_data is not None:
                updates["embed_data"] = json.dumps(data.embed_data.dict())

            merged = merge_partial(current, updates)

            await db.execute(
                "UPDATE welcome SET welcome_type = ?, welcome_message = ?, channel_id = ?, embed_data = ?, auto_delete_duration = ? WHERE guild_id = ?",
                (
                    merged["welcome_type"],
                    merged["welcome_message"],
                    merged["channel_id"],
                    merged["embed_data"],
                    merged["auto_delete_duration"],
                    guild_id,
                ),
            )
            
        await db.commit()
        
    return {"status": "success", "guild_id": guild_id}


# NOTE: anti-nuke moved to api/routes/antinuke.py. The pair here could
# only add a whitelist entry with every column True -- a full bypass of
# all seventeen protections from a button labelled "Add" -- and it did
# nothing at all when the table had not been created yet, while still
# reporting success.


# NOTE: vanity roles moved to api/routes/vanity.py. The three routes that
# lived here stored the trigger exactly as typed, so `.gg/MeinServer` and
# `discord.gg/meinserver` became two separate setups that both looked right;
# and they matched nothing useful anyway, because the cog behind them
# checked whether the *invite* still existed and then handed the role to
# every member of the server.


@router.get("/{guild_id}/autorole", response_model=AutoRoleConfig, summary="Get AutoRole config")
async def get_guild_autorole(guild_id: int):
    import aiosqlite
    
    async with aiosqlite.connect("db/autorole.db") as db:
        # Ensure table exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autorole (
                guild_id INTEGER PRIMARY KEY,
                bots TEXT NOT NULL DEFAULT '[]',
                humans TEXT NOT NULL DEFAULT '[]'
            )
        """)
        await db.commit()
        
        async with db.execute("SELECT bots, humans FROM autorole WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            
    if row:
        bots_str, humans_str = row
        try:
            bots = [r.strip() for r in bots_str.replace('[','').replace(']','').split(',') if r.strip()]
        except Exception:
            bots = []
            
        try:
            humans = [r.strip() for r in humans_str.replace('[','').replace(']','').split(',') if r.strip()]
        except Exception:
            humans = []
            
        return AutoRoleConfig(guild_id=str(guild_id), bots=bots, humans=humans)
        
    return AutoRoleConfig(guild_id=str(guild_id), bots=[], humans=[])

@router.patch("/{guild_id}/autorole", summary="Update AutoRole config")
async def patch_guild_autorole(guild_id: int, data: AutoRoleUpdate):
    import aiosqlite
    
    async with aiosqlite.connect("db/autorole.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autorole (
                guild_id INTEGER PRIMARY KEY,
                bots TEXT NOT NULL DEFAULT '[]',
                humans TEXT NOT NULL DEFAULT '[]'
            )
        """)
        
        # Build the bracket-format strings the bot cog expects
        if data.bots is not None:
            bots_str = str([int(b) for b in data.bots if b and b.isdigit()])
        else:
            # Get existing to keep
            async with db.execute("SELECT bots FROM autorole WHERE guild_id = ?", (guild_id,)) as cursor:
                old = await cursor.fetchone()
            bots_str = old[0] if old else '[]'
            
        if data.humans is not None:
            humans_str = str([int(h) for h in data.humans if h and h.isdigit()])
        else:
            async with db.execute("SELECT humans FROM autorole WHERE guild_id = ?", (guild_id,)) as cursor:
                old = await cursor.fetchone()
            humans_str = old[0] if old else '[]'
            
        await db.execute(
            "INSERT OR REPLACE INTO autorole (guild_id, bots, humans) VALUES (?, ?, ?)",
            (guild_id, bots_str, humans_str)
        )
        await db.commit()
        
    return {"status": "success"}


# NOTE: a second, duplicated definition of GET/PATCH /{guild_id}/welcome used
# to live here. Starlette matches the FIRST registered route, so this copy was
# dead code that only diverged from the active implementation above.

@router.delete("/{guild_id}/welcome", summary="Delete Welcome config")
async def delete_guild_welcome(guild_id: int):
    import aiosqlite
    async with aiosqlite.connect("db/welcome.db") as db:
        await db.execute("DELETE FROM welcome WHERE guild_id = ?", (guild_id,))
        await db.commit()
    return {"status": "success"}


@router.get("/{guild_id}/tracking", response_model=TrackingConfig, summary="Get Tracking config")
async def get_guild_tracking(guild_id: int):
    import aiosqlite
    async with aiosqlite.connect("db/invite.db") as db:
        async with db.execute("SELECT channel_id FROM logging WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
    return TrackingConfig(
        guild_id=guild_id,
        channel_id=str(row[0]) if row and row[0] else None,
    )

@router.patch("/{guild_id}/tracking", summary="Update Tracking config")
async def patch_guild_tracking(guild_id: int, data: TrackingUpdate):
    import aiosqlite
    async with aiosqlite.connect("db/invite.db") as db:
        # The table stores an integer; the string only exists so the id
        # survives the trip through the browser intact.
        channel_id = int(data.channel_id) if data.channel_id else None
        await db.execute(
            "CREATE TABLE IF NOT EXISTS logging "
            "(guild_id INTEGER PRIMARY KEY, channel_id INTEGER)"
        )
        await db.execute("INSERT OR REPLACE INTO logging (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
        await db.commit()
    return {"status": "success"}




# NOTE: Join DM moved to api/routes/memberperks.py. The pair here stored
# a bare string in jsondb/joindm_messages.json, and the cog behind it
# registered its listener at runtime -- so the feature was silently off
# after every restart while this endpoint still returned the text.




# NOTE: logging moved to api/routes/logging_cfg.py. The pair here knew
# six of the cog's nine categories, so emoji, reaction and server-update
# logging could not be reached from the web at all -- and the ignore
# lists were readable but not writable.


# NOTE: the leaderboard moved to /leveling/{guild_id}/leaderboard. The
# version here read `user_xp`, the table the admin commands never wrote
# to, so it disagreed with the bot as soon as anybody set somebody's XP.


@router.get("/{guild_id}/channels", response_model=List[DiscordChannel], summary="Get guild channels", description="Returns a list of all channels for the specific guild.")
async def get_guild_channels(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    channels = []
    for canal in guild.channels:
        try:
            # Handle both discord.ChannelType enum and literal ints
            c_type = canal.type.value if hasattr(canal.type, 'value') else int(canal.type)
            channels.append(DiscordChannel(
                id=str(canal.id),
                name=canal.name,
                type=str(c_type)
            ))
        except:
            continue
    return channels

@router.get("/{guild_id}/roles", response_model=List[DiscordRole], summary="Get guild roles", description="Returns a list of roles for the specific guild.")
async def get_guild_roles(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    me = guild.me
    bot_top = me.top_role.position if me is not None and me.top_role else 0

    roles = []
    for role in guild.roles:
        # Avoid @everyone role if desired, but frontend might need filtering. Let's return all.
        roles.append(DiscordRole(
            id=str(role.id),
            name=role.name,
            color=role.color.value,
            position=role.position,
            # A 64-bit bitfield as a JSON number would lose its low bits
            # in the browser, so it travels as a string.
            permissions=str(role.permissions.value),
            managed=bool(role.managed),
            bot_top_position=bot_top,
        ))
    # Sort roles by position descending
    roles.sort(key=lambda x: x.position, reverse=True)
    return roles


# ========== INVC ROLE (Voice Role) ==========



# NOTE: Join to Create, voice roles and custom role commands moved to
# api/routes/voice.py. The handlers here disagreed with the cogs behind
# them: /invcrole stored an "enabled" flag the cog never read, so the
# dashboard switch did nothing, and /customroles exposed only the five
# fixed slots while the real named commands lived in another table.


# ========== AUTO REACT ==========

# NOTE: a duplicated GET /{guild_id}/autoreact used to live here. The active
# definition sits below in the AUTO REACT section next to its PATCH handler.

# ========== INVC ROLE (Voice Role) ==========




# ========== AUTO REACT ==========

@router.get("/{guild_id}/autoreact", response_model=AutoReactConfig, summary="Get AutoReact config")
async def get_guild_autoreact(guild_id: int):
    import aiosqlite
    async with aiosqlite.connect("db/autoreact.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autoreact (
                guild_id INTEGER,
                trigger TEXT,
                emojis TEXT
            )
        """)
        await db.commit()

        async with db.execute("SELECT trigger, emojis FROM autoreact WHERE guild_id = ?", (guild_id,)) as cursor:
            rows = await cursor.fetchall()

    triggers = [AutoReactTrigger(trigger=row[0], emojis=row[1]) for row in rows]
    return AutoReactConfig(guild_id=str(guild_id), triggers=triggers)

@router.patch("/{guild_id}/autoreact", summary="Update AutoReact config")
async def patch_guild_autoreact(guild_id: int, data: AutoReactUpdate):
    db = await db_manager.get_connection("db/autoreact.db")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS autoreact (
            guild_id INTEGER,
            trigger TEXT,
            emojis TEXT
        )
    """)
    await db.execute("DELETE FROM autoreact WHERE guild_id = ?", (guild_id,))
    for t in data.triggers:
        await db.execute("INSERT INTO autoreact (guild_id, trigger, emojis) VALUES (?, ?, ?)",
                         (guild_id, t.trigger, t.emojis))
    await db.commit()
    return {"status": "success"}


# ========== INVITES LEADERBOARD ==========

@router.get("/{guild_id}/invites", response_model=InvitesLeaderboard, summary="Get invite leaderboard")
async def get_guild_invites(guild_id: int):
    table_name = f"invites_{guild_id}"
    data_list = []
    
    db = await db_manager.get_connection("db/invite.db")
    # Check if table exists
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)) as cursor:
        exists = await cursor.fetchone()
    
    if exists:
        try:
            # Use a safer query that handles missing columns if necessary
            async with db.execute(f"SELECT user_id, total, fake, left, rejoin FROM [{table_name}] ORDER BY total DESC LIMIT 20") as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                data_list.append(InviteStat(
                    user_id=str(row[0]),
                    total=row[1] or 0,
                    fake=row[2] or 0,
                    left=row[3] or 0,
                    rejoin=row[4] or 0
                ))
        except Exception as e:
            print(f"Error fetching invites for {guild_id}: {e}")
    else:
        # If no tracking data yet, just return empty list
        pass
    
    return InvitesLeaderboard(guild_id=str(guild_id), data=data_list)


# ========== REACTION ROLES ==========

# NOTE: reaction roles moved to api/routes/memberperks.py. The route here
# only wrote a database row; unlike the chat command it never called
# message.add_reaction(), so an entry created in the dashboard left
# members with nothing to click on.


# ========== NICKNAME RULES ==========
async def _ensure_nickname_table(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS nickname_rules (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            prefix TEXT DEFAULT '',
            suffix TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY (guild_id, role_id)
        )
    """)
    await db.commit()


@router.get("/{guild_id}/nickname", summary="Get nickname role rules")
async def get_nickname_rules(guild_id: int):
    db = await db_manager.get_connection("db/nickname.db")
    await _ensure_nickname_table(db)
    async with db.execute("SELECT role_id, prefix, suffix, enabled FROM nickname_rules WHERE guild_id = ? ORDER BY role_id", (guild_id,)) as cursor:
        rows = await cursor.fetchall()
    return {
        "guild_id": str(guild_id),
        "rules": [
            {"role_id": str(row[0]), "prefix": row[1] or "", "suffix": row[2] or "", "enabled": bool(row[3])}
            for row in rows
        ]
    }

@router.patch("/{guild_id}/nickname", summary="Update nickname role rules")
async def update_nickname_rules(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise HTTPException(status_code=400, detail="rules must be a list")
    db = await db_manager.get_connection("db/nickname.db")
    await _ensure_nickname_table(db)
    await db.execute("DELETE FROM nickname_rules WHERE guild_id = ?", (guild_id,))
    clean_rules = []
    for rule in rules[:25]:
        role_id = str(rule.get("role_id", "")).strip()
        if not role_id.isdigit():
            continue
        prefix = str(rule.get("prefix", ""))[:16]
        suffix = str(rule.get("suffix", ""))[:16]
        enabled = bool(rule.get("enabled", True))
        await db.execute(
            "INSERT OR REPLACE INTO nickname_rules (guild_id, role_id, prefix, suffix, enabled) VALUES (?, ?, ?, ?, ?)",
            (guild_id, int(role_id), prefix, suffix, 1 if enabled else 0),
        )
        clean_rules.append({"role_id": role_id, "prefix": prefix, "suffix": suffix, "enabled": enabled})
    await db.commit()
    # Try applying immediately to current members that are cached.
    guild = bot.get_guild(guild_id)
    if guild:
        apply_rules = getattr(bot, "apply_nickname_rules", None)
        if apply_rules:
            for member in guild.members:
                asyncio.create_task(apply_rules(member))
    return {"status": "success", "rules": clean_rules}


# ========== EXTRA SETTINGS ==========
async def _ensure_extra_settings_table(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS guild_extra_settings (
            guild_id INTEGER PRIMARY KEY,
            delete_command_messages INTEGER DEFAULT 0,
            mention_prefix_response INTEGER DEFAULT 1,
            same_voice_only INTEGER DEFAULT 1
        )
    """)
    await db.commit()

@router.get("/{guild_id}/extra-settings", summary="Get additional guild settings")
async def get_extra_settings(guild_id: int):
    db = await db_manager.get_connection("db/settings.db")
    await _ensure_extra_settings_table(db)
    async with db.execute(
        "SELECT delete_command_messages, mention_prefix_response, same_voice_only FROM guild_extra_settings WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {"guild_id": str(guild_id), "delete_command_messages": False, "mention_prefix_response": True, "same_voice_only": True}
    return {"guild_id": str(guild_id), "delete_command_messages": bool(row[0]), "mention_prefix_response": bool(row[1]), "same_voice_only": bool(row[2])}

@router.patch("/{guild_id}/extra-settings", summary="Update additional guild settings")
async def update_extra_settings(guild_id: int, data: dict):
    db = await db_manager.get_connection("db/settings.db")
    await _ensure_extra_settings_table(db)

    # PATCH must only change what was sent. Falling back to the hardcoded
    # defaults meant that toggling one switch silently reset the other two:
    # enable A, later toggle B, and A was off again on the next page load.
    async with db.execute(
        "SELECT delete_command_messages, mention_prefix_response, same_voice_only"
        " FROM guild_extra_settings WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()

    current = {
        "delete_command_messages": bool(row[0]) if row else False,
        "mention_prefix_response": bool(row[1]) if row else True,
        "same_voice_only": bool(row[2]) if row else True,
    }
    values = merge_partial(
        current, data, coerce={k: bool for k in current}
    )
    await db.execute(
        """
        INSERT OR REPLACE INTO guild_extra_settings
        (guild_id, delete_command_messages, mention_prefix_response, same_voice_only)
        VALUES (?, ?, ?, ?)
        """,
        (guild_id, int(values["delete_command_messages"]), int(values["mention_prefix_response"]), int(values["same_voice_only"])),
    )
    await db.commit()
    return {"status": "success", **values}


# ========== DASHBOARD FEATURE SETTINGS ==========
async def _ensure_feature_settings_table(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_feature_settings (
            guild_id INTEGER NOT NULL,
            scope TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (guild_id, scope)
        )
    """)
    await db.commit()

SETTINGS_DEFAULTS = {
    "delete_command_messages": False,
    "mention_prefix_response": True,
    "same_voice_only": True,
    "auto_cleanup_invites": False,
    "compact_embeds": False,
    "dm_mod_actions": False,
    "log_dashboard_changes": True,
    "require_reason_moderation": False,
    "auto_slowmode_alerts": False,
    "protect_admin_roles": True,
}

ADMIN_DASHBOARD_DEFAULTS = {
    "emergency_lockdown": False,
    "anti_raid_watch": True,
    "auto_role_audit": True,
    "permission_scan": True,
    "inactive_channel_scan": False,
    "invite_security": True,
    "webhook_monitoring": True,
    "bot_role_guard": True,
    "mass_mention_guard": True,
    "dashboard_audit_log": True,
    "channel_permission_diff": True,
    "role_hierarchy_alerts": True,
    "new_account_watch": True,
    "suspicious_name_watch": False,
    "automod_recommendations": True,
    "backup_snapshot_reminders": True,
    "staff_activity_insights": False,
    "ticket_overload_alerts": True,
    "voice_abuse_monitor": True,
    "public_webhook_alerts": True,
}

async def _get_feature_scope(guild_id: int, scope: str, defaults: dict):
    db = await db_manager.get_connection("db/settings.db")
    await _ensure_feature_settings_table(db)
    async with db.execute("SELECT settings_json FROM dashboard_feature_settings WHERE guild_id = ? AND scope = ?", (guild_id, scope)) as cursor:
        row = await cursor.fetchone()
    data = {}
    if row:
        try:
            data = json.loads(row[0] or "{}")
        except Exception:
            data = {}
    return {**defaults, **{k: bool(v) for k, v in data.items() if k in defaults}}

async def _set_feature_scope(guild_id: int, scope: str, defaults: dict, data: dict):
    db = await db_manager.get_connection("db/settings.db")
    await _ensure_feature_settings_table(db)
    current = await _get_feature_scope(guild_id, scope, defaults)
    clean = {**current, **{k: bool(v) for k, v in data.items() if k in defaults}}
    await db.execute(
        "INSERT OR REPLACE INTO dashboard_feature_settings (guild_id, scope, settings_json) VALUES (?, ?, ?)",
        (guild_id, scope, json.dumps(clean)),
    )
    await db.commit()
    return clean

@router.get("/{guild_id}/settings-features", summary="Get settings tab feature toggles")
async def get_settings_features(guild_id: int):
    return {"guild_id": str(guild_id), **await _get_feature_scope(guild_id, "settings", SETTINGS_DEFAULTS)}

@router.patch("/{guild_id}/settings-features", summary="Update settings tab feature toggles")
async def update_settings_features(guild_id: int, data: dict):
    return {"status": "success", **await _set_feature_scope(guild_id, "settings", SETTINGS_DEFAULTS, data)}

@router.get("/{guild_id}/admin-dashboard", summary="Get admin dashboard feature toggles")
async def get_admin_dashboard(guild_id: int):
    return {"guild_id": str(guild_id), **await _get_feature_scope(guild_id, "admin_dashboard", ADMIN_DASHBOARD_DEFAULTS)}

@router.patch("/{guild_id}/admin-dashboard", summary="Update admin dashboard feature toggles")
async def update_admin_dashboard(guild_id: int, data: dict):
    return {"status": "success", **await _set_feature_scope(guild_id, "admin_dashboard", ADMIN_DASHBOARD_DEFAULTS, data)}


# ══════════════════════════════════════════════════════════════════════════
#  Configuration export / import
# ══════════════════════════════════════════════════════════════════════════


@router.get("/{guild_id}/config/export", summary="Download the full server configuration")
async def export_guild_config(
    guild_id: int,
    include_user_data: bool = False,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Every setting configured for this server, as one JSON file.

    Covers all modules at once — welcome, automod, antinuke, leveling,
    tickets, verification, roles, logging and the rest. Per-user history
    (XP, warnings, tickets) is left out unless include_user_data is set,
    because it is not portable between servers.
    """
    from api.config_transfer import export_guild

    payload = await export_guild(guild_id, include_user_data=include_user_data)

    guild = bot.get_guild(guild_id)
    payload["guild_name"] = guild.name if guild else None
    payload["bot_name"] = bot.user.name if bot.user else None

    from fastapi.responses import JSONResponse

    safe_name = "".join(c for c in (guild.name if guild else str(guild_id)) if c.isalnum() or c in "-_")[:40]
    filename = f"config-{safe_name or guild_id}-{payload['exported_at']}.json"

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{guild_id}/config/preview", summary="Check an import file without applying it")
async def preview_guild_config(guild_id: int, data: dict):
    from api.config_transfer import preview_import

    payload = data.get("config") if "config" in data else data
    try:
        return await preview_import(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{guild_id}/config/import", summary="Restore a configuration file")
async def import_guild_config(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Apply an exported configuration to this server.

    The target guild id comes from the URL, so a file exported elsewhere can
    be applied here. Existing rows for the imported tables are replaced
    unless merge=true is passed.
    """
    from api.config_transfer import import_guild
    from utils import feature_audit

    payload = data.get("config") if "config" in data else data
    replace = not bool(data.get("merge", False))
    actor = str(data.get("actor", "dashboard"))

    try:
        result = await import_guild(guild_id, payload, replace=replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Settings the bot caches in memory have to be reloaded, otherwise the
    # import only takes effect after a restart.
    try:
        from utils.Tools import invalidate_prefix_cache

        invalidate_prefix_cache(guild_id)
    except Exception:
        pass

    invalidate = getattr(bot, "invalidate_no_prefix_cache", None)
    if callable(invalidate):
        invalidate()

    await feature_audit.log_action(
        "config_imported",
        actor=actor,
        guild_id=guild_id,
        detail=f"{result['rows_written']} rows across {result['tables_written']} tables",
    )

    return {"status": "success", **result}


@router.delete("/{guild_id}/config", summary="Reset every setting for this server")
async def reset_guild_config(guild_id: int, actor: str = "", bot: "universitybot" = Depends(get_bot)):
    """Wipe all configuration rows for this guild. Cannot be undone."""
    import glob
    import os as _os

    from api.config_transfer import _tables_with_guild_id, GLOBAL_TABLES, USER_DATA_TABLES
    from utils import feature_audit

    removed = 0
    for db_path in glob.glob("db/*.db"):
        try:
            async with aiosqlite.connect(db_path) as db:
                tables = await _tables_with_guild_id(db)
                for table in tables:
                    if table in GLOBAL_TABLES or table in USER_DATA_TABLES:
                        continue
                    cursor = await db.execute(
                        f"DELETE FROM [{table}] WHERE guild_id = ?", (guild_id,)
                    )
                    removed += cursor.rowcount if cursor.rowcount > 0 else 0
                await db.commit()
        except Exception as exc:
            print(f"[config reset] {db_path}: {exc}")

    try:
        from utils.Tools import invalidate_prefix_cache

        invalidate_prefix_cache(guild_id)
    except Exception:
        pass

    await feature_audit.log_action(
        "config_reset", actor=actor, guild_id=guild_id, detail=f"{removed} rows deleted"
    )
    return {"status": "success", "rows_deleted": removed}


@router.get("/{guild_id}/module-status", summary="Which modules are actually configured")
async def get_module_status(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """
    Real configuration state per module, for the server overview.

    The overview used to show a fixed list where everything was always
    "active". This checks the databases so the page reflects reality.
    """
    import glob as _glob

    async def has_rows(db_file: str, table: str, condition: str = "") -> int:
        # Most databases live in db/, but join-to-create keeps
        # j2c_data.db in the working directory -- the cog opens it by
        # that bare name, so the path has to match exactly.
        path = db_file if os.path.exists(db_file) else f"db/{db_file}"
        if not os.path.exists(path):
            return 0
        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
                ) as cursor:
                    if not await cursor.fetchone():
                        return 0
                query = f"SELECT COUNT(*) FROM [{table}] WHERE guild_id = ?"
                if condition:
                    query += f" AND {condition}"
                async with db.execute(query, (guild_id,)) as cursor:
                    row = await cursor.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    # (key, label, database, table, extra condition, dashboard path)
    checks = [
        ("welcome", "Welcome", "welcome.db", "welcome", "", "welcome"),
        ("automod", "Automod", "automod.db", "automod", "enabled = 1", "automod"),
        ("antinuke", "Anti-Nuke", "anti.db", "antinuke", "", "antinuke"),
        ("verification", "Verification", "verification.db", "verification_config", "enabled = 1", "verification"),
        ("leveling", "Leveling", "leveling.db", "leveling_settings", "enabled = 1", "leveling"),
        ("tickets", "Tickets", "ticket.db", "guild_configs", "", "tickets"),
        ("logging", "Logging", "logging.db", "logging", "", "logging"),
        ("autorole", "Auto Role", "autorole.db", "autorole", "", "autorole"),
        ("reactionroles", "Reaction Roles", "autoreact.db", "autoreact", "", "reactionroles"),
        ("vanityroles", "Vanity Roles", "vanity.db", "vanity_roles", "", "vanityroles"),
        # custom_roles, not roles: the "roles" table also holds the
        # reqrole, so a server with only a reqrole set looked configured.
        ("customroles", "Custom Roles", "customrole.db", "custom_roles", "", "customroles"),
        ("invcrole", "Voice Roles", "invc.db", "vcrole_roles", "", "invcrole"),
        # This pointed at block.db -- the blacklist database, which has
        # no j2c table -- so Join to Create was reported as "not set up"
        # on every server no matter what. The data lives in j2c_data.db.
        ("j2c", "Join to Create", "j2c_data.db", "guild_setup",
         "join_channel_id IS NOT NULL", "j2c"),
        ("nickname", "Nicknames", "nickname.db", "nickname_rules", "", "nickname"),
        ("noprefix", "No Prefix", "np.db", "np_roles", "", "noprefix"),
        ("tracking", "Invite Tracking", "invite.db", "logging", "", "tracking"),
    ]

    modules = []
    for key, label, db_file, table, condition, path in checks:
        count = await has_rows(db_file, table, condition)
        modules.append(
            {
                "key": key,
                "label": label,
                "configured": count > 0,
                "entries": count,
                "path": path,
            }
        )

    guild = bot.get_guild(guild_id)
    prefix = ">"
    try:
        from utils.Tools import getConfig

        prefix = (await getConfig(guild_id)).get("prefix", ">")
    except Exception:
        pass

    active = sum(1 for m in modules if m["configured"])

    return {
        "guild_id": str(guild_id),
        "prefix": prefix,
        "modules": modules,
        "active_count": active,
        "total_count": len(modules),
        "completion": round((active / len(modules)) * 100) if modules else 0,
        "guild": {
            "member_count": _member_count(guild),
            "channel_count": len(guild.channels) if guild else 0,
            "role_count": len(guild.roles) if guild else 0,
            "bot_count": sum(1 for m in guild.members if m.bot) if guild else 0,
            "boost_level": getattr(guild, "premium_tier", 0) if guild else 0,
            "boost_count": getattr(guild, "premium_subscription_count", 0) if guild else 0,
            "verification_level": str(getattr(guild.verification_level, "name", "none")) if guild else "none",
            "created_at": int(guild.created_at.timestamp()) if guild and guild.created_at else 0,
            "owner_id": str(guild.owner_id) if guild else None,
        },
    }


@router.get("/{guild_id}/behaviour", summary="Per-guild behaviour settings")
async def get_guild_behaviour(guild_id: int):
    """Settings that change how the bot acts on this server."""
    from utils import guild_settings

    values = await guild_settings.load(guild_id, force=True)
    return {
        "guild_id": str(guild_id),
        "groups": list(guild_settings.SETTING_GROUPS),
        "settings": guild_settings.describe(values),
    }


@router.patch("/{guild_id}/behaviour", summary="Update behaviour settings")
async def patch_guild_behaviour(guild_id: int, data: dict):
    from utils import guild_settings, feature_audit

    payload = {k: v for k, v in data.items() if k != "actor"}
    changed = await guild_settings.set_values(guild_id, payload)

    if changed and guild_settings.get_bool(guild_id, "log_dashboard_changes"):
        await feature_audit.log_action(
            "guild_settings_changed",
            actor=str(data.get("actor", "dashboard")),
            guild_id=guild_id,
            detail=", ".join(f"{k}={v}" for k, v in changed.items())[:400],
        )

    return {"status": "success", "changed": changed}
