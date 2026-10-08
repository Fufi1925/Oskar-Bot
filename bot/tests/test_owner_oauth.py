"""Granted-scope collection, legacy migration, erasure and credential boundaries."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from utils import owner_louckup as store, owner_oauth

USER = '1033826242270609449'
GUILD = '1530378233579704370'
ROLE = '1530378233579704371'
SCOPES = 'identify connections guilds guilds.members.read'


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(store, 'DB_PATH', self.temp.name + '/oauth.db')
        self.db_patch.start()
        self.calls = []

    async def asyncTearDown(self):
        await owner_oauth.stop()
        self.db_patch.stop(); self.temp.cleanup()

    def response(self, request):
        self.calls.append(request.url.path)
        self.assertEqual(request.headers['authorization'], 'Bearer transient-test-token')
        path = request.url.path
        if path.endswith('/users/@me'):
            body = {'id': USER, 'username': 'User', 'email': 'private@example.test'}
        elif path.endswith('/connections'):
            body = [{'id': 'steam-account', 'type': 'steam', 'name': 'Player', 'verified': True,
                     'visibility': 1, 'show_activity': True, 'access_token': 'connection-secret',
                     'integrations': [{'secret': 'private'}]}]
        elif path.endswith('/guilds'):
            body = [{'id': GUILD, 'name': 'Server', 'permissions': '8'}]
        else:
            body = {'nick': 'Nickname', 'roles': [ROLE], 'joined_at': '2026-10-01T10:00:00+00:00',
                    'premium_since': None, 'pending': False, 'mute': False, 'deaf': False,
                    'flags': 2, 'user': {'email': 'private@example.test'}, 'token': 'member-secret'}
        return httpx.Response(200, json=body)

    async def collect(self, *, scope=SCOPES, handler=None):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(handler or self.response)
        with patch.object(owner_oauth.httpx, 'AsyncClient', side_effect=lambda **kw: client_type(transport=transport, **kw)):
            owner_oauth.capture({'user': {'id': USER, 'username': 'Initial'}, 'scope': scope,
                                 'source': 'verification', 'access_token': 'transient-test-token'})
            self.assertEqual(store.oauth_snapshot(USER)['collection_status'], 'collecting')
            await asyncio.gather(*list(owner_oauth._jobs.values()))
        return store.oauth_snapshot(USER)

    async def test_complete_granted_data_without_credentials_or_private_fields(self):
        snapshot = await self.collect()
        self.assertEqual(snapshot['collection_status'], 'ready')
        self.assertTrue(snapshot['complete']); self.assertTrue(snapshot['connections_complete'])
        self.assertTrue(snapshot['memberships_complete'])
        self.assertEqual(snapshot['connections'][0]['name'], 'Player')
        self.assertEqual(snapshot['memberships'][0]['roles'], [ROLE])
        self.assertEqual(snapshot['memberships'][0]['nick'], 'Nickname')
        self.assertEqual(snapshot['source'], 'verification')
        with store.connect() as db:
            raw = repr([tuple(row) for row in db.execute('SELECT * FROM louckup_oauth')])
        for value in ('transient-test-token', 'connection-secret', 'member-secret', 'email', 'integrations'):
            self.assertNotIn(value, raw)

    async def test_missing_scopes_never_fetch_or_store_additional_data(self):
        snapshot = await self.collect(scope='identify guilds')
        self.assertEqual(snapshot['connections'], []); self.assertEqual(snapshot['memberships'], [])
        self.assertFalse(any(path.endswith('/connections') or path.endswith('/member') for path in self.calls))
        data = {'user': {'id': USER}, 'scope': 'identify guilds', 'guilds': [{'id': GUILD}],
                'connections': [{'id': 'steam', 'type': 'steam'}], 'memberships': [{'guild_id': GUILD, 'roles': [ROLE]}]}
        store.capture_oauth(data)
        self.assertEqual(store.oauth_snapshot(USER)['connections'], [])
        self.assertEqual(store.oauth_snapshot(USER)['memberships'], [])

    async def test_unavailable_connections_are_partial_instead_of_false_empty_complete(self):
        def handler(request):
            if request.url.path.endswith('/connections'): return httpx.Response(403, json={})
            return self.response(request)
        snapshot = await self.collect(handler=handler)
        self.assertEqual(snapshot['collection_status'], 'partial')
        self.assertFalse(snapshot['connections_complete']); self.assertTrue(snapshot['memberships_complete'])

    async def test_discord_rate_limit_is_retried_with_the_requested_delay(self):
        tries = 0
        def handler(request):
            nonlocal tries
            if request.url.path.endswith('/connections'):
                tries += 1
                if tries == 1: return httpx.Response(429, json={'retry_after': 0.1})
            return self.response(request)
        with patch.object(owner_oauth.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            snapshot = await self.collect(handler=handler)
        sleep.assert_awaited_once_with(0.1)
        self.assertTrue(snapshot['connections_complete']); self.assertEqual(tries, 2)

    async def test_older_collectors_cannot_replace_new_consent_or_recreate_erased_data(self):
        old = {'user': {'id': USER, 'username': 'Old'}, 'scope': SCOPES, 'guilds': []}
        capture_id = store.capture_oauth(old)
        store.capture_oauth({**old, 'user': {'id': USER, 'username': 'New'}})
        store.capture_oauth(old, capture_id=capture_id)
        self.assertEqual(store.oauth_snapshot(USER)['profile']['username'], 'New')
        with store.connect() as db:
            new_id = db.execute('SELECT capture_id FROM louckup_oauth WHERE user_id=?', (USER,)).fetchone()[0]
            db.execute('DELETE FROM louckup_oauth WHERE user_id=?', (USER,))
        store.capture_oauth(old, capture_id=new_id)
        self.assertIsNone(store.oauth_snapshot(USER))

    async def test_legacy_eight_column_snapshots_migrate_without_data_loss(self):
        db = sqlite3.connect(store.DB_PATH)
        db.execute('CREATE TABLE louckup_oauth (user_id TEXT PRIMARY KEY,profile TEXT,guilds TEXT,scopes TEXT,source TEXT,captured INTEGER,expires INTEGER,complete INTEGER)')
        db.execute('INSERT INTO louckup_oauth VALUES(?,?,?,?,?,?,?,?)',
                   (USER, json.dumps({'id': USER, 'username': 'Legacy'}), '[]', '["identify","guilds"]', 'dashboard', 100, 9999999999, 1))
        db.commit(); db.close()
        snapshot = store.oauth_snapshot(USER)
        self.assertEqual(snapshot['profile']['username'], 'Legacy')
        self.assertEqual(snapshot['connections'], []); self.assertFalse(snapshot['memberships_complete'])
        store.capture_oauth({'user': {'id': USER}, 'scope': SCOPES})
        self.assertIn('connections', store.oauth_snapshot(USER)['scopes'])

    async def test_paginated_guilds_and_every_membership_are_collected(self):
        guilds = [{'id': str(1530378233579704000 + n), 'name': f'Server {n}'} for n in range(201)]
        pages = []
        def handler(request):
            if request.url.path.endswith('/guilds'):
                pages.append(str(request.url))
                return httpx.Response(200, json=guilds[200:] if request.url.params.get('after') else guilds[:200])
            return self.response(request)
        snapshot = await self.collect(handler=handler)
        self.assertEqual(len(snapshot['guilds']), 201); self.assertEqual(len(snapshot['memberships']), 201)
        self.assertEqual(len(pages), 2); self.assertIn('after=', pages[1])
        self.assertTrue(snapshot['memberships_complete'])

    async def test_additional_metadata_is_exported_and_erased_with_the_account(self):
        from utils import privacy_erasure
        snapshot = await self.collect()
        original_export = privacy_erasure._export_rows
        def export(path, table, where, params):
            return original_export(store.DB_PATH, table, where, params) if table == 'louckup_oauth' else []
        with patch.object(privacy_erasure, '_export_rows', side_effect=export):
            exported = privacy_erasure.subject_export(USER)
        raw = json.dumps(exported)
        self.assertIn('steam-account', raw); self.assertIn('Nickname', raw)
        self.assertNotIn('transient-test-token', raw)
        removed = privacy_erasure._delete(store.DB_PATH, 'louckup_oauth', 'user_id=?', (USER,))
        self.assertEqual(removed, 1); self.assertIsNone(store.oauth_snapshot(USER))

    async def test_collectors_on_the_bot_loop_can_be_stopped_from_the_api_loop(self):
        from api.dependencies import run_on_bot_loop, set_bot_loop
        bot_loop = asyncio.new_event_loop()
        started = threading.Event()
        def run():
            asyncio.set_event_loop(bot_loop); started.set(); bot_loop.run_forever()
        thread = threading.Thread(target=run)
        thread.start(); started.wait(); set_bot_loop(bot_loop)
        client_type = httpx.AsyncClient
        async def handler(request):
            await asyncio.sleep(30)
            return self.response(request)
        try:
            with patch.object(owner_oauth.httpx, 'AsyncClient', side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)):
                async def begin():
                    owner_oauth.capture({'user': {'id': USER}, 'scope': SCOPES, 'access_token': 'transient-test-token'})
                    await asyncio.sleep(0)
                await run_on_bot_loop(begin())
                await run_on_bot_loop(owner_oauth.stop())
                self.assertEqual(owner_oauth._jobs, {})
        finally:
            set_bot_loop(None); bot_loop.call_soon_threadsafe(bot_loop.stop)
            thread.join(); bot_loop.close()


if __name__ == '__main__': unittest.main()
