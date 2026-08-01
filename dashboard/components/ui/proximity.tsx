"use client";

/**
 * The LineSidebar proximity effect, as a hook.
 *
 * Adapted from React Bits' LineSidebar rather than dropped in whole.
 * That component takes `items: string[]` and an `onItemClick`, and
 * renders `<li>` elements. Our navigation is `<Link href>` — using the
 * original as-is would have turned real links into click handlers, and
 * with them: right-click "open in new tab", middle-click, the URL
 * preview in the corner, and Next.js prefetching. The visual idea is
 * worth having; that trade is not.
 *
 * So the mechanism is kept and the markup is left alone. Each row gets
 * a `--effect` custom property between 0 and 1, eased toward its target
 * by one shared rAF loop. Colour, shift and marker length all read that
 * same value, so they move together instead of drifting apart the way
 * three separate CSS transitions would.
 *
 * Original: https://reactbits.dev — LineSidebar
 */

import { useCallback, useEffect, useRef } from "react";

/** Distance-to-strength curves, as in the original. */
const FALLOFF = {
  linear: (p: number) => p,
  smooth: (p: number) => p * p * (3 - 2 * p),
  sharp: (p: number) => p * p * p,
} as const;

export type Falloff = keyof typeof FALLOFF;

export interface ProximityOptions {
  /** How far, in pixels, the cursor reaches. */
  radius?: number;
  /** Which curve maps distance to strength. */
  falloff?: Falloff;
  /** Time constant of the easing, in milliseconds. */
  smoothing?: number;
  /** Index that stays lit even without the cursor. */
  activeIndex?: number | null;
}

export interface Proximity {
  /**
   * Spread onto the scrolling container. The ref is what makes the
   * distance maths correct: `offsetTop` is measured against the nearest
   * positioned ancestor, so the element the pointer is measured from
   * has to be that same ancestor. Give the container `position:
   * relative` (Tailwind `relative`) and the two always agree.
   */
  containerProps: {
    ref: (el: HTMLElement | null) => void;
    onPointerMove: (event: React.PointerEvent) => void;
    onPointerLeave: () => void;
  };
  /** Call with the row index; spread onto the row. */
  itemProps: (index: number) => { ref: (el: HTMLElement | null) => void };
  /** Drop rows when the list shrinks, so stale ones stop being eased. */
  setCount: (count: number) => void;
}

export function useProximity({
  radius = 120,
  falloff = "smooth",
  smoothing = 120,
  activeIndex = null,
}: ProximityOptions = {}): Proximity {
  const container = useRef<HTMLElement | null>(null);
  const rows = useRef<(HTMLElement | null)[]>([]);
  const targets = useRef<number[]>([]);
  const current = useRef<number[]>([]);
  const frame = useRef<number | null>(null);
  const last = useRef(0);

  // Read inside the loop, so changing them does not restart it.
  const active = useRef(activeIndex);
  const tau = useRef(smoothing);
  active.current = activeIndex;
  tau.current = smoothing;

  // Frame-rate independent easing: the same motion at 60 and 144 Hz.
  // A fixed step per frame would run at twice the speed on a fast
  // display.
  const step = useCallback((now: number) => {
    const delta = Math.min((now - last.current) / 1000, 0.05);
    last.current = now;

    const factor = 1 - Math.exp(-delta / (Math.max(tau.current, 1) / 1000));
    let moving = false;

    for (let i = 0; i < rows.current.length; i++) {
      const el = rows.current[i];
      if (!el) continue;

      const target = Math.max(
        targets.current[i] || 0,
        active.current === i ? 1 : 0
      );
      const value = (current.current[i] || 0) + (target - (current.current[i] || 0)) * factor;
      // Snap when close enough, or the loop runs forever chasing a
      // difference nobody can see.
      const settled = Math.abs(target - value) < 0.0015;

      current.current[i] = settled ? target : value;
      el.style.setProperty("--effect", (settled ? target : value).toFixed(4));
      if (!settled) moving = true;
    }

    frame.current = moving ? requestAnimationFrame(step) : null;
  }, []);

  const start = useCallback(() => {
    if (frame.current != null) return;
    last.current = performance.now();
    frame.current = requestAnimationFrame(step);
  }, [step]);

  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      const host = container.current;
      if (!host) return;

      // A touch drag is a scroll, not a hover. Reacting to it lights up
      // whatever the finger happens to pass over.
      if (event.pointerType === "touch") return;

      const top = host.getBoundingClientRect().top;
      const y = event.clientY - top + host.scrollTop;
      const ease = FALLOFF[falloff] ?? FALLOFF.linear;

      for (let i = 0; i < rows.current.length; i++) {
        const el = rows.current[i];
        if (!el) continue;
        const centre = el.offsetTop + el.offsetHeight / 2;
        targets.current[i] = ease(
          Math.max(0, 1 - Math.abs(y - centre) / radius)
        );
      }
      start();
    },
    [falloff, radius, start]
  );

  const onPointerLeave = useCallback(() => {
    targets.current = targets.current.map(() => 0);
    start();
  }, [start]);

  const containerRef = useCallback((el: HTMLElement | null) => {
    container.current = el;
  }, []);

  const itemProps = useCallback(
    (index: number) => ({
      ref: (el: HTMLElement | null) => {
        rows.current[index] = el;
      },
    }),
    []
  );

  const setCount = useCallback((count: number) => {
    rows.current.length = count;
    targets.current.length = count;
    current.current.length = count;
  }, []);

  // The active row lights up on its own, so a change has to wake the
  // loop even when the cursor is elsewhere.
  useEffect(() => {
    start();
  }, [activeIndex, start]);

  useEffect(
    () => () => {
      if (frame.current != null) cancelAnimationFrame(frame.current);
    },
    []
  );

  return {
    containerProps: { ref: containerRef, onPointerMove, onPointerLeave },
    itemProps,
    setCount,
  };
}
