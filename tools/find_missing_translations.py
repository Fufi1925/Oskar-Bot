#!/usr/bin/env python3
"""Extrahiert ALLE deutschen UI-Texte des Dashboards und vergleicht
sie mit dem dom-translations-Woerterbuch.

Ziel: eine vollstaendige Liste der Texte, die beim Sprachwechsel
unuebersetzt bleiben wuerden.

Bewusst NICHT aufgenommen:
  - lib/i18n/*                  -> das Woerterbuch selbst

Auch Changelog und Rechtstexte werden geprüft: Der Sprachumschalter gilt
für die gesamte Website, nicht nur für das Dashboard.
"""
import html
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboard"

SKIP_FILES = {
    "lib/i18n/dom-translations.ts",
    "lib/i18n/translations.ts",
    "lib/i18n/LanguageContext.tsx",
}

# ── Vorhandenes Woerterbuch ──────────────────────────────────────
src = (DASH / "lib" / "i18n" / "dom-translations.ts").read_text(encoding="utf-8")

known = set()
for m in re.finditer(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]', src):
    de = json.loads('"' + m.group(1) + '"')
    en = json.loads('"' + m.group(2) + '"')
    # Quelltexte dürfen historisch deutsch oder englisch sein. Beide Seiten
    # sind durch buildMap abgedeckt und gelten deshalb als übersetzt.
    for value in (de, en):
        normalised = re.sub(r"\s+", " ", value).strip()
        known.add(normalised)
        known.add(normalised.casefold())
print(f"Vorhandene Woerterbucheintraege: {len(known)}")

# ── t()-Schluessel aus translations.ts (die sind per t() abgedeckt)
tsrc = (DASH / "lib" / "i18n" / "translations.ts").read_text(encoding="utf-8")
tkeys = set(re.findall(r"^\s{4}(\w+):", tsrc, flags=re.M))
t_values = set(re.findall(r'"([^"\n]+)"', tsrc))
known |= t_values

GERMAN_HINT = re.compile(
    r"[äöüßÄÖÜ]|"
    r"\b(der|die|das|den|dem|ein|eine|einen|einem|einer|und|oder|ist|sind|wird|werden|"
    r"mit|für|von|vom|zum|zur|auf|aus|bei|nach|nicht|kein|keine|wenn|dann|noch|schon|"
    r"alle|aller|kann|muss|soll|haben|hat|sein|war|über|unter|neue|neuer|neues|"
    r"bitte|hier|deine|dein|deinen|diese|dieser|dieses|jetzt|erst|auch|nur|wie|was|"
    r"Server|Servern|Kanal|Kanäle|Rolle|Rollen|Mitglied|Mitglieder|Nachricht|Nachrichten|"
    r"Einstellungen|Aktiviert|Deaktiviert|Speichern|Löschen|Abbrechen|Suchen|Suche|"
    r"Hinzufügen|hinzufügen|Erstellen|erstellen|Bearbeiten|bearbeiten|Aktualisieren|"
    r"Erfolgreich|Fehlgeschlagen|geladen|Laden|gespeichert|gesendet|"
    r"Emoji|Emojis|Ticket|Tickets|Guilds|Kategorie|Kategorien|Wochen|Tage|Stunden|"
    r"Minuten|Sekunden|Jahre|Monate|Beispiel|Hinweis|Tipp|Warnung|Erklärung)\b"
)

def is_technical(t: str) -> bool:
    """Strings, die sicher keine sichtbaren Woerter sind."""
    # Treffer, die über mehrere benachbarte JS-/JSX-Tokens hinweggehen,
    # stammen aus dem groben String-Literal-Scanner und sind kein DOM-Text.
    if any(marker in t for marker in (
        "useState", "React.useState", " const [", "a.status ===",
        ", icon: Server, color:", ">Kanal</option>", ">Rolle</option>",
        ",`Server-Präfix (", "return (", ": Array", ": Record",
        "onChange: (", "entries.length ===", "!data ? (", ".replace(",
        "useRef", ".displayName", "React.forwardRef", "VariantProps",
        "ComponentProps", "setDraft:", "React.Dispatch", "safeName",
        "config.parameters.length", "a.trim().length", "Number(value(",
        "applyMany(", "setMany(", "if(!", "); if (", "; return",
        "for (let", ".trim().length", "draft as ", "request.status",
        "items.length", "limits.accept_", "limits.max_", "React.FocusEvent",
        "const target", "p.wert", "live.queue.length", "type ===",
        "teamAccess?.", "preview.content", "marketplace)return", "r.note) && (",
    )):
        return True
    if t in {"Promise", "$1"}:
        return True
    if re.fullmatch(r"\{[a-zA-Z0-9_.-]+\}", t):
        return True
    if t.startswith((") :", ": i ", "= (", "= 0", "();", "0 &&")):
        return True
    if t.startswith(("next-auth.", "ec.europa.eu/", "db/")):
        return True
    if "${" in t and t.count("${") > t.count("}"):
        return True
    if re.fullmatch(r"[\d\s()!<>=&|?:;.+-]+", t):
        return True
    if re.search(r"(slate|amber|emerald|blue|red|rose|indigo|violet|pink|cyan|teal|lime|sky|fuchsia|orange|yellow|purple)-\d", t):
        return True  # Tailwind-Klassen
    if re.match(r"^(bg|text|border|rounded|flex|grid|font|w|h|p|m|gap|items|justify|shadow|ring|space|tracking|leading|uppercase|lowercase|overflow|transition|animate|duration|delay|hover|focus|group|peer|absolute|relative|sticky|fixed|z-|opacity|scale|rotate|translate|min|max|col|row|grid-cols|aspect|object|truncate|whitespace|break|list|decoration|underline|italic|bold|semibold|normal|thin|light|black|hidden|block|inline|w-full|h-full)", t) and " " not in t:
        return True
    if t.startswith(("/", "./", "../", "@/", "http://", "https://", "#", "mailto:", "data:")):
        return True
    if re.fullmatch(r"[a-z0-9_\-]+", t):  # reine slug/identifier
        return True
    if re.fullmatch(r"[A-Z0-9_\-]+", t):  # Konstanten
        return True
    if re.fullmatch(r"[\w\s]*\.(png|jpg|jpeg|gif|webp|svg|mp3|mp4|ttf|woff2?)", t, re.I):
        return True
    if re.fullmatch(r"[\d\s.,:%+\-–—/()]+", t):  # reine Zahlen/Symbole
        return True
    return False

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def decode_source_literal(value: str) -> str:
    """Entspricht den Escapes, die JavaScript/JSX vor der DOM-Ausgabe
    auflöst. So werden `\\n`, `\\u00fc` und HTML-Entities mit den echten
    Laufzeittexten im Wörterbuch verglichen."""
    value = html.unescape(value)
    value = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )
    replacements = {r"\n": "\n", r"\t": "\t", r"\r": "\r", r'\"': '"', r"\'": "'", r"\\": "\\"}
    for escaped, actual in replacements.items():
        value = value.replace(escaped, actual)
    return value

def runtime_templates(text: str) -> set[str]:
    """Ermittelt die möglichen DOM-Texte eines JS-Templates.

    Normale Ausdrücke werden zu `{1}`, `{2}` …; einfache Ternäre mit zwei
    String-Literalen werden in beide Laufzeitvarianten aufgefächert. Dadurch
    gelten z. B. sowohl `1 Tag` als auch `2 Tage` nur dann als abgedeckt, wenn
    beide patternPairs existieren.
    """
    variants = [""]
    i = 0
    number = 1
    while i < len(text):
        if not text.startswith("${", i):
            variants = [value + text[i] for value in variants]
            i += 1
            continue
        j, depth, quote, escaped = i + 2, 1, None, False
        while j < len(text) and depth:
            char = text[j]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in "'\"`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            j += 1
        expression = text[i + 2:j - 1]
        ternary = re.search(
            r"\?\s*([\"'])((?:\\.|(?!\1).)*)\1\s*:\s*([\"'])((?:\\.|(?!\3).)*)\3\s*$",
            expression,
        )
        if ternary:
            choices = [decode_source_literal(ternary.group(2)), decode_source_literal(ternary.group(4))]
            variants = [value + choice for value in variants for choice in choices]
        else:
            variants = [value + f"{{{number}}}" for value in variants]
            number += 1
        i = j
    return {norm(decode_source_literal(value)) for value in variants}

candidates = {}

def add(text, rel, require_german=True):
    t = norm(text)
    runtime = norm(decode_source_literal(text))
    if len(runtime) < 2 or runtime in known or runtime.casefold() in known or is_technical(runtime):
        return
    if "${" in t:
        templates = runtime_templates(t)
        if templates.issubset(known) or {value.casefold() for value in templates}.issubset(known):
            return
    if require_german and not GERMAN_HINT.search(runtime):
        return
    candidates.setdefault(t, set()).add(rel)

files = []
for p in DASH.rglob("*"):
    if p.suffix in (".tsx", ".ts") and "node_modules" not in p.parts and ".next" not in p.parts:
        rel = str(p.relative_to(DASH)).replace("\\", "/")
        if rel in SKIP_FILES:
            continue
        files.append((p, rel))
print(f"Zu scannende Dateien: {len(files)}")

for p, rel in files:
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        continue
    # Kommentare entfernen
    c = re.sub(r"/\*.*?\*/", "", content, flags=re.S)
    c = re.sub(r"^\s*//.*$", "", c, flags=re.M)

    # 1) Attribute mit UI-Charakter
    for attr in ("placeholder", "title", "aria-label", "label", "name", "text", "hint",
                 "description", "error", "heading", "caption", "message", "emptyText",
                 "empty", "confirmLabel", "cancelLabel", "saveLabel", "tooltip"):
        for m in re.finditer(attr + r'=s?"((?:[^"\\\n]|\\.)*)"', c):
            add(m.group(1), rel, require_german=False)
        for m in re.finditer(attr + r'=\{s?"((?:[^"\\\n]|\\.)*)"\s*\}', c):
            add(m.group(1), rel, require_german=False)

    # 2) JSX-Text zwischen > und < (auch mehrzeilig), ohne {} Ausdruecke
    for m in re.finditer(r">\s*([^<>{}]+?)\s*<", c, flags=re.S):
        txt = m.group(1)
        # Mehrzeilig: als eine Zeichenkette normalisiert aufnehmen
        add(txt, rel, require_german=False)

    # 3) Objekt-Literale
    for m in re.finditer(r"\b(?:label|name|text|hint|title|description|placeholder|value|"
                         r"heading|caption|message|emptyText|error)\s*:\s*\"((?:[^\"\\\n]|\\.)*)\"", c):
        add(m.group(1), rel, require_german=False)

    # 4) Toast-Meldungen (template literals eingeschlossen)
    for m in re.finditer(r"toast\.(?:success|error|info|loading|warning|promise)\(\s*[\"'`]([^\"'`\n]+)[\"'`]", c):
        add(m.group(1), rel, require_german=False)
    for m in re.finditer(r"toast\.(?:success|error|info|loading|warning|promise)\.\w+\(\s*[\"'`]([^\"'`\n]+)[\"'`]", c):
        add(m.group(1), rel, require_german=False)

    # 5) Alle restlichen String-Literale mit deutschem Wort (fangt Arrays, Optionen)
    for m in re.finditer(r'"((?:[^"\\\n]|\\.){2,})"', c):
        add(m.group(1), rel)
    # Template-Literale mit ${...} und deutschem Wort (dynamische Meldungen)
    for m in re.finditer(r"`((?:[^`\\\n]|\\.){4,})`", c):
        if "${" in m.group(1):
            add(m.group(1), rel)

print(f"\nKandidaten ohne Uebersetzung: {len(candidates)}")

out = []
for t, rels in sorted(candidates.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    out.append({"text": t, "files": sorted(rels)})

if "--check" in sys.argv:
    if out:
        print("Fehlende Übersetzungen:")
        for item in out[:20]:
            print(f"  - {item['text'][:120]} ({', '.join(item['files'])})")
        sys.exit(1)
    print("Vollständige Übersetzungsabdeckung bestätigt.")
else:
    (ROOT / "tools" / "missing_translations.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Gespeichert: tools/missing_translations.json")
