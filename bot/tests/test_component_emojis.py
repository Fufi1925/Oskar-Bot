"""Discord labels must serialize custom emojis separately from plain text."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import aiosqlite
import discord
from api import ticket_panels
from utils.component_emojis import label_emoji, normalize_controls, category_text
from utils.panels import Panel
from utils.cv2 import build_container

STATIC = '<:handshake:1556018353233993858>'
ANIMATED = '<a:gearsloading:1555853541975924776>'


class ComponentTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_and_animated_options_are_real_emoji_fields(self):
        options = [discord.SelectOption(label=f'{icon} {name}', value=str(i))
                   for i, (icon, name) in enumerate([(STATIC, 'Entbannung'), (ANIMATED, 'Allgemeine Fragen')])]
        select = discord.ui.Select(custom_id='create_ticket_select', options=options)
        callback = select.callback
        panel = Panel('Tickets', buttons=[select])
        payload = select.to_component_dict()
        self.assertEqual([o['label'] for o in payload['options']], ['Entbannung', 'Allgemeine Fragen'])
        self.assertEqual(str(payload['options'][0]['emoji']['id']), '1556018353233993858')
        self.assertTrue(payload['options'][1]['emoji']['animated'])
        self.assertEqual(payload['options'][1]['value'], '1')
        self.assertEqual(select.callback, callback)
        self.assertIn('create_ticket_select', str(panel.to_components()))

    async def test_buttons_keep_explicit_icons_and_icon_only_controls(self):
        button = discord.ui.Button(label=f'{STATIC} Support', emoji=ANIMATED, custom_id='support')
        icon_only = discord.ui.Button(emoji=STATIC, custom_id='icon')
        original = icon_only.label
        build_container(discord.ui.ActionRow(button, icon_only))
        self.assertEqual(button.label, 'Support')
        self.assertEqual(button.emoji.id, 1555853541975924776)
        self.assertEqual(icon_only.label, original)
        self.assertEqual(button.custom_id, 'support')

    async def test_legacy_category_names_are_fixed_without_destroying_database(self):
        async with aiosqlite.connect(':memory:') as db:
            panel = await ticket_panels.create_panel(db, 42, 'Support')
            await db.execute('INSERT INTO ticket_categories(guild_id,panel_id,name,emoji) VALUES(42,?,?,?)', (panel, f'{ANIMATED} Allgemeine Fragen', ''))
            result = (await ticket_panels.list_panels(db, 42))[0]['categories'][0]
            self.assertEqual(result['name'], 'Allgemeine Fragen')
            self.assertEqual(result['emoji'], ANIMATED)
            async with db.execute('SELECT name FROM ticket_categories') as cursor:
                self.assertEqual((await cursor.fetchone())[0], f'{ANIMATED} Allgemeine Fragen')
            cat = await ticket_panels.upsert_category(db, 42, panel, {'name': f'{STATIC} Entbannung', 'emoji': ''})
            async with db.execute('SELECT name,emoji FROM ticket_categories WHERE category_id=?', (cat,)) as cursor:
                self.assertEqual(await cursor.fetchone(), ('Entbannung', STATIC))

    async def test_names_are_trimmed_after_emoji_extraction_and_text_keeps_markup(self):
        name, emoji = label_emoji(f'{ANIMATED} ' + 'A'*100, limit=80)
        self.assertEqual(name, 'A'*80)
        self.assertEqual(emoji, ANIMATED)
        self.assertEqual(category_text(f'{STATIC} Support'), f'{STATIC} **Support**')
        self.assertEqual(label_emoji('🎫 Support'), ('🎫 Support', None))
        self.assertEqual(label_emoji('<emoji:1556018353233993858> Support'), ('Support', '<:emoji:1556018353233993858>'))


if __name__ == '__main__':
    unittest.main()
