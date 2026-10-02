#!/usr/bin/env python3
"""Regression coverage for the complete isolated University-style giveaway."""
import os, tempfile
from pathlib import Path
path=str(Path(tempfile.gettempdir())/'lbost-giveaways-complete.sqlite3')
for suffix in ('','-wal','-shm'): Path(path+suffix).unlink(missing_ok=True)
os.environ['LBOST_SHOP_DB_PATH']=path
os.environ['LBOST_SHOP_SECRET_KEY']='giveaway-test-secret'
os.environ['LBOST_SHOP_TOKEN_ENCRYPTION_KEY']='giveaway-encryption-secret'
from lbost_shop_app import db, giveaways as store
from lbost_shop_app.config import get_settings
s=get_settings(); db.init_features(s)
required={'host_id','start_time','title','description','colour','button_label','button_emoji','image_url','blocked_role_id','min_messages','min_level','min_account_days','min_member_days','dm_winners','dm_host','allow_leave',*store.DEFAULT_MESSAGES}
with db._gesichert(s) as conn:
 columns={r['name'] for r in conn.execute('PRAGMA table_info(giveaways)').fetchall()}
 tables={r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
assert required<=columns
assert {'giveaway_entries','giveaway_winners','giveaway_boosts','giveaway_dms','giveaway_activity'}<=tables
record={'message_id':10,'guild_id':20,'channel_id':30,'prize':'Premium','winners':2,'ends_at':9999999999,'status':'active','winner_ids':'[]','host_id':40,'start_time':1,**store.clean({})}
store.create(record,s)
for uid in (1,2,3,4): assert store.toggle_entry(10,uid,True,s)[0]=='joined'
store.set_boost(10,1,'guaranteed',1,'interne Notiz',40,s)
store.set_boost(10,2,'weight',100,'mehr Lose',40,s)
odds=store.chances(10,2,s)
assert odds[1]==100 and odds[2]>odds[3]
for _ in range(30):
 winners=store.draw(10,2,s)
 assert len(winners)==len(set(winners))==2 and 1 in winners
store.record_winners(10,[1,2],s)
assert not ({1,2}&set(store.draw(10,2,s,exclude_past=True)))
assert store.claim_dm(10,1,'winner',s) and not store.claim_dm(10,1,'winner',s)
assert store.mark_ended(10,s) and not store.mark_ended(10,s)
root=Path(__file__).parents[1]
main=(root/'lbost_shop_app/main.py').read_text()
client=(root/'lbost_shop_bot/client.py').read_text()
overview=(root/'lbost_shop_app/templates/giveaways.html').read_text()
detail=(root/'lbost_shop_app/templates/giveaway_detail.html').read_text()
for token in ('duration_minutes','msg_winner_dm','msg_announce','blocked_role_id','min_messages','min_level','min_account_days','min_member_days','dm_winners','dm_host','allow_leave'): assert token in overview
for token in ('data-gw-detail-tab="entries"','data-gw-detail-tab="texts"','data-gw-detail-tab="rules"','data-gw-entry-search','data-gw-boost','guaranteed','Interne opmerking','extend_minutes','value="reroll"'): assert token in detail
for token in ('giveaway_join_','failed_requirements','claim_dm','exclude_past=reroll','giveaway_view'): assert token in client
for token in ('_giveaway_finish','_giveaway_dm','giveaways/{message_id}/boost','giveaways/{message_id}/action'): assert token in main
assert 'flags": 32768' in main and 'LayoutView' in client
print('ok   vollständiges Giveaway: Dashboard, Details, Regeln, Chancen, Ziehung, DMs und Components V2')
