"""Cloudtix artwork used by Discord messages and the main bot profile."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from urllib.parse import quote

import aiosqlite
import discord

from utils.links import dashboard_url


BRAND_ASSET_VERSION = "26d55bf24aa4"
BRAND_FILENAME = "cloudtix_pf weiß.gif"
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
logger = logging.getLogger(__name__)


def brand_logo_url() -> str:
    """Use the deployed artwork, with a public fallback for standalone bots."""
    base = dashboard_url() or (
        "https://raw.githubusercontent.com/Fufi1925/Oskar-Bot/main/dashboard/public"
    )
    return f"{base}/{quote(BRAND_FILENAME)}?v={BRAND_ASSET_VERSION}"


async def _sync_image(db, profile, field: str, artwork: Path) -> None:
    image = await asyncio.to_thread(artwork.read_bytes)
    digest = hashlib.sha256(image).hexdigest()
    current = getattr(profile, field)
    current_hash = current.key if current else ""
    async with db.execute(
        "SELECT digest, remote_hash FROM brand_images WHERE profile_id=? AND field=?",
        (str(profile.id), field),
    ) as cursor:
        saved = await cursor.fetchone()
    if saved and tuple(saved) == (digest, current_hash):
        return

    updated = await profile.edit(**{field: image})
    remote = getattr(updated, field)
    await db.execute(
        "INSERT OR REPLACE INTO brand_images (profile_id, field, digest, remote_hash) "
        "VALUES (?, ?, ?, ?)",
        (str(profile.id), field, digest, remote.key if remote else ""),
    )
    await db.commit()
    logger.info("Cloudtix artwork updated: %s", field)


async def sync_discord_branding(bot) -> None:
    """Update changed artwork once; keep the saved hashes across deployments."""
    if bot.user is None:
        return

    try:
        async with aiosqlite.connect("db/branding.db") as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS brand_images ("
                "profile_id TEXT, field TEXT, digest TEXT, remote_hash TEXT, "
                "PRIMARY KEY (profile_id, field))"
            )
            try:
                await _sync_image(db, bot.user, "avatar", ASSET_DIR / "cloudtix-avatar.gif")
            except (discord.HTTPException, OSError, aiosqlite.Error):
                logger.exception("Cloudtix bot avatar could not be updated")

            try:
                application = await bot.application_info()
                await _sync_image(db, application, "icon", ASSET_DIR / "cloudtix-icon.png")
            except (discord.HTTPException, OSError, aiosqlite.Error):
                logger.exception("Cloudtix application icon could not be updated")
    except aiosqlite.Error:
        logger.exception("Cloudtix artwork state could not be saved")
