const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(file, imports = {}, globals = {}) {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, process, Buffer,
    require: name => Object.hasOwn(imports, name) ? imports[name] : require(name), ...globals });
  return module.exports;
}
const dictionary = load('lib/i18n/dom-translations.ts');

test('public, dashboard and dynamic labels translate in both directions', () => {
  for (const [de, en] of [
    ['Erneut laden', 'Reload'], ['Owner-Konsole', 'Owner console'],
    ['Discord-Nachrichten', 'Discord messages'], ['Website-Sprache', 'Website language'],
    ['Offene Bewerbungen', 'Open applications'], ['Deutschland', 'Germany'],
    ['Du verwaltest 12 Server mit dem Bot.', 'You manage 12 servers with the bot.'],
    ['Frage 3 entfernen', 'Remove question 3'],
  ]) {
    assert.equal(dictionary.translateWebsiteText(de, 'en'), en);
    assert.equal(dictionary.translateWebsiteText(en, 'de'), de);
  }
});

test('native dialogs localize their prompts without changing entered text', () => {
  const seen = [];
  const helpers = load('lib/i18n/browser-language.ts', { './dom-translations': dictionary }, {
    document: { documentElement: { lang: 'en' } },
    window: {
      confirm: message => { seen.push(message); return true; },
      prompt: (message, initial) => { seen.push([message, initial]); return 'my server text'; },
      alert: message => seen.push(message),
    },
  });
  assert.equal(helpers.localizedConfirm('Diesen Eintrag löschen?'), true);
  assert.equal(helpers.localizedPrompt('Name oder Discord-ID', 'Eigenes Beispiel'), 'my server text');
  helpers.localizedAlert('Speichern fehlgeschlagen. Deine Änderungen bleiben erhalten.');
  assert.deepEqual(seen, ['Delete this entry?', ['Name or Discord ID', 'Eigenes Beispiel'], 'Could not save. Your changes are still available.']);
});

test('OAuth signs the language with its state and rejects tampering', () => {
  const saved = process.env.VERIFICATION_OAUTH_SECRET;
  process.env.VERIFICATION_OAUTH_SECRET = 'test-only-language-state-secret';
  try {
    const oauth = load('lib/verification-oauth.ts');
    const token = oauth.createVerifyState('1530378233579704370', 'de');
    assert.equal(oauth.readVerifyState(token).language, 'de');
    assert.equal(oauth.readVerifyState(oauth.createVerifyState('1530378233579704370')).language, 'en');
    const [body, signature] = token.split('.');
    const value = JSON.parse(Buffer.from(body, 'base64url'));
    value.language = 'en';
    assert.equal(oauth.readVerifyState(Buffer.from(JSON.stringify(value)).toString('base64url') + '.' + signature), null);
  } finally {
    if (saved === undefined) delete process.env.VERIFICATION_OAUTH_SECRET;
    else process.env.VERIFICATION_OAUTH_SECRET = saved;
  }
});

test('all verification outcomes have complete English and German views with safe actions', () => {
  for (const language of ['de', 'en']) {
    const { VerifyResult } = load('components/verify-result.tsx', {
      '@/lib/i18n/LanguageContext': { useLanguage: () => ({ language, setLanguage() {} }) },
      'next/link': ({ href, children, ...props }) => React.createElement('a', { href, ...props }, children),
    });
    for (const status of ['success', 'denied', 'error']) {
      const outcome = { guild_id: '1530378233579704370', guild_name: 'Test Guild', status,
        reason: status === 'error' ? 'oauth_cancelled' : undefined, role_name: 'Verified', exp: Date.now() + 1000 };
      const html = renderToStaticMarkup(React.createElement(VerifyResult, { guildId: outcome.guild_id, language, outcome }));
      assert.match(html, language === 'en' ? /Your next steps/ : /Deine nächsten Schritte/);
      if (language === 'en') assert.doesNotMatch(html, /Verifizierung|eingeschränkt|Zurück|Prüfung/);
      assert.equal(html.includes('https://discord.com/channels/'), status === 'success');
      assert.equal(html.includes('/api/verify/start?'), status === 'error');
      if (status === 'error') assert.match(html, new RegExp(`lang=${language}`));
    }
    const invalid = renderToStaticMarkup(React.createElement(VerifyResult, { guildId: 'invalid', language, outcome: null }));
    assert.doesNotMatch(invalid, /\/api\/verify\/start\?/);
  }
});
