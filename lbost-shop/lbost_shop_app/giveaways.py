"""Complete isolated giveaway store shared by LBoost dashboard and Discord."""
from __future__ import annotations
import math, random, time
from datetime import timezone
from typing import Any
from lbost_shop_app import db

DEFAULT_TITLE = "Gewinnspiel"
DEFAULT_DESCRIPTION = "**{prize}**\n\nDrücke den Knopf, um teilzunehmen.\n**Gewinner:** {winners}\n**Endet:** {ends}"
DEFAULT_MESSAGES = {
 "msg_joined":"Du bist dabei! Teilnehmer: **{entries}**",
 "msg_left":"Du nimmst nicht mehr teil. Teilnehmer: **{entries}**",
 "msg_ended":"Dieses Gewinnspiel ist bereits beendet.",
 "msg_denied":"Du erfüllst die Bedingungen noch nicht:",
 "msg_winner_dm":"**{prize}**\n\nServer: **{server}**",
 "msg_announce":"Glückwunsch {winners_mentions}! Ihr gewinnt **{prize}**.",
 "msg_no_entries":"Niemand hat am Gewinnspiel für **{prize}** teilgenommen.",
}
TEXT_LIMITS = {"title":200,"description":2000,"button_label":80,"button_emoji":100,"image_url":600,
 **{k:(1000 if k in {"msg_winner_dm","msg_announce"} else 500) for k in DEFAULT_MESSAGES}}
NUMBER_LIMITS = {"min_messages":(0,1_000_000),"min_level":(0,1000),"min_account_days":(0,3650),"min_member_days":(0,3650)}
FLAGS=("dm_winners","dm_host","allow_leave")

def fill(text: str, values: dict[str,Any]) -> str:
 out=str(text or "")
 for key,value in values.items(): out=out.replace("{"+key+"}",str(value))
 return out

def values(record:dict,entries:int=0,**extra)->dict:
 end=int(record.get("ends_at") or 0)
 data={"prize":record.get("prize") or "","winners":record.get("winners") or 1,"entries":entries,
       "ends":f"<t:{end}:R>" if end else "—","ends_full":f"<t:{end}:F>" if end else "—",
       "host":f"<@{record.get('host_id')}>" if record.get("host_id") else "—"}
 data.update(extra); return data

def message(record:dict,key:str,data:dict)->str: return fill(record.get(key) or DEFAULT_MESSAGES[key],data)

def clean(payload:dict,partial=False)->dict:
 out={}
 for key,limit in TEXT_LIMITS.items():
  if partial and key not in payload: continue
  out[key]=str(payload.get(key) or "")[:limit]
 for key,(low,high) in NUMBER_LIMITS.items():
  if partial and key not in payload: continue
  try: out[key]=max(low,min(high,int(payload.get(key) or 0)))
  except: out[key]=0
 for key in ("required_role_id","blocked_role_id"):
  if partial and key not in payload: continue
  raw=str(payload.get(key) or ""); out[key]=int(raw) if raw.isdigit() else 0
 for key in FLAGS:
  if partial and key not in payload: continue
  out[key]=int(bool(payload.get(key,True)))
 if not partial or "colour" in payload:
  try: out["colour"]=int(str(payload.get("colour") or "f59e0b").lstrip("#"),16) if isinstance(payload.get("colour"),str) else int(payload.get("colour") or 0xF59E0B)
  except: out["colour"]=0xF59E0B
 return out

def get(guild_id:int,message_id:int,settings)->dict|None:
 with db._gesichert(settings) as conn: row=conn.execute("SELECT * FROM giveaways WHERE guild_id=? AND message_id=?",(guild_id,message_id)).fetchone()
 return dict(row) if row else None

def list_all(guild_id:int,settings,limit=50)->list[dict]:
 with db._gesichert(settings) as conn: rows=conn.execute("SELECT * FROM giveaways WHERE guild_id=? ORDER BY ends_at DESC LIMIT ?",(guild_id,limit)).fetchall()
 return [dict(r) for r in rows]

def create(record:dict,settings)->None:
 fields=["message_id","guild_id","channel_id","prize","winners","ends_at","status","winner_ids","required_role_id","host_id","start_time","title","description","colour","button_label","button_emoji","image_url","blocked_role_id","min_messages","min_level","min_account_days","min_member_days","dm_winners","dm_host","allow_leave",*DEFAULT_MESSAGES]
 with db._gesichert(settings) as conn:
  conn.execute(f"INSERT INTO giveaways({','.join(fields)}) VALUES({','.join('?'*len(fields))})",[record.get(f,0 if f not in {"status","winner_ids","prize","title","description","button_label","button_emoji","image_url",*DEFAULT_MESSAGES} else ("active" if f=="status" else "[]" if f=="winner_ids" else "")) for f in fields])

def update(guild_id:int,message_id:int,payload:dict,settings)->dict|None:
 allowed=set(TEXT_LIMITS)|set(NUMBER_LIMITS)|set(FLAGS)|{"required_role_id","blocked_role_id","colour","prize","winners","ends_at","status"}
 values_={k:v for k,v in payload.items() if k in allowed}
 if not values_: return get(guild_id,message_id,settings)
 with db._gesichert(settings) as conn:
  conn.execute("UPDATE giveaways SET "+",".join(f"{k}=?" for k in values_)+" WHERE guild_id=? AND message_id=?",[*values_.values(),guild_id,message_id])
 return get(guild_id,message_id,settings)

def entries(message_id:int,settings)->list[int]:
 with db._gesichert(settings) as conn: rows=conn.execute("SELECT user_id FROM giveaway_entries WHERE message_id=? ORDER BY joined_at",(message_id,)).fetchall()
 return [int(r["user_id"]) for r in rows]

def toggle_entry(message_id:int,user_id:int,allow_leave:bool,settings)->tuple[str,int]:
 with db._gesichert(settings) as conn:
  exists=conn.execute("SELECT 1 FROM giveaway_entries WHERE message_id=? AND user_id=?",(message_id,user_id)).fetchone()
  if exists:
   if not allow_leave: result="already"
   else: conn.execute("DELETE FROM giveaway_entries WHERE message_id=? AND user_id=?",(message_id,user_id)); result="left"
  else: conn.execute("INSERT INTO giveaway_entries(message_id,user_id,joined_at) VALUES(?,?,?)",(message_id,user_id,int(time.time()))); result="joined"
  total=conn.execute("SELECT COUNT(*) n FROM giveaway_entries WHERE message_id=?",(message_id,)).fetchone()["n"]
 return result,int(total)

def boosts(message_id:int,settings)->dict[int,dict]:
 with db._gesichert(settings) as conn: rows=conn.execute("SELECT user_id,weight,guaranteed,note FROM giveaway_boosts WHERE message_id=?",(message_id,)).fetchall()
 return {int(r["user_id"]):{"weight":max(1,int(r["weight"])),"guaranteed":bool(r["guaranteed"]),"note":r["note"] or ""} for r in rows}

def set_boost(message_id:int,user_id:int,mode:str,weight:int,note:str,set_by:int,settings)->None:
 with db._gesichert(settings) as conn:
  if mode=="clear": conn.execute("DELETE FROM giveaway_boosts WHERE message_id=? AND user_id=?",(message_id,user_id)); return
  weight=max(1,min(1_000_000,int(weight or 1))); guaranteed=mode=="guaranteed"
  conn.execute("INSERT INTO giveaway_boosts(message_id,user_id,weight,guaranteed,note,set_by,set_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(message_id,user_id) DO UPDATE SET weight=excluded.weight,guaranteed=excluded.guaranteed,note=excluded.note,set_by=excluded.set_by,set_at=excluded.set_at",(message_id,user_id,weight,int(guaranteed),note[:200],set_by,int(time.time())))

def past_winners(message_id:int,settings)->list[int]:
 with db._gesichert(settings) as conn: rows=conn.execute("SELECT user_id FROM giveaway_winners WHERE message_id=?",(message_id,)).fetchall()
 return [int(r["user_id"]) for r in rows]

def record_winners(message_id:int,users:list[int],settings,reroll=False)->None:
 with db._gesichert(settings) as conn:
  for uid in users: conn.execute("INSERT OR REPLACE INTO giveaway_winners(message_id,user_id,won_at,rerolled) VALUES(?,?,?,?)",(message_id,uid,int(time.time()),int(reroll)))

def weighted_sample(pool:dict[int,int],count:int)->list[int]:
 pool={u:max(1,int(w)) for u,w in pool.items()}; picked=[]
 while pool and len(picked)<count:
  target=random.uniform(0,sum(pool.values())); run=0; chosen=next(iter(pool))
  for uid,weight in pool.items():
   run+=weight
   if run>=target: chosen=uid; break
  picked.append(chosen); del pool[chosen]
 return picked

def draw(message_id:int,count:int,settings,exclude_past=False,eligible:set[int]|None=None)->list[int]:
 candidates=entries(message_id,settings)
 if eligible is not None: candidates=[u for u in candidates if u in eligible]
 if exclude_past:
  candidates=[u for u in candidates if u not in set(past_winners(message_id,settings))]
 if not candidates:return []
 count=min(max(1,count),len(candidates)); tuning=boosts(message_id,settings)
 sure=[u for u in candidates if tuning.get(u,{}).get("guaranteed")]; random.shuffle(sure); winners=sure[:count]
 if len(winners)<count: winners+=weighted_sample({u:tuning.get(u,{}).get("weight",1) for u in candidates if u not in winners},count-len(winners))
 return winners

def chances(message_id:int,winners:int,settings)->dict[int,float]:
 ids=entries(message_id,settings); tuning=boosts(message_id,settings); sure=[u for u in ids if tuning.get(u,{}).get("guaranteed")]; slots=max(0,winners-len(sure)); pool=[u for u in ids if u not in sure]; total=sum(tuning.get(u,{}).get("weight",1) for u in pool) or 1
 return {u:(100.0 if u in sure else min(100.0,tuning.get(u,{}).get("weight",1)/total*slots*100) if slots else 0.0) for u in ids}

def mark_ended(message_id:int,settings)->bool:
 with db._gesichert(settings) as conn: cur=conn.execute("UPDATE giveaways SET status='ended' WHERE message_id=? AND status IN ('active','ending')",(message_id,))
 return bool(cur.rowcount)

def delete(guild_id:int,message_id:int,settings)->None:
 with db._gesichert(settings) as conn:
  conn.execute("DELETE FROM giveaways WHERE guild_id=? AND message_id=?",(guild_id,message_id))
  for table in ("giveaway_entries","giveaway_winners","giveaway_boosts","giveaway_dms"): conn.execute(f"DELETE FROM {table} WHERE message_id=?",(message_id,))

def claim_dm(message_id:int,user_id:int,kind:str,settings)->bool:
 with db._gesichert(settings) as conn: cur=conn.execute("INSERT OR IGNORE INTO giveaway_dms(message_id,user_id,kind,sent_at) VALUES(?,?,?,?)",(message_id,user_id,kind,int(time.time())))
 return bool(cur.rowcount)

def activity(guild_id:int,user_id:int,settings)->tuple[int,int]:
 with db._gesichert(settings) as conn: row=conn.execute("SELECT messages,xp FROM giveaway_activity WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()
 if not row:return 0,0
 return int(row["messages"]),int(math.sqrt(int(row["xp"])/100))

def add_activity(guild_id:int,user_id:int,settings)->None:
 with db._gesichert(settings) as conn: conn.execute("INSERT INTO giveaway_activity(guild_id,user_id,messages,xp) VALUES(?,?,1,15) ON CONFLICT(guild_id,user_id) DO UPDATE SET messages=messages+1,xp=xp+15",(guild_id,user_id))

def failed_requirements(record:dict,member,settings)->list[str]:
 problems=[]; roles={r.id for r in getattr(member,"roles",[])}
 required=int(record.get("required_role_id") or 0); blocked=int(record.get("blocked_role_id") or 0)
 if required and required not in roles: problems.append(f"Benötigte Rolle: <@&{required}>")
 if blocked and blocked in roles: problems.append(f"Ausgeschlossene Rolle: <@&{blocked}>")
 messages,level=activity(int(getattr(getattr(member,"guild",None),"id",0) or record.get("guild_id") or 0),member.id,settings)
 if messages<int(record.get("min_messages") or 0): problems.append(f"Mindestens {record['min_messages']} Nachrichten")
 if level<int(record.get("min_level") or 0): problems.append(f"Mindestens Level {record['min_level']}")
 now=time.time(); created=getattr(member,"created_at",None); joined=getattr(member,"joined_at",None)
 if created and (now-created.replace(tzinfo=timezone.utc).timestamp())/86400<int(record.get("min_account_days") or 0): problems.append(f"Account mindestens {record['min_account_days']} Tage alt")
 if joined and (now-joined.replace(tzinfo=timezone.utc).timestamp())/86400<int(record.get("min_member_days") or 0): problems.append(f"Mindestens {record['min_member_days']} Tage auf dem Server")
 return problems

def requirement_lines(record:dict)->list[str]:
 out=[]
 if record.get("required_role_id"):out.append(f"Rolle <@&{record['required_role_id']}>")
 if record.get("blocked_role_id"):out.append(f"Nicht <@&{record['blocked_role_id']}>")
 if record.get("min_messages"):out.append(f"{record['min_messages']} Nachrichten")
 if record.get("min_level"):out.append(f"Level {record['min_level']}")
 if record.get("min_account_days"):out.append(f"Account {record['min_account_days']} Tage")
 if record.get("min_member_days"):out.append(f"{record['min_member_days']} Tage Mitglied")
 return out
