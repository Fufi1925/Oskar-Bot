"use client";

/**
 * Der Verlauf eines Servers als Diagramme.
 *
 * ── Warum drei Bilder und nicht eins ────────────────────────────────
 *
 * Mitglieder liegen bei ein paar tausend, Beitritte bei ein paar
 * Dutzend. In einem Bild mit gemeinsamer Achse wäre die Beitritts-
 * linie ein Strich auf der Grundlinie — technisch richtig, praktisch
 * unlesbar.
 *
 * Beitritte und Austritte dagegen gehören zusammen: sie haben
 * dieselbe Größenordnung, und die Frage lautet ja gerade, welche der
 * beiden Linien oben liegt. Die teilen sich deshalb ein Bild.
 *
 * ── Was die Zeitraumwahl ändert ─────────────────────────────────────
 *
 * Nur die Anzahl der Tage in der Anfrage. Der Server schneidet nicht
 * zurecht, was er hat — fehlende Tage kommen als `null` zurück und
 * werden als Lücke gezeichnet. Wer den Bot erst seit gestern laufen
 * hat, sieht deshalb bei „90 Tage“ eine kurze Linie ganz rechts und
 * nicht 89 Nullen.
 */

import React, { useEffect, useState } from "react";
import { Loader2, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LineChart, MultiLineChart } from "@/components/ui/line-chart";

const CARD = "rounded-2xl border border-slate-800 bg-[#131318]";

/** Die wählbaren Zeiträume. */
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
  member_count: number;
  has_data: boolean;
}

/** Ein Datum als „12. Aug“ — kurz genug für die Achse. */
function tag(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/**
 * Summe einer Reihe, Lücken übersprungen.
 *
 * `null + 0` wäre in JavaScript 0 und damit stillschweigend falsch:
 * aus „nicht gemessen“ würde „nichts passiert“.
 */
function summe(werte: Array<number | null>) {
  return werte.reduce<number>((s, w) => s + (w ?? 0), 0);
}

export function HistoryCharts({ guildId }: { guildId: string }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Verlauf | null>(null);
  const [loading, setLoading] = useState(true);
  const [fehler, setFehler] = useState(false);

  useEffect(() => {
    let abgebrochen = false;
    setLoading(true);
    setFehler(false);

    api
      .getGuildHistory(guildId, days)
      .then((antwort) => {
        // Nach einem schnellen Wechsel des Zeitraums kann die alte
        // Antwort nach der neuen eintreffen. Ohne diesen Riegel
        // stünde dann der falsche Zeitraum im Bild.
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
  }, [guildId, days]);

  const labels = (data?.days || []).map(tag);

  const zeitraumWahl = (
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
  );

  return (
    <div className={cn(CARD, "p-5 sm:p-6")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[16px] font-bold text-white">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            Verlauf
          </h2>
          <p className="mt-1 text-[13px] text-slate-500">
            Ein Wert pro Tag. Eine Unterbrechung heißt: an dem Tag wurde
            nicht gemessen.
          </p>
        </div>
        {zeitraumWahl}
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
          <p className="text-[14px] text-slate-300">
            Noch keine Messungen für diesen Server.
          </p>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
            Der Verlauf beginnt, sobald der Bot läuft — der erste Punkt
            steht nach etwa einer halben Stunde im Bild, ein Diagramm
            braucht mindestens zwei Tage.
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {/* Mitglieder. Eigene Achse: die Zahl liegt zwei
              Größenordnungen über den Beitritten. */}
          <div>
            <p className="mb-2 text-[13px] font-semibold text-slate-300">
              Mitglieder
            </p>
            <LineChart
              daten={labels.map((label, i) => ({
                label,
                wert: data.members[i] ?? null,
              }))}
              name="Mitglieder"
              farbe="#5865f2"
              hoehe={180}
            />
          </div>

          {/* Beitritte gegen Austritte. Gemeinsame Achse, sonst sähen
              3 Austritte so hoch aus wie 30 Beitritte. */}
          <div>
            <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <p className="text-[13px] font-semibold text-slate-300">
                Kommen und Gehen
              </p>
              <p className="text-[12px] text-slate-500">
                {summe(data.joins).toLocaleString("de-DE")} Beitritte,{" "}
                {summe(data.leaves).toLocaleString("de-DE")} Austritte im
                Zeitraum
              </p>
            </div>
            <MultiLineChart
              labels={labels}
              reihen={[
                { name: "Beitritte", farbe: "#10b981", werte: data.joins },
                { name: "Austritte", farbe: "#f43f5e", werte: data.leaves },
              ]}
              hoehe={180}
            />
          </div>

          {/* Befehle. Zeigt, ob der Bot benutzt wird — die Frage, die
              hinter „lohnt sich das Modul“ steckt. */}
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
        </div>
      )}
    </div>
  );
}
