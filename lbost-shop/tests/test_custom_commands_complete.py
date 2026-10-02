#!/usr/bin/env python3
"""Complete University Custom Commands in LBoost, deliberately without Marketplace."""
import asyncio, os, tempfile, types
from pathlib import Path
path=str(Path(tempfile.gettempdir())/'lbost-custom-commands-complete.sqlite3')
for suffix in ('','-wal','-shm'):Path(path+suffix).unlink(missing_ok=True)
os.environ['LBOST_SHOP_DB_PATH']=path;os.environ['LBOST_SHOP_SECRET_KEY']='custom-command-test';os.environ['LBOST_SHOP_TOKEN_ENCRYPTION_KEY']='custom-command-encryption'
import discord
from lbost_shop_app.config import get_settings
from lbost_shop_app import db, custom_commands as store
from lbost_shop_bot.custom_commands import CustomCommandsService
settings=get_settings();db.init_features(settings);store.ensure_schema(settings)
flow={'description':'Vollständiger Test','enabled':True,'cooldown':10,'allowed_roles':['9'],'allowed_users':['42'],'deny_without_role':True,'parameters':[{'id':'p','name':'target','description':'Ziel','type':'user','required':True}], 'actions':[{'id':'a','type':'reply','text':'Hallo {target:UserPing}','ephemeral':True,'embed':{'enabled':True,'title':'Titel','description':'{server}','color':'#2563eb','image_url':'https://example.com/a.png','footer':'Fuß'},'buttons':[{'id':'b','label':'Klick','emoji':'','style':'green','actions':[{'id':'c','type':'condition_role','role_id':'9','then':[{'id':'d','type':'add_role','role_id':'10'}],'else':[{'id':'e','type':'dm','text':'Nein'}]}]}]},{'id':'f','type':'send_channel','channel_id':'7','text':'Kanal'},{'id':'g','type':'remove_role','role_id':'10'}]}
store.validate_config(flow)
for i in range(20):assert store.save(settings,1,f'cmd-{i}','ok','owner',use_prefix=True,use_slash=True,config=flow)
assert not store.save(settings,1,'cmd-20','no','owner',config=flow)
for i in range(20):assert store.save(settings,2,f'premium-{i}','ok','owner',config=flow,max_commands=20)
assert not store.save(settings,2,'premium-20','no','owner',config=flow,max_commands=20)
assert store.get(settings,1,'CMD-0')['config']['actions'][0]['buttons'][0]['actions'][0]['type']=='condition_role'
assert store.delete(settings,1,'cmd-2') and not store.delete(settings,1,'missing')
class Tree:
 def add_command(self,*a,**k):pass
 def remove_command(self,*a,**k):pass
 async def sync(self,*a,**k):return []
class Bot:
 tree=Tree();user=object();settings=settings
 async def get_prefix(self,message):return ['!']
 def get_command(self,name):return None
class Role:
 def __init__(self,id):self.id=id
class Author:
 id=42;bot=False;mention='<@42>';display_name='Alex';roles=[Role(9)]
class Guild:id=1;name='Testserver'
class Channel:id=7;mention='<#7>'
class Message:
 guild=Guild();author=Author();channel=Channel()
 def __init__(self,content):self.content=content
async def check():
 service=CustomCommandsService(Bot());await service.refresh()
 found=await service.invocation(Message('!cmd-0 Welt'));assert found and found[1]=='Welt'
 rendered=service._render('{user} {server} {target:UserPing}',Author(),Guild(),Channel(),'x',{'target':types.SimpleNamespace(mention='<@8>')});assert rendered=='<@42> Testserver <@8>'
 view=service._view(flow['actions'][0],'Hallo',Author(),Guild(),Channel(),'',{'target':types.SimpleNamespace(mention='<@8>')});assert isinstance(view,discord.ui.LayoutView)
asyncio.run(check())
root=Path(__file__).parents[1]
template=(root/'lbost_shop_app/templates/custom_commands.html').read_text();script=(root/'lbost_shop_app/static/dashboard.js').read_text();runtime=(root/'lbost_shop_bot/custom_commands.py').read_text();main=(root/'lbost_shop_app/main.py').read_text();client=(root/'lbost_shop_bot/client.py').read_text()
for token in ('Commandomaker','data-cc-actions','data-cc-parameters','data-cc-pane="settings"','Rol geven','Rol verwijderen','Bericht verzenden','DM verzenden','Voorwaarde','use_prefix','use_slash','use_exact','use_contains'):assert token in template
for token in ('condition_role','allowed_roles','allowed_users','cooldown','LayoutView','_make_slash_command','handle_message','buttons'):assert token in runtime
assert 'CustomCommandsService(self)' in client and 'custom_commands_service.start()' in client
assert 'custom_commands/save' in main and 'custom_commands/delete' in main
for forbidden in ('Marketplace','marketplace','Publiceren','publishTarget'):assert forbidden not in template and forbidden not in runtime and forbidden not in str(root/'lbost_shop_app/custom_commands.py')
assert 'data-cc-action-kind' in script and 'data-cc-add-button' in script and 'data-cc-param-type' in script
print('ok   Custom Commands vollständig: Flow, Aktionen, Parameter, Regeln, Trigger, Slash und Components V2; ohne Marketplace')
