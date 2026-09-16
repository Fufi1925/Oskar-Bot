"use client";

import React from "react";
import { cn } from "@/lib/utils";

type Wert = number | null;

export type AdminChartReihe = {
  key: string;
  name: string;
  farbe: string;
  werte: Wert[];
};

type Props = {
  labels: string[];
  reihen: AdminChartReihe[];
  hoehe?: number;
  className?: string;
  einheit?: string;
};

const B = 720;
const OBEN = 18;
const RECHTS = 12;
const UNTEN = 30;
const LINKS = 12;

function kurz(wert: number) {
  if (Math.abs(wert) >= 1_000_000) return `${(wert / 1_000_000).toLocaleString("de-DE", { maximumFractionDigits: 1 })} Mio.`;
  if (Math.abs(wert) >= 10_000) return `${(wert / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 })}k`;
  return wert.toLocaleString("de-DE", { maximumFractionDigits: 2 });
}

/** Catmull-Rom als kubische Bézier-Kurve: weich wie curveNatural, ohne neue Chart-Laufzeit. */
function weicherPfad(punkte: Array<[number, number]>) {
  if (!punkte.length) return "";
  if (punkte.length === 1) return `M${punkte[0][0]},${punkte[0][1]}`;
  let d = `M${punkte[0][0].toFixed(2)},${punkte[0][1].toFixed(2)}`;
  for (let i = 0; i < punkte.length - 1; i++) {
    const p0 = punkte[Math.max(0, i - 1)];
    const p1 = punkte[i];
    const p2 = punkte[i + 1];
    const p3 = punkte[Math.min(punkte.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2[0].toFixed(2)},${p2[1].toFixed(2)}`;
  }
  return d;
}

function marken(anzahl: number) {
  const schritt = Math.max(1, Math.ceil(anzahl / 7));
  const result = new Set<number>();
  for (let i = 0; i < anzahl; i += schritt) result.add(i);
  if (anzahl) result.add(anzahl - 1);
  return result;
}

export function AdminLineChart({ labels, reihen, hoehe = 220, className, einheit = "" }: Props) {
  const [aktiv, setAktiv] = React.useState<number | null>(null);
  const svg = React.useRef<SVGSVGElement>(null);
  const id = React.useId().replaceAll(":", "");
  const innenB = B - LINKS - RECHTS;
  const innenH = hoehe - OBEN - UNTEN;
  const alle = reihen.flatMap((reihe) => reihe.werte.filter((wert): wert is number => wert !== null));
  const max = alle.length ? Math.max(...alle) : 1;
  const min = alle.length ? Math.min(...alle) : 0;
  const spanne = Math.max(1, max - min);
  const rand = Math.max(spanne * 0.16, max === min ? Math.abs(max) * 0.1 : 0, 1);
  const unten = min >= 0 ? Math.max(0, min - rand) : min - rand;
  const oben = max + rand;
  const bereich = oben - unten || 1;
  const x = (i: number) => LINKS + (labels.length < 2 ? innenB / 2 : (i / (labels.length - 1)) * innenB);
  const y = (wert: number) => OBEN + innenH - ((wert - unten) / bereich) * innenH;
  const xMarken = marken(labels.length);

  const pfade = reihen.map((reihe) => {
    const teile: Array<Array<[number, number]>> = [];
    let teil: Array<[number, number]> = [];
    reihe.werte.forEach((wert, index) => {
      if (wert === null) {
        if (teil.length) teile.push(teil);
        teil = [];
      } else {
        teil.push([x(index), y(wert)]);
      }
    });
    if (teil.length) teile.push(teil);
    return { ...reihe, pfad: teile.map(weicherPfad).join(" ") };
  });

  const bewegen = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box || labels.length === 0) return;
    const px = ((event.clientX - box.left) / box.width) * B;
    const index = Math.round(((px - LINKS) / innenB) * (labels.length - 1));
    setAktiv(Math.max(0, Math.min(labels.length - 1, index)));
  };

  if (!labels.length || !alle.length) {
    return <div className={cn("grid place-items-center border-y border-slate-800 text-sm text-slate-600", className)} style={{ height: hoehe }}>Noch keine Messwerte</div>;
  }

  return (
    <div className={cn("relative min-w-0", className)}>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-2">
        {reihen.map((reihe) => (
          <span key={reihe.key} className="inline-flex items-center gap-2 text-xs text-slate-400">
            <span className="h-0.5 w-5 rounded-full" style={{ background: reihe.farbe }} />
            {reihe.name}
          </span>
        ))}
      </div>

      <div className="relative">
        <svg ref={svg} viewBox={`0 0 ${B} ${hoehe}`} preserveAspectRatio="none" className="w-full touch-none" style={{ height: hoehe }} onPointerMove={bewegen} onPointerLeave={() => setAktiv(null)} role="img" aria-label={`${reihen.map((reihe) => reihe.name).join(", ")} im Zeitverlauf`}>
          <defs>
            <linearGradient id={`fade-${id}`} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="black" stopOpacity="0" />
              <stop offset="0.06" stopColor="white" />
              <stop offset="0.94" stopColor="white" />
              <stop offset="1" stopColor="black" stopOpacity="0" />
            </linearGradient>
            <mask id={`mask-${id}`}><rect width={B} height={hoehe - UNTEN} fill={`url(#fade-${id})`} /></mask>
          </defs>

          {Array.from({ length: 5 }, (_, index) => {
            const yy = OBEN + (index / 4) * innenH;
            return <line key={index} x1={LINKS} y1={yy} x2={B - RECHTS} y2={yy} stroke="#252833" strokeWidth="1" vectorEffect="non-scaling-stroke" />;
          })}

          {labels.map((label, index) => xMarken.has(index) ? (
            <text key={`${label}-${index}`} x={x(index)} y={hoehe - 7} textAnchor={index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle"} fill="#64748b" fontSize="10">{label}</text>
          ) : null)}

          <g mask={`url(#mask-${id})`}>
            {pfade.map((reihe) => (
              <path key={reihe.key} d={reihe.pfad} fill="none" stroke={reihe.farbe} strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" pathLength={1} className="admin-chart-line" />
            ))}
          </g>

          {aktiv !== null && (
            <g>
              <line x1={x(aktiv)} y1={OBEN} x2={x(aktiv)} y2={OBEN + innenH} stroke="#475569" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
              {reihen.map((reihe) => {
                const wert = reihe.werte[aktiv];
                return wert === null || wert === undefined ? null : <circle key={reihe.key} cx={x(aktiv)} cy={y(wert)} r="4.5" fill={reihe.farbe} stroke="#0b0c10" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />;
              })}
            </g>
          )}
        </svg>

        {aktiv !== null && (
          <div className={cn("pointer-events-none absolute top-2 z-10 min-w-36 rounded-lg border border-slate-700 bg-[#11131a]/95 p-3 shadow-xl backdrop-blur", aktiv > labels.length / 2 ? "right-3" : "left-3")}>
            <p className="mb-2 text-[11px] font-semibold text-slate-300">{labels[aktiv]}</p>
            {reihen.map((reihe) => {
              const wert = reihe.werte[aktiv];
              return <div key={reihe.key} className="flex items-center justify-between gap-5 text-[11px]"><span style={{ color: reihe.farbe }}>{reihe.name}</span><strong className="tabular-nums text-white">{wert === null || wert === undefined ? "—" : `${kurz(wert)}${einheit}`}</strong></div>;
            })}
          </div>
        )}
      </div>

      <style jsx global>{`
        @keyframes adminChartDraw { from { stroke-dashoffset: 1; opacity: .2; } to { stroke-dashoffset: 0; opacity: 1; } }
        .admin-chart-line { stroke-dasharray: 1; animation: adminChartDraw 1100ms cubic-bezier(.5,1.35,.5,1) both; }
        @media (prefers-reduced-motion: reduce) { .admin-chart-line { animation: none; stroke-dashoffset: 0; } }
      `}</style>
    </div>
  );
}
