#!/usr/bin/env python3
"""
Load every cog without connecting to Discord.

A cog that fails to import is invisible to the test suite -- nothing
imports all 145 of them -- but fatal at start-up. This is the check that
catches a hand edit breaking a file no test happens to touch.

Run from the bot/ directory:

    python ../.github/scripts/boot_test.py

Exits non-zero when anything fails to load, or when the number of cogs
drops sharply. The version this replaces printed its failures and then
called os._exit(0) unconditionally, so a broken cog was reported and
the run still passed -- fine when a human reads the output, useless in
CI, which only looks at the exit code.
"""

import asyncio
import os
import sys
import warnings

sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

# The bot refuses to construct itself without one. Never used: nothing
# here logs in.
os.environ.setdefault("TOKEN", "x")

# A floor rather than an exact number, so adding a cog does not fail the
# build, but losing a pile of them does. Whole categories have gone
# missing before -- an import error early in cogs/__init__.py takes
# everything after it with it, and the count is the only thing that
# notices.
MINIMUM_COGS = 130


async def main() -> int:
    from core.universitybot import extensions, universitybot

    bot = universitybot()
    failed: list[tuple[str, str]] = []

    for extension in extensions:
        try:
            await bot.load_extension(extension)
        except Exception as err:  # noqa: BLE001 - report, do not raise
            failed.append((extension, repr(err)))

    cogs = len(bot.cogs)
    prefix_commands = len(list(bot.walk_commands()))
    app_commands = len(bot.tree.get_commands())

    print(f"RESULT_COGS {cogs}")
    print(f"RESULT_PREFIX_CMDS {prefix_commands}")
    print(f"RESULT_APP_CMDS {app_commands}")
    print(f"RESULT_FAILED {len(failed)}")

    for extension, error in failed:
        print(f"FAIL {extension} {error[:400]}")

    problems = []
    if failed:
        problems.append(f"{len(failed)} extension(s) failed to load")
    if cogs < MINIMUM_COGS:
        problems.append(
            f"only {cogs} cogs loaded, expected at least {MINIMUM_COGS} — "
            "an import error early in cogs/__init__.py silently drops "
            "everything after it"
        )

    if problems:
        print()
        for problem in problems:
            print(f"error: {problem}")
        return 1

    print(f"\nok: {cogs} cogs, {prefix_commands} prefix commands, "
          f"{app_commands} app commands")
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    # os._exit rather than sys.exit: discord.py leaves an aiohttp
    # connector and a few tasks behind when a bot is built but never
    # started, and their teardown can hang for a while. The result is
    # already known at this point.
    sys.stdout.flush()
    os._exit(code)
