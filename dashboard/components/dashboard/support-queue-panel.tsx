"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Headphones,
  Loader2,
  Mic,
  Music,
  Play,
  Save,
  Users,
  Volume2,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

interface VoiceChannel {
  id: string;
  name: string;
  category: string | null;
  user_limit: number;
  can_join: boolean;
  can_speak: boolean;
}

interface Waiting {
  user_id: string;
  name: string;
  avatar: string | null;
  since: number;
}

/** Wie lange jemand schon wartet. */
function waitedFor(since: number) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - since));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function SupportQueuePanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [enabled, setEnabled] = useState(false);
  const [channelId, setChannelId] = useState("");
  const [greeting, setGreeting] = useState("");
  const [seconds, setSeconds] = useState(30);
  const [musicUrl, setMusicUrl] = useState("");
  const [notifyId, setNotifyId] = useState("");
  const [roleId, setRoleId] = useState("");

  const load = useCallback(async () => {
    try {
      const answer = await api.supportQueue(guildId);
      setData(answer);
      setEnabled(Boolean(answer.enabled));
      setChannelId(answer.channel_id || "");
      setGreeting(answer.greeting || "");
      setSeconds(Number(answer.music_seconds) || 30);
      setMusicUrl(answer.music_url || "");
      setNotifyId(answer.notify_channel_id || "");
      setRoleId(answer.staff_role_id || "");
    } catch (err: any) {
      toast.error(err?.message || "Der Warteraum ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  // Die Warteliste im Blick behalten. Nur sie, nicht das ganze
  // Formular -- sonst überschreibt die Aktualisierung, was gerade
  // getippt wird.
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const answer = await api.supportQueue(guildId);
        setData((old: any) =>
          old ? { ...old, waiting: answer.waiting, audio: answer.audio } : answer
        );
      } catch {
        // Still bleiben: ein Aussetzer soll nicht die Seite volllaufen
        // lassen mit Fehlermeldungen.
      }
    }, 10000);
    return () => clearInterval(timer);
  }, [guildId]);

  const save = async () => {
    setBusy(true);
    try {
      const answer = await api.supportQueueSave(guildId, {
        enabled,
        channel_id: channelId,
        greeting,
        music_seconds: seconds,
        music_url: musicUrl,
        notify_channel_id: notifyId,
        staff_role_id: roleId,
      });
      setData((old: any) => ({ ...old, ...answer }));
      toast.success("Gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const answer = await api.supportQueueTest(guildId);
      toast.success(answer?.result || "Der Bot kommt gleich.");
    } catch (err: any) {
      toast.error(err?.message || "Der Test ist fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) return null;

  const channels: VoiceChannel[] = data.voice_channels ?? [];
  const chosen = channels.find((c) => c.id === channelId);
  const waiting: Waiting[] = data.waiting ?? [];
  const audioReady = Boolean(data.audio?.ready);
  const defaults = data.defaults ?? {};

  return (
    <section className="space-y-6">
      {/* Ohne Audio-Knoten bleibt der Bot stumm — das gehört nach oben,
          nicht in eine Fußnote. */}
      {!audioReady && (
        <div className="rounded-2xl bg-amber-500/[0.07] border border-amber-500/25 p-4 flex gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-sm font-bold text-amber-200">
              Kein Ton möglich
            </p>
            <p className="text-[12px] text-amber-200/75 mt-1 leading-relaxed">
              {data.audio?.detail}
            </p>
            <p className="text-[12px] text-amber-200/60 mt-2 leading-relaxed">
              Der Warteraum meldet dem Team trotzdem, wer wartet — nur Ansage
              und Musik fallen aus.
            </p>
          </div>
        </div>
      )}

      {/* Wer gerade wartet */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-4">
          <Users className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Wartet gerade
          </h3>
          <span className="ml-auto text-sm font-bold text-primary tabular-nums">
            {waiting.length}
          </span>
        </div>

        {waiting.length === 0 ? (
          <p className="text-sm text-slate-500">
            Im Moment wartet niemand.
          </p>
        ) : (
          <div className="space-y-2">
            {waiting.map((person) => (
              <div key={person.user_id} className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center text-[11px] font-black text-primary shrink-0">
                  {person.name.slice(0, 2).toUpperCase()}
                </div>
                <span className="text-sm text-slate-300 truncate">
                  {person.name}
                </span>
                <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-500 shrink-0">
                  <Clock className="h-3 w-3" />
                  {waitedFor(person.since)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Der Kanal */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-1">
          <Volume2 className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Warteraum
          </h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-4 leading-relaxed">
          Betritt jemand diesen Sprachkanal, kommt der Bot dazu, begrüßt ihn und
          spielt Wartemusik.
        </p>

        <select
          value={channelId}
          onChange={(event) => setChannelId(event.target.value)}
          className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white outline-none focus:border-primary/50 transition-colors"
        >
          <option value="">— kein Kanal gewählt —</option>
          {channels.map((channel) => (
            <option key={channel.id} value={channel.id} disabled={!channel.can_join}>
              {channel.category ? `${channel.category} / ` : ""}
              {channel.name}
              {!channel.can_join ? "  (Bot darf nicht rein)" : ""}
              {channel.can_join && !channel.can_speak ? "  (darf nicht sprechen)" : ""}
            </option>
          ))}
        </select>

        {chosen && !chosen.can_speak && (
          <p className="text-[12px] text-amber-300/80 mt-2.5 flex gap-2">
            <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            In diesem Kanal fehlt dem Bot „Sprechen“ — er käme herein, bliebe
            aber stumm.
          </p>
        )}

        {data.channel_missing && (
          <p className="text-[12px] text-red-300/80 mt-2.5 flex gap-2">
            <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            Der gespeicherte Kanal existiert nicht mehr.
          </p>
        )}

        <label className="flex items-center gap-3 mt-4 cursor-pointer">
          <button
            type="button"
            onClick={() => setEnabled(!enabled)}
            className={cn(
              "h-6 w-11 rounded-full transition-colors relative shrink-0",
              enabled ? "bg-primary" : "bg-slate-700"
            )}
          >
            <span
              className={cn(
                "absolute top-1 h-4 w-4 rounded-full bg-white transition-all",
                enabled ? "left-6" : "left-1"
              )}
            />
          </button>
          <span className="text-sm text-slate-300">Warteraum aktiv</span>
        </label>
      </div>

      {/* Die Ansage */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-1">
          <Mic className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Was der Bot sagt
          </h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-3 leading-relaxed">
          Wird vorgelesen, sobald jemand den Kanal betritt — und nach jeder
          Runde Musik erneut.
        </p>

        <textarea
          value={greeting}
          onChange={(event) => setGreeting(event.target.value)}
          rows={4}
          maxLength={defaults.max_greeting ?? 300}
          placeholder={defaults.greeting}
          className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-primary/50 transition-colors resize-none leading-relaxed"
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[11px] text-slate-600">
            Platzhalter: <code className="text-slate-500">{"{server}"}</code>
          </span>
          <span className="text-[11px] text-slate-600 tabular-nums">
            {greeting.length} / {defaults.max_greeting ?? 300}
          </span>
        </div>

        {!greeting && (
          <p className="text-[12px] text-slate-500 mt-3 leading-relaxed">
            Leer heißt: der voreingestellte Satz oben wird gesprochen.
          </p>
        )}
      </div>

      {/* Musik */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-1">
          <Music className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Wartemusik
          </h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-4 leading-relaxed">
          Läuft nach der Ansage. Danach beginnt alles von vorn.
        </p>

        <label className="text-[11px] font-black uppercase tracking-wider text-slate-500">
          Wie lange am Stück
        </label>
        <div className="flex items-center gap-3 mt-2">
          <input
            type="range"
            min={defaults.min_seconds ?? 10}
            max={180}
            step={5}
            value={seconds}
            onChange={(event) => setSeconds(Number(event.target.value))}
            className="flex-1 accent-blue-500"
          />
          <span className="text-sm font-bold text-white w-16 text-right tabular-nums shrink-0">
            {seconds} s
          </span>
        </div>

        <label className="text-[11px] font-black uppercase tracking-wider text-slate-500 block mt-5">
          Eigene Musik (optional)
        </label>
        <input
          value={musicUrl}
          onChange={(event) => setMusicUrl(event.target.value)}
          placeholder="Link oder Suchbegriff — leer = mitgelieferte Musik"
          className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-primary/50 transition-colors mt-2"
        />
      </div>

      {/* Benachrichtigung */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-1">
          <Headphones className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Team benachrichtigen
          </h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-4 leading-relaxed">
          Optional: eine Nachricht in einen Textkanal, sobald jemand wartet.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-500">
              Kanal
            </label>
            <select
              value={notifyId}
              onChange={(event) => setNotifyId(event.target.value)}
              className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white outline-none focus:border-primary/50 transition-colors mt-2"
            >
              <option value="">— keine Nachricht —</option>
              {(data.text_channels ?? []).map((channel: any) => (
                <option key={channel.id} value={channel.id}>
                  #{channel.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-500">
              Rolle pingen
            </label>
            <select
              value={roleId}
              onChange={(event) => setRoleId(event.target.value)}
              className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white outline-none focus:border-primary/50 transition-colors mt-2"
            >
              <option value="">— niemanden —</option>
              {(data.roles ?? []).map((role: any) => (
                <option key={role.id} value={role.id}>
                  @{role.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Speichern */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={save}
          disabled={busy}
          className="flex items-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-white text-sm font-bold px-5 py-2.5 rounded-xl transition-all"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Speichern
        </button>

        <button
          onClick={test}
          disabled={busy || !channelId || !audioReady}
          title={
            !audioReady
              ? "Ohne Audio-Knoten geht kein Test."
              : !channelId
              ? "Erst einen Kanal wählen."
              : ""
          }
          className="flex items-center gap-2 bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] disabled:opacity-40 text-slate-200 text-sm font-bold px-5 py-2.5 rounded-xl transition-all"
        >
          <Play className="h-4 w-4" />
          Einmal anhören
        </button>

        {data.enabled && data.channel_name && (
          <span className="flex items-center gap-2 text-[12px] text-emerald-300/80 ml-auto self-center">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Aktiv in {data.channel_name}
          </span>
        )}
      </div>
    </section>
  );
}
