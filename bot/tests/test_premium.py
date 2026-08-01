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

    class FakeUser:
        def __init__(self, uid):
            self.id = uid
            self.name = f"user{uid}"
            self.display_name = f"User {uid}"
            self.sent: list[str] = []

        async def send(self, content=None, **kw):
            self.sent.append(content or "")

    class Bot:
        user = type("U", (), {"id": 1})()

        def __init__(self):
            self.users = {}

        def get_guild(self, _gid):
            return None

        def get_user(self, uid):
            # Mirrors discord.py: only cached users, None otherwise.
            return self.users.get(int(uid))

        async def fetch_user(self, uid):
            return self.users.get(int(uid))

    bot = Bot()
    bot.users[BOB] = FakeUser(BOB)
    dep.set_bot(bot)
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

    os.environ["PARTNER_BOT_CLIENT_ID"] = "1530742522589089952"
    r = client.get(f"{base}/me/{BOB}")
    body = r.json()
    check("the dashboard sees its own status",
          body["template_bot"]["premium"] is True, r.text[:160])
    invite = body.get("template_invite", "")
    check("an invite link for the template bot is offered",
          "oauth2/authorize" in invite and "1530742522589089952" in invite,
          invite[:120])
    # Premium follows the account, so the link must not pin one server.
    check("the invite does not preselect a server",
          "guild_id" not in invite,
          "the buyer could only add the bot to one place")
    check("the main bot is honestly marked coming soon",
          body["main_bot"]["coming_soon"] is True
          and body["main_bot"]["premium"] is False, r.text[:160])

    print("\nMinting from the dashboard")

    # Without a pepper the keys would be hashed unsafely, and setting one
    # later would invalidate everything minted before.
    saved = os.environ.pop("PREMIUM_KEY_PEPPER")
    r = client.post(f"{base}/keys", json={"days": 30})
    check("minting is refused without a pepper", r.status_code == 503,
          str(r.status_code))
    os.environ["PREMIUM_KEY_PEPPER"] = saved

    r = client.post(f"{base}/keys", json={"days": 30})
    minted = r.json()
    check("a key can be minted", r.status_code == 200, r.text[:160])
    check("the key is returned exactly once",
          len(store.normalise(minted.get("key", ""))) == 16, r.text[:160])
    check("with nobody to DM it is reported honestly",
          minted.get("delivery") == "none", r.text[:160])

    r = client.post(f"{base}/keys", json={"days": 7, "user_id": str(BOB)})
    sent = r.json()
    check("a key is delivered by DM", sent.get("delivery") == "sent", r.text[:160])
    check("and the DM carries the key",
          sent["key"] in bot.users[BOB].sent[-1],
          "the DM went out without the key in it")

    r = client.post(f"{base}/keys", json={"days": 30, "user_id": "999999999999999999"})
    check("an unknown recipient is reported, key still made",
          r.json().get("delivery") == "unknown_user"
          and r.json().get("key"), r.text[:200])

    r = client.post(f"{base}/keys", json={"days": 5000})
    check("an absurd duration is refused", r.status_code == 400, str(r.status_code))
    r = client.post(f"{base}/keys", json={"days": -1})
    check("a negative duration is refused", r.status_code == 400, str(r.status_code))

    r = client.get(f"{base}/keys")
    listed = r.json().get("keys", [])
    check("keys can be listed", r.status_code == 200 and len(listed) > 0)
    check("the listing reports setup state",
          "pepper_set" in r.json() and "partner_token_set" in r.json())
    check("and the role state", "role" in r.json())

    print("\nRevoking from the dashboard")
    target = next(k for k in listed if k.get("redeemed_by"))
    r = client.post(f"{base}/revoke", json={"key_hash": target["key_hash"]})
    check("revoke by hash works", r.status_code == 200, r.text[:160])
    r = client.post(f"{base}/revoke",
                    json={"key_hash": target["key_hash"], "undo": True})
    check("and can be undone", r.status_code == 200
          and "aufgehoben" in r.text, r.text[:160])
    r = client.post(f"{base}/revoke", json={"key_hash": "nope"})
    check("an unknown hash is refused", r.status_code == 404, str(r.status_code))
    check("the listing never contains a usable key",
          all("key" not in row or row.get("key") is None for row in listed)
          and store.normalise(key) not in r.text,
          "the admin list leaks keys")


def test_key_commands_are_gone():
    print("\n/key is gone — the dashboard owns this now")

    src = open(os.path.join(BOT, "cogs", "commands", "premium.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    check("no /key command group", 'name="key"' not in body,
          "the chat command is back")
    check("no key subcommands", "@key.command" not in body)
    check("the cog registers no commands at all",
          "hybrid_command" not in body and "hybrid_group" not in body)


def test_role_sync(store):
    print("\nThe premium role follows the licence")

    src = open(os.path.join(BOT, "cogs", "commands", "premium.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    check("there is a timer", "@tasks.loop" in body,
          "nothing fires when a licence expires, so a timer is required")
    check("the role is added", "add_roles" in body)
    check("and removed again", "remove_roles" in body,
          "an expired customer would keep the role forever")
    check("a role above the bot is refused",
          "top_role" in body,
          "Discord rejects those and the loop would spin on 403s")
    check("the loop cannot die", "except Exception" in body)

    # premium_user_ids is what decides who holds the role.
    import time as _time
    import sqlite3

    fresh = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(fresh, 4001)
    check("an active licence is listed", "4001" in store.premium_user_ids())

    gone = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(gone, 4002)
    with sqlite3.connect(store.DB_PATH) as conn:
        conn.execute(
            "UPDATE premium_keys SET expires_at = ? WHERE key_hash = ?",
            (int(_time.time()) - 60, store.hash_key(gone)),
        )
    check("an expired licence drops out", "4002" not in store.premium_user_ids(),
          "the role would never come off")

    banned = store.create_key(created_by=1, duration_days=0)["key"]
    store.redeem(banned, 4003)
    store.revoke(banned)
    check("a revoked licence drops out", "4003" not in store.premium_user_ids())

    never = store.create_key(created_by=1, duration_days=30)["key"]
    check("an unredeemed key grants nobody the role",
          store.premium_user_ids() and never not in store.premium_user_ids())

    print("\nRevoking can be undone")
    key_hash = store.hash_key(banned)
    check("unrevoke reports success", store.unrevoke_hash(key_hash) is True)
    check("and premium comes back", "4003" in store.premium_user_ids(),
          "revoking the wrong row would be permanent")
    check("revoke by hash works too", store.revoke_hash(key_hash) is True)
    check("and takes it away again", "4003" not in store.premium_user_ids())


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


def test_dashboard_page():
    print("\nPremium page in the sidebar")

    dash = os.path.join(os.path.dirname(BOT), "dashboard")

    page = os.path.join(dash, "app", "dashboard", "premium", "page.tsx")
    check("the page exists", os.path.exists(page), page)

    src = open(page, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))
    check("it renders the premium panel", "<PremiumPanel />" in body)
    check("it is not cached", 'dynamic = "force-dynamic"' in body,
          "a stale page would show the wrong premium status")
    check("signed-out visitors are sent away", 'redirect("/dashboard")' in body)
    # A customer who bought a key is not staff. Gating this page behind
    # isAdmin would lock the buyer out of their own purchase.
    check("it is not limited to admins", "isAdmin" not in body,
          "customers could not reach the redeem field")

    layout = open(os.path.join(dash, "app", "dashboard", "layout.tsx"), encoding="utf-8").read()
    lbody = "\n".join(l for l in layout.splitlines() if not l.lstrip().startswith("//"))
    check("the sidebar links to it", '"/dashboard/premium"' in lbody)

    panel = open(os.path.join(dash, "components", "dashboard",
                              "premium-panel.tsx"), encoding="utf-8").read()
    pbody = "\n".join(l for l in panel.splitlines() if not l.lstrip().startswith("//"))
    check("the invite link is rendered", "template_invite" in pbody)
    # Offering it before a key is redeemed would advertise a bot the
    # visitor cannot use yet.
    check("only once premium is active",
          pbody.index("active ? (") < pbody.index("template_invite"),
          "the invite shows without premium")
    check("the admin panel can mint keys", "createPremiumKey" in pbody)
    check("and undo a revoke", "setRevoked" in pbody and "undo" in pbody)
    check("a fresh key is shown once", "fresh" in pbody)
    check("the role state is surfaced", "role?.ok" in pbody)

    # The sidebar splits into "inside a guild" and "top level". Premium is
    # account-wide, so it belongs to the second list, next to Admin Panel.
    tail = lbody.split('name: "Server", href: "/dashboard/guilds"')[-1]
    check("the link sits in the top-level menu",
          '"/dashboard/premium"' in tail,
          "it landed in the per-guild menu instead")


def run():
    from utils import premium_store as store

    test_keys(store)
    test_api(store)
    test_key_commands_are_gone()
    test_role_sync(store)
    test_proxy_binding()
    test_dashboard_page()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
