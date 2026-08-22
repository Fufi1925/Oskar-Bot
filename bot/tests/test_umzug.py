#!/usr/bin/env python3
"""
Der neue Umzugsweg gegen genau die Faelle, an denen der alte scheitert.

Fall 1: neues Konto ist LEER (bug_umzug_leer.py: 4 Zeilen -> 0)
Fall 2: der Schluessel db/template_secret.key (bug_umzug.py: 1 -> 0)
Fall 3: offene Tickets, Panels, eigene Texte
Fall 4: Zip-Slip -- ein boesartiges Archiv darf nicht ausbrechen

Run:   python3 tests/test_umzug.py
"""

import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

ARBEIT = tempfile.mkdtemp(prefix="umzugneu-")
ALT = os.path.join(ARBEIT, "alt")
NEU = os.path.join(ARBEIT, "neu")
GILDE = 1530378233579704370

fehler = []

#: Wohin am Ende zurueckgekehrt wird. run_all.py startet jeden Test
#: mit cwd=bot/; bliebe der Wechsel stehen, liefen die naechsten
#: Tests im Ordner dieses Versuchs.
START_ORDNER = os.getcwd()


def linie(t):
    print()
    print("=" * 70)
    print(t)
    print("=" * 70)


def pruefe(name, ok, hinweis=""):
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        fehler.append(name)


def baue_alt():
    """Die Installation auf dem alten Konto -- so realistisch wie moeglich."""
    os.makedirs(os.path.join(ALT, "db"), exist_ok=True)
    os.makedirs(os.path.join(ALT, "jsondb"), exist_ok=True)

    conn = sqlite3.connect(os.path.join(ALT, "db", "tickets.db"))
    conn.executescript(
        """
        CREATE TABLE guild_configs (guild_id INTEGER PRIMARY KEY, welcome_text TEXT);
        CREATE TABLE ticket_categories (id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER, name TEXT, emoji TEXT);
        CREATE TABLE open_tickets (channel_id INTEGER PRIMARY KEY, guild_id INTEGER,
            user_id INTEGER, betreff TEXT);
        CREATE TABLE ticket_panels (guild_id INTEGER, channel_id INTEGER,
            message_id INTEGER, titel TEXT);
        """
    )
    conn.execute(
        "INSERT INTO guild_configs VALUES (?,?)",
        (GILDE, "Willkommen im Ticket! Beschreibe bitte dein Anliegen. äöü ✅"),
    )
    for n, e in [("Allgemein", "❓"), ("Bewerbung", "📝"), ("Beschwerde", "⚠️")]:
        conn.execute(
            "INSERT INTO ticket_categories (guild_id, name, emoji) VALUES (?,?,?)",
            (GILDE, n, e),
        )
    for k, u, b in [
        (900001, 111, "Mein Rang fehlt"),
        (900002, 222, "Bewerbung Moderator"),
        (900003, 333, "Frage zu Premium"),
    ]:
        conn.execute("INSERT INTO open_tickets VALUES (?,?,?,?)", (k, GILDE, u, b))
    conn.execute(
        "INSERT INTO ticket_panels VALUES (?,?,?,?)",
        (GILDE, 850001, 860001, "Support-Panel"),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(os.path.join(ALT, "db", "welcome.db"))
    conn.execute("CREATE TABLE welcome (guild_id INTEGER PRIMARY KEY, message TEXT)")
    conn.execute(
        "INSERT INTO welcome VALUES (?,?)", (GILDE, "Hey {user}, willkommen! 🎉")
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(os.path.join(ALT, "db", "leveling.db"))
    conn.execute("CREATE TABLE levels (guild_id INTEGER, user_id INTEGER, xp INTEGER)")
    for u, x in [(111, 15400), (222, 9800), (333, 120)]:
        conn.execute("INSERT INTO levels VALUES (?,?,?)", (GILDE, u, x))
    conn.commit()
    conn.close()

    # Ausserhalb von db/
    conn = sqlite3.connect(os.path.join(ALT, "rr.db"))
    conn.execute("CREATE TABLE rr (guild_id INTEGER, emoji TEXT, role_id INTEGER)")
    conn.execute("INSERT INTO rr VALUES (?,?,?)", (GILDE, "🎮", 777))
    conn.commit()
    conn.close()

    # Der Schluessel -- keine Datenbank.
    with open(os.path.join(ALT, "db", "template_secret.key"), "wb") as f:
        f.write(b"0123456789abcdef0123456789abcdef")

    with open(os.path.join(ALT, "jsondb", "joindm_messages.json"), "w") as f:
        json.dump({str(GILDE): "Danke fuers Beitreten!"}, f)

    # Eine Journal-Datei, die NICHT mitkommen darf.
    with open(os.path.join(ALT, "db", "tickets.db-journal"), "wb") as f:
        f.write(b"muell")


def inhalt(wurzel):
    """Alle Tabellenzeilen + Zusatzdateien als vergleichbares Abbild."""
    ergebnis = {}
    db_ordner = os.path.join(wurzel, "db")
    dateien = []
    if os.path.isdir(db_ordner):
        dateien += [
            os.path.join(db_ordner, n)
            for n in sorted(os.listdir(db_ordner))
            if n.endswith(".db")
        ]
    for extra in ("rr.db", "j2c_data.db"):
        p = os.path.join(wurzel, extra)
        if os.path.exists(p):
            dateien.append(p)

    for pfad in dateien:
        name = os.path.relpath(pfad, wurzel)
        conn = sqlite3.connect(pfad)
        for (tab,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            zeilen = conn.execute(f"SELECT * FROM [{tab}] ORDER BY 1").fetchall()
            ergebnis[f"{name}:{tab}"] = zeilen
        conn.close()

    for zusatz in ("db/template_secret.key", "jsondb/joindm_messages.json"):
        p = os.path.join(wurzel, zusatz)
        ergebnis[f"DATEI {zusatz}"] = open(p, "rb").read() if os.path.exists(p) else None

    return ergebnis



def test_sicherung_vor_dem_ueberschreiben():
    """Der alte Stand muss weggesichert werden, bevor etwas ueberschrieben wird.

    Vorher lief im ganzen Test kein einziger Aufruf mit
    sicherung=True -- die Sicherung haette komplett fehlen koennen,
    ohne dass es auffiel.
    """
    linie("7  Sicherung vor dem Ueberschreiben")

    import io as _io
    import zipfile as _zip

    ordner = tempfile.mkdtemp(prefix="umzugsich-")
    os.makedirs(os.path.join(ordner, "db"), exist_ok=True)

    # Ein vorhandener Stand, der ueberschrieben wird.
    alt_db = os.path.join(ordner, "db", "vorher.db")
    conn = sqlite3.connect(alt_db)
    conn.execute("CREATE TABLE a (x TEXT)")
    conn.execute("INSERT INTO a VALUES ('DAS WAR VORHER DA')")
    conn.commit()
    conn.close()

    os.chdir(ordner)
    import importlib
    from api import umzug as _u
    importlib.reload(_u)

    # Ein Archiv, das genau diese Datei ersetzt.
    puffer = _io.BytesIO()
    with _zip.ZipFile(puffer, "w") as z:
        z.writestr("db/vorher.db", open(alt_db, "rb").read())

    ergebnis = _u.spiele_archiv_ein(puffer.getvalue(), sicherung=True)

    pruefe("ein Sicherungsordner wird angelegt",
           bool(ergebnis.get("sicherung")),
           "ohne ihn gibt es keinen Weg zurueck")

    if ergebnis.get("sicherung"):
        voll = os.path.join(ordner, ergebnis["sicherung"])
        pruefe("der Ordner liegt wirklich da", os.path.isdir(voll), voll)
        inhalt_ordner = os.listdir(voll) if os.path.isdir(voll) else []
        pruefe("der alte Stand ist darin gesichert",
               any("vorher" in n for n in inhalt_ordner),
               str(inhalt_ordner))

    os.chdir(START_ORDNER)


def test_panel_und_routen():
    """Die Oberflaeche und die Routen haengen zusammen -- beides pruefen."""
    linie("8  Dashboard und Routen")

    dash = os.path.join(os.path.dirname(BOT), "dashboard")
    panel = os.path.join(dash, "components", "dashboard", "umzug-panel.tsx")

    pruefe("das Umzugs-Panel gibt es", os.path.isfile(panel))
    if not os.path.isfile(panel):
        return

    quelle = open(panel, encoding="utf-8").read()

    for pfad in ("umzug/uebersicht", "umzug/download", "umzug/pruefen",
                 "umzug/einspielen"):
        pruefe(f"das Panel ruft {pfad} auf", pfad in quelle)

    # Ein ZIP darf nicht als JSON verschickt werden -- sonst kommt es
    # beschaedigt an.
    # Auf die Benutzung zielen, nicht auf das Wort.
    #
    # "application/zip" steht auch im accept-Attribut des Dateifelds.
    # Eine Pruefung auf blosses Vorkommen blieb deshalb gruen, als der
    # Upload versehentlich als JSON verschickt wurde -- im
    # Mutationstest nachgestellt. Also die Kopfzeile beider
    # Sende-Aufrufe pruefen.
    zip_kopfzeilen = re.findall(
        r'headers:\s*\{\s*"Content-Type":\s*"application/zip"\s*\}', quelle
    )
    pruefe("beide Uploads senden Content-Type application/zip",
           len(zip_kopfzeilen) >= 2,
           f"gefunden: {len(zip_kopfzeilen)} -- als JSON kommt das Archiv kaputt an")

    pruefe("kein Upload geht als JSON raus",
           not re.search(
               r'/umzug/(pruefen|einspielen)[\s\S]{0,300}?'
               r'"Content-Type":\s*"application/json"',
               quelle),
           "JSON wuerde das Archiv beim Umkodieren zerstoeren")

    # Der Reiter muss das Panel auch wirklich einbinden.
    reiter = os.path.join(dash, "components", "dashboard", "backups-panel.tsx")
    reiter_quelle = open(reiter, encoding="utf-8").read()
    pruefe("der Sicherungs-Reiter bindet das Panel ein",
           "<UmzugPanel />" in reiter_quelle)
    pruefe("es wird auch importiert",
           "umzug-panel" in reiter_quelle)

    # Und die API-Seite.
    admin = open(os.path.join(BOT, "api", "routes", "admin.py"), encoding="utf-8").read()
    for route in ("/umzug/uebersicht", "/umzug/download", "/umzug/pruefen",
                  "/umzug/einspielen"):
        pruefe(f"die Route {route} ist gebaut", f'"{route}"' in admin)

    # Der Upload darf NICHT ueber request.body() laufen: das haelt ein
    # Gigabyte-Archiv komplett im Arbeitsspeicher.
    rumpf = admin[admin.find("async def _hochgeladenes_archiv"):]
    rumpf = rumpf[:rumpf.find('@router.post("/umzug/einspielen')]

    # Kommentare und Docstrings raus, BEVOR gesucht wird.
    #
    # Ohne das schlug diese Pruefung faelschlich an: in der Begruendung
    # ueber der Funktion steht woertlich "NICHT `await request.body()`",
    # und die Suche fand ihre eigene Erklaerung. Geprueft werden soll
    # der Code, nicht die Prosa darueber.
    ohne_doc = re.sub(r'"""[\s\S]*?"""', "", rumpf)
    ohne_kommentar = re.sub(r"#[^\n]*", "", ohne_doc)

    pruefe("der Upload wird gestreamt, nicht in den Speicher geladen",
           "request.stream()" in ohne_kommentar
           and "request.body()" not in ohne_kommentar,
           "request.body() wuerde bei GB-Archiven den Container sprengen")

    # Der Proxy muss binaere Uploads durchreichen.
    proxy = open(os.path.join(dash, "app", "api", "bot", "[...path]", "route.ts"),
                 encoding="utf-8").read()
    pruefe("der Proxy reicht ZIP-Uploads unveraendert weiter",
           "arrayBuffer()" in proxy and "zip" in proxy.lower(),
           "request.text() wuerde jedes Nicht-UTF-8-Byte ersetzen")


def main():
    baue_alt()
    vorher = inhalt(ALT)

    linie("1  Archiv auf dem alten Konto bauen")
    os.chdir(ALT)
    from api import umzug

    uebersicht = umzug.baue_uebersicht()
    print(f"  Dateien:      {uebersicht['datei_anzahl']}")
    print(f"  Datenbanken:  {uebersicht['datenbanken']}")
    print(f"  Zeilen:       {uebersicht['zeilen_gesamt']}")
    print(f"  Groesse:      {uebersicht['bytes_gesamt']} Bytes")
    for e in uebersicht["dateien"]:
        print(f"    {e['bytes']:>8}  {e['pfad']}")

    puffer = io.BytesIO()
    umzug.schreibe_archiv_nach(puffer)
    rohdaten = puffer.getvalue()
    print(f"\n  Archiv: {len(rohdaten)} Bytes")

    namen = zipfile.ZipFile(io.BytesIO(rohdaten)).namelist()
    pruefe("der Schluessel ist im Archiv", "db/template_secret.key" in namen)
    pruefe("die JSON-Konfiguration ist dabei",
           "jsondb/joindm_messages.json" in namen)
    pruefe("rr.db ausserhalb von db/ ist dabei", "rr.db" in namen)
    pruefe("die Journal-Datei ist NICHT dabei",
           "db/tickets.db-journal" not in namen,
           "ein altes Journal kann die Datenbank beschaedigen")

    # Zusaetzlich die Filterliste selbst, unabhaengig vom Dateisystem.
    #
    # Die Pruefung darueber allein genuegt nicht: sqlite3.connect()
    # raeumt ein vorgefundenes Journal beim Oeffnen selbsttaetig weg.
    # Beim Zaehlen der Zeilen wird jede Datenbank geoeffnet -- danach
    # ist das Journal verschwunden, und die Pruefung ginge auch dann
    # durch, wenn der Filter komplett fehlte. Genau das ist im
    # Mutationstest passiert.
    for endung in (".db-journal", ".db-wal", ".db-shm"):
        pruefe(f"{endung} steht auf der Ausschlussliste",
               endung in umzug.UEBERSPRINGEN,
               "sonst landet ein Journal im Archiv und beschaedigt die DB")
    pruefe("eine Beschreibung liegt bei", umzug.INFO_NAME in namen)

    # ── Das neue Konto: voellig leer ─────────────────────────────────
    linie("2  Neues Konto: komplett leer (hier scheiterte der alte Weg)")
    os.makedirs(NEU, exist_ok=True)
    os.chdir(NEU)
    print(f"  Inhalt vorher: {os.listdir(NEU) or 'NICHTS'}")

    import importlib
    importlib.reload(umzug)

    linie("3  Pruefen vor dem Einspielen")
    bericht = umzug.pruefe_archiv(rohdaten)
    print(f"  Dateien im Archiv: {bericht['datei_anzahl']}")
    print(f"  Wuerde ueberschreiben: {bericht['ueberschreibt_anzahl']}")
    print(f"  Abgelehnt: {bericht['abgelehnt'] or 'nichts'}")
    pruefe("die Pruefung veraendert nichts", os.listdir(NEU) == [])

    linie("4  Einspielen")
    ergebnis = umzug.spiele_archiv_ein(rohdaten, sicherung=False)
    print(f"  Geschrieben:     {ergebnis['geschrieben']} Dateien")
    print(f"  Fehlgeschlagen:  {ergebnis['fehlgeschlagen'] or 'nichts'}")

    linie("5  Vergleich alt gegen neu -- Zeile fuer Zeile")
    nachher = inhalt(NEU)

    alle = sorted(set(vorher) | set(nachher))
    for k in alle:
        a, n = vorher.get(k), nachher.get(k)
        gleich = a == n
        zeichen = "OK  " if gleich else "FEHLT"
        menge = len(a) if isinstance(a, list) else ("Datei" if a else "-")
        print(f"  {zeichen}  {k:<45} {menge}")
        if not gleich:
            fehler.append(f"Inhalt weicht ab: {k}")

    pruefe("offene Tickets sind vollstaendig da",
           vorher.get("db/tickets.db:open_tickets") == nachher.get("db/tickets.db:open_tickets"))
    pruefe("Panel-Nachrichten sind da",
           vorher.get("db/tickets.db:ticket_panels") == nachher.get("db/tickets.db:ticket_panels"))
    pruefe("eigene Texte mit Umlauten und Emoji stimmen",
           vorher.get("db/tickets.db:guild_configs") == nachher.get("db/tickets.db:guild_configs"))
    pruefe("der Schluessel ist byteweise gleich",
           vorher.get("DATEI db/template_secret.key")
           == nachher.get("DATEI db/template_secret.key"))
    pruefe("XP sind da",
           vorher.get("db/leveling.db:levels") == nachher.get("db/leveling.db:levels"))

    # ── Zip-Slip ─────────────────────────────────────────────────────
    linie("6  Boesartiges Archiv: Ausbruch aus dem Datenordner")
    boese = io.BytesIO()
    with zipfile.ZipFile(boese, "w") as z:
        z.writestr("db/harmlos.db", b"x")
        z.writestr("../../../tmp/ausgebrochen.txt", b"ausgebrochen")
        z.writestr("/tmp/absolut.txt", b"absolut")
    boese_daten = boese.getvalue()

    bericht2 = umzug.pruefe_archiv(boese_daten)
    print(f"  Abgelehnt: {bericht2['abgelehnt']}")
    pruefe("der Ausbruchsversuch wird abgelehnt",
           len(bericht2["abgelehnt"]) == 2,
           f"erkannt: {bericht2['abgelehnt']}")

    # Die Pfadpruefung einzeln befragen. Ueber ein gebautes Archiv
    # allein ist das nicht zuverlaessig zu treffen: welche Formen
    # zipfile ueberhaupt durchlaesst, haengt von der Version ab.
    for boeser_name in (
        "../ausbruch.txt",
        "../../etc/passwd",
        "db/../../ausbruch.txt",
        "/etc/passwd",
        "/tmp/absolut.txt",
        "C:/windows/system32/x.dll",
    ):
        pruefe(f"abgelehnt: {boeser_name}",
               not umzug._ist_sicher(boeser_name),
               "dieser Pfad fuehrt aus dem Datenordner heraus")

    for guter_name in ("db/tickets.db", "jsondb/a.json", "rr.db",
                       "phantom/data/phantom.db"):
        pruefe(f"erlaubt: {guter_name}", umzug._ist_sicher(guter_name))

    ziel = "/tmp/ausgebrochen.txt"
    if os.path.exists(ziel):
        os.remove(ziel)
    umzug.spiele_archiv_ein(boese_daten, sicherung=False)
    pruefe("beim Einspielen entsteht keine Datei ausserhalb",
           not os.path.exists(ziel))

    test_sicherung_vor_dem_ueberschreiben()
    test_panel_und_routen()

    os.chdir(START_ORDNER)

    linie("ERGEBNIS")
    if fehler:
        print(f"  {len(fehler)} Probleme:")
        for f in fehler:
            print(f"    - {f}")
        return 1
    print("  Alles gruen -- der Umzug ist vollstaendig.")
    print(f"\n  Arbeitsordner: {ARBEIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
