"""Exercise the console HTTP routes against temporary databases and a fake guild."""
import math
import asyncio
import threading
import sqlite3
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_bot, set_bot_loop
from api.routes import support_operations as route
from utils import support_operations as ops, template_store, feature_flags


def main():
    app = FastAPI()
    app.include_router(route.router, prefix="/support-operations")
    guild = SimpleNamespace(id=ops.MAIN_SUPPORT_GUILD_ID, name="Support", icon=None,
        owner_id=1, owner=None, me=None, member_count=12, channels=[], roles=[])
    bot = SimpleNamespace(guilds=[guild], latency=math.nan,
        get_guild=lambda ident: guild if ident == guild.id else None,
        get_user=lambda ident: None)
    app.dependency_overrides[get_bot] = lambda: bot
    base = f"/support-operations/{guild.id}"
    # The API and Discord run on distinct loops in production.
    bot_loop = asyncio.new_event_loop()
    worker = threading.Thread(target=bot_loop.run_forever)
    worker.start()
    set_bot_loop(bot_loop)
    def on_bot_loop(result):
        async def action(*args):
            assert asyncio.get_running_loop() is bot_loop
            return result
        return action
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as temp, patch.object(ops, "OWNER_IDS", [1]):
        os.chdir(temp)
        os.mkdir("db")
        try:
            with TestClient(app) as client:
                def get(path, **kw):
                    return client.get(base + path, params={"actor": "1", **kw})
                def post(path, data):
                    return client.post(base + path, params={"actor": "1"}, json=data)
                assert get("/access").json() == {"allowed": True}
                assert client.get(base + "/access", params={"actor": "2"}).status_code == 403
                assert client.get("/support-operations/123/overview", params={"actor": "1"}).status_code == 404
                overview = get("/overview")
                assert overview.status_code == 200, overview.text
                assert overview.json()["deployment"]["heartbeat"] > 0
                assert overview.json()["global"]["latency_ms"] is None
                assert overview.json()["global"]["users"] == 12
                bot.latency = .125
                assert get("/overview").json()["global"]["latency_ms"] == 125
                channel = MagicMock(spec=discord.TextChannel)
                channel.id = 123
                channel.name = "private-errors"
                guild.default_role = object()
                guild.me = object()
                guild.get_channel = lambda ident: channel if ident == channel.id else None
                permissions = SimpleNamespace(view_channel=True, send_messages=True,
                    read_message_history=True, create_public_threads=True)
                channel.permissions_for.side_effect = lambda member: SimpleNamespace(view_channel=False) if member is guild.default_role else permissions
                assert post("/settings/error-channel", {"channel_id": "123"}).status_code == 200
                channel.permissions_for.side_effect = None
                channel.permissions_for.return_value = permissions
                assert post("/settings/error-channel", {"channel_id": "123"}).status_code == 400
                guild.me = None
                error, _ = ops.upsert_error("test", ValueError("broken"))
                with patch.object(ops, "refresh_error_report", new=AsyncMock(side_effect=on_bot_loop(True))) as refresh:
                    assert post(f'/errors/{error["error_id"]}/status', {"status": "resolved"}).status_code == 200
                    refresh.assert_awaited_once()
                assert post(f'/errors/{error["error_id"]}/status', {"status": "invalid"}).status_code == 400
                with patch.object(ops, "create_developer_ticket", new=AsyncMock(side_effect=on_bot_loop((error, "created")))) as ticket:
                    assert post(f'/errors/{error["error_id"]}/ticket', {}).status_code == 200
                    ticket.assert_awaited_once()
                incident = post("/incidents", {"title": "Test", "severity": "high"})
                assert incident.status_code == 200, incident.text
                ident = incident.json()["incident_id"]
                assert post(f"/incidents/{ident}", {"status": "resolved", "note": "Fixed"}).status_code == 200
                assert post("/incidents", {"title": ""}).status_code == 400
                key = next(iter(feature_flags.FEATURE_DEFAULTS))
                assert post(f"/features/{key}", {"enabled": False, "rollout": 20}).status_code == 200
                assert post(f"/features/{key}", {"enabled": True, "rollout": "bad"}).status_code == 400
                assert not feature_flags.all_values()[key]  # Invalid request made no partial change.
                assert post(f"/features/{key}", {"enabled": "false"}).status_code == 400
                with patch.object(ops, "diagnose_guild", new=AsyncMock(side_effect=on_bot_loop({"findings": [], "checked": 1}))) as diagnosis:
                    assert get(f"/diagnose/{guild.id}").status_code == 200
                    diagnosis.assert_awaited_once()
                assert get(f"/servers/{guild.id}").status_code == 200
                assert get("/servers/123").status_code == 404
                assert get("/premium-history", server_id=str(guild.id), user_id="1").status_code == 200
                assert get("/premium-history").status_code == 400
                assert get("/support-access", server_id=str(guild.id), user_id="1").json() == {"case": None}
                assert post("/support-access/revoke", {"server_id": "bad", "user_id": "1"}).status_code == 400
                with sqlite3.connect("db/admin_config.db") as db:
                    db.execute("INSERT INTO dashboard_support_cases(guild_id,supporter_id,status,created_at,updated_at) VALUES(?,?,?,1,1)", (str(guild.id), "1", "accepted"))
                assert post("/support-access/revoke", {"server_id": str(guild.id), "user_id": "1"}).status_code == 200
                assert get("/support-access", server_id=str(guild.id), user_id="1").json()["case"]["status"] == "closed"
                with patch.object(template_store, "get_template", new=AsyncMock(return_value={"name": "Test", "payload": {"channels": []}})):
                    result = get("/templates/1")
                    assert result.status_code == 200, result.text
                    assert "payload" not in result.json()["template"]
                    assert result.json()["inspection"]["modules"] == ["channels"]
                assert get("/templates/999").status_code == 404
                assert len(get("/overview").json()["incidents"]) == 1
                assert get(f'/errors/{error["error_id"]}').json()["status"] == "resolved"
                assert get("/errors/ERR-MISSING").status_code == 404
                assert post("/incidents", {"title": "Test", "severity": "invalid"}).status_code == 400
                assert post("/incidents", {"title": "x" * 151}).status_code == 400
                assert get("/premium-history", server_id=str(2**80)).status_code == 400
                assert get("/premium-history", user_id="²").status_code == 400
                assert get("/support-access", server_id="²", user_id="1").status_code == 400
                assert get("/servers/²").status_code == 404
                assert client.get(base + "/access", params={"actor": "²"}).status_code == 403
                assert get("/templates/0").status_code == 400
                assert get(f"/templates/{2**80}").status_code == 400
                for n in range(60):
                    ops.upsert_error(f"count:{n}", ValueError("count"))
                result = get("/overview").json()
                assert len(result["errors"]) == 50 and result["global"]["open_errors"] == 60
                assert result["global"]["total_errors"] == 61
                assert any(entry["action"] == "support_access_revoked" for entry in result["audit"])
                # A newer closed case must not hide an older active grant.
                with sqlite3.connect("db/admin_config.db") as db:
                    for status in ["accepted", "accepted", "closed"]:
                        db.execute("INSERT INTO dashboard_support_cases(guild_id,supporter_id,status,created_at,updated_at) VALUES(?,?,?,1,1)", (str(guild.id), "2", status))
                assert get("/support-access", server_id=str(guild.id), user_id="2").json()["case"]["status"] == "accepted"
                result = post("/support-access/revoke", {"server_id": str(guild.id), "user_id": "2"})
                assert result.json()["revoked"] == 2
                with sqlite3.connect("db/admin_config.db") as db:
                    assert db.execute("SELECT COUNT(*) FROM dashboard_support_cases WHERE supporter_id='2' AND status='accepted'").fetchone()[0] == 0
                assert post("/support-access/revoke", {"server_id": str(guild.id), "user_id": "2"}).json()["revoked"] == 0
                for path in ["/overview", f'/errors/{error["error_id"]}', "/support-access"]:
                    assert client.get(base + path, params={"actor": "2", "server_id": "1", "user_id": "1"}).status_code == 403
                    assert client.get(base + path, params={"actor": "", "server_id": "1", "user_id": "1"}).status_code == 403
                assert client.get(f'/support-operations/123/errors/{error["error_id"]}', params={"actor": "1"}).status_code == 404
        finally:
            os.chdir(old)
            set_bot_loop(None)
            bot_loop.call_soon_threadsafe(bot_loop.stop)
            worker.join()
            bot_loop.close()
    print("support operations HTTP: all checks passed")


if __name__ == "__main__":
    main()
