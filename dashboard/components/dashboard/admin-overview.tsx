"use client";

import React from "react";
import {
  Activity, ArrowRight, Bot, CreditCard, FileText, Lightbulb,
  Server, ShieldCheck, Sparkles, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type AdminOverviewData = {
  period_hours: number;
  captured_at: number;
  baseline_at: number;
  totals: { servers: number; users: number; premium_active: number };
  new: {
    servers: number;
    users: number;
    firewall_blocks: number;
    premium_purchases: number;
    ideas: number;
    applications: number;
  };
  pending: { premium_purchases: number; ideas: number; applications: number };
  system: { api_latency_ms: number; ready: boolean; guilds_available: boolean };
};

type OpenTab = (tab: string) => void;

const format = (value: number | undefined) => Number(value || 0).toLocaleString("de-DE");

export function AdminOverview({
  data,
  loading,
  onOpen,
}: {
  data: AdminOverviewData | null;
  loading: boolean;
  onOpen: OpenTab;
}) {
  const cards = [
    { label: "Neue Server", value: data?.new.servers, note: "Netto-Wachstum", icon: Server, tone: "text-violet-300", tab: "servers" },
    { label: "Neue Nutzer", value: data?.new.users, note: "Netto-Wachstum", icon: Users, tone: "text-blue-300", tab: "dashusers" },
    { label: "Firewall blockiert", value: data?.new.firewall_blocks, note: "Anfragen abgewehrt", icon: ShieldCheck, tone: "text-rose-300", tab: "firewall" },
    { label: "Premium-Anfragen", value: data?.new.premium_purchases, note: `${format(data?.pending.premium_purchases)} noch offen`, icon: CreditCard, tone: "text-amber-300", tab: "premium" },
    { label: "Neue Ideen", value: data?.new.ideas, note: `${format(data?.pending.ideas)} zu prüfen`, icon: Lightbulb, tone: "text-emerald-300", tab: "ideas" },
    { label: "Bewerbungen", value: data?.new.applications, note: `${format(data?.pending.applications)} noch offen`, icon: FileText, tone: "text-cyan-300", tab: "webapply" },
  ];

  const inbox = [
    { label: "Premium-Anfragen", value: data?.pending.premium_purchases, tab: "premium", icon: CreditCard },
    { label: "Offene Ideen", value: data?.pending.ideas, tab: "ideas", icon: Lightbulb },
    { label: "Offene Bewerbungen", value: data?.pending.applications, tab: "webapply", icon: FileText },
  ];

  return (
    <div className="space-y-5">
      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-white">Was ist neu?</h2>
            <p className="mt-1 text-xs text-slate-500">Aktivität der letzten 24 Stunden</p>
          </div>
          {data?.captured_at && (
            <p className="text-[11px] text-slate-600">
              Stand {new Date(data.captured_at * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}
            </p>
          )}
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {cards.map((card) => (
            <button
              key={card.label}
              type="button"
              onClick={() => onOpen(card.tab)}
              className="group flex items-center gap-3 rounded-xl border border-white/[.06] bg-[#202126] p-4 text-left transition-colors hover:border-white/[.12] hover:bg-[#23252b]"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-black/15">
                <card.icon className={cn("h-4 w-4", card.tone)} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-xl font-semibold tabular-nums text-white">
                  {loading ? "–" : format(card.value)}
                </span>
                <span className="mt-0.5 block text-xs font-medium text-slate-300">{card.label}</span>
                <span className="mt-0.5 block truncate text-[11px] text-slate-600">{card.note}</span>
              </span>
              <ArrowRight className="h-3.5 w-3.5 text-slate-700 transition group-hover:translate-x-0.5 group-hover:text-slate-400" />
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <section className="rounded-xl border border-white/[.06] bg-[#202126] p-4">
          <div className="mb-2 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-300" />
            <h2 className="text-sm font-semibold text-white">Zu erledigen</h2>
          </div>
          <div className="divide-y divide-white/[.055]">
            {inbox.map((item) => (
              <button key={item.label} type="button" onClick={() => onOpen(item.tab)} className="group flex w-full items-center gap-3 py-3 text-left first:pt-2 last:pb-1">
                <item.icon className="h-4 w-4 text-slate-500" />
                <span className="flex-1 text-sm text-slate-300 group-hover:text-white">{item.label}</span>
                <span className="rounded-md bg-black/20 px-2 py-1 text-xs font-semibold tabular-nums text-slate-300">{loading ? "–" : format(item.value)}</span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-700 group-hover:text-slate-400" />
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-white/[.06] bg-[#202126] p-4">
          <div className="mb-4 flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-300" />
            <h2 className="text-sm font-semibold text-white">System</h2>
          </div>
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between"><span className="text-slate-500">Bot</span><span className={data?.system.ready ? "text-emerald-300" : "text-amber-300"}>{data?.system.ready ? "Online" : "Startet"}</span></div>
            <div className="flex items-center justify-between"><span className="text-slate-500">Antwortzeit</span><span className="tabular-nums text-slate-300">{loading ? "–" : `${format(data?.system.api_latency_ms)} ms`}</span></div>
            <div className="flex items-center justify-between"><span className="text-slate-500">Aktive Server</span><span className="tabular-nums text-slate-300">{loading ? "–" : format(data?.totals.servers)}</span></div>
            <div className="flex items-center justify-between"><span className="text-slate-500">Erreichte Nutzer</span><span className="tabular-nums text-slate-300">{loading ? "–" : format(data?.totals.users)}</span></div>
            <div className="flex items-center justify-between"><span className="text-slate-500">Aktive Premium-Konten</span><span className="tabular-nums text-slate-300">{loading ? "–" : format(data?.totals.premium_active)}</span></div>
          </div>
        </section>
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-slate-600">
        <Bot className="h-3 w-3" /> Server und Nutzer zeigen das Netto-Wachstum seit dem gespeicherten Vergleichspunkt.
      </p>
    </div>
  );
}
