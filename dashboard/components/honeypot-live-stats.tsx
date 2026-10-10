"use client";

import { BRAND_LOGO } from "@/lib/brand";
import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { RefreshCw, Server, Shield, ShieldCheck } from "lucide-react";
import { AdminLineChart } from "@/components/dashboard/admin-line-chart";

interface LiveStats {
  total_moderations: number; total_servers: number;
  moderations_7d: number; triggered_servers_7d: number;
  history: { day: string; moderations: number | null; servers: number | null }[];
  tracking_since: string; updated_at: string;
}
const invite = process.env.NEXT_PUBLIC_BOT_INVITE_URL || "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

export function HoneypotLiveStats() {
  const [data, setData] = useState<LiveStats | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let running = false;
    const load = async () => {
      if (running) return;
      running = true;
      try {
        const response = await fetch("/api/honeypot-stats", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        const result = await response.json();
        if (!controller.signal.aborted) { setData(result); setError(false); }
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        running = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    load();
    const interval = window.setInterval(load, 30000);
    return () => { controller.abort(); window.clearInterval(interval); };
  }, [revision]);
  const metrics = [
    { label: "Moderations (7d)", value: data?.moderations_7d, icon: ShieldCheck, color: "text-slate-300" },
    { label: "Total Moderations", value: data?.total_moderations, icon: Shield, color: "text-blue-400" },
    { label: "Triggered Servers (7d)", value: data?.triggered_servers_7d, icon: Server, color: "text-slate-300" },
    { label: "Total Servers", value: data?.total_servers, icon: Server, color: "text-slate-300" },
  ];
  return <main className="min-h-screen bg-transparent text-white">
    <header className="border-b border-white/[.07]"><div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-5 py-5">
      <Link href="/" className="flex items-center gap-3"><Image src={BRAND_LOGO} alt="CloudTIX" width={40} height={40} unoptimized className="rounded-xl object-cover" /><span className="text-lg font-semibold sm:text-xl">CloudTIX <span className="text-slate-500">/ Honeypot</span></span></Link>
      <a href={invite} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-black transition hover:bg-slate-200">Invite Bot</a>
    </div></header>
    <div className="mx-auto max-w-4xl space-y-6 px-5 pb-16 pt-10 sm:pt-14">
      <div className="pb-6 text-center"><h1 className="text-3xl font-bold tracking-tight sm:text-5xl">Live Statistics</h1><p className="mt-3 text-sm text-slate-500">Honeypot protection powered by CloudTIX</p></div>
      {error && <div role="status" className="flex items-center justify-between gap-3 rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-200"><p>{data ? "Updates are unavailable. Showing the last successful reading." : "Live statistics are currently unavailable."}</p><button type="button" onClick={() => setRevision(value => value + 1)} className="rounded-lg border border-amber-400/20 p-2" aria-label="Retry"><RefreshCw className="h-4 w-4" /></button></div>}
      <div className="grid grid-cols-2 gap-4 sm:gap-5">{metrics.map(({ label, value, icon: Icon, color }) => <section key={label} className="flex items-center gap-3 rounded-2xl border border-white/[.045] bg-[var(--cloudtix-card)] px-4 py-6 sm:gap-5 sm:p-7"><Icon className={`h-6 w-6 shrink-0 sm:h-7 sm:w-7 ${color}`} /><div className="min-w-0"><h2 className="text-xs text-slate-500 sm:text-base">{label}</h2><p className="mt-1 text-xl font-bold tabular-nums sm:text-3xl">{value === undefined ? loading ? "…" : "—" : value.toLocaleString("en-US")}</p></div></section>)}</div>
      <section className="rounded-2xl border border-white/[.045] bg-[var(--cloudtix-card)] p-4 sm:p-6">
        {data ? <AdminLineChart labels={data.history.map(point => new Date(`${point.day}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }))}
          reihen={[{ key: "moderations", name: "Moderations Issued", farbe: "#f5f5f5", werte: data.history.map(point => point.moderations) }, { key: "servers", name: "Triggered Servers", farbe: "#737373", werte: data.history.map(point => point.servers) }]} hoehe={330} responsive />
          : <div className="grid h-[330px] place-items-center text-sm text-slate-500">{loading ? "Loading live history…" : "History unavailable"}</div>}
      </section>
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs leading-relaxed text-slate-500"><p>{data ? `Updated ${new Date(data.updated_at).toLocaleTimeString("en-US")} · refreshes every 30 seconds` : "No estimated or sample statistics are shown."}</p><Link href="/docs" className="text-slate-400 hover:text-white">Documentation ↗</Link></div>
      {data && <p className="text-xs leading-relaxed text-slate-600">Daily history has been recorded since {new Date(data.tracking_since).toLocaleDateString("en-US")}. Earlier days are left blank. The total includes successful moderations recorded before daily tracking began. Dates use UTC; a server is counted once per reporting period.</p>}
    </div>
  </main>;
}
