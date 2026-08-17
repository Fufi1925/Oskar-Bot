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

# ── Das Ping-System ──────────────────────────────────────────────────
#
# Vorher gab es genau eine Regel: "wenn ein Kanal eingestellt ist,
# schicke bei JEDEM Beitritt eine Nachricht". Das hatte drei Loecher,
# und alle drei treffen denselben Nerv -- entweder pingt es zu oft
# oder gar nicht:
#
#   * **Kein Cooldown.** Wer zweimal hintereinander verbindet (oder
#     dessen Verbindung kurz abreisst), loest zwei Pings aus. Bei
#     einem instabilen Netz wird das Team im Sekundentakt erwaehnt --
#     und schaltet die Erwaehnung ab.
#   * **Keine Erinnerung.** Sieht niemand die erste Meldung, wartet
#     die Person, bis sie aufgibt. Es gibt keinen zweiten Anlauf.
#   * **Alles oder nichts.** Entweder wird die Rolle bei jedem
#     Beitritt erwaehnt oder nie.
#
# Die Zeiten stehen als Grenzen hier und nicht nur im Browser: die
# Route ist per HTTP erreichbar, und curl fuellt kein Formular aus.

#: Wie lange nach einem Ping nicht erneut gepingt wird (Sekunden).
#: Verhindert die Ping-Lawine bei wackligem Netz.
DEFAULT_PING_COOLDOWN = 120
MIN_PING_COOLDOWN = 0
MAX_PING_COOLDOWN = 3600

#: Nach wie vielen Sekunden ohne Reaktion erinnert wird. 0 = nie.
#: "Reaktion" heisst: ein Teammitglied betritt den Warteraum.
DEFAULT_REMINDER_SECONDS = 300
MIN_REMINDER_SECONDS = 0
MAX_REMINDER_SECONDS = 3600

#: Wie oft hoechstens erinnert wird, bevor Ruhe ist. Ohne Obergrenze
#: pingt der Bot bis in alle Ewigkeit weiter, wenn niemand kommt --
#: und genau dann ist die Erwaehnung am wenigsten willkommen.
DEFAULT_MAX_REMINDERS = 3
MAX_MAX_REMINDERS = 10


#: Die Spalten des Ping-Systems, an EINER Stelle.
#:
#: Zwei handgepflegte Listen laufen auseinander -- bei `team_update`
#: ist genau das passiert: eine Spalte fehlte im Nachtrag, und auf
#: einer laufenden Installation kam "no such column".
PING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ping_enabled", "INTEGER DEFAULT 1"),
    ("ping_cooldown", f"INTEGER DEFAULT {DEFAULT_PING_COOLDOWN}"),
    ("reminder_seconds", f"INTEGER DEFAULT {DEFAULT_REMINDER_SECONDS}"),
    ("max_reminders", f"INTEGER DEFAULT {DEFAULT_MAX_REMINDERS}"),
    ("ping_when_staff_present", "INTEGER DEFAULT 0"),
)


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

    # Die Ping-Spalten nachruesten.
    #
    # `CREATE TABLE IF NOT EXISTS` aendert an einer bestehenden
    # Tabelle NICHTS. Auf jedem Server, der den Warteraum schon
    # benutzt, fehlten die neuen Spalten sonst -- und jede Abfrage
    # scheiterte mit "no such column". Die Liste steht an EINER
    # Stelle, damit sie nicht von der Tabellendefinition abweicht.
    for name, typ in PING_COLUMNS:
        try:
            await db.execute(f"ALTER TABLE support_queue ADD COLUMN {name} {typ}")
        except Exception:  # noqa: BLE001 - Spalte existiert bereits
            pass

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
            "ping_enabled": True,
            "ping_cooldown": DEFAULT_PING_COOLDOWN,
            "reminder_seconds": DEFAULT_REMINDER_SECONDS,
            "max_reminders": DEFAULT_MAX_REMINDERS,
            "ping_when_staff_present": False,
        }

    data = dict(row)
    data["enabled"] = bool(data.get("enabled"))

    # Nachgeruestete Spalten koennen NULL sein -- bei jedem Server,
    # der vor dem Update schon einen Eintrag hatte. `int(None)` wirft,
    # und ein Fehler beim Lesen der Einstellungen legt den ganzen
    # Warteraum still. Deshalb hier die Vorgaben einsetzen.
    data["ping_enabled"] = (
        True if data.get("ping_enabled") is None
        else bool(data.get("ping_enabled"))
    )
    data["ping_when_staff_present"] = bool(data.get("ping_when_staff_present"))
    for feld, vorgabe in (
        ("ping_cooldown", DEFAULT_PING_COOLDOWN),
        ("reminder_seconds", DEFAULT_REMINDER_SECONDS),
        ("max_reminders", DEFAULT_MAX_REMINDERS),
    ):
        try:
            data[feld] = int(data.get(feld))
        except (TypeError, ValueError):
            data[feld] = vorgabe
    return data


async def save(db: aiosqlite.Connection, guild_id: int, **fields) -> dict:
    """Einstellungen schreiben. Nur was mitkommt, wird geaendert."""

    current = await get(db, guild_id)

    allowed = {
        "channel_id", "enabled", "greeting", "music_url",
        "music_seconds", "notify_channel_id", "staff_role_id",
        "ping_enabled", "ping_cooldown", "reminder_seconds",
        "max_reminders", "ping_when_staff_present",
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

    # Die Ping-Werte, jeder in seinen Grenzen. Auch hier gilt: die
    # Route ist per HTTP erreichbar, ein Browser-Formular ist keine
    # Absicherung.
    merged["ping_enabled"] = 1 if merged.get("ping_enabled") else 0
    merged["ping_when_staff_present"] = (
        1 if merged.get("ping_when_staff_present") else 0
    )
    for feld, vorgabe, unten, oben in (
        ("ping_cooldown", DEFAULT_PING_COOLDOWN,
         MIN_PING_COOLDOWN, MAX_PING_COOLDOWN),
        ("reminder_seconds", DEFAULT_REMINDER_SECONDS,
         MIN_REMINDER_SECONDS, MAX_REMINDER_SECONDS),
        ("max_reminders", DEFAULT_MAX_REMINDERS, 0, MAX_MAX_REMINDERS),
    ):
        try:
            wert = int(merged.get(feld))
        except (TypeError, ValueError):
            wert = vorgabe
        merged[feld] = max(unten, min(wert, oben))

    await db.execute(
        """
        INSERT INTO support_queue
            (guild_id, channel_id, enabled, greeting, music_url,
             music_seconds, notify_channel_id, staff_role_id, updated_at,
             ping_enabled, ping_cooldown, reminder_seconds, max_reminders,
             ping_when_staff_present)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            enabled = excluded.enabled,
            greeting = excluded.greeting,
            music_url = excluded.music_url,
            music_seconds = excluded.music_seconds,
            notify_channel_id = excluded.notify_channel_id,
            staff_role_id = excluded.staff_role_id,
            updated_at = excluded.updated_at,
            ping_enabled = excluded.ping_enabled,
            ping_cooldown = excluded.ping_cooldown,
            reminder_seconds = excluded.reminder_seconds,
            max_reminders = excluded.max_reminders,
            ping_when_staff_present = excluded.ping_when_staff_present
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
            merged["ping_enabled"],
            merged["ping_cooldown"],
            merged["reminder_seconds"],
            merged["max_reminders"],
            merged["ping_when_staff_present"],
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
    """Alles vergessen -- fuer Tests und beim Abschalten.

    Nimmt den Ping-Zustand mit. Ohne das bliebe ein Cooldown stehen,
    nachdem der Warteraum leer war: der naechste Wartende wuerde
    verschluckt, weil "vor zwei Minuten wurde doch schon gepingt" --
    nur galt das einem anderen Menschen.
    """

    if guild_id is None:
        _waiting.clear()
    else:
        _waiting.pop(int(guild_id), None)
    reset_pings(guild_id)


# --------------------------------------------------------------------- #
#  Das Ping-System
# --------------------------------------------------------------------- #
#
# Wer wann zuletzt erwaehnt wurde -- damit das Team nicht im
# Sekundentakt gepingt wird und trotzdem eine Erinnerung bekommt, wenn
# niemand reagiert.
#
# Wie die Wartenden selbst nur im Arbeitsspeicher: nach einem Neustart
# ist ohnehin niemand mehr in einem Kanal, den der Bot kennt, und ein
# gespeicherter Cooldown wuerde nach dem Deploy die erste echte Meldung
# verschlucken.

# guild_id -> Zeitpunkt des letzten Pings
_last_ping: dict[int, float] = {}
# guild_id -> wie oft schon erinnert wurde
_reminders_sent: dict[int, int] = {}


def may_ping(record: dict, guild_id: int, *, now: float | None = None) -> bool:
    """Darf jetzt gepingt werden?

    Drei Gruende, es nicht zu tun, und alle drei sind einstellbar:

      1. Das Ping-System ist aus.
      2. Es gibt keinen Kanal, in den die Meldung koennte.
      3. Der letzte Ping ist noch keine `ping_cooldown` Sekunden her.

    Der Cooldown ist der wichtigste: ohne ihn loest jede wacklige
    Verbindung einen weiteren Ping aus, und ein Team, das im
    Sekundentakt erwaehnt wird, schaltet die Erwaehnung ab -- womit
    das ganze System nutzlos wird.
    """
    if not record.get("ping_enabled", True):
        return False
    if not record.get("notify_channel_id"):
        return False

    cooldown = int(record.get("ping_cooldown") or 0)
    if cooldown <= 0:
        return True

    jetzt = time.time() if now is None else now
    letzter = _last_ping.get(int(guild_id))
    if letzter is None:
        return True
    return (jetzt - letzter) >= cooldown


def mark_pinged(guild_id: int, *, now: float | None = None) -> None:
    """Merken, dass gerade gepingt wurde."""
    _last_ping[int(guild_id)] = time.time() if now is None else now


def due_for_reminder(
    record: dict, guild_id: int, *, now: float | None = None
) -> bool:
    """Ist eine Erinnerung faellig?

    Faellig heisst: es wartet jemand seit mindestens
    `reminder_seconds`, und die Obergrenze `max_reminders` ist noch
    nicht erreicht.

    Die Obergrenze ist kein Detail. Ohne sie erinnert der Bot bis in
    alle Ewigkeit weiter, wenn niemand kommt -- und genau dann ist die
    Erwaehnung am wenigsten willkommen. Nach drei Versuchen hat es
    entweder jemand gesehen oder es ist gerade niemand da.
    """
    if not record.get("ping_enabled", True):
        return False
    if not record.get("notify_channel_id"):
        return False

    abstand = int(record.get("reminder_seconds") or 0)
    if abstand <= 0:
        return False

    grenze = int(record.get("max_reminders") or 0)
    if grenze > 0 and _reminders_sent.get(int(guild_id), 0) >= grenze:
        return False

    wartende = waiting(guild_id)
    if not wartende:
        return False

    jetzt = time.time() if now is None else now
    # Der Aelteste zaehlt: wer am laengsten wartet, ist der Grund fuer
    # die Erinnerung.
    aeltester = min(wartende.values())
    return (jetzt - aeltester) >= abstand


def mark_reminded(guild_id: int, *, now: float | None = None) -> None:
    """Eine Erinnerung ist raus."""
    gid = int(guild_id)
    _reminders_sent[gid] = _reminders_sent.get(gid, 0) + 1
    _last_ping[gid] = time.time() if now is None else now


def reminders_sent(guild_id: int) -> int:
    """Wie oft schon erinnert wurde."""
    return _reminders_sent.get(int(guild_id), 0)


def reset_pings(guild_id: int | None = None) -> None:
    """Cooldown und Erinnerungszaehler vergessen.

    Wird gerufen, wenn der Warteraum leer ist: der naechste Wartende
    soll sofort gemeldet werden und nicht in einem Cooldown haengen,
    der noch vom Vorgaenger stammt.
    """
    if guild_id is None:
        _last_ping.clear()
        _reminders_sent.clear()
    else:
        gid = int(guild_id)
        _last_ping.pop(gid, None)
        _reminders_sent.pop(gid, None)
