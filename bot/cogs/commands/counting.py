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

"""
The counting game.

Rewritten because the cog and the dashboard were writing different
files' worth of keys into the same JSON:

  * the cog stored ``count`` / ``reset_on_fail``
  * the dashboard stored ``current`` / ``mode``

Neither could see the other. Switching the game on in the dashboard left
the cog at count 0, and the next correct number in chat wiped whatever
the dashboard had saved. Both sides now go through
``utils.extras_store``, which also migrates the old key names.

The rules themselves live in ``counting_judge`` in that store so they can
be tested without a Discord connection. This file only turns a verdict
into messages.
"""

import asyncio
import time

import discord
from discord.ext import commands
from discord.ui import Separator, TextDisplay

from utils import extras_store as store
from utils.cv2 import build_container
from utils.emoji import (
    ARROWRED, CROSS, NEXT_ALT1, REDRULESBOOK, RED_BUTTON, RED_PIN, STAR,
    TICK, ZWARNING,
)

CROSS = CROSS
TICK = TICK
WARNING = ZWARNING
BOOK = REDRULESBOOK
STOP = RED_BUTTON
NEXT = NEXT_ALT1
BACK = ARROWRED
PIN = RED_PIN
STAR = STAR

# Discord renders "> " as a quote bar. Every line the bot sends in the
# counting channel uses it so the game messages read as one block and
# stay visually apart from the players' numbers.
QUOTE = "> "


def quote(text: str) -> str:
    """Prefix every line with the quote marker."""
    return "\n".join(f"{QUOTE}{line}" if line else QUOTE
                     for line in str(text).split("\n"))


def panel(title: str, *sections, accent: int | None = None) -> discord.ui.LayoutView:
    """
    A Components V2 view whose body is quoted.

    ``CV2`` already builds the container; this only makes sure the text
    carries the quote bar and lets a colour through for the accent
    stripe, which CV2 itself does not expose.
    """
    view = discord.ui.LayoutView(timeout=None)
    container = build_container(
        TextDisplay(f"**{title}**"),
        *[
            item
            for section in sections
            for item in (Separator(visible=True), TextDisplay(quote(section)))
        ],
        accent_color=accent,
    )
    view.add_item(container)
    return view


GREEN = 0x57F287
RED = 0xED4245
AMBER = 0xFEE75C
BLURPLE = 0x5865F2


# How long to wait between two edits of the same rules card. Discord
# rate-limits message edits per channel, and a busy game produces a
# number every few hundred milliseconds. Five seconds still reads as
# live without spending the whole budget on one message.
RULES_EDIT_INTERVAL = 5.0

# Each wipe round clears up to 100 messages. 200 rounds is 20 000
# messages, far past any real counting channel, and stops a pinned or
# undeletable message from spinning forever.
MAX_WIPE_ROUNDS = 200


class Counting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Guarding one guild at a time: two people can hit send in the
        # same millisecond, and without this both would be judged
        # against the same "current" and both accepted.
        self._locks: dict[int, asyncio.Lock] = {}
        # Per guild bookkeeping for the live rules card: when it was
        # last edited, and the task that will write the pending value.
        self._rules_last_edit: dict[int, float] = {}
        self._rules_pending: dict[int, asyncio.Task] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = self._locks[guild_id] = asyncio.Lock()
        return lock

    def cog_unload(self):
        # Without this a reload leaves the delayed edits running against
        # a cog that no longer exists.
        for task in self._rules_pending.values():
            task.cancel()
        self._rules_pending.clear()

    # ──────────────────────────────────────────────────────────────
    #  The live rules card
    # ──────────────────────────────────────────────────────────────

    async def _fetch_rules_message(self, guild, settings):
        """
        The tracked rules message, or None if it is gone.

        A message the bot cannot find any more is forgotten so it does
        not try again after every single number.
        """
        message_id = settings.get("rules_message")
        channel_id = settings.get("rules_channel")
        if not message_id or not channel_id:
            return None

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            store.counting_save(guild.id, {"rules_message": None, "rules_channel": None})
            return None

        try:
            return await channel.fetch_message(int(message_id))
        except (discord.NotFound, discord.Forbidden):
            # Deleted by a moderator, or we lost access. Either way the
            # id is worthless now.
            store.counting_save(guild.id, {"rules_message": None, "rules_channel": None})
            return None
        except discord.HTTPException:
            # A hiccup; keep the id and try again next time.
            return None

    async def _write_rules_card(self, guild_id: int) -> None:
        """Edit the tracked rules card to the current numbers."""
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return

        settings = self.settings(guild_id)
        message = await self._fetch_rules_message(guild, settings)
        if message is None:
            return

        try:
            await message.edit(view=self.rules_view(settings))
            self._rules_last_edit[int(guild_id)] = time.monotonic()
        except discord.HTTPException:
            # Includes 429. The next number tries again; losing one
            # refresh is better than blocking the game.
            pass

    async def _delayed_rules_update(self, guild_id: int, wait: float) -> None:
        try:
            await asyncio.sleep(wait)
            await self._write_rules_card(guild_id)
        except asyncio.CancelledError:
            raise
        finally:
            self._rules_pending.pop(int(guild_id), None)

    def refresh_rules_card(self, guild_id) -> None:
        """
        Bring the rules card up to date, at most every few seconds.

        Called after every accepted number, so it must never block the
        game and never queue up more than one pending edit. When an edit
        happened recently the update is deferred instead of dropped, so
        the last number of a burst is always the one on display.
        """
        guild_id = int(guild_id)
        settings = self.settings(guild_id)
        if not settings.get("rules_message"):
            return

        if guild_id in self._rules_pending:
            # An edit is already scheduled; it will pick up the newest
            # numbers when it runs.
            return

        since = time.monotonic() - self._rules_last_edit.get(guild_id, 0.0)
        if since >= RULES_EDIT_INTERVAL:
            task = asyncio.create_task(self._delayed_rules_update(guild_id, 0))
        else:
            task = asyncio.create_task(
                self._delayed_rules_update(guild_id, RULES_EDIT_INTERVAL - since)
            )
        self._rules_pending[guild_id] = task

    async def refresh(self, guild_id=None):
        """
        Called by the dashboard after it saves.

        Nothing is cached in memory any more — every read goes to the
        store — so this only exists to keep the API's reload hook happy.
        """
        return True

    def settings(self, guild_id) -> dict:
        return store.counting_get(int(guild_id))

    def is_enabled(self, guild_id) -> bool:
        return bool(self.settings(guild_id).get("enabled"))

    # ──────────────────────────────────────────────────────────────
    #  Commands
    # ──────────────────────────────────────────────────────────────

    async def not_enabled_embed(self, ctx):
        prefix = ctx.clean_prefix or ">"
        await ctx.send(view=panel(
            f"{BOOK} Zählen — {ctx.guild.name}",
            f"**Status:** {CROSS} Aus",
            f"Mit `{prefix}counting enable` einschalten, danach "
            f"`{prefix}counting channel #kanal`.",
            accent=RED,
        ))

    async def send_help_embed(self, ctx):
        prefix = ctx.clean_prefix or ">"
        await ctx.send(view=panel(
            f"{BOOK} Counting",
            "Gemeinsam hochzählen — jede Zahl genau einmal, in der richtigen "
            "Reihenfolge.",
            f"**{prefix}counting enable / disable** — Spiel an- oder ausschalten\n"
            f"**{prefix}counting channel #kanal** — Kanal festlegen\n"
            f"**{prefix}counting config reset / continue** — Was bei einem Fehler passiert\n"
            f"**{prefix}counting alternate on / off** — Muss immer jemand anders dran sein?\n"
            f"**{prefix}counting reset** — Zähler zurück auf 0\n"
            f"**{prefix}counting stats** — Aktueller Stand und Rekord",
            accent=BLURPLE,
        ))

    def _rules_body(self, settings: dict) -> str:
        """The numbered rules, as they follow from the settings."""
        rules = [
            "Immer die **nächste Zahl** schreiben — eine nach der anderen.",
            "Nur die nackte Zahl. `42` zählt, `42!` oder `42 los` nicht.",
        ]
        if settings.get("require_alternate"):
            rules.append("**Nicht zweimal hintereinander** — jemand anders muss dran sein.")
        if settings.get("mode") == "reset":
            rules.append("Ein Fehler setzt den Zähler **zurück auf 0** "
                         "und der Kanal wird geleert.")
        else:
            rules.append("Ein Fehler ist halb so wild — es geht **weiter**.")
        if settings.get("allow_chat"):
            rules.append("Zwischendurch quatschen ist erlaubt.")

        return "\n".join(f"**{i}.** {r}" for i, r in enumerate(rules, 1))

    def _rules_status(self, settings: dict) -> str:
        """The live part of the card: next number and record."""
        return (
            f"**Als Nächstes:** {int(settings.get('current') or 0) + 1}\n"
            f"{STAR} **Rekord:** {settings.get('high_score') or 0}"
        )

    def rules_view(self, settings: dict) -> discord.ui.LayoutView:
        """
        The rules card, also posted by the dashboard's announce button.

        Kept here so both sides always show the same rules.
        """
        return panel(
            f"{BOOK} Zähl-Regeln",
            self._rules_body(settings),
            self._rules_status(settings),
            accent=BLURPLE,
        )

    async def wipe_channel(self, channel) -> dict:
        """
        Delete every message in the channel, however many there are.

        `purge` is called in rounds instead of once with a huge limit.
        A single call walks the history exactly once, so anything posted
        while it was running would survive; looping until a round finds
        nothing leaves the channel genuinely empty.

        Messages older than 14 days cannot be bulk deleted, so
        discord.py falls back to deleting them one at a time. That still
        removes them, it is only slower, which is why there is a ceiling
        on the number of rounds rather than on the number of messages.
        """
        deleted = 0
        rounds = 0
        # A stubborn message (a pinned system message, a race with
        # someone posting) must not turn this into an endless loop.
        while rounds < MAX_WIPE_ROUNDS:
            rounds += 1
            try:
                removed = await channel.purge(limit=100, bulk=True, check=lambda m: True)
            except discord.Forbidden:
                raise
            except discord.HTTPException:
                # Rate limited or a transient failure. Report what we
                # managed rather than pretending the channel is clean.
                return {"deleted": deleted, "complete": False}

            deleted += len(removed)
            if not removed:
                return {"deleted": deleted, "complete": True}

        return {"deleted": deleted, "complete": False}

    async def restart_game(self, channel, settings: dict) -> dict:
        """
        Wipe the counting channel, post the rules, start again at 0.

        Used both by the dashboard button and automatically whenever the
        counter falls back to 0 during play.
        """
        report = await self.wipe_channel(channel)

        # Reset before drawing the card so it shows "next: 1" straight
        # away. The record survives — only the streak restarts.
        fresh = store.counting_save(channel.guild.id, {
            "current": 0,
            "last_user": None,
            "record_announced": False,
            "record_baseline": max(
                int(settings.get("high_score") or 0),
                int(settings.get("record_baseline") or 0),
            ),
        })

        message = await channel.send(view=self.rules_view(fresh))
        store.counting_save(channel.guild.id, {
            "rules_message": message.id,
            "rules_channel": channel.id,
        })
        self._rules_last_edit[int(channel.guild.id)] = time.monotonic()

        return {**report, "message": message}

    # Kept under the old name: the API and older callers use it.
    async def purge_and_announce(self, channel, settings: dict) -> dict:
        return await self.restart_game(channel, settings)

    @commands.group(name="counting", invoke_without_command=True)
    @commands.guild_only()
    async def counting(self, ctx):
        if not self.is_enabled(ctx.guild.id):
            await self.not_enabled_embed(ctx)
        else:
            await self.send_help_embed(ctx)

    @counting.command(name="enable")
    @commands.has_permissions(manage_channels=True)
    async def enable(self, ctx):
        settings = store.counting_save(ctx.guild.id, {"enabled": True})
        if settings["channel"]:
            hint = f"Kanal: <#{settings['channel']}>"
        else:
            hint = (f"Jetzt noch `{ctx.clean_prefix or '>'}counting channel #kanal` "
                    "setzen — ohne Kanal passiert nichts.")
        await ctx.send(view=panel(
            "Counting", f"{TICK} Zählen ist an.", hint, accent=GREEN,
        ))

    @counting.command(name="disable")
    @commands.has_permissions(manage_channels=True)
    async def disable(self, ctx):
        store.counting_save(ctx.guild.id, {"enabled": False})
        await ctx.send(view=panel(
            "Counting",
            f"{STOP} Zählen ist aus. Stand und Rekord bleiben gespeichert.",
            accent=RED,
        ))

    @counting.command(name="channel")
    @commands.has_permissions(manage_channels=True)
    async def channel(self, ctx, channel: discord.TextChannel):
        me = ctx.guild.me
        perms = channel.permissions_for(me) if me else None
        if perms and not perms.send_messages:
            await ctx.send(view=panel(
                "Counting",
                f"{CROSS} In {channel.mention} darf der Bot nicht schreiben.",
                accent=RED,
            ))
            return

        store.counting_save(ctx.guild.id, {"channel": channel.id})
        missing = []
        if perms and not perms.manage_messages:
            missing.append("„Nachrichten verwalten“ — falsche Zahlen bleiben stehen")
        if perms and not perms.add_reactions:
            missing.append("„Reaktionen hinzufügen“ — kein Haken bei richtigen Zahlen")

        sections = [f"{PIN} Gezählt wird ab jetzt in {channel.mention}."]
        if missing:
            sections.append(f"{WARNING} Fehlende Rechte:\n" +
                            "\n".join(f"• {m}" for m in missing))
        await ctx.send(view=panel("Counting", *sections,
                                  accent=AMBER if missing else GREEN))

    @counting.command(name="config")
    @commands.has_permissions(manage_channels=True)
    async def config(self, ctx, mode: str):
        value = mode.lower()
        if value in ("reset", "true", "on", "streng"):
            store.counting_save(ctx.guild.id, {"mode": "reset"})
            msg = f"{TICK} Bei einem Fehler geht es zurück auf **0**."
        elif value in ("continue", "false", "off", "entspannt"):
            store.counting_save(ctx.guild.id, {"mode": "continue"})
            msg = f"{TICK} Bei einem Fehler wird **weitergezählt**."
        else:
            await ctx.send(view=panel(
                "Counting",
                f"{CROSS} Unbekannt: `{mode}` — erlaubt sind `reset` oder `continue`.",
                accent=RED,
            ))
            return
        await ctx.send(view=panel("Counting", msg, accent=GREEN))

    @counting.command(name="alternate")
    @commands.has_permissions(manage_channels=True)
    async def alternate(self, ctx, mode: str):
        value = mode.lower() in ("on", "true", "an", "ja", "yes")
        store.counting_save(ctx.guild.id, {"require_alternate": value})
        text = (
            f"{TICK} Es muss immer jemand anders die nächste Zahl schreiben."
            if value else
            f"{TICK} Dieselbe Person darf mehrmals hintereinander zählen."
        )
        await ctx.send(view=panel("Counting", text, accent=GREEN))

    @counting.command(name="reset")
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx):
        settings = store.counting_save(
            ctx.guild.id, {"current": 0, "last_user": None}
        )
        await ctx.send(view=panel(
            "Counting",
            f"{NEXT} Zähler steht wieder auf **0**.",
            f"Rekord bleibt bei **{settings['high_score']}**.",
            accent=AMBER,
        ))

    @counting.command(name="stats")
    async def stats(self, ctx):
        settings = self.settings(ctx.guild.id)
        channel = (
            ctx.guild.get_channel(settings["channel"])
            if settings["channel"] else None
        )

        last = settings.get("last_user")
        last_text = f"<@{last}>" if last else "—"

        await ctx.send(view=panel(
            f"{BOOK} Counting",
            f"**Aktuell:** {settings['current']}\n"
            f"**Als Nächstes:** {settings['current'] + 1}\n"
            f"{STAR} **Rekord:** {settings['high_score']}",
            f"**Kanal:** {channel.mention if channel else 'nicht gesetzt'}\n"
            f"**Zuletzt gezählt:** {last_text}",
            f"**Bei Fehler:** "
            f"{'zurück auf 0' if settings['mode'] == 'reset' else 'weiterzählen'}\n"
            f"**Abwechseln nötig:** {'ja' if settings['require_alternate'] else 'nein'}",
            accent=BLURPLE,
        ))

    # ──────────────────────────────────────────────────────────────
    #  Game
    # ──────────────────────────────────────────────────────────────

    async def _is_command(self, message: discord.Message) -> bool:
        """
        True when the message starts with a prefix the bot listens to.

        Commands typed in the counting channel must not break the
        streak — the old cog deleted them and told the user off.
        """
        try:
            prefixes = await self.bot.get_prefix(message)
        except Exception:
            return False
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        return any(p and message.content.startswith(p) for p in prefixes)

    async def _cleanup(self, message: discord.Message, notice=None, delay: float = 4.0):
        """Delete the message and, if given, a short-lived notice."""
        sent = None
        if notice is not None:
            try:
                sent = await message.channel.send(view=notice)
            except discord.HTTPException:
                sent = None

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        if sent is not None:
            await asyncio.sleep(delay)
            try:
                await sent.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DMs have no guild; the old version raised AttributeError here
        # on every direct message the bot received.
        if message.guild is None or message.author.bot:
            return
        if message.webhook_id is not None:
            return

        settings = self.settings(message.guild.id)
        if not settings.get("enabled"):
            return
        if not settings.get("channel") or message.channel.id != settings["channel"]:
            return
        if await self._is_command(message):
            return

        async with self._lock(message.guild.id):
            # Re-read inside the lock: another message may have moved
            # the counter on while we waited.
            settings = self.settings(message.guild.id)
            verdict = store.counting_judge(
                settings, message.author.id, message.content
            )

            if verdict["action"] == "ignore":
                return

            if verdict["action"] == "cleanup":
                await self._cleanup(message)
                return

            if verdict["action"] in ("wrong", "double"):
                outcome = store.counting_apply(
                    message.guild.id, settings, verdict, message.author.id
                )

                # Back to zero means a fresh round: clear the channel and
                # put the rules back at the top, so the game always
                # starts from the same clean state. Announcing the break
                # first would be pointless — the notice is wiped with
                # everything else a moment later.
                if verdict["reset"]:
                    await self._restart_after_reset(message, verdict, outcome)
                    return

                if not settings.get("delete_wrong"):
                    self.refresh_rules_card(message.guild.id)
                    await self._announce_break(message, verdict, outcome)
                    return

                self.refresh_rules_card(message.guild.id)
                notice = self._break_view(message, verdict, outcome)
                await self._cleanup(message, notice)
                return

            # Correct number.
            outcome = store.counting_apply(
                message.guild.id, settings, verdict, message.author.id
            )
            self.refresh_rules_card(message.guild.id)
            await self._celebrate(message, settings, verdict, outcome)

    async def _restart_after_reset(self, message, verdict, outcome):
        """
        The streak broke and the counter went back to 0: start over.

        Wipes the channel and posts a fresh rules card that says who
        broke it and how far the server had come, so the information is
        not lost with the messages.
        """
        channel = message.channel
        # How far the streak had come: the number that was due, minus one.
        reached = int(verdict.get("expected") or 1) - 1

        try:
            report = await self.wipe_channel(channel)
        except discord.Forbidden:
            # Without "manage messages" nothing can be cleared. Fall
            # back to the old behaviour rather than doing nothing.
            self.refresh_rules_card(message.guild.id)
            await self._announce_break(message, verdict, outcome)
            return
        except discord.HTTPException:
            report = {"deleted": 0, "complete": False}

        fresh = self.settings(message.guild.id)
        lines = [
            f"{CROSS} {message.author.mention} {verdict['reason']}",
            f"{BACK} Gezählt wurde bis **{reached}** — es geht wieder bei **1** los.",
        ]
        if not report["complete"]:
            lines.append(
                f"{WARNING} Der Kanal konnte nicht ganz geleert werden."
            )

        try:
            card = await channel.send(view=panel(
                f"{BOOK} Zähl-Regeln",
                "\n".join(lines),
                self._rules_body(fresh),
                self._rules_status(fresh),
                accent=RED,
            ))
        except discord.HTTPException:
            return

        store.counting_save(message.guild.id, {
            "rules_message": card.id,
            "rules_channel": channel.id,
        })
        self._rules_last_edit[int(message.guild.id)] = time.monotonic()

    def _break_view(self, message, verdict, outcome):
        icon = CROSS if verdict["action"] == "wrong" else WARNING
        lines = [f"{icon} {message.author.mention} {verdict['reason']}"]
        if verdict["reset"]:
            lines.append(f"{BACK} Der Zähler steht wieder auf **0** — "
                         "die nächste Zahl ist **1**.")
        else:
            nxt = int(outcome["settings"].get("current") or 0) + 1
            lines.append(f"Weiter geht es bei **{nxt}**.")
        return panel("Counting", "\n".join(lines),
                     accent=RED if verdict["reset"] else AMBER)

    async def _announce_break(self, message, verdict, outcome):
        try:
            await message.channel.send(view=self._break_view(message, verdict, outcome))
        except discord.HTTPException:
            pass

    async def _celebrate(self, message, settings, verdict, outcome):
        number = int(verdict["number"])

        if settings.get("react_success"):
            emoji = settings.get("success_emoji") or TICK
            try:
                await message.add_reaction(emoji)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                # A custom emoji from another server cannot be used;
                # fall back rather than losing the reaction entirely.
                if emoji != TICK:
                    try:
                        await message.add_reaction(TICK)
                    except discord.HTTPException:
                        pass

        notes = []
        if outcome["record"]:
            notes.append(f"{STAR} **Neuer Rekord: {number}!**")

        every = int(settings.get("milestone_every") or 0)
        if every > 0 and number % every == 0 and not outcome["record"]:
            notes.append(f"{STAR} **{number}** — Meilenstein geschafft!")

        if notes:
            try:
                await message.channel.send(view=panel(
                    "Counting", "\n".join(notes), accent=GREEN,
                ))
            except discord.HTTPException:
                pass


def setup(bot):
    bot.add_cog(Counting(bot))
