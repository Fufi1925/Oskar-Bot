#!/usr/bin/env python3
"""
Cold start: a container where `db/` does not exist yet.

The bug this pins down: `aiosqlite.connect("db/foo.db")` raises
`OperationalError: unable to open database file` when the folder is
missing. A fresh deploy has no `db/` until something creates it, so the
newer cogs — which, unlike the older ones, had no `os.makedirs()` — came
up with `self.connection = None` and then quietly did nothing forever.

The symptom is the worst kind: the dashboard saves happily and returns
200, the settings really are written, and the bot simply never reacts.

Run:  python3 tests/test_cold_start.py
"""

import asyncio
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")


class MiniBot:
    """Just enough for cog_load()."""

    user = type("U", (), {"id": 1, "name": "Bot"})()
    guilds: list = []

    def get_cog(self, _name):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ── the raw failure this is all about ──────────────────────────
    import aiosqlite

    from utils import db_open

    async def raw_connect():
        # A folder no earlier check has created, since db_open below makes
        # db/ exist. aiosqlite is also lazy: connect() hands back an object
        # and only opens the file on first use, so the failure has to be
        # provoked with a query.
        try:
            connection = await aiosqlite.connect("no_such_dir/never.db")
            await connection.execute("SELECT 1")
            await connection.close()
            return None
        except Exception as exc:
            return type(exc).__name__

    error = asyncio.run(raw_connect())
    check("connecting without the folder really does fail",
          error == "OperationalError",
          f"got {error} — if this passes, the bug cannot happen here")

    async def helper_connect():
        connection = await db_open.connect("db/made_by_helper.db")
        await connection.close()
        return os.path.isfile("db/made_by_helper.db")

    check("db_open.connect creates the folder and the file",
          asyncio.run(helper_connect()))
    check("the folder exists afterwards", os.path.isdir("db"))

    # It must stay loud: a cog that cannot reach its database has to fail
    # at load, not pretend to work.
    async def helper_raises():
        try:
            await db_open.connect("/proc/nope/cannot.db")
            return False
        except Exception:
            return True

    check("a genuinely impossible path still raises", asyncio.run(helper_raises()))

    # ── every rewritten cog survives a cold start ──────────────────
    from cogs.commands.anonchat import AnonChat
    from cogs.commands.leveling import Leveling
    from cogs.commands.vanityroles import VanityRoles

    for cls in (AnonChat, VanityRoles, Leveling):
        cog = cls(MiniBot())
        try:
            asyncio.run(cog.cog_load())
            opened = cog.connection is not None
        except Exception as exc:
            opened = False
            check(f"{cls.__name__} loads on a cold start", False,
                  f"{type(exc).__name__}: {exc}")
            continue

        check(f"{cls.__name__} loads on a cold start", opened,
              "connection is None — the cog would silently do nothing")

        # aiosqlite is lazy, so merely holding a connection proves
        # nothing: the file is not touched until the first query. Run one.
        async def usable(connection):
            try:
                await connection.execute("SELECT 1")
                return True
            except Exception:
                return False

        check(f"{cls.__name__}'s connection actually works",
              cog.connection is not None and asyncio.run(usable(cog.connection)),
              "the file could not be opened — the cog would do nothing")

        try:
            asyncio.run(cog.cog_unload())
        except Exception:
            pass

    # ── the API's shared manager, same problem ─────────────────────
    from api.db_manager import DatabaseManager

    async def manager_cold():
        manager = DatabaseManager()
        connection = await manager.get_connection("db/sub/deep/manager.db")
        await manager.close_all()
        return connection is not None and os.path.isfile("db/sub/deep/manager.db")

    check("the API's connection manager creates nested folders too",
          asyncio.run(manager_cold()))

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        # Deliberately no db/ — that is the whole point.
        os.chdir(tmp)
        os.makedirs("jsondb", exist_ok=True)
        sys.exit(run())
