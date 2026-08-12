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
from utils.emoji import ARROWRED, HANDSHAKE, PC, ZMODULE
from discord.utils import *
from core import universitybot, Cog
from utils.Tools import *
from utils.config import BotName, serverLink
from discord.ext import commands
from discord.ui import Button, View

from utils import links
from utils.panels import from_embed


def _welcome_text(guild: discord.Guild) -> str:
    """
    What the bot says in the DM after being added.

    The dashboard line is only included when there is a dashboard to
    link to -- telling somebody to "open the dashboard" with no address
    is worse than not mentioning it.
    """
    lines = [
        f"{ZMODULE} **Danke fürs Hinzufügen!**",
        "",
        f"{ARROWRED} Standard-Präfix: `>`",
        f"{ARROWRED} `>help` zeigt alle Befehle",
    ]

    if links.guild_dashboard_url(guild.id):
        lines.append(
            f"{ARROWRED} Alles einstellen kannst du im **Dashboard** — "
            "der Knopf unten führt direkt zu diesem Server"
        )

    lines.append(
        f"{ARROWRED} Fragen? Der **Support-Server** hilft weiter"
    )
    return "\n".join(lines)


class Autorole(Cog):
    def __init__(self, bot: universitybot):
       self.bot = bot


    @commands.Cog.listener(name="on_guild_join")
    async def send_msg_to_adder(self, guild: discord.Guild):
        async for entry in guild.audit_logs(limit=3):
            if entry.action == discord.AuditLogAction.bot_add:
                embed = discord.Embed(
                   description=_welcome_text(guild),
                    color=0xFF0000
               )
                embed.set_thumbnail(url=entry.user.avatar.url if entry.user.avatar else entry.user.default_avatar.url)
                embed.set_author(name=f"{guild.name}", icon_url=guild.me.display_avatar.url)
               
                # The dashboard first: it is the reason most people
                # add the bot, and it is what the DM should lead with.
                #
                # The old website button pointed at "https://.vercel.app"
                # -- a URL with no host, which Discord accepts and which
                # goes nowhere. That is presumably why it was commented
                # out instead of fixed. The address now comes from
                # utils.links, which falls back to NEXTAUTH_URL: the
                # dashboard cannot log anybody in without that, so on a
                # working deployment it is always set and always right.
                view = View()

                dashboard = links.guild_dashboard_url(guild.id)
                if dashboard:
                    # Straight to *this* server's settings, not the
                    # front page -- one click less, and it makes clear
                    # which server the link is about.
                    view.add_item(Button(
                        label="Dashboard öffnen",
                        emoji=PC,
                        style=discord.ButtonStyle.link,
                        url=dashboard,
                    ))

                support = links.support_url() or 'https://discord.gg/F3TedBAVZT'
                view.add_item(Button(
                    label='Support',
                    emoji=HANDSHAKE,
                    style=discord.ButtonStyle.link,
                    url=support,
                ))
                if guild.icon:
                    embed.set_author(name=guild.name, icon_url=guild.icon.url)
                try:
                    await entry.user.send(view=from_embed(embed, view))
                except Exception as e:
                    print(e)
