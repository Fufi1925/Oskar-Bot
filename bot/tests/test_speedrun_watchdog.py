#!/usr/bin/env python3
"""
Der Wächter: der Bot richtet selbst ein, ohne den Browser.

Was hier festgenagelt wird, ist der schwerste Fehler, den dieser Reiter
hatte. Früher stieß das Dashboard die zweite Hälfte an: es fragte den
Fortschritt ab, sah „Bau fertig“ und rief ``/finish``. Damit hing die
halbe Einrichtung am offenen Browser-Tab.

Im Betrieb heißt das: Nutzer klickt Start, der Bau läuft über eine
Minute, der Tab geht zu (Handy sperrt, Netz weg, Fenster geschlossen) --
und niemand ruft ``/finish``. Ergebnis: Rollen und Kanäle stehen, aber
Verify, Tickets, Logs, Anti-Nuke, Level und Begrüßung fehlen. Ohne jede
Meldung, und ein zweiter Anlauf hätte alles doppelt angelegt.

Geprüft wird gegen echte Abläufe, nicht gegen Textsuche: der Wächter
läuft wirklich, wartet wirklich auf das Ende und übergibt wirklich.

Run:  python3 tests/test_speedrun_watchdog.py
"""

import asyncio
import os
import sys
import time

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


# --------------------------------------------------------------------- #
# Attrappen
# --------------------------------------------------------------------- #


class FakeGuild:
    def __init__(self, guild_id=1520714989860814992):
        self.id = guild_id
        self.name = "Testserver"


class FakeBot:
    """Kein laufender Loop -- die Route fällt dann auf ensure_future zurück."""

    loop = None


def fresh_job(**over):
    job = {
        "state": "waiting",
        "lines": [],
        "report": None,
        "started": time.time(),
        "finished": 0.0,
        "error": "",
        "run_id": "lauf-1",
        "cancelled": False,
        "step": 0,
        "total": 0,
        "options": {},
    }
    job.update(over)
    return job


class Handover:
    """Merkt sich, ob und womit die Einrichtung gestartet wurde."""

    def __init__(self, delay=0.0):
        self.calls: list[dict] = []
        self.delay = delay

    async def __call__(self, bot, guild, payload, options=None, log=None,
                       on_step=None):
        self.calls.append({"payload": payload, "options": dict(options or {})})
        if self.delay:
            await asyncio.sleep(self.delay)

        class Report:
            steps: list = []
            failed: list = []

            def as_dict(self):
                return {"steps": [], "ok": True}

        return Report()


def install(speedrun, states, handover=None):
    """Der Template-Bot antwortet der Reihe nach mit ``states``."""

    seen = {"n": 0}

    async def fake_call(method, path, *, payload=None, timeout=15):
        if path.endswith("/cancel"):
            return 200, {"cancelled": True}
        index = min(seen["n"], len(states) - 1)
        seen["n"] += 1
        return 200, states[index]

    speedrun._call_template = fake_call
    if handover is not None:
        speedrun.handover.run_handover = handover
    return seen


BUILD_RESULT = {
    "roles": {"verified": "1"},
    "channels": {"verify": "2"},
}


# --------------------------------------------------------------------- #
# Die Prüfungen
# --------------------------------------------------------------------- #


def test_the_watcher_hands_over_without_a_browser():
    """Der Kern: Bau fertig -> der Bot richtet von selbst ein."""

    print("\nDer Bot übernimmt ohne den Browser")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        handover = Handover()
        # Erst zwei Mal „läuft noch“, dann fertig.
        install(
            speedrun,
            [
                {"state": "running", "run_id": "lauf-1"},
                {"state": "running", "run_id": "lauf-1"},
                {"state": "done", "run_id": "lauf-1", "result": BUILD_RESULT},
            ],
            handover,
        )

        job = fresh_job()
        guild = FakeGuild()

        async def run():
            await speedrun._watch_build(
                FakeBot(), guild, job, {"verify": True}, "lauf-1"
            )
            # Der Wächter startet die Einrichtung als eigenen Task.
            for _ in range(50):
                if handover.calls:
                    break
                await asyncio.sleep(0.02)

        asyncio.run(run())

        check("die Einrichtung wurde gestartet", len(handover.calls) == 1,
              f"{len(handover.calls)} Aufrufe -- der Browser war nie beteiligt")
        if handover.calls:
            check("sie bekam die Landkarte des Baus",
                  handover.calls[0]["payload"] == BUILD_RESULT,
                  str(handover.calls[0]["payload"]))
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_the_chosen_steps_survive_to_the_handover():
    """
    Die Auswahl aus dem Reiter muss ankommen.

    Früher kamen die Schritte erst mit ``/finish`` aus dem Browser. Da
    der nicht mehr gefragt wird, müssen sie beim Start mitgehen --
    sonst richtet der Bot stur den Standard ein und jedes Abwählen im
    Umfang wäre wirkungslos.
    """

    print("\nDie abgewählten Schritte bleiben abgewählt")

    from api.routes import speedrun
    from utils import speedrun_handover as ho

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        handover = Handover()
        install(
            speedrun,
            [{"state": "done", "run_id": "lauf-1", "result": BUILD_RESULT}],
            handover,
        )

        # Nur „verify“ an, alles andere aus. Einzeln aufzuzählen wäre
        # brüchig: kommt ein Schritt dazu, prüfte der Test ihn nie.
        wanted = {key: key == "verify" for key in ho.STEPS}
        job = fresh_job(options=wanted)

        async def run():
            await speedrun._watch_build(FakeBot(), FakeGuild(), job, wanted, "lauf-1")
            for _ in range(50):
                if handover.calls:
                    break
                await asyncio.sleep(0.02)

        asyncio.run(run())

        check("die Einrichtung lief", bool(handover.calls))
        if handover.calls:
            passed = handover.calls[0]["options"]
            check("verify ist an", passed.get("verify") is True, str(passed))
            others = [k for k, v in passed.items() if k != "verify" and v]
            check("nichts sonst wurde eingerichtet", not others,
                  f"trotz Abwahl gelaufen: {others}")
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_a_cancelled_run_stays_cancelled():
    """
    Abbrechen muss den Lauf wirklich beenden.

    Vorher setzte die Route nur den Zustand auf „failed“ -- die
    Einrichtung lief seelenruhig weiter und schrieb am Ende „done“
    darüber. Auf dem Bildschirm sprang der Reiter von „Abgebrochen“
    zurück auf „Fertig“, während der halbe Server fehlte.
    """

    print("\nAbgebrochen bleibt abgebrochen")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template

    try:
        # Eine Einrichtung, die zwei Sekunden braucht.
        handover = Handover(delay=2.0)
        install(speedrun, [{"state": "done", "run_id": "lauf-1"}], handover)

        job = fresh_job(state="running")
        speedrun._MAIN_JOBS[1] = job

        async def run():
            speedrun._spawn(
                FakeBot(),
                speedrun._run_main_phase(None, FakeGuild(), job, {}, {}),
                1,
            )
            await asyncio.sleep(0.2)
            await speedrun.cancel(1)
            straight_after = job["state"]

            # Lange genug warten, dass die Einrichtung fertig geworden
            # wäre, hätte der Abbruch sie nicht gestoppt.
            await asyncio.sleep(2.4)
            return straight_after, job["state"]

        straight_after, later = asyncio.run(run())

        check("direkt nach dem Klick abgebrochen", straight_after == "failed",
              straight_after)
        check("und zwei Sekunden später immer noch", later == "failed",
              f"sprang auf {later!r} zurück -- der Nutzer sieht „Fertig“, "
              "obwohl er abgebrochen hat")
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun._MAIN_JOBS.clear()


def test_cancel_does_both_things_it_promises():
    """
    ``cancel()`` muss beides tun: die Marke setzen *und* die Tasks stoppen.

    Die beiden Sicherungen decken einander im Ergebnis ab — fällt eine
    weg, sieht der Lauf trotzdem abgebrochen aus. Ein Test, der nur auf
    den Endzustand schaut, ist damit blind; ein Mutationstest hat genau
    das gezeigt. Deshalb wird hier nicht das Ergebnis geprüft, sondern
    ob die Route wirklich beide Handgriffe ausführt.

    Warum beide nötig sind: die Marke allein lässt die Einrichtung bis
    zum Ende weiterlaufen (Panels werden gepostet, Rollen vergeben) und
    korrigiert erst danach den Zustand. Der Task-Abbruch allein greift
    nicht beim Wächter, der gerade zwischen zwei Nachfragen schläft.
    """

    print("\nAbbrechen setzt die Marke UND stoppt die Tasks")

    from api.routes import speedrun

    original_call = speedrun._call_template

    try:
        install(speedrun, [{"state": "running", "run_id": "lauf-1"}])

        job = fresh_job(state="running")
        speedrun._MAIN_JOBS[9] = job

        async def run():
            # Ein Task, der lange läuft -- an ihm wird sichtbar, ob der
            # Abbruch ihn wirklich erreicht.
            async def sleeper():
                await asyncio.sleep(30)

            handle = speedrun._spawn(FakeBot(), sleeper(), 9)
            await asyncio.sleep(0.05)

            await speedrun.cancel(9)
            await asyncio.sleep(0.05)

            # Noch *innerhalb* der Schleife messen.
            #
            # Nach `asyncio.run()` ist jeder offene Task abgebrochen --
            # das besorgt das Schließen der Schleife, nicht der Code,
            # der hier geprüft werden soll. Von außen gemessen war die
            # Prüfung deshalb wertlos: sie blieb grün, als der Abbruch
            # ersatzlos entfiel.
            return {
                "cancelled": handle.cancelled(),
                "left": bool(speedrun._MAIN_TASKS.get(9)),
            }

        seen = asyncio.run(run())

        check("die Marke wurde gesetzt", job.get("cancelled") is True,
              "ohne sie schreibt die Einrichtung am Ende »Fertig« darüber")
        check("der laufende Task wurde abgebrochen", seen["cancelled"],
              "ohne das läuft die Einrichtung nach dem Abbruch weiter "
              "und postet Panels in einen Server, den niemand mehr will")
        check("die Task-Liste ist leer", not seen["left"])
    finally:
        speedrun._call_template = original_call
        speedrun._MAIN_JOBS.clear()
        speedrun._MAIN_TASKS.clear()


def test_cancelling_stops_the_watcher_before_it_hands_over():
    """Ein Abbruch während des Baus darf keine Einrichtung mehr auslösen."""

    print("\nEin Abbruch während des Baus verhindert die Übergabe")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.05

    try:
        handover = Handover()
        install(
            speedrun,
            [
                {"state": "running", "run_id": "lauf-1"},
                {"state": "done", "run_id": "lauf-1", "result": BUILD_RESULT},
            ],
            handover,
        )

        job = fresh_job()
        speedrun._MAIN_JOBS[1] = job

        async def run():
            speedrun._spawn(
                FakeBot(),
                speedrun._watch_build(FakeBot(), FakeGuild(1), job, {}, "lauf-1"),
                1,
            )
            await asyncio.sleep(0.02)
            await speedrun.cancel(1)
            await asyncio.sleep(0.4)

        asyncio.run(run())

        check("es wurde nichts eingerichtet", not handover.calls,
              f"{len(handover.calls)} Aufruf(e) trotz Abbruch")
        check("der Lauf steht auf abgebrochen", job["state"] == "failed",
              job["state"])
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_a_failed_build_sets_up_nothing():
    """Auf einen gescheiterten Bau darf keine Einrichtung folgen.

    Geprüft wird auch die *Meldung*. Ein gescheiterter Bau und ein
    abgelaufener Job sind zwei verschiedene Lagen mit zwei verschiedenen
    Handgriffen; sie unter derselben Zeile zusammenzufassen kostet den
    Leser eine Runde Raten. Ohne diese Prüfung blieb der Test grün,
    wenn der Fehlerzweig ganz entfiel und der Auffang-Zweig übernahm.
    """

    print("\nEin gescheiterter Bau richtet nichts ein")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        handover = Handover()
        install(speedrun, [{"state": "failed", "run_id": "lauf-1",
                            "error": "Keine Rechte"}], handover)

        job = fresh_job()
        asyncio.run(
            speedrun._watch_build(FakeBot(), FakeGuild(), job, {}, "lauf-1")
        )

        check("nichts wurde eingerichtet", not handover.calls)
        check("der Lauf gilt als gescheitert", job["state"] == "failed",
              job["state"])
        # Die Ursache muss beim Namen genannt werden.
        check("die Meldung nennt den gescheiterten Bau",
              "gescheitert" in job["error"].lower()
              or "keine rechte" in job["error"].lower(),
              f"Meldung: {job['error']!r} — das klingt nach einem "
              "abgelaufenen Job, nicht nach einem Absturz")
        last = job["lines"][-1]["text"].lower() if job["lines"] else ""
        check("und die Zeile im Terminal ebenso",
              "gescheitert" in last,
              f"letzte Zeile: {last!r}")
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_each_cancel_guard_works_on_its_own():
    """
    Der Abbruch ist dreifach abgesichert — jede Sicherung einzeln prüfen.

    Beim Abbrechen passieren drei Dinge: die Marke ``cancelled`` wird
    gesetzt, die laufenden Tasks werden abgebrochen, und der
    finally-Zweig der Einrichtung achtet auf die Marke. Das ist
    Absicht — aber es macht einen Test, der nur ``cancel()`` aufruft,
    blind: fällt eine der drei weg, fangen die anderen beiden es auf,
    und der Test bleibt grün. Genau das hat ein Mutationstest gezeigt.

    Deshalb hier jede Sicherung für sich, ohne die anderen.
    """

    print("\nJede Abbruch-Sicherung wirkt für sich allein")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        # -- Sicherung 1: die Marke allein --------------------------- #
        # Die Einrichtung läuft ganz normal durch, niemand bricht einen
        # Task ab. Nur die Marke steht. Der finally-Zweig muss daraus
        # „abgebrochen“ machen, statt „fertig“ darüberzuschreiben.
        speedrun.handover.run_handover = Handover()
        install(speedrun, [{"state": "done", "run_id": "lauf-1"}])

        job = fresh_job(state="running", cancelled=True)
        asyncio.run(speedrun._run_main_phase(None, FakeGuild(), job, {}, {}))
        check("die Marke allein hält den Abbruch fest",
              job["state"] == "failed",
              f"wurde {job['state']!r} — »Abgebrochen« sprang zurück auf »Fertig«")

        # -- Sicherung 2: der Task-Abbruch allein -------------------- #
        # Ohne Marke, aber der Task wird gestoppt. Die Einrichtung darf
        # dann nicht zu Ende laufen.
        slow = Handover(delay=2.0)
        speedrun.handover.run_handover = slow
        job2 = fresh_job(state="running")
        speedrun._MAIN_JOBS[2] = job2

        async def run_two():
            speedrun._spawn(
                FakeBot(),
                speedrun._run_main_phase(None, FakeGuild(2), job2, {}, {}),
                2,
            )
            await asyncio.sleep(0.2)
            speedrun._cancel_tasks(2)
            await asyncio.sleep(2.3)
            return job2["state"]

        state_two = asyncio.run(run_two())
        check("der Task-Abbruch allein stoppt die Einrichtung",
              state_two != "done",
              "die Einrichtung lief nach dem Abbruch zu Ende")

        # -- Sicherung 3: die Marke stoppt den Wächter --------------- #
        # Der Bau ist fertig, aber der Lauf ist abgebrochen. Es darf
        # nichts mehr übergeben werden.
        handover3 = Handover()
        install(
            speedrun,
            [{"state": "done", "run_id": "lauf-1", "result": BUILD_RESULT}],
            handover3,
        )
        job3 = fresh_job(cancelled=True)

        async def run_three():
            await speedrun._watch_build(
                FakeBot(), FakeGuild(3), job3, {}, "lauf-1"
            )
            await asyncio.sleep(0.1)

        asyncio.run(run_three())
        check("die Marke hält den Wächter von der Übergabe ab",
              not handover3.calls,
              "trotz Abbruch wurde eingerichtet")
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_a_foreign_run_is_refused():
    """
    Beim Template-Bot liegt ein anderer Lauf -- dann wird nicht
    eingerichtet.

    Ein fertiger Job bleibt dort 15 Minuten abrufbar. Ohne diese
    Prüfung würde der Wächter nach einem Neustart auf einen fremden
    Bau aufsetzen und dessen Kanäle verdrahten.
    """

    print("\nEin fremder Durchlauf wird abgelehnt")

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        handover = Handover()
        install(
            speedrun,
            [{"state": "done", "run_id": "ein-anderer", "result": BUILD_RESULT}],
            handover,
        )

        job = fresh_job()
        asyncio.run(
            speedrun._watch_build(FakeBot(), FakeGuild(), job, {}, "lauf-1")
        )

        check("es wurde nichts eingerichtet", not handover.calls,
              "der Wächter hat einen fremden Bau übernommen")
        check("der Lauf gilt als gescheitert", job["state"] == "failed",
              job["state"])
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_a_template_bot_hiccup_does_not_abort_the_wait():
    """
    Der Template-Bot startet nach einem Deploy neu -- der Bau läuft
    dort weiter. Ein einzelner Aussetzer darf den Wächter nicht
    aufgeben lassen.
    """

    print("\nEin Aussetzer beendet das Warten nicht")

    from fastapi import HTTPException

    from api.routes import speedrun

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template
    original_interval = speedrun.WATCH_INTERVAL
    speedrun.WATCH_INTERVAL = 0.01

    try:
        handover = Handover()
        speedrun.handover.run_handover = handover
        calls = {"n": 0}

        async def flaky(method, path, *, payload=None, timeout=15):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise HTTPException(status_code=502, detail="weg")
            return 200, {"state": "done", "run_id": "lauf-1",
                         "result": BUILD_RESULT}

        speedrun._call_template = flaky

        job = fresh_job()

        async def run():
            await speedrun._watch_build(FakeBot(), FakeGuild(), job, {}, "lauf-1")
            for _ in range(50):
                if handover.calls:
                    break
                await asyncio.sleep(0.02)

        asyncio.run(run())

        check("es wurde trotzdem eingerichtet", bool(handover.calls),
              "ein kurzer Aussetzer hat den ganzen Lauf gekostet")
        check("es wurde mehrfach nachgefragt", calls["n"] > 3, str(calls["n"]))
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun.WATCH_INTERVAL = original_interval
        speedrun._MAIN_JOBS.clear()


def test_the_status_survives_a_dead_template_bot():
    """
    Während der Einrichtung wird der Template-Bot nicht mehr gebraucht.

    Vorher warf ``/status`` 502, sobald er nicht antwortete -- und damit
    ging der Stand des Hauptbots verloren, obwohl der hier im
    Arbeitsspeicher liegt. Der Reiter lief ins Leere, während der Bot
    fleißig einrichtete.
    """

    print("\nEin toter Template-Bot verdeckt den Hauptbot nicht")

    from fastapi import HTTPException

    from api.routes import speedrun

    original_call = speedrun._call_template

    try:
        async def dead(*_a, **_k):
            raise HTTPException(status_code=502, detail="nicht erreichbar")

        speedrun._call_template = dead

        job = fresh_job(state="running", step=3, total=13)
        job["lines"].append({"text": "Verify eingerichtet", "source": "main",
                             "level": "success", "at": time.time()})
        speedrun._MAIN_JOBS[7] = job

        body = asyncio.run(speedrun.status_route(7, 0, 0))

        check("die Antwort kommt durch", isinstance(body, dict))
        check("der Stand des Hauptbots ist da",
              body.get("main", {}).get("state") == "running",
              str(body.get("main")))
        check("seine Zeilen sind da", len(body["main"]["lines"]) == 1)
        check("der Ausfall wird benannt", bool(body.get("template_error")),
              "sonst rätselt der Nutzer, warum die linke Hälfte still steht")

        # Ohne eigenen Job gibt es nichts zu retten -- dann ist der
        # Ausfall die ganze Nachricht und muss durchschlagen.
        speedrun._MAIN_JOBS.clear()
        try:
            asyncio.run(speedrun.status_route(8, 0, 0))
            check("ohne eigenen Lauf schlägt der Fehler durch", False,
                  "der Ausfall wurde verschluckt")
        except HTTPException as exc:
            check("ohne eigenen Lauf schlägt der Fehler durch",
                  exc.status_code == 502, str(exc.status_code))
    finally:
        speedrun._call_template = original_call
        speedrun._MAIN_JOBS.clear()


def test_the_second_half_reports_progress():
    """
    Der Balken darf während der Einrichtung nicht stillstehen.

    Er kam nur vom Template-Bot. War der fertig, sprang er auf 100 %,
    und die dreizehn Schritte der Einrichtung liefen hinter einem
    vollen Balken ab -- es sah aus, als hinge etwas.
    """

    print("\nDie zweite Hälfte meldet Fortschritt")

    from api.routes import speedrun
    from utils import speedrun_handover as ho

    original = speedrun.handover.run_handover
    original_call = speedrun._call_template

    try:
        seen: list[int] = []

        async def counting(bot, guild, payload, options=None, log=None,
                           on_step=None):
            # Drei Schritte melden, wie es der echte Ablauf tut.
            for key in ("verify", "rules", "tickets"):
                if on_step:
                    await on_step(key)
                seen.append(1)

            class Report:
                steps: list = []
                failed: list = []

                def as_dict(self):
                    return {"steps": [], "ok": True}

            return Report()

        speedrun.handover.run_handover = counting
        install(speedrun, [{"state": "done", "run_id": "lauf-1"}])

        wanted = {key: True for key in ho.STEPS}
        job = fresh_job(state="running", options=wanted)

        asyncio.run(
            speedrun._run_main_phase(None, FakeGuild(), job, wanted, {})
        )

        check("eine Gesamtzahl steht fest", job["total"] == len(ho.ORDER),
              f"{job['total']} statt {len(ho.ORDER)}")
        check("der Fortschritt wurde gezählt", len(seen) == 3, str(len(seen)))
        check("am Ende steht er auf voll", job["step"] == job["total"],
              f"{job['step']}/{job['total']}")

        # Der Zähler muss *während* des Laufs steigen, nicht erst am
        # Ende. Nur den Endstand zu prüfen ließ eine Mutation durch, die
        # den Haken gar nicht erst übergab: `job["step"]` wurde im
        # Abschluss ohnehin auf `total` gesetzt, und der Balken stand
        # trotzdem die ganze Einrichtung über still.
        mid: list[int] = []

        async def watching(bot, guild, payload, options=None, log=None,
                           on_step=None):
            for key in ("verify", "rules", "tickets"):
                if on_step:
                    await on_step(key)
                mid.append(job2["step"])

            class Report:
                steps: list = []
                failed: list = []

                def as_dict(self):
                    return {"steps": [], "ok": True}

            return Report()

        speedrun.handover.run_handover = watching
        job2 = fresh_job(state="running", options=wanted)
        asyncio.run(
            speedrun._run_main_phase(None, FakeGuild(), job2, wanted, {})
        )

        check("der Zähler steigt schon während des Laufs",
              mid == [1, 2, 3],
              f"Zwischenstände: {mid} — der Balken bewegt sich nicht mit")
    finally:
        speedrun.handover.run_handover = original
        speedrun._call_template = original_call
        speedrun._MAIN_JOBS.clear()


def test_skipped_steps_still_count():
    """Auch ein übersprungener Schritt ist abgearbeitet.

    Zählte man nur die geglückten, bliebe der Balken bei einem
    unvollständigen Lauf für immer unter 100 % stehen.
    """

    print("\nÜbersprungene Schritte zählen mit")

    from utils import speedrun_handover as ho

    ticked: list[str] = []

    async def on_step(key):
        ticked.append(key)

    # Nichts in der Übergabe: jeder Schritt mit Bedarf wird übersprungen.
    #
    # Die Schritte *ohne* Bedarf (Anti-Nuke, Level, Automod ...) laufen
    # dagegen wirklich los und öffnen dabei SQLite-Verbindungen. Die
    # müssen am Ende geschlossen werden, sonst bleiben die
    # aiosqlite-Arbeitsthreads hängen und der Testlauf endet nie --
    # er lief 300 Sekunden statt einer.
    wanted = {key: True for key in ho.STEPS}

    async def run():
        try:
            return await ho.run_handover(
                None, None, {}, options=wanted, on_step=on_step
            )
        finally:
            from api.db_manager import db_manager

            await db_manager.close_all()

    report = asyncio.run(run())

    needs = [k for k in ho.ORDER if ho.STEPS[k]["needs"]]
    skipped = [s for s in report.steps if "Übersprungen" in s.detail]

    check("es wurde wirklich übersprungen", len(skipped) == len(needs),
          f"{len(skipped)} von {len(needs)}")
    check("jeder übersprungene Schritt wurde gezählt",
          all(key in ticked for key in needs),
          f"nicht gezählt: {[k for k in needs if k not in ticked]}")


def main():
    test_the_watcher_hands_over_without_a_browser()
    test_the_chosen_steps_survive_to_the_handover()
    test_a_cancelled_run_stays_cancelled()
    test_cancel_does_both_things_it_promises()
    test_cancelling_stops_the_watcher_before_it_hands_over()
    test_a_failed_build_sets_up_nothing()
    test_each_cancel_guard_works_on_its_own()
    test_a_foreign_run_is_refused()
    test_a_template_bot_hiccup_does_not_abort_the_wait()
    test_the_status_survives_a_dead_template_bot()
    test_the_second_half_reports_progress()
    test_skipped_steps_still_count()

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
