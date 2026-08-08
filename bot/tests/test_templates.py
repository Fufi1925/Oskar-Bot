#!/usr/bin/env python3
"""
Community-Vorlagen: scannen, teilen, anwenden.

Ein Server laesst sich einlesen -- Kanaele, Rollen, Rechte und die
Dashboard-Einstellungen -- und als Vorlage veroeffentlichen. Andere
holen sie sich auf ihren Server.

Drei Dinge sind hier wirklich gefaehrlich, und danach ist dieser Test
sortiert:

  1. **Eine Vorlage ist oeffentlich.** Steht darin eine
     Webhook-Adresse, kann jeder, der sie sieht, in diesen Kanal
     schreiben -- eine Webhook-URL *ist* das Zugangsrecht.
  2. **Ein Zugangscode, dessen Inhalt man auch ohne ihn sieht, ist
     keiner.**
  3. **"Alles loeschen" ist endgueltig.** Discord kennt keinen
     Papierkorb.

Run:  python3 tests/test_templates.py
"""

import ast
import asyncio
import json
import os
import re
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


def read_dash(*parts) -> str:
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_ts(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def strip_py(src: str) -> str:
    """Kommentare und Docstrings raus.

    In den Dateien stehen die Gefahren woertlich beschrieben --
    inklusive Beispiel-Webhooks und Token-Mustern. Ohne Strippen
    faende eine Suche nach "webhook" die Erklaerung und meldete ein
    Leck, das es nicht gibt.
    """
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
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


async def _with_db(func):
    """Eine echte SQLite-Datei -- die Abfragen sollen wirklich laufen."""

    import aiosqlite

    from utils import template_store as store

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            return await func(db, store)
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ #
# 1. Nichts Geheimes darf hinaus
# ------------------------------------------------------------------ #
def test_secrets_never_reach_a_template():
    """Der wichtigste Test der Datei.

    Eine hochgeladene Vorlage ist oeffentlich. Was hier durchrutscht,
    steht fuer jeden lesbar in der Community-Liste.
    """
    print("\nZugangsdaten kommen nicht in die Vorlage")

    from utils import template_store as store

    raw = {
        "welcome_channel_id": 1530378233579704370,
        "log_webhook": "https://discord.com/api/webhooks/123456/abcDEF-xyz",
        "text": "Hallo <#1530378233579704370>, frag <@1303627964734246944>",
        # Bewusst unter einem HARMLOSEN Schluessel. Ein Feld namens
        # "bot_token" faellt schon der Schluessel-Liste zum Opfer --
        # damit prueft man die Muster gar nicht. Genau daran ist diese
        # Pruefung beim Mutationstest vorbeigelaufen.
        "notiz": "Zugang: MTUzMDM0OTIwNTM3MjE0NTcxNQ.GFBveZ.2Sf2aje1G6wgGpcs1VxuZHOMfuI-irq4y-YIas",
        "einladung": "https://discord.gg/MG3rYnUZJV",
        "nested": {"api_key": "geheim123", "harmlos": "bleibt"},
        "liste": ["https://discord.com/api/webhooks/9/zzz", "normaler Text"],
        "level": 5,
        "farbe": "#5865f2",
    }
    labels = {
        1530378233579704370: "channel:allgemein",
        1303627964734246944: "role:Admin",
    }
    clean = store.sanitise(raw, labels)
    blob = json.dumps(clean, ensure_ascii=False)

    check("die Webhook-Adresse ist weg", "webhooks/123456" not in blob)
    check("auch die in der Liste", "webhooks/9" not in blob)
    check("der Bot-Token ist weg", "GFBveZ" not in blob)
    check(
        "auch unter harmlosem Feldnamen",
        "2Sf2aje1G6wgGpcs1VxuZHOMfuI" not in blob,
        "das Muster muss greifen, nicht nur die Schluessel-Liste",
    )
    check("die Einladung ist weg", "discord.gg/MG3rYnUZJV" not in blob)
    check("der api_key ist weg", "geheim123" not in blob)

    check(
        "die Kanal-ID wurde zum Platzhalter",
        clean["welcome_channel_id"] == "{channel:allgemein}",
        str(clean.get("welcome_channel_id")),
    )
    check(
        "auch mitten im Text",
        "{channel:allgemein}" in clean["text"] and "{role:Admin}" in clean["text"],
        clean.get("text", ""),
    )

    check("harmlose Werte bleiben", clean.get("level") == 5)
    check("Farben auch", clean.get("farbe") == "#5865f2")
    check("und harmlose Texte", clean["nested"].get("harmlos") == "bleibt")

    # Ein Fall, den weder die Schluessel-Liste noch ein Muster in der
    # Route abfaengt: ein Webhook mitten in einem Kanalthema. Nur die
    # rekursive Bereinigung sieht das.
    deep = store.sanitise(
        {
            "channels": [
                {
                    "name": "logs",
                    "topic": "Meldungen an "
                    "https://discord.com/api/webhooks/77/geheim",
                }
            ]
        },
        {},
    )
    check(
        "auch tief verschachtelt",
        "webhooks/77" not in json.dumps(deep, ensure_ascii=False),
        "die Bereinigung muss rekursiv laufen",
    )

    # Die Gegenprobe muss anschlagen, wenn doch etwas durchkommt.
    check("die Gegenprobe erkennt das Original", store.contains_secret(raw))
    check("und gibt beim Bereinigten Entwarnung", not store.contains_secret(clean))


def test_an_id_as_a_number_is_caught_too():
    """Sonst reichte es, die ID als Zahl statt als Text abzulegen."""
    print("\nAuch eine ID als Zahl wird ersetzt")

    from utils import template_store as store

    clean = store.sanitise({"role_id": 1303627964734246944}, {})
    check(
        "unbekannte ID wird zu {id}",
        clean["role_id"] == "{id}",
        str(clean["role_id"]),
    )

    # Kleine Zahlen sind Zaehler, keine IDs -- sie muessen bleiben.
    keep = store.sanitise({"xp": 12345, "jahr": 2026, "farbe": 5793266}, {})
    check("kleine Zahlen bleiben", keep == {"xp": 12345, "jahr": 2026, "farbe": 5793266})


def test_the_upload_refuses_when_something_slips_through():
    """Lieber eine Fehlermeldung als ein Leck."""
    print("\nDer Upload lehnt ab, wenn noch etwas drinsteht")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"), encoding="utf-8").read()
    )

    check("es gibt die Gegenprobe", "store.contains_secret(clean)" in route)
    guarded = re.search(
        r"if store\.contains_secret\(clean\):[\s\S]{0,400}?raise HTTPException", route
    )
    check(
        "und sie bricht ab",
        bool(guarded),
        "ohne raise wuerde trotzdem veroeffentlicht",
    )

    # Bereinigt wird VOR dem Speichern, nicht beim Anzeigen.
    check(
        "bereinigt wird vor dem Speichern",
        route.index("store.sanitise(payload, labels)")
        < route.index("store.create_template"),
        "was gespeichert ist, kann versehentlich ausgeliefert werden",
    )

    # BEIDE Stellen einzeln pruefen -- Scan und Upload.
    #
    # `store.sanitise` kommt zweimal vor. Eine Suche ueber die ganze
    # Datei blieb gruen, als die Bereinigung im Scan durch
    # `clean = payload` ersetzt wurde: die andere Stelle enthielt den
    # Aufruf ja noch. Der Scan liefert aber die Vorschau ans
    # Dashboard -- dort waeren die Geheimnisse genauso sichtbar.
    for part, label in (
        ("async def scan", "Scan"),
        ("async def upload", "Upload"),
    ):
        block = route.split(part)[1].split("@router.")[0]
        assigned = re.search(r"clean\s*=\s*store\.sanitise\(", block)
        check(
            f"{label}: das Ergebnis wird uebernommen",
            bool(assigned),
            "»clean = payload« umgeht die Bereinigung vollstaendig",
        )
        # Und das Rohe darf danach nicht mehr weitergereicht werden.
        #
        # `payload=clean` ist dabei in Ordnung -- das ist der
        # Parametername der Speicherfunktion, nicht die rohe Variable.
        # Gesucht wird `payload` als *Wert*, also am Zeilenende oder
        # vor einem Komma ohne Zuweisung davor.
        # Ab dem ENDE der Zuweisungszeile suchen -- in ihr selbst
        # steht `sanitise(payload, ...)`, und das ist ja gerade
        # richtig.
        start = block.index("\n", assigned.end()) if assigned else 0
        after = block[start:]
        leaked = re.findall(r"(?<![=\w])payload(?=[\s,)\]])", after)
        check(
            f"{label}: danach wird nur noch das Bereinigte benutzt",
            not leaked,
            f"das Rohe wird {len(leaked)}x weitergereicht",
        )
    check(
        "gespeichert wird das Bereinigte",
        re.search(r"payload=clean", route) is not None,
        "sonst landet das Rohe in der Datenbank",
    )


# ------------------------------------------------------------------ #
# 2. Der Zugangscode
# ------------------------------------------------------------------ #
def test_a_locked_template_hides_its_preview():
    """Ein Code, dessen Inhalt man auch ohne ihn sieht, ist keiner."""
    print("\nOhne Code keine Vorschau")

    async def body(db, store):
        payload = {
            "channels": [{"name": "geheim-kanal"}],
            "roles": [{"name": "Geheimrolle"}],
        }
        template_id, key = await store.create_template(
            db,
            name="Verschlossen",
            description="sichtbar",
            author_id=1,
            author_name="Wer",
            source_guild_id=111,
            payload=payload,
            visibility="key",
        )

        check("ein Code wurde erzeugt", bool(key) and len(key) >= 8, str(key))

        locked = await store.get_template(db, template_id)
        check("ohne Code gilt sie als verschlossen", locked["locked"] is True)
        check("die Vorschau ist leer", locked["payload"] == {})
        check(
            "und die Zahlen verraten nichts",
            locked["summary"]["channels"] == 0,
            str(locked["summary"]),
        )
        check("Name und Beschreibung bleiben sichtbar", locked["name"] == "Verschlossen")

        # Der Kanalname darf nirgends auftauchen.
        blob = json.dumps(locked, ensure_ascii=False)
        check("kein Kanalname durchgesickert", "geheim-kanal" not in blob)
        check("kein Rollenname durchgesickert", "Geheimrolle" not in blob)

        wrong = await store.get_template(db, template_id, key="FALSCH99")
        check("ein falscher Code oeffnet nicht", wrong["locked"] is True)

        right = await store.get_template(db, template_id, key=key)
        check("der richtige oeffnet", right["locked"] is False)
        check("und zeigt die Kanaele", right["summary"]["channels"] == 1)

        # Kleinschreibung soll auch gehen -- niemand tippt Codes gern.
        lower = await store.get_template(db, template_id, key=key.lower())
        check("Gross- und Kleinschreibung egal", lower["locked"] is False)

        own = await store.get_template(db, template_id, owner_guild_id=111)
        check("der eigene Server sieht sie immer", own["locked"] is False)

    asyncio.run(_with_db(body))


def test_the_key_is_not_stored_in_the_clear():
    """Wer die Datenbank liest, soll keine Vorlagen oeffnen koennen."""
    print("\nDer Code liegt nur als Pruefsumme")

    async def body(db, store):
        template_id, key = await store.create_template(
            db,
            name="X",
            description="",
            author_id=None,
            author_name="",
            source_guild_id=1,
            payload={},
            visibility="key",
        )
        async with db.execute(
            "SELECT key_hash FROM templates WHERE id = ?", (template_id,)
        ) as cursor:
            row = await cursor.fetchone()

        stored = row[0]
        check("der Klartext steht nicht drin", stored != key, "im Klartext gespeichert")
        check("es ist ein SHA-256", len(stored) == 64)
        check("und passt zum Code", stored == store.hash_key(key))

    asyncio.run(_with_db(body))


def test_the_key_alphabet_avoids_lookalikes():
    """I/O/0/1 verwechselt man beim Abtippen."""
    print("\nDer Code ist vorlesbar")

    from utils import template_store as store

    for bad in "IO01":
        check(f"kein »{bad}« im Alphabet", bad not in store.KEY_ALPHABET)

    keys = {store.make_key() for _ in range(200)}
    check("die Codes wiederholen sich nicht", len(keys) > 190, str(len(keys)))


# ------------------------------------------------------------------ #
# 3. Fremde Vorlagen
# ------------------------------------------------------------------ #
def test_templates_belong_to_their_guild():
    """Die IDs sind fortlaufend und damit trivial zu raten."""
    print("\nNur die eigenen Vorlagen sind loeschbar")

    async def body(db, store):
        mine, _ = await store.create_template(
            db, name="Meine", description="", author_id=None, author_name="",
            source_guild_id=111, payload={}, visibility="public",
        )
        await store.create_template(
            db, name="Fremde", description="", author_id=None, author_name="",
            source_guild_id=222, payload={}, visibility="public",
        )

        check("fremdes Loeschen scheitert", not await store.delete_template(db, mine, 222))
        check("die Vorlage steht noch", (await store.get_template(db, mine)) is not None)
        check("eigenes Loeschen geht", await store.delete_template(db, mine, 111))

        own = await store.list_own(db, 222)
        check("die eigene Liste zeigt nur eigene", [t["name"] for t in own] == ["Fremde"])

        # Gegenprobe mit einem Server ohne Vorlagen: kommt hier etwas
        # zurueck, filtert die Abfrage gar nicht. Ohne diese Probe
        # blieb der Test gruen, obwohl `WHERE source_guild_id` fehlte
        # -- die erste Liste hatte zufaellig nur einen Treffer.
        none = await store.list_own(db, 999)
        check(
            "ein fremder Server sieht nichts",
            none == [],
            f"{len(none)} fremde Vorlagen sichtbar",
        )

    asyncio.run(_with_db(body))


def test_search_and_sort_work():
    print("\nSuche und Sortierung")

    async def body(db, store):
        for name in ("Gaming Server", "Musik Ecke", "Lern-Gruppe"):
            await store.create_template(
                db, name=name, description=f"Beschreibung von {name}",
                author_id=None, author_name="", source_guild_id=1,
                payload={}, visibility="public",
            )

        found = await store.list_templates(db, search="Gaming")
        check("Suche nach dem Namen", [t["name"] for t in found] == ["Gaming Server"])

        found = await store.list_templates(db, search="Beschreibung von Musik")
        check("Suche in der Beschreibung", len(found) == 1, str(len(found)))

        by_name = await store.list_templates(db, sort="name")
        check(
            "nach Namen sortiert",
            [t["name"] for t in by_name]
            == ["Gaming Server", "Lern-Gruppe", "Musik Ecke"],
            str([t["name"] for t in by_name]),
        )

    asyncio.run(_with_db(body))


# ------------------------------------------------------------------ #
# 4. Der Scanner
# ------------------------------------------------------------------ #
def test_the_scanner_skips_what_cannot_be_rebuilt():
    """@everyone und Bot-Rollen gibt es auf jedem Server schon."""
    print("\nDer Scanner laesst weg, was nicht nachbaubar ist")

    from utils import template_scan as scan

    class FakePerms:
        def __init__(self, names):
            self.names = names

        def __iter__(self):
            return iter([(n, True) for n in self.names])

    class FakeRole:
        def __init__(self, name, *, default=False, managed=False, position=1):
            self.name = name
            self.colour = 0
            self.hoist = False
            self.mentionable = False
            self.permissions = FakePerms(["send_messages"])
            self.position = position
            self._default = default
            self.managed = managed

        def is_default(self):
            return self._default

    class FakeGuild:
        id = 1
        name = "Test"
        member_count = 5
        roles = [
            FakeRole("@everyone", default=True, position=0),
            FakeRole("BotRolle", managed=True, position=1),
            FakeRole("Moderator", position=2),
        ]
        channels = []
        categories = []

    roles = scan.scan_roles(FakeGuild())
    names = [r["name"] for r in roles]
    check("@everyone faellt weg", "@everyone" not in names)
    check("Bot-Rollen fallen weg", "BotRolle" not in names)
    check("normale Rollen bleiben", "Moderator" in names, str(names))
    check("die Rechte stehen als Namen da", roles[0]["permissions"] == ["send_messages"])


def test_permissions_are_names_not_numbers():
    """Eine Zahl wie 137411140374080 kann niemand pruefen."""
    print("\nRechte stehen als Namen in der Vorlage")

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_scan.py"), encoding="utf-8").read()
    )
    check("es gibt die Umwandlung", "_permission_names" in src)
    check("nur gesetzte Rechte", "if value:" in src)

    apply_src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"), encoding="utf-8").read()
    )
    check("beim Anwenden zurueckuebersetzt", "_perms_from_names" in apply_src)
    check(
        "unbekannte Namen werden uebersprungen",
        "if name in valid" in apply_src,
        "Discord benennt Rechte gelegentlich um",
    )


def test_placeholders_survive_a_round_trip():
    """`{channel:name}` muss wieder eine echte ID werden."""
    print("\nPlatzhalter finden zurueck")

    from utils import template_apply as applier

    class FakeChannel:
        def __init__(self, cid, name):
            self.id = cid
            self.name = name

    class FakeRole:
        def __init__(self, rid, name):
            self.id = rid
            self.name = name

    class FakeGuild:
        channels = [FakeChannel(500, "allgemein")]
        roles = [FakeRole(600, "Moderator")]
        default_role = FakeRole(1, "@everyone")

    guild = FakeGuild()

    check(
        "ein Kanal-Platzhalter wird zur ID",
        applier.resolve_placeholders("{channel:allgemein}", guild) == 500,
    )
    check(
        "ein Rollen-Platzhalter auch",
        applier.resolve_placeholders("{role:Moderator}", guild) == 600,
    )
    check(
        "unbekannt bleibt None",
        applier.resolve_placeholders("{channel:gibtsnicht}", guild) is None,
        "eine fremde ID waere schlimmer als keine",
    )

    # Mitten im Text wird eine Erwaehnung daraus.
    text = applier.resolve_placeholders(
        "Willkommen in {channel:allgemein}, frag {role:Moderator}", guild
    )
    check("im Text wird es eine Erwaehnung", "<#500>" in text and "<@&600>" in text, text)

    # Und verschachtelt.
    nested = applier.resolve_placeholders(
        {"a": ["{channel:allgemein}"], "b": {"c": "{role:Moderator}"}}, guild
    )
    check("auch verschachtelt", nested["a"][0] == 500 and nested["b"]["c"] == 600)


# ------------------------------------------------------------------ #
# 5. Das Anwenden -- der gefaehrliche Teil
# ------------------------------------------------------------------ #
def test_the_precheck_actually_stops_the_run():
    """Pruefen allein genuegt nicht -- es muss abbrechen.

    `problems = []` liesse den Aufruf stehen und machte trotzdem
    weiter. Genau so ist diese Mutation entwischt: geprueft wurde nur,
    DASS `precheck` gerufen wird, nicht dass sein Ergebnis zaehlt.
    """
    print("\nEine fehlgeschlagene Pruefung bricht ab")

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"), encoding="utf-8").read()
    )
    block = src.split("async def apply_template")[1]

    called = re.search(r"problems\s*=\s*await precheck\(", block)
    check("precheck wird gerufen", bool(called))

    stops = re.search(
        r"if problems:[\s\S]{0,200}?return report\.as_dict\(\)", block
    )
    check(
        "und sein Ergebnis beendet den Lauf",
        bool(stops),
        "ohne das wird trotz fehlender Rechte angefangen",
    )

    # Und wirklich ausfuehren: ohne Rechte darf nichts angelegt werden.
    from utils import template_apply as applier

    class NoPerms:
        manage_channels = False
        manage_roles = False

    class FakeRole:
        position = 5

    class FakeMe:
        guild_permissions = NoPerms()
        top_role = FakeRole()

    class FakeGuild:
        id = 1
        me = FakeMe()
        roles: list = []
        channels: list = []

        async def create_role(self, **_kw):
            raise AssertionError("darf nicht angelegt werden")

    async def go():
        report = await applier.apply_template(
            FakeGuild(), {"roles": [{"name": "X"}]}, {"roles": True}
        )
        check("der Lauf meldet Fehler", report["ok"] is False)
        check(
            "und hat nichts angelegt",
            report["created"] == [],
            "es wurde trotz fehlender Rechte gebaut",
        )

    asyncio.run(go())


def test_it_checks_before_it_touches_anything():
    """Ein halb aufgesetzter Server ist schlimmer als keiner."""
    print("\nErst pruefen, dann anfassen")

    from utils import template_apply as applier

    class FakePerms:
        def __init__(self, channels=True, roles=True):
            self.manage_channels = channels
            self.manage_roles = roles

    class FakeRole:
        def __init__(self, position):
            self.position = position

    class FakeMe:
        def __init__(self, perms, position=5):
            self.guild_permissions = perms
            self.top_role = FakeRole(position)

    class FakeGuild:
        def __init__(self, me):
            self.me = me
            self.roles = []
            self.channels = []

    async def go():
        # Alles in Ordnung.
        ok = FakeGuild(FakeMe(FakePerms()))
        check("mit Rechten keine Einwaende", await applier.precheck(ok, {}, wipe=False) == [])

        # Ohne Kanalrecht.
        bad = FakeGuild(FakeMe(FakePerms(channels=False)))
        problems = await applier.precheck(bad, {}, wipe=False)
        check("fehlendes Kanalrecht wird gemeldet", any("Kanäle" in p for p in problems))

        # Rolle ganz unten.
        low = FakeGuild(FakeMe(FakePerms(), position=1))
        problems = await applier.precheck(low, {}, wipe=False)
        check(
            "zu niedrige Bot-Rolle wird gemeldet",
            any("ganz unten" in p for p in problems),
            str(problems),
        )

    asyncio.run(go())


def test_wiping_spares_what_must_stay():
    """Discord verbietet das Loeschen der Pflichtkanaele.

    Und die eigene Rolle des Bots kann er ohnehin nicht entfernen --
    der Versuch endet mitten im Lauf mit einem Fehler.
    """
    print("\nBeim Leeren bleibt stehen, was bleiben muss")

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"), encoding="utf-8").read()
    )

    check("Pflichtkanaele werden verschont", "_protected_channels" in src)
    for attribute in ("rules_channel", "public_updates_channel", "system_channel"):
        check(f"{attribute} steht auf der Liste", attribute in src)

    wipe = src.split("async def wipe_server")[1].split("async def ")[0]
    check("verwaltete Rollen bleiben", 'getattr(role, "managed", False)' in wipe)
    check("@everyone bleibt", "is_default" in wipe)
    check(
        "Rollen ueber dem Bot bleiben",
        "my_top" in wipe,
        "der Bot kann sie gar nicht loeschen",
    )


def test_deleting_needs_the_server_name():
    """Ein Fehlklick darf nicht reichen."""
    print("\nLoeschen verlangt den Servernamen")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"), encoding="utf-8").read()
    )

    block = route.split('if options["wipe"]:')[1].split("report =")[0]
    check("der Name wird verlangt", "confirm" in block)
    check("und verglichen", "guild.name" in block)
    guarded = re.search(r"!=\s*guild\.name[\s\S]{0,200}?raise HTTPException", block)
    check("bei Abweichung wird abgebrochen", bool(guarded))


def test_the_apply_survives_a_single_failure():
    """Ein Kanal, der nicht geht, darf nicht fuenfzig verhindern."""
    print("\nEin Fehlschlag beendet nicht den ganzen Lauf")

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"), encoding="utf-8").read()
    )

    for part in ("apply_roles", "apply_channels"):
        block = src.split(f"async def {part}")[1].split("async def ")[0]
        check(
            f"{part} sammelt Fehler",
            "report.errors.append" in block,
            "statt abzubrechen",
        )

    check("es gibt einen Bericht", "class Report" in src)
    check("mit Angelegtem, Geloeschtem und Fehlern",
          all(w in src for w in ("created", "deleted", "errors", "skipped")))


def test_roles_come_before_channels():
    """Kanalrechte verweisen auf Rollen.

    Andersherum zeigten sie ins Leere und muessten hinterher
    nachgetragen werden -- zwei Durchlaeufe statt einem.
    """
    print("\nRollen zuerst, dann Kanaele")

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"), encoding="utf-8").read()
    )
    block = src.split("async def apply_template")[1]
    check(
        "die Reihenfolge stimmt",
        block.index("apply_roles") < block.index("apply_channels"),
    )
    check(
        "und die Rollen werden weitergereicht",
        "apply_channels(guild, working, roles" in block,
    )

    # Der Aufruf muss auch ERREICHBAR sein. `if False:` liesse
    # `apply_roles` im Code stehen und legte trotzdem keine Rollen an
    # -- die Kanalrechte zeigten dann ins Leere.
    reachable = re.search(
        r'if options\.get\("roles", True\):\s*\n[\s\S]{0,200}?await self\.apply_roles|'
        r'if options\.get\("roles", True\):\s*\n[\s\S]{0,200}?roles = await apply_roles',
        block,
    )
    check(
        "und der Aufruf haengt an der Option, nicht an False",
        bool(reachable),
        "»if False« schaltet die Rollen stumm ab",
    )


# ------------------------------------------------------------------ #
# 6. Die Verdrahtung
# ------------------------------------------------------------------ #
def test_the_routes_are_registered():
    print("\nDie Routen sind angemeldet")

    from fastapi.testclient import TestClient

    from api.server import create_app

    client = TestClient(create_app())
    answer = client.get("/api/v1/openapi.json")
    check("openapi ist lesbar", answer.status_code == 200)
    if answer.status_code != 200:
        return

    paths = set(answer.json()["paths"])
    for path in (
        "/templates/{guild_id}/scan",
        "/templates/{guild_id}/upload",
        "/templates/{guild_id}/list",
        "/templates/{guild_id}/preview",
        "/templates/{guild_id}/apply",
    ):
        check(f"{path} gibt es", path in paths)


def test_the_proxy_knows_the_scope():
    """Ohne Zweig kaeme 404 »Unknown API scope«.

    Genau dieser Fehler ist hier schon dreimal passiert.
    """
    print("\nDer Proxy kennt den Bereich")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    check("es gibt den Zweig", 'scope === "templates"' in proxy)

    block = proxy.split('scope === "templates"')[1].split("if (scope ===")[0]
    check("Nichtangemeldete kommen nicht durch", "Not signed in" in block)
    check("Schreiben verlangt mehr als Lesen", "settings.edit" in block)


def test_the_dashboard_is_wired_up():
    print("\nDas Dashboard ist verdrahtet")

    api_src = strip_ts(read_dash("lib", "api.ts"))
    for name in (
        "templateScan:", "templateUpload:", "templateList:",
        "templateDetail:", "templateDelete:", "templatePreview:",
        "templateApply:",
    ):
        check(f"{name} gibt es", name in api_src)

    for page in ("template-upload", "templates"):
        check(
            f"die Seite {page} gibt es",
            bool(read_dash("app", "dashboard", "guild", "[guildId]", page, "page.tsx")),
        )

    layout = strip_ts(read_dash("app", "dashboard", "layout.tsx"))
    check("die Kategorie Templates gibt es", 'name: "Templates"' in layout)
    check("Speedrun steht darin", "/speedrun`" in layout)
    check("Hochladen auch", "/template-upload`" in layout)
    check("und die Community-Liste", "/templates`" in layout)

    # Speedrun darf nicht mehr unter Verwaltung stehen.
    admin = layout.split('name: "Verwaltung"')[1].split("],")[0]
    check(
        "Speedrun ist aus der Verwaltung raus",
        "/speedrun`" not in admin,
        "sonst steht er doppelt",
    )


def test_both_tabs_are_marked_experimental():
    """So gewuenscht -- und ehrlich: das System ist neu."""
    print("\nBeide Reiter sind als experimentell gekennzeichnet")

    for page in ("template-upload", "templates"):
        src = read_dash("app", "dashboard", "guild", "[guildId]", page, "page.tsx")
        check(f"{page} sagt es", "Experimentell" in src)


def test_the_delay_before_wiping():
    """Acht Sekunden, in denen man noch einmal liest."""
    print("\nDer Loesch-Knopf ist gesperrt")

    panel = strip_ts(read_dash("components", "dashboard", "template-community-panel.tsx"))

    check("es gibt eine Wartezeit", "WIPE_DELAY_SECONDS" in panel)
    found = re.search(r"WIPE_DELAY_SECONDS\s*=\s*(\d+)", panel)
    seconds = int(found.group(1)) if found else 0
    check("sie betraegt 8 Sekunden", seconds == 8, f"-> {seconds}")

    # Die Sperre muss im `disabled` des Knopfes stehen -- nicht bloss
    # irgendwo. Sie kommt auch in der Beschriftung vor; eine Suche
    # ueber die ganze Datei blieb deshalb gruen, obwohl der Knopf
    # klickbar war.
    disabled = re.search(r"disabled=\{([\s\S]{0,400}?)\}\s*\n\s*onClick=\{runApply",
                         panel)
    check(
        "der Knopf ist so lange gesperrt",
        bool(disabled) and "countdown > 0" in disabled.group(1),
        "die Wartezeit steht nur in der Beschriftung, nicht im disabled",
    )
    check(
        "und ohne Pruefung geht er gar nicht",
        bool(disabled) and "!preview" in disabled.group(1),
        "sonst liesse sich ungeprueft loeschen",
    )
    check("der Servername wird verlangt", "confirmName" in panel)
    check(
        "und geprueft",
        "confirmName.trim().toLowerCase()" in panel,
        "sonst waere das Feld Zierde",
    )
    check("der Knopf ist rot", "bg-red-500/15" in panel)


def main() -> int:
    test_secrets_never_reach_a_template()
    test_an_id_as_a_number_is_caught_too()
    test_the_upload_refuses_when_something_slips_through()
    test_a_locked_template_hides_its_preview()
    test_the_key_is_not_stored_in_the_clear()
    test_the_key_alphabet_avoids_lookalikes()
    test_templates_belong_to_their_guild()
    test_search_and_sort_work()
    test_the_scanner_skips_what_cannot_be_rebuilt()
    test_permissions_are_names_not_numbers()
    test_placeholders_survive_a_round_trip()
    test_the_precheck_actually_stops_the_run()
    test_it_checks_before_it_touches_anything()
    test_wiping_spares_what_must_stay()
    test_deleting_needs_the_server_name()
    test_the_apply_survives_a_single_failure()
    test_roles_come_before_channels()
    test_the_routes_are_registered()
    test_the_proxy_knows_the_scope()
    test_the_dashboard_is_wired_up()
    test_both_tabs_are_marked_experimental()
    test_the_delay_before_wiping()

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
