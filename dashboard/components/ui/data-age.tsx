"use client";

/**
 * How old the numbers on screen are.
 *
 * The stat cards each carried a green "LIVE" badge. The data refreshes
 * every 30 seconds, so for most of that window "live" is a small lie —
 * and four identical badges tell you nothing anyway.
 *
 * A ticking age is honest and actually useful: "vor 3 s" means the
 * figure is current, "vor 2 min" means the refresh loop has stopped and
 * something is wrong.
 *
 * The interval lives here rather than in the parent on purpose. Ticking
 * a clock in the page component re-renders the whole admin panel once a
 * second, including twenty tab buttons and a table.
 */

import React, { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Seconds since `since`, ticking. Returns null when nothing loaded yet. */
export function useDataAge(since: number | null): number | null {
  const [age, setAge] = useState<number | null>(null);

  useEffect(() => {
    if (!since) {
      setAge(null);
      return;
    }

    // Set it immediately, or the badge is blank for a second after
    // every refresh.
    const tick = () => setAge(Math.max(0, Math.round((Date.now() - since) / 1000)));
    tick();

    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [since]);

  return age;
}

function label(seconds: number): string {
  if (seconds < 5) return "gerade eben";
  if (seconds < 60) return `vor ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `vor ${minutes} min`;
  return `vor ${Math.floor(minutes / 60)} h`;
}

/**
 * A small badge saying how fresh the figure is.
 *
 * Turns amber once the data is older than the refresh interval allows,
 * because at that point the loop has stopped and the number on screen
 * is stale — the exact case a green badge would have hidden.
 */
export function DataAge({
  since,
  staleAfter = 90,
  className,
}: {
  since: number | null;
  staleAfter?: number;
  className?: string;
}) {
  const age = useDataAge(since);

  if (age === null) {
    return (
      <span
        className={cn(
          "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg",
          "text-slate-500 bg-white/[0.04]",
          className
        )}
      >
        lädt
      </span>
    );
  }

  const stale = age > staleAfter;

  return (
    <span
      // A title, because the short form loses precision on purpose.
      title={`Zuletzt aktualisiert: ${new Date(since!).toLocaleTimeString("de-DE")}`}
      className={cn(
        "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg",
        "transition-colors duration-500 inline-flex items-center gap-1.5",
        stale
          ? "text-amber-300 bg-amber-500/10"
          : "text-emerald-400 bg-emerald-500/10",
        className
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          stale ? "bg-amber-400" : "bg-emerald-400"
        )}
      />
      {label(age)}
    </span>
  );
}
