#!/usr/bin/env python3
"""
The counting game.

The bug that prompted this file: the cog and the dashboard wrote
*different key names into the same JSON file*.

    cog       ->  {"count": 7,  "reset_on_fail": true}
    dashboard ->  {"current": 7, "mode": "reset"}

Neither read the other's keys. Switching counting on in the dashboard
left the cog sitting at 0, and the next correct number in chat wrote the
cog's own keys back over everything the dashboard had saved. On a server
that had ever used the chat commands, the dashboard showed count 0 and a
disabled game no matter what was really configured.

Both sides now go through utils.extras_store, and counting_migrate folds
the old keys in on read.

Also covered here:

  * bot commands typed in the counting channel must not break the streak
  * a message is judged once, under a lock, so two people posting the
    same number in the same instant cannot both be accepted
  * every reply the bot sends is Components V2 (type 17 container) with
    the "> " quote bar, not a legacy embed

Run:  python3 tests/test_counting.py
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

GUILD = 9101
CHANNEL_ID = 1327995167345819721   # a real-length snowflake
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


class FakeAuthor:
    def __init__(self, uid, bot=False):
        self.id = uid
        self.bot = bot
        self.mention = f"<@{uid}>"
        self.display_name = f"User{uid}"


class FakeChannel:
    def __init__(self, cid=CHANNEL_ID):
        self.id = cid
        self.name = "counting"
        self.sent: list = []
        self.mention = f"<#{cid}>"

    async def send(self, content=None, view=None, **kw):
        msg = FakeMessage("", author=FakeAuthor(1, bot=True), channel=self)
        msg.view = view
        self.sent.append(msg)
        return msg


class FakeGuild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test"
        self.me = None


_UNSET = object()


class FakeMessage:
    def __init__(self, content, author=None, channel=None, guild=_UNSET):
        self.content = content
        self.author = author or FakeAuthor(ALICE)
        self.channel = channel or FakeChannel()
        # A sentinel, not `or`: an explicit guild=None means "this is a
        # DM". Defaulting None to a real guild made the DM test pass
        # while actually counting the message.
        self.guild = FakeGuild() if guild is _UNSET else guild
        self.webhook_id = None
        self.reactions: list = []
        self.deleted = False
        self.view = None

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def delete(self):
        self.deleted = True


class FakeBot:
    def __init__(self, prefix=">"):
        self.prefix = prefix

    async def get_prefix(self, message):
        return [self.prefix, "<@1>"]


# ══════════════════════════════════════════════════════════════════════
#  Rules — pure, no Discord
# ══════════════════════════════════════════════════════════════════════


def test_rules(store):
    print("\nRules")

    base = store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 7, "mode": "reset",
    })

    check("the next number is accepted",
          store.counting_judge(base, ALICE, "8")["action"] == "count")

    v = store.counting_judge(base, ALICE, "9")
    check("a number that skips ahead is wrong", v["action"] == "wrong")
    check("and in strict mode it resets", v["reset"] is True)

    lenient = {**base, "mode": "continue"}
    check("in lenient mode a wrong number does not reset",
          store.counting_judge(lenient, ALICE, "9")["reset"] is False)

    # Only a bare number counts. "8!" being accepted would make a typo
    # indistinguishable from chat.
    for text in ("8!", "8 los", "acht", "8.0", "1,000", "-3", ""):
        v = store.counting_judge(base, ALICE, text)
        check(f"{text!r} is not read as a number", v["action"] != "count",
              str(v["action"]))

    check("'+8' works — phone keyboards insert the plus",
          store.counting_judge(base, ALICE, "+8")["action"] == "count")

    check("chat is ignored while allow_chat is on",
          store.counting_judge(base, ALICE, "nice")["action"] == "ignore")
    check("and cleaned up when it is off",
          store.counting_judge({**base, "allow_chat": False}, ALICE, "nice")
          ["action"] == "cleanup")


def test_alternate(store):
    print("\nAlternate rule")

    settings = store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 7,
        "require_alternate": True, "last_user": ALICE,
    })

    v = store.counting_judge(settings, ALICE, "8")
    check("the same person twice is refused", v["action"] == "double")
    check("even though the number itself was right",
          v["expected"] == 8)

    check("someone else may continue",
          store.counting_judge(settings, BOB, "8")["action"] == "count")

    off = {**settings, "require_alternate": False}
    check("with the rule off the same person may go again",
          store.counting_judge(off, ALICE, "8")["action"] == "count")

    # A reset clears last_user; otherwise whoever broke the streak is
    # locked out of restarting it at 1.
    broken = store.counting_save(GUILD, {"current": 7, "last_user": ALICE,
                                         "require_alternate": True})
    verdict = store.counting_judge(broken, ALICE, "99")
    store.counting_apply(GUILD, broken, verdict, ALICE)
    after = store.counting_get(GUILD)
    check("after a reset the last counter is cleared",
          after["last_user"] is None, str(after["last_user"]))
    check("so they can start again at 1",
          store.counting_judge(after, ALICE, "1")["action"] == "count")


def test_split_modes(store):
    print("\nPer-rule punishment")

    settings = store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 7,
        "mode": "reset", "require_alternate": True, "last_user": ALICE,
        "double_post_mode": "continue",
    })

    check("a wrong number still follows the shared strict setting",
          store.counting_judge(settings, BOB, "50")["reset"] is True)
    check("but a double post uses its own lenient setting",
          store.counting_judge(settings, ALICE, "8")["reset"] is False)

    check("effective mode falls back to the shared one",
          store.counting_effective_mode({"mode": "continue"}, "wrong")
          == "continue")


def test_record(store):
    print("\nRecord")

    store.counting_save(GUILD, {"current": 9, "high_score": 5,
                                "last_user": None, "require_alternate": False})
    settings = store.counting_get(GUILD)
    verdict = store.counting_judge(settings, ALICE, "10")
    out = store.counting_apply(GUILD, settings, verdict, ALICE)

    check("passing the old record is reported", out["record"] is True)
    check("and the record is stored", store.counting_get(GUILD)["high_score"] == 10)

    settings = store.counting_get(GUILD)
    verdict = store.counting_judge(settings, ALICE, "11")
    store.counting_apply(GUILD, settings, verdict, ALICE)
    check("a reset does not touch the record",
          store.counting_save(GUILD, {"current": 0})["high_score"] == 11)

    off = store.counting_save(GUILD, {"current": 50, "high_score": 11,
                                      "save_record": False})
    verdict = store.counting_judge(off, ALICE, "51")
    out = store.counting_apply(GUILD, off, verdict, ALICE)
    check("with the record turned off it stops moving",
          out["record"] is False and store.counting_get(GUILD)["high_score"] == 11)


# ══════════════════════════════════════════════════════════════════════
#  The migration — this is the bug
# ══════════════════════════════════════════════════════════════════════


def test_migration(store):
    print("\nLegacy keys (the reported bug)")

    # Exactly what the old cog left behind.
    with open(store.COUNTING_JSON, "w") as fh:
        json.dump({str(GUILD): {
            "enabled": True, "channel": CHANNEL_ID,
            "count": 42, "reset_on_fail": True,
        }}, fh)

    settings = store.counting_get(GUILD)
    check("the old 'count' is read as the current stand",
          settings["current"] == 42, str(settings["current"]))
    check("'reset_on_fail: true' becomes strict mode",
          settings["mode"] == "reset", settings["mode"])
    check("the game is still switched on", settings["enabled"] is True)

    with open(store.COUNTING_JSON, "w") as fh:
        json.dump({str(GUILD): {"count": 3, "reset_on_fail": False}}, fh)
    check("'reset_on_fail: false' becomes lenient mode",
          store.counting_get(GUILD)["mode"] == "continue")

    # And once saved, the stale keys are gone for good.
    store.counting_save(GUILD, {"current": 4})
    on_disk = json.loads(open(store.COUNTING_JSON).read())[str(GUILD)]
    check("the old keys are dropped on save",
          "count" not in on_disk and "reset_on_fail" not in on_disk,
          str(sorted(on_disk)))
    check("without losing the value", on_disk["current"] == 4)


def test_normalise(store):
    print("\nBad input")

    entry = store.counting_save(GUILD, {
        "current": -5, "high_score": -1, "mode": "quatsch",
        "milestone_every": 99999, "channel": "nicht-eine-zahl",
        "wrong_number_mode": "bloedsinn",
    })
    check("a negative count is clamped to 0", entry["current"] == 0)
    check("a negative record is clamped to 0", entry["high_score"] == 0)
    check("an unknown mode falls back to strict", entry["mode"] == "reset")
    check("a silly milestone is capped", entry["milestone_every"] == 10000)
    check("a non-numeric channel becomes empty", entry["channel"] is None)
    check("an unknown per-rule mode becomes 'follow the shared one'",
          entry["wrong_number_mode"] is None)

    entry = store.counting_save(GUILD, {"channel": str(CHANNEL_ID)})
    check("a channel id survives as a full snowflake",
          entry["channel"] == CHANNEL_ID, str(entry["channel"]))

    # An unknown key must not be able to inject itself into the file.
    entry = store.counting_save(GUILD, {"evil": True})
    check("unknown keys are dropped", "evil" not in entry)


def test_atomic_write(store):
    print("\nFile safety")
    store.counting_save(GUILD, {"current": 5})
    leftovers = [f for f in os.listdir("db") if f.endswith(".tmp")]
    check("no temp file is left behind", not leftovers, str(leftovers))


# ══════════════════════════════════════════════════════════════════════
#  The cog
# ══════════════════════════════════════════════════════════════════════


def test_cog(store):
    print("\nCog behaviour")

    from cogs.commands.counting import Counting, quote

    cog = Counting(FakeBot())
    store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 0,
        "mode": "reset", "require_alternate": False, "high_score": 0,
        "last_user": None, "allow_chat": True, "delete_wrong": True,
    })

    channel = FakeChannel()

    def message(text, author_id=ALICE, guild=True):
        return FakeMessage(
            text, author=FakeAuthor(author_id), channel=channel,
            guild=FakeGuild() if guild else None,
        )

    # A DM used to raise AttributeError on message.guild.id.
    dm = message("1", guild=False)
    asyncio.run(cog.on_message(dm))
    check("a DM does not crash the listener", dm.deleted is False)

    msg = message("1")
    asyncio.run(cog.on_message(msg))
    check("a correct number is accepted",
          store.counting_get(GUILD)["current"] == 1)
    check("and gets a reaction", len(msg.reactions) == 1, str(msg.reactions))
    check("and is not deleted", msg.deleted is False)

    # The reported wish: commands must survive in the counting channel.
    # Tested with allow_chat OFF on purpose -- with it on, a command is
    # indistinguishable from chat and the test would pass even without
    # the prefix check.
    store.counting_save(GUILD, {"allow_chat": False})
    cmd = message(">counting stats")
    before = store.counting_get(GUILD)["current"]
    asyncio.run(cog.on_message(cmd))
    check("a bot command survives even in a numbers-only channel",
          cmd.deleted is False)
    check("and does not break the streak",
          store.counting_get(GUILD)["current"] == before)

    mention = message("<@1> counting stats")
    asyncio.run(cog.on_message(mention))
    check("a mention-prefixed command survives too", mention.deleted is False)
    store.counting_save(GUILD, {"allow_chat": True})

    chat = message("gg leute")
    asyncio.run(cog.on_message(chat))
    check("normal chat is left alone while allow_chat is on",
          chat.deleted is False)
    check("and does not break the streak",
          store.counting_get(GUILD)["current"] == before)

    store.counting_save(GUILD, {"allow_chat": False})
    chat2 = message("gg leute")
    asyncio.run(cog.on_message(chat2))
    check("with allow_chat off, chat is removed", chat2.deleted is True)
    check("but the streak still stands",
          store.counting_get(GUILD)["current"] == before)

    store.counting_save(GUILD, {"allow_chat": True})
    wrong = message("99")
    asyncio.run(cog.on_message(wrong))
    check("a wrong number is deleted", wrong.deleted is True)
    check("and the counter resets", store.counting_get(GUILD)["current"] == 0)

    bot_msg = message("1")
    bot_msg.author.bot = True
    asyncio.run(cog.on_message(bot_msg))
    check("the bot ignores itself", store.counting_get(GUILD)["current"] == 0)

    other = FakeMessage("1", author=FakeAuthor(ALICE), channel=FakeChannel(999))
    asyncio.run(cog.on_message(other))
    check("another channel is ignored",
          store.counting_get(GUILD)["current"] == 0)

    store.counting_save(GUILD, {"enabled": False})
    off = message("1")
    asyncio.run(cog.on_message(off))
    check("nothing happens while the game is off",
          store.counting_get(GUILD)["current"] == 0)

    check("the quote helper marks every line",
          quote("a\nb") == "> a\n> b", repr(quote("a\nb")))


def test_race(store):
    print("\nTwo people at once")

    from cogs.commands.counting import Counting

    cog = Counting(FakeBot())
    store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 0,
        "mode": "continue", "require_alternate": False, "allow_chat": True,
        "last_user": None,
    })

    channel = FakeChannel()

    # Reading the count and writing it back is two steps. To prove the
    # lock is what keeps them together, a suspend point is forced
    # between them -- exactly what a future `await` in this path would
    # introduce. Without the lock the second message reads the stale
    # count and both are accepted.
    real_apply = store.counting_apply
    overlaps = {"max": 0, "now": 0}

    import cogs.commands.counting as mod

    class Wrapper:
        """Counts how deep the judge/apply section is entered."""

        def __getattr__(self, name):
            return getattr(store, name)

        @staticmethod
        def counting_apply(guild_id, settings, verdict, author_id):
            overlaps["now"] += 1
            overlaps["max"] = max(overlaps["max"], overlaps["now"])
            result = real_apply(guild_id, settings, verdict, author_id)
            overlaps["now"] -= 1
            return result

    original_store = mod.store
    mod.store = Wrapper()

    a = FakeMessage("1", author=FakeAuthor(ALICE), channel=channel)
    b = FakeMessage("1", author=FakeAuthor(BOB), channel=channel)

    async def both():
        await asyncio.gather(cog.on_message(a), cog.on_message(b))

    try:
        asyncio.run(both())
    finally:
        mod.store = original_store

    accepted = [m for m in (a, b) if not m.deleted]
    check("only one of two simultaneous '1's is accepted",
          len(accepted) == 1, f"{len(accepted)} accepted")
    check("and the counter moved by exactly one",
          store.counting_get(GUILD)["current"] == 1,
          str(store.counting_get(GUILD)["current"]))
    check("the two never ran inside each other",
          overlaps["max"] == 1, f"max overlap {overlaps['max']}")

    # The lock itself: one per guild, shared across messages.
    check("each guild gets its own lock",
          cog._lock(1) is cog._lock(1) and cog._lock(1) is not cog._lock(2))

    # Honest note: today the read-judge-write section contains no
    # `await`, so asyncio cannot suspend inside it and the counter would
    # survive even without the lock. The lock is there so that adding
    # any await later -- a permission fetch, a webhook -- cannot quietly
    # reintroduce a double-accept. Behaviour alone cannot prove that, so
    # the structure is asserted directly.
    import ast as _ast
    import inspect as _inspect

    import textwrap as _textwrap

    # getsource keeps the class indentation and the @listener decorator.
    source = _textwrap.dedent(_inspect.getsource(Counting.on_message))
    body = _ast.parse(source)
    uses_lock = any(
        isinstance(node, _ast.AsyncWith)
        and "_lock" in _ast.dump(node.items[0].context_expr)
        for node in _ast.walk(body)
    )
    check("on_message still runs its judging inside the guild lock",
          uses_lock, "the `async with self._lock(...)` is gone")

    applies_inside_lock = False
    for node in _ast.walk(body):
        if isinstance(node, _ast.AsyncWith) and "_lock" in _ast.dump(
            node.items[0].context_expr
        ):
            applies_inside_lock = any(
                isinstance(inner, _ast.Attribute) and inner.attr == "counting_apply"
                for inner in _ast.walk(node)
            )
    check("and the state is written inside that lock, not outside",
          applies_inside_lock)

    # And with the lock held, a second message must wait.
    async def contention():
        order = []

        async def hold():
            async with cog._lock(GUILD):
                order.append("in")
                await asyncio.sleep(0.02)
                order.append("out")

        async def second():
            await asyncio.sleep(0.005)
            async with cog._lock(GUILD):
                order.append("second")

        await asyncio.gather(hold(), second())
        return order

    order = asyncio.run(contention())
    check("a second message waits for the first",
          order == ["in", "out", "second"], str(order))


def test_components_v2(store):
    print("\nComponents V2")

    from cogs.commands.counting import Counting

    cog = Counting(FakeBot())
    settings = store.counting_save(GUILD, {
        "enabled": True, "channel": CHANNEL_ID, "current": 3,
        "require_alternate": True, "mode": "reset",
    })

    view = cog.rules_view(settings)
    payload = view.to_components()

    check("the rules card is a V2 container",
          payload and payload[0]["type"] == 17, str(payload)[:120])

    texts = [
        c["content"] for c in payload[0]["components"] if c.get("type") == 10
    ]
    check("it has text sections", len(texts) >= 2, str(len(texts)))
    body = [t for t in texts if not t.startswith("**")]
    check("every body line carries the '>' quote bar",
          all(line.startswith("> ")
              for t in body for line in t.split("\n") if line),
          str(body)[:160])

    check("no legacy embed is produced anywhere in the cog",
          "discord.Embed" not in open(
              os.path.join(HERE, "..", "cogs", "commands", "counting.py")).read())

    check("the alternate rule shows up when it is on",
          any("abwechsel" in t.lower() or "hintereinander" in t.lower()
              for t in texts), str(texts)[:200])


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


def test_api(store):
    print("\nAPI")

    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient

    class Perms:
        def __init__(self, ok=True):
            self.view_channel = ok
            self.send_messages = ok
            self.manage_messages = ok
            self.add_reactions = ok

    class ApiChannel(FakeChannel):
        def __init__(self, cid, ok=True):
            super().__init__(cid)
            self._ok = ok

        def permissions_for(self, _member):
            return Perms(self._ok)

    class ApiGuild:
        def __init__(self):
            self.id = GUILD
            self.name = "Test"
            self.me = object()
            self._channels = {CHANNEL_ID: ApiChannel(CHANNEL_ID)}

        def get_channel(self, cid):
            return self._channels.get(int(cid))

        def get_member(self, _uid):
            return None

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def __init__(self):
            self.guild = ApiGuild()
            self.reloaded: list = []
            self.cog = None

        def get_guild(self, gid):
            return self.guild if int(gid) == GUILD else None

        def get_cog(self, name):
            self.reloaded.append(name)
            return self.cog

        def add_view(self, *a, **k):
            pass

    bot = ApiBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/extras/{GUILD}/counting"

    store.counting_save(GUILD, {"enabled": False, "channel": None,
                                "current": 0, "high_score": 0})

    r = client.patch(base, json={"enabled": True})
    check("cannot switch on without a channel", r.status_code == 400,
          r.text[:120])

    r = client.patch(base, json={"channel": str(CHANNEL_ID), "enabled": True})
    check("with a channel it works", r.status_code == 200, r.text[:120])

    data = client.get(base).json()
    check("the channel comes back as a string, not a rounded number",
          data["channel"] == str(CHANNEL_ID), str(data["channel"]))
    check("the next number is reported", data["next_number"] == 1,
          str(data.get("next_number")))

    bot.reloaded.clear()
    client.patch(base, json={"require_alternate": True})
    check("the cog is told to reload under its real name",
          "Counting" in bot.reloaded, str(bot.reloaded))

    data = client.get(base).json()
    check("a partial save keeps the other fields",
          data["enabled"] is True and data["require_alternate"] is True,
          str(data))

    client.patch(base, json={"current": 55})
    data = client.get(base).json()
    check("the count can be set by hand", data["current"] == 55)
    check("and that clears the last counter", data["last_user"] is None)

    r = client.patch(base, json={"current": -1})
    check("a negative count is refused", r.status_code == 400, r.text[:120])
    r = client.patch(base, json={"current": "acht"})
    check("a non-numeric count is refused", r.status_code == 400, r.text[:120])

    store.counting_save(GUILD, {"current": 80, "high_score": 80})
    client.post(f"{base}/reset", json={})
    data = client.get(base).json()
    check("reset zeroes the count", data["current"] == 0)
    check("and keeps the record", data["high_score"] == 80, str(data["high_score"]))

    client.post(f"{base}/reset", json={"keep_record": False})
    check("clearing the record works too",
          client.get(base).json()["high_score"] == 0)

    # Permission warnings
    bot.guild._channels[CHANNEL_ID] = ApiChannel(CHANNEL_ID, ok=False)
    warns = client.get(base).json()["warnings"]
    check("missing write permission is reported",
          any("schreiben" in w for w in warns), str(warns))
    bot.guild._channels[CHANNEL_ID] = ApiChannel(CHANNEL_ID)

    store.counting_save(GUILD, {"channel": 4242, "enabled": True})
    warns = client.get(base).json()["warnings"]
    check("a deleted channel is reported",
          any("nicht mehr" in w for w in warns), str(warns))
    store.counting_save(GUILD, {"channel": CHANNEL_ID})

    # Announce needs the cog present.
    r = client.post(f"{base}/announce", json={})
    check("announce says so when the cog is missing", r.status_code == 503,
          str(r.status_code))

    from cogs.commands.counting import Counting
    bot.cog = Counting(FakeBot())
    r = client.post(f"{base}/announce", json={})
    check("announce posts once the cog is there", r.status_code == 200,
          r.text[:120])
    check("and the card really reached the channel",
          len(bot.guild._channels[CHANNEL_ID].sent) == 1)

    posted = bot.guild._channels[CHANNEL_ID].sent[0].view.to_components()
    check("what it posted is a V2 container", posted[0]["type"] == 17)

    r = client.get("/api/v1/extras/999/counting")
    check("an unknown guild still answers", r.status_code == 200,
          str(r.status_code))

    asyncio.run(db_manager.close_all())


def run():
    from utils import extras_store as store

    test_migration(store)
    test_rules(store)
    test_alternate(store)
    test_split_modes(store)
    test_record(store)
    test_normalise(store)
    test_atomic_write(store)
    test_cog(store)
    test_race(store)
    test_components_v2(store)
    test_api(store)

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
