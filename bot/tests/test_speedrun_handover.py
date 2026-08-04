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
    def __init__(self, role_id, name, position=1, managed=False):
        self.id = role_id
        self.name = name
        self.position = position
        # Rollen einer Integration kann niemand vergeben -- der echte
        # Code prüft das, also muss der Fake das Feld haben.
        self.managed = managed

    def __ge__(self, other):
        return self.position >= other.position

    def __lt__(self, other):
        return self.position < other.position


class FakeCategory:
    def __init__(self, category_id, name):
        self.id = category_id
        self.name = name


class FakeChannel:
    def __init__(self, channel_id, name, category=None):
        self.id = channel_id
        self.name = name
        # Echte Kanäle liegen unter einer Kategorie. Der Ticket-Schritt
        # braucht deren ID, sonst laufen die Tickets ins Leere.
        self.category = category
        self.sent = []
        # Die Nachrichtenobjekte selbst, um Reaktionen prüfen zu können.
        self.messages: list["FakeMessage"] = []

    async def send(self, *args, **kwargs):
        message = FakeMessage(len(self.sent) + 9000, self)
        self.sent.append(kwargs.get("view") or (args[0] if args else None))
        self.messages.append(message)
        return message


class FakeMessage:
    def __init__(self, message_id, channel):
        self.id = message_id
        self.channel = channel
        self.reactions: list[str] = []

    async def add_reaction(self, emoji):
        self.reactions.append(str(emoji))


class FakePermissions:
    """Die Rechte, die die Schritte abfragen. Standard: alles erlaubt."""

    def __init__(self, **overrides):
        self.administrator = overrides.get("administrator", True)
        self.manage_roles = overrides.get("manage_roles", True)
        self.manage_channels = overrides.get("manage_channels", True)
        # Ohne "Server verwalten" sieht der Bot keine Einladungen -- der
        # echte Code prüft das, also muss der Fake das Feld kennen.
        self.manage_guild = overrides.get("manage_guild", True)


class FakeMe:
    def __init__(self, top_role, permissions=None):
        self.top_role = top_role
        self.guild_permissions = permissions or FakePermissions()


class FakeGuild:
    def __init__(self):
        self.id = 1520714989860814992
        self.name = "Testserver"
        self.owner_id = 1303627964734246944

        self._roles = {
            10: FakeRole(10, "🔰・ᴜɴᴠᴇʀɪꜰɪᴇᴅ", 1),
            11: FakeRole(11, "✅・ᴠᴇʀɪꜰɪᴇᴅ", 2),
            12: FakeRole(12, "🛡️・ᴍᴏᴅᴇʀᴀᴛᴏʀ", 3),
            13: FakeRole(13, "🎨・ᴄᴏɴᴛᴇɴᴛ ᴄʀᴇᴀᴛᴏʀ", 4),
            14: FakeRole(14, "🖌️・ᴅᴇꜱɪɢɴᴇʀ", 5),
            15: FakeRole(15, "👤・ᴍᴇᴍʙᴇʀ", 6),
            16: FakeRole(16, "🌟・ᴀᴄᴛɪᴠᴇ", 7),
            17: FakeRole(17, "💎・ᴠɪᴘ", 8),
        }
        self._channels = {
            20: FakeChannel(20, "✅・ᴠᴇʀɪꜰɪᴢɪᴇʀᴇɴ"),
            21: FakeChannel(21, "👋・ᴡɪʟʟᴋᴏᴍᴍᴇɴ"),
            22: FakeChannel(22, "🎫・ʜɪʟꜰᴇ", category=FakeCategory(99, "🛟・ʜɪʟꜰᴇ")),
            23: FakeChannel(23, "📋・ᴍᴏᴅ-ʟᴏɢꜱ"),
            24: FakeChannel(24, "💬・ɴᴀᴄʜʀɪᴄʜᴛᴇɴ-ʟᴏɢꜱ"),
            25: FakeChannel(25, "🔢・ᴢᴀᴇʜʟᴇɴ"),
            26: FakeChannel(26, "🔊・ᴀʟʟɢᴇᴍᴇɪɴᴇʀ-ᴛᴀʟᴋ"),
            27: FakeChannel(27, "📜・ʀᴇɢᴇʟɴ"),
            28: FakeChannel(28, "🏷️・ʀᴏʟʟᴇɴ-ᴠᴇʀɢᴀʙᴇ"),
            29: FakeChannel(29, "📨・ᴇɪɴʟᴀᴅᴜɴɢꜱ-ʟᴏɢꜱ"),
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
            # Auch die Ausnahmen festhalten: ohne sie protokolliert
            # jeder Log-Eintrag den nächsten, und ein Fake, der das Feld
            # wegwirft, könnte das nie zeigen.
            "ignore_channels": list(ignore_channels),
            "ignore_roles": list(ignore_roles),
            "ignore_users": list(ignore_users),
            "auto_delete": auto_delete,
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
        "member": "15",
        "active": "16",
        "vip": "17",
    },
    "staff_roles": ["12"],
    "channels": {
        "verify": "20",
        "welcome": "21",
        "tickets": "22",
        "counting": "25",
        "j2c": "26",
        "rules": "27",
        "roles": "28",
        "invite_log": "29",
        "announcements": None,
    },
    # Die Akzent-Rollen des Templates: die darf sich jeder selbst geben.
    "self_roles": [
        {"id": "13", "name": "🎨・ᴄᴏɴᴛᴇɴᴛ ᴄʀᴇᴀᴛᴏʀ", "emoji": "🎨", "key": "creator"},
        {"id": "14", "name": "🖌️・ᴅᴇꜱɪɢɴᴇʀ", "emoji": "🖌️", "key": "designer"},
    ],
    "log_channels": {
        "member_moderation": "23",
        "message_events": "24",
    },
}


def _find_selects(view):
    """Alle Dropdowns einer View, beliebig tief verschachtelt."""

    import discord

    found = []

    def walk(item):
        if isinstance(item, discord.ui.Select):
            found.append(item)
        for child in getattr(item, "children", []) or []:
            walk(child)

    for child in getattr(view, "children", []) or []:
        walk(child)
    return found


def _find_buttons(view):
    """Alle Knöpfe einer View, beliebig tief verschachtelt."""

    import discord

    found = []

    def walk(item):
        if isinstance(item, discord.ui.Button):
            found.append(item)
        for child in getattr(item, "children", []) or []:
            walk(child)

    for child in getattr(view, "children", []) or []:
        walk(child)
    return found


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

    from api.db_manager import db_manager

    async def wrapped():
        try:
            return await coro_factory()
        finally:
            # Die Verbindungen zeigen sonst auf geloeschte Dateien und
            # der naechste Test bekaeme die alte Datenbank.
            #
            # Und sie muessen *geschlossen* werden, nicht nur aus dem
            # Zwischenspeicher geworfen: jede aiosqlite-Verbindung haelt
            # einen eigenen Thread offen. Ein blosses .clear() liess sie
            # laufen, und der Prozess hing am Ende ewig beim Beenden --
            # der Test war fertig, das Programm kam nie zurueck. Mein
            # Fehler aus der letzten Runde.
            await db_manager.close_all()

    old = os.getcwd()
    os.chdir(workdir)
    try:
        return asyncio.run(wrapped())
    finally:
        os.chdir(old)


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
            bot, guild, HANDOVER, options={key: key == "verify" for key in ho.STEPS}
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
            options={key: key == "logging" for key in ho.STEPS},
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
        # Nur Verify. Die Schritte einzeln aufzuzählen war brüchig: ein
        # neuer Schritt fehlte in der Liste, lief mit seinem Standard
        # mit und postete dann doch etwas.
        return await ho.run_handover(
            bot, guild, blind,
            options={key: key == "verify" for key in ho.STEPS},
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
            options={key: key in ("verify", "logging", "antinuke") for key in ho.STEPS},
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
            options={key: key == "antinuke" for key in ho.STEPS},
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
            options={key: key == "autorole" for key in ho.STEPS},
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
            options={key: key == "autorole" for key in ho.STEPS},
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
        # Dropdown: die Liste bleibt auch mit mehreren Kategorien
        # lesbar, und Discord erlaubt nur fünf Knöpfe je Reihe.
        check("es ist ein Dropdown",
              found[0]["panel_type"] == "dropdown",
              str(found[0]["panel_type"]))
        check("die Team-Rolle ist eingetragen",
              "12" in [str(r) for r in (found[0].get("staff_roles") or [])],
              str(found[0].get("staff_roles")))
        cats = found[0].get("categories") or []
        check("es gibt drei Kategorien", len(cats) == 3, str(len(cats)))

        # Ohne discord_category_id bricht jeder Klick auf den Ticket-Knopf
        # ab: der Cog antwortet "This ticket category has been deleted or
        # is misconfigured". Genau das war der gemeldete Fehler.
        missing = [c["name"] for c in cats if not c.get("discord_category_id")]
        check("jede Kategorie kennt ihre Discord-Kategorie",
              not missing, str(missing))

        # Zwei gleiche Emojis im selben Dropdown kann man nicht
        # auseinanderhalten.
        icons = [c.get("emoji") for c in cats if c.get("emoji")]
        check("kein Emoji doppelt", len(icons) == len(set(icons)), str(icons))


def test_counting_is_actually_switched_on():
    """Der Kanal allein zählt nicht -- das Spiel muss scharf sein.

    Der Template-Bot legt den Zähl-Kanal an und schreibt eine 1 hinein.
    Im Hauptbot steht das Spiel aber auf ``enabled: False`` mit
    ``channel: None``. Ohne diesen Schritt sieht der Kanal fertig aus
    und reagiert auf keine Zahl -- genau das war die Meldung.
    """

    print("\nDas Zählspiel läuft danach wirklich")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "counting" for key in ho.STEPS},
        )
        # Mit demselben Weg zurücklesen, den das Counting-Cog nimmt.
        from utils import extras_store as store

        return report, store.counting_get(guild.id)

    try:
        report, settings = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("das Spiel ist an", settings["enabled"] is True, str(settings["enabled"]))
    check("der Kanal stimmt", str(settings["channel"]) == "25",
          str(settings["channel"]))
    # Der Template-Bot hat die 1 schon gepostet. Stünde hier 0, würde
    # der Bot die nächste Zahl als 1 erwarten und die 2 als Fehler
    # werten -- das Spiel wäre kaputt, bevor jemand mitspielt.
    check("der Stand berücksichtigt die gepostete 1",
          settings["current"] == 1, str(settings["current"]))


def test_j2c_points_at_a_voice_channel():
    print("\nJoin to Create hängt am Sprachkanal")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "j2c" for key in ho.STEPS},
        )
        from api.db_manager import db_manager
        from utils import voice_store as store

        db = await db_manager.get_connection("db/j2c_data.db")
        return report, await store.j2c_get(db, guild.id)

    try:
        report, settings = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("der Sprachkanal ist eingetragen",
          str(settings.get("join_channel_id")) == "26",
          str(settings.get("join_channel_id")))


def test_leveling_is_on():
    print("\nDas Level-System ist an")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "leveling" for key in ho.STEPS},
        )
        from api.db_manager import db_manager
        from utils import leveling_store as store

        db = await db_manager.get_connection(store.DB_PATH)
        return report, await store.get_settings(db, guild.id)

    try:
        report, settings = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("XP sind eingeschaltet", bool(settings.get("enabled")),
          str(settings.get("enabled")))


def test_the_ticket_panel_is_posted_not_just_prepared():
    """Ein Speedrun, der auf halbem Weg stehen bleibt, ist keiner."""

    print("\nDas Ticket-Panel steht im Kanal")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "tickets" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    # In den Ticket-Kanal (22) muss eine Nachricht gegangen sein.
    check("im Ticket-Kanal steht etwas",
          len(guild._channels[22].sent) == 1,
          f"{len(guild._channels[22].sent)} Nachrichten")
    # Und nur dort -- nicht versehentlich in einen anderen Kanal.
    elsewhere = {
        cid: len(c.sent) for cid, c in guild._channels.items()
        if cid != 22 and c.sent
    }
    check("und sonst nirgends", not elsewhere, str(elsewhere))


def test_self_roles_are_posted_with_reactions():
    """Der Rollen-Kanal blieb leer -- mein Fehler.

    Ich hatte dem Template-Bot das Rollen-Dropdown weggenommen (weil der
    Hauptbot die Rollen führt) und den Ersatz nicht gebaut. Der Kanal
    stand danach da und enthielt nichts.
    """

    print("\nDie Rollen-Vergabe steht im Kanal")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "selfroles" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("im Rollen-Kanal steht ein Panel",
          len(guild._channels[28].sent) == 1,
          f"{len(guild._channels[28].sent)} Nachrichten")

    # Ein Dropdown, keine Reaktionen. Eine Reaktion ist ein einzelnes
    # Emoji -- zwei Rollen mit demselben Emoji wären nicht zu
    # unterscheiden, und darum ging es beim Wechsel.
    posted = guild._channels[28].messages
    check("es wurde eine Nachricht behalten", len(posted) == 1)
    check("es werden keine Reaktionen mehr gesetzt",
          posted and not posted[0].reactions, str(posted[0].reactions if posted else None))

    view = guild._channels[28].sent[0]
    selects = _find_selects(view)
    check("es gibt ein Dropdown", len(selects) == 1, str(len(selects)))
    if selects:
        select = selects[0]
        from cogs.events import selfroles as sr

        check("der Listener erkennt es wieder",
              select.custom_id == sr.CUSTOM_ID, str(select.custom_id))
        check("beide Rollen stehen drin",
              len(select.options) == 2, str(len(select.options)))
        # min_values=0: abwählen muss möglich sein, sonst wird man eine
        # Rolle nie wieder los.
        check("abwählen ist möglich", select.min_values == 0,
              str(select.min_values))
        check("mehrere gleichzeitig wählbar",
              select.max_values == 2, str(select.max_values))


def test_self_roles_skip_a_role_above_the_bot():
    """Eine Rolle, die der Bot nicht vergeben kann, darf nicht dastehen.

    Sie wäre anklickbar und würde nichts tun -- schlimmer, als sie
    wegzulassen.
    """

    print("\nUnvergebbare Rollen kommen nicht ins Panel")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    # Content Creator über die Bot-Rolle schieben.
    guild._roles[13].position = 500
    bot = FakeBot()

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "selfroles" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt läuft trotzdem", not report.failed, str(report.failed))
    selects = _find_selects(guild._channels[28].sent[0])
    if selects:
        check("nur die vergebbare Rolle ist drin",
              len(selects[0].options) == 1,
              str([o.label for o in selects[0].options]))


def test_duplicate_emojis_are_dropped():
    """Zwei gleiche Emojis im Dropdown kann niemand unterscheiden.

    Die normalen Testdaten haben zufällig verschiedene Emojis -- damit
    liefe die Entdopplung nie und der Test wäre wertlos. Hier stehen
    absichtlich zwei gleiche.
    """

    print("\nDoppelte Emojis fliegen raus")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    same = dict(HANDOVER)
    same["self_roles"] = [
        {"id": "13", "name": "Creator", "emoji": "🎨", "key": "creator"},
        {"id": "14", "name": "Designer", "emoji": "🎨", "key": "designer"},
    ]

    async def go():
        return await ho.run_handover(
            bot, guild, same,
            options={key: key == "selfroles" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))

    selects = _find_selects(guild._channels[28].sent[0])
    check("es gibt ein Dropdown", len(selects) == 1)
    if selects:
        options = selects[0].options
        # Beide Rollen bleiben -- nur das doppelte Emoji fällt weg.
        check("beide Rollen stehen drin", len(options) == 2, str(len(options)))
        icons = [str(o.emoji) for o in options if o.emoji]
        check("das Emoji kommt nur einmal vor",
              len(icons) == len(set(icons)), str(icons))
        check("genau eines behält es", len(icons) == 1, str(icons))


def test_rules_are_posted():
    print("\nDie Regeln stehen im Regel-Kanal")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "rules" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("im Regel-Kanal steht etwas",
          len(guild._channels[27].sent) == 1,
          f"{len(guild._channels[27].sent)} Nachrichten")
    # Und der Text sagt, dass er angepasst gehört -- sonst stehen auf
    # jedem Server dieselben sechs Sätze und niemand merkt es.
    step = next(s for s in report.steps if s.key == "rules")
    check("der Hinweis aufs Anpassen fehlt nicht",
          "anpassen" in step.detail.lower(), step.detail)


def test_the_panels_use_custom_emojis():
    """Die App hat 142 eigene Emojis -- die neuen Panels nutzen sie auch."""

    print("\nEigene Emojis in den neuen Panels")
    import re

    source = open(
        os.path.join(BOT, "utils", "speedrun_handover.py"), encoding="utf-8"
    ).read()
    # Kommentare raus, sonst zählt eine Erklärung als Verwendung.
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    check("die Emoji-Sammlung wird benutzt", "emoji_set." in code)
    used = set(re.findall(r"emoji_set\.([A-Z_]+)", code))
    check("mehrere verschiedene Emojis", len(used) >= 3, str(used))

    # Und die Namen gibt es wirklich -- ein Tippfehler wäre ein
    # AttributeError mitten im Bau.
    from utils import emoji as emoji_set

    missing = [name for name in used if not hasattr(emoji_set, name)]
    check("alle Namen existieren", not missing, str(missing))

    # Sie müssen auch wie Discord-Emojis aussehen, nicht wie Text.
    for name in sorted(used):
        value = str(getattr(emoji_set, name))
        check(f"{name} ist ein Custom-Emoji",
              value.startswith("<") and value.endswith(">"), value)


def test_tickets_show_up_in_the_overview():
    """Die Übersicht liest guild_configs, nicht ticket_panels.

    Ohne eine Zeile dort stand »Tickets« als nicht eingerichtet da,
    obwohl das Panel im Kanal hing -- so wurde es gemeldet.
    """

    print("\nTickets stehen in der Übersicht")
    import aiosqlite

    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "tickets" for key in ho.STEPS},
        )
        # Genau die Abfrage, die die Übersicht stellt.
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute(
                "SELECT COUNT(*) FROM guild_configs WHERE guild_id = ?",
                (guild.id,),
            ) as cursor:
                rows = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT panel_channel_id, staff_roles FROM guild_configs"
                " WHERE guild_id = ?",
                (guild.id,),
            ) as cursor:
                entry = await cursor.fetchone()
        return report, rows, entry

    try:
        report, rows, entry = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("es gibt eine Zeile in guild_configs", rows == 1, str(rows))
    if entry:
        check("der Panel-Kanal ist vermerkt", str(entry[0]) == "22", str(entry[0]))
        check("die Team-Rollen sind vermerkt", "12" in str(entry[1]), str(entry[1]))


def test_log_channels_do_not_log_themselves():
    """Sonst protokolliert jeder Log-Eintrag den nächsten."""

    print("\nDie Log-Kanäle sind vom Protokoll ausgenommen")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    cog = FakeLoggingCog()
    bot = FakeBot({"Logging": cog})

    async def go():
        return await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "logging" for key in ho.STEPS},
        )

    try:
        report = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("das Cog hat die Ausnahmen bekommen",
          cog.saved is not None and cog.saved.get("ignore_channels"),
          str(cog.saved))
    if cog.saved:
        ignored = set(cog.saved["ignore_channels"])
        used = set(cog.saved["channels"].values())
        check("jeder Log-Kanal steht auf der Ausnahmeliste",
              used <= ignored, f"{used - ignored} fehlen")


def test_the_welcome_message_reads_german_and_is_filled_in():
    """Platzhalter, Autorzeile und Fußzeile müssen wirklich ankommen.

    Zwei Fallen hier, beide vermieden statt geraten:

      * Die Platzhalter heißen `{server_name}` und
        `{server_membercount}`. Ein `{server}` bliebe roh im Text stehen.
      * build_embed() liest flache Schlüssel `author_name`/`footer_text`.
        Ein verschachteltes `{"author": {...}}` würde kommentarlos
        ignoriert -- die Zeile fehlte einfach.
    """

    print("\nDie Willkommensnachricht ist deutsch und ausgefüllt")
    import json as _json
    import re as _re

    from utils import greet_render

    source = open(
        os.path.join(BOT, "utils", "speedrun_handover.py"), encoding="utf-8"
    ).read()
    block = source.split("json.dumps(")[1]
    depth, end = 0, 0
    for index, char in enumerate(block):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    raw = block[block.index("{"):end]
    raw = _re.sub(r"^\s*#.*$", "", raw, flags=_re.M)
    info = eval(raw)  # noqa: S307 -- eigener Quelltext, kein Fremdeingabe

    check("die Autorzeile ist flach", "author_name" in info, str(sorted(info)))
    check("die Fußzeile ist flach", "footer_text" in info, str(sorted(info)))
    check("die Fußzeile nennt den Bot",
          "University Bot" in info.get("footer_text", ""),
          info.get("footer_text"))

    class _Icon:
        url = "https://cdn.discordapp.com/icons/1/a.png"

    class _Guild:
        name = "University Support"
        id = 1
        member_count = 1247
        icon = _Icon()

    class _Avatar:
        url = "https://cdn.discordapp.com/avatars/2/b.png"

    class _Member:
        mention = "<@2>"
        name = "fufi"
        id = 2
        display_name = "Fufi"
        guild = _Guild()
        display_avatar = _Avatar()
        joined_at = None
        created_at = None

    embed = greet_render.build_embed(info, greet_render.placeholders(_Member()))

    check("der Servername steht als Autor da",
          embed.author.name == "University Support", str(embed.author.name))
    check("das Servericon ist gesetzt", bool(embed.author.icon_url))
    check("die Fußzeile kommt an",
          embed.footer.text == "by University Bot", str(embed.footer.text))

    text = (embed.description or "") + (embed.author.name or "")
    leftover = _re.findall(r"\{[a-z_]+\}", text)
    check("kein Platzhalter bleibt stehen", not leftover, str(leftover))
    check("die Mitgliedszahl ist eingesetzt", "1247" in text, text[:80])
    check("der Text ist deutsch", "Schön, dass du da bist" in text, text[:80])

    _json.dumps(info)  # muss serialisierbar bleiben


def test_the_ticket_panel_matches_its_stored_type():
    """Dashboard sagte Dropdown, in Discord standen Knöpfe.

    Der Speedrun baute die View unbedingt aus Knöpfen, während in der
    Datenbank "dropdown" stand. Schlimmer als nur unschön: der Cog baut
    die View nach einem Neustart aus panel_type neu -- die Nachricht
    hätte nach dem nächsten Deploy anders ausgesehen als vorher.
    """

    print("\nDas Panel sieht aus, wie es gespeichert ist")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        from api import ticket_panels as panels
        from api.db_manager import db_manager

        await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "tickets" for key in ho.STEPS},
        )
        db = await db_manager.get_connection("db/ticket.db")
        return await panels.list_panels(db, guild.id)

    try:
        found = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("es gibt ein Panel", len(found) == 1, str(len(found)))
    stored = found[0]["panel_type"] if found else None

    view = guild._channels[22].sent[0]
    selects = _find_selects(view)
    buttons = _find_buttons(view)

    check("gespeichert ist dropdown", stored == "dropdown", str(stored))
    check("und gepostet wurde ein Dropdown", len(selects) == 1, str(len(selects)))
    check("ohne Knöpfe daneben", not buttons, str(len(buttons)))

    if selects:
        # Genau die custom_id, auf die der Ticket-Cog hört. Eine andere
        # und der Klick verpufft.
        check("der Cog erkennt es wieder",
              selects[0].custom_id == "create_ticket_select",
              str(selects[0].custom_id))
        check("alle drei Kategorien stehen drin",
              len(selects[0].options) == 3, str(len(selects[0].options)))


def test_level_rewards_are_set():
    """Ohne Belohnungen sammelt man XP und bekommt nie etwas dafür."""

    print("\nLevel-Aufstiege bringen Rollen")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        from api.db_manager import db_manager
        from utils import leveling_store as store

        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "leveling" for key in ho.STEPS},
        )
        db = await db_manager.get_connection(store.DB_PATH)
        return report, await store.rewards(db, guild.id)

    try:
        report, rewards = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("es gibt drei Belohnungen", len(rewards) == 3, str(rewards))

    by_level = {r["level"]: r["role_id"] for r in rewards}
    check("Level 5 gibt es", 5 in by_level, str(sorted(by_level)))
    check("die Stufen steigen an",
          sorted(by_level) == [5, 15, 30], str(sorted(by_level)))
    # Und jede Stufe eine andere Rolle -- dreimal dieselbe wäre sinnlos.
    check("jede Stufe eine eigene Rolle",
          len(set(by_level.values())) == 3, str(by_level))


def test_a_level_role_above_the_bot_is_skipped():
    """Sie einzutragen hieße: beim Aufstieg passiert nichts."""

    print("\nZu hohe Level-Rollen werden nicht eingetragen")
    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    guild._roles[17].position = 500  # VIP über die Bot-Rolle
    bot = FakeBot()

    async def go():
        from api.db_manager import db_manager
        from utils import leveling_store as store

        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "leveling" for key in ho.STEPS},
        )
        db = await db_manager.get_connection(store.DB_PATH)
        return report, await store.rewards(db, guild.id)

    try:
        report, rewards = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("die anderen zwei bleiben", len(rewards) == 2, str(rewards))
    step = next(s for s in report.steps if s.key == "leveling")
    check("und es wird gesagt, welche fehlt",
          "über der Bot-Rolle" in step.detail, step.detail)


def test_invite_tracking_gets_a_channel():
    print("\nDas Einladungs-Protokoll bekommt einen Kanal")
    import aiosqlite

    from utils import speedrun_handover as ho

    workdir = fresh_workdir()
    guild = FakeGuild()
    bot = FakeBot()

    async def go():
        report = await ho.run_handover(
            bot, guild, HANDOVER,
            options={key: key == "tracking" for key in ho.STEPS},
        )
        async with aiosqlite.connect("db/invite.db") as db:
            async with db.execute(
                "SELECT channel_id FROM logging WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
        return report, row

    try:
        report, row = run_in(workdir, go)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    check("der Schritt meldet Erfolg", not report.failed, str(report.failed))
    check("der Kanal ist eingetragen", row is not None and str(row[0]) == "29",
          str(row))


def test_the_ticket_greeting_has_no_dead_image():
    """Eine abgelaufene CDN-Adresse kostet die ganze Nachricht.

    Im Ticket-Cog stand eine Discord-Anhang-URL mit Ablaufsignatur. Sie
    liefert seit Monaten 403, Discord lehnt das Embed mit dem toten Bild
    ab -- und der frisch erstellte Ticket-Kanal blieb leer.
    """

    print("\nKeine ablaufenden Bild-Adressen im Ticket")
    import re

    source = open(
        os.path.join(BOT, "cogs", "commands", "ticket.py"), encoding="utf-8"
    ).read()
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    # Anhang-URLs tragen eine Ablaufsignatur (?ex=...). Sie sind für
    # dauerhafte Nachrichten grundsätzlich untauglich.
    expiring = re.findall(r"cdn\.discordapp\.com/attachments/[^\"'\s]+", code)
    check("keine ablaufende Anhang-URL mehr", not expiring, str(expiring)[:120])

    # Und content darf nicht zusammen mit einer V2-View gehen: mit dem
    # V2-Flag gibt es kein content-Feld, Discord antwortet mit 50035.
    #
    # Über den Syntaxbaum, nicht mit einem Muster. Mein erster Versuch
    # war `send\(\s*content=[^)]*view=from_embed` -- und `[^)]*` stoppt
    # an der ersten Klammer, die hier in `" ".join(pings)` steckt. Der
    # Aufruf blieb also unentdeckt, obwohl er genau danebenstand.
    import ast

    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        names = {kw.arg for kw in node.keywords if kw.arg}
        if "content" not in names or "view" not in names:
            continue
        view_arg = next(kw.value for kw in node.keywords if kw.arg == "view")
        rendered = ast.unparse(view_arg)
        # Nur V2-Views zählen: from_embed, Panel, StatusCard und Co.
        if any(marker in rendered for marker in ("from_embed", "Panel(", "CV2(")):
            offenders.append(f"Zeile {node.lineno}: {rendered[:60]}")

    check("kein content zusammen mit einer V2-View",
          not offenders, str(offenders)[:200])


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

    # Automod war zuerst standardmäßig aus, mit der Begründung, dass er
    # in jede Nachricht eingreift. Das war die falsche Abwägung: ein
    # frischer Server ohne Spam-Bremse ist genau das, wonach Werbe-Bots
    # suchen, und wer den Speedrun laufen lässt, will einen fertigen
    # Server — keinen mit einer abgeschalteten Schutzfunktion, von der
    # er nichts weiß. Die Team-Rollen sind ausgenommen, und fünf
    # Nachrichten in zehn Sekunden schreibt niemand aus Versehen.
    check("Automod ist standardmäßig an", defaults["automod"] is True,
          "ein frischer Server ohne Spam-Bremse ist ein Ziel")

    # Alles, was der Speedrun ohne Zutun anschaltet, muss auch abwählbar
    # sein — sonst ist der Baukasten eine Behauptung.
    for key in ho.STEPS:
        cleaned = ho.normalise_options({key: False})
        check(f"„{key}“ lässt sich abwählen", cleaned[key] is False)

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
            options={key: key == "antinuke" for key in ho.STEPS},
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
    test_counting_is_actually_switched_on()
    test_j2c_points_at_a_voice_channel()
    test_leveling_is_on()
    test_the_ticket_panel_is_posted_not_just_prepared()
    test_tickets_show_up_in_the_overview()
    test_log_channels_do_not_log_themselves()
    test_the_welcome_message_reads_german_and_is_filled_in()
    test_self_roles_are_posted_with_reactions()
    test_self_roles_skip_a_role_above_the_bot()
    test_duplicate_emojis_are_dropped()
    test_rules_are_posted()
    test_the_panels_use_custom_emojis()
    test_the_ticket_panel_matches_its_stored_type()
    test_level_rewards_are_set()
    test_a_level_role_above_the_bot_is_skipped()
    test_invite_tracking_gets_a_channel()
    test_the_ticket_greeting_has_no_dead_image()
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
