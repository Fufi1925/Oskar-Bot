"use client";

import React, { useEffect, useState } from "react";
import { Check, ClipboardList, Loader2, RefreshCw, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface QueueEntry {
  id: number;
  created_at: number;
  requested_by: string;
  guild_id: string;
  action: string;
  payload: string;
  status: string;
}

function timeAgo(unix: number) {
  if (!unix) return "unknown";
  const s = Math.floor(Date.now() / 1000) - unix;
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/**
 * Queue of destructive actions waiting for a second admin to sign off.
 * Only visible while admin_action_approval_queue is switched on.
 */
export function ApprovalsPanel({ currentUserId }: { currentUserId?: string }) {
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [disabled, setDisabled] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getAdminApprovals(status);
      setEntries(data.entries || []);
      setDisabled(false);
    } catch (err: any) {
      if (String(err?.message || "").includes("disabled")) {
        setDisabled(true);
      } else {
        toast.error(err?.message || "Could not load the queue.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const resolve = async (entry: QueueEntry, approve: boolean) => {
    if (!currentUserId) return toast.error("Your session has no user id.");
    setBusy(entry.id);
    try {
      await api.resolveAdminApproval(entry.id, currentUserId, approve);
      toast.success(approve ? "Approved." : "Rejected.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not resolve this entry.");
    } finally {
      setBusy(null);
    }
  };

  if (disabled) {
    return (
      <div className="bg-white/[0.02] border border-white/5 rounded-3xl p-8 flex gap-4">
        <ClipboardList className="h-6 w-6 text-slate-500 shrink-0" />
        <div>
          <h4 className="font-black text-white">Approval queue is off</h4>
          <p className="text-sm text-slate-400 mt-1">
            Enable <code className="px-1.5 py-0.5 rounded bg-white/[0.05] font-mono text-xs">
              admin_action_approval_queue
            </code>{" "}
            in the Features tab. Destructive actions are then queued instead of running
            immediately. With <code className="px-1.5 py-0.5 rounded bg-white/[0.05] font-mono text-xs">
              two_person_rule
            </code>{" "}
            on top, a different admin has to sign them off.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <ClipboardList className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Approvals</h3>
              <p className="text-sm text-slate-400 mt-1">
                Destructive actions waiting for a decision.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex gap-1.5 p-1.5 bg-[#131318]/70 border border-slate-800 rounded-2xl">
              {(["pending", "approved", "rejected"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  className={cn(
                    "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                    status === s ? "bg-primary text-white" : "text-slate-400 hover:text-white"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
            <button
              onClick={load}
              className="p-3 rounded-2xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
            >
              <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
        </div>
      ) : entries.length === 0 ? (
        <p className="text-center text-slate-500 py-12">Nothing {status}.</p>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => {
            const ownRequest = entry.requested_by === currentUserId;
            let payload: any = {};
            try {
              payload = JSON.parse(entry.payload || "{}");
            } catch {
              /* ignore */
            }

            return (
              <div
                key={entry.id}
                className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card"
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="font-black text-white">{entry.action}</code>
                      <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-500">
                        #{entry.id}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-2">
                      requested by <span className="text-slate-400">{entry.requested_by}</span>
                      {" · "}server {entry.guild_id}
                      {" · "}{timeAgo(entry.created_at)}
                    </p>

                    {Object.keys(payload).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {Object.entries(payload)
                          .filter(([k]) => !["actor", "action", "guild_id"].includes(k))
                          .filter(([, v]) => v !== "" && v !== null && v !== undefined)
                          .map(([k, v]) => (
                            <span
                              key={k}
                              className="text-[10px] font-mono px-2 py-1 rounded-lg bg-white/[0.04] text-slate-400"
                            >
                              {k}: {String(v).slice(0, 40)}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>

                  {status === "pending" && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => resolve(entry, true)}
                        disabled={busy === entry.id || ownRequest}
                        title={ownRequest ? "You cannot approve your own request" : "Approve"}
                        className="p-3 rounded-xl bg-emerald-400/10 text-emerald-400 border border-emerald-400/20 hover:bg-emerald-400/20 transition-all disabled:opacity-30"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => resolve(entry, false)}
                        disabled={busy === entry.id}
                        className="p-3 rounded-xl bg-red-400/10 text-red-400 border border-red-400/20 hover:bg-red-400/20 transition-all disabled:opacity-30"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>

                {ownRequest && status === "pending" && (
                  <p className="text-[11px] text-amber-400/80 mt-3">
                    This is your own request — someone else has to approve it.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
