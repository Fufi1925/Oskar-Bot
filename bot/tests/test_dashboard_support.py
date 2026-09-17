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
        await support.owner_close_case(created["guild_id"], created["id"], {"rating": 9, "rating_note": "Sehr hilfreich"}, owner)
        assert (await support.support_access(created["guild_id"], created["supporter_id"]))["allowed"] is False
        listed = await support.guild_cases(created["guild_id"])
        assert listed["cases"][0]["rating"] == 9
        assert listed["cases"][0]["rating_note"] == "Sehr hilfreich"
        rankings = await support.admin_rankings(admin)
        assert rankings["summary"]["average_rating"] == 9
        assert rankings["ranking"][0]["average_rating"] == 9
        assert rankings["ranking"][0]["ratings_count"] == 1
        deleted = await support.admin_delete_case(created["id"], admin)
        assert deleted["ok"] is True
        assert (await support.guild_cases(created["guild_id"]))["cases"] == []

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
    guild_panel = open("dashboard/components/dashboard/guild-support-panel.tsx", encoding="utf-8").read()
    admin_panel = open("dashboard/components/dashboard/support-requests-admin.tsx", encoding="utf-8").read()
    ranking_panel = open("dashboard/components/dashboard/support-rankings-admin.tsx", encoding="utf-8").read()

    assert 'if (scope === "support")' in proxy
    assert "ownsGuildOnDiscord(guildId)" in proxy
    assert "hasAcceptedSupportAccess" in auth
    assert 'name: "Support"' in admin and 'ids: ["support", "support-rankings"]' in admin
    assert 'name: "Hilfe"' in layout and "pendingSupportRequests" in layout
    assert "Es kann sich um ein ernstes Problem handeln" in guild_panel
    assert "Bitte bewerte unseren Admin von 1 bis 10 Sternen" in guild_panel
    assert "Dashboard-Bugs prüfen" in admin_panel and "Discord-Bugs prüfen" in admin_panel
    assert "Anfrage löschen" in admin_panel
    assert 'label: "Rankings"' in admin and 'ids: ["support", "support-rankings"]' in admin
    assert "average_rating" in ranking_panel and "Zufriedenheit" in ranking_panel
