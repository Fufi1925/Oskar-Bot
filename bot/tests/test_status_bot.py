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
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return "\n".join(found)


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
    Buttons, and the rule that runs through the whole panel: never show
    a number that was not measured.

    A status page that lies is worth less than no status page. The
    template bot is the case that forces the issue -- reading another
    bot's online status needs the Presences intent, which this service
    does not ask for, and without it Member.status is *always* offline.
    Printing that as a red dot would be wrong; printing a green "online,
    34 ms" would be worse.
    """
    print("\nLinks and the template bot")

    from view import StatusView

    # Buttons only appear when configured.
    empty = StatusView(brand="B", state="online", health=FakeHealth(),
                       since=time.time())
    check("no buttons when nothing is configured", buttons(empty) == [],
          "a button that goes nowhere is worse than no button")

    full = StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        website="https://example.com", invite="https://example.com/invite",
        support="https://discord.gg/abc",
    )
    labels = [label for label, _ in buttons(full)]
    check("the dashboard link becomes a button", "Dashboard" in labels, str(labels))
    check("the invite link becomes a button", "Einladen" in labels, str(labels))
    check("the support link becomes a button", "Support" in labels, str(labels))

    partial = StatusView(brand="B", state="online", health=FakeHealth(),
                         since=time.time(), website="https://example.com")
    check("only the configured ones show up", len(buttons(partial)) == 1,
          str(buttons(partial)))

    # The template bot row.
    without = render(StatusView(brand="B", state="online",
                                health=FakeHealth(), since=time.time()))
    check("no template row when it could not be checked",
          "Template" not in without,
          "an unknown row invented is the thing being avoided")

    honest = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        partner={"ok": True, "label": "University Template",
                 "detail": "auf dem Server · Online-Status nicht abrufbar"},
    ))
    check("the template row says what was actually checked",
          "Online-Status nicht abrufbar" in honest, honest[-200:])
    check("and does not claim it is online",
          "🟢 **University Template**\n-# online" not in honest)

    missing = render(StatusView(
        brand="B", state="online", health=FakeHealth(), since=time.time(),
        partner={"ok": False, "label": "Template-Bot",
                 "detail": "nicht auf dem Server"},
    ))
    check("a missing template bot is marked red",
          "🔴 **Template-Bot**" in missing, missing[-200:])

    # Nothing unmeasured may be drawn as a fact.
    down = render(StatusView(
        brand="B", state="down",
        health=FakeHealth(reachable=False, error="Zeitüberschreitung",
                          code=None, latency=None),
        since=time.time(),
    ))
    check("an unreachable bot shows no latency at all",
          "ms" not in down.split("Zuletzt")[0],
          "inventing a ping for something we could not reach is the "
          "exact failure this rule exists for")
    check("and marks the rest as not checked",
          down.count("⚪") >= 2 and "nicht geprüft" in down, down[:200])

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()
    # Only an assignment counts as requesting it. Reading
    # self.intents.presences to decide what to display is fine and is
    # checked for separately below -- an earlier version of this check
    # matched both and failed on the reading.
    check("the presences intent is not requested",
          "intents.presences = True" not in source,
          "asking for a privileged intent that is off makes Discord "
          "refuse the login")
    check("but a real status is used if it happens to be available",
          "self.intents.presences" in source,
          "if somebody turns it on later, show the real value")
    check("the partner check fails soft",
          "return None" in source.split("async def check_partner")[1][:2000],
          "one unreadable row must not blank the panel")

    # The wording itself, not just the view. Checking only the view let
    # a mutation through that had check_partner return a flat "online"
    # without the intent -- exactly the invented status this is about.
    body = source.split("async def check_partner")[1].split("def build_view")[0]
    # Everything after the presences branch closes. Splitting on the
    # `if` alone kept the branch itself in the slice, where the word
    # "online" is legitimate -- and the check then failed on correct
    # code, which is how this was caught.
    after_branch = body.split("if self.intents.presences:")[1]
    fallback = after_branch.split("}\n", 1)[1] if "}\n" in after_branch else after_branch

    check("without the intent it does not say plain 'online'",
          '"detail": "online"' not in fallback,
          "claiming a status that was never read is the failure mode "
          "this whole rule exists for")
    check("it says what it actually checked instead",
          "auf dem Server" in fallback and "nicht abrufbar" in fallback,
          fallback[-200:])


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
