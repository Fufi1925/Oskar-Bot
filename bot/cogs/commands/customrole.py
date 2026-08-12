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
Custom role commands: `>gamer @user` toggles a role.

The five hard-coded slots (staff, girl, vip, guest, friend) are gone.
They were English-only words that could not be renamed, each one a
near-identical copy of the same twelve lines, and they duplicated the
free-form ``custom_roles`` table this cog already had. Existing slots
are migrated into ordinary named commands by
``voice_store.customrole_migrate`` so no server loses a command.

Real bugs fixed along the way:

  * ``on_message`` read ``message.guild.id`` with no None check, so
    every DM raised AttributeError before the listener could return.
  * The dynamic handler required the reqrole from everyone, while the
    slot commands let the server owner through. Same feature, two
    different answers -- the owner now bypasses in both.
  * The cooldown message said "5 seconds" while the code enforced 10.
  * The cooldown was stored per guild, so one person using a command
    blocked everybody else on the server for ten seconds.
  * ``add_role``/``remove_role`` passed ``discord.Object``, which skips
    the role hierarchy check and turns a predictable "role too high"
    into an opaque 403.
"""

import asyncio

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

from utils import voice_store as store
from utils.config import *        # noqa: F401,F403  (BRAND_NAME)
from utils.cv2 import CV2
from utils.emoji import CROSS, TICK, ZWARNING
from utils.Tools import *         # noqa: F401,F403  (blacklist_check, ignore_check)

DATABASE_PATH = store.CUSTOMROLE_DB

# One command per role, and Discord will not let a member hold an
# unlimited number anyway.
MAX_COMMANDS = 56
USER_COOLDOWN = 5.0


class Customrole(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        # Keyed by (guild, user). The old version keyed on the guild
        # alone, so one person's command silenced the whole server.
        self.cooldown: dict[tuple[int, int], float] = {}

    async def _db(self):
        db = await aiosqlite.connect(DATABASE_PATH)
        db.row_factory = aiosqlite.Row
        return db

    async def refresh(self, guild_id=None):
        """Nothing cached; here for the dashboard's reload hook."""
        return True

    # ──────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────

    def _role_problem(self, guild, role) -> str | None:
        me = guild.me
        if me is None:
            return None
        if not me.guild_permissions.manage_roles:
            return "Dem Bot fehlt das Recht „Rollen verwalten“."
        if role.managed:
            return f"{role.mention} gehört zu einer Integration."
        if role.is_default():
            return "@everyone geht nicht."
        if role >= me.top_role:
            return (f"{role.mention} steht über der Bot-Rolle. "
                    "Schieb die Bot-Rolle darüber.")
        return None

    def _on_cooldown(self, guild_id: int, user_id: int) -> float:
        """Seconds left, or 0."""
        key = (guild_id, user_id)
        now = asyncio.get_event_loop().time()
        last = self.cooldown.get(key)
        if last is not None and now - last < USER_COOLDOWN:
            return USER_COOLDOWN - (now - last)
        self.cooldown[key] = now
        return 0.0

    async def _may_use(self, guild, member) -> tuple[bool, str]:
        """
        Whether `member` may run the role commands.

        The owner always may -- otherwise setting a reqrole they do not
        hold locks them out of their own server.
        """
        if member == guild.owner:
            return True, ""
        if getattr(member.guild_permissions, "administrator", False):
            return True, ""

        db = await self._db()
        try:
            config = await store.customrole_get(db, guild.id)
        finally:
            await db.close()

        reqrole_id = config.get("reqrole")
        if not reqrole_id:
            return False, (
                "Es ist keine berechtigte Rolle eingestellt. "
                "Ein Admin legt sie im Dashboard oder mit "
                "`setup reqrole @rolle` fest."
            )

        reqrole = guild.get_role(int(reqrole_id))
        if reqrole is None:
            return False, ("Die eingestellte berechtigte Rolle gibt es nicht "
                           "mehr. Ein Admin muss sie neu setzen.")
        if reqrole not in member.roles:
            return False, f"Dafür brauchst du {reqrole.mention}."
        return True, ""

    async def _toggle(self, guild, member, role) -> str:
        """Add or remove the role; return a message for the channel."""
        if role in member.roles:
            await member.remove_roles(
                role, reason=f"{BRAND_NAME} Customrole"      # noqa: F405
            )
            return f"**Entfernt:** {role.mention} von {member.mention}"
        await member.add_roles(
            role, reason=f"{BRAND_NAME} Customrole"          # noqa: F405
        )
        return f"**Gegeben:** {role.mention} an {member.mention}"

    # ──────────────────────────────────────────────────────────────
    #  Setup commands
    # ──────────────────────────────────────────────────────────────

    @commands.hybrid_group(name="setup",
                           description="Set up custom role commands.",
                           help="Set up custom role commands.", with_app_command=False)
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def set(self, context: Context):
        if context.subcommand_passed is None:
            await context.send_help(context.command)
            context.command.reset_cooldown(context)

    @set.command(name="reqrole",
                 description="Which role may use the custom role commands",
                 help="Which role may use the custom role commands")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role allowed to use the commands")
    async def req_role(self, context: Context, role: discord.Role) -> None:
        db = await self._db()
        try:
            await store.customrole_set_reqrole(db, context.guild.id, role.id)
        finally:
            await db.close()
        await context.reply(view=CV2(
            f"{TICK} Gespeichert",
            f"Wer {role.mention} hat, darf die Rollen-Befehle benutzen.\n"
            "Serverinhaber und Admins dürfen immer.",
        ))

    @set.command(name="create",
                 description="Create a custom role command.",
                 help="Create a custom role command.")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="Command name", role="Role to assign")
    async def create(self, context: Context, name: str,
                     role: discord.Role) -> None:
        name = (name or "").strip().lower()

        problem = store.customrole_check_name(name)
        if problem:
            await context.reply(view=CV2(f"{CROSS} Geht nicht", problem))
            return

        # A custom name that shadows a real command would make the real
        # one unreachable.
        if self.bot.get_command(name):
            await context.reply(view=CV2(
                f"{CROSS} Name belegt",
                f"`{name}` ist schon ein Befehl des Bots. Nimm einen anderen Namen.",
            ))
            return

        problem = self._role_problem(context.guild, role)
        if problem:
            await context.reply(view=CV2(f"{ZWARNING} Geht nicht", problem))
            return

        db = await self._db()
        try:
            config = await store.customrole_get(db, context.guild.id)
            if len(config["entries"]) >= MAX_COMMANDS:
                await context.reply(view=CV2(
                    f"{ZWARNING} Limit erreicht",
                    f"Mehr als {MAX_COMMANDS} Rollen-Befehle gehen nicht.",
                ))
                return
            if any(e["name"] == name for e in config["entries"]):
                await context.reply(view=CV2(
                    f"{CROSS} Gibt es schon",
                    f"`{name}` ist vergeben. Erst löschen, dann neu anlegen.",
                ))
                return

            await store.customrole_add(db, context.guild.id, name, role.id)
        finally:
            await db.close()

        prefix = context.clean_prefix or ">"
        await context.reply(view=CV2(
            f"{TICK} Angelegt",
            f"`{prefix}{name} @user` gibt {role.mention} — nochmal "
            "ausgeführt nimmt sie wieder weg.",
        ))

    @set.command(name="delete", aliases=["remove"],
                 description="Delete a custom role command.",
                 help="Delete a custom role command.")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="Command name to delete")
    async def delete(self, context: Context, name: str) -> None:
        db = await self._db()
        try:
            removed = await store.customrole_remove(db, context.guild.id, name)
        finally:
            await db.close()

        if not removed:
            await context.reply(view=CV2(
                f"{CROSS} Nicht gefunden",
                f"Einen Befehl `{name}` gibt es hier nicht.",
            ))
            return
        await context.reply(view=CV2(f"{TICK} Gelöscht",
                                     f"`{name}` ist weg."))

    @set.command(name="list", aliases=["config"],
                 description="List the custom role commands.",
                 help="List the custom role commands.")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def list(self, context: Context) -> None:
        db = await self._db()
        try:
            config = await store.customrole_get(db, context.guild.id)
        finally:
            await db.close()

        if not config["entries"]:
            await context.reply(view=CV2(
                "Rollen-Befehle",
                "Es ist noch keiner angelegt.\n"
                f"`{context.clean_prefix or '>'}setup create name @rolle` legt einen an.",
            ))
            return

        prefix = context.clean_prefix or ">"
        reqrole = config.get("reqrole")
        header = (f"Benutzbar von <@&{reqrole}>, Admins und dem Inhaber."
                  if reqrole else
                  "Noch keine berechtigte Rolle gesetzt — nur Admins.")

        # 7 per message keeps each one comfortably under the 6000
        # character embed budget even with long role names.
        chunks = [config["entries"][i:i + 7]
                  for i in range(0, len(config["entries"]), 7)]
        for index, chunk in enumerate(chunks, 1):
            lines = []
            for entry in chunk:
                role = context.guild.get_role(entry["role_id"])
                target = role.mention if role else "*(Rolle gelöscht)*"
                lines.append(f"`{prefix}{entry['name']}` → {target}")
            await context.reply(view=CV2(
                "Rollen-Befehle",
                header if index == 1 else "",
                "\n".join(lines),
                f"Seite {index}/{len(chunks)}",
            ))

    @set.command(name="reset",
                 description="Delete every custom role command.",
                 help="Delete every custom role command.")
    @blacklist_check()      # noqa: F405
    @ignore_check()         # noqa: F405
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def reset(self, context: Context) -> None:
        db = await self._db()
        try:
            config = await store.customrole_get(db, context.guild.id)
            count = len(config["entries"])
            await db.execute(
                "DELETE FROM custom_roles WHERE guild_id = ?", (context.guild.id,)
            )
            await db.commit()
        finally:
            await db.close()

        await context.reply(view=CV2(
            "Zurückgesetzt",
            f"{count} Rollen-Befehl(e) gelöscht. "
            "Die Rollen selbst bleiben unverändert.",
        ))

    # ──────────────────────────────────────────────────────────────
    #  The dynamic commands
    # ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DMs have no guild. The old code read message.guild.id here and
        # raised on every direct message the bot received.
        if message.guild is None or message.author.bot or not message.content:
            return

        try:
            prefixes = await self.bot.get_prefix(message)
        except Exception:
            return
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if not prefixes:
            return

        used = next(
            (p for p in prefixes if p and message.content.startswith(p)), None
        )
        if used is None:
            return

        rest = message.content[len(used):].strip()
        if not rest:
            return
        command_name = rest.split()[0].lower()

        db = await self._db()
        try:
            role_id = await store.customrole_lookup(
                db, message.guild.id, command_name
            )
        finally:
            await db.close()
        if role_id is None:
            return

        allowed, reason = await self._may_use(message.guild, message.author)
        if not allowed:
            await message.channel.send(
                view=CV2(f"{ZWARNING} Nicht erlaubt", reason)
            )
            return

        remaining = self._on_cooldown(message.guild.id, message.author.id)
        if remaining:
            await message.channel.send(
                f"Warte noch {remaining:.0f} Sekunden.", delete_after=5
            )
            return

        role = message.guild.get_role(int(role_id))
        if role is None:
            await message.channel.send(view=CV2(
                f"{CROSS} Fehler",
                f"Die Rolle hinter `{command_name}` gibt es nicht mehr. "
                "Ein Admin sollte den Befehl neu anlegen.",
            ))
            return

        problem = self._role_problem(message.guild, role)
        if problem:
            await message.channel.send(view=CV2(f"{ZWARNING} Geht nicht", problem))
            return

        member = message.mentions[0] if message.mentions else None
        if member is None:
            await message.channel.send(view=CV2(
                f"{CROSS} Wen denn?",
                f"So geht es: `{used}{command_name} @user`",
            ))
            return
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id)
            if member is None:
                await message.channel.send(view=CV2(
                    f"{CROSS} Fehler", "Diese Person ist nicht auf dem Server."
                ))
                return

        try:
            result = await self._toggle(message.guild, member, role)
        except discord.Forbidden:
            await message.channel.send(view=CV2(
                f"{CROSS} Keine Rechte",
                f"Der Bot darf {role.mention} nicht vergeben. "
                "Steht die Bot-Rolle darüber?",
            ))
            return
        except discord.HTTPException as exc:
            await message.channel.send(view=CV2(
                f"{CROSS} Discord lehnte ab", str(exc)[:300]
            ))
            return

        await message.channel.send(view=CV2(f"{TICK} Erledigt", result))


async def setup(bot):
    await bot.add_cog(Customrole(bot))
