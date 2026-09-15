"""Global admin application-firewall routes."""
from __future__ import annotations
import json
import os
import httpx
from fastapi import APIRouter, HTTPException
from utils import firewall

router=APIRouter()

@router.get("/overview")
async def get_overview(): return firewall.overview()

@router.patch("/settings")
async def patch_settings(data:dict):
    try:return firewall.update_settings(data)
    except (TypeError,ValueError) as exc:raise HTTPException(400,str(exc)) from exc

@router.post("/rules")
async def create_rule(data:dict):
    try:
        minutes=int(data.get("minutes") or 0); expires=None if minutes<=0 else int(__import__('time').time())+minutes*60
        return firewall.add_rule(str(data.get("kind") or ""),str(data.get("value") or ""),str(data.get("note") or ""),expires,str(data.get("actor") or "dashboard"))
    except (TypeError,ValueError) as exc:raise HTTPException(400,str(exc)) from exc

@router.delete("/rules/{rule_id}")
async def remove_rule(rule_id:int):
    if not firewall.delete_rule(rule_id):raise HTTPException(404,"Regel nicht gefunden.")
    return {"status":"ok","unblocked":True}

@router.post("/unban")
async def unban(data:dict):
    try:removed=firewall.unban(str(data.get("kind") or ""),str(data.get("value") or ""))
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    if not removed:raise HTTPException(404,"Keine passende aktive Sperre gefunden.")
    return {"status":"ok","removed":removed,"unblocked":True}

@router.post("/inspect")
async def inspect_request(data:dict):
    return firewall.inspect(str(data.get("ip") or ""),str(data.get("actor_id") or ""),str(data.get("user_agent") or ""),str(data.get("country") or ""),str(data.get("path") or "/"),str(data.get("method") or "GET"))

@router.get("/diagnostics")
async def diagnostics():
    overview=firewall.overview()
    return {"status":"healthy","database":"ok","engine":overview["engine"],"runtime":overview["runtime"],"retention_days":overview["retention_days"],"active_rules":len(overview["rules"]),"internal_routes_exempt":True}

@router.post("/incidents/{event_id}/acknowledge")
async def acknowledge(event_id:int,data:dict):
    if not firewall.acknowledge_incident(event_id,str(data.get("actor") or "dashboard")):raise HTTPException(404,"Offener Alarm nicht gefunden.")
    return {"status":"ok","acknowledged":True,"blocked":False}

@router.post("/incidents/{event_id}/trust")
async def trust_incident(event_id:int,data:dict):
    try:return firewall.trust_incident(event_id,str(data.get("scope") or "ip"),str(data.get("actor") or "dashboard"))
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc

@router.patch("/rules/{rule_id}")
async def edit_rule(rule_id:int,data:dict):
    try:return firewall.extend_rule(rule_id,int(data.get("minutes") or 0),data.get("note"))
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc

@router.post("/operations/reset-counters")
async def reset_counters(): return {"status":"ok",**firewall.reset_runtime_counters()}

@router.post("/operations/bulk-unban")
async def bulk_unban(data:dict):
    try:removed=firewall.bulk_unban(str(data.get("scope") or ""))
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    return {"status":"ok","removed":removed}

@router.post("/operations/preset/{name}")
async def apply_preset(name:str):
    try:return firewall.apply_preset(name)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc

@router.get("/export")
async def export_configuration(): return firewall.export_configuration()

@router.post("/incidents/{event_id}/stop")
async def stop_attack(event_id:int,data:dict):
    try:return firewall.stop_incident(event_id,str(data.get("actor") or "dashboard"))
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc

@router.post("/incidents/{event_id}/analyze")
async def analyze_attack(event_id:int):
    event=next((item for item in firewall.events(1000) if int(item["id"])==event_id),None)
    if not event:raise HTTPException(404,"Angriff nicht gefunden.")
    key=(os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "").strip()
    if not key:raise HTTPException(503,"XAI_API_KEY ist nicht gesetzt. Grok-Berichte sind deshalb deaktiviert.")
    prompt=("Du bist ein defensiver Web-Sicherheitsanalyst. Erstelle ausschließlich einen kurzen deutschen Bericht "
            "mit Risiko, wahrscheinlicher Ursache, Belegen und empfohlenen manuellen Maßnahmen. Entscheide und "
            "blockiere niemals selbst. Antworte als Klartext. Ereignis: "+json.dumps(event,ensure_ascii=False))
    payload={"model":os.getenv("GROK_FIREWALL_MODEL","grok-4.6"),"messages":[{"role":"system","content":"Nur defensive Analyse und Vorschläge. Keine Aktionen ausführen."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":1200}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response=await client.post("https://api.x.ai/v1/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload)
        response.raise_for_status(); report=response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:raise HTTPException(502,f"Grok-Bericht fehlgeschlagen: {type(exc).__name__}") from exc
    firewall.save_ai_report(event_id,report)
    return {"event_id":event_id,"report":report,"advisory_only":True}

@router.post("/check")
async def check_request(data:dict):
    return firewall.evaluate(
        str(data.get("ip") or "unknown"),str(data.get("method") or "GET"),
        str(data.get("path") or "/"),str(data.get("user_agent") or ""),
        str(data.get("country") or ""),str(data.get("actor_id") or ""),
        bool(data.get("actor_is_owner")),False,
    )
