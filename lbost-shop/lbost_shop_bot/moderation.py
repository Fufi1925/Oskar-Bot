"""Isolated University-parity moderation commands for the LBoost Shop bot.

No University database/cog is imported: the command surface and safety rules are
mirrored while all state remains in the LBoost database.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from lbost_shop_app import db
from .client import layout


def register_moderation(bot: Any) -> None:
    snipes: dict[int, tuple[discord.abc.User, str, discord.utils.utcnow]] = {}

    async def say(ctx: commands.Context, title: str, text: str, *, error: bool = False) -> None:
        await ctx.send(view=layout(title, text, color="#ed4245" if error else "#5865f2"))

    async def ready(ctx: commands.Context) -> bool:
        if not ctx.guild:
            await say(ctx, "Alleen op servers", "Deze opdracht werkt niet in directe berichten.", error=True)
            return False
        if not bot.feature(ctx.guild.id, "moderation").get("enabled"):
            await say(ctx, "Moderatie uitgeschakeld", "Activeer eerst de module in het dashboard.", error=True)
            return False
        return True

    async def manageable(ctx: commands.Context, member: discord.Member) -> bool:
        if member.id in {ctx.author.id, ctx.guild.owner_id, bot.user.id}:
            await say(ctx, "Actie afgewezen", "Dit lid kan niet worden gemodereerd met deze actie.", error=True)
            return False
        if member.top_role >= ctx.guild.me.top_role:
            await say(ctx, "Botrol te laag", "Verplaats de botrol boven de hoogste rol van het lid.", error=True)
            return False
        cfg = bot.feature(ctx.guild.id, "moderation")
        if cfg.get("topcheck", True) and ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
            await say(ctx, "Rollen-Hierarchie", "Je kunt niet iemand modereren die op dezelfde of hogere rang staat.", error=True)
            return False
        return True

    async def dm(member: discord.abc.User, guild: discord.Guild, action: str, reason: str) -> str:
        try:
            await member.send(view=layout(f"Moderation in {guild.name}", f"Aktion: **{action}**\nGrund: {reason}"))
            return "zugestellt"
        except (discord.Forbidden, discord.HTTPException):
            return "niet leverbaar"

    def reason(value: str | None) -> str:
        return (value or "Geen reden gegeven").strip()[:500]

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, commands.CommandNotFound):
            return
        if isinstance(original, commands.MissingPermissions):
            return await say(ctx, "Geen toestemming", "Je beschikt niet over de vereiste Discord-machtigingen.", error=True)
        if isinstance(original, commands.BotMissingPermissions):
            return await say(ctx, "Bot-toestemming ontbreekt", "De bot mist de vereiste serverrechten.", error=True)
        if isinstance(original, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await say(ctx, "Ongeldige invoer", f"Controleer de argumenten voor `{ctx.clean_prefix}{ctx.command.qualified_name}`.", error=True)
        await say(ctx, "Commando mislukt", "De actie kon niet veilig worden uitgevoerd. Controleer rollen en machtigingen.", error=True)

    @bot.listen("on_message_delete")
    async def moderation_snipe_store(message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            snipes[message.channel.id] = (message.author, message.content or "Geen sms", discord.utils.utcnow())
            if len(snipes) > 2000:
                snipes.pop(next(iter(snipes)))

    @bot.hybrid_command(name="waarschuw", description="Waarschuwt een lid")
    @commands.has_guild_permissions(moderate_members=True)
    async def warn(ctx: commands.Context, member: discord.Member, *, grund: str = "Geen reden gegeven"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund)
        nummer = db.warnung_anlegen(ctx.guild.id, member.id, ctx.author.id, grund, bot.settings)
        count = db.warnungen_fuer_nutzer(ctx.guild.id, member.id, bot.settings)
        status = await dm(member, ctx.guild, f"Waarschuwing #{nummer}", grund)
        await say(ctx, "Waarschuwing opgeslagen", f"Fall **#{nummer}** · {member.mention}\nGrund: {grund}\nAktive Verwarnungen: **{count}** · DM: {status}")
        await bot.log(ctx.guild, "Waarschuwing", f"Fall: #{nummer}\nLid: {member.mention}\nModerator: {ctx.author.mention}\nGrund: {grund}", "moderation")

    @bot.hybrid_command(name="waarschuwingen", description="Toont waarschuwingen van een lid")
    @commands.has_guild_permissions(moderate_members=True)
    async def warnings(ctx: commands.Context, member: discord.Member):
        if not await ready(ctx): return
        rows = [x for x in db.warnungen_fuer_gilde(ctx.guild.id, bot.settings, 200) if int(x["user_id"]) == member.id]
        text = "\n".join(f"**#{x['case_number'] or x['id']}** · <@{x['moderator_id']}> · {str(x['reason'])[:180]}" for x in rows[:15])
        await say(ctx, f"Verwarnungen: {member}", text or "Geen actieve waarschuwingen.")

    async def clear_member_warnings(ctx: commands.Context, member: discord.Member):
        if not await ready(ctx): return
        amount = db.warnungen_loeschen_nutzer(ctx.guild.id, member.id, bot.settings)
        await say(ctx, "Waarschuwingen verwijderd", f"**{amount}** vermeldingen van {member.mention} wurden entfernt.")

    @bot.hybrid_command(name="wiswaarschuwingen", description="Verwijdert alle waarschuwingen voor een lid")
    @commands.has_guild_permissions(moderate_members=True)
    async def clearwarns(ctx: commands.Context, member: discord.Member):
        await clear_member_warnings(ctx, member)

    @bot.hybrid_command(name="wisallewaarschuwingen", description="Verwijdert alle waarschuwingen voor een lid")
    @commands.has_guild_permissions(moderate_members=True)
    async def clearwarnings(ctx: commands.Context, member: discord.Member):
        await clear_member_warnings(ctx, member)

    @bot.hybrid_command(name="demp", aliases=["timeout"], description="Plaatst een lid in een time-out")
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def mute(ctx: commands.Context, member: discord.Member, minuten: commands.Range[int, 1, 40320], *, grund: str = "Geen reden gegeven"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund)
        await member.timeout(timedelta(minutes=minuten), reason=f"{ctx.author}: {grund}")
        status = await dm(member, ctx.guild, f"Timeout ({minuten} Minuten)", grund)
        await say(ctx, "Time-out ingesteld", f"{member.mention} · **{minuten} Minuten**\nGrund: {grund}\nDM: {status}")

    @bot.hybrid_command(name="ontdemp", description="Verwijdert de time-out van een lid")
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def unmute(ctx: commands.Context, member: discord.Member, *, grund: str = "Time-out geannuleerd"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.timeout(None, reason=f"{ctx.author}: {reason(grund)}")
        await say(ctx, "Time-out geannuleerd", f"{member.mention} kann wieder schreiben.")

    @bot.hybrid_command(name="verwijder", description="Verwijdert een lid van de server")
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_guild_permissions(kick_members=True)
    async def kick(ctx: commands.Context, member: discord.Member, *, grund: str = "Geen reden gegeven"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund); status = await dm(member, ctx.guild, "Schop", grund)
        await member.kick(reason=f"{ctx.author}: {grund}")
        await say(ctx, "Lid verwijderd", f"**{member}** is verwijderd.\nReden: {grund}\nDM: {status}")

    @bot.hybrid_command(name="verban", description="Verbiedt een lid of gebruikers-ID")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def ban(ctx: commands.Context, user: discord.User, *, grund: str = "Geen reden gegeven"):
        if not await ready(ctx): return
        member = ctx.guild.get_member(user.id)
        if member and not await manageable(ctx, member): return
        grund = reason(grund); status = await dm(user, ctx.guild, "Verbod", grund)
        await ctx.guild.ban(user, reason=f"{ctx.author}: {grund}")
        await say(ctx, "Lid uitgesloten", f"**{user}** is verbannen.\nReden: {grund}\nDM: {status}")

    @bot.hybrid_command(name="ontban", description="Heft de ban van een gebruikers-ID op")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def unban(ctx: commands.Context, user_id: str, *, grund: str = "Verbod opgeheven"):
        if not await ready(ctx) or not user_id.isdigit(): return
        user = await bot.fetch_user(int(user_id)); await ctx.guild.unban(user, reason=f"{ctx.author}: {reason(grund)}")
        await say(ctx, "Verbod opgeheven", f"**{user}** mag weer deelnemen aan de server.")

    async def channel_overwrite(ctx: commands.Context, channel: discord.abc.GuildChannel, *, send: bool | None = None, view: bool | None = None, label: str):
        if not await ready(ctx): return
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if send is not None: overwrite.send_messages = send
        if view is not None: overwrite.view_channel = view
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{label} by {ctx.author}")
        await say(ctx, label, f"{channel.mention} is bijgewerkt.")

    @bot.hybrid_command(name="vergrendel", description="Blokkeert een kanaal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def lock(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, send=False, label="Kanaal geblokkeerd")

    @bot.hybrid_command(name="ontgrendel", description="Deblokkeert een kanaal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def unlock(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, send=None, label="Kanaal gedeblokkeerd")

    @bot.hybrid_command(name="verberg", description="Verbergt een kanaal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def hide(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, view=False, label="Kanaal verborgen")

    @bot.hybrid_command(name="toon", description="Maakt een kanaal weer zichtbaar")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def unhide(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, view=None, label="Kanaal zichtbaar")

    async def all_channels(ctx: commands.Context, field: str, value: bool | None, title: str):
        if not await ready(ctx): return
        done = 0
        for channel in ctx.guild.channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role); setattr(overwrite, field, value)
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{title} by {ctx.author}"); done += 1
            except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, title, f"**{done}** kanalen zijn bijgewerkt.")

    @bot.hybrid_command(name="vergrendelalles", description="Blokkeert alle kanalen")
    @commands.has_guild_permissions(administrator=True)
    async def lockall(ctx): await all_channels(ctx, "send_messages", False, "Alle kanalen geblokkeerd")
    @bot.hybrid_command(name="ontgrendelalles", description="Deblokkeert alle kanalen")
    @commands.has_guild_permissions(administrator=True)
    async def unlockall(ctx): await all_channels(ctx, "send_messages", None, "Alle kanalen gedeblokkeerd")
    @bot.hybrid_command(name="verbergalles", description="Verbergt alle kanalen")
    @commands.has_guild_permissions(administrator=True)
    async def hideall(ctx): await all_channels(ctx, "view_channel", False, "Alle kanalen verborgen")
    @bot.hybrid_command(name="toonalles", description="Maakt alle kanalen zichtbaar")
    @commands.has_guild_permissions(administrator=True)
    async def unhideall(ctx): await all_channels(ctx, "view_channel", None, "Alle kanalen zichtbaar")

    @bot.hybrid_command(name="traagmodus", description="Stelt de langzame modus in")
    @commands.has_guild_permissions(manage_channels=True)
    async def slowmode(ctx, sekunden: commands.Range[int, 0, 21600], channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; await channel.edit(slowmode_delay=sekunden, reason=f"Door {ctx.author}")
        await say(ctx, "Bijgewerkte langzame modus", f"{channel.mention}: **{sekunden} Sekunden**")
    @bot.hybrid_command(name="resettraagmodus", description="Verwijdert de langzame modus")
    @commands.has_guild_permissions(manage_channels=True)
    async def unslowmode(ctx, channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; await channel.edit(slowmode_delay=0, reason=f"Door {ctx.author}"); await say(ctx, "Langzame modus verwijderd", channel.mention)

    @bot.hybrid_command(name="bijnaam", description="Verandert de bijnaam van een lid")
    @commands.has_guild_permissions(manage_nicknames=True)
    async def nick(ctx, member: discord.Member, *, nickname: str = ""):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.edit(nick=nickname[:32] or None, reason=f"Door {ctx.author}"); await say(ctx, "Bijnaam bijgewerkt", member.mention)

    @bot.hybrid_command(name="voorvoegsel", description="Wijzigt het voorvoegsel voor hybride opdrachten")
    @commands.has_guild_permissions(administrator=True)
    async def prefix(ctx, value: str):
        if not await ready(ctx): return
        value = value.strip()[:10]
        if not value or any(char.isspace() for char in value):
            return await say(ctx, "Ongeldig voorvoegsel", "Gebruik 1 tot 10 tekens zonder spaties.", error=True)
        cfg = bot.feature(ctx.guild.id, "moderation"); cfg["prefix"] = value
        db.set_feature(ctx.guild.id, "moderation", cfg, ctx.author.id, bot.settings)
        bot.feature_cache.pop((ctx.guild.id, "moderation"), None)
        await say(ctx, "Voorvoegsel gewijzigd", f"Nieuwe prefixcommando’s beginnen met `{value}`.")

    @bot.hybrid_command(name="rolicoon", description="Stelt het symbool van een rol in of verwijdert het")
    @commands.has_guild_permissions(manage_roles=True)
    async def roleicon(ctx, role: discord.Role, bild: discord.Attachment | None = None):
        if not await ready(ctx): return
        if role >= ctx.guild.me.top_role:
            return await say(ctx, "Botrol te laag", "De bot kan deze rol niet bewerken.", error=True)
        icon = await bild.read() if bild else None
        await role.edit(display_icon=icon, reason=f"Door {ctx.author}")
        await say(ctx, "Bijgewerkt rolpictogram", role.mention)

    @bot.hybrid_command(name="ontbanalles", description="Heft de ban op van alle verboden gebruikers")
    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def unbanall(ctx):
        if not await ready(ctx): return
        entries = [entry async for entry in ctx.guild.bans(limit=None)]
        done = 0
        for entry in entries:
            try: await ctx.guild.unban(entry.user, reason=f"Unbanall by {ctx.author}"); done += 1
            except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, "Alle verboden opgeheven", f"**{done}** gebruikers zijn ontbannen.")

    @bot.hybrid_command(name="kloon", description="Kloont een kanaal zonder het originele kanaal te verwijderen")
    @commands.has_guild_permissions(manage_channels=True)
    async def clone(ctx, channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; new = await channel.clone(reason=f"Door {ctx.author}"); await new.edit(position=channel.position + 1)
        await say(ctx, "Kanaal gekloond", new.mention)

    @bot.hybrid_command(name="laatstebericht", description="Toont het meest recent verwijderde bericht")
    @commands.has_guild_permissions(manage_messages=True)
    async def snipe(ctx):
        if not await ready(ctx): return
        item = snipes.get(ctx.channel.id)
        await say(ctx, "Laatst verwijderd bericht", f"Door {item[0].mention}\n{item[1][:1800]}" if item else "Geen verwijderd bericht opgeslagen.")

    @bot.hybrid_command(name="wis", aliases=["purge"], description="Verwijdert berichten met optioneel filter")
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_messages=True)
    async def clear(ctx, anzahl: commands.Range[int, 1, 1000], filter: str = "all", wert: str = ""):
        if not await ready(ctx): return
        mode = filter.lower(); needle = wert.casefold()
        def check(m: discord.Message) -> bool:
            return mode == "all" or (mode in {"bot","bots"} and m.author.bot) or (mode in {"embed","embeds"} and bool(m.embeds)) or (mode in {"file","files","image","images"} and bool(m.attachments)) or (mode in {"mention","mentions"} and bool(m.mentions)) or (mode == "contains" and needle in m.content.casefold()) or (mode in {"reaction","reactions"} and bool(m.reactions)) or (mode == "user" and str(m.author.id) == wert)
        deleted = await ctx.channel.purge(limit=anzahl + 1, check=check, reason=f"Door {ctx.author}")
        await say(ctx, "Berichten verwijderd", f"**{max(0, len(deleted)-1)}** Nachrichten entfernt.")

    @bot.hybrid_group(name="rol", fallback="geef", description="Beheert rollen")
    @commands.has_guild_permissions(manage_roles=True)
    async def role(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.add_roles(role, reason=f"Door {ctx.author}"); await say(ctx, "Rol toewijzen", f"{role.mention} aan {member.mention}")

    @role.command(name="verwijder", description="Verwijdert een rol")
    async def role_remove(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.remove_roles(role, reason=f"Door {ctx.author}"); await say(ctx, "Rol verwijderd", f"{role.mention} van {member.mention}")
    @role.command(name="maak", description="Creëert een rol")
    async def role_create(ctx, *, name: str):
        if not await ready(ctx): return
        new = await ctx.guild.create_role(name=name[:100], reason=f"Door {ctx.author}"); await say(ctx, "Rol gemaakt", new.mention)
    @role.command(name="wis", description="Verwijdert een rol")
    async def role_delete(ctx, role: discord.Role):
        if not await ready(ctx): return
        name=role.name; await role.delete(reason=f"Door {ctx.author}"); await say(ctx, "Rol verwijderd", name)
    @role.command(name="hernoem", description="Hernoemt een rol")
    async def role_rename(ctx, role: discord.Role, *, name: str):
        if not await ready(ctx): return
        await role.edit(name=name[:100], reason=f"Door {ctx.author}"); await say(ctx, "Rol hernoemd", role.mention)
    @role.command(name="tijdelijk", description="Wijst tijdelijk een rol toe")
    async def role_temp(ctx, member: discord.Member, role: discord.Role, minuten: commands.Range[int, 1, 10080]):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.add_roles(role, reason=f"Temporary by {ctx.author}"); await say(ctx, "Tijdelijke rol", f"{role.mention} bleibt **{minuten} Minuten** bei {member.mention}.")
        async def later():
            await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(minutes=minuten))
            try: await member.remove_roles(role, reason="Tijdelijke rol verlopen")
            except (discord.Forbidden, discord.HTTPException): pass
        bot.loop.create_task(later())

    async def mass_role(ctx, role: discord.Role, mode: str, remove: bool):
        if not await ready(ctx): return
        done=0
        for member in ctx.guild.members:
            wanted = mode == "all" or (mode == "bots" and member.bot) or (mode == "humans" and not member.bot) or (mode == "unverified" and member.pending)
            if wanted and member != ctx.guild.me:
                try:
                    await (member.remove_roles(role, reason=f"Door {ctx.author}") if remove else member.add_roles(role, reason=f"Door {ctx.author}")); done += 1
                except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, "Massarolactie voltooid", f"**{done}** Mitglieder aktualisiert.")
    def add_mode_command(mode: str):
        async def callback(ctx, role: discord.Role):
            await mass_role(ctx, role, mode, False)
        callback.__name__ = f"role_{mode}"
        return callback
    for mode in ("all", "humans", "bots", "unverified"):
        role.command(name=mode, description=f"Geeft een rol aan {mode}")(add_mode_command(mode))

    @bot.hybrid_group(name="verwijderrol", fallback="een", description="Verwijdert rollen")
    @commands.has_guild_permissions(manage_roles=True)
    async def removerole(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.remove_roles(role, reason=f"Door {ctx.author}"); await say(ctx, "Rol verwijderd", f"{role.mention} van {member.mention}")
    def remove_mode_command(mode: str):
        async def callback(ctx, role: discord.Role):
            await mass_role(ctx, role, mode, True)
        callback.__name__ = f"removerole_{mode}"
        return callback
    for mode in ("all", "humans", "bots", "unverified"):
        removerole.command(name=mode, description=f"Verwijdert een rol van {mode}")(remove_mode_command(mode))

    @bot.hybrid_command(name="audit", description="Toont de meest recente vermelding in het auditlogboek")
    @commands.has_guild_permissions(view_audit_log=True)
    async def audit(ctx):
        if not await ready(ctx): return
        entry = await anext(ctx.guild.audit_logs(limit=1), None)
        text = f"Aktion: **{entry.action.name}**\nDoor: {entry.user}\nZiel: {entry.target}\nGrund: {entry.reason or 'Geen reden'}" if entry else "Geen vermelding gevonden."
        await say(ctx, "Audit-Log", text)

    @bot.hybrid_command(name="verwijderemoji", aliases=["deleteemoji"], description="Verwijdert een server-emoji")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def delemoji(ctx, emoji: discord.Emoji):
        if not await ready(ctx): return
        name=emoji.name; await emoji.delete(reason=f"Door {ctx.author}"); await say(ctx, "Emoji verwijderd", name)
    @bot.hybrid_command(name="verwijdersticker", aliases=["deletesticker"], description="Verwijdert een serversticker")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def delsticker(ctx, sticker: discord.GuildSticker):
        if not await ready(ctx): return
        name=sticker.name; await sticker.delete(reason=f"Door {ctx.author}"); await say(ctx, "Sticker verwijderd", name)

    @bot.hybrid_command(name="kopieeremoji", description="Kopieert een emoji naar deze server")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def steal(ctx, emoji: str, name: str = "copied"):
        if not await ready(ctx): return
        match = re.search(r"<(a?):[^:]+:(\d+)>", emoji)
        if not match: return await say(ctx, "Ongeldige emoji", "Stuur een aangepaste Discord-emoji.", error=True)
        ext="gif" if match.group(1) else "png"
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://cdn.discordapp.com/emojis/{match.group(2)}.{ext}") as response:
                data = await response.read()
        created=await ctx.guild.create_custom_emoji(name=name[:32], image=data, reason=f"Door {ctx.author}"); await say(ctx, "Emoji gekopieerd", str(created))

    @bot.hybrid_command(name="vergroot", description="Geeft een aangepaste emoji groot weer")
    async def enlarge(ctx, emoji: str):
        match = re.search(r"<(a?):[^:]+:(\d+)>", emoji)
        if not match: return await say(ctx, "Ongeldige emoji", "Stuur een aangepaste Discord-emoji.", error=True)
        ext="gif" if match.group(1) else "png"; await ctx.send(view=layout("Emoji", f"https://cdn.discordapp.com/emojis/{match.group(2)}.{ext}"))

    @bot.hybrid_group(name="hierarchiecontrole", fallback="status", description="Beheert de controle van de rollenhiërarchie")
    async def topcheck(ctx):
        cfg=bot.feature(ctx.guild.id,"moderation"); await say(ctx,"Topcontrole", "Actief" if cfg.get("topcheck",True) else "Inactief")
    async def set_topcheck(ctx, value: bool):
        if ctx.author.id != ctx.guild.owner_id: return await say(ctx,"Alleen servereigenaar","Alleen de servereigenaar mag Topcheck wijzigen.",error=True)
        cfg=bot.feature(ctx.guild.id,"moderation"); cfg["topcheck"]=value; db.set_feature(ctx.guild.id,"moderation",cfg,ctx.author.id,bot.settings); bot.feature_cache.pop((ctx.guild.id,"moderation"),None); await say(ctx,"Topcontrole", "Ingeschakeld" if value else "Uitgeschakeld")
    @topcheck.command(name="inschakelen", description="Activeert Topcheck")
    async def topcheck_enable(ctx): await set_topcheck(ctx,True)
    @topcheck.command(name="uitschakelen", description="Schakelt Topcheck uit")
    async def topcheck_disable(ctx): await set_topcheck(ctx,False)
