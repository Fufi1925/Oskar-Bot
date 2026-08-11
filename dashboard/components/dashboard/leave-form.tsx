"use client";

/**
 * Verabschiedung -- das Gegenstueck zur Begruessung.
 *
 * Bewusst nach demselben Muster wie `welcome-form.tsx`: gleiche Felder,
 * gleiche Platzhalter, gleiche Reihenfolge. Wer das eine bedienen kann,
 * kann auch das andere, ohne etwas Neues zu lernen.
 */

import React, { useCallback, useEffect, useState } from "react";
import { Image as ImageIcon, Loader2, LogOut, Type } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker } from "@/components/dashboard/pickers";

const INPUT =
  "w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500";

const PLACEHOLDERS: Array<[string, string]> = [
  ["{user}", "Erwähnung des Mitglieds"],
  ["{user.name}", "Name ohne Erwähnung"],
  ["{user.id}", "ID des Mitglieds"],
  ["{server}", "Name des Servers"],
  ["{membercount}", "Mitglieder nach dem Austritt"],
];

function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-black uppercase tracking-wider text-slate-400">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[11px] text-slate-500 italic">{hint}</span>}
    </label>
  );
}

function Toggle({
  checked, onChange,
}: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-12 h-6 rounded-full transition-colors shrink-0",
        checked ? "bg-emerald-500" : "bg-slate-700",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform",
          checked ? "translate-x-6" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export function LeaveForm({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      setConfig(await api.getLeave(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Einstellungen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!config) return;
    // Ohne Kanal passiert nichts -- das lieber hier sagen als den Nutzer
    // rätseln lassen, warum keine Verabschiedung kommt.
    if (config.enabled && !config.channel_id) {
      return toast.error("Bitte zuerst einen Kanal wählen.");
    }
    setSaving(true);
    try {
      const antwort = await api.updateLeave(guildId, config);
      setConfig({ ...config, ...antwort });
      toast.success("Gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-slate-600" />
      </div>
    );
  }
  if (!config) return null;

  const set = (patch: Record<string, any>) => setConfig({ ...config, ...patch });

  return (
    <div className="space-y-5">
      {/* ── An/Aus und Kanal ──────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-red-500/15 border border-red-500/25 grid place-items-center">
              <LogOut className="h-5 w-5 text-red-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">Verabschiedung</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Eine Nachricht, wenn jemand den Server verlässt.
              </p>
            </div>
          </div>
          <Toggle
            checked={!!config.enabled}
            onChange={(v) => set({ enabled: v })}
          />
        </div>

        <div className={cn("grid md:grid-cols-2 gap-5", !config.enabled && "opacity-40")}>
          <Field label="Kanal" hint="Dorthin geht die Verabschiedung.">
            <ChannelPicker
              guildId={guildId}
              value={config.channel_id || ""}
              onChange={(id) => set({ channel_id: id || null })}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>

          <Field
            label="Nach X Sekunden löschen"
            hint="0 heißt: die Nachricht bleibt stehen."
          >
            <input
              type="number"
              min={0}
              max={3600}
              value={config.auto_delete_duration || 0}
              onChange={(e) =>
                set({ auto_delete_duration: Math.max(0, Number(e.target.value) || 0) })
              }
              className={INPUT}
            />
          </Field>
        </div>
      </div>

      {/* ── Der Text ──────────────────────────────────────────── */}
      <div className={cn(
        "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card",
        !config.enabled && "opacity-40",
      )}>
        <div className="flex gap-3">
          <div className="shrink-0 h-10 w-10 rounded-2xl bg-slate-500/15 border border-slate-500/25 grid place-items-center">
            <Type className="h-5 w-5 text-slate-300" />
          </div>
          <div>
            <h3 className="font-bold text-white">Nachricht</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Leer lassen für den Standardtext.
            </p>
          </div>
        </div>

        <Field label="Text">
          <textarea
            rows={3}
            maxLength={2000}
            value={config.leave_message || ""}
            onChange={(e) => set({ leave_message: e.target.value })}
            placeholder="**{user.name}** hat den Server verlassen."
            className={INPUT}
          />
        </Field>

        <div>
          <p className="text-[11px] font-black uppercase tracking-wider text-slate-400 mb-2">
            Platzhalter
          </p>
          <div className="flex flex-wrap gap-1.5">
            {PLACEHOLDERS.map(([code, was]) => (
              <button
                key={code}
                type="button"
                title={was}
                onClick={() =>
                  set({ leave_message: `${config.leave_message || ""}${code}` })
                }
                className="text-[11px] font-mono px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors"
              >
                {code}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Das Bild ──────────────────────────────────────────── */}
      <div className={cn(
        "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card",
        !config.enabled && "opacity-40",
      )}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-amber-500/15 border border-amber-500/25 grid place-items-center">
              <ImageIcon className="h-5 w-5 text-amber-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">Bild mitschicken</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Der Bot zeichnet eine Karte in Rot — mit Profilbild, Name und
                verbleibender Mitgliederzahl.
              </p>
            </div>
          </div>
          <Toggle
            checked={config.card_enabled !== false}
            onChange={(v) => set({ card_enabled: v })}
          />
        </div>

        <div className={config.card_enabled === false ? "opacity-40" : ""}>
          <Field
            label="Eigenes Bild statt der gezeichneten Karte"
            hint="Leer lassen für die gezeichnete Karte. Direkter Link auf eine Bilddatei."
          >
            <input
              type="url"
              value={config.card_image_url || ""}
              disabled={config.card_enabled === false}
              onChange={(e) => set({ card_image_url: e.target.value })}
              placeholder="https://…/tschuess.png"
              className={INPUT}
            />
          </Field>
          {config.card_image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={config.card_image_url}
              alt=""
              className="mt-2 rounded-xl border border-slate-700 max-h-36 object-cover w-full"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = "none";
              }}
            />
          ) : null}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-blue-500/15 border border-blue-500/30 text-blue-200 font-bold text-sm hover:bg-blue-500/25 transition-colors disabled:opacity-40"
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Speichern
        </button>
      </div>
    </div>
  );
}
