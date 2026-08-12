# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Update                                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Die fuenf Team-Befehle.

  ``/uprank``      befoerdern: neue Rolle drauf, alte runter
  ``/downrank``    zurueckstufen: dasselbe in die andere Richtung
  ``/teamkick``    aus dem Team nehmen: alle Teamrollen runter
  ``/teamwarn``    verwarnen: in die Akte, DM, optional eine Folge
  ``/teamanfang``  aufnehmen: Rolle drauf, Begruessung

Warum Slash und nicht Prefix
----------------------------
Jeder dieser Befehle nimmt einen Nutzer und ein bis zwei Rollen. Als
Prefix-Befehl hiesse das Namen abtippen und hoffen, dass der Bot die
richtige Rolle trifft -- bei "Moderator" und "Moderator+" trifft er
sie nicht. Discords Auswahl fuer Nutzer und Rollen kennt dieses
Problem nicht.

Die Unterschriften
------------------
Wer den Befehl abschickt, unterschreibt automatisch. Bis zu vier
weitere lassen sich angeben, fuer Entscheidungen, die das Team
gemeinsam getroffen hat. Sie stehen als eigene, optionale Parameter
da -- eine Liste in einem Textfeld waere wieder Namen abtippen.

Alles andere steht im Dashboard
-------------------------------
Kanaele, Vorlagen, wer die Befehle nutzen darf, ob eine DM rausgeht,
die Verwarnungs-Automatik: Reiter »Team-Update«. Hier steht nur, was
im Moment der Ausfuehrung passiert.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import team_update as service
from utils import team_update_store as store
from utils.cv2 import CV2
from utils.emoji import CROSS, TICK, WARNING

logger = logging.getLogger(__name__)


def _extra_signers(*mitglieder) -> list[int]:
    """Die zusaetzlichen Unterschriften, ohne Doppelte und ohne Luecken."""

    out: list[int] = []
    for m in mitglieder:
        if m is None:
            continue
        if int(m.id) not in out:
            out.append(int(m.id))
    return out[:store.MAX_EXTRA_SIGNERS]


def _summary(ergebnis: service.Result, settings: dict) -> str:
    """Was der Ausfuehrende danach zu sehen bekommt.

    Ausfuehrlich mit Absicht: eine Rolle, die nicht vergeben werden
    konnte, muss jemand von Hand nachtragen -- und dafuer muss er
    davon wissen. Ein blosses "Erledigt" haette das verschluckt.
    """
    zeilen = []
    if ergebnis.given:
        zeilen.append(f"{TICK} Gegeben: **{', '.join(ergebnis.given)}**")
    if ergebnis.removed:
        zeilen.append(f"{TICK} Entfernt: **{', '.join(ergebnis.removed)}**")
    if ergebnis.failed:
        zeilen.append(
            f"{CROSS} Nicht geklappt: {', '.join(ergebnis.failed)}\n"
            "Bitte von Hand nachtragen."
        )
    if ergebnis.announced and ergebnis.channel_id:
        zeilen.append(f"{TICK} Angekündigt in <#{ergebnis.channel_id}>")
    elif ergebnis.note:
        zeilen.append(f"{WARNING} Keine Ankündigung: {ergebnis.note}")
    if settings.get("dm_user"):
        zeilen.append(
            f"{TICK} DM zugestellt" if ergebnis.dm_sent
            else f"{WARNING} DM ging nicht raus (geschlossene Direktnachrichten)"
        )
    return "\n".join(zeilen) or "Erledigt."


class TeamUpdate(commands.Cog):
    """Befoerderungen, Rueckstufungen, Rauswuerfe, Verwarnungen."""

    def __init__(self, bot):
        self.bot = bot

    # ── Gemeinsame Vorpruefung ───────────────────────────────────────

    async def _prepare(self, interaction: discord.Interaction, grund: str):
        """
        Alles, was vor jeder der fuenf Aktionen gilt.

        Gibt ``(settings, templates)`` zurueck oder ``None``, wenn
        schon geantwortet wurde. Der Aufrufer bricht dann ab.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                f"{CROSS} Das geht nur auf einem Server.", ephemeral=True
            )
            return None

        settings = await store.get_settings(guild.id)

        if not settings.get("enabled"):
            await interaction.response.send_message(
                f"{WARNING} Das Team-Update ist auf diesem Server noch aus.\n"
                "Ein Admin kann es im Dashboard unter »Team-Update« "
                "einschalten.",
                ephemeral=True,
            )
            return None

        if not store.may_use(settings, interaction.user):
            await interaction.response.send_message(
                f"{CROSS} Du darfst die Team-Befehle nicht benutzen.\n"
                "Wer sie benutzen darf, steht im Dashboard.",
                ephemeral=True,
            )
            return None

        kanal_id = getattr(interaction.channel, "id", 0)
        if not store.may_run_here(settings, kanal_id):
            erlaubt = settings.get("command_channel_id")
            await interaction.response.send_message(
                f"{CROSS} Die Team-Befehle sind hier nicht freigegeben — "
                f"bitte in <#{erlaubt}>.",
                ephemeral=True,
            )
            return None

        if settings.get("require_reason") and not (grund or "").strip():
            await interaction.response.send_message(
                f"{CROSS} Für diese Aktion ist ein Grund Pflicht.",
                ephemeral=True,
            )
            return None

        templates = await store.get_templates(guild.id)
        return settings, templates

    def _check_hierarchy(self, interaction, ziel) -> str:
        """
        Darf diese Person ueber jene bestimmen?

        Ohne das koennte ein Moderator den Inhaber zurueckstufen,
        sobald er die Befehle nutzen darf. Der Serverinhaber selbst
        ist ausgenommen -- ueber ihm steht niemand.
        """
        ausfuehrend = interaction.user
        guild = interaction.guild
        if guild is not None and getattr(guild, "owner_id", None) == ausfuehrend.id:
            return ""
        if ziel.id == ausfuehrend.id:
            return "Das geht nicht mit dir selbst."
        if guild is not None and ziel.id == getattr(guild, "owner_id", None):
            return "Der Serverinhaber lässt sich so nicht bearbeiten."
        oben_ich = getattr(ausfuehrend, "top_role", None)
        oben_ziel = getattr(ziel, "top_role", None)
        if oben_ich is not None and oben_ziel is not None and oben_ziel >= oben_ich:
            return (
                f"**{ziel.display_name}** steht auf gleicher Höhe oder über dir."
            )
        return ""

    async def _finish(self, interaction, ergebnis, settings, templates, ziel):
        """Antworten -- und bei einer Verwarnung die Folge ausfuehren."""

        text = _summary(ergebnis, settings)

        if ergebnis.action == store.ACTION_WARN:
            schwelle = int(settings.get("warn_threshold") or 0)
            zusatz = f"\n\n**Verwarnungen:** {ergebnis.warn_count}"
            if schwelle > 0:
                zusatz += f" von {schwelle}"
            text += zusatz

            if ergebnis.followup != store.FOLLOWUP_NONE:
                folge = await service.apply_followup(
                    self.bot, interaction.guild, ziel, settings, templates,
                    ergebnis, actor_id=interaction.user.id,
                )
                if folge is not None:
                    wort = (
                        "zurückgestuft"
                        if folge.action == store.ACTION_DOWNRANK
                        else "aus dem Team genommen"
                    )
                    text += (
                        f"\n\n{WARNING} **Schwelle erreicht** — "
                        f"automatisch {wort}.\n{_summary(folge, settings)}"
                    )

        titel = store.ACTION_LABELS.get(ergebnis.action, "Team-Update")
        await interaction.followup.send(
            view=CV2(f"{titel}: {ziel.display_name}", text), ephemeral=True
        )

    # ── /uprank ──────────────────────────────────────────────────────

    @app_commands.command(
        name="uprank",
        description="Jemanden im Team befördern: neue Rolle drauf, alte runter.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="Wer befördert wird",
        neue_rolle="Die Rolle, die er bekommt",
        alte_rolle="Die Rolle, die entfernt wird (optional)",
        grund="Warum",
        unterschrift2="Weitere Unterschrift (optional)",
        unterschrift3="Weitere Unterschrift (optional)",
        unterschrift4="Weitere Unterschrift (optional)",
        unterschrift5="Weitere Unterschrift (optional)",
    )
    async def uprank(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        neue_rolle: discord.Role,
        alte_rolle: discord.Role | None = None,
        grund: str = "",
        unterschrift2: discord.Member | None = None,
        unterschrift3: discord.Member | None = None,
        unterschrift4: discord.Member | None = None,
        unterschrift5: discord.Member | None = None,
    ):
        await self._rank(
            interaction, store.ACTION_UPRANK, user, neue_rolle, alte_rolle,
            grund,
            _extra_signers(unterschrift2, unterschrift3, unterschrift4,
                           unterschrift5),
        )

    # ── /downrank ────────────────────────────────────────────────────

    @app_commands.command(
        name="downrank",
        description="Jemanden zurückstufen: alte Rolle runter, neue drauf.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="Wer zurückgestuft wird",
        alte_rolle="Die Rolle, die entfernt wird",
        neue_rolle="Die Rolle, die er stattdessen bekommt (optional)",
        grund="Warum",
        unterschrift2="Weitere Unterschrift (optional)",
        unterschrift3="Weitere Unterschrift (optional)",
        unterschrift4="Weitere Unterschrift (optional)",
        unterschrift5="Weitere Unterschrift (optional)",
    )
    async def downrank(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        alte_rolle: discord.Role,
        neue_rolle: discord.Role | None = None,
        grund: str = "",
        unterschrift2: discord.Member | None = None,
        unterschrift3: discord.Member | None = None,
        unterschrift4: discord.Member | None = None,
        unterschrift5: discord.Member | None = None,
    ):
        await self._rank(
            interaction, store.ACTION_DOWNRANK, user, neue_rolle, alte_rolle,
            grund,
            _extra_signers(unterschrift2, unterschrift3, unterschrift4,
                           unterschrift5),
        )

    async def _rank(self, interaction, aktion, ziel, neue, alte, grund, weitere):
        """Der gemeinsame Teil von /uprank und /downrank."""

        vorbereitet = await self._prepare(interaction, grund)
        if vorbereitet is None:
            return
        settings, templates = vorbereitet

        hindernis = self._check_hierarchy(interaction, ziel)
        if hindernis:
            return await interaction.response.send_message(
                f"{CROSS} {hindernis}", ephemeral=True
            )

        if neue is not None and alte is not None and neue.id == alte.id:
            return await interaction.response.send_message(
                f"{CROSS} Alte und neue Rolle sind dieselbe — das ändert nichts.",
                ephemeral=True,
            )
        if neue is None and alte is None:
            return await interaction.response.send_message(
                f"{CROSS} Ohne Rolle gibt es nichts zu tun.", ephemeral=True
            )

        # Vorher pruefen, ob der Bot die Rollen ueberhaupt anfassen
        # kann. Sonst laeuft die Ankuendigung durch, waehrend die
        # Rollen unveraendert bleiben -- und im Kanal steht eine
        # Befoerderung, die nie stattgefunden hat.
        for rolle in (neue, alte):
            if rolle is None:
                continue
            hindernis = service._blocked(interaction.guild, rolle)
            if hindernis:
                return await interaction.response.send_message(
                    f"{CROSS} {hindernis}", ephemeral=True
                )

        await interaction.response.defer(ephemeral=True, thinking=True)

        ergebnis = await service.run_action(
            self.bot, interaction.guild, ziel, aktion,
            old_role=alte, new_role=neue, reason=grund,
            signers=weitere, actor_id=interaction.user.id,
            settings=settings, templates=templates,
        )
        await self._finish(interaction, ergebnis, settings, templates, ziel)

    # ── /teamkick ────────────────────────────────────────────────────

    @app_commands.command(
        name="teamkick",
        description="Jemanden aus dem Team nehmen: alle Teamrollen runter.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="Wer das Team verlässt",
        grund="Warum",
        unterschrift2="Weitere Unterschrift (optional)",
        unterschrift3="Weitere Unterschrift (optional)",
        unterschrift4="Weitere Unterschrift (optional)",
        unterschrift5="Weitere Unterschrift (optional)",
    )
    async def teamkick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        grund: str = "",
        unterschrift2: discord.Member | None = None,
        unterschrift3: discord.Member | None = None,
        unterschrift4: discord.Member | None = None,
        unterschrift5: discord.Member | None = None,
    ):
        vorbereitet = await self._prepare(interaction, grund)
        if vorbereitet is None:
            return
        settings, templates = vorbereitet

        hindernis = self._check_hierarchy(interaction, user)
        if hindernis:
            return await interaction.response.send_message(
                f"{CROSS} {hindernis}", ephemeral=True
            )

        rollen = service.team_roles_of(interaction.guild, user, settings)
        if not rollen:
            return await interaction.response.send_message(
                f"{WARNING} **{user.display_name}** hat keine der eingestellten "
                "Teamrollen.\nWelche das sind, legt das Dashboard fest "
                "(»Rollen, die zum Team gehören«).",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        ergebnis = await service.run_action(
            self.bot, interaction.guild, user, store.ACTION_KICK,
            old_role=rollen[0], reason=grund,
            signers=_extra_signers(unterschrift2, unterschrift3,
                                   unterschrift4, unterschrift5),
            actor_id=interaction.user.id,
            settings=settings, templates=templates,
        )
        await self._finish(interaction, ergebnis, settings, templates, user)

    # ── /teamwarn ────────────────────────────────────────────────────

    @app_commands.command(
        name="teamwarn",
        description="Ein Teammitglied verwarnen — mit Akte und optionaler Folge.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="Wer verwarnt wird",
        grund="Warum",
        unterschrift2="Weitere Unterschrift (optional)",
        unterschrift3="Weitere Unterschrift (optional)",
        unterschrift4="Weitere Unterschrift (optional)",
        unterschrift5="Weitere Unterschrift (optional)",
    )
    async def teamwarn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        grund: str = "",
        unterschrift2: discord.Member | None = None,
        unterschrift3: discord.Member | None = None,
        unterschrift4: discord.Member | None = None,
        unterschrift5: discord.Member | None = None,
    ):
        vorbereitet = await self._prepare(interaction, grund)
        if vorbereitet is None:
            return
        settings, templates = vorbereitet

        hindernis = self._check_hierarchy(interaction, user)
        if hindernis:
            return await interaction.response.send_message(
                f"{CROSS} {hindernis}", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        ergebnis = await service.run_action(
            self.bot, interaction.guild, user, store.ACTION_WARN,
            reason=grund,
            signers=_extra_signers(unterschrift2, unterschrift3,
                                   unterschrift4, unterschrift5),
            actor_id=interaction.user.id,
            settings=settings, templates=templates,
        )
        await self._finish(interaction, ergebnis, settings, templates, user)

    # ── /teamanfang ──────────────────────────────────────────────────

    @app_commands.command(
        name="teamanfang",
        description="Jemanden neu ins Team aufnehmen.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="Wer ins Team kommt",
        rolle="Die Rolle, die er bekommt",
        grund="Warum",
        unterschrift2="Weitere Unterschrift (optional)",
        unterschrift3="Weitere Unterschrift (optional)",
        unterschrift4="Weitere Unterschrift (optional)",
        unterschrift5="Weitere Unterschrift (optional)",
    )
    async def teamanfang(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        rolle: discord.Role,
        grund: str = "",
        unterschrift2: discord.Member | None = None,
        unterschrift3: discord.Member | None = None,
        unterschrift4: discord.Member | None = None,
        unterschrift5: discord.Member | None = None,
    ):
        vorbereitet = await self._prepare(interaction, grund)
        if vorbereitet is None:
            return
        settings, templates = vorbereitet

        hindernis = self._check_hierarchy(interaction, user)
        if hindernis:
            return await interaction.response.send_message(
                f"{CROSS} {hindernis}", ephemeral=True
            )

        hindernis = service._blocked(interaction.guild, rolle)
        if hindernis:
            return await interaction.response.send_message(
                f"{CROSS} {hindernis}", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        ergebnis = await service.run_action(
            self.bot, interaction.guild, user, store.ACTION_JOIN,
            new_role=rolle, reason=grund,
            signers=_extra_signers(unterschrift2, unterschrift3,
                                   unterschrift4, unterschrift5),
            actor_id=interaction.user.id,
            settings=settings, templates=templates,
        )
        await self._finish(interaction, ergebnis, settings, templates, user)

    # ── Fehler ───────────────────────────────────────────────────────

    async def cog_app_command_error(self, interaction, error):
        """
        Ein unerwarteter Fehler darf nicht als ewiges »denkt nach«
        enden. Discord zeigt sonst drei Punkte, bis die Interaktion
        verfaellt, und niemand erfaehrt, was los war.
        """
        logger.exception(f"[team_update] {error}")
        text = f"{CROSS} Da ist etwas schiefgegangen: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            pass
