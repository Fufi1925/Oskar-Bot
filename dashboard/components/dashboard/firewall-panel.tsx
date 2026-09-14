"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Ban, Bot, BrainCircuit, CheckCircle2, Clock3,
  Gauge, Globe2, KeyRound, Loader2, LockKeyhole, Plus, RefreshCw, Save,
  Search, Shield, ShieldCheck, Trash2, Undo2, UserRoundX, Wifi, X, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "overview" | "bans" | "trusted" | "protection" | "events" | "diagnostics";
type Rule = { id:number; kind:string; value:string; note:string; created_at:number; expires_at:number|null; created_by:string };
type Event = { id:number; ip:string; actor_id?:string; method:string; path:string; category:string; severity:string; created_at:number; request_count:number; blocked:number; note?:string; ai_report?:string };

const fmt = (seconds:number) => new Date(seconds * 1000).toLocaleString("de-DE");
const ruleNames:Record<string,string> = {
  block:"IP/CIDR gesperrt", allow:"IP/CIDR erlaubt", user_block:"Nutzer gesperrt",
  user_allow:"Nutzer erlaubt", user_agent:"User-Agent", path:"Pfad", country:"Land",
};

export function FirewallPanel() {
  const [data,setData] = useState<any>(null);
  const [tab,setTab] = useState<Tab>("overview");
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [query,setQuery] = useState("");
  const [confirmEvent,setConfirmEvent] = useState<Event|null>(null);
  const [report,setReport] = useState<any>(null);
  const [diagnostics,setDiagnostics] = useState<any>(null);
  const [inspection,setInspection] = useState<any>(null);
  const [inspect,setInspect] = useState({ip:"",actor_id:"",path:"/dashboard",country:"",user_agent:""});
  const [newRule,setNewRule] = useState({kind:"block",value:"",note:"",minutes:0});
  const [quickUnban,setQuickUnban] = useState({kind:"ip",value:""});

  const load = useCallback(async (silent=false) => {
    if (!silent) setLoading(true);
    try { setData(await api.getFirewallOverview()); }
    catch (error:any) { toast.error(error?.message || "Firewall konnte nicht geladen werden."); }
    finally { setLoading(false); }
  },[]);

  useEffect(() => { void load(); },[load]);
  useEffect(() => { const timer=setInterval(() => void load(true),15000); return () => clearInterval(timer); },[load]);

  const rules:Rule[] = data?.rules || [];
  const events:Event[] = useMemo(() => (data?.events || []).filter((event:Event) =>
    `${event.ip} ${event.actor_id || ""} ${event.path} ${event.category}`.toLowerCase().includes(query.toLowerCase())
  ),[data,query]);
  const settings = data?.settings || {};

  const saveSettings = async () => {
    setBusy(true);
    try { await api.updateFirewallSettings(settings); toast.success("Schutzprofil gespeichert."); await load(true); }
    catch (error:any) { toast.error(error?.message || "Einstellungen konnten nicht gespeichert werden."); }
    finally { setBusy(false); }
  };
  const createRule = async () => {
    if (!newRule.value.trim()) return toast.error("Bitte einen Regelwert eingeben.");
    setBusy(true);
    try { await api.addFirewallRule(newRule); setNewRule({...newRule,value:"",note:""}); toast.success("Regel aktiviert."); await load(true); }
    catch (error:any) { toast.error(error?.message || "Regel konnte nicht aktiviert werden."); }
    finally { setBusy(false); }
  };
  const removeRule = async (rule:Rule) => {
    setBusy(true);
    try { await api.deleteFirewallRule(rule.id); toast.success(`${ruleNames[rule.kind] || "Regel"} aufgehoben.`); await load(true); }
    catch (error:any) { toast.error(error?.message || "Entsperren fehlgeschlagen."); }
    finally { setBusy(false); }
  };
  const unban = async () => {
    setBusy(true);
    try { await api.unbanFirewall(quickUnban); toast.success("Sperre vollständig entfernt."); setQuickUnban({...quickUnban,value:""}); await load(true); }
    catch (error:any) { toast.error(error?.message || "Keine passende Sperre gefunden."); }
    finally { setBusy(false); }
  };
  const stopAttack = async () => {
    if (!confirmEvent) return;
    setBusy(true);
    try { await api.stopFirewallIncident(confirmEvent.id); toast.success("Quelle manuell gesperrt."); setConfirmEvent(null); await load(true); }
    catch (error:any) { toast.error(error?.message || "Diese Quelle darf nicht gesperrt werden."); }
    finally { setBusy(false); }
  };
  const analyze = async (event:Event) => {
    setBusy(true);
    try { setReport(await api.analyzeFirewallIncident(event.id)); }
    catch (error:any) { toast.error(error?.message || "Grok-Bericht nicht verfügbar."); }
    finally { setBusy(false); }
  };
  const runInspection = async () => {
    setBusy(true);
    try { setInspection(await api.inspectFirewall(inspect)); }
    catch (error:any) { toast.error(error?.message || "Prüfung fehlgeschlagen."); }
    finally { setBusy(false); }
  };
  const runDiagnostics = async () => {
    setBusy(true);
    try { setDiagnostics(await api.getFirewallDiagnostics()); toast.success("Eigene API ist erreichbar."); }
    catch (error:any) { toast.error(error?.message || "Diagnose fehlgeschlagen."); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="grid min-h-80 place-items-center"><Loader2 className="h-7 w-7 animate-spin text-cyan-400"/></div>;

  return <div className={cn("space-y-5",busy && "pointer-events-none opacity-75")}>
    <header className="relative overflow-hidden rounded-3xl border border-cyan-500/20 bg-[#101116] p-6 sm:p-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_90%_0%,rgba(6,182,212,.16),transparent_42%)]"/>
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center">
        <span className="grid h-16 w-16 place-items-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10"><Shield className="h-8 w-8 text-cyan-300"/></span>
        <div className="flex-1"><p className="text-xs font-black uppercase tracking-[.22em] text-cyan-300">Firewall Control Center</p><h2 className="mt-1 text-3xl font-black text-white">Sicher blockieren, niemals raten</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Owner, eigene Netze und interne Bot-Aufrufe haben Vorrang vor allen Sperren. Automatische Sperren sind standardmäßig aus; Alarme bleiben sichtbar und jede manuelle Sperre ist rückgängig.</p></div>
        <div className="flex gap-2"><Status active={settings.enabled} label={settings.enabled?"Schutz aktiv":"Schutz aus"}/><Status active={!settings.auto_block_enabled} label={settings.auto_block_enabled?"Auto-Bann aktiv":"Nur Alarm"}/></div>
      </div>
    </header>

    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Metric icon={Activity} label="Ereignisse · 24h" value={data.stats.events_24h}/>
      <Metric icon={AlertTriangle} label="Alarme · 24h" value={data.stats.alarms_24h}/>
      <Metric icon={Ban} label="Blockiert · 24h" value={data.stats.blocked_24h}/>
      <Metric icon={UserRoundX} label="Aktive Sperren" value={data.stats.manual_bans}/>
      <Metric icon={Globe2} label="Quellen · 24h" value={data.stats.unique_ips_24h}/>
    </div>

    <nav className="flex gap-1 overflow-x-auto rounded-2xl border border-slate-800 bg-[#131318] p-1.5">
      {([
        ["overview","Übersicht",ShieldCheck],["bans","Sperren & Entsperren",UserRoundX],
        ["trusted","Vertrauen",KeyRound],["protection","Schutzprofil",Gauge],
        ["events","Ereignisse",Clock3],["diagnostics","API-Diagnose",Bot],
      ] as [Tab,string,any][]).map(([id,label,Icon]) => <button key={id} onClick={() => setTab(id)} className={cn("flex shrink-0 items-center gap-2 rounded-xl px-4 py-3 text-xs font-bold transition",tab===id?"bg-cyan-500/10 text-cyan-200":"text-slate-500 hover:bg-white/[.03] hover:text-white")}><Icon className="h-4 w-4"/>{label}</button>)}
    </nav>

    {tab==="overview" && <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
      <Panel title="Aktive Warnungen" icon={Zap}>{data.active_incidents.length ? <div className="space-y-2">{data.active_incidents.slice(0,12).map((event:Event) => <EventRow key={event.id} event={event} onStop={setConfirmEvent} onAnalyze={analyze}/>)}</div> : <Empty text="Keine laufenden Warnungen. Normale Aufrufe werden nicht protokolliert."/>}</Panel>
      <Panel title="Sicherheitsgarantien" icon={ShieldCheck}><div className="space-y-3"><Guarantee title="Owner-Schutz" text="Konfigurierte Owner-IDs können nie durch Firewall-Regeln gesperrt werden."/><Guarantee title="Self-Protection" text="Firewall-Verwaltung und /firewall/check prüfen oder blockieren sich niemals selbst."/><Guarantee title="Interne API" text="Lokale Bot-Aufrufe werden weder gezählt noch als Angriff gespeichert."/><Guarantee title="Keine KI-Entscheidungen" text="Grok schreibt nur Berichte; Erkennung und Aktionen bleiben deterministisch und manuell."/></div></Panel>
    </div>}

    {tab==="bans" && <div className="grid gap-4 xl:grid-cols-[.8fr_1.2fr]">
      <div className="space-y-4"><Panel title="Manuelle Regel" icon={Plus}><Field label="Regelart"><select value={newRule.kind} onChange={e=>setNewRule({...newRule,kind:e.target.value})} className="input"><option value="block">IP oder CIDR sperren</option><option value="user_block">Discord-Nutzer sperren</option><option value="allow">IP oder CIDR immer erlauben</option><option value="user_allow">Discord-Nutzer immer erlauben</option><option value="country">Land sperren</option><option value="user_agent">User-Agent sperren</option><option value="path">Pfad-Muster sperren</option></select></Field><Field label="Wert"><input className="input" value={newRule.value} onChange={e=>setNewRule({...newRule,value:e.target.value})} placeholder={newRule.kind.includes("user_")?"Discord-Nutzer-ID":newRule.kind==="country"?"DE":"IP, CIDR oder Muster"}/></Field><div className="grid grid-cols-2 gap-3"><Field label="Dauer · Minuten"><input className="input" type="number" min="0" value={newRule.minutes} onChange={e=>setNewRule({...newRule,minutes:Number(e.target.value)})}/></Field><Field label="Notiz"><input className="input" value={newRule.note} onChange={e=>setNewRule({...newRule,note:e.target.value})} placeholder="Grund"/></Field></div><p className="mt-3 text-xs text-slate-600">0 Minuten bedeutet dauerhaft. Owner-IDs sowie eigene und vertrauenswürdige Netze lehnt das Backend immer ab.</p><button onClick={createRule} className="primary mt-4 w-full"><LockKeyhole className="h-4 w-4"/>Regel aktivieren</button></Panel>
      <Panel title="Schnell entsperren" icon={Undo2}><div className="grid grid-cols-[130px_1fr] gap-2"><select className="input" value={quickUnban.kind} onChange={e=>setQuickUnban({...quickUnban,kind:e.target.value})}><option value="ip">IP/CIDR</option><option value="user">Nutzer-ID</option></select><input className="input" value={quickUnban.value} onChange={e=>setQuickUnban({...quickUnban,value:e.target.value})} placeholder="Exakter gesperrter Wert"/></div><button onClick={unban} className="secondary mt-3 w-full"><Undo2 className="h-4 w-4"/>Sperre entfernen</button></Panel></div>
      <Panel title="Aktive Regeln" icon={Ban}>{rules.length ? <div className="space-y-2">{rules.map(rule => <RuleRow key={rule.id} rule={rule} remove={removeRule}/>)}</div> : <Empty text="Keine manuellen Regeln aktiv."/>}</Panel>
    </div>}

    {tab==="trusted" && <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Vertrauenswürdige Netze" icon={Wifi}><p className="mb-3 text-sm leading-6 text-slate-400">Diese Netze werden vor jeder Blockregel geprüft und niemals gezählt, geflaggt oder gesperrt.</p><textarea className="input min-h-44 font-mono" value={(settings.trusted_networks||[]).join("\n")} onChange={e=>setData({...data,settings:{...settings,trusted_networks:e.target.value.split(/\n|,/).map(v=>v.trim()).filter(Boolean)}})}/><button onClick={saveSettings} className="primary mt-4"><Save className="h-4 w-4"/>Netze speichern</button></Panel>
      <Panel title="Regel sicher testen" icon={Search}><p className="mb-3 text-sm text-slate-400">Dry-Run: erzeugt kein Ereignis, erhöht keinen Zähler und sperrt niemanden.</p><div className="grid gap-3 sm:grid-cols-2"><Field label="IP"><input className="input" value={inspect.ip} onChange={e=>setInspect({...inspect,ip:e.target.value})} placeholder="203.0.113.10"/></Field><Field label="Discord-Nutzer-ID"><input className="input" value={inspect.actor_id} onChange={e=>setInspect({...inspect,actor_id:e.target.value})}/></Field><Field label="Pfad"><input className="input" value={inspect.path} onChange={e=>setInspect({...inspect,path:e.target.value})}/></Field><Field label="Land"><input className="input" value={inspect.country} onChange={e=>setInspect({...inspect,country:e.target.value})}/></Field></div><button onClick={runInspection} className="secondary mt-4"><Search className="h-4 w-4"/>Ohne Aktion prüfen</button>{inspection && <Result allowed={inspection.allowed} title={inspection.allowed?"Würde erlaubt":"Würde blockiert"} text={`${inspection.reason}${inspection.rule?` · Regel #${inspection.rule.id}`:""}`}/>}</Panel>
    </div>}

    {tab==="protection" && <Panel title="Konservatives Schutzprofil" icon={Gauge}>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3"><Toggle label="Firewall aktiv" text="Explizite Regeln und Alarme anwenden" value={settings.enabled} set={v=>setData({...data,settings:{...settings,enabled:v}})}/><Toggle label="Automatisch sperren" text="Standardmäßig aus; erst nach mehreren Bestätigungen" value={settings.auto_block_enabled} danger set={v=>setData({...data,settings:{...settings,auto_block_enabled:v}})}/><Toggle label="Scanner erkennen" text="Bekannte offensive Scanner blockieren" value={settings.block_bad_bots} set={v=>setData({...data,settings:{...settings,block_bad_bots:v}})}/><Toggle label="Notfallmodus" text="Nur bei einem bestätigten Angriff einschalten" value={settings.emergency_mode} danger set={v=>setData({...data,settings:{...settings,emergency_mode:v}})}/></div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><NumberField label="Anfragen pro Minute" value={settings.requests_per_minute} set={v=>setData({...data,settings:{...settings,requests_per_minute:v}})}/><NumberField label="Burst in 10 Sekunden" value={settings.burst_10_seconds} set={v=>setData({...data,settings:{...settings,burst_10_seconds:v}})}/><NumberField label="Bestätigungen vor Auto-Sperre" value={settings.confirmations_required} set={v=>setData({...data,settings:{...settings,confirmations_required:v}})}/><NumberField label="Bestätigungsfenster · Sekunden" value={settings.confirmation_window_seconds} set={v=>setData({...data,settings:{...settings,confirmation_window_seconds:v}})}/><NumberField label="Automatische Sperre · Minuten" value={settings.auto_block_minutes} set={v=>setData({...data,settings:{...settings,auto_block_minutes:v}})}/><NumberField label="Notfalllimit pro Minute" value={settings.emergency_rpm} set={v=>setData({...data,settings:{...settings,emergency_rpm:v}})}/></div>
      <Field label="Geschützte Pfad-Präfixe · eine Zeile je Pfad"><textarea className="input min-h-24 font-mono" value={(settings.protected_paths||[]).join("\n")} onChange={e=>setData({...data,settings:{...settings,protected_paths:e.target.value.split(/\n|,/).map(v=>v.trim()).filter(Boolean)}})}/></Field>
      <Field label="Länder-Blockliste · ISO-Codes"><input className="input" value={(settings.country_blocklist||[]).join(", ")} onChange={e=>setData({...data,settings:{...settings,country_blocklist:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)}})}/></Field>
      <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/[.05] p-4 text-xs leading-5 text-amber-200">Eine Grenzwertüberschreitung ist zunächst nur ein Alarm. Ohne „Automatisch sperren“ wird unabhängig von der Anzahl der Alarme niemals automatisch eine Regel erstellt.</div><button onClick={saveSettings} className="primary mt-4"><Save className="h-4 w-4"/>Schutzprofil speichern</button>
    </Panel>}

    {tab==="events" && <Panel title="90-Tage-Ereignisverlauf" icon={Clock3}><div className="mb-4 flex gap-2"><div className="relative flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-600"/><input className="input pl-9" value={query} onChange={e=>setQuery(e.target.value)} placeholder="IP, Nutzer-ID, Pfad oder Kategorie suchen"/></div><button onClick={()=>load()} className="secondary"><RefreshCw className="h-4 w-4"/></button></div><div className="space-y-2">{events.map(event => <EventRow key={event.id} event={event} onStop={setConfirmEvent} onAnalyze={analyze}/>)}</div></Panel>}

    {tab==="diagnostics" && <div className="grid gap-4 lg:grid-cols-2"><Panel title="Eigene API prüfen" icon={Bot}><p className="text-sm leading-6 text-slate-400">Der Diagnoseaufruf läuft über BFF und FastAPI. Firewall-Verwaltungsrouten sind self-exempt und können sich nicht selbst als <code>blocked_ip</code> markieren.</p><button onClick={runDiagnostics} className="primary mt-5"><Activity className="h-4 w-4"/>Diagnose starten</button>{diagnostics && <Result allowed={diagnostics.status==="healthy"} title="API und Firewall erreichbar" text={`${diagnostics.active_rules} aktive Regeln · ${diagnostics.retention_days} Tage Verlauf · KI-Enforcement: nein`}/>}</Panel><Panel title="Engine-Status" icon={ShieldCheck}><div className="space-y-3"><StatusLine label="Erkennung" value="Deterministisch"/><StatusLine label="Firewall-Self-Protection" value="Aktiv"/><StatusLine label="Interne lokale API" value="Nicht flaggbar"/><StatusLine label="Automatische Sperren" value={settings.auto_block_enabled?"Aktiv":"Aus – nur Alarm"}/><StatusLine label="Speicherung" value="90 Tage"/></div></Panel></div>}

    {confirmEvent && <Modal close={()=>setConfirmEvent(null)}><Shield className="h-8 w-8 text-red-300"/><h3 className="mt-4 text-xl font-black text-white">Quelle wirklich sperren?</h3><p className="mt-2 text-sm leading-6 text-slate-400">IP <code>{confirmEvent.ip}</code> wird dauerhaft gesperrt. Interne Netze werden serverseitig abgelehnt. Die Regel kann jederzeit im Bereich „Sperren & Entsperren“ aufgehoben werden.</p><div className="mt-6 flex justify-end gap-2"><button onClick={()=>setConfirmEvent(null)} className="secondary">Abbrechen</button><button onClick={stopAttack} className="danger">Manuell sperren</button></div></Modal>}
    {report && <Modal close={()=>setReport(null)}><BrainCircuit className="h-8 w-8 text-violet-300"/><h3 className="mt-4 text-xl font-black text-white">Grok-Bericht</h3><p className="mt-1 text-xs text-amber-300">Nur Beratung. Keine Regel oder Aktion wurde durch KI ausgeführt.</p><pre className="mt-5 whitespace-pre-wrap rounded-xl border border-slate-800 bg-black/20 p-4 font-sans text-sm leading-6 text-slate-300">{report.report}</pre></Modal>}

    <style jsx global>{`.input{width:100%;border:1px solid rgb(51 65 85);background:#09090c;border-radius:.75rem;padding:.72rem .8rem;color:white;font-size:.875rem;outline:none}.input:focus{border-color:rgba(34,211,238,.55)}.primary,.secondary,.danger{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;border-radius:.75rem;padding:.72rem 1rem;font-size:.8rem;font-weight:800}.primary{background:rgb(34 211 238);color:#071014}.secondary{border:1px solid rgb(51 65 85);color:rgb(203 213 225)}.danger{background:rgb(239 68 68);color:white}`}</style>
  </div>;
}

function Panel({title,icon:Icon,children}:{title:string;icon:any;children:React.ReactNode}) { return <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><div className="mb-5 flex items-center gap-2"><Icon className="h-5 w-5 text-cyan-300"/><h3 className="font-black text-white">{title}</h3></div>{children}</section>; }
function Metric({icon:Icon,label,value}:{icon:any;label:string;value:any}) { return <div className="rounded-2xl border border-slate-800 bg-[#131318] p-4"><Icon className="h-4 w-4 text-cyan-300"/><p className="mt-3 text-2xl font-black text-white">{value || 0}</p><p className="text-xs text-slate-500">{label}</p></div>; }
function Status({active,label}:{active:boolean;label:string}) { return <span className={cn("h-fit whitespace-nowrap rounded-full border px-3 py-2 text-[11px] font-black",active?"border-emerald-500/25 bg-emerald-500/10 text-emerald-300":"border-amber-500/25 bg-amber-500/10 text-amber-300")}>{label}</span>; }
function Guarantee({title,text}:{title:string;text:string}) { return <div className="flex gap-3 rounded-xl border border-slate-800 p-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"/><div><p className="text-sm font-bold text-white">{title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{text}</p></div></div>; }
function Field({label,children}:{label:string;children:React.ReactNode}) { return <label className="mt-4 block text-xs font-bold text-slate-500">{label}<div className="mt-2">{children}</div></label>; }
function NumberField({label,value,set}:{label:string;value:number;set:(value:number)=>void}) { return <Field label={label}><input className="input" type="number" min="1" value={value} onChange={event=>set(Number(event.target.value))}/></Field>; }
function Toggle({label,text,value,set,danger=false}:{label:string;text:string;value:boolean;set:(value:boolean)=>void;danger?:boolean}) { return <button onClick={()=>set(!value)} className={cn("flex items-center gap-3 rounded-xl border p-4 text-left",value?(danger?"border-amber-500/25 bg-amber-500/[.05]":"border-cyan-500/25 bg-cyan-500/[.05]"):"border-slate-800")}><span className={cn("h-5 w-9 shrink-0 rounded-full p-0.5",value?(danger?"bg-amber-500":"bg-cyan-500"):"bg-slate-700")}><span className={cn("block h-4 w-4 rounded-full bg-white transition",value&&"translate-x-4")}/></span><span><strong className="block text-sm text-white">{label}</strong><small className="text-slate-500">{text}</small></span></button>; }
function RuleRow({rule,remove}:{rule:Rule;remove:(rule:Rule)=>void}) { const allow=rule.kind==="allow"||rule.kind==="user_allow"; return <div className="flex items-center gap-3 rounded-xl border border-slate-800 p-3"><span className={cn("rounded-lg px-2 py-1 text-[10px] font-black",allow?"bg-emerald-500/10 text-emerald-300":"bg-red-500/10 text-red-300")}>{ruleNames[rule.kind] || rule.kind}</span><div className="min-w-0 flex-1"><p className="truncate font-mono text-sm text-white">{rule.value}</p><p className="truncate text-xs text-slate-600">{rule.note || "Keine Notiz"} · {rule.expires_at?`bis ${fmt(rule.expires_at)}`:"dauerhaft"}</p></div><button title="Regel entfernen / entsperren" onClick={()=>remove(rule)} className="rounded-lg p-2 text-slate-600 hover:bg-red-500/10 hover:text-red-300">{allow?<Trash2 className="h-4 w-4"/>:<Undo2 className="h-4 w-4"/>}</button></div>; }
function EventRow({event,onStop,onAnalyze}:{event:Event;onStop:(event:Event)=>void;onAnalyze:(event:Event)=>void}) { return <div className="rounded-xl border border-slate-800 bg-black/10 p-3"><div className="flex flex-wrap items-center gap-2"><span className={cn("rounded-md px-2 py-1 text-[10px] font-black",event.blocked?"bg-red-500/10 text-red-300":event.category==="rate_alarm"?"bg-amber-500/10 text-amber-300":"bg-slate-800 text-slate-400")}>{event.blocked?"blockiert":"nur Alarm"}</span><code className="text-xs text-white">{event.ip}</code>{event.actor_id&&<span className="text-[10px] text-cyan-300">User {event.actor_id}</span>}<span className="ml-auto text-[10px] text-slate-600">{fmt(event.created_at)}</span></div><p className="mt-2 break-all text-xs text-slate-400">{event.method} {event.path} · {event.category} · {event.request_count} Anfragen</p><div className="mt-3 flex gap-2"><button onClick={()=>onStop(event)} className="danger !px-3 !py-2 !text-[11px]">Quelle sperren</button><button onClick={()=>onAnalyze(event)} className="secondary !px-3 !py-2 !text-[11px]"><BrainCircuit className="h-3 w-3"/>Grok-Bericht</button></div></div>; }
function Empty({text}:{text:string}) { return <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center"><CheckCircle2 className="mx-auto h-6 w-6 text-emerald-400"/><p className="mt-2 text-sm text-slate-500">{text}</p></div>; }
function Result({allowed,title,text}:{allowed:boolean;title:string;text:string}) { return <div className={cn("mt-4 rounded-xl border p-4",allowed?"border-emerald-500/20 bg-emerald-500/[.05]":"border-red-500/20 bg-red-500/[.05]")}><p className={cn("text-sm font-black",allowed?"text-emerald-300":"text-red-300")}>{title}</p><p className="mt-1 text-xs text-slate-400">{text}</p></div>; }
function StatusLine({label,value}:{label:string;value:string}) { return <div className="flex items-center justify-between rounded-xl border border-slate-800 p-3"><span className="text-sm text-slate-400">{label}</span><span className="text-xs font-black text-emerald-300">{value}</span></div>; }
function Modal({close,children}:{close:()=>void;children:React.ReactNode}) { return <div className="fixed inset-0 z-[10050] grid place-items-center bg-black/80 p-4 backdrop-blur-sm"><div className="relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-700 bg-[#131318] p-6"><button onClick={close} className="absolute right-4 top-4 text-slate-500 hover:text-white"><X className="h-5 w-5"/></button>{children}</div></div>; }
