"""Behavioural tests for inherited ticket rules and real Discord components."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import aiosqlite
from api import ticket_panels
from utils import ticket_settings as settings


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(':memory:')
        await ticket_panels.ensure_schema(self.db)
        self.panel=await ticket_panels.create_panel(self.db,42,'Support')

    async def asyncTearDown(self):await self.db.close()

    async def test_settings_roundtrip_and_category_inheritance(self):
        await ticket_panels.update_panel(self.db,42,self.panel,{'channel_id':'1557183988672766043','settings':{'auto_close':True,'auto_close_seconds':7200,'priority':'high'}})
        cat=await ticket_panels.upsert_category(self.db,42,self.panel,{'name':'Appeal','staff_roles':['1557183988672766043'],'settings':{'auto_close':False,'prefix':'appeal','opening_questions':[{'label':'Reason','type':'paragraph','required':True,'max_length':3000}]}})
        panels=await ticket_panels.list_panels(self.db,42)
        self.assertEqual(panels[0]['channel_id'],'1557183988672766043')
        self.assertEqual(panels[0]['categories'][0]['staff_roles'],['1557183988672766043'])
        prefs=settings.resolve(panels[0]['settings'],panels[0]['categories'][0]['settings'])
        self.assertFalse(prefs['auto_close']);self.assertEqual(prefs['auto_close_seconds'],7200)
        self.assertEqual(prefs['opening_questions'][0]['max_length'],3000)
        await ticket_panels.upsert_category(self.db,42,self.panel,{'category_id':cat,'name':'Appeal','settings':{}})
        panels=await ticket_panels.list_panels(self.db,42)
        self.assertTrue(settings.resolve(panels[0]['settings'],panels[0]['categories'][0]['settings'])['auto_close'])

    async def test_reject_wrong_guild_and_wrong_panel_category(self):
        cat=await ticket_panels.upsert_category(self.db,42,self.panel,{'name':'A'})
        other=await ticket_panels.create_panel(self.db,42,'B')
        for guild,panel in [(99,self.panel),(42,other)]:
            with self.assertRaises(ValueError):
                await ticket_panels.upsert_category(self.db,guild,panel,{'category_id':cat,'name':'Stolen'})
        self.assertEqual((await ticket_panels.list_panels(self.db,42))[0]['categories'][0]['name'],'A')

    async def test_invalid_settings_do_not_change_existing_panel(self):
        for prefs in [{'auto_close_seconds':0},{'opening_hours':[{'day':0,'start':'17:00','end':'09:00'}]}, {'priority':'invalid'}, {'rating_questions':[{'label':'A'}]*5}, {'opening_questions':[{'label':'','type':'short'}]}, {'opening_questions':[{'label':'A','type':'select','options':[]}]}]:
            with self.assertRaises(ValueError):
                await ticket_panels.update_panel(self.db,42,self.panel,{'name':'Broken','settings':prefs})
        self.assertEqual((await ticket_panels.list_panels(self.db,42))[0]['name'],'Support')

    async def test_category_counts_use_open_rows_only(self):
        cat=await ticket_panels.upsert_category(self.db,42,self.panel,{'name':'A'})
        await self.db.execute('INSERT INTO open_tickets(channel_id,guild_id,category_db_id) VALUES(1,42,?)',(cat,))
        await self.db.execute("INSERT INTO open_tickets(channel_id,guild_id,category_db_id,closed_at) VALUES(2,42,?,'closed')",(cat,))
        self.assertEqual((await ticket_panels.list_panels(self.db,42))[0]['categories'][0]['open_tickets'],1)

    async def test_all_supported_global_questions_survive_storage(self):
        fields=[{'label':'Choice','type':'select','options':['Yes','No']},{'label':'Choose topics','type':'checkbox','options':['Premium','',' Account ','']},{'label':'File','type':'file'},{'label':'Detail','type':'paragraph','max_length':3900,'category_ids':[4]}]
        await ticket_panels.update_panel(self.db,42,self.panel,{'ticket_questions':fields})
        result=(await ticket_panels.list_panels(self.db,42))[0]['ticket_questions']
        self.assertEqual([x['type'] for x in result],['select','checkbox','file','paragraph'])
        self.assertEqual(result[1]['label'],'Choose topics');self.assertEqual(result[1]['options'],['Premium','Account'])
        self.assertEqual(result[-1]['max_length'],3900);self.assertEqual(result[-1]['category_ids'],[4])


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from cogs.commands.ticket import TicketDatabase,TicketCog
        self.temp=tempfile.TemporaryDirectory()
        self.db=TicketDatabase(os.path.join(self.temp.name,'ticket.db'))
        self.db.execute("INSERT INTO guild_configs(guild_id,staff_roles) VALUES(42,'12')")
        self.db.execute("INSERT INTO ticket_categories(category_id,guild_id,name,notified_roles) VALUES(1,42,'Support','13')")
        self.db.execute("INSERT INTO open_tickets VALUES(123,1,42,99,1,'2026-10-08T12:00:00',NULL,NULL,0,0,NULL)")
        self.db.execute("INSERT INTO ticket_workflow(channel_id,last_activity,priority) VALUES(123,0,'normal')")
        self.cog=TicketCog.__new__(TicketCog);self.cog.db=self.db;self.cog._action_locks={}
        self.guild=SimpleNamespace(id=42,get_channel=lambda _:self.channel,get_role=lambda _:None,get_member=lambda _:None)
        self.channel=SimpleNamespace(id=123,guild=self.guild,send=AsyncMock(),set_permissions=AsyncMock())
        self.cog.bot=SimpleNamespace(get_guild=lambda _:self.guild)

    async def asyncTearDown(self):self.db.conn.close();self.temp.cleanup()

    async def test_opening_on_behalf_requires_enabled_setting_and_staff(self):
        author=SimpleNamespace(id=77,guild=self.guild,roles=[],guild_permissions=SimpleNamespace(administrator=False))
        interaction=SimpleNamespace(guild=self.guild,user=author,response=SimpleNamespace(is_done=lambda:False,send_message=AsyncMock()))
        await self.cog._create_ticket_flow(interaction,1,creator_id=55)
        self.assertIn('does not allow',str(interaction.response.send_message.call_args.kwargs['view'].to_components()))
        self.db.execute("INSERT INTO ticket_preferences VALUES(42,'category',1,?)",(json.dumps({'allow_on_behalf':True}),))
        await self.cog._create_ticket_flow(interaction,1,creator_id=55)
        self.assertIn('does not allow',str(interaction.response.send_message.call_args.kwargs['view'].to_components()))
        author.roles=[SimpleNamespace(id=12)]
        await self.cog._create_ticket_flow(interaction,1,creator_id=55)
        self.assertIn('no longer on the server',str(interaction.response.send_message.call_args.kwargs['view'].to_components()))
        self.channel.send.assert_not_awaited()

    async def test_forms_build_all_discord_field_types_and_limit_five(self):
        from cogs.commands.ticket import TicketQuestionsModal
        fields=[{'label':'Text','type':'short'},{'label':'Long','type':'paragraph','max_length':3900},{'label':'Choice','type':'radio','options':['A','B']},{'label':'Confirm','type':'checkbox'},{'label':'Upload','type':'file'},{'label':'ignored'}]
        modal=TicketQuestionsModal(self.cog,1,{'questions':fields})
        self.assertEqual(len(modal.children),5)
        self.assertEqual(modal.children[1].component.max_length,3900)
        self.assertEqual(modal.children[2].component.options[0].label,'A')
        self.assertEqual(type(modal.children[3].component).__name__,'Checkbox')

    async def test_creator_close_permission_and_staff_fallback(self):
        from cogs.commands.ticket import TicketActionsView
        view=TicketActionsView(self.cog,123,1)
        member=SimpleNamespace(id=99,guild=self.guild,roles=[],guild_permissions=SimpleNamespace(administrator=False))
        inter=SimpleNamespace(guild=self.guild,user=member,data={'custom_id':'t_close'},response=SimpleNamespace(send_message=AsyncMock()))
        self.assertFalse(await view.interaction_check(inter))
        self.db.execute("INSERT INTO ticket_preferences VALUES(42,'category',1,?)",(json.dumps({'staff_only_close':False}),))
        self.assertTrue(await view.interaction_check(inter))
        member.id=77;member.roles=[SimpleNamespace(id=12)]
        self.assertTrue(await view.interaction_check(inter))

    async def test_v2_action_callback_retains_staff_permissions(self):
        from cogs.commands.ticket import TicketActionsView
        from utils.panels import from_embed
        import discord
        view=TicketActionsView(self.cog,123,1)
        panel=from_embed(discord.Embed(title='Ticket'),view)
        user=SimpleNamespace(id=55,guild=self.guild,roles=[],guild_permissions=SimpleNamespace(administrator=False))
        interaction=SimpleNamespace(guild=self.guild,user=user,data={'custom_id':'t_close'},response=SimpleNamespace(send_message=AsyncMock()))
        with patch.object(view,'_close',new_callable=AsyncMock) as close:
            await view.b_close.callback(interaction)
            close.assert_not_awaited()
            interaction.response.send_message.assert_awaited_once()
        self.assertTrue(getattr(view.b_close.callback,'_university_ticket_action',False))

    async def test_registered_action_is_not_dispatched_twice(self):
        from cogs.commands.ticket import TicketActionsView
        import discord
        view=TicketActionsView(self.cog,123,1)
        store=SimpleNamespace(_views={444:{(2,'t_close'):view.b_close}})
        self.cog.bot._connection=SimpleNamespace(_view_store=store)
        interaction=SimpleNamespace(type=discord.InteractionType.component,guild_id=42,message=SimpleNamespace(id=444),data={'custom_id':'t_close','component_type':2},response=SimpleNamespace(is_done=lambda:False))
        with patch.object(self.cog,'_dispatch_ticket_button',new_callable=AsyncMock) as dispatch:
            await self.cog.on_interaction(interaction)
            dispatch.assert_not_awaited()
            store._views.clear()
            await self.cog.on_interaction(interaction)
            dispatch.assert_awaited_once_with(interaction,'t_close')

    async def test_registered_dropdown_uses_one_creation_callback(self):
        from cogs.commands.ticket import TicketPanelSelect
        import discord
        view=TicketPanelSelect(self.cog);view.children[0]._values=['1']
        self.cog.bot._connection=SimpleNamespace(_view_store=SimpleNamespace(_views={444:{(3,'create_ticket_select'):view.children[0]}}))
        interaction=SimpleNamespace(type=discord.InteractionType.component,guild_id=42,message=SimpleNamespace(id=444),data={'custom_id':'create_ticket_select','component_type':3,'values':['1']},response=SimpleNamespace(is_done=lambda:False))
        with patch.object(self.cog,'create_ticket_flow',new_callable=AsyncMock) as create:
            await self.cog.on_interaction(interaction)
            create.assert_not_awaited()
            await view.children[0].callback(interaction)
            create.assert_awaited_once_with(interaction,1)

    async def test_auto_alert_is_persisted_and_not_sent_twice(self):
        from cogs.commands.ticket_workflow import tick
        self.db.execute("INSERT INTO ticket_preferences VALUES(42,'category',1,?)",(json.dumps({'auto_alert':True,'auto_alert_seconds':60}),))
        await tick(self.cog);calls=self.channel.send.await_count
        self.assertEqual(calls,2)
        await tick(self.cog);self.assertEqual(self.channel.send.await_count,calls)
        self.assertIsNotNone(self.db.fetchone('SELECT alerted FROM ticket_workflow WHERE channel_id=123')['alerted'])

    async def test_activity_resets_reminders_and_preserves_priority(self):
        from cogs.commands.ticket_workflow import activity
        self.db.execute("UPDATE ticket_workflow SET alerted=1,team_alerted=1,priority='urgent'")
        author=SimpleNamespace(id=99,bot=False)
        await activity(self.cog,SimpleNamespace(guild=self.guild,channel=self.channel,author=author))
        row=self.db.fetchone('SELECT * FROM ticket_workflow WHERE channel_id=123')
        self.assertIsNone(row['alerted']);self.assertEqual(row['priority'],'urgent')
        self.assertGreater(row['last_activity'],0)

    async def test_duplicate_claims_have_one_winner(self):
        from cogs.commands.ticket_workflow import claim
        user=SimpleNamespace(id=77,mention='<@77>')
        results=await asyncio.gather(claim(self.cog,self.channel,1,user),claim(self.cog,self.channel,1,user))
        self.assertEqual(results.count(True),1)
        self.assertEqual(self.channel.send.await_count,1)

    async def test_inactivity_dispatches_the_real_close_action(self):
        from cogs.commands.ticket_workflow import tick
        from cogs.commands.ticket import TicketActionsView
        self.guild.me=SimpleNamespace(id=1,mention='<@1>')
        self.db.execute("INSERT INTO ticket_preferences VALUES(42,'category',1,?)",(json.dumps({'auto_close':True,'auto_close_seconds':60}),))
        with patch.object(TicketActionsView,'_close',new_callable=AsyncMock) as close:
            await tick(self.cog)
            close.assert_awaited_once()

    async def test_feedback_survives_deleted_channel_and_is_only_saved_once(self):
        from cogs.commands.ticket_workflow import RatingModal
        ticket=dict(self.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=123'))
        ticket['closed_at']='2026-10-08T13:00:00';ticket['_settings']=settings.resolve({'rating_enabled':True})
        self.db.execute('DELETE FROM open_tickets WHERE channel_id=123')
        self.db.execute('DELETE FROM ticket_categories WHERE category_id=1')
        interaction=SimpleNamespace(user=SimpleNamespace(id=99),response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
        modal=RatingModal(self.cog,ticket);modal.score._values=['5']
        await modal.on_submit(interaction)
        first=interaction.followup.send.call_args.kwargs
        self.assertIn('Your feedback has been successfully submitted.',str(first['view'].to_components()))
        self.assertTrue(first['ephemeral'])
        await modal.on_submit(interaction)
        self.assertIn('Already rated',str(interaction.followup.send.call_args.kwargs['view'].to_components()))
        self.assertEqual(self.db.fetchone('SELECT COUNT(*) AS n FROM ticket_ratings')['n'],1)
        self.assertEqual(self.db.fetchone('SELECT score FROM ticket_ratings')['score'],5)

    async def test_feedback_logs_quote_answers_and_never_ping(self):
        from cogs.commands.ticket_workflow import RatingModal
        from utils.dm_i18n import translate
        ticket=dict(self.db.fetchone('SELECT * FROM open_tickets WHERE channel_id=123'))
        ticket['closed_at']='2026-10-08T13:00:00';ticket['closed_by_id']=77
        ticket['_settings']=settings.resolve({'rating_enabled':True,'rating_channel_id':'456','rating_public_channel_id':'789','rating_values':['creator','case'],'rating_questions':[{'label':'Comment','type':'paragraph','required':False,'public':True}]})
        private=SimpleNamespace(send=AsyncMock());public=SimpleNamespace(send=AsyncMock())
        self.guild.get_channel=lambda cid:private if cid==456 else public
        modal=RatingModal(self.cog,ticket);modal.score._values=['4'];modal.inputs[0][1]._value='Great support!\n<@&12> <@99> @everyone'
        inter=SimpleNamespace(user=SimpleNamespace(id=99),response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
        await modal.on_submit(inter)
        for channel in (private,public):
            self.assertEqual(channel.send.await_count,2)
            for call in channel.send.call_args_list:self.assertEqual(call.kwargs['allowed_mentions'].to_dict()['parse'],[])
            payload=str(channel.send.call_args_list[0].kwargs['view'].to_components())
            self.assertIn('> **Creator:**',payload);self.assertIn('4 / 5',payload)
            self.assertIn('> Great support!',str(channel.send.call_args_list[1].kwargs['view'].to_components()))
        self.assertNotIn('Supporter:',str(public.send.call_args_list[0].kwargs['view'].to_components()))
        self.assertEqual(translate('Your feedback has been successfully submitted.','de'),'Dein Feedback wurde erfolgreich eingereicht.')

    async def test_ticket_controls_and_existing_cards_remove_only_lock_buttons(self):
        import discord
        from discord.components import _component_factory
        from cogs.commands.ticket import TicketActionsView
        from cogs.commands.ticket_workflow import remove_lock_controls
        from utils.panels import Panel
        controls=TicketActionsView(self.cog,123,1)
        self.assertNotIn('t_lock',{item.custom_id for item in controls.children})
        self.assertNotIn('t_unlock',{item.custom_id for item in controls.children})
        for v2 in (False,True):
            buttons=[discord.ui.Button(label=name,custom_id=cid) for name,cid in [('Lock','t_lock'),('Claim','t_claim'),('Unlock','t_unlock')]]
            if v2: old=Panel('Original welcome','Keep this text',buttons=buttons)
            else:
                old=discord.ui.View()
                for item in buttons:old.add_item(item)
            message=SimpleNamespace(components=[_component_factory(c) for c in old.to_components()],flags=discord.MessageFlags(components_v2=v2),edit=AsyncMock())
            self.assertTrue(await remove_lock_controls(message))
            payload=str(message.edit.call_args.kwargs['view'].to_components())
            self.assertNotIn('t_lock',payload);self.assertNotIn('t_unlock',payload);self.assertIn('t_claim',payload)
            if v2:self.assertIn('Original welcome',payload);self.assertIn('Keep this text',payload)

    async def test_ticket_action_logs_keep_mentions_visible_without_notifications(self):
        from cogs.commands.ticket import log_ticket_action
        user=SimpleNamespace(mention='<@99>')
        with patch('cogs.commands.ticket.get_or_create_log_channel',AsyncMock(return_value=self.channel)):
            await log_ticket_action(self.db,self.guild,user,'Created','<@&12> <@99> @everyone')
        self.assertEqual(self.channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'],[])

    async def test_second_rating_button_click_confirms_existing_feedback_without_modal(self):
        import discord
        self.db.execute("UPDATE open_tickets SET closed_at='2026-10-08T13:00:00' WHERE channel_id=123")
        self.db.execute('INSERT INTO ticket_ratings VALUES(123,42,99,5,?,0)',('Original feedback',))
        inter=SimpleNamespace(type=discord.InteractionType.component,guild_id=42,user=SimpleNamespace(id=99),data={'custom_id':'ticket_rating_123'},response=SimpleNamespace(is_done=lambda:False,send_message=AsyncMock(),send_modal=AsyncMock()))
        await self.cog.on_interaction(inter)
        inter.response.send_modal.assert_not_awaited()
        self.assertIn('Already rated',str(inter.response.send_message.call_args.kwargs['view'].to_components()))
        self.assertEqual(self.db.fetchone('SELECT comment FROM ticket_ratings WHERE channel_id=123')[0],'Original feedback')

    async def test_priority_exemption_blocks_automatic_close(self):
        from cogs.commands.ticket_workflow import tick
        from cogs.commands.ticket import TicketActionsView
        self.db.execute("UPDATE ticket_workflow SET priority='urgent'")
        self.db.execute("INSERT INTO ticket_preferences VALUES(42,'category',1,?)",(json.dumps({'auto_close':True,'auto_close_seconds':60,'no_auto_close_priority':'high'}),))
        with patch.object(TicketActionsView,'_close',new_callable=AsyncMock) as close:
            await tick(self.cog)
            close.assert_not_awaited()


class HoursTests(unittest.TestCase):
    def test_overlap_and_boundaries(self):
        with self.assertRaises(ValueError):settings.validate({'opening_hours':[{'day':0,'start':'09:00','end':'12:00'},{'day':0,'start':'11:00','end':'13:00'}]})
        prefs=settings.resolve(settings.validate({'opening_hours':[{'day':0,'start':'09:00','end':'12:00'}]}))
        self.assertTrue(settings.is_open(prefs,datetime(2026,10,5,9,0)))
        self.assertFalse(settings.is_open(prefs,datetime(2026,10,5,12,0)))

if __name__=='__main__':unittest.main()
