#!/usr/bin/env python3
"""
Guard the emoji table in utils/emoji.py.

Three real bugs lived here at once and all of them showed up in Discord as
raw text like "<:error:1397218903389044776>" in the middle of a sentence:

  1. `ERROR`, `PARTNER_BADGE`, `BUG_HUNTER_LVL2` and `HYPESQUAD_EVENTS`
     pointed at emojis that no longer exist. EmojiSync tried to re-upload
     them every single boot, failed to download the source, and gave up —
     four failures on every restart, forever.
  2. `king` is animated on Discord but was written as `<:king:...>`.
     A wrong "a" prefix makes Discord render the tag as plain text.
  3. EmojiSync itself preserved the template's own prefix when rewriting an
     ID, so bug 2 could never heal on its own.

These checks are offline: they read the file and compare it against a
snapshot of what the application really hosts. No token, no network.

    python3 tests/test_emoji_refs.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

EMOJI_PY = os.path.join(BOT, "utils", "emoji.py")
SNAPSHOT = os.path.join(HERE, "data", "app_emojis.json")

TAG = re.compile(r"<(a?):(\w+):(\d+)>")

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    source = open(EMOJI_PY, encoding="utf-8").read()
    # Drop comment lines so the explanations above a constant can never be
    # mistaken for a real emoji reference.
    body = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    refs = TAG.findall(body)

    print("emoji.py references")
    check("file contains emoji tags", len(refs) > 100, f"only {len(refs)}")

    hosted = {e["name"]: e for e in json.load(open(SNAPSHOT, encoding="utf-8"))}

    # 1. Every referenced emoji must actually be hosted by the application.
    unknown = sorted({n for _, n, _ in refs if n not in hosted})
    check("every emoji is hosted by the application", not unknown, f"missing: {unknown}")

    # 2. Every ID must match the hosted one, or the tag renders as text.
    wrong_id = sorted(
        {(n, i, hosted[n]["id"]) for _, n, i in refs if n in hosted and hosted[n]["id"] != i}
    )
    check("every emoji ID matches the hosted ID", not wrong_id, f"stale: {wrong_id}")

    # 3. The "a" prefix must match. This is the bug that hit `king`.
    wrong_anim = sorted(
        {
            (n, f"<{a}:{n}:{i}>")
            for a, n, i in refs
            if n in hosted and (a == "a") != bool(hosted[n]["animated"])
        }
    )
    check("animated prefix matches Discord", not wrong_anim, f"wrong: {wrong_anim}")

    # 4. The constants that were dead must resolve to a real hosted emoji.
    from utils import emoji as emoji_mod

    for const in ("ERROR", "PARTNER_BADGE", "BUG_HUNTER_LVL2", "HYPESQUAD_EVENTS", "KING"):
        value = getattr(emoji_mod, const, "")
        m = TAG.fullmatch(value.strip())
        ok = bool(m) and m.group(2) in hosted and hosted[m.group(2)]["id"] == m.group(3)
        check(f"{const} resolves to a live emoji", ok, f"got {value!r}")

    print("\nsync_emojis rewrites the animated prefix")
    sync = open(os.path.join(BOT, "utils", "sync_emojis.py"), encoding="utf-8").read()
    sync_body = "\n".join(l for l in sync.splitlines() if not l.lstrip().startswith("#"))
    # The rewritten tag must be built from Discord's answer, never from the
    # prefix we happened to read out of the template.
    check(
        "ID rewrite derives the prefix from the API",
        'new_prefix = "a" if existing.get("animated")' in sync_body,
        "prefix still copied from the template",
    )
    check(
        "upload rewrite derives the prefix from the API",
        'up_prefix = "a" if new_emoji.get("animated")' in sync_body,
        "prefix still copied from the template",
    )
    check(
        "download tries more than one extension",
        'order = ["gif", "png", "webp"] if animated else ["png", "webp", "gif"]' in sync_body,
        "single-extension download is back",
    )

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("All emoji reference checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
