import asyncio
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes import support


def request(user_id: str, name: str, kind: str = "supporter") -> Request:
    headers = [
        (b"x-dashboard-user-id", user_id.encode()),
        (b"x-dashboard-user-name", name.encode()),
        (b"x-dashboard-user-avatar", b"https%3A%2F%2Fcdn.example%2Fa.png"),
        (b"x-dashboard-actor-kind", kind.encode()),
    ]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers})


class FakeBot:
    def __init__(self):
        self.guild = SimpleNamespace(id=123456789012345678, name="Test Server", icon=None)

    def get_guild(self, guild_id):
        return self.guild if guild_id == self.guild.id else None


def test_support_requires_consent_and_closing_revokes_access(tmp_path, monkeypatch):
    monkeypatch.setattr(support, "DB_PATH", str(tmp_path / "support.db"))
    monkeypatch.setattr(support, "_support_role", lambda uid: ("Co-Owner", "#f43f5e", 95))

    async def run():
        admin = request("111111111111111111", "Support Admin")
        owner = request("222222222222222222", "Server Owner", "owner")
        created = await support.create_request(
            {"guild_id": "123456789012345678", "problem": "Ich helfe bei der Einrichtung."},
            admin,
            FakeBot(),
        )
        assert created["status"] == "pending"
        assert created["supporter_name"] == "Support Admin"
        assert (await support.support_access(created["guild_id"], created["supporter_id"]))["allowed"] is False

        accepted = await support.respond(created["guild_id"], created["id"], {"decision": "accepted"}, owner)
        assert accepted["status"] == "accepted"
        assert (await support.support_access(created["guild_id"], created["supporter_id"]))["allowed"] is True

        await support.owner_add_message(created["guild_id"], created["id"], {"message": "Bitte prüfe die Rollen."}, owner)
        await support.admin_add_message(created["id"], {"message": "Scan ist fertig."}, admin)
        await support.owner_close_case(created["guild_id"], created["id"], owner)
        assert (await support.support_access(created["guild_id"], created["supporter_id"]))["allowed"] is False

    asyncio.run(run())


def test_administrator_rank_is_not_high_enough(tmp_path, monkeypatch):
    monkeypatch.setattr(support, "DB_PATH", str(tmp_path / "support.db"))
    monkeypatch.setattr(support, "_support_role", lambda uid: ("Administrator", "#ef4444", 90))

    with pytest.raises(HTTPException) as exc:
        support._require_supporter(request("111111111111111111", "Admin"))
    assert exc.value.status_code == 403


def test_support_proxy_is_owner_gated_and_tab_is_grouped():
    proxy = open("dashboard/app/api/bot/[...path]/route.ts", encoding="utf-8").read()
    auth = open("dashboard/lib/guild-auth.ts", encoding="utf-8").read()
    admin = open("dashboard/components/dashboard/admin-content.tsx", encoding="utf-8").read()
    layout = open("dashboard/app/dashboard/layout.tsx", encoding="utf-8").read()

    assert 'if (scope === "support")' in proxy
    assert "ownsGuildOnDiscord(guildId)" in proxy
    assert "hasAcceptedSupportAccess" in auth
    assert 'name: "Support"' in admin and 'ids: ["support"]' in admin
    assert 'name: "Hilfe"' in layout and "pendingSupportRequests" in layout
