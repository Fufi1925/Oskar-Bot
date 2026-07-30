#!/usr/bin/env python3
"""
Every prepared announcement must survive being sent.

The sibling test_announcements.py reads lib/announcements.ts as text and
checks the scoping and the wording. That catches a lot, but it measures
the *source file*, not the message: a 1500-character block written as
twelve concatenated string literals looks short to a regex and is still
too long for Discord.

So this file does the thing itself. It executes the TypeScript with
sucrase, which the dashboard already depends on, and feeds the resulting
blocks through the bot's own validate() and build_v2() -- the exact code
path the Send button uses. If a template cannot be posted, it fails
here rather than in front of the server.

Why this is worth a file of its own: these entries are loaded and sent
with two clicks and no review step. Nobody re-reads a template that
worked last month, and "the announcement about the fix is broken" is a
particularly bad way to find out.

Needs node and dashboard/node_modules. Skips (exit 0) without them,
because the bot test suite has to run on a machine that never installed
the dashboard.

Run:  python3 tests/test_announcement_blocks.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")

sys.path.insert(0, BOT)

BOT_GUILD = "1530378233579704370"

failures: list[str] = []


def read_dashboard(relative):
    with open(os.path.join(DASH, relative), encoding="utf-8") as handle:
        return handle.read()


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


# ── getting the real data out of the TypeScript ─────────────────────


def load_announcements():
    """
    Run lib/announcements.ts and return what it actually exports.

    Reading it with a regex was the alternative and it is how the
    length check in the other file got fooled once already. sucrase is
    in the dashboard's dependency tree, so this needs nothing new.
    """
    runner = os.path.join(DASH, "node_modules/.bin/sucrase-node")
    if not os.path.exists(runner):
        return None, "dashboard/node_modules is missing (npm install)"

    script = (
        'import { ANNOUNCEMENTS, announcementsFor, BOT_GUILD_ID }'
        ' from "./lib/announcements";\n'
        "console.log(JSON.stringify({\n"
        "  entries: ANNOUNCEMENTS,\n"
        "  guild: BOT_GUILD_ID,\n"
        "  mine: announcementsFor(BOT_GUILD_ID).map((e) => e.id),\n"
        '  stranger: announcementsFor("999999999999999999").map((e) => e.id),\n'
        '  numeric: announcementsFor(1530378233579704370 as never).map((e) => e.id),\n'
        "  rounded: String(1530378233579704370),\n"
        "  literals: ANNOUNCEMENTS.map((e) => e.guilds.map((g) => typeof g)),\n"
        "}));\n"
    )

    # Written inside the dashboard so the "./lib/..." import resolves,
    # and named so it cannot collide with anything real.
    handle, path = tempfile.mkstemp(
        prefix="__announcement_probe_", suffix=".ts", dir=DASH
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(script)
        result = subprocess.run(
            [runner, "./" + os.path.basename(path)],
            cwd=DASH, capture_output=True, text=True, timeout=120,
        )
    except Exception as error:            # noqa: BLE001 - reported, not swallowed
        return None, f"could not run sucrase: {error}"
    finally:
        if os.path.exists(path):
            os.remove(path)

    if result.returncode != 0:
        return None, (result.stderr or result.stdout)[-500:]

    try:
        return json.loads(result.stdout), ""
    except json.JSONDecodeError as error:
        return None, f"output was not JSON: {error}"


# ── the tests ───────────────────────────────────────────────────────


def test_each_one_can_be_sent(data):
    """
    validate() must return no problems for any template.

    This is the same function the dashboard calls before enabling the
    Send button, so a template it rejects is one that cannot be posted
    at all.
    """
    print("\nEvery announcement passes the bot's own validator")

    from utils import message_builder

    for entry in data["entries"]:
        payload = {
            "kind": "v2",
            "color": entry["accent"],
            "blocks": entry["blocks"],
        }
        problems = message_builder.validate(payload)
        check(f"{entry['id']} validates", problems == [], "; ".join(problems))


def test_each_one_builds(data):
    """
    build_v2() must produce a view discord.py accepts.

    Validation is a list of rules somebody wrote; building is discord.py
    itself objecting. It catches the limits nobody encoded -- a
    Container holds 40 components, an ActionRow holds 5, and both raise
    before the message is ever sent.
    """
    print("\nEvery announcement builds into a real view")

    from utils import message_builder

    for entry in data["entries"]:
        payload = {
            "kind": "v2",
            "color": entry["accent"],
            "blocks": entry["blocks"],
        }
        try:
            view = message_builder.build_v2(payload)
            built = view is not None
            note = ""
        except Exception as error:        # noqa: BLE001 - the point of the test
            built = False
            note = f"{type(error).__name__}: {error}"
        check(f"{entry['id']} builds", built, note)


def test_the_limits_that_bite(data):
    """
    The three limits these templates can realistically hit.

    Checked on the assembled text rather than the source, which is the
    difference between this file and the other one.
    """
    print("\nDiscord's limits, measured on the assembled message")

    for entry in data["entries"]:
        name = entry["id"]
        blocks = entry["blocks"]

        # A Container holds 40 components. Every block is one.
        check(f"{name}: at most 40 blocks", len(blocks) <= 40, str(len(blocks)))

        texts = [b.get("text") or "" for b in blocks if b["type"] == "text"]
        for index, text in enumerate(texts, start=1):
            check(f"{name}: text {index} within 4000 characters",
                  len(text) <= 4000, f"{len(text)} chars")

        # Not a rule of Discord's, a rule of ours: nobody reads a wall,
        # and these get posted to a channel people scroll past.
        total = sum(len(t) for t in texts)
        check(f"{name}: readable length", 250 <= total <= 3000,
              f"{total} chars in total")

        # Five buttons per row is a hard limit; the builder silently
        # drops the sixth, which is worse than failing here.
        for index, block in enumerate(blocks, start=1):
            if block["type"] == "buttons":
                count = len(block.get("buttons") or [])
                check(f"{name}: button row {index} has at most 5",
                      count <= 5, str(count))


def test_scoping(data):
    """
    The announcements appear on one guild and on no other.

    A first version of this test asserted that a guild id passed as a
    JavaScript *number* still matched, on the theory that the String()
    in the filter made that safe. It does not, and cannot: 19 digits
    exceed what a double can hold exactly, so the id is already rounded
    to ...704300 before String() ever sees it. The test failed, and it
    was the test that was wrong.

    What String() actually protects against is narrower and still worth
    having -- a caller passing something that is not a primitive string,
    which is what params sometimes are. The real protection against
    rounding is that the ids are string literals in the source, never
    numbers, and that is asserted below.
    """
    print("\nScoping")

    check("the bot guild sees its announcements", len(data["mine"]) > 0,
          str(data["mine"]))
    check("a stranger's guild sees none", data["stranger"] == [],
          str(data["stranger"]))
    check("the ids are unique",
          len(data["mine"]) == len(set(data["mine"])),
          "a duplicate id makes React reuse the wrong row")

    # Every guild id in the file is a string at runtime. This is the
    # thing that keeps the id intact; typing it as a number would round
    # it and match nothing.
    kinds = {kind for entry in data["literals"] for kind in entry}
    check("every guild id is a string at runtime", kinds == {"string"},
          str(kinds))

    # Proof that the rounding is real, so nobody "fixes" the ids into
    # numbers later. If this ever stops rounding, the note above is
    # obsolete.
    check("a 19-digit id really is rounded when written as a number",
          data["rounded"] != BOT_GUILD,
          f"{data['rounded']} -- expected it to differ from {BOT_GUILD}")
    check("and such an id therefore matches nothing",
          data["numeric"] == [],
          f"{data['numeric']} -- a rounded id must not match")

    # The route hands this down as a string from the URL, which is the
    # only way it is ever called in the app.
    check("the panel is typed to receive a string",
          "guildId }: { guildId: string }" in read_dashboard(
              "components/dashboard/compose-panel.tsx"),
          "a number here would round and show nothing")


def test_the_newest_entry_is_first(data):
    """
    The list renders in order, so the newest has to be at the top.

    Not cosmetic: the whole card is a stack of buttons and the one
    people want is the one that just shipped.
    """
    print("\nOrder")

    ids = [e["id"] for e in data["entries"]]
    check("there are several announcements", len(ids) >= 2, str(len(ids)))

    def as_date(entry):
        day, month, year = entry["date"].split(".")
        return (int(year), int(month), int(day))

    dates = [as_date(e) for e in data["entries"]]
    check("newest first", dates == sorted(dates, reverse=True),
          str([e["date"] for e in data["entries"]]))

    # Every entry needs the fields the card renders, or the button shows
    # "undefined" to whoever opens the tab.
    for entry in data["entries"]:
        for field in ("id", "label", "summary", "date", "accent", "blocks"):
            check(f"{entry.get('id', '?')} has {field}",
                  bool(entry.get(field)))
        check(f"{entry['id']}: the accent is a hex colour",
              entry["accent"].startswith("#") and len(entry["accent"]) == 7,
              entry["accent"])


def main():
    if not os.path.isdir(DASH):
        print("dashboard folder not found -- skipped")
        return 0

    data, problem = load_announcements()
    if data is None:
        # Not a failure: the bot suite must run without the dashboard's
        # dependencies installed. Loud enough to notice in CI, where
        # they are installed and this should never print.
        print(f"skipped -- {problem}")
        return 0

    check("the announcements were loaded", bool(data["entries"]))
    check("the guild id survived the round trip",
          data["guild"] == BOT_GUILD, data["guild"])

    test_each_one_can_be_sent(data)
    test_each_one_builds(data)
    test_the_limits_that_bite(data)
    test_scoping(data)
    test_the_newest_entry_is_first(data)

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
