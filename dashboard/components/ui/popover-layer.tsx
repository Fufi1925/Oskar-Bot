"use client";

/**
 * Die oberste Ebene der Seite.
 *
 * Jedes Menü, das aus seinem Kasten herausragen soll -- Rollenauswahl,
 * Kanalauswahl, Mitgliedersuche, Auswahlfelder, Sprachumschalter, die
 * Suche in der Kopfzeile, Glocke und Profilmenü -- lag hinter der
 * nächsten Karte. Der Emoji-Auswahl ging es genauso, und dort haben
 * zwei Anläufe nichts geändert, weil beide vom falschen Grund ausgingen.
 *
 * ── Warum ein höherer z-index nicht hilft ───────────────────────────
 *
 * Mehrere Bausteine eröffnen einen **Stapelkontext**: `.prox-row`
 * per `transform`, `.admin-glass` per `backdrop-filter`. Früher tat es
 * auch der Rand-Schimmer der Karten mit `isolation: isolate` — der ist
 * entfernt, die beiden anderen sind geblieben, und damit bleibt auch
 * das Problem.
 *
 * Ein Element kann seinen Stapelkontext **nicht verlassen**. Sein
 * z-index zählt nur gegenüber Geschwistern *innerhalb* der Karte, nie
 * gegenüber etwas ausserhalb. Weil die Karte selbst keinen z-index
 * hat, liegt die nächste Karte im Dokument darüber -- egal ob im Menü
 * `z-50`, `z-[100]` oder `z-[9999]` steht.
 *
 * `position: fixed` hilft ebenfalls nicht. Es ändert nur den
 * Bezugsrahmen für die Koordinaten (das Fenster statt des nächsten
 * positionierten Vorfahren); gemalt wird weiter im Stapelkontext des
 * Vorfahren, und `fixed` eröffnet sogar selbst einen.
 *
 * Und es ist nicht nur `isolation`. Denselben Käfig bauen:
 *   `.admin-glass`   backdrop-filter
 *   `.prox-row`      transform
 *   `.prox-tab`      transform
 *   jedes `backdrop-blur-*` aus Tailwind
 *
 * ── Der einzige Ausweg ──────────────────────────────────────────────
 *
 * Das Menü muss im **DOM** aus der Karte heraus. `createPortal` hängt
 * es an `document.body`, also in den obersten Stapelkontext der Seite.
 * Dort gewinnt der z-index wirklich gegen alles.
 *
 * Der Preis ist die Position: draussen gibt es keinen positionierten
 * Vorfahren mehr, an dem sich das Menü ausrichten könnte. Sie wird
 * hier gerechnet -- einmal, für alle Menüs, statt elfmal einzeln.
 *
 * ── Was das fürs Handy bedeutet ─────────────────────────────────────
 *
 * Auf einem schmalen Bildschirm ist genau das der Unterschied zwischen
 * benutzbar und nicht. Deshalb rechnet `measure()` gegen die echten
 * Fenstermasse statt feste Zahlen zu setzen:
 *
 *   * Die Breite wird auf die Fensterbreite gedeckelt. Ein Menü, das
 *     so breit ist wie sein Auslöser, wäre sonst am rechten Rand halb
 *     abgeschnitten.
 *   * Läuft es rechts hinaus, rutscht es nach links, bis es passt.
 *   * Die Höhe ist der Platz, der wirklich da ist. Vorher stand in
 *     den Menüs `max-h-64` -- auf einem liegenden Handy ist das mehr
 *     als der halbe Bildschirm, das Menü lief unten hinaus.
 *   * Ist unten zu wenig Platz und oben mehr, klappt es nach oben.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

/** Wo das Menü sitzt, in Fensterkoordinaten. */
export interface Spot {
  top: number;
  left: number;
  width: number;
  height: number;
  /** Klappt es nach oben auf? Für die Ursprungsecke der Animation. */
  up: boolean;
}

const MARGIN = 12; // Luft zum Fensterrand
const GAP = 8; // Luft zum Auslöser

/**
 * Die Rechnung, ausgelagert, damit sie ohne Browser prüfbar ist.
 *
 * Nimmt nur Zahlen und gibt Zahlen zurück -- kein DOM. Ein Test kann
 * damit ein schmales Handyfenster nachstellen und nachsehen, ob das
 * Menü im Bild bleibt.
 */
export function measure(opts: {
  anchor: { top: number; left: number; right: number; bottom: number; width: number };
  view: { width: number; height: number };
  /** "anchor" = so breit wie der Auslöser, sonst feste Breite. */
  width: number | "anchor";
  /** Nie höher als das. */
  maxHeight: number;
  /** Nie niedriger als das, auch wenn es dann übersteht. */
  minHeight: number;
  /** Rechts- statt linksbündig ausrichten. */
  align: "start" | "end";
}): Spot {
  const { anchor, view, align } = opts;

  // ---- Breite ------------------------------------------------------
  // Auf dem Handy ist die Fensterbreite die harte Grenze. Ohne diesen
  // Deckel steht ein 380 breites Menü auf einem 360 breiten Gerät
  // immer über den Rand.
  const room = view.width - 2 * MARGIN;
  const wanted = opts.width === "anchor" ? anchor.width : opts.width;
  const width = Math.max(0, Math.min(wanted, room));

  // ---- Waagerecht --------------------------------------------------
  let left = align === "end" ? anchor.right - width : anchor.left;

  // Läuft es rechts hinaus, so weit nach links schieben, wie nötig.
  if (left + width + MARGIN > view.width) {
    left = view.width - width - MARGIN;
  }
  // Und niemals links hinaus. Diese Reihenfolge ist wichtig: bei einem
  // Fenster, das schmaler ist als das Menü, gewinnt der linke Rand.
  if (left < MARGIN) left = MARGIN;

  // ---- Senkrecht ---------------------------------------------------
  const above = anchor.top - GAP - MARGIN;
  const below = view.height - anchor.bottom - GAP - MARGIN;

  // Nach oben nur, wenn unten wirklich zu wenig ist UND oben mehr.
  // Sonst klappt ein Menü nach oben auf, das zwei Zeilen zeigt,
  // obwohl unten Platz für zehn wäre.
  const up = below < Math.min(220, opts.maxHeight) && above > below;

  const height = Math.max(
    opts.minHeight,
    Math.min(up ? above : below, opts.maxHeight)
  );

  const top = up ? anchor.top - GAP - height : anchor.bottom + GAP;

  return { top, left, width, height, up };
}

/**
 * Menü, das an `document.body` hängt und unter seinem Auslöser sitzt.
 *
 * `anchor` ist das Element, an dem es klebt -- meist der Knopf. Es
 * dient zugleich als Ausnahme beim Klick daneben, sonst würde der
 * Klick, der das Menü öffnet, es sofort wieder schliessen.
 */
export function PopoverLayer({
  anchor,
  open,
  onClose,
  children,
  className,
  width = "anchor",
  maxHeight = 420,
  minHeight = 140,
  align = "start",
  /**
   * Immer die volle gerechnete Höhe einnehmen statt nur zu deckeln.
   *
   * Für die Emoji-Auswahl: sie hat Kopf- und Fusszeile, und die Liste
   * dazwischen soll den Rest füllen. Für ein Menü aus fünf Einträgen
   * wäre eine feste Höhe dagegen nur unnötig viel Leerraum.
   */
  fill = false,
}: {
  anchor: React.RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  width?: number | "anchor";
  maxHeight?: number;
  minHeight?: number;
  align?: "start" | "end";
  fill?: boolean;
}) {
  const [spot, setSpot] = React.useState<Spot | null>(null);
  const popRef = React.useRef<HTMLDivElement | null>(null);

  // `document` gibt es beim Rendern auf dem Server nicht. Ohne diesen
  // Riegel bricht der Aufbau der Seite ab, bevor etwas zu sehen ist.
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const place = React.useCallback(() => {
    const el = anchor.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    setSpot(
      measure({
        anchor: {
          top: box.top,
          left: box.left,
          right: box.right,
          bottom: box.bottom,
          width: box.width,
        },
        view: { width: window.innerWidth, height: window.innerHeight },
        width,
        maxHeight,
        minHeight,
        align,
      })
    );
  }, [anchor, width, maxHeight, minHeight, align]);

  // Sofort messen, wenn geöffnet wird -- nicht erst nach einem Bild.
  // `useLayoutEffect` schreibt die Position, bevor der Browser malt;
  // mit `useEffect` blitzt das Menü einmal oben links auf.
  //
  // Auf dem Server gibt es kein Layout, und React warnt zu Recht.
  // Dort ist `useEffect` richtig -- gerendert wird ohnehin nichts,
  // weil `mounted` noch false ist.
  const useIsoLayout =
    typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;
  useIsoLayout(() => {
    if (open) place();
  }, [open, place]);

  // Beim Scrollen und Drehen mitwandern.
  //
  // Ein `fixed` Element bleibt sonst stehen, während die Seite sich
  // bewegt -- es hinge dann im Nichts statt unter seinem Knopf.
  // `capture` ist nötig, weil der Bildlauf in einem inneren Bereich
  // stattfinden kann und nicht am Fenster.
  React.useEffect(() => {
    if (!open) return;
    const update = () => place();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open, place]);

  // Klick daneben schliesst, Escape auch.
  //
  // Beide Bereiche prüfen, nicht nur den Auslöser: seit das Menü per
  // Portal an `document.body` hängt, liegt es nicht mehr in ihm. Eine
  // Prüfung nur auf den Auslöser würde das Menü bei jedem Klick
  // hinein sofort schliessen -- bei einer Mehrfachauswahl könnte man
  // dann nur noch einen Eintrag pro Öffnen setzen.
  React.useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      const inAnchor = anchor.current?.contains(target);
      const inPopup = popRef.current?.contains(target);
      if (!inAnchor && !inPopup) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, anchor]);

  if (!open || !mounted || !spot) return null;

  return createPortal(
    <div
      ref={popRef}
      style={{
        top: spot.top,
        left: spot.left,
        width: spot.width,
        // `fill` gibt die volle Höhe, sonst nur die Obergrenze. So
        // bleibt ein kurzes Menü kurz und ein langes im Bild.
        ...(fill ? { height: spot.height } : { maxHeight: spot.height }),
      }}
      className={cn(
        // `fixed`, weil es hier draussen keinen positionierten
        // Vorfahren mehr gibt, an dem `absolute` sich ausrichten
        // könnte. Die Koordinaten oben sind Fensterkoordinaten.
        //
        // Der hohe z-index wirkt erst *hier*. Stünde dieses Element
        // noch in einer Karte mit `isolation: isolate`, wäre der Wert
        // egal -- er zählte nur gegen Geschwister in der Karte. Er
        // wirkt, weil das Portal oben es an `document.body` gehängt
        // hat, also in den obersten Stapelkontext der Seite.
        "fixed z-[9999] flex flex-col overflow-hidden",
        className
      )}
    >
      {children}
    </div>,
    document.body
  );
}
