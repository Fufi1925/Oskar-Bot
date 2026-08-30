#!/usr/bin/env python3
"""
Louckup — Verhaltenstest.

Prüft den kompletten Weg durch den Bereich, ohne Discord zu berühren.
Getestet wird **eingebaut in eine Eltern-App unter /louckup**, also genau
so, wie es spaeter in bot/api/server.py haengt.

  /louckup              -> Login
  /louckup/auth/discord -> richtige Scopes + Redirect-URI
  Callback als Owner    -> Session + /louckup/dashboard
  Callback als Fremder  -> kein Cookie, weiter aufs normale Dashboard
  /dashboard mit entzogener Owner-Zugehoerigkeit -> raus

Aufruf:

    cd louckup && python3 tests/test_louckup_flow.py

Setzt voraus: fastapi, httpx, aiosqlite, jinja2, itsdangerous,
pydantic-settings (siehe louckup/requirements.txt).
"""

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TMP = tempfile.mkdtemp(prefix="louckup-test-")

# Muss gesetzt sein, BEVOR app.config importiert wird.
os.environ.update(
    {
        "LOUCKUP_BASE_URL": "http://testserver/louckup",
        "LOUCKUP_COOKIE_PATH": "/louckup",
        "LOUCKUP_SECRET_KEY": "test-secret-not-a-real-one",
        "LOUCKUP_DISCORD_CLIENT_ID": "123456789012345678",
        "LOUCKUP_DISCORD_CLIENT_SECRET": "test-client-secret",
        "LOUCKUP_OWNER_IDS": "111111111111111111,222222222222222222",
        "LOUCKUP_OAUTH_SCOPES": "identify email guilds guilds.join gdm.join",
        "LOUCKUP_DB_PATH": os.path.join(TMP, "louckup.db"),
        "LOUCKUP_FALLBACK_URL": "/",
    }
)

sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from louckup_app import auth  # noqa: E402
from louckup_app.config import get_settings  # noqa: E402
from louckup_app.main import create_app  # noqa: E402

OWNER = {
    "id": "111111111111111111",
    "username": "chef",
    "global_name": "Chef",
    "avatar": None,
    "email": "chef@example.com",
    "verified": True,
}
STRANGER = {"id": "999999999999999999", "username": "gast", "global_name": "Gast", "avatar": None}

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILURES.append(name)


async def fake_exchange(code, settings=None):
    return {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh",
        "expires_in": 604800,
        "scope": "identify email guilds guilds.join gdm.join",
    }


async def fake_user(access_token):
    return dict(STRANGER if fake_user.who == "stranger" else OWNER)


async def fake_guilds(access_token):
    return [{"id": "5000", "name": "Testserver", "owner": True, "permissions": "8"}]


fake_user.who = "owner"

auth.exchange_code = fake_exchange
auth.fetch_discord_user = fake_user
auth.fetch_user_guilds = fake_guilds


def clears_cookie(response, name: str) -> bool:
    """True, wenn die Antwort den Cookie per Max-Age=0 loescht.

    Der httpx-Cookie-Jar im Testclient entfernt manuell gesetzte Cookies
    nicht zuverlaessig, ein Browser aber sehr wohl — geprueft wird daher
    das, was ueber die Leitung geht.
    """
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}=") and "Max-Age=0" in raw.replace("max-age=0", "Max-Age=0"):
            return True
    return False


def mounted_client():
    """Louckup so einbauen, wie es in bot/api/server.py passiert."""
    parent = FastAPI()
    parent.mount("/louckup", create_app())
    return TestClient(parent)


def main() -> int:
    settings = get_settings()

    with mounted_client() as client:
        print("\n1) /louckup ohne Session")
        r = client.get("/louckup/", follow_redirects=False)
        check("Redirect", r.status_code in (302, 307), str(r.status_code))
        check("Ziel /louckup/login", r.headers.get("location", "").endswith("/louckup/login"), r.headers.get("location", ""))

        print("\n2) Loginseite")
        r = client.get("/louckup/login")
        check("HTTP 200", r.status_code == 200, str(r.status_code))
        check("Discord-Knopf vorhanden", "Mit Discord anmelden" in r.text)
        check("Redirect-URI sichtbar", settings.oauth_redirect_uri in r.text)

        print("\n3) /louckup/auth/discord")
        r = client.get("/louckup/auth/discord", follow_redirects=False)
        loc = r.headers.get("location", "")
        check("Geht zu Discord", loc.startswith("https://discord.com/api/oauth2/authorize"), loc)
        check("client_id korrekt", f"client_id={settings.louckup_discord_client_id}" in loc)
        for scope in ("identify", "email", "guilds", "guilds.join", "gdm.join"):
            check(f"Scope {scope}", scope in loc)
        check("redirect_uri passt", "louckup%2Fauth%2Fcallback" in loc, loc)
        state = client.cookies.get("louckup_oauth_state")
        check("State-Cookie gesetzt", bool(state))

        print("\n4) /louckup/dashboard ohne Session")
        r = client.get("/louckup/dashboard", follow_redirects=False)
        check(
            "Zurueck zum Login",
            r.status_code in (302, 307) and r.headers.get("location", "").endswith("/louckup/login"),
            r.headers.get("location", ""),
        )

        print("\n5) Callback als Owner")
        fake_user.who = "owner"
        r = client.get("/louckup/auth/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        check("Weiter auf Dashboard", r.headers.get("location", "").endswith("/louckup/dashboard"), r.headers.get("location", ""))
        check("Session-Cookie gesetzt", bool(client.cookies.get("louckup_session")))

        print("\n6) Dashboard als Owner")
        r = client.get("/louckup/dashboard")
        check("HTTP 200", r.status_code == 200, str(r.status_code))
        check("Begruesst den User", "Chef" in r.text, r.text[:200])
        check("Zeigt E-Mail", "chef@example.com" in r.text)
        check("Geruest vorhanden", "Platzhalter" in r.text)

        print("\n7) Abmelden")
        r = client.get("/louckup/logout", follow_redirects=False)
        check("Session-Cookie wird geloescht", clears_cookie(r, "louckup_session"), str(r.headers.get_list("set-cookie")))

        print("\n8) Callback als Nicht-Owner")
        client.cookies.clear()
        client.get("/louckup/auth/discord", follow_redirects=False)
        state = client.cookies.get("louckup_oauth_state")
        fake_user.who = "stranger"
        r = client.get("/louckup/auth/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        check("Weiter aufs normale Dashboard", r.headers.get("location") == "/", r.headers.get("location", ""))
        check("KEIN Session-Cookie", "louckup_session" not in client.cookies, str(list(client.cookies.keys())))

        print("\n9) Healthz")
        data = client.get("/louckup/healthz").json()
        check("ok", data.get("ok") is True, str(data))
        check("oauth konfiguriert", data.get("oauth_configured") is True, str(data))
        check("zwei Owner eingetragen", data.get("owners") == 2, str(data))

    print("\n10) Owner-Liste aendert sich bei bestehender Session")
    os.environ["LOUCKUP_OWNER_IDS"] = "555555555555555555"
    get_settings.cache_clear()
    with mounted_client() as client2:
        from louckup_app.config import get_settings as gs

        token = auth.create_session_token(OWNER, gs())
        client2.cookies.set("louckup_session", token, path="/louckup")
        r = client2.get("/louckup/dashboard", follow_redirects=False)
        check("Rauswurf aufs Dashboard", r.headers.get("location") == "/", r.headers.get("location", ""))
        check("Session wird geloescht", clears_cookie(r, "louckup_session"), str(r.headers.get_list("set-cookie")))

    print("\n11) Isolation im Quelltext")
    sources = sorted(ROOT.glob("louckup_app/*.py"))
    check("Dateien gefunden", len(sources) >= 4, str(len(sources)))
    bad = []
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in ("from phantom", "import phantom", "from bot.", "import bot.", "from dashboard"):
            if forbidden in text:
                bad.append(f"{path.name}: {forbidden}")
    check("kein Import aus phantom/bot/dashboard", not bad, "; ".join(bad))

    print("\n12) Session-Signer ist eigenstaendig")
    from louckup_app.config import get_settings as gs2
    from itsdangerous import URLSafeTimedSerializer

    s = gs2()
    foreign = URLSafeTimedSerializer(s.secret_key, salt="phantom-session-v1").dumps(
        {"uid": 111111111111111111}
    )
    check("Phantom-Cookie wird abgelehnt", auth.read_session_token(foreign, s) is None)

    print("\n13) Nackte Adresse /louckup (ohne Slash)")
    # Seit Starlette 1.x greift ein Mount nur auf Pfade MIT Slash. Die
    # nackte Adresse faellt sonst durch bis zum Catch-All-Proxy des
    # Dashboards und der Browser zeigt dessen 404. bot/api/server.py
    # faengt das mit einer eigenen Route ab — die wird hier nachgebaut.
    from fastapi.responses import PlainTextResponse, RedirectResponse

    parent = FastAPI()
    parent.mount("/louckup", create_app())

    @parent.get("/louckup", include_in_schema=False)
    async def louckup_root():
        return RedirectResponse(url="/louckup/", status_code=307)

    @parent.api_route("/{path:path}", methods=["GET"])
    async def catchall(path: str):
        return PlainTextResponse("DASHBOARD-PROXY", status_code=404)

    with TestClient(parent) as c:
        r = c.get("/louckup", follow_redirects=False)
        check("trifft nicht den Dashboard-Proxy", "DASHBOARD-PROXY" not in r.text, r.text[:60])
        check("leitet auf /louckup/ weiter", r.headers.get("location") == "/louckup/", r.headers.get("location", ""))
        r = c.get("/louckup", follow_redirects=True)
        check("landet am Ende auf der Loginseite", r.status_code == 200 and "Mit Discord anmelden" in r.text, str(r.status_code))

    print("\n14) Pfade stimmen auch ohne LOUCKUP_BASE_URL")
    # Ist die Variable leer oder falsch gesetzt, duerfen die internen
    # Links nicht aus dem Bereich herausfallen. Der Mount-Pfad steht in
    # request.scope["root_path"] — der ist die Wahrheit, nicht die Config.
    os.environ["LOUCKUP_BASE_URL"] = ""
    get_settings.cache_clear()
    with mounted_client() as c:
        r = c.get("/louckup/", follow_redirects=False)
        check(
            "/louckup/ bleibt im Bereich",
            r.headers.get("location", "").endswith("/louckup/login"),
            r.headers.get("location", ""),
        )
        r = c.get("/louckup/login")
        check("Loginseite mit richtigem CSS-Pfad", "/louckup/static/css/louckup.css" in r.text)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} von {CHECKS} Pruefungen fehlgeschlagen:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"Alle {CHECKS} Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
