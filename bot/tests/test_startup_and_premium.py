#!/usr/bin/env python3
"""
Zwei Startfehler und eine Rechteluecke.

  1. **Keine Slash-Befehle.** Der Command-Sync stand hinter
     ``run_sync(TOKEN)`` -- dem Emoji-Abgleich, der den Prozess per
     ``os.execv`` ersetzt, sobald er ``emoji.py`` angefasst hat. Dann
     wurde alles danach nie erreicht. Dazu lief er bei *jedem*
     Reconnect erneut, obwohl Discord nur wenige globale Syncs pro Tag
     erlaubt: ein Bot mit wackliger Verbindung landete im Rate-Limit
     und hatte danach gar keine Slash-Befehle mehr.

  2. **Der Status sprang auf Online.** Im Konstruktor stand
     ``do_not_disturb``, die Presence-Schleife rief danach
     ``change_presence(activity=...)`` ohne ``status``. discord.py
     setzt dann hart ``Status.online`` -- nachzulesen in
     ``Client.change_presence``. Der erste Tick nach dem Start hat das
     "Nicht stoeren" also ueberschrieben.

  3. **Premium nur im Browser geprueft.** ``/speedrun/start`` sah nur
     in die Beta-Liste. Wer den Endpunkt direkt aufrief, baute jede
     Premium-Vorlage ohne Premium.

Run:  python3 tests/test_startup_and_premium.py
"""

import ast
import asyncio
import os
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


def source(*parts) -> str:
    return open(os.path.join(BOT, *parts), encoding="utf-8").read()


def function(src: str, name: str):
    tree = ast.parse(src)
    return next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ),
        None,
    )


# --------------------------------------------------------------------- #
# 1. Slash-Befehle
# --------------------------------------------------------------------- #


def test_the_command_sync_actually_runs():
    """Ohne Sync gibt es kein / -Menü — nur Prefix."""

    print("\nDie Slash-Befehle werden angemeldet")

    src = source("university_bot.py")
    ready = function(src, "on_ready")
    check("es gibt on_ready", ready is not None)
    if ready is None:
        return

    body = ast.unparse(ready)
    check("der Baum wird synchronisiert", "tree.sync" in body,
          "ohne tree.sync() kennt Discord keinen einzigen Slash-Befehl")

    # Der Sync muss *vor* dem Emoji-Abgleich stehen: der ersetzt den
    # Prozess, sobald er emoji.py angefasst hat.
    if "tree.sync" in body and "run_sync" in body:
        check("er läuft vor dem Emoji-Abgleich",
              body.index("tree.sync") < body.index("run_sync"),
              "run_sync kann den Prozess neu starten — alles danach "
              "wird dann übersprungen")


def test_the_sync_does_not_repeat_on_every_reconnect():
    """
    Discord erlaubt nur wenige globale Command-Syncs pro Tag.

    `on_ready` feuert bei jedem Reconnect. Ohne Riegel läuft ein Bot
    mit wackliger Verbindung ins Rate-Limit und hat danach gar keine
    Slash-Befehle mehr.
    """

    print("\nDer Sync läuft einmal pro Prozess")

    src = source("university_bot.py")
    ready = function(src, "on_ready")
    if ready is None:
        check("es gibt on_ready", False)
        return

    body = ast.unparse(ready)

    check("es gibt einen Riegel", "_COMMANDS_SYNCED" in body)
    # Er muss abgefragt *und* gesetzt werden. Nur eines von beidem
    # wäre wirkungslos.
    check("er wird abgefragt", "if not _COMMANDS_SYNCED" in body,
          "ohne die Abfrage synct jeder Reconnect erneut")
    check("und gesetzt", "_COMMANDS_SYNCED = True" in body)

    # Und er muss modulweit existieren, sonst wirft `global` beim
    # ersten Zugriff einen NameError.
    check("die Variable ist modulweit angelegt",
          "\n_COMMANDS_SYNCED = False" in src,
          "sonst: NameError beim ersten on_ready")

    # Nach einem Fehlschlag soll es der nächste Reconnect erneut
    # versuchen -- ein Aussetzer darf nicht dauerhaft kosten.
    check("ein Fehlschlag erlaubt einen neuen Versuch",
          "_COMMANDS_SYNCED = False" in body,
          "sonst bleibt der Bot nach einem einzigen Fehler für immer "
          "ohne Slash-Befehle")


def test_a_failed_sync_is_not_swallowed():
    """Ein `print` zwischen tausend Startzeilen sieht niemand."""

    print("\nEin gescheiterter Sync fällt auf")

    src = source("university_bot.py")
    ready = function(src, "on_ready")
    body = ast.unparse(ready) if ready else ""

    check("der Fehler geht ins Log",
          "logging.exception" in body,
          "mit print verschwindet er in der Startausgabe")
    check("logging ist importiert", "\nimport logging" in src)


def test_the_tree_has_something_to_sync():
    """
    Ein leerer Baum synct erfolgreich — und liefert nichts.

    Deshalb hier die Gegenprobe: es müssen wirklich App-Commands
    registriert sein.
    """

    print("\nEs gibt überhaupt Slash-Befehle")

    # Der Boot-Test zählt sie beim echten Laden aller Cogs. Hier reicht
    # die Frage, ob überhaupt welche deklariert sind -- ohne die 147
    # Cogs zu laden, was Minuten dauert.
    import glob
    import re

    found = 0
    for path in glob.glob(os.path.join(BOT, "cogs", "**", "*.py"),
                          recursive=True):
        text = open(path, encoding="utf-8", errors="ignore").read()
        found += len(re.findall(r"@\w*\s*app_commands\s*\.\s*command", text))
        found += len(re.findall(r"hybrid_command", text))

    check("es sind Slash-Befehle deklariert", found > 20, str(found))


# --------------------------------------------------------------------- #
# 2. Der Online-Status
# --------------------------------------------------------------------- #


def test_the_presence_loop_keeps_the_status():
    """
    Der Fehler: change_presence ohne `status` setzt auf online.

    discord.py macht daraus `Status.online` -- der erste Tick der
    Schleife hat das "Nicht stören" aus dem Konstruktor gelöscht.
    """

    print("\nDie Presence-Schleife behält den Status")

    src = source("core", "universitybot.py")
    tree = ast.parse(src)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "change_presence"
    ]
    check("es gibt einen change_presence-Aufruf", bool(calls))

    for index, call in enumerate(calls, 1):
        names = {kw.arg for kw in call.keywords}
        check(f"Aufruf {index} schickt den Status mit",
              "status" in names,
              f"kwargs={sorted(n for n in names if n)} — ohne status "
              "springt der Bot auf online")


def test_the_status_is_defined_once():
    """Zwei Quellen für denselben Wert laufen auseinander."""

    print("\nDer Status steht an genau einer Stelle")

    src = source("core", "universitybot.py")

    check("es gibt eine Konstante",
          "PRESENCE_STATUS = discord.Status." in src)
    check("sie steht auf »Nicht stören«",
          "PRESENCE_STATUS = discord.Status.do_not_disturb" in src,
          "gewünscht war: nicht online")

    # Der Konstruktor darf den Wert nicht noch einmal hinschreiben.
    tree = ast.parse(src)
    init = function(src, "__init__")
    if init is not None:
        body = ast.unparse(init)
        check("der Konstruktor nutzt die Konstante",
              "self.PRESENCE_STATUS" in body,
              "ein zweiter fester Wert läuft irgendwann auseinander")

    # Und die Schleife ebenso.
    tick = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = ast.unparse(node)
            if "change_presence" in text:
                tick = text
                break
    check("die Schleife nutzt dieselbe Konstante",
          tick is not None and "PRESENCE_STATUS" in tick,
          "sonst kann sie den Status wieder überschreiben")


# --------------------------------------------------------------------- #
# 3. Premium
# --------------------------------------------------------------------- #


class _FakeGuild:
    id = 1520714989860814992
    name = "Testserver"


class _FakeBot:
    loop = None

    def get_guild(self, _id):
        return _FakeGuild()


def _install(speedrun, templates, premium: bool):
    """Template-Bot und Premium-Abfrage ersetzen."""

    async def fake_call(method, path, *, payload=None, timeout=15):
        return 200, {"templates": templates}

    speedrun._call_template = fake_call
    speedrun._has_premium = lambda _user: premium


def test_a_premium_template_needs_premium():
    """
    Der Kern: /start muss Premium selbst prüfen.

    Die Liste markiert Premium-Vorlagen korrekt als gesperrt, aber
    /start sah nur in die Beta-Liste. Wer den Endpunkt direkt aufrief,
    baute jede Premium-Vorlage ohne Premium.
    """

    print("\nEine Premium-Vorlage verlangt Premium")

    from fastapi import HTTPException

    from api.routes import speedrun
    from utils import speedrun_access as access

    original_call = speedrun._call_template
    original_premium = speedrun._has_premium
    original_state = access.state

    # Der Server ist freigeschaltet -- sonst greift die Code-Sperre
    # zuerst und der Test prüfte etwas anderes.
    access.state = lambda _g: {"unlocked": True, "banned": False,
                               "ban_reason": ""}

    templates = [
        {"key": "clan", "premium": True},
        {"key": "community", "premium": False},
    ]

    try:
        # 1. Ohne Premium: abgelehnt.
        _install(speedrun, templates, premium=False)
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "clan", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("ohne Premium wird abgelehnt", False,
                  "der Clan-Server wurde ohne Premium gebaut")
        except HTTPException as exc:
            check("ohne Premium wird abgelehnt", exc.status_code == 403,
                  f"HTTP {exc.status_code}")
            check("die Meldung nennt Premium",
                  "premium" in str(exc.detail).lower(), str(exc.detail))

        # 2. Eine freie Vorlage geht auch ohne Premium durch.
        #    Sie scheitert später am fehlenden Template-Bot -- aber
        #    nicht mit 403.
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "community", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("eine freie Vorlage kommt durch", True)
        except HTTPException as exc:
            check("eine freie Vorlage kommt durch", exc.status_code != 403,
                  f"HTTP {exc.status_code}: {exc.detail}")

        # 3. Mit Premium geht die Premium-Vorlage.
        _install(speedrun, templates, premium=True)
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "clan", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("mit Premium kommt sie durch", True)
        except HTTPException as exc:
            check("mit Premium kommt sie durch", exc.status_code != 403,
                  f"HTTP {exc.status_code}: {exc.detail}")
    finally:
        speedrun._call_template = original_call
        speedrun._has_premium = original_premium
        access.state = original_state
        speedrun._MAIN_JOBS.clear()
        speedrun._MAIN_TASKS.clear()


def test_an_unreachable_template_bot_denies_rather_than_allows():
    """Im Zweifel zu: eine kaputte Abfrage darf nichts freischalten."""

    print("\nIm Zweifel wird nicht gebaut")

    from fastapi import HTTPException

    from api.routes import speedrun

    original_call = speedrun._call_template

    async def dead(*_a, **_k):
        raise HTTPException(status_code=502, detail="weg")

    speedrun._call_template = dead
    try:
        allowed = asyncio.run(speedrun._template_is_free("clan", "123"))
        check("ohne Antwort keine Freigabe", allowed is False,
              "ein Aussetzer schaltet eine bezahlte Vorlage frei")

        # Auch eine unbekannte Vorlage darf nicht durchrutschen.
        async def empty(*_a, **_k):
            return 200, {"templates": []}

        speedrun._call_template = empty
        allowed = asyncio.run(speedrun._template_is_free("clan", "123"))
        check("eine unbekannte Vorlage wird abgelehnt", allowed is False)
    finally:
        speedrun._call_template = original_call


def test_the_beta_list_has_five_templates():
    """Fünf sollten es sein — clan ist dazugekommen."""

    print("\nFünf Vorlagen sind freigegeben")

    from api.routes import speedrun

    check("es sind fünf", len(speedrun.BETA_TEMPLATES) == 5,
          str(sorted(speedrun.BETA_TEMPLATES)))
    check("clan ist dabei", "clan" in speedrun.BETA_TEMPLATES)


def main():
    test_the_command_sync_actually_runs()
    test_the_sync_does_not_repeat_on_every_reconnect()
    test_a_failed_sync_is_not_swallowed()
    test_the_tree_has_something_to_sync()
    test_the_presence_loop_keeps_the_status()
    test_the_status_is_defined_once()
    test_a_premium_template_needs_premium()
    test_an_unreachable_template_bot_denies_rather_than_allows()
    test_the_beta_list_has_five_templates()

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
