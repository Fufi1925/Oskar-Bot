"""Unit tests for the partial-update helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.patch_utils import changed_fields, merge_partial, model_updates  # noqa: E402


def test_unsent_fields_keep_their_stored_value():
    """The bug this module exists for: B must not reset A."""
    current = {"a": True, "b": False, "c": "keep"}
    assert merge_partial(current, {"b": True}) == {
        "a": True,
        "b": True,
        "c": "keep",
    }


def test_explicit_false_is_written():
    """False is a value, not "missing" — turning something off must work."""
    assert merge_partial({"a": True}, {"a": False})["a"] is False


def test_none_counts_as_not_sent():
    assert merge_partial({"a": True}, {"a": None})["a"] is True


def test_unknown_keys_are_dropped():
    out = merge_partial({"a": 1}, {"a": 2, "evil": "x"})
    assert out == {"a": 2}


def test_meta_keys_are_dropped():
    out = merge_partial({"a": 1}, {"a": 2, "actor": "123", "guild_id": 5})
    assert out == {"a": 2}


def test_allowed_overrides_the_key_set():
    out = merge_partial({"a": 1}, {"b": 2}, allowed={"a", "b"})
    assert out == {"a": 1, "b": 2}


def test_coercion_applies():
    out = merge_partial({"n": 0}, {"n": "42"}, coerce={"n": int})
    assert out["n"] == 42


def test_bad_coercion_keeps_the_old_value():
    out = merge_partial({"n": 7}, {"n": "abc"}, coerce={"n": int})
    assert out["n"] == 7


def test_empty_body_changes_nothing():
    current = {"a": True, "b": 2}
    assert merge_partial(current, {}) == current
    assert merge_partial(current, None) == current


def test_changed_fields_reports_only_differences():
    assert changed_fields({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"b": 3}


def test_model_updates_ignores_unset_optionals():
    from pydantic import BaseModel

    class Update(BaseModel):
        a: bool | None = None
        b: int | None = None

    assert model_updates(Update(b=5)) == {"b": 5}


def test_model_updates_accepts_plain_dict():
    assert model_updates({"a": 1, "b": None}) == {"a": 1}


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failures")
    sys.exit(1 if failures else 0)
