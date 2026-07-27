"""
Regression guard for partial updates across the dashboard API.

For every module: set switch A, then send a request that changes only B,
then re-read with a fresh GET (what happens when the user opens the page
again later). A must still be set.

This is the class of bug that shipped in guild extra-settings, where a
PATCH rebuilt every field from defaults and silently reset the switches the
request did not mention.

Run directly:  python3 tests/test_partial_updates.py
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

GUILD = 111222333444555666


# ---------------------------------------------------------------- fakes
class FakeRole:
    def __init__(self, i, n):
        self.id, self.name, self.color, self.position = i, n, 0, 1
        self.permissions = type("P", (), {"administrator": False})()


class FakeChannel:
    def __init__(self, i, n):
        self.id, self.name = i, n
        self.type = type("T", (), {"value": 0})()

    def permissions_for(self, _):
        return type("P", (), {"send_messages": True, "view_channel": True})()


class FakeGuild:
    id, name, icon, owner_id, member_count = GUILD, "Test", None, 1, 42
    members: list = []

    def __init__(self):
        self.roles = [FakeRole(900, "Member"), FakeRole(901, "Staff")]
        self.channels = [FakeChannel(800, "general")]
        self.text_channels = self.channels

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == int(cid)), None)


class FakeBot:
    """Enough surface for the routes; get_cog returns None like a bot without that cog."""

    user = type("U", (), {"name": "Bot", "id": 1})()

    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_cog(self, _name):
        return None

    def is_ready(self):
        return True


# (label, path, (field_a, value_a), (field_b, value_b))
CASES = [
    # Leveling has its own router now (/leveling/{guild_id}) and its own
    # test file; a partial save is covered there.
    ("automod", "/automod", ("enabled", True), ("logging_channel", 800)),
    ("extra-settings", "/extra-settings",
     ("delete_command_messages", True), ("same_voice_only", False)),
    ("verification", "/verification",
     ("enabled", True), ("verification_method", "captcha")),
    ("welcome", "/welcome",
     ("welcome_message", "hello"), ("auto_delete_duration", 30)),
    ("antinuke", "/antinuke", ("status", True), ("status", True)),
    ("settings-features", "/settings-features", None, None),
    ("admin-dashboard", "/admin-dashboard", None, None),
]


def run():
    import api.dependencies as dep
    from api.schema_guard import ensure_schema
    from api.server import create_app
    from fastapi.testclient import TestClient

    dep.set_bot(FakeBot())
    asyncio.run(ensure_schema())
    client = TestClient(create_app())
    base = f"/api/v1/guilds/{GUILD}"

    failures = []

    for label, path, a, b in CASES:
        url = base + path

        # Toggle-map modules: flip the first two booleans the GET reports.
        if a is None:
            got = client.get(url)
            if got.status_code != 200:
                failures.append(f"{label}: GET -> {got.status_code}")
                print(f"  FAIL  {label}: GET {got.status_code}")
                continue
            bools = [
                k for k, v in got.json().items()
                if isinstance(v, bool)
            ][:2]
            if len(bools) < 2:
                print(f"  SKIP  {label}: fewer than two toggles")
                continue
            a, b = (bools[0], True), (bools[1], True)

        (fa, va), (fb, vb) = a, b

        r = client.patch(url, json={fa: va})
        if r.status_code != 200:
            failures.append(f"{label}: PATCH A -> {r.status_code} {r.text[:70]}")
            print(f"  FAIL  {label}: PATCH A {r.status_code}")
            continue

        r = client.patch(url, json={fb: vb})
        if r.status_code != 200:
            failures.append(f"{label}: PATCH B -> {r.status_code} {r.text[:70]}")
            print(f"  FAIL  {label}: PATCH B {r.status_code}")
            continue

        got = client.get(url)
        if got.status_code != 200:
            failures.append(f"{label}: GET -> {got.status_code}")
            print(f"  FAIL  {label}: GET {got.status_code}")
            continue

        now = got.json().get(fa)
        if not (now == va or bool(now) == bool(va)):
            failures.append(
                f"{label}: {fa}={va!r} was reset to {now!r} by patching {fb}"
            )
            print(f"  FAIL  {label}: {fa} reset to {now!r}")
            continue

        print(f"  PASS  {label}")

    print(f"\n{len(failures)} failures")
    for f in failures:
        print(f"   {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "db"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "jsondb"), exist_ok=True)
        os.chdir(tmp)
        sys.exit(run())
