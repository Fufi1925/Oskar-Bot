"use client";

/**
 * DM-Benachrichtigungen fuer Tickets.
 *
 * Zwei Richtungen, die unabhaengig voneinander an- und ausgehen:
 * der Ersteller wird benachrichtigt, wenn das Team geantwortet hat,
 * und das Team, wenn der Ersteller wartet.
 *
 * Der Kasten "Wann der Bot eine DM schickt" ist Absicht. Ein System
 * mit sechs Bedingungen, das mal schreibt und mal nicht, sieht von
 * aussen kaputt aus, solange die Regeln nirgends stehen.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  BellRing, Clock, Loader2, MessageSquare, Moon, ShieldQuestion, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SwitchToggle } from "@/components/dashboard/form-elements";

interface Settings {
  user_dm_enabled: boolean;
  staff_dm_enabled: boolean;
  user_delay: number;
  staff_delay: number;
  user_cooldown: number;
  staff_cooldown: number;
  quiet_enabled: boolean;
  quiet_start: number;
  quiet_end: number;
}

/** Sekunden zu einem Text, den man vorlesen kann. */
function humanize(seconds: number) {
  if (seconds < 60) return `${seconds} Sekunden`;
  if (seconds < 3600) {
    const m = Math.round(seconds / 60);
    return `${m} ${m === 1 ? "Minute" : "Minuten"}`;
  }
  const h = seconds / 3600;
  const gerundet = Math.round(h * 10) / 10;
  return `${gerundet} ${gerundet === 1 ? "Stunde" : "Stunden"}`;
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

/** Ein Zahlenfeld mit Einheit und lesbarer Anzeige darunter. */
function TimeField({
  label, hint, value, unit, min, max, onChange, disabled,
}: {
  label: string; hint: string; value: number; unit: "min" | "h";
  min: number; max: number; onChange: (seconds: number) => void; disabled?: boolean;
}) {
  const teiler = unit === "min" ? 60 : 3600;
  const angezeigt = Math.round((value / teiler) * 10) / 10;

  return (
    <div className={cn("space-y-1.5", disabled && "opacity-40")}>
      <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          min={Math.ceil(min / teiler)}
          max={Math.floor(max / teiler)}
          step={unit === "min" ? 1 : 0.5}
          value={angezeigt}
          disabled={disabled}
          onChange={(e) => {
            const roh = parseFloat(e.target.value);
            if (Number.isNaN(roh)) return;
            const sek = Math.round(roh * teiler);
            onChange(Math.max(min, Math.min(max, sek)));
          }}
          className="w-24 bg-slate-900/60 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
        />
        <span className="text-xs text-slate-500 font-bold">
          {unit === "min" ? "Minuten" : "Stunden"}
        </span>
      </div>
      <p className="text-[11px] text-slate-500 italic">{hint}</p>
    </div>
  );
}

/** Eine Regelzeile im Erklaerkasten. */
function Rule({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 items-start">
      <span className="shrink-0 w-5 h-5 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-300 text-[10px] font-black grid place-items-center mt-0.5">
        {n}
      </span>
      <p className="text-[12.5px] text-slate-400 leading-relaxed">{children}</p>
    </div>
  );
}

export function TicketNotifyPanel({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [pending, setPending] = useState({ user: 0, staff: 0 });

  const load = useCallback(async () => {
    try {
      const data = await api.getTicketNotify(guildId);
      setSettings(data.settings);
      setPending(data.pending || { user: 0, staff: 0 });
    } catch (err: any) {
      toast.error(err?.message || "Einstellungen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Sofort speichern, ohne Speicherleiste.
   *
   * Der oertliche Stand wird zuerst gesetzt, damit der Schalter nicht
   * kurz zurueckspringt. Geht das Speichern schief, wird neu geladen --
   * dann zeigt die Oberflaeche wieder, was wirklich gespeichert ist.
   */
  const patch = async (aenderung: Partial<Settings>) => {
    if (!settings) return;
    const vorher = settings;
    setSettings({ ...settings, ...aenderung });
    setSaving(true);
    try {
      const antwort = await api.saveTicketNotify(guildId, aenderung);
      if (antwort?.settings) setSettings(antwort.settings);
    } catch (err: any) {
      setSettings(vorher);
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

  if (!settings) return null;

  const s = settings;

  return (
    <div className="space-y-5">
      {/* ── Nutzer-DM ─────────────────────────────────────────── */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-purple-500/15 border border-purple-500/25 grid place-items-center">
              <MessageSquare className="h-5 w-5 text-purple-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">DM an den Ersteller</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Wenn das Team antwortet und der Ersteller es nicht mitbekommt.
              </p>
            </div>
          </div>
          <Toggle
            checked={s.user_dm_enabled}
            onChange={(v) => patch({ user_dm_enabled: v })}
            disabled={saving}
          />
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          <TimeField
            label="Wartezeit"
            hint={`Erst ${humanize(s.user_delay)} nach der Antwort des Teams.`}
            value={s.user_delay}
            unit="min"
            min={30}
            max={86400}
            disabled={!s.user_dm_enabled || saving}
            onChange={(v) => patch({ user_delay: v })}
          />
          <TimeField
            label="Sperrzeit"
            hint={`Höchstens eine DM pro Ticket in ${humanize(s.user_cooldown)}.`}
            value={s.user_cooldown}
            unit="h"
            min={60}
            max={604800}
            disabled={!s.user_dm_enabled || saving}
            onChange={(v) => patch({ user_cooldown: v })}
          />
        </div>

        {pending.user > 0 && (
          <div className="text-[11px] text-slate-500 flex items-center gap-2">
            <Clock className="h-3.5 w-3.5" />
            {pending.user} {pending.user === 1 ? "Ticket wartet" : "Tickets warten"} gerade
            auf diese Benachrichtigung.
          </div>
        )}
      </div>

      {/* ── Team-DM ───────────────────────────────────────────── */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-amber-500/15 border border-amber-500/25 grid place-items-center">
              <Users className="h-5 w-5 text-amber-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">DM an das Team</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Wenn jemand im Ticket wartet und keine Antwort kommt. Geht an
                das Teammitglied, das zuletzt geschrieben hat.
              </p>
            </div>
          </div>
          <Toggle
            checked={s.staff_dm_enabled}
            onChange={(v) => patch({ staff_dm_enabled: v })}
            disabled={saving}
          />
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          <TimeField
            label="Wartezeit"
            hint={`Erst ${humanize(s.staff_delay)} nachdem der Ersteller geschrieben hat.`}
            value={s.staff_delay}
            unit="min"
            min={30}
            max={86400}
            disabled={!s.staff_dm_enabled || saving}
            onChange={(v) => patch({ staff_delay: v })}
          />
          <TimeField
            label="Sperrzeit"
            hint={`Höchstens eine DM pro Ticket in ${humanize(s.staff_cooldown)}.`}
            value={s.staff_cooldown}
            unit="h"
            min={60}
            max={604800}
            disabled={!s.staff_dm_enabled || saving}
            onChange={(v) => patch({ staff_cooldown: v })}
          />
        </div>

        {pending.staff > 0 && (
          <div className="text-[11px] text-slate-500 flex items-center gap-2">
            <Clock className="h-3.5 w-3.5" />
            {pending.staff} {pending.staff === 1 ? "Ticket wartet" : "Tickets warten"} gerade
            auf diese Benachrichtigung.
          </div>
        )}
      </div>

      {/* ── Ruhezeit ──────────────────────────────────────────── */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="shrink-0 h-10 w-10 rounded-2xl bg-indigo-500/15 border border-indigo-500/25 grid place-items-center">
              <Moon className="h-5 w-5 text-indigo-300" />
            </div>
            <div>
              <h3 className="font-bold text-white">Ruhezeit</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                In diesem Zeitfenster geht gar keine DM raus — an niemanden.
              </p>
            </div>
          </div>
          <Toggle
            checked={s.quiet_enabled}
            onChange={(v) => patch({ quiet_enabled: v })}
            disabled={saving}
          />
        </div>

        <div className={cn("flex items-end gap-3", !s.quiet_enabled && "opacity-40")}>
          <div className="space-y-1.5">
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
              Von
            </label>
            <select
              value={s.quiet_start}
              disabled={!s.quiet_enabled || saving}
              onChange={(e) => patch({ quiet_start: parseInt(e.target.value, 10) })}
              className="bg-slate-900/60 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
              ))}
            </select>
          </div>
          <span className="text-slate-600 pb-2.5">bis</span>
          <div className="space-y-1.5">
            <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
              Bis
            </label>
            <select
              value={s.quiet_end}
              disabled={!s.quiet_enabled || saving}
              onChange={(e) => patch({ quiet_end: parseInt(e.target.value, 10) })}
              className="bg-slate-900/60 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
              ))}
            </select>
          </div>
          <p className="text-[11px] text-slate-500 italic pb-2.5">
            Zeiten in UTC.
          </p>
        </div>
      </div>

      {/* ── Die Regeln ────────────────────────────────────────── */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-2.5">
          <ShieldQuestion className="h-4 w-4 text-slate-400" />
          <h3 className="font-bold text-white text-sm">Wann der Bot eine DM schickt</h3>
        </div>

        <div className="space-y-2.5">
          <Rule n={1}>
            Nur wenn der Schalter oben an ist — für jede Richtung getrennt.
          </Rule>
          <Rule n={2}>
            <b className="text-slate-300">Nie in einem frischen Ticket.</b> Solange
            nur der Ersteller geschrieben hat, passiert nichts. Erst wenn ein
            Teammitglied da war, beginnt das System zu zählen.
          </Rule>
          <Rule n={3}>
            Dann wird die eingestellte Wartezeit abgewartet.
          </Rule>
          <Rule n={4}>
            Hat die Gegenseite in der Zwischenzeit geschrieben, entfällt die DM.
          </Rule>
          <Rule n={5}>
            <b className="text-slate-300">Sperrzeit:</b> Wer für dasselbe Ticket
            gerade schon eine DM bekommen hat, bekommt keine zweite.
          </Rule>
          <Rule n={6}>
            <b className="text-slate-300">
              <code className="text-purple-300">&gt;sleep</code> im Ticket
            </b>{" "}
            legt es komplett still — keine DM mehr, in keine Richtung. Bis{" "}
            <code className="text-purple-300">&gt;wake</code> kommt oder das Ticket
            geschlossen wird.
          </Rule>
          <Rule n={7}>
            Während der Ruhezeit wird niemand angeschrieben.
          </Rule>
        </div>

        <div className="pt-3 border-t border-slate-800 flex items-start gap-2.5">
          <BellRing className="h-3.5 w-3.5 text-slate-500 mt-0.5 shrink-0" />
          <p className="text-[11.5px] text-slate-500 leading-relaxed">
            Wer seine DMs geschlossen hat, bekommt nichts — das ist normal und
            löst keine Sperrzeit aus, damit die nächste Nachricht es wieder
            versuchen kann.
          </p>
        </div>
      </div>
    </div>
  );
}
