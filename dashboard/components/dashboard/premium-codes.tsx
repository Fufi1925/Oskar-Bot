"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Ban, Check, Clock, Copy, Gift, KeyRound, Plus, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const INPUT = "w-full rounded-xl border border-slate-800 bg-[#0b0b0f] px-3 py-2.5 text-sm text-white outline-none focus:border-amber-400/40";

function date(value: number) {
  return new Date(value * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

export function PremiumCodes() {
  const [codes, setCodes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState("7");
  const [uses, setUses] = useState("1");
  const [validHours, setValidHours] = useState("24");
  const [fresh, setFresh] = useState("");

  const load = useCallback(async () => {
    try { setCodes((await api.listPremiumCodes())?.codes || []); }
    catch (error: any) { toast.error(error?.message || "Codes konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    const premium_days = Number(days), max_uses = Number(uses), valid_hours = Number(validHours);
    if (!Number.isInteger(premium_days) || premium_days < 1 || !Number.isInteger(max_uses) || max_uses < 1 || !Number.isInteger(valid_hours) || valid_hours < 1) {
      toast.error("Bitte gültige Laufzeiten und Nutzungen eintragen."); return;
    }
    setBusy(true);
    try {
      const result = await api.createPremiumCode({ premium_days, max_uses, valid_hours });
      setFresh(result.code.code);
      toast.success("Premium-Code wurde erstellt.");
      await load();
    } catch (error: any) { toast.error(error?.message || "Code konnte nicht erstellt werden."); }
    finally { setBusy(false); }
  };

  const revokeCode = async (code: string) => {
    if (!confirm(`Code ${code} wirklich deaktivieren? Offene Einlösungen sind danach nicht mehr möglich.`)) return;
    try { await api.revokePremiumCode(code); toast.success("Code deaktiviert."); await load(); }
    catch (error: any) { toast.error(error?.message || "Code konnte nicht deaktiviert werden."); }
  };

  const revokeUse = async (use: any) => {
    if (!confirm(`Premium für ${use.guild_name} sofort einziehen?`)) return;
    try { await api.revokePremiumCodeRedemption(use.id); toast.success("Premium wurde eingezogen."); await load(); }
    catch (error: any) { toast.error(error?.message || "Premium konnte nicht eingezogen werden."); }
  };

  const now = Math.floor(Date.now() / 1000);
  return <section className="overflow-hidden rounded-3xl border border-amber-400/20 bg-gradient-to-br from-amber-500/[0.08] via-[#131318] to-[#131318]">
    <div className="border-b border-white/[0.06] p-5 sm:p-6">
      <div className="flex flex-wrap items-start gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-2xl bg-amber-400/15"><KeyRound className="h-5 w-5 text-amber-300" /></span>
        <div className="min-w-0 flex-1"><h2 className="text-lg font-black text-white">Codes</h2><p className="mt-1 text-xs leading-relaxed text-slate-400">Erstelle sechsstellige Premium-Codes für Verlosungen auf dem Support-Server.</p></div>
        <button onClick={load} className="rounded-xl border border-slate-700 p-2.5 text-slate-400 hover:text-white"><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /></button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Premium-Laufzeit
          <div className="relative mt-1.5"><input className={cn(INPUT,"pr-14")} inputMode="numeric" value={days} onChange={e=>setDays(e.target.value)} /><span className="absolute right-3 top-2.5 text-xs text-slate-500">Tage</span></div>
        </label>
        <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Maximale Nutzer
          <div className="relative mt-1.5"><Users className="absolute left-3 top-3 h-4 w-4 text-slate-600"/><input className={cn(INPUT,"pl-9")} inputMode="numeric" value={uses} onChange={e=>setUses(e.target.value)} /></div>
        </label>
        <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Code einlösbar
          <select className={cn(INPUT,"mt-1.5")} value={validHours} onChange={e=>setValidHours(e.target.value)}><option value="1">1 Stunde</option><option value="6">6 Stunden</option><option value="24">24 Stunden</option><option value="72">3 Tage</option><option value="168">7 Tage</option><option value="720">30 Tage</option></select>
        </label>
      </div>
      <button disabled={busy} onClick={create} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-amber-400 px-4 py-3 text-sm font-black text-black hover:bg-amber-300 disabled:opacity-50 sm:w-auto"><Plus className="h-4 w-4"/>Sechsstelligen Code erstellen</button>
      {fresh && <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.07] p-4"><Check className="h-5 w-5 text-emerald-400"/><div className="flex-1"><p className="text-xs text-emerald-300">Neu erstellt</p><p className="font-mono text-2xl font-black tracking-[0.25em] text-white">{fresh}</p></div><button onClick={()=>{navigator.clipboard.writeText(fresh);toast.success("Code kopiert.")}} className="rounded-xl border border-emerald-500/20 p-2.5 text-emerald-300"><Copy className="h-4 w-4"/></button></div>}
    </div>

    <div className="space-y-3 p-4 sm:p-5">
      {loading ? <p className="py-6 text-center text-sm text-slate-500">Codes werden geladen …</p> : !codes.length ? <p className="py-6 text-center text-sm text-slate-500">Noch keine Codes erstellt.</p> : codes.map(code => {
        const expired=code.redeem_until<=now, full=code.uses>=code.max_uses;
        const label=code.revoked?"Deaktiviert":expired?"Abgelaufen":full?"Vollständig genutzt":"Offen";
        return <article key={code.code} className="rounded-2xl border border-slate-800 bg-[#0d0d11] p-4">
          <div className="flex flex-wrap items-center gap-3"><span className="font-mono text-xl font-black tracking-[0.18em] text-white">{code.code}</span><span className={cn("rounded-full border px-2.5 py-1 text-[10px] font-bold",label==="Offen"?"border-emerald-500/20 bg-emerald-500/10 text-emerald-300":"border-slate-700 bg-slate-800/50 text-slate-400")}>{label}</span><span className="ml-auto text-xs text-slate-500">{code.uses}/{code.max_uses} genutzt</span>{!code.revoked&&!expired&&!full&&<button onClick={()=>revokeCode(code.code)} title="Code deaktivieren" className="rounded-lg p-2 text-slate-500 hover:bg-red-500/10 hover:text-red-400"><Ban className="h-4 w-4"/></button>}</div>
          <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3"><span className="flex items-center gap-2"><Gift className="h-3.5 w-3.5 text-amber-400"/>{code.premium_days} Tage Premium</span><span className="flex items-center gap-2"><Clock className="h-3.5 w-3.5 text-cyan-400"/>Einlösbar bis {date(code.redeem_until)}</span><span className="flex items-center gap-2"><Users className="h-3.5 w-3.5 text-violet-400"/>{code.max_uses} Nutzer maximal</span></div>
          {!!code.redemptions?.length&&<div className="mt-4 overflow-hidden rounded-xl border border-slate-800">{code.redemptions.map((use:any)=><div key={use.id} className="flex flex-col gap-2 border-b border-slate-800 px-3 py-3 last:border-0 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-white">{use.user_name}</p><p className="truncate text-[11px] text-slate-500">{use.guild_name} · bis {date(use.expires_at)}</p></div>{use.revoked?<span className="text-[11px] font-bold text-red-400">Eingezogen</span>:<button onClick={()=>revokeUse(use)} className="rounded-lg border border-red-500/20 px-3 py-2 text-[11px] font-bold text-red-300 hover:bg-red-500/10">Premium einziehen</button>}</div>)}</div>}
        </article>;
      })}
    </div>
  </section>;
}
