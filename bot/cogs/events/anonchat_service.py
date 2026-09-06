"""Anonymer Chat – bewusst kleiner, eigenständiger Laufzeitdienst.

Die alte Implementierung mischte Prefix-Befehle, Dashboard, eine dauerhaft
offene SQLite-Verbindung und den Relay in einem Cog. Dieser Dienst macht nur
eine Sache: konfigurierte Discord-Kanäle zuverlässig anonym weiterleiten.
Jeder Datenbankzugriff bekommt eine kurze eigene Verbindung; damit kann keine
Verbindung zwischen FastAPI- und Discord-Eventloop hängen bleiben.
"""

from __future__ import annotations

import logging
import time

import aiosqlite
import discord
from discord.ext import commands

from core import Cog
from utils import anonchat_store as store
from utils import db_open
from utils.emoji import CROSS

logger = logging.getLogger("anonymous_chat")


class AnonymousChatService(Cog):
    """Relay für die im Dashboard aktivierten anonymen Kanäle."""

    def __init__(self, bot):
        self.bot = bot
        self._channels: dict[int, set[int]] = {}
        self._webhooks: dict[int, discord.Webhook] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def _database(self) -> aiosqlite.Connection:
        db = await db_open.connect(store.DB_PATH)
        await store.ensure_schema(db)
        return db

    async def cog_load(self) -> None:
        await self.refresh()
        logger.info("Anonymous chat service loaded for %s guilds", len(self._channels))

    async def refresh(self, guild_id: int | None = None) -> None:
        """Aktive Kanäle frisch aus SQLite laden."""
        db = await self._database()
        try:
            self._channels = await store.all_channel_ids(db)
        finally:
            await db.close()
        self._webhooks.clear()
        if guild_id is not None:
            logger.info(
                "Anonymous chat cache refreshed for guild %s: %s",
                guild_id,
                sorted(self._channels.get(int(guild_id), set())),
            )

    def is_active(self, guild_id: int, channel_id: int) -> bool:
        return int(channel_id) in self._channels.get(int(guild_id), set())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not self.is_active(message.guild.id, message.channel.id):
            return

        try:
            # Befehle bleiben Befehle. Scheitert die Prefix-Erkennung, darf
            # dadurch nicht der komplette anonyme Kanal ausfallen.
            try:
                if hasattr(self.bot, "get_context"):
                    context = await self.bot.get_context(message)
                    if getattr(context, "valid", False):
                        return
                else:
                    prefixes = await self.bot.get_prefix(message)
                    if isinstance(prefixes, str):
                        prefixes = [prefixes]
                    if any(message.content.startswith(p) for p in prefixes or []):
                        return
            except Exception:
                logger.exception(
                    "Command detection failed in anonymous channel %s; relaying as text",
                    message.channel.id,
                )

            await self._relay(message)
        except Exception:
            logger.exception(
                "Anonymous relay crashed in guild %s channel %s",
                message.guild.id,
                message.channel.id,
            )

    async def _relay(self, message: discord.Message) -> None:
        db = await self._database()
        try:
            settings = await store.get_channel(
                db, message.guild.id, message.channel.id
            )
            if not settings or not settings.get("enabled"):
                # Cache und DB widersprechen sich: Cache sofort reparieren.
                await self.refresh(message.guild.id)
                return

            has_files = bool(message.attachments)
            original_text = message.content or ""

            # Erst löschen: Der Name darf nicht während der Verarbeitung
            # sichtbar bleiben.
            try:
                await message.delete()
            except discord.Forbidden:
                await self._tell(
                    message.author,
                    "Der Bot darf deine Nachricht nicht löschen. Dem Bot fehlt "
                    "im anonymen Kanal das Recht „Nachrichten verwalten“.",
                )
                logger.error(
                    "Missing manage_messages in anonymous channel %s",
                    message.channel.id,
                )
                return
            except discord.NotFound:
                pass

            problem = await store.why_not(
                db,
                settings,
                message.author,
                original_text,
                has_files=has_files,
            )
            if problem:
                await self._tell(message.author, problem)
                return

            cooldown = int(settings.get("cooldown_seconds") or 0)
            key = (message.guild.id, message.author.id)
            remaining = self._cooldowns.get(key, 0) - time.time()
            if cooldown and remaining > 0:
                await self._tell(
                    message.author,
                    f"Bitte warte noch {int(remaining) + 1} Sekunden.",
                )
                return
            if cooldown:
                self._cooldowns[key] = time.time() + cooldown

            content = store.clean_content(original_text, settings)
            files = []
            if settings.get("allow_attachments"):
                for attachment in message.attachments[:5]:
                    try:
                        files.append(await attachment.to_file())
                    except Exception:
                        logger.exception("Anonymous attachment download failed")

            if not content and not files:
                await self._tell(message.author, "Die anonyme Nachricht war leer.")
                return

            posted = await self._send(message.channel, settings, content, files)
            await store.log_message(
                db,
                message.guild.id,
                message.channel.id,
                message.author.id,
                original_text,
                getattr(posted, "id", None),
            )
            await self._send_staff_log(
                message.guild, settings, message.author, message, posted
            )
        finally:
            await db.close()

    async def send_test(self, channel, settings: dict, content: str):
        """Derselbe Sendepfad für den echten Dashboard-Test."""
        normal = store.normalise(settings)
        cleaned = store.clean_content(str(content or ""), normal)
        if not cleaned:
            raise ValueError("Die Testnachricht ist leer.")
        return await self._send(channel, normal, cleaned, [])

    async def send_disabled_notice(self, channel: discord.TextChannel):
        """Kurze Components-V2-Meldung, sobald der Kanal wieder normal ist."""
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                f"## {CROSS} Anonymer Chat ist aus\n"
                "Ab sofort werden Nachrichten wieder normal mit dem Namen des "
                "Absenders angezeigt und vom allgemeinen Log-System erfasst."
            ),
            accent_color=discord.Color.red(),
        ))
        return await channel.send(view=view)

    async def _send(self, channel, settings: dict, content: str, files: list):
        allowed_mentions = (
            discord.AllowedMentions.all()
            if settings.get("allow_mentions")
            else discord.AllowedMentions.none()
        )

        if settings.get("mode") == store.MODE_WEBHOOK:
            webhook = await self._webhook_for(channel)
            if webhook is not None:
                try:
                    return await webhook.send(
                        content=content or None,
                        username=settings.get("alias") or "Anonym",
                        avatar_url=settings.get("avatar_url") or None,
                        files=files or None,
                        wait=True,
                        allowed_mentions=allowed_mentions,
                    )
                except discord.NotFound:
                    self._webhooks.pop(channel.id, None)
                    # Genau einmal mit einem frisch angelegten Webhook.
                    webhook = await self._webhook_for(channel)
                    if webhook is not None:
                        return await webhook.send(
                            content=content or None,
                            username=settings.get("alias") or "Anonym",
                            avatar_url=settings.get("avatar_url") or None,
                            files=files or None,
                            wait=True,
                            allowed_mentions=allowed_mentions,
                        )
                except Exception:
                    logger.exception("Webhook send failed in channel %s", channel.id)

        # Bot-Modus und Webhook-Fallback. Kein Components-V2-Layout: eine
        # normale Discord-Nachricht ist hier absichtlich der robusteste Weg.
        try:
            alias = settings.get("alias") or "Anonym"
            body = f"**{alias}:**\n{content}" if content else f"**{alias}**"
            return await channel.send(
                body,
                files=files or None,
                allowed_mentions=allowed_mentions,
            )
        except Exception:
            logger.exception("Fallback send failed in channel %s", channel.id)
            raise

    async def _webhook_for(self, channel):
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached

        me = channel.guild.me
        if me is None or not channel.permissions_for(me).manage_webhooks:
            logger.warning(
                "Missing manage_webhooks in channel %s; using bot fallback",
                channel.id,
            )
            return None

        try:
            for hook in await channel.webhooks():
                if hook.user and self.bot.user and hook.user.id == self.bot.user.id:
                    self._webhooks[channel.id] = hook
                    return hook
            hook = await channel.create_webhook(
                name="Anonymer Chat",
                reason="Anonyme Nachrichten weiterleiten",
            )
            self._webhooks[channel.id] = hook
            return hook
        except Exception:
            logger.exception("Webhook create/list failed in channel %s", channel.id)
            return None

    async def _tell(self, member, text: str) -> None:
        try:
            await member.send(f"**Anonymer Chat**\n{text}")
        except Exception:
            pass

    async def _send_staff_log(self, guild, settings, member, original, posted) -> None:
        channel_id = settings.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            return
        try:
            embed = discord.Embed(
                title="Anonyme Nachricht",
                description=(original.content or "*(nur Anhang)*")[:4000],
                color=0x5865F2,
            )
            embed.add_field(name="Absender", value=f"{member.mention} (`{member.id}`)")
            embed.add_field(name="Kanal", value=original.channel.mention)
            jump_url = getattr(posted, "jump_url", None)
            if jump_url:
                embed.add_field(name="Nachricht", value=f"[Öffnen]({jump_url})")
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logger.exception("Anonymous staff log failed in channel %s", channel.id)

    # ── Kleine Verwaltungsbefehle; dieselbe Engine wie das Dashboard ──

    @commands.group(
        name="anon", aliases=["anonchat"], invoke_without_command=True,
        description="Anonyme Kanäle verwalten.",
    )
    @commands.has_permissions(manage_guild=True)
    async def anon(self, ctx):
        active = sorted(self._channels.get(ctx.guild.id, set()))
        channels = [ctx.guild.get_channel(channel_id) for channel_id in active]
        mentions = [channel.mention for channel in channels if channel is not None]
        text = "\n".join(mentions) if mentions else "Noch kein anonymer Kanal."
        await ctx.send(
            f"**Anonymer Chat**\n{text}\n\n"
            f"`{ctx.prefix}anon add #kanal` · `{ctx.prefix}anon remove #kanal`"
        )

    @anon.command(name="add", description="Einen Kanal anonym machen.")
    @commands.has_permissions(manage_guild=True)
    async def anon_add(self, ctx, channel: discord.TextChannel):
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.view_channel or not permissions.send_messages:
            return await ctx.send("❌ Der Bot kann den Kanal nicht sehen oder dort schreiben.")
        if not permissions.manage_messages:
            return await ctx.send("❌ Dem Bot fehlt dort „Nachrichten verwalten“.")

        db = await self._database()
        try:
            settings = await store.save_channel(
                db, ctx.guild.id, channel.id, {"enabled": True}
            )
        finally:
            await db.close()
        await self.refresh(ctx.guild.id)
        await self.send_test(
            channel,
            settings,
            "✅ Der anonyme Chat ist eingerichtet. Nachrichten werden ohne "
            "den Namen des Absenders neu gepostet.",
        )
        await ctx.send(f"✅ {channel.mention} ist jetzt anonym.")

    @anon.command(name="remove", description="Kanal wieder normal machen.")
    @commands.has_permissions(manage_guild=True)
    async def anon_remove(self, ctx, channel: discord.TextChannel):
        db = await self._database()
        try:
            removed = await store.delete_channel(db, ctx.guild.id, channel.id)
        finally:
            await db.close()
        await self.refresh(ctx.guild.id)
        if removed:
            try:
                await self.send_disabled_notice(channel)
            except Exception:
                logger.exception(
                    "Could not send disabled notice to anonymous channel %s",
                    channel.id,
                )
        await ctx.send(
            f"✅ {channel.mention} ist wieder normal."
            if removed else "Dieser Kanal war nicht als anonym gespeichert."
        )

    @anon.command(name="who", description="Autor einer anonymen Nachricht finden.")
    @commands.has_permissions(manage_guild=True)
    async def anon_who(self, ctx, message_id: str):
        if not message_id.isdigit():
            return await ctx.send("Bitte eine gültige Nachrichten-ID angeben.")
        db = await self._database()
        try:
            author_id = await store.find_author(db, ctx.guild.id, int(message_id))
        finally:
            await db.close()
        if author_id is None:
            return await ctx.send("Zu dieser Nachricht wurde kein Autor gefunden.")
        try:
            await ctx.author.send(
                f"Die anonyme Nachricht `{message_id}` stammt von <@{author_id}> "
                f"(`{author_id}`)."
            )
            await ctx.send("✅ Autor wurde dir per DM geschickt.")
        except discord.Forbidden:
            await ctx.send("Ich kann dir keine DM senden.")

    @anon.command(name="block", description="Jemanden vom anonymen Chat sperren.")
    @commands.has_permissions(manage_guild=True)
    async def anon_block(self, ctx, member: discord.Member, *, reason: str = ""):
        db = await self._database()
        try:
            await store.block(
                db, ctx.guild.id, member.id, reason=reason, by_id=ctx.author.id
            )
        finally:
            await db.close()
        await ctx.send(f"✅ {member.mention} kann nicht mehr anonym schreiben.")

    @anon.command(name="unblock", description="Anonym-Chat-Sperre aufheben.")
    @commands.has_permissions(manage_guild=True)
    async def anon_unblock(self, ctx, member: discord.Member):
        db = await self._database()
        try:
            removed = await store.unblock(db, ctx.guild.id, member.id)
        finally:
            await db.close()
        await ctx.send(
            f"✅ {member.mention} darf wieder anonym schreiben."
            if removed else "Diese Person war nicht gesperrt."
        )
