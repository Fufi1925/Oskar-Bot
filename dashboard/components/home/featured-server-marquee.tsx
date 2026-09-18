"use client";

import React from "react";
import { Server, Users } from "lucide-react";

type FeaturedServer = { guild_id: string; name: string; icon: string | null; members: number };

export function FeaturedServerMarquee() {
  const [servers, setServers] = React.useState<FeaturedServer[]>([]);
  React.useEffect(() => {
    let active = true;
    fetch("/api/bot/bot/featured-servers", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (active) setServers(data?.servers || []); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  if (!servers.length) return null;
  return <section className="overflow-hidden border-b border-blue-500/10 bg-[#0b0a0c] py-16 sm:py-20">
    <div className="mx-auto mb-9 max-w-[1320px] px-4 text-center sm:px-6"><p className="text-[10px] font-black uppercase tracking-[.28em] text-blue-400">Community</p><h2 className="mt-3 text-3xl font-black tracking-tight text-white sm:text-4xl">Server, die auf University Bot vertrauen</h2></div>
    <div className="server-marquee flex w-max px-2 hover:[animation-play-state:paused]">
      {[0, 1, 2].map((copy) => <div key={copy} className="flex shrink-0 gap-4 pr-4" aria-hidden={copy > 0}>{servers.map((server) => <article key={`${copy}-${server.guild_id}`} className="flex w-[280px] shrink-0 items-center gap-3 rounded-2xl border border-white/[.08] bg-[#121116] p-4 shadow-[0_12px_35px_rgba(0,0,0,.22)] sm:w-[320px]">
        {server.icon ? <img src={server.icon} alt="" className="h-12 w-12 shrink-0 rounded-xl border border-white/10 object-cover" /> : <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-blue-500/10"><Server className="h-5 w-5 text-blue-400" /></span>}
        <div className="min-w-0"><h3 className="truncate text-sm font-black text-white">{server.name}</h3><p className="mt-1 flex items-center gap-1.5 text-xs text-zinc-500"><Users className="h-3.5 w-3.5" />{server.members.toLocaleString("de-DE")} Mitglieder</p></div>
      </article>)}</div>)}
    </div>
    <style jsx global>{`@keyframes featuredServerRun { from { transform: translateX(0); } to { transform: translateX(-33.333333%); } } .server-marquee { animation: featuredServerRun ${Math.max(26, servers.length * 5)}s linear infinite; will-change: transform; } @media (prefers-reduced-motion: reduce) { .server-marquee { animation-play-state: paused; } }`}</style>
  </section>;
}
