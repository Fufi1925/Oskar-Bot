const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function route(fetch) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, "../app/api/honeypot-stats/route.ts"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInNewContext(code, {
    module, exports: module.exports, fetch, AbortSignal,
    process: { env: { API_BASE_URL: "http://localhost:8080/api/v1", DASHBOARD_API_KEY: "test-only" } },
    require: () => ({ NextResponse: { json: (body, options = {}) => ({ body, ...options }) } }),
  });
  return module.exports.GET;
}

test("public live stats proxy exposes aggregates without private backend fields", async () => {
  const GET = route(async (url, options) => {
    assert.equal(url, "http://localhost:8080/api/v1/honeypot/live-stats");
    assert.equal(options.headers.Authorization, "Bearer test-only");
    assert.equal(options.cache, "no-store");
    return { ok: true, json: async () => ({
      total_moderations: 123, total_servers: 4, moderations_7d: 2, triggered_servers_7d: 1,
      history: [{ day: "2026-10-07", moderations: 2, servers: 1, guild_id: "secret-guild" }],
      tracking_since: "2026-10-07T12:00:00Z", updated_at: "2026-10-07T13:00:00Z",
      token: "test-only", whitelist_roles: ["secret-role"],
    }) };
  });
  const result = await GET();
  assert.equal(result.body.total_moderations, 123);
  assert.equal(result.headers["Cache-Control"], "no-store");
  const serialized = JSON.stringify(result.body);
  assert.doesNotMatch(serialized, /secret|test-only|guild_id|whitelist/);
});

test("backend failure does not substitute zeros for real statistics", async () => {
  const GET = route(async () => ({ ok: false }));
  const result = await GET();
  assert.equal(result.status, 503);
  assert.equal(result.body.total_moderations, undefined);
  assert.equal(result.headers["Cache-Control"], "no-store");
});
