#!/usr/bin/env python3
"""Provision the authorized test catalog, customer portal and webhook.

Reads credentials exclusively from the process environment. Never prints keys
or webhook secrets. Retrieve the endpoint signing secret in Stripe Dashboard.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bot'))
from utils import stripe_billing as billing


async def setup(public_url):
    if billing.mode() != 'test':
        raise billing.BillingError('This setup command is restricted to test mode.')
    os.environ['STRIPE_PUBLIC_URL'] = public_url
    base = billing.origin()
    api = billing.client()
    products = {}
    for tier, name in [('premium', 'University Bot Premium'), ('lifetime', 'University Bot Premium Lifetime')]:
        key = 'university_' + tier + '_v1'
        products[tier] = await api.v1.products.create_async(
            {'id': key, 'name': name, 'description': 'Premium features for three fixed Discord server slots, including Ticket AI.'},
            options={'idempotency_key': key}) if not await exists_product(api, key) else await api.v1.products.retrieve_async(key)
    for plan, value in billing.PLANS.items():
        lookup = f'university_premium_{plan}_v1'
        found = await api.v1.prices.list_async({'lookup_keys': [lookup], 'active': True, 'limit': 2})
        if len(found.data) > 1:
            raise billing.BillingError('Ambiguous Stripe price catalog.')
        if found.data:
            price = found.data[0]
        else:
            params = {'product': products['lifetime' if plan == 'lifetime' else 'premium'].id,
                      'currency': 'eur', 'unit_amount': value['amount'], 'tax_behavior': 'inclusive',
                      'lookup_key': lookup, 'metadata': {'application': 'university_bot', 'plan': plan}}
            if value['interval']:
                params['recurring'] = {'interval': value['interval']}
            price = await api.v1.prices.create_async(params, options={'idempotency_key': lookup})
        os.environ[value['env']] = price.id
        await billing.validate_price(api, plan)
        print(f"{value['env']}={price.id}")
    configurations = await api.v1.billing_portal.configurations.list_async({'limit': 100})
    config = None
    async for item in configurations.auto_paging_iter():
        item = billing.as_dict(item)
        if item.get('metadata', {}).get('application') == 'university_bot' and item['active']:
            config = item
            break
    config_params = {'business_profile': {'headline': 'Manage your University Bot Premium subscription'},
                     'default_return_url': base + '/dashboard/premium',
                     'features': {'invoice_history': {'enabled': True}, 'payment_method_update': {'enabled': True},
                                  'subscription_cancel': {'enabled': True, 'mode': 'at_period_end'},
                                  'subscription_update': {'enabled': False}},
                     'metadata': {'application': 'university_bot'}}
    config = await api.v1.billing_portal.configurations.update_async(config['id'], config_params) if config else await api.v1.billing_portal.configurations.create_async(config_params, options={'idempotency_key': 'university-portal-v1'})
    config = billing.as_dict(config)
    print(f"STRIPE_PORTAL_CONFIGURATION={config['id']}")
    url = base + '/api/stripe/webhook'
    endpoints = await api.v1.webhook_endpoints.list_async({'limit': 100})
    endpoint = None
    async for item in endpoints.auto_paging_iter():
        item = billing.as_dict(item)
        if item['url'] == url:
            endpoint = item
            break
    if endpoint:
        if endpoint['api_version'] != billing.API_VERSION:
            raise billing.BillingError('Existing webhook API version differs. Update the endpoint in Stripe Dashboard before continuing.')
        endpoint = await api.v1.webhook_endpoints.update_async(endpoint['id'], {'enabled_events': list(billing.EVENTS), 'disabled': False})
    else:
        endpoint = await api.v1.webhook_endpoints.create_async({'url': url, 'enabled_events': list(billing.EVENTS),
                     'api_version': billing.API_VERSION, 'metadata': {'application': 'university_bot'}},
                     options={'idempotency_key': 'university-webhook-v1-' + base})
    endpoint = billing.as_dict(endpoint)
    print(f"Webhook endpoint: {endpoint['id']}")
    print(f'Webhook URL: {url}')
    print('Set STRIPE_WEBHOOK_SECRET in Railway using the signing secret shown in Stripe Dashboard. Secret not printed.')
    print('Test catalog ready. No live products, subscriptions or charges were created.')


async def exists_product(api, key):
    import stripe
    try:
        await api.v1.products.retrieve_async(key)
        return True
    except stripe.InvalidRequestError as exc:
        if exc.code == 'resource_missing':
            return False
        raise


async def run_setup(public_url):
    try:
        await setup(public_url)
    finally:
        await billing.close_client()


if __name__ == '__main__':
    import stripe
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-url', default='https://universtiy-bot.up.railway.app')
    args = parser.parse_args()
    try:
        asyncio.run(run_setup(args.public_url))
    except (billing.BillingError, stripe.StripeError) as exc:
        print(f'Setup could not complete ({type(exc).__name__}). Check environment, catalog and Stripe request logs.', file=sys.stderr)
        sys.exit(1)
