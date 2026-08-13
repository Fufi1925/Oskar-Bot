"use client";

/**
 * Ein schlichtes Liniendiagramm.
 *
 * ── Warum selbst gebaut ─────────────────────────────────────────────
 *
 * Recharts wiegt rund 100&nbsp;kB im Bundle und bringt eine eigene
 * Formensprache mit — abgerundete Tooltips, eigene Schriftgrößen,
 * eigene Farben. Für eine Linie mit Gitter und Achsen ist das viel
 * Gepäck für etwas, das in 200 Zeilen SVG passt und sich dann auch
 * an unsere Farben hält.
 *
 * ── Die zwei Regeln, die den Aufbau erklären ────────────────────────
 *
 * **Eine flache Linie muss flach aussehen.** Skaliert man die Y-Achse
 * immer auf Minimum-bis-Maximum, wird aus „2, 2, 2, 2, 3“ ein
 * dramatischer Anstieg über die volle Höhe. Deshalb bekommt eine
 * Reihe mit wenig Bewegung einen künstlichen Rand: erst ab einer
 * gewissen Spannweite füllt die Linie das Feld.
 *
 * **Eine Lücke ist keine Null.** Fehlt ein Tag, wird die Linie
 * unterbrochen statt auf null gezogen. Sonst sieht ein Ausfall der
 * Messung aus wie ein Einbruch der Zahl.
 *
 * ── Bedienung ───────────────────────────────────────────────────────
 *
 * Der Zeiger fährt über die Fläche, die nächstgelegene Stelle wird
 * hervorgehoben. Kein eigener Zustand pro Punkt: bei 90 Tagen wären
 * das 90 Listener.
 */

import React from "react";
import { cn } from "@/lib/utils";

export interface Punkt {
  /** Beschriftung auf der X-Achse. */
  label: string;
  /** Der Wert. `null` heißt: keine Messung — die Linie bricht dort. */
  wert: number | null;
}

interface Props {
  daten: Punkt[];
  /** Steht in der Legende oben links. */
  name?: string;
  /** Die Linienfarbe. */
  farbe?: string;
  /** Höhe der Zeichenfläche in Pixeln. */
  hoehe?: number;
  /** Nachkommastellen in der Beschriftung. */
  stellen?: number;
  /** Eine Einheit hinter den Zahlen, etwa „ms“. */
  einheit?: string;
  className?: string;
}

/** Wie viele Linien das Gitter hat. Fünf ist lesbar, ohne zu wimmeln. */
const GITTER = 5;

/** Innenabstand, damit Achsenbeschriftungen Platz haben. */
const LINKS = 46;
const RECHTS = 12;
const OBEN = 10;
const UNTEN = 26;

/**
 * Die Y-Achse festlegen.
 *
 * Nicht einfach min..max: bei „2, 2, 2“ wäre die Spannweite null und
 * die Linie läge auf der Kante. Und bei „2, 2, 3“ sähe ein Schritt
 * von eins aus wie eine Verdopplung über die volle Höhe.
 */
function achse(werte: number[]) {
  if (werte.length === 0) return { unten: 0, oben: 1 };

  const min = Math.min(...werte);
  const max = Math.max(...werte);
  const spanne = max - min;

  if (spanne === 0) {
    // Eine völlig flache Reihe: einen kleinen Rand ober- und
    // unterhalb, damit die Linie in der Mitte liegt.
    const rand = Math.max(Math.abs(min) * 0.1, 0.1);
    return { unten: min - rand, oben: max + rand };
  }

  const rand = spanne * 0.15;
  return {
    // Nie unter null, solange keine negativen Werte vorkommen: eine
    // Achse, die bei -3 anfängt, obwohl es keine negative Mitglieder-
    // zahl gibt, verwirrt mehr als sie zeigt.
    unten: min >= 0 ? Math.max(0, min - rand) : min - rand,
    oben: max + rand,
  };
}

/**
 * Wie viele Nachkommastellen die Achse braucht.
 *
 * Bei einer flachen Reihe ("2, 2, 2") liegen die fünf Gitterwerte
 * dicht beieinander -- ohne Nachkommastellen stünde fünfmal "2"
 * untereinander. Gemessen am eigenen Bild: genau das passierte.
 */
function stellenFuer(spanne: number, vorgabe: number) {
  const schritt = spanne / (GITTER - 1);
  if (schritt >= 1) return vorgabe;
  if (schritt >= 0.1) return Math.max(vorgabe, 1);
  return Math.max(vorgabe, 2);
}

/** Eine Zahl für die Achse: kurz, aber nicht falsch gerundet. */
function kurz(wert: number, stellen: number) {
  if (Math.abs(wert) >= 1_000_000) {
    return `${(wert / 1_000_000).toLocaleString("de-DE", {
      maximumFractionDigits: 1,
    })} Mio.`;
  }
  if (Math.abs(wert) >= 10_000) {
    return `${(wert / 1000).toLocaleString("de-DE", {
      maximumFractionDigits: 0,
    })}k`;
  }
  return wert.toLocaleString("de-DE", {
    minimumFractionDigits: stellen,
    maximumFractionDigits: stellen,
  });
}

/**
 * Dasselbe für die Y-Achse, aber ohne die Kürzung zu Unsinn zu machen.
 *
 * ── Der Fehler, den das behebt ──────────────────────────────────────
 *
 * `kurz()` schreibt ab 10.000 in Tausendern **ohne Nachkommastelle**.
 * Bei einer Achse von 48.200 bis 50.600 sind die fünf Gitterwerte
 * 48.200 / 48.800 / 49.400 / 50.000 / 50.600 — gekürzt wird daraus
 * 48k / 49k / 49k / 50k / 51k. Zwei Zeilen tragen dieselbe Zahl auf
 * verschiedenen Höhen. Im eigenen Bild nachgemessen, nicht vermutet.
 *
 * Die Kürzung braucht also so viele Nachkommastellen, dass zwei
 * benachbarte Gitterwerte sich unterscheiden — und keine mehr.
 */
function achsenBeschriftung(spanne: number, stellen: number) {
  const schritt = spanne / (GITTER - 1);

  return (wert: number) => {
    if (Math.abs(wert) >= 1_000_000) {
      // Ein Schritt von 20.000 braucht in Millionen zwei Stellen.
      const noetig = schritt >= 1_000_000 ? 0 : schritt >= 100_000 ? 1 : 2;
      return `${(wert / 1_000_000).toLocaleString("de-DE", {
        minimumFractionDigits: noetig,
        maximumFractionDigits: noetig,
      })} Mio.`;
    }
    if (Math.abs(wert) >= 10_000) {
      const noetig = schritt >= 1000 ? 0 : schritt >= 100 ? 1 : 2;
      return `${(wert / 1000).toLocaleString("de-DE", {
        minimumFractionDigits: noetig,
        maximumFractionDigits: noetig,
      })}k`;
    }
    return kurz(wert, stellen);
  };
}

/**
 * Welche X-Beschriftungen gezeigt werden.
 *
 * ── Der Fehler, den das behebt ──────────────────────────────────────
 *
 * Gezeigt wurde „jede n-te, und immer die letzte“. Geht die Reihe
 * nicht glatt auf, steht die letzte direkt neben der vorletzten: im
 * eigenen Bild überlappten „12. Aug.“ und „13. Aug.“ zu einem
 * unlesbaren Klumpen.
 *
 * Die letzte Beschriftung ist die wichtigere — sie sagt, bis wann die
 * Zahlen reichen. Also fliegt die vorletzte raus, wenn sie zu dicht
 * steht.
 */
function sichtbareMarken(anzahl: number): Set<number> {
  const schritt = Math.max(1, Math.ceil(anzahl / 8));
  const marken = new Set<number>();
  for (let i = 0; i < anzahl; i += schritt) marken.add(i);

  const letzte = anzahl - 1;
  // Was näher als ein halber Schritt an der letzten liegt, überlappt.
  for (const i of Array.from(marken)) {
    if (i !== letzte && letzte - i < Math.max(1, Math.ceil(schritt / 2))) {
      marken.delete(i);
    }
  }
  marken.add(letzte);
  return marken;
}

export function LineChart({
  daten,
  name,
  farbe = "#f59e0b",
  hoehe = 200,
  stellen = 0,
  einheit = "",
  className,
}: Props) {
  const [aktiv, setAktiv] = React.useState<number | null>(null);
  const flaeche = React.useRef<SVGSVGElement>(null);

  // Feste Breite im Koordinatensystem; das SVG skaliert selbst.
  const B = 600;
  const H = hoehe;
  const innenB = B - LINKS - RECHTS;
  const innenH = H - OBEN - UNTEN;

  const echte = daten.filter((p) => p.wert !== null).map((p) => p.wert as number);
  const { unten, oben } = achse(echte);
  const spanne = oben - unten || 1;
  // Genug Nachkommastellen, damit die Gitterwerte sich unterscheiden.
  const achsStellen = stellenFuer(spanne, stellen);
  // Kuerzt erst ab 10.000, und dann mit genug Nachkommastellen,
  // dass keine zwei Gitterwerte dieselbe Zahl tragen.
  const yText = achsenBeschriftung(spanne, achsStellen);

  const x = (i: number) =>
    LINKS + (daten.length <= 1 ? innenB / 2 : (i / (daten.length - 1)) * innenB);
  const y = (wert: number) => OBEN + innenH - ((wert - unten) / spanne) * innenH;

  /**
   * Die Linie als Pfad.
   *
   * Eine Lücke unterbricht ihn (`M` statt `L`), statt quer durch das
   * Feld auf null zu ziehen.
   */
  const pfad = React.useMemo(() => {
    let d = "";
    let luecke = true;
    daten.forEach((p, i) => {
      if (p.wert === null) {
        // Nach einer Lücke muss der nächste Punkt mit M anfangen,
        // sonst zieht die Linie quer darüber hinweg -- im eigenen
        // Bild nachgemessen, die Lücke war unsichtbar.
        luecke = true;
        return;
      }
      d += `${luecke ? "M" : "L"}${x(i).toFixed(1)},${y(p.wert).toFixed(1)}`;
      luecke = false;
    });
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [daten, unten, oben, hoehe]);

  /** Die Fläche darunter — nur wenn es keine Lücken gibt. */
  const flaechePfad = React.useMemo(() => {
    if (daten.some((p) => p.wert === null)) return "";
    if (daten.length < 2) return "";
    const erste = x(0);
    const letzte = x(daten.length - 1);
    const boden = OBEN + innenH;
    return `${pfad}L${letzte.toFixed(1)},${boden}L${erste.toFixed(1)},${boden}Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pfad, daten, hoehe]);

  const beiBewegung = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = flaeche.current?.getBoundingClientRect();
    if (!box || daten.length === 0) return;
    // Von Bildschirm- in Diagrammkoordinaten: das SVG ist skaliert.
    const relativ = ((e.clientX - box.left) / box.width) * B;
    const anteil = (relativ - LINKS) / innenB;
    const i = Math.round(anteil * (daten.length - 1));
    setAktiv(i >= 0 && i < daten.length ? i : null);
  };

  const gewaehlt = aktiv !== null ? daten[aktiv] : null;

  if (daten.length === 0) {
    return (
      <div
        className={cn(
          "grid place-items-center rounded-xl border border-slate-800 bg-[#0f0f13]",
          className,
        )}
        style={{ height: hoehe }}
      >
        <p className="text-[13px] text-slate-600">Noch keine Daten</p>
      </div>
    );
  }

  // Höchstens acht Beschriftungen auf der X-Achse: bei 90 Tagen
  // überlappen sonst alle.
  const marken = sichtbareMarken(daten.length);

  return (
    <div className={cn("rounded-xl border border-slate-800 bg-[#0f0f13] p-4", className)}>
      {name && (
        <div className="mb-2 flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-full border-2"
            style={{ borderColor: farbe }}
          />
          <span className="text-[13px] text-slate-300">{name}</span>
          {gewaehlt && (
            <span className="ml-auto text-[13px] tabular-nums text-slate-400">
              {gewaehlt.label}:{" "}
              <span className="font-semibold text-white">
                {gewaehlt.wert === null
                  ? "keine Messung"
                  : `${kurz(gewaehlt.wert, stellen)}${einheit}`}
              </span>
            </span>
          )}
        </div>
      )}

      <svg
        ref={flaeche}
        viewBox={`0 0 ${B} ${H}`}
        className="w-full"
        style={{ height: hoehe }}
        preserveAspectRatio="none"
        onMouseMove={beiBewegung}
        onMouseLeave={() => setAktiv(null)}
        role="img"
        aria-label={
          name
            ? `${name}: ${daten.length} Werte von ${daten[0]?.label} bis ${
                daten[daten.length - 1]?.label
              }`
            : "Diagramm"
        }
      >
        <defs>
          <linearGradient id={`fill-${farbe.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={farbe} stopOpacity="0.18" />
            <stop offset="100%" stopColor={farbe} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Gitter und Y-Beschriftung. */}
        {Array.from({ length: GITTER }, (_, i) => {
          const wert = oben - (i / (GITTER - 1)) * spanne;
          const yy = OBEN + (i / (GITTER - 1)) * innenH;
          return (
            <g key={i}>
              <line
                x1={LINKS}
                y1={yy}
                x2={B - RECHTS}
                y2={yy}
                stroke="#1e1f22"
                strokeWidth="1"
              />
              <text
                x={LINKS - 8}
                y={yy + 3.5}
                textAnchor="end"
                className="fill-slate-600"
                style={{ fontSize: 10 }}
              >
                {yText(wert)}
              </text>
            </g>
          );
        })}

        {/* X-Beschriftung. */}
        {daten.map((p, i) =>
          marken.has(i) ? (
            <text
              key={`${p.label}-${i}`}
              x={x(i)}
              y={H - 8}
              // Erste und letzte Beschriftung an ihrer Kante
              // ausrichten: mittig zentriert ragte "11. Aug" über
              // den Rand und wurde zu "11. Au".
              textAnchor={
                i === 0 ? "start" : i === daten.length - 1 ? "end" : "middle"
              }
              className="fill-slate-600"
              style={{ fontSize: 10 }}
            >
              {p.label}
            </text>
          ) : null,
        )}

        {flaechePfad && (
          <path d={flaechePfad} fill={`url(#fill-${farbe.replace("#", "")})`} />
        )}

        <path
          d={pfad}
          fill="none"
          stroke={farbe}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />

        {/* Bei wenigen Werten jeden Punkt zeigen -- eine Linie aus
            zwei Messungen sieht sonst aus wie eine Behauptung. */}
        {daten.length <= 14 &&
          daten.map((p, i) =>
            p.wert === null ? null : (
              <circle
                key={`p-${i}`}
                cx={x(i)}
                cy={y(p.wert)}
                r={3}
                fill="#0f0f13"
                stroke={farbe}
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            ),
          )}

        {/* Die Stelle unter dem Zeiger. */}
        {gewaehlt && gewaehlt.wert !== null && aktiv !== null && (
          <g>
            <line
              x1={x(aktiv)}
              y1={OBEN}
              x2={x(aktiv)}
              y2={OBEN + innenH}
              stroke="#33343b"
              strokeWidth="1"
            />
            <circle
              cx={x(aktiv)}
              cy={y(gewaehlt.wert)}
              r={4.5}
              fill={farbe}
              stroke="#0f0f13"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )}
      </svg>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
 *  Mehrere Linien in einem Bild
 * ──────────────────────────────────────────────────────────────────── */

export interface Reihe {
  /** Steht in der Legende. */
  name: string;
  /** Die Linienfarbe. */
  farbe: string;
  /** Ein Wert je Beschriftung. `null` heißt: keine Messung. */
  werte: Array<number | null>;
}

interface MultiProps {
  /** Die X-Achse. Alle Reihen teilen sie sich. */
  labels: string[];
  reihen: Reihe[];
  hoehe?: number;
  stellen?: number;
  einheit?: string;
  className?: string;
}

/**
 * Zwei oder drei Reihen übereinander.
 *
 * ── Warum nicht einfach zwei Diagramme untereinander ────────────────
 *
 * Beitritte und Austritte will man vergleichen, nicht nacheinander
 * lesen. Zwei getrennte Bilder haben zwei verschiedene Y-Achsen —
 * dann sehen 3 Austritte genauso hoch aus wie 30 Beitritte, und die
 * Antwort auf "wächst der Server?" steht nirgends.
 *
 * Deshalb: **eine gemeinsame Achse über alle Reihen.** Sie wird aus
 * allen Werten zusammen berechnet, nicht je Reihe.
 *
 * ── Die Legende ist anklickbar ──────────────────────────────────────
 *
 * Bei drei Reihen, von denen eine viel größer ist als die anderen,
 * drückt die große die kleinen auf die Grundlinie. Ein Klick auf die
 * Legende blendet sie aus, und die Achse rechnet sich neu — sonst
 * bliebe die Skala der ausgeblendeten Reihe stehen und der Klick
 * hätte nichts gebracht.
 */
export function MultiLineChart({
  labels,
  reihen,
  hoehe = 200,
  stellen = 0,
  einheit = "",
  className,
}: MultiProps) {
  const [aktiv, setAktiv] = React.useState<number | null>(null);
  const [aus, setAus] = React.useState<Set<string>>(() => new Set());
  const flaeche = React.useRef<SVGSVGElement>(null);

  const B = 600;
  const H = hoehe;
  const innenB = B - LINKS - RECHTS;
  const innenH = H - OBEN - UNTEN;

  const sichtbar = reihen.filter((r) => !aus.has(r.name));

  // Eine Achse über alle sichtbaren Reihen. Je Reihe eine eigene
  // hieße: zwei Linien, die sich kreuzen, ohne sich zu schneiden.
  const alle = sichtbar.flatMap((r) =>
    r.werte.filter((w): w is number => w !== null),
  );
  const { unten, oben } = achse(alle);
  const spanne = oben - unten || 1;
  const achsStellen = stellenFuer(spanne, stellen);
  // Kuerzt erst ab 10.000, und dann mit genug Nachkommastellen,
  // dass keine zwei Gitterwerte dieselbe Zahl tragen.
  const yText = achsenBeschriftung(spanne, achsStellen);

  const x = (i: number) =>
    LINKS + (labels.length <= 1 ? innenB / 2 : (i / (labels.length - 1)) * innenB);
  const y = (wert: number) => OBEN + innenH - ((wert - unten) / spanne) * innenH;

  /** Ein Pfad je Reihe, Lücken unterbrechen ihn. */
  const pfadVon = (werte: Array<number | null>) => {
    let d = "";
    let luecke = true;
    werte.forEach((wert, i) => {
      if (wert === null) {
        luecke = true;
        return;
      }
      d += `${luecke ? "M" : "L"}${x(i).toFixed(1)},${y(wert).toFixed(1)}`;
      luecke = false;
    });
    return d;
  };

  const beiBewegung = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = flaeche.current?.getBoundingClientRect();
    if (!box || labels.length === 0) return;
    const relativ = ((e.clientX - box.left) / box.width) * B;
    const anteil = (relativ - LINKS) / innenB;
    const i = Math.round(anteil * (labels.length - 1));
    setAktiv(i >= 0 && i < labels.length ? i : null);
  };

  const umschalten = (name: string) => {
    setAus((alt) => {
      const neu = new Set(alt);
      if (neu.has(name)) {
        neu.delete(name);
      } else if (neu.size < reihen.length - 1) {
        // Die letzte sichtbare Reihe lässt sich nicht ausblenden: ein
        // leeres Feld mit Gitter beantwortet keine Frage.
        neu.add(name);
      }
      return neu;
    });
  };

  if (labels.length === 0 || reihen.length === 0) {
    return (
      <div
        className={cn(
          "grid place-items-center rounded-xl border border-slate-800 bg-[#0f0f13]",
          className,
        )}
        style={{ height: hoehe }}
      >
        <p className="text-[13px] text-slate-600">Noch keine Daten</p>
      </div>
    );
  }

  const marken = sichtbareMarken(labels.length);

  return (
    <div className={cn("rounded-xl border border-slate-800 bg-[#0f0f13] p-4", className)}>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {reihen.map((reihe) => {
          const an = !aus.has(reihe.name);
          const wert = aktiv !== null ? reihe.werte[aktiv] : undefined;
          return (
            <button
              key={reihe.name}
              type="button"
              onClick={() => umschalten(reihe.name)}
              aria-pressed={an}
              className={cn(
                "flex items-center gap-2 text-[13px] transition-opacity",
                an ? "text-slate-300" : "text-slate-600 opacity-50",
              )}
            >
              <span
                className="h-2.5 w-2.5 rounded-full border-2"
                style={{ borderColor: reihe.farbe }}
              />
              {reihe.name}
              {an && wert !== undefined && (
                <span className="tabular-nums font-semibold text-white">
                  {wert === null ? "—" : `${kurz(wert, stellen)}${einheit}`}
                </span>
              )}
            </button>
          );
        })}

        {aktiv !== null && (
          <span className="ml-auto text-[13px] text-slate-500">
            {labels[aktiv]}
          </span>
        )}
      </div>

      <svg
        ref={flaeche}
        viewBox={`0 0 ${B} ${H}`}
        className="w-full"
        style={{ height: hoehe }}
        preserveAspectRatio="none"
        onMouseMove={beiBewegung}
        onMouseLeave={() => setAktiv(null)}
        role="img"
        aria-label={`${reihen.map((r) => r.name).join(", ")}: ${
          labels.length
        } Werte von ${labels[0]} bis ${labels[labels.length - 1]}`}
      >
        {/* Gitter und Y-Beschriftung. */}
        {Array.from({ length: GITTER }, (_, i) => {
          const wert = oben - (i / (GITTER - 1)) * spanne;
          const yy = OBEN + (i / (GITTER - 1)) * innenH;
          return (
            <g key={i}>
              <line
                x1={LINKS}
                y1={yy}
                x2={B - RECHTS}
                y2={yy}
                stroke="#1e1f22"
                strokeWidth="1"
              />
              <text
                x={LINKS - 8}
                y={yy + 3.5}
                textAnchor="end"
                className="fill-slate-600"
                style={{ fontSize: 10 }}
              >
                {yText(wert)}
              </text>
            </g>
          );
        })}

        {/* X-Beschriftung. Erste und letzte an ihrer Kante, sonst
            ragt die letzte über den Rand und wird abgeschnitten. */}
        {labels.map((label, i) =>
          marken.has(i) ? (
            <text
              key={`${label}-${i}`}
              x={x(i)}
              y={H - 8}
              textAnchor={
                i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"
              }
              className="fill-slate-600"
              style={{ fontSize: 10 }}
            >
              {label}
            </text>
          ) : null,
        )}

        {sichtbar.map((reihe) => (
          <path
            key={reihe.name}
            d={pfadVon(reihe.werte)}
            fill="none"
            stroke={reihe.farbe}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {/* Punkte nur bei wenigen Werten: bei 90 Tagen wird daraus
            ein Band, das die Linie verdeckt. */}
        {labels.length <= 14 &&
          sichtbar.map((reihe) =>
            reihe.werte.map((wert, i) =>
              wert === null ? null : (
                <circle
                  key={`${reihe.name}-${i}`}
                  cx={x(i)}
                  cy={y(wert)}
                  r={3}
                  fill="#0f0f13"
                  stroke={reihe.farbe}
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
              ),
            ),
          )}

        {aktiv !== null && (
          <g>
            <line
              x1={x(aktiv)}
              y1={OBEN}
              x2={x(aktiv)}
              y2={OBEN + innenH}
              stroke="#33343b"
              strokeWidth="1"
            />
            {sichtbar.map((reihe) => {
              const wert = reihe.werte[aktiv];
              if (wert === null || wert === undefined) return null;
              return (
                <circle
                  key={`a-${reihe.name}`}
                  cx={x(aktiv)}
                  cy={y(wert)}
                  r={4}
                  fill={reihe.farbe}
                  stroke="#0f0f13"
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
          </g>
        )}
      </svg>
    </div>
  );
}
