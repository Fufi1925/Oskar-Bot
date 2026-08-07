"use client";

/**
 * The private message new members receive.
 *
 * The old page had one textarea. It also could not show the thing that
 * mattered most: the feature used to switch itself off after every
 * restart, because `joindm enable` registered a listener at runtime
 * instead of storing a flag. The page showed the configured text either
 * way, so there was no way to tell.
 *
 * The counters here answer that directly — if "verschickt" stays at zero
 * while people are joining, something is wrong.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Check, Clock, Eye, Loader2, Mail, MailX, Save, Send,
  Shield, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { EmojiText } from "@/components/dashboard/emoji-field";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

const SAMPLE: Record<string, string> = {
  "{user}": "@Alex",
  "{user_name}": "Alex",
  "{user_id}": "123456789012345678",
  "{server}": "dein Server",
  "{membercount}": "1.204",
  "{owner}": "DerChef",
};

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

function Stat({ icon: Icon, label, value, tone }: any) {
  return (
    <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
      <Icon className={cn("h-4 w-4 mb-1.5", tone || "text-primary")} />
      <p className="text-lg font-black text-white">{value}</p>
      <p className="text-[11px] text-slate-500">{label}</p>
    </div>
  );
}

export function JoinDMPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});

  const load = useCallback(async () => {
    try {
      setData(await api.getJoinDM(guildId));
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
  const guard = useSaveGuard(dirtyCount, "joindm-save-bar");

  const save = async (extra: Record<string, any> = {}) => {
    const payload = { ...draft, ...extra };
    if (!Object.keys(payload).length) return;
    setBusy(true);
    try {
      const res = await api.updateJoinDM(guildId, payload);
      toast.success(res?.result || "Gespeichert.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      // Send the current draft so nobody has to save first.
      const res = await api.testJoinDM(guildId, draft);
      toast.success(res?.result || "Geschickt.");
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const preview = useMemo(() => {
    const fill = (text: string) => {
      let out = String(text || "");
      for (const [token, sample] of Object.entries(SAMPLE)) {
        out = out.split(token).join(sample);
      }
      return out;
    };
    return {
      title: fill(("title" in draft ? draft.title : data?.title) || ""),
      message: fill(("message" in draft ? draft.message : data?.message) || ""),
      footer: fill(("footer" in draft ? draft.footer : data?.footer) || ""),
    };
  }, [draft, data]);

  const colourHex = useMemo(() => {
    const raw = "colour" in draft ? draft.colour : data?.colour;
    if (typeof raw === "number") return `#${raw.toString(16).padStart(6, "0")}`;
    return data?.colour_hex || "#5865f2";
  }, [draft, data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const hasMessage = String(value("message") || "").trim().length > 0;

  return (
    <section className="grid xl:grid-cols-5 gap-6">
      <div className="xl:col-span-3 space-y-5">
        {/* ── Status ─────────────────────────────────── */}
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <div className={cn(
                "h-11 w-11 rounded-2xl grid place-items-center shrink-0",
                value("enabled") ? "bg-emerald-500/15" : "bg-slate-700/40"
              )}>
                <Mail className={cn(
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
                    ? "Neue Mitglieder bekommen eine private Nachricht."
                    : "Es wird gerade nichts verschickt."}
                </p>
              </div>
            </div>

            <button
              onClick={() => save({ enabled: !value("enabled") })}
              disabled={busy || (!value("enabled") && !hasMessage)}
              title={
                !value("enabled") && !hasMessage
                  ? "Erst eine Nachricht eintragen"
                  : undefined
              }
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

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat icon={Send} label="Verschickt" value={data?.sent_total ?? 0} />
            <Stat
              icon={MailX}
              label="DMs waren zu"
              value={data?.failed_total ?? 0}
              tone="text-amber-400"
            />
            <Stat
              icon={Clock}
              label="Zuletzt"
              value={
                data?.last_sent
                  ? new Date(data.last_sent * 1000).toLocaleDateString("de-DE")
                  : "—"
              }
            />
          </div>

          {(data?.failed_total ?? 0) > 0 && (
            <p className="text-[11px] text-slate-600 leading-relaxed">
              &bdquo;DMs waren zu&ldquo; heißt: die Person erlaubt keine privaten Nachrichten
              von Server-Mitgliedern. Das lässt sich nicht umgehen und ist kein
              Fehler des Bots.
            </p>
          )}
        </div>

        {/* ── Content ────────────────────────────────── */}
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Die Nachricht
          </p>

          <div className="grid md:grid-cols-2 gap-5">
            <Field label="Überschrift">
              <EmojiText
                value={value("title") ?? ""}
                onChange={(next) => set("title", next)}
                limit={256}
                placeholder="Willkommen!"
                onLimitReached={(cap) =>
                  toast.error(`Eine Überschrift darf höchstens ${cap} Zeichen haben.`)
                }
              />
            </Field>
            <Field label="Farbe">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={colourHex}
                  onChange={(e) =>
                    set("colour", parseInt(e.target.value.slice(1), 16))
                  }
                  className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1 shrink-0"
                />
                <input
                  value={colourHex}
                  onChange={(e) => {
                    const v = e.target.value.replace("#", "");
                    if (/^[0-9a-f]{6}$/i.test(v)) set("colour", parseInt(v, 16));
                  }}
                  className={cn(INPUT, "font-mono")}
                />
              </div>
            </Field>
          </div>

          <Field label="Text">
            <EmojiText
              value={value("message") ?? ""}
              onChange={(next) => set("message", next)}
              rows={5}
              limit={2000}
              showCount
              placeholder="Hey {user_name}, schön dass du da bist!"
              onLimitReached={(cap) =>
                toast.error(`Der Text darf höchstens ${cap} Zeichen haben.`)
              }
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {Object.keys(data?.placeholders || {}).map((key) => (
                <button
                  key={key}
                  title={data.placeholders[key]}
                  onClick={() =>
                    set("message", `${value("message") ?? ""}{${key}}`)
                  }
                  className="px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
                >
                  {`{${key}}`}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid md:grid-cols-2 gap-5">
            <Field label="Fußzeile" hint="Optional, kleiner Text darunter.">
              <EmojiText
                value={value("footer") ?? ""}
                onChange={(next) => set("footer", next)}
                limit={2048}
                onLimitReached={(cap) =>
                  toast.error(`Die Fußzeile darf höchstens ${cap} Zeichen haben.`)
                }
              />
            </Field>
            <Field label="Bild (URL)" hint="Muss mit https:// anfangen.">
              <input
                value={value("image_url") ?? ""}
                onChange={(e) => set("image_url", e.target.value)}
                placeholder="https://…"
                className={INPUT}
              />
            </Field>
          </div>

          <div className="border-t border-slate-800 pt-5 space-y-5">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Knopf (optional)
            </p>
            <div className="grid md:grid-cols-2 gap-5">
              <Field label="Beschriftung">
                <EmojiText
                  value={value("button_label") ?? ""}
                  onChange={(next) => set("button_label", next)}
                  limit={80}
                  placeholder="Zu den Regeln"
                  onLimitReached={(cap) =>
                    toast.error(`Eine Knopfbeschriftung darf höchstens ${cap} Zeichen haben.`)
                  }
                />
              </Field>
              <Field label="Link" hint="Ein Knopf ohne Link wird nicht angezeigt.">
                <input
                  value={value("button_url") ?? ""}
                  onChange={(e) => set("button_url", e.target.value)}
                  placeholder="https://…"
                  className={INPUT}
                />
              </Field>
            </div>
          </div>
        </div>

        {/* ── Guards ─────────────────────────────────── */}
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Wann verschickt wird
            </p>
            <p className="text-[11px] text-slate-600 mt-1.5 leading-relaxed">
              Bei einem Raid Hunderte DMs zu verschicken ist der schnellste Weg,
              den Bot bei Discord auffällig zu machen.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <Field
              label="Verzögerung (Sekunden)"
              hint="0 = sofort. Ein paar Sekunden wirken weniger maschinell."
            >
              <input
                type="number"
                min={0}
                value={value("delay_seconds") ?? 0}
                onChange={(e) => set("delay_seconds", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>
            <Field
              label="Account mindestens X Tage alt"
              hint="0 = jeder. Hält frische Wegwerf-Accounts draußen."
            >
              <input
                type="number"
                min={0}
                value={value("min_account_days") ?? 0}
                onChange={(e) => set("min_account_days", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>
          </div>
        </div>
      </div>

      {/* ── Preview ──────────────────────────────────── */}
      <div className="xl:col-span-2 space-y-5">
        <div className="xl:sticky xl:top-6 space-y-5">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
              <Eye className="h-3.5 w-3.5" /> Vorschau
            </p>

            <div className="rounded-2xl bg-[#313338] p-4">
              <div
                className="rounded border-l-4 bg-[#2b2d31] p-3.5 space-y-2"
                style={{ borderLeftColor: colourHex }}
              >
                <p className="text-[15px] font-bold text-white break-words">
                  {preview.title || "Willkommen"}
                </p>
                <p className="text-sm text-[#dbdee1] whitespace-pre-line break-words">
                  {preview.message || (
                    <span className="italic text-slate-600">Noch kein Text.</span>
                  )}
                </p>
                {preview.footer && (
                  <p className="text-[11px] text-[#949ba4]">{preview.footer}</p>
                )}
                {value("button_label") && value("button_url") && (
                  <span className="inline-block px-3 py-1.5 rounded bg-[#4e5058] text-white text-[13px] font-medium">
                    {value("button_label")}
                  </span>
                )}
              </div>
            </div>

            <button
              onClick={test}
              disabled={busy || !hasMessage}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              An mich selbst schicken
            </button>
            <p className="text-[11px] text-slate-600 text-center leading-relaxed">
              Schickt den aktuellen Stand — auch ungespeichert. Kommt nichts an,
              sind deine eigenen DMs zu.
            </p>
          </div>

        </div>
      </div>

      <StickySaveBar
        id="joindm-save-bar"
        count={dirtyCount}
        busy={busy}
        shake={guard.shake}
        onDiscard={() => setDraft({})}
        onSave={() => save()}
      />
    </section>
  );
}
