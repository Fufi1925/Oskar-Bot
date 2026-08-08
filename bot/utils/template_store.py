"""
Community-Vorlagen: einen Server einscannen, teilen, anwenden.

Die Idee
--------
Ein Server, der gut aufgesetzt ist, laesst sich einscannen: Kanaele,
Rollen, Rechte und -- wenn eingeschaltet -- die Dashboard-Einstellungen.
Daraus wird eine Vorlage, die andere auf ihren Server holen koennen.

Das ist etwas anderes als der Speedrun. Der bringt 14 fertige Vorlagen
mit, die der Template-Bot baut. Hier kommt die Vorlage von einem
echten Server, und der Hauptbot setzt sie um.

Warum die Daten hier bereinigt werden und nicht erst beim Anwenden
-------------------------------------------------------------------
Eine hochgeladene Vorlage ist oeffentlich. Steht in ihr eine
Webhook-Adresse, kann jeder, der sie sieht, in diesen Kanal schreiben
-- eine Webhook-URL *ist* das Zugangsrecht, sie braucht kein weiteres
Passwort.

Deshalb wird beim **Hochladen** bereinigt, nicht beim Anzeigen: was
gar nicht erst in der Datenbank landet, kann auch nicht versehentlich
ausgeliefert werden. Ein Fehler in der Anzeige waere sonst sofort ein
Datenleck.

Was dabei ersetzt wird
----------------------
* **IDs** (Kanal, Rolle, Nutzer, Server) -> Platzhalter wie
  ``{channel:allgemein}``. Sie waeren auf einem fremden Server ohnehin
  wertlos, und sie verraten, wo die Vorlage herkommt.
* **Webhook-Adressen, Tokens, Einladungen** -> entfernt.
* **Freitexte** bleiben. Eine Willkommensnachricht ist der halbe Sinn
  einer Vorlage.

Speicher
--------
`db/templates.db`. Braucht ein Railway-Volume, sonst sind alle
hochgeladenen Vorlagen nach dem naechsten Deploy weg.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time

import aiosqlite

DB_PATH = "db/templates.db"

# Grenzen. Sie stehen hier und nicht in der Route, damit das Dashboard
# sie abfragen und dieselben Zahlen anzeigen kann.
MAX_NAME = 80
MAX_DESCRIPTION = 500
MAX_TEMPLATES_PER_GUILD = 10
MAX_CHANNELS = 200
MAX_ROLES = 100

# Wie ein Zugangscode aussieht. Kurz genug zum Vorlesen, lang genug,
# dass Raten nichts bringt: 8 Zeichen aus 32 ergeben 2^40
# Moeglichkeiten.
KEY_LENGTH = 8
KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne I/O/0/1

SORTS = ("neu", "beliebt", "name")


# ── Bereinigung ──────────────────────────────────────────────────────

# Eine Discord-ID: 17 bis 20 Ziffern. Kuerzere Zahlen sind Zaehler,
# Zeitangaben oder Farben und muessen bleiben.
_ID_PATTERN = re.compile(r"\b\d{17,20}\b")

# Was niemals in eine oeffentliche Vorlage gehoert.
_SECRET_PATTERNS = (
    # Webhook-Adressen sind selbst das Zugangsrecht.
    re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I),
    # Bot-Tokens.
    re.compile(r"\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"),
    # Personal Access Tokens.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    # Einladungen -- sie zeigen auf den Ursprungsserver.
    re.compile(r"(?:https?://)?discord(?:\.gg|app\.com/invite)/\S+", re.I),
)

# Schluessel, deren Inhalt grundsaetzlich nicht mitgeht.
_SECRET_KEYS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwort",
        "api_key",
        "apikey",
        "webhook",
        "webhook_url",
        "access_token",
        "refresh_token",
        "client_secret",
        "invite",
        "invite_url",
    }
)


def _clean_text(value: str, id_names: dict[int, str] | None = None) -> str:
    """Einen Freitext entschaerfen.

    IDs werden zu lesbaren Platzhaltern, damit die Vorlage beim
    Anwenden wieder etwas damit anfangen kann -- und damit ein Mensch
    sieht, was gemeint war.
    """

    out = str(value)

    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[entfernt]", out)

    names = id_names or {}

    def _replace(match: re.Match) -> str:
        found = int(match.group(0))
        label = names.get(found)
        return f"{{{label}}}" if label else "{id}"

    return _ID_PATTERN.sub(_replace, out)


def sanitise(value, id_names: dict[int, str] | None = None):
    """Beliebige Daten rekursiv bereinigen.

    Arbeitet auf Dictionaries, Listen, Zeichenketten und Zahlen. Eine
    Zahl, die wie eine Discord-ID aussieht, wird ebenfalls ersetzt --
    sonst reichte es, `channel_id` als Zahl statt als Text zu
    speichern, um die Bereinigung zu umgehen.
    """

    names = id_names or {}

    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in _SECRET_KEYS):
                # Der Schluessel allein genuegt -- der Wert wird gar
                # nicht erst angesehen.
                continue
            out[key] = sanitise(inner, names)
        return out

    if isinstance(value, (list, tuple)):
        return [sanitise(item, names) for item in value]

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        # 17-20 Stellen: eine Discord-ID.
        if 10**16 <= abs(value) < 10**20:
            label = names.get(value)
            return f"{{{label}}}" if label else "{id}"
        return value

    if isinstance(value, str):
        return _clean_text(value, names)

    return value


def contains_secret(value) -> bool:
    """Steckt trotz Bereinigung noch ein Geheimnis darin?

    Die Gegenprobe nach dem Bereinigen. Faellt sie positiv aus, wird
    der Upload abgelehnt statt stillschweigend etwas durchzulassen --
    lieber eine Fehlermeldung als ein Leck.
    """

    blob = json.dumps(value, ensure_ascii=False)
    return any(pattern.search(blob) for pattern in _SECRET_PATTERNS)


# ── Zugangscodes ─────────────────────────────────────────────────────


def make_key() -> str:
    """Einen Zugangscode erzeugen.

    `secrets` statt `random`: letzteres ist vorhersagbar, sobald man
    ein paar Ausgaben kennt.
    """

    return "".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_LENGTH))


def hash_key(key: str) -> str:
    """Den Code als Hash ablegen, nicht im Klartext.

    Wer die Datenbank liest, soll damit keine fremden Vorlagen oeffnen
    koennen. Ein Salt ist hier unnoetig: die Codes sind zufaellig und
    haben genug Entropie, eine Regenbogentabelle bringt nichts.
    """

    return hashlib.sha256(key.strip().upper().encode("utf-8")).hexdigest()


# ── Schema ───────────────────────────────────────────────────────────


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            author_id INTEGER,
            author_name TEXT DEFAULT '',
            source_guild_id INTEGER,
            payload TEXT NOT NULL DEFAULT '{}',
            visibility TEXT NOT NULL DEFAULT 'public',
            key_hash TEXT,
            uses INTEGER DEFAULT 0,
            created_at REAL DEFAULT 0,
            updated_at REAL DEFAULT 0
        )
        """
    )
    # Ohne Index liest jede Suche die ganze Tabelle.
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_templates_visibility "
        "ON templates (visibility, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_templates_guild "
        "ON templates (source_guild_id)"
    )
    # Wer hat wann was angewendet -- fuer den Verlauf und um
    # Missbrauch nachvollziehen zu koennen.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS template_applies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            actor_id INTEGER,
            options TEXT DEFAULT '{}',
            wiped INTEGER DEFAULT 0,
            created_at REAL DEFAULT 0
        )
        """
    )
    await db.commit()


# ── Lesen ────────────────────────────────────────────────────────────


def _row_to_template(row, *, with_payload: bool, unlocked: bool) -> dict:
    """Eine Zeile in die Form bringen, die das Dashboard erwartet.

    `unlocked` entscheidet ueber den Inhalt: eine Vorlage mit Code
    zeigt ohne diesen nur Name, Beschreibung und Zahlen. Die Vorschau
    -- und damit die Kanal- und Rollennamen -- bleibt verschlossen.
    Das ist der Sinn eines Codes; wuerde die Vorschau trotzdem
    ausgeliefert, waere er reine Zierde.
    """

    locked = bool(row["key_hash"]) and not unlocked

    payload = {}
    if with_payload and not locked:
        try:
            payload = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            payload = {}

    summary = {"channels": 0, "roles": 0, "categories": 0, "features": 0}
    if not locked:
        try:
            raw = json.loads(row["payload"] or "{}")
            summary = {
                "channels": len(raw.get("channels") or []),
                "roles": len(raw.get("roles") or []),
                "categories": len(raw.get("categories") or []),
                "features": len(raw.get("features") or {}),
            }
        except (TypeError, ValueError):
            pass

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "author_name": row["author_name"] or "",
        "visibility": row["visibility"],
        "locked": locked,
        "uses": int(row["uses"] or 0),
        "created_at": row["created_at"],
        "summary": summary,
        "payload": payload,
    }


async def list_templates(
    db: aiosqlite.Connection,
    *,
    search: str = "",
    sort: str = "neu",
    limit: int = 50,
) -> list[dict]:
    """Die oeffentliche Liste.

    Vorlagen mit Code stehen mit drin -- man soll ja sehen, dass es
    sie gibt -- aber ohne Vorschau.
    """

    order = {
        "neu": "created_at DESC",
        "beliebt": "uses DESC, created_at DESC",
        "name": "name COLLATE NOCASE",
    }.get(sort, "created_at DESC")

    db.row_factory = aiosqlite.Row

    if search.strip():
        needle = f"%{search.strip()}%"
        query = (
            "SELECT * FROM templates WHERE visibility != 'private' "
            "AND (name LIKE ? OR description LIKE ?) "
            f"ORDER BY {order} LIMIT ?"
        )
        args = (needle, needle, int(limit))
    else:
        query = (
            "SELECT * FROM templates WHERE visibility != 'private' "
            f"ORDER BY {order} LIMIT ?"
        )
        args = (int(limit),)

    async with db.execute(query, args) as cursor:
        rows = await cursor.fetchall()

    return [_row_to_template(r, with_payload=False, unlocked=False) for r in rows]


async def list_own(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    """Was dieser Server selbst hochgeladen hat -- immer sichtbar."""

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM templates WHERE source_guild_id = ? ORDER BY created_at DESC",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    return [_row_to_template(r, with_payload=False, unlocked=True) for r in rows]


async def get_template(
    db: aiosqlite.Connection,
    template_id: int,
    *,
    key: str | None = None,
    owner_guild_id: int | None = None,
) -> dict | None:
    """Eine einzelne Vorlage, mit Vorschau wenn erlaubt.

    Erlaubt ist sie, wenn die Vorlage offen ist, der richtige Code
    kommt, oder der fragende Server sie selbst hochgeladen hat.
    """

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM templates WHERE id = ?", (template_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None

    unlocked = not row["key_hash"]
    if not unlocked and key:
        unlocked = hash_key(key) == row["key_hash"]
    if not unlocked and owner_guild_id is not None:
        unlocked = row["source_guild_id"] == owner_guild_id

    return _row_to_template(row, with_payload=True, unlocked=unlocked)


async def count_for_guild(db: aiosqlite.Connection, guild_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM templates WHERE source_guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


# ── Schreiben ────────────────────────────────────────────────────────


async def create_template(
    db: aiosqlite.Connection,
    *,
    name: str,
    description: str,
    author_id: int | None,
    author_name: str,
    source_guild_id: int,
    payload: dict,
    visibility: str = "public",
    key: str | None = None,
) -> tuple[int, str | None]:
    """Eine Vorlage anlegen. Gibt (id, Klartext-Code oder None).

    Der Code wird genau einmal zurueckgegeben -- danach steht in der
    Datenbank nur noch sein Hash. Wer ihn verliert, muss die Vorlage
    neu hochladen; das ist unbequem, aber besser als ein Code, den
    jeder mit Datenbankzugriff lesen kann.
    """

    now = time.time()
    plain_key = None
    key_hash = None

    if visibility == "key":
        plain_key = (key or "").strip().upper() or make_key()
        key_hash = hash_key(plain_key)

    cursor = await db.execute(
        """
        INSERT INTO templates
            (name, description, author_id, author_name, source_guild_id,
             payload, visibility, key_hash, uses, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            str(name or "Ohne Namen")[:MAX_NAME],
            str(description or "")[:MAX_DESCRIPTION],
            author_id,
            str(author_name or "")[:80],
            source_guild_id,
            json.dumps(payload, ensure_ascii=False),
            visibility if visibility in ("public", "key", "private") else "public",
            key_hash,
            now,
            now,
        ),
    )
    await db.commit()
    return int(cursor.lastrowid), plain_key


async def delete_template(
    db: aiosqlite.Connection, template_id: int, guild_id: int
) -> bool:
    """Loeschen -- nur die eigenen.

    Die IDs sind fortlaufend und damit trivial zu raten. Ohne
    `source_guild_id` im WHERE koennte jeder Server jede fremde
    Vorlage entfernen.
    """

    cursor = await db.execute(
        "DELETE FROM templates WHERE id = ? AND source_guild_id = ?",
        (template_id, guild_id),
    )
    await db.commit()
    return bool(cursor.rowcount)


async def bump_uses(db: aiosqlite.Connection, template_id: int) -> None:
    await db.execute(
        "UPDATE templates SET uses = uses + 1 WHERE id = ?", (template_id,)
    )
    await db.commit()


async def log_apply(
    db: aiosqlite.Connection,
    *,
    template_id: int,
    guild_id: int,
    actor_id: int | None,
    options: dict,
    wiped: bool,
) -> None:
    await db.execute(
        "INSERT INTO template_applies "
        "(template_id, guild_id, actor_id, options, wiped, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            template_id,
            guild_id,
            actor_id,
            json.dumps(options, ensure_ascii=False),
            1 if wiped else 0,
            time.time(),
        ),
    )
    await db.commit()
