"""
Server-Sicherungen: ein Knopf, eine Kennung, ein Wiederherstellen.

Was drinsteht
-------------
Der Aufbau des Servers (Kategorien, Kanaele, Rollen, Rechte) und die
Dashboard-Einstellungen -- beides liefert bereits
`utils.template_scan.build_payload`. Es gibt keinen zweiten Scanner:
zwei Stellen, die dasselbe lesen, laufen auseinander.

Zusaetzlich fuer Premium: die letzten :data:`MAX_NACHRICHTEN`
Nachrichten je Kanal.

Was NICHT drinsteht
-------------------
Mitglieder und ihre Rollenzuordnung. Discord kennt keinen Weg, jemanden
per Bot wieder in einen Server zu holen, und eine Rollenzuordnung ohne
die Person waere eine Liste von IDs ohne Wirkung.

Grenzen
-------
* Gratis: :data:`MAX_GRATIS` Sicherung(en), keine Nachrichten, keine
  Automatik.
* Premium: :data:`MAX_PREMIUM` Sicherungen, Nachrichten auf Wunsch,
  automatische Sicherung in einstellbarem Abstand.

Die Kennung
-----------
Jede Sicherung bekommt eine kurze Kennung (`BK-7F3A9C`). Sie steht in
der Oberflaeche und im Protokoll; eine fortlaufende Zahl waere
serveruebergreifend mehrdeutig, eine UUID zu lang zum Vorlesen.

Speicher
--------
`db/guild_backup.db`. Braucht ein Railway-Volume, sonst sind alle
Sicherungen nach dem naechsten Deploy weg -- und zwar lautlos.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
import zlib
from typing import Any, Optional

DB_PATH = os.path.join("db", "guild_backup.db")

#: Wie viele Sicherungen ein Server halten darf.
MAX_GRATIS = 1
MAX_PREMIUM = 10

#: Wie viele Nachrichten je Kanal gesichert werden (nur Premium).
#:
#: 500 ist die Vorgabe. Discord liefert 100 je Anfrage, das sind fuenf
#: Aufrufe je Kanal -- bei 50 Kanaelen 250 Aufrufe. Deshalb laeuft das
#: Sichern von Nachrichten im Hintergrund und nicht im Web-Aufruf.
MAX_NACHRICHTEN = 500

#: Kuerzeste erlaubte Automatik. Alles darunter waere ein Dauerlauf
#: ueber der Discord-Schnittstelle, ohne dass sich in der Zeit
#: nennenswert etwas aendert.
MIN_AUTO_STUNDEN = 6

#: Das Alphabet der Kennung. Ohne I, O, 0, 1 -- die werden beim
#: Vorlesen und Abtippen verwechselt.
KENNUNG_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def neue_kennung() -> str:
    """Eine kurze, vorlesbare Kennung: `BK-7F3A9C`."""
    teil = "".join(secrets.choice(KENNUNG_ALPHABET) for _ in range(6))
    return f"BK-{teil}"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Die Spalten stehen EINMAL hier. CREATE TABLE und das Nachruesten
# fehlender Spalten leiten sich beide daraus ab.
#
# Zwei handgepflegte Listen laufen auseinander -- bei `team_update` ist
# genau das passiert: eine Spalte fehlte in der zweiten, und auf einer
# bestehenden Installation kam „no such column".
SPALTEN: tuple[tuple[str, str], ...] = (
    ("guild_id", "INTEGER NOT NULL"),
    ("kennung", "TEXT NOT NULL"),
    ("erstellt_at", "INTEGER NOT NULL DEFAULT 0"),
    ("erstellt_von", "TEXT DEFAULT ''"),
    # Der Inhalt, als zlib-gepacktes JSON. Ein Serveraufbau mit 200
    # Kanaelen ist unkomprimiert schnell ein halbes Megabyte; mit
    # zehn Sicherungen je Server summiert sich das.
    ("daten", "BLOB"),
    ("groesse", "INTEGER NOT NULL DEFAULT 0"),
    # Zaehler fuer die Anzeige -- damit die Liste nicht jedes Mal
    # jede Sicherung entpacken muss.
    ("kanaele", "INTEGER NOT NULL DEFAULT 0"),
    ("rollen", "INTEGER NOT NULL DEFAULT 0"),
    ("nachrichten", "INTEGER NOT NULL DEFAULT 0"),
    ("mit_einstellungen", "INTEGER NOT NULL DEFAULT 1"),
    ("mit_nachrichten", "INTEGER NOT NULL DEFAULT 0"),
    # "hand" oder "auto" -- damit man sieht, was die Automatik
    # angelegt hat.
    ("quelle", "TEXT NOT NULL DEFAULT 'hand'"),
    ("notiz", "TEXT DEFAULT ''"),
)

AUTO_SPALTEN: tuple[tuple[str, str], ...] = (
    ("guild_id", "INTEGER PRIMARY KEY"),
    ("aktiv", "INTEGER NOT NULL DEFAULT 0"),
    ("stunden", "INTEGER NOT NULL DEFAULT 24"),
    # Beim automatischen Sichern die aelteste loeschen, wenn das
    # Fach voll ist. Ohne das steht die Automatik still, sobald die
    # Grenze erreicht ist -- und niemand merkt es.
    ("alte_loeschen", "INTEGER NOT NULL DEFAULT 1"),
    ("mit_nachrichten", "INTEGER NOT NULL DEFAULT 0"),
    ("letzter_lauf", "INTEGER NOT NULL DEFAULT 0"),
    ("letzter_fehler", "TEXT DEFAULT ''"),
)


def ensure() -> None:
    """Tabellen anlegen und fehlende Spalten nachruesten.

    `CREATE TABLE IF NOT EXISTS` aendert an einer BESTEHENDEN Tabelle
    nichts. Neue Spalten muessen per ALTER nachgezogen werden, sonst
    kommt auf jeder laufenden Installation „no such column".
    """
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS backups ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT)"
        )
        for name, typ in SPALTEN:
            try:
                conn.execute(f"ALTER TABLE backups ADD COLUMN {name} {typ}")
            except Exception:  # noqa: BLE001 - Spalte existiert bereits
                pass

        conn.execute(
            "CREATE INDEX IF NOT EXISTS backups_guild ON backups (guild_id)"
        )
        # Die Kennung muss eindeutig sein: sie ist der Weg, wie man
        # in Protokoll und Oberflaeche auf eine Sicherung zeigt.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS backups_kennung "
            "ON backups (kennung)"
        )

        conn.execute(
            "CREATE TABLE IF NOT EXISTS backup_auto ("
            " guild_id INTEGER PRIMARY KEY)"
        )
        for name, typ in AUTO_SPALTEN:
            if name == "guild_id":
                continue
            try:
                conn.execute(f"ALTER TABLE backup_auto ADD COLUMN {name} {typ}")
            except Exception:  # noqa: BLE001
                pass


def grenze(premium: bool) -> int:
    return MAX_PREMIUM if premium else MAX_GRATIS


# ── Packen ────────────────────────────────────────────────────────────
#
# JSON, dann zlib. Getrennt gehalten, damit `lade()` und `speichere()`
# sich nicht widersprechen koennen.


def _packe(inhalt: dict) -> bytes:
    return zlib.compress(
        json.dumps(inhalt, ensure_ascii=False).encode("utf-8"), 6
    )


def _entpacke(roh: bytes) -> dict:
    if not roh:
        return {}
    return json.loads(zlib.decompress(roh).decode("utf-8"))


def _zeile(row: sqlite3.Row, *, mit_daten: bool = False) -> dict[str, Any]:
    eintrag = {
        "id": int(row["id"]),
        # Als Zeichenkette: eine Discord-ID ist groesser als das, was
        # JavaScript als Zahl noch genau darstellen kann.
        "guild_id": str(row["guild_id"]),
        "kennung": row["kennung"] or "",
        "erstellt_at": int(row["erstellt_at"] or 0),
        "erstellt_von": row["erstellt_von"] or "",
        "groesse": int(row["groesse"] or 0),
        "kanaele": int(row["kanaele"] or 0),
        "rollen": int(row["rollen"] or 0),
        "nachrichten": int(row["nachrichten"] or 0),
        "mit_einstellungen": bool(row["mit_einstellungen"]),
        "mit_nachrichten": bool(row["mit_nachrichten"]),
        "quelle": row["quelle"] or "hand",
        "notiz": row["notiz"] or "",
    }
    if mit_daten:
        eintrag["daten"] = _entpacke(row["daten"])
    return eintrag


def liste(guild_id: int) -> list[dict[str, Any]]:
    """Alle Sicherungen dieses Servers, neueste zuerst."""
    ensure()
    with _connect() as conn:
        zeilen = conn.execute(
            "SELECT * FROM backups WHERE guild_id = ? "
            "ORDER BY erstellt_at DESC",
            (int(guild_id),),
        ).fetchall()
    return [_zeile(z) for z in zeilen]


def anzahl(guild_id: int) -> int:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM backups WHERE guild_id = ?",
            (int(guild_id),),
        ).fetchone()
    return int(row["n"] or 0)


def hole(guild_id: int, kennung: str, *, mit_daten: bool = False):
    """Eine Sicherung -- oder None.

    Die Server-ID steht in der Abfrage, obwohl die Kennung eindeutig
    ist. Sonst koennte man mit einer fremden Kennung die Sicherung
    eines anderen Servers lesen, indem man sie an die eigene
    Server-ID haengt.
    """
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM backups WHERE guild_id = ? AND kennung = ?",
            (int(guild_id), str(kennung)),
        ).fetchone()
    return _zeile(row, mit_daten=mit_daten) if row else None


def speichere(guild_id: int, inhalt: dict, *, erstellt_von: str = "",
              quelle: str = "hand", mit_nachrichten: bool = False,
              notiz: str = "") -> dict[str, Any]:
    """Eine Sicherung ablegen und ihre Kennung zurueckgeben."""
    ensure()

    roh = _packe(inhalt)

    kanaele = len(inhalt.get("channels") or [])
    rollen = len(inhalt.get("roles") or [])
    nachrichten = sum(
        len(v or []) for v in (inhalt.get("messages") or {}).values()
    )

    # Die Kennung muss eindeutig sein. Bei 32^6 Moeglichkeiten ist ein
    # Zusammenstoss unwahrscheinlich, aber „unwahrscheinlich" ist kein
    # Grund, den Fehler nicht zu behandeln.
    with _connect() as conn:
        for _ in range(10):
            kennung = neue_kennung()
            try:
                cur = conn.execute(
                    "INSERT INTO backups (guild_id, kennung, erstellt_at, "
                    "erstellt_von, daten, groesse, kanaele, rollen, "
                    "nachrichten, mit_einstellungen, mit_nachrichten, "
                    "quelle, notiz) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(guild_id), kennung, int(time.time()),
                        str(erstellt_von or ""), roh, len(roh),
                        kanaele, rollen, nachrichten,
                        1 if inhalt.get("features") else 0,
                        1 if mit_nachrichten else 0,
                        str(quelle or "hand"), str(notiz or "")[:200],
                    ),
                )
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise RuntimeError("Keine freie Kennung gefunden.")

        row = conn.execute(
            "SELECT * FROM backups WHERE id = ?", (cur.lastrowid,)
        ).fetchone()

    return _zeile(row)


def loesche(guild_id: int, kennung: str) -> bool:
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM backups WHERE guild_id = ? AND kennung = ?",
            (int(guild_id), str(kennung)),
        )
    return (cur.rowcount or 0) > 0


def loesche_aelteste(guild_id: int, *, behalte: int) -> int:
    """Alles ausser den `behalte` neuesten loeschen.

    Wird von der Automatik gebraucht: ohne das steht sie still, sobald
    das Fach voll ist -- und niemand merkt es.
    """
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM backups WHERE guild_id = ? AND id NOT IN ("
            "  SELECT id FROM backups WHERE guild_id = ? "
            "  ORDER BY erstellt_at DESC LIMIT ?"
            ")",
            (int(guild_id), int(guild_id), max(0, int(behalte))),
        )
    return cur.rowcount or 0


# ── Die Automatik ─────────────────────────────────────────────────────


def auto_zustand(guild_id: int) -> dict[str, Any]:
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM backup_auto WHERE guild_id = ?", (int(guild_id),)
        ).fetchone()

    if row is None:
        return {
            "aktiv": False,
            "stunden": 24,
            "alte_loeschen": True,
            "mit_nachrichten": False,
            "letzter_lauf": 0,
            "letzter_fehler": "",
        }

    return {
        "aktiv": bool(row["aktiv"]),
        "stunden": int(row["stunden"] or 24),
        "alte_loeschen": bool(row["alte_loeschen"]),
        "mit_nachrichten": bool(row["mit_nachrichten"]),
        "letzter_lauf": int(row["letzter_lauf"] or 0),
        "letzter_fehler": row["letzter_fehler"] or "",
    }


def auto_setze(guild_id: int, **felder) -> dict[str, Any]:
    """Einzelne Felder aendern; alles Uebrige bleibt stehen."""
    ensure()
    erlaubt = {name for name, _ in AUTO_SPALTEN} - {"guild_id"}
    zu_setzen: dict[str, Any] = {}

    for schluessel, wert in felder.items():
        if schluessel not in erlaubt:
            continue
        if schluessel == "stunden":
            # Untergrenze hier, nicht nur im Browser: eine Sperre, die
            # allein im Dashboard sitzt, ist keine.
            wert = max(MIN_AUTO_STUNDEN, min(24 * 30, int(wert or 24)))
        elif schluessel in ("aktiv", "alte_loeschen", "mit_nachrichten"):
            wert = 1 if wert else 0
        zu_setzen[schluessel] = wert

    if not zu_setzen:
        return auto_zustand(guild_id)

    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO backup_auto (guild_id) VALUES (?)",
            (int(guild_id),),
        )
        zuweisung = ", ".join(f"{name} = ?" for name in zu_setzen)
        conn.execute(
            f"UPDATE backup_auto SET {zuweisung} WHERE guild_id = ?",
            (*zu_setzen.values(), int(guild_id)),
        )

    return auto_zustand(guild_id)


def auto_faellige() -> list[dict[str, Any]]:
    """Welche Server sind dran?

    Gefragt wird beim Hintergrundlauf. Ein Server ist faellig, wenn
    die Automatik an ist und der letzte Lauf laenger her ist als der
    eingestellte Abstand.
    """
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        zeilen = conn.execute(
            "SELECT * FROM backup_auto WHERE aktiv = 1"
        ).fetchall()

    faellig = []
    for row in zeilen:
        abstand = max(MIN_AUTO_STUNDEN, int(row["stunden"] or 24)) * 3600
        if jetzt - int(row["letzter_lauf"] or 0) >= abstand:
            faellig.append({
                "guild_id": int(row["guild_id"]),
                "stunden": int(row["stunden"] or 24),
                "alte_loeschen": bool(row["alte_loeschen"]),
                "mit_nachrichten": bool(row["mit_nachrichten"]),
            })
    return faellig


def auto_lauf_vermerkt(guild_id: int, *, fehler: str = "") -> None:
    """Den Zeitpunkt festhalten -- auch bei einem Fehler.

    Sonst versucht die Automatik es bei jedem Durchlauf erneut und
    laeuft bei einem dauerhaften Problem gegen die Wand.
    """
    ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO backup_auto (guild_id) VALUES (?)",
            (int(guild_id),),
        )
        conn.execute(
            "UPDATE backup_auto SET letzter_lauf = ?, letzter_fehler = ? "
            "WHERE guild_id = ?",
            (int(time.time()), str(fehler or "")[:300], int(guild_id)),
        )
