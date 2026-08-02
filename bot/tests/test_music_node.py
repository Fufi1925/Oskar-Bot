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

    lines = source().split("\n")
    unguarded = []
    for lineno in connects:
        # Look back over the enclosing block for a guard.
        window = "\n".join(lines[max(0, lineno - 25):lineno])
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
    check("it waits for the node to actually come up",
          "music_ready()" in after[:900],
          "nothing verifies the node before reporting success")
    check("and says so when it does not",
          "did not come up" in src,
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


def main():
    test_reproduces()
    test_guard()
    test_every_connect_is_guarded()
    test_connect_log_is_honest()
    test_retry_spam_is_quietened()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
