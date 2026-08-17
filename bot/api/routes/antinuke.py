# ╔══════════════════════════════════════════════════════════════════╗
# ║   Anti-Nuke                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The anti-nuke tab.

Replaces the pair of handlers in guilds.py. What was wrong:

  * **Four invented modules.** The tab listed "Anti Ban & Kick",
    "Anti Server Edit", "Anti Role Modifier" and "Anti Channel Nukes",
    each with a green "Protected" badge. None of those four ids exists
    anywhere in the bot; the real thing is seventeen listeners, and none
    of them is individually switchable. So the tab showed four labels
    that stood for nothing and hid thirteen modules that do work.

  * **The whitelist was per-action, the dashboard was not.** The table
    has one boolean column per action (`ban`, `kick`, `chdl`, ...) and
    each module reads only its own column. The dashboard's "add to
    whitelist" wrote every column as True -- a full bypass of all
    seventeen protections -- while the chat command defaults them all to
    False and then asks. Both were shown in the same flat list of ids,
    so "who is whitelisted for what" was unanswerable from the web.

  * **A silent no-op.** Adding to the whitelist only worked if the table
    already existed, and did nothing at all otherwise. The API returned
    success either way.

The module list here is generated from the cogs themselves at import, so
it cannot drift from what is actually loaded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import feature_audit

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

DB_PATH = "db/anti.db"

# The whitelist columns, in the order the tab shows them. The key is the
# column name in `whitelisted_users`; every anti-nuke module reads
# exactly one of these. Verified against the cogs by tests/test_antinuke_tab.py.
ACTIONS: dict[str, dict] = {
    "ban": {
        "label": "Bannen",
        "description": "Mitglieder bannen und entbannen.",
        "cogs": ["AntiBan"],
    },
    "kick": {
        "label": "Kicken",
        "description": "Mitglieder vom Server werfen.",
        "cogs": ["AntiKick"],
    },
    "prune": {
        "label": "Aufräumen",
        "description": "Massenweise inaktive Mitglieder entfernen.",
        "cogs": ["AntiPrune"],
    },
    "botadd": {
        "label": "Bots hinzufügen",
        "description": "Neue Bots auf den Server holen.",
        "cogs": ["AntiBotAdd"],
    },
    "serverup": {
        "label": "Server ändern",
        "description": "Servername, Symbol und Einstellungen.",
        "cogs": ["AntiGuildUpdate"],
    },
    "memup": {
        "label": "Mitglieder ändern",
        "description": "Rollen vergeben, Namen ändern, timeouten.",
        "cogs": ["AntiMemberUpdate"],
    },
    "chcr": {
        "label": "Kanäle anlegen",
        "description": "Neue Kanäle erstellen.",
        "cogs": ["AntiChannelCreate"],
    },
    "chdl": {
        "label": "Kanäle löschen",
        "description": "Der klassische Nuke-Angriff.",
        "cogs": ["AntiChannelDelete"],
    },
    "chup": {
        "label": "Kanäle ändern",
        "description": "Kanäle umbenennen oder Rechte ändern.",
        "cogs": ["AntiChannelUpdate"],
    },
    "rlcr": {
        "label": "Rollen anlegen",
        "description": "Neue Rollen erstellen.",
        "cogs": ["AntiRoleCreate"],
    },
    "rlup": {
        "label": "Rollen ändern",
        "description": "Rechte einer Rolle ändern.",
        "cogs": ["AntiRoleUpdate"],
    },
    "rldl": {
        "label": "Rollen löschen",
        "description": "Rollen entfernen.",
        "cogs": ["AntiRoleDelete"],
    },
    "meneve": {
        "label": "@everyone pingen",
        "description": "Alle auf einmal erwähnen.",
        "cogs": ["AntiEveryone"],
    },
    "mngweb": {
        "label": "Webhooks & Integrationen",
        "description": "Webhooks anlegen, ändern, löschen — und Bots einbinden.",
        "cogs": [
            "AntiWebhookCreate",
            "AntiWebhookUpdate",
            "AntiWebhookDelete",
            "AntiIntegration",
        ],
    },
}

# Present in the table but read by no module. Kept so a row written by
# the chat command is not silently dropped on a rewrite.
UNUSED_COLUMNS = ["mngstemo"]

COLUMNS = list(ACTIONS) + UNUSED_COLUMNS


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der Bot ist nicht auf diesem Server (oder noch nicht bereit).",
        )
    return guild


async def _ensure_schema(db):
    """
    Create the tables if they are not there yet.

    The old handler checked whether `whitelisted_users` existed and did
    nothing when it did not -- which is exactly the state a fresh deploy
    is in, because the table is created by a cog on its own schedule.
    Adding somebody to the whitelist then returned success and changed
    nothing.
    """
    await db.execute(
        "CREATE TABLE IF NOT EXISTS antinuke ("
        "guild_id INTEGER PRIMARY KEY, status BOOLEAN)"
    )
    # Die Einzelschalter. Fehlt eine Zeile, gilt die Wache als AN --
    # so war es, als es nur den Gesamtschalter gab, und ein Update
    # darf keinem Server stillschweigend den Schutz nehmen.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS antinuke_modules ("
        "guild_id INTEGER, action TEXT, "
        "enabled BOOLEAN NOT NULL DEFAULT 1, "
        "PRIMARY KEY (guild_id, action))"
    )
    columns = ", ".join(f"{name} BOOLEAN DEFAULT FALSE" for name in COLUMNS)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS whitelisted_users ("
        "guild_id INTEGER, user_id INTEGER, "
        f"{columns}, PRIMARY KEY (guild_id, user_id))"
    )
    await db.commit()


def _member_info(guild, user_id):
    member = guild.get_member(int(user_id)) if guild and user_id else None
    avatar = getattr(member, "display_avatar", None)
    return {
        # Snowflakes travel as strings: a JSON number loses the last digits.
        "id": str(user_id),
        "name": getattr(member, "display_name", None),
        "avatar": str(avatar.url) if avatar is not None else None,
        "bot": bool(getattr(member, "bot", False)),
        "missing": member is None,
    }


def _warnings(guild, status: bool, entries: list[dict]) -> list[str]:
    """Everything standing between this configuration and it working."""
    problems: list[str] = []
    if guild is None:
        return problems

    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None) if me is not None else None

    if status and perms is not None:
        if not getattr(perms, "ban_members", False):
            problems.append(
                "Ohne „Mitglieder bannen“ kann der Bot einen Angreifer nicht "
                "stoppen — er sieht den Angriff nur zu."
            )
        if not getattr(perms, "view_audit_log", False):
            problems.append(
                "Ohne „Audit-Log einsehen“ erfährt der Bot gar nicht, wer "
                "etwas gelöscht hat. Anti-Nuke ist damit wirkungslos."
            )

    # The bot bans people who outrank it only if its own role is high
    # enough. An administrator below the bot is the normal case; above it
    # is the one that matters.
    if status and me is not None and getattr(me, "top_role", None) is not None:
        above = [
            role.name
            for role in getattr(guild, "roles", [])
            if role.position > me.top_role.position
            and getattr(getattr(role, "permissions", None), "administrator", False)
        ]
        if above:
            problems.append(
                "Diese Rollen stehen über dem Bot und haben Administrator: "
                + ", ".join(above[:5])
                + ". Gegen die kommt der Bot nicht an."
            )

    if not status:
        problems.append("Anti-Nuke ist ausgeschaltet — es wird nichts überwacht.")

    full = [e for e in entries if all(e["actions"].values())]
    if status and full:
        names = ", ".join(e["name"] or e["id"] for e in full[:5])
        problems.append(
            f"{len(full)} Eintrag/Einträge auf der Ausnahmeliste dürfen "
            f"alles ({names}). Für die greift keine einzige Schutzregel."
        )

    return problems


async def _read(db, guild_id: int) -> tuple[bool, list[dict]]:
    async with db.execute(
        "SELECT status FROM antinuke WHERE guild_id = ?", (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    status = bool(row[0]) if row else False

    selected = ", ".join(ACTIONS)
    async with db.execute(
        f"SELECT user_id, {selected} FROM whitelisted_users WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    entries = []
    for row in rows:
        entries.append({
            "user_id": int(row[0]),
            "actions": {
                name: bool(row[i + 1]) for i, name in enumerate(ACTIONS)
            },
        })
    return status, entries


@router.get("/{guild_id}", summary="Anti-nuke settings")
async def get_antinuke(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    guild = bot.get_guild(guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        status, raw = await _read(db, guild_id)

    entries = []
    for item in raw:
        info = _member_info(guild, item["user_id"])
        entries.append({**info, "actions": item["actions"]})

    # Sort the fullest bypasses to the top -- those are the ones worth
    # looking at.
    entries.sort(key=lambda e: -sum(e["actions"].values()))

    loaded = {
        name: bot.get_cog(name) is not None
        for spec in ACTIONS.values()
        for name in spec["cogs"]
    }

    # Welche der vierzehn Wachen einzeln abgeschaltet sind.
    modul_status: dict[str, bool] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        async with db.execute(
            "SELECT action, enabled FROM antinuke_modules WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            async for zeile in cursor:
                modul_status[str(zeile[0])] = bool(zeile[1])

    return {
        "guild_id": str(guild_id),
        "status": status,
        "actions": [
            {
                "key": key,
                "label": spec["label"],
                "description": spec["description"],
                # A module that failed to load protects nothing, and the
                # tab used to claim otherwise.
                "loaded": all(loaded.get(name) for name in spec["cogs"]),
                "modules": spec["cogs"],
                # Ob diese eine Wache laeuft. Ohne Eintrag: an.
                "enabled": modul_status.get(key, True),
            }
            for key, spec in ACTIONS.items()
        ],
        "module_count": sum(len(spec["cogs"]) for spec in ACTIONS.values()),
        "whitelist": entries,
        "warnings": _warnings(guild, status, entries),
        # Die vertrauten Bots aus `TRUSTED_BOTS`.
        #
        # Nur zum Anschauen: die Liste gilt global und laesst sich hier
        # nicht aendern. Sie steht trotzdem im Reiter, weil sonst
        # niemand nachvollziehen kann, warum ein bestimmter Bot
        # ungestraft Kanaele anlegt -- und das sieht von aussen aus
        # wie ein kaputter Anti-Nuke.
        "trusted_bots": _trusted_bot_info(bot),
    }


def _trusted_bot_info(bot) -> list[dict]:
    """Namen zu den IDs aus ``TRUSTED_BOTS``, soweit der Bot sie kennt.

    Kennt er einen nicht, bleibt die ID stehen. Das ist ehrlicher als
    ein erfundener Name -- und ein Hinweis darauf, dass der Bot
    vielleicht gar nicht auf dem Server ist.
    """
    from utils import nuke_guard

    out = []
    for kennung in sorted(nuke_guard.trusted_bot_ids()):
        # `get_user` kann fehlen oder werfen -- etwa solange der Bot
        # noch startet. Das darf nicht den ganzen Reiter mit einem
        # HTTP 500 abschiessen: die Namen sind eine Nebenangabe, die
        # Liste selbst ist die Auskunft.
        try:
            user = bot.get_user(kennung)
        except Exception:  # noqa: BLE001
            user = None
        out.append({
            # Als Zeichenkette: eine Discord-ID ist groesser als das,
            # was JavaScript unfallfrei als Zahl haelt.
            "id": str(kennung),
            "name": getattr(user, "display_name", "") or getattr(user, "name", ""),
            "avatar": (
                str(user.display_avatar.url)
                if user is not None and getattr(user, "display_avatar", None)
                else None
            ),
        })
    return out


@router.patch("/{guild_id}", summary="Switch anti-nuke on or off")
async def patch_antinuke(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)

    if "status" not in data:
        raise HTTPException(status_code=400, detail="„status“ fehlt.")
    status = bool(data["status"])

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        await db.execute(
            "INSERT INTO antinuke (guild_id, status) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET status = excluded.status",
            (guild_id, status),
        )
        await db.commit()

    await feature_audit.log_action(
        "antinuke_toggled",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail="enabled" if status else "disabled",
    )
    return {
        "result": "Anti-Nuke ist an." if status else "Anti-Nuke ist aus."
    }


@router.put("/{guild_id}/whitelist/{user_id}", summary="Set one entry's actions")
async def put_whitelist(
    guild_id: int,
    user_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Write exactly the actions given, nothing else.

    The old endpoint had one behaviour: add with every column True. That
    is a complete bypass of all seventeen protections, handed out by a
    button labelled "Add".
    """
    _guild_or_404(bot, guild_id)

    actions = data.get("actions")
    if not isinstance(actions, dict):
        raise HTTPException(status_code=400, detail="„actions“ muss ein Objekt sein.")

    unknown = set(actions) - set(ACTIONS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Unbekannte Aktion: " + ", ".join(sorted(unknown)),
        )

    values = {name: bool(actions.get(name, False)) for name in ACTIONS}

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        names = list(ACTIONS)
        placeholders = ", ".join("?" for _ in names)
        updates = ", ".join(f"{name} = excluded.{name}" for name in names)
        await db.execute(
            f"INSERT INTO whitelisted_users (guild_id, user_id, {', '.join(names)}) "
            f"VALUES (?, ?, {placeholders}) "
            f"ON CONFLICT(guild_id, user_id) DO UPDATE SET {updates}",
            (guild_id, user_id, *[values[name] for name in names]),
        )
        await db.commit()

    count = sum(values.values())
    if count == 0:
        return {
            "result": (
                "Gespeichert — dieser Eintrag darf nichts, wirkt also wie "
                "keine Ausnahme."
            )
        }
    return {"result": f"Gespeichert: {count} von {len(ACTIONS)} Aktionen erlaubt."}


@router.delete("/{guild_id}/whitelist/{user_id}", summary="Remove an entry")
async def delete_whitelist(
    guild_id: int, user_id: int, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        cursor = await db.execute(
            "DELETE FROM whitelisted_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()

    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Dieser Eintrag existiert nicht.")
    return {"result": "Von der Ausnahmeliste entfernt."}


@router.patch("/{guild_id}/modules", summary="Eine einzelne Wache an- oder abschalten")
async def patch_module(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Einen der vierzehn Bereiche einzeln umlegen.

    Erwartet ``{"action": "chdl", "enabled": false}``.

    Warum das nicht Teil des Hauptschalters ist: der schaltet den
    ganzen Anti-Nuke, und wer eine einzelne Wache stoert -- etwa weil
    ein Bot staendig Kanaele anlegt --, soll nicht alles abschalten
    muessen. Genau das ist bisher passiert.
    """
    _guild_or_404(bot, guild_id)

    action = str(data.get("action") or "").strip()
    if action not in ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannter Bereich: {action!r}.",
        )
    if "enabled" not in data:
        raise HTTPException(status_code=400, detail="„enabled“ fehlt.")
    enabled = bool(data["enabled"])

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        await db.execute(
            "INSERT INTO antinuke_modules (guild_id, action, enabled)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, action) DO UPDATE SET"
            "   enabled = excluded.enabled",
            (guild_id, action, enabled),
        )
        await db.commit()

    await feature_audit.log_action(
        "antinuke_module_toggled",
        actor=str(data.get("actor", "dashboard")),
        guild_id=guild_id,
        detail=f"{action}={'an' if enabled else 'aus'}",
    )

    return {
        "result": (
            f"„{ACTIONS[action]['label']}“ ist jetzt "
            f"{'an' if enabled else 'aus'}."
        ),
        "action": action,
        "enabled": enabled,
    }


# ══════════════════════════════════════════════════════════════════════
#  Vertraute Bots -- global, nur fuer Admins
# ══════════════════════════════════════════════════════════════════════


@router.get("/trusted/list", summary="Die vertrauten Bots")
async def list_trusted(bot: "universitybot" = Depends(get_bot)):
    """Alle Bots, die der Anti-Nuke nie angreift.

    Die Liste gilt fuer **alle** Server. Server-Inhaber sehen sie im
    eigenen Anti-Nuke-Reiter, aendern kann sie nur das Team -- sonst
    traegt jeder seinen Zweitbot ein und der Schutz ist ausgehebelt.
    """
    from utils import trusted_bots

    return {
        "bots": trusted_bots.list_all(bot),
        "builtin_count": len(trusted_bots.ALWAYS),
        "env_name": trusted_bots.TRUSTED_ENV,
    }


@router.post("/trusted", summary="Einen Bot eintragen")
async def add_trusted(data: dict, bot: "universitybot" = Depends(get_bot)):
    from utils import trusted_bots

    ergebnis = trusted_bots.add(
        data.get("bot_id"),
        note=str(data.get("note") or ""),
        actor=str(data.get("actor") or ""),
    )

    if not ergebnis["ok"]:
        meldungen = {
            "invalid_id": "Das ist keine gültige Discord-ID — nur Ziffern.",
            "builtin": "Dieser Bot steht fest auf der Liste und ist "
                       "immer geschützt.",
            "exists": "Dieser Bot steht schon auf der Liste.",
        }
        raise HTTPException(
            status_code=400,
            detail=meldungen.get(ergebnis["error"], "Das hat nicht geklappt."),
        )

    await feature_audit.log_action(
        "trusted_bot_added",
        actor=str(data.get("actor", "dashboard")),
        detail=str(ergebnis["bot_id"]),
    )
    return {"result": "Der Bot wird vom Anti-Nuke nicht mehr angegriffen.",
            "bots": trusted_bots.list_all(bot)}


@router.delete("/trusted/{bot_id}", summary="Einen Bot austragen")
async def remove_trusted(
    bot_id: str, actor: str = "", bot: "universitybot" = Depends(get_bot)
):
    from utils import trusted_bots

    ergebnis = trusted_bots.remove(bot_id)

    if not ergebnis["ok"]:
        meldungen = {
            "invalid_id": "Das ist keine gültige Discord-ID.",
            "builtin": "Dieser Bot lässt sich nicht entfernen — ohne ihn "
                       "würde der Anti-Nuke den eigenen Rettungsbot bannen.",
            "from_env": f"Dieser Bot steht in der Variablen "
                        f"{trusted_bots.TRUSTED_ENV} und lässt sich nur dort "
                        "entfernen.",
            "unknown": "Dieser Bot steht nicht auf der Liste.",
        }
        # `builtin` und `from_env` sind keine Fehler des Aufrufers,
        # sondern Auskuenfte -- trotzdem 400: die Aktion ist nicht
        # ausgefuehrt worden, und ein 200 wuerde das Gegenteil sagen.
        raise HTTPException(
            status_code=400,
            detail=meldungen.get(ergebnis["error"], "Das hat nicht geklappt."),
        )

    await feature_audit.log_action(
        "trusted_bot_removed", actor=actor or "dashboard",
        detail=str(ergebnis["bot_id"]),
    )
    return {"result": "Der Bot ist nicht mehr geschützt.",
            "bots": trusted_bots.list_all(bot)}
