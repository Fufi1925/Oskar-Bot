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

import base64
import hashlib
import json
import os
import re
import secrets
import time

import aiosqlite

DB_PATH = "db/templates.db"

# Wo der Schluessel liegt, mit dem die Zugangscodes verschluesselt
# werden. Liegt neben der Datenbank, damit dasselbe Railway-Volume
# beides traegt -- ein Code, dessen Schluessel beim naechsten Deploy
# weg ist, waere nicht wiederherstellbar.
SECRET_FILE = "db/template_secret.key"

# Umgebungsvariable hat Vorrang. Wer den Schluessel lieber selbst
# verwaltet, setzt sie; sonst legt der Bot beim ersten Mal eine Datei
# an.
SECRET_ENV = "TEMPLATE_KEY_SECRET"

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

    Der Hash bleibt die Pruefinstanz: beim Oeffnen einer fremden
    Vorlage wird gehasht und verglichen, nie entschluesselt.
    """

    return hashlib.sha256(key.strip().upper().encode("utf-8")).hexdigest()


# ── Den eigenen Code wieder anzeigen ─────────────────────────────────
#
# Bisher war der Code nach dem Hochladen fuer immer weg -- nur der
# Hash lag in der Datenbank, und ein Hash laesst sich nicht
# zurueckrechnen. Wer ihn verlor, musste die Vorlage neu hochladen.
#
# Jetzt liegt zusaetzlich eine *verschluesselte* Kopie daneben. Zwei
# Dinge sind dabei wichtig:
#
#   * Der Hash bleibt. Geprueft wird weiter ueber ihn, nie ueber die
#     Entschluesselung -- sonst haette ein Fehler in der Krypto sofort
#     jede Vorlage geoeffnet.
#   * Entschluesselt wird nur fuer den Server, der die Vorlage
#     hochgeladen hat, und fuer die Bot-Admins. Die Route prueft das,
#     bevor sie hierher kommt.
#
# Warum keine Bibliothek
# ----------------------
# `cryptography` steht nicht in den Abhaengigkeiten des Bots, und
# dafuer eine 10-MB-Abhaengigkeit mit C-Erweiterung nachzuziehen waere
# unverhaeltnismaessig. Was hier gebraucht wird, ist genau ein kurzer
# Text: AES-CTR von Hand ist gefaehrlich, ein Schluesselstrom aus
# SHA-256 plus HMAC-Signatur dagegen ist mit der Standardbibliothek
# vollstaendig und ohne Fussangeln zu bauen -- dasselbe Muster, das
# Fernet innen verwendet.


def _secret() -> bytes:
    """Der Hauptschluessel. Wird beim ersten Aufruf angelegt.

    Aus der Umgebung, wenn dort einer steht; sonst aus einer Datei
    neben der Datenbank. Ohne beides waere jeder Neustart ein neuer
    Schluessel und alle gespeicherten Codes Datenmuell.
    """

    from_env = os.environ.get(SECRET_ENV, "").strip()
    if from_env:
        return hashlib.sha256(from_env.encode("utf-8")).digest()

    try:
        if os.path.isfile(SECRET_FILE):
            with open(SECRET_FILE, "rb") as handle:
                raw = handle.read().strip()
            if len(raw) >= 32:
                return hashlib.sha256(raw).digest()
    except OSError:
        pass

    raw = secrets.token_bytes(48)
    try:
        folder = os.path.dirname(SECRET_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        # 0600: nur der Bot selbst. Auf Railway laeuft ohnehin nur ein
        # Prozess, aber ein weltlesbarer Schluessel neben der Datenbank
        # waere schlicht schlampig.
        handle = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "wb") as file:
            file.write(raw)
    except OSError:
        # Kein Schreibrecht: dann eben nur fuer diesen Lauf. Die
        # gespeicherten Codes lassen sich danach nicht mehr anzeigen,
        # aber nichts geht kaputt -- der Hash prueft weiter.
        pass
    return hashlib.sha256(raw).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Schluesselstrom aus SHA-256 im Zaehlerbetrieb."""

    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(
            key + nonce + counter.to_bytes(4, "big")
        ).digest()
        counter += 1
    return bytes(out[:length])


def encrypt_key(plain: str) -> str:
    """Den Code verschluesselt ablegen. Gibt einen Text fuer die DB."""

    import hmac

    if not plain:
        return ""

    key = _secret()
    nonce = secrets.token_bytes(16)
    data = plain.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    # Signatur ueber Nonce UND Text: ohne sie liesse sich der
    # Chiffretext bitweise veraendern, und beim Entschluesseln kaeme
    # unbemerkt etwas anderes heraus.
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")


def decrypt_key(blob: str) -> str | None:
    """Zurueck in Klartext. None, wenn das nicht geht.

    »Geht nicht« heisst: der Hauptschluessel hat gewechselt, der
    Eintrag stammt noch aus der Zeit ohne Verschluesselung, oder
    jemand hat daran herumgeschraubt. In allen drei Faellen ist None
    die richtige Antwort -- die Oberflaeche sagt dann ehrlich, dass
    der Code nicht mehr anzeigbar ist.
    """

    import hmac

    if not blob:
        return None

    try:
        raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None

    if len(raw) < 32:
        return None

    nonce, tag, cipher = raw[:16], raw[16:32], raw[32:]
    key = _secret()

    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:16]
    # compare_digest statt ==: ein normaler Vergleich bricht beim
    # ersten falschen Byte ab und verraet ueber die Laufzeit, wie weit
    # ein geratener Tag stimmte.
    if not hmac.compare_digest(tag, expected):
        return None

    try:
        return bytes(
            a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher)))
        ).decode("utf-8")
    except UnicodeDecodeError:
        return None


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

    # Nachtraeglich dazugekommene Spalten.
    #
    # ALTER TABLE ADD COLUMN wirft, wenn die Spalte schon da ist, und
    # SQLite kann das nicht bedingt. Deshalb erst nachsehen: eine
    # bestehende Datenbank soll weiterlaufen, ohne dass jemand sie von
    # Hand anfasst.
    async with db.execute("PRAGMA table_info(templates)") as cursor:
        have = {row[1] for row in await cursor.fetchall()}

    for column, definition in (
        # Der Zugangscode, verschluesselt -- damit der eigene Server
        # ihn wieder anzeigen kann.
        ("key_cipher", "TEXT"),
        # Wer gesperrt hat und warum. Eine gesperrte Vorlage bleibt
        # sichtbar, laesst sich aber nicht mehr anwenden.
        ("blocked", "INTEGER DEFAULT 0"),
        ("blocked_reason", "TEXT DEFAULT ''"),
        ("blocked_by", "TEXT DEFAULT ''"),
        ("blocked_at", "REAL DEFAULT 0"),
    ):
        if column not in have:
            await db.execute(
                f"ALTER TABLE templates ADD COLUMN {column} {definition}"
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


def _column(row, name, fallback=None):
    """Eine Spalte lesen, die es vielleicht noch nicht gibt.

    `aiosqlite.Row` wirft bei einem unbekannten Namen einen IndexError.
    Eine Datenbank aus der Zeit vor `ensure_schema` hat die neuen
    Spalten erst nach dem naechsten Start -- bis dahin soll das Lesen
    trotzdem funktionieren.
    """

    try:
        value = row[name]
    except (IndexError, KeyError):
        return fallback
    return fallback if value is None else value


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
        # Gesperrt heisst: sichtbar, aber nicht anwendbar. Der Grund
        # steht dabei -- eine Vorlage, die kommentarlos nicht mehr
        # geht, sieht nach einem Fehler aus statt nach einer
        # Entscheidung.
        "blocked": bool(_column(row, "blocked", 0)),
        "blocked_reason": str(_column(row, "blocked_reason", "") or ""),
        # Ob ueberhaupt ein Code hinterlegt ist. Damit weiss die
        # Oberflaeche, ob sie den Knopf »Code anzeigen« zeigen darf.
        "has_key": bool(row["key_hash"]),
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
    as_admin: bool = False,
) -> dict | None:
    """Eine einzelne Vorlage, mit Vorschau wenn erlaubt.

    Erlaubt ist sie, wenn die Vorlage offen ist, der richtige Code
    kommt, der fragende Server sie selbst hochgeladen hat -- oder ein
    Bot-Admin fragt.

    Warum `as_admin` sein muss
    --------------------------
    Ohne dieses Kennzeichen war der Admin-Reiter bei genau den
    Vorlagen leer, die man am ehesten pruefen will: bei einer Vorlage
    mit Code ist `key_hash` gesetzt, `key` und `owner_guild_id` sind
    beim Admin-Aufruf None -- also blieb `unlocked` False, und
    `_row_to_template` lieferte ein leeres payload. Kein Fehler, keine
    Meldung, nur eine leere Detailansicht.

    Der Zugangscode ist eine Schranke gegen *fremde Server*, nicht
    gegen das Bot-Team. Wer eine gemeldete Vorlage sperren soll, muss
    hineinsehen koennen -- sonst entscheidet er blind.

    Das Kennzeichen wird nur von den `/admin/*`-Routen gesetzt, und
    dorthin laesst der Proxy ausschliesslich globale Admins durch.
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
    if not unlocked and as_admin:
        unlocked = True

    return _row_to_template(row, with_payload=True, unlocked=unlocked)


async def list_for_admin(
    db: aiosqlite.Connection,
    *,
    search: str = "",
    sort: str = "neu",
    limit: int = 500,
) -> list[dict]:
    """Alles, was hochgeladen wurde -- fuer den Admin-Reiter.

    Anders als `list_templates`:

      * auch **private** Vorlagen stehen drin,
      * die Zahlen sind auch bei Code-Vorlagen echt (ein Admin soll
        sehen, wie gross eine Vorlage ist, bevor er sie prueft),
      * der Zugangscode kommt im Klartext mit, sofern er sich noch
        entschluesseln laesst,
      * dazu Herkunftsserver, Hochlader und wann zuletzt angewendet.

    Das ist bewusst mehr, als ein normaler Nutzer sieht. Deshalb
    laesst der Proxy hierher nur globale Admins durch -- dieselbe
    Regel wie bei der Speedrun-Verwaltung.
    """

    order = {
        "neu": "t.created_at DESC",
        "beliebt": "t.uses DESC, t.created_at DESC",
        "name": "t.name COLLATE NOCASE",
    }.get(sort, "t.created_at DESC")

    db.row_factory = aiosqlite.Row

    where = ""
    args: tuple = ()
    if search.strip():
        needle = f"%{search.strip()}%"
        where = (
            "WHERE t.name LIKE ? OR t.description LIKE ? "
            "OR t.author_name LIKE ? OR CAST(t.source_guild_id AS TEXT) LIKE ?"
        )
        args = (needle, needle, needle, needle)

    query = (
        "SELECT t.*, "
        "(SELECT MAX(created_at) FROM template_applies a "
        " WHERE a.template_id = t.id) AS last_used "
        f"FROM templates t {where} ORDER BY {order} LIMIT ?"
    )

    async with db.execute(query, (*args, int(limit))) as cursor:
        rows = await cursor.fetchall()

    out = []
    for row in rows:
        try:
            raw = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            raw = {}

        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"] or "",
                "author_id": str(row["author_id"] or ""),
                "author_name": row["author_name"] or "",
                "source_guild_id": str(row["source_guild_id"] or ""),
                # Wie der Server hiess, ALS die Vorlage entstand.
                # Ueberlebt auch, wenn der Bot den Server inzwischen
                # verlassen hat -- dann ist es die einzige Spur, um die
                # Vorlage noch zuzuordnen.
                "source_name_at_upload": str(
                    (raw.get("source") or {}).get("name") or ""
                ),
                "visibility": row["visibility"],
                "uses": int(row["uses"] or 0),
                "created_at": row["created_at"],
                "last_used": _column(row, "last_used", None),
                "blocked": bool(_column(row, "blocked", 0)),
                "blocked_reason": str(_column(row, "blocked_reason", "") or ""),
                "blocked_by": str(_column(row, "blocked_by", "") or ""),
                "has_key": bool(row["key_hash"]),
                # Klartext, wenn moeglich. None heisst: der
                # Hauptschluessel hat gewechselt oder der Eintrag ist
                # aelter als diese Funktion.
                "key": decrypt_key(str(_column(row, "key_cipher", "") or "")),
                # Groesse. Eine 4-MB-Vorlage ist ein Grund
                # nachzusehen, was darin steht.
                "size_bytes": len(row["payload"] or ""),
                "summary": {
                    "channels": len(raw.get("channels") or []),
                    "roles": len(raw.get("roles") or []),
                    "categories": len(raw.get("categories") or []),
                    "features": len(raw.get("features") or {}),
                },
            }
        )
    return out


async def admin_stats(db: aiosqlite.Connection) -> dict:
    """Ein paar Zahlen fuer den Kopf des Admin-Reiters."""

    async with db.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN visibility = 'key' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN COALESCE(blocked, 0) = 1 THEN 1 ELSE 0 END), "
        "SUM(uses) FROM templates"
    ) as cursor:
        row = await cursor.fetchone()

    async with db.execute("SELECT COUNT(*) FROM template_applies") as cursor:
        applies = await cursor.fetchone()

    return {
        "total": int((row or [0])[0] or 0),
        "with_key": int((row or [0, 0])[1] or 0),
        "blocked": int((row or [0, 0, 0])[2] or 0),
        "uses": int((row or [0, 0, 0, 0])[3] or 0),
        "applies": int((applies or [0])[0] or 0),
    }


async def reveal_key(
    db: aiosqlite.Connection,
    template_id: int,
    *,
    owner_guild_id: int | None = None,
) -> tuple[bool, str | None]:
    """Den eigenen Zugangscode wieder anzeigen.

    Gibt `(gefunden, code)`. `code` ist None, wenn es keinen gibt oder
    er sich nicht mehr entschluesseln laesst.

    `owner_guild_id` ist die Sperre: nur der Server, der die Vorlage
    hochgeladen hat, bekommt den Code. Ohne diese Bedingung im WHERE
    reichte eine geratene ID -- sie sind fortlaufend --, um jeden
    fremden Code zu lesen.
    """

    db.row_factory = aiosqlite.Row

    if owner_guild_id is None:
        query = "SELECT * FROM templates WHERE id = ?"
        args: tuple = (template_id,)
    else:
        query = "SELECT * FROM templates WHERE id = ? AND source_guild_id = ?"
        args = (template_id, owner_guild_id)

    async with db.execute(query, args) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return False, None
    if not row["key_hash"]:
        return True, None

    return True, decrypt_key(str(_column(row, "key_cipher", "") or ""))


async def set_blocked(
    db: aiosqlite.Connection,
    template_id: int,
    *,
    blocked: bool,
    reason: str = "",
    actor: str = "",
) -> bool:
    """Eine Vorlage sperren oder wieder freigeben.

    Sperren statt loeschen ist der mildere Eingriff: die Vorlage
    bleibt sichtbar, ihr Hochlader sieht den Grund, und ein Irrtum
    laesst sich zuruecknehmen. Geloescht wird nur, was wirklich weg
    muss.
    """

    cursor = await db.execute(
        "UPDATE templates SET blocked = ?, blocked_reason = ?, "
        "blocked_by = ?, blocked_at = ? WHERE id = ?",
        (
            1 if blocked else 0,
            str(reason or "")[:MAX_DESCRIPTION] if blocked else "",
            str(actor or "") if blocked else "",
            time.time() if blocked else 0,
            template_id,
        ),
    )
    await db.commit()
    return bool(cursor.rowcount)


async def force_delete(db: aiosqlite.Connection, template_id: int) -> bool:
    """Loeschen ohne Ruecksicht auf den Besitzer -- nur fuer Admins.

    Getrennt von `delete_template`, damit die normale Route den
    Besitzcheck gar nicht erst umgehen kann. Ein Aufruf hiervon ist
    im Quelltext sofort als Admin-Weg erkennbar.
    """

    cursor = await db.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    await db.execute(
        "DELETE FROM template_applies WHERE template_id = ?", (template_id,)
    )
    await db.commit()
    return bool(cursor.rowcount)


async def history_for(
    db: aiosqlite.Connection, template_id: int, limit: int = 50
) -> list[dict]:
    """Wer diese Vorlage wann angewendet hat."""

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM template_applies WHERE template_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (template_id, int(limit)),
    ) as cursor:
        rows = await cursor.fetchall()

    out = []
    for row in rows:
        try:
            options = json.loads(row["options"] or "{}")
        except (TypeError, ValueError):
            options = {}
        out.append(
            {
                "guild_id": str(row["guild_id"]),
                "actor_id": str(row["actor_id"] or ""),
                "wiped": bool(row["wiped"]),
                "created_at": row["created_at"],
                "options": options,
            }
        )
    return out


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

    Geprueft wird weiter ueber den Hash. Zusaetzlich liegt der Code
    verschluesselt daneben, damit der eigene Server ihn spaeter noch
    einmal anzeigen kann -- vorher war er nach dem Schliessen des
    Fensters unwiederbringlich weg, was in der Praxis bedeutete: neu
    hochladen.
    """

    now = time.time()
    plain_key = None
    key_hash = None
    key_cipher = ""

    if visibility == "key":
        plain_key = (key or "").strip().upper() or make_key()
        key_hash = hash_key(plain_key)
        key_cipher = encrypt_key(plain_key)

    cursor = await db.execute(
        """
        INSERT INTO templates
            (name, description, author_id, author_name, source_guild_id,
             payload, visibility, key_hash, key_cipher, uses,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
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
            key_cipher,
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
