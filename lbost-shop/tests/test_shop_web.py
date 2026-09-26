#!/usr/bin/env python3
"""Dashboard-Endpunkte: Eingabepruefung, Vorschau, Verlauf, Cache, Header."""
import asyncio
import json
import re as _re
import os
import tempfile
import time
from pathlib import Path

DB = Path(tempfile.gettempdir()) / "lbost-web-test.sqlite3"
for suffix in ("", "-wal", "-shm"):
    Path(str(DB) + suffix).unlink(missing_ok=True)

os.environ.update({
    "LBOST_SHOP_BASE_URL": "http://test/lbost-shop",
    "LBOST_SHOP_DISCORD_CLIENT_ID": "client",
    "LBOST_SHOP_DISCORD_CLIENT_SECRET": "client-secret",
    "LBOST_SHOP_SECRET_KEY": "web-session-secret",
    "LBOST_SHOP_TOKEN_ENCRYPTION_KEY": "web-token-secret",
    "LBOST_SHOP_AUTHORIZED_IDS": "123",
    "LBOST_SHOP_OWNER_IDS": "999",
    "LBOST_SHOP_ALLOWED_GUILD_IDS": "1",
    "LBOST_SHOP_BOT_TOKEN": "bot-token",
    "LBOST_SHOP_DB_PATH": str(DB),
})

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from lbost_shop_app import auth, db  # noqa: E402
from lbost_shop_app.config import get_settings  # noqa: E402
from lbost_shop_app.main import create_app  # noqa: E402

discord_aufrufe = {"guilds": 0, "ressourcen": 0}


async def run() -> None:
    async def exchange(code, settings):
        return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

    async def refresh(token, settings):
        return {"access_token": "a", "refresh_token": token, "expires_in": 3600}

    async def discord_user(token):
        return {"id": "123", "username": "tester", "global_name": "Tester", "avatar": None}

    async def guilds(token, authorization_type="Bearer"):
        discord_aufrufe["guilds"] += 1
        if authorization_type == "Bot":
            return [{"id": "1"}]
        return [{"id": "1", "name": "Testserver", "permissions": 0x20, "owner": False, "icon": None}]

    auth.exchange = exchange
    auth.refresh = refresh
    auth.discord_user = discord_user
    auth.guilds = guilds

    # Kanale, Rollen und Serverzahlen kommen aus _discord_abfrage - dort dockt der Test an.
    from lbost_shop_app import main as shop_main

    async def fake_abfrage(bot_token, pfad, params=None):
        discord_aufrufe["ressourcen"] += 1
        assert bot_token == "bot-token"
        if pfad.endswith("/channels"):
            return [{"id": "10", "name": "hallotest", "type": 0}, {"id": "20", "name": "Support", "type": 4}]
        if pfad.endswith("/roles"):
            return [{"id": "1", "name": "@everyone"}, {"id": "30", "name": "Support"}]
        return {"approximate_member_count": 42, "premium_tier": 1, "premium_subscription_count": 3,
                "verification_level": 2, "owner_id": "123"}

    shop_main._discord_abfrage = fake_abfrage

    parent = FastAPI()
    parent.mount("/lbost-shop", create_app())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=parent), base_url="http://test",
                                 follow_redirects=False) as client:
        response = await client.get("/lbost-shop/auth/discord")
        state = client.cookies.get("lbost_shop_oauth_state")
        await client.get("/lbost-shop/auth/callback", params={"code": "ok", "state": state})
        settings = get_settings()

        # ── CSP und Caching auf einer echten Seite ───────────────────
        response = await client.get("/lbost-shop/dashboard")
        csp = response.headers["content-security-policy"]
        assert "unsafe-inline" not in csp, f"CSP aufgeweicht: {csp}"
        assert "style-src 'self'" in csp
        assert response.headers["cache-control"] == "no-store, private"
        response = await client.get("/lbost-shop/static/css/shop.css")
        assert "max-age=86400" in response.headers["cache-control"], response.headers.get("cache-control")
        seite = await client.get("/lbost-shop/guild/1")
        assert _re.search(r"university-dashboard\.css\?v=\d{8}", seite.text), "Assets ohne Versions-Suffix"
        assert "style=" not in seite.text, "Inline-style-Attribute sind gegen die CSP"
        assert _re.search(r'class="ub-fill-\d+', seite.text), "Fortschrittsbalken ohne Fuellgrad-Klasse"
        assert _re.search(r'class="ub-h-\d+', seite.text), "Verlaufsdiagramm ohne Hoehen-Klasse"
        assert "Bot" in seite.text and "ub-status-pill" in seite.text
        anfrage = await client.get("/lbost-shop/guild/1", headers={"Accept-Encoding": "gzip"})
        assert anfrage.headers.get("content-encoding") == "gzip", "keine Kompression"

        # ── Discord-Aufrufe werden gecacht ───────────────────────────
        shop_main.cache_leeren()
        discord_aufrufe.update({"guilds": 0, "ressourcen": 0})
        await client.get("/lbost-shop/guild/1")
        await client.get("/lbost-shop/servers")
        await client.get("/lbost-shop/dashboard")
        # Drei Seiten, ein Nutzer: ein Durchgang durch Discord (Nutzerliste +
        # Botliste = 2 Anfragen). Ohne Cache waren es sechs.
        assert discord_aufrufe["guilds"] == 2, f"Serverliste nicht gecacht: {discord_aufrufe['guilds']} Anfragen (erwartet 2)"
        assert discord_aufrufe["ressourcen"] == 3, f"Kanael/Rollen nicht gecacht: {discord_aufrufe['ressourcen']} Anfragen (erwartet 3)"

        shop_main.cache_leeren()
        discord_aufrufe.update({"guilds": 0})
        await client.get("/lbost-shop/dashboard")
        assert discord_aufrufe["guilds"] == 2, "Cache wird nach dem Ablauf nicht neu gefullt"

        # ── Zahlgrenzen ──────────────────────────────────────────────
        session = auth.read_session(client.cookies.get("lbost_shop_session"), settings)
        token = session["sid"]
        response = await client.post("/lbost-shop/guild/1/moderation", data={
            "csrf": token, "enabled": "on", "spam_limit": "0", "anti_spam": "on",
            "spam_timeout_minuten": "99999", "log_channel_id": "10",
        })
        assert response.status_code == 200 and "nur Werte von" in response.text
        gespeichert = db.get_feature(1, "moderation", settings)
        # Bei einem Fehler bleibt der alte Stand stehen, ein halbes Formular
        # speichert der Shop nicht - sonst ist das Modul aktiv mit 0 Toleranz.
        assert gespeichert == {}, f"trotz Fehler gespeichert: {gespeichert}"
        assert "Nachrichten je 8 Sekunden: nur Werte von 3 bis 100." in response.text

        # Einmal korrekt speichern, dann zeigt die Seite die echten Zahlen
        await client.post("/lbost-shop/guild/1/moderation", data={
            "csrf": token, "enabled": "on", "spam_limit": "6", "anti_spam": "on",
            "spam_timeout": "on", "spam_timeout_minuten": "10", "anti_links": "on",
            "allowed_domains": "discord.com, example.org", "exempt_role_ids": "30, bose, 31",
            "log_channel_id": "10",
        })
        moderiert = db.get_feature(1, "moderation", settings)
        assert moderiert["spam_limit"] == 6 and moderiert["spam_timeout_minuten"] == 10
        assert moderiert["exempt_role_ids"] == "30,31", moderiert["exempt_role_ids"]
        assert moderiert["anti_links"] is True
        # Abschaaltbare Felder landen immer in der Konfiguration, auch als False.
        assert moderiert["link_timeout"] is False and moderiert["spam_timeout"] is True

        # ── URLs und Farben ──────────────────────────────────────────
        response = await client.post("/lbost-shop/guild/1/tickets", data={
            "csrf": token, "enabled": "on", "title": "Support", "description": "Text",
            "image_url": "javascript:alert(1)", "color": "gruen", "panel_channel_id": "10",
        })
        assert "nur http(s)-Links erlaubt" in response.text and "#rrggbb" in response.text
        assert db.get_feature(1, "tickets", settings) == {}, "ungueltige Eingabe wurde gespeichert"
        await client.post("/lbost-shop/guild/1/tickets", data={
            "csrf": token, "enabled": "on", "title": "Support", "description": "Text",
            "image_url": "https://cdn.discordapp.com/a.png", "color": "#5865f2",
            "panel_channel_id": "10", "category_id": "20", "support_role_ids": "30",
            "ticket_title": "Ticket {ticket_number} für {user}",
            "ticket_message": "Danke {user}, {server} hilft.",
            "ticket_created_message": "Los geht es in {channel}",
            "slowmode_seconds": "10",
            "questions_json": json.dumps([{"label": f"Frage {i}", "type": "short"} for i in range(9)]),
            "panels_json": '[{"key":"billing","title":"Billing"},{"label":"kein panel"}, "mist"]',
        })
        tickets = db.get_feature(1, "tickets", settings)
        assert tickets["ticket_title"] == "Ticket {ticket_number} für {user}"
        assert tickets["slowmode_seconds"] == 10
        assert len(tickets["questions_json"]) == 5, tickets["questions_json"]
        assert all(frage["type"] in {"short", "paragraph", "image"} for frage in tickets["questions_json"])
        assert len(tickets["panels_json"]) == 1 and tickets["panels_json"][0]["key"] == "billing"
        # ── Vorschau: rechnet den Entwurf, speichert aber nichts ─────
        response = await client.post("/lbost-shop/guild/1/tickets/vorschau",
                                     json={"ticket_message": "Entwurf für {user}", "fremder_schluessel": "x"})
        assert response.status_code == 200, response.text
        vorschau = response.json()
        assert vorschau["nachricht"] == "Entwurf für @dein.name"
        # Die Vorschau kennt nur die Ticket-Felder: ein fremder Schluessel kann
        # nichts veraendern, und fremde Module haben gar keine Vorschau.
        assert vorschau["unbekannte_felder"] == ["fremder_schluessel"], "Feld-Drift bleibt unsichtbar"
        sauber = await client.post("/lbost-shop/guild/1/tickets/vorschau", json={"ticket_message": "Nur Text"})
        assert "unbekannte_felder" not in sauber.json()
        fremdes_modul = await client.post("/lbost-shop/guild/1/moderation/vorschau", json={"spam_limit": 1})
        assert fremdes_modul.status_code == 403, fremdes_modul.status_code
        zu_gross = await client.post("/lbost-shop/guild/1/tickets/vorschau",
                                     content=b'{"ticket_message": "' + b"x" * 70000 + b'"}')
        assert zu_gross.status_code == 400, "Riesiger Entwurf laeuft durch"
        assert vorschau["titel"] == "Ticket 0001 für @dein.name"
        assert vorschau["bestaetigung"] == "Los geht es in #ticket-0001-support"
        assert len(vorschau["fragen"]) == 5
        # Gespeichert hat die Vorschau nichts
        assert db.get_feature(1, "tickets", settings)["ticket_message"] == "Danke {user}, {server} hilft."
        anonyme = httpx.AsyncClient(transport=httpx.ASGITransport(app=parent), base_url="http://test")
        async with anonyme as ohne_login:
            abgelehnt = await ohne_login.post("/lbost-shop/guild/1/tickets/vorschau", json={"ticket_message": "x"})
            assert abgelehnt.status_code in (403, 302, 401), abgelehnt.status_code

        # Panels ohne Schlussel oder mit doppeltem Schlussel sind kein Panel
        # (erst jetzt pruefen: Speichern ersetzt das ganze Modul)
        await client.post("/lbost-shop/guild/1/tickets", data={
            "csrf": token, "enabled": "on", "title": "Support",
            "panels_json": '[{"key":"billing","title":"A"},{"key":"billing","title":"B"},{"label":"ohne key"},{"key":"Bose Sache!"}]',
        })
        assert [p["key"] for p in db.get_feature(1, "tickets", settings)["panels_json"]] == ["billing"]

        # ── Verwarnungen im Dashboard ────────────────────────────────
        db.warnung_anlegen(1, 555, 123, "Beleidigung", settings)
        seite = await client.get("/lbost-shop/guild/1/moderation")
        assert "Verwarnungen auf diesem Server" in seite.text
        assert "555" in seite.text and "Beleidigung" in seite.text and "löschen" in seite.text
        eintrag = db.warnungen_fuer_gilde(1, settings, 5)[0]
        abgelehnt = await client.post(f"/lbost-shop/guild/1/moderation/warnung/{eintrag['id']}/loeschen", data={"csrf": "falsch"})
        assert abgelehnt.status_code == 403
        assert db.warnungen_fuer_gilde(1, settings, 5), "falsches CSRF hat trotzdem geloescht"
        ok = await client.post(f"/lbost-shop/guild/1/moderation/warnung/{eintrag['id']}/loeschen", data={"csrf": token})
        assert ok.status_code == 303 and "geloescht=1" in ok.headers["location"]
        assert not db.warnungen_fuer_gilde(1, settings, 5)

        # ── Import filtert unbekanntes ───────────────────────────────
        payload = {"version": 1, "guild_id": "1", "features": {
            "moderation": {"enabled": True, "spam_limit": 0, "bösartiger_schluessel": "x"},
            "unbekannt": {"enabled": True},
        }}
        antwort = await client.post("/lbost-shop/guild/1/config-import",
                                    data={"csrf": token},
                                    files={"config_file": ("c.json", json.dumps(payload).encode(), "application/json")})
        assert antwort.status_code == 303
        imported = db.get_feature(1, "moderation", settings)
        assert "bösartiger_schluessel" not in imported, "Import schreibt beliebige Felder"
        # Eine ungueltige Zahl im Import ueberschreibt nichts: das Modul wird
        # komplett uebersprungen, der alte Stand bleibt stehen.
        assert imported["spam_limit"] == 6 and imported["enabled"] is True
        assert "anti_spam" in imported
        assert "unbekannt" not in db.all_features(1, settings)
        assert "restored=0" in antwort.headers["location"], antwort.headers["location"]

        # ── Bot-Status gemessen statt behauptet ──────────────────────
        gesundheit = (await client.get("/lbost-shop/healthz")).json()
        assert gesundheit["bot_online"] is False and gesundheit["bot_letzte_meldung"] is None
        db.set_state(0, "bot_heartbeat", {"zeit": int(time.time()), "gilden": 3, "name": "Shop#0001"}, settings)
        gesundheit = (await client.get("/lbost-shop/healthz")).json()
        assert gesundheit["bot_online"] is True and gesundheit["bot_letzte_meldung"] <= 2
        seite = await client.get("/lbost-shop/dashboard")
        assert "Bot online" in seite.text and "3 Server" in seite.text

        # ── Admin-Panel: Sitzungen entwerten ────────────────────────
        admin = await client.get("/lbost-shop/admin")
        assert admin.status_code == 302, "Nicht-Owner sieht das Admin-Panel"

    # Owner-Login fuer das Admin-Panel
    async def discord_user_owner(token):
        return {"id": "999", "username": "owner", "global_name": "Owner", "avatar": None}

    auth.discord_user = discord_user_owner
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=parent), base_url="http://test",
                                 follow_redirects=False) as owner:
        await owner.get("/lbost-shop/auth/discord")
        state = owner.cookies.get("lbost_shop_oauth_state")
        await owner.get("/lbost-shop/auth/callback", params={"code": "ok", "state": state})
        admin = await owner.get("/lbost-shop/admin")
        assert admin.status_code == 200
        assert "aktive Sitzungen" in admin.text and "Zugang" in admin.text
        assert "123" in admin.text and "999" in admin.text
        assert "configure:" in admin.text, "Aenderungsverlauf fehlt"
        sitzungen = db.offene_sitzungen(get_settings())
        assert len(sitzungen) >= 2
        session = auth.read_session(owner.cookies.get("lbost_shop_session"), get_settings())
        entwerten = await owner.post("/lbost-shop/admin/sitzungen/loeschen", data={"csrf": session["sid"]})
        assert entwerten.status_code == 303 and "abgemeldet=2" in entwerten.headers["location"], entwerten.headers
        assert db.offene_sitzungen(get_settings()) == [], "Sitzungen bleiben in der Datenbank stehen"
        nachher = await owner.get("/lbost-shop/dashboard")
        assert nachher.status_code == 302, "abgemeldete Sitzung darf weiterarbeiten"
        # Der Browser folgt der Umleitung, der Test muss es also auch tun.
        login_seite = await owner.get(entwerten.headers["location"])
        assert login_seite.status_code == 200
        assert "Sitzungen wurden abgemeldet" in login_seite.text

    # ── Ratelimit bleibt begrenzt und raeumt auf ─────────────────────
    from lbost_shop_app.main import _rate, _rate_pruefen
    assert _rate_pruefen("9.9.9.9", 2) is True
    assert _rate_pruefen("9.9.9.9", 2) is True
    assert _rate_pruefen("9.9.9.9", 2) is False, "Ratelimit greift nicht"
    for index in range(6000):
        _rate[f"10.0.{index // 250}.{index % 250}"] = [time.time() - 500]
    assert _rate_pruefen("8.8.8.8", 10) is True
    assert len(_rate) < 20, f"Ratelimit-Woerterbuch raeumt nicht auf: {len(_rate)} Eintraege"

    print("ok   Pruefung, Vorschau, Verlauf, Cache, Header, Abmelden, Ratelimit")


if __name__ == "__main__":
    asyncio.run(run())
