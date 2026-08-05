#!/usr/bin/env python3
"""
Der Usage-Reiter und der Clan-Server im Speedrun.

Vier Fehler, alle vorher reproduziert:

  1. **Der Reiter war fuer fast jede Rolle unsichtbar.** Das
     Admin-Panel blendet einen Reiter aus, wenn die Rolle die in
     ``TAB_PERMISSION`` hinterlegte Berechtigung nicht hat. Fuer
     ``usage`` ist das ``metrics.view`` -- und die hatten sechs von
     einundvierzig Rollen.

  2. **Wer ihn doch sah, bekam 403.** Der BFF-Proxy entscheidet anhand
     von ``ADMIN_PERMISSIONS``, welche Berechtigung ein
     ``/admin/*``-Endpunkt braucht. ``command-stats`` stand nicht
     drin, fiel damit auf ``verifyAdminAccess()`` zurueck -- und die
     laesst ausschliesslich globale Admins durch.

  3. **Slash-Befehle wurden nie gezaehlt.** Gezaehlt wurde in
     ``on_command_completion``, und das feuert discord.py nur fuer
     Prefix-Befehle. Die Statistik zeigte damit ausgerechnet die
     Bedienung nicht, die Discord den Nutzern anbietet. Dasselbe bei
     der Bezugsgroesse: ``walk_commands()`` kennt keine Slash-Befehle.

  4. **Clan stand auf Platz neun.** Der Template-Bot sortiert nach
     (premium, Name); im Speedrun entscheidet aber die Beta-Freigabe.
     Die einzige baubare Premium-Vorlage lag deshalb hinter sieben
     grauen Kacheln.

Dazu die Servernamen: die Statistik nennt jeden Server, auf dem der
Bot ist. Fuer alle ausser Ownern werden Name, Bild und ID maskiert.

Run:  python3 tests/test_usage_and_clan.py
"""

import ast
import asyncio
import os
import re
import sys

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


def source(*parts) -> str:
    return open(os.path.join(BOT, *parts), encoding="utf-8").read()


def dashboard_source(*parts) -> str:
    return open(os.path.join(DASH, *parts), encoding="utf-8").read()


def strip_ts_comments(src: str) -> str:
    """Sonst treffen die Suchen die eigenen Kommentare statt des Codes."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def strip_py_comments(src: str) -> str:
    return re.sub(r"^\s*#.*$", "", src, flags=re.M)


def listener_names(src: str) -> set[str]:
    """Welche Ereignisse wirklich abonniert werden.

    Nicht nach dem Wort suchen -- eine Erwaehnung im Text zaehlt nicht.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            text = ast.unparse(deco)
            if "Cog.listener" in text or "add_listener" in text:
                found.add(node.name)
    return found


# --------------------------------------------------------------------- #
# 1. Jede Dashboard-Rolle sieht den Reiter
# --------------------------------------------------------------------- #


def test_every_role_sees_the_usage_tab():
    """Sonst ist der Reiter fuer fuenfunddreissig Rollen unsichtbar."""

    print("\nJede Dashboard-Rolle sieht den Usage-Reiter")

    from utils import dashboard_roles as roles

    admin = strip_ts_comments(
        dashboard_source("components", "dashboard", "admin-content.tsx")
    )

    match = re.search(r"usage:\s*\"([a-z_.]+)\"", admin)
    check("der Reiter verlangt eine Berechtigung", match is not None)
    if match is None:
        return

    required = match.group(1)
    without = [r for r in roles.ROLES if required not in r.permissions]

    # Der Tester ist die eine Ausnahme: sein Filter im Panel erkennt
    # ihn gerade daran, dass er ausser tester.access nichts hat.
    unexpected = [r.key for r in without if r.key != "tester"]

    check(
        f"jede Rolle ausser 'tester' hat {required}",
        not unexpected,
        f"ohne: {unexpected}",
    )
    check(
        "der Tester bekommt sie ausdruecklich NICHT",
        required not in roles.ROLES_BY_KEY["tester"].permissions,
        "sonst sieht er Reiter, die ihn nichts angehen",
    )


def test_the_tester_stays_narrow():
    """Die Grundausstattung darf den Tester nicht aufblaehen."""

    print("\nDer Tester bleibt eng")

    from utils import dashboard_roles as roles

    tester = roles.ROLES_BY_KEY["tester"]
    check(
        "er hat genau drei Berechtigungen",
        len(tester.permissions) == 3,
        f"hat: {sorted(tester.permissions)}",
    )
    check("darunter tester.access", "tester.access" in tester.permissions)
    check(
        "aber kein team.view",
        "team.view" not in tester.permissions,
        "der Reiter-Filter im Panel haengt genau daran",
    )

    # Und niemand sonst bekommt tester.access nebenbei.
    holders = {r.key for r in roles.ROLES if "tester.access" in r.permissions}
    check(
        "tester.access nur bei Tester, Co-Owner, Administrator",
        holders == {"tester", "co_owner", "administrator"},
        f"hat: {sorted(holders)}",
    )


# --------------------------------------------------------------------- #
# 2. Der Proxy laesst die Anfrage durch
# --------------------------------------------------------------------- #


def _admin_permission_keys(src: str) -> list[str]:
    """Die Schluessel aus ADMIN_PERMISSIONS.

    Die oeffnende Klammer wird hinter dem Gleichheitszeichen gesucht:
    die Typangabe ``Record<string, { GET?: string }>`` bringt eine
    eigene mit, und die Klammerbilanz waere sonst sofort wieder bei
    null.
    """

    start = src.index("const ADMIN_PERMISSIONS")
    brace = src.index("{", src.index("=", start))
    depth = 0
    block = ""
    for index in range(brace, len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                block = src[brace : index + 1]
                break

    return re.findall(r"^\s{2}\"?([a-z-]+)\"?:\s*\{", block, flags=re.M)


def test_the_proxy_allows_the_statistics():
    """Ohne Eintrag kommt nur ein globaler Admin durch."""

    print("\nDer Proxy laesst die Statistik durch")

    src = strip_ts_comments(
        dashboard_source("app", "api", "bot", "[...path]", "route.ts")
    )
    keys = _admin_permission_keys(src)

    check("command-stats steht in der Tabelle", "command-stats" in keys,
          f"drin sind: {keys}")

    # Und mit derselben Berechtigung wie der Reiter -- sonst sieht man
    # ihn und darf trotzdem nicht.
    match = re.search(r"\"command-stats\":\s*\{\s*GET:\s*\"([a-z_.]+)\"", src)
    check("und verlangt metrics.view",
          match is not None and match.group(1) == "metrics.view",
          match.group(1) if match else "kein GET-Eintrag")


def test_the_asker_is_named():
    """Ohne actor kann der Bot die Servernamen nicht maskieren."""

    print("\nDer Anfragende wird mitgeschickt")

    src = strip_ts_comments(
        dashboard_source("app", "api", "bot", "[...path]", "route.ts")
    )

    # Die Stelle muss den Endpunkt nennen *und* actor setzen -- beides
    # im selben Block, sonst gilt es fuer irgendetwas anderes.
    block = re.search(
        r"segments\[1\] === \"command-stats\"\)\s*\{([^}]*)\}", src
    )
    check("es gibt einen Zweig fuer command-stats", block is not None)
    if block is None:
        return

    body = block.group(1)
    check("er setzt actor", "searchParams.set(\"actor\"" in body)
    # Aus der Sitzung, nicht aus dem Browser.
    check("aus der Sitzung", "actorId" in body,
          "eine mitgeschickte ID waere frei waehlbar")


# --------------------------------------------------------------------- #
# 3. Slash-Befehle zaehlen mit
# --------------------------------------------------------------------- #


def test_slash_commands_are_counted():
    """`on_command_completion` feuert nur fuer Prefix-Befehle."""

    print("\nSlash-Befehle werden gezaehlt")

    src = strip_py_comments(source("cogs", "events", "feature_enforcement.py"))
    names = listener_names(src)

    check("Prefix-Befehle weiterhin", "on_command_completion" in names)
    check("Slash-Befehle jetzt auch", "on_app_command_completion" in names,
          "das Ereignis kommt aus CommandTree._call")

    # `on_app_command_error` gibt es NICHT: _dispatch_error ruft
    # tree.on_error direkt auf. Ein solcher Listener waere toter Code.
    check("kein toter Listener fuer Slash-Fehler",
          "on_app_command_error" not in names,
          "discord.py dispatcht dieses Ereignis nie")

    # Und jetzt die Wirkung, nicht nur die Anwesenheit: unter welchem
    # Namen wird gezaehlt? Landen Slash und Prefix im selben Topf, ist
    # die Trennung im Reiter wertlos -- man sieht dann nicht mehr, ob
    # jemand `/ban` oder `!ban` benutzt hat.
    #
    # Die Methode wird dafuer einzeln ausgefuehrt, ohne den Cog und
    # ohne discord.py: nur ihr eigener Rumpf zaehlt.
    node = next(
        (
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "on_app_command_completion"
        ),
        None,
    )
    if node is None:
        check("die Zaehlung laesst sich pruefen", False)
        return

    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    recorded: list[tuple] = []
    namespace: dict = {
        "command_stats": type(
            "Stub",
            (),
            {
                "record": staticmethod(
                    lambda *args, **kwargs: recorded.append((args, kwargs))
                ),
                "flush": staticmethod(lambda: asyncio.sleep(0)),
            },
        )()
    }
    exec(compile(ast.fix_missing_locations(module), "<mutation>", "exec"), namespace)

    class Guild:
        id = 4242

    class Command:
        qualified_name = "ban"

    class Interaction:
        guild = Guild()

    asyncio.run(namespace["on_app_command_completion"](None, Interaction(), Command()))

    check("es wird ueberhaupt gezaehlt", bool(recorded), "record() lief nie")
    if not recorded:
        return

    name = recorded[0][0][0]
    check("Slash-Befehle bekommen einen Schraegstrich",
          name == "/ban",
          f"abgelegt als {name!r} — dann sind Slash und Prefix derselbe Eintrag")
    check("die Server-ID wird mitgezaehlt",
          recorded[0][0][1] == 4242,
          str(recorded[0][0]))


def test_failed_slash_commands_are_counted():
    """Sonst steht jede Fehlerquote bei null."""

    print("\nFehlgeschlagene Slash-Befehle zaehlen mit")

    src = strip_py_comments(source("core", "universitybot.py"))
    tree = ast.parse(src)
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_count_failed_slash_commands"
        ),
        None,
    )
    check("es gibt den Einhaengepunkt", node is not None)
    if node is None:
        return

    body = ast.unparse(node)
    check("tree.on_error wird gesetzt", "tree.on_error = " in body)
    check("der vorhandene Handler laeuft weiter", "await original(" in body,
          "ohne ihn verschwaende die Fehlerausgabe von discord.py")
    check("mit failed=True gezaehlt", "failed=True" in body)
    check("und ein Riegel gegen doppeltes Einhaengen",
          "_usage_counter_installed" in body)

    # Er muss auch aufgerufen werden -- eine Methode, die niemand ruft,
    # ist wirkungslos.
    hook = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "setup_hook"
        ),
        None,
    )
    check("setup_hook ruft ihn auf",
          hook is not None
          and "_count_failed_slash_commands()" in ast.unparse(hook))

    # Und jetzt laufen lassen. Die Wortsuche oben faengt nicht, was
    # wirklich zaehlt: ob der Riegel greift. Zweimal eingehaengt wuerde
    # jeder Fehler doppelt gezaehlt -- die Fehlerquote im Reiter waere
    # dann schlicht falsch.
    module = ast.Module(body=[node], type_ignores=[])
    recorded: list[tuple] = []
    errors: list[str] = []
    namespace: dict = {}
    exec(compile(ast.fix_missing_locations(module), "<mutation>", "exec"), namespace)
    install = namespace["_count_failed_slash_commands"]

    import utils.command_stats as stats_module
    import utils.feature_services as services_module

    original_record = stats_module.record
    original_error = services_module.record_command_error
    stats_module.record = lambda *a, **k: recorded.append((a, k))
    services_module.record_command_error = lambda *a: errors.append(a)

    class Guild:
        id = 77

    class Command:
        qualified_name = "ban"

    class Interaction:
        command = Command()
        guild = Guild()

    original_calls: list = []

    class Tree:
        async def on_error(self, interaction, error):
            original_calls.append(error)

    class Bot:
        pass

    try:
        bot = Bot()
        bot.tree = Tree()

        install(bot)
        asyncio.run(bot.tree.on_error(Interaction(), ValueError("boom")))

        check("ein Fehler wird einmal gezaehlt",
              len(recorded) == 1,
              f"{len(recorded)}x gezaehlt")
        check("unter dem Slash-Namen",
              bool(recorded) and recorded[0][0][0] == "/ban",
              str(recorded[0][0]) if recorded else "nichts gezaehlt")
        check("der urspruengliche Handler lief wirklich",
              len(original_calls) == 1,
              f"{len(original_calls)}x aufgerufen")

        # Zweimal einhaengen darf nichts doppeln.
        install(bot)
        recorded.clear()
        original_calls.clear()
        asyncio.run(bot.tree.on_error(Interaction(), ValueError("noch mal")))

        check("zweimal einhaengen zaehlt trotzdem nur einmal",
              len(recorded) == 1,
              f"{len(recorded)}x gezaehlt — der Riegel greift nicht")
        check("und ruft den Handler nur einmal",
              len(original_calls) == 1,
              f"{len(original_calls)}x aufgerufen")
    finally:
        stats_module.record = original_record
        services_module.record_command_error = original_error


def test_the_total_includes_slash_commands():
    """`walk_commands()` allein kennt nur Prefix-Befehle."""

    print("\nDie Gesamtzahl enthaelt die Slash-Befehle")

    from utils import command_stats

    class Command:
        def __init__(self, name, hidden=False):
            self.qualified_name = name
            self.hidden = hidden

    class Group:
        qualified_name = "config"

        def walk_commands(self):
            return []

    class Tree:
        def walk_commands(self):
            return [Command("ban"), Command("help"), Group()]

    class Bot:
        tree = Tree()

        def walk_commands(self):
            return [Command("ban"), Command("prefix"), Command("geheim", True)]

    names = command_stats.all_command_names(Bot())

    check("Prefix-Befehle sind dabei", "ban" in names and "prefix" in names)
    check("Slash-Befehle mit Schraegstrich", "/ban" in names and "/help" in names)
    check("beide Wege bleiben getrennt",
          "ban" in names and "/ban" in names,
          "/ban und ban sind derselbe Befehl, aber nicht dieselbe Bedienung")
    check("versteckte bleiben draussen", "geheim" not in names)
    check("Gruppen zaehlen nicht mit", "/config" not in names,
          "eine Gruppe kann man nicht aufrufen -- sie waere fuer immer 'ungenutzt'")
    check("die Liste ist sortiert", names == sorted(names))

    # Ohne Baum darf nichts krachen: beim Start gibt es ihn noch nicht.
    class Bare:
        tree = None

        def walk_commands(self):
            return [Command("x")]

    try:
        bare = command_stats.all_command_names(Bare())
        check("ohne Baum geht es trotzdem", bare == ["x"], str(bare))
    except Exception as exc:
        check("ohne Baum geht es trotzdem", False, f"{type(exc).__name__}: {exc}")


def test_the_route_uses_the_shared_list():
    """Sonst zaehlt die Route wieder an der Statistik vorbei."""

    print("\nDie Route benutzt dieselbe Liste")

    src = strip_py_comments(source("api", "routes", "admin.py"))
    tree = ast.parse(src)
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "get_command_stats"
        ),
        None,
    )
    check("es gibt die Route", node is not None)
    if node is None:
        return

    body = ast.unparse(node)
    check("registered_commands kommt aus all_command_names",
          "all_command_names" in body)
    check("nicht mehr aus walk_commands allein",
          "bot.walk_commands()" not in body,
          "das kennt keine Slash-Befehle")


# --------------------------------------------------------------------- #
# 4. Die Servernamen sind fuer Fremde verdeckt
# --------------------------------------------------------------------- #


def test_guild_names_are_masked():
    """Die Statistik nennt sonst jeden Server, auf dem der Bot ist."""

    print("\nDie Servernamen sind verdeckt")

    from api.routes import admin as route
    from utils import command_stats
    from utils import dashboard_roles

    class Icon:
        url = "https://cdn.discordapp.com/icons/1/a.png"

    class Guild:
        def __init__(self, name):
            self.name = name
            self.icon = Icon()

    class Bot:
        def get_guild(self, guild_id):
            return Guild(f"Geheimer Server {guild_id}")

        def walk_commands(self):
            return []

        tree = None

    async def fake_summary(guild_id, days):
        return {
            "guilds": [
                {"guild_id": "123", "uses": 50},
                {"guild_id": "456", "uses": 10},
            ],
            "commands": [],
            "daily": [],
            "days": days,
            "total_uses": 60,
            "total_failures": 0,
            "unique_commands": 0,
        }

    async def fake_unused(bot, days):
        return []

    original_summary = command_stats.summary
    original_unused = command_stats.unused_commands
    original_is_owner = dashboard_roles.is_owner

    command_stats.summary = fake_summary
    command_stats.unused_commands = fake_unused
    dashboard_roles.is_owner = lambda uid: str(uid) == "1303627964734246944"

    try:
        # Als Owner: alles sichtbar.
        result = asyncio.run(
            route.get_command_stats(30, 0, "1303627964734246944", Bot())
        )
        check("der Owner sieht die Namen",
              result["guilds"][0]["guild_name"] == "Geheimer Server 123",
              str(result["guilds"][0]))
        check("und das Bild", bool(result["guilds"][0]["guild_icon"]))
        check("nichts ist maskiert", result["guilds_masked"] is False)

        # Als Team-Rolle: verdeckt.
        result = asyncio.run(route.get_command_stats(30, 0, "999", Bot()))
        check("eine Team-Rolle sieht nur Sternchen",
              all(g["guild_name"] == "•••••" for g in result["guilds"]),
              str(result["guilds"]))
        check("kein Bild", all(g["guild_icon"] is None for g in result["guilds"]))
        check("und keine ID",
              all(g["guild_id"] == "" for g in result["guilds"]),
              "mit der ID liesse sich der Server nachschlagen")
        check("die Zahlen bleiben aber stehen",
              [g["uses"] for g in result["guilds"]] == [50, 10],
              "genau um die geht es auf dieser Seite")
        check("und die Anzeige weiss davon",
              result["guilds_masked"] is True)

        # Ohne actor -- etwa ein direkter Aufruf mit dem API-Schluessel.
        result = asyncio.run(route.get_command_stats(30, 0, "", Bot()))
        check("ohne Anfragenden wird maskiert",
              result["guilds_masked"] is True
              and all(g["guild_name"] == "•••••" for g in result["guilds"]),
              "im Zweifel lieber ein Sternchen zu viel")
    finally:
        command_stats.summary = original_summary
        command_stats.unused_commands = original_unused
        dashboard_roles.is_owner = original_is_owner


# --------------------------------------------------------------------- #
# 5. Clan im Speedrun
# --------------------------------------------------------------------- #


_TEMPLATE_KEYS = [
    "community", "dev", "minimal", "music", "rp", "social", "anime",
    "business", "clan", "creator", "esports", "gaming", "study", "support",
]

# So wie der Template-Bot sie liefert: nach (premium, Name) sortiert.
_PREMIUM = {"anime", "business", "clan", "creator", "esports", "gaming",
            "study", "support"}


def _fake_templates() -> list[dict]:
    return [
        {"key": key, "premium": key in _PREMIUM, "name": key}
        for key in _TEMPLATE_KEYS
    ]


def test_clan_is_buildable_and_near_the_top():
    """Der Clan Server soll auswaehlbar sein -- ohne Premium."""

    print("\nClan ist waehlbar und steht weit oben")

    from api.routes import speedrun

    original_call = speedrun._call_template
    original_premium = speedrun._has_premium

    async def fake_call(method, path, *, payload=None, timeout=15):
        return 200, {"templates": _fake_templates()}

    speedrun._call_template = fake_call
    speedrun._has_premium = lambda _user: False

    try:
        answer = asyncio.run(speedrun.templates(user_id="123"))
        items = answer["templates"]
        by_key = {entry["key"]: entry for entry in items}
        order = [entry["key"] for entry in items]

        check("clan ist dabei", "clan" in by_key)
        check("und ohne Premium waehlbar",
              by_key["clan"]["available"] is True,
              f"gesperrt mit: {by_key['clan']['locked_reason']!r}")
        check("es bleibt eine Premium-Vorlage",
              by_key["clan"]["premium"] is True,
              "im Menue des Template-Bots gilt die Trennung weiter")

        # Die Position: der Template-Bot liefert clan an neunter
        # Stelle, hinter sieben gesperrten Kacheln.
        position = order.index("clan") + 1
        check("clan steht unter den ersten fuenf",
              position <= 5,
              f"steht an Position {position}: {order}")

        # Genauer: alles Baubare kommt zuerst.
        available = [entry["available"] for entry in items]
        check("nichts Gesperrtes steht vor etwas Baubarem",
              available == sorted(available, reverse=True),
              f"Reihenfolge: {order}")

        check("alle fuenf Beta-Vorlagen stehen vorn",
              set(order[:5]) == speedrun.BETA_TEMPLATES,
              f"vorn stehen: {order[:5]}")

        # Und die stabile Reihenfolge innerhalb der Gruppen bleibt.
        check("die freien Vorlagen behalten ihre Reihenfolge",
              order[:4] == ["community", "dev", "minimal", "music"],
              f"vorn stehen: {order[:4]}")
    finally:
        speedrun._call_template = original_call
        speedrun._has_premium = original_premium


def test_the_beta_note_is_not_hard_coded():
    """Der Reiter behauptete „erst eine Vorlage“, waehrend fuenf offen waren."""

    print("\nDer Hinweistext nennt die richtige Zahl")

    src = strip_ts_comments(
        dashboard_source("components", "dashboard", "speedrun-panel.tsx")
    )

    check("es gibt eine gezaehlte Liste",
          "openTemplates" in src,
          "sonst steht die Zahl fest im Text")
    check("sie kommt aus der Antwort",
          "const openTemplates = templates.filter((t) => t.available)" in src,
          "sie muss aus den geladenen Vorlagen entstehen")
    check("die alte feste Behauptung ist weg",
          "ist erst eine Vorlage freigegeben — auch mit" not in src)

    # Und jetzt die Wirkung: der Text muss dieselbe Liste benutzen, die
    # oben berechnet wurde. `[].length` wuerde den Wortlaut oben
    # unveraendert lassen und trotzdem immer null anzeigen.
    #
    # Dafuer wird der Absatz um den Text herum ausgeschnitten und
    # geprueft, worauf `.length` dort steht.
    paragraph = re.search(
        r"In der Beta (?:ist|sind)[\s\S]{0,400}?freigegeben", src
    )
    check("der Hinweis steht im Reiter", paragraph is not None)
    if paragraph is None:
        return

    # Der Ausdruck davor -- die Bedingung, die zwischen Einzahl und
    # Mehrzahl entscheidet.
    start = max(0, paragraph.start() - 200)
    around = src[start : paragraph.end() + 200]

    # Nur der Bezeichner, ohne die JSX-Klammern davor: in `{openTemplates`
    # und `${openTemplates` gehoert das `{` bzw. `${` zur Einbettung.
    lengths = re.findall(r"([A-Za-z_$][\w$]*|\[\])\.length", around)
    check("die Zahl kommt aus openTemplates",
          lengths and all(name == "openTemplates" for name in lengths),
          f"gezaehlt wird: {lengths}")
    check("und nicht aus einer leeren Liste",
          "[].length" not in around,
          "dann stuende dort fuer immer null")


def test_free_premium_templates_are_marked():
    """Sonst sieht man dem Clan nicht an, was man gerade umsonst bekommt."""

    print("\nFreigeschaltete Premium-Vorlagen sind erkennbar")

    src = strip_ts_comments(
        dashboard_source("components", "dashboard", "speedrun-panel.tsx")
    )

    check("es gibt eine Kennzeichnung",
          "Premium frei" in src)
    # Und zwar genau fuer offene Premium-Vorlagen -- nicht fuer jede.
    check("nur bei offenen Premium-Vorlagen",
          "!locked && template.premium" in src,
          "eine gesperrte traegt das Schloss, nicht diesen Hinweis")


# --------------------------------------------------------------------- #
# 6. Join to Create -- das Versprechen muss halten
# --------------------------------------------------------------------- #


def test_the_handover_step_needs_a_channel():
    """Der Schritt haengt an channels.j2c -- das darf nicht wegfallen."""

    print("\nJoin to Create braucht seinen Kanal")

    from utils import speedrun_handover as handover

    check("der Schritt existiert", "j2c" in handover.STEPS)
    check("und verlangt einen Kanal",
          "channels.j2c" in handover.STEPS["j2c"]["needs"],
          f"verlangt: {handover.STEPS['j2c']['needs']}")

    # Ohne Kanal muss er als fehlend gemeldet werden, nicht still
    # durchlaufen.
    missing = handover.missing_for("j2c", {"channels": {"j2c": None}})
    check("ohne Kanal wird er uebersprungen",
          missing == ["channels.j2c"],
          f"gemeldet: {missing}")

    present = handover.missing_for("j2c", {"channels": {"j2c": "123"}})
    check("mit Kanal laeuft er", present == [], f"gemeldet: {present}")


def main() -> int:
    test_every_role_sees_the_usage_tab()
    test_the_tester_stays_narrow()
    test_the_proxy_allows_the_statistics()
    test_the_asker_is_named()
    test_slash_commands_are_counted()
    test_failed_slash_commands_are_counted()
    test_the_total_includes_slash_commands()
    test_the_route_uses_the_shared_list()
    test_guild_names_are_masked()
    test_clan_is_buildable_and_near_the_top()
    test_the_beta_note_is_not_hard_coded()
    test_free_premium_templates_are_marked()
    test_the_handover_step_needs_a_channel()

    print()
    if failures:
        print(f"{len(failures)} failures")
        for entry in failures:
            print(f"  - {entry}")
        return 1

    print("0 failures, 0 skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
