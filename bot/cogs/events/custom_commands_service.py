"""Runtime listener for dashboard-defined text and slash commands."""

from __future__ import annotations

import asyncio
import logging
import re
import time

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
        self._slash_sync_tasks: dict[int, asyncio.Task] = {}
        self._cooldowns: dict[tuple[int, str, int], float] = {}

    async def cog_load(self):
        # Existing guild commands remain registered at Discord across restarts.
        # Rebuild the local dispatch tree without syncing every guild on boot.
        await self.refresh(sync_slash=False)
        logger.info("Custom command service loaded for %s guilds", len(self._commands))

    def cog_unload(self):
        for task in self._slash_sync_tasks.values():
            task.cancel()
        self._slash_sync_tasks.clear()

    def schedule_slash_sync(self, guild_id: int):
        """Sync Discord in the background so dashboard saves never hang.

        Repeated edits within a moment are collapsed into one guild sync. The
        database and local command tree have already been updated by refresh.
        """
        guild_id = int(guild_id)
        previous = self._slash_sync_tasks.pop(guild_id, None)
        if previous is not None:
            previous.cancel()
        task = asyncio.create_task(self._sync_slash_later(guild_id))
        self._slash_sync_tasks[guild_id] = task
        task.add_done_callback(
            lambda finished, current=guild_id: self._slash_sync_tasks.pop(current, None)
            if self._slash_sync_tasks.get(current) is finished else None
        )

    async def _sync_slash_later(self, guild_id: int):
        try:
            await asyncio.sleep(0.75)
            tree = getattr(self.bot, "tree", None)
            if tree is not None:
                await tree.sync(guild=discord.Object(id=guild_id))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not sync custom slash commands for guild %s", guild_id)

    async def refresh(self, guild_id: int | None = None, *, sync_slash: bool = False):
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
            if entry.get("use_slash") and entry.get("config", {}).get("enabled", True)
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
        entry = self._commands.get(guild_id, {}).get(name, {})
        configured = entry.get("config", {}).get("parameters", [])
        valid = []
        seen = set()
        type_names = {
            "string": "str", "integer": "int", "boolean": "bool",
            "user": "discord.Member", "channel": "discord.TextChannel", "role": "discord.Role",
        }
        for parameter in configured[:10]:
            option = str(parameter.get("name", ""))
            if re.fullmatch(r"[a-z][a-z0-9_]{0,31}", option) and option not in seen:
                seen.add(option); valid.append(parameter)

        async def runner(interaction: discord.Interaction, values: dict):
            current = self._commands.get(guild_id, {}).get(name)
            if current is None or not current.get("use_slash"):
                await interaction.response.send_message("Dieser Custom Command ist nicht mehr verfügbar.", ephemeral=True); return
            if not self._allowed(current, interaction.user):
                await interaction.response.send_message("Du darfst diesen Command nicht verwenden.", ephemeral=True); return
            if self._on_cooldown(guild_id, name, interaction.user.id, current):
                await interaction.response.send_message("Dieser Command hat für dich noch Cooldown.", ephemeral=True); return
            values = {key: value for key, value in values.items() if key != "interaction" and value is not None}
            arguments = " ".join(getattr(value, "mention", str(value)) for value in values.values())
            sent = False
            async def send(text, action=None):
                nonlocal sent
                kwargs = self._reply_options(action or {}, interaction.user, interaction.guild, interaction.channel, arguments, values)
                kwargs["allowed_mentions"] = discord.AllowedMentions(users=True, roles=False, everyone=False)
                ephemeral = bool((action or {}).get("ephemeral"))
                if not sent: await interaction.response.send_message(text or None, ephemeral=ephemeral, **kwargs); sent = True
                else: await interaction.followup.send(text or None, ephemeral=ephemeral, **kwargs)
            await self._run_actions(current, interaction.user, interaction.guild, interaction.channel, arguments, send, values)
            if not sent and not interaction.response.is_done():
                await interaction.response.send_message("Command ausgeführt.", ephemeral=True)

        if valid:
            declarations = []
            for parameter in valid:
                annotation = type_names.get(parameter.get("type"), "str")
                suffix = "" if parameter.get("required") else " = None"
                declarations.append(f"{parameter['name']}: {annotation}{suffix}")
            source = "async def callback(interaction: discord.Interaction, *, " + ", ".join(declarations) + "):\n    return await runner(interaction, locals())"
            namespace = {"discord": discord, "runner": runner}
            exec(source, namespace)
            callback = namespace["callback"]
        else:
            async def callback(interaction: discord.Interaction, args: str = ""):
                await runner(interaction, {"args": args})

        command = app_commands.Command(
            name=name,
            description=str(entry.get("config", {}).get("description") or f"Custom Command: {name}")[:100],
            callback=callback,
        )
        descriptions = {p["name"]: str(p.get("description") or p["name"])[:100] for p in valid}
        if descriptions:
            command._params.update({key: value for key, value in command._params.items()})
            for key, description in descriptions.items():
                command._params[key].description = description
        return command

    @staticmethod
    def _render(response: str, user, guild, channel, arguments: str, variables: dict | None = None) -> str:
        channel_text = getattr(channel, "mention", "#unbekannt")
        rendered = (
            response
            .replace("{user}", user.mention)
            .replace("{user_name}", user.display_name)
            .replace("{server}", guild.name)
            .replace("{channel}", channel_text)
            .replace("{args}", arguments.strip())
        )
        for key, value in (variables or {}).items():
            rendered = rendered.replace("{" + key + "}", getattr(value, "mention", str(value)))
            rendered = rendered.replace("{option." + key + "}", getattr(value, "mention", str(value)))
        return rendered

    def _allowed(self, entry: dict, member) -> bool:
        config = entry.get("config", {})
        if not config.get("enabled", True):
            return False
        users = {str(value) for value in config.get("allowed_users", [])}
        roles = {str(value) for value in config.get("allowed_roles", [])}
        if str(member.id) in users:
            return True
        if roles and any(str(role.id) in roles for role in getattr(member, "roles", [])):
            return True
        return not users and not roles and not config.get("deny_without_role", False)

    def _on_cooldown(self, guild_id: int, name: str, user_id: int, entry: dict) -> bool:
        seconds = max(0, min(86400, int(entry.get("config", {}).get("cooldown", 0) or 0)))
        if not seconds:
            return False
        key = (guild_id, name, user_id)
        now = time.monotonic()
        if now < self._cooldowns.get(key, 0):
            return True
        self._cooldowns[key] = now + seconds
        return False

    def _reply_options(self, action: dict, member, guild, channel, arguments: str, variables=None) -> dict:
        options: dict = {}
        embed_data = action.get("embed")
        if isinstance(embed_data, dict) and embed_data.get("enabled"):
            title = self._render(str(embed_data.get("title", "")), member, guild, channel, arguments, variables)
            description = self._render(str(embed_data.get("description", "")), member, guild, channel, arguments, variables)
            try:
                color = int(str(embed_data.get("color", "#2563eb")).lstrip("#"), 16)
            except ValueError:
                color = 0x2563EB
            embed = discord.Embed(title=title or None, description=description or None, color=color)
            if embed_data.get("image_url"): embed.set_image(url=str(embed_data["image_url"]))
            if embed_data.get("footer"): embed.set_footer(text=str(embed_data["footer"])[:2048])
            options["embed"] = embed
        buttons = action.get("buttons", [])
        if isinstance(buttons, list) and buttons:
            options["view"] = self._make_button_view(buttons[:5], guild, channel, arguments, variables)
        return options

    def _make_button_view(self, buttons: list, guild, channel, arguments: str, variables=None):
        view = discord.ui.View(timeout=900)
        styles = {"blue": discord.ButtonStyle.primary, "gray": discord.ButtonStyle.secondary,
                  "green": discord.ButtonStyle.success, "red": discord.ButtonStyle.danger}
        for definition in buttons:
            emoji = str(definition.get("emoji", "")).strip() or None
            button = discord.ui.Button(label=str(definition.get("label", "Klick mich"))[:80],
                                       emoji=emoji, style=styles.get(definition.get("style"), discord.ButtonStyle.primary))
            async def clicked(interaction: discord.Interaction, data=definition):
                sent = False
                async def send(text, action=None):
                    nonlocal sent
                    kwargs = self._reply_options(action or {}, interaction.user, guild, channel, arguments, variables)
                    kwargs["allowed_mentions"] = discord.AllowedMentions(users=True, roles=False, everyone=False)
                    if not sent and not interaction.response.is_done():
                        await interaction.response.send_message(text or None, ephemeral=bool((action or {}).get("ephemeral")), **kwargs); sent = True
                    else:
                        await interaction.followup.send(text or None, ephemeral=bool((action or {}).get("ephemeral")), **kwargs); sent = True
                child = {"response": "", "config": {"actions": data.get("actions", [])}}
                await self._run_actions(child, interaction.user, guild, channel, arguments, send, variables)
                if not sent and not interaction.response.is_done():
                    await interaction.response.send_message("Aktion ausgeführt.", ephemeral=True)
            button.callback = clicked
            view.add_item(button)
        return view

    async def _run_actions(self, entry: dict, member, guild, channel, arguments: str, send, variables: dict | None = None):
        config = entry.get("config", {})
        actions = config.get("actions") or [{"type": "reply", "text": entry["response"]}]

        async def run(items, depth=0):
            if depth > 4:
                return
            for action in items[:25]:
                kind = action.get("type")
                text = self._render(str(action.get("text", "")), member, guild, channel, arguments, variables)
                if kind == "reply" and (text or action.get("embed")):
                    await send(text, action)
                elif kind == "dm" and text:
                    await member.send(text)
                elif kind == "send_channel" and text:
                    target = guild.get_channel(int(action.get("channel_id", 0) or 0))
                    if target is not None:
                        await target.send(text, allowed_mentions=discord.AllowedMentions.none())
                elif kind in ("add_role", "remove_role"):
                    role = guild.get_role(int(action.get("role_id", 0) or 0))
                    if role is not None:
                        if kind == "add_role":
                            await member.add_roles(role, reason="Custom Command")
                        else:
                            await member.remove_roles(role, reason="Custom Command")
                elif kind == "condition_role":
                    role_id = int(action.get("role_id", 0) or 0)
                    has_role = any(role.id == role_id for role in getattr(member, "roles", []))
                    await run(action.get("then", []) if has_role else action.get("else", []), depth + 1)
        await run(actions)

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
            if (entry is not None and entry.get("use_prefix") and self._allowed(entry, message.author)
                    and self.bot.get_command(name.lower()) is None):
                return name.lower(), arguments.strip(), entry
            return None

        plain = message.content.strip()
        lowered = plain.lower()
        for name, entry in configured.items():
            if entry.get("use_exact") and lowered == name and self._allowed(entry, message.author):
                return name, "", entry
        for name, entry in configured.items():
            if not entry.get("use_contains") or not self._allowed(entry, message.author):
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
            name, arguments, entry = found
            if self._on_cooldown(message.guild.id, name, message.author.id, entry):
                return
            async def send(text, action=None):
                kwargs = self._reply_options(action or {}, message.author, message.guild, message.channel, arguments)
                await message.channel.send(
                    text or None,
                    allowed_mentions=discord.AllowedMentions(
                        users=True, roles=False, everyone=False, replied_user=False
                    ), **kwargs,
                )
            await self._run_actions(
                entry, message.author, message.guild, message.channel, arguments, send
            )
        except Exception:
            logger.exception(
                "Custom command failed in guild %s channel %s",
                getattr(message.guild, "id", "unknown"), message.channel.id,
            )
