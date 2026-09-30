#!/usr/bin/env python3
"""Complete three-part Automation dashboard and runtime."""
import os,tempfile,time
from pathlib import Path
path=str(Path(tempfile.gettempdir())/'lbost-automation-complete.sqlite3')
for suffix in ('','-wal','-shm'):Path(path+suffix).unlink(missing_ok=True)
os.environ['LBOST_SHOP_DB_PATH']=path;os.environ['LBOST_SHOP_SECRET_KEY']='automation-test';os.environ['LBOST_SHOP_TOKEN_ENCRYPTION_KEY']='automation-encryption'
from lbost_shop_app.config import get_settings
from lbost_shop_app import db,automation as store
s=get_settings();db.init_features(s);store.ensure_schema(s);now=int(time.time())
response_id=store.save_response(s,1,{'trigger':'hallo','response':'Hallo {user}','title':'Antwort','color':'#5865f2','exact':True,'cooldown_seconds':30,'enabled':True},9)
message_id=store.save_message(s,1,{'channel_id':10,'title':'Plan','content':'Heute {date}','send_at':now+1,'repeat_minutes':0,'delete_after':5,'enabled':True},9)
repeat_id=store.save_message(s,1,{'channel_id':10,'title':'Wiederholung','content':'Text','send_at':now+1,'repeat_minutes':15,'enabled':True},9)
announcement_id=store.save_announcement(s,1,{'channel_id':10,'title':'News','content':'Hallo {server}','interval_minutes':60,'first_delay_minutes':0,'mention_role_id':20,'enabled':True},9)
assert store.get(s,1,'responses',response_id)['exact']==1 and len(store.responses(s,1))==1
messages=store.claim_due(s,'messages',now+2,guild_id=1);assert {x['id'] for x in messages}=={message_id,repeat_id}
assert not store.get(s,1,'messages',message_id)['enabled'] and store.get(s,1,'messages',repeat_id)['next_run']>now
assert not store.claim_due(s,'messages',now+2,guild_id=1)
ann=store.claim_due(s,'announcements',now+2,guild_id=1);assert ann[0]['id']==announcement_id and store.get(s,1,'announcements',announcement_id)['next_run']>now
assert store.toggle(s,1,'responses',response_id) and not store.responses(s,1)
assert store.delete(s,1,'responses',response_id)
legacy={'auto_responses_json':[{'trigger':'alt','response':'legacy','exact':False}],'announcements_json':[{'channel_id':'11','title':'Alt','content':'legacy','interval_minutes':90}]}
assert store.migrate_legacy(s,2,legacy)==2 and store.migrate_legacy(s,2,legacy)==0
root=Path(__file__).parents[1];template=(root/'lbost_shop_app/templates/automation.html').read_text();main=(root/'lbost_shop_app/main.py').read_text();client=(root/'lbost_shop_bot/client.py').read_text();script=(root/'lbost_shop_app/static/dashboard.js').read_text()
for token in ('Automated messages','Auto-responses','Automatic announcements','data-auto-modal="messages"','data-auto-modal="responses"','data-auto-modal="announcements"','repeat_minutes','cooldown_seconds','interval_minutes','mention_role_id','first_delay_minutes','delete_after'):assert token in template
for token in ('automation/save','automation/action','_automation_payload','flags":32768'):assert token in main
for token in ('claim_due','automation_store.responses','AllowedMentions(roles=True','delete(delay=delay)'):assert token in client
assert 'data-auto-new' in script and 'data-auto-edit' in script and 'data-auto-token' in script
assert 'FREE_MAX_COMMANDS = 20' in (root/'lbost_shop_app/custom_commands.py').read_text()
print('ok   Automation vollständig: geplante Nachrichten, Auto-Responses, Ankündigungen, Migration und Components V2')
