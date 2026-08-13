#!/usr/bin/env python3
"""
Das Aussehen der oeffentlichen Seiten.

Zwei Dinge werden hier festgehalten:

  1. **Die Farben.** Der alte Marineton (#071527 und Verwandte) ist
     ueberall raus, und Tailwinds blaustichiges Slate ist in der
     Konfiguration neutralisiert. Ohne diesen Test schleicht sich
     beim naechsten Panel wieder ein `bg-[#10233f]` ein und die Seite
     hat zwei Grundtoene.

  2. **Die Navigationsleiste.** Sie steht in EINER Komponente und
     wird von allen oeffentlichen Seiten benutzt. Vorher gab es drei
     Fassungen -- Startseite, Rechtstexte, Dokumentation -- mit
     unterschiedlichem Logo und teils englischer Beschriftung.

Warum statisch geprueft wird: im Testlauf gibt es kein Node und
keinen Browser. Die Pruefungen lesen deshalb die Quelldateien. Was
sich damit nicht pruefen laesst -- ob eine Farbe wirklich ankommt --
wurde beim Bauen mit einem echten Browser nachgemessen.

Run:  python3 tests/test_website_look.py
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
    """Kommentare raus.

    Sonst trifft die Suche die Erklaerung ueber dem Code statt den
    Code -- in diesem Repo mehrfach passiert. Die Begruendung, warum
    Slate neutralisiert wurde, nennt den alten Farbwert ja.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return src


def quelldateien() -> list[str]:
    """Alle tsx/ts/css im Dashboard, ohne Fremdcode und Baureste."""
    out = []
    for root, dirs, files in os.walk(DASH):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".git")]
        for name in files:
            if name.endswith((".tsx", ".ts", ".css")):
                out.append(os.path.join(root, name))
    return out


# Die Marinetoene, die die Seite vorher durchzogen haben.
ALTE_TOENE = (
    "071527",   # Seitenhintergrund
    "10233f",   # Karten
    "0d1b31",   # Eingabefelder
    "0a1628",   # Unterflaechen
    "0b1f3a",   # themeColor
    "101a2c",   # Vorschaukarten
)

# Was stattdessen gilt. Aus den Vorlagen gemessen.
NEUE_TOENE = {
    "0a0a0c": "Seitenhintergrund",
    "131318": "Karten",
    "1e1f22": "Kartenrand",
    "5865f2": "Akzent (Blurple)",
}


def test_keine_alten_farben():
    print("\nDie alten Marinetoene sind ueberall raus")

    treffer: dict[str, list[str]] = {ton: [] for ton in ALTE_TOENE}
    for pfad in quelldateien():
        körper = strip_ts(open(pfad, encoding="utf-8").read()).lower()
        for ton in ALTE_TOENE:
            if f"#{ton}" in körper:
                treffer[ton].append(os.path.relpath(pfad, DASH))

    for ton, dateien in treffer.items():
        check(
            f"#{ton} kommt nicht mehr vor",
            not dateien,
            f"-> {dateien[:3]}",
        )


def test_neue_palette_definiert():
    print("\nDie neue Palette steht in den Wurzelvariablen")

    css = strip_ts(read("app", "globals.css"))

    check("Seitenhintergrund gesetzt", "--background: #0a0a0c;" in css)
    check("Akzentfarbe ist Blurple", "--primary: #5865f2;" in css)
    check("Kartenfarbe benannt", "--card: #131318;" in css)
    check("Kartenrand benannt", "--card-border: #1e1f22;" in css)

    # Der Rollbalken war der letzte Ort mit Marineblau.
    check("der Rollbalken ist neutral",
          "#26262c" in css and "#1e293b" not in css,
          "sonst zieht sich rechts ein blauer Streifen durch")


def test_slate_ist_neutralisiert():
    print("\nTailwinds Slate ist entblaut")

    config = strip_ts(read("tailwind.config.ts"))

    check("die Palette wird ueberschrieben", "slate: {" in config,
          "sonst faerbt Tailwind 536 Raender wieder marineblau")

    # Die entscheidenden Stufen: sie tragen die Raender und den Text.
    for stufe, wert in (("800", "#1e1f22"), ("900", "#131318"),
                        ("950", "#0a0a0c")):
        check(f"slate-{stufe} = {wert}", f'{stufe}: "{wert}"' in config)

    # Und wirklich fast neutral: Rot und Blau duerfen nur wenig
    # auseinanderliegen.
    #
    # Die Grenze ist nachgemessen, nicht geschaetzt. In der Vorlage
    # haben die Navigationslinks #b5bac1 -- 12 Punkte Abstand. Genau
    # dieser Hauch Blau ist gewollt ("schwarz und leicht dunkelblau").
    # Tailwinds eigenes Slate liegt mit #1e293b bei 29 und ist damit
    # klar Marineblau; #334155 sogar bei 34.
    #
    # 14 trennt beides sauber: der gewollte Hauch geht durch, ein
    # echter Marineton nicht.
    GRENZE = 14
    for treffer in re.finditer(r'\d+:\s*"#([0-9a-f]{6})"', config):
        wert = treffer.group(1)
        r, b = int(wert[0:2], 16), int(wert[4:6], 16)
        check(f"#{wert} ist fast neutral", b - r <= GRENZE,
              f"Blau-Rot = {b - r}, erlaubt {GRENZE}")

    # Gegenprobe: die alten Tailwind-Werte muessten an dieser Grenze
    # scheitern. Ohne sie koennte GRENZE auf 99 stehen und der Test
    # bliebe gruen.
    for alt_wert in ("1e293b", "334155", "0f172a"):
        r, b = int(alt_wert[0:2], 16), int(alt_wert[4:6], 16)
        check(f"die Grenze wuerde #{alt_wert} abweisen", b - r > GRENZE,
              f"Blau-Rot = {b - r}")

    check("der Akzent ist Blurple", '"#5865f2"' in config)


def test_eine_navigationsleiste():
    print("\nEine Leiste fuer alle oeffentlichen Seiten")

    pfad = os.path.join(DASH, "components", "site-nav.tsx")
    check("die Komponente gibt es", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    nav = strip_ts(read("components", "site-nav.tsx"))

    # Die Eintraege aus der Vorlage, in ihrer Reihenfolge.
    for beschriftung in ("Befehle", "Über", "Support Server", "Dashboard",
                         "Team beitreten", "Bot hinzufügen"):
        check(f"»{beschriftung}« steht in der Leiste", beschriftung in nav)

    # Es muss die Beschriftung des Aufklappmenues sein, nicht
    # irgendein Vorkommen des Wortes: im Handy-Menue steht es ein
    # zweites Mal, und die blosse Wortsuche blieb gruen, als das
    # Dropdown umbenannt war.
    check("»Team beitreten« ist ein Aufklappmenue",
          'label="Team beitreten"' in nav)
    check("und gruen hervorgehoben",
          'tone="emerald"' in nav and "text-emerald-400" in nav,
          "in der Vorlage ist genau dieser eine Punkt gruen")
    check("die Hoehe stimmt", "h-[76px]" in nav)
    check("die Leiste bleibt oben stehen", "sticky top-0" in nav)
    check("mit Rand darunter", "border-b border-slate-800" in nav)
    # Der Sprachschalter muss aus der echten Komponente kommen.
    # Ein umgebogener Import (LanguageSwitcherX as LanguageSwitcher)
    # liess die blosse Wortsuche gruen -- gemessen im Mutationstest.
    check("es gibt einen Sprachschalter",
          re.search(
              r'import\s*\{\s*LanguageSwitcher\s*\}\s*from\s*'
              r'"@/components/language-switcher"', nav) is not None)
    check("und er wird auch gerendert", "<LanguageSwitcher />" in nav)

    # Zwei Aufklappmenues, wie in der Vorlage -- und beide Listen
    # muessen wirklich an ein Dropdown gehen. Nur nach den Namen zu
    # suchen blieb gruen, als die Liste in BEFEHLE_AUS umbenannt war.
    check("Befehle klappt auf",
          "<Dropdown label=\"Befehle\" items={BEFEHLE} />" in nav)
    check("Über klappt auf",
          "<Dropdown label=\"Über\" items={UEBER} />" in nav)
    check("beide Listen sind gefuellt",
          "const BEFEHLE: Eintrag[]" in nav and "const UEBER: Eintrag[]" in nav)

    # »Bot hinzufuegen« muss in der Hauptleiste stehen, nicht nur im
    # eingeklappten Handy-Menue -- dort steht derselbe Text ein
    # zweites Mal, und genau daran ist die Pruefung vorbeigelaufen.
    check("»Bot hinzufügen« steht zweimal: Leiste und Handy-Menü",
          nav.count("Bot hinzufügen") >= 2,
          f"nur {nav.count('Bot hinzufügen')}x gefunden")
    check("und zeigt auf die Einladung",
          "href={INVITE_URL}" in nav)

    # Und der Kontoknopf muss beide Faelle kennen.
    check("angemeldet: Name und Bild", "session?.user" in nav)
    check("abgemeldet: Anmelden-Knopf", "Anmelden" in nav and "signIn" in nav)


def test_alle_seiten_nutzen_sie():
    print("\nJede oeffentliche Seite benutzt genau diese Leiste")

    for datei, name in (
        ("app/page.tsx", "Startseite"),
        ("components/legal-page.tsx", "Rechtstexte, Team, Status"),
        ("app/docs/page.tsx", "Dokumentation"),
    ):
        körper = strip_ts(read(*datei.split("/")))
        check(f"{name} bindet SiteNav ein", "<SiteNav />" in körper)
        # Und hat keine zweite, eigene Leiste mehr.
        check(
            f"{name} hat keine eigene Leiste mehr",
            '<nav className="fixed top-0' not in körper,
            "zwei Fassungen laufen auseinander",
        )


def test_startseite_hat_die_abschnitte():
    print("\nDie Startseite ist vollstaendig")

    seite = strip_ts(read("app", "page.tsx"))

    for text, was in (
        ("auf das nächste Level gebracht", "Hero-Überschrift"),
        ("Bot hinzufügen", "Hauptknopf"),
        ("Funktionen erkunden", "zweiter Knopf"),
        ("Alles was du brauchst", "Funktionen-Abschnitt"),
        ("In Zahlen", "Zahlen"),
        ("Community-Stimmen", "Stimmen"),
        ("Häufig gestellte Fragen", "FAQ"),
        ("Alle Rechte vorbehalten", "Fußzeile"),
    ):
        check(f"{was} vorhanden", text in seite)

    # Der alte Text ist weg. Er war zur Haelfte englisch und sprach
    # von einem "Neural Core", den es nie gab.
    for wort in ("Neural", "Evolution", "hyper-performance", "Moderiert."):
        check(f"»{wort}« steht nicht mehr drin", wort not in seite)

    # Keine erfundenen Zahlen im Quelltext: sie kommen aus dem Bot.
    # Die Adresse hat sich geaendert -- /bot/stats lieferte nur die
    # Serverzahl, /bot/numbers zaehlt auch Module und Befehle.
    check("die Zahlen werden geladen, nicht behauptet",
          "/api/bot/bot/numbers" in seite,
          "eine feste Zahl pflegt niemand nach")


def test_faq_ist_bedienbar():
    print("\nDas FAQ klappt wirklich auf")

    seite = strip_ts(read("app", "page.tsx"))

    check("es gibt einen Zustand je Zeile", "useState(false)" in seite)
    check("der Knopf schaltet um", "setOffen((o) => !o)" in seite)
    check("die Antwort haengt am Zustand", "{offen && (" in seite)
    check("und das Pfeilchen dreht sich", "rotate-180" in seite)
    check("mit aria-expanded fuer Screenreader", "aria-expanded={offen}" in seite)


def test_kein_layoutbruch_auf_dem_telefon():
    print("\nSchmale Bildschirme")

    nav = strip_ts(read("components", "site-nav.tsx"))
    seite = strip_ts(read("app", "page.tsx"))
    legal = strip_ts(read("components", "legal-page.tsx"))
    docs = strip_ts(read("app", "docs", "page.tsx"))

    check("die Leiste hat ein Menue fuer schmale Geraete",
          'aria-label="Menü"' in nav)
    check("die Marke darf schrumpfen",
          "max-w-[46vw]" in nav,
          "sonst schiebt sie die Knoepfe aus dem Bild -- gemessen: 19px")
    check("der Anmelden-Text weicht auf dem Telefon",
          'className="hidden sm:inline"' in nav)

    # Der dekorative Schein ragte ueber den Rand hinaus.
    check("der Hero schneidet den Schein ab", "overflow-x-clip" in seite)
    check("die Rechtstexte auch", "overflow-x-clip" in legal)

    # Ein flex-1 ohne min-w-0 schrumpft nie unter seinen Inhalt.
    check("die Doku-Spalte darf schrumpfen",
          "flex-1 min-w-0" in docs,
          "ohne min-w-0 ragte der Text 191px heraus -- gemessen")

    # Die Innenabstaende muessen mitwachsen -- und zwar in JEDEM
    # Abschnitt. Vorher genuegte ein einziges Vorkommen irgendwo,
    # sodass ein Abschnitt ohne Abstand unbemerkt blieb.
    abschnitte = re.findall(r'<(?:section|header|footer)\b[^>]*className="([^"]*)"',
                            seite)
    check("es gibt genug Abschnitte", len(abschnitte) >= 6, str(len(abschnitte)))
    ohne = [a[:45] for a in abschnitte
            if "px-" in a and "lg:px-12 xl:px-20" not in a]
    check("jeder Abschnitt skaliert seinen Abstand", not ohne, str(ohne))
    check("auch der Hero",
          "px-6 lg:px-12 xl:px-20 py-20 lg:py-28" in seite,
          "sonst klebt die Überschrift am Rand")


def test_h4_5_gibt_es_nicht():
    print("\nKeine erfundenen Tailwind-Stufen")

    # h-4.5 existiert in Tailwind nicht -- nur .5-Schritte bei 0.5,
    # 1.5, 2.5 und 3.5. Die Klasse faellt still weg, das Element hat
    # dann gar keine Hoehe.
    for pfad in quelldateien():
        if not pfad.endswith(".tsx"):
            continue
        körper = open(pfad, encoding="utf-8").read()
        for schlecht in ("h-4.5", "w-4.5", "h-5.5", "w-5.5"):
            if schlecht in körper:
                check(f"{os.path.relpath(pfad, DASH)}: kein {schlecht}",
                      False, "diese Stufe gibt es nicht")
                return
    check("keine Datei benutzt eine erfundene Stufe", True)


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_keine_alten_farben()
    test_neue_palette_definiert()
    test_slate_ist_neutralisiert()
    test_eine_navigationsleiste()
    test_alle_seiten_nutzen_sie()
    test_startseite_hat_die_abschnitte()
    test_faq_ist_bedienbar()
    test_kein_layoutbruch_auf_dem_telefon()
    test_h4_5_gibt_es_nicht()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for zeile in failures:
            print(f"   {zeile}")
        return 1
    print("Alle Aussehen-Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
