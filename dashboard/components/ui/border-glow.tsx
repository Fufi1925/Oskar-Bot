"use client";

/**
 * BorderGlow, adapted from React Bits.
 *
 * A rim light that follows the pointer around the edge of a card. Two
 * custom properties carry everything: the angle from the card's centre
 * to the cursor, and how close the cursor is to the edge (0-100). All
 * the drawing is CSS reading those two numbers.
 *
 * ── Why this is a provider and not a wrapper component ──────────────
 *
 * The original attaches an `onPointerMove` to each card and renders two
 * extra divs around the content. This dashboard has 132 cards. That
 * would mean 132 React listeners, 132 rAF loops, and -- worse -- 132
 * JSX restructures, each one turning a card into a nested pair of divs
 * and so breaking whatever grid or flex parent it sits in.
 *
 * Instead one listener sits on the document, finds the card under the
 * pointer with `closest()`, and writes to that one element. Adding the
 * effect to a card is then a class name and nothing else, which is a
 * change that cannot break a layout.
 *
 * ── What was dropped, and why ───────────────────────────────────────
 *
 * The original draws three layers: the mesh-gradient rim, a mesh wash
 * inside the card, and the outer halo. An element has two pseudos, and
 * the third layer is why the original needs a `<span class="edge-light">`
 * in the markup -- which is exactly the markup change being avoided.
 *
 * So the inner wash is the one that goes. It was the weakest of the
 * three: `soft-light` at low opacity underneath body text, and it does
 * not render in Firefox at all, which does not support
 * `mask-composite: subtract`. The rim and the halo are the effect.
 *
 * The `animated` intro sweep is not implemented either. It plays once
 * on mount, and with 121 cards on screen that is 121 rims sweeping at
 * page load -- the brief's own example switches it off, and there is no
 * call site here that wants it. It is left out rather than shipped
 * broken; if a single hero card ever needs it, it belongs there and not
 * in a provider that has no per-card state.
 *
 * ── The source in the brief ─────────────────────────────────────────
 *
 * It had been pasted through Markdown, which corrupted six places: a
 * missing `[` in the glow-var loop, a broken template literal on
 * `className`, `x * x * x` collapsed to `x  *x*  x` by italics, and
 * three autolinked identifiers (`performance.now`, `card.style`,
 * `rect.top`). Reconstructed here rather than copied.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

/** "213 94 68" or "213deg 94% 68%" -> {h, s, l}. */
export function parseHSL(value: string): { h: number; s: number; l: number } {
  const match = value.match(/([\d.]+)\s*(?:deg)?\s+([\d.]+)%?\s+([\d.]+)%?/);
  if (!match) return { h: 40, s: 80, l: 80 };
  return {
    h: parseFloat(match[1]),
    s: parseFloat(match[2]),
    l: parseFloat(match[3]),
  };
}

const GLOW_STEPS: Array<[string, number]> = [
  ["", 100], ["-60", 60], ["-50", 50], ["-40", 40],
  ["-30", 30], ["-20", 20], ["-10", 10],
];

export function buildGlowVars(glowColor: string, intensity: number) {
  const { h, s, l } = parseHSL(glowColor);
  const base = `${h}deg ${s}% ${l}%`;
  const vars: Record<string, string> = {};
  for (const [suffix, opacity] of GLOW_STEPS) {
    // Clamped: an intensity above 1 would push the top stops past 100%,
    // which is not a valid alpha and drops the declaration entirely.
    const alpha = Math.min(opacity * intensity, 100);
    vars[`--glow-color${suffix}`] = `hsl(${base} / ${alpha}%)`;
  }
  return vars;
}

const GRADIENT_POSITIONS = [
  "80% 55%", "69% 34%", "8% 6%", "41% 38%", "86% 85%", "82% 18%", "51% 4%",
];
const GRADIENT_KEYS = [
  "--gradient-one", "--gradient-two", "--gradient-three", "--gradient-four",
  "--gradient-five", "--gradient-six", "--gradient-seven",
];
const COLOR_MAP = [0, 1, 2, 0, 1, 2, 1];

export function buildGradientVars(colors: string[]) {
  const vars: Record<string, string> = {};
  for (let i = 0; i < GRADIENT_KEYS.length; i++) {
    const colour = colors[Math.min(COLOR_MAP[i], colors.length - 1)];
    vars[GRADIENT_KEYS[i]] =
      `radial-gradient(at ${GRADIENT_POSITIONS[i]}, ${colour} 0px, transparent 50%)`;
  }
  vars["--gradient-base"] = `linear-gradient(${colors[0]} 0 100%)`;
  return vars;
}

/** The class a card needs for the rim. Exported so tests can find it. */
export const GLOW_CLASS = "border-glow-card";

/**
 * Tracks the pointer for every card on the page. Mount once, high up.
 *
 * Reads are batched into one rAF: `pointermove` fires far more often
 * than the screen refreshes, and a write per event is work the browser
 * throws away. `getBoundingClientRect` forces layout, so it is done at
 * most once a frame rather than once an event.
 */
export function BorderGlowProvider() {
  React.useEffect(() => {
    let frame: number | null = null;
    let pendingEvent: { x: number; y: number } | null = null;
    let current: HTMLElement | null = null;

    const clear = (el: HTMLElement | null) => {
      // The rim fades out through CSS on :hover, but the value under it
      // has to go back to zero or the next hover starts lit, at
      // whatever angle the pointer left at.
      el?.style.setProperty("--edge-proximity", "0");
    };

    const flush = () => {
      frame = null;
      const point = pendingEvent;
      const card = current;
      if (!point || !card) return;

      const rect = card.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;

      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const dx = point.x - rect.left - cx;
      const dy = point.y - rect.top - cy;

      // How far out the pointer is as a fraction of the distance to the
      // edge in that same direction: 0 dead centre, 1 at the rim.
      const kx = dx !== 0 ? cx / Math.abs(dx) : Infinity;
      const ky = dy !== 0 ? cy / Math.abs(dy) : Infinity;
      const edge = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1) * 100;

      let angle = 0;
      if (dx !== 0 || dy !== 0) {
        angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
        if (angle < 0) angle += 360;
      }

      card.style.setProperty("--edge-proximity", edge.toFixed(2));
      card.style.setProperty("--cursor-angle", `${angle.toFixed(2)}deg`);
    };

    const onMove = (event: PointerEvent) => {
      // A touch drag is a scroll. Lighting whatever the finger passes
      // over is noise, and on a phone the rim is never seen anyway.
      if (event.pointerType === "touch") return;

      const target = event.target as Element | null;
      const card = target?.closest?.(`.${GLOW_CLASS}`) as HTMLElement | null;

      // Cards nest. `closest` returns the innermost, which is the one
      // the pointer is actually over -- the outer card keeps its own
      // last value, so reset it on the way out.
      if (card !== current) {
        clear(current);
        current = card;
      }
      if (!card) return;

      pendingEvent = { x: event.clientX, y: event.clientY };
      if (frame == null) frame = requestAnimationFrame(flush);
    };

    const onLeave = () => {
      clear(current);
      current = null;
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    // A card can be scrolled out from under a motionless pointer.
    window.addEventListener("blur", onLeave);

    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      if (frame != null) cancelAnimationFrame(frame);
      clear(current);
    };
  }, []);

  return null;
}

export interface BorderGlowProps extends React.HTMLAttributes<HTMLDivElement> {
  /** How close to the edge the pointer must be, 0-100. */
  edgeSensitivity?: number;
  /** Glow colour as "H S L". */
  glowColor?: string;
  /** Corner radius in px. Omit to keep the element's own rounding. */
  borderRadius?: number;
  /** How far the halo reaches past the card, in px. */
  glowRadius?: number;
  /** Opacity multiplier, 0.1-3.0. */
  glowIntensity?: number;
  /** Width of the directional cone, as a percentage (5-45). */
  coneSpread?: number;
  /** Three hex colours for the mesh gradient rim. */
  colors?: string[];
  /** Card clips its own content, so keep the halo inside it. */
  clipped?: boolean;
}

/**
 * A card with the rim. For new markup -- existing cards get the class
 * added instead, which is why this is deliberately thin.
 */
export const BorderGlow = React.forwardRef<HTMLDivElement, BorderGlowProps>(
  function BorderGlow(
    {
      children,
      className,
      edgeSensitivity = 30,
      glowColor = "40 80 80",
      borderRadius,
      glowRadius = 40,
      glowIntensity = 1.0,
      coneSpread = 25,
      colors = ["#c084fc", "#f472b6", "#38bdf8"],
      clipped = false,
      style,
      ...rest
    },
    ref
  ) {
    const vars = {
      "--edge-sensitivity": edgeSensitivity,
      "--glow-padding": `${glowRadius}px`,
      "--cone-spread": coneSpread,
      ...(borderRadius != null ? { "--border-radius": `${borderRadius}px` } : {}),
      ...buildGlowVars(glowColor, glowIntensity),
      ...buildGradientVars(colors),
      ...style,
    } as React.CSSProperties;

    return (
      <div
        {...rest}
        ref={ref}
        className={cn(GLOW_CLASS, clipped && "is-clipped", className)}
        style={vars}
      >
        {children}
      </div>
    );
  }
);

export default BorderGlow;
