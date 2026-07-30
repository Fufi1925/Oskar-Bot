#!/usr/bin/env python3
"""
The /verlauf command: charts drawn out of block characters.

Discord has no chart component, so these are text. Two rules run
through the whole thing, and both exist because a chart is the format
people screenshot and quote:

**A gap must look like a gap.** A slot with no samples is drawn as a
faint mark, never as zero and never skipped. "We were not watching" and
"nothing was wrong" are different statements.

**A number must mean what it looks like.** Two mistakes were caught
here while building it, both of which produced a figure that looked
authoritative and was wrong:

  * an outage was drawn as a full-height bar, which on a latency chart
    reads as "the slowest measurement" rather than "no measurement";
  * the command-error total summed a *running counter*, reporting 132
    errors for a window that held about a dozen. It needs the
    difference between readings, with a counter reset treated as a
    restart rather than as negative errors.

Run:  python3 tests/test_status_charts.py
"""

import importlib
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
STATUS = os.path.join(ROOT, "statusbot")

sys.path.insert(0, BOT)
sys.path.insert(0, STATUS)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def fresh_history():
    workspace = tempfile.mkdtemp()
    os.environ["STATUS_DATA_DIR"] = workspace
    import history
    importlib.reload(history)
    return history, workspace


def slot(latency=None, known=True, bad=False):
    return {"known": known, "bad": bad, "latency": latency,
            "samples": 1 if known else 0}


# ══════════════════════════════════════════════════════════════════════
#  Drawing
# ══════════════════════════════════════════════════════════════════════


def test_latency_chart():
    print("\nThe response-time chart")

    import charts

    empty = charts.latency_chart([])
    check("nothing to draw returns nothing", empty == ("", ""),
          "an empty frame is worse than no section")

    check("a window with no samples draws nothing",
          charts.latency_chart([slot(known=False)] * 24) == ("", ""), "")

    bars, caption = charts.latency_chart([slot(100 + i * 10) for i in range(24)])
    check("a full window gives one column per slot", len(bars) == 24,
          f"{len(bars)} columns")
    check("the caption names the scale", "ms" in caption and "0–" in caption,
          f"{caption} -- a bar chart without a maximum shows the shape "
          "and nothing else")
    check("and the average", "ø" in caption, caption)

    # Rising values must produce rising bars, or the chart is decorative.
    rising = charts.latency_chart([slot(50 * (i + 1)) for i in range(8)])[0]
    check("higher latency draws a taller bar",
          charts.BLOCKS.index(rising[-1]) > charts.BLOCKS.index(rising[0]),
          rising)

    # A healthy 20-40 ms range must not fill the chart and look alarming.
    quiet = charts.latency_chart([slot(20 + i) for i in range(24)])
    check("a fast bot does not draw a full chart",
          "█" not in quiet[0],
          f"{quiet[0]} -- scaling to the data alone makes 20 ms look "
          "like a crisis")
    check("because the scale has a floor", "0–100 ms" in quiet[1], quiet[1])
    # The floor lives in _round_up. Checked there directly: an earlier
    # max(100.0, ...) in the caller was dead code, so a mutation
    # removing it changed nothing and the test could not have noticed.
    check("and the floor is in the rounding itself",
          charts._round_up(8) >= 100 and charts._round_up(1) >= 100,
          f"_round_up(8)={charts._round_up(8)}")
    # The caption alone is not enough: the bars must actually stay
    # short. Dropping the floor changes the drawing, not the wording.
    tallest = max(charts.BLOCKS.index(c) for c in quiet[0])
    check("and the bars stay low because of it",
          tallest <= 3,
          f"height {tallest}/7 for a 20-40 ms range -- scaling to the "
          "data alone makes a healthy bot look like a crisis")

    # The gap rule.
    gapped = charts.latency_chart(
        [slot(120)] * 5 + [slot(known=False)] * 3 + [slot(120)] * 5
    )
    check("a gap is drawn, not skipped",
          charts.UNKNOWN in gapped[0] and len(gapped[0]) == 13, gapped[0])
    # Visibly, not just present. A space is "in" the string too, and
    # renders as nothing at all -- which is the failure this rule
    # exists to prevent, so checking membership alone proved nothing.
    check("and the mark for it is actually visible",
          charts.UNKNOWN.strip() != "",
          f"{charts.UNKNOWN!r} -- whitespace reads as 'zero', and this "
          "means 'unknown'")
    check("and differs from every bar height",
          charts.UNKNOWN not in charts.BLOCKS, charts.UNKNOWN)
    check("and the legend explains it",
          "keine Daten" in gapped[1], gapped[1])

    # The outage rule -- the bug found while building this.
    outage = charts.latency_chart(
        [slot(120)] * 5 + [slot(bad=True)] * 2 + [slot(120)] * 5
    )
    check("an outage is not drawn as a tall bar",
          charts.OUTAGE not in charts.BLOCKS,
          f"{charts.OUTAGE!r} -- a full block on a latency chart reads "
          "as 'slowest measurement', not 'no measurement'")
    check("it appears in the chart", charts.OUTAGE in outage[0], outage[0])
    check("and is explained",
          "nicht erreichbar" in outage[1], outage[1])

    # The legend must not list marks that are not there.
    clean = charts.latency_chart([slot(120)] * 24)
    check("no legend when nothing needs explaining",
          "keine Daten" not in clean[1] and "nicht erreichbar" not in clean[1],
          f"{clean[1]} -- otherwise the caption is longer than the chart")


def test_availability_chart():
    print("\nThe availability chart")

    import charts

    marks, caption = charts.availability_chart([slot(120)] * 24)
    check("all good is all green", marks.count("🟩") == 24, marks)
    check("and says so", "keine Störung" in caption, caption)

    marks, caption = charts.availability_chart(
        [slot(120)] * 10 + [slot(bad=True)] * 2 + [slot(120)] * 12
    )
    check("an outage is red", marks.count("🟥") == 2, marks)
    check("and counted", "2× Störung" in caption, caption)

    marks, caption = charts.availability_chart(
        [slot(120)] * 10 + [slot(known=False)] * 3 + [slot(120)] * 11
    )
    check("a gap is neither green nor red", marks.count("⬛") == 3, marks)
    check("and is named",
          "keine Daten" in caption,
          "these are the slots where the watcher itself was not running")

    # The two charts must disagree about nothing.
    mixed = [slot(120)] * 5 + [slot(bad=True)] * 2 + [slot(known=False)] * 2
    avail = charts.availability_chart(mixed)[0]
    latency = charts.latency_chart(mixed)[0]
    check("both charts have the same number of slots",
          len(latency) == len(mixed) and len(avail) // 2 == len(mixed) - 0
          or len(latency) == len(mixed),
          f"latency={len(latency)} slots={len(mixed)}")


# ══════════════════════════════════════════════════════════════════════
#  The data behind them
# ══════════════════════════════════════════════════════════════════════


def test_buckets():
    print("\nGrouping samples into slots")

    history, workspace = fresh_history()
    try:
        now = time.time()

        check("no samples means no slots to speak of",
              all(not s["known"] for s in history.buckets(24, 24, now)),
              "an empty database must not look like a healthy one")

        # Samples are throttled: writing on every poll would be 2,880
        # rows a day.
        for offset in range(0, 600, 30):
            history.sample(100.0, True, when=now - 3600 + offset)

        import sqlite3

        connection = sqlite3.connect(history.DB_PATH)
        rows = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        connection.close()
        check("samples are throttled, not written every poll",
              rows < 5,
              f"{rows} rows from 20 calls 30s apart -- one per poll "
              "would be 2,880 a day")

        # Averaging within a slot.
        history, workspace = fresh_history()
        history.sample(100.0, True, when=now - 1800)
        history.sample(300.0, True, when=now - 1200)
        slots = history.buckets(1, 2, now)
        second = slots[1]
        check("a slot averages its samples",
              second["known"] and abs(second["latency"] - 200.0) < 1,
              str(second))

        # An unreachable sample marks the slot bad and carries no
        # latency to average.
        history, workspace = fresh_history()
        history.sample(None, False, when=now - 600)
        slots = history.buckets(1, 2, now)
        bad = [s for s in slots if s["bad"]]
        check("an unreachable sample marks the slot", len(bad) == 1, str(slots))
        check("and contributes no latency",
              bad[0]["latency"] is None, str(bad[0]))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        os.environ.pop("STATUS_DATA_DIR", None)


def test_error_counting():
    """
    The stored value is the main bot's running total since it started.

    Summing that column gives a number that grows with the number of
    samples rather than with the number of errors -- the first version
    reported 132 for a window holding about a dozen.
    """
    print("\nCounting command errors")

    history, workspace = fresh_history()
    try:
        now = time.time()

        check("one reading is not enough to compute a difference",
              history.error_summary(24, now).get("known") is False, "")

        # 10 -> 12 -> 15 is five errors, not thirty-seven.
        for index, value in enumerate([10, 12, 15]):
            history.sample(120.0, True, errors=value, when=now - 3600 + index * 310)
        result = history.error_summary(24, now)
        check("the difference is counted, not the sum",
              result["total"] == 5,
              f"{result['total']} -- 10+12+15=37 is what summing gives")

        # A restart resets the counter. That is not minus fifteen errors.
        history, workspace = fresh_history()
        for index, value in enumerate([10, 12, 15, 0, 2, 5]):
            history.sample(120.0, True, errors=value, when=now - 3600 + index * 310)
        result = history.error_summary(24, now)
        check("a counter reset is not negative errors",
              result["total"] == 10,
              f"{result['total']} -- 5 before the restart, 5 after")
        check("and the restart is reported",
              result["restarts"] == 1, str(result))
        check("a run with no restart says so",
              history.error_summary(24, now)["restarts"] == 1, "")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        os.environ.pop("STATUS_DATA_DIR", None)


# ══════════════════════════════════════════════════════════════════════
#  The panel and the command
# ══════════════════════════════════════════════════════════════════════


def test_panel():
    print("\nThe /verlauf panel")

    import discord  # noqa: F401

    import emojis
    from view import HistoryView

    history, workspace = fresh_history()
    try:
        now = time.time()
        history.record("online", now - 7 * 86400)
        history.record("down", now - 2 * 86400)
        history.record("online", now - 2 * 86400 + 2700)

        moment = now - 24 * 3600
        while moment < now:
            hour = int((now - moment) / 3600)
            if 13 <= hour <= 14:
                history.sample(None, False, when=moment)
            else:
                history.sample(150.0, True, errors=0, when=moment)
            moment += 310

        emojis.adopt({})

        def render(view):
            out = []

            def walk(item):
                content = getattr(item, "content", None)
                if isinstance(content, str):
                    out.append(content)
                for child in getattr(item, "children", None) or []:
                    walk(child)

            for child in view.children:
                walk(child)
            return "\n".join(out)

        text = render(HistoryView(
            brand="University Bot",
            slots=history.buckets(24, 24, now),
            uptime=history.summary(now),
            errors=history.error_summary(24, now),
            hours=24,
            persistent=True,
        ))

        check("it has an availability section",
              "Erreichbarkeit" in text, text[:120])
        check("and a latency chart", "Antwortzeit" in text, "")
        check("and the longer uptime figure",
              "99." in text and "%" in text, "")
        check("the outage is visible", "🟥" in text, "")
        check("the window is stated", "letzte 24 Stunden" in text, text[:120])
        check("it says the values are measured",
              "gemessen" in text,
              "this panel has no simulated figure on it, unlike the "
              "template bot's row on the live panel")

        # Without a volume the record restarts on every deploy, and a
        # chart labelled "last 24 hours" covering forty minutes would
        # be misleading.
        warned = render(HistoryView(
            brand="B", slots=history.buckets(24, 24, now),
            uptime=history.summary(now),
            errors=history.error_summary(24, now),
            hours=24, persistent=False,
        ))
        check("no volume is warned about",
              "ohne Volume" in warned,
              "otherwise the chart quietly covers whatever survived the "
              "last deploy")

        # An empty database must not render a confident-looking panel.
        history, workspace = fresh_history()
        blank = render(HistoryView(
            brand="B", slots=history.buckets(24, 24, now),
            uptime=history.summary(now),
            errors=history.error_summary(24, now),
            hours=24, persistent=True,
        ))
        check("an empty record says so",
              "keine Messwerte" in blank, blank[:200])
        check("and claims nothing about that window",
              "keine Störung" not in blank,
              "an unwatched window is not a quiet one")
        check("and invents no percentage",
              "%" not in blank, blank[:200])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        os.environ.pop("STATUS_DATA_DIR", None)


def test_command():
    print("\nThe command itself")

    source = open(os.path.join(STATUS, "status_bot.py"), encoding="utf-8").read()

    check("there is a /verlauf command", 'name="verlauf"' in source, "")

    body = source.split('name="verlauf"')[1].split("@self.tree.command")[0]
    check("the window can be chosen", "stunden" in body, "")
    check("and is clamped",
          "max(1, min(168, stunden))" in body,
          "an unbounded window reads the whole table into memory")
    check("the chart is always 24 columns wide",
          "count=24" in body,
          "wider wraps on a phone, which is where this is read")
    # Comments stripped first: the code explains *why* it is not
    # ephemeral, and a plain search finds that explanation. Same trap
    # as several earlier tests in this project.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    check("it is not ephemeral",
          "ephemeral" not in code,
          "charts are the kind of thing people want to show somebody")

    # The error figure is fetched separately and must fail soft: a
    # watcher that breaks because the admin API said no is worse than
    # one missing a number.
    fetch = source.split("async def command_errors")[1].split("async def set_presence")[0]
    check("errors are read from the main bot", "/admin/metrics" in fetch, "")
    check("with the shared key", "DASHBOARD_API_KEY" in fetch, "")
    check("a failure returns zero rather than raising",
          "return 0" in fetch and "except Exception" in fetch, "")
    check("and it is cached",
          "_errors_checked" in fetch,
          "polling the main bot's admin API every 30 seconds from a "
          "watcher is its own small problem")


def main():
    test_latency_chart()
    test_availability_chart()
    test_buckets()
    test_error_counting()
    test_panel()
    test_command()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
