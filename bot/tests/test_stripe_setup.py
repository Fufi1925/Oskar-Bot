"""Provisioning uses supported SDK resource shapes and is repeatable in test mode."""
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
    async def test_existing_catalog_and_configuration_are_reused(self):
        prices = {'price_' + plan: {'id': 'price_' + plan, 'active': True, 'unit_amount': entry['amount'],
                   'currency': 'eur', 'livemode': False, 'tax_behavior': 'inclusive',
                   'recurring': {'interval': entry['interval'], 'interval_count': 1} if entry['interval'] else None}
                  for plan, entry in billing.PLANS.items()}
        async def list_prices(params):
            plan = params['lookup_keys'][0].removeprefix('university_premium_').removesuffix('_v1')
            return NS(data=[resource(prices['price_' + plan])])
        api = NS(v1=NS(
            products=NS(retrieve_async=AsyncMock(side_effect=lambda key: resource({'id': key})), create_async=AsyncMock()),
            prices=NS(list_async=AsyncMock(side_effect=list_prices), retrieve_async=AsyncMock(side_effect=lambda key: resource(prices[key])), create_async=AsyncMock()),
            billing_portal=NS(configurations=NS(list_async=AsyncMock(return_value=Page([{'id': 'bpc_existing', 'active': True, 'metadata': {'application': 'university_bot'}}])),
                              update_async=AsyncMock(return_value=resource({'id': 'bpc_existing'})), create_async=AsyncMock())),
            webhook_endpoints=NS(list_async=AsyncMock(return_value=Page([{'id': 'we_existing', 'url': 'https://bot.example/api/stripe/webhook', 'api_version': billing.API_VERSION}])),
                                 update_async=AsyncMock(return_value=resource({'id': 'we_existing'})), create_async=AsyncMock())))
        with patch.object(billing, 'client', return_value=api), patch.dict(os.environ, {'STRIPE_MODE': 'test'}), contextlib.redirect_stdout(io.StringIO()) as output:
            await setup.setup('https://bot.example')
            await setup.setup('https://bot.example')
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

    async def test_provisioning_refuses_live_mode(self):
        with patch.dict(os.environ, {'STRIPE_MODE': 'live'}), patch.object(billing, 'client') as client:
            with self.assertRaises(billing.BillingError): await setup.setup('https://bot.example')
        client.assert_not_called()


if __name__ == '__main__': unittest.main()
