#!/usr/bin/env python3
"""
The leveling system.

The bugs this pins down, all of which shipped:

  * `/rank`, the leaderboard and the API read the `user_xp` table while
    `resetxp`, `setxp` and `setlevel` wrote a second table called
    `users`. The admin commands reported success and changed nothing.
  * `min_xp` / `max_xp` were stored, shown in the setup dialog and never
    used — every message was worth exactly `xp_per_message`.
  * The level-up embed worked out a colour from the settings and then
    passed `color=0xFF0000` regardless.
  * Settings were unpacked by tuple index, so adding a column anywhere
    but at the end shifted every value after it.
  * Role multipliers were multiplied together, so three 2x roles became
    8x.

Run:  python3 tests/test_leveling.py
"""

import asyncio
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import aiosqlite  # noqa: E402
import discord  # noqa: E402

GUILD = 333
CHANNEL = "1327995167345819721"   # a real 19-digit snowflake
ROLE_LOW = 900000000000000001
ROLE_HIGH = 900000000000000002
ROLE_TOP = 900000000000000009


class FakeRole:
    def __init__(self, rid, name, position=1, managed=False):
        self.id, self.name, self.position = rid, name, position
        self.managed = managed
        self.color = type("C", (), {"value": 0x5865F2})()
        self.mention = f"<@&{rid}>"

    def __lt__(self, other):
        return self.position < other.position

    def __ge__(self, other):
        return self.position >= other.position


class FakeMessage:
    def __init__(self, mid, channel):
        self.id, self.channel = mid, channel
        self.jump_url = f"https://d/{mid}"


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent = []

    def permissions_for(self, _m):
        return discord.Permissions.all()

    async def send(self, content=None, view=None, **kw):
        self.sent.append(view or content)
        return FakeMessage(1, self)


class FakeMember:
    def __init__(self, uid, name):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.roles = []
        self.added, self.removed = [], []
        self.guild = None

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()

    @property
    def top_role(self):
        return max(self.roles, key=lambda r: r.position) if self.roles else FakeRole(0, "@everyone", 0)

    async def add_roles(self, *roles, reason=None):
        self.added += list(roles)
        self.roles += list(roles)

    async def remove_roles(self, *roles, reason=None):
        self.removed += list(roles)
        self.roles = [r for r in self.roles if r not in roles]


class FakeGuild:
    id, name = GUILD, "Test"

    def __init__(self):
        self.channel = FakeChannel(int(CHANNEL), "chat")
        self.roles = {
            ROLE_LOW: FakeRole(ROLE_LOW, "Bronze", 1),
            ROLE_HIGH: FakeRole(ROLE_HIGH, "Silber", 2),
            ROLE_TOP: FakeRole(ROLE_TOP, "Zu hoch", 99),
        }
        self.members = {
            10: FakeMember(10, "Alice"),
            11: FakeMember(11, "Bob"),
        }
        for m in self.members.values():
            m.guild = self
        # The bot's own role sits above Bronze/Silber but below "Zu hoch".
        self.me = FakeMember(1, "Bot")
        self.me.guild = self
        self.me.roles = [FakeRole(999, "Bot", 50)]

    def get_channel(self, cid):
        return self.channel if str(cid) == CHANNEL else None

    def get_role(self, rid):
        return self.roles.get(int(rid))

    def get_member(self, uid):
        return self.members.get(int(uid))


class FakeBot:
    user = type("U", (), {"name": "Bot", "id": 1})()

    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import leveling_store as store
    from utils import rank_card

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/leveling/{GUILD}"
    guild = bot.guilds[0]

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    async def db():
        connection = await db_manager.get_connection(store.DB_PATH)
        await store.ensure_schema(connection)
        return connection

    # ══ XP curve ══════════════════════════════════════════════════
    check("level 0 needs no xp", store.xp_for_level(0) == 0)
    check("the curve round-trips",
          store.level_from_xp(store.xp_for_level(7)) == 7,
          str(store.level_from_xp(store.xp_for_level(7))))
    check("one xp below a level does not count as that level",
          store.level_from_xp(store.xp_for_level(7) - 1) == 6)
    check("negative xp is level 0", store.level_from_xp(-50) == 0)

    level, into, needed = store.progress(store.xp_for_level(3) + 50)
    check("progress reports the level", level == 3, str(level))
    check("progress reports how far in", into == 50, str(into))
    check("progress reports what the level needs",
          needed == store.xp_for_level(4) - store.xp_for_level(3), str(needed))

    # ══ One table, not two ════════════════════════════════════════
    #
    # The old code kept `user_xp` and `users` in step by hand, and the
    # admin commands only wrote the second one.
    async def one_table():
        connection = await db()
        await store.set_xp(connection, GUILD, 10, 5000)
        before = await store.get_user(connection, GUILD, 10)
        await store.reset_user(connection, GUILD, 10)
        after = await store.get_user(connection, GUILD, 10)
        return before["xp"], after["xp"]

    before_xp, after_xp = asyncio.run(one_table())
    check("setting xp is visible to the read path", before_xp == 5000, str(before_xp))
    check("resetting really clears it", after_xp == 0, str(after_xp))

    # ══ Settings by name, not by position ═════════════════════════
    async def settings_round_trip():
        connection = await db()
        await store.save_settings(connection, GUILD, {
            "enabled": 1, "min_xp": 7, "max_xp": 9, "cooldown_seconds": 30,
            "embed_color": 0x00FF00, "level_message": "Hi {user}, Level {level}!",
            "delete_after": 15, "command_delete_after": 20,
        })
        return await store.get_settings(connection, GUILD)

    settings = asyncio.run(settings_round_trip())
    check("min_xp comes back as min_xp", settings["min_xp"] == 7, str(settings["min_xp"]))
    check("cooldown comes back as cooldown",
          settings["cooldown_seconds"] == 30, str(settings["cooldown_seconds"]))
    check("the colour survives", settings["embed_color"] == 0x00FF00,
          hex(settings["embed_color"]))
    check("auto-delete for level-ups is stored",
          settings["delete_after"] == 15, str(settings["delete_after"]))
    check("auto-delete for replies is stored",
          settings["command_delete_after"] == 20, str(settings["command_delete_after"]))

    # A partial write must not blank the rest.
    async def partial():
        connection = await db()
        await store.save_settings(connection, GUILD, {"cooldown_seconds": 45})
        return await store.get_settings(connection, GUILD)

    after = asyncio.run(partial())
    check("a partial save keeps the other settings",
          after["min_xp"] == 7 and after["level_message"] == "Hi {user}, Level {level}!",
          f'{after["min_xp"]} {after["level_message"]!r}')
    check("the changed setting is written", after["cooldown_seconds"] == 45)

    # ══ min/max are actually used ═════════════════════════════════
    rolls = {store.roll_xp({"min_xp": 5, "max_xp": 9}) for _ in range(300)}
    check("xp is random between min and max", len(rolls) > 1, str(sorted(rolls)))
    check("xp never leaves the range", rolls <= {5, 6, 7, 8, 9}, str(sorted(rolls)))
    check("min equal to max is a fixed amount",
          {store.roll_xp({"min_xp": 8, "max_xp": 8}) for _ in range(20)} == {8})
    check("a max below the min does not raise",
          store.roll_xp({"min_xp": 10, "max_xp": 2}) in range(2, 11))

    normalised = store.normalise({"min_xp": 10, "max_xp": 2})
    check("normalising lifts max up to min", normalised["max_xp"] == 10,
          str(normalised["max_xp"]))

    # ══ Multipliers: highest wins, no stacking ════════════════════
    async def multipliers():
        connection = await db()
        await store.set_multiplier(connection, GUILD, ROLE_LOW, "role", 2.0)
        await store.set_multiplier(connection, GUILD, ROLE_HIGH, "role", 3.0)
        both = await store.multiplier_for(
            connection, GUILD, role_ids=[ROLE_LOW, ROLE_HIGH]
        )
        await store.set_multiplier(connection, GUILD, int(CHANNEL), "channel", 2.0)
        with_channel = await store.multiplier_for(
            connection, GUILD, channel_id=int(CHANNEL), role_ids=[ROLE_LOW, ROLE_HIGH]
        )
        none = await store.multiplier_for(connection, GUILD, role_ids=[])
        return both, with_channel, none

    both, with_channel, none = asyncio.run(multipliers())
    check("two role multipliers do not stack — the highest wins",
          both == 3.0, str(both))
    check("a channel multiplier applies on top of the role one",
          with_channel == 6.0, str(with_channel))
    check("no multiplier means 1x", none == 1.0, str(none))

    # ══ Exclusions ════════════════════════════════════════════════
    async def exclusions():
        connection = await db()
        await store.add_excluded(connection, GUILD, int(CHANNEL), "channel")
        by_channel = await store.is_excluded(
            connection, GUILD, channel_id=int(CHANNEL)
        )
        elsewhere = await store.is_excluded(connection, GUILD, channel_id=42)
        await store.add_excluded(connection, GUILD, ROLE_LOW, "role")
        by_role = await store.is_excluded(
            connection, GUILD, channel_id=42, role_ids=[ROLE_LOW]
        )
        await store.remove_excluded(connection, GUILD, int(CHANNEL), "channel")
        gone = await store.is_excluded(connection, GUILD, channel_id=int(CHANNEL))
        return by_channel, elsewhere, by_role, gone

    by_channel, elsewhere, by_role, gone = asyncio.run(exclusions())
    check("an excluded channel gives no xp", by_channel is True)
    check("other channels are unaffected", elsewhere is False)
    check("an excluded role gives no xp", by_role is True)
    check("removing an exclusion works", gone is False)

    # ══ Reward roles ══════════════════════════════════════════════
    async def rewards():
        connection = await db()
        await store.set_reward(connection, GUILD, 2, ROLE_LOW)
        await store.set_reward(connection, GUILD, 5, ROLE_HIGH)

        stacked_add, stacked_remove = await store.roles_for_level(
            connection, GUILD, 5, stack=True
        )
        single_add, single_remove = await store.roles_for_level(
            connection, GUILD, 5, stack=False
        )
        too_early, _ = await store.roles_for_level(connection, GUILD, 1, stack=True)
        return stacked_add, stacked_remove, single_add, single_remove, too_early

    s_add, s_remove, one_add, one_remove, early = asyncio.run(rewards())
    check("stacking keeps every earned role",
          set(s_add) == {ROLE_LOW, ROLE_HIGH} and s_remove == [], str(s_add))
    check("without stacking only the highest is kept",
          one_add == [ROLE_HIGH], str(one_add))
    check("without stacking the lower one is taken away",
          one_remove == [ROLE_LOW], str(one_remove))
    check("a level below the first reward earns nothing", early == [], str(early))

    # ══ add_xp reports the level change ═══════════════════════════
    async def levelling():
        connection = await db()
        await store.reset_user(connection, GUILD, 11)
        first = await store.add_xp(connection, GUILD, 11, store.xp_for_level(1))
        again = await store.add_xp(connection, GUILD, 11, 1)
        return first, again

    first, again = asyncio.run(levelling())
    check("crossing a level is reported", first[1] == 0 and first[2] == 1, str(first))
    check("staying on a level is not reported as a level up",
          again[1] == again[2], str(again))

    async def counts_messages():
        connection = await db()
        await store.reset_user(connection, GUILD, 11)
        for _ in range(3):
            await store.add_xp(connection, GUILD, 11, 5)
        return await store.get_user(connection, GUILD, 11)

    user = asyncio.run(counts_messages())
    check("messages are counted", user["messages"] == 3, str(user["messages"]))
    check("xp adds up", user["xp"] == 15, str(user["xp"]))

    # ══ Ranking ═══════════════════════════════════════════════════
    async def ranking():
        connection = await db()
        await store.reset_guild(connection, GUILD)
        await store.set_xp(connection, GUILD, 10, 9000)
        await store.set_xp(connection, GUILD, 11, 100)
        board = await store.leaderboard(connection, GUILD, limit=10)
        return (
            board,
            await store.get_rank(connection, GUILD, 10),
            await store.get_rank(connection, GUILD, 11),
            await store.get_rank(connection, GUILD, 99),
        )

    board, top_rank, low_rank, unknown_rank = asyncio.run(ranking())
    check("the leaderboard is sorted by xp",
          [e["user_id"] for e in board] == [10, 11], str(board))
    check("the leaderboard numbers the places",
          [e["rank"] for e in board] == [1, 2], str(board))
    check("the top member is rank 1", top_rank == 1, str(top_rank))
    check("the second member is rank 2", low_rank == 2, str(low_rank))
    check("somebody with no xp is last, not rank 1",
          unknown_rank == 3, str(unknown_rank))

    # ══ The API ═══════════════════════════════════════════════════
    r = client.get(base)
    check("the settings can be read", r.status_code == 200, r.text[:120])
    body = r.json()
    check("ids come back as strings, not numbers",
          isinstance(body["guild_id"], str), str(type(body["guild_id"])))
    check("the colour is offered as hex too",
          body["embed_color_hex"].startswith("#"), body["embed_color_hex"])
    check("the stats ride along", "members" in body["stats"], str(body["stats"]))
    check("the placeholders are documented for the editor",
          "level" in body["placeholders"], str(body["placeholders"])[:60])

    r = client.patch(base, json={"cooldown_seconds": 90, "actor": "10"})
    check("settings can be changed", r.status_code == 200, r.text[:120])
    check("the change sticks",
          client.get(base).json()["cooldown_seconds"] == 90)

    r = client.patch(base, json={"embed_color_hex": "#ff0000"})
    check("a hex colour is accepted",
          client.get(base).json()["embed_color"] == 0xFF0000,
          hex(client.get(base).json()["embed_color"]))

    r = client.patch(base, json={"embed_color_hex": "nope"})
    check("a broken colour is rejected", r.status_code == 400, str(r.status_code))

    # A partial PATCH must not reset the rest.
    client.patch(base, json={"min_xp": 3, "max_xp": 4})
    client.patch(base, json={"enabled": True})
    after = client.get(base).json()
    check("a partial PATCH keeps the other settings",
          after["min_xp"] == 3 and after["cooldown_seconds"] == 90,
          f'{after["min_xp"]} {after["cooldown_seconds"]}')

    # Leaderboard
    r = client.get(f"{base}/leaderboard")
    board = r.json()
    check("the leaderboard is served", r.status_code == 200, r.text[:120])
    check("member ids stay strings",
          all(isinstance(e["user_id"], str) for e in board["entries"]),
          str(board["entries"][:1]))
    check("names are resolved",
          any(e["name"] == "Alice" for e in board["entries"]), str(board["entries"]))

    # Editing a member
    r = client.post(f"{base}/members/11", json={"level": 4, "actor": "10"})
    check("a level can be set from the dashboard", r.status_code == 200, r.text[:120])
    check("setting the level sets matching xp",
          r.json()["member"]["level"] == 4, str(r.json()["member"]))

    r = client.post(f"{base}/members/11", json={"add_xp": -100000})
    check("taking away more xp than someone has floors at 0",
          r.json()["member"]["xp"] == 0, str(r.json()["member"]))

    r = client.post(f"{base}/members/11", json={"nonsense": 1})
    check("an empty member update is rejected", r.status_code == 400)

    # Rewards through the API
    r = client.post(f"{base}/rewards", json={"level": 3, "role_id": str(ROLE_LOW)})
    check("a reward role can be added", r.status_code == 200, r.text[:120])

    r = client.post(f"{base}/rewards", json={"level": 4, "role_id": str(ROLE_TOP)})
    check("a role above the bot is refused with a reason",
          r.status_code == 400 and "Bot" in r.json()["detail"],
          r.text[:140])

    r = client.post(f"{base}/rewards", json={"level": 4, "role_id": "12345"})
    check("an unknown role gives 404", r.status_code == 404, str(r.status_code))

    r = client.delete(f"{base}/rewards/3")
    check("a reward can be removed", r.status_code == 200, r.text[:120])
    r = client.delete(f"{base}/rewards/3")
    check("removing it twice gives 404", r.status_code == 404)

    # Multipliers through the API
    r = client.post(f"{base}/multipliers", json={
        "target_id": str(ROLE_LOW), "target_type": "role", "multiplier": 2.5,
    })
    check("a multiplier can be added", r.status_code == 200, r.text[:120])
    r = client.post(f"{base}/multipliers", json={
        "target_id": str(ROLE_LOW), "target_type": "role", "multiplier": 0,
    })
    check("a multiplier of zero is rejected", r.status_code == 400)

    r = client.delete(f"{base}/multipliers/role/{ROLE_LOW}")
    check("a multiplier can be removed", r.status_code == 200)

    # Preview
    r = client.post(f"{base}/preview", json={
        "channel_id": CHANNEL, "actor": "10",
        "level_message": "Glückwunsch {user}, Level {level}!",
    })
    check("a preview can be sent", r.status_code == 200, r.text[:140])
    check("the preview reaches the channel", len(guild.channel.sent) > 0)

    r = client.post(f"{base}/preview", json={"channel_id": "999"})
    check("previewing into an unknown channel gives 404", r.status_code == 404)

    # ══ Rank card ═════════════════════════════════════════════════
    panel = rank_card.render_panel(
        name="Alice", level=5, rank=1, xp=2500,
        into_level=100, level_needs=1100, messages=42,
    )
    rendered = str(panel.to_components())
    check("the text card names the level", "Level 5" in rendered, rendered[:120])
    check("the text card shows the rank", "#1" in rendered, rendered[:120])

    check("the progress bar is empty at zero",
          rank_card.progress_bar(0, 100).startswith("▱"))
    check("the progress bar is full at the end",
          set(rank_card.progress_bar(100, 100)) == {"▰"})
    check("a zero-length level does not divide by zero",
          len(rank_card.progress_bar(0, 0)) == 16)

    check("big numbers are shortened", rank_card.compact(12345) == "12.3K",
          rank_card.compact(12345))
    check("small numbers are left alone", rank_card.compact(999) == "999")

    image = asyncio.run(rank_card.render_image(
        name="Alice", avatar_bytes=None, level=5, rank=1, xp=2500,
        into_level=100, level_needs=1100, messages=42,
    ))
    if rank_card.PIL_AVAILABLE:
        check("the image card is drawn", image is not None)
        check("it really is a PNG",
              image is not None and image.getvalue()[:4] == b"\x89PNG",
              str(image.getvalue()[:4]) if image else "None")
    else:
        check("without Pillow the caller gets None, not an exception",
              image is None)

    # A broken avatar must not take the whole card down.
    image = asyncio.run(rank_card.render_image(
        name="Alice", avatar_bytes=b"not an image", level=1, rank=1, xp=0,
        into_level=0, level_needs=100, messages=0,
    ))
    check("a corrupt avatar still produces a card",
          image is not None or not rank_card.PIL_AVAILABLE)

    # ══ Migration off the old tables ══════════════════════════════
    async def migration():
        path = "db/old_leveling.db"
        async with aiosqlite.connect(path) as old:
            await old.execute(
                "CREATE TABLE user_xp (guild_id INTEGER, user_id INTEGER,"
                " xp INTEGER, messages INTEGER, last_message_time TEXT,"
                " PRIMARY KEY (guild_id, user_id))"
            )
            await old.execute(
                "CREATE TABLE users (guild_id INTEGER, user_id INTEGER,"
                " xp INTEGER, level INTEGER, PRIMARY KEY (guild_id, user_id))"
            )
            await old.execute(
                "CREATE TABLE level_roles (guild_id INTEGER, level INTEGER,"
                " role_id INTEGER, PRIMARY KEY (guild_id, level))"
            )
            # What the members earned.
            await old.execute("INSERT INTO user_xp VALUES (?, ?, ?, ?, '')",
                              (GUILD, 77, 4200, 130))
            # The stale copy the admin commands wrote to.
            await old.execute("INSERT INTO users VALUES (?, ?, 0, 1)", (GUILD, 77))
            await old.execute("INSERT INTO level_roles VALUES (?, 6, ?)",
                              (GUILD, ROLE_HIGH))
            await old.commit()

        async with aiosqlite.connect(path) as connection:
            await store.ensure_schema(connection)
            user = await store.get_user(connection, GUILD, 77)
            carried = await store.rewards(connection, GUILD)
            return user, carried

    migrated, carried = asyncio.run(migration())
    check("the real xp is carried over, not the stale copy",
          migrated["xp"] == 4200, str(migrated))
    check("messages are carried over", migrated["messages"] == 130, str(migrated))
    check("the level is worked out from the carried xp",
          migrated["level"] == store.level_from_xp(4200), str(migrated))
    check("old level roles become rewards",
          carried == [{"level": 6, "role_id": ROLE_HIGH}], str(carried))

    # ══ Placeholders ══════════════════════════════════════════════
    text = store.fill("{user} ist Level {level} auf {server}", {
        "user": "<@10>", "level": 5, "server": "Test",
    })
    check("placeholders are replaced",
          text == "<@10> ist Level 5 auf Test", text)
    check("an unknown placeholder is left alone",
          store.fill("{gibtsnicht}", {"user": "x"}) == "{gibtsnicht}")

    # db_manager caches its connections, and aiosqlite's worker thread is
    # not a daemon — without this the process stays alive after the last
    # check has run. The bot does the same in its shutdown hook.
    asyncio.run(db_manager.close_all())

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        os.makedirs("jsondb", exist_ok=True)
        sys.exit(run())
