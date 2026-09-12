"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, BadgeCheck, CalendarDays, Crown, Server, ShieldCheck, Sparkles, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";

const WAIT_SECONDS = 3;
const date = (value?: number | null) => value ? new Date(value * 1000).toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" }) : "–";

export function PremiumHinweis() {
  const { data: session, status } = useSession();
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);
  const [returning, setReturning] = React.useState(false);
  const [remaining, setRemaining] = React.useState(WAIT_SECONDS);
  const [premium, setPremium] = React.useState<any>(null);

  React.useEffect(() => {
    if (status !== "authenticated" || !session?.user?.id || !pathname?.startsWith("/dashboard")) return;
    let cancelled = false;
    void Promise.all([
      fetch("/api/bot/beta/notice", { cache: "no-store" }).then(r => r.ok ? r.json() : null),
      fetch(`/api/bot/premium/me/${session.user.id}`, { cache: "no-store" }).then(r => r.ok ? r.json() : null),
    ]).then(([notice, account]) => {
      if (cancelled || !notice?.zeigen) return;
      setReturning(Boolean(notice.rueckkehr));
      setPremium(account?.premium || null);
      setRemaining(notice.rueckkehr ? 0 : WAIT_SECONDS);
      setOpen(true);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [status, session?.user?.id, pathname]);

  React.useEffect(() => {
    if (!open || remaining <= 0) return;
    const timer = window.setTimeout(() => setRemaining(value => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [open, remaining]);

  const close = () => {
    if (remaining > 0) return;
    setOpen(false);
    fetch("/api/bot/beta/notice/seen", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
  };

  if (!open) return null;
  const used = premium?.slots?.length || 0;
  return <div role="dialog" aria-modal="true" aria-labelledby="premium-dialog-title" className="fixed inset-0 z-[10001] grid place-items-center overflow-y-auto bg-black/80 p-4 backdrop-blur-md">
    <div className="relative w-full max-w-lg overflow-hidden rounded-[30px] border border-amber-400/35 bg-[#111116] shadow-2xl shadow-amber-500/10">
      <div className="absolute inset-x-0 top-0 h-52 bg-[radial-gradient(circle_at_50%_0%,rgba(251,191,36,.24),transparent_72%)]"/>
      <button onClick={close} disabled={remaining>0} aria-label="Schließen" className="absolute right-4 top-4 z-10 grid h-9 w-9 place-items-center rounded-full border border-white/10 bg-black/20 text-slate-400 hover:text-white disabled:opacity-30"><X className="h-4 w-4"/></button>
      <div className="relative px-5 pb-6 pt-8 sm:px-7">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-amber-400/25 bg-amber-400/15"><Crown className="h-8 w-8 text-amber-300"/></div>
        <div className="mt-4 text-center"><span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-black text-emerald-300"><BadgeCheck className="h-3.5 w-3.5"/>Premium aktiviert</span><h2 id="premium-dialog-title" className="mt-3 text-2xl font-black text-white">{returning ? "Willkommen zurück bei Premium" : "Ein Admin hat dir Premium gegeben"}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">Dein Discord-Konto ist freigeschaltet. Jetzt kannst du bis zu drei Server fest mit Premium verbinden.</p></div>

        <div className="mt-5 grid grid-cols-3 gap-2"><Info icon={CalendarDays} value={`${premium?.duration_days || "–"} Tage`} label={`bis ${date(premium?.expires_at)}`}/><Info icon={Server} value={`${used} / 3`} label="Plätze belegt"/><Info icon={ShieldCheck} value="Aktiv" label="Supportrolle"/></div>

        <div className="mt-5 rounded-2xl border border-violet-500/20 bg-violet-500/[0.06] p-4"><div className="flex gap-3"><Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-violet-300"/><div><p className="font-black text-white">Deine nächsten Schritte</p><ol className="mt-2 space-y-2 text-xs leading-5 text-slate-400"><li><strong className="text-violet-200">1.</strong> Premiumverwaltung öffnen</li><li><strong className="text-violet-200">2.</strong> Bis zu drei Server auswählen</li><li><strong className="text-violet-200">3.</strong> Feste Zuweisung bestätigen und Premiumfunktionen einrichten</li></ol></div></div></div>

        <div className="mt-5 grid gap-2 sm:grid-cols-[1fr_auto]"><Link href="/dashboard/premium" onClick={close} aria-disabled={remaining>0} className={`inline-flex items-center justify-center gap-2 rounded-xl bg-amber-400 px-5 py-3.5 text-sm font-black text-black ${remaining>0?"pointer-events-none opacity-50":"hover:brightness-110"}`}>Drei Serverplätze verwalten<ArrowRight className="h-4 w-4"/></Link><button onClick={close} disabled={remaining>0} className="rounded-xl border border-slate-700 px-4 py-3.5 text-sm font-bold text-slate-300 disabled:opacity-40">{remaining>0?`Weiter in ${remaining}s`:"Später"}</button></div>
        {remaining>0&&<p className="mt-3 text-center text-[11px] text-slate-600">Premiumplätze bleiben bis zum Laufzeitende fest mit dem gewählten Server verbunden.</p>}
      </div>
    </div>
  </div>;
}

function Info({icon:Icon,value,label}:{icon:any,value:string,label:string}){return <div className="rounded-xl border border-slate-800 bg-black/20 p-3 text-center"><Icon className="mx-auto h-4 w-4 text-amber-300"/><p className="mt-2 text-sm font-black text-white">{value}</p><p className="mt-0.5 truncate text-[10px] text-slate-500">{label}</p></div>}
