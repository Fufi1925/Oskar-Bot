"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React from "react";
import { Server, Users } from "lucide-react";

type FeaturedServer = { guild_id: string; name: string; icon: string | null; members: number };

export function FeaturedServerMarquee() {
  useWebsiteLocale();
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
  return <section className="overflow-hidden border-b border-white/10 bg-[#080808] py-10 sm:py-14">
    <div className="mx-auto mb-5 max-w-[1240px] px-4 text-center sm:mb-7 sm:px-6"><p className="text-[10px] font-medium uppercase tracking-[.2em] text-zinc-500">Community</p><h2 className="mt-2 text-2xl font-medium tracking-tight text-white sm:mt-3 sm:text-3xl">Server, die uns vertrauen</h2></div>
    <div className="server-marquee flex w-max px-2">
      {[0, 1, 2].map((copy) => <div key={copy} className="flex shrink-0 gap-4 pr-4" aria-hidden={copy > 0}>{servers.map((server) => <article key={`${copy}-${server.guild_id}`} className="flex w-[240px] shrink-0 items-center gap-3 rounded-xl border border-white/10 bg-[#101010] p-3 sm:w-[280px] sm:p-4">
        {server.icon ? <img src={server.icon} alt="" className="h-12 w-12 shrink-0 rounded-xl border border-white/10 object-cover" /> : <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-blue-500/10"><Server className="h-5 w-5 text-blue-400" /></span>}
        <div className="min-w-0"><h3 className="truncate text-sm font-black text-white">{server.name}</h3><p className="mt-1 flex items-center gap-1.5 text-xs text-zinc-500"><Users className="h-3.5 w-3.5" />{server.members.toLocaleString(websiteLocale())} Mitglieder</p></div>
      </article>)}</div>)}
    </div>
    <style jsx global>{`@keyframes featuredServerRun { from { transform: translate3d(0,0,0); } to { transform: translate3d(-33.333333%,0,0); } } .server-marquee { animation: featuredServerRun ${Math.max(26, servers.length * 5)}s linear infinite; will-change: transform; backface-visibility: hidden; } .server-marquee:hover { animation-play-state: paused; } @media (prefers-reduced-motion: reduce) { .server-marquee { animation: none; width: auto; overflow-x: auto; } .server-marquee [aria-hidden="true"] { display: none; } }`}</style>
  </section>;
}
