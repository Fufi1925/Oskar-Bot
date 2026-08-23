#!/usr/bin/env python3
"""
Der Honeypot: Köder-Kanal, Softban, Live-Zähler.

Was hier geprueft wird
----------------------
1. Der Speicher: Voreinstellungen, Grenzen, Rollen-Whitelist, und dass
   der Zaehler in SQL hochgezaehlt wird (nicht "lesen, plus eins,
   schreiben" -- zwei Treffer im selben Moment wuerden sich sonst
   gegenseitig ueberschreiben).
2. Wer verschont wird: Bots, der Server-Inhaber, gewhitelistete Rollen.
   Alle anderen NICHT -- ausdrueckliche Vorgabe: "jeder man kann aber
   rollen whitelisten".
3. Stillschweigen: kann der Bot nicht bannen, darf **nichts** passieren
   -- keine Antwort im Kanal, keine Nachricht an den Inhaber.
4. Der Kanal: Position 0, ausserhalb jeder Kategorie, jeder darf
   schreiben. Steht er weiter unten, hat ein Spam-Bot vorher schon in
   einen echten Kanal geschrieben.
5. Wiedererkennung: ein frueher angelegter Kanal wird beim erneuten
   Einschalten uebernommen, statt einen zweiten anzulegen.
6. Der Zaehler-Knopf ueberlebt einen Neustart (feste custom_id,
   timeout=None).

Run:  python3 tests/test_honeypot.py
"""

import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name: str, ok: bool, hinweis: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        failures.append(name)


def linie(titel: str) -> None:
    print()
    print("=" * 66)
    print(titel)
    print("=" * 66)


def strip_ts(src: str) -> str:
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare.

    Andersherum frisst der Blockkommentar-Ausdruck ein `//` mit, das
    in einer Zeichenkette steht, und reisst Code mit weg.
    """
    ohne_zeile = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne_zeile, flags=re.S)


def strip_py(src: str) -> str:
    """Docstrings und Kommentare raus.

    Ohne das findet eine Suche ihre eigene Begruendung wieder -- das
    ist beim Umzugs-Test schon einmal passiert.
    """
    ohne_doc = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"#[^\n]*", "", ohne_doc)


# ─────────────────────────────────────────────────────────────────────
# 1. Der Speicher
# ─────────────────────────────────────────────────────────────────────

def test_speicher() -> None:
    linie("1  Der Speicher")

    import aiosqlite

    from utils import honeypot as store

    ordner = tempfile.mkdtemp(prefix="honeypot-")
    pfad = os.path.join(ordner, "honeypot.db")

    async def lauf():
        db = await aiosqlite.connect(pfad)
        await store.ensure_schema(db)

        # Ein unbekannter Server liefert trotzdem ein vollstaendiges Dict.
        leer = await store.get(db, 111)
        check("ein unbekannter Server liefert Voreinstellungen",
              leer["enabled"] is False and leer["title"] == store.DEFAULT_TITLE,
              str(leer)[:80])
        check("die Whitelist ist zu Beginn leer",
              leer["whitelist_roles"] == [])

        # Speichern und wieder lesen.
        await store.save(db, 111, enabled=True, channel_id=999,
                         title="Nicht hier", text="Sonst Softban")
        daten = await store.get(db, 111)
        check("gespeicherte Werte kommen zurueck",
              daten["enabled"] and daten["channel_id"] == 999
              and daten["title"] == "Nicht hier")

        # Der Zaehler.
        for _ in range(3):
            await store.bump_kicks(db, 111)
        daten = await store.get(db, 111)
        check("der Zaehler zaehlt hoch", daten["kicks"] == 3, str(daten["kicks"]))

        # Rollen-Whitelist: rein als Liste, raus als Liste von int.
        await store.save(db, 111, whitelist_roles=[123, 456])
        daten = await store.get(db, 111)
        check("die Rollen-Whitelist ueberlebt das Speichern",
              daten["whitelist_roles"] == [123, 456],
              str(daten["whitelist_roles"]))

        # Grenzen.
        await store.save(db, 111, title="x" * 500, text="y" * 5000)
        daten = await store.get(db, 111)
        check("der Titel wird auf die Grenze gekuerzt",
              len(daten["title"]) <= store.MAX_TITLE, str(len(daten["title"])))
        check("der Text wird auf die Grenze gekuerzt",
              len(daten["text"]) <= store.MAX_TEXT, str(len(daten["text"])))

        await store.save(db, 111, delete_days=99)
        daten = await store.get(db, 111)
        check("delete_days bleibt in Discords Rahmen (0-7)",
              0 <= daten["delete_days"] <= store.MAX_DELETE_DAYS,
              str(daten["delete_days"]))

        # Leerer Titel faellt auf die Voreinstellung zurueck, statt
        # eine Nachricht ohne Ueberschrift zu erzeugen.
        await store.save(db, 111, title="   ")
        daten = await store.get(db, 111)
        check("ein leerer Titel faellt auf die Voreinstellung zurueck",
              daten["title"] == store.DEFAULT_TITLE)

        # Ein Feld aendern laesst die anderen stehen.
        await store.save(db, 111, log_channel_id=777)
        daten = await store.get(db, 111)
        check("ein einzelnes Feld aendern loescht nichts anderes",
              daten["log_channel_id"] == 777 and daten["kicks"] == 3
              and daten["whitelist_roles"] == [123, 456])

        await db.close()

    asyncio.run(lauf())

    # Der Zaehler muss in SQL hochgezaehlt werden.
    quelle = strip_py(open(os.path.join(BOT, "utils", "honeypot.py"),
                           encoding="utf-8").read())
    rumpf = quelle[quelle.find("async def bump_kicks"):]
    rumpf = rumpf[:rumpf.find("async def all_enabled")]
    check("der Zaehler wird in SQL erhoeht, nicht im Python-Code",
          "kicks = COALESCE(kicks, 0) + 1" in rumpf,
          "lesen/plus eins/schreiben verliert gleichzeitige Treffer")


# ─────────────────────────────────────────────────────────────────────
# 2. Wer verschont wird
# ─────────────────────────────────────────────────────────────────────

class FakeRolle:
    def __init__(self, rid, position=1):
        self.id = rid
        self.position = position

    def __le__(self, other):
        return self.position <= other.position


class FakeGuild:
    def __init__(self, owner_id=1):
        self.owner_id = owner_id
        self.id = 42


class FakeMember:
    def __init__(self, mid, bot=False, rollen=None, guild=None, top=1):
        self.id = mid
        self.bot = bot
        self.roles = rollen or []
        self.guild = guild or FakeGuild()
        self.top_role = FakeRolle(0, top)


def test_wer_verschont_wird() -> None:
    linie("2  Wer verschont wird")

    from cogs.commands.honeypot import Honeypot

    cog = Honeypot.__new__(Honeypot)  # ohne __init__, wir testen nur die Regel
    guild = FakeGuild(owner_id=1)

    ohne_whitelist = {"whitelist_roles": []}

    check("ein Bot wird verschont",
          cog._ist_geschuetzt(FakeMember(5, bot=True, guild=guild),
                              ohne_whitelist))
    check("der Server-Inhaber wird verschont",
          cog._ist_geschuetzt(FakeMember(1, guild=guild), ohne_whitelist))

    # Der Kern der Vorgabe: sonst trifft es JEDEN.
    check("ein normales Mitglied wird NICHT verschont",
          not cog._ist_geschuetzt(FakeMember(9, guild=guild), ohne_whitelist))
    check("auch jemand mit Rollen wird ohne Whitelist NICHT verschont",
          not cog._ist_geschuetzt(
              FakeMember(9, rollen=[FakeRolle(100), FakeRolle(200)], guild=guild),
              ohne_whitelist),
          "Vorgabe war ausdruecklich: jeden treffen, ausser gewhitelistet")

    mit_whitelist = {"whitelist_roles": [100]}
    check("wer eine gewhitelistete Rolle hat, wird verschont",
          cog._ist_geschuetzt(
              FakeMember(9, rollen=[FakeRolle(100)], guild=guild),
              mit_whitelist))
    check("eine andere Rolle schuetzt nicht",
          not cog._ist_geschuetzt(
              FakeMember(9, rollen=[FakeRolle(200)], guild=guild),
              mit_whitelist))
    check("eine von mehreren Rollen genuegt",
          cog._ist_geschuetzt(
              FakeMember(9, rollen=[FakeRolle(200), FakeRolle(100)], guild=guild),
              mit_whitelist))


# ─────────────────────────────────────────────────────────────────────
# 3. Stillschweigen
# ─────────────────────────────────────────────────────────────────────

def test_stillschweigen() -> None:
    linie("3  Stillschweigen bei Fehlschlag")

    quelle = open(os.path.join(BOT, "cogs", "commands", "honeypot.py"),
                  encoding="utf-8").read()
    ohne = strip_py(quelle)

    rumpf = ohne[ohne.find("async def _softban"):]
    rumpf = rumpf[:rumpf.find("async def _schreibe_log")]

    # Kein Antworten, kein Melden -- egal in welcher Form.
    for verboten in ("message.channel.send", "message.reply", "ctx.send",
                     "owner.send", "message.author.send"):
        check(f"kein {verboten} im Softban",
              verboten not in rumpf,
              "bei Fehlschlag soll NICHTS passieren")

    check("der Fehlschlag wird abgefangen und still verlassen",
          "except (discord.Forbidden, discord.HTTPException)" in rumpf
          and "return" in rumpf)

    # Die Rangfolge muss VOR dem Bann geprueft werden.
    stelle_rang = rumpf.find("top_role")
    stelle_bann = rumpf.find("guild.ban")
    check("die Rangfolge wird vor dem Bann geprueft",
          stelle_rang != -1 and stelle_bann != -1 and stelle_rang < stelle_bann,
          "sonst laeuft der Bann in einen vermeidbaren Fehler")

    check("fehlendes Bannrecht wird vorher abgefangen",
          "ban_members" in rumpf)

    # Softban heisst: bannen UND entbannen.
    check("nach dem Bann wird wieder entbannt",
          "guild.unban" in rumpf,
          "sonst ist es ein Bann, kein Softban")

    # Discord-Warnung vermeiden.
    check("delete_message_seconds statt des veralteten _days",
          "delete_message_seconds" in rumpf
          and "delete_message_days" not in rumpf,
          "delete_message_days ist in discord.py 2.7.1 veraltet")


# ─────────────────────────────────────────────────────────────────────
# 4. Der Kanal
# ─────────────────────────────────────────────────────────────────────

def test_kanal() -> None:
    linie("4  Der Köder-Kanal")

    from utils import honeypot as store

    quelle = open(os.path.join(BOT, "cogs", "commands", "honeypot.py"),
                  encoding="utf-8").read()
    ohne = strip_py(quelle)

    check("der Kanal heisst wie gewuenscht",
          store.DEFAULT_CHANNEL_NAME == "dont-sent-here",
          store.DEFAULT_CHANNEL_NAME)

    rumpf = ohne[ohne.find("async def _lege_kanal_an"):]
    rumpf = rumpf[:rumpf.find("async def _nach_oben")]

    check("er wird auf Position 0 angelegt",
          "position=0" in rumpf,
          "weiter unten kommt die Falle zu spaet")
    # Gezielt den @everyone-Block ansehen, nicht die ganze Funktion.
    #
    # `send_messages=True` steht ZWEIMAL darin: einmal fuer
    # @everyone, einmal fuer den Bot selbst. Eine Suche ueber die
    # ganze Funktion blieb deshalb gruen, als @everyone das
    # Schreibrecht entzogen wurde -- der Treffer beim Bot genuegte.
    # Im Mutationstest nachgestellt.
    jeder = rumpf[rumpf.find("guild.default_role"):]
    jeder = jeder[:jeder.find("me: discord.PermissionOverwrite")]

    check("jeder darf ihn sehen",
          "view_channel=True" in jeder)
    check("jeder darf hineinschreiben",
          "send_messages=True" in jeder,
          "ohne Schreibrecht fuer @everyone ist es kein Koeder")
    check("@everyone bekommt das Schreibrecht nicht entzogen",
          "send_messages=False" not in jeder,
          "dann tappt kein Spam-Bot hinein")

    # Das Verschieben muss auch die Kategorie aufloesen -- ein Kanal in
    # einer Kategorie kann nie ueber den Kategorien stehen.
    oben = ohne[ohne.find("async def _nach_oben"):]
    oben = oben[:oben.find("def _baue_embed")]
    check("beim Hochschieben wird die Kategorie entfernt",
          "category=None" in oben,
          "in einer Kategorie kommt er nie ganz nach oben")

    # Wiedererkennung.
    finde = ohne[ohne.find("def _finde_alten_kanal"):]
    finde = finde[:finde.find("async def _stelle_kanal_sicher")]
    check("ein alter Kanal wird am Namen wiedererkannt",
          "DEFAULT_CHANNEL_NAME" in finde,
          "sonst entstehen bei jedem Umschalten neue Kanaele")

    sicher = ohne[ohne.find("async def _stelle_kanal_sicher"):]
    sicher = sicher[:sicher.find("async def _lege_kanal_an")]
    stelle_alt = sicher.find("_finde_alten_kanal")
    stelle_neu = sicher.find("_lege_kanal_an")
    check("erst suchen, dann neu anlegen",
          stelle_alt != -1 and stelle_neu != -1 and stelle_alt < stelle_neu,
          "andersherum entstuende trotzdem jedes Mal ein neuer Kanal")

    # Ausschalten darf den Kanal nicht loeschen.
    routen = strip_py(open(os.path.join(BOT, "api", "routes", "honeypot.py"),
                           encoding="utf-8").read())
    check("beim Ausschalten wird kein Kanal geloescht",
          "delete()" not in routen and "channel.delete" not in routen,
          "der Kanal kann Verlauf enthalten")


# ─────────────────────────────────────────────────────────────────────
# 5. Der Zähler-Knopf
# ─────────────────────────────────────────────────────────────────────

def test_knopf() -> None:
    linie("5  Der Zähler-Knopf")

    quelle = open(os.path.join(BOT, "cogs", "commands", "honeypot.py"),
                  encoding="utf-8").read()
    ohne = strip_py(quelle)

    knopf = ohne[ohne.find("class KicksButton"):]
    knopf = knopf[:knopf.find("class Honeypot")]

    check("der Knopf laeuft nicht ab (timeout=None)",
          "timeout=None" in knopf,
          "sonst ist er nach 15 Minuten tot")
    check("er hat eine feste custom_id",
          "custom_id=" in knopf,
          "ohne sie ueberlebt er keinen Neustart")
    check("die Zahl steht auf dem Knopf",
          "kicks" in knopf and "label=" in knopf)
    check("er ist nicht anklickbar",
          "disabled=True" in knopf,
          "es ist eine Anzeige, kein Bedienelement")

    # Nach einem Treffer muss der Knopf nachgefuehrt werden.
    softban = ohne[ohne.find("async def _softban"):]
    softban = softban[:softban.find("async def _schreibe_log")]
    check("nach einem Treffer wird der Zaehler nachgefuehrt",
          "_aktualisiere_zaehler" in softban)
    stelle_bump = softban.find("bump_kicks")
    stelle_akt = softban.find("_aktualisiere_zaehler")
    check("erst zaehlen, dann anzeigen",
          stelle_bump != -1 and stelle_akt != -1 and stelle_bump < stelle_akt,
          "sonst zeigt der Knopf den alten Stand")

    # Die Nachricht wird geaendert, nicht neu gesendet.
    aktual = ohne[ohne.find("async def _aktualisiere_zaehler"):]
    aktual = aktual[:aktual.find("async def aktiviere")]
    check("die bestehende Nachricht wird geaendert",
          ".edit(" in aktual,
          "ein erneutes Senden haeuft Warnungen im Kanal an")
    check("fetch_message statt get_message",
          "fetch_message" in aktual and "get_message" not in aktual,
          "channel.get_message gibt es in discord.py 2.7 nicht")


# ─────────────────────────────────────────────────────────────────────
# 6. Routen, Dashboard, Registrierung
# ─────────────────────────────────────────────────────────────────────

def test_anbindung() -> None:
    linie("6  Anbindung")

    # Cog registriert?
    init = open(os.path.join(BOT, "cogs", "__init__.py"), encoding="utf-8").read()
    check("der Cog wird importiert", "from .commands.honeypot import Honeypot" in init)
    check("und hinzugefuegt", "await bot.add_cog(Honeypot(bot))" in init)

    # Router eingebunden?
    server = open(os.path.join(BOT, "api", "server.py"), encoding="utf-8").read()
    check("der Router ist importiert",
          re.search(r"from api\.routes import[^\n]*honeypot", server) is not None)
    check("und eingebunden", 'prefix="/honeypot"' in server)

    # Routen vorhanden?
    routen = open(os.path.join(BOT, "api", "routes", "honeypot.py"),
                  encoding="utf-8").read()
    for pfad in ('@router.get("/{guild_id}"',
                 '@router.patch("/{guild_id}"',
                 '@router.post("/{guild_id}/toggle"',
                 '@router.post("/{guild_id}/resend"'):
        check(f"Route {pfad.split('(')[1][:24]} ist gebaut", pfad in routen)

    # IDs als Zeichenkette -- Discord-IDs sind groesser als das, was
    # JavaScript als Zahl genau darstellen kann.
    antwort = routen[routen.find("def _antwort"):]
    antwort = antwort[:antwort.find('@router.get("/{guild_id}"')]
    check("IDs gehen als Zeichenkette raus",
          antwort.count("str(") >= 4,
          "eine rohe Zahl kommt im Browser verschoben an")

    # Proxy-Zweig, sonst 404.
    proxy = strip_ts(open(
        os.path.join(DASH, "app", "api", "bot", "[...path]", "route.ts"),
        encoding="utf-8").read())
    check("der Dashboard-Proxy kennt den Bereich",
          'scope === "honeypot"' in proxy,
          "ohne ihn kommt 404 Unknown API scope")
    zweig = proxy[proxy.find('scope === "honeypot"'):]
    zweig = zweig[:zweig.find('scope === "supportqueue"')]
    check("er prueft den Serverzugriff",
          "verifyGuildAccess" in zweig)

    # Seite und Navigation.
    seite = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                         "honeypot", "page.tsx")
    check("die Dashboard-Seite gibt es", os.path.isfile(seite))

    layout = open(os.path.join(DASH, "app", "dashboard", "layout.tsx"),
                  encoding="utf-8").read()
    check("die Seite steht in der Navigation", "/honeypot`" in layout,
          "sonst ist sie nur ueber die Adresszeile erreichbar")

    # api.ts
    api_ts = open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read()
    for name in ("honeypot:", "honeypotSave:", "honeypotToggle:", "honeypotResend:"):
        check(f"api.ts kennt {name.rstrip(':')}", name in api_ts)

    # Panel
    panel = os.path.join(DASH, "components", "dashboard", "honeypot-panel.tsx")
    check("das Panel gibt es", os.path.isfile(panel))
    if os.path.isfile(panel):
        p = open(panel, encoding="utf-8").read()
        check("das Panel bietet das Ein- und Ausschalten",
              "honeypotToggle" in p)
        check("das Panel zeigt den Zaehler", "kicks" in p)
        # Deutsche Zahlen.
        check("Zahlen werden deutsch formatiert",
              'toLocaleString("de-DE")' in p,
              "toFixed liefert immer einen Punkt")

    # Uebertragung auf andere Server.
    scan = open(os.path.join(BOT, "utils", "template_scan.py"),
                encoding="utf-8").read()
    check("die Vorlagen-Uebertragung kennt den Honeypot",
          '"honeypot"' in scan)


def main() -> int:
    test_speicher()
    test_wer_verschont_wird()
    test_stillschweigen()
    test_kanal()
    test_knopf()
    test_anbindung()

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
