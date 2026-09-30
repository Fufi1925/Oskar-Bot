#!/usr/bin/env python3
"""Start the isolated LBoost Shop Discord bot."""
from __future__ import annotations

import logging
import os

import discord

from lbost_shop_bot.client import create_bot

logging.basicConfig(
    level=os.getenv("LBOST_SHOP_BOT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | lbost-shop-bot | %(message)s",
)
logger = logging.getLogger("lbost-shop-bot")


def main() -> None:
    token = os.getenv("LBOST_SHOP_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LBOST_SHOP_BOT_TOKEN is not configured")

    logger.info("Starting isolated Discord client")
    try:
        create_bot(privileged_intents=True).run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        # Discord closes fresh applications with gateway code 4014 when
        # Server Members Intent or Message Content Intent has not yet been
        # enabled in the Developer Portal. Staying permanently offline is the
        # worst fallback: slash commands, dashboard status and all
        # non-privileged features can work without those two flags.
        logger.error(
            "Discord rejected privileged intents. Reconnecting in compatible "
            "mode. Enable Server Members Intent and Message Content Intent in "
            "Developer Portal -> Bot for complete logging and moderation."
        )
        create_bot(privileged_intents=False).run(token, log_handler=None)
    except discord.LoginFailure:
        logger.critical(
            "Discord rejected LBOST_SHOP_BOT_TOKEN. Use the bot token from "
            "Developer Portal -> Bot, not the client secret or application ID."
        )
        raise


if __name__ == "__main__":
    main()
