"use client";

import React from "react";
import { Activity, BarChart3, MessageSquare, Sparkles, Trophy } from "lucide-react";

function number(value: number) {
  return Number(value || 0).toLocaleString("de-DE");
}

export function AccountActivityPanel({ activity }: { activity: any }) {
  const [days, setDays] = React.useState<7 | 30>(7);
  const daily = Array.isArray(activity?.daily) ? activity.daily.slice(-days) : [];
  const maxMessages = Math.max(1, ...daily.map((item: any) => Number(item.messages || 0)));
  const progress = activity?.best_progress;
  const active = activity?.active_guild;
  const knownDays = daily.filter((item: any) => item.known).length;

  return (
    <section id="aktivitaet" className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div><div className="flex items-center gap-2 text-emerald-300"><Activity className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.2em]">Persönlicher Aktivitätsverlauf</span></div><h2 className="mt-2 text-xl font-bold text-white">XP und Nachrichten</h2><p className="mt-1 text-sm text-slate-500">Nur tatsächlich seit Einführung des Verlaufs gemessene Werte.</p></div>
        <div className="flex w-fit rounded-xl border border-slate-800 bg-black/20 p-1">{([7, 30] as const).map(value => <button key={value} type="button" onClick={() => setDays(value)} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${days === value ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-white"}`}>{value} Tage</button>)}</div>
      </div>

      <div className="grid gap-px bg-slate-800 sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-[#111116] p-5"><Sparkles className="h-4 w-4 text-indigo-400" /><p className="mt-3 text-xs text-slate-600">XP in 7 Tagen</p><p className="mt-1 text-xl font-bold text-white">{number(activity?.xp_7d)}</p></div>
        <div className="bg-[#111116] p-5"><BarChart3 className="h-4 w-4 text-cyan-400" /><p className="mt-3 text-xs text-slate-600">XP in 30 Tagen</p><p className="mt-1 text-xl font-bold text-white">{number(activity?.xp_30d)}</p></div>
        <div className="bg-[#111116] p-5"><MessageSquare className="h-4 w-4 text-emerald-400" /><p className="mt-3 text-xs text-slate-600">Nachrichten in {days} Tagen</p><p className="mt-1 text-xl font-bold text-white">{number(days === 7 ? activity?.messages_7d : activity?.messages_30d)}</p></div>
        <div className="bg-[#111116] p-5"><Trophy className="h-4 w-4 text-amber-400" /><p className="mt-3 text-xs text-slate-600">Aktivster Server</p><p className="mt-1 truncate text-base font-bold text-white">{active?.guild_name || (active?.guild_id ? `Server ${active.guild_id}` : "Noch keiner")}</p><p className="mt-1 text-xs text-slate-600">{active?.measured ? `${number(active.messages)} gemessene Nachrichten` : active ? "zuletzt verwendeter Server" : "keine Aktivität"}</p></div>
      </div>

      <div className="grid border-t border-slate-800 lg:grid-cols-[1.4fr_1fr] lg:divide-x lg:divide-slate-800">
        <div className="p-5 sm:p-6"><div className="flex items-baseline justify-between gap-4"><h3 className="font-bold text-white">Nachrichtenaktivität</h3><span className="text-xs text-slate-600">{knownDays} von {days} Tagen gemessen</span></div>
          <div className="mt-6 flex h-36 items-end gap-1" role="img" aria-label={`Nachrichtenaktivität der letzten ${days} Tage`}>
            {daily.map((item: any) => {
              const height = item.known ? Math.max(item.messages ? 8 : 3, Number(item.messages || 0) / maxMessages * 100) : 3;
              const stamp = new Date(Number(item.day) * 86400000).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
              return <div key={item.day} className="group relative flex h-full min-w-0 flex-1 items-end"><div className={`w-full rounded-t-sm transition-colors ${item.known ? item.messages ? "bg-indigo-500/75 group-hover:bg-indigo-400" : "bg-slate-700" : "bg-slate-800"}`} style={{ height: `${height}%` }} /><span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-lg border border-slate-700 bg-[#0b0b0e] px-2 py-1 text-[10px] text-slate-300 shadow-xl group-hover:block">{stamp}: {item.known ? `${number(item.messages)} Nachrichten · ${number(item.xp)} XP` : "nicht gemessen"}</span></div>;
            })}
          </div>
          {!activity?.recorded_since && <p className="mt-4 rounded-xl border border-slate-800 bg-black/20 p-3 text-xs leading-5 text-slate-500">Der Verlauf beginnt mit deiner nächsten Leveling-Nachricht. Frühere Tageswerte werden nicht erfunden oder aus dem aktuellen Gesamtstand zurückgerechnet.</p>}
        </div>

        <div className="border-t border-slate-800 p-5 sm:p-6 lg:border-t-0"><h3 className="font-bold text-white">Fortschritt zum nächsten Level</h3>{progress ? <><div className="mt-4 flex items-end justify-between gap-4"><div><p className="text-3xl font-black text-white">Level {progress.level}</p><p className="mt-1 text-xs text-slate-500">{progress.guild_name || `Server ${progress.guild_id}`}</p></div><span className="text-sm font-bold text-indigo-300">{progress.percent.toLocaleString("de-DE")} %</span></div><div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-cyan-400" style={{ width: `${Math.max(0, Math.min(100, progress.percent))}%` }} /></div><div className="mt-2 flex justify-between text-xs text-slate-600"><span>{number(progress.current)} XP</span><span>{number(progress.needed)} XP benötigt</span></div></> : <p className="mt-4 text-sm leading-6 text-slate-500">Sobald du auf einem Server XP sammelst, erscheint hier dein stärkster Level-Fortschritt.</p>}</div>
      </div>
    </section>
  );
}
