"use client";

/**
 * Der Stil des Admin-Dashboards, an einer Stelle.
 *
 * ── Warum es diese Datei gibt ───────────────────────────────────────
 *
 * Die Reiter des Admin-Bereichs waren in zwei Stilen gebaut, und man
 * sah es beim Umschalten sofort:
 *
 *   „Alle Server“, „Dashboard-Nutzer“  →  Glaskarten: `glass`,
 *       `border-white/5`, Ecken `rounded-[2rem]`, Flächen aus
 *       `bg-white/[0.03]`.
 *   die übrigen 19 Reiter               →  `bg-[#131318]`,
 *       `border-slate-800`, Ecken `rounded-3xl`.
 *
 * Ausgemessen waren es 23 `glass`, 101 `border-white/5` und 20
 * `rounded-[2rem]` gegen 113 Karten im anderen Stil. Zwei Stile in
 * einem Bereich sind kein Stil.
 *
 * Der Reiter „Alle Server“ ist die Vorlage — so wollte es der Nutzer.
 * Damit „1 zu 1“ nicht heißt, dass dieselben vierzig Zeichen künftig
 * an 130 Stellen von Hand gepflegt werden, stehen sie hier **einmal**.
 * Zwei handgepflegte Listen laufen auseinander; in diesem Repo ist das
 * schon passiert.
 *
 * ── Was bewusst NICHT übernommen wurde ──────────────────────────────
 *
 * `glass` heißt `backdrop-blur-xl bg-white/[0.02]` — eine Fläche, die
 * durchscheinen lässt, was dahinter liegt. Auf der Vorlagenseite liegt
 * dahinter nur der Seitenhintergrund, das Ergebnis ist also fast genau
 * `#131318`. Der Wert steht deshalb als **feste Farbe** hier, plus
 * dem Rand aus der Vorlage. Grund: `backdrop-blur` auf über hundert
 * Karten kostet auf jedem Bildlauf Rechenzeit für einen Effekt, den
 * man an keiner Stelle sieht. Gemessen, nicht vermutet: hinter jeder
 * dieser Karten liegt eine einfarbige Fläche.
 *
 * ── Der Rand-Schimmer ───────────────────────────────────────────────
 *
 * `` baut seinen Ring aus der Ecke der Karte und muss
 * sie deshalb kennen. Für `rounded-3xl` (1.5rem) ist das der
 * Standardwert; jede andere Ecke braucht ihre `glow-r-*`-Klasse. Ein
 * Test prüft das, weil ein fehlendes `glow-r-2xl` einen Ring an der
 * falschen Rundung zeichnet.
 */

import React from "react";
import { cn } from "@/lib/utils";

/* ── Karten ───────────────────────────────────────────────────────── */

/**
 * Die große Karte. Der Regelfall im Admin-Bereich.
 *
 * `rounded-3xl` ist die Ecke, auf die `` ohne
 * Zusatzklasse ausgelegt ist.
 */
export const KARTE =
  "bg-[#131318] border border-slate-800 rounded-3xl";

/** Dieselbe Karte mit dem üblichen Innenabstand. */
export const KARTE_P = cn(KARTE, "p-4 sm:p-6");

/**
 * Eine Karte, die ihren Inhalt beschneidet (Listen mit Trennlinien).
 *
 * `is-clipped` gehört zwingend dazu: ohne sie liegt der Schein-Ring
 * außerhalb von `overflow-hidden` und wird abgeschnitten.
 */
export const KARTE_LISTE = cn(KARTE, "overflow-hidden is-clipped");

/** Eine Fläche INNERHALB einer Karte — eine Stufe dunkler. */
export const FELD = "bg-[#0e0e12] border border-slate-800 rounded-xl";

/* ── Bedienelemente ───────────────────────────────────────────────── */

/** Ein Eingabefeld. */
export const EINGABE =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-2.5 " +
  "text-sm text-white placeholder:text-slate-600 transition-colors " +
  "focus:outline-none focus:border-slate-700";

/** Der ruhige Knopf: der Regelfall. */
export const KNOPF =
  "px-4 py-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-sm " +
  "font-semibold text-slate-300 transition-colors hover:border-slate-700 " +
  "hover:text-white disabled:opacity-40";

/** Der betonte Knopf: genau einer je Ansicht. */
export const KNOPF_AKTION =
  "px-4 py-2.5 rounded-xl bg-[#5865f2] border border-[#5865f2] text-sm " +
  "font-semibold text-white transition-colors hover:bg-[#4752c4] " +
  "disabled:opacity-40";

/** Ein Knopf, der etwas zerstört. */
export const KNOPF_GEFAHR =
  "px-4 py-2.5 rounded-xl bg-rose-500/10 border border-rose-500/25 text-sm " +
  "font-semibold text-rose-300 transition-colors hover:bg-rose-500/20 " +
  "disabled:opacity-40";

/** Ein quadratischer Knopf, in dem nur ein Symbol steht. */
export const KNOPF_SYMBOL =
  "grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#0e0e12] " +
  "border border-slate-800 text-slate-400 transition-colors " +
  "hover:border-slate-700 hover:text-white disabled:opacity-40";

/**
 * Beschriftung über einem Feld.
 *
 * Kleiner, aber nicht in Versalien mit 0.2em Sperrung: das war im
 * alten Stil an 370 Stellen und liest sich als Schreien.
 */
export const LABEL = "block text-[12px] font-semibold text-slate-400";

/* ── Bausteine ────────────────────────────────────────────────────── */

/**
 * Die Kopfzeile eines Reiters: Symbol, Titel, Satz, rechts Bedienung.
 *
 * Vorher hatte jeder Reiter seine eigene — mal 2xl-fett, mal in
 * Versalien, mal mit farbiger Symbolkachel, mal ganz ohne. Bei
 * einundzwanzig Reitern heißt das einundzwanzig erste Eindrücke.
 */
export function PanelKopf({
  icon: Icon,
  titel,
  text,
  children,
  className,
}: {
  icon?: React.ElementType;
  titel: string;
  text?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        KARTE,
        "flex flex-wrap items-center gap-4 px-5 py-4",
        className,
      )}
    >
      {Icon && (
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/25 bg-indigo-500/10">
          <Icon className="h-[18px] w-[18px] text-indigo-400" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="text-[18px] font-bold tracking-tight text-white">
          {titel}
        </h2>
        {text && <p className="mt-0.5 text-[13px] text-slate-500">{text}</p>}
      </div>
      {children && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Eine Reihe von Kennzahlen.
 *
 * Die Vorlage zeigt fünf Kacheln mit `text-3xl font-black` und einer
 * Beschriftung in Versalien darunter. Übernommen ist die Anordnung;
 * die Beschriftung steht in normaler Schrift, wie im übrigen
 * Dashboard seit dem Umbau des Admin-Kopfes.
 */
export function Kennzahlen({
  werte,
  className,
}: {
  werte: Array<{
    label: string;
    wert: React.ReactNode;
    icon?: React.ElementType;
    farbe?: string;
  }>;
  className?: string;
}) {
  if (werte.length === 0) return null;
  return (
    <div
      className={cn(
        "grid gap-3",
        werte.length >= 5
          ? "grid-cols-2 lg:grid-cols-5"
          : werte.length === 4
            ? "grid-cols-2 lg:grid-cols-4"
            : "grid-cols-2 lg:grid-cols-3",
        className,
      )}
    >
      {werte.map((k) => (
        <div
          key={k.label}
          className={cn(KARTE, "flex items-center gap-3 px-4 py-3.5")}
        >
          {k.icon && (
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/[0.04]">
              <k.icon className={cn("h-4 w-4", k.farbe || "text-slate-500")} />
            </span>
          )}
          <div className="min-w-0">
            <p className="truncate text-[19px] font-bold leading-none tabular-nums text-white">
              {k.wert}
            </p>
            <p className="mt-1.5 truncate text-[12px] text-slate-500">
              {k.label}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Eine Reiterleiste innerhalb eines Reiters.
 *
 * Dieselbe Form wie im Admin-Kopf: Fläche für den offenen, Text für
 * die übrigen. Zwei Signale — Fläche und fettere Schrift —, damit die
 * Auswahl nicht allein an der Farbe hängt.
 */
export function UnterReiter<T extends string>({
  wert,
  setzen,
  reiter,
  className,
}: {
  wert: T;
  setzen: (wert: T) => void;
  reiter: Array<{ id: T; label: string; icon?: React.ElementType }>;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap gap-1 rounded-xl border border-slate-800 bg-[#131318] p-1",
        className,
      )}
    >
      {reiter.map((r) => {
        const aktiv = wert === r.id;
        const Icon = r.icon;
        return (
          <button
            key={r.id}
            type="button"
            onClick={() => setzen(r.id)}
            aria-current={aktiv ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[13px] transition-colors",
              aktiv
                ? "border-indigo-500/30 bg-indigo-500/10 font-semibold text-white"
                : "border-transparent text-slate-500 hover:bg-white/[0.03] hover:text-slate-300",
            )}
          >
            {Icon && (
              <Icon
                className={cn(
                  "h-3.5 w-3.5 shrink-0",
                  aktiv ? "text-indigo-400" : "text-slate-600",
                )}
              />
            )}
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * „Hier ist nichts“ — als Karte, nicht als nackter Satz.
 *
 * Ein grauer Satz auf leerem Grund sieht aus wie ein Ladefehler.
 */
export function Leer({
  icon: Icon,
  titel,
  text,
  children,
}: {
  icon?: React.ElementType;
  titel: string;
  text?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn(KARTE, "px-6 py-10 text-center")}>
      {Icon && <Icon className="mx-auto mb-3 h-7 w-7 text-slate-700" />}
      <p className="text-[15px] text-slate-300">{titel}</p>
      {text && (
        <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
          {text}
        </p>
      )}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}
