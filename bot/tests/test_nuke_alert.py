#!/usr/bin/env python3
"""
Anti-nuke reporting and the partner-bot handshake.

What this pins down:

  * The seventeen anti-nuke modules used to do everything in silence.
    `except discord.Forbidden: return` meant "saw the attack, could not
    stop it, said nothing" — indistinguishable from "nothing happened"
    and from "anti-nuke is off". All three are now reported apart.
  * The alert has to reach somebody even when the attacker deleted every
    channel, which is the situation it exists for.
  * The handshake token has to be forgeable-proof: without a signature
    anybody could append `?state=university-bot` to their own invite.

Run:  python3 tests/test_nuke_alert.py
"""

import asyncio
import os
import sys
import tempfile
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
os.environ["PARTNER_HANDSHAKE_SECRET"] = "test-secret-123"
warnings.filterwarnings("ignore")

import discord  # noqa: E402

GUILD = 4242


class FakeChannel:
    def __init__(self, cid, name, writable=True):
        self.id, self.name = cid, name
        self.writable = writable
        self.sent: list = []
        self.deleted = False

    def permissions_for(self, _m):
        return discord.Permissions.all() if self.writable else discord.Permissions.none()

    async def send(self, content=None, view=None, **kw):
        if not self.writable:
            raise discord.Forbidden(
                type("R", (), {"status": 403, "reason": "x"})(), "no"
            )
        self.sent.append({"content": content, "view": view})
        return type("M", (), {"id": 1, "jump_url": "https://d/1"})()

    async def delete(self, reason=None):
        self.deleted = True


class FakeMember:
    def __init__(self, uid, name):
        self.id, self.name = uid, name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.dms: list = []

    def __str__(self):
        return self.name

    async def send(self, content=None, view=None, **kw):
        self.dms.append(view or content)


class FakeGuild:
    def __init__(self, permissions=None, channels=None):
        self.id, self.name = GUILD, "Testserver"
        self.owner_id = 99
        self.owner = FakeMember(99, "Inhaber")
        self.text_channels = channels if channels is not None else [
            FakeChannel(1, "allgemein")
        ]
        self.system_channel = self.text_channels[0] if self.text_channels else None
        self.created: list = []

        perms = permissions if permissions is not None else discord.Permissions.all()
        self.me = type("Me", (), {"guild_permissions": perms})()

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == int(cid)), None)

    async def create_text_channel(self, name, overwrites=None, reason=None, topic=None):
        if not self.me.guild_permissions.manage_channels:
            raise discord.Forbidden(
                type("R", (), {"status": 403, "reason": "x"})(), "no"
            )
        channel = FakeChannel(900 + len(self.created), name)
        self.text_channels.append(channel)
        self.created.append(channel)
        return channel

    @property
    def default_role(self):
        return type("R", (), {"id": 0})()


class FakeBot:
    user = type("U", (), {"id": 1, "name": "Bot"})()

    def __init__(self, guild):
        self.guilds = [guild]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    from utils import nuke_alert
    from utils import partner_bot

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    def reset_cooldown():
        # One report per guild per 20s in real use; the tests need each
        # scenario to actually send.
        nuke_alert._last_alert.clear()

    # ══ The three outcomes read differently ═══════════════════════
    stopped = nuke_alert._describe(nuke_alert.OUTCOME_STOPPED, "channel_create")
    no_perms = nuke_alert._describe(nuke_alert.OUTCOME_NO_PERMS, "channel_create", "Kanäle verwalten")
    disabled = nuke_alert._describe(nuke_alert.OUTCOME_DISABLED, "channel_create")

    check("a stopped attack reads as success", stopped[2] == "success", stopped[2])
    check("a failed defence reads as an error", no_perms[2] == "error", no_perms[2])
    check("anti-nuke being off reads as a warning", disabled[2] == "warning", disabled[2])
    check("all three say something different",
          len({stopped[0], no_perms[0], disabled[0]}) == 3,
          f"{stopped[0]} / {no_perms[0]} / {disabled[0]}")
    check("the failed one names the missing permission",
          "Kanäle verwalten" in no_perms[1], no_perms[1][:80])
    check("the disabled one says how to switch it on",
          "antinuke enable" in disabled[1], disabled[1][:80])
    check("the action is named in plain German",
          "Kanal erstellt" in stopped[1], stopped[1][:60])

    # ══ Missing permissions are spotted ═══════════════════════════
    full = FakeGuild()
    check("a fully permitted bot reports nothing missing",
          nuke_alert.missing_permissions(full) == [], str(nuke_alert.missing_permissions(full)))

    weak = discord.Permissions.none()
    weak.send_messages = True
    limited = FakeGuild(permissions=weak)
    missing = nuke_alert.missing_permissions(limited)
    check("a bot without rights reports them all", len(missing) == 6, str(missing))
    check("banning is named", "Mitglieder bannen" in missing, str(missing))
    check("the audit log is named", "Audit-Log einsehen" in missing, str(missing))

    # ══ Finding somewhere to report ═══════════════════════════════
    async def scenario(guild, settings=None):
        return await nuke_alert.alert_channel(
            guild, settings or dict(nuke_alert.DEFAULTS)
        )

    guild = FakeGuild()
    channel = asyncio.run(scenario(guild))
    check("with a normal channel it uses that one",
          channel is not None and channel.name == "allgemein",
          channel.name if channel else "None")

    # A configured channel wins.
    guild = FakeGuild(channels=[FakeChannel(1, "allgemein"), FakeChannel(2, "mod-log")])
    channel = asyncio.run(scenario(guild, {**nuke_alert.DEFAULTS, "channel_id": 2}))
    check("the configured channel is preferred",
          channel is not None and channel.id == 2, str(channel.id if channel else None))

    # The configured one was deleted mid-attack.
    guild = FakeGuild(channels=[FakeChannel(1, "mod-log")])
    channel = asyncio.run(scenario(guild, {**nuke_alert.DEFAULTS, "channel_id": 999}))
    check("a deleted target channel falls back to a log channel",
          channel is not None and channel.name == "mod-log",
          channel.name if channel else "None")

    # Everything unwritable, but the bot may create channels: the whole
    # point of the feature.
    guild = FakeGuild(channels=[FakeChannel(1, "allgemein", writable=False)])
    channel = asyncio.run(scenario(guild))
    check("with no writable channel it creates one",
          channel is not None and channel.name == nuke_alert.ALERT_CHANNEL_NAME,
          channel.name if channel else "None")
    check("and it really was created", len(guild.created) == 1)

    # Same, but not allowed to create anything.
    no_manage = discord.Permissions.all()
    no_manage.manage_channels = False
    guild = FakeGuild(permissions=no_manage,
                      channels=[FakeChannel(1, "x", writable=False)])
    check("without the permission to create, it gives up quietly",
          asyncio.run(scenario(guild)) is None)

    # Creation switched off by the server.
    guild = FakeGuild(channels=[FakeChannel(1, "x", writable=False)])
    channel = asyncio.run(scenario(guild, {**nuke_alert.DEFAULTS, "create_channel": 0}))
    check("a server can forbid the automatic channel", channel is None)

    # An earlier attack already made one — do not pile them up.
    guild = FakeGuild(channels=[
        FakeChannel(1, "allgemein", writable=False),
        FakeChannel(2, nuke_alert.ALERT_CHANNEL_NAME),
    ])
    channel = asyncio.run(scenario(guild))
    check("an existing alert channel is reused, not duplicated",
          channel is not None and channel.id == 2 and len(guild.created) == 0,
          str(len(guild.created)))

    # ══ The report itself ═════════════════════════════════════════
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)

        guild = FakeGuild()
        bot = FakeBot(guild)
        attacker = FakeMember(50, "Angreifer")

        def reports(channel):
            """Beitraege ohne die Wiederherstellungs-Karte."""
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

        # ── Regel 1: nichts ausgerichtet -> gar nichts ────────────
        #
        # Frueher meldete der Bot auch dann, wenn ihm ein Recht fehlte
        # oder er die Audit-Logs nicht lesen konnte. Genau in dem
        # Moment ist eine Meldung aber nur Laerm: der Angriff laeuft
        # weiter, und niemand wird geschuetzt.
        reset_cooldown()
        for outcome in (nuke_alert.OUTCOME_NO_PERMS,
                        nuke_alert.OUTCOME_BLIND,
                        nuke_alert.OUTCOME_DISABLED):
            asyncio.run(nuke_alert.report(
                bot, guild, "channel_create", outcome, executor=attacker,
            ))
        check("machtlos: nichts im Kanal",
              len(reports(guild.text_channels[0])) == 0,
              str(len(reports(guild.text_channels[0]))))
        check("machtlos: keine DM", len(guild.owner.dms) == 0,
              str(len(guild.owner.dms)))
        stumm = asyncio.run(nuke_alert.incidents(GUILD, 10))
        check("machtlos: nicht einmal ein Logeintrag",
              len(stumm) == 0, str(len(stumm)))

        # ── Regel 4: eine Rollenvergabe ist kein Nuke ─────────────
        #
        # Sie gehoert in den Verlauf -- aber sie rechtfertigt keinen
        # Kanal, keinen Alarm und keine DM.
        reset_cooldown()
        asyncio.run(nuke_alert.report(
            bot, guild, "member_update", nuke_alert.OUTCOME_STOPPED,
            executor=attacker, banned=True,
        ))
        check("Rollenvergabe: kein Alarm im Kanal",
              len(reports(guild.text_channels[0])) == 0,
              str(len(reports(guild.text_channels[0]))))
        check("Rollenvergabe: keine DM", len(guild.owner.dms) == 0,
              str(len(guild.owner.dms)))
        rows = asyncio.run(nuke_alert.incidents(GUILD, 10))
        check("Rollenvergabe: aber ein Logeintrag", len(rows) == 1,
              str(len(rows)))

        # ── Ein echter Nuke wird gemeldet ─────────────────────────
        reset_cooldown()
        guild2 = FakeGuild()
        bot2 = FakeBot(guild2)
        asyncio.run(nuke_alert.report(
            bot2, guild2, "channel_delete", nuke_alert.OUTCOME_STOPPED,
            executor=attacker, banned=True,
        ))
        sent = reports(guild2.text_channels[0])
        check("echter Nuke: Meldung im Kanal", len(sent) == 1, str(len(sent)))

        # ── Regel 3 + 5: die DM ───────────────────────────────────
        #
        # Nur bei einem echten Nuke UND nur, wenn wirklich jemand
        # gebannt wurde.
        check("Nuke mit Bann: DM geht raus", len(guild2.owner.dms) == 1,
              str(len(guild2.owner.dms)))

        reset_cooldown()
        guild3 = FakeGuild()
        bot3 = FakeBot(guild3)
        asyncio.run(nuke_alert.report(
            bot3, guild3, "channel_delete", nuke_alert.OUTCOME_PARTIAL,
            executor=attacker, banned=False,
        ))
        check("Nuke ohne Bann: keine DM", len(guild3.owner.dms) == 0,
              str(len(guild3.owner.dms)))
        check("aber im Kanal steht es",
              len(reports(guild3.text_channels[0])) == 1)

        # Ein Nuke feuert Dutzende Ereignisse; eine Meldung genuegt.
        asyncio.run(nuke_alert.report(
            bot3, guild3, "channel_delete", nuke_alert.OUTCOME_PARTIAL,
            executor=attacker, banned=False,
        ))
        check("ein zweites Ereignis spammt nicht",
              len(reports(guild3.text_channels[0])) == 1,
              str(len(reports(guild3.text_channels[0]))))

        # Jeder Vorfall, der ueberhaupt gemeldet wird, steht im Verlauf.
        rows = asyncio.run(nuke_alert.incidents(GUILD, 10))
        check("incidents are recorded", len(rows) >= 1, str(len(rows)))
        # Was der Bot ausgerichtet hat, steht dabei.
        #
        # "no_perms" kommt hier bewusst NICHT mehr vor: nach Regel 1
        # wird gar nichts vermerkt, wenn der Bot nichts ausrichten
        # konnte. Ein Verlauf voller "konnte nicht" ist kein Verlauf,
        # sondern eine Fehlerliste -- und sie verdeckt die Eintraege,
        # auf die es ankommt.
        outcomes = {r["outcome"] for r in rows}
        check("the outcome is stored",
              outcomes >= {"stopped", "partial"}, str(outcomes))
        check("und Machtlosigkeit steht NICHT darin",
              "no_perms" not in outcomes and "blind" not in outcomes,
              str(outcomes))
        check("the attacker is recorded",
              any(r["executor_id"] == 50 for r in rows), str(rows[:1]))

        # Reporting must never break the defence it runs inside.
        broken = FakeGuild(channels=[])
        broken.me = None
        reset_cooldown()
        try:
            asyncio.run(nuke_alert.report(
                bot, broken, "ban", nuke_alert.OUTCOME_STOPPED, executor=attacker
            ))
            survived = True
        except Exception:
            survived = False
        check("a broken guild does not raise out of the reporter", survived)

        # Settings round-trip.
        saved = asyncio.run(nuke_alert.save_settings(
            GUILD, {"channel_id": 7, "dm_owner": 0, "clean_channels": 0}
        ))
        check("settings can be saved", saved["channel_id"] == 7, str(saved))
        loaded = asyncio.run(nuke_alert.get_settings(GUILD))
        check("they survive a reload", loaded["dm_owner"] == 0, str(loaded))
        check("a partial save keeps the rest",
              loaded["enabled"] == 1 and loaded["create_channel"] == 1, str(loaded))

        os.chdir(cwd)

    # ══ The handshake ═════════════════════════════════════════════
    check("the secret is picked up from the environment", partner_bot.is_configured())

    token = partner_bot.make_state(GUILD, 77)
    payload = partner_bot.read_state(token)
    check("a token round-trips", payload is not None and payload["g"] == str(GUILD),
          str(payload))
    check("it carries who asked", payload and payload["u"] == "77", str(payload))

    # This is the attack the signature exists for.
    body, _, signature = token.partition(".")
    forged = body + "." + ("A" * len(signature))
    check("a forged signature is rejected", partner_bot.read_state(forged) is None)

    tampered = partner_bot.make_state(999, 77).partition(".")[0] + "." + signature
    check("swapping the payload under a valid signature is rejected",
          partner_bot.read_state(tampered) is None)

    check("nonsense is rejected", partner_bot.read_state("garbage") is None)

    # A correctly signed token from a *different* sender must not pass:
    # the template bot serves more than one source.
    import hashlib as _hl
    import hmac as _hm
    import json as _js
    foreign = _js.dumps(
        {"g": str(GUILD), "u": "77", "t": int(time.time()), "src": "someone-else"},
        separators=(",", ":"),
    ).encode()
    fbody = partner_bot._b64(foreign)
    fsig = partner_bot._b64(
        _hm.new(b"test-secret-123", fbody.encode(), _hl.sha256).digest()
    )
    check("a properly signed token from another sender is rejected",
          partner_bot.read_state(f"{fbody}.{fsig}") is None)

    check("our own source string is what the prompt documents",
          partner_bot.SOURCE == "university-bot", partner_bot.SOURCE)
    check("an empty token is rejected", partner_bot.read_state("") is None)

    # Old links must stop working.
    import json as _json
    stale = {
        "g": str(GUILD), "u": "77", "src": partner_bot.SOURCE,
        "t": int(time.time()) - partner_bot.MAX_AGE - 60,
    }
    body = partner_bot._b64(_json.dumps(stale, separators=(",", ":")).encode())
    import hashlib
    import hmac as _hmac
    signature = partner_bot._b64(
        _hmac.new(b"test-secret-123", body.encode(), hashlib.sha256).digest()
    )
    check("an expired token is rejected",
          partner_bot.read_state(f"{body}.{signature}") is None)

    # Without a shared secret nothing can be verified, so nothing is.
    os.environ.pop("PARTNER_HANDSHAKE_SECRET")
    check("without the secret no token verifies",
          partner_bot.read_state(token) is None)
    check("and the module says it is not configured",
          partner_bot.is_configured() is False)
    os.environ["PARTNER_HANDSHAKE_SECRET"] = "test-secret-123"

    # ══ The invite link ═══════════════════════════════════════════
    url = partner_bot.invite_url("123456", guild_id=GUILD, user_id=77)
    check("the link points at Discord", url.startswith("https://discord.com/oauth2/authorize"))
    check("it carries the client id", "client_id=123456" in url, url[:120])
    check("it preselects the server", f"guild_id={GUILD}" in url)
    check("it stops the server being changed by accident",
          "disable_guild_select=true" in url)
    check("it carries a signed state", "state=" in url)

    state = url.split("state=")[1].split("&")[0]
    from urllib.parse import unquote
    check("the state in the link verifies",
          partner_bot.read_state(unquote(state)) is not None)

    # ══ Pending handoffs ══════════════════════════════════════════
    partner_bot.handoffs.remember(GUILD, {"u": "77"})
    check("a handoff is remembered", partner_bot.handoffs.peek(GUILD) is not None)
    claimed = partner_bot.handoffs.claim(GUILD)
    check("claiming returns it", claimed is not None and claimed["u"] == "77")
    check("and removes it, so it cannot be replayed",
          partner_bot.handoffs.claim(GUILD) is None)

    partner_bot.handoffs.remember(GUILD, {"u": "1"})
    partner_bot.handoffs._pending[GUILD]["seen"] = time.time() - partner_bot.MAX_AGE - 10
    check("a stale handoff is dropped", partner_bot.handoffs.claim(GUILD) is None)

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
