"""Actual DM component payloads, language persistence and transport wrappers."""
import asyncio,io,os,sys,tempfile,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch,AsyncMock
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import discord
from utils import dm_delivery as dm,dm_preferences as prefs
from utils.dm_i18n import translate,preserve,preserve_values
from utils.panels import Panel

def text(view):return '\n'.join(x.content for x in view.walk_children() if isinstance(x,discord.ui.TextDisplay))
def channel(uid=12):
    obj=object.__new__(discord.DMChannel);obj.recipients=[NS(id=uid)];return obj

class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.calls=[]
        self.path=patch.object(prefs,'DB_PATH',os.path.join(self.temp.name,'dm.db'));self.path.start()
        owner=self
        async def send(sender,content=None,**kwargs):
            owner.calls.append((content,kwargs,text(kwargs['view']) if kwargs.get('view') else ''))
            await asyncio.sleep(0);return NS(id=len(owner.calls))
        async def response(sender,*args,**kwargs):return await send(sender,args[0] if args else kwargs.pop('content',None),**kwargs)
        self.patches=[patch.object(discord.abc.Messageable,'send',send),patch.object(discord.Message,'edit',response),patch.object(discord.InteractionResponse,'send_message',response),patch.object(discord.InteractionResponse,'edit_message',response),patch.object(discord.InteractionResponse,'defer',AsyncMock()),patch.object(discord.InteractionResponse,'send_modal',AsyncMock()),patch.object(discord.Interaction,'edit_original_response',response),patch.object(discord.Webhook,'send',response),patch.object(discord.Webhook,'edit_message',response),patch.object(dm,'_ORIGINAL_SEND',send),patch.object(dm,'_INSTALLED',False)]
        for p in self.patches:p.start()
        dm.install(NS(add_view=lambda view:None));self.ch=channel()
        class Sender(discord.abc.Messageable):
            async def _get_channel(inner):return owner.ch
        self.sender=Sender()
    async def asyncTearDown(self):
        for p in reversed(self.patches):p.stop()
        self.path.stop();self.temp.cleanup();dm._FOLLOWUPS.clear()
    async def test_first_delivery_then_one_language_offer(self):
        result=await self.sender.send('Hello')
        self.assertEqual(result.id,1);self.assertEqual(len(self.calls),2)
        self.assertIsNone(self.calls[0][0]);self.assertIsInstance(self.calls[0][1]['view'],discord.ui.LayoutView)
        self.assertIn('Which language',self.calls[1][2]);self.assertTrue(prefs.was_offered(12))
        await self.sender.send('Again');self.assertEqual(len(self.calls),3);self.assertEqual(prefs.language(12),'en')
    async def test_concurrent_notifications_offer_once_after_first_dm(self):
        await asyncio.gather(*(self.sender.send(f'Message {i}') for i in range(8)))
        self.assertEqual([i for i,c in enumerate(self.calls) if 'Which language' in c[2]],[1]);self.assertEqual(len(self.calls),9)
    async def test_direct_and_interaction_dms_keep_the_picker_second(self):
        parent=NS(guild_id=None,user=NS(id=12),channel=self.ch,message=None,followup=NS(token='mixed-token'))
        view=Panel('Verification complete')
        jobs=[discord.InteractionResponse(parent).send_message(view=view)]
        jobs.extend(self.sender.send(view=view) for _ in range(4))
        await asyncio.wait_for(asyncio.gather(*jobs),1)
        self.assertEqual([i for i,c in enumerate(self.calls) if 'Which language' in c[2]],[1])

    async def test_broadcast_keeps_custom_copy_but_translates_default_heading(self):
        from utils.broadcast_store import build_view
        await self.sender.send(view=build_view({'message':'Bewerbung angenommen'}))
        self.assertIn('Message from the bot team',self.calls[0][2])
        self.assertIn('Bewerbung angenommen',self.calls[0][2])
        prefs.select(12,'de')
        await self.sender.send(view=build_view({'title':'Warning','message':'Your idea was accepted'}))
        self.assertIn('Warning',self.calls[-1][2]);self.assertIn('Your idea was accepted',self.calls[-1][2])
        self.assertIn('<:',self.calls[-1][2])

    async def test_failed_dm_does_not_record_or_prompt(self):
        error=discord.Forbidden(NS(status=403,reason='Forbidden'),'closed')
        with patch.object(dm,'_offer',AsyncMock()) as offer,patch.object(self.sender,'_get_channel',AsyncMock(side_effect=error)):
            with self.assertRaises(discord.Forbidden):await self.sender.send('Never delivered')
            offer.assert_not_awaited()
        self.assertFalse(prefs.was_offered(12))
    async def test_failed_picker_keeps_delivered_message_and_retries_later(self):
        async def failed(*a,**k):raise discord.Forbidden(NS(status=403,reason='Forbidden'),'closed')
        with patch.object(dm,'_ORIGINAL_SEND',failed):result=await self.sender.send('Delivered')
        self.assertEqual(result.id,1);self.assertFalse(prefs.was_offered(12))
        await self.sender.send('Second');self.assertTrue(prefs.was_offered(12))
    async def test_persistent_german_preference_and_protected_names(self):
        prefs.select(12,'de');await self.sender.send('You have been unmuted in **English Server**.')
        self.assertIn('Stummschaltung',self.calls[0][2]);self.assertIn('English Server',self.calls[0][2]);self.assertEqual(len(self.calls),1)
        self.assertEqual(prefs.language(12),'de')
    async def test_custom_server_text_stays_exact(self):
        prefs.select(12,'de');view=preserve(Panel('Warning','Your idea was accepted'))
        await self.sender.send(view=view);self.assertIn('Warning',self.calls[0][2]);self.assertIn('Your idea was accepted',self.calls[0][2])
        await self.sender.send('Your idea was accepted',_university_dm_custom_copy=True);self.assertIn('Your idea was accepted',self.calls[1][2])
    async def test_content_embeds_images_and_files_are_all_inside_v2(self):
        prefs.mark_offered(12)
        embed=discord.Embed(title='Ticket Transcript',description='Transcript details');embed.add_field(name='Server',value='Server name')
        view=discord.ui.View();button=discord.ui.Button(label='Support',custom_id='support');callback=button.callback;view.add_item(button)
        files=[discord.File(io.BytesIO(b'image'),filename='captcha.png'),discord.File(io.BytesIO(b'file'),filename='report.txt')]
        await self.sender.send('Extra text',embed=embed,view=view,files=files)
        output=self.calls[0][1];self.assertNotIn('embed',output);self.assertNotIn('content',output)
        serialized=str(output['view'].to_components())
        for value in ['Extra text','Transcript details','Server name','attachment://captcha.png','attachment://report.txt','support']:self.assertIn(value,serialized)
        self.assertEqual(button.callback,callback)
    async def test_picker_is_restart_safe_and_only_owner_can_change_language(self):
        picker=dm.LanguageView(12);button=next(x for x in picker.walk_children() if isinstance(x,discord.ui.Button) and x.custom_id.endswith(':de'))
        inter=NS(guild_id=None,user=NS(id=99),response=NS(send_message=AsyncMock(),edit_message=AsyncMock()))
        await button.callback(inter);self.assertEqual(prefs.language(12),'en');inter.response.send_message.assert_awaited_once()
        inter.user.id=12;await button.callback(inter);self.assertEqual(prefs.language(12),'de')
        self.assertIn('jetzt **Deutsch**',text(inter.response.edit_message.call_args.kwargs['view']))
        self.assertTrue(dm.LanguageView().is_persistent())
    async def test_language_command_accepts_case_and_typos(self):
        for word in ['Language','LANGUAGE','langauge','languge','lenguage','languaeg','!Language','sprache']:self.assertTrue(dm.is_language_command(word),word)
        for word in ['hello','I would like help','ban','application','no thanks']:self.assertFalse(dm.is_language_command(word),word)
        prefs.select(12,'de');msg=NS(guild=None,author=NS(id=12,bot=False),content='LANGAUGE',channel=self.ch)
        self.assertTrue(await dm.handle_message(msg));self.assertIn('In welcher Sprache',self.calls[0][2])
    async def test_legacy_views_keep_checks_callbacks_timeout_and_wait(self):
        prefs.mark_offered(12)
        view=discord.ui.View(timeout=20);view.secret='preserved';view.interaction_check=AsyncMock(return_value=False)
        button=discord.ui.Button(label='Support',custom_id='legacy');view.add_item(button)
        await self.sender.send('Legacy body',view=view)
        converted=self.calls[0][1]['view']
        self.assertEqual(converted.timeout,20);self.assertEqual(converted.secret,'preserved')
        self.assertFalse(await converted.interaction_check(NS()))
        waiter=asyncio.create_task(view.wait());await asyncio.sleep(0);converted.stop()
        self.assertFalse(await asyncio.wait_for(waiter,1));self.assertTrue(view.is_finished())

    async def test_custom_cv2_heading_remains_exact(self):
        from utils.cv2 import CV2
        prefs.select(12,'de');view=preserve_values(CV2('Warning','Your idea was accepted'),['Warning','Your idea was accepted'])
        await self.sender.send(view=view)
        self.assertIn('Warning',self.calls[0][2]);self.assertIn('Your idea was accepted',self.calls[0][2])

    async def test_interactions_deferred_followups_and_edits_use_same_envelope(self):
        prefs.select(12,'de');parent=NS(guild_id=None,user=NS(id=12),channel=self.ch,message=None,followup=NS(token='test-token'))
        response=discord.InteractionResponse(parent);await response.send_message('Verification complete')
        self.assertIn('Verifizierung abgeschlossen',self.calls[0][2]);await response.defer()
        await discord.Webhook.send(NS(token='test-token'),'New reply in your ticket');self.assertIn('Neue Antwort',self.calls[-1][2])
        await response.edit_message(view=dm.LanguageView(12,'de'))
        self.assertIsNone(self.calls[-1][0]);self.assertEqual(self.calls[-1][1]['embeds'],[])
    async def test_modal_localizes_bot_fields_and_preserves_server_fields(self):
        prefs.select(12,'de')
        modal=discord.ui.Modal(title='Enter Verification Code')
        standard=discord.ui.TextInput(label='Verification Code',placeholder='Enter the 6-character code from the image');modal.add_item(standard)
        custom=discord.ui.Label(text='Your question',component=discord.ui.TextInput(placeholder='Reason'));custom._university_dm_custom_copy=True;modal.add_item(custom)
        parent=NS(guild_id=None,user=NS(id=12),channel=self.ch,message=None,followup=NS(token='modal-token'))
        await discord.InteractionResponse(parent).send_modal(modal)
        self.assertEqual(modal.title,'Verifizierungscode eingeben');self.assertEqual(standard.label,'Verifizierungscode')
        self.assertEqual(custom.component.placeholder,'Reason')

    async def test_long_dm_is_split_without_losing_text_controls_or_files(self):
        prefs.mark_offered(12)
        content='X'*8500
        button=discord.ui.Button(label='Support',custom_id='long-control')
        await self.sender.send(view=Panel('Long message',content,buttons=[button]),file=discord.File(io.BytesIO(b'file'),filename='long.txt'))
        self.assertGreater(len(self.calls),1)
        self.assertEqual(sum(call[2].count('X') for call in self.calls),8500)
        for call in self.calls:
            self.assertLessEqual(len(call[2]),4000);self.assertIsInstance(call[1]['view'],discord.ui.LayoutView)
        self.assertIn('long-control',str(self.calls[-1][1]['view'].to_components()))
        file_calls=[call for call in self.calls if 'attachment://long.txt' in str(call[1]['view'].to_components())]
        self.assertEqual(len(file_calls),1);self.assertEqual(file_calls[0][1]['files'][0].filename,'long.txt')

    async def test_user_and_member_dm_senders_use_the_same_wrapper(self):
        prefs.mark_offered(12)
        for cls in (discord.User,discord.Member):
            self.assertIs(cls.send,discord.abc.Messageable.send)
            receiver=object.__new__(cls)
            with patch.object(cls,'_get_channel',AsyncMock(return_value=self.ch)):
                await receiver.send('Private account message')
        self.assertEqual(len(self.calls),2)
        self.assertTrue(all(isinstance(call[1]['view'],discord.ui.LayoutView) for call in self.calls))

    async def test_attachment_edit_retains_registered_callbacks(self):
        prefs.mark_offered(12);view=Panel('Ticket',buttons=[discord.ui.Button(label='Support',custom_id='keep')])
        button=next(x for x in view.walk_children() if isinstance(x,discord.ui.Button));callback=button.callback
        message=NS(id=77,components=[object()],_state=NS(_view_store=NS(_views={77:{(2,'keep'):button}})))
        prepared=dm.prepare(discord.utils.MISSING,{},12,editing=True,message=message)
        self.assertIs(prepared['view'],view);self.assertEqual(button.callback,callback)

    async def test_public_messages_unchanged(self):
        self.ch=NS();await self.sender.send('Original guild text');self.assertEqual(self.calls[0][0],'Original guild text');self.assertNotIn('view',self.calls[0][1])
    async def test_same_view_can_switch_languages(self):
        view=Panel('Verification complete','Thank you');prefs.select(12,'de');await self.sender.send(view=view)
        self.assertIn('Verifizierung abgeschlossen',self.calls[0][2]);prefs.select(12,'en');await self.sender.send(view=view)
        self.assertIn('Verification complete',self.calls[1][2]);self.assertNotIn('Verifizierung',self.calls[1][2])

class TranslationTests(unittest.TestCase):
    def test_frames_translate_without_changing_dynamic_reasons(self):
        self.assertEqual(translate('You have been banned from **Deutsch** by **Warning**. Reason: Thank you','de'),'Du wurdest auf **Deutsch** von **Warning** gebannt. Grund: Thank you')
        self.assertEqual(translate('Frage 2 von 5','en'),'Question 2 of 5')
        self.assertEqual(translate('<@12> ist jetzt **Level 7**!', 'en'), '<@12> is now **level 7**!')
        self.assertEqual(translate('Deine Bewerbung als **Support** (APP-123) wurde angenommen.\n\n**Begründung:**\nOriginal reason', 'en'), 'Your application for **Support** (APP-123) was accepted.\n\n**Reason:**\nOriginal reason')
        self.assertIn('1 Tag, 2 Stunden',translate('You have been muted in **Server** by **Admin** for 1 day, 2 hours. Reason: Original reason','de'))
        self.assertEqual(translate('English Server','de'),'English Server')
        self.assertEqual(translate('```\nprivate-key\n```','de'),'```\nprivate-key\n```')

if __name__=='__main__':unittest.main()
