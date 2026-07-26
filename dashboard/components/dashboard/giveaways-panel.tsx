"use client";

import React, { useEffect, useState } from "react";
import {
  Clock, ExternalLink, Gift, Loader2, Plus, RefreshCw, Trophy, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Giveaway {
  message_id: string;
  prize: string;
  winners: number;
  ends_at: number;
  running: boolean;
  channel: string | null;
  url: string | null;
  host: string | null;
}

const SELECT_CLASS =
  "appearance-none bg-[#0b1f3a] border border-white/10 rounded-2xl px-4 py-3 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer";

const INPUT_CLASS =
  "w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary";

function timeLeft(unix: number) {
  const seconds = Math.floor(unix - Date.now() / 1000);
  if (seconds <= 0) return "ended";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h left`;
  if (h) return `${h}h ${m}m left`;
  return `${m}m left`;
}

export function GiveawaysPanel({
  guildId,
  channels,
}: {
  guildId: string;
  channels: Array<{ id: string; name: string }>;
}) {
  const [items, setItems] = useState<Giveaway[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [channelId, setChannelId] = useState("");
  const [prize, setPrize] = useState("");
  const [winners, setWinners] = useState("1");
  const [duration, setDuration] = useState("60");

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getGiveaways(guildId);
      setItems(data.giveaways || []);
    } catch (err: any) {
      toast.error(err?.message || "Could not load giveaways.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const create = async () => {
    if (!channelId) return toast.error("Pick a channel.");
    if (!prize.trim()) return toast.error("Enter what is being given away.");
    setBusy(true);
    try {
      const res = await api.createGiveaway(guildId, {
        channel_id: channelId,
        prize: prize.trim(),
        winners: Number(winners) || 1,
        duration_minutes: Number(duration) || 60,
      });
      toast.success(res.result);
      setPrize("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not start the giveaway.");
    } finally {
      setBusy(false);
    }
  };

  const endNow = async (id: string) => {
    setBusy(true);
    try {
      const res = await api.endGiveaway(guildId, id);
      toast.success(res.result);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not end the giveaway.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (id: string) => {
    setBusy(true);
    try {
      await api.cancelGiveaway(guildId, id);
      toast.success("Giveaway cancelled.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not cancel.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <h3 className="font-black text-white flex items-center gap-2">
            <Plus className="h-5 w-5 text-primary" /> Start a giveaway
          </h3>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Prize
            </span>
            <input
              value={prize}
              onChange={(e) => setPrize(e.target.value)}
              placeholder="Discord Nitro"
              className={INPUT_CLASS}
            />
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Channel
            </span>
            <select
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
              className={cn(SELECT_CLASS, "w-full")}
            >
              <option value="">Select a channel...</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Winners
            </span>
            <input
              type="number"
              min={1}
              max={20}
              value={winners}
              onChange={(e) => setWinners(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Duration in minutes
            </span>
            <input
              type="number"
              min={1}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className={INPUT_CLASS}
            />
          </label>
        </div>

        <button
          onClick={create}
          disabled={busy}
          className="mt-6 w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "Working..." : "Start giveaway"}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-7 w-7 text-primary animate-spin opacity-40" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-center text-slate-500 py-12">No giveaways yet.</p>
      ) : (
        <div className="space-y-3">
          {items.map((g) => (
            <div
              key={g.message_id}
              className={cn(
                "bg-[#10233f] border rounded-3xl p-6 flex items-center justify-between gap-4 flex-wrap",
                g.running ? "border-amber-400/25" : "border-slate-800"
              )}
            >
              <div className="flex items-center gap-4 min-w-0">
                <Gift className={cn("h-6 w-6 shrink-0", g.running ? "text-amber-400" : "text-slate-600")} />
                <div className="min-w-0">
                  <p className="font-black text-white truncate">{g.prize}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {g.winners} winner{g.winners === 1 ? "" : "s"}
                    {g.channel && <> · #{g.channel}</>}
                    {" · "}
                    <span className={g.running ? "text-amber-400" : ""}>
                      {timeLeft(g.ends_at)}
                    </span>
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {g.url && (
                  <a
                    href={g.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary transition-all"
                    title="Open in Discord"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
                {g.running && (
                  <button
                    onClick={() => endNow(g.message_id)}
                    disabled={busy}
                    className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-400/10 text-emerald-400 border border-emerald-400/20 hover:bg-emerald-400/20 transition-all text-xs font-black uppercase tracking-widest disabled:opacity-40"
                  >
                    <Trophy className="h-3.5 w-3.5" />
                    Draw now
                  </button>
                )}
                <button
                  onClick={() => cancel(g.message_id)}
                  disabled={busy}
                  className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                  title="Cancel"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
