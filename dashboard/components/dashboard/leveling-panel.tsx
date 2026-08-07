"use client";

/**
 * The leveling system.
 *
 * The old form had five fields — on/off, XP per message, cooldown,
 * channel and a colour — and everything else (reward roles, multipliers,
 * excluded channels, the level-up text, the member list) could only be
 * managed with chat commands. It also disabled every input when the
 * system was off, so a server owner could not prepare a setup before
 * switching it on.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Award, BarChart4, ChevronRight, Eye, Gauge, Loader2, Medal, MessageSquare,
  Pencil, Plus, RefreshCw, Save, Search, Send, Settings2, Sparkles, Timer,
  Trash2, TrendingUp, Users, Wand2, X, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { EmojiPicker } from "@/components/dashboard/emoji-picker";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

/** Sample values for the live preview of the level-up text. */
const SAMPLE: Record<string, string> = {
  "{user}": "@Alex",
  "{user_name}": "alex",
  "{user_nick}": "Alex",
  "{level}": "5",
  "{xp}": "2.500",
  "{rank}": "3",
  "{messages}": "412",
  "{server}": "dein Server",
  "{next_level}": "6",
  "{next_xp}": "1.100",
};

/** Presets for the auto-delete seconds, so nobody has to guess. */
const DELETE_PRESETS = [
  { label: "Aus", value: 0 },
  { label: "10s", value: 10 },
  { label: "30s", value: 30 },
  { label: "1 Min", value: 60 },
  { label: "5 Min", value: 300 },
];

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

function Stat({ icon: Icon, label, value }: any) {
  return (
    <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl p-4">
      <Icon className="h-4 w-4 text-primary mb-2" />
      <p className="text-lg font-black text-white">{value}</p>
      <p className="text-[11px] text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

function num(value: any) {
  return Number(value || 0).toLocaleString("de-DE");
}

export function LevelingPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] =
    useState<"settings" | "rewards" | "members" | "tuning" | "curve">("settings");
  const [draft, setDraft] = useState<Record<string, any>>({});

  const load = useCallback(async () => {
    try {
      const fresh = await api.getLeveling(guildId);
      setData(fresh);
      setDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  const value = (key: string) => (key in draft ? draft[key] : data?.[key]);
  const set = (key: string, v: any) => setDraft((d) => ({ ...d, [key]: v }));
  const dirtyCount = Object.keys(draft).length;
  // Refuses to leave the tab while something is unsaved.
  const guard = useSaveGuard(dirtyCount, "leveling-save-bar");

  const save = async (extra: Record<string, any> = {}) => {
    const payload = { ...draft, ...extra };
    if (!Object.keys(payload).length) return;
    setBusy(true);
    try {
      const res = await api.updateLeveling(guildId, payload);
      toast.success(res?.result || "Gespeichert.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  /** Run an action, then reload. */
  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  // Both read through `value()`, which is derived from draft+data; listing
  // those two directly keeps the dependency list honest.
  const preview = useMemo(() => {
    const raw = "level_message" in draft ? draft.level_message : data?.level_message;
    let text = String(raw ?? "");
    for (const [token, sample] of Object.entries(SAMPLE)) {
      text = text.split(token).join(sample);
    }
    return text;
  }, [draft, data]);

  const colourHex = useMemo(() => {
    const raw = "embed_color" in draft ? draft.embed_color : data?.embed_color;
    if (typeof raw === "number") return `#${raw.toString(16).padStart(6, "0")}`;
    return data?.embed_color_hex || "#5865f2";
  }, [draft, data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) {
    return (
      <p className="text-sm text-slate-400 text-center py-16">
        Das Level-System konnte nicht geladen werden.
      </p>
    );
  }

  return (
    <section className="space-y-6">
      {/* ── Master switch + stats ────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className={cn(
              "h-11 w-11 rounded-2xl grid place-items-center shrink-0",
              value("enabled") ? "bg-emerald-500/15" : "bg-slate-700/40"
            )}>
              <BarChart4 className={cn(
                "h-5 w-5",
                value("enabled") ? "text-emerald-400" : "text-slate-500"
              )} />
            </div>
            <div>
              <p className="font-black text-white">
                {value("enabled") ? "Läuft" : "Ausgeschaltet"}
              </p>
              <p className="text-[11px] text-slate-500">
                {value("enabled")
                  ? "Mitglieder sammeln XP fürs Schreiben."
                  : "Es wird gerade kein XP vergeben."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={load}
              className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
              title="Neu laden"
            >
              <RefreshCw className="h-4 w-4 text-primary" />
            </button>
            <button
              onClick={() => save({ enabled: !value("enabled") })}
              disabled={busy}
              className={cn(
                "px-5 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all disabled:opacity-40",
                value("enabled")
                  ? "bg-white/[0.03] border border-white/10 text-slate-300 hover:text-red-400"
                  : "bg-primary shadow-lg shadow-primary/20 hover:brightness-110"
              )}
            >
              {value("enabled") ? "Ausschalten" : "Einschalten"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat icon={Users} label="Mitglieder mit XP" value={num(data.stats?.members)} />
          <Stat icon={Zap} label="XP insgesamt" value={num(data.stats?.total_xp)} />
          <Stat icon={MessageSquare} label="Nachrichten" value={num(data.stats?.messages)} />
          <Stat icon={TrendingUp} label="Höchstes Level" value={data.stats?.top_level ?? 0} />
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────── */}
      <div className="flex gap-1.5 flex-wrap">
        {[
          { id: "settings", label: "Einstellungen", icon: Settings2 },
          { id: "rewards", label: "Belohnungen", icon: Award },
          { id: "tuning", label: "Multiplikatoren", icon: Gauge },
          { id: "members", label: "Mitglieder", icon: Medal },
          { id: "curve", label: "XP-Tabelle", icon: TrendingUp },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={cn(
              "flex items-center gap-2 px-4 h-11 rounded-xl text-xs font-black uppercase tracking-widest border transition-all",
              tab === t.id
                ? "bg-primary/15 border-primary/40 text-primary"
                : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
            )}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* ══ Settings ═════════════════════════════════ */}
      {tab === "settings" && (
        <div className="space-y-5">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              XP verdienen
            </p>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field
                label="XP pro Nachricht"
                hint="Zufällig zwischen den beiden Zahlen — gleiche Zahl zweimal heißt immer gleich viel."
              >
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    value={value("min_xp") ?? 15}
                    onChange={(e) => set("min_xp", Number(e.target.value) || 0)}
                    className={INPUT}
                  />
                  <span className="text-slate-600 shrink-0">bis</span>
                  <input
                    type="number"
                    min={0}
                    value={value("max_xp") ?? 25}
                    onChange={(e) => set("max_xp", Number(e.target.value) || 0)}
                    className={INPUT}
                  />
                </div>
              </Field>

              <Field
                label="Abklingzeit"
                hint="So lange muss zwischen zwei XP-Gewinnen liegen. Verhindert Spam."
              >
                <div className="relative">
                  <Timer className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
                  <input
                    type="number"
                    min={0}
                    value={value("cooldown_seconds") ?? 60}
                    onChange={(e) => set("cooldown_seconds", Number(e.target.value) || 0)}
                    className={cn(INPUT, "pl-11")}
                  />
                </div>
              </Field>
            </div>

            {Number(value("min_xp")) > Number(value("max_xp")) && (
              <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
                <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                <p className="text-[12px] text-amber-200/80">
                  Das Minimum ist größer als das Maximum — beim Speichern werden
                  die Werte angeglichen.
                </p>
              </div>
            )}
          </div>

          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Level-Up-Nachricht
            </p>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Wohin melden">
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "channel", label: "Kanal" },
                    { id: "dm", label: "Privat" },
                    { id: "off", label: "Gar nicht" },
                  ].map((o) => (
                    <button
                      key={o.id}
                      onClick={() => set("announce_mode", o.id)}
                      className={cn(
                        "h-11 rounded-xl text-xs font-bold border transition-all",
                        (value("announce_mode") || "channel") === o.id
                          ? "bg-primary/15 border-primary/40 text-primary"
                          : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </Field>

              <Field
                label="Kanal"
                hint="Leer lassen: die Meldung erscheint dort, wo geschrieben wurde."
              >
                <ChannelPicker
                  guildId={guildId}
                  value={value("channel_id") || ""}
                  onChange={(id) => set("channel_id", id || null)}
                  placeholder="Wo geschrieben wurde"
                  channelTypes={["0", "5"]}
                  disabled={(value("announce_mode") || "channel") !== "channel"}
                />
              </Field>
            </div>

            <Field label="Text">
              <textarea
                value={value("level_message") ?? ""}
                onChange={(e) => set("level_message", e.target.value)}
                rows={3}
                maxLength={2000}
                className={cn(INPUT, "resize-y")}
              />
              <div className="pt-1">
                <EmojiPicker
                  onPick={(raw) => {
                    const now = String(value("level_message") ?? "");
                    if ((now + raw).length <= 2000) set("level_message", now + raw);
                  }}
                />
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {Object.entries(data.placeholders || {}).map(([key, hint]) => (
                  <button
                    key={key}
                    title={String(hint)}
                    onClick={() => set("level_message", `${value("level_message") ?? ""}{${key}}`)}
                    className="px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
                  >
                    {`{${key}}`}
                  </button>
                ))}
              </div>
            </Field>

            <div className="rounded-xl bg-[#0b1626] border border-slate-800/70 p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 flex items-center gap-1">
                <Eye className="h-3 w-3" /> Vorschau
              </p>
              <div
                className="rounded border-l-4 bg-[#2b2d31] p-3.5"
                style={{ borderLeftColor: colourHex }}
              >
                <p className="text-xs font-bold text-white mb-1">Level aufgestiegen</p>
                <p className="text-sm text-[#dbdee1] whitespace-pre-line break-words">
                  {preview || <span className="italic text-slate-600">leer</span>}
                </p>
              </div>
            </div>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Farbe">
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={colourHex}
                    onChange={(e) =>
                      set("embed_color", parseInt(e.target.value.slice(1), 16))
                    }
                    className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1 shrink-0"
                  />
                  <input
                    value={colourHex}
                    onChange={(e) => {
                      const v = e.target.value.replace("#", "");
                      if (/^[0-9a-f]{6}$/i.test(v)) set("embed_color", parseInt(v, 16));
                    }}
                    className={cn(INPUT, "font-mono")}
                  />
                </div>
              </Field>

              <Field label="Bild in der Nachricht" hint="Optional, muss mit https:// anfangen.">
                <input
                  value={value("level_image") ?? ""}
                  onChange={(e) => set("level_image", e.target.value)}
                  placeholder="https://…"
                  className={INPUT}
                />
              </Field>
            </div>

            <button
              onClick={() =>
                act(() =>
                  api.previewLevelUp(guildId, {
                    channel_id: value("channel_id") || undefined,
                    level_message: value("level_message"),
                    embed_color: value("embed_color"),
                    level_image: value("level_image"),
                  })
                )
              }
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
            >
              <Send className="h-4 w-4" />
              Vorschau in den Kanal senden
            </button>
          </div>

          {/* Auto delete */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Automatisch aufräumen
              </p>
              <p className="text-[11px] text-slate-600 mt-1.5">
                Damit der Chat nicht mit Level-Meldungen und Rangkarten zuläuft.
              </p>
            </div>

            <Field label="Level-Up-Nachricht löschen nach">
              <div className="flex gap-1.5 flex-wrap">
                {DELETE_PRESETS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => set("delete_after", p.value)}
                    className={cn(
                      "px-4 h-11 rounded-xl text-xs font-bold border transition-all",
                      (value("delete_after") ?? 0) === p.value
                        ? "bg-primary/15 border-primary/40 text-primary"
                        : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                    )}
                  >
                    {p.label}
                  </button>
                ))}
                <input
                  type="number"
                  min={0}
                  value={value("delete_after") ?? 0}
                  onChange={(e) => set("delete_after", Number(e.target.value) || 0)}
                  className="h-11 w-24 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                />
              </div>
            </Field>

            <Field label="Antworten auf Befehle löschen nach">
              <div className="flex gap-1.5 flex-wrap">
                {DELETE_PRESETS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => set("command_delete_after", p.value)}
                    className={cn(
                      "px-4 h-11 rounded-xl text-xs font-bold border transition-all",
                      (value("command_delete_after") ?? 0) === p.value
                        ? "bg-primary/15 border-primary/40 text-primary"
                        : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                    )}
                  >
                    {p.label}
                  </button>
                ))}
                <input
                  type="number"
                  min={0}
                  value={value("command_delete_after") ?? 0}
                  onChange={(e) => set("command_delete_after", Number(e.target.value) || 0)}
                  className="h-11 w-24 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                />
              </div>
            </Field>

            <InlineToggle
              checked={value("delete_command_message")}
              onCheckedChange={(v: boolean) => set("delete_command_message", v)}
              label="Auch den Befehl des Mitglieds löschen"
              hint="Das „!rank“ verschwindet gleich mit. Der Bot braucht dafür das Recht, Nachrichten zu verwalten."
            />
          </div>

          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Rangkarte
            </p>

            <Field label="Aussehen">
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "image", icon: Sparkles, label: "Als Bild", desc: "Gezeichnete Karte mit Profilbild" },
                  { id: "text", icon: MessageSquare, label: "Als Text", desc: "Schneller, immer lesbar" },
                ].map((o) => (
                  <button
                    key={o.id}
                    onClick={() => set("card_style", o.id)}
                    className={cn(
                      "text-left rounded-2xl border p-4 transition-all",
                      (value("card_style") || "image") === o.id
                        ? "bg-primary/10 border-primary/40"
                        : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                    )}
                  >
                    <o.icon className={cn(
                      "h-4 w-4 mb-2",
                      (value("card_style") || "image") === o.id ? "text-primary" : "text-slate-500"
                    )} />
                    <p className="text-sm font-bold text-white">{o.label}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{o.desc}</p>
                  </button>
                ))}
              </div>
            </Field>

            <InlineToggle
              checked={value("thumbnail_enabled")}
              onCheckedChange={(v: boolean) => set("thumbnail_enabled", v)}
              label="Profilbild in der Level-Up-Nachricht"
            />
          </div>
        </div>
      )}

      {/* ══ Rewards ══════════════════════════════════ */}
      {tab === "rewards" && (
        <RewardsTab
          guildId={guildId}
          data={data}
          busy={busy}
          act={act}
          reload={load}
          stack={!!value("stack_roles")}
          onStack={(v: boolean) => save({ stack_roles: v })}
        />
      )}

      {/* ══ Multipliers and exclusions ═══════════════ */}
      {tab === "tuning" && (
        <TuningTab guildId={guildId} data={data} busy={busy} act={act} />
      )}

      {/* ══ Members ══════════════════════════════════ */}
      {tab === "members" && <MembersTab guildId={guildId} busy={busy} act={act} />}

      {/* ══ What each level costs ════════════════════ */}
      {tab === "curve" && <CurveTab guildId={guildId} />}

      {/* ── Sticky save ──────────────────────────────── */}
      <StickySaveBar
        id="leveling-save-bar"
        count={dirtyCount}
        busy={busy}
        shake={guard.shake}
        onDiscard={() => setDraft({})}
        onSave={() => save()}
      />
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * Reward roles
 * ------------------------------------------------------------------ */

function RewardsTab({ guildId, data, busy, act, stack, onStack, reload }: any) {
  const [level, setLevel] = useState(5);
  const [roleId, setRoleId] = useState("");

  return (
    <div className="space-y-5">
      {/* Build the whole ladder in one go */}
      <LadderWizard guildId={guildId} onDone={reload} />

      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Einzelne Belohnung
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5">
            Wer dieses Level erreicht, bekommt die Rolle automatisch.
          </p>
        </div>

        <div className="grid lg:grid-cols-[140px_1fr_auto] gap-3 items-end">
          <Field label="Ab Level">
            <input
              type="number"
              min={1}
              value={level}
              onChange={(e) => setLevel(Math.max(1, Number(e.target.value) || 1))}
              className={INPUT}
            />
          </Field>
          <Field label="Rolle">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
            />
          </Field>
          <button
            onClick={() =>
              act(async () => {
                const res = await api.addLevelReward(guildId, level, roleId);
                setRoleId("");
                return res;
              })
            }
            disabled={busy || !roleId}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Hinzufügen
          </button>
        </div>
      </div>

      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Belohnungen ({data.rewards?.length || 0})
          </p>
          {(data.rewards?.length || 0) > 0 && (
            <button
              onClick={() =>
                act(
                  () => api.syncLevelRewards(guildId),
                  "Allen Mitgliedern die Rollen geben, die ihr Level schon verdient hat?"
                )
              }
              disabled={busy}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Rollen nachtragen
            </button>
          )}
        </div>

        <InlineToggle
          checked={stack}
          onCheckedChange={onStack}
          label="Frühere Rollen behalten"
          hint="Aus: Beim Aufstieg wird die vorige Belohnungsrolle wieder abgenommen, nur die höchste bleibt."
        />

        {!data.rewards?.length ? (
          <p className="text-sm text-slate-500 text-center py-10 border border-dashed border-slate-800 rounded-2xl">
            Noch keine Belohnungen eingerichtet.
          </p>
        ) : (
          <div className="space-y-2">
            {data.rewards.map((r: any) => (
              <div
                key={r.level}
                className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3 flex-wrap"
              >
                <span className="px-3 py-1.5 rounded-lg bg-primary/15 text-primary text-xs font-black shrink-0">
                  Level {r.level}
                </span>
                <span className="text-slate-600">→</span>
                <span className={cn(
                  "text-sm font-bold flex-1 min-w-0 truncate",
                  r.missing ? "text-red-400 italic" : "text-white"
                )}
                  style={!r.missing && r.role_colour
                    ? { color: `#${r.role_colour.toString(16).padStart(6, "0")}` }
                    : undefined}
                >
                  {r.missing ? "Rolle wurde gelöscht" : `@${r.role_name}`}
                </span>
                <button
                  onClick={() =>
                    act(
                      () => api.removeLevelReward(guildId, r.level),
                      `Belohnung für Level ${r.level} entfernen?`
                    )
                  }
                  disabled={busy}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all disabled:opacity-40 shrink-0"
                  title="Entfernen"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Multipliers and exclusions
 * ------------------------------------------------------------------ */

function TuningTab({ guildId, data, busy, act }: any) {
  const [kind, setKind] = useState<"role" | "channel">("role");
  const [targetId, setTargetId] = useState("");
  const [factor, setFactor] = useState(2);

  const [exKind, setExKind] = useState<"role" | "channel">("channel");
  const [exTarget, setExTarget] = useState("");

  const Picker = ({ type, value, onChange }: any) =>
    type === "role" ? (
      <RolePicker guildId={guildId} value={value} onChange={onChange} placeholder="Rolle wählen" />
    ) : (
      <ChannelPicker guildId={guildId} value={value} onChange={onChange} placeholder="Kanal wählen" />
    );

  return (
    <div className="space-y-5">
      {/* Multipliers */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            XP-Multiplikatoren
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5">
            Mehr XP für bestimmte Rollen oder Kanäle. Bei mehreren passenden
            Rollen zählt die höchste — sie multiplizieren sich nicht.
          </p>
        </div>

        <div className="grid lg:grid-cols-[150px_1fr_120px_auto] gap-3 items-end">
          <Field label="Für">
            <div className="grid grid-cols-2 gap-1.5">
              {(["role", "channel"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => { setKind(k); setTargetId(""); }}
                  className={cn(
                    "h-[46px] rounded-xl text-xs font-bold border transition-all",
                    kind === k
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400"
                  )}
                >
                  {k === "role" ? "Rolle" : "Kanal"}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Ziel">
            <Picker type={kind} value={targetId} onChange={(id: string) => setTargetId(id || "")} />
          </Field>
          <Field label="Faktor">
            <input
              type="number"
              min={0.1}
              step={0.5}
              value={factor}
              onChange={(e) => setFactor(Number(e.target.value) || 1)}
              className={INPUT}
            />
          </Field>
          <button
            onClick={() =>
              act(async () => {
                const res = await api.addLevelMultiplier(guildId, {
                  target_id: targetId, target_type: kind, multiplier: factor,
                });
                setTargetId("");
                return res;
              })
            }
            disabled={busy || !targetId}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        {!data.multipliers?.length ? (
          <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
            Keine Multiplikatoren.
          </p>
        ) : (
          <div className="space-y-2">
            {data.multipliers.map((m: any) => (
              <div
                key={`${m.target_type}-${m.target_id}`}
                className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3"
              >
                <span className="text-[10px] font-black uppercase text-slate-600 shrink-0">
                  {m.target_type === "role" ? "Rolle" : "Kanal"}
                </span>
                <span className={cn(
                  "text-sm flex-1 min-w-0 truncate",
                  m.missing ? "text-red-400 italic" : "text-white"
                )}>
                  {m.missing ? "gelöscht" : (m.target_type === "role" ? "@" : "#") + m.name}
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-primary/15 text-primary text-xs font-black shrink-0">
                  {m.multiplier}×
                </span>
                <button
                  onClick={() =>
                    act(() =>
                      api.removeLevelMultiplier(guildId, m.target_type, m.target_id)
                    )
                  }
                  disabled={busy}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Exclusions */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Kein XP für
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5">
            In diesen Kanälen, oder mit diesen Rollen, wird kein XP gesammelt.
          </p>
        </div>

        <div className="grid lg:grid-cols-[150px_1fr_auto] gap-3 items-end">
          <Field label="Art">
            <div className="grid grid-cols-2 gap-1.5">
              {(["channel", "role"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => { setExKind(k); setExTarget(""); }}
                  className={cn(
                    "h-[46px] rounded-xl text-xs font-bold border transition-all",
                    exKind === k
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400"
                  )}
                >
                  {k === "role" ? "Rolle" : "Kanal"}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Ziel">
            <Picker type={exKind} value={exTarget} onChange={(id: string) => setExTarget(id || "")} />
          </Field>
          <button
            onClick={() =>
              act(async () => {
                const res = await api.addLevelExcluded(guildId, {
                  target_id: exTarget, target_type: exKind,
                });
                setExTarget("");
                return res;
              })
            }
            disabled={busy || !exTarget}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        {!data.excluded?.length ? (
          <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
            Nichts ausgenommen.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {data.excluded.map((e: any) => (
              <span
                key={`${e.target_type}-${e.target_id}`}
                className="flex items-center gap-2 px-3 py-2 rounded-xl bg-[#0d1b31] border border-slate-800 text-sm"
              >
                <span className={cn(e.missing ? "text-red-400 italic" : "text-slate-300")}>
                  {e.missing ? "gelöscht" : (e.target_type === "role" ? "@" : "#") + e.name}
                </span>
                <button
                  onClick={() =>
                    act(() => api.removeLevelExcluded(guildId, e.target_type, e.target_id))
                  }
                  disabled={busy}
                  className="text-slate-600 hover:text-red-400 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Members
 * ------------------------------------------------------------------ */

function MembersTab({ guildId, busy, act }: any) {
  const [board, setBoard] = useState<any>(null);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBoard(await api.getLevelingBoard(guildId, page, 25));
    } catch (err: any) {
      toast.error(err?.message || "Bestenliste konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId, page]);

  useEffect(() => { load(); }, [load]);

  const entries = useMemo(() => {
    const list = board?.entries || [];
    const q = query.trim().toLowerCase();
    return q
      ? list.filter((e: any) => e.name.toLowerCase().includes(q) || e.user_id.includes(q))
      : list;
  }, [board, query]);

  const pages = Math.max(1, Math.ceil((board?.total || 0) / (board?.per_page || 25)));

  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
      {editing && (
        <EditMember
          guildId={guildId}
          member={editing}
          onClose={() => setEditing(null)}
          onDone={async () => { setEditing(null); await load(); }}
        />
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name oder ID suchen"
            className={cn(INPUT, "pl-10")}
          />
        </div>
        <button
          onClick={() =>
            act(
              async () => {
                const res = await api.resetLevelingAll(guildId);
                await load();
                return res;
              },
              "Wirklich das XP von ALLEN Mitgliedern löschen? Das lässt sich nicht rückgängig machen."
            )
          }
          disabled={busy}
          className="px-4 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-red-400 hover:border-red-500/30 disabled:opacity-40 transition-all"
        >
          Alles zurücksetzen
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 text-primary animate-spin opacity-40" />
        </div>
      ) : entries.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-12">
          {query ? "Niemand gefunden." : "Hier hat noch niemand XP gesammelt."}
        </p>
      ) : (
        <div className="space-y-2">
          {entries.map((e: any) => (
            <div
              key={e.user_id}
              className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3 flex-wrap"
            >
              <span className={cn(
                "w-10 text-center text-xs font-black shrink-0",
                e.rank === 1 ? "text-amber-400"
                  : e.rank === 2 ? "text-slate-300"
                    : e.rank === 3 ? "text-amber-700" : "text-slate-600"
              )}>
                #{e.rank}
              </span>

              {e.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={e.avatar} alt="" className="h-8 w-8 rounded-full shrink-0" />
              ) : (
                <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
              )}

              <div className="min-w-0 flex-1">
                <p className={cn(
                  "text-sm font-bold truncate",
                  e.left ? "text-slate-500 italic" : "text-white"
                )}>
                  {e.name}
                </p>
                <p className="text-[11px] text-slate-500">
                  Level {e.level} · {num(e.xp)} XP · {num(e.messages)} Nachrichten
                </p>
              </div>

              <button
                onClick={() => setEditing(e)}
                className="p-2 rounded-lg text-slate-500 hover:text-primary transition-all shrink-0"
                title="Bearbeiten"
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                onClick={() =>
                  act(
                    async () => {
                      const res = await api.resetLevelingMember(guildId, e.user_id);
                      await load();
                      return res;
                    },
                    `${e.name} auf 0 zurücksetzen?`
                  )
                }
                disabled={busy}
                className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all shrink-0"
                title="Zurücksetzen"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-bold text-slate-300 disabled:opacity-30"
          >
            Zurück
          </button>
          <span className="text-xs text-slate-500">
            Seite {page} von {pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages}
            className="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-bold text-slate-300 disabled:opacity-30"
          >
            Weiter
          </button>
        </div>
      )}
    </div>
  );
}

function EditMember({ guildId, member, onClose, onDone }: any) {
  const [mode, setMode] = useState<"xp" | "level" | "add_xp">("xp");
  const [amount, setAmount] = useState(member.xp);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setAmount(mode === "level" ? member.level : mode === "add_xp" ? 100 : member.xp);
  }, [mode, member]);

  const apply = async () => {
    setSaving(true);
    try {
      const res = await api.setLevelingMember(guildId, member.user_id, {
        [mode]: amount,
      });
      toast.success(res?.result || "Gespeichert.");
      await onDone();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-md shadow-2xl border-glow-card">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-black text-white truncate">{member.name}</h3>
            <p className="text-[11px] text-slate-500">
              Level {member.level} · {num(member.xp)} XP
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white shrink-0">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "xp", label: "XP setzen" },
              { id: "level", label: "Level setzen" },
              { id: "add_xp", label: "XP geben" },
            ].map((o) => (
              <button
                key={o.id}
                onClick={() => setMode(o.id as any)}
                className={cn(
                  "h-11 rounded-xl text-xs font-bold border transition-all",
                  mode === o.id
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "bg-[#0d1b31] border-slate-800 text-slate-400"
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          <Field
            label={mode === "level" ? "Neues Level" : mode === "add_xp" ? "XP dazu" : "Neues XP"}
            hint={mode === "add_xp" ? "Eine negative Zahl zieht XP ab." : undefined}
          >
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value) || 0)}
              className={INPUT}
            />
          </Field>
        </div>

        <div className="p-5 border-t border-slate-800 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white transition-all"
          >
            Abbrechen
          </button>
          <button
            onClick={apply}
            disabled={saving}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Übernehmen
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * What each level costs
 *
 * Server owners kept having to ask how long level 10 takes. The answer
 * depends on the guild's own XP rate and cooldown, so the numbers come
 * from the API rather than being a fixed table in the docs.
 * ------------------------------------------------------------------ */

function duration(seconds: number) {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const d = Math.floor(h / 24);
  if (d >= 1) return `${d} Tg`;
  if (h >= 1) return `${h} Std`;
  return `${Math.max(1, Math.round(seconds / 60))} Min`;
}

function CurveTab({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [upTo, setUpTo] = useState(25);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getLevelCurve(guildId, upTo)
      .then((fresh) => { if (!cancelled) setData(fresh); })
      .catch((err: any) => toast.error(err?.message || "Konnte nicht geladen werden."))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [guildId, upTo]);

  const levels = data?.levels || [];
  // Scale the bars against the most expensive level on screen.
  const peak = levels.length ? levels[levels.length - 1].step_xp : 1;

  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Wie viel XP jedes Level braucht
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5 leading-relaxed">
            Gerechnet mit den Einstellungen dieses Servers:{" "}
            <b className="text-slate-400">
              ⌀ {data?.average_xp_per_message ?? "…"} XP pro Nachricht
            </b>
            , Abklingzeit {data?.cooldown_seconds ?? "…"}s. Ändere die Werte im
            Reiter „Einstellungen“, dann rechnet die Tabelle neu.
          </p>
        </div>

        <div className="flex gap-1.5 shrink-0">
          {[10, 25, 50, 100].map((n) => (
            <button
              key={n}
              onClick={() => setUpTo(n)}
              className={cn(
                "px-3 h-10 rounded-xl text-xs font-bold border transition-all",
                upTo === n
                  ? "bg-primary/15 border-primary/40 text-primary"
                  : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
              )}
            >
              bis {n}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-14">
          <Loader2 className="h-6 w-6 text-primary animate-spin opacity-40" />
        </div>
      ) : (
        <>
          {/* Header row, hidden on narrow screens where the cards stack. */}
          <div className="hidden md:grid grid-cols-[64px_1fr_110px_110px_90px] gap-3 px-3 text-[10px] font-black uppercase tracking-widest text-slate-600">
            <span>Level</span>
            <span>XP für dieses Level</span>
            <span className="text-right">Nachrichten</span>
            <span className="text-right">XP gesamt</span>
            <span className="text-right">min. Zeit</span>
          </div>

          <div className="space-y-1 max-h-[560px] overflow-y-auto pr-1">
            {levels.map((row: any) => (
              <div
                key={row.level}
                className={cn(
                  "grid md:grid-cols-[64px_1fr_110px_110px_90px] gap-x-3 gap-y-1 items-center rounded-xl px-3 py-2.5 border transition-colors",
                  row.role_id
                    ? "bg-primary/[0.06] border-primary/25"
                    : "bg-[#0d1b31] border-slate-800/60"
                )}
              >
                <span className="text-sm font-black text-white">
                  {row.level}
                  {row.role_name && (
                    <span className="md:hidden ml-2 text-[10px] font-bold text-primary">
                      @{row.role_name}
                    </span>
                  )}
                </span>

                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary/70"
                        style={{ width: `${Math.max(2, (row.step_xp / peak) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-400 tabular-nums shrink-0">
                      {num(row.step_xp)}
                    </span>
                  </div>
                  {row.role_name && (
                    <span className="hidden md:inline text-[10px] font-bold text-primary">
                      Belohnung: @{row.role_name}
                    </span>
                  )}
                </div>

                <span className="text-xs text-slate-400 tabular-nums md:text-right">
                  <span className="md:hidden text-slate-600">Nachrichten: </span>
                  {num(row.messages)}
                </span>
                <span className="text-xs text-slate-500 tabular-nums md:text-right">
                  <span className="md:hidden text-slate-600">gesamt: </span>
                  {num(row.total_xp)}
                </span>
                <span className="text-xs text-slate-500 tabular-nums md:text-right">
                  {duration(row.min_seconds)}
                </span>
              </div>
            ))}
          </div>

          <p className="text-[11px] text-slate-600 leading-relaxed">
            „min. Zeit“ ist der schnellstmögliche Fall — jemand schreibt exakt
            nach jeder Abklingzeit eine Nachricht. In der Praxis dauert es
            deutlich länger. Multiplikatoren sind hier nicht eingerechnet.
          </p>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Automatic role ladder
 *
 * Building this by hand means creating a dozen roles in Discord,
 * colouring each one, dragging them into order and then registering a
 * reward per level. This does all of it in one call.
 *
 * Nothing is created until the preview has been shown: a dozen new roles
 * are tedious to undo, so the plan is always visible first.
 * ------------------------------------------------------------------ */

function LadderWizard({ guildId, onDone }: { guildId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<any>(null);
  const [rungs, setRungs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [askSetup, setAskSetup] = useState(false);

  const [ramp, setRamp] = useState("sunrise");
  const [style, setStyle] = useState("level");
  const [spacing, setSpacing] = useState("linear");
  const [count, setCount] = useState(5);
  const [step, setStep] = useState(5);
  const [hoist, setHoist] = useState(true);

  useEffect(() => {
    if (!open || options) return;
    api.getLadderOptions(guildId).then(setOptions).catch(() => setOptions(null));
  }, [open, options, guildId]);

  // Re-run the preview whenever a choice changes.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .previewLadder(guildId, { ramp, style, spacing, count, step })
      .then((res) => { if (!cancelled) setRungs(res.rungs || []); })
      .catch(() => { if (!cancelled) setRungs([]); });
    return () => { cancelled = true; };
  }, [open, guildId, ramp, style, spacing, count, step]);

  const create = async (fullSetup: boolean) => {
    setBusy(true);
    setAskSetup(false);
    try {
      const res = await api.createLadder(guildId, {
        ramp, style, spacing, count, step, hoist,
        reuse_existing: true,
        full_setup: fullSetup,
      });
      toast.success(res?.result || "Erstellt.");
      for (const warning of res?.warnings || []) toast.warning(warning);
      setOpen(false);
      onDone();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full flex items-center gap-4 bg-[#10233f] border border-dashed border-primary/30 rounded-3xl p-4 sm:p-6 text-left hover:border-primary/60 transition-all group border-glow-card"
      >
        <div className="h-11 w-11 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
          <Wand2 className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-black text-white">Level-Rollen automatisch anlegen</p>
          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
            Erstellt fertige Rollen mit passenden Farben, sortiert sie und
            trägt sie als Belohnung ein — in einem Schritt.
          </p>
        </div>
        <ChevronRight className="h-5 w-5 text-slate-600 group-hover:text-primary transition-colors shrink-0" />
      </button>
    );
  }

  return (
    <div className="bg-[#10233f] border border-primary/30 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
      {/* The follow-up question, once they press create */}
      {askSetup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-md shadow-2xl">
            <div className="p-6 space-y-4">
              <div className="h-11 w-11 rounded-2xl bg-primary/15 grid place-items-center">
                <Sparkles className="h-5 w-5 text-primary" />
              </div>
              <h3 className="font-black text-white text-lg">
                Auch den Rest einrichten?
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                Die {rungs.length} Rollen werden auf jeden Fall angelegt.
                Zusätzlich kann das Level-System gleich komplett für dich
                eingestellt werden:
              </p>
              <ul className="text-[13px] text-slate-400 space-y-1.5 pl-1">
                <li>• Level-System einschalten</li>
                <li>• 15–25 XP pro Nachricht, 60s Abklingzeit</li>
                <li>• Level-Up-Nachricht im Kanal, verschwindet nach 60s</li>
                <li>• Nur die höchste Belohnungsrolle behalten</li>
              </ul>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Alles davon kannst du danach einzeln ändern. Bestehende
                Belohnungen bleiben unangetastet.
              </p>
            </div>
            <div className="p-5 border-t border-slate-800 flex gap-3 flex-wrap">
              <button
                onClick={() => create(false)}
                disabled={busy}
                className="flex-1 min-w-[140px] py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-white disabled:opacity-40 transition-all"
              >
                Nur die Rollen
              </button>
              <button
                onClick={() => create(true)}
                disabled={busy}
                className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Ja, alles einrichten
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
          <Wand2 className="h-3.5 w-3.5 text-primary" />
          Level-Rollen automatisch anlegen
        </p>
        <button
          onClick={() => setOpen(false)}
          className="text-slate-500 hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Field label="Farbverlauf">
          <div className="space-y-1.5">
            {(options?.ramps || []).map((r: any) => (
              <button
                key={r.id}
                onClick={() => setRamp(r.id)}
                className={cn(
                  "w-full flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all",
                  ramp === r.id
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                )}
              >
                <span className="flex gap-1 shrink-0">
                  {r.preview.map((hex: string, i: number) => (
                    <span
                      key={i}
                      className="h-5 w-5 rounded-md"
                      style={{ background: hex }}
                    />
                  ))}
                </span>
                <span className="min-w-0 text-left">
                  <span className="block text-sm font-bold text-white truncate">
                    {r.label}
                  </span>
                  <span className="block text-[10px] text-slate-500 truncate">
                    {r.description}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </Field>

        <div className="space-y-5">
          <Field label="Benennung">
            <div className="grid grid-cols-2 gap-1.5">
              {(options?.styles || []).map((o: any) => (
                <button
                  key={o.id}
                  onClick={() => setStyle(o.id)}
                  className={cn(
                    "h-11 px-3 rounded-xl text-xs font-bold border transition-all truncate",
                    style === o.id
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Abstände">
            <div className="space-y-1.5">
              {(options?.spacings || []).map((o: any) => (
                <button
                  key={o.id}
                  onClick={() => setSpacing(o.id)}
                  className={cn(
                    "w-full text-left rounded-xl border px-3 py-2 transition-all",
                    spacing === o.id
                      ? "bg-primary/10 border-primary/40"
                      : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                  )}
                >
                  <span className="block text-sm font-bold text-white">{o.label}</span>
                  <span className="block text-[10px] text-slate-500">{o.description}</span>
                </button>
              ))}
            </div>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Wie viele Rollen">
              <input
                type="number"
                min={1}
                max={25}
                value={count}
                onChange={(e) =>
                  setCount(Math.max(1, Math.min(25, Number(e.target.value) || 1)))
                }
                className={INPUT}
              />
            </Field>
            <Field
              label="Ab Level / Schritt"
              hint={spacing === "milestones" ? "Bei runden Zahlen ohne Wirkung." : undefined}
            >
              <input
                type="number"
                min={1}
                max={100}
                value={step}
                disabled={spacing === "milestones"}
                onChange={(e) =>
                  setStep(Math.max(1, Math.min(100, Number(e.target.value) || 1)))
                }
                className={cn(INPUT, spacing === "milestones" && "opacity-40")}
              />
            </Field>
          </div>

          <InlineToggle
            checked={hoist}
            onCheckedChange={setHoist}
            label="Rollen getrennt anzeigen"
            hint="Mitglieder mit der Rolle stehen in der Mitgliederliste in einer eigenen Gruppe."
          />
        </div>
      </div>

      {/* Preview */}
      <div className="rounded-2xl bg-[#0b1626] border border-slate-800/70 p-4 space-y-2">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1">
          <Eye className="h-3 w-3" /> Das wird angelegt
        </p>
        {rungs.length === 0 ? (
          <p className="text-sm text-slate-600 italic">Wird berechnet …</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {rungs.map((r: any) => (
              <span
                key={r.level}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl border text-sm"
                style={{
                  borderColor: `${r.colour_hex}66`,
                  background: `${r.colour_hex}14`,
                }}
              >
                <span
                  className="h-3 w-3 rounded-full shrink-0"
                  style={{ background: r.colour_hex }}
                />
                <span className="font-bold" style={{ color: r.colour_hex }}>
                  {r.name}
                </span>
                <span className="text-[10px] text-slate-500">Lvl {r.level}</span>
              </span>
            ))}
          </div>
        )}
        <p className="text-[11px] text-slate-600 leading-relaxed pt-1">
          Rollen mit gleichem Namen werden wiederverwendet statt doppelt
          angelegt. Der Bot braucht dafür das Recht „Rollen verwalten“, und
          seine eigene Rolle muss über den neuen stehen.
        </p>
      </div>

      <button
        onClick={() => setAskSetup(true)}
        disabled={busy || rungs.length === 0}
        className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
        {rungs.length} Rollen anlegen
      </button>
    </div>
  );
}
