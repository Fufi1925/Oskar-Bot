"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle, Clock, FileText, Loader2, Megaphone, RefreshCw, ScrollText, Shield,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface AuditEntry {
  id: number;
  created_at: number;
  actor: string;
  guild_id: string;
  action: string;
  detail: string;
  suspicious: number;
}

function timeAgo(unix: number) {
  if (!unix) return "unknown";
  const seconds = Math.floor(Date.now() / 1000) - unix;
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function AuditPanel() {
  const [tab, setTab] = useState<"audit" | "timeline" | "broadcasts">("audit");
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [broadcasts, setBroadcasts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [suspiciousOnly, setSuspiciousOnly] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      if (tab === "audit") {
        const data = await api.getAdminAudit(150, suspiciousOnly);
        setEntries(data.entries || []);
      } else if (tab === "timeline") {
        const data = await api.getAdminTimeline(80);
        setTimeline(data.events || []);
      } else {
        const data = await api.getNotificationHistory(50);
        setBroadcasts(data.history || []);
      }
    } catch (err: any) {
      toast.error(err?.message || "Could not load the log.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, suspiciousOnly]);

  return (
    <section className="space-y-6">
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <ScrollText className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Audit Log</h3>
              <p className="text-sm text-slate-400 mt-1">
                Every action taken through the dashboard, across all servers.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex gap-1.5 p-1.5 bg-[#131318]/70 border border-slate-800 rounded-2xl">
              {([
                ["audit", "Actions", FileText],
                ["timeline", "Timeline", Clock],
                ["broadcasts", "Broadcasts", Megaphone],
              ] as const).map(([id, label, Icon]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={cn(
  "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all",
                    tab === id ? "bg-primary text-white" : "text-slate-400 hover:text-white"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={load}
              className="p-3 rounded-2xl bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.06] transition-all"
              title="Refresh"
            >
              <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
            </button>
          </div>
        </div>

        {tab === "audit" && (
          <label className="flex items-center gap-2 mt-6 cursor-pointer w-fit">
            <input
              type="checkbox"
              checked={suspiciousOnly}
              onChange={(e) => setSuspiciousOnly(e.target.checked)}
              className="accent-amber-400"
            />
            <span className="text-xs font-bold text-slate-400">
              Only show flagged actions
            </span>
          </label>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
        </div>
      ) : (
        <>
          {tab === "audit" && (
            <div className="bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden">
              {entries.length === 0 ? (
                <p className="text-sm text-slate-500 py-12 text-center">
                  No actions recorded yet.
                </p>
              ) : (
                <div className="divide-y divide-slate-800">
                  {entries.map((entry) => (
                    <div
                      key={entry.id}
                      className={cn(
  "px-6 py-4 flex items-start gap-4",
                        entry.suspicious && "bg-amber-400/[0.04]"
                      )}
                    >
                      <div
                        className={cn(
  "h-8 w-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5",
                          entry.suspicious ? "bg-amber-400/10" : "bg-white/[0.04]"
                        )}
                      >
                        {entry.suspicious ? (
                          <AlertTriangle className="h-4 w-4 text-amber-400" />
                        ) : (
                          <Shield className="h-4 w-4 text-slate-500" />
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <code className="text-xs font-black text-white font-mono">
                            {entry.action}
                          </code>
                          {entry.suspicious === 1 && (
                            <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20">
                              flagged
                            </span>
                          )}
                        </div>
                        {entry.detail && (
                          <p className="text-sm text-slate-400 mt-1 break-words">{entry.detail}</p>
                        )}
                        <p className="text-[11px] text-slate-600 mt-1.5">
                          by <span className="text-slate-500">{entry.actor}</span>
                          {entry.guild_id && <> · server {entry.guild_id}</>}
                        </p>
                      </div>

                      <span className="text-[11px] text-slate-600 shrink-0 whitespace-nowrap">
                        {timeAgo(entry.created_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "timeline" && (
            <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6">
              {timeline.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">No events yet.</p>
              ) : (
                <div className="relative pl-6 space-y-5">
                  <div className="absolute left-[7px] top-2 bottom-2 w-px bg-white/10" />
                  {timeline.map((event, index) => (
                    <div key={index} className="relative">
                      <div
                        className={cn(
  "absolute -left-[22px] top-1.5 h-3.5 w-3.5 rounded-full border-2 border-[#131318]",
                          event.severity === "warning" || event.severity === "error"
                            ? "bg-amber-400"
                            : event.severity === "critical"
                            ? "bg-red-400"
                            : "bg-primary"
                        )}
                      />
                      <p className="text-sm font-bold text-white">{event.summary}</p>
                      {event.detail && event.detail !== event.summary && (
                        <p className="text-xs text-slate-500 mt-1 break-words">{event.detail}</p>
                      )}
                      <p className="text-[11px] text-slate-600 mt-1">
                        {event.kind} · {timeAgo(event.timestamp)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "broadcasts" && (
            <div className="bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden">
              {broadcasts.length === 0 ? (
                <p className="text-sm text-slate-500 py-12 text-center">
                  No broadcasts sent yet.
                </p>
              ) : (
                <div className="divide-y divide-slate-800">
                  {broadcasts.map((item) => (
                    <div key={item.id} className="px-6 py-4 flex items-start gap-4">
                      <Megaphone className="h-4 w-4 text-primary shrink-0 mt-1" />
                      <p className="text-sm text-slate-300 flex-1 break-words">
                        {item.message || <span className="text-slate-600 italic">cleared</span>}
                      </p>
                      <span className="text-[11px] text-slate-600 shrink-0">
                        {timeAgo(item.created_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
