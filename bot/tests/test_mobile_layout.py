#!/usr/bin/env python3
"""
The dashboard on a phone.

Four things were wrong, each confirmed in a real browser at 375px before
it was changed:

  * **No viewport meta tag.** `app/layout.tsx` exported metadata but no
    viewport, so Next emitted none, and a phone laid the page out at
    roughly 980px and zoomed out to fit. Everything was tiny and every
    tap landed beside its target. This is the one that made all the
    others hard to see.

  * **The save bar overlapped itself.** Text and buttons shared one row
    with `justify-between`; at 375px the text was squeezed to 7 pixels
    wide and its lines ran behind the buttons -- the screenshot read
    "noch VERWERFEN nicht".

  * **Three-column stat tiles overflowed.** 375px split three ways
    leaves 58px, and "1.204" in text-2xl does not fit. Measured
    `scrollWidth > clientWidth` on the real element.

  * **Padding written for a desktop.** p-6 on a card and px-8 on the
    header take 13-17% of a 375px screen for margin alone.

Checked here as source assertions, because the test run has no Node.
The measurements above came from Playwright while making the change;
what this file guards is that the fixes do not quietly get reverted.

Run:  python3 tests/test_mobile_layout.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

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


def strip_comments(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


# ══════════════════════════════════════════════════════════════════════
#  The viewport tag
# ══════════════════════════════════════════════════════════════════════


def test_viewport():
    print("\nViewport")

    src = read("app/layout.tsx")
    code = strip_comments(src)

    check("app/layout.tsx exports a viewport",
          "export const viewport" in code,
          "without it a phone renders at ~980px and zooms out")
    check("it is typed as Viewport", "Viewport" in code)
    check("width follows the device", 'width: "device-width"' in code)
    check("the initial scale is 1", "initialScale: 1" in code)

    # Capping zoom locks out anybody who needs bigger text. It is an
    # accessibility failure, not a layout choice.
    check("zoom is not capped",
          "maximumScale" not in code and "userScalable" not in code,
          "capping zoom locks out anybody who needs to enlarge text")


# ══════════════════════════════════════════════════════════════════════
#  The save bar
# ══════════════════════════════════════════════════════════════════════


def test_save_bar():
    print("\nSave bar")

    src = read("components/dashboard/save-bar.tsx")

    check("it stacks on a narrow screen",
          "flex flex-col sm:flex-row" in src,
          "one row at 375px squeezed the text to 7px behind the buttons")
    check("and goes back to one row from sm up",
          "sm:flex-row" in src and "sm:items-center" in src)
    check("the buttons fill the width when stacked",
          src.count("flex-1 sm:flex-none") == 2,
          "two half-width buttons beat two tiny ones")

    # Anything below about 40px is hard to hit with a thumb.
    check("the buttons are tall enough to hit",
          src.count("py-3 sm:py-2.5") == 2,
          "py-2.5 renders at 38px, under a comfortable thumb target")

    check("it clears the home indicator",
          "safe-area-inset-bottom" in src,
          "a bar pinned to the bottom sits under the gesture bar otherwise")


# ══════════════════════════════════════════════════════════════════════
#  Grids that were three columns everywhere
# ══════════════════════════════════════════════════════════════════════


# The four that hold numbers. The three that hold short words -- "Auf 0",
# "Weiter", "Kanal" -- are deliberately left at three columns: they fit,
# and wrapping them would look worse.
NUMBER_GRIDS = [
    "components/dashboard/anonchat-panel.tsx",
    "components/dashboard/extras-panels.tsx",
    "components/dashboard/joindm-panel.tsx",
    "components/dashboard/vanity-panel.tsx",
]


def test_stat_grids():
    print("\nStat grids")

    for path in NUMBER_GRIDS:
        src = read(path)
        check(f"{os.path.basename(path)}: stat tiles wrap on a phone",
              "grid-cols-2 sm:grid-cols-3" in src,
              "375px split three ways leaves 58px, and 1.204 does not fit")


def test_no_desktop_only_padding():
    """
    A card whose padding is written for a desktop wastes a sixth of a
    phone screen on margin.
    """
    print("\nPadding")

    header = read("app/dashboard/layout.tsx")
    check("the header padding scales",
          "px-3 lg:px-8" in header,
          "px-8 is 32px each side of a 375px screen")
    check("the header height scales", "h-16 lg:h-20" in header)
    check("the main area padding scales",
          "p-3 sm:p-6 lg:p-10" in header)

    guild = read("components/dashboard/guild-header.tsx")
    check("the guild header padding scales",
          "p-4 sm:p-6 lg:p-8" in guild)
    check("the server icon shrinks on a phone",
          "h-20 w-20 lg:h-[120px]" in guild,
          "120px of a 375px screen is a third of the width, for an icon")
    check("a long server name does not need 4xl on a phone",
          "text-2xl sm:text-3xl lg:text-4xl" in guild)

    # The bulk change across the panels. Spot-checked rather than
    # counted exactly, so adding a panel does not fail the test.
    scaled = 0
    folder = os.path.join(DASH, "components/dashboard")
    for name in sorted(os.listdir(folder)):
        if name.endswith(".tsx") and "p-4 sm:p-6" in read(f"components/dashboard/{name}"):
            scaled += 1
    check("most panels scale their card padding", scaled >= 25, str(scaled))


def test_tab_bar_on_a_phone():
    print("\nTab bar")

    src = read("components/guild-tabs.tsx")

    check("the search box gets its own row on a phone",
          "w-full sm:flex-1" in src,
          "beside the Übersicht button its placeholder was cut off")
    check("the tabs are tall enough to hit",
          "py-3 sm:py-2.5" in src)
    check("the group headers are tall enough too",
          "py-3.5 sm:py-3" in src)


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_viewport()
    test_save_bar()
    test_stat_grids()
    test_no_desktop_only_padding()
    test_tab_bar_on_a_phone()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
