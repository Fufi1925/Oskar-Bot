"use client";

import { openLoginPanel } from "@/lib/login-panel";

import { LogIn, ShieldCheck, UserRound, X } from "lucide-react";
import Link from "next/link";

export function AccountLoginGate() {
  return (
    <main className="relative min-h-[calc(100vh-76px)] overflow-hidden bg-[var(--cloudtix-field)] px-4 py-16">
      <div aria-hidden="true" className="mx-auto max-w-5xl opacity-25 blur-[2px]">
        <div className="h-48 rounded-[28px] border border-slate-800 bg-gradient-to-br from-indigo-500/20 via-[var(--cloudtix-card)] to-slate-500/10" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((item) => <div key={item} className="h-28 rounded-2xl border border-slate-800 bg-[var(--cloudtix-card)]" />)}
        </div>
      </div>

      <div className="fixed inset-0 z-[70] grid place-items-center bg-black/70 p-4 backdrop-blur-md">
        <section role="dialog" aria-modal="true" aria-labelledby="account-login-title" className="relative w-full max-w-md rounded-[28px] border border-slate-700 bg-[var(--cloudtix-card)] p-7 text-center shadow-2xl shadow-black/70 sm:p-9">
          <Link href="/" aria-label="Schließen" className="absolute right-4 top-4 rounded-xl p-2 text-slate-500 transition-colors hover:bg-white/5 hover:text-white"><X className="h-5 w-5" /></Link>
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-indigo-400/25 bg-indigo-500/15">
            <UserRound className="h-8 w-8 text-indigo-300" />
          </div>
          <h1 id="account-login-title" className="mt-6 text-2xl font-bold text-white">Dein Konto öffnen</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">Melde dich mit Discord an, um ausschließlich deine echten Profildaten, Server und Bot-Aktivität zu sehen.</p>
          <button type="button" onClick={() => openLoginPanel()} className="mt-7 flex w-full items-center justify-center gap-2.5 rounded-xl bg-primary px-5 py-3.5 font-semibold text-white transition-colors hover:bg-primary-hover">
            <LogIn className="h-5 w-5" /> Mit Discord anmelden
          </button>
          <p className="mt-5 flex items-center justify-center gap-1.5 text-xs text-slate-600"><ShieldCheck className="h-3.5 w-3.5" /> Wir zeigen keine erfundenen Beispielwerte.</p>
        </section>
      </div>
    </main>
  );
}
