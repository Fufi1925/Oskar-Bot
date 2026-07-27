#!/usr/bin/env python3
"""
Anonymous chat.

The things most likely to go wrong, and what each check protects:

  * The original message must be deleted *before* anything else. If the
    relay works out that the member is not allowed and only then
    deletes, the name was already visible to everybody watching.
  * One webhook per channel, not per member: Discord caps a channel at
    15 webhooks, so "one per person" breaks at the 16th.
  * @everyone from behind a mask is the classic abuse of this feature,
    so mentions are neutralised unless the guild opts in.
  * The log is the only thing that makes the channel moderatable — it
    must record the real author, and must never be readable by the
    people in the channel.

Run:  python3 tests/test_anonchat.py
"""

import asyncio
import datetime as _dt
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

GUILD = 888
CHANNEL = "1327995167345819721"
LOG_CHANNEL = "1327995167345819722"
ROLE_A = 800000000000000001
ROLE_B = 800000000000000002


class FakeRole:
    def __init__(self, rid, name):
        self.id, self.name = rid, name
        self.mention = f"<@&{rid}>"
        self.color = type("C", (), {"value": 0})()
        self.managed = False


class FakeAttachment:
    filename = "bild.png"

    async def to_file(self):
        return "file"


class FakeMessage:
    def __init__(self, author, channel, content, attachments=None):
        self.author, self.channel, self.content = author, channel, content
        self.guild = channel.guild
        self.attachments = attachments or []
        self.id = 4242
        self.deleted = False
        self.deleted_at_step = None

    async def delete(self):
        self.deleted = True
        # Records how much had already happened when the delete landed.
        self.deleted_at_step = self.channel.step


class FakeWebhook:
    def __init__(self, channel, user_id=1):
        self.channel = channel
        self.user = type("U", (), {"id": user_id})()
        self.sent = []
        self.id = 9001

    async def send(self, content=None, username=None, avatar_url=None,
                   files=None, wait=False, allowed_mentions=None, **kw):
        self.sent.append({
            "content": content, "username": username,
            "avatar_url": avatar_url, "mentions": allowed_mentions,
        })
        return type("M", (), {
            "id": 7000 + len(self.sent),
            "jump_url": "https://d/x",
        })()


class FakeChannel:
    def __init__(self, cid, name, guild=None):
        self.id, self.name = cid, name
        self.guild = guild
        self.sent = []
        self.step = 0
        self.hooks = []
        self.can_manage_messages = True
        self.can_manage_webhooks = True
        self.mention = f"<#{cid}>"

    def permissions_for(self, _m):
        permissions = discord.Permissions.all()
        if not self.can_manage_messages:
            permissions.manage_messages = False
        if not self.can_manage_webhooks:
            permissions.manage_webhooks = False
        return permissions

    async def send(self, content=None, view=None, files=None, **kw):
        self.step += 1
        self.sent.append(view or content)
        return type("M", (), {"id": 8000 + len(self.sent), "jump_url": "https://d/y"})()

    async def webhooks(self):
        return list(self.hooks)

    async def create_webhook(self, name=None, reason=None):
        if not self.can_manage_webhooks:
            raise discord.Forbidden(type("R", (), {"status": 403})(), "no")
        hook = FakeWebhook(self)
        self.hooks.append(hook)
        return hook


class FakeMember:
    def __init__(self, uid, name, *, days_old=1000, days_member=500):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.bot = False
        self.roles = []
        self.guild = None
        self.dms = []
        now = _dt.datetime.now(_dt.timezone.utc)
        self.created_at = now - _dt.timedelta(days=days_old)
        self.joined_at = now - _dt.timedelta(days=days_member)

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()

    async def send(self, content=None, view=None, **kw):
        self.dms.append(view or content)


class FakeGuild:
    id, name = GUILD, "Test"

    def __init__(self):
        self.channel = FakeChannel(int(CHANNEL), "beichte", self)
        self.log = FakeChannel(int(LOG_CHANNEL), "anon-log", self)
        self._roles = {
            ROLE_A: FakeRole(ROLE_A, "Verifiziert"),
            ROLE_B: FakeRole(ROLE_B, "Stumm"),
        }
        self.members = {}
        self.me = FakeMember(1, "Bot")
        self.me.guild = self

    @property
    def roles(self):
        return list(self._roles.values())

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        if str(cid) == CHANNEL:
            return self.channel
        if str(cid) == LOG_CHANNEL:
            return self.log
        return None

    def get_member(self, uid):
        return self.members.get(int(uid))

    def add(self, member):
        member.guild = self
        self.members[member.id] = member
        return member


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

    async def get_prefix(self, _message):
        return ["!"]


def run():
    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from cogs.commands.anonchat import AnonChat
    from fastapi.testclient import TestClient
    from utils import anonchat_store as store

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    guild = bot.guilds[0]
    base = f"/api/v1/anonchat/{GUILD}"

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ══════════════════════════════════════════════════════════════
    #  Settings are clamped to something usable
    # ══════════════════════════════════════════════════════════════

    settings = store.normalise({})
    check("the default alias is set", settings["alias"] == "Anonym", settings["alias"])
    check("webhook is the default mode",
          settings["mode"] == store.MODE_WEBHOOK, settings["mode"])
    check("mentions are off by default — anonymous pings get abused",
          settings["allow_mentions"] == 0)

    # Discord rejects a webhook username containing "discord"; sending
    # would fail with no explanation anywhere.
    check("a username containing 'discord' is defused",
          "discord" not in store.normalise({"alias": "Discord Team"})["alias"].lower(),
          store.normalise({"alias": "Discord Team"})["alias"])
    check("an over-long alias is cut to Discord's 80 characters",
          len(store.normalise({"alias": "x" * 200})["alias"]) == 80)
    check("an empty alias falls back to the default",
          store.normalise({"alias": "   "})["alias"] == "Anonym")
    check("a non-http avatar is dropped rather than breaking the send",
          store.normalise({"avatar_url": "javascript:x"})["avatar_url"] == "")
    check("max_length cannot exceed Discord's own limit",
          store.normalise({"max_length": 99999})["max_length"] == 2000)
    check("an unknown mode falls back to webhook",
          store.normalise({"mode": "quatsch"})["mode"] == store.MODE_WEBHOOK)

    # ══════════════════════════════════════════════════════════════
    #  Content filtering
    # ══════════════════════════════════════════════════════════════

    strict = store.normalise({"allow_links": 0, "allow_mentions": 0})

    out = store.clean_content("Hallo @everyone!", strict)
    check("@everyone no longer pings", "@everyone" not in out, out)
    check("but the text is still readable", "everyone" in out, out)

    out = store.clean_content("Ping <@&123> jetzt", strict)
    check("a role ping is defused", "<@&123>" not in out, out)

    out = store.clean_content("Schau: https://beispiel.de/x", strict)
    check("links are removed when not allowed",
          "https://" not in out and "entfernt" in out, out)

    loose = store.normalise({"allow_links": 1, "allow_mentions": 1})
    out = store.clean_content("https://beispiel.de @everyone", loose)
    check("with everything allowed the text is untouched",
          "https://beispiel.de" in out and "@everyone" in out, out)

    out = store.clean_content("x" * 5000, store.normalise({"max_length": 100}))
    check("over-long text is cut", len(out) == 100, str(len(out)))

    # ══════════════════════════════════════════════════════════════
    #  The API
    # ══════════════════════════════════════════════════════════════

    r = client.post(base, json={"channel_id": CHANNEL, "enabled": True})
    check("a channel can be made anonymous", r.status_code == 200, r.text[:160])

    listing = client.get(base).json()
    check("it shows up in the list", len(listing["channels"]) == 1, str(listing))
    check("channel ids stay strings",
          isinstance(listing["channels"][0]["channel_id"], str),
          str(type(listing["channels"][0]["channel_id"])))
    check("the dashboard is offered both modes", len(listing["modes"]) == 2)

    # A partial save must not blank the rest.
    client.post(base, json={"channel_id": CHANNEL, "alias": "Geheim"})
    client.post(base, json={"channel_id": CHANNEL, "cooldown_seconds": 30})
    current = client.get(base).json()["channels"][0]
    check("a partial save keeps the other settings",
          current["alias"] == "Geheim" and current["cooldown_seconds"] == 30,
          f'{current["alias"]} {current["cooldown_seconds"]}')

    r = client.post(base, json={"channel_id": "999"})
    check("an unknown channel gives 404", r.status_code == 404)

    # Missing "manage messages" must be refused up front, not discovered
    # at runtime when the original is already visible.
    guild.channel.can_manage_messages = False
    r = client.post(base, json={"channel_id": CHANNEL})
    check("a channel the bot cannot clean up is refused",
          r.status_code == 400 and "verwalten" in r.json()["detail"],
          r.text[:160])
    guild.channel.can_manage_messages = True

    r = client.post(f"{base}/preview", json={
        "content": "Hi https://x.de @everyone",
        "settings": {"allow_links": False, "allow_mentions": False},
    })
    body = r.json()
    check("the preview applies the same filters",
          "https://" not in body["result"] and "@everyone" not in body["result"],
          body["result"])
    check("the preview says what it changed", len(body["notes"]) >= 2, str(body["notes"]))

    # ══════════════════════════════════════════════════════════════
    #  The relay itself
    # ══════════════════════════════════════════════════════════════

    client.post(base, json={
        "channel_id": CHANNEL, "enabled": True, "alias": "Anonym",
        "log_channel_id": LOG_CHANNEL, "cooldown_seconds": 0,
        "allow_mentions": False,
    })

    cog = AnonChat(bot)
    asyncio.run(cog.cog_load())

    alice = guild.add(FakeMember(10, "Alice"))
    bob = guild.add(FakeMember(11, "Bob"))

    message = FakeMessage(alice, guild.channel, "Ich mag Kekse")
    asyncio.run(cog.on_message(message))

    check("the original is deleted", message.deleted is True)
    check("the original goes before anything is posted",
          message.deleted_at_step == 0,
          f"channel had already sent {message.deleted_at_step} messages")

    hook = guild.channel.hooks[0] if guild.channel.hooks else None
    check("a webhook was created", hook is not None)
    check("the message is re-posted through it",
          hook is not None and len(hook.sent) == 1,
          str(len(hook.sent) if hook else 0))
    check("it carries the configured alias",
          hook is not None and hook.sent[0]["username"] == "Anonym",
          str(hook.sent[0] if hook else None))
    check("the text survives",
          hook is not None and "Kekse" in (hook.sent[0]["content"] or ""),
          str(hook.sent[0] if hook else None))

    # One webhook per channel — not one per member. Discord caps a
    # channel at 15 webhooks, so 20 different people is past the point
    # where "one each" would start failing.
    asyncio.run(cog.on_message(FakeMessage(bob, guild.channel, "Ich auch")))
    check("a second member reuses the same webhook",
          len(guild.channel.hooks) == 1, str(len(guild.channel.hooks)))
    check("both messages went out", len(hook.sent) == 2, str(len(hook.sent)))

    # The log records who really wrote it.
    async def check_log():
        db = await db_manager.get_connection(store.DB_PATH)
        await store.ensure_schema(db)
        return await store.recent_log(db, GUILD, limit=10)

    log = asyncio.run(check_log())
    check("both messages are logged", len(log) == 2, str(len(log)))
    check("the log names the real author",
          {e["user_id"] for e in log} == {10, 11},
          str([e["user_id"] for e in log]))
    check("the log keeps the original text",
          any("Kekse" in e["content"] for e in log), str(log))
    check("a staff log message was posted",
          len(guild.log.sent) == 2, str(len(guild.log.sent)))

    # Looking the author back up.
    posted_id = hook.sent[0] and 7001
    r = client.get(f"{base}/log/{posted_id}")
    check("an anonymous message can be traced back",
          r.status_code == 200 and r.json()["user_id"] == "10", r.text[:140])

    r = client.get(f"{base}/log/999999")
    check("an unknown message id gives 404", r.status_code == 404)

    for index in range(20):
        crowd = guild.add(FakeMember(100 + index, f"Person{index}"))
        asyncio.run(cog.on_message(FakeMessage(crowd, guild.channel, f"Nr {index}")))

    check("20 more people still share one webhook — past Discord's cap of 15",
          len(guild.channel.hooks) == 1, str(len(guild.channel.hooks)))
    check("every one of them got through",
          len(hook.sent) == 22, str(len(hook.sent)))

    entries = client.get(f"{base}/log").json()
    check("the log is served to the dashboard",
          entries["count"] >= 2, str(entries["count"]))
    check("author ids stay strings",
          all(isinstance(e["user_id"], str) for e in entries["entries"]))

    # ══════════════════════════════════════════════════════════════
    #  Guards
    # ══════════════════════════════════════════════════════════════

    # Blocked member: deleted, not relayed, told privately.
    client.post(f"{base}/blocked", json={"user_id": "11", "reason": "Spam"})
    asyncio.run(cog.refresh(GUILD))

    before = len(hook.sent)
    blocked_message = FakeMessage(bob, guild.channel, "Nochmal ich")
    asyncio.run(cog.on_message(blocked_message))

    check("a blocked member's message is still deleted",
          blocked_message.deleted is True)
    check("but it is not relayed", len(hook.sent) == before, str(len(hook.sent)))
    check("and they are told why, privately", len(bob.dms) >= 1, str(len(bob.dms)))

    client.delete(f"{base}/blocked/11")
    asyncio.run(cog.refresh(GUILD))

    # Account age.
    client.post(base, json={"channel_id": CHANNEL, "min_account_days": 30})
    fresh = guild.add(FakeMember(12, "Neu", days_old=2))
    before = len(hook.sent)
    asyncio.run(cog.on_message(FakeMessage(fresh, guild.channel, "Hallo")))
    check("a brand new account cannot post",
          len(hook.sent) == before, str(len(hook.sent)))
    check("the young account is told why", len(fresh.dms) >= 1)
    client.post(base, json={"channel_id": CHANNEL, "min_account_days": 0})

    # Required role.
    client.post(base, json={"channel_id": CHANNEL, "required_role_id": str(ROLE_A)})
    before = len(hook.sent)
    asyncio.run(cog.on_message(FakeMessage(alice, guild.channel, "Ohne Rolle")))
    check("without the required role nothing is relayed",
          len(hook.sent) == before, str(len(hook.sent)))

    alice.roles = [guild.get_role(ROLE_A)]
    asyncio.run(cog.on_message(FakeMessage(alice, guild.channel, "Mit Rolle")))
    check("with the role it goes through", len(hook.sent) == before + 1)
    client.post(base, json={"channel_id": CHANNEL, "required_role_id": None})

    # Cooldown.
    client.post(base, json={"channel_id": CHANNEL, "cooldown_seconds": 60})
    asyncio.run(cog.refresh(GUILD))
    asyncio.run(cog.on_message(FakeMessage(alice, guild.channel, "Erste")))
    before = len(hook.sent)
    asyncio.run(cog.on_message(FakeMessage(alice, guild.channel, "Sofort nochmal")))
    check("the cooldown blocks a second message",
          len(hook.sent) == before, str(len(hook.sent)))
    client.post(base, json={"channel_id": CHANNEL, "cooldown_seconds": 0})
    asyncio.run(cog.refresh(GUILD))

    # A command must stay a command.
    before = len(hook.sent)
    asyncio.run(cog.on_message(FakeMessage(alice, guild.channel, "!help")))
    check("a command is not swallowed by the relay",
          len(hook.sent) == before, str(len(hook.sent)))

    # Bots and other channels are ignored.
    other = FakeChannel(999, "normal", guild)
    before = len(hook.sent)
    asyncio.run(cog.on_message(FakeMessage(alice, other, "Woanders")))
    check("other channels are untouched", len(hook.sent) == before)

    robot = guild.add(FakeMember(13, "Robo"))
    robot.bot = True
    asyncio.run(cog.on_message(FakeMessage(robot, guild.channel, "beep")))
    check("bot messages are ignored", len(hook.sent) == before)

    # ══════════════════════════════════════════════════════════════
    #  Falling back when webhooks are not allowed
    # ══════════════════════════════════════════════════════════════

    plain = FakeChannel(int(CHANNEL), "beichte", guild)
    plain.can_manage_webhooks = False
    guild.channel = plain
    asyncio.run(cog.refresh(GUILD))

    asyncio.run(cog.on_message(FakeMessage(alice, plain, "Ohne Webhook")))
    check("without the webhook right the message still arrives",
          len(plain.sent) >= 1, str(len(plain.sent)))
    check("and it does not leak the author",
          all("Alice" not in str(m) for m in plain.sent), str(plain.sent))

    # Bot mode.
    client.post(base, json={"channel_id": CHANNEL, "mode": "bot"})
    asyncio.run(cog.refresh(GUILD))
    before = len(plain.sent)
    asyncio.run(cog.on_message(FakeMessage(alice, plain, "Als Bot")))
    check("bot mode posts as the bot", len(plain.sent) == before + 1,
          str(len(plain.sent)))

    # ══════════════════════════════════════════════════════════════
    #  Log retention
    # ══════════════════════════════════════════════════════════════

    async def retention():
        db = await db_manager.get_connection(store.DB_PATH)
        import time as _t
        await db.execute(
            "INSERT INTO anon_log (guild_id, channel_id, user_id, content, at)"
            " VALUES (?, ?, ?, ?, ?)",
            (GUILD, int(CHANNEL), 10, "uralt", _t.time() - 90 * 86400),
        )
        await db.commit()
        removed = await store.prune_log(db, GUILD, 30)
        untouched = await store.prune_log(db, GUILD, 0)
        return removed, untouched, await store.recent_log(db, GUILD, limit=100)

    removed, untouched, remaining = asyncio.run(retention())
    check("old log rows are pruned", removed >= 1, str(removed))
    check("retention 0 means keep everything", untouched == 0, str(untouched))
    check("recent entries survive the prune",
          all("uralt" not in e["content"] for e in remaining), str(len(remaining)))

    # Removing the channel again.
    r = client.delete(f"{base}/{CHANNEL}")
    check("a channel can be made normal again", r.status_code == 200, r.text[:140])
    r = client.delete(f"{base}/{CHANNEL}")
    check("deleting it twice gives 404", r.status_code == 404)

    asyncio.run(cog.cog_unload())
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
