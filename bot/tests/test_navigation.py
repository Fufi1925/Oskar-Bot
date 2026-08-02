#!/usr/bin/env python3
"""
The guild navigation, and the removal of birthdays.

Three things this pins down:

  * **Birthdays are gone everywhere.** Removing a feature by deleting
    its cog leaves the API route answering, the dashboard tab linking
    into a 404, and the backup still trying to copy a file nobody
    writes. This checks the whole trail: cogs, registration, store, API,
    dashboard page, tab bar, sidebar, api client, bootstrap and the
    backup file list.

  * **The tab bar covers every page exactly once.** It used to be 32
    tabs in one flat row -- and Tracking had a page with no tab at all,
    so the only way in was to type the URL. A link with no page is a
    404; a page with no link is unreachable. Both are checked against
    the folders on disk.

  * **Anonymer Chat is marked as beta**, in both navigations, because
    the tab bar and the sidebar are separate lists and have drifted
    apart before.

Run:  python3 tests/test_navigation.py
"""

import json
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
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def strip_comments(src: str) -> str:
    """
    Drop /* */ and // comments.

    A note explaining that a feature was removed necessarily contains
    the word, and matching that would fail the check on the very commit
    that does the removing.
    """
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def strip_py_comments(src: str) -> str:
    without_doc = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return re.sub(r"^\s*#.*$", "", without_doc, flags=re.M)


# ══════════════════════════════════════════════════════════════════════
#  Birthdays are gone
# ══════════════════════════════════════════════════════════════════════


def test_birthday_removed_from_bot():
    print("\nBirthdays: the bot")

    for path in ("cogs/commands/Birthday.py", "cogs/universitybot/birth.py"):
        check(f"{path} is deleted", not os.path.exists(os.path.join(BOT, path)))

    registry = strip_py_comments(read(os.path.join(BOT, "cogs/__init__.py")))
    check("the cog registry does not import it",
          "Birthday" not in registry and "birth" not in registry,
          "a stale import crashes the whole bot at startup")

    store = strip_py_comments(read(os.path.join(BOT, "utils/extras_store.py")))
    for name in ("birthday_list", "birthday_set", "birthday_remove",
                 "birthday_upcoming", "BIRTHDAY_JSON"):
        check(f"the store has no {name}", name not in store)

    extras = strip_py_comments(read(os.path.join(BOT, "api/routes/extras.py")))
    check("the API has no birthday routes",
          "birthday" not in extras.lower(),
          "a route answering for a feature that is gone is worse than a 404")

    boot = strip_py_comments(read(os.path.join(BOT, "utils/bootstrap.py")))
    check("bootstrap no longer creates the json files",
          "birthday" not in boot.lower())

    transfer = strip_py_comments(read(os.path.join(BOT, "api/config_transfer.py")))
    check("backups no longer try to copy them",
          "birthday" not in transfer.lower(),
          "copying a file nobody writes any more")

    help_src = strip_py_comments(read(os.path.join(BOT, "cogs/commands/help.py")))
    check("the help menu does not list it",
          "Birthday" not in help_src)
    # The help menu died once already over an emoji that was imported but
    # no longer valid, so an unused import here is worth catching.
    check("and does not import an emoji it no longer uses",
          not re.search(r"\bZCIRCLE\b(?!_)", help_src),
          "ZCIRCLE was only used by the birthday line")


def test_birthday_removed_from_dashboard():
    print("\nBirthdays: the dashboard")

    page = os.path.join(DASH, "app/dashboard/guild/[guildId]/birthday")
    check("the page folder is deleted", not os.path.exists(page))

    for name in ("lib/api.ts",
                 "components/dashboard/extras-panels.tsx",
                 "components/guild-tabs.tsx",
                 "app/dashboard/layout.tsx",
                 "components/dashboard/full-backup-panel.tsx"):
        src = strip_comments(read(os.path.join(DASH, name)))
        check(f"{name} has no birthday left",
              "birthday" not in src.lower() and "geburtstag" not in src.lower())


# ══════════════════════════════════════════════════════════════════════
#  The tab bar
# ══════════════════════════════════════════════════════════════════════


def guild_pages() -> set[str]:
    root = os.path.join(DASH, "app/dashboard/guild/[guildId]")
    return {
        entry for entry in os.listdir(root)
        if os.path.isdir(os.path.join(root, entry))
    }


def test_tab_bar():
    print("\nTab bar")

    src = read(os.path.join(DASH, "components/guild-tabs.tsx"))
    slugs = re.findall(r'slug: "([a-z0-9-]+)"', src)
    pages = guild_pages()

    check("the bar has tabs at all", len(slugs) > 20, str(len(slugs)))

    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    check("no tab is listed twice", not duplicates, str(duplicates))

    missing_page = sorted(set(slugs) - pages)
    check("every tab points at a page that exists",
          not missing_page, str(missing_page))

    # This is the one that was actually broken: tracking had a page and
    # no tab, so it could only be reached by typing the URL.
    unreachable = sorted(pages - set(slugs))
    check("every page is reachable from the bar",
          not unreachable, str(unreachable))

    # Grouping. A flat list of 32 is what this replaced.
    groups = re.findall(r'name: "([^"]+)",\n      icon: \w+,\n      tabs: \[', src)
    check("the tabs are grouped", len(groups) >= 4, str(groups))
    check("every group has a name", all(g.strip() for g in groups))

    # Search, because 32 tabs is more than anyone scans by eye.
    check("there is a search box", "Einstellung suchen" in src)
    check("search also matches alternative words",
          "also:" in src,
          "somebody looking for 'xp' should find Level-System")

    # The group holding the current page must open by itself, or landing
    # on a page shows a collapsed bar with no hint where you are.
    check("the active group opens on its own",
          "setOpenGroup(activeGroup)" in src)


def test_beta_marking():
    print("\nBeta marking")

    tabs = read(os.path.join(DASH, "components/guild-tabs.tsx"))
    entry = re.search(
        r'slug: "anonchat",\s*\n\s*icon: \w+,\s*\n\s*tag: "beta"', tabs
    )
    check("anonchat is tagged beta in the tab bar", entry is not None)
    check("the badge is actually rendered", 'BETA' in tabs)
    check("and it explains what beta means",
          "Beta:" in tabs,
          "a badge nobody can interpret is decoration")

    # Two navigations that disagree is how the sidebar and the tab bar
    # drifted apart in the first place.
    sidebar = read(os.path.join(DASH, "app/dashboard/layout.tsx"))
    check("the sidebar says beta too",
          "Anonymer Chat (Beta)" in sidebar,
          "the two navigations must not disagree")

    # Nothing else claims to be beta unless it is in both.
    tab_betas = set(re.findall(r'slug: "([a-z0-9-]+)",\s*\n\s*icon: \w+,\s*\n\s*tag: "beta"', tabs))
    check("only anonchat is marked beta", tab_betas == {"anonchat"},
          str(tab_betas))


def test_both_navigations_agree():
    print("\nSidebar")

    sidebar = read(os.path.join(DASH, "app/dashboard/layout.tsx"))
    tabs = read(os.path.join(DASH, "components/guild-tabs.tsx"))

    side_slugs = set(re.findall(
        r"/dashboard/guild/\$\{currentGuildId\}/([a-z0-9-]+)", sidebar
    ))
    tab_slugs = set(re.findall(r'slug: "([a-z0-9-]+)"', tabs))
    pages = guild_pages()

    check("the sidebar links nothing that does not exist",
          not (side_slugs - pages), str(sorted(side_slugs - pages)))

    # The sidebar may legitimately be shorter, but anything it does list
    # has to be in the tab bar too, or the two disagree about where a
    # setting lives.
    check("everything in the sidebar is also in the tab bar",
          not (side_slugs - tab_slugs), str(sorted(side_slugs - tab_slugs)))

    # Same group names in both, so "Schutz" means the same thing twice.
    tab_groups = set(re.findall(
        r'name: "([^"]+)",\n      icon: \w+,\n      tabs: \[', tabs
    ))
    side_groups = set(re.findall(r'\n          name: "([^"]+)",\n          items: \[', sidebar))
    check("both navigations use the same group names",
          tab_groups == side_groups,
          f"tabs={sorted(tab_groups)} sidebar={sorted(side_groups)}")


def test_tab_names_are_consistent():
    """
    One tab, one name, in all four places it appears.

    The logging tab was called "Protokollierung" in the sidebar, the tab
    bar, the page heading and the panel title -- four separate strings,
    with nothing checking they agreed. Renaming it meant finding all
    four by hand, and missing one would show a different name depending
    on where you looked.

    Now called "Logs", and asserted rather than hoped for.
    """
    print("\nTab names agree everywhere")

    places = {
        "sidebar": "app/dashboard/layout.tsx",
        "tab bar": "components/guild-tabs.tsx",
        "page heading": "app/dashboard/guild/[guildId]/logging/page.tsx",
        "panel title": "components/dashboard/logging-panel.tsx",
    }

    for label, path in places.items():
        # Comments stripped: the tab file explains in a comment that the
        # old name stays searchable, and that sentence necessarily
        # contains the old name. Checking the raw text failed on the
        # very code that documents the decision.
        body = strip_comments(read(os.path.join(DASH, path)))
        check(f"{label}: says Logs", '"Logs"' in body or ">Logs" in body
              or "Logs\n" in body, path)
        check(f"{label}: no longer says Protokollierung",
              "Protokollierung" not in body,
              "a half-finished rename shows a different name depending "
              "on where you look")

    # The old name has to stay findable. Somebody who learned it should
    # not lose the tab because it was renamed.
    # Comments stripped: the code carries a comment explaining why the
    # old name stays searchable, and a plain search finds that comment
    # instead of the actual keyword. Removing the keyword then looked
    # fine.
    tabs = strip_comments(read(os.path.join(DASH, "components/guild-tabs.tsx")))
    check("the old name is still searchable",
          "protokoll" in tabs.lower(),
          "renaming a tab must not hide it from people who know the "
          "old name")

    search = strip_comments(read(os.path.join(DASH, "components/global-search.tsx")))
    check("global search calls it the same thing",
          '"Logs"' in search and '"Logging"' not in search,
          "the search result and the tab it opens must not disagree")
    check("and still matches the old name",
          "protokoll" in search.lower(), "")


def test_admin_link_style():
    """
    The Admin entry in the sidebar looks like admin, not like Premium.

    Premium glows gold because it sells something. Admin leads somewhere
    consequential and is clicked daily, so it gets a steady steel plate
    and deliberately no pulse -- a permanent animation on a link people
    use constantly is just fatigue.
    """
    print("\nAdmin link in the sidebar")

    layout = strip_comments(read(os.path.join(DASH, "app", "dashboard", "layout.tsx")))

    check("the admin link has its own class", "admin-link" in layout)
    # Keyed off the href: the label is translated, so matching the word
    # "Admin" would silently lose the styling in another language.
    check("it is matched by href, not by label",
          'item.href === "/dashboard/admin"' in layout,
          "matching on the label breaks under translation")
    check("the active state reaches the CSS",
          'data-active={isActive ? "true" : undefined}' in layout,
          "the edge marker cannot know which link is open")
    check("it does not reuse the premium glow",
          "premium-link" in layout and layout.count("admin-link") >= 1
          and "admin-link premium-link" not in layout,
          "admin would pulse like a sales link")

    css = read(os.path.join(DASH, "app", "globals.css"))
    check("the class is defined", ".admin-link" in css)
    # A grey plate on a dark navy sidebar read as disabled. The tile has
    # to be filled to look like the most powerful link in the list.
    # Both parts, and both inside their own rule: checking the words
    # separately passed even with the badge rule renamed away, because
    # "linear-gradient" appears elsewhere in the stylesheet.
    link_rule = css[css.index(".admin-link {"):] if ".admin-link {" in css else ""
    link_rule = link_rule[: link_rule.index("}")] if "}" in link_rule else ""
    check("the link itself is filled",
          "linear-gradient" in link_rule,
          "a low-contrast outline reads as a disabled item")
    # The name also appears inside the reduced-motion block, so a plain
    # "is it mentioned" check passed with the real rule renamed away.
    # Look for what the badge actually needs to be a tile.
    badge_rule = ""
    for chunk in css.split(".admin-badge {")[1:]:
        candidate = chunk[: chunk.index("}")] if "}" in chunk else ""
        if "background" in candidate:
            badge_rule = candidate
            break
    check("the badge is a real tile",
          "background" in badge_rule and "border-radius" in badge_rule,
          "the icon has no filled tile to sit in")
    # In JSX it is a class name without the dot; in CSS it has one.
    check("the icon sits in its own badge",
          'className="admin-badge' in layout,
          "a bare glyph looks like every other row")
    check("the open link is marked",
          '.admin-link[data-active="true"]' in css)
    # The point of the difference: the *link* must not pulse. Taking
    # everything from ".admin-link" to the end of the file swept in the
    # header's background wash, which is a different element entirely.
    link_rules = [
        chunk[: chunk.index("}")]
        for chunk in css.split(".admin-link")[1:]
        if "}" in chunk
    ]
    check("admin has no endless pulse",
          not any("infinite" in rule for rule in link_rules),
          "the admin link animates like premium")


def test_admin_tab_groups():
    """
    The admin tab bar is grouped.

    Twenty tabs in one flex-wrap row spilled across three lines of
    identical buttons, so finding one meant reading all twenty.

    The risk when grouping: a tab left out of the groups is not just
    misplaced, it disappears from the UI completely.
    """
    print("\nAdmin tab bar")

    src = read(os.path.join(DASH, "components", "dashboard", "admin-content.tsx"))
    body = strip_comments(src)

    check("the groups exist", "TAB_GROUPS" in body)

    defined = re.findall(r'\{ id: "(\w+)", label:', body)
    start = body.index("const TAB_GROUPS")
    block = body[start:body.index("];", start)]
    names = re.findall(r'name: "(\w+)"', block)
    grouped = [t for t in re.findall(r'"(\w+)"', block) if t not in names]

    check("every tab is in a group", not set(defined) - set(grouped),
          f"missing from the bar: {sorted(set(defined) - set(grouped))}")
    check("no group lists an unknown tab", not set(grouped) - set(defined),
          f"unknown: {sorted(set(grouped) - set(defined))}")
    check("no tab appears twice",
          len(grouped) == len(set(grouped)),
          f"duplicated: {[t for t in set(grouped) if grouped.count(t) > 1]}")
    check("the groups have names", len(names) >= 3, str(names))

    # Four stacked groups of different lengths looked worse than the
    # twenty buttons they replaced. One section at a time keeps it to a
    # single tidy row.
    check("one section is shown at a time",
          "TAB_GROUPS.filter((group) => group.ids.includes(activeTab))" in body,
          "all groups render at once again")
    # A section nobody may open promises something that is not there.
    check("empty sections are hidden",
          "if (count === 0) return null" in body,
          "a section the user cannot use would still show")
    check("the section shows how many tabs it holds", "{count}" in body)
    # Colour alone is not enough to say which section is open.
    check("the open section is underlined",
          "absolute inset-x-3 bottom-0" in body,
          "only colour marks the open section")
    check("the open tab is announced to screen readers",
          'aria-current={active ? "page" : undefined}' in body)
    check("the open section is announced too",
          'aria-current={open ? "true" : undefined}' in body)
    check("the bar is a landmark", "<nav" in body and "aria-label" in body)


def test_admin_glass_surfaces():
    """
    The admin panel is glass, not flat navy boxes.

    Real glass needs three things at once and the old version had none:
    a blur behind it, an edge brighter at the top than the bottom, and a
    highlight where light would fall.
    """
    print("\nAdmin glass")

    css = read(os.path.join(DASH, "app", "globals.css"))
    body = strip_comments(read(
        os.path.join(DASH, "components", "dashboard", "admin-content.tsx")
    ))

    check("the surface class exists", ".admin-glass {" in css)

    rule = ""
    for chunk in css.split(".admin-glass {")[1:]:
        candidate = chunk[: chunk.index("}")] if "}" in chunk else ""
        if "backdrop-filter" in candidate:
            rule = candidate
            break
    # The unprefixed property specifically: "-webkit-backdrop-filter"
    # contains the string "backdrop-filter", so a loose check passed
    # with the standard property deleted -- and every non-Safari browser
    # would have shown a flat box.
    check("it actually blurs what is behind it",
          any(line.strip().startswith("backdrop-filter:")
              for line in rule.splitlines()),
          "without the unprefixed property only Safari blurs")
    check("the blur is prefixed for Safari",
          "-webkit-backdrop-filter" in rule,
          "Safari would render a flat panel")
    check("there is an inner highlight", "inset 0 1px 0" in rule)
    check("there is a rim light", ".admin-glass::before" in css)
    # An overlay across the whole card would swallow every click on it.
    before = css[css.index(".admin-glass::before"):]
    before = before[: before.index("}")]
    check("the rim does not eat clicks",
          "pointer-events: none" in before,
          "the overlay would block the buttons underneath")
    # Firefox and older Safari have no backdrop-filter; without a
    # fallback the text sits on almost nothing.
    check("browsers without backdrop-filter get a solid fill",
          "@supports not (backdrop-filter" in css)

    check("the header uses it", "admin-hero admin-glass" in body)
    check("the cards use it", body.count("admin-glass") >= 3)
    check("the tab bar uses it",
          'className="admin-glass rounded-3xl overflow-hidden"' in body)

    # The drift is decoration on a page people keep open.
    check("the background wash can be switched off",
          any("admin-hero" in block for block in
              css.split("prefers-reduced-motion")[1:]),
          "the header animates regardless of the system setting")


def test_admin_live_badge():
    """
    The stat cards showed a green LIVE badge each.

    The panel refreshes every 30 seconds, so "live" was a small lie, and
    four identical badges carried no information. A ticking age says
    whether the number is current — and turns amber when the refresh
    loop has stopped, which is the case a green badge would hide.
    """
    print("\nData age instead of LIVE")

    body = strip_comments(read(
        os.path.join(DASH, "components", "dashboard", "admin-content.tsx")
    ))
    widget = strip_comments(read(os.path.join(DASH, "components", "ui", "data-age.tsx")))

    check("the badge component exists", "export function DataAge" in widget)
    check("the cards use it", "<DataAge" in body)
    check("the fake LIVE badge is gone",
          ">Live<" not in body and ">LIVE<" not in body,
          "a badge claiming live on 30s-old data")

    check("the age ticks", "setInterval" in widget)
    # A clock in the page component re-renders twenty tab buttons and a
    # table once a second.
    check("the interval lives in the badge, not the page",
          "setInterval" in widget)
    check("the interval is cleared", "clearInterval" in widget,
          "a timer per card would pile up on every re-render")
    check("stale data is marked differently",
          "staleAfter" in widget and "amber" in widget,
          "a stopped refresh loop would still look healthy")

    # Stamping the time in `finally` would make a failed refresh look
    # fresh while the figures on screen are the old ones.
    fetch = body[body.index("const fetchData"):]
    fetch = fetch[: fetch.index("  };")]
    check("the timestamp is only set on success",
          "setLastLoaded" in fetch
          and fetch.index("setLastLoaded") < fetch.index("} catch"),
          "a failed refresh would reset the age to 'gerade eben'")


def test_admin_stat_values():
    """
    Stat figures animate to their new value.

    They are strings with units -- "16.51ms", "0.94 MB" -- so CountUp
    cannot take them, and a naive parseFloat would print "0.94" where
    "0,94 MB" belongs.
    """
    print("\nAnimated stat figures")

    widget = strip_comments(read(os.path.join(DASH, "components", "ui", "stat-value.tsx")))
    body = strip_comments(read(
        os.path.join(DASH, "components", "dashboard", "admin-content.tsx")
    ))

    check("the component exists", "export function StatValue" in widget)
    check("the cards use it", "<StatValue" in body)
    check("the unit is kept", "suffix" in widget,
          "'0.94 MB' would lose its unit")
    # The gap has to be captured with the unit, not skipped.
    check("the space before the unit survives",
          r"(\s*.*)$" in widget,
          "'0,94 MB' would render as '0,94MB'")
    check("text without a number is left alone",
          "if (!parsed)" in widget,
          "an error string would become NaN")
    check("it counts from the previous figure",
          "from.current" in widget,
          "every refresh would snap back to zero")
    check("reduced motion skips the animation", "reduced" in widget)


def test_proximity_effect():
    """
    The LineSidebar proximity effect, adapted rather than dropped in.

    React Bits' component takes `items: string[]` and an `onItemClick`,
    and renders `<li onClick>`. Using it as-is would have replaced real
    links with click handlers, losing right-click "open in new tab",
    middle-click, the URL preview and Next.js prefetching. The visual
    idea is worth having; that trade is not — so the mechanism was kept
    as a hook and the markup left alone.
    """
    print("\nProximity effect")

    hook_path = os.path.join(DASH, "components", "ui", "proximity.tsx")
    check("the hook exists", os.path.isfile(hook_path), hook_path)
    hook = strip_comments(read(hook_path))
    layout = strip_comments(read(os.path.join(DASH, "app", "dashboard", "layout.tsx")))

    check("it is a client component", '"use client"' in hook)
    check("all three falloff curves are there",
          "linear:" in hook and "smooth:" in hook and "sharp:" in hook)
    check("one shared rAF loop drives every row",
          "requestAnimationFrame" in hook)
    check("the loop is cancelled on unmount",
          "cancelAnimationFrame" in hook,
          "a leaked loop keeps running after navigation")
    # A fixed step per frame runs at double speed on a 144 Hz display.
    check("the easing is frame-rate independent",
          "Math.exp" in hook,
          "the effect would run faster on a high refresh rate screen")
    # Without a floor the loop chases a difference nobody can see.
    check("the loop stops when settled", "settled" in hook)
    # A touch drag is a scroll, not a hover.
    check("touch drags are ignored",
          'pointerType === "touch"' in hook,
          "scrolling on a phone would light up rows under the finger")

    print("\nThe sidebar keeps real links")
    check("rows are still Link elements",
          "prox-row" in layout and "<Link" in layout)
    check("the effect is attached to them", "proximity.itemProps" in layout)
    check("the container handles the pointer",
          "proximity.containerProps" in layout)
    # React runs every hook on every render; the layout returns early
    # while the session loads.
    check("the hook runs before the early return",
          layout.index("useProximity({")
          < layout.index('if (status === "loading"'),
          "the hook would be skipped while loading and React would throw")
    # The container has to be the rows' offsetParent, or every distance
    # is measured against the wrong box. Reading it off the first row's
    # offsetParent guessed; the ref does not.
    check("the container is passed in explicitly",
          "ref:" in hook and "container.current = el" in hook,
          "offsetParent guessing breaks as soon as a wrapper is added")

    print("\nNo numbers and no tick marks")
    # Both come from the original LineSidebar. The 01/02/03 gutter was
    # the loudest thing in a sidebar that is read by label, and the line
    # was a second signal for what the movement already says. The shift
    # is the whole effect now.
    search_src = strip_comments(
        read(os.path.join(DASH, "components", "global-search.tsx")))
    css_src = strip_comments(read(os.path.join(DASH, "app", "globals.css")))

    check("no index element is rendered",
          "prox-index" not in layout,
          "the numbers are back")
    check("no index is styled either",
          "prox-index" not in css_src,
          "dead CSS for an element that no longer exists")
    check("nothing still builds a padded number",
          'padStart(2, "0")' not in layout,
          "leftover numbering code")
    check("no marker span in the sidebar",
          "prox-marker" not in layout,
          "the tick marks are back")
    check("none in the search results either",
          "prox-marker" not in search_src,
          "the dropdown kept a line the sidebar dropped")
    check("no marker rule is left behind",
          "prox-marker" not in css_src,
          "dead CSS for an element nothing renders")
    # The accent colour and the color-mix fallback existed only to tint
    # the line. With the line gone they are dead weight -- and color-mix
    # is used nowhere else in the project.
    check("the marker-only accent variable is gone",
          "prox-accent" not in css_src,
          "a custom property nothing reads")
    check("and the color-mix it fed",
          "color-mix" not in css_src,
          "a fallback for a declaration that no longer exists")

    print("\nEvery link takes part, not just the top level")
    # Inside a guild the sidebar is mostly sub-links. Lighting only the
    # four flat rows meant the effect was invisible on most pages.
    check("sub-links carry the row class",
          layout.count("prox-row") >= 2,
          "only the top-level rows would react")
    check("sub-links get their own index",
          layout.count("proximity.itemProps") >= 2)
    check("one running index covers both levels",
          "nextIndex()" in layout,
          "two counters would hand the same index to two rows")
    check("nested rows are toned down",
          "prox-row-sm" in layout,
          "a full-size shift makes a nested list look like it is coming apart")

    print("\nCSS")
    # Comments stripped throughout: notes explaining what a rule avoids
    # necessarily contain the thing being avoided, and matching those
    # has let mutated trees pass before.
    css = css_src
    check("the row class exists", ".prox-row {" in css)
    # Cut each media block to its own body first. A raw split chunk runs
    # to the end of the file, so an earlier reduced-motion block matched
    # the .prox-row rules further down and this passed with the block
    # deleted outright.
    def media_bodies(source: str, query: str) -> list[str]:
        out = []
        for chunk in source.split(query)[1:]:
            out.append(chunk[: chunk.index("\n}\n")] if "\n}\n" in chunk else chunk)
        return out

    check("motion can be switched off",
          any(".prox-row" in body and "transform: none" in body
              for body in media_bodies(css, "prefers-reduced-motion")),
          "the shift ignores the system setting")

    # How far a row may slide is bounded, not a matter of taste. The nav
    # is `overflow-y: auto`; per CSS Overflow 3 the other axis computes
    # to `auto` as well, and a scroll container clips at its padding
    # box. Sidebar 256px - 2x16px nav padding leaves exactly 16px of
    # room. Past that the row is clipped, or the nav scrolls sideways
    # under `no-scrollbar` -- invisibly. See repro/prox_shift_budget.py.
    # Read the padding off the nav instead of hard-coding it. It was
    # 16px, then had to grow to 40px so the rows could travel further --
    # and a copy of the number in this file just went stale and failed
    # against correct CSS. The point of the check is that the two agree.
    SIDEBAR_W = 256
    nav_class = re.search(
        r'className="mt-8 ([^"]*?)\s+space-y-6[^"]*overflow-y-auto', layout
    )
    check("the nav padding can be read",
          nav_class is not None,
          "cannot verify the shift budget without it")
    pad_right = re.search(r"\bpr-(\d+)\b", nav_class.group(1)) if nav_class else None
    both = re.search(r"\bpx-(\d+)\b", nav_class.group(1)) if nav_class else None
    # Tailwind's spacing scale is 4px per step.
    NAV_PAD = int((pad_right or both).group(1)) * 4 if (pad_right or both) else 0
    budget = NAV_PAD

    def shift_of(rule: str) -> int:
        """The px value of --prox-shift in a rule body, 0 if absent."""
        found = re.search(r"--prox-shift:\s*(\d+)px", rule)
        return int(found.group(1)) if found else 0

    # The default lives in the translateX fallback, the nested override
    # in .prox-row-sm.
    row_rule = css.split(".prox-row {")[1]
    row_rule = row_rule[: row_rule.index("}")]
    default_shift = re.search(r"var\(--prox-shift,\s*(\d+)px\)", row_rule)
    check("the row shifts on --effect",
          default_shift is not None and "translateX" in row_rule,
          "no movement means no effect at all")

    top_shift = int(default_shift.group(1)) if default_shift else 0
    check("the top-level shift is bigger than it was",
          top_shift > 8,
          f"asked for more travel, got {top_shift}px (was 8px)")
    check("and still inside the padding edge",
          top_shift <= budget,
          f"{top_shift}px against {budget}px of room "
          f"({SIDEBAR_W}px sidebar, {NAV_PAD}px nav padding) would clip")

    sm_rule = css.split(".prox-row-sm {")[1]
    sm_rule = sm_rule[: sm_rule.index("}")]
    nested_shift = shift_of(sm_rule)
    check("nested rows shift further too",
          nested_shift > 5,
          f"got {nested_shift}px (was 5px)")
    check("but still less than the top level",
          0 < nested_shift < top_shift,
          "a nested list that travels as far looks like it is coming apart")
    # LineSidebar's own maxShift. The nav padding was widened to make
    # room for exactly this, so if the travel shrinks again the padding
    # is just wasted space.
    check("the top-level travel is LineSidebar's 37px",
          top_shift == 37,
          f"got {top_shift}px")
    # The search dropdown is not in the nav and has no spare padding of
    # its own, so it must not inherit the sidebar's travel.
    tight_rule = css.split(".prox-row-tight {")[1]
    tight_rule = tight_rule[: tight_rule.index("}")]
    tight_shift = shift_of(tight_rule)
    check("the dropdown keeps a small travel",
          0 < tight_shift <= 12,
          f"{tight_shift}px would be clipped by the dropdown's own edge")
    search_src = strip_comments(
        read(os.path.join(DASH, "components", "global-search.tsx")))
    check("and the dropdown actually uses it",
          "prox-row-tight" in search_src and "prox-row-sm" not in search_src,
          "the dropdown would slide as far as the sidebar")
    check("and inside the budget as well",
          nested_shift <= budget,
          f"{nested_shift}px against {budget}px of room")

    print("\nSmoothing")
    # Both lists must *ask* for a time constant, and it has to be a
    # usable one -- but not a specific number. Pinning it to 120 made
    # this fail the moment the value was tuned by hand, against a
    # perfectly good setting. The hook divides by it, so 0 is the only
    # value that actually breaks; the upper bound is just "still feels
    # like a response".
    for label, src in (("sidebar", layout), ("search", search_src)):
        found = re.search(r"smoothing:\s*(\d+)", src)
        value = int(found.group(1)) if found else None
        check(f"the {label} sets a smoothing time",
              value is not None and 0 < value <= 600,
              f"got {value}")
    hook_default = re.search(r"smoothing\s*=\s*(\d+)", hook)
    default = int(hook_default.group(1)) if hook_default else None
    check("the hook has a sane default",
          default is not None and 0 < default <= 600,
          f"got {default}")

    print("\nThe search results use it too")
    search = strip_comments(read(os.path.join(DASH, "components", "global-search.tsx")))
    check("rows carry the class", "prox-row" in search)
    check("the container is wired up",
          "proximity.containerProps" in search)
    # The dropdown is `absolute`, which already makes it the offsetParent.
    # Tailwind emits `relative` after `absolute`, so adding it would win
    # and drop the panel back into the flow.
    check("no relative is added to the absolute dropdown",
          "z-50 py-2 relative" not in search,
          "the dropdown would stop floating over the page")
    # Keyboard and mouse must not end up with two separate highlights.
    check("the keyboard cursor drives the same effect",
          "activeIndex: open" in search,
          "arrowing down would light nothing")
    # The result list is rebuilt on every keystroke.
    check("stale rows are dropped when the list shrinks",
          "setProxCount(results.length)" in search,
          "rows from a longer previous search keep being eased")
    # useProximity returns a fresh object literal every render.
    check("the effect does not depend on the whole object",
          "proximity]" not in search,
          "an unstable dependency re-runs the effect on every render")

    print("\nThe tab rows use it, measured in two dimensions")
    # This used to assert the opposite: the hook measured y only, and a
    # wrapping row of buttons all share an offsetTop, so every tab in a
    # line lit at once. The hook now takes an axis, and the rows opt
    # into the real 2D distance -- so the old assertion is gone rather
    # than weakened.
    admin = strip_comments(read(
        os.path.join(DASH, "components", "dashboard", "admin-content.tsx")
    ))
    tabs = strip_comments(read(os.path.join(DASH, "components", "guild-tabs.tsx")))

    check("the hook can measure both axes",
          'axis === "vertical"' in hook and "Math.sqrt" in hook,
          "a wrapping row needs real distance, not just y")
    check("a stacked list still measures y only",
          "Math.abs(y - cy)" in hook,
          "using 2D on a full-width list would dim rows toward the edges")

    for label, src in (("admin", admin), ("guild", tabs)):
        check(f"the {label} tab row asks for both axes",
              'axis: "both"' in src,
              "every tab in a line would light at once")
        check(f"the {label} row is the offsetParent",
              "relative" in src and "containerProps" in src,
              "distances would be measured against the wrong box")
        # Not just "the word appears": the count has to come from the
        # list that is actually rendered. A hard-coded number keeps
        # easing rows that have left the page, and passes a check that
        # only looks for the identifier.
        check(f"the {label} row drops stale buttons",
              re.search(r"set(?:Tab)?Count\((?:shownTabs|tabs)\.length\)", src)
              is not None,
              "switching groups leaves rows being eased that are gone")

    # Each collapsible group is its own container. One shared instance
    # would measure every tab against whichever group registered first.
    # Checking that the component is *declared* is not enough -- it has
    # to be the thing the groups actually render, which is what the
    # first version of this check missed.
    check("each guild tab row gets its own instance",
          "function TabRow" in tabs and tabs.count("<TabRow") >= 2,
          "one hook across separate containers measures the wrong box")
    check("the old inline rows are gone",
          "flex gap-2 flex-wrap\">" not in tabs,
          "a hand-rolled row would have no effect at all")

    print("\nThe tab movement fits a sideways row")
    # LineSidebar's maxShift: 37 is a horizontal push on a vertical
    # list -- items slide into empty space. These tabs sit shoulder to
    # shoulder, so the travel is perpendicular here too: vertical, and
    # small enough to stay inside the strip.
    tab_rule = ""
    for chunk in css.split(".prox-tab {")[1:]:
        body = chunk[: chunk.index("}")] if "}" in chunk else ""
        if "transform" in body:
            tab_rule = body
            break
    check("tabs lift rather than slide sideways",
          "translateY" in tab_rule and "translateX" not in tab_rule,
          "a sideways push drives a tab into its neighbour")
    lift = re.search(r"translateY\(calc\(var\(--effect, 0\) \* -(\d+)px\)\)", tab_rule)
    check("the lift stays inside the strip",
          lift is not None and int(lift.group(1)) <= 12,
          f"{lift.group(1) if lift else '?'}px would leave the row or resize it")
    # `transition-all` from the Tailwind class would fight the rAF loop.
    # Read the declaration itself, not the rest of the rule: the first
    # version of this check matched `will-change: transform` on the next
    # line and failed against correct CSS.
    transitioned = re.search(r"transition-property:\s*([^;]+);", tab_rule)
    check("the transform is not also transitioned",
          transitioned is not None
          and "transform" not in transitioned.group(1)
          and "all" not in transitioned.group(1).split(","),
          "a CSS transition on top of the loop lags behind the cursor")


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_birthday_removed_from_bot()
    test_birthday_removed_from_dashboard()
    test_tab_bar()
    test_beta_marking()
    test_both_navigations_agree()
    test_tab_names_are_consistent()
    test_admin_link_style()
    test_admin_tab_groups()
    test_admin_glass_surfaces()
    test_admin_live_badge()
    test_admin_stat_values()
    test_proximity_effect()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
