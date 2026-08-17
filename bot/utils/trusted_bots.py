# ╔══════════════════════════════════════════════════════════════════╗
# ║   Bots, die der Anti-Nuke nie angreift                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Die Liste der vertrauten Bots -- global, vom Betreiber gepflegt.

Woher sie kommt
---------------
Bekannte Bots wie MEE6 oder Dyno legen Kanäle an, vergeben Rollen und
löschen Nachrichten -- also genau das, was der Anti-Nuke als Angriff
liest. Ohne Eintrag bannt er sie beim ersten Mal.

Bisher gab es dafür nur die Umgebungsvariable ``TRUSTED_BOTS``. Die
bleibt: was dort steht, gilt weiter. Dazu kommt jetzt eine Liste im
Admin-Dashboard, damit ein Bot ohne Deploy ergänzt werden kann.

Die drei, die immer drinstehen
------------------------------
``ALWAYS`` enthält den Hauptbot, den Template-Bot und den Statusbot.
Sie lassen sich **nicht** entfernen, und zwar aus einem handfesten
Grund: der Template-Bot baut nach einem Angriff Server wieder auf --
dutzende Kanäle und Rollen in Sekunden, die exakte Form eines Nukes.
Wer ihn versehentlich austrägt, lässt ihn mitten in der Rettung
bannen und steht mit einem halb wiederhergestellten Server da.

Warum global und nicht pro Server
---------------------------------
Weil die Liste sonst eine Hintertür wäre: wer sie auf dem eigenen
Server pflegen dürfte, trägt seinen Zweitbot ein und hat den Schutz
ausgehebelt, den der Reiter verspricht. Server-Inhaber sehen die
Liste, ändern können sie nur Admins.

Speicher
--------
``db/trusted_bots.db``. Braucht ein Railway-Volume -- ohne das ist die
Liste nach jedem Deploy leer, und dann bannt der Anti-Nuke beim
nächsten Mal wieder jeden fremden Bot.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

from utils import partner_bot

DB_PATH = os.path.join("db", "trusted_bots.db")

#: Die Umgebungsvariable, die es schon vorher gab.
TRUSTED_ENV = "TRUSTED_BOTS"

#: Die eigenen Bots. Nicht entfernbar -- siehe Modul-Docstring.
#:
#: Der Hauptbot steht hier, weil ein Bot sich sonst selbst bannen
#: könnte; der Template-Bot, weil er nach einem Angriff aufräumt; der
#: Statusbot, weil er auf Partner-Servern Panels pflegt.
ALWAYS: dict[int, str] = {
    1530349205372145715: "University Bot (Hauptbot)",
    partner_bot.BOT_ID: "University Template (Vorlagen-Bot)",
    1530378233579704370: "Statusbot",
}

COLUMNS: tuple[tuple[str, str], ...] = (
    ("bot_id", "TEXT PRIMARY KEY"),
    ("note", "TEXT NOT NULL DEFAULT ''"),
    ("added_by", "TEXT NOT NULL DEFAULT ''"),
    ("added_at", "INTEGER NOT NULL DEFAULT 0"),
)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    """Tabelle anlegen und fehlende Spalten nachrüsten."""
    spalten = ", ".join(f"{name} {typ}" for name, typ in COLUMNS)
    with _connect() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS trusted_bots ({spalten})")

        # CREATE TABLE IF NOT EXISTS ändert an einer bestehenden Tabelle
        # nichts. Kommt später eine Spalte dazu, fehlt sie auf jeder
        # laufenden Installation -- und jede Abfrage scheitert.
        vorhanden = {row[1] for row in conn.execute("PRAGMA table_info(trusted_bots)")}
        for name, typ in COLUMNS:
            if name in vorhanden:
                continue
            nachtrag = typ.replace("PRIMARY KEY", "").strip()
            if "DEFAULT" not in nachtrag.upper():
                nachtrag = nachtrag.replace("NOT NULL", "").strip()
            conn.execute(f"ALTER TABLE trusted_bots ADD COLUMN {name} {nachtrag}")


def from_env() -> set[int]:
    """Die IDs aus ``TRUSTED_BOTS``.

    Alles, was keine Zahl ist, wird übersprungen. Ein Tippfehler in der
    Variablen darf den Anti-Nuke nicht lahmlegen -- ein ungeschützter
    Server wäre der schlimmere Ausgang als ein ignorierter Eintrag.
    """
    roh = os.getenv(TRUSTED_ENV, "") or ""
    ids: set[int] = set()
    for teil in roh.replace(";", ",").split(","):
        teil = teil.strip()
        if teil.isdigit():
            ids.add(int(teil))
    return ids


def stored_ids() -> set[int]:
    """Nur die IDs aus der Datenbank, ohne ALWAYS und ohne Variable."""
    ensure()
    with _connect() as conn:
        rows = conn.execute("SELECT bot_id FROM trusted_bots").fetchall()
    ids: set[int] = set()
    for row in rows:
        try:
            ids.add(int(row["bot_id"]))
        except (TypeError, ValueError):
            continue
    return ids


def all_ids() -> frozenset[int]:
    """Alle vertrauten IDs: fest eingebaut, aus der Variablen, aus der DB.

    Diese Funktion fragt der Anti-Nuke. Sie liest bei jedem Aufruf --
    ein Zwischenspeicher würde bedeuten, dass ein neu eingetragener Bot
    erst nach einem Neustart geschützt ist, und genau darum ging es bei
    der Dashboard-Liste.
    """
    try:
        gespeichert = stored_ids()
    except sqlite3.Error:
        # Eine kaputte Datei darf den Schutz der eingebauten Bots nicht
        # mitnehmen: dann lieber ohne die Liste weiterlaufen.
        gespeichert = set()
    return frozenset(set(ALWAYS) | from_env() | gespeichert)


def is_trusted(user_or_id) -> bool:
    """Steht dieses Konto auf der Liste?"""
    if user_or_id is None:
        return False
    kennung = getattr(user_or_id, "id", user_or_id)
    try:
        return int(kennung) in all_ids()
    except (TypeError, ValueError):
        return False


def add(bot_id: int | str, *, note: str = "", actor: str = "") -> dict[str, Any]:
    """Einen Bot eintragen.

    Gibt ``{"ok": False, "error": ...}`` zurück statt zu werfen -- der
    Aufrufer ist eine HTTP-Route und braucht eine Antwort, keine
    Ausnahme.
    """
    kennung = str(bot_id).strip()
    if not kennung.isdigit():
        return {"ok": False, "error": "invalid_id"}

    zahl = int(kennung)
    if zahl in ALWAYS:
        return {"ok": False, "error": "builtin"}
    if zahl in stored_ids():
        return {"ok": False, "error": "exists"}

    ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO trusted_bots (bot_id, note, added_by, added_at)"
            " VALUES (?, ?, ?, ?)",
            (str(zahl), str(note or "")[:200], str(actor or ""), int(time.time())),
        )
    return {"ok": True, "bot_id": str(zahl)}


def remove(bot_id: int | str) -> dict[str, Any]:
    """Einen Bot austragen.

    Die drei aus ``ALWAYS`` lassen sich nicht entfernen. Ein stilles
    „hat geklappt" wäre hier falsch: der Aufrufer glaubt sonst, der
    Eintrag sei weg, und wundert sich beim nächsten Laden.
    """
    kennung = str(bot_id).strip()
    if not kennung.isdigit():
        return {"ok": False, "error": "invalid_id"}

    zahl = int(kennung)
    if zahl in ALWAYS:
        return {"ok": False, "error": "builtin"}

    ensure()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM trusted_bots WHERE bot_id = ?", (str(zahl),))
        if cur.rowcount:
            return {"ok": True, "bot_id": str(zahl)}

    # Aus der Umgebungsvariablen lässt sich hier nichts löschen -- das
    # geht nur in Railway. Das muss die Oberfläche sagen können.
    if zahl in from_env():
        return {"ok": False, "error": "from_env"}
    return {"ok": False, "error": "unknown"}


def _quelle(kennung: int) -> str:
    """Woher der Eintrag kommt -- entscheidet, ob er löschbar ist."""
    if kennung in ALWAYS:
        return "builtin"
    if kennung in from_env():
        return "env"
    return "manual"


def list_all(bot=None) -> list[dict[str, Any]]:
    """Die ganze Liste für das Dashboard, mit Namen und Bild.

    ``bot`` ist die laufende Bot-Instanz. Kennt sie ein Konto nicht,
    bleibt der Name leer -- das ist ehrlicher als ein erfundener und
    ein Hinweis darauf, dass der Bot dieses Konto nie gesehen hat.
    """
    ensure()
    with _connect() as conn:
        rows = {
            str(r["bot_id"]): r
            for r in conn.execute("SELECT * FROM trusted_bots").fetchall()
        }

    out: list[dict[str, Any]] = []
    for kennung in sorted(all_ids()):
        row = rows.get(str(kennung))
        # Gegen einen Bot, der noch startet oder eine Attrappe ist:
        # ohne Namen weiterzumachen ist besser, als die ganze Liste
        # scheitern zu lassen.
        try:
            user = bot.get_user(kennung) if bot is not None else None
        except Exception:  # noqa: BLE001
            user = None
        out.append({
            # Als Zeichenkette: eine Discord-ID ist größer als das, was
            # JavaScript unfallfrei als Zahl hält.
            "id": str(kennung),
            "name": (
                getattr(user, "display_name", "") or getattr(user, "name", "")
                if user is not None else ""
            ),
            "avatar": (
                str(user.display_avatar.url)
                if user is not None and getattr(user, "display_avatar", None)
                else None
            ),
            "known": user is not None,
            "source": _quelle(kennung),
            "label": ALWAYS.get(kennung, ""),
            "note": (row["note"] if row is not None else "") or "",
            "added_by": (row["added_by"] if row is not None else "") or "",
            "added_at": int(row["added_at"]) if row is not None else 0,
        })

    # Die eingebauten zuerst: sie erklären, warum die Liste nie leer
    # ist.
    reihenfolge = {"builtin": 0, "env": 1, "manual": 2}
    out.sort(key=lambda e: (reihenfolge.get(e["source"], 9), e["id"]))
    return out
