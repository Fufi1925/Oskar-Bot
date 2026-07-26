"""
Safe SQLite access.

Railway's filesystem is ephemeral: `db/` disappears on every redeploy, and it
is recreated by `utils/bootstrap.py` at startup. But anything that opens a
database *after* that point — or in a container where the directory was wiped
while the process was running — hit:

    sqlite3.OperationalError: unable to open database file

which surfaced in the dashboard as a bare "Internal Server Error" with no clue
what went wrong.

`connect()` here is a drop-in replacement for `aiosqlite.connect()` that makes
sure the parent directory exists first. Every write path in the API uses it.
"""

from __future__ import annotations

import os

import aiosqlite


def ensure_parent(path: str) -> None:
    """Create the directory a database lives in, if it is missing."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def connect(path: str, **kwargs):
    """
    aiosqlite.connect() that cannot fail because the folder vanished.

    Returns the same awaitable context manager as aiosqlite, so it is used
    exactly like the original:

        async with db_paths.connect("db/foo.db") as db:
            ...
    """
    ensure_parent(path)
    return aiosqlite.connect(path, **kwargs)
