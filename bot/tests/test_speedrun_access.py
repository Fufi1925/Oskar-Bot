#!/usr/bin/env python3
"""
Die Code-Sperre vor dem Speedrun-Reiter.

Freigeschaltet wird ein **Server**, nicht ein Konto. Drei Zustaende:
gesperrt (nichts eingegeben), frei (Code eingegeben), gebannt (ein
Admin hat zugemacht -- kein Code hilft mehr).

Worauf es hier ankommt, und warum jede Pruefung existiert:

  * Die Sperre muss **im Bot** greifen, nicht nur im Browser. Ein
    Overlay ist eine Tuer ohne Wand: /start ist eine HTTP-Route, und
    curl fragt nicht nach einem Overlay.
  * Ein Bann muss ueber dem Code stehen. Sonst befreit sich ein
    gebannter Server mit der richtigen Eingabe selbst.
  * Entziehen und Sperren sind verschieden: das eine heisst "neu
    eingeben", das andere "nie wieder".
  * Der Verlauf muss einen Entzug ueberleben -- sonst kann hinterher
    niemand mehr sagen, wer den Server damals freigeschaltet hat.

Geprueft wird gegen eine echte SQLite-Datei in einem Temp-Ordner, nicht
gegen Attrappen: die Zustandslogik steckt zum Teil in den SQL-Zeilen,
und eine Attrappe wuerde nur bestaetigen, was der Test selbst erfindet.

Run:  python3 tests/test_speedrun_access.py
"""

import asyncio
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


class TempDB:
    """Jeder Test auf einer frischen Datei."""

    def __init__(self):
        self.dir = None
        self.old = None

    def __enter__(self):
        from utils import speedrun_access as sa

        self.dir = tempfile.mkdtemp()
        self.old = sa.DB_PATH
        sa.DB_PATH = os.path.join(self.dir, "access.db")
        return sa

    def __exit__(self, *_exc):
        from utils import speedrun_access as sa

        sa.DB_PATH = self.old
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


GUILD = 1520714989860814992


# --------------------------------------------------------------------- #
# Der Code selbst
# --------------------------------------------------------------------- #


def test_the_code_is_forgiving_about_typing():
    """
    Der Code darf nicht an Kleinigkeiten scheitern.

    Er wird von einem Bildschirm abgetippt. Ob jemand
    grossschreibt oder zwei Leerzeichen setzt, sagt nichts darueber,
    ob er ihn kennt -- aber es kostet einen Support-Fall.

    Der Nutzer hat ihn als »Univertiy beta v1« aufgeschrieben, mit
    vertauschtem "si". Beide Schreibweisen gelten: sonst sperrt genau
    dieser Vertipper die Leute aus, fuer die die Beta gedacht ist, und
    auf dem Bildschirm stuende nur "falscher Code".
    """

    print("\nDer Code verzeiht Tippfehler")

    from utils import speedrun_access as sa

    for good in (
        "University beta v1",
        "university beta v1",
        "UNIVERSITY BETA V1",
        "  University   beta  v1  ",
        "Univertiy beta v1",
        "univertiy BETA v1",
    ):
        check(f"„{good.strip()}“ gilt", sa.code_is_valid(good))

    for bad in (
        "",
        "   ",
        "University beta",
        "University beta v2",
        "Universitybetav1",
        "beta v1",
        "University alpha v1",
    ):
        check(f"„{bad.strip() or '(leer)'}“ gilt nicht",
              not sa.code_is_valid(bad),
              "ein falscher Code kommt durch")


def test_the_code_is_not_stored_in_the_clear():
    """In einer Protokolltabelle hat ein Geheimnis nichts verloren."""

    print("\nDer Code liegt nicht im Klartext")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")

        blob = open(sa.DB_PATH, "rb").read().lower()
        check("der Klartext steht nicht in der Datei",
              b"university beta v1" not in blob,
              "der Code liegt lesbar in der Datenbank")


# --------------------------------------------------------------------- #
# Freischalten
# --------------------------------------------------------------------- #


def test_a_server_starts_locked():
    print("\nOhne Code ist zu")

    with TempDB() as sa:
        state = sa.state(GUILD)
        check("nicht freigeschaltet", state["unlocked"] is False)
        check("nicht gebannt", state["banned"] is False)
        check("is_unlocked sagt nein", sa.is_unlocked(GUILD) is False)


def test_the_right_code_unlocks_exactly_one_server():
    """
    Freigeschaltet wird ein Server, nicht das Konto.

    Sonst wandert die Freischaltung mit dem Nutzer auf jeden Server,
    auf dem er Rechte hat -- und der Speedrun baut einen konkreten
    Server um.
    """

    print("\nDer richtige Code öffnet genau einen Server")

    with TempDB() as sa:
        other = 1530378233579704370

        result = sa.unlock(GUILD, "University beta v1", "123")
        check("die Freischaltung klappt", result["ok"] is True, str(result))
        check("der Server ist offen", sa.is_unlocked(GUILD) is True)
        check("der andere Server bleibt zu",
              sa.is_unlocked(other) is False,
              "die Freischaltung gilt für alle Server -- sie hängt am Konto")

        state = sa.state(GUILD)
        check("es steht drin, wer es war", state["unlocked_by"] == "123")
        check("und wann", bool(state["unlocked_at"]))


def test_a_wrong_code_changes_nothing():
    print("\nEin falscher Code ändert nichts")

    with TempDB() as sa:
        result = sa.unlock(GUILD, "falsch", "123")
        check("die Freischaltung wird abgelehnt", result["ok"] is False)
        check("mit einer Begründung", bool(result["reason"]))
        check("der Server bleibt zu", sa.is_unlocked(GUILD) is False)

        events = sa.history(GUILD)
        check("der Fehlversuch steht im Verlauf",
              any(e["event"] == "denied" for e in events),
              "ein Server mit vierzig Fehlversuchen fiele sonst nicht auf")


def test_unlocking_twice_is_harmless():
    print("\nZweimal freischalten schadet nicht")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        second = sa.unlock(GUILD, "University beta v1", "456")
        check("der zweite Versuch geht durch", second["ok"] is True)
        check("und meldet, dass es schon offen war",
              second.get("already") is True)
        check("der Server ist offen", sa.is_unlocked(GUILD) is True)


# --------------------------------------------------------------------- #
# Entziehen und Sperren -- der Unterschied
# --------------------------------------------------------------------- #


def test_revoking_asks_for_the_code_again():
    """Entziehen heißt: neu eingeben, dann geht es wieder."""

    print("\nEntziehen verlangt den Code erneut")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        check("vorher offen", sa.is_unlocked(GUILD) is True)

        check("der Entzug greift", sa.revoke(GUILD, "999") is True)
        check("danach zu", sa.is_unlocked(GUILD) is False)
        check("aber nicht gebannt", sa.state(GUILD)["banned"] is False)

        again = sa.unlock(GUILD, "University beta v1", "123")
        check("mit dem Code geht es wieder", again["ok"] is True)
        check("und der Server ist offen", sa.is_unlocked(GUILD) is True)


def test_a_ban_cannot_be_undone_with_the_code():
    """
    Der Kern des Ganzen.

    Ein Bann, den der richtige Code aufhebt, ist kein Bann. Genau
    dieser Fehler ist leicht zu bauen: erst den Code prüfen, dann den
    Zustand -- und schon befreit sich ein gesperrter Server selbst.
    """

    print("\nEin Bann hält auch dem richtigen Code stand")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        sa.ban(GUILD, "999", "Missbrauch")

        check("der Server ist gebannt", sa.state(GUILD)["banned"] is True)
        check("und nicht mehr offen", sa.is_unlocked(GUILD) is False,
              "die alte Freischaltung gilt trotz Bann weiter")

        result = sa.unlock(GUILD, "University beta v1", "123")
        check("der richtige Code wird abgelehnt", result["ok"] is False,
              "ein gebannter Server befreit sich selbst")
        check("der Server bleibt zu", sa.is_unlocked(GUILD) is False)

        state = sa.state(GUILD)
        check("die Begründung steht dabei",
              state["ban_reason"] == "Missbrauch", state["ban_reason"])


def test_revoking_a_banned_server_keeps_the_ban():
    """Wer einen gebannten Server entzieht, will ihn nicht entsperren."""

    print("\nEntziehen hebt keinen Bann auf")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        sa.ban(GUILD, "999", "Grund")
        sa.revoke(GUILD, "999")

        check("der Bann steht noch", sa.state(GUILD)["banned"] is True,
              "der Entzug hat den Server nebenbei entsperrt")
        check("und der Code hilft nicht",
              sa.unlock(GUILD, "University beta v1", "123")["ok"] is False)


def test_unbanning_does_not_restore_access():
    """
    Entsperren gibt den Zugang nicht zurück.

    Eine aufgehobene Sperre ist keine Freischaltung -- der Code muss
    neu eingegeben werden. Alles andere wäre überraschend: man will
    jemandem die Möglichkeit zurückgeben, nicht den Zustand von vorher.
    """

    print("\nEntsperren ist keine Freischaltung")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        sa.ban(GUILD, "999", "Grund")
        check("der Bann wird aufgehoben", sa.unban(GUILD, "999") is True)

        state = sa.state(GUILD)
        check("nicht mehr gebannt", state["banned"] is False)
        check("aber auch nicht offen", state["unlocked"] is False,
              "die alte Freischaltung ist wieder da, ohne dass jemand tippte")

        check("mit dem Code geht es wieder",
              sa.unlock(GUILD, "University beta v1", "123")["ok"] is True)


def test_unbanning_something_that_is_not_banned():
    print("\nEntsperren ohne Bann meldet das")

    with TempDB() as sa:
        check("ein unbekannter Server", sa.unban(GUILD, "999") is False)
        sa.unlock(GUILD, "University beta v1", "123")
        check("ein freier Server", sa.unban(GUILD, "999") is False)
        check("und bleibt dabei offen", sa.is_unlocked(GUILD) is True,
              "das Entsperren hat die Freischaltung gelöscht")


# --------------------------------------------------------------------- #
# Verlauf und Zahlen
# --------------------------------------------------------------------- #


def test_the_history_survives_a_revoke():
    """Sonst kann niemand mehr sagen, wer den Server freigeschaltet hat."""

    print("\nDer Verlauf überlebt einen Entzug")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        sa.note_run(GUILD, "123")
        sa.revoke(GUILD, "999")

        events = sa.history(GUILD)
        kinds = [e["event"] for e in events]
        for wanted in ("unlocked", "run_started", "revoked"):
            check(f"„{wanted}“ steht noch im Verlauf", wanted in kinds,
                  str(kinds))

        unlocked = next(e for e in events if e["event"] == "unlocked")
        check("mit dem Nutzer, der es war", unlocked["user_id"] == "123")
        revoked = next(e for e in events if e["event"] == "revoked")
        check("und dem Admin, der entzogen hat", revoked["actor_id"] == "999")


def test_runs_are_counted():
    print("\nLäufe werden gezählt")

    with TempDB() as sa:
        sa.unlock(GUILD, "University beta v1", "123")
        for _ in range(3):
            sa.note_run(GUILD, "123")

        state = sa.state(GUILD)
        check("drei Läufe", state["runs"] == 3, str(state["runs"]))
        check("mit einem Zeitpunkt", bool(state["last_run_at"]))


def test_the_overview_lists_everything():
    print("\nDie Übersicht zeigt alle Server")

    with TempDB() as sa:
        sa.unlock(1111111111111111111, "University beta v1", "a")
        sa.unlock(2222222222222222222, "University beta v1", "b")
        sa.ban(3333333333333333333, "999", "weg")

        rows = sa.list_guilds()
        check("drei Einträge", len(rows) == 3, str(len(rows)))

        by_id = {row["guild_id"]: row for row in rows}
        check("der freie ist frei",
              by_id["1111111111111111111"]["unlocked"] is True)
        check("der gebannte ist gebannt",
              by_id["3333333333333333333"]["banned"] is True)
        check("und nicht gleichzeitig frei",
              by_id["3333333333333333333"]["unlocked"] is False)

        stats = sa.stats()
        check("zwei freigeschaltet", stats["unlocked"] == 2, str(stats))
        check("einer gebannt", stats["banned"] == 1, str(stats))


# --------------------------------------------------------------------- #
# Die Routen -- hier zählt es wirklich
# --------------------------------------------------------------------- #


def test_the_lock_is_enforced_by_the_bot():
    """
    Die Sperre muss serverseitig greifen.

    Ein Overlay im Browser hält niemanden auf: /start ist eine
    HTTP-Route. Wer sie mit curl aufruft, sieht kein Overlay -- und
    ein Speedrun legt Dutzende Rollen und Kanäle an.
    """

    print("\nDie Sperre greift im Bot, nicht nur im Browser")

    from fastapi import HTTPException

    from api.routes import speedrun

    with TempDB() as sa:
        speedrun.access = sa

        class FakeGuild:
            id = GUILD
            name = "Testserver"

        class FakeBot:
            loop = None

            def get_guild(self, _id):
                return FakeGuild()

        # 1. Zu: der Start muss abprallen.
        try:
            asyncio.run(
                speedrun.start(
                    GUILD,
                    {"template": "community", "user_id": "123"},
                    FakeBot(),
                )
            )
            check("ein gesperrter Server kann nicht starten", False,
                  "der Start lief trotz Sperre durch")
        except HTTPException as exc:
            check("ein gesperrter Server kann nicht starten",
                  exc.status_code == 403, f"HTTP {exc.status_code}")

        # 2. Gebannt: ebenfalls, und mit eigener Meldung.
        sa.ban(GUILD, "999", "Missbrauch")
        try:
            asyncio.run(
                speedrun.start(
                    GUILD,
                    {"template": "community", "user_id": "123"},
                    FakeBot(),
                )
            )
            check("ein gebannter Server kann nicht starten", False,
                  "der Start lief trotz Bann durch")
        except HTTPException as exc:
            check("ein gebannter Server kann nicht starten",
                  exc.status_code == 403, f"HTTP {exc.status_code}")
            check("die Meldung nennt die Sperre",
                  "gesperrt" in str(exc.detail).lower(), str(exc.detail))


def test_the_unlock_route_refuses_a_banned_server():
    print("\nDie Freischalt-Route lehnt einen gebannten Server ab")

    from fastapi import HTTPException

    from api.routes import speedrun

    with TempDB() as sa:
        speedrun.access = sa
        sa.ban(GUILD, "999", "Grund")

        try:
            asyncio.run(
                speedrun.access_unlock(
                    GUILD, {"code": "University beta v1", "user_id": "123"}
                )
            )
            check("der richtige Code wird abgelehnt", False,
                  "ein gebannter Server hat sich selbst freigeschaltet")
        except HTTPException as exc:
            check("der richtige Code wird abgelehnt", exc.status_code == 403)


def test_the_access_route_never_leaks_the_code():
    """Die Antwort darf keine Vorlage zum Raten sein."""

    print("\nDie Zustands-Route verrät den Code nicht")

    from api.routes import speedrun

    with TempDB() as sa:
        speedrun.access = sa
        sa.unlock(GUILD, "University beta v1", "123")

        body = asyncio.run(speedrun.access_state(GUILD))
        text = repr(body).lower()
        check("kein Code in der Antwort",
              "university beta" not in text and "univertiy" not in text,
              str(body))
        check("kein Hash in der Antwort", "code_hash" not in text, str(body))
        check("aber der Zustand steht drin", body["unlocked"] is True)


def test_revoking_stops_a_running_speedrun():
    """
    Wer den Zugang nimmt, will keinen weiterlaufenden Umbau.

    Ohne das arbeitet der Bot nach dem Entzug noch Minuten am Server
    weiter -- er postet Panels und vergibt Rollen für jemanden, dem
    gerade der Zugang entzogen wurde.
    """

    print("\nEin Entzug bricht den laufenden Speedrun ab")

    import time

    from api.routes import speedrun

    with TempDB() as sa:
        speedrun.access = sa
        original_call = speedrun._call_template

        async def fake_call(*_a, **_k):
            return 200, {"cancelled": True}

        speedrun._call_template = fake_call
        try:
            sa.unlock(GUILD, "University beta v1", "123")

            job = {
                "state": "running", "lines": [], "report": None,
                "started": time.time(), "finished": 0.0, "error": "",
                "run_id": "lauf-1", "cancelled": False,
                "step": 0, "total": 0, "options": {},
            }
            speedrun._MAIN_JOBS[GUILD] = job

            async def run():
                async def sleeper():
                    await asyncio.sleep(30)

                handle = speedrun._spawn(None, sleeper(), GUILD)
                await asyncio.sleep(0.05)
                answer = await speedrun.admin_revoke(
                    GUILD, {"actor_id": "999"}, None
                )
                await asyncio.sleep(0.05)
                return answer, handle.cancelled()

            answer, cancelled = asyncio.run(run())

            check("der Entzug wird gemeldet", answer["revoked"] is True)
            check("der Lauf gilt als abgebrochen",
                  answer["run_cancelled"] is True, str(answer))
            check("der Job steht auf failed", job["state"] == "failed",
                  job["state"])
            check("die Marke ist gesetzt", job.get("cancelled") is True)
            check("der Task wurde wirklich abgebrochen", cancelled,
                  "die Einrichtung läuft nach dem Entzug weiter")
            check("der Server ist zu", sa.is_unlocked(GUILD) is False)
        finally:
            speedrun._call_template = original_call
            speedrun._MAIN_JOBS.clear()
            speedrun._MAIN_TASKS.clear()


def test_banning_also_stops_a_running_speedrun():
    print("\nEin Bann bricht den laufenden Speedrun ab")

    import time

    from api.routes import speedrun

    with TempDB() as sa:
        speedrun.access = sa
        original_call = speedrun._call_template

        async def fake_call(*_a, **_k):
            return 200, {"cancelled": True}

        speedrun._call_template = fake_call
        try:
            sa.unlock(GUILD, "University beta v1", "123")
            job = {
                "state": "waiting", "lines": [], "report": None,
                "started": time.time(), "finished": 0.0, "error": "",
                "run_id": "lauf-1", "cancelled": False,
                "step": 0, "total": 0, "options": {},
            }
            speedrun._MAIN_JOBS[GUILD] = job

            answer = asyncio.run(
                speedrun.admin_ban(
                    GUILD, {"actor_id": "999", "reason": "Missbrauch"}, None
                )
            )

            check("der Bann greift", answer["banned"] is True)
            check("der Lauf wurde abgebrochen",
                  answer["run_cancelled"] is True, str(answer))
            check("der Server ist gebannt", sa.state(GUILD)["banned"] is True)
        finally:
            speedrun._call_template = original_call
            speedrun._MAIN_JOBS.clear()
            speedrun._MAIN_TASKS.clear()


def test_the_admin_routes_are_not_guild_ids():
    """
    /admin/guilds darf nicht als guild_id gelesen werden.

    FastAPI probiert die Routen der Reihe nach. Stünde
    ``/{guild_id}/access`` vor ``/admin/guilds``, landete der Aufruf
    beim falschen Handler und käme als 422 zurück -- das Panel bliebe
    leer, ohne dass jemand sähe, warum.
    """

    print("\nDie Admin-Routen kollidieren nicht mit guild_id")

    from fastapi.testclient import TestClient

    from api.server import create_app

    client = TestClient(create_app())
    for path in ("/api/v1/speedrun/admin/guilds",
                 "/api/v1/speedrun/admin/history"):
        response = client.get(path)
        check(f"{path.split('/v1')[1]} wird nicht als ID gelesen",
              response.status_code != 422,
              f"HTTP {response.status_code} -- als guild_id geparst")


def main():
    test_the_code_is_forgiving_about_typing()
    test_the_code_is_not_stored_in_the_clear()
    test_a_server_starts_locked()
    test_the_right_code_unlocks_exactly_one_server()
    test_a_wrong_code_changes_nothing()
    test_unlocking_twice_is_harmless()
    test_revoking_asks_for_the_code_again()
    test_a_ban_cannot_be_undone_with_the_code()
    test_revoking_a_banned_server_keeps_the_ban()
    test_unbanning_does_not_restore_access()
    test_unbanning_something_that_is_not_banned()
    test_the_history_survives_a_revoke()
    test_runs_are_counted()
    test_the_overview_lists_everything()
    test_the_lock_is_enforced_by_the_bot()
    test_the_unlock_route_refuses_a_banned_server()
    test_the_access_route_never_leaks_the_code()
    test_revoking_stops_a_running_speedrun()
    test_banning_also_stops_a_running_speedrun()
    test_the_admin_routes_are_not_guild_ids()

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
