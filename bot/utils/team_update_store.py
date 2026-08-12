# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Update                                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Team-Update: Befoerderungen, Rueckstufungen, Rauswuerfe, Verwarnungen.

Worum es geht
-------------
Ein Team veraendert sich staendig: jemand wird Moderator, jemand
rutscht zurueck auf Supporter, jemand fliegt raus. Bisher hiess das:
Rollen von Hand umstecken und danach in einen Kanal schreiben, was
passiert ist. Zwei Schritte, von denen der zweite regelmaessig
vergessen wird -- und dann steht im Team-Kanal eine Befoerderung von
vor drei Monaten als letzte Nachricht.

Fuenf Befehle machen beides in einem Zug:

  ``/uprank``      alte Rolle weg, neue Rolle drauf, Ankuendigung
  ``/downrank``    dasselbe in die andere Richtung
  ``/teamkick``    alle Teamrollen weg, Ankuendigung, Akte geschlossen
  ``/teamwarn``    Verwarnung in die Akte, DM, optional Folge
  ``/teamanfang``  Aufnahme ins Team

Unterschriften
--------------
Jede Aktion traegt mindestens eine Unterschrift: die Person, die den
Befehl abgeschickt hat. Das ist keine Formalitaet -- wer eine
Befoerderung ausspricht, soll darunterstehen. Bis zu vier weitere
lassen sich angeben, wenn eine Entscheidung im Team gemeinsam
getroffen wurde.

Warum die Reihenfolge "erst weg, dann drauf" falsch waere
---------------------------------------------------------
Umgekehrt: **erst die neue Rolle geben, dann die alte nehmen**.
Scheitert der erste Schritt (Rollenordnung, fehlende Rechte), steht
die Person noch dort, wo sie vorher war. Andersherum haette ein
halber Fehlschlag jemanden ohne jede Rolle zurueckgelassen -- und
zwar genau in dem Moment, in dem er befoerdert werden sollte.

Die Automatik bei Verwarnungen
------------------------------
Standard ist aus. Wer sie einschaltet, legt eine Schwelle fest und
was dann passiert: zurueckstufen oder rauswerfen. Die Zaehlung nimmt
nur Verwarnungen, die noch gelten -- eine Verfallszeit ist
einstellbar, sonst summiert sich ueber zwei Jahre alles auf.

Speicher
--------
``db/team_update.db``. Braucht ein Railway-Volume, sonst ist die
Team-Akte nach dem naechsten Deploy leer -- und die Verwarnungs-
Automatik zaehlt wieder bei null.
"""

from __future__ import annotations

import json
import time

from utils import db_paths

DB_PATH = "db/team_update.db"

# ── Grenzen ──────────────────────────────────────────────────────────
#
# Fuenf Unterschriften: die erste ist immer die des Ausfuehrenden, vier
# weitere lassen sich anhaengen. Mehr passt nicht mehr lesbar in eine
# Zeile der Ankuendigung.
MAX_SIGNERS = 5

# Vier zusaetzliche also, weil der Ausfuehrende schon einer ist.
MAX_EXTRA_SIGNERS = MAX_SIGNERS - 1

MAX_REASON = 1000
MAX_TEMPLATE = 1500
MAX_STAFF_ROLES = 15

# Wie viele Eintraege die Akte im Dashboard hoechstens ausliefert.
# Alles darueber ist Blaettern, und dafuer gibt es den Versatz.
MAX_HISTORY = 100

# ── Die fuenf Aktionen ───────────────────────────────────────────────
#
# Die Schluessel stehen so in der Datenbank, in der API und im
# Dashboard. Ein Tippfehler an einer Stelle faellt sonst erst auf,
# wenn eine Ankuendigung im falschen Kanal landet.
ACTION_UPRANK = "uprank"
ACTION_DOWNRANK = "downrank"
ACTION_KICK = "kick"
ACTION_WARN = "warn"
ACTION_JOIN = "join"

ACTIONS = (
    ACTION_UPRANK,
    ACTION_DOWNRANK,
    ACTION_KICK,
    ACTION_WARN,
    ACTION_JOIN,
)

# Anzeigenamen -- einmal hier, damit Bot und Dashboard dieselben
# Woerter benutzen.
ACTION_LABELS = {
    ACTION_UPRANK: "Befoerderung",
    ACTION_DOWNRANK: "Rueckstufung",
    ACTION_KICK: "Team-Ausschluss",
    ACTION_WARN: "Verwarnung",
    ACTION_JOIN: "Aufnahme",
}

# Was die Automatik nach zu vielen Verwarnungen tun darf.
FOLLOWUP_NONE = "none"
FOLLOWUP_DOWNRANK = "downrank"
FOLLOWUP_KICK = "kick"
FOLLOWUPS = (FOLLOWUP_NONE, FOLLOWUP_DOWNRANK, FOLLOWUP_KICK)

# ── Vorlagen ─────────────────────────────────────────────────────────
#
# Platzhalter, die in jeder Vorlage erlaubt sind. Die Liste steht hier
# und nicht nur im Dashboard, damit die Hilfe unter dem Textfeld
# dieselbe ist, die der Bot wirklich ersetzt.
PLACEHOLDERS = (
    "{user}",        # Erwaehnung der betroffenen Person
    "{user_name}",   # ihr Anzeigename
    "{user_id}",
    "{alt}",         # alte Rolle (Erwaehnung)
    "{alt_name}",
    "{neu}",         # neue Rolle (Erwaehnung)
    "{neu_name}",
    "{grund}",
    "{unterschriften}",
    "{actor}",       # wer den Befehl abgeschickt hat
    "{server}",
    "{anzahl}",      # bei Verwarnungen: wie viele gelten jetzt
    "{datum}",       # Discord-Zeitstempel, passt sich der Zeitzone an
)

DEFAULT_TEMPLATES = {
    ACTION_UPRANK: (
        "{user} wurde befördert.\n"
        "**Vorher:** {alt}\n**Jetzt:** {neu}\n\n"
        "**Grund:** {grund}\n\n"
        "*Unterschrift: {unterschriften}*"
    ),
    ACTION_DOWNRANK: (
        "{user} wurde zurückgestuft.\n"
        "**Vorher:** {alt}\n**Jetzt:** {neu}\n\n"
        "**Grund:** {grund}\n\n"
        "*Unterschrift: {unterschriften}*"
    ),
    ACTION_KICK: (
        "{user} ist nicht mehr im Team.\n"
        "**Bisher:** {alt}\n\n"
        "**Grund:** {grund}\n\n"
        "*Unterschrift: {unterschriften}*"
    ),
    ACTION_WARN: (
        "{user} wurde verwarnt.\n"
        "**Verwarnungen:** {anzahl}\n\n"
        "**Grund:** {grund}\n\n"
        "*Unterschrift: {unterschriften}*"
    ),
    ACTION_JOIN: (
        "{user} ist neu im Team.\n"
        "**Rolle:** {neu}\n\n"
        "**Grund:** {grund}\n\n"
        "*Unterschrift: {unterschriften}*"
    ),
}

DEFAULT_TITLES = {
    ACTION_UPRANK: "Beförderung",
    ACTION_DOWNRANK: "Rückstufung",
    ACTION_KICK: "Team-Ausschluss",
    ACTION_WARN: "Verwarnung",
    ACTION_JOIN: "Neu im Team",
}

DEFAULT_COLOURS = {
    ACTION_UPRANK: 0x22C55E,
    ACTION_DOWNRANK: 0xF59E0B,
    ACTION_KICK: 0xEF4444,
    ACTION_WARN: 0xF97316,
    ACTION_JOIN: 0x3B82F6,
}

# DM-Vorlagen. Getrennt von der Ankuendigung, weil eine DM die Person
# direkt anspricht und der Kanaltext ueber sie spricht.
DEFAULT_DM = {
    ACTION_UPRANK: (
        "Du wurdest auf **{server}** befördert: {alt_name} → **{neu_name}**.\n\n"
        "**Grund:** {grund}"
    ),
    ACTION_DOWNRANK: (
        "Du wurdest auf **{server}** zurückgestuft: {alt_name} → **{neu_name}**.\n\n"
        "**Grund:** {grund}"
    ),
    ACTION_KICK: (
        "Du bist auf **{server}** nicht mehr im Team.\n\n**Grund:** {grund}"
    ),
    ACTION_WARN: (
        "Du hast auf **{server}** eine Team-Verwarnung bekommen "
        "({anzahl} insgesamt).\n\n**Grund:** {grund}"
    ),
    ACTION_JOIN: (
        "Willkommen im Team von **{server}**! Deine Rolle: **{neu_name}**.\n\n"
        "**Grund:** {grund}"
    ),
}


# ── Schema ───────────────────────────────────────────────────────────
#
# Die Spalten von ``team_settings`` -- an EINER Stelle.
#
# Warum abgeleitet und nicht zweimal getippt: die erste Fassung hatte
# das CREATE TABLE ausgeschrieben und daneben eine handgepflegte Liste
# der spaeter dazugekommenen Spalten. Auf einer alten Installation
# fehlte dann ``updated_at`` -- es stand im CREATE, aber nicht in der
# Nachtrags-Liste, und jedes Sichern scheiterte mit "no such column".
# Der Test hat es gefunden, nicht der Blick auf den Code.
#
# So kann das nicht mehr passieren: dieselbe Liste baut die Tabelle
# UND traegt Fehlendes nach.
SETTINGS_COLUMNS = (
    ("enabled", "INTEGER DEFAULT 0"),
    # Der Kanal, in den alles geht, was keinen eigenen hat.
    ("channel_id", "INTEGER"),
    ("uprank_channel_id", "INTEGER"),
    ("downrank_channel_id", "INTEGER"),
    ("kick_channel_id", "INTEGER"),
    ("warn_channel_id", "INTEGER"),
    ("join_channel_id", "INTEGER"),
    # Ob der Befehl ueberall benutzt werden darf. Aus heisst: nur im
    # Befehlskanal.
    ("free_channel", "INTEGER DEFAULT 1"),
    ("command_channel_id", "INTEGER"),
    ("staff_roles", "TEXT DEFAULT ''"),
    ("require_reason", "INTEGER DEFAULT 1"),
    ("dm_user", "INTEGER DEFAULT 1"),
    ("ping_user", "INTEGER DEFAULT 0"),
    ("warn_threshold", "INTEGER DEFAULT 0"),
    ("warn_action", "TEXT DEFAULT 'none'"),
    ("warn_downrank_role_id", "INTEGER"),
    ("warn_expire_days", "INTEGER DEFAULT 0"),
    ("team_roles", "TEXT DEFAULT ''"),
    ("app_enabled", "INTEGER DEFAULT 0"),
    ("updated_at", "INTEGER DEFAULT 0"),
)


async def ensure_schema(db) -> None:
    """Tabellen anlegen und fehlende Spalten nachtragen.

    Beides ist noetig: ``CREATE TABLE IF NOT EXISTS`` aendert an einer
    bereits vorhandenen Tabelle nichts. Eine spaeter dazugekommene
    Spalte fehlt dort also -- und jede Abfrage darauf scheitert mit
    "no such column", womit der ganze Reiter tot ist.
    """

    spalten = ", ".join(f"{name} {typ}" for name, typ in SETTINGS_COLUMNS)
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS team_settings ("
        f" guild_id INTEGER PRIMARY KEY, {spalten})"
    )

    # Vorlagen: je Aktion eine Zeile. Eigene Tabelle statt fuenfzehn
    # Spalten in den Einstellungen -- eine sechste Aktion braucht so
    # keine Schemaaenderung.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS team_templates ("
        " guild_id INTEGER NOT NULL,"
        " action TEXT NOT NULL,"
        " title TEXT DEFAULT '',"
        " body TEXT DEFAULT '',"
        " dm_body TEXT DEFAULT '',"
        " colour INTEGER DEFAULT 0,"
        " enabled INTEGER DEFAULT 1,"
        " PRIMARY KEY (guild_id, action))"
    )

    # Die Team-Akte: wer ist drin, seit wann, mit welcher Rolle.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS team_members ("
        " guild_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " role_id INTEGER,"
        " joined_at INTEGER DEFAULT 0,"
        " left_at INTEGER DEFAULT 0,"
        " active INTEGER DEFAULT 1,"
        # Woher die Aufnahme kam: 'command', 'application' oder
        # 'auto'. Das beantwortet spaeter die Frage "wer hat den
        # eigentlich reingeholt".
        " source TEXT DEFAULT 'command',"
        " PRIMARY KEY (guild_id, user_id))"
    )

    # Jede Aktion, chronologisch. Auch die, die nichts veraendert
    # haben -- ein Rauswurf, bei dem keine Rolle entfernt werden
    # konnte, ist genau der Fall, den man spaeter nachlesen will.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS team_events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " action TEXT NOT NULL,"
        " old_role_id INTEGER,"
        " new_role_id INTEGER,"
        " reason TEXT DEFAULT '',"
        " signers TEXT DEFAULT '[]',"
        " actor_id INTEGER,"
        " source TEXT DEFAULT 'command',"
        " created_at INTEGER NOT NULL)"
    )

    # Verwarnungen getrennt von den Ereignissen: sie werden gezaehlt,
    # koennen verfallen und einzeln aufgehoben werden. Als Filter ueber
    # die Ereignistabelle waere jede dieser drei Sachen eine Sonderregel.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS team_warns ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " reason TEXT DEFAULT '',"
        " actor_id INTEGER,"
        " signers TEXT DEFAULT '[]',"
        " active INTEGER DEFAULT 1,"
        " created_at INTEGER NOT NULL)"
    )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_events_lookup"
        " ON team_events (guild_id, created_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_warns_lookup"
        " ON team_warns (guild_id, user_id, active)"
    )

    # Spalten, die spaeter dazugekommen sind. Siehe Docstring oben:
    # ohne ALTER fehlen sie auf jeder Installation, die vorher lief.
    await _ensure_columns(db)
    await db.commit()


# (Tabelle, Spalte, Typ) -- abgeleitet, nicht getippt.
#
# Jede Spalte von ``team_settings`` steht hier drin, nicht nur die
# zuletzt dazugekommenen. Das kostet ein PRAGMA pro Spalte beim Start
# und macht dafuer den Fall unmoeglich, dass jemand eine Spalte
# hinzufuegt und den Nachtrag vergisst -- genau das war schon einmal
# der Fall und liess jedes Sichern auf einer alten Installation
# scheitern.
#
# ``api/schema_guard.py`` fuehrt dieselben Nachtraege noch einmal
# aus, damit sie auch dann passieren, wenn die API frueher startet
# als der Cog.
LATE_COLUMNS = tuple(
    ("team_settings", name, typ) for name, typ in SETTINGS_COLUMNS
)


async def _ensure_columns(db) -> None:
    for tabelle, spalte, typ in LATE_COLUMNS:
        async with db.execute(f"PRAGMA table_info({tabelle})") as cursor:
            vorhanden = {r[1] for r in await cursor.fetchall()}
        # Leer heisst: die Tabelle gibt es noch gar nicht. Dann legt
        # CREATE TABLE sie gleich vollstaendig an.
        if not vorhanden or spalte in vorhanden:
            continue
        await db.execute(
            f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}"
        )


# ── Einstellungen ────────────────────────────────────────────────────

DEFAULTS = {
    "enabled": False,
    "channel_id": "",
    "uprank_channel_id": "",
    "downrank_channel_id": "",
    "kick_channel_id": "",
    "warn_channel_id": "",
    "join_channel_id": "",
    # Voreinstellung "ueberall erlaubt": ein Befehl, der beim ersten
    # Versuch mit "falscher Kanal" antwortet, wirkt kaputt.
    "free_channel": True,
    "command_channel_id": "",
    "staff_roles": [],
    "require_reason": True,
    "dm_user": True,
    "ping_user": False,
    "warn_threshold": 0,
    "warn_action": FOLLOWUP_NONE,
    "warn_downrank_role_id": "",
    "warn_expire_days": 0,
    "team_roles": [],
    "app_enabled": False,
    "updated_at": 0,
}


def _ids(text) -> list[str]:
    return [x for x in str(text or "").split(",") if x.strip().isdigit()]


def _row_to_settings(row) -> dict:
    def sid(value) -> str:
        # IDs immer als Text. 17-20 Ziffern liegen ueber
        # Number.MAX_SAFE_INTEGER -- als Zahl ausgeliefert rundet
        # JavaScript sie still, und die letzte Stelle stimmt nicht mehr.
        return str(value) if value else ""

    return {
        "enabled": bool(row["enabled"]),
        "channel_id": sid(row["channel_id"]),
        "uprank_channel_id": sid(row["uprank_channel_id"]),
        "downrank_channel_id": sid(row["downrank_channel_id"]),
        "kick_channel_id": sid(row["kick_channel_id"]),
        "warn_channel_id": sid(row["warn_channel_id"]),
        "join_channel_id": sid(row["join_channel_id"]),
        "free_channel": bool(row["free_channel"]),
        "command_channel_id": sid(row["command_channel_id"]),
        "staff_roles": _ids(row["staff_roles"]),
        "require_reason": bool(row["require_reason"]),
        "dm_user": bool(row["dm_user"]),
        "ping_user": bool(row["ping_user"]),
        "warn_threshold": int(row["warn_threshold"] or 0),
        "warn_action": row["warn_action"] or FOLLOWUP_NONE,
        "warn_downrank_role_id": sid(row["warn_downrank_role_id"]),
        "warn_expire_days": int(row["warn_expire_days"] or 0),
        "team_roles": _ids(row["team_roles"]),
        "app_enabled": bool(row["app_enabled"]),
        "updated_at": int(row["updated_at"] or 0),
    }


async def get_settings(guild_id: int) -> dict:
    """Die Einstellungen. Nie ``None`` -- ein Server ohne Eintrag
    bekommt die Voreinstellungen, damit das Dashboard keinen
    Sonderfall braucht."""

    import aiosqlite

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM team_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_settings(row) if row else dict(DEFAULTS)


# Feld -> (Spalte, Art). Die Art entscheidet, wie der Wert gesaeubert
# wird, bevor er in die Datenbank geht.
SETTING_FIELDS = {
    "enabled": ("enabled", "bool"),
    "channel_id": ("channel_id", "id"),
    "uprank_channel_id": ("uprank_channel_id", "id"),
    "downrank_channel_id": ("downrank_channel_id", "id"),
    "kick_channel_id": ("kick_channel_id", "id"),
    "warn_channel_id": ("warn_channel_id", "id"),
    "join_channel_id": ("join_channel_id", "id"),
    "free_channel": ("free_channel", "bool"),
    "command_channel_id": ("command_channel_id", "id"),
    "staff_roles": ("staff_roles", "idlist"),
    "require_reason": ("require_reason", "bool"),
    "dm_user": ("dm_user", "bool"),
    "ping_user": ("ping_user", "bool"),
    "warn_threshold": ("warn_threshold", "count"),
    "warn_action": ("warn_action", "followup"),
    "warn_downrank_role_id": ("warn_downrank_role_id", "id"),
    "warn_expire_days": ("warn_expire_days", "days"),
    "team_roles": ("team_roles", "idlist"),
    "app_enabled": ("app_enabled", "bool"),
}


def _clean(art: str, wert):
    if art == "bool":
        return int(bool(wert))
    if art == "id":
        text = str(wert or "").strip()
        return int(text) if text.isdigit() else None
    if art == "idlist":
        gefiltert: list[str] = []
        for eintrag in (wert or []):
            text = str(eintrag).strip()
            if text.isdigit() and text not in gefiltert:
                gefiltert.append(text)
            if len(gefiltert) >= MAX_STAFF_ROLES:
                break
        return ",".join(gefiltert)
    if art == "count":
        try:
            # Null heisst "Automatik aus" -- deshalb ist die untere
            # Grenze null und nicht eins.
            return max(0, min(50, int(wert)))
        except (TypeError, ValueError):
            return 0
    if art == "days":
        try:
            return max(0, min(3650, int(wert)))
        except (TypeError, ValueError):
            return 0
    if art == "followup":
        text = str(wert or "").strip()
        return text if text in FOLLOWUPS else FOLLOWUP_NONE
    return wert


async def save_settings(guild_id: int, data: dict) -> dict:
    zuweisungen, werte = [], []
    for feld, (spalte, art) in SETTING_FIELDS.items():
        if feld not in data:
            continue
        zuweisungen.append(f"{spalte} = ?")
        werte.append(_clean(art, data[feld]))

    if not zuweisungen:
        return await get_settings(guild_id)

    zuweisungen.append("updated_at = ?")
    werte.append(int(time.time()))

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        # Die Zeile muss es geben, bevor UPDATE etwas ausrichtet.
        await db.execute(
            "INSERT OR IGNORE INTO team_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
        await db.execute(
            f"UPDATE team_settings SET {', '.join(zuweisungen)}"
            " WHERE guild_id = ?",
            werte + [guild_id],
        )
        await db.commit()

    return await get_settings(guild_id)


# ── Vorlagen ─────────────────────────────────────────────────────────


async def get_templates(guild_id: int) -> dict[str, dict]:
    """Alle fuenf Vorlagen, fehlende mit der Voreinstellung gefuellt."""

    import aiosqlite

    gespeichert: dict[str, dict] = {}
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM team_templates WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            for row in await cursor.fetchall():
                gespeichert[row["action"]] = {
                    "title": row["title"] or "",
                    "body": row["body"] or "",
                    "dm_body": row["dm_body"] or "",
                    "colour": int(row["colour"] or 0),
                    "enabled": bool(row["enabled"]),
                }

    out: dict[str, dict] = {}
    for aktion in ACTIONS:
        eintrag = gespeichert.get(aktion, {})
        out[aktion] = {
            "action": aktion,
            "label": ACTION_LABELS[aktion],
            "title": eintrag.get("title") or DEFAULT_TITLES[aktion],
            "body": eintrag.get("body") or DEFAULT_TEMPLATES[aktion],
            "dm_body": eintrag.get("dm_body") or DEFAULT_DM[aktion],
            "colour": eintrag.get("colour") or DEFAULT_COLOURS[aktion],
            # Fehlt der Eintrag, ist die Aktion an: ein Server, der nie
            # eine Vorlage angefasst hat, soll trotzdem ankuendigen.
            "enabled": eintrag.get("enabled", True),
        }
    return out


async def save_template(guild_id: int, action: str, data: dict) -> None:
    if action not in ACTIONS:
        raise ValueError(f"Unbekannte Aktion: {action}")

    vorher = (await get_templates(guild_id))[action]

    titel = str(data.get("title", vorher["title"]))[:200]
    text = str(data.get("body", vorher["body"]))[:MAX_TEMPLATE]
    dm = str(data.get("dm_body", vorher["dm_body"]))[:MAX_TEMPLATE]
    try:
        farbe = max(0, min(0xFFFFFF, int(data.get("colour", vorher["colour"]))))
    except (TypeError, ValueError):
        farbe = vorher["colour"]
    an = int(bool(data.get("enabled", vorher["enabled"])))

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO team_templates"
            " (guild_id, action, title, body, dm_body, colour, enabled)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, action) DO UPDATE SET"
            " title = excluded.title, body = excluded.body,"
            " dm_body = excluded.dm_body, colour = excluded.colour,"
            " enabled = excluded.enabled",
            (guild_id, action, titel, text, dm, farbe, an),
        )
        await db.commit()


# ── Kanalwahl ────────────────────────────────────────────────────────


def channel_for(settings: dict, action: str) -> str:
    """
    In welchen Kanal die Ankuendigung geht.

    Erst der eigene Kanal der Aktion, sonst der allgemeine. Ein leerer
    Rueckgabewert heisst: nirgendwohin -- dann wird nicht angekuendigt,
    die Rollen werden aber trotzdem gesetzt. Eine Befoerderung darf
    nicht daran scheitern, dass niemand einen Kanal ausgesucht hat.
    """
    eigener = str(settings.get(f"{action}_channel_id") or "").strip()
    if eigener.isdigit():
        return eigener
    allgemein = str(settings.get("channel_id") or "").strip()
    return allgemein if allgemein.isdigit() else ""


def may_run_here(settings: dict, channel_id: int | str) -> bool:
    """
    Darf der Befehl in diesem Kanal benutzt werden?

    ``free_channel`` an heisst ueberall. Aus heisst: nur im
    Befehlskanal -- und wenn keiner eingestellt ist, wieder ueberall.
    Sonst waere der Befehl nach dem Ausschalten des Schalters
    nirgendwo mehr benutzbar, ohne dass irgendwo steht, warum.
    """
    if settings.get("free_channel", True):
        return True
    erlaubt = str(settings.get("command_channel_id") or "").strip()
    if not erlaubt.isdigit():
        return True
    return str(channel_id) == erlaubt


def may_use(settings: dict, member) -> bool:
    """
    Darf diese Person die Team-Befehle benutzen?

    Wer den Server verwalten darf, immer. Sonst nur die eingestellten
    Rollen. Ohne eingestellte Rollen bleibt es bei den Serverrechten --
    eine leere Liste darf nicht heissen "niemand", sonst ist das
    System nach dem Einschalten unbenutzbar.
    """
    if member is None:
        return False
    rechte = getattr(member, "guild_permissions", None)
    if rechte is not None and getattr(rechte, "manage_guild", False):
        return True

    erlaubt = {int(r) for r in settings.get("staff_roles") or []}
    if not erlaubt:
        return False
    return any(
        int(getattr(rolle, "id", 0)) in erlaubt
        for rolle in getattr(member, "roles", []) or []
    )


# ── Team-Akte ────────────────────────────────────────────────────────


async def set_member(
    guild_id: int,
    user_id: int,
    role_id: int | None,
    *,
    source: str = "command",
) -> None:
    """Jemanden ins Team eintragen oder seine Rolle fortschreiben."""

    jetzt = int(time.time())
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO team_members"
            " (guild_id, user_id, role_id, joined_at, left_at, active, source)"
            " VALUES (?, ?, ?, ?, 0, 1, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET"
            " role_id = excluded.role_id, active = 1, left_at = 0,"
            # joined_at bleibt stehen: wer zurueckkommt, war schon mal
            # da, und das Beitrittsdatum ist die interessantere Zahl.
            " joined_at = CASE WHEN team_members.joined_at > 0"
            "   THEN team_members.joined_at ELSE excluded.joined_at END",
            (guild_id, user_id, role_id, jetzt, source),
        )
        await db.commit()


async def remove_member(guild_id: int, user_id: int) -> None:
    """Aus dem Team nehmen -- die Zeile bleibt, damit die Akte bleibt."""

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        await db.execute(
            "UPDATE team_members SET active = 0, left_at = ?, role_id = NULL"
            " WHERE guild_id = ? AND user_id = ?",
            (int(time.time()), guild_id, user_id),
        )
        await db.commit()


async def get_member(guild_id: int, user_id: int) -> dict | None:
    import aiosqlite

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM team_members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "user_id": str(row["user_id"]),
        "role_id": str(row["role_id"]) if row["role_id"] else "",
        "joined_at": int(row["joined_at"] or 0),
        "left_at": int(row["left_at"] or 0),
        "active": bool(row["active"]),
        "source": row["source"] or "command",
    }


async def list_members(guild_id: int, *, active_only: bool = True) -> list[dict]:
    import aiosqlite

    sql = "SELECT * FROM team_members WHERE guild_id = ?"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY joined_at"

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, (guild_id,)) as cursor:
            zeilen = await cursor.fetchall()

    return [
        {
            "user_id": str(r["user_id"]),
            "role_id": str(r["role_id"]) if r["role_id"] else "",
            "joined_at": int(r["joined_at"] or 0),
            "left_at": int(r["left_at"] or 0),
            "active": bool(r["active"]),
            "source": r["source"] or "command",
        }
        for r in zeilen
    ]


# ── Ereignisse ───────────────────────────────────────────────────────


async def add_event(
    guild_id: int,
    user_id: int,
    action: str,
    *,
    old_role_id: int | None = None,
    new_role_id: int | None = None,
    reason: str = "",
    signers: list[int] | None = None,
    actor_id: int | None = None,
    source: str = "command",
) -> int:
    if action not in ACTIONS:
        raise ValueError(f"Unbekannte Aktion: {action}")

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "INSERT INTO team_events"
            " (guild_id, user_id, action, old_role_id, new_role_id, reason,"
            "  signers, actor_id, source, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild_id, user_id, action, old_role_id, new_role_id,
                str(reason or "")[:MAX_REASON],
                json.dumps([str(s) for s in (signers or [])]),
                actor_id, source, int(time.time()),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def list_events(
    guild_id: int,
    *,
    user_id: int | None = None,
    action: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    import aiosqlite

    sql = "SELECT * FROM team_events WHERE guild_id = ?"
    werte: list = [guild_id]
    if user_id:
        sql += " AND user_id = ?"
        werte.append(int(user_id))
    if action in ACTIONS:
        sql += " AND action = ?"
        werte.append(action)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    werte += [max(1, min(MAX_HISTORY, int(limit))), max(0, int(offset))]

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, werte) as cursor:
            zeilen = await cursor.fetchall()

    out = []
    for r in zeilen:
        try:
            unterschriften = json.loads(r["signers"] or "[]")
        except (ValueError, TypeError):
            unterschriften = []
        out.append({
            "id": int(r["id"]),
            "user_id": str(r["user_id"]),
            "action": r["action"],
            "label": ACTION_LABELS.get(r["action"], r["action"]),
            "old_role_id": str(r["old_role_id"]) if r["old_role_id"] else "",
            "new_role_id": str(r["new_role_id"]) if r["new_role_id"] else "",
            "reason": r["reason"] or "",
            "signers": [str(s) for s in unterschriften],
            "actor_id": str(r["actor_id"]) if r["actor_id"] else "",
            "source": r["source"] or "command",
            "created_at": int(r["created_at"] or 0),
        })
    return out


async def count_events(guild_id: int) -> dict[str, int]:
    """Wie oft jede Aktion vorkam -- fuer die Zahlen im Dashboard."""

    zaehler = {aktion: 0 for aktion in ACTIONS}
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT action, COUNT(*) FROM team_events"
            " WHERE guild_id = ? GROUP BY action",
            (guild_id,),
        ) as cursor:
            for aktion, anzahl in await cursor.fetchall():
                if aktion in zaehler:
                    zaehler[aktion] = int(anzahl or 0)
    return zaehler


# ── Verwarnungen ─────────────────────────────────────────────────────


async def add_warn(
    guild_id: int,
    user_id: int,
    reason: str,
    *,
    actor_id: int | None = None,
    signers: list[int] | None = None,
) -> int:
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "INSERT INTO team_warns"
            " (guild_id, user_id, reason, actor_id, signers, active, created_at)"
            " VALUES (?, ?, ?, ?, ?, 1, ?)",
            (
                guild_id, user_id, str(reason or "")[:MAX_REASON], actor_id,
                json.dumps([str(s) for s in (signers or [])]),
                int(time.time()),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def count_warns(guild_id: int, user_id: int, *, expire_days: int = 0) -> int:
    """
    Wie viele Verwarnungen noch gelten.

    ``expire_days`` gross null blendet aeltere aus. Sie werden nicht
    geloescht: die Akte soll vollstaendig bleiben, nur die Zaehlung
    fuer die Automatik laesst sie weg.
    """

    sql = ("SELECT COUNT(*) FROM team_warns"
           " WHERE guild_id = ? AND user_id = ? AND active = 1")
    werte: list = [guild_id, int(user_id)]
    if expire_days and int(expire_days) > 0:
        sql += " AND created_at >= ?"
        werte.append(int(time.time()) - int(expire_days) * 86400)

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        async with db.execute(sql, werte) as cursor:
            row = await cursor.fetchone()
    return int((row or [0])[0] or 0)


async def list_warns(guild_id: int, user_id: int) -> list[dict]:
    import aiosqlite

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM team_warns WHERE guild_id = ? AND user_id = ?"
            " ORDER BY created_at DESC",
            (guild_id, int(user_id)),
        ) as cursor:
            zeilen = await cursor.fetchall()

    out = []
    for r in zeilen:
        try:
            unterschriften = json.loads(r["signers"] or "[]")
        except (ValueError, TypeError):
            unterschriften = []
        out.append({
            "id": int(r["id"]),
            "user_id": str(r["user_id"]),
            "reason": r["reason"] or "",
            "actor_id": str(r["actor_id"]) if r["actor_id"] else "",
            "signers": [str(s) for s in unterschriften],
            "active": bool(r["active"]),
            "created_at": int(r["created_at"] or 0),
        })
    return out


async def clear_warn(guild_id: int, warn_id: int) -> bool:
    """Eine einzelne Verwarnung aufheben. Sie bleibt in der Akte."""

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE team_warns SET active = 0"
            " WHERE guild_id = ? AND id = ? AND active = 1",
            (guild_id, int(warn_id)),
        )
        await db.commit()
        return bool(cursor.rowcount)


async def clear_all_warns(guild_id: int, user_id: int) -> int:
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE team_warns SET active = 0"
            " WHERE guild_id = ? AND user_id = ? AND active = 1",
            (guild_id, int(user_id)),
        )
        await db.commit()
        return int(cursor.rowcount or 0)


def followup_due(settings: dict, warn_count: int) -> str:
    """
    Welche Folge nach dieser Verwarnung faellig ist.

    Gibt ``"none"`` zurueck, solange die Automatik aus ist, die
    Schwelle nicht erreicht wurde oder keine Folge eingestellt ist.
    Die Bedingung steht hier und nicht im Cog, damit das Dashboard
    dieselbe Antwort anzeigen kann, die der Bot spaeter zieht.
    """
    schwelle = int(settings.get("warn_threshold") or 0)
    folge = settings.get("warn_action") or FOLLOWUP_NONE
    if schwelle <= 0 or folge not in (FOLLOWUP_DOWNRANK, FOLLOWUP_KICK):
        return FOLLOWUP_NONE
    return folge if int(warn_count) >= schwelle else FOLLOWUP_NONE


# ── Text ─────────────────────────────────────────────────────────────


def render(vorlage: str, werte: dict) -> str:
    """
    Platzhalter ersetzen.

    Absichtlich kein ``str.format``: eine geschweifte Klammer im Text
    des Nutzers -- etwa in einem Grund -- liesse das mit einem
    KeyError auffliegen, und die Ankuendigung fiele ganz aus. Ein
    unbekannter Platzhalter bleibt hier einfach stehen.
    """
    text = str(vorlage or "")
    for schluessel in PLACEHOLDERS:
        name = schluessel.strip("{}")
        text = text.replace(schluessel, str(werte.get(name, "")))
    return text


def signature_line(signer_ids: list[int]) -> str:
    """Die Unterschriften als Erwaehnungen, in der gegebenen Reihenfolge."""
    return ", ".join(f"<@{int(s)}>" for s in signer_ids if str(s).isdigit())
