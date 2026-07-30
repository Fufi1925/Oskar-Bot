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
