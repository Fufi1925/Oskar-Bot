"""Sitzungen, Modul-Konfiguration und Laufzeitdaten des LBoost Shops.

Ein Detail, das hier den Unterschied macht: ``sqlite3.Connection`` schliesst
in einem ``with``-Block *nicht*. Der Block committet oder verwirft nur. Wer
pro Aufruf eine Verbindung öffnet und ``with`` schreibt, ließ bisher eine
offene Datei zurück — 150 ``get_feature``-Aufrufe waren 150 offene
Datei-Deskriptoren, und der Bot liest die Konfiguration bei jedem Event.
Unter Last war der Prozess nach einigen Minuten beim Datei-Descriptor-Limit.
Deshalb hier ein Kontextmanager, der garantiert schliesst, dazu ein
Verbindungspool pro Thread, damit nicht jedes Log eine neue SQLite-Datei
öffnet.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet, InvalidToken

from lbost_shop_app.config import Settings

_schema_lock = threading.RLock()
_schema_ready: set[str] = set()
#: Pfade, an denen das Schema gerade aufgebaut wird. Ohne diese Markierung
#: ruft init_features ueber _verbinden wieder init_features auf und laeuft in
#: einen toerkopften Rueckwaertslauf (Lock nicht reentrant) — der Test hing
#: genau dort, weil das derselbe Thread war.
_schema_aktiv: set[str] = set()
_thread_local = threading.local()

#: Wie lange Einträge im Änderungsverlauf bleiben (Tage).
AUDIT_TAGE = 45


# ── Anschluss und Schema ────────────────────────────────────────────────
def _verbinden(settings: Settings) -> sqlite3.Connection:
    """Wiederverwendete Verbindung pro Thread und Datei.

    WAL ist dauerhaft in der Datei gesetzt, die Pragmas müssen also nicht
    jeden Aufruf überleben — wohl aber ``busy_timeout``, damit Bot und
    Dashboard gleichzeitige Schreibversuche nicht mit ``database is locked``
    abbrechen.
    """
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schluessel = (str(path.resolve()), threading.get_ident())
    pool = getattr(_thread_local, "pool", None)
    if pool is None:
        pool = _thread_local.pool = {}
    conn = pool.get(schluessel)
    if conn is not None:
        return conn
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    pool[schluessel] = conn
    # Kein Aufrufer muss mehr ans Schema denken: init_features erkennt, ob es
    # schon steht oder gerade aufgebaut wird, und kommt dann sofort zurück.
    init_features(settings)
    return conn


@contextlib.contextmanager
def _gesichert(settings: Settings) -> Iterator[sqlite3.Connection]:
    """Verbindung liefern, committen und Fehler sauber zurückrollen.

    ``with verbindung:`` bei sqlite3 committet am Ende des Blocks — ein
    eigener Kontextmanager, der das vergisst, schreibt in die Verbindung
    hinein und für jeden anderen Prozess ins Leere. Der Bot hätte seine
    Tickets nie gesehen, was genau hier getestet wird.
    """
    conn = _verbinden(settings)
    try:
        yield conn
    except Exception:
        with contextlib.suppress(sqlite3.Error):
            conn.rollback()
        raise
    else:
        conn.commit()


def _spalte_hinzufuegen(conn: sqlite3.Connection, tabelle: str, spalte: str, typ: str) -> None:
    """ALTER TABLE, das zweimal gefahrlos laufen kann (Migration bei jedem Start)."""
    vorhanden = {row[1] for row in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}
    if spalte not in vorhanden:
        conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")


def _connect(settings: Settings) -> sqlite3.Connection:
    """Nur noch für Lesungen ohne Schreibbedarf; der Aufrufer muss nicht closen."""
    return _verbinden(settings)


def init_features(settings: Settings) -> None:
    """Tabellen anlegen und alte Zeilen missing-safe erweitern. Idempotent."""
    pfad = str(Path(settings.db_path).resolve())
    if pfad in _schema_ready or pfad in _schema_aktiv:
        return
    with _schema_lock:
        if pfad in _schema_ready or pfad in _schema_aktiv:
            return
        _schema_aktiv.add(pfad)
        try:
            with _gesichert(settings) as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS oauth_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    access_token BLOB NOT NULL,
                    refresh_token BLOB NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_shop_sessions_user ON oauth_sessions(user_id);

                CREATE TABLE IF NOT EXISTS guild_features (
                    guild_id INTEGER NOT NULL,
                    feature TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, feature)
                );
                CREATE TABLE IF NOT EXISTS guild_state (
                    guild_id INTEGER NOT NULL,
                    state_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, state_key)
                );
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL, reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL, channel_id INTEGER UNIQUE NOT NULL,
                    owner_id INTEGER NOT NULL, panel_key TEXT NOT NULL,
                    claimed_by INTEGER, status TEXT NOT NULL DEFAULT 'open',
                    created_at INTEGER NOT NULL, closed_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS giveaways (
                    message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL, prize TEXT NOT NULL,
                    winners INTEGER NOT NULL, ends_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', winner_ids TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    message_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    PRIMARY KEY(message_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS feature_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL, details TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS discord_event_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    channel_id INTEGER,
                    user_id INTEGER,
                    created_at INTEGER NOT NULL
                );
                """)
                # Ältere Bestände bekamen diese Spalten nie; ohne ALTER hätte der
                # Bot beim ersten Ticket danach mit "no such column" verloren.
                _spalte_hinzufuegen(conn, "tickets", "ticket_number", "INTEGER NOT NULL DEFAULT 0")
                _spalte_hinzufuegen(conn, "tickets", "answers_json", "TEXT NOT NULL DEFAULT ''")
                _spalte_hinzufuegen(conn, "tickets", "closed_by", "INTEGER")
                _spalte_hinzufuegen(conn, "warnings", "case_number", "INTEGER NOT NULL DEFAULT 0")
                _spalte_hinzufuegen(conn, "giveaways", "required_role_id", "INTEGER NOT NULL DEFAULT 0")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id,status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id,user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_guild_time ON feature_audit(guild_id,created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_shop_event_logs_guild_time ON discord_event_logs(guild_id,created_at DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_shop_event_logs_category ON discord_event_logs(guild_id,category,created_at DESC)")
                # scheduled_jobs war der geplante Weg für Ankündigungen; der Bot
                # nutzt jetzt guild_state. Die Tabelle bleibt zum Exportieren.
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL, kind TEXT NOT NULL,
                    channel_id INTEGER NOT NULL, content TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL, next_run INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                """)
        finally:
            # Auch ein fehlgeschlagener Aufbau darf den Pfad nicht für
            # immer als 'wird gerade gebaut' blockieren.
            _schema_aktiv.discard(pfad)
        _schema_ready.add(pfad)


def reset_schema_cache() -> None:
    """Nur für Tests: Schema-Markierung vergessen (neue DB-Datei pro Test)."""
    with _schema_lock:
        _schema_ready.clear()
        _schema_aktiv.clear()


# ── OAuth-Sitzungen ─────────────────────────────────────────────────────
def _fernet(settings: Settings) -> Fernet:
    raw = settings.token_encryption_key.strip() or settings.signing_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def save_oauth_session(session_id: str, user_id: int, token: dict[str, Any], settings: Settings) -> None:
    _connect(settings)
    cipher = _fernet(settings)
    now = int(time.time())
    expires_at = now + max(60, int(token.get("expires_in") or 604800))
    access = cipher.encrypt(str(token.get("access_token") or "").encode())
    refresh = cipher.encrypt(str(token.get("refresh_token") or "").encode())
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO oauth_sessions
               (session_id,user_id,access_token,refresh_token,expires_at,created_at,last_seen_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, user_id, access, refresh, expires_at, now, now),
        )


def load_oauth_session(session_id: str, user_id: int, settings: Settings) -> dict[str, Any] | None:
    _connect(settings)
    with _gesichert(settings) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE oauth_sessions SET last_seen_at=? WHERE session_id=?", (int(time.time()), session_id))
    try:
        cipher = _fernet(settings)
        return {
            "access_token": cipher.decrypt(row["access_token"]).decode(),
            "refresh_token": cipher.decrypt(row["refresh_token"]).decode(),
            "expires_at": int(row["expires_at"]),
        }
    except (InvalidToken, UnicodeDecodeError):
        delete_oauth_session(session_id, settings)
        return None


def delete_oauth_session(session_id: str, settings: Settings) -> None:
    if not session_id:
        return
    with _gesichert(settings) as conn:
        conn.execute("DELETE FROM oauth_sessions WHERE session_id=?", (session_id,))


def purge_expired(settings: Settings) -> None:
    cutoff = int(time.time()) - settings.session_max_age
    with _gesichert(settings) as conn:
        conn.execute("DELETE FROM oauth_sessions WHERE last_seen_at < ?", (cutoff,))


def offene_sitzungen(settings: Settings) -> list[dict[str, Any]]:
    """Für das Admin-Panel: wer ist gerade eingeloggt (ohne Token-Inhalte)."""
    _connect(settings)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            """SELECT session_id, user_id, created_at, last_seen_at, expires_at
               FROM oauth_sessions ORDER BY last_seen_at DESC LIMIT 50"""
        ).fetchall()
    out = []
    for row in rows:
        out.append({
            "session_id": str(row["session_id"]),
            "kurz": str(row["session_id"])[:6],
            "user_id": int(row["user_id"]),
            "erstellt": int(row["created_at"]),
            "zuletzt": int(row["last_seen_at"]),
            "laeuft_ab": int(row["expires_at"]),
        })
    return out


def alle_sitzungen_loeschen(settings: Settings) -> int:
    with _gesichert(settings) as conn:
        cursor = conn.execute("DELETE FROM oauth_sessions")
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


# ── Modul-Konfiguration ────────────────────────────────────────────────
def get_feature(guild_id: int, feature: str, settings: Settings) -> dict[str, Any]:
    _connect(settings)
    with _gesichert(settings) as conn:
        row = conn.execute(
            "SELECT data_json FROM guild_features WHERE guild_id=? AND feature=?",
            (guild_id, feature),
        ).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row["data_json"])
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def set_feature(
    guild_id: int,
    feature: str,
    data: dict[str, Any],
    actor_id: int,
    settings: Settings,
    *,
    audit: bool = True,
) -> None:
    """Konfiguration speichern.

    ``audit``: Der Bot schreibt Laufzeug (etwa den nächsten Sendelauf einer
    Ankündigung) ohne Vermerk. Zuvor zählte jedes dieser Schreiben als
    "Änderung im Dashboard" und stand dann im 14-Tage-Verlauf des Servers —
    der Graph zeigte den Bot statt der Menschen.
    """
    _connect(settings)
    now = int(time.time())
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT INTO guild_features(guild_id,feature,data_json,updated_at)
               VALUES(?,?,?,?) ON CONFLICT(guild_id,feature)
               DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at""",
            (guild_id, feature, payload, now),
        )
        if audit:
            conn.execute(
                "INSERT INTO feature_audit(guild_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                (guild_id, actor_id, f"configure:{feature}", payload[:2000], now),
            )


def all_features(guild_id: int, settings: Settings) -> dict[str, dict[str, Any]]:
    _connect(settings)
    result: dict[str, dict[str, Any]] = {}
    with _gesichert(settings) as conn:
        rows = conn.execute("SELECT feature,data_json FROM guild_features WHERE guild_id=?", (guild_id,)).fetchall()
    for row in rows:
        try:
            value = json.loads(row["data_json"])
            result[row["feature"]] = value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            result[row["feature"]] = {}
    return result


def prune_audit(settings: Settings, tage: int = AUDIT_TAGE) -> int:
    """Verlauf verkleinern; ohne das wuchs feature_audit unendlich."""
    _connect(settings)
    cutoff = int(time.time()) - max(1, int(tage)) * 86400
    with _gesichert(settings) as conn:
        cursor = conn.execute("DELETE FROM feature_audit WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM feature_audit WHERE id NOT IN (SELECT id FROM feature_audit ORDER BY created_at DESC LIMIT 5000)")
    return cursor.rowcount or 0


def feature_history(guild_id: int, settings: Settings, days: int = 14) -> list[dict[str, Any]]:
    """Tägliche Konfigurationsänderungen für den Verlaufsgraphen."""
    _connect(settings)
    start = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS amount
               FROM feature_audit WHERE guild_id=? AND created_at>=?
               GROUP BY day""",
            (guild_id, int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())),
        ).fetchall()
    amounts = {str(row["day"]): int(row["amount"]) for row in rows}
    points = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        points.append({"day": day.strftime("%d.%m"), "amount": amounts.get(day.isoformat(), 0)})
    maximum = max((point["amount"] for point in points), default=0) or 1
    for point in points:
        # Aufgerundet, damit ein einzelner Punkt sichtbar bleibt; die Höhe
        # landet in einer CSS-Klasse, nicht in einem style-Attribut — die
        # Content-Security-Policy des Shops verbietet Inline-Styles.
        point["prozent"] = max(6, min(100, round(point["amount"] / maximum * 100)))
        point["height"] = point["prozent"]
    return points


def konfigurations_uebersicht(settings: Settings) -> dict[str, int]:
    """Wie viele Server etwas konfiguriert haben und wie oft."""
    _connect(settings)
    with _gesichert(settings) as conn:
        server = conn.execute("SELECT COUNT(DISTINCT guild_id) AS anzahl FROM guild_features").fetchone()
        zeilen = conn.execute("SELECT COUNT(*) AS anzahl FROM guild_features").fetchone()
        aenderungen = conn.execute("SELECT COUNT(*) AS anzahl FROM feature_audit").fetchone()
        ticktes = conn.execute("SELECT COUNT(*) AS anzahl FROM tickets").fetchone()
        warnungen = conn.execute("SELECT COUNT(*) AS anzahl FROM warnings").fetchone()
    return {
        "server": int(server["anzahl"]),
        "konfigurationen": int(zeilen["anzahl"]),
        "aenderungen": int(aenderungen["anzahl"]),
        "tickets": int(ticktes["anzahl"]),
        "warnungen": int(warnungen["anzahl"]),
    }


def letzte_aenderungen(settings: Settings, grenze: int = 25) -> list[dict[str, Any]]:
    _connect(settings)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            """SELECT guild_id, actor_id, action, created_at FROM feature_audit
               ORDER BY created_at DESC LIMIT ?""",
            (max(1, min(100, int(grenze))),),
        ).fetchall()
    return [
        {"guild_id": int(row["guild_id"]), "actor_id": int(row["actor_id"]),
         "action": str(row["action"]), "created_at": int(row["created_at"])}
        for row in rows
    ]


# ── Laufzeit-Zustand (Bot schreibt, Dashboard liest) ────────────────────
def set_state(guild_id: int, schluessel: str, wert: Any, settings: Settings) -> None:
    _connect(settings)
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT INTO guild_state(guild_id,state_key,value_json,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(guild_id,state_key)
               DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
            (guild_id, schluessel, json.dumps(wert, ensure_ascii=False)[:4000], int(time.time())),
        )


def get_state(guild_id: int, schluessel: str, settings: Settings) -> Any | None:
    _connect(settings)
    with _gesichert(settings) as conn:
        row = conn.execute(
            "SELECT value_json, updated_at FROM guild_state WHERE guild_id=? AND state_key=?",
            (guild_id, schluessel),
        ).fetchone()
    if not row:
        return None
    try:
        return {"wert": json.loads(row["value_json"]), "updated_at": int(row["updated_at"])}
    except (TypeError, ValueError):
        return None


def alle_state(settings: Settings, praefix: str = "") -> dict[tuple[int, str], Any]:
    _connect(settings)
    with _gesichert(settings) as conn:
        if praefix:
            zeilen = conn.execute(
                "SELECT guild_id, state_key, value_json FROM guild_state WHERE state_key LIKE ?",
                (f"{praefix}%",),
            ).fetchall()
        else:
            zeilen = conn.execute("SELECT guild_id, state_key, value_json FROM guild_state").fetchall()
    out: dict[tuple[int, str], Any] = {}
    for row in zeilen:
        try:
            out[(int(row["guild_id"]), str(row["state_key"]))] = json.loads(row["value_json"])
        except (TypeError, ValueError):
            continue
    return out


# ── Tickets ─────────────────────────────────────────────────────────────
def offene_tickets_fuer_nutzer(guild_id: int, user_id: int, settings: Settings) -> int | None:
    _connect(settings)
    with _gesichert(settings) as conn:
        row = conn.execute(
            "SELECT channel_id FROM tickets WHERE guild_id=? AND owner_id=? AND status='open'",
            (guild_id, user_id),
        ).fetchone()
    return int(row["channel_id"]) if row else None


def naechste_ticket_nummer(guild_id: int, settings: Settings) -> int:
    with _gesichert(settings) as conn:
        row = conn.execute("SELECT COUNT(*) AS anzahl FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()
    return int(row["anzahl"]) + 1


def ticket_anlegen(guild_id: int, channel_id: int, owner_id: int, panel_key: str,
                   nummer: int, answers: list[dict[str, Any]], settings: Settings) -> None:
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tickets(guild_id,channel_id,owner_id,panel_key,status,created_at,ticket_number,answers_json)
               VALUES(?,?,?,?,'open',?,?,?)""",
            (guild_id, channel_id, owner_id, panel_key, int(time.time()), nummer,
             json.dumps(answers or [], ensure_ascii=False)[:8000]),
        )


def ticket_fuer_kanal(channel_id: int, settings: Settings) -> dict[str, Any] | None:
    _connect(settings)
    with _gesichert(settings) as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    return dict(row) if row else None


def ticket_setzen(channel_id: int, settings: Settings, **felder: Any) -> None:
    erlaubt = {"status", "claimed_by", "closed_at", "closed_by", "answers_json"}
    felder = {k: v for k, v in felder.items() if k in erlaubt}
    if not felder:
        return
    setzung = ", ".join(f"{name}=?" for name in felder)
    with _gesichert(settings) as conn:
        conn.execute(f"UPDATE tickets SET {setzung} WHERE channel_id=?", (*felder.values(), channel_id))


def tickets_fuer_gilde(guild_id: int, settings: Settings, grenze: int = 25) -> list[dict[str, Any]]:
    _connect(settings)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            """SELECT channel_id, owner_id, panel_key, status, claimed_by, created_at, closed_at, ticket_number
               FROM tickets WHERE guild_id=? ORDER BY created_at DESC, id DESC LIMIT ?""",
            (guild_id, max(1, min(100, int(grenze)))),
        ).fetchall()
    return [dict(row) for row in rows]


def ticket_kennzahlen(guild_id: int, settings: Settings) -> dict[str, int]:
    _connect(settings)
    with _gesichert(settings) as conn:
        gesamt = conn.execute(
            "SELECT status, COUNT(*) AS anzahl FROM tickets WHERE guild_id=? GROUP BY status", (guild_id,)
        ).fetchall()
        beansprucht = conn.execute(
            "SELECT COUNT(*) AS anzahl FROM tickets WHERE guild_id=? AND status='open' AND claimed_by IS NOT NULL",
            (guild_id,),
        ).fetchone()
        offen = conn.execute(
            """SELECT COUNT(*) AS anzahl FROM tickets WHERE guild_id=? AND status='open'
               AND created_at >= ?""",
            (guild_id, int(time.time()) - 7 * 86400),
        ).fetchone()
    nach_status = {str(row["status"]): int(row["anzahl"]) for row in gesamt}
    return {
        "offen": nach_status.get("open", 0),
        "beansprucht": int(beansprucht["anzahl"]),
        "neu_7_tage": int(offen["anzahl"]),
        "geschlossen": nach_status.get("closed", 0),
        "geloescht": nach_status.get("deleted", 0),
        "gesamt": sum(nach_status.values()),
    }


# ── Verwarnungen ────────────────────────────────────────────────────────
def warnung_anlegen(guild_id: int, user_id: int, moderator_id: int, grund: str,
                    settings: Settings) -> int:
    now = int(time.time())
    with _gesichert(settings) as conn:
        row = conn.execute("SELECT COUNT(*) AS anzahl FROM warnings WHERE guild_id=?", (guild_id,)).fetchone()
        case = int(row["anzahl"]) + 1
        conn.execute(
            "INSERT INTO warnings(guild_id,user_id,moderator_id,reason,created_at,case_number) VALUES(?,?,?,?,?,?)",
            (guild_id, user_id, moderator_id, grund[:1000], now, case),
        )
    return case


def warnungen_fuer_gilde(guild_id: int, settings: Settings, grenze: int = 50) -> list[dict[str, Any]]:
    _connect(settings)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            """SELECT id, user_id, moderator_id, reason, created_at, case_number
               FROM warnings WHERE guild_id=? ORDER BY created_at DESC, id DESC LIMIT ?""",
            (guild_id, max(1, min(200, int(grenze)))),
        ).fetchall()
    return [dict(row) for row in rows]


def warnungen_fuer_nutzer(guild_id: int, user_id: int, settings: Settings) -> int:
    with _gesichert(settings) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS anzahl FROM warnings WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        ).fetchone()
    return int(row["anzahl"])


def warnung_loeschen(guild_id: int, warnung_id: int, settings: Settings) -> bool:
    with _gesichert(settings) as conn:
        cursor = conn.execute("DELETE FROM warnings WHERE guild_id=? AND id=?", (guild_id, warnung_id))
    return bool(cursor.rowcount)


# ── Giveaways ───────────────────────────────────────────────────────────
def giveaway_anlegen(message_id: int, guild_id: int, channel_id: int, prize: str,
                     winners: int, ends_at: int, settings: Settings,
                     required_role_id: int = 0) -> None:
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO giveaways
               (message_id,guild_id,channel_id,prize,winners,ends_at,status,winner_ids,required_role_id)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (message_id, guild_id, channel_id, prize[:500], winners, ends_at, "active", "[]", required_role_id),
        )


def giveaway_teilnehmer(message_id: int, settings: Settings) -> list[int]:
    with _gesichert(settings) as conn:
        rows = conn.execute("SELECT user_id FROM giveaway_entries WHERE message_id=?", (message_id,)).fetchall()
    return [int(row["user_id"]) for row in rows]


def giveaway_beitreten(message_id: int, user_id: int, settings: Settings) -> str:
    """Teilnahme mit Prüfungen, die der Bot vorher nicht hatte.

    Rückgabe ist ein Schlüssel für die Meldung, die der Nutzer sieht.
    """
    now = int(time.time())
    with _gesichert(settings) as conn:
        row = conn.execute("SELECT status, ends_at FROM giveaways WHERE message_id=?", (message_id,)).fetchone()
        if not row:
            return "unbekannt"
        if str(row["status"]) != "active":
            return "beendet"
        if int(row["ends_at"]) <= now:
            return "beendet"
        vorhanden = conn.execute(
            "SELECT 1 FROM giveaway_entries WHERE message_id=? AND user_id=?", (message_id, user_id)
        ).fetchone()
        conn.execute("INSERT OR IGNORE INTO giveaway_entries(message_id,user_id) VALUES(?,?)", (message_id, user_id))
    return "bereits" if vorhanden else "beitritt"


def giveaway_belegen(message_id: int, settings: Settings) -> dict[str, Any] | None:
    """Zeile holen UND auf 'ending' setzen — in einem Schreibvorgang.

    Zwei Läufe desselben Workers (oder ein Reload während des Laufes) konnten
    sonst denselben Wettbewerb zweimal auflösen und doppelte Gewinner
    posten.
    """
    with _gesichert(settings) as conn:
        cursor = conn.execute("UPDATE giveaways SET status='ending' WHERE message_id=? AND status='active'", (message_id,))
        if not cursor.rowcount:
            conn.execute("UPDATE giveaways SET status='ended' WHERE message_id=? AND status='ending' AND ends_at < ?",
                         (message_id, int(time.time()) - 900))
            return None
        row = conn.execute("SELECT * FROM giveaways WHERE message_id=?", (message_id,)).fetchone()
    return dict(row) if row else None


def giveaway_abschliessen(message_id: int, winner_ids: list[int], settings: Settings) -> None:
    with _gesichert(settings) as conn:
        conn.execute("UPDATE giveaways SET status='ended', winner_ids=? WHERE message_id=?",
                     (json.dumps(winner_ids), message_id))


def giveaways_fuer_gilde(guild_id: int, settings: Settings, grenze: int = 25) -> list[dict[str, Any]]:
    _connect(settings)
    with _gesichert(settings) as conn:
        rows = conn.execute(
            "SELECT message_id, channel_id, prize, winners, ends_at, status, winner_ids FROM giveaways WHERE guild_id=? ORDER BY ends_at DESC LIMIT ?",
            (guild_id, max(1, min(100, int(grenze)))),
        ).fetchall()
    return [dict(row) for row in rows]


# ── Durchsuchbares Discord-Ereignisarchiv ───────────────────────────────
def add_event_log(
    guild_id: int,
    category: str,
    title: str,
    description: str,
    channel_id: int | None,
    user_id: int | None,
    settings: Settings,
) -> None:
    """Ein Discord-Ereignis speichern und Einträge nach 30 Tagen entfernen."""
    now = int(time.time())
    with _gesichert(settings) as conn:
        conn.execute(
            """INSERT INTO discord_event_logs
               (guild_id,category,title,description,channel_id,user_id,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (guild_id, category, title[:200], description[:4000], channel_id, user_id, now),
        )
        conn.execute("DELETE FROM discord_event_logs WHERE created_at < ?", (now - 30 * 86400,))


def search_event_logs(
    guild_id: int,
    settings: Settings,
    *,
    query: str = "",
    category: str = "",
    since: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = ["guild_id=?", "created_at>=?"]
    values: list[Any] = [guild_id, since]
    if category:
        clauses.append("category=?")
        values.append(category)
    if query:
        clauses.append("(title LIKE ? OR description LIKE ?)")
        pattern = f"%{query[:200]}%"
        values.extend((pattern, pattern))
    values.append(max(1, min(1000, limit)))
    with _gesichert(settings) as conn:
        rows = conn.execute(
            "SELECT * FROM discord_event_logs WHERE " + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [dict(row) for row in rows]


def clear_event_logs(guild_id: int, settings: Settings) -> None:
    with _gesichert(settings) as conn:
        conn.execute("DELETE FROM discord_event_logs WHERE guild_id=?", (guild_id,))
