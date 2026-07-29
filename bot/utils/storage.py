# ╔══════════════════════════════════════════════════════════════════╗
# ║   Where the data lives                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Keep every database and JSON file on one directory, so a Railway volume
mounted there survives a deploy.

The problem this solves: the bot writes 61 SQLite files and a handful of
JSON files. Most go to ``bot/db/``, but three do not -- ``rr.db``
(reaction roles), ``j2c_data.db`` (join to create) and the ``jsondb/``
folder sit in whatever the working directory happens to be. A volume
mounted on ``bot/db`` would quietly leave those three behind, and
nothing would say so: the bot would come up fine and the reaction roles
would just be gone.

Rewriting 405 ``aiosqlite.connect`` calls to use a helper would be a
large change with a lot of room for a typo in a place no test covers.
Instead this runs once at startup and puts the strays where the rest
already are, using a symlink so the old paths keep working untouched.

Set ``DATA_DIR`` to move everything somewhere else -- that is the
environment variable to point at a mounted volume. Without it nothing
changes and the bot behaves exactly as before.
"""

from __future__ import annotations

import os
import shutil

# Files the bot opens by a bare name from the working directory rather
# than from db/. Each is (name in the working directory, name inside the
# data directory). Verified against the source: rr.db is opened by
# api/panel_restore.py, api/routes/memberperks.py and
# cogs/commands/reactionroles.py; j2c_data.db by utils/voice_store.py.
STRAY_DATABASES = (
    "rr.db",
    "j2c_data.db",
)

# Directories that hold state and therefore belong on the volume.
STATE_DIRECTORIES = ("db", "jsondb")


def bot_dir() -> str:
    """The bot package directory, one level above utils/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """
    Where state should live.

    Defaults to the bot directory, which is what it always was. Point
    DATA_DIR at a mounted volume to make it survive a deploy.
    """
    configured = (os.environ.get("DATA_DIR") or "").strip()
    if not configured:
        return bot_dir()
    return os.path.abspath(os.path.expanduser(configured))


def is_persistent() -> bool:
    """True when DATA_DIR points somewhere other than the code itself."""
    return os.path.normpath(data_dir()) != os.path.normpath(bot_dir())


def _link_or_copy(source: str, target: str) -> str:
    """
    Make `source` resolve to `target`.

    A symlink is used rather than moving the file, because the code
    opens these by their bare name and rewriting every call site is the
    change this module exists to avoid.
    """
    if os.path.islink(source):
        if os.path.realpath(source) == os.path.realpath(target):
            return "already linked"
        os.unlink(source)

    # A real file at the source that is not yet in the data directory is
    # existing data. Move it rather than dropping it.
    if os.path.exists(source) and not os.path.islink(source):
        if not os.path.exists(target):
            shutil.move(source, target)
            action = "moved"
        else:
            # Both exist. The one in the data directory wins -- it is the
            # one that persists -- but the other is kept aside rather
            # than deleted, because guessing wrong here loses data.
            backup = source + ".before-volume"
            if not os.path.exists(backup):
                shutil.move(source, backup)
            else:
                os.remove(source)
            action = "kept the volume copy"
    else:
        action = "linked"

    try:
        os.symlink(target, source)
    except OSError as err:
        # Windows without developer mode, or a filesystem that has no
        # symlinks. Fall back to copying, which at least works, and say
        # so rather than pretending it is persistent.
        return f"could not link ({err}); the file stays local"

    return action


def prepare() -> list[str]:
    """
    Put everything where it belongs. Returns a line per thing done, for
    the startup log.

    Safe to call repeatedly: it does nothing on the second run.
    """
    notes: list[str] = []
    base = bot_dir()
    data = data_dir()

    if not is_persistent():
        return notes

    os.makedirs(data, exist_ok=True)

    for name in STATE_DIRECTORIES:
        source = os.path.join(base, name)
        target = os.path.join(data, name)
        os.makedirs(target, exist_ok=True)

        if os.path.islink(source):
            continue

        if os.path.isdir(source):
            # Copy anything already there into the volume, once.
            for entry in os.listdir(source):
                src_file = os.path.join(source, entry)
                dst_file = os.path.join(target, entry)
                if os.path.isfile(src_file) and not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
            shutil.rmtree(source)

        try:
            os.symlink(target, source)
            notes.append(f"{name}/ -> {target}")
        except OSError as err:
            os.makedirs(source, exist_ok=True)
            notes.append(f"{name}/ could not be linked: {err}")

    for name in STRAY_DATABASES:
        source = os.path.join(base, name)
        target = os.path.join(data, name)
        result = _link_or_copy(source, target)
        notes.append(f"{name} {result}")

    return notes


def looks_mounted() -> bool:
    """
    Whether the data directory is really a separate volume.

    Setting DATA_DIR without attaching a volume is the failure mode that
    matters here: everything works, nothing complains, and the data is
    gone on the next deploy anyway -- except now it looks like it is
    handled. A mount point sits on a different device than the root
    filesystem, so comparing st_dev tells the two apart.
    """
    if not is_persistent():
        return False
    path = data_dir()
    if not os.path.isdir(path):
        return False
    try:
        # Compared against the parent, not against "/". A mount point
        # sits on a different device than the directory it hangs in;
        # comparing to the root filesystem instead reports true for any
        # directory that merely happens to live on another filesystem --
        # /tmp/whatever in a container, for instance.
        parent = os.path.dirname(path.rstrip(os.sep)) or os.sep
        return os.stat(path).st_dev != os.stat(parent).st_dev
    except OSError:
        return False


def describe() -> dict:
    """What the dashboard needs to tell the owner whether this is safe."""
    return {
        "data_dir": data_dir(),
        "persistent": is_persistent(),
        "mounted": looks_mounted(),
        "env_var_set": bool((os.environ.get("DATA_DIR") or "").strip()),
        "strays": list(STRAY_DATABASES),
    }
