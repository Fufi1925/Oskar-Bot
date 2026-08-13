#!/usr/bin/env python3
"""
Die oberste UI-Ebene: liegen alle Menues vorne, und passen sie aufs Handy?

Gemeldet wurde dreimal, dass die Emoji-Auswahl hinter anderen Karten
liegt, und danach: dasselbe bitte ueberall, auch auf dem Handy und im
Nutzer-Dashboard.

Zwei Dinge sind zu pruefen, und sie sind verschieden:

  1. **Liegt es vorne?** Das ist eine Frage an den Stapelkontext. Die
     Karten tragen `.border-glow-card` mit `isolation: isolate`; ein
     Kind kann seinen Stapelkontext nicht verlassen, weder mit einem
     hoeheren z-index noch mit `position: fixed`. Der einzige Ausweg
     ist ein Ortswechsel im DOM -- `createPortal` an `document.body`.

  2. **Passt es aufs Handy?** Das ist reine Rechnerei. `measure()` aus
     `popover-layer.tsx` bekommt Zahlen und gibt Zahlen zurueck, also
     laesst sie sich hier ohne Browser nachrechnen: ein 360 breites
     Geraet, ein Knopf ganz rechts, ein Knopf ganz unten.

Die Rechnung wird dazu aus dem TypeScript herausgeloest und in Python
nachgebildet -- die Werte stammen aber aus der Datei selbst, damit ein
geaenderter Rand hier auffaellt und nicht stillschweigend durchgeht.

Run:  python3 tests/test_popover_layer.py
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts) -> str:
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Kommentare raus, damit eine Erklaerung nicht als Code zaehlt.

    Ohne das treffen die Suchen die eigenen Erlaeuterungen: in
    `popover-layer.tsx` steht woertlich, was frueher falsch war
    (`absolute z-50`, `max-h-64`). Genau dieser Fehler ist bei der
    Emoji-Auswahl mehrfach hintereinander passiert.
    """
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


LAYER = "components/ui/popover-layer.tsx"

# Jedes Menue der Seite und wo es steht.
MENUS = {
    "components/dashboard/emoji-picker.tsx": "Emoji-Auswahl",
    "components/dashboard/pickers.tsx": "Rollen- und Kanalauswahl",
    "components/dashboard/user-picker.tsx": "Mitgliedersuche",
    "components/ui/select.tsx": "Auswahlfeld",
    "components/language-switcher.tsx": "Sprachumschalter",
    "components/global-search.tsx": "Suche in der Kopfzeile",
    "app/dashboard/layout.tsx": "Glocke und Profilmenue",
}


# ---------------------------------------------------------------- #
# 1. Liegt jedes Menue vorne?
# ---------------------------------------------------------------- #
def test_every_menu_leaves_its_card():
    print("\nJedes Menue verlaesst seine Karte")

    layer = strip_comments(read(LAYER))
    check(
        "der gemeinsame Baustein haengt an document.body",
        re.search(r"createPortal\s*\(", layer) and "document.body" in layer,
        "-- ohne Portal bleibt jedes Menue im Stapelkontext gefangen",
    )

    for rel, name in MENUS.items():
        src = strip_comments(read(rel))
        # Entweder es benutzt den gemeinsamen Baustein, oder es
        # portalt selbst. Der blosse Import zaehlt nicht -- das
        # Element muss im Baum stehen.
        layered = bool(re.search(r"<PopoverLayer[\s>]", src))
        own = bool(re.search(r"createPortal\s*\(", src)) and "document.body" in src
        check(f"{name} liegt vorne", layered or own)


def test_no_menu_is_positioned_inside_a_card():
    """Kein Menue darf mehr mit `absolute` aus seiner Karte wollen.

    Ab `z-20` aufwaerts, denn darunter sind es keine Menues, sondern
    Symbole im Feld -- die Lupe der Suche steht auf `z-10` und soll
    genau dort bleiben.
    """
    print("\nKein Menue haengt mehr an der Karte")

    for rel, name in MENUS.items():
        src = strip_comments(read(rel))
        stuck = [
            int(hit)
            for hit in re.findall(r'"[^"]*\babsolute\b[^"]*?\bz-\[?(\d+)', src)
            if int(hit) >= 20
        ]
        check(f"{name} ohne eingesperrtes absolute", not stuck, f"-> {stuck}")


def test_the_layer_is_positioned_against_the_window():
    """`absolute` statt `fixed` waere hier still falsch.

    Der Mutationstest hat diese Luecke aufgedeckt: `fixed` durch
    `absolute` zu ersetzen blieb gruen, obwohl es das Menue kaputt
    macht.

    Der Unterschied ist nicht der Stapelkontext -- da helfen beide
    nicht -- sondern der Bezugsrahmen der Koordinaten. `place()`
    misst mit `getBoundingClientRect()`, und das liefert
    **Fensterkoordinaten**. Ein `fixed` Element versteht genau die.
    Ein `absolute` Element rechnet dagegen gegen den naechsten
    positionierten Vorfahren; am `document.body` ist das der
    Seitenanfang. Sobald die Seite gescrollt ist, sitzt das Menue
    dann um die Scrollhoehe daneben -- oben auf der Seite faellt es
    nicht auf, weiter unten liegt es voellig falsch.
    """
    print("\nDie Ebene rechnet in Fensterkoordinaten")

    layer = strip_comments(read(LAYER))

    check(
        "das Menue ist fixed",
        re.search(r'"fixed z-\[9999\]', layer) is not None,
        "-- mit absolute wandert es beim Scrollen um die Scrollhoehe weg",
    )
    check(
        "und nicht absolute",
        "absolute" not in layer,
        "-- getBoundingClientRect liefert Fensterkoordinaten",
    )
    check(
        "gemessen wird mit getBoundingClientRect",
        "getBoundingClientRect" in layer,
    )


def test_the_stacking_trap_is_real():
    """Belegen, dass die Karten wirklich Stapelkontexte eroeffnen.

    Faellt `isolation: isolate` eines Tages weg, ist der Aufwand hier
    unnoetig geworden -- dann soll das auffallen und nicht als Kult
    weitergetragen werden.
    """
    print("\nDie Falle ist echt")

    css = read("app", "globals.css")
    check(
        ".border-glow-card setzt isolation: isolate",
        bool(re.search(r"\.border-glow-card\s*\{[^}]*isolation:\s*isolate", css)),
    )
    check(
        ".prox-row setzt transform",
        bool(re.search(r"\.prox-row\s*\{[^}]*transform:", css)),
    )
    check(
        ".admin-glass setzt backdrop-filter",
        bool(re.search(r"\.admin-glass\s*\{[^}]*backdrop-filter:", css)),
    )


# ---------------------------------------------------------------- #
# 2. Passt es aufs Handy?
# ---------------------------------------------------------------- #
def constants() -> tuple[int, int]:
    """Rand und Abstand aus der Quelle lesen statt hier zu raten."""
    src = strip_comments(read(LAYER))
    margin = re.search(r"const MARGIN\s*=\s*(\d+)", src)
    gap = re.search(r"const GAP\s*=\s*(\d+)", src)
    if not margin or not gap:
        return -1, -1
    return int(margin.group(1)), int(gap.group(1))


def measure(anchor, view, width, max_height, min_height, align):
    """Die ECHTE `measure()` aus popover-layer.tsx ausfuehren.

    Hier stand zuerst ein Nachbau in Python. Das war falsch, und der
    Mutationstest hat es aufgedeckt: die Mutation "Hoehe ignoriert den
    freien Platz" blieb gruen, weil die Python-Kopie unveraendert
    weiterrechnete. Geprueft wurde damit der Nachbau, nicht der Code,
    der im Browser laeuft.

    Ein Nachbau kann nur beweisen, dass der Nachbau stimmt. Deshalb
    laedt `measure_bridge.js` jetzt die Funktion selbst.
    """

    bridge = os.path.join(HERE, "measure_bridge.js")
    payload = json.dumps(
        {
            "anchor": anchor,
            "view": view,
            "width": width,
            "maxHeight": max_height,
            "minHeight": min_height,
            "align": align,
        }
    )
    result = subprocess.run(
        ["node", bridge, payload],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"measure() liess sich nicht ausfuehren: {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def test_the_maths_is_read_from_the_source():
    print("\nDie Rechnung stammt aus der Datei")
    margin, gap = constants()
    check("MARGIN und GAP gefunden", margin > 0 and gap > 0, f"-> {margin}, {gap}")

    src = strip_comments(read(LAYER))
    check(
        "gerechnet wird gegen das echte Fenster",
        "window.innerWidth" in src and "window.innerHeight" in src,
        "-- feste Zahlen passen nur auf einem Geraet",
    )


def test_it_fits_a_phone():
    """360 x 640 -- ein gewoehnliches Handy im Hochformat."""
    print("\nAuf einem 360 breiten Handy")
    view = {"width": 360, "height": 640}
    MARGIN, _ = constants()

    # Ein breites Menue (die Emoji-Auswahl will 380) auf einem
    # schmaleren Geraet. Ohne Deckel stuende es ueber den Rand.
    spot = measure(
        anchor={"top": 200, "left": 20, "right": 100, "bottom": 232, "width": 80},
        view=view,
        width=380,
        max_height=420,
        min_height=140,
        align="start",
    )
    check("breiter als das Fenster wird gedeckelt", spot["width"] <= view["width"])
    check("linke Kante im Bild", spot["left"] >= MARGIN)
    check(
        "rechte Kante im Bild",
        spot["left"] + spot["width"] <= view["width"] - MARGIN + 1,
        f"-> endet bei {spot['left'] + spot['width']} von {view['width']}",
    )

    # Ein Knopf ganz am rechten Rand.
    spot = measure(
        anchor={"top": 100, "left": 300, "right": 350, "bottom": 132, "width": 50},
        view=view,
        width=320,
        max_height=420,
        min_height=140,
        align="start",
    )
    check(
        "Knopf am rechten Rand: Menue rutscht nach links",
        spot["left"] + spot["width"] <= view["width"] - MARGIN + 1,
        f"-> endet bei {spot['left'] + spot['width']}",
    )


def test_it_flips_up_when_the_button_is_at_the_bottom():
    """Ein Knopf unten am Bild -- das Menue muss nach oben aufklappen."""
    print("\nKnopf unten am Bildrand")
    view = {"width": 360, "height": 640}

    spot = measure(
        anchor={"top": 590, "left": 20, "right": 120, "bottom": 622, "width": 100},
        view=view,
        width="anchor",
        max_height=420,
        min_height=140,
        align="start",
    )
    check("es klappt nach oben", spot["up"] is True)
    check("obere Kante im Bild", spot["top"] >= 0, f"-> {spot['top']}")
    check(
        "es endet ueber dem Knopf",
        spot["top"] + spot["height"] <= 590,
        f"-> {spot['top'] + spot['height']}",
    )


def test_it_does_not_flip_up_for_nothing():
    """Ein Knopf oben: nach unten ist Platz, also bleibt es unten.

    Ohne diese Gegenprobe wuerde ein `up = true` in jedem Fall den
    Test oben bestehen -- und das Menue klappte immer nach oben, auch
    wenn darunter Platz fuer zehn Zeilen waere.
    """
    print("\nKnopf oben am Bildrand")
    view = {"width": 360, "height": 640}

    spot = measure(
        anchor={"top": 60, "left": 20, "right": 120, "bottom": 92, "width": 100},
        view=view,
        width="anchor",
        max_height=420,
        min_height=140,
        align="start",
    )
    check("es bleibt unten", spot["up"] is False)
    check("es sitzt unter dem Knopf", spot["top"] >= 92, f"-> {spot['top']}")


def test_the_height_is_the_room_that_exists():
    """Die Hoehe darf nicht groesser sein als der freie Platz.

    Hier lag der zweite gemeldete Fehler: die Menues hatten `max-h-64`
    beziehungsweise `max-h-96`, unabhaengig davon, wie viel Platz da
    war. Auf einem liegenden Handy (640 x 360) ist das mehr als der
    halbe Bildschirm.
    """
    print("\nAuf einem liegenden Handy (640 x 360)")
    view = {"width": 640, "height": 360}
    MARGIN, GAP = constants()

    spot = measure(
        anchor={"top": 120, "left": 40, "right": 240, "bottom": 152, "width": 200},
        view=view,
        width="anchor",
        max_height=420,
        min_height=0,
        align="start",
    )
    check(
        "untere Kante im Bild",
        spot["top"] + spot["height"] <= view["height"] - MARGIN + 1,
        f"-> endet bei {spot['top'] + spot['height']} von {view['height']}",
    )
    check(
        "die Hoehe ist kleiner als die Obergrenze",
        spot["height"] < 420,
        f"-> {spot['height']}",
    )


def test_right_aligned_menus_stay_in_frame():
    """Glocke, Profil und Sprachumschalter richten sich rechts aus."""
    print("\nRechtsbuendige Menues")
    view = {"width": 360, "height": 640}
    MARGIN, _ = constants()

    spot = measure(
        anchor={"top": 20, "left": 300, "right": 344, "bottom": 60, "width": 44},
        view=view,
        width=320,
        max_height=420,
        min_height=0,
        align="end",
    )
    check("linke Kante im Bild", spot["left"] >= MARGIN, f"-> {spot['left']}")
    check(
        "rechte Kante im Bild",
        spot["left"] + spot["width"] <= view["width"] - MARGIN + 1,
    )


# ---------------------------------------------------------------- #
# 3. Was der Portal-Umzug sonst noch verlangt
# ---------------------------------------------------------------- #
def test_clicking_inside_does_not_close_it():
    """Der Klick-daneben-Haken muss beide Bereiche kennen.

    Seit das Menue an `document.body` haengt, liegt es nicht mehr im
    Ausloeser. Ein Haken, der nur den Ausloeser prueft, wertet jeden
    Klick auf einen Eintrag als "daneben" und schliesst sofort. Bei
    einer Mehrfachauswahl liesse sich dann nur ein Eintrag pro Oeffnen
    setzen; im Profilmenue reagierte "Abmelden" gar nicht mehr.
    """
    print("\nEin Klick ins Menue schliesst es nicht")

    layer = strip_comments(read(LAYER))
    check(
        "der Baustein prueft Ausloeser UND Menue",
        "inAnchor" in layer and "inPopup" in layer,
    )
    check("Escape schliesst", 'event.key === "Escape"' in layer)

    # Die alten Haken muessen weg sein. Bleibt einer stehen, schliesst
    # er das Menue, bevor der Klick ankommt -- und der neue Haken im
    # Baustein kann daran nichts aendern.
    for rel, name in MENUS.items():
        src = strip_comments(read(rel))
        if "<PopoverLayer" not in src:
            continue
        stale = re.findall(
            r"addEventListener\(\s*[\"']mousedown[\"']", src
        )
        check(f"{name} hat keinen eigenen Aussenklick-Haken mehr", not stale)


def test_it_survives_rendering_on_the_server():
    """`document` gibt es beim Rendern auf dem Server nicht."""
    print("\nRendern auf dem Server")
    layer = strip_comments(read(LAYER))
    check("Riegel gegen fehlendes document", "mounted" in layer)
    check(
        "useLayoutEffect wird auf dem Server umgangen",
        'typeof window === "undefined"' in layer,
        "-- sonst warnt React bei jedem Seitenaufbau",
    )


def test_it_follows_the_page():
    """Ein `fixed` Element bleibt beim Scrollen sonst im Nichts stehen."""
    print("\nBeim Scrollen und Drehen")
    layer = strip_comments(read(LAYER))
    check('am Bildlauf angemeldet', '"scroll"' in layer)
    check("mit capture, fuer innere Bereiche", "update, true" in layer)
    check('an der Groessenaenderung angemeldet', '"resize"' in layer)


def test_the_lists_can_shrink():
    """`min-h-0` fehlt fast nie zufaellig.

    In einem Flex-Kasten behaelt ein Kind seine volle Hoehe, solange
    `min-height: auto` gilt. Die Liste schiebt dann Kopf- und
    Fusszeile aus dem Bild, statt selbst zu scrollen -- auf dem Handy
    faellt das sofort auf, auf einem grossen Bildschirm nie.
    """
    print("\nDie Listen duerfen schrumpfen")

    # Nicht "kommt min-h-0 irgendwo vor" pruefen, sondern JEDE
    # scrollende Liste einzeln.
    #
    # Der Mutationstest hat genau das aufgedeckt: `pickers.tsx` hat
    # zwei Listen (einfache und Mehrfachauswahl). Eine davon auf
    # `max-h-64` zurueckzudrehen blieb gruen, weil die andere das Wort
    # noch enthielt. "Kommt vor" ist eben keine Aussage ueber Wirkung.
    for rel in (
        "components/dashboard/pickers.tsx",
        "components/dashboard/user-picker.tsx",
        "components/ui/select.tsx",
        "components/dashboard/emoji-picker.tsx",
    ):
        src = strip_comments(read(rel))
        name = os.path.basename(rel)

        scrollers = re.findall(r'className="([^"]*overflow-y-auto[^"]*)"', src)
        check(f"{name}: scrollende Liste gefunden", bool(scrollers))

        # Innerhalb eines PopoverLayer sitzt die Liste in einem
        # Flex-Kasten. Dort behaelt sie ohne `min-h-0` ihre volle
        # Hoehe und schiebt Kopf- und Fusszeile aus dem Bild.
        stuck = [c for c in scrollers if "min-h-0" not in c and "flex-1" not in c]
        check(
            f"{name}: jede Liste darf schrumpfen",
            not stuck,
            f"-> ohne min-h-0: {stuck}",
        )

        # Und keine feste Hoehe mehr. Auf einem liegenden Handy ist
        # `max-h-64` (256px) mehr als der halbe Bildschirm.
        fixed = [c for c in scrollers if re.search(r"max-h-\[?\d", c)]
        check(
            f"{name}: keine feste Hoehe",
            not fixed,
            f"-> {fixed}",
        )


def test_the_trap_is_documented():
    """Der naechste Mensch soll nicht wieder am z-index drehen.

    Zwei Anlaeufe sind genau daran gescheitert. Steht der Grund nicht
    in der Datei, ist der dritte Anlauf nur eine Frage der Zeit.
    """
    print("\nDer Grund steht in der Datei")
    raw = read(LAYER)
    check("Stapelkontext erklaert", raw.count("Stapelkontext") >= 3)
    check("die Sackgasse z-index benannt", "z-index" in raw)
    check("die Sackgasse fixed benannt", "position: fixed" in raw or "`fixed`" in raw)


def main() -> int:
    test_every_menu_leaves_its_card()
    test_no_menu_is_positioned_inside_a_card()
    test_the_layer_is_positioned_against_the_window()
    test_the_stacking_trap_is_real()
    test_the_maths_is_read_from_the_source()
    test_it_fits_a_phone()
    test_it_flips_up_when_the_button_is_at_the_bottom()
    test_it_does_not_flip_up_for_nothing()
    test_the_height_is_the_room_that_exists()
    test_right_aligned_menus_stay_in_frame()
    test_clicking_inside_does_not_close_it()
    test_it_survives_rendering_on_the_server()
    test_it_follows_the_page()
    test_the_lists_can_shrink()
    test_the_trap_is_documented()

    print()
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    print("Alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
