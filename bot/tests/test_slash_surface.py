#!/usr/bin/env python3
"""
Which commands appear in the slash menu.

The bot exposed 142 slash commands. Discord's cap is 100 global ones, so
a chunk of them could never be registered anyway, and the menu was full
of things nobody on a German university server would type.

Eleven were moved to prefix-only. This file pins that decision down in
both directions:

  * they are gone from the slash tree
  * they still exist as prefix commands, because "removed from the
    slash menu" must not quietly mean "deleted"

Two of them were not merely unused but broken as slash commands:

  * /disconnect was the only music command in the tree. You could stop
    playback but there was no /play to start it — the other 16 music
    commands are prefix-only.
  * /steal is normally used by replying to a message. A slash command
    has no reply to read (ctx.message.reference is None), so that half
    of it silently did nothing.

Also guarded here: /report used to send to a hardcoded channel id the
bot has no access to (Discord answers 50001), so get_channel returned
None and the very next line raised AttributeError. Every report was
lost and the reporter saw nothing.

    python3 tests/test_slash_surface.py
"""

import asyncio
import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)
os.chdir(BOT)
warnings.filterwarnings("ignore")
os.environ.setdefault("TOKEN", "x")

# Deliberately prefix-only. Kept as a list so the intent is reviewable.
PREFIX_ONLY = [
    "hinglish",
    "urban",
    "disconnect",
    "steal",
    "2048",
    "lights-out",
    "number-slider",
]

# Subcommands of the /list group that were dropped from the tree.
LIST_PREFIX_ONLY = ["early", "activedeveloper", "createdat", "joinedat"]

# Explicitly kept, so a future cleanup cannot quietly take them along.
MUST_STAY = [
    "report", "nuke", "unbanall",
    "chess", "tic-tac-toe", "connectfour", "battleship", "rps",
    "wordle", "memory-game",
]
LIST_MUST_STAY = ["bots", "emojis", "roles"]

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


async def collect():
    from core.universitybot import extensions, universitybot
    from discord import app_commands

    bot = universitybot()
    for extension in extensions:
        try:
            await bot.load_extension(extension)
        except Exception:
            pass

    slash = set()

    def walk(cmd, parent=""):
        full = f"{parent} {cmd.name}".strip()
        if isinstance(cmd, app_commands.Group):
            for child in cmd.commands:
                walk(child, full)
        else:
            slash.add(full)

    for cmd in bot.tree.get_commands():
        walk(cmd)

    prefix = {c.qualified_name for c in bot.walk_commands()}
    return slash, prefix


def main() -> int:
    slash, prefix = asyncio.run(collect())

    print(f"slash commands: {len(slash)}   prefix commands: {len(prefix)}")
    check("the slash menu shrank below the old 142", len(slash) < 142, str(len(slash)))

    print("\nDropped from the slash menu")
    for name in PREFIX_ONLY:
        check(f"/{name} is gone", name not in slash)
    for name in LIST_PREFIX_ONLY:
        check(f"/list {name} is gone", f"list {name}" not in slash)

    print("\nStill usable with a prefix — nothing was deleted")
    for name in PREFIX_ONLY:
        check(f"!{name} still exists", name in prefix)
    for name in LIST_PREFIX_ONLY:
        check(f"!list {name} still exists", f"list {name}" in prefix)

    print("\nKept on purpose")
    for name in MUST_STAY:
        check(f"/{name} is still there", name in slash)
    for name in LIST_MUST_STAY:
        check(f"/list {name} is still there", f"list {name}" in slash)

    print("\n/report no longer targets a dead hardcoded channel")
    source = open(os.path.join(BOT, "cogs", "commands", "extra.py"), encoding="utf-8").read()
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    check(
        "the hardcoded channel id is gone",
        "1396813063642153030" not in body,
        "the unreachable channel is still wired up",
    )
    check(
        "it reads the configurable channel instead",
        'bot_settings.get_int("report_channel")' in body,
    )
    check(
        "a missing channel is handled instead of crashing",
        "if channel is None:" in body,
        "channel.send would raise AttributeError again",
    )

    from utils import bot_settings

    check(
        "the setting exists so it can be configured",
        any(s.key == "report_channel" for s in bot_settings.SETTINGS),
    )

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("All slash surface checks passed.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # os._exit rather than sys.exit: loading every cog starts background
    # tasks and an aiohttp session that never get closed, and the
    # interpreter waits on them for minutes at shutdown. boot_test.py
    # does the same thing for the same reason.
    os._exit(code)
