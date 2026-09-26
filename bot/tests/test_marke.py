#!/usr/bin/env python3
"""
Der Name des Bots ist „University Bot" — in jeder Sprache, ueberall.

Warum ein eigener Test dafuer existiert
--------------------------------------
Der Name stand an drei Orten verschieden: im Code „University Bot", in
einer Railway-Variable „Universitätsbot" und in der Bot-Konfiguration
„universitybot X" (ein Rest einer frueheren Umbenennung). Das Dashboard
hat die Variable benutzt, der Bot seine Konfiguration -- dadurch war
jede Seite zweisprachig benannt, obwohl niemand das wollten. Im Browser
nachgemessen am 27.08.2026: Navigation, Ueberschrift und Tab-Titel
zeigten „Universitätsbot".

Ein Name, der an mehreren Stellen frei geschrieben werden kann, laeuft
auseinander. Dieser Test haelt fest:

  * die Bot-Konfiguration normalisiert jede Variante des Namens
  * das Dashboard liest den Namen aus EINER Quelle
  * die Uebersetzung schreibt den NameN nicht um (das war der eigentliche
  Mechanismus, durch den „Universitätsbot" entstand)
  * kein Seitentitel haengt einen Werbesatz an den Namen

Run:  python3 tests/test_marke.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
WURZEL = os.path.dirname(BOT)
DASH = os.path.join(WURZEL, "dashboard")

DER_NAME = "University Bot"

#: Die alte Schreibweise, zusammengebaut -- damit ein kuenftiger
#: Ersetzungslauf den Test nicht selbst zerstoert.
ALT = "UniversityBot" + " Devs"

fehler: list[str] = []


def pruefe(name, ok, hinweis=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        fehler.append(name)


def linie(t):
    print()
    print("=" * 66)
    print(t)
    print("=" * 66)


def lies(*teile):
    with open(os.path.join(*teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(quelltext):
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare."""
    ohne = re.sub(r"(?<!:)//[^\n]*", "", quelltext)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


def test_bot_normalisiert():
    linie("1  Der Bot: eine Variante, ein Name")

    sys.path.insert(0, BOT)
    from utils.config import MARKE, _marke

    pruefe("die Vorgabe ist der eine Name", MARKE == DER_NAME, repr(MARKE))

    # Alles, was nur eine andere Schreibweise desselben Namens ist,
    # muss zurueckgefuehrt werden -- auch die Werte, die in der
    # Vergangenheit tatsaechlich in den Umgebungen standen.
    for variante in (
        "universitybot X",        # alte Vorgabe in utils/config.py
        "Universitätsbot",         # der Wert aus Railway
        "universitaetsbot",
        "University-Bot",
        "UNIVERSITY BOT",
        "Universität-Bot",
        "Oskar-Bot",
        "oskar bot",
        "UB",
        "",                        # leer gesetzt
        None,                      # gar nicht gesetzt
    ):
        pruefe(f"„{variante}“ fuehrt zu „{DER_NAME}“",
               _marke(variante) == DER_NAME, f"bekam {str(_marke(variante))!r}")

    # Ein wirklich anderer Name bleibt stehen: der Test sichert den
    # Namen, nicht die Unmoeglichkeit einer Umbenennung.
    pruefe("ein anderer Name bleibt ein anderer Name",
           _marke("Anderer Bot") == "Anderer Bot", repr(_marke("Anderer Bot")))


def test_dashboard_eine_quelle():
    linie("2  Das Dashboard: eine Quelle fuer den Namen")

    quelle = os.path.join(DASH, "lib", "brand.ts")
    pruefe("die Quelle existiert", os.path.isfile(quelle))
    if not os.path.isfile(quelle):
        return

    inhalt = strip_ts(lies(quelle))
    pruefe('sie enthaelt den Namen als Vorgabe',
           f'export const BRAND = "{DER_NAME}"' in inhalt, "ohne Vorgabe fehlt der Name")
    pruefe("sie normalisiert Varianten",
           "normalisiereMarke" in inhalt and "VARIANTEN" in inhalt,
           "sonst kann eine Variable den Namen erneut verbiegen")

    # Die Varianten-Menge muss durch dieselbe Umrechnung gehen wie die
    # Eingabe. Eine von Hand gepflegte Menge mit Umlauten wird nie
    # getroffen -- die Eingabe ist vorher umgerechnet, der Eintrag nicht.
    pruefe("die Menge wird ueber dieselbe Funktion gebaut",
           re.search(r"new Set\(ROHVARIANTEN\.map\(schluessel\)\)", inhalt)
           is not None,
           "sonst matchen Umlaut-Varianten nie")
    roh = re.search(r"const ROHVARIANTEN = \[(.*?)\];", inhalt, re.S)
    pruefe("die Liste der Varianten ist auffindbar", roh is not None)
    if roh:
        eintraege = re.findall(r'"([^"]+)"', roh.group(1))
        pruefe("die gelebte Variante ist dabei",
               any("universitätsbot" in e.lower() for e in eintraege),
               "genau der Wert stand in Railway")
        pruefe("der Name selbst ist dabei", any(e == DER_NAME for e in eintraege))

    # Kein Baustein darf den Namen weiter selbst lesen.
    gefunde = []
    for ordner, _, dateien in os.walk(os.path.join(DASH, "app")):
        for d in dateien:
            if d.endswith((".tsx", ".ts")):
                gefunde.append(os.path.join(ordner, d))
    for ordner, _, dateien in os.walk(os.path.join(DASH, "components")):
        for d in dateien:
            if d.endswith((".tsx", ".ts")):
                gefunde.append(os.path.join(ordner, d))

    eigenmacht = []
    for pfad in gefunde:
        if pfad.endswith("lib/brand.ts"):
            continue
        t = strip_ts(open(pfad, encoding="utf-8").read())
        # Ein eigener Rueckfallwert neben der env-Variablen haette die
        # Wahl der Normalisierung umgangen.
        if re.search(r"NEXT_PUBLIC_BRAND_NAME\s*\|\|", t):
            eigenmacht.append(os.path.relpath(pfad, DASH))
    pruefe("keine Seite liest die Variable gegen die Quelle",
           not eigenmacht, ", ".join(eigenmacht[:4]))


def test_keine_uebersetzung_des_namens():
    linie("3  Der Name wird nicht uebersetzt")

    pfad = os.path.join(DASH, "lib", "i18n", "dom-translations.ts")
    pruefe("die Tabelle existiert", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    t = lies(pfad)
    # Kein Paar darf den Namen in eine andere Form biegen -- weder
    # „Universitätsbot" noch ein erfundenes „Universitäts-Bot-Konto".
    for wort in ("Universitätsbot", "Universität-Bot", "Universitäts-Bot-Konto"):
        pruefe(f"„{wort}“ steht in keiner Zeile mehr", wort not in t,
               "der Name ist keine Vokabel")

    # Und die Bauanweisung fuer die Tabelle auch nicht -- sonst bringt
    # der naechste Lauf des Generators genau das zurueck.
    eintrag = 0
    for wurzel, _, dateien in os.walk(os.path.join(WURZEL, "tools")):
        for d in dateien:
            if d.endswith(".json"):
                p2 = os.path.join(wurzel, d)
                if "Universitätsbot" in open(p2, encoding="utf-8").read():
                    eintrag += 1
    pruefe("auch in den Bau-Vorlagen nicht", eintrag == 0,
           f"{eintrag} Datei(en) mit Eintrag")


def test_titel_und_footer():
    linie("4  Titel und Fußzeile")

    layout = strip_ts(lies(os.path.join(DASH, "app", "layout.tsx")))
    pruefe("der Seitentitel haengt keine Behauptung an",
           "Ultimate Discord Bot" not in layout,
           "das stand in jedem Browser-Tab und in jedem Suchergebnis")
    pruefe("Unterseiten kriegen ihren Namen vor den Markennamen",
           re.search(r"template:\s*`%s · \$\{brandName\}`", layout) is not None,
           "sonst heiẞt jede Seite gleich und die Suche kann sie nicht trennen")

    footer = strip_ts(lies(os.path.join(DASH, "components", "public-footer.tsx")))
    pruefe("die Fußzeile nennt den Namen, nicht einen Kosenamen",
           "vom University Bot Team" in footer and "vom University-Team" not in footer,
           "zwei Namen fuer dasselbe Team")

    ideen = strip_ts(lies(os.path.join(DASH, "components", "ideas-system.tsx")))
    pruefe("auch die Ideen-Antwort",
           "Antwort vom University Bot Team" in ideen
           and "Antwort vom University-Team" not in ideen)


def test_kopfzeilen():
    linie("5  Die Kopfzeilen im Quelltext")

    # In 190 Dateien stand die Marke ohne Leerzeichen in einer
    # Kommentarzeile. Auf GitHub ist das sichtbar, und wer den Namen
    # sucht, findet zwei.
    #
    # Der gesuchte String wird absichtlich zusammengebaut: ein kuenftiger
    # Ersetzungslauf, der die alte Schreibweise bereinigt, wuerde
    # sonst genau diesen Test umbiegen und ihn zur Aussage ueber die
    # neue Schreibweise machen. Das ist beim ersten Anlauf passiert.
    alt = "UniversityBot" + " Devs"
    neu = "University Bot" + " Devs"

    treffer = 0
    durchsucht = 0
    fuer_neu = 0
    for ordner in ("bot", "dashboard"):
        for wurzel, orden, dateien in os.walk(os.path.join(WURZEL, ordner)):
            orden[:] = [o for o in orden
                        if o not in ("node_modules", ".next", ".git", "__pycache__")]
            for d in dateien:
                if not d.endswith((".py", ".ts", ".tsx")):
                    continue
                durchsucht += 1
                inhalt = open(os.path.join(wurzel, d), encoding="utf-8",
                              errors="ignore").read()
                if alt in inhalt:
                    treffer += 1
                elif neu in inhalt:
                    fuer_neu += 1
    pruefe(f"keine „{alt}“-Schreibweise mehr ({durchsucht} Dateien gesehen)",
           treffer == 0, f"{treffer} Dateien")
    # Der Gegencheck: die neue Schreibweise muss wirklich stehen, sonst
    # ist der Test bloß weil nichts mehr gefunden wird gruen.
    pruefe(f"und „{neu}“ steht auch wirklich", fuer_neu > 100,
           f"nur {fuer_neu} Dateien — erwartet: die meisten von {durchsucht}")


if __name__ == "__main__":
    test_bot_normalisiert()
    test_dashboard_eine_quelle()
    test_keine_uebersetzung_des_namens()
    test_titel_und_footer()
    test_kopfzeilen()

    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print("  -", f)
        sys.exit(1)
    print(f"Der Name ist überall „{DER_NAME}“.")
