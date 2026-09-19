"use client";

import React from "react";
import { Clock3, Server, Users } from "lucide-react";
import { geoGraticule10, geoOrthographic, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import countriesTopology from "world-atlas/countries-110m.json";
import isoCountries from "i18n-iso-countries";

type CountryValue = { country: string; views: number };
type VisitorData = { total: number; today: number; countries: CountryValue[] };

const GERMAN_REGIONS = typeof Intl !== "undefined" && "DisplayNames" in Intl
  ? new Intl.DisplayNames(["de"], { type: "region" })
  : null;
const ENGLISH_REGIONS = typeof Intl !== "undefined" && "DisplayNames" in Intl
  ? new Intl.DisplayNames(["en"], { type: "region" })
  : null;

function countryName(code: string): string {
  const normalized = String(code || "").trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(normalized)) return "Unbekanntes Land";
  try {
    const german = GERMAN_REGIONS?.of(normalized);
    if (german && german !== normalized) return german;
    const english = ENGLISH_REGIONS?.of(normalized);
    if (english && english !== normalized) return english;
  } catch { /* Invalid or unsupported region code. */ }
  return "Unbekanntes Land";
}

const COUNTRIES = feature(countriesTopology as any, (countriesTopology as any).objects.countries) as any;
const GRATICULE = geoGraticule10();

function InteractiveCanvas({ visits }: { visits: Map<string, number> }) {
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const rotation = React.useRef(-18);
  const tilt = React.useRef(-10);
  const dragging = React.useRef(false);
  const last = React.useRef({ x: 0, y: 0 });

  React.useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const context = element.getContext("2d");
    if (!context) return;
    let frame = 0;
    let previous = performance.now();

    const draw = (now: number) => {
      const ratio = Math.min(2, window.devicePixelRatio || 1);
      const box = element.getBoundingClientRect();
      const width = Math.max(1, box.width);
      const height = Math.max(1, box.height);
      if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
        element.width = Math.round(width * ratio);
        element.height = Math.round(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      if (!dragging.current) rotation.current += Math.min(32, now - previous) * 0.008;
      previous = now;

      const radius = Math.min(width, height) * .4;
      const cx = width / 2;
      const cy = height / 2;
      const projection = geoOrthographic()
        .translate([cx, cy])
        .scale(radius)
        .clipAngle(90)
        .rotate([rotation.current, tilt.current, 0]);
      const path = geoPath(projection, context);

      const halo = context.createRadialGradient(cx, cy, radius * .72, cx, cy, radius * 1.22);
      halo.addColorStop(0, "rgba(37,99,235,.03)");
      halo.addColorStop(.82, "rgba(59,130,246,.11)");
      halo.addColorStop(1, "rgba(59,130,246,0)");
      context.beginPath(); context.arc(cx, cy, radius * 1.22, 0, Math.PI * 2); context.fillStyle = halo; context.fill();

      context.beginPath(); path({ type: "Sphere" } as any);
      context.fillStyle = "#090b11"; context.fill();
      context.strokeStyle = "rgba(96,165,250,.78)"; context.lineWidth = 1.5;
      context.shadowColor = "#3b82f6"; context.shadowBlur = 22; context.stroke(); context.shadowBlur = 0;

      context.beginPath(); path(GRATICULE as any);
      context.strokeStyle = "rgba(59,130,246,.075)"; context.lineWidth = .55; context.stroke();

      context.beginPath(); path(COUNTRIES);
      context.fillStyle = "rgba(37,99,235,.12)"; context.fill();
      context.strokeStyle = "rgba(191,219,254,.62)"; context.lineWidth = .55; context.stroke();

      const maximumVisits = Math.max(1, ...Array.from(visits.values()));
      for (const country of COUNTRIES.features || []) {
        const numeric = String(country.id ?? "").padStart(3, "0");
        const count = visits.get(numeric) || 0;
        if (!count) continue;
        const strength = Math.sqrt(count / maximumVisits);
        context.beginPath(); path(country);
        context.fillStyle = `rgba(37,99,235,${.28 + strength * .68})`;
        context.shadowColor = `rgba(59,130,246,${.35 + strength * .65})`;
        context.shadowBlur = 4 + strength * 19;
        context.fill();
        context.shadowBlur = 0;
        context.strokeStyle = `rgba(219,234,254,${.5 + strength * .5})`;
        context.lineWidth = .65 + strength * .8;
        context.stroke();
      }

      // A second soft outline keeps small real countries visible without
      // replacing them with invented continent blobs.
      context.beginPath(); path(COUNTRIES);
      context.strokeStyle = "rgba(59,130,246,.34)"; context.lineWidth = 1.3;
      context.shadowColor = "rgba(59,130,246,.65)"; context.shadowBlur = 5; context.stroke(); context.shadowBlur = 0;

      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [visits]);

  return <canvas ref={canvas} aria-label="Drehbare Weltkugel mit echten Ländergrenzen" className="h-full min-h-[255px] w-full cursor-grab touch-none active:cursor-grabbing sm:min-h-[350px]"
    onPointerDown={(event) => { dragging.current = true; last.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); }}
    onPointerMove={(event) => { if (!dragging.current) return; rotation.current += (event.clientX - last.current.x) * .32; tilt.current = Math.max(-42, Math.min(42, tilt.current - (event.clientY - last.current.y) * .2)); last.current = { x: event.clientX, y: event.clientY }; }}
    onPointerUp={(event) => { dragging.current = false; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { dragging.current = false; }}
    onLostPointerCapture={() => { dragging.current = false; }} />;
}

export function InteractiveHomeGlobe({ guilds, users }: { guilds?: number; users?: number }) {
  const [data, setData] = React.useState<VisitorData | null>(null);
  React.useEffect(() => {
    let active = true;
    fetch("/api/bot/bot/visitor-map", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then((response) => response.ok ? response.json() : null)
      .then((result) => { if (active && result) setData(result); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  const top = [...(data?.countries || [])].sort((a, b) => b.views - a.views).slice(0, 10);
  const maximum = Math.max(1, top[0]?.views || 1);
  const visits = React.useMemo(() => {
    const result = new Map<string, number>();
    for (const country of data?.countries || []) {
      const numeric = isoCountries.alpha2ToNumeric(country.country.toUpperCase());
      if (numeric) result.set(String(numeric).padStart(3, "0"), Number(country.views) || 0);
    }
    return result;
  }, [data]);
  const number = (value?: number) => typeof value === "number" && value > 0 ? value.toLocaleString("de-DE") : "—";

  return <section id="statistics" className="border-y border-blue-500/10 bg-[#0b0a0c] px-4 py-10 sm:px-6 sm:py-20">
    <div className="mx-auto max-w-[1320px]">
      <div className="mb-5 text-center sm:mb-10"><p className="text-[10px] font-black uppercase tracking-[.28em] text-blue-400">Live auf der ganzen Welt</p><h2 className="mt-2 text-2xl font-black tracking-tight text-white sm:mt-3 sm:text-4xl">Eine Community ohne Grenzen.</h2><p className="mt-2 text-xs leading-5 text-zinc-500 sm:mt-3 sm:text-sm">Dreht sich automatisch und lässt sich mit dem Finger bewegen.</p></div>
      <div className="grid items-center gap-4 sm:gap-8 lg:grid-cols-[.9fr_1.1fr]">
        <div className="relative min-h-[280px] overflow-hidden sm:min-h-[410px]"><InteractiveCanvas visits={visits} /><span className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-blue-400/15 bg-black/40 px-3 py-1.5 text-[10px] font-bold text-zinc-500 backdrop-blur sm:bottom-5">Ziehen zum Drehen</span></div>
        <div>
          <div className="grid grid-cols-3 gap-3">{[
            [Server, number(guilds), "Server"], [Users, number(users), "Nutzer"], [Clock3, "99,69%", "Uptime"],
          ].map(([Icon, value, label]) => { const StatIcon = Icon as React.ElementType; return <div key={String(label)} className="rounded-xl border border-blue-400/10 bg-[#120e13] px-2 py-3 text-center sm:rounded-2xl sm:px-3 sm:py-5"><span className="mx-auto hidden h-8 w-8 place-items-center rounded-lg border border-blue-400/20 bg-blue-500/10 sm:grid"><StatIcon className="h-4 w-4 text-blue-400" /></span><p className="text-base font-black tabular-nums text-white sm:mt-3 sm:text-xl">{String(value)}</p><p className="mt-1 text-[8px] font-black uppercase tracking-[.14em] text-zinc-600 sm:text-[9px] sm:tracking-[.2em]">{String(label)}</p></div>; })}</div>
          <p className="mb-3 mt-5 text-[10px] font-black uppercase tracking-[.25em] text-zinc-600 sm:mt-7">Top Länder · echte Homepage-Aufrufe</p>
          <div className="mobile-country-list space-y-2">{top.length ? top.map((country, index) => <div key={country.country}><div className="flex items-center gap-3 text-xs"><span className="w-4 tabular-nums text-zinc-700">{index + 1}.</span><span className="min-w-0 flex-1 truncate font-bold text-zinc-300">{countryName(country.country)}</span><span className="tabular-nums text-zinc-600">{country.views.toLocaleString("de-DE")}</span></div><div className="ml-7 mt-1 h-[3px] overflow-hidden rounded-full bg-white/[.05]"><div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.max(3, country.views / maximum * 100)}%` }} /></div></div>) : <div className="grid h-44 place-items-center rounded-2xl border border-blue-400/10 bg-[#120e13] text-sm text-zinc-600">Live-Daten werden geladen …</div>}</div>
        </div>
      </div>
    </div>
    <style jsx global>{`
      @media (max-width: 639px) {
        .mobile-country-list > :nth-child(n+6) { display: none; }
      }
    `}</style>
  </section>;
}
