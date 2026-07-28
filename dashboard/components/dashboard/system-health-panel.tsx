"use client";

import React, { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, Database, FileWarning,
  HardDrive, Loader2, RefreshCw, ScrollText, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface HealthPayload {
  bot_ready: boolean;
  uptime_seconds: number;
  flags: Record<string, boolean>;
  shard_latency: Record<string, number>;
  lavalink_nodes: Record<string, string>;
  lavalink_reconnects: number;
  discord_status: string;
  discord_incidents: string[];
  integrity: Record<string, string>;
  last_backup_at: number | null;
  last_cleanup_removed: number;
  failed_extensions: string[];
  recovered_extensions: string[];
  oauth_errors: number;
  session_warning: string | null;
  command_errors: Record<string, number>;
}

function formatUptime(seconds: number) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function Card({ title, icon: Icon, children, tone = "neutral" }: {
  title: string; icon: any; children: React.ReactNode; tone?: "neutral" | "good" | "warn";
}) {
  return (
    <div className={cn(
      "bg-[#10233f] border rounded-3xl p-4 sm:p-6",
      tone === "good" && "border-emerald-500/25",
      tone === "warn" && "border-amber-500/30",
      tone === "neutral" && "border-slate-800",
    )}>
      <div className="flex items-center gap-3 mb-4">
        <Icon className={cn(
          "h-5 w-5",
          tone === "good" ? "text-emerald-400" : tone === "warn" ? "text-amber-400" : "text-primary",
        )} />
        <h4 className="font-black text-white text-sm uppercase tracking-wider">{title}</h4>
      </div>
      {children}
    </div>
  );
}

export function SystemHealthPanel() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (silent = false) => {
    if (silent) setRefreshing(true);
    try {
      const data = await api.getAdminHealth();
      setHealth(data);
      if (data.flags?.railway_log_watch) {
        try {
          const logData = await api.getAdminLogs(30);
          setLogs(logData.entries || []);
        } catch {
          setLogs([]);
        }
      }
    } catch (err: any) {
      if (!silent) toast.error(err?.message || "Could not load health data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(() => load(true), 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!health) return <p className="text-slate-500">No health data available.</p>;

  const integrityIssues = Object.entries(health.integrity).filter(([, v]) => v !== "ok");
  const nodesConnected = Object.values(health.lavalink_nodes).filter((s) =>
    s.toLowerCase().includes("connect")
  ).length;

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-black text-white">System Health</h3>
          <p className="text-sm text-slate-400 mt-1">
            Collected by the monitoring feature flags · uptime {formatUptime(health.uptime_seconds)}
          </p>
        </div>
        <button
          onClick={() => load(true)}
          className="flex items-center gap-2 bg-white/[0.03] px-5 py-3 rounded-2xl border border-white/5 hover:bg-white/[0.06] transition-all"
        >
          <RefreshCw className={cn("h-4 w-4 text-primary", refreshing && "animate-spin")} />
          <span className="text-xs font-black uppercase tracking-widest text-primary">Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card title="Shards" icon={Activity} tone={health.bot_ready ? "good" : "warn"}>
          {Object.keys(health.shard_latency).length === 0 ? (
            <p className="text-sm text-slate-500">Monitor disabled.</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(health.shard_latency).map(([id, latency]) => (
                <div key={id} className="flex justify-between text-sm">
                  <span className="text-slate-400">Shard {id}</span>
                  <span className={cn(
                    "font-bold",
                    latency < 200 ? "text-emerald-400" : latency < 500 ? "text-amber-400" : "text-red-400",
                  )}>
                    {latency} ms
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Lavalink" icon={Zap} tone={nodesConnected > 0 ? "good" : "warn"}>
          {Object.keys(health.lavalink_nodes).length === 0 ? (
            <p className="text-sm text-slate-500">No nodes reported.</p>
          ) : (
            <>
              <div className="space-y-2">
                {Object.entries(health.lavalink_nodes).map(([id, status]) => (
                  <div key={id} className="flex justify-between text-sm">
                    <span className="text-slate-400 truncate">{id}</span>
                    <span className="font-bold text-slate-200">{status}</span>
                  </div>
                ))}
              </div>
              <p className="text-[10px] uppercase tracking-widest text-slate-600 mt-3">
                Failover reconnects: {health.lavalink_reconnects}
              </p>
            </>
          )}
        </Card>

        <Card title="Discord API" icon={Activity} tone={health.discord_incidents.length ? "warn" : "good"}>
          <p className="text-sm text-slate-200 font-bold">{health.discord_status}</p>
          {health.discord_incidents.length > 0 && (
            <ul className="mt-3 space-y-1">
              {health.discord_incidents.map((incident) => (
                <li key={incident} className="text-xs text-amber-400">• {incident}</li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Database Integrity" icon={Database} tone={integrityIssues.length ? "warn" : "good"}>
          {Object.keys(health.integrity).length === 0 ? (
            <p className="text-sm text-slate-500">Scan disabled or not run yet.</p>
          ) : integrityIssues.length === 0 ? (
            <p className="text-sm text-emerald-400 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              All {Object.keys(health.integrity).length} databases OK
            </p>
          ) : (
            <ul className="space-y-1">
              {integrityIssues.slice(0, 6).map(([name, value]) => (
                <li key={name} className="text-xs text-amber-400">{name}: {value}</li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Backups & Cleanup" icon={HardDrive}>
          <p className="text-sm text-slate-300">
            Last backup:{" "}
            <span className="font-bold">
              {health.last_backup_at
                ? new Date(health.last_backup_at * 1000).toLocaleString()
                : "not run yet"}
            </span>
          </p>
          <p className="text-sm text-slate-300 mt-2">
            Orphan rows removed: <span className="font-bold">{health.last_cleanup_removed}</span>
          </p>
        </Card>

        <Card
          title="Modules"
          icon={FileWarning}
          tone={health.failed_extensions.length ? "warn" : "good"}
        >
          {health.failed_extensions.length === 0 ? (
            <p className="text-sm text-emerald-400 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> All modules loaded
            </p>
          ) : (
            <ul className="space-y-1">
              {health.failed_extensions.map((name) => (
                <li key={name} className="text-xs text-amber-400">✗ {name}</li>
              ))}
            </ul>
          )}
          {health.recovered_extensions.length > 0 && (
            <p className="text-[10px] uppercase tracking-widest text-emerald-500 mt-3">
              Recovered: {health.recovered_extensions.join(", ")}
            </p>
          )}
        </Card>
      </div>

      {health.session_warning && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-3xl p-5 flex gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
          <p className="text-sm text-amber-200">{health.session_warning}</p>
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden">
          <div className="p-6 border-b border-white/5 flex items-center gap-3">
            <ScrollText className="h-5 w-5 text-primary" />
            <h4 className="font-black text-white text-sm uppercase tracking-wider">
              Recent Warnings &amp; Errors
            </h4>
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-white/5">
            {logs.map((entry, index) => (
              <div key={index} className="px-6 py-3 flex gap-4 text-xs">
                <span className="text-slate-600 shrink-0 font-mono">{entry.time}</span>
                <span className={cn(
                  "font-black uppercase shrink-0 w-16",
                  entry.level === "ERROR" || entry.level === "CRITICAL"
                    ? "text-red-400"
                    : "text-amber-400",
                )}>
                  {entry.level}
                </span>
                <span className="text-slate-300 break-all">{entry.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
