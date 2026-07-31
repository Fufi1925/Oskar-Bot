# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
/key — mint a premium licence key.

Two guards, because a key is worth money:

  * only on the support server, so the command does not even appear
    elsewhere
  * only for people in OWNER_IDS

The key is sent by DM, never into the channel. It is stored hashed, so
that DM is the only copy in existence — if it is lost the key has to be
revoked and a new one issued. That is deliberate: a key readable from
the database would be a key readable by anyone who reaches the database.
"""

from __future__ import annotations

import os

import discord
from discord.ext import commands

from utils import premium_store as store
from utils.config import OWNER_IDS
from utils.cv2 import CV2
from utils.emoji import CROSS, STAR, TICK, ZWARNING

# The support server. Same variable the compose route uses, so the two
# never drift apart.
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID") or 1530378233579704370)


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="key", invoke_without_command=True)
    @commands.guild_only()
    async def key(self, ctx):
        await ctx.send(view=CV2(
            f"{STAR} Premium-Keys",
            "**/key create** — einen neuen Key erstellen\n"
            "**/key revoke** — einen Key sperren\n\n"
            "Nur auf dem Support-Server und nur für das Team.",
        ), ephemeral=True)

    def _may_use(self, ctx) -> bool:
        if ctx.guild is None or ctx.guild.id != HOME_GUILD_ID:
            return False
        return ctx.author.id in OWNER_IDS

    @key.command(name="create")
    @commands.guild_only()
    async def key_create(self, ctx, days: int = 30, *, note: str = ""):
        """
        Mint a key and DM it to the caller.

        days = 0 means it never expires. The clock starts when the key is
        redeemed, not now, so a key sitting unread in a DM is not eaten
        by its own duration.
        """
        if not self._may_use(ctx):
            await ctx.send(view=CV2(
                f"{CROSS} Nicht erlaubt",
                "Diesen Befehl gibt es nur auf dem Support-Server und nur "
                "für das Team.",
            ), ephemeral=True)
            return

        if days < 0 or days > 3650:
            await ctx.send(view=CV2(
                f"{CROSS} Ungültige Laufzeit",
                "Bitte 0 (unbegrenzt) bis 3650 Tage angeben.",
            ), ephemeral=True)
            return

        if not os.getenv(store.PEPPER_ENV, "").strip():
            # Without the pepper the hashes are guessable, and worse:
            # setting it later invalidates every key issued before.
            await ctx.send(view=CV2(
                f"{ZWARNING} Nicht eingerichtet",
                f"`{store.PEPPER_ENV}` ist nicht gesetzt. Ohne diesen Wert "
                "wären die Keys unsicher gespeichert — und wird er später "
                "gesetzt, verfallen alle vorher erstellten Keys.",
            ), ephemeral=True)
            return

        created = store.create_key(
            created_by=ctx.author.id, duration_days=days, note=note,
        )
        laufzeit = "unbegrenzt" if days == 0 else f"{days} Tage ab Einlösung"

        try:
            await ctx.author.send(view=CV2(
                f"{STAR} Premium-Key",
                f"```\n{created['key']}\n```\n"
                f"**Laufzeit:** {laufzeit}\n"
                f"**Für:** Template-Bot\n\n"
                "Diesen Key im Dashboard unter **Premium** eintragen. "
                "Er wird beim Einlösen fest an das Discord-Konto gebunden "
                "und lässt sich danach nicht übertragen.\n\n"
                "Wir speichern den Key nur verschlüsselt — diese Nachricht "
                "ist die einzige Kopie. Geht sie verloren, muss der Key "
                "gesperrt und ein neuer erstellt werden.",
            ))
        except discord.Forbidden:
            # The key already exists at this point. Saying "failed" would
            # be a lie, and the admin needs to know it is out there.
            await ctx.send(view=CV2(
                f"{ZWARNING} Key erstellt, aber keine DM möglich",
                "Der Key wurde erstellt, konnte dir aber nicht per DM "
                "geschickt werden — deine Privatnachrichten sind zu. "
                "Bitte DMs öffnen und den Key sperren, dann einen neuen "
                "erstellen.",
            ), ephemeral=True)
            return

        await ctx.send(view=CV2(
            f"{TICK} Key erstellt",
            f"Der Key ist per DM unterwegs. Laufzeit: **{laufzeit}**.",
        ), ephemeral=True)

    @key.command(name="revoke")
    @commands.guild_only()
    async def key_revoke(self, ctx, key: str):
        """Turn a key off, whether or not it was already redeemed."""
        if not self._may_use(ctx):
            await ctx.send(view=CV2(
                f"{CROSS} Nicht erlaubt",
                "Diesen Befehl gibt es nur auf dem Support-Server und nur "
                "für das Team.",
            ), ephemeral=True)
            return

        if store.revoke(key):
            await ctx.send(view=CV2(
                f"{TICK} Gesperrt",
                "Der Key wurde gesperrt und funktioniert nicht mehr.",
            ), ephemeral=True)
        else:
            await ctx.send(view=CV2(
                f"{CROSS} Nicht gefunden",
                "Zu dieser Eingabe gibt es keinen Key.",
            ), ephemeral=True)


# Registered centrally in cogs/__init__.py, like every other cog here,
# so there is no setup() of its own.
