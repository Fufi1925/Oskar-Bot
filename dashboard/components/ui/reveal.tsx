"use client";

/**
 * Mount animations, driven by React.
 *
 * The dashboard is full of `animate-in fade-in slide-in-from-bottom-2`,
 * which comes from the `tailwindcss-animate` plugin — and that plugin
 * is not installed. Those classes generate no CSS at all, so none of it
 * has ever animated. Verified against a production build: the class
 * appears 45 times in the source and zero times in the output CSS.
 *
 * Rather than add a dependency for it, these components do the same job
 * with React state and a plain CSS transition. That also buys something
 * the utility classes cannot do: the delay is computed, so a list can
 * stagger itself without hard-coding a class per row.
 *
 * Two rules everything here follows:
 *
 *   * Animate on mount only. Re-running on every data refresh makes a
 *     table flicker every time somebody clicks "reload".
 *   * Honour prefers-reduced-motion. Not as a nicety — for some people
 *     moving interfaces are genuinely unusable, and the content is the
 *     same either way.
 */

import React, { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/** Whether the visitor asked their system to reduce motion. */
export function useReducedMotion(): boolean {
  // Starts false so the server and the first client render agree;
  // reading matchMedia during render would differ between the two and
  // React would complain about the mismatch.
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);

    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/**
 * Fade and lift its children in, once.
 *
 * `delay` is in milliseconds. Give siblings increasing delays and they
 * arrive one after another instead of all at once.
 */
export function Reveal({
  children,
  delay = 0,
  className,
  as: Tag = "div",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  as?: any;
}) {
  const [shown, setShown] = useState(false);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) {
      setShown(true);
      return;
    }
    // Two frames, not one: the browser has to paint the "before" state
    // at least once, otherwise it jumps straight to the end and there
    // is nothing to see.
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setShown(true));
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, [reduced]);

  return (
    <Tag
      className={cn(
        !reduced && "transition-all duration-500 ease-out will-change-transform",
        !reduced && !shown && "opacity-0 translate-y-3",
        (reduced || shown) && "opacity-100 translate-y-0",
        className
      )}
      style={reduced ? undefined : { transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}

/**
 * Count from zero up to `value`.
 *
 * Only on the first appearance of a number. Counting again every time
 * the list reloads would turn a quiet refresh into a slot machine.
 *
 * Uses a timestamp rather than a fixed step, so the duration holds even
 * when the tab is busy and frames are dropped.
 */
export function CountUp({
  value,
  duration = 700,
  className,
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(value);
  const animated = useRef(false);

  useEffect(() => {
    if (reduced || animated.current) {
      setShown(value);
      return;
    }
    // Nothing to count towards yet — wait for the real number instead
    // of "animating" zero to zero and marking it done.
    if (!value) {
      setShown(0);
      return;
    }

    animated.current = true;
    const start = performance.now();
    let frame = 0;

    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      // Ease-out: fast at first, settling at the end. A linear count
      // reads like a loading spinner.
      const eased = 1 - Math.pow(1 - progress, 3);
      setShown(Math.round(value * eased));
      if (progress < 1) frame = requestAnimationFrame(step);
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduced]);

  return <span className={className}>{shown}</span>;
}
