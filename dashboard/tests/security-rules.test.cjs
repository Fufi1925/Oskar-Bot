const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const fixture = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/security-rules.ts'), 'utf8'), {compilerOptions: { module: ts.ModuleKind.CommonJS }}).outputText, { exports: fixture.exports, module: fixture });
const { filterRules, ruleDefaults, validateRules } = fixture.exports;
const rules = [
  { key: 'spam', label: 'Nachrichten-Spam', description: 'Viele Nachrichten', enabled: true, has_window: true, threshold_min: 3, threshold_max: 20, defaults: { threshold: 6, duration: 12, punishment: 'mute', window: 10 } },
  { key: 'caps', label: 'Großbuchstaben', description: 'Zu viele Großbuchstaben', enabled: false, has_window: false, threshold_min: 20, threshold_max: 100, defaults: { threshold: 70, duration: 1, punishment: 'delete', window: 0 } },
];
test('search and enabled filters use drafts without changing them', () => {
  const draft = { caps: { enabled: true, threshold: 60 }, spam: { enabled: false, window: 15 } };
  const before = JSON.stringify(draft);
  assert.equal(filterRules(rules, draft, ' GROSS ', 'enabled', text => text === 'Großbuchstaben' ? 'Gross letters' : text)[0].key, 'caps');
  assert.equal(filterRules(rules, draft, '', 'disabled')[0].key, 'spam');
  assert.equal(filterRules(rules, draft, 'unknown', 'all').length, 0);
  assert.equal(JSON.stringify(draft), before);
});
test('reset restores the server window and omits windows for other rules', () => {
  assert.equal(ruleDefaults(rules[0]).window, 10);
  assert.equal(Object.hasOwn(ruleDefaults(rules[1]), 'window'), false);
  assert.equal(ruleDefaults({ ...rules[0], defaults: { ...rules[0].defaults, window: 20 } }).window, 20);
});
test('invalid, fractional and empty numeric input cannot be saved', () => {
  for (const patch of [{ threshold: 0 }, { threshold: 21 }, { threshold: 3.5 }, { duration: NaN }, { duration: 10081 }, { window: 121 }]) assert.equal(validateRules(rules, { spam: patch }), true);
  assert.equal(validateRules(rules, { spam: { threshold: 3, duration: 10080, window: 120 } }), false);
  assert.equal(validateRules(rules, { caps: { enabled: true } }), false);
});
