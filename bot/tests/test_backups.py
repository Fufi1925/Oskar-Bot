#!/usr/bin/env python3
"""
The automatic backups.

Two things are checked here, and the first one is a bug that shipped:

**Everything must be in the snapshot.** The scheduler used to glob
``db/*.db`` itself instead of asking the one function that knows what a
backup contains. Two copies of that knowledge drifted apart, and the
automatic snapshots quietly left out ``rr.db`` (reaction roles) and
``j2c_data.db`` (join to create) -- both of which live in the working
directory rather than in ``db/``. Restoring an automatic backup would
have wiped both, and nothing anywhere would have said so.

**The old snapshot is deleted last.** With only one kept, the previous
snapshot is the only copy in existence while the new one is being
written. Rotating first and then failing leaves nothing at all. So the
new one is read back -- opened, integrity-checked -- and the old one is
removed only after that passes. A backup nobody has opened is a guess.

Run:  python3 tests/test_backups.py
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time

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


class FakeBot:
    guilds: list = []


async def make_db(path, table):
    import aiosqlite

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (guild_id INTEGER, v TEXT)"
        )
        await db.execute(f"INSERT INTO {table} VALUES (1, 'wichtig')")
        await db.commit()


def fresh_workspace():
    """
    A clean working directory per test.

    The paths are relative ("db/...", "rr.db"), so tests sharing a
    directory also share leftover snapshots -- which made the rotation
    counts meaningless.
    """
    work = tempfile.mkdtemp()
    os.chdir(work)
    os.makedirs("db", exist_ok=True)
    return work


def services():
    from utils import feature_services as fs

    instance = fs.FeatureServices.__new__(fs.FeatureServices)
    instance.bot = FakeBot()
    return fs, instance


def snapshots(fs):
    if not os.path.isdir(fs.BACKUP_DIR):
        return []
    return sorted(
        d for d in os.listdir(fs.BACKUP_DIR)
        if os.path.isdir(os.path.join(fs.BACKUP_DIR, d))
    )


# ══════════════════════════════════════════════════════════════════════
#  Everything that belongs in a backup is in it
# ══════════════════════════════════════════════════════════════════════


async def test_nothing_is_skipped():
    print("\nEverything is in the snapshot")
    fresh_workspace()

    await make_db("db/leveling.db", "leveling")
    await make_db("db/ticket.db", "tickets")
    # The two that were missing. Not in db/, which is exactly why the
    # glob never saw them.
    await make_db("rr.db", "reaction_roles")
    await make_db("j2c_data.db", "guild_setup")
    os.makedirs("jsondb", exist_ok=True)
    with open("jsondb/joindm_messages.json", "w", encoding="utf-8") as handle:
        handle.write('{"1": "hallo"}')

    from api.config_transfer import db_key, iter_database_files

    fs, instance = services()
    await instance._backup_loop()

    taken = snapshots(fs)
    check("a snapshot was written", len(taken) == 1, str(taken))
    if not taken:
        return

    stored = set(os.listdir(os.path.join(fs.BACKUP_DIR, taken[-1])))
    expected = {db_key(p) for p in iter_database_files()}

    missing = sorted(expected - stored)
    check("every database the manual backup keeps is in there",
          not missing,
          f"missing: {missing} -- restoring this snapshot would wipe them")

    # Named individually, so the failure message says which feature dies.
    check("reaction roles are backed up", "rr.db" in stored, str(sorted(stored)))
    check("join to create is backed up", "j2c_data.db" in stored,
          str(sorted(stored)))
    check("the JSON config is backed up too",
          "jsondb__joindm_messages.json" in stored,
          "join-DM templates are not in SQLite and were lost on a restore")

    # The scheduler must not carry its own idea of what a backup is.
    source = open(os.path.join(BOT, "utils/feature_services.py"),
                  encoding="utf-8").read()
    body = source.split("async def _backup_loop")[1].split("async def _cleanup_loop")[0]
    stripped = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("#")
    )
    check("the scheduler asks the shared function instead of globbing",
          "write_snapshot" in stripped and 'glob.glob(os.path.join(DB_DIR' not in stripped,
          "a second copy of 'what goes in a backup' is how this broke")


# ══════════════════════════════════════════════════════════════════════
#  The old one goes last
# ══════════════════════════════════════════════════════════════════════


async def test_rotation_waits_for_a_good_backup():
    print("\nThe old snapshot is deleted last")
    fresh_workspace()

    await make_db("db/leveling.db", "leveling")
    await make_db("rr.db", "reaction_roles")

    fs, instance = services()

    check("only one snapshot is kept", fs.BACKUP_KEEP == 1, str(fs.BACKUP_KEEP))
    check("and it is taken daily", fs.BACKUP_INTERVAL == 86400,
          f"{fs.BACKUP_INTERVAL}s")

    await instance._backup_loop()
    first = snapshots(fs)
    check("the first backup is there", len(first) == 1, str(first))

    # A second later, so the folder name differs.
    time.sleep(1.1)
    await instance._backup_loop()
    second = snapshots(fs)
    check("a second run leaves exactly one", len(second) == 1, str(second))
    check("and it is the new one", second != first, f"{first} -> {second}")

    # Now the part that matters: a backup that cannot be read back must
    # not cost us the one we already had.
    import api.config_transfer as transfer

    real = transfer.write_snapshot

    async def corrupt(target):
        os.makedirs(target, exist_ok=True)
        # Right size, right name, not a database. A size check would
        # pass this, which is why the verifier opens the file instead.
        with open(os.path.join(target, "leveling.db"), "wb") as handle:
            handle.write(b"this is not sqlite" * 40)
        with open(os.path.join(target, "rr.db"), "wb") as handle:
            handle.write(b"nor is this" * 40)
        return 2, 0

    before = snapshots(fs)
    transfer.write_snapshot = corrupt
    try:
        time.sleep(1.1)
        await instance._backup_loop()
    finally:
        transfer.write_snapshot = real
    after = snapshots(fs)

    check("a corrupt backup does not delete the good one",
          before == after, f"{before} -> {after}")
    check("and the broken one is not left lying around",
          len(after) == 1,
          "a snapshot that failed verification must not look like a backup")

    # An empty file is the other realistic failure -- a disk that filled
    # up mid-write.
    async def empty(target):
        os.makedirs(target, exist_ok=True)
        for name in ("leveling.db", "rr.db"):
            open(os.path.join(target, name), "wb").close()
        return 2, 0

    before = snapshots(fs)
    transfer.write_snapshot = empty
    try:
        time.sleep(1.1)
        await instance._backup_loop()
    finally:
        transfer.write_snapshot = real
    check("an empty backup is refused too", snapshots(fs) == before,
          str(snapshots(fs)))

    # A file missing entirely.
    async def incomplete(target):
        os.makedirs(target, exist_ok=True)
        import aiosqlite

        async with aiosqlite.connect("db/leveling.db") as source:
            async with aiosqlite.connect(
                os.path.join(target, "leveling.db")
            ) as destination:
                await source.backup(destination)
        return 1, 0  # rr.db never written

    before = snapshots(fs)
    transfer.write_snapshot = incomplete
    try:
        time.sleep(1.1)
        await instance._backup_loop()
    finally:
        transfer.write_snapshot = real
    check("a snapshot with a file missing is refused",
          snapshots(fs) == before,
          "half a backup restores as a wiped database")

    # And after all that, a good run still works and still rotates.
    time.sleep(1.1)
    await instance._backup_loop()
    final = snapshots(fs)
    check("a good backup afterwards still rotates", len(final) == 1, str(final))
    check("and it is newer than the one it replaced",
          final != before, f"{before} -> {final}")


async def test_safety_copies_survive():
    """
    "pre-restore-*" and "pre-import-*" are the user's undo button.

    They are taken right before something overwrites live data, so
    rotating them away would remove the only way back from a bad
    restore.
    """
    print("\nSafety copies are not rotated away")
    fresh_workspace()

    await make_db("db/leveling.db", "leveling")
    await make_db("rr.db", "reaction_roles")

    fs, instance = services()
    os.makedirs(fs.BACKUP_DIR, exist_ok=True)
    keep = os.path.join(fs.BACKUP_DIR, "pre-restore-20200101-000000")
    os.makedirs(keep, exist_ok=True)
    with open(os.path.join(keep, "leveling.db"), "wb") as handle:
        handle.write(b"safety")

    await instance._backup_loop()
    time.sleep(1.1)
    await instance._backup_loop()

    check("the pre-restore copy is still there", os.path.isdir(keep),
          "this is the only way back from a bad restore")
    automatic = [d for d in snapshots(fs) if not d.startswith("pre-")]
    check("while the automatic ones still rotate to one",
          len(automatic) == 1, str(automatic))


# ══════════════════════════════════════════════════════════════════════


async def run():
    print("Automatic backups")

    from api.db_manager import db_manager

    try:
        await test_nothing_is_skipped()
        await test_rotation_waits_for_a_good_backup()
        await test_safety_copies_survive()
    finally:
        await db_manager.close_all()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
