"""University-compatible reaction-role commands for the isolated shop bot."""
from __future__ import annotations

import discord
from discord.ext import commands

from lbost_shop_app import db
from .client import layout


def register_reaction_roles(bot) -> None:
    async def say(ctx, title: str, text: str, error: bool = False) -> None:
        await ctx.send(view=layout(title, text, color="#ed4245" if error else "#5865f2"), ephemeral=bool(ctx.interaction))

    @bot.hybrid_command(name="createrr", description="Erstellt eine Reaktions-Rolle")
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True, add_reactions=True, read_message_history=True)
    async def createrr(ctx: commands.Context, channel: discord.TextChannel, message_id: str,
                       emoji: str, role: discord.Role):
        if not message_id.isdigit():
            return await say(ctx, "Ungültige Nachrichten-ID", "Kopiere die ID der Discord-Nachricht.", True)
        if role.managed or role >= ctx.guild.me.top_role:
            return await say(ctx, "Rolle nicht verwaltbar", "Die Rolle muss unter der höchsten Bot-Rolle stehen.", True)
        if db.reaktionsrolle(ctx.guild.id, int(message_id), emoji.strip(), bot.settings):
            return await say(ctx, "Bereits eingerichtet", "Dieses Emoji ist auf der Nachricht bereits vergeben.", True)
        try:
            message = await channel.fetch_message(int(message_id))
            await message.add_reaction(emoji.strip())
        except discord.NotFound:
            return await say(ctx, "Nachricht nicht gefunden", "Im ausgewählten Kanal existiert diese Nachrichten-ID nicht.", True)
        except discord.Forbidden:
            return await say(ctx, "Berechtigung fehlt", "Der Bot darf die Nachricht nicht lesen oder keine Reaktionen hinzufügen.", True)
        except discord.HTTPException:
            return await say(ctx, "Emoji nicht verwendbar", "Discord kennt das Emoji nicht oder der Bot kann es nicht benutzen.", True)
        db.reaktionsrolle_anlegen(ctx.guild.id, channel.id, int(message_id), emoji.strip(), role.id, bot.settings)
        await say(ctx, "Reaktions-Rolle erstellt", f"{emoji.strip()} gibt jetzt {role.mention}.\n[Nachricht öffnen]({message.jump_url})")

    @bot.hybrid_command(name="dmrr", description="Schaltet DMs für Reaktions-Rollen ein oder aus")
    @commands.has_guild_permissions(manage_guild=True)
    async def dmrr(ctx: commands.Context, aktiviert: bool):
        db.reaktionsrollen_dm_setzen(ctx.guild.id, aktiviert, bot.settings)
        await say(ctx, "DM-Benachrichtigung", "Aktiviert" if aktiviert else "Deaktiviert")
