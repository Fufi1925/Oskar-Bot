#!/usr/bin/env python3
"""
Die zweite Haelfte des Speedruns: was der University Bot einrichtet.

Geprueft wird gegen echte SQLite-Dateien in einem Temp-Ordner, nicht
gegen Attrappen. Der Grund steht in der Geschichte dieses Projekts: die
Automod-Einstellungen wurden jahrelang gespeichert und nie gelesen, weil
Dashboard und Cog verschiedene Schluessel benutzten. Ein Test gegen eine
Attrappe haette das nie gefunden -- er haette bestaetigt, dass
gespeichert wird, was der Test selbst erwartet.

Jeder Test liest deshalb nach dem Schreiben mit *dem Weg wieder aus, den
der Bot im Betrieb nimmt*.

Run:  python3 tests/test_speedrun_handover.py
"""

import asyncio
import os
import shutil
import sys
import tempfile

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


# --------------------------------------------------------------------- #
# Attrappen: nur so viel Discord, wie die Schritte anfassen
# --------------------------------------------------------------------- #


class FakeRole:
    def __init__(self, role_id, name, position=1):
        self.id = role_id
        self.name = name
        self.position = position

    def __ge__(self, other):
        return self.position >= other.position

    def __lt__(self, other):
        return self.position < other.position


class FakeChannel:
    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name
        self.sent = []

    async def send(self, *args, **kwargs):
        message = FakeMessage(len(self.sent) + 9000, self)
        self.sent.append(kwargs.get("view") or (args[0] if args else None))
        return message


class FakeMessage:
    def __init__(self, message_id, channel):
        self.id = message_id
        self.channel = channel


class FakeMe:
    def __init__(self, top_role):
        self.top_role = top_role


class FakeGuild:
    def __init__(self):
        self.id = 1520714989860814992
        self.name = "Testserver"
        self.owner_id = 1303627964734246944

        self._roles = {
            10: FakeRole(10, "🔰・ᴜɴᴠᴇʀɪꜰɪᴇᴅ", 1),
            11: FakeRole(11, "✅・ᴠᴇʀɪꜰɪᴇᴅ", 2),
            12: FakeRole(12, "🛡️・ᴍᴏᴅᴇʀᴀᴛᴏʀ", 3),
        }
        self._channels = {
            20: FakeChannel(20, "✅・ᴠᴇʀɪꜰɪᴢɪᴇʀᴇɴ"),
            21: FakeChannel(21, "👋・ᴡɪʟʟᴋᴏᴍᴍᴇɴ"),
            22: FakeChannel(22, "🎫・ʜɪʟꜰᴇ"),
            23: FakeChannel(23, "📋・ᴍᴏᴅ-ʟᴏɢꜱ"),
            24: FakeChannel(24, "💬・ɴᴀᴄʜʀɪᴄʜᴛᴇɴ-ʟᴏɢꜱ"),
        }
        self.me = FakeMe(FakeRole(99, "Bot", 50))

    def get_role(self, role_id):
        return self._roles.get(int(role_id))

    def get_channel(self, channel_id):
        return self._channels.get(int(channel_id))


class FakeVerifyCog:
    """Das Verify-Modul, so weit die Uebergabe es braucht."""

    def __init__(self):
        self.built = 0

    def build_panel(self, guild, settings, role):
        self.built += 1
        return {"panel": True}


class FakeLoggingCog:
    def __init__(self):
        self.saved = None

    async def _save_log_config(self, guild_id, channels, enabled,
                               ignore_channels, ignore_roles,
                               ignore_users, auto_delete):
        self.saved = {
            "guild_id": guild_id,
            "channels": dict(channels),
            "enabled": dict(enabled),
        }


class FakeBot:
    def __init__(self, cogs=None):
        self._cogs = cogs or {}

    def get_cog(self, name):
        return self._cogs.get(name)


HANDOVER = {
    "template": "community",
    "guild_id": "1520714989860814992",
    "roles": {
        "unverified": "10",
        "verified": "11",
        "moderator": "12",
    },
    "staff_roles": ["12"],
    "channels": {
        "verify": "20",
        "welcome": "21",
        "tickets": "22",
        "rules": None,
        "roles": None,
        "announcements": None,
    },
    "log_channels": {
        "member_moderation": "23",
        "message_events": "24",
    },
}


def fresh_workdir():
    """Ein leerer Ordner mit db/, in dem die Schritte schreiben duerfen."""

    path = tempfile.mkdtemp(prefix="speedrun-handover-")
    os.makedirs(os.path.join(path, "db"), exist_ok=True)
    return path


def run_in(workdir, coro_factory):
    """Einen Schritt in einem eigenen Arbeitsverzeichnis laufen lassen.

    Die Pfade der Stores sind relativ (``db/verification.db``), also
    entscheidet das Arbeitsverzeichnis, welche Datei getroffen wird.
    """

    old = os.getcwd()
    os.chdir(workdir)
    try:
        return asyncio.run(coro_factory())
    finally:
        os.chdir(old)
        # Die Verbindungen des db_manager zeigen sonst auf geloeschte
        # Dateien und der naechste Test bekommt die alte Datenbank.
        from api.db_manager import db_manager

        db_manager._connections.clear()


# --------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------- #


def test_verify_is_written_and_readable():
    """Nicht "es wurde gespeichert", sondern: der Store liest es zurueck."""

    print("\nVerify landet dort, wo der Bot es sucht")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    cog = FakeVerifyCog()
    bot = FakeBot({"Verification": cog})

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER, options={"verify": True,
                                           "logging": False, "antinuke": False,
                                           "tickets": False, "welcome": False,
                                           "autorole": False, "automod": False}
        )
        # Mit demselben Weg zurueckholen, den das Verify-Cog nimmt.
        from api.db_manager import db_manager
        from utils import verify_store as store

        db = await db_manager.get_connection(store.DB_PATH)
        return report, await store.get_settings(db, guild.id)

    try:
        report, settings = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("die Schleuse ist an", settings["enabled"] is True, str(settings["enabled"]))
    check("der Kanal stimmt", str(settings["verification_channel_id"]) == "20",
          str(settings["verification_channel_id"]))
    check("die Rolle stimmt", str(settings["verified_role_id"]) == "11",
          str(settings["verified_role_id"]))
    check("die Unverifiziert-Rolle stimmt",
          str(settings["unverified_role_id"]) == "10",
          str(settings["unverified_role_id"]))
    check("das Panel wurde gepostet", cog.built == 1, str(cog.built))
    check("und es steht im Verify-Kanal", len(guild._channels[20].sent) == 1,
          str(len(guild._channels[20].sent)))
    # Die Panel-ID muss zurueckgeschrieben sein, sonst postet der naechste
    # Lauf ein zweites Panel daneben.
    check("die Panel-ID ist vermerkt", bool(settings.get("panel_message_id")),
          str(settings.get("panel_message_id")))


def test_logs_go_to_their_own_channels():
    print("\nJede Log-Art in ihren eigenen Kanal")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    cog = FakeLoggingCog()
    bot = FakeBot({"Logging": cog})

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={"logging": True, "verify": False, "antinuke": False,
                     "tickets": False, "welcome": False, "autorole": False,
                     "automod": False},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("das Cog hat gespeichert", cog.saved is not None)
    if cog.saved:
        check("Moderation zeigt auf 23",
              str(cog.saved["channels"].get("member_moderation")) == "23",
              str(cog.saved["channels"]))
        check("Nachrichten zeigen auf 24",
              str(cog.saved["channels"].get("message_events")) == "24",
              str(cog.saved["channels"]))
        # Beide eingeschaltet -- ein Kanal ohne Haken loggt nichts.
        check("beide sind eingeschaltet",
              all(cog.saved["enabled"].values()) and len(cog.saved["enabled"]) == 2,
              str(cog.saved["enabled"]))


def test_a_missing_channel_is_skipped_not_guessed():
    """Fehlt die Angabe, wird uebersprungen -- nicht der naechstbeste Kanal."""

    print("\nOhne Angabe wird nichts geraten")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot({"Verification": FakeVerifyCog()})

    blind = dict(HANDOVER)
    blind["channels"] = dict(HANDOVER["channels"], verify=None)

    async def go():
        return await ho.run_handover(
            bot, guild, blind,
            options={"verify": True, "logging": False, "antinuke": False,
                     "tickets": False, "welcome": False, "autorole": False,
                     "automod": False},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    step = next(s for s in report.steps if s.key == "verify")
    check("der Schritt scheitert sichtbar", step.ok is False)
    check("und sagt, was fehlt", "channels.verify" in step.detail, step.detail)
    # Nichts gepostet: kein Panel in einem geratenen Kanal.
    posted = sum(len(c.sent) for c in guild._channels.values())
    check("nichts wurde irgendwohin gepostet", posted == 0, str(posted))


def test_one_broken_step_does_not_stop_the_others():
    """Ein Fehler darf die restlichen Schritte nicht mitreissen."""

    print("\nEin kaputter Schritt stoppt den Rest nicht")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    # Kein Verify-Cog: der erste Schritt scheitert zwangslaeufig.
    bot = FakeBot({"Logging": FakeLoggingCog()})

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={"verify": True, "logging": True, "antinuke": True,
                     "tickets": False, "welcome": False, "autorole": False,
                     "automod": False},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    keys = {s.key: s.ok for s in report.steps}
    check("Verify scheitert", keys.get("verify") is False, str(keys))
    check("Logs laufen trotzdem", keys.get("logging") is True, str(keys))
    check("Anti-Nuke läuft trotzdem", keys.get("antinuke") is True, str(keys))


def test_antinuke_whitelists_the_owner():
    """Sonst sperrt sich der Server-Inhaber selbst aus."""

    print("\nAnti-Nuke: der Inhaber kommt auf die Whitelist")
    import aiosqlite

    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={"antinuke": True, "verify": False, "logging": False,
                     "tickets": False, "welcome": False, "autorole": False,
                     "automod": False},
        )
        async with aiosqlite.connect("db/anti.db") as db:
            async with db.execute(
                "SELECT status FROM antinuke WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                status = await cursor.fetchone()
            async with db.execute(
                "SELECT user_id, ban, chdl FROM whitelisted_users"
                " WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                white = await cursor.fetchall()
        return report, status, white

    try:
        report, status, white = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("Anti-Nuke ist an", bool(status and status[0]), str(status))
    check("der Inhaber steht drauf",
          any(int(row[0]) == guild.owner_id for row in white), str(white))
    check("und zwar für alle Aktionen",
          all(row[1] and row[2] for row in white if int(row[0]) == guild.owner_id),
          str(white))


def test_autorole_refuses_a_role_above_the_bot():
    """Eine Rolle über der Bot-Rolle kann der Bot nicht vergeben."""

    print("\nAuto-Rolle: eine zu hohe Rolle wird abgelehnt")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    # Die Unverifiziert-Rolle über den Bot schieben.
    guild._roles[10].position = 500
    bot = FakeBot()

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={"autorole": True, "verify": False, "logging": False,
                     "antinuke": False, "tickets": False, "welcome": False,
                     "automod": False},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    step = next(s for s in report.steps if s.key == "autorole")
    check("der Schritt scheitert", step.ok is False)
    check("mit einem Grund, der weiterhilft",
          "über der Bot-Rolle" in step.detail, step.detail)


def test_autorole_writes_the_format_the_cog_reads():
    """Das Cog liest ein Python-Listen-Literal, kein JSON."""

    print("\nAuto-Rolle: das Format stimmt mit dem Cog überein")
    import aiosqlite

    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={"autorole": True, "verify": False, "logging": False,
                     "antinuke": False, "tickets": False, "welcome": False,
                     "automod": False},
        )
        async with aiosqlite.connect("db/autorole.db") as db:
            async with db.execute(
                "SELECT humans FROM autorole WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
        return report, row

    try:
        report, row = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("es steht etwas drin", row is not None)

    # Genau so liest die API-Route den Wert wieder aus.
    raw = row[0] if row else ""
    parsed = [r.strip() for r in raw.replace("[", "").replace("]", "").split(",")
              if r.strip()]
    check("die Rolle kommt heil zurück", parsed == ["10"], f"{raw!r} -> {parsed}")


def test_tickets_do_not_pile_up_on_a_second_run():
    """Zweimal Speedrun darf kein zweites Panel im selben Kanal anlegen."""

    print("\nTickets: der zweite Lauf legt nichts doppelt an")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    options = {"tickets": True, "verify": False, "logging": False,
               "antinuke": False, "welcome": False, "autorole": False,
               "automod": False}

    async def go():
        from api import ticket_panels as panels
        from api.db_manager import db_manager

        await ho.run_handover(bot, guild, HANDOVER, options=options)
        await ho.run_handover(bot, guild, HANDOVER, options=options)

        db = await db_manager.get_connection("db/ticket.db")
        return await panels.list_panels(db, guild.id)

    try:
        found = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("es gibt genau ein Panel", len(found) == 1, f"{len(found)} Panels")
    if found:
        check("es zeigt auf den Ticket-Kanal",
              str(found[0]["channel_id"]) == "22", str(found[0]["channel_id"]))
        check("die Team-Rolle ist eingetragen",
              "12" in [str(r) for r in (found[0].get("staff_roles") or [])],
              str(found[0].get("staff_roles")))
        check("es gibt genau eine Kategorie",
              len(found[0].get("categories") or []) == 1,
              str(len(found[0].get("categories") or [])))


def test_unchecked_steps_are_not_run():
    """Was nicht angehakt ist, wird nicht angefasst."""

    print("\nAbgewählte Schritte laufen nicht")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    cog = FakeVerifyCog()
    bot = FakeBot({"Verification": cog, "Logging": FakeLoggingCog()})

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: False for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("kein Schritt lief", report.steps == [], str(report.as_dict()))
    check("kein Panel gepostet", cog.built == 0, str(cog.built))


def test_defaults_and_unknown_keys():
    print("\nDer Baukasten")
    from utils import speedrun_handover as ho

    defaults = ho.default_options()
    check("Verify ist standardmäßig an", defaults["verify"] is True)
    check("Automod ist standardmäßig aus", defaults["automod"] is False,
          "Automod greift in jede Nachricht ein")

    # Ein Tippfehler im Browser darf nicht stillschweigend durchgereicht
    # werden -- sonst sucht jemand ewig, warum sein Schritt nichts tut.
    cleaned = ho.normalise_options({"verify": False, "verfy": True})
    check("unbekannte Schlüssel fliegen raus", "verfy" not in cleaned, str(cleaned))
    check("bekannte werden übernommen", cleaned["verify"] is False, str(cleaned))
    check("der Rest bleibt auf Standard", cleaned["logging"] is True, str(cleaned))

    # Jeder Schritt in ORDER muss es auch wirklich geben, sonst wird er
    # nie ausgefuehrt und niemand merkt es.
    check("ORDER und STEPS passen zusammen",
          set(ho.ORDER) == set(ho.STEPS), f"{set(ho.ORDER) ^ set(ho.STEPS)}")
    check("jeder Schritt hat eine Umsetzung",
          set(ho._RUNNERS) == set(ho.STEPS),
          f"{set(ho._RUNNERS) ^ set(ho.STEPS)}")


def test_the_log_names_the_bot():
    """Das Terminal färbt nach Bot -- jede Zeile braucht die Quelle."""

    print("\nJede Zeile sagt, welcher Bot spricht")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()
    lines = []

    async def collect(text, level="info"):
        lines.append((text, level))

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={"antinuke": True, "verify": False, "logging": False,
                     "tickets": False, "welcome": False, "autorole": False,
                     "automod": False},
            log=collect,
        )

    try:
        run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("es kamen Zeilen an", len(lines) >= 1, str(lines))
    check("die Erfolgsmeldung ist als solche markiert",
          any(level == "success" for _text, level in lines), str(lines))


def main():
    test_verify_is_written_and_readable()
    test_logs_go_to_their_own_channels()
    test_a_missing_channel_is_skipped_not_guessed()
    test_one_broken_step_does_not_stop_the_others()
    test_antinuke_whitelists_the_owner()
    test_autorole_refuses_a_role_above_the_bot()
    test_autorole_writes_the_format_the_cog_reads()
    test_tickets_do_not_pile_up_on_a_second_run()
    test_unchecked_steps_are_not_run()
    test_defaults_and_unknown_keys()
    test_the_log_names_the_bot()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
