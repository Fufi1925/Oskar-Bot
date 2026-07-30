# ╔══════════════════════════════════════════════════════════════════╗
# ║   What happened, and when                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The uptime record.

Until now the status bot kept nothing. That was deliberate -- the
service whose job is to still be running should carry as little as
possible -- but it means the panel can only ever say "right now", and
"how often does this actually break?" had no answer at all.

So: one SQLite file with one table, holding one row per state change.
Not one row per poll. At a 30 second interval that would be 2,880 rows
a day to say "still fine"; a change is written only when the state
actually changes, which on a healthy month is a handful of rows.

**This needs a volume.** Railway's filesystem is wiped on every deploy,
so without one mounted at ``STATUS_DATA_DIR`` the history restarts each
time the service is redeployed. That is not fatal -- the panel falls
back to "not enough data yet" -- but it makes the figure meaningless,
which is why ``storage_is_persistent()`` exists and the panel says so.

Uptime is computed from the spans between changes, so a gap in the
record (the service itself was down) is visible rather than silently
counted as "up". A watcher that reports 100 % because it was asleep is
worse than one that admits it does not know.
"""

from __future__ import annotations

import os
import sqlite3
import time

# Where the file lives. A volume mounted here survives deploys; without
# one this is a directory inside the container and the record is lost
# on every redeploy.
DATA_DIR = (os.getenv("STATUS_DATA_DIR") or "/data").strip() or "/data"
DB_PATH = os.path.join(DATA_DIR, "status_history.db")

# How far back the panel looks.
WINDOW_DAYS = int(os.getenv("STATUS_HISTORY_DAYS") or 7)

# Rows older than this are dropped. Well beyond the display window, so
# the window can be widened later without having thrown the data away.
KEEP_DAYS = int(os.getenv("STATUS_HISTORY_KEEP_DAYS") or 90)

# How often a latency sample is kept. Every poll would be 2,880 rows a
# day to draw a chart with 24 bars in it; every 5 minutes is 288, and
# the bars are hourly averages anyway.
SAMPLE_EVERY = int(os.getenv("STATUS_SAMPLE_SECONDS") or 300)


def _connect() -> sqlite3.Connection | None:
    """
    Open the database, creating the directory if need be.

    Returns None when that is impossible. Every caller treats that as
    "no history available" rather than raising: the watcher must keep
    watching even if it cannot write anything down.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        connection = sqlite3.connect(DB_PATH, timeout=5)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS state_changes (
                at REAL PRIMARY KEY,
                state TEXT NOT NULL
            )
            """
        )
        # Latency samples, for the response-time graph. One row per
        # poll would be 2,880 a day; one per SAMPLE_EVERY keeps a week
        # in a few hundred rows, which is plenty for a 24-bar chart.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                at REAL PRIMARY KEY,
                latency_ms REAL,
                reachable INTEGER NOT NULL,
                errors INTEGER DEFAULT 0
            )
            """
        )
        connection.commit()
        return connection
    except Exception as err:  # noqa: BLE001
        print(f"[status] history unavailable ({err}) — running without it.")
        return None


def storage_is_persistent() -> bool:
    """
    Is the history on something that survives a deploy?

    Compared against the parent directory rather than "/": a mount shows
    up as a different device from the directory it is mounted inside.
    Comparing with the root filesystem gets this wrong in a container
    where / is itself an overlay.
    """
    try:
        if not os.path.isdir(DATA_DIR):
            return False
        parent = os.path.dirname(DATA_DIR.rstrip("/")) or "/"
        return os.stat(DATA_DIR).st_dev != os.stat(parent).st_dev
    except Exception:  # noqa: BLE001
        return False


def record(state: str, when: float | None = None) -> None:
    """
    Note that the state changed. Called only on an actual change.

    Writing every poll would be 2,880 rows a day to record that nothing
    happened.
    """
    connection = _connect()
    if connection is None:
        return
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO state_changes (at, state) VALUES (?, ?)",
                (float(when or time.time()), state),
            )
            connection.execute(
                "DELETE FROM state_changes WHERE at < ?",
                (time.time() - KEEP_DAYS * 86400,),
            )
    except Exception as err:  # noqa: BLE001
        print(f"[status] could not write history: {err}")
    finally:
        connection.close()


def _rows(since: float) -> list[tuple[float, str]]:
    connection = _connect()
    if connection is None:
        return []
    try:
        # One row before the window too, so the state at the start of
        # the window is known. Without it a service that has been up for
        # a month looks like it has no data.
        cursor = connection.execute(
            "SELECT at, state FROM state_changes WHERE at < ? "
            "ORDER BY at DESC LIMIT 1",
            (since,),
        )
        before = cursor.fetchall()
        cursor = connection.execute(
            "SELECT at, state FROM state_changes WHERE at >= ? ORDER BY at",
            (since,),
        )
        return list(reversed(before)) + list(cursor.fetchall())
    except Exception as err:  # noqa: BLE001
        print(f"[status] could not read history: {err}")
        return []
    finally:
        connection.close()


def summary(now: float | None = None) -> dict:
    """
    Uptime over the window, and when the last outage was.

    Returns ``{"known": False}`` when there is not enough to say
    anything. The panel then omits the line rather than printing a
    percentage derived from twenty minutes of data.

    "Up" counts online *and* starting: a bot that is booting is not
    broken, and counting a deploy as downtime would make every update
    look like an incident.
    """
    now = now or time.time()
    window_start = now - WINDOW_DAYS * 86400
    rows = _rows(window_start)

    if not rows:
        return {"known": False, "reason": "noch keine Aufzeichnung"}

    # Clip the first span to the start of the window.
    spans: list[tuple[float, float, str]] = []
    for index, (at, state) in enumerate(rows):
        start = max(at, window_start)
        end = rows[index + 1][0] if index + 1 < len(rows) else now
        if end > start:
            spans.append((start, end, state))

    if not spans:
        return {"known": False, "reason": "noch keine Aufzeichnung"}

    measured = sum(end - start for start, end, _ in spans)

    # Less than an hour of record is not a percentage worth printing.
    if measured < 3600:
        return {"known": False, "reason": "noch zu wenig Daten"}

    up = sum(
        end - start
        for start, end, state in spans
        if state in ("online", "starting")
    )

    outages = [(start, end) for start, end, state in spans if state == "down"]
    last_outage = outages[-1] if outages else None

    return {
        "known": True,
        "percent": round(up / measured * 100, 2) if measured else 0.0,
        "days": WINDOW_DAYS,
        "measured_seconds": measured,
        "outage_count": len(outages),
        "outage_seconds": sum(end - start for start, end in outages),
        "last_outage_end": last_outage[1] if last_outage else None,
        "last_outage_seconds": (
            last_outage[1] - last_outage[0] if last_outage else 0
        ),
        # True when the record covers the whole window. When it does
        # not, the figure is still useful but should not be presented
        # as "over 7 days".
        "complete": measured >= WINDOW_DAYS * 86400 * 0.95,
    }


# ══════════════════════════════════════════════════════════════════════
#  Latency samples
# ══════════════════════════════════════════════════════════════════════


def sample(latency_ms: float | None, reachable: bool, errors: int = 0,
           when: float | None = None) -> None:
    """
    Keep one measurement, for the graphs.

    Called on every poll but only writes every SAMPLE_EVERY seconds --
    the caller does not have to track that itself, because getting it
    wrong in one place would quietly fill the database.
    """
    now = float(when or time.time())
    connection = _connect()
    if connection is None:
        return
    try:
        cursor = connection.execute("SELECT MAX(at) FROM samples")
        row = cursor.fetchone()
        if row and row[0] and now - row[0] < SAMPLE_EVERY:
            return

        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO samples (at, latency_ms, reachable, errors) "
                "VALUES (?, ?, ?, ?)",
                (now, latency_ms, 1 if reachable else 0, int(errors)),
            )
            connection.execute(
                "DELETE FROM samples WHERE at < ?",
                (now - KEEP_DAYS * 86400,),
            )
    except Exception as err:  # noqa: BLE001
        print(f"[status] could not write sample: {err}")
    finally:
        connection.close()


def buckets(hours: int = 24, count: int = 24, now: float | None = None) -> list[dict]:
    """
    The samples grouped into `count` equal slots over `hours`.

    Each slot reports the average latency and whether anything was
    unreachable in it. Slots with no samples are marked so -- the chart
    draws a gap rather than pretending the line continued, which is the
    difference between "nothing was wrong" and "we were not watching".
    """
    now = now or time.time()
    span = hours * 3600
    start = now - span
    width = span / count

    connection = _connect()
    if connection is None:
        return []
    try:
        rows = connection.execute(
            "SELECT at, latency_ms, reachable, errors FROM samples "
            "WHERE at >= ? ORDER BY at",
            (start,),
        ).fetchall()
    except Exception as err:  # noqa: BLE001
        print(f"[status] could not read samples: {err}")
        return []
    finally:
        connection.close()

    slots: list[dict] = [
        {
            "start": start + index * width,
            "end": start + (index + 1) * width,
            "latencies": [],
            "unreachable": 0,
            "errors": 0,
            "samples": 0,
        }
        for index in range(count)
    ]

    for at, latency, reachable, errors in rows:
        index = int((at - start) / width)
        if not 0 <= index < count:
            continue
        slot = slots[index]
        slot["samples"] += 1
        slot["errors"] += int(errors or 0)
        if reachable:
            if latency is not None:
                slot["latencies"].append(latency)
        else:
            slot["unreachable"] += 1

    for slot in slots:
        latencies = slot.pop("latencies")
        slot["latency"] = sum(latencies) / len(latencies) if latencies else None
        slot["known"] = slot["samples"] > 0
        slot["bad"] = slot["unreachable"] > 0

    return slots


def error_summary(hours: int = 24, now: float | None = None) -> dict:
    """
    How many command errors happened over the window.

    The stored value is the main bot's **running total since it
    started**, not a per-poll count -- so summing the column gives a
    meaningless number that grows with however many samples were taken.
    (First version did exactly that and reported 132 errors for a
    window that contained about a dozen.)

    What is wanted is the difference between the first and last reading.
    A restart resets the counter to zero, so a drop means "the bot
    restarted", not "minus fifty errors": those steps are summed
    segment by segment and the restart is reported separately, since a
    restart is itself worth knowing about.
    """
    now = now or time.time()
    connection = _connect()
    if connection is None:
        return {"known": False}
    try:
        rows = connection.execute(
            "SELECT errors FROM samples WHERE at >= ? ORDER BY at",
            (now - hours * 3600,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return {"known": False}
    finally:
        connection.close()

    values = [int(r[0] or 0) for r in rows]
    if len(values) < 2:
        return {"known": False}

    total = 0
    restarts = 0
    for previous, current in zip(values, values[1:]):
        if current >= previous:
            total += current - previous
        else:
            # Counter went backwards: the bot restarted. Everything
            # counted since that restart is the new value itself.
            restarts += 1
            total += current

    return {
        "known": True,
        "samples": len(values),
        "total": total,
        "restarts": restarts,
        "hours": hours,
    }
