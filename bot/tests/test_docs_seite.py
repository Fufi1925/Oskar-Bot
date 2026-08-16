#!/usr/bin/env python3
"""
Die Dokumentation (/docs).

Was hier vorher stand
---------------------
Eine Seite, die aussah wie eine Dokumentation, aber keine war. Neun
Navigationspunkte -- und **alle neun zeigten denselben Text**, nur die
Ueberschrift wechselte. Im Browser nachgemessen: ein Klick auf
„Anti-Nuke" ergab „Anti-Nuke." ueber demselben Absatz wie
„Introduction".

Der Text war zur Haelfte englisch und beschrieb Dinge, die es nicht
gibt. Drei davon sind nicht bloss Marketing, sondern **belegbar
falsch** -- und zwar gegen die eigene Datenschutzerklaerung:

  * „AES-256 encryption": `app/privacy/page.tsx` sagt ausdruecklich,
    die Daten lägen in gewoehnlichen SQLite-Dateien und seien *nicht*
    zusaetzlich verschluesselt. Genau diese Behauptung wurde dort
    schon einmal als falsch entfernt -- und stand hier weiter.
  * „global edge network in under 12ms": es laeuft ein Container auf
    einem Host. Steht so ebenfalls in der Datenschutzerklaerung.
  * „Neural Core", „neural sandbox", „cluster-shard [neural_07]":
    frei erfunden. Fuer die Startseite verbietet
    `test_website_look.py` das Wort „Neural" laengst; fuer diese
    Seite galt der Test nie.

Dazu ein Suchfeld, das nichts tat, und Requisiten wie
„DOC-ID: CX_7749_B" und ein blinkendes „Live Stream Active".

Was jetzt gilt
--------------
  1. **Jeder Abschnitt hat eigenen Inhalt.** Das ist der Kern: eine
     Doku, in der neun Punkte dasselbe zeigen, ist keine.
  2. **Die Suche filtert wirklich.** Ein Eingabefeld, das nicht
     reagiert, ist schlimmer als keines -- man sucht, findet nichts
     und haelt die Doku fuer leer.
  3. **Keine Behauptung, die der Datenschutzerklaerung widerspricht.**
  4. **Deutsch.** Die Seite ist Teil eines deutschen Auftritts.

Run:  python3 tests/test_docs_seite.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")

SEITE = os.path.join(DASH, "app", "docs", "page.tsx")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(pfad: str) -> str:
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus -- sonst trifft die Suche die Erklaerung.

    Reihenfolge: ERST die Zeilenkommentare, DANN die Bloecke. Ein
    ``/*`` in einem ``//``-Kommentar eroeffnet sonst einen
    Schein-Block, der den halben Quelltext verschluckt.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def entkette(src: str) -> str:
    """`"a" + "b"` zu `"ab"` -- sonst scheitert jede Prosa-Suche."""
    return re.sub(r'"\s*\+\s*"', "", src)


# ══════════════════════════════════════════════════════════════════════
#  1. Jeder Abschnitt hat eigenen Inhalt
# ══════════════════════════════════════════════════════════════════════


def test_abschnitte_sind_verschieden():
    print("\nJeder Abschnitt hat eigenen Inhalt")

    code = strip_ts(read(SEITE))
    check("die Seite existiert", bool(code))
    if not code:
        return

    check("es gibt eine Liste von Abschnitten",
          "const ABSCHNITTE" in code)

    # Jeder Eintrag braucht id, titel und eigenen Inhalt.
    # Nur die Eintraege der Liste zaehlen, nicht jedes Vorkommen im
    # Quelltext: `titel: string;` in der Typdefinition und drei
    # verschachtelte Modulkarten weiter unten trugen dasselbe Wort und
    # ergaben 9 statt 6. Deshalb erst den Block ausschneiden und dann
    # nur die Felder auf der Ebene der Eintraege lesen (vier
    # Leerzeichen Einrueckung, verschachtelte haben mehr).
    block = re.search(r"const ABSCHNITTE: Abschnitt\[\] = \[(.*?)\n\];",
                      code, re.S)
    if not block:
        check("die Abschnittsliste ist lesbar", False, "Block nicht gefunden")
        return
    rumpf = block.group(1)

    ids = re.findall(r'^    id:\s*"([^"]+)"', rumpf, re.M)
    titel = re.findall(r'^    titel:\s*"([^"]+)"', rumpf, re.M)
    inhalte = len(re.findall(r"^    inhalt:\s*\(", rumpf, re.M))

    check("es gibt mehrere Abschnitte", len(ids) >= 5, str(len(ids)))
    check("jeder hat einen Titel", len(titel) == len(ids),
          f"{len(titel)} Titel bei {len(ids)} Abschnitten")
    check("jeder hat eigenen Inhalt", inhalte == len(ids),
          f"{inhalte} Inhalte bei {len(ids)} Abschnitten -- vorher "
          "teilten sich neun Punkte EINEN Text")

    # Kein Abschnitt darf zweimal dieselbe Kennung tragen.
    check("die Kennungen sind eindeutig", len(set(ids)) == len(ids),
          f"doppelt: {[i for i in set(ids) if ids.count(i) > 1]}")

    # Und der gezeigte Inhalt muss am gewaehlten Abschnitt haengen.
    check("gezeigt wird der gewaehlte Abschnitt",
          re.search(r"ABSCHNITTE\.find\(\(a\) => a\.id === aktiv\)", code)
          is not None,
          "sonst steht ueberall derselbe Text")


# ══════════════════════════════════════════════════════════════════════
#  2. Die Suche filtert wirklich
# ══════════════════════════════════════════════════════════════════════


def test_suche_filtert():
    print("\nDie Suche filtert wirklich")

    code = strip_ts(read(SEITE))

    check("es gibt ein Suchfeld", "value={suche}" in code)
    check("und es schreibt in den Zustand",
          "onChange={(e) => setSuche(e.target.value)}" in code)

    # Der Kern: die Liste muss vom Suchwort abhaengen. Vorher stand
    # dort ein Feld ohne jede Wirkung.
    treffer = re.search(
        r"const gefiltert = React\.useMemo\(\(\) => \{(.*?)\}, \[suche\]\)",
        code, re.S,
    )
    check("die Liste wird gefiltert", treffer is not None,
          "das alte Feld tat nachweislich nichts")
    if treffer:
        rumpf = treffer.group(1)
        check("gesucht wird im Titel",
              "a.titel.toLowerCase().includes(q)" in rumpf, "")
        check("und in den Stichworten",
              "a.stichworte.includes(q)" in rumpf,
              "der sichtbare Text ist JSX und nicht durchsuchbar")

    # Die gefilterte Liste muss auch gerendert werden -- sonst filtert
    # sie ins Leere.
    check("die gefilterte Liste wird gerendert",
          "gefiltert.map((a) =>" in code,
          "sonst filtert die Suche, ohne dass man es sieht")

    # Jeder Abschnitt braucht Stichworte, sonst ist er unauffindbar.
    # Wie oben: nur die Ebene der Eintraege.
    block = re.search(r"const ABSCHNITTE: Abschnitt\[\] = \[(.*?)\n\];",
                      code, re.S)
    rumpf = block.group(1) if block else ""
    ids = re.findall(r'^    id:\s*"([^"]+)"', rumpf, re.M)
    stichworte = re.findall(r'^    stichworte:\s*"([^"]+)"', rumpf, re.M)
    check("jeder Abschnitt hat Stichworte",
          len(stichworte) == len(ids),
          f"{len(stichworte)} von {len(ids)}")
    check("und keine sind leer",
          all(len(s.strip()) > 3 for s in stichworte), "")

    # Null Treffer muss gesagt werden.
    check("bei null Treffern steht ein Hinweis",
          "gefiltert.length === 0" in code and "Nichts gefunden" in code,
          "eine leere Spalte sieht aus wie ein Fehler")

    # Verschwindet der offene Abschnitt, darf rechts nicht ein Text
    # stehen, der links nicht mehr auftaucht.
    check("die Anzeige springt auf den ersten Treffer",
          "setAktiv(gefiltert[0].id)" in code, "")


# ══════════════════════════════════════════════════════════════════════
#  3. Keine erfundenen Behauptungen
# ══════════════════════════════════════════════════════════════════════


def test_keine_erfundenen_behauptungen():
    print("\nKeine erfundenen Behauptungen")

    code = strip_ts(read(SEITE))
    text = entkette(code)

    # Die drei, die der Datenschutzerklaerung widersprechen.
    for luege, warum in (
        ("AES-256", "die Daten sind NICHT verschluesselt -- steht so in "
                    "app/privacy/page.tsx"),
        ("edge network", "es laeuft ein Container auf einem Host"),
        ("Neural", "frei erfunden; fuer die Startseite laengst verboten"),
    ):
        check(f"»{luege}« steht nicht mehr drin", luege not in text, warum)

    # Die Requisiten.
    for requisit in ("DOC-ID", "Live Stream", "cluster-shard",
                     "Runtime Environment", "12ms"):
        check(f"»{requisit}« ist weg", requisit not in text, "")

    # Gegenprobe: die Datenschutzerklaerung sagt wirklich das
    # Gegenteil. Ohne diesen Nachweis waere die Regel oben nur eine
    # Behauptung ueber eine Behauptung.
    privacy = read(os.path.join(DASH, "app", "privacy", "page.tsx"))
    check("die Datenschutzerklaerung widerspricht AES-256 ausdruecklich",
          "nicht zusätzlich" in privacy and "verschlüsselt" in privacy,
          "sonst ist unklar, welche Aussage stimmt")


def test_deutsch():
    print("\nDie Seite ist deutsch")

    code = strip_ts(read(SEITE))

    # Die englischen Ueberschriften der alten Fassung.
    for englisch in ("Getting Started", "Security Modules", "Quick Start",
                     "Introduction", "Fast Dispatch", "Secure Node",
                     "Protocol Overview", "Enterprise"):
        check(f"»{englisch}« ist uebersetzt", englisch not in code, "")

    # Und ein paar deutsche Begriffe muessen da sein.
    text = entkette(code)
    for deutsch in ("Dokumentation", "Bot hinzufügen", "Dashboard"):
        check(f"»{deutsch}« kommt vor", deutsch in text, "")


# ══════════════════════════════════════════════════════════════════════
#  4. Der Inhalt stimmt mit dem Projekt überein
# ══════════════════════════════════════════════════════════════════════


def test_zahlen_stimmen():
    """Was die Doku behauptet, muss im Projekt nachweisbar sein."""
    print("\nDie Angaben stimmen mit dem Projekt")

    code = strip_ts(read(SEITE))

    # Die Zahl der Dashboard-Bereiche steht als Konstante da und muss
    # der Zahl der Ordner entsprechen. Eine Doku, die 41 sagt, waehrend
    # es 30 sind, ist schlechter als gar keine Zahl.
    treffer = re.search(r"const BEREICHE_GESAMT = (\d+)", code)
    check("die Zahl der Bereiche steht als Konstante da",
          treffer is not None)
    if treffer:
        behauptet = int(treffer.group(1))
        ordner = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]")
        echt = len([
            e for e in os.listdir(ordner)
            if os.path.isdir(os.path.join(ordner, e))
        ])
        check("und sie stimmt", behauptet == echt,
              f"Doku sagt {behauptet}, es sind {echt}")

    # Das Praefix muss dem entsprechen, was die Startseite nennt.
    treffer = re.search(r'const PREFIX = "([^"]+)"', code)
    check("das Praefix steht als Konstante da", treffer is not None)
    if treffer:
        startseite = read(os.path.join(DASH, "app", "page.tsx"))
        check("und passt zur Startseite",
              f"Standard ist {treffer.group(1)}" in startseite,
              "zwei Angaben zum Praefix laufen auseinander")

    # Die aufgezaehlten Bereiche duerfen nicht mehr sein als es gibt.
    liste = re.search(r"const DASHBOARD_BEREICHE = \[(.*?)\];", code, re.S)
    check("es gibt eine Auswahlliste", liste is not None)
    if liste and treffer:
        namen = re.findall(r'"([^"]+)"', liste.group(1))
        gesamt = int(re.search(r"const BEREICHE_GESAMT = (\d+)", code).group(1))
        check("die Auswahl ist kleiner als die Gesamtzahl",
              0 < len(namen) < gesamt,
              f"{len(namen)} von {gesamt}")


def test_verlinkt_weiter():
    print("\nDie Seite fuehrt weiter")

    code = strip_ts(read(SEITE))

    check("zur Befehlsliste", '"/commands"' in code)
    check("zur Statusseite", '"/status"' in code)
    check("zum Support-Server", "SUPPORT_INVITE" in code)
    # JEDES target="_blank" einzeln pruefen, nicht "kommt noopener
    # irgendwo vor". Es gibt zwei externe Links; faellt bei einem der
    # Schutz weg, blieb die alte Pruefung gruen -- im Mutationstest
    # genau so durchgerutscht.
    offen = re.findall(r'target="_blank"', code)
    sicher = re.findall(r'rel="noopener noreferrer"', code)
    check("jeder externe Link oeffnet sicher",
          len(offen) > 0 and len(sicher) == len(offen),
          f"{len(offen)}x target=_blank, aber nur {len(sicher)}x noopener "
          "-- ohne das bekommt die Zielseite Zugriff auf das Fenster")

    # Ein Weiter-Knopf am Ende jedes Abschnitts.
    check("es gibt einen Weiter-Knopf",
          "ABSCHNITTE[i + 1]" in code,
          "eine Doku, die unten aufhoert, laesst einen im Nichts stehen")
    check("und er blendet sich beim letzten aus",
          "if (!naechster) return null;" in code, "")

    # Die gemeinsame Navigationsleiste, nicht eine eigene.
    check("die Seite nutzt die gemeinsame Leiste",
          "<SiteNav />" in code,
          "vorher gab es hier eine zweite Fassung")


def main() -> int:
    test_abschnitte_sind_verschieden()
    test_suche_filtert()
    test_keine_erfundenen_behauptungen()
    test_deutsch()
    test_zahlen_stimmen()
    test_verlinkt_weiter()

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
