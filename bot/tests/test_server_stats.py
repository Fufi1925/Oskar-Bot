#!/usr/bin/env python3
"""Server-Stats: Speicherung, Zählung und vollständige Dashboard-Verkabelung."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOT = ROOT / "bot"
DASH = ROOT / "dashboard"
sys.path.insert(0, str(BOT))


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"  ok   {label}")


async def storage() -> None:
    from utils import server_stats_store as store

    with tempfile.TemporaryDirectory() as tmp:
        old = os.getcwd()
        try:
            os.chdir(tmp)
            Path("db").mkdir()
            check("new guild starts disabled", await store.get(7) == store.DEFAULTS)
            saved = await store.save(7, {"humans_enabled": True})
            check("one counter can be enabled", saved["humans_enabled"] is True)
            check("unsent switches keep their value", saved["bots_enabled"] is False)
            await store.set_channel(7, "humans", 123456789012345678)
            saved = await store.get(7)
            check("Discord snowflakes stay exact", saved["humans_channel_id"] == 123456789012345678)
            check("enabled guild is found by refresh loop", await store.enabled_guild_ids() == [7])
        finally:
            os.chdir(old)


def wiring() -> None:
    server = (BOT / "api/server.py").read_text(encoding="utf-8")
    cogs = (BOT / "cogs/__init__.py").read_text(encoding="utf-8")
    proxy = (DASH / "app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")
    sidebar = (DASH / "app/dashboard/layout.tsx").read_text(encoding="utf-8")
    tabs = (DASH / "components/guild-tabs.tsx").read_text(encoding="utf-8")
    page = DASH / "app/dashboard/guild/[guildId]/server-stats/page.tsx"

    check("API router is mounted", 'prefix="/server-stats"' in server)
    check("event cog is loaded", "add_cog(ServerStats(bot))" in cogs)
    route = (BOT / "api/routes/server_stats.py").read_text(encoding="utf-8")
    panel = (DASH / "components/dashboard/server-stats-panel.tsx").read_text(encoding="utf-8")
    check("BFF authorizes the new scope", 'scope === "server-stats"' in proxy)
    check("premium is enforced by the API", "store.PREMIUM_KINDS" in route and "_has_premium" in route)
    check("premium cards are blurred and locked", "blur-[3px]" in panel and "Premium erforderlich" in panel)
    check("tab sits in the user sidebar", "/server-stats`" in sidebar)
    check("tab is in guild navigation", 'slug: "server-stats"' in tabs)
    check("dashboard page exists", page.is_file())


def counting() -> None:
    from cogs.events.server_stats import ServerStats

    class Member:
        def __init__(self, bot: bool, status: str = "offline"):
            self.bot = bot
            self.status = status

    class Guild:
        members = [Member(False, "online"), Member(False), Member(True, "online")]
        premium_subscription_count = 6
        roles = [object(), object(), object(), object()]  # @everyone + drei
        channels = [object(), object()]

    check(
        "all six statistics are counted correctly",
        ServerStats.counts(Guild()) == {
            "humans": 2,
            "bots": 1,
            "boosts": 6,
            "online": 1,
            "roles": 3,
            "channels": 2,
        },
    )


async def main() -> None:
    print("\nServer Stats")
    await storage()
    counting()
    wiring()
    print("\nAlles bestanden.")


if __name__ == "__main__":
    asyncio.run(main())
