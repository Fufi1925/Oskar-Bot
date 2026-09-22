#!/usr/bin/env python3
"""Minimal always-on Discord gateway client for the future LBoost Shop bot.

It deliberately registers no commands and handles no messages yet. Keeping the
bot in its own process means future features remain isolated from University
Bot, Louckup and Phantom.
"""
from __future__ import annotations

import logging
import os

import discord

logging.basicConfig(
    level=os.getenv("LBOST_SHOP_BOT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | lbost-shop-bot | %(message)s",
)
logger = logging.getLogger("lbost-shop-bot")


class LBoostShopBot(discord.Client):
    async def on_ready(self) -> None:
        # Readiness logging only: no commands, message handlers or automations.
        logger.info(
            "Connected as %s (%s); %s guild(s); no features enabled yet",
            self.user,
            self.user.id if self.user else "unknown",
            len(self.guilds),
        )


def main() -> None:
    token = os.getenv("LBOST_SHOP_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LBOST_SHOP_BOT_TOKEN is not configured")

    intents = discord.Intents.none()
    intents.guilds = True
    client = LBoostShopBot(intents=intents)
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
