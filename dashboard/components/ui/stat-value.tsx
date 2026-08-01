"use client";

/**
 * A stat figure that animates to its new value.
 *
 * The admin cards hold strings, not numbers: "977", "16.51ms",
 * "0.94 MB". CountUp takes a number, so it cannot be used here — and
 * naively parsing with parseFloat would drop the unit and print a bare
 * "0.94" where "0.94 MB" belongs.
 *
 * So the string is split into a leading number and whatever follows.
 * Anything with no number at all (an error string, a dash) is rendered
 * as-is rather than mangled into NaN.
 *
 * Animating on *change* rather than on mount is the point: the panel
 * refreshes every 30 seconds, and a figure that moves is how you notice
 * something happened without watching the screen.
 */

import React, { useEffect, useRef, useState } from "react";

import { useReducedMotion } from "@/components/ui/reveal";
import { cn } from "@/lib/utils";

/** "16.51ms" -> [16.51, "ms"]. Returns null when there is no number. */
function split(text: string): [number, string, number] | null {
  // The gap before the unit is captured, not skipped: "0.94 MB" has to
  // stay "0,94 MB". Swallowing it printed "0,94MB".
  const match = /^\s*(-?\d+(?:[.,]\d+)?)(\s*.*)$/.exec(text ?? "");
  if (!match) return null;

  const raw = match[1].replace(",", ".");
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;

  // Keep the original precision: rounding 0.94 to 1 would be wrong, and
  // printing 977.00 would be noise.
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  return [value, match[2] ?? "", decimals];
}

export function StatValue({
  value,
  duration = 800,
  className,
}: {
  value: string | number;
  duration?: number;
  className?: string;
}) {
  const text = String(value ?? "");
  const parsed = split(text);
  const reduced = useReducedMotion();

  const target = parsed ? parsed[0] : 0;
  const suffix = parsed ? parsed[1] : "";
  const decimals = parsed ? parsed[2] : 0;

  const [shown, setShown] = useState(target);
  // Where the last animation ended, so a refresh counts *from* the old
  // figure instead of snapping back to zero every thirty seconds.
  const from = useRef(target);

  useEffect(() => {
    if (!parsed || reduced) {
      setShown(target);
      from.current = target;
      return;
    }
    if (from.current === target) return;

    const start = performance.now();
    const origin = from.current;
    let frame = 0;

    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      // Ease-out: quick at first, settling at the end. Linear reads
      // like a loading bar rather than a value changing.
      const eased = 1 - Math.pow(1 - progress, 3);
      setShown(origin + (target - origin) * eased);
      if (progress < 1) {
        frame = requestAnimationFrame(step);
      } else {
        from.current = target;
      }
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration, reduced, parsed]);

  // No number in there at all — show whatever it is, untouched.
  if (!parsed) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={cn("tabular-nums", className)}>
      {shown.toLocaleString("de-DE", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}
