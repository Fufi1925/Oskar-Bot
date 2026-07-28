#!/usr/bin/env python3
"""
YouTube notifications.

The feature this replaces could not do the thing it was named after. It
watched the *Discord streaming status* of members, which means:

  * it never saw an upload at all -- there was no YouTube request
    anywhere in the bot;
  * it only worked for people who happened to be on the server;
  * its listener queried ``WHERE type = ?`` with no guild in it, so
    every server was handed the first server's role and channel;
  * and with no edge detection, one stream produced a ping per presence
    update.

What is here now: you give it a channel name, it resolves that to a
channel id once, then watches the public RSS feed for uploads (Shorts
included) and the channel's /live page for broadcasts. No API key.

Twitch is deliberately absent -- its API answers 401 to everything
without a registered client id and secret, so a Twitch control would be
a box that does nothing.

Network tests are skipped when YouTube is unreachable, so this stays
usable offline; the parsing is covered either way with saved markup.

Run:  python3 tests/test_youtube_notify.py
"""

import asyncio
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import aiohttp  # noqa: E402

GUILD = 7701
OTHER = 7702
CHANNEL = 1327995167345819721      # a real-length snowflake
ROLE = 500000000000000001

failures: list[str] = []
skipped: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def skip(name, why):
    print(f"  skip {name} ({why})")
    skipped.append(name)


# ══════════════════════════════════════════════════════════════════════
#  Fakes
# ══════════════════════════════════════════════════════════════════════


class Perms:
    def __init__(self, send=True, embed=True):
        self.send_messages = send
        self.embed_links = embed


class Channel:
    def __init__(self, cid, name="uploads"):
        self.id = cid
        self.name = name
        self.sent: list = []
        self.perms = Perms()

    def permissions_for(self, _member):
        return self.perms

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("M", (), {"id": 1})()


class Role:
    def __init__(self, rid, name="Ping"):
        self.id = rid
        self.name = name
        self.color = type("C", (), {"value": 0})()


class Guild:
    def __init__(self, gid=GUILD):
        self.id = gid
        self.name = "Test"
        self.me = type("M", (), {"id": 1})()
        self._channels = {CHANNEL: Channel(CHANNEL)}
        self._roles = {ROLE: Role(ROLE)}

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_role(self, rid):
        return self._roles.get(int(rid))


# ══════════════════════════════════════════════════════════════════════
#  Parsing, without the network
# ══════════════════════════════════════════════════════════════════════


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
 <title>Test Kanal</title>
 <entry>
  <yt:videoId>aaaaaaaaaaa</yt:videoId>
  <media:title>Neuestes Video &amp; mehr</media:title>
  <published>2026-07-28T10:00:00+00:00</published>
 </entry>
 <entry>
  <yt:videoId>bbbbbbbbbbb</yt:videoId>
  <media:title>Ein Short</media:title>
  <published>2026-07-27T10:00:00+00:00</published>
 </entry>
</feed>"""


class FakeResponse:
    def __init__(self, text, status=200):
        self._text = text
        self.status = status

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Answers whatever the test lines up, keyed by substring."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.asked: list[str] = []

    def get(self, url, **kwargs):
        self.asked.append(url)
        for needle, body in self.routes.items():
            if needle in url:
                return FakeResponse(body)
        return FakeResponse("", status=404)


async def test_parsing():
    print("\nParsing")
    from utils import youtube_watch as yt

    session = FakeSession({"feeds/videos.xml": FEED})
    videos = await yt.latest_videos(session, "UC" + "x" * 22)

    check("the feed is read", len(videos) == 2, str(len(videos)))
    check("newest comes first", videos[0].id == "aaaaaaaaaaa", videos[0].id)
    check("the title is unescaped",
          videos[0].title == "Neuestes Video & mehr", repr(videos[0].title))
    check("a watch url is built",
          videos[0].url == "https://www.youtube.com/watch?v=aaaaaaaaaaa",
          videos[0].url)
    # Shorts are ordinary entries in the feed -- the user asked for both.
    check("Shorts are in the same feed", videos[1].id == "bbbbbbbbbbb")

    # Live detection.
    live_html = '{"isLive":true} <meta name="title" content="Der Stream">' \
                ' "videoId":"ccccccccccc"'
    session = FakeSession({"/live": live_html})
    live = await yt.live_now(session, "UC" + "x" * 22)
    check("a running broadcast is found", live is not None)
    check("with its id", live and live.id == "ccccccccccc", str(live))
    check("and its title", live and live.title == "Der Stream", str(live))

    session = FakeSession({"/live": '{"isLive":false} "videoId":"ddddddddddd"'})
    check("a channel that is not live returns nothing",
          await yt.live_now(session, "UC" + "x" * 22) is None)

    # An ended stream keeps isLiveBroadcast in its metadata. Without the
    # endDate check the bot re-announces old streams as new ones.
    ended = '{"isLiveBroadcast":true} "endDate":"2026-07-01" "videoId":"eeeeeeeeeee"'
    session = FakeSession({"/live": ended})
    check("an ended stream is not announced as live",
          await yt.live_now(session, "UC" + "x" * 22) is None)

    session = FakeSession({})
    check("an unreachable channel does not raise",
          await yt.live_now(session, "UC" + "x" * 22) is None)
    check("an unreachable feed gives an empty list",
          await yt.latest_videos(session, "UC" + "x" * 22) == [])


async def test_resolve_offline():
    print("\nResolving a name")
    from utils import youtube_watch as yt

    cid = "UC" + "a" * 22
    page = f'"channelId":"{cid}" <meta property="og:title" content="Test Kanal">'
    session = FakeSession({"youtube.com/@": page, "feeds/videos.xml": FEED})

    found = await yt.resolve(session, "@TestKanal")
    check("an @handle resolves", found.id == cid, found.id)
    check("the display name comes along", found.title == "Test Kanal", found.title)

    session = FakeSession({"youtube.com/@": page, "feeds/videos.xml": FEED})
    check("a bare name resolves too",
          (await yt.resolve(session, "TestKanal")).id == cid)

    session = FakeSession({"youtube.com/@": page, "feeds/videos.xml": FEED})
    check("a full url resolves",
          (await yt.resolve(session, "https://www.youtube.com/@TestKanal")).id == cid)

    # A channel id needs no lookup, but must still exist.
    session = FakeSession({"feeds/videos.xml": FEED})
    found = await yt.resolve(session, cid)
    check("a UC id is taken as-is", found.id == cid, found.id)

    session = FakeSession({})
    try:
        await yt.resolve(session, "gibtesnicht")
        check("an unknown name is refused", False, "no error raised")
    except yt.LookupError_ as err:
        check("an unknown name is refused with a readable sentence",
              "gibt es nicht" in str(err), str(err)[:60])

    session = FakeSession({})
    try:
        await yt.resolve(session, "   ")
        check("an empty name is refused", False, "no error raised")
    except yt.LookupError_:
        check("an empty name is refused", True)


# ══════════════════════════════════════════════════════════════════════
#  Store
# ══════════════════════════════════════════════════════════════════════


async def test_store():
    print("\nStore")
    import aiosqlite
    from utils import extras_store as store

    db = await aiosqlite.connect(store.NOTIFY_DB)
    await store.yt_ensure(db)

    await store.yt_add(
        db, GUILD, channel_id="UC" + "1" * 22, handle="@eins", title="Eins",
        post_channel=CHANNEL, role_id=ROLE, last_video="v1",
    )
    await store.yt_add(
        db, OTHER, channel_id="UC" + "1" * 22, handle="@eins", title="Eins",
        post_channel=CHANNEL, role_id=None,
    )

    ours = await store.yt_list(db, GUILD)
    theirs = await store.yt_list(db, OTHER)

    # The bug that defined the old feature: one server's setting leaking
    # into every other server.
    check("each guild keeps its own row", len(ours) == 1 and len(theirs) == 1)
    check("and its own ping role",
          ours[0]["role_id"] == ROLE and theirs[0]["role_id"] is None,
          f"{ours[0]['role_id']} / {theirs[0]['role_id']}")
    check("two guilds can watch the same channel",
          ours[0]["channel_id"] == theirs[0]["channel_id"])

    check("the seeded video is remembered", ours[0]["last_video"] == "v1")

    # Partial update.
    await store.yt_update(db, GUILD, "UC" + "1" * 22, {"on_live": False})
    ours = await store.yt_list(db, GUILD)
    check("a partial update writes only what it was given",
          ours[0]["on_live"] is False and ours[0]["on_upload"] is True,
          str(ours[0]))
    check("and leaves the rest alone", ours[0]["role_id"] == ROLE)

    theirs = await store.yt_list(db, OTHER)
    check("the other guild is untouched", theirs[0]["on_live"] is True)

    check("yt_all sees both", len(await store.yt_all(db)) == 2)
    check("the count is per guild", await store.yt_count(db, GUILD) == 1)

    check("removing works", await store.yt_remove(db, GUILD, "UC" + "1" * 22))
    check("removing twice says so",
          not await store.yt_remove(db, GUILD, "UC" + "1" * 22))
    check("and the other guild still has its row",
          await store.yt_count(db, OTHER) == 1)

    await db.close()


# ══════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════


async def test_api(online: bool):
    print("\nAPI")

    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import extras_store as store

    guild = Guild()

    class ApiBot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, gid):
            return guild if int(gid) == GUILD else None

        def get_cog(self, name):
            return None

        def add_view(self, *a, **k):
            pass

    dep.set_bot(ApiBot())
    client = TestClient(create_app())
    base = f"/api/v1/extras/{GUILD}/notify"

    data = client.get(base).json()
    check("a fresh server answers", "entries" in data, str(data)[:120])
    check("with the limit stated", data["max"] == store.YT_MAX_PER_GUILD,
          str(data.get("max")))
    check("and three free slots", data["slots_left"] == 3,
          str(data.get("slots_left")))

    r = client.post(base, json={"name": "", "channel_id": str(CHANNEL)})
    check("an empty name is refused", r.status_code == 400, str(r.status_code))
    r = client.post(base, json={"name": "@x", "channel_id": "nonsense"})
    check("a bad channel is refused", r.status_code == 400, str(r.status_code))
    r = client.post(base, json={
        "name": "@x", "channel_id": str(CHANNEL),
        "on_upload": False, "on_live": False,
    })
    check("both events off is refused", r.status_code == 400,
          "a subscription that can never fire is not a subscription")

    if not online:
        skip("adding a real channel", "no network")
        return

    r = client.post(base, json={
        "name": "@MrBeast", "channel_id": str(CHANNEL), "role_id": str(ROLE),
    })
    check("a real channel can be added", r.status_code == 200, r.text[:160])
    body = r.json()
    check("the resolved id comes back",
          body.get("channel_id", "").startswith("UC"), str(body)[:120])

    data = client.get(base).json()
    check("it is listed", len(data["entries"]) == 1, str(len(data["entries"])))
    entry = data["entries"][0]
    check("with a readable title", bool(entry["title"]), str(entry))
    check("the discord channel id stayed a string",
          isinstance(entry["post_channel"], str))
    check("the role id stayed a string too",
          isinstance(entry["role_id"], str), str(entry["role_id"]))
    check("both events default to on", entry["on_upload"] and entry["on_live"])
    check("a slot was used", data["slots_left"] == 2, str(data["slots_left"]))

    cid = entry["channel_id"]

    # Seeding. Subscribing has to remember what is already out, or the
    # first poll announces the channel's last upload as though it had
    # just appeared -- which for a channel that posts daily means an
    # instant ping about a video everybody already saw.
    import aiosqlite
    from utils import extras_store as store2

    seed_db = await aiosqlite.connect(store2.NOTIFY_DB)
    seeded = await store2.yt_list(seed_db, GUILD)
    await seed_db.close()
    check("subscribing remembers the newest video already out",
          bool(seeded and seeded[0]["last_video"]),
          "without this the first poll re-announces an old upload")
    check("and the remembered id looks like a video id",
          bool(seeded) and len(seeded[0]["last_video"] or "") == 11,
          str(seeded[0]["last_video"] if seeded else None))

    r = client.patch(f"{base}/{cid}", json={"on_live": False})
    check("a subscription can be edited", r.status_code == 200, r.text[:120])
    entry = client.get(base).json()["entries"][0]
    check("the change stuck", entry["on_live"] is False)
    check("and the other flag is untouched", entry["on_upload"] is True)

    r = client.patch(f"{base}/{cid}", json={"on_upload": False})
    check("turning the last one off is refused", r.status_code == 400,
          str(r.status_code))

    r = client.patch(f"{base}/{'UC' + 'z' * 22}", json={"on_live": True})
    check("editing a subscription that does not exist gives 404",
          r.status_code == 404, str(r.status_code))

    before = len(guild._channels[CHANNEL].sent)
    r = client.post(f"{base}/{cid}/test")
    check("a test announcement can be posted", r.status_code == 200, r.text[:140])
    check("and it really reached the channel",
          len(guild._channels[CHANNEL].sent) == before + 1)
    # A test that pings the whole role every time somebody presses it
    # would make the button unusable.
    sent = guild._channels[CHANNEL].sent[-1]
    mentions = sent.get("allowed_mentions")
    check("the test pings nobody",
          mentions is not None and not getattr(mentions, "roles", None),
          str(mentions))

    guild._channels[CHANNEL].perms = Perms(send=False)
    warns = client.get(base).json()["warnings"]
    check("a channel the bot cannot post in is called out",
          any("nicht schreiben" in w for w in warns), str(warns))
    r = client.post(f"{base}/{cid}/test")
    check("and the test says so rather than failing silently",
          r.status_code == 400, str(r.status_code))
    guild._channels[CHANNEL].perms = Perms()

    r = client.post(base, json={"name": "quatschxyz999", "channel_id": str(CHANNEL)})
    check("a channel that does not exist is refused", r.status_code == 404,
          str(r.status_code))

    r = client.delete(f"{base}/{cid}")
    check("a subscription can be removed", r.status_code == 200)
    r = client.delete(f"{base}/{cid}")
    check("removing it twice gives 404", r.status_code == 404, str(r.status_code))


async def reachable() -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.youtube.com/feeds/videos.xml"
                "?channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                return response.status == 200
    except Exception:
        return False


async def test_live_network():
    """
    The two endpoints, against real channels.

    Skipped without network. Worth having: the whole feature rests on
    two pieces of undocumented public markup, and a silent change there
    is exactly the kind of thing that would otherwise only show up as
    "the bot stopped posting".
    """
    print("\nAgainst real YouTube")
    from utils import youtube_watch as yt

    async with aiohttp.ClientSession() as session:
        found = await yt.resolve(session, "@MrBeast")
        check("a real handle still resolves",
              found.id.startswith("UC") and len(found.id) == 24, found.id)

        videos = await yt.latest_videos(session, found.id)
        check("the real feed still parses", len(videos) > 0, str(len(videos)))
        if videos:
            check("with an 11-character video id",
                  len(videos[0].id) == 11, videos[0].id)
            check("and a title", bool(videos[0].title.strip()))

        # A channel that streams around the clock, and one that does not.
        live = await yt.live_now(session, "UCSJ4gkVC6NrvII8umztf0Ow")
        not_live = await yt.live_now(session, found.id)
        if live is None:
            skip("live detection", "the reference channel is not streaming")
        else:
            check("a live channel is detected", live.id != "")
            check("and a non-live one is not", not_live is None,
                  str(not_live))


async def run():
    online = await reachable()
    if not online:
        print("\n(no network — the parts that need YouTube are skipped)")

    await test_parsing()
    await test_resolve_offline()
    await test_store()
    await test_api(online)
    if online:
        await test_live_network()

    print(f"\n{len(failures)} failures, {len(skipped)} skipped")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        sys.exit(asyncio.run(run()))
