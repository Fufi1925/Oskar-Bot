"""Payment-backed Premium boundaries; no Stripe network or real credentials."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import stripe
from fastapi import FastAPI
from utils import stripe_billing as billing, premium_membership as membership, premium_notifications
from api.routes import stripe_billing as routes

UID = '123456789012345678'
OTHER = '223456789012345678'


class BillingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(membership, 'DB_PATH', self.temp.name + '/premium.db'),
                        patch.dict(os.environ, {'STRIPE_MODE': 'test', 'STRIPE_SECRET_KEY': 'sk_test_UNIT_TEST_ONLY',
                         'STRIPE_WEBHOOK_SECRET': 'whsec_UNIT_TEST_ONLY', 'STRIPE_PRICE_MONTHLY': 'price_month',
                         'STRIPE_PRICE_YEARLY': 'price_year', 'STRIPE_PRICE_LIFETIME': 'price_life',
                         'STRIPE_PORTAL_CONFIGURATION': 'bpc_test', 'STRIPE_PUBLIC_URL': 'https://bot.example'})]
        for item in self.patches: item.start()
        self.end = int(time.time()) + 30 * 86400
        self.sub = {'id': 'sub_test', 'customer': 'cus_test', 'status': 'active', 'cancel_at_period_end': False,
                    'metadata': {'application': 'university_bot', 'discord_user_id': UID, 'plan': 'monthly'},
                    'items': {'data': [{'price': {'id': 'price_month'}, 'quantity': 1, 'current_period_end': self.end}]}}
        self.invoice = self.make_invoice('in_one', self.end)
        self.charge = {'id': 'ch_test', 'customer': 'cus_test', 'refunded': False, 'disputed': False}
        self.session = {'id': 'cs_test_session', 'customer': 'cus_test', 'client_reference_id': UID,
                        'metadata': {'application': 'university_bot', 'discord_user_id': UID, 'plan': 'lifetime'},
                        'status': 'complete', 'payment_status': 'paid', 'amount_total': 2999, 'currency': 'eur',
                        'payment_intent': 'pi_test', 'url': 'https://checkout.stripe.com/c/pay/test'}
        self.api = NS(v1=NS(
            prices=NS(retrieve_async=AsyncMock(return_value={'id': 'price_month', 'active': True, 'unit_amount': 299,
                       'currency': 'eur', 'livemode': False, 'tax_behavior': 'inclusive',
                       'recurring': {'interval': 'month', 'interval_count': 1}})),
            customers=NS(create_async=AsyncMock(return_value={'id': 'cus_test'})),
            checkout=NS(sessions=NS(create_async=AsyncMock(return_value={**self.session, 'status': 'open'}),
                        retrieve_async=AsyncMock(side_effect=lambda *args, **kwargs: self.session),
                        expire_async=AsyncMock(), list_line_items_async=AsyncMock(return_value={'data': [{'price': {'id': 'price_life'}, 'quantity': 1}]}))),
            subscriptions=NS(retrieve_async=AsyncMock(side_effect=lambda *args, **kwargs: self.sub), list_async=AsyncMock(), cancel_async=AsyncMock()),
            invoices=NS(retrieve_async=AsyncMock(side_effect=lambda *args, **kwargs: self.invoice)),
            invoice_payments=NS(list_async=AsyncMock(return_value={'data': [{'payment': {'type': 'payment_intent', 'payment_intent': 'pi_test'}}]})),
            payment_intents=NS(retrieve_async=AsyncMock(side_effect=lambda *args, **kwargs: {'latest_charge': self.charge})),
            charges=NS(retrieve_async=AsyncMock(side_effect=lambda *args, **kwargs: self.charge)),
            billing_portal=NS(sessions=NS(create_async=AsyncMock(return_value={'url': 'https://billing.stripe.com/p/session/test'})))))
        self.patches.append(patch.object(billing, 'client', return_value=self.api)); self.patches[-1].start()
        billing.ensure()
        self.bind()

    def bind(self):
        with membership._connect() as db:
            db.execute('INSERT OR IGNORE INTO stripe_customers VALUES(?,?,?)', (UID, 'test', 'cus_test'))

    def make_invoice(self, invoice_id, end):
        return {'id': invoice_id, 'status': 'paid', 'currency': 'eur', 'amount_paid': 299,
                'parent': {'subscription_details': {'subscription': 'sub_test'}},
                'lines': {'data': [{'pricing': {'price_details': {'price': 'price_month'}}, 'period': {'end': end}}]}}

    async def asyncTearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    async def event(self, kind='invoice.paid', eid='evt_one', obj=None):
        return await billing.process_event({'id': eid, 'livemode': False, 'type': kind,
                                           'data': {'object': obj or {'id': 'in_one'}}})

    async def test_catalog_has_authorized_prices_and_modes(self):
        catalog = billing.catalog()
        self.assertEqual([(p['id'], p['amount'], p['interval']) for p in catalog['plans']],
                         [('monthly', 299, 'month'), ('yearly', 1299, 'year'), ('lifetime', 2999, None)])
        self.assertTrue(catalog['enabled']); self.assertEqual(catalog['slots'], 3)
        with patch.dict(os.environ, {'STRIPE_WEBHOOK_SECRET': ''}): self.assertFalse(billing.configured())

    async def test_paid_invoice_and_renewal_use_absolute_periods_and_dedupe(self):
        result = await self.event()
        self.assertEqual(result['notify_user'], UID)
        self.assertEqual(membership.account_status(UID)['expires_at'], self.end)
        self.assertTrue((await self.event())['duplicate'])
        result = await self.event(eid='evt_another')
        self.assertIsNone(result['notify_user'])
        self.assertEqual(membership.account_status(UID)['expires_at'], self.end)
        self.invoice = self.make_invoice('in_two', self.end + 31 * 86400)
        await self.event(eid='evt_renewal', obj={'id': 'in_two'})
        self.assertEqual(membership.account_status(UID)['expires_at'], self.end + 31 * 86400)
        self.invoice = self.make_invoice('in_one', self.end)
        await self.event(eid='evt_old')
        self.assertEqual(membership.account_status(UID)['expires_at'], self.end + 31 * 86400)

    async def test_subscription_checkout_and_active_state_do_not_grant_access(self):
        self.session.update(subscription='sub_test', metadata={**self.sub['metadata']})
        await self.event('checkout.session.completed', obj={'id': self.session['id']})
        self.assertFalse(membership.account_status(UID)['premium'])
        await self.event('customer.subscription.updated', 'evt_sub', {'id': 'sub_test'})
        self.assertFalse(membership.account_status(UID)['premium'])

    async def test_paid_lifetime_works_with_real_sdk_object_shape(self):
        self.session = stripe.StripeObject.construct_from(self.session, 'UNIT_TEST_ONLY')
        await self.event('checkout.session.completed', obj={'id': self.session['id']})
        account = membership.account_status(UID)
        self.assertTrue(account['premium']); self.assertTrue(account['lifetime'])
        self.assertEqual(account['expires_at'], membership.LIFETIME_EXPIRES_AT)

    async def test_delayed_payment_grants_only_after_paid(self):
        self.session['payment_status'] = 'unpaid'
        await self.event('checkout.session.completed', obj={'id': self.session['id']})
        self.assertFalse(membership.account_status(UID)['premium'])
        self.session['payment_status'] = 'paid'
        await self.event('checkout.session.async_payment_succeeded', 'evt_async', {'id': self.session['id']})
        self.assertTrue(membership.account_status(UID)['lifetime'])

    async def test_foreign_customer_cannot_bind_metadata_to_an_account(self):
        self.sub['customer'] = 'cus_foreign'
        await self.event()
        self.assertFalse(membership.account_status(UID)['premium'])

    async def test_wrong_mode_is_refused(self):
        with self.assertRaises(billing.BillingError):
            await billing.process_event({'id': 'evt_live', 'livemode': True, 'type': 'invoice.paid', 'data': {'object': self.invoice}})

    async def test_price_configuration_is_verified_before_checkout(self):
        self.api.v1.prices.retrieve_async.return_value['unit_amount'] = 999
        with self.assertRaises(billing.BillingError): await billing.checkout(UID, 'monthly')
        self.api.v1.checkout.sessions.create_async.assert_not_awaited()

    async def test_idempotent_checkout_uses_trusted_customer_prices_and_urls(self):
        await billing.checkout(UID, 'monthly', 'de')
        await billing.checkout(UID, 'monthly', 'en')
        calls = self.api.v1.checkout.sessions.create_async.await_args_list
        self.assertEqual(calls[0], calls[1])
        params = calls[0].args[0]
        self.assertEqual(params['customer'], 'cus_test'); self.assertEqual(params['locale'], 'de')
        self.assertEqual(params['line_items'], [{'price': 'price_month', 'quantity': 1}])
        self.assertNotIn('payment_method_types', params); self.assertNotIn('automatic_tax', params)
        self.assertGreater(params['expires_at'], int(time.time()) + 1800)
        self.assertRegex(params['integration_identifier'], r'^university_[a-z]{8}$')
        self.assertEqual(params['subscription_data']['metadata']['discord_user_id'], UID)
        self.assertTrue(params['success_url'].startswith('https://bot.example/dashboard/premium'))
        with self.assertRaises(billing.BillingError): await billing.checkout(UID, 'yearly')

    async def test_active_accounts_and_subscriptions_block_double_purchase(self):
        membership.grant_custom(UID, 10)
        with self.assertRaises(billing.BillingError): await billing.checkout(UID, 'monthly')
        membership.revoke(UID)
        await self.event('customer.subscription.created', obj={'id': 'sub_test'})
        with self.assertRaises(billing.BillingError): await billing.checkout(UID, 'monthly')

    async def test_dispute_revokes_runtime_even_with_keep_settings(self):
        await self.event(); membership.assign_slot(UID, 123)
        self.assertTrue(membership.guild_status(123)['billing_managed'])
        with self.assertRaises(ValueError): membership.set_expiry_action(123, 'keep')
        self.charge['disputed'] = True
        await self.event('charge.dispute.created', 'evt_dispute', {'id': 'dp_test', 'charge': 'ch_test'})
        self.assertFalse(membership.account_status(UID)['premium'])
        self.assertFalse(membership.guild_status(123)['runtime'])
        self.assertNotIn(123, membership.runtime_guilds()[0])
        self.assertEqual(len(membership.account_status(UID)['slots']), 1)

    async def test_full_refund_before_delayed_paid_event_never_grants(self):
        self.charge['refunded'] = True
        await self.event('charge.refunded', 'evt_refund', self.charge)
        self.charge['refunded'] = False  # Simulate an older payment snapshot arriving late.
        await self.event()
        self.assertFalse(membership.account_status(UID)['premium'])

    async def test_partial_refund_keeps_access_but_fraud_warning_blocks(self):
        await self.event()
        await self.event('charge.refunded', 'evt_partial', self.charge)
        self.assertTrue(membership.account_status(UID)['premium'])
        await self.event('radar.early_fraud_warning.created', 'evt_warning', {'id': 'issfr_test', 'charge': 'ch_test'})
        self.assertFalse(membership.account_status(UID)['premium'])

    async def test_cancellation_preserves_paid_access_failed_invoice_does_not_extend(self):
        await self.event()
        self.sub.update(status='canceled', cancel_at_period_end=True)
        await self.event('customer.subscription.deleted', 'evt_cancel', {'id': 'sub_test'})
        self.invoice.update(status='open')
        await self.event('invoice.payment_failed', 'evt_failed')
        self.assertTrue(membership.account_status(UID)['premium'])
        self.assertEqual(membership.account_status(UID)['expires_at'], self.end)

    async def test_expired_stripe_access_does_not_freeze_premium_runtime(self):
        self.invoice = self.make_invoice('in_old', int(time.time()) - 1)
        await self.event()
        with membership._connect() as db:
            db.execute('INSERT INTO premium_slots VALUES(?,?,?,?,?)', (UID, 1, 123, 1, 'keep'))
        self.assertFalse(membership.guild_status(123)['runtime'])
        self.assertNotIn(123, membership.runtime_guilds()[0])

    async def test_admin_override_survives_a_stripe_refund(self):
        await self.event(); membership.grant_custom(UID, None)
        self.charge['refunded'] = True
        await self.event('charge.refunded', 'evt_refund', self.charge)
        self.assertTrue(membership.account_status(UID)['lifetime'])
        self.assertEqual(membership.account_status(UID)['source'], 'admin')

    async def test_return_page_is_owner_scoped_and_cannot_fulfill(self):
        result = await billing.checkout_status(UID, self.session['id'])
        self.assertFalse(result['fulfilled']); self.assertFalse(membership.account_status(UID)['premium'])
        with self.assertRaises(billing.BillingError): await billing.checkout_status(OTHER, self.session['id'])
        self.session['client_reference_id'] = OTHER
        with self.assertRaises(billing.BillingError): await billing.checkout_status(UID, self.session['id'])

    async def test_portal_customer_and_configuration_are_server_owned(self):
        await billing.portal(UID)
        params = self.api.v1.billing_portal.sessions.create_async.await_args.args[0]
        self.assertEqual(params, {'customer': 'cus_test', 'configuration': 'bpc_test', 'return_url': 'https://bot.example/dashboard/premium'})
        with self.assertRaises(billing.BillingError): await billing.portal(OTHER)

    async def test_invalid_origin_and_hosted_redirect_are_rejected(self):
        for url in ['http://bot.example', 'https://user:pass@bot.example', 'https://bot.example/path']:
            with patch.dict(os.environ, {'STRIPE_PUBLIC_URL': url}):
                with self.assertRaises(billing.BillingError): billing.origin()
        with self.assertRaises(billing.BillingError): billing.hosted_url('https://evil.example', 'checkout.stripe.com')

    async def test_webhook_signature_and_body_limit(self):
        app = FastAPI(); app.include_router(routes.webhook_router, prefix='/api/stripe')
        self.session['payment_status'] = 'unpaid'
        body = json.dumps({'id': 'evt_signed', 'livemode': False, 'type': 'checkout.session.completed', 'data': {'object': {'id': self.session['id']}}}).encode()
        timestamp = int(time.time())
        digest = hmac.new(b'whsec_UNIT_TEST_ONLY', str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
        signature = f't={timestamp},v1={digest}'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
            self.assertEqual((await http.post('/api/stripe/webhook', content=body)).status_code, 400)
            self.assertEqual((await http.post('/api/stripe/webhook', content=body + b' ', headers={'stripe-signature': signature})).status_code, 400)
            self.assertEqual((await http.post('/api/stripe/webhook', content=body, headers={'stripe-signature': signature})).status_code, 200)
            self.assertEqual((await http.post('/api/stripe/webhook', content=b'x' * 1_048_577)).status_code, 413)
        self.assertFalse(membership.account_status(UID)['premium'])

    async def test_billing_routes_always_require_the_dashboard_api_key(self):
        app = FastAPI(); app.include_router(routes.router, prefix='/premium/billing')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
            with patch.dict(os.environ, {'DASHBOARD_API_KEY': ''}):
                response = await http.get('/premium/billing/catalog', params={'actor': UID})
                self.assertEqual(response.status_code, 503)
            with patch.dict(os.environ, {'DASHBOARD_API_KEY': 'UNIT_TEST_ONLY'}):
                response = await http.get('/premium/billing/catalog', params={'actor': UID})
                self.assertEqual(response.status_code, 401)
                response = await http.get('/premium/billing/catalog', params={'actor': UID}, headers={'Authorization': 'Bearer wrong'})
                self.assertEqual(response.status_code, 401)
                response = await http.get('/premium/billing/catalog', params={'actor': UID}, headers={'Authorization': 'Bearer UNIT_TEST_ONLY'})
                self.assertEqual(response.status_code, 200)

    async def test_stale_subscription_event_cannot_resurrect_a_cancelled_subscription(self):
        self.sub['status'] = 'canceled'
        await billing.process_event({'id': 'evt_new', 'created': 200, 'livemode': False,
                                    'type': 'customer.subscription.deleted', 'data': {'object': {'id': 'sub_test'}}})
        self.sub['status'] = 'active'
        await billing.process_event({'id': 'evt_older', 'created': 100, 'livemode': False,
                                    'type': 'customer.subscription.created', 'data': {'object': {'id': 'sub_test'}}})
        self.assertEqual(billing.summary(UID)['subscriptions'][0]['status'], 'canceled')

    async def test_retry_after_provider_failure_does_not_consume_the_event(self):
        self.api.v1.invoices.retrieve_async.side_effect = stripe.APIConnectionError('UNIT_TEST_ONLY')
        with self.assertRaises(stripe.APIConnectionError): await self.event()
        with membership._connect() as db:
            self.assertFalse(db.execute('SELECT 1 FROM stripe_events').fetchone())
        self.api.v1.invoices.retrieve_async.side_effect = lambda *args, **kwargs: self.invoice
        await self.event()
        self.assertTrue(membership.account_status(UID)['premium'])

    async def test_duplicate_invoice_does_not_restore_a_dismissed_notice(self):
        await self.event(); membership.dismiss_notice(UID)
        await self.event(eid='evt_samepayment')
        self.assertFalse(membership.account_status(UID)['notice_pending'])

    async def test_erasure_cancels_checkout_and_subscriptions(self):
        self.session['status'] = 'open'
        with membership._connect() as db:
            db.execute('INSERT INTO stripe_intents VALUES(?,?,?,?,?,?,?,?)', (UID, 'test', 'monthly', 'nonce', 'en', 1, self.session['id'], 0))
        async def rows(): yield self.sub
        self.api.v1.subscriptions.list_async.return_value = NS(auto_paging_iter=rows)
        await billing.cancel_for_erasure(UID)
        self.api.v1.checkout.sessions.expire_async.assert_awaited_once_with(self.session['id'])
        self.api.v1.subscriptions.cancel_async.assert_awaited_once_with('sub_test', {'invoice_now': False, 'prorate': False})

    async def test_payment_dm_has_custom_emojis_bilingual_v2_and_lifetime(self):
        account = {'expires_at': membership.LIFETIME_EXPIRES_AT, 'max_slots': 3, 'lifetime': True}
        with patch.object(premium_notifications, 'dashboard_url', return_value='https://bot.example'):
            english = str(premium_notifications.payment_view(account).to_components())
            german = str(premium_notifications.payment_view(account, 'de').to_components())
        self.assertIn('Payment confirmed', english); self.assertIn('Zahlung bestätigt', german)
        self.assertIn('<:', english); self.assertIn('Lifetime', english)
        self.assertNotIn(str(membership.LIFETIME_EXPIRES_AT), english)
        self.assertIn('https://bot.example/dashboard/premium', german)


if __name__ == '__main__': unittest.main()
