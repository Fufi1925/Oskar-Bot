#!/usr/bin/env python3
"""
Die Schritt-Liste muss zur gewaehlten Vorlage passen.

Der Speedrun bietet dreizehn Schritte an -- Verify, Tickets, Logs,
Zaehlspiel und so weiter. Manche davon brauchen einen Kanal, den *die
gewaehlte Vorlage* anlegen muss: ohne Verify-Kanal keine Schleuse, ohne
Ticket-Panel keine Tickets.

Vorher lieferte ``/speedrun/steps`` immer dieselbe Liste, alle auf
"an". Bei zwoelf von dreizehn Vorlagen standen dadurch Schalter auf
"an" fuer Sachen, die nie entstehen: ``minimal`` hat weder Verify noch
Tickets noch Rollen-Vergabe, ``rp`` keinen Rollen-Kanal, einen
Zaehl-Kanal hat nur ``community``. Wer sie anliess, las hinterher im
Bericht "Uebersprungen" -- und hatte etwas eingeschaltet, das gar nicht
gehen konnte.

Geprueft wird gegen die **echte** Registry des Template-Bots, nicht
gegen erfundene Vorlagen: die Frage ist ja gerade, ob die Auskunft zu
den ausgelieferten Daten passt.

Run:  python3 tests/test_speedrun_templates.py
"""

import asyncio
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
REPO = os.path.dirname(BOT)
TEMPLATE_REPO = os.path.join(os.path.dirname(REPO), "University-Template")

sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def load_registry():
    """Die echten Vorlagen -- oder None, wenn das Nachbar-Repo fehlt.

    Auf einem Rechner ohne den Template-Bot laesst sich das hier nicht
    pruefen. Dann wird uebersprungen statt rot gemeldet: ein Test, der
    an einer fehlenden Nachbardatei scheitert, sagt nichts ueber den
    Code aus.
    """

    if not os.path.isdir(TEMPLATE_REPO):
        return None
    if TEMPLATE_REPO not in sys.path:
        sys.path.insert(0, TEMPLATE_REPO)
    try:
        from core.registry import TemplateRegistry
    except Exception:
        return None
    return TemplateRegistry(Path(TEMPLATE_REPO) / "templates").load()


def install_fake_template_bot(registry):
    """Der Template-Bot antwortet mit dem, was die echte Registry hergibt."""

    from api.routes import speedrun

    async def fake_call(method, path, *, payload=None, timeout=15):
        return 200, {
            "templates": [
                {"key": t.key, "capabilities": t.capabilities}
                for t in registry.all
            ]
        }

    speedrun._call_template = fake_call
    return speedrun


# --------------------------------------------------------------------- #


def test_the_steps_match_the_chosen_template():
    """Kein Schalter fuer etwas, das diese Vorlage nicht baut."""

    print("\nDie Schritte passen zur Vorlage")

    registry = load_registry()
    if registry is None:
        print("  skip (University-Template liegt nicht daneben)")
        return

    from api.routes import speedrun as module

    original = module._call_template
    speedrun = install_fake_template_bot(registry)
    try:
        problems = []
        for template in registry.all:
            answer = asyncio.run(speedrun.steps(template=template.key))
            caps = template.capabilities

            for step in answer["steps"]:
                key = step["key"]
                possible = caps.get(key, True)

                if not possible and step["supported"]:
                    problems.append(
                        f"{template.key}: {key} wird als möglich gemeldet"
                    )
                if not possible and step["default"]:
                    problems.append(f"{template.key}: {key} steht auf an")
                if possible and not step["supported"]:
                    problems.append(
                        f"{template.key}: {key} wird zu Unrecht gesperrt"
                    )

        check("jede Vorlage bietet nur an, was sie baut",
              not problems,
              f"{len(problems)} Abweichungen: {problems[:4]}")
    finally:
        module._call_template = original


def test_the_known_gaps_are_reported():
    """
    Die Faelle, an denen der Fehler aufgefallen ist.

    Fest verdrahtet, damit ein spaeterer Umbau der Vorlagen nicht
    unbemerkt wieder Schalter fuer Unmoegliches anbietet. Aendert sich
    eine Vorlage absichtlich, muss diese Liste mitwandern -- und genau
    dann soll jemand hinsehen.
    """

    print("\nDie bekannten Lücken werden gemeldet")

    registry = load_registry()
    if registry is None:
        print("  skip (University-Template liegt nicht daneben)")
        return

    expected = {
        # minimal ist der Gegenentwurf: keine Schleuse, kein Ticket,
        # keine Rollen-Vergabe.
        "minimal": {"verify": False, "tickets": False, "selfroles": False},
        # rp hat keinen Rollen-Kanal.
        "rp": {"selfroles": False, "verify": True},
        # business regelt Support über eigene Kanäle.
        "business": {"tickets": False, "verify": True},
        # Zählen gibt es nur auf community.
        "community": {"counting": True, "verify": True, "tickets": True},
        "music": {"counting": False, "verify": True, "tickets": True},
        "dev": {"counting": False, "verify": True, "tickets": True},
    }

    for key, wanted in expected.items():
        template = registry.get(key)
        check(f"es gibt die Vorlage „{key}“", template is not None)
        if template is None:
            continue

        caps = template.capabilities
        for step, should in wanted.items():
            check(f"{key}: {step} = {should}",
                  caps[step] is should,
                  f"gemeldet: {caps[step]}")


def test_logging_is_offered_only_with_log_channels():
    """Ohne Log-Kanäle kein Log-Schritt."""

    print("\nLogs werden nur mit Log-Kanälen angeboten")

    registry = load_registry()
    if registry is None:
        print("  skip (University-Template liegt nicht daneben)")
        return

    from core.schema import ChannelMode

    for template in registry.all:
        has_logs = any(
            spec.mode is ChannelMode.LOG
            for _cat, spec in template.iter_channels()
        )
        check(f"{template.key}: Logs {'ja' if has_logs else 'nein'}",
              template.capabilities["logging"] is has_logs,
              f"gemeldet: {template.capabilities['logging']}")


def test_the_beta_list_only_names_real_templates():
    """
    Ein Tippfehler in der Beta-Liste sperrt eine Vorlage lautlos aus.

    Sie taucht dann im Dashboard als „nicht freigegeben“ auf, und
    niemand käme auf die Idee, dass der Name schlicht falsch
    geschrieben ist.
    """

    print("\nDie Beta-Liste nennt nur echte Vorlagen")

    registry = load_registry()
    if registry is None:
        print("  skip (University-Template liegt nicht daneben)")
        return

    from api.routes import speedrun

    known = {t.key for t in registry.all}
    unknown = sorted(speedrun.BETA_TEMPLATES - known)

    check("jede freigegebene Vorlage gibt es wirklich",
          not unknown,
          f"unbekannt: {unknown} — vorhanden: {sorted(known)}")


def test_an_unreachable_template_bot_does_not_empty_the_list():
    """
    Faellt der Template-Bot aus, lieber alle Schritte anbieten als
    keinen.

    Eine leere Liste wäre schlimmer als eine zu großzügige: der Bot
    überspringt ohnehin, was fehlt, aber ein Reiter ohne einen
    einzigen Schalter sieht kaputt aus.
    """

    print("\nEin toter Template-Bot leert die Liste nicht")

    from fastapi import HTTPException

    from api.routes import speedrun
    from utils import speedrun_handover as ho

    original = speedrun._call_template

    async def dead(*_a, **_k):
        raise HTTPException(status_code=502, detail="nicht erreichbar")

    speedrun._call_template = dead
    try:
        answer = asyncio.run(speedrun.steps(template="community"))

        check("es kommen alle Schritte zurück",
              len(answer["steps"]) == len(ho.STEPS),
              f"{len(answer['steps'])} von {len(ho.STEPS)}")
        check("alle gelten als möglich",
              all(step["supported"] for step in answer["steps"]))
        check("der Ausfall wird benannt",
              bool(answer.get("template_error")),
              "sonst rätselt man, warum nichts gesperrt ist")
    finally:
        speedrun._call_template = original


def test_without_a_template_the_route_behaves_as_before():
    """Ein alter Browser-Stand schickt kein ?template= mit."""

    print("\nOhne Vorlage bleibt alles wie vorher")

    from api.routes import speedrun
    from utils import speedrun_handover as ho

    answer = asyncio.run(speedrun.steps())

    check("alle Schritte kommen zurück",
          len(answer["steps"]) == len(ho.STEPS))
    check("die Standardwerte stimmen",
          all(
              step["default"] is bool(ho.STEPS[step["key"]]["default"])
              for step in answer["steps"]
          ))
    check("nichts ist gesperrt",
          all(step["supported"] for step in answer["steps"]))


def main():
    test_the_steps_match_the_chosen_template()
    test_the_known_gaps_are_reported()
    test_logging_is_offered_only_with_log_channels()
    test_the_beta_list_only_names_real_templates()
    test_an_unreachable_template_bot_does_not_empty_the_list()
    test_without_a_template_the_route_behaves_as_before()

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
