"""
Filesystem bootstrap.

The bot writes ~35 SQLite databases into ./db and a handful of JSON files into
./jsondb, but nothing ever created those directories. On a fresh container the
first `aiosqlite.connect("db/prefix.db")` therefore failed with
"unable to open database file" before the bot could even log in.

Importing this module (which happens at the very top of university_bot.py)
makes sure every path the code expects exists.
"""

from __future__ import annotations

import json
import logging
import os

# Libraries that are far too talkative at INFO.
#
# Three cogs call `logging.basicConfig(level=logging.INFO)`, and
# basicConfig configures the *root* logger -- so one cog turns on INFO
# for every library in the process. The Railway log was mostly two
# things nobody reads:
#
#   * wavelink retrying a Lavalink node that answers 429. Three lines
#     per attempt, forever: in one 2.5-minute log, 33 lines of it. Our
#     own one-line status message says whether music works.
#
#   * httpx narrating the dashboard's calls to itself --
#     "HTTP Request: GET http://127.0.0.1:3000/..." -- immediately
#     followed by our own request log line saying the same thing.
#
# ERROR rather than CRITICAL: a genuine failure still gets through.
NOISY_LOGGERS = (
    "wavelink",
    "wavelink.node",
    "wavelink.websocket",
    "httpx",
    "httpcore",
)


def quieten_libraries() -> None:
    """Raise the bar for libraries that log routine work at INFO."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)

# Directories that must exist before any cog touches the filesystem.
REQUIRED_DIRECTORIES = (
    "db",
    "jsondb",
    "instructions",
)

# Files that some modules read without checking whether they exist first.
# Value is the default content written when the file is missing.
REQUIRED_JSON_FILES = {
    "ignore.json": {"guilds": {}},
    "channels.json": {},
    "jsondb/joindm_messages.json": {},
}


def _base_dir() -> str:
    """Directory of the bot package (one level above utils/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_directories() -> list[str]:
    """Create every required directory. Returns the ones that were created."""
    created = []
    base = _base_dir()
    for name in REQUIRED_DIRECTORIES:
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
            created.append(name)
    return created


def ensure_json_files() -> list[str]:
    """Create missing JSON files with safe defaults. Returns the created ones."""
    created = []
    base = _base_dir()
    for name, default in REQUIRED_JSON_FILES.items():
        path = os.path.join(base, name)
        if os.path.exists(path):
            continue
        os.makedirs(os.path.dirname(path) or base, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(default, handle, indent=4, ensure_ascii=False)
            created.append(name)
        except OSError as exc:
            print(f"[bootstrap] Could not create {name}: {exc}")
    return created


def run() -> None:
    """Prepare the filesystem. Safe to call more than once."""
    # Before anything else: the cogs call basicConfig at import time, and
    # these levels have to survive that. setLevel on a named logger is
    # not touched by basicConfig, which only configures the root.
    quieten_libraries()

    directories = ensure_directories()
    files = ensure_json_files()
    if directories:
        print(f"[bootstrap] Created directories: {', '.join(directories)}")
    if files:
        print(f"[bootstrap] Created files: {', '.join(files)}")


# Run on import so that simply importing the module is enough.
run()
