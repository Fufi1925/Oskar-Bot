#!/usr/bin/env python3
"""
Die oeffentliche Team-Seite, neu gebaut.

Was an der alten Fassung fehlte
-------------------------------
Sie beantwortete „wer macht das?" und hoerte auf. Die Frage „kann ich
mitmachen?" beantwortete sie nicht: dass es offene Rollen gibt, stand
ausschliesslich in einem Aufklapp-Menue der Navigationsleiste -- also
dort, wo niemand sucht, der gerade „Team" angeklickt hat.

Dabei kam ein echter Fehler ans Licht: `GET /webapply/roles` lag hinter
der Anmeldepflicht. Nachgemessen mit curl ohne Sitzungs-Cookie: HTTP
307 auf die Anmeldeseite. Auch die Bewerbungsseite zeigte einem
Nichtangemeldeten deshalb keine einzige Rolle -- unter einer
Ueberschrift, die „Vier Rollen" versprach.

Die Regeln, die hier festgehalten werden
----------------------------------------
  1. **Die Rollenliste ist ohne Anmeldung lesbar.** Sie ist der
     Aushang „wir suchen Leute" und enthaelt nichts Persoenliches.
     Middleware UND Proxy muessen sie durchlassen -- die Middleware
     laeuft zuerst, eine Freigabe nur im Proxy bliebe wirkungslos.
  2. **Nur GET, nur `roles`.** Das Abgeben, Ansehen und Zuruecknehmen
     einer Bewerbung braucht weiterhin eine Sitzung.
  3. **Keine erfundenen Rollen.** Antwortet der Bot nicht, verschwindet
     der Abschnitt. Eine fest einprogrammierte Liste wuerde weiter
     „bewirb dich" sagen, waehrend die Bewerbung abgelehnt wird.
  4. **Alle Rollen zu ist eine eigene Aussage.** „Gerade suchen wir
     niemanden" ist eine Antwort, eine leere Flaeche ist keine.
  5. **Zahlen werden gezaehlt, nicht behauptet.** Auf der
     Bewerbungsseite stand fest „Vier Rollen" -- falsch, sobald das
     Team eine Rolle schliesst.
  6. **Die Discord-ID ist kopierbar.** Achtzehn Ziffern als toter Text
     tippt niemand fehlerfrei ab.
  7. **Der Stil ist der des Rests.** Die Karten trugen
     `bg-white/[0.02]` und `border-white/[0.05]`, einen Stil, den es
     sonst nirgends mehr gibt.

Run:  python3 tests/test_team_seite.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []

FUFI = "1303627964734246944"
VEXO = "1033826242270609449"


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    with open(os.path.join(*teile), encoding="utf-8") as f:
        return f.read()


def read_dash(*teile) -> str:
    return read(DASH, *teile)


def strip_ts(src: str) -> str:
    """Kommentare raus -- sonst trifft die Suche die Erklaerung.

    Reihenfolge: ERST die Zeilenkommentare, DANN die Bloecke. Ein `/*`
    in einem `//`-Kommentar eroeffnet sonst einen Schein-Block, der den
    halben Quelltext verschluckt.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def entkette(src: str) -> str:
    """`"a" + "b"` zu `"ab"` -- sonst scheitert jede Prosa-Suche."""
    return re.sub(r'"\s*\+\s*"', "", src)


# ══════════════════════════════════════════════════════════════════════
#  1. Die Rollenliste ist ohne Anmeldung erreichbar
# ══════════════════════════════════════════════════════════════════════


def test_rollenliste_ist_oeffentlich():
    print("\nDer Aushang ist ohne Anmeldung lesbar")

    mw = strip_ts(read_dash("middleware.ts"))
    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))

    # Die Middleware laeuft ZUERST. Eine Freigabe nur im Proxy bliebe
    # wirkungslos -- der Besucher bekaeme vorher eine Weiterleitung.
    liste = re.search(r"const OEFFENTLICH = \[(.*?)\];", mw, re.S)
    check("die Middleware hat eine Liste offener Routen", liste is not None)
    if liste:
        check("die Rollenliste steht darin",
              '"/api/bot/webapply/roles"' in liste.group(1),
              "sonst kommt HTTP 307 statt der Rollen")
        # Aber nicht der ganze Bereich: submit/me/withdraw sind
        # persoenlich.
        check("aber nicht der ganze Bewerbungsbereich",
              '"/api/bot/webapply"' not in liste.group(1),
              "fremde Bewerbungen waeren sonst lesbar")

    # Und der Proxy ebenso -- vor der Anmeldepruefung.
    scope = re.search(
        r'if \(scope === "webapply"\) \{(.*?)\n  \}\n', proxy, re.S
    )
    check("der Proxy kennt den Bereich", scope is not None)
    if scope:
        rumpf = scope.group(1)
        frei = re.search(
            r'if \(request\.method === "GET" && rest\[0\] === "roles"\) \{\s*return \{ ok: true \};',
            rumpf,
        )
        check("er laesst GET /roles durch", frei is not None,
              "sonst 401 auf der oeffentlichen Seite")

        # Die Reihenfolge entscheidet: steht die Freigabe HINTER der
        # Anmeldepruefung, wird sie nie erreicht. Genau das war der
        # Fehler -- `roles` galt als „eigene" Route, kam dort aber nie
        # an.
        # Auf das HOLEN der Sitzung pruefen, nicht auf die
        # Fehlermeldung: die steht mehrfach im Rumpf, und die
        # Reihenfolge stimmte deshalb auch dann noch, wenn die
        # Freigabe hinter die Pruefung gerutscht war.
        holt = rumpf.find("await getServerSession(authOptions)")
        check("die Sitzung wird ueberhaupt geholt", holt >= 0)
        check("und zwar ERST NACH der Freigabe",
              frei is not None and holt > frei.start(),
              "sonst wird die Freigabe nie erreicht")

        # Nur lesen. Ein POST auf /roles gibt es nicht, aber die
        # Bedingung muss die Methode trotzdem nennen: sonst waere ein
        # spaeter ergaenztes Schreiben still mit offen.
        check("nur GET, nicht jede Methode",
              frei is not None and 'request.method === "GET"' in frei.group(0))

        # Das Abgeben braucht weiterhin eine Sitzung.
        check("Abgeben verlangt weiterhin eine Anmeldung",
              "Not signed in." in rumpf)
        check("und fremde Bewerbungen bleiben gesperrt",
              "Nur die eigene Bewerbung." in rumpf)


# ══════════════════════════════════════════════════════════════════════
#  2. Die Team-Seite
# ══════════════════════════════════════════════════════════════════════


def test_seite_zeigt_beides():
    print("\nDie Seite beantwortet beide Fragen")

    seite = read_dash("app", "team", "page.tsx")
    code = strip_ts(seite)
    text = entkette(seite)

    check("die Mitglieder werden gezeigt", "<TeamMitglieder" in code)
    check("und die offenen Rollen", "<TeamRollen" in code,
          "sonst fehlt der Weg ins Team wieder")

    # Die Ueberschrift muss beides ankuendigen, sonst ueberrascht der
    # zweite Abschnitt.
    # Nur den Untertitel ansehen. "Rollen" kommt im Fliesstext
    # darunter ebenfalls vor und deckte die Pruefung ab.
    untertitel = re.search(r'subtitle="([^"]+)"', code)
    check("es gibt einen Untertitel", untertitel is not None)
    if untertitel:
        check("er kuendigt die Rollen an",
              "Rollen" in untertitel.group(1),
              "sonst kuendigt die Seite nur die Haelfte an")
    check("es gibt einen Abschnitt zum Mitmachen",
          '"Mitmachen"' in text or "Mitmachen" in text)

    # Pro Aufruf gerendert: die Avatare kommen vom laufenden Bot.
    check("die Seite wird pro Aufruf gerendert",
          'export const dynamic = "force-dynamic"' in code)

    # Ein toter Bot darf die Seite nicht mitnehmen.
    profile = re.search(r"async function ladeProfile\(.*?\n\}", code, re.S)
    check("es gibt die Profil-Abfrage", profile is not None)
    if profile:
        check("ein Fehlschlag nimmt die Seite nicht mit",
              "catch {" in profile.group(0) and "return {};" in profile.group(0))
        check("und sie kann nicht haengen",
              "AbortSignal.timeout" in profile.group(0))

    # Eine kaputte Umgebungsvariable ebenso wenig.
    team = re.search(r"function ladeTeam\(\).*?\n\}", code, re.S)
    check("eine kaputte TEAM_JSON-Variable faengt die Seite ab",
          team is not None and "catch" in team.group(0))

    # Beide Namen stehen drin.
    check("Fufi ist gelistet", FUFI in seite)
    check("Vexo ist gelistet", VEXO in seite)
    check("Vexo ist als Entwickler genannt",
          re.search(rf'id: "{VEXO}".*?role: "[^"]*Entwickler', seite, re.S)
          is not None)
    check("und mit der urspruenglichen Idee",
          "ursprüngliche Idee" in text)

    # Kein GitHub -- das Repository ist privat. Im gestrippten Code
    # suchen: der Kommentar daneben erklaert genau das und traf die
    # Pruefung sonst selbst.
    check("kein GitHub-Feld", "github" not in code.lower(),
          "ein Link ins Leere laedt zum Suchen ein")

    # Der Support-Server bleibt erreichbar. Auf die Benutzung
    # pruefen, nicht auf das Wort: der Import allein verlinkt nichts.
    check("der Support-Server ist wirklich verlinkt",
          re.search(r"href=\{SUPPORT_INVITE\}", code) is not None,
          "der Import allein ist kein Link")


def test_mitglieder_karten():
    print("\nDie Mitglieder-Karten")

    src = read_dash("components", "team-mitglieder.tsx")
    code = strip_ts(src)

    check("es ist eine Client-Komponente", src.lstrip().startswith('"use client"'))
    check("es gibt die Komponente", "export function TeamMitglieder" in code)

    # Regel 6: die ID muss kopierbar sein.
    check("die Discord-ID laesst sich kopieren",
          "navigator.clipboard.writeText" in code,
          "achtzehn Ziffern tippt niemand fehlerfrei ab")
    # Den Rumpf der Kopier-Funktion isolieren. `setKopiert` steht
    # auch im Aufraeum-Effekt (`setKopiert("")`), und die Pruefung
    # blieb deshalb gruen, obwohl der KLICK nichts mehr gesetzt hat.
    kopieren = re.search(r"const kopieren = async \(id: string\) => \{(.*?)\n  \};",
                         code, re.S)
    check("es gibt die Kopier-Funktion", kopieren is not None)
    if kopieren:
        check("der Klick setzt die Rueckmeldung",
              re.search(r"setKopiert\(id\)", kopieren.group(1)) is not None,
              kopieren.group(1)[:150])
    check("und sie wird angezeigt", "Kopiert" in code)
    # Und die Rueckmeldung muss sich zuruecksetzen, sonst bleibt das
    # Haekchen fuer immer stehen.
    check("die Rueckmeldung verschwindet wieder",
          "setKopiert(\"\")" in code and "setTimeout" in code)
    check("der Zeitgeber wird aufgeraeumt",
          "clearTimeout" in code,
          "sonst loescht der erste Klick die Rueckmeldung des zweiten")
    # Ohne HTTPS gibt es keine Zwischenablage -- das darf nichts
    # kaputtmachen.
    check("ein Fehlschlag beim Kopieren wird abgefangen",
          re.search(r"catch \{", code) is not None)
    # Die ID bleibt als Text stehen, damit man sie notfalls markieren
    # kann.
    check("die ID steht weiterhin als Text da",
          "{person.id}" in code,
          "ohne Zwischenablage waere sie sonst gar nicht zu bekommen")

    # Screenreader sehen kein Haekchen.
    check("der Knopf sagt seinen Zustand auch als Text",
          "aria-label" in code and "kopiert" in code)

    # Regel 3 der Optik: Initialen statt kaputtem Bild.
    # Auf die BENUTZUNG pruefen, nicht auf die Definition: eine
    # Funktion, die niemand aufruft, zeichnet keine Initialen.
    check("es gibt die Initialen-Funktion", "function initialen(" in code)
    check("und sie wird auch gerendert",
          re.search(r"\{initialen\(name\)\}", code) is not None,
          "sonst bleibt ein leeres Kaestchen stehen")
    check("das Bild nennt die Person im alt-Text",
          "Profilbild von ${name}" in code)

    # Regel 7: der Stil des Rests.
    check("die Karten tragen die Farbe des Rests", "bg-[#131318]" in code)
    check("und den Rand", "border-slate-800" in code)
    check("der alte Glas-Stil ist weg",
          "bg-white/[0.02]" not in code and "border-white/[0.05]" not in code,
          "ein Stil, den es sonst nirgends mehr gibt")


def test_rollen_abschnitt():
    print("\nDer Rollen-Abschnitt")

    src = read_dash("components", "team-rollen.tsx")
    code = strip_ts(src)
    text = entkette(src)

    check("es ist eine Client-Komponente", src.lstrip().startswith('"use client"'))
    check("es gibt die Komponente", "export function TeamRollen" in code)

    # Regel 3: keine erfundenen Rollen.
    #
    # Nicht auf `api.getApplyRoles()` am Stueck pruefen: der Aufruf
    # steht ueber zwei Zeilen (`api\n  .getApplyRoles()`), und die
    # Pruefung schlug fehl, obwohl der Aufruf da war.
    check("die Rollen kommen vom Bot",
          re.search(r"api\s*\n?\s*\.getApplyRoles\(\)", code) is not None,
          "eine feste Liste wuerde weiter werben, wenn eine Rolle zu ist")
    fest = re.findall(r'label:\s*"(Content Creator|Designer|Moderator|Tester)"', code)
    check("keine Rolle steht fest im Quelltext", not fest, str(fest))

    # Faellt der Bot aus, verschwindet der Abschnitt.
    check("ohne Antwort verschwindet der Abschnitt",
          "if (!rollen || rollen.length === 0) return null;" in code,
          "lieber nichts als eine erfundene Liste")
    check("ein Fehlschlag setzt die Liste auf nichts",
          re.search(r"\.catch\(\(\) => \{[^}]*setRollen\(null\)", code, re.S)
          is not None)
    # Der Ladekringel darf nicht haengen bleiben.
    check("der Ladezustand endet immer",
          ".finally(" in code and "setLaedt(false)" in code)
    # Und eine ueberholte Antwort darf nichts ueberschreiben.
    check("eine abgebrochene Anfrage schreibt nichts mehr",
          "abgebrochen" in code and "if (abgebrochen) return;" in code)

    # Regel 4: alle zu ist eine eigene Aussage.
    check("es wird nach offenen Rollen gefiltert",
          "rollen.filter((r) => r.open)" in code)
    check("alle zu sagt es ausdruecklich",
          "Gerade suchen wir niemanden" in text,
          "eine leere Flaeche ist keine Antwort")
    # Und die Aussage muss auch erreicht werden.
    check("und zwar bevor die Liste gezeichnet wird",
          "if (wirklichOffen.length === 0)" in code)

    # Der Weg ins Formular.
    check("jede Rolle fuehrt ins Formular",
          "/team/apply?rolle=${rolle.key}" in code)
    check("mit einem sichtbaren Knopf", "Bewerben" in text)

    # Die Fragen zum Aufklappen.
    check("die Fragen lassen sich aufklappen",
          "question_list" in code and "setOffen(" in code)
    check("der Ausklapper sagt seinen Zustand",
          "aria-expanded" in code)

    # Die Symbole muessen zu denen des Formulars passen.
    hier = set(re.findall(r"^\s+(\w+): (?:Video|Sparkles|Shield|Wrench),", code, re.M))
    formular = strip_ts(read_dash("app", "team", "apply", "page.tsx"))
    dort = set(re.findall(r"^\s+(\w+): (?:Video|Sparkles|Shield|Wrench),", formular, re.M))
    check("dieselben Symbole wie im Formular", hier == dort,
          f"hier {sorted(hier)}, dort {sorted(dort)}")

    # Die Farbe kommt aus dem Bot und muss inline gesetzt werden --
    # Tailwind sammelt Klassen zur Bauzeit ein und kennt einen erst zur
    # Laufzeit bekannten Farbwert nicht.
    # Das Symbol muss die Farbe bekommen, nicht irgendein Element.
    # `rolle.colour` und `style={{` stehen auch am Rahmen darum
    # herum, und die Pruefung blieb deshalb gruen, als das Symbol
    # seine Farbe verlor.
    check("der Rahmen benutzt die Rollenfarbe",
          "rolle.colour" in code and "style={{" in code)
    check("und das Symbol ebenfalls",
          re.search(r"<Icon[^>]*style=\{\{\s*color:\s*rolle\.colour", code)
          is not None,
          "sonst sind alle vier Symbole grau")

    # Die Dauer ist geschaetzt und wird als Schaetzung ausgewiesen.
    # Auf die Rueckgabe der Funktion pruefen. „etwa" steht auch in
    # anderen Saetzen der Datei und deckte die Pruefung ab.
    dauer = re.search(r"function dauer\(fragen: number\) \{(.*?)\n\}", code, re.S)
    check("es gibt die Dauer-Funktion", dauer is not None)
    if dauer:
        check("sie weist die Dauer als Schaetzung aus",
              "etwa" in dauer.group(1),
              "eine minutengenaue Angabe waere erfunden")


# ══════════════════════════════════════════════════════════════════════
#  3. Die Bewerbungsseite zaehlt statt zu behaupten
# ══════════════════════════════════════════════════════════════════════


def test_bewerbungsseite_zaehlt():
    print("\nDie Bewerbungsseite behauptet keine Zahl mehr")

    src = read_dash("app", "team", "apply", "page.tsx")
    code = strip_ts(src)
    text = entkette(code)

    check("die feste Zahl ist weg", "Vier Rollen" not in text,
          "falsch, sobald das Team eine Rolle schliesst")
    check("es wird wirklich gezaehlt",
          "rollen.filter((r) => r.open).length" in code)
    check("die Zahl wird auch gezeigt", "offeneRollen" in code)
    # Singular und Plural.
    check("eine einzelne Rolle heisst nicht »1 Rollen«",
          "offeneRollen === 1" in code)
    # Solange geladen wird, steht keine Zahl da: eine aufblitzende
    # Null waere schlimmer als eine Luecke.
    #
    # Der Lade-Zweig muss VOR der Zahl stehen. Nur auf `{laden ?` zu
    # pruefen reichte nicht: die Datei benutzt `laden` auch an
    # anderer Stelle, und ein Ausdruck, der die Zahl zuerst
    # auswertet, blieb unbemerkt.
    absatz = re.search(r"<p className=\"mt-3 max-w-2xl[^\"]*\">(.*?)</p>",
                       code, re.S)
    check("der Einleitungssatz wurde gefunden", absatz is not None)
    if absatz:
        rumpf = absatz.group(1)
        check("er nennt die Zahl", "offeneRollen" in rumpf, rumpf[:120])
        check("und prueft zuerst den Ladezustand",
              rumpf.find("laden") >= 0
              and rumpf.find("laden") < rumpf.find("offeneRollen"),
              "sonst blitzt beim Laden eine Null auf")

    # Der Ausweg fuer Nichtangemeldete.
    check("ohne Konto gibt es einen Weg zu den Rollen",
          "Erst die Rollen ansehen" in text,
          "sonst endet der Besuch in einer Sackgasse")
    check("und der zeigt auf die Team-Seite",
          re.search(r'href="/team"[^>]*>\s*\n?\s*Erst die Rollen ansehen', src)
          is not None
          or 'href="/team"' in src)


# ══════════════════════════════════════════════════════════════════════
#  4. Die Rollen stimmen mit dem Bot ueberein
# ══════════════════════════════════════════════════════════════════════


def test_rollen_passen_zum_bot():
    print("\nWebsite und Bot kennen dieselben Rollen")

    from utils import web_apply_store as store

    # Die Navigationsleiste hat ihre eigene, feste Liste. Sie darf
    # keine Rolle nennen, die es nicht gibt -- ein Link auf
    # ?rolle=irgendwas fuehrt zu einem Formular, das der Bot ablehnt.
    nav = strip_ts(read_dash("components", "site-nav.tsx"))
    verlinkt = set(re.findall(r"/team/apply\?rolle=(\w+)", nav))
    check("die Navigation verlinkt Rollen", bool(verlinkt), str(verlinkt))
    unbekannt = sorted(verlinkt - set(store.ROLE_KEYS))
    check("keine erfundene Rolle in der Navigation", not unbekannt,
          str(unbekannt))

    # Die Symbol-Zuordnung muss jede Rolle des Bots kennen, sonst
    # bekommt eine neue Rolle stillschweigend ein fremdes Symbol.
    rollen_src = strip_ts(read_dash("components", "team-rollen.tsx"))
    block = re.search(r"const ROLLEN_ICON[^=]*=\s*\{(.*?)\};", rollen_src, re.S)
    check("es gibt eine Symbol-Zuordnung", block is not None)
    if block:
        bekannt = set(re.findall(r"^\s+(\w+):", block.group(1), re.M))
        fehlt = sorted(set(store.ROLE_KEYS) - bekannt)
        check("jede Rolle des Bots hat ein Symbol", not fehlt, str(fehlt))
        zuviel = sorted(bekannt - set(store.ROLE_KEYS))
        check("und keins zu viel", not zuviel, str(zuviel))


def test_route_liefert_was_die_seite_braucht():
    """Die Felder, die die Seite liest, muessen wirklich ankommen."""
    print("\nDie Route liefert, was die Seite anzeigt")

    route = strip_ts(read(BOT, "api", "routes", "webapply.py"))
    rollen_src = strip_ts(read_dash("components", "team-rollen.tsx"))

    # Was die Komponente aus einer Rolle liest.
    gelesen = set(re.findall(r"rolle\.(\w+)", rollen_src))
    gelesen |= set(re.findall(r"\br\.(\w+)", rollen_src))

    from utils import web_apply_store as store

    # Was der Store liefert.
    vom_store = set(store.role_list()[0])

    # Und was die Route zusaetzlich anhaengt -- aus IHREM Quelltext
    # gelesen, nicht von Hand ergaenzt. Vorher standen "open" und
    # "question_list" hier fest in der Soll-Liste; damit konnte die
    # Pruefung ihren Verlust gar nicht bemerken.
    block = re.search(r"out\.append\(\{(.*?)\}\)", route, re.S)
    check("der Bauplan der Antwort wurde gefunden", block is not None)
    von_route = set(re.findall(r'"(\w+)":', block.group(1))) if block else set()

    geliefert = vom_store | von_route
    check("die Route ergaenzt den Offen-Zustand", "open" in von_route,
          f"die Route liefert nur {sorted(von_route)}")
    check("und die Fragen", "question_list" in von_route,
          f"die Route liefert nur {sorted(von_route)}")

    fehlt = sorted(gelesen - geliefert)
    check("jedes gelesene Feld wird auch geliefert", not fehlt,
          f"{fehlt} -- gelesen aber nicht geliefert")


def main() -> int:
    test_rollenliste_ist_oeffentlich()
    test_seite_zeigt_beides()
    test_mitglieder_karten()
    test_rollen_abschnitt()
    test_bewerbungsseite_zaehlt()
    test_rollen_passen_zum_bot()
    test_route_liefert_was_die_seite_braucht()

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
