"""Runtime listener for dashboard-defined text and slash commands."""

from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from core import Cog
from utils import custom_commands as store

logger = logging.getLogger("custom_commands")


class CustomCommandsService(Cog):
    def __init__(self, bot):
        self.bot = bot
        self._commands: dict[int, dict[str, dict]] = {}
        self._slash_names: dict[int, set[str]] = {}

    async def cog_load(self):
        # Existing guild commands remain registered at Discord across restarts.
        # Rebuild the local dispatch tree without syncing every guild on boot.
        await self.refresh(sync_slash=False)
        logger.info("Custom command service loaded for %s guilds", len(self._commands))

    async def refresh(self, guild_id: int | None = None, *, sync_slash: bool = True):
        db = await store.connect()
        try:
            rows = await store.list_all(db, guild_id)
        finally:
            await db.close()

        if guild_id is None:
            fresh: dict[int, dict[str, dict]] = {}
            for row in rows:
                fresh.setdefault(int(row["guild_id"]), {})[row["name"].lower()] = row
            self._commands = fresh
            for current_guild in fresh:
                await self._refresh_slash(current_guild, sync=False)
        else:
            guild_id = int(guild_id)
            self._commands[guild_id] = {row["name"].lower(): row for row in rows}
            if not self._commands[guild_id]:
                self._commands.pop(guild_id, None)
            await self._refresh_slash(guild_id, sync=sync_slash)
        logger.info("Custom commands refreshed for guild %s", guild_id or "all")

    async def _refresh_slash(self, guild_id: int, *, sync: bool):
        tree = getattr(self.bot, "tree", None)
        if tree is None:
            return
        guild = discord.Object(id=guild_id)
        desired = {
            name for name, entry in self._commands.get(guild_id, {}).items()
            if entry.get("use_slash")
        }
        for old_name in self._slash_names.get(guild_id, set()):
            tree.remove_command(old_name, guild=guild)
        for name in desired:
            tree.add_command(self._make_slash_command(guild_id, name), guild=guild, override=True)
        self._slash_names[guild_id] = desired
        if sync:
            try:
                await tree.sync(guild=guild)
            except Exception:
                logger.exception("Could not sync custom slash commands for guild %s", guild_id)

    def _make_slash_command(self, guild_id: int, name: str) -> app_commands.Command:
        async def callback(interaction: discord.Interaction, args: str = ""):
            entry = self._commands.get(guild_id, {}).get(name)
            if entry is None or not entry.get("use_slash"):
                await interaction.response.send_message(
                    "Dieser Custom Command ist nicht mehr verfügbar.", ephemeral=True
                )
                return
            rendered = self._render(entry["response"], interaction.user, interaction.guild,
                                    interaction.channel, args)
            await interaction.response.send_message(
                rendered,
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=False, everyone=False, replied_user=False
                ),
            )

        return app_commands.Command(
            name=name,
            description=f"Custom Command: {name}"[:100],
            callback=callback,
        )

    @staticmethod
    def _render(response: str, user, guild, channel, arguments: str) -> str:
        channel_text = getattr(channel, "mention", "#unbekannt")
        return (
            response
            .replace("{user}", user.mention)
            .replace("{user_name}", user.display_name)
            .replace("{server}", guild.name)
            .replace("{channel}", channel_text)
            .replace("{args}", arguments.strip())
        )

    async def invocation(self, message: discord.Message):
        """Return (name, arguments, entry), or None when this is not ours."""
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
        if prefix is not None:
            body = message.content[len(prefix):].strip()
            name, _, arguments = body.partition(" ")
            entry = configured.get(name.lower())
            if (entry is not None and entry.get("use_prefix")
                    and self.bot.get_command(name.lower()) is None):
                return name.lower(), arguments.strip(), entry
            return None

        plain = message.content.strip()
        lowered = plain.lower()
        for name, entry in configured.items():
            if entry.get("use_exact") and lowered == name:
                return name, "", entry
        for name, entry in configured.items():
            if not entry.get("use_contains"):
                continue
            match = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", plain, re.IGNORECASE)
            if match:
                arguments = plain[match.end():].strip()
                return name, arguments, entry
        return None

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
            _name, arguments, entry = found
            rendered = self._render(
                entry["response"], message.author, message.guild, message.channel, arguments
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
                getattr(message.guild, "id", "unknown"), message.channel.id,
            )
