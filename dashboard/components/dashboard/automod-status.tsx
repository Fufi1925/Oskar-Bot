"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ModuleState {
  event: string;
  punishment: string | null;
  active: boolean;
  listener_loaded: boolean;
}

interface StatusPayload {
  master_enabled: boolean;
  modules: ModuleState[];
  active_count: number;
  ignored_channels: string[];
  ignored_roles: string[];
  log_channel: string | null;
  missing_permissions: string[];
  live: string;
}

/**
 * Shows what automod is really doing right now.
 *
 * The listeners read their configuration from the database on every single
 * message, so a saved change is live immediately. This reads the same rows
 * they do, which turns "trust me" into something verifiable.
 */
export function AutomodStatus({ guildId }: { guildId: string }) {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.getAutomodStatus(guildId));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  if (loading) {
    return (
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 flex items-center justify-center border-glow-card">
        <Loader2 className="h-6 w-6 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div
      className={cn(
        "bg-[#10233f] border rounded-3xl p-4 sm:p-6",
        data.master_enabled ? "border-emerald-500/25" : "border-slate-800"
      )}
    >
      <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Zap className={cn("h-5 w-5", data.master_enabled ? "text-emerald-400" : "text-slate-600")} />
          <div>
            <h4 className="font-black text-white">Live status</h4>
            <p className="text-xs text-slate-500 mt-0.5">
              {data.master_enabled
                ? `${data.active_count} of ${data.modules.length} rules are enforcing right now`
                : "Automod is switched off — no rule is enforcing"}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
          title="Re-read from the database"
        >
          <RefreshCw className="h-4 w-4 text-primary" />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {data.modules.map((mod) => (
          <div
            key={mod.event}
            className={cn(
              "flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl border text-sm",
              mod.active
                ? "bg-emerald-500/5 border-emerald-500/20"
                : "bg-white/[0.02] border-white/5"
            )}
          >
            <span className={mod.active ? "text-white font-bold" : "text-slate-500"}>
              {mod.event}
            </span>
            <span
              className={cn(
                "text-[10px] font-black uppercase tracking-widest shrink-0",
                mod.active ? "text-emerald-400" : "text-slate-600"
              )}
            >
              {mod.active ? mod.punishment : mod.punishment ? "paused" : "off"}
            </span>
          </div>
        ))}
      </div>

      {data.missing_permissions.length > 0 && (
        <div className="mt-4 flex gap-3 p-4 bg-amber-500/10 border border-amber-500/25 rounded-2xl">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
          <div>
            <p className="text-sm font-bold text-amber-200">
              The bot is missing permissions
            </p>
            <p className="text-xs text-amber-200/70 mt-1">
              {data.missing_permissions.join(", ")} — the punishments above cannot run
              without them.
            </p>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-[11px] text-slate-600">
        {data.log_channel && <span>Log: #{data.log_channel}</span>}
        {data.ignored_channels.length > 0 && (
          <span>{data.ignored_channels.length} ignored channels</span>
        )}
        {data.ignored_roles.length > 0 && (
          <span>{data.ignored_roles.length} ignored roles</span>
        )}
      </div>

      <p className="mt-4 flex items-start gap-2 text-[11px] text-slate-500 leading-relaxed">
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
        {data.live}
      </p>
    </div>
  );
}
