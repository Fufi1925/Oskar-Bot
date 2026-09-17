"use client";

import React from "react";
import { Award, CheckCircle2, Clock3, LifeBuoy, Loader2, Medal, MessageSquare, RefreshCw, Star, Trophy, Users } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

function dauer(seconds: number) {
  if (!seconds) return "Noch keine Daten";
  if (seconds < 60) return `${seconds} Sek.`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} Min.`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} Std.`;
  return `${(seconds / 86400).toFixed(1)} Tage`;
}

const MEDALS = [
  { icon: Trophy, color: "text-amber-300", bg: "bg-amber-400/10 border-amber-400/20" },
  { icon: Medal, color: "text-slate-200", bg: "bg-slate-300/10 border-slate-300/20" },
  { icon: Award, color: "text-orange-300", bg: "bg-orange-400/10 border-orange-400/20" },
];

export function SupportRankingsAdmin() {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  const laden = React.useCallback(async () => {
    setLoading(true);
    try { setData(await api.getAdminSupportRankings()); }
    catch (error: any) { toast.error(error?.message || "Support-Rankings konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, []);
  React.useEffect(() => { laden(); }, [laden]);

  if (loading) return <div className="grid min-h-56 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-indigo-400" /></div>;
  const summary = data?.summary || {};
  const ranking = data?.ranking || [];

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-center gap-4 rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.05] p-5">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-500/10"><Trophy className="h-5 w-5 text-indigo-300" /></span>
        <div className="min-w-0 flex-1"><h3 className="font-bold text-white">Support-Rankings</h3><p className="mt-0.5 text-xs leading-5 text-slate-500">Echte Bewertungen der Serverinhaber nach geschlossenen Supportfällen. Unbewertete Fälle verändern den Sternedurchschnitt nicht.</p></div>
        <button onClick={laden} className="grid h-10 w-10 place-items-center rounded-xl border border-slate-700 text-slate-400 hover:text-white"><RefreshCw className="h-4 w-4" /></button>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[
          [Users, "Supporter", summary.supporters || 0],
          [LifeBuoy, "Fälle gesamt", summary.cases || 0],
          [Clock3, "Aktiv", summary.active || 0],
          [MessageSquare, "Bewertungen", summary.ratings || 0],
          [Star, "Ø Sterne", summary.average_rating ? `${summary.average_rating}/10` : "—"],
        ].map(([Icon, label, value]) => { const I = Icon as React.ElementType; return <div key={String(label)} className="rounded-2xl border border-slate-800 bg-[#131318] p-4"><I className="h-4 w-4 text-indigo-300" /><p className="mt-3 text-xl font-black text-white">{value as React.ReactNode}</p><p className="mt-1 text-xs text-slate-500">{label as string}</p></div>; })}
      </div>

      {!ranking.length && <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500">Noch keine Supportfälle für ein Ranking vorhanden.</div>}

      <div className="space-y-3">
        {ranking.map((agent: any) => {
          const medal = MEDALS[agent.rank - 1];
          const MedalIcon = medal?.icon || Award;
          return (
            <section key={agent.supporter_id} className="overflow-hidden rounded-2xl border border-slate-800 bg-[#111116]">
              <div className="flex flex-wrap items-center gap-4 p-5">
                <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl border ${medal?.bg || "border-slate-800 bg-black/20"}`}><MedalIcon className={`h-5 w-5 ${medal?.color || "text-slate-500"}`} /></span>
                {agent.supporter_avatar ? <img src={agent.supporter_avatar} alt="" className="h-12 w-12 rounded-full object-cover ring-2 ring-white/10" /> : <span className="grid h-12 w-12 place-items-center rounded-full bg-indigo-500/10 text-lg font-black text-indigo-300">{String(agent.supporter_name || "?").slice(0, 1)}</span>}
                <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h4 className="truncate font-black text-white">#{agent.rank} {agent.supporter_name || agent.supporter_id}</h4>{agent.rank <= 3 && agent.ratings_count > 0 && <span className="rounded-full bg-amber-400/10 px-2 py-1 text-[10px] font-black uppercase text-amber-300">Top Support</span>}</div><p className="mt-0.5 text-xs font-bold" style={{ color: agent.supporter_role_color }}>{agent.supporter_role}</p></div>
                <div className="text-right"><p className="flex items-center justify-end gap-1 text-2xl font-black text-amber-300"><Star className="h-5 w-5 fill-amber-300" />{agent.ratings_count ? agent.average_rating.toFixed(2) : "—"}</p><p className="text-[11px] text-slate-500">aus {agent.ratings_count} Bewertungen</p></div>
              </div>

              <div className="grid grid-cols-2 gap-px border-y border-slate-800 bg-slate-800 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  ["Fälle", agent.total_cases], ["Abgeschlossen", agent.closed], ["Aktiv", agent.active], ["Abgelehnt", agent.declined], ["10 Sterne", agent.ten_star_ratings], ["Ø Annahmezeit", dauer(agent.average_response_seconds)],
                ].map(([label, value]) => <div key={String(label)} className="bg-[#0e0e12] p-3"><p className="text-sm font-black text-white">{value}</p><p className="mt-1 text-[10px] text-slate-600">{label}</p></div>)}
              </div>

              <div className="grid gap-5 p-5 lg:grid-cols-[1fr_.8fr]">
                <div><div className="flex items-center justify-between text-xs"><span className="font-bold text-slate-300">Zufriedenheit</span><span className="text-emerald-300">{agent.satisfaction_percent}% mit 8–10 Sternen</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-emerald-400" style={{ width: `${agent.satisfaction_percent}%` }} /></div><div className="mt-4 flex h-16 items-end gap-1">{Array.from({ length: 10 }, (_, index) => index + 1).map((value) => { const count = agent.rating_distribution?.[String(value)] || 0; const max = Math.max(1, ...Object.values(agent.rating_distribution || {}).map(Number)); return <div key={value} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1"><div title={`${count} Bewertungen`} className="w-full rounded-t bg-amber-400/70" style={{ height: `${Math.max(count ? 8 : 2, count / max * 42)}px` }} /><span className="text-[9px] text-slate-600">{value}</span></div>; })}</div></div>
                <div><p className="text-xs font-bold text-slate-300">Letzte Rückmeldungen</p><div className="mt-2 space-y-2">{agent.recent_feedback?.filter((item: any) => item.note).slice(0, 3).map((item: any, index: number) => <div key={`${item.closed_at}-${index}`} className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-xs font-bold text-amber-300">{item.rating}/10 · {item.guild_name}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.note}</p></div>)}{!agent.recent_feedback?.some((item: any) => item.note) && <p className="rounded-xl border border-dashed border-slate-800 p-4 text-xs text-slate-600">Noch keine schriftliche Rückmeldung.</p>}</div></div>
              </div>
            </section>
          );
        })}
      </div>
      <p className="flex items-center gap-2 text-xs text-slate-600"><CheckCircle2 className="h-4 w-4" />Rankings werden ausschließlich aus abgeschlossenen und vom Serverinhaber bewerteten Fällen berechnet.</p>
    </div>
  );
}
