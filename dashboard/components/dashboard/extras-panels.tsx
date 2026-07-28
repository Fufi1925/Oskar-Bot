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
import {
  Loading, StickySaveBar, usePanel, useSaveGuard,
} from "@/components/dashboard/save-bar";

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

/* ══════════════════════════════════════════════════════════════════ *
 * Booster
 * ══════════════════════════════════════════════════════════════════ */

export function BoosterPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getBooster(guildId), [guildId]);
  const p = usePanel(load);
  // Before the early return below -- a hook may not be conditional.
  const guard = useSaveGuard(p.dirty, "booster-save-bar");

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

      <StickySaveBar
        id="booster-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
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
  const guard = useSaveGuard(p.dirty, "nightmode-save-bar");

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

      </Card>

      <StickySaveBar
        id="nightmode-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() => p.act(() => api.updateNightmode(guildId, p.draft))}
      />
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Jail
 * ══════════════════════════════════════════════════════════════════ */

export function JailPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getJail(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "jail-save-bar");

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

      <StickySaveBar
        id="jail-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
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
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Counting
 * ══════════════════════════════════════════════════════════════════ */

export function CountingPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getCounting(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "counting-save-bar");
  const [setTo, setSetTo] = useState("");

  if (p.loading) return <Loading />;

  const mode = p.value("mode") || "reset";
  // null means "follow the shared setting" — the selector shows that as
  // its own option rather than silently picking one.
  const wrongMode = p.value("wrong_number_mode") ?? null;
  const doubleMode = p.value("double_post_mode") ?? null;
  const warnings: string[] = p.data?.warnings || [];

  return (
    <section className="space-y-5">
      {warnings.length > 0 && (
        <Warn>
          <span className="font-bold">Das Spiel läuft nicht rund:</span>
          <br />
          {warnings.map((w, i) => (
            <span key={i}>
              • {w}
              <br />
            </span>
          ))}
        </Warn>
      )}

      <Card
        icon={Calculator}
        title="Counting"
        subtitle="Alle zählen gemeinsam hoch — eine Zahl nach der anderen."
        onReload={p.reload}
      >
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-2xl font-black text-white tabular-nums">
              {p.data?.current ?? 0}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Aktueller Stand</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-2xl font-black text-primary tabular-nums">
              {p.data?.next_number ?? 1}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Als Nächstes</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-2xl font-black text-amber-400 flex items-center gap-1.5 tabular-nums">
              <Trophy className="h-4 w-4 shrink-0" />
              {p.data?.high_score ?? 0}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Rekord</p>
          </div>
        </div>

        {p.data?.last_user_name && (
          <div className="flex items-center gap-2.5 rounded-xl bg-[#0d1b31] border border-slate-800 px-4 py-2.5">
            {p.data?.last_user_avatar && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={p.data.last_user_avatar}
                alt=""
                className="h-6 w-6 rounded-full"
              />
            )}
            <p className="text-[12px] text-slate-400">
              Zuletzt gezählt von{" "}
              <span className="text-white font-bold">{p.data.last_user_name}</span>
            </p>
          </div>
        )}

        <InlineToggle
          checked={p.value("enabled")}
          onCheckedChange={(v: boolean) => p.set("enabled", v)}
          label="Zählen aktiv"
        />

        <Field
          label="Kanal"
          hint="Nur in diesem Kanal wird gezählt. Der Bot braucht dort Schreibrechte, „Nachrichten verwalten“ und „Reaktionen hinzufügen“."
        >
          <ChannelPicker
            guildId={guildId}
            value={p.value("channel") || ""}
            onChange={(id) => p.set("channel", id)}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

      </Card>

      <Card
        icon={Users}
        title="Regeln"
        subtitle="Wie streng das Spiel sein soll."
      >
        <InlineToggle
          checked={p.value("require_alternate")}
          onCheckedChange={(v: boolean) => p.set("require_alternate", v)}
          label="Immer abwechseln"
          hint="Wer gerade gezählt hat, muss warten bis jemand anders dran war. Verhindert, dass eine Person allein durchzählt."
        />

        <Field
          label="Bei einem Fehler"
          hint="Gilt für alle Regelbrüche, solange unten nichts Eigenes eingestellt ist."
        >
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
                  mode === o.id
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

        <details className="group rounded-2xl bg-[#0d1b31] border border-slate-800 overflow-hidden">
          <summary className="cursor-pointer list-none px-4 py-3 flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-widest text-slate-400">
              Pro Fehlerart einstellen
            </span>
            <Plus className="h-4 w-4 text-slate-500 group-open:rotate-45 transition-transform" />
          </summary>
          <div className="px-4 pb-4 space-y-4">
            {[
              {
                key: "wrong_number_mode",
                value: wrongMode,
                label: "Falsche Zahl",
                hint: "Jemand schreibt eine Zahl, die nicht an der Reihe ist.",
              },
              {
                key: "double_post_mode",
                value: doubleMode,
                label: "Zweimal hintereinander",
                hint: "Nur wichtig, wenn „Immer abwechseln“ an ist.",
              },
            ].map((row) => (
              <Field key={row.key} label={row.label} hint={row.hint}>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: null, label: "Wie oben" },
                    { id: "reset", label: "Auf 0" },
                    { id: "continue", label: "Weiter" },
                  ].map((o) => (
                    <button
                      key={String(o.id)}
                      onClick={() => p.set(row.key, o.id)}
                      className={cn(
                        "rounded-xl border px-3 py-2.5 text-xs font-bold transition-all",
                        row.value === o.id
                          ? "bg-primary/10 border-primary/40 text-white"
                          : "bg-[#0a1628] border-slate-800 text-slate-400 hover:border-slate-700"
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </Field>
            ))}
          </div>
        </details>
      </Card>

      <Card
        icon={Hash}
        title="Kanal aufräumen"
        subtitle="Was mit Nachrichten passiert, die keine gültige Zahl sind."
      >
        <InlineToggle
          checked={p.value("allow_chat")}
          onCheckedChange={(v: boolean) => p.set("allow_chat", v)}
          label="Normalen Text stehen lassen"
          hint="An: „gg“ oder „nice“ bleiben stehen und brechen die Kette nicht. Aus: alles außer Zahlen wird gelöscht. Bot-Befehle bleiben in beiden Fällen unangetastet."
        />

        <InlineToggle
          checked={p.value("delete_wrong")}
          onCheckedChange={(v: boolean) => p.set("delete_wrong", v)}
          label="Falsche Zahlen löschen"
          hint="Aus: die falsche Zahl bleibt stehen, der Bot schreibt nur einen Hinweis."
        />

        <InlineToggle
          checked={p.value("react_success")}
          onCheckedChange={(v: boolean) => p.set("react_success", v)}
          label="Haken bei richtiger Zahl"
        />

        {p.value("react_success") && (
          <Field
            label="Eigenes Emoji"
            hint="Leer lassen für den Standard-Haken. Eigene Emojis nur von Servern, auf denen der Bot ist — sonst nimmt er wieder den Haken."
          >
            <input
              className={INPUT}
              value={p.value("success_emoji") ?? ""}
              onChange={(e) => p.set("success_emoji", e.target.value)}
              placeholder="z.B. ✅ oder <:name:123456789>"
            />
          </Field>
        )}

        <Field
          label="Meilenstein alle"
          hint="Der Bot meldet sich bei jedem Vielfachen. 0 schaltet die Meldungen ab."
        >
          <input
            type="number"
            min={0}
            max={10000}
            className={INPUT}
            value={p.value("milestone_every") ?? 100}
            onChange={(e) => p.set("milestone_every", Number(e.target.value))}
          />
        </Field>

      </Card>

      <Card
        icon={Trophy}
        title="Zähler verwalten"
        subtitle="Stand von Hand setzen oder das Spiel neu starten."
      >
        <Field
          label="Stand setzen"
          hint="Nützlich, wenn ihr woanders weitergezählt habt. Die nächste erwartete Zahl ist dann eins höher."
        >
          <div className="flex gap-2">
            <input
              type="number"
              min={0}
              className={INPUT}
              value={setTo}
              onChange={(e) => setSetTo(e.target.value)}
              placeholder={String(p.data?.current ?? 0)}
            />
            <button
              onClick={async () => {
                const value = Number(setTo);
                if (!setTo.trim() || Number.isNaN(value) || value < 0) {
                  toast.error("Bitte eine Zahl ab 0 eingeben.");
                  return;
                }
                await p.act(() =>
                  api.updateCounting(guildId, { current: value })
                );
                setSetTo("");
              }}
              disabled={p.busy}
              className="px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shrink-0 hover:brightness-110 disabled:opacity-40 transition-all"
            >
              Setzen
            </button>
          </div>
        </Field>

        <div className="grid sm:grid-cols-2 gap-2">
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
          <button
            onClick={() =>
              p.act(
                () => api.resetCounting(guildId, false),
                "Zähler UND Rekord löschen? Das lässt sich nicht rückgängig machen."
              )
            }
            disabled={p.busy}
            className="w-full py-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-xs font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
          >
            Auch Rekord löschen
          </button>
        </div>

        <button
          onClick={() => p.act(() => api.announceCounting(guildId))}
          disabled={p.busy || !p.data?.channel}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          <Send className="h-3.5 w-3.5" />
          Regeln in den Kanal posten
        </button>
      </Card>

      <StickySaveBar
        id="counting-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() => p.act(() => api.updateCounting(guildId, p.draft))}
      />
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Notify
 * ══════════════════════════════════════════════════════════════════ */

/**
 * Live notifications.
 *
 * The tab used to say "new video or stream" and offered a free-form
 * add-a-row form. Both were misleading:
 *
 *   * Nothing in the bot polls YouTube or Twitch. What it watches is the
 *     **Discord streaming status** of members of this server -- so an
 *     upload by somebody who is not in the server is never seen. People
 *     set this up expecting an upload feed and waited for nothing.
 *   * There are exactly two platforms, and one row each. A generic
 *     "add" form implied you could have several.
 *
 * Now: one card per platform, saying what it does and what it cannot do,
 * with a test button so you do not have to wait for somebody to go live
 * to find out whether the channel permissions are right.
 */
export function NotifyPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getNotify(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "notify-save-bar");

  if (p.loading) return <Loading />;

  const platforms: any[] = p.data?.platforms || [];
  const live: any[] = p.data?.live_now || [];
  const draft = p.draft.platforms || {};

  const change = (key: string, patch: any) =>
    p.set("platforms", { ...draft, [key]: { ...(draft[key] || {}), ...patch } });

  const save = () =>
    p.act(async () => {
      let last: any = null;
      for (const [key, patch] of Object.entries<any>(draft)) {
        const base = platforms.find((x) => x.key === key);
        const roleId = patch.role ?? base?.role?.id ?? "";
        const channelId = patch.channel ?? base?.channel?.id ?? "";
        if (!roleId || !channelId) {
          throw new Error(
            `Für ${base?.label ?? key} fehlt noch Rolle oder Kanal.`
          );
        }
        last = await api.setNotify(guildId, {
          type: key,
          role_id: String(roleId),
          channel_id: String(channelId),
        });
      }
      return last;
    });

  return (
    <section className="space-y-5">
      {(p.data?.warnings || []).length > 0 && (
        <Warn>
          <span className="font-bold">Das läuft so nicht rund:</span>
          <br />
          {p.data.warnings.map((w: string, i: number) => (
            <span key={i}>
              • {w}
              <br />
            </span>
          ))}
        </Warn>
      )}

      <Card
        icon={Youtube}
        title="Live-Benachrichtigungen"
        subtitle="Pingt eine Rolle, sobald jemand von diesem Server einen Stream in seinem Discord-Status hat."
        onReload={p.reload}
      >
        {/* Said plainly, because the old wording caused the confusion. */}
        <div className="rounded-xl bg-white/[0.03] border border-white/10 p-4 space-y-2">
          <p className="text-[12px] text-slate-300 leading-relaxed">
            <b className="text-white">Was das ist:</b> Der Bot sieht, wenn ein
            Mitglied dieses Servers in Discord als &bdquo;Streamt&ldquo;
            angezeigt wird, und pingt dann die eingestellte Rolle.
          </p>
          <p className="text-[12px] text-slate-400 leading-relaxed">
            <b className="text-slate-200">Was das nicht ist:</b> Kein
            YouTube-Abo. Neue Videos werden nicht bemerkt, und wer nicht auf
            diesem Server ist oder nicht über Discord streamt, löst nichts aus.
          </p>
        </div>

        {!p.data?.presence_intent && (
          <Warn>
            Dem Bot fehlt die Berechtigung, den Online-Status von Mitgliedern
            zu sehen (Presence Intent). Ohne die merkt er nie, dass jemand live
            geht.
          </Warn>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {p.data?.active_count ?? 0} / {platforms.length}
            </p>
            <p className="text-[11px] text-slate-500">Eingerichtet</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">{live.length}</p>
            <p className="text-[11px] text-slate-500">Gerade live</p>
          </div>
        </div>

        {live.length > 0 && (
          <div className="space-y-2">
            <p className="text-[11px] font-black uppercase tracking-widest text-slate-600">
              Streamt gerade
            </p>
            {live.map((person) => (
              <div
                key={person.id}
                className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5"
              >
                {person.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={person.avatar} alt="" className="h-7 w-7 rounded-full shrink-0" />
                ) : (
                  <div className="h-7 w-7 rounded-full bg-slate-800 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{person.name}</p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {person.title || "ohne Titel"}
                  </p>
                </div>
                <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 shrink-0">
                  {person.platform || "andere"}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {platforms.map((entry) => {
        const roleValue =
          draft[entry.key]?.role ?? entry.role?.id ?? "";
        const channelValue =
          draft[entry.key]?.channel ?? entry.channel?.id ?? "";
        const saved = entry.configured;
        return (
          <Card
            key={entry.key}
            icon={Youtube}
            title={entry.label}
            subtitle={
              saved
                ? "Eingerichtet."
                : "Noch nicht eingerichtet — Rolle und Kanal wählen."
            }
          >
            {entry.legacy && (
              <Warn>
                Diese Einstellung stammt aus einer alten Version, in der alle
                Server dieselbe benutzt haben. Sie wirkt nicht mehr — bitte
                unten neu setzen und speichern.
              </Warn>
            )}

            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Rolle, die gepingt wird">
                <RolePicker
                  guildId={guildId}
                  value={roleValue}
                  onChange={(id) => change(entry.key, { role: id || "" })}
                  placeholder="Rolle wählen"
                />
              </Field>
              <Field label="Kanal für die Meldung">
                <ChannelPicker
                  guildId={guildId}
                  value={channelValue}
                  onChange={(id) => change(entry.key, { channel: id || "" })}
                  placeholder="Kanal wählen"
                  channelTypes={["0", "5"]}
                />
              </Field>
            </div>

            {saved && !draft[entry.key] && (
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={() => p.act(() => api.testNotify(guildId, entry.key))}
                  disabled={p.busy}
                  className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-white disabled:opacity-40 transition-all"
                >
                  <Send className="h-3.5 w-3.5" />
                  Testmeldung posten
                </button>
                <button
                  onClick={() =>
                    p.act(
                      () => api.removeNotify(guildId, entry.key),
                      `${entry.label}-Benachrichtigung entfernen?`
                    )
                  }
                  disabled={p.busy}
                  className="px-5 py-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-xs font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
                >
                  Entfernen
                </button>
              </div>
            )}

            {saved && (
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Die Testmeldung pingt niemanden — sie zeigt nur, ob der Bot in
                den Kanal schreiben darf.
              </p>
            )}
          </Card>
        );
      })}

      <StickySaveBar
        id="notify-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={save}
      />
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
