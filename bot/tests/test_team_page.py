#!/usr/bin/env python3
"""
The public team page and the profile endpoint behind it.

Two separate concerns meet here.

**No source-code links anywhere on the site.** The repository is
private and stays private. A link to it is not merely broken for a
visitor -- it advertises that the project is on GitHub under a
particular account and invites them to go looking. The site also used
to call itself "Open-source" in the footer and claim an MIT licence in
the imprint, both of which were simply untrue. A licence claim in an
imprint is not decoration; it tells people what they may legally do
with the code.

**Real avatars need the bot.** A Discord avatar URL cannot be built
from a user id: the CDN path carries the avatar hash, so a guessed URL
404s -- verified, not assumed. Only the bot can look the hash up, which
is why /bot/profiles exists. It is reachable without a session, so it
is deliberately narrow: capped, digits only, and it returns nothing but
a display name and an avatar URL.

Run:  python3 tests/test_team_page.py
"""

import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASHBOARD = os.path.join(ROOT, "dashboard")

sys.path.insert(0, BOT)

FUFI = "1303627964734246944"
VEXO = "1033826242270609449"

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts) -> str:
    path = os.path.join(*parts)
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read()


def tsx_files() -> list[str]:
    found = []
    for base, dirs, names in os.walk(DASHBOARD):
        dirs[:] = [
            d for d in dirs
            if d not in {"node_modules", ".next", ".render-audit", "dist"}
        ]
        for name in names:
            if name.endswith((".tsx", ".ts")):
                found.append(os.path.join(base, name))
    return found


def strip_comments(source: str) -> str:
    """
    Drop comments before searching.

    The file headers in this project contain a github.com line in an
    ASCII box, and every page carries one. Searching the raw text finds
    those and says nothing about what a visitor can click.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.S)
    source = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("*", "//"))
    )
    return source


# ══════════════════════════════════════════════════════════════════════
#  Nothing points at the source
# ══════════════════════════════════════════════════════════════════════


def test_no_repository_links():
    print("\nNo links to the source")

    offenders = []
    for path in tsx_files():
        body = strip_comments(read(path))
        # Only what a visitor can actually click.
        for match in re.finditer(r'href\s*=\s*[{"\']?[^"\'}\s]*github[^"\'}\s]*', body, re.I):
            offenders.append(f"{os.path.relpath(path, ROOT)}: {match.group(0)[:70]}")

    check("no page links to GitHub", not offenders,
          "; ".join(offenders[:3]))

    # The specific repository, in any form -- a bare URL in text is just
    # as much of a pointer as a link.
    named = []
    for path in tsx_files():
        body = strip_comments(read(path))
        if "Fufi1925/Oskar-Bot" in body or "github.com/Fufi1925" in body:
            named.append(os.path.relpath(path, ROOT))
    check("the repository is not named anywhere in the site",
          not named, str(named))


def test_no_open_source_claims():
    print("\nThe site does not claim to be open source")

    landing = strip_comments(read(DASHBOARD, "app/page.tsx"))
    check("the footer no longer says 'Open-source'",
          "open-source" not in landing.lower(), "")

    team = strip_comments(read(DASHBOARD, "app/team/page.tsx"))
    check("the team page no longer says 'quelloffen'",
          "quelloffen" not in team.lower(), "")
    check("and does not invite pull requests",
          "pull request" not in team.lower(),
          "there is nowhere to send one")

    imprint = strip_comments(read(DASHBOARD, "app/imprint/page.tsx"))
    check("the imprint no longer claims an MIT licence",
          "MIT-Lizenz" not in imprint,
          "an imprint tells people what they may legally do with the "
          "code; claiming MIT when it is closed is wrong in the one "
          "place that has to be right")
    check("it states the source is closed instead",
          "nicht öffentlich" in imprint and "Alle Rechte vorbehalten" in imprint,
          imprint[-300:] if imprint else "imprint not found")


# ══════════════════════════════════════════════════════════════════════
#  The team page itself
# ══════════════════════════════════════════════════════════════════════


def test_team_members():
    print("\nThe team page")

    team = read(DASHBOARD, "app/team/page.tsx")
    check("the page exists", bool(team))
    if not team:
        return

    check("Fufi is listed", FUFI in team, "id missing")
    check("Vexo is listed", VEXO in team, "id missing")
    check("Vexo is named as a developer",
          re.search(r'"Vexo"[\s\S]{0,200}Entwickler', team) is not None,
          "he is one, and the page should say so")
    check("and credited with the original idea",
          "Idee" in team, "that was the explicit request")
    check("his role mentions the template bot",
          re.search(r'Vexo[\s\S]{0,200}Template-Bot', team) is not None,
          "that is what he works on")

    check("nobody carries a github field any more",
          "github" not in strip_comments(team).lower(),
          "the repository is private")

    # The avatar path: an <img> from the profile, initials when there is
    # none. A broken image on a public page looks worse than initials.
    #
    # Diese drei stehen seit dem Umbau der Team-Seite in der
    # Kartenkomponente, nicht mehr in page.tsx. Die ANFORDERUNG gilt
    # unveraendert weiter -- deshalb wandert die Pruefung mit, statt
    # gestrichen zu werden. Die Seite reicht die Profile als
    # `liveName`/`avatar` an die Karten durch.
    karten = read(DASHBOARD, "components/team-mitglieder.tsx")

    # Both halves, separately. `avatar:` also appears in the Profil
    # interface further up, so the loose check stayed green with the
    # hand-over deleted -- the cards would have shown initials for ever.
    check("the page passes the fetched avatar on",
          re.search(r"avatar:\s*profile\[person\.id\]\?\.avatar", team)
          is not None,
          "the cards can only render what they are given")
    check("and the fetched name",
          re.search(r"liveName:\s*profile\[person\.id\]\?\.name", team)
          is not None, "")
    # The <img> has to hang off the avatar, not merely exist: the
    # element stayed in the file when the condition was disabled.
    check("real avatars are rendered when available",
          re.search(r"person\.avatar \?", karten) is not None
          and re.search(r"src=\{person\.avatar\}", karten) is not None, "")
    check("with initials as the fallback",
          "initialen(name)" in karten,
          "the bot may be restarting; that must not leave a grey box")
    check("the alt text names the person",
          "Profilbild von" in karten, "")

    check("the page is rendered per request",
          'export const dynamic = "force-dynamic"' in team,
          "the bot is not running while the image builds, so a build-"
          "time fetch would bake in the fallback for ever")

    check("a failed profile lookup does not take the page down",
          "return {};" in team and "catch" in team,
          "a team page is not worth a 500")
    check("and the fetch cannot hang the page",
          "AbortSignal.timeout" in team,
          "an unbounded fetch to a bot that is starting up blocks the "
          "whole render")

    check("the support server is still linked",
          "SUPPORT" in team and "discord" in team.lower(), "")


# ══════════════════════════════════════════════════════════════════════
#  The profile endpoint
# ══════════════════════════════════════════════════════════════════════


class FakeAvatar:
    def __init__(self, url):
        self._url = url

    def replace(self, **kwargs):
        return type("A", (), {"url": self._url})()


class FakeUser:
    def __init__(self, uid, name, global_name=None, avatar=None):
        self.id = uid
        self.name = name
        self.global_name = global_name
        self.display_avatar = FakeAvatar(
            avatar or f"https://cdn.discordapp.com/avatars/{uid}/hash.png"
        )


class FakeBot:
    def __init__(self, known):
        self.known = known
        self.fetched: list[int] = []

    def get_user(self, uid):
        return self.known.get(int(uid))

    async def fetch_user(self, uid):
        self.fetched.append(int(uid))
        raise RuntimeError("unknown user")


async def test_profiles_endpoint():
    print("\nThe profile endpoint")

    from fastapi import HTTPException

    from api.routes import bot as bot_routes

    bot_routes._profile_cache.clear()

    fake = FakeBot({
        int(FUFI): FakeUser(int(FUFI), "fufi0091", global_name="Fufi"),
        int(VEXO): FakeUser(int(VEXO), "vexo"),
    })

    result = await bot_routes.get_profiles(f"{FUFI},{VEXO}", fake)
    profiles = result["profiles"]

    check("both profiles come back", set(profiles) == {FUFI, VEXO},
          str(list(profiles)))
    check("the display name is preferred over the username",
          profiles[FUFI]["name"] == "Fufi", str(profiles[FUFI]))
    check("falling back to the username when there is none",
          profiles[VEXO]["name"] == "vexo", str(profiles[VEXO]))
    # A working avatar URL is .../avatars/<id>/<hash>.png -- two
    # segments after "avatars". Checking only that the last segment
    # differs from the id was too weak: ".../avatars/<id>.png" passed
    # it, and that is exactly the broken form this guards against.
    avatar = profiles[FUFI]["avatar"]
    tail = avatar.split("/avatars/", 1)[-1].split("?")[0]
    check("the avatar url has both an id and a hash segment",
          avatar.count("/avatars/") == 1 and len(tail.split("/")) == 2
          and tail.startswith(f"{FUFI}/"),
          f"{avatar} -- a url built from the id alone 404s, which is "
          "the whole reason this endpoint exists")
    check("and it comes from Discord's object, not from string building",
          "display_avatar" in read(BOT, "api/routes/bot.py"),
          "only discord.py knows the hash")

    # Ids that are not digits must not reach int(). A ValueError here
    # would be a 500 on a public endpoint, so anything other than a
    # clean 400 is a failure -- including a crash.
    for bad in ("abc", "'; DROP TABLE", "12.5", ""):
        try:
            await bot_routes.get_profiles(bad, fake)
            check(f"a non-numeric id is refused ({bad!r})", False, "accepted")
        except HTTPException as err:
            check(f"a non-numeric id is refused ({bad!r})",
                  err.status_code == 400, str(err.status_code))
        except Exception as err:  # noqa: BLE001
            check(f"a non-numeric id is refused ({bad!r})", False,
                  f"crashed with {type(err).__name__}: {err} -- that is a "
                  "500 on a public endpoint")

    # Reachable without a session, so it must not be a bulk lookup tool.
    try:
        await bot_routes.get_profiles(",".join(str(i) for i in range(1, 30)), fake)
        check("a long list of ids is refused", False, "accepted 29 ids")
    except HTTPException as err:
        check("a long list of ids is refused", err.status_code == 400,
              "this endpoint needs no login; an uncapped loop here makes "
              "the bot hammer Discord for anyone who asks")

    # An unknown user is a gap, not an error.
    unknown = await bot_routes.get_profiles("999999999999999999", fake)
    entry = unknown["profiles"]["999999999999999999"]
    check("an unknown id gives an empty profile rather than failing",
          entry["name"] is None and entry["avatar"] is None, str(entry))

    # Only what Discord already shows publicly.
    fields = set(profiles[FUFI])
    check("only id, name and avatar are returned",
          fields == {"id", "name", "avatar"},
          f"{sorted(fields)} -- this endpoint has no session behind it")

    # The cache, so a public page cannot turn into one Discord call per
    # visitor.
    source = read(BOT, "api/routes/bot.py")
    check("results are cached", "_profile_cache" in source)
    check("and the cache expires",
          "_PROFILE_TTL" in source and "> now" in source,
          "a permanently cached name never updates")

    before = len(fake.fetched)
    await bot_routes.get_profiles(FUFI, fake)
    check("a second call does not hit Discord again",
          len(fake.fetched) == before, "")


def main():
    test_no_repository_links()
    test_no_open_source_claims()
    test_team_members()
    asyncio.run(test_profiles_endpoint())

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
