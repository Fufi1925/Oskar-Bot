#!/usr/bin/env python3
"""
Die Server-Auswahl im Dashboard (/dashboard/guilds).

Was hier schiefging
-------------------
Fuenf Maengel, alle nachgemessen und nicht vermutet:

  1. **Die Mitgliederzahl wurde weggeworfen.** `page.tsx` fragt Discord
     mit ``with_counts=true`` und setzt ``memberCount`` fuer JEDEN
     Server -- auch fuer die ohne Bot. Die Karte zeigte sie trotzdem
     nicht, sondern behauptete: „Mitgliederzahl sichtbar, sobald der
     Bot auf dem Server ist." Nachgestellt in ``repro/bug_guilds.mjs``:
     Server ohne Bot, ``memberCount = 847``, angezeigt wurde der Satz.

  2. **Sortieren nach einer Zahl, die nicht dasteht.** Der Knopf
     „Mitglieder" ordnete auch die Karten ohne Bot -- fuer den
     Betrachter war die Reihenfolge willkuerlich.

  3. **„Mitglieder gesamt" zaehlte nur die verbundenen.**

  4. **Versalien an fuenf Stellen** (MITGLIEDER, VERBUNDEN, OWNER).

  5. **„Owner" auf einer deutschen Seite**, obwohl das Woerterbuch des
     Dashboards „Besitzer" kennt und sechsmal benutzt.

Die Regel, die den Aufbau erklaert
----------------------------------
**Eine gezaehlte und eine geschaetzte Zahl sind nicht dasselbe.** Der
Bot kennt die echte Mitgliederzahl seiner Server; fuer alle anderen
liefert Discord nur ``approximate_member_count`` -- das steht so im
Feldnamen. Beide gleich zu drucken waere eine Behauptung, die eine
davon nicht deckt. Die geschaetzte traegt deshalb ein „ca.".

Run:  python3 tests/test_guilds_seite.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")

failures: list[str] = []

GRID = os.path.join(DASH, "components", "dashboard", "guild-grid.tsx")
SEITE = os.path.join(DASH, "app", "dashboard", "guilds", "page.tsx")


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(pfad: str) -> str:
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus -- sonst trifft die Suche die Erklaerung.

    Reihenfolge: ERST die Zeilenkommentare, DANN die Bloecke. Ein ``/*``
    in einem ``//``-Kommentar eroeffnet sonst einen Schein-Block, der
    den halben Quelltext verschluckt.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def entkette(src: str) -> str:
    """`"a" + "b"` zu `"ab"` -- sonst scheitert jede Prosa-Suche."""
    return re.sub(r'"\s*\+\s*"', "", src)


# ══════════════════════════════════════════════════════════════════════
#  1. Die verschwiegene Mitgliederzahl
# ══════════════════════════════════════════════════════════════════════


def test_zahl_wird_nicht_mehr_verschwiegen():
    print("\nDie Mitgliederzahl steht auch ohne Bot da")

    grid = strip_ts(read(GRID))
    text = entkette(read(GRID))
    seite = strip_ts(read(SEITE))

    # Erst nachweisen, dass die Zahl ueberhaupt ankommt -- sonst
    # prueft der Rest eine Angabe, die es gar nicht gibt.
    check("die Seite fragt Discord nach den Zahlen",
          "with_counts=true" in seite,
          "ohne das fehlt approximate_member_count komplett")
    check("und uebernimmt sie auch fuer Server ohne Bot",
          "approximate_member_count" in seite
          and re.search(r"fromDiscord\s*\n?\s*:\s*null", seite) is not None,
          "sonst gibt es fuer die gar keine Zahl")

    # Der Satz, der die vorhandene Zahl verschwiegen hat.
    check("der alte Ausredensatz ist weg",
          "Mitgliederzahl sichtbar, sobald der Bot" not in text,
          "die Zahl war da und wurde als »kommt spaeter« ausgegeben")

    # Beide Kartenarten zeigen die Zahl.
    treffer = re.findall(r"<Mitglieder\s+anzahl=\{guild\.memberCount\}", grid)
    check("beide Kartenarten zeigen die Zahl", len(treffer) == 2,
          f"{len(treffer)} statt 2")

    # Und sie unterscheiden gezaehlt von geschaetzt.
    check("die Karte mit Bot nennt sie genau",
          re.search(r"<Mitglieder anzahl=\{guild\.memberCount\} genau />", grid)
          is not None)
    check("die Karte ohne Bot nennt sie geschaetzt",
          re.search(r"<Mitglieder\s+anzahl=\{guild\.memberCount\}\s+genau=\{false\}",
                    grid) is not None,
          "approximate_member_count ist laut Feldname eine Naeherung")

    # Das „ca." muss wirklich von `genau` abhaengen -- ein fest
    # geschriebenes waere bei der gezaehlten Zahl schlicht falsch.
    check("das »ca.« haengt an der Unterscheidung",
          re.search(r'genau \? "" : "ca\. "', grid) is not None,
          "sonst steht »ca.« auch an der gezaehlten Zahl")


# ══════════════════════════════════════════════════════════════════════
#  2. Die Kennzahlen sagen, worauf sie sich beziehen
# ══════════════════════════════════════════════════════════════════════


def test_kennzahlen_sind_ehrlich():
    print("\nDie Kennzahlen sagen, was sie zaehlen")

    grid = strip_ts(read(GRID))
    text = entkette(grid)

    # Im GESTRIPPTEN Quelltext suchen, nicht im Rohtext: die
    # Erklaerung oben in der Datei zitiert den alten Namen, um zu
    # sagen, was daran falsch war. Ein Suchmuster, das die eigene
    # Begruendung trifft, meldet einen Fehler, der behoben ist.
    check("»Mitglieder gesamt« heisst nicht mehr so",
          "Mitglieder gesamt" not in text,
          "die Zahl zaehlte nur die verbundenen Server")
    check("sondern nennt ihren Bezug",
          "auf Servern mit Bot" in text, "")

    # Die beiden Summen bleiben getrennt. Sie zu addieren waere eine
    # Zahl, fuer die es keine Quelle gibt: die eine ist gezaehlt, die
    # andere geschaetzt.
    check("verbundene und andere werden getrennt gezaehlt",
          "mitgliederVerbunden" in grid and "mitgliederOhneBot" in grid, "")
    check("die verbundene Summe zaehlt nur connected",
          re.search(r"mitgliederVerbunden = connected\.reduce", grid) is not None,
          "")
    check("die andere Summe zaehlt nur missing",
          re.search(r"mitgliederOhneBot = missing\.reduce", grid) is not None, "")
    check("und die geschaetzte Summe ist als solche gekennzeichnet",
          re.search(r'`ca\. \$\{zahl\(mitgliederOhneBot\)\}', grid) is not None,
          "sonst steht eine Schaetzung so fest da wie eine Zaehlung")


# ══════════════════════════════════════════════════════════════════════
#  3. Deutsch und ruhig
# ══════════════════════════════════════════════════════════════════════


def test_deutsch_und_ruhig():
    print("\nDeutsche Beschriftungen, keine Versalien")

    grid = strip_ts(read(GRID))
    text = entkette(read(GRID))

    # „Owner" auf einer deutschen Seite. Das Woerterbuch des Dashboards
    # kennt „Besitzer" und benutzt es an sechs anderen Stellen.
    check("»Owner« ist uebersetzt",
          not re.search(r">\s*Owner\s*<", grid)
          and '"Du bist Owner"' not in grid,
          "das Dashboard sagt sonst »Besitzer«")
    check("und heisst »Besitzer«", "Besitzer" in text, "")

    # Versalien: vorher fuenf Stellen. Sie gehoeren ueber
    # Eingabefelder, nicht auf jede zweite Beschriftung -- dieselbe
    # Regel wie in test_admin_stil.py.
    check("keine Versalien mehr", "uppercase" not in grid,
          f"{grid.count('uppercase')} Stellen uebrig")

    # Deutsche Zahlen.
    check("Zahlen werden deutsch formatiert",
          'toLocaleString("de-DE")' in grid,
          "sonst steht dort 12,480 statt 12.480")
    check("und die Sortierung nach Namen auch",
          'localeCompare(b.name, "de")' in grid,
          "ohne Gebietsschema landen Umlaute hinter Z")


# ══════════════════════════════════════════════════════════════════════
#  4. Die Karte ist anklickbar
# ══════════════════════════════════════════════════════════════════════


def test_karte_ist_der_knopf():
    print("\nDie ganze Karte fuehrt zum Server")

    grid = strip_ts(read(GRID))

    # Vorher war nur ein Knopf am Fuss verlinkt: ein Klick auf den
    # Servernamen tat nichts, obwohl die Karte anklickbar aussah.
    treffer = re.search(
        r"<Link\s+key=\{guild\.id\}\s+href=\{`/dashboard/guild/\$\{guild\.id\}`\}",
        grid,
    )
    check("die Karte selbst ist der Link", treffer is not None,
          "sonst tut ein Klick auf den Namen nichts")

    check("die Beschriftung bleibt",
          "Server verwalten" in grid, "")

    # Der Einladungs-Link muss ein echtes Ziel haben.
    check("»Bot hinzufuegen« zeigt auf die Einladung",
          re.search(r"href=\{inviteUrl\}", grid) is not None, "")
    check("und oeffnet sich sicher",
          'rel="noopener noreferrer"' in grid,
          "target=_blank ohne noopener gibt der Zielseite Zugriff")


# ══════════════════════════════════════════════════════════════════════
#  5. Der Stil passt zum uebrigen Dashboard
# ══════════════════════════════════════════════════════════════════════


def test_stil():
    print("\nDer Stil passt zum uebrigen Dashboard")

    grid = strip_ts(read(GRID))
    seite = strip_ts(read(SEITE))

    check("die Karten tragen den Ton des Dashboards",
          "bg-[#131318]" in grid and "border-slate-800" in grid, "")

    # Die alten Sonderfarben und -formen.
    for laut, was in (
        ("#17375f", "der blaue Hover-Kasten"),
        ("rounded-3xl", "die extra runden Ecken"),
        ("shadow-xl", "der Schlagschatten"),
        ("grayscale", "das entfaerbte Serverbild"),
    ):
        check(f"{was} ist weg", laut not in grid, laut)

    # Die Hinweiskaesten der Seite ebenso.
    for laut in ("border-dashed", "p-16", "rounded-3xl"):
        check(f"die Seite hat kein {laut} mehr", laut not in seite, laut)

    # Der Rand-Schimmer MUSS hier bleiben.
    #
    # Beim ersten Anlauf hatte ich ihn entfernt -- mit der Begruendung,
    # die Karte habe jetzt einen eigenen Hover. Das war eine
    # Entscheidung, die mir nicht zusteht: der Nutzer wollte den
    # Schimmer ausdruecklich nur im ADMIN-Bereich nirgends, und diese
    # Seite gehoert nicht dazu. `test_admin_stil.py` hat es gemeldet
    # (111 Karten in 45 Dateien vorher, 108 in 44 danach) -- deshalb
    # steht die Erwartung jetzt auch hier, damit der naechste Umbau
    # nicht dieselbe stille Aenderung macht.
    check("der Rand-Schimmer bleibt erhalten",
          "border-glow-card" in grid,
          "er wurde nur im Admin-Bereich entfernt, nicht hier")
    check("mit passendem Eckradius",
          "glow-r-2xl" in grid,
          "ohne das sitzt der Lichtbogen an einer eckigen Bahn")


# ══════════════════════════════════════════════════════════════════════
#  6. Die leeren Zustaende erklaeren sich
# ══════════════════════════════════════════════════════════════════════


def test_leere_zustaende():
    print("\nDie leeren Zustaende erklaeren sich")

    seite = entkette(strip_ts(read(SEITE)))
    grid = entkette(strip_ts(read(GRID)))

    # „Keine Admin-Rechte" sagte nicht, welche gemeint sind.
    check("der Hinweis nennt die noetigen Rechte",
          "Server verwalten" in seite and "Administrator" in seite,
          "sonst weiss niemand, was ihm fehlt")

    # Eine leere Suche muss sagen, wonach gesucht wurde.
    check("die leere Suche sagt, wo gesucht wird",
          "im Namen und in der Server-ID" in grid, "")

    # Und der Bot-Ausfall darf keine falsche Sicherheit erzeugen.
    check("der Ausfall-Hinweis nennt die Folge",
          "Schätzungen von Discord" in seite,
          "sonst hält man die Zahlen für gezählt")


def main() -> int:
    test_zahl_wird_nicht_mehr_verschwiegen()
    test_kennzahlen_sind_ehrlich()
    test_deutsch_und_ruhig()
    test_karte_ist_der_knopf()
    test_stil()
    test_leere_zustaende()

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
