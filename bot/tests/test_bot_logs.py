#!/usr/bin/env python3
"""
Bot-Logs: alles, was der Bot protokolliert, an einer Stelle.

Worum es geht
-------------
Die Log-Kanäle der einzelnen Module lagen über sechs Seiten verstreut.
Wer wissen wollte, wohin der Bot überall schreibt, musste sie einzeln
durchklicken. Der neue Reiter sammelt sie ein -- **ohne sie zu
kopieren**: jedes Modul bleibt die Quelle der Wahrheit für seinen
eigenen Kanal, sonst laufen zwei Stände auseinander.

Was hier geprueft wird
----------------------
1. Die Registrierung stimmt mit dem echten Datenbankschema ueberein.
   Das ist der wichtigste Punkt: `_lies_kanal` faengt jeden Fehler ab
   und meldet dann "kein Kanal". Eine falsche Tabelle saehe also
   genauso aus wie ein unbenutztes Modul -- der Reiter waere
   stillschweigend leer.
2. Werte werden wirklich gelesen, nicht nur die Spalten gefunden.
3. Der TEXT-Schluessel bei Jail. SQLite rechnet Text und Zahl nicht
   ineinander um: '123' findet man nicht mit 123.
4. Bewerbungen sind ausdruecklich ausgenommen.
5. Die Weiterleitungen von den Modul-Seiten tragen `?highlight=` und
   einen Schluessel, den es in QUELLEN wirklich gibt.
6. Kein Modul hat sein Log-Feld doppelt -- einmal hier, einmal dort.

Run:  python3 tests/test_bot_logs.py
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
START = os.getcwd()


def check(name: str, ok: bool, hinweis: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        failures.append(name)


def linie(t: str) -> None:
    print()
    print("=" * 66)
    print(t)
    print("=" * 66)


def strip_ts(src: str) -> str:
    """Kommentare raus. ERST Zeilen-, DANN Blockkommentare."""
    ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)


# ─────────────────────────────────────────────────────────────────────
# 1. Die Registrierung
# ─────────────────────────────────────────────────────────────────────

def test_registrierung() -> None:
    linie("1  Die Registrierung")

    from utils import bot_logs

    check("es gibt Quellen", len(bot_logs.QUELLEN) >= 5,
          str(len(bot_logs.QUELLEN)))

    pflicht = {"key", "label", "beschreibung", "db", "tabelle", "spalte",
               "seite", "abschnitt", "gruppe"}
    for q in bot_logs.QUELLEN:
        fehlend = pflicht - set(q)
        check(f"{q.get('key', '?')}: alle Angaben da", not fehlend, str(fehlend))

    schluessel = [q["key"] for q in bot_logs.QUELLEN]
    check("keine doppelten Schluessel",
          len(schluessel) == len(set(schluessel)), str(schluessel))

    # Jede Seite muss es auch geben -- sonst geht "Modul öffnen" ins Leere.
    for q in bot_logs.QUELLEN:
        pfad = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                            q["seite"], "page.tsx")
        check(f"{q['key']}: die Seite /{q['seite']} existiert",
              os.path.isfile(pfad), pfad)

    check("Bewerbungen sind ausdruecklich ausgenommen",
          any("Bewerbung" in label for label, _ in bot_logs.AUSGENOMMEN),
          str(bot_logs.AUSGENOMMEN))
    check("Bewerbungen sind KEINE Quelle",
          not any("applic" in q["key"] or "bewerb" in q["key"]
                  for q in bot_logs.QUELLEN))


# ─────────────────────────────────────────────────────────────────────
# 2. Schema und echte Werte
# ─────────────────────────────────────────────────────────────────────

def test_liest_echte_werte() -> None:
    linie("2  Werden echte Werte gelesen?")

    import aiosqlite

    from utils import bot_logs

    ordner = tempfile.mkdtemp(prefix="botlogs-")
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)

    GILDE = 1530378233579704370
    KANAL = 1400000000000000123

    async def lauf():
        # Jede Quelle nach ihrer eigenen Beschreibung anlegen. Stimmt
        # die Beschreibung nicht mit dem echten Schema, faellt das in
        # test_schema_stimmt auf; hier geht es darum, ob gelesen wird.
        for q in bot_logs.QUELLEN:
            als_text = q.get("id_als_text")
            spalten = [
                "guild_id " + ("TEXT PRIMARY KEY" if als_text
                               else "INTEGER PRIMARY KEY"),
                f"{q['spalte']} INTEGER",
            ]
            if q.get("schalter"):
                spalten.append(f"{q['schalter']} INTEGER DEFAULT 1")

            async with aiosqlite.connect(q["db"]) as db:
                await db.execute(
                    f"CREATE TABLE IF NOT EXISTS [{q['tabelle']}] "
                    f"({', '.join(spalten)})"
                )
                felder = ["guild_id", q["spalte"]]
                werte = [str(GILDE) if als_text else GILDE, KANAL]
                if q.get("schalter"):
                    felder.append(q["schalter"])
                    werte.append(1)
                marken = ", ".join("?" for _ in felder)
                await db.execute(
                    f"INSERT OR REPLACE INTO [{q['tabelle']}] "
                    f"({', '.join(felder)}) VALUES ({marken})",
                    tuple(werte),
                )
                await db.commit()

        zeilen = await bot_logs.uebersicht(GILDE)
        nach_key = {z["key"]: z for z in zeilen}

        check("jede Quelle kommt zurueck",
              len(zeilen) == len(bot_logs.QUELLEN), str(len(zeilen)))

        for q in bot_logs.QUELLEN:
            z = nach_key.get(q["key"])
            check(f"{q['key']}: der Kanal wird gelesen",
                  z is not None and z["channel_id"] == str(KANAL),
                  str(z.get("channel_id") if z else None))

        # IDs muessen Zeichenketten sein -- eine Discord-ID ist
        # groesser als das, was JavaScript als Zahl genau darstellt.
        check("Kanal-IDs sind Zeichenketten",
              all(isinstance(z["channel_id"], str) for z in zeilen
                  if z["channel_id"] is not None))

        # Ausgeschaltet muss auch als aus erkannt werden.
        mit_schalter = [q for q in bot_logs.QUELLEN if q.get("schalter")]
        for q in mit_schalter:
            async with aiosqlite.connect(q["db"]) as db:
                sch = str(GILDE) if q.get("id_als_text") else GILDE
                await db.execute(
                    f"UPDATE [{q['tabelle']}] SET {q['schalter']} = 0 "
                    "WHERE guild_id = ?", (sch,))
                await db.commit()

        zeilen = await bot_logs.uebersicht(GILDE)
        nach_key = {z["key"]: z for z in zeilen}
        for q in mit_schalter:
            z = nach_key[q["key"]]
            check(f"{q['key']}: ausgeschaltet wird erkannt",
                  not z["enabled"] and not z["aktiv"], str(z))

        # Der Schluesseltyp -- und zwar so, dass er wirklich zaehlt.
        #
        # Bei einer Spalte MIT Typangabe wandelt SQLite selbst um
        # (type affinity), da faellt ein falscher Typ nicht auf. Nur
        # bei einer Spalte OHNE Typangabe findet 123 die Zeile '123'
        # nicht. Genau so wird hier gebaut, sonst prueft der Test
        # etwas, das ohnehin immer geht.
        for q in bot_logs.QUELLEN:
            if not q.get("id_als_text"):
                continue
            async with aiosqlite.connect(q["db"]) as db:
                await db.execute(f"DROP TABLE IF EXISTS [{q['tabelle']}]")
                spalten = ["guild_id", f"{q['spalte']} INTEGER"]
                if q.get("schalter"):
                    spalten.append(f"{q['schalter']} INTEGER DEFAULT 1")
                await db.execute(
                    f"CREATE TABLE [{q['tabelle']}] ({', '.join(spalten)})"
                )
                await db.execute(
                    f"INSERT INTO [{q['tabelle']}] (guild_id, {q['spalte']}) "
                    "VALUES (?, ?)",
                    (str(GILDE), KANAL),
                )
                await db.commit()

            zeilen2 = await bot_logs.uebersicht(GILDE)
            z = next(x for x in zeilen2 if x["key"] == q["key"])
            check(f"{q['key']}: TEXT-Schluessel auch ohne Typangabe gefunden",
                  z["channel_id"] == str(KANAL),
                  "eine Abfrage mit einer Zahl findet '123' hier NICHT")

        # Ein unbekannter Server darf nicht werfen.
        leer = await bot_logs.uebersicht(999999999999999999)
        check("ein unbenutzter Server liefert eine leere Liste ohne Fehler",
              len(leer) == len(bot_logs.QUELLEN)
              and all(z["channel_id"] is None for z in leer))

    asyncio.run(lauf())
    os.chdir(START)


def test_schema_stimmt() -> None:
    """Die Angaben gegen das ECHTE Schema der Module.

    Der entscheidende Test. `_lies_kanal` faengt jeden Fehler ab --
    eine falsche Tabelle oder Spalte saehe aus wie ein unbenutztes
    Modul, und der Reiter waere stillschweigend leer.
    """
    linie("3  Stimmen die Angaben mit dem echten Schema?")

    import aiosqlite

    from utils import bot_logs

    ordner = tempfile.mkdtemp(prefix="botlogsschema-")
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)

    async def lauf():
        # Die Module ihr eigenes Schema anlegen lassen.
        anleger = []
        try:
            from utils import honeypot
            anleger.append(("db/honeypot.db", honeypot.ensure_schema))
        except Exception:  # noqa: BLE001
            pass
        for modul, pfad in (("verify_store", "db/verification.db"),
                            ("anonchat_store", "db/anonchat.db"),
                            ("vanity_store", "db/vanity.db"),
                            ("automod_store", "db/automod.db")):
            try:
                m = __import__(f"utils.{modul}", fromlist=["x"])
                fn = getattr(m, "ensure_schema", None)
                if fn:
                    anleger.append((pfad, fn))
            except Exception:  # noqa: BLE001
                pass
        try:
            from utils import extras_store
            anleger.append(("db/jail.db", extras_store.jail_ensure))
        except Exception:  # noqa: BLE001
            pass

        for pfad, fn in anleger:
            async with aiosqlite.connect(pfad) as db:
                try:
                    await fn(db)
                except Exception as exc:  # noqa: BLE001
                    print(f"    (Schema {pfad}: {exc})")

        for q in bot_logs.QUELLEN:
            if not os.path.exists(q["db"]):
                check(f"{q['key']}: Datenbank angelegt", False,
                      f"{q['db']} fehlt -- stimmt der Pfad?")
                continue

            async with aiosqlite.connect(q["db"]) as db:
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cur:
                    tabellen = {r[0] for r in await cur.fetchall()}

                if q["tabelle"] not in tabellen:
                    check(f"{q['key']}: Tabelle '{q['tabelle']}'", False,
                          f"vorhanden: {sorted(tabellen)}")
                    continue

                async with db.execute(
                    f"PRAGMA table_info([{q['tabelle']}])"
                ) as cur:
                    infos = await cur.fetchall()
                spalten = {r[1]: r[2] for r in infos}

                fehlend = [s for s in (q["spalte"], "guild_id")
                           if s not in spalten]
                if q.get("schalter") and q["schalter"] not in spalten:
                    fehlend.append(q["schalter"])

                check(f"{q['key']}: {q['tabelle']}.{q['spalte']}",
                      not fehlend,
                      f"fehlt: {fehlend}, vorhanden: {sorted(spalten)}")

                # Der Schluesseltyp muss zur Angabe passen.
                typ = (spalten.get("guild_id") or "").upper()
                ist_text = "TEXT" in typ or "CHAR" in typ
                check(f"{q['key']}: Schluesseltyp richtig angegeben",
                      bool(q.get("id_als_text")) == ist_text,
                      f"Schema sagt {typ or '?'}, "
                      f"id_als_text={q.get('id_als_text')}")

    asyncio.run(lauf())
    os.chdir(START)


# ─────────────────────────────────────────────────────────────────────
# 4. Routen
# ─────────────────────────────────────────────────────────────────────

def test_routen() -> None:
    linie("4  Die Routen")

    quelle = open(os.path.join(BOT, "api", "routes", "logging_cfg.py"),
                  encoding="utf-8").read()

    check("GET /{guild_id}/bot ist gebaut",
          '@router.get("/{guild_id}/bot"' in quelle)
    check("PATCH /{guild_id}/bot/{key} ist gebaut",
          '@router.patch("/{guild_id}/bot/{key}"' in quelle)

    ohne_doc = re.sub(r'"""[\s\S]*?"""', "", quelle)
    ohne = re.sub(r"#[^\n]*", "", ohne_doc)

    rumpf = ohne[ohne.find("async def bot_log_patch"):]
    check("eine unbekannte Quelle wird abgelehnt",
          "404" in rumpf and "Unbekannte Protokollquelle" in quelle)
    check("ein fremder Kanal wird abgelehnt",
          "get_channel" in rumpf and "400" in rumpf)
    check("der Schluesseltyp wird beachtet",
          "id_als_text" in rumpf,
          "sonst findet die Abfrage bei Jail nichts")
    check("es wird in die Modul-Tabelle geschrieben",
          "quelle['tabelle']" in rumpf or 'quelle["tabelle"]' in rumpf,
          "keine eigene Tabelle -- sonst gibt es zwei Wahrheiten")


# ─────────────────────────────────────────────────────────────────────
# 5. Dashboard
# ─────────────────────────────────────────────────────────────────────

def test_dashboard() -> None:
    linie("5  Dashboard")

    seite = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                         "botlogs", "page.tsx")
    check("die Seite gibt es", os.path.isfile(seite))
    if os.path.isfile(seite):
        s = open(seite, encoding="utf-8").read()
        # useSearchParams braucht eine Suspense-Grenze, sonst faellt
        # die ganze Seite beim Bauen auf Client-Rendering zurueck.
        # Nicht nur "das Wort kommt vor": die Grenze muss das Panel
        # auch wirklich umschliessen.
        check("useSearchParams steht hinter einer Suspense-Grenze",
              re.search(r"<Suspense[^>]*>[\s\S]*?<BotLogsPanel", s) is not None,
              "sonst warnt der Build und die Seite wird komplett clientseitig")
        check("Suspense ist importiert",
              re.search(r"import[^\n]*\bSuspense\b", s) is not None)

    panel = os.path.join(DASH, "components", "dashboard", "bot-logs-panel.tsx")
    check("das Panel gibt es", os.path.isfile(panel))
    if os.path.isfile(panel):
        p = strip_ts(open(panel, encoding="utf-8").read())
        check("es laedt die Uebersicht", "api.botLogs" in p)
        check("es kann speichern", "api.botLogSave" in p)
        # Auf die Wirkung zielen, nicht auf das Symbol: ein Icon
        # allein klappt nichts auf. Entscheidend ist, dass der Inhalt
        # nur bei offenem Abschnitt gerendert wird.
        check("die Abschnitte sind wirklich aufklappbar",
              re.search(r"offen\.includes\(", p) is not None
              and re.search(r"\{istOffen && \(", p) is not None,
              "der Inhalt muss an den Zustand gebunden sein")
        check("ein Klick schaltet um",
              re.search(r"onClick=\{\(\) => umschalten\(", p) is not None)
        check("es liest ?highlight aus der Adresse",
              "highlight" in p and "useSearchParams" in p)
        # Auf die Wirkung zielen: gelb muss an die Hervorhebung
        # gebunden sein, nicht irgendwo im Stylesheet stehen.
        check("die Hervorhebung ist wirklich gelb",
              re.search(r"istHell[\s\S]{0,120}?amber", p) is not None,
              "gelb muss an den hervorgehobenen Eintrag gebunden sein")
        check("die Hervorhebung verschwindet wieder",
              "setTimeout" in p and 'setLeuchtet("")' in p,
              "ein dauerhaft gelber Rahmen sieht aus wie eine Warnung")

    api_ts = open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read()
    check("api.ts kennt botLogs", "botLogs:" in api_ts)
    check("api.ts kennt botLogSave", "botLogSave:" in api_ts)

    layout = open(os.path.join(DASH, "app", "dashboard", "layout.tsx"),
                  encoding="utf-8").read()
    check("die Seite steht in der Seitenleiste", "/botlogs`" in layout)

    tabs = open(os.path.join(DASH, "components", "guild-tabs.tsx"),
                encoding="utf-8").read()
    check("und in der Reiterleiste", '"botlogs"' in tabs)


# ─────────────────────────────────────────────────────────────────────
# 6. Die Weiterleitungen
# ─────────────────────────────────────────────────────────────────────

def test_weiterleitungen() -> None:
    linie("6  Weiterleitungen von den Modul-Seiten")

    from utils import bot_logs

    hinweis = os.path.join(DASH, "components", "dashboard", "log-umgezogen.tsx")
    check("die Hinweis-Komponente gibt es", os.path.isfile(hinweis))
    if os.path.isfile(hinweis):
        h = strip_ts(open(hinweis, encoding="utf-8").read())
        check("sie verlinkt auf botlogs", "botlogs" in h)
        check("sie nimmt ?highlight mit", "highlight=" in h,
              "ohne das sucht man auf einer Liste mit sechs Eintraegen")

    bekannt = {q["key"] for q in bot_logs.QUELLEN}
    ordner = os.path.join(DASH, "components", "dashboard")

    benutzt = []
    for name in sorted(os.listdir(ordner)):
        if not name.endswith(".tsx"):
            continue
        inhalt = open(os.path.join(ordner, name), encoding="utf-8").read()
        if "LogUmgezogen" not in inhalt:
            continue
        for treffer in re.findall(r'logKey="([^"]+)"', inhalt):
            benutzt.append((name, treffer))
            check(f"{name}: logKey '{treffer}' ist bekannt",
                  treffer in bekannt,
                  f"nicht in QUELLEN: {sorted(bekannt)}")

    check("mindestens drei Module verweisen weiter",
          len(benutzt) >= 3, str(benutzt))

    # Kein Modul darf sein Log-Feld doppelt haben: einmal als Verweis,
    # einmal als eigenes Auswahlfeld. Sonst gibt es zwei Stellen fuer
    # denselben Wert, und eine davon zeigt Veraltetes.
    for name, key in benutzt:
        inhalt = strip_ts(open(os.path.join(ordner, name), encoding="utf-8").read())
        quelle = next(q for q in bot_logs.QUELLEN if q["key"] == key)
        spalte = quelle["spalte"]
        # `set("<spalte>"` waere ein schreibendes Feld.
        doppelt = re.search(rf'set\(\s*"{re.escape(spalte)}"', inhalt)
        check(f"{name}: kein zweites Feld fuer {spalte}",
              doppelt is None,
              "der Wert waere an zwei Stellen einstellbar")


def main() -> int:
    try:
        test_registrierung()
        test_liest_echte_werte()
        test_schema_stimmt()
        test_routen()
        test_dashboard()
        test_weiterleitungen()
    finally:
        os.chdir(START)

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
