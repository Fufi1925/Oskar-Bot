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
import traceback
from discord.ext import commands
from core import universitybot, Cog, Context
from utils.Tools import get_ignore_data

class Errors(Cog):
  def __init__(self, client: universitybot):
    self.client = client

  @commands.Cog.listener()
  async def on_command_error(self, ctx: Context, error):
    if ctx.command is None:
      return
    

    if isinstance(error, commands.CommandNotFound):
      return

    if isinstance(error, commands.MissingRequiredArgument):
      await ctx.send_help(ctx.command)
      ctx.command.reset_cooldown(ctx)
      return

    # NoPrivateMessage, MissingPermissions, BotMissingPermissions, NotOwner and
    # MissingRole are all subclasses of CheckFailure. They have their own
    # branches further down, so they must not be captured here. The ignore list
    # is also per guild: in a DM ctx.guild is None and reading ctx.guild.id
    # raised AttributeError inside the error handler itself.
    if (
      isinstance(error, commands.CheckFailure)
      and not isinstance(error, (
        commands.NoPrivateMessage,
        commands.MissingPermissions,
        commands.BotMissingPermissions,
        commands.MissingRole,
        commands.MissingAnyRole,
        commands.NotOwner,
      ))
      and ctx.guild is not None
    ):
      data = await get_ignore_data(ctx.guild.id)
      ch = data["channel"]
      iuser = data["user"]
      cmd = data["command"]
      buser = data["bypassuser"]

      if str(ctx.author.id) in buser:
        return

      if str(ctx.channel.id) in ch:
        await ctx.reply(f"{ctx.author.mention} **This channel was in ignored list try my commands on other channel**.",
                        delete_after=8)
        return

      if str(ctx.author.id) in iuser:
        await ctx.reply(f"{ctx.author.mention} **You are set as an ignored user for this guild. Please try my commands in a different guild.**", delete_after=8)
        return

      if ctx.command.name in cmd or any(alias in cmd for alias in ctx.command.aliases):
        await ctx.reply(f"{ctx.author.mention} **This command is ignored in this guild. Please use other commands or try this command in a different guild**", delete_after=8)
        return

    if isinstance(error, commands.NoPrivateMessage):
      embed = discord.Embed(color=0xFF0000, description="You can't use my commands in DMs.")
      embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      await ctx.reply(embed=embed, delete_after=20)
      return

    if isinstance(error, commands.TooManyArguments):
      await ctx.send_help(ctx.command)
      ctx.command.reset_cooldown(ctx)
      return

    if isinstance(error, commands.CommandOnCooldown):
      embed = discord.Embed(color=0xFF0000, description=f"**{ctx.author.mention} Couldown is here Bro Tryy commands in {error.retry_after:.2f} seconds**.")
      embed.set_author(name="Cooldown", icon_url=self.client.user.display_avatar.url)
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      await ctx.reply(embed=embed, delete_after=10)
      return

    if isinstance(error, commands.MaxConcurrencyReached):
      embed = discord.Embed(color=0xFF0000, description=f"{ctx.author.mention} This command is already in progress. Please let it finish and try again afterward.")
      embed.set_author(name="Command in Progress.", icon_url=self.client.user.display_avatar.url)
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      await ctx.reply(embed=embed, delete_after=10)
      ctx.command.reset_cooldown(ctx)
      return

    if isinstance(error, commands.MissingPermissions):
      missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in error.missing_permissions]
      fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1]) if len(missing) > 2 else " and ".join(missing)
      embed = discord.Embed(color=0xFF0000, description=f"**Ops! You don't have {fmt} Permission to run the {ctx.command.name} command!**")
      embed.set_author(name="Missing Permissions", icon_url=self.client.user.display_avatar.url)
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      await ctx.reply(embed=embed, delete_after=7)
      ctx.command.reset_cooldown(ctx)
      return

    if isinstance(error, commands.BadArgument):
      await ctx.send_help(ctx.command)
      ctx.command.reset_cooldown(ctx)
      return

    if isinstance(error, commands.BotMissingPermissions):
      missing = ", ".join(error.missing_permissions)
      await ctx.reply(f'** Huh! I need {missing} Permission to run the {ctx.command.qualified_name}command! Give me {missing} Permission**', delete_after=7)
      return

    # Everything below is a real fault, not a user mistake. Previously the
    # function just ended here: the user saw nothing happen and the log stayed
    # empty, so a broken command was invisible until someone reported it.
    await self._report_unexpected(ctx, error)

  async def _report_unexpected(self, ctx: Context, error) -> None:
    """
    Last line of defence for errors that are nobody's fault but ours.

    Writes a full stack trace to the log so the problem is visible in
    Railway, and tells the user the command failed instead of leaving
    them staring at nothing.
    """
    # CommandInvokeError wraps the exception the command actually raised.
    # The wrapper says nothing useful, so unwrap it for the trace.
    original = getattr(error, "original", error)

    where = ctx.command.qualified_name if ctx.command else "unknown command"
    guild = f"{ctx.guild.id}" if ctx.guild else "DM"
    print(f"[ERROR] Unhandled error in '{where}' (guild {guild}, user {ctx.author.id}): "
          f"{type(original).__name__}: {original}")
    trace = "".join(
      traceback.format_exception(type(original), original, original.__traceback__)
    )
    print(trace.rstrip())

    # Never let the reporting itself break the handler: the channel may be
    # gone, or we may lack permission to talk in it.
    try:
      embed = discord.Embed(
        color=0xFF0000,
        description=(
          f"**Something went wrong while running `{where}`.**\n"
          "This is a bug on our side, not something you did. "
          "It has been written to the log."
        ),
      )
      embed.set_author(name="Unexpected Error", icon_url=self.client.user.display_avatar.url)
      await ctx.reply(embed=embed, delete_after=15)
    except discord.HTTPException:
      pass

