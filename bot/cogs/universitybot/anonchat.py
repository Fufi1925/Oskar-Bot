# ╔══════════════════════════════════════════════════════════════════╗
# ║   Help entry: anonymous chat                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

import discord
from discord.ext import commands


class _anonchat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Anonymous chat commands"""

    def help_custom(self):
        emoji = "🎭 "
        label = "Anonymer Chat"
        description = "Nachrichten ohne Namen in einem Kanal"
        return emoji, label, description

    @commands.group()
    async def __AnonChat__(self, ctx: commands.Context):
        """`anon add`, `anon remove`, `anon who`, `anon block`, `anon unblock`"""
