#!/usr/bin/env python3
"""
Teamliste: wer im Team ist, nach Rollen geordnet, im Kanal sichtbar.

Vier Dinge sind hier wirklich wichtig, und danach ist der Test
sortiert:

  1. **Die Nachricht wird BEARBEITET, nicht neu gesendet.** Sonst ist
     der Kanal nach einer Woche voller Teamlisten.
  2. **Niemand wird gepingt.** Die Liste besteht fast nur aus
     Erwaehnungen -- ohne Sperre bekaeme das halbe Team bei jeder
     Auffrischung eine Benachrichtigung.
  3. **Sie haelt sich aktuell.** Auf Ereignisse hoeren UND regelmaessig
     nachsehen; eines allein laesst Faelle offen.
  4. **Das Format stimmt auf beiden Seiten ueberein.** Dashboard und
     Bot muessen dieselben Stilarten kennen.

Run:  python3 tests/test_teamlist.py
"""

import ast
import asyncio
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

    In den Dateien stehen die Faelle woertlich beschrieben -- eine
    Suche nach "bearbeitet" faende sonst die Erklaerung statt des
    Codes.
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

    from utils import teamlist_store as store

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            return await func(db, store)
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ #
# Ein Server zum Anfassen
# ------------------------------------------------------------------ #
class Role:
    def __init__(self, rid, name, position, colour=0, managed=False,
                 default=False):
        self.id, self.name, self.position = rid, name, position
        self.colour = type("C", (), {"value": colour})()
        self.managed, self._default = managed, default
        self.members = []

    def is_default(self):
        return self._default


class Member:
    def __init__(self, mid, name, roles, bot=False):
        self.id, self.display_name, self.bot = mid, name, bot
        self.roles = roles
        for role in roles:
            role.members.append(self)


class Perms:
    send_messages = True
    embed_links = True


class Message:
    def __init__(self, mid, channel):
        self.id, self.channel = mid, channel
        self.content = None
        self.edits = 0
        self.deleted = False

    async def edit(self, content=None, embed=None, allowed_mentions=None):
        self.content = content
        self.edits += 1
        self.channel.guild.mentions.append(allowed_mentions)

    async def delete(self):
        self.deleted = True
        self.channel.messages.pop(self.id, None)


class Channel:
    def __init__(self, cid, name, guild):
        self.id, self.name, self.guild = cid, name, guild
        self.category = None
        self.sent = []
        self.messages = {}

    def permissions_for(self, who):
        return Perms()

    async def send(self, content=None, embed=None, allowed_mentions=None):
        message = Message(9000 + len(self.sent), self)
        message.content = content
        self.sent.append(content)
        self.messages[message.id] = message
        self.guild.mentions.append(allowed_mentions)
        return message

    async def fetch_message(self, mid):
        import discord

        if int(mid) in self.messages:
            return self.messages[int(mid)]
        raise discord.NotFound(
            type("R", (), {"status": 404, "reason": "x"})(), "weg"
        )


class Guild:
    def __init__(self, presences=False):
        self.id, self.name = 100, "Testserver"
        self.mentions = []

        everyone = Role(100, "@everyone", 0, default=True)
        self.owner_role = Role(1, "Inhaber", 90, 0xFF0000)
        self.admin_role = Role(2, "Administrator", 80, 0xFF8800)
        self.mod_role = Role(3, "Moderator", 70, 0x3B82F6)
        self.leer_role = Role(4, "Praktikant", 10)
        bot_role = Role(5, "BotRolle", 60, managed=True)

        self.roles = [everyone, self.leer_role, bot_role, self.mod_role,
                      self.admin_role, self.owner_role]

        Member(201, "Zoe", [self.owner_role])
        Member(202, "Anton", [self.owner_role])
        Member(203, "Mia", [self.admin_role])
        Member(204, "BotDing", [self.mod_role], bot=True)
        Member(205, "Ben", [self.mod_role])

        self.members = [m for r in self.roles for m in r.members]
        self.channel = Channel(500, "team", self)
        self.text_channels = [self.channel]
        self.me = type("M", (), {"id": 999})()
        self._state = type("S", (), {
            "intents": type("I", (), {"presences": presences})()
        })()

    def get_channel(self, cid):
        return self.channel if int(cid) == 500 else None


class Bot:
    def __init__(self, guild):
        self._guild = guild
        self.loop = None

    def get_guild(self, gid):
        return self._guild if int(gid) == 100 else None


GROUPS = [
    {"role_id": "1", "emoji": "<:krone:111>", "label": "Inhaber"},
    {"role_id": "2", "emoji": "<:schild:222>", "label": ""},
    {"role_id": "3", "emoji": "", "label": "Moderation"},
    {"role_id": "4", "emoji": "", "label": "Praktikant"},
]


def _run_route(coroutine, db_path):
    """Eine Route gegen eine eigene Datenbankdatei fahren.

    Die Verbindung wird danach geschlossen -- sonst haelt der
    `db_manager` sie offen und der Testprozess endet nicht mehr.
    """

    from api.db_manager import db_manager
    from utils import teamlist_store as store

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


_KEINE = object()


def _prepared(config=None, groups=_KEINE):
    """Eine Datenbank mit Einstellungen und Gruppen.

    `groups=[]` heisst wirklich "keine Gruppen". Mit dem
    naheliegenden `groups or GROUPS` waere eine leere Liste zur
    Vorgabe geworden -- und der Test, der genau diesen Fall pruefen
    sollte, lief mit vier Gruppen.
    """

    import aiosqlite

    from utils import teamlist_store as store

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    async def build():
        async with aiosqlite.connect(path) as db:
            await store.ensure_schema(db)
            await store.save_config(db, 100, {
                "enabled": True, "channel_id": "500", "title": "Unser Team",
                "show_counts": True, **(config or {}),
            })
            await store.save_groups(
                db, 100, GROUPS if groups is _KEINE else groups
            )

    asyncio.run(build())
    return path


# ------------------------------------------------------------------ #
# 1. Der Text
# ------------------------------------------------------------------ #
def test_the_message_looks_right():
    """Ueberschrift, Emoji, Zitat-Strich, Zaehler."""
    print("\nDie Nachricht sieht richtig aus")

    from api.routes import teamlist as route

    path = _prepared()
    guild = Guild()
    answer = _run_route(lambda: route.preview(100, bot=Bot(guild)), path)
    text = answer["text"]

    check("es gibt eine Ueberschrift", "## Unser Team" in text)
    check("Emoji und Beschriftung stehen da",
          "<:krone:111> **Inhaber**" in text, text[:80])
    check(
        "ohne eigene Beschriftung springt der Rollenname ein",
        "**Administrator**" in text,
        "sonst stuende dort eine leere Ueberschrift",
    )
    check("die Anzahl steht dabei", "`2`" in text)
    check("die Zeilen haben den Zitat-Strich", "> <@201>" in text)
    check(
        "Mitglieder stehen als Erwaehnung, nicht als Name",
        "<@203>" in text and "Mia" not in text,
        "ein abgeschriebener Name waere nach einer Umbenennung falsch",
    )

    # Sortierung: Anton (202) vor Zoe (201).
    check(
        "die Mitglieder sind alphabetisch sortiert",
        text.index("<@202>") < text.index("<@201>"),
        "sonst springt die Liste bei jeder Auffrischung durcheinander",
    )
    check(
        "Bots stehen nicht drin",
        "<@204>" not in text,
        "eine Teamliste zaehlt Menschen",
    )
    check(
        "eine leere Gruppe faellt heraus",
        "Praktikant" not in text,
        "sonst steht eine Ueberschrift ohne Inhalt da",
    )

    os.unlink(path)


def test_the_options_change_the_text():
    print("\nDie Einstellungen wirken")

    from api.routes import teamlist as route

    # Leere Gruppen zeigen.
    path = _prepared({"show_empty": True})
    answer = _run_route(lambda: route.preview(100, bot=Bot(Guild())), path)
    check("show_empty zeigt die leere Gruppe",
          "Praktikant" in answer["text"])
    check("mit Hinweis statt einer Luecke",
          "*niemand*" in answer["text"])
    os.unlink(path)

    # Zaehler aus.
    path = _prepared({"show_counts": False})
    answer = _run_route(lambda: route.preview(100, bot=Bot(Guild())), path)
    check("ohne show_counts fehlt die Zahl", "`2`" not in answer["text"])
    os.unlink(path)

    # Andere Zeilenform.
    path = _prepared({"style": "bullet"})
    answer = _run_route(lambda: route.preview(100, bot=Bot(Guild())), path)
    check("eine andere Zeilenform greift",
          "• <@201>" in answer["text"] and "> <@201>" not in answer["text"],
          answer["text"][:120])
    os.unlink(path)

    # Kopf- und Fusstext.
    path = _prepared({"intro": "Hallo!", "footer": "Bis bald."})
    answer = _run_route(lambda: route.preview(100, bot=Bot(Guild())), path)
    check("der Text darueber steht da", "Hallo!" in answer["text"])
    check("der Text darunter auch", "Bis bald." in answer["text"])
    check("und in der richtigen Reihenfolge",
          answer["text"].index("Hallo!") < answer["text"].index("Bis bald."))
    os.unlink(path)


def test_a_long_list_is_cut_not_broken():
    """Discord nimmt hoechstens 2000 Zeichen."""
    print("\nEine zu lange Liste wird sauber gekuerzt")

    from utils import teamlist_store as store

    # 400 Mitglieder in einer Gruppe.
    members = {"1": [{"mention": f"<@{700000000000000000 + i}>"}
                     for i in range(400)]}
    text = store.build_lines(
        {"title": "Team", "style": "quote", "show_counts": True},
        [{"role_id": "1", "emoji": "", "label": "Alle"}],
        members,
    )

    check("der Text bleibt unter der Grenze",
          len(text) <= store.MAX_MESSAGE, f"-> {len(text)}")
    check("es wird angedeutet, dass gekuerzt wurde", text.endswith("…"))
    # Ein halber Erwaehnungs-Code waere sichtbarer Muell.
    check(
        "es wird an einer Zeile abgeschnitten",
        not re.search(r"<@\d*$", text.rstrip("…\n")),
        "mitten in einer Erwaehnung abgeschnitten",
    )


# ------------------------------------------------------------------ #
# 2. Senden und bearbeiten
# ------------------------------------------------------------------ #
def test_it_edits_instead_of_sending_again():
    """Sonst ist der Kanal nach einer Woche voller Teamlisten."""
    print("\nDie Nachricht wird bearbeitet, nicht neu gesendet")

    from api.routes import teamlist as route

    path = _prepared()
    guild = Guild()
    bot = Bot(guild)

    first = _run_route(lambda: route.publish(100, {}, bot=bot), path)
    check("beim ersten Mal wird gesendet", len(guild.channel.sent) == 1)

    second = _run_route(lambda: route.publish(100, {}, bot=bot), path)
    check(
        "beim zweiten Mal nicht noch einmal",
        len(guild.channel.sent) == 1,
        f"-> {len(guild.channel.sent)} Nachrichten",
    )
    check("sondern bearbeitet",
          guild.channel.messages[int(first["message_id"])].edits == 1)
    check("die ID bleibt dieselbe",
          second["message_id"] == first["message_id"])

    # Wurde die Nachricht geloescht, muss eine neue kommen.
    guild.channel.messages.clear()
    third = _run_route(lambda: route.publish(100, {}, bot=bot), path)
    check(
        "nach dem Loeschen wird neu gesendet",
        len(guild.channel.sent) == 2,
        "sonst bliebe der Kanal fuer immer ohne Liste",
    )
    check("mit neuer ID", third["message_id"] != first["message_id"])

    os.unlink(path)


def test_nobody_gets_pinged():
    """Die Liste besteht fast nur aus Erwaehnungen."""
    print("\nEs wird niemand angepingt")

    from api.routes import teamlist as route

    path = _prepared()
    guild = Guild()
    _run_route(lambda: route.publish(100, {}, bot=Bot(guild)), path)

    check("es wurde ueberhaupt gesendet", bool(guild.mentions))

    # Der zweite Aufruf BEARBEITET. Ohne ihn blieb die Luecke offen:
    # das Senden war gesperrt, das Bearbeiten nicht -- und genau das
    # passiert danach bei jeder Rollenaenderung, also staendig.
    _run_route(lambda: route.publish(100, {}, bot=Bot(guild)), path)
    check(
        "es wurde auch bearbeitet",
        len(guild.mentions) >= 2,
        f"-> {len(guild.mentions)} Aufrufe",
    )

    for index, entry in enumerate(guild.mentions):
        wo = "beim Senden" if index == 0 else "beim Bearbeiten"
        check(f"{wo} ist allowed_mentions gesetzt", entry is not None)
        if entry is None:
            continue
        check(f"{wo}: niemand einzeln", not entry.users)
        check(f"{wo}: keine Rolle", not entry.roles)
        check(f"{wo}: nicht @everyone", not entry.everyone)

    os.unlink(path)


def test_publishing_needs_a_channel_and_groups():
    print("\nOhne Kanal oder Gruppen wird nicht gesendet")

    from api.routes import teamlist as route

    # Keine Gruppen.
    path = _prepared(groups=[])
    status = 0
    try:
        _run_route(lambda: route.publish(100, {}, bot=Bot(Guild())), path)
    except Exception as error:
        status = getattr(error, "status_code", 0)
    check("ohne Gruppen wird abgelehnt", status == 400,
          "eine leere Liste zu senden hilft niemandem")
    os.unlink(path)

    # Kein Kanal.
    path = _prepared({"channel_id": ""})
    guild = Guild()
    status = 0
    try:
        _run_route(lambda: route.publish(100, {}, bot=Bot(guild)), path)
    except Exception as error:
        status = getattr(error, "status_code", 0)
    check("ohne Kanal ebenso", status == 400)
    # Und es darf wirklich nichts gesendet worden sein. Die Pruefung
    # auf den Statuscode allein blieb gruen, als die Route weiterlief
    # -- der Fehler kam dann von woanders, die Nachricht war aber
    # schon raus.
    check(
        "und es wurde nichts gesendet",
        len(guild.channel.sent) == 0,
        f"-> {len(guild.channel.sent)} Nachrichten trotz Fehler",
    )
    os.unlink(path)

    # Zwei Ebenen, zwei Pruefungen -- und beide muessen einzeln
    # greifen.
    #
    # Sie decken sich naemlich gegenseitig ab: nimmt man die eine
    # heraus, faengt die andere den Fall trotzdem, und der Test bleibt
    # gruen. Genau das ist zweimal passiert. Deshalb wird jede Ebene
    # fuer sich geprueft.
    from utils import teamlist_render as renderer

    # (a) Der Renderer allein.
    guild2 = Guild()
    result = asyncio.run(
        renderer.publish(Bot(guild2), guild2, {"channel_id": ""}, GROUPS)
    )
    check("der Renderer meldet den fehlenden Kanal", result["ok"] is False)
    check("mit Begruendung", "Kanal" in result["reason"])
    # Und zwar mit DIESER Begruendung. Ohne die fruehe Pruefung liefe
    # der Aufruf in `get_channel("")` und meldete "Den eingestellten
    # Kanal gibt es nicht mehr" -- eine irrefuehrende Auskunft, denn
    # es war nie einer eingestellt.
    check(
        "und der richtigen",
        result["reason"] == "Kein Kanal eingestellt.",
        f"-> {result['reason']!r}",
    )
    check(
        "und fasst nichts an",
        len(guild2.channel.sent) == 0,
        "es wurde trotz fehlendem Kanal gesendet",
    )

    # (b) Die Route allein -- am Renderer vorbei. Sie muss den Fall
    # ABLEHNEN, bevor sie ihn ueberhaupt aufruft: der Nutzer soll eine
    # Fehlermeldung bekommen, keinen stillen Nichtstuer.
    route_src = strip_py(
        open(os.path.join(BOT, "api", "routes", "teamlist.py"),
             encoding="utf-8").read()
    )
    block = route_src.split("async def publish(")[1].split("@router")[0]
    guarded = re.search(
        r'if not config\.get\("channel_id"\):[\s\S]{0,150}?raise HTTPException',
        block,
    )
    check(
        "die Route lehnt den fehlenden Kanal selbst ab",
        bool(guarded),
        "sie verliesse sich auf den Renderer -- der meldet nur, wirft nicht",
    )
    # Und sie darf den Renderer dann gar nicht erst rufen.
    check(
        "und zwar vor dem Aufruf",
        bool(guarded)
        and block.index('if not config.get("channel_id")')
        < block.index("renderer.publish"),
        "sonst laeuft der Aufruf trotzdem",
    )


def test_removing_takes_the_message_with_it():
    """Eine Liste, die niemand mehr aktualisiert, ist schlimmer als
    keine: sie sieht richtig aus und ist es nicht."""
    print("\nEntfernen loescht auch die Nachricht")

    from api.routes import teamlist as route

    path = _prepared()
    guild = Guild()
    bot = Bot(guild)

    sent = _run_route(lambda: route.publish(100, {}, bot=bot), path)
    message = guild.channel.messages[int(sent["message_id"])]

    _run_route(lambda: route.remove(100, True, bot=bot), path)
    check("die Nachricht ist weg", message.deleted)

    answer = _run_route(lambda: route.get_all(100, bot=bot), path)
    check("die Einstellungen sind vergessen",
          not answer["config"]["enabled"] and not answer["groups"])

    os.unlink(path)


# ------------------------------------------------------------------ #
# 3. Was das Dashboard bekommt
# ------------------------------------------------------------------ #
def test_the_dashboard_gets_usable_roles():
    print("\nDas Dashboard bekommt brauchbare Rollen")

    from api.routes import teamlist as route

    path = _prepared()
    answer = _run_route(lambda: route.get_all(100, bot=Bot(Guild())), path)
    names = [r["name"] for r in answer["roles"]]

    check("@everyone faellt heraus", "@everyone" not in names,
          "die haette jeder")
    check("verwaltete Rollen ebenso", "BotRolle" not in names,
          "eine Bot-Rolle ergibt keine Liste von Menschen")
    check("die hoechste Rolle steht oben", names[0] == "Inhaber", str(names))
    check(
        "die IDs sind Zeichenketten",
        all(isinstance(r["id"], str) for r in answer["roles"]),
        "17-20 Ziffern sind groesser als JavaScripts sicherer Bereich",
    )
    check("die Mitgliederzahl kommt mit",
          any(r["members"] == 2 for r in answer["roles"]))
    check("Kanaele auch", bool(answer["channels"]))
    check("und die Zeilenformen", "quote" in answer["styles"])

    os.unlink(path)


def test_status_is_offered_only_when_it_works():
    """Ohne presences-Intent waere jeder »offline«."""
    print("\nStatus wird nur angeboten, wenn er etwas sagt")

    from api.routes import teamlist as route

    path = _prepared()
    ohne = _run_route(lambda: route.get_all(100, bot=Bot(Guild())), path)
    check(
        "ohne Intent wird es nicht angeboten",
        ohne["can_show_status"] is False,
        "sonst stuende bei jedem ein grauer Punkt",
    )

    mit = _run_route(
        lambda: route.get_all(100, bot=Bot(Guild(presences=True))), path
    )
    check("mit Intent schon", mit["can_show_status"] is True)
    os.unlink(path)

    # Und der Renderer darf ohne Intent keinen Status setzen.
    from utils import teamlist_render as renderer

    guild = Guild()
    collected = renderer.collect(guild, GROUPS, want_status=True)
    has_status = any(
        "status" in entry for entries in collected.values() for entry in entries
    )
    check("und der Aufbau setzt keinen", not has_status)

    # `member_status` einzeln: das ist die Stelle, an der der Intent
    # geprueft wird. Ohne diesen Fall blieb der Test gruen, als die
    # Pruefung ausgebaut war -- die Testmitglieder haben schlicht kein
    # `status`-Attribut, also kam ohnehin None heraus.
    class MitStatus:
        status = type("S", (), {"value": "online"})()

    check(
        "ohne Intent kommt kein Status, auch wenn Discord einen liefert",
        renderer.member_status(guild, MitStatus()) is None,
        "es stuende bei jedem ein Punkt, der nichts bedeutet",
    )
    check(
        "mit Intent schon",
        renderer.member_status(Guild(presences=True), MitStatus()) == "🟢",
    )

    # Und im fertigen Text darf dann auch wirklich einer stehen.
    path2 = _prepared({"show_status": True})
    mit = Guild(presences=True)
    for member in mit.owner_role.members:
        member.status = type("S", (), {"value": "online"})()
    answer = _run_route(lambda: route.preview(100, bot=Bot(mit)), path2)
    check("und er landet im Text", "🟢" in answer["text"],
          answer["text"][:100])
    os.unlink(path2)


def test_duplicates_are_reported():
    print("\nWer in zwei Gruppen steht, wird gemeldet")

    from api.routes import teamlist as route

    path = _prepared()
    guild = Guild()
    Member(206, "Doppel", [guild.owner_role, guild.mod_role])

    answer = _run_route(lambda: route.preview(100, bot=Bot(guild)), path)
    check("das doppelte Mitglied faellt auf", "206" in answer["duplicates"])
    # Fuenf verschiedene Menschen: Zoe, Anton, Mia, Ben und Doppel.
    # Doppel steht in zwei Gruppen, zaehlt aber einmal -- der Bot
    # zaehlt nicht doppelt.
    check("und nur einmal gezaehlt", answer["total"] == 5,
          f"-> {answer['total']}")
    # Die Gegenprobe: in den Gruppen steht er sehr wohl zweimal.
    check(
        "in den Gruppen taucht er zweimal auf",
        answer["counts"]["1"] == 3 and answer["counts"]["3"] == 2,
        f"-> {answer['counts']}",
    )
    os.unlink(path)


# ------------------------------------------------------------------ #
# 4. Der Speicher
# ------------------------------------------------------------------ #
def test_the_store_keeps_order_and_rejects_doubles():
    print("\nDer Speicher haelt die Reihenfolge")

    async def scenario(db, store):
        await store.save_groups(db, 100, [
            {"role_id": "3", "label": "Drei"},
            {"role_id": "1", "label": "Eins"},
            {"role_id": "2", "label": "Zwei"},
        ])
        order = [g["label"] for g in await store.get_groups(db, 100)]
        check("die Reihenfolge bleibt, wie sie kam",
              order == ["Drei", "Eins", "Zwei"], str(order))

        # Dieselbe Rolle zweimal waere eine Gruppe, die sich
        # wiederholt -- und die Mitglieder staenden doppelt da.
        await store.save_groups(db, 100, [
            {"role_id": "1", "label": "A"},
            {"role_id": "1", "label": "B"},
        ])
        groups = await store.get_groups(db, 100)
        check("dieselbe Rolle kommt nur einmal vor", len(groups) == 1,
              f"-> {len(groups)}")

        # Mehr als erlaubt wird abgeschnitten.
        await store.save_groups(db, 100, [
            {"role_id": str(i)} for i in range(1, store.MAX_GROUPS + 10)
        ])
        groups = await store.get_groups(db, 100)
        check("die Obergrenze greift", len(groups) == store.MAX_GROUPS,
              f"-> {len(groups)}")

        # Ein Eintrag ohne Rolle ist keiner.
        await store.save_groups(db, 100, [
            {"label": "ohne Rolle"}, {"role_id": "7"},
        ])
        groups = await store.get_groups(db, 100)
        check("ein Eintrag ohne Rolle faellt weg", len(groups) == 1)

    asyncio.run(_with_db(scenario))


def test_ids_come_back_as_text():
    """Discord-IDs sind groesser als JavaScripts sicherer Bereich."""
    print("\nIDs kommen als Text zurueck")

    async def scenario(db, store):
        await store.save_config(db, 100, {
            "channel_id": "1530378233579704370",
            "message_id": "1530378233579704371",
        })
        config = await store.get_config(db, 100)
        check("die Kanal-ID ist Text",
              config["channel_id"] == "1530378233579704370",
              f"-> {config['channel_id']!r}")
        check("die Nachrichten-ID auch",
              config["message_id"] == "1530378233579704371")

        # Die Probe: als Zahl gelesen waere die letzte Stelle falsch.
        check(
            "und sie ueberlebt die Umwandlung",
            str(int(config["channel_id"])) == "1530378233579704370",
            "JavaScript rundet hier stillschweigend",
        )

        await store.save_groups(db, 100, [{"role_id": "1530378233579704372"}])
        groups = await store.get_groups(db, 100)
        check("die Rollen-ID ebenso",
              groups[0]["role_id"] == "1530378233579704372")

    asyncio.run(_with_db(scenario))


def test_defaults_need_no_row():
    """Ein Server ohne Einrichtung darf kein Sonderfall sein."""
    print("\nOhne Eintrag kommen die Voreinstellungen")

    async def scenario(db, store):
        config = await store.get_config(db, 999)
        check("es kommt etwas zurueck", config is not None)
        check("und zwar ausgeschaltet", config["enabled"] is False)
        check("mit leerem Kanal", config["channel_id"] == "")
        check("und einer Vorgabe fuer die Ueberschrift",
              bool(config["title"]))

    asyncio.run(_with_db(scenario))


# ------------------------------------------------------------------ #
# 5. Aktuell bleiben
# ------------------------------------------------------------------ #
def test_it_listens_to_the_right_events():
    """Vier Ereignisse, jedes deckt einen eigenen Fall ab."""
    print("\nDer Bot hoert auf die richtigen Ereignisse")

    src = open(
        os.path.join(BOT, "cogs", "events", "teamlist.py"), encoding="utf-8"
    ).read()
    body = strip_py(src)

    for event in ("on_member_update", "on_member_remove",
                  "on_guild_role_delete", "on_guild_role_update"):
        check(f"{event} gibt es", f"async def {event}" in body)
        # Ohne Dekorator ruft discord.py die Funktion nie auf. Genau
        # diese Falle ist hier schon mehrfach zugeschlagen.
        pattern = re.compile(
            r"@commands\.Cog\.listener\(\)\s*\n\s*async def " + event
        )
        check(f"und ist als Listener angemeldet", bool(pattern.search(body)),
              "ohne Dekorator laeuft er nie")

    # on_member_update feuert auch bei Spitznamen und Zeitstrafen. Ohne
    # Filter waeren das bei einem grossen Server hunderte Aufrufe pro
    # Minute, von denen keiner die Teamliste betrifft.
    block = body.split("async def on_member_update")[1].split("async def")[0]
    check(
        "Spitznamen loesen keine Auffrischung aus",
        "set(before.roles) == set(after.roles)" in block,
        "sonst laeuft der Bot bei jeder Kleinigkeit los",
    )

    # Der Cog muss auch WIRKLICH geladen werden.
    #
    # `cogs/__init__.py` importiert jeden Cog einzeln und meldet ihn
    # per `add_cog` an -- ein Cog, der dort fehlt, existiert als Datei
    # und laeuft trotzdem nie. Genau das war hier zuerst der Fall: der
    # Boot-Test zaehlte weiter 148 statt 149.
    init = open(
        os.path.join(BOT, "cogs", "__init__.py"), encoding="utf-8"
    ).read()
    check(
        "der Cog wird importiert",
        "from .events.teamlist import TeamList" in init,
        "sonst kennt ihn niemand",
    )
    check(
        "und angemeldet",
        "await bot.add_cog(TeamList(bot))" in init,
        "ein Import allein laedt keinen Cog",
    )

    check("es gibt die regelmaessige Runde", "@tasks.loop" in body)
    check(
        "sie wartet auf den Bot",
        "wait_until_ready" in body,
        "sonst laeuft die erste Runde, bevor er seine Server kennt",
    )
    # Der innere `except` -- der aeussere faengt nur das Laden der
    # Liste. Eine Suche nach "except Exception" im ganzen Rumpf blieb
    # gruen, als der innere Zweig `raise` machte.
    loop_body = body.split("async def refresh_loop")[1]
    inner = re.search(
        r"for guild_id in guild_ids:[\s\S]{0,400}?except Exception[\s\S]{0,200}",
        loop_body,
    )
    check("die Schleife faengt Fehler ab", bool(inner))
    check(
        "ein kaputter Server haelt die anderen nicht auf",
        bool(inner) and "raise" not in inner.group(0),
        "ein raise hier beendet die ganze Runde",
    )

    # Und das Verhalten: ein Server, der wirft, darf die anderen nicht
    # mitnehmen.
    from utils import teamlist_render as renderer

    seen = []

    async def kaputt(bot, guild_id):
        seen.append(guild_id)
        if guild_id == 2:
            raise RuntimeError("kaputt")
        return {"ok": True, "reason": "", "message_id": "1"}

    original = renderer.refresh_guild
    renderer.refresh_guild = kaputt
    try:
        async def runde():
            # Genau die Schleife aus dem Cog, ohne discord.py.
            for guild_id in (1, 2, 3):
                try:
                    await renderer.refresh_guild(None, guild_id)
                except Exception:
                    pass

        asyncio.run(runde())
    finally:
        renderer.refresh_guild = original

    check(
        "nach dem Fehler geht es weiter",
        seen == [1, 2, 3],
        f"-> {seen}",
    )


def test_changes_are_collected_before_writing():
    """Fuenf Rollen nacheinander sind fuenf Ereignisse."""
    print("\nMehrere Aenderungen werden gesammelt")

    from utils import teamlist_store as store

    check("es gibt eine Sammelpause", hasattr(store, "DEBOUNCE_SECONDS"))
    check("sie ist kurz genug fuer »sofort«",
          0 < store.DEBOUNCE_SECONDS <= 10,
          f"-> {store.DEBOUNCE_SECONDS}")
    check("und es gibt die regelmaessige Runde",
          store.REFRESH_SECONDS >= 60, f"-> {store.REFRESH_SECONDS}")

    src = strip_py(
        open(os.path.join(BOT, "utils", "teamlist_render.py"),
             encoding="utf-8").read()
    )
    block = src.split("def schedule(")[1]
    check(
        "eine laufende Auffrischung wird verworfen",
        "old.cancel()" in block,
        "sonst schreibt der Bot fuenfmal statt einmal",
    )
    check("und eine neue angesetzt", "create_task" in block or
          "ensure_future" in block)

    # Jetzt gegen das Verhalten: fuenf Aenderungen kurz hintereinander
    # duerfen genau EINE Auffrischung ergeben.
    #
    # Eine Suche nach `old.cancel()` blieb gruen, als der Aufruf unter
    # `if False:` stand.
    from utils import teamlist_render as renderer

    runs = {"n": 0}

    async def fake_refresh(bot, guild_id):
        runs["n"] += 1
        return {"ok": True, "reason": "", "message_id": "1"}

    original_refresh = renderer.refresh_guild
    original_pause = store.DEBOUNCE_SECONDS
    renderer.refresh_guild = fake_refresh
    store.DEBOUNCE_SECONDS = 0.05

    async def five_changes():
        for _ in range(5):
            renderer.schedule(Bot(Guild()), 100)
            await asyncio.sleep(0.005)
        # Warten, bis die Pause vorbei ist.
        await asyncio.sleep(0.3)

    try:
        asyncio.run(five_changes())
    finally:
        renderer.refresh_guild = original_refresh
        store.DEBOUNCE_SECONDS = original_pause

    check(
        "fuenf Aenderungen ergeben eine Auffrischung",
        runs["n"] == 1,
        f"-> {runs['n']} Schreibvorgaenge; Discords Grenze sind 5 pro 5 s",
    )


def test_the_refresh_survives_a_broken_guild():
    """Ein Server, der nicht geht, darf die anderen nicht aufhalten."""
    print("\nEine kaputte Teamliste stoppt die Runde nicht")

    from utils import teamlist_render as renderer

    # Kein Kanal: das muss ein Bericht sein, keine Ausnahme.
    guild = Guild()
    result = asyncio.run(
        renderer.publish(Bot(guild), guild, {"channel_id": ""}, GROUPS)
    )
    check("ohne Kanal kommt ein Bericht", result["ok"] is False)
    check("mit Begruendung", bool(result["reason"]))

    # Kanal gibt es nicht mehr.
    result = asyncio.run(
        renderer.publish(Bot(guild), guild, {"channel_id": "404"}, GROUPS)
    )
    check("ein verschwundener Kanal ebenso", result["ok"] is False)
    check("und wird benannt", "Kanal" in result["reason"])


def test_a_deleted_role_does_not_crash():
    print("\nEine geloeschte Rolle stuerzt nicht ab")

    from utils import teamlist_render as renderer

    guild = Guild()
    collected = renderer.collect(guild, [{"role_id": "999999"}])
    check("sie ergibt eine leere Gruppe", collected["999999"] == [])

    names = renderer.role_names(guild, [{"role_id": "999999"}])
    check("und bekommt einen lesbaren Namen",
          names["999999"] == "Gelöschte Rolle", str(names))


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
        "/teamlist/{guild_id}",
        "/teamlist/{guild_id}/groups",
        "/teamlist/{guild_id}/preview",
        "/teamlist/{guild_id}/publish",
    ):
        check(f"{path} gibt es", path in paths)


def test_the_proxy_knows_the_scope():
    """Ohne Zweig kaeme 404 »Unknown API scope«.

    Genau dieser Fehler ist hier schon viermal passiert.
    """
    print("\nDer Proxy kennt den Bereich")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))
    check("es gibt den Zweig", 'scope === "teamlist"' in proxy)

    block = proxy.split('scope === "teamlist"')[1].split("if (scope ===")[0]
    check("Nichtangemeldete kommen nicht durch", "Not signed in" in block)
    check("der Serverzugang wird geprueft", "verifyGuildAccess" in block)
    check(
        "Schreiben verlangt mehr als Lesen",
        "channels.manage" in block,
        "die Teamliste postet als Bot in einen Kanal",
    )


def test_the_dashboard_is_wired_up():
    print("\nDas Dashboard ist verdrahtet")

    api_src = strip_ts(read_dash("lib", "api.ts"))
    for name in ("teamlist:", "teamlistSave:", "teamlistGroups:",
                 "teamlistPreview:", "teamlistPublish:", "teamlistRemove:"):
        check(f"{name} gibt es", name in api_src)

    check(
        "die Seite gibt es",
        bool(read_dash("app", "dashboard", "guild", "[guildId]", "teamlist",
                       "page.tsx")),
    )
    check("und das Bauteil",
          bool(read_dash("components", "dashboard", "teamlist-panel.tsx")))

    # Alle Navigationswege -- ein fehlender macht die Seite unsichtbar.
    layout = strip_ts(read_dash("app", "dashboard", "layout.tsx"))
    check("die Seitenleiste kennt sie", "/teamlist`" in layout)

    tabs = strip_ts(read_dash("components", "guild-tabs.tsx"))
    check("die Reiterleiste auch", 'slug: "teamlist"' in tabs)

    search = strip_ts(read_dash("components", "global-search.tsx"))
    check("und die Suche", "/teamlist" in search)


def test_both_sides_know_the_same_styles():
    """Ein Tippfehler faellt sonst still auf »quote« zurueck."""
    print("\nBot und Dashboard kennen dieselben Zeilenformen")

    from utils import teamlist_store as store

    panel = strip_ts(read_dash("components", "dashboard",
                               "teamlist-panel.tsx"))
    block = panel.split("const STYLES = [")[1].split("];")[0]
    ids = set(re.findall(r'id: "(\w+)"', block))

    check(
        "das Dashboard bietet nichts an, was der Bot nicht kennt",
        ids <= set(store.STYLES),
        f"unbekannt: {sorted(ids - set(store.STYLES))}",
    )
    check(
        "und der Bot nichts, was fehlt",
        set(store.STYLES) <= ids,
        f"fehlt im Dashboard: {sorted(set(store.STYLES) - ids)}",
    )


def test_the_preview_comes_from_the_bot():
    """Sonst gaebe es das Format zweimal."""
    print("\nDie Vorschau kommt vom Bot")

    panel = strip_ts(read_dash("components", "dashboard",
                               "teamlist-panel.tsx"))
    check("sie wird abgerufen", "api.teamlistPreview(" in panel)
    check(
        "und nicht im Browser gebaut",
        "**\" +" not in panel and "'> ' +" not in panel,
        "zwei Fassungen des Formats laufen auseinander",
    )
    # Die Vorschau muss nach Aenderungen neu geholt werden.
    check(
        "sie folgt den Aenderungen",
        "[loading, pullPreview, groups, config]" in panel,
        "sonst zeigt sie den Stand von vorhin",
    )
    check(
        "mit kurzer Pause",
        "setTimeout(pullPreview" in panel,
        "sonst eine Anfrage je Tastendruck",
    )


def test_the_panel_explains_itself():
    print("\nDas Panel erklaert sich")

    panel = strip_ts(read_dash("components", "dashboard",
                               "teamlist-panel.tsx"))

    check("es gibt eine Discord-Vorschau", "function DiscordPreview(" in panel)
    check("mit Zitat-Strich als Linie", "bg-[#4e5058]" in panel)
    check("Erwaehnungen als Blase", "@Mitglied" in panel)
    # Die Warnungen muessen an der Bedingung HAENGEN, nicht nur
    # irgendwo vorkommen: `{false && (` liess den Text stehen und
    # zeigte ihn nie.
    check(
        "eine zu lange Nachricht wird gemeldet",
        "{preview?.too_long && (" in panel,
        "die Warnung haengt an nichts -- sie erscheint nie",
    )
    check(
        "und der Text dazu steht da",
        "zu lang für Discord" in panel,
    )
    check(
        "doppelte Mitglieder ebenso",
        "{(preview?.duplicates || []).length > 0 && (" in panel,
        "die Warnung erscheint nie",
    )
    check(
        "der Sendeknopf begruendet sich an einer Bedingung",
        "{(!config?.channel_id || groups.length === 0) && (" in panel,
        "der Hinweis steht da und wird nie gezeigt",
    )
    check(
        "der Status-Schalter ist gesperrt, wenn er nichts sagt",
        "disabled={!canStatus}" in panel,
        "sonst schaltet man etwas ein, das nur graue Punkte zeigt",
    )
    check(
        "eine geloeschte Rolle wird benannt",
        "Rolle gelöscht" in panel,
        "sonst sieht die leere Gruppe nach einem Fehler aus",
    )
    check(
        "der Sendeknopf sagt, warum er aus ist",
        "Erst mindestens eine Rolle" in panel,
    )


def main() -> int:
    test_the_message_looks_right()
    test_the_options_change_the_text()
    test_a_long_list_is_cut_not_broken()
    test_it_edits_instead_of_sending_again()
    test_nobody_gets_pinged()
    test_publishing_needs_a_channel_and_groups()
    test_removing_takes_the_message_with_it()
    test_the_dashboard_gets_usable_roles()
    test_status_is_offered_only_when_it_works()
    test_duplicates_are_reported()
    test_the_store_keeps_order_and_rejects_doubles()
    test_ids_come_back_as_text()
    test_defaults_need_no_row()
    test_it_listens_to_the_right_events()
    test_changes_are_collected_before_writing()
    test_the_refresh_survives_a_broken_guild()
    test_a_deleted_role_does_not_crash()
    test_the_routes_are_registered()
    test_the_proxy_knows_the_scope()
    test_the_dashboard_is_wired_up()
    test_both_sides_know_the_same_styles()
    test_the_preview_comes_from_the_bot()
    test_the_panel_explains_itself()

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
