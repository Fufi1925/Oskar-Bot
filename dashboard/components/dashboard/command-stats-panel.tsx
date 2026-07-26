"use client";

import React, { useEffect, useState } from "react";
import { Activity, AlertTriangle, Loader2, RefreshCw, Terminal, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CommandEntry {
  command: string;
  uses: number;
  failures: number;
  failure_rate: number;
}

interface StatsPayload {
  days: number;
  total_uses: number;
  total_failures: number;
  unique_commands: number;
  registered_commands: number;
  commands: CommandEntry[];
  daily: Array<{ day: string; uses: number }>;
  guilds: Array<{ guild_id: string; guild_name: string | null; uses: number }>;
  unused: string[];
}

/**
 * Which commands people actually use.
 *
 * The bot has 235 commands and previously no idea which ones matter — this
 * shows usage, failure rates and the ones nobody has ever run.
 */
export function CommandStatsPanel() {
  const [data, setData] = useState<StatsPayload | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [showUnused, setShowUnused] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.getCommandStats(days));
    } catch (err: any) {
      toast.error(err?.message || "Could not load the statistics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) return null;

  const maxUses = Math.max(...data.commands.map((c) => c.uses), 1);
  const maxDaily = Math.max(...data.daily.map((d) => d.uses), 1);

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Terminal className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Command usage</h3>
              <p className="text-sm text-slate-400 mt-1">
                {data.total_uses.toLocaleString()} calls · {data.unique_commands} of{" "}
                {data.registered_commands} commands used
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex gap-1.5 p-1.5 bg-[#10233f]/70 border border-slate-800 rounded-2xl">
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={cn(
                    "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                    days === d ? "bg-primary text-white" : "text-slate-400 hover:text-white"
                  )}
                >
                  {d}d
                </button>
              ))}
            </div>
            <button
              onClick={load}
              className="p-3 rounded-2xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
            >
              <RefreshCw className="h-4 w-4 text-primary" />
            </button>
          </div>
        </div>
      </div>

      {data.total_uses === 0 ? (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-12 text-center">
          <Activity className="h-10 w-10 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-400">No commands recorded in the last {days} days.</p>
          <p className="text-xs text-slate-600 mt-2">
            Counting started when this feature was deployed, so older usage is not
            included.
          </p>
        </div>
      ) : (
        <>
          {data.daily.length > 1 && (
            <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-4">
                Per day
              </p>
              <div className="flex items-end gap-1 h-28">
                {data.daily.map((d) => (
                  <div
                    key={d.day}
                    className="flex-1 bg-primary/60 hover:bg-primary rounded-t transition-colors min-w-[3px]"
                    style={{ height: `${Math.max((d.uses / maxDaily) * 100, 3)}%` }}
                    title={`${d.day}: ${d.uses}`}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 flex items-center gap-3">
              <TrendingUp className="h-5 w-5 text-primary" />
              <h4 className="font-black text-white text-sm uppercase tracking-wider">
                Most used
              </h4>
            </div>
            <div className="divide-y divide-white/5 max-h-[28rem] overflow-y-auto">
              {data.commands.slice(0, 40).map((cmd) => (
                <div key={cmd.command} className="px-6 py-3 flex items-center gap-4">
                  <code className="text-sm font-mono text-white w-40 truncate shrink-0">
                    {cmd.command}
                  </code>
                  <div className="flex-1 h-5 bg-slate-800/60 rounded-lg overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-lg"
                      style={{ width: `${(cmd.uses / maxUses) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold text-white w-14 text-right shrink-0">
                    {cmd.uses}
                  </span>
                  {cmd.failures > 0 && (
                    <span
                      className={cn(
                        "text-[10px] font-black w-14 text-right shrink-0",
                        cmd.failure_rate > 25 ? "text-red-400" : "text-amber-400"
                      )}
                      title={`${cmd.failures} failures`}
                    >
                      {cmd.failure_rate}%
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {data.guilds.length > 1 && (
            <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-4">
                Busiest servers
              </p>
              <div className="space-y-2">
                {data.guilds.slice(0, 8).map((g) => (
                  <div key={g.guild_id} className="flex items-center justify-between gap-4">
                    <span className="text-sm text-slate-300 truncate">
                      {g.guild_name || g.guild_id}
                    </span>
                    <span className="text-sm font-bold text-primary shrink-0">{g.uses}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {data.unused.length > 0 && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6">
          <button
            onClick={() => setShowUnused(!showUnused)}
            className="flex items-center gap-3 w-full text-left"
          >
            <AlertTriangle className="h-5 w-5 text-slate-600" />
            <div className="flex-1">
              <p className="font-black text-white text-sm">
                {data.unused.length} commands never used
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                Candidates for removal or better documentation
              </p>
            </div>
            <span className="text-xs font-black uppercase tracking-widest text-slate-600">
              {showUnused ? "Hide" : "Show"}
            </span>
          </button>

          {showUnused && (
            <div className="flex flex-wrap gap-1.5 mt-4">
              {data.unused.map((c) => (
                <code
                  key={c}
                  className="text-[10px] font-mono px-2 py-1 rounded-lg bg-white/[0.04] text-slate-500"
                >
                  {c}
                </code>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
