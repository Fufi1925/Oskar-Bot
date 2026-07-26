"use client";

import React, { useEffect, useState } from "react";
import { AlertCircle, Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { UserPicker } from "@/components/dashboard/user-picker";

interface WarnEntry {
  id: number;
  moderator_id: string;
  moderator: string | null;
  reason: string;
  created_at: number;
}

interface WarnUser {
  user_id: string;
  username: string | null;
  count: number;
  entries: WarnEntry[];
}

function timeAgo(unix: number) {
  if (!unix) return "";
  const s = Math.floor(Date.now() / 1000) - unix;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function WarningsPanel({ guildId }: { guildId: string }) {
  const [users, setUsers] = useState<WarnUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const [targetId, setTargetId] = useState("");
  const [reason, setReason] = useState("");

  const load = async () => {
    if (!guildId) return;
    setLoading(true);
    try {
      const data = await api.getWarnings(guildId);
      setUsers(data.users || []);
      setTotal(data.total || 0);
    } catch (err: any) {
      toast.error(err?.message || "Could not load warnings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const addWarning = async () => {
    if (!targetId) return toast.error("Pick a member first.");
    if (!reason.trim()) return toast.error("A reason is required.");
    setBusy(true);
    try {
      await api.addWarning(guildId, targetId, reason.trim());
      toast.success("Warning added.");
      setTargetId("");
      setReason("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not add the warning.");
    } finally {
      setBusy(false);
    }
  };

  const removeEntry = async (entryId: number) => {
    setBusy(true);
    try {
      await api.removeWarning(guildId, entryId);
      toast.success("Warning removed.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not remove.");
    } finally {
      setBusy(false);
    }
  };

  const clearUser = async (userId: string) => {
    setBusy(true);
    try {
      await api.clearWarnings(guildId, userId);
      toast.success("All warnings cleared.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not clear.");
    } finally {
      setBusy(false);
    }
  };

  if (!guildId) {
    return <p className="text-center text-slate-500 py-12">Select a server first.</p>;
  }

  return (
    <section className="space-y-6">
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <h4 className="font-black text-white flex items-center gap-2">
            <Plus className="h-5 w-5 text-primary" /> Warn a member
          </h4>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <UserPicker guildId={guildId} value={targetId} onChange={setTargetId} label="Member" />
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Reason
            </span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="What happened?"
              className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>

        <button
          onClick={addWarning}
          disabled={busy}
          className="mt-6 w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "Working..." : "Add warning"}
        </button>

        <p className="text-[11px] text-slate-600 mt-3">
          The member is notified by DM when possible, and the counter stays in sync with
          the bot&apos;s own warn command.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-7 w-7 text-primary animate-spin opacity-40" />
        </div>
      ) : users.length === 0 ? (
        <p className="text-center text-slate-500 py-12">No warnings in this server.</p>
      ) : (
        <>
          <p className="text-xs font-black uppercase tracking-widest text-slate-600">
            {users.length} members · {total} warnings
          </p>

          <div className="space-y-3">
            {users.map((user) => (
              <div key={user.user_id} className="bg-[#10233f] border border-slate-800 rounded-3xl p-6">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <p className="font-black text-white truncate">
                      {user.username || "Unknown member"}
                    </p>
                    <code className="text-[11px] text-slate-500 font-mono">{user.user_id}</code>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <span
                      className={cn(
                        "flex items-center gap-1.5 text-sm font-black px-3 py-1.5 rounded-xl border",
                        user.count >= 3
                          ? "text-red-400 bg-red-400/10 border-red-400/20"
                          : "text-amber-400 bg-amber-400/10 border-amber-400/20"
                      )}
                    >
                      <AlertCircle className="h-3.5 w-3.5" />
                      {user.count}
                    </span>
                    <button
                      onClick={() => clearUser(user.user_id)}
                      disabled={busy}
                      className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                      title="Clear all warnings"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {user.entries.length > 0 && (
                  <>
                    <button
                      onClick={() =>
                        setExpanded(expanded === user.user_id ? null : user.user_id)
                      }
                      className="mt-4 text-xs font-bold text-slate-500 hover:text-white transition-colors"
                    >
                      {expanded === user.user_id
                        ? "Hide history"
                        : `Show ${user.entries.length} entries`}
                    </button>

                    {expanded === user.user_id && (
                      <div className="mt-3 space-y-2">
                        {user.entries.map((entry) => (
                          <div
                            key={entry.id}
                            className="flex items-start justify-between gap-3 p-3 bg-white/[0.02] border border-white/5 rounded-2xl"
                          >
                            <div className="min-w-0">
                              <p className="text-sm text-slate-300 break-words">{entry.reason}</p>
                              <p className="text-[11px] text-slate-600 mt-1">
                                by {entry.moderator || entry.moderator_id || "unknown"} ·{" "}
                                {timeAgo(entry.created_at)}
                              </p>
                            </div>
                            <button
                              onClick={() => removeEntry(entry.id)}
                              disabled={busy}
                              className="text-slate-600 hover:text-red-400 transition-colors shrink-0"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}

                {user.entries.length === 0 && user.count > 0 && (
                  <p className="text-[11px] text-slate-600 mt-3">
                    Counter only — these predate the detailed log.
                  </p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
