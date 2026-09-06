#!/usr/bin/env python3
"""Custom commands: three slots, runtime refresh and placeholder relay."""
import asyncio, importlib.util, os, sys, tempfile, types
HERE=os.path.dirname(os.path.abspath(__file__));BOT=os.path.dirname(HERE);sys.path.insert(0,BOT)
from discord.ext import commands
from utils import custom_commands as store
# Load the one service file without importing the complete cogs registry.
sys.modules["core"] = types.SimpleNamespace(Cog=commands.Cog)
spec=importlib.util.spec_from_file_location("custom_commands_service",os.path.join(BOT,"cogs/events/custom_commands_service.py"))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CustomCommandsService=module.CustomCommandsService

class Sent:
 def __init__(self): self.items=[];self.id=55;self.mention='<#55>'
 async def send(self,text,**kw): self.items.append(text)
class Author:
 id=42;bot=False;mention='<@42>';display_name='Alex';roles=[]
class Guild:id=77;name='Testserver'
class Message:
 def __init__(self,text,ch):self.guild=Guild();self.author=Author();self.channel=ch;self.content=text
class Bot:
 user=object()
 async def get_prefix(self,m):return ['>']
 def get_command(self,n):return None
async def main():
 store.DB_PATH=os.path.join(tempfile.mkdtemp(),'cc.db')
 db=await store.connect()
 try:
  assert await store.save(db,77,'eins','1','test')
  assert await store.save(db,77,'zwei','2','test')
  assert await store.save(db,77,'drei','Hallo {user} in {server}: {args}','test', use_exact=True, use_contains=True, use_slash=True)
  assert not await store.save(db,77,'vier','4','test')
  assert await store.save(db,77,'drei','Hi {user_name}: {args}','test', use_exact=True, use_contains=True, use_slash=True)
  for index in range(20):
   assert await store.save(db,78,f'premium-{index}','ok','test',max_commands=20)
  assert not await store.save(db,78,'premium-20','no','test',max_commands=20)
 finally:await db.close()
 service=CustomCommandsService(Bot());await service.refresh()
 channel=Sent();await service.on_message(Message('>drei Welt',channel))
 await service.on_message(Message('drei',channel))
 await service.on_message(Message('Wo ist drei bitte',channel))
 assert channel.items==['Hi Alex: Welt','Hi Alex: ','Hi Alex: bitte'],channel.items
 slash=service._make_slash_command(77,'drei')
 assert slash.name=='drei' and slash.parameters[0].name=='args'
 options=service._reply_options({'embed':{'enabled':True,'title':'Test','description':'Hallo','color':'#2563eb'},'buttons':[{'label':'Klick','style':'blue','actions':[]}]},Author(),Guild(),channel,'')
 assert options['embed'].title=='Test' and len(options['view'].children)==1
 assert store.valid_name('regeln') and not store.valid_name('bad command')
 print('custom commands: all checks passed')
asyncio.run(main())
