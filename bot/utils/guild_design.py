"""
Design: wie der Bot auf einem bestimmten Server aussieht.

Was hier geht -- und was ausdruecklich nicht
--------------------------------------------
Geaendert wird nur das **Server-Profil**: Nickname, Server-Avatar und
Server-Banner. Das gilt genau auf diesem einen Server; ueberall sonst
bleibt der Bot, wie er ist.

Der globale Name bleibt bewusst aussen vor. Discord laesst nur zwei
Namensaenderungen pro Stunde zu, und eine davon traefe alle Server auf
einmal -- ein Server koennte damit das Aussehen fuer alle anderen
bestimmen.

Wer darf das
------------
Premium haengt am Discord-Konto (`product="main_bot"`). Zusaetzlich
muss eine von zwei Bedingungen erfuellt sein:

  * die Person ist **Inhaber** des Servers, oder
  * der Server steht auf der Freischaltliste, die das Admin-Dashboard
    pflegt.

Die Freischaltliste taucht im Nutzer-Dashboard nirgends auf -- weder
als Text noch als Zustand in der Antwort. Fuer den Nutzer sieht ein
freigeschalteter Server genauso aus wie einer, auf dem er Inhaber
ist.

Speicher
--------
`db/guild_design.db`. Braucht ein Railway-Volume, sonst sind die
Einstellungen und die Freischaltungen nach jedem Deploy weg.
"""

from __future__ import annotations

import time

import aiosqlite

DB_PATH = "db/guild_design.db"

#: Discord-Grenzen. Ein Nickname darf 32 Zeichen haben; darueber
#: antwortet die API mit 400, und der Fehler kaeme erst beim Speichern.
MAX_NICK = 32

#: Bilder. Discord nimmt bis 10 MB, aber alles darueber ist ohnehin
#: unsinnig fuer ein Avatarbild -- und der Upload laeuft durch den
#: Bot-Container.
MAX_IMAGE_BYTES = 8 * 1024 * 1024

#: Welche Formate Discord fuer Avatar und Banner annimmt.
ERLAUBTE_TYPEN = ("image/png", "image/jpeg", "image/gif", "image/webp")


COLUMNS: tuple[tuple[str, str], ...] = (
    ("nickname", "TEXT"),
    ("avatar_url", "TEXT"),
    ("banner_url", "TEXT"),
    ("updated_at", "REAL DEFAULT 0"),
    ("updated_by", "TEXT"),
)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_design (
            guild_id INTEGER PRIMARY KEY
        )
        """
    )
    for name, typ in COLUMNS:
        try:
            await db.execute(f"ALTER TABLE guild_design ADD COLUMN {name} {typ}")
        except Exception:  # noqa: BLE001 - Spalte existiert bereits
            pass

    # Die Freischaltliste.
    #
    # Eigene Tabelle, nicht eine Spalte in `guild_design`: ein Server
    # kann freigeschaltet sein, ohne je ein Design gespeichert zu
    # haben, und eine Freischaltung soll das Loeschen der Einstellungen
    # ueberleben.
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS design_unlocked (
            guild_id   INTEGER PRIMARY KEY,
            granted_at REAL,
            granted_by TEXT,
            note       TEXT
        )
        """
    )
    await db.commit()


async def get(db: aiosqlite.Connection, guild_id: int) -> dict:
    """Das gespeicherte Design -- immer vollstaendig, nie None."""
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM guild_design WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        zeile = await cursor.fetchone()

    if zeile is None:
        return {
            "guild_id": guild_id,
            "nickname": None,
            "avatar_url": None,
            "banner_url": None,
            "updated_at": 0.0,
            "updated_by": None,
        }

    daten = dict(zeile)
    return {
        "guild_id": guild_id,
        "nickname": daten.get("nickname") or None,
        "avatar_url": daten.get("avatar_url") or None,
        "banner_url": daten.get("banner_url") or None,
        "updated_at": float(daten.get("updated_at") or 0),
        "updated_by": daten.get("updated_by") or None,
    }


async def save(db: aiosqlite.Connection, guild_id: int, *,
               actor: str | None = None, **felder) -> dict:
    """Einzelne Felder aendern; alles Uebrige bleibt stehen."""
    erlaubt = {name for name, _ in COLUMNS}
    zu_setzen: dict[str, object] = {}

    for schluessel, wert in felder.items():
        if schluessel not in erlaubt:
            continue
        if schluessel == "nickname":
            text = str(wert or "").strip()
            wert = text[:MAX_NICK] if text else None
        elif schluessel in ("avatar_url", "banner_url"):
            text = str(wert or "").strip()
            wert = text or None
        zu_setzen[schluessel] = wert

    if not zu_setzen:
        return await get(db, guild_id)

    zu_setzen["updated_at"] = time.time()
    if actor:
        zu_setzen["updated_by"] = str(actor)

    await db.execute(
        "INSERT OR IGNORE INTO guild_design (guild_id) VALUES (?)", (guild_id,)
    )
    zuweisung = ", ".join(f"{name} = ?" for name in zu_setzen)
    await db.execute(
        f"UPDATE guild_design SET {zuweisung} WHERE guild_id = ?",
        (*zu_setzen.values(), guild_id),
    )
    await db.commit()
    return await get(db, guild_id)


async def clear(db: aiosqlite.Connection, guild_id: int, *,
                actor: str | None = None) -> dict:
    """Alle gespeicherten Design-Felder loeschen.

    Wird beim Knopf „Auf Standard“ gebraucht. Die Zeile selbst bleibt
    stehen -- `updated_at` und `updated_by` sollen zeigen, WANN und von
    WEM zurueckgesetzt wurde. Eine geloeschte Zeile koennte das nicht.

    Die Freischaltung bleibt unberuehrt: sie liegt in einer eigenen
    Tabelle, damit ein Zuruecksetzen sie nicht mitnimmt.
    """
    await db.execute(
        "INSERT OR IGNORE INTO guild_design (guild_id) VALUES (?)", (guild_id,)
    )
    await db.execute(
        "UPDATE guild_design SET nickname = NULL, avatar_url = NULL, "
        "banner_url = NULL, updated_at = ?, updated_by = ? WHERE guild_id = ?",
        (time.time(), str(actor or ""), guild_id),
    )
    await db.commit()
    return await get(db, guild_id)


# ── Die Freischaltliste ──────────────────────────────────────────────
#
# Gepflegt im Admin-Dashboard. Im Nutzer-Dashboard darf sie nirgends
# sichtbar werden -- ausdrueckliche Vorgabe. Ein freigeschalteter
# Server sieht dort genauso aus wie einer, auf dem die Person Inhaber
# ist.


async def is_unlocked(db: aiosqlite.Connection, guild_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM design_unlocked WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        return await cursor.fetchone() is not None


async def unlock(db: aiosqlite.Connection, guild_id: int, *,
                 by: str = "", note: str = "") -> None:
    await db.execute(
        "INSERT OR REPLACE INTO design_unlocked "
        "(guild_id, granted_at, granted_by, note) VALUES (?, ?, ?, ?)",
        (guild_id, time.time(), str(by or ""), str(note or "")[:200]),
    )
    await db.commit()


async def lock(db: aiosqlite.Connection, guild_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM design_unlocked WHERE guild_id = ?", (guild_id,)
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0


async def unlocked_list(db: aiosqlite.Connection) -> list[dict]:
    """Alle freigeschalteten Server -- nur fuers Admin-Dashboard."""
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM design_unlocked ORDER BY granted_at DESC"
    ) as cursor:
        zeilen = await cursor.fetchall()

    return [
        {
            # Als Zeichenkette: eine Discord-ID ist groesser als das,
            # was JavaScript als Zahl noch genau darstellen kann.
            "guild_id": str(z["guild_id"]),
            "granted_at": float(z["granted_at"] or 0),
            "granted_by": z["granted_by"] or "",
            "note": z["note"] or "",
        }
        for z in zeilen
    ]


async def may_edit(db: aiosqlite.Connection, guild, user_id: int | str) -> bool:
    """Darf diese Person das Design dieses Servers aendern?

    Premium allein genuegt nicht -- sonst koennte jeder mit einem Key
    das Aussehen auf jedem Server bestimmen, auf dem er zufaellig
    Rechte hat. Zusaetzlich muss er Inhaber sein oder der Server
    freigeschaltet.
    """
    if guild is None:
        return False
    try:
        if int(user_id) == int(getattr(guild, "owner_id", 0) or 0):
            return True
    except (TypeError, ValueError):
        pass
    return await is_unlocked(db, int(guild.id))
