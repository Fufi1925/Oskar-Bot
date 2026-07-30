#!/usr/bin/env python3
"""
The dashboard buttons: welcome DM, help menu, nuke alert.

Three places link to the dashboard, and none of them worked.

  * The **welcome DM** had a website button pointing at
    ``https://.vercel.app`` -- a URL with no host. Discord accepts it
    and the button goes nowhere, which is presumably why it was
    commented out rather than fixed.
  * The **nuke alert** read ``DASHBOARD_URL`` and skipped its button
    when empty. That variable is not set on the live deployment, so the
    button never appeared -- silently, on the one alert where reaching
    the settings quickly matters most.
  * The **help menu** had no dashboard button at all.

So they now share ``utils.links``, which falls back through the
variables that *are* set in production. ``NEXTAUTH_URL`` is the reliable
one: the dashboard cannot log anybody in without it, so if the site
works, that value is correct.

The rule throughout: no address means no button. A dead link is worse
than a missing one.

Run:  python3 tests/test_dashboard_links.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

GUILD = 1520714989860814992
LIVE = "https://universtiy-bot.up.railway.app"

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def clear_env():
    for name in ("DASHBOARD_URL", "NEXTAUTH_URL", "WEBSITE_URL",
                 "CORS_ORIGINS", "SUPPORT_INVITE_URL"):
        os.environ.pop(name, None)


def buttons_in(view) -> list:
    """Every button in a view, however deeply nested."""
    import discord

    found = []

    def walk(item):
        if isinstance(item, discord.ui.Button):
            found.append(item)
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(item, "children", None) or []:
            walk(child)

    for child in view.children:
        walk(child)
    return found


# ══════════════════════════════════════════════════════════════════════
#  Finding the address
# ══════════════════════════════════════════════════════════════════════


def test_url_resolution():
    print("\nWorking out where the dashboard is")

    from utils import links

    clear_env()
    check("nothing configured means no url", links.dashboard_url() == "",
          links.dashboard_url())

    clear_env()
    os.environ["NEXTAUTH_URL"] = LIVE
    check("NEXTAUTH_URL is used", links.dashboard_url() == LIVE,
          "this is the one that is actually set in production")

    clear_env()
    os.environ["DASHBOARD_URL"] = "https://explicit.dev/"
    os.environ["NEXTAUTH_URL"] = LIVE
    check("an explicit DASHBOARD_URL wins",
          links.dashboard_url() == "https://explicit.dev",
          links.dashboard_url())
    check("and the trailing slash is dropped",
          not links.dashboard_url().endswith("/"), "")

    clear_env()
    os.environ["CORS_ORIGINS"] = f"{LIVE},https://other.dev"
    check("CORS_ORIGINS is a last resort",
          links.dashboard_url() == LIVE, links.dashboard_url())

    # The exact string that was hard-coded in the welcome DM.
    clear_env()
    os.environ["NEXTAUTH_URL"] = "https://.vercel.app"
    check("a url with no host counts as unset",
          links.dashboard_url() == "",
          "https://.vercel.app was in the code; Discord renders it as a "
          "button that goes nowhere")

    for broken in ("", "   ", "not-a-url", "https://", "http://localhost"):
        clear_env()
        os.environ["NEXTAUTH_URL"] = broken
        result = links.dashboard_url()
        check(f"{broken!r} does not produce a broken link",
              result == "" or "." in result.split("://")[-1],
              repr(result))

    clear_env()
    os.environ["NEXTAUTH_URL"] = LIVE
    check("a guild link points at that guild",
          links.guild_dashboard_url(GUILD) == f"{LIVE}/dashboard/guild/{GUILD}",
          links.guild_dashboard_url(GUILD))
    check("and a tab can be appended",
          links.guild_dashboard_url(GUILD, "antinuke").endswith("/antinuke"),
          links.guild_dashboard_url(GUILD, "antinuke"))
    check("the guild id is not rounded",
          str(GUILD) in links.guild_dashboard_url(GUILD),
          "a snowflake through a float loses its last digits")

    clear_env()
    check("no url means no guild link",
          links.guild_dashboard_url(GUILD) == "",
          "callers use this to decide whether to render the button")


# ══════════════════════════════════════════════════════════════════════
#  The welcome DM
# ══════════════════════════════════════════════════════════════════════


def test_welcome_dm():
    print("\nThe DM after being added")

    import importlib

    clear_env()
    os.environ["NEXTAUTH_URL"] = LIVE

    from cogs.events import auto
    importlib.reload(auto)

    class Guild:
        id = GUILD
        name = "Test"

    text = auto._welcome_text(Guild())
    check("it mentions the dashboard", "Dashboard" in text, text[:120])
    check("and still explains the prefix", "`>`" in text, text[:120])
    check("and still points at help", ">help" in text, text[:120])

    # With no dashboard configured the line has to go, or the DM tells
    # people to open something it cannot link to.
    clear_env()
    importlib.reload(auto)
    text = auto._welcome_text(Guild())
    check("no dashboard means no dashboard line",
          "Dashboard" not in text, text[:160])
    check("but the rest of the message survives",
          "`>`" in text and ">help" in text, text[:160])

    source = open(os.path.join(BOT, "cogs/events/auto.py"),
                  encoding="utf-8").read()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    check("the broken vercel url is gone",
          "https://.vercel.app" not in code,
          "it was a url with no host, rendering a dead button")
    check("the button is built from utils.links",
          "links.guild_dashboard_url(guild.id)" in code,
          "hard-coding it is what produced the dead link")
    check("and only added when there is an address",
          "if dashboard:" in code,
          "no address must mean no button")
    check("the support button is still there",
          "label='Support'" in code or 'label="Support"' in code, "")


# ══════════════════════════════════════════════════════════════════════
#  The help menu
# ══════════════════════════════════════════════════════════════════════


def build_help_view():
    import discord
    from utils import help as vhelp

    class Author:
        display_name = "Lena"
        id = 42

    class Guild:
        id = GUILD

    class Ctx:
        author = Author()
        guild = Guild()
        prefix = ">"
        bot = None

    embed = discord.Embed(description="Test")
    embed.add_field(name="A", value="x")
    return vhelp.View(mapping={}, ctx=Ctx(), homeembed=embed, ui=2)


def test_help_menu():
    print("\nThe help menu")

    import importlib

    import discord
    from utils import help as vhelp

    clear_env()
    os.environ["NEXTAUTH_URL"] = LIVE
    importlib.reload(vhelp)

    view = build_help_view()
    found = buttons_in(view)
    dashboard = [b for b in found if b.label == "Dashboard"]

    check("there is a dashboard button", len(dashboard) == 1,
          str([b.label for b in found]))
    if dashboard:
        check("it links to this server's settings",
              dashboard[0].url == f"{LIVE}/dashboard/guild/{GUILD}",
              dashboard[0].url)
        check("it is a link button, not a callback",
              dashboard[0].style is discord.ButtonStyle.link, "")

    # Discord allows five buttons per row and the navigation uses all
    # five, so a sixth in that row raises before the message is sent.
    rows = []

    def collect(items):
        for item in items:
            if isinstance(item, discord.ui.ActionRow):
                rows.append([
                    c for c in item.children
                    if isinstance(c, discord.ui.Button)
                ])
            collect(getattr(item, "children", None) or [])

    collect(view.children)
    oversized = [r for r in rows if len(r) > 5]
    check("no action row holds more than five buttons",
          not oversized,
          f"{[len(r) for r in rows]} -- a sixth raises 'maximum number "
          "of children exceeded'")
    check("the dashboard button is on its own row",
          any(len(r) == 1 and r[0].label == "Dashboard" for r in rows),
          str([[b.label for b in r] for r in rows]))

    # Total components. A LayoutView is capped at 40.
    payload = view.to_components()

    def count(items):
        total = 0
        for item in items:
            total += 1
            total += count(item.get("components", []) or [])
            if item.get("accessory"):
                total += 1
        return total

    used = count(payload)
    check("the message stays under Discord's component limit",
          used <= 40, f"{used} of 40")

    # And without a dashboard, no button.
    clear_env()
    importlib.reload(vhelp)
    view = build_help_view()
    labels = [b.label for b in buttons_in(view)]
    check("no dashboard configured means no button",
          "Dashboard" not in labels, str(labels))
    check("but the navigation still works",
          len(buttons_in(view)) == 5, str(labels))


# ══════════════════════════════════════════════════════════════════════
#  The nuke alert
# ══════════════════════════════════════════════════════════════════════


def test_nuke_alert_button():
    """
    The alert button that never appeared.

    It required DASHBOARD_URL, which is not set on the live deployment.
    Nothing reported that -- the button was simply absent from every
    alert ever sent.
    """
    print("\nThe anti-nuke alert")

    source = open(os.path.join(BOT, "utils/nuke_alert.py"),
                  encoding="utf-8").read()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )

    check("it no longer depends on DASHBOARD_URL alone",
          'os.getenv("DASHBOARD_URL", "")' not in code,
          "that variable is not set in production, so the button was "
          "never rendered")
    check("it uses the shared resolver",
          "guild_dashboard_url" in code, "")
    check("and links straight to the antinuke tab",
          '"antinuke"' in code, "")

    # Exercise it: with NEXTAUTH_URL set the link must now resolve.
    clear_env()
    os.environ["NEXTAUTH_URL"] = LIVE
    from utils.links import guild_dashboard_url

    url = guild_dashboard_url(GUILD, "antinuke")
    check("the alert can now build a working link",
          url == f"{LIVE}/dashboard/guild/{GUILD}/antinuke", url)


def main():
    try:
        test_url_resolution()
        test_welcome_dm()
        test_help_menu()
        test_nuke_alert_button()
    finally:
        clear_env()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
