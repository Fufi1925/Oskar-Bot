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

import discord
from utils.emoji import ARROWRED, BOOST, CAST, GAMES, LEVEL_UP, LOADINGRED, LOCK, MESSAGE, MINECRAFT, MUSIC, NEW, PIN, SEED, STAR, SWORD, SYSTEM, THUNDER, TICKET, WIFI, ZAI, ZARROW, ZBAN, ZBOT, ZCIRCLE_ALT1, ZCLOUD, ZCOUNTING, ZMODULE, ZPEOPLE, ZROCKET, ZSAFE, ZTADA, ZUNMUTE, ZWRENCH
from discord.ext import commands
from discord import app_commands, Interaction
from difflib import get_close_matches
from contextlib import suppress
from core import Context
from core.universitybot import universitybot
from core.Cog import Cog
from utils.Tools import getConfig
from itertools import chain
import json
from utils import help as vhelp
from utils import Paginator, DescriptionEmbedPaginator, FieldPagePaginator, TextPaginator
import asyncio
from utils.config import serverLink
from utils.Tools import *
from utils.cv2 import CV2, CV2Embed
from utils.config import *

color = 0xFF0000
client = universitybot()

from utils.config import BotName
from utils.panels import from_view

class HelpCommand(commands.HelpCommand):

  async def send_ignore_message(self, ctx, ignore_type: str):
    if ignore_type == "channel":
      await ctx.reply(f"This channel is ignored.", mention_author=False)
    elif ignore_type == "command":
      await ctx.reply(f"{ctx.author.mention} This Command, Channel, or You have been ignored here.", delete_after=6)
    elif ignore_type == "user":
      await ctx.reply(f"You are ignored.", mention_author=False)

  async def on_help_command_error(self, ctx, error):
    errors = [
      commands.CommandOnCooldown, commands.CommandNotFound,
      discord.HTTPException, commands.CommandInvokeError
    ]
    if not type(error) in errors:
      await self.context.reply(f"Unknown Error Occurred\n{error.original}",
                               mention_author=False)
    else:
      if type(error) == commands.CommandOnCooldown:
        return
    return await super().on_help_command_error(ctx, error)

  async def command_not_found(self, string: str) -> None:
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist:
        return

    if not check_ignore:
        await self.send_ignore_message(ctx, "command")
        return

    cmds = (str(cmd) for cmd in self.context.bot.walk_commands())
    matches = get_close_matches(string, cmds)

    embed = CV2Embed(
        title=f"{BotName} Helper",
        description=f">>> **Ops! Command not found with the name** `{string}`.",
        color=0xFF0000
    )

    await ctx.reply(view=embed, mention_author=True)

  async def send_bot_help(self, mapping):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist:
      return

    if not check_ignore:
      await self.send_ignore_message(ctx, "command")
      return

    # Show loading message
    loading_embed = CV2(f"{LOADINGRED} Loading help Menu...")
    loading_msg = await ctx.reply(view=loading_embed)

    # Wait 2 seconds
    await asyncio.sleep(2)

    # Delete loading message
    with suppress(discord.NotFound):
      await loading_msg.delete()

    data = await getConfig(self.context.guild.id)
    prefix = data["prefix"]
    filtered = await self.filter_commands(self.context.bot.walk_commands(), sort=True)

    # Beide Zahlen getrennt nennen.
    #
    # Hier stand nur `walk_commands()`, und das sind ausschliesslich
    # Prefix-Befehle -- die Slash-Befehle fehlten in der Zaehlung
    # vollstaendig. Seit dem Aufraeumen ist der Unterschied gross
    # genug, dass eine einzelne Zahl in die Irre fuehrt: 539 Befehle
    # per Prefix, aber nur 73 im /-Menue.
    prefix_total = len(set(self.context.bot.walk_commands()))
    try:
        slash_total = len(self.context.bot.tree.get_commands())
    except Exception:
        slash_total = 0

    dash = ""
    try:
        from utils.links import guild_dashboard_url

        dash = guild_dashboard_url(self.context.guild.id)
    except Exception:
        dash = ""

    embed = CV2Embed(
        description=(
         f"**{ARROWRED} __Start {BotName} Today__**\n"
         f"**{ZARROW} Type {prefix}antinuke enable**\n"
         f"**{ZARROW} Server Prefix:** `{prefix}`\n"
         f"**{ZARROW} Commands:** `{prefix_total}` mit Prefix · "
         f"`{slash_total}` im `/`-Menü\n"
         + (f"**{ZARROW} Einrichten:** [Dashboard]({dash})\n" if dash else "")),
        color=0xFF0000)
    
    embed.add_field(
        name=f"{ZCLOUD} Main Features",
        value=f">>> \n {ZSAFE} `»` Security\n" 
              f" {ZBOT} `»` Automoderation\n"
              f" {ZWRENCH} `»` Utility\n" 
              f" {MUSIC} `»` Music\n"
              f" {WIFI} `»` Autoreact & responder\n"
              f" {SWORD} `»` Moderation\n"
              f" {ZPEOPLE} `»` Autorole & Invc\n"
              f" {ZROCKET} `»` Fun\n"
              f" {GAMES} `»` Games\n" 
              f" {ZBAN} `»` Ignore Channels\n"
              f" {WIFI} `»` Server\n"
              f" {ZUNMUTE} `»` Voice\n"
              f" {SEED} `»` Welcomer\n"  
              f" {ZTADA} `»` Giveaway\n"
              f" {TICKET} `»` Ticket {NEW}\n"
              f" {ZPEOPLE} `»` Invite Tracker {NEW}\n"
    )
    
    embed.add_field(
        name=f" {ZMODULE} Extra Features",
        value=f">>> \n {CAST} `»` Advance Logging\n"
              f" {STAR} `»` Vanityroles\n"
              f" {ZCOUNTING} `»` Counting {NEW}\n"
              f" {SYSTEM} `»` J2C {NEW}\n"
              f" {ZAI} `»` AI {NEW}\n"
              f" {BOOST} `»` Boost {NEW}\n"
              f" {LEVEL_UP} `»` Leveling {NEW}\n"
              f" {PIN} `»` Sticky {NEW}\n"
              f" {THUNDER} `»` Verification {NEW}\n"
              f" {LOCK} `»` Encryption {NEW}\n" 
              f" {MINECRAFT} `»` Minecraft {NEW}\n"
              f" {MESSAGE} `»` Joindm {NEW}\n"
              f" {ZCIRCLE_ALT1} `»` Customrole\n"           
    )

    embed.set_footer(
      text=f"Requested By {self.context.author} | [Support](https://discord.gg/MG3rYnUZJV)",
    )
    
    view = vhelp.View(mapping=mapping, ctx=self.context, homeembed=embed, ui=2)
    await ctx.reply(view=from_view(view))

  async def send_command_help(self, command):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist:
      return

    if not check_ignore:
      await self.send_ignore_message(ctx, "command")
      return

    from utils import command_surface as surface

    universitybot = f">>> {command.help}" if command.help else '>>> No Help Provided...'

    # Wo laesst sich der Befehl aufrufen?
    #
    # Seit dem Aufraeumen des /-Menues ist das nicht mehr bei jedem
    # Befehl gleich: die Einrichtung laeuft nur noch per Prefix. Ohne
    # diesen Hinweis sucht man den Befehl im /-Menue und findet ihn
    # nicht -- und haelt ihn fuer geloescht, obwohl er funktioniert.
    slash = surface.has_slash(command)
    where = (
        f"`/{command.qualified_name}` oder `{self.context.prefix}{command.qualified_name}`"
        if slash
        else f"`{self.context.prefix}{command.qualified_name}` — nicht im `/`-Menü"
    )

    hint = surface.dashboard_hint(command, self.context.guild.id)

    embed = CV2Embed(
        description=(
            f"""{universitybot}\n\n"""
            f"{ZARROW} {where}"
            + (f"\n{ZARROW} {hint}" if hint else "")
        ),
        color=color)
    alias = ' & '.join(command.aliases)

    embed.add_field(name="**Alt cmd**",
                      value=f"```{alias}```" if command.aliases else "No Alt cmd",
                      inline=False)
    embed.add_field(name="**Usage**",
                      value=f"```{self.context.prefix}{command.signature}```\n")
    embed.set_author(name=f"{command.qualified_name.title()} Command")
    embed.set_footer(text="<[] = optional | < > = required • Use Prefix Before Commands.")
    await self.context.reply(view=embed, mention_author=False)

  def get_command_signature(self, command: commands.Command) -> str:
    parent = command.full_parent_name
    if len(command.aliases) > 0:
      aliases = ' | '.join(command.aliases)
      fmt = f'[{command.name} | {aliases}]'
      if parent:
        fmt = f'{parent}'
      alias = f'[{command.name} | {aliases}]'
    else:
      alias = command.name if not parent else f'{parent} {command.name}'
    return f'{alias} {command.signature}'

  def common_command_formatting(self, embed_like, command):
    embed_like.title = self.get_command_signature(command)
    if command.description:
      embed_like.description = f'{command.description}\n\n{command.help}'
    else:
      embed_like.description = command.help or 'No help found...'

  async def send_group_help(self, group):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist:
      return

    if not check_ignore:
      await self.send_ignore_message(ctx, "command")
      return

    from utils import command_surface as surface

    entries = [
        (
            f"`{self.context.prefix}{cmd.qualified_name}`\n",
            f"{cmd.short_doc if cmd.short_doc else ''}\n\u200b"
        )
        for cmd in group.commands
      ]

    count = len(group.commands)

    # Der Kopf der Gruppe sagt, wo sie lebt.
    #
    # Gerade bei `automod` mit dreizehn Unterbefehlen ist das die
    # Stelle, an der jemand nachschaut, warum im /-Menue nichts
    # auftaucht.
    lines = ["< > Duty | [ ] Optional"]
    if not surface.has_slash(group):
        lines.append(
            f"Nur mit Prefix: `{self.context.prefix}{group.qualified_name} …`"
        )
        hint = surface.dashboard_hint(group, self.context.guild.id)
        if hint:
            lines.append(hint)

    embeds = FieldPagePaginator(
      entries=entries,
      title=f"{group.qualified_name.title()} [{count}]",
      description="\n".join(lines) + "\n",
      per_page=4
    ).get_pages()   
    
    paginator = Paginator(ctx, embeds)
    await paginator.paginate()

  async def send_cog_help(self, cog):
    ctx = self.context
    check_ignore = await ignore_check().predicate(ctx)
    check_blacklist = await blacklist_check().predicate(ctx)

    if not check_blacklist:
      return

    if not check_ignore:
      await self.send_ignore_message(ctx, "command")
      return

    entries = [(
      f"> `{self.context.prefix}{cmd.qualified_name}`",
      f"-# Description : {cmd.short_doc if cmd.short_doc else ''}"
      f"\n\u200b",
    ) for cmd in cog.get_commands()]
    paginator = Paginator(source=FieldPagePaginator(
      entries=entries,
      title=f"{BRAND_NAME}'s {cog.qualified_name.title()} ({len(cog.get_commands())})",
      description="`<..> Required | [..] Optional`\n\n",
      color=0xFF0000,
      per_page=4),
                          ctx=self.context)
    await paginator.paginate()


class Help(Cog, name="help"):

  def __init__(self, client: universitybot):
    self._original_help_command = client.help_command
    attributes = {
      'name': "help",
      'aliases': ['h'],
      'cooldown': commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user),
      'help': 'Shows help about bot, a command, or a category'
    }
    client.help_command = HelpCommand(command_attrs=attributes)
    client.help_command.cog = self

  async def cog_unload(self):
    self.help_command = self._original_help_command