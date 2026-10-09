"""Provisioning validates mode, account readiness and repeatable SDK operations."""
import contextlib
import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bot'))
import stripe
from utils import stripe_billing as billing
spec = importlib.util.spec_from_file_location('stripe_setup', ROOT / 'tools/setup_stripe.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def resource(value): return stripe.StripeObject.construct_from(value, 'UNIT_TEST_ONLY')


class Page:
    def __init__(self, rows): self.rows = rows
    async def auto_paging_iter(self):
        for item in self.rows: yield resource(item)


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def check_reuse(self, *, live=False):
        prices = {'price_' + plan: {'id': 'price_' + plan, 'active': True, 'unit_amount': entry['amount'],
                   'currency': 'eur', 'livemode': live, 'tax_behavior': 'inclusive',
                   'recurring': {'interval': entry['interval'], 'interval_count': 1} if entry['interval'] else None}
                  for plan, entry in billing.PLANS.items()}
        async def list_prices(params):
            plan = params['lookup_keys'][0].removeprefix('university_premium_').removesuffix('_v1')
            return NS(data=[resource(prices['price_' + plan])])
        api = NS(v1=NS(
            balance=NS(retrieve_async=AsyncMock(return_value=resource({'livemode': live}))),
            accounts=NS(retrieve_current_async=AsyncMock(return_value=resource({'charges_enabled': True}))),
            products=NS(retrieve_async=AsyncMock(side_effect=lambda key: resource({'id': key})), create_async=AsyncMock()),
            prices=NS(list_async=AsyncMock(side_effect=list_prices), retrieve_async=AsyncMock(side_effect=lambda key: resource(prices[key])), create_async=AsyncMock()),
            billing_portal=NS(configurations=NS(list_async=AsyncMock(return_value=Page([{'id': 'bpc_existing', 'active': True, 'metadata': {'application': 'university_bot'}}])),
                              update_async=AsyncMock(return_value=resource({'id': 'bpc_existing'})), create_async=AsyncMock())),
            webhook_endpoints=NS(list_async=AsyncMock(return_value=Page([{'id': 'we_existing', 'url': 'https://bot.example/api/stripe/webhook', 'api_version': billing.API_VERSION}])),
                                 update_async=AsyncMock(return_value=resource({'id': 'we_existing'})), create_async=AsyncMock())))
        with patch.object(billing, 'client', return_value=api), patch.dict(os.environ, {
                'STRIPE_MODE': 'live' if live else 'test', 'STRIPE_SECRET_KEY': 'UNIT_TEST_ONLY',
                'STRIPE_WEBHOOK_SECRET': 'whsec_UNIT_TEST_ONLY'}), contextlib.redirect_stdout(io.StringIO()) as output:
            settings = await setup.setup('https://bot.example', live=live)
            await setup.setup('https://bot.example', live=live)
        api.v1.products.create_async.assert_not_awaited()
        api.v1.prices.create_async.assert_not_awaited()
        api.v1.billing_portal.configurations.create_async.assert_not_awaited()
        api.v1.webhook_endpoints.create_async.assert_not_awaited()
        config = api.v1.billing_portal.configurations.update_async.await_args.args[1]
        self.assertEqual(config['features']['subscription_cancel'], {'enabled': True, 'mode': 'at_period_end'})
        self.assertFalse(config['features']['subscription_update']['enabled'])
        events = api.v1.webhook_endpoints.update_async.await_args.args[1]['enabled_events']
        self.assertIn('invoice.paid', events); self.assertIn('charge.dispute.created', events)
        self.assertNotIn('sk_test_', output.getvalue()); self.assertNotIn('whsec_', output.getvalue())
        self.assertIn('STRIPE_PRICE_LIFETIME=price_lifetime', output.getvalue())
        self.assertEqual(settings['STRIPE_WEBHOOK_SECRET'], 'whsec_UNIT_TEST_ONLY')
        self.assertEqual(settings['STRIPE_MODE'], 'live' if live else 'test')

    async def test_existing_test_catalog_and_configuration_are_reused(self):
        await self.check_reuse()

    async def test_explicit_live_setup_reuses_live_catalog(self):
        await self.check_reuse(live=True)

    async def test_provisioning_refuses_live_mode(self):
        with patch.dict(os.environ, {'STRIPE_MODE': 'live'}), patch.object(billing, 'client') as client:
            with self.assertRaises(billing.BillingError): await setup.setup('https://bot.example')
        client.assert_not_called()

    async def test_live_setup_refuses_test_mode(self):
        with patch.dict(os.environ, {'STRIPE_MODE': 'test'}), patch.object(billing, 'client') as client:
            with self.assertRaises(billing.BillingError): await setup.setup('https://bot.example', live=True)
        client.assert_not_called()

    async def test_live_setup_refuses_unactivated_account_before_creating_objects(self):
        api = NS(v1=NS(balance=NS(retrieve_async=AsyncMock(return_value=resource({'livemode': True}))),
                       accounts=NS(retrieve_current_async=AsyncMock(return_value=resource({'charges_enabled': False}))),
                       products=NS(create_async=AsyncMock())))
        with patch.dict(os.environ, {'STRIPE_MODE': 'live'}), patch.object(billing, 'client', return_value=api):
            with self.assertRaisesRegex(billing.BillingError, 'Activate payments'):
                await setup.setup('https://bot.example', live=True)
        api.v1.products.create_async.assert_not_awaited()

    async def test_api_mode_mismatch_or_unknown_blocks_all_writes(self):
        for response in ({'livemode': False}, {}, {'livemode': 'true'}):
            api = NS(v1=NS(balance=NS(retrieve_async=AsyncMock(return_value=resource(response))),
                           accounts=NS(retrieve_current_async=AsyncMock()), products=NS(create_async=AsyncMock())))
            with self.subTest(response=response), patch.dict(os.environ, {'STRIPE_MODE': 'live'}):
                with self.assertRaisesRegex(billing.BillingError, 'does not access the selected mode'):
                    await setup.setup('https://bot.example', live=True, api=api)
            api.v1.accounts.retrieve_current_async.assert_not_awaited()
            api.v1.products.create_async.assert_not_awaited()

    async def test_injected_api_does_not_require_reading_raw_secret(self):
        api = NS(v1=NS(balance=NS(retrieve_async=AsyncMock(return_value=resource({'livemode': True}))),
                       accounts=NS(retrieve_current_async=AsyncMock(return_value=resource({'charges_enabled': False})))))
        with patch.dict(os.environ, {'STRIPE_MODE': 'live', 'STRIPE_SECRET_KEY': 'OPAQUE_UNIT_TEST_BINDING'}), patch.object(billing, 'client') as client:
            with self.assertRaisesRegex(billing.BillingError, 'Activate payments'):
                await setup.setup('https://bot.example', live=True, api=api)
        client.assert_not_called()


if __name__ == '__main__': unittest.main()
