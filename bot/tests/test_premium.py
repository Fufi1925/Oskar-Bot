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

import asyncio
import os
import re
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
            self.views: list = []

        async def send(self, content=None, view=None, **kw):
            # The DM is a Components V2 view, not text. Flattening it
            # here keeps the assertion about *what the buyer sees*
            # rather than about which argument was used.
            self.views.append(view)
            if view is not None:
                parts: list[str] = []

                def walk(items):
                    for item in items:
                        if item.get("type") == 10:
                            parts.append(item.get("content", ""))
                        if "components" in item:
                            walk(item["components"])

                walk(view.to_components())
                self.sent.append("\n".join(parts))
            else:
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
    # Der Hauptbot hat jetzt echtes Premium: es schaltet den
    # Design-Reiter frei (Server-Nickname, -Avatar, -Banner).
    #
    # Vorher stand hier fest `{"premium": False, "coming_soon": True}`.
    # Das war richtig, solange es nichts zu kaufen gab -- es haette
    # aber auch dann noch "demnaechst" gemeldet, wenn laengst Keys im
    # Umlauf sind.
    check("the main bot reports a real premium state",
          "coming_soon" not in body["main_bot"]
          and body["main_bot"]["premium"] is False,
          r.text[:160])
    check("and it is answered by the same place as the template bot",
          "product" in body["main_bot"]
          and body["main_bot"]["product"] == "main_bot",
          str(body["main_bot"])[:160])

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

    dm = bot.users[BOB].sent[-1]
    check("and the DM carries the key", sent["key"] in dm,
          "the DM went out without the key in it")
    # What was actually sent, not just what _key_dm can produce: the
    # route could always go back to a plain string.
    check("the DM that goes out is a V2 view",
          bot.users[BOB].views[-1] is not None,
          "a plain text message was sent instead of a panel")
    check("with the bot's emojis in it",
          dm.count("<:") + dm.count("<a:") >= 4,
          "the delivered DM has no bot emojis")

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
    # Nicht die Liste woertlich vergleichen -- sie waechst. Geprueft
    # wird, dass jeder dieser Pfade drinsteht: eine exakte Zeichenkette
    # schlug fehl, sobald „trials" dazukam, obwohl der Schutz gerade
    # erweitert wurde.
    gate = re.search(r'\[((?:\s*"[a-z]+",?)+)\]\.includes\(rest\[0\]', body)
    geschuetzt = set(re.findall(r'"([a-z]+)"', gate.group(1))) if gate else set()
    fehlt = {"keys", "revoke", "delete", "purge"} - geschuetzt
    check("key management is staff only",
          not fehlt and "Admins only." in body,
          f"nicht hinter dem staff gate: {sorted(fehlt)}")
    # Die Probewochen gehoeren dazu: „zuruecksetzen" verschenkt Tage.
    check("trial management is staff only too",
          "trials" in geschuetzt,
          "resetting a trial hands out another free week")


def test_partner_reaches_the_api(store):
    """
    The reported bug: premium never activated in the template bot.

    The whole /api/v1 app sits behind verify_api_key, so a request
    carrying only X-Partner-Token was rejected with 401 before the route
    ever ran. The template bot has no reason to know the dashboard key —
    it is a different program — so the licence check authenticates with
    its own token instead.

    This test runs with DASHBOARD_API_KEY set, the way production is.
    Without that the old code passed by accident, because a missing key
    lets everything through.
    """
    print("\nThe template bot can reach the licence check")

    from fastapi.testclient import TestClient
    from api import dependencies as dep
    from api.server import create_app

    saved_key = os.environ.get("DASHBOARD_API_KEY")
    saved_keyless = os.environ.get("ALLOW_KEYLESS_API")
    os.environ["DASHBOARD_API_KEY"] = "dashboard-secret"
    os.environ.pop("ALLOW_KEYLESS_API", None)
    os.environ["PREMIUM_PARTNER_TOKEN"] = "partner-secret"

    try:
        class Bot:
            user = type("U", (), {"id": 1})()

            def get_guild(self, _gid):
                return None

            def get_user(self, _uid):
                return None

        dep.set_bot(Bot())
        client = TestClient(create_app())
        base = "/api/v1/premium"

        key = store.create_key(created_by=1, duration_days=30)["key"]
        store.redeem(key, 5150)

        r = client.get(f"{base}/check/5150",
                       headers={"X-Partner-Token": "partner-secret"})
        check("the partner token alone is enough", r.status_code == 200,
              f"{r.status_code} {r.text[:120]}")
        check("and premium is reported", r.json().get("premium") is True,
              r.text[:120])

        # The exception has to be narrow, or it becomes a way around the
        # dashboard key entirely.
        r = client.get(f"{base}/check/5150",
                       headers={"X-Partner-Token": "wrong"})
        check("a wrong partner token is still rejected", r.status_code == 401,
              str(r.status_code))

        r = client.get(f"{base}/check/5150")
        check("no token at all is rejected", r.status_code == 401,
              str(r.status_code))

        r = client.get(f"{base}/keys",
                       headers={"X-Partner-Token": "partner-secret"})
        check("the partner token opens no other route", r.status_code == 401,
              f"{r.status_code} — the exception is too wide")

        r = client.get("/api/v1/admin/settings",
                       headers={"X-Partner-Token": "partner-secret"})
        check("and does not reach admin routes", r.status_code == 401,
              f"{r.status_code} — the exception is far too wide")

        # Without a configured partner token the exception must not exist,
        # otherwise an empty value would match an empty header.
        os.environ.pop("PREMIUM_PARTNER_TOKEN")
        r = client.get(f"{base}/check/5150", headers={"X-Partner-Token": ""})
        check("an unconfigured token grants nothing", r.status_code == 401,
              str(r.status_code))

        # Und mit IRGENDEINEM Wert ebenso wenig.
        #
        # Der leere Header oben wird schon von der spaeteren
        # "kein Token"-Pruefung gefangen; faellt der Riegel fuer die
        # unkonfigurierte Seite weg, faellt das daran nicht auf --
        # im Mutationstest genau so durchgerutscht. Ohne den Riegel
        # koennte auf einer Installation OHNE PREMIUM_PARTNER_TOKEN
        # jeder mit einem beliebigen Header am Dashboard-Schluessel
        # vorbei.
        r = client.get(f"{base}/check/5150",
                       headers={"X-Partner-Token": "irgendwas"})
        check("nor does any value when none is configured",
              r.status_code == 401,
              f"{r.status_code} — ohne konfiguriertes Token darf die "
              "Ausnahme gar nicht greifen")
        os.environ["PREMIUM_PARTNER_TOKEN"] = "partner-secret"

        # The gate is also tested on its own. Through the API a wrong
        # token is caught twice — here and again in the route — so a hole
        # in the gate alone would not show up above.
        class FakeRequest:
            def __init__(self, path, headers, method="GET"):
                self.method = method
                self.url = type("U", (), {"path": path})()
                self.headers = headers

        gate = dep._is_partner_licence_check
        ok = FakeRequest("/api/v1/premium/check/1",
                         {"x-partner-token": "partner-secret"})
        check("the gate accepts the right token", gate(ok) is True)
        check("the gate rejects a wrong token",
              gate(FakeRequest("/api/v1/premium/check/1",
                               {"x-partner-token": "nope"})) is False,
              "any token would pass the gate")
        check("the gate rejects a missing header",
              gate(FakeRequest("/api/v1/premium/check/1", {})) is False)
        check("the gate rejects other paths",
              gate(FakeRequest("/api/v1/admin/settings",
                               {"x-partner-token": "partner-secret"})) is False)
        check("the gate rejects other methods",
              gate(FakeRequest("/api/v1/premium/check/1",
                               {"x-partner-token": "partner-secret"},
                               method="POST")) is False)

        # ── Die Meldung der Probewoche ────────────────────────────
        #
        # Derselbe Tuersteher, dieselbe Falle: die Route /premium/grant
        # wurde gebaut, die Ausnahme aber nicht erweitert. Der
        # Template-Bot bekam HTTP 401 auf ein voellig korrektes Token
        # und schrieb ins Log "stimmt PREMIUM_PARTNER_TOKEN auf beiden
        # Seiten?" -- eine falsche Faehrte, denn das Token stimmte.
        #
        # Dieser Block existiert, weil der Test darueber nur `check`
        # abdeckte. Eine Ausnahmeliste braucht einen Test JE Eintrag.
        from utils import premium_trial
        import tempfile as _tf

        premium_trial.DB_PATH = os.path.join(_tf.mkdtemp(), "trial.db")
        rumpf = {"user_id": "5151", "guild_id": "1", "expires_at": 1893456000,
                 "duration_days": 7}

        r = client.post(f"{base}/grant", json=rumpf,
                        headers={"X-Partner-Token": "partner-secret"})
        check("the trial report gets through", r.status_code == 200,
              f"{r.status_code} {r.text[:140]} — the template bot logs "
              "'Premium-Meldung abgelehnt' when this is 401")
        if r.status_code == 200:
            check("and the trial is granted", r.json().get("granted") is True,
                  r.text[:140])

        r = client.post(f"{base}/grant", json=rumpf,
                        headers={"X-Partner-Token": "wrong"})
        check("a wrong token cannot grant a trial", r.status_code == 401,
              str(r.status_code))

        r = client.post(f"{base}/grant", json=rumpf)
        check("and no token cannot either", r.status_code == 401,
              str(r.status_code))

        check("the gate accepts the grant route",
              gate(FakeRequest("/api/v1/premium/grant",
                               {"x-partner-token": "partner-secret"},
                               method="POST")) is True)
        # GET auf grant ist nicht vorgesehen -- die Liste bindet die
        # Methode mit, sonst oeffnet ein Eintrag mehr als gemeint.
        check("but not with the wrong method",
              gate(FakeRequest("/api/v1/premium/grant",
                               {"x-partner-token": "partner-secret"},
                               method="GET")) is False)

        # Jede Route in der Liste muss oben wirklich geprueft worden
        # sein. Ohne diese Zeile waechst die Liste, der Test nicht --
        # genau so ist `grant` durchgerutscht.
        geprueft = {("GET", "/premium/check/"), ("POST", "/premium/grant")}
        check("every partner route is covered by a test",
              set(dep.PARTNER_ROUTES) == geprueft,
              f"nicht geprueft: {set(dep.PARTNER_ROUTES) - geprueft}")
    finally:
        if saved_key is None:
            os.environ.pop("DASHBOARD_API_KEY", None)
        else:
            os.environ["DASHBOARD_API_KEY"] = saved_key
        if saved_keyless is not None:
            os.environ["ALLOW_KEYLESS_API"] = saved_keyless


def test_key_dm_is_components_v2():
    """
    The DM carrying a key looks like the rest of the bot.

    It used to be a plain markdown message in a bot that speaks in
    panels everywhere else — which reads like a phishing attempt for
    something that is worth money.
    """
    print("\nThe key DM")

    os.environ.setdefault("DASHBOARD_URL", "https://example.invalid")
    from api.routes.premium import _key_dm

    view = _key_dm("5RN2-AGKT-GS6P-CTYE", "30 Tage ab Einlösung")
    payload = view.to_components()

    check("the DM builds at all", bool(payload))

    texts: list[str] = []
    kinds: set[int] = set()

    def walk(items):
        for item in items:
            kinds.add(item.get("type"))
            if item.get("type") == 10:
                texts.append(item.get("content", ""))
            if "components" in item:
                walk(item["components"])

    walk(payload)
    blob = "\n".join(texts)

    # Type 17 is a container, i.e. Components V2 rather than a plain
    # message or a legacy embed.
    check("it is a V2 container", 17 in kinds, str(sorted(kinds)))
    check("the key is in there", "5RN2-AGKT-GS6P-CTYE" in blob)
    check("inside a code block so it can be tapped to copy",
          "```" in blob)
    check("the duration is stated", "30 Tage" in blob)
    check("custom emojis are used, not plain text",
          blob.count("<:") + blob.count("<a:") >= 4,
          "the DM has no bot emojis in it")
    check("a dashboard button is attached", 2 in kinds,
          "no button — the buyer has to find the page themselves")
    check("it warns that this is the only copy",
          "einzige Kopie" in blob)


def test_revoke_reaches_the_template_bot(store):
    """
    Revoking in the dashboard has to take premium away everywhere.

    Two things would otherwise keep it alive on the other side: the
    licence cache (up to five minutes) and any local unlock left over
    from the old master key. So the template bot is told directly.
    """
    print("\nRevoking reaches the template bot")

    src = open(os.path.join(BOT, "api", "routes", "premium.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    check("the template bot is notified", "_tell_partner(" in body)
    check("it posts to the internal endpoints",
          '/internal/{endpoint}' in body
          and '_tell_partner("licence-revoked"' in body)
    check("authenticated with the partner token",
          "X-Partner-Token" in body)
    check("the owner is read before the row changes",
          body.index("owner = store.owner_of_hash") < body.index("ok = store.unrevoke_hash"),
          "after revoking, the owner could no longer be looked up")
    check("a failed notification does not break the revoke",
          "except Exception" in body)

    # Someone may hold two licences; revoking one must not cut the other.
    first = store.create_key(created_by=1, duration_days=0)["key"]
    second = store.create_key(created_by=1, duration_days=0)["key"]
    store.redeem(first, 7001)
    store.redeem(second, 7001)
    store.revoke(first)
    check("a second licence keeps premium alive",
          store.status(7001)["premium"] is True,
          "revoking one key cut an unrelated licence")
    store.revoke(second)
    check("and premium ends with the last one",
          store.status(7001)["premium"] is False)

    check("the owner of a key can be looked up",
          store.owner_of_hash(store.hash_key(second)) == "7001")
    check("an unredeemed key has no owner",
          store.owner_of_hash(store.hash_key(
              store.create_key(created_by=1, duration_days=0)["key"])) is None)


def test_status_reports_the_duration(store):
    """
    The dashboard draws "how much of the licence is left" as a bar, and
    for that it needs the original duration alongside the expiry date.

    Without it the bar silently never appears — no error, just a missing
    element nobody notices until somebody asks where it went.
    """
    print("\nStatus carries the duration")

    key = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(key, 9100)
    state = store.status(9100)
    check("a timed licence reports its length",
          state.get("duration_days") == 30, str(state))

    forever = store.create_key(created_by=1, duration_days=0)["key"]
    store.redeem(forever, 9200)
    check("a lifetime licence reports 0",
          store.status(9200).get("duration_days") == 0,
          "dividing by this would be meaningless")

    check("no licence reports 0",
          store.status(9300).get("duration_days") == 0)

    # Two licences: the bar has to match the date shown next to it, so
    # the duration must come from whichever one runs longest.
    short = store.create_key(created_by=1, duration_days=7)["key"]
    long = store.create_key(created_by=1, duration_days=90)["key"]
    store.redeem(short, 9400)
    store.redeem(long, 9400)
    check("with two licences the longer one wins",
          store.status(9400).get("duration_days") == 90,
          f"got {store.status(9400).get('duration_days')}")


def test_unrevoke_restores_access(store):
    """
    Reported: taking premium away and giving it back left the user
    without premium, while the dashboard said they had it.

    Revoking told the template bot. Lifting the block told it nothing,
    so its cache kept answering "no premium" for up to five minutes —
    the dashboard said active, the bot said no.
    """
    print("\nGiving premium back actually gives it back")

    key = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(key, 8100)
    key_hash = store.hash_key(key)

    check("premium is on", store.status(8100)["premium"] is True)
    store.revoke_hash(key_hash)
    check("and off after revoking", store.status(8100)["premium"] is False)
    store.unrevoke_hash(key_hash)
    check("and on again after undo", store.status(8100)["premium"] is True,
          "the store itself lost the licence")

    src = open(os.path.join(BOT, "api", "routes", "premium.py"), encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    check("undo notifies the template bot too",
          'await _tell_partner("licence-refresh"' in body,
          "lifting a block still tells the other side nothing")

    # Drive the real route and record what it would send. Reading the
    # source only proves the line exists, not that it runs — the first
    # version of this test passed with the branch disabled.
    import api.routes.premium as premium_route

    calls: list[tuple[str, str]] = []

    async def fake_tell(endpoint, user_id):
        calls.append((endpoint, str(user_id)))
        return True

    real_tell = premium_route._tell_partner
    real_url = os.environ.get("TEMPLATE_BOT_URL")
    premium_route._tell_partner = fake_tell
    os.environ["TEMPLATE_BOT_URL"] = "https://template.invalid"
    try:
        asyncio.run(premium_route.revoke_key({"key_hash": key_hash}, bot=None))
        check("revoking calls the revoke endpoint",
              calls and calls[-1] == ("licence-revoked", "8100"),
              str(calls))

        calls.clear()
        asyncio.run(
            premium_route.revoke_key({"key_hash": key_hash, "undo": True}, bot=None)
        )
        check("undo really calls the refresh endpoint",
              calls and calls[-1] == ("licence-refresh", "8100"),
              f"nothing was sent: {calls}")
    finally:
        premium_route._tell_partner = real_tell
        if real_url is None:
            os.environ.pop("TEMPLATE_BOT_URL", None)
        else:
            os.environ["TEMPLATE_BOT_URL"] = real_url
    check("revoking uses the revoke endpoint",
          'await _tell_partner("licence-revoked"' in body)
    # If the branch still reads "if not undo and owner", the refresh can
    # never run.
    check("the notification is not limited to revoking",
          "if not undo and owner:" not in body,
          "undo is excluded from notifying again")


def test_delete_and_purge(store):
    print("\nDeleting keys for good")

    key = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(key, 8200)
    key_hash = store.hash_key(key)

    check("the key exists", store.owner_of_hash(key_hash) == "8200")
    check("delete reports success", store.delete_hash(key_hash) is True)
    check("it is gone from the list",
          all(row["key_hash"] != key_hash for row in store.list_keys(500)))
    check("and premium with it", store.status(8200)["premium"] is False)
    check("deleting twice reports failure", store.delete_hash(key_hash) is False)

    # Bulk cleanup must never touch a licence somebody is using.
    live = store.create_key(created_by=1, duration_days=0)["key"]
    store.redeem(live, 8300)
    dead = store.create_key(created_by=1, duration_days=30)["key"]
    store.redeem(dead, 8400)
    store.revoke(dead)
    store.create_key(created_by=1, duration_days=30)  # never redeemed

    removed = store.purge("revoked")
    check("revoked keys can be purged", removed >= 1, str(removed))
    check("an active licence survives the purge",
          store.status(8300)["premium"] is True,
          "purging cut a live licence")

    before = len(store.list_keys(500))
    store.purge("unclaimed")
    check("unclaimed keys are purged", len(store.list_keys(500)) < before)
    check("the live one is still there",
          store.status(8300)["premium"] is True)

    try:
        store.purge("all")
        check("there is no purge-everything", False, "purge('all') was allowed")
    except ValueError:
        check("there is no purge-everything", True)

    print("\nCounts for the overview")
    numbers = store.stats()
    for field in ("total", "active", "unclaimed", "expired", "revoked",
                  "lifetime", "expiring_soon", "created_30d"):
        check(f"stats has '{field}'", field in numbers, str(numbers))
    check("active matches the live licence", numbers["active"] >= 1, str(numbers))


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
    # The customer panel is only for redeeming. Staff tooling moved to
    # premium-admin.tsx, and leaving mint buttons here would put them in
    # front of people who cannot use them.
    check("the customer panel does not mint keys",
          "createPremiumKey" not in pbody,
          "staff controls are still on the customer page")

    admin = open(os.path.join(dash, "components", "dashboard",
                              "premium-admin.tsx"), encoding="utf-8").read()
    abody = "\n".join(l for l in admin.splitlines() if not l.lstrip().startswith("//"))

    print("\nThe admin tab")
    check("it can mint keys", "createPremiumKey" in abody)
    check("it can revoke and undo",
          "revokePremiumKey" in abody and '"unrevoke"' in abody)
    check("it can delete for good", "deletePremiumKey" in abody)
    check("a fresh key is shown once", "fresh" in abody)
    check("the role state is surfaced", "role?.ok" in abody)

    # Every field the API returns must be *rendered*, not merely
    # mentioned. Checking the whole file passes as long as the name
    # appears in a type or in the CSV export, which is how the first
    # version of this test stayed green with the detail row deleted.
    detail = abody[abody.index("{isOpen && ("):] if "{isOpen && (" in abody else ""
    check("there is a detail row", bool(detail), "nothing expands")

    for field in ("created_at", "redeemed_at", "expires_at", "created_by",
                  "note", "product", "key_hash"):
        check(f"'{field}' is in the detail row", field in detail,
              f"the API sends {field} and the row does not show it")
    for field in ("redeemed_name", "duration"):
        check(f"'{field}' is shown", field in abody,
              f"the API sends {field} and nothing displays it")

    check("rows can be selected for bulk work", "selected" in abody)
    # Both the handler and the buttons that call it: renaming the
    # function alone left the name in the file and the test green.
    check("bulk actions exist",
          "const runBulk" in abody
          and 'runBulk("revoke")' in abody
          and 'runBulk("delete")' in abody,
          "the bulk bar is not wired up")
    check("the list can be searched", "query" in abody)
    check("and sorted", "sortBy" in abody)
    check("the export never writes a key, only hashes",
          "key_hash" in abody and "premium-keys-" in abody)
    check("CSV fields are quoted",
          'replace(/"/g' in abody,
          "a note with a comma would shift every later column")

    # The sidebar splits into "inside a guild" and "top level". Premium is
    # account-wide, so it belongs to the second list, next to Admin Panel.
    tail = lbody.split('name: "Server", href: "/dashboard/guilds"')[-1]
    check("the link sits in the top-level menu",
          '"/dashboard/premium"' in tail,
          "it landed in the per-guild menu instead")

    print("\nDer Premium-Eintrag ist abgesetzt, aber ruhig")

    # Premium bleibt farblich hervorgehoben -- es verkauft etwas --
    # aber ohne goldenes Pulsieren. Eine Dauer-Animation auf einem
    # Link, den man taeglich sieht, ermuedet nur; und in einer Liste,
    # in der drei Eintraege blinken, sticht keiner mehr hervor.
    check("der Eintrag ist farblich abgesetzt",
          "text-amber-300/80" in lbody or "text-amber-200" in lbody,
          "sonst sieht Premium aus wie jeder andere Eintrag")
    check("das Symbol traegt die Farbe", "text-amber-400" in lbody)
    check("aber ohne Pulsieren", "premium-link" not in lbody,
          "die Klasse traegt die Dauer-Animation")

    # Weiter ueber die Adresse zugeordnet: die Beschriftung ist
    # uebersetzt, ein Treffer auf das Wort "Premium" ginge in der
    # zweiten Sprache verloren.
    check("es wird ueber die Adresse erkannt, nicht ueber den Text",
          'item.href === "/dashboard/premium"' in lbody,
          "matching on the label breaks under translation")


def test_mount_animation():
    """
    The Premium tab animates in when it opens.

    Found while building it: the dashboard uses `animate-in fade-in
    slide-in-from-bottom-2` in 45 places, and that comes from the
    tailwindcss-animate plugin — which is not in package.json. Those
    classes produce no CSS whatsoever, so none of it has ever animated.

    Rather than pull in a dependency, Reveal does it with React state
    and a plain transition, which also allows a computed stagger.
    """
    print("\nThe tab animates on open")

    dash = os.path.join(os.path.dirname(BOT), "dashboard")

    reveal_path = os.path.join(dash, "components", "ui", "reveal.tsx")
    check("the Reveal helper exists", os.path.exists(reveal_path), reveal_path)
    reveal = open(reveal_path, encoding="utf-8").read()
    # Strip block comments too, not just "//" lines. The header of this
    # file explains the very things being checked, so a search for
    # "prefers-reduced-motion" matched the prose even after the code was
    # removed — the first run of this test passed with the media query
    # deleted.
    import re as _re
    rbody = _re.sub(r"/\*.*?\*/", "", reveal, flags=_re.S)
    rbody = "\n".join(l for l in rbody.splitlines() if not l.lstrip().startswith("//"))

    check("it is a client component", '"use client"' in rbody,
          "hooks cannot run in a server component")
    check("it animates with state, not dead classes",
          "useState" in rbody and "transition-all" in rbody)
    check("it staggers by a computed delay", "transitionDelay" in rbody)
    check("numbers count up", "CountUp" in rbody and "requestAnimationFrame" in rbody)
    # Two frames, or the browser skips straight to the end state and
    # there is nothing to see.
    check("it paints the start state first",
          "second = requestAnimationFrame(() => setShown(true))" in rbody,
          "a single frame makes the browser skip to the end state")
    check("reduced motion is honoured",
          "prefers-reduced-motion" in rbody and "useReducedMotion" in rbody)
    check("counting is skipped under reduced motion",
          "if (reduced || animated.current)" in rbody)

    admin = open(os.path.join(dash, "components", "dashboard",
                              "premium-admin.tsx"), encoding="utf-8").read()
    abody = "\n".join(l for l in admin.splitlines() if not l.lstrip().startswith("//"))

    check("the admin tab uses it", "<Reveal" in abody)
    check("the counters count up", "<CountUp" in abody)
    check("blocks arrive one after another",
          "delay={60}" in abody and "delay={120}" in abody,
          "everything appears at once")
    # Two hundred keys at 35ms each would take seven seconds to finish.
    check("the row stagger is capped",
          "Math.min(index, 10)" in abody,
          "a long list would animate for far too long")

    page = open(os.path.join(dash, "app", "dashboard", "premium", "page.tsx"),
                encoding="utf-8").read()
    check("the customer page animates too", "<Reveal" in page)
    check("and no longer uses the dead classes",
          "animate-in" not in page,
          "animate-in generates no CSS in this project")

    print("\nThe customer panel")
    panel_path = os.path.join(dash, "components", "dashboard", "premium-panel.tsx")
    panel_src = open(panel_path, encoding="utf-8").read()
    import re as _re
    pb = _re.sub(r"/\*.*?\*/", "", panel_src, flags=_re.S)
    pb = "\n".join(l for l in pb.splitlines() if not l.lstrip().startswith("//"))

    # Count them: with four blocks on the page, swapping one back to a
    # plain div left the word in the file and the check green.
    check("every block animates on open", pb.count("<Reveal") >= 4,
          f"only {pb.count('<Reveal')} of 4 blocks animate")
    check("the remaining days count up", "<CountUp" in pb)
    # Defined *and* rendered — a skeleton that is never returned is just
    # dead code.
    check("there is a loading skeleton",
          "function Skeleton()" in pb and "return <Skeleton />" in pb,
          "the page jumps from nothing to content")
    check("the key is formatted while typing", "tidyKey" in pb)
    check("a wrong length is caught before the request",
          "cleaned.length !== 16" in pb,
          "a typo costs a round trip to find out")
    check("success is acknowledged", "justRedeemed" in pb)

    styles = open(os.path.join(dash, "app", "globals.css"), encoding="utf-8").read()
    # The name appears four times (keyframes, rule, animation, and the
    # reduced-motion override), so pick the line that actually starts
    # the animation rather than whichever match happens to be last.
    celebrate = [
        line for line in styles.splitlines()
        if "animation:" in line and "premium-celebrate" in line
    ]
    check("the celebration runs once",
          bool(celebrate) and "forwards" in celebrate[0]
          and "infinite" not in celebrate[0],
          f"a permanent shimmer on an idle page is noise: {celebrate}")

    # A bar dividing by an absent number renders NaN%, which silently
    # collapses to nothing.
    check("the progress bar needs a real duration",
          "template?.duration_days" in pb,
          "the bar would divide by undefined")

    # Leftovers from when this file also held the admin tab. Unused
    # imports are the kind of thing that quietly rots.
    #
    # Nur den IMPORT-Block ansehen, nicht die ganze Datei.
    #
    # Vorher lief die Suche ueber den kompletten Quelltext, und
    # "Ban" ist ein Teilstring von "Banner" -- das Wort steht seit
    # dem Beta-Abschnitt im Fliesstext ("ein eigenes Banner"). Der
    # Test schlug also an, obwohl kein einziger Import dazugekommen
    # war. Dieselbe Falle traefe "Plus" in "Pluspunkt" oder "Copy"
    # in "Copyright".
    import re as _re
    _block = _re.search(r'import \{([^}]*)\} from "lucide-react";', pb)
    _importiert = {
        n.strip() for n in (_block.group(1).split(",") if _block else [])
    }
    for gone in ("Trash2", "Undo2", "AlertTriangle", "ShieldCheck",
                 "Plus", "Ban", "Search", "Copy"):
        check(f"'{gone}' is no longer imported here", gone not in _importiert,
              "dead import left over from the admin split")


def run():
    from utils import premium_store as store

    test_keys(store)
    test_api(store)
    test_key_commands_are_gone()
    test_role_sync(store)
    test_proxy_binding()
    test_partner_reaches_the_api(store)
    test_key_dm_is_components_v2()
    test_revoke_reaches_the_template_bot(store)
    test_status_reports_the_duration(store)
    test_unrevoke_restores_access(store)
    test_delete_and_purge(store)
    test_dashboard_page()
    test_mount_animation()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
