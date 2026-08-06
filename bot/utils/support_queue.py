"""
Support-Warteraum: wer wartet gerade, und was hat der Server eingestellt.

Die Idee dahinter
-----------------
Ein Sprachkanal wird zum Warteraum erklaert. Betritt ihn jemand, kommt
der Bot dazu, begruesst per Sprache und spielt danach Wartemusik. Das
Team sieht im Dashboard, wer wartet und seit wann.

Warum eine eigene Tabelle und nicht `j2c`
-----------------------------------------
Join-to-Create legt bei jedem Beitritt einen *neuen* Kanal an und
verschiebt die Person dorthin. Hier ist es umgekehrt: der Kanal bleibt,
der Bot kommt dazu. Zwei Systeme, die sich am selben Ereignis
(`on_voice_state_update`) aufhaengen, aber Gegenteiliges tun -- deshalb
getrennte Tabellen. Ein gemeinsamer Kanal fuer beides waere ohnehin ein
Widerspruch: J2C wuerde die Person sofort wegschieben.

Speicher
--------
`db/support_queue.db`, wie die uebrigen Feature-Datenbanken. Sie
braucht ein Railway-Volume, sonst sind die Einstellungen nach jedem
Deploy weg -- die Wartenden selbst nicht, die stehen nur im
Arbeitsspeicher (nach einem Neustart ist ohnehin niemand mehr in einem
Kanal, den der Bot noch kennt).
"""

from __future__ import annotations

import time

import aiosqlite

DB_PATH = "db/support_queue.db"

# Grenzen fuer die Ansage. Discords Nachrichtenlaenge spielt keine
# Rolle -- der Text wird gesprochen, und gTTS wird bei sehr langen
# Saetzen langsam und teuer.
MAX_GREETING = 300

# Voreinstellung: genau der Satz, den sich der Nutzer gewuenscht hat,
# in ordentlichem Deutsch.
DEFAULT_GREETING = (
    "Hey, willkommen im Support! Ein Teammitglied ist gleich für dich da. "
    "Wenn dir das System gefällt, lade den Bot doch auch auf deinen "
    "eigenen Server ein."
)

# Wie lange die Wartemusik am Stueck laeuft, bevor die Ansage
# wiederholt wird. In Sekunden.
DEFAULT_MUSIC_SECONDS = 30
MIN_MUSIC_SECONDS = 10
MAX_MUSIC_SECONDS = 600


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS support_queue (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            enabled INTEGER DEFAULT 0,
            greeting TEXT,
            music_url TEXT,
            music_seconds INTEGER DEFAULT 30,
            notify_channel_id INTEGER,
            staff_role_id INTEGER,
            updated_at REAL DEFAULT 0
        )
        """
    )
    await db.commit()


async def get(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Die Einstellungen eines Servers -- immer ein vollstaendiges Dict.

    Nie None: der Aufrufer soll nicht bei jedem Zugriff pruefen
    muessen, ob schon einmal etwas gespeichert wurde. Ein Server ohne
    Eintrag ist schlicht ein Server mit ausgeschaltetem Warteraum.
    """

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM support_queue WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return {
            "guild_id": guild_id,
            "channel_id": None,
            "enabled": False,
            "greeting": "",
            "music_url": "",
            "music_seconds": DEFAULT_MUSIC_SECONDS,
            "notify_channel_id": None,
            "staff_role_id": None,
            "updated_at": 0.0,
        }

    data = dict(row)
    data["enabled"] = bool(data.get("enabled"))
    return data


async def save(db: aiosqlite.Connection, guild_id: int, **fields) -> dict:
    """Einstellungen schreiben. Nur was mitkommt, wird geaendert."""

    current = await get(db, guild_id)

    allowed = {
        "channel_id", "enabled", "greeting", "music_url",
        "music_seconds", "notify_channel_id", "staff_role_id",
    }
    merged = {key: current.get(key) for key in allowed}
    for key, value in fields.items():
        if key in allowed:
            merged[key] = value

    # Grenzen durchsetzen, hier und nicht nur im Browser: die Route ist
    # per HTTP erreichbar, und curl fragt nicht nach einem Formular.
    merged["greeting"] = str(merged.get("greeting") or "")[:MAX_GREETING]
    try:
        seconds = int(merged.get("music_seconds") or DEFAULT_MUSIC_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_MUSIC_SECONDS
    merged["music_seconds"] = max(
        MIN_MUSIC_SECONDS, min(seconds, MAX_MUSIC_SECONDS)
    )
    merged["enabled"] = 1 if merged.get("enabled") else 0

    await db.execute(
        """
        INSERT INTO support_queue
            (guild_id, channel_id, enabled, greeting, music_url,
             music_seconds, notify_channel_id, staff_role_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            enabled = excluded.enabled,
            greeting = excluded.greeting,
            music_url = excluded.music_url,
            music_seconds = excluded.music_seconds,
            notify_channel_id = excluded.notify_channel_id,
            staff_role_id = excluded.staff_role_id,
            updated_at = excluded.updated_at
        """,
        (
            guild_id,
            merged.get("channel_id"),
            merged["enabled"],
            merged["greeting"],
            merged.get("music_url") or "",
            merged["music_seconds"],
            merged.get("notify_channel_id"),
            merged.get("staff_role_id"),
            time.time(),
        ),
    )
    await db.commit()
    return await get(db, guild_id)


def greeting_text(record: dict, *, member_name: str = "", guild_name: str = "") -> str:
    """Der Satz, der gesprochen wird.

    Platzhalter werden ersetzt, damit der Server die Ansage anpassen
    kann, ohne dass jemand Code anfassen muss.
    """

    raw = str(record.get("greeting") or "").strip() or DEFAULT_GREETING
    return (
        raw.replace("{user}", member_name or "")
        .replace("{server}", guild_name or "")
        .strip()
    )


# --------------------------------------------------------------------- #
#  Wer wartet gerade
# --------------------------------------------------------------------- #
#
# Bewusst nur im Arbeitsspeicher. Nach einem Neustart ist die Liste
# leer -- und das ist richtig so: der Bot ist dann aus jedem Kanal
# geflogen, und eine gespeicherte Liste wuerde Leute anzeigen, um die
# sich niemand mehr kuemmert.

# guild_id -> {user_id: seit wann (Zeitstempel)}
_waiting: dict[int, dict[int, float]] = {}


def mark_waiting(guild_id: int, user_id: int) -> None:
    """Jemand hat den Warteraum betreten."""

    _waiting.setdefault(int(guild_id), {}).setdefault(int(user_id), time.time())


def clear_waiting(guild_id: int, user_id: int) -> None:
    """Jemand hat ihn verlassen."""

    entries = _waiting.get(int(guild_id))
    if entries:
        entries.pop(int(user_id), None)
        if not entries:
            _waiting.pop(int(guild_id), None)


def waiting(guild_id: int) -> dict[int, float]:
    """Wer wartet, und seit wann."""

    return dict(_waiting.get(int(guild_id), {}))


def reset(guild_id: int | None = None) -> None:
    """Alles vergessen -- fuer Tests und beim Abschalten."""

    if guild_id is None:
        _waiting.clear()
    else:
        _waiting.pop(int(guild_id), None)
