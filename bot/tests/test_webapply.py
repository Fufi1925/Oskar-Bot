#!/usr/bin/env python3
"""
Team-Bewerbungen ueber die Website.

Vier Rollen mit je eigenen Fragen, genau eine Bewerbung pro Person,
Entscheidung im Admin-Dashboard.

Was hier festgehalten wird:

  1. **Eine Bewerbung pro Person** -- und zwar wirklich: auch fuer
     eine andere Rolle nicht, auch nach einer Entscheidung nicht.
     Erst wenn das Team freigibt.
  2. **Die Nutzer-ID kommt aus der Sitzung.** Kaeme sie aus dem
     Browser, waere die Regel mit einer erfundenen ID beliebig oft
     zu umgehen. Das prueft der Proxy-Teil.
  3. **Jede Rolle hat eigene Fragen.** Ein gemeinsamer Fragebogen
     haette bei jeder Rolle danebengelegen.
  4. **Reihenfolge der Pruefungen.** Die Doppel-Pruefung laeuft VOR
     der Laengenpruefung -- sonst bekommt jemand "Frage 7 ist zu
     kurz" statt seiner Bewerbungsnummer.

Run:  python3 tests/test_webapply.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

from utils import web_apply_store as store  # noqa: E402

failures: list[str] = []

USER = 1303627964734246944
USER2 = 1033826242270609449


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    with open(os.path.join(BOT, *teile), encoding="utf-8") as f:
        return f.read()


def read_dash(*teile) -> str:
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def lang(anzahl: int) -> list[str]:
    return ["Das ist eine ausreichend lange Antwort." for _ in range(anzahl)]


# ══════════════════════════════════════════════════════════════════════
#  Verhalten
# ══════════════════════════════════════════════════════════════════════


async def test_rollen():
    print("\nDie vier Rollen")

    rollen = store.role_list()
    check("genau vier", len(rollen) == 4, str(len(rollen)))
    namen = {r["label"] for r in rollen}
    check("Content Creator, Designer, Moderator, Tester",
          namen == {"Content Creator", "Designer", "Moderator", "Tester"},
          str(sorted(namen)))

    for schluessel in store.ROLE_KEYS:
        fragen = store.questions_of(schluessel)
        check(f"{schluessel}: mindestens fuenf Fragen", len(fragen) >= 5,
              str(len(fragen)))
        check(f"{schluessel}: keine leere Frage", all(f.strip() for f in fragen))

    # Und die Fragen passen wirklich zur Rolle -- ein gemeinsamer
    # Fragebogen waere kuerzer und ueberall halb daneben.
    check("Designer wird nicht nach Moderation gefragt",
          not any("moderiert" in f.lower()
                  for f in store.questions_of("designer")))
    check("Moderator wird nicht nach Portfolio gefragt",
          not any("portfolio" in f.lower()
                  for f in store.questions_of("moderator")))
    check("Tester wird nach Fehlern gefragt",
          any("fehler" in f.lower() for f in store.questions_of("tester")))
    check("Content Creator wird nach Plattformen gefragt",
          any("plattform" in f.lower() for f in store.questions_of("content")))

    # Jede Rolle fragt nach der Zeit -- daran scheitert es in der Praxis.
    for schluessel in store.ROLE_KEYS:
        check(f"{schluessel} fragt nach der Zeit",
              any("zeit" in f.lower() for f in store.questions_of(schluessel)))

    # Keine zwei Rollen haben denselben Fragebogen -- und auch keine
    # zwei fast denselben. Nur auf Gleichheit zu pruefen liesse zwei
    # Fragebogen durchgehen, die sich in einem Wort unterscheiden.
    saetze = {k: set(store.questions_of(k)) for k in store.ROLE_KEYS}
    check("kein Fragebogen doppelt",
          len({tuple(sorted(v)) for v in saetze.values()}) == 4)
    schluessel = list(store.ROLE_KEYS)
    for i, a in enumerate(schluessel):
        for b in schluessel[i + 1:]:
            gemeinsam = saetze[a] & saetze[b]
            # Die Zeitfrage teilen sich alle -- mehr als eine
            # gemeinsame Frage hiesse, die Fragebogen laufen zusammen.
            check(f"{a} und {b} haben eigene Fragen",
                  len(gemeinsam) <= 1, f"{len(gemeinsam)} gemeinsam")


async def test_abgeben():
    print("\nAbgeben")

    antworten = lang(len(store.questions_of("tester")))
    bewerbung = await store.submit(USER, "Mia", "", "tester", antworten)

    check("angelegt", bewerbung is not None)
    check("Status offen", bewerbung["status"] == store.STATUS_OPEN)
    check("hat eine Nummer", bewerbung["ticket"].startswith("BW-"),
          bewerbung["ticket"])
    check("Nutzer-ID als Text", isinstance(bewerbung["user_id"], str),
          "als Zahl rundet JavaScript die letzte Stelle weg")
    check("Rolle richtig", bewerbung["role_label"] == "Tester")
    check("Fragen kommen mit", len(bewerbung["questions"]) == len(antworten))


async def test_nur_eine():
    print("\nGenau eine Bewerbung pro Person")

    antworten = lang(len(store.questions_of("tester")))

    gefangen = False
    try:
        await store.submit(USER, "Mia", "", "tester", antworten)
    except store.AlreadyApplied as exc:
        gefangen = True
        check("die vorhandene kommt mit", bool(exc.existing.get("ticket")))
    check("eine zweite wird abgelehnt", gefangen)

    # Auch fuer eine ANDERE Rolle nicht -- und mit der richtigen
    # Meldung. Der Moderator hat sieben Fragen, der Tester sechs:
    # lief die Laengenpruefung zuerst, kam "Frage 7 ist zu kurz"
    # statt der Bewerbungsnummer.
    art = ""
    try:
        await store.submit(USER, "Mia", "", "moderator", antworten)
    except store.AlreadyApplied:
        art = "already"
    except ValueError as exc:
        art = f"value: {exc}"
    check("auch fuer eine andere Rolle nicht", art == "already", art)

    # Und die zweite Sperre direkt an der Datenbank.
    #
    # Zwischen der Pruefung oben und dem INSERT koennte eine zweite
    # Anfrage durchlaufen. Hier wird genau dieser Moment nachgestellt:
    # get_application liefert einmal None, obwohl die Zeile existiert.
    # Faellt die Pruefung in der Verbindung weg, kommt statt einer
    # sprechenden Meldung ein IntegrityError.
    echte = store.get_application

    async def blind(uid):
        return None

    store.get_application = blind
    art2 = ""
    try:
        await store.submit(USER, "Mia", "", "tester", antworten)
        art2 = "durchgelaufen"
    except store.AlreadyApplied:
        art2 = "already"
    except Exception as exc:
        art2 = f"{type(exc).__name__}: {exc}"
    finally:
        store.get_application = echte
    check("auch bei gleichzeitigen Anfragen sauber abgewiesen",
          art2 == "already", art2)


async def test_kurze_antworten():
    print("\nZu kurze Antworten")

    for schlecht, wie in (([""] * 6, "leer"), (["kurz"] * 6, "vier Zeichen"),
                          ([], "gar keine")):
        gefangen = False
        try:
            await store.submit(USER2, "Tom", "", "tester", schlecht)
        except ValueError:
            gefangen = True
        check(f"{wie} wird abgelehnt", gefangen)

    check("und nichts wurde angelegt",
          await store.get_application(USER2) is None)

    gefangen = False
    try:
        await store.submit(999, "X", "", "hacker", lang(6))
    except ValueError:
        gefangen = True
    check("unbekannte Rolle wird abgelehnt", gefangen)


async def test_entscheiden():
    print("\nEntscheiden")

    ent = await store.decide(USER, store.STATUS_ACCEPTED, "42", "Chef",
                             "Willkommen im Team!")
    check("angenommen", ent is not None and ent["status"] == "accepted")
    check("Grund gespeichert", ent and ent["reason"] == "Willkommen im Team!")
    check("wer entschied", ent and ent["decided_by_name"] == "Chef")
    check("Zeitpunkt gesetzt", ent and ent["decided_at"] > 0)

    # Ein zweiter Klick darf die erste Entscheidung nicht kippen.
    nochmal = await store.decide(USER, store.STATUS_DENIED, "43", "Andere",
                                 "Doch nicht")
    check("zweite Entscheidung prallt ab", nochmal is None)
    danach = await store.get_application(USER)
    check("die erste steht noch", danach["status"] == "accepted")
    check("und ihr Grund auch", danach["reason"] == "Willkommen im Team!")

    # Nur annehmen oder ablehnen.
    gefangen = False
    try:
        await store.decide(USER, "vielleicht", "1", "X", "hm")
    except ValueError:
        gefangen = True
    check("kein dritter Status", gefangen)


async def test_nach_der_entscheidung():
    print("\nNach der Entscheidung")

    gefangen = False
    try:
        await store.submit(USER, "Mia", "", "designer",
                           lang(len(store.questions_of("designer"))))
    except store.AlreadyApplied:
        gefangen = True
    check("bleibt gesperrt", gefangen,
          "sonst bewirbt sich jeder nach der Ablehnung sofort neu")

    check("freigeben geht", await store.reopen(USER))
    check("die Akte ist danach leer", await store.get_application(USER) is None)

    neu = await store.submit(USER, "Mia", "", "designer",
                             lang(len(store.questions_of("designer"))))
    check("danach ist eine neue moeglich", neu["status"] == "open")
    check("mit der neuen Rolle", neu["role_label"] == "Designer")


async def test_zurueckziehen():
    print("\nZurueckziehen")

    check("geht, solange offen", await store.withdraw(USER))
    zurueck = await store.get_application(USER)
    check("Status zurueckgezogen", zurueck["status"] == "withdrawn")
    check("ein zweites Mal nicht", not await store.withdraw(USER))


async def test_liste():
    print("\nListe, Filter und Zaehler")

    await store.reopen(USER)
    await store.submit(USER, "Mia", "", "tester",
                       lang(len(store.questions_of("tester"))))
    await store.submit(USER2, "Tom", "", "moderator",
                       lang(len(store.questions_of("moderator"))))

    liste = await store.list_applications()
    check("beide in der Liste", len(liste) == 2, str(len(liste)))
    # Mit gemischten Zustaenden pruefen. Vorher waren beide offen,
    # und "2 von 2" stimmt auch, wenn der Filter gar nichts tut.
    await store.decide(USER2, store.STATUS_ACCEPTED, "9", "Chef", "Ja")
    nur_offen = await store.list_applications("open")
    check("nach Status filterbar", len(nur_offen) == 1, str(len(nur_offen)))
    check("und wirklich nur offene",
          all(a["status"] == "open" for a in nur_offen))
    nur_an = await store.list_applications("accepted")
    check("auch nach angenommen", len(nur_an) == 1 and
          nur_an[0]["status"] == "accepted")
    check("ohne Filter kommen beide",
          len(await store.list_applications()) == 2)
    # Zuruecksetzen fuer die folgenden Pruefungen.
    await store.reopen(USER2)
    await store.submit(USER2, "Tom", "", "moderator",
                       lang(len(store.questions_of("moderator"))))

    zahlen = await store.counts()
    check("Zaehler stimmt", zahlen["open"] == 2, str(zahlen))

    await store.decide(USER2, store.STATUS_DENIED, "1", "Chef", "Leider nein")
    zahlen = await store.counts()
    check("nach der Ablehnung",
          zahlen["open"] == 1 and zahlen["denied"] == 1, str(zahlen))

    liste = await store.list_applications()
    check("offene stehen oben", liste[0]["status"] == "open",
          "sonst muss das Team suchen, was zu tun ist")


async def test_nummer():
    print("\nDie Bewerbungsnummer")

    a = await store.get_application(USER)
    b = await store.get_application(USER)
    check("bleibt gleich", a["ticket"] == b["ticket"])
    check("verraet die Discord-ID nicht", str(USER)[:6] not in a["ticket"])
    check("ist kurz genug zum Vorlesen", len(a["ticket"]) <= 9, a["ticket"])

    # Zwei Personen bekommen nicht dieselbe.
    andere = await store.get_application(USER2)
    check("zwei Personen, zwei Nummern", a["ticket"] != andere["ticket"])


async def test_config():
    print("\nEinstellungen")

    config = await store.get_config()
    check("alle vier Rollen", set(config["roles"]) == set(store.ROLE_KEYS))
    check("erst mal alle offen",
          all(r["open"] for r in config["roles"].values()))

    await store.save_config({
        "roles": {"tester": {"discord_role_id": "555", "open": False}},
        "guild_id": "1530378233579704370",
        "channel_id": "900",
    })
    config = await store.get_config()
    check("Rolle gesichert",
          config["roles"]["tester"]["discord_role_id"] == "555")
    check("geschlossen gesichert", config["roles"]["tester"]["open"] is False)
    check("Server gesichert", config["guild_id"] == "1530378233579704370")
    check("die anderen unberuehrt", config["roles"]["designer"]["open"] is True)

    await store.save_config({"roles": {"designer": {"discord_role_id": "abc"}}})
    config = await store.get_config()
    check("Buchstaben als Rollen-ID fallen raus",
          config["roles"]["designer"]["discord_role_id"] == "")


async def test_altes_schema():
    print("\nEine alte Installation bekommt die neuen Spalten")

    import aiosqlite

    pfad = os.path.join(tempfile.mkdtemp(), "alt.db")
    async with aiosqlite.connect(pfad) as db:
        await db.execute(
            "CREATE TABLE web_applications (user_id INTEGER PRIMARY KEY,"
            " role_key TEXT NOT NULL)"
        )
        await db.commit()

    alt = store.DB_PATH
    store.DB_PATH = pfad
    try:
        neu = await store.submit(77, "Alt", "", "tester",
                                 lang(len(store.questions_of("tester"))))
        check("laesst sich trotzdem benutzen", neu is not None)
        check("Status kommt zurueck", neu["status"] == "open")
        check("Nummer auch", neu["ticket"].startswith("BW-"))
    finally:
        store.DB_PATH = alt


# ══════════════════════════════════════════════════════════════════════
#  Verdrahtung
# ══════════════════════════════════════════════════════════════════════


def test_route_haengt():
    print("\nDie API-Route haengt am Server")

    server = read("api", "server.py")
    check("importiert", "webapply" in server.split("include_router")[0])
    check("eingehaengt", 'webapply.router, prefix="/webapply"' in server)
    check("Befehlsverzeichnis importiert",
          "commands as commands_route" in server)
    check("und eingehaengt",
          'commands_route.router, prefix="/commands"' in server)


def test_proxy_setzt_die_id():
    print("\nDie Nutzer-ID kommt aus der Sitzung")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))

    check("es gibt einen webapply-Bereich", 'scope === "webapply"' in proxy)
    check("und einen fuer die Befehle", 'scope === "commands"' in proxy)

    # Der entscheidende Teil: bei submit wird die ID ueberschrieben.
    # Ohne das koennte jeder im Namen anderer bewerben -- und die
    # Regel "eine pro Person" waere mit einer erfundenen ID beliebig
    # oft zu umgehen.
    check(
        "submit setzt die user_id aus der Sitzung",
        re.search(
            r'segments\[0\]\s*===\s*"webapply"\s*&&\s*segments\[1\]\s*===\s*"submit"'
            r'[^}]*parsed\.user_id\s*=\s*actorId',
            proxy, re.S,
        ) is not None,
    )
    check("Name kommt ebenfalls aus der Sitzung",
          "parsed.user_name = session?.user?.name" in proxy)

    # Und niemand darf die Bewerbung eines anderen lesen.
    zweig = proxy.split('scope === "webapply"', 1)[1]
    ende = zweig.find("\n  if (scope ===")
    zweig = zweig[: ende if ende > 0 else 2000]
    check("me/withdraw nur fuer die eigene ID",
          'rest[1] !== session.user.id' in zweig)
    check("und prueft die Anmeldung", "Not signed in" in zweig)

    # Die Berechtigung muss wirklich abgefragt werden -- ein
    # "approvals.resolve" irgendwo im Text genuegt nicht. Vorher
    # blieb der Test gruen, als aus der Abfrage ein `if (true)`
    # wurde.
    check(
        "alles andere fragt die Berechtigung wirklich ab",
        re.search(
            r"await\s+hasTeamPermission\(\s*session\.user\.id\s*,\s*"
            r'"approvals\.resolve"',
            zweig,
        ) is not None,
    )
    check("und weist sonst ab", "deny(403" in zweig)
    check("globale Admins duerfen immer", "isGlobalAdmin" in zweig)


def test_schema_guard():
    print("\nDatenbank")

    from api import schema_guard

    check("eigene Datei", store.DB_PATH == "db/web_apply.db")
    check("schema_guard kennt sie", store.DB_PATH in schema_guard.SCHEMA)

    anweisungen = " ".join(schema_guard.SCHEMA.get(store.DB_PATH, ()))
    for tabelle in ("web_applications", "web_apply_config",
                    "web_apply_settings"):
        check(f"{tabelle} wird angelegt", tabelle in anweisungen)

    # Jede Spalte des Stores muss nachgetragen werden.
    im_guard = {
        spalte for datei, tabelle, spalte, _ in schema_guard.ADDED_COLUMNS
        if datei == store.DB_PATH
    }
    fehlend = sorted({n for n, _ in store.COLUMNS} - im_guard)
    check("schema_guard traegt jede Spalte nach", not fehlend, str(fehlend))


def test_seiten_existieren():
    print("\nDie Seiten gibt es")

    for pfad, was in (
        (("app", "commands", "page.tsx"), "Befehlsverzeichnis"),
        (("app", "team", "apply", "page.tsx"), "Bewerbungsseite"),
        (("components", "dashboard", "applications-admin.tsx"), "Admin-Reiter"),
    ):
        check(f"{was}", os.path.isfile(os.path.join(DASH, *pfad)))


def test_admin_reiter():
    print("\nDer Admin-Reiter ist eingehaengt")

    inhalt = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))

    check("importiert", "ApplicationsAdmin" in inhalt)
    check("als Reiter eingetragen", '"webapply"' in inhalt)
    check("mit deutschem Namen", 'label: "Bewerbungen"' in inhalt)
    check("wird gerendert",
          'activeTab === "webapply" && <ApplicationsAdmin />' in inhalt)
    check("in einer Gruppe", '"webapply",' in inhalt or '"webapply"' in inhalt)
    check("mit Berechtigung", 'webapply: "approvals.resolve"' in inhalt)

    # Die englischen Beschriftungen sind weg.
    for englisch in ('label: "Warnings"', 'label: "Usage"', 'label: "Reports"',
                     'label: "Audit"', 'label: "Approvals"',
                     'label: "Backups"', 'label: "Access"',
                     'label: "Bot Config"'):
        check(f"{englisch} ist uebersetzt", englisch not in inhalt)


def test_rollen_stimmen_ueberein():
    print("\nWebsite und Bot kennen dieselben Rollen")

    nav = strip_ts(read_dash("components", "site-nav.tsx"))

    # Die Navigationsleiste verlinkt ?rolle=xyz -- jeder dieser
    # Schluessel muss im Bot existieren, sonst fuehrt der Link auf
    # einen Fragebogen, den der Bot ablehnt.
    verlinkt = set(re.findall(r"/team/apply\?rolle=([a-z]+)", nav))
    check("die Leiste verlinkt Rollen", verlinkt, str(verlinkt))
    unbekannt = sorted(verlinkt - set(store.ROLE_KEYS))
    check("jede verlinkte Rolle gibt es im Bot", not unbekannt, str(unbekannt))
    fehlt = sorted(set(store.ROLE_KEYS) - verlinkt)
    check("und jede Rolle des Bots ist verlinkt", not fehlt, str(fehlt))


def test_seite_wertet_rolle_aus():
    print("\nDie Bewerbungsseite")

    seite = strip_ts(read_dash("app", "team", "apply", "page.tsx"))

    # Die Anmeldung muss wirklich aus useSession kommen. Vorher
    # genuegte das Wort irgendwo; eine fest verdrahtete Sitzung
    # blieb unentdeckt.
    check("liest die echte Sitzung",
          re.search(r"const\s*\{\s*data:\s*session[^}]*\}\s*=\s*useSession\(\)",
                    seite) is not None)
    check("und haengt die Anzeige daran",
          "const angemeldet = Boolean(session?.user?.id)" in seite)
    check("bietet den Login an", "signIn(\"discord\"" in seite)
    check("wertet ?rolle= aus", 'params.get("rolle")' in seite)
    # Die Grenze muss die Seite auch wirklich umschliessen.
    check("in einer Suspense-Grenze",
          re.search(r"<React\.Suspense.*?>\s*<ApplyInner\s*/>\s*</React\.Suspense>",
                    seite, re.S) is not None,
          "useSearchParams verlangt das, sonst faellt die Seite zurueck")
    check("zeigt den Fortschritt", "beantwortet" in seite)
    check("zeigt die Nummer", "ticket" in seite)
    # Der 409 muss zu einer echten Anzeige fuehren, nicht nur
    # erwaehnt werden.
    check("faengt den 409 ab",
          re.search(r"if\s*\(d\?\.application\)\s*\{\s*\n\s*setMeine\(d\.application\)",
                    seite) is not None,
          "sonst steht dort eine rote Fehlermeldung statt der Nummer")
    check("und zeigt die Meldung des Bots", "toast.info(d.message" in seite)
    check("erlaubt Zurueckziehen", "withdrawApplication" in seite)


def test_befehlsseite():
    print("\nDas Befehlsverzeichnis")

    seite = strip_ts(read_dash("app", "commands", "page.tsx"))

    # Ueber einen Ausdruck, nicht woertlich: Prettier bricht den
    # Aufruf um, und "api.getCommands()" steht dann auf zwei Zeilen.
    check("holt die Befehle vom Bot",
          re.search(r"api\s*\.?\s*\n?\s*\.?getCommands\s*\(", seite)
          is not None)
    check("hat eine Suche", "Befehl suchen" in seite)
    check("teilt in Top und Rest",
          re.search(r"const\s+top\s*=\s*gefiltert\.slice\(0,", seite)
          is not None
          and re.search(r"const\s+rest\s*=\s*gefiltert\.slice\(", seite)
          is not None,
          "ohne slice steht alles in einer Liste")
    check("sagt, worauf die Reihenfolge beruht", "ranked_by_usage" in seite,
          "sonst behauptet die Seite eine Rangliste, die keine ist")
    check("gruppiert den Rest nach Kategorie", "gruppen" in seite)
    check("nennt einen Fehler beim Namen", "antwortet gerade nicht" in seite)

    # Die alte Docs-Seite bleibt bestehen, aber die Leiste zeigt auf
    # die neue.
    nav = strip_ts(read_dash("components", "site-nav.tsx"))
    # Der Eintrag "Alle Befehle" muss dorthin zeigen. Nur zu
    # pruefen, dass "/commands" irgendwo vorkommt, blieb gruen, als
    # er auf /docs umgebogen wurde -- ein zweiter Eintrag zeigte
    # noch hin.
    check("»Alle Befehle« zeigt auf /commands",
          re.search(r'label:\s*"Alle Befehle",\s*href:\s*"/commands"', nav)
          is not None)


def test_kategorien_decken_ab():
    print("\nDie Kategorien der Befehle")

    from api.routes import commands as route

    check("es gibt Kategorien", len(route.KATEGORIEN) > 40,
          str(len(route.KATEGORIEN)))
    check("die wichtigsten stehen oben",
          route.KATEGORIEN["Moderation"][1] == 0)
    check("Besitzer-Befehle ganz unten",
          route.KATEGORIEN["Owner"][1] == 99)
    check("Besitzer-Cogs sind versteckt", "Owner" in route.VERSTECKT)
    check("hundert oben", route.TOP_COUNT == 100)


def test_sidebar_ist_ruhig():
    print("\nDie Seitenleiste ist ruhig")

    layout = strip_ts(read_dash("app", "dashboard", "layout.tsx"))

    # Der KI-Look: Pulsieren, Leuchten, drei Sonderstile.
    for laut, was in (
        ("speedrun-link", "wanderndes Licht am Speedrun"),
        ("speedrun-badge", "eigenes Symbolfeld"),
        ("admin-badge", "Stahlplatte am Admin"),
        ("premium-link", "goldenes Pulsieren"),
        ("animate-pulse shadow-", "pulsierender Punkt"),
        ("drop-shadow-[0_0_6px", "Leuchten unter dem Symbol"),
        ("scale-110", "Symbol waechst beim Aktivieren"),
    ):
        check(f"kein {was}", laut not in layout)

    check("ein Stil fuer den aktiven Eintrag",
          'bg-white/[0.06] text-white font-semibold' in layout)
    check("die Leiste sitzt am Rand", "fixed left-0 top-0 bottom-0" in layout)
    check("und der Inhalt passt dazu", "lg:pl-64" in layout,
          "sonst liegt der Inhalt unter der Leiste")


def test_hero_hat_dreizehn():
    print("\nDreizehn Karten auf der Startseite")

    seite = read_dash("app", "page.tsx")
    anfang = seite.index("const HERO_KARTEN")
    ende = seite.index("];", anfang)
    block = seite[anfang:ende]

    anzahl = block.count("titel:")
    check("genau dreizehn", anzahl == 13, str(anzahl))
    check("jede hat ein Symbol", block.count("icon:") == anzahl)
    check("jede hat eine Zahl", block.count("zahl:") == anzahl)
    check("die Punkte zeigen die Stelle", "von {HERO_KARTEN.length}" in seite)


# ══════════════════════════════════════════════════════════════════════


async def run_async():
    ordner = tempfile.mkdtemp()
    alt = os.getcwd()
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)
    try:
        await test_rollen()
        await test_abgeben()
        await test_nur_eine()
        await test_kurze_antworten()
        await test_entscheiden()
        await test_nach_der_entscheidung()
        await test_zurueckziehen()
        await test_liste()
        await test_nummer()
        await test_config()
        await test_altes_schema()
    finally:
        os.chdir(alt)


def main() -> int:
    asyncio.run(run_async())

    test_route_haengt()
    test_proxy_setzt_die_id()
    test_schema_guard()
    test_seiten_existieren()
    test_admin_reiter()
    test_rollen_stimmen_ueberein()
    test_seite_wertet_rolle_aus()
    test_befehlsseite()
    test_kategorien_decken_ab()
    test_sidebar_ist_ruhig()
    test_hero_hat_dreizehn()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for zeile in failures:
            print(f"   {zeile}")
        return 1
    print("Alle Bewerbungs- und Befehlspruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
