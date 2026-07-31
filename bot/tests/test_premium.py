#!/usr/bin/env python3
"""
Premium licence keys.

The chain: a team member mints a key with /key on the support server,
it arrives by DM, the buyer redeems it in the dashboard, and the
template bot asks us whether that Discord account has premium.

Money is involved, so the checks here are about the ways it could be
abused rather than the happy path:

  * a key must bind to one account and stay there
  * keys are stored hashed, so a stolen database activates nothing
  * the template bot's endpoint needs its own token and is read-only
  * the dashboard cannot redeem onto somebody else's account
  * /key refuses to run off the support server or for non-staff

    python3 tests/test_premium.py
"""

import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

# A fresh directory per run: leftovers from an earlier run would make
# "already used" pass for the wrong reason.
_TMP = tempfile.mkdtemp()
os.chdir(_TMP)
os.makedirs("db", exist_ok=True)
os.environ["PREMIUM_KEY_PEPPER"] = "test-pepper"
os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

ALICE = 1303627964734246944
BOB = 1033826242270609449

failures: list[str] = []


def check(name, ok, extra=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra and not ok else ""))
    if not ok:
        failures.append(name)


def test_keys(store):
    print("\nMinting and redeeming")

    made = store.create_key(created_by=ALICE, duration_days=30)
    key = made["key"]

    raw = store.normalise(key)
    check("a key is 16 characters", len(raw) == 16, str(len(raw)))
    check("it is grouped for reading", key.count("-") == 3, key)
    check("no ambiguous characters",
          not set(raw) & set("IO01U"), key)

    check("nobody has premium yet", store.status(ALICE)["premium"] is False)

    result = store.redeem(key, ALICE)
    check("the key redeems", result["ok"] is True, str(result))
    check("premium is now active", store.status(ALICE)["premium"] is True)

    # Typing it back in is someone checking it worked, not an error.
    again = store.redeem(key, ALICE)
    check("the same account may re-enter its own key", again["ok"] is True)
    check("and it is reported as already redeemed", again.get("already") is True)

    stolen = store.redeem(key, BOB)
    check("a second account is refused", stolen["ok"] is False)
    check("with a clear reason", stolen.get("error") == "already_used", str(stolen))
    check("and gains nothing", store.status(BOB)["premium"] is False)

    print("\nInput the way people actually type it")
    messy = store.create_key(created_by=ALICE, duration_days=0)["key"]
    variant = messy.lower().replace("-", " ")
    check("lowercase and spaces still work",
          store.redeem(variant, BOB)["ok"] is True, variant)
    check("a lifetime key never expires",
          store.status(BOB)["lifetime"] is True)

    print("\nBad keys")
    check("an unknown key is refused",
          store.redeem("ABCD-EFGH-JKLM-NPQR", 555)["error"] == "unknown")
    check("a short key is refused as malformed",
          store.redeem("ABCD", 555)["error"] == "invalid_format")
    check("an empty key is refused",
          store.redeem("", 555)["error"] == "invalid_format")

    print("\nRevoking")
    third = store.create_key(created_by=ALICE, duration_days=30)["key"]
    store.redeem(third, 777)
    check("premium is active before revoking", store.status(777)["premium"] is True)
    check("revoke reports success", store.revoke(third) is True)
    check("premium is gone afterwards", store.status(777)["premium"] is False)
    check("revoking an unknown key reports failure",
          store.revoke("ABCD-EFGH-JKLM-NPQR") is False)

    print("\nThe database never holds a usable key")
    blob = open(os.path.join("db", "premium.db"), "rb").read().decode("latin1")
    check("the plaintext key is absent", store.normalise(key) not in blob,
          "a stolen database would hand out premium")
    check("the formatted key is absent too", key not in blob)

    print("\nExpiry")
    import sqlite3
    import time
    expired = store.create_key(created_by=ALICE, duration_days=1)["key"]
    store.redeem(expired, 888)
    check("active while valid", store.status(888)["premium"] is True)
    with sqlite3.connect(store.DB_PATH) as conn:
        conn.execute(
            "UPDATE premium_keys SET expires_at = ? WHERE key_hash = ?",
            (int(time.time()) - 60, store.hash_key(expired)),
        )
    check("an expired key stops counting", store.status(888)["premium"] is False)


def test_api(store):
    print("\nAPI")

    from fastapi.testclient import TestClient
    from api import dependencies as dep
    from api.server import create_app

    class Bot:
        user = type("U", (), {"id": 1})()

        def get_guild(self, _gid):
            return None

    dep.set_bot(Bot())
    client = TestClient(create_app())
    base = "/api/v1/premium"

    key = store.create_key(created_by=ALICE, duration_days=30)["key"]

    # The template bot's endpoint.
    os.environ.pop("PREMIUM_PARTNER_TOKEN", None)
    r = client.get(f"{base}/check/{ALICE}")
    check("without a partner token the check is disabled",
          r.status_code == 503, str(r.status_code))

    os.environ["PREMIUM_PARTNER_TOKEN"] = "partner-secret"
    r = client.get(f"{base}/check/{ALICE}")
    check("a missing token is rejected", r.status_code == 401, str(r.status_code))

    r = client.get(f"{base}/check/{ALICE}", headers={"X-Partner-Token": "wrong"})
    check("a wrong token is rejected", r.status_code == 401, str(r.status_code))

    r = client.get(f"{base}/check/{ALICE}", headers={"X-Partner-Token": "partner-secret"})
    check("the right token is accepted", r.status_code == 200, r.text[:120])

    # Redeeming through the API.
    r = client.post(f"{base}/redeem", json={"user_id": str(BOB), "key": key})
    check("a key can be redeemed", r.status_code == 200, r.text[:160])

    r = client.get(f"{base}/check/{BOB}", headers={"X-Partner-Token": "partner-secret"})
    check("and the template bot sees it",
          r.json().get("premium") is True, r.text[:160])

    r = client.post(f"{base}/redeem", json={"user_id": str(ALICE), "key": key})
    check("the same key cannot be moved to another account",
          r.status_code == 400, r.text[:160])
    check("and the message says why",
          "anderen Konto" in r.text, r.text[:200])

    r = client.post(f"{base}/redeem", json={"user_id": "not-a-number", "key": key})
    check("a nonsense user id is refused", r.status_code == 400, str(r.status_code))

    r = client.post(f"{base}/redeem", json={"user_id": str(ALICE), "key": ""})
    check("an empty key is refused", r.status_code == 400, str(r.status_code))

    r = client.get(f"{base}/me/{BOB}")
    body = r.json()
    check("the dashboard sees its own status",
          body["template_bot"]["premium"] is True, r.text[:160])
    check("the main bot is honestly marked coming soon",
          body["main_bot"]["coming_soon"] is True
          and body["main_bot"]["premium"] is False, r.text[:160])

    r = client.get(f"{base}/keys")
    listed = r.json().get("keys", [])
    check("keys can be listed", r.status_code == 200 and len(listed) > 0)
    check("the listing never contains a usable key",
          all("key" not in row or row.get("key") is None for row in listed)
          and store.normalise(key) not in r.text,
          "the admin list leaks keys")


def test_command_guards():
    print("\n/key guards")

    src = open(os.path.join(BOT, "cogs", "commands", "premium.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    check("it is limited to the support server",
          "ctx.guild.id != HOME_GUILD_ID" in body)
    check("and to the owner list", "OWNER_IDS" in body)
    check("the key is sent by DM, not into the channel",
          "ctx.author.send" in body)
    check("a closed DM is handled",
          "discord.Forbidden" in body,
          "a user with DMs off would crash the command")
    check("it refuses to run without the pepper",
          "PEPPER_ENV" in body,
          "keys would be hashed without a pepper and break later")


def test_proxy_binding():
    print("\nDashboard proxy")

    path = os.path.join(
        os.path.dirname(BOT), "dashboard", "app", "api", "bot", "[...path]", "route.ts"
    )
    src = open(path, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))

    check("the premium scope is handled", 'scope === "premium"' in body)
    check("redeeming is pinned to the session user",
          'parsed.user_id = actorId' in body,
          "a browser could redeem onto another account")
    check("the template bot's check is not reachable from a browser",
          'rest[0] === "check"' in body)
    check("key management is staff only",
          'rest[0] === "keys"' in body and "Admins only." in body)


def run():
    from utils import premium_store as store

    test_keys(store)
    test_api(store)
    test_command_guards()
    test_proxy_binding()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
