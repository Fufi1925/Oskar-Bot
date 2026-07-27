# ╔══════════════════════════════════════════════════════════════════╗
# ║   Leveling                                                       ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The leveling system.

Rewritten from a 3165-line cog that carried several bugs which made whole
commands do nothing:

  * `/rank`, the leaderboard and the API read the `user_xp` table, while
    `resetxp`, `setxp` and `setlevel` wrote a second table called `users`.
    The admin commands reported success and changed nothing.
  * `setxp` was registered twice — once as `level setxp` (XP per message)
    and once as a top-level command (a member's XP).
  * The level-up embed worked out a colour from the settings and then
    passed `color=0xFF0000` anyway, so the setting never had an effect.
  * `min_xp` / `max_xp` were stored and shown in the setup dialog but
    never used; every message was worth exactly `xp_per_message`.
  * `dm_level_up` was stored and never read.
  * Settings were unpacked by tuple index, so a new column shifted every
    value after it.

Storage and the XP curve now live in `utils/leveling_store.py`, the card
in `utils/rank_card.py`, so the dashboard runs the same code.
"""

from __future__ import annotations

import logging
import time

import aiosqlite
import discord
from discord.ext import commands

from utils import leveling_store as store
from utils import rank_card
from utils.panels import ACCENT, Panel, StatusCard
from utils.Tools import blacklist_check, ignore_check

logger = logging.getLogger(__name__)


class Leveling(commands.Cog):
    """XP for chatting, with rewards, multipliers and a rank card."""

    def __init__(self, bot):
        self.bot = bot
        self.connection: aiosqlite.Connection | None = None
        # guild_id -> settings, dropped whenever they are written. Reading
        # the settings row on every single message was the cog's hottest
        # query by a wide margin.
        self._settings_cache: dict[int, dict] = {}
        # (guild_id, user_id) -> when the cooldown expires
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def cog_load(self) -> None:
        self.connection = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(self.connection)

    async def cog_unload(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    # ── helpers ─────────────────────────────────────────────────────

    async def settings(self, guild_id: int) -> dict:
        if guild_id not in self._settings_cache:
            self._settings_cache[guild_id] = await store.get_settings(
                self.connection, guild_id
            )
        return self._settings_cache[guild_id]

    def forget(self, guild_id: int) -> None:
        """Drop the cached settings after a write."""
        self._settings_cache.pop(guild_id, None)

    async def reply(self, ctx, view, *, settings: dict | None = None):
        """
        Answer a command, honouring the guild's auto-delete settings.

        `command_delete_after` removes the bot's reply, and
        `delete_command_message` removes the member's own command, so a
        busy channel does not fill up with rank cards.
        """
        settings = settings or await self.settings(ctx.guild.id)
        delete_after = settings.get("command_delete_after") or None

        message = await ctx.send(view=view, delete_after=delete_after)

        if settings.get("delete_command_message"):
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, AttributeError):
                pass
        return message

    async def send_card(self, ctx, *, file=None, view=None, settings=None):
        """Same as reply(), for a message carrying a file."""
        settings = settings or await self.settings(ctx.guild.id)
        delete_after = settings.get("command_delete_after") or None

        message = await ctx.send(file=file, view=view, delete_after=delete_after)

        if settings.get("delete_command_message"):
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, AttributeError):
                pass
        return message

    async def note(self, ctx, title, body, tone="info"):
        await self.reply(ctx, StatusCard(title, body, tone=tone))

    # ── XP on every message ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if self.connection is None:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # Cooldown before any database work, since this runs on every
        # message the bot can see.
        key = (guild_id, user_id)
        now = time.time()
        if self._cooldowns.get(key, 0) > now:
            return

        try:
            settings = await self.settings(guild_id)
            if not settings.get("enabled"):
                return

            role_ids = [r.id for r in getattr(message.author, "roles", [])]
            if await store.is_excluded(
                self.connection, guild_id,
                channel_id=message.channel.id, role_ids=role_ids,
            ):
                return

            self._cooldowns[key] = now + settings.get("cooldown_seconds", 60)

            multiplier = await store.multiplier_for(
                self.connection, guild_id,
                channel_id=message.channel.id, role_ids=role_ids,
            )
            gained = int(store.roll_xp(settings) * multiplier)
            if gained <= 0:
                return

            new_xp, before, after = await store.add_xp(
                self.connection, guild_id, user_id, gained
            )

            if after > before:
                await self.level_up(message, after, new_xp, settings)

        except Exception as exc:
            logger.error(f"Leveling: could not award XP: {exc}")

    async def level_up(self, message, level, xp, settings) -> None:
        """Announce the new level and hand out the reward roles."""
        member = message.author
        guild = message.guild

        try:
            rank = await store.get_rank(self.connection, guild.id, member.id)
            _, into, needed = store.progress(xp)

            values = {
                "user": member.mention,
                "user_name": member.name,
                "user_nick": member.display_name,
                "level": level,
                "xp": xp,
                "rank": rank,
                "messages": (await store.get_user(
                    self.connection, guild.id, member.id
                ))["messages"],
                "server": guild.name,
                "next_level": level + 1,
                "next_xp": max(0, needed - into),
            }
            text = store.fill(settings.get("level_message"), values)

            mode = settings.get("announce_mode", "channel")
            if mode != "off":
                card = Panel(
                    "Level aufgestiegen",
                    text,
                    accent=settings.get("embed_color") or ACCENT["success"],
                    image_url=settings.get("level_image") or None,
                )

                if mode == "dm":
                    try:
                        await member.send(view=card)
                    except (discord.Forbidden, discord.HTTPException):
                        pass  # DMs closed is not worth logging
                else:
                    channel = message.channel
                    configured = settings.get("channel_id")
                    if configured:
                        found = guild.get_channel(int(configured))
                        # A thread has .send but is not a TextChannel;
                        # checking the type turned threads away.
                        if found is not None and hasattr(found, "send"):
                            channel = found

                    permissions = channel.permissions_for(guild.me)
                    if permissions.send_messages:
                        await channel.send(
                            view=card,
                            delete_after=settings.get("delete_after") or None,
                        )

            await self.apply_rewards(guild, member, level, settings)

        except Exception as exc:
            logger.error(f"Leveling: level-up failed: {exc}")

    async def apply_rewards(self, guild, member, level, settings) -> None:
        """Give the roles earned at this level, and clean up if stacking is off."""
        try:
            add_ids, remove_ids = await store.roles_for_level(
                self.connection, guild.id, level,
                stack=bool(settings.get("stack_roles", 1)),
            )
            if not add_ids and not remove_ids:
                return

            me = guild.me
            top = me.top_role if me else None
            held = {r.id for r in member.roles}

            def usable(role):
                # Trying a role the bot cannot reach just raises Forbidden
                # in a loop; skip it and say so once.
                return role is not None and not role.managed and (
                    top is None or role < top
                )

            to_add = [
                role for role in (guild.get_role(r) for r in add_ids)
                if usable(role) and role.id not in held
            ]
            to_remove = [
                role for role in (guild.get_role(r) for r in remove_ids)
                if usable(role) and role.id in held
            ]

            if to_add:
                await member.add_roles(*to_add, reason=f"Level {level} erreicht")
            if to_remove:
                await member.remove_roles(*to_remove, reason=f"Level {level} erreicht")

        except discord.Forbidden:
            logger.warning(
                f"Leveling: missing permissions for reward roles in {guild.id}"
            )
        except Exception as exc:
            logger.error(f"Leveling: reward roles failed: {exc}")

    # ── /rank ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="rank", description="Zeigt dein Level und deinen Platz.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        settings = await self.settings(ctx.guild.id)

        if member.bot:
            return await self.note(
                ctx, "Keine Daten", "Bots sammeln kein XP.", "warning"
            )

        data = await store.get_user(self.connection, ctx.guild.id, member.id)
        rank = await store.get_rank(self.connection, ctx.guild.id, member.id)
        level, into, needed = store.progress(data["xp"])
        accent = settings.get("embed_color") or ACCENT["brand"]

        if settings.get("card_style") == "image":
            avatar_bytes = None
            try:
                avatar_bytes = await member.display_avatar.replace(
                    size=256, format="png"
                ).read()
            except Exception:
                pass

            buffer = await rank_card.render_image(
                name=member.display_name,
                avatar_bytes=avatar_bytes,
                level=level, rank=rank, xp=data["xp"],
                into_level=into, level_needs=needed,
                messages=data["messages"], accent=accent,
            )
            if buffer is not None:
                # Pillow may be missing on the host; falling through to the
                # panel is better than an error nobody can act on.
                return await self.send_card(
                    ctx,
                    file=discord.File(buffer, filename="rank.png"),
                    settings=settings,
                )

        await self.reply(
            ctx,
            rank_card.render_panel(
                name=member.display_name,
                level=level, rank=rank, xp=data["xp"],
                into_level=into, level_needs=needed,
                messages=data["messages"], accent=accent,
            ),
            settings=settings,
        )

    # ── /leaderboard ────────────────────────────────────────────────

    @commands.hybrid_command(
        name="leaderboard", aliases=["lb", "top"],
        description="Die Bestenliste des Servers.",
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def leaderboard(self, ctx, page: int = 1):
        settings = await self.settings(ctx.guild.id)
        page = max(1, min(page, 100))
        entries = await store.leaderboard(
            self.connection, ctx.guild.id, limit=10, offset=(page - 1) * 10
        )

        names = {}
        for entry in entries:
            member = ctx.guild.get_member(entry["user_id"])
            names[entry["user_id"]] = (
                member.display_name if member else f"Unbekannt ({entry['user_id']})"
            )

        await self.reply(
            ctx,
            rank_card.render_leaderboard_panel(
                guild_name=ctx.guild.name, entries=entries, names=names,
                accent=settings.get("embed_color") or ACCENT["brand"],
            ),
            settings=settings,
        )

    # ── level group ─────────────────────────────────────────────────

    @commands.group(
        name="level", invoke_without_command=True,
        description="Das Level-System einstellen.",
    )
    @blacklist_check()
    @ignore_check()
    async def level(self, ctx):
        settings = await self.settings(ctx.guild.id)
        stats = await store.guild_stats(self.connection, ctx.guild.id)

        state = "an" if settings.get("enabled") else "aus"
        deletion = (
            f"{settings['command_delete_after']}s"
            if settings.get("command_delete_after") else "aus"
        )

        await self.reply(ctx, Panel(
            "Level-System",
            f"**Status:** {state}\n"
            f"**XP pro Nachricht:** {settings['min_xp']}–{settings['max_xp']}\n"
            f"**Abklingzeit:** {settings['cooldown_seconds']}s\n"
            f"**Antworten löschen nach:** {deletion}\n"
            f"**Mitglieder mit XP:** {stats['members']}",
            "**Befehle**\n"
            f"`{ctx.prefix}rank` · `{ctx.prefix}leaderboard`\n"
            f"`{ctx.prefix}level on` / `off`\n"
            f"`{ctx.prefix}level xp <min> <max>` · `{ctx.prefix}level cooldown <s>`\n"
            f"`{ctx.prefix}level message <text>` · `{ctx.prefix}level channel [#kanal]`\n"
            f"`{ctx.prefix}level autodelete <sekunden>`\n"
            f"`{ctx.prefix}level reward add <level> <@rolle>`\n"
            f"`{ctx.prefix}level setxp <@user> <xp>` · `{ctx.prefix}level reset <@user>`\n\n"
            "Alles davon geht auch im Dashboard.",
            accent=settings.get("embed_color") or ACCENT["brand"],
        ), settings=settings)

    async def write(self, ctx, **updates):
        """Save settings and drop the cache in one step."""
        merged = await store.save_settings(self.connection, ctx.guild.id, updates)
        self.forget(ctx.guild.id)
        return merged

    @level.command(name="on", aliases=["enable"], description="Level-System einschalten.")
    @commands.has_permissions(manage_guild=True)
    async def level_on(self, ctx):
        await self.write(ctx, enabled=1)
        await self.note(ctx, "Eingeschaltet",
                        "Mitglieder sammeln ab jetzt XP fürs Schreiben.", "success")

    @level.command(name="off", aliases=["disable"], description="Level-System ausschalten.")
    @commands.has_permissions(manage_guild=True)
    async def level_off(self, ctx):
        await self.write(ctx, enabled=0)
        await self.note(ctx, "Ausgeschaltet",
                        "Es wird kein XP mehr vergeben. Die Daten bleiben erhalten.",
                        "info")

    @level.command(name="xp", description="XP pro Nachricht festlegen.")
    @commands.has_permissions(manage_guild=True)
    async def level_xp(self, ctx, minimum: int, maximum: int = None):
        maximum = maximum if maximum is not None else minimum
        if minimum < 0 or maximum < 0:
            return await self.note(ctx, "Geht nicht",
                                   "XP kann nicht negativ sein.", "error")
        merged = await self.write(ctx, min_xp=minimum, max_xp=maximum)
        await self.note(
            ctx, "Gespeichert",
            f"Pro Nachricht gibt es jetzt **{merged['min_xp']}–{merged['max_xp']}** XP.",
            "success",
        )

    @level.command(name="cooldown", description="Abklingzeit zwischen zwei XP-Gewinnen.")
    @commands.has_permissions(manage_guild=True)
    async def level_cooldown(self, ctx, seconds: int):
        merged = await self.write(ctx, cooldown_seconds=seconds)
        await self.note(ctx, "Gespeichert",
                        f"Abklingzeit: **{merged['cooldown_seconds']} Sekunden**.",
                        "success")

    @level.command(name="message", description="Text der Level-Up-Nachricht.")
    @commands.has_permissions(manage_guild=True)
    async def level_message(self, ctx, *, text: str):
        merged = await self.write(ctx, level_message=text)
        preview = store.fill(merged["level_message"], {
            "user": ctx.author.mention, "user_name": ctx.author.name,
            "user_nick": ctx.author.display_name, "level": 5, "xp": 2500,
            "rank": 3, "messages": 120, "server": ctx.guild.name,
            "next_level": 6, "next_xp": 1100,
        })
        await self.reply(ctx, Panel(
            "Nachricht gespeichert", preview,
            "Platzhalter: " + " ".join(f"`{{{k}}}`" for k in store.PLACEHOLDERS),
            accent=ACCENT["success"],
        ))

    @level.command(name="channel", description="Wohin die Level-Up-Nachricht geht.")
    @commands.has_permissions(manage_guild=True)
    async def level_channel(self, ctx, channel: discord.TextChannel = None):
        await self.write(ctx, channel_id=channel.id if channel else None)
        await self.note(
            ctx, "Gespeichert",
            f"Level-Ups kommen jetzt nach {channel.mention}." if channel
            else "Level-Ups erscheinen dort, wo das Mitglied geschrieben hat.",
            "success",
        )

    @level.command(name="autodelete", description="Antworten nach X Sekunden löschen.")
    @commands.has_permissions(manage_guild=True)
    async def level_autodelete(self, ctx, seconds: int):
        """0 turns it off. Applies to level-ups and to command replies."""
        merged = await self.write(
            ctx, delete_after=seconds, command_delete_after=seconds
        )
        if merged["command_delete_after"]:
            body = (
                f"Level-Up-Nachrichten und Antworten verschwinden nach "
                f"**{merged['command_delete_after']} Sekunden**."
            )
        else:
            body = "Nachrichten bleiben stehen."
        await self.note(ctx, "Gespeichert", body, "success")

    @level.command(name="color", aliases=["colour", "setcolor"],
                   description="Farbe der Level-Up-Nachricht.")
    @commands.has_permissions(manage_guild=True)
    async def level_color(self, ctx, colour: str):
        try:
            value = int(colour.strip().lstrip("#"), 16)
        except ValueError:
            return await self.note(
                ctx, "Keine Farbe",
                "Bitte als Hex angeben, zum Beispiel `#5865f2`.", "error",
            )
        merged = await self.write(ctx, embed_color=value)
        await self.reply(ctx, Panel(
            "Farbe gespeichert",
            f"Neue Farbe: `#{merged['embed_color']:06x}` — so sieht sie aus.",
            accent=merged["embed_color"],
        ))

    @level.command(name="thumbnail", description="Profilbild in der Level-Up-Nachricht.")
    @commands.has_permissions(manage_guild=True)
    async def level_thumbnail(self, ctx, on: bool = None):
        settings = await self.settings(ctx.guild.id)
        value = (not settings.get("thumbnail_enabled")) if on is None else on
        await self.write(ctx, thumbnail_enabled=1 if value else 0)
        await self.note(ctx, "Gespeichert",
                        f"Profilbild ist jetzt **{'an' if value else 'aus'}**.",
                        "success")

    @level.command(name="card", description="Rangkarte als Bild oder als Text.")
    @commands.has_permissions(manage_guild=True)
    async def level_card(self, ctx, style: str = None):
        style = (style or "").lower()
        if style not in store.CARD_STYLES:
            return await self.note(
                ctx, "Welche Karte?",
                f"`{ctx.prefix}level card image` — gezeichnetes Bild\n"
                f"`{ctx.prefix}level card text` — schnelle Textkarte",
                "info",
            )
        await self.write(ctx, card_style=style)
        await self.note(
            ctx, "Gespeichert",
            "Die Rangkarte wird jetzt als Bild gezeichnet." if style == "image"
            else "Die Rangkarte kommt jetzt als Textkarte.",
            "success",
        )

    @level.command(name="announce", description="Wo Level-Ups gemeldet werden.")
    @commands.has_permissions(manage_guild=True)
    async def level_announce(self, ctx, mode: str = None):
        mode = (mode or "").lower()
        if mode not in store.ANNOUNCE_MODES:
            return await self.note(
                ctx, "Wohin?",
                f"`{ctx.prefix}level announce channel` — in den Kanal\n"
                f"`{ctx.prefix}level announce dm` — als private Nachricht\n"
                f"`{ctx.prefix}level announce off` — gar nicht melden",
                "info",
            )
        await self.write(ctx, announce_mode=mode)
        await self.note(ctx, "Gespeichert", {
            "channel": "Level-Ups werden im Kanal gemeldet.",
            "dm": "Level-Ups kommen als private Nachricht.",
            "off": "Level-Ups werden nicht mehr gemeldet.",
        }[mode], "success")

    @level.command(name="stack", description="Frühere Belohnungsrollen behalten?")
    @commands.has_permissions(manage_guild=True)
    async def level_stack(self, ctx, on: bool = None):
        settings = await self.settings(ctx.guild.id)
        value = (not settings.get("stack_roles")) if on is None else on
        await self.write(ctx, stack_roles=1 if value else 0)
        await self.note(
            ctx, "Gespeichert",
            "Alle erreichten Rollen bleiben erhalten." if value
            else "Nur die höchste erreichte Rolle bleibt.",
            "success",
        )

    @level.command(name="placeholders", aliases=["vars"],
                   description="Welche Platzhalter es gibt.")
    async def level_placeholders(self, ctx):
        lines = [f"`{{{key}}}` — {text}" for key, text in store.PLACEHOLDERS.items()]
        await self.reply(ctx, Panel(
            "Platzhalter", "\n".join(lines),
            f"Benutzbar in `{ctx.prefix}level message`.",
            accent=ACCENT["brand"],
        ))

    @level.command(name="stats", description="Zahlen zum Level-System.")
    async def level_stats(self, ctx):
        settings = await self.settings(ctx.guild.id)
        stats = await store.guild_stats(self.connection, ctx.guild.id)
        top = await store.leaderboard(self.connection, ctx.guild.id, limit=1)

        leader = "—"
        if top:
            member = ctx.guild.get_member(top[0]["user_id"])
            leader = (
                f"{member.display_name if member else top[0]['user_id']} "
                f"(Level {top[0]['level']})"
            )

        await self.reply(ctx, Panel(
            f"Level-Statistik — {ctx.guild.name}",
            f"**Mitglieder mit XP:** {stats['members']:,}\n"
            f"**XP insgesamt:** {stats['total_xp']:,}\n"
            f"**Nachrichten gezählt:** {stats['messages']:,}\n"
            f"**Höchstes Level:** {stats['top_level']}\n"
            f"**Spitzenreiter:** {leader}".replace(",", "."),
            accent=settings.get("embed_color") or ACCENT["brand"],
        ), settings=settings)

    @level.command(name="setlevel", description="Ein Mitglied auf ein Level setzen.")
    @commands.has_permissions(manage_guild=True)
    async def level_setlevel(self, ctx, member: discord.Member, level: int):
        if level < 0:
            return await self.note(ctx, "Geht nicht",
                                   "Das Level kann nicht negativ sein.", "error")
        data = await store.set_xp(
            self.connection, ctx.guild.id, member.id, store.xp_for_level(level)
        )
        await self.note(
            ctx, "Gesetzt",
            f"{member.mention} ist jetzt **Level {data['level']}** "
            f"({data['xp']:,} XP).".replace(",", "."),
            "success",
        )

    @level.command(name="setxp", description="Das XP eines Mitglieds setzen.")
    @commands.has_permissions(manage_guild=True)
    async def level_setxp(self, ctx, member: discord.Member, xp: int):
        """
        This is the command that silently did nothing: it wrote to a
        second table that no read path ever looked at.
        """
        data = await store.set_xp(self.connection, ctx.guild.id, member.id, xp)
        await self.note(
            ctx, "Gesetzt",
            f"{member.mention} hat jetzt **{data['xp']:,}** XP "
            f"(Level {data['level']}).".replace(",", "."),
            "success",
        )

    @level.command(name="addxp", description="Einem Mitglied XP geben.")
    @commands.has_permissions(manage_guild=True)
    async def level_addxp(self, ctx, member: discord.Member, xp: int):
        new_xp, before, after = await store.add_xp(
            self.connection, ctx.guild.id, member.id, xp
        )
        note = f" — Level {before} → **{after}**" if after != before else ""
        await self.note(
            ctx, "Gutgeschrieben",
            f"{member.mention} hat jetzt **{new_xp:,}** XP{note}.".replace(",", "."),
            "success",
        )

    @level.command(name="reset", description="XP eines Mitglieds oder des Servers löschen.")
    @commands.has_permissions(manage_guild=True)
    async def level_reset(self, ctx, member: discord.Member = None):
        if member is not None:
            await store.reset_user(self.connection, ctx.guild.id, member.id)
            return await self.note(ctx, "Zurückgesetzt",
                                   f"{member.mention} fängt wieder bei 0 an.", "success")

        removed = await store.reset_guild(self.connection, ctx.guild.id)
        await self.note(ctx, "Alles zurückgesetzt",
                        f"**{removed}** Mitglieder wurden geleert.", "warning")

    # ── rewards ─────────────────────────────────────────────────────

    @level.group(name="reward", aliases=["rewards"], invoke_without_command=True,
                 description="Rollen als Belohnung für ein Level.")
    @commands.has_permissions(manage_guild=True)
    async def reward(self, ctx):
        entries = await store.rewards(self.connection, ctx.guild.id)
        settings = await self.settings(ctx.guild.id)

        if not entries:
            return await self.note(
                ctx, "Keine Belohnungen",
                f"`{ctx.prefix}level reward add <level> <@rolle>` legt eine an.",
                "info",
            )

        lines = []
        for entry in entries:
            role = ctx.guild.get_role(entry["role_id"])
            lines.append(
                f"**Level {entry['level']}** → "
                + (role.mention if role else "*Rolle gelöscht*")
            )

        stacking = (
            "Frühere Rollen bleiben erhalten."
            if settings.get("stack_roles")
            else "Nur die höchste Rolle bleibt."
        )
        await self.reply(ctx, Panel(
            "Belohnungen", "\n".join(lines), stacking,
            accent=settings.get("embed_color") or ACCENT["brand"],
        ), settings=settings)

    @reward.command(name="add", description="Rolle für ein Level festlegen.")
    @commands.has_permissions(manage_guild=True)
    async def reward_add(self, ctx, level: int, role: discord.Role):
        if level < 1:
            return await self.note(ctx, "Geht nicht",
                                   "Das Level muss mindestens 1 sein.", "error")

        me = ctx.guild.me
        if me and role >= me.top_role:
            return await self.note(
                ctx, "Zu hoch",
                f"{role.mention} steht über meiner eigenen Rolle — ich könnte "
                "sie niemandem geben. Schieb meine Rolle darüber.",
                "error",
            )
        if role.managed:
            return await self.note(
                ctx, "Nicht möglich",
                f"{role.mention} wird von einer Integration verwaltet und kann "
                "nicht vergeben werden.",
                "error",
            )

        await store.set_reward(self.connection, ctx.guild.id, level, role.id)
        await self.note(ctx, "Gespeichert",
                        f"Ab **Level {level}** gibt es {role.mention}.", "success")

    @reward.command(name="remove", description="Belohnung für ein Level entfernen.")
    @commands.has_permissions(manage_guild=True)
    async def reward_remove(self, ctx, level: int):
        if await store.remove_reward(self.connection, ctx.guild.id, level):
            await self.note(ctx, "Entfernt",
                            f"Für Level {level} gibt es keine Rolle mehr.", "success")
        else:
            await self.note(ctx, "Nichts gefunden",
                            f"Für Level {level} war keine Rolle eingetragen.", "warning")

    # ── multipliers ─────────────────────────────────────────────────

    @level.group(name="multiplier", aliases=["mult"], invoke_without_command=True,
                 description="XP-Multiplikatoren für Rollen oder Kanäle.")
    @commands.has_permissions(manage_guild=True)
    async def multiplier(self, ctx):
        entries = await store.multipliers(self.connection, ctx.guild.id)
        if not entries:
            return await self.note(
                ctx, "Keine Multiplikatoren",
                f"`{ctx.prefix}level multiplier set <@rolle|#kanal> <faktor>`",
                "info",
            )

        lines = []
        for entry in entries:
            if entry["target_type"] == "role":
                target = ctx.guild.get_role(entry["target_id"])
            else:
                target = ctx.guild.get_channel(entry["target_id"])
            lines.append(
                f"{target.mention if target else '*gelöscht*'} — "
                f"**{entry['multiplier']}×**"
            )

        await self.reply(ctx, Panel(
            "XP-Multiplikatoren", "\n".join(lines),
            "Bei mehreren Rollen zählt die höchste, nicht das Produkt.",
            accent=ACCENT["brand"],
        ))

    @multiplier.command(name="set", description="Multiplikator festlegen.")
    @commands.has_permissions(manage_guild=True)
    async def multiplier_set(self, ctx, target: discord.Role | discord.TextChannel,
                             factor: float):
        kind = "role" if isinstance(target, discord.Role) else "channel"
        await store.set_multiplier(
            self.connection, ctx.guild.id, target.id, kind, factor
        )
        await self.note(ctx, "Gespeichert",
                        f"{target.mention} bekommt **{factor}×** XP.", "success")

    @multiplier.command(name="remove", description="Multiplikator entfernen.")
    @commands.has_permissions(manage_guild=True)
    async def multiplier_remove(self, ctx,
                                target: discord.Role | discord.TextChannel):
        kind = "role" if isinstance(target, discord.Role) else "channel"
        if await store.remove_multiplier(self.connection, ctx.guild.id, target.id, kind):
            await self.note(ctx, "Entfernt",
                            f"{target.mention} bekommt wieder normales XP.", "success")
        else:
            await self.note(ctx, "Nichts gefunden",
                            "Da war kein Multiplikator eingetragen.", "warning")

    # ── exclusions ──────────────────────────────────────────────────

    @level.group(name="exclude", aliases=["ignore"], invoke_without_command=True,
                 description="Rollen oder Kanäle vom XP ausnehmen.")
    @commands.has_permissions(manage_guild=True)
    async def exclude(self, ctx):
        entries = await store.excluded(self.connection, ctx.guild.id)
        if not entries:
            return await self.note(
                ctx, "Nichts ausgenommen",
                f"`{ctx.prefix}level exclude add <@rolle|#kanal>`", "info",
            )

        lines = []
        for entry in entries:
            if entry["target_type"] == "role":
                target = ctx.guild.get_role(entry["target_id"])
            else:
                target = ctx.guild.get_channel(entry["target_id"])
            lines.append(target.mention if target else "*gelöscht*")

        await self.reply(ctx, Panel(
            "Kein XP für", "\n".join(lines), accent=ACCENT["warning"]
        ))

    @exclude.command(name="add", description="Rolle oder Kanal ausnehmen.")
    @commands.has_permissions(manage_guild=True)
    async def exclude_add(self, ctx, target: discord.Role | discord.TextChannel):
        kind = "role" if isinstance(target, discord.Role) else "channel"
        await store.add_excluded(self.connection, ctx.guild.id, target.id, kind)
        await self.note(ctx, "Ausgenommen",
                        f"In {target.mention} gibt es kein XP mehr.", "success")

    @exclude.command(name="remove", description="Ausnahme aufheben.")
    @commands.has_permissions(manage_guild=True)
    async def exclude_remove(self, ctx, target: discord.Role | discord.TextChannel):
        kind = "role" if isinstance(target, discord.Role) else "channel"
        if await store.remove_excluded(self.connection, ctx.guild.id, target.id, kind):
            await self.note(ctx, "Aufgehoben",
                            f"{target.mention} sammelt wieder XP.", "success")
        else:
            await self.note(ctx, "Nichts gefunden",
                            "Das war gar nicht ausgenommen.", "warning")


async def setup(bot):
    await bot.add_cog(Leveling(bot))
