#!/usr/bin/env python3
"""
Nutzer nachschlagen, sperren, ueberall bannen, Inhaber warnen.

Vier Anforderungen waren der Anlass, und danach ist dieser Test
sortiert:

  1. Zu einer ID sieht man das Profil und **jeden** Server, auf dem die
     Person ist -- auch die, auf die der Betrachter keinen Zugriff hat.
  2. Eine Bot-Sperre, die wirklich sperrt: keine Befehle, kein
     Dashboard-Login, kein Einladen des Bots. Die alte
     ``user_blacklist`` konnte nur das erste.
  3. Bann auf allen Servern -- mit Bestaetigung, Wartezeit und Textfeld.
  4. Warnung an alle Server-Inhaber, ohne dass jemand gebannt wird.

Discord wird durch schlanke Attrappen ersetzt. Das ist hier kein
Notbehelf: geprueft werden soll, *welche* Server ausgewaehlt und
*welche* uebersprungen werden, und das laesst sich mit erfundenen
Rollenordnungen genauer durchspielen als mit einem echten Server.

Run:  python3 tests/test_user_lookup.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import user_lookup as ul  # noqa: E402

failures: list[str] = []

USER = 1303627964734246944
ACTOR = 1033826242270609449


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
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                for i in range(first.lineno - 1, first.end_lineno):
                    lines[i] = ""
    return "\n".join(lines)


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


# ── Attrappen ────────────────────────────────────────────────────────

class FakeRole:
    def __init__(self, name, position):
        self.name, self.position = name, position

    def __gt__(self, other):
        return self.position > other.position

    def __le__(self, other):
        return self.position <= other.position


class FakePerms:
    def __init__(self, **kw):
        self.administrator = kw.get("administrator", False)
        self.ban_members = kw.get("ban_members", False)
        self.view_audit_log = kw.get("view_audit_log", False)
        self.manage_guild = kw.get("manage_guild", False)


class FakeMember:
    def __init__(self, uid, *, top=1, admin=False, name="Wer"):
        self.id, self.bot = uid, False
        self.top_role = FakeRole("Rolle", top)
        self.guild_permissions = FakePerms(administrator=admin)
        self.display_name = name
        self.roles = [FakeRole("@everyone", 0), self.top_role]
        self.joined_at = None

    def __str__(self):
        return self.display_name


class FakeUser:
    def __init__(self, uid, name="Wer"):
        self.id, self.bot = uid, False
        self.display_name = name
        self.sent: list = []

    def __str__(self):
        return self.display_name

    @property
    def display_avatar(self):
        class A:
            url = "https://cdn.discordapp.com/x.png"
        return A()

    @property
    def created_at(self):
        import datetime
        return datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeGuild:
    def __init__(self, gid, name, *, owner_id, members, bot_top=10,
                 bot_can_ban=True, member_count=100):
        self.id, self.name = gid, name
        self.owner_id = owner_id
        self._members = {m.id: m for m in members}
        self.member_count = member_count
        self.icon = None
        self.me = FakeMember(999, top=bot_top, name="Bot")
        self.me.guild_permissions = FakePerms(ban_members=bot_can_ban)
        self.banned: list = []
        self.owner = FakeUser(owner_id, f"Owner{owner_id}")

    @property
    def members(self):
        return list(self._members.values())

    def get_member(self, uid):
        return self._members.get(uid)

    async def ban(self, target, *, reason="", delete_message_seconds=0):
        self.banned.append((getattr(target, "id", target), reason))


class FakeBot:
    def __init__(self, guilds, users=None):
        self.guilds = guilds
        self._users = {u.id: u for u in (users or [])}
        for g in guilds:
            self._users.setdefault(g.owner_id, g.owner)

    def get_user(self, uid):
        return self._users.get(uid)

    async def fetch_user(self, uid):
        if uid in self._users:
            return self._users[uid]
        raise RuntimeError("unbekannt")


def welt():
    """Vier Server: normal, Person ist Inhaber, Bot ohne Recht, Rolle zu hoch."""
    ziel = FakeMember(USER, top=3, name="Boesewicht")

    a = FakeGuild(101, "Alpha", owner_id=501,
                  members=[FakeMember(USER, top=3, name="Boesewicht")],
                  bot_top=10, member_count=500)
    # Beta: die Person ist Inhaberin, ihre Rolle ist aber NIEDRIG.
    #
    # Das ist Absicht. Mit einer hohen Rolle wuerde schon die
    # Rollenordnung den Bann verhindern, und die Pruefung auf
    # Inhaberschaft koennte ersatzlos wegfallen, ohne dass es auffiele --
    # zwei Ebenen, die denselben Fall abdecken. Nur so trennt der Test
    # sie.
    b = FakeGuild(102, "Beta", owner_id=USER,
                  members=[FakeMember(USER, top=1, name="Boesewicht")],
                  bot_top=10, member_count=300)
    c = FakeGuild(103, "Gamma", owner_id=503,
                  members=[FakeMember(USER, top=3, name="Boesewicht")],
                  bot_top=10, bot_can_ban=False, member_count=200)
    d = FakeGuild(104, "Delta", owner_id=504,
                  members=[FakeMember(USER, top=50, name="Boesewicht")],
                  bot_top=10, member_count=100)
    e = FakeGuild(105, "Epsilon", owner_id=505, members=[], member_count=50)

    # Bewusst UNSORTIERT uebergeben. Lagen sie schon nach Groesse
    # geordnet vor, koennte die Sortierung im Code ersatzlos wegfallen,
    # ohne dass ein Test es merkt.
    bot = FakeBot([d, b, a, e, c], users=[FakeUser(USER, "Boesewicht")])
    return bot, (a, b, c, d, e), ziel


# ── 1. Nachschlagen ──────────────────────────────────────────────────

async def test_lookup():
    print("\n1. Alle Server einer Person, auch ohne eigene Rechte")
    bot, (a, b, c, d, e), _ = welt()

    res = await ul.lookup(bot, USER)
    check("Profil gefunden", res["found"] and res["username"] == "Boesewicht")
    check("vier gemeinsame Server", res["guild_count"] == 4,
          f"({res['guild_count']})")

    namen = {g["guild_name"] for g in res["guilds"]}
    check("Server ohne die Person fehlt", "Epsilon" not in namen, f"({namen})")
    check("Server, auf dem sie nur Mitglied ist, ist dabei", "Alpha" in namen)

    per_name = {g["guild_name"]: g for g in res["guilds"]}
    check("Inhaberschaft wird erkannt", per_name["Beta"]["is_owner"])
    check("auf dem eigenen Server nicht bannbar",
          not per_name["Beta"]["bot_can_ban"])
    check("ohne Bann-Recht nicht bannbar", not per_name["Gamma"]["bot_can_ban"])
    check("bei zu hoher Rolle nicht bannbar", not per_name["Delta"]["bot_can_ban"])
    check("sonst bannbar", per_name["Alpha"]["bot_can_ban"])
    check("Zahl der bannbaren stimmt", res["bannable_count"] == 1,
          f"({res['bannable_count']})")

    # Sortierung: der groesste Server zuerst -- sonst ist die Liste bei
    # vierzig Eintraegen nicht lesbar. Die ganze Reihenfolge pruefen,
    # nicht nur den ersten Eintrag: der steht sonst zufaellig richtig.
    check("nach Groesse sortiert",
          [g["guild_name"] for g in res["guilds"]] == ["Alpha", "Beta", "Gamma", "Delta"],
          f"({[g['guild_name'] for g in res['guilds']]})")

    # Eine unbekannte ID darf nicht abstuerzen.
    leer = await ul.lookup(bot, 999888777666555444)
    check("unbekannte ID ergibt ein leeres Ergebnis",
          leer["guild_count"] == 0 and not leer["found"])


# ── 2. Die Bot-Sperre ────────────────────────────────────────────────

async def test_bot_ban():
    print("\n2. Die Sperre wirkt ueberall")
    import aiosqlite

    await ul.ban_from_bot(USER, reason="Nuke-Versuch", actor=str(ACTOR))

    ban = await ul.get_ban(USER)
    check("Sperre gespeichert", ban is not None and ban["reason"] == "Nuke-Versuch")
    check("is_banned meldet True", await ul.is_banned(USER))

    # Der entscheidende Teil: die alte Tabelle muss mitgeschrieben
    # werden. Nur ueber sie greift blacklist_check() in allen Befehlen.
    async with aiosqlite.connect(ul.BLOCK_DB) as db:
        async with db.execute(
            "SELECT 1 FROM user_blacklist WHERE user_id = ?", (str(USER),)
        ) as cur:
            drin = await cur.fetchone() is not None
    check("steht auch in user_blacklist (Befehle)", drin,
          "-> sonst laufen die Befehle der Person weiter")

    check("taucht in der Liste auf",
          any(b["user_id"] == str(USER) for b in await ul.list_bans()))

    check("Aufheben meldet Erfolg", await ul.unban_from_bot(USER))
    check("danach nicht mehr gesperrt", not await ul.is_banned(USER))

    async with aiosqlite.connect(ul.BLOCK_DB) as db:
        async with db.execute(
            "SELECT 1 FROM user_blacklist WHERE user_id = ?", (str(USER),)
        ) as cur:
            noch_drin = await cur.fetchone() is not None
    check("auch aus user_blacklist entfernt", not noch_drin)

    check("zweites Aufheben meldet False", not await ul.unban_from_bot(USER))


def test_ban_wirkt_auf_login_und_invite():
    print("\n   -- und sie greift an den drei Toren --")
    # Tor 1: der Login. Vorher pruefte die Route nur access-Bans.
    acc = strip_py(read("api/routes/access.py"))
    check("Login prueft die Bot-Sperre",
          "user_lookup.get_ban" in acc,
          "-> sonst kommt ein Gesperrter weiter ins Dashboard")
    # Tor 2: bestehende Sitzungen, die bei jedem Aufruf geprueft werden.
    check("die Dauerpruefung prueft sie auch",
          acc.count("user_lookup.get_ban") >= 2,
          "-> sonst bleibt eine offene Sitzung gueltig")
    # Tor 3: den Bot einladen.
    fe = strip_py(read("cogs/events/feature_enforcement.py"))
    check("beim Serverbeitritt wird der Einladende geprueft",
          "user_lookup.is_banned" in fe,
          "-> sonst laedt ein Gesperrter den Bot einfach woanders ein")
    check("und der Inhaber des Servers auch",
          "guild.owner" in fe)


# ── 3. Bann auf allen Servern ────────────────────────────────────────

async def test_ban_everywhere():
    print("\n3. Bann auf allen Servern")
    from utils import user_actions as ua

    bot, (a, b, c, d, e), _ = welt()

    # Erst die Probe -- sie darf nichts tun.
    probe = await ua.ban_everywhere(bot, USER, reason="Test", dry_run=True)
    check("Probe meldet einen bannbaren Server", probe["ok_count"] == 1,
          f"({probe['ok_count']})")
    check("Probe bannt wirklich nichts", not a.banned, f"({a.banned})")
    check("Probe meldet die uebersprungenen", probe["skipped_count"] == 3,
          f"({probe['skipped_count']})")

    res = await ua.ban_everywhere(bot, USER, reason="Nuke", actor=str(ACTOR))
    check("ein Server gebannt", res["ok_count"] == 1, f"({res['ok_count']})")
    check("Alpha hat den Bann bekommen", len(a.banned) == 1, f"({a.banned})")
    check("der Grund steht im Auditlog",
          bool(a.banned) and "Nuke" in a.banned[0][1], f"({a.banned})")

    check("auf dem eigenen Server nicht gebannt", not b.banned)
    check("ohne Recht nicht gebannt", not c.banned)
    check("bei zu hoher Rolle nicht gebannt", not d.banned)
    check("auf fremdem Server ohne die Person nichts", not e.banned)

    gruende = {s["guild_name"]: s["reason"] for s in res["skipped"]}
    check("Grund fuer Beta genannt", "Inhaber" in gruende.get("Beta", ""),
          f"({gruende})")
    check("Grund fuer Gamma genannt", "Recht" in gruende.get("Gamma", ""),
          f"({gruende})")
    check("Grund fuer Delta genannt", "Rolle" in gruende.get("Delta", ""),
          f"({gruende})")

    # Der Vorgang muss im Protokoll stehen.
    verlauf = await ul.recent_actions(USER)
    check("Aktion protokolliert",
          any(v["kind"] == "ban_all" and v["ok_count"] == 1 for v in verlauf),
          f"({verlauf})")


# ── 4. Warnung an die Inhaber ────────────────────────────────────────

async def test_warn_owners():
    print("\n4. Warnung an die Inhaber")
    from utils import user_actions as ua

    bot, (a, b, c, d, e), _ = welt()

    res = await ua.warn_owners(bot, USER, reason="Bitte aufpassen",
                               actor=str(ACTOR))

    # Drei Inhaber: Alpha, Gamma, Delta. Beta faellt raus, weil die
    # Person dort selbst Inhaber ist.
    check("drei Inhaber benachrichtigt", res["ok_count"] == 3,
          f"({res['ok_count']})")
    check("niemand wurde gebannt",
          not a.banned and not c.banned and not d.banned)

    gewarnt = {int(w["owner_id"]) for w in res["warned"]}
    check("der Inhaber von Alpha ist dabei", 501 in gewarnt, f"({gewarnt})")
    check("die Person warnt sich nicht selbst", USER not in gewarnt,
          f"({gewarnt})")

    owner = bot.get_user(501)
    check("die DM ging wirklich raus", len(owner.sent) == 1, f"({owner.sent})")
    if owner.sent:
        check("die DM nutzt kein content=", "content" not in owner.sent[0],
              "-> mit Components V2 antwortet Discord mit 50035")
        check("die DM ist eine View", "view" in owner.sent[0])

    verlauf = await ul.recent_actions(USER)
    check("Warnung protokolliert",
          any(v["kind"] == "warn_owners" for v in verlauf))

    # Und die Probe verschickt nichts.
    bot2, (a2, *_), _ = welt()
    probe = await ua.warn_owners(bot2, USER, reason="x", dry_run=True)
    check("Probe meldet die Zahl", probe["ok_count"] == 3, f"({probe['ok_count']})")
    check("Probe verschickt nichts", not bot2.get_user(501).sent)


# ── 5. Grenzen und Schutz ────────────────────────────────────────────

async def test_schutz_wirkt():
    """
    Die Schutzregeln werden AUFGERUFEN, nicht im Text gesucht.

    Eine Textsuche waere hier wertlos: wer die Pruefung entfernt,
    entfernt auch die Zeichenkette, nach der gesucht wird -- und ein
    Test, der genau dann gruen bleibt, wenn der Schutz weg ist, ist
    schlimmer als keiner.
    """
    print("\n5. Schutz vor Fehlgriffen -- wirklich ausgefuehrt")
    from fastapi import HTTPException

    from api.routes import access as route_mod

    bot, *_ = welt()

    # Der Prueflauf braucht einen Betrachter mit Rechten. `roles` laedt
    # aus einer Datei, die es im Testverzeichnis nicht gibt -- also wird
    # die Rechtefrage vorruebergehend beantwortet.
    import utils.dashboard_authority as authority

    echte_global = authority.may_act_globally
    echte_owner = authority.is_owner
    bot_owner_ids = {"555000111222333444"}

    authority.may_act_globally = lambda b, a, p: str(a) == str(ACTOR)
    authority.is_owner = lambda b, u: str(u) in bot_owner_ids
    route_mod.authority = authority

    async def erwarte_fehler(coro, stichwort, name):
        try:
            await coro
        except HTTPException as exc:
            check(name, stichwort.lower() in str(exc.detail).lower(),
                  f"(bekam: {exc.detail})")
        else:
            check(name, False, "-> kein Fehler, die Aktion lief durch")

    try:
        # Ohne Rechte darf niemand nachschlagen.
        await erwarte_fehler(
            route_mod.lookup_user(str(USER), actor="999999999999999999", bot=bot),
            "darfst", "Nachschlagen ohne Rechte wird abgelehnt")

        # Ungueltige IDs.
        for schlecht in ("abc", "12", "1" * 25, ""):
            await erwarte_fehler(
                route_mod.lookup_user(schlecht, actor=str(ACTOR), bot=bot),
                "id", f"ungueltige ID '{schlecht[:6]}' wird abgelehnt")

        # Sich selbst sperren.
        await erwarte_fehler(
            route_mod.create_bot_ban(
                {"user_id": str(ACTOR), "reason": "x", "actor": str(ACTOR)}, bot=bot),
            "selbst", "man kann sich nicht selbst sperren")

        # Einen Bot-Inhaber sperren.
        await erwarte_fehler(
            route_mod.create_bot_ban(
                {"user_id": "555000111222333444", "reason": "x", "actor": str(ACTOR)},
                bot=bot),
            "inhaber", "Bot-Inhaber lassen sich nicht sperren")

        # Und ueberall bannen.
        await erwarte_fehler(
            route_mod.mass_action(
                {"user_id": "555000111222333444", "kind": "ban_all",
                 "reason": "x", "actor": str(ACTOR)}, bot=bot),
            "inhaber", "Bot-Inhaber lassen sich nicht ueberall bannen")

        # Ein Bann ohne Grund.
        await erwarte_fehler(
            route_mod.mass_action(
                {"user_id": str(USER), "kind": "ban_all", "actor": str(ACTOR)}, bot=bot),
            "grund", "ein Bann ohne Grund wird abgelehnt")

        # Unbekannte Massnahme.
        await erwarte_fehler(
            route_mod.mass_action(
                {"user_id": str(USER), "kind": "loeschen", "reason": "x",
                 "actor": str(ACTOR)}, bot=bot),
            "kind", "unbekannte Massnahme wird abgelehnt")

        # Der Zwischenspeicher muss nach einer Sperre neu geladen werden.
        # Sonst laufen die Befehle der Person bis zum naechsten Neustart
        # weiter -- blacklist_check() liest aus dem Speicher, nicht aus
        # der Datei.
        import utils.feature_gates as gates
        geladen = {"n": 0}
        echt_invalidate = gates.invalidate_blacklist
        echt_refresh = gates.refresh_blacklist

        async def zaehl_refresh():
            geladen["n"] += 1

        gates.invalidate_blacklist = lambda: None
        gates.refresh_blacklist = zaehl_refresh
        route_mod.feature_gates = gates
        try:
            await route_mod.create_bot_ban(
                {"user_id": str(USER), "reason": "Test", "actor": str(ACTOR)}, bot=bot)
            check("Sperre laedt den Zwischenspeicher neu", geladen["n"] >= 1,
                  "-> sonst greift sie erst nach einem Neustart")

            geladen["n"] = 0
            await route_mod.delete_bot_ban(str(USER), actor=str(ACTOR), bot=bot)
            check("Aufheben laedt ihn ebenfalls neu", geladen["n"] >= 1)
        finally:
            gates.invalidate_blacklist = echt_invalidate
            gates.refresh_blacklist = echt_refresh
    finally:
        authority.may_act_globally = echte_global
        authority.is_owner = echte_owner


def test_actor_kommt_an():
    """
    Der Aufrufer muss die Route ueberhaupt erreichen.

    Der Fehler, der das ausgeloest hat: der Dashboard-Proxy haengte die
    ID des Angemeldeten nur bei POST/PATCH (im Koerper) und bei DELETE
    (als Parameter) an. Eine **lesende** Route mit Rechtepruefung fiel
    durch beide Raster, bekam ``actor=""`` und antwortete zuverlaessig
    mit 403 -- fuer jeden, auch fuer den Inhaber.

    Deshalb wird hier nicht nur der Proxy geprueft, sondern der
    Abgleich: **jede** GET-Route, die eine Rechtepruefung macht, muss
    einen actor bekommen koennen. Das faengt auch die naechste solche
    Route ab, die jemand anlegt.
    """
    print("\n5c. Der Aufrufer erreicht auch lesende Routen")
    proxy_pfad = os.path.join(
        BOT, "..", "dashboard", "app", "api", "bot", "[...path]", "route.ts"
    )
    proxy = open(proxy_pfad, encoding="utf-8").read()
    proxy_ohne_kommentare = "\n".join(
        z for z in re.sub(r"/\*.*?\*/", "", proxy, flags=re.S).splitlines()
        if not z.strip().startswith("//")
    )

    # Der actor darf nicht mehr an der Methode haengen.
    nur_delete = bool(re.search(
        r'request\.method === "DELETE" && actorId', proxy_ohne_kommentare))
    check("actor haengt nicht mehr an DELETE", not nur_delete,
          "-> lesende Routen bekaemen sonst nie einen")
    check("actor wird gesetzt, sobald jemand angemeldet ist",
          bool(re.search(r'if \(actorId\) \{\s*url\.searchParams\.set\("actor", actorId\)',
                         proxy_ohne_kommentare)))
    # Und ohne Sitzung darf kein Wert aus dem Browser durchrutschen.
    check("ohne Sitzung wird ein mitgeschickter actor verworfen",
          'url.searchParams.delete("actor")' in proxy_ohne_kommentare,
          "-> sonst schreibt sich jeder eine fremde ID in die URL")

    # Jede GET-Route mit Rechtepruefung -- auch kuenftige.
    baum = ast.parse(read("api/routes/access.py"))
    lesend_mit_pruefung = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        ist_get = any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "get"
            for d in knoten.decorator_list
        )
        prueft = any(
            isinstance(u, ast.Call) and getattr(u.func, "id", "") == "_require_global"
            for u in ast.walk(knoten)
        )
        if ist_get and prueft:
            hat_parameter = any(a.arg == "actor" for a in knoten.args.args)
            lesend_mit_pruefung.append((knoten.name, hat_parameter))

    check("es gibt solche Routen (sonst prueft das hier nichts)",
          len(lesend_mit_pruefung) >= 2, f"({lesend_mit_pruefung})")
    ohne = [n for n, hat in lesend_mit_pruefung if not hat]
    check("jede nimmt einen actor entgegen", not ohne, f"({ohne})")

    # Und die Meldung muss die beiden Faelle trennen -- wirklich
    # ausgefuehrt, nicht im Text gesucht: eine Textsuche traefe auch den
    # Kommentar, der die Regel beschreibt, und bliebe gruen, wenn nur
    # die Regel selbst wegfaellt.
    from fastapi import HTTPException

    from api.routes import access as route_mod

    for leerer_actor in ("", "   ", None):
        try:
            route_mod._require_global(None, leerer_actor, "etwas tun")
        except HTTPException as exc:
            check(f"leerer actor ({leerer_actor!r}) ergibt 401",
                  exc.status_code == 401, f"(war {exc.status_code})")
        else:
            check(f"leerer actor ({leerer_actor!r}) wird abgelehnt", False,
                  "-> lief einfach durch")

    # Die Prueflogik selbst muss aber weiter greifen: ein vorhandener,
    # aber unberechtigter Aufrufer bekommt 403 -- nicht 401.
    import utils.dashboard_authority as authority

    echt = authority.may_act_globally
    authority.may_act_globally = lambda b, a, p: False
    route_mod.authority = authority
    try:
        route_mod._require_global(None, "123456789012345678", "etwas tun")
    except HTTPException as exc:
        check("unberechtigter Aufrufer ergibt 403", exc.status_code == 403,
              f"(war {exc.status_code})")
    else:
        check("unberechtigter Aufrufer wird abgelehnt", False)
    finally:
        authority.may_act_globally = echt

    # Proxy und Bot muessen dieselbe Inhaberliste sehen. Auch das per
    # Wirkung: der Kommentar darueber nennt OWNER_IDS ebenfalls.
    ga = open(os.path.join(BOT, "..", "dashboard", "lib", "guild-auth.ts"),
              encoding="utf-8").read()
    rumpf = ga[ga.index("export function getAdminIds"):]
    rumpf = rumpf[: rumpf.index("\n}")]
    check("getAdminIds liest OWNER_IDS", "process.env.OWNER_IDS" in rumpf,
          "-> der Bot liest beide Namen; las der Proxy nur ADMIN_IDS, "
          "war der Betreiber fuer den Bot Inhaber und fuer den Proxy nicht")
    startsh = open(os.path.join(BOT, "..", "start.sh"), encoding="utf-8").read()
    check("start.sh fuellt ADMIN_IDS aus OWNER_IDS",
          'ADMIN_IDS="$OWNER_IDS"' in startsh)


def test_schutz():
    print("\n5b. Oberflaeche und Verdrahtung")

    # Die Oberflaeche: Wartezeit und Textfeld.
    panel = read("../dashboard/components/dashboard/user-lookup-panel.tsx")
    check("zehn Sekunden Wartezeit", "BAN_DELAY_SECONDS = 10" in panel)
    check("der Countdown laeuft wirklich",
          "setInterval" in panel and "countdown" in panel)
    check("der Knopf ist waehrend der Wartezeit gesperrt",
          "countdown === 0 &&" in panel)
    check("ein Textfeld muss abgetippt werden",
          "confirmText.trim() === erwarteterText" in panel)
    check("vorher wird eine Probe gefahren", "dry_run: true" in panel)

    # Das Schema muss angelegt werden -- sonst faellt die erste Sperre
    # nach einem frischen Deploy auf die Nase.
    guard = read("api/schema_guard.py")
    check("schema_guard kennt db/user_lookup.db", '"db/user_lookup.db"' in guard)
    check("schema_guard kennt bot_bans", "bot_bans" in guard)
    check("schema_guard kennt mass_actions", "mass_actions" in guard)

    # Der Reiter muss auch erreichbar sein.
    #
    # Frueher standen hier die Nachbarn woertlich drin
    # (`"userlookup", "access"`). Das nagelte die Reihenfolge innerhalb
    # der Gruppe fest -- eine Umsortierung der Leiste liess den Test
    # scheitern, obwohl der Reiter vollstaendig eingetragen war.
    # Geprueft wird deshalb, DASS er in einer Gruppe steht, nicht
    # neben wem.
    admin = read("../dashboard/components/dashboard/admin-content.tsx")
    for stelle, text in (
        ("TabId", '"userlookup"'),
        ("Reiterliste", 'id: "userlookup"'),
        ("Anzeige", 'activeTab === "userlookup"'),
        ("Import", "UserLookupPanel"),
    ):
        check(f"Reiter eingetragen: {stelle}", text in admin)

    # In einer Gruppe -- sonst verschwindet er ganz aus der Leiste,
    # weil sie ausschliesslich ueber die Gruppen rendert.
    import re as _re
    block = _re.search(r"const TAB_GROUPS[^=]*=\s*\[(.*?)\n\];", admin, _re.S)
    check("Reiter eingetragen: Gruppe",
          block is not None and '"userlookup"' in block.group(1),
          "ohne Gruppe waere er unsichtbar")

    # Und ueber die volle Breite, sonst quetscht ihn die
    # Eingabe-Seitenleiste zusammen.
    voll = _re.search(r"FULL_WIDTH_TABS = new Set<TabId>\(\[(.*?)\]\)", admin, _re.S)
    check("Reiter eingetragen: volle Breite",
          voll is not None and '"userlookup"' in voll.group(1))


# ── 6. Protokoll ─────────────────────────────────────────────────────

async def test_protokoll():
    print("\n6. Protokoll der Massnahmen")
    await ul.record_action(555, "ban_all", actor="1", reason="a", ok_count=3,
                           fail_count=1)
    await ul.record_action(555, "warn_owners", actor="1", reason="b", ok_count=2)

    eintraege = await ul.recent_actions(555)
    check("zwei Eintraege", len(eintraege) == 2, f"({len(eintraege)})")
    check("neueste zuerst", eintraege[0]["kind"] == "warn_owners",
          f"({eintraege[0]['kind']})")
    check("Zahlen stimmen",
          any(e["ok_count"] == 3 and e["fail_count"] == 1 for e in eintraege))

    andere = await ul.recent_actions(556)
    check("fremde ID sieht nichts", len(andere) == 0, f"({andere})")

    alle = await ul.recent_actions()
    check("ohne ID kommt alles", len(alle) >= 2, f"({len(alle)})")


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)
        try:
            await test_lookup()
            await test_bot_ban()
            await test_ban_everywhere()
            await test_warn_owners()
            await test_protokoll()
            await test_schutz_wirkt()
        finally:
            os.chdir(alt)

    test_ban_wirkt_auf_login_und_invite()
    test_actor_kommt_an()
    test_schutz()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Nutzer-Nachschlag: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
