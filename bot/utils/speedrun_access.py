"""
Wer darf den Speedrun-Reiter benutzen.

Der Reiter ist gesperrt, bis jemand einen Code eingibt. Freigeschaltet
wird damit **ein Server**, nicht ein Nutzer: der Speedrun baut einen
konkreten Server um, und wer auf zwei Servern etwas aufsetzen will,
gibt ihn zweimal ein. Das ist Absicht -- eine Freischaltung, die am
Konto haengt, wandert mit dem Nutzer auf jeden Server, auf dem er
Rechte hat.

Drei Zustaende pro Server:

  * **gesperrt**   Nichts eingegeben. Der Reiter zeigt nur das Feld.
  * **frei**       Code eingegeben, alles offen.
  * **gebannt**    Von einem Admin gesperrt. Kein Code hilft mehr,
                   bis der Bann aufgehoben wird.

Der Unterschied zwischen *Entzug* und *Bann* ist der, den der Betrieb
braucht: Entzug heisst "einmal neu eingeben, dann geht es wieder" --
etwa wenn ein Server den Besitzer wechselt. Bann heisst "nie wieder,
egal wie oft du tippst".

Der Code selbst wird gehasht abgelegt, nicht im Klartext. Das ist hier
weniger dramatisch als bei einem Passwort -- der Code ist derselbe fuer
alle -- aber die Tabelle protokolliert mit, *wer wann was* getan hat,
und in so einer Tabelle hat ein Geheimnis nichts verloren.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from typing import Any

DB_PATH = os.path.join("db", "speedrun_access.db")

# Der Code, wie er dem Nutzer angezeigt wird.
DISPLAY_CODE = "University beta v1"

# Was als richtig durchgeht.
#
# Der Nutzer hat den Code als »Univertiy beta v1« aufgeschrieben -- mit
# vertauschtem "si". Beide Schreibweisen gelten, denn ein Vertipper im
# Codewort sperrt sonst genau die Leute aus, fuer die die Beta gedacht
# ist, und sie koennten es nicht einmal erklaeren: auf dem Bildschirm
# steht ja "falscher Code".
#
# Verglichen wird kleingeschrieben und mit zusammengezogenen
# Leerzeichen, damit "UNIVERSITY  BETA V1" ebenfalls durchgeht.
_ACCEPTED = {
    "university beta v1",
    "univertiy beta v1",
}


def normalise(code: str) -> str:
    """Zum Vergleich vorbereiten: klein, ohne Rand, ein Leerzeichen."""

    return re.sub(r"\s+", " ", str(code or "").strip()).lower()


def code_is_valid(code: str) -> bool:
    return normalise(code) in _ACCEPTED


def _hash(code: str) -> str:
    """Der eingegebene Code, gehasht -- damit er nicht im Klartext liegt."""

    return hashlib.sha256(normalise(code).encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    """Die Tabellen anlegen. Bei jedem Zugriff gefahrlos aufrufbar."""

    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS speedrun_access (
                guild_id     TEXT PRIMARY KEY,
                unlocked_at  INTEGER NOT NULL,
                unlocked_by  TEXT NOT NULL,
                code_hash    TEXT NOT NULL,
                banned       INTEGER NOT NULL DEFAULT 0,
                banned_at    INTEGER,
                banned_by    TEXT,
                ban_reason   TEXT NOT NULL DEFAULT '',
                runs         INTEGER NOT NULL DEFAULT 0,
                last_run_at  INTEGER
            )
            """
        )
        # Der Verlauf. Getrennt von der Zustandstabelle, weil ein
        # Entzug die Zeile dort loescht -- die Geschichte soll das
        # ueberleben, sonst kann niemand mehr sagen, wer den Server
        # damals freigeschaltet hat.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS speedrun_access_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id  TEXT NOT NULL,
                event     TEXT NOT NULL,
                user_id   TEXT NOT NULL DEFAULT '',
                actor_id  TEXT NOT NULL DEFAULT '',
                detail    TEXT NOT NULL DEFAULT '',
                at        INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS speedrun_access_log_guild "
            "ON speedrun_access_log (guild_id, id DESC)"
        )


def log_event(
    guild_id: int | str,
    event: str,
    *,
    user_id: str = "",
    actor_id: str = "",
    detail: str = "",
) -> None:
    """Eine Zeile in den Verlauf.

    Ereignisse: ``unlocked``, ``denied``, ``revoked``, ``banned``,
    ``unbanned``, ``run_started``.
    """

    ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO speedrun_access_log "
            "(guild_id, event, user_id, actor_id, detail, at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(guild_id), event, str(user_id), str(actor_id), detail,
             int(time.time())),
        )


def state(guild_id: int | str) -> dict[str, Any]:
    """Der Zustand eines Servers -- die eine Frage, die der Reiter stellt."""

    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM speedrun_access WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()

    if row is None:
        return {
            "unlocked": False,
            "banned": False,
            "guild_id": str(guild_id),
        }

    banned = bool(row["banned"])
    return {
        # Ein gebannter Server ist nicht frei, auch wenn die
        # Freischaltung noch in der Zeile steht. Sonst muesste jeder
        # Aufrufer an zwei Stellen denken.
        "unlocked": not banned,
        "banned": banned,
        "guild_id": str(guild_id),
        "unlocked_at": row["unlocked_at"],
        "unlocked_by": row["unlocked_by"],
        "banned_at": row["banned_at"],
        "banned_by": row["banned_by"],
        "ban_reason": row["ban_reason"] or "",
        "runs": row["runs"],
        "last_run_at": row["last_run_at"],
    }


def is_unlocked(guild_id: int | str) -> bool:
    return bool(state(guild_id)["unlocked"])


def unlock(guild_id: int | str, code: str, user_id: int | str) -> dict[str, Any]:
    """Einen Server freischalten.

    Gibt ``{"ok": bool, "reason": str}`` zurueck statt zu werfen: der
    Aufrufer soll die Meldung weiterreichen, nicht einen Fehlertyp
    uebersetzen muessen.
    """

    ensure()
    current = state(guild_id)

    # Ein Bann steht ueber allem. Erst pruefen, sonst koennte ein
    # gebannter Server sich mit dem richtigen Code selbst befreien.
    if current["banned"]:
        log_event(guild_id, "denied", user_id=str(user_id), detail="gebannt")
        return {
            "ok": False,
            "reason": (
                "Für diesen Server ist der Speedrun gesperrt. "
                "Das hebt kein Code auf — melde dich beim Team."
            ),
        }

    if not code_is_valid(code):
        log_event(guild_id, "denied", user_id=str(user_id),
                  detail="falscher Code")
        return {"ok": False, "reason": "Der Code stimmt nicht."}

    if current["unlocked"]:
        return {"ok": True, "reason": "", "already": True}

    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO speedrun_access "
            "(guild_id, unlocked_at, unlocked_by, code_hash) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "unlocked_at = excluded.unlocked_at, "
            "unlocked_by = excluded.unlocked_by, "
            "code_hash = excluded.code_hash",
            (str(guild_id), now, str(user_id), _hash(code)),
        )

    log_event(guild_id, "unlocked", user_id=str(user_id))
    return {"ok": True, "reason": "", "already": False}


def revoke(guild_id: int | str, actor_id: int | str = "") -> bool:
    """Die Freischaltung entziehen -- der Code muss neu eingegeben werden.

    Der Verlauf bleibt stehen. Ein Bann wird dabei *nicht* aufgehoben:
    wer einen gebannten Server entzieht, will ihn nicht entsperren.
    """

    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT banned FROM speedrun_access WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
        if row is None:
            return False
        if row["banned"]:
            # Nur die Freischaltung loeschen, den Bann behalten.
            conn.execute(
                "UPDATE speedrun_access SET unlocked_at = 0, code_hash = '' "
                "WHERE guild_id = ?",
                (str(guild_id),),
            )
        else:
            conn.execute(
                "DELETE FROM speedrun_access WHERE guild_id = ?",
                (str(guild_id),),
            )

    log_event(guild_id, "revoked", actor_id=str(actor_id))
    return True


def ban(guild_id: int | str, actor_id: int | str = "", reason: str = "") -> bool:
    """Einen Server dauerhaft sperren. Kein Code hilft mehr."""

    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO speedrun_access "
            "(guild_id, unlocked_at, unlocked_by, code_hash, "
            " banned, banned_at, banned_by, ban_reason) "
            "VALUES (?, 0, '', '', 1, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "banned = 1, banned_at = excluded.banned_at, "
            "banned_by = excluded.banned_by, ban_reason = excluded.ban_reason",
            (str(guild_id), now, str(actor_id), reason),
        )

    log_event(guild_id, "banned", actor_id=str(actor_id), detail=reason)
    return True


def unban(guild_id: int | str, actor_id: int | str = "") -> bool:
    """Den Bann aufheben.

    Der Server ist danach **nicht** automatisch frei -- der Code muss
    neu eingegeben werden. Ein Bann aufzuheben und damit gleichzeitig
    die alte Freischaltung wiederzubeleben waere ueberraschend.
    """

    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT banned FROM speedrun_access WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
        if row is None or not row["banned"]:
            return False
        conn.execute(
            "DELETE FROM speedrun_access WHERE guild_id = ?",
            (str(guild_id),),
        )

    log_event(guild_id, "unbanned", actor_id=str(actor_id))
    return True


def note_run(guild_id: int | str, user_id: int | str = "") -> None:
    """Einen gestarteten Speedrun mitzaehlen."""

    ensure()
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE speedrun_access SET runs = runs + 1, last_run_at = ? "
            "WHERE guild_id = ?",
            (now, str(guild_id)),
        )

    log_event(guild_id, "run_started", user_id=str(user_id))


def list_guilds(limit: int = 200) -> list[dict[str, Any]]:
    """Alle Server mit Zustand -- die Liste im Admin-Panel."""

    ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM speedrun_access "
            "ORDER BY banned DESC, unlocked_at DESC LIMIT ?",
            (max(1, min(limit, 1000)),),
        ).fetchall()

    return [
        {
            "guild_id": row["guild_id"],
            "unlocked": bool(row["unlocked_at"]) and not row["banned"],
            "unlocked_at": row["unlocked_at"],
            "unlocked_by": row["unlocked_by"],
            "banned": bool(row["banned"]),
            "banned_at": row["banned_at"],
            "banned_by": row["banned_by"],
            "ban_reason": row["ban_reason"] or "",
            "runs": row["runs"],
            "last_run_at": row["last_run_at"],
        }
        for row in rows
    ]


def history(guild_id: int | str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Der Verlauf -- fuer einen Server oder ueber alle."""

    ensure()
    capped = max(1, min(limit, 1000))
    with _connect() as conn:
        if guild_id:
            rows = conn.execute(
                "SELECT * FROM speedrun_access_log WHERE guild_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (str(guild_id), capped),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM speedrun_access_log ORDER BY id DESC LIMIT ?",
                (capped,),
            ).fetchall()

    return [
        {
            "id": row["id"],
            "guild_id": row["guild_id"],
            "event": row["event"],
            "user_id": row["user_id"],
            "actor_id": row["actor_id"],
            "detail": row["detail"],
            "at": row["at"],
        }
        for row in rows
    ]


def stats() -> dict[str, int]:
    """Zahlen fuer den Kopf des Admin-Panels."""

    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN banned = 1 THEN 1 ELSE 0 END) AS banned, "
            "  SUM(CASE WHEN banned = 0 AND unlocked_at > 0 THEN 1 ELSE 0 END) "
            "    AS unlocked, "
            "  SUM(runs) AS runs "
            "FROM speedrun_access"
        ).fetchone()

    return {
        "total": row["total"] or 0,
        "unlocked": row["unlocked"] or 0,
        "banned": row["banned"] or 0,
        "runs": row["runs"] or 0,
    }
