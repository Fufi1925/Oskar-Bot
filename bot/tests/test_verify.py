#!/usr/bin/env python3
"""
Verification.

The tab could set five things -- channel, role, log channel, method and
an on/off switch -- and nothing else. Every word the bot said during
verification was hard-coded English inside the cog, and the direct
messages could not be turned off.

Real bugs pinned down here, each reproduced before it was fixed:

  * **on_message had no DM guard.** It read ``message.guild.id``
    immediately, so every direct message the bot received raised
    AttributeError before the handler could return.

  * **The API stored 0 for "not set".** ``verification_channel_id or 0``
    writes the id 0, which is neither null nor a channel; the read side
    then handed ``"0"`` back to the dashboard as a real snowflake.

  * **A save from the dashboard wiped a chat setup.** The INSERT branch
    defaulted every column it was not given, so the first save dropped
    whatever ``verification setup`` had configured.

  * **panel_restore rendered its own panel** with the English strings
    baked in, so restoring after a backup silently replaced the
    server's own texts.

Run:  python3 tests/test_verify.py
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

GUILD = 4401
CHANNEL = 1327995167345819721      # a real-length snowflake
ROLE_OK = 500000000000000001
ROLE_HIGH = 500000000000000002
ROLE_MANAGED = 500000000000000003
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
        for key in ("manage_roles", "send_messages", "manage_messages",
                    "view_channel", "administrator", "read_message_history"):
            setattr(self, key, kw.get(key, ok))


class Role:
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

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Role) and other.id == self.id


class Channel:
    def __init__(self, cid=CHANNEL, name="verify", ok=True):
        self.id = cid
        self.name = name
        self.sent: list = []
        self._ok = ok
        self.guild = None

    def permissions_for(self, _member):
        return Perms(self._ok)

    async def send(self, content=None, view=None, **kwargs):
        self.sent.append({"content": content, "view": view})
        return type("M", (), {"id": 900, "edit": self._edit})()

    async def _edit(self, **kwargs):
        pass


class Member:
    def __init__(self, uid=ALICE, roles=None, bot=False, perms=None,
                 created_days=400):
        from datetime import datetime, timedelta, timezone

        self.id = uid
        self.bot = bot
        self.name = f"User{uid}"
        self.display_name = self.name
        self.mention = f"<@{uid}>"
        self.roles = list(roles or [])
        self.guild_permissions = perms or Perms()
        self.created_at = (
            datetime.now(timezone.utc) - timedelta(days=created_days)
        )
        self.dms: list = []
        self.added: list = []

    async def add_roles(self, *roles, reason=None):
        self.added.extend(roles)
        self.roles.extend(roles)

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]

    async def send(self, **kwargs):
        self.dms.append(kwargs)


class Guild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test Server"
        self.member_count = 1204
        self.me = Member(1)
        self._roles = {}
        self._channels = {}
        self._members = {}

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_member(self, uid):
        return self._members.get(int(uid))


# ══════════════════════════════════════════════════════════════════════
#  Store
# ══════════════════════════════════════════════════════════════════════


async def test_migration(store):
    """
    The table on every running server has only the original columns.

    schema_guard's CREATE TABLE IF NOT EXISTS would leave that shape in
    place, so the new columns are added with ALTER -- the same mismatch
    that made custom_roles raise "no such column" in production.
    """
    print("\nMigrating the old table")

    path = store.DB_PATH
    if os.path.exists(path):
        os.remove(path)

    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE verification_config ("
        " guild_id INTEGER PRIMARY KEY,"
        " verification_channel_id INTEGER NOT NULL,"
        " verified_role_id INTEGER NOT NULL,"
        " log_channel_id INTEGER,"
        " verification_method TEXT DEFAULT 'both',"
        " enabled BOOLEAN DEFAULT 1,"
        " created_at TEXT)"
    )
    con.execute(
        "INSERT INTO verification_config VALUES (?,?,?,?,?,?,?)",
        (GUILD, CHANNEL, ROLE_OK, 0, "both", 1, ""),
    )
    con.commit()
    con.close()

    db = await aiosqlite.connect(path)
    try:
        settings = await store.get_settings(db, GUILD)

        check("the existing setup survives",
              settings["verification_channel_id"] == CHANNEL,
              str(settings["verification_channel_id"]))
        check("the channel id is not rounded",
              len(str(settings["verification_channel_id"])) == 19,
              str(settings["verification_channel_id"]))
        check("it is still switched on", settings["enabled"] is True)

        # The old API wrote 0 for an unset channel.
        check("a stored 0 is read as 'not set'",
              settings["log_channel_id"] is None,
              str(settings["log_channel_id"]))

        check("the new text fields get their defaults",
              settings["panel_title"] == store.DEFAULTS["panel_title"],
              settings["panel_title"])
        check("the success DM starts switched off",
              settings["dm_on_success"] is False)
        check("and the extra rules start off",
              settings["min_account_age_days"] == 0)
    finally:
        await db.close()


async def test_partial_save(store):
    """A save must not drop the fields it was not given."""
    print("\nPartial saves")

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {
            "verification_channel_id": str(CHANNEL),
            "verified_role_id": str(ROLE_OK),
            "enabled": True,
        })

        # This is what the old INSERT branch destroyed.
        await store.save_settings(db, GUILD, {"panel_title": "Mein Titel"})
        settings = await store.get_settings(db, GUILD)

        check("the new title is stored", settings["panel_title"] == "Mein Titel")
        check("the channel survives",
              settings["verification_channel_id"] == CHANNEL,
              str(settings["verification_channel_id"]))
        check("the role survives", settings["verified_role_id"] == ROLE_OK)
        check("the switch survives", settings["enabled"] is True)

        await store.save_settings(db, GUILD, {"dm_on_success": True})
        settings = await store.get_settings(db, GUILD)
        check("and so does the title after another save",
              settings["panel_title"] == "Mein Titel")

        # An empty text falls back rather than shipping a blank panel.
        settings = await store.save_settings(db, GUILD, {"panel_title": "   "})
        check("an empty title falls back to the default",
              settings["panel_title"] == store.DEFAULTS["panel_title"],
              settings["panel_title"])

        # Junk must not reach Discord.
        settings = await store.save_settings(db, GUILD, {
            "verification_method": "quatsch",
            "min_account_age_days": -5,
            "button_label": "x" * 200,
        })
        check("an unknown method falls back to 'both'",
              settings["verification_method"] == "both")
        check("a negative age is clamped",
              settings["min_account_age_days"] == 0)
        check("a long button label is cut to Discord's 80",
              len(settings["button_label"]) == 80,
              str(len(settings["button_label"])))

        settings = await store.save_settings(db, GUILD, {"evil": True})
        check("unknown keys are dropped", "evil" not in settings)
    finally:
        await db.close()


def test_rendering(store):
    print("\nPlaceholders")

    out = store.render(
        "Hallo {user} auf {server}, du bekommst {role}. ({member_count})",
        server="Mein Server", user_mention="@Lena", user_name="Lena",
        role="@Verifiziert", member_count=1204,
    )
    check("every placeholder is filled in",
          out == "Hallo @Lena auf Mein Server, du bekommst @Verifiziert. (1204)",
          out)

    check("{user.name} is the plain name",
          store.render("{user.name}", user_mention="@Lena", user_name="Lena")
          == "Lena")

    # A typo would otherwise ship literal braces to Discord.
    check("a typo is reported",
          store.unknown_placeholders("Hallo {username}") == ["{username}"])
    check("correct ones are not",
          store.unknown_placeholders("Hallo {user} auf {server}") == [])
    check("empty text is fine", store.render("", server="x") == "")


def test_rules(store):
    print("\nRules")

    check("the age gate is off at 0",
          store.account_too_young({"min_account_age_days": 0}, 0) is False)
    check("a three-day account fails a seven-day rule",
          store.account_too_young({"min_account_age_days": 7}, 3) is True)
    check("a ten-day account passes it",
          store.account_too_young({"min_account_age_days": 7}, 10) is False)
    check("exactly the minimum passes",
          store.account_too_young({"min_account_age_days": 7}, 7) is False)

    check("'button' offers one button",
          store.methods_for({"verification_method": "button"}) == ["button"])
    check("'captcha' offers one button",
          store.methods_for({"verification_method": "captcha"}) == ["captcha"])
    check("'both' offers two",
          store.methods_for({"verification_method": "both"})
          == ["button", "captcha"])

    check("a channel alone is not configured",
          store.is_configured({"verification_channel_id": CHANNEL}) is False)
    check("a channel and a role are",
          store.is_configured({
              "verification_channel_id": CHANNEL, "verified_role_id": ROLE_OK,
          }) is True)

    print("\nReadiness warnings")
    problems = store.readiness({
        **store.DEFAULTS, "enabled": True,
        "verification_channel_id": None, "verified_role_id": None,
    })
    check("switching on without a channel is flagged",
          any("Kanal" in p for p in problems), str(problems))
    check("and without a role", any("Rolle" in p for p in problems), str(problems))

    problems = store.readiness({
        **store.DEFAULTS, "panel_text": "Hallo {username}",
    })
    check("a bad placeholder is flagged",
          any("{username}" in p for p in problems), str(problems))

    problems = store.readiness({
        **store.DEFAULTS, "remove_unverified_role": True,
        "unverified_role_id": None,
    })
    check("a pointless setting is called out",
          any("Unverifiziert" in p for p in problems), str(problems))


# ══════════════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════════════


async def test_dm_crash(store):
    """on_message read message.guild.id with no None check."""
    print("\nDirect messages to the bot")

    from cogs.commands.verification import Verification

    cog = Verification.__new__(Verification)
    cog.bot = type("B", (), {})()

    guild = Guild()
    channel = Channel()
    channel.guild = guild

    message = type("M", (), {})()
    message.guild = None                      # a DM
    message.author = Member(ALICE)
    message.author.bot = False
    message.channel = channel
    message.content = "hallo"

    deleted = []
    message.delete = lambda: deleted.append(1)

    # The handler wraps everything in a broad `except` that logs and
    # moves on, so the AttributeError never reaches the caller -- the
    # first version of this test passed against the bug because it only
    # checked that nothing was deleted. The log is the only evidence.
    import logging

    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    # The cog logs to the "discord" logger, not a module-named one.
    logger = logging.getLogger("discord")
    handler = Catch()
    logger.addHandler(handler)
    try:
        await cog.on_message(message)
    finally:
        logger.removeHandler(handler)

    check("a DM does not raise", deleted == [])
    check("and does not even hit the error handler",
          not any("NoneType" in r for r in records), str(records))
    check("nothing is deleted", deleted == [])


async def test_message_cleanup(store):
    print("\nCleaning the verification channel")

    from cogs.commands.verification import Verification

    cog = Verification.__new__(Verification)
    cog.bot = type("B", (), {})()

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {
            "enabled": True,
            "verification_channel_id": str(CHANNEL),
            "verified_role_id": str(ROLE_OK),
            "delete_messages": True,
            "dm_on_delete": True,
        })
    finally:
        await db.close()

    guild = Guild()
    channel = Channel()
    channel.guild = guild

    def message(author, channel_id=CHANNEL):
        msg = type("M", (), {})()
        msg.guild = guild
        msg.author = author
        msg.channel = Channel(channel_id)
        msg.content = "hallo"
        msg.deleted = False

        async def delete():
            msg.deleted = True

        msg.delete = delete
        return msg

    member = Member(ALICE, perms=Perms(manage_messages=False))
    msg = message(member)
    await cog.on_message(msg)
    check("a normal message is removed", msg.deleted is True)
    check("and the person is told why", len(member.dms) == 1, str(member.dms))

    # Moderators are left alone.
    mod = Member(222, perms=Perms(manage_messages=True))
    msg = message(mod)
    await cog.on_message(msg)
    check("a moderator is left alone", msg.deleted is False)

    # Another channel is none of its business.
    other = Member(333, perms=Perms(manage_messages=False))
    msg = message(other, channel_id=999)
    await cog.on_message(msg)
    check("another channel is untouched", msg.deleted is False)

    # The DM can be switched off without switching off the cleanup.
    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {"dm_on_delete": False})
    finally:
        await db.close()

    quiet = Member(444, perms=Perms(manage_messages=False))
    msg = message(quiet)
    await cog.on_message(msg)
    check("with the DM off it still deletes", msg.deleted is True)
    check("but says nothing", quiet.dms == [], str(quiet.dms))

    # And the cleanup itself can be switched off.
    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {"delete_messages": False})
    finally:
        await db.close()

    kept = Member(555, perms=Perms(manage_messages=False))
    msg = message(kept)
    await cog.on_message(msg)
    check("with cleanup off nothing is deleted", msg.deleted is False)

    db = await aiosqlite.connect(store.DB_PATH)
    try:
        await store.save_settings(db, GUILD, {
            "delete_messages": True, "dm_on_delete": True,
        })
    finally:
        await db.close()


def test_panel_rendering(store):
    print("\nThe panel")

    from cogs.commands.verification import Verification

    cog = Verification.__new__(Verification)
    cog.bot = type("B", (), {"add_view": lambda *a, **k: None})()

    guild = Guild()
    role = Role(ROLE_OK, "Verifiziert", 5)

    settings = store.normalise({
        **store.DEFAULTS,
        "panel_title": "Willkommen bei {server}",
        "panel_text": "Klick unten, {user} bekommt {role}.",
        "panel_footer": "Wir sind {member_count} Leute.",
        "button_label": "Los geht's",
        "verification_method": "button",
    })

    view = cog.build_panel(guild, settings, role, preview=True)
    payload = view.to_components()

    check("it is a Components V2 container", payload[0]["type"] == 17,
          str(payload[0]["type"]))

    texts = [
        c["content"] for c in payload[0]["components"] if c.get("type") == 10
    ]
    joined = " ".join(texts)
    check("the server name is filled in", "Test Server" in joined, joined[:120])
    check("the role is filled in", "@Verifiziert" in joined, joined[:160])
    check("the member count is filled in", "1204" in joined, joined[:160])
    check("no raw placeholder survives", "{" not in joined, joined[:160])

    # Each configured text has to appear in its own right. Checking only
    # that *some* placeholder resolved let a hard-coded body slip past,
    # because the title and footer were still being rendered.
    check("the configured title is used",
          any("Willkommen bei Test Server" in t for t in texts), str(texts))
    check("the configured body is used",
          any("Klick unten" in t for t in texts), str(texts))
    check("the configured footer is used",
          any("Wir sind 1204 Leute" in t for t in texts), str(texts))
    check("no English default leaked through",
          "Click below" not in joined and "Welcome to" not in joined,
          joined[:200])

    rows = [c for c in payload[0]["components"] if c.get("type") == 1]
    check("there is a button row", len(rows) == 1, str(len(rows)))
    labels = [b.get("label") for b in rows[0]["components"]]
    check("the custom label is used", "Los geht's" in labels, str(labels))
    check("'button' mode shows one button", len(labels) == 1, str(labels))
    check("a preview button is disabled",
          all(b.get("disabled") for b in rows[0]["components"]),
          str(rows[0]["components"]))

    settings = store.normalise({**settings, "verification_method": "both"})
    view = cog.build_panel(guild, settings, role, preview=True)
    rows = [
        c for c in view.to_components()[0]["components"] if c.get("type") == 1
    ]
    check("'both' shows two buttons", len(rows[0]["components"]) == 2,
          str(len(rows[0]["components"])))

    # The live panel must keep the ids that make it survive a restart.
    view = cog.build_panel(guild, settings, role, preview=False)
    rows = [
        c for c in view.to_components()[0]["components"] if c.get("type") == 1
    ]
    ids = [b.get("custom_id") for b in rows[0]["components"]]
    check("the live buttons keep their custom_id",
          all(i for i in ids), str(ids))
    check("and they are not disabled",
          not any(b.get("disabled") for b in rows[0]["components"]), str(ids))


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
    guild._roles[ROLE_OK] = Role(ROLE_OK, "Verifiziert", 5)
    guild._roles[ROLE_HIGH] = Role(ROLE_HIGH, "Zu hoch", 500)
    guild._roles[ROLE_MANAGED] = Role(ROLE_MANAGED, "Bot", 3, managed=True)
    channel = Channel(CHANNEL, "verify")
    channel.guild = guild
    guild._channels[CHANNEL] = channel
    guild.me = Member(1)
    guild.me.top_role = Role(9999, "bot", 100)

    class Bot:
        user = type("U", (), {"id": 1})()

        def __init__(self):
            self.reloaded: list = []
            self.cog = None

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            self.reloaded.append(name)
            return self.cog

        def add_view(self, *a, **k):
            pass

    bot = Bot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/verify/{GUILD}"

    if os.path.exists(store.DB_PATH):
        os.remove(store.DB_PATH)

    r = client.patch(base, json={"enabled": True})
    check("cannot switch on without a channel and role",
          r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"verified_role_id": str(ROLE_HIGH)})
    check("a role above the bot is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"verified_role_id": str(ROLE_MANAGED)})
    check("an integration role is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"verification_method": "quatsch"})
    check("an unknown method is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"panel_title": "   "})
    check("an empty text is refused", r.status_code == 400, r.text[:120])

    r = client.patch(base, json={"min_account_age_days": -3})
    check("a negative age is refused", r.status_code == 400, r.text[:120])

    bot.reloaded.clear()
    r = client.patch(base, json={
        "verification_channel_id": str(CHANNEL),
        "verified_role_id": str(ROLE_OK),
        "enabled": True,
    })
    check("a proper setup is accepted", r.status_code == 200, r.text[:120])
    check("the cog is told under its real name",
          "Verification" in bot.reloaded, str(bot.reloaded))

    data = client.get(base).json()
    check("ids come back as strings, not rounded numbers",
          data["verification_channel_id"] == str(CHANNEL),
          str(data["verification_channel_id"]))
    check("it reports itself as configured", data["configured"] is True)
    check("the preview is rendered server-side",
          "Test Server" in data["preview"]["text"], str(data["preview"]))
    check("the placeholder list is sent along",
          "{server}" in data["placeholders"], str(data.get("placeholders")))

    client.patch(base, json={"panel_title": "Mein Titel"})
    data = client.get(base).json()
    check("a partial save keeps the channel",
          data["verification_channel_id"] == str(CHANNEL))
    check("and applies the new title", data["panel_title"] == "Mein Titel")

    # Warnings
    guild.me.guild_permissions = Perms(manage_roles=False)
    warns = client.get(base).json()["warnings"]
    check("a missing permission is reported",
          any("Rollen verwalten" in w for w in warns), str(warns))
    guild.me.guild_permissions = Perms()

    client.patch(base, json={"panel_text": "Hallo {username}"})
    warns = client.get(base).json()["warnings"]
    check("a bad placeholder is reported",
          any("{username}" in w for w in warns), str(warns))
    client.patch(base, json={"panel_text": store.DEFAULTS["panel_text"]})

    # Panel needs the cog.
    r = client.post(f"{base}/panel", json={})
    check("posting the panel needs the cog", r.status_code == 503,
          str(r.status_code))

    from cogs.commands.verification import Verification

    cog = Verification.__new__(Verification)
    cog.bot = bot
    bot.cog = cog

    channel.sent.clear()
    r = client.post(f"{base}/panel", json={})
    check("with the cog it posts", r.status_code == 200, r.text[:140])
    check("and the panel reached the channel", len(channel.sent) == 1,
          str(len(channel.sent)))
    posted = channel.sent[0]["view"].to_components()
    check("what it posted is a V2 container", posted[0]["type"] == 17)

    check("the message id is remembered",
          client.get(base).json()["panel_message_id"] is not None)

    # The preview must not replace the live panel.
    channel.sent.clear()
    before = client.get(base).json()["panel_message_id"]
    r = client.post(f"{base}/preview", json={"panel_title": "Andere Fassung"})
    check("a preview can be sent", r.status_code == 200, r.text[:140])
    after = client.get(base).json()["panel_message_id"]
    check("it does not replace the live panel", before == after,
          f"{before} -> {after}")
    check("and it does not save the draft",
          client.get(base).json()["panel_title"] == "Mein Titel")

    preview_view = channel.sent[0]["view"].to_components()
    texts = " ".join(
        c["content"] for c in preview_view[0]["components"] if c.get("type") == 10
    )
    check("the preview shows the unsaved text",
          "Andere Fassung" in texts, texts[:120])

    # Manual verification.
    member = Member(ALICE)
    guild._members[ALICE] = member
    r = client.post(f"{base}/verify/{ALICE}", json={})
    check("somebody can be verified by hand", r.status_code == 200, r.text[:120])
    check("and really gets the role",
          any(role.id == ROLE_OK for role in member.added),
          str(member.added))

    r = client.post(f"{base}/verify/999", json={})
    check("an unknown member gives 404", r.status_code == 404, str(r.status_code))

    check("the count went up",
          client.get(base).json()["verified_count"] >= 1)

    # Reset keeps the texts.
    r = client.post(f"{base}/reset", json={})
    data = client.get(base).json()
    check("reset switches it off", data["enabled"] is False)
    check("but keeps the texts", data["panel_title"] == "Mein Titel")

    client.post(f"{base}/reset", json={"keep_texts": False})
    check("clearing the texts works too",
          client.get(base).json()["panel_title"] == store.DEFAULTS["panel_title"])

    r = client.get("/api/v1/verify/999999")
    check("an unknown guild still answers", r.status_code == 200,
          str(r.status_code))

    await db_manager.close_all()


def test_panel_restore_uses_cog():
    """
    Restoring must not overwrite the configured texts.

    panel_restore used to build the panel itself with the English
    strings hard-coded, so a restore after a backup quietly replaced
    whatever the server had written.
    """
    print("\nRestore keeps the texts")

    src = open(os.path.join(HERE, "..", "api", "panel_restore.py")).read()

    check("the restore asks the cog to render",
          "build_panel" in src, "build_panel is not called")
    check("and no longer builds its own panel",
          "VerificationPanel(" not in src, "VerificationPanel is still used")
    check("the English strings are gone",
          "Quick Verify" not in src, "hard-coded English is still there")


async def run():
    from utils import verify_store as store

    await test_migration(store)
    await test_partial_save(store)
    test_rendering(store)
    test_rules(store)
    await test_dm_crash(store)
    await test_message_cleanup(store)
    test_panel_rendering(store)
    await test_api(store)
    test_panel_restore_uses_cog()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
