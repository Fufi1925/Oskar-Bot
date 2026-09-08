"""Public community ideas with authenticated participation and owner moderation."""
from __future__ import annotations
import os, time
import aiosqlite
import discord
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_bot
from utils import ideas_store as store, emoji
from utils.panels import Panel

router=APIRouter()

def need_user(data):
    uid=str(data.get("user_id") or data.get("actor") or "").strip()
    if not uid.isdigit(): raise HTTPException(401,"Melde dich mit Discord an.")
    reason=store.blocked(uid)
    if reason is not None: raise HTTPException(403, f"Du bist vom Ideen-System ausgeschlossen: {reason or 'Keine Begründung angegeben.'}")
    return uid

async def send_dm(bot,user_id,title,text,link=""):
    try:
        user=bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
        panel=Panel(f"{emoji.STAR} {title}",text,"University Bot Ideen",tone="success" if "angenommen" in title.lower() else "warning")
        if link:
            panel.add_item(discord.ui.ActionRow(discord.ui.Button(label="Belohnung einlösen",url=link)))
        await user.send(view=panel)
        return "sent"
    except Exception:return "failed"

@router.get("")
async def list_ideas(status:str="",sort:str="new",q:str="",offset:int=0,actor:str=""):
    return {"ideas":store.listing(status,sort,q,50,offset,actor)}

@router.get("/me")
async def my_ideas(actor:str=""):
    if not actor.isdigit(): raise HTTPException(401,"Melde dich mit Discord an.")
    ideas,rewards=store.mine(actor); return {"ideas":ideas,"rewards":rewards}

@router.get("/rewards/servers")
async def reward_servers(actor:str="",bot=Depends(get_bot)):
    if not actor.isdigit(): raise HTTPException(401,"Melde dich mit Discord an.")
    result=[]
    for guild in bot.guilds:
        member=guild.get_member(int(actor))
        if member and (guild.owner_id==int(actor) or member.guild_permissions.manage_guild):
            result.append({"id":str(guild.id),"name":guild.name,"icon":str(guild.icon.url) if guild.icon else None})
    return {"servers":result}

@router.get("/admin/overview")
async def admin_overview(admin:bool=False,status:str="",q:str=""):
    if not admin:raise HTTPException(403,"Nur Bot-Owner dürfen Ideen verwalten.")
    ideas,counts,blacklisted=store.admin_overview(status,q)
    return {"ideas":ideas,"counts":counts,"blacklisted":blacklisted}

@router.get("/{idea_id}")
async def idea_detail(idea_id:str,actor:str=""):
    item=store.get(idea_id,actor)
    if not item: raise HTTPException(404,"Idee nicht gefunden.")
    return {"idea":item}

@router.post("")
async def submit(data:dict):
    uid=need_user(data); title=str(data.get("title") or "").strip(); desc=str(data.get("description") or "").strip()
    if len(title)<3 or len(title)>100: raise HTTPException(400,"Der Titel muss 3 bis 100 Zeichen lang sein.")
    if len(desc)<10 or len(desc)>2000: raise HTTPException(400,"Die Beschreibung muss 10 bis 2000 Zeichen lang sein.")
    images=[]
    for raw in (data.get("images") or [])[:3]:
        value=str(raw)
        if value.startswith("https://"):
            images.append(value[:500])
        elif value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,", "data:image/gif;base64,")):
            images.append(value)
    if sum(len(value) for value in images) > 11_200_000:
        raise HTTPException(400,"Die Referenzbilder dürfen zusammen höchstens 8 MB groß sein.")
    return {"idea":store.create(uid,data.get("user_name") or "Discord-Nutzer",data.get("avatar") or "",title,desc,images)}

@router.post("/{idea_id}/vote")
async def cast_vote(idea_id:str,data:dict):
    uid=need_user(data)
    try:item=store.vote(idea_id,uid,int(data.get("value",0)))
    except ValueError:raise HTTPException(400,"Ungültige Stimme.")
    if not item:raise HTTPException(404,"Idee nicht gefunden.")
    return {"idea":item}

@router.post("/{idea_id}/comments")
async def add_comment(idea_id:str,data:dict):
    uid=need_user(data)
    try:item=store.comment(idea_id,uid,data.get("user_name") or "Discord-Nutzer",data.get("avatar") or "",data.get("body") or "")
    except ValueError:raise HTTPException(400,"Der Kommentar darf nicht leer und höchstens 1000 Zeichen lang sein.")
    if not item:raise HTTPException(404,"Idee nicht gefunden.")
    return {"idea":item}

@router.post("/{idea_id}/admin")
async def admin_decide(idea_id:str,data:dict,bot=Depends(get_bot)):
    if not data.get("admin"):raise HTTPException(403,"Nur Bot-Owner dürfen Ideen verwalten.")
    try:item=store.decide(idea_id,str(data.get("status")),data.get("note") or "",bool(data.get("reward")))
    except ValueError:raise HTTPException(400,"Ungültiger Status.")
    if not item:raise HTTPException(404,"Idee nicht gefunden.")
    status=item["status"]
    accepted=status in {"planned","working","implemented"}
    title="Deine Idee wurde angenommen" if accepted else "Update zu deiner Idee"
    if status=="rejected":title="Deine Idee wurde abgelehnt"
    if item.get("reward_granted"):title="Deine Idee wurde angenommen und belohnt"
    link=(os.getenv("DASHBOARD_PUBLIC_URL") or os.getenv("NEXTAUTH_URL") or "https://universtiy-bot.up.railway.app").rstrip("/")+"/ideas/me?tab=rewards"
    status_name={"open":"Offen","planned":"Geplant","working":"In Bearbeitung","implemented":"Umgesetzt","rejected":"Abgelehnt","needs_info":"Informationen benötigt"}.get(status,status)
    text=f"**{item['title']}**\n\nStatus: **{status_name}**"
    if item.get("admin_note"):text+=f"\n\n{item['admin_note']}"
    await send_dm(bot,item["user_id"],title,text,link if item.get("reward_granted") else "")
    return {"idea":item}

@router.delete("/{idea_id}")
async def admin_delete(idea_id:str,admin:bool=False):
    if not admin:raise HTTPException(403,"Nur Bot-Owner dürfen Ideen löschen.")
    if not store.delete(idea_id):raise HTTPException(404,"Idee nicht gefunden.")
    return {"status":"deleted"}

@router.post("/admin/blacklist")
async def blacklist(data:dict):
    if not data.get("admin"):raise HTTPException(403,"Nur Bot-Owner dürfen Nutzer sperren.")
    uid=str(data.get("target_user_id") or "")
    if not uid.isdigit():raise HTTPException(400,"Ungültige Nutzer-ID.")
    store.blacklist(uid,data.get("reason") or "",data.get("actor") or "owner",bool(data.get("enabled",True)))
    return {"status":"blocked" if data.get("enabled",True) else "unblocked"}

@router.post("/{idea_id}/reward")
async def claim_reward(idea_id:str,data:dict,bot=Depends(get_bot)):
    uid=need_user(data); gid=str(data.get("guild_id") or "")
    guild=bot.get_guild(int(gid)) if gid.isdigit() else None
    member=guild.get_member(int(uid)) if guild else None
    if not guild or not member or not (guild.owner_id==int(uid) or member.guild_permissions.manage_guild):
        raise HTTPException(403,"Du verwaltest diesen Server nicht oder University Bot ist dort nicht installiert.")
    try:expires=store.claim(idea_id,uid,gid)
    except RuntimeError:raise HTTPException(409,"Diese Belohnung wurde bereits eingelöst.")
    except ValueError:raise HTTPException(404,"Belohnung nicht gefunden.")
    # Guild-scoped premium: permanent admin grants keep expires_at NULL.
    db=await aiosqlite.connect("db/admin_config.db")
    await db.execute("CREATE TABLE IF NOT EXISTS premium_guilds(guild_id INTEGER PRIMARY KEY,granted_at INTEGER,expires_at INTEGER)")
    try:await db.execute("ALTER TABLE premium_guilds ADD COLUMN expires_at INTEGER")
    except Exception:pass
    await db.execute("INSERT OR REPLACE INTO premium_guilds(guild_id,granted_at,expires_at) VALUES(?,?,?)",(guild.id,int(time.time()),expires))
    await db.commit(); await db.close()
    from utils import feature_gates
    await feature_gates.refresh_premium_guilds()
    return {"status":"claimed","guild_id":gid,"expires_at":expires}
