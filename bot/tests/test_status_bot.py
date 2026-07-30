#!/usr/bin/env python3
"""
The status bot.

A second, small bot whose job is to still be running when the main one
is not, and to say so.

The design decision worth defending: it is a **separate Railway
service**, not another process in the main container. A watcher sharing
a container with what it watches cannot report the failure that matters
-- when Railway restarts the container, the deploy fails, or
`restartPolicyMaxRetries = 5` is used up, both processes die together
and the outage goes unannounced. That is the exact case a status bot
exists for, so the whole thing would have been decoration.

What is checked here:

  * The check reads /health from outside and tells the three states
    apart: reachable and ready, reachable but starting (the main bot
    answers 503 during a deploy), and not reachable at all.
  * One missed poll is not an outage. Without that, every deploy of the
    main service would announce a crash.
  * The wording never claims more than was measured. "Not reachable" is
    not the same statement as "the bot is offline", and when the checker
    itself might be the problem, only the first one is honest.
  * The send endpoint is locked down: shared key required, and scoped
    to the support guild so it cannot become a way to post anywhere the
    bot happens to be.

Run:  python3 tests/test_status_bot.py
"""

import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
STATUS = os.path.join(ROOT, "statusbot")

sys.path.insert(0, BOT)
sys.path.insert(0, STATUS)

HOME_GUILD = 1530378233579704370

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


# ══════════════════════════════════════════════════════════════════════
#  A stand-in for the main bot's /health
# ══════════════════════════════════════════════════════════════════════


MODE = {"value": "ok"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        mode = MODE["value"]
        if mode == "ok":
            body, code = {"status": "ok", "bot_ready": True,
                          "dashboard": "online"}, 200
        elif mode == "starting":
            # What the real endpoint answers during a deploy: 503 with a
            # body that still says what is going on.
            body, code = {"status": "starting", "bot_ready": False,
                          "dashboard": "starting"}, 503
        else:
            self.close_connection = True
            return
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


# ══════════════════════════════════════════════════════════════════════
#  The layout
# ══════════════════════════════════════════════════════════════════════


class FakeHealth:
    def __init__(self, **kw):
        self.reachable = kw.get("reachable", True)
        self.bot_ready = kw.get("ready", True)
        self.dashboard = kw.get("dashboard", "online")
        self.latency_ms = kw.get("latency", 120.0)
        self.status_code = kw.get("code", 200)
        self.error = kw.get("error")
        self.checked_at = time.time()

    @property
    def state(self):
        if not self.reachable:
            return "down"
        return "online" if (self.bot_ready and self.dashboard == "online") else "starting"


def buttons(view) -> list[tuple[str, str]]:
    """Every link button in the view, as (label, url)."""
    import discord

    found: list[tuple[str, str]] = []

    def walk(item):
        if isinstance(item, discord.ui.Button):
            found.append((item.label, item.url))
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return found


def render(view) -> str:
    """Every bit of text in a LayoutView, flattened."""
    found: list[str] = []

    def walk(item):
        content = getattr(item, "content", None)
        if isinstance(content, str):
            found.append(content)
        # A Section keeps its thumbnail/button in `accessory`, not in
        # `children`. Walking only children misses it entirely, which
        # is how an earlier version of this file "passed" while the
        # avatars were not rendered at all.
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return "\n".join(found)


def section(text: str, heading: str) -> str:
    """
    Everything under a heading, or "" when the heading is not there.

    Plain `.split(...)[1]` raises IndexError when the heading is
    missing, which crashes the run instead of failing a check -- and a
    crashed run reports nothing at all about the checks after it.
    """
    parts = text.split(heading, 1)
    return parts[1] if len(parts) > 1 else ""


def thumbnails(view) -> list[str]:
    """Every thumbnail URL in the view."""
    import discord

    found: list[str] = []

    def walk(item):
        if isinstance(item, discord.ui.Thumbnail):
            found.append(item.media.url)
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return found


def test_layout():
    print("\nThe status message")

    from view import StatusView

    ok = render(StatusView(brand="University Bot", state="online",
                           health=FakeHealth(), since=time.time() - 3600))
    check("the running state says so", "Alle Systeme laufen" in ok, ok[:60])
    check("it shows how long that has held", "1 Stunde" in ok, ok[:80])
    check("it shows the response time", "120 ms" in ok)
    check("green marks for the things that are up", ok.count("🟢") >= 3, ok)

    starting = render(StatusView(
        brand="University Bot", state="starting",
        health=FakeHealth(ready=False, dashboard="starting", code=503),
        since=time.time(),
    ))
    check("a deploy reads as starting, not broken",
          "Startet gerade" in starting, starting[:60])
    check("and says how long that normally takes",
          "ein bis zwei Minuten" in starting)

    down = render(StatusView(
        brand="University Bot", state="down",
        health=FakeHealth(reachable=False, error="Zeitüberschreitung",
                          code=None, latency=None),
        since=time.time(),
    ))
    check("an outage is called out", "Störung" in down, down[:60])
    # The honest wording. We know the check failed; we do not know the
    # bot is gone, and the checker itself could be the problem.
    check("it says not reachable, not 'the bot is offline'",
          "nicht erreichbar" in down and "ist offline" not in down,
          down[:120])
    check("it names the likely causes",
          "Neustart" in down and "Discord" in down)
    check("what it cannot see is marked unknown, not red",
          down.count("⚪") >= 2, down)


# ══════════════════════════════════════════════════════════════════════
#  The check itself
# ══════════════════════════════════════════════════════════════════════


async def run_checks():
    print("\nChecking the main bot")

    import aiohttp
    import status_bot as sb

    server = HTTPServer(("127.0.0.1", 8097), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sb.MAIN_URL = "http://127.0.0.1:8097"

    bot = sb.StatusBot.__new__(sb.StatusBot)
    bot.session = aiohttp.ClientSession()

    try:
        MODE["value"] = "ok"
        health = await bot.check()
        check("a healthy bot reads as online", health.state == "online",
              health.state)
        check("the http status is recorded", health.status_code == 200)
        check("the latency is measured", (health.latency_ms or 0) > 0)

        MODE["value"] = "starting"
        health = await bot.check()
        check("a 503 during a deploy reads as starting",
              health.state == "starting", health.state)
        check("and is still counted as reachable", health.reachable is True,
              "503 means it answered; treating that as down would call "
              "every deploy an outage")

        server.shutdown()
        health = await bot.check()
        check("an unreachable bot reads as down", health.state == "down",
              health.state)
        check("with a reason", bool(health.error), str(health.error))

        sb.MAIN_URL = ""
        health = await bot.check()
        check("no URL configured is handled, not crashed",
              health.reachable is False and "MAIN_BOT_URL" in (health.error or ""),
              str(health.error))
    finally:
        await bot.session.close()


def test_links_and_partner():
    """
    The four-part layout, the buttons, and the one place where the panel
    knowingly shows a number it did not measure.

    Everything about the main bot is measured -- and the rule that
    nothing unmeasured may be drawn as a fact still holds there, which
    is what the "unreachable shows no latency" check below is about.

    The template bot's section is the deliberate exception, on the
    owner's instruction, and it is exceptional because the figures are
    not obtainable at all: online status needs the Presences intent
    (without it Member.status is *always* offline), and no API reports
    a third-party bot's gateway latency to anyone but that bot. So the
    ping is generated. What is checked here is that it is generated
    inside the configured range, that it changes, and that the switch
    to turn it off still leads back to the honest wording.
    """
    print("\nLayout, links and the template bot")

    from view import StatusView

    # ── the order of the four blocks ─────────────────────────────
    full = render(StatusView(
        brand="University Bot", state="online", health=FakeHealth(),
        since=time.time(), website="https://example.com",
        invite="https://example.com/invite",
        partner={"ok": True, "label": "University Template",
                 "detail": "online", "ping": 42.0,
                 "invite": "https://example.com/t"},
    ))
    # str.index raises when a marker is missing, which turns a failed
    # check into a crashed run -- the rest of the file then never runs
    # and the summary says nothing. Reported as a failure instead.
    markers = ["Alle Systeme laufen", "## University Bot",
               "## University Template", "University Status System"]
    missing = [marker for marker in markers if marker not in full]
    check("headline, main bot, template bot and footer are all present",
          not missing, f"missing: {missing}")
    if not missing:
        positions = [full.index(marker) for marker in markers]
        check("and they come in that order",
              positions == sorted(positions), full)

    # ── the footer ───────────────────────────────────────────────
    footer = full.rsplit("\n", 1)[-1]
    check("the footer names the status system", "University Status System" in footer,
          footer)
    check("and carries a live timestamp", "<t:" in footer and ":R>" in footer,
          "a relative stamp counts itself up in every client, so the "
          "line stays true between edits")
    check("the 30-second note is gone from the footer",
          "30 Sekunden" not in full and "alle 30" not in full, footer)
    check("the footer is one line, name and time only",
          footer.count("·") == 1 and "geprüft" not in footer, footer)

    # ── buttons, per bot ─────────────────────────────────────────
    empty = StatusView(brand="B", state="online", health=FakeHealth(),
                       since=time.time())
    check("no buttons when nothing is configured", buttons(empty) == [],
          "a button that goes nowhere is worse than no button")

    labels = [label for label, _ in buttons(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        website="https://example.com", invite="https://example.com/invite",
    ))]
    check("the main bot gets a dashboard button", "Dashboard" in labels, str(labels))
    check("and an invite button", "Einladen" in labels, str(labels))

    # The support button is gone on purpose: the panel lives in the
    # support server, so the link would point at the room you are in.
    check("there is no support button any more", "Support" not in labels,
          str(labels))

    source_view = open(os.path.join(STATUS, "view.py"), encoding="utf-8").read()
    check("the view takes no support argument", "support" not in source_view,
          "a leftover parameter invites the button back")
    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("and the bot no longer reads SUPPORT_INVITE_URL",
          "SUPPORT_INVITE_URL" not in source)

    partial = StatusView(brand="B", state="online", health=FakeHealth(),
                         since=time.time(), website="https://example.com")
    check("only the configured ones show up", len(buttons(partial)) == 1,
          str(buttons(partial)))

    # The template bot has no website, so exactly one button.
    with_partner = buttons(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        website="https://example.com", invite="https://example.com/i",
        partner={"ok": True, "label": "T", "detail": "online", "ping": 20.0,
                 "invite": "https://example.com/t"},
    ))
    check("the template bot gets its own invite button",
          ("Einladen", "https://example.com/t") in with_partner,
          str(with_partner))
    check("and no dashboard button, because it has no website",
          [url for label, url in with_partner if label == "Dashboard"]
          == ["https://example.com"],
          str(with_partner))

    # ── the template row ─────────────────────────────────────────
    without = render(StatusView(brand="B", state="online",
                                health=FakeHealth(), since=time.time()))
    check("no template section when it could not be checked",
          "Template" not in without,
          "an unknown row invented is the thing being avoided")

    shown = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        partner={"ok": True, "label": "University Template",
                 "detail": "online", "ping": 63.0},
    ))
    check("the template bot shows as online", "🟢 **Status**" in shown, shown)
    check("with its own ping", "63 ms" in shown, shown)
    check("drawn the same way as the main bot's",
          "▰" in section(shown, "## University Template"), shown)

    missing = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        partner={"ok": False, "label": "Template-Bot",
                 "detail": "nicht auf dem Server"},
    ))
    check("a template bot that is really absent is marked red",
          "🔴 **Status**" in missing and "nicht auf dem Server" in missing,
          missing[-250:])
    check("and gets no invented ping when it is not there",
          "ms" not in section(missing, "## Template-Bot"), missing[-250:])

    # ── the main bot's figures are still never invented ──────────
    down = render(StatusView(
        brand="B", state="down",
        health=FakeHealth(reachable=False, error="Zeitüberschreitung",
                          code=None, latency=None),
        since=time.time(),
    ))
    check("an unreachable main bot shows no latency at all",
          "ms" not in down,
          "inventing a ping for something we could not reach is the "
          "exact failure this rule exists for")
    check("and marks the rest as not checked",
          down.count("⚪") >= 2 and "nicht geprüft" in down, down[:200])


def test_partner_ping_range():
    """
    The generated ping, and the rule that the section is always there.

    The figures are simulated on the owner's instruction and there is
    deliberately no switch and no variable for them: the section was
    invisible in production precisely because it depended on
    PARTNER_BOT_CLIENT_ID being set on the status service, and it was
    not. check_partner returned None before doing anything and the whole
    block silently vanished, with nothing in the log to say why. So the
    id is a constant and the method never returns None.

    A constant ping would be the giveaway that it is fake, and a value
    outside the range would mean the bounds do nothing.
    """
    print("\nThe template bot's section")

    import importlib
    import status_bot as sb
    importlib.reload(sb)

    check("the template bot's id is baked in, not from the environment",
          sb.PARTNER_BOT_ID == 1530742522589089952,
          f"{sb.PARTNER_BOT_ID} -- an unset variable is how the whole "
          "section disappeared from the live panel")
    check("the low end is 10", sb.PARTNER_PING_MIN == 10,
          str(sb.PARTNER_PING_MIN))
    check("the high end is 100", sb.PARTNER_PING_MAX == 100,
          str(sb.PARTNER_PING_MAX))

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("there is no on/off switch for it",
          "PARTNER_SIMULATED" not in source,
          "the owner asked for one less thing to configure")

    # Drive the real code path rather than re-implementing it here.
    class FakeMember:
        display_name = "University Template"
        status = None

        class display_avatar:
            @staticmethod
            def replace(**kwargs):
                return type("A", (), {"url": "https://cdn/x.png"})()

    class FakeGuild:
        async def fetch_member(self, _id):
            return FakeMember()

    bot = sb.StatusBot.__new__(sb.StatusBot)
    bot.get_guild = lambda _id: FakeGuild()
    bot._intents = type("I", (), {"presences": False})()
    type(bot).intents = property(lambda self: self._intents)

    try:
        seen = set()
        row = None
        for _ in range(200):
            row = asyncio.run(bot.check_partner())
            seen.add(row["ping"])
            if not (sb.PARTNER_PING_MIN <= row["ping"] <= sb.PARTNER_PING_MAX):
                break

        check("every value lands inside the range",
              all(sb.PARTNER_PING_MIN <= value <= sb.PARTNER_PING_MAX
                  for value in seen),
              str(sorted(seen)[:5]))
        check("and it is not the same number every poll", len(seen) > 5,
              f"{len(seen)} distinct values in 200 polls")
        check("the row reads as online",
              row["ok"] is True and row["detail"] == "online")
        check("it carries the bot's own name",
              row["label"] == "University Template")
        check("an invite link is built from the client id",
              str(sb.PARTNER_BOT_ID) in row["invite"]
              and row["invite"].startswith("https://discord.com/oauth2/authorize"),
              row["invite"])
        check("the dict says the figures are simulated",
              row.get("simulated") is True,
              "a caller that cannot tell measured from generated will "
              "eventually copy the number somewhere it matters")

        # ── the section must survive every failure mode ──────────
        #
        # This is the actual production bug: any of these returned None
        # and the block disappeared from the panel entirely.
        bot.get_guild = lambda _id: None
        no_guild = asyncio.run(bot.check_partner())
        check("no guild in cache still shows the section",
              no_guild is not None and no_guild["ok"] is True,
              str(no_guild))
        check("and still has a ping", "ping" in (no_guild or {}), str(no_guild))

        import discord

        class Forbidden:
            async def fetch_member(self, _id):
                raise discord.Forbidden(
                    type("R", (), {"status": 403, "reason": "Forbidden"})(),
                    "no",
                )

        bot.get_guild = lambda _id: Forbidden()
        denied = asyncio.run(bot.check_partner())
        check("a permission error still shows the section",
              denied is not None and denied["ok"] is True, str(denied))

        class Broken:
            async def fetch_member(self, _id):
                raise RuntimeError("network")

        bot.get_guild = lambda _id: Broken()
        broken = asyncio.run(bot.check_partner())
        check("an unexpected error still shows the section",
              broken is not None and broken["ok"] is True, str(broken))
        check("it falls back to a sensible name",
              broken["label"] == "University Template", str(broken))

        # The one case that genuinely changes what is displayed.
        class Absent:
            async def fetch_member(self, _id):
                raise discord.NotFound(
                    type("R", (), {"status": 404, "reason": "Not Found"})(),
                    "unknown member",
                )

        bot.get_guild = lambda _id: Absent()
        gone = asyncio.run(bot.check_partner())
        check("an absent template bot is reported as absent",
              gone["ok"] is False and gone["detail"] == "nicht auf dem Server",
              str(gone))
        check("and gets no ping, generated or otherwise",
              "ping" not in gone,
              "the one thing actually established here is that it is "
              "NOT there; a latency next to that is nonsense")
    finally:
        del type(bot).intents

    check("check_partner never returns None",
          "return None" not in source.split("async def check_partner")[1]
                                    .split("@staticmethod")[0],
          "returning None deletes the whole section from the panel")

    # There must be something to draw before the first check finishes.
    check("there is a fallback row for the very first poll",
          "def partner_fallback" in source)
    check("and the bot starts out holding it",
          "self.partner: dict = self.partner_fallback()" in source,
          "otherwise the first published panel has no template section")
    check("a failed poll keeps the last row instead of dropping it",
          "if self.partner is None:" in source,
          "blanking it on one bad poll makes the section flicker away")

    # The comments have to be there: the next person to read this file
    # must not mistake the ping for a measurement.
    check("the code says out loud that the ping is not measured",
          "not measured" in source or "are simulated" in source,
          "an unlabelled fake number is how a status page starts lying "
          "by accident")
    check("and explains why it cannot be", "gateway latency" in source)


def test_discord_markup():
    """
    The panel is written in Discord's own markup, not in plain text.

    This is not decoration. Each of these renders as something the
    client maintains or draws, where the plain-text equivalent goes
    stale or reads as an undifferentiated wall:

      * `<t:...:R>` and `<t:...:t>` are counted up by the client, so a
        message edited every 30 seconds is never wrong in between. A
        written-out "Stand: 12:04 UTC" is wrong the moment it is sent.
      * `>` draws a continuous bar down a run of lines, which groups
        the readings without a box.
      * `#`/`##`/`###` are real headings, so the two bots are visibly
        separate blocks rather than paragraphs.
      * `-#` is small print, for the things that are context.
      * backticks put measured values in code type, which separates a
        reading from prose at a glance.
    """
    print("\nDiscord markup")

    from view import StatusView

    full = render(StatusView(
        brand="University Bot", state="online", health=FakeHealth(),
        since=time.time() - 7200, website="https://example.com",
        invite="https://example.com/i",
        partner={"ok": True, "label": "University Template",
                 "detail": "online", "ping": 42.0},
    ))

    check("the headline is an h1", full.startswith("# 🟢"), full[:40])
    check("each bot gets an h2",
          "## University Bot" in full and "## University Template" in full)
    check("and a state line as an h3",
          "### 🟢 Betriebsbereit" in full and "### 🟢 Online" in full, full)

    quoted = [line for line in full.splitlines() if line.startswith("> ")]
    check("the readings are quoted lines", len(quoted) >= 6,
          f"{len(quoted)} quoted lines")
    check("every reading row is quoted",
          all(line.startswith("> ") for line in full.splitlines()
              if "**Antwortzeit**" in line or "**Erreichbar**" in line),
          full)
    check("the explanation is quoted too",
          "> Der Bot ist erreichbar und bereit." in full)

    check("measured values are in code type",
          "`143 ms`" in full or "`120 ms`" in full, full)
    check("the http status too", "`HTTP 200`" in full, full)

    check("context lines use small print", full.count("-# ") >= 3, full)
    check("labels are bold", full.count("**") >= 8, full)

    # Timestamps: the client keeps these current, a written time does
    # not. Both kinds appear -- relative in the footer, clock time for
    # when the state last changed.
    check("the footer timestamp is relative", "<t:" in full and ":R>" in full)
    check("the state change carries a clock stamp", ":t>" in full, full)
    check("no hand-written UTC clock reading is left",
          "UTC" not in full,
          "a fixed clock reading is stale the moment the message is "
          "edited; that is what the timestamp markup is for")

    # A separator between the blocks, drawn by Discord rather than by
    # a row of dashes in the text.
    import discord

    def count(kind):
        found = []

        def walk(item):
            if isinstance(item, kind):
                found.append(item)
            for child in getattr(item, "children", None) or []:
                walk(child)

        for child in StatusView(
            brand="B", state="online", health=FakeHealth(), since=time.time(),
            partner={"ok": True, "label": "T", "detail": "online", "ping": 5.0},
        ).children:
            walk(child)
        return len(found)

    check("real separators, not dashes in the text",
          count(discord.ui.Separator) >= 3 and "---" not in full,
          f"{count(discord.ui.Separator)} separators")

    source_view = open(os.path.join(STATUS, "view.py"), encoding="utf-8").read()
    check("the large spacing is used between bots",
          "SeparatorSpacing.large" in source_view,
          "same-size gaps everywhere make one block of two")


def test_avatars():
    """
    Each bot's name plate carries its own profile picture.

    Both are real: the main bot's comes from its application over
    Discord's CDN, the template bot's straight off the member object
    that was already fetched. Neither is configured by hand, so neither
    can drift out of date.

    A missing avatar must cost nothing but the picture -- Section
    requires an accessory, so the heading falls back to plain text
    rather than raising.
    """
    print("\nAvatars")

    from view import StatusView

    main_url = "https://cdn.discordapp.com/avatars/1/a.png?size=128"
    partner_url = "https://cdn.discordapp.com/avatars/2/b.png?size=128"

    view = StatusView(
        brand="University Bot", state="online", health=FakeHealth(),
        since=time.time(), avatar=main_url,
        partner={"ok": True, "label": "University Template",
                 "detail": "online", "ping": 30.0, "avatar": partner_url},
    )
    urls = thumbnails(view)
    check("the main bot's avatar is shown", main_url in urls, str(urls))
    check("the template bot's too", partner_url in urls, str(urls))
    check("one each, no duplicates", len(urls) == 2, str(urls))

    # The heading text must survive either way.
    without = StatusView(
        brand="University Bot", state="online", health=FakeHealth(),
        since=time.time(),
        partner={"ok": True, "label": "T", "detail": "online", "ping": 30.0},
    )
    check("no avatar means no thumbnail", thumbnails(without) == [],
          str(thumbnails(without)))
    text = render(without)
    check("but the heading is still there", "## University Bot" in text, text)
    check("and so is the state line", "### 🟢 Betriebsbereit" in text, text)

    # The bot fetches them itself rather than taking them from config.
    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("the main avatar comes from Discord, not an env var",
          "display_avatar" in source and "await self.fetch_user" in source,
          "a URL pasted into config goes stale when the picture changes")
    check("the template avatar is read off the member object",
          "member.display_avatar" in source)
    check("a failed lookup is remembered, not retried every poll",
          "self._main_avatar is not None" in source,
          "one broken fetch must not mean a request every 30 seconds")
    check("and it fails soft",
          'avatar = ""' in source,
          "no picture is a missing picture, not a broken panel")


def test_emojis():
    """
    The custom emojis, and the constraint that decides everything here.

    An application-owned emoji **only works for the application that
    owns it**. Discord's documentation is explicit: "an application can
    own up to 2000 emojis that can only be used by that app", and
    USE_EXTERNAL_EMOJIS does not lift it.

    The status bot is a *second* application. If these emojis live on
    the main bot's application, then posting <:online:1532...> puts that
    literal string into the panel -- a status page reading
    "<:online:1532168117319499839> Alle Systeme laufen" is worse than
    one with a plain green circle.

    So the ids are never used on faith. The bot asks Discord which
    emojis it owns and only those are used; the rest fall back to the
    characters that were there before. What is checked here is that both
    directions work and that the fallback is the *default* -- a panel
    drawn before the check finishes must show circles, not raw text.
    """
    print("\nCustom emojis")

    import emojis
    from view import StatusView

    # ── the safe default ─────────────────────────────────────────
    emojis.adopt({})
    check("nothing is adopted until Discord confirms it",
          emojis.missing() == sorted(emojis.CUSTOM),
          str(emojis.missing()))
    check("and every role falls back to a plain character",
          emojis.markup("online") == "🟢" and emojis.markup("down") == "🔴",
          f"{emojis.markup('online')} {emojis.markup('down')}")

    plain = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        website="https://example.com",
        partner={"ok": True, "label": "T", "detail": "online", "ping": 20.0},
    ))
    check("an unconfirmed emoji never reaches the message as raw text",
          "<:" not in plain,
          "this is the failure being guarded against: the literal "
          "'<:online:1532...>' printed into the panel")

    # ── when the application does own them ───────────────────────
    taken = emojis.adopt(dict(emojis.CUSTOM))
    check("every uploaded emoji is recognised",
          taken == ["loding", "offllien", "online", "plus", "uptime",
                    "website", "zbot"],
          str(taken))

    # Which ones are animated was read off Discord's CDN, not guessed:
    # the .webp?animated=true response carries an ANIM chunk for the
    # animated ones. Pinned here so a careless edit cannot flip it.
    animated = {name for name, (_, flag) in emojis.CUSTOM.items() if flag}
    check("the three moving ones are marked animated",
          animated == {"loding", "offllien", "online"},
          f"{sorted(animated)} -- checked against the CDN, not assumed")
    still = {name for name, (_, flag) in emojis.CUSTOM.items() if not flag}
    check("and the still ones are not",
          still == {"plus", "uptime", "website", "zbot"},
          f"{sorted(still)} -- an a: prefix on a still emoji breaks it "
          "just as thoroughly as a missing one")
    check("nothing is left over", emojis.missing() == [], str(emojis.missing()))

    custom = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        partner={"ok": True, "label": "T", "detail": "online", "ping": 20.0},
    ))
    # <a:...> for the animated ones. This is not a detail: writing
    # <:...> for an animated emoji makes Discord print the raw text
    # instead of a picture, and that is exactly what shipped -- uptime,
    # website and zbot appeared while online, offllien and loding came
    # out as ":online:" and friends.
    check("the online emoji is animated, so it uses the a: prefix",
          "<a:online:1532168117319499839>" in custom, custom[:160])
    check("the uptime emoji sits on the 'unchanged since' line",
          "<:uptime:1532168115339919552>" in custom, custom[:200])
    check("and a static emoji does NOT get the a: prefix",
          "<a:uptime:" not in custom,
          "the wrong way round breaks it just as thoroughly")
    check("and the bot emoji labels each bot",
          custom.count("<:zbot:1532168112810627222>") == 2, custom)

    down = render(StatusView(
        brand="B", state="down",
        health=FakeHealth(reachable=False, error="Zeitüberschreitung",
                          code=None, latency=None),
        since=time.time(),
    ))
    check("the offline emoji uses the a: prefix too",
          "<a:offllien:1532168119597142068>" in down, down[:160])
    check("but 'not checked' stays a hollow circle, not a red emoji",
          "⚪" in down,
          "red says we looked and it was broken; hollow says we did not "
          "look, and there is no uploaded emoji for that")

    starting = render(StatusView(
        brand="B", state="starting",
        health=FakeHealth(ready=False, dashboard="starting", code=503),
        since=time.time(),
    ))
    check("and so does the loading one",
          "<a:loding:1532168121182453950>" in starting, starting[:160])

    # ── buttons need a PartialEmoji, not a string ────────────────
    import discord

    picked = emojis.button("website")
    check("a custom button emoji is a PartialEmoji",
          isinstance(picked, discord.PartialEmoji),
          f"{type(picked).__name__} -- passing '<:name:id>' as a string "
          "makes Discord reject the component")
    check("with the right id", getattr(picked, "id", None) == 1532168114085826863,
          str(picked))
    check("and the website emoji lands on the dashboard button",
          any(isinstance(b, discord.PartialEmoji) and b.name == "website"
              for b in _button_emojis(StatusView(
                  brand="B", state="online", health=FakeHealth(),
                  since=time.time(), website="https://example.com"))),
          "the uploaded 'website' emoji exists for exactly this button")

    # A role with no uploaded emoji still returns something usable.
    # "unknown" is deliberately one: there is no emoji for "we did not
    # look at this", and reusing the red one would claim otherwise.
    check("a role without a custom emoji returns the plain character",
          emojis.button("unknown") == "⚪", str(emojis.button("unknown")))
    check("and the invite button uses the uploaded plus",
          getattr(emojis.button("invite"), "name", None) == "plus",
          str(emojis.button("invite")))

    # ── Discord's answer decides, not the table ──────────────────
    #
    # So an emoji re-uploaded as a still image starts rendering right
    # without anyone editing the code.
    emojis.adopt({"online": (1532168117319499839, False)})
    check("a re-uploaded still image drops the a: prefix by itself",
          emojis.markup("online") == "<:online:1532168117319499839>",
          emojis.markup("online"))

    # ── an id that does not match is refused ─────────────────────
    emojis.adopt({"online": (999, True)})
    check("a name collision with a different id is not adopted",
          emojis.markup("online") == "🟢",
          "some unrelated emoji uploaded later must not silently change "
          "what the panel draws")

    # ── the bot actually asks Discord ────────────────────────────
    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("the bot asks which emojis it owns",
          "fetch_application_emojis" in source,
          "using the ids without checking is the whole risk")
    # Reading the flag and then not passing it on is invisible in the
    # view -- the table would still be right and the panel would still
    # look correct in the tests. Checked at the seam instead.
    check("and passes Discord's animated flag through",
          "e.animated" in source,
          "dropping it here is how an animated emoji ends up written "
          "as <:name:id> and printed as raw text")

    # The same seam, exercised rather than grepped: feed adopt() what
    # the bot would build from a real answer and see what comes out.
    class FakeEmoji:
        def __init__(self, name, eid, animated):
            self.name, self.id, self.animated = name, eid, animated

    answer = [FakeEmoji(n, i, a) for n, (i, a) in emojis.CUSTOM.items()]
    emojis.adopt({e.name: (e.id, e.animated) for e in answer})
    check("an animated emoji from Discord renders with a:",
          emojis.markup("online").startswith("<a:"),
          emojis.markup("online"))
    check("and a static one without",
          emojis.markup("uptime").startswith("<:"),
          emojis.markup("uptime"))

    # A button whose emoji is animated must say so too, or Discord
    # shows a single frame.
    emojis.ROLES["_test_anim"] = ("online", "🟢")
    try:
        moving = emojis.button("_test_anim")
        check("an animated button emoji keeps its animated flag",
              getattr(moving, "animated", None) is True,
              f"{moving!r} -- a still frame instead of the animation")
    finally:
        del emojis.ROLES["_test_anim"]
    check("it does that on ready", "await self.load_emojis()" in source)
    check("a failed lookup falls back instead of crashing",
          "falling back to plain ones" in source)
    check("and unavailable ones are named in the log",
          "not available to this application" in source,
          "otherwise nobody can tell why the panel looks plain")

    emojis.adopt({})


def _button_emojis(view):
    """Every button's emoji in a view."""
    import discord

    found = []

    def walk(item):
        if isinstance(item, discord.ui.Button):
            found.append(item.emoji)
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return found


def test_no_name_clashes_with_discord():
    """
    Nothing on StatusBot may shadow something discord.Client owns.

    This is not hypothetical: the first deploy crash-looped with
    "'_UnixSelectorEventLoop' object is not callable" because the
    polling method was called `loop`, and discord.py assigns the running
    event loop to `self.loop` during start-up. The method was simply
    gone by the time anything called it.

    Nothing in the local tests caught that -- the clash only happens
    after a real login -- so it is checked statically instead.
    """
    print("\nNo name clashes with discord.Client")

    import ast

    import discord

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    tree = ast.parse(source)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StatusBot":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(item.name)
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.Attribute)
                    and isinstance(item.ctx, ast.Store)
                    and isinstance(item.value, ast.Name)
                    and item.value.id == "self"
                ):
                    names.add(item.attr)

    check("the class was found", bool(names), "StatusBot not parsed")

    # Overriding these is the normal way to extend a Client, and each
    # one calls super(). Everything else must not collide.
    intentional = {"__init__", "close", "setup_hook", "on_ready"}

    # Attributes discord.py sets at runtime rather than on the class,
    # which is why `loop` did not show up in dir(discord.Client).
    runtime_attributes = {
        "loop", "ws", "http", "user", "application_id",
        "shard_id", "shard_count",
    }

    owned = set(dir(discord.Client)) | runtime_attributes
    clashes = sorted((names & owned) - intentional)

    check("nothing shadows a discord.Client attribute",
          not clashes,
          f"{clashes} — this is how the first deploy crash-looped")

    # And the specific one, named, so the fix cannot quietly be undone.
    check("the polling loop is not called 'loop'",
          "loop" not in names or "async def loop" not in source,
          "discord.py overwrites self.loop with the event loop")
    check("it is called watch_loop", "async def watch_loop" in source)
    check("and that is what gets scheduled",
          "create_task(self.watch_loop())" in source)


def test_one_miss_is_not_an_outage():
    """
    A single failed poll happens: a deploy, a dropped connection, a slow
    response. Calling that an outage would mean an alarm on every
    update of the main service.
    """
    print("\nOne miss is not an outage")

    import status_bot as sb

    check("there is a threshold", sb.FAILURES_BEFORE_DOWN >= 2,
          str(sb.FAILURES_BEFORE_DOWN))
    check("and it is not absurdly high", sb.FAILURES_BEFORE_DOWN <= 10,
          str(sb.FAILURES_BEFORE_DOWN))

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("the loop counts consecutive failures",
          "self.consecutive_failures += 1" in source)
    check("and resets the counter on success",
          "self.consecutive_failures = 0" in source)
    check("down is only declared past the threshold",
          "self.consecutive_failures >= FAILURES_BEFORE_DOWN" in source)

    # With the default of 3 and a 30s poll, an outage is announced after
    # roughly a minute and a half. Fast enough to matter, slow enough
    # not to fire on a restart.
    window = sb.FAILURES_BEFORE_DOWN * sb.POLL_SECONDS
    check("an outage is noticed within a few minutes", window <= 300,
          f"{window}s")


# ══════════════════════════════════════════════════════════════════════
#  The send endpoint
# ══════════════════════════════════════════════════════════════════════


class FakeChannel:
    def __init__(self, guild_id=HOME_GUILD, name="status"):
        self.id = 555
        self.name = name
        self.guild = type("G", (), {"id": guild_id})()
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("M", (), {"id": 777, "jump_url": "https://discord.com/x"})()


class FakeBot:
    user = type("U", (), {"name": "University Status", "id": 1})()
    state = "online"

    def __init__(self):
        self.home = FakeChannel()
        self.foreign = FakeChannel(guild_id=999, name="woanders")

    def get_channel(self, cid):
        return {555: self.home, 556: self.foreign}.get(int(cid))

    async def fetch_channel(self, cid):
        raise RuntimeError("not found")


async def run_endpoint():
    print("\nThe send endpoint")

    import aiohttp
    import shutil

    # The builder is copied into the image at build time; do the same
    # here so the import resolves.
    builder_src = os.path.join(BOT, "utils", "message_builder.py")
    builder_dst = os.path.join(STATUS, "message_builder.py")
    copied = False
    if not os.path.exists(builder_dst):
        shutil.copy(builder_src, builder_dst)
        copied = True

    os.environ["DASHBOARD_API_KEY"] = "geheim123"
    os.environ["PORT"] = "8096"

    import importlib
    import status_bot as sb
    importlib.reload(sb)

    bot = FakeBot()
    await sb.start_web(bot)

    base = "http://127.0.0.1:8096"
    try:
        async with aiohttp.ClientSession() as session:
            async def post(payload, key="geheim123"):
                headers = {"X-API-Key": key} if key else {}
                async with session.post(f"{base}/send", json=payload,
                                        headers=headers) as response:
                    return response.status, await response.json()

            status, body = await post({"channel_id": "555"}, key="falsch")
            check("a wrong key is refused", status == 401, str(body))

            status, body = await post({"channel_id": "555"}, key=None)
            check("no key at all is refused", status == 401, str(body))

            status, body = await post({})
            check("a missing channel is refused", status == 400, str(body))

            # The important one: this endpoint posts as a bot with no
            # per-guild permission model behind it.
            status, body = await post({
                "channel_id": "556", "kind": "text", "content": "hallo",
            })
            check("posting to another guild is refused", status == 403,
                  "otherwise this is a way to post anywhere the bot is")

            status, body = await post({"channel_id": "111", "kind": "text",
                                       "content": "hallo"})
            check("an unknown channel gives a clear 404", status == 404,
                  str(body))

            status, body = await post({
                "channel_id": "555", "kind": "text", "content": "Hallo Welt",
            })
            check("a valid message goes out", status == 200, str(body))
            check("and really reached the channel", len(bot.home.sent) == 1)
            check("mentions are off unless asked for",
                  bot.home.sent[0].get("allowed_mentions") is not None,
                  "a changelog pinging @everyone by accident is a bad day")

            async with session.get(f"{base}/health") as response:
                status, body = response.status, await response.json()
            check("the service reports its own health", status == 200,
                  str(body))
            check("and what it is watching", "main_state" in body, str(body))
    finally:
        if copied:
            os.remove(builder_dst)


# ══════════════════════════════════════════════════════════════════════
#  Deployment
# ══════════════════════════════════════════════════════════════════════


def test_status_command():
    """
    !status and /status, from anywhere, panel always in the one channel.

    Two commands rather than one because !status needs the Message
    Content intent, which is a switch in the developer portal. Discord
    refuses the login outright when a bot asks for a privileged intent
    it was not granted -- so the text command is off unless STATUS_PREFIX
    is set, and /status is always there as the one that cannot fail that
    way.
    """
    print("\nThe status command")

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()

    check("there is a slash command", 'name="status"' in source)
    check("it is registered to the home guild, not globally",
          "copy_global_to(guild=guild)" in source,
          "a global command can take an hour to appear")
    check("the reply is only shown to whoever asked",
          "ephemeral=True" in source,
          "the panel goes to the channel; the receipt does not belong there")

    check("there is a text command too", "async def on_message" in source)
    check("the prefix comes from the environment",
          'os.getenv("STATUS_PREFIX")' in source)
    check("message_content is only requested when the prefix is used",
          "if PREFIX_COMMAND_ENABLED:\n            intents.message_content = True" in source,
          "asking for a privileged intent that is switched off in the "
          "portal makes Discord refuse the login entirely")
    check("the text command is off by default",
          'PREFIX = (os.getenv("STATUS_PREFIX") or "").strip()' in source
          and "PREFIX_COMMAND_ENABLED = bool(PREFIX)" in source)

    # The actual requirement: it does not matter where you type it.
    check("both commands share one implementation",
          source.count("await self.refresh_panel()") == 2,
          "two copies would drift")
    check("the panel always goes to the configured channel",
          "self.get_channel(STATUS_CHANNEL_ID)" in source.split(
              "async def refresh_panel")[1][:900],
          "it must not post where the command was typed")

    # Other servers must not be able to drive this bot.
    guard = source.split("async def on_message")[1][:600]
    check("a command on another guild is ignored",
          "message.guild.id != HOME_GUILD_ID" in guard)
    check("and so are other bots", "message.author.bot" in guard)

    # Reposting rather than editing: asking to see the status and having
    # it quietly change three thousand messages up the channel is not
    # what anybody means.
    body = source.split("async def refresh_panel")[1][:2200]
    check("the panel is reposted at the bottom",
          "self.message = None" in body and "await self.publish()" in body)
    check("and the old one is removed",
          "old_message.delete()" in body,
          "otherwise every call leaves another dead panel behind")


def test_deployment():
    print("\nHow it is deployed")

    dockerfile = os.path.join(STATUS, "Dockerfile")
    check("the status bot has its own Dockerfile", os.path.exists(dockerfile))
    if not os.path.exists(dockerfile):
        return
    src = open(dockerfile, encoding="utf-8").read()

    check("it starts the status bot",
          "statusbot/status_bot.py" in src)
    # Railway rejects the build outright with this instruction.
    check("no docker VOLUME instruction", "\nVOLUME " not in src)
    check("the message builder is shared, not copied into the repo twice",
          "bot/utils/message_builder.py" in src,
          "two copies drift apart and the same changelog renders "
          "differently depending on which bot sent it")

    reqs = open(os.path.join(STATUS, "requirements.txt"), encoding="utf-8").read()
    check("it depends on discord.py", "discord.py" in reqs)
    check("and stays small", len([
        line for line in reqs.splitlines()
        if line.strip() and not line.startswith("#")
    ]) <= 4, "the service that must stay up should carry little")

    # railway.toml applies to every service built from this repo. If it
    # pins dockerfilePath, the status service silently builds the main
    # bot's image instead -- two copies of the main bot, both logging in
    # with the same token, kicking each other off Discord. Nothing in
    # the logs would say "wrong Dockerfile".
    toml_path = os.path.join(ROOT, "railway.toml")
    if os.path.exists(toml_path):
        toml = open(toml_path, encoding="utf-8").read()
        active = [
            line for line in toml.splitlines()
            if line.strip().startswith("dockerfilePath")
        ]
        check("railway.toml does not pin one Dockerfile for every service",
              not active,
              "each service must set its own path in Settings -> Build")

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    check("it explains why it is a separate service",
          "separate Railway service" in source or "separate service" in source,
          "the next person will otherwise merge it into the main container")
    check("an unconfigured service exits quietly instead of crash-looping",
          "return 0" in source.split("STATUS_BOT_TOKEN is not set")[1][:400],
          "burning restarts on a missing token helps nobody")
    check("it asks for no intents it does not need",
          "discord.Intents.none()" in source,
          "a bot that only posts needs nothing else")


def test_dashboard_can_choose():
    """
    The dashboard offers the status bot as a sender, but only where it
    exists.

    The point of the option: "the bot is down" cannot be announced by
    the bot that is down. The point of the scoping: the status bot has
    no per-guild permission model behind it, so it must not become a
    way to post anywhere.
    """
    print("\nChoosing the sender")

    compose = open(os.path.join(BOT, "api/routes/compose.py"),
                   encoding="utf-8").read()

    check("there is an endpoint listing the senders",
          '/senders' in compose)
    check("the status bot is only offered on the support guild",
          "guild_id == HOME_GUILD_ID and _status_bot_url()" in compose)
    check("and only when its URL is configured",
          "_status_bot_url()" in compose)
    check("sending through it is refused elsewhere",
          "Der Status-Bot postet nur im Support-Server." in compose)
    check("an unreachable status bot is named as such",
          "Der Status-Bot antwortet nicht" in compose,
          "a generic failure would send somebody hunting in the wrong place")
    check("an unknown sender falls back to the main bot",
          'data.get("sender") or "main"' in compose)

    panel = open(os.path.join(
        os.path.dirname(BOT), "dashboard/components/dashboard/compose-panel.tsx"
    ), encoding="utf-8").read()
    check("the picker is hidden when there is only one option",
          "senders.length > 1 &&" in panel,
          "a choice of one is noise")
    check("the choice is sent along", "sender," in panel)


def main():
    check("the statusbot folder exists", os.path.isdir(STATUS), STATUS)
    if not os.path.isdir(STATUS):
        return 1

    test_layout()
    asyncio.run(run_checks())
    test_links_and_partner()
    test_partner_ping_range()
    test_discord_markup()
    test_avatars()
    test_emojis()
    test_no_name_clashes_with_discord()
    test_one_miss_is_not_an_outage()
    asyncio.run(run_endpoint())
    test_status_command()
    test_deployment()
    test_dashboard_can_choose()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
