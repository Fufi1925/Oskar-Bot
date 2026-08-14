#!/usr/bin/env python3
"""
Die Status-Website: live, mit Verlauf.

Was vorher war
--------------
Die Seite holte den Zustand einmal beim Rendern auf dem Server und
zeichnete ihn als feste Liste. Zwei Nachteile, und beide fielen genau
dann auf, wenn man die Seite braucht:

  * **Sie blieb stehen.** Wer sie waehrend einer Stoerung offen liess,
    las eine halbe Stunde spaeter immer noch „Stoerung".
  * **Sie zeigte nur den Moment.** Keine Antwort auf „war das nur
    kurz?" oder „wie oft passiert das?".

Was jetzt gilt
--------------
  1. Der Browser holt sich den Zustand alle 30 Sekunden selbst, ueber
     ``/api/status``. `STATUS_BOT_URL` zeigt auf einen Railway-internen
     Namen -- den kann ein Browser nicht aufloesen, deshalb die Route.
  2. Der Verlauf haengt am Zeitraum, nicht am Takt: 24 Stunden, 7 Tage,
     30 Tage. Ihn alle 30 Sekunden mitzuschicken waeren ein paar
     hundert Messpunkte, die sich nicht geaendert haben.
  3. **Ein grauer Balken ist keine gute Nachricht.** „Nicht gemessen"
     heisst: der Waechter war selbst aus. Das gruen zu zeichnen waere
     eine Behauptung ohne Messung -- dieselbe Regel wie beim
     Discord-Panel.
  4. Antwortet der Waechter nicht, steht das da. Kein falsches Gruen,
     und HTTP 200 statt 502: „nicht erreichbar" ist eine Auskunft,
     kein Fehler.

Run:  python3 tests/test_status_website.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
STATUS = os.path.join(ROOT, "statusbot")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    with open(os.path.join(*teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke. Ein
    # Pfad mit Sternchen in einem //-Kommentar eroeffnet sonst einen
    # Schein-Block, der den halben Quelltext verschluckt.
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


# ══════════════════════════════════════════════════════════════════════


def test_der_endpunkt():
    print("\nDer Waechter liefert den Verlauf")

    quelle = read(STATUS, "status_bot.py")

    check("es gibt /history.json",
          'app.router.add_get("/history.json"' in quelle)
    check("die Route ist definiert",
          "async def handle_public_history" in quelle)
    check("sie liefert die Saeulen", "history.buckets(" in quelle)
    check("dazu die Zusammenfassung",
          '"uptime": history.summary()' in quelle
          and "history.error_summary(" in quelle)

    # Ohne CORS kann die Website sie nicht lesen.
    rumpf = quelle.split("async def handle_public_history", 1)[1]
    rumpf = rumpf.split("\n    app = web.Application", 1)[0]
    check("mit offenem CORS",
          '"Access-Control-Allow-Origin": "*"' in rumpf,
          "sonst blockt der Browser die Antwort")

    # Ein Zeitraum jenseits der Aufbewahrung waere eine Achse ueber
    # Wochen, die es nie gab.
    check("der Zeitraum ist begrenzt",
          "min(hours, history.KEEP_DAYS * 24)" in rumpf)
    check("und faellt bei Unsinn auf 24 zurueck",
          "except (TypeError, ValueError)" in rumpf)

    # 30 Tage stundenweise waeren 720 Saeulen auf einem Handy.
    check("die Saeulenzahl haengt am Zeitraum",
          "count = 24 if hours <= 24" in rumpf)

    # Die Website muss wissen, ob ueberhaupt dauerhaft aufgezeichnet
    # wird -- sonst kann sie einen leeren Graphen nicht erklaeren.
    check("sie meldet, ob dauerhaft gespeichert wird",
          "storage_is_persistent()" in rumpf)
    check("status.json sagt es auch",
          '"history_persistent"' in quelle)


def test_die_proxy_route():
    print("\nDie Route, die der Browser erreichen kann")

    pfad = os.path.join(DASH, "app", "api", "status", "route.ts")
    check("es gibt sie", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    quelle = strip_ts(read(pfad))

    check("sie liest STATUS_BOT_URL", "process.env.STATUS_BOT_URL" in quelle)
    check("sie holt den Zustand", "/status.json" in quelle)
    check("und den Verlauf", "/history.json" in quelle)
    check("der Zeitraum wird durchgereicht",
          "hours=${encodeURIComponent(stunden)}" in quelle,
          "sonst zeigen alle drei Knoepfe dasselbe")

    # Ein Fehlerstatus wuerde im Browser als abgebrochene Anfrage
    # landen -- die Seite koennte nicht unterscheiden, ob der Waechter
    # aus ist oder das eigene Netz.
    check("ein Ausfall kommt als ok:false, nicht als 502",
          '{ ok: false, reason: "unreachable" }' in quelle
          or 'reason: "unreachable"' in quelle)
    check("mit Zeitgrenze",
          "AbortSignal.timeout" in quelle,
          "sonst haengt die Statusseite am ausgefallenen Dienst")
    check("nie zwischengespeichert",
          '"Cache-Control": "no-store"' in quelle
          and 'cache: "no-store"' in quelle)
    check("ohne gesetzte URL sagt sie das",
          '"not_configured"' in quelle)


def test_die_seite():
    print("\nDie Seite selbst")

    seite = strip_ts(read(DASH, "app", "status", "page.tsx"))
    check("sie bindet den Live-Baustein ein",
          re.search(r"<StatusLive\b", seite) is not None)
    check("und wird nie zwischengespeichert",
          'dynamic = "force-dynamic"' in seite and "revalidate = 0" in seite,
          "ein alter Zustand ist schlimmer als keiner")

    # Der alte Aufbau darf nicht zurueckkommen.
    check("sie holt die Daten nicht mehr selbst",
          "status.json" not in seite,
          "das macht jetzt der Browser -- sonst steht die Seite wieder still")


def test_der_live_baustein():
    print("\nDer Live-Baustein")

    quelle = strip_ts(read(DASH, "components", "status-live.tsx"))

    # Nicht "kommt das Wort vor": `setInterval` steht auch in der
    # Uhr-Anzeige weiter oben, und `clearInterval` dort ebenso. Beide
    # Mutationen -- Takt ganz weg, Timer nicht abgeraeumt -- blieben
    # damit gruen. Geprueft wird deshalb der Zustands-Effekt selbst.
    takt = ""
    if "ladeZustand();" in quelle:
        takt = quelle.split("    ladeZustand();", 1)[1].split("}, [ladeZustand]);", 1)[0]
    check("er aktualisiert sich selbst",
          "setInterval(() => ladeZustand(), INTERVALL_MS)" in takt,
          "ohne diesen Takt steht die Seite still")
    check("alle 30 Sekunden", "30_000" in quelle)
    check("und raeumt den Timer wieder ab",
          "return () => clearInterval(t);" in takt,
          "sonst laeuft er nach dem Verlassen der Seite weiter")

    check("drei Zeitraeume", "24 * 7" in quelle and "24 * 30" in quelle)
    check("der Verlauf haengt am Zeitraum",
          "}, [stunden]);" in quelle,
          "sonst wird er bei jedem Takt neu geladen")

    # Eine spaet eintreffende alte Antwort darf die neue nicht
    # ueberschreiben -- sonst steht nach schnellem Klicken der falsche
    # Zeitraum im Bild.
    # `abgebrochen.current` steht auch in der Aufraeumfunktion --
    # allein das Vorkommen sagt nichts darueber, ob der Riegel VOR
    # setVerlauf sitzt. Im Mutationstest genau so durchgerutscht.
    check("eine veraltete Antwort wird verworfen",
          "if (!abgebrochen.current) setVerlauf(daten);" in quelle,
          "sonst steht nach schnellem Klicken der falsche Zeitraum im Bild")
    check("und der Riegel wird beim Aufraeumen gesetzt",
          "abgebrochen.current = true;" in quelle)

    check("ein toter Waechter wird gemeldet",
          "Status nicht abrufbar" in quelle)
    check("und nicht als gruen dargestellt",
          quelle.index("Status nicht abrufbar") < quelle.index("Alle Systeme laufen"),
          "der Ausfall muss VOR dem Normalfall geprueft werden")

    # Prozent auf Deutsch: toFixed liefert immer einen Punkt.
    check("die Prozentzahl ist deutsch formatiert",
          "function prozent(" in quelle and 'toLocaleString("de-DE"' in quelle)
    check("kein toFixed mehr",
          "toFixed(" not in quelle,
          "»99.62 %« mit Punkt auf einer deutschen Seite")

    # Die Einheit gehoert sichtbar hin -- an der Achse steht sie nicht.
    check("die Antwortzeit nennt ihre Einheit",
          "in Millisekunden" in quelle,
          "»4.813« liest sich sonst als vier Komma acht")

    # Eine Luecke ist keine Null.
    check("nicht gemessene Abschnitte werden null",
          "s.known && s.latency !== null ? Math.round(s.latency) : null" in quelle,
          "0 hiesse »sofort geantwortet«")

    # Die Variable existiert auch dann noch, wenn sie niemand mehr
    # abfragt. Geprueft wird die Benutzung als Bedingung.
    check("ohne Messwerte kein leeres Gitter",
          "{hatMesswerte && (" in quelle,
          "ein Gitter ohne Linie beantwortet keine Frage")


def test_die_balken():
    print("\nDie Verfuegbarkeits-Balken")

    pfad = os.path.join(DASH, "components", "ui", "uptime-bars.tsx")
    check("es gibt sie", os.path.isfile(pfad))
    if not os.path.isfile(pfad):
        return

    quelle = strip_ts(read(pfad))

    check("es gibt UptimeBars", "export function UptimeBars" in quelle)

    # Der Kern: drei Zustaende, nicht zwei.
    check("nicht gemessen ist eine eigene Farbe",
          "!a.known ? GRAU" in quelle,
          "sonst sieht ein Ausfall des Waechters aus wie »lief«")
    # "nicht gemessen" steht auch im Text unter dem Zeiger. Die
    # Legende ist die Stelle, an der Grau ueberhaupt erklaert wird --
    # geprueft wird deshalb das Paar aus Farbe und Wort.
    check("und steht in der Legende",
          '[GRAU, "nicht gemessen"]' in quelle,
          "Grau wird sonst als »egal« gelesen")
    check("Stoerung ist rot", "a.bad ? ROT" in quelle)

    # Ohne Beschriftung ist ein Balken nur ein Farbklecks.
    check("jeder Balken ist beschriftet",
          "aria-label=" in quelle)
    check("und zeigt seinen Zeitraum",
          "function zeitraum(" in quelle)

    check("keine Diagramm-Bibliothek",
          "recharts" not in quelle and "chart.js" not in quelle)


def test_kein_wildwuchs():
    print("\nKeine zweite Farbwelt")

    quelle = strip_ts(read(DASH, "components", "status-live.tsx"))
    balken = strip_ts(read(DASH, "components", "ui", "uptime-bars.tsx"))

    # Die Seite soll aussehen wie der Rest -- nicht wie eine eigene App.
    for datei, name in ((quelle, "status-live"), (balken, "uptime-bars")):
        check(f"{name}: Kartenfarbe der Seite",
              "#131318" in datei or "#0f0f13" in datei)
        check(f"{name}: kein glass", not re.search(r"\bglass\b", datei))
        check(f"{name}: kein rounded-[2rem]", "rounded-[2rem]" not in datei)


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    check("das statusbot-Verzeichnis wurde gefunden", os.path.isdir(STATUS), STATUS)
    if not (os.path.isdir(DASH) and os.path.isdir(STATUS)):
        return 1

    test_der_endpunkt()
    test_die_proxy_route()
    test_die_seite()
    test_der_live_baustein()
    test_die_balken()
    test_kein_wildwuchs()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Die Statusseite lebt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
