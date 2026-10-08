"""Departure editor regression tests: persistence, exact IDs and V2 output."""
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import discord
from utils import greet_extras as ge


def member():
    guild = SimpleNamespace(name="Our server", id=42, member_count=12, icon=None, members=[])
    return SimpleNamespace(guild=guild, name="Alex", display_name="Alex nick", id=123,
                           mention="<@123>", display_avatar=SimpleNamespace(url="https://example.org/avatar.png"),
                           joined_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc))


class LeaveEditorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "greet.db")
        self.override = patch.object(ge, "GREET_DB", self.path)
        self.override.start()

    async def asyncTearDown(self):
        self.override.stop()
        self.temp.cleanup()

    async def test_migrate_old_table_without_losing_message_or_channel(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE greet_extras (guild_id INTEGER PRIMARY KEY, welcome_image_enabled INTEGER, welcome_image_url TEXT, leave_enabled INTEGER, leave_channel_id INTEGER, leave_message TEXT, leave_image_enabled INTEGER, leave_image_url TEXT)")
            db.execute("INSERT INTO greet_extras VALUES (42, 0, '', 1, 1557183988672766043, 'Bye {user.display}', 0, '')")
        settings = await ge.get(42)
        self.assertEqual(settings["leave_channel_id"], 1557183988672766043)
        self.assertEqual(settings["leave_message"], 'Bye {user.display}')
        self.assertEqual(settings["leave_type"], 'simple')
        self.assertFalse(settings["welcome_image_enabled"])
        await ge.get(42)  # Migration must be safe to repeat.

    async def test_roundtrip_all_embed_settings_and_keep_other_module_fields(self):
        embed = dict(title='Bye {user_nick}', description='x' * 3000, message='{user}', color='#f43f5e',
                     author_name='{user_name}', author_icon='{user_avatar}', footer_text='{count} members',
                     footer_icon='{server_icon}', image='https://example.org/image.png', thumbnail='{user_avatar}')
        await ge.save(42, {'welcome_image_enabled': False, 'leave_enabled': True})
        await ge.save(42, {'leave_channel_id': '1557183988672766043', 'leave_type': 'embed',
                          'leave_embed_data': embed, 'leave_auto_delete_duration': 60})
        settings = await ge.get(42)
        self.assertEqual(settings['leave_embed_data'], embed)
        self.assertFalse(settings['welcome_image_enabled'])
        self.assertTrue(settings['leave_enabled'])
        wire = json.loads(json.dumps(ge.api_settings(settings)))
        self.assertEqual(wire['leave_channel_id'], '1557183988672766043')
        payload = ge.message_payload(settings, member())
        self.assertEqual(payload['delete_after'], 60)
        raw = json.dumps(payload['view'].to_components())
        self.assertIn('Alex nick', raw)
        self.assertIn('x' * 3000, raw)  # Full description, not the old 2000-char text limit.
        self.assertIn('12 members', raw)
        self.assertIn('https://example.org/image.png', raw)

    async def test_banner_and_configured_embed_image_are_both_visible(self):
        settings = ge.validate_update(ge.DEFAULTS, {'leave_type': 'embed', 'leave_embed_data': {
            'title': 'Bye', 'image': 'https://example.org/image.png'}})
        banner = discord.File(io.BytesIO(b'image'), filename='departure.png')
        try:
            payload = ge.message_payload(settings, member(), banner)
            raw = json.dumps(payload['view'].to_components())
            self.assertIn('attachment://departure.png', raw)
            self.assertIn('https://example.org/image.png', raw)
            self.assertIs(payload['file'], banner)
        finally:
            banner.close()

    async def test_invalid_draft_does_not_overwrite_saved_settings(self):
        await ge.save(42, {'leave_message': 'Keep me'})
        for payload in [{'leave_type': 'wrong'}, {'leave_embed_data': []},
                        {'leave_embed_data': {'description': 'x' * 4097}},
                        {'leave_auto_delete_duration': 1.5}, {'leave_auto_delete_duration': -1},
                        {'leave_image_url': 'not-an-image'}]:
            with self.assertRaises(ValueError):
                await ge.save(42, payload)
        self.assertEqual((await ge.get(42))['leave_message'], 'Keep me')

    async def test_preview_uses_the_real_payload_without_saving_the_draft(self):
        from api.routes.actions import test_leave
        original = await ge.save(42, {'leave_message': 'Stored message'})
        person = member()
        channel = SimpleNamespace(name='departures', send=AsyncMock(return_value=SimpleNamespace(jump_url='https://discord.com/test')),
                                  permissions_for=lambda _: SimpleNamespace(view_channel=True, send_messages=True, embed_links=True))
        person.guild.me = person
        person.guild.get_member = lambda _: person
        person.guild.get_channel = lambda _: channel
        greeter = SimpleNamespace(build_banner=AsyncMock(return_value=None))
        bot = SimpleNamespace(get_guild=lambda _: person.guild, get_cog=lambda _: greeter)
        draft = {'leave_channel_id': '1557183988672766043', 'leave_type': 'embed',
                 'leave_embed_data': {'title': 'Bye {user_name}', 'description': 'Draft'}, 'leave_image_enabled': False}
        result = await test_leave(42, draft, bot)
        self.assertEqual(result['status'], 'success')
        sent = channel.send.call_args.kwargs
        self.assertIn('Bye Alex', json.dumps(sent['view'].to_components()))
        self.assertEqual(await ge.get(42), original)

    async def test_legacy_and_new_placeholders_work_in_the_same_message(self):
        settings = ge.validate_update(ge.DEFAULTS, {'leave_message': '{user.display} / {user_name} / {server} / {server_name} / {count}'})
        raw = json.dumps(ge.message_payload(settings, member())['view'].to_components())
        self.assertIn('Alex nick / Alex / Our server / Our server / 12', raw)


if __name__ == '__main__':
    unittest.main()
