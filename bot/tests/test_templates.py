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


def test_deleting_waits_ten_seconds_server_side():
    """Die Wartezeit muss im BOT stehen, nicht nur im Browser.

    Das Abtippen des Servernamens ist auf Wunsch entfallen. Es sah nach
    Sicherheit aus, war aber keine: der Name stand als Platzhalter
    direkt im Feld darueber.

    Was ihn ersetzt, muss dafuer echt sein. Eine Sperre, die nur im
    `disabled` eines Knopfes lebt, umgeht man mit einem einzigen
    `curl` -- deshalb rechnet der Bot selbst nach.
    """
    print("\nLoeschen wartet zehn Sekunden, serverseitig")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"), encoding="utf-8").read()
    )

    found = re.search(r"WIPE_DELAY_SECONDS\s*=\s*(\d+)", route)
    seconds = int(found.group(1)) if found else 0
    check("die Wartezeit steht im Bot", bool(found))
    check("sie betraegt 10 Sekunden", seconds == 10, f"-> {seconds}")

    block = route.split('if options["wipe"]:')[1].split("report =")[0]
    check("der Zeitstempel wird gelesen", "armed_at" in block)

    # Nicht nur erwaehnt -- verglichen, und bei zu frueh abgebrochen.
    guarded = re.search(
        r"waited\s*<\s*WIPE_DELAY_SECONDS[\s\S]{0,300}?raise HTTPException", block
    )
    check(
        "zu frueh wird abgewiesen",
        bool(guarded),
        "die Wartezeit wird berechnet, aber nichts passiert",
    )

    # Ohne diese Pruefung reichte `armed_at: 0` -- dann waere
    # `time.time() - 0` riesig und die Wartezeit immer erfuellt.
    zero = re.search(r"started\s*<=\s*0[\s\S]{0,300}?raise HTTPException", block)
    check(
        "ein fehlender Zeitstempel wird abgewiesen",
        bool(zero),
        "»armed_at: 0« haette die Sperre ausgehebelt",
    )

    # Eine Vorschau von gestern beschreibt den Server von gestern.
    stale = re.search(
        r"waited\s*>\s*WIPE_WINDOW_SECONDS[\s\S]{0,300}?raise HTTPException", block
    )
    check("eine alte Pruefung verfaellt", bool(stale))

    # Und die Pruefung muss den Stempel ueberhaupt ausliefern.
    preview = route.split("async def preview")[1].split("async def ")[0]
    check(
        "die Pruefung liefert den Zeitstempel",
        '"armed_at": time.time()' in preview,
        "sonst kann das Dashboard ihn gar nicht mitschicken",
    )
    check("und die Wartezeit dazu", '"wipe_delay": WIPE_DELAY_SECONDS' in preview)

    # Der Servername darf NICHT mehr verlangt werden -- sonst haengt
    # der Knopf an einem Feld, das es nicht mehr gibt.
    panel = strip_ts(read_dash("components", "dashboard", "template-community-panel.tsx"))
    check(
        "das Namensfeld ist weg",
        "confirmName" not in panel,
        "es steht noch da und blockiert den Knopf",
    )
    check(
        "und wird auch nicht mehr mitgeschickt",
        "confirm:" not in panel,
        "der Bot erwartet es nicht mehr",
    )


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
    """Zehn Sekunden, in denen man noch einmal liest."""
    print("\nDer Loesch-Knopf ist gesperrt")

    panel = strip_ts(read_dash("components", "dashboard", "template-community-panel.tsx"))

    check("es gibt eine Wartezeit", "WIPE_DELAY_SECONDS" in panel)
    found = re.search(r"WIPE_DELAY_SECONDS\s*=\s*(\d+)", panel)
    seconds = int(found.group(1)) if found else 0
    check("sie betraegt 10 Sekunden", seconds == 10, f"-> {seconds}")

    # Die Uhr muss an der PRUEFUNG haengen, nicht am Schalter.
    #
    # Lief sie ab dem Umlegen des Schalters, war sie abgelaufen, bevor
    # die Pruefung zurueck war: der Knopf sah frei aus, der Bot wies
    # trotzdem ab. Genau der Fall, der wie ein Fehler aussieht.
    effect = re.search(
        r"useEffect\(\(\) => \{[\s\S]{0,1400}?\}, \[wipe, preview\?\.armed_at",
        panel,
    )
    check(
        "die Wartezeit startet mit der Pruefung",
        bool(effect),
        "sie haengt noch am Schalter statt an der Pruefung",
    )

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
    check("der Knopf ist rot", "bg-red-500/15" in panel)

    # Der Zeitstempel muss beim Anwenden wirklich MITGESCHICKT werden.
    # Ohne ihn weist der Bot jeden Loeschversuch ab -- die Funktion
    # waere komplett tot, und zwar leise.
    apply_block = panel.split("const runApply")[1].split("if (loading)")[0]
    check(
        "der Zeitstempel geht mit",
        "armed_at: preview?.armed_at" in apply_block,
        "der Bot weist sonst jeden Versuch ab",
    )


# ------------------------------------------------------------------ #
# 7. Die drei echten Fehler, die beim Nachmessen auffielen
# ------------------------------------------------------------------ #
def test_wiping_then_building_actually_builds():
    """Der schlimmste Fehler im ganzen System.

    `channel.delete()` schickt nur die Anfrage. Aus `guild.channels`
    verschwindet der Kanal erst, wenn das Gateway `CHANNEL_DELETE`
    zurueckmeldet -- ein eigener Frame, Millisekunden bis Sekunden
    spaeter.

    `apply_channels` las danach sofort `{c.name for c in
    guild.channels}` und uebersprang jeden Namen, der dort stand. Bei
    "alles loeschen" standen dort ALLE gerade geloeschten Namen: der
    Server wurde geleert und danach nichts wieder angelegt.

    Reproduziert in `repro/bug_templates_wipe.py`. Dieser Test faehrt
    denselben Ablauf mit einer Gilde, deren Cache sich beim Loeschen
    NICHT aktualisiert -- genau wie der echte.
    """
    print("\nLeeren und neu bauen baut auch wirklich")

    from utils import template_apply as applier

    applier.STEP_PAUSE = 0

    class Role:
        def __init__(self, guild, name, position, default=False):
            self.guild, self.name, self.position = guild, name, position
            self.id = abs(hash((name, position))) % 10**18
            self._default, self.managed = default, False

        def is_default(self):
            return self._default

        async def delete(self, reason=None):
            self.guild.killed.append(self.name)

    class Channel:
        def __init__(self, guild, name):
            self.guild, self.name, self.position = guild, name, 0
            self.id = abs(hash(("c", name))) % 10**18
            self.category, self.overwrites = None, {}

        async def delete(self, reason=None):
            self.guild.killed.append(self.name)

    class Guild:
        def __init__(self):
            self.id, self.name = 1, "T"
            self.killed, self.built = [], []
            self.default_role = Role(self, "@everyone", 0, True)
            # Der Cache bleibt stehen -- das ist der springende Punkt.
            self._roles = [self.default_role, Role(self, "Mod", 5)]
            self._channels = [Channel(self, "allgemein")]
            self.rules_channel = None
            self.public_updates_channel = None
            self.system_channel = None
            top = Role(self, "Bot", 50)
            self.me = type("M", (), {
                "guild_permissions": type("P", (), {
                    "manage_channels": True, "manage_roles": True})(),
                "top_role": top})()

        @property
        def roles(self):
            return list(self._roles)

        @property
        def channels(self):
            return list(self._channels)

        @property
        def categories(self):
            return []

        async def create_role(self, **kw):
            self.built.append(kw["name"])
            return Role(self, kw["name"], 3)

        async def create_text_channel(self, **kw):
            self.built.append(kw["name"])
            return Channel(self, kw["name"])

        async def create_voice_channel(self, **kw):
            return await self.create_text_channel(**kw)

        async def create_category(self, **kw):
            return Channel(self, kw["name"])

    payload = {
        "categories": [],
        "channels": [{"name": "allgemein", "kind": "text", "category": None}],
        "roles": [{"name": "Mod", "colour": None, "permissions": []}],
        "features": {},
    }

    guild = Guild()
    asyncio.run(applier.apply_template(
        guild, payload,
        {"roles": True, "channels": True, "permissions": True,
         "features": False, "wipe": True}))

    check("die alte Rolle wurde geloescht", "Mod" in guild.killed)
    check("der alte Kanal wurde geloescht", "allgemein" in guild.killed)
    check(
        "die Rolle wurde neu angelegt",
        "Mod" in guild.built,
        "geloescht und nicht wieder da -- der Server bleibt leer",
    )
    check(
        "der Kanal wurde neu angelegt",
        "allgemein" in guild.built,
        "geloescht und nicht wieder da -- der Server bleibt leer",
    )

    # Und ohne Leeren muss die Wiederverwendung WEITER greifen: zwei
    # Rollen "Mod" waeren danach kaum auseinanderzuhalten.
    guild2 = Guild()
    asyncio.run(applier.apply_template(
        guild2, payload,
        {"roles": True, "channels": True, "permissions": True,
         "features": False, "wipe": False}))
    check(
        "ohne Leeren wird nichts doppelt angelegt",
        "Mod" not in guild2.built and "allgemein" not in guild2.built,
        f"-> {guild2.built}",
    )


def test_same_name_in_two_categories():
    """»chat« unter Team UND unter Community.

    Discord erlaubt gleichnamige Kanaele in verschiedenen Kategorien;
    das ist ein voellig gewoehnlicher Aufbau. Verglichen wurde aber nur
    der Name, also entstand nur der erste.

    Reproduziert in `repro/bug_templates_dupnames.py`.
    """
    print("\nGleichnamige Kanaele in zwei Kategorien")

    from utils import template_apply as applier

    applier.STEP_PAUSE = 0

    class Cat:
        def __init__(self, name):
            self.name, self.position = name, 0
            self.id = abs(hash(name)) % 10**18
            self.overwrites = {}

    class Guild:
        def __init__(self):
            self.id, self.name = 1, "T"
            self.built, self._cats = [], []
            self.roles, self.channels = [], []
            self.default_role = None

        @property
        def categories(self):
            return list(self._cats)

        async def create_category(self, **kw):
            made = Cat(kw["name"])
            self._cats.append(made)
            return made

        async def create_text_channel(self, **kw):
            self.built.append(
                f"{getattr(kw.get('category'), 'name', '-')}/{kw['name']}")
            return object()

        async def create_voice_channel(self, **kw):
            return await self.create_text_channel(**kw)

    payload = {
        "categories": [
            {"name": "Team", "position": 0, "overwrites": []},
            {"name": "Community", "position": 1, "overwrites": []},
        ],
        "channels": [
            {"name": "chat", "kind": "text", "category": "Team", "position": 0},
            {"name": "chat", "kind": "text", "category": "Community",
             "position": 1},
        ],
        "roles": [],
    }

    guild = Guild()
    report = applier.Report()
    asyncio.run(applier.apply_channels(guild, payload, {}, report))

    check(
        "beide werden angelegt",
        len(guild.built) == 2,
        f"-> {guild.built}",
    )
    check("in Team", "Team/chat" in guild.built)
    check("und in Community", "Community/chat" in guild.built)

    # Der Merker muss die Kategorie MITSCHREIBEN, nicht nur lesen.
    #
    # Ohne diesen Fall blieb der Test gruen, obwohl `existing.add`
    # die Kategorie wegwarf: die zwei Kanaele oben liegen in
    # verschiedenen Kategorien, aber sie kommen aus derselben Liste
    # und der zweite wurde ohnehin nicht gegen den ersten geprueft.
    # Erst DREI Kanaele decken es auf -- der dritte trifft auf den
    # Eintrag, den der erste hinterlassen hat.
    payload3 = {
        "categories": [
            {"name": "Team", "position": 0, "overwrites": []},
            {"name": "Community", "position": 1, "overwrites": []},
        ],
        "channels": [
            {"name": "chat", "kind": "text", "category": "Team", "position": 0},
            {"name": "info", "kind": "text", "category": "Team", "position": 1},
            {"name": "chat", "kind": "text", "category": "Community",
             "position": 2},
        ],
        "roles": [],
    }
    guild3 = Guild()
    asyncio.run(applier.apply_channels(guild3, payload3, {}, applier.Report()))
    check(
        "der Merker behaelt die Kategorie",
        "Community/chat" in guild3.built,
        f"»existing.add« wirft die Kategorie weg -> {guild3.built}",
    )

    # Und andersherum: derselbe Kanal ZWEIMAL in derselben Kategorie
    # darf nur einmal entstehen.
    #
    # Ohne diesen Fall blieb der Test gruen, obwohl `existing.add` die
    # Kategorie wegwarf -- die drei Kanaele oben liegen alle in
    # verschiedenen Paaren und stolpern nie ueber den Merker. Erst ein
    # echtes Duplikat trifft ihn.
    guild5 = Guild()
    asyncio.run(applier.apply_channels(
        guild5,
        {"categories": [{"name": "Team", "position": 0, "overwrites": []}],
         "channels": [
             {"name": "chat", "kind": "text", "category": "Team", "position": 0},
             {"name": "chat", "kind": "text", "category": "Team", "position": 1},
         ], "roles": []},
        {}, applier.Report()))
    check(
        "ein echtes Duplikat entsteht nur einmal",
        guild5.built.count("Team/chat") == 1,
        f"der Merker vergisst die Kategorie -> {guild5.built}",
    )

    # Und die KATEGORIEN selbst duerfen nach dem Leeren nicht als
    # bestehend gelten. Ohne diesen Fall blieb der Test gruen, obwohl
    # eine gerade geloeschte Kategorie im Cache jeden Kanal darin
    # elternlos gemacht haette.
    class Guild4(Guild):
        def __init__(self):
            super().__init__()
            stale = Cat("Team")
            self._cats.append(stale)
            self.stale_id = stale.id

    guild4 = Guild4()
    report4 = applier.Report()
    asyncio.run(applier.apply_channels(
        guild4,
        {"categories": [{"name": "Team", "position": 0, "overwrites": []}],
         "channels": [{"name": "chat", "kind": "text", "category": "Team"}],
         "roles": []},
        {}, report4, None, {guild4.stale_id}))
    # Auf den KANAL zu schauen genuegt nicht: er entsteht so oder so,
    # nur haengt er sonst an der toten Kategorie aus dem Cache. Discord
    # antwortet darauf mit "Unknown Channel". Geprueft wird deshalb, ob
    # die Kategorie wirklich NEU angelegt wurde.
    check(
        "eine geloeschte Kategorie wird neu angelegt",
        "Kategorie Team" in report4.created,
        f"der Kanal haengt an der toten Kategorie -> {report4.created}",
    )
    check("und der Kanal darin", "Team/chat" in guild4.built)

    # Der Vergleich muss wirklich das Paar sein, nicht nur der Name.
    src = strip_py(
        open(os.path.join(BOT, "utils", "template_apply.py"),
             encoding="utf-8").read()
    )
    block = src.split("async def apply_channels")[1].split("def resolve_")[0]
    check(
        "verglichen wird Name UND Kategorie",
        "(name, where) in existing" in block,
        "nur der Name reicht nicht",
    )


def test_an_unknown_column_does_not_lose_the_block():
    """Eine Spalte zu viel darf nicht alles mitnehmen.

    Das INSERT wurde aus den Spalten der QUELLE gebaut. Kennt das Ziel
    eine davon nicht, warf SQLite »has no column named x« und der ganze
    Block ging verloren -- statt der einen unpassenden Spalte.
    """
    print("\nEine unbekannte Spalte kostet nicht den ganzen Block")

    import sqlite3

    from utils import template_apply as applier
    from utils import template_scan

    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "music.db")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE music_settings (guild_id INTEGER PRIMARY KEY, "
            "dj_role_id INTEGER)"
        )

    class Guild:
        id, name = 1530378233579704370, "T"
        roles, channels = [], []
        default_role = None

    original = dict(template_scan.FEATURE_TABLES)
    template_scan.FEATURE_TABLES["music"] = ("Musik", path, ("music_settings",))
    try:
        report = applier.Report()
        payload = {"features": {"music": {"label": "Musik", "tables": {
            "music_settings": [
                {"guild_id": 1, "dj_role_id": None, "volume": 60}]}}}}
        asyncio.run(applier.apply_features(
            Guild(), payload, {"music": True}, report))
    finally:
        template_scan.FEATURE_TABLES.clear()
        template_scan.FEATURE_TABLES.update(original)

    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT * FROM music_settings").fetchall()

    check(
        "die passenden Spalten kommen an",
        bool(rows),
        f"alles verloren wegen einer Spalte -> {report.errors}",
    )
    check("und es gibt keinen Fehler", not report.errors, str(report.errors))
    check(
        "die unpassende wird benannt",
        any("volume" in entry for entry in report.skipped),
        "still weggeworfen waere schlechter als gemeldet",
    )

    # Eine Tabelle, die es gar nicht gibt, ist kein Fehler des Nutzers.
    template_scan.FEATURE_TABLES["music"] = ("Musik", path, ("music_settings",))
    try:
        report2 = applier.Report()
        payload2 = {"features": {"music": {"label": "Musik", "tables": {
            "gibt_es_nicht": [{"guild_id": 1}]}}}}
        asyncio.run(applier.apply_features(
            Guild(), payload2, {"music": True}, report2))
    finally:
        template_scan.FEATURE_TABLES.clear()
        template_scan.FEATURE_TABLES.update(original)

    check(
        "eine fehlende Tabelle wird uebersprungen, nicht geworfen",
        not report2.errors,
        str(report2.errors),
    )

    # Eine einzelne kaputte Zeile darf die anderen nicht mitnehmen.
    #
    # Ohne diesen Fall blieb der Test gruen, obwohl `raise` statt
    # `report.errors.append` dort stand: alle Zeilen oben waren heil,
    # der except-Zweig wurde nie betreten.
    path2 = os.path.join(folder, "zwei.db")
    with sqlite3.connect(path2) as db:
        db.execute(
            "CREATE TABLE music_settings (guild_id INTEGER, "
            "dj_role_id INTEGER NOT NULL)"
        )

    template_scan.FEATURE_TABLES["music"] = ("Musik", path2, ("music_settings",))
    try:
        report3 = applier.Report()
        payload3 = {"features": {"music": {"label": "Musik", "tables": {
            "music_settings": [
                # Die erste verletzt NOT NULL, die zweite ist heil.
                {"guild_id": 1, "dj_role_id": None},
                {"guild_id": 1, "dj_role_id": 42},
            ]}}}}
        asyncio.run(applier.apply_features(
            Guild(), payload3, {"music": True}, report3))
    finally:
        template_scan.FEATURE_TABLES.clear()
        template_scan.FEATURE_TABLES.update(original)

    with sqlite3.connect(path2) as db:
        rows2 = db.execute("SELECT dj_role_id FROM music_settings").fetchall()

    check(
        "die heile Zeile kommt trotzdem an",
        rows2 == [(42,)],
        f"eine kaputte Zeile riss alle mit -> {rows2}",
    )
    check(
        "und die kaputte wird gemeldet",
        len(report3.errors) == 1,
        f"-> {report3.errors}",
    )


# ------------------------------------------------------------------ #
# 8. Der eigene Code laesst sich wieder ansehen
# ------------------------------------------------------------------ #
def test_the_key_can_be_shown_again():
    """Verschluesselt gespeichert -- und wieder lesbar.

    Vorher gab es den Code genau einmal. Wer das Fenster schloss,
    musste die Vorlage neu hochladen.

    Wichtig dabei: der HASH bleibt die Pruefinstanz. Wuerde stattdessen
    entschluesselt und verglichen, oeffnete ein Fehler in der Krypto
    sofort jede Vorlage.
    """
    print("\nDer eigene Code laesst sich wieder ansehen")

    from utils import template_store as store

    # Fester Schluessel, damit der Test nicht davon abhaengt, ob eine
    # Datei angelegt werden kann.
    os.environ[store.SECRET_ENV] = "test-schluessel-fuer-den-test"

    plain = store.make_key()
    blob = store.encrypt_key(plain)

    check("verschluesselt ist es nicht mehr lesbar", plain not in blob)
    check("und wieder entschluesselbar", store.decrypt_key(blob) == plain)

    # Ein veraenderter Chiffretext darf NICHT stillschweigend etwas
    # anderes ergeben.
    import base64 as _b64

    raw = bytearray(_b64.urlsafe_b64decode(blob))
    raw[-1] ^= 0x01
    tampered = _b64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    check(
        "eine Faelschung wird erkannt",
        store.decrypt_key(tampered) is None,
        "ohne Signatur kaeme unbemerkt etwas anderes heraus",
    )

    # Anderer Hauptschluessel -> nicht lesbar, aber auch kein Absturz.
    os.environ[store.SECRET_ENV] = "ein-ganz-anderer-schluessel"
    check("mit falschem Schluessel: None", store.decrypt_key(blob) is None)
    os.environ[store.SECRET_ENV] = "test-schluessel-fuer-den-test"

    check("Muell ergibt None", store.decrypt_key("nicht-base64!!!") is None)
    check("leer ergibt None", store.decrypt_key("") is None)
    # "nicht-base64!!!" dekodiert ohne Murren zu Bytes und faellt erst
    # an der Laengenpruefung durch -- der except-Zweig wurde dabei nie
    # betreten. "A" hat eine ungueltige Laenge und wirft wirklich.
    check(
        "ungueltiges Base64 wirft nicht, sondern gibt None",
        store.decrypt_key("A") is None,
        "ein raise hier liesse das Admin-Panel abstuerzen",
    )
    # Und Zeichen ausserhalb von ASCII: `.encode("ascii")` wirft dabei
    # einen UnicodeEncodeError, einen anderen Typ als binascii.Error.
    check(
        "auch Nicht-ASCII gibt None",
        store.decrypt_key("Ümlaut") is None,
        "ein raise hier liesse das Admin-Panel abstuerzen",
    )

    async def scenario(db, store):
        made, key = await store.create_template(
            db, name="Mit Code", description="", author_id=1,
            author_name="x", source_guild_id=100, payload={"roles": []},
            visibility="key")

        found, again = await store.reveal_key(db, made, owner_guild_id=100)
        check("die eigene Vorlage gibt den Code her", found and again == key)

        # Ein fremder Server nicht. Die IDs sind fortlaufend.
        other, leaked = await store.reveal_key(db, made, owner_guild_id=999)
        check(
            "ein fremder Server bekommt ihn nicht",
            not other and leaked is None,
            "sonst reichte eine geratene Zahl",
        )

        # Der Hash prueft weiter -- unabhaengig von der Krypto.
        opened = await store.get_template(db, made, key=key)
        check("mit Code laesst sie sich oeffnen", not opened["locked"])
        # Auch die Einzelansicht muss sagen, ob es einen Code gibt.
        # Sie speist die eigene Liste im Upload-Reiter; stuende dort
        # fest False, erschiene der Knopf »Code anzeigen« nirgends.
        check(
            "die Einzelansicht meldet den Code",
            opened["has_key"] is True,
            "ohne das faellt der Knopf »Code anzeigen« weg",
        )
        wrong = await store.get_template(db, made, key="FALSCH12")
        check("mit falschem Code nicht", wrong["locked"])

        # Eine offene Vorlage hat gar keinen Code.
        plain_id, no_key = await store.create_template(
            db, name="Offen", description="", author_id=1, author_name="x",
            source_guild_id=100, payload={"roles": []}, visibility="public")
        check("eine offene Vorlage hat keinen", no_key is None)
        _, nothing = await store.reveal_key(db, plain_id, owner_guild_id=100)
        check("und gibt auch keinen her", nothing is None)

    asyncio.run(_with_db(scenario))

    # Geprueft wird ueber den Hash, nicht ueber die Entschluesselung.
    src = strip_py(
        open(os.path.join(BOT, "utils", "template_store.py"),
             encoding="utf-8").read()
    )
    block = src.split("async def get_template")[1].split("async def ")[0]
    check(
        "das Oeffnen prueft den Hash",
        "hash_key(key) == row" in block,
        "geprueft wird ueber den Hash, nie ueber die Entschluesselung",
    )
    check(
        "und entschluesselt dabei nichts",
        "decrypt_key" not in block,
        "ein Fehler in der Krypto oeffnete sonst jede Vorlage",
    )


def test_the_schema_upgrades_itself():
    """Eine bestehende Datenbank darf nicht von Hand angefasst werden."""
    print("\nDas Schema waechst mit")

    async def scenario(db, store):
        # Zweiter Aufruf auf derselben Datei: ALTER TABLE darf nicht
        # werfen, nur weil die Spalte schon da ist.
        await store.ensure_schema(db)
        await store.ensure_schema(db)

        async with db.execute("PRAGMA table_info(templates)") as cursor:
            have = {row[1] for row in await cursor.fetchall()}

        for column in ("key_cipher", "blocked", "blocked_reason",
                       "blocked_by", "blocked_at"):
            check(f"{column} gibt es", column in have)

    asyncio.run(_with_db(scenario))

    src = strip_py(
        open(os.path.join(BOT, "utils", "template_store.py"),
             encoding="utf-8").read()
    )
    check(
        "vorher wird nachgesehen",
        "PRAGMA table_info(templates)" in src,
        "SQLite kann ADD COLUMN nicht bedingt",
    )


# ------------------------------------------------------------------ #
# 9. Der Admin-Reiter
# ------------------------------------------------------------------ #
def test_the_admin_sees_everything():
    """Alles, auch die privaten -- und der Code im Klartext."""
    print("\nDer Admin-Reiter zeigt alles")

    from utils import template_store as store

    os.environ[store.SECRET_ENV] = "test-schluessel-fuer-den-test"

    async def scenario(db, store):
        _, key = await store.create_template(
            db, name="Geheim", description="", author_id=7,
            author_name="Fufi", source_guild_id=100,
            payload={"roles": [{"name": "A"}]}, visibility="key")
        await store.create_template(
            db, name="Privat", description="", author_id=7,
            author_name="Fufi", source_guild_id=100,
            payload={"roles": []}, visibility="private")
        await store.create_template(
            db, name="Offen", description="", author_id=7,
            author_name="Fufi", source_guild_id=200,
            payload={"roles": []}, visibility="public")

        # Die oeffentliche Liste laesst die private aus.
        public = await store.list_templates(db)
        check(
            "privat bleibt privat",
            not any(e["name"] == "Privat" for e in public),
            "die normale Liste zeigt sie",
        )

        entries = await store.list_for_admin(db)
        names = {e["name"] for e in entries}
        check("der Admin sieht alle drei", names == {"Geheim", "Privat", "Offen"},
              str(sorted(names)))

        secret = next(e for e in entries if e["name"] == "Geheim")
        check("der Code steht im Klartext dabei", secret["key"] == key)
        # Auch die Admin-Liste muss sagen, ob es ueberhaupt einen Code
        # gibt. Ohne diesen Fall blieb der Test gruen, obwohl das Feld
        # dort fest auf False stand -- im Panel waere der Abschnitt
        # "Zugangscode" dann bei jeder Vorlage mit "ist offen"
        # beschriftet gewesen, direkt neben dem Code.
        check(
            "und die Liste sagt, dass es einen gibt",
            secret["has_key"] is True,
            "das Panel schriebe sonst »ist offen« neben den Code",
        )
        offen = next(e for e in entries if e["name"] == "Offen")
        check("bei einer offenen Vorlage nicht", offen["has_key"] is False)
        check("die Herkunft auch", secret["source_guild_id"] == "100")
        check("und der Hochlader", secret["author_name"] == "Fufi")
        check(
            "die Zahlen sind echt, nicht verschluesselt weggelassen",
            secret["summary"]["roles"] == 1,
            "bei Code-Vorlagen standen sonst ueberall Nullen",
        )

        # Suche ueber die Server-ID -- eine Zahl ist oft alles, was man
        # aus einer Meldung hat.
        by_id = await store.list_for_admin(db, search="200")
        check("Suche nach der Server-ID findet sie", len(by_id) == 1)

        stats = await store.admin_stats(db)
        check("die Zahlen stimmen", stats["total"] == 3 and stats["with_key"] == 1,
              str(stats))

    asyncio.run(_with_db(scenario))


def test_blocking_is_reversible_and_bites():
    """Sperren muss wirken -- und sich zuruecknehmen lassen."""
    print("\nSperren wirkt und laesst sich zuruecknehmen")

    async def scenario(db, store):
        made, _ = await store.create_template(
            db, name="X", description="", author_id=1, author_name="x",
            source_guild_id=100, payload={"roles": []}, visibility="public")

        check("frisch ist sie frei",
              not (await store.get_template(db, made))["blocked"])

        await store.set_blocked(db, made, blocked=True, reason="Grund",
                                actor="42")
        found = await store.get_template(db, made)
        check("gesperrt", found["blocked"])
        check("mit Grund", found["blocked_reason"] == "Grund")

        # Sie bleibt SICHTBAR -- Sperren ist nicht Loeschen.
        listed = await store.list_templates(db)
        check(
            "sie steht weiter in der Liste",
            any(e["id"] == made for e in listed),
            "sonst waere Sperren dasselbe wie Loeschen",
        )

        await store.set_blocked(db, made, blocked=False)
        after = await store.get_template(db, made)
        check("wieder frei", not after["blocked"])
        check("und der Grund ist weg", not after["blocked_reason"])

        # Loeschen raeumt auch den Verlauf mit weg.
        await store.log_apply(db, template_id=made, guild_id=5, actor_id=1,
                              options={}, wiped=False)
        check("der Verlauf ist da", len(await store.history_for(db, made)) == 1)
        check("Admin-Loeschen geht", await store.force_delete(db, made))
        check("und der Verlauf ist mit weg",
              not await store.history_for(db, made))
        check("ein zweites Mal geht nicht",
              not await store.force_delete(db, made))

    asyncio.run(_with_db(scenario))

    # Der Riegel muss im BOT stehen, nicht nur im Knopf.
    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"),
             encoding="utf-8").read()
    )
    apply_block = route.split("async def apply(")[1].split("report =")[0]
    check(
        "eine gesperrte Vorlage wird beim Anwenden abgewiesen",
        'found.get("blocked")' in apply_block
        and "raise HTTPException" in apply_block,
        "ein direkter Aufruf umginge den ausgegrauten Knopf",
    )

    # Ein Grund ist Pflicht.
    block_route = route.split("async def admin_block")[1].split("@router")[0]
    check(
        "sperren ohne Grund geht nicht",
        "if blocked and not reason" in block_route,
        "der Hochlader saehe sonst nur, dass etwas kaputt ist",
    )


def test_the_admin_routes_are_locked_down():
    """/templates/admin/* nur fuer globale Admins."""
    print("\nDie Admin-Routen sind dicht")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    block = proxy.split('scope === "templates"')[1].split("if (scope ===")[0]

    check("der Admin-Zweig existiert", 'first === "admin"' in block)
    check(
        "und laesst nur globale Admins durch",
        "isGlobalAdmin" in block.split('first === "admin"')[1][:400],
        "jeder Server-Moderator saehe sonst jeden fremden Code",
    )

    # Die Regel muss VOR der guild_id-Pruefung stehen: "admin" ist
    # keine achtzehnstellige Zahl.
    check(
        "die Regel steht vor der guild_id-Pruefung",
        block.index('first === "admin"') < block.index("verifyGuildAccess"),
        "sonst liefe der Aufruf in verifyGuildAccess(\"admin\")",
    )
    check(
        "eine echte Server-ID wird verlangt",
        "/^\\d{17,20}$/.test(guildId)" in block,
        "sonst geht jedes Wort als guild_id durch",
    )

    # Und der Reiter darf nur Ownern angezeigt werden.
    admin = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))
    check(
        "der Reiter ist fuer Team-Rollen ausgeblendet",
        'if (tab.id === "templates") return false;' in admin,
        "er stuende sonst da und gaebe beim Klick nur Fehler",
    )


def test_the_admin_tab_is_wired_up():
    print("\nDer Admin-Reiter ist verdrahtet")

    admin = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))
    check("der Reiter steht in der Liste",
          '{ id: "templates", label: "Vorlagen"' in admin)
    check("er wird gerendert",
          'activeTab === "templates" && <TemplatesAdmin />' in admin)
    check("das Bauteil ist eingebunden",
          "import { TemplatesAdmin }" in admin)
    check("er nimmt die volle Breite",
          '"templates",\n]);' in admin or '"tester", "templates"' in admin)

    api_src = strip_ts(read_dash("lib", "api.ts"))
    for name in ("templateAdminList:", "templateAdminPayload:",
                 "templateAdminHistory:", "templateAdminBlock:",
                 "templateAdminDelete:", "templateKey:"):
        check(f"{name} gibt es", name in api_src)

    panel = strip_ts(read_dash("components", "dashboard", "templates-admin.tsx"))
    check("es gibt eine Wartezeit vorm Loeschen",
          "DELETE_DELAY_SECONDS" in panel)
    found = re.search(r"DELETE_DELAY_SECONDS\s*=\s*(\d+)", panel)
    check("sie betraegt 10 Sekunden",
          bool(found) and int(found.group(1)) == 10)

    # Die Sperre muss im disabled stehen, nicht nur in der Beschriftung.
    disabled = re.search(
        r"disabled=\{countdown > 0([\s\S]{0,120}?)\}\s*\n\s*onClick=\{\(\) => runDelete",
        panel)
    check("der Knopf ist so lange gesperrt", bool(disabled),
          "die Wartezeit steht nur in der Beschriftung")

    # Die Uhr muss beim Wechsel der Vorlage neu starten -- sonst wartet
    # man einmal und kann danach alles wegklicken.
    check(
        "die Uhr startet je Vorlage neu",
        "}, [deleteFor]);" in panel,
        "sonst haette man einmal gewartet und koennte alles loeschen",
    )


def test_the_own_uploads_show_their_key():
    print("\nEigene Uploads zeigen ihren Code")

    panel = strip_ts(read_dash("components", "dashboard",
                               "template-upload-panel.tsx"))
    check("es gibt den Knopf", "api.templateKey(" in panel)
    check("der Code wird angezeigt", "keys[entry.id]" in panel)
    check(
        "nur wenn es einen gibt",
        "entry.has_key &&" in panel,
        "bei offenen Vorlagen waere der Knopf sinnlos",
    )
    # `undefined` heisst zugeklappt, "" heisst aufgeklappt aber nicht
    # mehr lesbar. Eine Pruefung auf Wahrheit verschluckte den Hinweis.
    # Alle DREI Stellen muessen gegen `undefined` pruefen, nicht auf
    # Wahrheit. Eine Suche ueber die ganze Datei blieb gruen, obwohl
    # ausgerechnet die Anzeige auf Wahrheit pruefte -- der Hinweis
    # "nicht mehr anzeigbar" waere unsichtbar geblieben, und der Knopf
    # haette bei jedem Klick neu geladen statt zuzuklappen.
    check(
        "aufgeklappt und leer wird ueberall unterschieden",
        panel.count("keys[entry.id] !== undefined") == 3,
        f"nur {panel.count('keys[entry.id] !== undefined')} von 3 Stellen",
    )
    check(
        "und nirgends auf Wahrheit geprueft",
        "{keys[entry.id] && (" not in panel,
        "ein leerer Code gilt in JavaScript als falsch",
    )
    check("eine Sperre wird angezeigt", "entry.blocked_reason" in panel)

    store_src = strip_py(
        open(os.path.join(BOT, "utils", "template_store.py"),
             encoding="utf-8").read()
    )
    check(
        "die eigene Liste sagt, ob es einen Code gibt",
        '"has_key"' in store_src,
        "sonst weiss die Oberflaeche nicht, ob sie den Knopf zeigen darf",
    )


def test_the_new_routes_are_registered():
    print("\nDie neuen Routen sind angemeldet")

    from fastapi.testclient import TestClient

    from api.server import create_app

    client = TestClient(create_app())
    answer = client.get("/api/v1/openapi.json")
    if answer.status_code != 200:
        check("openapi ist lesbar", False)
        return

    paths = set(answer.json()["paths"])
    for path in (
        "/templates/admin/list",
        "/templates/admin/{template_id}/payload",
        "/templates/admin/{template_id}/history",
        "/templates/admin/{template_id}/block",
        "/templates/admin/{template_id}",
        "/templates/{guild_id}/template/{template_id}/key",
    ):
        check(f"{path} gibt es", path in paths)

    # Die Reihenfolge zaehlt: FastAPI prueft von oben nach unten.
    # Stuende /admin/list hinter /{guild_id}/list, liefe der Aufruf in
    # die guild_id-Regel und antwortete mit 422.
    route = open(os.path.join(BOT, "api", "routes", "templates.py"),
                 encoding="utf-8").read()
    check(
        "die Admin-Routen stehen vor den guild_id-Routen",
        route.index('"/admin/list"') < route.index('"/{guild_id}/list"'),
        "sonst faengt die guild_id-Regel /admin/list ab",
    )


# ------------------------------------------------------------------ #
# 10. Der Admin-Reiter zeigt WIRKLICH etwas
# ------------------------------------------------------------------ #
def test_the_admin_detail_is_not_empty_for_locked_templates():
    """Der Fehler, den der Nutzer gemeldet hat.

    `admin_payload` rief `get_template` ohne Code und ohne
    owner_guild_id. Bei einer Vorlage MIT Code blieb `unlocked` damit
    False, und `_row_to_template` lieferte ein LEERES payload --
    genau bei den Vorlagen, die ein Admin am ehesten pruefen will.

    Keine Fehlermeldung, kein Hinweis: nur eine leere Detailansicht.

    Reproduziert in `repro/bug_admin_templates.py`.
    """
    print("\nDie Detailansicht ist auch bei Code-Vorlagen gefuellt")

    async def scenario(db, store):
        payload = {
            "source": {"name": "Quellserver", "member_count": 42},
            "categories": [{"name": "Team", "position": 0, "overwrites": []}],
            "channels": [{"name": "geheim", "kind": "text",
                          "category": "Team"}],
            "roles": [{"name": "Admin", "colour": "#00ff00",
                       "permissions": ["administrator"]}],
            "features": {},
        }

        offen, _ = await store.create_template(
            db, name="Offen", description="", author_id=1, author_name="x",
            source_guild_id=100, payload=payload, visibility="public")
        mit_code, _ = await store.create_template(
            db, name="Code", description="", author_id=1, author_name="x",
            source_guild_id=100, payload=payload, visibility="key")
        privat, _ = await store.create_template(
            db, name="Privat", description="", author_id=1, author_name="x",
            source_guild_id=100, payload=payload, visibility="private")

        for label, tid in (("offen", offen), ("mit Code", mit_code),
                           ("privat", privat)):
            found = await store.get_template(db, tid, as_admin=True)
            check(
                f"»{label}«: der Admin sieht den Inhalt",
                bool((found.get("payload") or {}).get("roles")),
                "die Detailansicht bliebe leer",
            )
            check(
                f"»{label}«: und die Zahlen stimmen",
                found["summary"]["channels"] == 1,
                f"-> {found['summary']}",
            )

        # OHNE das Kennzeichen bleibt eine Code-Vorlage verschlossen.
        # Das ist der Sinn des Codes -- er darf nur fuer Admins fallen.
        normal = await store.get_template(db, mit_code)
        check(
            "ohne Admin-Kennzeichen bleibt sie verschlossen",
            normal["locked"] and not normal.get("payload"),
            "der Zugangscode waere reine Zierde",
        )

    asyncio.run(_with_db(scenario))

    # Und die Route muss das Kennzeichen auch WIRKLICH setzen.
    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"),
             encoding="utf-8").read()
    )
    block = route.split("async def admin_payload")[1].split("@router")[0]
    check(
        "admin_payload fragt als Admin",
        "as_admin=True" in block,
        "sonst ist die Detailansicht bei Code-Vorlagen leer",
    )
    # Die normalen Routen duerfen es NICHT setzen.
    for name in ("async def detail", "async def preview", "async def apply("):
        part = route.split(name)[1].split("@router")[0]
        check(
            f"{name.split()[-1]} fragt NICHT als Admin",
            "as_admin" not in part,
            "der Zugangscode waere damit ausgehebelt",
        )


def test_the_detail_says_what_is_in_the_template():
    """Mehr als Namen: Aufbau, Rechte, Herkunft."""
    print("\nDie Detailansicht sagt, was drinsteht")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"),
             encoding="utf-8").read()
    )
    block = route.split("async def admin_payload")[1].split("@router")[0]

    for field in ('"counts"', '"source"', '"dangerous"', '"position"',
                  '"topic"', '"nsfw"'):
        check(f"{field} kommt mit", field in block)

    check(
        "es gibt eine Liste heikler Rechte",
        "_DANGEROUS_PERMISSIONS" in route,
        "eine Admin-Rolle in einer Vorlage muss auffallen",
    )
    check("administrator steht darauf", '"administrator"' in route)

    # Und jetzt gegen die echte Route. Die Textsuchen oben blieben
    # gruen, als "dangerous" fest auf [] und "counts" auf 0 standen --
    # die Felder waren da, nur leer.
    from api.routes import templates as api_route

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    async def build():
        import aiosqlite

        from utils import template_store as store

        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            tid, _ = await store.create_template(
                db, name="Riskant", description="", author_id=1,
                author_name="x", source_guild_id=100,
                payload={
                    "source": {"name": "Quelle", "member_count": 99},
                    "categories": [
                        {"name": "Zwei", "position": 1, "overwrites": []},
                        {"name": "Eins", "position": 0, "overwrites": []},
                    ],
                    "channels": [
                        {"name": "chat", "kind": "text", "category": "Eins",
                         "topic": "Hallo", "nsfw": True, "slowmode": 30},
                        {"name": "reden", "kind": "voice",
                         "category": "Zwei"},
                    ],
                    "roles": [
                        {"name": "Boss", "colour": "#ff0000",
                         "permissions": ["administrator", "send_messages"]},
                        {"name": "Gast", "colour": None,
                         "permissions": ["send_messages"]},
                    ],
                    "features": {},
                },
                visibility="key")
            return tid

    tid = asyncio.run(build())
    answer = _run_route(lambda: api_route.admin_payload(tid), path)

    check("die Zahlen stimmen",
          answer["counts"] == {"categories": 2, "channels": 2, "roles": 2,
                               "features": 0},
          f"-> {answer['counts']}")
    check("die Herkunft kommt mit",
          answer["source"].get("name") == "Quelle",
          f"-> {answer['source']}")

    roles = {r["name"]: r for r in answer["roles"]}
    check(
        "die riskante Rolle ist als riskant markiert",
        roles["Boss"]["dangerous"] == ["administrator"],
        f"-> {roles['Boss']['dangerous']}",
    )
    check(
        "die harmlose nicht",
        roles["Gast"]["dangerous"] == [],
        f"-> {roles['Gast']['dangerous']}",
    )
    check("die Rechte werden gezaehlt", roles["Boss"]["permissions"] == 2)

    channels = {c["name"]: c for c in answer["channels"]}
    check("das Thema kommt mit", channels["chat"]["topic"] == "Hallo")
    check("NSFW auch", channels["chat"]["nsfw"] is True)
    check("und der Slowmode", channels["chat"]["slowmode"] == 30)
    check("die Kanalart bleibt erhalten",
          channels["reden"]["kind"] == "voice")

    positions = [c["position"] for c in answer["categories"]]
    check("die Kategorien behalten ihre Reihenfolge",
          sorted(positions) == [0, 1], f"-> {positions}")

    os.unlink(path)

    # Die Warnung muss auf ECHTEN Daten beruhen, nicht auf einem
    # Textvergleich im Browser.
    panel = strip_ts(read_dash("components", "dashboard",
                               "templates-admin.tsx"))
    check(
        "das Panel liest die Bewertung vom Bot",
        "role?.dangerous || []" in panel,
        "eine eigene Liste im Browser liefe auseinander",
    )
    check("und warnt sichtbar", "riskyRoles(content).length > 0" in panel)


class _FakeGuild:
    """Ein Server, wie der Bot-Cache ihn liefert."""

    def __init__(self, gid, name, members=0):
        self.id = gid
        self.name = name
        self.member_count = members


class _FakeBot:
    """Ein Bot, der genau die uebergebenen Server kennt.

    `get_guild` verhaelt sich wie discord.py: ein String findet nichts,
    auch wenn die Zahl darin stimmt.
    """

    def __init__(self, *guilds):
        self._guilds = {int(g.id): g for g in guilds}

    def get_guild(self, gid):
        return self._guilds.get(gid)


def _run_route(coroutine, db_path):
    """Eine Route gegen eine eigene Datenbankdatei fahren.

    Die Verbindung wird danach GESCHLOSSEN. Ohne das haelt der
    `db_manager` sie offen, und der Testprozess endet nicht mehr: er
    lief von zwei Sekunden auf ueber fuenf Minuten und wurde im
    Mutationstest als Fehlschlag gewertet -- obwohl alle Pruefungen
    gruen waren. Dieselbe Falle wie schon in `test_phantom.py`.

    Geschlossen wird IM selben Ereignisschleifen-Lauf: eine
    aiosqlite-Verbindung gehoert der Schleife, in der sie entstand,
    und laesst sich aus einer neuen nicht mehr schliessen.
    """

    from api.db_manager import db_manager
    from utils import template_store as store

    before = store.DB_PATH
    store.DB_PATH = db_path

    async def wrapper():
        try:
            return await coroutine()
        finally:
            await db_manager.close_all()

    try:
        return asyncio.run(wrapper())
    finally:
        store.DB_PATH = before


def test_the_admin_list_is_honest_about_the_bot():
    """»Bot nicht auf dem Server« darf nicht geraten sein.

    Drei Faelle, die sich unterscheiden muessen:
      * der Bot ist dort            -> gruen
      * der Bot ist dort nicht mehr -> grau
      * die ID ist unbrauchbar      -> "weiss ich nicht"

    Der dritte Fall lief vorher als "Bot ist weg" durch. Das ist ein
    Unterschied, an dem jemand eine Entscheidung festmacht.

    Geprueft wird die ANTWORT der Route, nicht ihr Quelltext. Eine
    Suche nach »presence_known« blieb gruen, als das Feld fest auf
    True stand -- der Wert war da, nur falsch.
    """
    print("\nDie Liste ist ehrlich, ob der Bot da ist")

    from api.routes import templates as route

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    async def build():
        import aiosqlite

        from utils import template_store as store

        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            for name, gid in (("Da", 111111111111111111),
                              ("Weg", 222222222222222222)):
                await store.create_template(
                    db, name=name, description="", author_id=1,
                    author_name="x", source_guild_id=gid,
                    payload={"source": {"name": f"{name}-Server",
                                        "member_count": 7},
                             "roles": [], "channels": [], "categories": [],
                             "features": {}},
                    visibility="public")

    asyncio.run(build())

    bot = _FakeBot(_FakeGuild(111111111111111111, "Noch dabei", 1284))
    answer = _run_route(lambda: route.admin_list(bot=bot), path)
    found = {e["name"]: e for e in answer["templates"]}

    here = found["Da"]
    check("der anwesende Server ist als anwesend gemeldet",
          here["bot_present"] is True)
    check("und das gilt als gesichert", here["presence_known"] is True)
    check("mit Namen aus dem Cache",
          here["source_guild_name"] == "Noch dabei",
          f"-> {here['source_guild_name']!r}")
    check("und Mitgliederzahl", here["members"] == 1284)

    gone = found["Weg"]
    check("der verlassene Server ist als verlassen gemeldet",
          gone["bot_present"] is False)
    check("auch das ist gesichert", gone["presence_known"] is True)
    # Ohne Cache bleibt nur der Name aus der Vorlage. Ohne diesen
    # Rueckfall stuende dort gar nichts.
    check(
        "und der Name von damals springt ein",
        gone["source_guild_name"] == "Weg-Server",
        f"-> {gone['source_guild_name']!r}",
    )

    # Der dritte Fall: eine ID, die keine Zahl ist.
    async def broken():
        import aiosqlite

        from utils import template_store as store

        async with aiosqlite.connect(path) as db:
            await db.execute(
                "UPDATE templates SET source_guild_id = 'kaputt' "
                "WHERE name = 'Weg'"
            )
            await db.commit()

    asyncio.run(broken())

    answer2 = _run_route(lambda: route.admin_list(bot=bot), path)
    odd = next(e for e in answer2["templates"] if e["name"] == "Weg")
    check(
        "eine unlesbare ID gilt als »weiss ich nicht«",
        odd["presence_known"] is False,
        "sonst laeuft sie als »Bot ist weg« durch",
    )

    os.unlink(path)

    panel = strip_ts(read_dash("components", "dashboard",
                               "templates-admin.tsx"))
    check(
        "das Panel unterscheidet die drei Faelle",
        "!entry.presence_known" in panel,
        "sonst zeigt es weiter »Bot ist weg«",
    )


def test_the_uploader_is_actually_recorded():
    """Hochlader und Anwender kamen nie an.

    Der Proxy setzt in jeden Schreibvorgang `actor` aus der Sitzung.
    Die Route las aber `author_id` bzw. `actor_id` -- Felder, die kein
    Aufrufer je mitschickt. Ergebnis: bei JEDER Vorlage stand
    "unbekannt", und der Verlauf hatte eine leere Spalte.
    """
    print("\nDer Hochlader wird wirklich gespeichert")

    route = strip_py(
        open(os.path.join(BOT, "api", "routes", "templates.py"),
             encoding="utf-8").read()
    )

    upload = route.split("async def upload")[1].split("@router")[0]
    check(
        "der Upload liest »actor«",
        'get("actor")' in upload,
        "nur das Feld setzt der Proxy aus der Sitzung",
    )
    check(
        "und reicht es an den Store weiter",
        "author_id=author_id" in upload,
        "sonst landet es nicht in der Datenbank",
    )

    apply_block = route.split("async def apply(")[1]
    check(
        "das Anwenden liest »actor« ebenso",
        'get("actor")' in apply_block,
        "der Verlauf bliebe ohne Namen",
    )
    check("und schreibt es in den Verlauf", "actor_id=actor_id" in apply_block)

    # Der Proxy muss es tatsaechlich setzen -- sonst ist alles obige
    # umsonst.
    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    check(
        "der Proxy setzt actor aus der Sitzung",
        "parsed.actor = actorId" in proxy,
        "eine ID aus dem Browser waere faelschbar",
    )

    # Und der Store muss eine Zahl bekommen, keinen String: die Spalte
    # ist INTEGER, ein String landete dort als Text und passte danach
    # zu keinem Vergleich mehr.
    check(
        "die ID wird zur Zahl gemacht",
        "int(author_id) if author_id else None" in upload,
        "eine INTEGER-Spalte mit Text darin",
    )


def test_the_history_names_the_servers():
    """Der Verlauf muss den Namen wirklich LIEFERN.

    Eine Suche nach '"guild_name"' im Quelltext blieb gruen, als das
    Feld fest auf "" stand.
    """
    print("\nDer Verlauf nennt Servernamen")

    from api.routes import templates as route

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    async def build():
        import aiosqlite

        from utils import template_store as store

        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            tid, _ = await store.create_template(
                db, name="X", description="", author_id=1, author_name="x",
                source_guild_id=111111111111111111, payload={"roles": []},
                visibility="public")
            await store.log_apply(
                db, template_id=tid, guild_id=333333333333333333,
                actor_id=1303627964734246944, options={}, wiped=True)
            await store.log_apply(
                db, template_id=tid, guild_id=444444444444444444,
                actor_id=None, options={}, wiped=False)
            return tid

    tid = asyncio.run(build())

    bot = _FakeBot(_FakeGuild(333333333333333333, "Gaming-Treff"))
    answer = _run_route(lambda: route.admin_history(tid, bot=bot), path)
    events = {e["guild_id"]: e for e in answer["events"]}

    known = events["333333333333333333"]
    check(
        "ein bekannter Server bekommt seinen Namen",
        known["guild_name"] == "Gaming-Treff",
        f"-> {known['guild_name']!r}",
    )
    check("wer es war, steht dabei",
          known["actor_id"] == "1303627964734246944")
    check("und ob geleert wurde", known["wiped"] is True)

    unknown = events["444444444444444444"]
    check("ein unbekannter Server bleibt namenlos, ohne zu stuerzen",
          unknown["guild_name"] == "")

    os.unlink(path)

    panel = strip_ts(read_dash("components", "dashboard",
                               "templates-admin.tsx"))
    check("das Panel zeigt ihn", "event.guild_name" in panel)
    check("und wer es war", "event.actor_id" in panel)


def test_a_failed_load_is_visible():
    """Ein Ladefehler sah aus wie eine leere Vorlage.

    Beides zeigte gar nichts. Ein Toast verschwindet nach fuenf
    Sekunden -- danach steht man wieder vor dem Nichts und weiss
    nicht, ob die Vorlage leer ist oder die Anfrage scheiterte.
    """
    print("\nEin Fehlschlag beim Laden ist sichtbar")

    panel = strip_ts(read_dash("components", "dashboard",
                               "templates-admin.tsx"))

    check("es gibt einen Fehlerzustand", "setFailed" in panel)
    check("er wird angezeigt", "failed[entry.id] ?" in panel)
    # Der Grund muss im Fehlerfall auch GESETZT werden. Eine Suche
    # nach "setFailed" blieb gruen, als der catch-Zweig ihn wegwarf.
    # Genau der catch-Zweig von loadDetail -- es gibt vier in der
    # Datei, und der erste gehoert zur Listenabfrage.
    detail_fn = panel.split("const loadDetail")[1].split("const toggleOpen")[0]
    catch = detail_fn.split("} catch (error: any) {")[1].split("} finally")[0]
    check(
        "der Fehler wird im catch festgehalten",
        "setFailed(" in catch,
        "sonst bleibt die Ansicht leer wie zuvor",
    )
    check(
        "und der Grund kommt aus der Meldung",
        "error?.message" in catch,
        "»ging nicht« allein hilft niemandem",
    )
    check(
        "mit einem Knopf zum Wiederholen",
        "loadDetail(entry)" in panel,
        "sonst hilft nur neu laden",
    )
    check(
        "und der Grund steht dabei",
        "{failed[entry.id]}" in panel,
        "»ging nicht« allein hilft niemandem",
    )
    # Eine wirklich leere Vorlage muss sich davon unterscheiden.
    check(
        "eine leere Vorlage sagt, dass sie leer ist",
        "Diese Vorlage ist leer" in panel,
        "sonst sieht Leere aus wie ein Fehler",
    )
    # Nach einem Fehlschlag muss ein erneutes Aufklappen es nochmal
    # versuchen -- sonst haengt der Eintrag fuer immer im Fehler.
    check(
        "ein Fehlschlag wird erneut versucht",
        "if (detail[entry.id] && !failed[entry.id]) return;" in panel,
        "sonst bleibt der Eintrag fuer immer im Fehlerzustand",
    )


def test_channels_are_grouped_by_category():
    print("\nKanaele stehen nach Kategorie gruppiert")

    panel = strip_ts(read_dash("components", "dashboard",
                               "templates-admin.tsx"))

    check("es gibt die Gruppierung", "function grouped(" in panel)
    check("sie wird benutzt", "grouped(content).map" in panel)
    check(
        "die Reihenfolge kommt aus der Vorlage",
        "a.position ?? 0" in panel,
        "alphabetisch waere nicht der Aufbau des Servers",
    )
    check(
        "Kanaele ohne Kategorie kommen zuerst",
        "Ohne Kategorie" in panel,
        "Discord zeigt sie auch oben",
    )
    check(
        "eine unbekannte Kategorie faellt nicht unter den Tisch",
        "!order.includes(name)" in panel,
        "sonst verschwaenden Kanaele aus der Anzeige",
    )


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
    test_deleting_waits_ten_seconds_server_side()
    test_the_apply_survives_a_single_failure()
    test_roles_come_before_channels()
    test_the_routes_are_registered()
    test_the_proxy_knows_the_scope()
    test_the_dashboard_is_wired_up()
    test_both_tabs_are_marked_experimental()
    test_the_delay_before_wiping()
    test_wiping_then_building_actually_builds()
    test_same_name_in_two_categories()
    test_an_unknown_column_does_not_lose_the_block()
    test_the_key_can_be_shown_again()
    test_the_schema_upgrades_itself()
    test_the_admin_sees_everything()
    test_blocking_is_reversible_and_bites()
    test_the_admin_routes_are_locked_down()
    test_the_admin_tab_is_wired_up()
    test_the_own_uploads_show_their_key()
    test_the_new_routes_are_registered()
    test_the_admin_detail_is_not_empty_for_locked_templates()
    test_the_detail_says_what_is_in_the_template()
    test_the_admin_list_is_honest_about_the_bot()
    test_the_uploader_is_actually_recorded()
    test_the_history_names_the_servers()
    test_a_failed_load_is_visible()
    test_channels_are_grouped_by_category()

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
