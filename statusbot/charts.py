# ╔══════════════════════════════════════════════════════════════════╗
# ║   Drawing graphs in a Discord message                            ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Charts made of block characters.

Discord has no chart component, so the options are an image (a whole
rendering pipeline, plus a file upload on every refresh) or text. Text
wins here: it is instant, it costs nothing, it survives being quoted,
and it stays readable on a phone.

Two rules run through this file.

**A gap must look like a gap.** A slot with no samples is drawn as a
faint mark, never as zero and never skipped. "We were not watching" and
"nothing was wrong" are different statements, and a chart that renders
them identically is lying by omission -- which is exactly the failure
the whole status panel is built to avoid.

**The scale is shown.** A bar chart without a maximum tells you the
shape and nothing else. Every chart here prints its own range, so a tall
bar at 80 ms is not mistaken for a tall bar at 8 seconds.
"""

from __future__ import annotations

# Eight heights, so a column can show roughly an eighth of the scale.
# U+2581..U+2588, the standard block-element ramp.
BLOCKS = "▁▂▃▄▅▆▇█"

# A slot we have no data for. Deliberately not a space -- a space reads
# as "zero", and this means "unknown".
UNKNOWN = "·"

# A slot where the bot was unreachable.
#
# NOT a full block: on a latency chart a tall bar means "very slow", and
# drawing an outage the same way makes it look like the worst possible
# measurement rather than the absence of one. An outage has no response
# time at all. A cross reads as "nothing here" instead.
OUTAGE = "x"


def _height(value: float, top: float) -> str:
    """One column, scaled against the top of the chart."""
    if top <= 0:
        return BLOCKS[0]
    ratio = max(0.0, min(1.0, value / top))
    index = round(ratio * (len(BLOCKS) - 1))
    return BLOCKS[index]


def latency_chart(slots: list[dict]) -> tuple[str, str]:
    """
    Response time over the window, and a caption naming the scale.

    Returns ("", "") when there is nothing to draw at all, so the caller
    can leave the section out rather than print an empty frame.
    """
    known = [s for s in slots if s.get("known")]
    if not known:
        return "", ""

    measured = [s["latency"] for s in known if s.get("latency") is not None]
    if not measured:
        return "", ""

    # The top of the chart, rounded up to a number a human would pick.
    #
    # _round_up never returns less than 100, which is the floor this
    # needs: without it a healthy 20-40 ms range would be scaled to its
    # own maximum and fill the whole height, making a fast bot look
    # like a crisis. The floor lives in _round_up rather than here --
    # an earlier max(100.0, ...) at this line was dead code, since the
    # value could never be lower.
    peak = max(measured)
    top = _round_up(peak)

    columns = []
    for slot in slots:
        if not slot.get("known"):
            columns.append(UNKNOWN)
        elif slot.get("bad"):
            columns.append(OUTAGE)
        elif slot.get("latency") is None:
            columns.append(UNKNOWN)
        else:
            columns.append(_height(slot["latency"], top))

    average = sum(measured) / len(measured)
    caption = (
        f"0–{int(top)} ms · ø {int(average)} ms · "
        f"max {int(peak)} ms"
    )
    # Only explain the marks that actually appear, or the caption is
    # longer than the chart.
    legend = []
    if UNKNOWN in columns:
        legend.append(f"`{UNKNOWN}` keine Daten")
    if OUTAGE in columns:
        legend.append(f"`{OUTAGE}` nicht erreichbar")
    if legend:
        caption += " · " + " · ".join(legend)
    return "".join(columns), caption


def availability_chart(slots: list[dict]) -> tuple[str, str]:
    """
    Reachable or not, per slot. Green squares and red ones.

    Separate from the latency chart on purpose: an outage has no
    latency, so on that chart it is a full bar that could be misread as
    "very slow". Here it is unambiguous.
    """
    if not slots:
        return "", ""

    marks = []
    outages = 0
    unknown = 0
    for slot in slots:
        if not slot.get("known"):
            marks.append("⬛")
            unknown += 1
        elif slot.get("bad"):
            marks.append("🟥")
            outages += 1
        else:
            marks.append("🟩")

    parts = []
    if unknown == len(slots):
        # Nothing was measured at all. Saying "keine Störung" here would
        # be a claim about a window nobody watched -- the same mistake
        # as an uptime figure from an empty database.
        return "".join(marks), "keine Messwerte in diesem Zeitraum"
    if outages:
        parts.append(f"{outages}× Störung")
    else:
        parts.append("keine Störung")
    if unknown:
        # Named rather than hidden: these are the slots where the
        # watcher itself was not running.
        parts.append(f"{unknown}× keine Daten")

    return "".join(marks), " · ".join(parts)


def _round_up(value: float) -> float:
    """
    Round up to a number a human would pick for an axis.

    The smallest step is 100 on purpose: it is the chart's floor. A bot
    answering in 20-40 ms scaled to its own peak would draw full-height
    bars, which reads as a problem when it is the opposite.
    """
    for step in (100, 200, 250, 500, 1000, 2000, 5000, 10000):
        if value <= step:
            return float(step)
    return float(int(value / 10000 + 1) * 10000)


def sparkline(values: list[float | None]) -> str:
    """
    A small inline chart, for anything that is a plain list of numbers.

    None means no data and is drawn as such -- same rule as above.
    """
    present = [v for v in values if v is not None]
    if not present:
        return ""
    top = max(present) or 1.0
    return "".join(
        UNKNOWN if value is None else _height(value, top) for value in values
    )
