#!/usr/bin/env python3
"""
The logging tab.

Three faults, each reproduced here before it was fixed:

  * **Three of nine categories were unreachable.** The cog logs emoji
    changes, reactions and server updates, but the dashboard listed six
    categories. Those three could only be switched on with a chat
    command, and `/log status` reported them as unconfigured forever.

  * **The ignore lists were read-only.** `ignore_channels`,
    `ignore_roles` and `ignore_users` came back from the API and were
    rendered as two bare numbers. The PATCH schema had no field for
    them at all, so nothing the web sent could ever change one.

  * **A category could claim to be on with no channel.** `_send_log`
    returns early when there is no channel, so the switch said "Active"
    while nothing was ever posted, with no hint why.

Plus what the rewrite adds: the ignore lists keep their order, a
category loses its "on" state when its channel is cleared, and the
warnings name the actual obstacle (no send permission, deleted channel,
channel set but switched off).

Run:  python3 tests/test_logging_tab.py
"""

import asyncio
import os
import re
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

GUILD = 4401
LOGS = 1327995167345819721        # real-length snowflakes throughout
SECOND = 1327995167345819722
TEAM_ROLE = 500000000000000001
BOT_USER = 600000000000000001

BOT = os.path.dirname(HERE)

failures: list[str] = []


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def strip_comments(src: str) -> str:
    """
    Drop comments before searching.

    The cog explains in comments *why* the cache-only reaction events
    were replaced -- and that explanation names them. Searching the raw
    text finds the explanation and reports the fix as the bug.
    """
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(
        line for line in without_block.splitlines()
        if not line.lstrip().startswith("#")
    )


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
        for key in ("view_audit_log", "send_messages", "embed_links"):
            setattr(self, key, kw.get(key, True))


class Channel:
    def __init__(self, cid, name="logs", perms=None):
        self.id = cid
        self.name = name
        self.sent: list = []
        self._perms = perms or Perms()
        self.allow_send = True

    def permissions_for(self, _member):
        return self._perms

    async def send(self, content=None, embed=None, **kwargs):
        if not self.allow_send:
            import discord
            raise discord.Forbidden(
                type("R", (), {"status": 403, "reason": "Forbidden"})(), "nope"
            )
        self.sent.append(embed)
        return type("M", (), {"id": 1})()


class Role:
    def __init__(self, rid, name="Team"):
        self.id = rid
        self.name = name
        self.color = type("C", (), {"value": 0})()


class Member:
    def __init__(self, uid, name="Bot"):
        self.id = uid
        self.display_name = name
        self.display_avatar = type("A", (), {"url": "https://cdn/x.png"})()
        self.guild_permissions = Perms()


class Guild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test"
        self.me = Member(1, "University Bot")
        self._channels = {}
        self._roles = {}
        self._members = {}

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_member(self, uid):
        return self._members.get(int(uid))


class FakeCog:
    """
    Stands in for the Logging cog.

    `_save_log_config` mirrors the real one closely enough for the route:
    it drops channels that are None, coerces the enabled flags to bool,
    and de-duplicates the ignore lists.
    """

    def __init__(self):
        self.config_cache: dict = {}
        self.saves = 0

    async def _save_log_config(
        self, guild_id, log_channels, log_enabled,
        ignore_channels, ignore_roles, ignore_users, auto_delete_duration,
    ):
        self.saves += 1
        self.config_cache[guild_id] = {
            "guild_id": str(guild_id),
            "log_channels": {
                k: v for k, v in log_channels.items()
                if v is not None and isinstance(v, int)
            },
            "log_enabled": {k: bool(v) for k, v in log_enabled.items()},
            "ignore_channels": list(dict.fromkeys(ignore_channels)),
            "ignore_roles": list(dict.fromkeys(ignore_roles)),
            "ignore_users": list(dict.fromkeys(ignore_users)),
            "auto_delete_duration": auto_delete_duration,
        }


# ══════════════════════════════════════════════════════════════════════
#  The bug that started it: the dashboard knew six of nine categories
# ══════════════════════════════════════════════════════════════════════


def test_categories_match_the_cog():
    """
    The route's category list has to be exactly the cog's list.

    Guessing the names has failed here before: a key the cog does not
    know is accepted, stored and then never matched by `_send_log`, so
    the switch is decoration. And a key the cog knows but the route does
    not is simply unreachable from the web.
    """
    print("\nCategory names")

    import ast
    from api.routes import logging_cfg

    src = open(os.path.join(os.path.dirname(HERE), "cogs/commands/logging.py")).read()
    match = re.search(r"^LOG_CATEGORIES = (\[[^\]]*\])", src, re.M)
    check("the cog's list is still where we look for it", match is not None)
    if not match:
        return

    cog_names = ast.literal_eval(match.group(1))
    route_names = list(logging_cfg.CATEGORIES)

    check("the route offers all nine categories", len(route_names) == 9,
          str(len(route_names)))
    check("nothing the cog logs is missing from the tab",
          set(cog_names) <= set(route_names),
          str(set(cog_names) - set(route_names)))
    check("the tab invents no category the cog ignores",
          set(route_names) <= set(cog_names),
          str(set(route_names) - set(cog_names)))

    # This is the reported gap, spelled out.
    for key in ("emoji_events", "reaction_events", "system_events"):
        check(f"{key} is reachable from the dashboard", key in route_names)

    for key, spec in logging_cfg.CATEGORIES.items():
        check(f"{key} has a German label", bool(spec.get("label")))
        check(f"{key} explains itself", len(spec.get("description", "")) > 15)

    # Every category the cog actually passes to _send_log must be listed,
    # otherwise something is logged that cannot be configured.
    used = set(re.findall(r'_send_log\(\s*[^,]+,\s*"([a-z_]+)"', src))
    check("every category used in the code is configurable",
          used <= set(route_names), str(used - set(route_names)))


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


def build_client(cog, guild):
    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            return cog if name == "Logging" else None

        def add_view(self, *a, **k):
            pass

    dep.set_bot(ApiBot())
    return TestClient(create_app())


async def test_api():
    print("\nAPI")

    guild = Guild()
    logs = Channel(LOGS, "logs")
    second = Channel(SECOND, "mod-logs")
    guild._channels[LOGS] = logs
    guild._channels[SECOND] = second
    guild._roles[TEAM_ROLE] = Role(TEAM_ROLE)
    guild._members[BOT_USER] = Member(BOT_USER, "MusikBot")

    cog = FakeCog()
    client = build_client(cog, guild)
    base = f"/api/v1/logging/{GUILD}"

    # ── Fresh server ─────────────────────────────────────────────
    data = client.get(base).json()
    check("a fresh server answers", "categories" in data, str(data)[:120])
    check("all nine categories come back", len(data["categories"]) == 9,
          str(len(data.get("categories", []))))
    check("nothing is on yet", data["active_count"] == 0)
    check("the ignore lists come back empty",
          data["ignore_channels"] == [] and data["ignore_roles"] == []
          and data["ignore_users"] == [])
    check("the guild id is a string, not a rounded number",
          isinstance(data["guild_id"], str))

    def all_ids(node, path="", found=None):
        """
        Every id anywhere in the response has to be a string.

        Checking one field is not enough: the first version of this test
        only looked at `categories[].channel`, and a mutation that turned
        `channel_info.id` back into an int sailed straight through. A
        19-digit int becomes 1327995167345819600 in the browser -- the
        save then points at a channel that does not exist.
        """
        found = [] if found is None else found
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("id", "channel", "guild_id") or key.startswith("ignore_"):
                    if isinstance(value, int) and value > 2 ** 53:
                        found.append(f"{path}.{key}")
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, int) and item > 2 ** 53:
                                found.append(f"{path}.{key}[]")
                all_ids(value, f"{path}.{key}", found)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                all_ids(item, f"{path}[{i}]", found)
        return found

    # ── Switching a category on ──────────────────────────────────
    r = client.patch(base, json={
        "categories": {"message_events": {"enabled": True, "channel": str(LOGS)}}
    })
    check("a category can be switched on", r.status_code == 200, r.text[:160])

    data = client.get(base).json()
    cat = next(c for c in data["categories"] if c["key"] == "message_events")
    check("it comes back on", cat["enabled"] is True)
    check("with its channel", cat["channel"] == str(LOGS), str(cat["channel"]))
    check("the channel id stayed a string", isinstance(cat["channel"], str))
    check("and the channel name is resolved",
          cat["channel_info"]["name"] == "logs", str(cat["channel_info"]))
    check("the counter moved", data["active_count"] == 1)

    check("the cog stored an int, as it expects",
          cog.config_cache[GUILD]["log_channels"]["message_events"] == LOGS,
          str(cog.config_cache[GUILD]["log_channels"]))

    # ── The three categories that used to be unreachable ─────────
    for key in ("emoji_events", "reaction_events", "system_events"):
        r = client.patch(base, json={
            "categories": {key: {"enabled": True, "channel": str(SECOND)}}
        })
        check(f"{key} can be configured from the web", r.status_code == 200,
              r.text[:120])
    data = client.get(base).json()
    check("all four are on now", data["active_count"] == 4,
          str(data["active_count"]))

    # ── Partial writes ───────────────────────────────────────────
    r = client.patch(base, json={
        "categories": {"voice_events": {"enabled": True, "channel": str(LOGS)}}
    })
    data = client.get(base).json()
    cat = next(c for c in data["categories"] if c["key"] == "message_events")
    check("an unrelated category is left alone by a partial write",
          cat["enabled"] is True and cat["channel"] == str(LOGS))

    # ── Clearing a channel switches the category off ─────────────
    client.patch(base, json={"categories": {"voice_events": {"channel": None}}})
    data = client.get(base).json()
    cat = next(c for c in data["categories"] if c["key"] == "voice_events")
    check("clearing the channel clears the channel", cat["channel"] is None)
    check("and turns the category off, because it could not log anyway",
          cat["enabled"] is False)

    # ── Ignore lists, the part that had no way in ────────────────
    r = client.patch(base, json={
        "ignore_channels": [str(SECOND)],
        "ignore_roles": [str(TEAM_ROLE)],
        "ignore_users": [str(BOT_USER)],
    })
    check("the ignore lists accept a write", r.status_code == 200, r.text[:160])

    data = client.get(base).json()
    check("ignored channels come back", data["ignore_channels"] == [str(SECOND)],
          str(data["ignore_channels"]))
    check("ignored roles come back", data["ignore_roles"] == [str(TEAM_ROLE)],
          str(data["ignore_roles"]))
    check("ignored users come back", data["ignore_users"] == [str(BOT_USER)],
          str(data["ignore_users"]))
    check("and they carry names, not just ids",
          data["ignore_roles_info"][0]["name"] == "Team"
          and data["ignore_users_info"][0]["name"] == "MusikBot",
          str(data["ignore_users_info"]))
    check("the avatar comes along so the list is readable",
          data["ignore_users_info"][0]["avatar"] is not None)
    check("the cog got ints for the ignore lists",
          cog.config_cache[GUILD]["ignore_roles"] == [TEAM_ROLE],
          str(cog.config_cache[GUILD]["ignore_roles"]))

    numeric = all_ids(data)
    check("no id anywhere in the response is a raw 64-bit number",
          not numeric, str(numeric))

    # Order is kept: a set() here would shuffle the list on every save.
    # Both directions are checked on purpose -- with only one of them a
    # sort() mutation passes whenever the ids happen to already be in
    # that order, which is exactly what happened the first time this was
    # written.
    for order in ([SECOND, LOGS], [LOGS, SECOND]):
        client.patch(base, json={"ignore_channels": [str(c) for c in order]})
        data = client.get(base).json()
        check(f"the ignore list keeps the order it was built in {order}",
              data["ignore_channels"] == [str(c) for c in order],
              str(data["ignore_channels"]))

    client.patch(base, json={"ignore_channels": [str(LOGS), str(LOGS)]})
    data = client.get(base).json()
    check("a duplicate is dropped", data["ignore_channels"] == [str(LOGS)],
          str(data["ignore_channels"]))

    client.patch(base, json={"ignore_channels": []})
    data = client.get(base).json()
    check("an ignore list can be emptied again",
          data["ignore_channels"] == [], str(data["ignore_channels"]))

    # ── Auto delete ──────────────────────────────────────────────
    client.patch(base, json={"auto_delete_duration": 3600})
    check("the auto-delete duration sticks",
          client.get(base).json()["auto_delete_duration"] == 3600)
    client.patch(base, json={"auto_delete_duration": 0})
    check("zero means off, not zero seconds",
          client.get(base).json()["auto_delete_duration"] is None)
    r = client.patch(base, json={"auto_delete_duration": 999999})
    check("an absurd duration is refused", r.status_code == 400, str(r.status_code))

    # ── Rubbish input ────────────────────────────────────────────
    r = client.patch(base, json={"categories": {"nonsense": {"enabled": True}}})
    check("an unknown category is refused", r.status_code == 400, str(r.status_code))
    r = client.patch(base, json={"categories": {"message_events": True}})
    check("a category that is not an object is refused", r.status_code == 400,
          str(r.status_code))
    r = client.patch(base, json={"ignore_roles": "nope"})
    check("an ignore list that is not a list is refused", r.status_code == 400,
          str(r.status_code))
    r = client.patch(base, json={"ignore_roles": ["not-an-id"]})
    check("a non-numeric id is refused", r.status_code == 400, str(r.status_code))
    r = client.patch(base, json={
        "categories": {"role_events": {"enabled": True, "channel": "abc"}}
    })
    check("a non-numeric channel is refused", r.status_code == 400,
          str(r.status_code))

    # ── Warnings ─────────────────────────────────────────────────
    client.patch(base, json={
        "categories": {"role_events": {"enabled": True, "channel": None}}
    })
    # enabled=True with channel=None is impossible through the route, so
    # write it straight into the cog's cache the way a chat command could.
    cog.config_cache[GUILD]["log_enabled"]["role_events"] = True
    warns = client.get(base).json()["warnings"]
    check("a category with no channel is called out",
          any("ohne Kanal" in w for w in warns), str(warns))
    cog.config_cache[GUILD]["log_enabled"]["role_events"] = False

    logs._perms = Perms(send_messages=False)
    warns = client.get(base).json()["warnings"]
    check("a channel the bot cannot post in is called out",
          any("nicht schreiben" in w for w in warns), str(warns))

    logs._perms = Perms(embed_links=False)
    warns = client.get(base).json()["warnings"]
    check("a channel without embed permission is called out",
          any("Links einbetten" in w for w in warns), str(warns))
    logs._perms = Perms()

    guild.me.guild_permissions = Perms(view_audit_log=False)
    warns = client.get(base).json()["warnings"]
    check("a missing audit-log permission is called out",
          any("Audit-Log" in w for w in warns), str(warns))
    guild.me.guild_permissions = Perms()

    client.patch(base, json={
        "categories": {"channel_events": {"enabled": True, "channel": str(LOGS)}}
    })
    client.patch(base, json={"categories": {"channel_events": {"enabled": False}}})
    warns = client.get(base).json()["warnings"]
    check("a category with a channel but switched off is called out",
          any("ausgeschaltet" in w for w in warns), str(warns))

    del guild._channels[SECOND]
    warns = client.get(base).json()["warnings"]
    check("a deleted log channel is called out",
          any("existiert nicht mehr" in w for w in warns), str(warns))
    guild._channels[SECOND] = second

    # ── Test entry ───────────────────────────────────────────────
    before = len(logs.sent)
    r = client.post(f"{base}/test/message_events")
    check("a test entry can be posted", r.status_code == 200, r.text[:160])
    check("and it actually reached the channel", len(logs.sent) == before + 1)

    r = client.post(f"{base}/test/nonsense")
    check("a test for an unknown category is refused", r.status_code == 400)

    r = client.post(f"{base}/test/emoji_events")
    check("a test for a configured category works", r.status_code == 200,
          r.text[:120])

    client.patch(base, json={"categories": {"role_events": {"channel": None}}})
    r = client.post(f"{base}/test/role_events")
    check("a test without a channel says so, rather than failing silently",
          r.status_code == 400, str(r.status_code))

    logs.allow_send = False
    r = client.post(f"{base}/test/message_events")
    check("a refused post is reported as a permission problem",
          r.status_code == 400 and "nicht schreiben" in r.text, r.text[:160])
    logs.allow_send = True

    # ── One channel for everything ───────────────────────────────
    cog.config_cache.clear()
    r = client.post(f"{base}/all", json={"channel": str(LOGS)})
    check("everything can be pointed at one channel", r.status_code == 200,
          r.text[:160])
    data = client.get(base).json()
    check("eight of nine are on — reactions stay out by default",
          data["active_count"] == 8, str(data["active_count"]))
    reactions = next(c for c in data["categories"] if c["key"] == "reaction_events")
    check("reactions specifically stayed off", reactions["enabled"] is False)

    cog.config_cache.clear()
    client.post(f"{base}/all", json={"channel": str(LOGS), "include_noisy": True})
    data = client.get(base).json()
    check("but they can be asked for", data["active_count"] == 9,
          str(data["active_count"]))

    r = client.post(f"{base}/all", json={"channel": "999999999999999999"})
    check("a channel that is not on the server is refused", r.status_code == 400,
          str(r.status_code))

    # ── Missing bot / missing cog ────────────────────────────────
    r = client.get("/api/v1/logging/999999")
    check("an unknown guild still answers rather than crashing",
          r.status_code == 200, str(r.status_code))
    r = client.patch("/api/v1/logging/999999", json={})
    check("but writing to it is refused", r.status_code == 404, str(r.status_code))

    class NoCogBot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, gid):
            return guild

        def get_cog(self, name):
            return None

        def add_view(self, *a, **k):
            pass

    import api.dependencies as dep
    dep.set_bot(NoCogBot())
    r = client.get(base)
    check("an unloaded cog gives a clear 503, not a 500",
          r.status_code == 503, str(r.status_code))


def test_events_reach_the_right_category():
    """
    Every event has to land in the category the dashboard offers for it.

    A category switched on in the dashboard that never receives anything
    is indistinguishable from a broken bot -- and that is what happened:
    giving a member a role was logged under "Moderation", while the
    dashboard has a category called "Rollen" that stayed silent no
    matter what.
    """
    print("\nEvents land in the right category")

    source = read(os.path.join(BOT, "cogs/commands/logging.py"))

    # Which category each handler sends to.
    handlers: dict[str, set[str]] = {}
    current = None
    lines = source.splitlines()
    for index, line in enumerate(lines):
        found = re.search(r"async def (on_[a-z_]+|_reaction_log)", line)
        if found:
            current = found.group(1)
            handlers.setdefault(current, set())
        if current and "_send_log(" in line:
            blob = "\n".join(lines[index:index + 6])
            for category in re.findall(r'"([a-z_]+_events|member_moderation)"', blob):
                handlers[current].add(category)

    check("role changes go to the role category",
          "role_events" in handlers.get("on_member_update", set()),
          f"{handlers.get('on_member_update')} -- somebody switching on "
          "\"Rollen\" and handing out a role saw nothing")

    check("and no longer to moderation",
          "member_moderation" not in handlers.get("on_member_update", set())
          or "role_events" in handlers.get("on_member_update", set()),
          str(handlers.get("on_member_update")))

    # Every category the dashboard offers must be reachable.
    from api.routes.logging_cfg import CATEGORIES

    reachable = set()
    for cats in handlers.values():
        reachable |= cats
    unreachable = sorted(set(CATEGORIES) - reachable)
    check("every category the dashboard offers can actually fire",
          not unreachable,
          f"{unreachable} -- a category nothing sends to is a switch "
          "that does nothing")


def test_reactions_use_the_raw_events():
    """
    on_reaction_add only fires for cached messages.

    discord.py keeps 1000 messages across the whole bot by default, so
    on a busy server that is minutes of history. Reacting to anything
    older produced no event and nothing was logged -- the reported
    symptom exactly.

    The raw events always fire.
    """
    print("\nReactions are logged whatever their age")

    source = read(os.path.join(BOT, "cogs/commands/logging.py"))
    code = strip_comments(source)

    check("the raw add event is used",
          "async def on_raw_reaction_add" in code, "")
    check("and the raw remove event",
          "async def on_raw_reaction_remove" in code, "")
    check("the cache-only versions are gone",
          "async def on_reaction_add" not in code
          and "async def on_reaction_remove" not in code,
          "those only fire for messages still in the cache")

    body = source.split("async def _reaction_log")[1].split("\n    @commands")[0]

    check("both events share one implementation",
          code.count("await self._reaction_log(") == 2,
          "two copies drift, and one of them ends up missing a check")
    check("bots are still filtered out",
          'getattr(user, "bot", False)' in body,
          "reaction roles and paginators would bury the human ones")
    check("DMs are skipped",
          "payload.guild_id is None" in body, "")
    check("the jump link is built from ids",
          "discord.com/channels/" in body,
          "the raw event carries no message object to take it from")
    check("a member that cannot be resolved still logs",
          "fetch_user" in body and "<@{payload.user_id}>" in body,
          "the id is the one thing that survives a deleted account")
    check("it still reports the reaction category",
          '"reaction_events"' in body, "")


def test_new_events():
    """
    Things Discord reports that were not being logged at all.
    """
    print("\nEvents that were missing entirely")

    source = read(os.path.join(BOT, "cogs/commands/logging.py"))
    code = strip_comments(source)

    for event, why in (
        ("on_bulk_message_delete",
         "a purge fires one bulk event, not fifty deletes -- clearing a "
         "hundred messages left no trace"),
        ("on_thread_create", "threads are channels people talk in"),
        ("on_thread_delete", ""),
        ("on_invite_create", "an invite is how a raid gets in"),
        ("on_invite_delete", ""),
    ):
        check(f"{event} is handled", f"async def {event}" in code, why)

    bulk = source.split("async def on_bulk_message_delete")[1].split("\n    @commands")[0]
    check("a purge is one entry, not one per message",
          '"Count"' in bulk, "")
    check("and says who did it",
          "message_bulk_delete" in bulk,
          "that is the question a purge log answers")
    check("only a sample of the messages is quoted",
          "messages[:5]" in bulk,
          "fifty quoted messages exceed the embed limits and are "
          "unreadable anyway")


async def run():
    test_categories_match_the_cog()
    test_events_reach_the_right_category()
    test_reactions_use_the_raw_events()
    test_new_events()
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
