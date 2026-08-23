# ╔══════════════════════════════════════════════════════════════════╗
# ║   Honeypot -- der Koeder-Kanal                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Ein Kanal ganz oben, in den niemand schreiben soll.

Ablauf
------
1. Im Dashboard einschalten.
2. Der Bot legt `#dont-sent-here` an -- **ausserhalb jeder Kategorie
   und auf Position 0**, also ueber allem anderen.
3. Jeder darf ihn sehen und darin schreiben. Genau das ist der Koeder.
4. In den Kanal kommt eine Nachricht mit deutlicher Warnung und einem
   Knopf, auf dem die Zahl der Treffer steht.
5. Wer trotzdem schreibt, wird softgebannt: bannen, Nachrichten der
   letzten Tage loeschen, sofort entbannen.

Warum Position 0 der ganze Trick ist
------------------------------------
Spam-Bots gehen den Kanalbaum von oben nach unten durch und schreiben
in den ersten Kanal, in dem sie duerfen. Text lesen sie nicht. Steht
der Koeder weiter unten, hat der Bot vorher schon in einen echten
Kanal geschrieben -- die Falle kaeme zu spaet.

Deshalb wird die Position auch bei jedem Einschalten neu gesetzt,
nicht nur beim Anlegen: neue Kategorien schieben einen bestehenden
Kanal nach unten.

Stillschweigen
--------------
Kann der Bot jemanden nicht bannen, passiert **nichts**. Keine
Antwort im Kanal, keine Nachricht an den Inhaber. Nur die Zeile im
Log-Kanal, falls einer eingestellt ist. So gewuenscht -- und
inhaltlich richtig: eine Fehlermeldung im Koeder-Kanal wuerde
verraten, dass die Falle Grenzen hat.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from utils import honeypot as store
from utils.emoji import ICONS_WARNING
from utils.panels import from_embed

log = logging.getLogger(__name__)


class KicksButton(discord.ui.View):
    """Die Nachricht im Koeder-Kanal.

    Der Knopf zeigt die Zahl der Treffer und tut sonst nichts -- er
    ist eine Anzeige, kein Bedienelement. `timeout=None` und eine
    feste `custom_id`, damit er einen Neustart ueberlebt: ohne beides
    ist der Knopf nach jedem Deploy tot und muesste neu gesendet
    werden.
    """

    def __init__(self, kicks: int = 0):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label=f"Softbans: {kicks}",
                emoji=ICONS_WARNING,
                style=discord.ButtonStyle.secondary,
                disabled=True,
                custom_id="honeypot:kicks",
            )
        )


class Honeypot(Cog):
    """Der Koeder-Kanal und was danach passiert."""

    def __init__(self, client):
        self.client = client
        self._connection = None

    async def cog_load(self) -> None:
        import aiosqlite

        self._connection = await aiosqlite.connect(store.DB_PATH)
        await store.ensure_schema(self._connection)

    async def cog_unload(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _db(self):
        if self._connection is None:
            import aiosqlite

            self._connection = await aiosqlite.connect(store.DB_PATH)
            await store.ensure_schema(self._connection)
        return self._connection

    async def settings(self, guild_id: int) -> dict:
        return await store.get(await self._db(), guild_id)

    # ── Der Kanal ────────────────────────────────────────────────────

    def _finde_alten_kanal(self, guild) -> discord.TextChannel | None:
        """Einen frueher angelegten Koeder-Kanal wiedererkennen.

        Ausdruecklicher Wunsch: „wenn man funktion an aus und wieder
        an channel falls es schon bot mal ein erstellt hat
        uebernehmen". Ohne das haette der Server nach dem dritten
        Umschalten drei Kanaele namens `dont-sent-here`.

        Gesucht wird ueber den Namen, weil die gespeicherte ID genau
        dann fehlt, wenn es darauf ankommt -- etwa nach einem Deploy
        ohne Volume.
        """
        for kanal in getattr(guild, "text_channels", []):
            if kanal.name == store.DEFAULT_CHANNEL_NAME:
                return kanal
        return None

    async def _stelle_kanal_sicher(self, guild, daten: dict):
        """Den Koeder-Kanal beschaffen: eigener, alter oder neuer.

        Rueckgabe ist der Kanal oder None, wenn nichts davon geht.
        """
        # 1. Ein im Dashboard ausdruecklich gewaehlter Kanal hat Vorrang.
        eigener = daten.get("custom_channel_id")
        if eigener:
            kanal = guild.get_channel(int(eigener))
            if kanal is not None:
                return kanal
            # Eingestellt, aber geloescht: nicht heimlich einen neuen
            # anlegen. Der Server hat sich fuer einen bestimmten Kanal
            # entschieden, und ein zweiter waere eine Ueberraschung.
            return None

        # 2. Der zuletzt benutzte.
        bekannt = daten.get("channel_id")
        if bekannt:
            kanal = guild.get_channel(int(bekannt))
            if kanal is not None:
                return kanal

        # 3. Einer, den der Bot frueher schon angelegt hat.
        alt = self._finde_alten_kanal(guild)
        if alt is not None:
            return alt

        # 4. Neu anlegen.
        return await self._lege_kanal_an(guild)

    async def _lege_kanal_an(self, guild):
        """Den Koeder-Kanal anlegen -- offen fuer alle, ganz oben."""
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return None

        # Jeder sieht ihn, jeder darf schreiben. Das ist der Sinn.
        # `add_reactions=False`, damit der Kanal nicht als Spielwiese
        # benutzt wird, ohne dass es einen Softban gibt -- eine
        # Reaktion ist keine Nachricht und loest nichts aus.
        rechte = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
                attach_files=False,
                embed_links=False,
            ),
            me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                embed_links=True,
            ),
        }

        try:
            return await guild.create_text_channel(
                store.DEFAULT_CHANNEL_NAME,
                overwrites=rechte,
                position=0,
                topic=(
                    "Nicht hineinschreiben. Dieser Kanal faengt Spam-Bots ab."
                ),
                reason="Honeypot eingeschaltet",
            )
        except discord.Forbidden:
            return None
        except discord.HTTPException as fehler:
            log.warning("[honeypot] Kanal anlegen fehlgeschlagen: %s", fehler)
            return None

    async def _nach_oben(self, kanal) -> None:
        """Den Kanal ueber alles andere schieben.

        Auch bei einem bestehenden Kanal noetig, nicht nur beim
        Anlegen: eine neue Kategorie schiebt ihn wieder nach unten,
        und dann greift die Falle nicht mehr als Erstes.

        Ein eigener, im Dashboard gewaehlter Kanal wird NICHT
        verschoben -- wer ihn selbst aussucht, hat ihn dort hingelegt,
        wo er ihn haben will.
        """
        try:
            if kanal.category is not None:
                await kanal.edit(category=None, position=0,
                                 reason="Honeypot ganz nach oben")
            elif kanal.position != 0:
                await kanal.edit(position=0, reason="Honeypot ganz nach oben")
        except (discord.Forbidden, discord.HTTPException):
            # Nicht schlimm genug, um das Einschalten scheitern zu
            # lassen: ein Koeder an zweiter Stelle faengt immer noch
            # die meisten Bots.
            pass

    # ── Die Nachricht ────────────────────────────────────────────────

    def _baue_embed(self, daten: dict) -> discord.Embed:
        embed = discord.Embed(
            title=daten.get("title") or store.DEFAULT_TITLE,
            description=daten.get("text") or store.DEFAULT_TEXT,
            colour=0x2B2D31,
        )
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/emojis/1041498063641903204.png"
        )
        return embed

    async def sende_oder_aktualisiere(self, guild, daten: dict | None = None):
        """Die Koeder-Nachricht schreiben oder die vorhandene anpassen.

        Rueckgabe: die Nachricht oder None.
        """
        if daten is None:
            daten = await self.settings(guild.id)

        kanal_id = daten.get("channel_id")
        if not kanal_id:
            return None
        kanal = guild.get_channel(int(kanal_id))
        if kanal is None:
            return None

        panel = from_embed(
            self._baue_embed(daten), KicksButton(daten.get("kicks", 0))
        )

        # Erst versuchen, die bestehende Nachricht zu aendern. Sonst
        # sammeln sich bei jedem Umschalten neue Warnungen an.
        nachricht_id = daten.get("message_id")
        if nachricht_id:
            try:
                # `get_message` gibt es in discord.py 2.7 nicht mehr.
                nachricht = await kanal.fetch_message(int(nachricht_id))
                await nachricht.edit(embed=None, view=panel)
                return nachricht
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # geloescht oder unerreichbar -- neu senden

        try:
            nachricht = await kanal.send(view=panel)
        except (discord.Forbidden, discord.HTTPException):
            return None

        await store.save(
            await self._db(), guild.id, message_id=nachricht.id
        )
        return nachricht

    async def _aktualisiere_zaehler(self, guild, daten: dict) -> None:
        """Nur den Knopf nachfuehren.

        Getrennt vom Senden, weil das der haeufige Fall ist: nach
        jedem Treffer eine Zahl aendern, nicht eine neue Nachricht
        schreiben.
        """
        kanal_id = daten.get("channel_id")
        nachricht_id = daten.get("message_id")
        if not kanal_id or not nachricht_id:
            return
        kanal = guild.get_channel(int(kanal_id))
        if kanal is None:
            return
        try:
            nachricht = await kanal.fetch_message(int(nachricht_id))
            await nachricht.edit(
                embed=None,
                view=from_embed(
                    self._baue_embed(daten),
                    KicksButton(daten.get("kicks", 0)),
                ),
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    # ── Ein- und Ausschalten ─────────────────────────────────────────

    async def aktiviere(self, guild) -> dict:
        """Kanal beschaffen, nach oben schieben, Nachricht setzen."""
        daten = await self.settings(guild.id)
        kanal = await self._stelle_kanal_sicher(guild, daten)
        if kanal is None:
            return {"ok": False, "grund": "Kanal konnte nicht angelegt werden."}

        # Nur einen selbst angelegten Kanal verschieben.
        if not daten.get("custom_channel_id"):
            await self._nach_oben(kanal)

        daten = await store.save(
            await self._db(), guild.id, enabled=True, channel_id=kanal.id
        )
        nachricht = await self.sende_oder_aktualisiere(guild, daten)

        return {
            "ok": True,
            "channel_id": str(kanal.id),
            "message_id": str(nachricht.id) if nachricht else None,
        }

    # ── Das Ereignis ─────────────────────────────────────────────────

    def _ist_geschuetzt(self, member, daten: dict) -> bool:
        """Darf diese Person hier schreiben, ohne bestraft zu werden?

        Ausdruecklich knapp gehalten: „jeder man kann aber rollen
        whitelisten". Also trifft es grundsaetzlich alle -- ausser
        Bots (die sollen den Koeder nicht selbst ausloesen), dem
        Server-Inhaber (den kann Discord ohnehin nicht bannen) und
        den ausgewaehlten Rollen.
        """
        if member.bot:
            return True
        if member.id == member.guild.owner_id:
            return True

        erlaubt = set(daten.get("whitelist_roles") or [])
        if erlaubt and any(rolle.id in erlaubt for rolle in member.roles):
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot:
            return

        daten = await self.settings(message.guild.id)
        if not daten.get("enabled"):
            return
        if not daten.get("channel_id"):
            return
        if message.channel.id != int(daten["channel_id"]):
            return

        member = message.guild.get_member(message.author.id) or message.author
        if self._ist_geschuetzt(member, daten):
            return

        await self._softban(message, member, daten)

    async def _softban(self, message, member, daten: dict) -> None:
        """Bannen, Nachrichten loeschen, sofort entbannen.

        Schlaegt irgendetwas davon fehl, passiert **nichts weiter**:
        keine Antwort im Kanal, keine Nachricht an den Inhaber. So
        ausdruecklich gewuenscht.
        """
        guild = message.guild
        me = guild.me
        if me is None or not me.guild_permissions.ban_members:
            return

        # Rangfolge: Discord verbietet Aktionen gegen jemanden, der
        # gleich hoch oder hoeher steht. Vorher pruefen erspart einen
        # Fehlschlag mitten im Ablauf -- und bleibt still.
        oben = getattr(member, "top_role", None)
        if oben is not None and me.top_role <= oben:
            return

        tage = int(daten.get("delete_days", store.DEFAULT_DELETE_DAYS))

        try:
            # `delete_message_seconds`, nicht `delete_message_days`:
            # letzteres ist in discord.py 2.7.1 veraltet und schreibt
            # bei jedem Softban eine DeprecationWarning ins Log --
            # nachgesehen in discord.Guild.ban, die Meldung lautet
            # woertlich "delete_message_days is deprecated, use
            # delete_message_seconds instead".
            await guild.ban(
                member,
                reason="Honeypot: Nachricht im Koeder-Kanal",
                delete_message_seconds=tage * 86400,
            )
        except (discord.Forbidden, discord.HTTPException):
            return  # still

        try:
            await guild.unban(
                discord.Object(id=member.id),
                reason="Honeypot: Softban -- sofort wieder entbannt",
            )
        except (discord.Forbidden, discord.HTTPException):
            # Der Bann steht, das Entbannen ging schief. Aus dem
            # Softban wurde ein Bann. Auch hier keine Meldung -- aber
            # protokollieren, denn das ist ein echter Unterschied.
            log.warning(
                "[honeypot] %s in %s gebannt, Entbannen fehlgeschlagen",
                member.id, guild.id,
            )

        neu = await store.bump_kicks(await self._db(), guild.id)
        daten = {**daten, "kicks": neu}

        await self._aktualisiere_zaehler(guild, daten)
        await self._schreibe_log(guild, member, daten, neu)

    async def _schreibe_log(self, guild, member, daten: dict, stand: int) -> None:
        """Eine Zeile in den Log-Kanal, falls einer eingestellt ist."""
        kanal_id = daten.get("log_channel_id")
        if not kanal_id:
            return
        kanal = guild.get_channel(int(kanal_id))
        if kanal is None:
            return

        embed = discord.Embed(
            title=f"{ICONS_WARNING} Honeypot ausgelöst",
            description=(
                f"{member.mention} (`{member.id}`) hat in den Köder-Kanal "
                f"geschrieben und wurde softgebannt."
            ),
            colour=0xED4245,
        )
        embed.add_field(name="Softbans insgesamt", value=str(stand))
        try:
            await kanal.send(view=from_embed(embed))
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── Nach einem Neustart ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Die Knoepfe wieder anhaengen.

        Ohne das ist der Zaehler-Knopf nach jedem Deploy tot. Er ist
        zwar ohnehin `disabled`, aber Discord blendet eine Ansicht
        ohne registrierten Empfaenger nach einiger Zeit aus.
        """
        try:
            self.client.add_view(KicksButton(0))
        except Exception:  # noqa: BLE001 - schon registriert
            pass


async def setup(client):
    await client.add_cog(Honeypot(client))
