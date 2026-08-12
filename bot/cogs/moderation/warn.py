# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import discord
from utils.emoji import DELETE, TICK
from discord.ext import commands
from discord import ui
import asyncio
from utils.Tools import *
from utils.panels import from_embed
from utils import warn_store


#class WarnView(ui.View):
 #   def __init__(self, user, author):
       # super().__init__(timeout=60)
       # self.user = user
      #  self.author = author
       # self.message = None

   # async def interaction_check(self, interaction: discord.Interaction) -> bool:
       # if interaction.user != self.author:
          #  await interaction.response.send_message("You are not allowed to interact with this!", ephemeral=True)
        #    return False
       # return True

   # async def on_timeout(self):
       # for item in self.children:
         #   item.disabled = True
      #  if self.message:
         #   try:
             #   await self.message.edit(view=self)
         #   except Exception:
            #    pass

   # @ui.button(style=discord.ButtonStyle.gray, emoji=DELETE)
  #  async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
      #  await interaction.message.delete()


class Warn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = discord.Color.from_rgb(255, 0, 0)
        self.db_path = "db/warn.db"

        
        asyncio.create_task(self.setup())

    def get_user_avatar(self, user):
        return user.avatar.url if user.avatar else user.default_avatar.url

    # Alle vier Methoden gehen ueber utils/warn_store.py. Vorher stand das
    # SQL hier und eine zweite, abweichende Fassung in
    # api/routes/moderation.py -- der Cog kannte nur den Zaehler, das
    # Dashboard zusaetzlich das Protokoll mit Grund und Moderator. Beide
    # schrieben in dieselbe Datei, also zeigte das Dashboard Warnungen
    # ohne Grund an und behielt geloeschte Warnungen bei. Eine gemeinsame
    # Schicht kann nicht mehr auseinanderlaufen.

    async def add_warn(self, guild_id: int, user_id: int, *, reason: str = "",
                       moderator_id: int | None = None):
        return await warn_store.add(
            guild_id, user_id, reason=reason, moderator_id=moderator_id
        )

    async def get_total_warns(self, guild_id: int, user_id: int):
        return await warn_store.count_of(guild_id, user_id)

    async def reset_warns(self, guild_id: int, user_id: int):
        return await warn_store.clear(guild_id, user_id)

    async def setup(self):
        try:
            async with warn_store.db_paths.connect(warn_store.WARN_DB) as db:
                await warn_store.ensure_schema(db)
        except Exception as e:
            print(f"Error during database setup: {e}")

    @commands.hybrid_command(
        name="warn",
        help="Warn a user in the server",
        usage="warn <user> [reason]",
        aliases=["warnuser"])
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    #@commands.bot_has_permissions(manage_messages=True)
    async def warn(self, ctx, user: discord.Member, *, reason=None):
        if user == ctx.author:
            return await ctx.reply("You cannot warn yourself.")

        if user == ctx.bot.user:
            return await ctx.reply("You cannot warn me.")

        if not ctx.author == ctx.guild.owner:
            if user == ctx.guild.owner:
                return await ctx.reply("I cannot warn the server owner.")

            if ctx.author.top_role <= user.top_role:
                return await ctx.reply("You cannot Warn a member with a higher or equal role.")

        if ctx.guild.me.top_role <= user.top_role:
            return await ctx.reply("I cannot Warn a member with a higher or equal role.")

        if user not in ctx.guild.members:
            return await ctx.reply("The user is not a member of this server.")
        try:
            
            reason_to_send = reason or "No reason provided"

            # Grund und Moderator gehen mit in die Datenbank. Vorher kannte
            # nur die DM an den Betroffenen den Grund -- im Dashboard stand
            # danach eine nackte Zahl.
            total_warns = await self.add_warn(
                ctx.guild.id,
                user.id,
                reason=reason_to_send,
                moderator_id=ctx.author.id,
            )

            try:
                await user.send(f"You have been warned in **{ctx.guild.name}** by **{ctx.author}**. Reason: {reason_to_send}")
                dm_status = "Yes"
            except discord.Forbidden:
                dm_status = "No"
            except discord.HTTPException:
                dm_status = "No"

            
            embed = discord.Embed(description=f"**{TICK} | Successfully Warned [{user}](https://discord.com/users/{user.id})\nReason {reason_to_send}\nNow He has {total_warns} Warns**",
                                              color=self.color)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.set_author(name=f"Successfully Warned {user.name}", icon_url=self.get_user_avatar(user))
            #embed.add_field(name="Moderator:", value=ctx.author.mention, inline=False)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=self.get_user_avatar(ctx.author))
            embed.timestamp = discord.utils.utcnow()

           # view = WarnView(user=user, author=ctx.author)
            message = await ctx.send(view=from_embed(embed))
          #  view.message = message
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            print(f"Error during warn command: {e}")

    @commands.hybrid_command(
        name="clearwarns",
        help="Clear all warnings for a user",
        aliases=["clearwarn" , "clearwarnings"],
        usage="clearwarns <user>")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def clearwarns(self, ctx, user: discord.Member):
        try:
            # reset_warns nimmt jetzt auch die Protokolleintraege zurueck.
            # Vorher blieben die auf active = 1 stehen, also zeigte das
            # Dashboard die geloeschten Warnungen munter weiter an.
            entfernt = await self.reset_warns(ctx.guild.id, user.id)
            anzahl = (
                f" ({entfernt} " + ("Eintrag" if entfernt == 1 else "Eintraege") + ")"
                if entfernt
                else ""
            )
            embed = discord.Embed(description=f"{TICK} | All warnings have been cleared for **{user}** in this guild.{anzahl}", color=self.color)
            embed.set_author(name=f"Warnings Cleared", icon_url=self.get_user_avatar(user))
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=self.get_user_avatar(ctx.author))
            embed.timestamp = discord.utils.utcnow()

            await ctx.send(view=from_embed(embed))
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            print(f"Error during clearwarns command: {e}")

