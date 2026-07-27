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

from discord.ext import commands, tasks
import datetime, pytz, time as t
from discord.ui import Button, Select, View
import aiosqlite, random, typing
import sqlite3
import asyncio
import discord, logging
from utils.emoji import ARROWRED, TADAA, TICK
from discord.utils import get
from utils.Tools import *
import os
import aiohttp
from utils.cv2 import CV2

db_folder = 'db'
db_file = 'giveaways.db'
db_path = os.path.join(db_folder, db_file)
connection = sqlite3.connect(db_path)

cursor = connection.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS Giveaway (
                    guild_id INTEGER,
                    host_id INTEGER,
                    start_time TIMESTAMP,
                    ends_at TIMESTAMP,
                    prize TEXT,
                    winners INTEGER,
                    message_id INTEGER,
                    channel_id INTEGER,
                    PRIMARY KEY (guild_id, message_id)
                )''')

connection.commit()
connection.close()

def convert(time):
    pos = ["s","m","h","d"]
    time_dict = {"s" : 1, "m" : 60, "h" : 3600 , "d" : 86400 , "f" : 259200}
    unit = time[-1]
    if unit not in pos:
        return
    try:
        val = int(time[:-1])
    except ValueError:
        return
    return val * time_dict[unit]

def WinnerConverter(winner):
    try:
        int(winner)
    except ValueError:
        try:
           return int(winner[:-1])
        except:
            return -4
    return winner

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.connection = await aiosqlite.connect(db_path)
        self.cursor = await self.connection.cursor()
        # Dashboard giveaways use extra columns and their own entry table.
        try:
            from api import giveaways as gstore
            await gstore.ensure_schema(self.connection)
        except Exception as exc:
            logging.error(f"Giveaway schema check failed: {exc}")
        await self.check_for_ended_giveaways() 
        self.GiveawayEnd.start()

    async def cog_unload(self) -> None:
        await self.connection.close()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Join button on dashboard giveaways.

        Entries used to be counted by reading the 🎉 reaction back off the
        message, which loses everything if the reaction is cleared and makes
        a reroll that skips previous winners impossible. Presses are now
        recorded in their own table.
        """
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not custom_id.startswith("giveaway_join_"):
            return

        suffix = custom_id.rsplit("_", 1)[-1]
        if not suffix.isdigit():
            return
        message_id = int(suffix)

        try:
            from api import giveaways as gstore
            from api.routes.giveaways import (
                build_view,
                message_text,
                placeholder_values,
            )
            from utils.panels import StatusCard

            async def reply(title, body, tone="info"):
                """Every answer is a Components V2 card, like the panel itself."""
                await interaction.response.send_message(
                    view=StatusCard(title, body, tone=tone), ephemeral=True
                )

            record = await gstore.get(self.connection, interaction.guild_id, message_id)
            if record is None:
                return await reply(
                    "Nicht mehr da", "Dieses Gewinnspiel gibt es nicht mehr.", "error"
                )

            if record.get("ended") or float(record.get("ends_at") or 0) <= datetime.datetime.now().timestamp():
                return await reply(
                    "Schon vorbei",
                    message_text(record, "msg_ended", placeholder_values(record)),
                    "warning",
                )

            # Entry requirements: role, blocked role, messages, level,
            # account age, time on the server. All of them optional.
            member = interaction.user
            already_in = interaction.user.id in await gstore.entry_ids(
                self.connection, message_id
            )
            if not already_in:
                problems = await gstore.failed_requirements(record, member)
                if problems:
                    heading = message_text(
                        record, "msg_denied", placeholder_values(record)
                    )
                    return await reply(
                        "Noch nicht",
                        heading + "\n" + "\n".join(f"• {p}" for p in problems),
                        "warning",
                    )

            if already_in and not record.get("allow_leave", 1):
                total = await gstore.entry_count(self.connection, message_id)
                return await reply(
                    "Schon dabei",
                    f"Du nimmst bereits teil. Teilnehmer: **{total}**",
                    "success",
                )

            # Pressing again leaves the giveaway, so it doubles as an undo.
            added = await gstore.add_entry(
                self.connection, message_id, interaction.user.id
            )
            if not added:
                await gstore.remove_entry(
                    self.connection, message_id, interaction.user.id
                )

            total = await gstore.entry_count(self.connection, message_id)
            values = placeholder_values(record, entries=total)
            if added:
                await reply(
                    "Du bist dabei",
                    message_text(record, "msg_joined", values)
                    + ("\n\nNochmal drücken, um wieder auszusteigen."
                       if record.get("allow_leave", 1) else ""),
                    "success",
                )
            else:
                await reply(
                    "Ausgestiegen",
                    message_text(record, "msg_left", values),
                    "info",
                )

            # Keep the entry count on the message honest.
            try:
                await interaction.message.edit(
                    view=build_view(
                        record, entries=total, guild=interaction.guild
                    )
                )
            except Exception:
                pass

        except Exception as exc:
            logging.error(f"Giveaway join failed: {exc}")
            if not interaction.response.is_done():
                from utils.panels import StatusCard

                await interaction.response.send_message(
                    view=StatusCard(
                        "Fehler", "Da ist etwas schiefgelaufen.", tone="error"
                    ),
                    ephemeral=True,
                )

    async def check_for_ended_giveaways(self):
        await self.cursor.execute("SELECT ends_at, guild_id, message_id, host_id, winners, prize, channel_id FROM Giveaway WHERE ends_at <= ?", (datetime.datetime.now().timestamp(),))
        ended_giveaways = await self.cursor.fetchall()
        for giveaway in ended_giveaways:
            await self.end_giveaway(giveaway)

    async def end_giveaway(self, giveaway):
        try:
            current_time = datetime.datetime.now().timestamp()
            guild = self.bot.get_guild(int(giveaway[1]))
            if guild is None:
                await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (giveaway[2], giveaway[1]))
                await self.connection.commit()
                return

            # A giveaway created from the dashboard collects entries through
            # its button, not the reaction, so it is drawn and announced by
            # the shared logic (which also sends the DMs).
            try:
                from api import giveaways as gstore
                from api.routes.giveaways import _announce

                entries = await gstore.entry_count(self.connection, int(giveaway[2]))
                if entries:
                    record = await gstore.get(
                        self.connection, int(giveaway[1]), int(giveaway[2])
                    )
                    if record is not None:
                        winners = await gstore.draw(
                            self.connection, int(giveaway[2]), int(giveaway[4] or 1)
                        )
                        await gstore.record_winners(
                            self.connection, int(giveaway[2]), winners
                        )
                        await gstore.mark_ended(self.connection, int(giveaway[2]))
                        await _announce(self.bot, record, winners)
                        return
            except Exception as exc:
                logging.error(f"Dashboard giveaway end failed: {exc}")

            channel = self.bot.get_channel(int(giveaway[6]))
            if channel is not None:
                try:
                    retries = 3
                    for attempt in range(retries):
                        try:
                            message = await channel.fetch_message(int(giveaway[2]))
                            break
                        except discord.NotFound:
                            await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (giveaway[2], giveaway[1]))
                            await self.connection.commit()
                            return
                        except aiohttp.ClientResponseError as e:
                            if e.status == 503:
                                if attempt < retries - 1:
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                else:
                                    raise
                            else:
                                raise

                    users = [i.id async for i in message.reactions[0].users()]
                    if self.bot.user.id in users:
                        users.remove(self.bot.user.id)

                    if len(users) < 1:
                        await message.reply(f"No one won the **{giveaway[5]}** giveaway, due to Not enough participants.")
                        await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))
                        await self.connection.commit()
                        return

                    winners_count = min(len(users), int(giveaway[4]))
                    winner = ', '.join(f'<@!{i}>' for i in random.sample(users, k=winners_count))

                    desc = f"Ended at <t:{int(current_time)}:R>\nHosted by <@{int(giveaway[3])}>\nWinner(s): {winner}"
                    view = CV2(f"{giveaway[5]}", desc)

                    await message.edit(content=f"{TADAA} **GIVEAWAY ENDED** {TADAA}", view=view)
                    await message.reply(f"{TADAA} Congrats {winner}, you won **{giveaway[5]}!**, Hosted by <@{int(giveaway[3])}>")
                    await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))
                    await self.connection.commit()

                except (discord.HTTPException, aiohttp.ClientResponseError) as e:
                    logging.error(f"Error ending giveaway: {e}")

        except IndexError:
            logging.error(f"Giveaway data is corrupted or missing: {giveaway}")
            await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (giveaway[2], giveaway[1]))
            await self.connection.commit()

    @tasks.loop(seconds=5)
    async def GiveawayEnd(self):
        await self.cursor.execute("SELECT ends_at, guild_id, message_id, host_id, winners, prize, channel_id FROM Giveaway WHERE ends_at <= ?", (datetime.datetime.now().timestamp(),))
        ends_raw = await self.cursor.fetchall()
        for giveaway in ends_raw:
            await self.end_giveaway(giveaway)




    @commands.hybrid_command(description="Starts a new giveaway.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def gstart(self, ctx,
                      time,
                      winners: int,
                      *,
                      prize: str):

        await self.cursor.execute("SELECT message_id, channel_id FROM Giveaway WHERE guild_id = ?", (ctx.guild.id,))
        re = await self.cursor.fetchall()

        if winners >=  15:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "Cannot exceed more than 15 winners."))
            await asyncio.sleep(5)
            await message.delete()
            return

        g_list = [i[0] for i in re]
        if len(g_list) >= 5:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "You can only host upto 5 giveaways in this Guild."))
            await asyncio.sleep(5)
            await message.delete()
            return

        converted = self.convert(time)
        if converted / 60 >= 50400:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "Time cannot exceed 31 days!"))
            await asyncio.sleep(5)
            await message.delete()
            return

        if converted == -1:
            message = await ctx.send(view=CV2("❌ Error", "Invalid time format"))
            await asyncio.sleep(5)
            await message.delete()
            return
        if converted == -2:
            message = await ctx.send(view=CV2("❌ Error", "Invalid time format. Please provide the time in numbers."))
            await asyncio.sleep(5)
            await message.delete()
            return

        ends = (datetime.datetime.now().timestamp() + converted)

        desc = (
            f"{ARROWRED} Winner(s): **{winners}**\n"
            f"{ARROWRED} Hosted by {ctx.author.mention}\n"
            f"{ARROWRED} Ends <t:{round(ends)}:R> (<t:{round(ends)}:f>)\n\n"
            f"{ARROWRED} React with {TADAA} to participate!"
        )
        
        view = CV2(f"{TADAA} {prize}", desc)

        message = await ctx.send(f"{TADAA} **GIVEAWAY** {TADAA}", view=view)
        try:
           await ctx.message.delete()
        except:
            pass

        await self.cursor.execute("INSERT INTO Giveaway(guild_id, host_id, start_time, ends_at, prize, winners, message_id, channel_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (ctx.guild.id, ctx.author.id, datetime.datetime.now(), ends, prize, winners, message.id, ctx.channel.id))

        await message.add_reaction(TADAA)
        await self.connection.commit()

    
                                    

    @commands.Cog.listener("on_message_delete")
    async def GiveawayMessageDelete(self, message):
        await self.cursor.execute("SELECT message_id FROM Giveaway WHERE guild_id = ?", (message.guild.id,))
        re = await self.cursor.fetchone()

        if message.author != self.bot.user:
            return

        if re is not None:
            if message.id == int(re[0]):
                await self.cursor.execute("DELETE FROM Giveaway WHERE channel_id = ? AND message_id = ? AND guild_id = ?", (message.channel.id, message.id, message.guild.id))

                print(f"Giveaway message deleted in {message.guild.name} - {message.guild.id}")
                await self.connection.commit()

    @commands.hybrid_command(name="gend", description="Ends a giveaway before its ending time.", help="Ends a giveaway before its ending time.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def gend(self, ctx, message_id = None):
        if message_id:
            try:
                int(message_id)
            except ValueError:
                message = await ctx.send(view=CV2("⚠️ Access Denied", "Invalid message ID provided."))
                await asyncio.sleep(5)
                await message.delete()
                return

        if message_id is not None:
            current_time = datetime.datetime.now().timestamp()
            await self.cursor.execute('SELECT ends_at, guild_id, message_id, host_id, winners, prize, channel_id FROM Giveaway WHERE message_id = ?', (int(message_id),))
            re = await self.cursor.fetchone()

            if re is None:
                message = await ctx.send(view=CV2("❌ Error", "The giveaway was not found."))
                await asyncio.sleep(5)
                await message.delete()
                return

            ch = self.bot.get_channel(int(re[6]))
            message = await ch.fetch_message(int(message_id))

            users = [i.id async for i in message.reactions[0].users()]
            users.remove(self.bot.user.id)

            if len(users) < 1:
                await ctx.send(f"{TICK} Successfully Ended the giveaway in <#{int(re[6])}>")
                await message.reply(f"No one won the **{re[5]}** giveaway, due to Not enough participants.")
                await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))
                return

            winner = ', '.join(f'<@!{i}>' for i in random.sample(users, k=int(re[4])))

            desc = f"Ended at <t:{int(current_time)}:R>\nHosted by <@{int(re[3])}>\nWinner(s): {winner}"
            view = CV2(f"🎁 {re[5]}", desc)

            await message.edit(content="🎁 **GIVEAWAY ENDED** 🎁", view=view)

            if int(ctx.channel.id) != int(re[6]):
                await ctx.send(f"{TADAA} Successfully ended the giveaway in <#{int(re[6])}>")

            await message.reply(f" Congrats {winner}, you won **{re[5]}!**, Hosted by <@{int(re[3])}>")
            await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))

        elif ctx.message.reference:
            await self.cursor.execute('SELECT ends_at, guild_id, message_id, host_id, winners, prize, channel_id FROM Giveaway WHERE message_id = ?', (ctx.message.reference.resolved.id,))
            re = await self.cursor.fetchone()

            if re is None:
                return await ctx.send(f"The giveaway was not found.")

            current_time = datetime.datetime.now().timestamp()

            message = await ctx.fetch_message(ctx.message.reference.message_id)

            users = [i.id async for i in message.reactions[0].users()]
            try: users.remove(self.bot.user.id)
            except: pass

            if len(users) < 1:
                await message.reply(f"No one won the **{re[5]}** giveaway, due to not enough participants.")
                await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))
                return

            winner = ', '.join(f'<@!{i}>' for i in random.sample(users, k=int(re[4])))

            desc = f"Ended <t:{int(current_time)}:R>\nHosted by <@{int(re[3])}>\nWinner(s): {winner}"
            view = CV2(f"🎁 {re[5]}", desc)

            await message.edit(content="🎁 **GIVEAWAY ENDED** 🎁", view=view)

            await message.reply(f"💐 Congrats {winner}, you won **{re[5]}!**, Hosted by <@{int(re[3])}>")
            await self.cursor.execute("DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?", (message.id, message.guild.id))

        else:
            await ctx.send("Please reply to the giveaway message or provide the giveaway ID.")
        await self.connection.commit()

    @commands.hybrid_command(description="Rerolls a giveaway on replying the giveaway message.", help="Rerolls a giveaway on replying the giveaway message.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: typing.Optional[int] = None):
        if not ctx.message.reference:
            message = await ctx.reply("Reply this command with the Giveaway Ended message to reroll.")
            await asyncio.sleep(5)
            await message.delete()
            return

        if ctx.message.reference:
            message_id = ctx.message.reference.resolved.id

        message = await ctx.fetch_message(message_id)

        if ctx.message.reference.resolved.author.id != self.bot.user.id :
            msg = await ctx.send(view=CV2("⚠️ Access Denied", "The giveaway was not found."))
            await asyncio.sleep(5)
            await msg.delete()
            return


        await self.cursor.execute(f"SELECT message_id FROM Giveaway WHERE message_id = ?", (message.id,))
        re = await self.cursor.fetchone()

        if re is not None:
            msg = await ctx.send(view=CV2("⚠️ Access Denied", "The giveaway is currently running. Please use the `gend` command instead to end the giveaway."))
            await asyncio.sleep(5)
            await msg.delete()
            return

        users = [i.id async for i in message.reactions[0].users()]
        users.remove(self.bot.user.id)

        if len(users) < 1:
            await message.reply(f"No one won the **{re[5]}** giveaway, due to not enough participants.")
            return

        winners = random.sample(users, k=1)
        await message.reply(f" The new winner is "+", ".join(f"<@{i}>" for i in winners)+". Congratulations!")
        await self.connection.commit()

    def convert(self, time):
        pos = ["s", "m", "h", "d"]
        time_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400, "f": 259200}

        unit = time[-1]
        if unit not in pos:
            return -1

        try:
            val = int(time[:-1])
        except ValueError:
            return -2

        return val * time_dict[unit]


    @commands.hybrid_command(name="glist", description="Lists all ongoing giveaways.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def glist(self, ctx):
        await self.cursor.execute("SELECT prize, ends_at, winners, message_id FROM Giveaway WHERE guild_id = ?", (ctx.guild.id,))
        giveaways = await self.cursor.fetchall()

        if not giveaways:
            await ctx.send(view=CV2("Ongoing Giveaways", "No ongoing giveaways."))
            return

        desc = ""
        for giveaway in giveaways:
            prize, ends_at, winners, message_id = giveaway
            desc += f"**{prize}**\nEnds: <t:{int(ends_at)}:R> (<t:{int(ends_at)}:f>)\nWinners: {winners}\n[Jump to Message](https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message_id})\n\n"

        await ctx.send(view=CV2("Ongoing Giveaways", desc))

async def setup(bot):
    await bot.add_cog(Giveaway(bot))
