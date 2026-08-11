#!/usr/bin/env python3
"""
Music commands when Lavalink is down.

From the Railway log:

    [ERROR] Unhandled error in 'play' (guild ..., user ...):
    InvalidNodeException: No nodes are currently assigned to the
    wavelink.Pool in a CONNECTED state.

The public Lavalink host was answering 429, so no node ever reached
CONNECTED. Every music command then died as an unhandled traceback and
the user in the channel got nothing at all -- no reply, no error, just
silence.

The fix cannot be a try/except around the command body: wavelink
resolves the node inside `Player.__init__`, so
`channel.connect(cls=wavelink.Player)` raises before any of the cog's
code runs. It has to be checked before connecting, which is what
`Music.music_ready()` and `Music.require_music()` do.

Run:  python3 tests/test_music_node.py
"""

import ast
import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

MUSIC = os.path.join(BOT, "cogs", "commands", "music.py")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def source() -> str:
    return open(MUSIC, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Drop comments and docstrings before matching.

    The guard's own docstring names the exception and quotes the call it
    protects, so a raw search finds those and passes even with the guard
    deleted.
    """
    out = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    return re.sub(r'"""(?:.|\n)*?"""', "", out)


def test_reproduces():
    print("\nThe crash itself")
    import wavelink

    raised = None
    try:
        wavelink.Pool.get_node()
    except Exception as exc:
        raised = exc

    check("wavelink raises with no node connected", raised is not None,
          "the premise of this test no longer holds")
    check("and it is the exception from the log",
          type(raised).__name__ == "InvalidNodeException",
          f"got {type(raised).__name__}")


def test_guard():
    print("\nThe guard")
    from cogs.commands.music import Music

    check("music_ready exists", hasattr(Music, "music_ready"))
    check("it reports not-ready with no node",
          Music.music_ready() is False,
          "commands would go on to connect and crash")

    sent = []

    class Ctx:
        async def send(self, *args, **kwargs):
            sent.append(kwargs.get("view") or (args[0] if args else None))

    cog = Music.__new__(Music)  # __init__ wants a live bot
    allowed = asyncio.run(cog.require_music(Ctx()))

    check("require_music refuses", allowed is False)
    check("and the user is told why", len(sent) == 1 and sent[0] is not None,
          "silence in the channel is what the bug looked like")


def test_every_connect_is_guarded():
    """
    Every `connect(cls=wavelink.Player)` must be preceded by a check.

    Counting them is the point: a new music command that connects
    without asking is the exact bug this file exists for, and it would
    otherwise only show up in production.
    """
    print("\nEvery connect is guarded")
    src = strip_comments(source())
    tree = ast.parse(source())

    connects = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "connect":
            continue
        kw = {k.arg for k in node.keywords if k.arg}
        if "cls" in kw:
            connects.append(node.lineno)

    check("the connect calls were found", len(connects) >= 3,
          f"found {len(connects)}, expected the three player connects")

    # Die Pruefung muss irgendwo in derselben Funktion VOR dem Aufruf
    # stehen -- ein festes Fenster von 25 Zeilen ist zu eng, sobald vor
    # dem Verbinden noch etwas anderes passiert (Rechte, alte
    # Verbindung). Die Frage ist ohnehin eine andere: kann dieser
    # Aufruf ohne Node ausgefuehrt werden?
    lines = source().split("\n")
    funktionen = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def enclosing(lineno):
        treffer = [
            f for f in funktionen
            if f.lineno <= lineno <= (f.end_lineno or f.lineno)
        ]
        return min(treffer, key=lambda f: (f.end_lineno or f.lineno) - f.lineno) \
            if treffer else None

    unguarded = []
    for lineno in connects:
        funktion = enclosing(lineno)
        start = (funktion.lineno - 1) if funktion else max(0, lineno - 25)
        window = "\n".join(lines[start:lineno])
        if "require_music" not in window and "music_ready" not in window:
            unguarded.append(lineno)

    check("none of them connects unchecked", not unguarded,
          f"lines {unguarded} would raise InvalidNodeException")

    # The search command opens a picker; without a node every choice in
    # it fails, so it is refused up front rather than after two clicks.
    check("the search command checks too",
          "require_music" in src.split("async def search2")[1][:600]
          if "async def search2" in src else False,
          "the platform picker would lead nowhere")


def test_connect_log_is_honest():
    print("\nThe startup log")
    src = strip_comments(source())

    # Pool.connect() returns once the handshake is handed off; the
    # websocket is still coming up. Printing "connected" right after it
    # is why the log said connected and then logged 429s from the same
    # node in the next second.
    after = src.split("Pool.connect(")[1] if "Pool.connect(" in src else ""
    immediate = after[:200]
    check("it does not claim success straight after Pool.connect",
          "node connected" not in immediate,
          "the log said connected while the node was still failing")

    # Not just "music_ready appears somewhere": the success line has to
    # be *inside* that check. A mutation that replaced the poll with
    # `if True:` left the call elsewhere in the file and passed.
    guarded = re.search(
        r"if\s+self\.music_ready\(\)\s*:\s*\n\s*print\([^\n]*node connected",
        src,
    )
    check("the success line is behind that check",
          guarded is not None,
          "success is announced without confirming the node is up")
    check("and says so when it does not",
          "not reachable" in src,
          "a silent failure leaves nobody knowing music is off")


def test_retry_spam_is_quietened():
    """
    wavelink retries a 429 host forever, three log lines per attempt.

    In one 2.5-minute Railway log that was 33 lines of the same thing.
    The info line among them only shows up because three cogs call
    `logging.basicConfig(level=logging.INFO)`, and basicConfig
    configures the *root* logger -- so one cog turns on INFO for every
    library in the process.
    """
    print("\nThe retry spam")
    import logging
    from utils.bootstrap import NOISY_LOGGERS, quieten_libraries

    for name in ("wavelink", "wavelink.websocket", "httpx"):
        check(f"{name} is on the quiet list", name in NOISY_LOGGERS)

    # Called from run(), which executes on import -- so it has to be
    # wired in, not merely available. Calling it here first would mask
    # exactly that: the check passed with the call deleted from run().
    boot_src = strip_comments(
        open(os.path.join(BOT, "utils", "bootstrap.py"), encoding="utf-8").read()
    )
    run_body = boot_src.split("def run()")[1] if "def run()" in boot_src else ""
    check("start-up actually calls it",
          "quieten_libraries()" in run_body,
          "the levels would never be applied in production")

    quieten_libraries()
    level = logging.getLogger("wavelink.websocket").level
    check("wavelink is raised to ERROR", level == logging.ERROR,
          f"got {logging.getLevelName(level)}")

    # A named logger's own level is not touched by basicConfig, which
    # only configures the root -- but the cogs run after bootstrap, so
    # this has to be true rather than assumed.
    logging.basicConfig(level=logging.INFO)
    after = logging.getLogger("wavelink.websocket").level
    check("and survives a later basicConfig(INFO)", after == logging.ERROR,
          f"a cog's basicConfig reset it to {logging.getLevelName(after)}")

    # Quiet, not silent: a real failure still has to reach the log.
    ws = logging.getLogger("wavelink.websocket")
    check("routine retries are dropped", not ws.isEnabledFor(logging.INFO))
    check("so is the 429 warning", not ws.isEnabledFor(logging.WARNING))
    check("but genuine errors get through", ws.isEnabledFor(logging.ERROR),
          "silencing everything would hide a real outage")

    # httpx narrates the dashboard calling itself, one line per request,
    # directly beside our own request log saying the same thing.
    check("httpx is quietened too",
          not logging.getLogger("httpx").isEnabledFor(logging.INFO),
          "every internal HTTP call would be logged twice")

    src = strip_comments(source())
    check("music re-applies it when connecting",
          "quieten_libraries()" in src,
          "a stray basicConfig during start-up would resurrect the spam")


def test_no_double_retry_loop():
    """
    We must not wrap wavelink's own retry in a second one.

    Pool.connect() awaits node._connect(), and the websocket underneath
    reconnects forever on its own. On a host that refuses the handshake
    that await never returns -- so a `while ...: connect(); sleep(30)`
    loop is parked in its first iteration for good. Its "Retrying in 30
    seconds..." line showed up exactly once in the Railway log and never
    again, which is what gave it away.
    """
    print("\nNo retry loop around wavelink's own")
    src = strip_comments(source())
    body = src.split("async def connect_nodes")[1].split("@staticmethod")[0]

    check("the connect is kicked off in the background",
          "asyncio.create_task(" in body,
          "awaiting it directly blocks forever on a dead host")
    check("there is no while loop around it",
          "while " not in body,
          "a loop here can never reach its second iteration")
    check("nothing sleeps 30s pretending to retry",
          "sleep(30)" not in body,
          "that message never fires twice, so it is a lie")
    # asyncio only keeps a weak reference to a task; dropping it lets the
    # connection be collected mid-flight.
    check("the task is kept referenced",
          "self._lavalink_task" in body,
          "a fire-and-forget task can be garbage-collected")
    check("it still reports the outcome once",
          "No Lavalink node reachable" in body and "node connected" in body)


def test_guild_log_channel_is_configurable():
    """
    The join/leave log used a hard-coded channel that no longer exists.

    From the log: "Channel with ID 1396794297386532978 not found." --
    logged at ERROR on every join and every leave, and the message
    dropped, while `guild_log_channel` sat in the dashboard unused.
    university_bot.py already reads that setting for the same event.
    """
    print("\nThe guild join/leave log")
    path = os.path.join(BOT, "cogs", "events", "on_guild.py")
    src = strip_comments(open(path, encoding="utf-8").read())

    check("the dead hard-coded id is gone",
          "1396794297386532978" not in src,
          "it points at a channel that no longer exists")
    check("the dashboard setting is used instead",
          'bot_settings.get_int("guild_log_channel")' in src)
    # An unset log channel is a normal configuration, not a fault.
    check("a missing channel is not an error",
          "logging.error" not in src.split("_guild_log_channel")[0]
          or "not found" not in src,
          "this fired at ERROR on every single join")

    import asyncio as _asyncio
    from cogs.events.on_guild import _guild_log_channel
    from utils import bot_settings

    class Client:
        def __init__(self, found):
            self.found = found

        def get_channel(self, cid):
            return f"<channel {cid}>" if self.found else None

    async def scenarios():
        unset = _guild_log_channel(Client(True))
        await bot_settings.set_values({"guild_log_channel": "1234567890123456789"})
        present = _guild_log_channel(Client(True))
        deleted = _guild_log_channel(Client(False))
        await bot_settings.set_values({"guild_log_channel": ""})
        return unset, present, deleted

    unset, present, deleted = _asyncio.run(scenarios())
    check("unset means no channel", unset is None)
    check("a configured channel is found", present is not None,
          "the setting is read but ignored")
    check("a deleted channel is handled", deleted is None,
          "it would raise on send()")


def test_dead_defaults_are_gone():
    """
    The two hosts the bot shipped with are both dead.

        lava-v4.ajieblogs.eu.org   404, the vhost is gone
        lavalink.jirayu.net:13592  500, "dial tcp 38.49.216.39:2334:
                                   connection refused" -- a proxy whose
                                   backend is down. The 429 wavelink
                                   logged forever was that same outage
                                   on the websocket route.

    So "the music server is not reachable" was true on every /play. No
    guard fixes that; the host has to be one that answers.
    """
    print("\nThe Lavalink hosts")
    src = strip_comments(source())

    for dead in ("ajieblogs", "jirayu"):
        check(f"{dead} is no longer a default", dead not in src,
              "this host does not answer")

    check("there is more than one candidate",
          src.count("serenetia") >= 2,
          "a single host means a single point of failure again")
    check("the environment variable still wins",
          'os.getenv("LAVALINK_HOST"' in src,
          "your own node must take precedence over the public ones")
    # A fire-and-forget task can be collected mid-connection.
    check("each attempt is kept referenced",
          "self._lavalink_tasks.append(task)" in src)
    check("the list is initialised",
          "_lavalink_tasks: list[asyncio.Task] = []" in src,
          "AttributeError on the first connection attempt")
    # Waiting the full window on a dead host means never reaching the
    # next candidate.
    check("a dead candidate is abandoned",
          "trying the next one" in src,
          "one unreachable host would block the rest")


def test_rate_limit_is_reported():
    """
    The public nodes allow a handful of searches, then answer 429.

    Measured: four searches, then 429 on the first host; fewer on the
    second. That used to surface as "No results found.", which sends
    people hunting for a better search term when the answer is "wait a
    few seconds".
    """
    print("\nA rate-limited search")
    src = strip_comments(source())

    check("there is a distinct exception for it",
          "class RateLimited" in src)
    check("a 429 is recognised",
          '"429" in str(exc)' in src,
          "wavelink puts the status in the message, not the type")
    # Not just "the raise appears": it has to be reachable. A mutation
    # that changed the guard to `if False:` left the line in place and
    # passed this check.
    raised = re.search(
        r"if\s+throttled\s*:\s*\n\s*raise\s+Music\.RateLimited\(\)", src
    )
    check("it is raised rather than swallowed",
          raised is not None,
          "the raise is present but unreachable")
    check("and handled separately from other failures",
          "except Music.RateLimited:" in src,
          "it would fall through to the generic error text")
    check("the user is told to wait, not to search differently",
          "busy right now" in src,
          '"No results found." is the wrong answer to a 429')

    # It must not be mistaken for an empty result.
    from cogs.commands.music import Music
    check("it is a real exception type",
          issubclass(Music.RateLimited, Exception))


def main():
    test_reproduces()
    test_dead_defaults_are_gone()
    test_rate_limit_is_reported()
    test_guard()
    test_every_connect_is_guarded()
    test_connect_log_is_honest()
    test_retry_spam_is_quietened()
    test_no_double_retry_loop()
    test_guild_log_channel_is_configurable()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
