#!/usr/bin/env python3
"""
Verabschiedung, Bild-Schalter und der Musik-Beitritt.

Drei Dinge auf einmal, weil sie zusammen gemeldet wurden:

  1. ``>play`` liess den Bot beitreten und sofort wieder gehen, ohne
     eine Antwort im Chat -- und "manchmal, nach Warten geht es wieder".
  2. Beim Ticket-Panel fehlten die Felder fuer ein Bild, obwohl die
     Datenbank sie kennt.
  3. Das Willkommensbild war fest an, und eine Verabschiedung gab es
     ueberhaupt nicht.

Run:  python3 tests/test_leave_and_cards.py
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

from utils import leave_store, welcome_card  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370


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


def funktion(baum, name):
    for k in ast.walk(baum):
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k.name == name:
            return k
    return None


# ── 1. Der Musik-Beitritt ────────────────────────────────────────────

def test_musik_beitritt():
    print("\n1. >play: Bot joint und geht sofort wieder")
    roh = read("cogs/commands/music.py")
    baum = ast.parse(roh)
    ohne = strip_py(roh)

    ep = funktion(baum, "ensure_player")
    check("es gibt eine gemeinsame Verbindungsfunktion", ep is not None)
    quelle = ast.get_source_segment(roh, ep) if ep else ""

    # Der Aufbau muss abgesichert sein -- sonst haengt der Befehl
    # stumm, bis Discords Vorgabe von 30 Sekunden abgelaufen ist.
    im_try = any(
        ".connect(" in (ast.get_source_segment(roh, v) or "")
        for v in ast.walk(ep or ast.Module(body=[], type_ignores=[]))
        if isinstance(v, ast.Try)
    )
    check("connect() steht in einem try", im_try)
    check("ein eigener, kuerzerer Timeout ist gesetzt",
          bool(re.search(r"connect\([^)]*timeout\s*=", quelle)))

    import inspect

    import discord
    vorgabe = inspect.signature(discord.VoiceChannel.connect).parameters["timeout"].default
    check("Discords Vorgabe ist wirklich hoeher", vorgabe > 12,
          f"(Vorgabe {vorgabe}s -- deshalb der eigene Wert)")

    # Genau EINE Stelle darf noch selbst verbinden.
    direkt = len(re.findall(r"\.connect\(cls=wavelink\.Player", ohne))
    check("nur ensure_player verbindet", direkt == 1,
          f"({direkt} Stellen umgehen die Absicherung)")

    # Eine tote Verbindung aus einem frueheren Versuch muss erkannt
    # werden -- das ist das "manchmal geht es".
    check("ein toter Player wird erkannt", "_player_alive" in quelle)
    check("und vorher weggeraeumt", "disconnect(force=True)" in quelle)

    # Jeder Ausgang muss antworten.
    check("jeder Fehlerausgang sagt etwas", quelle.count("ctx.send") >= 5,
          f"({quelle.count('ctx.send')} Antworten)")

    # Fehlende Rechte vorher pruefen spart die volle Wartezeit.
    check("Rechte werden vorab geprueft",
          "permissions_for" in quelle and "connect" in quelle)

    # Der Waechter darf nicht in den eigenen Start funken.
    check("der Waechter wird waehrend des Aufbaus ausgesetzt",
          "_started_empty" in quelle)


async def test_ensure_player_wirkung():
    """
    ensure_player wird AUSGEFUEHRT.

    Die Pruefungen oben lesen den Quelltext -- das faengt eine entfernte
    Zeile, aber nicht eine, die stehenbleibt und nichts mehr tut.
    Deshalb hier echte Aufrufe mit Attrappen.
    """
    print("\n   -- ensure_player, wirklich ausgefuehrt --")
    from cogs.commands.music import Music

    gesendet: list = []

    class FakePerms:
        def __init__(self, connect=True, speak=True):
            self.connect, self.speak = connect, speak

    class FakeChannel:
        def __init__(self, perms=None):
            self.id = 5
            self.mention = "#voice"
            self._perms = perms or FakePerms()
            self.versuche = 0

        def permissions_for(self, member):
            return self._perms

        async def connect(self, **kwargs):
            self.versuche += 1
            raise asyncio.TimeoutError()

    class FakeGuild:
        id = GUILD
        me = object()
        voice_client = None

        async def change_voice_state(self, **kw):
            pass

    class FakeCtx:
        def __init__(self, kanal):
            self.guild = FakeGuild()
            self.voice_client = None

            class Voice:
                channel = kanal
            class Author:
                voice = Voice()
            self.author = Author()

        async def send(self, **kwargs):
            gesendet.append(kwargs)

    cog = Music.__new__(Music)
    cog._started_empty = set()

    # ensure_player fragt seit dem Node-Fix zuerst require_music -- ohne
    # laufenden Lavalink-Knoten kaeme es gar nicht bis zum Verbinden.
    # Im Test gibt es keinen Knoten, also wird die Antwort gesetzt. Das
    # ist kein Umgehen der Pruefung: dass sie da ist, belegt
    # test_music_node.py, und zwar fuer jeden Verbindungsaufruf.
    async def _node_da(ctx):
        return True

    cog.require_music = _node_da

    # 1. Timeout: es muss eine Antwort geben, und der Vermerk beim
    #    Waechter muss wieder weg sein.
    kanal = FakeChannel()
    ctx = FakeCtx(kanal)
    ergebnis = await cog.ensure_player(ctx)
    check("Timeout gibt None zurueck", ergebnis is None)
    check("und sagt es im Chat", len(gesendet) == 1, f"({gesendet})")
    check("der Waechter-Vermerk wird zurueckgenommen",
          GUILD not in cog._started_empty,
          "-> der Bot bliebe sonst dauerhaft von der Leerlauf-Pruefung ausgenommen")

    # 1b. Der Erfolgsfall. Nur hier ist zu sehen, ob der Vermerk
    #     ueberhaupt je gesetzt wird -- nach einem Timeout ist er in
    #     beiden Faellen weg, das trennt nichts.
    class GuterKanal(FakeChannel):
        async def connect(self, **kwargs):
            self.versuche += 1
            return "spieler"

    cog._started_empty.clear()
    ergebnis = await cog.ensure_player(FakeCtx(GuterKanal()))
    check("bei Erfolg kommt ein Player zurueck", ergebnis == "spieler")
    check("und der Waechter bleibt fuer den Start ausgesetzt",
          GUILD in cog._started_empty,
          "-> sonst pausiert er den frisch verbundenen Bot sofort wieder")
    cog._started_empty.clear()

    # 2. Fehlende Rechte: gar kein Verbindungsversuch.
    gesendet.clear()
    kanal2 = FakeChannel(FakePerms(connect=False))
    ergebnis = await cog.ensure_player(FakeCtx(kanal2))
    check("ohne Verbinden-Recht wird es abgelehnt", ergebnis is None)
    check("und gar nicht erst versucht", kanal2.versuche == 0,
          "-> sonst wartet der Nutzer den vollen Timeout ab")
    check("mit einer Meldung", len(gesendet) == 1, f"({gesendet})")
    # Der Text selbst laesst sich am View nicht ablesen -- CV2 baut ein
    # Komponenten-Objekt. Also die Quelle belegen: sie muss die
    # fehlende Berechtigung benennen, nicht nur "geht nicht" sagen.
    check("und sie benennt die fehlende Berechtigung",
          "Berechtigung **Verbinden**" in read("cogs/commands/music.py"),
          "-> sonst sucht der Betreiber an der falschen Stelle")

    # 3. Ein lebender Player wird wiederverwendet, kein neuer Aufbau.
    gesendet.clear()

    class LebenderPlayer:
        connected = True
        channel = object()

    ctx3 = FakeCtx(FakeChannel())
    ctx3.voice_client = LebenderPlayer()
    ergebnis = await cog.ensure_player(ctx3)
    check("ein lebender Player wird weiterbenutzt",
          isinstance(ergebnis, LebenderPlayer))
    check("ohne neue Meldung", not gesendet)

    # 4. Ein toter Player wird nicht wiederverwendet.
    geraeumt = {"n": 0}

    class ToterPlayer:
        connected = False
        channel = None

        async def disconnect(self, force=False):
            geraeumt["n"] += 1

    ctx4 = FakeCtx(FakeChannel())
    ctx4.voice_client = ToterPlayer()
    ergebnis = await cog.ensure_player(ctx4)
    check("ein toter Player wird verworfen", not isinstance(ergebnis, ToterPlayer),
          "-> der naechste >play spielt sonst ins Leere")
    check("und vorher getrennt", geraeumt["n"] == 1, f"({geraeumt['n']})")


# ── 2. Die Verabschiedung ────────────────────────────────────────────

async def test_leave_store():
    print("\n2. Verabschiedung: Einstellungen")
    s = await leave_store.get(GUILD)
    check("Voreinstellung ist AUS", s["enabled"] is False)
    check("Bild ist voreingestellt an", s["card_enabled"] is True)

    s = await leave_store.save(GUILD, {
        "enabled": True, "channel_id": "123456789012345678",
        "leave_message": "Tschuess {user.name}",
    })
    check("Einschalten wird gespeichert", s["enabled"] is True)
    check("Kanal wird gespeichert", s["channel_id"] == "123456789012345678")
    check("Text wird gespeichert", s["leave_message"] == "Tschuess {user.name}")

    # Teilweise speichern darf den Rest nicht loeschen -- das Dashboard
    # schickt beim Umlegen eines Schalters nur dieses eine Feld.
    s = await leave_store.save(GUILD, {"card_enabled": False})
    check("Teil-Speichern behaelt den Kanal", s["channel_id"] == "123456789012345678")
    check("Teil-Speichern behaelt den Text", s["leave_message"] == "Tschuess {user.name}")
    check("Bild ist jetzt aus", s["card_enabled"] is False)

    # Eine ID, die keine ist, darf nicht durchrutschen.
    s = await leave_store.save(GUILD, {"channel_id": "abc"})
    check("unsinniger Kanal wird verworfen", s["channel_id"] is None)

    # Nur http(s) als Bildquelle.
    s = await leave_store.save(GUILD, {"card_image_url": "javascript:alert(1)"})
    check("fremdes Schema wird abgelehnt", s["card_image_url"] is None)
    s = await leave_store.save(GUILD, {"card_image_url": "https://example.com/a.png"})
    check("https wird angenommen", s["card_image_url"] == "https://example.com/a.png")

    # Die Loeschdauer hat Grenzen.
    s = await leave_store.save(GUILD, {"auto_delete_duration": 99999})
    check("Loeschdauer ist begrenzt", s["auto_delete_duration"] == 3600,
          f"({s['auto_delete_duration']})")
    s = await leave_store.save(GUILD, {"auto_delete_duration": 0})
    check("Null heisst: nicht loeschen", s["auto_delete_duration"] is None)


def test_platzhalter():
    print("\n   -- Platzhalter --")

    class M:
        id = 999
        mention = "<@999>"
        display_name = "Fufi"

        class guild:
            name = "LSPD I Dunya"

    text = leave_store.fill(
        "{user} alias {user.name} ({user.id}) verlaesst {server}, "
        "noch {membercount} da",
        M(), 1234,
    )
    check("Erwaehnung ersetzt", "<@999>" in text, text)
    check("Name ersetzt", "Fufi" in text, text)
    check("ID ersetzt", "999" in text, text)
    check("Server ersetzt", "LSPD I Dunya" in text, text)
    check("Mitgliederzahl mit Punkt", "1.234" in text, text)
    check("leerer Text bleibt None", leave_store.fill(None, M(), 1) is None)


# ── 3. Das Bild ──────────────────────────────────────────────────────

def test_karte():
    print("\n3. Die gezeichnete Karte")
    b = welcome_card.render(name="Fufi", avatar_bytes=None,
                            guild_name="LSPD I Dunya", member_count=1234)
    check("Willkommenskarte wird gezeichnet", b is not None)

    b2 = welcome_card.render(
        name="Fufi", avatar_bytes=None, guild_name="LSPD I Dunya",
        member_count=1233, accent=0xEF4444, label="AUF WIEDERSEHEN",
        preposition="verlässt", counter_text="Noch 1.233 Mitglieder",
    )
    check("Abschiedskarte wird gezeichnet", b2 is not None)

    # Jede der drei neuen Angaben EINZELN pruefen, bei sonst gleichen
    # Werten. Wuerde man alle auf einmal aendern, genuegte eine wirksame
    # Angabe -- die Farbe zum Beispiel --, damit die Bilder verschieden
    # aussehen, und die anderen zwei koennten wirkungslos sein, ohne
    # dass es auffaellt.
    grund = dict(name="Fufi", avatar_bytes=None, guild_name="Server",
                 member_count=100)
    basis = welcome_card.render(**grund)

    if basis is not None:
        for feld, wert in (
            ("label", "AUF WIEDERSEHEN"),
            ("preposition", "verlässt"),
            ("counter_text", "Noch 99 Mitglieder"),
            ("accent", 0xEF4444),
        ):
            anders = welcome_card.render(**grund, **{feld: wert})
            check(f"{feld} veraendert das Bild wirklich",
                  anders is not None and anders.getvalue() != basis.getvalue(),
                  f"-> {feld} wird beim Zeichnen ignoriert")

    # Ein sehr langer Name darf die Karte nicht sprengen.
    lang = welcome_card.render(name="X" * 80, avatar_bytes=None,
                               guild_name="Y" * 80, member_count=1)
    check("langer Name bricht nichts", lang is not None)


async def test_bild_schalter():
    """
    Der Schalter wird AUSGEFUEHRT, nicht im Text gesucht.

    "card_enabled kommt vor" bleibt auch dann wahr, wenn ein ``if
    False`` davorsteht -- eine Textsuche waere hier also genau dann
    gruen, wenn der Schalter nicht mehr wirkt.
    """
    print("\n   -- Der Ein/Aus-Schalter, wirklich ausgefuehrt --")

    class FakeAsset:
        async def read(self):
            raise RuntimeError("kein Avatar im Test")

        def replace(self, **kw):
            return self

    class FakeGuild:
        id = GUILD
        name = "Server"
        member_count = 100
        members: list = []

    class FakeMember:
        id = 42
        bot = False
        display_name = "Fufi"
        mention = "<@42>"
        guild = FakeGuild()
        display_avatar = FakeAsset()

    from cogs.events import leave as leave_cog

    cog = leave_cog.LeaveMessages.__new__(leave_cog.LeaveMessages)

    # Aus heisst: gar kein Bild.
    karte = await cog.build_card(FakeMember(), {"card_enabled": False})
    check("Schalter AUS liefert kein Bild", karte is None,
          "-> der Bot zeichnet trotzdem")

    # Ein eigenes Bild ersetzt die gezeichnete Karte -- also auch hier
    # keine Datei, die URL wandert stattdessen ins Panel.
    karte = await cog.build_card(
        FakeMember(), {"card_enabled": True, "card_image_url": "https://x/y.png"}
    )
    check("eigenes Bild ersetzt die gezeichnete Karte", karte is None)

    # Und es muss auch wirklich als Bildquelle verwendet werden -- sonst
    # ist das Feld im Dashboard wirkungslos. Im Syntaxbaum nachsehen,
    # nicht im Text: der Name bleibt sonst auch stehen, wenn ihm nie
    # etwas zugewiesen wird.
    greet_baum = ast.parse(read("cogs/events/greet2.py"))
    zuweisung = any(
        isinstance(k, ast.Assign)
        and len(k.targets) == 1
        and getattr(k.targets[0], "id", "") == "eigenes_bild"
        and getattr(k.value, "id", "") == "card_image_url"
        for k in ast.walk(greet_baum)
    )
    check("das eigene Bild wird der Bildquelle zugewiesen", zuweisung,
          "-> das Feld im Dashboard bliebe wirkungslos")

    # An und ohne eigenes Bild: es wird gezeichnet.
    karte = await cog.build_card(FakeMember(), {"card_enabled": True})
    check("Schalter AN liefert ein Bild", karte is not None,
          "-> ohne Bild waere der Schalter wirkungslos")
    if karte is not None:
        check("das Bild heisst abschied.png", karte.filename == "abschied.png")

    # Und die Begruessung: der Zweig muss das Zeichnen wirklich
    # ueberspringen. Dafuer wird der Syntaxbaum befragt statt der Text.
    baum = ast.parse(read("cogs/events/greet2.py"))
    gefunden = False
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.If):
            continue
        if ast.unparse(knoten.test).strip() != "card_enabled":
            continue
        if "build_banner" in ast.unparse(knoten):
            gefunden = True
    check("die Begruessung zeichnet nur bei eingeschaltetem Schalter", gefunden,
          "-> build_banner steht nicht hinter 'if card_enabled'")

    # NULL muss weiter als AN gelten, sonst verlieren alle bestehenden
    # Server ihr Banner beim ersten Start nach dem Deploy.
    greet_quelle = read("cogs/events/greet2.py")
    check("NULL gilt als AN",
          "True if card_enabled is None else bool(card_enabled)" in greet_quelle,
          "-> bestehende Server verlieren sonst ihr Willkommensbild")

    # Der Aus-Schalter der Verabschiedung: bei 'aus' darf nichts raus.
    baum_l = ast.parse(read("cogs/events/leave.py"))
    pq = funktion(baum_l, "process_queue")
    quelle_pq = ast.get_source_segment(read("cogs/events/leave.py"), pq) if pq else ""
    check("die Verabschiedung prueft 'enabled'",
          bool(re.search(r'if not settings\.get\("enabled"\)', quelle_pq)),
          "-> sonst schreibt sie auch bei ausgeschalteter Funktion")


# ── 4. Verdrahtung ───────────────────────────────────────────────────

async def test_welcome_route():
    """Die welcome-Route muss card_enabled auch wirklich liefern."""
    print("\n   -- /welcome liefert den Schalter --")
    import aiosqlite

    from api.routes.guilds import get_guild_welcome
    from api import schema_guard

    await schema_guard.ensure_schema()
    async with aiosqlite.connect("db/welcome.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO welcome (guild_id, welcome_type, channel_id,"
            " card_enabled, card_image_url) VALUES (?, 'simple', 1, 0, ?)",
            (GUILD, "https://example.com/a.png"),
        )
        await db.commit()

    cfg = await get_guild_welcome(GUILD)
    check("card_enabled kommt als False an", cfg.card_enabled is False,
          f"(war {cfg.card_enabled})")
    check("card_image_url kommt an",
          cfg.card_image_url == "https://example.com/a.png")

    # Und NULL muss als AN ankommen.
    async with aiosqlite.connect("db/welcome.db") as db:
        await db.execute(
            "UPDATE welcome SET card_enabled = NULL WHERE guild_id = ?", (GUILD,)
        )
        await db.commit()
    cfg = await get_guild_welcome(GUILD)
    check("NULL kommt als True an", cfg.card_enabled is True,
          f"(war {cfg.card_enabled})")


def test_verdrahtung():
    print("\n4. Cog, Routen, Schema und Dashboard")
    init = read("cogs/__init__.py")
    check("Leave-Cog wird importiert",
          "from .events.leave import LeaveMessages" in init)
    check("Leave-Cog wird hinzugefuegt", "add_cog(LeaveMessages(bot))" in init)

    # Ein on_member_remove ohne Dekorator wird nie aufgerufen.
    baum = ast.parse(read("cogs/events/leave.py"))
    hat_listener = False
    for k in ast.walk(baum):
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "on_member_remove":
            for d in k.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "listener":
                    hat_listener = True
    check("on_member_remove ist als Listener registriert", hat_listener)

    guilds = read("api/routes/guilds.py")
    check("GET /leave vorhanden", '"/{guild_id}/leave"' in guilds)
    check("PATCH /leave vorhanden", guilds.count('"/{guild_id}/leave"') >= 2)

    guard = read("api/schema_guard.py")
    check("schema_guard kennt db/leave.db", '"db/leave.db"' in guard)
    check("welcome bekommt die neuen Spalten nachtraeglich",
          '"card_enabled"' in guard and "ADDED_COLUMNS" in guard,
          "-> bestehende Datenbanken haben die Spalte sonst nicht")

    dash = "../dashboard"
    tickets = open(os.path.join(BOT, dash, "components/dashboard/ticket-panels.tsx"),
                   encoding="utf-8").read()
    # Auf die wirksame Zeile pruefen, nicht auf das Vorkommen des
    # Feldnamens: der steht auch in der Typdeklaration, und die bleibt
    # stehen, wenn das Eingabefeld verschwindet.
    check("Ticket speichert das grosse Bild",
          "patchPanel(panel.panel_id, { embed_image_url:" in tickets,
          "-> das Feld schreibt nichts zurueck")
    check("Ticket speichert das Vorschaubild",
          "embed_thumbnail_url: next || null," in tickets)
    check("das grosse Bild ist als solches beschriftet",
          'label="Großes Bild"' in tickets,
          "-> ohne Beschriftung findet es niemand")

    welcome_form = open(os.path.join(BOT, dash, "components/dashboard/welcome-form.tsx"),
                        encoding="utf-8").read()
    check("Willkommen schaltet das Bild wirklich um",
          "card_enabled: config.card_enabled === false" in welcome_form,
          "-> der Schalter bewegt sich, aendert aber nichts")

    leave_form = open(os.path.join(BOT, dash, "components/dashboard/leave-form.tsx"),
                      encoding="utf-8").read()
    check("Verabschiedung hat eine Oberflaeche", "LeaveForm" in leave_form)
    check("ihr Bild-Schalter zeigt den echten Stand",
          "checked={config.card_enabled !== false}" in leave_form,
          "-> der Schalter steht fest auf an")
    check("und schreibt ihn zurueck",
          "set({ card_enabled: v })" in leave_form)

    # Eine neue Seite braucht fuenf Eintraege, sonst findet sie niemand.
    seite = os.path.join(BOT, dash, "app/dashboard/guild/[guildId]/leave/page.tsx")
    check("die Seite existiert", os.path.isfile(seite))
    tabs = open(os.path.join(BOT, dash, "components/guild-tabs.tsx"),
                encoding="utf-8").read()
    check("Reiter eingetragen", 'slug: "leave"' in tabs)
    check("Reiter-Icon importiert", "DoorOpen" in tabs.split("interface")[0])
    suche = open(os.path.join(BOT, dash, "components/global-search.tsx"),
                 encoding="utf-8").read()
    check("in der Suche eingetragen", "/leave" in suche)
    layout = open(os.path.join(BOT, dash, "app/dashboard/layout.tsx"),
                  encoding="utf-8").read()
    check("in der Seitenleiste eingetragen", "/leave" in layout)

    api_ts = open(os.path.join(BOT, dash, "lib/api.ts"), encoding="utf-8").read()
    check("api.ts kennt getLeave", "getLeave" in api_ts)
    check("api.ts kennt updateLeave", "updateLeave" in api_ts)


async def main():
    test_musik_beitritt()

    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)
        try:
            await test_leave_store()
            await test_ensure_player_wirkung()
            await test_welcome_route()
        finally:
            os.chdir(alt)

    test_platzhalter()
    test_karte()
    await test_bild_schalter()
    test_verdrahtung()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Verabschiedung, Bilder und Musik-Beitritt: alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
