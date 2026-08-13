#!/usr/bin/env python3
"""
Der taegliche Verlauf und die Diagramme, die daraus entstehen.

Warum es das Modul ueberhaupt gibt
----------------------------------
Das Dashboard konnte nur den Jetzt-Zustand zeigen. Auf die einzige
Frage, die man vor einem Zahlenfeld stellt -- "wird es mehr oder
weniger?" -- gab es nirgends eine Antwort, weil niemand Vergangenheit
gespeichert hat.

Was hier geprueft wird, und warum genau das
-------------------------------------------
  1. **Eine Luecke ist keine Null.** Ein Tag ohne Messung liefert
     ``None``. Ohne diese Unterscheidung saehe ein Tag, an dem der Bot
     aus war, aus wie ein Tag ohne einen einzigen Beitritt -- ein
     Ausfall der Messung wie ein Einbruch der Zahl.
  2. **Ein Schnappschuss loescht keine Zaehler.** ``INSERT OR
     REPLACE`` haette die bereits gezaehlten Beitritte des Tages jedes
     Mal auf null gesetzt.
  3. **Neue Spalten per ALTER TABLE.** ``CREATE TABLE IF NOT EXISTS``
     aendert an einer bestehenden Tabelle nichts -- bei ``team_update``
     ist genau daran "no such column: updated_at" entstanden.
  4. **``totals()`` mit leerer Serverliste summiert nicht alles.**
     Sonst saehe jemand ohne einen einzigen Server die Zahlen des
     ganzen Bots.
  5. Die Oberflaeche: das mehrreihige Diagramm, die Einbindung an den
     drei Stellen, der Proxy-Eintrag. Der fehlende Proxy-Eintrag ist
     der Fehler, der in diesem Repo am oeftesten passiert ist -- der
     Reiter ist sichtbar und gibt beim Klick 404.

Run:  python3 tests/test_guild_history.py
"""

import ast
import asyncio
import os
import re
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

from utils import guild_history as store  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370
GUILD2 = 1530349205372145715


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
    """Kommentare raus.

    Sonst trifft eine Suche die eigene Erklaerung darueber statt den
    Code -- eine Falle, in die dieses Repo mehrfach getappt ist.
    """
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def benutzt(src: str, name: str) -> bool:
    """Wird der Baustein wirklich gerendert?

    Nicht ``"<Name" in src``: das trifft auch ``<NameX``, und genau so
    ist im Mutationstest eine umbenannte -- also nirgends definierte --
    Komponente durchgerutscht. Der Test blieb gruen, obwohl die Seite
    den Baustein gar nicht mehr enthielt.
    """
    return re.search(rf"<{name}\b", src) is not None


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        baum = ast.parse(src)
    except SyntaxError:
        return src
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(knoten, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


# ══════════════════════════════════════════════════════════════════════
#  Verhalten -- echtes SQLite, keine Attrappe
# ══════════════════════════════════════════════════════════════════════


async def test_luecke_ist_keine_null():
    print("\nEine Luecke ist keine Null")

    ordner = tempfile.mkdtemp()
    store.DB_PATH = os.path.join(ordner, "h.db")

    reihe = await store.series(GUILD, 5)
    check("die Achse hat alle Tage", len(reihe["days"]) == 5, reihe["days"])
    check(
        "ohne Messung ist jeder Wert None",
        all(w is None for w in reihe["members"])
        and all(w is None for w in reihe["joins"])
        and all(w is None for w in reihe["leaves"]),
        f"{reihe['joins']}",
    )
    check("und nichts gilt als gemessen", reihe["measured"] == [])

    # Ein Tag mit Messung, aber ohne Beitritte: das ist eine echte Null.
    await store.snapshot(GUILD, 100)
    reihe = await store.series(GUILD, 5)
    check(
        "gemessen und nichts passiert ergibt 0, nicht None",
        reihe["joins"][-1] == 0,
        f"{reihe['joins'][-1]!r}",
    )
    check(
        "die Vortage bleiben None",
        all(w is None for w in reihe["joins"][:-1]),
        f"{reihe['joins']}",
    )


async def test_schnappschuss_loescht_nichts():
    print("\nEin Schnappschuss loescht keine Zaehler")

    ordner = tempfile.mkdtemp()
    store.DB_PATH = os.path.join(ordner, "h.db")

    await store.record_join(GUILD)
    await store.record_join(GUILD)
    await store.record_leave(GUILD)
    await store.snapshot(GUILD, 4714)

    reihe = await store.series(GUILD, 3)
    check("zwei Beitritte", reihe["joins"][-1] == 2, f"{reihe['joins'][-1]}")
    check("ein Austritt", reihe["leaves"][-1] == 1)
    check("der Stand kam an", reihe["members"][-1] == 4714)

    # Der zweite Schnappschuss ist der Fall, den INSERT OR REPLACE
    # kaputt gemacht haette.
    await store.snapshot(GUILD, 4720)
    reihe = await store.series(GUILD, 3)
    check(
        "nach dem zweiten Schnappschuss stehen die Beitritte noch",
        reihe["joins"][-1] == 2,
        f"{reihe['joins'][-1]}",
    )
    check("und der Stand ist der neue", reihe["members"][-1] == 4720)

    # Ein Beitritt nach dem Schnappschuss zaehlt weiter hoch.
    await store.record_join(GUILD, 4721)
    reihe = await store.series(GUILD, 3)
    check("weiter gezaehlt", reihe["joins"][-1] == 3, f"{reihe['joins'][-1]}")
    check("und der mitgegebene Stand gilt", reihe["members"][-1] == 4721)


async def test_neue_spalte():
    print("\nEine neue Spalte wird nachgeruestet")

    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "alt.db")

    # Die Tabelle, wie sie vor der Erweiterung aussah: ohne updated_at.
    conn = sqlite3.connect(pfad)
    conn.execute(
        "CREATE TABLE guild_daily (guild_id TEXT NOT NULL, day TEXT NOT NULL,"
        " members INTEGER, joins INTEGER NOT NULL DEFAULT 0,"
        " leaves INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (guild_id, day))"
    )
    conn.execute(
        "INSERT INTO guild_daily (guild_id, day, members, joins, leaves)"
        " VALUES (?, '2020-01-01', 5, 1, 0)",
        (str(GUILD),),
    )
    conn.commit()
    conn.close()

    store.DB_PATH = pfad
    fehler = ""
    try:
        await store.record_join(GUILD)
    except Exception as exc:
        fehler = str(exc)
    check("kein 'no such column'", not fehler, fehler)

    spalten = {
        z[1] for z in sqlite3.connect(pfad).execute("PRAGMA table_info(guild_daily)")
    }
    check("updated_at ist da", "updated_at" in spalten, str(sorted(spalten)))
    check(
        "die alte Zeile hat ueberlebt",
        sqlite3.connect(pfad)
        .execute("SELECT joins FROM guild_daily WHERE day = '2020-01-01'")
        .fetchone()[0]
        == 1,
    )

    # Die Spaltenliste steht nur an EINER Stelle. Zwei handgepflegte
    # Listen laufen auseinander -- genau so entstand der team_update-
    # Fehler.
    quelle = strip_py(read("utils", "guild_history.py"))
    check(
        "das Schema leitet sich aus COLUMNS ab",
        "for name, typ in COLUMNS" in quelle,
        "eine zweite handgepflegte Liste laeuft irgendwann auseinander",
    )
    check(
        "und die Nachruestung ebenfalls",
        quelle.count("COLUMNS") >= 3,
        "CREATE, PRAGMA-Abgleich und ALTER muessen dieselbe Liste nutzen",
    )


async def test_totals():
    print("\nDie Summe ueber alle Server")

    ordner = tempfile.mkdtemp()
    store.DB_PATH = os.path.join(ordner, "h.db")

    await store.record_join(GUILD)
    await store.snapshot(GUILD, 100)
    await store.record_join(GUILD2)
    await store.record_join(GUILD2)
    await store.snapshot(GUILD2, 50)

    alle = await store.totals(3)
    check("beide Staende addiert", alle["members"][-1] == 150, f"{alle['members'][-1]}")
    check("beide Beitritte addiert", alle["joins"][-1] == 3, f"{alle['joins'][-1]}")
    check("has_data stimmt", alle["has_data"] is True)

    einer = await store.totals(3, [str(GUILD)])
    check("eingegrenzt zaehlt nur den einen", einer["members"][-1] == 100)
    check("und dessen Beitritte", einer["joins"][-1] == 1)

    # Der gefaehrliche Fall: eine leere Liste darf nicht "alles" heissen.
    keiner = await store.totals(3, [])
    check(
        "leere Liste summiert NICHT alle Server",
        all(w is None for w in keiner["members"]),
        f"{keiner['members']}",
    )
    check("und meldet has_data=False", keiner["has_data"] is False)

    # Zwei Schichten schuetzen hier dasselbe: der fruehe Ausstieg oben
    # UND der Filter in der Schleife. Deckt eine die andere ab, faellt
    # nicht auf, wenn eine davon kaputtgeht -- im Mutationstest genau
    # so passiert. Also jede Schicht einzeln pruefen.
    #
    # Der fruehe Ausstieg ist daran zu erkennen, dass er die Datenbank
    # gar nicht erst anfasst. Bei jemandem ohne einen einzigen Server
    # waere das sonst ein voller Durchlauf durch die ganze Tabelle.
    from utils import db_paths

    original = db_paths.connect
    beruehrt = {"ja": False}

    def gezaehlt(*args, **kwargs):
        beruehrt["ja"] = True
        return original(*args, **kwargs)

    db_paths.connect = gezaehlt
    try:
        await store.totals(3, [])
        ohne_server = beruehrt["ja"]
        beruehrt["ja"] = False
        await store.totals(3, [str(GUILD)])
        mit_server = beruehrt["ja"]
    finally:
        db_paths.connect = original

    check(
        "ohne Server wird die Datenbank gar nicht geoeffnet",
        ohne_server is False,
        "sonst laeuft fuer jemanden ohne Server ein voller Tabellendurchlauf",
    )
    check(
        "mit Server aber schon",
        mit_server is True,
        "sonst prueft die Zeile darueber nur, dass nichts passiert",
    )


async def test_zeitraum_grenzen():
    print("\nDer Zeitraum bleibt in seinen Grenzen")

    check("mindestens ein Tag", len(store.tage_zurueck(0)) == 1)
    check("mindestens ein Tag auch bei -5", len(store.tage_zurueck(-5)) == 1)
    check(
        "nicht mehr als die Aufbewahrung",
        len(store.tage_zurueck(9999)) == store.KEEP_DAYS,
        f"{len(store.tage_zurueck(9999))}",
    )
    tage = store.tage_zurueck(3)
    check("aeltester zuerst", tage == sorted(tage), str(tage))


# ══════════════════════════════════════════════════════════════════════
#  Die Oberflaeche
# ══════════════════════════════════════════════════════════════════════


def test_mehrreihiges_diagramm():
    print("\nDas Diagramm kann mehrere Linien")

    src = strip_ts(read_dash("components", "ui", "line-chart.tsx"))

    check("es gibt MultiLineChart", "export function MultiLineChart" in src)
    check("mit einer Reihen-Schnittstelle", "export interface Reihe" in src)

    # Eine gemeinsame Achse ueber alle Reihen. Je Reihe eine eigene
    # hiesse: zwei Linien, die sich kreuzen, ohne sich zu schneiden.
    check(
        "eine gemeinsame Achse ueber alle sichtbaren Reihen",
        "sichtbar.flatMap" in src and "achse(alle)" in src,
        "je Reihe eine eigene Achse macht den Vergleich wertlos",
    )

    # Die Luecke -- derselbe Fehler wie beim einreihigen Diagramm.
    zweig = ""
    if "if (wert === null) {" in src:
        zweig = src.split("if (wert === null) {", 1)[1].split("}", 1)[0]
    check(
        "eine Luecke unterbricht auch hier den Pfad",
        "luecke = true" in zweig and 'luecke ? "M" : "L"' in src,
        "sonst zieht die Linie quer darueber",
    )

    check(
        "die letzte Beschriftung wird nicht abgeschnitten",
        'i === labels.length - 1 ? "end"' in src,
        "mittig zentriert ragt sie ueber den Rand",
    )

    # Die letzte sichtbare Reihe darf nicht ausblendbar sein: ein
    # leeres Gitter beantwortet keine Frage.
    check(
        "die letzte Reihe laesst sich nicht ausblenden",
        "neu.size < reihen.length - 1" in src,
        "sonst steht da ein leeres Gitter",
    )


def test_achse_und_marken():
    """Zwei Fehler, die erst im gerenderten Bild aufgefallen sind."""
    print("\nDie Achse zeigt keine Zahl doppelt")

    src = strip_ts(read_dash("components", "ui", "line-chart.tsx"))

    # Fehler 1: `kurz()` schreibt ab 10.000 ohne Nachkommastelle. Bei
    # einer Achse von 48.200 bis 50.600 wurden 49.400 und 50.000 beide
    # zu "50k" -- zwei Gitterlinien mit derselben Zahl.
    check(
        "es gibt eine eigene Achsen-Beschriftung",
        "function achsenBeschriftung(" in src,
        "kurz() allein rundet zwei Gitterwerte auf dieselbe Zahl",
    )
    check(
        "die Stellen richten sich nach dem Gitterschritt",
        "const schritt = spanne / (GITTER - 1);" in src
        and "schritt >= 1000 ? 0 : schritt >= 100 ? 1 : 2" in src,
    )
    # Sie muss auch wirklich benutzt werden -- in BEIDEN Diagrammen.
    check(
        "beide Diagramme benutzen sie",
        src.count("achsenBeschriftung(spanne, achsStellen)") == 2
        and src.count("{yText(wert)}") == 2,
        "eine Funktion, die niemand aufruft, behebt nichts",
    )
    check(
        "die alte, kuerzende Fassung steht nicht mehr an der Achse",
        "{kurz(wert, achsStellen)}" not in src,
    )

    print("\nDie Datumsangaben ueberlappen nicht")

    # Fehler 2: "jede n-te und immer die letzte" -- geht die Reihe
    # nicht glatt auf, standen "12. Aug." und "13. Aug." uebereinander.
    check(
        "es gibt eine eigene Markenauswahl",
        "function sichtbareMarken(" in src,
    )
    check(
        "eine zu dichte vorletzte Marke faellt weg",
        "marken.delete(i)" in src and "letzte - i <" in src,
        "sonst klebt die vorletzte an der letzten",
    )
    check(
        "die letzte bleibt aber immer stehen",
        "marken.add(letzte);" in src,
        "sie sagt, bis wann die Zahlen reichen",
    )
    check(
        "beide Diagramme benutzen sie",
        src.count("sichtbareMarken(") == 3,
        "einmal die Definition, zweimal der Aufruf",
    )
    check(
        "die alte Auswahl ist weg",
        "i % schritt === 0" not in src,
    )


def test_verlauf_panels():
    print("\nDie Verlaufs-Bausteine")

    fuer_server = strip_ts(read_dash("components", "dashboard", "history-charts.tsx"))
    check("es gibt HistoryCharts", "export function HistoryCharts" in fuer_server)
    check("es holt den Server-Verlauf", "getGuildHistory" in fuer_server)
    check(
        "Beitritte und Austritte teilen sich ein Bild",
        "<MultiLineChart" in fuer_server
        and "Beitritte" in fuer_server
        and "Austritte" in fuer_server,
        "getrennte Bilder haben getrennte Achsen -- dann ist der Vergleich weg",
    )
    check(
        "Mitglieder bekommen ein eigenes Bild",
        fuer_server.count("<LineChart") >= 2,
        "in einem Bild mit den Beitritten waere deren Linie ein Strich am Boden",
    )
    # Eine veraltete Antwort darf die neue nicht ueberschreiben.
    #
    # Nicht pruefen, ob das Wort "abgebrochen" vorkommt: die Variable
    # steht auch dann noch da, wenn der Riegel VOR setData weggefallen
    # ist. Genau so ist die Mutation durchgerutscht. Geprueft wird
    # deshalb die Benutzung -- setData muss hinter der Bedingung
    # stehen.
    check(
        "ein spaeter eintreffendes altes Ergebnis wird verworfen",
        "if (!abgebrochen) setData(antwort);" in fuer_server,
        "sonst steht nach einem schnellen Wechsel der falsche Zeitraum im Bild",
    )
    check(
        "und der Riegel wird beim Aufraeumen gesetzt",
        "abgebrochen = true;" in fuer_server,
        "ohne das Setzen ist die Bedingung immer wahr",
    )
    # Der Hinweis muss auch erreichbar sein. `has_data` kommt im Code
    # ebenso vor, wenn der Zweig auf `false` steht -- dann ist der
    # Text da und wird nie gezeigt.
    check(
        "der Fall 'noch nichts gemessen' wird erklaert",
        "!data.has_data ?" in fuer_server and "Noch keine Messungen" in fuer_server,
        "ein leeres Gitter sagt nicht, warum es leer ist",
    )

    global_ = strip_ts(read_dash("components", "dashboard", "overview-charts.tsx"))
    check("es gibt OverviewCharts", "export function OverviewCharts" in global_)
    check("es holt den globalen Verlauf", "getAdminHistory" in global_)
    check(
        "auch hier wird die alte Antwort verworfen",
        "if (!abgebrochen) setData(antwort);" in global_,
    )
    check(
        "und auch hier der Riegel gesetzt",
        "abgebrochen = true;" in global_,
    )


def test_eingebaut():
    print("\nDie Diagramme sind auch eingebaut")

    # Server-Uebersicht.
    uebersicht = strip_ts(
        read_dash("app", "dashboard", "guild", "[guildId]", "page.tsx")
    )
    check(
        "die Server-Uebersicht bindet sie ein",
        benutzt(uebersicht, "HistoryCharts") and "history-charts" in uebersicht,
    )

    # Admin-Bereich.
    admin = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))
    check(
        "der Admin-Bereich bindet sie ein",
        benutzt(admin, "OverviewCharts") and "overview-charts" in admin,
    )

    # Einstiegsseite.
    start = strip_ts(read_dash("app", "dashboard", "page.tsx"))
    check(
        "die Einstiegsseite bindet sie ein",
        benutzt(start, "MyServersChart") and "my-servers-chart" in start,
    )

    meine = strip_ts(read_dash("components", "dashboard", "my-servers-chart.tsx"))
    check(
        "sie nutzt den Server-Endpunkt, nicht den Admin-Endpunkt",
        "HistoryCharts" in meine and "getAdminHistory" not in meine,
        "der Admin-Endpunkt verlangt metrics.view -- ein Server-Inhaber hat das nicht",
    )
    check(
        "ein Serverwechsel setzt das Diagramm zurueck",
        "key={aktiv}" in meine,
        "sonst steht kurz die Kurve des falschen Servers unter dem neuen Namen",
    )


def test_api_und_proxy():
    print("\nDie Route ist erreichbar")

    routen = strip_py(read("api", "routes", "guilds.py"))
    check(
        "der Server-Endpunkt existiert",
        '@router.get("/{guild_id}/history"' in routen,
    )
    check(
        "ein Tag ohne Messung bleibt None",
        "befehle.append(None)" in routen,
        "0 hiesse 'keine Befehle', nicht 'nicht gemessen'",
    )

    admin_routen = strip_py(read("api", "routes", "admin.py"))
    check(
        "der Admin-Endpunkt existiert",
        '@router.get("/history"' in admin_routen,
    )

    # Der Fehler, der in diesem Repo am oeftesten passiert ist: die
    # Route steht da, der Proxy kennt sie nicht, und der Reiter gibt
    # beim Klick 404 "Unknown API scope".
    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    check(
        "der Proxy kennt /admin/history",
        re.search(r"\bhistory:\s*\{\s*GET:", proxy) is not None,
        "sonst 403/404 beim Klick, obwohl die Route existiert",
    )

    api_ts = strip_ts(read_dash("lib", "api.ts"))
    check("getGuildHistory ist verdrahtet", "getGuildHistory:" in api_ts)
    check("getAdminHistory ist verdrahtet", "getAdminHistory:" in api_ts)
    check(
        "beide zeigen auf die richtige Route",
        "/guilds/${guildId}/history" in api_ts and "/admin/history" in api_ts,
    )


def test_cog_ist_geladen():
    print("\nDer Mitschnitt laeuft auch")

    init = strip_py(read("cogs", "__init__.py"))
    check(
        "der Cog wird importiert",
        "from .events.guild_history import GuildHistory" in init,
    )
    # Import allein reicht nicht -- ohne add_cog laeuft nichts.
    check(
        "und auch geladen",
        "await bot.add_cog(GuildHistory(bot))" in init,
        "ohne add_cog ist der Cog toter Code",
    )

    cog = strip_py(read("cogs", "events", "guild_history.py"))
    check("es hoert auf Beitritte", "async def on_member_join" in cog)
    check("es hoert auf Austritte", "async def on_member_remove" in cog)
    check(
        "und misst regelmaessig nach",
        "@tasks.loop(minutes=SNAPSHOT_MINUTEN)" in cog,
        "ohne Schnappschuss fehlt der Tag, an dem nichts passiert ist",
    )
    check(
        "der Schnappschuss wartet auf den Verbindungsaufbau",
        "wait_until_ready" in cog,
        "vorher ist client.guilds leer",
    )
    # Buchhaltung darf nie ein Ereignis stoeren.
    check(
        "Fehler beim Zaehlen verschlucken keinen Beitritt",
        cog.count("except Exception") >= 3,
    )


def test_admin_optik():
    print("\nDer Admin-Bereich hat wieder Form")

    src = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))

    # Der alte, laute Look bleibt weg.
    for laut, was in (
        ("admin-glass", "Glaskarten"),
        ("admin-hero", "Farbverlauf im Kopf"),
        ("useProximity", "Naeherungseffekt"),
        ("prox-tab", "verschiebende Knoepfe"),
        ("<Reveal", "Einblend-Animation"),
        ("shadow-primary/25", "Schlagschatten"),
        ("group-hover:scale-110", "wachsende Symbole"),
        ("font-outfit", "zweite Schriftart"),
    ):
        check(f"kein {was}", laut not in src, laut)

    # Und das, was jetzt gilt: vier Felder statt einer Textzeile.
    check(
        "die Zahlen stehen in vier Feldern",
        "grid grid-cols-2 gap-3 lg:grid-cols-4" in src,
        "eine einzige Zeile las sich als ein Satz statt als vier Angaben",
    )
    check(
        "und die Farbe steckt im Symbol",
        "stat.color" in src,
        "ohne Zuordnung sind vier graue Zahlen nebeneinander",
    )
    check(
        "der Kopf hat eine eigene Flaeche",
        "rounded-2xl border border-slate-800 bg-[#131318] px-5 py-4" in src,
    )
    # Zwei Navigationsebenen muessen sich unterscheiden lassen.
    check(
        "die Gruppen tragen eine Linie",
        "border-b-2" in src and "border-indigo-500" in src,
        "gleich aussehende Zeilen uebereinander lesen sich nicht als Ebenen",
    )
    check(
        "die Reiter tragen eine Flaeche",
        "border-indigo-500/30 bg-indigo-500/10" in src,
    )


def test_alles_auf_deutsch():
    """Im Screenshot aufgefallen: die halbe Seite stand auf Englisch.

    "Active Servers", "Database Size", "Members", "Channels" -- direkt
    neben "Server waehlen, dann Moderation und Verwaltung erledigen."
    Dazu jede Meldung ("Please select a server first.") und jede
    Aktionskarte ("Ban a user from the server.").

    Ausgenommen bleiben die `action`-Werte: die gehen an die API und
    duerfen sich nicht aendern. Genau deshalb wird hier nach `label:`
    und `desc:` gesucht und nicht nach beliebigen englischen Woertern.
    """
    print("\nDer Admin-Bereich ist auf Deutsch")

    src = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))

    # Beschriftungen, die im Bild zu sehen waren.
    for wort in (
        'label: "Members"', 'label: "Channels"', 'label: "Broadcast"',
        'label: "Health"', 'label: "Features"', 'label: "Servers"',
        'label: "Dashboard Users"',
        'name: "Active Servers"', 'name: "Database Size"',
        'name: "API Latency"', 'name: "Gesamte Nutzer"',
        'label: "Ban"', 'label: "Kick"', 'label: "Mute"', 'label: "Unmute"',
        'label: "Create Text Channel"', 'label: "Purge Messages"',
        'label: "Scan Webhooks"', 'label: "Audit Summary"',
    ):
        check(f"kein {wort}", wort not in src, "steht auf einer deutschen Seite")

    # Die Meldungen, die bei jeder Aktion aufpoppen.
    for satz in (
        "Please select a server first.",
        "Please enter a valid User ID.",
        "Please enter a reason.",
        "Action failed.",
        "Failed to load real-time data",
        "Failed to update maintenance mode",
    ):
        check(f"keine Meldung »{satz[:28]}«", satz not in src)

    # Und die Beschreibungen unter den Karten.
    englische_desc = re.findall(r'desc:\s*"([^"]+)"', src)
    verdaechtig = [
        d for d in englische_desc
        if re.search(r"\b(the|a|to|from|with|selected|member|server)\b", d)
    ]
    check(
        "keine englische Kartenbeschreibung",
        not verdaechtig,
        f"{verdaechtig[:3]}",
    )

    # `needs` traegt die technischen Schluessel. Wurden die roh
    # angezeigt, stand woertlich "Braucht: channel, amount" da.
    check(
        "die Pflichtfelder werden uebersetzt angezeigt",
        "BRAUCHT[n]" in src and 'channel: "Kanal"' in src,
        "sonst steht »Braucht: channel, amount« auf einer deutschen Seite",
    )

    # Der Grund landet im Discord-Auditlog und steht dort dauerhaft.
    check(
        "der voreingestellte Grund ist deutsch",
        '"Dashboard admin action"' not in src,
        "der Text steht dauerhaft im Discord-Auditlog",
    )

    # Die technischen Schluessel duerfen NICHT uebersetzt sein --
    # sonst nimmt die API die Aktion nicht mehr an.
    for aktion in ('action: "ban"', 'action: "purge"',
                   'action: "create_text_channel"', 'action: "scan_webhooks"'):
        check(f"{aktion} ist unveraendert", aktion in src,
              "die API kennt nur den englischen Schluessel")


async def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    await test_luecke_ist_keine_null()
    await test_schnappschuss_loescht_nichts()
    await test_neue_spalte()
    await test_totals()
    await test_zeitraum_grenzen()

    test_mehrreihiges_diagramm()
    test_achse_und_marken()
    test_verlauf_panels()
    test_eingebaut()
    test_api_und_proxy()
    test_cog_ist_geladen()
    test_admin_optik()
    test_alles_auf_deutsch()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
