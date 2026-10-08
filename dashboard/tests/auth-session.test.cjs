/* Run with: node --test tests/auth-session.test.cjs */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const { encode } = require('next-auth/jwt');
const { getServerSession } = require('next-auth/next');
const root = path.resolve(__dirname, '..');
const resolve = Module._resolveFilename;
const compile = Module._extensions['.ts'];
Module._resolveFilename = function (name, ...args) {
  return resolve.call(this, name.startsWith('@/') ? path.join(root, name.slice(2)) : name, ...args);
};
Module._extensions['.ts'] = (mod, file) => {
  mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText, file);
};
const originalFetch = global.fetch;
const { DASHBOARD_AUTH_VERSION } = require('../lib/discord-oauth.ts');
const envNames = ['NEXTAUTH_SECRET', 'DASHBOARD_API_KEY', 'NEXTAUTH_URL', 'WARTUNG'];
const originalEnv = Object.fromEntries(envNames.map(name => [name, process.env[name]]));
let revoked = false;
global.fetch = async url => new Response(JSON.stringify(
  String(url).includes('/session-valid') ? { valid: !revoked, revoked_before_ms: revoked ? Date.now() + 10_000 : 0 } :
  String(url).includes('/access/check/') ? { banned: false } : { allowed: true }
), { headers: { 'content-type': 'application/json' } });
test.after(() => {
  global.fetch = originalFetch;
  Module._resolveFilename = resolve;
  if (compile) Module._extensions['.ts'] = compile; else delete Module._extensions['.ts'];
  for (const name of envNames) { if (originalEnv[name] === undefined) delete process.env[name]; else process.env[name] = originalEnv[name]; }
});
function load(secret, origin, dedicated) {
  process.env.DASHBOARD_API_KEY = dedicated ? crypto.randomBytes(32).toString('hex') : secret;
  if (dedicated) process.env.NEXTAUTH_SECRET = secret; else delete process.env.NEXTAUTH_SECRET;
  process.env.NEXTAUTH_URL = origin;
  process.env.WARTUNG = 'false';
  revoked = false;
  for (const file of ['middleware.ts', 'lib/auth.ts', 'lib/auth-session.ts']) delete require.cache[path.join(root, file)];
  return { middleware: require('../middleware.ts').default, options: require('../lib/auth.ts').authOptions };
}
function cookie(origin, token) {
  const name = origin.startsWith('https:') ? '__Secure-next-auth.session-token' : 'next-auth.session-token';
  // NextAuth splits larger cookies. Exercise that path too.
  return { [`${name}.0`]: token.slice(0, 100), [`${name}.1`]: token.slice(100) };
}
function request(origin, cookies, endpoint = '/dashboard') {
  return new NextRequest('http://127.0.0.1:3000' + endpoint, { headers: {
    'x-forwarded-host': new URL(origin).host,
    'x-forwarded-proto': new URL(origin).protocol.slice(0, -1),
    cookie: Object.entries(cookies).map(([key, value]) => `${key}=${value}`).join('; '),
  } });
}
for (const origin of ['http://localhost:3000', 'https://dashboard.example.test']) {
  for (const dedicated of [false, true]) {
    test(`Session survives dashboard/API navigation: ${new URL(origin).protocol} ${dedicated ? 'NEXTAUTH_SECRET' : 'API-key fallback'}`, async () => {
      const secret = crypto.randomBytes(32).toString('hex');
      const { middleware, options } = load(secret, origin, dedicated);
      const token = await encode({ secret: options.secret, token: { sub: '111', name: 'Test', accessToken: 'test-token', sessionIssuedAtMs: Date.now(), authVersion: DASHBOARD_AUTH_VERSION } });
      const cookies = cookie(origin, token);
      const session = await getServerSession({ headers: {}, cookies }, { getHeader() {}, setHeader() {}, setCookie() {} }, options);
      assert.equal(session?.user?.id, '111', 'server components must see the signed-in account');
      for (const endpoint of ['/dashboard', '/dashboard/guilds', '/api/bot/guilds/']) {
        const response = await middleware(request(origin, cookies, endpoint));
        assert.equal(response.status, 200, 'middleware must accept the same encrypted cookie');
        assert.equal(response.headers.get('location'), null, 'must not bounce to the homepage');
      }
    });
  }
}
test('Missing, forged, expired and revoked sessions stay blocked', async () => {
  const secret = crypto.randomBytes(32).toString('hex');
  const origin = 'https://dashboard.example.test';
  const { middleware } = load(secret, origin, true);
  const forged = await encode({ secret: crypto.randomBytes(32).toString('hex'), token: { sub: '111' } });
  const expired = await encode({ secret, token: { sub: '111' }, maxAge: -60 });
  for (const cookies of [{}, cookie(origin, forged), cookie(origin, expired)]) {
    const response = await middleware(request(origin, cookies));
    assert.equal(response.status, 307);
  }
  revoked = true;
  const token = await encode({ secret, token: { sub: 'revoked-user', sessionIssuedAtMs: Date.now() - 10_000, authVersion: DASHBOARD_AUTH_VERSION } });
  const response = await middleware(request(origin, cookie(origin, token)));
  assert.equal(response.status, 307);
  assert.equal(new URL(response.headers.get('location')).searchParams.get('error'), 'SessionRevoked');
});

test('all pre-cutover cookies lose dashboard, API and server-session access; new consent remains valid', async () => {
  const origin = 'https://dashboard.example.test';
  const { middleware, options } = load(crypto.randomBytes(32).toString('hex'), origin, true);
  for (const authVersion of [undefined, 'previous-consent']) {
    const value = await encode({ secret: options.secret, token: { sub: 'old-user', accessToken: 'old-access', refreshToken: 'old-refresh', sessionIssuedAtMs: Date.now(), authVersion } });
    const cookies = cookie(origin, value);
    assert.equal((await middleware(request(origin, cookies))).status, 307);
    assert.equal((await middleware(request(origin, cookies, '/api/bot/guilds/'))).status, 401);
    const session = await getServerSession({ headers: {}, cookies }, { getHeader() {}, setHeader() {}, setCookie() {} }, options);
    assert.equal(session.user, undefined); assert.equal(session.accessToken, undefined); assert.equal(session.revoked, true);
  }
  const fresh = await options.callbacks.jwt({ token: { sub: 'new-user' }, account: { scope: 'identify connections guilds guilds.members.read', access_token: 'new-access' }, profile: {} });
  assert.equal(fresh.authVersion, DASHBOARD_AUTH_VERSION); assert.equal(fresh.sessionRevoked, false);
  const incomplete = await options.callbacks.jwt({ token: { sub: 'new-user' }, account: { scope: 'identify guilds', access_token: 'old-scope-access' }, profile: {} });
  assert.equal(incomplete.sessionRevoked, true); assert.equal(incomplete.accessToken, undefined);
});

test('Railway auth logs retain the reason and omit credentials, tokens and state values', () => {
  const { options } = load(crypto.randomBytes(32).toString('hex'), 'https://dashboard.example.test', true);
  const entries = [];
  const original = console.error;
  const marker = 'do-not-log-test-secret';
  try {
    console.error = (...args) => entries.push(args);
    options.logger.error('OAUTH_CALLBACK_ERROR', {
      error: Object.assign(new Error('invalid_client (client authentication failed)'), {
        request: { headers: { Authorization: marker }, client_secret: marker },
        access_token: marker,
      }),
      providerId: 'discord',
    });
    options.logger.error('OAUTH_CALLBACK_ERROR', {
      error: new Error(`state mismatch, expected ${marker}, got ${marker}`),
      providerId: 'discord',
    });
  } finally { console.error = original; }
  assert.equal(entries[0][0], '[next-auth][OAUTH_CALLBACK_ERROR]');
  assert.equal(entries[0][1].message, 'invalid_client (client authentication failed)');
  assert.equal(entries[0][1].providerId, 'discord');
  assert.equal(entries[1][1].message, 'state mismatch (values redacted)');
  assert(!JSON.stringify(entries).includes(marker));
});
