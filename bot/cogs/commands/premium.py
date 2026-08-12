# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The premium role.

Licence keys are minted and revoked in the dashboard under
Admin → Premium; this cog only makes sure the role matches reality.

Handing the role out at redemption would be half a feature, because a
licence also ends. Nothing fires an event when a key expires at three in
the morning, so the role is reconciled on a timer: everyone entitled
gets it, everyone else loses it.
"""

from __future__ import annotations

import os

import discord
from discord.ext import commands, tasks

from utils import bot_settings
from utils import premium_store as store

# The support server. Same variable the compose route uses, so the two
# never drift apart.
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID") or 1530378233579704370)


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_roles.start()

    def cog_unload(self):
        self.sync_roles.cancel()

    # ──────────────────────────────────────────────────────────────
    #  The premium role
    # ──────────────────────────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def sync_roles(self) -> None:
        """
        Keep the premium role in step with who actually has a licence.

        Granting on redemption alone is not enough: a licence also *ends*.
        Nothing fires an event when a key runs out at three in the
        morning, so the role has to be checked on a timer, or an expired
        customer keeps the role forever.

        Ten minutes is a compromise. Faster would mean more requests for
        a thing that changes a few times a day at most.
        """
        try:
            await self._sync_once()
        except Exception as exc:  # noqa: BLE001 - a loop must not die
            print(f"[premium] role sync failed: {exc}")

    @sync_roles.before_loop
    async def _before_sync(self) -> None:
        await self.bot.wait_until_ready()
        # Settings live in the database, and the first read happens after
        # login. Without this the very first pass sees no role id.
        await bot_settings.load()

    async def _sync_once(self) -> dict[str, int]:
        """Add the role to everyone entitled, remove it from everyone else."""
        role_id = bot_settings.get("premium_role", "").strip()
        if not role_id.isdigit():
            return {"added": 0, "removed": 0}

        guild = self.bot.get_guild(HOME_GUILD_ID)
        if guild is None:
            return {"added": 0, "removed": 0}

        role = guild.get_role(int(role_id))
        if role is None:
            return {"added": 0, "removed": 0}

        me = guild.me
        # Discord refuses to manage a role at or above the bot's own top
        # role. Trying anyway just produces a stream of 403s.
        if me is None or not me.guild_permissions.manage_roles \
                or role >= me.top_role:
            print(
                "[premium] cannot manage the premium role — either "
                "'Manage Roles' is missing or the role sits above mine"
            )
            return {"added": 0, "removed": 0}

        entitled = store.premium_user_ids()
        added = removed = 0

        for user_id in entitled:
            member = guild.get_member(int(user_id)) if user_id.isdigit() else None
            if member is not None and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Premium licence active")
                    added += 1
                except discord.HTTPException:
                    pass

        for member in list(role.members):
            if str(member.id) not in entitled:
                try:
                    await member.remove_roles(role, reason="Premium licence ended")
                    removed += 1
                except discord.HTTPException:
                    pass

        return {"added": added, "removed": removed}

    # The /key commands were removed on purpose. Minting a licence is
    # billing work, it belongs in one place with an audit trail, and a
    # chat command that only three people may run is a worse version of
    # a dashboard button. Everything now lives under Admin -> Premium.


# Registered centrally in cogs/__init__.py, like every other cog here,
# so there is no setup() of its own.
