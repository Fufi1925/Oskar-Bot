#!/usr/bin/env python3
"""
Das Liniendiagramm und die neue Optik des Admin-Bereichs.

Zum Diagramm gibt es drei Regeln, und alle drei stehen hier, weil
genau sie beim ersten Bauen falsch waren -- im gerenderten Bild
nachgemessen, nicht vermutet:

  1. **Eine flache Reihe darf keine fuenf gleichen Achsenwerte
     zeigen.** Bei "2, 2, 2, 2, 2" lagen die Gitterwerte bei 1.9 bis
     2.1 und wurden ohne Nachkommastellen alle zu "2".
  2. **Eine Luecke muss eine Luecke bleiben.** Der Pfad lief quer
     darueber hinweg, weil nach einem fehlenden Wert kein neues `M`
     kam.
  3. **Die letzte Beschriftung darf nicht abgeschnitten werden.**
     Mittig zentriert ragte "11. Aug" ueber den Rand und wurde zu
     "11. Au".

Dazu: der Admin-Bereich ist neu und soll ruhig bleiben.

Run:  python3 tests/test_line_chart.py
"""

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


def strip_ts(src: str) -> str:
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


# ══════════════════════════════════════════════════════════════════════


def test_der_baustein_existiert():
    print("\nDas Diagramm gibt es")

    pfad = os.path.join(DASH, "components", "ui", "line-chart.tsx")
    check("die Datei", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    src = strip_ts(read("components", "ui", "line-chart.tsx"))
    check("es wird ausgefuehrt", "export function LineChart" in src)
    check("als SVG, ohne neue Abhaengigkeit", "<svg" in src)

    # Keine Diagramm-Bibliothek im Bundle.
    pkg = read("package.json")
    for schwer in ("recharts", "chart.js", "apexcharts", "victory", "nivo"):
        check(f"{schwer} wurde nicht dazugeholt", schwer not in pkg,
              "100 kB fuer eine Linie mit Gitter")


def test_flache_reihe():
    print("\nEine flache Reihe sieht flach aus")

    src = strip_ts(read("components", "ui", "line-chart.tsx"))

    # Die Achse darf nicht stur min..max sein.
    check("es gibt eine eigene Achsenrechnung", "function achse(" in src)
    check("eine Spanne von null bekommt einen Rand",
          "if (spanne === 0)" in src,
          "sonst liegt die Linie auf der Kante")
    check("und sonst ebenfalls", "spanne * 0.15" in src)
    check("die Achse geht nicht ins Negative, wenn nichts negativ ist",
          "min >= 0 ? Math.max(0, min - rand)" in src)

    # Der Fehler aus dem ersten Bild: fuenfmal "2".
    check("die Nachkommastellen richten sich nach der Spanne",
          "function stellenFuer(" in src,
          "sonst steht bei einer flachen Reihe fuenfmal dieselbe Zahl")
    # Seit dem Achsen-Fix laeuft die Beschriftung ueber
    # `achsenBeschriftung()`, das `achsStellen` weiterreicht und ab
    # 10.000 zusaetzlich genug Stellen erzwingt, damit nicht zwei
    # Gitterwerte dieselbe Zahl tragen.
    check("und werden auch benutzt",
          "achsenBeschriftung(spanne, achsStellen)" in src
          and "{yText(wert)}" in src,
          "sonst rechnet stellenFuer() ins Leere")


def test_luecke_bleibt_luecke():
    print("\nEine Luecke ist keine Null")

    src = strip_ts(read("components", "ui", "line-chart.tsx"))

    check("ein fehlender Wert ist erlaubt", "wert: number | null" in src)
    # Nicht nur, dass die Woerter vorkommen: die Zuweisung muss im
    # null-Zweig stehen. Faellt sie dort weg, bleibt `luecke` auf
    # false und die Linie laeuft durch -- die Deklaration oben und
    # das Fragezeichen weiter unten stehen trotzdem noch da, und der
    # Test blieb gruen. Im Mutationstest aufgefallen.
    zweig = ""
    if "if (p.wert === null) {" in src:
        zweig = src.split("if (p.wert === null) {", 1)[1]
        zweig = zweig.split("}", 1)[0]
    check("und unterbricht den Pfad",
          "luecke = true" in zweig and 'luecke ? "M" : "L"' in src,
          "sonst zieht die Linie quer darueber -- im Bild nachgemessen")
    check("die Marke startet unterbrochen",
          "let luecke = true;" in src,
          "sonst faengt der erste Punkt mit L an und der Pfad ist leer")
    check("die Flaeche entfaellt bei Luecken",
          "daten.some((p) => p.wert === null)) return" in src,
          "eine Flaeche unter einer unterbrochenen Linie ist geraten")


def test_beschriftung_passt_ins_bild():
    print("\nDie Beschriftung wird nicht abgeschnitten")

    src = strip_ts(read("components", "ui", "line-chart.tsx"))

    check("erste und letzte werden an der Kante ausgerichtet",
          'i === 0 ? "start" : i === daten.length - 1 ? "end" : "middle"' in src,
          "mittig zentriert ragte »11. Aug« ueber den Rand")
    # Ausgeduennt wird jetzt in `sichtbareMarken()` -- und dort faellt
    # zusaetzlich die vorletzte Marke weg, wenn sie der letzten zu nahe
    # kommt. Im Bild klebten sonst "12. Aug." und "13. Aug." aneinander.
    check("bei vielen Werten wird ausgeduennt",
          "Math.ceil(anzahl / 8)" in src and "marken.has(i)" in src,
          "90 Tage nebeneinander ueberlappen")


def test_leerer_fall():
    print("\nOhne Daten kein leeres Gitter")

    src = strip_ts(read("components", "ui", "line-chart.tsx"))
    check("es wird abgefangen", "if (daten.length === 0)" in src)
    check("und gesagt, was los ist", "Noch keine Daten" in src)


def test_wird_benutzt():
    print("\nEs wird auch eingesetzt")

    stats = strip_ts(read("components", "dashboard", "command-stats-panel.tsx"))
    check("die Befehls-Statistik nutzt es", "<LineChart" in stats)
    check("und importiert es",
          'from "@/components/ui/line-chart"' in stats)
    check("die alten Balken sind weg",
          "maxDaily" not in stats,
          "Balken zeigen die Hoehe, eine Linie den Verlauf")


def test_admin_ist_ruhig():
    print("\nDer Admin-Bereich ist ruhig")

    src = strip_ts(read("components", "dashboard", "admin-content.tsx"))

    # Der alte Look: Glaskarten, Farbverlauf, Naeherungseffekt.
    for laut, was in (
        ("admin-glass", "Glaskarten"),
        ("admin-hero", "Farbverlauf im Kopf"),
        ("useProximity", "Naeherungseffekt an den Reitern"),
        ("prox-tab", "verschiebende Knoepfe"),
        ("<Reveal", "Einblend-Animation je Karte"),
        ("shadow-primary/25", "Schlagschatten unter den Reitern"),
        ("group-hover:scale-110", "wachsende Symbole"),
        ("rounded-[28px]", "28px-Rundung"),
        ("rounded-[2rem]", "2rem-Rundung"),
        ("font-outfit", "zweite Schriftart"),
    ):
        check(f"kein {was}", laut not in src, laut)

    # Und das, was jetzt gilt.
    check("der Kopf ist eine Zeile", "Admin-Bereich" in src)
    check("der Knopf sagt, was er tut",
          "Aktualisieren" in src and "Real-time Mode" not in src,
          "»Real-time Mode« war ein Versprechen, kein Zustand")
    # Die Zahlen standen zwischenzeitlich als eine einzige Textzeile
    # da. Das war zu wenig: vier Angaben dicht nebeneinander lesen
    # sich als ein Satz. Jetzt vier ruhige Felder -- ruhig heisst hier
    # eigene Flaeche, aber kein Leuchten und kein Wachsen.
    check("die Zahlen stehen in vier Feldern",
          "grid grid-cols-2 gap-3 lg:grid-cols-4" in src,
          "eine einzige Zeile las sich als ein Satz statt als vier Angaben")
    check("die Reiter heben sich ab, ohne zu leuchten",
          "border-indigo-500/30 bg-indigo-500/10" in src
          and "shadow-primary/25" not in src)

    # Eine gemeinsame Beschriftung statt Versalien ueberall.
    check("es gibt eine gemeinsame Feldbeschriftung", "const LBL =" in src)
    check("die Karten sehen aus wie ueberall sonst",
          src.count("border border-slate-800 bg-[#131318]") >= 3)


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_der_baustein_existiert()
    test_flache_reihe()
    test_luecke_bleibt_luecke()
    test_beschriftung_passt_ins_bild()
    test_leerer_fall()
    test_wird_benutzt()
    test_admin_ist_ruhig()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for zeile in failures:
            print(f"   {zeile}")
        return 1
    print("Alle Diagramm- und Admin-Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
