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
        # Der Nachhol-Durchlauf lief hier frueher direkt, noch waehrend
        # `cog_load`. Zu diesem Zeitpunkt kennt der Bot seine Server
        # nicht -- `get_guild` gibt None -- und der Zweig fuer "Bot ist
        # nicht mehr auf dem Server" haette jedes faellige Gewinnspiel
        # geloescht, samt Teilnehmern.
        #
        # Die Schleife holt dasselbe nach: sie wartet auf
        # `wait_until_ready` und laeuft dann alle fuenf Sekunden.
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

    # ── Der Abschluss ────────────────────────────────────────────────
    #
    # Hier lag der Fehler, wegen dem ein beendetes Gewinnspiel im
    # Sekundentakt weiterlief.
    #
    # Die Auswahl unten holte jede Zeile mit `ends_at <= jetzt` und
    # filterte NIE nach `ended`. Der Dashboard-Zweig in `end_giveaway`
    # setzte am Ende zwar `ended = 1`, loeschte die Zeile aber nicht --
    # und stand damit fuenf Sekunden spaeter wieder in derselben
    # Auswahl. Ausgelost, angekuendigt, DMs an alle Gewinner und an den
    # Host. Zwoelfmal pro Minute, 720-mal pro Stunde, bis jemand von
    # Hand eingriff.
    #
    # Zwei Riegel dagegen:
    #   1. `ended = 0` steht jetzt in der Abfrage.
    #   2. `mark_ended` meldet, ob *dieser* Aufruf den Abschluss
    #      bewirkt hat. Nur dann wird ueberhaupt angekuendigt.
    #
    # Der zweite ist der wichtigere: die Abfrage allein wuerde nichts
    # nuetzen, wenn Timer und Dashboard gleichzeitig zugreifen.

    SELECT_DUE = (
        "SELECT ends_at, guild_id, message_id, host_id, winners, prize, "
        "channel_id FROM Giveaway "
        "WHERE ends_at <= ? AND COALESCE(ended, 0) = 0"
    )

    async def check_for_ended_giveaways(self):
        await self.cursor.execute(
            self.SELECT_DUE, (datetime.datetime.now().timestamp(),)
        )
        ended_giveaways = await self.cursor.fetchall()
        for giveaway in ended_giveaways:
            await self.end_giveaway(giveaway)

    async def end_giveaway(self, giveaway):
        """Ein Gewinnspiel abschliessen -- genau einmal.

        Alle Gewinnspiele laufen ueber den Knopf und die eigene
        Teilnehmer-Tabelle. Der alte Weg las die Teilnehmer aus der
        Reaktion zurueck (`message.reactions[0]`), und daran hing eine
        ganze Reihe von Abstuerzen: die Liste ist leer, sobald jemand
        die Reaktion entfernt oder der Bot sie nie setzen durfte, und
        der IndexError wurde ganz aussen gefangen -- mit einem DELETE.
        Ein Gewinnspiel verschwand dann wortlos.
        """

        guild_id = int(giveaway[1])
        message_id = int(giveaway[2])

        async def drop():
            """Die Zeile entfernen -- fuer Faelle, die nie mehr laufen."""
            await self.cursor.execute(
                "DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?",
                (message_id, guild_id),
            )
            await self.connection.commit()

        try:
            from api import giveaways as gstore
            from api.routes.giveaways import _announce

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                # Der Bot ist nicht mehr auf dem Server. Ohne das DELETE
                # bliebe die Zeile in jeder Runde erneut haengen.
                await drop()
                return

            record = await gstore.get(self.connection, guild_id, message_id)
            if record is None:
                await drop()
                return

            # Der Riegel. Nur wer hier True bekommt, kuendigt an.
            #
            # Steht das Gewinnspiel schon auf beendet -- weil der Timer
            # eine Runde zu frueh war, oder jemand im Dashboard auf
            # "Beenden" geklickt hat -- passiert hier gar nichts mehr.
            if not await gstore.mark_ended(self.connection, message_id):
                return

            winners = await gstore.draw(
                self.connection, message_id, int(giveaway[4] or 1)
            )
            if winners:
                await gstore.record_winners(self.connection, message_id, winners)

            # Auch ohne Teilnehmer wird angekuendigt.
            #
            # Frueher lief der leere Fall in den Reaktions-Pfad, dort in
            # den IndexError und damit ins stille Loeschen. Der Text
            # `msg_no_entries`, den der Host im Dashboard geschrieben
            # hat, wurde nie geschickt -- und im Log stand "corrupted",
            # obwohl nichts kaputt war.
            await _announce(
                self.bot, record, winners, db=self.connection
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Ein Fehler darf das Gewinnspiel NICHT loeschen.
            #
            # Genau das tat der alte `except IndexError`. Ein Aussetzer
            # bei Discord kostete den Host sein Gewinnspiel samt
            # Teilnehmern. Es steht jetzt auf beendet und laeuft nicht
            # erneut an; wer will, kann im Dashboard neu auslosen.
            logging.error(
                f"Giveaway {message_id} konnte nicht beendet werden: "
                f"{type(exc).__name__}: {exc}"
            )

    @tasks.loop(seconds=5)
    async def GiveawayEnd(self):
        await self.cursor.execute(
            self.SELECT_DUE, (datetime.datetime.now().timestamp(),)
        )
        ends_raw = await self.cursor.fetchall()
        for giveaway in ends_raw:
            await self.end_giveaway(giveaway)

    @GiveawayEnd.before_loop
    async def before_giveaway_end(self):
        """Erst starten, wenn der Bot seine Server kennt.

        Ohne dieses Warten laeuft der erste Durchlauf, solange
        `get_guild` noch None liefert -- und der Zweig fuer "Bot ist
        nicht mehr auf dem Server" haette jedes faellige Gewinnspiel
        geloescht.
        """
        await self.bot.wait_until_ready()

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

        # Nur laufende Gewinnspiele zaehlen gegen das Limit.
        #
        # Die Zeilen bleiben nach dem Ende stehen (die Teilnehmer werden
        # fuer einen Reroll gebraucht). Ohne den `ended`-Filter waeren
        # nach fuenf abgeschlossenen Gewinnspielen keine neuen mehr
        # moeglich -- "You can only host upto 5", obwohl keins mehr
        # laeuft.
        await self.cursor.execute(
            "SELECT message_id, channel_id FROM Giveaway "
            "WHERE guild_id = ? AND COALESCE(ended, 0) = 0",
            (ctx.guild.id,),
        )
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

        # Knopf statt Reaktion -- derselbe Weg wie im Dashboard.
        #
        # Der alte Ablauf setzte eine Reaktion und las beim Ende die
        # Teilnehmer daraus zurueck. Das ging aus mehreren Gruenden
        # schief: nimmt jemand die Reaktion weg, ist die Liste leer;
        # darf der Bot sie nicht setzen, kommt sie nie an; und der
        # Zugriff warf dann IndexError, der ganz aussen gefangen wurde
        # -- mit einem DELETE auf das Gewinnspiel.
        #
        # Mit dem Knopf steht jeder Beitritt in `giveaway_entries`.
        # Damit funktionieren Bedingungen, Aussteigen, Reroll ohne
        # Wiederholung und die Anzeige der Teilnehmerzahl -- alles
        # Dinge, die ueber die Reaktion nicht gingen.
        from api import giveaways as gstore
        from api.routes.giveaways import build_view

        # Erst eine leere Nachricht, um die ID zu bekommen: der Knopf
        # traegt sie in seiner custom_id, und die steht vor dem Senden
        # noch nicht fest.
        message = await ctx.send(f"{TADAA} **GIVEAWAY** {TADAA}")

        try:
            await ctx.message.delete()
        except Exception:
            pass

        await self.cursor.execute(
            "INSERT INTO Giveaway(guild_id, host_id, start_time, ends_at, "
            "prize, winners, message_id, channel_id, ended) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (ctx.guild.id, ctx.author.id, datetime.datetime.now().timestamp(),
             ends, prize, winners, message.id, ctx.channel.id),
        )
        await self.connection.commit()

        record = await gstore.get(self.connection, ctx.guild.id, message.id)
        if record is None:
            # Kann eigentlich nicht sein -- aber ein Gewinnspiel ohne
            # Knopf waere eines, an dem niemand teilnehmen kann.
            await message.edit(content=f"{TADAA} **GIVEAWAY** {TADAA}",
                               view=CV2(f"{TADAA} {prize}", "Fehler beim Anlegen."))
            return

        await message.edit(
            content=None,
            view=build_view(record, entries=0, guild=ctx.guild),
        )

    
                                    

    @commands.Cog.listener("on_message_delete")
    async def GiveawayMessageDelete(self, message):
        """Wird die Gewinnspiel-Nachricht geloescht, ist es vorbei.

        Der alte Code las mit `fetchone()` **irgendeine** Zeile des
        Servers -- ohne die Nachricht in der Bedingung und ohne
        Sortierung -- und verglich sie mit der geloeschten. Bei zwei
        laufenden Gewinnspielen traf das meistens das falsche: das
        geloeschte blieb stehen, und der Timer versuchte spaeter, eine
        Nachricht zu beenden, die es nicht mehr gibt.

        Jetzt wird direkt nach dieser einen Nachricht gefragt.
        """

        # DMs haben keinen Server.
        if message.guild is None:
            return
        if message.author != self.bot.user:
            return

        await self.cursor.execute(
            "SELECT message_id FROM Giveaway WHERE guild_id = ? AND message_id = ?",
            (message.guild.id, message.id),
        )
        row = await self.cursor.fetchone()
        if row is None:
            return

        await self.cursor.execute(
            "DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?",
            (message.id, message.guild.id),
        )
        # Teilnehmer gehoeren zu dieser Nachricht und haben ohne sie
        # keinen Zweck mehr. Blieben sie liegen, wuechse die Datenbank
        # mit jedem geloeschten Gewinnspiel weiter.
        await self.cursor.execute(
            "DELETE FROM giveaway_entries WHERE message_id = ?", (message.id,)
        )
        await self.connection.commit()
        logging.info(
            f"Gewinnspiel-Nachricht geloescht in {message.guild.name} "
            f"({message.guild.id})"
        )

    @commands.hybrid_command(name="gend", description="Ends a giveaway before its ending time.", help="Ends a giveaway before its ending time.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def gend(self, ctx, message_id=None):
        """Ein laufendes Gewinnspiel sofort beenden.

        Frueher hatte dieser Befehl vier eigene Fehler, alle aus dem
        Reaktions-Weg:

          * Der Zugriff auf die erste Reaktion ohne Pruefung --
            IndexError, sobald sie fehlt.
          * `users.remove(self.bot.user.id)` ohne try -- ValueError,
            wenn der Bot nicht in der Liste steht.
          * `random.sample(users, k=int(re[4]))` ohne Deckelung: bei
            fuenf gewuenschten Gewinnern und zwei Teilnehmern warf
            sample einen ValueError. Im Timer war die Deckelung da,
            hier fehlte sie.
          * Im Zweig "keine Teilnehmer" stand ein DELETE, dann `return`
            -- am Commit vorbei. Die Zeile blieb stehen, und der Timer
            beendete dasselbe Gewinnspiel gleich noch einmal.

        Jetzt laeuft alles ueber denselben Abschluss wie der Timer.
        """

        from api import giveaways as gstore

        target = None

        if message_id is not None:
            if not str(message_id).isdigit():
                message = await ctx.send(
                    view=CV2("⚠️ Access Denied", "Invalid message ID provided.")
                )
                await asyncio.sleep(5)
                await message.delete()
                return
            target = int(message_id)
        elif ctx.message.reference is not None:
            target = ctx.message.reference.message_id

        if target is None:
            await ctx.send(
                view=CV2(
                    "❌ Error",
                    "Bitte antworte auf die Gewinnspiel-Nachricht oder gib die ID an.",
                )
            )
            return

        record = await gstore.get(self.connection, ctx.guild.id, target)
        if record is None:
            message = await ctx.send(
                view=CV2("❌ Error", "The giveaway was not found.")
            )
            await asyncio.sleep(5)
            await message.delete()
            return

        if record.get("ended"):
            message = await ctx.send(
                view=CV2("⚠️ Access Denied", "Dieses Gewinnspiel ist schon beendet.")
            )
            await asyncio.sleep(5)
            await message.delete()
            return

        # Derselbe Ablauf wie im Timer -- ein Weg, ein Riegel, eine DM.
        await self.end_giveaway(
            (
                record.get("ends_at"),
                ctx.guild.id,
                target,
                record.get("host_id"),
                record.get("winners") or 1,
                record.get("prize"),
                record.get("channel_id"),
            )
        )

        if int(ctx.channel.id) != int(record.get("channel_id") or 0):
            await ctx.send(
                f"{TICK} Successfully ended the giveaway in "
                f"<#{int(record.get('channel_id') or 0)}>"
            )
        else:
            await ctx.send(f"{TICK} Gewinnspiel beendet.")

    @commands.hybrid_command(description="Rerolls a giveaway on replying the giveaway message.", help="Rerolls a giveaway on replying the giveaway message.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: typing.Optional[int] = None):
        """Neu auslosen, ohne die bisherigen Gewinner erneut zu ziehen.

        Der alte Befehl konnte gar nicht funktionieren. Er brach ab,
        wenn er das Gewinnspiel in der Datenbank FAND ("laeuft noch"),
        und lief weiter, wenn er es NICHT fand -- um dann auf `re[5]`
        eines `None` zuzugreifen. Also entweder Abbruch oder
        TypeError, in jedem Fall kein Reroll.

        Dazu las auch er die Teilnehmer aus der Reaktion, mit denselben
        Abstuerzen wie `gend`, und zog mit `k=1` immer genau einen
        Gewinner -- egal wie viele das Gewinnspiel vorsah.
        """

        from api import giveaways as gstore
        from api.routes.giveaways import _announce

        target = message_id
        if target is None and ctx.message.reference is not None:
            target = ctx.message.reference.message_id

        if target is None:
            message = await ctx.reply(
                "Antworte auf die Gewinnspiel-Nachricht oder gib die ID an."
            )
            await asyncio.sleep(5)
            await message.delete()
            return

        record = await gstore.get(self.connection, ctx.guild.id, int(target))
        if record is None:
            msg = await ctx.send(
                view=CV2("⚠️ Access Denied", "The giveaway was not found.")
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Ein laufendes Gewinnspiel wird beendet, nicht neu ausgelost.
        if not record.get("ended"):
            msg = await ctx.send(
                view=CV2(
                    "⚠️ Access Denied",
                    "Das Gewinnspiel laeuft noch. Nutze `gend`, um es zu beenden.",
                )
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        winners = await gstore.draw(
            self.connection,
            int(target),
            int(record.get("winners") or 1),
            exclude_past=True,
        )
        if not winners:
            await ctx.send(
                view=CV2("Neu auslosen", "Es gibt keine Teilnehmer zum Auslosen.")
            )
            return

        await gstore.record_winners(self.connection, int(target), winners, reroll=True)
        await _announce(
            self.bot, record, winners, reroll=True, db=self.connection
        )
        await ctx.send(f"{TICK} Neu ausgelost — {len(winners)} Gewinner.")

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
        """Die laufenden Gewinnspiele.

        Zwei Fehler steckten hier:

          * Die Liste hiess "Ongoing", zeigte aber jedes Gewinnspiel --
            auch die laengst beendeten, weil deren Zeilen fuer den
            Reroll stehen bleiben.
          * Der Sprunglink benutzte `ctx.channel.id`, also den Kanal, in
            dem der Befehl getippt wurde. Steht das Gewinnspiel
            woanders, fuehrte der Link ins Leere.
        """

        from api import giveaways as gstore

        await self.cursor.execute(
            "SELECT prize, ends_at, winners, message_id, channel_id "
            "FROM Giveaway WHERE guild_id = ? AND COALESCE(ended, 0) = 0 "
            "ORDER BY ends_at ASC",
            (ctx.guild.id,),
        )
        giveaways = await self.cursor.fetchall()

        if not giveaways:
            await ctx.send(view=CV2("Ongoing Giveaways", "No ongoing giveaways."))
            return

        desc = ""
        for prize, ends_at, winners, message_id, channel_id in giveaways:
            entries = await gstore.entry_count(self.connection, int(message_id))
            link = (
                f"https://discord.com/channels/{ctx.guild.id}"
                f"/{int(channel_id or 0)}/{int(message_id)}"
            )
            desc += (
                f"**{prize}**\n"
                f"Ends: <t:{int(ends_at)}:R> (<t:{int(ends_at)}:f>)\n"
                f"Winners: {winners} · Teilnehmer: {entries}\n"
                f"[Jump to Message]({link})\n\n"
            )

        await ctx.send(view=CV2("Ongoing Giveaways", desc))

async def setup(bot):
    await bot.add_cog(Giveaway(bot))
