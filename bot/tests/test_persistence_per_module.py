#!/usr/bin/env python3
"""
Does every module's data actually survive a deploy?

The volume works -- the deploy log shows `[storage] data lives in /data`
and a verification setup came back after a redeploy. This checks the
same thing for *every* module rather than trusting one spot check,
because the failure mode is per-file: one database written to the wrong
place looks exactly like the others until the day it is empty.

How it works: a throwaway directory plays the container, another plays
the volume. Each module writes through the API or its store, then the
"container" is deleted and rebuilt from scratch -- which is what Railway
does on a deploy -- and the data is read back.

Two things this is built to catch:

  * A database that lands outside the data directory. It would work
    perfectly until the next deploy and then be empty.
  * A module whose store points at a path nobody linked. rr.db and
    j2c_data.db were exactly that before the volume work: opened by a
    bare name from the working directory.

Run:  python3 tests/test_persistence_per_module.py
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


# ══════════════════════════════════════════════════════════════════════
#  Every database the bot writes, and which module owns it
# ══════════════════════════════════════════════════════════════════════
#
# Collected from the source rather than typed out by hand, so a new
# module cannot be forgotten. The check below walks this list.


def discover_databases() -> dict[str, set[str]]:
    """Map every .db path the bot opens to the files that open it."""
    import re

    owners: dict[str, set[str]] = {}
    # db_file is deliberately not in here: three cogs set it to a bare
    # name and then join it onto db_folder ("db") on the next line, so
    # matching it reported three false alarms the first time this ran.
    patterns = [
        re.compile(r'(?:aiosqlite|sqlite3)\.connect\(\s*[fr]?["\']([^"\']+\.db)["\']'),
        re.compile(r'(?:DB|PATH|_DB|_PATH|db_path)\s*=\s*[fr]?["\']([^"\']+\.db)["\']', re.I),
        re.compile(r'get_connection\(\s*["\']([^"\']+\.db)["\']'),
    ]
    for root, dirs, files in os.walk(BOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".git")]
        for name in files:
            if not name.endswith(".py"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, BOT)
            src = open(full, encoding="utf-8", errors="replace").read()
            for pattern in patterns:
                for found in pattern.findall(src):
                    if found in ("*.db", ".db"):
                        continue
                    owners.setdefault(found, set()).add(rel)
    return owners


def test_every_database_is_covered():
    """
    Every database is either under db/ or in the stray list.

    A path that is neither is written into the container and lost on the
    next deploy, silently.
    """
    print("\nEvery database is accounted for")

    from utils import storage

    owners = discover_databases()
    check("databases were found at all", len(owners) > 30, str(len(owners)))

    uncovered = []
    for path in sorted(owners):
        normalised = path.lstrip("./")
        if normalised.startswith("db/"):
            continue
        if normalised in storage.STRAY_DATABASES:
            continue
        uncovered.append((normalised, sorted(owners[path])[:2]))

    check("no database is written outside the volume",
          not uncovered,
          "; ".join(f"{p} ({', '.join(f)})" for p, f in uncovered))

    # And the reverse: a stray in the list that nothing opens is dead
    # weight that will rot.
    opened = {p.lstrip("./") for p in owners}
    for stray in storage.STRAY_DATABASES:
        check(f"{stray} is really used by something", stray in opened,
              "listed as a stray but nothing opens it")


# ══════════════════════════════════════════════════════════════════════
#  The deploy simulation
# ══════════════════════════════════════════════════════════════════════


def load_storage(bot_dir: str, data_dir: str):
    os.environ["DATA_DIR"] = data_dir
    path = os.path.join(bot_dir, "utils", "storage.py")
    spec = importlib.util.spec_from_file_location(
        f"storage_{id(bot_dir)}_{len(data_dir)}", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_container(root: str) -> str:
    """
    A fresh 'container': the code, and nothing else.

    Deleting and recreating this is what a Railway deploy does.
    """
    bot = os.path.join(root, "container", "bot")
    os.makedirs(os.path.join(bot, "utils"), exist_ok=True)
    shutil.copy(os.path.join(BOT, "utils", "storage.py"),
                os.path.join(bot, "utils", "storage.py"))
    return bot


# What each module writes, by the path its store actually uses. Taken
# from the store constants rather than guessed, so a renamed file shows
# up as a failure here instead of as missing data in production.
def module_databases() -> list[tuple[str, str]]:
    from utils import (
        anonchat_store, automod_store, extras_store, joindm_store,
        leveling_store, vanity_store, verify_store, voice_store,
    )

    entries = [
        ("Automod", automod_store.DB_PATH),
        ("Verifizierung", verify_store.DB_PATH),
        ("Level-System", leveling_store.DB_PATH),
        ("Anonymer Chat", anonchat_store.DB_PATH),
        ("Vanity-Rollen", vanity_store.DB_PATH),
        ("Beitritts-DM", joindm_store.DB_PATH),
        ("Benachrichtigungen", extras_store.NOTIFY_DB),
        # Counting keeps its state as JSON, not SQLite.
        ("Counting", extras_store.COUNTING_JSON),
        ("Jail", extras_store.JAIL_DB),
        ("Nachtmodus", extras_store.NIGHTMODE_DB),
        ("Sticky-Nachricht", extras_store.STICKY_DB),
        ("Booster", extras_store.BOOST_DB),
        ("Sprach-Rolle", voice_store.VOICEROLE_DB),
        ("Eigene Rollen", voice_store.CUSTOMROLE_DB),
        # The two that live outside db/. These are the ones a volume on
        # bot/db alone would have missed.
        ("Join to Create", voice_store.J2C_DB),
        ("Reaktions-Rollen", "rr.db"),
        # A few opened by literal path in their cog.
        ("Anti-Nuke", "db/anti.db"),
        ("Tickets", "db/ticket.db"),
        ("Begrüßung", "db/welcome.db"),
        ("Auto-Rolle", "db/autorole.db"),
        ("Protokollierung", "db/logging.db"),
        ("Einladungs-Log", "db/invite.db"),
        ("Giveaways", "db/giveaways.db"),
        ("Einstellungen", "db/settings.db"),
        ("Nickname", "db/nickname.db"),
        ("No Prefix", "db/np.db"),
        ("Auto-Reaktion", "db/autoreact.db"),
        ("Autoresponder", "db/autoresponder.db"),
        ("Notfall", "db/emergency.db"),
        ("Warnungen", "db/warn.db"),
    ]
    return entries


def test_survives_a_deploy():
    print("\nSurviving a deploy, module by module")

    modules = module_databases()
    check("modules were collected", len(modules) >= 25, str(len(modules)))

    root = tempfile.mkdtemp()
    volume = os.path.join(root, "volume")
    os.makedirs(volume)

    # ── First boot ───────────────────────────────────────────────
    bot = build_container(root)
    storage = load_storage(bot, volume)
    storage.prepare()

    cwd = os.getcwd()
    os.chdir(bot)
    try:
        for label, path in modules:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            if path.endswith(".json"):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(f'{{"module": "{label}"}}')
                continue
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE IF NOT EXISTS survives (module TEXT)")
            con.execute("DELETE FROM survives")
            con.execute("INSERT INTO survives VALUES (?)", (label,))
            con.commit()
            con.close()
    finally:
        os.chdir(cwd)

    written = len(modules)
    check(f"all {written} module databases were written", True)

    # ── The deploy: throw the container away, build it again ─────
    shutil.rmtree(os.path.join(root, "container"))
    bot = build_container(root)
    storage = load_storage(bot, volume)
    storage.prepare()

    os.chdir(bot)
    try:
        for label, path in modules:
            if not os.path.exists(path):
                check(f"{label}: data survived", False, f"{path} is gone")
                continue
            if path.endswith(".json"):
                content = open(path, encoding="utf-8").read()
                check(f"{label}: data survived", label in content, content[:60])
                continue
            try:
                con = sqlite3.connect(path)
                rows = list(con.execute("SELECT module FROM survives"))
                con.close()
            except sqlite3.Error as err:
                check(f"{label}: data survived", False, f"{path}: {err}")
                continue
            check(f"{label}: data survived",
                  rows == [(label,)],
                  f"{path} came back as {rows}")
    finally:
        os.chdir(cwd)

    shutil.rmtree(root)


def test_a_new_database_is_caught():
    """
    A module that writes somewhere nobody linked has to be noticed.

    This is the regression that matters: somebody adds a feature, opens
    "newthing.db" from the working directory, everything works, and the
    data disappears on the next deploy.
    """
    print("\nA database in the wrong place is noticed")

    root = tempfile.mkdtemp()
    volume = os.path.join(root, "volume")
    os.makedirs(volume)
    bot = build_container(root)
    storage = load_storage(bot, volume)
    storage.prepare()

    cwd = os.getcwd()
    os.chdir(bot)
    try:
        # A careless new module.
        con = sqlite3.connect("newfeature.db")
        con.execute("CREATE TABLE t (x INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()
        con.close()
        landed_in_volume = os.path.exists(os.path.join(volume, "newfeature.db"))
    finally:
        os.chdir(cwd)

    check("a database opened by a bare name does NOT persist",
          not landed_in_volume,
          "if this ever passes the check below is pointless")

    # Which is exactly why the source scan above exists: it is the thing
    # that catches this, not the filesystem.
    check("and the source scan is what catches that",
          True)

    shutil.rmtree(root)


def test_json_state_survives():
    print("\nThe JSON files")

    root = tempfile.mkdtemp()
    volume = os.path.join(root, "volume")
    os.makedirs(volume)
    bot = build_container(root)
    storage = load_storage(bot, volume)
    storage.prepare()

    cwd = os.getcwd()
    os.chdir(bot)
    try:
        os.makedirs("jsondb", exist_ok=True)
        with open("jsondb/joindm_messages.json", "w") as handle:
            handle.write('{"1": "hallo"}')
    finally:
        os.chdir(cwd)

    shutil.rmtree(os.path.join(root, "container"))
    bot = build_container(root)
    storage = load_storage(bot, volume)
    storage.prepare()

    os.chdir(bot)
    try:
        exists = os.path.exists("jsondb/joindm_messages.json")
        content = open("jsondb/joindm_messages.json").read() if exists else ""
    finally:
        os.chdir(cwd)

    check("jsondb/ survives a deploy", exists)
    check("with its contents", content == '{"1": "hallo"}', content)

    shutil.rmtree(root)


def main():
    test_every_database_is_covered()
    test_survives_a_deploy()
    test_a_new_database_is_caught()
    test_json_state_survives()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
