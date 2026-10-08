"""Security boundaries and real RFC 6238 / six-digit TOTP behavior."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from utils import owner_louckup as store
from api.routes import owner_louckup as route
from api.dependencies import get_bot

OWNER = '870179991462236170'
USER = '1033826242270609449'
KEY = base64.b32encode(b'12345678901234567890').decode()


class LouckupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(store, 'DB_PATH', self.temp.name + '/data.db'),
            patch.dict(os.environ, {'OWNER_IDS': OWNER, 'ADMIN_IDS': USER, 'DASHBOARD_API_KEY': 'service-test-key', 'OWNER_LOUCKUP_TOTP_SECRET': KEY}),
            patch.object(store.time, 'time', return_value=1_000_000_000)]
        for p in self.patches: p.start()
        app = FastAPI(); app.include_router(route.router, prefix='/owner-louckup')
        app.dependency_overrides[get_bot] = lambda: object()
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer service-test-key', 'X-Louckup-Actor': OWNER, 'X-Louckup-Session': 'a'*64}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def unlock(self):
        response = self.client.post('/owner-louckup/unlock', headers=self.headers, json={'code': store.totp(store.authenticator_key(), int(store.time.time())//30)})
        self.assertEqual(response.status_code, 200)
        return response.json()['grant']

    def test_rfc_6238_sha1_vector_with_six_digits(self):
        self.assertEqual(store.totp(b'12345678901234567890', 59//30), '287082')
        self.assertNotEqual(store.totp(b'12345678901234567890', 2), store.totp(b'12345678901234567890', 3))

    def test_service_key_required_even_with_forged_owner_headers(self):
        for headers in ({}, {**self.headers, 'Authorization': 'Bearer wrong'}, {**self.headers, 'Authorization': ''}):
            self.assertEqual(self.client.get('/owner-louckup/status', headers=headers).status_code, 401)

    def test_admin_and_database_roles_cannot_become_owners(self):
        self.assertEqual(store.owner_ids(), {OWNER})
        headers = {**self.headers, 'X-Louckup-Actor': USER}
        self.assertEqual(self.client.get('/owner-louckup/status', headers=headers).status_code, 403)
        with patch.dict(os.environ, {'OWNER_IDS': ''}):
            self.assertEqual(self.client.get('/owner-louckup/status', headers=self.headers).status_code, 403)

    def test_lookup_cannot_bypass_2fa(self):
        with patch.object(route.user_lookup, 'lookup', new_callable=AsyncMock) as lookup:
            self.assertEqual(self.client.get('/owner-louckup/users/' + USER, headers=self.headers).status_code, 403)
            lookup.assert_not_awaited()

    def test_grant_binding_expiry_rotation_and_logout(self):
        grant = self.unlock()
        self.assertTrue(store.grant_expires(OWNER, 'a'*64, grant))
        self.assertFalse(store.grant_expires(USER, 'a'*64, grant))
        self.assertFalse(store.grant_expires(OWNER, 'b'*64, grant))
        with patch.object(store.time, 'time', return_value=1_000_000_601):
            self.assertFalse(store.grant_expires(OWNER, 'a'*64, grant))
        with patch.dict(os.environ, {'OWNER_LOUCKUP_TOTP_SECRET': base64.b32encode(b'x'*20).decode()}):
            self.assertFalse(store.grant_expires(OWNER, 'a'*64, grant))
        store.lock(grant); self.assertFalse(store.grant_expires(OWNER, 'a'*64, grant))

    def test_grants_are_hashed_and_codes_are_not_logged(self):
        grant = self.unlock()
        with store.connect() as db:
            saved = repr([tuple(r) for r in db.execute('SELECT * FROM louckup_grants')])
            self.assertNotIn(grant, saved); self.assertNotIn(KEY, saved)
            audit = db.execute('SELECT event FROM louckup_audit').fetchall()
            self.assertEqual(audit[0][0], 'unlocked')

    def test_replay_is_rejected_and_failures_survive_requests(self):
        self.unlock()
        code = store.totp(store.authenticator_key(), int(store.time.time())//30)
        self.assertEqual(self.client.post('/owner-louckup/unlock', headers=self.headers, json={'code':code}).status_code, 401)
        for _ in range(3):
            self.assertEqual(self.client.post('/owner-louckup/unlock', headers=self.headers, json={'code':'über'}).status_code, 401)
        response = self.client.post('/owner-louckup/unlock', headers=self.headers, json={'code':'bad'})
        self.assertEqual(response.status_code, 429); self.assertEqual(response.headers['retry-after'], '300')
        with patch.object(store.time, 'time', return_value=1_000_000_301):
            self.unlock()

    def test_missing_authenticator_key_fails_closed(self):
        with patch.dict(os.environ, {'OWNER_LOUCKUP_TOTP_SECRET':''}):
            self.assertFalse(self.client.get('/owner-louckup/status', headers=self.headers).json()['configured'])
            self.assertEqual(self.client.post('/owner-louckup/unlock', headers=self.headers, json={'code':'123456'}).status_code, 503)

    def test_snapshot_allowlist_retention_and_no_credentials(self):
        store.capture_oauth({'user': {'id':USER, 'username':'Test', 'email':'private@example.test', 'password':'secret'},
            'guilds':[{'id':OWNER, 'name':'Test server', 'owner':True, 'permissions':'8', 'token':'secret'}],
            'scope':'identify guilds email', 'access_token':'secret', 'refresh_token':'secret', 'complete':True})
        data = store.oauth_snapshot(USER)
        serialized = json.dumps(data)
        for word in ('password', 'secret', 'email', 'token', 'private@example'): self.assertNotIn(word, serialized)
        self.assertEqual(data['guilds'][0]['id'], OWNER); self.assertTrue(data['complete'])
        with patch.object(store.time, 'time', return_value=1_000_000_000 + store.SNAPSHOT_SECONDS + 1):
            self.assertIsNone(store.oauth_snapshot(USER))

    def test_bot_data_allowlist_does_not_leak_private_extra_fields(self):
        grant = self.unlock()
        data={'user_id':USER,'found':True,'username':'Test','guilds':[], 'bot_ban':None,
              'access_token':'secret','email':'private@example.test','history':[{'password':'secret'}]}
        with patch.object(route.user_lookup, 'lookup', AsyncMock(return_value=data)), patch.object(store, 'login_summary', return_value=None):
            response=self.client.get('/owner-louckup/users/'+USER, headers={**self.headers,'X-Louckup-Grant':grant})
        self.assertEqual(response.status_code,200)
        for word in ('password','token','secret','email'): self.assertNotIn(word,response.text)
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT target FROM louckup_audit WHERE event='lookup'").fetchone()[0], USER)


if __name__ == '__main__': unittest.main()
