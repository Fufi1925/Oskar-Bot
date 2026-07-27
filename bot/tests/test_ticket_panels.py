"""
Multiple ticket panels per guild.

Two things this has to get right:

  * a legacy single-panel configuration must survive the schema change —
    it becomes panel #1 with its categories attached
  * every endpoint touches one section only, so saving the appearance
    cannot wipe the channel and switching tabs cannot lose the other half
    of the form (the old single PATCH did exactly that, and it also wrote
    a `staff_roles` column that did not exist, aborting the request)

Run:  python3 tests/test_ticket_panels.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

GUILD = 111222333444555666


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.sent = []
        self.deleted = []
        self._next = 7000

    def permissions_for(self, _member):
        return type("P", (), {"send_messages": True})()

    async def fetch_message(self, mid):
        raise Exception("gone")

    async def send(self, **kwargs):
        self._next += 1
        self.sent.append(kwargs)
        return type(
            "M", (), {"id": self._next, "jump_url": f"https://d/{self._next}"}
        )()


class FakeGuild:
    id, name = GUILD, "Test"

    def __init__(self):
        self.channel = FakeChannel(800, "support")
        self.me = object()

    def get_channel(self, cid):
        return self.channel if int(cid) == 800 else None


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


def seed_legacy():
    """A pre-migration configuration, exactly as the old code left it."""
    os.makedirs("db", exist_ok=True)
    con = sqlite3.connect("db/ticket.db")
    con.execute(
        "CREATE TABLE IF NOT EXISTS guild_configs ("
        " guild_id INTEGER PRIMARY KEY, panel_channel_id INTEGER,"
        " logging_channel_id INTEGER, panel_message_id INTEGER,"
        " panel_type TEXT, embed_title TEXT, embed_description TEXT,"
        " embed_color INTEGER, embed_image_url TEXT,"
        " embed_thumbnail_url TEXT, closed_category_id INTEGER)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ticket_categories ("
        " category_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,"
        " name TEXT NOT NULL, emoji TEXT, notified_roles TEXT,"
        " button_style INTEGER, discord_category_id INTEGER)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS open_tickets ("
        " channel_id INTEGER PRIMARY KEY, guild_id INTEGER, closed_at TEXT)"
    )
    con.execute(
        "INSERT INTO guild_configs (guild_id, panel_channel_id, panel_type,"
        " embed_title, embed_description, embed_color, logging_channel_id)"
        " VALUES (?, 800, 'button', 'Altes Panel', 'Beschreibung', 123456, 801)",
        (GUILD,),
    )
    con.executemany(
        "INSERT INTO ticket_categories (guild_id, name, emoji, notified_roles,"
        " button_style, discord_category_id) VALUES (?,?,?,?,?,?)",
        [
            (GUILD, "Support", "🎫", "900,901", 2, 700),
            (GUILD, "Bug", "🐛", "900", 4, 701),
        ],
    )
    con.commit()
    con.close()


def run():
    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient

    dep.set_bot(FakeBot())
    client = TestClient(create_app())
    base = f"/api/v1/tickets/{GUILD}"

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # --- migration ----------------------------------------------------
    body = client.get(f"{base}/panels").json()
    check("legacy config becomes one panel",
          len(body["panels"]) == 1, str(body))

    panel = body["panels"][0]
    check("panel keeps its channel", panel["channel_id"] == "800", str(panel))
    check("panel keeps its title",
          panel["embed_title"] == "Altes Panel", str(panel))
    check("categories are attached to it",
          len(panel["categories"]) == 2, str(panel["categories"]))
    check("category roles survive",
          panel["categories"][0]["staff_roles"] == ["900", "901"],
          str(panel["categories"][0]))
    check("server settings are read",
          body["server"]["logging_channel"] == "801", str(body["server"]))

    # running it again must not duplicate anything
    again = client.get(f"{base}/panels").json()
    check("migration is idempotent", len(again["panels"]) == 1, str(again))

    panel_id = panel["panel_id"]

    # --- the bug that lost half the form ------------------------------
    r = client.patch(f"{base}/server", json={"staff_roles": [900, 901]})
    check("saving global staff roles no longer errors",
          r.status_code == 200, f"-> {r.status_code} {r.text[:80]}")

    after = client.get(f"{base}/panels").json()
    check("global staff roles are stored",
          after["server"]["staff_roles"] == ["900", "901"],
          str(after["server"]))
    check("saving the server section keeps the panel channel",
          after["panels"][0]["channel_id"] == "800", str(after["panels"][0]))

    # --- partial updates ----------------------------------------------
    client.patch(f"{base}/panels/{panel_id}", json={"embed_title": "Neu"})
    after = client.get(f"{base}/panels").json()["panels"][0]
    check("editing the title keeps the channel",
          after["channel_id"] == "800" and after["embed_title"] == "Neu",
          str(after))
    check("editing the title keeps the categories",
          len(after["categories"]) == 2, str(after["categories"]))

    # --- a second panel ------------------------------------------------
    r = client.post(f"{base}/panels", json={"name": "Bewerbungen"})
    second = r.json()["panel_id"]
    check("a second panel can be created", r.status_code == 200 and second)

    body = client.get(f"{base}/panels").json()
    check("both panels exist", len(body["panels"]) == 2, str(len(body["panels"])))

    # categories are per panel
    client.put(
        f"{base}/panels/{second}/categories",
        json={"name": "Moderator", "emoji": "🛡️", "staff_roles": [902]},
    )
    body = client.get(f"{base}/panels").json()
    first_p = next(p for p in body["panels"] if p["panel_id"] == panel_id)
    second_p = next(p for p in body["panels"] if p["panel_id"] == second)
    check("the new category lands on the second panel",
          len(second_p["categories"]) == 1, str(second_p["categories"]))
    check("the first panel is untouched",
          len(first_p["categories"]) == 2, str(first_p["categories"]))

    # --- posting --------------------------------------------------------
    r = client.post(f"{base}/panels/{second}/send", json={})
    check("posting without a channel is refused",
          r.status_code == 400, f"-> {r.status_code}")

    client.patch(f"{base}/panels/{second}", json={"channel_id": 800})
    r = client.post(f"{base}/panels/{second}/send", json={})
    check("posting works once channel and category are set",
          r.status_code == 200, f"-> {r.status_code} {r.text[:90]}")

    body = client.get(f"{base}/panels").json()
    second_p = next(p for p in body["panels"] if p["panel_id"] == second)
    check("the message id is stored", second_p["posted"] is True, str(second_p))

    # a panel with no categories must not post
    third = client.post(f"{base}/panels", json={"name": "Leer"}).json()["panel_id"]
    client.patch(f"{base}/panels/{third}", json={"channel_id": 800})
    r = client.post(f"{base}/panels/{third}/send", json={})
    check("a panel without categories is refused",
          r.status_code == 400, f"-> {r.status_code}")

    # --- deleting --------------------------------------------------------
    r = client.delete(f"{base}/panels/{third}")
    check("a panel can be deleted", r.status_code == 200)
    body = client.get(f"{base}/panels").json()
    check("only that panel went", len(body["panels"]) == 2, str(len(body["panels"])))

    cat_id = second_p["categories"][0]["category_id"]
    r = client.delete(f"{base}/categories/{cat_id}")
    check("a category can be deleted", r.status_code == 200)

    r = client.delete(f"{base}/panels/999999")
    check("deleting an unknown panel gives 404", r.status_code == 404)

    # --- the channel picker ---------------------------------------------
    # A PATCH saved the channel but the reload right after it crashed with
    # "no such table: guild_configs" when the cog had not run yet, so the
    # picker snapped back and selecting a channel looked broken.
    fresh = client.post(f"{base}/panels", json={"name": "Kanaltest"}).json()["panel_id"]
    client.patch(f"{base}/panels/{fresh}", json={"channel_id": 800})
    got = client.get(f"{base}/panels").json()
    target = next(p for p in got["panels"] if p["panel_id"] == fresh)
    check("selecting a channel is stored", target["channel_id"] == "800", str(target))

    client.patch(f"{base}/panels/{fresh}", json={"embed_title": "Titel"})
    target = next(
        p for p in client.get(f"{base}/panels").json()["panels"]
        if p["panel_id"] == fresh
    )
    check("editing another field keeps the channel",
          target["channel_id"] == "800", str(target))

    # Clearing has to work too — null is "not sent" for most fields, but
    # the channel must be removable.
    client.patch(f"{base}/panels/{fresh}", json={"channel_id": None})
    target = next(
        p for p in client.get(f"{base}/panels").json()["panels"]
        if p["panel_id"] == fresh
    )
    check("the channel can be cleared again", target["channel_id"] is None, str(target))

    # --- dropdown vs buttons ---------------------------------------------
    client.patch(f"{base}/panels/{fresh}", json={"channel_id": 800,
                                                 "panel_type": "dropdown"})
    client.put(
        f"{base}/panels/{fresh}/categories",
        json={"name": "Frage", "emoji": "❓", "staff_roles": []},
    )
    target = next(
        p for p in client.get(f"{base}/panels").json()["panels"]
        if p["panel_id"] == fresh
    )
    check("panel type is stored", target["panel_type"] == "dropdown", str(target))

    guild = FakeBot().guilds[0]
    r = client.post(f"{base}/panels/{fresh}/send", json={})
    check("a dropdown panel posts", r.status_code == 200, f"-> {r.status_code} {r.text[:80]}")

    client.patch(f"{base}/panels/{fresh}", json={"panel_type": "button"})
    r = client.post(f"{base}/panels/{fresh}/send", json={})
    check("a button panel posts", r.status_code == 200, f"-> {r.status_code}")

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        os.makedirs("db", exist_ok=True)
        os.makedirs("jsondb", exist_ok=True)
        seed_legacy()
        sys.exit(run())
