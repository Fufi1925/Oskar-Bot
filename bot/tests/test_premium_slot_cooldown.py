"""Cooldown boundaries, ownership, atomic approval and unavailable server behavior."""
import os
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.dependencies import get_bot
from api.routes import premium
from utils import premium_membership as store, feature_audit, feature_gates


class CooldownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(store, 'DB_PATH', os.path.join(self.temp.name, 'membership.db'))
        self.db.start()
        self.clock = patch.object(store.time, 'time', return_value=1_800_000_000)
        self.now = self.clock.start()
        store.grant('100', 365)

    def tearDown(self):
        self.clock.stop(); self.db.stop(); self.temp.cleanup()

    def fill(self):
        for gid in (10, 20, 30): store.assign_slot('100', gid)

    def test_release_disables_server_and_blocks_only_released_slot(self):
        self.fill()
        result = store.release_slot('100', 1)
        self.assertEqual(result['available_at'], 1_800_000_000 + 30 * 86400)
        self.assertFalse(store.guild_status(10)['runtime'])
        self.assertTrue(store.guild_status(20)['runtime'])
        self.assertEqual(store.account_status('100')['available_slots'], 0)
        with self.assertRaises(ValueError): store.assign_slot('100', 40)

    def test_other_free_slot_can_be_used_during_cooldown(self):
        store.assign_slot('100', 10); store.assign_slot('100', 20)
        store.release_slot('100', 1)
        self.assertEqual(store.assign_slot('100', 40)['slot_no'], 3)
        self.assertEqual(store.account_status('100')['slot_cooldowns'][0]['slot_no'], 1)

    def test_exact_thirty_day_boundary_and_reload(self):
        self.fill(); result = store.release_slot('100', 1)
        self.now.return_value = result['available_at'] - 1
        with self.assertRaises(ValueError): store.assign_slot('100', 40)
        store.ensure()
        self.assertEqual(len(store.account_status('100')['slot_cooldowns']), 1)
        self.now.return_value = result['available_at']
        self.assertEqual(store.assign_slot('100', 40)['slot_no'], 1)
        self.assertEqual(store.account_status('100')['slot_cooldowns'], [])

    def test_release_cannot_affect_another_account_or_reset_cooldown(self):
        store.assign_slot('100', 10)
        with self.assertRaises(ValueError): store.release_slot('999', 1)
        result = store.release_slot('100', 1)
        self.now.return_value += 100
        with self.assertRaises(ValueError): store.release_slot('100', 1)
        self.assertEqual(store.account_status('100')['slot_cooldowns'][0]['available_at'], result['available_at'])

    def test_expired_account_can_release_without_cooldown_reset_on_renewal(self):
        store.assign_slot('100', 10)
        self.now.return_value += 366 * 86400
        result = store.release_slot('100', 1)
        store.grant('100', 30)
        self.assertEqual(store.account_status('100')['slot_cooldowns'][0]['available_at'], result['available_at'])
        self.assertEqual(store.assign_slot('100', 20)['slot_no'], 2)

    def test_server_identity_survives_assignment_and_refresh(self):
        store.assign_slot('100', 10, guild_name='Community', guild_icon='https://cdn.discordapp.com/icon.png')
        store.remember_slot_guild('100', 10, 'Renamed Community', None)
        slot = store.account_status('100')['slots'][0]
        self.assertEqual(slot['guild_name'], 'Renamed Community')
        self.assertIsNone(slot['guild_icon'])
        store.remember_slot_guild('999', 10, 'Forged', None)
        self.assertEqual(store.account_status('100')['slots'][0]['guild_name'], 'Renamed Community')

    def test_discord_snowflake_is_serialized_without_number_precision_loss(self):
        guild_id = 1530378233579704370
        store.assign_slot('100', guild_id, guild_name='Community')
        self.assertEqual(store.account_status('100')['slots'][0]['guild_id'], str(guild_id))

    def test_admin_revocation_also_reserves_removed_slot(self):
        store.assign_slot('100', 10)
        store.revoke_server(10)
        self.assertFalse(store.guild_status(10)['runtime'])
        self.assertEqual(store.account_status('100')['slot_cooldowns'][0]['slot_no'], 1)

    def test_revoked_account_does_not_run_frozen_features(self):
        store.assign_slot('100', 10); store.revoke('100')
        self.assertFalse(store.guild_status(10)['runtime'])

    def test_concurrent_approval_grants_once(self):
        request = store.request_purchase('200', 30)
        def approve(_):
            try: store.decide_request(request['id'], True, 'admin'); return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(approve, range(2))), 1)
        self.assertEqual(store.account_status('200')['expires_at'], 1_800_000_000 + 30 * 86400)

    def test_lifetime_purchase_is_manually_approved(self):
        request = store.request_purchase('200', 0)
        result = store.decide_request(request['id'], True, 'admin')
        self.assertTrue(result['premium']); self.assertTrue(result['lifetime'])

    def test_legacy_schema_migrates_without_losing_assignments(self):
        with store._connect() as db:
            db.execute('DROP TABLE premium_slots')
            db.execute('CREATE TABLE premium_slots (user_id TEXT,slot_no INTEGER,guild_id INTEGER,assigned_at INTEGER,expiry_action TEXT,PRIMARY KEY(user_id,slot_no))')
            db.execute("INSERT INTO premium_slots VALUES('100',1,10,1800000000,'keep')")
        store.ensure()
        self.assertEqual(store.account_status('100')['slots'][0]['guild_id'], '10')
        store.release_slot('100', 1)
        self.assertEqual(store.account_status('100')['slot_cooldowns'][0]['slot_no'], 1)


class SlotRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(store, 'DB_PATH', os.path.join(self.temp.name, 'membership.db')),
                        patch.object(feature_gates, 'refresh_premium_guilds', new_callable=AsyncMock),
                        patch.object(feature_audit, 'log_action', new_callable=AsyncMock)]
        for item in self.patches: item.start()
        store.grant('100', 30)
        store.assign_slot('100', 10, guild_name='Unavailable Community')
        self.bot = NS(get_guild=Mock(return_value=None))
        app = FastAPI(); app.include_router(premium.router, prefix='/premium')
        app.dependency_overrides[get_bot] = lambda: self.bot
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    async def test_missing_server_has_name_and_can_be_removed(self):
        data = (await self.client.get('/premium/me/100')).json()['premium']
        self.assertEqual(data['slots'][0]['guild_name'], 'Unavailable Community')
        self.assertFalse(data['slots'][0]['bot_present'])
        response = await self.client.post('/premium/slots/1/release', json={'actor': '100'})
        self.assertEqual(response.status_code, 200)
        feature_gates.refresh_premium_guilds.assert_awaited_once()
        self.assertFalse(store.guild_status(10)['runtime'])

    async def test_release_requires_actor_and_owned_slot(self):
        self.assertEqual((await self.client.post('/premium/slots/1/release', json={})).status_code, 401)
        self.assertEqual((await self.client.post('/premium/slots/1/release', json={'actor': '999'})).status_code, 400)
        self.assertTrue(store.guild_status(10)['runtime'])

    async def test_request_requires_explicit_plan_and_supports_lifetime(self):
        self.assertEqual((await self.client.post('/premium/purchase-request', json={'actor': '200'})).status_code, 400)
        result = await self.client.post('/premium/purchase-request', json={'actor': '200', 'duration_days': 0})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(store.list_requests()[0]['duration_days'], 0)


if __name__ == '__main__': unittest.main()
