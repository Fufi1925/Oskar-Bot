#!/usr/bin/env python3
"""
Premium soll man SEHEN -- drei Stellen.

  1. Das goldene Fenster kommt alle sieben Tage wieder, nicht nur
     einmal. Geprueft wird das Verhalten ueber die Zeit, indem der
     gespeicherte Zeitpunkt zurueckgedreht wird.
  2. Unten links in der Seitenleiste steht, ob man Premium hat --
     neben der Team-Rolle, nicht statt ihr.
  3. Der Admin-Reiter zeigt KONTEN statt Keys.

Run:  python3 tests/test_premium_sichtbar.py
"""

import os
import re
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
START = os.getcwd()
sys.path.insert(0, BOT)

fehler: list[str] = []


def pruefe(name, ok, hinweis=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        fehler.append(name)


def linie(t):
    print()
    print("=" * 66)
    print(t)
    print("=" * 66)


def lies(*teile):
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare.

    Andersherum frisst der Blockausdruck ein `// ... */`. Das
    `(?<!:)` schuetzt `https://`.
    """
    ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


def entkette(src: str) -> str:
    """`"abc" + "def"` zu `"abcdef"` -- sonst scheitert Prosa-Suche."""
    return re.sub(r'"\s*\+\s*"', "", src)


# ══════════════════════════════════════════════════════════════════════
#  1. Das Fenster alle sieben Tage
# ══════════════════════════════════════════════════════════════════════


def test_fenster_kommt_wieder():
    linie("1  Das Fenster kommt alle sieben Tage")

    arbeit = tempfile.mkdtemp(prefix="sichtbar-")
    os.chdir(arbeit)
    os.makedirs("db", exist_ok=True)

    from utils import premium_notice as pn

    pruefe("der Abstand ist sieben Tage", pn.ABSTAND_TAGE == 7,
           str(pn.ABSTAND_TAGE))

    A = "1303627964734246944"

    def zurueckdrehen(tage):
        with sqlite3.connect(pn.DB_PATH) as conn:
            conn.execute(
                "UPDATE premium_notice SET gesehen_at = ? WHERE user_id = ?",
                (int(time.time()) - int(tage * 86400), A),
            )

    pruefe("beim ersten Premium erscheint es",
           pn.zustand(A, True)["zeigen"] is True)

    pn.als_gesehen(A)
    pruefe("nach dem Wegklicken ist Ruhe",
           pn.zustand(A, True)["zeigen"] is False)

    # Mehrere Seitenaufrufe duerfen nichts aendern.
    for _ in range(5):
        pn.zustand(A, True)
    pruefe("auch nach fuenf Aufrufen",
           pn.zustand(A, True)["zeigen"] is False)

    zurueckdrehen(6)
    pruefe("sechs Tage reichen nicht",
           pn.zustand(A, True)["zeigen"] is False,
           "sonst kaeme es zu frueh")

    zurueckdrehen(7)
    pruefe("nach sieben Tagen kommt es wieder",
           pn.zustand(A, True)["zeigen"] is True,
           "genau das war vorher nicht so -- es kam nur einmal")

    # Und der Zyklus laeuft weiter.
    pn.als_gesehen(A)
    pruefe("danach wieder Ruhe", pn.zustand(A, True)["zeigen"] is False)
    zurueckdrehen(8)
    pruefe("und acht Tage spaeter erneut",
           pn.zustand(A, True)["zeigen"] is True)

    # Ohne Premium bleibt es weg -- egal wie lange her.
    B = "1033826242270609449"
    pn.zustand(B, True)
    pn.als_gesehen(B)
    with sqlite3.connect(pn.DB_PATH) as conn:
        conn.execute(
            "UPDATE premium_notice SET gesehen_at = ? WHERE user_id = ?",
            (int(time.time()) - 90 * 86400, B),
        )
    pruefe("ohne Premium kein Fenster",
           pn.zustand(B, False)["zeigen"] is False)

    # Nach Entzug und Neuvergabe sofort, nicht erst in sieben Tagen.
    z = pn.zustand(B, True)
    pruefe("nach einer Rueckkehr sofort", z["zeigen"] is True)
    pruefe("und als Rueckkehr gekennzeichnet", z["rueckkehr"] is True,
           "der alte Abstand darf das nicht aufhalten")

    # Alte Zeilen ohne die neue Spalte.
    C = "999888777666555444"
    pn.zustand(C, True)
    pn.als_gesehen(C)
    with sqlite3.connect(pn.DB_PATH) as conn:
        conn.execute(
            "UPDATE premium_notice SET gesehen_at = 0 WHERE user_id = ?", (C,)
        )
    pruefe("eine Zeile ohne Zeitpunkt gilt als faellig",
           pn.zustand(C, True)["zeigen"] is True,
           "lieber einmal zu viel als eine, die nie wieder meldet")

    os.chdir(START)


def test_fenster_nur_im_dashboard():
    linie("2  Das Fenster nur im Dashboard")

    quelle = entkette(strip_ts(lies("components", "premium-hinweis.tsx")))

    pruefe("es liest den Pfad", "usePathname()" in quelle)
    # Auf die WIRKUNG zielen: der Abbruch muss wirklich passieren.
    pruefe("und bricht ausserhalb ab",
           re.search(r"if \(!imDashboard\) return;", quelle) is not None,
           "sonst erscheint es auch im Impressum")
    pruefe("die Bedingung haengt am Pfad",
           'pathname?.startsWith("/dashboard")' in quelle)
    # Der Abstand darf NICHT im Frontend stehen -- zwei Stellen mit
    # derselben Zahl laufen auseinander.
    pruefe("der Abstand steht nicht doppelt im Browser",
           "7 * 24" not in quelle and "ABSTAND" not in quelle,
           "die Entscheidung gehoert auf den Server")


# ══════════════════════════════════════════════════════════════════════
#  3. Das Abzeichen in der Seitenleiste
# ══════════════════════════════════════════════════════════════════════


def test_abzeichen_in_der_seitenleiste():
    linie("3  Premium und Rolle unten links")

    quelle = strip_ts(lies("app", "dashboard", "layout.tsx"))

    pruefe("der Premium-Zustand wird geladen",
           "api.getMyPremium(userId)" in quelle)
    pruefe("und in den Zustand geschrieben", "setPremium({" in quelle)
    # Die Funktion muss auch AUFGERUFEN werden.
    #
    # Ohne diese Zeile stuende die Definition da und liefe nie --
    # das Abzeichen bliebe fuer immer aus. Der Mutationstest hat
    # genau das durchgelassen.
    pruefe("und die Abfrage laeuft wirklich",
           re.search(r"^\s*fetchPremium\(\);", quelle, re.M) is not None,
           "eine definierte, nie gerufene Funktion tut nichts")

    # Auf die Wirkung: das Abzeichen muss an `premium.aktiv` haengen.
    #
    # Den KNOPF-Block isolieren, nicht die Datei durchsuchen.
    # `premium?.aktiv &&` steht zweimal -- einmal am Abzeichen, einmal
    # an der Zeile darunter. Eine Mutation, die nur eins ersetzt,
    # bliebe sonst unbemerkt: nachgemessen im Mutationstest.
    # Rueckwaerts vom Abzeichen zur Bedingung: das JSX davor sucht
    # sich schlecht vorwaerts, weil `strip_ts` aus einem
    # JSX-Kommentar ein leeres `{}` macht und ein `[^{}]`-Ausdruck
    # daran haengenbleibt. Nachgemessen.
    abzeichen = re.search(
        r"(\{[^\n]*&& \()\s*\n\s*<span\s*\n\s*className=\"ml-auto",
        quelle,
    )
    pruefe("das Abzeichen ist auffindbar", abzeichen is not None)
    if abzeichen:
        pruefe("das Abzeichen haengt am Zustand",
               "premium?.aktiv" in abzeichen.group(0),
               "sonst steht es auch ohne Premium da")

    # Und die Zeile darunter ebenfalls.
    zeile = re.search(r"\{[^{}]*?\(premium\.probewoche \|\| premium\.tester\)",
                      quelle)
    pruefe("die Zusatzzeile haengt auch daran",
           zeile is not None and "premium?.aktiv" in zeile.group(0),
           "sonst stuende 'Probewoche laeuft' ohne Premium da")

    # Die Team-Rolle bleibt daneben bestehen -- beides gleichzeitig.
    pruefe("die Team-Rolle steht weiterhin da",
           "teamAccess?.is_owner ?" in quelle
           and "teamAccess?.roles?.length ?" in quelle,
           "Premium sagt was man HAT, die Rolle was man DARF")

    # Und im Ausklappmenue oben rechts ebenfalls.
    pruefe("auch im Profilmenue",
           "Premium · Probewoche" in quelle or "premium?.aktiv ||" in quelle,
           "dort steht die Rolle auch")

    # Eine laufende Probewoche muss erkennbar sein: sie endet.
    pruefe("eine Probewoche wird benannt",
           "Probewoche läuft" in quelle,
           "sonst merkt niemand, dass sie ausläuft")

    pruefe("ein Tester-Zugang auch", "Tester-Zugang" in quelle)


# ══════════════════════════════════════════════════════════════════════
#  4. Der Speedrun ist golden, nicht Beta
# ══════════════════════════════════════════════════════════════════════


def test_speedrun_ist_golden():
    linie("4  Der Speedrun ist golden")

    layout = strip_ts(lies("app", "dashboard", "layout.tsx"))
    tabs = strip_ts(lies("components", "guild-tabs.tsx"))

    pruefe("kein „(Beta)“ mehr im Namen",
           "Speedrun (Beta)" not in layout)
    # Den EINTRAG isolieren, dann darin suchen.
    #
    # Ein Ausdruck ueber die ganze Datei findet das `tag: "beta"` des
    # naechsten Eintrags und meldet einen Fehler, den es nicht gibt --
    # in dieser Datei stehen mehrere Beta-Reiter.
    sr = re.search(r'slug: "speedrun",(.*?)\n\s{8}\},', tabs, re.S)
    pruefe("der Speedrun-Eintrag ist auffindbar", sr is not None)
    if sr:
        pruefe("und kein Beta-Zeichen in der Reiterleiste",
               'tag: "beta"' not in sr.group(1),
               "der Speedrun ist Premium, keine Beta")

    # Den Eintrag isolieren -- `[^}]*` bricht am Template-String im
    # href ab, der selbst eine schliessende Klammer enthaelt.
    eintrag = re.search(r'name: "Speedrun",(.*?)\n\s{12}\},', layout, re.S)
    pruefe("der Eintrag ist auffindbar", eintrag is not None)
    if eintrag:
        pruefe("er ist golden markiert",
               "highlight: true" in eintrag.group(1),
               "ohne highlight bleibt er grau wie jeder andere")

    # Und `highlight` muss die Farbe wirklich steuern.
    pruefe("highlight faerbt golden",
           "Boolean((item as any).highlight)" in layout
           and "isPremium" in layout,
           "sonst ist das Feld Zierde")

    # Design traegt dasselbe Feld -- ein Sonderfall, nicht zwei.
    pruefe("Design nutzt dasselbe Feld",
           layout.count("highlight: true") >= 2,
           "Design und Speedrun sollen gleich behandelt werden")


# ══════════════════════════════════════════════════════════════════════
#  5. Der Admin-Reiter zeigt Konten
# ══════════════════════════════════════════════════════════════════════


def test_admin_zeigt_konten():
    linie("5  Der Admin-Reiter zeigt Konten statt Keys")

    quelle = entkette(strip_ts(lies("components", "dashboard",
                                    "premium-admin.tsx")))

    pruefe("er laedt Konten", "api.listPremiumAccounts(" in quelle)
    pruefe("er kann Premium vergeben", "api.grantPremiumAccount(" in quelle)
    pruefe("und entziehen", "api.revokePremiumAccount(" in quelle)

    # Der Entzug ist nicht rueckgaengig zu machen -- Rueckfrage noetig.
    pruefe("mit Rueckfrage vor dem Entzug", "window.confirm(" in quelle)
    pruefe("und der Hinweis nennt beide Bots",
           "auf beiden Bots" in quelle,
           "sonst glaubt man, es betrifft nur einen")

    # „laeuft bald ab" ist die Zahl, wegen der man den Reiter oeffnet.
    # Die Reihenfolge der KACHELN, nicht der Filter-Liste.
    #
    # „Mit Premium" steht auch als Filter-Beschriftung in der Datei,
    # und die kommt frueher. Ein Vergleich ueber die ganze Datei
    # prueft damit etwas anderes als gemeint -- nachgemessen.
    kacheln = re.search(r"<Zahl\b.*?</div>\s*</Reveal>", quelle, re.S)
    pruefe("der Kachel-Block ist auffindbar", kacheln is not None)
    if kacheln:
        block = kacheln.group(0)
        pruefe("„läuft bald ab“ steht zuerst",
               block.index("Läuft bald ab") < block.index("Mit Premium"),
               "das ist die einzige Zahl, bei der man handeln muss")
        pruefe("und ist golden hervorgehoben",
               'ton="gold"' in block,
               "sonst geht sie zwischen vier gleichen Kacheln unter")

    # Die Key-Verwaltung ist erhalten, nur eine Ebene tiefer.
    pruefe("die Keys bleiben erreichbar", "<PremiumKeys />" in quelle)
    pruefe("die Datei dafuer gibt es",
           os.path.isfile(os.path.join(DASH, "components", "dashboard",
                                       "premium-keys.tsx")))

    # Sie duerfen NICHT mehr die Hauptsache sein.
    pruefe("Keys sind zugeklappt",
           re.search(r"\{zeigeKeys && \(", quelle) is not None,
           "neue Keys werden nicht mehr ausgegeben")

    # Und der Reiter selbst darf keine Keys mehr praegen.
    pruefe("der Reiter praegt selbst keine Keys",
           "createPremiumKey" not in quelle,
           "das gehoert in den aufklappbaren Abschnitt")


def test_konten_route():
    linie("6  Die Route dahinter")

    quelle = open(os.path.join(BOT, "api", "routes", "premium.py"),
                  encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    for pfad in ('@router.get("/accounts"',
                 '@router.post("/accounts/grant"',
                 '@router.post("/accounts/revoke"'):
        pruefe(f"{pfad.split(chr(34))[1]} gibt es", pfad in ohne)

    # Ein Entzug muss die Probewoche mitnehmen -- sonst bleibt Premium
    # bestehen, obwohl „entzogen" dasteht.
    rumpf = re.search(r'async def revoke_account.*?\n    return \{', ohne, re.S)
    pruefe("der Rumpf ist auffindbar", rumpf is not None)
    if rumpf:
        pruefe("der Entzug nimmt die Probewoche mit",
               "premium_trial.revoke(user_id)" in rumpf.group(0),
               "sonst bliebe Premium ueber die Probewoche bestehen")
        pruefe("und die Lizenzen", "store.revoke_user(user_id)" in rumpf.group(0))

    # Die Route darf nicht offen sein: sie zeigt jedes Konto.
    proxy = strip_ts(lies("app", "api", "bot", "[...path]", "route.ts"))
    pruefe("die Route ist nur fuer das Team",
           re.search(r'\["keys", "revoke", "delete", "purge", "trials", "accounts"\]',
                     proxy) is not None,
           "sonst liest jeder Angemeldete alle Premium-Konten")


def test_store_fasst_zusammen():
    linie("7  list_accounts fasst je Konto zusammen")

    quelle = open(os.path.join(BOT, "utils", "premium_store.py"),
                  encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    pruefe("es gibt list_accounts", "def list_accounts(" in ohne)

    fn = re.search(r"def list_accounts\(.*?\n    return ergebnis", ohne, re.S)
    pruefe("der Rumpf ist auffindbar", fn is not None)
    if fn:
        koerper = fn.group(0)
        pruefe("zusammengefasst wird nach dem Konto",
               "konten.setdefault(wer" in koerper,
               "sonst steht eine Person mit drei Keys dreimal da")
        pruefe("die Probewochen zaehlen mit",
               "premium_trial.list_all" in koerper,
               "sonst fehlen genau die Konten, bei denen etwas ablaeuft")
        pruefe("widerrufene Zeilen geben kein Premium",
               'if row["revoked"]' in koerper)
        pruefe("und was zuerst ablaeuft, steht oben",
               "ergebnis.sort(" in koerper)


if __name__ == "__main__":
    test_fenster_kommt_wieder()
    test_fenster_nur_im_dashboard()
    test_abzeichen_in_der_seitenleiste()
    test_speedrun_ist_golden()
    test_admin_zeigt_konten()
    test_konten_route()
    test_store_fasst_zusammen()

    os.chdir(START)
    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print(f"  - {f}")
        sys.exit(1)
    print("Premium ist ueberall sichtbar, wo es sein soll.")
