# ╔══════════════════════════════════════════════════════════════════╗
# ║   Diagnose: is the running bot actually wired up?                ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Answers "the dashboard saves but Discord does nothing" without guessing.

That symptom has several possible causes and they are indistinguishable
from the outside: the cog failed to load, its database connection is
dead, the settings were written for a different guild, a required intent
is off, or the bot is missing a permission in the channel. Each one
looks exactly the same to somebody clicking Save.

This route checks all of them against the *running* process and reports
what it finds, so the next step is a fact rather than a theory.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from api.dependencies import get_bot

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

# The features rewritten recently, with the cog that has to be alive, the
# database it needs and the intent without which it cannot work.
FEATURES = [
    {
        "key": "anonchat", "label": "Anonymer Chat",
        "cog": "AnonChat", "db": "db/anonchat.db",
        "intents": ["message_content"],
        "listener": "on_message",
    },
    {
        "key": "vanity", "label": "Vanity-Rollen",
        "cog": "VanityRoles", "db": "db/vanity.db",
        "intents": ["presences", "members"],
        "listener": "on_presence_update",
    },
    {
        "key": "leveling", "label": "Level-System",
        "cog": "Leveling", "db": "db/leveling.db",
        "intents": ["message_content"],
        "listener": "on_message",
    },
    {
        "key": "giveaways", "label": "Gewinnspiele",
        "cog": "Giveaway", "db": "db/giveaways.db",
        "intents": [],
        "listener": "on_interaction",
    },
]


def _intent_state(bot, names: list[str]) -> dict[str, bool]:
    intents = getattr(bot, "intents", None)
    if intents is None:
        return {name: False for name in names}
    return {name: bool(getattr(intents, name, False)) for name in names}


async def _db_state(path: str) -> dict:
    """Whether the file exists and can be read right now."""
    state = {"path": path, "exists": os.path.isfile(path), "readable": False,
             "tables": 0, "error": ""}
    if not state["exists"]:
        state["error"] = "Datei existiert nicht — noch nie etwas gespeichert?"
        return state

    try:
        import aiosqlite

        async with aiosqlite.connect(path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ) as cursor:
                state["tables"] = (await cursor.fetchone())[0]
        state["readable"] = True
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
    return state


@router.get("/diagnose", summary="Why is nothing happening in Discord?")
async def diagnose(
    guild_id: str = "", bot: "universitybot" = Depends(get_bot)
):
    """
    A per-feature report from the running process.

    Pass `guild_id` to also check the permissions and the stored settings
    for one server, which is where the answer usually is.
    """
    guild = None
    if guild_id.isdigit():
        guild = bot.get_guild(int(guild_id))

    report = []
    for feature in FEATURES:
        cog = bot.get_cog(feature["cog"])
        connection = getattr(cog, "connection", "n/a") if cog else None

        # A cog that loaded but holds no connection is alive and useless —
        # the exact shape of "saves fine, does nothing".
        if cog is None:
            state, hint = "missing", (
                f"Der Cog {feature['cog']} ist nicht geladen. Im Startlog nach "
                f"„Failed to load extension\" suchen."
            )
        elif connection is None:
            state, hint = "no_database", (
                "Der Cog läuft, hat aber keine Datenbankverbindung. Alles, was "
                "im Dashboard gespeichert wird, erreicht ihn nie."
            )
        else:
            state, hint = "ok", ""

        intents = _intent_state(bot, feature["intents"])
        missing_intents = [name for name, on in intents.items() if not on]
        if state == "ok" and missing_intents:
            state = "intent_off"
            hint = (
                f"Der Intent {', '.join(missing_intents)} ist aus. Ohne ihn sieht "
                "der Bot die Ereignisse gar nicht. Im Discord Developer Portal "
                "unter Bot → Privileged Gateway Intents einschalten."
            )

        listeners = 0
        try:
            listeners = len(bot.extra_events.get(feature["listener"], []))
        except Exception:
            pass

        entry = {
            "key": feature["key"],
            "label": feature["label"],
            "state": state,
            "hint": hint,
            "cog_loaded": cog is not None,
            "has_connection": connection is not None and connection != "n/a",
            "intents": intents,
            "listeners": listeners,
            "database": await _db_state(feature["db"]),
        }

        # What is actually stored for this guild, since "saved for the
        # wrong server" looks identical to "not saved".
        if guild is not None:
            entry["guild"] = await _guild_state(feature["key"], guild)

        report.append(entry)

    return {
        "bot_ready": bot.is_ready() if hasattr(bot, "is_ready") else None,
        "guild_count": len(bot.guilds),
        "checked_guild": (
            {"id": str(guild.id), "name": guild.name} if guild else None
        ),
        "working_directory": os.getcwd(),
        "features": report,
    }


async def _guild_state(key: str, guild) -> dict:
    """What is stored for this guild, and can the bot act on it."""
    out: dict = {"configured": 0, "problems": []}
    me = guild.me

    try:
        if key == "anonchat":
            from api.db_manager import db_manager
            from utils import anonchat_store as store

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            channels = await store.list_channels(db, guild.id)
            out["configured"] = len(channels)

            for setup in channels:
                channel = guild.get_channel(setup["channel_id"])
                if channel is None:
                    out["problems"].append("Ein eingerichteter Kanal existiert nicht mehr.")
                    continue
                permissions = channel.permissions_for(me) if me else None
                if permissions and not permissions.manage_messages:
                    out["problems"].append(
                        f"#{channel.name}: „Nachrichten verwalten“ fehlt — die "
                        "Originalnachricht bleibt stehen."
                    )
                if permissions and not permissions.send_messages:
                    out["problems"].append(f"#{channel.name}: Der Bot darf nicht schreiben.")

        elif key == "vanity":
            from api.db_manager import db_manager
            from utils import vanity_store as store

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            setups = await store.list_setups(db, guild.id)
            out["configured"] = len(setups)

            for setup in setups:
                role = guild.get_role(setup["role_id"])
                if role is None:
                    out["problems"].append(f"`{setup['vanity']}`: Die Rolle wurde gelöscht.")
                elif me and role >= me.top_role:
                    out["problems"].append(
                        f"@{role.name} steht über der Bot-Rolle und kann nicht "
                        "vergeben werden."
                    )

        elif key == "leveling":
            from api.db_manager import db_manager
            from utils import leveling_store as store

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            settings = await store.get_settings(db, guild.id)
            out["configured"] = 1 if settings.get("enabled") else 0
            if not settings.get("enabled"):
                out["problems"].append(
                    "Das Level-System ist für diesen Server ausgeschaltet."
                )

        elif key == "giveaways":
            from api.db_manager import db_manager
            from api import giveaways as store

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            async with db.execute(
                "SELECT COUNT(*) FROM Giveaway WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                out["configured"] = (await cursor.fetchone())[0]

    except Exception as exc:
        out["problems"].append(f"Prüfung fehlgeschlagen: {type(exc).__name__}: {exc}")

    if me is not None and not me.guild_permissions.manage_roles:
        out["problems"].append("Dem Bot fehlt serverweit „Rollen verwalten“.")

    return out
