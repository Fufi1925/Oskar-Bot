#!/usr/bin/env python3
"""
Welcome messages: one renderer for the greeter and the dashboard.

The bug this pins down: the live greeter in cogs/events/greet2.py filled
`{server_name}` and `{server_membercount}`, while the dashboard's preview
route filled `{server}` and `{count}` and only understood title,
description and footer. So the preview showed something no member would
ever get, and the other half of the placeholders was posted verbatim as
`{server_name}`.

Both now go through utils/greet_render.py.

Run:  python3 tests/test_welcome.py
"""

import asyncio
import datetime as _dt
import json
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import aiosqlite  # noqa: E402
import discord  # noqa: E402

GUILD = 222
CHANNEL = "1327995167345819721"


class FakeAsset:
    url = "https://cdn.discordapp.com/avatars/7/abc.png"


class FakeMember:
    def __init__(self, uid=7, name="neuer"):
        self.id = uid
        self.name = name
        self.display_name = "Neuer"
        self.mention = f"<@{uid}>"
        self.display_avatar = FakeAsset()
        self.joined_at = _dt.datetime(2026, 7, 25, tzinfo=_dt.timezone.utc)
        self.created_at = _dt.datetime(2024, 1, 8, tzinfo=_dt.timezone.utc)
        self.guild = None


class FakeMessage:
    # `view` is recorded too: the greeting is a Components V2 panel now,
    # and a stub that only kept the embed made the panel invisible to
    # the assertions.
    def __init__(self, content=None, embed=None, view=None):
        self.content, self.embed, self.view = content, embed, view
        self.jump_url = "https://d/1"

    async def delete(self, delay=None):
        pass


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent = []

    def permissions_for(self, _m):
        return discord.Permissions.all()

    async def send(self, content=None, embed=None, view=None, **kw):
        message = FakeMessage(content, embed, view)
        self.sent.append(message)
        return message


class FakeIcon:
    url = "https://cdn.discordapp.com/icons/222/x.png"


class FakeGuild:
    id, name = GUILD, "Mein Server"
    member_count = 1204
    icon = FakeIcon()

    def __init__(self):
        self.channel = FakeChannel(int(CHANNEL), "willkommen")
        self.member = FakeMember()
        self.member.guild = self
        self.me = FakeMember(1, "bot")
        self.me.guild = self

    def get_channel(self, cid):
        return self.channel if str(cid) == CHANNEL else None

    def get_member(self, uid):
        return self.member if int(uid) == self.member.id else None

    def get_role(self, _r):
        return None


class FakeBot:
    user = type("U", (), {"name": "Bot", "id": 1})()

    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_channel(self, cid):
        return self.guilds[0].get_channel(cid)

    def get_cog(self, _n):
        return None

    def add_view(self, *a, **k):
        pass


def run():
    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import greet_render

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    guild = bot.guilds[0]
    member = guild.member

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ── placeholders ───────────────────────────────────────────────
    values = greet_render.placeholders(member)
    check("every documented placeholder has a value",
          set(greet_render.PLACEHOLDERS) <= set(values),
          str(set(greet_render.PLACEHOLDERS) - set(values)))

    text = greet_render.fill(
        "Hi {user}, willkommen auf {server_name}! Du bist #{server_membercount}.",
        values,
    )
    check("the greeter's placeholders are replaced",
          "<@7>" in text and "Mein Server" in text and "1204" in text, text)
    check("nothing is left over as raw text", "{" not in text, text)

    check("placeholders work regardless of case",
          greet_render.fill("{SERVER_NAME}", values) == "Mein Server",
          greet_render.fill("{SERVER_NAME}", values))
    check("an unknown placeholder is left alone, not an error",
          greet_render.fill("{gibtsnicht}", values) == "{gibtsnicht}",
          greet_render.fill("{gibtsnicht}", values))

    # A member without their own avatar: .avatar is None and used to crash.
    check("a member without an avatar still works",
          values["user_avatar"].startswith("https://"), values["user_avatar"])

    # ── colours ────────────────────────────────────────────────────
    check("a #rrggbb colour is understood",
          greet_render.parse_colour("#5865f2") == 0x5865F2)
    check("a colour without the hash is understood",
          greet_render.parse_colour("5865f2") == 0x5865F2)
    check("an integer colour is passed through",
          greet_render.parse_colour(0x123456) == 0x123456)
    check("nonsense falls back to the default colour",
          greet_render.parse_colour("blau") == greet_render.DEFAULT_COLOUR)

    # ── rendering ──────────────────────────────────────────────────
    content, embed = greet_render.render(
        {"welcome_type": "simple", "welcome_message": "Hi {user}!"}, member
    )
    check("a plain message renders", content == "Hi <@7>!" and embed is None,
          f"{content!r}")

    embed_config = {
        "welcome_type": "embed",
        "embed_data": json.dumps({
            "message": "{user}",
            "title": "Willkommen auf {server_name}!",
            "description": "Schön, dass du da bist, {user}!",
            "color": "#5865f2",
            "footer_text": "Mitglied #{server_membercount}",
            "footer_icon": "{server_icon}",
            "author_name": "{user_name}",
            "author_icon": "{user_avatar}",
            "thumbnail": "{user_avatar}",
            "image": "https://example.com/banner.png",
        }),
    }
    content, embed = greet_render.render(embed_config, member)
    check("the text above the card is rendered", content == "<@7>", str(content))
    check("the card title is filled",
          embed.title == "Willkommen auf Mein Server!", str(embed.title))
    check("the colour is applied", embed.color.value == 0x5865F2,
          str(embed.color))
    check("the footer is filled", embed.footer.text == "Mitglied #1204",
          str(embed.footer.text))
    # The old greeter had these, the old preview silently dropped them.
    check("the header survives", embed.author.name == "neuer",
          str(embed.author.name))
    check("the small image survives",
          embed.thumbnail.url == member.display_avatar.url, str(embed.thumbnail))
    check("the large image survives",
          embed.image.url == "https://example.com/banner.png", str(embed.image))

    # A placeholder that is not a URL must not be handed to Discord.
    broken = greet_render.render(
        {
            "welcome_type": "embed",
            "embed_data": json.dumps({"title": "Hi", "thumbnail": "kein-link"}),
        },
        member,
    )[1]
    check("a broken image link is dropped instead of breaking the embed",
          broken.thumbnail.url is None, str(broken.thumbnail))

    check("nothing configured means nothing is sent",
          greet_render.render({"welcome_type": "simple"}, member) == (None, None))
    check("broken JSON does not raise",
          greet_render.render(
              {"welcome_type": "embed", "embed_data": "{kaputt"}, member
          ) == (None, None))

    # ── the preview route uses the same renderer ───────────────────
    async def seed():
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS welcome (guild_id INTEGER PRIMARY KEY,"
                " welcome_type TEXT, welcome_message TEXT, channel_id INTEGER,"
                " embed_data TEXT, auto_delete_duration INTEGER)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO welcome VALUES (?, ?, ?, ?, ?, ?)",
                (
                    GUILD, "simple",
                    "Willkommen {user} auf {server_name}! Mitglied #{server_membercount}.",
                    int(CHANNEL), None, 0,
                ),
            )
            await db.commit()

    asyncio.run(seed())

    r = client.post(
        f"/api/v1/actions/{GUILD}/welcome/test",
        json={"channel_id": CHANNEL, "actor": "7"},
    )
    check("the preview can be sent", r.status_code == 200, r.text[:120])

    posted = guild.channel.sent[-1].content or ""
    check("the preview fills the same placeholders as the greeter",
          "Mein Server" in posted and "1204" in posted, posted)
    check("the preview leaves no raw placeholder behind",
          "{" not in posted, posted)

    # Previewing an unsaved draft.
    r = client.post(
        f"/api/v1/actions/{GUILD}/welcome/test",
        json={
            "channel_id": CHANNEL,
            "actor": "7",
            "welcome_type": "embed",
            "embed_data": {
                "title": "Entwurf für {server_name}",
                "description": "Hallo {user}",
                "color": "#ff0000",
            },
        },
    )
    check("an unsaved draft can be previewed", r.status_code == 200, r.text[:120])
    sent = guild.channel.sent[-1]
    # The preview is a Components V2 panel now, not an embed, so read
    # the text out of whichever one was sent. What matters is that the
    # rendered title reaches the channel -- with placeholders filled in.
    def rendered_text(message) -> str:
        if getattr(message, "embed", None) is not None:
            return "\n".join(
                str(part) for part in
                (message.embed.title, message.embed.description) if part
            )
        collected: list[str] = []

        def walk(item):
            if type(item).__name__ == "TextDisplay":
                collected.append(str(item.content))
            for child in getattr(item, "children", []) or []:
                walk(child)
            accessory = getattr(item, "accessory", None)
            if accessory is not None:
                walk(accessory)

        for child in getattr(getattr(message, "view", None), "children", []) or []:
            walk(child)
        return "\n".join(collected)

    body = rendered_text(sent)
    check("the draft is rendered as a card, not as text",
          "Entwurf für Mein Server" in body,
          repr(body[:120]))

    # Saving the draft must not have happened.
    async def stored():
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT welcome_type FROM welcome WHERE guild_id = ?", (GUILD,)
            ) as cursor:
                return (await cursor.fetchone())[0]

    check("previewing a draft does not save it", asyncio.run(stored()) == "simple",
          asyncio.run(stored()))

    r = client.post(
        f"/api/v1/actions/{GUILD}/welcome/test", json={"channel_id": "999"}
    )
    check("an unknown channel is rejected", r.status_code in (400, 404),
          str(r.status_code))

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
