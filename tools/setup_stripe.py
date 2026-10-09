#!/usr/bin/env python3
"""Provision the authorized Stripe catalog, customer portal and webhook.

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


async def setup(public_url, *, live=False):
    expected_mode = 'live' if live else 'test'
    if billing.mode() != expected_mode:
        raise billing.BillingError('Selected setup mode differs from STRIPE_MODE. Use --live explicitly for live setup.')
    os.environ['STRIPE_PUBLIC_URL'] = public_url
    base = billing.origin()
    api = billing.client()
    if live:
        account = billing.as_dict(await api.v1.accounts.retrieve_current_async())
        if not account.get('charges_enabled'):
            raise billing.BillingError('Activate payments for this account in Stripe Dashboard before live setup.')
    settings = {'STRIPE_MODE': expected_mode, 'STRIPE_PUBLIC_URL': base,
                'STRIPE_SECRET_KEY': os.environ['STRIPE_SECRET_KEY'].strip()}
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
        settings[value['env']] = price.id
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
    settings['STRIPE_PORTAL_CONFIGURATION'] = config['id']
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
    # The secret is only returned upon creation. Keep it in memory for an
    # authorized Railway transfer; never serialize the returned settings.
    secret = endpoint.get('secret') or os.getenv('STRIPE_WEBHOOK_SECRET', '').strip()
    if secret:
        settings['STRIPE_WEBHOOK_SECRET'] = secret
    print(f"Webhook endpoint: {endpoint['id']}")
    print(f'Webhook URL: {url}')
    print('Set STRIPE_WEBHOOK_SECRET in Railway using the signing secret shown in Stripe Dashboard. Secret not printed.')
    print(f'{expected_mode.capitalize()} catalog ready. No customer subscriptions or charges were created.')
    return settings


async def exists_product(api, key):
    import stripe
    try:
        await api.v1.products.retrieve_async(key)
        return True
    except stripe.InvalidRequestError as exc:
        if exc.code == 'resource_missing':
            return False
        raise


async def run_setup(public_url, *, live=False, railway_url=None):
    try:
        if railway_url:
            from setup_stripe_railway import RailwayTarget
            async with RailwayTarget(railway_url) as railway:
                # Check credentials and scope before creating Stripe objects.
                await railway.preflight()
                settings = await setup(public_url, live=live)
                await railway.configure(settings)
        else:
            await setup(public_url, live=live)
    finally:
        await billing.close_client()


if __name__ == '__main__':
    import stripe
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-url', default='https://universtiy-bot.up.railway.app')
    parser.add_argument('--live', action='store_true', help='Provision live objects; requires STRIPE_MODE=live and a live credential.')
    parser.add_argument('--railway-url', help='Authorized Railway project/service URL. Transfer settings privately and request deployment.')
    args = parser.parse_args()
    try:
        asyncio.run(run_setup(args.public_url, live=args.live, railway_url=args.railway_url))
    except billing.BillingError as exc:
        print(f'Setup could not complete: {exc.code}', file=sys.stderr)
        sys.exit(1)
    except stripe.StripeError as exc:
        print(f'Setup could not complete ({type(exc).__name__}). Check environment, catalog and Stripe request logs.', file=sys.stderr)
        sys.exit(1)
