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

import os
import sys
import subprocess
# os.system("")
import asyncio
import traceback
from threading import Thread
from datetime import datetime
import random
import time

import aiohttp
import aiosqlite
import discord
from discord import Spotify
from discord.ext import commands, tasks

# Create db/, jsondb/ and the JSON files before anything else runs, because
# utils.Tools opens db/prefix.db at import time.
#
# This is loaded straight from its file rather than with `import
# utils.bootstrap`. Importing the submodule would execute utils/__init__.py,
# which imports Tools -> core -> back into utils, and that circular chain
# fails while utils is still half-initialised.
def _run_bootstrap():
    import importlib.util
    import os

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils", "bootstrap.py")
    spec = importlib.util.spec_from_file_location("_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

_run_bootstrap()

from core import Context
from core.Cog import Cog
from core.universitybot import universitybot
from utils.Tools import *
from utils.config import *
from utils.emoji import SUCCESS, ERROR, TICK, CROSS, REACTION_TEST_EMOJIS
from utils.sync_emojis import run_sync

import jishaku
import cogs


os.environ["JISHAKU_NO_DM_TRACEBACK"] = "False"
os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_FORCE_PAGINATOR"] = "True"

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("TOKEN")

# --- Configuration ---
# These used to be hardcoded channel IDs pointing at somebody else's server,
# which silently did nothing on every other deployment. They now come from
# utils/bot_settings.py and are editable in the dashboard; an environment
# variable of the same name still takes precedence.
from utils import bot_settings


def _stats_channels() -> tuple[int, int]:
    return (
        bot_settings.get_int("stats_server_channel"),
        bot_settings.get_int("stats_user_channel"),
    )


def _guild_log_channel() -> int:
    return bot_settings.get_int("guild_log_channel")


client = universitybot()
tree = client.tree

# --- Background Task for Stats ---
async def update_stats():
    """A background task to update server and user stats in channel names."""
    await client.wait_until_ready()
    await bot_settings.load()

    while not client.is_closed():
        interval = max(60, bot_settings.get_int("stats_interval", 600))
        try:
            server_channel_id, user_channel_id = _stats_channels()

            # Nothing configured yet — skip quietly instead of spamming errors.
            if server_channel_id or user_channel_id:
                servers = len(client.guilds)
                users = sum(
                    guild.member_count for guild in client.guilds
                    if guild.member_count is not None
                )

                server_channel = client.get_channel(server_channel_id) if server_channel_id else None
                user_channel = client.get_channel(user_channel_id) if user_channel_id else None

                if server_channel:
                    await server_channel.edit(name=f"Servers: {servers}")

                if user_channel:
                    await user_channel.edit(name=f"Users: {users}")

        except Exception as e:
            print(f"Error updating stats: {e}")

        await asyncio.sleep(interval)

# --- Event Handlers ---
@client.event
async def on_ready():
    await client.wait_until_ready()
    
    print("""
        \033[1;31m
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
        \033[0m
       """)
    print("Loaded & Online!")
    print(f"Logged in as: {client.user}")
    print(f"Connected to: {len(client.guilds)} guilds")
    print(f"Connected to: {len(client.users)} users")

    # Sync application emojis on startup
    await run_sync(TOKEN)

    async def sync_commands():
        try:
            synced = await client.tree.sync()
            all_commands = list(client.commands)
            print(f"Synced Total {len(all_commands)} Client Commands and {len(synced)} Slash Commands")
        except Exception as e:
            print(f"Error syncing command tree: {e}")

    asyncio.create_task(sync_commands())
    asyncio.create_task(update_stats())


@client.event
async def on_guild_join(guild: discord.Guild):
    # Log when the bot joins a server
    log_channel_id = _guild_log_channel()
    log_channel = client.get_channel(log_channel_id) if log_channel_id else None
    if log_channel:
        await log_channel.send(f"{BRAND_NAME} has been added to the server: **{guild.name}** (ID: `{guild.id}`)")

async def apply_nickname_rules(member: discord.Member):
    """Apply dashboard-configured prefix/suffix nickname rules for matching roles."""
    if member.bot or not member.guild:
        return
    guild = member.guild
    me = guild.me or guild.get_member(client.user.id) if client.user else None
    if not me or not me.guild_permissions.manage_nicknames:
        return
    if member.top_role >= me.top_role or member.guild_permissions.administrator:
        return

    try:
        async with aiosqlite.connect("db/nickname.db") as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS nickname_rules (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    prefix TEXT DEFAULT '',
                    suffix TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    PRIMARY KEY (guild_id, role_id)
                )
            ''')
            async with db.execute(
                "SELECT role_id, prefix, suffix FROM nickname_rules WHERE guild_id = ? AND enabled = 1",
                (guild.id,),
            ) as cursor:
                rules = await cursor.fetchall()
    except Exception as exc:
        print(f"Nickname rule load failed: {exc}")
        return

    if not rules:
        return

    role_ids = {role.id for role in member.roles}
    current_name = member.nick or member.name
    base_name = current_name
    for _, prefix, suffix in rules:
        prefix = prefix or ""
        suffix = suffix or ""
        if prefix and base_name.startswith(prefix):
            base_name = base_name[len(prefix):]
        if suffix and base_name.endswith(suffix):
            base_name = base_name[:-len(suffix)]
    base_name = base_name.strip() or member.name

    matched = next(((prefix or "", suffix or "") for role_id, prefix, suffix in rules if int(role_id) in role_ids), None)
    if matched:
        prefix, suffix = matched
        desired = f"{prefix}{base_name}{suffix}"[:32]
    else:
        # Role removed: remove known affixes if they are present, otherwise leave the nickname alone.
        if base_name == current_name:
            return
        desired = base_name[:32]

    if desired == member.name:
        desired = None
    if member.nick != desired:
        try:
            await member.edit(nick=desired, reason=f"{BRAND_NAME} dashboard nickname rule")
        except Exception as exc:
            print(f"Nickname update failed for {member.id}: {exc}")

client.apply_nickname_rules = apply_nickname_rules

@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles != after.roles or before.nick != after.nick:
        await apply_nickname_rules(after)

@client.event
async def on_command_completion(context: commands.Context) -> None:
    if context.guild:
        try:
            async with aiosqlite.connect("db/settings.db") as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS guild_extra_settings (
                        guild_id INTEGER PRIMARY KEY,
                        delete_command_messages INTEGER DEFAULT 0,
                        mention_prefix_response INTEGER DEFAULT 1,
                        same_voice_only INTEGER DEFAULT 1
                    )
                ''')
                async with db.execute("SELECT delete_command_messages FROM guild_extra_settings WHERE guild_id = ?", (context.guild.id,)) as cursor:
                    row = await cursor.fetchone()
            if row and row[0]:
                try:
                    await context.message.delete()
                except Exception:
                    pass
        except Exception:
            pass

    if context.author.id in OWNER_IDS:
        return

    full_command_name = context.command.qualified_name
    split = full_command_name.split("\n")
    executed_command = str(split[0])
    webhook_url = bot_settings.get("command_log_webhook") or CMD_WEBHOOK_URL

    # Without this guard discord.Webhook.from_url(None) raises on *every*
    # command when CMD_WEBHOOK_URL is not configured.
    if not webhook_url:
        return

    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)

        embed_color = 0xFF0000
        embed = discord.Embed(color=embed_color)
        avatar_url = context.author.display_avatar.url

        embed.set_author(name=f"Cmd Executed: {executed_command}", icon_url=avatar_url)
        embed.set_thumbnail(url=avatar_url)

        if context.guild is not None:
            embed.add_field(name="User", value=f"{context.author.mention} (`{context.author.id}`)", inline=False)
            embed.add_field(name="Server", value=f"{context.guild.name} (`{context.guild.id}`)", inline=False)
            embed.add_field(name="Channel", value=f"{context.channel.mention} (`{context.channel.id}`)", inline=False)
        else:
            embed.add_field(name="User (DM)", value=f"{context.author.mention} (`{context.author.id}`)", inline=False)
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"{BRAND_NAME} Development™ ❤️", icon_url=client.user.display_avatar.url)
        
        try:
            await webhook.send(embed=embed)
        except Exception as e:
            print(f'Command log webhook failed: {e}')


# --- Utility Commands ---
@client.command(name='spotify')
async def spotify(ctx: Context, user: discord.Member = None):
    """Shows what a user is listening to on Spotify."""
    user = user or ctx.author
    spotify_activity = next((activity for activity in user.activities if isinstance(activity, Spotify)), None)

    if not spotify_activity:
        return await ctx.send(f"{user.name} is not listening to Spotify.")
    
    embed = discord.Embed(
        title=f"{user.name}'s Spotify",
        description=f"**Listening to:** {spotify_activity.title}",
        color=0x1DB954 # Spotify Green
    )
    embed.set_thumbnail(url=spotify_activity.album_cover_url)
    embed.add_field(name="Artist", value=spotify_activity.artist)
    embed.add_field(name="Album", value=spotify_activity.album)
    embed.set_footer(text=f"Song started at {spotify_activity.created_at.strftime('%H:%M')}")
    await ctx.send(embed=embed)


@client.command(name='makeinvite', aliases=['createinvite', 'makeinv'])
@commands.is_owner()
async def make_invite(ctx: Context, guild_id: int = None):
    """Creates an invite for a specified server (owner only)."""
    if guild_id is None:
        return await ctx.send("Please provide a Guild ID.")
        
    guild = client.get_guild(guild_id)
    if not guild:
        return await ctx.send("Invalid Guild ID. I am not in that server.")

    if guild.system_channel and guild.system_channel.permissions_for(guild.me).create_instant_invite:
        try:
            invite = await guild.system_channel.create_invite(max_age=0, max_uses=0, unique=True, reason="Owner requested invite.")
            return await ctx.send(f"Invite for **{guild.name}**:\n{invite.url}")
        except Exception:
            pass

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).create_instant_invite:
            try:
                invite = await channel.create_invite(max_age=0, max_uses=0, unique=True, reason="Owner requested invite.")
                return await ctx.send(f"Invite for **{guild.name}** (from #{channel.name}):\n{invite.url}")
            except Exception:
                continue
                
    await ctx.send(f"I don't have 'Create Instant Invite' permission in any channel in **{guild.name}**.")


# --- Webhook Management Commands ---
@client.command(name='create_hook', aliases=['makehook'])
@commands.has_permissions(administrator=True)
async def create_hook(ctx: Context, *, name: str = None):
    """Creates a webhook in the current channel."""
    if name is None:
        return await ctx.send("Please provide a name for the webhook.")
    
    try:
        webhook = await ctx.channel.create_webhook(name=name, reason=f"Created by {ctx.author}")
        embed = discord.Embed(
            title=f"{SUCCESS} Webhook Created",
            description=f"A webhook named **{webhook.name}** was created.",
            color=0xFF0000
        )
        try:
            await ctx.author.send(
                f"Webhook URL for **{webhook.name}** in **{ctx.channel.name}**:\n||{webhook.url}||",
                embed=embed,
            )
            await ctx.send("Webhook created. I've sent the URL to your DMs.")
        except discord.Forbidden:
            await ctx.send(f"Webhook created: **{webhook.name}**\n||{webhook.url}||\n(I could not DM you the URL.)")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create webhooks here.")
    except Exception as exc:
        print(f"Webhook creation failed: {exc}")
        await ctx.send("Webhook creation failed unexpectedly.")


@client.command(name='delete_hook', aliases=['delhook'])
@commands.has_permissions(administrator=True)
async def delete_hook(ctx: Context, webhook_url: str = None):
    """Deletes a webhook using its URL."""
    if webhook_url is None:
        return await ctx.send("Please provide the webhook URL to delete.")

    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            await webhook.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(f"{SUCCESS} Webhook deleted successfully.")
    except (discord.NotFound, ValueError):
        await ctx.send(f"{ERROR} Webhook not found or URL is invalid.")


@client.command(name='list_hooks', aliases=['hooks'])
@commands.has_permissions(administrator=True)
async def list_hooks(ctx: Context):
    """Lists all webhooks in the current channel."""
    try:
        webhooks = await ctx.channel.webhooks()
        if not webhooks:
            return await ctx.send("No webhooks found in this channel.")

        embed = discord.Embed(title=f"Webhooks in #{ctx.channel.name}", color=0xFF0000)
        description = "\n".join([f"**Name:** {wh.name} | **ID:** `{wh.id}`" for wh in webhooks])
        embed.description = description
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have permission to view webhooks in this channel.")


# --- Game Command ---
@client.command()
async def reaction(ctx: Context):
    """See how fast you can react to the correct emoji."""
    emojis = ["🍪", "🎉", "🧋", "🍒", "🍑", "💸", "🌙", "💕"]
    correct_emoji = random.choice(emojis)
    random.shuffle(emojis)
    
    embed = discord.Embed(
        title="Reaction Test",
        description="I will show an emoji in a few seconds. Get ready to click it!",
        color=0xFF0000
    )
    message = await ctx.send(embed=embed)
    
    for emoji in emojis:
        await message.add_reaction(emoji)
        
    await asyncio.sleep(random.uniform(2.0, 7.0))
    
    embed.description = f"**GET THE {correct_emoji} EMOJI!**"
    await message.edit(embed=embed)
    start_time = time.time()

    def check(reaction, user):
        return (
            reaction.message.id == message.id
            and str(reaction.emoji) == correct_emoji
            and user == ctx.author
        )

    try:
        reaction, user = await client.wait_for("reaction_add", timeout=15.0, check=check)
        end_time = time.time()
        reaction_time = end_time - start_time
        
        embed.description = f"{user.mention} got the {correct_emoji} in **{reaction_time:.2f} seconds**!"
        await message.edit(embed=embed)
    except asyncio.TimeoutError:
        embed.description = "Timeout! You were too slow."
        await message.edit(embed=embed)


# ---API Server for Dashboard Backend ---
import uvicorn
from threading import Thread
from api.server import create_app
from api.dependencies import set_bot

fastapi_app = create_app()
fastapi_app.state.bot = client
set_bot(client)

API_ENABLED = os.getenv("API_ENABLED", "true").strip().lower() == "true"
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

def run_api():
    uvicorn.run(fastapi_app, host='0.0.0.0', port=API_PORT, log_level="warning")

def keep_alive():
    if not API_ENABLED:
        print(f"\033[33m◈ API+Dashboard Server: Disabled via API_ENABLED=false\033[0m")
        return
    print(f"\033[32m◈ API+Dashboard Server: Starting on port {API_PORT}\033[0m")
    server = Thread(target=run_api, daemon=True)
    server.start()

keep_alive()


# --- Main Bot Execution ---
# Exit code the wrapper script understands as "do not restart quickly".
RATE_LIMIT_EXIT_CODE = 75


async def main():
    async with client:
        # os.system("clear")  # disabled for Railway container
        await client.load_extension("jishaku")

        # Login rate limits are per IP and get WORSE with every attempt, so
        # retrying fast is actively harmful. The old loop tried five times
        # with 1-16s backoff, gave up, and start.sh restarted it after five
        # seconds — roughly 65 login attempts in nine minutes, which kept the
        # block alive indefinitely.
        max_retries = 3
        base_wait = 60

        for attempt in range(max_retries):
            try:
                await client.start(TOKEN)
                return
            except discord.HTTPException as exc:
                if exc.status != 429:
                    raise

                # Discord tells us how long to wait; trust it when present.
                retry_after = 0.0
                try:
                    payload = exc.response.headers if exc.response is not None else {}
                    retry_after = float(payload.get("Retry-After", 0))
                except Exception:
                    retry_after = 0.0

                wait_time = max(retry_after, base_wait * (2 ** attempt))
                wait_time = min(wait_time, 900) + random.random() * 5

                if attempt == max_retries - 1:
                    break

                print(
                    f"⏳ Login rate limited by Discord (429). "
                    f"Waiting {wait_time / 60:.1f} minutes before retry "
                    f"{attempt + 2}/{max_retries}."
                )
                await asyncio.sleep(wait_time)

        print(
            "\n"
            "❌ Could not log in: Discord is rate limiting this IP.\n"
            "\n"
            "   Retrying immediately makes it worse, so the process now stops.\n"
            "   Common causes:\n"
            "     • the container restarted many times in a row\n"
            "     • several instances running with the same token\n"
            "     • the token was reset while an instance was still running\n"
            "\n"
            "   What to do: stop the service, wait 15-30 minutes, start it once.\n"
            "   If it persists, reset the bot token in the Discord developer portal.\n"
        )
        # Signals start.sh to back off instead of restarting after 5 seconds.
        sys.exit(RATE_LIMIT_EXIT_CODE)

if __name__ == "__main__":
    asyncio.run(main())
