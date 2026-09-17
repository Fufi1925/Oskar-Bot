"use client";

import React from "react";
import Link from "next/link";
import { AlertTriangle, Bug, CheckCircle2, Clock3, Copy, ExternalLink, LifeBuoy, Loader2, MessageSquare, Plus, RefreshCw, Search, SearchCheck, Send, ShieldCheck, SlidersHorizontal, Star, Trash2, UserCheck, X } from "lucide-react";
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
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<"priority" | "newest" | "oldest" | "rating">("priority");
  const [composerOpen, setComposerOpen] = React.useState(false);
  const [cases, setCases] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<Record<number, string>>({});
  const [deleteTarget, setDeleteTarget] = React.useState<any | null>(null);
  const [scanResult, setScanResult] = React.useState<any | null>(null);
  const [scanning, setScanning] = React.useState<string>("");

  const laden = React.useCallback(async () => {
    setLoading(true);
    try { setCases((await api.getAdminSupportCases("all")).cases || []); }
    catch (error: any) { toast.error(error?.message || "Server-Anfragen konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, []);
  React.useEffect(() => { laden(); }, [laden]);

  const anfragen = async () => {
    if (!/^\d{17,20}$/.test(guildId.trim())) return toast.error("Gib eine gültige Discord-Server-ID ein.");
    setSaving(true);
    try {
      await api.createSupportRequest(guildId.trim(), problem.trim());
      toast.success("Support-Anfrage wurde an den Serverinhaber gesendet.");
      setGuildId(""); setProblem(""); setFilter("all"); setComposerOpen(false); await laden();
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

  const loeschen = async () => {
    if (!deleteTarget) return;
    setSaving(true);
    try {
      await api.deleteAdminSupportCase(deleteTarget.id);
      toast.success("Support-Anfrage wurde gelöscht.");
      setDeleteTarget(null);
      await laden();
    } catch (error: any) { toast.error(error?.message || "Anfrage konnte nicht gelöscht werden."); }
    finally { setSaving(false); }
  };

  const scannen = async (id: number, type: "dashboard" | "discord" | "full") => {
    setScanning(`${id}:${type}`);
    try {
      setScanResult(await api.scanAdminSupportCase(id, type));
      toast.success("Der schreibgeschützte Support-Scan ist abgeschlossen.");
    } catch (error: any) { toast.error(error?.message || "Support-Scan fehlgeschlagen."); }
    finally { setScanning(""); }
  };

  const counts = React.useMemo(() => ({
    all: cases.length,
    pending: cases.filter((item) => item.status === "pending").length,
    accepted: cases.filter((item) => item.status === "accepted").length,
    declined: cases.filter((item) => item.status === "declined").length,
    closed: cases.filter((item) => item.status === "closed").length,
  }), [cases]);
  const rated = cases.filter((item) => Number(item.rating) > 0);
  const averageRating = rated.length ? rated.reduce((sum, item) => sum + Number(item.rating), 0) / rated.length : 0;
  const averageResponse = (() => {
    const values = cases.filter((item) => Number(item.accepted_at) > Number(item.created_at)).map((item) => Number(item.accepted_at) - Number(item.created_at));
    return values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length / 60) : 0;
  })();
  const visibleCases = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    const statusOrder: Record<string, number> = { pending: 0, accepted: 1, declined: 2, closed: 3 };
    return cases
      .filter((item) => filter === "all" || item.status === filter)
      .filter((item) => !needle || [item.guild_name, item.guild_id, item.supporter_name, item.supporter_role, item.problem].some((value) => String(value || "").toLowerCase().includes(needle)))
      .sort((a, b) => {
        if (sort === "newest") return Number(b.created_at) - Number(a.created_at);
        if (sort === "oldest") return Number(a.created_at) - Number(b.created_at);
        if (sort === "rating") return Number(b.rating || 0) - Number(a.rating || 0) || Number(b.updated_at) - Number(a.updated_at);
        return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9) || Number(b.updated_at) - Number(a.updated_at);
      });
  }, [cases, filter, query, sort]);
  const sortLabel = { priority: "Priorität", newest: "Neueste", oldest: "Älteste", rating: "Bewertung" }[sort];

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl border border-indigo-400/20 bg-[linear-gradient(135deg,rgba(79,70,229,.16),rgba(15,15,22,.95)_55%)] p-6 sm:p-7">
        <div aria-hidden className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-indigo-400/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start gap-4"><span className="grid h-12 w-12 place-items-center rounded-2xl border border-indigo-300/20 bg-indigo-400/10"><LifeBuoy className="h-6 w-6 text-indigo-200" /></span><div className="min-w-0 flex-1"><p className="text-xs font-black uppercase tracking-[.16em] text-indigo-300">Support-Zentrale</p><h2 className="mt-1 text-2xl font-black text-white">Server-Anfragen verwalten</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">Anfragen senden, Zustimmung verfolgen, sichere Diagnosen starten und jeden Fall vollständig dokumentieren.</p></div><button onClick={() => setComposerOpen((open) => !open)} className="inline-flex items-center gap-2 rounded-xl bg-indigo-500 px-4 py-2.5 text-sm font-black text-white"><Plus className={`h-4 w-4 transition-transform ${composerOpen ? "rotate-45" : ""}`} />{composerOpen ? "Schließen" : "Neue Anfrage"}</button></div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[[LifeBuoy,"Fälle",counts.all],[Clock3,"Warten",counts.pending],[UserCheck,"Aktiver Zugriff",counts.accepted],[Star,"Ø Bewertung",averageRating ? `${averageRating.toFixed(2)}/10` : "—"],[MessageSquare,"Ø Annahmezeit",averageResponse ? `${averageResponse} Min.` : "—"]].map(([Icon,label,value])=>{const I=Icon as React.ElementType;return <div key={String(label)} className="rounded-2xl border border-slate-800 bg-[#131318] p-4"><I className="h-4 w-4 text-indigo-300"/><p className="mt-3 text-xl font-black text-white">{value as React.ReactNode}</p><p className="mt-1 text-xs text-slate-500">{label as string}</p></div>})}
      </div>

      {composerOpen && <section className="rounded-2xl border border-indigo-500/20 bg-[#111116] p-5 sm:p-6">
        <div className="grid gap-5 lg:grid-cols-[.7fr_1.3fr]"><div><h3 className="font-black text-white">Sichere Admin-Anfrage</h3><p className="mt-2 text-xs leading-5 text-slate-500">Der Bot muss auf dem Server sein. Der Serverinhaber sieht deinen Namen, dein Profilbild, deine Dashboard-Rolle und diese Nachricht. Vor der Annahme erhältst du keinerlei Zugriff.</p><div className="mt-4 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.05] p-3 text-xs leading-5 text-emerald-200/80"><ShieldCheck className="mb-2 h-4 w-4"/>Zugriff endet beim Schließen oder Löschen des Falls sofort.</div></div><div className="space-y-3"><label className="block"><span className="mb-1.5 block text-xs font-bold text-slate-400">Discord-Server-ID</span><input value={guildId} onChange={(e) => setGuildId(e.target.value.replace(/\D/g, ""))} placeholder="123456789012345678" maxLength={20} className="w-full rounded-xl border border-slate-800 bg-[#09090c] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500/50" /></label><label className="block"><span className="mb-1.5 flex justify-between text-xs font-bold text-slate-400">Nachricht an den Serverinhaber <span className="font-normal text-slate-600">{problem.length}/1000</span></span><textarea value={problem} onChange={(e) => setProblem(e.target.value)} placeholder="Beschreibe kurz, wobei du helfen möchtest …" maxLength={1000} rows={4} className="w-full resize-none rounded-xl border border-slate-800 bg-[#09090c] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500/50" /></label><button onClick={anfragen} disabled={saving || !/^\d{17,20}$/.test(guildId)} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-500 px-5 py-3 text-sm font-black text-white disabled:opacity-40"><Send className="h-4 w-4" />Anfrage sicher senden</button></div></div>
      </section>}

      <section className="rounded-2xl border border-slate-800 bg-[#111116] p-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center"><div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-600"/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Server, ID, Supporter oder Problem suchen …" className="w-full rounded-xl border border-slate-800 bg-[#09090c] py-2.5 pl-9 pr-4 text-sm text-white outline-none focus:border-indigo-500/50"/></div><div className="flex flex-wrap gap-2">{FILTER.map(([id, text]) => <button key={id} onClick={() => setFilter(id)} className={`rounded-lg border px-3 py-2 text-xs font-bold ${filter === id ? "border-indigo-400/30 bg-indigo-400/10 text-indigo-200" : "border-slate-800 text-slate-500 hover:text-slate-300"}`}>{text} <span className="ml-1 opacity-60">{counts[id as keyof typeof counts]}</span></button>)}</div><button onClick={()=>setSort(sort === "priority" ? "newest" : sort === "newest" ? "oldest" : sort === "oldest" ? "rating" : "priority")} title="Sortierung wechseln" className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-800 px-3 py-2 text-xs font-bold text-slate-400"><SlidersHorizontal className="h-3.5 w-3.5"/>{sortLabel}</button><button onClick={laden} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-800 text-slate-500 hover:text-white"><RefreshCw className="h-4 w-4" /></button></div>
        <p className="mt-3 px-1 text-[11px] text-slate-600">{visibleCases.length} von {cases.length} Fällen sichtbar · Sortierung: {sortLabel}</p>
      </section>

      {loading && <div className="grid min-h-40 place-items-center"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /></div>}
      {!loading && visibleCases.length === 0 && <div className="rounded-2xl border border-dashed border-slate-800 bg-[#0d0d11] p-10 text-center"><Search className="mx-auto h-6 w-6 text-slate-700"/><p className="mt-3 text-sm font-bold text-slate-400">Keine passenden Supportfälle</p><p className="mt-1 text-xs text-slate-600">Ändere Suche oder Filter oder erstelle eine neue Anfrage.</p></div>}
      {!loading && visibleCases.map((fall) => (
        <section key={fall.id} className={`overflow-hidden rounded-2xl border bg-[#0f0f13] ${fall.status === "pending" ? "border-amber-400/20" : fall.status === "accepted" ? "border-emerald-400/20" : "border-slate-800"}`}>
          <div className="flex flex-wrap items-start justify-between gap-4 p-5">
            <div className="flex min-w-0 items-center gap-3">
              {fall.guild_icon ? <img src={fall.guild_icon} alt="" className="h-12 w-12 rounded-xl object-cover ring-1 ring-white/10" /> : <span className="grid h-12 w-12 place-items-center rounded-xl bg-indigo-500/10"><ShieldCheck className="h-5 w-5 text-indigo-300" /></span>}
              <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="truncate font-black text-white">{fall.guild_name}</p><span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-bold text-slate-500">Fall #{fall.id}</span></div><button onClick={()=>{navigator.clipboard?.writeText(String(fall.guild_id));toast.success("Server-ID kopiert.")}} className="mt-0.5 inline-flex items-center gap-1 text-xs tabular-nums text-slate-500 hover:text-indigo-300">{fall.guild_id}<Copy className="h-3 w-3"/></button><p className="mt-1 text-[10px] text-slate-600">{fall.supporter_name} · <span style={{color:fall.supporter_role_color}}>{fall.supporter_role}</span></p></div>
            </div>
            <div className="text-right"><span className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${COLOR[fall.status] || COLOR.closed}`}>{LABEL[fall.status] || fall.status}</span><p className="mt-2 text-[10px] text-slate-600">Erstellt {zeit(fall.created_at)}</p></div>
          </div>
          <div className="grid grid-cols-2 gap-px border-t border-slate-800 bg-slate-800 sm:grid-cols-4">{[["Status",LABEL[fall.status] || fall.status],["Nachrichten",fall.messages?.length || 0],["Letzte Änderung",zeit(fall.updated_at)],["Bewertung",fall.rating ? `${fall.rating}/10` : "Noch keine"]].map(([label,value])=><div key={String(label)} className="bg-[#0c0c10] px-4 py-3"><p className="truncate text-xs font-bold text-slate-300">{value}</p><p className="mt-1 text-[10px] text-slate-600">{label}</p></div>)}</div>

          {fall.messages?.length > 0 && <div className="space-y-2 border-t border-slate-800 p-5">{fall.messages.map((eintrag: any) => <div key={eintrag.id} className="rounded-xl border border-slate-800 bg-black/20 p-3"><div className="flex justify-between gap-3 text-xs"><strong className="text-slate-300">{eintrag.actor_name || eintrag.actor_role} · {eintrag.actor_role}</strong><span className="text-slate-600">{zeit(eintrag.created_at)}</span></div><p className="mt-1.5 whitespace-pre-wrap text-sm text-slate-400">{eintrag.message}</p></div>)}</div>}

          <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 p-5">
            {fall.status === "accepted" && <Link href={`/dashboard/guild/${fall.guild_id}`} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500/10 px-4 py-2.5 text-sm font-bold text-emerald-300"><ExternalLink className="h-4 w-4" />Server-Dashboard öffnen</Link>}
            {fall.status === "accepted" && <button onClick={() => schliessen(fall.id)} disabled={saving} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-300">Fall schließen</button>}
            {fall.status === "pending" && <span className="text-xs text-amber-300">Wartet auf Annahme oder Ablehnung durch den Serverinhaber.</span>}
            {fall.status === "declined" && <span className="text-xs text-rose-300">Der Serverinhaber hat die Anfrage abgelehnt. Kein Zugriff wurde erteilt.</span>}
            {fall.status === "closed" && fall.rating > 0 && <span className="text-xs font-bold text-amber-300">Bewertung des Inhabers: {fall.rating}/10 Sterne</span>}
            <button onClick={() => setDeleteTarget(fall)} className="ml-auto inline-flex items-center gap-2 rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-2.5 text-sm font-bold text-rose-300"><Trash2 className="h-4 w-4" />Anfrage löschen</button>
          </div>
          {fall.status === "accepted" && (
            <div className="border-t border-indigo-500/15 bg-indigo-500/[0.04] p-5">
              <div className="flex items-start gap-3"><SearchCheck className="mt-0.5 h-5 w-5 text-indigo-300" /><div><h4 className="text-sm font-bold text-white">Exklusive Support-Diagnose</h4><p className="mt-1 text-xs leading-5 text-slate-500">Nur hier im Admin-Dashboard verfügbar. Alle Prüfungen sind schreibgeschützt und ändern nichts am Server.</p></div></div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <button onClick={() => scannen(fall.id, "dashboard")} disabled={Boolean(scanning)} className="rounded-xl border border-slate-700 bg-black/20 p-3 text-left text-sm font-bold text-slate-200 disabled:opacity-40"><Bug className="mb-2 h-4 w-4 text-cyan-300" />Dashboard-Bugs prüfen<span className="mt-1 block text-[11px] font-normal text-slate-500">Datenbank, Bot-Cache, Rechte und Support-Zugriff</span></button>
                <button onClick={() => scannen(fall.id, "discord")} disabled={Boolean(scanning)} className="rounded-xl border border-slate-700 bg-black/20 p-3 text-left text-sm font-bold text-slate-200 disabled:opacity-40"><ShieldCheck className="mb-2 h-4 w-4 text-violet-300" />Discord-Bugs prüfen<span className="mt-1 block text-[11px] font-normal text-slate-500">Rollen, Webhooks, Einladungen und Sicherheitsrisiken</span></button>
                <button onClick={() => scannen(fall.id, "full")} disabled={Boolean(scanning)} className="rounded-xl border border-indigo-400/25 bg-indigo-400/10 p-3 text-left text-sm font-bold text-indigo-100 disabled:opacity-40"><SearchCheck className="mb-2 h-4 w-4 text-indigo-300" />Komplettscan<span className="mt-1 block text-[11px] font-normal text-indigo-200/60">Beide Diagnosen in einem Durchlauf</span></button>
              </div>
              {scanning.startsWith(`${fall.id}:`) && <p className="mt-3 flex items-center gap-2 text-xs text-indigo-300"><Loader2 className="h-3.5 w-3.5 animate-spin" />Server wird schreibgeschützt geprüft …</p>}
            </div>
          )}
          {(fall.status === "pending" || fall.status === "accepted") && <div className="flex gap-2 border-t border-slate-800 p-5"><input value={message[fall.id] || ""} onChange={(e) => setMessage((old) => ({ ...old, [fall.id]: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") senden(fall.id); }} placeholder="Notiz oder Nachricht …" maxLength={2000} className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-[#09090c] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500/50" /><button onClick={() => senden(fall.id)} disabled={saving || !(message[fall.id] || "").trim()} className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-500 text-white disabled:opacity-40"><MessageSquare className="h-4 w-4" /></button></div>}
        </section>
      ))}

      {deleteTarget && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10050] grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl border border-rose-500/25 bg-[#131318] p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-rose-500/10"><AlertTriangle className="h-6 w-6 text-rose-300" /></span><button onClick={() => setDeleteTarget(null)} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"><X className="h-5 w-5" /></button></div>
            <h3 className="mt-4 text-xl font-black text-white">Support-Anfrage löschen?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">Der Fall für <strong className="text-white">{deleteTarget.guild_name}</strong> wird mit allen Notizen und Bewertungen endgültig gelöscht. Ein eventuell aktiver Support-Zugriff wird sofort entzogen.</p>
            <div className="mt-6 grid grid-cols-2 gap-3"><button onClick={() => setDeleteTarget(null)} className="rounded-xl border border-slate-700 py-3 text-sm font-bold text-slate-300">Abbrechen</button><button onClick={loeschen} disabled={saving} className="rounded-xl bg-rose-500 py-3 text-sm font-black text-white disabled:opacity-50">Endgültig löschen</button></div>
          </div>
        </div>
      )}

      {scanResult && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10050] overflow-y-auto bg-black/80 p-4 backdrop-blur-sm sm:p-8">
          <div className="mx-auto w-full max-w-3xl rounded-3xl border border-indigo-400/20 bg-[#131318] p-5 shadow-2xl sm:p-7">
            <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-widest text-indigo-300">Support-Diagnose</p><h3 className="mt-1 text-xl font-black text-white">Scan-Ergebnis für {scanResult.guild_id}</h3></div><button onClick={() => setScanResult(null)} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"><X className="h-5 w-5" /></button></div>
            {scanResult.dashboard && <section className="mt-6"><h4 className="flex items-center gap-2 text-sm font-bold text-white"><Bug className="h-4 w-4 text-cyan-300" />Dashboard- und Verbindungsprüfung</h4><div className="mt-3 grid gap-2 sm:grid-cols-2">{scanResult.dashboard.checks?.map((check: any) => <div key={check.key} className={`rounded-xl border p-3 ${check.ok ? "border-emerald-500/15 bg-emerald-500/[0.05]" : "border-rose-500/20 bg-rose-500/[0.06]"}`}><p className="flex items-center gap-2 text-sm font-bold text-white">{check.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-rose-300" />}{check.label}</p><p className="mt-1 text-xs text-slate-500">{check.detail}</p></div>)}</div></section>}
            {scanResult.discord && <section className="mt-6"><div className="flex flex-wrap items-center justify-between gap-3"><h4 className="flex items-center gap-2 text-sm font-bold text-white"><ShieldCheck className="h-4 w-4 text-violet-300" />Discord- und Sicherheitsprüfung</h4><span className="rounded-full border border-indigo-400/20 bg-indigo-400/10 px-3 py-1 text-xs font-black text-indigo-200">Score {scanResult.discord.score}/100</span></div><div className="mt-3 space-y-2">{scanResult.discord.findings?.length ? scanResult.discord.findings.map((finding: any, index: number) => <div key={`${finding.kind}-${index}`} className="rounded-xl border border-slate-800 bg-black/20 p-3"><p className="text-sm font-bold text-white">{finding.title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{finding.detail}</p><span className="mt-2 inline-block rounded bg-slate-800 px-2 py-1 text-[10px] font-bold uppercase text-slate-400">{finding.severity}</span></div>) : <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/[0.05] p-4 text-sm text-emerald-300">Keine Discord-Probleme in diesem Scan gefunden.</div>}</div></section>}
            <p className="mt-6 rounded-xl border border-slate-800 bg-black/20 p-3 text-xs leading-5 text-slate-500">Dieser Diagnose-Scan ist schreibgeschützt. Ergebnisse sind Hinweise für den Supporter und führen niemals automatisch Aktionen auf dem Discord-Server aus.</p>
            <button onClick={() => setScanResult(null)} className="mt-5 w-full rounded-xl bg-indigo-500 py-3 text-sm font-black text-white">Ergebnis schließen</button>
          </div>
        </div>
      )}
    </div>
  );
}
