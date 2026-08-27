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


def test_the_invite_links_carry_the_slash_scope():
    """
    Ohne `applications.commands` gibt es nie Slash-Befehle.

    Discord meldet sie nur fuer Server an, auf die der Bot mit diesem
    Scope eingeladen wurde. Fehlt er, ist der Bot drauf, Prefix geht --
    und das / -Menue bleibt leer, egal wie oft gesynct wird.

    Zwei echte Fehler steckten in den Links, die der Bot selbst
    verteilt: `/invite` nannte eine voellig fremde Client-ID, und der
    Link im Erwaehnungs-Menue hatte gar keinen Scope.
    """

    print("\nDie Einladungslinks bringen Slash-Befehle mit")

    import glob
    import re

    # Die ID eines fremden Bots, die hier einmal fest eingetippt war.
    FOREIGN = "1396114795102470196"

    checked = 0
    for path in glob.glob(os.path.join(BOT, "**", "*.py"), recursive=True):
        if os.sep + "tests" + os.sep in path:
            continue
        text = open(path, encoding="utf-8", errors="ignore").read()
        if "oauth2/authorize" not in text:
            continue

        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        rel = os.path.relpath(path, BOT)

        # Je Datei prüfen, nicht je Textstück.
        #
        # Die Links stehen oft über mehrere Zeilen zusammengesetzt --
        # "…authorize" in der einen, "&scope=…" in der nächsten. Wer
        # jedes Fragment einzeln ansieht, meldet lauter Fehlalarme:
        # genau das ist mir hier passiert, sechs Stück auf einmal.
        # Kommentare strippen, bevor gesucht wird.
        #
        # Sonst findet die Prüfung ihre eigene Erklärung wieder: in
        # mention.py steht "Ohne `scope=bot applications.commands` …"
        # als Kommentar direkt über dem Link. Mit dem blieb der Test
        # grün, obwohl der Scope aus dem Link entfernt war -- ein
        # Mutationstest hat genau das durchgelassen.
        code = re.sub(r"^\s*#.*$", "", text, flags=re.M)

        checked += 1
        check(f"{rel}: die Links bringen den Scope mit",
              "applications.commands" in code,
              "ohne ihn gibt es auf diesem Server nie Slash-Befehle")

        # Die fremde ID darf in keinem *Einladungslink* stehen. In
        # Avatar-URLs ist sie harmlos -- das ist nur ein Bild.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.JoinedStr, ast.Constant)):
                continue
            try:
                piece = ast.unparse(node)
            except Exception:
                continue
            if "oauth2/authorize" not in piece:
                continue
            check(f"{rel}: keine fremde Client-ID im Einladungslink",
                  FOREIGN not in piece,
                  f"{FOREIGN} gehoert einem anderen Bot")

    check("es wurden Links geprüft", checked >= 3, str(checked))


def test_the_owner_cog_imports_cleanly():
    """
    Ein NameError in setup() nimmt das ganze Cog mit.

    `aiohttp` wurde in setup() benutzt, aber nie importiert. Damit
    schlug load_extension fehl -- und im Log stand dazu eine einzelne
    rote Zeile zwischen 147 grünen.
    """

    print("\nDas Owner-Cog importiert sauber")

    src = source("cogs", "commands", "owner.py")

    # Jeder benutzte Name auf Modulebene muss auch importiert sein.
    tree = ast.parse(src)
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.asname or a.name for a in node.names}

    setup = function(src, "setup")
    check("es gibt ein setup()", setup is not None)
    if setup is not None:
        body = ast.unparse(setup)
        for name in ("aiohttp",):
            if name in body:
                check(f"{name} ist importiert", name in imported,
                      "sonst: NameError, und das ganze Cog fehlt")


def test_there_is_a_manual_sync_command():
    """Ein Weg, den Sync anzustoßen, ohne neu zu starten."""

    print("\nEs gibt einen Befehl zum Nachsyncen")

    src = source("cogs", "commands", "owner.py")

    check("der Befehl heißt syncslash", 'name="syncslash"' in src)
    check("er ruft tree.sync", "tree.sync" in src)
    check("er kann auch nur diesen Server",
          "copy_global_to" in src,
          "ein globaler Sync braucht bis zu einer Stunde — zum "
          "Ausprobieren ist das unbrauchbar")
    check("er nennt das Rate-Limit beim Namen",
          "429" in src,
          "der häufigste Fehlschlag, und der einzige, den Warten nicht löst")
    check("er meldet einen leeren Baum",
          "Der Sync lief durch" in src,
          "ein leerer Baum synct erfolgreich und liefert nichts")

    # Der alte !sync gleicht Datenbanken ab -- er darf nicht ersetzt
    # worden sein.
    check("der alte !sync bleibt erhalten", 'name="sync"' in src)


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
    # Ausdrücklich so gewünscht: der Bot soll ansprechbar wirken.
    # Vorher stand hier do_not_disturb und er war dauerhaft rot.
    check("sie steht auf »online«",
          "PRESENCE_STATUS = discord.Status.online" in src,
          "gewünscht war: online, nicht »Nicht stören«")

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


def test_premium_is_the_hurdle():
    """
    Im Speedrun ist PREMIUM die Hürde -- der Beta-Code ist weg.

    Vorher schaltete ein Code EINEN Server frei, und Premium spielte
    keine Rolle. Jetzt gibt es genau ein Premium, es hängt am Konto
    und gilt für beide Bots.

    Zwei Dinge werden hier festgehalten:

      * Ohne Premium prallt der Start mit 403 ab -- auch bei einer
        Vorlage, die in der Beta freigegeben ist.
      * Mit Premium läuft er durch, scheitert aber später am fehlenden
        Template-Bot. Wichtig ist nur: nicht an 403.
    """

    print("\nPremium ist die Hürde")

    from fastapi import HTTPException

    from api.routes import speedrun
    from utils import speedrun_access as access

    original_call = speedrun._call_template
    original_premium = speedrun._has_premium
    original_state = access.state

    # Der Server ist nicht gebannt -- ein Bann sticht Premium und der
    # Test prüfte sonst etwas anderes.
    access.state = lambda _g: {"unlocked": True, "banned": False,
                               "ban_reason": ""}

    templates = [
        {"key": "clan", "premium": True},
        {"key": "community", "premium": False},
        # Nicht in der Beta -- muss weiterhin abprallen.
        {"key": "gaming", "premium": True},
    ]

    try:
        # Ohne jedes Premium.
        _install(speedrun, templates, premium=False)

        # 1. Die Liste bietet die Premium-Vorlage an.
        listed = asyncio.run(speedrun.templates(user_id="123"))
        by_key = {t["key"]: t for t in listed["templates"]}
        check("clan ist ohne Premium gesperrt",
              by_key["clan"]["available"] is False,
              "eine Premium-Vorlage darf ohne Premium nicht offenstehen")
        check("und trägt einen Sperrgrund",
              bool(by_key["clan"]["locked_reason"]),
              "ohne Grund weiss niemand, warum sie zu ist")

        # 2. Was nicht in der Beta ist, bleibt gesperrt.
        check("gaming bleibt gesperrt",
              by_key["gaming"]["available"] is False,
              "die Beta-Freigabe muss weiter greifen")
        check("und nennt die Beta als Grund",
              "beta" in by_key["gaming"]["locked_reason"].lower(),
              by_key["gaming"]["locked_reason"])

        # 3. Ohne Premium prallt der Start ab -- mit 403.
        #
        #    Das ist der Kern der Umstellung: frueher genuegte der
        #    Beta-Code, und Premium wurde hier gar nicht geprueft.
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "clan", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("clan prallt ohne Premium ab", False,
                  "der Bau lief ohne Premium los")
        except HTTPException as exc:
            check("clan prallt ohne Premium ab", exc.status_code == 403,
                  f"HTTP {exc.status_code}: {exc.detail}")
            check("die Meldung nennt Premium",
                  "premium" in str(exc.detail).lower(), str(exc.detail))

        # 4. Eine Vorlage außerhalb der Beta prallt weiter ab.
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "gaming", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("gaming prallt ab", False, "eine gesperrte Vorlage lief los")
        except HTTPException as exc:
            # 403 statt 400: die Premium-Pruefung steht jetzt VOR der
            # Beta-Liste. Beides ist ein Abprallen -- entscheidend ist,
            # dass nichts losläuft.
            check("gaming prallt ab", exc.status_code in (400, 403),
                  f"HTTP {exc.status_code}")

        # 5. Eine Vorlage, die der Template-Bot nicht kennt, muss
        #    ebenfalls abprallen -- und zwar über den Startweg, nicht
        #    nur in der Hilfsfunktion. Ein Mutationstest hat gezeigt,
        #    dass die Prüfung ganz entfallen konnte, ohne dass ein Test
        #    rot wurde: sie war nur einzeln geprüft.
        #
        #    MIT Premium, sonst prallt der Start schon an der
        #    Premium-Pruefung ab und ueber die Vorlage waere nichts
        #    gesagt.
        speedrun._has_premium = lambda _u: True
        speedrun.BETA_TEMPLATES.add("gibtsnicht")
        try:
            asyncio.run(
                speedrun.start(
                    _FakeGuild.id,
                    {"template": "gibtsnicht", "user_id": "123"},
                    _FakeBot(),
                )
            )
            check("eine unbekannte Vorlage prallt beim Start ab", False,
                  "der Bau lief mit einem Namen los, den es nicht gibt")
        except HTTPException as exc:
            check("eine unbekannte Vorlage prallt beim Start ab",
                  exc.status_code == 400, f"HTTP {exc.status_code}")
            check("die Meldung nennt den Template-Bot",
                  "template-bot" in str(exc.detail).lower(), str(exc.detail))
        finally:
            speedrun.BETA_TEMPLATES.discard("gibtsnicht")
    finally:
        speedrun._call_template = original_call
        speedrun._has_premium = original_premium
        access.state = original_state
        speedrun._MAIN_JOBS.clear()
        speedrun._MAIN_TASKS.clear()


def test_an_unknown_template_is_refused():
    """
    Ein Tippfehler im Namen soll früh auffallen.

    Sonst scheitert er erst mitten im Bau mit einer Meldung, die
    niemand einordnen kann.
    """

    print("\nEine unbekannte Vorlage prallt ab")

    from fastapi import HTTPException

    from api.routes import speedrun

    original_call = speedrun._call_template

    try:
        async def empty(*_a, **_k):
            return 200, {"templates": []}

        speedrun._call_template = empty
        check("eine unbekannte Vorlage wird abgelehnt",
              asyncio.run(speedrun._template_exists("clan")) is False)

        async def known(*_a, **_k):
            return 200, {"templates": [{"key": "clan", "premium": True}]}

        speedrun._call_template = known
        check("eine bekannte kommt durch",
              asyncio.run(speedrun._template_exists("clan")) is True)

        # Im Zweifel zu: ohne Antwort wird nicht gebaut. Der Bau würde
        # ohne den Template-Bot ohnehin scheitern.
        async def dead(*_a, **_k):
            raise HTTPException(status_code=502, detail="weg")

        speedrun._call_template = dead
        check("ohne erreichbaren Template-Bot: nein",
              asyncio.run(speedrun._template_exists("clan")) is False)
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
    test_the_invite_links_carry_the_slash_scope()
    test_the_owner_cog_imports_cleanly()
    test_there_is_a_manual_sync_command()
    test_the_tree_has_something_to_sync()
    test_the_presence_loop_keeps_the_status()
    test_the_status_is_defined_once()
    test_premium_is_the_hurdle()
    test_an_unknown_template_is_refused()
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
