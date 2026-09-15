"""Conservative application firewall shared by website, BFF and FastAPI.

The firewall is intentionally fail-safe for legitimate users: trusted networks,
owner identities and bot-internal calls are evaluated before every deny rule.
Automatic blocking is optional and needs several independent confirmations.
Grok is not used anywhere in detection or enforcement.
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
_strikes: dict[str, tuple[int, float]] = {}

DEFAULTS = {
    "enabled": "1",
    "auto_block_enabled": "0",
    "requests_per_minute": "900",
    "burst_10_seconds": "250",
    "confirmations_required": "3",
    "confirmation_window_seconds": "300",
    "auto_block_minutes": "15",
    "emergency_mode": "0",
    "emergency_until": "0",
    "emergency_rpm": "120",
    "block_bad_bots": "1",
    "country_blocklist": "",
    "protected_paths": "/api/,/dashboard",
    "trusted_networks": "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,169.254.0.0/16,fc00::/7,fe80::/10",
    "safety_profile_version": "3",
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
          priority INTEGER NOT NULL DEFAULT 100,
          UNIQUE(kind,value));
        CREATE TABLE IF NOT EXISTS firewall_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,created_at INTEGER NOT NULL,ip TEXT NOT NULL,
          method TEXT NOT NULL,path TEXT NOT NULL,user_agent TEXT NOT NULL DEFAULT '',country TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL,severity TEXT NOT NULL,status INTEGER NOT NULL DEFAULT 0,
          request_count INTEGER NOT NULL DEFAULT 1,blocked INTEGER NOT NULL DEFAULT 0,
          stopped_at INTEGER,note TEXT NOT NULL DEFAULT '',ai_report TEXT NOT NULL DEFAULT '',
          actor_id TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT 'external');
        CREATE INDEX IF NOT EXISTS firewall_events_created ON firewall_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS firewall_events_ip ON firewall_events(ip,created_at DESC);
        CREATE TABLE IF NOT EXISTS firewall_snapshots(
          id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,created_at INTEGER NOT NULL,
          created_by TEXT NOT NULL DEFAULT '',settings_json TEXT NOT NULL,rules_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS firewall_audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,created_at INTEGER NOT NULL,actor TEXT NOT NULL,
          action TEXT NOT NULL,target_type TEXT NOT NULL,target_id TEXT NOT NULL DEFAULT '',
          reason TEXT NOT NULL DEFAULT '',before_json TEXT,after_json TEXT,
          rolled_back_at INTEGER,rolled_back_by TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS firewall_audit_created ON firewall_audit_log(created_at DESC);
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(firewall_events)")}
        if "actor_id" not in columns: db.execute("ALTER TABLE firewall_events ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''")
        if "source" not in columns: db.execute("ALTER TABLE firewall_events ADD COLUMN source TEXT NOT NULL DEFAULT 'external'")
        rule_columns={row[1] for row in db.execute("PRAGMA table_info(firewall_rules)")}
        if "priority" not in rule_columns: db.execute("ALTER TABLE firewall_rules ADD COLUMN priority INTEGER NOT NULL DEFAULT 100")
        profile=db.execute("SELECT value FROM firewall_settings WHERE key='safety_profile_version'").fetchone()
        previous=int(profile[0]) if profile and str(profile[0]).isdigit() else 0
        for key,value in DEFAULTS.items():
            db.execute("INSERT OR IGNORE INTO firewall_settings(key,value) VALUES(?,?)",(key,value))
        if previous < 3:
            # Safe migration: do not carry the overly eager automatic blocker forward.
            db.execute("INSERT OR REPLACE INTO firewall_settings(key,value) VALUES('auto_block_enabled','0')")
            db.execute("UPDATE firewall_settings SET value='900' WHERE key='requests_per_minute' AND value IN ('180','600')")
            db.execute("UPDATE firewall_settings SET value='250' WHERE key='burst_10_seconds' AND value IN ('60','150')")
            db.execute("INSERT OR REPLACE INTO firewall_settings(key,value) VALUES('safety_profile_version','3')")
            # Remove artifacts produced when the mounted /firewall/check route
            # accidentally inspected itself. They were not real attacks.
            db.execute("DELETE FROM firewall_events WHERE path LIKE '%/firewall/check%'")
            trusted=[ipaddress.ip_network(item,strict=False) for item in DEFAULTS["trusted_networks"].split(",")]
            for row in db.execute("SELECT id,value FROM firewall_rules WHERE kind='block'").fetchall():
                try: candidate=ipaddress.ip_network(row["value"],strict=False)
                except ValueError: continue
                if any(net.version==candidate.version and (candidate.subnet_of(net) or net.subnet_of(candidate)) for net in trusted):
                    db.execute("DELETE FROM firewall_rules WHERE id=?",(row["id"],))
        now=int(time.time())
        db.execute("DELETE FROM firewall_events WHERE created_at<?",(now-RETENTION_SECONDS,))
        db.execute("DELETE FROM firewall_rules WHERE expires_at IS NOT NULL AND expires_at<=?",(now,))


def _raw_settings() -> dict[str,str]:
    ensure()
    with _connect() as db:
        return {row["key"]:row["value"] for row in db.execute("SELECT key,value FROM firewall_settings")}


def _csv(value:str, upper:bool=False) -> list[str]:
    items=[item.strip() for item in value.split(",") if item.strip()]
    return [item.upper() for item in items] if upper else items


def settings() -> dict[str,Any]:
    raw=_raw_settings()
    integer=lambda key: int(raw.get(key,DEFAULTS[key]))
    return {
        "enabled":raw.get("enabled")=="1",
        "auto_block_enabled":raw.get("auto_block_enabled")=="1",
        "requests_per_minute":integer("requests_per_minute"),
        "burst_10_seconds":integer("burst_10_seconds"),
        "confirmations_required":integer("confirmations_required"),
        "confirmation_window_seconds":integer("confirmation_window_seconds"),
        "auto_block_minutes":integer("auto_block_minutes"),
        "emergency_mode":raw.get("emergency_mode")=="1",
        "emergency_until":int(raw.get("emergency_until","0")),
        "emergency_rpm":integer("emergency_rpm"),
        "block_bad_bots":raw.get("block_bad_bots")=="1",
        "country_blocklist":_csv(raw.get("country_blocklist",""),True),
        "protected_paths":_csv(raw.get("protected_paths","")),
        "trusted_networks":_csv(raw.get("trusted_networks",DEFAULTS["trusted_networks"])),
    }


def update_settings(data:dict[str,Any]) -> dict[str,Any]:
    allowed=set(DEFAULTS)-{"safety_profile_version"}
    values={**settings(),**{key:value for key,value in data.items() if key in allowed}}
    for key in ("requests_per_minute","burst_10_seconds","confirmations_required","confirmation_window_seconds","auto_block_minutes","emergency_rpm"):
        value=int(values[key])
        if not 1<=value<=100000: raise ValueError(f"{key} liegt außerhalb des erlaubten Bereichs.")
    for network in values.get("trusted_networks",[]):
        ipaddress.ip_network(str(network).strip(),strict=False)
    with _connect() as db:
        for key in allowed:
            if key not in values: continue
            value=values[key]
            text="1" if value is True else "0" if value is False else ",".join(str(x).strip() for x in value if str(x).strip()) if isinstance(value,list) else str(value)
            db.execute("INSERT OR REPLACE INTO firewall_settings(key,value) VALUES(?,?)",(key,text))
    return settings()


def _valid_network(value:str) -> str:
    return str(ipaddress.ip_network(value.strip(),strict=False))


def _valid_user(value:str) -> str:
    clean=value.strip()
    if not clean.isdigit() or not 5<=len(clean)<=20: raise ValueError("Ungültige Discord-Nutzer-ID.")
    return clean


def add_rule(kind:str,value:str,note:str="",expires_at:int|None=None,actor:str="") -> dict[str,Any]:
    aliases={"user":"user_block","country_block":"country"}
    kind=aliases.get(kind,kind)
    if kind not in {"block","allow","user_block","user_allow","user_agent","path","country","method"}:
        raise ValueError("Unbekannte Regelart.")
    if kind in {"block","allow"}: clean=_valid_network(value)
    elif kind in {"user_block","user_allow"}: clean=_valid_user(value)
    elif kind=="country":
        clean=value.strip().upper()
        if len(clean)!=2 or not clean.isalpha(): raise ValueError("Bitte einen zweistelligen ISO-Ländercode verwenden.")
    elif kind=="method":
        clean=value.strip().upper()
        if clean not in {"GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"}: raise ValueError("Ungültige HTTP-Methode.")
    else: clean=value.strip().lower()
    if not clean: raise ValueError("Der Regelwert fehlt.")
    if kind=="user_block" and _configured_owner(clean):
        raise ValueError("Owner-IDs dürfen niemals gesperrt werden.")
    if kind=="block":
        candidate=ipaddress.ip_network(clean,strict=False)
        protected=[ipaddress.ip_network(item,strict=False) for item in settings()["trusted_networks"]]
        if any(net.version==candidate.version and (net.subnet_of(candidate) or candidate.subnet_of(net)) for net in protected):
            raise ValueError("Eigene oder vertrauenswürdige Netze dürfen nicht gesperrt werden.")
    ensure(); now=int(time.time())
    with _connect() as db:
        db.execute("""INSERT INTO firewall_rules(kind,value,note,created_at,expires_at,created_by,enabled)
          VALUES(?,?,?,?,?,?,1) ON CONFLICT(kind,value) DO UPDATE SET note=excluded.note,
          expires_at=excluded.expires_at,created_by=excluded.created_by,enabled=1""",(kind,clean,note[:300],now,expires_at,actor[:80]))
        row=db.execute("SELECT * FROM firewall_rules WHERE kind=? AND value=?",(kind,clean)).fetchone()
    return dict(row)


def delete_rule(rule_id:int) -> bool:
    ensure()
    with _connect() as db: return db.execute("DELETE FROM firewall_rules WHERE id=?",(int(rule_id),)).rowcount>0


def unban(kind:str,value:str) -> int:
    kind={"ip":"block","user":"user_block"}.get(kind,kind)
    clean=_valid_network(value) if kind=="block" else _valid_user(value) if kind=="user_block" else value.strip()
    ensure()
    with _connect() as db: removed=db.execute("DELETE FROM firewall_rules WHERE kind=? AND value=?",(kind,clean)).rowcount
    if kind=="block":
        with _lock:
            _hits.pop(value.split("/")[0],None); _strikes.pop(value.split("/")[0],None)
    return int(removed)


def rules(include_disabled:bool=False) -> list[dict[str,Any]]:
    ensure(); now=int(time.time())
    enabled="" if include_disabled else "enabled=1 AND "
    with _connect() as db:
        return [dict(row) for row in db.execute(f"SELECT * FROM firewall_rules WHERE {enabled}(expires_at IS NULL OR expires_at>?) ORDER BY priority ASC,created_at DESC",(now,))]


def _matches_ip(ip:str,network:str) -> bool:
    try:return ipaddress.ip_address(ip) in ipaddress.ip_network(network,strict=False)
    except ValueError:return False


def _trusted_network(ip:str,cfg:dict[str,Any]) -> bool:
    return any(_matches_ip(ip,network) for network in cfg["trusted_networks"])


def _configured_owner(actor_id:str) -> bool:
    raw=",".join((os.getenv("OWNER_IDS",""),os.getenv("ADMIN_IDS",""),os.getenv("BOT_OWNER_IDS","")))
    return bool(actor_id and actor_id in {item.strip() for item in raw.split(",") if item.strip()})


def log_event(ip:str,method:str,path:str,user_agent:str,country:str,category:str,severity:str,status:int=0,count:int=1,blocked:bool=False,note:str="",actor_id:str="",source:str="external") -> int:
    ensure()
    with _connect() as db:
        cur=db.execute("""INSERT INTO firewall_events(created_at,ip,method,path,user_agent,country,category,severity,status,request_count,blocked,note,actor_id,source)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(int(time.time()),ip,method[:12],path[:500],user_agent[:500],country[:8],category,severity,int(status),int(count),int(blocked),note[:500],actor_id[:30],source[:30]))
        return int(cur.lastrowid)


def evaluate(ip:str,method:str,path:str,user_agent:str="",country:str="",actor_id:str="",actor_is_owner:bool=False,trusted_internal:bool=False) -> dict[str,Any]:
    cfg=settings(); now=time.time(); ip=(ip or "unknown").strip(); ua=user_agent.lower(); country=country.upper(); actor_id=str(actor_id or "")
    if not cfg["enabled"]: return {"allowed":True,"reason":"disabled"}
    # These bypasses happen before every rule. They are never logged as attacks.
    if trusted_internal:return {"allowed":True,"reason":"trusted_internal"}
    if actor_is_owner or _configured_owner(actor_id):return {"allowed":True,"reason":"owner_bypass"}
    if _trusted_network(ip,cfg):return {"allowed":True,"reason":"trusted_network"}
    active=rules()
    if actor_id and any(r["kind"]=="user_allow" and r["value"]==actor_id for r in active):return {"allowed":True,"reason":"user_allowlist"}
    if any(r["kind"]=="allow" and _matches_ip(ip,r["value"]) for r in active):return {"allowed":True,"reason":"allowlist"}
    user_rule=next((r for r in active if r["kind"]=="user_block" and actor_id and r["value"]==actor_id),None)
    if user_rule:
        log_event(ip,method,path,user_agent,country,"blocked_user","high",403,1,True,f"rule:{user_rule['id']}",actor_id)
        return {"allowed":False,"status":403,"reason":"Nutzerkonto wurde manuell durch die Firewall gesperrt."}
    blocked_rule=next((r for r in active if r["kind"]=="block" and _matches_ip(ip,r["value"])),None)
    if blocked_rule:
        log_event(ip,method,path,user_agent,country,"blocked_ip","high",403,1,True,f"rule:{blocked_rule['id']}",actor_id)
        return {"allowed":False,"status":403,"reason":"IP-Adresse wurde manuell durch die Firewall gesperrt."}
    path_rule=next((r for r in active if r["kind"]=="path" and r["value"] in path.lower()),None)
    ua_rule=next((r for r in active if r["kind"]=="user_agent" and r["value"] in ua),None)
    country_rule=next((r for r in active if r["kind"]=="country" and r["value"]==country),None)
    method_rule=next((r for r in active if r["kind"]=="method" and r["value"]==method.upper()),None)
    bad_bot=cfg["block_bad_bots"] and any(item in ua for item in ("sqlmap","nikto","masscan","nmap","gobuster","dirbuster"))
    if path_rule or ua_rule or country_rule or method_rule or bad_bot or (country and country in cfg["country_blocklist"]):
        reason="bad_bot" if bad_bot else "rule_match"
        log_event(ip,method,path,user_agent,country,reason,"high",403,1,True,"",actor_id)
        return {"allowed":False,"status":403,"reason":"Anfrage durch eine explizite Firewall-Regel blockiert."}
    protected=not cfg["protected_paths"] or any(path.startswith(prefix) for prefix in cfg["protected_paths"])
    try: ipaddress.ip_address(ip); valid_ip=True
    except ValueError: valid_ip=False
    if not protected or not valid_ip:return {"allowed":True,"reason":"ok"}
    with _lock:
        q=_hits[ip]; q.append(now)
        while q and q[0]<now-60:q.popleft()
        per_min=len(q); burst=sum(stamp>=now-10 for stamp in q)
    emergency_active=cfg["emergency_mode"] and (not cfg["emergency_until"] or cfg["emergency_until"]>int(now))
    limit=cfg["emergency_rpm"] if emergency_active else cfg["requests_per_minute"]
    if per_min<=limit and burst<=cfg["burst_10_seconds"]:return {"allowed":True,"reason":"ok"}
    with _lock:
        previous,last=_strikes.get(ip,(0,0.0))
        confirmations=(previous if last>=now-cfg["confirmation_window_seconds"] else 0)+1
        _strikes[ip]=(confirmations,now); q.clear()
    event=log_event(ip,method,path,user_agent,country,"rate_alarm","high",0,per_min,False,f"burst={burst}; confirmation={confirmations}/{cfg['confirmations_required']}",actor_id)
    if not cfg["auto_block_enabled"] or confirmations<cfg["confirmations_required"]:
        return {"allowed":True,"reason":"rate_alarm","event_id":event,"confirmations":confirmations}
    expires=int(now)+cfg["auto_block_minutes"]*60
    rule=add_rule("block",ip,"Automatische Sperre nach mehrfach bestätigter Angriffserkennung",expires,"firewall")
    with _connect() as db:db.execute("UPDATE firewall_events SET category='rate_attack',severity='critical',status=429,blocked=1 WHERE id=?",(event,))
    with _lock:_strikes.pop(ip,None)
    return {"allowed":False,"status":429,"reason":"Mehrfach bestätigter Rate-Angriff; vorübergehend gesperrt.","event_id":event,"rule_id":rule["id"]}


def inspect(ip:str="",actor_id:str="",user_agent:str="",country:str="",path:str="/",method:str="GET") -> dict[str,Any]:
    """Dry-run a request without logging, counting, blocking or creating rules."""
    cfg=settings(); active=rules(); actor_id=str(actor_id or ""); country=country.upper(); ua=user_agent.lower()
    if not cfg["enabled"]:return {"allowed":True,"reason":"disabled","dry_run":True}
    if _configured_owner(actor_id):return {"allowed":True,"reason":"owner_bypass","dry_run":True}
    if _trusted_network(ip,cfg):return {"allowed":True,"reason":"trusted_network","dry_run":True}
    for kind,reason,match in (
        ("user_allow","user_allowlist",lambda r:actor_id and r["value"]==actor_id),
        ("allow","allowlist",lambda r:_matches_ip(ip,r["value"])),
        ("user_block","blocked_user",lambda r:actor_id and r["value"]==actor_id),
        ("block","blocked_ip",lambda r:_matches_ip(ip,r["value"])),
        ("country","blocked_country",lambda r:r["value"]==country),
        ("user_agent","blocked_user_agent",lambda r:r["value"] in ua),
        ("path","blocked_path",lambda r:r["value"] in path.lower()),
        ("method","blocked_method",lambda r:r["value"]==method.upper()),
    ):
        rule=next((item for item in active if item["kind"]==kind and match(item)),None)
        if rule:return {"allowed":kind in {"allow","user_allow"},"reason":reason,"rule":rule,"dry_run":True}
    return {"allowed":True,"reason":"no_matching_rule","dry_run":True}


def events(limit:int=200,active_only:bool=False) -> list[dict[str,Any]]:
    ensure(); cap=max(1,min(1000,int(limit)))
    if active_only: where="WHERE stopped_at IS NULL AND severity IN ('high','critical') AND created_at>=?"; params=(int(time.time())-900,cap)
    else: where=""; params=(cap,)
    with _connect() as db:return [dict(row) for row in db.execute(f"SELECT * FROM firewall_events {where} ORDER BY created_at DESC LIMIT ?",params)]


def stop_incident(event_id:int,actor:str) -> dict[str,Any]:
    ensure(); now=int(time.time())
    with _connect() as db:
        row=db.execute("SELECT * FROM firewall_events WHERE id=?",(int(event_id),)).fetchone()
        if not row:raise ValueError("Ereignis nicht gefunden.")
        if _trusted_network(row["ip"],settings()):raise ValueError("Vertrauenswürdige interne Netze dürfen nicht gesperrt werden.")
        db.execute("UPDATE firewall_events SET stopped_at=?,note=note||? WHERE id=?",(now,f"; stopped by {actor}",int(event_id)))
    rule=add_rule("block",row["ip"],"Manuell über Angriff stoppen gesperrt",None,actor)
    return {"stopped":True,"event_id":int(event_id),"rule":rule}


def acknowledge_incident(event_id:int,actor:str) -> bool:
    """Close an alert without blocking its IP or user."""
    ensure()
    with _connect() as db:
        return db.execute("UPDATE firewall_events SET stopped_at=?,note=note||? WHERE id=? AND stopped_at IS NULL",(int(time.time()),f"; acknowledged by {actor}",int(event_id))).rowcount>0


def trust_incident(event_id:int,scope:str,actor:str) -> dict[str,Any]:
    """Mark a false positive safe and add an explicit reversible allow rule."""
    ensure()
    with _connect() as db:
        row=db.execute("SELECT * FROM firewall_events WHERE id=?",(int(event_id),)).fetchone()
        if not row:raise ValueError("Ereignis nicht gefunden.")
    if scope=="ip":
        value=str(row["ip"])
        try:unban("block",value)
        except ValueError:pass
        rule=add_rule("allow",value,"Als Fehlalarm als sicher markiert",None,actor)
    elif scope=="user":
        value=str(row["actor_id"] or "")
        if not value:raise ValueError("Dieses Ereignis enthält keine Discord-Nutzer-ID.")
        try:unban("user_block",value)
        except ValueError:pass
        rule=add_rule("user_allow",value,"Als Fehlalarm als sicher markiert",None,actor)
    else:raise ValueError("Unbekannter Vertrauensbereich.")
    with _connect() as db:
        db.execute("UPDATE firewall_events SET stopped_at=?,note=note||? WHERE id=?",(int(time.time()),f"; trusted {scope} by {actor}",int(event_id)))
    reset_runtime_counters()
    return {"trusted":True,"scope":scope,"value":value,"rule":rule}


def extend_rule(rule_id:int,minutes:int,note:str|None=None,enabled:bool|None=None,priority:int|None=None) -> dict[str,Any]:
    """Change duration, note, state and priority without replacing a rule."""
    if minutes<0 or minutes>525600:raise ValueError("Ungültige Dauer.")
    if priority is not None and not 1<=int(priority)<=1000:raise ValueError("Priorität muss zwischen 1 und 1000 liegen.")
    ensure(); expires=None if minutes==0 else int(time.time())+minutes*60
    with _connect() as db:
        row=db.execute("SELECT * FROM firewall_rules WHERE id=?",(int(rule_id),)).fetchone()
        if not row:raise ValueError("Regel nicht gefunden.")
        state=int(row["enabled"]) if enabled is None else int(bool(enabled))
        rank=int(row["priority"]) if priority is None else int(priority)
        db.execute("UPDATE firewall_rules SET expires_at=?,note=?,enabled=?,priority=? WHERE id=?",(expires,(row["note"] if note is None else str(note)[:300]),state,rank,int(rule_id)))
        updated=db.execute("SELECT * FROM firewall_rules WHERE id=?",(int(rule_id),)).fetchone()
    return dict(updated)


def reset_runtime_counters() -> dict[str,int]:
    """Forget volatile rate observations; persistent rules remain untouched."""
    with _lock:
        hit_count=len(_hits); strike_count=len(_strikes)
        _hits.clear(); _strikes.clear()
    return {"hit_sources_cleared":hit_count,"strike_sources_cleared":strike_count}


def bulk_unban(scope:str) -> int:
    ensure(); now=int(time.time())
    clauses={
        "automatic":("created_by='firewall'",()),
        "temporary":("expires_at IS NOT NULL",()),
        "ip_user":("kind IN ('block','user_block')",()),
        "all_denies":("kind IN ('block','user_block','user_agent','path','country','method')",()),
    }
    if scope not in clauses:raise ValueError("Unbekannte Bereinigungsart.")
    where,params=clauses[scope]
    with _connect() as db: removed=db.execute(f"DELETE FROM firewall_rules WHERE {where}",params).rowcount
    reset_runtime_counters()
    return int(removed)


def apply_preset(name:str) -> dict[str,Any]:
    presets={
        "safe":{"auto_block_enabled":False,"requests_per_minute":1200,"burst_10_seconds":350,"confirmations_required":5,"emergency_mode":False},
        "balanced":{"auto_block_enabled":False,"requests_per_minute":900,"burst_10_seconds":250,"confirmations_required":4,"emergency_mode":False},
        "guarded":{"auto_block_enabled":True,"requests_per_minute":700,"burst_10_seconds":180,"confirmations_required":4,"emergency_mode":False},
        "emergency":{"auto_block_enabled":True,"requests_per_minute":500,"burst_10_seconds":120,"confirmations_required":3,"emergency_mode":True,"emergency_rpm":120},
    }
    if name not in presets:raise ValueError("Unbekanntes Schutzprofil.")
    reset_runtime_counters()
    return update_settings(presets[name])


def clone_rule(rule_id:int,new_value:str,minutes:int,actor:str) -> dict[str,Any]:
    """Create a new rule using an existing rule as a safe template."""
    ensure()
    with _connect() as db:row=db.execute("SELECT * FROM firewall_rules WHERE id=?",(int(rule_id),)).fetchone()
    if not row:raise ValueError("Regel nicht gefunden.")
    if not new_value.strip():raise ValueError("Neuer Regelwert fehlt.")
    expires=None if minutes<=0 else int(time.time())+minutes*60
    cloned=add_rule(row["kind"],new_value,f"Kopie von Regel #{rule_id}: {row['note']}"[:300],expires,actor)
    return extend_rule(cloned["id"],0 if expires is None else max(1,minutes),cloned["note"],bool(row["enabled"]),int(row["priority"]))


def annotate_event(event_id:int,note:str,actor:str) -> dict[str,Any]:
    clean=note.strip()
    if not clean:raise ValueError("Notiz darf nicht leer sein.")
    ensure()
    with _connect() as db:
        row=db.execute("SELECT * FROM firewall_events WHERE id=?",(int(event_id),)).fetchone()
        if not row:raise ValueError("Ereignis nicht gefunden.")
        db.execute("UPDATE firewall_events SET note=note||? WHERE id=?",(f"; note by {actor}: {clean[:300]}",int(event_id)))
        updated=db.execute("SELECT * FROM firewall_events WHERE id=?",(int(event_id),)).fetchone()
    return dict(updated)


def set_timed_emergency(minutes:int) -> dict[str,Any]:
    if minutes not in {0,15,30,60,120,360}:raise ValueError("Ungültige Notfall-Dauer.")
    until=0 if minutes==0 else int(time.time())+minutes*60
    return update_settings({"emergency_mode":minutes>0,"emergency_until":until})


def safety_audit() -> dict[str,Any]:
    cfg=settings(); active=rules(); findings=[]
    if cfg["auto_block_enabled"]:findings.append({"severity":"warning","title":"Automatische Sperren aktiv","detail":f"Nach {cfg['confirmations_required']} Bestätigungen wird automatisch gesperrt."})
    if cfg["emergency_mode"]:findings.append({"severity":"warning","title":"Notfallmodus aktiv","detail":"Das strengere Notfalllimit ist eingeschaltet."})
    if cfg["requests_per_minute"]<300:findings.append({"severity":"critical","title":"Sehr niedriges Minutenlimit","detail":"Unter 300 Requests/min können legitime Dashboard-Aufrufe auffallen."})
    if cfg["burst_10_seconds"]<80:findings.append({"severity":"critical","title":"Sehr niedriges Burst-Limit","detail":"Unter 80 Requests/10s steigt das Fehlalarmrisiko."})
    if not cfg["trusted_networks"]:findings.append({"severity":"critical","title":"Keine vertrauenswürdigen Netze","detail":"Interne Bot-Netze sollten geschützt bleiben."})
    if any(r["kind"]=="method" and r["value"] in {"GET","POST"} for r in active):findings.append({"severity":"warning","title":"Häufige HTTP-Methode gesperrt","detail":"GET/POST-Sperren können große Teile des Dashboards abschalten."})
    score=max(0,100-sum(25 if item["severity"]=="critical" else 10 for item in findings))
    return {"score":score,"status":"good" if score>=80 else "review" if score>=50 else "danger","findings":findings,"checked_at":int(time.time())}


def is_management_path(path:str) -> bool:
    clean=(path or "").split("?",1)[0]
    return clean.startswith("/firewall") or clean.startswith("/api/v1/firewall")


def record_audit(actor:str,action:str,target_type:str,target_id:str="",reason:str="",before:Any=None,after:Any=None) -> int:
    ensure()
    encode=lambda value:None if value is None else json.dumps(value,ensure_ascii=False,sort_keys=True)
    with _connect() as db:
        cur=db.execute("INSERT INTO firewall_audit_log(created_at,actor,action,target_type,target_id,reason,before_json,after_json) VALUES(?,?,?,?,?,?,?,?)",(int(time.time()),str(actor or "dashboard")[:80],action[:80],target_type[:30],str(target_id)[:100],reason[:300],encode(before),encode(after)))
        return int(cur.lastrowid)


def audit_entries(limit:int=300) -> list[dict[str,Any]]:
    ensure(); cap=max(1,min(1000,int(limit)))
    with _connect() as db:rows=[dict(row) for row in db.execute("SELECT * FROM firewall_audit_log ORDER BY created_at DESC,id DESC LIMIT ?",(cap,))]
    for row in rows:
        row["before"]=json.loads(row.pop("before_json")) if row.get("before_json") else None
        row["after"]=json.loads(row.pop("after_json")) if row.get("after_json") else None
    return rows


def _restore_rule_state(state:dict[str,Any]) -> dict[str,Any]:
    expires=state.get("expires_at"); now=int(time.time())
    if expires is not None and int(expires)<=now:expires=None
    restored=add_rule(state["kind"],state["value"],state.get("note","") ,int(expires) if expires is not None else None,"rollback")
    minutes=0 if expires is None else max(1,int((int(expires)-now)/60))
    return extend_rule(restored["id"],minutes,state.get("note",""),bool(state.get("enabled",1)),int(state.get("priority",100)))


def rollback_audit(entry_id:int,actor:str,reason:str="") -> dict[str,Any]:
    ensure()
    with _connect() as db:row=db.execute("SELECT * FROM firewall_audit_log WHERE id=?",(int(entry_id),)).fetchone()
    if not row:raise ValueError("Audit-Eintrag nicht gefunden.")
    if row["rolled_back_at"]:raise ValueError("Diese Änderung wurde bereits rückgängig gemacht.")
    before=json.loads(row["before_json"]) if row["before_json"] else None
    after=json.loads(row["after_json"]) if row["after_json"] else None
    if row["target_type"]=="rule":
        if before is None and after is not None:
            with _connect() as db:db.execute("DELETE FROM firewall_rules WHERE kind=? AND value=?",(after["kind"],after["value"]))
            result={"removed":True}
        elif before is not None:
            if after is not None and (after.get("kind"),after.get("value"))!=(before.get("kind"),before.get("value")):
                with _connect() as db:db.execute("DELETE FROM firewall_rules WHERE kind=? AND value=?",(after["kind"],after["value"]))
            result=_restore_rule_state(before)
        else:raise ValueError("Dieser Audit-Eintrag enthält keinen wiederherstellbaren Regelstand.")
    elif row["target_type"]=="setting":
        if before is None:raise ValueError("Alter Einstellungswert fehlt.")
        result=update_settings({row["target_id"]:before})
    else:raise ValueError("Diese Änderung unterstützt keinen Einzel-Rollback.")
    now=int(time.time())
    with _connect() as db:db.execute("UPDATE firewall_audit_log SET rolled_back_at=?,rolled_back_by=? WHERE id=?",(now,actor[:80],int(entry_id)))
    record_audit(actor,"rollback",row["target_type"],row["target_id"],reason or f"Rollback von Audit #{entry_id}",after,before)
    reset_runtime_counters()
    return {"rolled_back":True,"entry_id":int(entry_id),"result":result}


def compare_snapshot(snapshot_id:int) -> dict[str,Any]:
    ensure()
    with _connect() as db:row=db.execute("SELECT * FROM firewall_snapshots WHERE id=?",(int(snapshot_id),)).fetchone()
    if not row:raise ValueError("Sicherung nicht gefunden.")
    saved_settings=json.loads(row["settings_json"]); current_settings=settings()
    setting_changes=[{"key":key,"snapshot":saved_settings.get(key),"current":current_settings.get(key)} for key in sorted(set(saved_settings)|set(current_settings)) if saved_settings.get(key)!=current_settings.get(key)]
    identify=lambda rule:f"{rule.get('kind')}:{rule.get('value')}"
    saved={identify(rule):rule for rule in json.loads(row["rules_json"])}; current={identify(rule):rule for rule in rules(True)}
    added=[current[key] for key in current.keys()-saved.keys()]
    removed=[saved[key] for key in saved.keys()-current.keys()]
    changed=[{"key":key,"snapshot":saved[key],"current":current[key]} for key in saved.keys()&current.keys() if any(saved[key].get(field)!=current[key].get(field) for field in ("note","enabled","expires_at","priority"))]
    return {"snapshot":{"id":row["id"],"name":row["name"],"created_at":row["created_at"]},"settings":setting_changes,"rules_added":added,"rules_removed":removed,"rules_changed":changed,"total_changes":len(setting_changes)+len(added)+len(removed)+len(changed)}


def self_protection_test() -> dict[str,Any]:
    cases=[]
    for path in ("/firewall/check","/api/v1/firewall/check","/api/v1/firewall/overview"):
        cases.append({"name":f"Management-Pfad {path}","passed":is_management_path(path),"result":"bypass" if is_management_path(path) else "failed"})
    internal=evaluate("203.0.113.250","POST","/api/templates",trusted_internal=True)
    owner=evaluate("203.0.113.251","POST","/dashboard",actor_id="test-owner",actor_is_owner=True)
    cases.extend(({"name":"Interner Bot-Aufruf","passed":internal.get("reason")=="trusted_internal","result":internal.get("reason")},{"name":"Owner-Bypass","passed":owner.get("reason")=="owner_bypass","result":owner.get("reason")}))
    return {"passed":all(case["passed"] for case in cases),"cases":cases,"tested_at":int(time.time()),"created_events":False,"created_rules":False}


def create_snapshot(name:str,actor:str) -> dict[str,Any]:
    """Store a reversible configuration snapshot without security events."""
    clean=(name or "Manuelle Sicherung").strip()[:80]
    now=int(time.time()); cfg=settings(); saved_rules=rules(True)
    with _connect() as db:
        cur=db.execute("INSERT INTO firewall_snapshots(name,created_at,created_by,settings_json,rules_json) VALUES(?,?,?,?,?)",(clean,now,actor[:80],json.dumps(cfg,ensure_ascii=False),json.dumps(saved_rules,ensure_ascii=False)))
        # Bounded storage: the newest 30 snapshots are enough for rollback.
        db.execute("DELETE FROM firewall_snapshots WHERE id NOT IN (SELECT id FROM firewall_snapshots ORDER BY created_at DESC,id DESC LIMIT 30)")
        row=db.execute("SELECT id,name,created_at,created_by FROM firewall_snapshots WHERE id=?",(cur.lastrowid,)).fetchone()
    return dict(row)


def snapshots() -> list[dict[str,Any]]:
    ensure()
    with _connect() as db:return [dict(row) for row in db.execute("SELECT id,name,created_at,created_by FROM firewall_snapshots ORDER BY created_at DESC,id DESC LIMIT 30")]


def delete_snapshot(snapshot_id:int) -> bool:
    ensure()
    with _connect() as db:return db.execute("DELETE FROM firewall_snapshots WHERE id=?",(int(snapshot_id),)).rowcount>0


def restore_snapshot(snapshot_id:int,actor:str) -> dict[str,Any]:
    ensure()
    with _connect() as db:row=db.execute("SELECT * FROM firewall_snapshots WHERE id=?",(int(snapshot_id),)).fetchone()
    if not row:raise ValueError("Sicherung nicht gefunden.")
    cfg=json.loads(row["settings_json"]); saved_rules=json.loads(row["rules_json"])
    if not isinstance(cfg,dict) or not isinstance(saved_rules,list):raise ValueError("Sicherung ist beschädigt.")
    create_snapshot("Automatisch vor Wiederherstellung",actor)
    update_settings(cfg)
    with _connect() as db:db.execute("DELETE FROM firewall_rules")
    restored=0; now=int(time.time())
    for item in saved_rules:
        expires=item.get("expires_at")
        if expires is not None and int(expires)<=now:continue
        rule=add_rule(str(item.get("kind") or ""),str(item.get("value") or ""),str(item.get("note") or ""),int(expires) if expires is not None else None,actor)
        remaining=0 if expires is None else max(1,int((int(expires)-now)/60))
        extend_rule(rule["id"],remaining,str(item.get("note") or ""),bool(item.get("enabled",1)),int(item.get("priority",100)))
        restored+=1
    reset_runtime_counters()
    return {"restored":True,"snapshot_id":int(snapshot_id),"rules_restored":restored,"settings":settings()}


def export_configuration() -> dict[str,Any]:
    return {"version":4,"exported_at":int(time.time()),"settings":settings(),"rules":rules(True),"contains_events":False}


def overview() -> dict[str,Any]:
    ensure(); now=int(time.time()); since=now-86400
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
        blocked=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND blocked=1",(since,)).fetchone()[0]
        alarms=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND category='rate_alarm'",(since,)).fetchone()[0]
        ips=db.execute("SELECT COUNT(DISTINCT ip) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
        top_sources=[dict(row) for row in db.execute("SELECT ip,COUNT(*) AS count,SUM(blocked) AS blocked FROM firewall_events WHERE created_at>=? GROUP BY ip ORDER BY count DESC LIMIT 8",(since,))]
        top_categories=[dict(row) for row in db.execute("SELECT category,COUNT(*) AS count FROM firewall_events WHERE created_at>=? GROUP BY category ORDER BY count DESC LIMIT 8",(since,))]
        top_paths=[dict(row) for row in db.execute("SELECT path,COUNT(*) AS count,SUM(blocked) AS blocked FROM firewall_events WHERE created_at>=? GROUP BY path ORDER BY count DESC LIMIT 8",(since,))]
        top_methods=[dict(row) for row in db.execute("SELECT method,COUNT(*) AS count FROM firewall_events WHERE created_at>=? GROUP BY method ORDER BY count DESC",(since,))]
        top_countries=[dict(row) for row in db.execute("SELECT COALESCE(NULLIF(country,''),'--') AS country,COUNT(*) AS count FROM firewall_events WHERE created_at>=? GROUP BY country ORDER BY count DESC LIMIT 8",(since,))]
        hourly=[dict(row) for row in db.execute("SELECT strftime('%Y-%m-%d %H:00',created_at,'unixepoch') AS hour,COUNT(*) AS count,SUM(blocked) AS blocked FROM firewall_events WHERE created_at>=? GROUP BY hour ORDER BY hour",(since,))]
    active=rules(); all_rules=rules(True)
    with _lock: runtime={"tracked_sources":len(_hits),"pending_confirmations":len(_strikes)}
    return {"settings":settings(),"rules":all_rules,"events":events(300),"active_incidents":events(60,True),"top_sources":top_sources,"top_categories":top_categories,"top_paths":top_paths,"top_methods":top_methods,"top_countries":top_countries,"hourly":hourly,"runtime":runtime,"stats":{"events_24h":total,"blocked_24h":blocked,"alarms_24h":alarms,"unique_ips_24h":ips,"manual_bans":sum(r["kind"] in ("block","user_block") for r in active),"disabled_rules":sum(not r["enabled"] for r in all_rules)},"retention_days":90,"engine":{"mode":"deterministic","ai_enforcement":False,"self_protection":True}}


def save_ai_report(event_id:int,report:str) -> None:
    with _connect() as db:db.execute("UPDATE firewall_events SET ai_report=? WHERE id=?",(report[:12000],int(event_id)))
