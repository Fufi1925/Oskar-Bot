"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Clock, Dices, ExternalLink, Gift, Loader2, PartyPopper, Plus, RefreshCw,
  Trash2, Trophy, Users, Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";

interface Giveaway {
  message_id: string;
  prize: string;
  title: string;
  description: string;
  button_label: string;
  winners: number;
  ends_at: number;
  running: boolean;
  entries: number;
  winner_ids: string[];
  channel: string | null;
  channel_id: string;
  url: string | null;
}

const DURATIONS = [
  { label: "10 Min", minutes: 10 },
  { label: "1 Std", minutes: 60 },
  { label: "6 Std", minutes: 360 },
  { label: "1 Tag", minutes: 1440 },
  { label: "3 Tage", minutes: 4320 },
  { label: "1 Woche", minutes: 10080 },
];

const PRESET_COLORS = ["#f59e0b", "#5865f2", "#2ecc71", "#e74c3c", "#9b59b6"];

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

/** Placeholders the user can drop into their own text. */
const TOKENS = [
  { token: "{prize}", hint: "Der Preis" },
  { token: "{winners}", hint: "Anzahl Gewinner" },
  { token: "{ends}", hint: "Endet in …" },
  { token: "{entries}", hint: "Teilnehmerzahl" },
  { token: "{host}", hint: "Wer es gestartet hat" },
];

function relativeTime(unix: number) {
  const diff = unix * 1000 - Date.now();
  const abs = Math.abs(diff);
  const m = 60_000, h = 60 * m, d = 24 * h;
  let text: string;
  if (abs < m) text = "unter 1 Min";
  else if (abs < h) text = `${Math.round(abs / m)} Min`;
  else if (abs < d) text = `${Math.round(abs / h)} Std`;
  else text = `${Math.round(abs / d)} Tg`;
  return diff > 0 ? `endet in ${text}` : `vor ${text} beendet`;
}

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600">{hint}</p>}
    </div>
  );
}

/**
 * Giveaways.
 *
 * Entries come from a button rather than a reaction, the whole message is
 * editable with placeholders, and finished giveaways can be redrawn — the
 * reroll skips whoever already won.
 */
export function GiveawaysPanel({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<Giveaway[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showText, setShowText] = useState(false);
  const [entrantsOf, setEntrantsOf] = useState<string | null>(null);
  const [entrants, setEntrants] = useState<any[]>([]);

  const [prize, setPrize] = useState("");
  const [channelId, setChannelId] = useState("");
  const [winners, setWinners] = useState(1);
  const [minutes, setMinutes] = useState(1440);
  const [customMinutes, setCustomMinutes] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [buttonLabel, setButtonLabel] = useState("");
  const [buttonEmoji, setButtonEmoji] = useState("");
  const [colour, setColour] = useState("#f59e0b");
  const [requiredRole, setRequiredRole] = useState("");
  const [dmWinners, setDmWinners] = useState(true);
  const [dmHost, setDmHost] = useState(true);

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

  useEffect(() => { load(); }, [load]);

  // Keep the countdowns moving without polling the API.
  useEffect(() => {
    const t = setInterval(() => setItems((i) => [...i]), 30_000);
    return () => clearInterval(t);
  }, []);

  const effectiveMinutes = customMinutes.trim()
    ? Math.max(1, Number(customMinutes) || 0)
    : minutes;
  const canCreate = Boolean(prize.trim()) && Boolean(channelId) && effectiveMinutes > 0;

  const act = async (fn: () => Promise<any>, fallback: string, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || fallback);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const create = () =>
    act(async () => {
      const res = await api.startGiveaway(guildId, {
        channel_id: channelId,
        prize: prize.trim(),
        winners,
        duration_minutes: effectiveMinutes,
        title: title.trim(),
        description: description.trim(),
        button_label: buttonLabel.trim(),
        button_emoji: buttonEmoji.trim(),
        colour: parseInt(colour.slice(1), 16),
        required_role_id: requiredRole || null,
        dm_winners: dmWinners,
        dm_host: dmHost,
      });
      setPrize("");
      setCustomMinutes("");
      return res;
    }, "Gewinnspiel gestartet.");

  const openEntrants = async (g: Giveaway) => {
    setEntrantsOf(g.message_id);
    try {
      const data = await api.getGiveawayEntries(guildId, g.message_id);
      setEntrants(data.entries || []);
    } catch {
      setEntrants([]);
    }
  };

  const previewText = useMemo(() => {
    const ends = new Date(Date.now() + effectiveMinutes * 60_000);
    const fill = (s: string) =>
      s
        .replace(/\{prize\}/g, prize || "…")
        .replace(/\{winners\}/g, String(winners))
        .replace(/\{ends\}/g, ends.toLocaleString("de-DE", {
          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        }))
        .replace(/\{entries\}/g, "0")
        .replace(/\{host\}/g, "@du");
    return {
      title: fill(title || "🎉 Gewinnspiel"),
      body: fill(
        description ||
          "**{prize}**\n\nDrücke den Knopf, um teilzunehmen.\n**Gewinner:** {winners}\n**Endet:** {ends}"
      ),
      button: buttonLabel || "Teilnehmen",
      emoji: buttonEmoji || "🎉",
    };
  }, [prize, winners, effectiveMinutes, title, description, buttonLabel, buttonEmoji]);

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
      {/* ── Entrant list ─────────────────────────────── */}
      {entrantsOf && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-md shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-white">
                Teilnehmer ({entrants.length})
              </h3>
              <button
                onClick={() => setEntrantsOf(null)}
                className="text-slate-500 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="p-5 max-h-[50vh] overflow-y-auto space-y-1.5">
              {entrants.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-6">
                  Noch niemand.
                </p>
              ) : (
                entrants.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center gap-2 text-sm text-slate-300"
                  >
                    <Users className="h-3.5 w-3.5 text-slate-600 shrink-0" />
                    <span className={cn("truncate", e.left && "text-slate-500 italic")}>
                      {e.name}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Create ───────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <h3 className="font-black text-white flex items-center gap-2">
            <Gift className="h-5 w-5 text-primary" />
            Neues Gewinnspiel
          </h3>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid lg:grid-cols-2 gap-5">
          <Field label="Preis">
            <input
              value={prize}
              onChange={(e) => setPrize(e.target.value)}
              placeholder="z. B. Discord Nitro"
              maxLength={200}
              className={INPUT}
            />
          </Field>

          <Field label="Kanal">
            <ChannelPicker
              guildId={guildId}
              value={channelId}
              onChange={(id) => setChannelId(id || "")}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>

          <Field label="Gewinner">
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
          </Field>

          <Field label="Laufzeit">
            <div className="flex gap-1.5 flex-wrap">
              {DURATIONS.map((d) => (
                <button
                  key={d.minutes}
                  onClick={() => { setMinutes(d.minutes); setCustomMinutes(""); }}
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
          </Field>
        </div>

        {/* Own text */}
        <button
          onClick={() => setShowText((v) => !v)}
          className="mt-6 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-primary transition-colors"
        >
          <Wand2 className="h-3.5 w-3.5" />
          {showText ? "Text ausblenden" : "Text & Aussehen anpassen"}
        </button>

        {showText && (
          <div className="mt-5 space-y-5 border-t border-slate-800 pt-5">
            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Überschrift" hint="Leer = 🎉 Gewinnspiel">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="🎉 Gewinnspiel"
                  className={INPUT}
                />
              </Field>

              <Field label="Knopf-Text" hint="Leer = Teilnehmen">
                <div className="flex gap-2">
                  <input
                    value={buttonEmoji}
                    onChange={(e) => setButtonEmoji(e.target.value)}
                    placeholder="🎉"
                    className="w-16 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                  />
                  <input
                    value={buttonLabel}
                    onChange={(e) => setButtonLabel(e.target.value)}
                    placeholder="Teilnehmen"
                    className={cn(INPUT, "flex-1")}
                  />
                </div>
              </Field>
            </div>

            <Field label="Beschreibung">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder="**{prize}**&#10;&#10;Drücke den Knopf, um teilzunehmen.&#10;**Gewinner:** {winners}&#10;**Endet:** {ends}"
                className={cn(INPUT, "resize-y font-mono text-[13px]")}
              />
              <div className="flex flex-wrap gap-1.5 pt-1">
                {TOKENS.map((t) => (
                  <button
                    key={t.token}
                    title={t.hint}
                    onClick={() => setDescription((d) => d + t.token)}
                    className="px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
                  >
                    {t.token}
                  </button>
                ))}
              </div>
            </Field>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Farbe">
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={colour}
                    onChange={(e) => setColour(e.target.value)}
                    className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1"
                  />
                  <div className="flex gap-1.5">
                    {PRESET_COLORS.map((hex) => (
                      <button
                        key={hex}
                        onClick={() => setColour(hex)}
                        style={{ background: hex }}
                        className="h-7 w-7 rounded-lg border border-white/20 hover:scale-110 transition-transform"
                      />
                    ))}
                  </div>
                </div>
              </Field>

              <Field label="Nur mit Rolle" hint="Leer = alle dürfen teilnehmen.">
                <RolePicker
                  guildId={guildId}
                  value={requiredRole}
                  onChange={(id) => setRequiredRole(id || "")}
                  placeholder="Keine Einschränkung"
                />
              </Field>
            </div>

            <div className="flex flex-wrap gap-5">
              {[
                { on: dmWinners, set: setDmWinners, label: "Gewinner per DM benachrichtigen" },
                { on: dmHost, set: setDmHost, label: "Mir eine Zusammenfassung schicken" },
              ].map((o) => (
                <label key={o.label} className="flex items-center gap-2.5 cursor-pointer">
                  <button
                    onClick={() => o.set(!o.on)}
                    role="switch"
                    aria-checked={o.on}
                    className={cn(
                      "relative h-6 w-11 rounded-full transition-colors",
                      o.on ? "bg-primary" : "bg-slate-700"
                    )}
                  >
                    <span className={cn(
                      "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
                      o.on ? "translate-x-6" : "translate-x-1"
                    )} />
                  </button>
                  <span className="text-sm text-slate-400">{o.label}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Preview */}
        {prize.trim() && (
          <div
            className="mt-6 rounded-2xl border-l-4 bg-[#0d1b31] p-5"
            style={{ borderLeftColor: colour }}
          >
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
              Vorschau
            </p>
            <p className="font-black text-white">{previewText.title}</p>
            <p className="text-slate-300 mt-2 text-sm whitespace-pre-line">
              {previewText.body}
            </p>
            <div className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold">
              <span>{previewText.emoji}</span>
              {previewText.button}
            </div>
          </div>
        )}

        <button
          onClick={create}
          disabled={busy || !canCreate}
          title={canCreate ? undefined : "Preis eingeben und Kanal wählen"}
          className="mt-6 w-full flex items-center justify-center gap-2 py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Gewinnspiel starten
        </button>
      </div>

      {/* ── Running ──────────────────────────────────── */}
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
                    <button
                      onClick={() => openEntrants(g)}
                      className="flex items-center gap-1 hover:text-primary transition-colors"
                    >
                      <Users className="h-3 w-3" />
                      {g.entries} Teilnehmer
                    </button>
                    <span className="flex items-center gap-1">
                      <Trophy className="h-3 w-3" />
                      {g.winners} Gewinner
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {relativeTime(g.ends_at)}
                    </span>
                    {g.channel && <span>#{g.channel}</span>}
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
                    onClick={() =>
                      act(
                        () => api.drawGiveaway(guildId, g.message_id),
                        "Ausgelost.",
                        `„${g.prize}" jetzt beenden und auslosen?`
                      )
                    }
                    disabled={busy}
                    className="px-4 py-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 hover:bg-amber-500/25 transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
                  >
                    Jetzt auslosen
                  </button>
                  <button
                    onClick={() =>
                      act(
                        () => api.cancelGiveaway(guildId, g.message_id),
                        "Abgebrochen.",
                        `„${g.prize}" abbrechen? Die Nachricht wird gelöscht.`
                      )
                    }
                    disabled={busy}
                    className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 transition-all disabled:opacity-40"
                    title="Abbrechen"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Finished ─────────────────────────────────── */}
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
                className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-3.5 flex items-center gap-4 flex-wrap"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-bold text-slate-300 truncate">{g.prize}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {g.winner_ids.length > 0
                      ? `${g.winner_ids.length} Gewinner · ${g.entries} Teilnehmer`
                      : "Keine Teilnehmer"}
                    {" · "}
                    {relativeTime(g.ends_at)}
                  </p>
                </div>

                <div className="flex gap-2 shrink-0">
                  {g.entries > 0 && (
                    <button
                      onClick={() =>
                        act(
                          () => api.rerollGiveaway(guildId, g.message_id, 1),
                          "Neu ausgelost.",
                          "Neu auslosen? Bisherige Gewinner werden übersprungen."
                        )
                      }
                      disabled={busy}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:text-primary transition-all text-[11px] font-black uppercase tracking-widest disabled:opacity-40"
                    >
                      <Dices className="h-3.5 w-3.5" />
                      Neu auslosen
                    </button>
                  )}
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
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
