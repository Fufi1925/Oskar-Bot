#!/usr/bin/env python3
"""
Der Cookie-Hinweis: Fenster, Nachweis, Admin-Reiter.

Was gebaut wurde
----------------
Ein Hinweisfenster, das beim Betreten der Seite mittig erscheint --
alles dahinter abgedunkelt und unscharf --, mit „Verstanden" und einem
Ausklapper „Details". Jede Bestaetigung wird gespeichert: mit
Discord-Konto, wenn jemand angemeldet ist. Im Admin-Bereich gibt es
dafuer einen eigenen Reiter.

Die Regeln, die hier festgehalten werden
----------------------------------------
  1. **Die Discord-ID kommt aus der Sitzung, nie aus dem Browser.**
     Ein Nachweis, in den jeder eine fremde ID schreiben kann, belegt
     nichts. Der Proxy setzt sie -- und zwar in BEIDEN Faellen: mit
     Sitzung aus der Sitzung, ohne Sitzung auf leer. Der zweite Fall
     ist der leicht zu uebersehende: der Ueberschreib-Block lief
     frueher nur MIT `actorId`, und ohne Anmeldung rutschte ein
     mitgeschicktes `user_id` unveraendert durch.
  2. **Eine Zeile pro Browser, nicht eine pro Klick.**
  3. **Abmelden loescht die bekannte Discord-ID nicht.** Sonst reicht
     ein Abmelden und ein Neuladen, und der Nachweis verliert genau die
     Angabe, wegen der er interessant ist.
  4. **Keine IP-Adresse, kein User-Agent.** Die Datenschutzerklaerung
     sagt zu, dass keine IP-Adressen zu Analysezwecken verarbeitet
     werden. Eine Spalte, die dem widerspricht, gehoert nicht in die
     Datenbank -- auch nicht „fuer spaeter".
  5. **Die Cookie-Liste steht EINMAL.** Fenster und
     Datenschutzerklaerung lesen dieselbe Quelle; zwei Listen liefen
     auseinander, und dann sind beide Angaben belegbar falsch.
  6. **Erst messen, dann anzeigen.** Ohne den `bereit`-Zustand blitzt
     das Fenster bei jedem Aufruf kurz auf, auch bei jemandem, der es
     laengst weggeklickt hat.
  7. **Das Speichern haelt das Schliessen nicht auf.** Ein
     Hinweisfenster, das sich nicht schliessen laesst, weil ein
     Protokolleintrag scheitert, ist schlimmer als ein fehlender
     Protokolleintrag.
  8. **Ein Klick daneben bestaetigt nicht.** Man klickt daneben, weil
     man wegwischen will, nicht als Zustimmung.

Run:  python3 tests/test_cookie_hinweis.py
"""

import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []

KONTO = "1303627964734246944"
A = "0f8fad5b-d9cb-469f-a165-70867728950e"
B = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


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

    Reihenfolge: ERST die Zeilenkommentare, DANN die Bloecke. Steht ein
    Pfad mit Sternchen in einem //-Kommentar, eroeffnet das darin
    enthaltene /* sonst einen Schein-Block, der den halben Quelltext
    verschluckt.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def entkette(src: str) -> str:
    """`"a" + "b"` zu `"ab"` -- sonst scheitert jede Prosa-Suche."""
    return re.sub(r'"\s*\+\s*"', "", src)


# ══════════════════════════════════════════════════════════════════════
#  1. Der Speicher, gegen echte SQLite
# ══════════════════════════════════════════════════════════════════════


def test_speicher():
    print("\nDer Speicher haelt sich an seine Regeln")

    arbeit = tempfile.mkdtemp()
    vorher = os.getcwd()
    os.chdir(arbeit)
    try:
        from utils import cookie_consent as store

        # Frisch: das Modul kann in einem anderen Test schon gelaufen
        # sein, und dann zeigt DB_PATH auf einen anderen Ordner.
        store.ensure()
        with store._connect() as conn:
            conn.execute("DELETE FROM cookie_consents")

        check("eine Bestaetigung wird angenommen", store.record(A)["ok"])
        check("und ist wiederfindbar", store.get(A) is not None)

        # Regel 2: eine Zeile pro Browser.
        store.record(A)
        store.record(A)
        check("dreimal bestaetigt = eine Zeile", len(store.list_all()) == 1,
              str(len(store.list_all())))
        check("der Zaehler steht auf 3", store.get(A)["anzahl"] == 3,
              str(store.get(A)["anzahl"]))

        # Regel 3: Abmelden loescht das Konto nicht.
        store.record(A, user_id=KONTO, user_name="Fufi")
        store.record(A, user_id="", user_name="")
        check("Abmelden loescht die Discord-ID NICHT",
              store.get(A)["user_id"] == KONTO,
              store.get(A)["user_id"])
        # Der Name gehoert zum Nachweis: ohne ihn steht im
        # Admin-Bereich eine nackte Zahl, und die Zeile ist genau so
        # wertvoll wie eine ohne Konto. Zwei Zeilen im Speicher
        # regeln das getrennt -- also braucht es zwei Pruefungen.
        check("und den Namen ebensowenig",
              store.get(A)["user_name"] == "Fufi",
              store.get(A)["user_name"])

        # Eine erfundene Kennung darf nicht landen.
        for schrott in ("", "abc", "'; DROP TABLE cookie_consents; --", "0f8fad5b"):
            check(f"{schrott[:24]!r} wird abgewiesen",
                  not store.record(schrott)["ok"])
        check("und nichts davon gelandet", len(store.list_all()) == 1)

        # Eine erfundene Konto-ID ebenso.
        store.record(B, user_id="keine-zahl")
        check("eine nicht-numerische Konto-ID wird verworfen",
              store.get(B)["user_id"] == "", store.get(B)["user_id"])

        # Die IDs muessen Zeichenketten sein: eine Discord-ID ist
        # groesser als Number.MAX_SAFE_INTEGER.
        check("die Discord-ID ist eine Zeichenkette",
              isinstance(store.get(A)["user_id"], str))

        # Loeschen, beide Wege.
        store.record(B, user_id=KONTO)
        check("Konto-Loeschung nimmt alle Zeilen des Kontos",
              store.delete_for_user(KONTO) == 2)
        check("danach ist die Tabelle leer", len(store.list_all()) == 0)

        # Zu alte Zeilen fliegen raus.
        store.record(A)
        alt = int(time.time()) - (store.KEEP_DAYS + 5) * 86400
        with store._connect() as conn:
            conn.execute(
                "UPDATE cookie_consents SET zuletzt_at = ? WHERE besucher_id = ?",
                (alt, A),
            )
        store.aufraeumen()
        check("zu alte Zeilen werden entfernt", store.get(A) is None)

        # Die Tageskurve zaehlt NEUE Bestaetigungen.
        with store._connect() as conn:
            conn.execute("DELETE FROM cookie_consents")
        store.record(A)
        store.record(A)
        store.record(A)
        kurve = store.per_day(7)
        check("die Kurve hat sieben Punkte", len(kurve) == 7, str(len(kurve)))
        check("ein Wiederkehrer zaehlt nur einmal",
              sum(p["anzahl"] for p in kurve) == 1,
              str([p["anzahl"] for p in kurve]))
        check("Luecken stehen als 0 drin, nicht als fehlender Punkt",
              all("anzahl" in p for p in kurve))

        # Und zwar am Tag der ERSTEN Bestaetigung, nicht der letzten.
        # Blosse Summen merken den Unterschied nicht: bei einem
        # Browser, der heute wiederkommt, ist die Summe in beiden
        # Faellen 1 -- nur der Balken sitzt woanders. Genau daran ist
        # die Mutation vorbeigekommen.
        with store._connect() as conn:
            conn.execute("DELETE FROM cookie_consents")
        store.record(B)
        vor_drei_tagen = int(time.time()) - 3 * 86400
        with store._connect() as conn:
            conn.execute(
                "UPDATE cookie_consents SET zuerst_at = ? WHERE besucher_id = ?",
                (vor_drei_tagen, B),
            )
        store.record(B)  # heute wieder da
        kurve = store.per_day(7)
        check("der Balken steht am Tag der ERSTEN Bestaetigung",
              kurve[-4]["anzahl"] == 1,
              f"steht bei {[p['anzahl'] for p in kurve]}")
        check("und heute steht nichts",
              kurve[-1]["anzahl"] == 0,
              "sonst wandert jeder Wiederkehrer taeglich in die Kurve")
    finally:
        os.chdir(vorher)


def test_ensure_ruestet_nach():
    """CREATE TABLE IF NOT EXISTS aendert an einer bestehenden nichts."""
    print("\nFehlende Spalten werden nachgeruestet")

    arbeit = tempfile.mkdtemp()
    vorher = os.getcwd()
    os.chdir(arbeit)
    try:
        from utils import cookie_consent as store

        store.ensure()
        with store._connect() as conn:
            conn.execute("DROP TABLE cookie_consents")
            conn.execute(
                "CREATE TABLE cookie_consents ("
                " besucher_id TEXT PRIMARY KEY, user_id TEXT)"
            )
        store.ensure()

        with store._connect() as conn:
            vorhanden = {
                row[1] for row in conn.execute("PRAGMA table_info(cookie_consents)")
            }
        fehlend = [name for name, _ in store.COLUMNS if name not in vorhanden]
        check("keine Spalte fehlt", not fehlend, str(fehlend))
        check("und danach laesst sich schreiben", store.record(A)["ok"])
    finally:
        os.chdir(vorher)


def test_keine_ip_gespeichert():
    """Regel 4: keine IP, kein User-Agent -- auch nicht als Spalte."""
    print("\nKeine IP-Adresse, kein Browser-Kennzeichen")

    from utils import cookie_consent as store

    spalten = {name for name, _ in store.COLUMNS}
    for verboten in ("ip", "ip_adresse", "ip_address", "user_agent", "useragent",
                     "referer", "referrer"):
        check(f"keine Spalte {verboten!r}", verboten not in spalten)

    # Und die Route darf sie auch nicht aus dem Request ziehen.
    route = strip_ts(read(BOT, "api", "routes", "cookies.py"))
    for verboten in ("request.client", "user-agent", "x-forwarded-for", "referer"):
        check(f"die Route liest kein {verboten!r}",
              verboten.lower() not in route.lower())

    # Die Datenschutzerklaerung sagt es zu -- der Satz muss dastehen.
    privacy = entkette(strip_ts(read_dash("app", "privacy", "page.tsx")))
    # Nur im Cookie-Abschnitt suchen. „Keine IP-Adressen zu Werbe-
    # oder Analysezwecken" steht schon weiter oben und deckte die
    # Pruefung ab: die Zusage im Cookie-Abschnitt konnte
    # verschwinden, ohne dass etwas anschlug.
    abschnitt = privacy.split('<Section title="Cookies">')
    check("es gibt einen Cookie-Abschnitt", len(abschnitt) == 2)
    if len(abschnitt) == 2:
        rumpf = abschnitt[1].split("</Section>")[0]
        check("er sagt die Zusage ausdruecklich",
              "Keine IP-Adresse, kein Browser-Kennzeichen" in rumpf,
              "sonst steht sie nur im allgemeinen Teil")


# ══════════════════════════════════════════════════════════════════════
#  2. Der Proxy: die Discord-ID kommt aus der Sitzung
# ══════════════════════════════════════════════════════════════════════


def test_proxy_setzt_die_id():
    print("\nDie Discord-ID kommt aus der Sitzung, nie aus dem Browser")

    src = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))

    # Der Fall MIT Sitzung.
    treffer = re.search(
        r'segments\[0\]\s*===\s*"cookies"\s*&&\s*segments\[1\]\s*===\s*"consent"\s*\)\s*\{(.*?)\}',
        src, re.S,
    )
    check("es gibt einen Zweig fuer die Bestaetigung", treffer is not None)
    if treffer:
        rumpf = treffer.group(1)
        check("er setzt user_id aus der Sitzung",
              re.search(r"parsed\.user_id\s*=\s*actorId", rumpf) is not None,
              rumpf[:120])
        check("und den Namen ebenso",
              re.search(r"parsed\.user_name\s*=\s*session", rumpf) is not None,
              rumpf[:120])

    # Der Fall OHNE Sitzung -- der leicht zu uebersehende. Der
    # Ueberschreib-Block lief nur mit `actorId`; ohne Anmeldung
    # rutschte ein mitgeschicktes user_id unveraendert durch.
    ohne = re.search(r"if\s*\(\s*body\s*&&\s*!actorId\s*\)\s*\{(.*?)\n    \}", src, re.S)
    check("es gibt einen Zweig fuer den nicht angemeldeten Fall",
          ohne is not None,
          "sonst schreibt sich jeder eine fremde Discord-ID in den Nachweis")
    if ohne:
        rumpf = ohne.group(1)
        check("er leert user_id",
              re.search(r'parsed\.user_id\s*=\s*""', rumpf) is not None,
              rumpf[:150])
        check("er leert den Namen",
              re.search(r'parsed\.user_name\s*=\s*""', rumpf) is not None,
              rumpf[:150])
        check("und wirft einen mitgeschickten actor weg",
              "delete parsed.actor" in rumpf, rumpf[:150])

    # Der Scope selbst: POST /consent offen, alles andere mit Recht.
    scope = re.search(r'if\s*\(scope\s*===\s*"cookies"\)\s*\{(.*?)\n  \}', src, re.S)
    check("der Proxy kennt den Bereich", scope is not None)
    if scope:
        rumpf = scope.group(1)
        check("POST /consent geht ohne Anmeldung",
              re.search(
                  r'request\.method\s*===\s*"POST"\s*&&\s*rest\[0\]\s*===\s*"consent"',
                  rumpf,
              ) is not None,
              "sonst laesst sich das Fenster ohne Login nicht wegklicken")
        check("alles Uebrige verlangt eine Anmeldung",
              "Not signed in." in rumpf, rumpf[:200])
        check("Lesen verlangt team.view",
              '"team.view"' in rumpf, rumpf[:250])
        check("Loeschen verlangt team.assign",
              '"team.assign"' in rumpf, rumpf[:250])

    # Und die Middleware muss die eine Route freigeben, sonst kommt
    # eine Weiterleitung statt einer Antwort.
    mw = strip_ts(read_dash("middleware.ts"))
    check("die Middleware laesst /api/bot/cookies/consent durch",
          "/api/bot/cookies/consent" in mw,
          "sonst bekommt jeder Nichtangemeldete eine Weiterleitung")
    # Und zwar NUR diese, nicht den ganzen Bereich.
    check("aber nicht den ganzen Cookie-Bereich",
          '"/api/bot/cookies"' not in mw and '"/api/bot/cookies/"' not in mw,
          "die Nachweisliste waere sonst offen")


# ══════════════════════════════════════════════════════════════════════
#  3. Das Fenster
# ══════════════════════════════════════════════════════════════════════


def test_fenster():
    print("\nDas Hinweisfenster")

    src = read_dash("components", "cookie-hinweis.tsx")
    code = strip_ts(src)
    text = entkette(src)

    check("es ist eine Client-Komponente", src.lstrip().startswith('"use client"'))
    check("es gibt die Komponente", "export function CookieHinweis" in code)

    # Mittig, abgedunkelt, unscharf -- so wollte es der Nutzer.
    check("es steht mittig", "items-center justify-center" in code, "")
    check("es liegt ueber allem", "fixed inset-0" in code and "z-[100]" in code)
    check("der Hintergrund ist abgedunkelt", "bg-black/70" in code)
    check("und unscharf", "backdrop-blur" in code)

    # Regel 6: erst messen, dann anzeigen.
    check("es gibt einen Bereit-Zustand",
          re.search(r"const \[bereit, setBereit\] = React\.useState\(false\)", code)
          is not None)
    check("ohne Messung wird nichts gezeigt",
          re.search(r"if \(!bereit \|\| !offen\) return null", code) is not None,
          "sonst blitzt das Fenster bei jedem Aufruf kurz auf")

    # Regel 7: das Speichern haelt das Schliessen nicht auf.
    zu = re.search(r"const bestaetigen = React\.useCallback\(\(\) => \{(.*?)\n  \}, ",
                   code, re.S)
    check("es gibt einen Bestaetigen-Weg", zu is not None)
    if zu:
        rumpf = zu.group(1)
        # Reihenfolge: erst merken, dann schliessen, dann melden.
        check("erst wird das Cookie gesetzt",
              rumpf.index("setzeCookie") < rumpf.index("setOffen(false)"),
              "braeche der Browser weg, waere die Bestaetigung verloren")
        check("dann geschlossen",
              rumpf.index("setOffen(false)") < rumpf.index("melden("),
              "sonst haengt das Fenster bei langsamem Netz")
        check("das Melden wird nicht abgewartet",
              "await melden" not in rumpf,
              "ein Serverfehler liesse das Fenster sonst fuer immer stehen")

    # Regel 8: ein Klick daneben bestaetigt nicht.
    hintergrund = re.search(r'className="absolute inset-0 bg-black/70[^"]*"([^>]*)>',
                            code, re.S)
    check("der abgedunkelte Bereich hat keinen Klick-Handler",
          hintergrund is not None and "onClick" not in hintergrund.group(1),
          "ein Klick daneben ist kein Einverstaendnis")

    # Der Nachweis geht raus -- und ohne selbst eine ID zu behaupten.
    melden = re.search(r"const melden = React\.useCallback\(async \(kennung.*?\n  \}, \[\]\);",
                       code, re.S)
    check("es wird gemeldet", melden is not None)
    if melden:
        rumpf = melden.group(0)
        check("an die richtige Adresse",
              '"/api/bot/cookies/consent"' in rumpf, rumpf[:150])
        check("mit keepalive",
              "keepalive: true" in rumpf,
              "wer sofort weiterklickt, braeche die Anfrage sonst selbst ab")
        check("das Fenster behauptet selbst KEINE Discord-ID",
              "user_id" not in rumpf,
              "die haengt der Proxy aus der Sitzung an")
        check("das Cookie gilt erst nach einer Antwort als fertig",
              rumpf.index("if (!antwort.ok) return false;")
              < rumpf.index("setzeCookie(HINWEIS_COOKIE, HINWEIS_VERSION"),
              "sonst gilt ein fehlgeschlagener Versuch als erledigt")

    # Ein fehlgeschlagener Versuch wird nachgeholt.
    check("ein offener Nachweis wird spaeter nachgetragen",
          "OFFEN_SUFFIX" in code and "stand.endsWith(OFFEN_SUFFIX)" in code,
          "sonst geht die Bestaetigung bei einem Netzfehler verloren")

    # Und die Anmeldung traegt das Konto nach.
    check("nach dem Anmelden wird das Konto nachgetragen",
          "session?.user" in code and "void melden(kennung)" in code,
          "sonst traegt der Nachweis nie eine Discord-ID")

    # Tastatur.
    check("Escape schliesst", 'ereignis.key === "Escape"' in code)
    check("der Fokus wandert ins Fenster", "knopf.current?.focus()" in code)
    check("und bleibt darin gefangen",
          "letztes.focus()" in code and "erstes.focus()" in code,
          "sonst tabbt man durch die gesperrte Seite dahinter")
    check("es ist als Dialog ausgezeichnet",
          'role="dialog"' in code and 'aria-modal="true"' in code)
    check("das Scrollen dahinter wird gesperrt",
          'document.body.style.overflow = "hidden"' in code)
    check("und danach wieder freigegeben",
          "document.body.style.overflow = vorher" in code,
          "sonst laesst sich die Seite nach dem Schliessen nicht scrollen")

    # Die zwei Knoepfe, die der Nutzer wollte.
    check("es gibt »Verstanden«", ">\n            Verstanden\n          </button>" in src
          or "Verstanden" in text)
    check("es gibt »Details«", "Details" in text)
    check("es gibt KEINEN Ablehnen-Knopf",
          not re.search(r">\s*Ablehnen\s*<", src),
          "er koennte nichts abschalten, ohne die Anmeldung mit abzuschalten")

    # Deutsche Anfuehrungszeichen duerfen den Build nicht brechen.
    check("keine geraden Anfuehrungszeichen als Schlusszeichen im JSX",
          '„' not in src or '“' in src or '"' not in src.split("„")[-1][:80],
          "„…\" bricht den Build")


def test_fenster_haengt_im_layout():
    print("\nDas Fenster gilt fuer jede Seite")

    layout = strip_ts(read_dash("app", "layout.tsx"))
    check("es ist eingebunden", "<CookieHinweis />" in layout,
          "sonst erscheint es nirgends")
    check("und importiert",
          "@/components/cookie-hinweis" in layout)

    # Es liest die Sitzung, muss also INNERHALB des Providers stehen.
    vor = layout.index("<AuthProvider>")
    nach = layout.index("</AuthProvider>")
    stelle = layout.index("<CookieHinweis />")
    check("innerhalb von AuthProvider", vor < stelle < nach,
          "useSession() ausserhalb waere ein Fehler beim Rendern")


# ══════════════════════════════════════════════════════════════════════
#  4. Die Cookie-Liste steht einmal
# ══════════════════════════════════════════════════════════════════════


def test_liste_einmal():
    print("\nDie Cookie-Liste steht an genau einer Stelle")

    lib = read_dash("lib", "cookie-consent.ts")
    code = strip_ts(lib)
    fenster = strip_ts(read_dash("components", "cookie-hinweis.tsx"))
    privacy = strip_ts(read_dash("app", "privacy", "page.tsx"))

    check("es gibt die gemeinsame Liste", "export const COOKIES" in code)
    check("das Fenster liest sie", "COOKIES" in fenster
          and "@/lib/cookie-consent" in fenster)
    check("die Datenschutzerklaerung auch", "COOKIES" in privacy
          and "@/lib/cookie-consent" in privacy,
          "zwei Listen laufen auseinander")

    # Und sie muss wirklich gerendert werden, nicht nur importiert.
    check("die Datenschutzerklaerung rendert sie",
          re.search(r"COOKIES\.map\(", privacy) is not None,
          "importiert und nicht benutzt waere dasselbe wie gar nicht")
    check("das Fenster rendert sie",
          re.search(r"COOKIES\.map\(", fenster) is not None)

    # Jedes gelistete Cookie muss es wirklich geben.
    namen = re.findall(r'name:\s*"([^"]+)"', code)
    namen += [
        "ub_cookie_hinweis" if "HINWEIS_COOKIE" in zeile else "ub_besucher"
        for zeile in re.findall(r"name:\s*(HINWEIS_COOKIE|BESUCHER_COOKIE)", code)
    ]
    check("es sind mehrere Cookies gelistet", len(namen) >= 5, str(namen))

    auth = read_dash("lib", "auth.ts")
    wartung = read_dash("lib", "maintenance.ts")
    zusammen = auth + wartung + lib

    for cookie in namen:
        if cookie.startswith("next-auth."):
            # NextAuth setzt die selbst; nachweisbar ist die Strategie.
            check(f"{cookie}: NextAuth ist im Einsatz",
                  "next-auth" in auth or "NextAuth" in auth or "authOptions" in auth)
            continue
        if cookie == "wartung_bypass":
            check("wartung_bypass steht wirklich im Code",
                  'BYPASS_COOKIE = "wartung_bypass"' in wartung, "")
            continue
        check(f"{cookie} steht wirklich im Code", cookie in zusammen, "")

    # Die Laufzeit im Fenster darf nicht in Versalien stehen: „30 TAGE"
    # ist etwas anderes als die „30 Tage" der Datenschutzerklaerung.
    # Im Browser aufgefallen, nicht im Quelltext.
    dauer = re.search(r"\{eintrag\.dauer\}", fenster)
    check("die Laufzeit wird gezeigt", dauer is not None)
    if dauer:
        umgebung = fenster[max(0, dauer.start() - 260):dauer.start()]
        # Nur der letzte <span> davor zaehlt.
        letzter = umgebung.rsplit("<span", 1)[-1]
        check("und zwar ohne Versalien", "uppercase" not in letzter,
              "sonst steht dort »30 TAGE« statt »30 Tage«")


def test_sitzungsdauer_stimmt():
    """Die genannte Laufzeit muss die echte sein."""
    print("\nDie genannten Laufzeiten stimmen")

    lib = strip_ts(read_dash("lib", "cookie-consent.ts"))
    auth = strip_ts(read_dash("lib", "auth.ts"))
    wartung = strip_ts(read_dash("lib", "maintenance.ts"))

    # NextAuth: maxAge: 30 * 24 * 60 * 60
    echt = re.search(r"maxAge:\s*(\d+)\s*\*\s*24\s*\*\s*60\s*\*\s*60", auth)
    check("die Sitzungsdauer steht im Code", echt is not None)
    if echt:
        tage = int(echt.group(1))
        eintrag = re.search(
            r'name:\s*"next-auth\.session-token".*?dauer:\s*"([^"]+)"', lib, re.S
        )
        check("und wird richtig genannt",
              eintrag is not None and str(tage) in eintrag.group(1),
              f"Code sagt {tage} Tage, die Liste sagt "
              f"{eintrag.group(1) if eintrag else '—'}")

    # Wartung: BYPASS_MAX_AGE = 60 * 60 * 8
    echt = re.search(r"BYPASS_MAX_AGE\s*=\s*60\s*\*\s*60\s*\*\s*(\d+)", wartung)
    check("die Wartungsdauer steht im Code", echt is not None)
    if echt:
        stunden = int(echt.group(1))
        eintrag = re.search(
            r'name:\s*"wartung_bypass".*?dauer:\s*"([^"]+)"', lib, re.S
        )
        check("und wird richtig genannt",
              eintrag is not None and str(stunden) in eintrag.group(1),
              f"Code sagt {stunden} Stunden, die Liste sagt "
              f"{eintrag.group(1) if eintrag else '—'}")

    # Der Nachweis muss die Bestaetigung ueberdauern, nicht umgekehrt.
    from utils import cookie_consent as store

    browser_tage = re.search(r"HINWEIS_TAGE\s*=\s*(\d+)", lib)
    check("die Browser-Laufzeit steht im Code", browser_tage is not None)
    if browser_tage:
        check("der Nachweis haelt laenger als die Bestaetigung",
              store.KEEP_DAYS > int(browser_tage.group(1)),
              f"Nachweis {store.KEEP_DAYS} Tage, Cookie {browser_tage.group(1)} Tage")


# ══════════════════════════════════════════════════════════════════════
#  5. Der Admin-Reiter
# ══════════════════════════════════════════════════════════════════════


def test_admin_reiter():
    print("\nDer Admin-Reiter")

    admin = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))

    check("der Reiter ist in der Liste",
          re.search(r'\{ id: "cookies", label: "[^"]+", icon: \w+ \}', admin)
          is not None)
    check("er steht in einer Gruppe",
          re.search(r'ids:\s*\[[^\]]*"cookies"', admin) is not None,
          "ohne Gruppe verschwindet er ganz aus der Leiste")
    check("er ist im TabId-Typ", '| "cookies"' in admin)
    check("er rendert ueber die volle Breite",
          re.search(r'FULL_WIDTH_TABS[^;]*"cookies"', admin, re.S) is not None)
    check("er wird gerendert",
          'activeTab === "cookies" && <CookieConsentsPanel />' in admin,
          "sonst ist der Reiter da und der Inhalt leer")
    check("und das Panel ist importiert",
          "@/components/dashboard/cookie-consents-panel" in admin)

    # Das Recht muss zu dem passen, was der Proxy verlangt. Steht hier
    # weniger, ist der Reiter sichtbar und gibt beim Klick nur eine
    # Fehlermeldung -- genau der Fall »Nutzer suchen«.
    block = re.search(r"const TAB_PERMISSION[^=]*=\s*\{(.*?)\n  \};", admin, re.S)
    check("es gibt die Rechte-Zuordnung", block is not None)
    if block:
        zuordnung = dict(re.findall(r'^\s*(\w+):\s*"([^"]+)"', block.group(1), re.M))
        check("der Reiter verlangt team.view",
              zuordnung.get("cookies") == "team.view",
              f"steht auf {zuordnung.get('cookies')!r}")

        # Und das Recht muss es wirklich geben.
        from utils import dashboard_roles as dr

        check("team.view ist ein echtes Recht",
              "team.view" in dr.PERMISSIONS_BY_KEY)


def test_admin_panel():
    print("\nDas Panel selbst")

    src = read_dash("components", "dashboard", "cookie-consents-panel.tsx")
    code = strip_ts(src)
    text = entkette(src)

    check("es ist eine Client-Komponente", src.lstrip().startswith('"use client"'))
    check("es gibt die Komponente", "export function CookieConsentsPanel" in code)

    # Der Admin-Bereich hat einen Stil: #131318, slate-800, kein
    # Rand-Schimmer. Das steht so in test_admin_stil.py.
    check("die Karten tragen die Farbe des Bereichs", "bg-[#131318]" in code)
    check("und den Rand", "border-slate-800" in code)
    check("kein Rand-Schimmer", "border-glow-card" not in code,
          "der Admin-Bereich hat bewusst keinen")
    check("kein Glas-Stil",
          not re.search(r"\bglass\b", code) and "rounded-[2rem]" not in code)

    # Beide Loeschwege.
    check("eine einzelne Zeile laesst sich loeschen",
          "api.cookieConsentDelete(" in code)
    check("und alles zu einem Konto",
          "api.cookieConsentDeleteUser(" in code)
    # Nicht zaehlen, sondern die Wirkung pruefen: `false && !confirm(...)`
    # laesst die Zeile stehen und fragt trotzdem nie. Gesucht ist die
    # Form `if (\n !confirm(` -- der Rueckzieher, wenn jemand abbricht.
    rueckzieher = re.findall(r"if\s*\(\s*\n\s*!confirm\(", code)
    check("beides fragt vorher nach -- und bricht wirklich ab",
          len(rueckzieher) >= 2,
          f"nur {len(rueckzieher)} echte Abfragen; ein Nachweis ist "
          "sonst mit einem Klick weg")
    # Nur im Rumpf von `kontoLoeschen` suchen. „Art. 17" steht auch im
    # Docstring der Datei UND im title-Tooltip des Knopfes -- zwei
    # Stellen, die die Pruefung nacheinander abgedeckt haben, waehrend
    # der Satz im Bestaetigungsdialog verschwinden konnte. Ein Tooltip
    # ersetzt ihn nicht: er erscheint erst beim Verweilen, der Dialog
    # steht vor dem Klick, der die Zeilen wirklich loescht.
    dialog = re.search(
        r"const kontoLoeschen = async \(row: ConsentRow\) => \{(.*?)\n    setBusy\(",
        code, re.S,
    )
    check("der Konto-Weg fragt in einem eigenen Dialog nach", dialog is not None)
    if dialog:
        check("und nennt darin den Rechtsgrund",
              "Art. 17" in entkette(dialog.group(1)),
              "sonst weiss niemand, wofuer der zweite Knopf da ist")
    check("der Konto-Knopf erscheint nur bei Angemeldeten",
          "row.angemeldet ?" in code or "row.angemeldet &&" in code)

    # Der Verlauf.
    check("es gibt ein Diagramm", "<LineChart" in code)
    check("mit waehlbarem Zeitraum",
          "setTage(" in code and "90 Tage" in text)
    check("die Ueberschrift sagt, was gezaehlt wird",
          "Neue Bestätigungen pro Tag" in text,
          "sonst haelt man es fuer Besuche")

    # Zahlen auf einer deutschen Seite.
    check("die Zahlen sind deutsch formatiert",
          'toLocaleString("de-DE")' in code,
          "toFixed() liefert immer einen Punkt")

    # Und der Hinweis, was NICHT gespeichert wird.
    # Wieder im gestrippten Code: der Docstring nennt die IP dreimal.
    check("das Panel sagt, was nicht gespeichert wird",
          "keine IP-Adresse" in entkette(code),
          "sonst vermutet jeder, es stuende doch eine drin")

    # Feste Spaltenbreiten: mit `min-w` richtete sich jede Zeile nach
    # ihrem eigenen Inhalt und die Tabelle stand schief. Im Browser
    # aufgefallen.
    check("die Zeitspalte hat eine feste Breite",
          re.search(r'w-\[\d+px\] shrink-0 text-\[12px\] tabular-nums', code)
          is not None,
          "sonst springen die Spalten von Zeile zu Zeile")
    check("die Knopfspalte auch",
          re.search(r'flex w-\[\d+px\] shrink-0 items-center justify-end', code)
          is not None)


def test_api_anbindung():
    print("\nDie Anbindung im Dashboard")

    api = strip_ts(read_dash("lib", "api.ts"))

    for name, pfad in (
        ("cookieConsents", "/cookies/consents"),
        ("cookieConsentStats", "/cookies/consents/stats"),
        ("cookieConsentDelete", "/cookies/consents/"),
        ("cookieConsentDeleteUser", "/cookies/consents/user"),
    ):
        check(f"{name} ist da", f"{name}:" in api)
        check(f"{name} zeigt auf {pfad}", pfad in api)

    # `.*?` mit re.S lief bis zum naechsten DELETE irgendwo weiter
    # unten in der Datei -- die Pruefung blieb gruen, obwohl bei
    # cookieConsentDelete gar keine Methode mehr stand. Deshalb nur
    # bis zum naechsten Eintrag suchen.
    zeile = re.search(r"cookieConsentDelete:(.*?)\n  \w+:", api, re.S)
    check("cookieConsentDelete ist abgegrenzt gefunden", zeile is not None)
    if zeile:
        check("das Loeschen einer Zeile ist ein DELETE",
              re.search(r'method:\s*"DELETE"', zeile.group(1)) is not None,
              zeile.group(1)[:120])


# ══════════════════════════════════════════════════════════════════════
#  6. Die Route im Bot
# ══════════════════════════════════════════════════════════════════════


def test_route_haengt_im_server():
    print("\nDie Route ist eingehaengt")

    server = read(BOT, "api", "server.py")
    code = re.sub(r"^\s*#.*$", "", server, flags=re.M)

    check("das Modul ist importiert",
          re.search(r"from api\.routes import[^\n]*\bcookies\b", code) is not None,
          "ohne Import gibt es die Route nicht")
    check("und eingehaengt",
          re.search(r'cookies\.router,\s*prefix="/cookies"', code) is not None)

    # NICHT unter /admin: dort laesst der Proxy nur Angemeldete durch.
    check("nicht unter /admin",
          re.search(r'cookies\.router,\s*prefix="/admin', code) is None,
          "die Bestaetigung kommt von der oeffentlichen Startseite")


def test_route_gegen_echtes_http():
    """Die Route wirklich aufrufen, nicht nur lesen."""
    print("\nDie Route, gegen echtes HTTP")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as exc:  # noqa: BLE001
        check("FastAPI ist da", False, str(exc))
        return

    arbeit = tempfile.mkdtemp()
    vorher = os.getcwd()
    os.chdir(arbeit)
    try:
        from api.routes import cookies
        from utils import cookie_consent as store

        store.ensure()
        with store._connect() as conn:
            conn.execute("DELETE FROM cookie_consents")

        app = FastAPI()
        app.include_router(cookies.router, prefix="/cookies")
        client = TestClient(app)

        antwort = client.post("/cookies/consent", json={"besucher_id": A})
        check("bestaetigen -> 200", antwort.status_code == 200, antwort.text)

        antwort = client.post("/cookies/consent", json={"besucher_id": "abc"})
        check("kaputte Kennung -> 400", antwort.status_code == 400,
              str(antwort.status_code))

        antwort = client.get("/cookies/consents")
        check("die Liste -> 200", antwort.status_code == 200)
        check("und enthaelt den Eintrag",
              len(antwort.json()["consents"]) == 1, antwort.text[:200])

        # Die Discord-ID muss als Zeichenkette durch JSON gehen.
        client.post("/cookies/consent",
                    json={"besucher_id": B, "user_id": KONTO})
        roh = client.get("/cookies/consents").text
        check("die Discord-ID kommt als Zeichenkette an",
              f'"user_id":"{KONTO}"' in roh.replace(" ", ""),
              roh[:200])

        antwort = client.delete(f"/cookies/consents/{B}")
        check("loeschen -> 200", antwort.status_code == 200, antwort.text)
        antwort = client.delete(f"/cookies/consents/{B}")
        check("zweites Mal -> 404", antwort.status_code == 404,
              str(antwort.status_code))

        antwort = client.post("/cookies/consents/user", json={"user_id": "keine-zahl"})
        check("erfundene Konto-ID -> 400", antwort.status_code == 400,
              str(antwort.status_code))
    finally:
        os.chdir(vorher)


# ══════════════════════════════════════════════════════════════════════
#  7. Der Speicher liegt auf dem Volume
# ══════════════════════════════════════════════════════════════════════


def test_liegt_auf_dem_volume():
    print("\nDie Datei liegt dort, wo sie einen Deploy ueberlebt")

    from utils import cookie_consent as store

    check("die Datenbank liegt unter db/",
          store.DB_PATH.replace("\\", "/").startswith("db/"),
          store.DB_PATH)

    # Und die Anleitung muss sie nennen -- ein Volume, das niemand
    # anlegt, ist kein Volume.
    doku = read(ROOT, "RAILWAY_DEPLOYMENT.md")
    check("die Deploy-Anleitung nennt sie",
          "cookie_consent.db" in doku,
          "sonst weiss niemand, dass der Nachweis ein Volume braucht")


def main() -> int:
    test_speicher()
    test_ensure_ruestet_nach()
    test_keine_ip_gespeichert()
    test_proxy_setzt_die_id()
    test_fenster()
    test_fenster_haengt_im_layout()
    test_liste_einmal()
    test_sitzungsdauer_stimmt()
    test_admin_reiter()
    test_admin_panel()
    test_api_anbindung()
    test_route_haengt_im_server()
    test_route_gegen_echtes_http()
    test_liegt_auf_dem_volume()

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
