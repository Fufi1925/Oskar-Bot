#!/usr/bin/env python3
"""
Maintenance mode: WARTUNG=true puts the whole site behind a notice.

The behaviour is proven end to end against a running server by
repro/wartung_live.py, which needs a build and a spare port. This file
is the cheap version that runs in the suite: it pins the decisions that
are easy to undo by accident and expensive to get wrong.

The one that matters most: the notice must answer 200. start.sh waits
for `curl /` to succeed before it starts the bot, so a 503 there aborts
the container -- and takes down the Discord bot, which is the one thing
the notice promises is still running.

Run:  python3 tests/test_wartung.py
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


def read(*parts):
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Drop comments, so a note about a mistake is not read as the code."""
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def test_files_exist():
    print("\nThe pieces")
    for label, parts in (
        ("the helper", ("lib", "maintenance.ts")),
        ("the notice page", ("app", "wartung", "page.tsx")),
        ("the bypass page", ("app", "526etrzeqwgoqfu32qzi", "page.tsx")),
        ("the middleware", ("middleware.ts",)),
    ):
        check(f"{label} exists", bool(read(*parts)), os.path.join(*parts))


def test_switch():
    print("\nThe switch")
    lib = strip_comments(read("lib", "maintenance.ts"))

    check("it reads WARTUNG", 'process.env.WARTUNG' in lib)
    # NEXT_PUBLIC_* is baked in at build time, so flipping the Railway
    # variable afterwards would change nothing at all.
    check("it is not a NEXT_PUBLIC name",
          "NEXT_PUBLIC_WARTUNG" not in lib,
          "the value would be frozen into the bundle at build time")
    # Off must be the default: a typo in the variable name should leave
    # the site working, not take it down.
    check("anything unrecognised means off",
          'raw === "true"' in lib,
          "an unexpected value must not switch maintenance on")
    for spelling in ('"1"', '"yes"', '"ja"', '"on"'):
        check(f"{spelling} also counts as on", spelling in lib)


def test_notice_is_200():
    print("\nThe notice answers 200")
    middleware = strip_comments(read("middleware.ts"))

    check("pages are rewritten, not redirected",
          "NextResponse.rewrite" in middleware,
          "a redirect would lose the path the visitor asked for")
    # This is the one that takes the bot down if it is wrong.
    rewrite_line = next(
        (line for line in middleware.split("\n") if "rewrite" in line), "")
    check("the rewrite carries no status override",
          "503" not in rewrite_line,
          "start.sh aborts the container on a non-200 for /")

    page = read("app", "wartung", "page.tsx")
    check("the notice is rendered dynamically",
          'dynamic = "force-dynamic"' in page,
          "a statically rendered page could be cached from build time")


def test_wording():
    print("\nWhat it says")
    page = read("app", "wartung", "page.tsx")
    for phrase in ("Wartung", "0 Uhr", "Sicherheitslücke", "Fufi"):
        check(f"it mentions {phrase!r}", phrase in page)
    # The point of the whole notice.
    check("it says the bot still works",
          "Discord-Bot läuft normal" in page,
          "people will assume the bot is down too")


def test_order_and_scope():
    print("\nMiddleware order and scope")
    middleware = strip_comments(read("middleware.ts"))

    # withAuth sends anonymous visitors to Discord to sign in. Running
    # it before the maintenance check would do that during an outage.
    gate = middleware.index("maintenanceGate(request)")
    auth = middleware.index("authGate")
    first_call = middleware.index("const halted")
    check("maintenance is checked before auth",
          first_call < middleware.index("needsAuth(request.nextUrl.pathname)"),
          "visitors would be bounced to the sign-in page mid-outage")

    # It has to cover every path, not just /dashboard.
    matcher = middleware.split("matcher:")[1] if "matcher:" in middleware else ""
    check("the matcher covers everything",
          "(?!" in matcher,
          "maintenance would only apply to some paths")
    check("Next's own assets are excluded",
          "_next/static" in matcher,
          "the notice would render without styling")

    # The gate itself must also skip them: the matcher exempts
    # /_next/static, but not /_next/data, so without this the notice
    # would be served in place of Next's own payloads.
    gate_body = middleware.split("function maintenanceGate")[1]
    gate_body = gate_body.split("\nconst API_BASE_URL")[0]
    check("the gate skips Next's own paths",
          '"/_next/"' in gate_body,
          "the notice would replace Next's assets and lose its styling")

    # API callers must get JSON; an HTML page confuses the client.
    # Checked inside the gate, and behind a real condition -- looking
    # for the call anywhere in the file passed with the branch disabled.
    api_branch = re.search(
        r'if \(pathname\.startsWith\("/api/"\)\) \{\s*return NextResponse\.json',
        gate_body)
    check("API paths get JSON", api_branch is not None,
          "the JSON branch is present but unreachable")
    check("and a 503", "status: 503" in gate_body)


def test_bypass():
    print("\nThe bypass")
    lib = strip_comments(read("lib", "maintenance.ts"))
    middleware = strip_comments(read("middleware.ts"))
    page = read("app", "526etrzeqwgoqfu32qzi", "page.tsx")

    check("the secret path is defined", "526etrzeqwgoqfu32qzi" in lib)

    # Not just "the name appears": the gate has to actually return early
    # for it, or maintenance locks everyone out including whoever knows
    # the password.
    gate_body = middleware.split("function maintenanceGate")[1]
    gate_body = gate_body.split("\nconst API_BASE_URL")[0]
    bypass_branch = re.search(
        r"if \(\s*pathname === BYPASS_PATH.*?\)\s*\{\s*return null;",
        gate_body, re.S)
    check("the middleware lets it through", bypass_branch is not None,
          "there would be no way back into the site")

    check("the password has a default", "fufi67" in lib)
    check("it can be overridden", "WARTUNG_PASSWORT" in lib)

    # The cookie must not be the password itself -- a cookie is readable
    # by anything with access to the browser. Checking that the function
    # body derives a value and never returns the password directly;
    # looking for "hash" anywhere passed with `return bypassPassword()`
    # inserted above it.
    token_fn = lib.split("export function bypassToken")[1]
    token_fn = token_fn.split("\n}")[0]
    check("the cookie stores a derived value, not the password",
          "return bypassPassword()" not in token_fn and "hash" in token_fn,
          "the password would sit in the browser in clear text")
    check("the middleware compares against that token",
          "bypassToken()" in middleware)

    # The comparison happens in a server action, so the password never
    # reaches the browser bundle.
    check("the password is checked on the server",
          '"use server"' in page,
          "the password would be shipped to every visitor")
    check("the cookie is httpOnly", "httpOnly: true" in page)


def main():
    if not os.path.isdir(DASH):
        print(f"FAIL: dashboard not found at {DASH}")
        return 1

    test_files_exist()
    test_switch()
    test_notice_is_200()
    test_wording()
    test_order_and_scope()
    test_bypass()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
