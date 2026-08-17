#!/usr/bin/env python3
"""
Vertraute Bots und die Einzelschalter des Anti-Nuke.

Zwei Dinge, beide bestellt:

  1. **Ein Admin-Reiter „Vertraute Bots".** Dort lassen sich
     Discord-IDs eintragen, die der Anti-Nuke nie angreift -- mit
     Profilbild und Name. Hauptbot, Template-Bot und Statusbot stehen
     fest drin und lassen sich nicht entfernen.

     Warum sie fest sind: der Template-Bot baut nach einem Angriff
     Server wieder auf -- dutzende Kanaele und Rollen in Sekunden,
     die exakte Form eines Nukes. Wer ihn austraegt, laesst ihn
     mitten in der Rettung bannen.

  2. **Die vierzehn Wachen einzeln schaltbar.** Vorher war das eine
     reine Anzeige: wer wollte, dass Kanal-Loeschungen ignoriert
     werden, musste den ganzen Anti-Nuke abschalten -- und stand dann
     ohne jeden Schutz da.

Die Regel, die den Aufbau erklaert
----------------------------------
**Fehlt ein Eintrag, gilt AN.** Das ist der Zustand, den jeder Server
bisher hatte, als es nur den Gesamtschalter gab. Ein Update darf
keinem Server stillschweigend den Schutz nehmen -- so ein Fehler
faellt erst auf, wenn er ausgenutzt wurde.

Run:  python3 tests/test_trusted_bots.py
"""

import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []

MEE6 = 159985870458322944
DYNO = 155149108183695360


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    pfad = os.path.join(*teile)
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus -- sonst trifft die Suche die Erklaerung.

    Reihenfolge: ERST die Zeilenkommentare, DANN die Bloecke.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def in_ordner():
    """Ein Wegwerf-Verzeichnis, damit die echten Daten unberuehrt bleiben."""
    ordner = tempfile.mkdtemp()
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)
    return ordner


# ══════════════════════════════════════════════════════════════════════
#  1. Der Speicher
# ══════════════════════════════════════════════════════════════════════


def test_speicher():
    print("\nDie Liste haelt sich an ihre Regeln")

    alt = os.getcwd()
    in_ordner()
    try:
        from utils import trusted_bots as tb

        os.environ.pop("TRUSTED_BOTS", None)

        check("drei sind fest eingebaut", len(tb.ALWAYS) == 3, str(len(tb.ALWAYS)))
        check("alle drei sind vertraut",
              all(tb.is_trusted(k) for k in tb.ALWAYS))
        check("ein Fremder nicht", not tb.is_trusted(MEE6))

        # Die drei duerfen NICHT verschwinden.
        for kennung in tb.ALWAYS:
            e = tb.remove(kennung)
            check(f"{kennung} laesst sich nicht entfernen",
                  not e["ok"] and e["error"] == "builtin", str(e))
        check("und sie sind danach noch da",
              all(tb.is_trusted(k) for k in tb.ALWAYS))

        # Hinzufuegen.
        check("ein Bot laesst sich eintragen", tb.add(MEE6, note="MEE6")["ok"])
        check("und ist dann vertraut", tb.is_trusted(MEE6))
        check("zweimal geht nicht", tb.add(MEE6)["error"] == "exists")

        for schrott in ("abc", "", "12.5", "'; DROP TABLE trusted_bots; --"):
            check(f"{schrott[:22]!r} wird abgewiesen",
                  tb.add(schrott)["error"] == "invalid_id")

        # Entfernen.
        check("entfernen geht", tb.remove(MEE6)["ok"])
        check("danach nicht mehr vertraut", not tb.is_trusted(MEE6))
        check("zweimal entfernen meldet unknown",
              tb.remove(MEE6)["error"] == "unknown")

        # Die Variable gilt weiter -- und laesst sich hier nicht
        # loeschen. Ein stilles „hat geklappt" waere falsch: der
        # Eintrag waere beim naechsten Laden wieder da.
        os.environ["TRUSTED_BOTS"] = f"{DYNO}, abc, ,{MEE6}"
        check("die Variable wird gelesen",
              tb.from_env() == {DYNO, MEE6}, str(tb.from_env()))
        # Und sie muss in der GESAMTLISTE landen. `from_env()` allein
        # zu pruefen reichte nicht: `all_ids()` konnte sie weglassen,
        # ohne dass etwas anschlug -- im Mutationstest genau so
        # durchgerutscht.
        check("und landet in der Gesamtliste",
              DYNO in tb.all_ids() and MEE6 in tb.all_ids(),
              "sonst steht sie da und wirkt trotzdem nicht")
        check("der Waechter sieht sie auch",
              tb.is_trusted(DYNO), "")
        e = tb.remove(DYNO)
        check("aus der Variablen laesst sich hier nichts entfernen",
              not e["ok"] and e["error"] == "from_env", str(e))
        os.environ.pop("TRUSTED_BOTS", None)
    finally:
        os.chdir(alt)


def test_liste_fuers_dashboard():
    print("\nDie Liste fuer die Anzeige")

    alt = os.getcwd()
    in_ordner()
    try:
        from utils import trusted_bots as tb

        os.environ.pop("TRUSTED_BOTS", None)
        tb.add(MEE6, note="MEE6")
        liste = tb.list_all(None)

        check("enthaelt die eingebauten und den eigenen",
              len(liste) == len(tb.ALWAYS) + 1, str(len(liste)))

        # Discord-IDs muessen Zeichenketten sein: sie sind groesser
        # als Number.MAX_SAFE_INTEGER, und JavaScript rundet sonst
        # stillschweigend auf eine ANDERE ID.
        check("die IDs sind Zeichenketten",
              all(isinstance(e["id"], str) for e in liste))

        check("die eingebauten stehen vorn",
              [e["source"] for e in liste[:3]] == ["builtin"] * 3,
              str([e["source"] for e in liste]))

        manuell = [e for e in liste if e["source"] == "manual"]
        check("der eigene Eintrag ist als manuell markiert", len(manuell) == 1)
        check("mit seiner Notiz", manuell and manuell[0]["note"] == "MEE6")

        # Ohne Bot-Instanz darf kein Name erfunden werden.
        check("kein erfundener Name ohne Bot",
              all(e["name"] == "" for e in liste),
              "eine leere Angabe ist ehrlicher als eine geratene")
        check("und das wird gekennzeichnet",
              all(e["known"] is False for e in liste))
    finally:
        os.chdir(alt)


def test_waechter_nutzt_die_liste():
    print("\nDer Anti-Nuke fragt dieselbe Liste")

    alt = os.getcwd()
    in_ordner()
    try:
        from utils import nuke_guard, trusted_bots as tb

        os.environ.pop("TRUSTED_BOTS", None)
        check("die eingebauten sind geschuetzt",
              all(nuke_guard.is_trusted_bot(k) for k in tb.ALWAYS))
        check("ein Fremder nicht", not nuke_guard.is_trusted_bot(MEE6))

        # Kein Zwischenspeicher: ein neuer Eintrag muss sofort wirken.
        # Sonst waere der Bot erst nach einem Neustart geschuetzt --
        # und genau darum ging es bei der Dashboard-Liste.
        tb.add(MEE6)
        check("ein neu eingetragener Bot wirkt SOFORT",
              nuke_guard.is_trusted_bot(MEE6),
              "mit Zwischenspeicher erst nach einem Neustart")
        tb.remove(MEE6)
        check("und ein entfernter ebenso",
              not nuke_guard.is_trusted_bot(MEE6))
    finally:
        os.chdir(alt)


# ══════════════════════════════════════════════════════════════════════
#  2. Die Einzelschalter
# ══════════════════════════════════════════════════════════════════════


def test_einzelschalter():
    print("\nJede Wache einzeln schaltbar")

    alt = os.getcwd()
    in_ordner()
    try:
        from utils import nuke_guard

        async def lauf():
            import aiosqlite

            # DER wichtigste Fall: ohne Eintrag gilt AN. Andernfalls
            # stuenden nach dem Update alle Server ohne Schutz da.
            check("ohne Eintrag gilt AN",
                  await nuke_guard.action_enabled(123, "chdl"),
                  "sonst nimmt das Update jedem Server den Schutz")

            async with aiosqlite.connect("db/anti.db") as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS antinuke_modules ("
                    "guild_id INTEGER, action TEXT,"
                    " enabled BOOLEAN NOT NULL DEFAULT 1,"
                    " PRIMARY KEY (guild_id, action))"
                )
                await db.execute(
                    "INSERT INTO antinuke_modules (guild_id, action, enabled)"
                    " VALUES (?, ?, ?)", (123, "chdl", False),
                )
                await db.commit()

            check("abgeschaltet wirkt",
                  not await nuke_guard.action_enabled(123, "chdl"))
            check("ein anderer Bereich bleibt an",
                  await nuke_guard.action_enabled(123, "rldl"))
            check("ein anderer Server bleibt an",
                  await nuke_guard.action_enabled(456, "chdl"),
                  "die Einstellung gilt pro Server")

        asyncio.run(lauf())
    finally:
        os.chdir(alt)


def test_module_fragen_den_schalter():
    print("\nAlle Module fragen ihren Schalter")

    ordner = os.path.join(BOT, "cogs", "antinuke")
    dateien = sorted(
        n for n in os.listdir(ordner) if n.endswith(".py") and n != "__init__.py"
    )
    check("es gibt die Module", len(dateien) >= 15, str(len(dateien)))

    ohne = [n for n in dateien
            if "nuke_guard.action_enabled" not in read(ordner, n)]
    check("jedes Modul fragt action_enabled", not ohne, ", ".join(ohne))

    # Und zwar mit einem Schluessel, den es wirklich gibt. Ein Tippfehler
    # hier hiesse: die Wache liest einen Schalter, den niemand umlegen
    # kann -- sie waere dauerhaft an und der Knopf ohne Wirkung.
    route = read(BOT, "api", "routes", "antinuke.py")
    block = re.search(r"ACTIONS: dict\[str, dict\] = \{(.*?)\n\}", route, re.S)
    check("die Aktionsliste ist lesbar", block is not None)
    if block:
        gueltig = set(re.findall(r'^    "(\w+)":', block.group(1), re.M))
        falsch = []
        for name in dateien:
            for schluessel in re.findall(
                r'action_enabled\([^,]+,\s*"(\w+)"\)', read(ordner, name)
            ):
                if schluessel not in gueltig:
                    falsch.append(f"{name}:{schluessel}")
        check("jeder Schluessel existiert wirklich", not falsch,
              ", ".join(falsch))


# ══════════════════════════════════════════════════════════════════════
#  3. Die Oberflaeche
# ══════════════════════════════════════════════════════════════════════


def test_admin_reiter():
    print("\nDer Admin-Reiter")

    admin = strip_ts(read(DASH, "components", "dashboard", "admin-content.tsx"))

    check("der Reiter steht in der Liste",
          re.search(r'\{ id: "trustedbots", label: "[^"]+", icon: \w+ \}', admin)
          is not None)
    check("er ist in einer Gruppe",
          re.search(r'ids:\s*\[[^\]]*"trustedbots"', admin) is not None,
          "ohne Gruppe verschwindet er aus der Leiste")
    check("er ist im TabId-Typ", '| "trustedbots"' in admin)
    check("er rendert ueber die volle Breite",
          re.search(r'FULL_WIDTH_TABS[^;]*"trustedbots"', admin, re.S) is not None)
    check("und wird gerendert",
          'activeTab === "trustedbots" && <TrustedBotsPanel />' in admin)
    check("das Panel ist importiert",
          "@/components/dashboard/trusted-bots-panel" in admin)

    block = re.search(r"const TAB_PERMISSION[^=]*=\s*\{(.*?)\n  \};", admin, re.S)
    check("es gibt ein Recht dafuer", block is not None)
    if block:
        zuordnung = dict(re.findall(r'^\s*(\w+):\s*"([^"]+)"', block.group(1), re.M))
        check("der Reiter verlangt ein Recht",
              zuordnung.get("trustedbots") == "dashboard.access",
              f"steht auf {zuordnung.get('trustedbots')!r}")


def test_panel():
    print("\nDas Panel selbst")

    src = read(DASH, "components", "dashboard", "trusted-bots-panel.tsx")
    code = strip_ts(src)

    check("es gibt die Komponente",
          "export function TrustedBotsPanel" in code)
    check("Bots lassen sich eintragen", "api.addTrustedBot(" in code)
    check("und entfernen", "api.removeTrustedBot(" in code)
    # Wieder die Wirkung, nicht das Wort: `false && !confirm(...)`
    # laesst die Zeile stehen und fragt nie.
    check("das Entfernen fragt nach -- und bricht wirklich ab",
          re.search(r"if\s*\(\s*\n\s*!confirm\(", code) is not None,
          "`false && !confirm(` fragt nie")

    # Profilbild und Name -- ausdruecklich bestellt.
    #
    # Nicht "kommt eintrag.avatar vor": `{false ? (` laesst den Namen
    # stehen und zeigt trotzdem nie ein Bild. Geprueft wird die
    # Bedingung selbst.
    check("das Profilbild wird gezeigt",
          re.search(r"\{eintrag\.avatar \? \(", code) is not None
          and "<img" in code,
          "`{false ? (` haelt den Namen und zeigt nichts")
    check("mit einem Platzhalter, wenn es keines gibt",
          "<Bot className" in code,
          "ein leerer Kreis ist ehrlicher als ein erfundenes Bild")
    check("der Name steht dabei", "eintrag.name" in code)

    # Die festen duerfen kein Entfernen-Kreuz haben.
    check("feste Eintraege tragen ein Schloss",
          "<Lock" in code and 'eintrag.source !== "manual"' in code,
          "sonst klickt jemand den Rettungsbot weg")

    # Eine ID vorab pruefen, statt den Server antworten zu lassen.
    check("die ID wird vorab geprueft",
          re.search(r"\\d\{17,20\}", code) is not None,
          "wer einen Namen eintippt, soll es sofort erfahren")


def test_server_reiter():
    print("\nDer Anti-Nuke-Reiter beim Server")

    src = read(DASH, "components", "dashboard", "antinuke-panel.tsx")
    code = strip_ts(src)

    # Die Einzelschalter.
    check("jede Wache hat einen Schalter",
          "api.setAntiNukeModule(guildId, action.key" in code,
          "vorher war das eine reine Anzeige")
    check("der Zustand kommt vom Server",
          "action.enabled !== false" in code,
          "ohne Angabe gilt an")
    check("er ist gesperrt, solange der Hauptschalter aus ist",
          "disabled={p.busy || !nutzbar}" in code,
          "ein bedienbarer Schalter ohne Wirkung ist eine Luege")
    check("und das Abschalten fragt nach",
          "wirklich abschalten" in src)

    # Die vertrauten Bots mit Bild.
    check("die vertrauten Bots stehen im Reiter", "trustedBots" in code)
    check("mit Profilbild",
          re.search(r"\{b\.avatar \? \(", code) is not None,
          "`{false ? (` laesst den Namen stehen und zeigt nichts")
    check("und Namen", "b.name || b.id" in code)


def test_api():
    print("\nDie Schnittstellen")

    route = read(BOT, "api", "routes", "antinuke.py")

    check("es gibt die Liste", "/trusted/list" in route)
    check("das Eintragen", '@router.post("/trusted"' in route)
    check("das Entfernen", '@router.delete("/trusted/{bot_id}"' in route)
    check("und den Einzelschalter", '"/{guild_id}/modules"' in route)

    # Ein unbekannter Bereich muss abgewiesen werden -- sonst legt
    # jemand einen Schalter an, den kein Modul liest.
    check("ein unbekannter Bereich wird abgewiesen",
          "if action not in ACTIONS:" in route)

    proxy = strip_ts(read(DASH, "app", "api", "bot", "[...path]", "route.ts"))
    treffer = re.search(r'if \(rest\[0\] === "trusted"\)', proxy)
    check("der Proxy kennt den Sonderweg", treffer is not None,
          "sonst liest er „trusted“ als Server-ID")

    if treffer:
        zweig = re.search(r'if \(scope === "antinuke"\) \{(.*?)\n  \}', proxy, re.S)
        if zweig:
            rumpf = zweig.group(1)
            # Die Ausnahme MUSS vor der Guild-Pruefung stehen, sonst
            # wird sie nie erreicht.
            check("und zwar VOR der Server-Pruefung",
                  rumpf.index('rest[0] === "trusted"')
                  < rumpf.index("verifyGuildAccess"),
                  "danach waere sie unerreichbar")
            check("Lesen und Schreiben sind verschieden streng",
                  '"dashboard.access"' in rumpf and '"maintenance.toggle"' in rumpf,
                  "sonst darf jede Team-Rolle die Liste aendern")


def test_volume():
    print("\nDie Datei ueberlebt einen Deploy")

    from utils import trusted_bots as tb

    check("die Datenbank liegt unter db/",
          tb.DB_PATH.replace("\\", "/").startswith("db/"), tb.DB_PATH)

    doku = read(ROOT, "RAILWAY_DEPLOYMENT.md")
    check("die Deploy-Anleitung nennt sie",
          "trusted_bots.db" in doku,
          "sonst ist die Liste nach jedem Deploy leer")


def main() -> int:
    test_speicher()
    test_liste_fuers_dashboard()
    test_waechter_nutzt_die_liste()
    test_einzelschalter()
    test_module_fragen_den_schalter()
    test_admin_reiter()
    test_panel()
    test_server_reiter()
    test_api()
    test_volume()

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
