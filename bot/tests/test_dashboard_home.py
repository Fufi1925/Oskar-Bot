#!/usr/bin/env python3
"""
Startseite, Handy-Navigation und die Seiten hinter dem Login.

Vier Dinge werden hier festgehalten:

  1. **Die Zahlen auf der Startseite sind echt.** Modulzahl, Befehle
     und Mitglieder standen fest im Quelltext -- und waren falsch:
     608 Befehle behauptet, 623 gezaehlt. Jetzt kommen sie aus
     ``/bot/numbers``.
  2. **Auf Telefon und Tablet kommt man ins Dashboard.** Die
     Hauptleiste ist erst ab ``lg`` sichtbar; im eingeklappten Menue
     fehlte der Dashboard-Link komplett. Wer auf dem Handy einsteigen
     wollte, kam gar nicht hin.
  3. **Die Reiterleiste ueber jeder Serverseite ist weg.** Sie
     listete dieselben 41 Eintraege wie die Seitenleiste links --
     nachgezaehlt, beide Listen waren deckungsgleich.
  4. **Die Seite nach dem Login ist deutsch und ruhig.** Sie war
     englisch ("Welcome back", "Your servers") mit vier
     Glaskacheln.

Run:  python3 tests/test_dashboard_home.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

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


def read_bot(*teile) -> str:
    with open(os.path.join(BOT, *teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def guild_pages() -> set[str]:
    root = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]")
    return {
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e))
    }


# ══════════════════════════════════════════════════════════════════════


def test_zahlen_sind_echt():
    print("\nDie Zahlen der Startseite kommen aus dem Bot")

    seite = strip_ts(read("app", "page.tsx"))

    check("sie werden geladen", '"/api/bot/bot/numbers"' in seite)
    check("und in den Zustand gelegt", "setZahlen(d)" in seite)

    # Keine festen Zahlen mehr in den Kacheln.
    block = seite[seite.index("label: \"Server\""):]
    block = block[: block.index("].map(")]
    for fest in ('"152"', '"608"', '"41"'):
        check(f"{fest} steht nicht mehr fest drin", fest not in block)

    for feld in ("zahlen?.modules", "zahlen?.commands", "zahlen?.users"):
        check(f"{feld} wird angezeigt", feld in block)

    # Fehlt die Antwort, steht ein Strich -- keine erfundene Zahl.
    check("ohne Antwort ein Strich", 'wert > 0 ? wert.toLocaleString("de-DE") : "—"'
          in seite)


def test_route_zaehlt_richtig():
    print("\nDie Route zaehlt vollstaendig")

    route = read_bot("api", "routes", "bot.py")

    check("es gibt sie", '@router.get("/numbers"' in route)
    check("Module sind die Cogs", "len(bot.cogs)" in route)
    check("Prefix-Befehle mit Untergruppen", "bot.walk_commands()" in route)
    check("versteckte zaehlen nicht mit", "if not c.hidden" in route)
    check("Slash-Befehle werden mitgezaehlt", "app_commands.Group" in route,
          "sonst fehlen 80 Befehle")
    check("und rekursiv", "zaehle(kind)" in route,
          "eine Gruppe zaehlt sonst als ein Befehl")
    check("die Summe wird geliefert", '"commands": prefix + slash' in route)

    # Sie muss ohne Anmeldung erreichbar sein -- die Startseite ist
    # oeffentlich. Genau daran ist die alte Serverzahl gescheitert.
    mw = strip_ts(read("middleware.ts"))
    check("die Middleware kennt den Pfad",
          '"/api/bot/bot/numbers"' in mw)
    # Und die Liste muss auch abgefragt werden. Ein `if (false)` liess
    # den Pfad in der Datei stehen und sperrte ihn trotzdem -- im
    # Mutationstest aufgefallen.
    check("und fragt die Ausnahmeliste wirklich ab",
          "OEFFENTLICH.some((p) => pathname === p)" in mw,
          "sonst kommt fuer jeden Nichtangemeldeten eine Weiterleitung")
    check("die Ausnahme kommt vor der Sperre",
          mw.index("OEFFENTLICH.some") < mw.index('pathname.startsWith("/api/bot")'),
          "danach greift sie nie")
    proxy = strip_ts(read("app", "api", "bot", "[...path]", "route.ts"))
    check("der Proxy ebenfalls",
          'rest[0] === "numbers"' in proxy)
    check("aber nur lesend",
          'rest[0] === "numbers" && request.method === "GET"' in proxy)


def test_handy_kommt_ins_dashboard():
    print("\nAuf Telefon und Tablet kommt man ins Dashboard")

    nav = strip_ts(read("components", "site-nav.tsx"))

    # Der Block fuer schmale Bildschirme.
    start = nav.index("{offen && (")
    block = nav[start:]

    check("es gibt einen Dashboard-Knopf",
          'href="/dashboard"' in block,
          "die Hauptleiste ist erst ab lg sichtbar -- ohne diesen "
          "Eintrag kommt man auf dem Handy gar nicht hin")
    check("er ist hervorgehoben", "bg-[#5865f2]" in block)
    check("Bot hinzufügen ist dabei", "Bot hinzufügen" in block)
    check("Support-Server auch", "Support-Server" in block)
    check("und die Team-Rollen", "TEAM_ROLLEN" in block)
    # Die Ueberschrift muss wirklich gerendert werden. `gruppe.titel`
    # steht auch im key= des map-Aufrufs -- eine blosse Wortsuche
    # blieb gruen, als die Ueberschrift geloescht war.
    check("nach Abschnitten geordnet",
          re.search(r"<p[^>]*>\s*\{gruppe\.titel\}\s*</p>", block, re.S)
          is not None,
          "elf Eintraege am Stueck liest niemand")
    check("es sind drei Abschnitte",
          block.count("eintraege:") == 3,
          "Befehle, Team beitreten, Über")

    # Der Knopf muss sich auch schliessen lassen.
    check("der Menueknopf zeigt ein X", "offen ? (" in nav and "<X className" in nav,
          "drei Striche, die sich nicht aendern, sagen nicht, wie man "
          "wieder zumacht")
    check("jeder Eintrag schliesst das Menue",
          block.count("setOffen(false)") >= 4)


def test_reiterleiste_ist_weg():
    print("\nDie doppelte Reiterleiste ist weg")

    layout = strip_ts(read("app", "dashboard", "guild", "[guildId]", "layout.tsx"))

    check("sie wird nicht mehr eingebunden", "<GuildTabs" not in layout)
    check("und nicht mehr importiert", "guild-tabs" not in layout)

    # Der Grund: sie war deckungsgleich mit der Seitenleiste. Das
    # muss so bleiben -- sonst fehlt ein Reiter ueberall.
    sidebar = strip_ts(read("app", "dashboard", "layout.tsx"))
    verlinkt = set(re.findall(
        r"/dashboard/guild/\$\{currentGuildId\}/([a-z0-9\-]+)", sidebar))
    seiten = guild_pages()

    fehlend = sorted(seiten - verlinkt)
    check("jede Seite steht in der Seitenleiste", not fehlend, str(fehlend))
    check("es sind alle", len(verlinkt) >= len(seiten),
          f"{len(verlinkt)} verlinkt, {len(seiten)} Seiten")

    # Und die Datei selbst darf verschwinden oder bleiben -- benutzt
    # werden darf sie nirgends mehr.
    benutzt = []
    for root, dirs, files in os.walk(DASH):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".git")]
        for name in files:
            if not name.endswith(".tsx"):
                continue
            pfad = os.path.join(root, name)
            if os.path.basename(pfad) == "guild-tabs.tsx":
                continue
            if "<GuildTabs" in open(pfad, encoding="utf-8").read():
                benutzt.append(os.path.relpath(pfad, DASH))
    check("niemand bindet sie mehr ein", not benutzt, str(benutzt))


def test_kopfbereich_ist_schlicht():
    print("\nDer Kopf ueber der Serverseite")

    kopf = strip_ts(read("components", "dashboard", "guild-header.tsx"))

    # Das Bild war 120px -- auf einem 375px-Telefon ein Drittel der
    # Breite fuer eine Kennung.
    check("das Serverbild ist klein", "h-14 w-14" in kopf)
    check("nicht mehr 120px", "lg:h-[120px]" not in kopf)

    # Der Aktualisieren-Knopf war der lauteste auf der Seite.
    check("Aktualisieren ist nur noch ein Symbol",
          'aria-label="Aktualisieren"' in kopf)
    check("ohne Versalien",
          "uppercase tracking-widest" not in kopf)

    # Die drei Zahlen ohne eigene Kaesten.
    check("die Zahlen stehen in einer Zeile", "flex flex-wrap gap-x-6" in kopf)
    check("kein pulsierender Punkt mehr", "animate-pulse" not in kopf)

    # Der Statuspunkt sagt weiterhin die Wahrheit.
    check("der Punkt zeigt echte Latenz", "state.tone" in kopf)
    check("und erklaert sich", "title={state.hint}" in kopf)


def test_seite_nach_dem_login():
    print("\nDie Seite nach dem Login")

    seite = strip_ts(read("app", "dashboard", "page.tsx"))

    # Sie war komplett englisch.
    for englisch in ("Welcome back", "Your servers", "Members reached",
                     "Bot servers", "No servers yet", "Invite the bot",
                     "All servers", "Add the bot", "Latency"):
        check(f"»{englisch}« ist uebersetzt", englisch not in seite)

    check("auf Deutsch", "Hallo, {firstName}" in seite
          and "Deine Server" in seite)

    # Vier Glaskacheln mit Symbolrahmen -> eine Zeile.
    check("keine Glaskacheln mehr", 'className="group glass' not in seite)
    check("die Zahlen stehen in einer Zeile",
          "flex flex-wrap gap-x-8" in seite)

    # Deutsche Zahlformatierung.
    check("Zahlen deutsch formatiert", 'toLocaleString("de-DE")' in seite)
    check("nicht mehr englisch", 'toLocaleString("en-US")' not in seite)

    # Die Serverliste bleibt der Kern der Seite.
    check("die Server werden aufgelistet", "vorschau.map" in seite)
    check("verbundene fuehren ins Dashboard",
          "/dashboard/guild/${guild.id}" in seite)
    check("fehlende laden den Bot ein", "BOT_INVITE_URL" in seite)
    check("und es wird gesagt, wie viele fehlen",
          "fehlt der Bot noch" in seite)


def test_startseite_ist_ruhiger():
    print("\nDie Startseite ist ruhiger")

    seite = strip_ts(read("app", "page.tsx"))

    # Fuenf goldene Sterne ueber echten Zahlen sahen aus wie eine
    # Bewertung, waren aber Dekoration.
    check("keine Deko-Sterne mehr", "fill-amber-400" not in seite)
    check("und keine in den Stimmen", "fill-emerald-400" not in seite)
    check("das Symbol ist nicht mehr importiert",
          not re.search(r"^\s*Star,?\s*$", seite, re.M),
          "ein unbenutzter Import bleibt sonst ewig stehen")

    # Die Versal-Sperrung unter den Zahlen.
    zahlen_block = seite[seite.index('label: "Server"'):]
    zahlen_block = zahlen_block[: zahlen_block.index("</section>")]
    check("keine Versalien unter den Zahlen",
          "uppercase tracking-widest" not in zahlen_block)


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_zahlen_sind_echt()
    test_route_zaehlt_richtig()
    test_handy_kommt_ins_dashboard()
    test_reiterleiste_ist_weg()
    test_kopfbereich_ist_schlicht()
    test_seite_nach_dem_login()
    test_startseite_ist_ruhiger()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for zeile in failures:
            print(f"   {zeile}")
        return 1
    print("Alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
