"""Exercise real coaching storage, isolation, API gates and local server reading."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI
from api.routes import tickets
from api.db_manager import db_manager
from api import ticket_panels
from utils import ticket_ai as ai, ticket_ai_scan as scan, ticket_ai_workspace as store

class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=self.temp.name+'/ticket.db'
        self.patches=[patch.object(tickets,'DB',self.path),patch.object(store,'DB',self.path),patch.object(scan,'DB',self.path),
          patch.object(ai.feature_gates,'is_premium_guild',side_effect=lambda gid:gid in (42,43)),patch.object(tickets.feature_gates,'has_premium_access',side_effect=lambda gid,*args,**kwargs:gid in (42,43))]
        for p in self.patches:p.start()
        db=await tickets._db();await tickets._ensure_ai_schema(db)
        panel=await ticket_panels.create_panel(db,42,'Support');self.cat=await ticket_panels.upsert_category(db,42,panel,{'name':'Premium'})
        app=FastAPI();app.include_router(tickets.router,prefix='/tickets')
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')
    async def asyncTearDown(self):
        await self.client.aclose();await db_manager.close_all()
        for task in list(tickets._scan_tasks.values()):task.cancel()
        tickets._scan_tasks.clear()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    async def post(self,message,mode='teach',gid=42,actor='100'):
        return await self.client.post(f'/tickets/{gid}/ai/chat',json={'message':message,'mode':mode,'actor':actor,'language':'en'})
    async def test_exact_facts_deduplicate_and_chats_are_personal(self):
        await self.post('Premium costs 5 euros here.')
        repeated=(await self.post('Premium costs 5 euros here.')).json()
        self.assertEqual(repeated['status'],'conflict')
        self.assertEqual(len(await store.history(42,'100')),2)
        await self.resolve('Premium costs 5 euros here.',repeated,'keep')
        facts=await store.memories(42);self.assertEqual(len(facts),1);self.assertEqual(facts[0]['content'],'Premium costs 5 euros here.')
        self.assertEqual(len(await store.history(42,'100')),4);self.assertEqual(await store.history(42,'200'),[]);self.assertEqual(await store.memories(43),[])
        await store.clear_history(42,'100');self.assertEqual(await store.history(42,'100'),[]);self.assertEqual(len(await store.memories(42)),1)

    async def resolve(self,message,pending,action):
        return await self.client.post('/tickets/42/ai/chat',json={'actor':'100','message':message,'mode':'teach','language':'en','resolution':{'action':action,'versions':{item['reference']:item['version'] for item in pending['conflicts']}}})

    async def test_paraphrases_require_decision_and_replace_all_related_sources(self):
        await self.post('Premium kostet nix.')
        pending=(await self.post('Premium ist gratis.')).json()
        self.assertEqual(pending['status'],'conflict');self.assertEqual((await store.memories(42))[0]['content'],'Premium kostet nix.')
        await self.resolve('Premium ist gratis.',pending,'keep')
        self.assertEqual((await store.memories(42))[0]['content'],'Premium kostet nix.')
        await store.save_memory(42,'Premium bekommt eine blaue Rolle.')
        upload=await self.client.put('/tickets/42/ai/knowledge',json={'filename':'info.txt','content':'Premium ist kostenlos.\nTickets helfen dir bei Fragen.'})
        self.assertEqual(upload.status_code,200)
        pending=(await self.post('Premium costs 5 euros.')).json()
        self.assertEqual({c['source'] for c in pending['conflicts']},{'memory','document'})
        result=await self.resolve('Premium costs 5 euros.',pending,'replace')
        self.assertEqual(result.json()['status'],'saved')
        self.assertEqual({m['content'] for m in await store.memories(42)},{'Premium costs 5 euros.','Premium bekommt eine blaue Rolle.'})
        doc=(await tickets.get_ticket_ai(42))['knowledge']['content']
        self.assertNotIn('kostenlos',doc);self.assertIn('5 euros',doc);self.assertIn('Tickets helfen',doc)

    async def test_stale_decisions_never_overwrite_newer_knowledge(self):
        await self.post('Premium costs 5 euros.')
        pending=(await self.post('Premium is free.')).json();fact=(await store.memories(42))[0]
        await store.save_memory(42,'Premium costs 6 euros.',memory_id=fact['id'])
        stale=await self.resolve('Premium is free.',pending,'replace')
        self.assertEqual(stale.json()['status'],'conflict');self.assertIn('6 euros',stale.json()['conflicts'][0]['content'])
        self.assertEqual((await store.memories(42))[0]['content'],'Premium costs 6 euros.')
    async def test_edit_delete_and_enable_memory_only_with_panel_categories(self):
        await self.post('Premium costs 5 euros here.');fact=(await store.memories(42))[0]
        self.assertEqual((await self.client.put('/tickets/43/ai/memories',json={'id':fact['id'],'content':'intruder'})).status_code,404)
        await self.client.put('/tickets/42/ai/memories',json={'id':fact['id'],'title':'Premium','content':'Premium costs 6 euros.'})
        self.assertEqual((await store.memories(42))[0]['content'],'Premium costs 6 euros.')
        with patch.object(ai,'api_key_configured',return_value=True):
            r=await self.client.patch('/tickets/42/ai',json={'enabled':True,'categories':[{'category_id':self.cat,'enabled':True}]})
        self.assertEqual(r.status_code,200)
        settings=(await self.client.get('/tickets/42/ai')).json();self.assertTrue(settings['enabled']);self.assertEqual(settings['categories'][0]['panel_name'],'Support')
        await self.client.delete('/tickets/42/ai/knowledge');self.assertTrue((await self.client.get('/tickets/42/ai')).json()['enabled'])
        await self.client.delete(f"/tickets/42/ai/memories/{fact['id']}");self.assertFalse((await self.client.get('/tickets/42/ai')).json()['enabled'])
    async def test_grounded_response_uses_saved_fact_without_teaching_questions(self):
        await self.post('Premium costs 5 euros here.');await store.save_memory(43,'other guild private')
        async def provider(prompt,**kwargs):
            self.assertIn('5 euros',prompt);self.assertNotIn('other guild private',prompt)
            return json.dumps({'supported':True,'answer':'Premium costs 5 euros.'})
        with patch.object(ai,'api_key_configured',return_value=True),patch.dict('os.environ',{ai.API_KEY_ENV:'test-only'}),patch.object(ai,'generate_text',side_effect=provider):
            result=await self.post('How much does Premium cost?',mode='ask')
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()['messages'][-1]['content'],'Premium costs 5 euros.');self.assertEqual(len(await store.memories(42)),1)
        with patch.object(ai,'generate_text',return_value='{"supported":"false","answer":"hallucinated"}'),patch.dict('os.environ',{ai.API_KEY_ENV:'test-only'}):
            self.assertIsNone(await ai.grounded_answer('Premium?',['Premium costs 5 euros']))
        with patch.object(ai,'api_key_configured',return_value=True),patch.dict('os.environ',{ai.API_KEY_ENV:'test-only'}),patch.object(ai,'generate_text',side_effect=RuntimeError('provider offline')):
            failed=await self.post('Premium?',mode='ask')
        self.assertEqual(failed.status_code,502);self.assertEqual(failed.json()['detail'],'ai_unavailable');self.assertEqual(len(await store.history(42,'100')),4)
        context=ai.answer_context('Premium cost?', 'Premium costs 3 euros.', [{'title':'New pricing','content':'Premium costs 6 euros from November onwards in the server shop.'},{'title':'Premium','content':'Premium costs 5 euros.'}])
        self.assertIn('6 euros',context[0]);self.assertIn('3 euros',context[-1])
    async def test_access_limits_and_failed_settings_cannot_partially_persist(self):
        self.assertEqual((await self.post('fact',gid=99)).status_code,402)
        with patch.object(ai,'pilot_available',return_value=False),patch.object(tickets.feature_gates,'has_premium_access',return_value=False):self.assertEqual((await self.post('fact')).status_code,402)
        self.assertEqual((await self.post('fact',actor='')).status_code,401);self.assertEqual((await self.post('x'*4001)).status_code,400)
        r=await self.client.patch('/tickets/42/ai',json={'enabled':False,'fallback_text':'bad','categories':[{'category_id':99999,'enabled':True}]})
        self.assertEqual(r.status_code,400);await self.post('Premium costs 5 euros here.')
        self.assertNotEqual((await self.client.get('/tickets/42/ai')).json()['fallback_text'],'bad')
        with patch.object(ai,'api_key_configured',return_value=False):self.assertEqual((await self.post('Premium?',mode='ask')).status_code,503)

    async def test_any_premium_server_has_access_without_rollout_and_frozen_rules_remain(self):
        with patch.object(ai,'_allowed_guilds',set()),patch.object(ai.feature_gates,'is_premium_guild',return_value=True),patch.object(tickets.feature_gates,'has_premium_access',return_value=True):
            self.assertTrue(ai.pilot_available(777))
            self.assertTrue((await self.client.get('/tickets/777/ai-available')).json()['available'])
            self.assertEqual((await self.post('Premium costs 5 euros.',gid=777)).status_code,200)
            self.assertEqual((await self.client.get('/tickets/777/ai')).status_code,200)
        with patch.object(ai.feature_gates,'is_premium_guild',return_value=True),patch.object(tickets.feature_gates,'has_premium_access',side_effect=lambda gid,*args,configure=False: not configure):
            self.assertEqual((await self.client.get('/tickets/777/ai')).status_code,200)
            self.assertEqual((await self.post('new fact',gid=777)).status_code,423)
        with patch.object(ai.feature_gates,'is_premium_guild',return_value=False),patch.object(tickets.feature_gates,'has_premium_access',return_value=False):
            self.assertFalse((await self.client.get('/tickets/777/ai-available')).json()['available'])
            self.assertEqual((await self.client.get('/tickets/777/ai')).status_code,402)
    async def test_scan_is_local_and_handles_unreadable_and_private_ticket_channels(self):
        admin=NS(id=7,bot=False,guild_permissions=NS(administrator=True));visitor=NS(id=8,bot=False,guild_permissions=NS(administrator=False))
        def channel(ident,name,permitted=True):
            async def history(**kwargs):
                yield NS(author=visitor,content='Never learn member private data',created_at=datetime.now(timezone.utc))
                yield NS(author=admin,content='Premium costs 5 euros here.',created_at=datetime.now(timezone.utc))
            return NS(id=ident,name=name,topic=None,category=None,permissions_for=lambda me:NS(view_channel=permitted,read_message_history=permitted),history=history)
        readable=channel(10,'rules');denied=channel(11,'private',False);private=channel(12,'ticket-private')
        db=await tickets._db();await db.execute('INSERT INTO open_tickets(channel_id,guild_id,creator_id) VALUES(12,42,7)');await db.commit()
        guild=NS(id=42,name='Server',owner_id=7,roles=[],channels=[readable,denied,private],text_channels=[readable,denied,private],threads=[],forums=[],me=object())
        bot=NS(get_guild=lambda gid:guild,intents=NS(message_content=True));provider=AsyncMock(side_effect=AssertionError('Raw server data must not be sent to a model'))
        with patch.object(scan.config_transfer,'export_guild',return_value={'databases':{'settings':{'api_key':'secret','welcome':'Read the rules'}}}),patch.object(ai,'generate_text',provider),patch.object(ai,'api_key_configured',return_value=False):
            await tickets.start_ticket_ai_scan(42,bot=bot);await tickets._scan_tasks[42]
        result=await tickets.get_ticket_ai_scan(42)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['message_count'],1);self.assertEqual(result['skipped_channels'],1)
        self.assertIn('5 euros',result['draft']);self.assertIn('Read the rules',result['draft'])
        for value in ('secret','Never learn','ticket-private'):self.assertNotIn(value,result['draft'])
        self.assertEqual(result['warnings'][0]['code'],'history_permission');provider.assert_not_awaited();self.assertIsNone((await tickets.get_ticket_ai(42))['knowledge'])
    async def test_schema_upgrade_and_retention_preserve_knowledge(self):
        db=sqlite3.connect(':memory:');db.execute('CREATE TABLE ticket_ai_scan_jobs(guild_id INTEGER PRIMARY KEY,status TEXT,progress INTEGER,total_channels INTEGER,message_count INTEGER,draft TEXT,error TEXT,updated_at INTEGER)');ai.ensure_sync_schema(db)
        self.assertIn('warnings',{r[1] for r in db.execute('PRAGMA table_info(ticket_ai_scan_jobs)')});db.close()
        await self.post('Premium costs 5 euros here.')
        async with store.connection() as db:await db.execute('UPDATE ticket_ai_coaching SET created_at=0');await db.commit()
        self.assertEqual(await store.history(42,'100'),[]);self.assertEqual(len(await store.memories(42)),1)

    async def test_real_discord_listener_uses_memory_only_and_respects_claim_race(self):
        from cogs.commands.ticket import TicketCog, TicketDatabase
        await self.post('Premium costs 5 euros here.')
        db=TicketDatabase(self.path)
        db.execute('INSERT INTO open_tickets(channel_id,guild_id,creator_id,category_db_id) VALUES(123,42,100,?)',(self.cat,))
        db.execute('INSERT INTO ticket_ai_settings(guild_id,enabled) VALUES(42,1)')
        db.execute('INSERT INTO ticket_ai_categories(guild_id,category_id,enabled) VALUES(42,?,1)',(self.cat,))
        cog=TicketCog.__new__(TicketCog);cog.db=db;cog._ai_inflight=set()
        @asynccontextmanager
        async def typing():yield
        channel=NS(id=123,send=AsyncMock(),typing=typing)
        message=NS(guild=NS(id=42),author=NS(id=100,bot=False),content='How much does Premium cost?',channel=channel)
        async def provider(prompt,**kwargs):
            self.assertIn('5 euros',prompt)
            return json.dumps({'supported':True,'answer':'Premium costs 5 euros.'})
        try:
            with patch.object(ai,'api_key_configured',return_value=True),patch.dict('os.environ',{ai.API_KEY_ENV:'test-only'}),patch.object(ai,'generate_text',side_effect=provider):
                await TicketCog.on_message(cog,message)
                channel.send.assert_awaited_once()
                components=channel.send.call_args.kwargs['view'].to_components()
                self.assertIn('5 euros',json.dumps(components));self.assertEqual(components[0]['type'],17)
                channel.send.reset_mock()
                async def claimed_while_generating(prompt,**kwargs):
                    db.execute('UPDATE open_tickets SET is_claimed=1 WHERE channel_id=123')
                    return await provider(prompt,**kwargs)
                with patch.object(ai,'generate_text',side_effect=claimed_while_generating):await TicketCog.on_message(cog,message)
                channel.send.assert_not_awaited();self.assertFalse(cog._ai_inflight)
        finally:db.conn.close()

    async def test_configuration_export_excludes_personal_chats_and_transcripts(self):
        from api import config_transfer
        await self.post('Premium costs 5 euros here.')
        async with store.connection() as db:
            await db.execute("INSERT INTO ticket_transcripts(ticket_id,guild_id,guild_name,channel_name,creator_id,closed_by_id,created_at,expires_at,messages_json) VALUES(1,42,'Server','ticket',100,200,'2026-10-09','2026-11-09','private conversation')");await db.commit()
        with patch.object(config_transfer,'iter_database_files',return_value=[self.path]):exported=await config_transfer.export_guild(42)
        payload=json.dumps(exported)
        self.assertIn('ticket_ai_memories',payload)
        self.assertNotIn('ticket_ai_coaching',payload);self.assertNotIn('ticket_transcripts',payload);self.assertNotIn('private conversation',payload)

    async def test_large_binary_backups_cannot_starve_scan_and_workers_are_parallel(self):
        from api import config_transfer
        async with store.connection() as db:
            await db.execute('CREATE TABLE backups(guild_id INTEGER,daten BLOB)')
            await db.execute('INSERT INTO backups VALUES(42,?)',(b'\xc0\xb2'*500000,))
            await db.execute('CREATE TABLE support_config(guild_id INTEGER,image BLOB,description TEXT)')
            await db.execute('INSERT INTO support_config VALUES(42,?,?)',(b'\xc0\xb2'*500000,'Read the support rules'))
            await db.commit()
        active=peak=0
        def channel(index):
            async def history(**kwargs):
                nonlocal active,peak
                self.assertEqual(kwargs['limit'],301);self.assertFalse(kwargs['oldest_first'])
                active+=1;peak=max(peak,active)
                try:
                    await asyncio.sleep(.02)
                    yield NS(author=NS(id=7,bot=False,guild_permissions=NS(administrator=True)),content='Premium costs 5 euros.',created_at=datetime.now(timezone.utc))
                finally:active-=1
            return NS(id=index,name=f'rules-{index}',topic=None,history=history,permissions_for=lambda _:NS(view_channel=True,read_message_history=True))
        channels=[channel(i+100) for i in range(37)]
        guild=NS(id=42,name='Server',owner_id=7,roles=[],channels=channels,text_channels=channels,threads=[],forums=[],me=object())
        with patch.object(config_transfer,'iter_database_files',return_value=[self.path]):
            full=await config_transfer.export_guild(42)
            self.assertTrue(any(t.get('backups') for t in full['databases'].values()))
            await tickets.start_ticket_ai_scan(42,bot=NS(get_guild=lambda _:guild,intents=NS(message_content=True)))
            await tickets._scan_tasks[42]
        result=await tickets.get_ticket_ai_scan(42)
        self.assertEqual(result['progress'],37);self.assertEqual(result['total_channels'],37);self.assertEqual(result['message_count'],37)
        self.assertGreater(peak,1);self.assertLessEqual(peak,4)
        self.assertIn('5 euros',result['draft']);self.assertIn('Read the support rules',result['draft'])
        self.assertNotIn('\\x',result['draft']);self.assertLess(len(result['draft'].encode()),100000)
        self.assertFalse(any(w['code']=='source_limit' for w in result['warnings']))
        async with store.connection() as db:
            await db.execute('UPDATE ticket_ai_scan_jobs SET draft=? WHERE guild_id=42',("data: "+str(b'\xc0\xb2'*1000)+"\nPremium costs 5 euros.",));await db.commit()
        old=await tickets.get_ticket_ai_scan(42);self.assertNotIn('\\x',old['draft']);self.assertIn('5 euros',old['draft']);self.assertIn('binary_removed',{w['code'] for w in old['warnings']})

    async def test_cancel_scan_stops_parallel_readers_without_completed_draft(self):
        started=asyncio.Event();stopped=asyncio.Event();active=0
        async def history(**kwargs):
            nonlocal active
            active+=1;started.set()
            try:
                await asyncio.Event().wait()
                yield None
            finally:
                active-=1
                if not active:stopped.set()
        channels=[NS(id=i+100,name=f'channel-{i}',topic='',history=history,permissions_for=lambda _:NS(view_channel=True,read_message_history=True)) for i in range(8)]
        guild=NS(name='Cancel test',owner_id=100,me=object(),channels=channels,text_channels=channels,threads=[],forums=[],roles=[])
        with patch.object(scan.config_transfer,'export_guild',AsyncMock(return_value={'databases':{}})):
            await tickets.start_ticket_ai_scan(42,bot=NS(get_guild=lambda _:guild,intents=NS(message_content=True)))
            await asyncio.wait_for(started.wait(),2)
            await tickets.cancel_ticket_ai_scan(42)
            await asyncio.wait_for(stopped.wait(),2)
        self.assertEqual(active,0)
        result=await tickets.get_ticket_ai_scan(42)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['draft'],'')
        self.assertNotIn(42,tickets._scan_tasks)

    async def test_followups_use_only_creator_context_and_match_typoes(self):
        creator=NS(id=100,bot=False)
        async def history(**kwargs):
            yield NS(id=3,author=creator,content='Und wo bekomme ich es?')
            yield NS(id=2,author=NS(id=200,bot=False),content='Other member private data')
            yield NS(id=1,author=creator,content='Wie viel kostet Premium?')
        current=NS(id=3,author=creator,content='Und wo bekomme ich es?',channel=NS(history=history))
        previous=await ai.recent_ticket_questions(current)
        self.assertEqual(previous,['Wie viel kostet Premium?'])
        self.assertTrue(ai.answer_context('Was kostet Prenium?', '', [{'title':'Premium','content':'Premium ist gratis.'}]))
        self.assertIn('Premium',ai.conversation_question(current.content,previous))
        facts=[{'title':'Jail','content':'Jail costs 10 euros.'},{'title':'Premium','content':'Premium costs 5 euros.'}]
        self.assertIn('Premium',ai.conversation_excerpts('Und wie viel kostet es?', '', facts, previous)[0])
        self.assertIn('Jail',ai.conversation_excerpts('What does Jail cost?', '', facts, previous)[0])

if __name__=='__main__':unittest.main()
