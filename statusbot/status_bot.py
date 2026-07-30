#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════╗
# ║   University Status                                              ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
A second, deliberately tiny bot that watches the main one.

Why it is a separate Railway service and not another thread in the main
container: a watcher that shares a container with the thing it watches
cannot report the failure that matters. When Railway restarts the
container, the deploy fails, or `restartPolicyMaxRetries = 5` is used
up, both processes die together -- and the outage goes unannounced,
which is precisely the case anybody builds a status bot for.

Two separate containers die separately. That is the whole point, and it
is the only reason this file exists rather than a cog in the main bot.

What it does:

  * Polls the main bot's ``/health`` endpoint over the public URL, the
    same way a stranger would reach it. Checking from inside would test
    a different thing than "is it reachable".
  * Keeps one Components V2 message in a status channel, edited in
    place rather than reposted, so the channel does not fill up.
  * Announces a change of state once, when it changes -- not every
    poll.

It writes nothing to the database and has no commands. Less to go
wrong in the thing whose job is to still be running.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from datetime import datetime, timezone

import aiohttp
import discord

import emojis
import history

# ── Configuration, all from the environment ───────────────────────────

TOKEN = os.getenv("STATUS_BOT_TOKEN", "").strip()

# The main bot's public URL. Railway gives every service its own domain;
# this must be the *main* one, not this service's.
MAIN_URL = (os.getenv("MAIN_BOT_URL") or "").strip().rstrip("/")

# Where the live status message lives.
STATUS_CHANNEL_ID = int(os.getenv("STATUS_CHANNEL_ID") or 0)

# The support guild. Used only to sanity-check the channel is ours.
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID") or 1530378233579704370)

BRAND = os.getenv("NEXT_PUBLIC_BRAND_NAME", "University Bot")

# How often to look. Every 30s is frequent enough to be useful and slow
# enough that a brief restart does not trigger an alarm on its own.
POLL_SECONDS = int(os.getenv("STATUS_POLL_SECONDS") or 30)

# How many failed polls before it is called an outage. A single missed
# request is normal -- a deploy, a dropped connection, a slow response.
FAILURES_BEFORE_DOWN = int(os.getenv("STATUS_FAILURES_BEFORE_DOWN") or 3)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Links shown as buttons under the panel. Each one only appears when it
# is configured -- a button that goes nowhere is worse than no button.
#
# No support button: the panel lives in the support server, so a link
# back to it would only point at the channel it is already in.
WEBSITE_URL = (os.getenv("WEBSITE_URL") or os.getenv("NEXTAUTH_URL") or "").strip()
INVITE_URL = (os.getenv("BOT_INVITE_URL") or "").strip()

# The main bot's own application id, used only to fetch its avatar for
# the panel. Falls back to the dashboard's client id, which is the same
# application.
MAIN_BOT_ID = int(
    os.getenv("MAIN_BOT_CLIENT_ID") or os.getenv("DISCORD_CLIENT_ID") or 0
)

# ── The template bot ──────────────────────────────────────────────────
#
# Its id is baked in rather than read from the environment. The section
# was invisible in production for exactly that reason: the variable was
# never set on the status service, `PARTNER_BOT_ID` came out 0, and
# check_partner returned None before doing anything -- so the panel
# silently dropped the whole block with nothing in the log to say why.
# The bot is a fixed part of this setup, so a constant cannot go
# missing the way a variable can.
#
# The environment may still override it, for a test instance.
PARTNER_BOT_ID = int(
    os.getenv("PARTNER_BOT_CLIENT_ID") or 1530742522589089952
)

# Its invite. It has no dashboard of its own, so this is the only link
# in its section. Built from the client id when not given explicitly.
PARTNER_INVITE_URL = (os.getenv("PARTNER_BOT_INVITE_URL") or "").strip()

# ── The template bot's figures are simulated ──────────────────────────
#
# Say it plainly, because everything else in this file follows the
# opposite rule: these two numbers are not measured.
#
# They cannot be. Reading another bot's online status needs the
# Presences intent, and no API exists that reports a third-party bot's
# gateway latency to anyone but that bot itself -- its heartbeat round
# trip is between it and Discord. The owner asked for the row to show
# green with a plausible ping anyway, so it does: a fresh random value
# each poll, in a believable range.
#
# Always on, and not switchable: the owner asked for one less thing to
# configure. The range is fixed at 10-100 ms for the same reason.
PARTNER_PING_MIN = 10
PARTNER_PING_MAX = 100

# The text command. Off unless STATUS_PREFIX is set, because reading
# messages needs the privileged Message Content intent and Discord
# refuses the login when the portal switch is off -- defaulting to on
# would strand anybody who has not flipped it.
# Who to ping when the main bot goes down. A role id, or "everyone".
# Empty means announce without pinging anybody.
ALERT_ROLE_ID = (os.getenv("STATUS_ALERT_ROLE_ID") or "").strip()

PREFIX = (os.getenv("STATUS_PREFIX") or "").strip()
PREFIX_COMMAND_ENABLED = bool(PREFIX)

GREEN = 0x3BA55D
AMBER = 0xFAA61A
RED = 0xED4245


def _duration(seconds: int) -> str:
    """A span in words: "3 Minuten", "1 Stunde 20 Minuten"."""
    if seconds < 60:
        return f"{seconds} Sekunden"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} Minute{'n' if minutes != 1 else ''}"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        text = f"{hours} Stunde{'n' if hours != 1 else ''}"
        return f"{text} {minutes} Minuten" if minutes else text
    days, hours = divmod(hours, 24)
    text = f"{days} Tag{'e' if days != 1 else ''}"
    return f"{text} {hours} Stunden" if hours else text


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


class Health:
    """The last thing we managed to learn about the main bot."""

    def __init__(self) -> None:
        self.reachable = False
        self.bot_ready = False
        self.dashboard = "unbekannt"
        self.latency_ms: float | None = None
        self.status_code: int | None = None
        self.error: str | None = None
        self.checked_at = 0.0

    @property
    def state(self) -> str:
        """One of: online, starting, down."""
        if not self.reachable:
            return "down"
        if self.bot_ready and self.dashboard == "online":
            return "online"
        return "starting"


class StatusBot(discord.Client):
    def __init__(self) -> None:
        # Still almost nothing: no members, no presences, no reactions.
        #
        # message_content is the exception, and only when asked for.
        # It is a privileged intent -- Discord refuses the login outright
        # if the switch in the developer portal is off -- so turning it
        # on by default would break the bot for anyone who has not.
        # /status works without it; !status does not.
        intents = discord.Intents.none()
        intents.guilds = True
        if PREFIX_COMMAND_ENABLED:
            intents.message_content = True

        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None
        self.health = Health()
        self.consecutive_failures = 0
        self.state = "unknown"
        self.state_since = time.time()
        # Set by /wartung. While on, the panel says "planned
        # maintenance" instead of raising an alarm, and no outage
        # announcement goes out.
        self.maintenance = False
        self.maintenance_note = ""
        self.message: discord.Message | None = None
        # Never None after start-up: the section is always part of the
        # panel, so the first publish must already have something to
        # draw rather than silently omitting the block.
        self.partner: dict = self.partner_fallback()
        self._task: asyncio.Task | None = None
        # Avatars are fetched once and kept. None means "not tried yet",
        # "" means tried and unavailable -- the difference stops a
        # failed lookup from being retried on every single poll.
        self._main_avatar: str | None = None

    # ── lifecycle ────────────────────────────────────────────────

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self.watch_loop())

        # /status works without any privileged intent, so it is always
        # registered -- it is the one that is certain to work.
        @self.tree.command(
            name="status",
            description="Status jetzt prüfen und das Panel erneuern",
        )
        async def status_command(interaction: discord.Interaction):
            # Ephemeral: the panel goes to the status channel, and the
            # confirmation is only of interest to whoever asked.
            await interaction.response.defer(ephemeral=True)
            ok, note = await self.refresh_panel()
            await interaction.followup.send(note, ephemeral=True)

        @self.tree.command(
            name="wartung",
            description="Wartungsmodus an oder aus",
        )
        @discord.app_commands.describe(
            an="An = Panel zeigt Wartung statt Störung",
            grund="Wird im Panel angezeigt, z. B. „Datenbank-Umzug“",
        )
        async def maintenance_command(
            interaction: discord.Interaction,
            an: bool,
            grund: str = "",
        ):
            # Only people who can manage the server. This changes what
            # every member sees, so it is not for everybody -- and the
            # status bot has no permission model of its own to lean on.
            member = interaction.user
            allowed = getattr(
                getattr(member, "guild_permissions", None), "manage_guild", False
            )
            if not allowed:
                await interaction.response.send_message(
                    "Dafür brauchst du „Server verwalten“.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)
            self.maintenance = bool(an)
            self.maintenance_note = grund.strip()[:200]

            # Recorded like any other state change, so a planned window
            # does not count against uptime the way a real outage does.
            history.record("maintenance" if an else self.state)

            await self.publish()
            await self.set_presence()

            if an:
                note = "Wartungsmodus ist **an**. Das Panel meldet keine Störung mehr."
                if self.maintenance_note:
                    note += f"\nGrund: {self.maintenance_note}"
            else:
                note = "Wartungsmodus ist **aus**. Normale Überwachung läuft wieder."
            await interaction.followup.send(note, ephemeral=True)

        if HOME_GUILD_ID:
            # Copied to the one guild rather than published globally:
            # a guild command appears immediately, a global one can take
            # an hour, and this bot has no business anywhere else.
            guild = discord.Object(id=HOME_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            try:
                await self.tree.sync(guild=guild)
            except Exception as err:  # noqa: BLE001
                print(f"[status] could not register /status: {err}")
        try:
            await start_web(self)
        except Exception as err:  # noqa: BLE001
            # Watching matters more than the send endpoint; losing one
            # must not take the other down with it.
            print(f"[status] the send endpoint failed to start: {err}")

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def load_emojis(self) -> None:
        """
        Find out which custom emojis this application may actually use.

        An application-owned emoji only works for the application that
        owns it -- there is no permission that lifts that. Since the
        status bot is a second application, using the ids without
        checking would print raw "<:online:1532...>" text into the panel
        on every poll.

        So it asks. Whatever comes back is used; everything else falls
        back to the plain characters, and the log says which.
        """
        try:
            owned = await self.fetch_application_emojis()
        except Exception as err:  # noqa: BLE001
            print(
                f"[status] could not read the application's emojis ({err}) — "
                "falling back to plain ones."
            )
            return

        # The animated flag has to come along: an animated emoji written
        # as <:name:id> renders as raw text, which is what happened on
        # the first deploy.
        taken = emojis.adopt({e.name: (e.id, e.animated) for e in owned})
        if taken:
            print(f"[status] using custom emojis: {', '.join(taken)}")
        absent = emojis.missing()
        if absent:
            # Named individually: the likely cause is that they were
            # uploaded to the main bot's application instead of this
            # one, and that is worth being able to see at a glance.
            print(
                f"[status] not available to this application: "
                f"{', '.join(absent)} — using plain ones instead. "
                "App emojis only work for the app that owns them."
            )

    async def on_ready(self) -> None:
        print(f"[status] logged in as {self.user}")
        await self.load_emojis()
        if not MAIN_URL:
            print(
                "[status] MAIN_BOT_URL is not set — there is nothing to "
                "watch. Set it to the main service's public URL."
            )
        if not STATUS_CHANNEL_ID:
            print(
                "[status] STATUS_CHANNEL_ID is not set — the live message "
                "cannot be posted."
            )

    # ── commands ─────────────────────────────────────────────────

    async def refresh_panel(self) -> tuple[bool, str]:
        """
        Check now and rebuild the panel, wherever it belongs.

        Shared by both commands. They differ only in how the answer gets
        back to whoever asked; the work is identical, and the panel
        always lands in STATUS_CHANNEL_ID no matter which channel the
        command came from.
        """
        if not STATUS_CHANNEL_ID:
            return False, (
                "Es ist kein Status-Kanal eingestellt (`STATUS_CHANNEL_ID`)."
            )

        channel = self.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.fetch_channel(STATUS_CHANNEL_ID)
            except Exception:
                return False, (
                    "Den eingestellten Status-Kanal sehe ich nicht. Bin ich "
                    "auf dem Server und darf ich den Kanal sehen?"
                )

        health = await self.check()
        self.health = health

        if health.reachable:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        if self.consecutive_failures >= FAILURES_BEFORE_DOWN:
            new_state = "down"
        elif health.reachable:
            new_state = health.state
        else:
            new_state = self.state if self.state != "unknown" else "starting"

        if new_state != self.state:
            self.state = new_state
            self.state_since = time.time()

        # Posted fresh on purpose. Asking for the panel and having it
        # silently edited three thousand messages up the channel is not
        # what anybody means by "show me the status".
        old_message = self.message
        self.message = None
        await self.publish()

        if old_message is not None and self.message is not None:
            if old_message.id != self.message.id:
                try:
                    await old_message.delete()
                except Exception:
                    # An old panel left behind is untidy, not broken.
                    pass

        if self.message is None:
            return False, f"Ich darf in {channel.mention} nicht schreiben."

        return True, f"Status aktualisiert: {self.message.jump_url}"

    async def on_message(self, message: discord.Message) -> None:
        if not PREFIX_COMMAND_ENABLED:
            return
        if message.author.bot or message.guild is None:
            return
        if HOME_GUILD_ID and message.guild.id != HOME_GUILD_ID:
            return
        if message.content.strip().lower() != f"{PREFIX}status":
            return

        ok, note = await self.refresh_panel()
        try:
            # A short reply where the command was typed, so the person
            # knows it worked even though the panel went elsewhere.
            await message.reply(note, mention_author=False,
                                delete_after=None if not ok else 15)
        except discord.Forbidden:
            pass
        except Exception as err:
            print(f"[status] could not reply to {PREFIX}status: {err}")

    # ── the check ────────────────────────────────────────────────

    async def check(self) -> Health:
        """
        Ask the main bot how it is, from outside.

        Deliberately over the public URL: that is the path a real user
        takes, so it also catches a container that is up but not
        serving.
        """
        health = Health()
        health.checked_at = time.time()

        if not MAIN_URL or self.session is None:
            health.error = "MAIN_BOT_URL fehlt"
            return health

        started = time.perf_counter()
        try:
            async with self.session.get(
                f"{MAIN_URL}/health", timeout=REQUEST_TIMEOUT
            ) as response:
                health.status_code = response.status
                health.latency_ms = (time.perf_counter() - started) * 1000
                # /health answers 503 while starting, with a body that
                # still says what is going on. Reading it either way is
                # the difference between "starting" and "down".
                try:
                    payload = await response.json()
                except Exception:
                    payload = {}
                health.reachable = True
                health.bot_ready = bool(payload.get("bot_ready"))
                health.dashboard = str(payload.get("dashboard") or "unbekannt")
        except asyncio.TimeoutError:
            health.error = "Zeitüberschreitung"
        except aiohttp.ClientError as err:
            health.error = type(err).__name__
        except Exception as err:  # noqa: BLE001 - a watcher must not die
            health.error = f"{type(err).__name__}: {err}"

        return health

    # ── the message ──────────────────────────────────────────────

    async def check_partner(self) -> dict:
        """
        The template bot's section.

        Membership is real: `fetch_member` either finds the bot on the
        support server or it does not, and a genuine NotFound is shown
        as such -- red, and with no ping, because a latency next to
        "it is not there" would be nonsense.

        The green dot and the ping are **simulated**, deliberately, on
        the owner's instruction. Neither is obtainable:

          * online status needs the Presences intent, and without it
            `Member.status` is *always* offline -- so reading it would
            put a permanent red dot on a bot that runs fine;
          * a third-party bot's gateway latency is not exposed by any
            API. Its heartbeat round trip is between it and Discord.
            Nothing outside that bot can measure it.

        So the ping is a fresh random value in PARTNER_PING_MIN..MAX on
        every poll, and there is no switch to turn it off.

        **This never returns None.** It used to, whenever the guild or
        the member could not be read -- and in production that silently
        deleted the entire block from the panel with nothing in the log
        to explain it, which is indistinguishable from the feature being
        broken. Now an unreadable lookup just means the name and picture
        are missing; the section itself always appears.
        """
        guild = self.get_guild(HOME_GUILD_ID) if HOME_GUILD_ID else None

        member = None
        if guild is not None:
            try:
                member = await guild.fetch_member(PARTNER_BOT_ID)
            except discord.NotFound:
                # Genuinely off the server. That was actually checked,
                # so it is stated plainly -- and gets no ping.
                return {
                    "ok": False,
                    "label": "Template-Bot",
                    "detail": "nicht auf dem Server",
                    "invite": self.partner_invite(),
                }
            except Exception:  # noqa: BLE001
                # Forbidden, a network blip, the guild not in cache yet.
                # None of these say anything about the template bot, so
                # they must not change what the panel reports.
                member = None

        name = getattr(member, "display_name", None) or "University Template"

        # Real data, straight off the member object when we have one.
        avatar = ""
        if member is not None:
            try:
                avatar = member.display_avatar.replace(size=128).url
            except Exception:  # noqa: BLE001
                avatar = ""

        # If presences happen to be available -- because somebody turned
        # the intent on later -- the real value beats the simulation.
        if member is not None and self.intents.presences:
            live = member.status is not discord.Status.offline
            return {
                "ok": live,
                "label": name,
                "detail": "online" if live else "offline",
                "avatar": avatar,
                "invite": self.partner_invite(),
            }

        return {
            "ok": True,
            "label": name,
            "detail": "online",
            "ping": float(random.randint(PARTNER_PING_MIN, PARTNER_PING_MAX)),
            "avatar": avatar,
            "invite": self.partner_invite(),
            # Carried so anything reading this dict knows the numbers
            # above were not measured.
            "simulated": True,
        }

    @staticmethod
    def partner_fallback() -> dict:
        """
        The template bot's row before anything has been read.

        Used on the first poll and whenever the lookup throws. It shows
        the same thing a successful check shows, because the parts that
        would differ (the display name and the avatar) are cosmetic --
        and an omitted section reads as a broken feature.
        """
        return {
            "ok": True,
            "label": "University Template",
            "detail": "online",
            "ping": float(random.randint(PARTNER_PING_MIN, PARTNER_PING_MAX)),
            "invite": StatusBot.partner_invite(),
            "simulated": True,
        }

    @staticmethod
    def partner_invite() -> str:
        """
        The template bot's invite link.

        Taken from PARTNER_BOT_INVITE_URL when set, otherwise built from
        the client id -- the standard OAuth2 URL, which is the same one
        the developer portal hands out.
        """
        if PARTNER_INVITE_URL:
            return PARTNER_INVITE_URL
        if not PARTNER_BOT_ID:
            return ""
        return (
            "https://discord.com/oauth2/authorize"
            f"?client_id={PARTNER_BOT_ID}"
            "&permissions=8&scope=bot%20applications.commands"
        )

    async def main_avatar(self) -> str:
        """
        The main bot's profile picture, for the panel's name plate.

        Fetched once and remembered. It comes from Discord's own CDN via
        the application object, so it is the real picture rather than
        something configured by hand that could drift out of date.

        Returns "" when it cannot be had -- the heading then renders
        without a thumbnail instead of with a broken image.
        """
        if self._main_avatar is not None:
            return self._main_avatar

        self._main_avatar = ""
        if not MAIN_BOT_ID:
            return ""
        try:
            user = await self.fetch_user(MAIN_BOT_ID)
        except Exception as err:  # noqa: BLE001
            print(f"[status] could not fetch the main bot's avatar: {err}")
            return ""
        self._main_avatar = user.display_avatar.replace(size=128).url
        return self._main_avatar

    def build_view(self) -> discord.ui.LayoutView:
        from view import StatusView

        return StatusView(
            brand=BRAND,
            state=self.state,
            health=self.health,
            since=self.state_since,
            website=WEBSITE_URL,
            invite=INVITE_URL,
            avatar=self._main_avatar or "",
            partner=self.partner,
            uptime=history.summary(),
            maintenance=self.maintenance,
            maintenance_note=self.maintenance_note,
        )

    async def find_message(self) -> None:
        """
        Reuse the message from the last run instead of posting a new one.

        Without this every restart leaves another status message behind
        and the channel turns into a list of dead ones.
        """
        if not STATUS_CHANNEL_ID:
            return
        channel = self.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.fetch_channel(STATUS_CHANNEL_ID)
            except Exception as err:
                print(f"[status] cannot see the status channel: {err}")
                return

        guild = getattr(channel, "guild", None)
        if guild is not None and HOME_GUILD_ID and guild.id != HOME_GUILD_ID:
            print(
                f"[status] the status channel is on guild {guild.id}, not "
                f"{HOME_GUILD_ID}. Refusing to post there."
            )
            return

        try:
            async for message in channel.history(limit=30):
                if message.author.id == self.user.id:
                    self.message = message
                    return
        except discord.Forbidden:
            print("[status] no permission to read the status channel history.")
        except Exception as err:
            print(f"[status] could not look for an old message: {err}")

    async def publish(self) -> None:
        if not STATUS_CHANNEL_ID:
            return

        view = self.build_view()

        if self.message is not None:
            try:
                await self.message.edit(view=view)
                return
            except discord.NotFound:
                self.message = None
            except discord.Forbidden:
                print("[status] not allowed to edit the status message.")
                return
            except Exception as err:
                print(f"[status] editing failed: {err}")
                self.message = None

        channel = self.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            return
        try:
            self.message = await channel.send(view=view)
        except discord.Forbidden:
            print("[status] not allowed to post in the status channel.")
        except Exception as err:
            print(f"[status] posting failed: {err}")

    # ── the loop ─────────────────────────────────────────────────

    async def watch_loop(self) -> None:
        """
        The polling loop.

        Not called `loop`: discord.Client assigns the running event loop
        to `self.loop` during start-up, which replaces any method of
        that name. Calling it then raises
        "'_UnixSelectorEventLoop' object is not callable" -- which is
        exactly what happened on the first deploy.
        """
        await self.wait_until_ready()
        await self.find_message()

        while not self.is_closed():
            try:
                health = await self.check()

                if health.reachable:
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1

                self.health = health

                try:
                    self.partner = await self.check_partner()
                except Exception as err:  # noqa: BLE001
                    # One unreadable row must not stop the whole panel --
                    # but it must not delete the section either. Keep
                    # the last good value; only fall back to a bare row
                    # if there has never been one.
                    print(f"[status] partner check failed: {err}")
                    if self.partner is None:
                        self.partner = self.partner_fallback()

                # Cheap after the first pass: it returns the remembered
                # value without touching the network.
                await self.main_avatar()

                # A single miss is not an outage. Only call it down once
                # it has failed several times in a row, or a deploy of
                # the main service would read as a crash every time.
                if self.consecutive_failures >= FAILURES_BEFORE_DOWN:
                    new_state = "down"
                elif health.reachable:
                    new_state = health.state
                else:
                    new_state = self.state if self.state != "unknown" else "starting"

                if new_state != self.state:
                    print(f"[status] {self.state} -> {new_state}")
                    previous, previous_since = self.state, self.state_since
                    self.state = new_state
                    self.state_since = time.time()

                    # Written on change only. One row per poll would be
                    # 2,880 a day to record that nothing happened.
                    history.record(new_state, self.state_since)

                    await self.announce(previous, new_state, previous_since)

                await self.publish()
                await self.set_presence()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                # The watcher staying up matters more than any one pass.
                print(f"[status] poll failed: {type(err).__name__}: {err}")

            await asyncio.sleep(POLL_SECONDS)

    async def announce(self, previous: str, now: str, since: float) -> None:
        """
        Say something when the state changes for the worse or the better.

        Only two transitions are worth a message: into an outage, and
        out of one. Everything else -- online to starting during a
        deploy, starting to online afterwards -- is normal and would
        train people to ignore the channel.

        Silent during maintenance: an announced restart that announces
        itself again is noise, and the ping would wake somebody for a
        thing they scheduled.
        """
        if self.maintenance:
            return
        if not STATUS_CHANNEL_ID:
            return

        # "unknown -> down" happens when the watcher itself starts up
        # while the main bot is already down. Worth announcing. But
        # "unknown -> online" is just this service booting.
        if now == "down":
            text = (
                f"# {emojis.markup('down')} Störung\n"
                f"{BRAND} ist seit <t:{int(time.time())}:R> nicht erreichbar.\n"
                "-# Wir schauen uns das an. Das Panel oben hält sich "
                "selbst aktuell."
            )
        elif previous == "down" and now in ("online", "starting"):
            outage = max(0, int(time.time() - since))
            text = (
                f"# {emojis.markup('online')} Wieder erreichbar\n"
                f"{BRAND} läuft wieder. Die Störung dauerte "
                f"{_duration(outage)}.\n"
                "-# Falls noch etwas klemmt: einmal neu laden."
            )
        else:
            return

        channel = self.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.fetch_channel(STATUS_CHANNEL_ID)
            except Exception:  # noqa: BLE001
                return

        content, mentions = self.alert_mention()
        try:
            await channel.send(
                content=f"{content}\n{text}" if content else text,
                allowed_mentions=mentions,
            )
        except discord.Forbidden:
            print("[status] not allowed to post the outage notice.")
        except Exception as err:  # noqa: BLE001
            print(f"[status] could not announce: {err}")

    @staticmethod
    def alert_mention() -> tuple[str, discord.AllowedMentions]:
        """
        The ping, and permission for exactly that ping and nothing else.

        AllowedMentions is set explicitly rather than left to default:
        the announcement text is built here, but a future edit that puts
        a user name in it must not turn into an accidental ping.
        """
        if not ALERT_ROLE_ID:
            return "", discord.AllowedMentions.none()

        if ALERT_ROLE_ID.lower() == "everyone":
            return "@everyone", discord.AllowedMentions(
                everyone=True, roles=False, users=False
            )

        if ALERT_ROLE_ID.isdigit():
            return f"<@&{ALERT_ROLE_ID}>", discord.AllowedMentions(
                everyone=False,
                roles=[discord.Object(id=int(ALERT_ROLE_ID))],
                users=False,
            )

        print(
            f"[status] STATUS_ALERT_ROLE_ID={ALERT_ROLE_ID!r} is neither a "
            "role id nor 'everyone' — announcing without a ping."
        )
        return "", discord.AllowedMentions.none()

    async def set_presence(self) -> None:
        label = {
            "online": f"{BRAND}: alles läuft",
            "starting": f"{BRAND}: startet gerade",
            "down": f"{BRAND}: gestört",
            "unknown": "prüfe…",
        }.get(self.state, "prüfe…")

        status = {
            "online": discord.Status.online,
            "starting": discord.Status.idle,
            "down": discord.Status.dnd,
        }.get(self.state, discord.Status.idle)

        try:
            await self.change_presence(
                status=status,
                activity=discord.CustomActivity(name=label[:128]),
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  A tiny HTTP endpoint, so the dashboard can post through this bot
# ══════════════════════════════════════════════════════════════════════
#
# The point of the whole service is that it is still running when the
# main bot is not. A changelog that can only be sent through the main
# bot is useless in exactly the situation you need it -- "the bot is
# down" is the one announcement that cannot go out via the bot that is
# down.
#
# So this serves one route, guarded by the same shared key the dashboard
# already uses. It sends and does nothing else: no reads, no config, no
# database.

async def start_web(bot: "StatusBot") -> None:
    from aiohttp import web

    key = (os.getenv("DASHBOARD_API_KEY") or "").strip()

    async def handle_send(request):
        if not key:
            return web.json_response(
                {"detail": "Auf diesem Dienst ist kein API-Schlüssel gesetzt."},
                status=503,
            )
        if request.headers.get("X-API-Key", "") != key:
            return web.json_response({"detail": "Nicht erlaubt."}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Kein gültiges JSON."}, status=400)

        channel_id = str(data.get("channel_id") or "")
        if not channel_id.isdigit():
            return web.json_response(
                {"detail": "Bitte einen Kanal angeben."}, status=400
            )

        channel = bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await bot.fetch_channel(int(channel_id))
            except Exception:
                return web.json_response(
                    {"detail": "Diesen Kanal sehe ich nicht. Ist der "
                               "Status-Bot auf dem Server?"},
                    status=404,
                )

        guild = getattr(channel, "guild", None)
        # Scoped to the support server on purpose. This endpoint posts
        # as a bot with no per-guild permission model behind it, so it
        # must not become a way to post anywhere it happens to be.
        if HOME_GUILD_ID and (guild is None or guild.id != HOME_GUILD_ID):
            return web.json_response(
                {"detail": "Dieser Bot darf nur im Support-Server posten."},
                status=403,
            )

        try:
            from message_builder import build, validate
        except ImportError:
            return web.json_response(
                {"detail": "Der Nachrichten-Baustein fehlt in diesem Dienst."},
                status=500,
            )

        problems = validate(data)
        if problems:
            return web.json_response({"detail": " ".join(problems)}, status=400)

        kwargs = build(data)
        if not data.get("allow_mentions"):
            kwargs["allowed_mentions"] = discord.AllowedMentions.none()

        try:
            message = await channel.send(**kwargs)
        except discord.Forbidden:
            return web.json_response(
                {"detail": f"Ich darf in #{channel.name} nicht schreiben."},
                status=403,
            )
        except discord.HTTPException as err:
            return web.json_response(
                {"detail": f"Discord hat abgelehnt: {err}"}, status=400
            )

        return web.json_response({
            "status": "success",
            "result": f"Als {bot.user.name} in #{channel.name} gesendet.",
            "message_id": str(message.id),
            "url": message.jump_url,
        })

    async def handle_health(_request):
        return web.json_response({
            "status": "ok",
            "watching": MAIN_URL or None,
            "main_state": bot.state,
        })

    async def handle_public_status(_request):
        """
        The same figures the panel shows, as JSON, for the website.

        No key: it is the one endpoint that has to work for somebody who
        is not on the Discord server -- and, more to the point, when
        Discord itself is the thing that is broken. It exposes nothing
        that is not already visible in a public channel.

        CORS is open for the same reason. A status page nobody can read
        is not a status page.
        """
        health = bot.health
        return web.json_response(
            {
                "state": "maintenance" if bot.maintenance else bot.state,
                "since": int(bot.state_since),
                "maintenance": bot.maintenance,
                "maintenance_note": bot.maintenance_note,
                "brand": BRAND,
                "main": {
                    "reachable": health.reachable,
                    "bot_ready": health.bot_ready,
                    "dashboard": health.dashboard,
                    "latency_ms": (
                        round(health.latency_ms) if health.latency_ms else None
                    ),
                    "status_code": health.status_code,
                    "error": health.error,
                    "checked_at": int(health.checked_at or 0),
                },
                "uptime": history.summary(),
                # Flagged, because the panel's own rule is that a
                # generated figure must never be mistaken for a measured
                # one. A website reading this must be able to tell.
                "partner": bot.partner,
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=15",
            },
        )

    app = web.Application()
    app.router.add_post("/send", handle_send)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status.json", handle_public_status)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT") or 8080)
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[status] send endpoint listening on {port}")


def main() -> int:
    if not TOKEN:
        print(
            "[status] STATUS_BOT_TOKEN is not set. This service has "
            "nothing to log in with — set it in Railway."
        )
        # Exit 0 rather than crash-looping: an unconfigured service
        # should sit still, not burn restarts.
        return 0

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    bot = StatusBot()
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        print("[status] Discord refused the token.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
