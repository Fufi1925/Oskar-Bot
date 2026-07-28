#!/usr/bin/env python3
"""
The >help menu.

Reported from production: >help printed a loading card, then deleted it
five seconds later and nothing else appeared.

    HTTPException: 400 Bad Request (error code: 50035)
    In components.0.components.6.components.0.options.13.emoji.name:
    Invalid emoji

Option 13 was the "Anonymer Chat" category, whose emoji was written as
"\U0001f3ad " -- with a trailing space. Discord validates that field
strictly and refuses the whole payload, so *every* category became
unreachable because of one stray character. The loading message was not
being deleted on purpose; it is always removed, and the menu that should
have replaced it never arrived.

Two fixes are covered here: the space is gone, and safe_emoji() drops an
unusable icon instead of letting it take the menu down.

Run:  python3 tests/test_help_menu.py
"""

import os
import re
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

warnings.filterwarnings("ignore")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def test_safe_emoji():
    print("\nsafe_emoji")

    from utils.help import safe_emoji

    check("a plain unicode emoji is kept", safe_emoji("\U0001f3ad") == "\U0001f3ad")
    check("a custom emoji is kept",
          safe_emoji("<:ztick:1448951767990796298>")
          == "<:ztick:1448951767990796298>")
    check("an animated one is kept",
          safe_emoji("<a:wave:1448951767990796298>")
          == "<a:wave:1448951767990796298>")

    # The reported bug.
    check("a trailing space is stripped, not passed on",
          safe_emoji("\U0001f3ad ") == "\U0001f3ad",
          repr(safe_emoji("\U0001f3ad ")))
    check("a leading space too", safe_emoji(" \U0001f3ad") == "\U0001f3ad")

    check("an empty string becomes nothing", safe_emoji("") is None)
    check("whitespace becomes nothing", safe_emoji("   ") is None)
    check("None stays None", safe_emoji(None) is None)

    # A half-written custom emoji must be dropped, not sent.
    for broken in ("<:name:>", "<:name>", ":name:", "<::123>",
                   "<:name:abc>", "not an emoji at all"):
        check(f"{broken!r} is dropped", safe_emoji(broken) is None,
              repr(safe_emoji(broken)))

    # A real Emoji object is not a string and must pass through.
    marker = object()
    check("a non-string emoji object is left alone",
          safe_emoji(marker) is marker)


def test_no_padded_emojis():
    """
    No help_custom emoji may carry stray whitespace.

    Asserted across every cog: one bad entry is enough to break the
    entire menu, and it is invisible until somebody runs >help.
    """
    print("\nNo padded emojis anywhere")

    bad = []
    for folder in ("cogs/universitybot", "cogs/commands", "cogs/events"):
        path = os.path.join(HERE, "..", folder)
        if not os.path.isdir(path):
            continue
        for name in sorted(os.listdir(path)):
            if not name.endswith(".py"):
                continue
            src = open(os.path.join(path, name)).read()
            if "help_custom" not in src:
                continue
            for match in re.finditer(r'emoji\s*=\s*(["\'])(.*?)\1', src):
                value = match.group(2)
                if value != value.strip():
                    bad.append(f"{folder}/{name}: {value!r}")

    check("every help emoji is free of stray whitespace", not bad, str(bad))


def test_every_help_emoji_is_valid():
    """Each declared emoji has to survive safe_emoji unchanged."""
    print("\nEvery category icon is usable")

    from utils.help import safe_emoji
    import utils.emoji as emoji_module

    dropped = []
    checked = 0
    folder = os.path.join(HERE, "..", "cogs", "universitybot")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(folder, name)).read()
        if "help_custom" not in src:
            continue

        match = re.search(r"emoji\s*=\s*([A-Z_][A-Z0-9_]*)", src)
        if match:
            value = getattr(emoji_module, match.group(1), None)
            if value is None:
                dropped.append(f"{name}: {match.group(1)} does not exist")
                continue
        else:
            match = re.search(r'emoji\s*=\s*(["\'])(.*?)\1', src)
            if not match:
                continue
            value = match.group(2)

        checked += 1
        if safe_emoji(value) is None:
            dropped.append(f"{name}: {value!r}")

    check("at least the known categories were inspected", checked > 20,
          str(checked))
    check("none of them would be dropped by Discord", not dropped, str(dropped))


def test_menu_survives_one_bad_icon():
    """
    A single unusable icon must cost one icon, not the whole menu.

    Before this, option 13 alone made every category unreachable.
    """
    print("\nOne bad icon does not break the menu")

    import discord
    from utils.help import safe_emoji

    categories = [
        ("Home", "\U0001f3e0"),
        ("Security", "<:zSafe:1448951403434479626>"),
        ("Anonymer Chat", "\U0001f3ad "),      # the broken one
        ("Counting", "<:zcounting:1448949348103749713>"),
    ]

    options = []
    for label, raw in categories:
        options.append(discord.SelectOption(
            label=label, emoji=safe_emoji(raw), description=""
        ))

    check("every category still has an option", len(options) == 4,
          str(len(options)))

    payloads = [option.to_dict() for option in options]
    check("nothing raises while building the payload", len(payloads) == 4)

    anon = payloads[2]
    name = (anon.get("emoji") or {}).get("name")
    check("the offending icon is now valid",
          name == "\U0001f3ad", repr(name))
    check("and carries no trailing space",
          name is None or name == name.strip(), repr(name))

    # Discord rejects a select with more than 25 options; the menu has
    # about 30 categories, so this is not hypothetical.
    check("a select still has to stay within 25 options",
          len(options) <= 25)


def run():
    test_safe_emoji()
    test_no_padded_emojis()
    test_every_help_emoji_is_valid()
    test_menu_survives_one_bad_icon()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
