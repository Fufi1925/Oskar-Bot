import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import dashboard_settings, bot
from utils import dashboard_settings as store, account_security

OWNER = '870179991462236170'
USER = '1033826242270609449'


class DashboardSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(store, 'DB_PATH', self.temp.name + '/settings.db'),
                        patch.object(account_security, 'DB_PATH', self.temp.name + '/security.db'),
                        patch.dict(os.environ, {'OWNER_IDS': OWNER, 'ADMIN_IDS': USER, 'DASHBOARD_API_KEY': 'test-service-key'})]
        for p in self.patches: p.start()
        app = FastAPI(); app.include_router(dashboard_settings.router, prefix='/settings'); app.include_router(bot.router, prefix='/bot')
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer test-service-key', 'X-Dashboard-Settings-Actor': OWNER}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def valid(self, uid, issued):
        return self.client.get(f'/bot/account/{uid}/session-valid?issued_at_ms={issued}').json()['valid']

    def test_configured_owners_only_and_service_credentials_always_required(self):
        for method, path, data in [('GET', '/settings/settings', None), ('PATCH', '/settings/settings', {'scopes': ['identify', 'guilds']}), ('POST', '/settings/revoke-all', {})]:
            for headers, expected in [({}, 401), ({'X-Dashboard-Settings-Actor': OWNER}, 401), ({**self.headers, 'X-Dashboard-Settings-Actor': USER}, 403)]:
                self.assertEqual(self.client.request(method, path, headers=headers, json=data).status_code, expected)
        self.assertEqual(self.client.get('/settings/oauth-policy').status_code, 401)
        self.assertEqual(self.client.get('/settings/oauth-policy', headers={'Authorization': 'Bearer test-service-key'}).status_code, 200)
        with patch.dict(os.environ, {'OWNER_IDS': ''}):
            self.assertEqual(self.client.get('/settings/settings', headers=self.headers).status_code, 403)

    def test_selected_scopes_persist_and_mandatory_or_unrelated_scopes_cannot_be_changed(self):
        response = self.client.patch('/settings/settings', headers=self.headers, json={'scopes': ['guilds', 'identify'], 'revoked_before_ms': 999, 'actor': USER})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.read()['scopes'], ['identify', 'guilds']); self.assertEqual(store.read()['updated_by'], OWNER)
        self.assertEqual(store.revoked_before(), 0)
        for scopes in [[], ['identify'], ['identify', 'guilds', 'email'], ['identify', 'guilds', 'guilds.join'], None]:
            self.assertEqual(self.client.patch('/settings/settings', headers=self.headers, json={'scopes': scopes}).status_code, 400)
        self.assertEqual(self.client.get('/settings/oauth-policy', headers=self.headers).json(), {'scopes': ['identify', 'guilds']})

    def test_global_logout_invalidates_every_older_session_and_survives_restart(self):
        with patch.object(store.time, 'time', return_value=1000):
            response = self.client.post('/settings/revoke-all', headers=self.headers)
        self.assertEqual(response.status_code, 200); cutoff = response.json()['revoked_before_ms']
        for uid in (OWNER, USER, '1530349205372145715'):
            self.assertFalse(self.valid(uid, cutoff)); self.assertTrue(self.valid(uid, cutoff + 1))
        self.assertEqual(store.revoked_before(), cutoff)
        with patch.object(store.time, 'time', return_value=999):
            later = store.revoke_everyone(OWNER)
        self.assertGreater(later, cutoff)

    def test_targeted_logout_affects_only_the_selected_account(self):
        with patch.object(account_security.time, 'time', return_value=1000):
            response = self.client.post('/settings/revoke-user', headers=self.headers, json={'user_id': USER})
        self.assertEqual(response.status_code, 200)
        cutoff = response.json()['revoked_before_ms']
        self.assertFalse(self.valid(USER, cutoff)); self.assertTrue(self.valid(OWNER, cutoff))
        self.assertTrue(self.valid(USER, cutoff + 1)); self.assertEqual(store.revoked_before(), 0)
        for uid in ['1', 'not-an-id', 123, '99999999999999999999']:
            self.assertEqual(self.client.post('/settings/revoke-user', headers=self.headers, json={'user_id': uid}).status_code, 400)


if __name__ == '__main__': unittest.main()
