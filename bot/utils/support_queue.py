"""
Support-Warteraum: wer wartet gerade, und die vier Einstellungen.

Die Idee
--------
Ein Sprachkanal wird zum Warteraum erklaert. Betritt ihn jemand, kommt
der Bot dazu und spielt Wartemusik. Gleichzeitig bekommt das Team eine
Meldung im eingestellten Kanal, mit Erwaehnung der Team-Rolle.

Was hier bewusst NICHT mehr einstellbar ist
-------------------------------------------
Vorher gab es acht Felder: eigene Ansage, eigene Musik-URL, Dauer,
Cooldown, Erinnerungsabstand, Zahl der Erinnerungen, Ping-trotz-Team,
Meldekanal. Auf ausdruecklichen Wunsch bleiben vier:

    an/aus · Warteraum-Kanal · Meldekanal · Team-Rolle

Alles Uebrige steht fest. Der Grund ist nicht Bequemlichkeit: jede
zusaetzliche Einstellung war ein Weg, das System kaputt einzustellen
-- eine Musik-URL, die Lavalink nicht findet; ein Cooldown von einer
Stunde, nach dem sich niemand mehr meldet. Die festen Werte unten
sind erprobt.

Die Nachricht ist nicht bearbeitbar. Sie enthaelt genau das, was das
Team braucht: wer wartet, seit wann, in welchem Kanal.

Speicher
--------
`db/support_queue.db`. Braucht ein Railway-Volume, sonst sind die
Einstellungen nach jedem Deploy weg. Die Wartenden selbst stehen nur
im Arbeitsspeicher -- nach einem Neustart sitzt ohnehin niemand mehr
in einem Kanal, den der Bot noch kennt.
"""

from __future__ import annotations

import time

import aiosqlite

DB_PATH = "db/support_queue.db"


# ── Die festen Werte ─────────────────────────────────────────────────
#
# Frueher waren das alles Felder im Dashboard. Sie stehen hier, damit
# klar ist, was gilt -- und damit ein spaeteres Nachjustieren an einer
# Stelle passiert und nicht auf jedem Server einzeln.

#: Wie lange ein Stueck Wartemusik am Stueck laeuft, bevor die
#: Schleife neu ansetzt. Bei der Platzhalter-Datei ist das genau ihre
#: Laenge, also spielt sie einmal durch.
MUSIC_SECONDS = 30

#: Wie lange nach einer Meldung nicht erneut gemeldet wird.
#:
#: Ohne diese Sperre loeste jedes Wackeln der Verbindung eine neue
#: Erwaehnung aus -- bei instabilem Netz im Sekundentakt. Zwei Minuten
#: sind lang genug gegen die Lawine und kurz genug, dass ein echter
#: zweiter Wartender nicht untergeht.
PING_COOLDOWN = 120

#: Nach wie vielen Sekunden ohne Reaktion erinnert wird.
REMINDER_SECONDS = 300

#: Wie oft hoechstens erinnert wird. Danach ist Ruhe -- ein Bot, der
#: endlos weiterpingt, wird abgeschaltet.
MAX_REMINDERS = 3

#: Wird auch gemeldet, wenn schon jemand vom Team im Warteraum sitzt?
#: Nein: dann ist ja bereits jemand da.
PING_WHEN_STAFF_PRESENT = False


#: Die Spalten, an EINER Stelle.
#:
#: `CREATE TABLE IF NOT EXISTS` aendert an einer bestehenden Tabelle
#: nichts. Wer die Tabelle schon hat, bekaeme bei einer neuen Spalte
#: sonst „no such column".
#:
#: Die alten Spalten (greeting, music_url, music_seconds,
#: ping_cooldown, ...) werden absichtlich NICHT geloescht: auf einer
#: laufenden Installation stehen dort Werte, und ein DROP COLUMN
#: waere nicht rueckgaengig zu machen. Sie werden nur nicht mehr
#: gelesen.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("channel_id", "INTEGER"),
    ("enabled", "INTEGER DEFAULT 0"),
    ("notify_channel_id", "INTEGER"),
    ("staff_role_id", "INTEGER"),
    ("updated_at", "REAL DEFAULT 0"),
)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS support_queue (
            guild_id INTEGER PRIMARY KEY
        )
        """
    )
    for name, typ in COLUMNS:
        try:
            await db.execute(f"ALTER TABLE support_queue ADD COLUMN {name} {typ}")
        except Exception:  # noqa: BLE001 - Spalte existiert bereits
            pass
    await db.commit()


async def get(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Die Einstellungen eines Servers -- immer vollstaendig.

    Nie None: ein Server ohne Eintrag ist schlicht ein Server mit
    ausgeschaltetem Warteraum, und der Aufrufer soll das nicht bei
    jedem Zugriff pruefen muessen.
    """
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM support_queue WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        zeile = await cursor.fetchone()

    if zeile is None:
        return {
            "guild_id": guild_id,
            "enabled": False,
            "channel_id": None,
            "notify_channel_id": None,
            "staff_role_id": None,
            "updated_at": 0.0,
        }

    daten = dict(zeile)
    return {
        "guild_id": guild_id,
        "enabled": bool(daten.get("enabled")),
        "channel_id": daten.get("channel_id") or None,
        "notify_channel_id": daten.get("notify_channel_id") or None,
        "staff_role_id": daten.get("staff_role_id") or None,
        "updated_at": float(daten.get("updated_at") or 0),
    }


async def save(db: aiosqlite.Connection, guild_id: int, **felder) -> dict:
    """Einzelne Felder aendern; alles Uebrige bleibt stehen."""
    erlaubt = {name for name, _ in COLUMNS}
    zu_setzen: dict[str, object] = {}

    for schluessel, wert in felder.items():
        if schluessel not in erlaubt:
            continue

        if schluessel == "enabled":
            wert = 1 if wert else 0
        elif schluessel in ("channel_id", "notify_channel_id", "staff_role_id"):
            wert = int(wert) if wert not in (None, "", 0, "0") else None

        zu_setzen[schluessel] = wert

    if not zu_setzen:
        return await get(db, guild_id)

    zu_setzen["updated_at"] = time.time()

    await db.execute(
        "INSERT OR IGNORE INTO support_queue (guild_id) VALUES (?)", (guild_id,)
    )
    zuweisung = ", ".join(f"{name} = ?" for name in zu_setzen)
    await db.execute(
        f"UPDATE support_queue SET {zuweisung} WHERE guild_id = ?",
        (*zu_setzen.values(), guild_id),
    )
    await db.commit()
    return await get(db, guild_id)


# ── Wer wartet gerade ────────────────────────────────────────────────
#
# Nur im Arbeitsspeicher. Nach einem Neustart sitzt niemand mehr in
# einem Kanal, den der Bot noch kennt -- eine Datenbank waere hier
# nicht nur ueberfluessig, sondern falsch.

_waiting: dict[int, dict[int, float]] = {}

#: guild_id -> Zeitpunkt der letzten Meldung.
_last_ping: dict[int, float] = {}

#: guild_id -> Zahl der bereits geschickten Erinnerungen.
_reminders: dict[int, int] = {}


def mark_waiting(guild_id: int, user_id: int) -> None:
    _waiting.setdefault(guild_id, {})[user_id] = time.time()


def clear_waiting(guild_id: int, user_id: int) -> None:
    if guild_id in _waiting:
        _waiting[guild_id].pop(user_id, None)
        if not _waiting[guild_id]:
            _waiting.pop(guild_id, None)


def waiting(guild_id: int) -> dict[int, float]:
    return dict(_waiting.get(guild_id, {}))


def reset(guild_id: int | None = None) -> None:
    """Alles vergessen -- fuer einen Server oder ueberall.

    Nimmt den Ping-Zustand mit: der naechste Wartende soll sofort
    gemeldet werden und nicht in einem Cooldown haengen, der noch dem
    Vorgaenger galt.
    """
    if guild_id is None:
        _waiting.clear()
        _last_ping.clear()
        _reminders.clear()
        return
    _waiting.pop(guild_id, None)
    _last_ping.pop(guild_id, None)
    _reminders.pop(guild_id, None)


# ── Das Ping-System ──────────────────────────────────────────────────

def may_ping(guild_id: int, *, now: float | None = None) -> bool:
    """Darf jetzt gemeldet werden?

    Einzige Bedingung ist der Cooldown. Er verhindert die Lawine bei
    wackliger Verbindung: wer zweimal hintereinander verbindet, loest
    sonst zwei Meldungen aus.
    """
    jetzt = time.time() if now is None else now
    zuletzt = _last_ping.get(guild_id)
    if zuletzt is None:
        return True
    return (jetzt - zuletzt) >= PING_COOLDOWN


def mark_pinged(guild_id: int, *, now: float | None = None) -> None:
    """Festhalten, dass gerade gemeldet wurde.

    Setzt den Erinnerungszaehler zurueck: die Erinnerungen zaehlen ab
    der letzten Meldung, nicht ab dem Serverstart.
    """
    _last_ping[guild_id] = time.time() if now is None else now
    _reminders[guild_id] = 0


def due_for_reminder(guild_id: int, *, now: float | None = None) -> bool:
    """Ist eine Erinnerung faellig?

    Drei Bedingungen, und alle drei muessen stimmen:
      * es gab ueberhaupt eine erste Meldung
      * seit der letzten sind REMINDER_SECONDS vergangen
      * die Obergrenze ist noch nicht erreicht
    """
    jetzt = time.time() if now is None else now

    zuletzt = _last_ping.get(guild_id)
    if zuletzt is None:
        # Ohne erste Meldung gibt es nichts zu erinnern.
        return False

    if _reminders.get(guild_id, 0) >= MAX_REMINDERS:
        return False

    return (jetzt - zuletzt) >= REMINDER_SECONDS


def mark_reminded(guild_id: int, *, now: float | None = None) -> None:
    """Eine Erinnerung ist raus.

    Der Zeitstempel wird mitgesetzt, damit die naechste Erinnerung
    wieder den vollen Abstand hat -- sonst kaemen nach der ersten alle
    weiteren im Takt der Pruefschleife.
    """
    _reminders[guild_id] = _reminders.get(guild_id, 0) + 1
    _last_ping[guild_id] = time.time() if now is None else now


def reminders_sent(guild_id: int) -> int:
    return _reminders.get(guild_id, 0)
