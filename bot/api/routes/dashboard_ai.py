"""Owner-allowlisted, guild-scoped dashboard configuration assistant."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import get_bot
from api.routes import antinuke, automod, leveling, verify
from utils import dashboard_ai, feature_audit, guild_modules, ticket_ai

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


class PlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)


class ApplyRequest(BaseModel):
    plan_id: str = Field(min_length=16, max_length=100)


def _actor(request: Request) -> str:
    actor = request.headers.get("x-firewall-actor", "").strip()
    if not actor.isdigit():
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    return actor


async def _context(request: Request, guild_id: int, bot: "universitybot"):
    actor = _actor(request)
    if not await dashboard_ai.allowed(actor):
        # Do not reveal that an internal pilot exists to arbitrary users.
        raise HTTPException(status_code=404, detail="Not found.")
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Server nicht gefunden.")
    return actor, guild


@router.get("/{guild_id}/access")
async def access(request: Request, guild_id: int, bot: "universitybot" = Depends(get_bot)):
    actor = _actor(request)
    guild = bot.get_guild(guild_id)
    return {
        "allowed": bool(guild is not None and await dashboard_ai.allowed(actor)),
        "key_configured": ticket_ai.api_key_configured(),
    }


@router.post("/{guild_id}/plan")
async def plan(
    request: Request, guild_id: int, data: PlanRequest,
    bot: "universitybot" = Depends(get_bot),
):
    actor, guild = await _context(request, guild_id, bot)
    try:
        return await dashboard_ai.create_plan(
            user_id=actor, guild=guild, message=data.message, history=data.history
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _configure_welcome(guild_id: int, operation: dict) -> None:
    async with aiosqlite.connect("db/welcome.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS welcome (
            guild_id INTEGER PRIMARY KEY,
            welcome_type TEXT,
            welcome_message TEXT,
            channel_id INTEGER,
            embed_data TEXT,
            auto_delete_duration INTEGER
        )""")
        await db.execute(
            """INSERT INTO welcome (guild_id, welcome_type, welcome_message, channel_id)
               VALUES (?, 'simple', ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
                 welcome_type = 'simple', welcome_message = excluded.welcome_message,
                 channel_id = excluded.channel_id""",
            (guild_id, operation["message"], int(operation["channel_id"])),
        )
        await db.commit()
        async with db.execute(
            "SELECT welcome_message, channel_id FROM welcome WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            saved = await cursor.fetchone()
    enabled = bool(operation.get("enabled", True))
    await guild_modules.set_enabled(guild_id, "welcome", enabled)
    if (
        not saved
        or str(saved[0] or "") != str(operation["message"])
        or str(saved[1] or "") != str(operation["channel_id"])
        or await guild_modules.get_enabled(guild_id, "welcome") != enabled
    ):
        raise HTTPException(status_code=500, detail="Die Welcome-Einstellungen wurden nicht vollständig gespeichert.")


@router.post("/{guild_id}/apply")
async def apply_plan(
    request: Request, guild_id: int, data: ApplyRequest,
    bot: "universitybot" = Depends(get_bot),
):
    actor, guild = await _context(request, guild_id, bot)
    try:
        operations = await dashboard_ai.take_plan(data.plan_id, actor, guild_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    applied: list[dict] = []
    for operation in operations:
        kind = operation.get("type")
        if kind == "set_module":
            module = operation["module"]
            enabled = bool(operation["enabled"])
            await guild_modules.set_enabled(guild_id, module, enabled)
            # Anti-Nuke also has its established internal master status. Keep
            # both gates synchronized so "on" means the protection truly runs.
            if module == "antinuke":
                await antinuke.patch_antinuke(
                    guild_id, {"status": enabled, "actor": f"dashboard-ai:{actor}"}, bot
                )
            elif module == "automod":
                await automod.patch_automod(
                    guild_id, {"enabled": enabled, "actor": f"dashboard-ai:{actor}"}, bot
                )
            elif module == "verification":
                await verify.patch_verification(
                    guild_id, {"enabled": enabled, "actor": f"dashboard-ai:{actor}"}, bot
                )
            elif module == "leveling":
                await leveling.patch_leveling(
                    guild_id, {"enabled": enabled, "actor": f"dashboard-ai:{actor}"}, bot
                )
            # Read the persisted gate back before reporting success. This turns
            # a failed/no-op write into an error instead of a false "applied".
            if await guild_modules.get_enabled(guild_id, module) != enabled:
                raise HTTPException(status_code=500, detail=f"{module} wurde nicht gespeichert.")
            applied.append(operation)
        elif kind == "configure_welcome":
            await _configure_welcome(guild_id, operation)
            applied.append(operation)
        elif kind == "antinuke_whitelist":
            actions = {name: name in set(operation["actions"]) for name in antinuke.ACTIONS}
            await antinuke.put_whitelist(
                guild_id, int(operation["user_id"]),
                {"actions": actions, "actor": f"dashboard-ai:{actor}"}, bot,
            )
            async with aiosqlite.connect(antinuke.DB_PATH) as db:
                selected = ", ".join(operation["actions"])
                async with db.execute(
                    f"SELECT {selected} FROM whitelisted_users WHERE guild_id = ? AND user_id = ?",
                    (guild_id, int(operation["user_id"])),
                ) as cursor:
                    saved = await cursor.fetchone()
            if not saved or not all(bool(value) for value in saved):
                raise HTTPException(status_code=500, detail="Die Anti-Nuke-Whitelist wurde nicht gespeichert.")
            applied.append(operation)
        elif kind == "dashboard_api":
            # Executed by the browser through the normal authenticated BFF after
            # this server-side plan was confirmed. Every existing endpoint then
            # re-applies its own guild permission and schema checks.
            applied.append(operation)

    await feature_audit.log_action(
        "dashboard_ai_plan_applied",
        actor=actor,
        guild_id=guild_id,
        detail=json.dumps(
            [{"type": op["type"], "module": op.get("module")} for op in applied]
        )[:1000],
    )
    return {"applied": applied, "count": len(applied)}
