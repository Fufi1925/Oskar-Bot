#!/usr/bin/env python3
"""
What the anti-nuke says after it reacts.

Four reported problems, all reproduced before they were fixed:

  * **Wrong claim.** The repair and the ban shared one try-block, so a
    Forbidden from the *ban* was reported through the same handler as a
    Forbidden from the repair. The channel was already deleted or
    restored, yet the owner read "Angriff erkannt — konnte ihn NICHT
    stoppen". Fourteen modules did this.

  * **DM spam.** Channel post and DM shared one 20 second cooldown. A
    five minute attack therefore produced fifteen direct messages, one
    every twenty seconds, each saying nearly the same thing -- and a DM
    cannot be muted.

  * **Self-inflicted alerts.** Cleaning up after an attacker means
    deleting channels, which fires the very listener that watches for
    channel deletions. The executor check depends on the audit log,
    which lags during a nuke.

  * **Silence when blind.** Nine modules leave fetch_audit_logs the
    moment the bot has no ban permission -- returning None without a
    word. Nothing is defended and nobody is told.

Plus the new recovery message: three link buttons on every alert.

Run:  python3 tests/test_nuke_report.py
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

GUILD = 6601
OWNER = 9
ATTACKER = 77

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


class FakeOwner:
    def __init__(self, accepts_dms=True):
        self.id = OWNER
        self.mention = f"<@{OWNER}>"
        self.dms: list = []
        self.accepts_dms = accepts_dms

    async def send(self, **kwargs):
        if not self.accepts_dms:
            raise forbidden()
        self.dms.append(kwargs)


class FakePerms:
    def __init__(self, **kw):
        for key in ("ban_members", "kick_members", "manage_channels",
                    "manage_roles", "manage_webhooks", "view_audit_log"):
            setattr(self, key, kw.get(key, True))


class FakeChannel:
    def __init__(self, cid=3, name="mod-log", can_send=True):
        self.id = cid
        self.name = name
        self.sent: list = []
        self._can_send = can_send

    def permissions_for(self, _member):
        return type("P", (), {"send_messages": self._can_send})()

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("M", (), {"id": 1})()


class FakeGuild:
    def __init__(self, gid=GUILD, perms=None, accepts_dms=True, channels=None):
        self.id = gid
        self.name = "Server"
        # alert_channel builds permission overwrites from this when it
        # has to create a channel; without it the call raises and the
        # test would "pass" against a fake that cannot do the job.
        self.default_role = type("R", (), {"id": 0})()
        self.owner_id = OWNER
        self.owner = FakeOwner(accepts_dms)
        self.channel = FakeChannel()
        self.text_channels = channels if channels is not None else [self.channel]
        self.system_channel = None
        self.me = type("M", (), {"guild_permissions": perms or FakePerms()})()

    def get_channel(self, _cid):
        return self.channel


def reports_only(channel):
    """
    Messages that are incident reports.

    The recovery panel is a separate, deliberate message posted once per
    attack, so a bare len(channel.sent) no longer counts reports.
    """
    out = []
    for entry in channel.sent:
        view = entry.get("view")
        text = " ".join(
            c.get("content", "")
            for c in view.to_components()[0]["components"]
            if c.get("type") == 10
        ) if view is not None else ""
        if "Server wiederherstellen" not in text:
            out.append(entry)
    return out


def panels_only(channel):
    return [e for e in channel.sent if e not in reports_only(channel)]


def reset(na):
    na._last_alert.clear()
    na._last_dm.clear()
    na._incident.clear()
    na._repairing.clear()
    na._self_deleting.clear()


# ══════════════════════════════════════════════════════════════════════
#  Wording
# ══════════════════════════════════════════════════════════════════════


def test_wording(na):
    print("\nWhat each outcome says")

    title, body, tone = na._describe(na.OUTCOME_STOPPED, "channel_delete")
    check("a stopped attack reads as success", tone == "success", tone)
    check("and never claims failure", "NICHT" not in title, title)

    # The reported bug.
    title, body, tone = na._describe(na.OUTCOME_PARTIAL, "channel_delete", "Bannen")
    check("a failed ban does not claim the attack continued",
          "NICHT stoppen" not in title, title)
    check("it says the attack was stopped", "gestoppt" in title.lower(), title)
    check("and names what actually failed",
          "bann" in title.lower(), title)
    check("the missing permission is passed through", "Bannen" in body)

    title, body, tone = na._describe(na.OUTCOME_NO_PERMS, "channel_delete", "Bannen")
    check("a genuine failure still says so", "NICHT" in title, title)
    check("and is an error, not a warning", tone == "error", tone)

    title, body, tone = na._describe(na.OUTCOME_BLIND, "channel_delete", "Audit-Log")
    check("being blind is reported as its own case",
          "blind" in title.lower(), title)
    check("and says the feature is effectively off",
          "läuft" in body or "nicht" in body)

    title, _, tone = na._describe(na.OUTCOME_DISABLED, "channel_delete")
    check("switched off is a warning, not an error", tone == "warning", tone)


# ══════════════════════════════════════════════════════════════════════
#  DMs
# ══════════════════════════════════════════════════════════════════════


async def test_dm_spam(na):
    print("\nDM volume (the reported bug)")

    await na.save_settings(GUILD, {"enabled": 1, "dm_owner": 1, "ping_owner": 1})
    attacker = type("E", (), {"id": ATTACKER, "mention": f"<@{ATTACKER}>"})()

    reset(na)
    guild = FakeGuild()
    # A five minute attack, in real time rather than by clearing the
    # bookkeeping: winding the clock back 21 seconds per event is what
    # actually happens, and it lets the DM timer notice it is longer
    # than the channel one. Clearing _last_alert alone would leave
    # _last_dm untouched and the test would pass either way.
    for _ in range(15):
        # 21 seconds pass: past the channel cooldown, nowhere near the
        # DM one.
        for book in (na._last_alert, na._last_dm):
            if guild.id in book:
                book[guild.id] -= 21.0
        await na.report(None, guild, "channel_delete",
                        na.OUTCOME_NO_PERMS, executor=attacker)

    check("the channel keeps a full log",
          len(reports_only(guild.channel)) == 15,
          str(len(reports_only(guild.channel))))
    check("and the recovery panel is posted exactly once",
          len(panels_only(guild.channel)) == 1,
          str(len(panels_only(guild.channel))))
    check("but the owner is messaged once, not fifteen times",
          len(guild.owner.dms) == 1, f"{len(guild.owner.dms)} DMs")

    # And the DM timer really is the longer of the two.
    check("the DM cooldown is far longer than the channel one",
          na.DM_COOLDOWN >= na.COOLDOWN * 10,
          f"{na.DM_COOLDOWN} vs {na.COOLDOWN}")

    reset(na)
    guild = FakeGuild()
    for _ in range(40):
        await na.report(None, guild, "channel_delete",
                        na.OUTCOME_NO_PERMS, executor=attacker)
    check("a burst of forty events is one channel post",
          len(reports_only(guild.channel)) == 1,
          str(len(reports_only(guild.channel))))
    check("and one DM", len(guild.owner.dms) == 1, str(len(guild.owner.dms)))

    # Nothing is asked of the owner, so nothing is sent.
    reset(na)
    guild = FakeGuild()
    await na.report(None, guild, "channel_create",
                    na.OUTCOME_STOPPED, executor=attacker)
    check("a stopped attack does not wake the owner at all",
          len(guild.owner.dms) == 0, str(len(guild.owner.dms)))
    check("but is still written to the channel",
          len(reports_only(guild.channel)) == 1,
          str(len(reports_only(guild.channel))))

    reset(na)
    guild = FakeGuild()
    await na.report(None, guild, "channel_delete",
                    na.OUTCOME_PARTIAL, executor=attacker)
    check("a partial stop does reach the owner",
          len(guild.owner.dms) == 1, str(len(guild.owner.dms)))

    # A closed DM must not be retried on every single event.
    reset(na)
    guild = FakeGuild(accepts_dms=False)
    for _ in range(5):
        na._last_alert.clear()
        await na.report(None, guild, "channel_delete",
                        na.OUTCOME_NO_PERMS, executor=attacker)
    check("closed DMs do not break the channel report",
          len(reports_only(guild.channel)) == 5,
          str(len(reports_only(guild.channel))))

    reset(na)
    guild = FakeGuild()
    await na.save_settings(GUILD, {"dm_owner": 0})
    await na.report(None, guild, "channel_delete",
                    na.OUTCOME_NO_PERMS, executor=attacker)
    check("switching DMs off is respected", len(guild.owner.dms) == 0)
    await na.save_settings(GUILD, {"dm_owner": 1})


async def test_incident_grouping(na):
    print("\nOne attack, one story")

    await na.save_settings(GUILD, {"enabled": 1, "dm_owner": 1})
    attacker = type("E", (), {"id": ATTACKER, "mention": f"<@{ATTACKER}>"})()

    reset(na)
    guild = FakeGuild()
    for action in ("channel_delete", "channel_delete", "role_delete", "ban"):
        na._last_alert.clear()
        await na.report(None, guild, action,
                        na.OUTCOME_NO_PERMS, executor=attacker)

    summary = na._incident_summary(GUILD)
    check("the running total counts each action",
          "2× Kanal gelöscht" in summary, summary)
    check("and lists the others too",
          "Rolle gelöscht" in summary and "gebannt" in summary, summary)

    last = " ".join(
        c.get("content", "")
        for c in reports_only(guild.channel)[-1]["view"]
        .to_components()[0]["components"]
        if c.get("type") == 10
    )
    check("the report shows what the attack has done so far",
          "Bisher in diesem Angriff" in last, last[:150])

    first = " ".join(
        c.get("content", "")
        for c in reports_only(guild.channel)[0]["view"]
        .to_components()[0]["components"]
        if c.get("type") == 10
    )
    check("the very first report does not, having nothing to summarise",
          "Bisher in diesem Angriff" not in first, first[:150])

    # The worst outcome wins; one success mid-attack must not soften it.
    reset(na)
    na._track_incident(GUILD, "channel_delete", na.OUTCOME_STOPPED)
    na._track_incident(GUILD, "channel_delete", na.OUTCOME_NO_PERMS)
    na._track_incident(GUILD, "channel_delete", na.OUTCOME_STOPPED)
    check("the most serious outcome is remembered",
          na._incident[GUILD]["worst"] == na.OUTCOME_NO_PERMS,
          na._incident[GUILD]["worst"])


# ══════════════════════════════════════════════════════════════════════
#  Self-inflicted alerts
# ══════════════════════════════════════════════════════════════════════


def test_self_action(na):
    print("\nThe bot must not flag its own cleanup")

    reset(na)
    check("nothing is flagged when idle", na.is_self_action(GUILD) is False)

    na.mark_repairing(GUILD)
    check("during a repair the guild is marked", na.is_self_action(GUILD) is True)
    check("but only that guild", na.is_self_action(GUILD + 1) is False)

    reset(na)
    na._self_deleting.add(4242)
    check("a channel being deleted by the cleanup is known",
          na.is_self_action(GUILD, 4242) is True)
    check("an unrelated channel is not",
          na.is_self_action(GUILD, 4243) is False)

    # The window has to expire, or the bot goes deaf after one repair.
    reset(na)
    na._repairing[GUILD] = 0.0
    check("the repair window expires",
          na.is_self_action(GUILD) is False)


def test_listener_guards():
    """The guard has to sit before any work, in every channel listener."""
    print("\nGuards in the listeners")

    import ast

    for name, listener in (
        ("antichdl.py", "on_guild_channel_delete"),
        ("antichcr.py", "on_guild_channel_create"),
        ("antichup.py", "on_guild_channel_update"),
    ):
        path = os.path.join(HERE, "..", "cogs", "antinuke", name)
        src = open(path).read()
        tree = ast.parse(src)

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == listener:
                body = ast.unparse(node)
                found = "is_self_action" in body
                # And it must be the first thing, before any database work.
                first = ast.unparse(node.body[0]) if node.body else ""
                check(f"{name}: the guard runs before anything else",
                      "is_self_action" in first, first[:60])
        check(f"{name}: {listener} checks for its own work", found)


# ══════════════════════════════════════════════════════════════════════
#  The modules
# ══════════════════════════════════════════════════════════════════════


async def test_module_reports():
    print("\nWhat the modules report")

    from cogs.antinuke.antichcr import AntiChannelCreate
    import cogs.antinuke.antichcr as module
    from utils import nuke_alert as na

    seen: list[str] = []

    async def stopped(*a, **kw):
        seen.append("stopped")

    async def partial(*a, repaired=True, **kw):
        seen.append("partial" if repaired else "no_perms")

    async def forbidden_(*a, **kw):
        seen.append("no_perms")

    real = (na.handle_stopped, na.handle_partial, na.handle_forbidden)
    na.handle_stopped, na.handle_partial, na.handle_forbidden = (
        stopped, partial, forbidden_
    )
    module.nuke_alert = na

    class Guild:
        id = GUILD
        owner_id = OWNER

        def __init__(self, ban_ok):
            self.ban_ok = ban_ok

        async def ban(self, _user, reason=None):
            if not self.ban_ok:
                raise forbidden()

    class Channel:
        id = 5

        def __init__(self, delete_ok, ban_ok):
            self.guild = Guild(ban_ok)
            self.delete_ok = delete_ok
            self.deleted = False

        async def delete(self, reason=None):
            if not self.delete_ok:
                raise forbidden()
            self.deleted = True

    cog = AntiChannelCreate(
        type("B", (), {"user": type("U", (), {"id": 2})()})()
    )
    attacker = type("E", (), {"id": ATTACKER})()

    seen.clear()
    channel = Channel(True, True)
    await cog.delete_channel_and_ban(channel, attacker, delay=0)
    check("everything worked -> stopped", seen == ["stopped"], str(seen))
    check("and the channel really is gone", channel.deleted is True)

    # This is the reported bug.
    seen.clear()
    channel = Channel(True, False)
    await cog.delete_channel_and_ban(channel, attacker, delay=0)
    check("channel removed but ban refused -> partial, not 'could not stop'",
          seen == ["partial"], str(seen))
    check("the attack was in fact stopped", channel.deleted is True)

    seen.clear()
    channel = Channel(False, False)
    await cog.delete_channel_and_ban(channel, attacker, delay=0)
    check("nothing worked -> the honest 'could not stop it'",
          seen == ["no_perms"], str(seen))
    check("and the channel is still there", channel.deleted is False)

    na.handle_stopped, na.handle_partial, na.handle_forbidden = real


def test_blind_reporting():
    """Nine modules used to return None here without telling anyone."""
    print("\nMissing audit access is reported")

    import ast

    silent = []
    for name in sorted(os.listdir(os.path.join(HERE, "..", "cogs", "antinuke"))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(HERE, "..", "cogs", "antinuke", name)
        src = open(path).read()
        if "guild_permissions.ban_members" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.AsyncFunctionDef) \
                    and node.name == "fetch_audit_logs":
                if "handle_blind" not in ast.unparse(node):
                    silent.append(name)

    check("no module bails out of the audit check in silence",
          not silent, str(silent))

    # Every module needs the label the report is filed under.
    missing = []
    for name in sorted(os.listdir(os.path.join(HERE, "..", "cogs", "antinuke"))):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(HERE, "..", "cogs", "antinuke", name)).read()
        if "ALERT_ACTION" not in src:
            missing.append(name)
    check("every module declares what it reports on", not missing, str(missing))

    # And those labels have to be ones the report can name.
    from utils import nuke_alert as na
    import re

    unknown = []
    for name in sorted(os.listdir(os.path.join(HERE, "..", "cogs", "antinuke"))):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(HERE, "..", "cogs", "antinuke", name)).read()
        for match in re.finditer(r'ALERT_ACTION = "([a-z_]+)"', src):
            if match.group(1) not in na.LABELS:
                unknown.append(f"{name}:{match.group(1)}")
    check("and every label has German wording", not unknown, str(unknown))


def test_no_stale_wording():
    """
    A Forbidden after a ban must not use the "could not stop it" helper.

    This is what made fourteen modules lie, so it is asserted on the
    source rather than trusting that they were all found.
    """
    print("\nNo module still mis-reports a failed ban")

    import ast

    wrong = []
    for name in sorted(os.listdir(os.path.join(HERE, "..", "cogs", "antinuke"))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(HERE, "..", "cogs", "antinuke", name)
        src = open(path).read()
        lines = src.split("\n")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Try):
                continue
            body = "\n".join(
                lines[node.body[0].lineno - 1:node.body[-1].end_lineno]
            )
            if ".ban(" not in body:
                continue
            for handler in node.handlers:
                hsrc = "\n".join(lines[handler.lineno - 1:handler.end_lineno])
                if "handle_forbidden" in hsrc:
                    wrong.append(f"{name}:{handler.lineno}")

    check("a failed ban never reports 'could not stop it'",
          not wrong, str(wrong))


# ══════════════════════════════════════════════════════════════════════
#  Recovery buttons
# ══════════════════════════════════════════════════════════════════════


def test_buttons(na):
    print("\nRecovery buttons")

    guild = type("G", (), {"id": 1327995167345819721, "owner_id": OWNER})()

    os.environ.pop("PARTNER_BOT_CLIENT_ID", None)
    os.environ.pop("DASHBOARD_URL", None)
    buttons = na.recovery_buttons(guild)
    labels = [b.label for b in (buttons or [])]
    check("without configuration only the support link remains",
          labels == ["Hilfe holen"], str(labels))

    os.environ["PARTNER_BOT_CLIENT_ID"] = "123456789"
    os.environ["DASHBOARD_URL"] = "https://example.com/"
    buttons = na.recovery_buttons(guild, user_id=42)
    labels = [b.label for b in buttons]
    check("configured, all three appear", len(buttons) == 3, str(labels))
    check("one of them restores the server",
          any("wiederherstellen" in b.label.lower() for b in buttons), str(labels))

    invite = next(b for b in buttons if "wiederherstellen" in b.label.lower())
    check("the invite carries the client id", "client_id=123456789" in invite.url)
    check("and preselects this server",
          f"guild_id={guild.id}" in invite.url, invite.url[:120])
    check("the server id is not rounded",
          "1327995167345819721" in invite.url, invite.url[:120])

    dash = next(b for b in buttons if "Anti-Nuke" in b.label)
    check("the dashboard link has no double slash",
          "//dashboard" not in dash.url, dash.url)
    check("and points at this server's anti-nuke page",
          dash.url.endswith(f"/dashboard/guild/{guild.id}/antinuke"), dash.url)

    check("every button is a link, so it survives a restart",
          all(b.style is discord.ButtonStyle.link for b in buttons))

    # Discord refuses more than five buttons in a row.
    check("they fit in a single action row", len(buttons) <= 5, str(len(buttons)))


async def test_buttons_in_report(na):
    print("\nButtons reach the message")

    os.environ["PARTNER_BOT_CLIENT_ID"] = "123456789"
    os.environ["DASHBOARD_URL"] = "https://example.com"
    await na.save_settings(GUILD, {"enabled": 1, "dm_owner": 1})

    reset(na)
    guild = FakeGuild()
    attacker = type("E", (), {"id": ATTACKER, "mention": f"<@{ATTACKER}>"})()
    await na.report(None, guild, "channel_delete",
                    na.OUTCOME_NO_PERMS, executor=attacker)

    check("the channel got a message",
          len(reports_only(guild.channel)) == 1,
          str(len(reports_only(guild.channel))))
    view = reports_only(guild.channel)[0]["view"]
    payload = view.to_components()
    check("it is a Components V2 container", payload[0]["type"] == 17,
          str(payload[0]["type"]))

    rows = [c for c in payload[0]["components"] if c.get("type") == 1]
    check("with an action row of buttons", len(rows) == 1, str(len(rows)))
    check("holding all three", len(rows[0]["components"]) == 3,
          str(len(rows[0]["components"])))

    check("the DM carries them too", len(guild.owner.dms) == 1)
    dm_payload = guild.owner.dms[0]["view"].to_components()
    dm_rows = [c for c in dm_payload[0]["components"] if c.get("type") == 1]
    check("so the owner can act straight from the DM", len(dm_rows) == 1)

    text = " ".join(
        c.get("content", "") for c in dm_payload[0]["components"]
        if c.get("type") == 10
    )
    check("and the DM says it will not repeat itself",
          "nicht einzeln" in text, text[:120])

    # Even with nothing configured the message must still go out.
    os.environ.pop("PARTNER_BOT_CLIENT_ID", None)
    os.environ.pop("DASHBOARD_URL", None)
    reset(na)
    guild = FakeGuild()
    await na.report(None, guild, "channel_delete",
                    na.OUTCOME_NO_PERMS, executor=attacker)
    check("an unconfigured bot still reports the attack",
          len(reports_only(guild.channel)) == 1,
          str(len(reports_only(guild.channel))))


async def test_alert_channel_survives(na):
    print("\nFinding somewhere to report")

    await na.save_settings(GUILD, {"enabled": 1, "create_channel": 1})
    settings = await na.get_settings(GUILD)

    # The attacker deleted everything.
    class EmptyGuild(FakeGuild):
        def __init__(self):
            super().__init__(channels=[])
            self.created = []
            self.me = type("M", (), {"guild_permissions": FakePerms()})()

        def get_channel(self, _cid):
            return None

        async def create_text_channel(self, name, **kwargs):
            channel = FakeChannel(99, name)
            self.created.append(name)
            return channel

    guild = EmptyGuild()
    channel = await na.alert_channel(guild, settings)
    check("with no channels left the bot makes one", channel is not None)
    check("named so it can be found again",
          guild.created == [na.ALERT_CHANNEL_NAME], str(guild.created))

    # And it must not create one when told not to.
    guild = EmptyGuild()
    channel = await na.alert_channel(guild, {**settings, "create_channel": 0})
    check("unless that was switched off", channel is None)
    check("and then it creates nothing", guild.created == [])


async def run():
    from utils import nuke_alert as na

    test_wording(na)
    await test_dm_spam(na)
    await test_incident_grouping(na)
    test_self_action(na)
    test_listener_guards()
    await test_module_reports()
    test_blind_reporting()
    test_no_stale_wording()
    test_buttons(na)
    await test_buttons_in_report(na)
    await test_alert_channel_survives(na)

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
