# ╔══════════════════════════════════════════════════════════════════╗
# ║   Opening a database file, safely                                ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
One place that opens an SQLite file for a cog.

Why this exists: `aiosqlite.connect("db/foo.db")` raises
`OperationalError: unable to open database file` when the `db/` folder
does not exist — which is the case on a fresh container, before anything
else has run. Several cogs then caught the error, logged nothing useful,
and carried on with `self.connection = None`, so every feature that
depended on them silently did nothing: settings saved fine in the
dashboard and the bot never reacted.

The older cogs each did their own `os.makedirs(...)` at the top; the
newer ones did not, which is exactly how the gap appeared.
"""

from __future__ import annotations

import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)


async def connect(path: str) -> aiosqlite.Connection:
    """
    Open `path`, creating the folder around it first.

    Deliberately does not swallow errors: a cog that cannot reach its
    database must fail loudly at load time, where the message ends up in
    the startup log, rather than pretending to work for weeks.
    """
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    return await aiosqlite.connect(path)


async def connect_or_none(path: str, *, owner: str = "") -> aiosqlite.Connection | None:
    """
    Same, but returns None instead of raising.

    For the few callers that genuinely can continue without the database.
    Logs loudly so the failure is at least findable.
    """
    try:
        return await connect(path)
    except Exception as exc:
        logger.error(
            f"{owner or path}: could not open {path} ({type(exc).__name__}: {exc}). "
            "This feature will not work until that is fixed."
        )
        return None
