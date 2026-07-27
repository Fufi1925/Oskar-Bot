"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Clock, ExternalLink, Gift, Loader2, PartyPopper, Plus, RefreshCw, Trophy, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker } from "@/components/dashboard/pickers";

interface Giveaway {
  message_id: string;
  prize: string;
  winners: number;
  ends_at: number;
  running: boolean;
  channel: string | null;
  channel_id: string;
  host: string | null;
  url: string | null;
}

/** Presets instead of "duration in minutes" — nobody wants to work out 10080. */
const DURATIONS = [
  { label: "10 Min", minutes: 10 },
  { label: "1 Std", minutes: 60 },
  { label: "6 Std", minutes: 360 },
  { label: "12 Std", minutes: 720 },
  { label: "1 Tag", minutes: 1440 },
  { label: "3 Tage", minutes: 4320 },
  { label: "1 Woche", minutes: 10080 },
];

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

/** "in 2 Tagen" / "vor 5 Min" — a raw timestamp says nothing at a glance. */
function relativeTime(unix: number) {
  const diff = unix * 1000 - Date.now();
  const abs = Math.abs(diff);
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  let text: string;
  if (abs < minute) text = "weniger als 1 Min";
  else if (abs < hour) text = `${Math.round(abs / minute)} Min`;
  else if (abs < day) text = `${Math.round(abs / hour)} Std`;
  else text = `${Math.round(abs / day)} Tg`;

  return diff > 0 ? `endet in ${text}` : `vor ${text} beendet`;
}

function endsAtLabel(unix: number) {
  if (!unix) return "";
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Giveaways.
 *
 * The previous version asked for a duration in minutes, listed everything
 * in one undifferentiated pile and was the last tab still using a plain
 * channel dropdown fed by a prop. This one uses duration presets, splits
 * running from finished, and shows what the message will look like before
 * it is posted.
 */
export function GiveawaysPanel({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<Giveaway[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [prize, setPrize] = useState("");
  const [channelId, setChannelId] = useState("");
  const [winners, setWinners] = useState(1);
  const [minutes, setMinutes] = useState(1440);
  const [customMinutes, setCustomMinutes] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.getGiveaways(guildId);
      setItems(data.giveaways || []);
    } catch (err: any) {
      toast.error(err?.message || "Gewinnspiele konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  // Keep the countdowns honest without hammering the API.
  useEffect(() => {
    const timer = setInterval(() => setItems((i) => [...i]), 30_000);
    return () => clearInterval(timer);
  }, []);

  const effectiveMinutes = customMinutes.trim()
    ? Math.max(1, Number(customMinutes) || 0)
    : minutes;

  const canCreate = Boolean(prize.trim()) && Boolean(channelId) && effectiveMinutes > 0;

  const create = async () => {
    if (!canCreate) return;
    setBusy(true);
    try {
      const result = await api.createGiveaway(guildId, {
        channel_id: channelId,
        prize: prize.trim(),
        winners,
        duration_minutes: effectiveMinutes,
      });
      toast.success(result?.result || "Gewinnspiel gestartet.");
      setPrize("");
      setCustomMinutes("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht gestartet werden.");
    } finally {
      setBusy(false);
    }
  };

  const end = async (giveaway: Giveaway) => {
    if (!confirm(`Gewinnspiel „${giveaway.prize}" jetzt beenden und auslosen?`)) return;
    setBusy(true);
    try {
      const result = await api.endGiveaway(guildId, giveaway.message_id);
      toast.success(result?.result || "Beendet.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht beendet werden.");
    } finally {
      setBusy(false);
    }
  };

  const running = useMemo(() => items.filter((g) => g.running), [items]);
  const finished = useMemo(() => items.filter((g) => !g.running), [items]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {/* ── Create ──────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <h3 className="font-black text-white flex items-center gap-2">
            <Gift className="h-5 w-5 text-primary" />
            Neues Gewinnspiel
          </h3>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
            title="Neu laden"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid lg:grid-cols-2 gap-5">
          <div className="space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Preis
            </span>
            <input
              value={prize}
              onChange={(e) => setPrize(e.target.value)}
              placeholder="z. B. Discord Nitro"
              maxLength={200}
              className={INPUT}
            />
          </div>

          <div className="space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Kanal
            </span>
            <ChannelPicker
              guildId={guildId}
              value={channelId}
              onChange={(id) => setChannelId(id || "")}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </div>

          <div className="space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Gewinner
            </span>
            <div className="flex gap-1.5 flex-wrap">
              {[1, 2, 3, 5, 10].map((n) => (
                <button
                  key={n}
                  onClick={() => setWinners(n)}
                  className={cn(
                    "h-11 w-11 rounded-xl text-sm font-bold border transition-all",
                    winners === n
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                  )}
                >
                  {n}
                </button>
              ))}
              <input
                type="number"
                min={1}
                max={20}
                value={winners}
                onChange={(e) =>
                  setWinners(Math.max(1, Math.min(20, Number(e.target.value) || 1)))
                }
                className="h-11 w-20 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
              />
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Laufzeit
            </span>
            <div className="flex gap-1.5 flex-wrap">
              {DURATIONS.map((d) => (
                <button
                  key={d.minutes}
                  onClick={() => {
                    setMinutes(d.minutes);
                    setCustomMinutes("");
                  }}
                  className={cn(
                    "px-3 h-11 rounded-xl text-xs font-bold border transition-all",
                    !customMinutes && minutes === d.minutes
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                  )}
                >
                  {d.label}
                </button>
              ))}
              <input
                type="number"
                min={1}
                value={customMinutes}
                onChange={(e) => setCustomMinutes(e.target.value)}
                placeholder="Min"
                className="h-11 w-20 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
              />
            </div>
          </div>
        </div>

        {/* What the message will look like. */}
        {prize.trim() && (
          <div className="mt-6 rounded-2xl border-l-4 border-amber-500 bg-[#0d1b31] p-5">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
              Vorschau
            </p>
            <p className="font-black text-white">🎉 Giveaway</p>
            <p className="text-slate-300 mt-1">{prize.trim()}</p>
            <p className="text-sm text-slate-400 mt-2">
              Mit 🎉 reagieren zum Teilnehmen.
              <br />
              <span className="font-bold">Gewinner:</span> {winners}
              <br />
              <span className="font-bold">Endet:</span>{" "}
              {endsAtLabel(Date.now() / 1000 + effectiveMinutes * 60)}
            </p>
          </div>
        )}

        <button
          onClick={create}
          disabled={busy || !canCreate}
          title={
            canCreate
              ? undefined
              : "Preis eingeben und einen Kanal wählen"
          }
          className="mt-6 w-full flex items-center justify-center gap-2 py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Gewinnspiel starten
        </button>
      </div>

      {/* ── Running ─────────────────────────────────────── */}
      <div>
        <h3 className="font-black text-white flex items-center gap-2 mb-3">
          <PartyPopper className="h-5 w-5 text-emerald-400" />
          Laufend
          <span className="text-xs font-normal text-slate-500">({running.length})</span>
        </h3>

        {running.length === 0 ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
            Gerade läuft kein Gewinnspiel.
          </p>
        ) : (
          <div className="space-y-3">
            {running.map((g) => (
              <div
                key={g.message_id}
                className="bg-[#10233f] border border-emerald-500/20 rounded-2xl p-5 flex items-center gap-4 flex-wrap"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-black text-white truncate">{g.prize}</p>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Trophy className="h-3 w-3" />
                      {g.winners} Gewinner
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {relativeTime(g.ends_at)}
                    </span>
                    {g.channel && <span>#{g.channel}</span>}
                    {g.host && (
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {g.host}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex gap-2 shrink-0">
                  {g.url && (
                    <a
                      href={g.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary transition-all"
                      title="In Discord öffnen"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                  <button
                    onClick={() => end(g)}
                    disabled={busy}
                    className="px-4 py-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 hover:bg-amber-500/25 transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
                  >
                    Jetzt auslosen
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Finished ────────────────────────────────────── */}
      {finished.length > 0 && (
        <div>
          <h3 className="font-black text-white flex items-center gap-2 mb-3">
            Beendet
            <span className="text-xs font-normal text-slate-500">({finished.length})</span>
          </h3>
          <div className="space-y-2">
            {finished.map((g) => (
              <div
                key={g.message_id}
                className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-3.5 flex items-center gap-4 flex-wrap opacity-70"
              >
                <p className="font-bold text-slate-300 truncate flex-1 min-w-0">{g.prize}</p>
                <span className="text-xs text-slate-500">
                  {g.winners} Gewinner · {relativeTime(g.ends_at)}
                </span>
                {g.url && (
                  <a
                    href={g.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 rounded-lg text-slate-500 hover:text-primary transition-all"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
