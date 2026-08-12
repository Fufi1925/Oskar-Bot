#!/usr/bin/env python3
"""
Team-Update: die fuenf Befehle, die Rollen und das Dashboard.

Was hier geprueft wird:

  1. Der Rollentausch -- und zwar die **Wirkung**, nicht dass ein Wort
     im Quelltext vorkommt. Attrappen fuer Guild, Member und Rolle,
     echtes SQLite.
  2. Die Reihenfolge: erst geben, dann nehmen -- und wenn das Geben
     scheitert, wird gar nichts entfernt. Ohne diesen zweiten Teil
     machte eine misslungene Befoerderung aus jemandem ein Mitglied
     ohne Rolle.
  3. Die Verwarnungs-Automatik: Schwelle, Verfall, Folge.
  4. Die Ankuendigung: Ping IN der Karte (content= neben einer
     LayoutView ist Discord-Fehler 50035).
  5. Alle sechs Stellen, an denen ein neuer Reiter eingetragen sein
     muss -- die Liste ist aus Erfahrung entstanden, jede einzelne
     wurde schon mindestens einmal vergessen.

Run:  python3 tests/test_team_update.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

from utils import team_update as service  # noqa: E402
from utils import team_update_store as store  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370
USER = 1303627964734246944
ACTOR = 1033826242270609449


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


def read_dash(rel: str) -> str:
    return open(os.path.join(DASH, rel), encoding="utf-8").read()


def strip_py(src: str) -> str:
    """Kommentare und Docstrings raus.

    Sonst trifft eine Suche die eigene Erklaerung darueber statt den
    Code -- eine Falle, in die dieses Repo mehrfach getappt ist.
    """
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        baum = ast.parse(src)
    except SyntaxError:
        return src
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(knoten, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


def strip_ts(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return src


# ══════════════════════════════════════════════════════════════════════
#  Attrappen
# ══════════════════════════════════════════════════════════════════════


class FakeRole:
    def __init__(self, rid, name, position=5, managed=False):
        self.id = rid
        self.name = name
        self.position = position
        self.managed = managed
        self.mention = f"<@&{rid}>"

    def __ge__(self, other):
        return self.position >= other.position

    def __lt__(self, other):
        return self.position < other.position

    def __eq__(self, other):
        return isinstance(other, FakeRole) and other.id == self.id

    def __hash__(self):
        return hash(self.id)


class FakePerms:
    def __init__(self, **kw):
        self.manage_roles = kw.get("manage_roles", True)
        self.manage_guild = kw.get("manage_guild", True)
        self.view_channel = kw.get("view_channel", True)
        self.send_messages = kw.get("send_messages", True)


class _Resp:
    status = 403
    reason = "Forbidden"


class FakeMember:
    def __init__(self, uid, roles=None, name="Mia", manage_guild=True):
        self.id = uid
        self.display_name = name
        self.name = name
        self.mention = f"<@{uid}>"
        self.roles = list(roles or [])
        self.bot = False
        self.guild_permissions = FakePerms(manage_guild=manage_guild)
        self.dms = []
        self.dm_open = True

    @property
    def top_role(self):
        return (max(self.roles, key=lambda r: r.position) if self.roles
                else FakeRole(0, "@everyone", 0))

    async def add_roles(self, *rollen, reason=None):
        for r in rollen:
            if r not in self.roles:
                self.roles.append(r)

    async def remove_roles(self, *rollen, reason=None):
        for r in rollen:
            if r in self.roles:
                self.roles.remove(r)

    async def send(self, *a, **kw):
        if not self.dm_open:
            import discord
            raise discord.Forbidden(_Resp(), "closed")
        self.dms.append(kw.get("view") or (a[0] if a else None))


class FakeChannel:
    def __init__(self, cid, name="team-log", writable=True):
        self.id = cid
        self.name = name
        self.writable = writable
        self.sent = []

    def permissions_for(self, _member):
        return FakePerms(send_messages=self.writable, view_channel=True)

    async def send(self, *a, **kw):
        if not self.writable:
            import discord
            raise discord.Forbidden(_Resp(), "no")
        self.sent.append(kw)
        return object()


class FakeGuild:
    def __init__(self, roles, channels, bot_top=90):
        self.id = GUILD
        self.name = "Uni-Server"
        self.owner_id = 999
        self._roles = {r.id: r for r in roles}
        self._channels = {c.id: c for c in channels}
        self.me = FakeMember(4242, [FakeRole(1, "Bot", bot_top)], "Bot")

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_channel(self, cid):
        return self._channels.get(int(cid))


class FakeBot:
    def get_guild(self, _gid):
        return None


def _texte(view):
    """Alle TextDisplay-Bausteine einer LayoutView, egal wie tief.

    Die Karte besteht aus Container -> TextDisplay; der Ping steckt
    im Text des ersten Blocks. Rekursiv, damit eine spaetere
    Verschachtelung die Pruefung nicht still aushebelt.
    """
    out = []
    for kind in getattr(view, "children", []) or []:
        if hasattr(kind, "content"):
            out.append(kind)
        out.extend(_texte(kind))
    return out


def welt():
    supporter = FakeRole(101, "Supporter", 10)
    moderator = FakeRole(102, "Moderator", 20)
    admin = FakeRole(103, "Administrator", 30)
    zuhoch = FakeRole(104, "Inhaber", 95)
    verwaltet = FakeRole(105, "Nitro", 15, managed=True)
    kanal = FakeChannel(900, "team-log")
    dicht = FakeChannel(901, "gesperrt", writable=False)
    guild = FakeGuild([supporter, moderator, admin, zuhoch, verwaltet],
                      [kanal, dicht])
    return {
        "supporter": supporter, "moderator": moderator, "admin": admin,
        "zuhoch": zuhoch, "verwaltet": verwaltet,
        "kanal": kanal, "dicht": dicht, "guild": guild, "bot": FakeBot(),
    }


# ══════════════════════════════════════════════════════════════════════
#  Verhalten
# ══════════════════════════════════════════════════════════════════════


async def test_defaults():
    print("\nVoreinstellungen")

    s = await store.get_settings(GUILD)
    check("aus, bis jemand einschaltet", s["enabled"] is False)
    check("Kanal frei benutzbar", s["free_channel"] is True)
    check("Grund ist Pflicht", s["require_reason"] is True)
    check("Verwarnungs-Automatik aus", s["warn_threshold"] == 0)
    check("Folge auf »nichts«", s["warn_action"] == store.FOLLOWUP_NONE)
    check("Bewerbungs-Uebernahme aus", s["app_enabled"] is False)
    check("fuenf Aktionen", len(store.ACTIONS) == 5, str(store.ACTIONS))


async def test_settings_roundtrip():
    print("\nEinstellungen sichern und wiederfinden")

    await store.save_settings(GUILD, {
        "enabled": True, "channel_id": "900",
        "staff_roles": ["102", "103"], "team_roles": ["101", "102", "103"],
        "warn_threshold": 2, "warn_action": store.FOLLOWUP_DOWNRANK,
        "warn_downrank_role_id": "101",
    })
    s = await store.get_settings(GUILD)

    check("eingeschaltet", s["enabled"] is True)
    check("Kanal-ID als Text", s["channel_id"] == "900",
          "als Zahl rundet JavaScript die letzte Stelle weg")
    check("Rollen kommen zurueck", s["staff_roles"] == ["102", "103"])
    check("Schwelle gesichert", s["warn_threshold"] == 2)
    check("Folge gesichert", s["warn_action"] == store.FOLLOWUP_DOWNRANK)

    # Muell darf nicht durchrutschen.
    await store.save_settings(GUILD, {
        "warn_action": "loeschen", "warn_threshold": -5,
        "staff_roles": ["abc", "102", "102"],
    })
    s = await store.get_settings(GUILD)
    check("unbekannte Folge faellt auf »nichts«",
          s["warn_action"] == store.FOLLOWUP_NONE, s["warn_action"])
    check("negative Schwelle wird null", s["warn_threshold"] == 0)
    check("keine Buchstaben, keine Doppelten",
          s["staff_roles"] == ["102"], str(s["staff_roles"]))

    await store.save_settings(GUILD, {
        "warn_threshold": 2, "warn_action": store.FOLLOWUP_DOWNRANK,
        "staff_roles": ["102", "103"],
    })


async def test_role_swap():
    print("\nDer Rollentausch wirkt wirklich")

    w = welt()
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    mia = FakeMember(USER, [w["supporter"]], "Mia")
    e = await service.run_action(
        w["bot"], w["guild"], mia, store.ACTION_UPRANK,
        old_role=w["supporter"], new_role=w["moderator"],
        reason="Gute Arbeit", actor_id=ACTOR, settings=s, templates=t,
    )
    check("neue Rolle liegt an", w["moderator"] in mia.roles)
    check("alte Rolle ist weg", w["supporter"] not in mia.roles)
    check("nichts gescheitert", not e.failed, str(e.failed))
    check("angekuendigt", e.announced)
    check("DM zugestellt", e.dm_sent)


async def test_failed_grant_keeps_old_role():
    print("\nScheitert das Geben, bleibt die alte Rolle")

    # Der Fehler, den das verhindert: eine Rolle ueber der Bot-Rolle
    # laesst sich nicht vergeben. Wurde die alte trotzdem entfernt,
    # stand die Person danach ohne alles da -- aus einer gescheiterten
    # Befoerderung wurde ein stiller Rauswurf.
    w = welt()
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    lea = FakeMember(555, [w["supporter"]], "Lea")
    e = await service.run_action(
        w["bot"], w["guild"], lea, store.ACTION_UPRANK,
        old_role=w["supporter"], new_role=w["zuhoch"], reason="Test",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("die zu hohe Rolle wurde nicht vergeben",
          w["zuhoch"] not in lea.roles)
    check("die alte Rolle blieb erhalten", w["supporter"] in lea.roles,
          "sonst steht sie jetzt ohne jede Rolle da")
    check("nichts wurde entfernt", not e.removed, str(e.removed))
    check("und es wurde gemeldet", bool(e.failed), str(e.failed))

    # Und die Gegenprobe: klappt das Geben, wird sehr wohl entfernt.
    tom = FakeMember(556, [w["supporter"]], "Tom")
    e = await service.run_action(
        w["bot"], w["guild"], tom, store.ACTION_UPRANK,
        old_role=w["supporter"], new_role=w["moderator"], reason="T",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("bei Erfolg wird die alte sehr wohl entfernt",
          e.removed == ["Supporter"], str(e.removed))

    # Die Reihenfolge selbst: die alte Rolle darf erst fallen, wenn
    # die neue sitzt. Beobachtet ueber die Rollenlage waehrend des
    # Gebens -- vorher war nur das Ergebnis geprueft, und das sieht
    # bei beiden Reihenfolgen gleich aus.
    verlauf = []

    class Beobachter(FakeMember):
        async def add_roles(self, *rollen, reason=None):
            verlauf.append(("geben", [r.name for r in rollen],
                            [r.name for r in self.roles]))
            await super().add_roles(*rollen, reason=reason)

        async def remove_roles(self, *rollen, reason=None):
            verlauf.append(("nehmen", [r.name for r in rollen],
                            [r.name for r in self.roles]))
            await super().remove_roles(*rollen, reason=reason)

    ana = Beobachter(557, [w["supporter"]], "Ana")
    await service.run_action(
        w["bot"], w["guild"], ana, store.ACTION_UPRANK,
        old_role=w["supporter"], new_role=w["moderator"], reason="T",
        actor_id=ACTOR, settings=s, templates=t,
    )
    schritte = [x[0] for x in verlauf]
    check("beide Schritte passieren", schritte == ["geben", "nehmen"],
          str(schritte))
    if len(verlauf) == 2:
        check("beim Entfernen liegt die neue Rolle schon an",
              "Moderator" in verlauf[1][2], str(verlauf[1][2]),
              )


async def test_blocked_roles():
    print("\nRollen, die der Bot nicht anfassen kann")

    w = welt()
    check("zu hoch wird erkannt",
          "über der Rolle des Bots" in service._blocked(w["guild"], w["zuhoch"]))
    check("von Discord verwaltet wird erkannt",
          "verwaltet" in service._blocked(w["guild"], w["verwaltet"]).lower())
    check("eine normale Rolle geht durch",
          service._blocked(w["guild"], w["supporter"]) == "")
    check("eine geloeschte Rolle wird gemeldet",
          "gibt es nicht mehr" in service._blocked(w["guild"], None),
          "sonst laeuft die Aktion mit einer Rolle weiter, die es nicht gibt")

    # Ohne das Recht »Rollen verwalten« geht gar nichts.
    w["guild"].me.guild_permissions = FakePerms(manage_roles=False)
    check("fehlendes Recht wird erkannt",
          "Rollen verwalten" in service._blocked(w["guild"], w["supporter"]))


async def test_kick_takes_all_team_roles():
    print("\n/teamkick nimmt alle Teamrollen")

    w = welt()
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    mia = FakeMember(USER, [w["moderator"], w["supporter"]], "Mia")
    rollen = service.team_roles_of(w["guild"], mia, s)
    check("beide Teamrollen erkannt", len(rollen) == 2, str(len(rollen)))

    await service.run_action(
        w["bot"], w["guild"], mia, store.ACTION_KICK, old_role=w["moderator"],
        reason="Inaktiv", actor_id=ACTOR, settings=s, templates=t,
    )
    check("keine Teamrolle mehr",
          not [r for r in mia.roles if r in (w["moderator"], w["supporter"])],
          str([r.name for r in mia.roles]))

    akte = await store.get_member(GUILD, USER)
    check("Akte auf inaktiv", akte is not None and not akte["active"])
    check("Austrittsdatum gesetzt", akte and akte["left_at"] > 0)

    # Ohne eigene Team-Rollenliste zaehlen die Zugriffsrollen.
    ohne = {"team_roles": [], "staff_roles": ["102"]}
    check("Rueckfall auf die Zugriffsrollen",
          len(service.team_roles_of(w["guild"],
                                    FakeMember(1, [w["moderator"]]), ohne)) == 1)


async def test_warn_automatic():
    print("\nVerwarnungen: zaehlen, Schwelle, Folge")

    w = welt()
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    tom = FakeMember(777, [w["moderator"]], "Tom")
    e1 = await service.run_action(
        w["bot"], w["guild"], tom, store.ACTION_WARN, reason="Erste",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("erste gezaehlt", e1.warn_count == 1, str(e1.warn_count))
    check("noch keine Folge", e1.followup == store.FOLLOWUP_NONE)
    check("die Rollen bleiben unberuehrt", w["moderator"] in tom.roles)

    e2 = await service.run_action(
        w["bot"], w["guild"], tom, store.ACTION_WARN, reason="Zweite",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("zweite gezaehlt", e2.warn_count == 2, str(e2.warn_count))
    check("Schwelle erreicht -> Rueckstufung",
          e2.followup == store.FOLLOWUP_DOWNRANK, e2.followup)

    folge = await service.apply_followup(w["bot"], w["guild"], tom, s, t, e2,
                                         actor_id=ACTOR)
    check("Folge ausgefuehrt", folge is not None)
    check("Moderator weg", w["moderator"] not in tom.roles)
    check("Supporter drauf", w["supporter"] in tom.roles,
          str([r.name for r in tom.roles]))
    check("die Folge steht getrennt in der Akte",
          folge is not None and folge.action == store.ACTION_DOWNRANK)

    # followup_due allein, ohne den ganzen Ablauf.
    check("Automatik aus -> keine Folge",
          store.followup_due({"warn_threshold": 0,
                              "warn_action": "kick"}, 99)
          == store.FOLLOWUP_NONE)
    check("unter der Schwelle -> keine Folge",
          store.followup_due({"warn_threshold": 3,
                              "warn_action": "kick"}, 2)
          == store.FOLLOWUP_NONE)
    check("Folge »nichts« -> keine Folge",
          store.followup_due({"warn_threshold": 1,
                              "warn_action": "none"}, 5)
          == store.FOLLOWUP_NONE)
    check("erreicht -> Folge",
          store.followup_due({"warn_threshold": 2,
                              "warn_action": "kick"}, 2)
          == store.FOLLOWUP_KICK)


async def test_warn_clear_and_expire():
    print("\nVerwarnungen aufheben und verfallen")

    warns = await store.list_warns(GUILD, 777)
    check("zwei in der Akte", len(warns) == 2, str(len(warns)))

    await store.clear_warn(GUILD, warns[0]["id"])
    check("Zaehler faellt", await store.count_warns(GUILD, 777) == 1)
    check("die Akte behaelt beide",
          len(await store.list_warns(GUILD, 777)) == 2,
          "aufheben darf nicht loeschen")

    import time as _t

    import aiosqlite
    async with aiosqlite.connect(store.DB_PATH) as db:
        await db.execute(
            "UPDATE team_warns SET created_at = ? WHERE guild_id = ?",
            (int(_t.time()) - 40 * 86400, GUILD),
        )
        await db.commit()

    check("ohne Verfallszeit zaehlt alles",
          await store.count_warns(GUILD, 777) == 1)
    check("mit 30 Tagen faellt es raus",
          await store.count_warns(GUILD, 777, expire_days=30) == 0)


async def test_channels():
    print("\nKanalwahl")

    await store.save_settings(GUILD, {"warn_channel_id": "901"})
    s = await store.get_settings(GUILD)

    check("eigener Kanal gewinnt",
          store.channel_for(s, store.ACTION_WARN) == "901")
    check("sonst der allgemeine",
          store.channel_for(s, store.ACTION_UPRANK) == "900")
    check("gar keiner -> leer",
          store.channel_for({"channel_id": ""}, store.ACTION_UPRANK) == "")

    await store.save_settings(GUILD, {"warn_channel_id": ""})


async def test_dead_channel_does_not_abort():
    print("\nEin dichter Kanal bricht die Aktion nicht ab")

    w = welt()
    await store.save_settings(GUILD, {"warn_channel_id": "901"})
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    anna = FakeMember(888, [w["supporter"]], "Anna")
    e = await service.run_action(
        w["bot"], w["guild"], anna, store.ACTION_WARN, reason="Test",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("nicht angekuendigt", not e.announced)
    check("aber mit Begruendung", "Schreibrechte" in e.note, e.note)
    check("die Verwarnung steht trotzdem", e.warn_count >= 1)

    await store.save_settings(GUILD, {"warn_channel_id": ""})


async def test_permission_gates():
    print("\nWer darf, und wo")

    w = welt()
    s = await store.get_settings(GUILD)

    mod = FakeMember(11, [w["moderator"]], "Mod", manage_guild=False)
    fremd = FakeMember(12, [w["supporter"]], "Fremd", manage_guild=False)

    check("Rolle steht auf der Liste", store.may_use(s, mod))
    check("Rolle steht nicht drauf", not store.may_use(s, fremd))
    check("Server verwalten reicht immer",
          store.may_use(s, FakeMember(13, [], "A", manage_guild=True)))
    check("ohne Liste kein Freibrief",
          not store.may_use({"staff_roles": []}, fremd))
    check("None faellt nicht durch", not store.may_use(s, None))

    check("frei: ueberall", store.may_run_here({"free_channel": True}, 1))
    check("gesperrt: der eine geht",
          store.may_run_here({"free_channel": False,
                              "command_channel_id": "900"}, 900))
    check("gesperrt: anderswo nicht",
          not store.may_run_here({"free_channel": False,
                                  "command_channel_id": "900"}, 901))
    check("gesperrt ohne Kanal: wieder ueberall",
          store.may_run_here({"free_channel": False,
                              "command_channel_id": ""}, 999),
          "sonst waere der Befehl nirgends benutzbar")


async def test_render():
    print("\nPlatzhalter")

    w = welt()
    tom = FakeMember(777, [w["moderator"]], "Tom")
    werte = service.build_values(
        w["guild"], tom, old_role=w["moderator"], new_role=w["supporter"],
        reason="Grund mit {geschweift}", signers=[ACTOR, USER],
        actor_id=ACTOR, warn_count=3,
    )
    text = store.render(store.DEFAULT_TEMPLATES[store.ACTION_DOWNRANK], werte)

    check("Erwaehnung eingesetzt", f"<@{tom.id}>" in text)
    check("alte Rolle eingesetzt", "<@&102>" in text)
    check("neue Rolle eingesetzt", "<@&101>" in text)
    check("beide Unterschriften",
          f"<@{ACTOR}>" in text and f"<@{USER}>" in text)
    check("geschweifte Klammer im Grund bricht nichts",
          "{geschweift}" in text,
          "str.format haette hier einen KeyError geworfen")

    # Und derselbe Fall in der Vorlage selbst: ein unbekannter
    # Platzhalter darf stehen bleiben, statt alles abzuraeumen.
    # str.format wuerfe hier einen KeyError, und die Ankuendigung
    # fiele ganz aus -- ohne diesen Aufruf blieb der Test gruen.
    eigen = store.render("Hallo {user}, {unbekannt} und {noch_eins}", werte)
    check("unbekannter Platzhalter bleibt einfach stehen",
          "{unbekannt}" in eigen and f"<@{tom.id}>" in eigen, eigen)

    # Jeder Platzhalter aus der Liste muss auch ersetzt werden.
    alle = store.render(" ".join(store.PLACEHOLDERS), werte)
    uebrig = [p for p in store.PLACEHOLDERS if p in alle]
    check("kein Platzhalter bleibt stehen", not uebrig, str(uebrig))


async def test_announcement_shape():
    print("\nDie Ankuendigung: Ping IN der Karte")

    w = welt()
    await store.save_settings(GUILD, {"ping_user": True})
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    w["kanal"].sent.clear()
    tom = FakeMember(777, [w["moderator"]], "Tom")

    # Eine Vorlage OHNE {user}. Sonst steht die Erwaehnung ohnehin im
    # Text, und die Pruefung darunter deckt sich selbst ab: sie bliebe
    # gruen, auch wenn der Ping ganz wegfiele. Genau so ist diese
    # Mutation beim ersten Durchlauf entwischt.
    t = dict(t)
    t[store.ACTION_UPRANK] = dict(
        t[store.ACTION_UPRANK], body="Jemand wurde befoerdert."
    )

    await service.run_action(
        w["bot"], w["guild"], tom, store.ACTION_UPRANK,
        old_role=w["moderator"], new_role=w["admin"], reason="P",
        actor_id=ACTOR, settings=s, templates=t,
    )
    check("gesendet", bool(w["kanal"].sent))
    if w["kanal"].sent:
        aufruf = w["kanal"].sent[-1]
        check("kein content= neben der LayoutView", "content" not in aufruf,
              "content + LayoutView = Discord-Fehler 50035")
        check("eine View wird geschickt", "view" in aufruf)
        check("allowed_mentions gesetzt", "allowed_mentions" in aufruf)
        erlaubt = aufruf.get("allowed_mentions")
        check("keine Rollen-Pings", getattr(erlaubt, "roles", True) is False)
        check("kein @everyone", getattr(erlaubt, "everyone", True) is False)

        # Der Ping muss IM Text der Karte stehen. Frueher pruefte das
        # nur "kein content=" -- ein Ping, der ganz verschwindet, war
        # damit ebenfalls gruen, und dann benachrichtigt die
        # Ankuendigung niemanden mehr.
        karte = aufruf.get("view")
        gesamt = "".join(
            str(getattr(x, "content", "")) for x in _texte(karte)
        )
        check("die Erwaehnung steht im Text der Karte",
              f"<@{tom.id}>" in gesamt,
              "content= neben einer LayoutView ist Fehler 50035, "
              "also muss der Ping hinein")

    # Ohne Schreibrecht darf gar nicht erst gesendet werden.
    w["dicht"].sent.clear()
    await store.save_settings(GUILD, {"uprank_channel_id": "901"})
    s2 = await store.get_settings(GUILD)
    e = await service.run_action(
        w["bot"], w["guild"], FakeMember(779, [], "Q"), store.ACTION_UPRANK,
        new_role=w["supporter"], reason="P", actor_id=ACTOR,
        settings=s2, templates=t,
    )
    check("in einen dichten Kanal wird nicht gesendet",
          not w["dicht"].sent and not e.announced,
          "das Recht muss VORHER geprueft werden")
    await store.save_settings(GUILD, {"uprank_channel_id": ""})

    await store.save_settings(GUILD, {"ping_user": False})


async def test_history():
    print("\nVerlauf")

    ereignisse = await store.list_events(GUILD)
    check("Ereignisse stehen drin", len(ereignisse) >= 5, str(len(ereignisse)))
    # Nicht ueber die Zeitstempel: die Ereignisse entstehen in
    # derselben Sekunde, damit war ">=" immer wahr und eine
    # umgedrehte Sortierung blieb unentdeckt. Die laufende Nummer
    # steigt dagegen streng.
    check("neueste zuerst", ereignisse[0]["id"] > ereignisse[-1]["id"],
          f'{ereignisse[0]["id"]} .. {ereignisse[-1]["id"]}')
    check("IDs als Text",
          all(isinstance(x["user_id"], str) for x in ereignisse))
    check("jede Aktion hat ein Etikett",
          all(x["label"] for x in ereignisse))

    nur_warn = await store.list_events(GUILD, action=store.ACTION_WARN)
    check("nach Aktion filterbar",
          nur_warn and all(x["action"] == "warn" for x in nur_warn))
    nur_tom = await store.list_events(GUILD, user_id=777)
    check("nach Person filterbar",
          nur_tom and all(x["user_id"] == "777" for x in nur_tom))

    zahlen = await store.count_events(GUILD)
    check("Zaehler kennt alle fuenf", set(zahlen) == set(store.ACTIONS))


async def test_signatures():
    print("\nUnterschriften")

    w = welt()
    s = await store.get_settings(GUILD)
    t = await store.get_templates(GUILD)

    await service.run_action(
        w["bot"], w["guild"], FakeMember(5555, [], "Y"), store.ACTION_JOIN,
        new_role=w["supporter"], reason="T", actor_id=ACTOR,
        settings=s, templates=t,
    )
    ev = (await store.list_events(GUILD, user_id=5555))[0]
    check("der Ausfuehrende unterschreibt immer",
          str(ACTOR) in ev["signers"], str(ev["signers"]))

    await service.run_action(
        w["bot"], w["guild"], FakeMember(5556, [], "Z"), store.ACTION_JOIN,
        new_role=w["supporter"], reason="T", actor_id=ACTOR,
        signers=[ACTOR, USER], settings=s, templates=t,
    )
    ev = (await store.list_events(GUILD, user_id=5556))[0]
    check("kein Doppeleintrag", ev["signers"].count(str(ACTOR)) == 1,
          str(ev["signers"]))
    check("die weitere ist dabei", str(USER) in ev["signers"])

    check("hoechstens fuenf", store.MAX_SIGNERS == 5)
    check("also vier zusaetzliche", store.MAX_EXTRA_SIGNERS == 4)

    # Und die Grenze greift wirklich.
    await service.run_action(
        w["bot"], w["guild"], FakeMember(5557, [], "W"), store.ACTION_JOIN,
        new_role=w["supporter"], reason="T", actor_id=ACTOR,
        signers=[1, 2, 3, 4, 5, 6, 7], settings=s, templates=t,
    )
    ev = (await store.list_events(GUILD, user_id=5557))[0]
    check("mehr als fuenf werden gekappt", len(ev["signers"]) == 5,
          str(len(ev["signers"])))


async def test_from_application():
    print("\nUebernahme aus einer Bewerbung")

    w = welt()
    await store.save_settings(GUILD, {"app_enabled": False})

    neu = FakeMember(1234, [], "Neu")
    ergebnis = await service.from_application(
        w["bot"], w["guild"], neu,
        {"name": "Supporter", "accept_roles": ["101"]}, actor_id=ACTOR,
    )
    check("aus, solange der Schalter aus ist", ergebnis is None,
          "sonst kuendigt der Bot ungefragt an")

    await store.save_settings(GUILD, {"app_enabled": True})
    ergebnis = await service.from_application(
        w["bot"], w["guild"], neu,
        {"name": "Supporter", "accept_roles": ["101"]}, actor_id=ACTOR,
    )
    check("an: Ereignis angelegt", ergebnis is not None)
    check("als Aufnahme verbucht",
          ergebnis is not None and ergebnis.action == store.ACTION_JOIN)

    akte = await store.get_member(GUILD, 1234)
    check("steht in der Akte", akte is not None and akte["active"])
    check("Herkunft vermerkt", akte and akte["source"] == "application",
          str(akte))

    # Auch ohne Rolle in der Kategorie darf es nicht scheitern.
    ergebnis = await service.from_application(
        w["bot"], w["guild"], FakeMember(1235, [], "Ohne"),
        {"name": "Ohne Rolle", "accept_roles": []}, actor_id=ACTOR,
    )
    check("ohne Rolle trotzdem verbucht", ergebnis is not None)

    # Und das Team-Update selbst muss an sein.
    await store.save_settings(GUILD, {"enabled": False})
    ergebnis = await service.from_application(
        w["bot"], w["guild"], FakeMember(1236, [], "X"),
        {"name": "T", "accept_roles": ["101"]}, actor_id=ACTOR,
    )
    check("Modul aus -> keine Uebernahme", ergebnis is None)
    await store.save_settings(GUILD, {"enabled": True})


async def test_templates():
    print("\nVorlagen")

    t = await store.get_templates(GUILD)
    check("alle fuenf da", set(t) == set(store.ACTIONS), str(set(t)))
    check("jede hat einen Text", all(v["body"] for v in t.values()))
    check("jede hat eine DM", all(v["dm_body"] for v in t.values()))
    check("jede ist erst mal an", all(v["enabled"] for v in t.values()))

    await store.save_template(GUILD, store.ACTION_UPRANK,
                              {"title": "Neuer Rang", "body": "{user} rockt."})
    t = await store.get_templates(GUILD)
    check("Titel gesichert", t[store.ACTION_UPRANK]["title"] == "Neuer Rang")
    check("Text gesichert", t[store.ACTION_UPRANK]["body"] == "{user} rockt.")
    check("die anderen unveraendert",
          t[store.ACTION_KICK]["body"]
          == store.DEFAULT_TEMPLATES[store.ACTION_KICK])

    fehler = ""
    try:
        await store.save_template(GUILD, "quatsch", {})
    except ValueError as exc:
        fehler = str(exc)
    check("unbekannte Aktion wird abgelehnt", "Unbekannte" in fehler, fehler)

    # Ausgeschaltet heisst: keine Ankuendigung, aber die Rolle sitzt.
    w = welt()
    await store.save_template(GUILD, store.ACTION_JOIN, {"enabled": False})
    t = await store.get_templates(GUILD)
    e = await service.run_action(
        w["bot"], w["guild"], FakeMember(4321, [], "X"), store.ACTION_JOIN,
        new_role=w["supporter"], reason="T", actor_id=ACTOR,
        settings=await store.get_settings(GUILD), templates=t,
    )
    check("keine Ankuendigung", not e.announced)
    check("aber die Rolle sitzt", e.given == ["Supporter"], str(e.given))
    await store.save_template(GUILD, store.ACTION_JOIN, {"enabled": True})


async def test_schema_survives_old_install():
    print("\nEine alte Installation bekommt die neuen Spalten")

    # Der Fall: die Tabelle gibt es schon, ohne die spaeter
    # dazugekommenen Spalten. CREATE TABLE IF NOT EXISTS aendert
    # daran nichts -- ohne ALTER scheitert jede Abfrage mit
    # "no such column", und der ganze Reiter ist tot.
    import aiosqlite

    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "alt.db")
    async with aiosqlite.connect(pfad) as db:
        await db.execute(
            "CREATE TABLE team_settings (guild_id INTEGER PRIMARY KEY,"
            " enabled INTEGER DEFAULT 0)"
        )
        await db.commit()

    alt = store.DB_PATH
    store.DB_PATH = pfad
    try:
        s = await store.get_settings(GUILD)
        check("laesst sich trotzdem lesen", s is not None)
        await store.save_settings(GUILD, {"app_enabled": True,
                                          "team_roles": ["1"],
                                          "warn_expire_days": 7})
        s = await store.get_settings(GUILD)
        check("app_enabled nachgetragen", s["app_enabled"] is True)
        check("team_roles nachgetragen", s["team_roles"] == ["1"])
        check("warn_expire_days nachgetragen", s["warn_expire_days"] == 7)
    finally:
        store.DB_PATH = alt


# ══════════════════════════════════════════════════════════════════════
#  Verdrahtung
# ══════════════════════════════════════════════════════════════════════


def test_cog_is_registered():
    print("\nDer Cog ist eingetragen")

    src = strip_py(read("cogs/__init__.py"))
    check("importiert", "from .commands.team_update import TeamUpdate" in src)
    check("und wirklich geladen", "await bot.add_cog(TeamUpdate(bot))" in src,
          "ein Import allein laedt keinen Cog")


def test_all_five_commands_exist():
    print("\nAlle fuenf Befehle stehen im Cog")

    # Ueber den Syntaxbaum, nicht per Textsuche: ein Name in einem
    # Kommentar oder eine Funktion ohne Dekorator waeren sonst gruen.
    baum = ast.parse(read("cogs/commands/team_update.py"))
    befehle = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deko in knoten.decorator_list:
            if not isinstance(deko, ast.Call):
                continue
            ziel = deko.func
            name = getattr(ziel, "attr", "")
            if name != "command":
                continue
            for kw in deko.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    befehle.add(kw.value.value)

    for name in ("uprank", "downrank", "teamkick", "teamwarn", "teamanfang"):
        check(f"/{name} ist ein echter Slash-Befehl", name in befehle,
              str(sorted(befehle)))


def test_commands_take_the_right_things():
    print("\nDie Parameter stimmen")

    baum = ast.parse(read("cogs/commands/team_update.py"))
    typen: dict[str, dict[str, str]] = {}
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.AsyncFunctionDef):
            continue
        if knoten.name not in ("uprank", "downrank", "teamkick", "teamwarn",
                               "teamanfang"):
            continue
        felder = {}
        for arg in knoten.args.args:
            if arg.annotation is None:
                continue
            felder[arg.arg] = ast.unparse(arg.annotation)
        typen[knoten.name] = felder

    check("/uprank nimmt nur einen Member als Ziel",
          typen.get("uprank", {}).get("user") == "discord.Member",
          str(typen.get("uprank", {}).get("user")))
    check("/uprank: neue Rolle ist eine Rolle",
          typen.get("uprank", {}).get("neue_rolle") == "discord.Role")
    check("/uprank: alte Rolle ist eine Rolle",
          "discord.Role" in typen.get("uprank", {}).get("alte_rolle", ""))
    check("/downrank: alte Rolle ist Pflicht",
          typen.get("downrank", {}).get("alte_rolle") == "discord.Role")
    check("/teamanfang: Rolle ist eine Rolle",
          typen.get("teamanfang", {}).get("rolle") == "discord.Role")

    # Vier zusaetzliche Unterschriften, jeweils Member.
    for name in ("uprank", "downrank", "teamkick", "teamwarn", "teamanfang"):
        felder = typen.get(name, {})
        unter = [k for k in felder if k.startswith("unterschrift")]
        check(f"/{name} hat vier weitere Unterschriften",
              len(unter) == store.MAX_EXTRA_SIGNERS, str(unter))
        check(f"/{name}: Unterschriften sind Member",
              all("discord.Member" in felder[k] for k in unter))


def test_the_module_is_gated():
    print("\nAusgeschaltet heisst wirklich ausgeschaltet")

    src = strip_py(read("cogs/commands/team_update.py"))
    check("die Vorpruefung liest die Einstellungen",
          "store.get_settings" in src)
    check("und bricht ab, wenn das Modul aus ist",
          'if not settings.get("enabled")' in src)
    check("prueft, wer darf", "store.may_use" in src)
    check("prueft, wo", "store.may_run_here" in src)
    check("und den Pflicht-Grund", 'settings.get("require_reason")' in src)

    # Jeder der fuenf Befehle muss durch die Vorpruefung.
    baum = ast.parse(read("cogs/commands/team_update.py"))
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.AsyncFunctionDef):
            continue
        if knoten.name not in ("uprank", "downrank", "teamkick", "teamwarn",
                               "teamanfang"):
            continue
        koerper = ast.unparse(knoten)
        # uprank/downrank reichen an _rank durch, das selbst prueft.
        check(f"/{knoten.name} laeuft durch die Vorpruefung",
              "_prepare" in koerper or "self._rank" in koerper,
              "sonst wirkt der Befehl auch bei ausgeschaltetem Modul")


def test_hierarchy_is_checked():
    print("\nRangordnung unter Menschen")

    # Die Funktion wirklich aufrufen, nicht nach ihrem Namen suchen.
    # Ein "if False:" darin liesse jede Textsuche gruen -- genau so
    # ist diese Pruefung beim Mutationstest entwischt.
    from cogs.commands.team_update import TeamUpdate

    w = welt()
    cog = TeamUpdate.__new__(TeamUpdate)

    class FakeInteraction:
        def __init__(self, user, guild):
            self.user = user
            self.guild = guild

    mod = FakeMember(21, [w["moderator"]], "Mod", manage_guild=False)
    admin = FakeMember(22, [w["admin"]], "Admin", manage_guild=False)
    inhaber = FakeMember(999, [w["supporter"]], "Inhaber", manage_guild=False)
    kleiner = FakeMember(23, [w["supporter"]], "Klein", manage_guild=False)

    i = FakeInteraction(mod, w["guild"])
    check("wer hoeher steht, ist tabu",
          cog._check_hierarchy(i, admin) != "",
          "sonst stuft ein Moderator den Administrator zurueck")
    check("gleich hoch ist auch tabu",
          cog._check_hierarchy(i, FakeMember(24, [w["moderator"]], "M2")) != "")
    check("tiefer geht", cog._check_hierarchy(i, kleiner) == "")
    check("sich selbst nicht", cog._check_hierarchy(i, mod) != "")
    check("der Serverinhaber ist geschuetzt",
          cog._check_hierarchy(i, inhaber) != "",
          "owner_id muss abgefangen werden")

    # Der Serverinhaber selbst darf alles -- ueber ihm steht niemand.
    besitzer = FakeMember(999, [w["supporter"]], "Chef", manage_guild=True)
    check("der Inhaber darf auch ueber Hoehergestellte bestimmen",
          cog._check_hierarchy(FakeInteraction(besitzer, w["guild"]),
                               admin) == "")

    src = strip_py(read("cogs/commands/team_update.py"))

    baum = ast.parse(read("cogs/commands/team_update.py"))
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.AsyncFunctionDef):
            continue
        if knoten.name not in ("teamkick", "teamwarn", "teamanfang", "_rank"):
            continue
        check(f"{knoten.name} prueft die Rangordnung",
              "_check_hierarchy" in ast.unparse(knoten))


def test_applications_bridge():
    print("\nBeide Wege einer Annahme fuehren ins Team")

    cog = strip_py(read("cogs/commands/applications.py"))
    route = strip_py(read("api/routes/applications.py"))

    check("die Knoepfe in Discord uebernehmen",
          "team_service.from_application" in cog)
    check("das Dashboard auch", "team_service.from_application" in route)
    check("die Route hat einen logger",
          "logger = logging.getLogger" in route,
          "sonst NameError, sobald die Uebernahme scheitert")


def test_persistence_and_schema():
    print("\nDatenbank")

    check("eigene Datei", store.DB_PATH == "db/team_update.db")

    # Ueber die geladene Tabelle, nicht per Textsuche: der Pfad kommt
    # auch in einem Kommentar vor, und ein vertippter Schluessel
    # blieb damit gruen.
    from api import schema_guard

    check("schema_guard kennt die Datei",
          store.DB_PATH in schema_guard.SCHEMA,
          str([k for k in schema_guard.SCHEMA if "team" in k]))
    anweisungen = " ".join(schema_guard.SCHEMA.get(store.DB_PATH, ()))
    for tabelle in ("team_settings", "team_templates", "team_members",
                    "team_events", "team_warns"):
        check(f"{tabelle} wird angelegt", tabelle in anweisungen)

    # schema_guard muss dieselben Spalten nachtragen wie der Store.
    #
    # Nicht per Textsuche im Quelltext: die erste Fassung hatte hier
    # zwei handgepflegte Listen, und genau deren Auseinanderlaufen
    # war der Fehler. Deshalb werden die geladenen Werte verglichen.
    from api import schema_guard

    im_guard = {
        (tabelle, spalte)
        for datei, tabelle, spalte, _ in schema_guard.ADDED_COLUMNS
        if datei == store.DB_PATH
    }
    im_store = {(t, s) for t, s, _ in store.LATE_COLUMNS}
    fehlend = sorted(im_store - im_guard)
    check("schema_guard traegt dieselben Spalten nach",
          not fehlend, str(fehlend))
    check("und jede Spalte der Tabelle ist dabei",
          len(im_store) == len(store.SETTINGS_COLUMNS),
          "eine vergessene Spalte laesst jedes Sichern scheitern")


def test_no_user_data_in_templates():
    print("\nKeine Personendaten in einer Vorlage")

    from utils import template_scan as scan

    check("Team-Update ist erfasst", "teamupdate" in scan.FEATURE_TABLES)
    check("und einer Gruppe zugeordnet", "teamupdate" in scan.FEATURE_GROUPS)

    _, _, tabellen = scan.FEATURE_TABLES["teamupdate"]
    check("nur Einstellungen und Vorlagen gehen mit",
          set(tabellen) == {"team_settings", "team_templates"}, str(tabellen))

    # Der zweite Riegel: auch wenn jemand die Liste oben aendert.
    for tabelle in ("team_members", "team_events", "team_warns"):
        check(f"{tabelle} steht auf der Sperrliste",
              tabelle in scan.NEVER_EXPORT,
              "wer wann verwarnt wurde, ist ein Personendatum")


def test_dashboard_is_wired():
    print("\nDas Dashboard ist an sechs Stellen verdrahtet")

    # Jede dieser Stellen wurde in diesem Repo schon mindestens
    # einmal vergessen -- deshalb stehen sie alle einzeln hier.
    seite = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                         "teamupdate", "page.tsx")
    check("1. die Seite gibt es", os.path.isfile(seite))

    tabs = strip_ts(read_dash("components/guild-tabs.tsx"))
    check("2. Reiter eingetragen", 'slug: "teamupdate"' in tabs)
    check("   und das Icon importiert",
          re.search(r"^\s*UserCog,\s*$", tabs, re.M) is not None,
          "ohne Import faellt die ganze Reiterleiste aus")

    sidebar = strip_ts(read_dash("app/dashboard/layout.tsx"))
    check("3. in der Seitenleiste", "/teamupdate`" in sidebar)
    check("   Icon importiert", "UserCog" in sidebar)

    suche = strip_ts(read_dash("components/global-search.tsx"))
    check("4. in der Suche",
          re.search(r'href:\s*"/dashboard/guild/\{g\}/teamupdate"', suche)
          is not None,
          "ein blosses »/teamupdate« traefe auch »/teamupdate-alt«")
    check("   Icon importiert", "UserCog" in suche)

    api = strip_ts(read_dash("lib/api.ts"))

    # Jeder Aufruf muss auch wirklich auf /teamupdate zeigen. Nur den
    # Namen zu suchen liess eine umbenannte Funktion durchgehen --
    # das Panel ruft sie dann ins Leere.
    aufrufe = dict(re.findall(
        r"(\w+):\s*\([^)]*\)\s*=>\s*\n?\s*request<any>\(\s*`([^`]+)`",
        api,
    ))
    for name, teil in (
        ("getTeamUpdate", "/teamupdate/"),
        ("saveTeamUpdate", "/teamupdate/"),
        ("saveTeamUpdateTemplate", "/templates/"),
        ("teamUpdatePreview", "/preview"),
        ("teamUpdateHistory", "/history"),
        ("teamUpdateMembers", "/members"),
        ("teamUpdateWarns", "/warns/"),
        ("clearAllTeamWarns", "/warns/user/"),
    ):
        ziel = aufrufe.get(name, "")
        check(f"5. {name} zeigt auf {teil}", teil in ziel,
              f"-> {ziel or 'fehlt ganz'}")

    proxy = strip_ts(read_dash("app/api/bot/[...path]/route.ts"))
    check("6. der Proxy kennt den Bereich",
          'scope === "teamupdate"' in proxy,
          "sonst 404 »Unknown API scope« beim ersten Klick")

    # Und die Sicherung dahinter. Der Zweig wird an seiner
    # schliessenden Klammer abgeschnitten -- vorher lief die Suche in
    # den naechsten Zweig hinein und fand dessen verifyGuildAccess,
    # obwohl der eigene keins mehr hatte.
    rest = proxy.split('scope === "teamupdate"', 1)[1]
    ende = rest.find("\n  if (scope ===")
    zweig = rest[:ende if ende > 0 else 1500]
    check("   der Proxy prueft den Serverzugang",
          "verifyGuildAccess" in zweig,
          "sonst kommt jeder Angemeldete an jeden Server")
    check("   und wehrt Nichtangemeldete ab",
          "Not signed in" in zweig)
    check("   und verlangt ein Recht zum Schreiben",
          "roles.manage" in zweig)


def test_beta_marking_agrees():
    print("\nBeta steht in beiden Navigationen")

    tabs = read_dash("components/guild-tabs.tsx")
    sidebar = read_dash("app/dashboard/layout.tsx")

    eintrag = re.search(
        r'\{[^{}]*slug:\s*"teamupdate"[^{}]*\}', tabs, re.S
    )
    check("der Reiter ist als Beta markiert",
          eintrag is not None and 'tag: "beta"' in eintrag.group(0))
    check("und die Seitenleiste sagt dasselbe",
          "Team-Update (Beta)" in sidebar,
          "beide Navigationen muessen sich einig sein")


def test_route_is_registered():
    print("\nDie API-Route haengt am Server")

    server = read("api/server.py")
    check("importiert", "teamupdate" in server.split("include_router")[0])
    check("und eingehaengt",
          'teamupdate.router, prefix="/teamupdate"' in server)


def test_panel_uses_the_shared_toggle():
    print("\nDas Panel benutzt den gemeinsamen Schalter")

    src = strip_ts(read_dash("components/dashboard/teamupdate-panel.tsx"))
    check("SwitchToggle wird aus form-elements geholt",
          re.search(
              r"import\s*\{[^}]*SwitchToggle[^}]*\}\s*from\s*"
              r'"@/components/dashboard/form-elements"', src) is not None,
          "eigene Schalter sind hier dreimal mit 10px Ueberhang gebaut worden")
    check("und auch benutzt", "<SwitchToggle" in src)
    check("keine eigene absolute Bahn",
          "translate-x-6" not in src,
          "das ist genau der Toggle-Fehler von zuletzt")
    check("h-4.5 gibt es in Tailwind nicht", "h-4.5" not in src)

    # Die Aktionen im Panel muessen zu denen im Bot passen.
    im_panel = set(re.findall(r'key:\s*"(\w+)",\s*\n\s*label:', src))
    check("dieselben fuenf Aktionen wie im Bot",
          im_panel == set(store.ACTIONS),
          f"Panel={sorted(im_panel)} Bot={sorted(store.ACTIONS)}")


# ══════════════════════════════════════════════════════════════════════


async def run_async():
    ordner = tempfile.mkdtemp()
    alt = os.getcwd()
    os.chdir(ordner)
    os.makedirs("db", exist_ok=True)
    try:
        await test_defaults()
        await test_settings_roundtrip()
        await test_role_swap()
        await test_failed_grant_keeps_old_role()
        await test_blocked_roles()
        await test_kick_takes_all_team_roles()
        await test_warn_automatic()
        await test_warn_clear_and_expire()
        await test_channels()
        await test_dead_channel_does_not_abort()
        await test_permission_gates()
        await test_render()
        await test_announcement_shape()
        await test_history()
        await test_signatures()
        await test_from_application()
        await test_templates()
        await test_schema_survives_old_install()
    finally:
        os.chdir(alt)


def main() -> int:
    asyncio.run(run_async())

    test_cog_is_registered()
    test_all_five_commands_exist()
    test_commands_take_the_right_things()
    test_the_module_is_gated()
    test_hierarchy_is_checked()
    test_applications_bridge()
    test_persistence_and_schema()
    test_no_user_data_in_templates()
    test_dashboard_is_wired()
    test_beta_marking_agrees()
    test_route_is_registered()
    test_panel_uses_the_shared_toggle()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for line in failures:
            print(f"   {line}")
        return 1
    print("Alle Team-Update-Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
