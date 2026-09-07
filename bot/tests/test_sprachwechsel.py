#!/usr/bin/env python3
"""
Der Sprachumschalter und sein Woerterbuch.

Drei Dinge werden hier festgehalten:

  1. **Der Schalter steht im Dashboard neben dem Profil.** Der Import
     war schon lange in der Layout-Datei — gerendert wurde er nie.
     Wer im Dashboard war, konnte die Sprache nicht wechseln, obwohl
     Umschalter und Woerterbuch existierten. Die oeffentlichen Seiten
     (site-nav) hatten ihn schon; deren Test prueft das weiter.

  2. **Die Flagge steht vor dem Namen** — im Knopf wie in der Liste.
     Das ist die Vorgabe: Deutschland- und UK-Flagge erkennbar, dann
     der Sprachname.

  3. **Das Woerterbuch ist abgeschlossen und ohne Konflikte.** Ein
     deutscher Schluessel, der zugleich englischer Wert eines anderen
     Paars ist, wuerde beim Zurueckschalten auf Deutsch die
     Rueckuebersetzung des anderen Paars ueberschreiben (buildMap:
     letzte Zusetzung gewinnt). Und die Vorlagen muessen nach
     Spezifitaet sortiert sein, sonst fängt "{1} Tage" zuerst
     "noch 5 Tage" und macht "noch 5 days" daraus.

Warum statisch geprueft wird: im Testlauf gibt es kein Node und keinen
Browser. Die Rundreise der Vorlagen wird deshalb in Python nachgebaut —
templateToRegex ist zehn Zeilen, die sich hier genauso_verhalten wie in
TypeScript (beides reguläre Ausdrücke, beide angekert).

Run:  python3 tests/test_sprachwechsel.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def strip_comments(src: str) -> str:
    """Kommentare raus — sonst trifft die Suche die Erklaerung."""
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- #
# Das Woerterbuch einlesen
# ---------------------------------------------------------------- #
woerterbuch = read("lib", "i18n", "dom-translations.ts")

phrase_pairs: list[tuple[str, str]] = []
for m in re.finditer(
    r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]', woerterbuch
):
    de = json.loads('"' + m.group(1) + '"')
    en = json.loads('"' + m.group(2) + '"')
    phrase_pairs.append((de, en))

pattern_block = woerterbuch[woerterbuch.index("patternPairs"):]
pattern_pairs: list[tuple[str, str]] = []
for m in re.finditer(
    r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]', pattern_block
):
    de = json.loads('"' + m.group(1) + '"')
    en = json.loads('"' + m.group(2) + '"')
    pattern_pairs.append((de, en))

de_keys = [norm(de) for de, _ in phrase_pairs]
en_values = [norm(en) for _, en in phrase_pairs]


# ---------------------------------------------------------------- #
# 1. Der Schalter im Dashboard
# ---------------------------------------------------------------- #
def test_schalter_im_dashboard():
    print("\nDer Schalter steht im Dashboard neben dem Profil")
    layout = strip_comments(read("app", "dashboard", "layout.tsx"))

    check("der Import ist da",
          'from "@/components/language-switcher"' in layout)
    check("und er wird gerendert",
          "<LanguageSwitcher />" in layout)

    # Neben dem Profil heisst: zwischen Trennstrich und Profil-Dropdown.
    # Vorher stand der Import allein da — gerendert wurde er nicht.
    strich = layout.find('<div className="h-8 w-[1px] bg-white/5 hidden sm:block"></div>')
    schalter = layout.find("<LanguageSwitcher />")
    profil = layout.find('ref={profileRef}')
    check("er steht zwischen Trennstrich und Profil",
          -1 < strich < schalter < profil,
          f"(strich={strich}, schalter={schalter}, profil={profil})")


# ---------------------------------------------------------------- #
# 2. Flaggen vor dem Namen
# ---------------------------------------------------------------- #
def test_flaggen_vor_dem_namen():
    print("\nDie Flaggen stehen vor den Sprachnamen")
    src = strip_comments(read("components", "language-switcher.tsx"))

    check("Deutsch hat die Deutschland-Flagge",
          '"🇩🇪"' in src or "🇩🇪" in src)
    check("English hat die UK-Flagge",
          "🇬🇧" in src)

    # Im Knopf: Flagge vor dem Namen (Reihenfolge im Markup).
    button_start = src.find("<button")
    button_end = src.find("</button>", button_start)
    button = src[button_start:button_end]
    flag_pos = button.find("{aktuell.flagge}")
    name_pos = button.find("{aktuell.name}")
    check("im Knopf steht die Flagge vor dem Namen",
          -1 < flag_pos < name_pos,
          f"(flagge={flag_pos}, name={name_pos})")

    # In der Liste: dasselbe fuer jeden Eintrag.
    liste = src[src.find("SPRACHEN.map"):]
    flag_pos = liste.find("{sprache.flagge}")
    name_pos = liste.find("{sprache.name}")
    check("in der Liste steht die Flagge vor dem Namen",
          -1 < flag_pos < name_pos,
          f"(flagge={flag_pos}, name={name_pos})")

    # Beide Sprachen muessen es geben — nicht mehr und nicht weniger.
    check("es gibt genau Deutsch und Englisch",
          'code: "de"' in src and 'code: "en"' in src
          and src.count("code: ") == 2)


# ---------------------------------------------------------------- #
# 3. Woerterbuch-Invarianten
# ---------------------------------------------------------------- #
def test_woerterbuch_invarianten():
    print("\nDas Woerterbuch ist widerspruchsfrei")

    check("es ist deutlich gewachsen",
          len(phrase_pairs) >= 2600,
          f"(hat {len(phrase_pairs)})")

    # Keine doppelten Schluessel — der spaetere wuerde den frueheren
    # stillschweigend ueberschreiben.
    doppel = [k for k in de_keys if de_keys.count(k) > 1]
    check("keine doppelten deutschen Schluessel",
          not doppel, f"-> {doppel[:3]}")

    # Ping-Pong: Ein deutscher Schluessel, der zugleich englischer Wert
    # eines ANDEREN Paars ist, killt im DE-Modus dessen Rueckuebersetzung
    # (buildMap ueberschreibt) und driftet im EN-Modus weiter. Reine
    # Identitaeten — deren Wert nur von ihnen selbst kommt — sind
    # harmlos und zaehlen nicht.
    fremde_werte = {norm(en) for de, en in phrase_pairs if norm(de) != norm(en)}
    konflikt = sorted({k for k in set(de_keys) if k in fremde_werte})
    check("kein Schluessel ist englischer Wert eines anderen Paars",
          not konflikt, f"-> {konflikt[:3]}")

    # Vorlagen: gleiche Platzhalter auf beiden Seiten, fortlaufend.
    schleife = []
    for de, en in pattern_pairs:
        p_de = re.findall(r"\{(\d+)\}", de)
        p_en = re.findall(r"\{(\d+)\}", en)
        if sorted(p_de) != sorted(p_en) or p_en != sorted(p_en, key=int):
            schleife.append((de, en))
    check("Vorlagen haben auf beiden Seiten dieselben Platzhalter",
          not schleife, f"-> {schleife[:2]}")

    # Vorlagen: laengste (spezifischste) zuerst.
    laengen = [len(norm(de)) for de, _ in pattern_pairs]
    check("Vorlagen sind nach Spezifitaet sortiert",
          laengen == sorted(laengen, reverse=True))


# ---------------------------------------------------------------- #
# 4. Rundreise der Vorlagen
# ---------------------------------------------------------------- #
def _escape_regex(text: str) -> str:
    return re.sub(r"([.*+?^${}()|[\]\\])", r"\\\1", text)


def _template_to_regex(template: str):
    pattern = _escape_regex(template)
    pattern = re.sub(r"\\\{(\d+)\\\}", r"(.+?)", pattern)
    return re.compile("^" + pattern + "$")


def _translate(value: str, language: str) -> str:
    key = norm(value)
    quelle, ziel = ("de", "en") if language == "en" else ("en", "de")
    for de, en in pattern_pairs:
        source = de if quelle == "de" else en
        target = en if quelle == "de" else de
        regex = _template_to_regex(norm(source))
        if regex.match(key):
            return regex.sub(
                lambda m: re.sub(r"\{(\d+)\}",
                                 lambda p: m.group(int(p.group(1))),
                                 target),
                key,
            )
    return value


def test_vorlagen_rundreise():
    print("\nDie Vorlagen uebersetzen hin und zurueck")

    faelle = [
        ("12 Titel hinzugefügt.", "12 titles added."),
        ("noch 5 Tage", "5 days left"),
        ("noch 1 Tag", "1 day left"),
        ("seit 30 Minuten", "for 30 minutes"),
        ("30 Minuten", "30 minutes"),
        ("3 von 10 Aktionen erlaubt. Bei allen anderen greift der Schutz weiter.",
         "3 of 10 actions allowed. The protection continues to apply to all others."),
    ]
    for de, en in faelle:
        check(f"„{de[:38]}…“ wird englisch",
              _translate(de, "en") == en,
              f"(bekam {_translate(de, 'en')!r})")
        check(f"„{en[:38]}…“ wird wieder deutsch",
              _translate(en, "de") == norm(de),
              f"(bekam {_translate(en, 'de')!r})")

    # Unbekannter Text darf unberuehrt bleiben.
    check("unbekannter Text bleibt stehen",
          _translate("Beliebiger Text ohne Vorlage", "en")
          == "Beliebiger Text ohne Vorlage")


# ---------------------------------------------------------------- #
# 5. Stichproben aus allen Bereichen
# ---------------------------------------------------------------- #
def test_stichproben():
    print("\nStichproben aus allen Dashboard-Bereichen")

    # Je Bereich ein deutscher Text, der vorher unuebersetzt blieb.
    stichproben = [
        ("Server-Werkzeuge", "Server Tools"),                     # Sidebar
        ("Wird geladen …", "Loading …"),                          # Panels
        ("Kanal wählen …", "Select a channel …"),                 # Formulare
        ("Das lässt sich nicht rückgängig machen.",
         "This cannot be undone."),                               # Dialoge
        ("Häufige Fragen", "Frequently Asked Questions"),         # Landing
        ("Verfügbarkeit in Echtzeit", "Availability in real time"),
        ("Zähler verwalten", "Manage counter"),                   # Counting
        ("Support-Server", "Support Server"),                     # Navi
    ]
    mapping = {norm(de): en for de, en in phrase_pairs}
    for de, en in stichproben:
        check(f"„{de}“ ist uebersetzt",
              mapping.get(norm(de)) == en,
              f"(hat {mapping.get(norm(de))!r})")

    # Die mobile Ansicht des Umschalters zeigt mindestens die Flagge:
    # der Name darf auf schmalen Bildschirmen fehlen, die Flagge nicht.
    src = strip_comments(read("components", "language-switcher.tsx"))
    name_span = re.search(r"<span[^>]*hidden sm:inline[^>]*>", src)
    check("auf schmalen Bildschirmen bleibt die Flagge sichtbar",
          "text-base" in src and name_span is not None)


if __name__ == "__main__":
    test_schalter_im_dashboard()
    test_flaggen_vor_dem_namen()
    test_woerterbuch_invarianten()
    test_vorlagen_rundreise()
    test_stichproben()

    print()
    if failures:
        print(f"{len(failures)} Pruefung(en) fehlgeschlagen:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
