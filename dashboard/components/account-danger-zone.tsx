"use client";

import React from "react";
import { signOut } from "next-auth/react";
import { AlertTriangle, Clock3, LogOut, ShieldAlert, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";

export function AccountDangerZone({ userId, username }: { userId: string; username: string }) {
  const [step, setStep] = React.useState<0 | 1 | 2 | 3>(0);
  const [typed, setTyped] = React.useState("");
  const [request, setRequest] = React.useState<any>(null);
  const [seconds, setSeconds] = React.useState(10);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    api.getMyErasureRequest(userId).then(data => {
      const item = data?.request;
      if (!item || item.status === "cancelled") return;
      setRequest(item);
      if (item.status === "undo") {
        setSeconds(Math.max(0, Number(item.undo_until) - Math.floor(Date.now() / 1000)));
        setStep(3);
      }
    }).catch(() => {});
  }, [userId]);

  React.useEffect(() => {
    if (step !== 3 || !request || request.status !== "undo") return;
    const update = () => setSeconds(Math.max(0, Number(request.undo_until) - Math.floor(Date.now() / 1000)));
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [step, request]);

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const item = await api.requestErasure();
      setRequest(item);
      setSeconds(Math.max(0, Number(item.undo_until) - Math.floor(Date.now() / 1000)));
      setStep(3);
    } catch (err: any) {
      setError(err?.message || "Der Antrag konnte nicht angelegt werden.");
    } finally { setBusy(false); }
  };

  const undo = async () => {
    if (!request?.id) return;
    setBusy(true); setError("");
    try {
      await api.cancelErasure(request.id);
      setRequest(null); setTyped(""); setStep(0);
    } catch (err: any) {
      setError(err?.message || "Die Rücknahmefrist ist bereits abgelaufen.");
      setRequest({ ...request, status: "pending" });
    } finally { setBusy(false); }
  };

  const status = request?.status;

  return (
    <section className="overflow-hidden rounded-2xl border border-red-500/35 bg-red-950/15 shadow-lg shadow-red-950/10">
      <div className="border-b border-red-500/20 px-5 py-4 sm:px-6">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-red-400">Gefahrenbereich</p>
        <h2 className="mt-1 text-lg font-bold text-white">Konto und Daten</h2>
      </div>

      <div className="divide-y divide-red-500/15">
        <div className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:px-6">
          <div className="flex min-w-0 flex-1 items-start gap-3"><LogOut className="mt-0.5 h-5 w-5 shrink-0 text-red-400" /><div><h3 className="font-semibold text-white">Abmelden</h3><p className="mt-1 text-sm text-slate-500">Beendet nur deine aktuelle Discord-Sitzung. Es werden keine Daten gelöscht.</p></div></div>
          <button type="button" onClick={() => signOut({ callbackUrl: "/" })} className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-sm font-semibold text-red-300 transition-colors hover:bg-red-500/20">Abmelden</button>
        </div>

        <div className="px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
            <div className="flex min-w-0 flex-1 items-start gap-3"><Trash2 className="mt-0.5 h-5 w-5 shrink-0 text-red-400" /><div><h3 className="font-semibold text-white">Alle löschbaren Kontodaten löschen</h3><p className="mt-1 text-sm leading-6 text-slate-500">Antrag nach Art. 17 DSGVO. Nach der 10-Sekunden-Rücknahmefrist prüft ein Administrator den Antrag. Die Bearbeitung erfolgt normalerweise innerhalb von 24–98 Stunden.</p></div></div>
            {!status || status === "cancelled" ? <button type="button" onClick={() => setStep(1)} className="rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-red-500">Datenlöschung starten</button> : null}
          </div>

          <div className="mt-4 rounded-xl border border-red-500/15 bg-black/20 p-4 text-xs leading-5 text-slate-500">
            <strong className="text-slate-300">Gelöscht oder anonymisiert:</strong> Dashboard-Profil und Loginverlauf, verknüpfte Cookie-Bestätigungen, persönliche Bewerbungsdaten, Tester-Zuordnungen und Premium-Zugriff. Premium wird entzogen und die direkte Kontozuordnung pseudonymisiert.<br />
            <strong className="text-slate-300">Bleibt erhalten:</strong> XP, Leveling-Nachrichten, Voice-Zeit, Servereinstellungen, von Serververantwortlichen eingerichtete Zugriffe sowie erforderliche Moderations-, Sicherheits-, Rechts- und Nachweisdaten. Ausnahmen richten sich insbesondere nach Art. 17 Abs. 3 DSGVO und § 35 BDSG.
          </div>

          {status === "undo" && step !== 3 && <p className="mt-4 text-sm text-amber-300">Dein Antrag befindet sich noch in der Rücknahmefrist.</p>}
          {status === "pending" && <div className="mt-4 flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-200"><Clock3 className="h-5 w-5 shrink-0" /><p>Dein Antrag wartet auf die Prüfung durch einen Administrator. Fufi wurde per Discord-DM informiert. Geplante Bearbeitung: 24–98 Stunden.</p></div>}
          {status === "rejected" && <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-200">Der Antrag wurde abgelehnt.{request?.reason ? ` Grund: ${request.reason}` : ""}</div>}
          {status === "completed" && <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-emerald-200">Die freigegebenen Kontodaten wurden gelöscht oder anonymisiert und Premium wurde entfernt.</div>}
          {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
        </div>
      </div>

      {step > 0 && step < 3 && <div className="fixed inset-0 z-[120] grid place-items-center bg-black/80 p-4 backdrop-blur-md">
        <div role="dialog" aria-modal="true" className="relative w-full max-w-lg rounded-[26px] border border-red-500/30 bg-[#151519] p-6 shadow-2xl shadow-black/70 sm:p-8">
          <button type="button" onClick={() => { setStep(0); setTyped(""); }} aria-label="Schließen" className="absolute right-4 top-4 rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"><X className="h-5 w-5" /></button>
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-red-500/10"><ShieldAlert className="h-6 w-6 text-red-400" /></span>
          {step === 1 ? <>
            <h2 className="mt-5 text-2xl font-bold text-white">Bist du sicher?</h2>
            <p className="mt-3 text-sm leading-6 text-slate-400">Dies startet einen echten Antrag auf Löschung deiner löschbaren personenbezogenen Kontodaten. XP, Voice-Zeit, Serverkonfigurationen und erforderliche Sicherheitsdaten werden nicht entfernt.</p>
            <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between"><button type="button" onClick={() => setStep(2)} className="rounded-xl border border-slate-700 px-5 py-3 font-semibold text-white hover:bg-white/5">Ich bin sicher</button><button type="button" onClick={() => setStep(0)} className="rounded-xl bg-red-600 px-5 py-3 font-bold text-white hover:bg-red-500">Nein</button></div>
          </> : <>
            <h2 className="mt-5 text-2xl font-bold text-white">Unwiderruflich bestätigen</h2>
            <p className="mt-3 text-sm leading-6 text-slate-400">Gib deinen Discord-Benutzernamen exakt ein. Danach bleiben 10 Sekunden, um den Antrag zurückzunehmen.</p>
            <label className="mt-6 block text-sm font-semibold text-slate-300" htmlFor="delete-username">Discord-Benutzername</label>
            <input id="delete-username" autoComplete="off" value={typed} onChange={event => setTyped(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-700 bg-black/30 px-4 py-3 text-white outline-none transition-colors focus:border-red-500" placeholder={username} />
            <p className="mt-2 text-xs text-slate-600">Erwartet: <span className="font-mono text-slate-400">{username}</span></p>
            <button type="button" disabled={typed !== username || busy} onClick={submit} className="mt-6 w-full rounded-xl bg-red-600 px-5 py-3 font-bold text-white transition-all hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-35">{busy ? "Wird angelegt…" : "Löschung verbindlich beantragen"}</button>
          </>}
        </div>
      </div>}

      {step === 3 && request && <div className="fixed inset-0 z-[120] grid place-items-center bg-black/80 p-4 backdrop-blur-md">
        <div role="dialog" aria-modal="true" className="w-full max-w-lg rounded-[26px] border border-red-500/30 bg-[#151519] p-7 text-center shadow-2xl shadow-black/70 sm:p-9">
          <AlertTriangle className="mx-auto h-12 w-12 text-red-400" />
          <h2 className="mt-5 text-2xl font-bold text-white">Deine Datenlöschung wurde beantragt</h2>
          {seconds > 0 && request.status === "undo" ? <><p className="mt-3 text-sm text-slate-400">Der Antrag wird in <strong className="text-white">{seconds} Sekunden</strong> an Fufi zur Prüfung weitergegeben.</p><button type="button" disabled={busy} onClick={undo} className="mt-7 w-full rounded-xl bg-red-600 px-5 py-3.5 font-bold text-white hover:bg-red-500 disabled:opacity-50">Rückgängig machen ({seconds}s)</button></> : <><p className="mt-3 text-sm leading-6 text-slate-400">Die Rücknahmefrist ist abgelaufen. Fufi erhält eine Discord-DM und prüft den Antrag im Admin-Dashboard. Die Löschung erfolgt nach Genehmigung innerhalb von 24–98 Stunden.</p><button type="button" onClick={() => { setRequest({ ...request, status: "pending" }); setStep(0); }} className="mt-7 rounded-xl border border-slate-700 px-5 py-3 font-semibold text-white hover:bg-white/5">Verstanden</button></>}
          {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
        </div>
      </div>}
    </section>
  );
}
