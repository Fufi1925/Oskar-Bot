#!/usr/bin/env python3
"""
Der Support-Link ist ueberall derselbe.

Der alte Server stand an 261 Stellen: in
Befehlen, in Karten, in Kopfzeilen, in der README, in den
GitHub-Vorlagen. Ein Link, der an 260 Stellen richtig ist und an
einer falsch, faellt niemandem auf -- ausser dem, der genau dort
klickt.

Deshalb steht hier nur eine Regel: der alte Code kommt nirgends mehr
vor, und der neue an den Stellen, die zaehlen.

Run:  python3 tests/test_support_link.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
REPO = os.path.dirname(BOT)

failures: list[str] = []

# Zusammengesetzt, damit dieser Test sich nicht selbst als
# Fundstelle meldet -- beim ersten Lauf tat er genau das.
ALT = "MG3rYn" + "UZJV"
NEU = "F3TedB" + "AVZT"

# Ordner, die nicht uns gehoeren oder beim Bauen entstehen.
UEBERSPRINGEN = {
    "node_modules", ".next", ".git", "__pycache__", "dist", "build",
    ".venv", "venv", "out", "coverage",
}

ENDUNGEN = (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yml", ".yaml",
            ".json", ".txt", ".toml", ".css", ".html")


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


SELBST = os.path.abspath(__file__)

# Der eingefrorene Commit-Verlauf. Er enthaelt die Beschreibungen
# vergangener Aenderungen -- also auch den Satz "der alte Link stand
# an 261 Stellen" samt der alten Codes. Das ist eine Erzaehlung, kein
# Link: niemand klickt in einer JSON-Datei auf eine Zeichenkette.
#
# Ohne diese Ausnahme meldet der Test genau die Aufraeumarbeit, die
# er selbst ausgeloest hat -- und zwar bei jedem weiteren Commit
# erneut.
AUSGENOMMEN = {os.path.abspath(os.path.join(BOT, "deploy_history.json"))}


def dateien():
    """Jede Quelldatei des Projekts -- ausser dieser hier.

    Diese Datei nennt beide Codes zwangslaeufig: sie prueft ja auf
    sie. Ohne die Ausnahme meldet der Test sich selbst als
    Fundstelle, und zwar fuer immer.
    """
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in UEBERSPRINGEN]
        for name in files:
            if not name.endswith(ENDUNGEN):
                continue
            pfad = os.path.join(root, name)
            voll = os.path.abspath(pfad)
            if voll == SELBST or voll in AUSGENOMMEN:
                continue
            yield pfad


def test_der_alte_ist_weg():
    print("\nDer alte Support-Server kommt nirgends mehr vor")

    treffer = []
    for pfad in dateien():
        try:
            src = open(pfad, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        if ALT in src:
            treffer.append(
                f"{os.path.relpath(pfad, REPO)} ({src.count(ALT)}x)"
            )

    check("keine einzige Fundstelle mehr", not treffer,
          f"-> {treffer[:5]}")


def test_der_neue_ist_da():
    print("\nUnd der neue steht an den Stellen, die zaehlen")

    # Diese Dateien sind die Quelle fuer alles andere. Steht der Link
    # dort falsch, hilft es nichts, dass er anderswo stimmt.
    stellen = [
        (os.path.join(BOT, "utils", "config.py"), "die Bot-Konfiguration"),
        (os.path.join(BOT, "utils", "bot_settings.py"), "die Voreinstellung"),
        (os.path.join(REPO, "dashboard", "lib", "legal.ts"), "das Dashboard"),
    ]
    for pfad, was in stellen:
        if not os.path.isfile(pfad):
            check(f"{was} gibt es", False, pfad)
            continue
        src = open(pfad, encoding="utf-8").read()
        check(f"{was} nennt den neuen Server", NEU in src)

    # Und die Adresse ist vollstaendig, nicht nur der Code.
    config = open(os.path.join(BOT, "utils", "config.py"), encoding="utf-8").read()
    check("als vollstaendige Adresse",
          f"https://discord.gg/{NEU}" in config)


def test_keine_zweite_einladung():
    print("\nEs gibt keine zweite echte Einladung")

    # Beispiel-Platzhalter sind erlaubt -- sie stehen in Hilfetexten
    # ("trag hier deinen Server ein"). Ein zweiter *echter* Code
    # waere dagegen genau der Fall, den dieser Test verhindern soll:
    # zwei Support-Server, von denen einer tot ist.
    platzhalter = {"meinserver", "MEINSERVER", "dein", "abcdef", "abc",
                   "deinserver", "beispiel", "example", "invite", "xxx"}

    gefunden: dict[str, int] = {}
    for pfad in dateien():
        try:
            src = open(pfad, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for code in re.findall(r"discord\.gg/([A-Za-z0-9]+)", src):
            if code in platzhalter or code == NEU:
                continue
            gefunden[code] = gefunden.get(code, 0) + 1

    check("kein zweiter echter Einladungscode", not gefunden, str(gefunden))


def main() -> int:
    test_der_alte_ist_weg()
    test_der_neue_ist_da()
    test_keine_zweite_einladung()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for zeile in failures:
            print(f"   {zeile}")
        return 1
    print("Der Support-Link ist ueberall derselbe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
