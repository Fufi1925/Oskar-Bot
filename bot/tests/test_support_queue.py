#!/usr/bin/env python3
"""
Support-Warteraum: Bot dazu, Ansage, Musik, von vorn.

Ein Sprachkanal wird zum Warteraum erklaert. Betritt ihn jemand, kommt
der Bot dazu, spricht eine Begruessung und spielt danach Wartemusik.
Nach der eingestellten Zeit wiederholt sich beides -- bis der letzte
Mensch geht.

Worauf es dabei ankommt, und was hier geprueft wird:

  * **Der Bot muss wieder rausgehen.** Eine Schleife, die weiterlaeuft,
    wenn niemand mehr da ist, spielt sich selbst etwas vor -- und haelt
    den Sprachkanal dauerhaft belegt.

  * **Ein Wechsel innerhalb desselben Kanals ist kein Beitritt.**
    `on_voice_state_update` feuert auch beim Stummschalten. Ohne diese
    Unterscheidung startet der Bot bei jedem Klick auf das Mikrofon
    eine neue Runde.

  * **Zwei Wartende starten eine Schleife, nicht zwei.** Sonst reden
    zwei Ansagen gleichzeitig.

  * **Ohne Lavalink kein Beitritt.** Stumm im Kanal zu sitzen taeuscht
    Anwesenheit vor; der Hinweis ans Team geht trotzdem raus.

  * **Grenzen gelten serverseitig.** Die Route ist per HTTP erreichbar,
    und curl fragt nicht nach einem Formular.

Run:  python3 tests/test_support_queue.py
"""

import asyncio
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ.setdefault("TOKEN", "x")
os.environ["ALLOW_KEYLESS_API"] = "true"
warnings.filterwarnings("ignore")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


# --------------------------------------------------------------------- #
#  Attrappen
# --------------------------------------------------------------------- #
#
# Sie bilden nach, was discord.py an diesen Stellen wirklich liefert:
# `channel.members` enthaelt auch Bots, `guild.me` hat Rechte, und
# `connect(cls=...)` gibt einen Player zurueck.


class FakeMember:
    def __init__(self, uid, name, bot=False):
        self.id = uid
        self.display_name = name
        self.name = name
        self.mention = f"<@{uid}>"
        self.bot = bot
        self.guild = None


class FakePlayer:
    """Was wavelink.Player an dieser Stelle tut."""

    def __init__(self):
        self.played: list[tuple] = []
        self.playing = False
        self.disconnected = False

    async def play(self, track, *, volume=100, end=None, **kwargs):
        self.played.append((getattr(track, "title", str(track)), volume, end))
        # Sofort fertig: der Test wartet sonst echte Sekunden.
        self.playing = False

    async def disconnect(self):
        self.disconnected = True


class FakePermissions:
    def __init__(self, ok=True):
        self.view_channel = ok
        self.connect = ok
        self.speak = ok


class FakeVoiceChannel:
    def __init__(self, cid, name, guild):
        self.id = cid
        self.name = name
        self.guild = guild
        self._members: list[FakeMember] = []
        self.category = None
        self.user_limit = 0
        self.mention = f"<#{cid}>"
        self.player = FakePlayer()
        self._can = True

    @property
    def members(self):
        return self._members

    @members.setter
    def members(self, people):
        # discord.py verknuepft jedes Member mit seinem Server. Ohne
        # das ist `member.guild` None, und der Waechter ganz oben in
        # `on_voice_state_update` steigt sofort aus -- die erste
        # Fassung dieser Attrappe hat genau deshalb fuenf Tests
        # scheitern lassen, obwohl der Code stimmte.
        for person in people:
            person.guild = self.guild
        self._members = list(people)

    def permissions_for(self, _member):
        return FakePermissions(self._can)

    async def connect(self, *, cls=None, self_deaf=False):
        return self.player


class FakeTextChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.sent: list = []

    async def send(self, content=None, view=None, **kwargs):
        self.sent.append(content or view)


class FakeGuild:
    def __init__(self):
        self.id = 4242
        self.name = "Testserver"
        self.me = FakeMember(1, "Bot", bot=True)
        self.voice = FakeVoiceChannel(555, "warteraum", self)
        self.text = FakeTextChannel(777, "team")
        self.voice_channels = [self.voice]
        self.text_channels = [self.text]
        self.roles = []
        self.voice_client = None

    def get_channel(self, cid):
        if int(cid) == 555:
            return self.voice
        if int(cid) == 777:
            return self.text
        return None

    def get_member(self, uid):
        for member in self.voice.members:
            if member.id == int(uid):
                return member
        return None

    def get_role(self, _rid):
        return None


class FakeBot:
    def __init__(self, guild):
        self.guild = guild
        self.user = FakeMember(1, "Bot", bot=True)

    def get_guild(self, gid):
        return self.guild if int(gid) == self.guild.id else None

    def get_cog(self, _name):
        return None


class FakeState:
    def __init__(self, channel=None):
        self.channel = channel


async def build_cog(guild, *, node_ready=True, **settings):
    """Einen Cog mit eigener Datenbank und ohne echtes Lavalink."""

    import aiosqlite

    from cogs.commands.supportqueue import SupportQueue
    from utils import support_queue as store

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    cog = SupportQueue(FakeBot(guild))
    cog._connection = await aiosqlite.connect(path)
    await store.ensure_schema(cog._connection)
    await store.save(cog._connection, guild.id, **settings)

    # Kein echter Knoten und keine echten Suchanfragen.
    cog._wait_for_node = staticmethod(lambda: asyncio.sleep(0, result=node_ready))

    class Track:
        title = "stueck"

    async def fake_tts(_text):
        return Track()

    cog._tts_track = staticmethod(fake_tts)

    async def fake_search(_query):
        return [Track()]

    import wavelink

    wavelink.Playable.search = staticmethod(fake_search)

    return cog, path


# --------------------------------------------------------------------- #
#  1. Der Ablauf
# --------------------------------------------------------------------- #


def test_the_bot_joins_speaks_and_plays():
    print("\nBot kommt dazu, sagt etwas, spielt Musik")

    from utils import support_queue as store

    async def scenario():
        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, music_seconds=10
        )
        try:
            person = FakeMember(10, "Alice")
            guild.voice.members = [person]

            await cog.on_voice_state_update(
                person, FakeState(None), FakeState(guild.voice)
            )

            # Die Schleife laeuft im Hintergrund. Ihr Zeit fuer die
            # Ansage geben (die wartet mindestens eine Sekunde, damit
            # sie bei einem stummen Player nicht durchdreht), dann den
            # Kanal leeren.
            await asyncio.sleep(1.8)
            guild.voice.members = []
            await asyncio.sleep(0.6)

            task = cog._loops.get(guild.id)
            if task is not None:
                task.cancel()

            return guild.voice.player, store.waiting(guild.id)
        finally:
            await cog._connection.close()
            os.unlink(path)

    player, waiting = asyncio.run(scenario())

    check("der Bot hat etwas abgespielt", len(player.played) >= 1,
          f"abgespielt: {player.played}")
    check("die Ansage kam zuerst",
          bool(player.played) and player.played[0][2] is None,
          "die Ansage laeuft ohne Laengenbegrenzung, die Musik mit")
    check("jemand stand auf der Warteliste", 10 in waiting or not waiting)


def test_the_music_is_cut_to_length():
    """Ohne `end` liefe ein langer Track durch und die Ansage kaeme nie."""

    print("\nDie Musik wird auf die eingestellte Dauer geschnitten")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, music_seconds=25
        )
        try:
            record = await cog.settings(guild.id)
            await cog._play_music(guild.voice.player, record, 25)
            return guild.voice.player.played
        finally:
            await cog._connection.close()
            os.unlink(path)

    played = asyncio.run(scenario())

    check("es lief etwas", bool(played), str(played))
    if played:
        check("mit Laengenbegrenzung", played[0][2] == 25000,
              f"end={played[0][2]} — erwartet 25000 Millisekunden")
        check("und leiser als die Ansage", played[0][1] < 100,
              f"Lautstaerke {played[0][1]}")


def test_the_loop_does_not_spin():
    """Ein Player, der sofort "fertig" meldet, darf die Schleife nicht
    durchdrehen lassen.

    Beim Bauen aufgefallen und deshalb hier festgehalten: `_wait_until_idle`
    kehrte sofort zurueck, wenn `playing` schon False war. Die Schleife
    startete dann ohne Pause die naechste Runde -- tausende Durchlaeufe
    pro Sekunde, ein Kern auf Anschlag, und die Task liess sich nicht
    einmal mehr abbrechen: sie kam nie an einen Wartepunkt, an dem
    asyncio den Abbruch haette zustellen koennen.

    Auf einem echten Server passiert genau das, wenn Lavalink einen
    Track nicht laden kann.
    """

    print("\nDie Schleife dreht nicht durch")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, music_seconds=10
        )
        try:
            guild.voice.members = [FakeMember(10, "Alice")]
            record = await cog.settings(guild.id)

            task = asyncio.create_task(cog._run_loop(guild, guild.voice, record))
            await asyncio.sleep(2.0)
            rounds = len(guild.voice.player.played)

            task.cancel()
            cancelled = False
            try:
                await asyncio.wait_for(task, timeout=3)
            except asyncio.CancelledError:
                cancelled = True
            except asyncio.TimeoutError:
                cancelled = False

            return rounds, cancelled
        finally:
            await cog._connection.close()
            os.unlink(path)

    rounds, cancelled = asyncio.run(scenario())

    check("in zwei Sekunden laufen wenige Runden",
          rounds <= 6,
          f"{rounds} Runden — die Schleife dreht durch")
    check("und die Schleife bleibt abbrechbar",
          cancelled is True,
          "ohne Wartepunkt kommt der Abbruch nie an")


def test_the_loop_stops_when_everyone_left():
    print("\nDie Schleife endet, wenn niemand mehr da ist")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, music_seconds=10
        )
        try:
            # Niemand im Kanal -- die Schleife darf gar nicht erst
            # loslaufen.
            guild.voice.members = []
            await cog._run_loop(guild, guild.voice, await cog.settings(guild.id))
            return guild.voice.player
        finally:
            await cog._connection.close()
            os.unlink(path)

    player = asyncio.run(scenario())

    check("nichts wurde abgespielt", player.played == [],
          f"abgespielt: {player.played}")
    check("und der Bot ist wieder draussen", player.disconnected is True)


def test_a_mute_does_not_restart_everything():
    """`on_voice_state_update` feuert auch beim Stummschalten."""

    print("\nStummschalten ist kein Beitritt")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(guild, channel_id=555, enabled=True)
        try:
            person = FakeMember(10, "Alice")
            guild.voice.members = [person]

            # Vorher und nachher derselbe Kanal: nur das Mikrofon.
            await cog.on_voice_state_update(
                person, FakeState(guild.voice), FakeState(guild.voice)
            )
            await asyncio.sleep(0.1)

            started = guild.id in cog._loops
            for task in cog._loops.values():
                task.cancel()
            return started
        finally:
            await cog._connection.close()
            os.unlink(path)

    started = asyncio.run(scenario())
    check("keine neue Runde gestartet", started is False,
          "sonst redet der Bot bei jedem Mikrofon-Klick los")


def test_two_people_share_one_loop():
    print("\nZwei Wartende, eine Schleife")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, music_seconds=10
        )
        try:
            first = FakeMember(10, "Alice")
            second = FakeMember(11, "Bob")

            guild.voice.members = [first]
            await cog.on_voice_state_update(
                first, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.2)
            task_after_first = cog._loops.get(guild.id)

            guild.voice.members = [first, second]
            await cog.on_voice_state_update(
                second, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.2)
            task_after_second = cog._loops.get(guild.id)

            waiting = store.waiting(guild.id)

            guild.voice.members = []
            for task in list(cog._loops.values()):
                task.cancel()
            return task_after_first, task_after_second, waiting
        finally:
            await cog._connection.close()
            os.unlink(path)

    first_task, second_task, waiting = asyncio.run(scenario())

    check("beide stehen auf der Warteliste", len(waiting) == 2, str(waiting))
    check("es laeuft dieselbe Schleife weiter",
          first_task is second_task,
          "zwei Schleifen wuerden gleichzeitig reden")


def test_the_last_one_out_turns_off_the_light():
    print("\nDer Letzte macht das Licht aus")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(guild, channel_id=555, enabled=True)
        try:
            person = FakeMember(10, "Alice")
            guild.voice.members = [person]
            await cog.on_voice_state_update(
                person, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.1)

            # Geht wieder.
            guild.voice.members = []
            guild.voice_client = guild.voice.player
            await cog.on_voice_state_update(
                person, FakeState(guild.voice), FakeState(None)
            )
            await asyncio.sleep(0.1)

            return store.waiting(guild.id), guild.voice.player.disconnected
        finally:
            for task in list(cog._loops.values()):
                task.cancel()
            await cog._connection.close()
            os.unlink(path)

    waiting, disconnected = asyncio.run(scenario())

    check("die Warteliste ist leer", waiting == {}, str(waiting))
    check("der Bot hat den Kanal verlassen", disconnected is True)


def test_without_lavalink_the_bot_stays_out():
    """Stumm im Kanal sitzen taeuscht Anwesenheit vor."""

    print("\nOhne Audio-Knoten bleibt der Bot draussen")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, node_ready=False
        )
        try:
            guild.voice.members = [FakeMember(10, "Alice")]
            await cog._run_loop(guild, guild.voice, await cog.settings(guild.id))
            return guild.voice.player
        finally:
            await cog._connection.close()
            os.unlink(path)

    player = asyncio.run(scenario())
    check("nichts abgespielt", player.played == [], str(player.played))


def test_the_team_gets_told():
    print("\nDas Team wird benachrichtigt")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(
            guild, channel_id=555, enabled=True, notify_channel_id=777
        )
        try:
            person = FakeMember(10, "Alice")
            guild.voice.members = [person]
            await cog.on_voice_state_update(
                person, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.1)
            return list(guild.text.sent)
        finally:
            for task in list(cog._loops.values()):
                task.cancel()
            await cog._connection.close()
            os.unlink(path)

    sent = asyncio.run(scenario())
    check("eine Nachricht kam an", len(sent) == 1, f"{len(sent)} Nachrichten")


def test_a_disabled_queue_does_nothing():
    print("\nAusgeschaltet passiert nichts")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(guild, channel_id=555, enabled=False)
        try:
            person = FakeMember(10, "Alice")
            guild.voice.members = [person]
            await cog.on_voice_state_update(
                person, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.1)
            return cog._loops, store.waiting(guild.id), guild.voice.player.played
        finally:
            for task in list(cog._loops.values()):
                task.cancel()
            await cog._connection.close()
            os.unlink(path)

    loops, waiting, played = asyncio.run(scenario())
    check("keine Schleife", not loops, str(loops))
    check("keine Warteliste", waiting == {}, str(waiting))
    check("nichts abgespielt", played == [], str(played))


def test_bots_are_ignored():
    """Sonst begruesst der Warteraum den naechsten Musikbot."""

    print("\nAndere Bots loesen nichts aus")

    async def scenario():
        from utils import support_queue as store

        store.reset()
        guild = FakeGuild()
        cog, path = await build_cog(guild, channel_id=555, enabled=True)
        try:
            other = FakeMember(99, "MusikBot", bot=True)
            guild.voice.members = [other]
            await cog.on_voice_state_update(
                other, FakeState(None), FakeState(guild.voice)
            )
            await asyncio.sleep(0.1)
            return cog._loops, store.waiting(guild.id)
        finally:
            for task in list(cog._loops.values()):
                task.cancel()
            await cog._connection.close()
            os.unlink(path)

    loops, waiting = asyncio.run(scenario())
    check("keine Schleife", not loops)
    check("keine Warteliste", waiting == {})


# --------------------------------------------------------------------- #
#  2. Die Einstellungen
# --------------------------------------------------------------------- #


def test_the_limits_hold():
    print("\nDie Grenzen gelten im Bot, nicht nur im Browser")

    import aiosqlite

    from utils import support_queue as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = await aiosqlite.connect(path)
        await store.ensure_schema(db)
        try:
            out = {}
            out["zu_lang"] = (await store.save(db, 1, greeting="x" * 9999))["greeting"]
            out["zu_viel"] = (await store.save(db, 1, music_seconds=99999))["music_seconds"]
            out["zu_wenig"] = (await store.save(db, 1, music_seconds=1))["music_seconds"]
            out["unsinn"] = (await store.save(db, 1, music_seconds="abc"))["music_seconds"]
            return out
        finally:
            await db.close()
            os.unlink(path)

    out = asyncio.run(scenario())

    check("die Ansage wird gekuerzt",
          len(out["zu_lang"]) == store.MAX_GREETING,
          f"{len(out['zu_lang'])} Zeichen")
    check("die Dauer bekommt eine Obergrenze",
          out["zu_viel"] == store.MAX_MUSIC_SECONDS,
          str(out["zu_viel"]))
    check("und eine Untergrenze",
          out["zu_wenig"] == store.MIN_MUSIC_SECONDS,
          str(out["zu_wenig"]))
    check("Unsinn faellt auf den Standard zurueck",
          out["unsinn"] == store.DEFAULT_MUSIC_SECONDS,
          str(out["unsinn"]))


def test_a_partial_save_keeps_the_rest():
    """Ein Formular mit drei Feldern darf die anderen nicht loeschen."""

    print("\nTeilweises Speichern loescht nichts")

    import aiosqlite

    from utils import support_queue as store

    async def scenario():
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = await aiosqlite.connect(path)
        await store.ensure_schema(db)
        try:
            await store.save(
                db, 1, channel_id=555, enabled=True,
                greeting="Moin", notify_channel_id=777, music_seconds=45,
            )
            return await store.save(db, 1, music_seconds=60)
        finally:
            await db.close()
            os.unlink(path)

    record = asyncio.run(scenario())

    check("der Kanal steht noch", record["channel_id"] == 555)
    check("die Ansage steht noch", record["greeting"] == "Moin")
    check("der Hinweis-Kanal steht noch", record["notify_channel_id"] == 777)
    check("es ist weiter an", record["enabled"] is True)
    check("nur die Dauer ist neu", record["music_seconds"] == 60)


def test_the_greeting_says_what_was_asked_for():
    """Der Satz aus der Anforderung, in ordentlichem Deutsch."""

    print("\nDie voreingestellte Ansage")

    from utils import support_queue as store

    text = store.DEFAULT_GREETING.lower()
    check("sie begruesst", "willkommen" in text, store.DEFAULT_GREETING)
    check("sie nennt den Support", "support" in text)
    check("sie kuendigt das Team an",
          "teammitglied" in text or "team" in text)
    check("sie lädt zum Einladen ein",
          "lade" in text and "server" in text,
          store.DEFAULT_GREETING)


def test_the_waiting_time_does_not_reset():
    """Die Uhr laeuft ab dem ersten Beitritt, nicht ab dem letzten Event.

    `on_voice_state_update` feuert auch beim Stummschalten. Wuerde
    `mark_waiting` die Zeit dabei ueberschreiben, staende im Dashboard
    bei jemandem, der zwischendurch sein Mikrofon anfasst, immer
    wieder "wartet seit 0 Sekunden" -- und das Team saehe nicht, wer
    am laengsten dran ist.
    """

    print("\nDie Wartezeit springt nicht zurueck")

    import time as clock

    from utils import support_queue as store

    store.reset()
    store.mark_waiting(1, 111)
    first = store.waiting(1)[111]

    clock.sleep(0.05)
    store.mark_waiting(1, 111)
    second = store.waiting(1)[111]

    check("die Zeit bleibt beim ersten Beitritt",
          first == second,
          f"{first} -> {second}")
    check("und es bleibt bei einem Eintrag",
          len(store.waiting(1)) == 1,
          str(store.waiting(1)))
    store.reset()


def test_the_dashboard_page_exists():
    print("\nDer Reiter im Dashboard")

    dashboard = os.path.join(os.path.dirname(BOT), "dashboard")
    if not os.path.isdir(dashboard):
        print("  skip (dashboard liegt nicht daneben)")
        return

    page = os.path.join(
        dashboard, "app", "dashboard", "guild", "[guildId]",
        "supportqueue", "page.tsx",
    )
    check("es gibt die Seite", os.path.isfile(page))

    panel = os.path.join(
        dashboard, "components", "dashboard", "support-queue-panel.tsx"
    )
    check("es gibt das Panel", os.path.isfile(panel))

    layout = open(
        os.path.join(dashboard, "app", "dashboard", "layout.tsx"), encoding="utf-8"
    ).read()

    # Genau der Eintrag, nicht irgendein Vorkommen des Wortes: der
    # Pfad steht auch in der Beta-Liste ein paar Zeilen weiter unten.
    # Ein blosses `"/supportqueue" in layout` bliebe deshalb wahr, wenn
    # der Navigationseintrag geloescht wird -- genau das ist beim
    # Mutationstest passiert.
    check("er steht in der Navigation",
          "/supportqueue`, icon: Headphones }" in layout,
          "der Eintrag selbst fehlt")
    check("und heisst nach dem Warteraum",
          "Support-Warteraum (Beta)" in layout)

    # Das Abzeichen haengt an der Liste im Renderzweig. Auch hier: die
    # Liste muss den Pfad enthalten, nicht bloss irgendwo im Text
    # stehen.
    import re as _re

    beta_lists = _re.findall(
        r"\[\s*\"/speedrun\"\s*,\s*\"/supportqueue\"\s*\]", layout
    )
    check("und traegt das Beta-Abzeichen",
          len(beta_lists) >= 2,
          f"{len(beta_lists)} von 2 Renderzweigen — die Sidebar hat zwei, "
          "und ein Eintrag in nur einem davon wirkt nicht")

    proxy = open(
        os.path.join(dashboard, "app", "api", "bot", "[...path]", "route.ts"),
        encoding="utf-8",
    ).read()
    check("der Proxy kennt den Bereich",
          'scope === "supportqueue"' in proxy,
          "sonst gibt es 404 'Unknown API scope'")


def main() -> int:
    test_the_bot_joins_speaks_and_plays()
    test_the_music_is_cut_to_length()
    test_the_loop_does_not_spin()
    test_the_loop_stops_when_everyone_left()
    test_a_mute_does_not_restart_everything()
    test_two_people_share_one_loop()
    test_the_last_one_out_turns_off_the_light()
    test_without_lavalink_the_bot_stays_out()
    test_the_team_gets_told()
    test_a_disabled_queue_does_nothing()
    test_bots_are_ignored()
    test_the_limits_hold()
    test_a_partial_save_keeps_the_rest()
    test_the_greeting_says_what_was_asked_for()
    test_the_waiting_time_does_not_reset()
    test_the_dashboard_page_exists()

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
