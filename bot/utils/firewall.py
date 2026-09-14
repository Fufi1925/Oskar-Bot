"""Conservative application firewall shared by website, BFF and FastAPI.

The firewall is intentionally fail-safe for legitimate users: trusted networks,
owner identities and bot-internal calls are evaluated before every deny rule.
Automatic blocking is optional and needs several independent confirmations.
Grok is not used anywhere in detection or enforcement.
"""
from __future__ import annotations

import ipaddress
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
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(firewall_events)")}
        if "actor_id" not in columns: db.execute("ALTER TABLE firewall_events ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''")
        if "source" not in columns: db.execute("ALTER TABLE firewall_events ADD COLUMN source TEXT NOT NULL DEFAULT 'external'")
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
    if kind not in {"block","allow","user_block","user_allow","user_agent","path","country"}:
        raise ValueError("Unbekannte Regelart.")
    if kind in {"block","allow"}: clean=_valid_network(value)
    elif kind in {"user_block","user_allow"}: clean=_valid_user(value)
    elif kind=="country":
        clean=value.strip().upper()
        if len(clean)!=2 or not clean.isalpha(): raise ValueError("Bitte einen zweistelligen ISO-Ländercode verwenden.")
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


def rules() -> list[dict[str,Any]]:
    ensure(); now=int(time.time())
    with _connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM firewall_rules WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at DESC",(now,))]


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
    bad_bot=cfg["block_bad_bots"] and any(item in ua for item in ("sqlmap","nikto","masscan","nmap","gobuster","dirbuster"))
    if path_rule or ua_rule or country_rule or bad_bot or (country and country in cfg["country_blocklist"]):
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
    limit=cfg["emergency_rpm"] if cfg["emergency_mode"] else cfg["requests_per_minute"]
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


def inspect(ip:str="",actor_id:str="",user_agent:str="",country:str="",path:str="/") -> dict[str,Any]:
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


def overview() -> dict[str,Any]:
    ensure(); now=int(time.time()); since=now-86400
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
        blocked=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND blocked=1",(since,)).fetchone()[0]
        alarms=db.execute("SELECT COUNT(*) FROM firewall_events WHERE created_at>=? AND category='rate_alarm'",(since,)).fetchone()[0]
        ips=db.execute("SELECT COUNT(DISTINCT ip) FROM firewall_events WHERE created_at>=?",(since,)).fetchone()[0]
    active=rules()
    return {"settings":settings(),"rules":active,"events":events(300),"active_incidents":events(60,True),"stats":{"events_24h":total,"blocked_24h":blocked,"alarms_24h":alarms,"unique_ips_24h":ips,"manual_bans":sum(r["kind"] in ("block","user_block") for r in active)},"retention_days":90,"engine":{"mode":"deterministic","ai_enforcement":False,"self_protection":True}}


def save_ai_report(event_id:int,report:str) -> None:
    with _connect() as db:db.execute("UPDATE firewall_events SET ai_report=? WHERE id=?",(report[:12000],int(event_id)))
