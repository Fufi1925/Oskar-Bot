"""Runtime listener for the three dashboard-defined commands per server."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core import Cog
from utils import custom_commands as store

logger = logging.getLogger("custom_commands")


class CustomCommandsService(Cog):
    def __init__(self, bot):
        self.bot = bot
        self._commands: dict[int, dict[str, str]] = {}

    async def cog_load(self):
        await self.refresh()
        logger.info("Custom command service loaded for %s guilds", len(self._commands))

    async def refresh(self, guild_id: int | None = None):
        db = await store.connect()
        try:
            rows = await store.list_all(db, guild_id)
        finally:
            await db.close()

        if guild_id is None:
            fresh: dict[int, dict[str, str]] = {}
            for row in rows:
                fresh.setdefault(int(row["guild_id"]), {})[row["name"].lower()] = row["response"]
            self._commands = fresh
        else:
            self._commands[int(guild_id)] = {
                row["name"].lower(): row["response"] for row in rows
            }
            if not self._commands[int(guild_id)]:
                self._commands.pop(int(guild_id), None)
        logger.info("Custom commands refreshed for guild %s", guild_id or "all")

    async def invocation(self, message: discord.Message):
        """Return (name, arguments, response), or None when this is not ours."""
        if message.guild is None or not message.content:
            return None
        configured = self._commands.get(message.guild.id)
        if not configured:
            return None
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        prefix = next(
            (item for item in sorted(prefixes or [], key=len, reverse=True)
             if item and message.content.startswith(item)),
            None,
        )
        if prefix is None:
            return None
        body = message.content[len(prefix):].strip()
        if not body:
            return None
        name, _, arguments = body.partition(" ")
        name = name.lower()
        response = configured.get(name)
        if response is None or self.bot.get_command(name) is not None:
            return None
        return name, arguments.strip(), response

    async def matches(self, message: discord.Message) -> bool:
        return await self.invocation(message) is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        try:
            found = await self.invocation(message)
            if found is None:
                return
            _name, arguments, response = found
            rendered = (
                response
                .replace("{user}", message.author.mention)
                .replace("{user_name}", message.author.display_name)
                .replace("{server}", message.guild.name)
                .replace("{channel}", message.channel.mention)
                .replace("{args}", arguments.strip())
            )
            await message.channel.send(
                rendered,
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=False, everyone=False, replied_user=False
                ),
            )
        except Exception:
            logger.exception(
                "Custom command failed in guild %s channel %s",
                message.guild.id, message.channel.id,
            )
