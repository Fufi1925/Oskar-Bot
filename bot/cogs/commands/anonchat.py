# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anonymous chat                                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Channels where everything is posted without the author's name.

A member writes normally; the message is deleted straight away and put
back by the bot, so nobody reading the channel can tell who wrote it.

Two design notes:

  * **One webhook per channel.** Discord caps a channel at 15 webhooks,
    so "one per member" stops working at the 16th person. The username
    and avatar are overridden per message instead, which a reader cannot
    tell apart and has no limit.
  * **Staff can still trace a message.** An anonymous channel with no
    record at all is a free pass for harassment. Every message is
    written to a log only staff can see, and old entries are pruned.
"""

from __future__ import annotations

import logging
import time

import aiosqlite
import discord
from discord.ext import commands

from utils import db_open
from utils import anonchat_store as store
from utils.panels import ACCENT, Panel, StatusCard
from utils.Tools import blacklist_check, ignore_check

logger = logging.getLogger(__name__)


class AnonChat(commands.Cog):
    """Post messages in a channel without showing who wrote them."""

    def __init__(self, bot):
        self.bot = bot
        self.connection: aiosqlite.Connection | None = None
        # guild_id -> {channel_id}. on_message fires for everything the
        # bot can see; a database round trip per message would be the
        # single busiest query in the process.
        self._channels: dict[int, set[int]] = {}
        # channel_id -> webhook, so a webhook is fetched once, not per
        # message.
        self._webhooks: dict[int, discord.Webhook] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._last_prune = 0.0

    async def cog_load(self) -> None:
        # db_open creates the folder first: aiosqlite raises
        # "unable to open database file" when db/ does not exist,
        # which is the case on a fresh container.
        self.connection = await db_open.connect(store.DB_PATH)
        await store.ensure_schema(self.connection)
        self._channels = await store.all_channel_ids(self.connection)

    async def cog_unload(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def refresh(self, guild_id: int | None = None) -> None:
        """Reload the cache after a change from chat or the dashboard."""
        if self.connection is None:
            return
        self._channels = await store.all_channel_ids(self.connection)
        # Drop cached webhooks so a mode change takes effect at once.
        self._webhooks.clear()

    # ── the relay ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if self.connection is None:
            return

        channels = self._channels.get(message.guild.id)
        if not channels or message.channel.id not in channels:
            return

        # A command in an anonymous channel should stay a command.
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if any(message.content.startswith(p) for p in prefixes or []):
            return

        try:
            await self._relay(message)
        except Exception as exc:
            logger.error(f"Anon chat relay failed in {message.channel.id}: {exc}")

    async def _relay(self, message: discord.Message) -> None:
        settings = await store.get_channel(
            self.connection, message.guild.id, message.channel.id
        )
        if settings is None or not settings.get("enabled"):
            return

        member = message.author
        # why_not() looks at this to decide about attachments.
        member._has_files = bool(message.attachments)

        # Delete first, no matter what happens next. Leaving the original
        # up while working out that it is not allowed would defeat the
        # whole point of the channel.
        try:
            await message.delete()
        except discord.Forbidden:
            return await self._tell(
                member,
                "Ich darf in diesem Kanal keine Nachrichten löschen — sag das "
                "bitte dem Server-Team, sonst ist der anonyme Chat nicht anonym.",
            )
        except discord.NotFound:
            pass

        problem = await store.why_not(
            self.connection, settings, member, message.content
        )
        if problem:
            return await self._tell(member, problem)

        cooldown = int(settings.get("cooldown_seconds") or 0)
        key = (message.guild.id, member.id)
        if cooldown:
            remaining = self._cooldowns.get(key, 0) - time.time()
            if remaining > 0:
                return await self._tell(
                    member,
                    f"Bitte warte noch {int(remaining) + 1} Sekunden, "
                    "bevor du wieder anonym schreibst.",
                )
            self._cooldowns[key] = time.time() + cooldown

        content = store.clean_content(message.content, settings)
        files = []
        if settings.get("allow_attachments"):
            for attachment in message.attachments[:5]:
                try:
                    files.append(await attachment.to_file())
                except Exception:
                    pass

        if not content and not files:
            return

        posted = await self._post(message.channel, settings, content, files)
        if posted is None:
            return await self._tell(
                member, "Deine Nachricht konnte nicht gesendet werden."
            )

        await store.log_message(
            self.connection, message.guild.id, message.channel.id,
            member.id, message.content, getattr(posted, "id", None),
        )
        await self._log_to_channel(message.guild, settings, member, message, posted)
        await self._maybe_prune(message.guild.id, settings)

    async def _post(self, channel, settings, content, files):
        """Send the message, by webhook or as the bot."""
        if settings.get("mode") == store.MODE_BOT:
            try:
                return await channel.send(view=Panel(
                    settings.get("alias") or "Anonym",
                    content or "*(nur Anhang)*",
                    accent=ACCENT["brand"],
                ), files=files or None)
            except Exception:
                return None

        webhook = await self._webhook_for(channel)
        if webhook is None:
            # Falling back keeps the channel working when the bot cannot
            # manage webhooks, instead of swallowing every message.
            try:
                return await channel.send(
                    f"**{settings.get('alias') or 'Anonym'}:** {content}",
                    files=files or None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception:
                return None

        try:
            return await webhook.send(
                content=content or None,
                username=settings.get("alias") or "Anonym",
                avatar_url=settings.get("avatar_url") or None,
                files=files or None,
                wait=True,
                allowed_mentions=(
                    discord.AllowedMentions.all()
                    if settings.get("allow_mentions")
                    else discord.AllowedMentions.none()
                ),
            )
        except discord.NotFound:
            # Somebody deleted the webhook behind our back.
            self._webhooks.pop(channel.id, None)
            return None
        except Exception:
            return None

    async def _webhook_for(self, channel):
        """Our webhook for this channel, created once and cached."""
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached

        me = channel.guild.me
        if me is None or not channel.permissions_for(me).manage_webhooks:
            return None

        try:
            for hook in await channel.webhooks():
                if hook.user and hook.user.id == self.bot.user.id:
                    self._webhooks[channel.id] = hook
                    return hook

            hook = await channel.create_webhook(
                name="Anonymer Chat",
                reason="Anonyme Nachrichten weiterleiten",
            )
            self._webhooks[channel.id] = hook
            return hook
        except Exception:
            return None

    async def _tell(self, member, text: str) -> None:
        """Tell the author privately why nothing appeared."""
        try:
            await member.send(view=StatusCard("Anonymer Chat", text, tone="warning"))
        except Exception:
            pass  # closed DMs are normal

    async def _log_to_channel(self, guild, settings, member, original, posted) -> None:
        channel_id = settings.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            return

        link = getattr(posted, "jump_url", None)
        try:
            await channel.send(view=Panel(
                "Anonyme Nachricht",
                f"**Von:** {member.mention} (`{member.id}`)\n"
                f"**Kanal:** <#{original.channel.id}>"
                + (f"\n**Nachricht:** [ansehen]({link})" if link else ""),
                (original.content or "*(nur Anhang)*")[:1500],
                accent=ACCENT["info"],
            ))
        except Exception:
            # A missing permission here must not stop the relay itself.
            pass

    async def _maybe_prune(self, guild_id: int, settings: dict) -> None:
        """Drop old log rows, at most once an hour."""
        now = time.time()
        if now - self._last_prune < 3600:
            return
        self._last_prune = now
        try:
            await store.prune_log(
                self.connection, guild_id, int(settings.get("log_retention_days") or 0)
            )
        except Exception:
            pass

    # ── commands ────────────────────────────────────────────────────

    @commands.group(name="anon", aliases=["anonchat"], invoke_without_command=True,
                    description="Anonymer Chat.")
    @blacklist_check()
    @ignore_check()
    async def anon(self, ctx):
        setups = await store.list_channels(self.connection, ctx.guild.id)

        if not setups:
            return await ctx.send(view=Panel(
                "Anonymer Chat",
                "In einem anonymen Kanal wird jede Nachricht sofort gelöscht "
                "und vom Bot ohne Namen neu gepostet.",
                f"`{ctx.prefix}anon add <#kanal>` — Kanal anonym machen\n"
                f"`{ctx.prefix}anon remove <#kanal>`\n"
                f"`{ctx.prefix}anon who <nachrichten-id>` — Autor nachschlagen\n"
                f"`{ctx.prefix}anon block <@user>` / `unblock`\n\n"
                "Alles Weitere im Dashboard.",
                accent=ACCENT["brand"],
            ))

        lines = []
        for setup in setups:
            channel = ctx.guild.get_channel(setup["channel_id"])
            lines.append(
                f"{channel.mention if channel else '*gelöscht*'} — "
                f"als **{setup['alias']}**"
                + (" *(aus)*" if not setup["enabled"] else "")
            )

        numbers = await store.stats(self.connection, ctx.guild.id)
        await ctx.send(view=Panel(
            "Anonymer Chat", "\n".join(lines),
            f"**{numbers['messages']}** Nachrichten insgesamt, "
            f"**{numbers['last_24h']}** in den letzten 24 Stunden.",
            accent=ACCENT["brand"],
        ))

    @anon.command(name="add", description="Einen Kanal anonym machen.")
    @commands.has_permissions(manage_guild=True)
    async def anon_add(self, ctx, channel: discord.TextChannel,
                       log_channel: discord.TextChannel = None):
        me = ctx.guild.me
        permissions = channel.permissions_for(me)

        missing = []
        if not permissions.manage_messages:
            missing.append("Nachrichten verwalten")
        if not permissions.manage_webhooks:
            missing.append("Webhooks verwalten")
        if missing:
            return await ctx.send(view=StatusCard(
                "Rechte fehlen",
                f"In {channel.mention} brauche ich: **{', '.join(missing)}**.\n\n"
                "Ohne „Nachrichten verwalten“ bleibt die Originalnachricht "
                "stehen — der Kanal wäre dann nicht anonym.",
                tone="error",
            ))

        await store.save_channel(
            self.connection, ctx.guild.id, channel.id,
            {"enabled": 1, "log_channel_id": log_channel.id if log_channel else None},
        )
        await self.refresh(ctx.guild.id)

        await ctx.send(view=Panel(
            "Anonymer Kanal eingerichtet",
            f"Alles in {channel.mention} wird ab jetzt anonym gepostet.",
            (f"Protokoll: {log_channel.mention}" if log_channel
             else "**Kein Protokoll gesetzt.** Ohne Protokoll kann niemand "
                  "nachvollziehen, wer etwas geschrieben hat — bei Missbrauch "
                  "steht das Team ohne Handhabe da."),
            accent=ACCENT["success"],
        ))

    @anon.command(name="remove", description="Kanal wieder normal machen.")
    @commands.has_permissions(manage_guild=True)
    async def anon_remove(self, ctx, channel: discord.TextChannel):
        if await store.delete_channel(self.connection, ctx.guild.id, channel.id):
            await self.refresh(ctx.guild.id)
            await ctx.send(view=StatusCard(
                "Entfernt", f"{channel.mention} ist wieder ein normaler Kanal.",
                tone="success",
            ))
        else:
            await ctx.send(view=StatusCard(
                "Nichts gefunden", "Dieser Kanal war nicht anonym.", tone="warning"
            ))

    @anon.command(name="who", description="Wer hat diese Nachricht geschrieben?")
    @commands.has_permissions(manage_guild=True)
    async def anon_who(self, ctx, message_id: str):
        """
        Look up the author of an anonymous message.

        Deliberately restricted to manage_guild and answered privately —
        posting the name in the channel would undo the anonymity for
        everybody watching.
        """
        if not message_id.isdigit():
            return await ctx.send(view=StatusCard(
                "Keine ID", "Bitte die Nachrichten-ID angeben.", tone="error"
            ))

        author_id = await store.find_author(
            self.connection, ctx.guild.id, int(message_id)
        )
        if author_id is None:
            return await ctx.send(view=StatusCard(
                "Nichts gefunden",
                "Zu dieser ID gibt es keinen Eintrag. Vielleicht ist sie älter "
                "als die Aufbewahrungszeit.",
                tone="warning",
            ))

        member = ctx.guild.get_member(author_id)
        try:
            await ctx.author.send(view=Panel(
                "Autor nachgeschlagen",
                f"Nachricht `{message_id}` stammt von "
                f"{member.mention if member else f'`{author_id}`'}.",
                "Diese Antwort kam per DM, damit die Anonymität im Kanal "
                "erhalten bleibt.",
                accent=ACCENT["info"],
            ))
            await ctx.send(view=StatusCard(
                "Per DM geschickt", "Ich habe dir die Antwort privat gesendet.",
                tone="success",
            ))
        except discord.Forbidden:
            await ctx.send(view=StatusCard(
                "DMs zu",
                "Ich kann dir nicht schreiben. Öffne deine DMs für diesen "
                "Server und versuch es nochmal — hier im Kanal sage ich es "
                "nicht.",
                tone="error",
            ))

    @anon.command(name="block", description="Jemanden vom anonymen Chat aussperren.")
    @commands.has_permissions(manage_guild=True)
    async def anon_block(self, ctx, member: discord.Member, *, reason: str = ""):
        await store.block(
            self.connection, ctx.guild.id, member.id,
            reason=reason, by_id=ctx.author.id,
        )
        await ctx.send(view=StatusCard(
            "Gesperrt",
            f"{member.mention} kann nicht mehr anonym schreiben.",
            tone="success",
        ))

    @anon.command(name="unblock", description="Sperre aufheben.")
    @commands.has_permissions(manage_guild=True)
    async def anon_unblock(self, ctx, member: discord.Member):
        if await store.unblock(self.connection, ctx.guild.id, member.id):
            await ctx.send(view=StatusCard(
                "Aufgehoben", f"{member.mention} darf wieder anonym schreiben.",
                tone="success",
            ))
        else:
            await ctx.send(view=StatusCard(
                "Nicht gesperrt", "Diese Person war nicht gesperrt.", tone="warning"
            ))


async def setup(bot):
    await bot.add_cog(AnonChat(bot))
