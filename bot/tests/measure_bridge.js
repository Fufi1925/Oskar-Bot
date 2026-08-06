/**
 * Fuehrt die ECHTE `measure()` aus popover-layer.tsx aus.
 *
 * Warum diese Bruecke noetig ist
 * ------------------------------
 * Der Test hat die Rechnung zuerst in Python nachgebaut. Das war ein
 * Fehler, und der Mutationstest hat ihn aufgedeckt: die Mutation
 * "Hoehe ignoriert den freien Platz" blieb gruen, weil die Python-
 * Kopie weiterrechnete wie zuvor. Geprueft wurde damit die Kopie,
 * nicht der Code, der im Browser laeuft.
 *
 * Eine nachgebaute Rechnung kann nur beweisen, dass der Nachbau
 * stimmt. Hier wird deshalb die Funktion selbst geladen.
 *
 * `measure()` ist bewusst frei von React und DOM -- sie nimmt Zahlen
 * und gibt Zahlen zurueck. Deshalb genuegt es, die Typannotationen zu
 * entfernen und den Rest als JavaScript auszufuehren; ein Bundler
 * waere fuer eine reine Rechenfunktion zu viel Apparat.
 *
 * Aufruf:  node measure_bridge.js '<json>'
 * Ausgabe: das Ergebnis als JSON auf stdout.
 */

const fs = require("fs");
const path = require("path");
const ts = require(
  path.join(
    __dirname,
    "..",
    "..",
    "dashboard",
    "node_modules",
    "typescript",
    "lib",
    "typescript.js"
  )
);

const SOURCE = path.join(
  __dirname,
  "..",
  "..",
  "dashboard",
  "components",
  "ui",
  "popover-layer.tsx"
);

const raw = fs.readFileSync(SOURCE, "utf8");

// Nur den Teil bis zur ersten React-Komponente uebersetzen. Alles
// darunter braucht React; `measure()` und die beiden Konstanten
// stehen davor und kommen ohne aus.
const cut = raw.indexOf("export function PopoverLayer");
const head = cut === -1 ? raw : raw.slice(0, cut);

const js = ts.transpileModule(head, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.Preserve,
  },
}).outputText;

// Die Importe zeigen auf React und `@/lib/utils`. Beide werden von
// `measure()` nicht gebraucht, sind hier aber nicht aufloesbar --
// also entfernen statt zu laden.
const clean = js
  .split("\n")
  .filter((line) => !/^\s*(const|var)\s+\w+\s*=\s*require\(/.test(line))
  .join("\n");

const module_ = { exports: {} };
new Function("module", "exports", clean)(module_, module_.exports);

if (typeof module_.exports.measure !== "function") {
  console.error("measure() wurde nicht gefunden -- ist sie noch exportiert?");
  process.exit(2);
}

const input = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(module_.exports.measure(input)));
