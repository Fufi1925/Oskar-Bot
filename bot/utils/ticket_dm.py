"""
Die DM selbst -- Aufbau und Zustellung.

Getrennt von ``ticket_notify.py``, weil das dort die Regeln sind und
hier das Aussehen. Die Regeln lassen sich ohne Discord pruefen, das
Aussehen nicht.

Gebaut als Components V2: ein Container mit farbigem Balken, Text
darin, und der Knopf **ausserhalb** des Containers. Genau so sieht die
Vorlage aus -- der Knopf sitzt unter der Karte, nicht in ihr.

Ein Fallstrick, der hier zweimal zuschlagen kann: mit dem V2-Flag gibt
es kein ``content``-Feld mehr. Wer eine LayoutView zusammen mit
``content=`` verschickt, bekommt von Discord 50035 zurueck. Im
Ticket-Cog ist genau das schon einmal passiert, deshalb steht hier
nirgends ein ``content=``.
"""

from __future__ import annotations

import logging

import discord
from discord.ui import ActionRow, Button, Container, LayoutView, TextDisplay

from utils.emoji import TICKET

logger = logging.getLogger(__name__)

# Der Farbstreifen links. Lila fuer "jemand hat geantwortet", Bernstein
# fuer "hier wartet jemand" -- zwei Meldungen, die man im DM-Verlauf
# auseinanderhalten koennen sollte, ohne zu lesen.
FARBE_ANTWORT = discord.Color.from_rgb(155, 89, 232)
FARBE_WARTET = discord.Color.from_rgb(232, 165, 71)


class TicketDMView(LayoutView):
    """
    Die Karte plus Knopf.

    Der Knopf ist ein Link auf den Kanal. Ein Interaktionsknopf waere
    hier falsch: die DM ueberlebt jeden Neustart des Bots, ein
    ``custom_id`` haette danach niemanden mehr, der zuhoert. Ein Link
    funktioniert immer.

    Der Knopf sitzt **im** Container, nicht daneben. In der Vorlage
    sieht es aus, als stuende er darunter -- das taeuscht: eine
    ActionRow direkt in der LayoutView rendert ausserhalb der Karte und
    damit wieder wie vor der V2-Umstellung. ``test_v2_buttons.py``
    prueft das repoweit, und zu Recht: beim J2C-Panel sassen zwoelf
    Knoepfe monatelang ausserhalb der Box, ohne dass es auffiel.
    """

    def __init__(self, *, titel: str, text: str, fusszeile: str,
                 kanal_url: str, knopf_text: str, farbe: discord.Color):
        super().__init__(timeout=None)

        container = Container(accent_color=farbe)
        container.add_item(TextDisplay(f"### {titel}"))
        container.add_item(TextDisplay(text))
        container.add_item(TextDisplay(f"-# {fusszeile}"))
        container.add_item(
            ActionRow(
                Button(
                    label=knopf_text,
                    url=kanal_url,
                    style=discord.ButtonStyle.link,
                    # Das eigene Emoji des Bots, nicht das der Plattform:
                    # ein Unicode-Zeichen wird auf Windows, Android und
                    # iOS unterschiedlich gezeichnet.
                    emoji=TICKET,
                )
            )
        )
        self.add_item(container)


def build_user_dm(*, guild_name: str, kanal_url: str, ticket_nr: int | None = None
                  ) -> TicketDMView:
    """„Jemand vom Team hat dir geantwortet."""
    nummer = f" #{ticket_nr:04d}" if ticket_nr else ""
    return TicketDMView(
        titel="Neue Antwort in deinem Ticket",
        text=(
            f"Ein Teammitglied hat auf dein Ticket{nummer} auf "
            f"**{guild_name}** geantwortet."
        ),
        fusszeile=f"University Bot • {guild_name}",
        kanal_url=kanal_url,
        knopf_text="Zum Ticket",
        farbe=FARBE_ANTWORT,
    )


def build_staff_dm(*, guild_name: str, kanal_url: str, user_name: str,
                   ticket_nr: int | None = None) -> TicketDMView:
    """„Da wartet jemand auf dich."""
    nummer = f" #{ticket_nr:04d}" if ticket_nr else ""
    return TicketDMView(
        titel="Jemand wartet auf eine Antwort",
        text=(
            f"**{user_name}** hat im Ticket{nummer} auf **{guild_name}** "
            f"geschrieben und noch keine Antwort bekommen."
        ),
        fusszeile=f"University Bot • {guild_name}",
        kanal_url=kanal_url,
        knopf_text="Zum Ticket",
        farbe=FARBE_WARTET,
    )


async def send_dm(user: discord.User | discord.Member, view: LayoutView) -> bool:
    """
    Zustellen. ``True``, wenn es geklappt hat.

    Eine geschlossene DM ist kein Fehler, sondern eine Einstellung des
    Empfaengers -- deshalb wird ``Forbidden`` nur vermerkt und nicht
    weitergereicht. Wichtig ist, dass der Aufrufer erfaehrt, ob etwas
    ankam: nur dann darf die Sperrzeit anlaufen.
    """
    try:
        # Kein content= -- mit dem V2-Flag lehnt Discord das mit 50035 ab.
        await user.send(view=view)
        return True
    except discord.Forbidden:
        logger.info(f"Ticket-DM an {user.id} nicht moeglich (DMs zu).")
        return False
    except discord.HTTPException as exc:
        logger.warning(f"Ticket-DM an {user.id} fehlgeschlagen: {exc}")
        return False
