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
            await say(ctx, "Nur auf Servern", "Dieser Befehl funktioniert nicht in Direktnachrichten.", error=True)
            return False
        if not bot.feature(ctx.guild.id, "moderation").get("enabled"):
            await say(ctx, "Moderation deaktiviert", "Aktiviere das Modul zuerst im Dashboard.", error=True)
            return False
        return True

    async def manageable(ctx: commands.Context, member: discord.Member) -> bool:
        if member.id in {ctx.author.id, ctx.guild.owner_id, bot.user.id}:
            await say(ctx, "Aktion abgelehnt", "Dieses Mitglied kann mit dieser Aktion nicht moderiert werden.", error=True)
            return False
        if member.top_role >= ctx.guild.me.top_role:
            await say(ctx, "Bot-Rolle zu niedrig", "Verschiebe die Bot-Rolle über die höchste Rolle des Mitglieds.", error=True)
            return False
        cfg = bot.feature(ctx.guild.id, "moderation")
        if cfg.get("topcheck", True) and ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
            await say(ctx, "Rollen-Hierarchie", "Du kannst keine gleich oder höher eingeordnete Person moderieren.", error=True)
            return False
        return True

    async def dm(member: discord.abc.User, guild: discord.Guild, action: str, reason: str) -> str:
        try:
            await member.send(view=layout(f"Moderation in {guild.name}", f"Aktion: **{action}**\nGrund: {reason}"))
            return "zugestellt"
        except (discord.Forbidden, discord.HTTPException):
            return "nicht zustellbar"

    def reason(value: str | None) -> str:
        return (value or "Kein Grund angegeben").strip()[:500]

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, commands.CommandNotFound):
            return
        if isinstance(original, commands.MissingPermissions):
            return await say(ctx, "Keine Berechtigung", "Dir fehlen die erforderlichen Discord-Berechtigungen.", error=True)
        if isinstance(original, commands.BotMissingPermissions):
            return await say(ctx, "Bot-Berechtigung fehlt", "Dem Bot fehlen die erforderlichen Serverrechte.", error=True)
        if isinstance(original, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await say(ctx, "Ungültige Eingabe", f"Prüfe die Argumente für `{ctx.clean_prefix}{ctx.command.qualified_name}`.", error=True)
        await say(ctx, "Befehl fehlgeschlagen", "Die Aktion konnte nicht sicher ausgeführt werden. Prüfe Rollen und Berechtigungen.", error=True)

    @bot.listen("on_message_delete")
    async def moderation_snipe_store(message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            snipes[message.channel.id] = (message.author, message.content or "Keine Textnachricht", discord.utils.utcnow())
            if len(snipes) > 2000:
                snipes.pop(next(iter(snipes)))

    @bot.hybrid_command(name="warn", description="Verwarnt ein Mitglied")
    @commands.has_guild_permissions(moderate_members=True)
    async def warn(ctx: commands.Context, member: discord.Member, *, grund: str = "Kein Grund angegeben"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund)
        nummer = db.warnung_anlegen(ctx.guild.id, member.id, ctx.author.id, grund, bot.settings)
        count = db.warnungen_fuer_nutzer(ctx.guild.id, member.id, bot.settings)
        status = await dm(member, ctx.guild, f"Verwarnung #{nummer}", grund)
        await say(ctx, "Verwarnung gespeichert", f"Fall **#{nummer}** · {member.mention}\nGrund: {grund}\nAktive Verwarnungen: **{count}** · DM: {status}")
        await bot.log(ctx.guild, "Verwarnung", f"Fall: #{nummer}\nMitglied: {member.mention}\nModerator: {ctx.author.mention}\nGrund: {grund}", "moderation")

    @bot.hybrid_command(name="warnings", description="Zeigt Verwarnungen eines Mitglieds")
    @commands.has_guild_permissions(moderate_members=True)
    async def warnings(ctx: commands.Context, member: discord.Member):
        if not await ready(ctx): return
        rows = [x for x in db.warnungen_fuer_gilde(ctx.guild.id, bot.settings, 200) if int(x["user_id"]) == member.id]
        text = "\n".join(f"**#{x['case_number'] or x['id']}** · <@{x['moderator_id']}> · {str(x['reason'])[:180]}" for x in rows[:15])
        await say(ctx, f"Verwarnungen: {member}", text or "Keine aktiven Verwarnungen.")

    async def clear_member_warnings(ctx: commands.Context, member: discord.Member):
        if not await ready(ctx): return
        amount = db.warnungen_loeschen_nutzer(ctx.guild.id, member.id, bot.settings)
        await say(ctx, "Verwarnungen gelöscht", f"**{amount}** Einträge von {member.mention} wurden entfernt.")

    @bot.hybrid_command(name="clearwarns", description="Löscht alle Verwarnungen eines Mitglieds")
    @commands.has_guild_permissions(moderate_members=True)
    async def clearwarns(ctx: commands.Context, member: discord.Member):
        await clear_member_warnings(ctx, member)

    @bot.hybrid_command(name="clearwarnings", description="Löscht alle Verwarnungen eines Mitglieds")
    @commands.has_guild_permissions(moderate_members=True)
    async def clearwarnings(ctx: commands.Context, member: discord.Member):
        await clear_member_warnings(ctx, member)

    @bot.hybrid_command(name="mute", aliases=["timeout"], description="Setzt ein Mitglied in Timeout")
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def mute(ctx: commands.Context, member: discord.Member, minuten: commands.Range[int, 1, 40320], *, grund: str = "Kein Grund angegeben"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund)
        await member.timeout(timedelta(minutes=minuten), reason=f"{ctx.author}: {grund}")
        status = await dm(member, ctx.guild, f"Timeout ({minuten} Minuten)", grund)
        await say(ctx, "Timeout gesetzt", f"{member.mention} · **{minuten} Minuten**\nGrund: {grund}\nDM: {status}")

    @bot.hybrid_command(name="unmute", description="Entfernt den Timeout eines Mitglieds")
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def unmute(ctx: commands.Context, member: discord.Member, *, grund: str = "Timeout aufgehoben"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.timeout(None, reason=f"{ctx.author}: {reason(grund)}")
        await say(ctx, "Timeout aufgehoben", f"{member.mention} kann wieder schreiben.")

    @bot.hybrid_command(name="kick", description="Entfernt ein Mitglied vom Server")
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_guild_permissions(kick_members=True)
    async def kick(ctx: commands.Context, member: discord.Member, *, grund: str = "Kein Grund angegeben"):
        if not await ready(ctx) or not await manageable(ctx, member): return
        grund = reason(grund); status = await dm(member, ctx.guild, "Kick", grund)
        await member.kick(reason=f"{ctx.author}: {grund}")
        await say(ctx, "Mitglied entfernt", f"**{member}** wurde entfernt.\nGrund: {grund}\nDM: {status}")

    @bot.hybrid_command(name="ban", description="Bannt ein Mitglied oder eine Nutzer-ID")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def ban(ctx: commands.Context, user: discord.User, *, grund: str = "Kein Grund angegeben"):
        if not await ready(ctx): return
        member = ctx.guild.get_member(user.id)
        if member and not await manageable(ctx, member): return
        grund = reason(grund); status = await dm(user, ctx.guild, "Ban", grund)
        await ctx.guild.ban(user, reason=f"{ctx.author}: {grund}")
        await say(ctx, "Mitglied gebannt", f"**{user}** wurde gebannt.\nGrund: {grund}\nDM: {status}")

    @bot.hybrid_command(name="unban", description="Entbannt eine Nutzer-ID")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def unban(ctx: commands.Context, user_id: str, *, grund: str = "Ban aufgehoben"):
        if not await ready(ctx) or not user_id.isdigit(): return
        user = await bot.fetch_user(int(user_id)); await ctx.guild.unban(user, reason=f"{ctx.author}: {reason(grund)}")
        await say(ctx, "Ban aufgehoben", f"**{user}** darf dem Server wieder beitreten.")

    async def channel_overwrite(ctx: commands.Context, channel: discord.abc.GuildChannel, *, send: bool | None = None, view: bool | None = None, label: str):
        if not await ready(ctx): return
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if send is not None: overwrite.send_messages = send
        if view is not None: overwrite.view_channel = view
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{label} by {ctx.author}")
        await say(ctx, label, f"{channel.mention} wurde aktualisiert.")

    @bot.hybrid_command(name="lock", description="Sperrt einen Kanal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def lock(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, send=False, label="Kanal gesperrt")

    @bot.hybrid_command(name="unlock", description="Entsperrt einen Kanal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def unlock(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, send=None, label="Kanal entsperrt")

    @bot.hybrid_command(name="hide", description="Versteckt einen Kanal")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def hide(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, view=False, label="Kanal versteckt")

    @bot.hybrid_command(name="unhide", description="Macht einen Kanal wieder sichtbar")
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def unhide(ctx: commands.Context, channel: discord.TextChannel | None = None): await channel_overwrite(ctx, channel or ctx.channel, view=None, label="Kanal sichtbar")

    async def all_channels(ctx: commands.Context, field: str, value: bool | None, title: str):
        if not await ready(ctx): return
        done = 0
        for channel in ctx.guild.channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role); setattr(overwrite, field, value)
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{title} by {ctx.author}"); done += 1
            except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, title, f"**{done}** Kanäle wurden aktualisiert.")

    @bot.hybrid_command(name="lockall", description="Sperrt alle Kanäle")
    @commands.has_guild_permissions(administrator=True)
    async def lockall(ctx): await all_channels(ctx, "send_messages", False, "Alle Kanäle gesperrt")
    @bot.hybrid_command(name="unlockall", description="Entsperrt alle Kanäle")
    @commands.has_guild_permissions(administrator=True)
    async def unlockall(ctx): await all_channels(ctx, "send_messages", None, "Alle Kanäle entsperrt")
    @bot.hybrid_command(name="hideall", description="Versteckt alle Kanäle")
    @commands.has_guild_permissions(administrator=True)
    async def hideall(ctx): await all_channels(ctx, "view_channel", False, "Alle Kanäle versteckt")
    @bot.hybrid_command(name="unhideall", description="Macht alle Kanäle sichtbar")
    @commands.has_guild_permissions(administrator=True)
    async def unhideall(ctx): await all_channels(ctx, "view_channel", None, "Alle Kanäle sichtbar")

    @bot.hybrid_command(name="slowmode", description="Setzt den Slowmode")
    @commands.has_guild_permissions(manage_channels=True)
    async def slowmode(ctx, sekunden: commands.Range[int, 0, 21600], channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; await channel.edit(slowmode_delay=sekunden, reason=f"By {ctx.author}")
        await say(ctx, "Slowmode aktualisiert", f"{channel.mention}: **{sekunden} Sekunden**")
    @bot.hybrid_command(name="unslowmode", description="Entfernt den Slowmode")
    @commands.has_guild_permissions(manage_channels=True)
    async def unslowmode(ctx, channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; await channel.edit(slowmode_delay=0, reason=f"By {ctx.author}"); await say(ctx, "Slowmode entfernt", channel.mention)

    @bot.hybrid_command(name="nick", description="Ändert den Nickname eines Mitglieds")
    @commands.has_guild_permissions(manage_nicknames=True)
    async def nick(ctx, member: discord.Member, *, nickname: str = ""):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.edit(nick=nickname[:32] or None, reason=f"By {ctx.author}"); await say(ctx, "Nickname aktualisiert", member.mention)

    @bot.hybrid_command(name="prefix", description="Ändert das Präfix für Hybrid-Befehle")
    @commands.has_guild_permissions(administrator=True)
    async def prefix(ctx, value: str):
        if not await ready(ctx): return
        value = value.strip()[:10]
        if not value or any(char.isspace() for char in value):
            return await say(ctx, "Ungültiges Präfix", "Nutze 1 bis 10 Zeichen ohne Leerzeichen.", error=True)
        cfg = bot.feature(ctx.guild.id, "moderation"); cfg["prefix"] = value
        db.set_feature(ctx.guild.id, "moderation", cfg, ctx.author.id, bot.settings)
        bot.feature_cache.pop((ctx.guild.id, "moderation"), None)
        await say(ctx, "Präfix geändert", f"Neue Präfix-Befehle beginnen mit `{value}`.")

    @bot.hybrid_command(name="roleicon", description="Setzt oder entfernt das Symbol einer Rolle")
    @commands.has_guild_permissions(manage_roles=True)
    async def roleicon(ctx, role: discord.Role, bild: discord.Attachment | None = None):
        if not await ready(ctx): return
        if role >= ctx.guild.me.top_role:
            return await say(ctx, "Bot-Rolle zu niedrig", "Diese Rolle kann der Bot nicht bearbeiten.", error=True)
        icon = await bild.read() if bild else None
        await role.edit(display_icon=icon, reason=f"By {ctx.author}")
        await say(ctx, "Rollensymbol aktualisiert", role.mention)

    @bot.hybrid_command(name="unbanall", description="Entbannt alle gesperrten Nutzer")
    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def unbanall(ctx):
        if not await ready(ctx): return
        entries = [entry async for entry in ctx.guild.bans(limit=None)]
        done = 0
        for entry in entries:
            try: await ctx.guild.unban(entry.user, reason=f"Unbanall by {ctx.author}"); done += 1
            except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, "Alle Bans aufgehoben", f"**{done}** Nutzer wurden entbannt.")

    @bot.hybrid_command(name="clone", description="Klont einen Kanal ohne den ursprünglichen zu löschen")
    @commands.has_guild_permissions(manage_channels=True)
    async def clone(ctx, channel: discord.TextChannel | None = None):
        if not await ready(ctx): return
        channel = channel or ctx.channel; new = await channel.clone(reason=f"By {ctx.author}"); await new.edit(position=channel.position + 1)
        await say(ctx, "Kanal geklont", new.mention)

    @bot.hybrid_command(name="snipe", description="Zeigt die zuletzt gelöschte Nachricht")
    @commands.has_guild_permissions(manage_messages=True)
    async def snipe(ctx):
        if not await ready(ctx): return
        item = snipes.get(ctx.channel.id)
        await say(ctx, "Zuletzt gelöschte Nachricht", f"Von {item[0].mention}\n{item[1][:1800]}" if item else "Keine gelöschte Nachricht gespeichert.")

    @bot.hybrid_command(name="clear", aliases=["purge"], description="Löscht Nachrichten mit optionalem Filter")
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_messages=True)
    async def clear(ctx, anzahl: commands.Range[int, 1, 1000], filter: str = "all", wert: str = ""):
        if not await ready(ctx): return
        mode = filter.lower(); needle = wert.casefold()
        def check(m: discord.Message) -> bool:
            return mode == "all" or (mode in {"bot","bots"} and m.author.bot) or (mode in {"embed","embeds"} and bool(m.embeds)) or (mode in {"file","files","image","images"} and bool(m.attachments)) or (mode in {"mention","mentions"} and bool(m.mentions)) or (mode == "contains" and needle in m.content.casefold()) or (mode in {"reaction","reactions"} and bool(m.reactions)) or (mode == "user" and str(m.author.id) == wert)
        deleted = await ctx.channel.purge(limit=anzahl + 1, check=check, reason=f"By {ctx.author}")
        await say(ctx, "Nachrichten gelöscht", f"**{max(0, len(deleted)-1)}** Nachrichten entfernt.")

    @bot.hybrid_group(name="role", fallback="give", description="Verwaltet Rollen")
    @commands.has_guild_permissions(manage_roles=True)
    async def role(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.add_roles(role, reason=f"By {ctx.author}"); await say(ctx, "Rolle vergeben", f"{role.mention} an {member.mention}")

    @role.command(name="remove", description="Entfernt eine Rolle")
    async def role_remove(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.remove_roles(role, reason=f"By {ctx.author}"); await say(ctx, "Rolle entfernt", f"{role.mention} von {member.mention}")
    @role.command(name="create", description="Erstellt eine Rolle")
    async def role_create(ctx, *, name: str):
        if not await ready(ctx): return
        new = await ctx.guild.create_role(name=name[:100], reason=f"By {ctx.author}"); await say(ctx, "Rolle erstellt", new.mention)
    @role.command(name="delete", description="Löscht eine Rolle")
    async def role_delete(ctx, role: discord.Role):
        if not await ready(ctx): return
        name=role.name; await role.delete(reason=f"By {ctx.author}"); await say(ctx, "Rolle gelöscht", name)
    @role.command(name="rename", description="Benennt eine Rolle um")
    async def role_rename(ctx, role: discord.Role, *, name: str):
        if not await ready(ctx): return
        await role.edit(name=name[:100], reason=f"By {ctx.author}"); await say(ctx, "Rolle umbenannt", role.mention)
    @role.command(name="temp", description="Vergibt eine Rolle vorübergehend")
    async def role_temp(ctx, member: discord.Member, role: discord.Role, minuten: commands.Range[int, 1, 10080]):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.add_roles(role, reason=f"Temporary by {ctx.author}"); await say(ctx, "Temporäre Rolle", f"{role.mention} bleibt **{minuten} Minuten** bei {member.mention}.")
        async def later():
            await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(minutes=minuten))
            try: await member.remove_roles(role, reason="Temporary role expired")
            except (discord.Forbidden, discord.HTTPException): pass
        bot.loop.create_task(later())

    async def mass_role(ctx, role: discord.Role, mode: str, remove: bool):
        if not await ready(ctx): return
        done=0
        for member in ctx.guild.members:
            wanted = mode == "all" or (mode == "bots" and member.bot) or (mode == "humans" and not member.bot) or (mode == "unverified" and member.pending)
            if wanted and member != ctx.guild.me:
                try:
                    await (member.remove_roles(role, reason=f"By {ctx.author}") if remove else member.add_roles(role, reason=f"By {ctx.author}")); done += 1
                except (discord.Forbidden, discord.HTTPException): pass
        await say(ctx, "Massen-Rollenaktion abgeschlossen", f"**{done}** Mitglieder aktualisiert.")
    def add_mode_command(mode: str):
        async def callback(ctx, role: discord.Role):
            await mass_role(ctx, role, mode, False)
        callback.__name__ = f"role_{mode}"
        return callback
    for mode in ("all", "humans", "bots", "unverified"):
        role.command(name=mode, description=f"Vergibt eine Rolle an {mode}")(add_mode_command(mode))

    @bot.hybrid_group(name="removerole", fallback="one", description="Entfernt Rollen")
    @commands.has_guild_permissions(manage_roles=True)
    async def removerole(ctx, member: discord.Member, role: discord.Role):
        if not await ready(ctx) or not await manageable(ctx, member): return
        await member.remove_roles(role, reason=f"By {ctx.author}"); await say(ctx, "Rolle entfernt", f"{role.mention} von {member.mention}")
    def remove_mode_command(mode: str):
        async def callback(ctx, role: discord.Role):
            await mass_role(ctx, role, mode, True)
        callback.__name__ = f"removerole_{mode}"
        return callback
    for mode in ("all", "humans", "bots", "unverified"):
        removerole.command(name=mode, description=f"Entfernt eine Rolle von {mode}")(remove_mode_command(mode))

    @bot.hybrid_command(name="audit", description="Zeigt den jüngsten Audit-Log-Eintrag")
    @commands.has_guild_permissions(view_audit_log=True)
    async def audit(ctx):
        if not await ready(ctx): return
        entry = await anext(ctx.guild.audit_logs(limit=1), None)
        text = f"Aktion: **{entry.action.name}**\nVon: {entry.user}\nZiel: {entry.target}\nGrund: {entry.reason or 'Kein Grund'}" if entry else "Kein Eintrag gefunden."
        await say(ctx, "Audit-Log", text)

    @bot.hybrid_command(name="delemoji", aliases=["deleteemoji"], description="Löscht ein Server-Emoji")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def delemoji(ctx, emoji: discord.Emoji):
        if not await ready(ctx): return
        name=emoji.name; await emoji.delete(reason=f"By {ctx.author}"); await say(ctx, "Emoji gelöscht", name)
    @bot.hybrid_command(name="delsticker", aliases=["deletesticker"], description="Löscht einen Server-Sticker")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def delsticker(ctx, sticker: discord.GuildSticker):
        if not await ready(ctx): return
        name=sticker.name; await sticker.delete(reason=f"By {ctx.author}"); await say(ctx, "Sticker gelöscht", name)

    @bot.hybrid_command(name="steal", description="Kopiert ein Emoji in diesen Server")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def steal(ctx, emoji: str, name: str = "copied"):
        if not await ready(ctx): return
        match = re.search(r"<(a?):[^:]+:(\d+)>", emoji)
        if not match: return await say(ctx, "Ungültiges Emoji", "Sende ein benutzerdefiniertes Discord-Emoji.", error=True)
        ext="gif" if match.group(1) else "png"
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://cdn.discordapp.com/emojis/{match.group(2)}.{ext}") as response:
                data = await response.read()
        created=await ctx.guild.create_custom_emoji(name=name[:32], image=data, reason=f"By {ctx.author}"); await say(ctx, "Emoji kopiert", str(created))

    @bot.hybrid_command(name="enlarge", description="Zeigt ein benutzerdefiniertes Emoji groß")
    async def enlarge(ctx, emoji: str):
        match = re.search(r"<(a?):[^:]+:(\d+)>", emoji)
        if not match: return await say(ctx, "Ungültiges Emoji", "Sende ein benutzerdefiniertes Discord-Emoji.", error=True)
        ext="gif" if match.group(1) else "png"; await ctx.send(view=layout("Emoji", f"https://cdn.discordapp.com/emojis/{match.group(2)}.{ext}"))

    @bot.hybrid_group(name="topcheck", fallback="status", description="Verwaltet die Rollen-Hierarchieprüfung")
    async def topcheck(ctx):
        cfg=bot.feature(ctx.guild.id,"moderation"); await say(ctx,"Topcheck", "Aktiv" if cfg.get("topcheck",True) else "Inaktiv")
    async def set_topcheck(ctx, value: bool):
        if ctx.author.id != ctx.guild.owner_id: return await say(ctx,"Nur Serverinhaber","Nur der Serverinhaber darf Topcheck ändern.",error=True)
        cfg=bot.feature(ctx.guild.id,"moderation"); cfg["topcheck"]=value; db.set_feature(ctx.guild.id,"moderation",cfg,ctx.author.id,bot.settings); bot.feature_cache.pop((ctx.guild.id,"moderation"),None); await say(ctx,"Topcheck", "Aktiviert" if value else "Deaktiviert")
    @topcheck.command(name="enable", description="Aktiviert Topcheck")
    async def topcheck_enable(ctx): await set_topcheck(ctx,True)
    @topcheck.command(name="disable", description="Deaktiviert Topcheck")
    async def topcheck_disable(ctx): await set_topcheck(ctx,False)
