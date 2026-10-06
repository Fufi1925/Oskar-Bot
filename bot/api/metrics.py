"""JSON-safe Discord metrics, including the pre-heartbeat connection state."""
import math


def latency_milliseconds(seconds: float, precision: int | None = None) -> float | None:
    if not math.isfinite(seconds) or seconds < 0:
        return None
    milliseconds = seconds * 1000
    if not math.isfinite(milliseconds):
        return None
    return round(milliseconds, precision) if precision is not None else milliseconds
