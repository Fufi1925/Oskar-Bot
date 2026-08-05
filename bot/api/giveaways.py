# ╔══════════════════════════════════════════════════════════════════╗
# ║   Giveaways: entries, drawing, rerolls                           ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Giveaway storage and draw logic.

Two problems with the previous setup:

  * The cog wrote to `db/giveaways.db` while the API wrote to
    `db/giveaway.db` — two different files. A giveaway started from the
    dashboard was invisible to the cog's timer, so it never ended by
    itself and never announced a winner.
  * Entries were counted by reading the 🎉 reaction back off the message.
    That breaks as soon as the reaction is cleared, cannot record when
    somebody joined, and makes a reroll that excludes previous winners
    impossible.

Entries now live in their own table, written when someone presses the
join button. Everything reads one file: `db/giveaways.db`, the one the
cog already used.
"""

from __future__ import annotations

import random
import time
from typing import Any

import aiosqlite

DB_PATH = "db/giveaways.db"


async def ensure_schema(db: aiosqlite.Connection) -> None:
    """Create the tables and add the columns newer features need."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS Giveaway (
            guild_id INTEGER,
            host_id INTEGER,
            start_time TIMESTAMP,
            ends_at TIMESTAMP,
            prize TEXT,
            winners INTEGER,
            message_id INTEGER,
            channel_id INTEGER,
            PRIMARY KEY (guild_id, message_id)
        )
        """
    )

    # Who pressed the button. Reading the reaction back was lossy.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at REAL NOT NULL,
            PRIMARY KEY (message_id, user_id)
        )
        """
    )

    # Past winners, so a reroll can skip them.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_winners (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            won_at REAL NOT NULL,
            rerolled INTEGER DEFAULT 0,
            PRIMARY KEY (message_id, user_id)
        )
        """
    )

    # Wem fuer welches Gewinnspiel schon eine DM geschickt wurde.
    #
    # Der eigentliche Riegel gegen den DM-Spam. Frueher entschied allein
    # der Ablauf, ob geschickt wird -- und weil die Timer-Schleife
    # dasselbe Gewinnspiel alle fuenf Sekunden erneut beendete, kam die
    # DM eben alle fuenf Sekunden erneut.
    #
    # Jetzt entscheidet die Datenbank: der Primaerschluessel laesst
    # dieselbe Kombination kein zweites Mal zu. Das haelt auch dann,
    # wenn zwei Ablaeufe gleichzeitig ankuendigen wollen.
    #
    # ``kind`` trennt Gewinner- und Host-DM, damit ein Host, der selbst
    # gewinnt, beide bekommt -- aber jede nur einmal.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_dms (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'winner',
            sent_at REAL NOT NULL,
            PRIMARY KEY (message_id, user_id, kind)
        )
        """
    )

    # Per-user tuning of the draw. Never shown in the channel: the host
    # sets it in the dashboard, entrants only ever see the plain count.
    #   weight     — how many tickets the user holds (1 = normal)
    #   guaranteed — 1 means the user is drawn before anybody else
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_boosts (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            weight INTEGER DEFAULT 1,
            guaranteed INTEGER DEFAULT 0,
            note TEXT,
            set_by INTEGER,
            set_at REAL,
            PRIMARY KEY (message_id, user_id)
        )
        """
    )

    # Columns added after the table shipped; CREATE IF NOT EXISTS is a
    # no-op on an existing table, so these need an explicit ALTER.
    async with db.execute("PRAGMA table_info([Giveaway])") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    extras = {
        "title": "TEXT",
        "description": "TEXT",
        "colour": "INTEGER",
        "button_label": "TEXT",
        "button_emoji": "TEXT",
        "image_url": "TEXT",
        "required_role_id": "INTEGER",
        "dm_winners": "INTEGER DEFAULT 1",
        "dm_host": "INTEGER DEFAULT 1",
        "ended": "INTEGER DEFAULT 0",
        # Entry requirements. Everything defaults to "no requirement" so
        # existing giveaways keep behaving the way they did.
        "blocked_role_id": "INTEGER",
        "min_messages": "INTEGER DEFAULT 0",
        "min_level": "INTEGER DEFAULT 0",
        "min_account_days": "INTEGER DEFAULT 0",
        "min_member_days": "INTEGER DEFAULT 0",
        # Texts the host can write themselves; empty means the default.
        "msg_joined": "TEXT",
        "msg_left": "TEXT",
        "msg_ended": "TEXT",
        "msg_denied": "TEXT",
        "msg_winner_dm": "TEXT",
        "msg_announce": "TEXT",
        "msg_no_entries": "TEXT",
        "allow_leave": "INTEGER DEFAULT 1",
    }
    for name, kind in extras.items():
        if name not in columns:
            try:
                await db.execute(f"ALTER TABLE Giveaway ADD COLUMN {name} {kind}")
            except Exception:
                pass

    await db.commit()


# ---------------------------------------------------------------- entries


async def add_entry(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    """Record a join. Returns False when the user had already entered."""
    async with db.execute(
        "SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
        (message_id, user_id),
    ) as cursor:
        if await cursor.fetchone():
            return False

    await db.execute(
        "INSERT INTO giveaway_entries (message_id, user_id, joined_at)"
        " VALUES (?, ?, ?)",
        (message_id, user_id, time.time()),
    )
    await db.commit()
    return True


async def remove_entry(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
        (message_id, user_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def entry_ids(db: aiosqlite.Connection, message_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_id FROM giveaway_entries WHERE message_id = ?", (message_id,)
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def entry_count(db: aiosqlite.Connection, message_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM giveaway_entries WHERE message_id = ?", (message_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------- boosts


async def set_boost(
    db: aiosqlite.Connection,
    message_id: int,
    user_id: int,
    *,
    weight: int = 1,
    guaranteed: bool = False,
    note: str = "",
    set_by: int = 0,
) -> None:
    """
    Give one user better odds, or a guaranteed win.

    Deliberately stored apart from the entries: the giveaway message only
    ever shows the plain entrant count, so nobody in the channel can tell
    that somebody was favoured.
    """
    weight = max(1, min(int(weight or 1), 1_000_000))
    if weight == 1 and not guaranteed:
        # Nothing special left to remember.
        await clear_boost(db, message_id, user_id)
        return

    await db.execute(
        "INSERT OR REPLACE INTO giveaway_boosts"
        " (message_id, user_id, weight, guaranteed, note, set_by, set_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            message_id, user_id, weight, 1 if guaranteed else 0,
            str(note or "")[:200], int(set_by or 0), time.time(),
        ),
    )
    await db.commit()


async def clear_boost(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM giveaway_boosts WHERE message_id = ? AND user_id = ?",
        (message_id, user_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def boosts(db: aiosqlite.Connection, message_id: int) -> dict[int, dict]:
    """{user_id: {"weight": n, "guaranteed": bool, "note": str}}"""
    async with db.execute(
        "SELECT user_id, weight, guaranteed, note FROM giveaway_boosts"
        " WHERE message_id = ?",
        (message_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    return {
        int(row[0]): {
            "weight": max(1, int(row[1] or 1)),
            "guaranteed": bool(row[2]),
            "note": row[3] or "",
        }
        for row in rows
    }


# ---------------------------------------------------------------- winners


async def past_winner_ids(db: aiosqlite.Connection, message_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_id FROM giveaway_winners WHERE message_id = ?", (message_id,)
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def record_winners(
    db: aiosqlite.Connection, message_id: int, user_ids: list[int], *, reroll=False
) -> None:
    now = time.time()
    for user_id in user_ids:
        await db.execute(
            "INSERT OR REPLACE INTO giveaway_winners"
            " (message_id, user_id, won_at, rerolled) VALUES (?, ?, ?, ?)",
            (message_id, user_id, now, 1 if reroll else 0),
        )
    await db.commit()


def weighted_sample(pool: dict[int, int], count: int) -> list[int]:
    """
    Draw `count` distinct users, each user's chance proportional to its
    weight.

    `random.sample` cannot do this: repeating a user in the list to give
    them extra tickets lets the same person be picked twice, because
    sample only guarantees distinct *positions*. So the pick is done one
    at a time and the winner is removed from the pool.
    """
    remaining = {uid: max(1, int(w or 1)) for uid, w in pool.items()}
    picked: list[int] = []

    while remaining and len(picked) < count:
        total = sum(remaining.values())
        target = random.uniform(0, total)
        running = 0.0
        chosen = next(iter(remaining))
        for uid, weight in remaining.items():
            running += weight
            if running >= target:
                chosen = uid
                break
        picked.append(chosen)
        del remaining[chosen]

    return picked


async def draw(
    db: aiosqlite.Connection,
    message_id: int,
    count: int,
    *,
    exclude_past: bool = False,
) -> list[int]:
    """
    Pick winners from the recorded entries.

    Two extras on top of a plain random pick, both invisible in the
    channel:

      * a user marked `guaranteed` is placed first, without a roll
      * everyone else is drawn with their weight as extra tickets

    exclude_past skips everyone who already won this giveaway, which is
    what a reroll should do — otherwise it can hand the prize to the same
    person again.
    """
    candidates = await entry_ids(db, message_id)
    if exclude_past:
        already = set(await past_winner_ids(db, message_id))
        remaining = [u for u in candidates if u not in already]
        # If everyone has won already, fall back to the full pool rather
        # than returning nobody.
        candidates = remaining or candidates

    if not candidates:
        return []

    count = min(max(1, count), len(candidates))
    tuning = await boosts(db, message_id)

    # Guaranteed winners come first, but only if they actually entered.
    sure = [u for u in candidates if tuning.get(u, {}).get("guaranteed")]
    random.shuffle(sure)
    winners = sure[:count]

    if len(winners) < count:
        rest = {
            uid: tuning.get(uid, {}).get("weight", 1)
            for uid in candidates
            if uid not in winners
        }
        winners += weighted_sample(rest, count - len(winners))

    return winners


# ---------------------------------------------------------------- records


async def get(db: aiosqlite.Connection, guild_id: int, message_id: int) -> dict | None:
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM Giveaway WHERE guild_id = ? AND message_id = ?",
        (guild_id, message_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_ended(db: aiosqlite.Connection, message_id: int) -> bool:
    """
    Flag it as finished instead of deleting the row.

    The entries and winners have to stay around for a reroll, and the
    dashboard should still be able to show what happened.

    Gibt True zurueck, wenn *dieser* Aufruf das Gewinnspiel beendet
    hat, und False, wenn es schon beendet war. Das ist der Riegel
    gegen den Mehrfach-Abschluss:

    ``UPDATE ... WHERE ended = 0`` ist eine einzelne Anweisung, also
    atomar. Zwei Aufrufer -- der Timer und ein Klick im Dashboard --
    koennen nicht beide True bekommen, auch wenn sie sich
    ueberschneiden. Wer False bekommt, muss die Ankuendigung und alle
    DMs auslassen.

    Vorher setzte diese Funktion nur das Flag und meldete nichts
    zurueck. Die Auswahl der Timer-Schleife filterte gleichzeitig nur
    nach ``ends_at <= jetzt`` und nie nach ``ended`` -- die Zeile
    tauchte also alle fuenf Sekunden wieder auf, wurde erneut
    ausgelost und erneut angekuendigt. Pro Stunde waren das 720
    Ankuendigungen und ebenso viele DMs an jeden Gewinner.
    """

    cursor = await db.execute(
        "UPDATE Giveaway SET ended = 1 WHERE message_id = ? AND ended = 0",
        (message_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def is_ended(db: aiosqlite.Connection, message_id: int) -> bool:
    """Ist dieses Gewinnspiel schon abgeschlossen?"""

    async with db.execute(
        "SELECT ended FROM Giveaway WHERE message_id = ?", (message_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


# ------------------------------------------------------------- DM-Sperre


async def claim_dm(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    """Darf dieser Nutzer fuer dieses Gewinnspiel eine DM bekommen?

    True genau beim ersten Mal. Jeder weitere Aufruf gibt False.

    ``INSERT OR IGNORE`` mit zusammengesetztem Primaerschluessel: die
    Datenbank entscheidet, nicht der Code. Selbst wenn zwei Ablaeufe
    gleichzeitig ankuendigen wollen -- der Timer und ein Klick im
    Dashboard -- bekommt nur einer den Zuschlag.

    Bewusst eine eigene Tabelle statt eines Feldes an den Gewinnern:
    auch der Host bekommt eine DM, und der steht nicht in
    ``giveaway_winners``. ``kind`` trennt beide Faelle, damit ein
    Gewinner, der zugleich Host ist, seine Gewinner-DM nicht verliert.
    """

    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO giveaway_dms (message_id, user_id, kind, sent_at)"
            " VALUES (?, ?, ?, ?)",
            (message_id, user_id, "winner", time.time()),
        )
        await db.commit()
        return cursor.rowcount > 0
    except Exception:
        # Lieber eine DM zu wenig als eine Endlosschleife: schlaegt die
        # Buchhaltung fehl, wird nicht geschickt.
        return False


async def claim_host_dm(db: aiosqlite.Connection, message_id: int, user_id: int) -> bool:
    """Dasselbe fuer die Zusammenfassung an den Host."""

    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO giveaway_dms (message_id, user_id, kind, sent_at)"
            " VALUES (?, ?, ?, ?)",
            (message_id, user_id, "host", time.time()),
        )
        await db.commit()
        return cursor.rowcount > 0
    except Exception:
        return False


# ---------------------------------------------------------- requirements

LEVELING_DB = "db/leveling.db"


def level_from_xp(xp: int) -> int:
    """Same curve the leveling cog uses: level = floor(sqrt(xp / 100))."""
    if xp is None or xp < 0:
        return 0
    return int((xp / 100) ** 0.5)


async def member_activity(guild_id: int, user_id: int) -> tuple[int, int]:
    """
    (messages, level) for a member, read from the leveling database.

    Returns (0, 0) when leveling was never switched on for that server —
    a requirement on messages then simply blocks nobody who has written,
    which is nicer than erroring out.
    """
    try:
        async with aiosqlite.connect(LEVELING_DB) as db:
            async with db.execute(
                "SELECT xp, messages FROM user_xp WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
    except Exception:
        return 0, 0

    if not row:
        return 0, 0
    xp = int(row[0] or 0)
    messages = int(row[1] or 0)
    return messages, level_from_xp(xp)


async def failed_requirements(record: dict, member) -> list[str]:
    """
    Everything the member does not fulfil, in plain German.

    An empty list means they may enter. The checks are ordered the way a
    host would explain them, so the first line is the most obvious one.
    """
    import datetime as _dt

    problems: list[str] = []
    guild = getattr(member, "guild", None)
    role_ids = {r.id for r in getattr(member, "roles", [])}

    required = record.get("required_role_id")
    if required and guild is not None:
        if int(required) not in role_ids:
            role = guild.get_role(int(required))
            problems.append(
                f"Du brauchst die Rolle {role.mention if role else f'<@&{required}>'}."
            )

    blocked = record.get("blocked_role_id")
    if blocked and guild is not None and int(blocked) in role_ids:
        role = guild.get_role(int(blocked))
        problems.append(
            f"Mit der Rolle {role.mention if role else f'<@&{blocked}>'}"
            " darfst du nicht teilnehmen."
        )

    min_messages = int(record.get("min_messages") or 0)
    min_level = int(record.get("min_level") or 0)
    if min_messages or min_level:
        messages, level = await member_activity(
            int(record.get("guild_id") or 0), int(member.id)
        )
        if min_messages and messages < min_messages:
            problems.append(
                f"Du brauchst **{min_messages}** Nachrichten auf dem Server"
                f" (du hast {messages})."
            )
        if min_level and level < min_level:
            problems.append(
                f"Du brauchst **Level {min_level}** (du hast Level {level})."
            )

    now = _dt.datetime.now(_dt.timezone.utc)

    min_account = int(record.get("min_account_days") or 0)
    created = getattr(member, "created_at", None)
    if min_account and created is not None:
        age = (now - created).days
        if age < min_account:
            problems.append(
                f"Dein Account muss **{min_account} Tage** alt sein"
                f" (er ist {age} Tage alt)."
            )

    min_member = int(record.get("min_member_days") or 0)
    joined = getattr(member, "joined_at", None)
    if min_member and joined is not None:
        days = (now - joined).days
        if days < min_member:
            problems.append(
                f"Du musst **{min_member} Tage** auf dem Server sein"
                f" (du bist {days} Tage hier)."
            )

    return problems


def requirement_lines(record: dict, guild=None) -> list[str]:
    """The same rules as a short list for the giveaway message itself."""
    lines: list[str] = []

    required = record.get("required_role_id")
    if required:
        role = guild.get_role(int(required)) if guild else None
        lines.append(f"Rolle {role.mention if role else f'<@&{required}>'}")

    blocked = record.get("blocked_role_id")
    if blocked:
        role = guild.get_role(int(blocked)) if guild else None
        lines.append(f"nicht mit {role.mention if role else f'<@&{blocked}>'}")

    if int(record.get("min_messages") or 0):
        lines.append(f"{int(record['min_messages'])} Nachrichten")
    if int(record.get("min_level") or 0):
        lines.append(f"Level {int(record['min_level'])}")
    if int(record.get("min_account_days") or 0):
        lines.append(f"Account {int(record['min_account_days'])} Tage alt")
    if int(record.get("min_member_days") or 0):
        lines.append(f"{int(record['min_member_days'])} Tage auf dem Server")

    return lines


def fill_placeholders(text: str, values: dict[str, Any]) -> str:
    """Replace {prize}, {winners}, {ends}, {host}, {entries} in user text."""
    out = str(text or "")
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out
