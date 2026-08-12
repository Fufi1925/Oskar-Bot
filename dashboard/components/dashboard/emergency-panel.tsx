"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface EmergencyState {
  active: boolean;
  locked_roles: Array<{ id: string; name: string }>;
  authorised_users: Array<{ id: string; name: string | null }>;
}

/**
 * Emergency lockdown: strips dangerous permissions from every role and
 * remembers exactly what was removed, so lifting it restores the previous
 * state instead of guessing.
 */
export function EmergencyPanel({ guildId }: { guildId: string }) {
  const [state, setState] = useState<EmergencyState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setState(await api.getEmergency(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Could not load the lockdown state.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const toggle = async (enable: boolean) => {
    setBusy(true);
    try {
      const res = await api.setEmergency(guildId, enable);
      toast.success(res.result);
      setConfirm(false);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not change the lockdown.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-7 w-7 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!state) return null;

  return (
    <section className="space-y-6">
      <div
        className={cn(
          "border rounded-3xl p-8",
          state.active
            ? "bg-red-500/10 border-red-500/30"
            : "bg-[#131318] border-slate-800"
        )}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            {state.active ? (
              <ShieldAlert className="h-8 w-8 text-red-400" />
            ) : (
              <ShieldCheck className="h-8 w-8 text-emerald-400" />
            )}
            <div>
              <h3 className="text-xl font-black text-white">
                {state.active ? "Lockdown is active" : "Normal operation"}
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                {state.active
                  ? `Dangerous permissions removed from ${state.locked_roles.length} roles.`
                  : "All roles have their normal permissions."}
              </p>
            </div>
          </div>

          <button
            onClick={() => load()}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        </div>
      </div>

      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-8 border-glow-card">
        <p className="text-sm text-slate-400 leading-relaxed mb-6">
          A lockdown removes Administrator, Ban, Kick, Manage Channels, Manage Roles,
          Manage Server, Manage Webhooks, Mention Everyone, Manage Messages and Timeout
          from every role the bot can edit. What was removed is stored, so lifting the
          lockdown puts everything back exactly as it was.
        </p>

        {state.active ? (
          <button
            onClick={() => toggle(false)}
            disabled={busy}
            className="w-full py-4 bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-emerald-500/25 disabled:opacity-50"
          >
            {busy ? "Restoring..." : "Lift lockdown and restore permissions"}
          </button>
        ) : confirm ? (
          <div className="space-y-4">
            <div className="flex gap-3 p-4 bg-red-500/10 border border-red-500/25 rounded-2xl">
              <AlertTriangle className="h-5 w-5 text-red-400 shrink-0" />
              <p className="text-sm text-red-200">
                Your moderators will lose their permissions until you lift this. Use it
                when the server is under attack.
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => toggle(true)}
                disabled={busy}
                className="flex-1 py-4 bg-red-500/15 text-red-400 border border-red-500/30 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-red-500/25 disabled:opacity-50"
              >
                {busy ? "Locking down..." : "Yes, lock the server down"}
              </button>
              <button
                onClick={() => setConfirm(false)}
                className="px-6 py-4 rounded-2xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-white transition-all text-xs font-black uppercase tracking-widest"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirm(true)}
            className="w-full py-4 rounded-2xl bg-white/[0.03] border border-red-500/20 text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition-all font-black uppercase tracking-widest text-xs"
          >
            Start emergency lockdown
          </button>
        )}
      </div>

      {state.locked_roles.length > 0 && (
        <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-3">
            Affected roles
          </p>
          <div className="flex flex-wrap gap-1.5">
            {state.locked_roles.map((role) => (
              <span
                key={role.id}
                className="text-[11px] font-bold px-2.5 py-1 rounded-lg bg-red-400/10 text-red-300 border border-red-400/20"
              >
                {role.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
