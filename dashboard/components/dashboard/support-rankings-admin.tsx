"use client";

import React from "react";
import { Award, BarChart3, CheckCircle2, ChevronDown, Clock3, Gauge, LifeBuoy, Loader2, Medal, MessageSquare, RefreshCw, Search, SlidersHorizontal, Star, Target, Trophy, Users, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

function dauer(seconds: number) {
  if (!seconds) return "Keine Daten";
  if (seconds < 60) return `${seconds} Sek.`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} Min.`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} Std.`;
  return `${(seconds / 86400).toFixed(1)} Tage`;
}

const PERIODS = [[30, "30 Tage"], [90, "90 Tage"], [365, "1 Jahr"], [0, "Gesamt"]] as const;
const MEDALS = [
  { icon: Trophy, color: "text-amber-300", bg: "border-amber-400/25 bg-amber-400/10", label: "Platz 1" },
  { icon: Medal, color: "text-slate-200", bg: "border-slate-300/20 bg-slate-300/10", label: "Platz 2" },
  { icon: Award, color: "text-orange-300", bg: "border-orange-400/20 bg-orange-400/10", label: "Platz 3" },
];

type Sort = "rating" | "cases" | "satisfaction" | "speed";

export function SupportRankingsAdmin() {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [period, setPeriod] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<Sort>("rating");
  const [ratedOnly, setRatedOnly] = React.useState(false);
  const [open, setOpen] = React.useState<Record<string, boolean>>({});

  const laden = React.useCallback(async () => {
    setLoading(true);
    try { setData(await api.getAdminSupportRankings(period)); }
    catch (error: any) { toast.error(error?.message || "Support-Rankings konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, [period]);
  React.useEffect(() => { laden(); }, [laden]);

  const summary = data?.summary || {};
  const ranking = React.useMemo(() => data?.ranking || [], [data]);
  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...ranking]
      .filter((agent: any) => !ratedOnly || agent.ratings_count > 0)
      .filter((agent: any) => !needle || [agent.supporter_name, agent.supporter_id, agent.supporter_role].some((value) => String(value || "").toLowerCase().includes(needle)))
      .sort((a: any, b: any) => {
        if (sort === "cases") return b.total_cases - a.total_cases || b.average_rating - a.average_rating;
        if (sort === "satisfaction") return b.satisfaction_percent - a.satisfaction_percent || b.ratings_count - a.ratings_count;
        if (sort === "speed") return (a.average_response_seconds || Number.MAX_SAFE_INTEGER) - (b.average_response_seconds || Number.MAX_SAFE_INTEGER);
        return b.average_rating - a.average_rating || b.ratings_count - a.ratings_count || b.closed - a.closed;
      });
  }, [ranking, query, ratedOnly, sort]);
  const podium = ranking.filter((agent: any) => agent.ratings_count > 0).slice(0, 3);
  const mostCases = [...ranking].sort((a: any, b: any) => b.total_cases - a.total_cases)[0];
  const fastest = [...ranking].filter((agent: any) => agent.average_response_seconds > 0).sort((a: any, b: any) => a.average_response_seconds - b.average_response_seconds)[0];
  const sortLabel: Record<Sort, string> = { rating: "Sterne", cases: "Fallzahl", satisfaction: "Zufriedenheit", speed: "Annahmezeit" };

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl border border-amber-400/20 bg-[linear-gradient(135deg,rgba(245,158,11,.12),rgba(15,15,22,.96)_55%)] p-6 sm:p-7">
        <div aria-hidden className="absolute -right-16 -top-24 h-72 w-72 rounded-full bg-amber-400/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start gap-4"><span className="grid h-12 w-12 place-items-center rounded-2xl border border-amber-300/20 bg-amber-400/10"><Trophy className="h-6 w-6 text-amber-300" /></span><div className="min-w-0 flex-1"><p className="text-xs font-black uppercase tracking-[.16em] text-amber-300">Support-Leistung</p><h2 className="mt-1 text-2xl font-black text-white">Rankings und Qualitätsanalyse</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Ausschließlich echte, abgeschlossene Supportfälle und Bewertungen der tatsächlichen Serverinhaber. Keine erfundenen Punkte und keine Bewertung für offene Fälle.</p></div><button onClick={laden} className="grid h-10 w-10 place-items-center rounded-xl border border-slate-700 text-slate-400 hover:text-white"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></div>
        <div className="relative mt-5 flex flex-wrap gap-2">{PERIODS.map(([days,label])=><button key={days} onClick={()=>setPeriod(days)} className={`rounded-lg border px-3 py-2 text-xs font-bold ${period===days?"border-amber-400/30 bg-amber-400/10 text-amber-200":"border-slate-800 bg-black/10 text-slate-500 hover:text-slate-300"}`}>{label}</button>)}</div>
      </section>

      {loading ? <div className="grid min-h-56 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-amber-400" /></div> : <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          {[[Users,"Supporter",summary.supporters||0],[LifeBuoy,"Fälle",summary.cases||0],[Clock3,"Wartend",summary.pending||0],[Gauge,"Aktiv",summary.active||0],[CheckCircle2,"Geschlossen",summary.closed||0],[MessageSquare,"Bewertungen",summary.ratings||0],[Star,"Ø Sterne",summary.average_rating?`${summary.average_rating}/10`:"—"],[Target,"Zufrieden",`${summary.satisfaction_percent||0}%`]].map(([Icon,label,value])=>{const I=Icon as React.ElementType;return <div key={String(label)} className="rounded-2xl border border-slate-800 bg-[#131318] p-4"><I className="h-4 w-4 text-amber-300"/><p className="mt-3 text-lg font-black text-white">{value as React.ReactNode}</p><p className="mt-1 text-[11px] text-slate-500">{label as string}</p></div>})}
        </div>

        {(podium.length > 0 || mostCases || fastest) && <section className="rounded-3xl border border-slate-800 bg-[#111116] p-5 sm:p-6"><div className="flex items-center gap-3"><BarChart3 className="h-5 w-5 text-indigo-300"/><div><h3 className="font-black text-white">Team auf einen Blick</h3><p className="text-xs text-slate-500">Spitzenplätze und messbare Arbeitsdaten im gewählten Zeitraum.</p></div></div><div className="mt-5 grid gap-3 lg:grid-cols-3">{podium.map((agent:any,index:number)=>{const medal=MEDALS[index];const Icon=medal.icon;return <div key={agent.supporter_id} className={`rounded-2xl border p-4 ${medal.bg}`}><div className="flex items-center gap-3"><Icon className={`h-5 w-5 ${medal.color}`}/>{agent.supporter_avatar?<img src={agent.supporter_avatar} alt="" className="h-10 w-10 rounded-full object-cover"/>:<span className="grid h-10 w-10 place-items-center rounded-full bg-black/20 font-black text-white">{String(agent.supporter_name||"?")[0]}</span>}<div className="min-w-0"><p className="truncate text-sm font-black text-white">{medal.label} · {agent.supporter_name}</p><p className="text-xs" style={{color:agent.supporter_role_color}}>{agent.supporter_role}</p></div></div><p className="mt-4 flex items-end gap-2 text-3xl font-black text-amber-300"><Star className="mb-1 h-5 w-5 fill-amber-300"/>{agent.average_rating.toFixed(2)}<span className="mb-1 text-xs font-normal text-slate-500">/10 · {agent.ratings_count} Stimmen</span></p></div>})}</div><div className="mt-3 grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-[10px] text-slate-600">Meiste Fälle</p><p className="mt-1 text-sm font-bold text-white">{mostCases?`${mostCases.supporter_name} · ${mostCases.total_cases}`:"—"}</p></div><div className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-[10px] text-slate-600">Schnellste Ø Annahme</p><p className="mt-1 text-sm font-bold text-white">{fastest?`${fastest.supporter_name} · ${dauer(fastest.average_response_seconds)}`:"—"}</p></div><div className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-[10px] text-slate-600">Bewertungsabdeckung</p><p className="mt-1 text-sm font-bold text-white">{summary.rating_coverage_percent||0}% der geschlossenen Fälle</p></div></div></section>}

        <section className="rounded-2xl border border-slate-800 bg-[#111116] p-3 sm:p-4"><div className="flex flex-col gap-3 lg:flex-row"><div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-600"/><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Supporter, Discord-ID oder Rolle suchen …" className="w-full rounded-xl border border-slate-800 bg-[#09090c] py-2.5 pl-9 pr-4 text-sm text-white outline-none focus:border-amber-500/40"/></div><button onClick={()=>setRatedOnly((value)=>!value)} className={`rounded-xl border px-4 py-2.5 text-xs font-bold ${ratedOnly?"border-amber-400/30 bg-amber-400/10 text-amber-200":"border-slate-800 text-slate-500"}`}>Nur mit Bewertung</button><button onClick={()=>setSort(sort==="rating"?"cases":sort==="cases"?"satisfaction":sort==="satisfaction"?"speed":"rating")} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-800 px-4 py-2.5 text-xs font-bold text-slate-400"><SlidersHorizontal className="h-3.5 w-3.5"/>Sortiert nach {sortLabel[sort]}</button></div><p className="mt-3 px-1 text-[11px] text-slate-600">{visible.length} von {ranking.length} Supportern sichtbar</p></section>

        {!visible.length && <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500">Keine Supporter passen zu dieser Auswahl.</div>}
        <div className="space-y-3">{visible.map((agent:any)=>{const expanded=Boolean(open[agent.supporter_id]);const medal=MEDALS[agent.rank-1];const MedalIcon=medal?.icon||Award;return <section key={agent.supporter_id} className="overflow-hidden rounded-2xl border border-slate-800 bg-[#111116]"><button onClick={()=>setOpen((old)=>({...old,[agent.supporter_id]:!expanded}))} className="flex w-full flex-wrap items-center gap-4 p-5 text-left"><span className={`grid h-11 w-11 place-items-center rounded-xl border ${medal?.bg||"border-slate-800 bg-black/20"}`}><MedalIcon className={`h-5 w-5 ${medal?.color||"text-slate-500"}`}/></span>{agent.supporter_avatar?<img src={agent.supporter_avatar} alt="" className="h-12 w-12 rounded-full object-cover ring-2 ring-white/10"/>:<span className="grid h-12 w-12 place-items-center rounded-full bg-indigo-500/10 font-black text-indigo-300">{String(agent.supporter_name||"?")[0]}</span>}<div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2"><h4 className="truncate font-black text-white">#{agent.rank} {agent.supporter_name||agent.supporter_id}</h4>{agent.rank<=3&&agent.ratings_count>0&&<span className="rounded-full bg-amber-400/10 px-2 py-1 text-[9px] font-black uppercase text-amber-300">Top Support</span>}</div><p className="text-xs font-bold" style={{color:agent.supporter_role_color}}>{agent.supporter_role}</p><p className="mt-1 text-[10px] tabular-nums text-slate-600">{agent.supporter_id}</p></div><div className="grid grid-cols-3 gap-5 text-right"><div><p className="font-black text-white">{agent.total_cases}</p><p className="text-[10px] text-slate-600">Fälle</p></div><div><p className="font-black text-emerald-300">{agent.satisfaction_percent}%</p><p className="text-[10px] text-slate-600">Zufrieden</p></div><div><p className="flex items-center justify-end gap-1 font-black text-amber-300"><Star className="h-3.5 w-3.5 fill-amber-300"/>{agent.ratings_count?agent.average_rating.toFixed(2):"—"}</p><p className="text-[10px] text-slate-600">{agent.ratings_count} Stimmen</p></div></div><ChevronDown className={`h-5 w-5 text-slate-600 transition-transform ${expanded?"rotate-180":""}`}/></button>{expanded&&<div className="border-t border-slate-800"><div className="grid grid-cols-2 gap-px bg-slate-800 sm:grid-cols-4 lg:grid-cols-8">{[["Fälle",agent.total_cases],["Geschlossen",agent.closed],["Aktiv",agent.active],["Wartend",agent.pending],["Abgelehnt",agent.declined],["10 Sterne",agent.ten_star_ratings],["Abschlussquote",`${agent.completion_percent}%`],["Ø Annahme",dauer(agent.average_response_seconds)]].map(([label,value])=><div key={String(label)} className="bg-[#0e0e12] p-3"><p className="text-sm font-black text-white">{value}</p><p className="mt-1 text-[10px] text-slate-600">{label}</p></div>)}</div><div className="grid gap-5 p-5 lg:grid-cols-[1fr_.85fr]"><div><div className="flex justify-between text-xs"><span className="font-bold text-slate-300">Bewertungen 1–10</span><span className="text-emerald-300">{agent.satisfaction_percent}% positiv</span></div><div className="mt-4 flex h-24 items-end gap-1">{Array.from({length:10},(_,index)=>index+1).map((value)=>{const count=agent.rating_distribution?.[String(value)]||0;const max=Math.max(1,...Object.values(agent.rating_distribution||{}).map(Number));return <div key={value} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1"><span className="text-[9px] text-slate-600">{count||""}</span><div className="w-full rounded-t bg-amber-400/70" style={{height:`${Math.max(count?8:2,count/max*56)}px`}}/><span className="text-[9px] text-slate-600">{value}</span></div>})}</div></div><div><p className="text-xs font-bold text-slate-300">Letzte Rückmeldungen</p><div className="mt-2 max-h-48 space-y-2 overflow-y-auto">{agent.recent_feedback?.filter((item:any)=>item.note).map((item:any,index:number)=><div key={`${item.closed_at}-${index}`} className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-xs font-bold text-amber-300">{item.rating}/10 · {item.guild_name}</p><p className="mt-1 text-xs leading-5 text-slate-500">{item.note}</p></div>)}{!agent.recent_feedback?.some((item:any)=>item.note)&&<p className="rounded-xl border border-dashed border-slate-800 p-4 text-xs text-slate-600">Keine schriftliche Rückmeldung im Zeitraum.</p>}</div></div></div></div>}</section>})}</div>
        <p className="flex items-center gap-2 text-xs text-slate-600"><CheckCircle2 className="h-4 w-4"/>Sterne-Rangfolge: Durchschnitt, danach Anzahl der Bewertungen und abgeschlossene Fälle.</p>
      </>}
    </div>
  );
}
