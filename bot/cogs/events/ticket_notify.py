# ╔══════════════════════════════════════════════════════════════════╗
# ║   Benachrichtigungen im Ticket                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Wer im Ticket schreibt, und wer deshalb eine DM bekommt.

Dieser Cog macht drei Dinge und sonst nichts:

  * Er liest mit, wer in einem Ticketkanal schreibt, und vermerkt es
    ueber ``utils/ticket_notify.py``.
  * Ein Hintergrundlauf schaut alle 30 Sekunden nach, welche Erinnerung
    faellig geworden ist, und fragt dieselbe Regelschicht, ob sie raus
    darf.
  * ``>sleep`` und ``>wake`` legen ein Ticket still.

Die Entscheidung *ob* eine DM rausgeht steht bewusst nicht hier,
sondern in ``ticket_notify.decide()``. Sie muss an drei Stellen
identisch gelten -- beim Schreiben, beim Hintergrundlauf und im
Dashboard -- und drei Kopien derselben Bedingung laufen frueher oder
spaeter auseinander.

Warum ein Hintergrundlauf und kein ``asyncio.sleep(300)`` pro
Nachricht: der Bot startet auf Railway staendig neu. Ein wartender
Task waere danach weg, ein Eintrag in der Datenbank nicht.
"""

import logging
import sqlite3

import discord
from discord.ext import commands, tasks

from utils import ticket_dm, ticket_notify

logger = logging.getLogger(__name__)

TICKET_DB = "db/ticket.db"

# 30 Sekunden Takt. Die Wartezeit betraegt mindestens 30 Sekunden, also
# geht nichts verloren; haeufiger nachzusehen brauchte niemand.
INTERVALL = 30


class TicketNotify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_pending.start()

    def cog_unload(self):
        self.check_pending.cancel()

    # ── Ticket-Daten aus der Cog-Datenbank ───────────────────────────

    def _ticket_row(self, channel_id: int):
        """
        Das offene Ticket zu einem Kanal, oder None.

        Der Ticket-Cog haelt seine Daten in einer eigenen
        sqlite3-Verbindung. Hier wird nur gelesen, deshalb eine eigene
        kurze Verbindung -- die des Cogs gehoert ihm.
        """
        try:
            conn = sqlite3.connect(TICKET_DB, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(
                    "SELECT channel_id, ticket_number, guild_id, creator_id, closed_at"
                    " FROM open_tickets WHERE channel_id = ?",
                    (channel_id,),
                )
                return cur.fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.debug(f"Ticket-Datenbank nicht lesbar: {exc}")
            return None

    def _staff_role_ids(self, guild_id: int) -> set[int]:
        """
        Die Rollen, die als Team gelten.

        Zusammen aus den serverweiten Rollen und denen der Kategorien --
        wer eine davon hat, zaehlt als Teammitglied.
        """
        rollen: set[int] = set()
        try:
            conn = sqlite3.connect(TICKET_DB, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                try:
                    cur = conn.execute(
                        "SELECT staff_roles FROM guild_configs WHERE guild_id = ?",
                        (guild_id,),
                    )
                    row = cur.fetchone()
                    if row and row["staff_roles"]:
                        for teil in str(row["staff_roles"]).split(","):
                            if teil.strip().isdigit():
                                rollen.add(int(teil.strip()))
                except sqlite3.Error:
                    # Die Spalte gibt es erst seit dem Dashboard-Umbau.
                    pass

                cur = conn.execute(
                    "SELECT notified_roles FROM ticket_categories WHERE guild_id = ?",
                    (guild_id,),
                )
                for row in cur.fetchall():
                    if row["notified_roles"]:
                        for teil in str(row["notified_roles"]).split(","):
                            if teil.strip().isdigit():
                                rollen.add(int(teil.strip()))
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.debug(f"Team-Rollen nicht lesbar: {exc}")
        return rollen

    def _is_staff(self, member: discord.Member, guild_id: int) -> bool:
        """
        Zaehlt dieses Mitglied als Team?

        Neben den eingestellten Rollen gilt auch, wer den Kanal
        verwalten darf -- sonst wuerde ein Administrator ohne
        Team-Rolle als Nutzer gezaehlt, und das Ticket bekaeme nie den
        Zustand "es war jemand da".
        """
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.manage_channels:
            return True
        rollen = self._staff_role_ids(guild_id)
        if not rollen:
            return False
        return any(r.id in rollen for r in member.roles)

    # ── Mitlesen ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        ticket = self._ticket_row(message.channel.id)
        if ticket is None or ticket["closed_at"]:
            return

        istaff = self._is_staff(message.author, message.guild.id)

        # Der Ersteller ist nie "Team" in seinem eigenen Ticket. Ohne
        # diese Zeile wuerde ein Moderator, der selbst ein Ticket
        # aufmacht, sich seine eigenen Antworten melden.
        if int(ticket["creator_id"]) == message.author.id:
            istaff = False

        try:
            await ticket_notify.note_message(
                message.channel.id,
                author_id=message.author.id,
                is_staff=istaff,
                guild_id=message.guild.id,
                creator_id=int(ticket["creator_id"]),
            )
        except Exception as exc:
            logger.error(f"Ticket-Zustand nicht gespeichert: {type(exc).__name__}: {exc}")

    # ── Der Hintergrundlauf ──────────────────────────────────────────

    @tasks.loop(seconds=INTERVALL)
    async def check_pending(self):
        try:
            offen = await ticket_notify.due_tickets()
        except Exception as exc:
            logger.error(f"Faellige Tickets nicht lesbar: {type(exc).__name__}: {exc}")
            return

        for eintrag in offen:
            for kind in ("user", "staff"):
                if not eintrag[f"pending_{kind}"]:
                    continue
                try:
                    await self._maybe_send(eintrag["channel_id"], kind)
                except Exception as exc:
                    logger.error(
                        f"Ticket-DM ({kind}) fuer {eintrag['channel_id']} "
                        f"fehlgeschlagen: {type(exc).__name__}: {exc}"
                    )

    @check_pending.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
        try:
            weg = await ticket_notify.cleanup()
            if weg:
                logger.info(f"{weg} alte Benachrichtigungs-Eintraege aufgeraeumt.")
        except Exception as exc:
            logger.warning(f"Aufraeumen uebersprungen: {exc}")

    async def _maybe_send(self, channel_id: int, kind: str):
        """Eine faellige Erinnerung pruefen und ggf. zustellen."""
        entscheidung = await ticket_notify.decide(channel_id, kind)
        if not entscheidung.send:
            # "Zu frueh" heisst spaeter nochmal. Alles andere ist
            # endgueltig -- den Eintrag stehen zu lassen hiesse, es alle
            # 30 Sekunden erneut zu versuchen.
            if entscheidung.reason not in ("too_soon", "disabled", "quiet_hours",
                                           "sleeping"):
                await ticket_notify.clear_pending(channel_id, kind)
            return

        kanal = self.bot.get_channel(channel_id)
        if kanal is None:
            await ticket_notify.forget(channel_id)
            return

        ticket = self._ticket_row(channel_id)
        if ticket is None or ticket["closed_at"]:
            await ticket_notify.forget(channel_id)
            return

        ziel = self.bot.get_user(entscheidung.target_id)
        if ziel is None:
            try:
                ziel = await self.bot.fetch_user(entscheidung.target_id)
            except discord.HTTPException:
                await ticket_notify.clear_pending(channel_id, kind)
                return

        nummer = ticket["ticket_number"]
        if kind == "user":
            view = ticket_dm.build_user_dm(
                guild_name=kanal.guild.name,
                kanal_url=kanal.jump_url,
                ticket_nr=nummer,
            )
        else:
            ersteller = self.bot.get_user(int(ticket["creator_id"]))
            view = ticket_dm.build_staff_dm(
                guild_name=kanal.guild.name,
                kanal_url=kanal.jump_url,
                user_name=ersteller.display_name if ersteller else "Der Ersteller",
                ticket_nr=nummer,
            )

        zugestellt = await ticket_dm.send_dm(ziel, view)
        if zugestellt:
            # Nur eine angekommene DM startet die Sperrzeit. Sonst
            # bliebe jemand mit geschlossenen DMs eine Stunde lang
            # gesperrt fuer eine Nachricht, die er nie bekommen hat.
            await ticket_notify.record_sent(
                channel_id, kanal.guild.id, entscheidung.target_id, kind
            )
        else:
            await ticket_notify.clear_pending(channel_id, kind)

    # ── >sleep und >wake ─────────────────────────────────────────────

    @commands.command(
        name="sleep",
        help="Legt dieses Ticket still -- keine Benachrichtigungen mehr",
        usage="sleep",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def _sleep(self, ctx):
        ticket = self._ticket_row(ctx.channel.id)
        if ticket is None or ticket["closed_at"]:
            return await ctx.reply(
                "Das geht nur in einem offenen Ticket."
            )
        if not self._is_staff(ctx.author, ctx.guild.id):
            return await ctx.reply("Das darf nur das Team.")

        await ticket_notify.register_ticket(
            ctx.channel.id, ctx.guild.id, int(ticket["creator_id"])
        )
        await ticket_notify.set_sleeping(ctx.channel.id, True, ctx.author.id)
        await ctx.reply(
            "Für dieses Ticket gehen jetzt **keine Benachrichtigungen** mehr raus "
            "— weder an das Team noch an den Ersteller.\n"
            "Mit `>wake` wieder an; beim Schließen des Tickets endet es ohnehin."
        )

    @commands.command(
        name="wake",
        help="Benachrichtigungen in diesem Ticket wieder einschalten",
        usage="wake",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def _wake(self, ctx):
        ticket = self._ticket_row(ctx.channel.id)
        if ticket is None or ticket["closed_at"]:
            return await ctx.reply("Das geht nur in einem offenen Ticket.")
        if not self._is_staff(ctx.author, ctx.guild.id):
            return await ctx.reply("Das darf nur das Team.")

        if await ticket_notify.set_sleeping(ctx.channel.id, False):
            await ctx.reply("Benachrichtigungen für dieses Ticket sind wieder an.")
        else:
            await ctx.reply("Für dieses Ticket war nichts stillgelegt.")
