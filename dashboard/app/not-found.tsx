import React from "react";
import Link from "next/link";
import { ArrowLeft, Compass, LayoutDashboard, LifeBuoy, Server } from "lucide-react";
import { SUPPORT_INVITE } from "@/lib/legal";

export const metadata = {
  title: "404 — Page not found",
};

const LINKS = [
  {
    href: "/dashboard",
    icon: LayoutDashboard,
    title: "Dashboard",
    desc: "Live status and metrics",
  },
  {
    href: "/dashboard/guilds",
    icon: Server,
    title: "Your servers",
    desc: "Pick a server to configure",
  },
  {
    href: SUPPORT_INVITE,
    icon: LifeBuoy,
    title: "Support",
    desc: "Ask us on Discord",
    external: true,
  },
];

/**
 * Global 404.
 *
 * Next.js ships a bare black-on-white page by default, which looks like the
 * app broke. This keeps the dashboard's look and, more importantly, offers a
 * way out instead of leaving people on a dead end.
 */
export default function NotFound() {
  return (
    <main className="min-h-screen bg-[#070c18] text-slate-200 flex items-center justify-center px-6 py-16 relative overflow-hidden">
      {/* Soft background glow, same language as the dashboard cards. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[420px] w-[720px] rounded-full blur-[120px]"
        style={{ background: "rgba(59,130,246,0.12)" }}
      />

      <div className="relative w-full max-w-2xl text-center">
        <p className="text-[clamp(5rem,18vw,9rem)] leading-none font-black tracking-tighter bg-gradient-to-b from-blue-400 to-blue-600/30 bg-clip-text text-transparent select-none">
          404
        </p>

        <div className="-mt-4 flex items-center justify-center gap-2 text-blue-400">
          <Compass className="h-4 w-4" />
          <span className="text-[11px] font-black uppercase tracking-[0.25em]">
            Page not found
          </span>
        </div>

        <h1 className="mt-6 text-2xl md:text-3xl font-black text-white tracking-tight">
          This page does not exist
        </h1>
        <p className="mt-3 text-slate-400 leading-relaxed max-w-md mx-auto">
          The link may be outdated, or the server was removed from your account.
          Here is where you can go instead.
        </p>

        <div className="mt-10 grid gap-3 sm:grid-cols-3 text-left">
          {LINKS.map((item) => {
            const inner = (
              <>
                <div className="h-10 w-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-3 group-hover:bg-blue-500/20 transition-colors">
                  <item.icon className="h-5 w-5 text-blue-400" />
                </div>
                <p className="font-bold text-white text-sm">{item.title}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{item.desc}</p>
              </>
            );

            const className =
              "group block rounded-2xl border border-white/5 bg-white/[0.02] p-5 hover:bg-white/[0.05] hover:border-blue-500/30 transition-all";

            return item.external ? (
              <a
                key={item.href}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
              >
                {inner}
              </a>
            ) : (
              <Link key={item.href} href={item.href} className={className}>
                {inner}
              </Link>
            );
          })}
        </div>

        <Link
          href="/dashboard"
          className="mt-10 inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-blue-500 text-white text-xs font-black uppercase tracking-widest hover:brightness-110 transition-all"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to the dashboard
        </Link>
      </div>
    </main>
  );
}
