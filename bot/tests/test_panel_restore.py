"""
Panels must come back after a restore.

The configuration survives a backup, the panel message does not: it lives
in a Discord channel and is referenced by a message id that no longer works
after a redeploy. These tests use a fake Discord layer to check that
repost_all_panels() deletes the stale message, posts a fresh one and writes
the new id back.

Run:  python3 tests/test_panel_restore.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
warnings.filterwarnings("ignore")

GUILD = 111222333444555666
CHANNEL = 800
ROLE = 900
OLD_MESSAGE = 555


class FakeMessage:
    def __init__(self, mid, channel):
        self.id = mid
        self.channel = channel
        self.jump_url = f"https://discord.test/{mid}"
        self.deleted = False

    async def delete(self):
        self.deleted = True
        self.channel.deleted.append(self.id)


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent = []
        self.deleted = []
        self.existing = {}
        self._next = 9000

    async def fetch_message(self, mid):
        if mid in self.existing:
            return self.existing[mid]
        raise Exception("Unknown message")

    async def send(self, **kwargs):
        self._next += 1
        msg = FakeMessage(self._next, self)
        self.sent.append(kwargs)
        return msg


class FakeRole:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class FakeGuild:
    def __init__(self):
        self.id, self.name = GUILD, "Test Guild"
        self.channel = FakeChannel(CHANNEL, "verify")
        self.role = FakeRole(ROLE, "Verified")
        self.text_channels = [self.channel]

    def get_channel(self, cid):
        return self.channel if int(cid) == CHANNEL else None

    def get_role(self, rid):
        return self.role if int(rid) == ROLE else None


class FakeBot:
    def __init__(self, guild):
        self.guilds = [guild]
        self.registered = []

    def add_view(self, view, message_id=None):
        self.registered.append(message_id)

    def get_cog(self, _name):
        return None


def seed_verification(enabled=1, channel=CHANNEL, role=ROLE, panel_id=None):
    os.makedirs("db", exist_ok=True)
    con = sqlite3.connect("db/verification.db")
    con.execute(
        "CREATE TABLE IF NOT EXISTS verification_config ("
        " guild_id INTEGER PRIMARY KEY, verification_channel_id INTEGER,"
        " verified_role_id INTEGER, log_channel_id INTEGER,"
        " verification_method TEXT, enabled BOOLEAN,"
        " panel_message_id INTEGER)"
    )
    con.execute(
        "INSERT OR REPLACE INTO verification_config VALUES (?,?,?,?,?,?,?)",
        (GUILD, channel, role, 0, "both", enabled, panel_id),
    )
    con.commit()
    con.close()


def stored_panel_id():
    con = sqlite3.connect("db/verification.db")
    row = con.execute(
        "SELECT panel_message_id FROM verification_config WHERE guild_id = ?",
        (GUILD,),
    ).fetchone()
    con.close()
    return row[0] if row else None


def run():
    from api.panel_restore import repost_all_panels

    failures = []

    # --- 1. a configured, enabled panel is reposted -------------------
    seed_verification()
    guild = FakeGuild()
    guild.channel.existing[OLD_MESSAGE] = FakeMessage(OLD_MESSAGE, guild.channel)
    bot = FakeBot(guild)

    result = asyncio.run(repost_all_panels(bot))
    if result["panels_posted"] != 1:
        failures.append(f"expected 1 panel, got {result}")
        print(f"  FAIL  posts a panel: {result}")
    else:
        print("  PASS  posts a panel")

    if not guild.channel.sent:
        failures.append("nothing was sent to the channel")
        print("  FAIL  panel reached the channel")
    else:
        sent = guild.channel.sent[-1]
        if "view" not in sent:
            failures.append("panel was not sent as a Components V2 view")
            print("  FAIL  sent as a view")
        else:
            print("  PASS  sent as a view")

    if bot.registered:
        print("  PASS  view registered for persistence")
    else:
        failures.append("add_view was never called")
        print("  FAIL  view registered for persistence")

    # --- 1b. the stale panel is removed and the new id stored ---------
    seed_verification(panel_id=OLD_MESSAGE)
    guild1b = FakeGuild()
    guild1b.channel.existing[OLD_MESSAGE] = FakeMessage(OLD_MESSAGE, guild1b.channel)
    bot1b = FakeBot(guild1b)
    asyncio.run(repost_all_panels(bot1b))

    if OLD_MESSAGE in guild1b.channel.deleted:
        print("  PASS  deletes the stale panel")
    else:
        failures.append("the old panel message was not deleted")
        print("  FAIL  deletes the stale panel")

    new_id = stored_panel_id()
    if new_id and new_id != OLD_MESSAGE:
        print("  PASS  stores the new message id")
    else:
        failures.append(f"panel_message_id was not updated (got {new_id})")
        print(f"  FAIL  stores the new message id: {new_id}")

    # --- 2. disabled verification is left alone -----------------------
    seed_verification(enabled=0)
    guild2 = FakeGuild()
    result = asyncio.run(repost_all_panels(FakeBot(guild2)))
    if guild2.channel.sent:
        failures.append("posted a panel although verification is disabled")
        print("  FAIL  skips disabled verification")
    else:
        print("  PASS  skips disabled verification")

    # --- 3. missing channel is reported, not crashed on ---------------
    seed_verification(channel=999999)
    guild3 = FakeGuild()
    result = asyncio.run(repost_all_panels(FakeBot(guild3)))
    skipped = [d for d in result["details"] if d["status"] == "skipped"]
    if result["panels_failed"] or not skipped:
        failures.append(f"deleted channel not handled cleanly: {result}")
        print(f"  FAIL  handles a deleted channel: {result}")
    else:
        print("  PASS  handles a deleted channel")

    # --- 4. missing role is reported ----------------------------------
    seed_verification(role=999999)
    guild4 = FakeGuild()
    result = asyncio.run(repost_all_panels(FakeBot(guild4)))
    if result["panels_posted"]:
        failures.append("posted although the verified role is gone")
        print("  FAIL  handles a deleted role")
    else:
        print("  PASS  handles a deleted role")

    # --- 5. no configuration at all -----------------------------------
    con = sqlite3.connect("db/verification.db")
    con.execute("DELETE FROM verification_config")
    con.commit()
    con.close()
    guild5 = FakeGuild()
    result = asyncio.run(repost_all_panels(FakeBot(guild5)))
    if result["panels_posted"] or result["panels_failed"]:
        failures.append(f"unconfigured guild produced work: {result}")
        print(f"  FAIL  unconfigured guild is a no-op: {result}")
    else:
        print("  PASS  unconfigured guild is a no-op")

    # --- 6. dead reaction role rows are cleaned up --------------------
    con = sqlite3.connect("rr.db")
    con.execute(
        "CREATE TABLE IF NOT EXISTS reaction_roles ("
        " guild_id INTEGER, message_id INTEGER, emoji TEXT, role_id INTEGER)"
    )
    con.execute("DELETE FROM reaction_roles")
    con.executemany(
        "INSERT INTO reaction_roles VALUES (?,?,?,?)",
        [
            (GUILD, OLD_MESSAGE, "👍", ROLE),   # message still exists
            (GUILD, 777777, "❤", ROLE),        # message is gone
        ],
    )
    con.commit()
    con.close()

    guild6 = FakeGuild()
    guild6.text_channels = [guild6.channel]
    guild6.channel.existing[OLD_MESSAGE] = FakeMessage(OLD_MESSAGE, guild6.channel)
    asyncio.run(repost_all_panels(FakeBot(guild6)))

    con = sqlite3.connect("rr.db")
    left = {r[0] for r in con.execute(
        "SELECT message_id FROM reaction_roles WHERE guild_id = ?", (GUILD,)
    ).fetchall()}
    con.close()

    if left == {OLD_MESSAGE}:
        print("  PASS  removes dead reaction role rows, keeps live ones")
    else:
        failures.append(f"reaction role cleanup wrong, left={left}")
        print(f"  FAIL  removes dead reaction role rows: {left}")

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(run())
