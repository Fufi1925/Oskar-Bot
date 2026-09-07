#!/usr/bin/env python3
"""Baut die neuen dom-translations-Eintraege aus den Autoring-Batches.

Macht drei Dinge:

 1. Statische Paare (batch_001 … batch_008) in phrasePairs einfuegen.
 2. Vorlagen-Paare (dynamic_pairs.json) als neuen patternPairs-Abschnitt
    einfuegen — fuer Texte, in die zur Laufzeit Werte eingesetzt werden.
 3. Konflikte pruefen: Ein deutscher Schluessel, der zugleich englischer
    Wert eines anderen Paars ist, wuerde beim zurueckschalten
    ueberschrieben. Solche Eintraege werden verworfen und gemeldet.

Escapes: Die extrahierten Schluessel enthalten die Literal-Sequenz \n
(Backslash + n) aus dem Quelltext. Zur Laufzeit steht dort ein echter
Zeilenumbruch — der Generator wandelt deshalb \n, \t, \\, \" in echte
Zeichen um. HTML-Entities (&auml; &bdquo; &mdash; …) dekodiert React in
JSX-Texten und -Attributen; auch sie werden aufgeloest.
"""
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "i18n_work"
DASH = HERE.parent / "dashboard"
TARGET = DASH / "lib" / "i18n" / "dom-translations.ts"

# ── Escapes ───────────────────────────────────────────────────────
def unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 5 < len(s) and s[i + 1] == "u":
            digits = s[i + 2:i + 6]
            if re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                out.append(chr(int(digits, 16)))
                i += 6
                continue
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "n":
                out.append("\n"); i += 2; continue
            if nxt == "t":
                out.append("\t"); i += 2; continue
            if nxt == "r":
                out.append("\r"); i += 2; continue
            if nxt == "\\":
                out.append("\\"); i += 2; continue
            if nxt == '"':
                out.append('"'); i += 2; continue
            if nxt == "'":
                out.append("'"); i += 2; continue
        out.append(c)
        i += 1
    return "".join(out)

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

# ── Bestehendes Woerterbuch einlesen ──────────────────────────────
src = TARGET.read_text(encoding="utf-8")

existing_pairs: list[tuple[str, str]] = []
for m in re.finditer(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]', src):
    de = json.loads('"' + m.group(1) + '"')
    en = json.loads('"' + m.group(2) + '"')
    existing_pairs.append((de, en))

existing_de_keys = {norm(de) for de, _ in existing_pairs}
existing_en_vals = {norm(en) for _, en in existing_pairs}
print(f"Bestehende Paare: {len(existing_pairs)}")

# ── Konflikt-Identitaeten im Bestand entfernen ────────────────────
# Das alte Woerterbuch enthaelt 140 Identitaeten wie
# ["Authenticated As", "Authenticated As"] ZUSAMTZU den deutschen
# Paaren ["Authentifiziert als", "Authenticated As"]. buildMap setzt
# map[en]=de der Reihe nach — die spaetere Identitaet ueberschreibt
# die Rueckuebersetzung: Beim Zurueckschalten auf Deutsch blieben
# diese 140 Texte englisch. Sie fliegen raus; das deutsche Paar
# uebernimmt beide Richtungen.
en_val_count: dict[str, int] = {}
for _, en in existing_pairs:
    k = norm(en)
    en_val_count[k] = en_val_count.get(k, 0) + 1
konflikt_identitaeten = {
    (de, en) for de, en in existing_pairs
    if norm(de) == norm(en) and en_val_count.get(norm(en), 0) > 1
}
if konflikt_identitaeten:
    print(f"\nKonflikt-Identitaeten im Bestand entfernt: {len(konflikt_identitaeten)}")
    for de, _ in sorted(konflikt_identitaeten)[:5]:
        print(f"  - {de[:70]}")
    if len(konflikt_identitaeten) > 5:
        print(f"  … und {len(konflikt_identitaeten) - 5} weitere")

# ── Batches laden ─────────────────────────────────────────────────
static: dict[str, str] = {}
for p in sorted(WORK.glob("batch_*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    for k, v in data.items():
        k2 = unescape(html.unescape(k))
        v2 = unescape(html.unescape(v))
        if k2 in static and static[k2] != v2:
            print(f"  KONFLIKT in {p.name}: {k2[:60]!r} -> {static[k2][:40]!r} vs {v2[:40]!r}")
        static[k2] = v2
print(f"Statische Neueintraege (roh): {len(static)}")

dyn = json.loads((WORK / "dynamic_pairs.json").read_text(encoding="utf-8"))
dyn_pairs = [(unescape(html.unescape(k)), unescape(html.unescape(v)))
             for k, v in dyn.items()]
# Reihenfolge = Spezifitaet. translateValue probiert die Vorlagen der
# Reihe nach, und „{1} Tage“ wuerde sonst „noch 5 Tage“ als („noch 5“,
# „Tage“) fangen, bevor „noch {1} Tage“ drankommt. Das laengere Template
# hat mehr festen Text und gewinnt so immer zuerst — in beide Richtungen,
# weil beide aus derselben Liste gebaut werden. Gemessen wird die
# normalisierte Laenge, genau wie im Test.
dyn_pairs.sort(key=lambda p: len(norm(p[0])), reverse=True)
print(f"Vorlagen-Paare (roh): {len(dyn_pairs)}")

# ── Konfliktpruefung ──────────────────────────────────────────────
def check_no_chains(pairs, label):
    """de-Schluessel, die zugleich en-Wert sind, wuerden beim
    zurueckschalten (DE-Modus) ueberschrieben: buildMap setzt
    map[en]=de, und spaeter gesetzte Identitaeten wuerden das
    kaputtmachen. Solche Eintraege fliegen raus."""
    en_vals = {norm(en) for _, en in pairs}
    kept, dropped = [], []
    for de, en in pairs:
        k = norm(de)
        if k in existing_en_vals and k not in existing_de_keys:
            # Es gibt schon ein Paar X -> k. Unser Eintrag k -> en
            # wuerde im DE-Modus die Rueckuebersetzung von k killen,
            # wenn er spaeter in die Map kommt. Nur Identitaeten sind
            # da eine Gefahr; andere sind schlicht nutzlos.
            dropped.append((de, en, "Schluessel ist bereits englischer Wert"))
            continue
        kept.append((de, en))
    # Identitaeten, deren Schluessel zugleich englischer Wert eines
    # ANDEREN neuen Paars ist, wuerden dessen Rueckuebersetzung
    # ueberschreiben (buildMap: letzte Zusetzung gewinnt). Die
    # Identitaet selbst zaehlt dabei nicht mit — sonst fliegen alle
    # Identitaeten raus, genau wie „Server Stats“ es tat.
    en_val_count: dict[str, int] = {}
    for _, en in kept:
        en_val_count[norm(en)] = en_val_count.get(norm(en), 0) + 1
    kept2 = []
    for de, en in kept:
        k = norm(de)
        if k == norm(en) and en_val_count.get(k, 0) > 1:
            dropped.append((de, en, "Identitaet kollidiert mit Rueckuebersetzung"))
            continue
        kept2.append((de, en))
    kept = kept2
    # Drift: Ein neuer englischer Wert, der zugleich deutscher Schluessel
    # eines BESTEHENDEN Paars ist, wuerde im EN-Modus weiteruebersetzt:
    # Durchlauf 1 macht aus X den Wert, Durchlauf 2 uebersetzt ihn nochmal.
    existing_de_nonident = {norm(d) for d, e in existing_pairs
                            if norm(d) != norm(e)}
    kept3 = []
    for de, en in kept:
        if norm(en) in existing_de_nonident and norm(de) != norm(en):
            dropped.append((de, en, "Englischer Wert ist deutscher Schluessel (Drift)"))
            continue
        kept3.append((de, en))
    kept = kept3
    # Ketten: en-Wert, der zugleich de-Schluessel eines anderen Paars ist
    all_de_keys = {norm(d) for d, _ in kept} | existing_de_keys
    chain = [(de, en) for de, en in kept
             if norm(en) in all_de_keys and norm(en) != norm(de)]
    if dropped:
        print(f"\n{label}: verworfen ({len(dropped)}):")
        for de, en, why in dropped:
            print(f"  - {de[:70]!r} ({why})")
    if chain:
        print(f"\n{label}: Kettenrisiko ({len(chain)}):")
        for de, en in chain:
            print(f"  ! {de[:50]!r} -> {en[:50]!r}")
    return kept

static_kept = check_no_chains(list(static.items()), "statisch")

# Dedupe gegen bestehende Schluessel
final_static = []
seen = set()
for de, en in static_kept:
    k = norm(de)
    if k in seen:
        continue
    if k in existing_de_keys:
        continue  # schon abgedeckt
    seen.add(k)
    final_static.append((de, en))
print(f"\nStatische Neueintraege (endgueltig): {len(final_static)}")

# ── TS-Escaping ───────────────────────────────────────────────────
def ts_str(s: str) -> str:
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return '"' + out + '"'

# ── Korrigierte Batch-Werte im Bestand aktualisieren ──────────────
# Frühere Versionen konnten nur anhängen. Dadurch blieb eine später im
# reviewbaren JSON-Batch korrigierte Übersetzung in der TS-Datei unverändert.
# Da die Batches jetzt dedupliziert sind, darf der jeweils aktuelle Wert einen
# bereits generierten Eintrag mit demselben deutschen Schlüssel ersetzen.
static_by_norm = {norm(de): (de, en) for de, en in static.items()}
updated_existing = 0
for old_de, old_en in existing_pairs:
    replacement_pair = static_by_norm.get(norm(old_de))
    if not replacement_pair:
        continue
    new_de, new_en = replacement_pair
    if old_de == new_de and old_en == new_en:
        continue
    old_line = f"  [{ts_str(old_de)}, {ts_str(old_en)}],"
    new_line = f"  [{ts_str(new_de)}, {ts_str(new_en)}],"
    if old_line in src:
        src = src.replace(old_line, new_line, 1)
        updated_existing += 1
if updated_existing:
    print(f"Bestehende Batch-Eintraege aktualisiert: {updated_existing}")

# ── Konflikt-Identitaeten aus der Datei loeschen ──────────────────
konflikt_zeilen = {f"  [{ts_str(de)}, {ts_str(en)}]," for de, en in konflikt_identitaeten}
for zeile in konflikt_zeilen:
    assert zeile in src, f"Zeile nicht gefunden: {zeile[:80]}"
src = "\n".join(l for l in src.split("\n") if l not in konflikt_zeilen)

# ── phrasePairs erweitern ─────────────────────────────────────────
lines = [f"  [{ts_str(de)}, {ts_str(en)}]," for de, en in final_static]
block = (
    "\n  // ════════════════════════════════════════════════════════════════\n"
    "  // Vollstaendige Abdeckung der Dashboard-Oberflaeche. Diese Eintraege\n"
    "  // stammen aus tools/build_dom_translations.py — nicht von Hand hier\n"
    "  // pflegen, sondern die Batches in tools/i18n_work/ anpassen und den\n"
    "  // Generator neu laufen lassen.\n"
    "  // ════════════════════════════════════════════════════════════════\n"
    + "\n".join(lines)
    + "\n"
)

# Einfuegen vor dem schliessenden `];` von phrasePairs. Beim ersten Lauf
# folgt direkt normalise(), bei späteren Läufen der bereits generierte
# patternPairs-Block. Der Generator muss inkrementell erneut ausführbar sein.
already_generated = "export const patternPairs" in src
if already_generated:
    anchor = "\n];\n\n/**\n * Vorlagen fuer Texte"
    replacement = "\n" + block + "];\n\n/**\n * Vorlagen fuer Texte"
else:
    anchor = "\n];\n\nfunction normalise"
    replacement = "\n" + block + "];\n\nfunction normalise"
assert anchor in src, "Einfuegepunkt (phrasePairs-Ende) nicht gefunden"
new_src = src.replace(anchor, replacement, 1) if final_static else src

# ── patternPairs + Mechanik einfuegen ─────────────────────────────
pat_lines = [f"  [{ts_str(de)}, {ts_str(en)}]," for de, en in dyn_pairs]
pat_block = (
    "\n/**\n"
    " * Vorlagen fuer Texte, in die React zur Laufzeit Werte einsetzt —\n"
    " * Meldungen wie „12 Titel hinzugefügt.“, die nie wortgleich im\n"
    " * Quelltext stehen. `{1}`, `{2}` … stehen fuer die eingesetzten\n"
    " * Teile; daraus werden ankervolle Regexen mit Fanggruppen gebaut.\n"
    " * Einträge mit Einzahl/Mehrzahl-Ternären im Quelltext stehen hier\n"
    " * doppelt — einmal je Laufzeitform.\n"
    " */\n"
    "export const patternPairs: Array<[de: string, en: string]> = [\n"
    + "\n".join(pat_lines)
    + "\n];\n\n"
    "interface PatternMatcher {\n"
    "  pattern: RegExp;\n"
    "  replacement: string;\n"
    "}\n\n"
    "function escapeRegex(text: string) {\n"
    "  return text.replace(/[.*+?^${}()|[\\]\\\\]/g, \"\\\\$&\");\n"
    "}\n\n"
    "function templateToRegex(template: string) {\n"
    "  // Erst alles escapen, dann die (escapten) Platzhalter zu\n"
    "  // Fanggruppen machen — so kann kein Template-Inhalt die Regex\n"
    "  // umbiegen.\n"
    "  return new RegExp(\n"
    "    \"^\" + escapeRegex(template).replace(/\\\\\\{(\\d+)\\\\\\}/g, \"(.+?)\") + \"$\",\n"
    "  );\n"
    "}\n\n"
    "function templateToReplacement(template: string) {\n"
    "  return template.replace(/\\{(\\d+)\\}/g, \"$$$1\");\n"
    "}\n\n"
    "function buildPatternMatchers(language: Language): PatternMatcher[] {\n"
    "  return patternPairs.map(([de, en]) => {\n"
    "    const source = language === \"de\" ? en : de;\n"
    "    const target = language === \"de\" ? de : en;\n"
    "    return {\n"
    "      pattern: templateToRegex(normalise(source)),\n"
    "      replacement: templateToReplacement(target),\n"
    "    };\n"
    "  });\n"
    "}\n"
)

if already_generated:
    # Nur den Datenblock ersetzen; die darunterliegende Laufzeitmechanik bleibt
    # unverändert. So lassen sich neue Batches jederzeit reproduzierbar bauen.
    pattern_start = new_src.index("export const patternPairs")
    pattern_end = new_src.index("\n];", pattern_start) + len("\n];")
    data_only = (
        "export const patternPairs: Array<[de: string, en: string]> = [\n"
        + "\n".join(pat_lines)
        + "\n];"
    )
    new_src = new_src[:pattern_start] + data_only + new_src[pattern_end:]
else:
    # patternPairs beim ersten Lauf hinter phrasePairs definieren.
    pp_end = new_src.index("];", new_src.index("export const phrasePairs"))
    insert_at = new_src.index("\n", pp_end) + 1
    new_src = new_src[:insert_at] + pat_block + new_src[insert_at:]

# ── buildMap & translateValue & translateDashboardDom anpassen ────
old_buildmap = """function buildMap(language: Language) {
  const map = new Map<string, string>();
  for (const [de, en] of phrasePairs) {
    if (language === "de") {
      map.set(normalise(en), de);
    } else {
      map.set(normalise(de), en);
    }
  }
  return map;
}"""
new_buildmap = """function buildMap(language: Language) {
  const map = new Map<string, string>();
  for (const [de, en] of phrasePairs) {
    if (language === "de") {
      map.set(normalise(en), de);
    } else {
      map.set(normalise(de), en);
    }
  }
  return map;
}

function buildTranslator(language: Language) {
  return {
    map: buildMap(language),
    patterns: buildPatternMatchers(language),
  };
}"""
if not already_generated:
    if old_buildmap not in new_src:
        raise AssertionError("buildMap nicht gefunden")
    new_src = new_src.replace(old_buildmap, new_buildmap, 1)

old_translate = """function translateValue(value: string, map: Map<string, string>) {
  const key = normalise(value);
  if (!key) return value;
  const translated = map.get(key);
  return translated ? preserveWhitespace(value, translated) : value;
}"""
new_translate = """function translateValue(
  value: string,
  map: Map<string, string>,
  patterns: PatternMatcher[],
) {
  const key = normalise(value);
  if (!key) return value;
  const translated = map.get(key);
  if (translated) return preserveWhitespace(value, translated);
  // Kein exakter Treffer — dann die Vorlagen probieren. Die laufen auf
  // dem normalisierten Text, damit Zeilenumbrueche in Bestaetigungen
  // nicht zum Match killer werden.
  for (const { pattern, replacement } of patterns) {
    if (pattern.test(key)) {
      return preserveWhitespace(value, key.replace(pattern, replacement));
    }
  }
  return value;
}"""
if not already_generated:
    if old_translate not in new_src:
        raise AssertionError("translateValue nicht gefunden")
    new_src = new_src.replace(old_translate, new_translate, 1)

old_dom = """export function translateDashboardDom(language: Language, root: ParentNode = document) {
  if (typeof document === "undefined") return;
  const map = buildMap(language);"""
new_dom = """export function translateDashboardDom(language: Language, root: ParentNode = document) {
  if (typeof document === "undefined") return;
  const { map, patterns } = buildTranslator(language);"""
if not already_generated:
    if old_dom not in new_src:
        raise AssertionError("translateDashboardDom nicht gefunden")
    new_src = new_src.replace(old_dom, new_dom, 1)

new_src = new_src.replace(
    "const translated = translateValue(current, map);",
    "const translated = translateValue(current, map, patterns);", 1)
new_src = new_src.replace(
    "const translated = translateValue(value, map);",
    "const translated = translateValue(value, map, patterns);", 1)

# ── Dateikopf: Hinweis, dass diese Datei aus dem Generator kommt ──
old_kopf = (
    " * new code, but this bridge makes the language switcher apply consistently\n"
    " * across the existing UI without rewriting every page by hand.\n"
    " */"
)
new_kopf = (
    " * new code, but this bridge makes the language switcher apply consistently\n"
    " * across the existing UI without rewriting every page by hand.\n"
    " *\n"
    " * GENERIERT — bitte nicht von Hand pflegen. Neue Texte gehoeren in\n"
    " * die Batches unter tools/i18n_work/; danach\n"
    " * tools/build_dom_translations.py neu laufen lassen.\n"
    " */"
)
if old_kopf in new_src:
    new_src = new_src.replace(old_kopf, new_kopf, 1)
else:
    print("Hinweis: Dateikopf enthaelt den Generator-Hinweis bereits.")

TARGET.write_text(new_src, encoding="utf-8")
print(f"\nGeschrieben: {TARGET}")
print(f"  phrasePairs: +{len(final_static)} (gesamt {len(existing_pairs) + len(final_static)})")
print(f"  patternPairs: {len(dyn_pairs)}")
