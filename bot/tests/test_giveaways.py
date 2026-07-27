"""
Giveaways: button entries, drawing, rerolls and DMs.

The old flow counted entrants by reading the 🎉 reaction back off the
message and stored giveaways in db/giveaway.db while the cog's timer read
db/giveaways.db — a different file — so a giveaway started from the
dashboard never ended by itself.

Run:  python3 tests/test_giveaways.py
"""

import asyncio
import datetime as _dt
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import discord  # noqa: E402

GUILD = 111
CHANNEL = "1327995167345819721"  # a real 19-digit snowflake


class FakeMessage:
    def __init__(self, mid, channel):
        self.id, self.channel = mid, channel
        self.jump_url = f"https://d/{mid}"
        self.edits = 0
        self.deleted = False

    async def edit(self, **kwargs):
        self.edits += 1

    async def delete(self):
        self.deleted = True

    async def add_reaction(self, _emoji):
        pass


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.messages = {}
        self.replies = []
        self._next = 5000

    def permissions_for(self, _m):
        return discord.Permissions.all()

    async def send(self, content=None, view=None, reference=None, **kw):
        if content is not None:
            self.replies.append(content)
            return FakeMessage(1, self)
        self._next += 1
        msg = FakeMessage(self._next, self)
        self.messages[msg.id] = msg
        return msg

    async def fetch_message(self, mid):
        if int(mid) in self.messages:
            return self.messages[int(mid)]
        raise Exception("not found")


class FakeMember:
    def __init__(self, uid, name):
        self.id, self.display_name = uid, name
        self.mention = f"<@{uid}>"
        self.dms = []
        self.roles = []
        self.guild = None
        # Old enough that no requirement blocks the plain cases.
        self.created_at = _dt.datetime(2015, 1, 1, tzinfo=_dt.timezone.utc)
        self.joined_at = _dt.datetime(2020, 1, 1, tzinfo=_dt.timezone.utc)

    @property
    def display_avatar(self):
        return type("A", (), {"url": "https://cdn/a.png"})()

    async def send(self, content=None, view=None, **kw):
        self.dms.append(view or content)


class FakeGuild:
    id, name = GUILD, "Test"

    def __init__(self):
        self.channel = FakeChannel(int(CHANNEL), "gewinnspiele")
        self.members = {
            10: FakeMember(10, "Alice"),
            11: FakeMember(11, "Bob"),
            12: FakeMember(12, "Carol"),
            99: FakeMember(99, "Host"),
        }
        self.me = object()
        for member in self.members.values():
            member.guild = self

    def get_channel(self, cid):
        return self.channel if str(cid) == CHANNEL else None

    def get_member(self, uid):
        return self.members.get(int(uid))

    def get_role(self, _rid):
        return None


class FakeBot:
    user = type("U", (), {"name": "Bot", "id": 1})()

    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    import api.dependencies as dep
    from api import giveaways as store
    from api.db_manager import db_manager
    from api.routes.giveaways import build_view
    from api.server import create_app
    from fastapi.testclient import TestClient

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/giveaways/{GUILD}"
    guild = bot.guilds[0]

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # --- the file the cog reads ---------------------------------------
    check("uses the same database as the cog's timer",
          store.DB_PATH == "db/giveaways.db", store.DB_PATH)

    # --- create with custom text --------------------------------------
    r = client.post(base, json={
        "channel_id": CHANNEL,
        "prize": "Discord Nitro",
        "winners": 2,
        "duration_minutes": 60,
        "title": "Mein Gewinnspiel",
        "description": "Gewinne {prize}! Endet {ends}.",
        "button_label": "Mitmachen",
        "button_emoji": "🎁",
        "actor": "99",
    })
    check("a giveaway can be created", r.status_code == 200,
          f"-> {r.status_code} {r.text[:90]}")
    message_id = int(r.json()["message_id"])

    listing = client.get(base).json()["giveaways"][0]
    check("the channel id survives intact",
          listing["channel_id"] == CHANNEL, listing["channel_id"])
    check("custom title is stored",
          listing["title"] == "Mein Gewinnspiel", listing["title"])
    check("custom button label is stored",
          listing["button_label"] == "Mitmachen", listing["button_label"])
    check("it starts with no entries", listing["entries"] == 0, str(listing))

    # --- placeholders --------------------------------------------------
    filled = store.fill_placeholders(
        "Gewinne {prize}! Endet {ends}.", {"prize": "Nitro", "ends": "morgen"}
    )
    check("placeholders are replaced",
          filled == "Gewinne Nitro! Endet morgen.", filled)

    # --- entries via the button ---------------------------------------
    async def scenario():
        db = await db_manager.get_connection(store.DB_PATH)
        await store.ensure_schema(db)

        first = await store.add_entry(db, message_id, 10)
        again = await store.add_entry(db, message_id, 11)
        duplicate = await store.add_entry(db, message_id, 10)
        await store.add_entry(db, message_id, 12)
        return first, again, duplicate, await store.entry_count(db, message_id)

    first, second, duplicate, total = asyncio.run(scenario())
    check("a join is recorded", first is True)
    check("a second person can join", second is True)
    check("joining twice does not count twice", duplicate is False)
    check("three entrants are counted", total == 3, str(total))

    listing = client.get(base).json()["giveaways"][0]
    check("the entry count shows up in the API", listing["entries"] == 3,
          str(listing["entries"]))

    entries = client.get(f"{base}/{message_id}/entries").json()
    check("entrants can be listed with names",
          entries["count"] == 3 and any(e["name"] == "Alice" for e in entries["entries"]),
          str(entries))

    # --- leaving again --------------------------------------------------
    async def leave():
        db = await db_manager.get_connection(store.DB_PATH)
        await store.remove_entry(db, message_id, 12)
        return await store.entry_count(db, message_id)

    check("pressing again leaves the giveaway", asyncio.run(leave()) == 2)

    # --- drawing ---------------------------------------------------------
    r = client.post(f"{base}/{message_id}/end", json={"actor": "99"})
    body = r.json()
    check("ending draws the configured number of winners",
          r.status_code == 200 and len(body["winners"]) == 2, str(body))
    check("winners come from the entrants",
          all(w in {"10", "11"} for w in body["winners"]), str(body["winners"]))
    check("the result is announced in the channel",
          any("gewinn" in m.lower() or "Glückwunsch" in m
              for m in guild.channel.replies),
          str(guild.channel.replies))

    winner_dms = sum(
        1 for uid in (10, 11) if guild.members[uid].dms
    )
    check("winners get a DM", winner_dms == 2, str(winner_dms))
    check("the host gets a summary DM", bool(guild.members[99].dms))

    listing = client.get(base).json()["giveaways"][0]
    check("it is marked as finished", listing["running"] is False, str(listing))
    check("the winners are remembered",
          len(listing["winner_ids"]) == 2, str(listing["winner_ids"]))

    # --- reroll ------------------------------------------------------------
    async def add_more():
        db = await db_manager.get_connection(store.DB_PATH)
        for uid in (20, 21, 22):
            await store.add_entry(db, message_id, uid)

    asyncio.run(add_more())

    r = client.post(f"{base}/{message_id}/reroll", json={"count": 1, "actor": "99"})
    body = r.json()
    check("a reroll works from the dashboard", r.status_code == 200, str(body))
    check("the reroll skips previous winners",
          body["winners"][0] not in {"10", "11"}, str(body["winners"]))

    # --- cancel -------------------------------------------------------------
    r = client.post(base, json={
        "channel_id": CHANNEL, "prize": "Test", "winners": 1,
        "duration_minutes": 10, "actor": "99",
    })
    doomed = r.json()["message_id"]
    r = client.delete(f"{base}/{doomed}")
    check("a giveaway can be cancelled", r.status_code == 200, str(r.json()))
    remaining = [g["message_id"] for g in client.get(base).json()["giveaways"]]
    check("the cancelled one is gone", doomed not in remaining, str(remaining))

    r = client.post(f"{base}/999999/end", json={})
    check("an unknown giveaway gives 404", r.status_code == 404)

    # ══════════════════════════════════════════════════════════════════
    #  Editing a running giveaway
    # ══════════════════════════════════════════════════════════════════

    r = client.post(base, json={
        "channel_id": CHANNEL, "prize": "Steam Key", "winners": 1,
        "duration_minutes": 60, "actor": "99",
        "msg_joined": "Viel Glück! ({entries} dabei)",
        "min_messages": 50, "min_account_days": 7,
    })
    live = r.json()["message_id"]

    detail = client.get(f"{base}/{live}").json()
    check("the detail view returns the whole giveaway",
          detail["prize"] == "Steam Key", str(detail)[:120])
    check("custom reply text is stored",
          detail["msg_joined"] == "Viel Glück! ({entries} dabei)",
          detail["msg_joined"])
    check("requirements are stored",
          detail["min_messages"] == 50 and detail["min_account_days"] == 7,
          str(detail["min_messages"]))
    check("requirements are listed for the message",
          any("50" in line for line in detail["requirements"]),
          str(detail["requirements"]))
    check("the defaults are sent along for the editor",
          "msg_left" in detail["defaults"], str(detail["defaults"])[:80])

    before = detail["ends_at"]
    r = client.patch(f"{base}/{live}", json={"extend_minutes": 120, "actor": "99"})
    check("a giveaway can be extended", r.status_code == 200, r.text[:100])
    after = client.get(f"{base}/{live}").json()["ends_at"]
    check("extending really moves the end time",
          7100 < after - before < 7300, str(after - before))

    # A partial PATCH must not blank the fields it does not mention —
    # that is exactly how the ticket tab used to lose half its input.
    client.patch(f"{base}/{live}", json={"winners": 3})
    detail = client.get(f"{base}/{live}").json()
    check("a partial edit keeps the other fields",
          detail["msg_joined"] == "Viel Glück! ({entries} dabei)"
          and detail["min_messages"] == 50,
          f'{detail["msg_joined"]!r} {detail["min_messages"]}')
    check("the winner count can be changed", detail["winners"] == 3,
          str(detail["winners"]))

    r = client.patch(f"{base}/{live}", json={"prize": "  "})
    check("an empty prize is rejected", r.status_code == 400, str(r.status_code))

    # ══════════════════════════════════════════════════════════════════
    #  Per-user odds
    # ══════════════════════════════════════════════════════════════════

    async def join_all():
        db = await db_manager.get_connection(store.DB_PATH)
        for uid in (10, 11, 12):
            await store.add_entry(db, int(live), uid)

    asyncio.run(join_all())

    r = client.post(f"{base}/{live}/boost", json={
        "user_id": "10", "mode": "weight", "weight": 100, "actor": "99",
    })
    check("extra tickets can be handed out", r.status_code == 200, r.text[:100])

    detail = client.get(f"{base}/{live}").json()
    alice = next(e for e in detail["entries"] if e["id"] == "10")
    bob = next(e for e in detail["entries"] if e["id"] == "11")
    check("the weight shows up in the dashboard", alice["weight"] == 100,
          str(alice))
    check("a favoured entrant has a far higher chance",
          alice["chance"] > bob["chance"] * 10,
          f'{alice["chance"]} vs {bob["chance"]}')

    # Nothing about it may reach the channel: render the real message and
    # look for anything that would give the favouritism away.
    async def rendered():
        db = await db_manager.get_connection(store.DB_PATH)
        record = await store.get(db, GUILD, int(live))
        entries = await store.entry_count(db, int(live))
        view = build_view(record, entries=entries, guild=guild)
        return str(view.to_components())

    payload = asyncio.run(rendered()).lower()
    check("the odds never appear in the giveaway message",
          "lose" not in payload and "garantiert" not in payload
          and "chance" not in payload,
          payload[:160])

    r = client.post(f"{base}/{live}/boost", json={
        "user_id": "11", "mode": "guaranteed", "actor": "99",
    })
    check("a guaranteed winner can be set", r.status_code == 200, r.text[:100])
    detail = client.get(f"{base}/{live}").json()
    bob = next(e for e in detail["entries"] if e["id"] == "11")
    check("a guaranteed entrant is shown at 100%",
          bob["guaranteed"] and bob["chance"] == 100.0, str(bob))

    # 1000 draws for one winner: Bob is guaranteed, so he must win each time.
    async def draw_many():
        db = await db_manager.get_connection(store.DB_PATH)
        return [
            (await store.draw(db, int(live), 1))[0] for _ in range(200)
        ]

    picks = asyncio.run(draw_many())
    check("the guaranteed entrant wins every single draw",
          set(picks) == {11}, str(sorted(set(picks))))

    # Without the guarantee, weight alone should still dominate.
    client.post(f"{base}/{live}/boost", json={"user_id": "11", "mode": "clear"})
    picks = asyncio.run(draw_many())
    share = picks.count(10) / len(picks)
    check("100 tickets against 1 wins about 98% of the time",
          share > 0.9, f"{share:.2f}")

    # Two winners must be two different people, even with a huge weight.
    async def draw_two():
        db = await db_manager.get_connection(store.DB_PATH)
        return [await store.draw(db, int(live), 2) for _ in range(50)]

    pairs = asyncio.run(draw_two())
    check("a weighted draw never picks the same person twice",
          all(len(set(p)) == len(p) for p in pairs),
          str([p for p in pairs if len(set(p)) != len(p)][:2]))

    r = client.post(f"{base}/{live}/boost", json={"user_id": "10", "mode": "clear"})
    check("a boost can be removed", r.status_code == 200, r.text[:100])
    detail = client.get(f"{base}/{live}").json()
    alice = next(e for e in detail["entries"] if e["id"] == "10")
    check("after removing, everyone is equal again", alice["weight"] == 1,
          str(alice["weight"]))

    r = client.post(f"{base}/{live}/boost", json={"user_id": "nope"})
    check("a boost without a member is rejected", r.status_code == 400)

    # ══════════════════════════════════════════════════════════════════
    #  Entry requirements
    # ══════════════════════════════════════════════════════════════════

    guild.members[10].created_at = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=2)
    record = {"guild_id": GUILD, "min_account_days": 7}
    problems = asyncio.run(store.failed_requirements(record, guild.members[10]))
    check("a young account is turned away", len(problems) == 1, str(problems))
    check("the reason names the requirement", "7" in problems[0], problems[0])

    guild.members[10].created_at = _dt.datetime(2015, 1, 1, tzinfo=_dt.timezone.utc)
    problems = asyncio.run(store.failed_requirements(record, guild.members[10]))
    check("an old enough account may enter", problems == [], str(problems))

    problems = asyncio.run(store.failed_requirements(
        {"guild_id": GUILD, "min_messages": 10}, guild.members[10]
    ))
    check("a message requirement blocks someone with no messages",
          len(problems) == 1, str(problems))

    problems = asyncio.run(store.failed_requirements(
        {"guild_id": GUILD}, guild.members[10]
    ))
    check("without requirements nobody is blocked", problems == [], str(problems))

    check("no requirements means no extra line in the message",
          store.requirement_lines({"guild_id": GUILD}) == [], "")

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        os.makedirs("jsondb", exist_ok=True)
        sys.exit(run())
