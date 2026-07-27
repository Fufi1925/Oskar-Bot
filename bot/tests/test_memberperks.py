#!/usr/bin/env python3
"""
Join DM, no-prefix and reaction roles.

The three bugs this pins down, all of which shipped:

  * **No-prefix leaked between servers.** The `np` table has no guild
    column, so every guild's dashboard showed the same global list — and
    pressing Save on one server ran `DELETE FROM np WHERE id NOT IN (…)`
    and wiped what another server had granted.
  * **Join DM was off after every restart.** `joindm enable` registered
    a listener at runtime instead of storing a flag, so after each
    deploy the feature was silently dead while the dashboard still
    showed the configured text. Running it twice sent the DM twice.
  * **Reaction roles never got their reaction.** The chat command calls
    `message.add_reaction(...)`; the API route only wrote a row, so an
    entry made in the dashboard left members nothing to click.

Run:  python3 tests/test_memberperks.py
"""

import asyncio
import datetime as _dt
import os
import sys
import tempfile
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import discord  # noqa: E402

GUILD = 7001
OTHER_GUILD = 7002
CHANNEL = "1327995167345819721"
ROLE_OK = 600000000000000001
ROLE_TOO_HIGH = 600000000000000009


def response(status):
    return type("R", (), {"status": status, "reason": "test"})()


class FakeRole:
    def __init__(self, rid, name, position=1, managed=False, default=False):
        self.id, self.name, self.position = rid, name, position
        self.managed = managed
        self._default = default
        self.color = type("C", (), {"value": 0x5865F2})()
        self.mention = f"<@&{rid}>"
        self.members: list = []

    def is_default(self):
        return self._default

    def __lt__(self, other):
        return self.position < other.position

    def __ge__(self, other):
        return self.position >= other.position


class FakeReaction:
    def __init__(self, emoji):
        self.emoji = emoji


class FakeMessage:
    def __init__(self, mid, channel):
        self.id, self.channel = mid, channel
        self.jump_url = f"https://d/{mid}"
        self.reactions: list = []
        self.rejects: set = set()

    async def add_reaction(self, emoji):
        if emoji in self.rejects:
            raise discord.HTTPException(response(400), "unknown emoji")
        self.reactions.append(FakeReaction(emoji))

    async def clear_reaction(self, emoji):
        self.reactions = [r for r in self.reactions if str(r.emoji) != emoji]


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.messages: dict = {}
        self.readable = True

    def permissions_for(self, _m):
        return discord.Permissions.all()

    async def fetch_message(self, mid):
        if not self.readable:
            raise discord.Forbidden(response(403), "no")
        if int(mid) in self.messages:
            return self.messages[int(mid)]
        raise discord.NotFound(response(404), "gone")

    async def send(self, **kw):
        return FakeMessage(1, self)


class FakeMember:
    def __init__(self, uid, name, days_old=1000):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.bot = False
        self.guild = None
        self.dms: list = []
        self.dms_closed = False
        self.created_at = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days_old)

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()

    async def send(self, content=None, view=None, **kw):
        if self.dms_closed:
            raise discord.Forbidden(response(403), "closed")
        self.dms.append(view or content)


class FakeGuild:
    def __init__(self, gid=GUILD, name="Test"):
        self.id, self.name = gid, name
        self.member_count = 100
        self.channel = FakeChannel(int(CHANNEL), "allgemein")
        self.text_channels = [self.channel]
        self._roles = {
            ROLE_OK: FakeRole(ROLE_OK, "Mitglied", 1),
            ROLE_TOO_HIGH: FakeRole(ROLE_TOO_HIGH, "Zu hoch", 99),
            0: FakeRole(0, "@everyone", 0, default=True),
        }
        self.members: dict = {}
        self.me = type("Me", (), {
            "guild_permissions": discord.Permissions.all(),
            "top_role": FakeRole(999, "Bot", 50),
        })()
        self.owner = None

    @property
    def roles(self):
        return list(self._roles.values())

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return self.channel if str(cid) == CHANNEL else None

    def get_member(self, uid):
        return self.members.get(int(uid))

    def add(self, member):
        member.guild = self
        self.members[member.id] = member
        return member


class FakeBot:
    user = type("U", (), {"id": 1, "name": "Bot"})()

    def __init__(self, guilds):
        self.guilds = guilds
        self.invalidated = 0

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == int(gid)), None)

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass

    def invalidate_no_prefix_cache(self):
        self.invalidated += 1


def run():
    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import joindm_store as joindm
    from utils import noprefix_store as noprefix

    main = FakeGuild()
    other = FakeGuild(OTHER_GUILD, "Anderer Server")
    bot = FakeBot([main, other])
    dep.set_bot(bot)
    client = TestClient(create_app())

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ══════════════════════════════════════════════════════════════
    #  No prefix — the cross-server bug
    # ══════════════════════════════════════════════════════════════

    base = f"/api/v1/perks/{GUILD}/noprefix"
    other_base = f"/api/v1/perks/{OTHER_GUILD}/noprefix"

    alice = main.add(FakeMember(10, "Alice"))
    bob = main.add(FakeMember(11, "Bob"))
    carol = other.add(FakeMember(12, "Carol"))

    r = client.post(f"{base}/users", json={"user_id": "10"})
    check("a member can be granted no-prefix", r.status_code == 200, r.text[:140])
    client.post(f"{base}/users", json={"user_id": "11"})

    r = client.post(f"{other_base}/users", json={"user_id": "12"})
    check("another server can grant its own", r.status_code == 200, r.text[:140])

    ours = client.get(base).json()
    theirs = client.get(other_base).json()

    check("our server sees exactly its own two",
          {u["user_id"] for u in ours["users"]} == {"10", "11"},
          str([u["user_id"] for u in ours["users"]]))
    check("the other server does not see ours",
          {u["user_id"] for u in theirs["users"]} == {"12"},
          str([u["user_id"] for u in theirs["users"]]))

    # The exact failure that shipped: saving on one guild wiped another.
    client.post(f"{other_base}/users", json={"user_id": "12"})
    still = client.get(base).json()
    check("saving on another server does not wipe ours",
          {u["user_id"] for u in still["users"]} == {"10", "11"},
          str([u["user_id"] for u in still["users"]]))

    # And a foreign entry cannot be removed from here.
    r = client.delete(f"{base}/users/12")
    check("we cannot delete another server's entry",
          r.status_code == 404, str(r.status_code))
    check("it really is still there",
          len(client.get(other_base).json()["users"]) == 1)

    check("ids come back as strings",
          all(isinstance(u["user_id"], str) for u in ours["users"]))
    check("names are resolved",
          any(u["name"] == "Alice" for u in ours["users"]), str(ours["users"]))

    r = client.delete(f"{base}/users/10")
    check("our own entry can be removed", r.status_code == 200)
    check("the bot cache is invalidated on every change", bot.invalidated >= 1,
          str(bot.invalidated))

    # Legacy rows really are global and stay visible everywhere.
    async def seed_legacy():
        db = await db_manager.get_connection(noprefix.DB_PATH)
        await noprefix.ensure_schema(db)
        await db.execute(
            "INSERT OR REPLACE INTO np (id, expiry_time, guild_id)"
            " VALUES (?, NULL, ?)",
            (55, noprefix.GLOBAL_GUILD),
        )
        await db.commit()

    asyncio.run(seed_legacy())
    ours = client.get(base).json()
    theirs = client.get(other_base).json()
    check("a legacy global entry shows on every server",
          any(u["user_id"] == "55" for u in ours["users"])
          and any(u["user_id"] == "55" for u in theirs["users"]),
          "migration must not quietly revoke existing access")
    check("and it is marked as global",
          next(u for u in ours["users"] if u["user_id"] == "55")["global"] is True)
    check("the dashboard is told a global entry exists", ours["has_global"] is True)

    # Removing a global one takes an explicit scope.
    r = client.delete(f"{base}/users/55")
    check("a global entry is not removed by a normal delete", r.status_code == 404)
    r = client.delete(f"{base}/users/55?scope=global")
    check("but can be removed deliberately", r.status_code == 200, r.text[:120])

    # Roles
    r = client.post(f"{base}/roles", json={"role_id": str(ROLE_OK)})
    check("a role can be granted no-prefix", r.status_code == 200, r.text[:140])
    r = client.post(f"{base}/roles", json={"role_id": "0"})
    check("@everyone is refused with a reason",
          r.status_code == 400 and "everyone" in r.json()["detail"], r.text[:140])

    listing = client.get(base).json()
    check("roles come back with their name",
          listing["roles"] and listing["roles"][0]["name"] == "Mitglied",
          str(listing["roles"]))

    r = client.delete(f"{base}/roles/{ROLE_OK}")
    check("a role can be removed", r.status_code == 200)

    # Expiry
    r = client.post(f"{base}/users", json={"user_id": "11", "days": 7})
    entry = next(u for u in client.get(base).json()["users"] if u["user_id"] == "11")
    check("a time limit is stored", entry["expires_at"] is not None, str(entry))
    check("and it is not already expired", entry["expired"] is False, str(entry))

    async def expire():
        db = await db_manager.get_connection(noprefix.DB_PATH)
        await db.execute(
            "UPDATE np SET expiry_time = ? WHERE id = 11", (str(time.time() - 100),)
        )
        await db.commit()
        return await noprefix.purge_expired(db)

    check("expired entries are purged", asyncio.run(expire()) == 1)

    # ══════════════════════════════════════════════════════════════
    #  Join DM
    # ══════════════════════════════════════════════════════════════

    dm_base = f"/api/v1/perks/{GUILD}/joindm"

    settings = client.get(dm_base).json()
    check("join dm starts switched off", settings["enabled"] is False)
    check("the placeholders are documented for the editor",
          "user_name" in settings["placeholders"], str(settings["placeholders"])[:60])

    # Turning it on with no text would look like it works and send
    # nothing — the exact shape of the old bug.
    r = client.patch(dm_base, json={"enabled": True, "message": ""})
    check("it cannot be switched on without a message",
          r.status_code == 400, r.text[:140])

    r = client.patch(dm_base, json={"message": "Hallo {user_name} auf {server}!"})
    check("a message can be saved", r.status_code == 200, r.text[:140])
    r = client.patch(dm_base, json={"enabled": True})
    check("now it can be switched on", r.status_code == 200, r.text[:140])

    # A partial save must not blank the rest.
    client.patch(dm_base, json={"title": "Willkommen!"})
    now = client.get(dm_base).json()
    check("a partial save keeps the other fields",
          now["message"].startswith("Hallo") and now["enabled"] is True,
          f'{now["message"]!r} {now["enabled"]}')

    check("the colour is offered as hex too",
          now["colour_hex"].startswith("#"), now["colour_hex"])

    r = client.patch(dm_base, json={"colour_hex": "#ff0000"})
    check("a hex colour is accepted",
          client.get(dm_base).json()["colour"] == 0xFF0000,
          hex(client.get(dm_base).json()["colour"]))
    r = client.patch(dm_base, json={"colour_hex": "quatsch"})
    check("a broken colour is rejected", r.status_code == 400)

    # Placeholders
    filled = joindm.fill("Hi {user_name}, willkommen auf {server}", alice, main)
    check("placeholders are replaced",
          filled == "Hi Alice, willkommen auf Test", filled)
    check("an unknown placeholder is left alone",
          "{gibtsnicht}" in joindm.fill("{gibtsnicht}", alice, main))

    # Test send
    r = client.post(f"{dm_base}/test", json={"actor": "10"})
    check("a test DM can be sent", r.status_code == 200, r.text[:140])
    check("it really arrived", len(alice.dms) == 1, str(len(alice.dms)))

    alice.dms_closed = True
    r = client.post(f"{dm_base}/test", json={"actor": "10"})
    check("closed DMs are explained, not a stack trace",
          r.status_code == 403 and "DMs" in r.json()["detail"], r.text[:140])
    alice.dms_closed = False

    # An unsaved draft can be tried without saving first.
    r = client.post(f"{dm_base}/test", json={
        "actor": "10", "message": "Entwurf {user_name}",
    })
    check("an unsaved draft can be previewed", r.status_code == 200, r.text[:140])
    check("previewing a draft does not save it",
          client.get(dm_base).json()["message"].startswith("Hallo"),
          client.get(dm_base).json()["message"])

    # The guard rails
    young = main.add(FakeMember(20, "Neu", days_old=1))
    blocked = joindm.may_send(
        joindm.normalise({"enabled": 1, "message": "x", "min_account_days": 30}), young
    )
    check("a brand new account can be skipped", blocked is not None, str(blocked))
    check("the reason names the requirement", "30" in str(blocked), str(blocked))

    check("a bot never gets a join DM",
          joindm.may_send(
              joindm.normalise({"enabled": 1, "message": "x"}),
              type("B", (), {"bot": True, "created_at": None})(),
          ) is not None)

    check("nothing is sent when it is switched off",
          joindm.may_send(joindm.normalise({"enabled": 0, "message": "x"}), alice)
          is not None)

    # The flag has to persist — that is the whole fix.
    async def reload_check():
        db = await db_manager.get_connection(joindm.DB_PATH)
        await joindm.ensure_schema(db)
        return await joindm.all_enabled(db)

    check("the enabled flag survives a reload, unlike the old listener",
          GUILD in asyncio.run(reload_check()))

    # ══════════════════════════════════════════════════════════════
    #  Reaction roles
    # ══════════════════════════════════════════════════════════════

    rr_base = f"/api/v1/perks/{GUILD}/reactionroles"
    message = FakeMessage(9001, main.channel)
    main.channel.messages[9001] = message

    r = client.post(rr_base, json={
        "channel_id": CHANNEL, "message_id": "9001",
        "emoji": "🎉", "role_id": str(ROLE_OK),
    })
    check("a reaction role can be added", r.status_code == 200, r.text[:160])

    # The bug: the old route stored a row and never reacted.
    check("the reaction is actually put on the message",
          len(message.reactions) == 1, str(len(message.reactions)))
    check("and it is the right emoji",
          str(message.reactions[0].emoji) == "🎉", str(message.reactions[0].emoji))

    listing = client.get(rr_base).json()
    check("entries are grouped by message",
          len(listing["messages"]) == 1, str(listing["messages"]))
    check("the role name is resolved",
          listing["messages"][0]["entries"][0]["role_name"] == "Mitglied",
          str(listing["messages"][0]))
    check("ids stay strings",
          isinstance(listing["messages"][0]["message_id"], str))

    r = client.post(rr_base, json={
        "channel_id": CHANNEL, "message_id": "9001",
        "emoji": "🎉", "role_id": str(ROLE_OK),
    })
    check("the same emoji twice on one message is refused",
          r.status_code == 400 and "schon" in r.json()["detail"], r.text[:140])

    r = client.post(rr_base, json={
        "channel_id": CHANNEL, "message_id": "9001",
        "emoji": "⭐", "role_id": str(ROLE_TOO_HIGH),
    })
    check("a role above the bot is refused with a reason",
          r.status_code == 400 and "Bot" in r.json()["detail"], r.text[:160])
    check("and no reaction was added for it",
          len(message.reactions) == 1, str(len(message.reactions)))

    r = client.post(rr_base, json={
        "channel_id": CHANNEL, "message_id": "9999",
        "emoji": "⭐", "role_id": str(ROLE_OK),
    })
    check("a missing message gives 404", r.status_code == 404, str(r.status_code))

    # An emoji Discord will not accept must not leave a dead row behind.
    message.rejects.add("nope")
    before = client.get(rr_base).json()["total"]
    r = client.post(rr_base, json={
        "channel_id": CHANNEL, "message_id": "9001",
        "emoji": "nope", "role_id": str(ROLE_OK),
    })
    check("an emoji Discord rejects is reported", r.status_code == 400, r.text[:140])
    check("and no row was stored for it",
          client.get(rr_base).json()["total"] == before,
          str(client.get(rr_base).json()["total"]))

    # Verify finds a cleared reaction and puts it back.
    message.reactions.clear()
    r = client.post(f"{rr_base}/verify", json={})
    body = r.json()
    check("verify runs", r.status_code == 200, r.text[:140])
    check("it notices the missing reaction and restores it",
          body["repaired"] == 1, str(body))
    check("the reaction is back", len(message.reactions) == 1)

    # A deleted role is reported rather than silently ignored.
    del main._roles[ROLE_OK]
    body = client.post(f"{rr_base}/verify", json={}).json()
    check("a deleted role is reported as a problem",
          any("gelöscht" in p for p in body["problems"]), str(body["problems"]))
    main._roles[ROLE_OK] = FakeRole(ROLE_OK, "Mitglied", 1)

    r = client.delete(
        f"{rr_base}?message_id=9001&emoji=%F0%9F%8E%89&channel_id={CHANNEL}"
    )
    check("an entry can be removed", r.status_code == 200, r.text[:140])
    check("the reaction is cleared too, not left inviting clicks",
          len(message.reactions) == 0, str(len(message.reactions)))

    r = client.patch(rr_base, json={"dm_enabled": False})
    check("the DM setting can be changed", r.status_code == 200)
    check("and it sticks", client.get(rr_base).json()["dm_enabled"] is False)

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
