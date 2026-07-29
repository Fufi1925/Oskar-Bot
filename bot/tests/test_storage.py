#!/usr/bin/env python3
"""
Where the data lives, and whether it survives a deploy.

Until now it did not. Railway rebuilds the container on every deploy, so
all 61 SQLite files went with it -- every server lost every setting,
every time. The fix is a mounted volume, but a volume on ``bot/db``
alone would have been a trap:

  * **Three things live outside db/.** ``rr.db`` (reaction roles),
    ``j2c_data.db`` (join to create) and the ``jsondb/`` folder are
    opened by a bare name from the working directory. A volume on
    ``bot/db`` would silently leave those behind -- the bot would start
    fine and the reaction roles would just be gone. Confirmed by
    grepping the source: rr.db is opened in three files, j2c_data.db in
    one.

  * **DATA_DIR set without a volume attached looks identical to the
    working case.** Everything runs, nothing complains, and the data is
    still lost -- except now it looks handled. A mount point sits on a
    different device than /, so st_dev tells them apart.

Rather than rewrite 405 ``aiosqlite.connect`` calls -- a large change
with plenty of room for a typo somewhere no test looks -- the strays are
symlinked into the data directory at startup, so every existing path
keeps working untouched.

Run:  python3 tests/test_storage.py
"""

import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def load_storage(bot_dir: str, data_dir: str | None):
    """A fresh copy of the module rooted at a throwaway directory."""
    if data_dir is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = data_dir

    path = os.path.join(bot_dir, "utils", "storage.py")
    spec = importlib.util.spec_from_file_location(f"storage_{id(path)}_{data_dir}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_bot() -> str:
    """A directory shaped like the bot package, with some data in it."""
    tmp = tempfile.mkdtemp()
    bot = os.path.join(tmp, "bot")
    os.makedirs(os.path.join(bot, "utils"))
    shutil.copy(os.path.join(BOT, "utils", "storage.py"),
                os.path.join(bot, "utils", "storage.py"))
    return bot


def seed(bot: str):
    """Existing data, as a server that has been running would have."""
    os.makedirs(os.path.join(bot, "db"), exist_ok=True)
    con = sqlite3.connect(os.path.join(bot, "db", "welcome.db"))
    con.execute("CREATE TABLE welcome (guild_id INTEGER, message TEXT)")
    con.execute("INSERT INTO welcome VALUES (1, 'hallo')")
    con.commit()
    con.close()

    con = sqlite3.connect(os.path.join(bot, "rr.db"))
    con.execute("CREATE TABLE rr (message_id INTEGER, emoji TEXT)")
    con.execute("INSERT INTO rr VALUES (42, '👍')")
    con.commit()
    con.close()


# ══════════════════════════════════════════════════════════════════════
#  The strays are real
# ══════════════════════════════════════════════════════════════════════


def test_stray_list_matches_the_code():
    """
    The list of databases living outside db/ has to match what the code
    actually opens. A name missing from it is a database that silently
    does not persist.
    """
    print("\nThe strays")

    import re

    storage = load_storage(BOT, None)

    # Only real opens count. A bare name that is looked up in a table
    # and gets "db/" put in front of it later -- guilds.py does exactly
    # that for its module overview -- is not a stray, and an earlier
    # version of this check flagged fifteen of them.
    patterns = [
        r'connect\(\s*"((?!db/)[a-z_0-9]+\.db)"',          # aiosqlite.connect("x.db")
        r'(?:DB|PATH|_DB|_PATH)\s*=\s*"((?!db/)[a-z_0-9]+\.db)"',
        r'self\.db\w*\s*=\s*"((?!db/)[a-z_0-9]+\.db)"',
    ]
    opened: set[str] = set()
    for root, dirs, files in os.walk(BOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
        for name in files:
            if not name.endswith(".py"):
                continue
            src = open(os.path.join(root, name), encoding="utf-8").read()
            for pattern in patterns:
                opened.update(re.findall(pattern, src))

    missing = opened - set(storage.STRAY_DATABASES)
    check("every database outside db/ is in the stray list",
          not missing, str(sorted(missing)))

    for name in storage.STRAY_DATABASES:
        check(f"{name} is really opened somewhere", name in opened,
              "a stray nobody opens is dead weight")

    check("db and jsondb are both treated as state",
          set(storage.STATE_DIRECTORIES) == {"db", "jsondb"},
          str(storage.STATE_DIRECTORIES))


# ══════════════════════════════════════════════════════════════════════
#  Behaviour
# ══════════════════════════════════════════════════════════════════════


def test_without_data_dir():
    print("\nWithout DATA_DIR")

    bot = fake_bot()
    storage = load_storage(bot, None)

    check("it reports as not persistent", storage.is_persistent() is False)
    check("and does nothing at all", storage.prepare() == [])
    check("looks_mounted is false too", storage.looks_mounted() is False,
          "no DATA_DIR cannot be a mounted volume")
    check("describe says so",
          storage.describe()["persistent"] is False)


def test_moves_existing_data():
    print("\nMoving what is already there")

    bot = fake_bot()
    seed(bot)
    volume = os.path.join(os.path.dirname(bot), "volume")
    storage = load_storage(bot, volume)

    notes = storage.prepare()
    check("it reports what it did", len(notes) >= 3, str(notes))

    # The directories.
    check("db/ became a link", os.path.islink(os.path.join(bot, "db")))
    check("jsondb/ became a link", os.path.islink(os.path.join(bot, "jsondb")))
    check("the existing welcome.db moved into the volume",
          os.path.exists(os.path.join(volume, "db", "welcome.db")))

    # The data itself, not just the file.
    con = sqlite3.connect(os.path.join(volume, "db", "welcome.db"))
    rows = list(con.execute("SELECT message FROM welcome"))
    con.close()
    check("with its contents intact", rows == [("hallo",)], str(rows))

    # The strays.
    check("rr.db became a link", os.path.islink(os.path.join(bot, "rr.db")))
    check("and its data moved too",
          os.path.exists(os.path.join(volume, "rr.db")))
    con = sqlite3.connect(os.path.join(volume, "rr.db"))
    rows = list(con.execute("SELECT emoji FROM rr"))
    con.close()
    check("with its contents intact", rows == [("👍",)], str(rows))

    check("j2c_data.db is linked even though it did not exist yet",
          os.path.islink(os.path.join(bot, "j2c_data.db")),
          "it has to be ready before the cog first writes to it")

    shutil.rmtree(os.path.dirname(bot))


def test_old_paths_still_work():
    """
    The point of the symlink: 405 call sites keep their bare paths.
    """
    print("\nThe old paths keep working")

    bot = fake_bot()
    seed(bot)
    volume = os.path.join(os.path.dirname(bot), "volume")
    storage = load_storage(bot, volume)
    storage.prepare()

    # Write through the old path.
    con = sqlite3.connect(os.path.join(bot, "rr.db"))
    con.execute("INSERT INTO rr VALUES (99, '🎉')")
    con.commit()
    con.close()

    # Read it out of the volume.
    con = sqlite3.connect(os.path.join(volume, "rr.db"))
    rows = [r[0] for r in con.execute("SELECT emoji FROM rr ORDER BY message_id")]
    con.close()
    check("a write through the old path lands in the volume",
          rows == ["👍", "🎉"], str(rows))

    # Same for a file inside db/.
    con = sqlite3.connect(os.path.join(bot, "db", "new.db"))
    con.execute("CREATE TABLE t (x INTEGER)")
    con.commit()
    con.close()
    check("a new database in db/ lands in the volume too",
          os.path.exists(os.path.join(volume, "db", "new.db")))

    shutil.rmtree(os.path.dirname(bot))


def test_second_run_is_harmless():
    """
    prepare() runs on every start, not just the first.
    """
    print("\nRunning it twice")

    bot = fake_bot()
    seed(bot)
    volume = os.path.join(os.path.dirname(bot), "volume")
    storage = load_storage(bot, volume)
    storage.prepare()
    storage.prepare()
    storage.prepare()

    check("the link is still a link",
          os.path.islink(os.path.join(bot, "rr.db")))
    con = sqlite3.connect(os.path.join(volume, "rr.db"))
    rows = list(con.execute("SELECT emoji FROM rr"))
    con.close()
    check("and the data is still there", rows == [("👍",)], str(rows))

    shutil.rmtree(os.path.dirname(bot))


def test_never_deletes_data():
    """
    Both copies exist. The volume wins, but the other is kept.

    This is the case where guessing wrong loses somebody's reaction
    roles, so the loser is set aside rather than removed.
    """
    print("\nWhen both copies exist")

    bot = fake_bot()
    seed(bot)
    volume = os.path.join(os.path.dirname(bot), "volume")
    os.makedirs(volume)

    # A different rr.db already in the volume.
    con = sqlite3.connect(os.path.join(volume, "rr.db"))
    con.execute("CREATE TABLE rr (message_id INTEGER, emoji TEXT)")
    con.execute("INSERT INTO rr VALUES (7, '⭐')")
    con.commit()
    con.close()

    storage = load_storage(bot, volume)
    storage.prepare()

    con = sqlite3.connect(os.path.join(bot, "rr.db"))
    rows = [r[0] for r in con.execute("SELECT emoji FROM rr")]
    con.close()
    check("the volume copy wins", rows == ["⭐"], str(rows))
    check("the local one is kept, not deleted",
          os.path.exists(os.path.join(bot, "rr.db.before-volume")),
          "guessing wrong here loses somebody's data")

    shutil.rmtree(os.path.dirname(bot))


def test_mount_detection():
    print("\nTelling a volume from a plain folder")

    bot = fake_bot()
    volume = os.path.join(os.path.dirname(bot), "volume")
    os.makedirs(volume)
    storage = load_storage(bot, volume)

    check("a plain directory is not reported as mounted",
          storage.looks_mounted() is False,
          "DATA_DIR set with no volume behind it is the dangerous case")
    check("but it is still reported as persistent-configured",
          storage.is_persistent() is True)
    check("describe separates the two",
          storage.describe()["persistent"] is True
          and storage.describe()["mounted"] is False)

    # /tmp is a real mount point in this container, so it proves the
    # detection reports true when it should.
    if os.stat("/tmp").st_dev != os.stat("/").st_dev:
        mounted = load_storage(bot, "/tmp")
        check("a real mount point is detected", mounted.looks_mounted() is True)
    else:
        print("  skip a real mount point is detected (/tmp is not one here)")

    shutil.rmtree(os.path.dirname(bot))


# ══════════════════════════════════════════════════════════════════════
#  Wiring
# ══════════════════════════════════════════════════════════════════════


def test_startup_and_docker():
    print("\nWiring")

    main = open(os.path.join(BOT, "university_bot.py"), encoding="utf-8").read()
    check("storage runs at startup", "_prepare_storage()" in main)

    # Order matters: bootstrap creates db/ and jsondb/ when missing, so
    # running it first would make the directories in the image and leave
    # storage moving something created a moment earlier.
    check("storage runs before bootstrap",
          main.index("_prepare_storage()\n") < main.index("_run_bootstrap()\n"),
          "bootstrap would otherwise create the directories first")

    check("it warns when nothing is mounted",
          "WARNING: DATA_DIR is set but nothing is mounted" in main,
          "silent half-configuration is worse than none")

    docker = open(os.path.join(os.path.dirname(BOT), "Dockerfile"),
                  encoding="utf-8").read()
    check("the Dockerfile sets DATA_DIR", "ENV DATA_DIR=/data" in docker)
    # Railway refuses to build at all when a VOLUME instruction is
    # present: "docker VOLUME at Line 76 is not supported, use Railway
    # Volumes". It manages mounts from its own dashboard, so declaring
    # one here is not just redundant, it is fatal.
    check("and does not declare a docker VOLUME",
          "\nVOLUME " not in docker and not docker.startswith("VOLUME "),
          "Railway rejects the build outright")

    admin = open(os.path.join(BOT, "api/routes/admin.py"), encoding="utf-8").read()
    check("the health endpoint reports it", '"storage": {' in admin,
          "the owner needs to see this without reading logs")
    check("and says plainly whether it is safe", '"safe":' in admin)


def main_():
    test_stray_list_matches_the_code()
    test_without_data_dir()
    test_moves_existing_data()
    test_old_paths_still_work()
    test_second_run_is_harmless()
    test_never_deletes_data()
    test_mount_detection()
    test_startup_and_docker()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_())
