"""Persistent isolated automation engine for LBoost Shop."""
from __future__ import annotations
import time
from typing import Any
from lbost_shop_app import db

KINDS={"messages","responses","announcements"}
TABLES={"messages":"automated_messages","responses":"auto_responses","announcements":"automatic_announcements"}


def ensure_schema(settings)->None:
    with db._gesichert(settings) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS automated_messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,channel_id INTEGER NOT NULL,
          title TEXT NOT NULL DEFAULT '',content TEXT NOT NULL,color TEXT NOT NULL DEFAULT '#5865f2',
          image_url TEXT NOT NULL DEFAULT '',send_at INTEGER NOT NULL,repeat_minutes INTEGER NOT NULL DEFAULT 0,
          next_run INTEGER NOT NULL,delete_after INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,
          last_sent INTEGER NOT NULL DEFAULT 0,created_by INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auto_responses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,trigger TEXT NOT NULL,response TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '',color TEXT NOT NULL DEFAULT '#5865f2',image_url TEXT NOT NULL DEFAULT '',
          exact INTEGER NOT NULL DEFAULT 0,cooldown_seconds INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,
          created_by INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS automatic_announcements(
          id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,channel_id INTEGER NOT NULL,
          title TEXT NOT NULL DEFAULT '',content TEXT NOT NULL,color TEXT NOT NULL DEFAULT '#5865f2',
          image_url TEXT NOT NULL DEFAULT '',interval_minutes INTEGER NOT NULL,first_delay_minutes INTEGER NOT NULL DEFAULT 0,
          next_run INTEGER NOT NULL,mention_role_id INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,
          last_sent INTEGER NOT NULL DEFAULT 0,created_by INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS automation_migrations(guild_id INTEGER PRIMARY KEY,migrated_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_automated_messages_due ON automated_messages(enabled,next_run);
        CREATE INDEX IF NOT EXISTS idx_auto_responses_guild ON auto_responses(guild_id,enabled);
        CREATE INDEX IF NOT EXISTS idx_announcements_due ON automatic_announcements(enabled,next_run);
        """)


def list_items(settings,guild_id:int,kind:str)->list[dict]:
    ensure_schema(settings);table=TABLES[kind]
    order="trigger COLLATE NOCASE" if kind=="responses" else "next_run"
    with db._gesichert(settings) as conn:rows=conn.execute(f"SELECT * FROM {table} WHERE guild_id=? ORDER BY {order}",(guild_id,)).fetchall()
    return [dict(row) for row in rows]


def get(settings,guild_id:int,kind:str,item_id:int)->dict|None:
    ensure_schema(settings);table=TABLES[kind]
    with db._gesichert(settings) as conn:row=conn.execute(f"SELECT * FROM {table} WHERE guild_id=? AND id=?",(guild_id,item_id)).fetchone()
    return dict(row) if row else None


def save_response(settings,guild_id:int,data:dict,actor:int)->int:
    ensure_schema(settings);now=int(time.time());item_id=int(data.get("id") or 0)
    values=(str(data.get("trigger") or "")[:200],str(data.get("response") or "")[:1900],str(data.get("title") or "")[:200],str(data.get("color") or "#5865f2")[:7],str(data.get("image_url") or "")[:600],int(bool(data.get("exact"))),max(0,min(86400,int(data.get("cooldown_seconds") or 0))),int(bool(data.get("enabled",True))))
    with db._gesichert(settings) as conn:
        if item_id:
            cursor=conn.execute("UPDATE auto_responses SET trigger=?,response=?,title=?,color=?,image_url=?,exact=?,cooldown_seconds=?,enabled=?,updated_at=? WHERE guild_id=? AND id=?",(*values,now,guild_id,item_id));
            if not cursor.rowcount:raise ValueError("Automatisch antwoord niet gevonden.")
            return item_id
        cursor=conn.execute("INSERT INTO auto_responses(guild_id,trigger,response,title,color,image_url,exact,cooldown_seconds,enabled,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(guild_id,*values,actor,now,now));return int(cursor.lastrowid)


def save_message(settings,guild_id:int,data:dict,actor:int)->int:
    ensure_schema(settings);now=int(time.time());item_id=int(data.get("id") or 0);send_at=max(now+1,int(data.get("send_at") or now+60))
    values=(int(data.get("channel_id") or 0),str(data.get("title") or "")[:200],str(data.get("content") or "")[:3900],str(data.get("color") or "#5865f2")[:7],str(data.get("image_url") or "")[:600],send_at,max(0,min(525600,int(data.get("repeat_minutes") or 0))),send_at,max(0,min(86400,int(data.get("delete_after") or 0))),int(bool(data.get("enabled",True))))
    with db._gesichert(settings) as conn:
        if item_id:
            cursor=conn.execute("UPDATE automated_messages SET channel_id=?,title=?,content=?,color=?,image_url=?,send_at=?,repeat_minutes=?,next_run=?,delete_after=?,enabled=?,updated_at=? WHERE guild_id=? AND id=?",(*values,now,guild_id,item_id));
            if not cursor.rowcount:raise ValueError("Geautomatiseerd bericht niet gevonden.")
            return item_id
        cursor=conn.execute("INSERT INTO automated_messages(guild_id,channel_id,title,content,color,image_url,send_at,repeat_minutes,next_run,delete_after,enabled,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(guild_id,*values,actor,now,now));return int(cursor.lastrowid)


def save_announcement(settings,guild_id:int,data:dict,actor:int)->int:
    ensure_schema(settings);now=int(time.time());item_id=int(data.get("id") or 0);delay=max(0,min(525600,int(data.get("first_delay_minutes") or 0)));next_run=now+delay*60
    values=(int(data.get("channel_id") or 0),str(data.get("title") or "")[:200],str(data.get("content") or "")[:3900],str(data.get("color") or "#5865f2")[:7],str(data.get("image_url") or "")[:600],max(1,min(525600,int(data.get("interval_minutes") or 60))),delay,next_run,int(data.get("mention_role_id") or 0),int(bool(data.get("enabled",True))))
    with db._gesichert(settings) as conn:
        if item_id:
            cursor=conn.execute("UPDATE automatic_announcements SET channel_id=?,title=?,content=?,color=?,image_url=?,interval_minutes=?,first_delay_minutes=?,next_run=?,mention_role_id=?,enabled=?,updated_at=? WHERE guild_id=? AND id=?",(*values,now,guild_id,item_id));
            if not cursor.rowcount:raise ValueError("Automatische aankondiging niet gevonden.")
            return item_id
        cursor=conn.execute("INSERT INTO automatic_announcements(guild_id,channel_id,title,content,color,image_url,interval_minutes,first_delay_minutes,next_run,mention_role_id,enabled,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(guild_id,*values,actor,now,now));return int(cursor.lastrowid)


def delete(settings,guild_id:int,kind:str,item_id:int)->bool:
    ensure_schema(settings);table=TABLES[kind]
    with db._gesichert(settings) as conn:cursor=conn.execute(f"DELETE FROM {table} WHERE guild_id=? AND id=?",(guild_id,item_id));return cursor.rowcount>0


def toggle(settings,guild_id:int,kind:str,item_id:int)->bool:
    ensure_schema(settings);table=TABLES[kind]
    with db._gesichert(settings) as conn:
        cursor=conn.execute(f"UPDATE {table} SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END,updated_at=? WHERE guild_id=? AND id=?",(int(time.time()),guild_id,item_id));return cursor.rowcount>0


def responses(settings,guild_id:int)->list[dict]:
    return [row for row in list_items(settings,guild_id,"responses") if row["enabled"]]


def claim_due(settings,kind:str,now:int|None=None,limit=25,guild_id:int|None=None)->list[dict]:
    """Atomically claim due jobs before Discord I/O to prevent duplicate sends."""
    ensure_schema(settings);now=int(now or time.time());table=TABLES[kind];interval="repeat_minutes" if kind=="messages" else "interval_minutes"
    with db._gesichert(settings) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if guild_id is None:rows=conn.execute(f"SELECT * FROM {table} WHERE enabled=1 AND next_run<=? ORDER BY next_run LIMIT ?",(now,limit)).fetchall()
        else:rows=conn.execute(f"SELECT * FROM {table} WHERE guild_id=? AND enabled=1 AND next_run<=? ORDER BY next_run LIMIT ?",(guild_id,now,limit)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw);minutes=int(row[interval] or 0)
            if kind=="messages" and minutes<=0:conn.execute(f"UPDATE {table} SET enabled=0,last_sent=? WHERE id=? AND next_run=?",(now,row["id"],row["next_run"]))
            else:conn.execute(f"UPDATE {table} SET next_run=?,last_sent=? WHERE id=? AND next_run=?",(now+max(1,minutes)*60,now,row["id"],row["next_run"]))
            result.append(row)
        conn.commit();return result


def migrate_legacy(settings,guild_id:int,legacy:dict,actor=0)->int:
    """Move old JSON automation into the new tables exactly once, without deleting it."""
    ensure_schema(settings)
    with db._gesichert(settings) as conn:
        if conn.execute("SELECT 1 FROM automation_migrations WHERE guild_id=?",(guild_id,)).fetchone():return 0
    count=0
    for item in legacy.get("auto_responses_json",[]) if isinstance(legacy.get("auto_responses_json"),list) else []:
        if isinstance(item,dict) and item.get("trigger") and item.get("response"):
            save_response(settings,guild_id,{**item,"enabled":True},actor);count+=1
    for item in legacy.get("announcements_json",[]) if isinstance(legacy.get("announcements_json"),list) else []:
        if isinstance(item,dict) and item.get("channel_id") and item.get("content"):
            save_announcement(settings,guild_id,{**item,"interval_minutes":item.get("interval_minutes") or 1440,"first_delay_minutes":0,"enabled":True},actor);count+=1
    with db._gesichert(settings) as conn:conn.execute("INSERT OR IGNORE INTO automation_migrations(guild_id,migrated_at) VALUES(?,?)",(guild_id,int(time.time())))
    return count
