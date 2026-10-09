"""Scoped Railway configuration for setup_stripe; secret values never logged."""
import os
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
from utils.stripe_billing import BillingError, PLANS

ENDPOINT = 'https://backboard.railway.com/graphql/v2'
PROJECT_QUERY = '''query StripeSetupTarget($id: String!) {
  project(id: $id) {
    id
    environments { edges { node { id deletedAt } } }
    services { edges { node { id } } }
  }
}'''
TOKEN_QUERY = '''query StripeSetupToken {
  projectToken { project { id } environment { id } }
}'''
UPSERT = '''mutation StripeSetupVariables($input: VariableCollectionUpsertInput!) {
  variableCollectionUpsert(input: $input)
}'''


def target_ids(value):
    parsed = urlsplit(value)
    parts = parsed.path.strip('/').split('/')
    query = parse_qs(parsed.query)
    if (parsed.scheme != 'https' or parsed.netloc != 'railway.com' or parsed.fragment
            or len(parts) != 4 or parts[0] != 'project' or parts[2] != 'service'
            or len(query.get('environmentId', [])) != 1):
        raise BillingError('Use the exact Railway project/service URL with environmentId.')
    ids = (parts[1], parts[3], query['environmentId'][0])
    try:
        for value in ids:
            if str(uuid.UUID(value)) != value:
                raise ValueError
    except ValueError:
        raise BillingError('Invalid Railway target IDs.') from None
    return dict(zip(('projectId', 'serviceId', 'environmentId'), ids))


class RailwayTarget:
    def __init__(self, url):
        self.ids = target_ids(url)
        token = os.getenv('RAILWAY_TOKEN', '').strip()
        if not token:
            raise BillingError('Supply RAILWAY_TOKEN securely in environment settings (project/environment token).')
        self.http = httpx.AsyncClient(headers={'project-access-token': token}, timeout=30)
        self.ready = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.http.aclose()

    async def query(self, query, variables=None):
        try:
            response = await self.http.post(ENDPOINT, json={'query': query, 'variables': variables or {}})
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            # Provider errors may echo variables, so do not print their body.
            raise BillingError('Railway request failed. Check token access and network configuration.') from None
        if data.get('errors') or not isinstance(data.get('data'), dict):
            raise BillingError('Railway rejected the request. Check token scope and Railway activity.')
        return data['data']

    async def preflight(self):
        token = (await self.query(TOKEN_QUERY)).get('projectToken') or {}
        if (token.get('project', {}).get('id') != self.ids['projectId']
                or token.get('environment', {}).get('id') != self.ids['environmentId']):
            raise BillingError('Railway token belongs to a different project or environment.')
        project = (await self.query(PROJECT_QUERY, {'id': self.ids['projectId']})).get('project') or {}
        services = project.get('services', {}).get('edges', [])
        environments = project.get('environments', {}).get('edges', [])
        if (project.get('id') != self.ids['projectId']
                or not any(e['node']['id'] == self.ids['serviceId'] for e in services)
                or not any(e['node']['id'] == self.ids['environmentId'] and not e['node'].get('deletedAt') for e in environments)):
            raise BillingError('Railway service/environment does not belong to the selected project.')
        self.ready = True

    async def configure(self, settings):
        if not self.ready:
            raise BillingError('Verify the Railway target before configuring it.')
        required = {'STRIPE_MODE', 'STRIPE_PUBLIC_URL', 'STRIPE_SECRET_KEY',
                    'STRIPE_WEBHOOK_SECRET', 'STRIPE_PORTAL_CONFIGURATION',
                    *(p['env'] for p in PLANS.values())}
        if set(settings) != required or not all(settings.values()):
            raise BillingError('Missing Stripe settings. For an existing endpoint, supply STRIPE_WEBHOOK_SECRET securely first.')
        if not settings['STRIPE_WEBHOOK_SECRET'].startswith('whsec_'):
            raise BillingError('Invalid webhook signing secret.')
        result = await self.query(UPSERT, {'input': {**self.ids, 'variables': settings,
                                                  'replace': False, 'skipDeploys': False}})
        if result.get('variableCollectionUpsert') is not True:
            raise BillingError('Railway did not confirm the configuration update.')
        print('Stripe variables saved to the verified Railway service; deployment requested. Check deployment and webhook delivery before claiming readiness.')
