"use client";

/**
 * Anonymous chat.
 *
 * A channel is marked anonymous; whatever a member writes there is
 * deleted at once and posted again by the bot, so no reader can tell who
 * wrote it.
 *
 * Two things this deliberately makes visible rather than hiding:
 *
 *   * the bot needs "manage messages" or the original stays up and the
 *     channel is not anonymous at all — shown as a red warning per
 *     channel instead of failing silently at runtime
 *   * the log deanonymises members for staff. Pretending otherwise
 *     would be worse than saying it plainly.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, Eye, Hash, Info, Link2, Loader2, Lock, MessageSquare,
  Plus, RefreshCw, Save, Search, Settings2, Shield, Trash2, UserX, Webhook, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { useSaveGuard } from "@/components/dashboard/save-bar";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

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

function Stat({ label, value }: any) {
  return (
    <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
      <p className="text-lg font-black text-white">{value}</p>
      <p className="text-[11px] text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

function ago(unix: number) {
  const diff = Date.now() - unix * 1000;
  const m = 60_000, h = 60 * m, d = 24 * h;
  if (diff < m) return "gerade eben";
  if (diff < h) return `vor ${Math.round(diff / m)} Min`;
  if (diff < d) return `vor ${Math.round(diff / h)} Std`;
  return `vor ${Math.round(diff / d)} Tg`;
}

export function AnonChatPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"channels" | "log" | "blocked">("channels");
  const [editing, setEditing] = useState<string | null>(null);
  const [newChannel, setNewChannel] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.getAnonChat(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      if (res?.warning) toast.warning(res.warning);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
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

  const channels = data?.channels || [];

  return (
    <section className="space-y-6">
      {/* ── What this is ─────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4">
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Lock className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">Schreiben ohne Namen</p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              In einem anonymen Kanal wird jede Nachricht sofort gelöscht und
              vom Bot ohne Absender neu gepostet. Für alle im Kanal ist nicht
              erkennbar, wer geschrieben hat.
            </p>
          </div>
        </div>

        <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
          <Shield className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-amber-200/80 leading-relaxed">
            Anonym heißt hier: anonym gegenüber anderen Mitgliedern. Wer das
            Dashboard öffnen darf, sieht im Protokoll, wer was geschrieben hat.
            Ohne diese Möglichkeit wäre so ein Kanal ein Freifahrtschein für
            Beleidigungen.
          </p>
        </div>

        {channels.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat label="Nachrichten" value={data.stats?.messages ?? 0} />
            <Stat label="Letzte 24 Std" value={data.stats?.last_24h ?? 0} />
            <Stat label="Verschiedene Leute" value={data.stats?.people ?? 0} />
          </div>
        )}
      </div>

      {/* ── Tabs ─────────────────────────────────────── */}
      <div className="flex gap-1.5 flex-wrap">
        {[
          { id: "channels", label: "Kanäle", icon: Hash },
          { id: "log", label: "Protokoll", icon: Eye },
          { id: "blocked", label: "Gesperrt", icon: Ban },
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

      {/* ══ Channels ═════════════════════════════════ */}
      {tab === "channels" && (
        <div className="space-y-5">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Kanal anonym machen
              </p>
              <button
                onClick={load}
                className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
              >
                <RefreshCw className="h-4 w-4 text-primary" />
              </button>
            </div>

            <div className="grid md:grid-cols-[1fr_auto] gap-3 items-end">
              <Field label="Kanal">
                <ChannelPicker
                  guildId={guildId}
                  value={newChannel}
                  onChange={(id) => setNewChannel(id || "")}
                  placeholder="Kanal wählen"
                  channelTypes={["0", "5"]}
                />
              </Field>
              <button
                onClick={() =>
                  act(async () => {
                    const res = await api.saveAnonChat(guildId, {
                      channel_id: newChannel,
                      enabled: true,
                    });
                    setNewChannel("");
                    return res;
                  })
                }
                disabled={busy || !newChannel}
                className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-2"
              >
                <Plus className="h-4 w-4" />
                Hinzufügen
              </button>
            </div>
          </div>

          {channels.length === 0 ? (
            <p className="text-sm text-slate-500 py-10 text-center border border-dashed border-slate-800 rounded-2xl">
              Noch kein anonymer Kanal.
            </p>
          ) : (
            <div className="space-y-3">
              {channels.map((channel: any) => (
                <ChannelCard
                  key={channel.channel_id}
                  guildId={guildId}
                  channel={channel}
                  modes={data.modes || []}
                  busy={busy}
                  act={act}
                  open={editing === channel.channel_id}
                  onToggleOpen={() =>
                    setEditing(editing === channel.channel_id ? null : channel.channel_id)
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══ Log ══════════════════════════════════════ */}
      {tab === "log" && <LogTab guildId={guildId} busy={busy} act={act} />}

      {/* ══ Blocked ══════════════════════════════════ */}
      {tab === "blocked" && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Vom anonymen Chat ausgeschlossen
            </p>
            <p className="text-[11px] text-slate-600 mt-1.5">
              Diese Mitglieder können in keinem anonymen Kanal schreiben. Sie
              erfahren es per DM, sonst würden sie ins Leere schreiben.
            </p>
          </div>

          {!data.blocked?.length ? (
            <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
              Niemand gesperrt.
            </p>
          ) : (
            <div className="space-y-2">
              {data.blocked.map((b: any) => (
                <div
                  key={b.user_id}
                  className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3"
                >
                  {b.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={b.avatar} alt="" className="h-8 w-8 rounded-full shrink-0" />
                  ) : (
                    <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white truncate">{b.name}</p>
                    {b.reason && (
                      <p className="text-[11px] text-slate-500 truncate">{b.reason}</p>
                    )}
                  </div>
                  <button
                    onClick={() => act(() => api.unblockAnonUser(guildId, b.user_id))}
                    disabled={busy}
                    className="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-white disabled:opacity-40 transition-all shrink-0"
                  >
                    Freigeben
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * One channel, with everything it can be configured with
 * ------------------------------------------------------------------ */

function ChannelCard({ guildId, channel, modes, busy, act, open, onToggleOpen }: any) {
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [preview, setPreview] = useState<any>(null);
  const [sample, setSample] = useState("Hallo, das ist ein Test https://beispiel.de");

  const value = (key: string) => (key in draft ? draft[key] : channel[key]);
  const set = (key: string, v: any) => setDraft((d) => ({ ...d, [key]: v }));
  const dirty = Object.keys(draft).length > 0;

  // Each channel card saves itself, but leaving the tab with one of
  // them half-edited used to drop the change without a word.
  const guard = useSaveGuard(dirty ? 1 : 0, `anon-save-${channel.channel_id}`);

  const save = () =>
    act(async () => {
      const res = await api.saveAnonChat(guildId, {
        channel_id: channel.channel_id,
        ...draft,
      });
      setDraft({});
      return res;
    });

  const runPreview = async () => {
    try {
      setPreview(
        await api.previewAnonMessage(guildId, {
          content: sample,
          settings: {
            alias: value("alias"),
            avatar_url: value("avatar_url"),
            allow_links: value("allow_links"),
            allow_mentions: value("allow_mentions"),
            max_length: value("max_length"),
          },
        })
      );
    } catch {
      setPreview(null);
    }
  };

  return (
    <div
      className={cn(
        "bg-[#10233f] border rounded-3xl p-5 space-y-4",
        channel.problem
          ? "border-red-500/30"
          : channel.enabled
            ? "border-slate-800"
            : "border-slate-800 opacity-60"
      )}
    >
      <div className="flex items-start gap-4 flex-wrap">
        <button onClick={onToggleOpen} className="min-w-0 flex-1 text-left group">
          <p className="font-black text-white flex items-center gap-2 flex-wrap">
            <Hash className="h-4 w-4 text-slate-600" />
            {channel.channel_name || "gelöschter Kanal"}
            {!channel.enabled && (
              <span className="px-2 py-0.5 rounded-md bg-slate-700/50 text-slate-400 text-[10px] font-black uppercase">
                aus
              </span>
            )}
          </p>
          <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
            {channel.mode === "webhook" ? (
              <><Webhook className="h-3 w-3" /> als &bdquo;{channel.alias}&ldquo;</>
            ) : (
              <><MessageSquare className="h-3 w-3" /> als Bot-Nachricht</>
            )}
            {channel.log_channel_name && <span>· Protokoll #{channel.log_channel_name}</span>}
            {!channel.log_channel_id && (
              <span className="text-amber-400/70">· kein Protokoll-Kanal</span>
            )}
          </p>
        </button>

        <div className="flex gap-2 shrink-0">
          <button
            onClick={onToggleOpen}
            className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
          >
            {open ? "Zuklappen" : "Einstellen"}
          </button>
          <button
            onClick={() =>
              act(
                () => api.deleteAnonChat(guildId, channel.channel_id),
                `#${channel.channel_name} wieder zu einem normalen Kanal machen?`
              )
            }
            disabled={busy}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 transition-all disabled:opacity-40"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {channel.problem && (
        <div className="rounded-xl bg-red-500/[0.07] border border-red-500/25 p-3.5 flex gap-2.5">
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-red-200/80 leading-relaxed">{channel.problem}</p>
        </div>
      )}

      {open && (
        <div className="space-y-5 border-t border-slate-800 pt-5">
          <InlineToggle
            checked={value("enabled")}
            onCheckedChange={(v: boolean) => set("enabled", v)}
            label="Kanal ist anonym"
            hint="Aus: Nachrichten bleiben ganz normal stehen."
          />

          {/* How it is posted */}
          <Field label="Wie wird gepostet">
            <div className="grid md:grid-cols-2 gap-2">
              {modes.map((m: any) => (
                <button
                  key={m.id}
                  onClick={() => set("mode", m.id)}
                  className={cn(
                    "text-left rounded-2xl border p-4 transition-all",
                    value("mode") === m.id
                      ? "bg-primary/10 border-primary/40"
                      : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                  )}
                >
                  {m.id === "webhook" ? (
                    <Webhook className={cn("h-4 w-4 mb-2", value("mode") === m.id ? "text-primary" : "text-slate-500")} />
                  ) : (
                    <MessageSquare className={cn("h-4 w-4 mb-2", value("mode") === m.id ? "text-primary" : "text-slate-500")} />
                  )}
                  <p className="text-sm font-bold text-white">{m.label}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                    {m.description}
                  </p>
                </button>
              ))}
            </div>
          </Field>

          <div className="grid lg:grid-cols-2 gap-5">
            <Field label="Angezeigter Name" hint="So heißt jeder Absender im Kanal.">
              <input
                value={value("alias") ?? ""}
                onChange={(e) => set("alias", e.target.value)}
                placeholder="Anonym"
                maxLength={80}
                className={INPUT}
              />
            </Field>
            <Field label="Profilbild (URL)" hint="Nur im Webhook-Modus. Muss mit https:// anfangen.">
              <input
                value={value("avatar_url") ?? ""}
                onChange={(e) => set("avatar_url", e.target.value)}
                placeholder="https://…"
                disabled={value("mode") !== "webhook"}
                className={cn(INPUT, value("mode") !== "webhook" && "opacity-40")}
              />
            </Field>
          </div>

          <Field
            label="Protokoll-Kanal"
            hint="Hier meldet der Bot jede anonyme Nachricht mit Absender. Nur für Leute sichtbar, die den Kanal sehen dürfen."
          >
            <ChannelPicker
              guildId={guildId}
              value={value("log_channel_id") || ""}
              onChange={(id) => set("log_channel_id", id || null)}
              placeholder="Kein Protokoll"
              channelTypes={["0", "5"]}
            />
          </Field>

          {/* Preview */}
          <div className="rounded-2xl bg-[#0b1626] border border-slate-800/70 p-4 space-y-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1">
              <Eye className="h-3 w-3" /> Ausprobieren
            </p>
            <div className="flex gap-2 flex-wrap">
              <input
                value={sample}
                onChange={(e) => { setSample(e.target.value); setPreview(null); }}
                className={cn(INPUT, "flex-1 min-w-[200px]")}
              />
              <button
                onClick={runPreview}
                className="px-5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/25 transition-all"
              >
                Prüfen
              </button>
            </div>
            {preview && (
              <div className="rounded-xl bg-[#313338] p-3.5 space-y-1">
                <p className="text-sm font-semibold text-white">
                  {preview.alias}
                  <span className="ml-1.5 px-1 py-0.5 rounded bg-[#5865f2] text-[9px] font-bold uppercase">
                    Bot
                  </span>
                </p>
                <p className="text-sm text-[#dbdee1] break-words whitespace-pre-line">
                  {preview.result || <span className="italic text-slate-600">leer</span>}
                </p>
                {preview.notes?.length > 0 && (
                  <p className="text-[11px] text-amber-300/70 pt-1">
                    {preview.notes.join(" ")}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Who may write */}
          <div className="border-t border-slate-800 pt-5 space-y-5">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Wer darf hier schreiben
            </p>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Rolle nötig">
                <RolePicker
                  guildId={guildId}
                  value={value("required_role_id") || ""}
                  onChange={(id) => set("required_role_id", id || null)}
                  placeholder="Keine Einschränkung"
                />
              </Field>
              <Field label="Rolle ausgeschlossen">
                <RolePicker
                  guildId={guildId}
                  value={value("blocked_role_id") || ""}
                  onChange={(id) => set("blocked_role_id", id || null)}
                  placeholder="Niemand ausgeschlossen"
                />
              </Field>
              <Field label="Account mindestens X Tage alt" hint="Hält Wegwerf-Accounts draußen.">
                <input
                  type="number"
                  min={0}
                  value={value("min_account_days") ?? 0}
                  onChange={(e) => set("min_account_days", Number(e.target.value) || 0)}
                  className={INPUT}
                />
              </Field>
              <Field label="Mindestens X Tage auf dem Server">
                <input
                  type="number"
                  min={0}
                  value={value("min_member_days") ?? 0}
                  onChange={(e) => set("min_member_days", Number(e.target.value) || 0)}
                  className={INPUT}
                />
              </Field>
              <Field label="Wartezeit zwischen Nachrichten (Sek.)" hint="0 = keine.">
                <input
                  type="number"
                  min={0}
                  value={value("cooldown_seconds") ?? 0}
                  onChange={(e) => set("cooldown_seconds", Number(e.target.value) || 0)}
                  className={INPUT}
                />
              </Field>
              <Field
                label="Protokoll aufbewahren (Tage)"
                hint="0 = für immer. Danach lässt sich niemand mehr nachschlagen."
              >
                <input
                  type="number"
                  min={0}
                  value={value("log_retention_days") ?? 0}
                  onChange={(e) => set("log_retention_days", Number(e.target.value) || 0)}
                  className={INPUT}
                />
              </Field>
            </div>

            <div className="space-y-3">
              <InlineToggle
                checked={value("allow_attachments")}
                onCheckedChange={(v: boolean) => set("allow_attachments", v)}
                label="Bilder und Dateien erlauben"
              />
              <InlineToggle
                checked={value("allow_links")}
                onCheckedChange={(v: boolean) => set("allow_links", v)}
                label="Links erlauben"
                hint="Aus: Links werden durch „[Link entfernt]“ ersetzt."
              />
              <InlineToggle
                checked={value("allow_mentions")}
                onCheckedChange={(v: boolean) => set("allow_mentions", v)}
                label="Erwähnungen erlauben"
                hint="Aus (empfohlen): @everyone und Rollen-Pings benachrichtigen niemanden. Anonym pingen zu können wird gerne missbraucht."
              />
            </div>
          </div>

          {dirty && (
            <div
              id={`anon-save-${channel.channel_id}`}
              className={cn(
                "flex gap-3 flex-wrap pt-2 rounded-xl transition-colors",
                guard.shake &&
                  "bg-red-500/10 border border-red-500/40 p-3 animate-[verify-shake_0.4s_ease-in-out]"
              )}
            >
              <button
                onClick={() => setDraft({})}
                className="px-4 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white transition-all"
              >
                Verwerfen
              </button>
              <button
                onClick={save}
                disabled={busy}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                Speichern
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * The staff-only log
 * ------------------------------------------------------------------ */

function LogTab({ guildId, busy, act }: any) {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getAnonLog(guildId, 100);
      setEntries(res.entries || []);
    } catch (err: any) {
      toast.error(err?.message || "Protokoll konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.user_id.includes(q) ||
        e.content.toLowerCase().includes(q)
    );
  }, [entries, query]);

  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
      <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
        <Info className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-amber-200/80 leading-relaxed">
          Hier steht, wer welche anonyme Nachricht geschrieben hat. Geh damit
          sorgsam um — für alle anderen im Server ist das nicht sichtbar.
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name, ID oder Textinhalt suchen"
            className={cn(INPUT, "pl-10")}
          />
        </div>
        <button
          onClick={load}
          className="p-3 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
        >
          <RefreshCw className="h-4 w-4 text-primary" />
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 text-primary animate-spin opacity-40" />
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-12">
          {query ? "Nichts gefunden." : "Noch keine anonymen Nachrichten."}
        </p>
      ) : (
        <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
          {filtered.map((entry) => (
            <div
              key={entry.id}
              className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3 space-y-2"
            >
              <div className="flex items-center gap-2.5 flex-wrap">
                {entry.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={entry.avatar} alt="" className="h-6 w-6 rounded-full shrink-0" />
                ) : (
                  <div className="h-6 w-6 rounded-full bg-slate-800 shrink-0" />
                )}
                <span className="text-sm font-bold text-white truncate">{entry.name}</span>
                <span className="text-[11px] text-slate-600">
                  {entry.channel_name ? `#${entry.channel_name}` : ""} · {ago(entry.at)}
                </span>
                <span className="flex-1" />
                {entry.url && (
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-600 hover:text-primary transition-colors"
                    title="Nachricht in Discord öffnen"
                  >
                    <Link2 className="h-3.5 w-3.5" />
                  </a>
                )}
                <button
                  onClick={() =>
                    act(
                      () =>
                        api.blockAnonUser(guildId, {
                          user_id: entry.user_id,
                          reason: "Über das Protokoll gesperrt",
                        }),
                      `${entry.name} vom anonymen Chat aussperren?`
                    )
                  }
                  disabled={busy}
                  className="text-slate-600 hover:text-red-400 transition-colors disabled:opacity-40"
                  title="Sperren"
                >
                  <UserX className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="text-[13px] text-slate-300 break-words whitespace-pre-line pl-8.5">
                {entry.content || <span className="italic text-slate-600">(nur Anhang)</span>}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
