# ╔══════════════════════════════════════════════════════════════════╗
# ║   Server-Verlauf                                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Der tägliche Verlauf eines Servers.

Warum es das braucht
--------------------
Das Dashboard konnte bis jetzt nur sagen, wie etwas **gerade** ist:
4.714 Mitglieder, 52 Server, 15 ms. Die eine Frage, die jeder zuerst
stellt -- "wird es mehr oder weniger?" -- war nirgends zu beantworten.
Ein Diagramm braucht Vergangenheit, und die hat niemand gespeichert.

Hier steht deshalb eine Zeile pro Server und Tag:

    guild_id | day        | members | joins | leaves
    ---------+------------+---------+-------+-------
    1530...  | 2026-08-12 |    4714 |    23 |      9

Drei Entscheidungen, die den Aufbau erklären
--------------------------------------------

**Eine fehlende Zeile heißt "wir haben nicht gemessen".**
Nicht "null Mitglieder", nicht "null Beitritte". Der Schnappschuss
läuft alle 30 Minuten, solange der Bot läuft; gibt es für einen Tag
gar keine Zeile, war der Bot an dem Tag offline. Genau dann liefert
``series()`` ``None`` statt ``0`` -- und das Diagramm zeichnet eine
Lücke statt eines Einbruchs. Ein Ausfall der Messung darf nicht
aussehen wie ein Absturz der Zahl.

**Beitritte werden gezählt, die Mitgliederzahl wird gemessen.**
Man könnte die Mitgliederzahl aus Beitritten minus Austritten
fortschreiben. Nach einem verpassten Gateway-Ereignis liefe die
Rechnung dann für immer daneben. Der Schnappschuss überschreibt
deshalb den gemessenen Stand, die Zähler laufen unabhängig davon.

**Der Tag ist UTC.** Derselbe Schlüssel wie in
``utils/command_stats.py``. Zwei Zeitzonen in einem Diagramm ergäben
Reihen, die um einen Tag gegeneinander verschoben sind.

Speicher
--------
``db/guild_history.db``. Braucht ein Railway-Volume -- ohne das ist
der Verlauf nach jedem Deploy leer, und dann zeigt das Diagramm
wieder nur den heutigen Tag.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from utils import db_paths

DB_PATH = "db/guild_history.db"

# Die Spalten stehen **einmal** hier. Sowohl das CREATE TABLE als auch
# die Nachrüstung fehlender Spalten leiten sich daraus ab.
#
# Zwei handgepflegte Listen laufen auseinander -- bei `team_update`
# ist genau das passiert: `updated_at` fehlte in der zweiten Liste,
# und auf einer bestehenden Installation kam "no such column".
COLUMNS: tuple[tuple[str, str], ...] = (
    ("guild_id", "TEXT NOT NULL"),
    ("day", "TEXT NOT NULL"),
    # NULL erlaubt: an einem Tag kann gezählt worden sein, ohne dass
    # ein Schnappschuss lief (Bot startete kurz vor Mitternacht).
    ("members", "INTEGER"),
    ("joins", "INTEGER NOT NULL DEFAULT 0"),
    ("leaves", "INTEGER NOT NULL DEFAULT 0"),
    ("updated_at", "INTEGER NOT NULL DEFAULT 0"),
)

# Wie lange der Verlauf aufgehoben wird. Ein Jahr plus Reserve: mehr
# zeigt kein Diagramm, und die Datei soll nicht endlos wachsen.
KEEP_DAYS = 400


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def tage_zurueck(days: int) -> list[str]:
    """Die letzten ``days`` Tage als Schlüssel, ältester zuerst.

    Das Diagramm braucht auch die Tage, an denen nichts passiert ist --
    sonst rücken zwei Wochen Stille zu einem Strich zusammen und die
    X-Achse lügt über den Abstand.
    """
    days = max(1, min(int(days or 1), KEEP_DAYS))
    heute = datetime.now(timezone.utc).date()
    return [
        (heute - timedelta(days=abstand)).strftime("%Y-%m-%d")
        for abstand in range(days - 1, -1, -1)
    ]


async def ensure_schema(db) -> None:
    spalten = ", ".join(f"{name} {typ}" for name, typ in COLUMNS)
    await db.execute(
        f"CREATE TABLE IF NOT EXISTS guild_daily ({spalten},"
        " PRIMARY KEY (guild_id, day))"
    )

    # CREATE TABLE IF NOT EXISTS ändert an einer bestehenden Tabelle
    # nichts. Kommt später eine Spalte dazu, fehlt sie auf jeder
    # laufenden Installation -- und jede Abfrage scheitert.
    async with db.execute("PRAGMA table_info(guild_daily)") as cursor:
        vorhanden = {zeile[1] for zeile in await cursor.fetchall()}

    for name, typ in COLUMNS:
        if name in vorhanden:
            continue
        # NOT NULL ohne Vorgabewert lehnt SQLite bei ALTER TABLE ab.
        nachtrag = typ if "DEFAULT" in typ.upper() else typ.replace("NOT NULL", "").strip()
        await db.execute(f"ALTER TABLE guild_daily ADD COLUMN {name} {nachtrag}")

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_guild_daily_lookup"
        " ON guild_daily (guild_id, day)"
    )
    await db.commit()


async def _zeile_anlegen(db, guild_id: str, day: str) -> None:
    """Die Zeile für heute, falls es sie noch nicht gibt.

    ``INSERT OR IGNORE`` und nicht ``INSERT OR REPLACE``: sonst würde
    jeder Aufruf die bereits gezählten Beitritte des Tages auf null
    zurücksetzen.
    """
    await db.execute(
        "INSERT OR IGNORE INTO guild_daily (guild_id, day, joins, leaves, updated_at)"
        " VALUES (?, ?, 0, 0, ?)",
        (guild_id, day, _now()),
    )


async def snapshot(guild_id: int | str, members: int) -> None:
    """Den gemessenen Mitgliederstand für heute festhalten.

    Überschreibt bewusst: der letzte Messwert des Tages ist der, der
    zählt. Fortgeschriebene Summen aus Beitritten und Austritten
    liefen nach einem verpassten Ereignis dauerhaft daneben.
    """
    gid = str(guild_id)
    day = _today()
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        await _zeile_anlegen(db, gid, day)
        await db.execute(
            "UPDATE guild_daily SET members = ?, updated_at = ?"
            " WHERE guild_id = ? AND day = ?",
            (int(members), _now(), gid, day),
        )
        await db.commit()


async def record_join(guild_id: int | str, members: int | None = None) -> None:
    """Einen Beitritt zählen."""
    await _record(guild_id, "joins", members)


async def record_leave(guild_id: int | str, members: int | None = None) -> None:
    """Einen Austritt zählen."""
    await _record(guild_id, "leaves", members)


async def _record(guild_id: int | str, feld: str, members: int | None) -> None:
    # Der Feldname kommt ausschliesslich aus diesem Modul, nie von
    # aussen -- trotzdem geprueft, damit er es auch nie tut.
    if feld not in {"joins", "leaves"}:
        raise ValueError(f"unbekanntes Feld: {feld}")

    gid = str(guild_id)
    day = _today()
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        await _zeile_anlegen(db, gid, day)
        await db.execute(
            f"UPDATE guild_daily SET {feld} = {feld} + 1, updated_at = ?"
            " WHERE guild_id = ? AND day = ?",
            (_now(), gid, day),
        )
        if members is not None:
            # Der Stand direkt nach dem Ereignis ist genauer als der
            # letzte Schnappschuss von vor 29 Minuten.
            await db.execute(
                "UPDATE guild_daily SET members = ? WHERE guild_id = ? AND day = ?",
                (int(members), gid, day),
            )
        await db.commit()


async def series(guild_id: int | str, days: int = 30) -> dict:
    """Der Verlauf als drei Reihen, je ein Wert pro Tag.

    Tage ohne Zeile liefern ``None``. Das ist der ganze Punkt dieser
    Funktion: ohne die Unterscheidung sähe ein Tag, an dem der Bot
    offline war, aus wie ein Tag ohne einen einzigen Beitritt.
    """
    gid = str(guild_id)
    tage = tage_zurueck(days)

    zeilen: dict[str, tuple] = {}
    try:
        async with db_paths.connect(DB_PATH) as db:
            await ensure_schema(db)
            async with db.execute(
                "SELECT day, members, joins, leaves FROM guild_daily"
                " WHERE guild_id = ? AND day >= ? ORDER BY day",
                (gid, tage[0]),
            ) as cursor:
                for zeile in await cursor.fetchall():
                    zeilen[str(zeile[0])] = zeile
    except Exception:
        # Ein fehlender Verlauf darf die Übersicht nicht kaputtmachen.
        zeilen = {}

    members: list[int | None] = []
    joins: list[int | None] = []
    leaves: list[int | None] = []

    for tag in tage:
        zeile = zeilen.get(tag)
        if zeile is None:
            members.append(None)
            joins.append(None)
            leaves.append(None)
            continue
        members.append(int(zeile[1]) if zeile[1] is not None else None)
        joins.append(int(zeile[2] or 0))
        leaves.append(int(zeile[3] or 0))

    return {
        "days": tage,
        "members": members,
        "joins": joins,
        "leaves": leaves,
        # An welchen Tagen überhaupt gemessen wurde. Andere Reihen --
        # etwa die Befehle -- unterscheiden damit "null Aufrufe" von
        # "Bot war aus".
        "measured": [tag for tag in tage if tag in zeilen],
    }


async def totals(days: int = 30, guild_ids: list[str] | None = None) -> dict:
    """Derselbe Verlauf, aber über alle Server zusammengezählt.

    Für die Einstiegsseite: dort geht es nicht um einen Server,
    sondern um den Bot.

    ``guild_ids`` grenzt auf bestimmte Server ein -- die Seite eines
    Nutzers darf nur zusammenzählen, was ihm gehört. Ohne die Angabe
    wird alles genommen; das ist der Admin-Fall.

    **Warum die Mitgliederzahl summiert und nicht gemittelt wird:**
    gefragt ist die Reichweite, also "wie viele Menschen erreicht der
    Bot". Ein Durchschnitt je Server beantwortet eine andere Frage
    und sinkt, sobald ein kleiner Server dazukommt.

    **Warum ein Tag ohne jede Zeile ``None`` bleibt:** an einem Tag,
    an dem der Bot aus war, ist die Reichweite nicht null gewesen --
    sie ist unbekannt.
    """
    tage = tage_zurueck(days)
    erlaubt = {str(g) for g in guild_ids} if guild_ids is not None else None

    if erlaubt is not None and not erlaubt:
        # Kein einziger Server: es gibt nichts zu summieren. Ohne
        # diesen Zweig würde die Abfrage unten alle Server addieren.
        return {
            "days": tage,
            "members": [None] * len(tage),
            "joins": [None] * len(tage),
            "leaves": [None] * len(tage),
            "has_data": False,
        }

    members: dict[str, int] = {}
    joins: dict[str, int] = {}
    leaves: dict[str, int] = {}
    vorhanden: set[str] = set()

    try:
        async with db_paths.connect(DB_PATH) as db:
            await ensure_schema(db)
            async with db.execute(
                "SELECT day, guild_id, members, joins, leaves FROM guild_daily"
                " WHERE day >= ?",
                (tage[0],),
            ) as cursor:
                for tag, gid, mem, ein, aus in await cursor.fetchall():
                    tag = str(tag)
                    if erlaubt is not None and str(gid) not in erlaubt:
                        continue
                    vorhanden.add(tag)
                    if mem is not None:
                        members[tag] = members.get(tag, 0) + int(mem)
                    joins[tag] = joins.get(tag, 0) + int(ein or 0)
                    leaves[tag] = leaves.get(tag, 0) + int(aus or 0)
    except Exception:
        vorhanden = set()

    return {
        "days": tage,
        "members": [members.get(t) if t in vorhanden else None for t in tage],
        "joins": [joins.get(t, 0) if t in vorhanden else None for t in tage],
        "leaves": [leaves.get(t, 0) if t in vorhanden else None for t in tage],
        "has_data": bool(vorhanden),
    }


async def prune(keep_days: int = KEEP_DAYS) -> int:
    """Alte Zeilen wegräumen. Gibt die Zahl der gelöschten zurück."""
    grenze = (
        datetime.now(timezone.utc).date() - timedelta(days=max(1, int(keep_days)))
    ).strftime("%Y-%m-%d")
    try:
        async with db_paths.connect(DB_PATH) as db:
            await ensure_schema(db)
            cursor = await db.execute(
                "DELETE FROM guild_daily WHERE day < ?", (grenze,)
            )
            await db.commit()
            return int(cursor.rowcount or 0)
    except Exception:
        return 0
