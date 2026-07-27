#!/usr/bin/env python3
"""
Compose: designing a message in the dashboard and posting it as the bot.

Discord answers a malformed message with a terse 400 that names no
field, so everything is validated here first — these checks are what
turns "Discord rejected the message" into a sentence somebody can act
on.

Run:  python3 tests/test_compose.py
"""

import asyncio
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

GUILD = 999
CHANNEL = "1327995167345819721"


def fake_response(status):
    """discord.HTTPException reads .status and .reason off the response."""
    return type("R", (), {"status": status, "reason": "test"})()


class FakeMessage:
    def __init__(self, mid, author_id=1):
        self.id = mid
        self.jump_url = f"https://d/{mid}"
        self.author = type("A", (), {"id": author_id})()
        self.content = "alt"
        self.embeds: list = []
        self.components: list = []
        self.edits: list = []
        self.pinned = False

    async def edit(self, **kwargs):
        self.edits.append(kwargs)

    async def pin(self, reason=None):
        self.pinned = True


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent: list = []
        self.can_send = True
        self.can_embed = True
        self.messages: dict = {}

    def permissions_for(self, _m):
        permissions = discord.Permissions.all()
        if not self.can_send:
            permissions.send_messages = False
        if not self.can_embed:
            permissions.embed_links = False
        return permissions

    async def send(self, **kwargs):
        if not self.can_send:
            raise discord.Forbidden(fake_response(403), "no")
        self.sent.append(kwargs)
        message = FakeMessage(5000 + len(self.sent))
        self.messages[message.id] = message
        return message

    async def fetch_message(self, mid):
        if int(mid) in self.messages:
            return self.messages[int(mid)]
        raise discord.NotFound(fake_response(404), "gone")


class FakeGuild:
    id, name = GUILD, "Test"

    def __init__(self):
        self.channel = FakeChannel(int(CHANNEL), "ankündigungen")
        self.me = type("M", (), {"guild_permissions": discord.Permissions.all()})()

    def get_channel(self, cid):
        return self.channel if str(cid) == CHANNEL else None


class FakeBot:
    user = type("U", (), {"id": 1, "name": "Bot"})()

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
    from api.db_manager import db_manager
    from api.server import create_app
    from fastapi.testclient import TestClient
    from utils import message_builder as builder

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    guild = bot.guilds[0]
    base = f"/api/v1/compose/{GUILD}"

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # ══ Validation: plain text ════════════════════════════════════
    check("an empty text is caught",
          builder.validate({"kind": "text", "content": "  "}) != [])
    check("a normal text passes",
          builder.validate({"kind": "text", "content": "Hallo"}) == [])
    problems = builder.validate({"kind": "text", "content": "x" * 2500})
    check("text over 2000 characters is caught", problems != [], str(problems))
    check("the message says how long it actually is",
          any("2500" in p for p in problems), str(problems))

    # ══ Validation: embed ═════════════════════════════════════════
    check("a completely empty embed is caught",
          builder.validate({"kind": "embed", "embed": {}}) != [])
    check("a title alone is enough",
          builder.validate({"kind": "embed", "embed": {"title": "Hi"}}) == [])

    problems = builder.validate({
        "kind": "embed",
        "embed": {"title": "x" * 300, "description": "ok"},
    })
    check("an over-long title is caught", problems != [], str(problems))

    problems = builder.validate({
        "kind": "embed",
        "embed": {"title": "Hi", "fields": [{"name": "", "value": "x"}]},
    })
    check("a field without a name is caught", problems != [], str(problems))
    check("the message names the field number",
          any("Feld 1" in p for p in problems), str(problems))

    problems = builder.validate({
        "kind": "embed",
        "embed": {"title": "Hi", "fields": [{"name": "n", "value": "v"}] * 30},
    })
    check("more than 25 fields is caught", problems != [], str(problems))

    # Discord counts the whole embed together, which is easy to miss.
    problems = builder.validate({
        "kind": "embed",
        "embed": {
            "title": "x" * 200, "description": "y" * 4000,
            "fields": [{"name": "n" * 200, "value": "v" * 1000}] * 3,
        },
    })
    check("the combined 6000-character limit is caught",
          any("insgesamt" in p for p in problems), str(problems))

    problems = builder.validate({
        "kind": "embed", "embed": {"title": "Hi", "image": "nicht-mal-ein-link"},
    })
    check("an image that is not a URL is caught", problems != [], str(problems))

    # ══ Validation: Components V2 ═════════════════════════════════
    check("a V2 message with no blocks is caught",
          builder.validate({"kind": "v2", "blocks": []}) != [])

    check("only dividers is caught",
          builder.validate({
              "kind": "v2", "blocks": [{"type": "divider"}, {"type": "divider"}],
          }) != [])

    check("a text block is enough",
          builder.validate({
              "kind": "v2", "blocks": [{"type": "text", "text": "Hallo"}],
          }) == [])

    problems = builder.validate({
        "kind": "v2", "blocks": [{"type": "text", "text": ""}],
    })
    check("an empty text block is caught", problems != [], str(problems))

    problems = builder.validate({
        "kind": "v2",
        "blocks": [{"type": "buttons", "buttons": [{"label": "Hi", "url": "kein-link"}]}],
    })
    check("a button without a proper link is caught", problems != [], str(problems))
    check("the reason explains why a link is needed",
          any("täte nichts" in p or "https" in p for p in problems), str(problems))

    problems = builder.validate({
        "kind": "v2",
        "blocks": [{"type": "buttons", "buttons": [{"label": "", "url": "https://x.de"}]}],
    })
    check("a button without a label is caught", problems != [], str(problems))

    problems = builder.validate({
        "kind": "v2", "blocks": [{"type": "image", "url": "irgendwas"}],
    })
    check("an image block without a URL is caught", problems != [], str(problems))

    problems = builder.validate({"kind": "v2", "blocks": [{"type": "quatsch"}]})
    check("an unknown block type is caught", problems != [], str(problems))

    check("several problems are reported at once, not one at a time",
          len(builder.validate({
              "kind": "embed",
              "embed": {
                  "title": "x" * 300,
                  "fields": [{"name": "", "value": ""}],
                  "image": "kaputt",
              },
          })) >= 3)

    # ══ Colours ═══════════════════════════════════════════════════
    check("a #rrggbb colour is understood", builder.parse_colour("#5865f2") == 0x5865F2)
    check("a colour without the hash works", builder.parse_colour("5865f2") == 0x5865F2)
    check("an integer passes through", builder.parse_colour(0x112233) == 0x112233)
    check("nonsense falls back", builder.parse_colour("blau") == 0x5865F2)

    # ══ Building ══════════════════════════════════════════════════
    built = builder.build({"kind": "text", "content": "Hallo"})
    check("a text message builds to content",
          built.get("content") == "Hallo" and "embed" not in built, str(built.keys()))

    built = builder.build({
        "kind": "embed", "content": "@hier",
        "embed": {"title": "T", "description": "D", "color": "#ff0000",
                  "fields": [{"name": "n", "value": "v", "inline": True}]},
    })
    check("an embed builds", built.get("embed") is not None)
    check("the text above the embed survives", built.get("content") == "@hier")
    check("the colour is applied", built["embed"].color.value == 0xFF0000)
    check("fields are carried over", len(built["embed"].fields) == 1)

    built = builder.build({
        "kind": "v2", "color": "#00ff00",
        "blocks": [
            {"type": "text", "text": "Oben"},
            {"type": "divider"},
            {"type": "buttons", "buttons": [{"label": "Los", "url": "https://x.de"}]},
        ],
    })
    check("a V2 layout builds to a view",
          built.get("view") is not None and "content" not in built,
          str(built.keys()))
    rendered = str(built["view"].to_components())
    check("the V2 text is in the layout", "Oben" in rendered, rendered[:100])
    check("the button is in the layout", "Los" in rendered, rendered[:200])

    # A V2 layout must never carry content — Discord rejects that combo.
    check("a V2 message carries neither content nor embed",
          set(built.keys()) == {"view"}, str(built.keys()))

    # ══ The API ═══════════════════════════════════════════════════
    r = client.post(f"{base}/check", json={"kind": "text", "content": "Hi"})
    check("the check endpoint says ok", r.json()["ok"] is True, r.text[:120])

    r = client.post(f"{base}/check", json={"kind": "text", "content": ""})
    check("the check endpoint reports problems",
          r.json()["ok"] is False and r.json()["problems"], r.text[:120])
    check("it also hands back the limits for the editor",
          "content" in r.json()["limits"], str(r.json()["limits"])[:80])

    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "Hallo Welt", "channel_id": CHANNEL,
    })
    check("a text message can be sent", r.status_code == 200, r.text[:160])
    check("it really reached the channel", len(guild.channel.sent) == 1)
    check("message ids come back as strings",
          isinstance(r.json()["message_id"], str))

    # Mentions must be neutralised unless asked for.
    sent = guild.channel.sent[-1]
    check("mentions are suppressed by default",
          sent.get("allowed_mentions") is not None,
          str(sent.get("allowed_mentions")))

    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "@everyone", "channel_id": CHANNEL,
        "allow_mentions": True,
    })
    check("mentions can be switched on deliberately",
          guild.channel.sent[-1].get("allowed_mentions") is None,
          str(guild.channel.sent[-1].get("allowed_mentions")))

    r = client.post(f"{base}/send", json={
        "kind": "embed", "channel_id": CHANNEL,
        "embed": {"title": "Regeln", "description": "Sei nett."},
    })
    check("an embed can be sent", r.status_code == 200, r.text[:160])
    check("the embed arrived", guild.channel.sent[-1].get("embed") is not None)

    r = client.post(f"{base}/send", json={
        "kind": "v2", "channel_id": CHANNEL,
        "blocks": [{"type": "text", "text": "Karte"}],
    })
    check("a V2 layout can be sent", r.status_code == 200, r.text[:160])
    check("the layout arrived", guild.channel.sent[-1].get("view") is not None)

    # Bad input is refused before Discord ever sees it.
    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "", "channel_id": CHANNEL,
    })
    check("an empty message is refused with a reason",
          r.status_code == 400 and "leer" in r.json()["detail"], r.text[:140])

    r = client.post(f"{base}/send", json={"kind": "text", "content": "x"})
    check("sending without a channel is refused", r.status_code == 400)

    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "x", "channel_id": "999",
    })
    check("an unknown channel gives 404", r.status_code == 404)

    # Permissions are checked before sending.
    guild.channel.can_send = False
    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "x", "channel_id": CHANNEL,
    })
    check("a channel the bot cannot write in is refused with a reason",
          r.status_code == 403 and "schreiben" in r.json()["detail"], r.text[:140])
    guild.channel.can_send = True

    guild.channel.can_embed = False
    r = client.post(f"{base}/send", json={
        "kind": "embed", "channel_id": CHANNEL, "embed": {"title": "x"},
    })
    check("a missing 'embed links' permission is caught up front",
          r.status_code == 403 and "einbetten" in r.json()["detail"], r.text[:140])
    guild.channel.can_embed = True

    # Pinning.
    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "Angepinnt", "channel_id": CHANNEL, "pin": True,
    })
    pinned = guild.channel.messages[int(r.json()["message_id"])]
    check("a message can be pinned on send", pinned.pinned is True)

    # ══ Editing ═══════════════════════════════════════════════════
    r = client.post(f"{base}/send", json={
        "kind": "text", "content": "Tippfehlr", "channel_id": CHANNEL,
    })
    message_id = r.json()["message_id"]

    r = client.post(f"{base}/edit", json={
        "kind": "text", "content": "Tippfehler behoben",
        "channel_id": CHANNEL, "message_id": message_id,
    })
    check("a message can be edited", r.status_code == 200, r.text[:160])

    edited = guild.channel.messages[int(message_id)]
    check("the edit reached Discord", len(edited.edits) == 1, str(edited.edits))
    check("the new text is in the edit",
          edited.edits[0].get("content") == "Tippfehler behoben", str(edited.edits[0]))
    # Switching away from an embed has to clear the old one, otherwise it
    # just sits there next to the new text.
    check("an edit clears whatever the message had before",
          edited.edits[0].get("embeds") == [], str(edited.edits[0]))

    # Somebody else's message cannot be edited.
    foreign = FakeMessage(6000, author_id=42)
    guild.channel.messages[6000] = foreign
    r = client.post(f"{base}/edit", json={
        "kind": "text", "content": "x", "channel_id": CHANNEL, "message_id": "6000",
    })
    check("a message from somebody else is refused with a reason",
          r.status_code == 400 and "nicht vom Bot" in r.json()["detail"],
          r.text[:160])

    r = client.post(f"{base}/edit", json={
        "kind": "text", "content": "x", "channel_id": CHANNEL, "message_id": "123",
    })
    check("editing a missing message gives 404", r.status_code == 404)

    # Reading a message back.
    r = client.get(f"{base}/fetch?channel_id={CHANNEL}&message_id={message_id}")
    check("a message can be read back", r.status_code == 200, r.text[:140])
    check("it says the message belongs to the bot", r.json()["is_ours"] is True)

    withbuttons = FakeMessage(7000)
    withbuttons.components = ["something"]
    guild.channel.messages[7000] = withbuttons
    r = client.get(f"{base}/fetch?channel_id={CHANNEL}&message_id=7000")
    check("a message with buttons is marked as not re-editable",
          r.json()["editable"] is False, r.text[:140])
    check("and it says why", bool(r.json()["note"]), r.json()["note"])

    asyncio.run(db_manager.close_all())

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
