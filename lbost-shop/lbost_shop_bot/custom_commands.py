"""Full University-style Custom Commands runtime for isolated LBoost data."""
from __future__ import annotations
import asyncio, logging, re, time
from datetime import datetime
from typing import Any
import discord
from discord import app_commands
from lbost_shop_app import custom_commands as store

logger=logging.getLogger("lbost-shop-custom-commands")


def colour(value: Any) -> int:
    try:return int(str(value or "#2563eb").lstrip("#"),16)
    except (TypeError,ValueError):return 0x2563EB


class CustomCommandsService:
    def __init__(self,bot):
        self.bot=bot;self.settings=bot.settings
        self._commands:dict[int,dict[str,dict]]={};self._slash_names:dict[int,set[str]]={}
        self._cooldowns:dict[tuple[int,str,int],float]={};self._watch_task:asyncio.Task|None=None
        self._signatures:dict[int,tuple[int,int]]={}

    async def start(self):
        store.ensure_schema(self.settings);await self.refresh(sync_slash=False)
        self._signatures=store.signatures(self.settings)
        self._watch_task=asyncio.create_task(self._watch())
        logger.info("Aangepaste opdrachten geladen voor %s gilden",len(self._commands))

    async def close(self):
        if self._watch_task:self._watch_task.cancel()

    async def _watch(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(4)
                current=store.signatures(self.settings)
                for guild_id in set(current)|set(self._signatures):
                    if current.get(guild_id)!=self._signatures.get(guild_id):
                        await self.refresh(guild_id,sync_slash=True)
                self._signatures=current
            except asyncio.CancelledError:raise
            except Exception:logger.exception("Vernieuwen van aangepaste opdracht mislukt")

    async def refresh(self,guild_id:int|None=None,*,sync_slash=False):
        rows=store.list_all(self.settings,guild_id)
        if guild_id is None:
            fresh:dict[int,dict[str,dict]]={}
            for row in rows:fresh.setdefault(int(row["guild_id"]),{})[row["name"].lower()]=row
            self._commands=fresh
            for current in fresh:await self._refresh_slash(current,sync=False)
        else:
            guild_id=int(guild_id);mapped={row["name"].lower():row for row in rows}
            if mapped:self._commands[guild_id]=mapped
            else:self._commands.pop(guild_id,None)
            await self._refresh_slash(guild_id,sync=sync_slash)

    async def _refresh_slash(self,guild_id:int,*,sync:bool):
        tree=self.bot.tree;guild=discord.Object(id=guild_id)
        desired={name for name,entry in self._commands.get(guild_id,{}).items() if entry.get("use_slash") and entry.get("config",{}).get("enabled",True)}
        for old in self._slash_names.get(guild_id,set()):tree.remove_command(old,guild=guild)
        for name in desired:tree.add_command(self._make_slash_command(guild_id,name),guild=guild,override=True)
        self._slash_names[guild_id]=desired
        if sync:
            try:await tree.sync(guild=guild)
            except Exception:logger.exception("Aangepaste slash-synchronisatie mislukt voor gilde %s",guild_id)

    def _make_slash_command(self,guild_id:int,name:str)->app_commands.Command:
        entry=self._commands.get(guild_id,{}).get(name,{})
        configured=entry.get("config",{}).get("parameters",[]);valid=[];seen=set()
        type_names={"string":"str","integer":"int","boolean":"bool","user":"discord.Member","channel":"discord.TextChannel","role":"discord.Role"}
        for parameter in configured[:10]:
            option=str(parameter.get("name", ""))
            if re.fullmatch(r"[a-z][a-z0-9_]{0,31}",option) and option not in seen:seen.add(option);valid.append(parameter)
        async def runner(interaction:discord.Interaction,values:dict):
            if not self.bot.feature(guild_id,"custom_commands").get("enabled",True):
                await interaction.response.send_message("Aangepaste opdrachten zijn uitgeschakeld op deze server.",ephemeral=True);return
            current=self._commands.get(guild_id,{}).get(name)
            if current is None or not current.get("use_slash"):
                await interaction.response.send_message("Deze aangepaste opdracht is niet langer beschikbaar.",ephemeral=True);return
            if not self._allowed(current,interaction.user):
                await interaction.response.send_message("U mag deze opdracht niet gebruiken.",ephemeral=True);return
            if self._on_cooldown(guild_id,name,interaction.user.id,current):
                await interaction.response.send_message("Deze opdracht heeft nog een cooldown voor je.",ephemeral=True);return
            variables={key:value for key,value in values.items() if key!="interaction" and value is not None}
            arguments=" ".join(getattr(value,"mention",str(value)) for value in variables.values());sent=False
            async def send(text,action=None):
                nonlocal sent
                view=self._view(action or {},text,interaction.user,interaction.guild,interaction.channel,arguments,variables)
                ephemeral=bool((action or {}).get("ephemeral"))
                if not sent:await interaction.response.send_message(view=view,ephemeral=ephemeral);sent=True
                else:await interaction.followup.send(view=view,ephemeral=ephemeral)
            await self._run_actions(current,interaction.user,interaction.guild,interaction.channel,arguments,send,variables)
            if not sent and not interaction.response.is_done():await interaction.response.send_message("Commando uitgevoerd.",ephemeral=True)
        if valid:
            declarations=[]
            for parameter in valid:
                annotation=type_names.get(parameter.get("type"),"str");suffix="" if parameter.get("required") else " = None"
                declarations.append(f"{parameter['name']}: {annotation}{suffix}")
            source="async def callback(interaction: discord.Interaction, *, "+", ".join(declarations)+"):\n    return await runner(interaction, locals())"
            namespace={"discord":discord,"runner":runner};exec(source,namespace);callback=namespace["callback"]
        else:
            async def callback(interaction:discord.Interaction,args:str=""):await runner(interaction,{"args":args})
        command=app_commands.Command(name=name,description=str(entry.get("config",{}).get("description") or f"Custom Command: {name}")[:100],callback=callback)
        for parameter in valid:
            if parameter["name"] in command._params:command._params[parameter["name"]].description=str(parameter.get("description") or parameter["name"])[:100]
        return command

    @staticmethod
    def _render(response:str,user,guild,channel,arguments:str,variables:dict|None=None)->str:
        rendered=(str(response or "").replace("{user}",user.mention).replace("{user_name}",user.display_name)
                  .replace("{server}",guild.name).replace("{channel}",getattr(channel,"mention","#unbekannt"))
                  .replace("{args}",arguments.strip()).replace("{date}",datetime.now().strftime("%d.%m.%Y")))
        for key,value in (variables or {}).items():
            natural=getattr(value,"mention",str(value));tokens={
                f"{{{key}}}":natural,f"{{option.{key}}}":natural,f"{{{key}:UserPing}}":natural,
                f"{{{key}:ChannelPing}}":natural,f"{{{key}:RolePing}}":natural,f"{{{key}:Username}}":natural,
                f"{{{key}:Channel}}":natural,f"{{{key}:Role}}":natural,f"{{{key}:Text}}":str(value),
                f"{{{key}:Number}}":str(value),f"{{{key}:Boolean}}":"Ja" if value is True else "Nee" if value is False else str(value)}
            for token,result in tokens.items():rendered=rendered.replace(token,result)
        return rendered

    def _allowed(self,entry:dict,member)->bool:
        config=entry.get("config",{})
        if not config.get("enabled",True):return False
        users={str(v) for v in config.get("allowed_users",[])};roles={str(v) for v in config.get("allowed_roles",[])}
        if str(member.id) in users:return True
        if roles and any(str(role.id) in roles for role in getattr(member,"roles",[])):return True
        return not users and not roles and not config.get("deny_without_role",False)

    def _on_cooldown(self,guild_id:int,name:str,user_id:int,entry:dict)->bool:
        seconds=max(0,min(86400,int(entry.get("config",{}).get("cooldown",0) or 0)))
        if not seconds:return False
        key=(guild_id,name,user_id);now=time.monotonic()
        if now<self._cooldowns.get(key,0):return True
        self._cooldowns[key]=now+seconds;return False

    def _view(self,action:dict,text:str,member,guild,channel,arguments:str,variables=None):
        embed=action.get("embed") if isinstance(action.get("embed"),dict) else {}
        enabled=bool(embed.get("enabled"));title=self._render(embed.get("title","") if enabled else "Aangepaste opdracht",member,guild,channel,arguments,variables)
        description=self._render(embed.get("description","") if enabled else text,member,guild,channel,arguments,variables)
        if enabled and text:description=f"{text}\n\n{description}" if description else text
        view=discord.ui.LayoutView(timeout=900);container=discord.ui.Container(accent_color=colour(embed.get("color") if enabled else "#5865f2"))
        content=((f"## {title}\n" if title else "")+(description or "Commando uitgevoerd."))[:3900]
        container.add_item(discord.ui.TextDisplay(content))
        image=str(embed.get("image_url") or "") if enabled else ""
        if image:
            gallery=discord.ui.MediaGallery();gallery.add_item(media=image);container.add_item(gallery)
        buttons=action.get("buttons",[]) if isinstance(action.get("buttons"),list) else []
        for offset in range(0,min(5,len(buttons)),5):
            row=discord.ui.ActionRow()
            for definition in buttons[offset:offset+5]:row.add_item(self._button(definition,guild,channel,arguments,variables))
            container.add_item(row)
        footer=str(embed.get("footer") or "") if enabled else ""
        if footer:container.add_item(discord.ui.Separator());container.add_item(discord.ui.TextDisplay(f"-# {footer}"))
        view.add_item(container);return view

    def _button(self,definition:dict,guild,channel,arguments:str,variables=None):
        styles={"blue":discord.ButtonStyle.primary,"gray":discord.ButtonStyle.secondary,"green":discord.ButtonStyle.success,"red":discord.ButtonStyle.danger}
        button=discord.ui.Button(label=str(definition.get("label") or "Klik op mij")[:80],emoji=str(definition.get("emoji") or "").strip() or None,style=styles.get(definition.get("style"),discord.ButtonStyle.primary))
        async def clicked(interaction:discord.Interaction,data=definition):
            sent=False
            async def send(text,action=None):
                nonlocal sent
                view=self._view(action or {},text,interaction.user,guild,channel,arguments,variables)
                if not sent and not interaction.response.is_done():await interaction.response.send_message(view=view,ephemeral=bool((action or {}).get("ephemeral")));sent=True
                else:await interaction.followup.send(view=view,ephemeral=bool((action or {}).get("ephemeral")));sent=True
            await self._run_actions({"response":"","config":{"actions":data.get("actions",[])}},interaction.user,guild,channel,arguments,send,variables)
            if not sent and not interaction.response.is_done():await interaction.response.send_message("Actie uitgevoerd.",ephemeral=True)
        button.callback=clicked;return button

    async def _run_actions(self,entry:dict,member,guild,channel,arguments:str,send,variables:dict|None=None):
        actions=entry.get("config",{}).get("actions") or [{"type":"reply","text":entry.get("response","")}]
        async def run(items,depth=0):
            if depth>4:return
            for action in items[:25]:
                kind=action.get("type");text=self._render(str(action.get("text", "")),member,guild,channel,arguments,variables)
                if kind=="reply" and (text or action.get("embed")):await send(text,action)
                elif kind=="dm" and text:await member.send(view=self._view(action,text,member,guild,channel,arguments,variables))
                elif kind=="send_channel" and text:
                    target=guild.get_channel(int(action.get("channel_id",0) or 0))
                    if target is not None:await target.send(view=self._view(action,text,member,guild,target,arguments,variables))
                elif kind in ("add_role","remove_role"):
                    role=guild.get_role(int(action.get("role_id",0) or 0))
                    if role is not None:
                        if kind=="add_role":await member.add_roles(role,reason="LBoost aangepaste opdracht")
                        else:await member.remove_roles(role,reason="LBoost aangepaste opdracht")
                elif kind=="condition_role":
                    role_id=int(action.get("role_id",0) or 0);has_role=any(role.id==role_id for role in getattr(member,"roles",[]))
                    await run(action.get("then",[]) if has_role else action.get("else",[]),depth+1)
        await run(actions)

    async def invocation(self,message:discord.Message):
        if message.guild is None or not message.content:return None
        configured=self._commands.get(message.guild.id)
        if not configured:return None
        prefixes=await self.bot.get_prefix(message);prefixes=[prefixes] if isinstance(prefixes,str) else prefixes
        prefix=next((item for item in sorted(prefixes or [],key=len,reverse=True) if item and message.content.startswith(item)),None)
        if prefix is not None:
            body=message.content[len(prefix):].strip();name,_,arguments=body.partition(" ");entry=configured.get(name.lower())
            if entry is not None and entry.get("use_prefix") and self._allowed(entry,message.author) and self.bot.get_command(name.lower()) is None:return name.lower(),arguments.strip(),entry
            return None
        plain=message.content.strip();lowered=plain.lower()
        for name,entry in configured.items():
            if entry.get("use_exact") and lowered==name and self._allowed(entry,message.author):return name,"",entry
        for name,entry in configured.items():
            if not entry.get("use_contains") or not self._allowed(entry,message.author):continue
            match=re.search(rf"(?<!\w){re.escape(name)}(?!\w)",plain,re.IGNORECASE)
            if match:return name,plain[match.end():].strip(),entry
        return None

    async def handle_message(self,message:discord.Message)->bool:
        if message.author.bot:return False
        if not self.bot.feature(message.guild.id,"custom_commands").get("enabled",True):return False
        try:
            found=await self.invocation(message)
            if found is None:return False
            name,arguments,entry=found
            if self._on_cooldown(message.guild.id,name,message.author.id,entry):return True
            async def send(text,action=None):await message.channel.send(view=self._view(action or {},text,message.author,message.guild,message.channel,arguments))
            await self._run_actions(entry,message.author,message.guild,message.channel,arguments,send);return True
        except Exception:
            logger.exception("Aangepaste opdracht mislukt in gilde %s",getattr(message.guild,"id","unknown"));return True
