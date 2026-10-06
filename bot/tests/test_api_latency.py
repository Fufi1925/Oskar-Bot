"""Status endpoints must remain usable before Discord's first heartbeat."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_bot
from api.routes import admin, bot as bot_routes, support_operations
from utils import support_operations as ops
from unittest.mock import patch


def main():
    fake = SimpleNamespace(latency=float('nan'), guilds=[], commands=[], cogs={},
        shard_count=None, user=None, tree=None, is_ready=lambda: False,
        walk_commands=lambda: iter([]))
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.include_router(bot_routes.router, prefix='/bot')
    app.include_router(support_operations.router, prefix='/support-operations')
    app.dependency_overrides[get_bot] = lambda: fake
    previous = os.getcwd()
    checked = 0
    try:
        with tempfile.TemporaryDirectory() as temp, patch.object(ops, 'OWNER_IDS', [1]):
            os.chdir(temp)
            Path('db').mkdir()
            with TestClient(app) as client:
                for value in [float('nan'), float('inf'), -float('inf'), -1.0, 1e308, 0.0, 0.125]:
                    fake.latency = value
                    available = value in (0.0, 0.125)
                    fake.is_ready = lambda: available
                    for path in ['/admin/stats', '/admin/overview', '/bot/status', '/bot/info', '/bot/numbers', f'/support-operations/{ops.MAIN_SUPPORT_GUILD_ID}/overview?actor=1']:
                        result = client.get(path)
                        assert result.status_code == 200, (value, path, result.text)
                        body = result.json()
                        assert 'NaN' not in result.text and 'Infinity' not in result.text
                        if path == '/admin/stats':
                            assert body['api_latency'] == (f'{value * 1000}ms' if available else 'Nicht verfügbar')
                            sockets = next(node for node in body['nodes'] if node['name'] == 'Auth Sockets')
                            assert sockets['status'] == ('Healthy' if available else 'Booting')
                        elif path == '/bot/info':
                            assert body['latency'] == (f'{value * 1000}ms' if available else 'Nicht verfügbar')
                        else:
                            latency = body['system']['api_latency_ms'] if path == '/admin/overview' else body['global']['latency_ms'] if path.startswith('/support-operations') else body['latency'] if path == '/bot/status' else body['latency_ms']
                            assert latency == (value * 1000 if available else None), (path, latency)
                        checked += 1
    finally:
        os.chdir(previous)
    print(f'API latency: {checked} HTTP checks passed (startup, invalid readings, zero, and connected)')


if __name__ == '__main__':
    main()
