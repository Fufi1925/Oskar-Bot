"""
Honeypot: ein Koeder-Kanal, in den niemand schreiben soll.

Die Idee
--------
Ganz oben im Server steht ein Kanal, den jeder sehen und in den jeder
schreiben darf. In ihm steht eine Nachricht, die unmissverstaendlich
sagt: **hier nichts hineinschreiben**. Wer es trotzdem tut, wird
softgebannt.

Das trifft fast ausschliesslich Spam-Bots. Die arbeiten den Kanalbaum
von oben nach unten ab und schreiben in den erstbesten Kanal, in dem
sie duerfen -- Text lesen sie nicht. Ein Mensch liest die Warnung.

Deshalb muss der Kanal **ganz oben** stehen (`position = 0`, ausserhalb
jeder Kategorie): steht er weiter unten, hat der Bot vorher schon in
einen echten Kanal geschrieben, und der Koeder kommt zu spaet.

Warum Softban und nicht Kick
----------------------------
Ein Kick entfernt die Person, laesst aber ihren Spam stehen. Ein
Softban -- bannen und sofort wieder entbannen -- loescht die
Nachrichten der letzten Tage gleich mit und laesst die Person
grundsaetzlich zurueckkommen. Genau das steht auch im Bild, an dem
sich diese Umsetzung orientiert: „will result in **a softban**".

Was bewusst NICHT passiert
--------------------------
Kann der Bot jemanden nicht bannen -- zu hohe Rolle, fehlendes Recht,
Server-Inhaber --, passiert **nichts**. Keine Fehlermeldung im Kanal,
keine Nachricht an den Inhaber, kein Eintrag ausser der Zeile im
Log-Kanal, falls einer eingestellt ist. Ausdrueckliche Vorgabe:
„alles was der bot nicht sofabnne kann keine meldung nix einsfach
still".

Der Grund dahinter ist auch inhaltlich richtig: eine Fehlermeldung im
Koeder-Kanal wuerde verraten, dass es eine Grenze gibt, und aus einer
stillen Falle eine Ankuendigung machen.

Speicher
--------
`db/honeypot.db`. Braucht ein Railway-Volume, sonst sind nach jedem
Deploy die Einstellungen **und der Zaehler** weg.
"""

from __future__ import annotations

import time

import aiosqlite

DB_PATH = "db/honeypot.db"

#: Name des Kanals, den der Bot selbst anlegt.
#:
#: Genau so gewuenscht. Discord macht daraus ohnehin Kleinbuchstaben
#: mit Bindestrichen, also steht er hier gleich in der Form, in der er
#: nachher wirklich heisst -- sonst sucht die Wiedererkennung weiter
#: unten nach einem Namen, den es so nie gibt.
DEFAULT_CHANNEL_NAME = "dont-sent-here"

#: Die Ueberschrift der Koeder-Nachricht.
DEFAULT_TITLE = "SCHREIBE NICHT IN DIESEN KANAL"

#: Der Text darunter.
DEFAULT_TEXT = (
    "Dieser Kanal fängt Spam-Bots ab. Jede Nachricht hier führt zu "
    "einem **Softban**."
)

#: Obergrenzen. Discord selbst laesst im Titel eines Embeds 256 und in
#: der Beschreibung 4096 Zeichen zu; darunter zu bleiben ist billiger,
#: als die Fehlermeldung erst von Discord zu bekommen.
MAX_TITLE = 200
MAX_TEXT = 1500

#: Wie viele Tage Nachrichten der Softban loescht. Discord erlaubt
#: 0 bis 7.
DEFAULT_DELETE_DAYS = 1
MAX_DELETE_DAYS = 7


#: Die Spalten, an EINER Stelle.
#:
#: `CREATE TABLE IF NOT EXISTS` aendert an einer bestehenden Tabelle
#: nichts. Wer die Tabelle schon hat, bekaeme bei einer neuen Spalte
#: sonst „no such column" -- zwei handgepflegte Listen laufen
#: auseinander, das ist bei `team_update` genau so passiert.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("enabled", "INTEGER DEFAULT 0"),
    ("channel_id", "INTEGER"),
    ("message_id", "INTEGER"),
    ("custom_channel_id", "INTEGER"),
    ("log_channel_id", "INTEGER"),
    ("title", "TEXT"),
    ("text", "TEXT"),
    ("kicks", "INTEGER DEFAULT 0"),
    ("delete_days", f"INTEGER DEFAULT {DEFAULT_DELETE_DAYS}"),
    ("whitelist_roles", "TEXT"),
    ("updated_at", "REAL DEFAULT 0"),
)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS honeypot (
            guild_id INTEGER PRIMARY KEY
        )
        """
    )
    for name, typ in COLUMNS:
        try:
            await db.execute(f"ALTER TABLE honeypot ADD COLUMN {name} {typ}")
        except Exception:  # noqa: BLE001 - Spalte existiert bereits
            pass
    await db.commit()


def _rollen_liste(roh: str | None) -> list[int]:
    """Aus dem gespeicherten Text eine Liste von Rollen-IDs machen."""
    if not roh:
        return []
    ergebnis = []
    for stueck in str(roh).split(","):
        stueck = stueck.strip()
        if stueck.isdigit():
            ergebnis.append(int(stueck))
    return ergebnis


async def get(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Die Einstellungen eines Servers -- immer vollstaendig.

    Nie None: ein Server ohne Eintrag ist schlicht ein Server mit
    ausgeschaltetem Honeypot, und der Aufrufer soll das nicht bei
    jedem Zugriff pruefen muessen.
    """
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM honeypot WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        zeile = await cursor.fetchone()

    if zeile is None:
        return {
            "guild_id": guild_id,
            "enabled": False,
            "channel_id": None,
            "message_id": None,
            "custom_channel_id": None,
            "log_channel_id": None,
            "title": DEFAULT_TITLE,
            "text": DEFAULT_TEXT,
            "kicks": 0,
            "delete_days": DEFAULT_DELETE_DAYS,
            "whitelist_roles": [],
            "updated_at": 0.0,
        }

    daten = dict(zeile)
    return {
        "guild_id": guild_id,
        "enabled": bool(daten.get("enabled")),
        "channel_id": daten.get("channel_id") or None,
        "message_id": daten.get("message_id") or None,
        "custom_channel_id": daten.get("custom_channel_id") or None,
        "log_channel_id": daten.get("log_channel_id") or None,
        "title": daten.get("title") or DEFAULT_TITLE,
        "text": daten.get("text") or DEFAULT_TEXT,
        "kicks": int(daten.get("kicks") or 0),
        "delete_days": int(
            daten.get("delete_days")
            if daten.get("delete_days") is not None
            else DEFAULT_DELETE_DAYS
        ),
        "whitelist_roles": _rollen_liste(daten.get("whitelist_roles")),
        "updated_at": float(daten.get("updated_at") or 0),
    }


async def save(db: aiosqlite.Connection, guild_id: int, **felder) -> dict:
    """Einzelne Felder aendern; alles Uebrige bleibt stehen."""
    erlaubt = {name for name, _ in COLUMNS}
    zu_setzen: dict[str, object] = {}

    for schluessel, wert in felder.items():
        if schluessel not in erlaubt:
            continue

        if schluessel == "whitelist_roles":
            if isinstance(wert, (list, tuple, set)):
                wert = ",".join(str(int(w)) for w in wert if str(w).isdigit())
            else:
                wert = ",".join(str(r) for r in _rollen_liste(wert))
        elif schluessel in ("enabled",):
            wert = 1 if wert else 0
        elif schluessel == "title":
            wert = (str(wert or "").strip() or DEFAULT_TITLE)[:MAX_TITLE]
        elif schluessel == "text":
            wert = (str(wert or "").strip() or DEFAULT_TEXT)[:MAX_TEXT]
        elif schluessel == "delete_days":
            try:
                wert = max(0, min(int(wert), MAX_DELETE_DAYS))
            except (TypeError, ValueError):
                wert = DEFAULT_DELETE_DAYS
        elif schluessel in ("channel_id", "message_id", "custom_channel_id",
                            "log_channel_id"):
            wert = int(wert) if wert not in (None, "", 0, "0") else None
        elif schluessel == "kicks":
            try:
                wert = max(0, int(wert))
            except (TypeError, ValueError):
                wert = 0

        zu_setzen[schluessel] = wert

    if not zu_setzen:
        return await get(db, guild_id)

    zu_setzen["updated_at"] = time.time()

    await db.execute(
        "INSERT OR IGNORE INTO honeypot (guild_id) VALUES (?)", (guild_id,)
    )
    zuweisung = ", ".join(f"{name} = ?" for name in zu_setzen)
    await db.execute(
        f"UPDATE honeypot SET {zuweisung} WHERE guild_id = ?",
        (*zu_setzen.values(), guild_id),
    )
    await db.commit()
    return await get(db, guild_id)


async def bump_kicks(db: aiosqlite.Connection, guild_id: int) -> int:
    """Den Zaehler um eins erhoehen und den neuen Stand zurueckgeben.

    Ausdruecklich in SQL (`kicks = kicks + 1`) und nicht als
    „lesen, plus eins, schreiben": zwei Spam-Bots, die im selben
    Moment schreiben, wuerden sich sonst gegenseitig ueberschreiben
    und nur einen Treffer zaehlen.
    """
    await db.execute(
        "INSERT OR IGNORE INTO honeypot (guild_id) VALUES (?)", (guild_id,)
    )
    await db.execute(
        "UPDATE honeypot SET kicks = COALESCE(kicks, 0) + 1, updated_at = ? "
        "WHERE guild_id = ?",
        (time.time(), guild_id),
    )
    await db.commit()

    async with db.execute(
        "SELECT kicks FROM honeypot WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        zeile = await cursor.fetchone()
    return int(zeile[0]) if zeile else 0


async def all_enabled(db: aiosqlite.Connection) -> list[dict]:
    """Jeder Server mit eingeschaltetem Honeypot.

    Wird beim Start gebraucht, um die Koeder-Nachrichten wieder an
    ihre Knoepfe zu haengen.
    """
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT guild_id FROM honeypot WHERE enabled = 1"
    ) as cursor:
        zeilen = await cursor.fetchall()

    return [await get(db, int(z["guild_id"])) for z in zeilen]
