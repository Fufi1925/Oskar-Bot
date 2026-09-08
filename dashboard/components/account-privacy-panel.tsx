"use client";

import React from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ChevronDown,
  Cookie,
  Database,
  Download,
  FileClock,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { COOKIES, HINWEIS_COOKIE } from "@/lib/cookie-consent";

const STATUS: Record<string, { label: string; style: string }> = {
  undo: { label: "Rücknahmefrist", style: "text-amber-300 bg-amber-400/10 border-amber-400/20" },
  pending: { label: "Wird geprüft", style: "text-amber-300 bg-amber-400/10 border-amber-400/20" },
  rejected: { label: "Abgelehnt", style: "text-rose-300 bg-rose-400/10 border-rose-400/20" },
  completed: { label: "Abgeschlossen", style: "text-emerald-300 bg-emerald-400/10 border-emerald-400/20" },
  cancelled: { label: "Zurückgenommen", style: "text-slate-400 bg-white/[0.03] border-slate-700" },
};

function date(value: number) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value * 1000));
}

export function AccountPrivacyPanel({ userId }: { userId: string }) {
  const [inventory, setInventory] = React.useState<any[]>([]);
  const [requests, setRequests] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [details, setDetails] = React.useState(false);
  const [cookies, setCookies] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [downloading, setDownloading] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    Promise.all([
      api.getMyPrivacyInventory(userId),
      api.getMyErasureRequests(userId),
    ]).then(([stored, history]) => {
      if (!active) return;
      setInventory(stored?.inventory || []);
      setRequests(history?.requests || []);
    }).catch(() => {
      if (active) setMessage("Die Datenschutzdaten konnten gerade nicht geladen werden.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [userId]);

  const download = async () => {
    setDownloading(true);
    setMessage("");
    try {
      const data = await api.exportMyData(userId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `university-bot-daten-${userId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage("Deine Datenkopie wurde heruntergeladen.");
    } catch (error: any) {
      setMessage(error?.message || "Der Download ist fehlgeschlagen.");
    } finally {
      setDownloading(false);
    }
  };

  const resetCookieNotice = () => {
    document.cookie = `${HINWEIS_COOKIE}=; Max-Age=0; path=/; SameSite=Lax`;
    setMessage("Cookie-Einstellung zurückgesetzt. Der Hinweis erscheint beim nächsten Seitenaufruf erneut.");
  };

  return (
    <section id="datenschutz" className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-indigo-300"><ShieldCheck className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.2em]">Datenschutzbereich</span></div>
          <h2 className="mt-2 text-xl font-bold text-white">Deine Daten und Anträge</h2>
          <p className="mt-1 text-sm text-slate-500">Verständlich aufgelistet und als maschinenlesbare Kopie verfügbar.</p>
        </div>
        <button type="button" onClick={download} disabled={downloading} className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-indigo-500 disabled:opacity-50">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Daten herunterladen
        </button>
      </div>

      <div className="grid gap-px bg-slate-800 md:grid-cols-3">
        <button type="button" onClick={() => setDetails(value => !value)} className="flex items-center gap-3 bg-[#111116] p-5 text-left hover:bg-[#15151b]">
          <Database className="h-5 w-5 text-cyan-400" /><span className="flex-1"><strong className="block text-sm text-white">Gespeicherte Daten</strong><span className="mt-1 block text-xs text-slate-500">{inventory.reduce((sum, item) => sum + Number(item.count || 0), 0)} Datensätze in {inventory.length || 10} Bereichen</span></span><ChevronDown className={`h-4 w-4 text-slate-600 transition-transform ${details ? "rotate-180" : ""}`} />
        </button>
        <button type="button" onClick={() => setCookies(value => !value)} className="flex items-center gap-3 bg-[#111116] p-5 text-left hover:bg-[#15151b]">
          <Cookie className="h-5 w-5 text-amber-400" /><span className="flex-1"><strong className="block text-sm text-white">Cookie-Einstellungen</strong><span className="mt-1 block text-xs text-slate-500">Nur technisch notwendige Cookies</span></span><ChevronDown className={`h-4 w-4 text-slate-600 transition-transform ${cookies ? "rotate-180" : ""}`} />
        </button>
        <a href="#gefahrenbereich" className="flex items-center gap-3 bg-[#111116] p-5 hover:bg-[#15151b]">
          <FileClock className="h-5 w-5 text-rose-400" /><span><strong className="block text-sm text-white">Löschantrag stellen</strong><span className="mt-1 block text-xs text-slate-500">Mit Status und Rücknahmefrist</span></span>
        </a>
      </div>

      {loading && <div className="grid place-items-center p-8"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /></div>}

      {details && !loading && (
        <div className="border-t border-slate-800 p-5 sm:p-6">
          <h3 className="font-bold text-white">Was zu deinem Konto gespeichert ist</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {inventory.map(item => (
              <article key={item.key} className="rounded-xl border border-slate-800 bg-black/20 p-4">
                <div className="flex items-start justify-between gap-3"><strong className="text-sm text-slate-200">{item.label}</strong><span className="rounded-md bg-white/[0.04] px-2 py-0.5 text-xs tabular-nums text-slate-500">{item.count == null ? "serververwaltet" : item.count}</span></div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{item.purpose}</p>
              </article>
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-600">Der Download enthält die tatsächlichen Datensätze. Sicherheits- und Moderationsdaten anderer Verantwortlicher können gesetzlichen oder berechtigten Aufbewahrungsgründen unterliegen.</p>
        </div>
      )}

      {cookies && (
        <div className="border-t border-slate-800 p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div><h3 className="font-bold text-white">Technisch notwendige Cookies</h3><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Es gibt keine Werbe-, Tracking- oder Analyse-Cookies. Sitzungs- und Sicherheitscookies lassen sich nicht einzeln abschalten, ohne die Anmeldung zu beenden.</p></div>
            <button type="button" onClick={resetCookieNotice} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-600 hover:text-white"><RefreshCw className="h-4 w-4" />Hinweis zurücksetzen</button>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {COOKIES.map(item => <div key={item.name} className="rounded-xl border border-slate-800 bg-black/20 p-3"><code className="text-xs text-indigo-300">{item.name}</code><p className="mt-1 text-xs text-slate-500">{item.zweck} · {item.dauer}</p></div>)}
          </div>
          <Link href="/privacy" className="mt-4 inline-flex text-sm text-indigo-400 hover:text-indigo-300">Vollständige Datenschutzerklärung →</Link>
        </div>
      )}

      <div className="border-t border-slate-800 p-5 sm:p-6">
        <h3 className="flex items-center gap-2 font-bold text-white"><FileClock className="h-[18px] w-[18px] text-indigo-400" />Vergangene Datenschutzanträge</h3>
        {requests.length ? <div className="mt-4 space-y-2">{requests.map(item => {
          const state = STATUS[item.status] || STATUS.pending;
          return <div key={item.id} className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-black/20 p-4 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-slate-200">Löschantrag vom {date(item.requested_at)}</p><p className="mt-1 text-xs text-slate-500">Kennung: {String(item.id).slice(0, 10)}…{item.reason ? ` · Grund: ${item.reason}` : ""}</p></div><span className={`w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${state.style}`}>{state.label}</span></div>;
        })}</div> : <p className="mt-4 flex items-center gap-2 text-sm text-slate-500"><CheckCircle2 className="h-4 w-4 text-emerald-400" />Noch keine früheren Datenschutzanträge.</p>}
      </div>

      {message && <p className="border-t border-slate-800 px-5 py-3 text-sm text-slate-400 sm:px-6">{message}</p>}
    </section>
  );
}
