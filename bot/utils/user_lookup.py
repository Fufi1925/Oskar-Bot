"""
Einen Nutzer nachschlagen -- und dann etwas gegen ihn tun.

Vier Dinge stecken hier drin, und sie gehoeren zusammen, weil sie alle
dieselbe Frage beantworten: *wer ist diese ID und wo taucht sie auf?*

  * **Profil und Server.** Zu einer eingegebenen ID alles, was der Bot
    ueber sie weiss -- inklusive **jedem** gemeinsamen Server, nicht nur
    denen, auf die der Betrachter Zugriff hat. Genau das war vorher
    nicht moeglich: ``/access/users/{id}`` listet ausschliesslich
    ``reachable``, also Server, in denen die Person selbst Rechte hat.
  * **Bot-Sperre.** Eine harte Sperre, die mehr ist als die bisherige
    ``user_blacklist``: die blockte nur Befehle. Gemessen (siehe
    ``repro/check_blacklist_reach.py``) liess sie den Dashboard-Login
    zu und hinderte niemanden daran, den Bot einzuladen.
  * **Bann auf allen Servern.** Der Bot bannt die Person ueberall, wo er
    sie erreicht und die Rechte dazu hat.
  * **Warnung an die Inhaber.** Eine DM an jeden Server-Inhaber, auf
    dessen Server die Person ist -- ohne selbst etwas zu tun.

Die drei Massnahmen sind bewusst getrennt. "Der darf den Bot nicht mehr
benutzen" und "der fliegt von 40 Servern" sind sehr verschiedene Dinge,
und wer nur das eine will, soll nicht das andere ausloesen.

Die Sperre wird **zusaetzlich** in die bestehende ``user_blacklist``
geschrieben. Sonst muesste jeder der 175 Befehle einzeln umgestellt
werden -- ``blacklist_check()`` fragt genau diese Tabelle ab, und so
greift die Sperre sofort ueberall.
"""

from __future__ import annotations

import time

from utils import db_paths

LOOKUP_DB = "db/user_lookup.db"
BLOCK_DB = "db/block.db"

# Gruende, die im Dashboard zur Auswahl stehen. Freitext geht auch.
STANDARD_GRUENDE = (
    "Nuke-Versuch",
    "Raid / Massenspam",
    "Werbung per DM",
    "Betrug",
    "Belaestigung",
    "Umgehung einer Sperre",
)


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS bot_bans ("
        " user_id TEXT PRIMARY KEY,"
        " reason TEXT DEFAULT '',"
        " banned_by TEXT,"
        " banned_at INTEGER NOT NULL,"
        " note TEXT DEFAULT '')"
    )
    # Was ein Massenbann bewirkt hat. Ohne Protokoll laesst sich
    # hinterher nicht sagen, auf welchen Servern es geklappt hat.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS mass_actions ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " user_id TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " actor TEXT,"
        " reason TEXT DEFAULT '',"
        " ok_count INTEGER DEFAULT 0,"
        " fail_count INTEGER DEFAULT 0,"
        " detail TEXT DEFAULT '',"
        " created_at INTEGER NOT NULL)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mass_actions_user"
        " ON mass_actions (user_id, created_at)"
    )
    await db.commit()


# ── Die Bot-Sperre ───────────────────────────────────────────────────

async def ban_from_bot(
    user_id: int | str, *, reason: str = "", actor: str = "", note: str = ""
) -> dict:
    """
    Jemanden komplett vom Bot aussperren.

    Schreibt in zwei Tabellen: die eigene mit Grund und Zeitpunkt, und
    die alte ``user_blacklist``. Nur ueber die zweite greifen die
    bestehenden ``blacklist_check()``-Pruefungen in allen Befehlen.
    """
    uid = str(user_id)
    jetzt = int(time.time())
    reason = (reason or "").strip()[:500]

    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO bot_bans (user_id, reason, banned_by, banned_at, note)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " reason = excluded.reason, banned_by = excluded.banned_by,"
            " banned_at = excluded.banned_at, note = excluded.note",
            (uid, reason, str(actor), jetzt, (note or "")[:1000]),
        )
        await db.commit()

    # Und in die Tabelle, die alle Befehle ohnehin schon abfragen.
    async with db_paths.connect(BLOCK_DB) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT PRIMARY KEY)"
        )
        await db.execute(
            "INSERT OR IGNORE INTO user_blacklist (user_id) VALUES (?)", (uid,)
        )
        await db.commit()

    return {"user_id": uid, "reason": reason, "banned_at": jetzt}


async def unban_from_bot(user_id: int | str) -> bool:
    """Sperre aufheben -- in beiden Tabellen."""
    uid = str(user_id)
    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute("DELETE FROM bot_bans WHERE user_id = ?", (uid,))
        await db.commit()
        entfernt = (cursor.rowcount or 0) > 0

    async with db_paths.connect(BLOCK_DB) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT PRIMARY KEY)"
        )
        await db.execute("DELETE FROM user_blacklist WHERE user_id = ?", (uid,))
        await db.commit()

    return entfernt


async def get_ban(user_id: int | str) -> dict | None:
    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id, reason, banned_by, banned_at, note"
            " FROM bot_bans WHERE user_id = ?",
            (str(user_id),),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "user_id": str(row[0]),
        "reason": row[1] or "",
        "banned_by": str(row[2] or ""),
        "banned_at": int(row[3] or 0),
        "note": row[4] or "",
    }


async def is_banned(user_id: int | str) -> bool:
    return await get_ban(user_id) is not None


async def list_bans() -> list[dict]:
    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id, reason, banned_by, banned_at, note"
            " FROM bot_bans ORDER BY banned_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "user_id": str(r[0]),
            "reason": r[1] or "",
            "banned_by": str(r[2] or ""),
            "banned_at": int(r[3] or 0),
            "note": r[4] or "",
        }
        for r in rows
    ]


# ── Protokoll der Massenaktionen ─────────────────────────────────────

async def record_action(
    user_id: int | str,
    kind: str,
    *,
    actor: str = "",
    reason: str = "",
    ok_count: int = 0,
    fail_count: int = 0,
    detail: str = "",
) -> int:
    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "INSERT INTO mass_actions"
            " (user_id, kind, actor, reason, ok_count, fail_count, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(user_id), kind, str(actor), (reason or "")[:500],
                int(ok_count), int(fail_count), (detail or "")[:2000],
                int(time.time()),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def recent_actions(user_id: int | str | None = None, limit: int = 50) -> list[dict]:
    async with db_paths.connect(LOOKUP_DB) as db:
        await ensure_schema(db)
        if user_id is None:
            query = (
                "SELECT id, user_id, kind, actor, reason, ok_count, fail_count,"
                " detail, created_at FROM mass_actions"
                " ORDER BY created_at DESC LIMIT ?"
            )
            args: tuple = (max(1, min(limit, 200)),)
        else:
            query = (
                "SELECT id, user_id, kind, actor, reason, ok_count, fail_count,"
                " detail, created_at FROM mass_actions WHERE user_id = ?"
                " ORDER BY created_at DESC LIMIT ?"
            )
            args = (str(user_id), max(1, min(limit, 200)))

        async with db.execute(query, args) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": int(r[0]),
            "user_id": str(r[1]),
            "kind": r[2],
            "actor": str(r[3] or ""),
            "reason": r[4] or "",
            "ok_count": int(r[5] or 0),
            "fail_count": int(r[6] or 0),
            "detail": r[7] or "",
            "created_at": int(r[8] or 0),
        }
        for r in rows
    ]


# ── Nachschlagen ─────────────────────────────────────────────────────

def _avatar_url(user) -> str | None:
    try:
        return user.display_avatar.url
    except Exception:
        return None


async def lookup(bot, user_id: int | str) -> dict:
    """
    Alles, was der Bot ueber diese ID weiss.

    Wichtig ist die Liste der Server: **jeder** gemeinsame Server, in
    dem die Person Mitglied ist. Ob der Betrachter dort Rechte hat,
    spielt keine Rolle -- gerade das ist der Sinn der Uebersicht.
    Deshalb darf sie auch nur, wer global handeln darf; die Pruefung
    steht in der Route.

    Findet der Bot die Person nirgends, wird trotzdem versucht, das
    Discord-Profil zu holen. Jemanden sperren zu koennen, den man noch
    nicht teilt, ist genau der Fall, um den es geht.
    """
    uid = int(user_id)

    user = bot.get_user(uid)
    fetched = False
    if user is None:
        try:
            user = await bot.fetch_user(uid)
            fetched = True
        except Exception:
            user = None

    # Jeder gemeinsame Server. `guild.get_member` geht ueber den Cache und
    # ist damit still unvollstaendig, wenn der Members-Intent fehlt --
    # deshalb steht die Zahl der eingelesenen Mitglieder mit dabei.
    server: list[dict] = []
    for guild in bot.guilds:
        member = guild.get_member(uid)
        if member is None:
            continue

        inhaber = guild.owner_id == uid
        try:
            hoechste = member.top_role.name if member.top_role else None
            position = member.top_role.position if member.top_role else 0
        except Exception:
            hoechste, position = None, 0

        server.append({
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "guild_icon": guild.icon.url if guild.icon else None,
            "member_count": guild.member_count or len(guild.members),
            "is_owner": inhaber,
            "is_admin": bool(member.guild_permissions.administrator),
            "top_role": hoechste,
            "top_role_position": position,
            "joined_at": int(member.joined_at.timestamp()) if member.joined_at else 0,
            "roles": [r.name for r in member.roles if r.name != "@everyone"][:20],
            # Kann der Bot hier ueberhaupt bannen? Sonst verspricht die
            # Oberflaeche etwas, das nachher scheitert.
            "bot_can_ban": bool(
                guild.me
                and guild.me.guild_permissions.ban_members
                and (guild.me.top_role > member.top_role)
                and guild.owner_id != uid
            ),
        })

    server.sort(key=lambda s: (-s["member_count"], s["guild_name"]))

    ban = await get_ban(uid)

    return {
        "user_id": str(uid),
        "found": user is not None,
        "fetched_from_discord": fetched,
        "username": str(user) if user else None,
        "display_name": getattr(user, "display_name", None) if user else None,
        "avatar": _avatar_url(user) if user else None,
        "is_bot": bool(getattr(user, "bot", False)) if user else False,
        "created_at": int(user.created_at.timestamp()) if user else 0,
        "guilds": server,
        "guild_count": len(server),
        "bannable_count": sum(1 for s in server if s["bot_can_ban"]),
        "owner_of_count": sum(1 for s in server if s["is_owner"]),
        "admin_of_count": sum(1 for s in server if s["is_admin"]),
        "bot_ban": ban,
        "history": await recent_actions(uid, limit=20),
    }
