#!/usr/bin/env python3
"""
The status bot's four new pieces: outage alerts, uptime history,
maintenance mode, and the public status page.

Each carries a way of being wrong that is worse than not having it:

  * An **outage alert** that fires on a normal deploy trains everybody
    to ignore the channel, and then the real outage is ignored too. It
    only fires on the two transitions that matter, and never during
    maintenance.
  * An **uptime figure** computed from twenty minutes of data, or from a
    record with holes in it, is a number that looks authoritative and is
    not. It is omitted below an hour of record, and a partial record is
    labelled as such.
  * **Maintenance mode** must not hide what is actually happening -- it
    changes the headline, not the readings.
  * A **status page** that says "all fine" because it could not reach
    anything is the one failure a status page must not have.

Run:  python3 tests/test_status_history.py
"""

import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
STATUS = os.path.join(ROOT, "statusbot")
DASHBOARD = os.path.join(ROOT, "dashboard")

sys.path.insert(0, BOT)
sys.path.insert(0, STATUS)

DAY = 86400

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path) -> str:
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read()


def fresh_history():
    """A history module pointed at an empty directory."""
    import importlib

    workspace = tempfile.mkdtemp()
    os.environ["STATUS_DATA_DIR"] = workspace
    import history
    importlib.reload(history)
    return history, workspace


# ══════════════════════════════════════════════════════════════════════
#  The uptime record
# ══════════════════════════════════════════════════════════════════════


def test_history():
    print("\nThe uptime record")

    history, workspace = fresh_history()
    try:
        now = time.time()

        check("nothing recorded means nothing claimed",
              history.summary(now).get("known") is False,
              "a percentage from an empty record would be invented")

        # An hour of record is not enough for a percentage.
        history.record("online", now - 600)
        result = history.summary(now)
        check("ten minutes is still not enough",
              result.get("known") is False, str(result))

        # A week: up throughout except one hour.
        history, workspace = fresh_history()
        history.record("online", now - 7 * DAY)
        history.record("down", now - 2 * DAY)
        history.record("online", now - 2 * DAY + 3600)

        result = history.summary(now)
        check("a week of record gives a figure",
              result.get("known") is True, str(result))
        check("and the arithmetic is right",
              abs(result["percent"] - 99.4) < 0.05,
              f"{result['percent']} -- one hour down in seven days is 99.40%")
        check("the outage is counted", result["outage_count"] == 1,
              str(result["outage_count"]))
        check("with its length", abs(result["outage_seconds"] - 3600) < 5,
              str(result["outage_seconds"]))
        check("and the window is marked complete",
              result["complete"] is True, str(result))

        # "starting" is not downtime. Counting it would make every
        # deploy look like an incident.
        history, workspace = fresh_history()
        history.record("online", now - 7 * DAY)
        history.record("starting", now - 3 * DAY)
        history.record("online", now - 3 * DAY + 120)
        result = history.summary(now)
        check("a deploy does not count against uptime",
              result["percent"] == 100.0,
              f"{result['percent']} -- 'starting' is booting, not broken")
        check("and is not reported as an outage",
              result["outage_count"] == 0, str(result))

        # A record that starts mid-window must not be presented as
        # covering the whole window.
        history, workspace = fresh_history()
        history.record("online", now - 2 * DAY)
        result = history.summary(now)
        check("a partial record is flagged as partial",
              result["known"] is True and result["complete"] is False,
              str(result))

        # One row per change, not per poll.
        history, workspace = fresh_history()
        for index in range(5):
            history.record("online", now - 5000 + index)
        import sqlite3

        connection = sqlite3.connect(history.DB_PATH)
        rows = connection.execute(
            "SELECT COUNT(*) FROM state_changes"
        ).fetchone()[0]
        connection.close()
        check("each change is one row", rows == 5, str(rows))

        source = read(os.path.join(STATUS, "status_bot.py"))
        body = source.split("async def watch_loop")[1]
        check("and the loop only records on a change",
              "history.record(new_state" in body
              and body.index("history.record") > body.index("if new_state != self.state"),
              "recording every poll is 2,880 rows a day to say nothing "
              "happened")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        os.environ.pop("STATUS_DATA_DIR", None)


def test_history_survives_nothing_gracefully():
    """
    An unwritable directory must not stop the watcher.

    Its job is to keep watching. Losing the record is a nuisance;
    crashing because of it defeats the purpose.
    """
    print("\nThe record failing is not fatal")

    import importlib

    os.environ["STATUS_DATA_DIR"] = "/proc/cannot-write-here"
    import history
    importlib.reload(history)

    try:
        history.record("online")
        check("recording into an unwritable place does not raise", True)
    except Exception as err:  # noqa: BLE001
        check("recording into an unwritable place does not raise", False,
              f"{type(err).__name__}: {err}")

    result = history.summary()
    check("and the summary says it does not know",
          result.get("known") is False, str(result))

    check("persistence is checked against the parent, not /",
          "os.path.dirname(DATA_DIR" in read(os.path.join(STATUS, "history.py")),
          "comparing with / gets this wrong in a container where / is "
          "itself an overlay")

    os.environ.pop("STATUS_DATA_DIR", None)
    importlib.reload(history)


# ══════════════════════════════════════════════════════════════════════
#  Announcing an outage
# ══════════════════════════════════════════════════════════════════════


def test_storage_is_reported_at_boot():
    """
    The bot must say at start-up whether the history will survive.

    Railway logs the *host* path of a mounted volume, which says nothing
    about where it landed inside the container. If the mount point is
    not exactly STATUS_DATA_DIR, the bot writes into the container, the
    record is wiped on every deploy, and nothing mentions it -- the
    panel simply never shows an uptime figure and nobody knows why.
    """
    print("\nWhere the history lives is reported")

    import importlib
    import io
    from contextlib import redirect_stdout

    source = read(os.path.join(STATUS, "status_bot.py"))
    check("there is a report at boot",
          "def report_storage" in source, "")
    check("and on_ready calls it",
          "self.report_storage()" in source,
          "a check nothing calls reports nothing")

    workspace = tempfile.mkdtemp()
    os.environ["STATUS_DATA_DIR"] = workspace
    import history
    importlib.reload(history)
    import status_bot as sb
    importlib.reload(sb)

    try:
        # A plain directory is not a volume.
        out = io.StringIO()
        with redirect_stdout(out):
            sb.StatusBot.report_storage()
        text = out.getvalue()
        check("a plain directory is called out",
              "NOT on a volume" in text, text.strip())
        check("and the path is named",
              workspace in text, text.strip())
        check("and it says what to do",
              "STATUS_DATA_DIR" in text or "Mount a Railway volume" in text,
              text.strip())

        # The positive case too. Only testing the warning let a
        # mutation through that removed the confirmation entirely --
        # silence then means "no volume" and "volume fine" alike, which
        # is the ambiguity this whole line exists to remove.
        original = history.storage_is_persistent
        history.storage_is_persistent = lambda: True
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                sb.StatusBot.report_storage()
            text = out.getvalue()
            check("a real volume is confirmed, not passed over silently",
                  text.strip() != "",
                  "no output means the same as no volume")
            check("and the confirmation says it survives",
                  "survives" in text or "volume" in text, text.strip())
            check("without warning about anything",
                  "NOT on a volume" not in text, text.strip())
        finally:
            history.storage_is_persistent = original

        # A directory that does not exist at all.
        os.environ["STATUS_DATA_DIR"] = "/tmp/definitely-not-here-xyz"
        importlib.reload(history)
        importlib.reload(sb)
        out = io.StringIO()
        with redirect_stdout(out):
            sb.StatusBot.report_storage()
        check("a missing directory is mentioned as missing",
              "does not exist" in out.getvalue(), out.getvalue().strip())
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        os.environ.pop("STATUS_DATA_DIR", None)
        importlib.reload(history)
        importlib.reload(sb)


def test_announcements():
    print("\nAnnouncing an outage")

    source = read(os.path.join(STATUS, "status_bot.py"))
    body = source.split("async def announce")[1].split("@staticmethod")[0]

    check("there is an announce method", bool(body.strip()), "")
    check("it fires when the state becomes down",
          'if now == "down":' in body, "")
    check("and when it recovers",
          'previous == "down"' in body, "")
    check("the recovery message says how long it lasted",
          "_duration(outage)" in body,
          "'it is back' without a duration tells nobody anything")

    # The important restraint: everything else is silent.
    check("nothing else is announced",
              "        else:\n            return" in body,
          "online->starting on a deploy must not ping anybody")
    check("and maintenance is silent",
          "if self.maintenance:\n            return" in body,
          "an announced restart announcing itself is noise")

    # The ping, and permission for exactly that ping.
    import importlib

    import status_bot as sb

    for value, expect_content in (
        ("", ""),
        ("everyone", "@everyone"),
        ("123456789012345678", "<@&123456789012345678>"),
        ("nonsense", ""),
    ):
        os.environ["STATUS_ALERT_ROLE_ID"] = value
        importlib.reload(sb)
        content, mentions = sb.StatusBot.alert_mention()
        check(f"role {value!r} gives content {expect_content!r}",
              content == expect_content, repr(content))

        if value == "everyone":
            check("everyone is actually permitted",
                  mentions.everyone is True, str(mentions))
            # AllowedMentions.all() also sets everyone=True and would
            # have passed the check above -- while permitting every
            # user and role mention in the text as well. The point of
            # naming the ping is that nothing else can slip through.
            check("but users and roles still cannot be pinged",
                  mentions.users is False and mentions.roles is False,
                  f"{mentions} -- .all() would satisfy 'everyone is "
                  "permitted' and open everything else too")
        elif value == "123456789012345678":
            check("the role is permitted and nothing else",
                  mentions.everyone is False and mentions.users is False
                  and len(mentions.roles or []) == 1,
                  str(mentions))
        else:
            check(f"{value!r} pings nobody",
                  mentions.everyone is False and not mentions.roles,
                  str(mentions))

    os.environ.pop("STATUS_ALERT_ROLE_ID", None)
    importlib.reload(sb)

    check("mentions are always set explicitly",
          "allowed_mentions=mentions" in body,
          "a later edit that puts a username in the text must not turn "
          "into an accidental ping")

    # The duration wording.
    check("seconds read as seconds", "Sekunden" in sb._duration(30),
          sb._duration(30))
    check("minutes read as minutes", sb._duration(300) == "5 Minuten",
          sb._duration(300))
    check("one minute is singular", sb._duration(60) == "1 Minute",
          sb._duration(60))
    check("hours include the minutes",
          sb._duration(3900) == "1 Stunde 5 Minuten", sb._duration(3900))
    check("and days are days", sb._duration(2 * DAY).startswith("2 Tage"),
          sb._duration(2 * DAY))


# ══════════════════════════════════════════════════════════════════════
#  Maintenance
# ══════════════════════════════════════════════════════════════════════


def test_maintenance():
    print("\nMaintenance mode")

    import discord  # noqa: F401  (view import needs it loaded)
    from view import StatusView

    class Health:
        reachable = True
        bot_ready = True
        dashboard = "online"
        latency_ms = 120.0
        status_code = 200
        error = None
        checked_at = time.time()

    def render(view):
        out = []

        def walk(item):
            content = getattr(item, "content", None)
            if isinstance(content, str):
                out.append(content)
            accessory = getattr(item, "accessory", None)
            if accessory is not None:
                walk(accessory)
            for child in getattr(item, "children", None) or []:
                walk(child)

        for child in view.children:
            walk(child)
        return "\n".join(out)

    normal = render(StatusView(brand="B", state="online", health=Health(),
                               since=time.time()))
    check("normally there is no maintenance banner",
          "Wartung" not in normal, normal[:80])

    during = render(StatusView(
        brand="B", state="online", health=Health(), since=time.time(),
        maintenance=True, maintenance_note="Datenbank-Umzug",
    ))
    check("maintenance changes the headline",
          "Geplante Wartung" in during, during[:80])
    check("and shows the reason",
          "Datenbank-Umzug" in during, during[:200])
    check("but the readings stay real",
          "HTTP 200" in during and "120 ms" in during,
          "maintenance is not a reason to hide what is happening")

    # It has to win even while the bot is genuinely unreachable --
    # that is the entire point during a restart.
    class Down:
        reachable = False
        bot_ready = False
        dashboard = "unbekannt"
        latency_ms = None
        status_code = None
        error = "Zeitüberschreitung"
        checked_at = time.time()

    restarting = render(StatusView(
        brand="B", state="down", health=Down(), since=time.time(),
        maintenance=True,
    ))
    check("a restart during maintenance does not say 'Störung'",
          "Geplante Wartung" in restarting
          and not restarting.startswith("# 🔴"),
          restarting[:80])
    check("while still showing the bot is unreachable",
          "Zeitüberschreitung" in restarting, restarting[:250])

    source = read(os.path.join(STATUS, "status_bot.py"))
    check("there is a /wartung command", 'name="wartung"' in source, "")
    check("it is limited to people who manage the server",
          "manage_guild" in source,
          "this changes what every member sees")
    check("and the reply is only shown to whoever ran it",
          source.split('name="wartung"')[1].count("ephemeral=True") >= 2, "")


# ══════════════════════════════════════════════════════════════════════
#  The public status page
# ══════════════════════════════════════════════════════════════════════


def test_public_endpoint():
    print("\nThe public JSON endpoint")

    source = read(os.path.join(STATUS, "status_bot.py"))
    body = source.split("async def handle_public_status")[1].split(
        "    app = web.Application()")[0]

    check("there is a public endpoint", bool(body.strip()), "")
    check("it is registered", '"/status.json"' in source, "")
    check("it needs no api key",
          "X-API-Key" not in body,
          "this has to work for somebody who is not on the Discord "
          "server, and when Discord itself is the problem")
    check("CORS is open",
          "Access-Control-Allow-Origin" in body, "")
    check("it carries the uptime figures",
          "history.summary()" in body, "")
    check("and the partner flag comes along",
          "bot.partner" in body,
          "a website reading this must be able to tell a generated "
          "figure from a measured one")


def test_status_page():
    print("\nThe status page on the website")

    page = read(os.path.join(DASHBOARD, "app/status/page.tsx"))
    check("the page exists", bool(page), "")
    if not page:
        return

    check("it is never cached",
          'export const dynamic = "force-dynamic"' in page
          and "revalidate = 0" in page,
          "a five minute old status says 'fine' during an outage")
    check("it asks the status bot, not the main bot",
          "STATUS_BOT_URL" in page,
          "asking the broken thing whether it is broken always answers "
          "'fine' or nothing")
    check("the fetch cannot hang the page",
          "AbortSignal.timeout" in page, "")

    # The failure that matters most. Checked on the branch, not just
    # the string: the message can sit in the file while the `if` that
    # reaches it has been removed, which is exactly what slipped past
    # the first version of this test.
    check("an unreachable service says so",
          "nicht abrufbar" in page,
          "a status page that claims 'all fine' because it reached "
          "nothing is the one thing it must never do")
    check("and there is a branch that actually reaches that message",
          re.search(r"if\s*\(\s*!\s*data\s*\)", page) is not None,
          "the text is worthless if nothing renders it")
    # Whitespace collapsed before searching: the formatter breaks lines
    # wherever it likes, so a phrase search fails on prose that is
    # perfectly correct. Third time this has bitten in this project.
    prose = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    check("and does not blame the bot for it",
          "kann auch der Wächter selbst sein" in prose,
          "the watcher being down says nothing about the bot")

    check("unchecked rows are grey, not red",
          'tone="unknown"' in page or '"unknown"' in page,
          "red claims we looked; we did not")
    check("the uptime section is conditional",
          "uptime?.known" in page,
          "no record means no percentage")
    check("a partial record is labelled",
          "seit Beginn der Aufzeichnung" in page, "")


def main():
    test_history()
    test_history_survives_nothing_gracefully()
    test_storage_is_reported_at_boot()
    test_announcements()
    test_maintenance()
    test_public_endpoint()
    test_status_page()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
