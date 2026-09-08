"use client";

import React from "react";
import { signOut } from "next-auth/react";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Laptop,
  Loader2,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  X,
} from "lucide-react";
import { api } from "@/lib/api";

function date(value: number) {
  if (!value) return "Noch nicht aufgezeichnet";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value * 1000));
}

export function AccountSecurityPanel({ userId }: { userId: string }) {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [confirm, setConfirm] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let active = true;
    api.getAccountSecurity(userId)
      .then(value => { if (active) setData(value); })
      .catch((err: any) => { if (active) setError(err?.message || "Sicherheitsdaten nicht verfügbar."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId]);

  const revoke = async () => {
    setBusy(true); setError("");
    try {
      await api.revokeAccountSessions(userId);
      await signOut({ callbackUrl: "/" });
    } catch (err: any) {
      setError(err?.message || "Die Sitzungen konnten nicht widerrufen werden.");
      setBusy(false);
    }
  };

  return (
    <section id="sicherheit" className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div><div className="flex items-center gap-2 text-cyan-300"><ShieldCheck className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.2em]">Sitzungen und Sicherheit</span></div><h2 className="mt-2 text-xl font-bold text-white">Deine Kontoanmeldungen</h2><p className="mt-1 text-sm text-slate-500">Geräte ohne IP-Adresse oder verstecktes Fingerprinting.</p></div>
        <button type="button" onClick={() => setConfirm(true)} className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-2.5 text-sm font-bold text-rose-300 hover:bg-rose-500/15"><LogOut className="h-4 w-4" />Von allen Geräten abmelden</button>
      </div>

      {loading ? <div className="grid place-items-center p-10"><Loader2 className="h-5 w-5 animate-spin text-cyan-400" /></div> : (
        <>
          {data?.unusual && <div className="m-5 flex gap-3 rounded-xl border border-amber-400/25 bg-amber-400/[0.06] p-4 text-sm text-amber-200 sm:m-6"><AlertTriangle className="h-5 w-5 shrink-0" /><div><strong>Ungewöhnliche Anmeldung erkannt</strong><p className="mt-1 text-amber-200/70">Die Geräteklasse unterscheidet sich von deiner vorherigen Anmeldung. Wenn du das nicht warst, melde alle Geräte ab und ändere dein Discord-Passwort.</p></div></div>}

          <div className="grid gap-px bg-slate-800 sm:grid-cols-2">
            <div className="bg-[#111116] p-5 sm:p-6"><p className="text-xs font-semibold text-slate-600">Aktuelle Anmeldung</p><div className="mt-3 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10"><Smartphone className="h-5 w-5 text-cyan-400" /></span><div><p className="font-semibold text-slate-200">{data?.current_device || "Unbekanntes Gerät"}</p><p className="mt-0.5 text-xs text-emerald-400">Jetzt aktiv · {date(data?.current_login || data?.current_time)}</p></div></div></div>
            <div className="bg-[#111116] p-5 sm:p-6"><p className="text-xs font-semibold text-slate-600">Letzte Kontoanmeldung</p><div className="mt-3 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-400/10"><KeyRound className="h-5 w-5 text-indigo-400" /></span><div><p className="font-semibold text-slate-200">{date(data?.last_login)}</p><p className="mt-0.5 text-xs text-slate-500">Insgesamt {data?.login_count || 0} Anmeldungen</p></div></div></div>
          </div>

          <div className="grid border-t border-slate-800 lg:grid-cols-2 lg:divide-x lg:divide-slate-800">
            <div className="p-5 sm:p-6"><h3 className="font-bold text-white">Letzte Sitzungen</h3>{data?.sessions?.length ? <div className="mt-4 space-y-2">{data.sessions.slice(0, 5).map((session: any) => <div key={session.id} className="flex items-center gap-3 rounded-xl border border-slate-800 bg-black/20 p-3"><Laptop className="h-4 w-4 text-slate-500" /><div className="min-w-0 flex-1"><p className="truncate text-sm text-slate-300">{session.device}</p><p className="text-xs text-slate-600">{date(session.created_at)}</p></div>{session.unusual ? <AlertTriangle className="h-4 w-4 text-amber-400" /> : <CheckCircle2 className="h-4 w-4 text-emerald-400" />}</div>)}</div> : <p className="mt-4 text-sm leading-6 text-slate-500">Der Geräteverlauf beginnt mit deiner nächsten neuen Anmeldung. Die aktuelle Gerätebezeichnung wird bereits angezeigt.</p>}</div>

            <div className="border-t border-slate-800 p-5 sm:p-6 lg:border-t-0"><h3 className="font-bold text-white">Verbundene Discord-Berechtigungen</h3><div className="mt-4 space-y-3">{data?.permissions?.map((permission: any) => <div key={permission.scope} className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" /><div><p className="text-sm font-semibold text-slate-300">{permission.label} <code className="ml-1 text-xs text-slate-600">{permission.scope}</code></p><p className="mt-0.5 text-xs text-slate-500">{permission.detail}</p></div></div>)}</div><div className="mt-4 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.04] p-3 text-xs leading-5 text-emerald-200/70">Nicht freigegeben: {(data?.not_granted || []).join(", ")}. Der Bot erhält über diese Anmeldung keinen Zugriff darauf.</div></div>
          </div>
        </>
      )}
      {error && <p className="border-t border-slate-800 px-5 py-3 text-sm text-rose-300 sm:px-6">{error}</p>}

      {confirm && <div className="fixed inset-0 z-[130] grid place-items-center bg-black/80 p-4 backdrop-blur-md"><div role="dialog" aria-modal="true" className="relative w-full max-w-md rounded-3xl border border-rose-500/30 bg-[#151519] p-6 shadow-2xl sm:p-8"><button type="button" onClick={() => setConfirm(false)} className="absolute right-4 top-4 rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Schließen"><X className="h-5 w-5" /></button><span className="grid h-12 w-12 place-items-center rounded-2xl bg-rose-500/10"><ShieldAlert className="h-6 w-6 text-rose-400" /></span><h2 className="mt-5 text-2xl font-bold text-white">Wirklich überall abmelden?</h2><p className="mt-3 text-sm leading-6 text-slate-400">Alle bestehenden Dashboard-Sitzungen werden innerhalb von höchstens 15 Sekunden ungültig. Danach musst du dich auf jedem Gerät erneut über Discord anmelden.</p><div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={() => setConfirm(false)} className="rounded-xl border border-slate-700 px-5 py-3 font-semibold text-slate-300 hover:text-white">Abbrechen</button><button type="button" disabled={busy} onClick={revoke} className="inline-flex items-center justify-center gap-2 rounded-xl bg-rose-600 px-5 py-3 font-bold text-white hover:bg-rose-500 disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" />}Alle Sitzungen beenden</button></div></div></div>}
    </section>
  );
}
