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
        # No trailing space: Discord validates the emoji field of a
        # select option strictly and rejects "🎭 " as an invalid
        # emoji, which fails the whole >help menu with a 400.
        emoji = "🎭"
        label = "Anonymer Chat"
        description = "Nachrichten ohne Namen in einem Kanal"
        return emoji, label, description

    @commands.group()
    async def __AnonChat__(self, ctx: commands.Context):
        """`anon add`, `anon remove`, `anon who`, `anon block`, `anon unblock`"""
