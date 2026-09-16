"use client";

import React from "react";
import { ArrowDown, ArrowUp, Globe2 } from "lucide-react";
import { WORLD_PATHS } from "@/components/home/world-paths";
import { cn } from "@/lib/utils";

type CountryValue = { country: string; views: number };
type VisitorMapData = {
  total: number;
  today: number;
  trend_7d: number | null;
  countries: CountryValue[];
  updated_at: number;
  metric: "homepage_page_views";
};

type Hover = { code: string; name: string; views: number; x: number; y: number } | null;

const formatter = new Intl.NumberFormat("de-DE");
const regionNames = typeof Intl !== "undefined" && "DisplayNames" in Intl
  ? new Intl.DisplayNames(["de"], { type: "region" })
  : null;

function farbe(wert: number, max: number) {
  if (!wert) return "#20232d";
  const anteil = wert / Math.max(1, max);
  if (anteil >= 0.8) return "#818cf8";
  if (anteil >= 0.5) return "#6366f1";
  if (anteil >= 0.25) return "#4f46e5";
  if (anteil >= 0.1) return "#3730a3";
  return "#312e81";
}

export function HomepageWorldMap() {
  const [data, setData] = React.useState<VisitorMapData | null>(null);
  const [hover, setHover] = React.useState<Hover>(null);
  const [fehler, setFehler] = React.useState(false);
  const mapRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let aktiv = true;
    const laden = (method: "GET" | "POST") => fetch("/api/bot/bot/visitor-map", {
      method,
      cache: "no-store",
      headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
      body: method === "POST" ? "{}" : undefined,
    }).then((response) => {
      if (!response.ok) throw new Error("visitor map unavailable");
      return response.json();
    });

    // Bei jedem Öffnen melden. Das Backend entscheidet anhand der IP, ob der
    // letzte gezählte Aufruf mindestens zehn Minuten zurückliegt.
    laden("POST")
      .then((result) => { if (aktiv) { setData(result); setFehler(false); } })
      .catch(() => { if (aktiv) setFehler(true); });

    const timer = window.setInterval(() => {
      laden("GET").then((result) => { if (aktiv) setData(result); }).catch(() => {});
    }, 30_000);
    return () => { aktiv = false; window.clearInterval(timer); };
  }, []);

  const werte = React.useMemo(
    () => new Map((data?.countries || []).map((item) => [item.country.toUpperCase(), Number(item.views) || 0])),
    [data],
  );
  const max = Math.max(1, ...Array.from(werte.values()));
  const trend = data?.trend_7d;

  const zeigen = (event: React.PointerEvent<SVGPathElement>, code: string, name: string) => {
    const box = mapRef.current?.getBoundingClientRect();
    if (!box) return;
    setHover({
      code,
      name: regionNames?.of(code) || name,
      views: werte.get(code) || 0,
      x: Math.max(12, Math.min(box.width - 170, event.clientX - box.left + 12)),
      y: Math.max(12, Math.min(box.height - 76, event.clientY - box.top + 12)),
    });
  };

  return (
    <section className="px-4 py-12 sm:px-6 lg:px-12 xl:px-20">
      <div className="mx-auto max-w-[1400px] border-y border-slate-800 py-8">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-5 px-1">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.14em] text-indigo-400">
              <Globe2 className="h-4 w-4" /> Live von der Homepage
            </p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">Website-Aufrufe weltweit</h2>
          </div>
          <div className="flex items-end gap-6">
            <div><p className="text-3xl font-semibold tabular-nums text-white">{data ? formatter.format(data.total) : "—"}</p><p className="mt-1 text-xs text-slate-500">Aufrufe gesamt</p></div>
            <div><p className="text-xl font-semibold tabular-nums text-white">{data ? formatter.format(data.today) : "—"}</p><p className="mt-1 text-xs text-slate-500">heute</p></div>
            {trend !== null && trend !== undefined && (
              <span className={cn("mb-4 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-bold", trend >= 0 ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400" : "border-red-500/20 bg-red-500/10 text-red-400")}>
                {trend >= 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}{trend >= 0 ? "+" : ""}{trend.toFixed(1)}%
              </span>
            )}
          </div>
        </div>

        <div ref={mapRef} className="relative overflow-hidden bg-[#0d0e13]">
          <svg viewBox="0 0 1000 500" className="block h-auto min-h-[250px] w-full" role="img" aria-label="Weltkarte der echten Homepage-Aufrufe nach Land">
            <rect width="1000" height="500" fill="#0d0e13" />
            {WORLD_PATHS.map((country) => {
              const views = werte.get(country.code) || 0;
              return (
                <path
                  key={`${country.code}-${country.name}`}
                  d={country.d}
                  fill={farbe(views, max)}
                  stroke="#0d0e13"
                  strokeWidth="0.8"
                  vectorEffect="non-scaling-stroke"
                  className="transition-[fill,opacity] duration-200 hover:opacity-80 focus:outline-none"
                  tabIndex={views ? 0 : -1}
                  onPointerMove={(event) => zeigen(event, country.code, country.name)}
                  onPointerLeave={() => setHover(null)}
                  onFocus={(event) => {
                    const box = event.currentTarget.getBoundingClientRect();
                    const parent = mapRef.current?.getBoundingClientRect();
                    if (parent) setHover({ code: country.code, name: regionNames?.of(country.code) || country.name, views, x: Math.max(12, box.left - parent.left), y: Math.max(12, box.top - parent.top) });
                  }}
                  onBlur={() => setHover(null)}
                />
              );
            })}
          </svg>

          {hover && (
            <div className="pointer-events-none absolute z-10 w-40 rounded-lg border border-slate-700 bg-[#151720]/95 p-3 shadow-xl backdrop-blur" style={{ left: hover.x, top: hover.y }}>
              <p className="truncate text-xs font-semibold text-white">{hover.name}</p>
              <p className="mt-1 text-sm font-bold tabular-nums text-indigo-300">{formatter.format(hover.views)} Aufrufe</p>
            </div>
          )}

          {!data && !fehler && <div className="absolute inset-0 grid place-items-center bg-[#0d0e13]/60 text-sm text-slate-500">Live-Daten werden geladen …</div>}
          {fehler && !data && <div className="absolute inset-x-0 bottom-4 text-center text-sm text-slate-500">Die Live-Zahlen sind gerade nicht erreichbar.</div>}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1 text-[11px] text-slate-600">
          <span>Je heller das Land, desto mehr echte Seitenaufrufe.</span>
          <span>Aktualisierung alle 30 Sekunden · keine erfundenen Beispieldaten</span>
        </div>
      </div>
    </section>
  );
}
