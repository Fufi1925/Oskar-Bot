import asyncio
from dataclasses import dataclass

import discord
from discord.ext import commands
from discord.ui import Button, View

from utils.Tools import blacklist_check, ignore_check
from utils.config import BRAND_NAME


@dataclass(frozen=True)
class RoleSpec:
    name: str
    color: int
    permissions: discord.Permissions
    hoist: bool = False
    mentionable: bool = False


class CommunityTemplateView(View):
    def __init__(self, cog: "ServerTemplates", ctx: commands.Context):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Nur der User, der den Setup gestartet hat, kann diese Auswahl benutzen.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Community Server", style=discord.ButtonStyle.primary, emoji="🌐")
    async def community_server(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🚀 Community-Template wird erstellt...", ephemeral=True)
        await self.cog.apply_community_template(self.ctx, interaction)


class ServerTemplates(commands.Cog):
    """Premium server template setup commands."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_or_create_role(self, guild: discord.Guild, spec: RoleSpec) -> discord.Role:
        role = discord.utils.get(guild.roles, name=spec.name)
        if role:
            try:
                await role.edit(
                    permissions=spec.permissions,
                    color=discord.Color(spec.color),
                    hoist=spec.hoist,
                    mentionable=spec.mentionable,
                    reason=f"{BRAND_NAME} community template update",
                )
            except discord.Forbidden:
                pass
            return role

        return await guild.create_role(
            name=spec.name,
            permissions=spec.permissions,
            color=discord.Color(spec.color),
            hoist=spec.hoist,
            mentionable=spec.mentionable,
            reason=f"{BRAND_NAME} community template setup",
        )

    async def _get_or_create_category(self, guild: discord.Guild, name: str, overwrites=None) -> discord.CategoryChannel:
        category = discord.utils.get(guild.categories, name=name)
        if category:
            if overwrites is not None:
                try:
                    await category.edit(overwrites=overwrites, reason=f"{BRAND_NAME} community template update")
                except discord.Forbidden:
                    pass
            return category
        return await guild.create_category(name=name, overwrites=overwrites, reason=f"{BRAND_NAME} community template setup")

    async def _get_or_create_text(self, guild: discord.Guild, name: str, category: discord.CategoryChannel, overwrites=None, topic: str | None = None):
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            try:
                await channel.edit(category=category, overwrites=overwrites or channel.overwrites, topic=topic, reason=f"{BRAND_NAME} community template update")
            except discord.Forbidden:
                pass
            return channel
        return await guild.create_text_channel(name=name, category=category, overwrites=overwrites, topic=topic, reason=f"{BRAND_NAME} community template setup")

    async def _get_or_create_voice(self, guild: discord.Guild, name: str, category: discord.CategoryChannel, overwrites=None, user_limit: int = 0):
        channel = discord.utils.get(guild.voice_channels, name=name)
        if channel:
            try:
                await channel.edit(category=category, overwrites=overwrites or channel.overwrites, user_limit=user_limit, reason=f"{BRAND_NAME} community template update")
            except discord.Forbidden:
                pass
            return channel
        return await guild.create_voice_channel(name=name, category=category, overwrites=overwrites, user_limit=user_limit, reason=f"{BRAND_NAME} community template setup")

    async def apply_community_template(self, ctx: commands.Context, interaction: discord.Interaction | None = None):
        guild = ctx.guild
        if guild is None:
            return

        me = guild.me or guild.get_member(self.bot.user.id)
        if not me or not me.guild_permissions.manage_roles or not me.guild_permissions.manage_channels:
            msg = "❌ Ich brauche `Manage Roles` und `Manage Channels`, um das Template zu erstellen."
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return

        progress = await ctx.send("⏳ **Community Server Template**: Rollen werden erstellt...")

        admin_perms = discord.Permissions(administrator=True)
        mod_perms = discord.Permissions(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            kick_members=True,
            ban_members=True,
            moderate_members=True,
            manage_nicknames=True,
            view_audit_log=True,
            read_message_history=True,
            connect=True,
            speak=True,
        )
        support_perms = discord.Permissions(view_channel=True, send_messages=True, manage_messages=True, read_message_history=True, connect=True, speak=True)
        member_perms = discord.Permissions(view_channel=True, send_messages=True, read_message_history=True, add_reactions=True, connect=True, speak=True, use_voice_activation=True)
        muted_perms = discord.Permissions(view_channel=True, read_message_history=True, connect=True)
        bot_perms = discord.Permissions(manage_channels=True, manage_roles=True, manage_messages=True, moderate_members=True, view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)

        role_specs = [
            RoleSpec("Administrator", 0x2563EB, admin_perms, hoist=True),
            RoleSpec("Moderator", 0x3B82F6, mod_perms, hoist=True),
            RoleSpec("Support", 0x38BDF8, support_perms, hoist=True),
            RoleSpec("VIP", 0xFACC15, member_perms, hoist=True),
            RoleSpec("Member", 0x22C55E, member_perms),
            RoleSpec("Bots", 0x64748B, bot_perms, hoist=True),
            RoleSpec("Muted", 0x334155, muted_perms),
        ]

        roles: dict[str, discord.Role] = {}
        for spec in role_specs:
            roles[spec.name] = await self._get_or_create_role(guild, spec)
            await asyncio.sleep(0.35)

        everyone = guild.default_role
        admin = roles["Administrator"]
        mod = roles["Moderator"]
        support = roles["Support"]
        muted = roles["Muted"]

        await progress.edit(content="⏳ **Community Server Template**: Kategorien und Rechte werden erstellt...")

        read_only = {
            everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
            muted: discord.PermissionOverwrite(send_messages=False, speak=False),
        }
        public = {
            everyone: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            muted: discord.PermissionOverwrite(send_messages=False, add_reactions=False, speak=False),
        }
        mod_only = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            admin: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            mod: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        support_private = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            admin: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            mod: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            support: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        voice_public = {
            everyone: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
            muted: discord.PermissionOverwrite(speak=False, send_messages=False),
        }
        afk_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False),
            muted: discord.PermissionOverwrite(speak=False),
        }

        info_cat = await self._get_or_create_category(guild, "📌 INFORMATION", read_only)
        community_cat = await self._get_or_create_category(guild, "💬 COMMUNITY", public)
        support_cat = await self._get_or_create_category(guild, "🎫 SUPPORT", public)
        mod_cat = await self._get_or_create_category(guild, "🛡️ MODERATION", mod_only)
        voice_cat = await self._get_or_create_category(guild, "🔊 VOICE", voice_public)

        await progress.edit(content="⏳ **Community Server Template**: Textkanäle werden erstellt...")

        channels = [
            ("rules", info_cat, read_only, "Server rules and important guidelines."),
            ("announcements", info_cat, read_only, "Official announcements."),
            ("welcome", info_cat, read_only, "Welcome messages and member joins."),
            ("roles", info_cat, read_only, "Role information and reaction roles."),
            ("general", community_cat, public, "Main community chat."),
            ("media", community_cat, public, "Images, clips and community media."),
            ("bot-commands", community_cat, public, "Use bot commands here."),
            ("off-topic", community_cat, public, "Off-topic discussions."),
            ("ticket-create", support_cat, public, "Open support tickets here."),
            ("support-info", support_cat, read_only, "Support information and response times."),
            ("support-team", support_cat, support_private, "Private support team coordination."),
            ("mod-chat", mod_cat, mod_only, "Private moderator chat."),
            ("logs", mod_cat, mod_only, "Bot and moderation logs. Only moderators can read this."),
            ("reports", mod_cat, mod_only, "Member reports and moderation notes."),
        ]
        for name, category, overwrites, topic in channels:
            await self._get_or_create_text(guild, name, category, overwrites, topic)
            await asyncio.sleep(0.25)

        await progress.edit(content="⏳ **Community Server Template**: Voice-Kanäle werden erstellt...")

        call1 = await self._get_or_create_voice(guild, "Call 1", voice_cat, voice_public)
        await self._get_or_create_voice(guild, "Call 2", voice_cat, voice_public)
        await self._get_or_create_voice(guild, "Call 3", voice_cat, voice_public)
        await self._get_or_create_voice(guild, "Musik", voice_cat, voice_public)
        await self._get_or_create_voice(guild, "Gaming", voice_cat, voice_public)
        afk = await self._get_or_create_voice(guild, "AFK", voice_cat, afk_overwrites)

        try:
            await guild.edit(afk_channel=afk, reason=f"{BRAND_NAME} community template setup")
        except discord.Forbidden:
            pass

        try:
            await call1.edit(position=0)
        except discord.Forbidden:
            pass

        embed = discord.Embed(
            title="✅ Community Server Template erstellt",
            description=(
                "Rollen, Farben, Kategorien, Textkanäle, Voice-Kanäle und Rechte wurden eingerichtet.\n\n"
                "**Wichtig:** Ziehe die Bot-Rolle und die neuen Team-Rollen in der Rollenliste möglichst weit nach oben, damit alle Rechte korrekt funktionieren."
            ),
            color=0x3B82F6,
        )
        embed.add_field(name="Rollen", value="Administrator, Moderator, Support, VIP, Member, Bots, Muted", inline=False)
        embed.add_field(name="Private Bereiche", value="`logs`, `mod-chat`, `reports` sind nur für Moderator/Admin sichtbar.", inline=False)
        embed.add_field(name="Voice", value="Call 1, Call 2, Call 3, Musik, Gaming, AFK", inline=False)
        embed.set_footer(text=f"Premium Template • {BRAND_NAME}")
        await progress.edit(content=None, embed=embed)

    @commands.command(name="start", aliases=["setupserver", "template"], help="Premium server template setup.")
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def start_template(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Premium Server Template Setup",
            description=(
                "Wähle aus, welches Discord Server Template erstellt werden soll.\n\n"
                "Aktuell verfügbar: **Community Server**\n"
                "Nach dem Klick startet der Bot sofort mit Rollen, Kanälen, Voice-Channels und Rechten."
            ),
            color=0x3B82F6,
        )
        embed.add_field(name="Hinweis", value="Bestehende Kanäle werden nicht gelöscht. Fehlende Elemente werden erstellt oder aktualisiert.", inline=False)
        await ctx.send(embed=embed, view=CommunityTemplateView(self, ctx))

    @start_template.error
    async def start_template_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Du brauchst Administrator-Rechte für dieses Premium Setup.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ Ich brauche `Manage Roles` und `Manage Channels`.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ Dieses Setup funktioniert nur auf einem Server.")
        else:
            raise error


async def setup(bot):
    await bot.add_cog(ServerTemplates(bot))
