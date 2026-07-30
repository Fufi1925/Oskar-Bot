#!/usr/bin/env python3
"""
The command error handler (cogs/events/Errors.py).

Three real problems lived here:

  1. Unknown errors vanished. The handler tested twelve error types and
     then the function simply ended. A KeyError inside a command meant:
     nothing for the user, nothing in the Railway log, no stack trace.
     With 540 prefix commands that is flying blind.

  2. `NoPrivateMessage` and `MissingPermissions` are *subclasses* of
     `CheckFailure`, and the CheckFailure branch came first. In a DM
     `ctx.guild` is None, so `get_ignore_data(ctx.guild.id)` raised
     AttributeError inside the error handler itself. The nicely written
     "You can't use my commands in DMs." branch below was unreachable.

  3. The CheckFailure branch could fall through without replying and
     without returning, silently reaching the branches beneath it.

These tests drive the real cog with fake Context/Command objects. No
Discord connection.

    python3 tests/test_error_handler.py
"""

import asyncio
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)
os.chdir(BOT)

from discord.ext import commands  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


# ── Fakes ──────────────────────────────────────────────────────────────────
class FakeUser:
    def __init__(self, uid=1, bot=False):
        self.id = uid
        self.mention = f"<@{uid}>"
        self.avatar = None
        self.default_avatar = types.SimpleNamespace(url="https://example.invalid/a.png")
        self.display_avatar = types.SimpleNamespace(url="https://example.invalid/a.png")

    def __str__(self):
        return "tester#0001"


class FakeCommand:
    def __init__(self, name="ping"):
        self.name = name
        self.qualified_name = name
        self.aliases = []
        self.cog_name = "Testing"
        self.reset_called = False

    def reset_cooldown(self, ctx):
        self.reset_called = True


class FakeChannel:
    def __init__(self, cid=555):
        self.id = cid
        self.mention = f"<#{cid}>"


class FakeContext:
    """Records what the handler said instead of talking to Discord."""

    def __init__(self, guild=None):
        self.command = FakeCommand()
        self.author = FakeUser()
        self.channel = FakeChannel()
        self.guild = guild
        self.replies = []
        self.help_sent = False
        self.message = types.SimpleNamespace(content="!ping", jump_url="https://x.invalid/1")

    async def reply(self, content=None, *, embed=None, **kw):
        self.replies.append(embed.description if embed is not None else content)

    async def send(self, content=None, *, embed=None, **kw):
        self.replies.append(embed.description if embed is not None else content)

    async def send_help(self, *a, **kw):
        self.help_sent = True

    @property
    def said(self):
        return " ".join(str(r) for r in self.replies if r)


def load_cog():
    """Import the Errors cog with a client stub."""
    import importlib

    mod = importlib.import_module("cogs.events.Errors")
    importlib.reload(mod)
    client = types.SimpleNamespace(
        user=types.SimpleNamespace(display_avatar=types.SimpleNamespace(url="https://x.invalid/b.png")),
    )
    return mod.Errors(client)


def run(cog, ctx, error):
    """Call the handler; report an exception raised *by the handler*."""
    try:
        asyncio.run(cog.on_command_error(ctx, error))
        return None
    except Exception as exc:  # noqa: BLE001 - that is what we are measuring
        return exc


def main() -> int:
    cog = load_cog()

    print("A DM triggers the DM branch, not a crash")
    # NoPrivateMessage is a CheckFailure subclass and ctx.guild is None in a DM.
    ctx = FakeContext(guild=None)
    exc = run(cog, ctx, commands.NoPrivateMessage())
    check("handler does not raise on a DM", exc is None, f"raised {type(exc).__name__}: {exc}")
    check("user is told it was a DM", "DM" in ctx.said, f"said {ctx.said!r}")

    print("\nMissingPermissions still reaches its own branch")
    # Also a CheckFailure subclass; must not be swallowed by the ignore-list branch.
    ctx = FakeContext(guild=types.SimpleNamespace(id=42))
    exc = run(cog, ctx, commands.MissingPermissions(["manage_messages"]))
    check("handler does not raise", exc is None, f"raised {type(exc).__name__}: {exc}")
    check("user is told about the permission", "Permission" in ctx.said, f"said {ctx.said!r}")

    print("\nA plain CheckFailure in a DM does not crash the handler")
    # A custom check failing in a DM is a CheckFailure with no guild. Reading
    # the per-guild ignore list here is what used to blow up.
    ctx = FakeContext(guild=None)
    exc = run(cog, ctx, commands.CheckFailure("nope"))
    check("handler does not raise in a DM", exc is None, f"raised {type(exc).__name__}: {exc}")

    print("\nThe ignore list never hijacks a permission error")
    # The ignore-list branch must not swallow CheckFailure subclasses that have
    # their own branch. Pretend the author is on the ignore list: the user must
    # still be told about the missing permission, not about being ignored.
    import cogs.events.Errors as errmod

    async def fake_ignore(_guild_id):
        return {
            "channel": set(),
            "user": {str(FakeUser().id)},
            "command": set(),
            "bypassuser": set(),
        }

    real_ignore = errmod.get_ignore_data
    errmod.get_ignore_data = fake_ignore
    try:
        ctx = FakeContext(guild=types.SimpleNamespace(id=42))
        exc = run(cog, ctx, commands.MissingPermissions(["manage_messages"]))
        check("handler does not raise", exc is None, f"raised {type(exc).__name__}: {exc}")
        check(
            "permission error wins over the ignore list",
            "Permission" in ctx.said and "ignored user" not in ctx.said,
            f"said {ctx.said!r}",
        )
    finally:
        errmod.get_ignore_data = real_ignore

    print("\nAn unknown error is reported, not swallowed")
    ctx = FakeContext(guild=types.SimpleNamespace(id=42))
    boom = commands.CommandInvokeError(KeyError("missing_key"))
    exc = run(cog, ctx, boom)
    check("handler does not raise", exc is None, f"raised {type(exc).__name__}: {exc}")
    check("the user gets an answer", bool(ctx.said.strip()), "the command failed in total silence")

    print("\nA completely unhandled error type still answers")
    ctx = FakeContext(guild=types.SimpleNamespace(id=42))

    class WeirdError(commands.CommandError):
        pass

    exc = run(cog, ctx, WeirdError("something odd"))
    check("handler does not raise", exc is None, f"raised {type(exc).__name__}: {exc}")
    check("the user gets an answer", bool(ctx.said.strip()), "unknown error vanished silently")

    print("\nThe handler writes a traceback for unknown errors")
    src = open(os.path.join(BOT, "cogs", "events", "Errors.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    check("traceback is imported", "import traceback" in body, "no traceback import")
    check(
        "a fallback exists for unknown errors",
        "format_exception" in body or "print_exception" in body,
        "nothing prints a stack trace",
    )
    check(
        "CommandNotFound is still ignored",
        "CommandNotFound" in body,
        "unknown commands would now spam",
    )

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("All error handler checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
