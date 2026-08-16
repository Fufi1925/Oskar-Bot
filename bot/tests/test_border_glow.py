#!/usr/bin/env python3
"""
Kein Rand-Schimmer mehr -- nirgends.

Was hier vorher stand
---------------------
Ein Test fuer den BorderGlow: ein Lichtrand, der dem Zeiger um die
Kartenkante folgte, umgesetzt ueber eine Klasse `.border-glow-card` und
einen einzelnen Zeiger-Beobachter fuer die ganze Seite. Er wurde
zunaechst nur im Admin-Bereich entfernt -- 114 Karten in 46 Dateien
durften ihn behalten, das war ausdruecklich so gewollt.

Der Nutzer hat diese Entscheidung umgekehrt: „enfer überall den glow
effet". Also ist der Effekt vollstaendig raus, und dieser Test dreht
sich mit: er sichert jetzt, dass er **weg bleibt**.

Warum das nicht bloss ein Loeschen war
--------------------------------------
`.border-glow-card` setzte zwei Dinge, die nichts mit Optik zu tun
haben:

  * ``position: relative`` -- gemessen: 96 Verwendungen hatten kein
    eigenes `relative`, und bei fuenf davon steckte ein absolut
    positioniertes Kind darin. Ohne Ersatz waeren die verrutscht.
    Dort steht `relative` jetzt ausdruecklich in der Klassenliste.

  * ``isolation: isolate`` -- jede Karte war damit ein eigener
    Stapelkontext. Genau deshalb haengen die Aufklappmenues per
    ``createPortal`` an ``document.body``. Diese Loesung bleibt
    richtig, denn `.prox-row` (transform) und `.admin-glass`
    (backdrop-filter) eroeffnen weiterhin welche -- aber die
    Begruendung in den Kommentaren durfte nicht auf eine Klasse
    verweisen, die es nicht mehr gibt.

Run:  python3 tests/test_border_glow.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

failures: list[str] = []

#: Die Klassen, die zum Schimmer gehoerten.
GLOW_KLASSEN = ("border-glow-card", "is-clipped", "glow-r-2xl", "glow-r-20")

#: Die fuenf Karten mit absolut positioniertem Kind. Sie verliessen
#: sich auf das `position: relative` der Glow-Klasse.
BRAUCHT_RELATIVE = (
    "components/dashboard/anonchat-panel.tsx",
    "components/dashboard/giveaway-detail.tsx",
    "components/dashboard/leveling-panel.tsx",
    "components/dashboard/noprefix-panel.tsx",
)


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    pfad = os.path.join(DASH, *teile)
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def quelldateien() -> list[str]:
    gefunden = []
    for wurzel, ordner, namen in os.walk(DASH):
        ordner[:] = [
            o for o in ordner
            if o not in {"node_modules", ".next", ".render-audit", "dist", ".git"}
        ]
        for name in namen:
            if name.endswith((".tsx", ".ts")):
                gefunden.append(os.path.join(wurzel, name))
    return gefunden


def klassenlisten(src: str) -> list[str]:
    """Jede Zeichenkette, die wie eine Klassenliste aussieht.

    Nur diese pruefen, nicht den ganzen Quelltext: ein Kommentar, der
    erklaert, dass der Schimmer entfernt wurde, MUSS das Wort nennen
    duerfen. Ein Test, der die eigene Begruendung als Fehler meldet,
    zwingt zum Loeschen der Begruendung.
    """
    listen = []
    for m in re.finditer(r'className=\{?\s*(?:cn\()?\s*["`]([^"`]*)["`]', src):
        listen.append(m.group(1))
    # Klassen-Konstanten wie `const KARTE = "..."`.
    for m in re.finditer(r'=\s*["`]([^"`]*(?:rounded|border|bg-)\S[^"`]*)["`]', src):
        listen.append(m.group(1))
    return listen


# ══════════════════════════════════════════════════════════════════════
#  1. Keine Karte traegt den Schimmer mehr
# ══════════════════════════════════════════════════════════════════════


def test_keine_karte_mehr():
    print("\nKeine Karte traegt den Schimmer")

    for klasse in GLOW_KLASSEN:
        treffer = []
        for pfad in quelldateien():
            src = read(os.path.relpath(pfad, DASH))
            for liste in klassenlisten(src):
                if re.search(rf"\b{re.escape(klasse)}\b", liste):
                    treffer.append(os.path.relpath(pfad, DASH))
                    break
        check(f"{klasse} steht in keiner Klassenliste",
              not treffer, ", ".join(sorted(set(treffer))[:4]))


def test_die_maschinerie_ist_weg():
    print("\nDie Maschinerie dahinter ist weg")

    check("die Komponente gibt es nicht mehr",
          not os.path.exists(os.path.join(DASH, "components", "ui", "border-glow.tsx")),
          "sie war der Zeiger-Beobachter fuer den Effekt")

    layout = read("app", "layout.tsx")
    check("das Layout haengt keinen Beobachter mehr ein",
          "BorderGlowProvider" not in layout,
          "ein Zeiger-Listener ohne Karten ist Arbeit fuer nichts")
    check("und importiert das Modul nicht mehr",
          "ui/border-glow" not in layout,
          "ein Import auf eine geloeschte Datei bricht den Build")

    # Nichts darf mehr aus dem Modul importieren.
    importe = []
    for pfad in quelldateien():
        src = read(os.path.relpath(pfad, DASH))
        if "ui/border-glow" in src:
            importe.append(os.path.relpath(pfad, DASH))
    check("nichts importiert es mehr", not importe, ", ".join(importe))


def test_css_ist_weg():
    print("\nDas CSS ist weg")

    css = read("app", "globals.css")
    check("die Datei wurde gefunden", bool(css))

    # Im CSS gibt es keine Prosa-Ausnahme: eine Regel ist eine Regel.
    # Der erklaerende Kommentar darf den Namen nennen, eine Regel nicht.
    ohne_kommentare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for klasse in GLOW_KLASSEN:
        check(f"keine Regel fuer .{klasse}",
              f".{klasse}" not in ohne_kommentare, "")

    check("keine Glow-Variablen mehr",
          "--glow-color" not in ohne_kommentare
          and "--edge-proximity" not in ohne_kommentare, "")

    # Aber eine Notiz muss dastehen, sonst sucht der Naechste den
    # Effekt in einer Datei, in der er nie war.
    check("eine Notiz erklaert, wohin er ist",
          "Kein Rand-Schimmer mehr" in css,
          "sonst raetselt der Naechste, wo der Effekt geblieben ist")


# ══════════════════════════════════════════════════════════════════════
#  2. Was die Klasse nebenbei tat, ist ersetzt
# ══════════════════════════════════════════════════════════════════════


def test_relative_wurde_ersetzt():
    """`position: relative` kam von der Glow-Klasse mit.

    Fuenf Karten haben ein absolut positioniertes Kind und verliessen
    sich darauf. Ohne Ersatz haengt das Kind am naechsten
    positionierten Vorfahren -- irgendwo weiter oben -- und sitzt an
    der falschen Stelle.
    """
    print("\nDas verlorene position:relative ist ersetzt")

    for datei in BRAUCHT_RELATIVE:
        src = read(datei)
        check(f"{os.path.basename(datei)} existiert", bool(src))
        if not src:
            continue

        # Die KARTE muss es tragen, nicht irgendein Element der Datei.
        #
        # Der erste Anlauf suchte `relative` in irgendeiner
        # Klassenliste. Das war zu lose: in leveling-panel stehen
        # neben den 13 Karten noch 3 weitere `relative` an Kindern --
        # nimmt man es allen Karten weg, bleiben die drei stehen und
        # die Pruefung bleibt gruen. Im Mutationstest genau so
        # durchgerutscht.
        #
        # Gesucht ist deshalb die Kombination: eine Karte
        # (`bg-[#131318]`), die `relative` traegt.
        karten = [
            liste for liste in klassenlisten(src)
            if "bg-[#131318]" in liste
        ]
        mit_relative = [
            liste for liste in karten if re.search(r"\brelative\b", liste)
        ]
        check(f"{os.path.basename(datei)}: eine Karte setzt relative selbst",
              bool(mit_relative),
              f"{len(karten)} Karten, keine mit relative -- das absolut "
              "positionierte Kind rutscht weg")


def test_die_stapel_begruendung_stimmt_noch():
    """Die Portale bleiben noetig -- aber aus anderen Gruenden.

    Die Kommentare begruendeten `createPortal` mit `.border-glow-card`.
    Die Klasse gibt es nicht mehr; die Begruendung schon, denn
    `.prox-row` und `.admin-glass` eroeffnen weiterhin Stapelkontexte.
    Ein Kommentar, der eine geloeschte Klasse als Grund nennt, fuehrt
    den naechsten Leser in die Irre -- und laedt dazu ein, das Portal
    als unnoetig zu entfernen.
    """
    print("\nDie Begruendung fuer die Portale ist aktuell")

    css = read("app", "globals.css")
    check(".prox-row eroeffnet weiterhin einen Stapelkontext",
          re.search(r"\.prox-row\s*\{[^}]*transform:", css) is not None,
          "sonst waere der Aufwand mit den Portalen unnoetig geworden")
    check(".admin-glass ebenso",
          re.search(r"\.admin-glass\s*\{[^}]*backdrop-filter:", css) is not None, "")

    # Kein Kommentar darf die geloeschte Klasse noch als GRUND nennen,
    # ohne zu sagen, dass es sie nicht mehr gibt.
    irrefuehrend = []
    for datei in ("components/ui/popover-layer.tsx",
                  "components/dashboard/pickers.tsx",
                  "components/dashboard/emoji-picker.tsx"):
        src = read(datei)
        if not src:
            continue
        if "border-glow-card" not in src:
            continue
        # Nennt er sie, muss im selben Absatz stehen, dass sie weg ist.
        umfeld = src[max(0, src.index("border-glow-card") - 400):
                     src.index("border-glow-card") + 400]
        if not re.search(r"weg|entfernt|frueher|Früher|inzwischen", umfeld):
            irrefuehrend.append(datei)
    check("kein Kommentar nennt sie noch als lebenden Grund",
          not irrefuehrend, ", ".join(irrefuehrend))

    # Und die Portale selbst muessen bleiben.
    layer = read("components", "ui", "popover-layer.tsx")
    check("die Menues haengen weiterhin per Portal am body",
          "createPortal" in layer,
          "die anderen Stapelkontexte bestehen fort")


# ══════════════════════════════════════════════════════════════════════
#  3. Die Karten sehen trotzdem nach Karten aus
# ══════════════════════════════════════════════════════════════════════


def test_karten_haben_noch_eine_kante():
    print("\nDie Karten haben weiterhin eine sichtbare Kante")

    mit_rand = 0
    dateien = 0
    for pfad in quelldateien():
        src = read(os.path.relpath(pfad, DASH))
        n = len(re.findall(r"border-slate-800", src))
        if n:
            mit_rand += n
            dateien += 1

    # Ohne den Schimmer traegt der Rand die ganze Abgrenzung. Faellt
    # der auch noch weg, verschwimmen die Karten mit dem Hintergrund.
    check("der Rand traegt die Abgrenzung", mit_rand >= 300,
          f"nur {mit_rand} Stellen")
    check("und zwar breit gestreut", dateien >= 40, f"nur {dateien} Dateien")


def main() -> int:
    test_keine_karte_mehr()
    test_die_maschinerie_ist_weg()
    test_css_ist_weg()
    test_relative_wurde_ersetzt()
    test_die_stapel_begruendung_stimmt_noch()
    test_karten_haben_noch_eine_kante()

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
