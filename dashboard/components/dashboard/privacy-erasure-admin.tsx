"use client";

import React from "react";
import { Check, Clock3, RefreshCw, ShieldAlert, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const labels: Record<string, string> = { undo: "Rücknahmefrist", pending: "Offen", approved: "Genehmigt", rejected: "Abgelehnt", completed: "Gelöscht", cancelled: "Zurückgenommen" };

export function PrivacyErasureAdmin() {
  const [items, setItems] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState("");
  const [reasons, setReasons] = React.useState<Record<string, string>>({});

  const load = React.useCallback(async () => {
    setLoading(true);
    try { setItems((await api.listErasureRequests())?.requests ?? []); }
    catch (error: any) { toast.error(error?.message || "Löschanträge konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const decide = async (id: string, action: "approve" | "reject") => {
    if (action === "approve" && !window.confirm("Diesen Antrag genehmigen und die freigegebenen Daten jetzt unwiderruflich löschen?")) return;
    const reason = reasons[id]?.trim() || "";
    if (action === "reject" && !reason) { toast.error("Bitte gib einen Ablehnungsgrund ein."); return; }
    setBusy(id);
    try {
      await api.decideErasure(id, action, reason);
      toast.success(action === "approve" ? "Daten wurden gelöscht und anonymisiert." : "Antrag wurde abgelehnt.");
      await load();
    } catch (error: any) { toast.error(error?.message || "Entscheidung fehlgeschlagen."); }
    finally { setBusy(""); }
  };

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="flex items-center gap-2 text-xl font-bold text-white"><ShieldAlert className="h-5 w-5 text-red-400" />Datenlöschung</h2><p className="mt-1 text-sm text-slate-500">Anträge nach Art. 17 DSGVO prüfen, genehmigen oder begründet ablehnen.</p></div><button onClick={load} disabled={loading} className="rounded-xl border border-slate-700 p-2.5 text-slate-400 hover:text-white"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></div>
    <div className="rounded-2xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm leading-6 text-amber-200">Bei einer Genehmigung werden Konto-/Profildaten entfernt oder anonymisiert und Premium entzogen. XP, Voice-Zeit, Serverkonfiguration, vergebene Dashboard-Zugriffe sowie Moderations-, Sicherheits- und erforderliche Nachweisdaten bleiben erhalten.</div>
    {loading ? <p className="py-12 text-center text-slate-500">Anträge werden geladen…</p> : items.length === 0 ? <p className="rounded-2xl border border-slate-800 bg-[#131318] py-12 text-center text-slate-500">Keine Löschanträge vorhanden.</p> : <div className="space-y-3">{items.map(item => <article key={item.id} className="rounded-2xl border border-slate-800 bg-[#131318] p-5">
      <div className="flex flex-wrap items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="font-bold text-white">{item.username || "Unbekannter Nutzer"}</h3><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${item.status === "pending" ? "bg-amber-400/10 text-amber-300" : item.status === "completed" ? "bg-emerald-400/10 text-emerald-300" : item.status === "rejected" ? "bg-red-400/10 text-red-300" : "bg-slate-700/40 text-slate-400"}`}>{labels[item.status] || item.status}</span></div><p className="mt-1 font-mono text-xs text-slate-500">Discord-ID: {item.user_id}</p><p className="mt-2 flex items-center gap-1.5 text-xs text-slate-600"><Clock3 className="h-3.5 w-3.5" />Beantragt: {new Date(item.requested_at * 1000).toLocaleString("de-DE")}</p>{item.reason && <p className="mt-2 text-sm text-red-300">Grund: {item.reason}</p>}</div></div>
      {item.status === "pending" && <div className="mt-4 border-t border-slate-800 pt-4"><input value={reasons[item.id] || ""} onChange={event => setReasons(old => ({ ...old, [item.id]: event.target.value }))} placeholder="Ablehnungsgrund (nur bei Ablehnung erforderlich)" className="w-full rounded-xl border border-slate-700 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-indigo-500" /><div className="mt-3 flex flex-wrap gap-3"><button disabled={busy === item.id} onClick={() => decide(item.id, "approve")} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-50"><Check className="h-4 w-4" />Genehmigen und löschen</button><button disabled={busy === item.id} onClick={() => decide(item.id, "reject")} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-50"><X className="h-4 w-4" />Ablehnen</button></div></div>}
    </article>)}</div>}
  </div>;
}
