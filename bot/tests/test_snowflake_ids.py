"""
Discord IDs must survive the round trip exactly.

Snowflakes are 64-bit. JavaScript numbers lose precision past 2^53, so
`Number("1327995167345819721")` silently becomes 1327995167345819600 —
off by 121. The dashboard used to convert IDs that way before sending
them, which stored a channel that does not exist: the save succeeded, the
picker showed nothing, and selecting a channel looked broken.

The frontend now keeps IDs as strings. These tests pin down the backend
half: a string ID has to arrive intact, and a corrupted one must not be
mistaken for the real thing.

Run:  python3 tests/test_snowflake_ids.py
"""

import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

GUILD = 111
# A real 19-digit channel id, and what JS Number() turns it into.
REAL_ID = "1327995167345819721"
JS_MANGLED = 1327995167345819600


def run():
    import api.dependencies as dep
    from api.schemas import LevelingUpdate, TicketUpdate
    from api.server import create_app
    from fastapi.testclient import TestClient

    class FakeBot:
        user = type("U", (), {"name": "Bot", "id": 1})()
        guilds: list = []

        def get_guild(self, _gid):
            return None

        def get_cog(self, _n):
            return None

    dep.set_bot(FakeBot())
    client = TestClient(create_app())

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # --- the corruption itself -----------------------------------------
    check("the mangled value really differs from the real one",
          str(JS_MANGLED) != REAL_ID)
    check("python parses the id without loss",
          str(int(REAL_ID)) == REAL_ID)

    # --- pydantic coercion ---------------------------------------------
    model = LevelingUpdate(level_up_channel=REAL_ID)
    check("a string id survives LevelingUpdate",
          str(model.level_up_channel) == REAL_ID, str(model.level_up_channel))

    ticket = TicketUpdate(staff_roles=[REAL_ID, "900"])
    check("string role ids survive TicketUpdate",
          str(ticket.staff_roles[0]) == REAL_ID, str(ticket.staff_roles))

    # --- through the ticket panel API ----------------------------------
    base = f"/api/v1/tickets/{GUILD}"
    panel_id = client.post(base + "/panels", json={"name": "T"}).json()["panel_id"]

    client.patch(f"{base}/panels/{panel_id}", json={"channel_id": REAL_ID})
    stored = client.get(base + "/panels").json()["panels"][0]["channel_id"]
    check("a channel id round trips through the panel API",
          stored == REAL_ID, f"{stored} != {REAL_ID}")

    client.patch(f"{base}/server", json={"staff_roles": [REAL_ID]})
    roles = client.get(base + "/panels").json()["server"]["staff_roles"]
    check("a role id round trips through the server settings",
          roles == [REAL_ID], str(roles))

    client.put(
        f"{base}/panels/{panel_id}/categories",
        json={"name": "Support", "staff_roles": [REAL_ID],
              "discord_category_id": REAL_ID},
    )
    category = client.get(base + "/panels").json()["panels"][0]["categories"][0]
    check("a category keeps its role id",
          category["staff_roles"] == [REAL_ID], str(category["staff_roles"]))
    check("a category keeps its channel id",
          category["discord_category_id"] == REAL_ID,
          str(category["discord_category_id"]))

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
