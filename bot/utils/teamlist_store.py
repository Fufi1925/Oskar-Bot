"""
Teamliste: wer im Team ist, nach Rollen geordnet, im Kanal sichtbar.

Was das ist
-----------
Eine Nachricht in einem Kanal, die zeigt, wer welche Rolle hat --
Inhaber, Administratoren, Moderatoren, Supporter. Sie haelt sich
selbst aktuell: bekommt jemand eine Rolle dazu oder verliert sie,
schreibt der Bot die Nachricht neu.

Warum eine gespeicherte Nachricht und kein Befehl
-------------------------------------------------
Ein `>team` waere weniger Code. Aber eine Teamliste soll oben im
Kanal stehen und dort bleiben -- angeheftet, jederzeit nachlesbar.
Ein Befehl erzeugt eine Antwort, die nach zwanzig Nachrichten
weggescrollt ist.

Deshalb merkt sich der Bot Kanal und Nachrichten-ID und bearbeitet
dieselbe Nachricht immer wieder, statt eine neue zu schicken.

Wie die Anzeige aufgebaut ist
-----------------------------
Je Rolle eine Gruppe, in der Reihenfolge, die im Dashboard
festgelegt wird:

    <:krone:123> **Inhaber**
    > <@111>
    > <@222>

    <:schild:456> **Administrator**
    > <@333>

Das ``>`` ist Discords Zitat-Strich: er zieht eine senkrechte Linie
neben die Zeile und rueckt sie ein. Das ist der Grund, warum die
Liste ohne weiteres Zutun geordnet aussieht.

Warum Erwaehnungen und keine Namen
----------------------------------
``<@111>`` zeigt Discord als Anzeigenamen mit Farbe der hoechsten
Rolle -- und es bleibt richtig, wenn jemand seinen Namen aendert. Ein
abgeschriebener Name waere nach der naechsten Umbenennung falsch.

Erwaehnungen in einer bearbeiteten Nachricht pingen uebrigens
niemanden: Discord benachrichtigt nur beim ersten Absenden, und auch
das unterbinden wir ueber ``allowed_mentions``.

Speicher
--------
`db/teamlist.db`. Braucht ein Railway-Volume, sonst ist die
Einrichtung nach dem naechsten Deploy weg -- und der Bot schriebe
eine zweite Nachricht statt die alte zu bearbeiten.
"""

from __future__ import annotations

import json
import time

import aiosqlite

DB_PATH = "db/teamlist.db"

# Discords Grenze fuer eine gewoehnliche Nachricht.
MAX_MESSAGE = 2000

# Grenzen fuer die Einrichtung. Sie stehen hier und nicht in der
# Route, damit das Dashboard dieselben Zahlen anzeigen kann.
MAX_GROUPS = 15
MAX_TITLE = 200
MAX_TEXT = 1000

# Wie lange nach einer Rollenaenderung gewartet wird, bevor die
# Nachricht neu geschrieben wird.
#
# Wer fuenf Leuten nacheinander eine Rolle gibt, loest fuenf
# Ereignisse aus. Ohne diese Sammelpause schriebe der Bot fuenfmal --
# und liefe in Discords Bearbeitungsgrenze (5 Bearbeitungen pro 5
# Sekunden je Nachricht). Drei Sekunden fassen eine solche Serie
# zusammen und sind kurz genug, dass es sich noch nach "sofort"
# anfuehlt.
DEBOUNCE_SECONDS = 3.0

# Zusaetzlich alle 15 Minuten neu schreiben.
#
# Nicht als Ersatz fuer die Ereignisse, sondern als Netz darunter: ein
# Neustart mitten in einer Aenderung, ein verpasstes Gateway-Ereignis
# oder ein Mitglied, das der Bot nicht im Zwischenspeicher hatte --
# dann steht die Liste sonst dauerhaft falsch da, ohne dass es jemand
# merkt.
REFRESH_SECONDS = 15 * 60


# ── Schema ───────────────────────────────────────────────────────────


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS teamlist (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            channel_id INTEGER,
            message_id INTEGER,
            title TEXT DEFAULT '',
            intro TEXT DEFAULT '',
            footer TEXT DEFAULT '',
            style TEXT DEFAULT 'quote',
            show_empty INTEGER DEFAULT 0,
            show_counts INTEGER DEFAULT 1,
            show_status INTEGER DEFAULT 0,
            use_embed INTEGER DEFAULT 0,
            colour TEXT DEFAULT '',
            updated_at REAL DEFAULT 0
        )
        """
    )
    # Die Gruppen: je Rolle eine Zeile, mit Reihenfolge.
    #
    # Eigene Tabelle statt einer JSON-Spalte, weil die Reihenfolge
    # veraenderbar sein muss und einzelne Gruppen geloescht werden --
    # beides waere in einem JSON-Feld Handarbeit mit Fehlerpotenzial.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS teamlist_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            emoji TEXT DEFAULT '',
            label TEXT DEFAULT '',
            position INTEGER DEFAULT 0
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_teamlist_groups "
        "ON teamlist_groups (guild_id, position)"
    )
    await db.commit()


# ── Lesen ────────────────────────────────────────────────────────────


def _row_to_config(row) -> dict:
    return {
        "enabled": bool(row["enabled"]),
        # IDs als Text. 17-20 Ziffern sind groesser als
        # Number.MAX_SAFE_INTEGER -- als Zahl ausgeliefert rundet
        # JavaScript sie stillschweigend und die letzte Stelle stimmt
        # nicht mehr.
        "channel_id": str(row["channel_id"] or ""),
        "message_id": str(row["message_id"] or ""),
        "title": row["title"] or "",
        "intro": row["intro"] or "",
        "footer": row["footer"] or "",
        "style": row["style"] or "quote",
        "show_empty": bool(row["show_empty"]),
        "show_counts": bool(row["show_counts"]),
        "show_status": bool(row["show_status"]),
        "use_embed": bool(row["use_embed"]),
        "colour": row["colour"] or "",
        "updated_at": row["updated_at"],
    }


DEFAULTS = {
    "enabled": False,
    "channel_id": "",
    "message_id": "",
    "title": "Unser Team",
    "intro": "",
    "footer": "",
    "style": "quote",
    "show_empty": False,
    "show_counts": True,
    "show_status": False,
    "use_embed": False,
    "colour": "",
    "updated_at": 0,
}


async def get_config(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Die Einstellungen. Nie None -- ein leerer Server bekommt die
    Voreinstellungen, damit das Dashboard keinen Sonderfall braucht."""

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM teamlist WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()

    return _row_to_config(row) if row else dict(DEFAULTS)


async def get_groups(db: aiosqlite.Connection, guild_id: int) -> list[dict]:
    """Die Rollengruppen, in ihrer Reihenfolge."""

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM teamlist_groups WHERE guild_id = ? "
        "ORDER BY position, id",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "role_id": str(row["role_id"]),
            "emoji": row["emoji"] or "",
            "label": row["label"] or "",
            "position": int(row["position"] or 0),
        }
        for row in rows
    ]


# ── Schreiben ────────────────────────────────────────────────────────

_FIELDS = (
    "enabled", "channel_id", "message_id", "title", "intro", "footer",
    "style", "show_empty", "show_counts", "show_status", "use_embed",
    "colour",
)


async def save_config(
    db: aiosqlite.Connection, guild_id: int, data: dict
) -> None:
    """Einstellungen sichern. Nur bekannte Felder."""

    current = await get_config(db, guild_id)
    merged = {**current, **{k: v for k, v in data.items() if k in _FIELDS}}

    def _id(value):
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    await db.execute(
        """
        INSERT INTO teamlist
            (guild_id, enabled, channel_id, message_id, title, intro,
             footer, style, show_empty, show_counts, show_status,
             use_embed, colour, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            enabled = excluded.enabled,
            channel_id = excluded.channel_id,
            message_id = excluded.message_id,
            title = excluded.title,
            intro = excluded.intro,
            footer = excluded.footer,
            style = excluded.style,
            show_empty = excluded.show_empty,
            show_counts = excluded.show_counts,
            show_status = excluded.show_status,
            use_embed = excluded.use_embed,
            colour = excluded.colour,
            updated_at = excluded.updated_at
        """,
        (
            guild_id,
            1 if merged["enabled"] else 0,
            _id(merged["channel_id"]),
            _id(merged["message_id"]),
            str(merged["title"] or "")[:MAX_TITLE],
            str(merged["intro"] or "")[:MAX_TEXT],
            str(merged["footer"] or "")[:MAX_TEXT],
            str(merged["style"] or "quote"),
            1 if merged["show_empty"] else 0,
            1 if merged["show_counts"] else 0,
            1 if merged["show_status"] else 0,
            1 if merged["use_embed"] else 0,
            str(merged["colour"] or "")[:20],
            time.time(),
        ),
    )
    await db.commit()


async def set_message(
    db: aiosqlite.Connection, guild_id: int, channel_id, message_id
) -> None:
    """Merken, wo die Nachricht steht.

    Getrennt von `save_config`, weil der Bot das nach dem Senden
    aufruft -- und dabei nicht versehentlich Einstellungen
    ueberschreiben soll, die der Nutzer inzwischen geaendert hat.
    """

    def _id(value):
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    await db.execute(
        "UPDATE teamlist SET channel_id = ?, message_id = ?, updated_at = ? "
        "WHERE guild_id = ?",
        (_id(channel_id), _id(message_id), time.time(), guild_id),
    )
    await db.commit()


async def save_groups(
    db: aiosqlite.Connection, guild_id: int, groups: list
) -> None:
    """Die Rollengruppen ersetzen.

    Alles loeschen und neu schreiben ist hier richtig: die Liste ist
    kurz (hoechstens 15), und die Reihenfolge zaehlt. Einzelne Zeilen
    abzugleichen waere mehr Code und mehr Gelegenheit, die Reihenfolge
    durcheinanderzubringen.
    """

    await db.execute("DELETE FROM teamlist_groups WHERE guild_id = ?", (guild_id,))

    seen: set[int] = set()
    position = 0
    for entry in (groups or [])[:MAX_GROUPS]:
        try:
            role_id = int((entry or {}).get("role_id") or 0)
        except (TypeError, ValueError):
            continue
        if not role_id:
            continue
        # Dieselbe Rolle zweimal waere eine Gruppe, die sich selbst
        # wiederholt -- und beim Anwenden staenden die Mitglieder
        # doppelt in der Liste.
        if role_id in seen:
            continue
        seen.add(role_id)

        await db.execute(
            "INSERT INTO teamlist_groups "
            "(guild_id, role_id, emoji, label, position) VALUES (?, ?, ?, ?, ?)",
            (
                guild_id,
                role_id,
                str((entry or {}).get("emoji") or "")[:100],
                str((entry or {}).get("label") or "")[:100],
                position,
            ),
        )
        position += 1

    await db.commit()


async def clear(db: aiosqlite.Connection, guild_id: int) -> None:
    """Alles zu diesem Server vergessen."""

    await db.execute("DELETE FROM teamlist WHERE guild_id = ?", (guild_id,))
    await db.execute(
        "DELETE FROM teamlist_groups WHERE guild_id = ?", (guild_id,)
    )
    await db.commit()


async def all_enabled(db: aiosqlite.Connection) -> list[int]:
    """Welche Server eine eingeschaltete Teamliste haben.

    Fuer die regelmaessige Auffrischung -- sie muss wissen, wen sie
    ueberhaupt ansehen soll, ohne jeden Server einzeln abzufragen.
    """

    async with db.execute(
        "SELECT guild_id FROM teamlist WHERE enabled = 1 "
        "AND channel_id IS NOT NULL"
    ) as cursor:
        rows = await cursor.fetchall()
    return [int(row[0]) for row in rows]


# ── Die Nachricht bauen ──────────────────────────────────────────────

# Wie eine Mitgliederzeile aussieht.
#
# `quote` ist Discords Zitat-Strich: eine senkrechte Linie neben der
# Zeile, eingerueckt. Genau das gibt der Liste ohne weiteres Zutun ihre
# Form.
STYLES = {
    "quote": "> {member}",
    "quote_dash": "> — {member}",
    "bullet": "• {member}",
    "plain": "{member}",
    "code": "`»` {member}",
}


def _clip(text: str, limit: int) -> str:
    """Text kuerzen, ohne mitten in einer Zeile abzubrechen."""

    if len(text) <= limit:
        return text
    cut = text[: limit - 20]
    # An der letzten vollstaendigen Zeile abschneiden -- ein halber
    # Erwaehnungs-Code (`<@1234`) waere sichtbarer Muell.
    if "\n" in cut:
        cut = cut[: cut.rindex("\n")]
    return cut + "\n…"


def build_lines(
    config: dict,
    groups: list[dict],
    members_by_role: dict[str, list[dict]],
) -> str:
    """Den Text der Teamliste bauen.

    `members_by_role` ist Rollen-ID (als Text) -> Liste von
    Mitgliedern, jedes mit `mention` und optional `status`.

    Bewusst ohne Discord-Objekte: so laesst sich das Ergebnis in
    einem Test pruefen, ohne einen Server nachzubauen -- und das
    Dashboard kann dieselbe Funktion fuer seine Vorschau benutzen,
    statt das Format ein zweites Mal (und leicht anders) zu bauen.
    """

    template = STYLES.get(config.get("style") or "quote", STYLES["quote"])
    parts: list[str] = []

    title = str(config.get("title") or "").strip()
    if title and not config.get("use_embed"):
        parts.append(f"## {title}")

    intro = str(config.get("intro") or "").strip()
    if intro:
        parts.append(intro)

    for group in groups:
        members = members_by_role.get(str(group["role_id"])) or []

        # Eine leere Gruppe ist meist ein Versehen -- die Rolle hat
        # gerade niemand. Sie trotzdem zu zeigen ist eine Entscheidung,
        # keine Voreinstellung.
        if not members and not config.get("show_empty"):
            continue

        emoji = str(group.get("emoji") or "").strip()
        label = str(group.get("label") or "").strip() or group.get(
            "role_name"
        ) or "Rolle"

        head = f"{emoji} " if emoji else ""
        head += f"**{label}**"
        if config.get("show_counts"):
            head += f" `{len(members)}`"
        parts.append(head)

        if not members:
            parts.append("> *niemand*")
        else:
            for member in members:
                line = template.format(member=member.get("mention") or "")
                status = member.get("status")
                if config.get("show_status") and status:
                    line += f" {status}"
                parts.append(line)

        # Leerzeile zwischen den Gruppen. Ohne sie kleben die Bloecke
        # aneinander und der Zitat-Strich laeuft durch.
        parts.append("")

    footer = str(config.get("footer") or "").strip()
    if footer:
        parts.append(footer)

    text = "\n".join(parts).strip()
    return _clip(text, MAX_MESSAGE) if text else "*Noch keine Gruppen eingerichtet.*"
