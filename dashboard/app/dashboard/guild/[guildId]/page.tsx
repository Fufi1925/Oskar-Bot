"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity, ArrowRight, BarChart4, Bot, Check, CheckCircle2, FileJson, FileText,
  Hash, Link2, Loader2, Mail, Mic, Settings, Shield, ShieldCheck, SmilePlus,
  Sparkles, Ticket, UserCheck, Users, Volume2, Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ConfigTransferPanel } from "@/components/dashboard/config-transfer-panel";

const MODULE_ICONS: Record<string, any> = {
  welcome: SmilePlus,
  automod: ShieldCheck,
  antinuke: Shield,
  verification: UserCheck,
  leveling: BarChart4,
  tickets: Ticket,
  logging: FileText,
  autorole: Bot,
  reactionroles: Zap,
  vanityroles: Sparkles,
  customroles: Sparkles,
  invcrole: Volume2,
  j2c: Mic,
  nickname: UserCheck,
  noprefix: Hash,
  tracking: Link2,
};

interface ModuleState {
  key: string;
  label: string;
  configured: boolean;
  entries: number;
  path: string;
}

interface StatusPayload {
  prefix: string;
  modules: ModuleState[];
  active_count: number;
  total_count: number;
  completion: number;
  guild: {
    member_count: number;
    channel_count: number;
    role_count: number;
    bot_count: number;
    boost_level: number;
    boost_count: number;
    verification_level: string;
    created_at: number;
    owner_id: string | null;
  };
}

export default function GuildOverviewPage({ params }: { params: { guildId: string } }) {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview" | "backup">("overview");

  useEffect(() => {
    api
      .getModuleStatus(params.guildId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [params.guildId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) {
    return (
      <p className="text-center text-slate-500 py-16">
        Could not load this server&apos;s status.
      </p>
    );
  }

  const active = data.modules.filter((m) => m.configured);
  const inactive = data.modules.filter((m) => !m.configured);

  const stats = [
    { label: "Members", value: data.guild.member_count.toLocaleString(), icon: Users, color: "text-blue-400" },
    { label: "Channels", value: data.guild.channel_count, icon: Hash, color: "text-purple-400" },
    { label: "Roles", value: data.guild.role_count, icon: Shield, color: "text-emerald-400" },
    { label: "Bots", value: data.guild.bot_count, icon: Bot, color: "text-amber-400" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex gap-2 p-1.5 bg-[#10233f]/70 border border-slate-800 rounded-2xl w-fit">
        {([
          ["overview", "Overview", Activity],
          ["backup", "Backup & Restore", FileJson],
        ] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
              tab === id ? "bg-primary text-white" : "text-slate-400 hover:text-white"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === "backup" ? (
        <ConfigTransferPanel guildId={params.guildId} />
      ) : (
        <>
          {/* Setup progress */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
            <div className="flex items-center justify-between gap-6 flex-wrap mb-6">
              <div>
                <h2 className="text-xl font-black text-white">Setup progress</h2>
                <p className="text-sm text-slate-400 mt-1">
                  {data.active_count} of {data.total_count} modules configured
                </p>
              </div>
              <div className="text-right">
                <span
                  className={cn(
                    "text-4xl font-black",
                    data.completion >= 70
                      ? "text-emerald-400"
                      : data.completion >= 35
                      ? "text-amber-400"
                      : "text-slate-500"
                  )}
                >
                  {data.completion}%
                </span>
              </div>
            </div>

            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-700",
                  data.completion >= 70
                    ? "bg-emerald-400"
                    : data.completion >= 35
                    ? "bg-amber-400"
                    : "bg-slate-600"
                )}
                style={{ width: `${data.completion}%` }}
              />
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
              {stats.map((stat) => (
                <div
                  key={stat.label}
                  className="bg-white/[0.02] border border-white/5 rounded-2xl p-4"
                >
                  <stat.icon className={cn("h-5 w-5 mb-2", stat.color)} />
                  <p className="text-2xl font-black text-white">{stat.value}</p>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-0.5">
                    {stat.label}
                  </p>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-4 mt-6 pt-6 border-t border-white/5">
              <div className="text-xs">
                <span className="text-slate-500">Prefix </span>
                <code className="px-2 py-0.5 rounded-lg bg-white/[0.05] text-primary font-mono font-bold">
                  {data.prefix}
                </code>
              </div>
              {data.guild.boost_level > 0 && (
                <div className="text-xs">
                  <span className="text-slate-500">Boost </span>
                  <span className="text-pink-400 font-bold">
                    Level {data.guild.boost_level} · {data.guild.boost_count} boosts
                  </span>
                </div>
              )}
              <div className="text-xs">
                <span className="text-slate-500">Verification </span>
                <span className="text-slate-300 font-bold capitalize">
                  {data.guild.verification_level}
                </span>
              </div>
            </div>
          </div>

          {/* Active modules */}
          {active.length > 0 && (
            <section>
              <div className="flex items-center gap-3 mb-5">
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                <h2 className="text-lg font-black text-white">Configured</h2>
                <span className="text-xs font-black text-slate-600">{active.length}</span>
                <div className="h-px flex-1 bg-slate-800" />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {active.map((mod) => {
                  const Icon = MODULE_ICONS[mod.key] || Settings;
                  return (
                    <Link
                      key={mod.key}
                      href={`/dashboard/guild/${params.guildId}/${mod.path}`}
                      className="group bg-[#10233f] border border-emerald-500/20 rounded-3xl p-5 hover:border-emerald-500/40 transition-all"
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="h-10 w-10 bg-emerald-500/10 rounded-xl flex items-center justify-center text-emerald-400 group-hover:scale-110 transition-transform">
                          <Icon className="h-5 w-5" />
                        </div>
                        <span className="flex items-center gap-1 text-[10px] font-black uppercase text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-lg border border-emerald-500/20">
                          <Check className="h-2.5 w-2.5" />
                          on
                        </span>
                      </div>
                      <h3 className="font-black text-white">{mod.label}</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        {mod.entries} {mod.entries === 1 ? "entry" : "entries"}
                      </p>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* Not configured yet */}
          {inactive.length > 0 && (
            <section>
              <div className="flex items-center gap-3 mb-5">
                <Sparkles className="h-5 w-5 text-slate-600" />
                <h2 className="text-lg font-black text-white">Not set up yet</h2>
                <span className="text-xs font-black text-slate-600">{inactive.length}</span>
                <div className="h-px flex-1 bg-slate-800" />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {inactive.map((mod) => {
                  const Icon = MODULE_ICONS[mod.key] || Settings;
                  return (
                    <Link
                      key={mod.key}
                      href={`/dashboard/guild/${params.guildId}/${mod.path}`}
                      className="group bg-[#10233f]/50 border border-slate-800 rounded-3xl p-5 hover:border-primary/40 hover:bg-[#10233f] transition-all"
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="h-10 w-10 bg-slate-800/60 rounded-xl flex items-center justify-center text-slate-500 group-hover:text-primary group-hover:scale-110 transition-all">
                          <Icon className="h-5 w-5" />
                        </div>
                        <ArrowRight className="h-4 w-4 text-slate-700 group-hover:text-primary group-hover:translate-x-1 transition-all" />
                      </div>
                      <h3 className="font-bold text-slate-300 group-hover:text-white transition-colors">
                        {mod.label}
                      </h3>
                      <p className="text-xs text-slate-600 mt-1">Set up now</p>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
