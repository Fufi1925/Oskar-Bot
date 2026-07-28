#!/usr/bin/env python3
"""
Every guild tab has to have a save bar, and it has to be wired up.

This is a static check over the dashboard sources rather than a
behavioural one -- there is no Node in the test run -- but the four
things it pins down are exactly the ones that went wrong by hand:

  * A tab that edits a draft but has no bar. The change then lives in
    React state until you navigate away, and it is gone with no word.
  * A bar that is rendered but whose `useSaveGuard` was forgotten, so
    leaving is not refused after all.
  * A guard whose bar id does not match the bar's `id`, so the refusal
    scrolls to nothing and the shake never shows.
  * A save bar inside a `{dirty && ...}` wrapper *and* with its own
    `count` check, which used to double up and render an empty bar.

Run:  python3 tests/test_dashboard_save_bars.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Oskar-Bot", "dashboard")
if not os.path.isdir(DASH):
    DASH = os.path.join(os.path.dirname(os.path.dirname(HERE)), "dashboard")

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


# Tabs whose page is a list of actions with no draft state: nothing is
# ever "unsaved", so a save bar would never appear.
NO_DRAFT = {
    "invites",       # read-only statistics
    "giveaways",     # a dialog per giveaway, saved on confirm
    "compose",       # one-shot send
    "emergency",     # buttons that act immediately
    "admin-dashboard",
    "noprefix",      # add/remove entries, each its own request
    "reactionroles", # add/remove entries, each its own request
    "vanityroles",   # add/remove entries, each its own request
    "autoresponder", # add/remove entries, each its own request
    "birthday",      # add/remove entries
    "notify",        # add/remove entries
    "sticky",        # add/remove entries
    "customroles",   # add/remove entries plus its own bar in voice-panels
    "j2c",
    "invcrole",
    "booster",
    "nightmode",
    "jail",
    "counting",
    "tickets",       # dialogs with an explicit save
    "anonchat",      # a bar per channel card
    "leveling",
    "verification",
    "automod",
    "welcome",
    "settings",
    "joindm",
    "logging",
    "antinuke",
    "autorole",
    "nickname",
    "tracking",
    "autoreact",
}


def test_shared_module():
    print("\nThe shared module")

    path = os.path.join(DASH, "components/dashboard/save-bar.tsx")
    check("save-bar.tsx exists", os.path.exists(path))
    if not os.path.exists(path):
        return
    src = read(path)

    for name in ("StickySaveBar", "useUnsavedGuard", "useSaveGuard", "usePanel",
                 "useDraft", "Loading"):
        check(f"it exports {name}", f"export function {name}" in src)

    # The guard is what makes the bar more than decoration.
    check("the guard catches clicks in the capture phase",
          'document.addEventListener("click", onClick, true)' in src,
          "without capture, Next's Link has already routed")
    check("the guard also covers a reload",
          'window.addEventListener("beforeunload"' in src)
    check("external links are let through",
          "startsWith(window.location.origin)" in src)
    check("a link to the same page is let through",
          "href === window.location.pathname" in src)
    check("the bar hides itself when there is nothing to save",
          "if (!count) return null;" in src)
    check("the listeners are removed again",
          src.count("removeEventListener") == 2, str(src.count("removeEventListener")))


def test_every_panel():
    print("\nPanels")

    folder = os.path.join(DASH, "components/dashboard")
    pages = os.path.join(DASH, "app/dashboard/guild/[guildId]")

    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
             if f.endswith(".tsx")]
    for entry in sorted(os.listdir(pages)):
        page = os.path.join(pages, entry, "page.tsx")
        if os.path.isfile(page):
            files.append(page)

    for path in files:
        src = read(path)
        name = os.path.relpath(path, DASH)
        if "StickySaveBar" not in src:
            continue
        # save-bar.tsx defines it; it is not a consumer.
        if path.endswith("save-bar.tsx"):
            continue

        check(f"{name}: imports the bar from the shared module",
              'from "@/components/dashboard/save-bar"' in src)

        # Every rendered bar needs an id, and every id needs a guard
        # pointing at it -- otherwise the refusal has nothing to scroll
        # to and the user sees nothing happen at all.
        bar_ids = re.findall(r'<StickySaveBar\s+id="([^"]+)"', src)
        rendered = src.count("<StickySaveBar")
        check(f"{name}: every rendered bar carries an id",
              len(bar_ids) == rendered, f"{len(bar_ids)} ids for {rendered} bars")

        guard_ids = re.findall(r'useSaveGuard\([^,]+,\s*[`"]([^`"]+)[`"]\)', src)
        for bar_id in bar_ids:
            check(f"{name}: the guard for {bar_id} matches the bar",
                  bar_id in guard_ids, str(guard_ids))

        check(f"{name}: every bar has a discard",
              src.count("onDiscard=") >= rendered)
        check(f"{name}: every bar has a save",
              src.count("onSave=") >= rendered)
        check(f"{name}: the shake is passed through",
              src.count("shake={") >= rendered,
              "without it the refusal is invisible")

        # A bar inside `{dirty && ...}` on top of its own count check
        # renders nothing but still takes up the sticky slot.
        check(f"{name}: the bar is not double-gated",
              "{dirty && (\n        <StickySaveBar" not in src)


def test_admin_area():
    """
    The admin area has its own tabs, and two of them hold a draft.

    Bot Config is a long list of text fields whose only save button was
    in the header, four screens up. The dashboard notice in the System
    tab was worse: a 30-second poll called setNotification() with the
    server's value, so a longer notice had the text pulled out from
    under the cursor while it was being typed.
    """
    print("\nAdmin area")

    admin = os.path.join(DASH, "components/dashboard/admin-content.tsx")
    src = read(admin)

    check("the admin page has a rendered save bar for the notice",
          "<StickySaveBar" in src and 'id="admin-notice-save-bar"' in src)
    check("the notice save bar has a guard",
          'useSaveGuard(noticeDirty, "admin-notice-save-bar")' in src)
    # The poll must not overwrite an edit in progress.
    check("the 30-second poll leaves an edit in progress alone",
          "setNotification((current) =>" in src,
          "a bare setNotification() call clobbers what is being typed")
    check("and it remembers what the server last sent",
          "savedNotification.current" in src)

    settings = os.path.join(DASH, "components/dashboard/bot-settings-panel.tsx")
    src = read(settings)
    # Both halves: the guard *and* the rendered bar. Checking only for
    # the id string passed even after the whole <StickySaveBar> element
    # was deleted, because the useSaveGuard call still mentioned it.
    check("bot settings has a rendered save bar",
          "<StickySaveBar" in src and 'id="botsettings-save-bar"' in src)
    check("bot settings has the matching guard",
          'useSaveGuard(dirtyCount, "botsettings-save-bar")' in src)
    check("bot settings counts the changed fields, not just yes/no",
          "const dirtyCount = settings.filter(" in src)

    flags = os.path.join(DASH, "components/dashboard/feature-flags-panel.tsx")
    src = read(flags)
    # Not a save bar -- this one saves per switch on purpose -- but the
    # slider was lying about its own value.
    check("the rollout slider is controlled, so its number keeps up",
          "value={rolloutDraft[flag.key] ?? flag.rollout_percent}" in src,
          "defaultValue leaves the label showing the old percentage")
    check("the rollout slider can be moved with the keyboard",
          "onKeyUp=" in src,
          "mouse-up only means arrow keys set nothing")


def test_buttons_that_leave():
    """
    The guard hooks link clicks. Two places leave by button instead.

    Both were found only by walking the panels by hand after the guard
    was already in place, which is the point: "every tab has a bar" and
    "no edit can be lost" are not the same statement.

      * The giveaway detail view is swapped in by its parent, so "back"
        is a <button> the guard never sees. Pressing it with an unsaved
        edit dropped it silently.
      * The ticket category editor is a modal. Cancel and the X threw
        away everything typed into it, and a modal has nowhere to put a
        sticky bar -- so that one asks with a confirm() instead.
    """
    print("\nLeaving by button")

    detail = read(os.path.join(DASH, "components/dashboard/giveaway-detail.tsx"))
    check("the giveaway view has a save bar",
          "<StickySaveBar" in detail and 'id="giveaway-save-bar"' in detail)
    check("its back button goes through the guard",
          "const leave = () => {" in detail and "guard.refuse();" in detail)
    check("and no back button calls onBack directly any more",
          "onClick={onBack}" not in detail,
          "a raw onBack drops the edit without asking")

    tickets = read(os.path.join(DASH, "components/dashboard/ticket-panels.tsx"))
    check("the ticket dialog has a close guard",
          "const closeEditor = () => {" in tickets)
    check("cancel and the X both use it",
          tickets.count("onClick={closeEditor}") == 2,
          str(tickets.count("onClick={closeEditor}")))
    check("nothing closes the dialog behind its back",
          tickets.count("onClick={() => setEditing(null)}") == 0,
          "a raw setEditing(null) skips the confirm")
    check("the dialog records what it was opened with",
          "setEditingBase(JSON.stringify(next.cat))" in tickets)
    # Only the two real openers may reset the baseline. A field edit
    # that resets it makes "did anything change?" permanently false --
    # which is exactly what a careless search-and-replace did here once.
    check("only the two real openers reset the baseline",
          tickets.count("openEditor({") == 2,
          str(tickets.count("openEditor({")))
    check("field edits inside the dialog do not reset it",
          "openEditor({ ...editing" not in tickets)


def test_no_tab_was_missed():
    """
    Every tab that keeps an edit in local state needs a bar somewhere.

    The list above is the exception list, and it has to stay honest:
    an entry for a tab that no longer exists means the list is stale.
    """
    print("\nCoverage")

    pages = os.path.join(DASH, "app/dashboard/guild/[guildId]")
    tabs = sorted(
        entry for entry in os.listdir(pages)
        if os.path.isdir(os.path.join(pages, entry))
    )

    stale = [name for name in NO_DRAFT if name not in tabs]
    check("the exception list has no entry for a tab that is gone",
          not stale, str(stale))

    unknown = [t for t in tabs if t not in NO_DRAFT]
    check("every tab is either covered or listed as needing no bar",
          not unknown, str(unknown))


def test_old_bars_are_gone():
    """
    The near-identical local copies each panel used to carry.

    Three of them existed with slightly different wording and none of
    them stopped a navigation. Leaving one behind means that tab quietly
    keeps the old behaviour.
    """
    print("\nNo leftovers")

    folder = os.path.join(DASH, "components/dashboard")
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".tsx") or entry == "save-bar.tsx":
            continue
        src = read(os.path.join(folder, entry))
        check(f"{entry}: no local SaveBar definition",
              "function SaveBar(" not in src
              and "function StickySaveBar(" not in src)
        check(f"{entry}: no local unsaved guard",
              "function useUnsavedGuard(" not in src)


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_shared_module()
    test_every_panel()
    test_admin_area()
    test_buttons_that_leave()
    test_no_tab_was_missed()
    test_old_bars_are_gone()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
