/* Exercises NextAuth's real Discord callback against a local OAuth server. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const resolve = Module._resolveFilename;
const compile = Module._extensions['.ts'];
Module._resolveFilename = function (name, ...args) { return resolve.call(this, name.startsWith('@/') ? path.join(root, name.slice(2)) : name, ...args); };
Module._extensions['.ts'] = (mod, file) => mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText, file);
const originalFetch = global.fetch;
const saved = Object.fromEntries(['NEXTAUTH_URL', 'NEXTAUTH_SECRET'].map(key => [key, process.env[key]]));
test.after(() => {
  global.fetch = originalFetch;
  Module._resolveFilename = resolve;
  if (compile) Module._extensions['.ts'] = compile; else delete Module._extensions['.ts'];
  for (const [key, value] of Object.entries(saved)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
});
const { AuthHandler } = require(path.join(root, 'node_modules/next-auth/core/index.js'));
const origin = 'https://universtiy-bot.up.railway.app';
const callbackUrl = origin + '/auth/success?next=%2Fdashboard';
const credentials = { id: 'test-client', secret: crypto.randomBytes(32).toString('hex') };
process.env.NEXTAUTH_URL = origin;
process.env.NEXTAUTH_SECRET = crypto.randomBytes(32).toString('hex');
global.fetch = async () => new Response(JSON.stringify({ banned: false, valid: true, revoked_before_ms: 0 }), { headers: { 'content-type': 'application/json' } });
function applyCookies(jar, response) { for (const cookie of response.cookies || []) { if (cookie.options?.maxAge === 0) delete jar[cookie.name]; else jar[cookie.name] = cookie.value; } }

async function roundtrip(mode = 'ok') {
  let exchanges = 0;
  const errors = [];
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/token') {
      exchanges++;
      let body = ''; for await (const part of req) body += part;
      const params = new URLSearchParams(body);
      assert.equal(params.get('redirect_uri'), origin + '/api/auth/callback/discord');
      assert.equal(params.get('grant_type'), 'authorization_code');
      assert.equal(params.get('code'), 'test-code');
      if (mode === 'invalid_client') { res.writeHead(401); return res.end(JSON.stringify({ error: 'invalid_client' })); }
      res.end(JSON.stringify({ access_token: 'test-access', refresh_token: 'test-refresh', token_type: 'Bearer', expires_in: 3600, scope: 'identify guilds' }));
    } else if (req.url === '/profile') {
      res.end(JSON.stringify({ id: '111', username: 'OAuth-Test', avatar: null, discriminator: '0' }));
    } else { res.writeHead(404); res.end('{}'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const endpoint = `http://127.0.0.1:${server.address().port}`;
  try {
    const base = require('../lib/auth.ts').authOptions;
    const provider = base.providers[0];
    const options = { ...base, debug: false, logger: { error(code, metadata) { errors.push({ code, message: metadata?.error?.message || metadata?.message || '' }); }, warn() {}, debug() {} }, providers: [{ ...provider, options: { ...provider.options, clientId: credentials.id, clientSecret: credentials.secret, authorization: { url: endpoint + '/authorize', params: { scope: 'identify guilds' } }, token: endpoint + '/token', userinfo: endpoint + '/profile' } }] };
    const jar = {};
    const csrf = await AuthHandler({ options, req: { action: 'csrf', method: 'GET', headers: {}, cookies: jar, query: {} } });
    applyCookies(jar, csrf);
    const signIn = await AuthHandler({ options, req: { action: 'signin', providerId: 'discord', method: 'POST', headers: {}, cookies: jar, query: {}, body: { csrfToken: csrf.body.csrfToken, callbackUrl } } });
    applyCookies(jar, signIn);
    const authorize = new URL(signIn.redirect);
    assert.equal(authorize.searchParams.get('redirect_uri'), origin + '/api/auth/callback/discord');
    assert.equal(authorize.searchParams.get('scope'), 'identify guilds');
    assert(jar['__Secure-next-auth.state'], 'secure state cookie must survive the Discord redirect');
    const state = authorize.searchParams.get('state');
    if (mode === 'missing_state') delete jar['__Secure-next-auth.state'];
    const response = await AuthHandler({ options, req: { action: 'callback', providerId: 'discord', method: 'GET', headers: {}, cookies: jar, query: { code: 'test-code', state: mode === 'wrong_state' ? 'wrong-state' : state, ...(mode === 'legacy_no_issuer' ? {} : { iss: mode === 'wrong_issuer' ? 'https://untrusted.example.test' : 'https://discord.com' }) } } });
    applyCookies(jar, response);
    if (mode === 'ok' || mode === 'legacy_no_issuer') {
      assert.equal(response.redirect, callbackUrl, JSON.stringify(errors));
      assert(jar['__Secure-next-auth.session-token'], 'callback must issue a real signed session');
      const session = await AuthHandler({ options, req: { action: 'session', method: 'GET', headers: {}, cookies: jar, query: {} } });
      assert.equal(session.body.user.id, '111');
      assert.equal(session.body.accessToken, 'test-access');
      assert.deepEqual(errors, []);
    } else {
      assert.equal(new URL(response.redirect).searchParams.get('error'), 'OAuthCallback');
      assert(!jar['__Secure-next-auth.session-token']);
      assert(errors.some(item => item.code === 'OAUTH_CALLBACK_ERROR'));
      if (mode === 'missing_state' || mode === 'wrong_issuer') assert.equal(exchanges, 0, 'invalid state or issuer must be rejected before token exchange');
      if (mode === 'wrong_issuer') assert(errors.some(item => item.message.startsWith('iss mismatch')), 'reject the unexpected issuer explicitly');
      if (mode === 'invalid_client') {
        assert.equal(exchanges, 1, 'valid state and issuer must reach the token endpoint');
        assert(errors.some(item => item.message.includes('invalid_client')));
      }
    }
  } finally { await new Promise(resolve => server.close(resolve)); }
}
test('Discord authorization, state, code exchange, profile and session roundtrip on Railway origin', () => roundtrip());
test('Discord legacy callbacks without an issuer still create a session', () => roundtrip('legacy_no_issuer'));
for (const mode of ['missing_state', 'wrong_state', 'wrong_issuer', 'invalid_client']) test('OAuthCallback safely rejects ' + mode, () => roundtrip(mode));

test('OAuth failures open the error page rather than bouncing back to the homepage', () => {
  const { authErrorPath } = require('../lib/auth-errors.ts');
  for (const action of ['error', 'signin']) {
    assert.equal(authErrorPath(action, 'OAuthCallback'), '/auth/error?error=OAuthCallback');
  }
  assert.equal(authErrorPath('callback', 'access_denied'), null, 'Discord callbacks must still undergo OAuth validation');
  assert.equal(authErrorPath('signin', null), null, 'normal sign-in must be unchanged');
});

test('The reported homepage URL and NextAuth failure endpoints reach the visible error page', async () => {
  const { NextRequest } = require('next/server');
  const middleware = require('../middleware.ts').default;
  const reported = new NextRequest('http://127.0.0.1:3000/?callbackUrl=' + encodeURIComponent(callbackUrl) + '&error=OAuthCallback');
  const homeResponse = await middleware(reported);
  assert.equal(new URL(homeResponse.headers.get('location')).origin, origin);
  assert.equal(new URL(homeResponse.headers.get('location')).pathname, '/auth/error');
  assert.equal(new URL(homeResponse.headers.get('location')).searchParams.get('error'), 'OAuthCallback');
  const { GET } = require('../app/api/auth/[...nextauth]/route.ts');
  for (const action of ['error', 'signin']) {
    const response = await GET(new NextRequest('http://127.0.0.1:3000/api/auth/' + action + '?error=OAuthCallback'), { params: { nextauth: [action] } });
    assert.equal(response.status, 307);
    assert.equal(response.headers.get('location'), origin + '/auth/error?error=OAuthCallback');
  }
});
