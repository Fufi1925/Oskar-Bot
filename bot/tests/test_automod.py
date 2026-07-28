#!/usr/bin/env python3
"""
Automod.

The tab was wired to nothing at all. Three faults, each reproduced
before it was fixed:

  * **The dashboard and the bot used different names.** The tab saved
    ``anti_spam`` / ``mute``; the cogs looked for ``Anti spam`` /
    ``Mute``. Every switch in the tab wrote a row no listener would ever
    match, so turning a rule on did nothing.

  * **A rule could be switched on but never off.** "Is this rule
    active?" was answered by *whether a punishment row exists*, so the
    only way to disable one was to delete the row -- which the tab could
    not do.

  * **The spam counter was keyed by user, not by user and guild.** Three
    messages on one server plus three on another added up to six, so
    somebody talking normally in two servers the bot shares got muted
    for spam in one of them.

Plus what the six near-identical copies each got wrong on their own: no
guard against direct messages, moderators not exempt, and `except: pass`
around every action so a missing permission looked like the rule simply
being off.

Run:  python3 tests/test_automod.py
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
import discord  # noqa: E402

GUILD = 3301
OTHER = 3302
CHANNEL = 1327995167345819721      # a real-length snowflake
ROLE_OK = 500000000000000001
ALICE = 111

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def forbidden():
    return discord.Forbidden(
        type("R", (), {"status": 403, "reason": "Forbidden"})(), "nope"
    )


# ══════════════════════════════════════════════════════════════════════
#  Fakes
# ══════════════════════════════════════════════════════════════════════


class Perms:
    def __init__(self, ok=True, **kw):
        for key in ("administrator", "manage_messages", "moderate_members",
                    "kick_members", "ban_members", "send_messages"):
            setattr(self, key, kw.get(key, ok))


class Role:
    def __init__(self, rid, name="Rolle"):
        self.id = rid
        self.name = name
        self.color = type("C", (), {"value": 0})()


class Channel:
    def __init__(self, cid=CHANNEL, name="chat"):
        self.id = cid
        self.name = name
        self.mention = f"<#{cid}>"
        self.sent: list = []

    async def send(self, content=None, view=None, **kwargs):
        self.sent.append({"content": content, "view": view})
        return type("M", (), {"id": 1})()


class Member:
    def __init__(self, uid=ALICE, bot=False, roles=(), perms=None):
        self.id = uid
        self.bot = bot
        self.name = f"User{uid}"
        self.display_name = self.name
        self.mention = f"<@{uid}>"
        self.roles = list(roles)
        self.guild_permissions = perms or Perms(False)
        self.actions: list = []
        self.allow = True

    async def edit(self, **kwargs):
        if not self.allow:
            raise forbidden()
        self.actions.append("mute")

    async def kick(self, reason=None):
        if not self.allow:
            raise forbidden()
        self.actions.append("kick")

    async def ban(self, reason=None, delete_message_days=0):
        if not self.allow:
            raise forbidden()
        self.actions.append("ban")


class Guild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test"
        self.owner_id = 999
        self.me = Member(1)
        self.me.guild_permissions = Perms(True)
        self._channels = {}
        self._roles = {}

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_role(self, rid):
        return self._roles.get(int(rid))


class Message:
    def __init__(self, content="", author=None, guild=None, channel=None,
                 mentions=(), role_mentions=(), everyone=False):
        self.content = content
        self.author = author or Member()
        self.guild = guild if guild is not None else Guild()
        self.channel = channel or Channel()
        self.mentions = list(mentions)
        self.role_mentions = list(role_mentions)
        self.mention_everyone = everyone
        self.webhook_id = None
        self.deleted = False

    async def delete(self):
        self.deleted = True


class Bot:
    def __init__(self):
        self.user = type("U", (), {"id": 1})()

    async def wait_until_ready(self):
        return True


# ══════════════════════════════════════════════════════════════════════
#  Naming
# ══════════════════════════════════════════════════════════════════════


def test_naming(store):
    """
    Both spellings have to resolve to the same rule.

    This is the reported bug: the tab wrote one name, the bot read
    another, and nothing in between noticed.
    """
    print("\nRule names")

    for dashboard_name, expected in (
        ("anti_spam", "spam"), ("Anti spam", "spam"), ("spam", "spam"),
        ("anti_caps", "caps"), ("Anti caps", "caps"),
        ("anti_links", "links"), ("Anti link", "links"),
        ("anti_invites", "invites"), ("Anti invites", "invites"),
        ("anti_mentions", "mentions"), ("Anti mass mention", "mentions"),
        ("anti_emoji", "emoji"), ("Anti emoji spam", "emoji"),
    ):
        check(f"{dashboard_name!r} resolves to {expected!r}",
              store.normalise_rule(dashboard_name) == expected,
              str(store.normalise_rule(dashboard_name)))

    check("nonsense resolves to nothing",
          store.normalise_rule("anti_nonsense") is None)
    check("an empty name resolves to nothing",
          store.normalise_rule("") is None)

    # Every rule the store knows must have a legacy name to write, or a
    # server set up over chat silently loses it.
    missing = [k for k in store.RULES if k not in store.LEGACY_EVENTS]
    check("every rule maps back to its legacy event name",
          not missing, str(missing))

    for punishment in store.PUNISHMENTS:
        check(f"{punishment!r} survives normalisation",
              store.normalise_punishment(punishment) == punishment)
    check("an unknown punishment falls back to mute",
          store.normalise_punishment("explode") == "mute")


# ══════════════════════════════════════════════════════════════════════
#  Store
# ══════════════════════════════════════════════════════════════════════


async def test_legacy_adoption(store):
    """A setup made over chat must survive opening the new tab."""
    print("\nAdopting a chat setup")

    if os.path.exists(store.DB_PATH):
        os.remove(store.DB_PATH)

    con = sqlite3.connect(store.DB_PATH)
    con.execute(
        "CREATE TABLE automod (guild_id INTEGER PRIMARY KEY, enabled INTEGER)"
    )
    con.execute(
        "CREATE TABLE automod_punishments"
        " (guild_id INTEGER, event TEXT, punishment TEXT)"
    )
    con.execute("INSERT INTO automod VALUES (?, 1)", (GUILD,))
    con.execute(
        "INSERT INTO automod_punishments VALUES (?, 'Anti spam', 'Mute')", (GUILD,)
    )
    con.execute(
        "INSERT INTO automod_punishments VALUES (?, 'Anti caps', 'Kick')", (GUILD,)
    )
    con.commit()
    con.close()

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        settings = await store.get_settings(db, GUILD)

        check("the master switch is picked up", settings["enabled"] is True)
        check("a configured rule reads as on",
              settings["rules"]["spam"]["enabled"] is True)
        check("with its punishment",
              settings["rules"]["spam"]["punishment"] == "mute")
        check("a second one too",
              settings["rules"]["caps"]["punishment"] == "kick")
        check("a rule never configured stays off",
              settings["rules"]["links"]["enabled"] is False)
        check("and gets its default threshold",
              settings["rules"]["spam"]["threshold"]
              == store.RULES["spam"]["threshold"])
    finally:
        await db.close()


async def test_switching_off(store):
    """
    A rule has to be switchable off again.

    "Enabled" used to mean "a punishment row exists", so the only way to
    turn a rule off was to delete the row -- which nothing did.
    """
    print("\nSwitching a rule off")

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        settings = await store.save_settings(
            db, GUILD, {"rules": {"spam": {"enabled": False}}}
        )
        check("the rule reads as off",
              settings["rules"]["spam"]["enabled"] is False)
        check("and is not active", store.rule_active(settings, "spam") is False)

        # The legacy table has to follow, or a downgrade turns it back on.
        async with db.execute(
            "SELECT event FROM automod_punishments WHERE guild_id = ?", (GUILD,)
        ) as cursor:
            events = [r[0] for r in await cursor.fetchall()]
        check("the legacy row is gone too", "Anti spam" not in events, str(events))
        check("but the other rule is untouched", "Anti caps" in events, str(events))

        settings = await store.save_settings(
            db, GUILD, {"rules": {"spam": {"enabled": True}}}
        )
        check("switching back on works",
              store.rule_active(settings, "spam") is True)

        # The dashboard's own spelling has to work end to end.
        settings = await store.save_settings(
            db, GUILD, {"rules": {"anti_spam": {"punishment": "ban"}}}
        )
        check("the dashboard's spelling reaches the same rule",
              settings["rules"]["spam"]["punishment"] == "ban",
              str(settings["rules"]["spam"]))
        async with db.execute(
            "SELECT punishment FROM automod_punishments"
            " WHERE guild_id = ? AND event = 'Anti spam'",
            (GUILD,),
        ) as cursor:
            row = await cursor.fetchone()
        check("and is written in the form the cogs read",
              row and row[0] == "Ban", str(row))

        # The master switch has to win over everything.
        settings = await store.save_settings(db, GUILD, {"enabled": False})
        check("the master switch disables every rule",
              store.rule_active(settings, "spam") is False)
        check("even though the rule itself is still on",
              settings["rules"]["spam"]["enabled"] is True)
        await store.save_settings(db, GUILD, {"enabled": True})
    finally:
        await db.close()


async def test_partial_and_clamping(store):
    print("\nPartial saves and bad input")

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {
            "rules": {"spam": {"enabled": True, "threshold": 7, "duration": 30}},
            "log_channel": str(CHANNEL),
        })

        await store.save_settings(db, GUILD, {"rules": {"caps": {"enabled": True}}})
        settings = await store.get_settings(db, GUILD)
        check("editing one rule leaves the other alone",
              settings["rules"]["spam"]["threshold"] == 7,
              str(settings["rules"]["spam"]))
        check("and the log channel survives",
              settings["log_channel"] == CHANNEL, str(settings["log_channel"]))
        check("the channel id is not rounded",
              len(str(settings["log_channel"])) == 19,
              str(settings["log_channel"]))

        spec = store.RULES["spam"]
        settings = await store.save_settings(db, GUILD, {
            "rules": {"spam": {"threshold": 9999, "duration": -5}},
        })
        check("an absurd threshold is clamped",
              settings["rules"]["spam"]["threshold"] == spec["threshold_max"],
              str(settings["rules"]["spam"]["threshold"]))
        check("a negative duration is clamped",
              settings["rules"]["spam"]["duration"] >= 1,
              str(settings["rules"]["spam"]["duration"]))

        settings = await store.save_settings(db, GUILD, {
            "rules": {"spam": {"punishment": "explode"}},
        })
        check("an unknown punishment falls back",
              settings["rules"]["spam"]["punishment"] == "mute")

        settings = await store.save_settings(db, GUILD, {
            "rules": {"not_a_rule": {"enabled": True}},
        })
        check("an unknown rule is ignored rather than stored",
              "not_a_rule" not in settings["rules"], str(list(settings["rules"])))

        settings = await store.save_settings(db, GUILD, {
            "ignored_roles": [str(ROLE_OK), "nonsense", None, str(ROLE_OK)],
        })
        check("only real ids are kept, without duplicates",
              settings["ignored_roles"] == [ROLE_OK],
              str(settings["ignored_roles"]))

        settings = await store.save_settings(db, GUILD, {"log_channel": None})
        check("the log channel can be cleared",
              settings["log_channel"] is None)
    finally:
        await db.close()


def test_exemptions(store):
    print("\nWho is exempt")

    settings = {
        "enabled": True,
        "rules": {"spam": {"enabled": True}},
        "ignored_roles": [ROLE_OK],
        "ignored_channels": [CHANNEL],
    }

    check("an ordinary member is not exempt",
          store.is_exempt(settings, channel_id=1, role_ids=[]) is False)
    check("the owner is", store.is_exempt(settings, is_owner=True) is True)
    # Moderators were not exempt before -- only the owner -- so a
    # moderator posting a link got muted by their own bot.
    check("an admin is too", store.is_exempt(settings, is_admin=True) is True)
    check("an ignored role is",
          store.is_exempt(settings, role_ids=[ROLE_OK]) is True)
    check("an ignored channel is",
          store.is_exempt(settings, channel_id=CHANNEL) is True)
    check("another channel is not",
          store.is_exempt(settings, channel_id=42) is False)


def test_spam_tracker(store):
    """
    The counter has to be per guild.

    Keyed on the member alone, three messages here plus three on another
    server the bot shares tripped a five-message threshold.
    """
    print("\nSpam counter (the reported bug)")

    tracker = store.SpamTracker()

    for i in range(3):
        first = tracker.hit(GUILD, ALICE, window=10, now=1000 + i)
    for i in range(3):
        second = tracker.hit(OTHER, ALICE, window=10, now=1003 + i)

    check("each server counts on its own",
          first == 3 and second == 3, f"{first} / {second}")
    check("so neither trips a threshold of five",
          first <= 5 and second <= 5)

    # Real spam still has to be caught.
    tracker = store.SpamTracker()
    for i in range(6):
        count = tracker.hit(GUILD, ALICE, window=10, now=2000 + i * 0.5)
    check("six messages in one server does trip it", count == 6, str(count))

    tracker = store.SpamTracker()
    tracker.hit(GUILD, ALICE, window=10, now=100)
    check("the window expires",
          tracker.hit(GUILD, ALICE, window=10, now=130) == 1)

    tracker.clear(GUILD, ALICE)
    check("clearing resets the count",
          tracker.hit(GUILD, ALICE, window=10, now=131) == 1)

    # Without pruning the dict grows for every member ever seen.
    tracker = store.SpamTracker()
    for user in range(50):
        tracker.hit(GUILD, user, window=10, now=0)
    check("entries accumulate", len(tracker) == 50, str(len(tracker)))
    tracker.prune(older_than=300, now=1000)
    check("and are pruned once stale", len(tracker) == 0, str(len(tracker)))

    tracker.hit(GUILD, ALICE, window=10, now=1000)
    tracker.prune(older_than=300, now=1010)
    check("a fresh entry survives pruning", len(tracker) == 1, str(len(tracker)))


def test_readiness(store):
    print("\nReadiness warnings")

    problems = store.readiness({
        "enabled": True, "rules": {k: {"enabled": False} for k in store.RULES},
    })
    check("automod on with no rules is flagged",
          any("keine einzige Regel" in p for p in problems), str(problems))

    problems = store.readiness({
        "enabled": False,
        "rules": {**{k: {"enabled": False} for k in store.RULES},
                  "spam": {"enabled": True}},
    })
    check("rules on with the master off is flagged",
          any("Hauptschalter" in p for p in problems), str(problems))

    problems = store.readiness({
        "enabled": True,
        "rules": {**{k: {"enabled": False} for k in store.RULES},
                  "spam": {"enabled": True}},
    })
    check("a working setup is quiet", problems == [], str(problems))


# ══════════════════════════════════════════════════════════════════════
#  The cogs
# ══════════════════════════════════════════════════════════════════════


async def test_cog_behaviour(store):
    print("\nThe listeners")

    from cogs.automod.antispam import AntiSpam

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {
            "enabled": True,
            "rules": {"spam": {"enabled": True, "threshold": 3, "window": 10}},
            "ignored_roles": [], "ignored_channels": [], "log_channel": None,
        })
    finally:
        await db.close()

    cog = AntiSpam.__new__(AntiSpam)
    cog.bot = Bot()
    cog.tracker = store.SpamTracker()

    # A direct message: this used to raise AttributeError on guild.id.
    dm = Message("hallo", guild=None)
    await cog.on_message(dm)
    check("a DM does not crash the listener", dm.deleted is False)

    bot_msg = Message("hallo", author=Member(5, bot=True))
    await cog.on_message(bot_msg)
    check("bots are ignored", bot_msg.deleted is False)

    guild = Guild()
    channel = Channel()

    # A moderator must not be punished by their own bot.
    mod = Member(7, perms=Perms(manage_messages=True))
    for _ in range(6):
        msg = Message("spam", author=mod, guild=guild, channel=channel)
        await cog.on_message(msg)
    check("a moderator is never punished", mod.actions == [], str(mod.actions))

    # An ordinary member spamming is.
    cog.tracker = store.SpamTracker()
    member = Member(ALICE, perms=Perms(False))
    last = None
    for _ in range(4):
        last = Message("spam", author=member, guild=guild, channel=channel)
        await cog.on_message(last)
    check("an ordinary member is punished", member.actions == ["mute"],
          str(member.actions))
    check("and the message is deleted", last.deleted is True)

    # After punishing, the counter resets -- otherwise every further
    # message punishes again.
    before = len(member.actions)
    msg = Message("hallo", author=member, guild=guild, channel=channel)
    await cog.on_message(msg)
    check("the counter resets after a punishment",
          len(member.actions) == before, str(member.actions))

    # An ignored channel is off limits.
    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {"ignored_channels": [str(CHANNEL)]})
    finally:
        await db.close()

    cog.tracker = store.SpamTracker()
    quiet = Member(222, perms=Perms(False))
    for _ in range(6):
        await cog.on_message(
            Message("spam", author=quiet, guild=guild, channel=Channel(CHANNEL))
        )
    check("an ignored channel is left alone", quiet.actions == [],
          str(quiet.actions))

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {"ignored_channels": []})
    finally:
        await db.close()

    # The master switch has to stop the listener too.
    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {"enabled": False})
    finally:
        await db.close()

    cog.tracker = store.SpamTracker()
    safe = Member(333, perms=Perms(False))
    for _ in range(6):
        await cog.on_message(
            Message("spam", author=safe, guild=guild, channel=channel)
        )
    check("the master switch stops the listener", safe.actions == [],
          str(safe.actions))


async def test_missing_permission(store):
    """
    A refused punishment must be reported, not swallowed.

    Every module wrapped its actions in `except: pass`, so a missing
    permission was indistinguishable from the rule being switched off.
    """
    print("\nWhen the bot is not allowed")

    guild = Guild()
    channel = Channel()
    member = Member(ALICE, perms=Perms(False))
    member.allow = False          # every action raises Forbidden

    message = Message("spam", author=member, guild=guild, channel=channel)
    settings = {
        "enabled": True,
        "rules": {"spam": {"enabled": True, "punishment": "mute", "duration": 5}},
        "log_channel": None,
    }

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        action = await store.punish(Bot(), message, "spam", settings, "Spam")

    check("a refused punishment reports nothing done", action is None, str(action))
    printed = buffer.getvalue()
    check("and says so on the console",
          "missing permission" in printed, printed[:120])

    member.allow = True
    action = await store.punish(Bot(), message, "spam", settings, "Spam")
    check("a permitted one reports what it did", action is not None, str(action))
    check("naming the duration", "5" in str(action), str(action))


def test_detection_rules():
    """Each module's own detection, without a Discord connection."""
    print("\nDetection")

    import re

    from cogs.automod import anti_emoji_spam, anti_invites, antilink

    # Links: music and reaction GIFs are what people actually share.
    for allowed in ("https://open.spotify.com/track/x",
                    "https://tenor.com/view/x",
                    "https://discord.gg/abc"):
        found = antilink.LINK_PATTERN.findall(allowed)
        kept = [u for u in found if not antilink.ALLOWED_HOSTS.search(u)]
        check(f"{allowed[:30]} is allowed", kept == [], str(kept))

    blocked = "schau mal https://spam-site.example/gewinn"
    found = antilink.LINK_PATTERN.findall(blocked)
    kept = [u for u in found if not antilink.ALLOWED_HOSTS.search(u)]
    check("an unknown link is caught", len(kept) == 1, str(kept))

    check("plain text has no links",
          antilink.LINK_PATTERN.findall("nur text") == [])

    # Invites.
    for invite in ("discord.gg/abcdef", "https://discord.com/invite/xyz",
                   "discord.io/server"):
        check(f"{invite} is recognised as an invite",
              len(anti_invites.INVITE_PATTERN.findall(invite)) == 1, invite)
    check("an ordinary sentence is not an invite",
          anti_invites.INVITE_PATTERN.findall("kommt auf meinen server") == [])

    # Emoji: an accented German sentence must not count as emoji spam.
    german = "Schöne Grüße für die Übung"
    count = len(anti_emoji_spam.CUSTOM_EMOJI.findall(german))
    count += sum(1 for c in german if c in anti_emoji_spam.UNICODE_EMOJI_RANGES)
    check("German text is not emoji spam", count == 0, str(count))

    emojis = "🎉🎉🎉🎉🎉🎉"
    count = sum(1 for c in emojis if c in anti_emoji_spam.UNICODE_EMOJI_RANGES)
    check("six emoji are counted as six", count == 6, str(count))

    custom = "<:party:123456789012345678> <a:wave:987654321098765432>"
    check("custom emoji are counted",
          len(anti_emoji_spam.CUSTOM_EMOJI.findall(custom)) == 2)

    del re


def test_every_module_guards():
    """
    The same guards have to be in all six, not five.

    They were copies of each other, so a fix applied to one and not the
    rest is exactly how they drifted apart in the first place.
    """
    print("\nAll six modules")

    import ast

    folder = os.path.join(HERE, "..", "cogs", "automod")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(folder, name)).read()
        tree = ast.parse(src)

        listener = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message":
                listener = ast.unparse(node)

        check(f"{name}: has an on_message", listener is not None)
        if listener is None:
            continue

        check(f"{name}: guards against DMs",
              "message.guild is None" in listener, listener[:80])
        check(f"{name}: checks the master switch",
              "rule_active" in listener, listener[:80])
        check(f"{name}: honours the exemptions",
              "is_exempt" in listener, listener[:80])
        check(f"{name}: goes through the shared punisher",
              "store.punish" in listener, listener[:80])
        # A bare `except: pass` is what hid the missing permissions.
        check(f"{name}: no blanket except around the action",
              "except Exception:\n            pass" not in src, name)


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


async def test_api(store):
    print("\nAPI")

    import api.dependencies as dep
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient

    guild = Guild()
    guild._roles[ROLE_OK] = Role(ROLE_OK, "Team")
    channel = Channel(CHANNEL, "mod-log")
    guild._channels[CHANNEL] = channel

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            return None

        def add_view(self, *a, **k):
            pass

    dep.set_bot(ApiBot())
    client = TestClient(create_app())
    base = f"/api/v1/automod/{GUILD}"

    if os.path.exists(store.DB_PATH):
        os.remove(store.DB_PATH)

    data = client.get(base).json()
    check("a fresh server reads as off", data["enabled"] is False)
    check("every rule is listed", len(data["rules"]) == len(store.RULES),
          str(len(data["rules"])))
    check("each rule carries its limits",
          all("threshold_min" in r and "threshold_max" in r for r in data["rules"]))
    check("the punishments are advertised",
          set(data["punishments"]) == set(store.PUNISHMENTS),
          str(data["punishments"]))
    check("delete and warn are offered",
          "delete" in data["punishments"] and "warn" in data["punishments"])

    r = client.patch(base, json={"rules": {"nope": {"enabled": True}}})
    check("an unknown rule is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"rules": {"spam": {"punishment": "explode"}}})
    check("an unknown punishment is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"rules": {"spam": {"threshold": -1}}})
    check("a negative threshold is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"rules": {"spam": "nonsense"}})
    check("a malformed rule body is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"log_channel": "999999999999999999"})
    check("an unknown log channel is refused", r.status_code == 404, r.text[:120])

    r = client.patch(base, json={
        "enabled": True,
        "rules": {"anti_spam": {"enabled": True, "punishment": "kick"}},
    })
    check("the dashboard's own spelling is accepted",
          r.status_code == 200, r.text[:140])

    data = client.get(base).json()
    spam = next(r_ for r_ in data["rules"] if r_["key"] == "spam")
    check("and lands on the right rule", spam["enabled"] is True, str(spam))
    check("with the punishment it was given",
          spam["punishment"] == "kick", str(spam))
    check("the active count is reported", data["active_count"] == 1,
          str(data["active_count"]))

    client.patch(base, json={"ignored_roles": [str(ROLE_OK)]})
    data = client.get(base).json()
    check("ids come back as strings, not rounded numbers",
          data["ignored_roles"] == [str(ROLE_OK)], str(data["ignored_roles"]))
    check("with the role's name for display",
          data["ignored_roles_info"][0]["name"] == "Team",
          str(data["ignored_roles_info"]))

    # Warnings
    guild.me.guild_permissions = Perms(True, kick_members=False)
    warns = client.get(base).json()["warnings"]
    check("a missing punishment permission is reported",
          any("kicken" in w for w in warns), str(warns))
    guild.me.guild_permissions = Perms(True)

    client.patch(base, json={"enabled": False})
    warns = client.get(base).json()["warnings"]
    check("rules on with the master off is reported",
          any("Hauptschalter" in w for w in warns), str(warns))

    client.patch(base, json={"enabled": True})
    r = client.post(f"{base}/reset", json={})
    check("it can be switched off", r.status_code == 200)
    data = client.get(base).json()
    check("and is then off", data["enabled"] is False)
    check("but the rules are remembered",
          next(x for x in data["rules"] if x["key"] == "spam")["enabled"] is True)

    client.post(f"{base}/reset", json={"keep_rules": False})
    data = client.get(base).json()
    check("clearing the rules works too",
          all(not x["enabled"] for x in data["rules"]),
          str([x["key"] for x in data["rules"] if x["enabled"]]))

    r = client.get("/api/v1/automod/999999")
    check("an unknown guild still answers", r.status_code == 200,
          str(r.status_code))

    await db_manager.close_all()


async def run():
    from utils import automod_store as store

    test_naming(store)
    await test_legacy_adoption(store)
    await test_switching_off(store)
    await test_partial_and_clamping(store)
    test_exemptions(store)
    test_spam_tracker(store)
    test_readiness(store)
    await test_cog_behaviour(store)
    await test_missing_permission(store)
    test_detection_rules()
    test_every_module_guards()
    await test_api(store)

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
