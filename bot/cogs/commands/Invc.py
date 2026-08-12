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
Voice roles: hand out a role while someone sits in a voice channel.

Rewritten because the dashboard and the cog disagreed about what the
feature even was:

  * The dashboard showed an on/off switch and the API stored it in an
    ``enabled`` column -- but the cog only ran
    ``SELECT role_id FROM vcroles``. It never read ``enabled``, so
    switching the feature off changed a number in the database and
    nothing else. The bot carried on handing the role out.

  * The cog refused a second role ("VC role is already set in this
    guild") because the table was keyed on ``guild_id`` alone. Multiple
    roles are now stored one per row.

  * ``on_voice_state_update`` also fires when someone mutes, deafens or
    starts streaming. The old code re-checked the role on every one of
    those, so a channel full of people toggling mute meant a stream of
    pointless API calls. It now returns early unless the channel
    actually changed.

Which channels count is configurable; empty means all of them.
"""

import asyncio

import aiosqlite
import discord
from discord.ext import commands

from utils import voice_store as store
from utils.Tools import *          # noqa: F401,F403  (blacklist_check, ignore_check)
from utils.config import *         # noqa: F401,F403  (BRAND_NAME)
from utils.cv2 import CV2


class Invcrole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = store.VOICEROLE_DB

    async def _db(self):
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        return db

    async def settings(self, guild_id: int) -> dict:
        db = await self._db()
        try:
            return await store.voicerole_get(db, guild_id)
        finally:
            await db.close()

    async def refresh(self, guild_id=None):
        """Nothing is cached; the dashboard's reload hook is satisfied."""
        return True

    # ──────────────────────────────────────────────────────────────
    #  Commands
    # ──────────────────────────────────────────────────────────────

    @commands.group(name="vcrole", help="Voice role setup", invoke_without_command=True)
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.has_permissions(administrator=True)
    async def vcrole(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @vcrole.command(name="add", help="Add a role that voice members receive")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.has_permissions(administrator=True)
    async def add(self, ctx, role: discord.Role):
        problem = self._role_problem(ctx.guild, role)
        if problem:
            await ctx.reply(view=CV2("⚠️ Geht nicht", problem))
            return

        current = await self.settings(ctx.guild.id)
        if role.id in current["roles"]:
            await ctx.reply(view=CV2(
                "⚠️ Schon drin", f"{role.mention} ist bereits eingetragen."
            ))
            return

        db = await self._db()
        try:
            saved = await store.voicerole_save(db, ctx.guild.id, {
                "roles": current["roles"] + [role.id],
                # Adding the first role with the feature off would look
                # broken, so it switches itself on.
                "enabled": True if not current["roles"] else current["enabled"],
            })
        finally:
            await db.close()

        await ctx.reply(view=CV2(
            "✅ Gespeichert",
            f"{role.mention} kommt jetzt dazu, solange jemand im Sprachkanal ist.\n"
            f"Insgesamt eingetragen: **{len(saved['roles'])}**",
        ))

    @vcrole.command(name="remove", aliases=["reset"], help="Remove a voice role")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, role: discord.Role):
        current = await self.settings(ctx.guild.id)
        if role.id not in current["roles"]:
            await ctx.send(view=CV2("❌ Nicht gefunden",
                                    "Diese Rolle ist gar nicht eingetragen."))
            return

        db = await self._db()
        try:
            saved = await store.voicerole_save(db, ctx.guild.id, {
                "roles": [r for r in current["roles"] if r != role.id],
            })
        finally:
            await db.close()

        await ctx.send(view=CV2(
            "✅ Entfernt",
            f"{role.mention} wird nicht mehr vergeben.\n"
            f"Noch eingetragen: **{len(saved['roles'])}**",
        ))

    @vcrole.command(name="toggle", help="Switch voice roles on or off")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx, mode: str = None):
        current = await self.settings(ctx.guild.id)
        if mode is None:
            value = not current["enabled"]
        else:
            value = mode.lower() in ("on", "an", "true", "yes", "ja", "1")

        db = await self._db()
        try:
            await store.voicerole_save(db, ctx.guild.id, {"enabled": value})
        finally:
            await db.close()

        await ctx.send(view=CV2(
            "Voice Roles",
            "✅ Eingeschaltet." if value else "🛑 Ausgeschaltet.",
        ))

    @vcrole.command(name="config", aliases=["view", "show"], help="Show the setup")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        settings = await self.settings(ctx.guild.id)

        if not settings["roles"]:
            await ctx.send(view=CV2(
                "Voice Roles",
                "Es ist noch keine Rolle eingetragen.\n"
                f"`{ctx.clean_prefix}vcrole add @rolle` legt eine an.",
            ))
            return

        roles = "\n".join(
            f"• <@&{r}>" if ctx.guild.get_role(r) else f"• (gelöschte Rolle {r})"
            for r in settings["roles"]
        )
        if settings["channels"]:
            where = "\n".join(f"• <#{c}>" for c in settings["channels"])
        else:
            where = "Alle Sprachkanäle"

        await ctx.send(view=CV2(
            "Voice Roles",
            f"**Status:** {'✅ An' if settings['enabled'] else '🛑 Aus'}",
            f"**Rollen:**\n{roles}",
            f"**Gilt für:**\n{where}",
            "*Die Bot-Rolle muss über den vergebenen Rollen stehen.*",
        ))

    @staticmethod
    def _role_problem(guild, role) -> str | None:
        me = guild.me
        if me is None:
            return None
        if not me.guild_permissions.manage_roles:
            return "Dem Bot fehlt das Recht „Rollen verwalten“."
        if role.managed:
            return (f"{role.mention} gehört zu einer Integration und kann "
                    "nicht von Hand vergeben werden.")
        if role.is_default():
            return "@everyone kann nicht vergeben werden."
        if role >= me.top_role:
            return (f"{role.mention} steht über der Bot-Rolle — er könnte sie "
                    "niemandem geben. Schieb die Bot-Rolle darüber.")
        return None

    # ──────────────────────────────────────────────────────────────
    #  Event
    # ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Fires for mute, deafen, stream and camera too. Without this
        # the role was re-checked every time somebody touched their
        # microphone.
        if before.channel == after.channel:
            return
        if member.guild is None or member.bot:
            return

        try:
            settings = await self.settings(member.guild.id)
        except Exception as exc:
            print(f"vcrole: could not read settings: {exc}")
            return

        if not settings["enabled"] or not settings["roles"]:
            return

        guild = member.guild
        afk_id = guild.afk_channel.id if guild.afk_channel else None

        def counts(channel):
            if channel is None:
                return False
            return store.voicerole_applies(
                settings,
                channel.id,
                is_afk=(afk_id is not None and channel.id == afk_id),
                is_stage=isinstance(channel, discord.StageChannel),
            )

        was_in = counts(before.channel)
        now_in = counts(after.channel)
        if was_in == now_in:
            return

        held = {r.id for r in member.roles}
        wanted = [
            role for role in (guild.get_role(r) for r in settings["roles"])
            if role is not None
        ]

        if now_in:
            missing = [r for r in wanted if r.id not in held]
            if missing:
                await self._apply(member, missing, add=True)
        else:
            extra = [r for r in wanted if r.id in held]
            if extra:
                await self._apply(member, extra, add=False)

    async def _apply(self, member, roles, *, add: bool, retries: int = 3):
        """
        Add or remove roles in one call.

        The old code looped one role at a time; a bulk edit is a single
        request and cannot leave the member half-updated.
        """
        reason = (f"Joined voice | {BRAND_NAME} vcrole" if add       # noqa: F405
                  else f"Left voice | {BRAND_NAME} vcrole")          # noqa: F405

        for attempt in range(retries):
            try:
                if add:
                    await member.add_roles(*roles, reason=reason)
                else:
                    await member.remove_roles(*roles, reason=reason)
                return
            except discord.Forbidden:
                # Nothing to retry: the bot is not allowed to touch
                # these roles. Silence here was the old behaviour and it
                # made the feature look randomly broken.
                names = ", ".join(r.name for r in roles)
                print(
                    f"vcrole: missing permission for {names} in "
                    f"{member.guild.id} -- is the bot role above them?"
                )
                return
            except discord.NotFound:
                return
            except discord.HTTPException as exc:
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is None and attempt == retries - 1:
                    print(f"vcrole: giving up after {retries} tries: {exc}")
                    return
                await asyncio.sleep(retry_after or (attempt + 1))


async def setup(bot):
    await bot.add_cog(Invcrole(bot))
