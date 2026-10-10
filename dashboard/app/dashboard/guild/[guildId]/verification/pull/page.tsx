"use client";

import { ModerationHeader } from "@/components/dashboard/moderation-design";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Crown, Link2, Loader2, Lock, Sparkles } from "lucide-react";
import { UserPullPanel } from "@/components/dashboard/user-pull-panel";
import { api } from "@/lib/api";

export default function Page({ params }: { params: { guildId: string } }) {
  const [premium, setPremium] = useState<boolean | null>(null);

  useEffect(() => {
    api.getVerify(params.guildId)
      .then((data) => setPremium(Boolean(data?.pull_premium)))
      .catch(() => setPremium(false));
  }, [params.guildId]);

  return (
    <div className="mx-auto max-w-6xl space-y-7">
      <ModerationHeader icon={Link2} title="User Pull" description="Ausdrücklich autorisierte Verifizierungen sicher mit deinem Zielserver verbinden." />

      {premium === null ? (
        <div className="grid min-h-72 place-items-center rounded-2xl border border-white/[.07] cloudtix-workspace-card bg-[#202124]"><Loader2 className="h-6 w-6 animate-spin text-amber-400" /></div>
      ) : premium ? (
        <UserPullPanel guildId={params.guildId} />
      ) : (
        <section className="relative min-h-[460px] overflow-hidden rounded-2xl border border-amber-400/25 cloudtix-workspace-card bg-[#101014]">
          <div className="pointer-events-none absolute inset-0 opacity-30 blur-[3px]">
            <div className="grid grid-cols-3 gap-3 p-6"><div className="h-24 rounded-2xl bg-slate-800"/><div className="h-24 rounded-2xl bg-slate-800"/><div className="h-24 rounded-2xl bg-slate-800"/></div>
            <div className="mx-6 h-64 rounded-2xl border border-slate-700 bg-slate-900"/>
          </div>
          <div className="absolute inset-0 cloudtix-workspace-field bg-[#09090c]/70" />
          <div className="relative z-10 flex min-h-[460px] items-center justify-center p-5">
            <div className="max-w-md rounded-2xl border border-amber-400/30 cloudtix-workspace-card bg-[#202124] p-6 text-center shadow-2xl">
              <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-amber-400/15"><Crown className="h-7 w-7 text-amber-400" /></span>
              <h3 className="mt-4 text-xl font-semibold text-white">Premium erforderlich</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">Das komplette User-Pull-System ist eine Premium-Funktion. Dazu gehören der Tab, die Einrichtung, Mitgliederlisten, Pull all und das Aktivieren des zusätzlichen <b className="text-slate-300">guilds.join</b>-Scopes.</p>
              <div className="mt-4 flex items-center justify-center gap-2 text-xs font-bold text-amber-300"><Lock className="h-3.5 w-3.5" /> Ohne Premium bleibt der Scope ausgeschaltet</div>
              <Link href="/dashboard/premium" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-amber-400 px-5 py-3 text-sm font-semibold text-black hover:bg-amber-300"><Sparkles className="h-4 w-4" /> Premium freischalten</Link>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
