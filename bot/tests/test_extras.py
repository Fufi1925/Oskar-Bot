#!/usr/bin/env python3
"""
Seven features that worked in chat but had no dashboard.

Two real bugs are pinned down here, both invisible on a single server:

  * **notify** declared `type TEXT NOT NULL UNIQUE` with no guild
    column. Once one server configured "youtube", the insert failed for
    every other server, and all of them read the same row.
  * **counting** holds its whole state in memory, loaded once at
    startup. Anything the dashboard writes is invisible to the cog and
    gets overwritten on its next save.

Plus the one thing nightmode has to get right: the window normally runs
23:00 to 07:00, which crosses midnight — a plain `start <= h < end`
returns False for the entire night.

Run:  python3 tests/test_extras.py
"""

import asyncio
import json
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import discord  # noqa: E402

GUILD = 8001
OTHER = 8002
CHANNEL = "1327995167345819721"
ROLE_OK = 500000000000000001
ROLE_TOO_HIGH = 500000000000000009


def response(status):
    return type("R", (), {"status": status, "reason": "test"})()


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
    def __init__(self, mid):
        self.id = mid
        self.jump_url = f"https://d/{mid}"
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent: list = []
        self.overwrites: dict = {}
        self.can_send = True
        self.can_manage = True
        self.messages: dict = {}

    def permissions_for(self, _m):
        permissions = discord.Permissions.all()
        if not self.can_send:
            permissions.send_messages = False
        if not self.can_manage:
            permissions.manage_messages = False
        return permissions

    def overwrites_for(self, target):
        return self.overwrites.get(
            getattr(target, "id", 0), discord.PermissionOverwrite()
        )

    async def set_permissions(self, target, overwrite=None, reason=None):
        self.overwrites[getattr(target, "id", 0)] = overwrite

    async def send(self, content=None, view=None, **kw):
        if not self.can_send:
            raise discord.Forbidden(response(403), "no")
        self.sent.append(view or content)
        return FakeMessage(3000 + len(self.sent))

    async def fetch_message(self, mid):
        if int(mid) in self.messages:
            return self.messages[int(mid)]
        raise discord.NotFound(response(404), "gone")


class FakeMember:
    def __init__(self, uid, name):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.bot = False

    def __str__(self):
        return self.name

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()


class FakeGuild:
    def __init__(self, gid=GUILD, name="Test"):
        self.id, self.name = gid, name
        self.member_count = 250
        self.premium_subscription_count = 3
        self.premium_tier = 1
        self.channel = FakeChannel(int(CHANNEL), "allgemein")
        self.text_channels = [self.channel]
        self.channels = [self.channel]
        self._roles = {
            ROLE_OK: FakeRole(ROLE_OK, "Booster", 1),
            ROLE_TOO_HIGH: FakeRole(ROLE_TOO_HIGH, "Zu hoch", 99),
        }
        self.members = {}
        self.me = FakeMember(1, "Bot")
        self.me.guild_permissions = discord.Permissions.all()
        self.me.top_role = FakeRole(999, "Bot", 50)
        self.default_role = FakeRole(0, "@everyone", 0)
        self.premium_subscribers: list = []
        self.created_roles: list = []
        self.created_channels: list = []

    @property
    def roles(self):
        return list(self._roles.values())

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == int(cid)), None)

    def get_member(self, uid):
        return self.members.get(int(uid))

    def add(self, member):
        self.members[member.id] = member
        return member

    async def create_role(self, name=None, colour=None, reason=None, **kw):
        role = FakeRole(700000 + len(self.created_roles), name, 2)
        self._roles[role.id] = role
        self.created_roles.append(role)
        return role

    async def create_text_channel(self, name, overwrites=None, reason=None, **kw):
        channel = FakeChannel(800000 + len(self.created_channels), name)
        self.channels.append(channel)
        self.text_channels.append(channel)
        self.created_channels.append(channel)
        return channel


class FakeBot:
    user = type("U", (), {"id": 1, "name": "Bot"})()

    def __init__(self, guilds):
        self.guilds = guilds
        self.reloaded: list = []

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == int(gid)), None)

    def get_cog(self, name):
        # Records which cog the API tried to refresh. A wrong name fails
        # silently, which is the "dashboard saves, Discord ignores it"
        # complaint -- so the tests assert on this.
        self.reloaded.append(name)
        return None

    def add_view(self, *a, **k):
        pass


def run():
    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import extras_store as store

    main = FakeGuild()
    other = FakeGuild(OTHER, "Anderer")
    bot = FakeBot([main, other])
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/extras/{GUILD}"

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ══ Nightmode: the midnight window ════════════════════════════
    night = {"enabled": 1, "start_hour": 23, "end_hour": 7}
    for hour, expected in [
        (22, False), (23, True), (0, True), (3, True),
        (6, True), (7, False), (12, False),
    ]:
        got = store.nightmode_should_be_closed(night, hour)
        check(f"nightmode at {hour:02d}:00 is {'closed' if expected else 'open'}",
              got == expected, f"got {got}")

    day = {"enabled": 1, "start_hour": 9, "end_hour": 17}
    check("a window inside one day also works",
          store.nightmode_should_be_closed(day, 12) is True
          and store.nightmode_should_be_closed(day, 20) is False)
    check("start equal to end never closes",
          store.nightmode_should_be_closed(
              {"enabled": 1, "start_hour": 5, "end_hour": 5}, 5) is False)
    check("switched off never closes",
          store.nightmode_should_be_closed(
              {"enabled": 0, "start_hour": 23, "end_hour": 7}, 2) is False)

    # Birthdays were removed from the bot entirely, so the date
    # validation and the API that used it are gone with them.

    # ══ Notify ════════════════════════════════════════════════════
    # Moved to tests/test_youtube_notify.py. The feature was replaced
    # outright: it used to store a role and channel per "type" and watch
    # members' Discord streaming status; it now subscribes to a YouTube
    # channel by name and polls the public feed. Nothing about the old
    # request shape is left to test here.

    # ══ Counting ══════════════════════════════════════════════════
    counting_base = f"{base}/counting"

    r = client.patch(counting_base, json={"enabled": True})
    check("counting cannot be switched on without a channel",
          r.status_code == 400, r.text[:140])

    r = client.patch(counting_base, json={"channel": CHANNEL, "enabled": True})
    check("with a channel it can", r.status_code == 200, r.text[:140])

    bot.reloaded.clear()
    client.patch(counting_base, json={"mode": "continue"})
    check("the counting cog is told to reload — it caches the whole file",
          "Counting" in bot.reloaded, str(bot.reloaded))

    settings = client.get(counting_base).json()
    check("a partial save keeps the rest",
          settings["enabled"] is True and settings["mode"] == "continue",
          str(settings))

    store.counting_save(GUILD, {"current": 42, "high_score": 42})
    r = client.post(f"{counting_base}/reset", json={})
    check("resetting sets the count to zero",
          client.get(counting_base).json()["current"] == 0)
    check("but keeps the high score",
          client.get(counting_base).json()["high_score"] == 42,
          str(client.get(counting_base).json()["high_score"]))

    # The file on disk is the single source of truth for both sides.
    on_disk = json.loads(open(store.COUNTING_JSON).read())
    check("the state really is written to the file",
          str(GUILD) in on_disk, str(list(on_disk)))

    # ══ Booster ═══════════════════════════════════════════════════
    boost_base = f"{base}/booster"

    config = client.get(boost_base).json()
    check("the boost defaults come back",
          "{user.mention}" in config["boost"]["message"], config["boost"]["message"])
    check("the current boost count is shown",
          config["boost_count"] == 3, str(config["boost_count"]))
    check("placeholders are documented for the editor",
          "{server.boost_count}" in config["placeholders"])

    r = client.patch(boost_base, json={
        "message": "Danke {user.name}!", "channels": [CHANNEL],
    })
    check("the boost message can be changed", r.status_code == 200, r.text[:140])

    after = client.get(boost_base).json()
    check("it was stored", after["boost"]["message"] == "Danke {user.name}!",
          after["boost"]["message"])
    check("channel ids stay strings",
          all(isinstance(c, str) for c in after["boost"]["channel"]),
          str(after["boost"]["channel"]))

    # A partial save must not wipe the rest of the config.
    client.patch(boost_base, json={"autodel": 60})
    after = client.get(boost_base).json()
    check("a partial save keeps the message",
          after["boost"]["message"] == "Danke {user.name}!"
          and after["boost"]["autodel"] == 60,
          str(after["boost"]))

    r = client.patch(boost_base, json={"roles": [str(ROLE_TOO_HIGH)]})
    check("a reward role above the bot is refused with a reason",
          r.status_code == 400 and "Bot" in r.json()["detail"], r.text[:160])

    r = client.patch(boost_base, json={"roles": [str(ROLE_OK)]})
    check("a usable role is accepted", r.status_code == 200, r.text[:140])

    r = client.post(f"{boost_base}/test", json={"channel_id": CHANNEL, "actor": "1"})
    check("the boost message can be previewed", r.status_code == 200, r.text[:140])
    check("the preview reached the channel", len(main.channel.sent) >= 1)

    # ══ Sticky ════════════════════════════════════════════════════
    sticky_base = f"{base}/sticky"

    r = client.post(sticky_base, json={"channel_id": CHANNEL, "message": "Regeln lesen!"})
    check("a sticky message can be set", r.status_code == 200, r.text[:140])

    listing = client.get(sticky_base).json()
    check("it shows up", len(listing["entries"]) == 1, str(listing))
    check("with its channel name",
          listing["entries"][0]["channel_name"] == "allgemein",
          str(listing["entries"][0]))

    r = client.post(sticky_base, json={"channel_id": CHANNEL, "message": ""})
    check("an empty sticky is refused", r.status_code == 400)

    # Without manage_messages the old copy would pile up.
    main.channel.can_manage = False
    r = client.post(sticky_base, json={"channel_id": CHANNEL, "message": "x"})
    check("a channel where the bot cannot clean up is refused",
          r.status_code == 403 and "verwalten" in r.json()["detail"], r.text[:160])
    main.channel.can_manage = True

    r = client.delete(f"{sticky_base}/{CHANNEL}")
    check("a sticky can be removed", r.status_code == 200)
    r = client.delete(f"{sticky_base}/{CHANNEL}")
    check("removing it twice gives 404", r.status_code == 404)

    # ══ Nightmode API ═════════════════════════════════════════════
    night_base = f"{base}/nightmode"

    r = client.patch(night_base, json={"enabled": True})
    check("nightmode cannot be switched on with no channels",
          r.status_code == 400, r.text[:140])

    r = client.patch(night_base, json={
        "enabled": True, "channels": [CHANNEL], "start_hour": 22, "end_hour": 6,
    })
    check("with channels it can", r.status_code == 200, r.text[:140])

    settings = client.get(night_base).json()
    check("the hours are stored",
          settings["start_hour"] == 22 and settings["end_hour"] == 6,
          str(settings))
    check("channel ids stay strings",
          all(isinstance(c, str) for c in settings["channels"]))

    r = client.post(f"{night_base}/toggle", json={"close": True})
    check("channels can be closed right now", r.status_code == 200, r.text[:140])
    overwrite = main.channel.overwrites.get(0)
    check("the everyone role really loses send_messages",
          overwrite is not None and overwrite.send_messages is False,
          str(overwrite.send_messages if overwrite else None))

    r = client.post(f"{night_base}/toggle", json={"close": False})
    overwrite = main.channel.overwrites.get(0)
    check("opening clears the override instead of forcing it on",
          overwrite is not None and overwrite.send_messages is None,
          "forcing True would grant writing where a role had denied it")

    # ══ Jail ══════════════════════════════════════════════════════
    jail_base = f"{base}/jail"

    state = client.get(jail_base).json()
    check("jail starts unconfigured", state["configured"] is False)

    r = client.patch(jail_base, json={"jail_role": str(ROLE_TOO_HIGH)})
    check("a jail role above the bot is refused",
          r.status_code == 400 and "Bot" in r.json()["detail"], r.text[:160])

    r = client.post(f"{jail_base}/setup", json={})
    check("the jail can be set up in one call", r.status_code == 200, r.text[:160])
    check("a role was created", len(main.created_roles) == 1,
          str(len(main.created_roles)))
    check("a channel was created", len(main.created_channels) == 1)
    check("the role is denied everywhere",
          len(main.channel.overwrites) >= 1, str(len(main.channel.overwrites)))

    state = client.get(jail_base).json()
    check("it is configured afterwards", state["configured"] is True, str(state))
    check("role ids stay strings",
          isinstance(state["jail_role"]["id"], str), str(state["jail_role"]))

    # ══ Every write reaches the cog ═══════════════════════════════
    #
    # A refresh call to a cog name that does not exist fails silently --
    # settings are saved and Discord never notices. These are the real
    # class names, checked against the running bot.
    expected = {
        "Booster": lambda: client.patch(boost_base, json={"autodel": 5}),
        "StickyMessage": lambda: client.post(
            sticky_base, json={"channel_id": CHANNEL, "message": "x"}),
        "Nightmode": lambda: client.patch(night_base, json={"start_hour": 21}),
        "Jail": lambda: client.patch(jail_base, json={"log_channel": CHANNEL}),
        "Counting": lambda: client.patch(counting_base, json={"mode": "reset"}),
        # Birthdays used to be in this list. The feature was removed.
    }
    for cog_name, call in expected.items():
        bot.reloaded.clear()
        call()
        check(f"saving notifies the {cog_name} cog",
              cog_name in bot.reloaded,
              f"tried {bot.reloaded} — a wrong name fails silently")

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
