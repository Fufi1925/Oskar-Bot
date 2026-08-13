#!/usr/bin/env python3
"""
Ein Stil fuer alle Reiter des Admin-Bereichs.

Das Problem
-----------
Die einundzwanzig Reiter waren in zwei Stilen gebaut, und man sah es
beim Umschalten sofort:

    „Alle Server“, „Dashboard-Nutzer“  ->  Glaskarten: `glass`,
        `border-white/5`, Ecken `rounded-[2rem]`, Flaechen
        `bg-white/[0.03]`
    die uebrigen 19 Reiter              ->  `bg-[#131318]`,
        `border-slate-800`, Ecken `rounded-3xl`

Ausgemessen: 23 `glass`, 101 `border-white/5`, 20 `rounded-[2rem]`
gegen 113 Karten im anderen Stil. Zwei Stile in einem Bereich sind
kein Stil.

Der Nutzer hat den Reiter „Alle Server“ als Vorlage bestimmt. Genommen
wurde davon die **Form** -- Kartenecke, Randfarbe, Flaechen,
Knopfformen. Nicht genommen wurde `backdrop-blur`: hinter jeder dieser
Karten liegt eine einfarbige Flaeche, der Weichzeichner kostet also
Rechenzeit auf jedem Bildlauf fuer ein Ergebnis, das exakt `#131318`
entspricht. Nachgemessen, nicht vermutet.

Was hier festgehalten wird
--------------------------
  1. Kein `glass`, kein `rounded-[2rem]`, kein `border-white/5`,
     kein `bg-white/[0.03]` mehr in den Admin-Reitern.
  2. Karten tragen `bg-[#131318] border border-slate-800`.
  3. Kein Rand-Schimmer im Admin-Bereich -- die Vorlage hat keinen,
     und der Nutzer wollte es ausdruecklich so. Damit muessen auch
     `is-clipped` und `glow-r-*` weg: beide gehoeren zum Schimmer.
  4. `overflow-hidden` bleibt. Es beschneidet den Inhalt und hat mit
     dem Schimmer nichts zu tun -- wer es mitloescht, bekommt eckige
     Listen in runden Karten.
  5. Knoepfe und Reiter schreien nicht in Versalien. Die Vorlage
     benutzt `text-sm font-bold`; Versalien stehen dort nur ueber
     Eingabefeldern und unter Kennzahlen.
  6. Der Schimmer ausserhalb des Admin-Bereichs bleibt unangetastet.

Run:  python3 tests/test_admin_stil.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
PANEL_DIR = os.path.join(DASH, "components", "dashboard")

failures: list[str] = []

# Die Reiter des Admin-Bereichs.
PANELS = [
    "feature-flags-panel", "system-health-panel", "team-panel",
    "premium-admin", "speedrun-admin", "tester-panel",
    "applications-admin", "templates-admin", "owner-access-panel",
    "command-stats-panel", "ping-reactions-panel", "dashboard-users-panel",
    "user-lookup-panel", "servers-panel", "reports-panel", "audit-panel",
    "approvals-panel", "bot-settings-panel", "broadcast-panel",
    "backups-panel", "warnings-panel",
]


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def lies(panel: str) -> str:
    with open(os.path.join(PANEL_DIR, f"{panel}.tsx"), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus -- sonst trifft die Suche die Erklaerung."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


# ══════════════════════════════════════════════════════════════════════


def test_kein_zweiter_stil():
    print("\nDer alte Glas-Stil ist weg")

    # Als ganzes Wort: `glass-blue` waere ein anderer Baustein.
    fuer = {
        "glass": lambda s: len(re.findall(r"\bglass\b", s)),
        "rounded-[2rem]": lambda s: s.count("rounded-[2rem]"),
        "border-white/5": lambda s: len(re.findall(r"border-white/5\b", s)),
        "bg-white/[0.03]": lambda s: s.count("bg-white/[0.03]"),
    }

    for name, zaehle in fuer.items():
        treffer = []
        for panel in PANELS:
            n = zaehle(strip_ts(lies(panel)))
            if n:
                treffer.append(f"{panel}({n})")
        check(f"kein {name}", not treffer, ", ".join(treffer[:4]))


def test_karten_sehen_gleich_aus():
    print("\nAlle Karten tragen dieselbe Form")

    gesamt = 0
    for panel in PANELS:
        src = strip_ts(lies(panel))
        gesamt += len(re.findall(r"bg-\[#131318\]", src))
    check("es gibt ueberhaupt Karten", gesamt >= 50, f"nur {gesamt}")

    # Eine Karte mit Rand muss den Rand aus der Vorlage tragen.
    falsch = []
    for panel in PANELS:
        src = strip_ts(lies(panel))
        for m in re.finditer(r'"([^"]*bg-\[#131318\][^"]*border[^"]*)"', src):
            cls = m.group(1)
            # `border` ohne Farbe ist in Ordnung: die kommt per cn() dazu.
            if "border-" in cls and "border-slate-800" not in cls:
                # Farbige Raender sind Absicht (Warnung, Gefahr).
                if not re.search(r"border-(rose|red|amber|emerald|indigo|primary)", cls):
                    falsch.append((panel, cls[:60]))
    check("jede Karte hat den Rand der Vorlage", not falsch, f"{falsch[:3]}")


def test_kein_schimmer_im_admin():
    print("\nKein Rand-Schimmer -- wie in der Vorlage")

    # Der Schimmer selbst.
    mit = [p for p in PANELS if "border-glow-card" in lies(p)]
    check("border-glow-card ist raus", not mit, ", ".join(mit[:4]))

    # Und die zwei Klassen, die nur fuer ihn da sind. Bleiben sie
    # stehen, sieht man nichts -- aber der naechste, der den Schimmer
    # wieder einschaltet, bekommt einen Ring an der falschen Ecke.
    for klasse in ("is-clipped", "glow-r-2xl", "glow-r-20"):
        mit = [p for p in PANELS if re.search(rf"\b{re.escape(klasse)}\b", lies(p))]
        check(f"{klasse} ist mit raus", not mit, ", ".join(mit[:4]))

    # `overflow-hidden` beschneidet den INHALT und muss bleiben.
    #
    # Eine blosse Gesamtzahl reicht dafuer nicht: bei 17 Vorkommen
    # faellt ein einzelnes verlorenes nicht auf, und genau das ist im
    # Mutationstest durchgerutscht. Geprueft wird deshalb je Datei --
    # eine Karte mit Trennlinien-Liste braucht es an ihrer eigenen
    # Stelle, sonst laufen die Linien aus der runden Ecke heraus.
    LISTEN_KARTEN = {
        "audit-panel": 2,
        "servers-panel": 1,
        "dashboard-users-panel": 1,
        "command-stats-panel": 1,
        "reports-panel": 1,
        "system-health-panel": 1,
    }
    zu_wenig = []
    for panel, mindestens in LISTEN_KARTEN.items():
        n = lies(panel).count("overflow-hidden")
        if n < mindestens:
            zu_wenig.append(f"{panel}({n}<{mindestens})")
    check("jede Listen-Karte beschneidet noch ihren Inhalt",
          not zu_wenig, ", ".join(zu_wenig))

    behalten = sum(lies(p).count("overflow-hidden") for p in PANELS)
    check("overflow-hidden blieb insgesamt stehen", behalten >= 15,
          f"nur {behalten} -- Listen liefen sonst aus der Kartenecke")


def test_schimmer_ausserhalb_bleibt():
    print("\nAusserhalb des Admin-Bereichs bleibt alles")

    treffer = 0
    dateien = 0
    for wurzel, ordner, namen in os.walk(DASH):
        ordner[:] = [o for o in ordner if o not in {"node_modules", ".next", ".git"}]
        for name in namen:
            if not name.endswith(".tsx"):
                continue
            if name[:-4] in PANELS:
                continue
            with open(os.path.join(wurzel, name), encoding="utf-8") as f:
                n = f.read().count("border-glow-card")
            if n:
                treffer += n
                dateien += 1

    # Die Server-Seiten und die Startseite behalten ihren Schimmer.
    check("die uebrige Seite hat ihn noch", treffer >= 110,
          f"nur noch {treffer} Karten")
    check("und zwar breit gestreut", dateien >= 45, f"nur {dateien} Dateien")

    # Eine Gesamtzahl allein merkt nicht, wenn eine einzelne Datei ihn
    # verliert -- im Mutationstest genau so durchgerutscht. Die
    # groessten Traeger werden deshalb einzeln geprueft.
    TRAEGER = {
        "leveling-panel": 10,
        "welcome-form": 5,
        "compose-panel": 5,
        "giveaway-detail": 4,
        "guild-settings-form": 1,
    }
    verloren = []
    for name, mindestens in TRAEGER.items():
        pfad = os.path.join(PANEL_DIR, f"{name}.tsx")
        if not os.path.isfile(pfad):
            verloren.append(f"{name}(fehlt)")
            continue
        with open(pfad, encoding="utf-8") as f:
            n = f.read().count("border-glow-card")
        if n < mindestens:
            verloren.append(f"{name}({n}<{mindestens})")
    check("die grossen Traeger haben ihn einzeln noch",
          not verloren, ", ".join(verloren))


def test_knoepfe_schreien_nicht():
    print("\nKnoepfe und Reiter sind nicht in Versalien")

    # Gefahr-Knoepfe duerfen laut bleiben: bei etwas, das nicht
    # rueckgaengig zu machen ist, ist das richtig.
    gefahr = re.compile(r"rose-|red-|Delete|delete|Leave|Revoke|Purge")

    laut = []
    for panel in PANELS:
        src = strip_ts(lies(panel))
        for m in re.finditer(r"<(?:button|Link)\b.*?(?<!=)>", src, re.S):
            block = m.group(0)
            if "uppercase" in block and not gefahr.search(block):
                laut.append(panel)
                break
    check("kein normaler Knopf in Versalien", not laut, ", ".join(laut[:5]))


def test_kein_roher_schluessel():
    print("\nKein technischer Schluessel als Beschriftung")

    # Ohne `uppercase` faellt auf, was vorher kaschiert war: ein
    # Reiter, der `{s}` rendert, zeigte kleingeschrieben "pending".
    # Gesucht ist der Fall, der im Bild auffiel: ein Knopf rendert die
    # Laufvariable einer Liste aus **technischen Schluesseln**.
    #
    # Nicht jede Laufvariable ist verdaechtig -- `GRUENDE.map((g) =>
    # ... {g})` rendert fertige deutsche Saetze ("Nuke-Versuch"). Der
    # erste Anlauf dieses Tests hat genau das gemeldet: ein Fehlalarm.
    # Entscheidend ist, woher die Liste kommt, nicht wie die Variable
    # heisst. Also: die Liste suchen und in ihre Werte schauen.
    schluessel = re.compile(r"^[a-z][a-z0-9_]*$")

    verdaechtig = []
    for panel in PANELS:
        src = strip_ts(lies(panel))
        # `] as const ).map((s) =>` -- eine flache Liste. Die
        # destrukturierte Form `.map(([s, label]) =>` ist der
        # reparierte Fall und darf nicht mitgefangen werden; sie
        # bindet die Beschriftung ja gerade an einen zweiten Wert.
        for m in re.finditer(
            r"\[([^\[\]]*?)\]\s*as const\s*\)?\s*\.map\(\s*\(\s*(\w+)\s*\)\s*=>",
            src, re.S,
        ):
            werte = re.findall(r'"([^"]+)"', m.group(1))
            variable = m.group(2)
            if not werte or not all(schluessel.match(w) for w in werte):
                continue
            # Wird diese Variable irgendwo als Knopfbeschriftung gezeigt?
            if re.search(rf">\s*\{{{variable}\}}\s*<", src):
                verdaechtig.append(f"{panel}:{werte[:3]}")

    check("Reiter zeigen eine Beschriftung, keinen Schluessel",
          not verdaechtig, ", ".join(verdaechtig[:4]))

    # Der konkrete Fall aus dem gerenderten Bild.
    src = strip_ts(lies("approvals-panel"))
    check("die Freigaben-Reiter sind uebersetzt",
          '"Ausstehend"' in src and '"Freigegeben"' in src and '"Abgelehnt"' in src,
          "sonst steht dort kleingeschrieben »pending«")

    # Die Uebersetzung muss auch ANGEZEIGT werden. Steht sie nur in
    # der Liste, waehrend der Knopf weiter den Schluessel rendert, ist
    # nichts gewonnen -- im Mutationstest genau so durchgerutscht:
    # das Paar blieb stehen, `{label}` wurde zu `{s}`.
    destrukturiert = re.search(r"\.map\(\(\[\s*(\w+)\s*,\s*(\w+)\s*\]\)\s*=>", src)
    if destrukturiert:
        beschriftung = destrukturiert.group(2)
        check("und die Beschriftung wird auch gezeigt",
              re.search(rf">\s*\{{{beschriftung}\}}\s*<", src) is not None,
              f"der Knopf rendert nicht {{{beschriftung}}}")
    else:
        check("und die Beschriftung wird auch gezeigt", False,
              "die Liste ist nicht mehr als Paar aufgebaut")


def test_gemeinsame_bausteine():
    print("\nDer Stil steht an einer Stelle")

    pfad = os.path.join(PANEL_DIR, "admin-ui.tsx")
    check("es gibt admin-ui.tsx", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    src = strip_ts(open(pfad, encoding="utf-8").read())
    for name in ("KARTE", "FELD", "EINGABE", "KNOPF", "PanelKopf",
                 "Kennzahlen", "UnterReiter", "Leer"):
        check(f"{name} ist da", re.search(rf"\b{name}\b", src) is not None)

    # Die Karte darf nicht heimlich wieder den alten Stil tragen.
    check("KARTE benutzt die Vorlagenfarben",
          'bg-[#131318] border border-slate-800' in src)
    check("und keine Glasflaeche",
          "backdrop-blur" not in src and not re.search(r"\bglass\b", src))


def test_warnungen_auf_deutsch():
    print("\nDer Warnungen-Reiter ist auf Deutsch")

    src = strip_ts(lies("warnings-panel"))
    for satz in ("Warn a member", "Add warning", "Select a server first.",
                 "Could not load warnings.", "No warnings in this server.",
                 "Hide history", "members ·"):
        check(f"kein »{satz[:26]}«", satz not in src)
    check("die Zeitangabe ist deutsch",
          "vor ${Math.floor(s / 60)} Min." in src,
          "»5m ago« auf einer deutschen Seite")


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    fehlend = [p for p in PANELS
               if not os.path.isfile(os.path.join(PANEL_DIR, f"{p}.tsx"))]
    check("alle Reiter gefunden", not fehlend, str(fehlend))
    if fehlend:
        return 1

    test_kein_zweiter_stil()
    test_karten_sehen_gleich_aus()
    test_kein_schimmer_im_admin()
    test_schimmer_ausserhalb_bleibt()
    test_knoepfe_schreien_nicht()
    test_kein_roher_schluessel()
    test_gemeinsame_bausteine()
    test_warnungen_auf_deutsch()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Ein Stil, ueberall.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
