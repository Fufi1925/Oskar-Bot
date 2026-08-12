#!/usr/bin/env python3
"""
Bewerbungen: Panels, Fragen, DM-Ablauf und Entscheidung.

Der Ablauf, um den es geht:

  1. Bis zu zwei Panels pro Server, je bis zu acht Kategorien.
  2. Jede Kategorie hat drei bis zwanzig Fragen.
  3. Wer im Auswahlmenue waehlt, bekommt die Fragen per DM -- einzeln.
  4. Am Ende geht die Zusammenfassung in einen Kanal, mit Knoepfen zum
     Annehmen und Ablehnen, beide mit Begruendung.
  5. Nur eine offene Bewerbung pro Person, serveruebergreifend.
  6. Optional eine Sperre nach einer Ablehnung.

Alles gegen echtes SQLite. Discord wird nur dort durch Attrappen
ersetzt, wo es um Nachrichten geht.

Run:  python3 tests/test_applications.py
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

from utils import application_store as store  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370
USER = 1303627964734246944
STAFF = 1033826242270609449


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


def read_dash(rel: str) -> str:
    return open(os.path.join(DASH, rel), encoding="utf-8").read()


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                for i in range(first.lineno - 1, first.end_lineno):
                    lines[i] = ""
    return "\n".join(lines)


DREI = ["Warum du?", "Wie alt bist du?", "Wie viel Zeit hast du?"]


# ── 1. Panels und ihre Grenzen ───────────────────────────────────────

async def test_panels():
    print("\n1. Panels: hoechstens zwei")
    a = await store.create_panel(GUILD, "Team")
    b = await store.create_panel(GUILD, "Events")
    check("zwei Panels gehen", a["panel_id"] != b["panel_id"])

    try:
        await store.create_panel(GUILD, "Drittes")
        check("das dritte wird abgelehnt", False, "-> es wurde angelegt")
    except ValueError as exc:
        check("das dritte wird abgelehnt", "2" in str(exc))

    # Auf einem anderen Server wieder frei.
    anderer = await store.create_panel(999888777666555, "Woanders")
    check("anderer Server hat eigene Panels", anderer["panel_id"] > 0)

    await store.update_panel(GUILD, a["panel_id"], {
        "channel_id": "111222333444555666",
        "embed_title": "Bewirb dich",
        "deny_cooldown_enabled": True,
        "deny_cooldown_days": 14,
    })
    panels = await store.list_panels(GUILD)
    eins = next(p for p in panels if p["panel_id"] == a["panel_id"])
    check("Kanal gespeichert", eins["channel_id"] == "111222333444555666")
    check("Ueberschrift gespeichert", eins["embed_title"] == "Bewirb dich")
    check("Sperre gespeichert",
          eins["deny_cooldown_enabled"] and eins["deny_cooldown_days"] == 14)

    # Grenzen: 0 Tage waere keine Sperre, dafuer gibt es den Schalter.
    # Negative Werte und Unsinn duerfen auch nicht durchrutschen -- eine
    # Sperre von minus fuenf Tagen laege in der Vergangenheit und waere
    # damit wirkungslos, ohne dass es jemand merkt.
    for eingabe, mindestens in ((0, 1), (-5, 1), (99999, None)):
        await store.update_panel(GUILD, a["panel_id"],
                                 {"deny_cooldown_days": eingabe})
        panels = await store.list_panels(GUILD)
        eins = next(p for p in panels if p["panel_id"] == a["panel_id"])
        wert = eins["deny_cooldown_days"]
        check(f"{eingabe} Tage werden begrenzt", 1 <= wert <= 365,
              f"(wurde {wert})")

    return a["panel_id"]


# ── 2. Kategorien und Fragen ─────────────────────────────────────────

async def test_kategorien(panel_id: int):
    print("\n2. Kategorien: hoechstens acht, drei bis zwanzig Fragen")

    kategorie = await store.upsert_category(GUILD, panel_id, {
        "name": "Moderator", "emoji": "🛡️", "questions": DREI,
        "results_channel_id": "222333444555666777",
        "staff_roles": [str(STAFF)],
    })
    check("Kategorie angelegt", kategorie["category_id"] > 0)

    # Unter drei Fragen ist es kein Bewerbungsbogen mehr.
    try:
        await store.upsert_category(GUILD, panel_id, {
            "name": "Zu kurz", "questions": ["Nur eine?"],
        })
        check("zwei Fragen werden abgelehnt", False, "-> wurde angelegt")
    except ValueError as exc:
        check("zu wenige Fragen werden abgelehnt", "3" in str(exc))

    # Leere Fragen zaehlen nicht mit.
    try:
        await store.upsert_category(GUILD, panel_id, {
            "name": "Leer", "questions": ["Echt?", "   ", ""],
        })
        check("leere Fragen zaehlen nicht", False, "-> wurde angelegt")
    except ValueError:
        check("leere Fragen zaehlen nicht", True)

    # Ueber zwanzig wird gekuerzt, nicht abgelehnt.
    viele = await store.upsert_category(GUILD, panel_id, {
        "name": "Viele", "questions": [f"Frage {i}" for i in range(30)],
    })
    geladen = await store.get_category(viele["category_id"])
    check("mehr als zwanzig werden gekuerzt",
          len(geladen["questions"]) == store.MAX_QUESTIONS,
          f"({len(geladen['questions'])})")

    # Acht ist Schluss.
    for i in range(6):
        await store.upsert_category(GUILD, panel_id, {
            "name": f"Kategorie {i}", "questions": DREI,
        })
    try:
        await store.upsert_category(GUILD, panel_id, {
            "name": "Neunte", "questions": DREI,
        })
        check("die neunte wird abgelehnt", False, "-> wurde angelegt")
    except ValueError as exc:
        check("die neunte wird abgelehnt", "8" in str(exc))

    # Bearbeiten aendert, legt nicht neu an.
    await store.upsert_category(GUILD, panel_id, {
        "category_id": kategorie["category_id"],
        "name": "Moderator (neu)", "questions": DREI + ["Noch was?"],
    })
    geladen = await store.get_category(kategorie["category_id"])
    check("Bearbeiten aendert den Namen", geladen["name"] == "Moderator (neu)")
    check("Bearbeiten aendert die Fragen", len(geladen["questions"]) == 4)

    return kategorie["category_id"]


# ── 2b. Mehrere Rollen beim Annehmen ─────────────────────────────────

async def test_accept_rollen(_ignoriert: int):
    print("\n2b. Bis zu fuenf Rollen beim Annehmen")

    # Eigenes Panel auf einem eigenen Server: das aus Test 2 hat schon
    # seine acht Kategorien.
    eigener = 424242424242
    panel = await store.create_panel(eigener, "Rollen")
    panel_id = panel["panel_id"]

    k = await store.upsert_category(eigener, panel_id, {
        "name": "Mit Rollen", "questions": DREI,
        "accept_roles": ["111", "222", "333"],
    })
    geladen = await store.get_category(k["category_id"])
    check("drei Rollen werden gespeichert",
          geladen["accept_roles"] == ["111", "222", "333"],
          f"({geladen['accept_roles']})")

    # Mehr als fuenf werden gekappt, nicht abgelehnt.
    await store.upsert_category(eigener, panel_id, {
        "category_id": k["category_id"], "name": "Mit Rollen",
        "questions": DREI,
        "accept_roles": [str(i) for i in range(200, 212)],
    })
    geladen = await store.get_category(k["category_id"])
    check("mehr als fuenf werden gekappt",
          len(geladen["accept_roles"]) == store.MAX_ACCEPT_ROLES,
          f"({len(geladen['accept_roles'])})")

    # Doppelte fliegen raus, die Reihenfolge bleibt.
    await store.upsert_category(eigener, panel_id, {
        "category_id": k["category_id"], "name": "Mit Rollen",
        "questions": DREI,
        "accept_roles": ["9", "8", "9", "7", "8"],
    })
    geladen = await store.get_category(k["category_id"])
    check("doppelte werden entfernt", geladen["accept_roles"] == ["9", "8", "7"],
          f"({geladen['accept_roles']})")

    # Unsinn wird verworfen.
    await store.upsert_category(eigener, panel_id, {
        "category_id": k["category_id"], "name": "Mit Rollen",
        "questions": DREI, "accept_roles": ["abc", "", "42"],
    })
    geladen = await store.get_category(k["category_id"])
    check("nur Zahlen kommen durch", geladen["accept_roles"] == ["42"],
          f"({geladen['accept_roles']})")

    # Die alte Einzelrolle bleibt als Eingabe erlaubt.
    await store.upsert_category(eigener, panel_id, {
        "category_id": k["category_id"], "name": "Mit Rollen",
        "questions": DREI, "accept_role_id": "777",
    })
    geladen = await store.get_category(k["category_id"])
    check("accept_role_id wird uebernommen", geladen["accept_roles"] == ["777"],
          f"({geladen['accept_roles']})")
    check("und bleibt fuer alte Aufrufer lesbar",
          geladen["accept_role_id"] == "777")

    # Der Fall, um den es wirklich geht: eine Zeile aus der Zeit VOR
    # dieser Aenderung. Dort steht nur accept_role_id, accept_roles ist
    # leer. Ueber upsert_category laesst sich das nicht herstellen --
    # die Funktion fuellt beide Spalten -- also direkt in die Tabelle.
    import aiosqlite
    async with aiosqlite.connect(store.APP_DB) as db:
        await db.execute(
            "UPDATE app_categories SET accept_roles = '', accept_role_id = 555"
            " WHERE category_id = ?",
            (k["category_id"],),
        )
        await db.commit()

    geladen = await store.get_category(k["category_id"])
    check("eine alte Zeile behaelt ihre Rolle",
          geladen["accept_roles"] == ["555"],
          f"({geladen['accept_roles']}) -> bestehende Kategorien verlieren "
          f"still ihre Rolle, und das faellt erst beim Annehmen auf")

    return k["category_id"]


async def test_rollenvergabe():
    """
    grant_accept_roles wird ausgefuehrt.

    Die Rollenordnung ist der Punkt, den man leicht falsch macht: eine
    Rolle ueber der des Bots kann er nicht vergeben, und Discord meldet
    das erst mit 403.
    """
    print("\n   -- die Vergabe, wirklich ausgefuehrt --")

    class FakeRole:
        def __init__(self, rid, name, pos):
            self.id, self.name, self.position = rid, name, pos

        def __ge__(self, other):
            return self.position >= other.position

        def __eq__(self, other):
            return getattr(other, "id", None) == self.id

        def __hash__(self):
            return self.id

    class FakeMember:
        def __init__(self, rollen):
            self.roles = list(rollen)
            self.bekommen = []

        async def add_roles(self, rolle, reason=""):
            self.bekommen.append(rolle.name)
            self.roles.append(rolle)

    class FakeGuild:
        def __init__(self, rollen, bot_pos=10):
            self._rollen = {r.id: r for r in rollen}
            self.me = type("Me", (), {"top_role": FakeRole(0, "Bot", bot_pos)})()

        def get_role(self, rid):
            return self._rollen.get(rid)

    team = FakeRole(1, "Team", 5)
    mod = FakeRole(2, "Mod", 6)
    admin = FakeRole(3, "Admin", 50)     # ueber der Bot-Rolle
    guild = FakeGuild([team, mod, admin])

    mitglied = FakeMember([])
    vergeben, gescheitert = await store.grant_accept_roles(
        guild, mitglied, {"accept_roles": ["1", "2"]}
    )
    check("beide Rollen werden vergeben", vergeben == ["Team", "Mod"],
          f"({vergeben})")
    check("nichts scheitert", not gescheitert, f"({gescheitert})")

    # Eine Rolle ueber der des Bots.
    mitglied = FakeMember([])
    vergeben, gescheitert = await store.grant_accept_roles(
        guild, mitglied, {"accept_roles": ["1", "3"]}
    )
    check("die zu hohe Rolle wird uebersprungen", vergeben == ["Team"],
          f"({vergeben})")
    check("und gemeldet, nicht verschwiegen",
          gescheitert and "Admin" in gescheitert[0],
          f"({gescheitert}) -> sonst glaubt das Team, sie sei vergeben")

    # Eine unbekannte ID.
    mitglied = FakeMember([])
    _, gescheitert = await store.grant_accept_roles(
        guild, mitglied, {"accept_roles": ["999"]}
    )
    check("unbekannte Rollen werden gemeldet", bool(gescheitert), f"({gescheitert})")

    # Wer die Rolle schon hat, bekommt sie nicht doppelt.
    mitglied = FakeMember([team])
    vergeben, _ = await store.grant_accept_roles(
        guild, mitglied, {"accept_roles": ["1"]}
    )
    check("vorhandene Rollen werden uebersprungen", vergeben == [], f"({vergeben})")

    # Ohne Mitglied passiert gar nichts.
    vergeben, gescheitert = await store.grant_accept_roles(
        guild, None, {"accept_roles": ["1"]}
    )
    check("ohne Mitglied passiert nichts", not vergeben and not gescheitert)


# ── 2c. Zurueckziehen ────────────────────────────────────────────────

async def test_zurueckziehen(category_id: int):
    print("\n2c. Eine Bewerbung zurueckziehen")
    nutzer = 616161616161

    check("ohne Bewerbung gibt es nichts zurueckzuziehen",
          await store.withdraw(nutzer) is None)

    bewerbung = await store.submit(GUILD, category_id, nutzer, ["a", "b", "c"])
    check("sie blockiert zunaechst",
          await store.has_open_anywhere(nutzer) is not None)

    zurueck = await store.withdraw(nutzer)
    check("Zurueckziehen meldet die Bewerbung",
          zurueck is not None and zurueck["id"] == bewerbung)
    check("der Stand ist zurueckgezogen",
          zurueck["status"] == store.STATUS_CANCELLED, f"({zurueck['status']})")
    check("danach ist die Person wieder frei",
          await store.has_open_anywhere(nutzer) is None,
          "-> sonst bleibt sie bis zur Entscheidung blockiert")

    # Eine entschiedene Bewerbung laesst sich nicht zurueckziehen.
    zweite = await store.submit(GUILD, category_id, nutzer, ["x", "y", "z"])
    await store.decide(zweite, store.STATUS_ACCEPTED, STAFF, "ok")
    check("eine entschiedene bleibt unberuehrt",
          await store.withdraw(nutzer) is None)


# ── 2d. Neustart mitten in der Bewerbung ─────────────────────────────

async def test_alle_sitzungen(category_id: int):
    print("\n2d. Laufende Gespraeche nach einem Neustart")
    await store.start_session(717171717171, GUILD, category_id)
    await store.record_answer(717171717171, "erste Antwort")

    alle = await store.all_sessions()
    meine = [s for s in alle if s["user_id"] == 717171717171]
    check("das Gespraech wird gefunden", len(meine) == 1, f"({len(meine)})")
    check("der Stand ist erhalten",
          meine and meine[0]["question_index"] == 1
          and meine[0]["answers"] == ["erste Antwort"],
          f"({meine})")
    await store.end_session(717171717171)


# ── 3. Der DM-Ablauf ─────────────────────────────────────────────────

async def test_ablauf(category_id: int):
    print("\n3. Fragen einzeln, Antworten der Reihe nach")
    await store.start_session(USER, GUILD, category_id)

    sitzung = await store.get_session(USER)
    check("Gespraech beginnt bei Frage eins", sitzung["question_index"] == 0)
    check("noch keine Antwort", sitzung["answers"] == [])

    kategorie = await store.get_category(category_id)
    for i, _ in enumerate(kategorie["questions"]):
        sitzung = await store.record_answer(USER, f"Antwort {i + 1}")
    check("alle Antworten gesammelt",
          len(sitzung["answers"]) == len(kategorie["questions"]),
          f"({len(sitzung['answers'])})")
    check("Zaehler steht am Ende",
          sitzung["question_index"] == len(kategorie["questions"]))

    # Zu lange Antworten werden gekuerzt, nicht abgelehnt.
    await store.record_answer(USER, "x" * 5000)
    sitzung = await store.get_session(USER)
    check("lange Antwort wird gekuerzt",
          len(sitzung["answers"][-1]) == store.MAX_ANSWER_LEN,
          f"({len(sitzung['answers'][-1])})")

    await store.end_session(USER)
    check("Gespraech beendet", await store.get_session(USER) is None)


# ── 4. Nur eine Bewerbung, serveruebergreifend ───────────────────────

async def test_eine_bewerbung(category_id: int):
    print("\n4. Nur eine offene Bewerbung -- ueber alle Server")

    check("am Anfang ist nichts offen",
          await store.has_open_anywhere(USER) is None)

    await store.start_session(USER, GUILD, category_id)
    offen = await store.has_open_anywhere(USER)
    check("ein laufendes Gespraech blockiert",
          offen is not None and offen["kind"] == "session")

    # Auch auf einem anderen Server -- der Bot fragt ja in derselben DM.
    check("blockiert auch fuer andere Server",
          await store.has_open_anywhere(USER) is not None)

    await store.end_session(USER)
    check("nach dem Ende wieder frei",
          await store.has_open_anywhere(USER) is None)

    # Eine eingereichte, unentschiedene Bewerbung blockiert ebenfalls.
    bewerbung = await store.submit(GUILD, category_id, USER, ["a", "b", "c"])
    offen = await store.has_open_anywhere(USER)
    check("eine offene Bewerbung blockiert",
          offen is not None and offen["kind"] == "pending")

    await store.decide(bewerbung, store.STATUS_DENIED, STAFF, "Diesmal nicht.")
    check("nach der Entscheidung wieder frei",
          await store.has_open_anywhere(USER) is None)

    # Und eine andere Person ist davon nicht betroffen.
    await store.start_session(555444333, GUILD, category_id)
    check("andere Person ist frei",
          await store.has_open_anywhere(USER) is None)
    await store.end_session(555444333)


# ── 5. Entscheiden ───────────────────────────────────────────────────

async def test_entscheiden(category_id: int):
    print("\n5. Annehmen und ablehnen")
    bewerbung = await store.submit(GUILD, category_id, 777666555, ["x", "y", "z"])

    ergebnis = await store.decide(bewerbung, store.STATUS_ACCEPTED, STAFF,
                                  "Passt gut.")
    check("Annehmen klappt", ergebnis is not None
          and ergebnis["status"] == store.STATUS_ACCEPTED)
    check("die Begruendung wird gespeichert", ergebnis["reason"] == "Passt gut.")
    check("wer entschieden hat, steht drin", ergebnis["decided_by"] == str(STAFF))

    # Zwei Teammitglieder koennen gleichzeitig klicken -- der zweite
    # Klick darf nichts mehr aendern.
    nochmal = await store.decide(bewerbung, store.STATUS_DENIED, 111, "Doch nicht")
    check("der zweite Klick aendert nichts", nochmal is None,
          "-> sonst ueberschreibt der Zweite die Entscheidung des Ersten")
    danach = await store.get_application(bewerbung)
    check("die erste Entscheidung bleibt stehen",
          danach["status"] == store.STATUS_ACCEPTED)

    try:
        await store.decide(bewerbung, "vielleicht", STAFF, "x")
        check("unbekannter Status wird abgelehnt", False)
    except ValueError:
        check("unbekannter Status wird abgelehnt", True)


# ── 6. Sperre nach Ablehnung ─────────────────────────────────────────

async def test_sperre(panel_id: int, category_id: int):
    print("\n6. Sperre nach einer Ablehnung")
    import time

    abgelehnt = await store.submit(GUILD, category_id, 888777666, ["a", "b", "c"])
    await store.decide(abgelehnt, store.STATUS_DENIED, STAFF, "Nein.")

    frei_ab = await store.denied_until(888777666, category_id, 7)
    check("die Sperre greift", frei_ab is not None and frei_ab > int(time.time()))

    check("ohne Sperre ist sofort wieder frei",
          await store.denied_until(888777666, category_id, 0) is None)

    # Eine andere Kategorie bleibt frei -- eine Absage als Moderator
    # soll niemanden als Supporter blockieren. Das erste Panel ist nach
    # Test 2 voll, also ein eigenes fuer diesen Fall.
    zweites = await store.create_panel(777000111222333, "Sperrtest")
    andere = await store.upsert_category(777000111222333, zweites["panel_id"], {
        "name": "Andere Rolle", "questions": DREI,
    })
    check("andere Kategorie ist nicht gesperrt",
          await store.denied_until(888777666, andere["category_id"], 7) is None)

    # Und wer nie abgelehnt wurde, ist frei.
    check("ohne Ablehnung keine Sperre",
          await store.denied_until(123123123, category_id, 7) is None)


# ── 7. Abgelaufene Gespraeche ────────────────────────────────────────

async def test_ablauf_zeit(category_id: int):
    print("\n7. Vergessene Bewerbungen laufen ab")
    import time

    await store.start_session(444333222, GUILD, category_id)
    check("frisch ist nichts abgelaufen",
          not any(s["user_id"] == 444333222 for s in await store.stale_sessions()))

    spaeter = int(time.time()) + store.ANSWER_TIMEOUT + 60
    alt = await store.stale_sessions(now=spaeter)
    check("nach der Frist laeuft es ab",
          any(s["user_id"] == 444333222 for s in alt))

    await store.end_session(444333222)
    check("danach blockiert es niemanden mehr",
          await store.has_open_anywhere(444333222) is None)


# ── 8. Verdrahtung ───────────────────────────────────────────────────

def test_verdrahtung():
    print("\n8. Cog, Route, Schema und Dashboard")
    init = read("cogs/__init__.py")
    check("Cog wird importiert",
          "from .commands.applications import Applications" in init)
    check("Cog wird hinzugefuegt", "add_cog(Applications(bot))" in init)

    quelle = read("cogs/commands/applications.py")
    baum = ast.parse(quelle)

    # Ein on_message ohne Dekorator wird nie aufgerufen.
    listener = set()
    for k in ast.walk(baum):
        if isinstance(k, ast.AsyncFunctionDef):
            for d in k.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "listener":
                    listener.add(k.name)
    check("on_message ist registriert", "on_message" in listener,
          "-> die Antworten kaemen nie an")
    check("on_interaction ist registriert", "on_interaction" in listener,
          "-> die Knoepfe waeren nach einem Neustart tot")
    check("on_ready ist registriert", "on_ready" in listener,
          "-> das Auswahlmenue reagierte nach einem Neustart nicht mehr")

    stripped = strip_py(quelle)
    # Nur DMs auswerten -- sonst liest der Bot jede Nachricht im Server
    # als Bewerbungsantwort.
    check("nur Direktnachrichten zaehlen",
          "message.guild is not None" in stripped,
          "-> sonst wird jede Servernachricht zur Antwort")
    check("eigene Nachrichten werden uebersprungen",
          "message.author.bot" in stripped)
    # Abbrechen: die Woerter muessen in einem Vergleich stehen, nicht
    # irgendwo im Text -- ein "if False:" davor laesst sie stehen.
    abbruch = False
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Compare) and isinstance(knoten.ops[0], ast.In):
            if "abbrechen" in ast.unparse(knoten).lower():
                abbruch = True
    check("Abbrechen wird wirklich geprueft", abbruch,
          "-> das Wort steht da, wird aber nicht ausgewertet")

    # Die Knoepfe muessen ohne Zeitgrenze gebaut werden. Im Syntaxbaum
    # nachsehen: "timeout=None" kommt an mehreren Stellen vor.
    def super_timeout(klassenname):
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.ClassDef) or knoten.name != klassenname:
                continue
            for unter in ast.walk(knoten):
                if isinstance(unter, ast.Call) and "super()" in ast.unparse(unter.func):
                    for kw in unter.keywords:
                        if kw.arg == "timeout":
                            return ast.unparse(kw.value)
        return "(nicht gefunden)"

    check("die Entscheidungsknoepfe haben keine Zeitgrenze",
          super_timeout("DecisionView") == "None",
          f"-> timeout={super_timeout('DecisionView')}, nach einem Neustart tot")
    check("das Auswahlmenue hat keine Zeitgrenze",
          super_timeout("ApplicationPanelView") == "None",
          f"-> timeout={super_timeout('ApplicationPanelView')}")

    check("eine Begruendung ist Pflicht", "required=True" in stripped)

    # Das Aufraeumen muss wirklich gestartet werden.
    gestartet = False
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == "__init__":
            for unter in ast.walk(knoten):
                if isinstance(unter, ast.Call) and ast.unparse(unter).startswith(
                        "self.cleanup_sessions.start"):
                    gestartet = True
    check("das Aufraeumen wird gestartet", gestartet,
          "-> eine vergessene Bewerbung blockierte die Person fuer immer")

    # Nach einem Neustart muss die offene Frage neu gestellt werden --
    # sonst wartet der Bewerber auf eine Nachricht, die nie kommt: er
    # antwortet nicht, weil er wartet, und die naechste Frage kommt nur
    # als Antwort auf eine Nachricht.
    on_ready = resume = submit = build = None
    for k in ast.walk(baum):
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "on_ready":
            on_ready = ast.get_source_segment(quelle, k)
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "_resume_sessions":
            resume = ast.get_source_segment(quelle, k)
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "_submit":
            submit = ast.get_source_segment(quelle, k)
        if isinstance(k, ast.FunctionDef) and k.name == "_build_embed":
            build = ast.get_source_segment(quelle, k)

    check("on_ready stoesst die laufenden Gespraeche an",
          bool(on_ready and "_resume_sessions" in on_ready),
          "-> eine Bewerbung haengt nach jedem Deploy")
    check("und die offene Frage wird neu gestellt",
          bool(resume and "_ask_next" in resume),
          "-> der Bewerber wartet fuer immer")
    check("eine geloeschte Kategorie beendet das Gespraech",
          bool(resume and "end_session" in resume),
          "-> die Person waere dauerhaft blockiert")

    # Das Team muss erfahren, dass eine Bewerbung da ist.
    check("das Team wird erwaehnt",
          bool(submit and "erwaehnungen" in submit and "mention" in submit),
          "-> die Bewerbung liegt im Kanal und niemand merkt es")
    check("die Erwaehnung landet in der Karte",
          bool(submit and "embed.description = " in submit),
          "-> sonst braeuchte es content=, und das lehnt Discord bei V2 ab")
    check("kein content= bei einer V2-Ansicht", "content=" not in stripped,
          "-> Discord antwortet mit 50035")
    check("nur die Team-Rollen duerfen gepingt werden",
          bool(submit and "AllowedMentions" in submit),
          "-> eine Antwort des Bewerbers koennte @everyone enthalten")

    # Und wie lange sie schon liegt.
    check("der Zeitpunkt steht in der Nachricht",
          bool(build and "<t:" in build),
          "-> man sieht nicht, ob sie von heute oder letzter Woche ist")

    route = read("api/routes/applications.py")
    for pfad in ('"/{guild_id}/panels"', '"/{guild_id}/panels/{panel_id}/send"',
                 '"/{guild_id}/entries"'):
        check(f"Route {pfad} vorhanden", pfad in route)
    # Beide Pruefungen muessen einen Abbruch ausloesen. "if False:"
    # laesst den Namen stehen und prueft trotzdem nichts mehr.
    route_baum = ast.parse(route)
    abbrueche = set()
    for knoten in ast.walk(route_baum):
        if not isinstance(knoten, ast.If):
            continue
        bedingung = ast.unparse(knoten.test)
        wirft = any(isinstance(u, ast.Raise) for u in ast.walk(knoten))
        if not wirft:
            continue
        if "ohne_ziel" in bedingung:
            abbrueche.add("ziel")
        if "rechte.send_messages" in bedingung or "rechte.view_channel" in bedingung:
            abbrueche.add("rechte")
    check("ohne Ergebniskanal wird abgebrochen", "ziel" in abbrueche,
          "-> die erste Bewerbung landete sonst im Nichts")
    check("ohne Schreibrechte wird abgebrochen", "rechte" in abbrueche,
          "-> das Posten scheiterte sonst wortlos")
    check("Entscheiden verlangt eine Begruendung",
          "Eine Begründung ist erforderlich" in route)

    server = read("api/server.py")
    check("Router eingehaengt", 'prefix="/applications"' in server)

    guard = read("api/schema_guard.py")
    check("schema_guard kennt db/applications.db", '"db/applications.db"' in guard)
    for tabelle in ("app_panels", "app_categories", "active_sessions",
                    "applications"):
        check(f"schema_guard kennt {tabelle}", tabelle in guard)

    # Fuenf Stellen, sonst findet die Seite niemand.
    seite = os.path.join(DASH, "app/dashboard/guild/[guildId]/applications/page.tsx")
    check("die Seite existiert", os.path.isfile(seite))
    tabs = read_dash("components/guild-tabs.tsx")
    check("Reiter eingetragen", 'slug: "applications"' in tabs)
    check("Reiter-Icon importiert",
          bool(re.search(r"^\s*ClipboardList,\s*$", tabs, re.M)))
    suche = read_dash("components/global-search.tsx")
    check("in der Suche eingetragen", "/applications" in suche)
    layout = read_dash("app/dashboard/layout.tsx")
    check("in der Seitenleiste eingetragen", "/applications`" in layout)
    bars = read("tests/test_dashboard_save_bars.py")
    check("in der Ausnahmeliste der Speicherleisten", '"applications",' in bars)

    panel = read_dash("components/dashboard/applications-panel.tsx")
    check("das Panel benutzt den gemeinsamen Schalter",
          "<SwitchToggle" in panel,
          "-> eine eigene Kopie holt sich den alten Darstellungsfehler zurueck")
    check("und baut keine eigene Bahn",
          "rounded-full transition-colors shrink-0" not in panel,
          "-> das ist die handgeschriebene Kopie mit dem Anker-Fehler")
    check("die Fragenliste ist begrenzt", "max={limits.max_questions}" in panel)
    check("zu wenige Fragen werden angezeigt", "min_questions" in panel)


async def test_schema_wirkung():
    """
    schema_guard wird ausgefuehrt.

    Die Textsuche oben faellt nicht auf, wenn der Datenbankname
    verstellt wird: sie findet dann nichts und meldet nichts. Hier
    entsteht die Datenbank wirklich.
    """
    print("\n8b. schema_guard legt die Tabellen an")
    import aiosqlite

    from api import schema_guard

    await schema_guard.ensure_schema()
    async with aiosqlite.connect("db/applications.db") as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tabellen = {r[0] for r in await cursor.fetchall()}

    for name in ("app_panels", "app_categories", "active_sessions",
                 "applications"):
        check(f"{name} wurde angelegt", name in tabellen,
              f"-> ohne die Tabelle scheitert die erste Bewerbung ({tabellen})")

    # Und die nachtraegliche Spalte muss auch entstehen.
    async with aiosqlite.connect("db/applications.db") as db:
        async with db.execute("PRAGMA table_info(app_categories)") as cursor:
            spalten = {r[1] for r in await cursor.fetchall()}
    check("accept_roles ist vorhanden", "accept_roles" in spalten,
          f"({sorted(spalten)})")

    # Und der Store muss sich auch ohne schema_guard selbst helfen.
    #
    # Eine Installation, die vor dieser Aenderung lief, hat die Spalte
    # nicht -- und ohne sie scheitert jede Abfrage mit "no such column",
    # der ganze Reiter ist tot. Nachgemessen: CREATE TABLE IF NOT EXISTS
    # traegt sie NICHT nach.
    import sqlite3

    alt_pfad = "db/applications_alt.db"
    conn = sqlite3.connect(alt_pfad)
    conn.executescript("""
        CREATE TABLE app_categories (category_id INTEGER PRIMARY KEY AUTOINCREMENT,
          panel_id INTEGER, guild_id INTEGER, name TEXT, emoji TEXT,
          description TEXT, questions TEXT, results_channel_id INTEGER,
          accept_role_id INTEGER, staff_roles TEXT, position INTEGER);
        CREATE TABLE app_panels (panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER, name TEXT, channel_id INTEGER, message_id INTEGER,
          results_channel_id INTEGER, embed_title TEXT, embed_description TEXT,
          embed_color INTEGER, embed_image_url TEXT, embed_thumbnail_url TEXT,
          placeholder TEXT, deny_cooldown_enabled INTEGER,
          deny_cooldown_days INTEGER);
        INSERT INTO app_panels VALUES (1,99,'P',NULL,NULL,NULL,'T','',0,
          NULL,NULL,'',0,7);
        INSERT INTO app_categories VALUES (1,1,99,'Mod','','',
          '["a","b","c"]',NULL,555,'',0);
    """)
    conn.commit()
    conn.close()

    echt = store.APP_DB
    store.APP_DB = alt_pfad
    try:
        panels = await store.list_panels(99)
        geladen = panels[0]["categories"][0]
        check("der Store repariert eine alte Datenbank selbst",
              geladen["accept_roles"] == ["555"],
              f"({geladen['accept_roles']}) -> sonst ist der Reiter tot")
    except Exception as exc:
        check("der Store repariert eine alte Datenbank selbst", False,
              f"-> {type(exc).__name__}: {exc}")
    finally:
        store.APP_DB = echt


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)
        try:
            panel_id = await test_panels()
            category_id = await test_kategorien(panel_id)
            await test_accept_rollen(panel_id)
            await test_rollenvergabe()
            await test_zurueckziehen(category_id)
            await test_alle_sitzungen(category_id)
            await test_schema_wirkung()
            await test_ablauf(category_id)
            await test_eine_bewerbung(category_id)
            await test_entscheiden(category_id)
            await test_sperre(panel_id, category_id)
            await test_ablauf_zeit(category_id)
        finally:
            os.chdir(alt)

    test_verdrahtung()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Bewerbungen: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
