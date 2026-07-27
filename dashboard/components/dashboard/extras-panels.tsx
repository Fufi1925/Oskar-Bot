"use client";

/**
 * Seven features that worked over chat commands but had no dashboard.
 *
 * They live in one file because they share the same shape — load, edit a
 * draft, save, reload — and splitting that into seven near-identical
 * files would just mean fixing every bug seven times.
 *
 * The pattern each panel follows: `value()` reads the draft first and
 * falls back to what the server sent, so a half-finished edit is never
 * lost by a background reload.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Cake, Calculator, Check, Clock, Gem, Hash, Info, Loader2,
  Lock, Moon, Pin, Plus, RefreshCw, Save, Send, Trash2, Trophy, Users, Youtube,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker, MultiRolePicker } from "@/components/dashboard/pickers";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";

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

function Card({ icon: Icon, title, subtitle, children, onReload }: any) {
  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">{title}</p>
            {subtitle && (
              <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {onReload && (
          <button
            onClick={onReload}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] shrink-0"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Warn({ children }: any) {
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <p className="text-[12px] text-amber-200/80 leading-relaxed">{children}</p>
    </div>
  );
}

function SaveBar({ count, onDiscard, onSave, busy }: any) {
  if (!count) return null;
  return (
    <div className="flex items-center gap-3 flex-wrap pt-2 border-t border-slate-800">
      <p className="text-sm text-slate-300 flex-1 min-w-[120px]">
        {count} Änderung{count === 1 ? "" : "en"} offen.
      </p>
      <button
        onClick={onDiscard}
        className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white transition-all"
      >
        Verwerfen
      </button>
      <button
        onClick={onSave}
        disabled={busy}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Speichern
      </button>
    </div>
  );
}

/** Shared load/draft/save wiring. */
function usePanel(load: () => Promise<any>) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});

  const reload = useCallback(async () => {
    try {
      setData(await load());
      setDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [load]);

  useEffect(() => { reload(); }, [reload]);

  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      await reload();
      return res;
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return {
    data, loading, busy, draft, setDraft, reload, act,
    value: (key: string) => (key in draft ? draft[key] : data?.[key]),
    set: (key: string, v: any) => setDraft((d) => ({ ...d, [key]: v })),
    dirty: Object.keys(draft).length,
  };
}

function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[240px]">
      <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Booster
 * ══════════════════════════════════════════════════════════════════ */

export function BoosterPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getBooster(guildId), [guildId]);
  const p = usePanel(load);

  const preview = useMemo(() => {
    let text = String(p.value("boost")?.message ?? "");
    const pairs: [string, string][] = [
      ["{user.mention}", "@Alex"],
      ["{user.name}", "Alex"],
      ["{user.tag}", "alex#0001"],
      ["{server.name}", "dein Server"],
      ["{server.boost_count}", String(p.data?.boost_count ?? 0)],
      ["{server.boost_level}", `Level ${p.data?.boost_level ?? 0}`],
      ["{server.member_count}", "1.204"],
    ];
    for (const [token, value] of pairs) text = text.split(token).join(value);
    return text;
  }, [p.draft, p.data]);

  if (p.loading) return <Loading />;

  const boost = p.value("boost") || {};
  const setBoost = (patch: any) => p.set("boost", { ...boost, ...patch });

  return (
    <section className="space-y-5">
      <Card
        icon={Gem}
        title="Booster belohnen"
        subtitle="Wer den Server boostet, bekommt eine Ankündigung und optional Rollen."
        onReload={p.reload}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">{p.data?.boost_count ?? 0}</p>
            <p className="text-[11px] text-slate-500">Boosts gerade</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">Level {p.data?.boost_level ?? 0}</p>
            <p className="text-[11px] text-slate-500">Server-Stufe</p>
          </div>
        </div>

        {(p.data?.boosters || []).length > 0 && (
          <div className="space-y-2">
            <p className="text-[11px] font-black uppercase tracking-widest text-slate-600">
              Aktuelle Booster
            </p>
            <div className="flex flex-wrap gap-2">
              {p.data.boosters.map((b: any) => (
                <span
                  key={b.user_id}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#0d1b31] border border-slate-800 text-sm text-slate-300"
                >
                  {b.avatar && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={b.avatar} alt="" className="h-5 w-5 rounded-full" />
                  )}
                  {b.name}
                </span>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card icon={Send} title="Ankündigung">
        <Field label="Kanal" hint="Wo die Boost-Meldung erscheint.">
          <ChannelPicker
            guildId={guildId}
            value={(p.value("boost")?.channel || [])[0] || ""}
            onChange={(id) => p.set("channels", id ? [id] : [])}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <Field label="Nachricht">
          <textarea
            value={boost.message ?? ""}
            onChange={(e) => setBoost({ message: e.target.value })}
            rows={3}
            className={cn(INPUT, "resize-y")}
          />
          <div className="flex flex-wrap gap-1.5 pt-1">
            {Object.keys(p.data?.placeholders || {}).map((token) => (
              <button
                key={token}
                title={p.data.placeholders[token]}
                onClick={() => setBoost({ message: (boost.message ?? "") + token })}
                className="px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
              >
                {token}
              </button>
            ))}
          </div>
        </Field>

        <div className="rounded-xl bg-[#0b1626] border border-slate-800/70 p-3.5">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-1.5">
            Vorschau
          </p>
          <p className="text-sm text-slate-200 whitespace-pre-line break-words">
            {preview || <span className="italic text-slate-600">leer</span>}
          </p>
        </div>

        <Field
          label="Nach X Sekunden löschen"
          hint="0 = bleibt stehen."
        >
          <input
            type="number"
            min={0}
            value={boost.autodel ?? 0}
            onChange={(e) => setBoost({ autodel: Number(e.target.value) || 0 })}
            className={INPUT}
          />
        </Field>

        <button
          onClick={() =>
            p.act(() =>
              api.testBooster(guildId, {
                channel_id: (p.value("boost")?.channel || [])[0],
                message: boost.message,
              })
            )
          }
          disabled={p.busy}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
        >
          <Send className="h-4 w-4" /> Vorschau senden
        </button>
      </Card>

      <Card
        icon={Users}
        title="Belohnungs-Rollen"
        subtitle="Bekommt jeder Booster automatisch. Müssen unter der Bot-Rolle stehen."
      >
        <MultiRolePicker
          guildId={guildId}
          value={p.value("roles") || []}
          onChange={(ids: string[]) => p.set("roles", ids)}
        />
      </Card>

      <SaveBar
        count={p.dirty}
        busy={p.busy}
        onDiscard={() => p.setDraft({})}
        onSave={() =>
          p.act(() =>
            api.updateBooster(guildId, {
              ...(p.draft.boost || {}),
              ...(p.draft.channels ? { channels: p.draft.channels } : {}),
              ...(p.draft.roles ? { roles: p.draft.roles } : {}),
            })
          )
        }
      />
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Sticky messages
 * ══════════════════════════════════════════════════════════════════ */

export function StickyPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getSticky(guildId), [guildId]);
  const p = usePanel(load);
  const [channelId, setChannelId] = useState("");
  const [message, setMessage] = useState("");

  if (p.loading) return <Loading />;

  return (
    <section className="space-y-5">
      <Card
        icon={Pin}
        title="Nachricht bleibt unten"
        subtitle="Der Bot postet sie neu, sobald jemand schreibt — sie steht also immer als Letztes im Kanal."
        onReload={p.reload}
      >
        <Warn>
          Der Bot braucht &bdquo;Nachrichten verwalten&ldquo;, sonst bleibt die alte Kopie
          stehen und der Kanal läuft mit Wiederholungen zu.
        </Warn>

        <div className="grid md:grid-cols-2 gap-5">
          <Field label="Kanal">
            <ChannelPicker
              guildId={guildId}
              value={channelId}
              onChange={(id) => setChannelId(id || "")}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>
        </div>

        <Field label="Text">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="Bitte lest zuerst die Regeln!"
            className={cn(INPUT, "resize-y")}
          />
        </Field>

        <button
          onClick={() =>
            p.act(async () => {
              const res = await api.setSticky(guildId, {
                channel_id: channelId, message,
              });
              setMessage("");
              return res;
            })
          }
          disabled={p.busy || !channelId || !message.trim()}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          <Plus className="h-4 w-4" /> Festpinnen
        </button>
      </Card>

      {!p.data?.entries?.length ? (
        <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
          Noch keine Sticky-Nachricht.
        </p>
      ) : (
        <div className="space-y-2">
          {p.data.entries.map((entry: any) => (
            <div
              key={entry.channel_id}
              className={cn(
                "bg-[#10233f] border rounded-2xl p-4 space-y-2",
                entry.missing || !entry.can_post
                  ? "border-amber-500/25" : "border-slate-800"
              )}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <Hash className="h-4 w-4 text-slate-600 shrink-0" />
                <span className="text-sm font-bold text-white flex-1 min-w-0 truncate">
                  {entry.channel_name || "gelöschter Kanal"}
                </span>
                {!entry.missing && !entry.can_post && (
                  <span className="text-[10px] font-black uppercase text-amber-400">
                    Bot darf nicht schreiben
                  </span>
                )}
                <button
                  onClick={() =>
                    p.act(
                      () => api.removeSticky(guildId, entry.channel_id),
                      "Sticky-Nachricht entfernen?"
                    )
                  }
                  disabled={p.busy}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <p className="text-[13px] text-slate-400 whitespace-pre-line break-words pl-6">
                {entry.message}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Nightmode
 * ══════════════════════════════════════════════════════════════════ */

export function NightmodePanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getNightmode(guildId), [guildId]);
  const p = usePanel(load);

  if (p.loading) return <Loading />;

  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <section className="space-y-5">
      <Card
        icon={Moon}
        title="Nachts automatisch schließen"
        subtitle="Zur eingestellten Zeit darf niemand mehr schreiben, morgens geht es von allein wieder auf."
        onReload={p.reload}
      >
        {!p.data?.can_manage && (
          <Warn>
            Dem Bot fehlt &bdquo;Kanäle verwalten&ldquo; — er könnte gar nichts schließen.
          </Warn>
        )}

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="font-black text-white">
              {p.value("enabled") ? "Zeitplan läuft" : "Ausgeschaltet"}
            </p>
            <p className="text-[11px] text-slate-500">
              {p.data?.active
                ? "Die Kanäle sind gerade geschlossen."
                : "Die Kanäle sind offen."}
            </p>
          </div>
          <InlineToggle
            checked={p.value("enabled")}
            onCheckedChange={(v: boolean) => p.set("enabled", v)}
            label="Zeitplan aktiv"
          />
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          <Field label="Schließen um">
            <select
              value={p.value("start_hour") ?? 23}
              onChange={(e) => p.set("start_hour", Number(e.target.value))}
              className={INPUT}
            >
              {hours.map((h) => (
                <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
              ))}
            </select>
          </Field>
          <Field label="Öffnen um">
            <select
              value={p.value("end_hour") ?? 7}
              onChange={(e) => p.set("end_hour", Number(e.target.value))}
              className={INPUT}
            >
              {hours.map((h) => (
                <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Zeitzone" hint="Damit die Uhrzeiten zu eurem Tag passen.">
          <select
            value={p.value("timezone") ?? "Europe/Berlin"}
            onChange={(e) => p.set("timezone", e.target.value)}
            className={INPUT}
          >
            {["Europe/Berlin", "Europe/London", "Europe/Vienna", "Europe/Zurich",
              "America/New_York", "UTC"].map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </select>
        </Field>

        <Field label="Welche Kanäle" hint="Nur diese werden geschlossen.">
          <ChannelPicker
            guildId={guildId}
            value={(p.value("channels") || [])[0] || ""}
            onChange={(id) => {
              const current: string[] = p.value("channels") || [];
              if (!id) return;
              p.set("channels", current.includes(id) ? current : [...current, id]);
            }}
            placeholder="Kanal hinzufügen"
            channelTypes={["0", "5"]}
          />
          <div className="flex flex-wrap gap-2 pt-2">
            {(p.value("channels") || []).map((cid: string) => {
              const info = (p.data?.channels_info || []).find(
                (c: any) => c.id === cid
              );
              return (
                <span
                  key={cid}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#0d1b31] border border-slate-800 text-sm text-slate-300"
                >
                  #{info?.name || cid}
                  <button
                    onClick={() =>
                      p.set("channels",
                        (p.value("channels") || []).filter((c: string) => c !== cid))
                    }
                    className="text-slate-600 hover:text-red-400"
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        </Field>

        <div className="flex gap-3 flex-wrap">
          <button
            onClick={() => p.act(() => api.toggleNightmode(guildId, true))}
            disabled={p.busy}
            className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary disabled:opacity-40 transition-all"
          >
            <Lock className="h-4 w-4" /> Jetzt schließen
          </button>
          <button
            onClick={() => p.act(() => api.toggleNightmode(guildId, false))}
            disabled={p.busy}
            className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary disabled:opacity-40 transition-all"
          >
            <Check className="h-4 w-4" /> Jetzt öffnen
          </button>
        </div>

        <SaveBar
          count={p.dirty}
          busy={p.busy}
          onDiscard={() => p.setDraft({})}
          onSave={() => p.act(() => api.updateNightmode(guildId, p.draft))}
        />
      </Card>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Jail
 * ══════════════════════════════════════════════════════════════════ */

export function JailPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getJail(guildId), [guildId]);
  const p = usePanel(load);

  if (p.loading) return <Loading />;

  return (
    <section className="space-y-5">
      <Card
        icon={Lock}
        title="Isolation statt Bann"
        subtitle="Wer eingesperrt wird, verliert alle Rollen und sieht nur noch einen Kanal. Rückgängig zu machen, im Gegensatz zu einem Bann."
        onReload={p.reload}
      >
        {p.data?.problem && <Warn>{p.data.problem}</Warn>}

        {!p.data?.configured && (
          <div className="rounded-xl bg-primary/[0.06] border border-primary/25 p-4 space-y-3">
            <p className="text-[12px] text-slate-300 leading-relaxed">
              Noch nicht eingerichtet. Der Bot kann Rolle und Kanal anlegen und
              die Rolle in <b>allen</b> Kanälen sperren — von Hand heißt das,
              jeden einzelnen Kanal zu bearbeiten.
            </p>
            <button
              onClick={() =>
                p.act(
                  () => api.setupJail(guildId),
                  "Jail-Rolle und -Kanal anlegen und in allen Kanälen sperren?"
                )
              }
              disabled={p.busy}
              className="w-full py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
            >
              Automatisch einrichten
            </button>
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-5">
          <Field label="Jail-Rolle">
            <RolePicker
              guildId={guildId}
              value={p.value("jail_role")?.id || ""}
              onChange={(id) => p.set("jail_role", id)}
              placeholder="Rolle wählen"
            />
          </Field>
          <Field label="Jail-Kanal" hint="Der einzige Kanal, den Eingesperrte sehen.">
            <ChannelPicker
              guildId={guildId}
              value={p.value("jail_channel")?.id || ""}
              onChange={(id) => p.set("jail_channel", id)}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>
          <Field label="Mod-Rolle" hint="Wer einsperren darf.">
            <RolePicker
              guildId={guildId}
              value={p.value("mod_role")?.id || ""}
              onChange={(id) => p.set("mod_role", id)}
              placeholder="Rolle wählen"
            />
          </Field>
          <Field label="Protokoll-Kanal">
            <ChannelPicker
              guildId={guildId}
              value={p.value("log_channel")?.id || ""}
              onChange={(id) => p.set("log_channel", id)}
              placeholder="Kein Protokoll"
              channelTypes={["0", "5"]}
            />
          </Field>
        </div>

        <SaveBar
          count={p.dirty}
          busy={p.busy}
          onDiscard={() => p.setDraft({})}
          onSave={() =>
            p.act(() =>
              api.updateJail(guildId, {
                jail_role: p.draft.jail_role,
                jail_channel: p.draft.jail_channel,
                mod_role: p.draft.mod_role,
                log_channel: p.draft.log_channel,
              })
            )
          }
        />
      </Card>

      <div>
        <h3 className="font-black text-white flex items-center gap-2 mb-3">
          <Users className="h-5 w-5 text-slate-500" />
          Gerade eingesperrt
          <span className="text-xs font-normal text-slate-500">
            ({p.data?.inmates?.length || 0})
          </span>
        </h3>
        {!p.data?.inmates?.length ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
            Niemand.
          </p>
        ) : (
          <div className="space-y-2">
            {p.data.inmates.map((inmate: any) => (
              <div
                key={inmate.user_id}
                className="flex items-center gap-3 bg-[#10233f] border border-slate-800 rounded-2xl px-4 py-3"
              >
                {inmate.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={inmate.avatar} alt="" className="h-8 w-8 rounded-full shrink-0" />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className={cn(
                    "text-sm font-bold truncate",
                    inmate.left ? "text-slate-500 italic" : "text-white"
                  )}>
                    {inmate.name}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {inmate.reason || "kein Grund angegeben"}
                    {inmate.mod_name && ` · von ${inmate.mod_name}`}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Counting
 * ══════════════════════════════════════════════════════════════════ */

export function CountingPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getCounting(guildId), [guildId]);
  const p = usePanel(load);

  if (p.loading) return <Loading />;

  return (
    <section className="space-y-5">
      <Card
        icon={Calculator}
        title="Zähl-Spiel"
        subtitle="Alle zählen gemeinsam hoch. Wer sich vertut oder zweimal hintereinander schreibt, macht es kaputt."
        onReload={p.reload}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">{p.data?.current ?? 0}</p>
            <p className="text-[11px] text-slate-500">Aktueller Stand</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white flex items-center gap-1.5">
              <Trophy className="h-4 w-4 text-amber-400" />
              {p.data?.high_score ?? 0}
            </p>
            <p className="text-[11px] text-slate-500">Rekord</p>
          </div>
        </div>

        <InlineToggle
          checked={p.value("enabled")}
          onCheckedChange={(v: boolean) => p.set("enabled", v)}
          label="Zählen aktiv"
        />

        <Field label="Kanal">
          <ChannelPicker
            guildId={guildId}
            value={p.value("channel") || ""}
            onChange={(id) => p.set("channel", id)}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <Field label="Bei einem Fehler">
          <div className="grid grid-cols-2 gap-2">
            {[
              { id: "reset", label: "Zurück auf 0", desc: "Streng" },
              { id: "continue", label: "Weiterzählen", desc: "Entspannt" },
            ].map((o) => (
              <button
                key={o.id}
                onClick={() => p.set("mode", o.id)}
                className={cn(
                  "text-left rounded-2xl border p-4 transition-all",
                  (p.value("mode") || "reset") === o.id
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                )}
              >
                <p className="text-sm font-bold text-white">{o.label}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{o.desc}</p>
              </button>
            ))}
          </div>
        </Field>

        <button
          onClick={() =>
            p.act(
              () => api.resetCounting(guildId),
              "Zähler auf 0 setzen? Der Rekord bleibt erhalten."
            )
          }
          disabled={p.busy}
          className="w-full py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          Zähler zurücksetzen
        </button>

        <SaveBar
          count={p.dirty}
          busy={p.busy}
          onDiscard={() => p.setDraft({})}
          onSave={() => p.act(() => api.updateCounting(guildId, p.draft))}
        />
      </Card>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Notify
 * ══════════════════════════════════════════════════════════════════ */

export function NotifyPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getNotify(guildId), [guildId]);
  const p = usePanel(load);
  const [kind, setKind] = useState("youtube");
  const [roleId, setRoleId] = useState("");
  const [channelId, setChannelId] = useState("");

  if (p.loading) return <Loading />;

  return (
    <section className="space-y-5">
      <Card
        icon={Youtube}
        title="Benachrichtigungen"
        subtitle="Rolle anpingen, wenn ein neues Video oder ein Stream kommt."
        onReload={p.reload}
      >
        {p.data?.has_legacy && (
          <Warn>
            Einträge ohne Server-Zuordnung stammen aus einer älteren Version, in
            der die Einstellung für alle Server gemeinsam war. Lege sie neu an,
            damit sie nur noch hier gelten.
          </Warn>
        )}

        <div className="grid lg:grid-cols-[140px_1fr_1fr_auto] gap-3 items-end">
          <Field label="Typ">
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className={INPUT}
            >
              {(p.data?.types || []).map((t: string) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Rolle">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
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
          <button
            onClick={() =>
              p.act(async () => {
                const res = await api.setNotify(guildId, {
                  type: kind, role_id: roleId, channel_id: channelId,
                });
                setRoleId("");
                setChannelId("");
                return res;
              })
            }
            disabled={p.busy || !roleId || !channelId}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </Card>

      {!p.data?.entries?.length ? (
        <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
          Nichts eingerichtet.
        </p>
      ) : (
        <div className="space-y-2">
          {p.data.entries.map((entry: any) => (
            <div
              key={entry.type}
              className="flex items-center gap-3 bg-[#10233f] border border-slate-800 rounded-2xl px-4 py-3 flex-wrap"
            >
              <span className="px-2.5 py-1 rounded-lg bg-primary/15 text-primary text-xs font-black uppercase shrink-0">
                {entry.type}
              </span>
              <span className="text-sm text-slate-300 flex-1 min-w-0 truncate">
                @{entry.role.name || "gelöscht"} in #{entry.channel.name || "gelöscht"}
              </span>
              {entry.legacy && (
                <span className="text-[10px] font-black uppercase text-amber-400">
                  ohne Server
                </span>
              )}
              <button
                onClick={() => p.act(() => api.removeNotify(guildId, entry.type))}
                disabled={p.busy}
                className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all shrink-0"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Birthdays
 * ══════════════════════════════════════════════════════════════════ */

export function BirthdayPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getBirthdays(guildId), [guildId]);
  const p = usePanel(load);
  const [userId, setUserId] = useState("");
  const [date, setDate] = useState("");

  if (p.loading) return <Loading />;

  return (
    <section className="space-y-5">
      <Card
        icon={Cake}
        title="Geburtstage"
        subtitle="Der Bot gratuliert automatisch am richtigen Tag."
        onReload={p.reload}
      >
        <div className="grid lg:grid-cols-[1fr_160px_auto] gap-3 items-end">
          <Field label="Mitglied">
            <UserPicker
              guildId={guildId}
              value={userId}
              onChange={(id: string) => setUserId(id || "")}
              placeholder="Mitglied suchen"
            />
          </Field>
          <Field label="Datum" hint="TT.MM">
            <input
              value={date}
              onChange={(e) => setDate(e.target.value)}
              placeholder="15.03"
              className={INPUT}
            />
          </Field>
          <button
            onClick={() =>
              p.act(async () => {
                const res = await api.setBirthday(guildId, {
                  user_id: userId, date,
                });
                setUserId("");
                setDate("");
                return res;
              })
            }
            disabled={p.busy || !userId || !date.trim()}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </Card>

      {(p.data?.upcoming || []).length > 0 && (
        <Card icon={Clock} title="Als Nächstes">
          <div className="space-y-2">
            {p.data.upcoming.slice(0, 5).map((entry: any) => (
              <div
                key={entry.user_id}
                className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-2.5"
              >
                <Cake className="h-4 w-4 text-primary shrink-0" />
                <span className="text-sm text-white flex-1 min-w-0 truncate">
                  {entry.name}
                </span>
                <span className="text-[11px] text-slate-500 shrink-0">
                  {entry.in_days === 0
                    ? "heute!"
                    : entry.in_days === 1
                      ? "morgen"
                      : `in ${entry.in_days} Tagen`}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div>
        <h3 className="font-black text-white mb-3">
          Alle ({p.data?.total ?? 0})
        </h3>
        {!p.data?.entries?.length ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
            Noch nichts eingetragen.
          </p>
        ) : (
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {p.data.entries.map((entry: any) => (
              <div
                key={entry.user_id}
                className="flex items-center gap-3 bg-[#10233f] border border-slate-800 rounded-2xl px-4 py-3"
              >
                {entry.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={entry.avatar} alt="" className="h-8 w-8 rounded-full shrink-0" />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
                )}
                <span className={cn(
                  "text-sm font-bold flex-1 min-w-0 truncate",
                  entry.left ? "text-slate-500 italic" : "text-white"
                )}>
                  {entry.name}
                </span>
                <span className="text-[11px] text-slate-500 shrink-0">{entry.date}</span>
                <button
                  onClick={() => p.act(() => api.removeBirthday(guildId, entry.user_id))}
                  disabled={p.busy}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
