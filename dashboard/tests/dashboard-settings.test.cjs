const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const root = path.resolve(__dirname, '..');
const resolve = Module._resolveFilename, load = Module._load, compile = Module._extensions['.ts'];
const originalFetch = global.fetch;
const envKeys = ['OWNER_IDS', 'ADMIN_IDS', 'DASHBOARD_API_KEY', 'NEXTAUTH_URL'];
const env = Object.fromEntries(envKeys.map(key => [key, process.env[key]]));
let session, requests, result, authCalls;
Module._resolveFilename = function(name, ...args) { return resolve.call(this, name.startsWith('@/') ? path.join(root, name.slice(2)) : name, ...args); };
Module._load = function(name, ...args) {
  if (name === 'next-auth/next') return { getServerSession: async () => session };
  if (name === 'next-auth') return options => async request => {
    authCalls.push({ scope: options.providers[0].options.authorization.params.scope, override: request.nextUrl.searchParams.get('scope') });
    return new Response('{}');
  };
  return load.call(this, name, ...args);
};
Module._extensions['.ts'] = (mod, file) => mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, file);
const route = require('../app/api/dashboard-settings/[...path]/route.ts');
const authRoute = require('../app/api/auth/[...nextauth]/route.ts');
const owner = '870179991462236170', admin = '1033826242270609449';
function setup() {
  process.env.OWNER_IDS = owner; process.env.ADMIN_IDS = admin; process.env.DASHBOARD_API_KEY = 'test-service-key'; process.env.NEXTAUTH_URL = 'https://example.test';
  session = { user: { id: owner } }; requests = []; authCalls = []; result = { scopes: ['identify', 'guilds'] };
  global.fetch = async (url, options) => { requests.push({ url: String(url), options }); return new Response(JSON.stringify(result)); };
}
function request(action, method = 'GET', body, headers = {}) {
  return route[method](new NextRequest('http://127.0.0.1:3000/api/dashboard-settings/' + action, {
    method, headers: { origin: 'https://example.test', ...headers }, body: method === 'GET' ? undefined : body && JSON.stringify(body),
  }), { params: { path: action.split('/') } });
}
test.after(() => {
  global.fetch = originalFetch; Module._resolveFilename = resolve; Module._load = load;
  if (compile) Module._extensions['.ts'] = compile; else delete Module._extensions['.ts'];
  for (const key of envKeys) { if (env[key] === undefined) delete process.env[key]; else process.env[key] = env[key]; }
});

test('only signed-in OWNER_IDS can reach dashboard controls, including with forged actor headers', async () => {
  setup(); session = null; assert.equal((await request('settings')).status, 401);
  session = { user: { id: admin } };
  for (const [action, method] of [['settings', 'GET'], ['settings', 'PATCH'], ['revoke-all', 'POST'], ['revoke-user', 'POST']]) {
    assert.equal((await request(action, method, {}, { 'X-Dashboard-Settings-Actor': owner })).status, 403);
  }
  assert.equal(requests.length, 0);
});
test('internal policy paths and cross-origin mutations stay blocked', async () => {
  setup(); assert.equal((await request('oauth-policy')).status, 404);
  assert.equal((await request('settings', 'PATCH', {}, { origin: 'https://attacker.test' })).status, 403);
  assert.equal((await request('revoke-all', 'POST', {}, { 'sec-fetch-site': 'cross-site' })).status, 403);
  assert.equal(requests.length, 0);
});
test('proxy-aware owner controls derive actor identity and strip spoofed privilege fields', async () => {
  setup();
  const response = await request('settings', 'PATCH', { scopes: ['identify', 'guilds'], actor: admin, revoked_before_ms: 99 }, { 'X-Dashboard-Settings-Actor': admin });
  assert.equal(response.status, 200); assert.equal(response.headers.get('cache-control'), 'no-store, private');
  assert.equal(requests[0].options.headers['X-Dashboard-Settings-Actor'], owner);
  assert.deepEqual(JSON.parse(requests[0].options.body), { scopes: ['identify', 'guilds'] });
  assert.equal((await request('revoke-all', 'POST')).status, 200);
  assert.equal(requests[1].options.body, '{}');
});
test('every Discord sign-in and callback uses current owner policy and rejects scope overrides', async () => {
  setup();
  for (const [scopes, action] of [[['identify', 'guilds'], 'signin'], [['identify', 'connections', 'guilds'], 'callback']]) {
    result = { scopes };
    const response = await authRoute.POST(new NextRequest('https://example.test/api/auth/' + action + '/discord?scope=email', { method: 'POST' }), { params: { nextauth: [action, 'discord'] } });
    assert.equal(response.status, 200);
    assert.deepEqual(authCalls.at(-1), { scope: scopes.join(' '), override: null });
  }
  assert.ok(requests.every(request => request.url.endsWith('/dashboard-settings/oauth-policy')));
});
test('unavailable or invalid scope policy stops authorization rather than requesting unwanted defaults', async () => {
  setup(); result = { scopes: ['identify', 'email'] };
  const response = await authRoute.POST(new NextRequest('https://example.test/api/auth/signin/discord', { method: 'POST' }), { params: { nextauth: ['signin', 'discord'] } });
  assert.equal(response.status, 307); assert.ok(response.headers.get('location').includes('OAuthSignin'));
  assert.equal(authCalls.length, 0);
});
test('previously granted extra scopes are excluded from dashboard snapshot collection', async () => {
  setup(); const capture = [];
  global.fetch = async (url, options) => {
    if (String(url).startsWith('https://discord.com/')) return new Response('[]');
    capture.push(JSON.parse(options.body)); return new Response('{}');
  };
  const options = require('../lib/auth.ts').createAuthOptions('identify guilds');
  const token = await options.callbacks.jwt({ token: { sub: owner }, account: { scope: 'identify connections guilds guilds.members.read', access_token: 'test-only-token' }, profile: { id: owner } });
  assert.equal(token.sessionRevoked, false);
  assert.equal(capture.length, 1); assert.equal(capture[0].scope, 'identify guilds');
  assert.equal(capture[0].access_token, undefined);
});
