# ╔══════════════════════════════════════════════════════════════════╗
# ║   Self-assignable roles                                          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The role picker: a dropdown, one entry per role, toggling on select.

Reactions were the first version and they are worse in every way that
matters here:

  * A reaction is a single emoji. Two roles with the same emoji cannot
    be told apart, and Discord happily accepts the duplicate.
  * A reaction removed by hand desyncs the state silently.
  * On a phone, hitting a small reaction is fiddly; a dropdown is a list
    with names in it.

The dropdown carries a fixed `custom_id`, and the roles live in the
database. That is what lets it survive a restart: discord.py only has to
recognise the id, and the handler looks the rest up when somebody uses
it.

The roles are re-read on every interaction rather than baked into the
view. A role deleted after the panel was posted would otherwise sit in
the list and fail on click.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from utils.db_open import connect

# The dropdown of a self-role panel. Fixed, so the listener recognises it
# after a restart without anything stored per message.
CUSTOM_ID = "selfroles_pick"

DB_PATH = "db/selfroles.db"


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS selfrole_panels ("
        " guild_id INTEGER, message_id INTEGER, role_id INTEGER,"
        " label TEXT, emoji TEXT,"
        " PRIMARY KEY (guild_id, message_id, role_id))"
    )
    await db.commit()


async def offered_roles(guild_id: int, message_id: int) -> list[int]:
    """Which roles this panel hands out. Empty means: not ours."""

    db = await connect(DB_PATH)
    try:
        await ensure_schema(db)
        async with db.execute(
            "SELECT role_id FROM selfrole_panels"
            " WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        ) as cursor:
            return [int(row[0]) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def remember_panel(guild_id: int, message_id: int, entries) -> None:
    """Store what a freshly posted panel offers.

    `entries` is an iterable of (role_id, label, emoji).
    """

    db = await connect(DB_PATH)
    try:
        await ensure_schema(db)
        # A second run replaces the old list instead of adding to it,
        # otherwise a role removed from the template would keep working.
        await db.execute(
            "DELETE FROM selfrole_panels WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        for role_id, label, emoji in entries:
            await db.execute(
                "INSERT OR REPLACE INTO selfrole_panels"
                " (guild_id, message_id, role_id, label, emoji)"
                " VALUES (?, ?, ?, ?, ?)",
                (guild_id, message_id, int(role_id), str(label), str(emoji or "")),
            )
        await db.commit()
    finally:
        await db.close()


class SelfRoles(commands.Cog):
    """Hands out the roles a member may pick for themselves."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if (interaction.data or {}).get("custom_id") != CUSTOM_ID:
            return

        guild = interaction.guild
        message = interaction.message
        if guild is None or message is None:
            return

        offered = set(await offered_roles(guild.id, message.id))
        if not offered:
            await interaction.response.send_message(
                "Dieses Panel kennt keine Rollen mehr. Bitte neu einrichten.",
                ephemeral=True,
            )
            return

        chosen = {
            int(value)
            for value in (interaction.data.get("values") or [])
            if str(value).isdigit()
        }
        # Only ever touch roles this panel offers. Without the filter a
        # forged interaction could name any role id at all -- including
        # one that carries permissions.
        wanted = chosen & offered

        member = interaction.user
        if not isinstance(member, discord.Member):
            member = guild.get_member(interaction.user.id)
        if member is None:
            return

        me = guild.me
        added, removed, refused = [], [], []

        for role_id in offered:
            role = guild.get_role(role_id)
            if role is None:
                continue
            # A role above the bot cannot be handed out. Saying so beats
            # a button that silently does nothing.
            if me is not None and role >= me.top_role:
                if role_id in wanted:
                    refused.append(role.name)
                continue

            has_it = role in member.roles
            try:
                if role_id in wanted and not has_it:
                    await member.add_roles(role, reason="Rollen-Vergabe")
                    added.append(role.name)
                elif role_id not in wanted and has_it:
                    await member.remove_roles(role, reason="Rollen-Vergabe")
                    removed.append(role.name)
            except discord.HTTPException:
                refused.append(role.name)

        parts = []
        if added:
            parts.append("Dazu: " + ", ".join(f"**{n}**" for n in added))
        if removed:
            parts.append("Entfernt: " + ", ".join(f"**{n}**" for n in removed))
        if refused:
            parts.append(
                "Ging nicht: "
                + ", ".join(f"**{n}**" for n in refused)
                + " — die Rolle steht über der des Bots."
            )
        if not parts:
            parts.append("Nichts geändert.")

        await interaction.response.send_message("\n".join(parts), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SelfRoles(bot))
