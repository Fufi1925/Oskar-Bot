#!/usr/bin/env python3
"""
Join to Create, voice roles and custom role commands.

The bugs pinned down here, all reproduced before they were fixed:

  * **The voice-role off switch did nothing.** The API stored an
    ``enabled`` column and the dashboard rendered a toggle for it, but
    the cog only ever ran ``SELECT role_id FROM vcroles``. Setting it to
    off changed a number in the database and the bot carried on handing
    the role out.

  * **Only one voice role was possible.** ``vcroles`` was keyed on
    ``guild_id`` alone, so the schema itself made a second role
    impossible -- and the cog said "already set in this guild".

  * **Join to Create never showed as configured.** The setup overview
    counted rows in ``db/block.db`` table ``j2c``. That is the blacklist
    database and has no such table, so the module was reported as "not
    set up" on every server no matter what. The data lives in
    ``j2c_data.db``.

  * **Blocking someone in a private VC did not keep them out.** The
    check sat in the ``before.channel`` branch, which runs when a member
    *leaves*.

  * **Member dropdowns broke above 25 members.** They were built from
    the full member list; Discord rejects a select with more than 25
    options, so BLOCK, INVITE, KICK, UNBLOCK and TRANSFER failed on any
    server big enough to need them.

  * **Custom roles crashed on DMs** -- ``message.guild.id`` with no None
    check -- and required the reqrole from the server owner in the
    dynamic handler while letting them through everywhere else.

Run:  python3 tests/test_voice.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import aiosqlite  # noqa: E402

GUILD = 7701
ROLE_OK = 500000000000000001
ROLE_HIGH = 500000000000000002
ROLE_MANAGED = 500000000000000003
CHANNEL_VOICE = 1327995167345819721      # a real-length snowflake
CHANNEL_TEXT = 1327995167345819722
CATEGORY = 1327995167345819723
ALICE = 111
BOB = 222

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


# ══════════════════════════════════════════════════════════════════════
#  Fakes
# ══════════════════════════════════════════════════════════════════════


class FakeRole:
    def __init__(self, rid, name, position=1, managed=False, default=False):
        self.id = rid
        self.name = name
        self.position = position
        self.managed = managed
        self.color = type("C", (), {"value": 0})()
        self.mention = f"<@&{rid}>"
        self._default = default

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= other.position

    def __lt__(self, other):
        return self.position < other.position

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, FakeRole) and other.id == self.id


class FakePerms:
    def __init__(self, **kw):
        self.manage_roles = kw.get("manage_roles", True)
        self.manage_channels = kw.get("manage_channels", True)
        self.move_members = kw.get("move_members", True)
        self.administrator = kw.get("administrator", False)
        self.send_messages = kw.get("send_messages", True)


class FakeChannel:
    def __init__(self, cid, name="kanal", ctype="voice", category=None):
        self.id = cid
        self.name = name
        self.type = ctype
        self.category = category
        self.channels = []
        self.sent = []
        self.mention = f"<#{cid}>"

    async def send(self, content=None, view=None, **kw):
        message = type("M", (), {"id": 999, "view": view})()
        self.sent.append(message)
        return message


class FakeMember:
    def __init__(self, uid, roles=None, top=1, bot=False, perms=None):
        self.id = uid
        self.name = f"User{uid}"
        self.display_name = self.name
        self.bot = bot
        self.mention = f"<@{uid}>"
        self.roles = roles or []
        self.top_role = FakeRole(9999, "top", top)
        self.guild_permissions = perms or FakePerms()
        self.added = []
        self.removed = []
        self.moved_to = "not called"

    async def add_roles(self, *roles, reason=None):
        self.added.extend(roles)
        self.roles = list(self.roles) + list(roles)

    async def remove_roles(self, *roles, reason=None):
        self.removed.extend(roles)
        self.roles = [r for r in self.roles if r not in roles]

    async def move_to(self, channel, reason=None):
        self.moved_to = channel


class FakeGuild:
    def __init__(self, gid=GUILD, afk=None):
        self.id = gid
        self.name = "Test"
        self.owner = None
        self.afk_channel = afk
        self._roles = {}
        self._channels = {}
        # The cog resolves message.mentions through get_member when the
        # mention is a bare User rather than a Member -- which is real
        # behaviour, so the fake has to support it.
        self._members = {}
        self.me = FakeMember(1, top=100)
        self.default_role = FakeRole(0, "@everyone", 0, default=True)

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_member(self, uid):
        return self._members.get(int(uid))


class FakeVoiceState:
    def __init__(self, channel=None):
        self.channel = channel


class FakeBot:
    def __init__(self, prefix=">"):
        self.prefix = prefix
        self.commands_by_name = {}

    async def get_prefix(self, message):
        return [self.prefix, "<@1>"]

    def get_command(self, name):
        return self.commands_by_name.get(name)


# ══════════════════════════════════════════════════════════════════════
#  Store
# ══════════════════════════════════════════════════════════════════════


async def test_voicerole_store(store):
    print("\nVoice role storage")

    # Exactly the layout the old cog created.
    conn = sqlite3.connect(store.VOICEROLE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vcroles "
        "(guild_id INTEGER PRIMARY KEY, role_id INTEGER NOT NULL)"
    )
    conn.execute("INSERT INTO vcroles (guild_id, role_id) VALUES (?, ?)",
                 (GUILD, ROLE_OK))
    conn.commit()
    conn.close()

    db = await aiosqlite.connect(store.VOICEROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        settings = await store.voicerole_get(db, GUILD)
        check("an old single role is carried over",
              settings["roles"] == [ROLE_OK], str(settings["roles"]))
        check("and it starts switched off, as it was",
              settings["enabled"] is False)

        saved = await store.voicerole_save(db, GUILD, {
            "enabled": True, "roles": [str(ROLE_OK), str(ROLE_HIGH)],
        })
        check("more than one role can be stored",
              saved["roles"] == [ROLE_OK, ROLE_HIGH], str(saved["roles"]))
        check("snowflakes survive as full ids",
              all(len(str(r)) == 18 for r in saved["roles"]), str(saved["roles"]))

        saved = await store.voicerole_save(db, GUILD, {"channels": [str(CHANNEL_VOICE)]})
        check("a partial save keeps the roles",
              saved["roles"] == [ROLE_OK, ROLE_HIGH], str(saved["roles"]))
        check("and the switch", saved["enabled"] is True)

        saved = await store.voicerole_save(db, GUILD, {"roles": []})
        check("clearing the roles works", saved["roles"] == [])

        # Junk must not reach the database.
        saved = await store.voicerole_save(db, GUILD, {"roles": ["nope", None, "42", "42"]})
        check("only real ids are kept, without duplicates",
              saved["roles"] == [42], str(saved["roles"]))
    finally:
        await db.close()


def test_voicerole_rules(store):
    print("\nVoice role rules")

    base = {"enabled": True, "roles": [ROLE_OK], "channels": [],
            "ignore_afk": True, "include_stage": True}

    check("with no channel list it covers everything",
          store.voicerole_applies(base, CHANNEL_VOICE, False, False))

    # This is the bug that was reported: the switch did nothing.
    off = {**base, "enabled": False}
    check("switching it off really stops it",
          store.voicerole_applies(off, CHANNEL_VOICE, False, False) is False)

    check("no roles means nothing happens",
          store.voicerole_applies({**base, "roles": []}, CHANNEL_VOICE, False, False)
          is False)

    limited = {**base, "channels": [CHANNEL_VOICE]}
    check("a chosen channel counts",
          store.voicerole_applies(limited, CHANNEL_VOICE, False, False))
    check("any other channel does not",
          store.voicerole_applies(limited, 424242, False, False) is False)

    check("the AFK channel is skipped",
          store.voicerole_applies(base, CHANNEL_VOICE, True, False) is False)
    check("unless that is switched off",
          store.voicerole_applies({**base, "ignore_afk": False},
                                  CHANNEL_VOICE, True, False))
    check("stage channels can be excluded",
          store.voicerole_applies({**base, "include_stage": False},
                                  CHANNEL_VOICE, False, True) is False)


async def test_schema_conflict(store):
    """
    schema_guard and the store disagreed about custom_roles.

    The guard declared (guild_id, user_id, role_id) -- a shape nothing
    reads -- and it runs first. CREATE TABLE IF NOT EXISTS does not
    alter an existing table, so on any deployment starting from an empty
    database the wrong table won and every prefixed message raised
    "sqlite3.OperationalError: no such column: name". It went unnoticed
    locally because the development database already had the right
    table.
    """
    print("\nWrong table shape (seen in production)")

    import sqlite3

    path = store.CUSTOMROLE_DB
    if os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE custom_roles (guild_id INTEGER, user_id INTEGER,"
        " role_id INTEGER, PRIMARY KEY (guild_id, user_id))"
    )
    conn.commit()
    conn.close()

    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    try:
        # This is the call that crashed on every message with a prefix.
        result = await store.customrole_lookup(db, GUILD, "gamer")
        check("a lookup against the wrong table does not crash",
              result is None, str(result))

        columns = [
            row[1] for row in
            await (await db.execute("PRAGMA table_info(custom_roles)")).fetchall()
        ]
        check("the table is rebuilt with the right columns",
              "name" in columns, str(columns))
        check("and the dead column is gone", "user_id" not in columns, str(columns))

        await store.customrole_add(db, GUILD, "gamer", ROLE_OK)
        check("commands can be created afterwards",
              await store.customrole_lookup(db, GUILD, "gamer") == ROLE_OK)

        # Repairing must not run again and wipe what was just created.
        await store.customrole_ensure(db)
        check("a correct table is left alone",
              await store.customrole_lookup(db, GUILD, "gamer") == ROLE_OK)
    finally:
        await db.close()
        if os.path.exists(path):
            os.remove(path)


def test_schema_guard_matches_store():
    """The guard must declare the same shape the store expects."""
    print("\nschema_guard agrees with the store")

    guard = open(os.path.join(HERE, "..", "api", "schema_guard.py")).read()
    block = guard[guard.index("db/customrole.db"):]
    block = block[:block.index("db/logging.db")]

    check("custom_roles is keyed by name in schema_guard",
          "name TEXT NOT NULL" in block and "PRIMARY KEY (guild_id, name)" in block,
          block[-300:])
    # Only the SQL matters -- the surrounding comment mentions the old
    # column on purpose, to explain what went wrong.
    sql = block[block.index("CREATE TABLE IF NOT EXISTS custom_roles"):]
    sql = sql[:sql.index('"""')]
    check("and no longer by user_id", "user_id" not in sql, sql)


async def test_customrole_store(store):
    print("\nCustom role storage")

    db = await aiosqlite.connect(store.CUSTOMROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        await store.customrole_ensure(db)
        await db.execute(
            "INSERT INTO roles (guild_id, staff, vip, reqrole) VALUES (?, ?, ?, ?)",
            (GUILD, ROLE_OK, ROLE_HIGH, 4242),
        )
        await db.commit()

        config = await store.customrole_get(db, GUILD)
        check("the old fixed slots become named commands",
              sorted(config["migrated"]) == ["staff", "vip"], str(config["migrated"]))
        check("with the right roles behind them",
              {e["name"]: e["role_id"] for e in config["entries"]}
              == {"staff": ROLE_OK, "vip": ROLE_HIGH},
              str(config["entries"]))
        check("the required role survives", config["reqrole"] == 4242)

        again = await store.customrole_get(db, GUILD)
        check("the migration does not run twice", again["migrated"] == [])

        # A deleted command must stay deleted.
        await store.customrole_remove(db, GUILD, "staff")
        third = await store.customrole_get(db, GUILD)
        check("a deleted command is not resurrected",
              [e["name"] for e in third["entries"]] == ["vip"],
              str(third["entries"]))

        await store.customrole_add(db, GUILD, "Gamer", ROLE_OK)
        check("names are stored lowercase",
              await store.customrole_lookup(db, GUILD, "gamer") == ROLE_OK)
        check("and looked up case-insensitively",
              await store.customrole_lookup(db, GUILD, "GAMER") == ROLE_OK)
        check("an unknown name returns nothing",
              await store.customrole_lookup(db, GUILD, "nope") is None)

        check("removing something absent reports it",
              await store.customrole_remove(db, GUILD, "nope") is False)
    finally:
        await db.close()

    print("\nCommand names")
    for bad in ("", "mit leerzeichen", "a" * 25, "Groß Klein", "emoji🎉", "@ping"):
        check(f"{bad[:18]!r} is rejected",
              store.customrole_check_name(bad) is not None)
    for good in ("gamer", "vip_2", "team-a", "GAMER"):
        check(f"{good!r} is accepted", store.customrole_check_name(good) is None)


async def test_j2c_store(store):
    print("\nJoin to Create storage")

    db = await aiosqlite.connect(store.J2C_DB)
    db.row_factory = aiosqlite.Row
    try:
        settings = await store.j2c_get(db, GUILD)
        check("an unconfigured server reads as empty",
              settings["join_channel_id"] is None)
        check("and is not reported as configured",
              store.j2c_is_configured(settings) is False)

        settings = await store.j2c_save(db, GUILD, {
            "join_channel_id": str(CHANNEL_VOICE),
            "control_channel_id": str(CHANNEL_TEXT),
        })
        check("the ids survive as full snowflakes",
              settings["join_channel_id"] == CHANNEL_VOICE,
              str(settings["join_channel_id"]))
        check("both channels means configured",
              store.j2c_is_configured(settings))

        settings = await store.j2c_save(db, GUILD, {"default_limit": 9999})
        check("the limit is capped at what Discord allows",
              settings["default_limit"] == 99, str(settings["default_limit"]))
        check("a partial save keeps the channels",
              settings["join_channel_id"] == CHANNEL_VOICE)

        await store.j2c_clear(db, GUILD)
        check("clearing really removes it",
              store.j2c_is_configured(await store.j2c_get(db, GUILD)) is False)
    finally:
        await db.close()

    print("\nChannel names")
    check("the placeholder is filled in",
          store.j2c_channel_name("{user}'s VC", user_name="Lena") == "Lena's VC")
    check("the display name is used when asked for",
          store.j2c_channel_name("{user.display}", user_name="a",
                                 display_name="Lena") == "Lena")
    check("the counter works",
          store.j2c_channel_name("Raum {count}", user_name="x", count=3) == "Raum 3")
    long = store.j2c_channel_name("{user}", user_name="x" * 200)
    check("an over-long name is cut to Discord's 100",
          len(long) == 100, str(len(long)))
    check("an empty template still yields a usable name",
          store.j2c_channel_name("   ", user_name="Lena") == "Lena's VC")

    print("\nSelect menus")
    check("25 options need no note", store.select_options_note(25) == "")
    check("more than 25 is called out", "25" in store.select_options_note(200))


# ══════════════════════════════════════════════════════════════════════
#  Cogs
# ══════════════════════════════════════════════════════════════════════


async def test_voicerole_cog(store):
    print("\nVoice role cog")

    from cogs.commands.Invc import Invcrole

    cog = Invcrole(FakeBot())
    guild = FakeGuild()
    role = FakeRole(ROLE_OK, "In Voice", 5)
    guild._roles[ROLE_OK] = role
    voice = FakeChannel(CHANNEL_VOICE, "Talk")
    guild._channels[CHANNEL_VOICE] = voice

    db = await aiosqlite.connect(store.VOICEROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        await store.voicerole_save(db, GUILD, {
            "enabled": True, "roles": [ROLE_OK], "channels": [],
        })
    finally:
        await db.close()

    member = FakeMember(ALICE)
    member.guild = guild

    await cog.on_voice_state_update(
        member, FakeVoiceState(None), FakeVoiceState(voice)
    )
    check("joining hands out the role", role in member.roles,
          str([r.name for r in member.roles]))

    await cog.on_voice_state_update(
        member, FakeVoiceState(voice), FakeVoiceState(None)
    )
    check("leaving takes it away again", role not in member.roles)

    # The reported bug.
    db = await aiosqlite.connect(store.VOICEROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        await store.voicerole_save(db, GUILD, {"enabled": False})
    finally:
        await db.close()

    member2 = FakeMember(BOB)
    member2.guild = guild
    await cog.on_voice_state_update(
        member2, FakeVoiceState(None), FakeVoiceState(voice)
    )
    check("with the switch off nothing is handed out",
          member2.added == [], str(member2.added))

    # Mute/deafen fire the same event with the same channel on both
    # sides; the old code re-checked the role every time.
    db = await aiosqlite.connect(store.VOICEROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        await store.voicerole_save(db, GUILD, {"enabled": True})
    finally:
        await db.close()

    member3 = FakeMember(333)
    member3.guild = guild
    await cog.on_voice_state_update(
        member3, FakeVoiceState(voice), FakeVoiceState(voice)
    )
    check("muting inside the same channel changes nothing",
          member3.added == [] and member3.removed == [])

    bot_member = FakeMember(444, bot=True)
    bot_member.guild = guild
    await cog.on_voice_state_update(
        bot_member, FakeVoiceState(None), FakeVoiceState(voice)
    )
    check("bots are ignored", bot_member.added == [])


async def test_customrole_cog(store):
    print("\nCustom role cog")

    from cogs.commands.customrole import Customrole

    bot = FakeBot()
    cog = Customrole(bot)

    guild = FakeGuild()
    role = FakeRole(ROLE_OK, "Gamer", 5)
    reqrole = FakeRole(4242, "Team", 4)
    guild._roles[ROLE_OK] = role
    guild._roles[4242] = reqrole

    db = await aiosqlite.connect(store.CUSTOMROLE_DB)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("DELETE FROM custom_roles WHERE guild_id = ?", (GUILD,))
        await db.execute("DELETE FROM roles WHERE guild_id = ?", (GUILD,))
        await db.commit()
        await store.customrole_add(db, GUILD, "gamer", ROLE_OK)
        await store.customrole_set_reqrole(db, GUILD, 4242)
    finally:
        await db.close()

    channel = FakeChannel(CHANNEL_TEXT, "chat", "text")

    def message(content, author, mentions=(), guild_obj=guild):
        msg = type("M", (), {})()
        msg.content = content
        msg.author = author
        msg.channel = channel
        msg.guild = guild_obj
        msg.mentions = list(mentions)
        return msg

    # The DM crash.
    dm_author = FakeMember(ALICE)
    channel.sent.clear()
    await cog.on_message(message(">gamer @x", dm_author, guild_obj=None))
    check("a DM does not crash the listener", channel.sent == [])

    def known(member):
        """Members the guild can resolve, like a real cache would."""
        guild._members[member.id] = member
        member.guild = guild
        return member

    # Someone without the required role.
    outsider = known(FakeMember(ALICE, roles=[]))
    target = known(FakeMember(BOB, roles=[]))
    channel.sent.clear()
    await cog.on_message(message(">gamer @bob", outsider, [target]))
    check("without the required role it is refused", target.added == [])
    check("and the reason is said out loud", len(channel.sent) == 1)

    # The owner. The dynamic handler used to refuse them while the slot
    # commands let them through.
    owner = known(FakeMember(777, roles=[]))
    guild.owner = owner
    target2 = known(FakeMember(888, roles=[]))
    channel.sent.clear()
    await cog.on_message(message(">gamer @t", owner, [target2]))
    check("the server owner may use it without the required role",
          role in target2.roles, str([r.name for r in target2.roles]))

    # Holder of the required role, toggling.
    holder = known(FakeMember(999, roles=[reqrole]))
    target3 = known(FakeMember(1010, roles=[]))
    await cog.on_message(message(">gamer @t", holder, [target3]))
    check("someone with the role may hand it out", role in target3.roles)

    cog.cooldown.clear()
    await cog.on_message(message(">gamer @t", holder, [target3]))
    check("running it again takes the role back", role not in target3.roles)

    # The cooldown was keyed per guild, so one person blocked everyone.
    cog.cooldown.clear()
    a = known(FakeMember(1111, roles=[reqrole]))
    b = known(FakeMember(2222, roles=[reqrole]))
    t1, t2 = known(FakeMember(3333)), known(FakeMember(4444))
    await cog.on_message(message(">gamer @t", a, [t1]))
    await cog.on_message(message(">gamer @t", b, [t2]))
    check("one person's cooldown does not block everybody else",
          role in t1.roles and role in t2.roles,
          f"{[r.name for r in t1.roles]} {[r.name for r in t2.roles]}")

    # An unknown command must be left for the normal command handler.
    channel.sent.clear()
    await cog.on_message(message(">something", holder, []))
    check("an unrelated command is ignored", channel.sent == [])

    channel.sent.clear()
    await cog.on_message(message("gamer @t", holder, [t1]))
    check("text without a prefix is ignored", channel.sent == [])


async def test_j2c_cog(store):
    print("\nJoin to Create cog")

    from cogs.commands.j2c import JoinToCreate, UserSelectDropdown
    from discord import SelectOption

    # The dropdown cap -- this is what broke on every server over 25
    # members.
    options = [SelectOption(label=f"M{i}", value=str(i)) for i in range(120)]
    dropdown = UserSelectDropdown(options, "Wähle", lambda *a: None)
    check("a 120-member list is cut to 25",
          len(dropdown.options) == 25, str(len(dropdown.options)))
    check("max_values never exceeds the options",
          dropdown.max_values <= len(dropdown.options),
          f"{dropdown.max_values} > {len(dropdown.options)}")
    check("and the placeholder says so",
          "120" in (dropdown.placeholder or ""), str(dropdown.placeholder))
    check("the placeholder stays within Discord's 100 characters",
          len(dropdown.placeholder or "") <= 100)

    small = UserSelectDropdown(
        [SelectOption(label="A", value="1")], "Wähle", lambda *a: None
    )
    check("a single option still works",
          small.max_values == 1 and len(small.options) == 1)

    # Blocking has to bite on the way in.
    cog = JoinToCreate(FakeBot())
    guild = FakeGuild()
    private = FakeChannel(555, "Lenas VC")
    guild._channels[555] = private

    cog.setup_data[GUILD] = {
        "join_channel_id": CHANNEL_VOICE,
        "control_channel_id": CHANNEL_TEXT,
        "control_message_id": None,
        "category_id": None,
        "name_template": "{user}'s VC",
        "default_limit": 2,
        "default_locked": False,
    }
    cog.private_channels[555] = {
        "owner": ALICE, "limit": 2, "region": "", "is_locked": False,
        "has_waiting_room": False, "has_thread": False, "guild_id": GUILD,
    }
    cog.blocked_users[555] = [BOB]

    blocked = FakeMember(BOB)
    blocked.guild = guild
    await cog.on_voice_state_update(
        blocked, FakeVoiceState(None), FakeVoiceState(private)
    )
    check("a blocked member is thrown out when they walk in",
          blocked.moved_to is None, str(blocked.moved_to))

    allowed = FakeMember(333)
    allowed.guild = guild
    await cog.on_voice_state_update(
        allowed, FakeVoiceState(None), FakeVoiceState(private)
    )
    check("everybody else is left alone",
          allowed.moved_to == "not called", str(allowed.moved_to))

    owner = FakeMember(ALICE)
    owner.guild = guild
    cog.blocked_users[555] = [ALICE]
    await cog.on_voice_state_update(
        owner, FakeVoiceState(None), FakeVoiceState(private)
    )
    check("the owner cannot lock themselves out",
          owner.moved_to == "not called", str(owner.moved_to))


async def test_j2c_cache_reload(store):
    """
    The cache the cog answers voice events from must match the database.

    Two ways it did not, both of which look exactly like "I set it in
    the dashboard and nothing happens":

      * ``load_data`` assigned into the existing dicts and never removed
        anything, so a guild that switched Join to Create **off** stayed
        in the cache and kept creating channels until the next restart.
      * it ran the SELECT without letting the shared store bring the
        schema up to date, so on a database written before the extra
        columns existed it raised "no such column: name_template". The
        caller swallows that, leaving the cache empty -- and then Join
        to Create does nothing at all, on a server where the dashboard
        happily shows it as configured.
    """
    print("\nJoin to Create: the cog's cache")

    import aiosqlite

    from cogs.commands.j2c import JoinToCreate

    cog = JoinToCreate(FakeBot())
    await cog.init_db()

    async with aiosqlite.connect(store.J2C_DB) as db:
        await store.j2c_save(db, GUILD, {
            "join_channel_id": str(CHANNEL_VOICE),
            "control_channel_id": str(CHANNEL_TEXT),
        })
    await cog.refresh(GUILD)
    check("a dashboard save reaches the cog",
          GUILD in cog.setup_data, str(cog.setup_data))

    # Switching it off has to actually switch it off.
    async with aiosqlite.connect(store.J2C_DB) as db:
        await store.j2c_clear(db, GUILD)
    await cog.refresh(GUILD)
    check("switching it off empties the cache too",
          GUILD not in cog.setup_data,
          "the cog kept creating channels for a guild that had turned "
          "the feature off")

    # And a changed lobby is picked up, not merged on top of the old one.
    async with aiosqlite.connect(store.J2C_DB) as db:
        await store.j2c_save(db, GUILD, {
            "join_channel_id": str(CHANNEL_VOICE),
            "control_channel_id": str(CHANNEL_TEXT),
        })
        await store.j2c_save(db, GUILD, {"join_channel_id": "4242424242424242"})
    await cog.refresh(GUILD)
    check("a changed lobby channel is picked up",
          cog.setup_data[GUILD]["join_channel_id"] == 4242424242424242,
          str(cog.setup_data[GUILD]["join_channel_id"]))

    # Live state lives in the database, so a reload must not drop it.
    await cog.save_private_channel(555, GUILD, {
        "owner": ALICE, "limit": 2, "region": "",
        "is_locked": False, "has_waiting_room": False, "has_thread": False,
    })
    await cog.block_user(555, BOB)
    await cog.refresh(GUILD)
    check("an open private channel survives a reload",
          555 in cog.private_channels, str(list(cog.private_channels)))
    check("and so does a block",
          BOB in (cog.blocked_users.get(555) or []),
          str(cog.blocked_users))


async def test_j2c_old_database(store):
    """
    A database from before the extra columns existed must still load.

    This is the upgrade path every existing server takes, and it was
    broken: the cog's SELECT names columns the old table does not have,
    so it raised and the cache stayed empty -- Join to Create dead, with
    the dashboard showing it as set up.
    """
    print("\nJoin to Create: an older database")

    import os

    import aiosqlite

    from cogs.commands.j2c import JoinToCreate

    # Start from a table with only the original five columns.
    if os.path.exists(store.J2C_DB):
        os.remove(store.J2C_DB)
    async with aiosqlite.connect(store.J2C_DB) as db:
        await db.execute(
            """CREATE TABLE guild_setup (
                guild_id INTEGER PRIMARY KEY,
                join_channel_id INTEGER,
                control_channel_id INTEGER,
                control_message_id INTEGER,
                category_id INTEGER)"""
        )
        await db.execute(
            "INSERT INTO guild_setup VALUES (?, ?, ?, ?, ?)",
            (GUILD, CHANNEL_VOICE, CHANNEL_TEXT, None, None),
        )
        await db.commit()

    # Confirm the table really is the old shape, otherwise this test
    # proves nothing -- an earlier test in the same run may already have
    # migrated the file, and then the check below passes for the wrong
    # reason. That is exactly what happened the first time: the
    # mutation removing the migration did not fail anything.
    async with aiosqlite.connect(store.J2C_DB) as db:
        async with db.execute("PRAGMA table_info(guild_setup)") as cursor:
            columns = [row[1] async for row in cursor]
    check("the table really is the pre-migration shape",
          "name_template" not in columns,
          f"{columns} -- this test cannot detect anything otherwise")

    cog = JoinToCreate(FakeBot())
    failed = None
    try:
        await cog.load_data()
    except Exception as err:  # noqa: BLE001
        failed = err

    check("loading an older database does not raise",
          failed is None,
          f"{type(failed).__name__}: {failed} -- the cache then stays "
          "empty and the feature is silently dead")
    check("and the existing setup is still there",
          GUILD in cog.setup_data, str(cog.setup_data))
    if GUILD in cog.setup_data:
        check("with the lobby it was configured with",
              cog.setup_data[GUILD]["join_channel_id"] == CHANNEL_VOICE)
        check("and sensible defaults for the new columns",
              cog.setup_data[GUILD]["name_template"] == "{user}'s VC"
              and cog.setup_data[GUILD]["default_limit"] == 2,
              str(cog.setup_data[GUILD]))

    # The event has to work off that migrated cache. FakeGuild has no
    # channel factory, so the lobby and the creation call are supplied
    # here rather than reaching for real Discord objects.
    created = []

    class Lobby:
        id = CHANNEL_VOICE
        name = "Join to Create"
        category = None
        members = []

    class CreatingGuild(FakeGuild):
        categories = []

        async def create_voice_channel(self, name, **kwargs):
            created.append(name)
            made = Lobby()
            made.id = 998877
            made.name = name
            return made

    guild = CreatingGuild()
    guild._channels[CHANNEL_VOICE] = Lobby()
    member = FakeMember(ALICE)
    member.guild = guild

    await cog.on_voice_state_update(
        member, FakeVoiceState(None), FakeVoiceState(guild._channels[CHANNEL_VOICE])
    )
    check("and a member joining the lobby gets a channel",
          len(created) == 1,
          "nothing was created from a migrated setup")
    if created:
        check("named from the default template",
              created[0].endswith("'s VC"), created[0])


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


async def test_api(store):
    print("\nAPI")

    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient

    guild = FakeGuild()
    guild._roles[ROLE_OK] = FakeRole(ROLE_OK, "In Voice", 5)
    guild._roles[ROLE_HIGH] = FakeRole(ROLE_HIGH, "Zu hoch", 500)
    guild._roles[ROLE_MANAGED] = FakeRole(ROLE_MANAGED, "Bot-Rolle", 3, managed=True)

    import discord

    # The API asks isinstance(channel, discord.VoiceChannel) -- a real
    # check a plain stand-in cannot answer. Registering the fake as a
    # virtual subclass satisfies isinstance without inheriting
    # VoiceChannel's read-only properties, so the test exercises the
    # real branch rather than a weakened copy of it.
    class ApiVoiceChannel(FakeChannel):
        pass

    discord.VoiceChannel.register(ApiVoiceChannel)

    voice = ApiVoiceChannel(CHANNEL_VOICE, "Talk", "voice")
    text = FakeChannel(CHANNEL_TEXT, "chat", "text")
    guild._channels[CHANNEL_VOICE] = voice
    guild._channels[CHANNEL_TEXT] = text

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def __init__(self):
            self.reloaded: list = []
            self.cogs: dict = {}

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            self.reloaded.append(name)
            return self.cogs.get(name)

        def get_command(self, name):
            return "ban" if name == "ban" else None

        def add_view(self, *a, **k):
            pass

    bot = ApiBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/voice/{GUILD}"

    # The store tests above already wrote to these files, so clear
    # anything for this guild first -- a test that only passes when run
    # in a particular order is worse than no test.
    for path, statements in (
        (store.VOICEROLE_DB, ("DELETE FROM vcroles WHERE guild_id = ?",
                              "DELETE FROM vcrole_roles WHERE guild_id = ?",
                              "DELETE FROM vcrole_channels WHERE guild_id = ?")),
        (store.CUSTOMROLE_DB, ("DELETE FROM custom_roles WHERE guild_id = ?",
                               "DELETE FROM roles WHERE guild_id = ?")),
        (store.J2C_DB, ("DELETE FROM guild_setup WHERE guild_id = ?",)),
    ):
        async with aiosqlite.connect(path) as conn:
            for statement in statements:
                try:
                    await conn.execute(statement, (GUILD,))
                except Exception:
                    pass
            await conn.commit()

    # ── Voice roles
    r = client.patch(f"{base}/voicerole", json={"enabled": True, "roles": []})
    check("cannot switch voice roles on with no role",
          r.status_code == 400, r.text[:120])

    r = client.patch(f"{base}/voicerole", json={"roles": [str(ROLE_HIGH)]})
    check("a role above the bot is refused", r.status_code == 400, r.text[:120])

    r = client.patch(f"{base}/voicerole", json={"roles": [str(ROLE_MANAGED)]})
    check("an integration role is refused", r.status_code == 400, r.text[:120])

    bot.reloaded.clear()
    r = client.patch(f"{base}/voicerole",
                     json={"roles": [str(ROLE_OK)], "enabled": True})
    check("a usable role is accepted", r.status_code == 200, r.text[:120])
    check("and the cog is told under its real name",
          "Invcrole" in bot.reloaded, str(bot.reloaded))

    data = client.get(f"{base}/voicerole").json()
    check("ids come back as strings, not rounded numbers",
          data["roles"] == [str(ROLE_OK)], str(data["roles"]))
    check("the switch is reported", data["enabled"] is True)

    client.patch(f"{base}/voicerole", json={"ignore_afk": False})
    data = client.get(f"{base}/voicerole").json()
    check("a partial save keeps the roles",
          data["roles"] == [str(ROLE_OK)] and data["ignore_afk"] is False,
          str(data))

    guild.me.guild_permissions = FakePerms(manage_roles=False)
    warns = client.get(f"{base}/voicerole").json()["warnings"]
    check("a missing permission is reported",
          any("Rollen verwalten" in w for w in warns), str(warns))
    guild.me.guild_permissions = FakePerms()

    # ── Custom roles
    r = client.post(f"{base}/customroles",
                    json={"name": "mit leerzeichen", "role_id": str(ROLE_OK)})
    check("a name with a space is refused", r.status_code == 400, r.text[:120])

    r = client.post(f"{base}/customroles",
                    json={"name": "ban", "role_id": str(ROLE_OK)})
    check("a name the bot already uses is refused",
          r.status_code == 400, r.text[:120])

    r = client.post(f"{base}/customroles",
                    json={"name": "gamer", "role_id": str(ROLE_HIGH)})
    check("a role above the bot is refused here too",
          r.status_code == 400, r.text[:120])

    r = client.post(f"{base}/customroles",
                    json={"name": "gamer", "role_id": str(ROLE_OK)})
    check("a good one is created", r.status_code == 200, r.text[:120])

    r = client.post(f"{base}/customroles",
                    json={"name": "gamer", "role_id": str(ROLE_OK)})
    check("the same name twice is refused", r.status_code == 409, r.text[:120])

    data = client.get(f"{base}/customroles").json()
    check("it shows up with the prefix in front",
          any(e["command"].endswith("gamer") for e in data["entries"]),
          str(data["entries"]))

    r = client.delete(f"{base}/customroles/gamer")
    check("it can be deleted", r.status_code == 200)
    r = client.delete(f"{base}/customroles/gamer")
    check("deleting it twice gives 404", r.status_code == 404)

    # ── Join to Create
    r = client.patch(f"{base}/j2c", json={"join_channel_id": str(CHANNEL_TEXT)})
    check("a text channel is refused as the lobby",
          r.status_code == 400, r.text[:120])

    r = client.patch(f"{base}/j2c", json={"default_limit": 500})
    check("an impossible limit is refused", r.status_code == 400, r.text[:120])

    r = client.patch(f"{base}/j2c", json={"name_template": "   "})
    check("an empty name is refused", r.status_code == 400, r.text[:120])

    bot.reloaded.clear()
    r = client.patch(f"{base}/j2c", json={
        "join_channel_id": str(CHANNEL_VOICE),
        "control_channel_id": str(CHANNEL_TEXT),
        "name_template": "{user} Lounge",
    })
    check("a proper setup is accepted", r.status_code == 200, r.text[:120])
    check("and the cog is told", "JoinToCreate" in bot.reloaded, str(bot.reloaded))

    data = client.get(f"{base}/j2c").json()
    check("it now reports itself as configured", data["configured"] is True)
    check("the preview is rendered", data["preview"] == "Lena Lounge",
          str(data["preview"]))
    check("channel ids stay exact",
          data["join_channel_id"] == str(CHANNEL_VOICE),
          str(data["join_channel_id"]))

    r = client.post(f"{base}/j2c/panel", json={})
    check("posting the panel needs the cog", r.status_code == 503,
          str(r.status_code))

    r = client.post(f"{base}/j2c/reset", json={})
    check("it can be switched off", r.status_code == 200)
    check("and then reads as unconfigured",
          client.get(f"{base}/j2c").json()["configured"] is False)

    r = client.get("/api/v1/voice/999/voicerole")
    check("an unknown guild still answers", r.status_code == 200,
          str(r.status_code))

    await db_manager.close_all()


def test_setup_overview():
    """
    The overview looked for join-to-create in the blacklist database.

    ``db/block.db`` has no ``j2c`` table, so the module was reported as
    "not configured" on every server regardless of the real setup.
    """
    print("\nSetup overview")

    src = open(os.path.join(HERE, "..", "api", "routes", "guilds.py")).read()

    check("join to create points at its own database",
          '("j2c", "Join to Create", "j2c_data.db"' in src)
    check("and no longer at the blacklist database",
          '"block.db", "j2c"' not in src)
    check("voice roles count the per-role table",
          '"invc.db", "vcrole_roles"' in src)
    check("custom roles count the named commands, not the reqrole row",
          '"customrole.db", "custom_roles"' in src)
    check("a database outside db/ can be found at all",
          "os.path.exists(db_file)" in src)


async def run():
    from utils import voice_store as store

    await test_voicerole_store(store)
    test_voicerole_rules(store)
    await test_schema_conflict(store)
    test_schema_guard_matches_store()
    await test_customrole_store(store)
    await test_j2c_store(store)
    await test_voicerole_cog(store)
    await test_customrole_cog(store)
    await test_j2c_cog(store)
    await test_j2c_cache_reload(store)
    await test_j2c_old_database(store)
    await test_api(store)
    test_setup_overview()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        os.makedirs("jsondb", exist_ok=True)
        sys.exit(asyncio.run(run()))
