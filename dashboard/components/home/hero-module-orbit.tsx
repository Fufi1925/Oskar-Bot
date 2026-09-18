"use client";

import React from "react";
import { BarChart3, Gift, ShieldCheck, Ticket } from "lucide-react";

const MODULES = [
  { label: "Moderation", hint: "LIVE MODUL", icon: ShieldCheck, position: "left-0 top-[9%] sm:left-0" },
  { label: "Ticket-System", hint: "LIVE MODUL", icon: Ticket, position: "right-0 top-[18%]" },
  { label: "Level-System", hint: "LIVE MODUL", icon: BarChart3, position: "bottom-[12%] left-[4%]" },
  { label: "Werbegeschenke", hint: "LIVE MODUL", icon: Gift, position: "bottom-[4%] right-[4%]" },
];

export function HeroModuleOrbit() {
  return <div className="relative mx-auto h-[470px] w-full max-w-[620px] sm:h-[570px]" aria-label="Ausgewählte Bot-Module">
    <div className="pointer-events-none absolute left-1/2 top-1/2 h-[330px] w-[330px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-blue-500/20 bg-blue-500/[.018] shadow-[inset_0_0_80px_rgba(37,99,235,.035),0_0_90px_rgba(37,99,235,.05)] sm:h-[430px] sm:w-[430px]">
      <div className="absolute inset-[10%] rounded-full border border-dashed border-blue-400/25" />
      <div className="absolute inset-[23%] rounded-full border border-blue-500/10" />
      <span className="orbit-pulse absolute left-1/2 top-[-4px] h-2 w-2 -translate-x-1/2 rounded-full bg-blue-400 shadow-[0_0_16px_4px_rgba(96,165,250,.8)]" />
    </div>

    <div className="absolute left-1/2 top-1/2 z-10 grid h-[156px] w-[156px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[42px] border border-blue-400/30 bg-[#15121a] shadow-[inset_0_1px_rgba(255,255,255,.06),0_24px_70px_rgba(0,0,0,.55),0_0_65px_rgba(37,99,235,.12)] sm:h-[196px] sm:w-[196px] sm:rounded-[54px]">
      <div className="absolute inset-4 rounded-[32px] border border-white/[.04] bg-black/20 sm:inset-5 sm:rounded-[40px]" />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon-192.png" alt="University Bot" className="relative h-[92px] w-[92px] rounded-[26px] object-cover shadow-[0_10px_35px_rgba(0,0,0,.55)] sm:h-[118px] sm:w-[118px] sm:rounded-[32px]" />
    </div>

    {MODULES.map(({ label, hint, icon: Icon, position }, index) => <article key={label} className={`hero-module-card absolute z-20 ${position} flex w-[180px] items-center gap-3 rounded-2xl border border-blue-400/25 bg-[#151219]/95 p-3 shadow-[0_18px_48px_rgba(0,0,0,.42)] backdrop-blur-xl transition duration-300 hover:-translate-y-1 hover:border-blue-400/45 sm:w-[200px] sm:p-4`} style={{ animationDelay: `${index * 180}ms` }}>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-blue-400/30 bg-blue-500/10 shadow-[inset_0_1px_rgba(255,255,255,.05)]"><Icon className="h-5 w-5 text-blue-400" /></span>
      <div className="min-w-0"><h2 className="truncate text-[13px] font-black text-white sm:text-sm">{label}</h2><p className="mt-1 text-[9px] font-bold tracking-[.16em] text-zinc-600">{hint}</p></div>
    </article>)}

    <style jsx global>{`
      @keyframes orbitPulse { from { transform: translateX(-50%) rotate(0deg) translateY(-165px); } to { transform: translateX(-50%) rotate(360deg) translateY(-165px); } }
      @keyframes moduleFloat { 0%,100% { margin-top: 0; } 50% { margin-top: -7px; } }
      .orbit-pulse { transform-origin: 50% 169px; animation: orbitPulse 13s linear infinite; }
      .hero-module-card { animation: moduleFloat 5s ease-in-out infinite; }
      @media (min-width:640px) { @keyframes orbitPulse { from { transform: translateX(-50%) rotate(0deg) translateY(-215px); } to { transform: translateX(-50%) rotate(360deg) translateY(-215px); } } .orbit-pulse { transform-origin: 50% 219px; } }
      @media (prefers-reduced-motion:reduce) { .orbit-pulse,.hero-module-card { animation:none!important; } }
    `}</style>
  </div>;
}
