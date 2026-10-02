"""University-compatible reaction-role commands for the isolated shop bot."""
from __future__ import annotations

import discord
from discord.ext import commands

from lbost_shop_app import db
from .client import layout


def register_reaction_roles(bot) -> None:
    async def say(ctx, title: str, text: str, error: bool = False) -> None:
        await ctx.send(view=layout(title, text, color="#ed4245" if error else "#5865f2"), ephemeral=bool(ctx.interaction))

    @bot.hybrid_command(name="maakreactierol", aliases=["createrr"], description="Creëert een reactierol")
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True, add_reactions=True, read_message_history=True)
    async def createrr(ctx: commands.Context, channel: discord.TextChannel, message_id: str,
                       emoji: str, role: discord.Role):
        if not message_id.isdigit():
            return await say(ctx, "Ongeldige bericht-ID", "Kopieer de Discord-bericht-ID.", True)
        if role.managed or role >= ctx.guild.me.top_role:
            return await say(ctx, "Rol niet beheersbaar", "De rol moet lager zijn dan de hoogste botrol.", True)
        if db.reaktionsrolle(ctx.guild.id, int(message_id), emoji.strip(), bot.settings):
            return await say(ctx, "Al ingesteld", "Deze emoji is al overgenomen in het bericht.", True)
        try:
            message = await channel.fetch_message(int(message_id))
            await message.add_reaction(emoji.strip())
        except discord.NotFound:
            return await say(ctx, "Bericht niet gevonden", "Deze bericht-ID bestaat niet in het geselecteerde kanaal.", True)
        except discord.Forbidden:
            return await say(ctx, "Autorisatie ontbreekt", "De bot mag het bericht niet lezen of reacties toevoegen.", True)
        except discord.HTTPException:
            return await say(ctx, "Emoji niet bruikbaar", "Discord kent de emoji niet of de bot kan deze niet gebruiken.", True)
        db.reaktionsrolle_anlegen(ctx.guild.id, channel.id, int(message_id), emoji.strip(), role.id, bot.settings)
        await say(ctx, "Reactierol aangemaakt", f"{emoji.strip()} geeft nu {role.mention}.\n[Bericht openen]({message.jump_url})")

    @bot.hybrid_command(name="dmreactierol", aliases=["dmrr"], description="Schakelt DM's voor reactierollen in of uit")
    @commands.has_guild_permissions(manage_guild=True)
    async def dmrr(ctx: commands.Context, aktiviert: bool):
        db.reaktionsrollen_dm_setzen(ctx.guild.id, aktiviert, bot.settings)
        await say(ctx, "DM-melding", "Ingeschakeld" if aktiviert else "Uitgeschakeld")
