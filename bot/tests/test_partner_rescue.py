#!/usr/bin/env python3
"""
Handing a wrecked server over to the template bot.

Two things had to be true before this could work at all:

  * **The rescue bot must never be attacked by the anti-nuke.** Rebuilding
    a server means creating dozens of channels and roles in seconds --
    the exact shape of a nuke. All seventeen modules would have acted on
    it. `antibotadd` was worse still: it checks *who invited* the bot, so
    the rescue bot was kicked on arrival and the admin who invited it was
    banned.

  * **Somebody has to type the start command.** After a nuke that
    somebody is staring at an empty server, so this bot types it --
    five seconds after the template bot joins, in the channel where the
    recovery panel went.

The handoff is deliberately narrow: only after a real attack, only for
the one known bot id, only once. Firing it on every bot join would mean
poking a stranger's bot with a command it never asked for.

Run:  python3 tests/test_partner_rescue.py
"""

import asyncio
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
warnings.filterwarnings("ignore")

GUILD = 5501
OWNER = 9
ATTACKER = 77
PARTNER_ID = 1530742522589089952

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


class Perms:
    def __init__(self, ok=True, **kw):
        for key in ("send_messages", "view_channel", "read_message_history",
                    "manage_channels", "ban_members", "kick_members",
                    "manage_roles", "manage_webhooks", "view_audit_log"):
            setattr(self, key, kw.get(key, ok))


class Channel:
    def __init__(self, cid=10, name="nuke-alarm", guild=None, ok=True):
        self.id = cid
        self.name = name
        self.guild = guild
        self.sent: list = []
        self._ok = ok

    def permissions_for(self, _member):
        return Perms(self._ok)

    async def send(self, content=None, view=None, **kwargs):
        self.sent.append(content if content is not None else "<panel>")
        return type("M", (), {"id": 1})()


class Member:
    def __init__(self, uid, bot=True, guild=None):
        self.id = uid
        self.bot = bot
        self.guild = guild
        self.mention = f"<@{uid}>"
        self.name = f"User{uid}"


class Guild:
    def __init__(self, gid=GUILD, channels=None):
        self.id = gid
        self.name = "Server"
        self.owner_id = OWNER
        self.system_channel = None
        self.me = Member(1, guild=self)
        self.me.guild_permissions = Perms()
        if channels is None:
            channel = Channel(guild=self)
            channels = [channel]
        for channel in channels:
            channel.guild = self
        self.text_channels = channels

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == int(cid)), None)


# ══════════════════════════════════════════════════════════════════════
#  Identity
# ══════════════════════════════════════════════════════════════════════


def test_identity(pb):
    print("\nRecognising the template bot")

    check("the id is stored exactly, not rounded",
          pb.BOT_ID == 1530742522589089952, str(pb.BOT_ID))
    check("it survives as a full 19-digit snowflake",
          len(str(pb.BOT_ID)) == 19, str(len(str(pb.BOT_ID))))

    check("a bare id is recognised", pb.is_partner(PARTNER_ID))
    check("an object with .id is recognised",
          pb.is_partner(Member(PARTNER_ID)))
    check("a string id is recognised", pb.is_partner(str(PARTNER_ID)))

    check("another bot is not", pb.is_partner(999) is False)
    check("None is not", pb.is_partner(None) is False)
    check("nonsense is not", pb.is_partner("abc") is False)
    check("an object without an id is not",
          pb.is_partner(object()) is False)

    # An id one digit off must not slip through -- this is the failure
    # mode that would whitelist a stranger.
    check("a near-miss id is rejected",
          pb.is_partner(PARTNER_ID + 1) is False)


def test_every_module_whitelists():
    """
    All seventeen modules have to skip the rescue bot.

    Asserted on the source: missing one means the bot gets banned
    halfway through rebuilding, and only on the server where it matters.
    """
    print("\nWhitelisted everywhere")

    folder = os.path.join(HERE, "..", "cogs", "antinuke")
    missing = []
    unimported = []

    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(folder, name)).read()
        if "partner_bot.is_partner" not in src:
            missing.append(name)
        elif "partner_bot" not in src.split("class ")[0]:
            unimported.append(name)

    check("every anti-nuke module checks for it", not missing, str(missing))
    check("and each one imports it properly", not unimported, str(unimported))

    # The bot-add module needs a second check: the one above looks at
    # who *invited* the bot, which is a normal admin.
    src = open(os.path.join(folder, "antibotadd.py")).read()
    joined = src[src.index("async def on_member_join"):]
    joined = joined[:joined.index("guild = member.guild")]
    check("antibotadd also checks the arriving bot itself, not just the inviter",
          "is_partner(member)" in joined, joined[-200:])


async def test_not_banned_on_arrival():
    """The rescue bot joins: antibotadd must leave it alone."""
    print("\nArriving without being kicked")

    from cogs.antinuke.antibotadd import AntiBotAdd

    acted = []

    class Cog(AntiBotAdd):
        async def take_action_and_kick_bot(self, *a, **kw):
            acted.append(a)

    cog = Cog(type("B", (), {"user": Member(2)})())
    guild = Guild()

    partner = Member(PARTNER_ID, guild=guild)
    await cog.on_member_join(partner)
    check("the template bot is not kicked", acted == [], str(acted))

    # A human is not a bot, so the listener returns before anything else.
    human = Member(555, bot=False, guild=guild)
    await cog.on_member_join(human)
    check("a human joining is ignored", acted == [])


# ══════════════════════════════════════════════════════════════════════
#  The handoff
# ══════════════════════════════════════════════════════════════════════


async def test_handoff(na, pb):
    print("\nThe handoff")

    from cogs.events.partner_handoff import PartnerHandoff

    original_delay = na.TEMPLATE_TRIGGER_DELAY
    na.TEMPLATE_TRIGGER_DELAY = 0.01

    try:
        cog = PartnerHandoff(type("B", (), {})())

        # No attack: nothing to rescue, so nothing is sent.
        guild = Guild()
        na.clear_attack(guild.id)
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("without a recent attack the bot stays quiet",
              guild.text_channels[0].sent == [],
              str(guild.text_channels[0].sent))

        # After an attack.
        guild = Guild()
        channel = guild.text_channels[0]
        na.remember_attack(guild.id, channel.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))

        check("the trigger is sent", na.TEMPLATE_TRIGGER in channel.sent,
              str(channel.sent))
        check("it is exactly the command the template bot expects",
              na.TEMPLATE_TRIGGER == "!start", na.TEMPLATE_TRIGGER)
        # The ping comes first now, so the bot is notified before the
        # explanation card; see test_ping_then_trigger.
        check("the bot is pinged before anything else",
              channel.sent[0].startswith("<@"), str(channel.sent))
        check("a heads-up follows", channel.sent[1] == "<panel>",
              str(channel.sent))
        check("the trigger comes last",
              channel.sent[-1] == na.TEMPLATE_TRIGGER, str(channel.sent))

        # A different bot must not set it off.
        guild = Guild()
        channel = guild.text_channels[0]
        na.remember_attack(guild.id, channel.id)
        cog._done.clear()
        await cog.on_member_join(Member(4242, guild=guild))
        check("another bot joining does nothing", channel.sent == [],
              str(channel.sent))

        # A human must not either.
        guild = Guild()
        channel = guild.text_channels[0]
        na.remember_attack(guild.id, channel.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, bot=False, guild=guild))
        check("a human with that id is ignored", channel.sent == [])

        # Twice must stay once.
        guild = Guild()
        channel = guild.text_channels[0]
        na.remember_attack(guild.id, channel.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        # The second event deliberately does *not* re-arm the mark --
        # re-arming it here is what made the first version of this check
        # test its own setup rather than the code.
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("a duplicate join event does not send it twice",
              channel.sent.count(na.TEMPLATE_TRIGGER) == 1,
              str(channel.sent))

        # The mark is consumed by a completed handoff, so the template
        # bot rejoining later is not treated as a fresh rescue.
        check("the attack mark is cleared afterwards",
              na.recent_attack(guild.id) is None)

        # An old attack does not count.
        guild = Guild()
        channel = guild.text_channels[0]
        na.remember_attack(guild.id, channel.id)
        na._recent_attack[guild.id]["at"] -= na.RESCUE_WINDOW + 10
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("an attack from hours ago is not treated as a rescue",
              channel.sent == [], str(channel.sent))

        # If the bot leaves, a later rescue may start over.
        cog._done.add(GUILD)
        guild = Guild()
        await cog.on_member_remove(Member(PARTNER_ID, guild=guild))
        check("the bot leaving re-arms the handoff",
              GUILD not in cog._done or guild.id not in cog._done)
    finally:
        na.TEMPLATE_TRIGGER_DELAY = original_delay


async def test_channel_choice(na, pb):
    print("\nChoosing where to send it")

    from cogs.events.partner_handoff import PartnerHandoff

    original_delay = na.TEMPLATE_TRIGGER_DELAY
    na.TEMPLATE_TRIGGER_DELAY = 0.01

    try:
        cog = PartnerHandoff(type("B", (), {})())

        # The panel's channel wins, even when others exist.
        general = Channel(20, "general")
        panel = Channel(21, "nuke-alarm")
        guild = Guild(channels=[general, panel])
        na.remember_attack(guild.id, panel.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("the trigger goes where the panel is",
              na.TEMPLATE_TRIGGER in panel.sent, str(panel.sent))
        check("and not into the first channel it finds",
              general.sent == [], str(general.sent))

        # Panel channel gone: fall back to one that works.
        general = Channel(20, "general")
        guild = Guild(channels=[general])
        na.remember_attack(guild.id, 9999)     # a channel that no longer exists
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("a deleted panel channel falls back to another",
              na.TEMPLATE_TRIGGER in general.sent, str(general.sent))

        # A channel the bot cannot write in is not used.
        locked = Channel(30, "locked", ok=False)
        open_one = Channel(31, "open")
        guild = Guild(channels=[locked, open_one])
        na.remember_attack(guild.id, locked.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("a channel the bot cannot use is skipped", locked.sent == [])
        check("and a usable one is found instead",
              na.TEMPLATE_TRIGGER in open_one.sent, str(open_one.sent))

        # Nothing usable at all: no crash, no trigger.
        locked = Channel(40, "locked", ok=False)
        guild = Guild(channels=[locked])
        na.remember_attack(guild.id, locked.id)
        cog._done.clear()
        await cog.on_member_join(Member(PARTNER_ID, guild=guild))
        check("with nowhere to write nothing happens, and nothing raises",
              locked.sent == [])
        check("and the guild is not marked as done, so a retry is possible",
              guild.id not in cog._done)
    finally:
        na.TEMPLATE_TRIGGER_DELAY = original_delay


def test_delay(na):
    print("\nThe pause before the trigger")

    check("there is a delay at all", na.TEMPLATE_TRIGGER_DELAY > 0)
    # Two seconds between the ping and the command. The longer wait now
    # sits before the backup channel is created instead.
    check("it is the two seconds asked for",
          na.TEMPLATE_TRIGGER_DELAY == 2.0, str(na.TEMPLATE_TRIGGER_DELAY))

    import ast
    import inspect
    from cogs.events.partner_handoff import PartnerHandoff

    source = inspect.getsource(PartnerHandoff._hand_over)
    tree = ast.parse(source.lstrip().replace("    ", "", 1) if False else
                     __import__("textwrap").dedent(source))
    sleeps = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and "sleep" in ast.unparse(node.func)
    ]
    check("the handoff actually waits", len(sleeps) == 1, str(len(sleeps)))
    check("using the shared constant, not a magic number",
          "TEMPLATE_TRIGGER_DELAY" in ast.unparse(sleeps[0]),
          ast.unparse(sleeps[0]))


# ══════════════════════════════════════════════════════════════════════
#  The panel
# ══════════════════════════════════════════════════════════════════════


async def test_recovery_panel(na):
    print("\nThe recovery panel")

    os.environ["PARTNER_BOT_CLIENT_ID"] = "1530742522589089952"
    os.environ["DASHBOARD_URL"] = "https://example.com"

    guild = Guild()
    view = na.recovery_panel(guild, cleaned=4)
    payload = view.to_components()

    check("it is a Components V2 container", payload[0]["type"] == 17,
          str(payload[0]["type"]))

    text = " ".join(
        c.get("content", "") for c in payload[0]["components"]
        if c.get("type") == 10
    )
    check("it explains how to get the server back",
          "wiederherstellen" in text.lower(), text[:120])
    check("it says the rescue bot will not trigger the anti-nuke",
          "Alarm" in text or "freigestellt" in text, text[-200:])
    check("and mentions what was already cleaned up", "4" in text)

    rows = [c for c in payload[0]["components"] if c.get("type") == 1]
    check("it carries the buttons", len(rows) == 1, str(len(rows)))
    check("all three of them", len(rows[0]["components"]) == 3,
          str(len(rows[0]["components"])))


async def test_panel_posted_once(na):
    print("\nThe panel is posted once per attack")

    await na.save_settings(GUILD, {"enabled": 1, "dm_owner": 0, "ping_owner": 0})

    na._last_alert.clear()
    na._last_dm.clear()
    na._incident.clear()

    guild = Guild()
    channel = guild.text_channels[0]
    guild.owner = None
    attacker = type("E", (), {"id": ATTACKER, "mention": f"<@{ATTACKER}>"})()

    for _ in range(5):
        na._last_alert.clear()
        await na.report(None, guild, "channel_delete",
                        na.OUTCOME_STOPPED, executor=attacker,
                        banned=True)

    check("every event is logged to the channel",
          len(channel.sent) == 5, str(len(channel.sent)))
    # The recovery panel is not here any more -- it goes into the
    # #backup channel after the attack. This fake records "<panel>" for
    # a view-only message, so every entry being one means reports only.
    check("the alert channel carries reports only",
          all(entry == "<panel>" for entry in channel.sent),
          str(channel.sent[:3]))

    check("and the attack is remembered for the handoff",
          na.recent_attack(guild.id) is not None)
    remembered = na.recent_attack(guild.id)
    check("along with the channel it went to",
          remembered["channel_id"] == channel.id, str(remembered))
    check("the panel was scheduled rather than posted inline",
          na._incident[guild.id].get("panel_sent") is True,
          str(na._incident.get(guild.id)))


async def test_backup_channel(na):
    """
    The rescue gets its own channel, twenty seconds after the attack.

    Creating it immediately would build it into a nuke that is still
    running -- the events that trigger this arrive while channels are
    being deleted.
    """
    print("\nThe backup channel")

    original = na.BACKUP_DELAY
    na.BACKUP_DELAY = 0.05
    try:
        await na.save_settings(GUILD, {"enabled": 1, "dm_owner": 0, "ping_owner": 0})
        na._last_alert.clear()
        na._last_dm.clear()
        na._incident.clear()
        na._backup_pending.clear()

        guild = Guild()
        guild.owner = None
        guild.created = []

        async def create_text_channel(name, **kwargs):
            channel = Channel(200 + len(guild.created), name, guild)
            guild.text_channels.append(channel)
            guild.created.append(name)
            return channel

        guild.create_text_channel = create_text_channel
        guild.default_role = type("R", (), {"id": 0})()

        attacker = type("E", (), {"id": ATTACKER, "mention": f"<@{ATTACKER}>"})()

        # Ein ECHTER Nuke, zweimal gemeldet.
        #
        # Vorher stand hier OUTCOME_NO_PERMS. Nach Regel 1 passiert
        # dabei jetzt gar nichts mehr -- der Bot hat den Angriff nicht
        # gestoppt, also schweigt er. Und zweimal, weil erst zwei
        # zerstoerende Aktionen in einer Minute als Angriff gelten:
        # ein einzelner geloeschter Kanal ist ein Fehlklick.
        from utils import nuke_policy as policy

        policy.forget(guild.id)
        for _ in range(2):
            await na.report(None, guild, "channel_delete",
                            na.OUTCOME_STOPPED, executor=attacker,
                            banned=True)

        check("nothing is created while the attack is still running",
              guild.created == [], str(guild.created))

        await asyncio.sleep(0.3)

        check("the backup channel appears afterwards",
              guild.created == [na.BACKUP_CHANNEL_NAME], str(guild.created))
        check("it is called 'backup'", na.BACKUP_CHANNEL_NAME == "backup",
              na.BACKUP_CHANNEL_NAME)

        backup = next(c for c in guild.text_channels
                      if c.name == na.BACKUP_CHANNEL_NAME)
        check("the panel is posted into it", len(backup.sent) == 1,
              str(backup.sent))

        remembered = na.recent_attack(guild.id)
        check("and the handoff is pointed at it",
              remembered and remembered["channel_id"] == backup.id,
              str(remembered))

        # A burst of events must not start a timer each.
        na._last_alert.clear()
        na._incident.clear()
        guild.created.clear()
        for _ in range(10):
            na._last_alert.clear()
            await na.report(None, guild, "channel_delete",
                            na.OUTCOME_STOPPED, executor=attacker,
                        banned=True)
        await asyncio.sleep(0.3)
        check("an existing backup channel is reused, not duplicated",
              guild.created == [], str(guild.created))

        check("the wait is twenty seconds in production", original == 20.0,
              str(original))
    finally:
        na.BACKUP_DELAY = original


async def test_ping_then_trigger(na, pb):
    """Ping the bot, wait two seconds, then send the command."""
    print("\nPing, pause, trigger")

    from cogs.events.partner_handoff import PartnerHandoff

    original = na.TEMPLATE_TRIGGER_DELAY
    na.TEMPLATE_TRIGGER_DELAY = 0.01
    try:
        check("the pause is two seconds in production", original == 2.0,
              str(original))

        cog = PartnerHandoff(type("B", (), {})())
        backup = Channel(50, na.BACKUP_CHANNEL_NAME)
        guild = Guild(channels=[backup])
        na.remember_attack(guild.id, backup.id)
        cog._done.clear()

        member = Member(PARTNER_ID, guild=guild)
        await cog.on_member_join(member)

        check("three messages go out", len(backup.sent) == 3, str(backup.sent))
        check("the bot is pinged first",
              backup.sent[0] == member.mention, str(backup.sent[0]))
        check("then the explanation", backup.sent[1] == "<panel>",
              str(backup.sent[1]))
        check("then the trigger", backup.sent[2] == na.TEMPLATE_TRIGGER,
              str(backup.sent[2]))

        # The ping has to be a real message, not a mention buried in a
        # card -- a card does not notify.
        check("the ping is its own plain message",
              isinstance(backup.sent[0], str)
              and backup.sent[0].startswith("<@"), str(backup.sent[0]))
    finally:
        na.TEMPLATE_TRIGGER_DELAY = original


async def test_backup_access(na, pb):
    """
    The backup channel is hidden from @everyone, including the rescue bot.

    Without opening it the handoff would filter the channel out as
    unusable and do the rescue somewhere else -- or nowhere.
    """
    print("\nLetting the rescue bot in")

    from cogs.events.partner_handoff import PartnerHandoff

    original = na.TEMPLATE_TRIGGER_DELAY
    na.TEMPLATE_TRIGGER_DELAY = 0.01
    try:
        cog = PartnerHandoff(type("B", (), {})())

        class Hidden(Channel):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.granted = {}
                self.visible_to = set()

            def permissions_for(self, member):
                if getattr(member, "id", None) == PARTNER_ID \
                        and PARTNER_ID not in self.visible_to:
                    return Perms(False)
                return Perms(True)

            async def set_permissions(self, target, **kwargs):
                self.granted[target.id] = kwargs
                self.visible_to.add(target.id)

        backup = Hidden(60, na.BACKUP_CHANNEL_NAME)
        guild = Guild(channels=[backup])
        na.remember_attack(guild.id, backup.id)
        cog._done.clear()

        member = Member(PARTNER_ID, guild=guild)
        await cog.on_member_join(member)

        check("the bot is given access to the backup channel",
              PARTNER_ID in backup.granted, str(backup.granted))
        check("including being able to read it",
              backup.granted.get(PARTNER_ID, {}).get("view_channel") is True,
              str(backup.granted))
        check("and the rescue then happens there",
              na.TEMPLATE_TRIGGER in backup.sent, str(backup.sent))
    finally:
        na.TEMPLATE_TRIGGER_DELAY = original


async def run():
    from utils import nuke_alert as na
    from utils import partner_bot as pb

    test_identity(pb)
    test_every_module_whitelists()
    await test_not_banned_on_arrival()
    await test_backup_channel(na)
    await test_ping_then_trigger(na, pb)
    await test_backup_access(na, pb)
    await test_handoff(na, pb)
    await test_channel_choice(na, pb)
    test_delay(na)
    await test_recovery_panel(na)
    await test_panel_posted_once(na)

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
