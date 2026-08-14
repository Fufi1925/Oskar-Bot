#!/usr/bin/env python3
"""
Der Status-Bot: kein doppeltes Panel, und Partner-Server.

Zwei gemeldete Punkte
---------------------
**1. „manchmal kommt ein neues Panel, das alte bleibt".**
Der normale Weg raeumt auf. Es gab aber zwei Wege daran vorbei:

  * ``publish()`` setzte nach einem fehlgeschlagenen ``edit()``
    (Discord 500, Verbindungsabbruch) den Merker auf ``None`` und
    sendete neu -- die alte Nachricht kannte danach niemand mehr.
    ``refresh_panel()`` haette sie geloescht, aber der
    Hintergrundlauf ruft ``refresh_panel()`` gar nicht.
  * ``find_message()`` nahm nach einem Neustart die erste eigene
    Nachricht und brach ab. Lagen zwei tote Panels im Kanal, blieb
    eines fuer immer stehen.

**2. Partner-Server.** ``PARTNER_SERVER`` nimmt eine oder mehrere
Server-IDs. Dort ist ``/status`` fuer jeden benutzbar, das Panel landet
in dem Kanal, in dem der Befehl kam, wird live nachgefuehrt und traegt
in der Fusszeile, von welchem Server es kommt.

Geprueft wird die Wirkung an den echten Methoden -- nicht ein Nachbau,
der nur sich selbst misst.

Run:  python3 tests/test_status_partner.py
"""

import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
STATUS = os.path.join(ROOT, "statusbot")

sys.path.insert(0, BOT)
sys.path.insert(0, STATUS)

os.environ.setdefault("STATUS_BOT_TOKEN", "x")
os.environ["STATUS_CHANNEL_ID"] = "999"
os.environ["HOME_GUILD_ID"] = "0"
# Ein eigenes Verzeichnis: der Test darf die echte Historie nicht
# anfassen, und /data ist in der Sandbox nicht beschreibbar.
os.environ["STATUS_DATA_DIR"] = tempfile.mkdtemp()

import discord  # noqa: E402

import history  # noqa: E402
import status_bot as sb  # noqa: E402

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(rel: str) -> str:
    with open(os.path.join(STATUS, rel), encoding="utf-8") as f:
        return f.read()


# ── Attrappen ─────────────────────────────────────────────────────────


class FakeMessage:
    def __init__(self, kanal, mid, autor_id=1):
        self.channel = kanal
        self.id = mid
        self.author = type("A", (), {"id": autor_id})()
        self.geloescht = False
        self.edit_faellt_aus = False
        self.jump_url = f"https://discord.test/{mid}"

    async def edit(self, **_kwargs):
        if self.edit_faellt_aus:
            raise RuntimeError("Discord antwortet mit 500")

    async def delete(self):
        self.geloescht = True
        if self in self.channel.nachrichten:
            self.channel.nachrichten.remove(self)


class FakeChannel:
    def __init__(self, cid=999, guild=None):
        self.id = cid
        self.nachrichten: list[FakeMessage] = []
        self._next = cid * 10
        self.guild = guild
        self.mention = f"<#{cid}>"
        self.darf_senden = True

    async def send(self, **_kwargs):
        if not self.darf_senden:
            raise discord.Forbidden(
                type("R", (), {"status": 403, "reason": "x"})(), "nein"
            )
        self._next += 1
        m = FakeMessage(self, self._next)
        self.nachrichten.append(m)
        return m

    async def fetch_message(self, mid):
        for m in self.nachrichten:
            if m.id == mid and not m.geloescht:
                return m
        raise discord.NotFound(
            type("R", (), {"status": 404, "reason": "x"})(), "weg"
        )

    def history(self, limit=30):
        daten = list(reversed(self.nachrichten))[:limit]

        class Iter:
            def __aiter__(self_inner):
                self_inner._i = iter(daten)
                return self_inner

            async def __anext__(self_inner):
                try:
                    return next(self_inner._i)
                except StopIteration:
                    raise StopAsyncIteration

        return Iter()


class FakeGuild:
    def __init__(self, gid, name):
        self.id = gid
        self.name = name


def leerer_bot(kanal=None, guilds=None):
    """Ein StatusBot ohne Discord-Verbindung."""
    bot = object.__new__(sb.StatusBot)
    bot.message = None
    bot.state = "online"
    bot.state_since = 0.0
    gesundheit = sb.Health()
    gesundheit.reachable = True
    gesundheit.bot_ready = True
    gesundheit.dashboard = "online"
    bot.health = gesundheit
    bot.partner = None
    bot.maintenance = False
    bot.maintenance_note = ""
    bot._main_avatar = ""

    kanaele = {kanal.id: kanal} if kanal is not None else {}
    bot._kanaele = kanaele
    bot.get_channel = lambda cid: kanaele.get(cid)
    bot.get_guild = lambda gid: (guilds or {}).get(gid)

    typ = type("BotMitUser", (sb.StatusBot,), {"user": type("U", (), {"id": 1})()})
    bot.__class__ = typ
    return bot


def lebende(kanal):
    return [m for m in kanal.nachrichten if not m.geloescht]


def leere_panels():
    for eintrag in history.all_panels():
        history.forget_panel(eintrag["channel_id"])


# ══════════════════════════════════════════════════════════════════════
#  1. Kein doppeltes Panel
# ══════════════════════════════════════════════════════════════════════


async def test_publish_raeumt_auf():
    print("\npublish(): ein fehlgeschlagenes edit hinterlaesst keine Leiche")

    kanal = FakeChannel()
    bot = leerer_bot(kanal)

    alt = await kanal.send()
    alt.edit_faellt_aus = True
    bot.message = alt

    await bot.publish()

    check("nur ein Panel im Kanal", len(lebende(kanal)) == 1,
          f"{len(lebende(kanal))} Panels")
    check("das alte wurde geloescht", alt.geloescht is True,
          "genau der gemeldete Fehler")
    check("das neue ist gemerkt", bot.message is not None)


async def test_publish_bearbeitet_normal():
    print("\npublish(): der Normalfall sendet nichts Neues")

    kanal = FakeChannel()
    bot = leerer_bot(kanal)
    vorhanden = await kanal.send()
    bot.message = vorhanden

    await bot.publish()

    check("kein zweites Panel", len(lebende(kanal)) == 1)
    check("dieselbe Nachricht", bot.message.id == vorhanden.id)
    check("nichts geloescht", vorhanden.geloescht is False)


async def test_publish_notfound():
    print("\npublish(): eine verschwundene Nachricht wird nicht geloescht")

    kanal = FakeChannel()
    bot = leerer_bot(kanal)

    class Weg(FakeMessage):
        async def edit(self, **_kwargs):
            raise discord.NotFound(
                type("R", (), {"status": 404, "reason": "x"})(), "weg"
            )

    verschwunden = Weg(kanal, 55)
    bot.message = verschwunden
    await bot.publish()

    check("ein neues Panel steht", len(lebende(kanal)) == 1)
    check("kein Loeschversuch auf die 404", verschwunden.geloescht is False,
          "das waere ein zweiter Fehlschlag ohne Zweck")


async def test_find_message_raeumt_auf():
    print("\nfind_message(): alte Panels werden mit weggeraeumt")

    kanal = FakeChannel()
    bot = leerer_bot(kanal)

    erstes = await kanal.send()
    await kanal.send()
    juengstes = await kanal.send()

    await bot.find_message()

    check("eine wird weiterverwendet", bot.message is not None)
    check("und zwar die neueste", bot.message.id == juengstes.id,
          f"behalten: {getattr(bot.message, 'id', None)}")
    check("die aelteste ist weg", erstes.geloescht is True)
    check("genau eine bleibt", len(lebende(kanal)) == 1,
          f"{len(lebende(kanal))}")


# ══════════════════════════════════════════════════════════════════════
#  2. Partner-Server
# ══════════════════════════════════════════════════════════════════════


def test_ids_lesen():
    print("\nPARTNER_SERVER: mehrere IDs, egal wie getrennt")

    check("Komma", sb._ids("111,222") == (111, 222))
    check("Komma mit Leerzeichen", sb._ids("111, 222") == (111, 222))
    check("nur Leerzeichen", sb._ids("111 222") == (111, 222))
    check("Zeilenumbruch", sb._ids("111\n222") == (111, 222))
    check("Anfuehrungszeichen", sb._ids('"111","222"') == (111, 222))
    check("eine einzelne", sb._ids("111") == (111,))
    check("leer", sb._ids("") == ())
    check("Unsinn faellt weg", sb._ids("111,abc,222") == (111, 222),
          "eine kaputte ID darf nicht den Start verhindern")
    check("Doppelte nur einmal", sb._ids("111,111") == (111,))
    check("Null zaehlt nicht", sb._ids("0,111") == (111,))


async def test_partner_panel():
    print("\nDas Panel landet im Kanal des Partners")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    bot = leerer_bot(kanal, guilds={4242: guild})

    ok, note = await bot.post_partner_panel(kanal, guild)
    check("es klappt", ok is True, note)
    check("das Panel steht im Kanal", len(lebende(kanal)) == 1)
    check("die Antwort nennt den Link", "discord.test" in note, note)

    gemerkt = history.all_panels()
    check("es ist gemerkt", len(gemerkt) == 1, str(gemerkt))
    if gemerkt:
        check("mit dem richtigen Kanal", gemerkt[0]["channel_id"] == 777)
        check("und dem richtigen Server", gemerkt[0]["guild_id"] == 4242)


async def test_zweites_status_ersetzt():
    print("\nEin zweites /status ersetzt, statt zu stapeln")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    bot = leerer_bot(kanal, guilds={4242: guild})

    await bot.post_partner_panel(kanal, guild)
    erstes = lebende(kanal)[0]
    await bot.post_partner_panel(kanal, guild)

    check("nur ein Panel im Kanal", len(lebende(kanal)) == 1,
          f"{len(lebende(kanal))} -- sonst stapeln sie sich bei jedem Aufruf")
    check("das erste wurde geloescht", erstes.geloescht is True)
    check("und nur einer ist gemerkt", len(history.all_panels()) == 1)


async def test_live_nachfuehren():
    print("\nDie Partner-Panels laufen live mit")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    bot = leerer_bot(kanal, guilds={4242: guild})

    # Der Server muss als Partner gelten, sonst raeumt der Lauf auf.
    alt = sb.PARTNER_SERVER_IDS
    sb.PARTNER_SERVER_IDS = (4242,)
    try:
        await bot.post_partner_panel(kanal, guild)
        panel = lebende(kanal)[0]

        bearbeitet = {"n": 0}
        original = panel.edit

        async def zaehlend(**kwargs):
            bearbeitet["n"] += 1
            return await original(**kwargs)

        panel.edit = zaehlend

        await bot.refresh_partner_panels()

        check("das Panel wurde bearbeitet", bearbeitet["n"] == 1,
              f"{bearbeitet['n']} Aufrufe")
        check("und kein neues gesendet", len(lebende(kanal)) == 1)
    finally:
        sb.PARTNER_SERVER_IDS = alt


async def test_vergessen_wenn_weg():
    print("\nEin verschwundenes Panel wird vergessen")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    bot = leerer_bot(kanal, guilds={4242: guild})

    alt = sb.PARTNER_SERVER_IDS
    sb.PARTNER_SERVER_IDS = (4242,)
    try:
        await bot.post_partner_panel(kanal, guild)
        # Jemand loescht das Panel von Hand.
        await lebende(kanal)[0].delete()

        await bot.refresh_partner_panels()

        check("der Eintrag ist weg", history.all_panels() == [],
              "sonst scheitert jede Runde erneut")
        check("und es wird kein neues aufgedraengt", lebende(kanal) == [],
              "wer es zurueck will, tippt /status")
    finally:
        sb.PARTNER_SERVER_IDS = alt


async def test_kein_partner_mehr():
    print("\nWird ein Server aus der Liste genommen, verschwindet sein Panel")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    bot = leerer_bot(kanal, guilds={4242: guild})

    alt = sb.PARTNER_SERVER_IDS
    sb.PARTNER_SERVER_IDS = (4242,)
    try:
        await bot.post_partner_panel(kanal, guild)
        check("ein Panel ist gemerkt", len(history.all_panels()) == 1)

        # Der Server fliegt aus PARTNER_SERVER.
        sb.PARTNER_SERVER_IDS = ()
        await bot.refresh_partner_panels()

        check("der Eintrag wurde vergessen", history.all_panels() == [],
              "sonst laeuft der Bot ewig fuer einen Ex-Partner")
    finally:
        sb.PARTNER_SERVER_IDS = alt


async def test_kein_schreibrecht():
    print("\nOhne Schreibrecht kommt eine Erklaerung, kein Absturz")

    leere_panels()
    guild = FakeGuild(4242, "Partner-Server")
    kanal = FakeChannel(cid=777, guild=guild)
    kanal.darf_senden = False
    bot = leerer_bot(kanal, guilds={4242: guild})

    ok, note = await bot.post_partner_panel(kanal, guild)
    check("es meldet einen Fehlschlag", ok is False)
    check("und sagt warum", "nicht schreiben" in note, note)
    check("nichts wurde gemerkt", history.all_panels() == [],
          "ein Panel, das es nicht gibt, darf nicht in der Liste stehen")


def test_is_partner_guild():
    print("\nis_partner_guild")

    bot = object.__new__(sb.StatusBot)
    alt = sb.PARTNER_SERVER_IDS
    sb.PARTNER_SERVER_IDS = (4242, 7)
    try:
        check("ein Partner", sb.StatusBot.is_partner_guild(bot, 4242) is True)
        check("noch einer", sb.StatusBot.is_partner_guild(bot, 7) is True)
        check("ein fremder nicht", sb.StatusBot.is_partner_guild(bot, 1) is False)
        check("None nicht", sb.StatusBot.is_partner_guild(bot, None) is False)
    finally:
        sb.PARTNER_SERVER_IDS = alt


# ══════════════════════════════════════════════════════════════════════
#  3. Fusszeile und Verdrahtung
# ══════════════════════════════════════════════════════════════════════


def test_fusszeile():
    print("\nDie Fusszeile nennt den Partner-Server")

    from view import StatusView

    gesundheit = sb.Health()
    gesundheit.reachable = True
    gesundheit.bot_ready = True
    gesundheit.dashboard = "online"

    def text_von(view) -> str:
        return str(view.to_components())

    mit = StatusView(
        brand="University Bot", state="online", health=gesundheit,
        since=0.0, partner_server="Partner-Server",
    )
    check("der Name steht drin", "Partner-Server" in text_von(mit))
    check("mit dem Zusatz", "gesendet von" in text_von(mit))

    ohne = StatusView(
        brand="University Bot", state="online", health=gesundheit, since=0.0,
    )
    check("ohne Partner steht er nicht da", "gesendet von" not in text_von(ohne),
          "auf dem eigenen Server waere das falsch")


def test_verdrahtung():
    print("\nDie Verdrahtung -- was sonst still ausfaellt")

    quelle = read("status_bot.py")

    check("die Variable wird gelesen",
          'os.getenv("PARTNER_SERVER"' in quelle)
    check("/status kennt den Partner-Fall",
          "self.is_partner_guild(guild.id)" in quelle
          and "post_partner_panel" in quelle)
    check("und schliesst den eigenen Server aus",
          "guild.id != HOME_GUILD_ID" in quelle,
          "sonst landet das Panel im falschen Kanal des Support-Servers")

    # Die Bedingung muss WIRKEN, nicht nur dastehen. Wird sie zu
    # `and True` entschaerft, steht die Zeichenkette weiter im
    # Quelltext -- im Mutationstest genau so durchgerutscht. Der
    # Support-Server bekaeme dann sein Panel im Befehls-Kanal statt in
    # STATUS_CHANNEL_ID, und das eigentliche Panel bliebe stehen.
    zweig = quelle.split("async def status_command", 1)[-1].split("@self.tree", 1)[0]
    check("die Ausnahme fuer den eigenen Server ist wirksam",
          "and True:" not in zweig and "guild.id != HOME_GUILD_ID" in zweig,
          "sonst gilt der Support-Server als Partner")

    # Ohne Registrierung gibt es auf dem Partner-Server kein /status --
    # der haeufigste stille Ausfall in diesem Projekt.
    check("der Befehl wird auf den Partner-Servern registriert",
          "list(PARTNER_SERVER_IDS)" in quelle and "self.tree.sync(guild=guild)" in quelle)
    # Eine falsche ID in PARTNER_SERVER darf den Start nicht verhindern.
    # `raise` an dieser Stelle wuerde setup_hook abbrechen -- und damit
    # den ganzen Bot, samt Ueberwachung. Nur nach dem Wort zu suchen
    # reichte nicht: die Mutation ersetzte den Rumpf durch `raise` und
    # liess `except discord.Forbidden` stehen.
    reg = quelle.split("for guild_id in ziele:", 1)[-1].split("if PARTNER_SERVER_IDS", 1)[0]
    check("ein unerreichbarer Server bricht den Start nicht ab",
          "except discord.Forbidden" in reg and "raise" not in reg,
          "sonst startet der Bot nicht, wenn eine ID falsch ist")
    check("und sagt im Log, dass dort kein /status ankommt",
          "no access to guild" in reg,
          "sonst sucht man den fehlenden Befehl ohne Hinweis")

    # Und ohne Aufruf im Lauf waere „live" nur eine Behauptung.
    check("der Hintergrundlauf fuehrt sie nach",
          "await self.refresh_partner_panels()" in quelle)
    lauf = quelle.split("async def watch_loop", 1)[-1]
    check("und zwar wirklich IM Lauf",
          "refresh_partner_panels()" in lauf,
          "ausserhalb waere es einmalig statt live")

    # Der Speicher muss Neustarts ueberleben.
    hist = read("history.py")
    check("die Panels werden gespeichert",
          "CREATE TABLE IF NOT EXISTS panels" in hist)
    check("ein Panel je Kanal",
          "channel_id TEXT PRIMARY KEY" in hist,
          "sonst bekommt derselbe Kanal mehrere")
    for name in ("remember_panel", "forget_panel", "all_panels"):
        check(f"{name} gibt es", f"def {name}(" in hist)

    env = read("ENV.md")
    check("die Variable ist dokumentiert", "PARTNER_SERVER" in env)


async def main() -> int:
    check("das statusbot-Verzeichnis wurde gefunden", os.path.isdir(STATUS), STATUS)
    if not os.path.isdir(STATUS):
        return 1

    await test_publish_raeumt_auf()
    await test_publish_bearbeitet_normal()
    await test_publish_notfound()
    await test_find_message_raeumt_auf()

    test_ids_lesen()
    test_is_partner_guild()
    await test_partner_panel()
    await test_zweites_status_ersetzt()
    await test_live_nachfuehren()
    await test_vergessen_wenn_weg()
    await test_kein_partner_mehr()
    await test_kein_schreibrecht()

    test_fusszeile()
    test_verdrahtung()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Ein Panel je Kanal, Partner inbegriffen.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
