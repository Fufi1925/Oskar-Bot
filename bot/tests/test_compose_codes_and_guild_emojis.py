"""Regression tests for reusable compose codes and live guild emojis.

The API module is loaded with tiny dependency stubs so these storage tests run in
minimal CI images that do not install discord.py.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Router:
    def get(self, *_args, **_kwargs):
        return lambda fn: fn

    post = get


def _load_compose(monkeypatch, tmp_path):
    fastapi = types.ModuleType("fastapi")
    fastapi.APIRouter = Router
    fastapi.Depends = lambda value: value
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda value, **_kwargs: value
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    monkeypatch.setitem(sys.modules, "discord", types.ModuleType("discord"))
    monkeypatch.setitem(sys.modules, "httpx", types.ModuleType("httpx"))

    dependencies = types.ModuleType("api.dependencies")
    dependencies.get_bot = lambda: None
    monkeypatch.setitem(sys.modules, "api", types.ModuleType("api"))
    monkeypatch.setitem(sys.modules, "api.dependencies", dependencies)

    utils = types.ModuleType("utils")
    utils.feature_audit = types.SimpleNamespace()
    utils.message_builder = types.SimpleNamespace(
        validate=lambda _payload: [], LIMITS={}, describe=lambda _payload: "",
    )
    monkeypatch.setitem(sys.modules, "utils", utils)

    spec = importlib.util.spec_from_file_location(
        "compose_under_test", ROOT / "bot/api/routes/compose.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module.COMPOSE_CODES_DB = str(tmp_path / "compose_codes.db")
    return module


def test_code_is_eight_digits_and_payload_roundtrips_repeatedly(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)
    payload = {
        "kind": "v2",
        "channel_id": "123456789012345678",
        "color": "#1e90ff",
        "blocks": [
            {"type": "text", "text": "Hallo <:wave:123456789012345678>"},
            {"type": "divider", "invisible": False},
            {"type": "buttons", "buttons": [{"label": "Öffnen", "url": "https://example.com", "emoji": "<a:go:223456789012345678>"}]},
        ],
        "allow_mentions": True,
        "pin": True,
        "sender": "main",
    }
    created = asyncio.run(compose.create_compose_code(42, payload, actor="7"))
    code = created["code"]
    assert len(code) == 8 and code.isdigit()

    imported = asyncio.run(compose.import_compose_code(42, {"code": code}, actor="8"))
    assert imported["payload"] == payload
    assert created['single_use'] is False
    for actor in ('9', '10', '11'):
        again = asyncio.run(compose.import_compose_code(42, {"code": code}, actor=actor))
        assert again['payload'] == payload
        assert again['consumed'] is False


def test_parallel_imports_both_succeed(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)
    code = asyncio.run(compose.create_compose_code(42, {"kind": "text", "content": "snapshot"}))["code"]
    barrier = threading.Barrier(2)
    outcomes: list[int] = []

    def consume(actor: str):
        barrier.wait()
        try:
            asyncio.run(compose.import_compose_code(42, {"code": code}, actor=actor))
            outcomes.append(200)
        except HTTPException as exc:
            outcomes.append(exc.status_code)

    threads = [threading.Thread(target=consume, args=(str(index),)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [200, 200]


def test_previously_consumed_code_is_reusable_and_cross_server_targets_are_reset(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)
    payload = {'kind': 'text', 'content': 'Saved message', 'channel_id': '123456789012345678', 'sender': 'status', 'pin': True}
    code = asyncio.run(compose.create_compose_code(42, payload, actor='7'))['code']
    db = compose._compose_codes_db()
    with db:
        db.execute('UPDATE compose_codes SET used_at=1,used_by=? WHERE code=?', ('8', code))
    db.close()
    imported = asyncio.run(compose.import_compose_code(99, {'code': code}, actor='9'))
    assert imported['cross_server'] is True and imported['consumed'] is False
    assert imported['payload'] == {**payload, 'channel_id': '', 'sender': 'main'}
    assert asyncio.run(compose.import_compose_code(42, {'code': code}, actor='10'))['payload'] == payload


def test_server_library_lists_all_authors_with_pagination_and_isolated_preview(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)
    saved = []
    for actor in ('7', '8', '9'):
        saved.append(asyncio.run(compose.create_compose_code(42, {'kind': 'text', 'content': f'Message by {actor}'}, actor=actor))['code'])
    other = asyncio.run(compose.create_compose_code(99, {'kind': 'text', 'content': 'Other server'}))['code']
    first = asyncio.run(compose.list_compose_codes(42, offset=0, limit=2))
    second = asyncio.run(compose.list_compose_codes(42, offset=first['next_offset'], limit=2))
    assert first['total'] == second['total'] == 3 and second['next_offset'] is None
    assert {row['code'] for row in first['codes'] + second['codes']} == set(saved)
    assert all('payload' not in row and 'created_by' not in row for row in first['codes'])
    preview = asyncio.run(compose.preview_compose_code(42, saved[0]))
    assert preview['payload']['content'] == 'Message by 7'
    with pytest.raises(HTTPException) as denied:
        asyncio.run(compose.preview_compose_code(42, other))
    assert denied.value.status_code == 404
    db = compose._compose_codes_db()
    assert db.execute('SELECT used_at FROM compose_codes WHERE code=?', (saved[0],)).fetchone()[0] is None
    db.close()


def test_invalid_and_unknown_import_codes_do_not_load_a_design(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)
    for code, status in [('abc', 400), ('12345678', 404)]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(compose.import_compose_code(42, {'code': code}))
        assert error.value.status_code == status


def test_guild_emojis_include_static_and_animated(monkeypatch, tmp_path):
    compose = _load_compose(monkeypatch, tmp_path)

    class Emoji:
        def __init__(self, emoji_id, name, animated):
            self.id, self.name, self.animated = emoji_id, name, animated
            self.url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}"

    guild = types.SimpleNamespace(emojis=[Emoji(20, "wave", False), Emoji(21, "party", True)])
    bot = types.SimpleNamespace(get_guild=lambda guild_id: guild if guild_id == 42 else None)
    answer = asyncio.run(compose.guild_emojis(42, bot))
    assert [item["raw"] for item in answer["emojis"]] == ["<a:party:21>", "<:wave:20>"]
    assert answer["groups"] == ["Server-Emojis"]


def test_dashboard_wires_codes_and_appends_server_emojis():
    panel = (ROOT / "dashboard/components/dashboard/compose-panel.tsx").read_text()
    picker = (ROOT / "dashboard/components/dashboard/emoji-picker.tsx").read_text()
    api = (ROOT / "dashboard/lib/api.ts").read_text()
    proxy = (ROOT / "dashboard/app/api/bot/[...path]/route.ts").read_text()
    assert "Import über Code" in panel
    assert "Als Code speichern" in panel
    assert "saved.blocks.map" in panel and "id: nextId++" in panel
    assert "getGuildEmojis(guildId)" in picker
    assert "...botEmojis" in picker and "...serverEmojis.filter" in picker
    assert "createComposeCode" in api and "importComposeCode" in api
    assert 'rest[1] === "emojis" && request.method === "GET"' in proxy
