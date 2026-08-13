#!/usr/bin/env python3
"""
Der Tester-Bereich.

Wer die Rolle **Tester** hat, sieht im Admin-Panel genau einen Reiter
und bekommt alle Premium-Funktionen ohne Key. Beides haengt an
derselben Rolle: wird sie entzogen, ist beides sofort weg.

Worauf es hier ankommt:

  * **Der Bypass muss an der Rolle haengen, nicht an einer Sitzung.**
    Sonst behaelt jemand Premium, dem es gerade genommen wurde.
  * **Ein Tester darf nur seinen Reiter sehen.** Die Rolle ist bewusst
    eng -- ausprobieren, nicht verwalten.
  * **Fremde Meldungen gehen ihn nichts an.** In einer Fehlermeldung
    steht schnell mehr, als der Melder oeffentlich sagen wollte.
  * **Die Rechte werden im Bot geprueft**, nicht nur im Dashboard.

Geprueft wird gegen echte SQLite-Dateien in einem Temp-Ordner.

Run:  python3 tests/test_tester_area.py
"""

import asyncio
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts):
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


TESTER = "1303627964734246944"
OTHER = "1033826242270609449"


class TempState:
    """Rollen und Premium auf Temp-Dateien, damit nichts Echtes leidet."""

    def __init__(self):
        self.dir = None

    def __enter__(self):
        from utils import dashboard_roles as dr
        from utils import premium_store as ps
        from utils import tester_feedback as tf

        self.dir = tempfile.mkdtemp()
        self.old_premium = ps.DB_PATH
        self.old_feedback = tf.DB_PATH
        ps.DB_PATH = os.path.join(self.dir, "premium.db")
        tf.DB_PATH = os.path.join(self.dir, "feedback.db")
        # Der Rollen-Cache liegt im Speicher -- leeren reicht.
        dr._cache.clear()
        return dr, ps, tf

    def __exit__(self, *_exc):
        from utils import dashboard_roles as dr
        from utils import premium_store as ps
        from utils import tester_feedback as tf

        ps.DB_PATH = self.old_premium
        tf.DB_PATH = self.old_feedback
        dr._cache.clear()
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


# --------------------------------------------------------------------- #
# Die Rolle
# --------------------------------------------------------------------- #


def test_the_role_exists_and_is_narrow():
    """Ein Tester soll ausprobieren, nicht verwalten."""

    print("\nDie Tester-Rolle ist eng geschnitten")

    from utils import dashboard_roles as dr

    role = dr.ROLES_BY_KEY.get("tester")
    check("es gibt die Rolle", role is not None)
    if role is None:
        return

    check("sie heißt Tester", role.label == "Tester", role.label)
    check("es gibt die Berechtigung",
          "tester.access" in dr.PERMISSIONS_BY_KEY)

    # Genau die drei: Anmelden, Serverliste, der eigene Reiter. Alles
    # weitere waere eine Berechtigung, die niemand angefordert hat.
    check("sie öffnet nur den Tester-Reiter",
          set(role.permissions) == {"dashboard.access", "guild.view",
                                    "tester.access"},
          str(sorted(role.permissions)))

    # Kein Recht, das etwas verändert.
    dangerous = [
        key for key in role.permissions
        if dr.PERMISSIONS_BY_KEY.get(key)
        and dr.PERMISSIONS_BY_KEY[key].dangerous
    ]
    check("keine gefährliche Berechtigung", not dangerous, str(dangerous))

    # Niedriger Rang: sonst könnte ein Tester Rollen unter sich
    # vergeben, sobald er je team.assign bekäme.
    check("der Rang ist niedrig", role.rank <= 20, str(role.rank))


# --------------------------------------------------------------------- #
# Der Premium-Bypass
# --------------------------------------------------------------------- #


def test_the_role_grants_premium_and_taking_it_removes_premium():
    """
    Der Kern: Premium hängt an der Rolle.

    Wird sie entzogen, muss Premium im selben Moment weg sein -- nicht
    erst beim nächsten Neustart oder wenn eine Sitzung ausläuft.
    """

    print("\nDie Rolle schaltet Premium frei — und wieder ab")

    with TempState() as (dr, ps, _tf):
        async def run():
            before = ps.status(TESTER)
            check("vorher kein Premium", before["premium"] is False)
            check("und nicht über die Rolle", before["via_tester"] is False)

            await dr.assign(TESTER, "tester", granted_by="owner")

            during = ps.status(TESTER)
            check("mit der Rolle: Premium", during["premium"] is True,
                  "der Bypass greift nicht")
            check("als unbefristet gemeldet", during["lifetime"] is True)
            check("und als Tester-Zugang markiert",
                  during["via_tester"] is True,
                  "sonst sieht es aus wie ein gekaufter Lifetime-Key")

            await dr.revoke(TESTER, "tester")

            after = ps.status(TESTER)
            check("nach dem Entzug: kein Premium",
                  after["premium"] is False,
                  "der Zugang bleibt bestehen, obwohl die Rolle weg ist")
            check("und nicht mehr markiert", after["via_tester"] is False)

        asyncio.run(run())


def test_the_bypass_does_not_leak_to_others():
    print("\nDer Bypass gilt nur für Tester")

    with TempState() as (dr, ps, _tf):
        async def run():
            await dr.assign(TESTER, "tester", granted_by="owner")
            check("ein Fremder bekommt nichts",
                  ps.status(OTHER)["premium"] is False)

            # Auch eine andere Rolle schaltet nichts frei.
            await dr.assign(OTHER, "moderator", granted_by="owner")
            check("eine andere Rolle auch nicht",
                  ps.status(OTHER)["premium"] is False,
                  "jede Team-Rolle bekäme Premium")

        asyncio.run(run())


def test_a_real_key_still_wins():
    """Ein bezahlter Key darf nicht als Tester-Zugang erscheinen."""

    print("\nEin echter Key bleibt ein echter Key")

    with TempState() as (dr, ps, _tf):
        key = ps.create_key(created_by="owner", duration_days=0)
        ps.redeem(key["key"], OTHER)

        state = ps.status(OTHER)
        check("der Key gibt Premium", state["premium"] is True)
        check("aber nicht über die Rolle", state["via_tester"] is False,
              "sonst steht bei einem zahlenden Kunden „Tester-Zugang“")


def test_a_broken_role_lookup_does_not_grant_premium():
    """Im Zweifel nein -- und niemandem etwas wegnehmen."""

    print("\nEine kaputte Rollenabfrage schaltet nichts frei")

    with TempState() as (dr, ps, _tf):
        original = dr.is_tester

        def explode(_user):
            raise RuntimeError("Rollen weg")

        dr.is_tester = explode
        try:
            state = ps.status(TESTER)
            check("kein Premium aus dem Fehler", state["premium"] is False)
            check("und keine Ausnahme nach oben", True)
        except Exception as exc:
            check("und keine Ausnahme nach oben", False,
                  f"{type(exc).__name__}: {exc}")
        finally:
            dr.is_tester = original


# --------------------------------------------------------------------- #
# Die Routen
# --------------------------------------------------------------------- #


def test_the_routes_check_the_role_themselves():
    """Eine Sperre, die nur im Dashboard sitzt, ist keine."""

    print("\nDie Routen prüfen die Rolle selbst")

    from fastapi import HTTPException

    from api.routes import tester

    with TempState() as (dr, _ps, _tf):
        async def run():
            # 1. Ohne Rolle: abgewiesen.
            try:
                await tester.deploy_changelog(user_id=OTHER)
                check("ohne Rolle kein Changelog", False,
                      "ein Fremder liest den Tester-Bereich")
            except HTTPException as exc:
                check("ohne Rolle kein Changelog", exc.status_code == 403,
                      f"HTTP {exc.status_code}")

            # 2. Ganz ohne Anmeldung ebenso.
            try:
                await tester.deploy_changelog(user_id="")
                check("ohne Anmeldung erst recht nicht", False)
            except HTTPException as exc:
                check("ohne Anmeldung erst recht nicht",
                      exc.status_code == 401, f"HTTP {exc.status_code}")

            # 3. Mit Rolle: erlaubt.
            await dr.assign(TESTER, "tester", granted_by="owner")
            body = await tester.deploy_changelog(user_id=TESTER)
            check("mit Rolle kommt der Changelog", "entries" in body)

            # 4. Rolle weg -> sofort wieder gesperrt.
            await dr.revoke(TESTER, "tester")
            try:
                await tester.deploy_changelog(user_id=TESTER)
                check("nach dem Entzug gesperrt", False,
                      "der Reiter bleibt offen, obwohl die Rolle weg ist")
            except HTTPException as exc:
                check("nach dem Entzug gesperrt", exc.status_code == 403)

        asyncio.run(run())


def test_a_tester_sees_only_their_own_reports():
    """
    Fremde Meldungen gehen einen Tester nichts an.

    In einer Fehlermeldung steht schnell mehr, als der Melder
    öffentlich sagen wollte.
    """

    print("\nEin Tester sieht nur seine eigenen Meldungen")

    from api.routes import tester

    with TempState() as (dr, _ps, tf):
        async def run():
            await dr.assign(TESTER, "tester", granted_by="owner")
            await dr.assign(OTHER, "tester", granted_by="owner")

            tf.submit(TESTER, "Mein Fehler", body="passiert immer")
            tf.submit(OTHER, "Fremder Fehler", body="geheim")

            body = await tester.list_feedback(user_id=TESTER)
            titles = [e["title"] for e in body["entries"]]

            check("die eigene Meldung ist dabei", "Mein Fehler" in titles)
            check("die fremde nicht", "Fremder Fehler" not in titles,
                  str(titles))
            check("der Umfang ist markiert", body["scope"] == "own")

        asyncio.run(run())


def test_a_tester_cannot_open_a_stranger_report():
    """
    Die Liste filtert -- die Einzelansicht muss es auch.

    Sonst kommt man über /feedback/17 an jede fremde Meldung, obwohl
    sie in keiner Liste auftaucht. Ein Mutationstest hat gezeigt, dass
    diese Prüfung ersatzlos entfallen konnte, ohne dass ein Test rot
    wurde.
    """

    print("\nEin Tester öffnet keine fremde Meldung")

    from fastapi import HTTPException

    from api.routes import tester

    with TempState() as (dr, _ps, tf):
        async def run():
            await dr.assign(TESTER, "tester", granted_by="owner")
            await dr.assign(OTHER, "tester", granted_by="owner")

            mine = tf.submit(TESTER, "Meine eigene Meldung")["id"]
            theirs = tf.submit(OTHER, "Die Meldung des anderen")["id"]

            # Die eigene: geht.
            entry = await tester.feedback_detail(mine, user_id=TESTER)
            check("die eigene Meldung geht auf", entry["id"] == mine)

            # Die fremde: nicht.
            try:
                await tester.feedback_detail(theirs, user_id=TESTER)
                check("die fremde bleibt zu", False,
                      "jeder Tester liest jede Meldung über die ID")
            except HTTPException as exc:
                check("die fremde bleibt zu", exc.status_code == 403,
                      f"HTTP {exc.status_code}")

            # Kommentieren ebenfalls nicht.
            try:
                await tester.add_comment(
                    theirs, {"user_id": TESTER, "text": "hallo"}
                )
                check("und man kann dort nicht mitreden", False,
                      "ein Tester kommentiert in fremden Meldungen")
            except HTTPException as exc:
                check("und man kann dort nicht mitreden",
                      exc.status_code == 403, f"HTTP {exc.status_code}")

            # In der eigenen schon.
            ok = await tester.add_comment(
                mine, {"user_id": TESTER, "text": "Nachtrag"}
            )
            check("in der eigenen schon", ok["added"] is True)

        asyncio.run(run())


def test_owners_see_everything():
    print("\nOwner sehen alle Meldungen")

    from api.routes import tester

    with TempState() as (dr, _ps, tf):
        original = dr.is_owner
        dr.is_owner = lambda uid: str(uid) == OTHER
        try:
            async def run():
                tf.submit(TESTER, "Mein Fehler")
                tf.submit(OTHER, "Anderer Fehler")

                body = await tester.list_feedback(user_id=OTHER)
                titles = [e["title"] for e in body["entries"]]

                check("beide Meldungen sind da", len(titles) == 2, str(titles))
                check("der Umfang ist markiert", body["scope"] == "all")
                check("es gibt Zahlen", body["stats"].get("total") == 2)

            asyncio.run(run())
        finally:
            dr.is_owner = original


def test_only_owners_change_the_state():
    """Ein Tester darf seine eigene Meldung nicht auf »erledigt« setzen."""

    print("\nDen Stand setzen dürfen nur Owner")

    from fastapi import HTTPException

    from api.routes import tester

    with TempState() as (dr, _ps, tf):
        async def run():
            await dr.assign(TESTER, "tester", granted_by="owner")
            entry = tf.submit(TESTER, "Mein Fehler")

            try:
                await tester.update_feedback(
                    entry["id"], {"user_id": TESTER, "state": "done"}
                )
                check("ein Tester darf das nicht", False,
                      "er hat seine eigene Meldung geschlossen")
            except HTTPException as exc:
                check("ein Tester darf das nicht", exc.status_code == 403)

            # Und die Mitgliederliste erst recht nicht: sie zeigt, wer
            # Premium ohne Key hat.
            try:
                await tester.members(user_id=TESTER)
                check("die Mitgliederliste bleibt zu", False)
            except HTTPException as exc:
                check("die Mitgliederliste bleibt zu",
                      exc.status_code == 403)

        asyncio.run(run())


def test_a_report_needs_a_title():
    print("\nEine Meldung braucht einen Titel")

    with TempState() as (_dr, _ps, tf):
        check("leer wird abgelehnt", tf.submit(TESTER, "")["ok"] is False)
        check("zu kurz auch", tf.submit(TESTER, "ab")["ok"] is False)
        check("ein echter Titel geht durch",
              tf.submit(TESTER, "Der Knopf tut nichts")["ok"] is True)

        # Unbekannte Art faellt auf "bug" zurueck statt zu werfen.
        tf.submit(TESTER, "Irgendwas passiert hier", kind="quatsch")
        entries = tf.listing(user_id=TESTER)
        check("eine unbekannte Art wird zu »bug«",
              all(e["kind"] in tf.KINDS for e in entries),
              str([e["kind"] for e in entries]))

        # Ein Vorschlag hat keine Dringlichkeit -- er ist ein Wunsch.
        result = tf.submit(TESTER, "Waere schoen wenn", kind="idea",
                           priority="critical")
        entry = tf.detail(result["id"])
        check("ein Vorschlag bleibt auf normal",
              entry["priority"] == "normal", entry["priority"])


def test_the_history_is_append_only():
    """
    Der Grund fuer den Umbau.

    Vorher gab es ein einziges Notizfeld: die zweite Antwort
    ueberschrieb die erste, und niemand konnte nachlesen, warum etwas
    abgelehnt wurde.
    """

    print("\nDer Verlauf wird nur ergänzt")

    with TempState() as (_dr, _ps, tf):
        entry = tf.submit(TESTER, "Der Knopf tut nichts")["id"]

        tf.update(entry, actor="owner", state="confirmed",
                  note="Kann ich nachstellen.")
        tf.update(entry, actor="owner", state="in_progress")
        tf.comment(entry, TESTER, "Danke!")
        tf.update(entry, actor="owner", state="done", note="Behoben.")

        log = tf.detail(entry)["log"]
        texts = [item["text"] for item in log]

        check("die erste Antwort steht noch da",
              any("nachstellen" in t for t in texts), str(texts))
        check("die letzte auch",
              any("Behoben" in t for t in texts), str(texts))
        check("die Antwort des Melders ebenfalls",
              any("Danke" in t for t in texts))
        check("jede Statusänderung ist vermerkt",
              sum(1 for i in log if i["kind"] == "state") >= 3,
              str([i["kind"] for i in log]))

        # Und die Reihenfolge stimmt: aelteste zuerst.
        check("der Verlauf ist chronologisch",
              [i["id"] for i in log] == sorted(i["id"] for i in log))


def test_duplicates_are_flagged_not_blocked():
    """
    Ein Hinweis, keine Sperre.

    Zwei Leute koennen dieselbe Ueberschrift fuer verschiedene Dinge
    waehlen -- und wer ein "gibt es schon" bekommt, meldet beim
    naechsten Mal gar nichts mehr.
    """

    print("\nDubletten werden gemeldet, nicht abgelehnt")

    with TempState() as (_dr, _ps, tf):
        first = tf.submit(TESTER, "Der Knopf tut nichts!")
        check("die erste geht durch", first["ok"] is True)
        check("und findet nichts Ähnliches", first["similar"] == [])

        second = tf.submit(OTHER, "knopf tut nichts")
        check("die zweite geht auch durch", second["ok"] is True,
              "eine Dublette wurde abgelehnt")
        check("aber sie nennt die erste",
              [s["id"] for s in second["similar"]] == [first["id"]],
              str(second["similar"]))

        # Ein voellig anderer Titel darf nicht als Dublette gelten.
        third = tf.submit(TESTER, "Die Farben im Diagramm stimmen nicht")
        check("ein anderer Titel ist keine Dublette",
              third["similar"] == [], str(third["similar"]))

        # Eine erledigte Meldung wird nicht mehr vorgeschlagen.
        #
        # Beide bisherigen ("Der Knopf tut nichts!" und "knopf tut
        # nichts") haben denselben Fingerabdruck. Also müssen beide
        # geschlossen werden, sonst schlägt die zweite weiterhin an --
        # der erste Anlauf dieses Tests hat genau das übersehen.
        tf.update(first["id"], actor="owner", state="done")
        tf.update(second["id"], actor="owner", state="rejected")

        fourth = tf.submit(TESTER, "Der Knopf tut nichts")
        check("erledigte zählen nicht mehr",
              fourth["similar"] == [], str(fourth["similar"]))


def test_votes_count_once_per_person():
    print("\nZustimmung zählt einmal je Person")

    with TempState() as (_dr, _ps, tf):
        entry = tf.submit(TESTER, "Betrifft mich auch")["id"]

        tf.vote(entry, OTHER)
        tf.vote(entry, OTHER)  # zweites Mal: zuruecknehmen
        check("zweimal klicken nimmt zurück",
              tf.detail(entry)["votes"] == 0)

        tf.vote(entry, OTHER)
        tf.vote(entry, "333")
        check("zwei Leute, zwei Stimmen",
              tf.detail(entry)["votes"] == 2)
        check("die eigene Stimme ist markiert",
              tf.detail(entry, viewer=OTHER)["voted"] is True)
        check("die eines anderen nicht",
              tf.detail(entry, viewer="999")["voted"] is False)


def test_open_and_urgent_come_first():
    """Sonst verschwindet eine offene Meldung unter zwanzig erledigten."""

    print("\nOffen und dringend steht oben")

    with TempState() as (_dr, _ps, tf):
        done = tf.submit(TESTER, "Schon erledigt worden")["id"]
        tf.update(done, actor="owner", state="done")
        small = tf.submit(TESTER, "Kleiner Schreibfehler", priority="low")["id"]
        urgent = tf.submit(TESTER, "Gar nichts geht mehr",
                           priority="critical")["id"]

        order = [e["id"] for e in tf.listing()]
        check("das Dringendste zuerst", order[0] == urgent, str(order))
        check("das Erledigte zuletzt", order[-1] == done, str(order))
        check("die Kleinigkeit dazwischen", order[1] == small, str(order))


def test_a_duplicate_cannot_point_at_itself():
    """Sonst dreht sich die Anzeige im Kreis."""

    print("\nEin Duplikat verweist nicht auf sich selbst")

    with TempState() as (_dr, _ps, tf):
        entry = tf.submit(TESTER, "Irgendein Fehler hier")["id"]
        result = tf.update(entry, actor="owner", duplicate_of=entry)
        check("wird abgelehnt", result["ok"] is False, str(result))

        other = tf.submit(TESTER, "Ein anderer Fehler")["id"]
        ok = tf.update(other, actor="owner", duplicate_of=entry)
        check("auf eine andere zeigen geht", ok["ok"] is True)
        check("und setzt den Stand",
              tf.detail(other)["state"] == "duplicate")


def test_an_old_database_is_upgraded():
    """
    Die erste Fassung hatte weniger Spalten.

    Ohne Nachziehen schlaegt jede Abfrage fehl -- und die bereits
    gemeldeten Sachen waeren weg.
    """

    print("\nEine alte Datenbank wird nachgezogen")

    import sqlite3

    with TempState() as (_dr, _ps, tf):
        # Die alte Tabelle von Hand anlegen.
        os.makedirs(os.path.dirname(tf.DB_PATH), exist_ok=True)
        with sqlite3.connect(tf.DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE tester_feedback ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
                "user_name TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'bug', "
                "title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', "
                "state TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '', "
                "at INTEGER NOT NULL, updated_at INTEGER)"
            )
            conn.execute(
                "INSERT INTO tester_feedback (user_id, title, at) VALUES (?, ?, ?)",
                (TESTER, "Alte Meldung von früher", 1700000000),
            )

        # Jetzt der neue Code.
        entries = tf.listing()
        check("die alte Meldung ist noch da", len(entries) == 1, str(entries))
        if entries:
            check("und hat die neuen Felder",
                  entries[0]["priority"] == "normal"
                  and entries[0]["area"] == "",
                  str(entries[0]))

        # Und Neues lässt sich weiterhin anlegen.
        check("neue Meldungen gehen weiter",
              tf.submit(TESTER, "Etwas ganz Neues")["ok"] is True)


# --------------------------------------------------------------------- #
# Der Changelog
# --------------------------------------------------------------------- #


def test_the_changelog_reads_real_commits():
    """Keine von Hand gepflegte Liste, die veraltet."""

    print("\nDer Changelog kommt aus den Commits")

    from utils import changelog

    body = changelog.recent(10)
    check("es kommen Einträge", len(body["entries"]) > 0,
          "weder Datei noch git log lieferten etwas")
    check("die Quelle ist benannt", body["source"] in ("build", "git"))

    if body["entries"]:
        entry = body["entries"][0]
        for field in ("commit", "at", "summary", "kind_label", "tone"):
            check(f"„{field}“ ist gesetzt", bool(entry.get(field) is not None))

    # Der Präfix muss übersetzt werden -- "feat" sagt einem Tester
    # nichts.
    parsed = changelog._parse_subject("feat(speedrun): drei neue Vorlagen")
    check("feat wird übersetzt", parsed["kind_label"] == "Neue Funktion",
          parsed["kind_label"])
    check("der Bereich wird übersetzt", parsed["scope"] == "Speedrun",
          parsed["scope"])
    check("die Zusammenfassung beginnt groß",
          parsed["summary"].startswith("Drei"), parsed["summary"])

    # Auch ein Commit ohne Präfix darf nicht verlorengehen.
    plain = changelog._parse_subject("irgendwas geändert")
    check("ein Commit ohne Präfix bleibt erhalten",
          plain["summary"] == "irgendwas geändert", plain["summary"])
    check("und bekommt ein neutrales Etikett",
          plain["kind_label"] == "Änderung")


def test_headings_are_not_used_as_explanations():
    """
    Die Commits hier gliedern sich mit Zeilen in Großbuchstaben.

    Als Erklärung gelesen ist das eine Überschrift ohne Inhalt.
    """

    print("\nÜberschriften sind keine Erklärung")

    from utils import changelog

    body = (
        "INVITE LINKS WERE THE MISSING PIECE\n\n"
        "Discord only registers slash commands for servers the bot was "
        "invited to with the right scope."
    )
    detail = changelog._explain({}, body)
    check("die Überschrift wird übersprungen",
          not detail.startswith("INVITE"), detail[:60])
    check("der Absatz danach wird genommen",
          detail.startswith("Discord only"), detail[:60])


# --------------------------------------------------------------------- #
# Das Dashboard
# --------------------------------------------------------------------- #


def test_the_tab_is_wired_and_gated():
    print("\nDer Reiter ist eingebunden und abgesichert")

    admin = strip_comments(read("components", "dashboard", "admin-content.tsx"))
    panel = read("components", "dashboard", "tester-panel.tsx")

    check("es gibt das Panel", bool(panel))
    check("der Reiter ist eingetragen", '"tester"' in admin)
    check("er wird gerendert", "<TesterPanel />" in admin)
    check("er verlangt tester.access",
          'tester: "tester.access"' in admin,
          "ohne Eintrag wäre er für jeden sichtbar")

    # Der entscheidende Teil: ein Tester sieht *nur* diesen Reiter.
    # Ohne die Regel käme jeder Reiter durch, der in TAB_PERMISSION
    # keinen Eintrag hat.
    check("ein Tester sieht nur seinen Reiter",
          'tabs.filter((tab) => tab.id === "tester")' in admin,
          "sonst sieht er Reiter, die ihn nichts angehen")
    check("die Regel hängt an der Berechtigung",
          'permissions.includes("tester.access")' in admin)


def test_the_proxy_passes_the_session_id():
    """
    Die user_id darf nicht aus dem Browser kommen.

    Sonst schreibt sich jeder eine fremde ID in die Anfrage und liest
    deren Meldungen.
    """

    print("\nDie Nutzer-Kennung kommt aus der Sitzung")

    proxy = strip_comments(read("app", "api", "bot", "[...path]", "route.ts"))

    check("es gibt eine Regel für den Bereich",
          'scope === "tester"' in proxy)
    check("Nichtangemeldete kommen nicht durch",
          "Not signed in" in proxy.split('scope === "tester"')[1][:400])

    # Beide Stellen einzeln prüfen.
    #
    # Ein `and` über beide Bedingungen blieb grün, als der POST-Zweig
    # entfiel: `segments[0] === "tester"` steht auch im GET-Zweig
    # darunter, und `parsed.user_id = actorId` gibt es zusätzlich beim
    # Premium-Einlösen. Ein Mutationstest hat das durchgelassen.
    post_branch = ""
    if "parsed.user_id = actorId" in proxy:
        # Der Zweig, der zum Tester-Bereich gehört -- nicht der von
        # premium/redeem.
        for chunk in proxy.split("if (segments[0] ===")[1:]:
            if chunk.lstrip().startswith('"tester") {') and "parsed" in chunk[:200]:
                post_branch = chunk[:200]
                break
    check("die ID wird bei POST überschrieben",
          "parsed.user_id = actorId" in post_branch,
          "der Tester-Zweig setzt sie nicht -- jeder meldet unter "
          "fremdem Namen")
    check("und bei GET gesetzt",
          'url.searchParams.set("user_id", actorId)' in proxy,
          "sonst liest ein Tester fremde Meldungen mit ?user_id=…")


def test_a_plain_user_never_sees_the_admin_link():
    """
    Wer keine Dashboard-Rolle hat, soll den Link gar nicht erst sehen.

    Der Link haengt an `isAdmin(...) || hasTeamRole`. `isAdmin` liest
    NEXT_PUBLIC_ADMIN_IDS -- eine Variable, die beim Build ins
    JavaScript eingebacken und im Browser fuer jeden lesbar ist. Als
    Sperre taugt sie nicht; sie darf nur *zusaetzlich* etwas
    freischalten, nie etwas oeffnen, was sonst zu waere.
    """

    print("\nOhne Rolle kein Admin-Link")

    layout = strip_comments(read("app", "dashboard", "layout.tsx"))
    utils = read("lib", "utils.ts")

    check("der Link hängt an einer Bedingung",
          'name: "Admin Panel"' in layout)
    check("und zwar an der Team-Rolle",
          "hasTeamRole" in layout,
          "sonst entscheidet allein eine im Browser lesbare Variable")

    # Der Startwert muss `false` sein: solange die Abfrage laeuft, darf
    # der Link nicht aufblitzen.
    check("er ist zu Beginn versteckt",
          "useState(false)" in layout.split("hasTeamRole")[1][:80],
          "der Link blitzt auf, bevor die Rollen geladen sind")

    # Ein leerer Eintrag darf niemanden durchlassen. "".split(",")
    # ergibt [""] -- ohne filter(Boolean) waere eine leere userId
    # gleich einem leeren Eintrag.
    check("leere Einträge werden verworfen",
          "filter(Boolean)" in utils,
          '"".split(",") ergibt [""] -- das darf nicht matchen')
    check("Leerzeichen werden entfernt",
          ".trim()" in utils,
          '"111, 123" sperrte einen echten Admin aus')


def test_the_admin_page_checks_on_the_server():
    """Der Link ist Anzeige. Die Sperre ist die Seite selbst."""

    print("\nDie Admin-Seite prüft serverseitig")

    page = strip_comments(read("app", "dashboard", "admin", "page.tsx"))

    check("die Sitzung wird serverseitig gelesen",
          "getServerSession" in page)
    check("ohne Anmeldung wird umgeleitet",
          "redirect" in page)
    check("die Team-Rolle wird geprüft",
          "fetchTeamAccess" in page,
          "sonst kommt jeder Angemeldete über die URL hinein")

    # Und die Prüfung muss wirklich umleiten, nicht nur rechnen.
    branch = page.split("fetchTeamAccess")[1][:400]
    check("ohne Rolle geht es zurück ins Dashboard",
          "redirect" in branch,
          "das Ergebnis wird berechnet und dann ignoriert")

    # fetchTeamAccess liest ADMIN_IDS serverseitig -- nicht die
    # NEXT_PUBLIC-Variante, die im Browser steht.
    auth = read("lib", "guild-auth.ts")
    check("serverseitig gilt ADMIN_IDS",
          "process.env.ADMIN_IDS" in auth,
          "eine im Browser lesbare Variable als Sperre wäre keine")


def test_nobody_reads_a_stranger_access():
    """
    `/team/me/{user_id}` darf nur den eigenen Zugang liefern.

    Die ID steht im Pfad und kommt aus dem Browser. Vorher liess der
    Proxy jede durch: mit /team/me/<fremde-id> las jeder Angemeldete,
    welche Dashboard-Rollen ein anderer hat.
    """

    print("\nNiemand liest den Zugang eines Fremden")

    proxy = strip_comments(read("app", "api", "bot", "[...path]", "route.ts"))
    block = proxy.split('scope === "team"')[1][:1200]

    check("es gibt eine Regel für /me", 'resource === "me"' in block)

    branch = block.split('resource === "me"')[1][:400]
    check("die ID im Pfad wird gelesen", "rest[1]" in branch)

    # Die Bedingung selbst ansehen, nicht nur die Wörter drumherum.
    #
    # `if (false) { ... }` ließ alles stehen -- Vergleich, deny(403),
    # die ganze Zeile -- und trotzdem kam jede fremde ID durch. Ein
    # Mutationstest hat das durchgelassen.
    guard = re.search(r"if \(([^)]*wanted[^)]*)\)", branch)
    check("es gibt eine echte Bedingung", guard is not None, branch[:120])
    if guard is not None:
        condition = guard.group(1)
        check("sie vergleicht mit der Sitzung",
              "session.user.id" in condition,
              f"Bedingung: {condition}")
        check("und ist nicht konstant",
              "false" not in condition.lower()
              and "true" not in condition.lower(),
              f"Bedingung: {condition}")
    check("abgewiesen wird mit 403",
          "deny(403" in branch,
          "der Vergleich wird berechnet und ignoriert")


def test_the_removed_commands_are_gone():
    """`ticket setup` und `verification setup` sollten weg sein."""

    print("\nDie beiden Setup-Befehle sind entfernt")

    ticket = open(os.path.join(BOT, "cogs", "commands", "ticket.py"),
                  encoding="utf-8").read()
    verify = open(os.path.join(BOT, "cogs", "commands", "verification.py"),
                  encoding="utf-8").read()

    # Kommentare strippen: beide Dateien erklären an der Stelle, warum
    # der Befehl weg ist -- und würden sich sonst selbst finden.
    ticket_code = re.sub(r"^\s*#.*$", "", ticket, flags=re.M)
    verify_code = re.sub(r"^\s*#.*$", "", verify, flags=re.M)

    check("ticket setup ist weg",
          'name="setup"' not in ticket_code,
          "der Befehl ist noch registriert")
    check("verification setup ist weg",
          'name ="setup"' not in verify_code and 'name="setup"' not in verify_code,
          "der Befehl ist noch registriert")

    # Die übrigen Befehle der Gruppen müssen bleiben.
    check("ticket close bleibt", 'name="close"' in ticket_code)
    check("verification status bleibt", 'name ="status"' in verify_code)


def main():
    test_the_role_exists_and_is_narrow()
    test_the_role_grants_premium_and_taking_it_removes_premium()
    test_the_bypass_does_not_leak_to_others()
    test_a_real_key_still_wins()
    test_a_broken_role_lookup_does_not_grant_premium()
    test_the_routes_check_the_role_themselves()
    test_a_tester_sees_only_their_own_reports()
    test_a_tester_cannot_open_a_stranger_report()
    test_owners_see_everything()
    test_only_owners_change_the_state()
    test_a_report_needs_a_title()
    test_the_history_is_append_only()
    test_duplicates_are_flagged_not_blocked()
    test_votes_count_once_per_person()
    test_open_and_urgent_come_first()
    test_a_duplicate_cannot_point_at_itself()
    test_an_old_database_is_upgraded()
    test_the_changelog_reads_real_commits()
    test_headings_are_not_used_as_explanations()
    test_the_tab_is_wired_and_gated()
    test_the_proxy_passes_the_session_id()
    test_a_plain_user_never_sees_the_admin_link()
    test_the_admin_page_checks_on_the_server()
    test_nobody_reads_a_stranger_access()
    test_the_removed_commands_are_gone()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
