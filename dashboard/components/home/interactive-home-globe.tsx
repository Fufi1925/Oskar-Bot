"use client";

import React from "react";
import { Clock3, Server, Users } from "lucide-react";

type CountryValue = { country: string; views: number };
type VisitorData = { total: number; today: number; countries: CountryValue[] };
type Dot = { lat: number; lon: number; accent: boolean };

const COUNTRY_NAMES: Record<string, string> = {
  DE: "Deutschland", AT: "Österreich", US: "Vereinigte Staaten", NL: "Niederlande",
  CH: "Schweiz", CN: "China", FR: "Frankreich", RU: "Russland", GB: "Vereinigtes Königreich",
  IT: "Italien", ES: "Spanien", TR: "Türkei", CA: "Kanada", BR: "Brasilien", AU: "Australien",
};

function land(lat: number, lon: number) {
  // Deliberately coarse continent silhouettes. The dense dotted projection and
  // moving sphere are the visual layer; the live country list beside it is the
  // exact visitor data.
  const ellipse = (cx: number, cy: number, rx: number, ry: number) =>
    ((lon - cx) / rx) ** 2 + ((lat - cy) / ry) ** 2 < 1;
  return (
    ellipse(-108, 47, 42, 25) || ellipse(-88, 22, 18, 22) ||
    ellipse(-61, -17, 20, 36) || ellipse(-43, -10, 10, 19) ||
    ellipse(15, 50, 23, 14) || ellipse(18, 7, 22, 36) ||
    ellipse(67, 47, 56, 25) || ellipse(108, 23, 34, 25) ||
    ellipse(135, -25, 19, 13) || ellipse(48, -20, 6, 12) ||
    ellipse(-42, 72, 11, 8)
  );
}

const DOTS: Dot[] = (() => {
  const values: Dot[] = [];
  for (let lat = -58; lat <= 78; lat += 3.2) {
    for (let lon = -178; lon <= 178; lon += 3.2) {
      if (land(lat, lon)) values.push({ lat, lon, accent: ((Math.round(lat * 10) + Math.round(lon * 10)) % 41) === 0 });
    }
  }
  return values;
})();

function InteractiveCanvas() {
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const rotation = React.useRef(-18);
  const tilt = React.useRef(-7);
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
      if (!dragging.current) rotation.current += Math.min(32, now - previous) * 0.0025;
      previous = now;

      const radius = Math.min(width, height) * 0.39;
      const cx = width / 2;
      const cy = height / 2;
      const gradient = context.createRadialGradient(cx - radius * .3, cy - radius * .35, radius * .08, cx, cy, radius * 1.18);
      gradient.addColorStop(0, "rgba(217,70,239,.055)");
      gradient.addColorStop(.72, "rgba(90,12,92,.05)");
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      context.beginPath(); context.arc(cx, cy, radius * 1.18, 0, Math.PI * 2); context.fillStyle = gradient; context.fill();
      context.beginPath(); context.arc(cx, cy, radius, 0, Math.PI * 2); context.strokeStyle = "rgba(217,70,239,.68)"; context.lineWidth = 1.5; context.shadowColor = "#d946ef"; context.shadowBlur = 22; context.stroke(); context.shadowBlur = 0;

      const yaw = rotation.current * Math.PI / 180;
      const pitch = tilt.current * Math.PI / 180;
      const rendered: Array<{ x: number; y: number; z: number; accent: boolean }> = [];
      for (const dot of DOTS) {
        const lat = dot.lat * Math.PI / 180;
        const lon = dot.lon * Math.PI / 180 + yaw;
        const x0 = Math.cos(lat) * Math.sin(lon);
        const y0 = Math.sin(lat);
        const z0 = Math.cos(lat) * Math.cos(lon);
        const y = y0 * Math.cos(pitch) - z0 * Math.sin(pitch);
        const z = y0 * Math.sin(pitch) + z0 * Math.cos(pitch);
        if (z > -.08) rendered.push({ x: cx + x0 * radius, y: cy - y * radius, z, accent: dot.accent });
      }
      rendered.sort((a, b) => a.z - b.z);
      for (const dot of rendered) {
        const alpha = .22 + Math.max(0, dot.z) * .78;
        context.beginPath();
        context.arc(dot.x, dot.y, dot.accent ? 1.8 : 1.05, 0, Math.PI * 2);
        context.fillStyle = dot.accent ? `rgba(232,121,249,${alpha})` : `rgba(244,244,245,${alpha})`;
        context.fill();
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, []);

  return <canvas ref={canvas} aria-label="Drehbare Weltkugel der Homepage-Aufrufe" className="h-full min-h-[350px] w-full cursor-grab touch-none active:cursor-grabbing"
    onPointerDown={(event) => { dragging.current = true; last.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); }}
    onPointerMove={(event) => { if (!dragging.current) return; rotation.current += (event.clientX - last.current.x) * .32; tilt.current = Math.max(-42, Math.min(42, tilt.current - (event.clientY - last.current.y) * .2)); last.current = { x: event.clientX, y: event.clientY }; }}
    onPointerUp={(event) => { dragging.current = false; event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { dragging.current = false; }} />;
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
  const number = (value?: number) => typeof value === "number" && value > 0 ? value.toLocaleString("de-DE") : "—";

  return <section id="statistics" className="border-y border-fuchsia-500/10 bg-[#0b0a0c] px-4 py-16 sm:px-6 sm:py-20">
    <div className="mx-auto max-w-[1320px]">
      <div className="mb-10 text-center"><p className="text-[10px] font-black uppercase tracking-[.28em] text-fuchsia-400">Live auf der ganzen Welt</p><h2 className="mt-3 text-3xl font-black tracking-tight text-white sm:text-4xl">Eine Community ohne Grenzen.</h2><p className="mt-3 text-sm text-zinc-500">Die Kugel dreht sich langsam weiter. Ziehe sie mit Maus oder Finger in jede Richtung.</p></div>
      <div className="grid items-center gap-8 lg:grid-cols-[.9fr_1.1fr]">
        <div className="relative min-h-[410px] overflow-hidden"><InteractiveCanvas /><span className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full border border-fuchsia-400/15 bg-black/40 px-3 py-1.5 text-[10px] font-bold text-zinc-500 backdrop-blur">Ziehen zum Drehen</span></div>
        <div>
          <div className="grid grid-cols-3 gap-3">{[
            [Server, number(guilds), "Server"], [Users, number(users), "Nutzer"], [Clock3, "99,69%", "Uptime"],
          ].map(([Icon, value, label]) => { const StatIcon = Icon as React.ElementType; return <div key={String(label)} className="rounded-2xl border border-fuchsia-400/10 bg-[#120e13] px-3 py-5 text-center"><span className="mx-auto grid h-8 w-8 place-items-center rounded-lg border border-fuchsia-400/20 bg-fuchsia-500/10"><StatIcon className="h-4 w-4 text-fuchsia-400" /></span><p className="mt-3 text-lg font-black tabular-nums text-white sm:text-xl">{String(value)}</p><p className="mt-1 text-[9px] font-black uppercase tracking-[.2em] text-zinc-600">{String(label)}</p></div>; })}</div>
          <p className="mb-3 mt-7 text-[10px] font-black uppercase tracking-[.25em] text-zinc-600">Top Länder · echte Homepage-Aufrufe</p>
          <div className="space-y-2">{top.length ? top.map((country, index) => <div key={country.country}><div className="flex items-center gap-3 text-xs"><span className="w-4 tabular-nums text-zinc-700">{index + 1}.</span><span className="min-w-0 flex-1 truncate font-bold text-zinc-300">{COUNTRY_NAMES[country.country] || country.country}</span><span className="tabular-nums text-zinc-600">{country.views.toLocaleString("de-DE")}</span></div><div className="ml-7 mt-1 h-[3px] overflow-hidden rounded-full bg-white/[.05]"><div className="h-full rounded-full bg-fuchsia-600" style={{ width: `${Math.max(3, country.views / maximum * 100)}%` }} /></div></div>) : <div className="grid h-44 place-items-center rounded-2xl border border-fuchsia-400/10 bg-[#120e13] text-sm text-zinc-600">Live-Daten werden geladen …</div>}</div>
        </div>
      </div>
    </div>
  </section>;
}
