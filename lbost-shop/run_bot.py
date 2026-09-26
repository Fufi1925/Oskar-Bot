#!/usr/bin/env python3
"""Start the isolated LBoost Shop Discord bot."""
from __future__ import annotations

import logging
import os

from lbost_shop_bot.client import create_bot

logging.basicConfig(
    level=os.getenv("LBOST_SHOP_BOT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | lbost-shop-bot | %(message)s",
)


def main() -> None:
    token = os.getenv("LBOST_SHOP_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LBOST_SHOP_BOT_TOKEN is not configured")
    create_bot().run(token, log_handler=None)


if __name__ == "__main__":
    main()
