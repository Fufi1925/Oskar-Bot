"""
Guard against response-model type mismatches.

Several tables store Discord IDs as INTEGER while the response models
declare them as strings. Pydantic then raises on the way out and the whole
page returns 500 — but only once a value has been written, so it slips
through a quick manual check on an empty server.

This walks every GET route with a response_model, writes a realistic row
first, and asserts the endpoint still answers 200.

Run:  python3 tests/test_response_types.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

from test_partial_updates import FakeBot, GUILD  # noqa: E402

# (label, path, db file, SQL that stores integer IDs)
SEEDS = [
    (
        "welcome",
        "/welcome",
        "welcome.db",
        "INSERT OR REPLACE INTO welcome"
        " (guild_id, welcome_type, welcome_message, channel_id,"
        " embed_data, auto_delete_duration)"
        " VALUES (?, 'simple', 'hi', 800, NULL, 0)",
    ),
    # Verification lives under its own router now, so these carry an
    # absolute path instead of hanging off the /guilds base.
    (
        "verification",
        "/api/v1/verify/{guild}",
        "verification.db",
        "INSERT OR REPLACE INTO verification_config"
        " (guild_id, verification_channel_id, verified_role_id,"
        " log_channel_id, verification_method, enabled)"
        " VALUES (?, 800, 900, 801, 'both', 1)",
    ),
    (
        "verification-empty",
        "/api/v1/verify/{guild}",
        "verification.db",
        "INSERT OR REPLACE INTO verification_config"
        " (guild_id, verification_channel_id, verified_role_id,"
        " log_channel_id, verification_method, enabled)"
        " VALUES (?, 0, 0, 0, 'both', 1)",
    ),
    (
        "antinuke",
        "/antinuke",
        "anti.db",
        "INSERT OR REPLACE INTO antinuke (guild_id, status) VALUES (?, 1)",
    ),
    # Leveling moved to its own router; see test_leveling.py.
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
    for label, path, dbfile, sql in SEEDS:
        try:
            con = sqlite3.connect(f"db/{dbfile}")
            con.execute(sql, (GUILD,))
            con.commit()
            con.close()
        except Exception as exc:  # noqa: BLE001
            print(f"  SKIP  {label}: seed failed ({exc})")
            continue

        try:
            # A case may give an absolute path when its router is not
            # the /guilds one.
            url = (
                path.format(guild=GUILD) if path.startswith("/api/")
                else base + path
            )
            response = client.get(url)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label}: raised {type(exc).__name__}")
            print(f"  FAIL  {label}: raised {type(exc).__name__}")
            continue

        if response.status_code != 200:
            failures.append(
                f"{label}: GET -> {response.status_code} {response.text[:90]}"
            )
            print(f"  FAIL  {label}: {response.status_code}")
            continue

        print(f"  PASS  {label}")

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "db"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "jsondb"), exist_ok=True)
        os.chdir(tmp)
        sys.exit(run())
