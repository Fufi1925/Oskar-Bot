const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const root = path.resolve(__dirname, '..');
const originalResolve = Module._resolveFilename, originalLoad = Module._load, originalCompile = Module._extensions['.ts'];
const originalFetch = global.fetch;
const names = ['OWNER_IDS', 'ADMIN_IDS', 'DASHBOARD_API_KEY', 'NODE_ENV', 'NEXTAUTH_URL'];
const env = Object.fromEntries(names.map(name => [name, process.env[name]]));
let session, requests = [], upstream = {};
Module._resolveFilename = function (name, ...args) { return originalResolve.call(this, name.startsWith('@/') ? path.join(root, name.slice(2)) : name, ...args); };
Module._load = function (name, ...args) {
  if (name === 'next-auth/next') return { getServerSession: async () => session };
  if (name === '@/lib/auth') return { authOptions: {} };
  return originalLoad.call(this, name, ...args);
};
Module._extensions['.ts'] = (mod, file) => mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, file);
const route = require('../app/api/owner-louckup/[...path]/route.ts');
const { recordOAuthSnapshot } = require('../lib/oauth-snapshot.ts');
const owner = '870179991462236170', other = '1033826242270609449';
function setup() {
  process.env.OWNER_IDS = owner; process.env.ADMIN_IDS = other; process.env.DASHBOARD_API_KEY = 'test-service-key'; process.env.NODE_ENV = 'production';
  delete process.env.NEXTAUTH_URL;
  session = { user: { id: owner }, sessionIssuedAtMs: 1000 };
  requests = []; upstream = {};
  global.fetch = async (url, options) => {
    requests.push({ url: String(url), options });
    return new Response(JSON.stringify(upstream), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
}
function request(parts, method = 'GET', body, headers = {}, base = 'https://example.test') {
  const req = new NextRequest(base + '/api/owner-louckup/' + parts.join('/'), {
    method, headers: { origin: 'https://example.test', ...headers }, body: body && JSON.stringify(body),
  });
  return route[method](req, { params: { path: parts } });
}
test.after(() => {
  global.fetch = originalFetch; Module._resolveFilename = originalResolve; Module._load = originalLoad;
  if (originalCompile) Module._extensions['.ts'] = originalCompile; else delete Module._extensions['.ts'];
  for (const name of names) { if (env[name] === undefined) delete process.env[name]; else process.env[name] = env[name]; }
});

test('signed-in owner is required; ADMIN_IDS and forged owner headers grant no access', async () => {
  setup(); session = null; assert.equal((await request(['status'])).status, 401);
  session = { user: { id: other }, sessionIssuedAtMs: 1000 };
  assert.equal((await request(['status'], 'GET', undefined, { 'X-Louckup-Actor': owner })).status, 403);
  assert.equal(requests.length, 0);
});
test('the internal OAuth capture endpoint and arbitrary paths are not browser-accessible', async () => {
  setup(); assert.equal((await request(['oauth-snapshot'], 'POST', { user: { id: owner } })).status, 404);
  assert.equal((await request(['users', '../admin'])).status, 404); assert.equal(requests.length, 0);
});
test('cross-origin unlocks are refused before contacting the bot', async () => {
  setup(); assert.equal((await request(['unlock'], 'POST', { code: '123456' }, { origin: 'https://attacker.test' })).status, 403);
  assert.equal((await request(['unlock'], 'POST', { code: '123456' }, { 'sec-fetch-site': 'cross-site' })).status, 403);
  assert.equal(requests.length, 0);
});
test('public-origin unlocks work through the internal dashboard proxy', async () => {
  setup(); process.env.NEXTAUTH_URL = 'https://example.test/';
  upstream = { grant: 'a'.repeat(43), expires_at: 12345 };
  const response = await request(['unlock'], 'POST', { code: '123456' }, {
    'x-forwarded-host': 'example.test', 'x-forwarded-proto': 'https', 'sec-fetch-site': 'same-origin',
  }, 'http://127.0.0.1:3000');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { unlocked: true, expires_at: 12345 });
  assert.equal(requests.length, 1);
});
test('proxy headers and the internal origin cannot override the configured public origin', async () => {
  setup(); process.env.NEXTAUTH_URL = 'https://example.test';
  for (const origin of ['https://attacker.test', 'http://127.0.0.1:3000', 'null', '']) {
    const response = await request(['unlock'], 'POST', { code: '123456' }, {
      origin, 'x-forwarded-host': 'attacker.test', 'x-forwarded-proto': 'https',
    }, 'http://127.0.0.1:3000');
    assert.equal(response.status, 403);
    assert.deepEqual(await response.json(), { detail: 'invalid_origin' });
  }
  assert.equal(requests.length, 0);
});
test('locking also works through the proxy and clears the grant cookie', async () => {
  setup(); process.env.NEXTAUTH_URL = 'https://example.test'; upstream = { unlocked: false };
  const response = await request(['lock'], 'POST', undefined, {}, 'http://127.0.0.1:3000');
  assert.equal(response.status, 200);
  assert.ok(response.headers.get('set-cookie').includes('Max-Age=0'));
  assert.equal(requests.length, 1);
});
test('missing origins and invalid public URL configuration fail closed', async () => {
  setup();
  const req = new NextRequest('https://example.test/api/owner-louckup/unlock', {
    method: 'POST', body: JSON.stringify({ code: '123456' }),
  });
  assert.equal((await route.POST(req, { params: { path: ['unlock'] } })).status, 403);
  for (const url of ['invalid', 'file:///tmp/dashboard', 'https://user:password@example.test']) {
    process.env.NEXTAUTH_URL = url;
    assert.equal((await request(['unlock'], 'POST', { code: '123456' })).status, 403);
  }
  assert.equal(requests.length, 0);
});
test('grants stay in Secure HttpOnly SameSite cookies, never in JSON', async () => {
  setup(); upstream = { grant: 'a'.repeat(43), expires_at: 12345 };
  const response = await request(['unlock'], 'POST', { code: '123456', actor: other, session: 'forged' }, { 'X-Louckup-Actor': other });
  assert.deepEqual(await response.json(), { unlocked: true, expires_at: 12345 });
  const cookie = response.headers.get('set-cookie');
  for (const flag of ['HttpOnly', 'Secure', 'SameSite=strict', 'Path=/api/owner-louckup', 'Max-Age=600']) assert.ok(cookie.includes(flag), flag);
  assert.equal(requests[0].options.headers['X-Louckup-Actor'], owner);
  assert.equal(requests[0].options.body, JSON.stringify({ code: '123456' }));
  assert.equal(response.headers.get('cache-control'), 'no-store, private');
});
test('new logins produce different server-derived step-up bindings', async () => {
  setup(); await request(['status']); const old = requests[0].options.headers['X-Louckup-Session'];
  session.sessionIssuedAtMs++; await request(['status']); assert.notEqual(old, requests[1].options.headers['X-Louckup-Session']);
  assert.equal(old.length, 64);
});
test('OAuth snapshots store only granted public data, support pagination and retain no tokens/email', async () => {
  setup(); let page = 0;
  global.fetch = async (url, options) => {
    requests.push({ url: String(url), options });
    if (String(url).startsWith('https://discord.com/')) {
      page++;
      return new Response(JSON.stringify(page === 1 ? Array.from({ length: 200 }, (_, n) => ({ id: String(100000000000000000n + BigInt(n)), name: 'Server', email: 'secret' })) : [{ id: owner, name: 'Last server', permissions: '8' }]));
    }
    return new Response('{}');
  };
  await recordOAuthSnapshot('private-oauth-token', 'identify guilds', { id: owner, username: 'Owner', email: 'private@example.test' }, owner);
  const body = JSON.parse(requests.at(-1).options.body);
  assert.equal(body.guilds.length, 201); assert.equal(body.complete, true);
  assert.ok(requests[1].url.includes('&after='));
  for (const text of ['private-oauth-token', 'email', 'private@example.test']) assert.ok(!JSON.stringify(body).includes(text));
  requests = []; await recordOAuthSnapshot('private-oauth-token', 'identify', {}, owner); assert.equal(requests.length, 0);
});
