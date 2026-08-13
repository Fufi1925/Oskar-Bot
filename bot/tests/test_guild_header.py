#!/usr/bin/env python3
"""
The header above the guild tabs.

Four things in it were decoration rather than information, each
confirmed by reading the code before it was changed:

  * **"Aktualisieren" refreshed nothing.** It was a <Link> to the route
    you were already on. The layout is `revalidate = 0`, so there was no
    cache to bust and Next had nothing to do -- clicking it looked like
    an action and was not one. It is a button calling router.refresh()
    now, which actually refetches the server components.

  * **"Server Settings" was a duplicate.** It linked to the Einstellungen
    tab, which sits in the tab bar directly underneath it.

  * **The green dot always said "Active".** It was hardcoded markup with
    `title="Active"` and an animate-pulse, shown identically whether the
    bot was connected, lagging or offline -- which is precisely when
    somebody looks at it. It now reads the real gateway latency.

  * **Everyone was called the server owner.** "Serverinhaber-Dashboard"
    was static text, shown to team members and global admins too. The
    header compares the signed-in user against the guild's owner_id.

The header itself is a React component, so this checks the source: the
old markup must be gone and the new wiring present. The half that can
be tested for real -- that the API supplies owner_id and a latency the
dot can be derived from -- is exercised against the running app.

Run:  python3 tests/test_guild_header.py
"""

import os
import re
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

DASH = os.path.join(os.path.dirname(BOT), "dashboard")

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

GUILD = 1520714989860814992      # the id from the reported screenshot
OWNER = 111111111111111111
OTHER = 222222222222222222

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
    """Drop /* */ and // comments so a checked-for string in an
    explanatory comment cannot pass or fail a check about the code."""
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


# ══════════════════════════════════════════════════════════════════════
#  The component
# ══════════════════════════════════════════════════════════════════════


def test_header_component():
    print("\nHeader component")

    path = os.path.join(DASH, "components/dashboard/guild-header.tsx")
    check("the header is its own component now", os.path.exists(path), path)
    if not os.path.exists(path):
        return
    src = read(path)

    # Strip comments first. The doc comment at the top of the file
    # quotes the old markup to explain what it replaced, and matching
    # that would fail the check on the very fix it describes -- which is
    # exactly what happened the first time this test was run.
    code = strip_comments(src)

    # Refresh has to do something. Checked against the stripped source:
    # the doc comment names router.refresh() to explain the fix, and
    # matching that passed even after the real call was deleted.
    check("refresh calls router.refresh()", "router.refresh()" in code,
          "a <Link> to the same route does nothing on a revalidate=0 page")
    check("refresh is a button, not a link",
          "<Link" not in code,
          "a Link to the current route is a no-op")
    check("refresh re-checks the bot status too", "await ping();" in code)

    # The dot has to be derived from something.
    check("the status dot is computed", "function health(latency" in src)
    for label in ("Online", "Träge", "Offline", "Unbekannt"):
        check(f"the dot can read {label!r}", f'"{label}"' in src)
    check("the dot no longer hardcodes Active",
          'title="Active"' not in src and "bg-emerald-500 text-white p-2" not in src)
    # Der Punkt pulst gar nicht mehr -- auch nicht bei "Online".
    # Eine Dauer-Animation neben dem Servernamen zieht das Auge auf
    # die eine Stelle, an der sich nie etwas aendert. Was zaehlt,
    # bleibt: die Farbe kommt aus der echten Latenz, nicht aus einem
    # festen Gruen.
    check("nothing pulses any more",
          "animate-pulse" not in src,
          "a permanent animation next to the server name is noise")
    check("the dot takes its colour from the measurement",
          "state.tone" in src)
    # A latency of 0 means "no heartbeat yet", not "instant".
    check("zero latency counts as offline, not as perfect",
          "latency <= 0" in src)

    # Ownership has to be a fact, not a label.
    check("the header takes isOwner as a prop", "isOwner," in src)
    check("and says something different for a non-owner",
          "Du verwaltest diesen Server" in src)
    check("the old blanket claim is gone",
          "Serverinhaber-Dashboard" not in code)


def test_layout_wiring():
    print("\nLayout")

    path = os.path.join(DASH, "app/dashboard/guild/[guildId]/layout.tsx")
    src = read(path)

    check("the layout renders the component", "<GuildHeader" in src)
    check("it imports it", "@/components/dashboard/guild-header" in src)
    check("ownership is compared against the signed-in user",
          "String(guild.owner_id) === String(access.userId" in src,
          "a static label calls everyone the owner")

    # The two dead buttons.
    check("the duplicate Server Settings button is gone",
          "Server Settings" not in src,
          "it linked to the tab directly below it")
    check("the no-op refresh link is gone",
          "Refresh" not in src)
    check("the hardcoded green dot is gone from the layout",
          'title="Active"' not in src)


# ══════════════════════════════════════════════════════════════════════
#  The data behind it
# ══════════════════════════════════════════════════════════════════════


class Role:
    def __init__(self, rid):
        self.id = rid


class Channel:
    def __init__(self, cid):
        self.id = cid


class Guild:
    def __init__(self):
        self.id = GUILD
        self.name = "FUSE EH"
        self.icon = None
        self.owner_id = OWNER
        self.member_count = 95
        self.roles = [Role(i) for i in range(69)]
        self.channels = [Channel(i) for i in range(98)]
        self.members = []
        self.approximate_member_count = 95


def test_api():
    """
    The header can only be honest if the API tells it the truth.

    Two fields carry it: owner_id, which decides what the subtitle says,
    and the latency the dot is derived from.
    """
    print("\nAPI")

    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient

    guild = Guild()

    class ApiBot:
        user = type("U", (), {"id": 1, "name": "University Bot",
                              "__str__": lambda s: "University Bot"})()
        guilds = [guild]
        latency = 0.042
        shard_count = 1
        commands = []

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            return None

        def add_view(self, *a, **k):
            pass

    dep.set_bot(ApiBot())
    client = TestClient(create_app())

    data = client.get(f"/api/v1/guilds/{GUILD}").json()
    check("the guild details answer", "owner_id" in data, str(data)[:120])
    check("owner_id comes back as a string",
          isinstance(data.get("owner_id"), str),
          "a 19-digit id as a JSON number is rounded in the browser")
    check("owner_id is the real owner", data["owner_id"] == str(OWNER),
          str(data.get("owner_id")))
    check("the id survives intact", data["id"] == str(GUILD), str(data.get("id")))

    # The counts from the screenshot.
    check("the member count is reported", data["member_count"] == 95,
          str(data.get("member_count")))
    check("the role count is reported", data["role_count"] == 69,
          str(data.get("role_count")))
    check("the channel count is reported", data["channel_count"] == 98,
          str(data.get("channel_count")))

    # The dot needs a latency.
    status = client.get("/api/v1/bot/status").json()
    check("the status endpoint answers", "latency" in status, str(status)[:120])
    check("the latency is a number in milliseconds",
          isinstance(status["latency"], (int, float)) and status["latency"] > 1,
          str(status.get("latency")))
    check("42 ms would read as Online",
          0 < status["latency"] <= 500, str(status["latency"]))

    # Somebody who is not the owner must not be told they are.
    check("a non-owner does not match owner_id",
          data["owner_id"] != str(OTHER))


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_header_component()
    test_layout_wiring()
    test_api()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(main())
