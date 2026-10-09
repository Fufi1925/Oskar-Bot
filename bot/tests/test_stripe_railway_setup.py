"""Railway provisioning cannot cross token scope or expose provider secrets."""
import contextlib
import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bot'))
from utils.stripe_billing import BillingError
spec = importlib.util.spec_from_file_location('stripe_railway_setup', ROOT / 'tools/setup_stripe_railway.py')
railway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(railway)

PROJECT = 'cc07f89d-2778-4349-829d-6818f5919b3e'
SERVICE = '843cb7e8-0b8d-403d-8c21-c219a309fbc8'
ENVIRONMENT = '4a49133c-f668-4bad-b6d5-d991c55759bf'
URL = f'https://railway.com/project/{PROJECT}/service/{SERVICE}?environmentId={ENVIRONMENT}'


class RailwayTests(unittest.IsolatedAsyncioTestCase):
    def target(self):
        with patch.dict(os.environ, {'RAILWAY_TOKEN': 'UNIT_TEST_ONLY'}):
            return railway.RailwayTarget(URL)

    def settings(self):
        return {'STRIPE_MODE': 'live', 'STRIPE_PUBLIC_URL': 'https://bot.example',
                'STRIPE_SECRET_KEY': 'UNIT_TEST_ONLY', 'STRIPE_WEBHOOK_SECRET': 'whsec_UNIT_TEST_ONLY',
                'STRIPE_PORTAL_CONFIGURATION': 'bpc_1', 'STRIPE_PRICE_MONTHLY': 'price_m',
                'STRIPE_PRICE_YEARLY': 'price_y', 'STRIPE_PRICE_LIFETIME': 'price_l'}

    def test_target_rejects_untrusted_urls(self):
        for url in [URL.replace('railway.com', 'railway.com.evil.example'), URL.replace('https:', 'http:'),
                    URL + '&environmentId=' + ENVIRONMENT, URL.replace(SERVICE, 'invalid'),
                    URL.replace('railway.com', 'user:pass@railway.com')]:
            with self.subTest(url=url), self.assertRaises(BillingError): railway.target_ids(url)

    async def test_wrong_environment_token_blocks_all_mutations(self):
        async with self.target() as target:
            target.query = AsyncMock(return_value={'projectToken': {'project': {'id': PROJECT}, 'environment': {'id': 'other'}}})
            with self.assertRaisesRegex(BillingError, 'different project or environment'): await target.preflight()
            self.assertFalse(target.ready)
            with self.assertRaises(BillingError): await target.configure(self.settings())
            self.assertEqual(target.query.await_count, 1)

    async def test_wrong_service_blocks_all_mutations(self):
        async with self.target() as target:
            target.query = AsyncMock(side_effect=[
                {'projectToken': {'project': {'id': PROJECT}, 'environment': {'id': ENVIRONMENT}}},
                {'project': {'id': PROJECT, 'services': {'edges': [{'node': {'id': 'other'}}]},
                             'environments': {'edges': [{'node': {'id': ENVIRONMENT}}]}}}])
            with self.assertRaisesRegex(BillingError, 'does not belong'): await target.preflight()
            self.assertFalse(target.ready)

    async def test_configure_updates_only_stripe_variables_without_replacement(self):
        async with self.target() as target:
            target.query = AsyncMock(side_effect=[
                {'projectToken': {'project': {'id': PROJECT}, 'environment': {'id': ENVIRONMENT}}},
                {'project': {'id': PROJECT, 'services': {'edges': [{'node': {'id': SERVICE}}]},
                             'environments': {'edges': [{'node': {'id': ENVIRONMENT}}]}}},
                {'variableCollectionUpsert': True}])
            with contextlib.redirect_stdout(io.StringIO()) as output:
                await target.preflight()
                await target.configure(self.settings())
            payload = target.query.await_args.args[1]['input']
            self.assertFalse(payload['replace']); self.assertFalse(payload['skipDeploys'])
            self.assertEqual(payload['serviceId'], SERVICE); self.assertEqual(payload['environmentId'], ENVIRONMENT)
            self.assertEqual(set(payload['variables']), set(self.settings()))
            self.assertNotIn('UNIT_TEST_ONLY', output.getvalue()); self.assertNotIn('whsec_', output.getvalue())

    async def test_missing_secret_or_extra_variable_blocks_upload(self):
        async with self.target() as target:
            target.ready = True
            target.query = AsyncMock()
            for settings in [self.settings() | {'UNRELATED_KEY': 'value'}, self.settings() | {'STRIPE_WEBHOOK_SECRET': ''}]:
                with self.assertRaises(BillingError): await target.configure(settings)
            target.query.assert_not_awaited()

    async def test_provider_error_cannot_leak_secrets(self):
        async with self.target() as target:
            target.http.post = AsyncMock(return_value=httpx.Response(200, request=httpx.Request('POST', railway.ENDPOINT),
                                                                    json={'errors': [{'message': 'whsec_UNIT_TEST_ONLY'}]}))
            with self.assertRaises(BillingError) as error: await target.query(railway.TOKEN_QUERY)
            self.assertNotIn('whsec_', str(error.exception))


if __name__ == '__main__': unittest.main()
