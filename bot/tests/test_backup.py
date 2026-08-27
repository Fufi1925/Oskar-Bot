#!/usr/bin/env python3
"""
Der Backup-Reiter und das Support-Fenster.

Drei Dinge werden hier festgehalten:

  1. **Die Grenzen greifen im Bot.** Gratis eine Sicherung, mit
     Premium zehn, Automatik nur mit Premium. Eine Sperre, die nur im
     Browser sitzt, ist keine.
  2. **Das Support-Fenster kommt alle sieben Tage** -- fuer jeden, der
     sich anmeldet, nicht nur fuer Premium.
  3. **Das goldene Premium-Fenster kommt wieder nur EINMAL.** Der
     Sieben-Tage-Rhythmus gehoert dem Support-Fenster; zwei Fenster im
     selben Takt waeren zwei Fenster hintereinander.

Run:  python3 tests/test_backup.py
"""

import asyncio
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

GILDE = 1530378233579704370
ARM = 424242424242424242
REICH = 1303627964734246944


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
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare."""
    ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


def entkette(src: str) -> str:
    return re.sub(r'"\s*\+\s*"', "", src)


class FakeGuild:
    def __init__(self):
        self.id = GILDE
        self.name = "Test-Server"
        self.icon = None
        self.categories = []
        self.channels = []
        self.roles = []
        self.text_channels = []
        self.me = None


# ══════════════════════════════════════════════════════════════════════
#  1. Die Grenzen -- echt ueber HTTP
# ══════════════════════════════════════════════════════════════════════


async def _routen():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.dependencies import get_bot
    from api.routes import backup as routes
    from utils import guild_backup as store
    from utils import premium_store

    premium_store.ensure()
    premium_store.grant_direct(REICH, duration_days=30, note="Test")

    async def fake_erstelle(bot, guild, **kw):
        await asyncio.sleep(0)
        return {
            "version": 1,
            "guild": {"name": "Test-Server"},
            "categories": [{"name": "Allgemein", "position": 0}],
            "channels": [{"name": "chat", "kind": "text", "position": 0}],
            "roles": [{"name": "Mitglied", "permissions": []}],
            "features": {"automod": {"settings": [{"guild_id": GILDE}]}},
        }

    routes.backup_runner.erstelle = fake_erstelle

    class FakeBot:
        def get_guild(self, gid):
            return FakeGuild() if int(gid) == GILDE else None

    app = FastAPI()
    app.include_router(routes.router, prefix="/backup")
    app.dependency_overrides[get_bot] = lambda: FakeBot()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:

        async def fertig():
            for _ in range(100):
                r = await c.get(f"/backup/{GILDE}/status")
                if not r.json().get("aktiv"):
                    return
                await asyncio.sleep(0.05)

        linie("1  Ohne Premium: genau eine Sicherung")
        r = await c.get(f"/backup/{GILDE}?actor={ARM}")
        pruefe("die Uebersicht antwortet", r.status_code == 200, r.text[:150])
        pruefe("Grenze ist 1", r.json()["grenze"] == 1)

        r = await c.post(f"/backup/{GILDE}/create", json={"actor": str(ARM)})
        pruefe("die erste geht", r.status_code == 200, r.text[:150])
        await fertig()

        eintraege = (await c.get(f"/backup/{GILDE}?actor={ARM}")).json()["backups"]
        pruefe("eine liegt vor", len(eintraege) == 1, str(len(eintraege)))
        pruefe("mit Kennung", eintraege[0]["kennung"].startswith("BK-"),
               eintraege[0]["kennung"])
        pruefe("die Einstellungen sind dabei",
               eintraege[0]["mit_einstellungen"] is True,
               "die Dashboard-Konfiguration soll mitgesichert werden")

        r = await c.post(f"/backup/{GILDE}/create", json={"actor": str(ARM)})
        pruefe("die zweite wird abgelehnt", r.status_code == 409,
               str(r.status_code))
        pruefe("die Meldung sagt, was zu tun ist",
               "Lösche" in r.text, r.text[:200])

        linie("2  Nachrichten und Automatik nur mit Premium")
        # Erst Platz schaffen -- sonst greift die Mengengrenze (409)
        # und die Premium-Pruefung wird gar nicht erreicht. Genau das
        # hat der Mutationstest aufgedeckt: die Zeile blieb gruen,
        # obwohl die Pruefung entfernt war.
        alt = (await c.get(f"/backup/{GILDE}?actor={ARM}")
               ).json()["backups"][0]["kennung"]
        await c.delete(f"/backup/{GILDE}/{alt}?actor={ARM}")

        r = await c.post(f"/backup/{GILDE}/create",
                         json={"actor": str(ARM), "mit_nachrichten": True})
        pruefe("Nachrichten ohne Premium abgelehnt", r.status_code == 403,
               f"HTTP {r.status_code} -- es ist Platz, nur Premium fehlt")
        pruefe("und die Meldung nennt Premium", "Premium" in r.text,
               r.text[:150])
        pruefe("es wurde auch nichts angelegt",
               (await c.get(f"/backup/{GILDE}?actor={ARM}")
                ).json()["backups"] == [],
               "die abgelehnte Anfrage darf nichts hinterlassen")

        # Fuer die folgenden Abschnitte wieder eine anlegen.
        await c.post(f"/backup/{GILDE}/create", json={"actor": str(ARM)})
        await fertig()
        eintraege = (await c.get(f"/backup/{GILDE}?actor={ARM}")
                     ).json()["backups"]

        r = await c.post(f"/backup/{GILDE}/auto",
                         json={"actor": str(ARM), "aktiv": True})
        pruefe("Automatik ohne Premium abgelehnt", r.status_code == 403,
               str(r.status_code))
        pruefe("und nennt Premium", "Premium" in r.text, r.text[:150])

        linie("3  Mit Premium: zehn")
        kennung = eintraege[0]["kennung"]
        await c.delete(f"/backup/{GILDE}/{kennung}?actor={ARM}")

        r = await c.get(f"/backup/{GILDE}?actor={REICH}")
        pruefe("Grenze ist 10", r.json()["grenze"] == 10)

        for _ in range(10):
            r = await c.post(f"/backup/{GILDE}/create",
                             json={"actor": str(REICH)})
            if r.status_code != 200:
                break
            await fertig()

        alle = (await c.get(f"/backup/{GILDE}?actor={REICH}")).json()["backups"]
        pruefe("zehn liegen vor", len(alle) == 10, str(len(alle)))

        r = await c.post(f"/backup/{GILDE}/create", json={"actor": str(REICH)})
        pruefe("die elfte wird abgelehnt", r.status_code == 409,
               str(r.status_code))

        kennungen = [b["kennung"] for b in alle]
        pruefe("jede Kennung ist eindeutig",
               len(kennungen) == len(set(kennungen)))

        linie("4  Die Automatik")
        r = await c.post(f"/backup/{GILDE}/auto", json={
            "actor": str(REICH), "aktiv": True, "stunden": 12,
            "alte_loeschen": True,
        })
        pruefe("Einschalten geht", r.status_code == 200, r.text[:150])
        pruefe("12 Stunden gemerkt", r.json()["auto"]["stunden"] == 12)

        # Die Untergrenze muss im BOT greifen.
        r = await c.post(f"/backup/{GILDE}/auto",
                         json={"actor": str(REICH), "stunden": 1})
        pruefe("eine Stunde wird angehoben",
               r.json()["auto"]["stunden"] == store.MIN_AUTO_STUNDEN,
               f"{r.json()['auto']['stunden']} statt {store.MIN_AUTO_STUNDEN}")

        linie("5  Wiederherstellen reicht beide Antworten durch")
        gerufen = {}

        async def fake_restore(bot, guild, inhalt, **kw):
            gerufen.update(kw)
            gerufen["kanaele"] = len(inhalt.get("channels") or [])
            return {"geloescht": {"kanaele": 0, "rollen": 0},
                    "erstellt": {"kategorien": 1, "kanaele": 1, "rollen": 1},
                    "nachrichten": 0, "einstellungen": True,
                    "fehler": [], "fehler_gesamt": 0}

        routes.backup_runner.stelle_wieder_her = fake_restore

        r = await c.post(f"/backup/{GILDE}/{kennungen[0]}/restore", json={
            "actor": str(REICH), "alles_loeschen": True,
            "mit_einstellungen": False,
        })
        pruefe("Wiederherstellen startet", r.status_code == 200, r.text[:150])
        await fertig()

        pruefe("„alles löschen“ kommt an",
               gerufen.get("alles_loeschen") is True, str(gerufen))
        pruefe("„ohne Einstellungen“ kommt an",
               gerufen.get("mit_einstellungen") is False, str(gerufen))
        pruefe("der Inhalt wurde entpackt", gerufen.get("kanaele") == 1)

        r = await c.post(f"/backup/{GILDE}/BK-GIBTSNICHT/restore",
                         json={"actor": str(REICH)})
        pruefe("unbekannte Kennung gibt 404", r.status_code == 404,
               str(r.status_code))

        linie("6  Fremde Server und fremde Kennungen")
        r = await c.get(f"/backup/999999999999999999?actor={REICH}")
        pruefe("ein fremder Server gibt 404", r.status_code == 404,
               str(r.status_code))

        # Eine gueltige Kennung an eine andere Server-ID gehaengt darf
        # nichts liefern -- sonst liest man fremde Sicherungen.
        pruefe("eine Kennung gilt nur fuer ihren Server",
               store.hole(999, kennungen[0]) is None,
               "sonst liest man mit fremder Kennung fremde Sicherungen")


def test_routen():
    arbeit = tempfile.mkdtemp(prefix="backup-test-")
    os.chdir(arbeit)
    os.makedirs("db", exist_ok=True)
    os.environ.setdefault("PREMIUM_KEY_PEPPER", "test-pepper")
    try:
        asyncio.run(_routen())
    finally:
        os.chdir(START)


# ══════════════════════════════════════════════════════════════════════
#  2. Das Support-Fenster
# ══════════════════════════════════════════════════════════════════════


def test_support_fenster():
    linie("7  Das Support-Fenster kommt alle sieben Tage")

    arbeit = tempfile.mkdtemp(prefix="support-test-")
    os.chdir(arbeit)
    os.makedirs("db", exist_ok=True)

    try:
        from utils import support_notice as sn

        pruefe("der Abstand ist sieben Tage", sn.ABSTAND_TAGE == 7,
               str(sn.ABSTAND_TAGE))

        A = "1303627964734246944"

        def zurueck(tage):
            with sqlite3.connect(sn.DB_PATH) as conn:
                conn.execute(
                    "UPDATE support_notice SET gesehen_at = ? WHERE user_id = ?",
                    (int(time.time()) - int(tage * 86400), A),
                )

        pruefe("beim ersten Mal erscheint es", sn.zustand(A)["zeigen"] is True)

        # Reine Abfrage: mehrfaches Nachfragen darf nichts verbrauchen.
        for _ in range(3):
            sn.zustand(A)
        pruefe("nachfragen verbraucht es nicht",
               sn.zustand(A)["zeigen"] is True,
               "wer die Seite neu laedt, soll es noch sehen")

        sn.weggeklickt(A)
        pruefe("nach dem Wegklicken ist Ruhe", sn.zustand(A)["zeigen"] is False)

        zurueck(6)
        pruefe("sechs Tage reichen nicht", sn.zustand(A)["zeigen"] is False)

        zurueck(7)
        pruefe("nach sieben Tagen kommt es wieder",
               sn.zustand(A)["zeigen"] is True)

        # „Ja, beitreten" beendet es endgueltig.
        B = "1033826242270609449"
        sn.weggeklickt(B, beigetreten=True)
        pruefe("nach dem Beitritt nie wieder",
               sn.zustand(B)["zeigen"] is False)
        with sqlite3.connect(sn.DB_PATH) as conn:
            conn.execute(
                "UPDATE support_notice SET gesehen_at = 0 WHERE user_id = ?",
                (B,),
            )
        pruefe("auch nach langer Zeit nicht",
               sn.zustand(B)["zeigen"] is False,
               "wer beigetreten ist, soll nicht weiter gefragt werden")

        zahlen = sn.zahlen()
        pruefe("die Zahlen stimmen",
               zahlen["konten"] == 2 and zahlen["beigetreten"] == 1,
               str(zahlen))
    finally:
        os.chdir(START)


def test_premium_fenster_nur_einmal():
    linie("8  Das goldene Fenster kommt wieder nur EINMAL")

    arbeit = tempfile.mkdtemp(prefix="pn-test-")
    os.chdir(arbeit)
    os.makedirs("db", exist_ok=True)

    try:
        from utils import premium_notice as pn

        pruefe("kein Sieben-Tage-Abstand mehr",
               not hasattr(pn, "ABSTAND_TAGE"),
               "der Rhythmus gehoert dem Support-Fenster")

        A = "1303627964734246944"
        pruefe("beim ersten Premium erscheint es",
               pn.zustand(A, True)["zeigen"] is True)
        pn.als_gesehen(A)
        pruefe("danach nie wieder", pn.zustand(A, True)["zeigen"] is False)

        # Auch nach langer Zeit nicht.
        with sqlite3.connect(pn.DB_PATH) as conn:
            conn.execute(
                "UPDATE premium_notice SET gesehen_at = 0, zuletzt_at = 0 "
                "WHERE user_id = ?", (A,)
            )
        pruefe("auch viel spaeter nicht",
               pn.zustand(A, True)["zeigen"] is False)

        # Nach Entzug und Neuvergabe aber schon.
        pn.zustand(A, False)
        z = pn.zustand(A, True)
        pruefe("nach einer Rueckkehr wieder", z["zeigen"] is True)
        pruefe("und als Rueckkehr gekennzeichnet", z["rueckkehr"] is True)
    finally:
        os.chdir(START)


# ══════════════════════════════════════════════════════════════════════
#  3. Die Oberflaeche
# ══════════════════════════════════════════════════════════════════════


def test_oberflaeche():
    linie("9  Der Reiter im Dashboard")

    seite = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                         "backup", "page.tsx")
    pruefe("die Seite gibt es", os.path.isfile(seite))

    panel_pfad = os.path.join(DASH, "components", "dashboard",
                              "backup-panel.tsx")
    pruefe("das Panel gibt es", os.path.isfile(panel_pfad))
    if not os.path.isfile(panel_pfad):
        return

    panel = entkette(strip_ts(open(panel_pfad, encoding="utf-8").read()))

    pruefe("ein Knopf zum Erstellen", "api.backupCreate(" in panel)
    pruefe("Wiederherstellen", "api.backupRestore(" in panel)
    pruefe("Loeschen", "api.backupDelete(" in panel)
    pruefe("die Automatik", "api.backupAuto(" in panel)

    # Die beiden Fragen beim Wiederherstellen -- auf die WIRKUNG
    # zielen, nicht auf das Wort.
    pruefe("die Frage „alles löschen“ gibt es",
           "Alles zuerst löschen" in panel)
    pruefe("und sie wird mitgeschickt",
           "alles_loeschen: allesLoeschen" in panel,
           "sonst ist der Schalter Zierde")
    pruefe("die Frage nach den Einstellungen gibt es",
           "Dashboard-Einstellungen auch wiederherstellen" in panel)
    pruefe("und sie wird mitgeschickt",
           "mit_einstellungen: mitEinstellungen" in panel)

    # Kein Live-Protokoll -- ausdrueckliche Vorgabe.
    pruefe("kein Live-Protokoll",
           "logs" not in panel.lower() and "protokoll" not in panel.lower(),
           "es soll nur ein Satz zum Fortschritt stehen")

    # Die Premium-Sperre haengt am Zustand, nicht an einer festen
    # Bedingung.
    pruefe("die Automatik ist ohne Premium gesperrt",
           re.search(r"\{!premium && \(", panel) is not None,
           "sonst ist die Sperre Zierde")

    # Und der Hinweis, was NICHT geht.
    pruefe("es steht da, dass Mitglieder fehlen",
           "Mitglieder und ihre Rollenzuordnung" in panel,
           "sonst erwartet jemand, dass sein Server komplett zurueckkommt")


def test_registrierung():
    linie("10  Der Reiter ist ueberall eingetragen")

    layout = strip_ts(lies("app", "dashboard", "layout.tsx"))
    tabs = strip_ts(lies("components", "guild-tabs.tsx"))

    pruefe("in der Seitenleiste", "/backup`" in layout)
    pruefe("und in der Reiterleiste", 'slug: "backup"' in tabs)

    # Golden wie Design: die Automatik ist Premium.
    eintrag = re.search(r'name: "Backup",(.*?)\n\s{12}\},', layout, re.S)
    pruefe("der Eintrag ist auffindbar", eintrag is not None)
    if eintrag:
        pruefe("er ist golden markiert",
               "highlight: true" in eintrag.group(1))

    # Die Testlisten.
    sb = open(os.path.join(BOT, "tests", "test_dashboard_save_bars.py"),
              encoding="utf-8").read()
    pruefe("in NO_DRAFT eingetragen", '"backup",' in sb,
           "sonst verlangt der Test eine Speicherleiste")

    tp = open(os.path.join(BOT, "tests", "test_templates.py"),
              encoding="utf-8").read()
    pruefe("in der Ausnahmeliste", '"backup",' in tp,
           "der Reiter hat keine Feature-Tabelle")

    docs = lies("app", "docs", "page.tsx")
    pruefe("der Doku-Zaehler stimmt", "BEREICHE_GESAMT = 45" in docs,
           "ein Bereich mehr")

    # Die Route ist im Bot eingebunden.
    server = open(os.path.join(BOT, "api", "server.py"), encoding="utf-8").read()
    pruefe("der Router ist importiert",
           re.search(r"from api\.routes import[^\n]*\bbackup\b", server)
           is not None)
    pruefe("und eingebunden", 'prefix="/backup"' in server)

    # Feste Pfade VOR den Mustern.
    from api.routes import backup as modul

    pfade = [getattr(r, "path", "") for r in modul.router.routes]
    pruefe("/status steht vor /{kennung}",
           pfade.index("/{guild_id}/status") < pfade.index("/{guild_id}/{kennung}"),
           f"Reihenfolge: {pfade}")
    pruefe("/auto steht vor /{kennung}",
           pfade.index("/{guild_id}/auto") < pfade.index("/{guild_id}/{kennung}"),
           f"Reihenfolge: {pfade}")

    # Der Proxy muss den Bereich kennen -- sonst laeuft alles ins Leere.
    proxy = strip_ts(lies("app", "api", "bot", "[...path]", "route.ts"))
    pruefe("der Proxy kennt den Bereich", 'scope === "backup"' in proxy)
    # Den BLOCK isolieren, dann darin suchen.
    #
    # `server.manage` steht zwoelfmal in der Datei. Eine Suche ueber
    # das Ganze bleibt gruen, auch wenn der Backup-Block seine
    # Rechtepruefung verliert -- nachgemessen im Mutationstest.
    anfang = proxy.find('scope === "backup"')
    ende = proxy.find('scope === "honeypot"', anfang)
    block = proxy[anfang:ende] if anfang >= 0 and ende > anfang else ""
    pruefe("der Backup-Block ist auffindbar", bool(block))
    pruefe("Schreiben verlangt server.manage",
           "server.manage" in block,
           "eine Wiederherstellung kann den Server leerraeumen")
    pruefe("und Lesen guild.view",
           "guild.view" in block)
    pruefe("wer den Server verwaltet, darf auch",
           "managesGuildOnDiscord(guildId)" in block)


def test_automatik_cog():
    linie("11  Die Automatik laeuft wirklich")

    quelle = open(os.path.join(BOT, "cogs", "commands", "backup_auto.py"),
                  encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    pruefe("es gibt einen Durchlauf", "@tasks.loop(" in ohne)
    pruefe("er wird gestartet", "self.durchlauf.start()" in ohne)
    pruefe("und beim Entladen gestoppt", "self.durchlauf.cancel()" in ohne)
    pruefe("er wartet auf den Bot", "wait_until_ready" in ohne)

    # Der Zeitpunkt muss AUCH bei einem Fehler vermerkt werden.
    pruefe("ein Fehler wird vermerkt",
           "auto_lauf_vermerkt(guild_id, fehler=" in ohne,
           "sonst laeuft die Automatik alle 15 Minuten gegen die Wand")

    # Und das Cog ist geladen.
    init = open(os.path.join(BOT, "cogs", "__init__.py"), encoding="utf-8").read()
    pruefe("das Cog ist importiert", "BackupAuto" in init)
    pruefe("und hinzugefuegt", "add_cog(BackupAuto(bot))" in init)


def test_store():
    linie("12  Der Speicher")

    quelle = open(os.path.join(BOT, "utils", "guild_backup.py"),
                  encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    pruefe("Gratis-Grenze ist 1", "MAX_GRATIS = 1" in ohne)
    pruefe("Premium-Grenze ist 10", "MAX_PREMIUM = 10" in ohne)
    pruefe("500 Nachrichten", "MAX_NACHRICHTEN = 500" in ohne)

    # Neue Spalten muessen per ALTER nachgezogen werden.
    pruefe("fehlende Spalten werden nachgeruestet",
           "ALTER TABLE backups ADD COLUMN" in ohne,
           "CREATE TABLE IF NOT EXISTS aendert an bestehenden nichts")

    # Die Kennung muss eindeutig sein.
    pruefe("die Kennung ist eindeutig",
           "CREATE UNIQUE INDEX IF NOT EXISTS backups_kennung" in ohne)

    # Und `hole` darf nicht serveruebergreifend lesen.
    fn = re.search(r"def hole\(.*?\n    return ", ohne, re.S)
    pruefe("hole() ist auffindbar", fn is not None)
    if fn:
        pruefe("hole() prueft die Server-ID mit",
               "WHERE guild_id = ? AND kennung = ?" in fn.group(0),
               "sonst liest man mit fremder Kennung fremde Sicherungen")


def test_runner_haelt_grenzen_ein():
    linie("13  Der Runner haelt Discords Grenzen ein")

    quelle = open(os.path.join(BOT, "utils", "backup_runner.py"),
                  encoding="utf-8").read()
    ohne = re.sub(r'"""(?:.|\n)*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne)

    pruefe("es gibt eine Pause", "PAUSE = " in ohne)
    pruefe("und sie wird benutzt",
           ohne.count("await asyncio.sleep(PAUSE)") >= 3,
           "ohne Pause antwortet Discord mit 429")
    pruefe("Webhooks haben eine eigene Pause",
           "PAUSE_WEBHOOK" in ohne and "sleep(PAUSE_WEBHOOK)" in ohne,
           "Webhooks haben ein eigenes Limit")

    # Erwaehnungen duerfen nicht ausgeloest werden.
    pruefe("keine Erwaehnungen beim Zurueckschreiben",
           "AllowedMentions.none()" in ohne,
           "sonst pingt eine Wiederherstellung den halben Server")

    # Der Webhook muss wieder weg.
    pruefe("der Webhook wird abgeraeumt",
           "webhook.delete(" in ohne,
           "er bliebe sonst als dauerhafter Schreibzugang zurueck")

    # Rechte kommen als NAMEN, nicht als Bitmaske.
    pruefe("Rechte werden ueber Namen gesetzt",
           "hasattr(discord.Permissions, name)" in ohne,
           "template_scan speichert Namen; int(...) waere immer 0")


if __name__ == "__main__":
    test_routen()
    test_support_fenster()
    test_premium_fenster_nur_einmal()
    test_oberflaeche()
    test_registrierung()
    test_automatik_cog()
    test_store()
    test_runner_haelt_grenzen_ein()

    os.chdir(START)
    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print(f"  - {f}")
        sys.exit(1)
    print("Backup und die Fenster verhalten sich richtig.")
