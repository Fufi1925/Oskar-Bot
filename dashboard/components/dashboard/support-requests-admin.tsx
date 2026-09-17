"use client";

import React from "react";
import Link from "next/link";
import { ExternalLink, LifeBuoy, Loader2, MessageSquare, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const FILTER = [
  ["all", "Alle"], ["pending", "Offen"], ["accepted", "Angenommen"], ["declined", "Abgelehnt"], ["closed", "Geschlossen"],
] as const;
const LABEL: Record<string, string> = { pending: "Offen", accepted: "Angenommen", declined: "Abgelehnt", closed: "Geschlossen" };
const COLOR: Record<string, string> = { pending: "border-amber-400/20 bg-amber-400/10 text-amber-300", accepted: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300", declined: "border-rose-400/20 bg-rose-400/10 text-rose-300", closed: "border-slate-700 bg-slate-800/60 text-slate-400" };

const zeit = (value: number) => value ? new Date(value * 1000).toLocaleString("de-DE") : "—";

export function SupportRequestsAdmin() {
  const [guildId, setGuildId] = React.useState("");
  const [problem, setProblem] = React.useState("");
  const [filter, setFilter] = React.useState("all");
  const [cases, setCases] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<Record<number, string>>({});

  const laden = React.useCallback(async () => {
    setLoading(true);
    try { setCases((await api.getAdminSupportCases(filter)).cases || []); }
    catch (error: any) { toast.error(error?.message || "Server-Anfragen konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, [filter]);
  React.useEffect(() => { laden(); }, [laden]);

  const anfragen = async () => {
    if (!/^\d{17,20}$/.test(guildId.trim())) return toast.error("Gib eine gültige Discord-Server-ID ein.");
    setSaving(true);
    try {
      await api.createSupportRequest(guildId.trim(), problem.trim());
      toast.success("Support-Anfrage wurde an den Serverinhaber gesendet.");
      setGuildId(""); setProblem(""); setFilter("all"); await laden();
    } catch (error: any) { toast.error(error?.message || "Support-Anfrage konnte nicht erstellt werden."); }
    finally { setSaving(false); }
  };

  const senden = async (id: number) => {
    const text = (message[id] || "").trim(); if (!text) return;
    setSaving(true);
    try { await api.addAdminSupportMessage(id, text); setMessage((old) => ({ ...old, [id]: "" })); await laden(); }
    catch (error: any) { toast.error(error?.message || "Notiz konnte nicht gesendet werden."); }
    finally { setSaving(false); }
  };

  const schliessen = async (id: number) => {
    setSaving(true);
    try { await api.closeAdminSupportCase(id); toast.success("Fall geschlossen; Support-Zugriff entzogen."); await laden(); }
    catch (error: any) { toast.error(error?.message || "Fall konnte nicht geschlossen werden."); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.05] p-5">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-500/10"><LifeBuoy className="h-5 w-5 text-indigo-300" /></span><div><h3 className="font-bold text-white">Server-Anfrage senden</h3><p className="text-xs text-slate-500">Nur Server, auf denen der Bot ist. Zugriff entsteht erst nach Zustimmung des tatsächlichen Serverinhabers.</p></div></div>
        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(220px,.45fr)_1fr_auto]">
          <input value={guildId} onChange={(e) => setGuildId(e.target.value.replace(/\D/g, ""))} placeholder="Discord-Server-ID" maxLength={20} className="rounded-xl border border-slate-800 bg-[#09090c] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500/50" />
          <input value={problem} onChange={(e) => setProblem(e.target.value)} placeholder="Kurze Nachricht zum Problem (optional)" maxLength={1000} className="rounded-xl border border-slate-800 bg-[#09090c] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500/50" />
          <button onClick={anfragen} disabled={saving} className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-5 py-3 text-sm font-bold text-white disabled:opacity-50"><Send className="h-4 w-4" />Support-Anfrage</button>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">{FILTER.map(([id, text]) => <button key={id} onClick={() => setFilter(id)} className={`rounded-lg border px-3 py-2 text-xs font-bold ${filter === id ? "border-indigo-400/30 bg-indigo-400/10 text-indigo-200" : "border-slate-800 text-slate-500"}`}>{text}</button>)}</div>
        <button onClick={laden} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-800 text-slate-500 hover:text-white"><RefreshCw className="h-4 w-4" /></button>
      </div>

      {loading && <div className="grid min-h-40 place-items-center"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /></div>}
      {!loading && cases.length === 0 && <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500">Keine Server-Anfragen in dieser Ansicht.</div>}
      {!loading && cases.map((fall) => (
        <section key={fall.id} className="overflow-hidden rounded-2xl border border-slate-800 bg-[#0f0f13]">
          <div className="flex flex-wrap items-start justify-between gap-4 p-5">
            <div className="flex items-center gap-3">
              {fall.guild_icon ? <img src={fall.guild_icon} alt="" className="h-11 w-11 rounded-xl object-cover" /> : <span className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-500/10"><ShieldCheck className="h-5 w-5 text-indigo-300" /></span>}
              <div><p className="font-bold text-white">{fall.guild_name}</p><p className="text-xs tabular-nums text-slate-500">{fall.guild_id}</p><p className="mt-1 text-[10px] text-slate-600">Supporter: {fall.supporter_name} · {fall.supporter_role}</p></div>
            </div>
            <span className={`rounded-full border px-3 py-1 text-xs font-bold ${COLOR[fall.status] || COLOR.closed}`}>{LABEL[fall.status] || fall.status}</span>
          </div>

          {fall.messages?.length > 0 && <div className="space-y-2 border-t border-slate-800 p-5">{fall.messages.map((eintrag: any) => <div key={eintrag.id} className="rounded-xl border border-slate-800 bg-black/20 p-3"><div className="flex justify-between gap-3 text-xs"><strong className="text-slate-300">{eintrag.actor_name || eintrag.actor_role} · {eintrag.actor_role}</strong><span className="text-slate-600">{zeit(eintrag.created_at)}</span></div><p className="mt-1.5 whitespace-pre-wrap text-sm text-slate-400">{eintrag.message}</p></div>)}</div>}

          <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 p-5">
            {fall.status === "accepted" && <Link href={`/dashboard/guild/${fall.guild_id}`} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500/10 px-4 py-2.5 text-sm font-bold text-emerald-300"><ExternalLink className="h-4 w-4" />Server-Dashboard öffnen</Link>}
            {fall.status === "accepted" && <button onClick={() => schliessen(fall.id)} disabled={saving} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-300">Fall schließen</button>}
            {fall.status === "pending" && <span className="text-xs text-amber-300">Wartet auf Annahme oder Ablehnung durch den Serverinhaber.</span>}
            {fall.status === "declined" && <span className="text-xs text-rose-300">Der Serverinhaber hat die Anfrage abgelehnt. Kein Zugriff wurde erteilt.</span>}
          </div>
          {(fall.status === "pending" || fall.status === "accepted") && <div className="flex gap-2 border-t border-slate-800 p-5"><input value={message[fall.id] || ""} onChange={(e) => setMessage((old) => ({ ...old, [fall.id]: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") senden(fall.id); }} placeholder="Notiz oder Nachricht …" maxLength={2000} className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-[#09090c] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500/50" /><button onClick={() => senden(fall.id)} disabled={saving || !(message[fall.id] || "").trim()} className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-500 text-white disabled:opacity-40"><MessageSquare className="h-4 w-4" /></button></div>}
        </section>
      ))}
    </div>
  );
}
