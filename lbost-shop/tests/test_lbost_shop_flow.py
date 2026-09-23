#!/usr/bin/env python3
"""Integration test for OAuth, strict guild filtering and owner-only admin."""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

DB_PATH = str(Path(tempfile.gettempdir()) / "lbost-shop-flow-test.sqlite3")
for suffix in ("", "-wal", "-shm"):
    Path(DB_PATH + suffix).unlink(missing_ok=True)

os.environ.update({
    "LBOST_SHOP_BASE_URL": "http://test/lbost-shop",
    "LBOST_SHOP_DISCORD_CLIENT_ID": "client",
    "LBOST_SHOP_DISCORD_CLIENT_SECRET": "client-secret",
    "LBOST_SHOP_SECRET_KEY": "session-secret-for-test",
    "LBOST_SHOP_TOKEN_ENCRYPTION_KEY": "token-secret-for-test",
    "LBOST_SHOP_AUTHORIZED_IDS": "123",
    "LBOST_SHOP_OWNER_IDS": "999",
    "LBOST_SHOP_ALLOWED_GUILD_IDS": "1,3,4",
    "LBOST_SHOP_BOT_TOKEN": "bot-token",
    "LBOST_SHOP_DB_PATH": DB_PATH,
})

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from lbost_shop_app import auth  # noqa: E402
from lbost_shop_app.config import get_settings  # noqa: E402
from lbost_shop_app.main import create_app  # noqa: E402


async def run() -> None:
    user_id = "123"

    async def exchange(code, settings):
        return {"access_token": "plain-access", "refresh_token": "plain-refresh", "expires_in": 3600}

    async def discord_user(token):
        return {"id": user_id, "username": "tester", "global_name": "Tester", "avatar": None, "email": "test@example.invalid"}

    async def guilds(token, authorization_type="Bearer"):
        if authorization_type == "Bot":
            return [{"id": "1"}, {"id": "2"}, {"id": "4"}]
        return [
            {"id": "1", "name": "Visible", "permissions": 0x20, "owner": False, "icon": None},
            {"id": "2", "name": "Not secret", "permissions": 0x20, "owner": False, "icon": None},
            {"id": "3", "name": "Bot absent", "permissions": 0x20, "owner": False, "icon": None},
            {"id": "4", "name": "No rights", "permissions": 0, "owner": False, "icon": None},
        ]

    auth.exchange = exchange
    auth.discord_user = discord_user
    auth.guilds = guilds

    parent = FastAPI()
    parent.mount("/lbost-shop", create_app())
    transport = httpx.ASGITransport(app=parent)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        async def login():
            response = await client.get("/lbost-shop/auth/discord")
            assert response.status_code == 302
            state = client.cookies.get("lbost_shop_oauth_state")
            response = await client.get("/lbost-shop/auth/callback", params={"code": "ok", "state": state})
            assert response.headers["location"] == "/lbost-shop/auth/success"

        await login()
        response = await client.get("/lbost-shop/dashboard")
        assert response.status_code == 200
        assert "Visible" in response.text
        assert all(name not in response.text for name in ("Not secret", "Bot absent", "No rights"))
        assert "University Bot" in response.text and "Control Center" in response.text
        response = await client.get("/lbost-shop/servers")
        assert response.status_code == 200
        assert "Deine Server" in response.text and "Mitglieder erreicht" in response.text and "Server mit Bot" in response.text
        response = await client.get("/lbost-shop/guild/1")
        assert response.status_code == 200
        assert "Advanced Ticket System" in response.text and "Dashboard durchsuchen" in response.text
        assert "Einrichtung" in response.text and "Nächste Schritte" in response.text and "Noch offen" in response.text

        # Ordinary authorised users neither see nor open the owner panel.
        assert "Admin-Panel" not in response.text
        response = await client.get("/lbost-shop/admin")
        assert response.status_code == 302
        assert response.headers["location"] == "/lbost-shop/dashboard"

        row = sqlite3.connect(DB_PATH).execute("SELECT access_token,refresh_token FROM oauth_sessions").fetchone()
        assert b"plain-access" not in row[0]
        assert b"plain-refresh" not in row[1]

        # Removing an ID invalidates its existing browser session immediately.
        get_settings().authorized_ids = ""
        response = await client.get("/lbost-shop/dashboard")
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        get_settings().authorized_ids = "123"

        await client.get("/lbost-shop/logout")
        user_id = "999"
        await login()
        response = await client.get("/lbost-shop/admin")
        assert response.status_code == 200
        assert "Noch keine Einstellungen" in response.text

    print("ok   OAuth, Filter, Verschluesselung, Widerruf und Owner-Admin")


if __name__ == "__main__":
    asyncio.run(run())
