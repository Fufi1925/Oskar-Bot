"""
Benachrichtigungen im Ticket -- wer bekommt wann eine DM.

Zwei Richtungen, und beide haben denselben Bauplan: jemand schreibt,
die Gegenseite antwortet eine Weile nicht, also bekommt sie einen
Hinweis per DM. Der Rest sind Regeln, die verhindern, dass daraus
Spam wird.

**Richtung 1 -- der Nutzer wird benachrichtigt.**
Ein Teammitglied schreibt ins Ticket. Wenn der Nutzer fuenf Minuten
spaeter noch nichts gelesen und geschrieben hat, geht eine DM raus:
"jemand hat geantwortet".

**Richtung 2 -- das Team wird benachrichtigt.**
Ein Teammitglied hat geschrieben, der Nutzer antwortet darauf. Wenn
fuenf Minuten spaeter niemand vom Team zurueckgeschrieben hat, bekommt
das Teammitglied eine DM, das zuletzt im Ticket geschrieben hat.

Die Regeln in der Reihenfolge, in der sie greifen:

  1. **Ist die Funktion ueberhaupt an?** Steht im Dashboard, pro
     Server und pro Richtung getrennt.
  2. **Ist das Ticket noch frisch?** Solange nur der Nutzer (und der
     Bot) geschrieben haben, gibt es keine DM. Sonst bekaeme jemand
     eine Benachrichtigung ueber sein eigenes Ticket, das noch niemand
     gesehen hat.
  3. **Fuenf Minuten warten.** Wer selbst noch tippt, braucht keine
     Erinnerung.
  4. **Hat die Gegenseite inzwischen geschrieben?** Dann ist die
     Benachrichtigung hinfaellig.
  5. **Sperrzeit.** Wer fuer dieses Ticket in der letzten Stunde schon
     eine DM bekommen hat, bekommt keine zweite.
  6. **Schlaeft jemand?** ``>sleep`` legt ein Ticket still -- keine DM
     mehr, in keine Richtung, bis ``>wake`` kommt oder das Ticket
     geschlossen wird.
  7. **Ruhezeit.** Ein optionales Zeitfenster, in dem der Server
     grundsaetzlich niemanden anschreibt.

Alle Zeiten sind im Dashboard einstellbar; die Werte hier sind nur die
Voreinstellung.

Warum das nicht im Ticket-Cog steht: die Regeln muessen an drei
Stellen gelten -- beim Schreiben im Kanal, beim faelligen
Hintergrundlauf und beim Anzeigen im Dashboard. Drei Kopien derselben
Bedingung laufen frueher oder spaeter auseinander. Hier gibt es eine.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from utils import db_paths

NOTIFY_DB = "db/ticket_notify.db"

# ── Voreinstellungen ─────────────────────────────────────────────────
#
# Fuenf Minuten: kurz genug, dass die Antwort noch aktuell ist, lang
# genug, dass niemand eine DM bekommt, waehrend er ohnehin gerade liest.
# Eine Stunde Sperrzeit: ein Ticket kann lebhaft sein, ohne dass daraus
# ein Dutzend DMs werden.
DEFAULT_USER_DELAY = 300        # 5 Minuten
DEFAULT_STAFF_DELAY = 300       # 5 Minuten
DEFAULT_USER_COOLDOWN = 3600    # 1 Stunde
DEFAULT_STAFF_COOLDOWN = 3600   # 1 Stunde

# Warum eine Entscheidung nicht zugestellt wurde. Steht so auch im
# Dashboard, damit "warum kam keine DM" beantwortbar ist.
GRUND_TEXTE = {
    "disabled": "Die Funktion ist im Dashboard aus.",
    "fresh_ticket": "Im Ticket war noch kein Teammitglied -- es wurde gerade erst erstellt.",
    "too_soon": "Die Wartezeit ist noch nicht um.",
    "answered": "Die Gegenseite hat inzwischen selbst geschrieben.",
    "cooldown": "Fuer dieses Ticket ging in der Sperrzeit schon eine DM raus.",
    "sleeping": "Im Ticket wurde >sleep gesetzt.",
    "quiet_hours": "Ruhezeit -- der Server verschickt gerade keine DMs.",
    "no_target": "Es gibt niemanden, den man anschreiben koennte.",
    "closed": "Das Ticket ist nicht mehr offen.",
}


class Decision:
    """
    Das Ergebnis einer Pruefung.

    ``send`` sagt, ob eine DM rausgeht. ``reason`` sagt warum nicht --
    und zwar immer, auch wenn gesendet wird, damit im Protokoll steht,
    welche Regel entschieden hat.
    """

    __slots__ = ("send", "reason", "target_id", "kind")

    def __init__(self, send: bool, reason: str, target_id: int | None = None,
                 kind: str = ""):
        self.send = send
        self.reason = reason
        self.target_id = target_id
        self.kind = kind

    @property
    def text(self) -> str:
        return GRUND_TEXTE.get(self.reason, self.reason)

    def __repr__(self) -> str:
        return f"<Decision send={self.send} reason={self.reason} target={self.target_id}>"


SILENT = Decision(False, "disabled")


# ── Schema ───────────────────────────────────────────────────────────

async def ensure_schema(db) -> None:
    # Einstellungen pro Server.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS notify_settings ("
        " guild_id INTEGER PRIMARY KEY,"
        " user_dm_enabled INTEGER DEFAULT 0,"
        " staff_dm_enabled INTEGER DEFAULT 0,"
        " user_delay INTEGER DEFAULT 300,"
        " staff_delay INTEGER DEFAULT 300,"
        " user_cooldown INTEGER DEFAULT 3600,"
        " staff_cooldown INTEGER DEFAULT 3600,"
        " quiet_enabled INTEGER DEFAULT 0,"
        " quiet_start INTEGER DEFAULT 22,"
        " quiet_end INTEGER DEFAULT 8)"
    )
    # Was in einem Ticket zuletzt passiert ist. Eine Zeile pro Kanal.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS ticket_state ("
        " channel_id INTEGER PRIMARY KEY,"
        " guild_id INTEGER NOT NULL,"
        " creator_id INTEGER NOT NULL,"
        " last_user_msg INTEGER DEFAULT 0,"
        " last_staff_msg INTEGER DEFAULT 0,"
        " last_staff_id INTEGER,"
        " staff_has_written INTEGER DEFAULT 0,"
        " sleeping INTEGER DEFAULT 0,"
        " sleep_by INTEGER,"
        " pending_user INTEGER DEFAULT 0,"
        " pending_staff INTEGER DEFAULT 0)"
    )
    # Wann wem zuletzt geschrieben wurde -- fuer die Sperrzeit.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS notify_log ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " channel_id INTEGER NOT NULL,"
        " guild_id INTEGER NOT NULL,"
        " target_id INTEGER NOT NULL,"
        " kind TEXT NOT NULL,"
        " sent_at INTEGER NOT NULL)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_notify_log_lookup"
        " ON notify_log (channel_id, target_id, kind, sent_at)"
    )
    # Der Hintergrundlauf fragt nach faelligen Eintraegen.
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_state_pending"
        " ON ticket_state (pending_user, pending_staff)"
    )
    await db.commit()


# ── Einstellungen ────────────────────────────────────────────────────

async def get_settings(guild_id: int) -> dict:
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_dm_enabled, staff_dm_enabled, user_delay, staff_delay,"
            " user_cooldown, staff_cooldown, quiet_enabled, quiet_start, quiet_end"
            " FROM notify_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return {
            "user_dm_enabled": False,
            "staff_dm_enabled": False,
            "user_delay": DEFAULT_USER_DELAY,
            "staff_delay": DEFAULT_STAFF_DELAY,
            "user_cooldown": DEFAULT_USER_COOLDOWN,
            "staff_cooldown": DEFAULT_STAFF_COOLDOWN,
            "quiet_enabled": False,
            "quiet_start": 22,
            "quiet_end": 8,
        }

    return {
        "user_dm_enabled": bool(row[0]),
        "staff_dm_enabled": bool(row[1]),
        "user_delay": int(row[2]),
        "staff_delay": int(row[3]),
        "user_cooldown": int(row[4]),
        "staff_cooldown": int(row[5]),
        "quiet_enabled": bool(row[6]),
        "quiet_start": int(row[7]),
        "quiet_end": int(row[8]),
    }


# Grenzen fuer die einstellbaren Zeiten. Ohne sie koennte jemand 0
# eintragen und damit bei jeder Nachricht eine DM ausloesen.
LIMITS = {
    "user_delay": (30, 86400),
    "staff_delay": (30, 86400),
    "user_cooldown": (60, 604800),
    "staff_cooldown": (60, 604800),
}


async def save_settings(guild_id: int, data: dict) -> dict:
    """Einstellungen speichern. Gibt den Stand danach zurueck."""
    aktuell = await get_settings(guild_id)

    for schluessel in ("user_dm_enabled", "staff_dm_enabled", "quiet_enabled"):
        if schluessel in data:
            aktuell[schluessel] = bool(data[schluessel])

    for schluessel, (minimum, maximum) in LIMITS.items():
        if schluessel in data:
            try:
                wert = int(data[schluessel])
            except (TypeError, ValueError):
                continue
            aktuell[schluessel] = max(minimum, min(maximum, wert))

    for schluessel in ("quiet_start", "quiet_end"):
        if schluessel in data:
            try:
                aktuell[schluessel] = max(0, min(23, int(data[schluessel])))
            except (TypeError, ValueError):
                pass

    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO notify_settings (guild_id, user_dm_enabled, staff_dm_enabled,"
            " user_delay, staff_delay, user_cooldown, staff_cooldown,"
            " quiet_enabled, quiet_start, quiet_end)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " user_dm_enabled = excluded.user_dm_enabled,"
            " staff_dm_enabled = excluded.staff_dm_enabled,"
            " user_delay = excluded.user_delay,"
            " staff_delay = excluded.staff_delay,"
            " user_cooldown = excluded.user_cooldown,"
            " staff_cooldown = excluded.staff_cooldown,"
            " quiet_enabled = excluded.quiet_enabled,"
            " quiet_start = excluded.quiet_start,"
            " quiet_end = excluded.quiet_end",
            (
                guild_id,
                int(aktuell["user_dm_enabled"]),
                int(aktuell["staff_dm_enabled"]),
                aktuell["user_delay"],
                aktuell["staff_delay"],
                aktuell["user_cooldown"],
                aktuell["staff_cooldown"],
                int(aktuell["quiet_enabled"]),
                aktuell["quiet_start"],
                aktuell["quiet_end"],
            ),
        )
        await db.commit()

    return aktuell


def in_quiet_hours(settings: dict, now: datetime | None = None) -> bool:
    """
    Liegt der Zeitpunkt in der Ruhezeit?

    Der Fall, den man leicht falsch macht: 22 bis 8 laeuft ueber
    Mitternacht. ``22 <= stunde < 8`` waere immer falsch, also muss der
    Vergleich in dem Fall umgedreht werden.
    """
    if not settings.get("quiet_enabled"):
        return False

    start = int(settings.get("quiet_start", 22))
    ende = int(settings.get("quiet_end", 8))
    if start == ende:
        return False

    stunde = (now or datetime.now(timezone.utc)).hour
    if start < ende:
        return start <= stunde < ende
    return stunde >= start or stunde < ende


# ── Zustand eines Tickets ────────────────────────────────────────────

async def register_ticket(channel_id: int, guild_id: int, creator_id: int) -> None:
    """Ein frisch erstelltes Ticket vormerken."""
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO ticket_state (channel_id, guild_id, creator_id, last_user_msg)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(channel_id) DO UPDATE SET"
            " guild_id = excluded.guild_id, creator_id = excluded.creator_id",
            (channel_id, guild_id, creator_id, int(time.time())),
        )
        await db.commit()


async def get_state(channel_id: int) -> dict | None:
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT channel_id, guild_id, creator_id, last_user_msg, last_staff_msg,"
            " last_staff_id, staff_has_written, sleeping, sleep_by,"
            " pending_user, pending_staff"
            " FROM ticket_state WHERE channel_id = ?",
            (channel_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "channel_id": int(row[0]),
        "guild_id": int(row[1]),
        "creator_id": int(row[2]),
        "last_user_msg": int(row[3] or 0),
        "last_staff_msg": int(row[4] or 0),
        "last_staff_id": int(row[5]) if row[5] else None,
        "staff_has_written": bool(row[6]),
        "sleeping": bool(row[7]),
        "sleep_by": int(row[8]) if row[8] else None,
        "pending_user": int(row[9] or 0),
        "pending_staff": int(row[10] or 0),
    }


async def note_message(
    channel_id: int,
    *,
    author_id: int,
    is_staff: bool,
    guild_id: int | None = None,
    creator_id: int | None = None,
    now: int | None = None,
) -> dict | None:
    """
    Eine Nachricht im Ticket vermerken.

    Hier entsteht die eigentliche Buchfuehrung. Schreibt das Team,
    steht danach eine Nutzer-Benachrichtigung an und eine etwaige
    Team-Benachrichtigung ist hinfaellig -- und umgekehrt. Genau diese
    gegenseitige Aufhebung ist der Grund, warum beide Richtungen in
    derselben Funktion stehen.
    """
    jetzt = int(now if now is not None else time.time())

    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)

        async with db.execute(
            "SELECT guild_id, creator_id FROM ticket_state WHERE channel_id = ?",
            (channel_id,),
        ) as cursor:
            vorhanden = await cursor.fetchone()

        if vorhanden is None:
            if guild_id is None or creator_id is None:
                # Kein bekanntes Ticket und nichts, woraus sich eins
                # bauen liesse -- also ist es keins.
                return None
            await db.execute(
                "INSERT INTO ticket_state (channel_id, guild_id, creator_id)"
                " VALUES (?, ?, ?)",
                (channel_id, guild_id, creator_id),
            )

        if is_staff:
            # Team hat geschrieben: der Nutzer soll das erfahren, und
            # eine offene Team-Erinnerung ist damit erledigt.
            await db.execute(
                "UPDATE ticket_state SET last_staff_msg = ?, last_staff_id = ?,"
                " staff_has_written = 1, pending_user = ?, pending_staff = 0"
                " WHERE channel_id = ?",
                (jetzt, author_id, jetzt, channel_id),
            )
        else:
            # Nutzer hat geschrieben: eine offene Nutzer-Erinnerung ist
            # hinfaellig. Eine Team-Erinnerung entsteht nur, wenn
            # ueberhaupt schon jemand vom Team da war -- sonst waere es
            # ein frisches Ticket, in dem niemand etwas verpasst hat.
            await db.execute(
                "UPDATE ticket_state SET last_user_msg = ?, pending_user = 0,"
                " pending_staff = CASE WHEN staff_has_written = 1 THEN ? ELSE 0 END"
                " WHERE channel_id = ?",
                (jetzt, jetzt, channel_id),
            )

        await db.commit()

    return await get_state(channel_id)


async def set_sleeping(channel_id: int, sleeping: bool, by_id: int | None = None) -> bool:
    """
    ``>sleep`` / ``>wake`` fuer ein Ticket.

    Beim Einschlafen werden die offenen Erinnerungen gleich mit
    geloescht. Sonst kaeme nach dem Aufwachen eine DM zu einer
    Nachricht, die inzwischen laengst beantwortet ist.
    """
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        if sleeping:
            cursor = await db.execute(
                "UPDATE ticket_state SET sleeping = 1, sleep_by = ?,"
                " pending_user = 0, pending_staff = 0 WHERE channel_id = ?",
                (by_id, channel_id),
            )
        else:
            cursor = await db.execute(
                "UPDATE ticket_state SET sleeping = 0, sleep_by = NULL"
                " WHERE channel_id = ?",
                (channel_id,),
            )
        await db.commit()
        return bool(cursor.rowcount)


async def forget(channel_id: int) -> None:
    """Ticket geschlossen -- Zustand und Protokoll weg."""
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        await db.execute("DELETE FROM ticket_state WHERE channel_id = ?", (channel_id,))
        await db.execute("DELETE FROM notify_log WHERE channel_id = ?", (channel_id,))
        await db.commit()


# ── Sperrzeit ────────────────────────────────────────────────────────

async def recently_notified(
    channel_id: int, target_id: int, kind: str, within: int, now: int | None = None
) -> bool:
    """Hat diese Person fuer dieses Ticket kuerzlich schon eine DM bekommen?"""
    jetzt = int(now if now is not None else time.time())
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT 1 FROM notify_log WHERE channel_id = ? AND target_id = ?"
            " AND kind = ? AND sent_at > ? LIMIT 1",
            (channel_id, target_id, kind, jetzt - within),
        ) as cursor:
            return await cursor.fetchone() is not None


async def record_sent(
    channel_id: int, guild_id: int, target_id: int, kind: str, now: int | None = None
) -> None:
    """Eine zugestellte DM protokollieren und die Erinnerung abhaken."""
    jetzt = int(now if now is not None else time.time())
    spalte = "pending_user" if kind == "user" else "pending_staff"
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO notify_log (channel_id, guild_id, target_id, kind, sent_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (channel_id, guild_id, target_id, kind, jetzt),
        )
        await db.execute(
            f"UPDATE ticket_state SET {spalte} = 0 WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()


async def clear_pending(channel_id: int, kind: str) -> None:
    """Eine Erinnerung verwerfen, ohne etwas zu verschicken."""
    spalte = "pending_user" if kind == "user" else "pending_staff"
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        await db.execute(
            f"UPDATE ticket_state SET {spalte} = 0 WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()


# ── Die Entscheidung ─────────────────────────────────────────────────

async def decide(
    channel_id: int,
    kind: str,
    *,
    now: int | None = None,
    state: dict | None = None,
    settings: dict | None = None,
) -> Decision:
    """
    Darf jetzt eine DM raus?

    ``kind`` ist ``"user"`` oder ``"staff"``. Die Reihenfolge der
    Pruefungen ist die aus dem Kopf dieser Datei, und sie ist bewusst
    so: die billigen und die endgueltigen zuerst.
    """
    jetzt = int(now if now is not None else time.time())

    if state is None:
        state = await get_state(channel_id)
    if state is None:
        return Decision(False, "closed", kind=kind)

    if settings is None:
        settings = await get_settings(state["guild_id"])

    # 1. Funktion an?
    an = settings["user_dm_enabled"] if kind == "user" else settings["staff_dm_enabled"]
    if not an:
        return Decision(False, "disabled", kind=kind)

    # 6. Schlaeft das Ticket? Frueh geprueft, weil es alles ueberstimmt.
    if state["sleeping"]:
        return Decision(False, "sleeping", kind=kind)

    # 7. Ruhezeit.
    if in_quiet_hours(settings, datetime.fromtimestamp(jetzt, timezone.utc)):
        return Decision(False, "quiet_hours", kind=kind)

    if kind == "user":
        # 2. Frisches Ticket -- es war noch nie jemand vom Team da.
        if not state["staff_has_written"]:
            return Decision(False, "fresh_ticket", target_id=state["creator_id"], kind=kind)

        faellig_seit = state["pending_user"]
        if not faellig_seit:
            return Decision(False, "answered", target_id=state["creator_id"], kind=kind)

        # 4. Hat der Nutzer nach der Team-Nachricht selbst geschrieben?
        if state["last_user_msg"] >= state["last_staff_msg"]:
            return Decision(False, "answered", target_id=state["creator_id"], kind=kind)

        # 3. Wartezeit.
        if jetzt - faellig_seit < settings["user_delay"]:
            return Decision(False, "too_soon", target_id=state["creator_id"], kind=kind)

        # 5. Sperrzeit.
        if await recently_notified(
            channel_id, state["creator_id"], "user", settings["user_cooldown"], jetzt
        ):
            return Decision(False, "cooldown", target_id=state["creator_id"], kind=kind)

        return Decision(True, "ok", target_id=state["creator_id"], kind=kind)

    # kind == "staff"
    ziel = state["last_staff_id"]
    if not ziel:
        return Decision(False, "no_target", kind=kind)

    faellig_seit = state["pending_staff"]
    if not faellig_seit:
        return Decision(False, "answered", target_id=ziel, kind=kind)

    # 4. Hat das Team nach der Nutzer-Nachricht geantwortet?
    if state["last_staff_msg"] >= state["last_user_msg"]:
        return Decision(False, "answered", target_id=ziel, kind=kind)

    # 3. Wartezeit.
    if jetzt - faellig_seit < settings["staff_delay"]:
        return Decision(False, "too_soon", target_id=ziel, kind=kind)

    # 5. Sperrzeit.
    if await recently_notified(
        channel_id, ziel, "staff", settings["staff_cooldown"], jetzt
    ):
        return Decision(False, "cooldown", target_id=ziel, kind=kind)

    return Decision(True, "ok", target_id=ziel, kind=kind)


async def due_tickets(now: int | None = None) -> list[dict]:
    """
    Alle Tickets mit einer offenen Erinnerung.

    Nur eine Vorauswahl -- ob wirklich etwas rausgeht, entscheidet
    ``decide()``. Schlafende Tickets fallen schon hier raus, weil sie
    ohnehin nie zugestellt werden.
    """
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT channel_id, guild_id, pending_user, pending_staff"
            " FROM ticket_state"
            " WHERE sleeping = 0 AND (pending_user > 0 OR pending_staff > 0)"
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "channel_id": int(r[0]),
            "guild_id": int(r[1]),
            "pending_user": int(r[2] or 0),
            "pending_staff": int(r[3] or 0),
        }
        for r in rows
    ]


async def cleanup(older_than_days: int = 14) -> int:
    """Alte Protokollzeilen wegraeumen, damit die Tabelle nicht waechst."""
    grenze = int(time.time()) - older_than_days * 86400
    async with db_paths.connect(NOTIFY_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "DELETE FROM notify_log WHERE sent_at < ?", (grenze,)
        )
        await db.commit()
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
