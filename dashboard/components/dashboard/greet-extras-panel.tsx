"use client";

/**
 * Das Bild bei Begrüßung und Abschied.
 *
 * Drei Dinge, die es vorher nicht gab: ein Schalter für das
 * Willkommensbild (es ging immer mit), ein eigener Hintergrund statt
 * des gezeichneten Verlaufs, und derselbe Aufbau noch einmal für den
 * Abschied — den gab es überhaupt nicht.
 */

import React, { useCallback, useEffect, useState } from "react";
import { DoorOpen, Image as ImageIcon, Loader2, LogIn } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SwitchToggle } from "@/components/dashboard/form-elements";
import { ChannelPicker } from "@/components/dashboard/pickers";

interface Extras {
  welcome_image_enabled: boolean;
  welcome_image_url: string;
  leave_enabled: boolean;
  leave_channel_id: string | number;
  leave_message: string;
  leave_image_enabled: boolean;
  leave_image_url: string;
}

/** Dieselbe Regel wie im Bot (`utils/greet_extras.valid_image_url`). */
function isImageUrl(url: string) {
  const wert = (url || "").trim();
  if (!/^https:\/\/[^\s<>"']{5,500}$/i.test(wert)) return false;
  const pfad = wert.split("?")[0].split("#")[0].toLowerCase();
  return [".png", ".jpg", ".jpeg", ".gif", ".webp"].some((e) => pfad.endsWith(e));
}

/**
 * Der Schalter kommt aus form-elements.
 *
 * Hier stand eine eigene Kopie, und die hatte den Fehler, den
 * form-elements.tsx schon zweimal beschreibt: der Knopf war `absolute`
 * ohne `left` und rutschte deshalb über den rechten Rand der Bahn.
 * Eine vierte Kopie zu reparieren hätte den nächsten Fehler nur
 * vertagt.
 */
function Toggle({
  checked, onChange, disabled,
}: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <SwitchToggle checked={checked} onCheckedChange={onChange} disabled={disabled} />
  );
}

/** Adressfeld mit Prüfung beim Verlassen und kleiner Vorschau. */
function ImageField({
  value, onCommit, disabled, hint,
}: {
  value: string;
  onCommit: (next: string) => void;
  disabled?: boolean;
  hint: string;
}) {
  return (
    <div className={cn("space-y-2", disabled && "opacity-40")}>
      <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
        Eigenes Hintergrundbild
      </label>
      <input
        key={value}
        defaultValue={value}
        disabled={disabled}
        onBlur={(e) => {
          const next = e.target.value.trim();
          if (next === value) return;
          if (next && !isImageUrl(next)) {
            toast.error(
              "Das muss eine https-Adresse sein, die auf .png, .jpg, .gif oder .webp endet.",
            );
            e.target.value = value;
            return;
          }
          onCommit(next);
        }}
        placeholder="https://…/hintergrund.png  (leer = gezeichneter Hintergrund)"
        className="w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500"
      />
      <p className="text-[11px] text-slate-500 italic">{hint}</p>
      {value && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={value}
          alt="Vorschau des Hintergrundbildes"
          className="max-h-32 rounded-xl border border-slate-700"
        />
      )}
    </div>
  );
}

/**
 * Beide Teile teilen sich eine Route und einen Datensatz, aber nicht
 * mehr dieselbe Seite: der Abschied hat inzwischen einen eigenen
 * Reiter. `show` entscheidet, welcher Teil gezeichnet wird -- getrennte
 * Komponenten haetten denselben Ladevorgang zweimal gemacht und
 * koennten beim Speichern auseinanderlaufen.
 */
export function GreetExtrasPanel({
  guildId,
  show = "both",
}: {
  guildId: string;
  show?: "welcome" | "leave" | "both";
}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState<Extras | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.getGreetExtras(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Einstellungen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  const patch = async (aenderung: Partial<Extras>) => {
    if (!data) return;
    const vorher = data;
    setData({ ...data, ...aenderung });
    setSaving(true);
    try {
      const antwort = await api.saveGreetExtras(guildId, aenderung);
      if (antwort) {
        const { status, guild_id, ...rest } = antwort;
        setData(rest as Extras);
      }
    } catch (err: any) {
      setData(vorher);
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
  if (!data) return null;

  return (
    <div className="space-y-5">
      {/* ── Willkommensbild ───────────────────────────────────── */}
      {show !== "leave" && (
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-emerald-500/15 border border-emerald-500/25 grid place-items-center">
              <ImageIcon className="h-5 w-5 text-emerald-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">Bild bei der Begrüßung</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Die Karte mit Profilbild, Name und Mitgliedsnummer. Aus heißt:
                nur die Textnachricht.
              </p>
            </div>
          </div>
          <Toggle
            checked={data.welcome_image_enabled}
            onChange={(v) => patch({ welcome_image_enabled: v })}
            disabled={saving}
          />
        </div>

        <ImageField
          value={data.welcome_image_url}
          disabled={!data.welcome_image_enabled || saving}
          onCommit={(next) => patch({ welcome_image_url: next })}
          hint="Wird zugeschnitten und abgedunkelt, damit die Schrift lesbar bleibt. Leer lassen für den gezeichneten Hintergrund."
        />
      </div>
      )}

      {/* ── Abschied ──────────────────────────────────────────── */}
      {show !== "welcome" && (
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-rose-500/15 border border-rose-500/25 grid place-items-center">
              <DoorOpen className="h-5 w-5 text-rose-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">Abschiedsnachricht</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Wenn jemand den Server verlässt. Funktioniert genau wie die
                Begrüßung.
              </p>
            </div>
          </div>
          <Toggle
            checked={data.leave_enabled}
            onChange={(v) => patch({ leave_enabled: v })}
            disabled={saving}
          />
        </div>

        <div className={cn("space-y-5", !data.leave_enabled && "opacity-40")}>
          <div className="space-y-2">
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
              Kanal
            </label>
            <ChannelPicker
              guildId={guildId}
              value={String(data.leave_channel_id || "")}
              onChange={(id) => patch({ leave_channel_id: id || 0 })}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
              Nachricht
            </label>
            <textarea
              key={data.leave_message}
              defaultValue={data.leave_message}
              disabled={!data.leave_enabled || saving}
              rows={2}
              maxLength={2000}
              onBlur={(e) => {
                if (e.target.value === data.leave_message) return;
                patch({ leave_message: e.target.value });
              }}
              placeholder="**{user.display}** hat den Server verlassen."
              className="w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500 resize-y"
            />
            <p className="text-[11px] text-slate-500">
              Platzhalter:{" "}
              {["{user}", "{user.name}", "{user.display}", "{server}", "{count}"].map(
                (p) => (
                  <code
                    key={p}
                    className="mx-0.5 px-1.5 py-0.5 rounded bg-slate-800 text-purple-300"
                  >
                    {p}
                  </code>
                ),
              )}
            </p>
          </div>

          <div className="flex items-start justify-between gap-4 pt-1">
            <div>
              <p className="text-sm font-bold text-slate-200">Bild beim Abschied</p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Dieselbe Karte, mit „Tschüss“ statt „Willkommen“.
              </p>
            </div>
            <Toggle
              checked={data.leave_image_enabled}
              onChange={(v) => patch({ leave_image_enabled: v })}
              disabled={!data.leave_enabled || saving}
            />
          </div>

          <ImageField
            value={data.leave_image_url}
            disabled={!data.leave_enabled || !data.leave_image_enabled || saving}
            onCommit={(next) => patch({ leave_image_url: next })}
            hint="Eigener Hintergrund nur für den Abschied."
          />
        </div>
      </div>
      )}
    </div>
  );
}
