#!/usr/bin/env python3
"""
Vanity roles and admin broadcasts.

What these pin down:

  Vanity — the old cog polled `/api/v10/invites/<code>` every fifteen
  seconds and, if the invite existed, gave the role to *every member of
  the guild*, removing it from everyone again the moment a request
  failed. It also stored the trigger exactly as typed, so `.gg/Oskar`
  and `discord.gg/oskar` were two separate setups.

  Broadcast — the dashboard tab called "Global Broadcast" wrote the
  dashboard's own banner and sent nothing to Discord. The route that did
  send had no interface and reported its result with print().

Run:  python3 tests/test_vanity_broadcast.py
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

import discord  # noqa: E402

GUILD = 555
OTHER_GUILD = 556
CHANNEL = "1327995167345819721"
ROLE_OK = 700000000000000001
ROLE_TOO_HIGH = 700000000000000009


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


class FakeActivity:
    def __init__(self, name=None, state=None, details=None):
        self.name, self.state, self.details = name, state, details


class FakeMember:
    def __init__(self, uid, name, status_text=""):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.bot = False
        self.roles = []
        self.guild = None
        self.dms = []
        self.activities = [FakeActivity(state=status_text)] if status_text else []
        self.dm_fails = False

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()

    @property
    def top_role(self):
        return max(self.roles, key=lambda r: r.position) if self.roles else FakeRole(0, "@e", 0)

    @property
    def guild_permissions(self):
        return discord.Permissions.all()

    async def add_roles(self, *roles, reason=None):
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]

    async def send(self, content=None, view=None, **kw):
        if self.dm_fails:
            raise discord.Forbidden(type("R", (), {"status": 403})(), "closed")
        self.dms.append(view or content)


class FakeChannel:
    def __init__(self, cid, name, writable=True):
        self.id, self.name = cid, name
        self.writable = writable
        self.sent = []

    def permissions_for(self, _m):
        return discord.Permissions.all() if self.writable else discord.Permissions.none()

    async def send(self, content=None, view=None, **kw):
        if not self.writable:
            raise discord.Forbidden(type("R", (), {"status": 403})(), "no")
        self.sent.append(view or content)
        return type("M", (), {"id": 1, "jump_url": "https://d/1"})()


class FakeGuild:
    def __init__(self, gid=GUILD, name="Test", writable=True):
        self.id, self.name = gid, name
        self.system_channel = FakeChannel(int(CHANNEL), "allgemein", writable)
        self.text_channels = [self.system_channel]
        self._roles = {
            ROLE_OK: FakeRole(ROLE_OK, "Werber", 1),
            ROLE_TOO_HIGH: FakeRole(ROLE_TOO_HIGH, "Zu hoch", 99),
        }
        self.members = []
        self.me = FakeMember(1, "Bot")
        self.me.guild = self
        self.me.roles = [FakeRole(999, "Bot", 50)]
        self.owner = FakeMember(2, "Inhaber")
        self.owner.guild = self

    @property
    def roles(self):
        return list(self._roles.values())

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return self.system_channel if str(cid) == CHANNEL else None

    def get_member(self, uid):
        return next((m for m in self.members if m.id == int(uid)), None)

    def add_member(self, member):
        member.guild = self
        self.members.append(member)
        return member


class FakeIntents:
    presences = True


class FakeBot:
    user = type("U", (), {"name": "Bot", "id": 1})()
    intents = FakeIntents()

    def __init__(self, guilds=None):
        self.guilds = guilds or [FakeGuild()]

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == int(gid)), None)

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import broadcast_store as bstore
    from utils import vanity_store as vstore

    main_guild = FakeGuild()
    silent_guild = FakeGuild(OTHER_GUILD, "Stumm", writable=False)
    bot = FakeBot([main_guild, silent_guild])
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
    #  Vanity: normalising the trigger
    # ══════════════════════════════════════════════════════════════

    same = {
        vstore.normalise_trigger(raw)
        for raw in [
            ".gg/oskar", ".gg/Oskar", "discord.gg/oskar",
            "https://discord.gg/oskar", "https://discord.com/invite/oskar/",
            "OSKAR", "oskar?ref=x", "  oskar  ",
        ]
    }
    check("every way of writing the trigger becomes the same thing",
          same == {"oskar"}, str(same))
    check("an empty trigger stays empty", vstore.normalise_trigger("  ") == "")

    # ══════════════════════════════════════════════════════════════
    #  Vanity: matching a status
    # ══════════════════════════════════════════════════════════════

    cases = [
        ("spiele auf .gg/oskar", True, "the usual way people write it"),
        ("discord.gg/oskar komm rein!", True, "full domain"),
        ("https://discord.gg/oskar", True, "with the protocol"),
        ("oskar", True, "the bare code"),
        ("OSKAR IST TOP", True, "shouting still counts"),
        ("oskarina", False, "a longer word must not match"),
        ("meinoskar", False, "nor a word ending in it"),
        ("oskar-2", False, "nor one with a suffix"),
        ("nichts hier", False, "unrelated text"),
        ("", False, "an empty status"),
    ]
    for text, want, why in cases:
        got = vstore.matches("oskar", text.lower())
        check(f"status matching: {why}", got == want, f"{text!r} -> {got}")

    check("an empty trigger never matches",
          vstore.matches("", "irgendwas") is False)

    # Text is collected from every activity slot, not just the custom one.
    member = FakeMember(10, "Alice")
    member.activities = [
        FakeActivity(name="Visual Studio Code"),
        FakeActivity(state="komm auf .gg/oskar"),
    ]
    text = vstore.status_text(member)
    check("the status text covers every activity",
          "oskar" in text and "visual studio code" in text, text)

    # ══════════════════════════════════════════════════════════════
    #  Vanity: the API
    # ══════════════════════════════════════════════════════════════

    base = f"/api/v1/vanity/{GUILD}"

    r = client.post(base, json={"vanity": ".gg/Oskar", "role_id": str(ROLE_OK)})
    check("a setup can be created", r.status_code == 200, r.text[:140])

    listing = client.get(base).json()
    check("it is stored under the normalised trigger",
          listing["setups"][0]["vanity"] == "oskar", str(listing["setups"][0]))
    check("the dashboard gets it pre-formatted",
          listing["setups"][0]["display"] == ".gg/oskar",
          listing["setups"][0]["display"])
    check("role ids come back as strings",
          isinstance(listing["setups"][0]["role_id"], str),
          str(type(listing["setups"][0]["role_id"])))
    check("the presence intent is reported",
          listing["presence_intent"] is True)

    # Writing the same trigger differently must update, not duplicate.
    client.post(base, json={"vanity": "discord.gg/OSKAR", "role_id": str(ROLE_OK)})
    listing = client.get(base).json()
    check("re-adding the same trigger written differently does not duplicate it",
          len(listing["setups"]) == 1, str(len(listing["setups"])))

    r = client.post(base, json={"vanity": ".gg/x", "role_id": str(ROLE_TOO_HIGH)})
    check("a role above the bot is refused with a reason",
          r.status_code == 400 and "Bot" in r.json()["detail"], r.text[:160])

    r = client.post(base, json={"vanity": "", "role_id": str(ROLE_OK)})
    check("an empty trigger is rejected", r.status_code == 400)

    r = client.post(base, json={"vanity": ".gg/y", "role_id": "nope"})
    check("a missing role is rejected", r.status_code == 400)

    # The tester answers without touching anybody.
    r = client.post(f"{base}/oskar/test", json={"status": "zocke auf .gg/oskar"})
    check("the tester says yes to a matching status",
          r.json()["matches"] is True, r.text[:120])
    r = client.post(f"{base}/oskar/test", json={"status": "oskarina"})
    check("the tester says no to a near miss",
          r.json()["matches"] is False, r.text[:120])

    # ══════════════════════════════════════════════════════════════
    #  Vanity: syncing real members
    # ══════════════════════════════════════════════════════════════

    advertiser = main_guild.add_member(FakeMember(10, "Alice", "komm auf .gg/oskar"))
    bystander = main_guild.add_member(FakeMember(11, "Bob", "nichts"))
    manual = main_guild.add_member(FakeMember(12, "Carol", "nichts"))
    # Carol was given the role by hand; the bot must never take it away.
    manual.roles.append(main_guild.get_role(ROLE_OK))

    r = client.post(f"{base}/oskar/sync", json={})
    check("a sync runs", r.status_code == 200, r.text[:140])
    body = r.json()
    check("only the advertiser gets the role", body["granted"] == 1, str(body))

    role = main_guild.get_role(ROLE_OK)
    check("the advertiser has the role", role in advertiser.roles)
    check("somebody without the trigger does not", role not in bystander.roles)
    check("a role given by hand is left alone", role in manual.roles,
          "the bot removed a role it never granted")

    # Taking the trigger back out.
    advertiser.activities = [FakeActivity(state="nichts mehr")]
    r = client.post(f"{base}/oskar/sync", json={})
    check("removing the trigger takes the role back",
          role not in advertiser.roles, str(r.json()))
    check("the manual holder still keeps it", role in manual.roles)

    holders = client.get(f"{base}/oskar/holders").json()
    check("the holder list is empty again", holders["count"] == 0, str(holders))

    # Counters survive.
    listing = client.get(base).json()
    check("granting is counted", listing["setups"][0]["granted_total"] >= 1,
          str(listing["setups"][0]))
    check("removing is counted", listing["setups"][0]["removed_total"] >= 1,
          str(listing["setups"][0]))

    r = client.delete(f"{base}/oskar")
    check("a setup can be deleted", r.status_code == 200, r.text[:120])
    r = client.delete(f"{base}/oskar")
    check("deleting it twice gives 404", r.status_code == 404)

    # ══════════════════════════════════════════════════════════════
    #  Broadcast
    # ══════════════════════════════════════════════════════════════

    admin = "/api/v1/admin/broadcast"

    r = client.post(admin, json={"message": ""})
    check("an empty broadcast is refused", r.status_code == 400, str(r.status_code))

    # Preview must not send and must not stay in the history.
    before = len(client.get(admin).json()["broadcasts"])
    r = client.post(f"{admin}/preview", json={"message": "Hallo Welt"})
    plan = r.json()
    check("a preview works", r.status_code == 200, r.text[:140])
    check("the preview covers every guild", plan["guilds"] == 2, str(plan))
    check("it marks the guild with no writable channel",
          plan["reachable"] == 1, str(plan))
    check("previewing sends nothing",
          len(main_guild.system_channel.sent) == 0,
          str(main_guild.system_channel.sent))
    check("a preview leaves no trace in the history",
          len(client.get(admin).json()["broadcasts"]) == before)

    # Test to one server only.
    r = client.post(f"{admin}/test", json={
        "message": "Nur ein Test", "guild_id": str(GUILD),
    })
    check("a test can go to a single server", r.status_code == 200, r.text[:140])
    check("the test really arrives", len(main_guild.system_channel.sent) == 1,
          str(len(main_guild.system_channel.sent)))
    check("the other server is untouched",
          len(silent_guild.system_channel.sent) == 0)

    r = client.post(f"{admin}/test", json={"message": "x", "guild_id": "999"})
    check("testing against an unknown server gives 404", r.status_code == 404)

    # The real thing.
    r = client.post(admin, json={
        "title": "Wartung", "message": "Sonntag ab 10 Uhr.", "tone": "warning",
    })
    body = r.json()
    check("a broadcast is sent", r.status_code == 200, r.text[:160])
    check("it reports how many were reached", body["delivered"] == 1, str(body))
    check("it reports the failures too", body["failed"] == 1, str(body))
    check("the message reached the writable guild",
          len(main_guild.system_channel.sent) == 2,
          str(len(main_guild.system_channel.sent)))

    detail = client.get(f"{admin}/{body['id']}").json()
    check("every guild is listed with its outcome",
          len(detail["results"]) == 2, str(detail["results"]))
    check("the failure carries a reason",
          any(not r["ok"] and r["detail"] for r in detail["results"]),
          str(detail["results"]))
    check("guild ids stay strings",
          all(isinstance(r["guild_id"], str) for r in detail["results"]))

    # Retry only what failed.
    r = client.post(f"{admin}/{body['id']}/resend", json={})
    check("failures can be retried on their own", r.status_code == 200, r.text[:140])
    check("the retry only touched the failing guild",
          r.json()["guilds"] == 1, str(r.json()))

    # Nothing to retry.
    r = client.post(f"{admin}/999999/resend", json={})
    check("retrying an unknown broadcast gives 404", r.status_code == 404)

    # DM delivery.
    main_guild.system_channel.writable = False
    r = client.post(admin, json={"message": "An die Inhaber", "target": "owner"})
    check("a broadcast can go to the owners instead",
          r.status_code == 200 and r.json()["delivered"] >= 1, r.text[:160])
    check("the owner received a DM", len(main_guild.owner.dms) >= 1,
          str(len(main_guild.owner.dms)))
    main_guild.system_channel.writable = True

    # Closed DMs must not count as a crash.
    main_guild.owner.dm_fails = True
    r = client.post(admin, json={"message": "Zu", "target": "owner"})
    check("closed DMs are reported, not raised",
          r.status_code == 200 and r.json()["failed"] >= 1, r.text[:160])
    main_guild.owner.dm_fails = False

    # Scheduling.
    import time as _time

    future = int(_time.time()) + 3600
    r = client.post(admin, json={"message": "Später", "send_at": future})
    check("a broadcast can be scheduled",
          r.status_code == 200 and r.json().get("scheduled") is True, r.text[:140])
    scheduled_id = r.json()["id"]

    check("nothing was sent yet",
          all(b["status"] != "sent" or b["id"] != scheduled_id
              for b in client.get(admin).json()["broadcasts"]))

    r = client.post(f"{admin}/{scheduled_id}/cancel", json={})
    check("a scheduled broadcast can be called back",
          r.status_code == 200, r.text[:140])
    r = client.post(f"{admin}/{scheduled_id}/cancel", json={})
    check("cancelling it twice is refused", r.status_code == 400)

    r = client.post(admin, json={"message": "x", "send_at": 1000})
    check("a time in the past is refused", r.status_code == 400, str(r.status_code))

    # The scheduler picks up what is due.
    async def due_check():
        db = await db_manager.get_connection(bstore.DB_PATH)
        await bstore.ensure_schema(db)
        fields = bstore.clean({"message": "fällig"})
        bid = await bstore.create(db, fields, send_at=int(_time.time()) - 5)
        due = await bstore.due(db)
        found = any(d and d["id"] == bid for d in due)
        result = await bstore.deliver(bot, db, bid)
        after = await bstore.get(db, bid)
        return found, result, after["status"]

    found, result, status = asyncio.run(due_check())
    check("a due broadcast is picked up by the scheduler", found)
    check("the scheduler delivers it", result["delivered"] >= 1, str(result))
    check("it is marked as sent afterwards", status == "sent", status)

    # Channel choice: prefer somewhere sensible.
    guild = FakeGuild(777, "Kanaltest")
    guild.system_channel = None
    guild.text_channels = [
        FakeChannel(1, "logs"),
        FakeChannel(2, "ankündigungen"),
        FakeChannel(3, "spam"),
    ]
    picked = bstore.pick_channel(guild)
    check("an announcement channel is preferred over a log channel",
          picked is not None and picked.name == "ankündigungen",
          picked.name if picked else "None")

    guild.text_channels = [FakeChannel(1, "logs", writable=False)]
    check("a guild with nowhere to post returns nothing",
          bstore.pick_channel(guild) is None)

    # db_manager keeps its connections and aiosqlite's worker thread is
    # not a daemon; without this the process never exits.
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
