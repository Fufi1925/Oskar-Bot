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
import re
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
from louckup_app import discord_api as api  # noqa: E402
from louckup_app import krypto  # noqa: E402
from louckup_app.main import create_app  # noqa: E402

# Kein echter Token — lang genug, damit die Laengenpruefung ihn
# durchlaesst, und nur in diesem Prozess bekannt.
HAUPTBOT_TOKEN = "MTExMTEyMjIzMzM0NDQ1NTUuQUJDREVG.R0hJSktMTU5PUFFSLTEyMzQ1Ng"
ZWEITBOT_TOKEN = "OTk5OTg4ODc3NjY1NTQ0MzMuWllYV1ZVVFNS.cXRlc3QtdG9rZW4tbjg4Nzc3"

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
        check("keine Erklaerung auf der Loginseite", settings.oauth_redirect_uri not in r.text)

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
        check("leitet auf den Reiter Self", r.url.path.endswith("/dashboard/self"), r.url.path)
        check("Seitenreiter vorhanden", all(
            label in r.text for label in ("Discord IDs", "Roblox User", "IP", "Self")
        ))
        check("Eigener Name", "Chef" in r.text, r.text[:200])
        check("Eigene E-Mail", "chef@example.com" in r.text)
        check("Eigene Discord-ID", "111111111111111111" in r.text)
        check("Eigene Server", "Testserver" in r.text)
        check("Eigene Logins auf Self", "Eigene Logins" in r.text)
        check("eigener Login als erfolgreich vermerkt", "erfolgreich" in r.text)

        print("\n6b) Platzhalter-Reiter")
        for slug, label in (("roblox", "Roblox User"), ("ip", "IP")):
            r = client.get(f"/louckup/dashboard/{slug}")
            check(f"Reiter {label} erreichbar", r.status_code == 200, str(r.status_code))
            check(f"Reiter {label} ist leer", '<div class="leer">' in r.text)

        r = client.get("/louckup/dashboard/discord-ids")
        check("Reiter Discord IDs erreichbar", r.status_code == 200, str(r.status_code))
        check("Reiter Discord IDs hat Suchfeld", 'name="id"' in r.text)

        print("\n6c) Unbekannter Reiter")
        r = client.get("/louckup/dashboard/quatsch", follow_redirects=True)
        check("faellt auf Self zurueck", r.url.path.endswith("/dashboard/self"), r.url.path)

        print("\n6d) Keine Erklaerungen auf der Seite")
        r = client.get("/louckup/dashboard/self")
        for wort in ("Redirect-URI", "Datenbank:", "Owner-IDs", "Protokoll"):
            check(f"kein '{wort}'", wort not in r.text)

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

        print("\n8b) Loginprotokoll: nur die eigenen Zeilen")
    import asyncio

    from louckup_app import db as dbmod

    async def protokoll():
        db = await dbmod.connect()
        eigene = await dbmod.own_attempts(db, 111111111111111111)
        alle = await dbmod.recent_attempts(db, 50)
        await db.close()
        return eigene, alle

    eigene, alle = asyncio.run(protokoll())
    check(
        "nur Zeilen der eigenen ID",
        bool(eigene) and all(r["user_id"] == 111111111111111111 for r in eigene),
        str([r["user_id"] for r in eigene]),
    )
    check(
        "fremder Versuch liegt in der Tabelle, aber nicht im eigenen Blick",
        any(r["user_id"] == 999999999999999999 for r in alle)
        and not any(r["user_id"] == 999999999999999999 for r in eigene),
    )

    print("\n9) Healthz")
    with mounted_client() as c9:
        data = c9.get("/louckup/healthz").json()
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
        r = client2.get("/louckup/dashboard/self", follow_redirects=False)
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
        check("Login nur mit Knopf, ohne Erklaerung", "gdm.join" not in r.text and "Mit Discord anmelden" in r.text)
        check("kein Footer mehr", "footer" not in r.text)

    print("\n15) Sicherheits-Header")
    with mounted_client() as c:
        r = c.get("/louckup/login")
        check("Content-Security-Policy", "Content-Security-Policy" in r.headers, str(list(r.headers))[:120])
        check("X-Frame-Options DENY", r.headers.get("X-Frame-Options") == "DENY")
        check("X-Content-Type-Options", r.headers.get("X-Content-Type-Options") == "nosniff")
        check("Referrer-Policy", r.headers.get("Referrer-Policy") == "no-referrer")
        check("Bilder nur von Discord erlaubt", "cdn.discordapp.com" in r.headers.get("Content-Security-Policy", ""))

        r = c.get("/louckup/login")
        check("Seiten ohne Browser-Cache", "no-store" in (r.headers.get("Cache-Control") or ""), r.headers.get("Cache-Control", ""))

    print("\n16) Login-Rate-Limit")
    os.environ["LOUCKUP_LOGIN_RATE_LIMIT"] = "2"
    get_settings.cache_clear()
    # Der Zaehler lebt im Modul und damit ueber alle Apps dieses
    # Prozesses hinweg — fuer den Test faengt er bei null an.
    from louckup_app.main import _rate

    _rate.clear()
    with mounted_client() as c:
        codes = [c.get("/louckup/auth/discord", follow_redirects=False).status_code for _ in range(3)]
        check("die ersten beiden gehen durch", codes[:2] == [302, 302], str(codes))
        check("die dritte wird gebremst", codes[2] == 429, str(codes))

    print("\n17) Reiter Einstellungen")
    # Owner-Liste zuruecksetzen — Schritt 10 hatte sie geaendert — und
    # das Login-Rate-Limit aus Schritt 16 wieder hochdrehen, sonst
    # blockt es hier jeden weiteren Login.
    os.environ["LOUCKUP_OWNER_IDS"] = "111111111111111111,222222222222222222"
    os.environ["LOUCKUP_LOGIN_RATE_LIMIT"] = "10"
    os.environ["TOKEN"] = HAUPTBOT_TOKEN
    get_settings.cache_clear()
    import louckup_app.main as louckup_main
    from louckup_app.main import _rate

    _rate.clear()
    # Der Zustand des Hauptbots wird im Modul gehalten und gilt danach
    # eine Weile. Fuer den Test faengt er bei null an.
    louckup_main._primaer_status = {}

    # Discord wird hier nicht wirklich gefragt. Der Hauptbot und ein
    # zusaetzlicher Bot bekommen verschiedene Konten, damit klar ist,
    # welcher Name woher kommt.
    async def bot_selbst(token, zeitlimit=12.0):
        if token == HAUPTBOT_TOKEN:
            return {
                "id": "100000000000000001",
                "username": "universitybot",
                "global_name": "University Bot",
                "avatar": "aa11bb22",
            }
        return {"id": "555000111222333444", "username": "zweitbot", "avatar": "cc33dd44"}

    async def anwendung(token, zeitlimit=12.0):
        return {"name": "University Bot Dev"} if token == HAUPTBOT_TOKEN else {"name": "Zweitbot"}

    api.bot_selbst = bot_selbst
    api.anwendung = anwendung

    def csrf_aus(html: str) -> str:
        treffer = re.search(r'name="csrf" value="([0-9a-f]{32})"', html)
        return treffer.group(1) if treffer else ""

    with mounted_client() as c:
        c.get("/louckup/auth/discord", follow_redirects=False)
        state = c.cookies.get("louckup_oauth_state")
        fake_user.who = "owner"
        c.get("/louckup/auth/callback", params={"code": "abc", "state": state}, follow_redirects=False)

        r = c.get("/louckup/dashboard/einstellungen")
        check("Seite erreichbar", r.status_code == 200, str(r.status_code))
        check("Hauptbot-Zeile vorhanden", "Hauptbot" in r.text)
        check("Hauptbot kommt aus TOKEN", "TOKEN" in r.text)
        check("Hauptbot-Name von Discord geholt", "universitybot" in r.text, r.text[:400])
        check(
            "Hauptbot-Bild von Discord geholt",
            "cdn.discordapp.com/avatars/100000000000000001/aa11bb22.png" in r.text,
            r.text[:400],
        )
        check("Formular mit CSRF-Feld", 'name="csrf"' in r.text)
        check("nur ein Token-Feld, kein Namensfeld", 'name="token"' in r.text and 'name="label"' not in r.text)
        form_csrf = csrf_aus(r.text)
        check("CSRF-Wert auslesbar", len(form_csrf) == 32, form_csrf)

        # Ohne CSRF darf nichts passieren.
        r = c.post(
            "/louckup/dashboard/einstellungen/bots",
            data={"token": ZWEITBOT_TOKEN},
            follow_redirects=True,
        )
        check("ohne CSRF abgelehnt", "Formular abgelaufen" in r.text, r.text[:200])

        # Zu kurzer Kram wird gar nicht erst an Discord geschickt.
        r = c.post(
            "/louckup/dashboard/einstellungen/bots",
            data={"csrf": form_csrf, "token": "vielzukurz"},
            follow_redirects=True,
        )
        check("zu kurzer Token abgelehnt", "zu kurz" in r.text, r.text[:200])

        r = c.post(
            "/louckup/dashboard/einstellungen/bots",
            data={"csrf": form_csrf, "token": ZWEITBOT_TOKEN},
            follow_redirects=True,
        )
        check("Bot angenommen", "Zweitbot eingetragen" in r.text, r.text[:400])

        # Token darf nicht im Klartext in der Datenbank stehen.
        import asyncio

        from louckup_app import db as dbmod2

        async def lies():
            db = await dbmod2.connect()
            reihen = await dbmod2.list_bots(db)
            await db.close()
            return reihen

        reihen = asyncio.run(lies())
        check("ein Bot gespeichert", len(reihen) == 1, str(len(reihen)))
        if reihen:
            check(
                "Token nicht im Klartext",
                ZWEITBOT_TOKEN not in (reihen[0]["token_cipher"] or ""),
                reihen[0]["token_cipher"][:40],
            )
            entschluesselt = krypto.entschluesseln(
                reihen[0]["token_cipher"], get_settings().secret_key
            )
            check("Token laesst sich zuruecklesen", entschluesselt == ZWEITBOT_TOKEN)
            check("Name selbst von Discord geholt", reihen[0]["label"] == "Zweitbot", str(reihen[0]["label"]))
            check("Kontoname gespeichert", reihen[0]["username"] == "zweitbot", str(reihen[0]["username"]))
            check("Bild gespeichert", reihen[0]["avatar"] == "cc33dd44", str(reihen[0]["avatar"]))
            check("Maske statt Token in der Seite", ZWEITBOT_TOKEN not in r.text)
            check(
                "Bild des Bots in der Seite",
                "cdn.discordapp.com/avatars/555000111222333444/cc33dd44.png" in r.text,
                r.text[:400],
            )

        # Pruefen — aktualisiert Name und Bild.
        r2 = c.get("/louckup/dashboard/einstellungen")
        form_csrf = csrf_aus(r2.text)
        bot_id = reihen[0]["id"] if reihen else 0
        r = c.post(
            f"/louckup/dashboard/einstellungen/bots/{bot_id}/pruefen",
            data={"csrf": form_csrf},
            follow_redirects=True,
        )
        check("Pruefen meldet Erfolg", "Token gilt" in r.text, r.text[:300])

        # Entfernen — wieder mit CSRF.
        r2 = c.get("/louckup/dashboard/einstellungen")
        form_csrf = csrf_aus(r2.text)
        r = c.post(
            f"/louckup/dashboard/einstellungen/bots/{bot_id}/entfernen",
            data={"csrf": form_csrf},
            follow_redirects=True,
        )
        check("Bot entfernt", "entfernt" in r.text, r.text[:300])
        check("Liste ist leer", len(asyncio.run(lies())) == 0)

    print("\n18) Suche nach einer Discord-ID")
    with mounted_client() as c:
        c.get("/louckup/auth/discord", follow_redirects=False)
        state = c.cookies.get("louckup_oauth_state")
        c.get("/louckup/auth/callback", params={"code": "abc", "state": state}, follow_redirects=False)

        async def profil(token, uid, zeitlimit=12.0):
            return {
                "id": str(uid),
                "username": "zielperson",
                "global_name": "Ziel",
                "public_flags": 0,
                "accent_color": 16738740,
            }

        async def server(token, zeitlimit=12.0):
            return [{"id": "9001", "name": "Server A"}, {"id": "9002", "name": "Server B"}]

        async def mitglied(token, gid, uid, zeitlimit=12.0):
            if gid == 9001:
                return {
                    "nick": "Spitzname",
                    "joined_at": "2024-05-06T07:08:09.000000+00:00",
                    "roles": ["7001"],
                }
            return None

        async def rollen(token, gid, zeitlimit=12.0):
            return {7001: {"name": "Moderator", "farbe": "#ff0000"}}

        api.profil = profil
        api.bot_server = server
        api.mitglied = mitglied
        api.rollen = rollen

        r = c.get("/louckup/dashboard/discord-ids?id=123456789012345678")
        check("Seite erreichbar", r.status_code == 200, str(r.status_code))
        check("Profil gefunden", "Ziel" in r.text)
        check("ID angezeigt", "123456789012345678" in r.text)
        check("Treffer-Server genannt", "Server A" in r.text)
        check("Rollen aufgeloest", "Moderator" in r.text)
        check("Nickname gezeigt", "Spitzname" in r.text)
        check("Beitrittsdatum gezeigt", "06.05.2024" in r.text, r.text[:400])
        check("Alter des Kontos gezeigt", "seit" in r.text)
        check("keine E-Mail erfunden", "example.com" not in r.text)

        # Alle Server des Bots stehen da — auch die ohne die Person.
        check("Server ohne Mitgliedschaft ist gelistet", "Server B" in r.text)
        check("und als solcher gekennzeichnet", "nicht Mitglied" in r.text, r.text[:400])

        # Aufklappen ohne Skript.
        check("Server sind aufklappbar", "<details" in r.text)
        check("Treffer ist aufklappbar", r.text.count("<details") >= 2, str(r.text.count("<details")))

        # Mehr als vorher: Server-ID, Stumm, Boost, Freigabe, Rollenanzahl.
        for feld in ("Server-ID", "Stumm bis", "Boost seit"):
            check(f"Feld '{feld}' vorhanden", feld in r.text, r.text[:400])

        check("Hauptbot erscheint in der Suche", "University Bot" in r.text, r.text[:400])
        check("Zusammenfassung genannt", "gemeinsame Server" in r.text)

        r = c.get("/louckup/dashboard/discord-ids?id=keinzahl")
        check("Unsinn wird abgewiesen", "keine Zahl" in r.text, r.text[:300])

    print("\n19) Eigene Aufzeichnung in der Suche")
    # Fuer Konten, die sich hier selbst eingeloggt haben, steht in der
    # eigenen Datenbank mehr als bei Discord abrufbar ist: E-Mail,
    # genehmigte Rechte und die Serverliste vom Zeitpunkt der
    # Anmeldung. Fuer alle anderen bleibt die Zeile leer.
    with mounted_client() as c:
        c.get("/louckup/auth/discord", follow_redirects=False)
        state = c.cookies.get("louckup_oauth_state")
        fake_user.who = "owner"
        c.get("/louckup/auth/callback", params={"code": "abc", "state": state}, follow_redirects=False)

        # Die eigene ID des eingeloggten Owners.
        r = c.get("/louckup/dashboard/discord-ids?id=111111111111111111")
        check("Seite erreichbar", r.status_code == 200, str(r.status_code))
        check("Autorisierung wird gezeigt", "Autorisierung" in r.text, r.text[:400])
        check("E-Mail aus der eigenen Datenbank", "chef@example.com" in r.text, r.text[:600])
        check("E-Mail steht auch im Profilblock", r.text.count("chef@example.com") >= 2,
              str(r.text.count("chef@example.com")))
        check("Scope email vermerkt", "Scope email" in r.text, r.text[:600])
        check("Scope guilds vermerkt", "guilds" in r.text)
        check(
            "Serverliste vom Zeitpunkt der Anmeldung",
            "Testserver" in r.text and "Zeitpunkt der Autorisierung" in r.text,
            r.text[:600],
        )
        check("Zeitpunkt der Autorisierung genannt", "Autorisierung bei" in r.text)

        # Das Wichtigste: kein Token auf der Seite.
        check("kein Zugangs-Token im Text", "fake-access-token" not in r.text)
        check("kein Auffrisch-Token im Text", "fake-refresh" not in r.text)
        check("nur gesagt, dass es einen gibt", "wird hier nie angezeigt" in r.text, r.text[:600])

        # Eine fremde ID hat hier nichts liegen.
        r = c.get("/louckup/dashboard/discord-ids?id=123456789012345678")
        check("fremde ID ohne Autorisierung", "Autorisierung bei" not in r.text, r.text[:400])
        check("fremde ID ohne E-Mail", "chef@example.com" not in r.text)
        check("Hinweis, warum die Zeile leer bleibt", "nicht abrufbar" in r.text, r.text[:600])

        # Erster Login ist nicht mehr die letzte Aktualisierung.
        r = c.get("/louckup/dashboard/self")
        check("Self zeigt den ersten Login", "Erster Login" in r.text)

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
