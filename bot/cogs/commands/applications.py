# ╔══════════════════════════════════════════════════════════════════╗
# ║   Bewerbungen                                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Bewerbungen: Auswahlmenue im Kanal, Fragen per DM, Entscheidung im Team.

Der Ablauf:

  1. Im Kanal steht ein Panel mit einem Auswahlmenue. Wer eine Kategorie
     waehlt, bekommt eine kurze Bestaetigung -- nur fuer ihn sichtbar --
     und danach eine DM.
  2. Der Bot stellt die Fragen aus dem Dashboard einzeln. Nach jeder
     Antwort kommt die naechste.
  3. Am Ende geht die Zusammenfassung in den eingestellten Kanal, mit
     zwei Knoepfen: annehmen und ablehnen, beide mit Begruendung.
  4. Die Person bekommt die Entscheidung per DM.

**Warum der Fortschritt in der Datenbank liegt und nicht in einem
``wait_for``:** Railway startet den Container bei jedem Deploy neu. Ein
wartender Task waere danach weg, und die halbe Bewerbung haette
niemand mehr -- der Bewerber sitzt vor einer Frage, die nie beantwortet
wird. So wird nach dem Neustart einfach weitergemacht.

**Warum die Knoepfe feste custom_id tragen:** eine Bewerbung liegt
tagelang im Kanal. Ein View mit Zeitbegrenzung waere nach dem naechsten
Neustart tot, und die Knoepfe taeten nichts mehr. Die ID enthaelt die
Nummer der Bewerbung, damit auch ein frisch gestarteter Bot weiss,
worum es geht.
"""

import logging
import time

import discord
from discord.ext import commands, tasks

from utils import application_store as store
from utils.cv2 import CV2
from utils.emoji import CROSS, TICK, ZWRENCH
from utils.panels import from_embed

logger = logging.getLogger(__name__)

FARBE_OFFEN = 0x3B82F6
FARBE_ANGENOMMEN = 0x22C55E
FARBE_ABGELEHNT = 0xEF4444


def _fmt_dauer(sekunden: int) -> str:
    if sekunden >= 86400:
        tage = sekunden // 86400
        return f"{tage} {'Tag' if tage == 1 else 'Tagen'}"
    stunden = max(1, sekunden // 3600)
    return f"{stunden} {'Stunde' if stunden == 1 else 'Stunden'}"


class ApplicationPanelView(discord.ui.View):
    """Das Auswahlmenue im Kanal. Ohne Zeitbegrenzung -- es bleibt stehen."""

    def __init__(self, cog, panel: dict | None = None):
        super().__init__(timeout=None)
        self.cog = cog

        optionen = []
        for kategorie in (panel or {}).get("categories", []):
            emoji = kategorie.get("emoji") or None
            optionen.append(
                discord.SelectOption(
                    label=kategorie["name"][:100],
                    value=str(kategorie["category_id"]),
                    description=(kategorie.get("description") or "")[:100] or None,
                    emoji=emoji,
                )
            )

        if not optionen:
            optionen = [
                discord.SelectOption(label="Noch keine Kategorie", value="none")
            ]

        self.auswahl = discord.ui.Select(
            placeholder=(panel or {}).get("placeholder")
            or "Wofuer moechtest du dich bewerben?",
            options=optionen[:store.MAX_CATEGORIES],
            custom_id="application_panel_select",
        )
        self.auswahl.callback = self._gewaehlt
        self.add_item(self.auswahl)

    async def _gewaehlt(self, interaction: discord.Interaction):
        werte = interaction.data.get("values") or []
        if not werte or not str(werte[0]).isdigit():
            return await interaction.response.send_message(
                "Diese Kategorie gibt es nicht mehr.", ephemeral=True
            )
        await self.cog.start_application(interaction, int(werte[0]))


class DecisionModal(discord.ui.Modal):
    """Der Grund fuer eine Entscheidung. Pflichtfeld, in beide Richtungen."""

    def __init__(self, cog, application_id: int, status: str):
        angenommen = status == store.STATUS_ACCEPTED
        super().__init__(
            title="Bewerbung annehmen" if angenommen else "Bewerbung ablehnen",
            timeout=600,
        )
        self.cog = cog
        self.application_id = application_id
        self.status = status

        self.grund = discord.ui.TextInput(
            label="Begruendung",
            style=discord.TextStyle.paragraph,
            placeholder=(
                "Was der Bewerber dazu erfaehrt."
                if angenommen
                else "Warum es nicht gereicht hat."
            ),
            required=True,
            max_length=1000,
        )
        self.add_item(self.grund)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.finish_decision(
            interaction, self.application_id, self.status, str(self.grund.value)
        )


class DecisionView(discord.ui.View):
    """
    Annehmen und ablehnen unter der Bewerbung.

    Die ``custom_id`` traegt die Nummer der Bewerbung, damit die Knoepfe
    einen Neustart ueberleben: ein frisch gestarteter Bot liest sie aus
    der ID heraus, statt sich an einen View im Arbeitsspeicher erinnern
    zu muessen.
    """

    def __init__(self, cog, application_id: int = 0, *, entschieden: bool = False):
        super().__init__(timeout=None)
        self.cog = cog

        if entschieden:
            # Nach der Entscheidung bleibt die Nachricht stehen, aber
            # ohne Knoepfe -- sonst klickt jemand ins Leere.
            return

        annehmen = discord.ui.Button(
            label="Annehmen",
            style=discord.ButtonStyle.success,
            emoji=TICK,
            custom_id=f"app_accept_{application_id}",
        )
        ablehnen = discord.ui.Button(
            label="Ablehnen",
            style=discord.ButtonStyle.danger,
            emoji=CROSS,
            custom_id=f"app_deny_{application_id}",
        )
        annehmen.callback = self._annehmen
        ablehnen.callback = self._ablehnen
        self.add_item(annehmen)
        self.add_item(ablehnen)

    async def _annehmen(self, interaction: discord.Interaction):
        await self.cog.ask_reason(interaction, store.STATUS_ACCEPTED)

    async def _ablehnen(self, interaction: discord.Interaction):
        await self.cog.ask_reason(interaction, store.STATUS_DENIED)


class Applications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_sessions.start()

    def cog_unload(self):
        self.cleanup_sessions.cancel()

    # ── Panels wiederherstellen ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Die Auswahlmenues nach einem Neustart wieder ansprechbar machen.

        Ohne das reagiert das Panel im Kanal nicht mehr -- die Nachricht
        steht da, aber niemand hoert zu.
        """
        for guild in self.bot.guilds:
            try:
                panels = await store.list_panels(guild.id)
            except Exception as exc:
                logger.debug(f"Bewerbungs-Panels nicht lesbar: {exc}")
                continue
            for panel in panels:
                if not panel.get("message_id"):
                    continue
                try:
                    self.bot.add_view(
                        ApplicationPanelView(self, panel),
                        message_id=int(panel["message_id"]),
                    )
                except Exception:
                    pass

        await self._resume_sessions()

    async def _resume_sessions(self):
        """
        Laufende Bewerbungen nach einem Neustart wieder anstossen.

        Der Fehler, den das behebt: die Sitzung steht in der Datenbank,
        aber der Bot stellt die naechste Frage nur als Antwort auf eine
        Nachricht. Wer beim Deploy gerade auf eine Frage wartete,
        wartete danach fuer immer -- er antwortet nicht, weil er auf
        eine Frage wartet, und die kommt nicht, weil er nicht antwortet.

        Deshalb wird die offene Frage einmal neu gestellt. Dass sie
        doppelt ankommt, ist der deutlich kleinere Schaden.
        """
        try:
            offen = await store.all_sessions()
        except Exception as exc:
            logger.debug(f"Laufende Bewerbungen nicht lesbar: {exc}")
            return

        for sitzung in offen:
            kategorie = await store.get_category(sitzung["category_id"])
            if kategorie is None:
                # Die Kategorie wurde geloescht -- die Sitzung kann
                # nicht mehr weitergehen und blockiert die Person sonst.
                await store.end_session(sitzung["user_id"])
                continue

            index = sitzung["question_index"]
            if index >= len(kategorie["questions"]):
                # Alle Fragen beantwortet, aber das Absenden hat den
                # Neustart nicht ueberlebt. Jetzt nachholen.
                nutzer = self.bot.get_user(sitzung["user_id"])
                if nutzer is not None:
                    await self._submit(nutzer, sitzung["guild_id"], kategorie,
                                       sitzung["answers"])
                continue

            nutzer = self.bot.get_user(sitzung["user_id"])
            if nutzer is None:
                continue
            try:
                dm = await nutzer.create_dm()
                await dm.send(view=CV2(
                    "Weiter geht's",
                    "Der Bot wurde neu gestartet. Hier ist deine offene "
                    "Frage noch einmal:",
                ))
            except (discord.Forbidden, discord.HTTPException):
                continue
            await self._ask_next(nutzer, kategorie, index)

    # ── Der Einstieg ─────────────────────────────────────────────────

    async def start_application(self, interaction: discord.Interaction,
                                category_id: int):
        await interaction.response.defer(ephemeral=True)
        nutzer = interaction.user

        kategorie = await store.get_category(category_id)
        if kategorie is None:
            return await interaction.followup.send(
                "Diese Kategorie gibt es nicht mehr.", ephemeral=True
            )
        if len(kategorie["questions"]) < store.MIN_QUESTIONS:
            return await interaction.followup.send(
                "Für diese Kategorie sind noch keine Fragen hinterlegt. "
                "Bitte melde dich beim Team.",
                ephemeral=True,
            )

        # Nur eine Bewerbung gleichzeitig -- serveruebergreifend.
        offen = await store.has_open_anywhere(nutzer.id)
        if offen is not None:
            if offen["kind"] == "session":
                text = (
                    "Du hast gerade schon eine Bewerbung offen. Beantworte sie "
                    "erst zu Ende — schau in deine Direktnachrichten."
                )
            else:
                text = (
                    "Du hast bereits eine Bewerbung eingereicht, über die noch "
                    "nicht entschieden wurde. Bitte warte, bis das Team sich "
                    "gemeldet hat."
                )
            return await interaction.followup.send(text, ephemeral=True)

        # Sperre nach einer Ablehnung, falls im Dashboard eingeschaltet.
        panel = await store.get_panel(kategorie["panel_id"])
        if panel and panel.get("deny_cooldown_enabled"):
            frei_ab = await store.denied_until(
                nutzer.id, category_id, int(panel.get("deny_cooldown_days") or 0)
            )
            if frei_ab:
                return await interaction.followup.send(
                    f"Deine letzte Bewerbung für **{kategorie['name']}** wurde "
                    f"abgelehnt. Du kannst dich <t:{frei_ab}:R> wieder bewerben.",
                    ephemeral=True,
                )

        # Erst die DM versuchen, dann vormerken: geschlossene DMs sind
        # der haeufigste Fall, und dann darf keine Sitzung entstehen,
        # die niemand beantworten kann.
        try:
            dm = await nutzer.create_dm()
            await dm.send(view=CV2(
                f"{ZWRENCH} Bewerbung: {kategorie['name']}",
                f"Du bewirbst dich auf **{interaction.guild.name}**.\n"
                f"Ich stelle dir jetzt **{len(kategorie['questions'])} Fragen** "
                f"— eine nach der anderen.\n\n"
                f"Pro Frage hast du **{_fmt_dauer(store.ANSWER_TIMEOUT)}** Zeit. "
                f"Mit `abbrechen` steigst du jederzeit aus.",
            ))
        except discord.Forbidden:
            return await interaction.followup.send(
                "Ich kann dir keine Direktnachricht schicken. Stell sie in den "
                "Privatsphäre-Einstellungen dieses Servers an und versuch es "
                "noch einmal.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            logger.warning(f"Bewerbungs-DM fehlgeschlagen: {exc}")
            return await interaction.followup.send(
                "Die Direktnachricht ließ sich nicht senden. Bitte gleich noch "
                "einmal versuchen.",
                ephemeral=True,
            )

        await store.start_session(nutzer.id, interaction.guild.id, category_id)
        await self._ask_next(nutzer, kategorie, 0)

        await interaction.followup.send(
            f"{TICK} Erfolgreich — ich habe dir eine Direktnachricht geschickt. "
            f"Dort geht es weiter.",
            ephemeral=True,
        )

    async def _ask_next(self, user, kategorie: dict, index: int) -> bool:
        """Die naechste Frage stellen. False, wenn die DM nicht ankam."""
        fragen = kategorie["questions"]
        if index >= len(fragen):
            return True
        try:
            dm = await user.create_dm()
            await dm.send(view=CV2(
                f"Frage {index + 1} von {len(fragen)}",
                fragen[index],
            ))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    # ── Die Antworten ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Nur Direktnachrichten von Menschen.
        if message.author.bot or message.guild is not None:
            return
        if not message.content:
            return

        sitzung = await store.get_session(message.author.id)
        if sitzung is None:
            # Kein laufendes Gespraech -- aber vielleicht eine
            # abgeschickte Bewerbung, die zurueckgezogen werden soll.
            # Ohne das ist blockiert, wer sich vertippt hat: eine offene
            # Bewerbung laesst keine zweite zu, und bis das Team
            # entscheidet koennen Tage vergehen.
            if message.content.strip().lower() in ("zurückziehen", "zurueckziehen",
                                                   "withdraw"):
                await self._withdraw(message.author, message.channel)
            return

        if message.content.strip().lower() in ("abbrechen", "cancel", "stop"):
            await store.end_session(message.author.id)
            return await message.channel.send(view=CV2(
                f"{CROSS} Abgebrochen",
                "Deine Bewerbung wurde verworfen. Du kannst jederzeit neu "
                "anfangen.",
            ))

        kategorie = await store.get_category(sitzung["category_id"])
        if kategorie is None:
            await store.end_session(message.author.id)
            return await message.channel.send(view=CV2(
                f"{CROSS} Abgebrochen",
                "Diese Bewerbungskategorie gibt es nicht mehr.",
            ))

        aktualisiert = await store.record_answer(
            message.author.id, message.content.strip()
        )
        if aktualisiert is None:
            return

        fragen = kategorie["questions"]
        if aktualisiert["question_index"] < len(fragen):
            await self._ask_next(
                message.author, kategorie, aktualisiert["question_index"]
            )
            return

        # Fertig.
        await self._submit(message.author, sitzung["guild_id"], kategorie,
                           aktualisiert["answers"])

    async def _withdraw(self, user, kanal):
        """Eine abgeschickte Bewerbung zurueckziehen."""
        bewerbung = await store.withdraw(user.id)
        if bewerbung is None:
            return await kanal.send(view=CV2(
                "Nichts zurueckzuziehen",
                "Du hast gerade keine offene Bewerbung.",
            ))

        # Die Nachricht im Team-Kanal entwerten, sonst entscheidet
        # jemand ueber eine Bewerbung, die es nicht mehr gibt.
        kategorie = await store.get_category(bewerbung["category_id"])
        if bewerbung.get("message_id") and kategorie:
            kanal_id = kategorie.get("results_channel_id")
            if not kanal_id:
                panel = await store.get_panel(kategorie["panel_id"])
                kanal_id = (panel or {}).get("results_channel_id")
            ziel = self.bot.get_channel(int(kanal_id)) if kanal_id else None
            if ziel is not None:
                try:
                    nachricht = await ziel.fetch_message(int(bewerbung["message_id"]))
                    alt_embed = nachricht.embeds[0] if nachricht.embeds else None
                    embed = discord.Embed(
                        title=(alt_embed.title if alt_embed else "Bewerbung"),
                        description=(alt_embed.description if alt_embed else ""),
                        color=0x64748B,
                    )
                    for feld in (alt_embed.fields if alt_embed else []):
                        embed.add_field(name=feld.name, value=feld.value,
                                        inline=feld.inline)
                    embed.add_field(
                        name="Zurueckgezogen",
                        value="Der Bewerber hat die Bewerbung selbst zurueckgezogen.",
                        inline=False,
                    )
                    embed.set_footer(text=f"Bewerbung #{bewerbung['id']}")
                    await nachricht.edit(
                        view=from_embed(embed, DecisionView(self, entschieden=True))
                    )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await kanal.send(view=CV2(
            f"{TICK} Zurueckgezogen",
            "Deine Bewerbung wurde zurueckgezogen. Du kannst dich jetzt "
            "wieder neu bewerben.",
        ))

    async def _submit(self, user, guild_id: int, kategorie: dict,
                      antworten: list[str]):
        await store.end_session(user.id)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return await user.send(view=CV2(
                f"{CROSS} Etwas ist schiefgelaufen",
                "Der Server ist nicht mehr erreichbar.",
            ))

        bewerbung_id = await store.submit(guild_id, kategorie["category_id"],
                                          user.id, antworten)

        panel = await store.get_panel(kategorie["panel_id"])
        kanal_id = kategorie.get("results_channel_id") or (
            panel or {}).get("results_channel_id")
        kanal = self.bot.get_channel(int(kanal_id)) if kanal_id else None

        if kanal is None:
            logger.warning(
                f"Bewerbung {bewerbung_id}: kein Ergebniskanal eingestellt."
            )
            return await user.send(view=CV2(
                f"{TICK} Danke",
                "Deine Bewerbung ist eingegangen. Das Team meldet sich.",
            ))

        embed = self._build_embed(user, guild, kategorie, antworten,
                                  bewerbung_id)

        # Das Team erwaehnen.
        #
        # Ohne das landet die Bewerbung im Kanal und niemand merkt es --
        # wer nicht zufaellig hinsieht, laesst den Bewerber tagelang
        # warten. Nur Rollen, die es noch gibt, und nur solche, die der
        # Bot auch erwaehnen darf; sonst steht dort eine tote ID.
        erwaehnungen = []
        for rollen_id in kategorie.get("staff_roles") or []:
            if not str(rollen_id).isdigit():
                continue
            rolle = guild.get_role(int(rollen_id))
            if rolle is not None:
                erwaehnungen.append(rolle.mention)

        # Die Erwaehnung gehoert IN die Karte, nicht daneben.
        #
        # `from_embed` baut eine Components-V2-Ansicht, und mit dem
        # V2-Flag gibt es kein content-Feld mehr -- Discord antwortet
        # mit 50035. Nachgeprueft: utils.panels.Panel ist eine
        # LayoutView. Also wird die Zeile an die Beschreibung gehaengt.
        if erwaehnungen:
            embed.description = f"{' '.join(erwaehnungen)}\n{embed.description}"

        # allowed_mentions ausdruecklich: der Bot soll die Team-Rollen
        # anpingen duerfen, aber nichts anderes -- eine Antwort des
        # Bewerbers koennte sonst @everyone enthalten.
        erlaubt = discord.AllowedMentions(
            everyone=False, users=False,
            roles=[r for r in (guild.get_role(int(x))
                               for x in (kategorie.get("staff_roles") or [])
                               if str(x).isdigit())
                   if r is not None],
        )

        try:
            nachricht = await kanal.send(
                view=from_embed(embed, DecisionView(self, bewerbung_id)),
                allowed_mentions=erlaubt,
            )
            await store.attach_message(bewerbung_id, nachricht.id)
        except discord.Forbidden:
            logger.warning(f"Keine Schreibrechte in {kanal.id} fuer Bewerbungen.")
        except discord.HTTPException as exc:
            logger.warning(f"Bewerbung nicht zustellbar: {exc}")

        await user.send(view=CV2(
            f"{TICK} Bewerbung abgeschickt",
            f"Deine Bewerbung für **{kategorie['name']}** auf "
            f"**{guild.name}** ist eingegangen.\n"
            f"Du bekommst hier Bescheid, sobald das Team entschieden hat.\n\n"
            f"-# Mit `zurückziehen` kannst du sie hier wieder zurücknehmen.",
        ))

    def _build_embed(self, user, guild, kategorie: dict,
                     antworten: list[str], bewerbung_id: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"Neue Bewerbung: {kategorie['name']}",
            description=f"von {user.mention} (`{user.id}`)",
            color=FARBE_OFFEN,
            timestamp=discord.utils.utcnow(),
        )
        # Discord erlaubt 25 Felder; bei zwanzig Fragen bleibt Luft.
        for nummer, (frage, antwort) in enumerate(
            zip(kategorie["questions"], antworten), start=1
        ):
            embed.add_field(
                name=f"{nummer}. {frage[:250]}",
                value=(antwort or "—")[:1024],
                inline=False,
            )
        # Wann sie eingegangen ist -- sonst sieht man nicht, ob eine
        # Bewerbung von heute oder von letzter Woche ist.
        embed.add_field(
            name="Eingegangen",
            value=f"<t:{int(time.time())}:R>",
            inline=False,
        )
        embed.set_footer(text=f"Bewerbung #{bewerbung_id}")
        try:
            embed.set_thumbnail(url=user.display_avatar.url)
        except Exception:
            pass
        return embed

    # ── Die Entscheidung ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Die Knoepfe nach einem Neustart wieder bedienen.

        Der View im Arbeitsspeicher ist dann weg; die Nummer steckt aber
        in der custom_id, also laesst sich die Bewerbung trotzdem finden.
        """
        if interaction.type != discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id", "")
        if not cid.startswith(("app_accept_", "app_deny_")):
            return
        # Ein registrierter View hat schon geantwortet.
        if interaction.response.is_done():
            return

        status = (store.STATUS_ACCEPTED if cid.startswith("app_accept_")
                  else store.STATUS_DENIED)
        await self.ask_reason(interaction, status)

    async def ask_reason(self, interaction: discord.Interaction, status: str):
        cid = (interaction.data or {}).get("custom_id", "")
        nummer = cid.rsplit("_", 1)[-1]
        if not nummer.isdigit():
            return await interaction.response.send_message(
                "Diese Bewerbung lässt sich nicht mehr zuordnen.", ephemeral=True
            )

        bewerbung = await store.get_application(int(nummer))
        if bewerbung is None:
            return await interaction.response.send_message(
                "Diese Bewerbung gibt es nicht mehr.", ephemeral=True
            )
        if bewerbung["status"] != store.STATUS_OPEN:
            return await interaction.response.send_message(
                "Über diese Bewerbung wurde bereits entschieden.", ephemeral=True
            )

        if not await self._darf_entscheiden(interaction, bewerbung):
            return await interaction.response.send_message(
                "Du darfst über diese Bewerbung nicht entscheiden.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            DecisionModal(self, int(nummer), status)
        )

    async def _darf_entscheiden(self, interaction, bewerbung: dict) -> bool:
        """
        Wer darf annehmen oder ablehnen?

        Die Team-Rollen der Kategorie, sonst jeder, der den Server
        verwalten darf. Ohne eingestellte Rollen faellt es auf die
        Serverrechte zurueck -- eine leere Liste darf nicht heissen,
        dass niemand entscheiden kann.
        """
        mitglied = interaction.user
        if not isinstance(mitglied, discord.Member):
            return False
        if mitglied.guild_permissions.manage_guild:
            return True

        kategorie = await store.get_category(bewerbung["category_id"])
        rollen = {int(r) for r in (kategorie or {}).get("staff_roles", [])
                  if str(r).isdigit()}
        if not rollen:
            return False
        return any(r.id in rollen for r in mitglied.roles)

    async def finish_decision(self, interaction: discord.Interaction,
                              application_id: int, status: str, grund: str):
        bewerbung = await store.decide(
            application_id, status, interaction.user.id, grund
        )
        if bewerbung is None:
            return await interaction.response.send_message(
                "Über diese Bewerbung wurde inzwischen schon entschieden.",
                ephemeral=True,
            )

        angenommen = status == store.STATUS_ACCEPTED
        kategorie = await store.get_category(bewerbung["category_id"])

        # Die Nachricht im Kanal aktualisieren: neue Farbe, keine
        # Knoepfe mehr, und wer entschieden hat.
        try:
            nachricht = interaction.message
            if nachricht is not None:
                alt = nachricht.embeds[0] if nachricht.embeds else None
                embed = discord.Embed(
                    title=(alt.title if alt else "Bewerbung"),
                    description=(alt.description if alt else ""),
                    color=FARBE_ANGENOMMEN if angenommen else FARBE_ABGELEHNT,
                    timestamp=discord.utils.utcnow(),
                )
                for feld in (alt.fields if alt else []):
                    embed.add_field(name=feld.name, value=feld.value,
                                    inline=feld.inline)
                embed.add_field(
                    name="Angenommen von" if angenommen else "Abgelehnt von",
                    value=f"{interaction.user.mention}\n{grund[:1000]}",
                    inline=False,
                )
                embed.set_footer(text=f"Bewerbung #{application_id}")
                if alt and alt.thumbnail:
                    embed.set_thumbnail(url=alt.thumbnail.url)
                await nachricht.edit(
                    view=from_embed(embed, DecisionView(self, entschieden=True))
                )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

        # Die Rollen vergeben, falls eingestellt. Bis zu fünf.
        rollen_hinweis = ""
        problem_hinweis = ""
        if angenommen and kategorie:
            guild = interaction.guild
            mitglied = guild.get_member(int(bewerbung["user_id"])) if guild else None
            vergeben, gescheitert = await store.grant_accept_roles(
                guild, mitglied, kategorie
            )
            if vergeben:
                wort = "die Rolle" if len(vergeben) == 1 else "die Rollen"
                rollen_hinweis = (
                    f"\nDu hast {wort} **{', '.join(vergeben)}** bekommen."
                )
            if gescheitert:
                # Nicht verschweigen: was der Bot nicht vergeben konnte,
                # muss jemand von Hand nachtragen. Der Hinweis wird
                # gesammelt und unten an die Antwort gehaengt -- ein
                # followup ginge hier ins Leere, weil auf die Interaktion
                # noch gar nicht geantwortet wurde.
                logger.warning(
                    f"Bewerbung #{application_id}: nicht vergeben — "
                    f"{', '.join(gescheitert)}"
                )
                problem_hinweis = (
                    f"\n{CROSS} Nicht vergeben: {', '.join(gescheitert)} "
                    f"— bitte von Hand nachtragen."
                )

            # Ins Team uebernehmen, wenn das im Dashboard eingeschaltet
            # ist. Der Dienst entscheidet selbst, ob etwas zu tun ist,
            # und kuemmert sich um Akte, Ankuendigung und DM.
            #
            # In einem eigenen try: eine Ankuendigung, die scheitert,
            # darf die Annahme nicht zurueckdrehen -- die Rollen sind
            # zu dem Zeitpunkt schon vergeben.
            try:
                from utils import team_update as team_service

                uebernahme = await team_service.from_application(
                    self.bot, guild, mitglied, kategorie,
                    actor_id=interaction.user.id,
                )
                if uebernahme is not None and uebernahme.failed:
                    problem_hinweis += (
                        f"\n{CROSS} Team-Update: {', '.join(uebernahme.failed)}"
                    )
            except Exception as exc:
                logger.warning(f"Team-Uebernahme fehlgeschlagen: {exc}")

        # Und die Person benachrichtigen.
        nutzer = self.bot.get_user(int(bewerbung["user_id"]))
        if nutzer is None:
            try:
                nutzer = await self.bot.fetch_user(int(bewerbung["user_id"]))
            except discord.HTTPException:
                nutzer = None

        if nutzer is not None:
            name = kategorie["name"] if kategorie else "deine Bewerbung"
            server = interaction.guild.name if interaction.guild else "dem Server"
            try:
                if angenommen:
                    await nutzer.send(view=CV2(
                        f"{TICK} Bewerbung angenommen",
                        f"Deine Bewerbung für **{name}** auf **{server}** "
                        f"wurde angenommen.{rollen_hinweis}\n\n"
                        f"**Begründung:**\n{grund}",
                    ))
                else:
                    await nutzer.send(view=CV2(
                        f"{CROSS} Bewerbung abgelehnt",
                        f"Deine Bewerbung für **{name}** auf **{server}** "
                        f"wurde abgelehnt.\n\n**Begründung:**\n{grund}",
                    ))
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.response.send_message(
            f"{TICK} Bewerbung #{application_id} "
            f"{'angenommen' if angenommen else 'abgelehnt'}.{problem_hinweis}",
            ephemeral=True,
        )

    # ── Aufraeumen ───────────────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def cleanup_sessions(self):
        """
        Gespraeche schliessen, in denen zu lange nichts kam.

        Wichtig, weil eine offene Sitzung die Person daran hindert, sich
        woanders zu bewerben. Eine vergessene Bewerbung darf niemanden
        dauerhaft blockieren.
        """
        try:
            alt = await store.stale_sessions()
        except Exception as exc:
            logger.error(f"Bewerbungs-Aufraeumen fehlgeschlagen: {exc}")
            return

        for eintrag in alt:
            await store.end_session(eintrag["user_id"])
            nutzer = self.bot.get_user(eintrag["user_id"])
            if nutzer is None:
                continue
            try:
                await nutzer.send(view=CV2(
                    f"{CROSS} Bewerbung abgelaufen",
                    f"Du hast über {_fmt_dauer(store.ANSWER_TIMEOUT)} nicht "
                    f"geantwortet, deshalb wurde deine Bewerbung verworfen. "
                    f"Du kannst jederzeit neu anfangen.",
                ))
            except (discord.Forbidden, discord.HTTPException):
                pass

    @cleanup_sessions.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
