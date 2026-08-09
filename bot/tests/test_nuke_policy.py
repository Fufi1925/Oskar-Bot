#!/usr/bin/env python3
"""
Die Regeln des Anti-Nuke-Systems.

Sechs Beschwerden waren der Anlass, und danach ist dieser Test
sortiert:

  1. Konnte der Bot nichts ausrichten, passiert gar nichts -- kein
     Log, keine DM, kein Kanal.
  2. Wiederhergestellt wird nur nach einem echten Nuke.
  3. Die DM an den Inhaber kommt nur bei einem Nuke.
  4. Ein Kanal wird nur angelegt, wenn genukt wurde; eine
     Rollenvergabe ergibt nur einen Logeintrag.
  5. Die DM kommt nur, wenn jemand gebannt wurde.
  6. Und das Ganze an EINER Stelle statt in siebzehn Modulen.

Run:  python3 tests/test_nuke_policy.py
"""

import ast
import asyncio
import os
import re
import sys

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


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            doc = body[0]
            for i in range(doc.lineno - 1, min(doc.end_lineno, len(lines))):
                lines[i] = ""
    return "\n".join(lines)


EIN = {"enabled": True, "dm_owner": True, "offer_rebuild": True}


# ------------------------------------------------------------------ #
# 1. Nichts ausgerichtet -> gar nichts
# ------------------------------------------------------------------ #
def test_powerless_means_silent():
    """Die wichtigste der sechs Regeln.

    Wenn dem Bot ein Recht fehlt oder er die Audit-Logs nicht lesen
    darf, hat er den Angriff nicht gestoppt. Eine Meldung darueber ist
    Laerm in genau dem Moment, in dem ohnehin nichts geschuetzt wird
    -- und sie kostet Zeit und Rate-Limit, waehrend der Server
    angegriffen wird.
    """
    print("\nMachtlos heisst still")

    from utils import nuke_policy as policy

    for outcome in (policy.OUTCOME_NO_PERMS, policy.OUTCOME_BLIND,
                    policy.OUTCOME_DISABLED):
        d = policy.decide("channel_delete", outcome, banned=False,
                          enabled=True, settings=EIN)
        check(f"{outcome}: kein Logeintrag", not d.log)
        check(f"{outcome}: kein Alarm", not d.post)
        check(f"{outcome}: keine DM", not d.dm)
        check(f"{outcome}: kein Kanal", not d.rebuild)

    # Auch bei ausgeschaltetem System, selbst wenn alles andere
    # zutraefe.
    d = policy.decide("channel_delete", policy.OUTCOME_STOPPED, banned=True,
                      enabled=False, settings=EIN)
    check("ausgeschaltet: gar nichts",
          not (d.log or d.post or d.dm or d.rebuild), repr(d))

    # Die Sammlung muss vollstaendig sein -- ein vergessenes Ergebnis
    # faellt sonst durch.
    check("alle drei stehen in POWERLESS",
          policy.POWERLESS == {policy.OUTCOME_NO_PERMS, policy.OUTCOME_BLIND,
                               policy.OUTCOME_DISABLED},
          str(sorted(policy.POWERLESS)))


# ------------------------------------------------------------------ #
# 2./4. Wiederherstellung und Kanaele
# ------------------------------------------------------------------ #
def test_rebuild_only_after_a_real_nuke():
    print("\nWiederherstellung nur nach einem echten Nuke")

    from utils import nuke_policy as policy

    for action in sorted(policy.NUKE_ACTIONS):
        d = policy.decide(action, policy.OUTCOME_STOPPED, banned=True,
                          enabled=True, settings=EIN)
        check(f"{action}: Wiederherstellung angeboten", d.rebuild)
        check(f"{action}: und gemeldet", d.post)

    for action in sorted(policy.INCIDENT_ONLY):
        d = policy.decide(action, policy.OUTCOME_STOPPED, banned=True,
                          enabled=True, settings=EIN)
        check(f"{action}: KEINE Wiederherstellung", not d.rebuild)
        check(f"{action}: KEINE DM", not d.dm)
        check(f"{action}: aber ein Logeintrag", d.log)

    # Punkt 4 woertlich: eine Rollenvergabe.
    d = policy.decide("member_update", policy.OUTCOME_STOPPED, banned=True,
                      enabled=True, settings=EIN)
    check("Rollenvergabe: nur der Logeintrag",
          d.log and not d.post and not d.dm and not d.rebuild, repr(d))

    # channel_create gehoert BEWUSST nicht zu den Nukes: dabei geht
    # nichts verloren.
    check("ein angelegter Kanal ist kein Nuke",
          not policy.is_nuke_action("channel_create"))
    check("ein geloeschter schon", policy.is_nuke_action("channel_delete"))


def test_the_action_lists_cover_every_module():
    """Ein Modul mit unbekannter Aktion faellt still auf »Vorfall«.

    Das waere die harmlose Richtung -- aber ein neues Modul, das
    Kanaele loescht, bekaeme dann keine Wiederherstellung. Deshalb
    muss jede Aktion, die es wirklich gibt, eingeordnet sein.
    """
    print("\nJedes Modul ist eingeordnet")

    from utils import nuke_policy as policy

    folder = os.path.join(BOT, "cogs", "antinuke")
    used = set()
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".py"):
            continue
        src = open(os.path.join(folder, entry), encoding="utf-8").read()
        found = re.search(r'ALERT_ACTION\s*=\s*"([a-z_]+)"', src)
        if found:
            used.add(found.group(1))

    check("es gibt Module", len(used) >= 15, str(len(used)))

    known = policy.NUKE_ACTIONS | policy.INCIDENT_ONLY
    check("jede benutzte Aktion ist eingeordnet",
          used <= known, f"unbekannt: {sorted(used - known)}")
    check("und keine Einordnung ins Leere",
          known <= used, f"nie benutzt: {sorted(known - used)}")

    # Die beiden Listen duerfen sich nicht ueberschneiden -- sonst
    # entscheidet die Reihenfolge im Code, und das waere Zufall.
    check("die Listen ueberschneiden sich nicht",
          not (policy.NUKE_ACTIONS & policy.INCIDENT_ONLY),
          str(sorted(policy.NUKE_ACTIONS & policy.INCIDENT_ONLY)))


# ------------------------------------------------------------------ #
# 3./5. Die DM
# ------------------------------------------------------------------ #
def test_the_dm_needs_a_nuke_and_a_ban():
    """Beides, nicht eines von beiden.

    Eine DM ist die lauteste Meldung, die es gibt -- sie erreicht den
    Inhaber auch nachts. Ein Bann wegen einer Rollenvergabe ist kein
    Grund dafuer, und ein Nuke ohne Bann heisst, dass der Angreifer
    noch da ist: dann steht es im Kanal, aber die DM wartet.
    """
    print("\nDie DM braucht einen Nuke UND einen Bann")

    from utils import nuke_policy as policy

    faelle = [
        ("channel_delete", policy.OUTCOME_STOPPED, True, True),
        ("channel_delete", policy.OUTCOME_STOPPED, False, False),
        ("channel_delete", policy.OUTCOME_PARTIAL, False, False),
        ("role_delete", policy.OUTCOME_STOPPED, True, True),
        ("prune", policy.OUTCOME_STOPPED, True, True),
        ("member_update", policy.OUTCOME_STOPPED, True, False),
        ("ban", policy.OUTCOME_STOPPED, True, False),
        ("webhook_create", policy.OUTCOME_STOPPED, True, False),
    ]
    for action, outcome, banned, erwartet in faelle:
        d = policy.decide(action, outcome, banned=banned, enabled=True,
                          settings=EIN)
        check(
            f"{action}/{outcome}/banned={banned} -> DM={erwartet}",
            d.dm is erwartet,
            f"-> {d.dm}",
        )


def test_the_switches_still_work():
    """Die Regeln ersetzen die Einstellungen nicht, sie ergaenzen sie."""
    print("\nDie Schalter greifen weiter")

    from utils import nuke_policy as policy

    d = policy.decide("channel_delete", policy.OUTCOME_STOPPED, banned=True,
                      enabled=True, settings=dict(EIN, dm_owner=False))
    check("dm_owner=False verhindert die DM", not d.dm)
    check("der Alarm bleibt trotzdem", d.post)

    d = policy.decide("channel_delete", policy.OUTCOME_STOPPED, banned=True,
                      enabled=True, settings=dict(EIN, offer_rebuild=False))
    check("offer_rebuild=False verhindert den Kanal", not d.rebuild)

    # Vorfaelle im Kanal sind abschaltbar -- und aus als Vorgabe.
    d = policy.decide("member_update", policy.OUTCOME_STOPPED, banned=True,
                      enabled=True, settings=EIN)
    check("Vorfaelle stehen standardmaessig nicht im Kanal", not d.post)
    d = policy.decide("member_update", policy.OUTCOME_STOPPED, banned=True,
                      enabled=True, settings=dict(EIN, post_incidents=True))
    check("aber man kann sie einschalten", d.post)


# ------------------------------------------------------------------ #
# Angriffserkennung
# ------------------------------------------------------------------ #
def test_one_slip_is_not_an_attack():
    """Ein einzelner geloeschter Kanal passiert im Alltag."""
    print("\nEin Fehlklick ist kein Angriff")

    from utils import nuke_policy as policy

    policy.forget(1)
    policy.note_action(1, "channel_delete")
    check("nach einem geloeschten Kanal: kein Angriff",
          not policy.is_under_attack(1))

    policy.note_action(1, "channel_delete")
    check("nach zweien schon", policy.is_under_attack(1))

    # Vorfaelle duerfen die Schwelle nicht mit erreichen helfen.
    policy.forget(2)
    for _ in range(20):
        policy.note_action(2, "member_update")
    check("zwanzig Rollenvergaben sind kein Angriff",
          not policy.is_under_attack(2))

    # Und die Zaehlung ist je Server getrennt.
    policy.forget(3)
    policy.forget(4)
    policy.note_action(3, "channel_delete")
    policy.note_action(3, "channel_delete")
    policy.note_action(4, "channel_delete")
    check("Server 3 ist im Angriff", policy.is_under_attack(3))
    check("Server 4 nicht", not policy.is_under_attack(4))

    check("die Zusammenfassung nennt die Aktionen",
          "channel_delete" in policy.attack_summary(3),
          policy.attack_summary(3))

    policy.forget(3)
    check("und vergessen geht auch", not policy.is_under_attack(3))

    # ── Das Zeitfenster ──────────────────────────────────────────
    #
    # Ohne diesen Fall blieb der Test gruen, als die Zeitpruefung
    # ausgebaut war: zwei geloeschte Kanaele von GESTERN haetten dann
    # heute noch als laufender Angriff gegolten -- und der Bot haette
    # einen Backup-Kanal auf einem voellig heilen Server angelegt.
    import time as _time

    policy.forget(5)
    policy.note_action(5, "channel_delete")
    policy.note_action(5, "channel_delete")
    check("frisch: Angriff erkannt", policy.is_under_attack(5))

    # Die Eintraege kuenstlich altern lassen -- schneller als zu
    # warten, und es prueft genau dieselbe Rechnung.
    alt = _time.time() - (policy.NUKE_WINDOW + 5)
    policy._recent[5] = [(alt, "channel_delete"), (alt, "channel_delete")]
    check(
        "alte Ereignisse zaehlen nicht mehr",
        not policy.is_under_attack(5),
        "ein Angriff von gestern gaelte heute noch",
    )
    check("und sie werden weggeraeumt",
          len(policy._recent.get(5, [])) == 0,
          str(len(policy._recent.get(5, []))))

    # Dasselbe beim Mitzaehlen: ein alter Eintrag darf einen neuen
    # nicht zur Schwelle verhelfen.
    policy.forget(6)
    policy._recent[6] = [(alt, "channel_delete")]
    policy.note_action(6, "channel_delete")
    check(
        "ein alter plus ein neuer sind kein Angriff",
        not policy.is_under_attack(6),
        f"-> {len(policy._recent.get(6, []))} Eintraege",
    )

    # Und die Zusammenfassung darf nichts Altes nennen.
    policy.forget(7)
    policy._recent[7] = [(alt, "channel_delete")]
    check("die Zusammenfassung ist dann leer",
          policy.attack_summary(7) == "", policy.attack_summary(7))

    # `note_action` gibt die Zahl im Fenster zurueck -- und muss dabei
    # selbst filtern.
    #
    # Ohne diesen Fall blieb der Test gruen, als der Filter dort
    # ausgebaut war: `is_under_attack` filtert noch einmal und deckte
    # den Fehler zu. Der Rueckgabewert war trotzdem falsch, und wer
    # sich darauf verlaesst -- etwa um "3. Angriff in Folge" zu melden
    # -- bekaeme Unsinn.
    policy.forget(8)
    policy._recent[8] = [(alt, "channel_delete"), (alt, "channel_delete")]
    zahl = policy.note_action(8, "channel_delete")
    check(
        "note_action zaehlt nur das Zeitfenster",
        zahl == 1,
        f"-> {zahl}; alte Ereignisse werden mitgezaehlt",
    )


# ------------------------------------------------------------------ #
# Die Verdrahtung
# ------------------------------------------------------------------ #
def test_report_asks_the_policy():
    """Die Regeln muessen auch BENUTZT werden."""
    print("\nDie Meldung fragt die Regeln")

    src = strip_py(
        open(os.path.join(BOT, "utils", "nuke_alert.py"), encoding="utf-8").read()
    )
    block = src.split("async def report(")[1].split("\nasync def ")[0]

    check("die Regeln werden gefragt", "policy.decide(" in block)
    check("das Ergebnis heisst decision", "decision" in block)

    # Jede der vier Erlaubnisse muss wirklich abgefragt werden.
    for feld, wozu in (
        ("decision.log", "Logeintrag"),
        ("decision.post", "Alarm im Kanal"),
        ("decision.dm", "DM"),
        ("decision.rebuild", "Wiederherstellung"),
    ):
        check(f"{wozu} haengt an {feld}", feld in block,
              "die Regel wird berechnet und ignoriert")

    # `banned` muss durchgereicht werden -- ohne das greift Regel 5
    # nie.
    check("banned wird weitergegeben", "banned=banned" in block)
    check("und ist ein Parameter",
          "banned: bool = False" in src,
          "sonst weiss report() nichts davon")

    # Der Logeintrag darf erst NACH der Entscheidung geschrieben
    # werden. Steht er davor, landet jede Machtlosigkeit doch im
    # Verlauf.
    check(
        "der Logeintrag kommt nach der Entscheidung",
        block.index("policy.decide(") < block.index("await record("),
        "sonst wird trotzdem protokolliert",
    )


def test_the_handlers_pass_the_ban_through():
    print("\nDie Helfer reichen den Bann durch")

    src = strip_py(
        open(os.path.join(BOT, "utils", "nuke_alert.py"), encoding="utf-8").read()
    )

    stopped = src.split("async def handle_stopped")[1].split("async def ")[0]
    check("handle_stopped meldet einen Bann",
          "banned=banned" in stopped and "banned: bool = True" in stopped,
          "sonst kommt bei einem gestoppten Nuke keine DM")

    partial = src.split("async def handle_partial")[1].split("async def ")[0]
    check(
        "handle_partial meldet KEINEN Bann",
        "banned=False" in partial,
        "der Bann ging ja gerade nicht durch -- Regel 5",
    )


def test_the_backup_channel_checks_twice():
    """Zwischen Anstossen und Anlegen liegen zwanzig Sekunden."""
    print("\nDer Backup-Kanal prueft ein zweites Mal")

    src = strip_py(
        open(os.path.join(BOT, "utils", "nuke_alert.py"), encoding="utf-8").read()
    )
    block = src.split("async def schedule_backup_channel")[1].split(
        "\ndef "
    )[0]

    check("es wird nachgeprueft", "is_under_attack" in block)
    guarded = re.search(
        r"if not policy\.is_under_attack\([\s\S]{0,60}?return", block
    )
    check("und bei keinem Angriff abgebrochen", bool(guarded),
          "ein Kanal namens backup auf einem heilen Server ist Muell")
    # Vor dem Anlegen, nicht danach.
    check(
        "vor dem Anlegen",
        block.index("is_under_attack") < block.index("ensure_backup_channel"),
        "sonst steht der Kanal schon da",
    )


def test_all_modules_use_the_helpers():
    """Siebzehn Module, eine Regel.

    Ein Modul, das an den Helfern vorbei meldet, umgeht damit alle
    sechs Regeln auf einmal.
    """
    print("\nAlle Module gehen ueber die Helfer")

    folder = os.path.join(BOT, "cogs", "antinuke")
    direkt = []
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".py"):
            continue
        src = strip_py(open(os.path.join(folder, entry), encoding="utf-8").read())
        # Ein direkter `nuke_alert.report(`-Aufruf umginge die Helfer.
        if "nuke_alert.report(" in src or "alert.report(" in src:
            direkt.append(entry)

    check("kein Modul meldet direkt", not direkt, f"-> {direkt}")

    # Und jedes Modul meldet ueberhaupt.
    stumm = []
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".py") or entry == "__init__.py":
            continue
        src = open(os.path.join(folder, entry), encoding="utf-8").read()
        if "handle_" not in src:
            stumm.append(entry)
    check("jedes Modul meldet", not stumm, f"-> {stumm}")


def test_the_new_switches_reach_the_bot():
    """Ein Schalter im Dashboard, der nirgends ankommt, ist Zierde."""
    print("\nDie neuen Schalter kommen an")

    src = strip_py(
        open(os.path.join(BOT, "utils", "nuke_alert.py"), encoding="utf-8").read()
    )

    for key in ("offer_rebuild", "post_incidents"):
        check(f"{key}: es gibt eine Vorgabe", f'"{key}"' in src)
        # Speicherbar muss er auch sein -- sonst laesst er sich
        # umlegen und faellt beim naechsten Laden zurueck.
        block = src.split("async def save_settings")[1].split("async def ")[0]
        check(f"{key}: laesst sich speichern", key in block,
              "der Schalter faellt beim Neuladen zurueck")

    # Und das Schema muss sie kennen -- eine bestehende Datenbank
    # bekommt sie per ALTER TABLE nachgezogen.
    schema = src.split("async def ensure_schema")[1].split("\nDEFAULTS")[0]
    check("das Schema zieht sie nach", "ALTER TABLE nuke_alerts" in schema)
    check(
        "und prueft vorher, ob es sie schon gibt",
        "PRAGMA table_info(nuke_alerts)" in schema,
        "SQLite kann ADD COLUMN nicht bedingt -- der zweite Start wuerfe",
    )

    # post_incidents muss AUS sein: ein Alarmkanal voller
    # Rollenvergaben wird nicht mehr gelesen.
    defaults = src.split("DEFAULTS = {")[1].split("}")[0]
    check(
        "post_incidents ist standardmaessig aus",
        '"post_incidents": 0' in defaults,
        defaults,
    )
    check('offer_rebuild ist standardmaessig an',
          '"offer_rebuild": 1' in defaults, defaults)


def test_the_panel_explains_the_silence():
    """Schweigen sieht leicht wie ein Ausfall aus."""
    print("\nDas Dashboard erklaert, wann nichts passiert")

    path = os.path.join(
        os.path.dirname(BOT), "dashboard", "components", "dashboard",
        "nuke-alert-panel.tsx",
    )
    if not os.path.isfile(path):
        check("das Panel gibt es", False)
        return

    panel = open(path, encoding="utf-8").read()

    check("es gibt die Uebersicht", "Wann der Bot was tut" in panel)
    check("sie nennt den Nuke-Fall", "gelöscht" in panel)
    check(
        "sie nennt den stillen Fall",
        "Gar nichts" in panel,
        "sonst haelt jemand das Schweigen fuer einen Ausfall",
    )
    # Die Schalter muessen den Wert auch LESEN und SETZEN. Eine Suche
    # nach dem Namen blieb gruen, als dort fest `checked={false}`
    # stand -- der Schalter war da und liess sich nicht umlegen.
    for key in ("offer_rebuild", "post_incidents"):
        check(f"{key}: der Schalter liest den Wert",
              f'checked={{value("{key}")}}' in panel,
              "er steht fest auf einem Wert")
        check(f"{key}: und schreibt ihn",
              f'set("{key}", v)' in panel,
              "umlegen bewirkt nichts")
    check(
        "die DM ist ehrlich beschriftet",
        "gebannt hat" in panel,
        "sonst verspricht der Schalter mehr, als er tut",
    )


def main() -> int:
    test_powerless_means_silent()
    test_rebuild_only_after_a_real_nuke()
    test_the_action_lists_cover_every_module()
    test_the_dm_needs_a_nuke_and_a_ban()
    test_the_switches_still_work()
    test_one_slip_is_not_an_attack()
    test_report_asks_the_policy()
    test_the_handlers_pass_the_ban_through()
    test_the_backup_channel_checks_twice()
    test_all_modules_use_the_helpers()
    test_the_new_switches_reach_the_bot()
    test_the_panel_explains_the_silence()

    print()
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    print("Alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
