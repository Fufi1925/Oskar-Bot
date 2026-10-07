const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

function load(file, imports) {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports,
    require: name => Object.hasOwn(imports, name) ? imports[name] : require(name),
  });
  return module.exports;
}

function render({ enabled = true, loading = false, error = false,
                  pathname = "/dashboard/guild/123/honeypot", loadedPath = pathname } = {}) {
  const states = [enabled, loading, false, error, 0, loadedPath];
  const { GuildModuleStatus } = load("components/dashboard/guild-module-status.tsx", {
    react: { ...React, useState: () => [states.shift(), () => {}], useEffect: () => {}, useMemo: callback => callback() },
    "next/navigation": { usePathname: () => pathname },
    "@/lib/i18n/LanguageContext": { useLanguage: () => ({ language: "en" }) },
    "@/lib/utils": { cn: (...args) => args.filter(Boolean).join(" ") },
    "@/lib/api": { api: {} },
    "@/lib/guild-modules": load("lib/guild-modules.ts", {}),
  });
  return renderToStaticMarkup(React.createElement(GuildModuleStatus, { guildId: "123" },
    React.createElement("div", {}, "PRIVATE_MODULE_SETTINGS")));
}

test("disabled module renders only its enable control", () => {
  const html = render({ enabled: false });
  assert.match(html, /Enable/);
  assert.doesNotMatch(html, /PRIVATE_MODULE_SETTINGS/);
});
test("enabled module reveals its existing settings", () => {
  assert.match(render(), /PRIVATE_MODULE_SETTINGS/);
});
test("loading, failed state and navigating to another module hide settings", () => {
  for (const state of [{ loading: true }, { error: true }, { loadedPath: "/dashboard/guild/123/music" }]) {
    assert.doesNotMatch(render(state), /PRIVATE_MODULE_SETTINGS/);
  }
});
test("tools without a module switch remain visible", () => {
  assert.match(render({ pathname: "/dashboard/guild/123/compose", loading: true }), /PRIVATE_MODULE_SETTINGS/);
});
