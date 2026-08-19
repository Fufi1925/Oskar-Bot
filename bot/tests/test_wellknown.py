#!/usr/bin/env python3
"""
Die Nachweisdatei unter /.well-known/ -- und warum sie eine Ausnahme
in der Wartungsweiche braucht.

── Worum es geht ────────────────────────────────────────────────────

Der Sicherheitsscanner Strix prueft, ob die Domain wirklich uns
gehoert. Dazu ruft er

    https://universtiy-bot.up.railway.app/.well-known/strix-verify.txt

ab und erwartet dort genau eine Zeichenkette. Die Datei liegt in
`dashboard/public/.well-known/` -- Next liefert alles aus `public/`
unveraendert unter dem gleichen Pfad aus.

── Der Fehler, der dabei auffiel ────────────────────────────────────

Die Wartungsweiche in `middleware.ts` schreibt **jeden** Pfad auf
`/wartung` um. Das ist fuer Seiten richtig und ausdruecklich so
gewollt -- aber es traf auch die Nachweisdatei. Nachgemessen am
Produktionsserver (`next build` + standalone) mit `WARTUNG=true`:

    GET /.well-known/strix-verify.txt
    -> HTTP 200
    -> x-middleware-rewrite: /wartung
    -> Content-Type: text/html; charset=utf-8

Der Scanner bekommt also die Wartungsseite als HTML und meldet
„Verification not detected". Besonders unangenehm: es kommt **200**
zurueck, nicht 503 -- an der Antwort sieht man den Fehler nicht,
und im Browser sieht die Seite voellig normal aus.

Nach dem Fix, gleiche Bedingungen:

    -> HTTP 200
    -> Content-Type: text/plain; charset=UTF-8
    -> strix-verify-8d00e75e2c6c4328bd864355a9fd556b

── Was hier geprueft wird ───────────────────────────────────────────

1. Die Datei existiert und enthaelt genau das Token -- ohne
   Anfuehrungszeichen, ohne BOM, ohne zusaetzliche Zeilen.
2. Die Wartungsweiche laesst `/.well-known/` durch, und zwar
   **bevor** sie umschreibt.
3. `.gitignore` schluckt den Ordner nicht. Punkt-Ordner werden gerne
   uebersehen, und ohne die Datei im Repo landet sie nicht im Image.
4. Der Ordner haengt nicht an der Anmeldepflicht.

Run:  python3 tests/test_wellknown.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")

failures: list[str] = []

#: Genau der Wert, den Strix im Bestaetigungsfenster angezeigt hat.
TOKEN = "strix-verify-8d00e75e2c6c4328bd864355a9fd556b"

#: Wo die Datei liegen muss, damit Next sie unter dem Pfad ausliefert.
DATEI = os.path.join(DASH, "public", ".well-known", "strix-verify.txt")


def check(name: str, ok: bool, hinweis: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        zusatz = f" -- {hinweis}" if hinweis else ""
        print(f"  FAIL {name}{zusatz}")
        failures.append(name)


def strip_ts(src: str) -> str:
    """Kommentare raus. Erst Zeilen-, dann Blockkommentare.

    Andersherum frisst der Blockkommentar-Ausdruck ein `//` mit, das
    innerhalb eines Strings steht (`"http://..."`), und reisst dann
    Code mit weg.
    """
    ohne_zeile = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne_zeile, flags=re.S)


# ─────────────────────────────────────────────────────────────────────
# 1. Die Datei selbst
# ─────────────────────────────────────────────────────────────────────

def test_datei() -> None:
    print("\nDie Nachweisdatei")

    check("sie liegt in dashboard/public/.well-known/",
          os.path.isfile(DATEI),
          "ohne public/ liefert Next sie nicht aus")

    if not os.path.isfile(DATEI):
        return

    roh = open(DATEI, "rb").read()

    check("kein BOM am Anfang",
          not roh.startswith(b"\xef\xbb\xbf"),
          "die drei Bytes stehen vor dem Token und verderben den Vergleich")

    text = roh.decode("utf-8")

    check("der Inhalt ist genau das Token",
          text.strip() == TOKEN,
          f"gefunden: {text.strip()[:60]!r}")

    check("keine Anfuehrungszeichen drumherum",
          '"' not in text and "'" not in text,
          "das Token wird woertlich verglichen")

    check("nur eine Zeile",
          len([z for z in text.splitlines() if z.strip()]) == 1,
          "eine zweite Zeile kann der Pruefdienst als Abweichung werten")


# ─────────────────────────────────────────────────────────────────────
# 2. Die Wartungsweiche
# ─────────────────────────────────────────────────────────────────────

def test_wartung_laesst_durch() -> None:
    print("\nWartungsmodus")

    pfad = os.path.join(DASH, "middleware.ts")
    quelle = strip_ts(open(pfad, encoding="utf-8").read())

    # Nur den Rumpf der Weiche ansehen. Sonst greift die Pruefung
    # womoeglich auf einen Treffer irgendwo sonst in der Datei.
    treffer = re.search(
        r"function\s+maintenanceGate\s*\([^)]*\)[^{]*\{(.*?)\n\}",
        quelle,
        re.S,
    )
    check("die Weiche maintenanceGate ist auffindbar", treffer is not None)
    if not treffer:
        return

    rumpf = treffer.group(1)

    check("sie kennt /.well-known/",
          ".well-known" in rumpf,
          "sonst wird die Nachweisdatei auf /wartung umgeschrieben")

    # Auf die *Wirkung* zielen, nicht auf das blosse Vorkommen des
    # Wortes: die Bedingung muss zu einem `return null` fuehren --
    # nur das laesst die Anfrage unveraendert weiterlaufen.
    #
    # Achtung beim Ausdruck: die Bedingung enthaelt mit
    # `startsWith("/.well-known/")` eine geschachtelte Klammer. Ein
    # `[^)]*` bricht daran ab -- deshalb bis zur Zeilenklammer lesen
    # und erst dann auf `return null` pruefen.
    ausnahme = re.search(
        r"if\s*\(.*?\.well-known.*?\)\s*\{\s*return\s+null\s*;?",
        rumpf,
        re.S,
    )
    check("sie laesst den Ordner ausdruecklich durch (return null)",
          ausnahme is not None,
          "eine Erwaehnung ohne return null aendert nichts")

    # Reihenfolge zaehlt: steht das Umschreiben vorher, kommt die
    # Ausnahme nie zum Zug.
    umschreiben = rumpf.find("NextResponse.rewrite")
    stelle = rumpf.find(".well-known")
    check("die Ausnahme steht vor dem Umschreiben",
          stelle != -1 and umschreiben != -1 and stelle < umschreiben,
          "danach wird sie nie erreicht")

    # Und sie darf nicht hinter einer Bedingung haengen, die sie
    # abschaltet.
    check("die Ausnahme ist nicht abgeschaltet",
          not re.search(r"if\s*\(\s*false\s*&&[^)]*\.well-known", rumpf),
          "eine tote Bedingung sieht im Text gleich aus")


# ─────────────────────────────────────────────────────────────────────
# 3. Die Datei muss auch wirklich mitgeliefert werden
# ─────────────────────────────────────────────────────────────────────

def test_wird_ausgeliefert() -> None:
    print("\nWeg ins Image")

    # .gitignore darf den Ordner nicht schlucken. Ist die Datei nicht
    # im Repo, ist sie auch nicht im Build-Kontext -- und dann fehlt
    # sie im Container, obwohl sie lokal daliegt.
    ignore = os.path.join(ROOT, ".gitignore")
    zeilen = [
        z.strip() for z in open(ignore, encoding="utf-8").read().splitlines()
        if z.strip() and not z.strip().startswith("#")
    ]
    gefaehrlich = [z for z in zeilen if z in (".well-known", ".well-known/", "public/", "*.txt")]
    check("keine .gitignore-Regel schluckt den Ordner",
          not gefaehrlich,
          f"stoerende Regeln: {gefaehrlich}")

    # Das Dockerfile muss public/ in den standalone-Server kopieren.
    # Der standalone-Build von Next bringt public/ NICHT von selbst
    # mit -- das ist genau die Zeile, die es nachholt.
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    check("das Dockerfile kopiert public/ in den standalone-Server",
          re.search(r"COPY\s+--from=dashboard-builder\s+\S*dashboard/public\s+\S*standalone/public",
                    dockerfile) is not None,
          "ohne diese Zeile fehlt public/ im Container -- standalone bringt es nicht mit")


# ─────────────────────────────────────────────────────────────────────
# 4. Keine Anmeldepflicht davor
# ─────────────────────────────────────────────────────────────────────

def test_keine_anmeldung() -> None:
    print("\nAnmeldepflicht")

    pfad = os.path.join(DASH, "middleware.ts")
    quelle = strip_ts(open(pfad, encoding="utf-8").read())

    treffer = re.search(
        r"function\s+needsAuth\s*\([^)]*\)[^{]*\{(.*?)\n\}",
        quelle,
        re.S,
    )
    check("needsAuth ist auffindbar", treffer is not None)
    if not treffer:
        return

    rumpf = treffer.group(1)

    # Die Weiche verlangt nur bei /dashboard und /api/bot eine
    # Sitzung. /.well-known/ faellt unter keines von beiden -- das
    # hier haelt fest, dass das so bleibt.
    check("nur /dashboard und /api/bot verlangen eine Sitzung",
          sorted(re.findall(r'startsWith\("(/[^"]+)"\)', rumpf)) == ["/api/bot", "/dashboard"],
          "kommt ein Praefix dazu, das /.well-known/ trifft, bricht die Pruefung")


def main() -> int:
    test_datei()
    test_wartung_laesst_durch()
    test_wird_ausgeliefert()
    test_keine_anmeldung()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for eintrag in failures:
            print(f"  - {eintrag}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
