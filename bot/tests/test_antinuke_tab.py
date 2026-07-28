#!/usr/bin/env python3
"""
The anti-nuke tab.

Three faults, each reproduced before it was fixed:

  * **Four modules that do not exist.** The tab listed `anti_ban_kick`,
    `anti_server_edit`, `anti_role_modifier` and `anti_channel_nukes`,
    each with a green "Protected" badge. Not one of those ids appears
    anywhere in the bot. Meanwhile the seventeen listeners that do exist
    -- webhooks, integrations, pruning, @everyone, bot adds and the rest
    -- were not mentioned at all.

  * **"Add to whitelist" was a full bypass.** The table has one boolean
    column per action and each module reads only its own. The dashboard
    inserted every column as True, so one click let that account do all
    seventeen things unchecked. The chat command defaults them to False
    and then asks which ones to grant.

  * **A silent no-op on a fresh deploy.** The insert only ran when
    `whitelisted_users` already existed, and the table is created by a
    cog at its own pace. Adding somebody before that returned success
    and wrote nothing -- which on Railway, where the database is empty
    after every deploy, is the normal case.

Run:  python3 tests/test_antinuke_tab.py
"""

import asyncio
import os
import re
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import aiosqlite  # noqa: E402

GUILD = 5501
ALICE = 111111111111111111
BOB = 222222222222222222

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


# ══════════════════════════════════════════════════════════════════════
#  Fakes
# ══════════════════════════════════════════════════════════════════════


class Perms:
    def __init__(self, **kw):
        for key in ("ban_members", "view_audit_log", "administrator"):
            setattr(self, key, kw.get(key, True))


class Role:
    def __init__(self, name, position, admin=False):
        self.name = name
        self.position = position
        self.permissions = Perms(administrator=admin)


class Member:
    def __init__(self, uid, name="Alice", bot=False, top=10):
        self.id = uid
        self.display_name = name
        self.display_avatar = type("A", (), {"url": "https://cdn/x.png"})()
        self.bot = bot
        self.guild_permissions = Perms()
        self.top_role = Role("Bot", top)


class Guild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test"
        self.me = Member(1, "University Bot", top=10)
        self.roles = [Role("@everyone", 0)]
        self._members = {}

    def get_member(self, uid):
        return self._members.get(int(uid))


# ══════════════════════════════════════════════════════════════════════
#  The module list has to match the cogs on disk
# ══════════════════════════════════════════════════════════════════════


def test_modules_are_real():
    """
    Every action in the tab must map to a cog that exists, and every cog
    must be reachable from the tab.

    This is the reported bug in test form: four ids in the dashboard
    matched nothing, and ten kinds of protection were invisible.
    """
    print("\nModules")

    from api.routes import antinuke

    folder = os.path.join(BOT, "cogs", "antinuke")
    files = sorted(f for f in os.listdir(folder) if f.endswith(".py"))

    # Class name and whitelist column, read straight out of each cog.
    on_disk: dict[str, str] = {}
    for name in files:
        src = open(os.path.join(folder, name)).read()
        cls = re.search(r"^class ([A-Za-z_]+)\(commands\.Cog", src, re.M)
        column = re.search(r"SELECT ([a-z_]+) FROM whitelisted_users", src)
        if cls and column:
            on_disk[cls.group(1)] = column.group(1)

    check("all seventeen anti-nuke cogs were found", len(on_disk) == 17,
          f"{len(on_disk)}: {sorted(on_disk)}")

    listed = {
        name: key
        for key, spec in antinuke.ACTIONS.items()
        for name in spec["cogs"]
    }

    missing = set(on_disk) - set(listed)
    check("no cog is missing from the tab", not missing, str(sorted(missing)))

    invented = set(listed) - set(on_disk)
    check("the tab invents no module", not invented, str(sorted(invented)))

    # The four ids the old dashboard used, named so a regression is loud.
    for fake in ("anti_ban_kick", "anti_server_edit", "anti_role_modifier",
                 "anti_channel_nukes"):
        check(f"the made-up id {fake} is gone",
              fake not in antinuke.ACTIONS and fake not in listed)

    # Each cog must be filed under the column it actually reads,
    # otherwise ticking "Bannen" in the tab writes a column AntiBan
    # never looks at.
    for cls, column in sorted(on_disk.items()):
        check(f"{cls} is filed under the column it reads ({column})",
              listed.get(cls) == column, f"listed as {listed.get(cls)}")

    for key in antinuke.ACTIONS:
        check(f"{key} is a real column of the table", key in antinuke.COLUMNS)

    # The table's own definition, from the cog that creates it.
    src = open(os.path.join(BOT, "cogs", "commands", "anti_wl.py")).read()
    body = re.search(
        r"CREATE TABLE IF NOT EXISTS whitelisted_users \((.*?)\)\s*\n\s*'''",
        src, re.S,
    )
    if body:
        declared = set(re.findall(r"^\s+([a-z_]+) BOOLEAN", body.group(1), re.M))
        check("every column the tab writes exists in the table",
              set(antinuke.COLUMNS) >= declared and declared <= set(antinuke.COLUMNS),
              str(declared ^ set(antinuke.COLUMNS)))


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


async def test_api():
    print("\nAPI")

    import api.dependencies as dep
    from api.routes import antinuke
    from api.server import create_app
    from fastapi.testclient import TestClient

    guild = Guild()
    guild._members[ALICE] = Member(ALICE, "Alice")
    guild._members[BOB] = Member(BOB, "MusikBot", bot=True)

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            # Pretend every anti-nuke cog is loaded.
            return object() if name.startswith("Anti") else None

        def add_view(self, *a, **k):
            pass

    dep.set_bot(ApiBot())
    client = TestClient(create_app())
    base = f"/api/v1/antinuke/{GUILD}"

    if os.path.exists(antinuke.DB_PATH):
        os.remove(antinuke.DB_PATH)

    # ── Fresh deploy: no tables at all ───────────────────────────
    # The old handler returned success here and wrote nothing.
    data = client.get(base).json()
    check("a database with no tables still answers", "actions" in data,
          str(data)[:120])
    check("anti-nuke reads as off", data["status"] is False)
    check("the whitelist is empty", data["whitelist"] == [])
    check("all fourteen action groups are offered",
          len(data["actions"]) == len(antinuke.ACTIONS), str(len(data["actions"])))
    check("and they cover all seventeen modules", data["module_count"] == 17,
          str(data["module_count"]))
    check("being off is reported as a warning",
          any("ausgeschaltet" in w for w in data["warnings"]), str(data["warnings"]))

    r = client.put(
        f"{base}/whitelist/{ALICE}", json={"actions": {"ban": True}}
    )
    check("a whitelist entry can be added before any cog created the table",
          r.status_code == 200, r.text[:160])

    data = client.get(base).json()
    check("and it is actually there", len(data["whitelist"]) == 1,
          str(data["whitelist"]))

    # ── Per-action, not all-or-nothing ───────────────────────────
    entry = data["whitelist"][0]
    check("only the action asked for is allowed",
          entry["actions"]["ban"] is True
          and sum(entry["actions"].values()) == 1,
          str(entry["actions"]))
    check("the user id is a string, not a rounded number",
          isinstance(entry["id"], str) and entry["id"] == str(ALICE),
          str(entry["id"]))
    check("the name is resolved", entry["name"] == "Alice", str(entry["name"]))
    check("the avatar comes along", entry["avatar"] is not None)

    # Straight from the database: the columns nobody asked for must be
    # false. The old endpoint set all of them.
    async with aiosqlite.connect(antinuke.DB_PATH) as db:
        async with db.execute(
            "SELECT kick, chdl, mngweb FROM whitelisted_users "
            "WHERE guild_id = ? AND user_id = ?", (GUILD, ALICE)
        ) as cursor:
            row = await cursor.fetchone()
    check("every other column stayed false in the database",
          row is not None and not any(row), str(row))

    # ── Editing an entry ─────────────────────────────────────────
    client.put(
        f"{base}/whitelist/{ALICE}",
        json={"actions": {"chdl": True, "chcr": True}},
    )
    data = client.get(base).json()
    entry = next(e for e in data["whitelist"] if e["id"] == str(ALICE))
    check("an edit replaces the old set rather than adding to it",
          entry["actions"]["ban"] is False
          and entry["actions"]["chdl"] is True
          and entry["actions"]["chcr"] is True,
          str(entry["actions"]))

    client.put(f"{base}/whitelist/{ALICE}", json={"actions": {}})
    data = client.get(base).json()
    entry = next(e for e in data["whitelist"] if e["id"] == str(ALICE))
    check("an entry can be emptied without deleting it",
          not any(entry["actions"].values()), str(entry["actions"]))

    # ── A full bypass is possible but reported ───────────────────
    everything = {key: True for key in antinuke.ACTIONS}
    client.put(f"{base}/whitelist/{BOB}", json={"actions": everything})
    client.patch(base, json={"status": True})
    data = client.get(base).json()
    check("a full bypass is called out in the warnings",
          any("dürfen alles" in w for w in data["warnings"]),
          str(data["warnings"]))
    check("and the fullest bypass is listed first",
          data["whitelist"][0]["id"] == str(BOB),
          str([e["id"] for e in data["whitelist"]]))
    check("a bot is marked as one",
          next(e for e in data["whitelist"] if e["id"] == str(BOB))["bot"] is True)

    # ── Rubbish input ────────────────────────────────────────────
    r = client.put(f"{base}/whitelist/{ALICE}",
                   json={"actions": {"anti_ban_kick": True}})
    check("one of the old invented ids is refused", r.status_code == 400,
          str(r.status_code))
    r = client.put(f"{base}/whitelist/{ALICE}", json={"actions": "all"})
    check("actions that are not an object are refused", r.status_code == 400,
          str(r.status_code))
    r = client.patch(base, json={})
    check("a patch with no status is refused", r.status_code == 400,
          str(r.status_code))

    # ── Delete ───────────────────────────────────────────────────
    r = client.delete(f"{base}/whitelist/{ALICE}")
    check("an entry can be removed", r.status_code == 200, r.text[:120])
    data = client.get(base).json()
    check("and is then gone",
          all(e["id"] != str(ALICE) for e in data["whitelist"]),
          str([e["id"] for e in data["whitelist"]]))
    r = client.delete(f"{base}/whitelist/{ALICE}")
    check("removing it twice says so instead of pretending",
          r.status_code == 404, str(r.status_code))

    # ── The switch ───────────────────────────────────────────────
    client.patch(base, json={"status": False})
    check("it can be switched off", client.get(base).json()["status"] is False)
    client.patch(base, json={"status": True})
    check("and on again", client.get(base).json()["status"] is True)

    # ── Warnings that name the real obstacle ─────────────────────
    guild.me.guild_permissions = Perms(ban_members=False)
    warns = client.get(base).json()["warnings"]
    check("a missing ban permission is called out",
          any("bannen" in w for w in warns), str(warns))

    guild.me.guild_permissions = Perms(view_audit_log=False)
    warns = client.get(base).json()["warnings"]
    check("a missing audit-log permission is called out",
          any("Audit-Log" in w for w in warns), str(warns))
    guild.me.guild_permissions = Perms()

    guild.roles.append(Role("Über-Admin", 99, admin=True))
    warns = client.get(base).json()["warnings"]
    check("an admin role above the bot is called out",
          any("Über-Admin" in w for w in warns), str(warns))
    guild.roles.pop()

    # ── A module that failed to load protects nothing ────────────
    class HalfLoadedBot(ApiBot):
        def get_cog(self, name):
            if name == "AntiChannelDelete":
                return None
            return object() if name.startswith("Anti") else None

    dep.set_bot(HalfLoadedBot())
    data = client.get(base).json()
    chdl = next(a for a in data["actions"] if a["key"] == "chdl")
    check("an unloaded module is reported as not loaded",
          chdl["loaded"] is False, str(chdl))
    others = [a for a in data["actions"] if a["key"] != "chdl"]
    check("the loaded ones still say loaded", all(a["loaded"] for a in others))
    dep.set_bot(ApiBot())

    # ── Unknown guild ────────────────────────────────────────────
    r = client.get("/api/v1/antinuke/999999")
    check("an unknown guild still answers", r.status_code == 200,
          str(r.status_code))
    r = client.patch("/api/v1/antinuke/999999", json={"status": True})
    check("but writing to it is refused", r.status_code == 404,
          str(r.status_code))


async def run():
    test_modules_are_real()
    await test_api()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
