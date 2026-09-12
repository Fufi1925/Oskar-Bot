"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { BadgeCheck, Bot, Clock3, Crown, Database, Loader2, Lock, Power, RefreshCw, Server, ShieldCheck, Snowflake, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const FEATURES = [
  [Bot, "Server-Design", "Name, Avatar und Banner des Bots"],
  [Database, "Backups", "Erweiterte Sicherungen und Automatik"],
  [Users, "Server-Stats", "Automatisch aktualisierte Statistikkanäle"],
  [RefreshCw, "User Pull", "Owner-geschützter Mitglieder-Pull"],
  [Sparkles, "Ticket-KI", "Wenn der Server zusätzlich freigeschaltet ist"],
  [ShieldCheck, "Weitere Bereiche", "Speedrun, Vorlagen und höhere Limits"],
] as const;

const date = (value?: number | null) => value ? new Date(value * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : "–";
const daysLeft = (value?: number | null) => value ? Math.max(0, Math.ceil((value * 1000 - Date.now()) / 86_400_000)) : 0;

export function ServerPremiumPanel({ guildId }: { guildId: string }) {
  const [state, setState] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setState(await api.getServerPremium(guildId)); }
    catch (error: any) { toast.error(error?.message || "Premiumstatus konnte nicht geladen werden."); }
  }, [guildId]);
  useEffect(() => { void load(); }, [load]);
  const remaining = daysLeft(state?.expires_at);
  const status = useMemo(() => state?.active ? { label: "Premium aktiv", text: `${remaining} Tage verbleibend`, tone: "emerald" } : state?.frozen ? { label: "Premium eingefroren", text: "Bestehende Funktionen laufen, Bearbeitung gesperrt", tone: "blue" } : { label: "Kein Server-Premium", text: "Dieser Server belegt keinen aktiven Premium-Platz", tone: "slate" }, [state, remaining]);

  const choose = async (action: "keep" | "disable") => {
    setBusy(true);
    try { setState(await api.setServerPremiumExpiryAction(guildId, action)); toast.success("Ablaufverhalten gespeichert."); }
    catch (error: any) { toast.error(error?.message || "Speichern fehlgeschlagen."); }
    finally { setBusy(false); }
  };

  if (!state) return <div className="grid min-h-64 place-items-center"><Loader2 className="h-7 w-7 animate-spin text-amber-400"/></div>;

  return <div className={cn("space-y-5", busy && "pointer-events-none opacity-70")}>
    <section className="relative overflow-hidden rounded-3xl border border-amber-400/20 bg-[#131318] p-5 sm:p-7">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_90%_0%,rgba(251,191,36,.14),transparent_40%)]"/>
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-400/10"><Crown className="h-6 w-6 text-amber-300"/></span><div><p className="text-xs font-black uppercase tracking-[.18em] text-amber-300">Premiumserver</p><h2 className="mt-1 text-2xl font-black text-white">{state.guild_name}</h2><p className="mt-1 text-sm text-slate-500">Premium gilt serverbezogen – unabhängig davon, wer die Einstellungen verwaltet.</p></div></div>
        <span className={cn("w-fit rounded-full border px-3 py-1.5 text-xs font-black",status.tone==="emerald"&&"border-emerald-500/25 bg-emerald-500/10 text-emerald-300",status.tone==="blue"&&"border-blue-500/25 bg-blue-500/10 text-blue-300",status.tone==="slate"&&"border-slate-700 bg-black/20 text-slate-400")}>{status.label}</span>
      </div>
      <div className="relative mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Fact icon={BadgeCheck} label="Status" value={status.label} detail={status.text}/><Fact icon={Clock3} label="Laufzeit bis" value={date(state.expires_at)} detail={state.active ? `${remaining} Tage übrig` : "Keine aktive Laufzeit"}/><Fact icon={Server} label="Fester Platz" value={state.assigned ? `Platz ${state.slot_no} von 3` : "Nicht zugeordnet"} detail={state.assigned ? `Seit ${date(state.assigned_at)}` : "Über das Premium-Konto einlösen"}/><Fact icon={Crown} label="Premium-Konto" value={state.account_user_id || "Nicht vorhanden"} detail={state.assigned ? "Discord-Konto der Zuweisung" : "Noch kein Platz eingelöst"}/></div>
      {state.active && <div className="relative mt-5"><div className="mb-2 flex justify-between text-xs"><span className="font-bold text-slate-400">Aktive Restlaufzeit</span><span className="text-amber-300">{remaining} Tage</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-yellow-300" style={{width:`${Math.max(3,Math.min(100,(remaining/Math.max(1,state.duration_days||1))*100))}%`}}/></div></div>}
    </section>

    {!state.assigned && <section className="rounded-2xl border border-dashed border-slate-700 bg-[#111116] p-6 text-center"><Lock className="mx-auto h-8 w-8 text-slate-600"/><h3 className="mt-3 text-lg font-black text-white">Dieser Server hat noch kein Premium</h3><p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">Ein aktives Premium-Konto besitzt drei feste Plätze. Öffne deine Premiumverwaltung, wähle diesen Server aus und bestätige die dauerhafte Zuweisung für die aktuelle Laufzeit.</p><Link href="/dashboard/premium" className="mt-5 inline-flex rounded-xl bg-amber-400 px-5 py-3 text-sm font-black text-black">Premiumplatz einlösen</Link></section>}

    <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5 sm:p-6"><div className="flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-violet-300"/><div><h3 className="font-black text-white">Premiumfunktionen dieses Servers</h3><p className="text-xs text-slate-500">Jeder mit Dashboard-Zugriff darf sie konfigurieren; bestehende Owner-only-Regeln bleiben bestehen.</p></div></div><div className="mt-4 grid gap-2 md:grid-cols-2 lg:grid-cols-3">{FEATURES.map(([Icon,title,text])=><div key={title} className={cn("flex gap-3 rounded-xl border p-3.5",state.runtime?"border-violet-500/15 bg-violet-500/[0.04]":"border-slate-800 opacity-55")}><Icon className={cn("mt-0.5 h-4 w-4 shrink-0",state.runtime?"text-violet-300":"text-slate-600")}/><div><p className="text-sm font-bold text-white">{title}</p><p className="mt-0.5 text-xs leading-5 text-slate-500">{text}</p></div></div>)}</div></section>

    {state.assigned && <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5 sm:p-6"><div className="flex items-center gap-3"><Power className="h-5 w-5 text-amber-300"/><div><h3 className="font-black text-white">Verhalten nach Ablauf</h3><p className="text-xs text-slate-500">Die Auswahl verändert oder löscht keine gespeicherten Einstellungen und Daten.</p></div></div><div className="mt-4 grid gap-3 md:grid-cols-2"><Choice active={state.expiry_action==="keep"} onClick={()=>choose("keep")} icon={Snowflake} title="Eingefroren weiterlaufen" badge="Empfohlen" text="Bereits eingerichtete Premiumfunktionen laufen unverändert weiter. Bis zur Verlängerung kann niemand Einstellungen ändern oder neue Premiumfunktionen einrichten."/><Choice active={state.expiry_action==="disable"} onClick={()=>choose("disable")} icon={Power} title="Beim Ablauf deaktivieren" text="Alle Premiumfunktionen stoppen. Einstellungen und Inhalte bleiben gespeichert und stehen nach einer Verlängerung wieder bereit."/></div>{state.frozen&&<div className="mt-4 flex gap-2 rounded-xl border border-blue-500/20 bg-blue-500/[0.06] p-4 text-xs leading-5 text-blue-200"><Lock className="mt-0.5 h-4 w-4 shrink-0"/><span><strong>Konfiguration eingefroren:</strong> Die bestehende Einrichtung läuft weiter, kann derzeit aber nicht bearbeitet werden.</span></div>}</section>}
  </div>;
}

function Fact({icon:Icon,label,value,detail}:{icon:any,label:string,value:string,detail:string}){return <div className="rounded-2xl border border-slate-800 bg-black/20 p-4"><Icon className="h-4 w-4 text-amber-300"/><p className="mt-3 text-[10px] font-black uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 truncate text-sm font-black text-white">{value}</p><p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p></div>}
function Choice({active,onClick,icon:Icon,title,text,badge}:{active:boolean,onClick:()=>void,icon:any,title:string,text:string,badge?:string}){return <button onClick={onClick} className={cn("relative rounded-2xl border p-5 text-left transition",active?"border-amber-400/40 bg-amber-400/[0.08]":"border-slate-800 hover:border-slate-700")}><div className="flex items-start justify-between"><Icon className="h-5 w-5 text-amber-300"/>{active?<BadgeCheck className="h-5 w-5 text-emerald-400"/>:badge?<span className="rounded-full bg-amber-400/10 px-2 py-1 text-[10px] font-black text-amber-300">{badge}</span>:null}</div><p className="mt-3 font-black text-white">{title}</p><p className="mt-1 text-xs leading-5 text-slate-400">{text}</p></button>}
