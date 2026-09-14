"""Application firewall for the website, dashboard BFF and FastAPI.

Detection and blocking are deterministic. The optional Grok endpoint only
writes a recommendation and can never mutate a rule or stop an incident.
"""
from __future__ import annotations
import ipaddress
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from typing import Any

DB_PATH = os.path.join("db", "firewall.db")
RETENTION_SECONDS = 90 * 86400
_lock = threading.RLock()
_hits: dict[str, deque[float]] = defaultdict(deque)

DEFAULTS = {
    "enabled": "1", "requests_per_minute": "180", "burst_10_seconds": "60",
    "auto_block_minutes": "30", "emergency_mode": "0", "emergency_rpm": "30",
    "block_bad_bots": "1", "country_blocklist": "", "protected_paths": "/api/,/dashboard",
}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def ensure() -> None:
    with _lock, _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS firewall_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS firewall_rules(
          id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,value TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,expires_at INTEGER,created_by TEXT NOT NULL DEFAULT '',
          UNIQUE(kind,value));
        CREATE TABLE IF NOT EXISTS firewall_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,created_at INTEGER NOT NULL,ip TEXT NOT NULL,
          method TEXT NOT NULL,path TEXT NOT NULL,user_agent TEXT NOT NULL DEFAULT '',country TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL,severity TEXT NOT NULL,status INTEGER NOT NULL DEFAULT 0,
          request_count INTEGER NOT NULL DEFAULT 1,blocked INTEGER NOT NULL DEFAULT 0,
          stopped_at INTEGER,note TEXT NOT NULL DEFAULT '',ai_report TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS firewall_events_created ON firewall_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS firewall_events_ip ON firewall_events(ip,created_at DESC);
        """)
        for key, value in DEFAULTS.items():
            db.execute("INSERT OR IGNORE INTO firewall_settings(key,value) VALUES(?,?)", (key,value))
        db.execute("DELETE FROM firewall_events WHERE created_at<?", (int(time.time())-RETENTION_SECONDS,))
        db.execute("DELETE FROM firewall_rules WHERE expires_at IS NOT NULL AND expires_at<=?", (int(time.time()),))


def settings() -> dict[str, Any]:
    ensure()
    with _connect() as db: raw={r["key"]:r["value"] for r in db.execute("SELECT key,value FROM firewall_settings")}
    return {
        "enabled": raw.get("enabled")=="1", "requests_per_minute": int(raw.get("requests_per_minute","180")),
        "burst_10_seconds": int(raw.get("burst_10_seconds","60")), "auto_block_minutes": int(raw.get("auto_block_minutes","30")),
        "emergency_mode": raw.get("emergency_mode")=="1", "emergency_rpm": int(raw.get("emergency_rpm","30")),
        "block_bad_bots": raw.get("block_bad_bots")=="1",
        "country_blocklist": [x.strip().upper() for x in raw.get("country_blocklist","").split(",") if x.strip()],
        "protected_paths": [x.strip() for x in raw.get("protected_paths","").split(",") if x.strip()],
    }


def update_settings(data: dict[str, Any]) -> dict[str, Any]:
    allowed=set(DEFAULTS); current=settings()
    values={**current,**{k:v for k,v in data.items() if k in allowed}}
    for key in ("requests_per_minute","burst_10_seconds","auto_block_minutes","emergency_rpm"):
        value=int(values[key])
        if not 1<=value<=100000: raise ValueError(f"{key} liegt außerhalb des erlaubten Bereichs.")
    with _connect() as db:
        for key in allowed:
            if key not in values: continue
            value=values[key]
            if isinstance(value,bool): text="1" if value else "0"
            elif isinstance(value,list): text=",".join(str(x).strip() for x in value if str(x).strip())
            else: text=str(value)
            db.execute("INSERT OR REPLACE INTO firewall_settings(key,value) VALUES(?,?)",(key,text))
    return settings()


def _valid_network(value: str) -> str:
    return str(ipaddress.ip_network(value.strip(), strict=False))


def add_rule(kind: str,value: str,note: str="",expires_at: int|None=None,actor: str="") -> dict[str,Any]:
    if kind not in {"block","allow","user_agent","path"}: raise ValueError("Unbekannte Regelart.")
    clean=_valid_network(value) if kind in {"block","allow"} else value.strip().lower()
    if not clean: raise ValueError("Der Regelwert fehlt.")
    ensure(); now=int(time.time())
    with _connect() as db:
        db.execute("""INSERT INTO firewall_rules(kind,value,note,created_at,expires_at,created_by,enabled)
          VALUES(?,?,?,?,?,?,1) ON CONFLICT(kind,value) DO UPDATE SET note=excluded.note,
          expires_at=excluded.expires_at,created_by=excluded.created_by,enabled=1""",(kind,clean,note[:300],now,expires_at,actor))
        row=db.execute("SELECT * FROM firewall_rules WHERE kind=? AND value=?",(kind,clean)).fetchone()
    return dict(row)


def delete_rule(rule_id: int) -> bool:
    ensure()
    with _connect() as db:return db.execute("DELETE FROM firewall_rules WHERE id=?",(int(rule_id),)).rowcount>0


def rules() -> list[dict[str,Any]]:
    ensure(); now=int(time.time())
    with _connect() as db:return [dict(r) for r in db.execute("SELECT * FROM firewall_rules WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?) ORDER BY kind,created_at DESC",(now,))]


def _matches_ip(ip: str,network: str) -> bool:
    try:return ipaddress.ip_address(ip) in ipaddress.ip_network(network,strict=False)
    except ValueError:return False


def log_event(ip:str,method:str,path:str,user_agent:str,country:str,category:str,severity:str,status:int=0,count:int=1,blocked:bool=False,note:str="") -> int:
    ensure()
    with _connect() as db:
        cur=db.execute("""INSERT INTO firewall_events(created_at,ip,method,path,user_agent,country,category,severity,status,request_count,blocked,note)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(int(time.time()),ip,method[:12],path[:500],user_agent[:500],country[:8],category,severity,int(status),int(count),int(blocked),note[:500]))
        return int(cur.lastrowid)


def evaluate(ip:str,method:str,path:str,user_agent:str="",country:str="") -> dict[str,Any]:
    cfg=settings(); now=time.time(); ip=ip or "unknown"; ua=user_agent.lower(); country=country.upper()
    if not cfg["enabled"]: return {"allowed":True,"reason":"disabled"}
    active=rules()
    if any(r["kind"]=="allow" and _matches_ip(ip,r["value"]) for r in active): return {"allowed":True,"reason":"allowlist"}
    blocked_rule=next((r for r in active if r["kind"]=="block" and _matches_ip(ip,r["value"])),None)
    if blocked_rule:
        log_event(ip,method,path,user_agent,country,"blocked_ip","high",403,blocked=True,note=f"rule:{blocked_rule['id']}")
        return {"allowed":False,"status":403,"reason":"IP-Adresse durch Firewall gesperrt."}
    path_rule=next((r for r in active if r["kind"]=="path" and r["value"] in path.lower()),None)
    ua_rule=next((r for r in active if r["kind"]=="user_agent" and r["value"] in ua),None)
    bad_bot=cfg["block_bad_bots"] and any(x in ua for x in ("sqlmap","nikto","masscan","nmap","gobuster","dirbuster"))
    if path_rule or ua_rule or bad_bot or (country and country in cfg["country_blocklist"]):
        reason="bad_bot" if bad_bot else "rule_match"
        log_event(ip,method,path,user_agent,country,reason,"high",403,blocked=True)
        return {"allowed":False,"status":403,"reason":"Anfrage durch eine Firewall-Regel blockiert."}
    protected=not cfg["protected_paths"] or any(path.startswith(prefix) for prefix in cfg["protected_paths"])
    try: ipaddress.ip_address(ip); valid_ip=True
    except ValueError: valid_ip=False
    if protected and valid_ip:
        with _lock:
            q=_hits[ip]; q.append(now)
            while q and q[0]<now-60:q.popleft()
            per_min=len(q); burst=sum(1 for stamp in q if stamp>=now-10)
        limit=cfg["emergency_rpm"] if cfg["emergency_mode"] else cfg["requests_per_minute"]
        if per_min>limit or burst>cfg["burst_10_seconds"]:
            expires=int(now)+cfg["auto_block_minutes"]*60
            add_rule("block",ip,"Automatische Sperre nach Angriffserkennung",expires,"firewall")
            event=log_event(ip,method,path,user_agent,country,"rate_attack","critical",429,per_min,True,note=f"burst={burst}")
            return {"allowed":False,"status":429,"reason":"Angriff erkannt; IP vorübergehend gesperrt.","event_id":event}
    return {"allowed":True,"reason":"ok"}


def events(limit:int=200,active_only:bool=False) -> list[dict[str,Any]]:
    ensure()
    if active_only:
        # A request event is considered active only for a short observation
        # window; stopped incidents disappear immediately from the live list.
        where="WHERE stopped_at IS NULL AND severity IN ('high','critical') AND created_at>=?"
        params=(int(time.time())-900,max(1,min(1000,int(limit))))
    else:
        where=""; params=(max(1,min(1000,int(limit))),)
    with _connect() as db:return [dict(r) for r in db.execute(f"SELECT * FROM firewall_events {where} ORDER BY created_at DESC LIMIT ?",params)]


def stop_incident(event_id:int,actor:str) -> dict[str,Any]:
    ensure(); now=int(time.time())
    with _connect() as db:
        row=db.execute("SELECT * FROM firewall_events WHERE id=?",(int(event_id),)).fetchone()
        if not row: raise ValueError("Angriff nicht gefunden.")
        db.execute("UPDATE firewall_events SET stopped_at=?,note=note||? WHERE id=?",(now,f"; stopped by {actor}",int(event_id)))
    rule=add_rule("block",row["ip"],"Manuell über Angriff stoppen gesperrt",None,actor)
    return {"stopped":True,"event_id":int(event_id),"rule":rule}


def overview() -> dict[str,Any]:
    ensure(); now=int(time.time()); since=now-86400
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
        blocked=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND blocked=1",(since,)).fetchone()[0]
        critical=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND severity='critical'",(since,)).fetchone()[0]
        ips=db.execute("SELECT COUNT(DISTINCT ip) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
    return {"settings":settings(),"rules":rules(),"events":events(200),"active_incidents":events(50,True),"stats":{"events_24h":total,"blocked_24h":blocked,"critical_24h":critical,"unique_ips_24h":ips},"retention_days":90}


def save_ai_report(event_id:int,report:str) -> None:
    with _connect() as db:db.execute("UPDATE firewall_events SET ai_report=? WHERE id=?",(report[:12000],int(event_id)))
