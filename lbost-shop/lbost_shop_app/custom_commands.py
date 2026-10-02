"""Isolated LBoost Custom Command storage, mirroring University without Marketplace."""
from __future__ import annotations
import json, re, time
from typing import Any
from lbost_shop_app import db

FREE_MAX_COMMANDS = 20
PREMIUM_MAX_COMMANDS = 20
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ACTION_TYPES = {"reply", "dm", "send_channel", "add_role", "remove_role", "condition_role"}
PARAMETER_TYPES = {"string", "integer", "boolean", "user", "channel", "role"}


def ensure_schema(settings) -> None:
    with db._gesichert(settings) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS custom_commands (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL COLLATE NOCASE,
            response TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0,
            use_prefix INTEGER NOT NULL DEFAULT 1,
            use_exact INTEGER NOT NULL DEFAULT 0,
            use_contains INTEGER NOT NULL DEFAULT 0,
            use_slash INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(guild_id,name)
        );
        CREATE INDEX IF NOT EXISTS idx_custom_commands_updated
            ON custom_commands(guild_id,updated_at);
        """)


def normalise_name(value: str) -> str:
    return str(value or "").strip().lower().lstrip("!>?.")


def valid_name(value: str) -> bool:
    return bool(NAME_RE.fullmatch(value))


def _row(row) -> dict:
    item = dict(row)
    try: item["config"] = json.loads(item.pop("config_json") or "{}")
    except (TypeError, ValueError): item["config"] = {}
    return item


def list_all(settings, guild_id: int | None = None) -> list[dict]:
    ensure_schema(settings)
    with db._gesichert(settings) as conn:
        if guild_id is None:
            rows=conn.execute("SELECT * FROM custom_commands ORDER BY guild_id,name").fetchall()
        else:
            rows=conn.execute("SELECT * FROM custom_commands WHERE guild_id=? ORDER BY name",(guild_id,)).fetchall()
    return [_row(row) for row in rows]


def get(settings, guild_id: int, name: str) -> dict | None:
    ensure_schema(settings)
    with db._gesichert(settings) as conn:
        row=conn.execute("SELECT * FROM custom_commands WHERE guild_id=? AND name=? COLLATE NOCASE",(guild_id,name)).fetchone()
    return _row(row) if row else None


def save(settings, guild_id: int, name: str, response: str, actor: str, *,
         use_prefix=True, use_exact=False, use_contains=False, use_slash=False,
         config: dict | None=None, max_commands=FREE_MAX_COMMANDS) -> bool:
    ensure_schema(settings); now=int(time.time())
    with db._gesichert(settings) as conn:
        cursor=conn.execute(
            "INSERT INTO custom_commands(guild_id,name,response,created_by,created_at,updated_at,use_prefix,use_exact,use_contains,use_slash,config_json) "
            "SELECT ?,?,?,?,?,?,?,?,?,?,? WHERE (SELECT COUNT(*) FROM custom_commands WHERE guild_id=?)<? "
            "OR EXISTS(SELECT 1 FROM custom_commands WHERE guild_id=? AND name=? COLLATE NOCASE) "
            "ON CONFLICT(guild_id,name) DO UPDATE SET response=excluded.response,updated_at=excluded.updated_at,"
            "use_prefix=excluded.use_prefix,use_exact=excluded.use_exact,use_contains=excluded.use_contains,"
            "use_slash=excluded.use_slash,config_json=excluded.config_json",
            (guild_id,name,response,actor,now,now,int(use_prefix),int(use_exact),int(use_contains),int(use_slash),
             json.dumps(config or {},ensure_ascii=False),guild_id,max(1,int(max_commands)),guild_id,name))
        return cursor.rowcount>0


def delete(settings, guild_id: int, name: str) -> bool:
    ensure_schema(settings)
    with db._gesichert(settings) as conn:
        cursor=conn.execute("DELETE FROM custom_commands WHERE guild_id=? AND name=? COLLATE NOCASE",(guild_id,name))
        return cursor.rowcount>0


def signatures(settings) -> dict[int, tuple[int,int]]:
    ensure_schema(settings)
    with db._gesichert(settings) as conn:
        rows=conn.execute("SELECT guild_id,COUNT(*) amount,MAX(updated_at) changed FROM custom_commands GROUP BY guild_id").fetchall()
    return {int(row["guild_id"]):(int(row["amount"]),int(row["changed"] or 0)) for row in rows}


def validate_config(config: Any) -> dict:
    if not isinstance(config,dict): raise ValueError("De opdrachtconfiguratie is ongeldig.")
    actions=config.get("actions",[]); parameters=config.get("parameters",[]); total=0
    def steps(items,depth=0):
        nonlocal total
        if not isinstance(items,list) or depth>4: raise ValueError("De opdrachtstroom is ongeldig of te diep genest.")
        for action in items:
            if not isinstance(action,dict) or action.get("type") not in ACTION_TYPES: raise ValueError("De opdracht bevat een ongeldige stap.")
            total+=1
            if total>50: raise ValueError("Het commando mag in totaal maximaal 50 stappen bevatten.")
            buttons=action.get("buttons",[])
            if not isinstance(buttons,list) or len(buttons)>5: raise ValueError("Een antwoord mag maximaal 5 knoppen bevatten.")
            for button in buttons:
                if not isinstance(button,dict): raise ValueError("Ongeldige knop.")
                steps(button.get("actions",[]),depth+1)
            if action.get("type")=="condition_role":
                steps(action.get("then",[]),depth+1);steps(action.get("else",[]),depth+1)
    if not isinstance(actions,list) or len(actions)>25: raise ValueError("De stroom mag maximaal 25 stappen bevatten.")
    steps(actions)
    if not actions: raise ValueError("Voeg ten minste één stroomstap toe.")
    if not isinstance(parameters,list) or len(parameters)>10: raise ValueError("Er zijn maximaal 10 parameters mogelijk.")
    names=[]
    for parameter in parameters:
        name=str(parameter.get("name", "")) if isinstance(parameter,dict) else ""
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}",name): raise ValueError("Elke parameter heeft een geldige naam nodig.")
        if name in names: raise ValueError("Parameternamen mogen niet dubbel voorkomen.")
        if parameter.get("type") not in PARAMETER_TYPES: raise ValueError("Ongeldig parametertype.")
        names.append(name)
    config["cooldown"]=max(0,min(86400,int(config.get("cooldown") or 0)))
    config["allowed_roles"]=[str(v) for v in config.get("allowed_roles",[]) if str(v).isdigit()][:50]
    config["allowed_users"]=[str(v) for v in config.get("allowed_users",[]) if str(v).isdigit()][:50]
    config["enabled"]=bool(config.get("enabled",True));config["deny_without_role"]=bool(config.get("deny_without_role",False))
    return config
