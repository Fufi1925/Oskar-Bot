"""Components V2 notices after an administrator approves a purchase request."""
import asyncio
import logging

import discord
from utils import dm_preferences
from utils.emoji import PREMIUM, TICK, UPTIME, STAR, NEXT_ALT1
from utils.links import dashboard_url, support_url
from utils.panels import Panel

logger = logging.getLogger(__name__)


def approval_view(account, language='en'):
    def t(en, de): return de if language == 'de' else en
    expires = int(account['expires_at'])
    slots = int(account['max_slots'])
    sections = [
        t(f'{TICK} Your Premium purchase request has been approved. Premium is now active on your account.',
          f'{TICK} Deine Premium-Kaufanfrage wurde genehmigt. Premium ist jetzt für dein Konto aktiv.'),
        t(f'{UPTIME} **Active until**\n> <t:{expires}:F>\n\n{STAR} **Server slots**\n> {slots}',
          f'{UPTIME} **Aktiv bis**\n> <t:{expires}:F>\n\n{STAR} **Serverplätze**\n> {slots}'),
        t('**Your next step**\n> Open your Premium dashboard and assign a slot to a server.\n> Ticket AI is available on your Premium servers; add knowledge and enable it in the ticket settings.',
          '**Dein nächster Schritt**\n> Öffne deine Premiumverwaltung und weise einem Server einen Platz zu.\n> Auf deinen Premium-Servern ist die Ticket-KI verfügbar; hinterlege Wissen und aktiviere sie in den Ticket-Einstellungen.'),
    ]
    buttons = []
    base = dashboard_url()
    if base:
        buttons.append(discord.ui.Button(label=t('Manage Premium','Premium verwalten'),url=f'{base}/dashboard/premium',emoji=NEXT_ALT1))
    support = support_url()
    if support:
        buttons.append(discord.ui.Button(label=t('Contact support','Support kontaktieren'),url=support,emoji=PREMIUM))
    return Panel(t(f'{PREMIUM} Premium approved',f'{PREMIUM} Premium genehmigt'), *sections, tone='success', buttons=buttons)


async def notify_approved(bot, account):
    """A blocked DM must never undo a successful Premium grant."""
    try:
        user_id = int(account['user_id'])
        async with asyncio.timeout(15):
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            await user.send(view=approval_view(account,dm_preferences.language(user_id)),allowed_mentions=discord.AllowedMentions.none())
        return True
    except Exception as exc:
        logger.warning('Premium approval DM could not be delivered: %s',type(exc).__name__)
        return False
