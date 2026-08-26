#!/usr/bin/env python3
"""
Die oeffentliche Premium-Seite und der Knopf „Auf Standard“.

Zwei Dinge werden hier festgehalten:

  1. **Die Seite sagt die Wahrheit.** Von den zehn Punkten der Tabelle
     wirkt heute genau EINER -- das Design. Die anderen neun sind
     beschlossen, aber nicht scharf. Ohne diesen Test rutscht die
     Kennzeichnung beim naechsten Umbau raus und die Seite verkauft
     Dinge, die der Bot nicht tut.

  2. **Die Kauf-Knoepfe sind aus.** Es ist kein Zahlungsanbieter
     angebunden. Ein Knopf, der zu PayPal fuehren soll und es nicht
     tut, ist schlimmer als einer, der ehrlich `disabled` ist.

Warum statisch geprueft wird: im Testlauf gibt es kein Node und
keinen Browser. Ob die Farben ankommen, wurde beim Bauen mit einem
echten Browser nachgemessen.

Run:  python3 tests/test_premium_seite.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")

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

    Andersherum frisst der Blockausdruck ein `// ... */` und laesst
    Reste stehen. Das `(?<!:)` schuetzt `https://`.
    """
    ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


def entkette(src: str) -> str:
    """`"abc" + "def"` zu `"abcdef"`.

    Prosa wird beim Formatieren ueber mehrere Zeilen verkettet. Wer
    danach nach dem ganzen Satz sucht, findet ihn sonst nie.
    """
    return re.sub(r'"\s*\+\s*"', "", src)


SEITE = os.path.join(DASH, "app", "premium", "page.tsx")
PANEL = os.path.join(DASH, "components", "dashboard", "design-panel.tsx")


def test_seite_existiert():
    linie("1  Die Seite gibt es")
    pruefe("app/premium/page.tsx", os.path.isfile(SEITE))
    if not os.path.isfile(SEITE):
        return

    roh = lies("app", "premium", "page.tsx")
    koerper = strip_ts(roh)
    pruefe("sie benutzt die gemeinsame Leiste", "<SiteNav />" in koerper)
    pruefe("keine zweite, eigene Leiste",
           '<nav className="fixed top-0' not in koerper,
           "zwei Fassungen laufen auseinander")
    pruefe("sie ist in der Navigation verlinkt",
           'href: "/premium"' in strip_ts(lies("components", "site-nav.tsx")),
           "sonst findet die Seite niemand")


def test_preise():
    linie("2  Die Preise")
    if not os.path.isfile(SEITE):
        return
    koerper = strip_ts(lies("app", "premium", "page.tsx"))

    pruefe("Monatspreis 1,99", "PREIS_MONAT = 1.99" in koerper)
    pruefe("Lifetime 20", "PREIS_LIFETIME = 20" in koerper)
    pruefe("Jahresrabatt 10 Prozent", "RABATT_JAHR = 0.1" in koerper)

    # Der Jahrespreis muss GERECHNET sein. Eine getippte Zahl laeuft
    # beim naechsten Preiswechsel auseinander, und dann steht auf der
    # Seite ein Rabatt, den es nicht gibt.
    pruefe("der Jahrespreis wird gerechnet, nicht getippt",
           re.search(r"PREIS_JAHR\s*=\s*PREIS_MONAT\s*\*\s*12\s*\*\s*\(\s*1\s*-\s*RABATT_JAHR",
                     koerper) is not None,
           "sonst passt der Rabatt beim naechsten Preiswechsel nicht mehr")

    # Nachgerechnet: 1,99 * 12 = 23,88; minus 10 % = 21,49 (gerundet).
    erwartet = round(1.99 * 12 * 0.9, 2)
    pruefe("die Rechnung ergibt 21,49 EUR", abs(erwartet - 21.49) < 0.005,
           f"gerechnet: {erwartet}")

    # Deutsche Schreibweise. `toFixed` liefert IMMER einen Punkt.
    pruefe("Betraege mit Komma, nicht mit Punkt",
           "toLocaleString(\"de-DE\"" in koerper and ".toFixed(" not in koerper,
           "toFixed liefert immer einen Punkt")


def test_kauf_ist_aus():
    linie("3  Kaufen geht noch nicht")
    if not os.path.isfile(SEITE):
        return
    roh = lies("app", "premium", "page.tsx")
    koerper = entkette(strip_ts(roh))

    pruefe("die Testphase wird genannt", "Testphase" in koerper)
    pruefe("PayPal wird genannt", "PayPal" in koerper)

    # Auf die WIRKUNG zielen: der Knopf muss wirklich `disabled` sein.
    # Dass das Wort „PayPal" irgendwo steht, sagt nichts.
    knopf = re.search(
        r"<button[^>]*?disabled[^>]*?>\s*Mit PayPal kaufen", koerper, re.S
    )
    pruefe("der Kauf-Knopf ist wirklich abgeschaltet", knopf is not None,
           "sonst fuehrt er ins Leere")

    pruefe("und der Grund steht daneben",
           "Kommt, sobald die Testphase vorbei ist." in koerper)

    # Kein echter Zahlungslink -- sonst waere der `disabled`-Knopf
    # nur Zierde neben einem funktionierenden Weg.
    pruefe("keine echte Zahlungsadresse verlinkt",
           "paypal.me" not in roh.lower() and "paypal.com" not in roh.lower(),
           "solange nichts angebunden ist, darf hier kein Link stehen")


def test_tabelle():
    linie("4  Die Tabelle: zehn Punkte")
    if not os.path.isfile(SEITE):
        return
    koerper = strip_ts(lies("app", "premium", "page.tsx"))

    # Den Rumpf der Liste isolieren. Sonst zaehlt ein `titel:` aus
    # einem anderen Abschnitt mit.
    block = re.search(r"const VERGLEICH: Zeile\[\] = \[(.*?)\n\];", koerper, re.S)
    pruefe("die Liste VERGLEICH gibt es", block is not None)
    if block is None:
        return

    rumpf = block.group(1)
    titel = re.findall(r"titel:\s*\"([^\"]+)\"", rumpf)
    pruefe(f"es sind genau 10 Punkte (gezaehlt: {len(titel)})", len(titel) == 10,
           str(titel))

    # Jeder Punkt braucht beide Spalten.
    pruefe("jeder Punkt hat eine Gratis-Angabe",
           len(re.findall(r"gratis:", rumpf)) == len(titel),
           f"{len(re.findall(r'gratis:', rumpf))} von {len(titel)}")
    pruefe("jeder Punkt hat eine Premium-Angabe",
           len(re.findall(r"premium:", rumpf)) == len(titel),
           f"{len(re.findall(r'premium:', rumpf))} von {len(titel)}")

    # Genau EINER wirkt heute: das Design.
    live = re.findall(r"live:\s*true", rumpf)
    pruefe("genau ein Punkt ist als aktiv markiert", len(live) == 1,
           f"gefunden: {len(live)}")

    design = re.search(
        r"titel:\s*\"Eigenes Aussehen pro Server\".*?(?=\n\s*\{|\Z)", rumpf, re.S
    )
    pruefe("und zwar das Design", design is not None
           and "live: true" in design.group(0),
           "nur das Design ist gebaut")

    # Die neun anderen duerfen NICHT als aktiv gelten.
    pruefe("die neun uebrigen gelten als geplant", len(titel) - len(live) == 9,
           f"{len(titel) - len(live)} statt 9")

    # Die Kennzeichnung muss auch angezeigt werden, nicht nur in den
    # Daten stehen.
    pruefe("„geplant“ wird angezeigt", "geplant" in koerper)
    pruefe("„aktiv“ wird angezeigt", "aktiv" in koerper)
    pruefe("die Anzeige haengt am Feld live",
           re.search(r"\{z\.live \?", koerper) is not None,
           "sonst ist das Abzeichen Zierde")

    # Die Zahl der aktiven wird gerechnet, nicht getippt.
    pruefe("die Anzahl der aktiven wird gezaehlt",
           "VERGLEICH.filter((z) => z.live).length" in koerper,
           "eine getippte Zahl laeuft beim naechsten Punkt auseinander")


def test_keine_falschen_versprechen():
    linie("5  Keine erfundenen Angaben")
    if not os.path.isfile(SEITE):
        return
    roh = lies("app", "premium", "page.tsx")
    koerper = entkette(strip_ts(roh)).lower()

    # Dieselben Behauptungen, die auf Startseite und in der Doku schon
    # einmal entfernt wurden.
    for wort in ("aes-256", "neural", "edge network", "99,9", "99.9",
                 "geld-zurück", "geld-zurueck"):
        pruefe(f"„{wort}“ kommt nicht vor", wort not in koerper,
               "diese Behauptung ist nicht belegt")

    # Und der Hinweis, dass „geplant" wirklich geplant heisst.
    pruefe("der Vorbehalt steht auf der Seite",
           "noch nicht scharf geschaltet" in entkette(strip_ts(roh)),
           "sonst liest sich die Tabelle wie ein Leistungsversprechen")


def test_standard_knopf():
    linie("6  Der Knopf „Auf Standard“ im Design-Reiter")
    pruefe("das Panel gibt es", os.path.isfile(PANEL))
    if not os.path.isfile(PANEL):
        return

    roh = lies("components", "dashboard", "design-panel.tsx")
    koerper = entkette(strip_ts(roh))

    pruefe("er heisst „Auf Standard“", "Auf Standard" in koerper)
    pruefe("die alte Beschriftung ist weg", "Auf Original" not in koerper,
           "es soll genau eine Beschriftung geben")

    # Er darf NUR erscheinen, wenn es wirklich etwas zurueckzusetzen
    # gibt -- und das entscheidet der Bot, nicht das Formular.
    pruefe("er haengt an der Abweichung vom Portal",
           re.search(r"\{weichtAb && \(\s*<button", koerper) is not None,
           "sonst steht er auch da, wenn es nichts zu tun gibt")
    pruefe("die Abweichung kommt vom Bot",
           re.search(r"weichtAb\s*=\s*Boolean\(daten\?\.deviates\?\.abweichung\)",
                     koerper) is not None,
           "das Formular allein weiss nichts von Discord")

    # Er muss die eigene Route rufen, nicht das normale Speichern.
    pruefe("er ruft die Reset-Route", "api.designReset(guildId)" in koerper)
    pruefe("mit Rueckfrage", "window.confirm(" in koerper,
           "die Bilder sind danach weg")

    # Nur der Knopf, nicht das Formular-Verwerfen: der alte Knopf ist
    # ersetzt, nicht ergaenzt.
    pruefe("genau ein Zuruecksetzen-Knopf",
           len(re.findall(r"Auf Standard\s*\n?\s*</button>", koerper)) == 1,
           "zwei Knoepfe mit aehnlichem Namen verwirren")

    # Der Hinweis zur Bio: Discord bietet dafuer keine Schnittstelle.
    pruefe("der Bio-Hinweis steht da",
           "Die Bio des Bots lässt sich hier nicht ändern" in koerper)
    pruefe("und nennt das Developer Portal",
           "Developer Portal" in koerper)

    # api.ts kennt die Route.
    api_ts = strip_ts(lies("lib", "api.ts"))
    pruefe("api.ts kennt designReset", "designReset:" in api_ts)
    pruefe("und zeigt auf /standard",
           re.search(r"designReset:.*?/design/\$\{guildId\}/standard",
                     api_ts, re.S) is not None)
    pruefe("und ist ein POST",
           re.search(r"designReset:.*?method: \"POST\"", api_ts, re.S)
           is not None)


def test_route_im_bot():
    linie("7  Die Route im Bot")
    pfad = os.path.join(BOT, "api", "routes", "design.py")
    quelle = open(pfad, encoding="utf-8").read()

    # Kommentare raus -- sonst treffen die Muster die eigene Doku.
    ohne_docstring = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne_kommentar = re.sub(r"#[^\n]*", "", ohne_docstring)

    pruefe("es gibt eine Route /{guild_id}/standard",
           '@router.post("/{guild_id}/standard"' in ohne_kommentar)

    # Sie muss VOR der allgemeinen POST-Route stehen: Starlette nimmt
    # die erste passende.
    sys.path.insert(0, BOT)
    from api.routes import design as modul

    pfade = [getattr(r, "path", "") for r in modul.router.routes]
    pruefe("sie steht vor /{guild_id}",
           pfade.index("/{guild_id}/standard") < pfade.index("/{guild_id}"),
           f"Reihenfolge: {pfade}")

    # Auf die Wirkung zielen: alle drei Felder muessen geleert werden.
    rumpf = re.search(
        r'@router\.post\("/\{guild_id\}/standard".*?\n    return await _antwort',
        ohne_kommentar, re.S,
    )
    pruefe("der Rumpf ist auffindbar", rumpf is not None)
    if rumpf is not None:
        koerper = rumpf.group(0)
        pruefe("sie loescht Nickname, Avatar und Banner auf einmal",
               re.search(r"me\.edit\(\s*nick=None,\s*avatar=None,\s*banner=None",
                         koerper) is not None,
               "ein halb zurueckgesetztes Profil ist schlimmer als keins")
        pruefe("sie verlangt Premium", "_hat_premium(actor)" in koerper)
        pruefe("und die Berechtigung", "store.may_edit(db, guild, actor)" in koerper)
        pruefe("sie leert auch die eigene Tabelle",
               "store.clear(db, guild_id" in koerper,
               "sonst zeigt das Dashboard nach dem Neuladen alte Werte")

    # Das Feld, an dem der Knopf haengt.
    pruefe("die Antwort meldet die Abweichung",
           '"deviates": _weicht_ab(guild)' in ohne_kommentar)

    # `_weicht_ab` muss am ECHTEN Zustand messen, nicht an der Tabelle.
    fn = re.search(r"def _weicht_ab\(guild\).*?\n    return \{[^}]*\}",
                   ohne_kommentar, re.S)
    pruefe("_weicht_ab gibt es", fn is not None)
    if fn is not None:
        koerper = fn.group(0)
        for feld, muster in (
            ("nickname", r'getattr\(me, "nick", None\)'),
            ("avatar", r'getattr\(me, "guild_avatar", None\)'),
            ("banner", r'getattr\(me, "guild_banner", None\)'),
        ):
            pruefe(f"sie prueft {feld} am echten Bot",
                   re.search(muster, koerper) is not None,
                   "die eigene Tabelle kennt Handaenderungen in Discord nicht")


def test_clear_im_store():
    linie("8  clear() im Speicher")
    pfad = os.path.join(BOT, "utils", "guild_design.py")
    quelle = open(pfad, encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    pruefe("es gibt clear()", "async def clear(" in ohne)

    fn = re.search(r"async def clear\(.*?\n    return await get\(db, guild_id\)",
                   ohne, re.S)
    pruefe("der Rumpf ist auffindbar", fn is not None)
    if fn is not None:
        koerper = fn.group(0)
        for feld in ("nickname", "avatar_url", "banner_url"):
            pruefe(f"{feld} wird auf NULL gesetzt",
                   f"{feld} = NULL" in koerper)
        # Die Freischaltung liegt in einer eigenen Tabelle und darf
        # nicht mitgeloescht werden.
        pruefe("die Freischaltliste bleibt unberuehrt",
               "design_unlocked" not in koerper,
               "eine Freischaltung hat mit dem Aussehen nichts zu tun")
        pruefe("die Zeile bleibt stehen", "DELETE FROM" not in koerper,
               "updated_at soll zeigen, wann zurueckgesetzt wurde")


if __name__ == "__main__":
    test_seite_existiert()
    test_preise()
    test_kauf_ist_aus()
    test_tabelle()
    test_keine_falschen_versprechen()
    test_standard_knopf()
    test_route_im_bot()
    test_clear_im_store()

    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print(f"  - {f}")
        sys.exit(1)
    print("Die Premium-Seite und der Standard-Knopf sind in Ordnung.")
