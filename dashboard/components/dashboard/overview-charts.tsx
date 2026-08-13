"use client";

/**
 * Der Verlauf über alle Server — für den Admin-Bereich und die
 * Einstiegsseite des Dashboards.
 *
 * ── Warum getrennt von `history-charts.tsx` ─────────────────────────
 *
 * Die Server-Übersicht fragt einen Server, diese Ansicht fragt alle.
 * Das sind zwei Endpunkte mit zwei Berechtigungen — ein gemeinsamer
 * Baustein hätte einen Schalter gebraucht, der entscheidet, welchen
 * er nimmt, und die Berechtigung wäre eine Eigenschaft des Aufrufers
 * geworden statt der Route.
 *
 * Die Diagramme selbst sind dieselben: `LineChart` und
 * `MultiLineChart` stehen in `components/ui/line-chart.tsx`.
 *
 * ── Warum „Reichweite“ und nicht „Mitglieder“ ───────────────────────
 *
 * Die Reihe ist die Summe der Mitgliederzahlen aller Server. Wer auf
 * drei Servern ist, steckt dreimal darin. „Mitglieder“ würde als
 * Personenzahl gelesen und wäre dann zu hoch.
 */

import React, { useEffect, useState } from "react";
import { Loader2, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LineChart, MultiLineChart } from "@/components/ui/line-chart";

const ZEITRAEUME: Array<[number, string]> = [
  [7, "7 Tage"],
  [30, "30 Tage"],
  [90, "90 Tage"],
];

interface Verlauf {
  days: string[];
  members: Array<number | null>;
  joins: Array<number | null>;
  leaves: Array<number | null>;
  commands: Array<number | null>;
  guild_count: number;
  has_data: boolean;
}

function tag(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

export function OverviewCharts({ className }: { className?: string }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Verlauf | null>(null);
  const [loading, setLoading] = useState(true);
  const [fehler, setFehler] = useState(false);

  useEffect(() => {
    let abgebrochen = false;
    setLoading(true);
    setFehler(false);

    api
      .getAdminHistory(days)
      .then((antwort) => {
        // Nach einem schnellen Wechsel kann die alte Antwort nach der
        // neuen eintreffen — dann stünde der falsche Zeitraum im Bild.
        if (!abgebrochen) setData(antwort);
      })
      .catch(() => {
        if (!abgebrochen) {
          setData(null);
          setFehler(true);
        }
      })
      .finally(() => {
        if (!abgebrochen) setLoading(false);
      });

    return () => {
      abgebrochen = true;
    };
  }, [days]);

  const labels = (data?.days || []).map(tag);

  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-800 bg-[#131318] p-5 sm:p-6",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[16px] font-bold text-white">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            Verlauf
          </h2>
          <p className="mt-1 text-[13px] text-slate-500">
            Über alle Server zusammen. Eine Unterbrechung heißt: an dem
            Tag wurde nicht gemessen.
          </p>
        </div>

        <div className="flex gap-1 rounded-lg border border-slate-800 bg-[#0f0f13] p-1">
          {ZEITRAEUME.map(([wert, label]) => (
            <button
              key={wert}
              type="button"
              onClick={() => setDays(wert)}
              aria-pressed={days === wert}
              className={cn(
                "rounded-md px-2.5 py-1 text-[12px] transition-colors",
                days === wert
                  ? "bg-white/[0.07] font-semibold text-white"
                  : "text-slate-500 hover:text-slate-300",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="mt-5 flex h-[200px] items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-indigo-400 opacity-50" />
        </div>
      ) : fehler || !data ? (
        <p className="mt-5 text-[13px] text-slate-500">
          Der Verlauf ließ sich nicht laden. Der Bot antwortet gerade nicht.
        </p>
      ) : !data.has_data ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-[#0f0f13] p-5">
          <p className="text-[14px] text-slate-300">Noch keine Messungen.</p>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
            Der Verlauf beginnt mit dem ersten Schnappschuss — der läuft
            alle 30 Minuten. Ein Diagramm braucht mindestens zwei Tage.
            Ohne Volume für <code className="text-slate-400">db/</code> fängt
            die Zählung nach jedem Deploy von vorn an.
          </p>
        </div>
      ) : (
        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <div>
            <p className="mb-2 text-[13px] font-semibold text-slate-300">
              Reichweite
            </p>
            <LineChart
              daten={labels.map((label, i) => ({
                label,
                wert: data.members[i] ?? null,
              }))}
              name="Nutzer auf allen Servern"
              farbe="#5865f2"
              hoehe={180}
            />
          </div>

          <div>
            <p className="mb-2 text-[13px] font-semibold text-slate-300">
              Befehle pro Tag
            </p>
            <LineChart
              daten={labels.map((label, i) => ({
                label,
                wert: data.commands[i] ?? null,
              }))}
              name="Aufrufe"
              farbe="#f59e0b"
              hoehe={180}
            />
          </div>

          <div className="xl:col-span-2">
            <p className="mb-2 text-[13px] font-semibold text-slate-300">
              Kommen und Gehen
            </p>
            <MultiLineChart
              labels={labels}
              reihen={[
                { name: "Beitritte", farbe: "#10b981", werte: data.joins },
                { name: "Austritte", farbe: "#f43f5e", werte: data.leaves },
              ]}
              hoehe={180}
            />
          </div>
        </div>
      )}
    </div>
  );
}
