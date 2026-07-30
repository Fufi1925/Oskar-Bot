#!/usr/bin/env python3
"""
Prepared announcements in the compose tab.

These are changelog posts for the bot's own community server, offered
as one-click templates. The point of this test is the scoping: they
must appear on that one guild and nowhere else. A stranger's server has
no use for "the bot got a database" and should not have to scroll past
it -- and worse, an announcement about our roadmap showing up in someone
else's dashboard would be a small leak of things that are not theirs.

Verified in a real browser while building it: on guild
1530378233579704370 the card and the button render and a click fills
the editor; on another guild id neither exists in the DOM at all.
This file guards the parts that can be checked without a browser.

Run:  python3 tests/test_announcements.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

BOT_GUILD = "1530378233579704370"

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path):
    with open(os.path.join(DASH, path), encoding="utf-8") as handle:
        return handle.read()


def test_the_file():
    print("\nThe announcements file")

    path = os.path.join(DASH, "lib/announcements.ts")
    check("lib/announcements.ts exists", os.path.exists(path))
    if not os.path.exists(path):
        return
    src = read("lib/announcements.ts")

    check("the bot guild is the one that was asked for",
          f'BOT_GUILD_ID = "{BOT_GUILD}"' in src,
          "a wrong id here means the announcement lands nowhere, or worse, "
          "somewhere else")

    # The id is 19 digits. Written as a number it would be rounded by
    # JavaScript and match nothing.
    check("the guild id is a string, not a number",
          f'"{BOT_GUILD}"' in src and f"= {BOT_GUILD}" not in src,
          "a 19-digit number loses its last digits in JS")

    check("there is a filter function", "export function announcementsFor" in src)
    check("it filters by guild",
          "entry.guilds.includes(String(guildId))" in src,
          "without the String() a number id would never match")

    check("at least one announcement exists",
          "ANNOUNCEMENTS: Announcement[] = [" in src and '"id":' not in src.split("ANNOUNCEMENTS")[0])

    # Every entry has to be scoped. An entry with an empty guilds list
    # would render for nobody; one without the field would crash.
    entries = re.findall(r"guilds:\s*\[([^\]]*)\]", src)
    check("every entry names its guilds", entries, str(entries))
    for value in entries:
        check(f"the guild list {value.strip()[:40]} is not empty",
              value.strip() != "")


def test_the_content():
    print("\nWhat it says")

    src = read("lib/announcements.ts")

    # The thing the announcement is about.
    check("it mentions the database change",
          "Datenbank" in src)
    check("it says settings now survive",
          "erhalten" in src or "überstehen" in src or "übersteht" in src)
    check("it names how many modules were checked",
          "30 Module" in src,
          "a number people can check beats a vague claim")

    # The other things shipped alongside.
    for topic in ("YouTube", "Handy", "Tabs"):
        check(f"it mentions {topic}", topic in src)

    # Length: medium was asked for, not a one-liner and not a wall.
    #
    # Measured per announcement, not across the file. Two earlier
    # mistakes here, both worth keeping in mind:
    #
    #   * a per-literal pattern stopped at the first "+" join and
    #     reported 201 characters for something near 1500;
    #   * summing every block in the file worked while there was one
    #     announcement and then measured nothing but the file size --
    #     it failed at five entries without any single one being long.
    entries = re.split(r"\n  \{\n    id: ", src)[1:]
    check("the announcements were found", len(entries) >= 1, str(len(entries)))

    for entry in entries:
        name = entry.split('"')[1] if '"' in entry else "?"
        blocks = re.findall(r"text:\s*(.*?),\n      \},", entry, re.S)
        joined = " ".join(blocks)
        check(f"{name}: the text was found", len(blocks) >= 3,
              f"{len(blocks)} blocks")
        check(f"{name}: not a one-liner", len(joined) > 300,
              f"{len(joined)} chars")
        check(f"{name}: not a wall of text", len(joined) < 4000,
              f"{len(joined)} chars")

    # Discord markdown that the message relies on.
    check("it uses headings", "# " in src)
    check("it uses a quote line", "> " in src)
    check("it uses small text for the footer", "-# " in src)


def test_the_panel_is_scoped():
    print("\nThe compose panel")

    src = read("components/dashboard/compose-panel.tsx")

    check("it imports the filter",
          "announcementsFor" in src and "@/lib/announcements" in src)
    check("it filters by the guild it was given",
          "announcementsFor(guildId)" in src,
          "anything else would show the same list everywhere")

    # The card must not render when the list is empty, or every other
    # server sees an empty box.
    check("the card is hidden when there is nothing to show",
          "announcements.length > 0 &&" in src)

    check("loading a template switches to the right editor",
          'setKind("v2")' in src,
          "the blocks are Components V2; loading them into the text "
          "editor would show nothing")
    check("loading also sets the accent colour",
          "setAccent(entry.accent)" in src)
    check("and gives each block a fresh id",
          "id: nextId++" in src,
          "reusing ids makes React mix up the rows when reordering")

    # Nothing is sent automatically -- it fills the editor and stops.
    load = src.split("const loadAnnouncement")[1].split("};")[0]
    check("loading does not send anything by itself",
          "api.send" not in load and "sendComposed" not in load,
          "a template that posts on click is a mistake waiting to happen")


def test_preview_renders_headings():
    """
    The preview has to show what Discord will show.

    It knew bold, italic, code and quotes but not headings, so "# Titel"
    appeared as a literal hash while Discord renders a heading. Found by
    looking at the rendered preview of this very announcement.
    """
    print("\nPreview")

    src = read("components/dashboard/compose-panel.tsx")

    for pattern, label in (
        (r"\^# \(\.\*\)\$", "h1"),
        (r"\^## \(\.\*\)\$", "h2"),
        (r"\^### \(\.\*\)\$", "h3"),
        (r"\^-# \(\.\*\)\$", "small text"),
    ):
        check(f"the preview renders {label}",
              re.search(pattern.replace("\\^", r"\^").replace(" ", r"\s?"), src)
              or pattern.replace("\\", "") in src.replace("\\", ""),
              "the preview would show the raw marker instead")

    # Simpler and less brittle: the four replacements are present.
    for marker in ("^### ", "^## ", "^# ", "^-# "):
        check(f"a rule exists for {marker.strip()}",
              marker in src, "preview and Discord would disagree")


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_the_file()
    test_the_content()
    test_the_panel_is_scoped()
    test_preview_renders_headings()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
