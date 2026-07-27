# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
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


class Counting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Guarding one guild at a time: two people can hit send in the
        # same millisecond, and without this both would be judged
        # against the same "current" and both accepted.
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = self._locks[guild_id] = asyncio.Lock()
        return lock

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

    def rules_view(self, settings: dict) -> discord.ui.LayoutView:
        """
        The rules card, also posted by the dashboard's announce button.

        Kept here so both sides always show the same rules.
        """
        rules = [
            "Immer die **nächste Zahl** schreiben — eine nach der anderen.",
            "Nur die nackte Zahl. `42` zählt, `42!` oder `42 los` nicht.",
        ]
        if settings.get("require_alternate"):
            rules.append("**Nicht zweimal hintereinander** — jemand anders muss dran sein.")
        if settings.get("mode") == "reset":
            rules.append("Ein Fehler setzt den Zähler **zurück auf 0**.")
        else:
            rules.append("Ein Fehler ist halb so wild — es geht **weiter**.")
        if settings.get("allow_chat"):
            rules.append("Zwischendurch quatschen ist erlaubt.")

        body = "\n".join(f"**{i}.** {r}" for i, r in enumerate(rules, 1))
        return panel(
            f"{BOOK} Zähl-Regeln",
            body,
            f"**Als Nächstes:** {int(settings.get('current') or 0) + 1}\n"
            f"{STAR} **Rekord:** {settings.get('high_score') or 0}",
            accent=BLURPLE,
        )

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
                if not settings.get("delete_wrong"):
                    outcome = store.counting_apply(
                        message.guild.id, settings, verdict, message.author.id
                    )
                    await self._announce_break(message, verdict, outcome)
                    return

                outcome = store.counting_apply(
                    message.guild.id, settings, verdict, message.author.id
                )
                notice = self._break_view(message, verdict, outcome)
                await self._cleanup(message, notice)
                return

            # Correct number.
            outcome = store.counting_apply(
                message.guild.id, settings, verdict, message.author.id
            )
            await self._celebrate(message, settings, verdict, outcome)

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
