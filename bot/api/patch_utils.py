# ╔══════════════════════════════════════════════════════════════════╗
# ║   Helpers for PATCH handlers                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Shared logic for partial updates.

A PATCH must only change the fields the client actually sent. Rebuilding a
record with ``data.get("key", DEFAULT)`` looks harmless but silently resets
every field that was left out: enable switch A, later toggle switch B, and A
is back to its default on the next page load.

That bug shipped once (guild extra-settings) and the shape of the code made
it easy to repeat, because each route re-implemented merging by hand. These
helpers make the correct behaviour the short path.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

# Keys that travel with a request for bookkeeping and are never settings.
META_KEYS = frozenset({"actor", "guild_id", "id"})


def merge_partial(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any] | None,
    *,
    allowed: Iterable[str] | None = None,
    coerce: Mapping[str, Callable[[Any], Any]] | None = None,
) -> dict[str, Any]:
    """
    Overlay ``incoming`` onto ``current`` — only for keys that were sent.

    Parameters
    ----------
    current:
        The values as stored right now. Supplies every key of the result,
        so unsent fields keep their stored value instead of a default.
    incoming:
        The request body. ``None`` values are treated as "not sent", which
        matches how the Pydantic models here mark optional fields.
    allowed:
        Whitelist of writable keys. Defaults to the keys of ``current``, so
        an unknown or injected field can never reach the database.
    coerce:
        Optional per-key conversion, e.g. ``{"enabled": bool}``.

    Returns
    -------
    A complete dict: every key of ``current``, updated where the request
    asked for it.
    """
    allowed_keys = set(allowed) if allowed is not None else set(current.keys())
    result = dict(current)

    for key, value in (incoming or {}).items():
        if key in META_KEYS or key not in allowed_keys or value is None:
            continue
        if coerce and key in coerce:
            try:
                value = coerce[key](value)
            except (TypeError, ValueError):
                continue
        result[key] = value

    return result


def changed_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    """Fields whose value actually differs — handy for audit log entries."""
    return {k: v for k, v in after.items() if before.get(k) != v}


def model_updates(model: Any) -> dict[str, Any]:
    """
    The fields a Pydantic model actually received.

    ``model.dict()`` also yields the ones left at ``None``, which would make
    a partial update look like "set everything to null". Pydantic v2 knows
    which fields were provided; ``exclude_unset`` uses exactly that.
    """
    if hasattr(model, "model_dump"):
        data = model.model_dump(exclude_unset=True)
    elif hasattr(model, "dict"):
        data = model.dict(exclude_unset=True)
    else:
        data = dict(model or {})
    return {k: v for k, v in data.items() if v is not None}
