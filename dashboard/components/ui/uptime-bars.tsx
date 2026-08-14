"use client";

/**
 * Der Verfügbarkeits-Balken: eine Säule je Zeitabschnitt.
 *
 * ── Warum Balken und keine Linie ────────────────────────────────────
 *
 * Eine Linie beantwortet „wie schnell war es?". Hier lautet die Frage
 * „lief es?" — und darauf gibt es drei Antworten, nicht einen Wert:
 *
 *   **lief**            grün
 *   **Störung**         rot
 *   **nicht gemessen**  grau
 *
 * Der dritte Fall ist der wichtigste und der Grund, warum diese Datei
 * existiert. Ein Abschnitt ohne Messung ist **nicht** „alles in
 * Ordnung": der Wächter war da selbst aus, oder die Aufzeichnung
 * begann später. Wer das grün zeichnet, behauptet etwas, das er nicht
 * geprüft hat.
 *
 * ── Warum reines SVG ────────────────────────────────────────────────
 *
 * Dieselbe Begründung wie beim Liniendiagramm nebenan: eine
 * Diagramm-Bibliothek wiegt rund 100 kB und bringt eigene Farben und
 * Formen mit. Ein paar Rechtecke sind kein Grund dafür.
 */

import React from "react";
import { cn } from "@/lib/utils";

export interface Abschnitt {
  /** Beginn des Abschnitts, Unix-Sekunden. */
  start: number;
  /** Ende des Abschnitts, Unix-Sekunden. */
  end: number;
  /** Wurde in diesem Abschnitt überhaupt gemessen? */
  known: boolean;
  /** War in diesem Abschnitt etwas nicht erreichbar? */
  bad: boolean;
  /** Durchschnittliche Antwortzeit, `null` wenn nichts gemessen. */
  latency: number | null;
  /** Wie viele Messungen fielen hinein. */
  samples: number;
  /** Wie viele davon waren erfolglos. */
  unreachable: number;
}

const GRUEN = "#10b981";
const ROT = "#f43f5e";
const GRAU = "#26262c";

function zeitraum(von: number, bis: number) {
  const a = new Date(von * 1000);
  const b = new Date(bis * 1000);
  // Über einen Tag hinweg reicht das Datum, darunter die Uhrzeit.
  const langer = bis - von > 6 * 3600;
  const format: Intl.DateTimeFormatOptions = langer
    ? { day: "2-digit", month: "2-digit" }
    : { hour: "2-digit", minute: "2-digit" };
  const links = a.toLocaleString("de-DE", format);
  const rechts = b.toLocaleString("de-DE", format);
  return links === rechts ? links : `${links} – ${rechts}`;
}

export function UptimeBars({
  abschnitte,
  hoehe = 56,
  className,
}: {
  abschnitte: Abschnitt[];
  hoehe?: number;
  className?: string;
}) {
  const [aktiv, setAktiv] = React.useState<number | null>(null);

  if (abschnitte.length === 0) {
    return (
      <div
        className={cn(
          "grid place-items-center rounded-xl border border-slate-800 bg-[#0f0f13]",
          className,
        )}
        style={{ height: hoehe + 40 }}
      >
        <p className="text-[13px] text-slate-600">Noch keine Aufzeichnung</p>
      </div>
    );
  }

  const gewaehlt = aktiv !== null ? abschnitte[aktiv] : null;

  return (
    <div className={cn("rounded-xl border border-slate-800 bg-[#0f0f13] p-4", className)}>
      {/* Die Säulen. Feste Höhe, gleiche Breite: die Frage ist "lief
          es", nicht "wie viel" -- eine unterschiedliche Höhe würde eine
          Menge behaupten, die es hier nicht gibt. */}
      <div
        className="flex items-end gap-[3px]"
        style={{ height: hoehe }}
        onMouseLeave={() => setAktiv(null)}
      >
        {abschnitte.map((a, i) => {
          const farbe = !a.known ? GRAU : a.bad ? ROT : GRUEN;
          return (
            <button
              key={`${a.start}-${i}`}
              type="button"
              onMouseEnter={() => setAktiv(i)}
              onFocus={() => setAktiv(i)}
              aria-label={`${zeitraum(a.start, a.end)}: ${
                !a.known ? "nicht gemessen" : a.bad ? "Störung" : "lief"
              }`}
              className={cn(
                "h-full min-w-0 flex-1 rounded-[3px] transition-opacity",
                aktiv !== null && aktiv !== i && "opacity-45",
              )}
              style={{ backgroundColor: farbe }}
            />
          );
        })}
      </div>

      {/* Was unter dem Zeiger liegt. Feste Höhe, damit die Zeile
          darunter nicht springt, sobald man über die Säulen fährt. */}
      <div className="mt-3 flex min-h-[20px] flex-wrap items-center gap-x-3 text-[12px]">
        {gewaehlt ? (
          <>
            <span className="text-slate-300">
              {zeitraum(gewaehlt.start, gewaehlt.end)}
            </span>
            <span
              className={
                !gewaehlt.known
                  ? "text-slate-500"
                  : gewaehlt.bad
                    ? "text-rose-400"
                    : "text-emerald-400"
              }
            >
              {!gewaehlt.known
                ? "nicht gemessen"
                : gewaehlt.bad
                  ? `${gewaehlt.unreachable} von ${gewaehlt.samples} Prüfungen fehlgeschlagen`
                  : "erreichbar"}
            </span>
            {gewaehlt.latency !== null && (
              <span className="text-slate-500 tabular-nums">
                {Math.round(gewaehlt.latency)} ms
              </span>
            )}
          </>
        ) : (
          <span className="text-slate-600">
            Zum Ansehen über einen Balken fahren
          </span>
        )}
      </div>

      {/* Die Legende. Sie steht hier, weil Grau sonst als „egal"
          gelesen wird -- dabei ist es die einzige Farbe, die eine
          fehlende Aussage bedeutet. */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-slate-800 pt-3 text-[11px] text-slate-500">
        {[
          [GRUEN, "erreichbar"],
          [ROT, "Störung"],
          [GRAU, "nicht gemessen"],
        ].map(([farbe, text]) => (
          <span key={text} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-[2px]"
              style={{ backgroundColor: farbe }}
            />
            {text}
          </span>
        ))}
      </div>
    </div>
  );
}
