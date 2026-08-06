"use client";

/**
 * Auswahl für die eigenen Emojis des Bots.
 *
 * Der Bot bringt rund 140 eigene Emojis mit. Um eines davon in eine
 * Nachricht zu setzen, musste man bisher seine Schreibweise kennen --
 * `<:name:1530375445785084005>`, achtzehnstellige ID inklusive. In der
 * Praxis hieß das: aus dem Quelltext abschreiben oder im Chat
 * `\:name:` tippen und das Ergebnis herüberkopieren.
 *
 * Hier stehen sie als Kacheln, nach Zweck gruppiert und durchsuchbar.
 * Ein Klick setzt das Emoji an der Stelle ein, an der der Cursor
 * gerade steht -- nicht am Ende. Wer mitten im Satz eines braucht,
 * müsste es sonst von Hand dorthin schieben.
 *
 * Die Liste kommt vom Bot und wird dort aus `utils/emoji.py` gelesen.
 * Eine zweite, hier gepflegte Aufstellung würde beim ersten neuen
 * Emoji auseinanderlaufen.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, Search, Smile, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface BotEmoji {
  key: string;
  name: string;
  id: string;
  animated: boolean;
  /** Die fertige Schreibweise, genau so wie sie in den Text muss. */
  raw: string;
  group: string;
  url: string;
}

/**
 * Ein Emoji an der Cursorposition einsetzen.
 *
 * Exportiert, weil beide Aufrufer (das freie Textfeld und die
 * V2-Blöcke) dieselbe Rechnung brauchen und eine zweite Kopie beim
 * nächsten Sonderfall auseinanderliefe.
 */
export function insertAtCursor(
  field: HTMLTextAreaElement | HTMLInputElement | null,
  value: string,
  insert: string
): { text: string; caret: number } {
  // Ohne Feld -- etwa wenn es gerade nicht sichtbar ist -- hinten
  // anhängen. Das ist die Stelle, an der ein Mensch es erwartet.
  if (!field) {
    const joined = value + insert;
    return { text: joined, caret: joined.length };
  }

  const start = field.selectionStart ?? value.length;
  const end = field.selectionEnd ?? start;
  const text = value.slice(0, start) + insert + value.slice(end);
  return { text, caret: start + insert.length };
}

export function EmojiPicker({
  onPick,
  label = "Emoji einfügen",
  className,
}: {
  onPick: (raw: string) => void;
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [emojis, setEmojis] = useState<BotEmoji[]>([]);
  const [query, setQuery] = useState("");
  // Wo das Feld auf dem Bildschirm sitzt.
  //
  // Warum das Feld per Portal an `document.body` hängt
  // ---------------------------------------------------
  // Die Karten tragen `.border-glow-card`, und die setzt
  // `isolation: isolate` — für ihre eigenen `z-index: -1`-Ebenen
  // nötig, aber sie eröffnet damit einen **Stapelkontext**.
  //
  // Ein Element kann seinen Stapelkontext **nicht verlassen**. Egal
  // wie hoch sein z-index ist, es konkurriert nur mit Geschwistern
  // *innerhalb* der Karte — nie mit etwas ausserhalb. Und weil die
  // Karte selbst keinen z-index hat, liegt die nächste Karte im
  // Dokument darüber.
  //
  // Zwei Anläufe sind daran gescheitert, beide aus demselben Irrtum:
  //
  //   1. `z-50` → `z-[100]`. Der Wert war nie das Problem.
  //   2. `absolute` → `fixed`. Auch falsch: `fixed` ändert nur den
  //      Bezugsrahmen für die Koordinaten (das Fenster statt des
  //      nächsten positionierten Vorfahren). Die Malfläche bleibt der
  //      Stapelkontext des Vorfahren — `fixed` erzeugt sogar selbst
  //      einen. Es kommt damit genauso wenig heraus.
  //
  // Der einzige Ausweg ist, das Feld im **DOM** aus der Karte
  // herauszunehmen. `createPortal` hängt es an `document.body`, also
  // in den obersten Stapelkontext der Seite. Dort gewinnt der z-index
  // wirklich gegen alles andere.
  //
  // Der Preis: die Position muss selbst gerechnet werden, weil das
  // Feld keinen positionierten Vorfahren mehr hat, an dem es sich
  // ausrichten könnte.
  const [spot, setSpot] = useState<{
    top: number;
    left: number;
    height: number;
  } | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const popRef = useRef<HTMLDivElement | null>(null);

  // `document` gibt es beim Rendern auf dem Server nicht. Ohne diesen
  // Riegel bricht der Aufbau der Seite ab, bevor irgendetwas zu sehen
  // ist.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  /**
   * Das Feld unter den Knopf legen — und dabei im Bild bleiben.
   *
   * Gemessen wird beim Öffnen, nicht beim Aufbau der Seite: die
   * Fensterbreite ändert sich, und der Knopf kann in einem Bereich
   * sitzen, der erst später sichtbar wird.
   */
  const place = useCallback(() => {
    const button = boxRef.current?.getBoundingClientRect();
    if (!button) return;

    const width = window.innerWidth >= 640 ? 380 : 320;
    const margin = 12;
    const gap = 8;

    // ---- Waagerecht ------------------------------------------------
    // Standard: linksbündig zum Knopf, wie es ein Menü tut.
    let left = button.left;

    // Läuft es rechts hinaus, an der rechten Kante des Knopfes
    // ausrichten — dann wächst es nach links, dorthin wo Platz ist.
    if (left + width + margin > window.innerWidth) {
      left = button.right - width;
    }
    // Und falls es dadurch links hinausrutscht (schmales Fenster),
    // einfach an den linken Rand.
    if (left < margin) left = margin;

    // ---- Senkrecht --------------------------------------------------
    //
    // Hier lag der zweite gemeldete Fehler: das Feld war schlicht zu
    // hoch und lief unten aus dem Bild. Vorher stand hier eine feste
    // Zahl (420) und eine feste Höhe der Liste (`max-h-[300px]`) --
    // die passt auf einem grossen Bildschirm und auf einem kleinen
    // nicht.
    //
    // Jetzt wird gerechnet, wie viel Platz wirklich da ist, und die
    // Liste bekommt genau so viel. Sie scrollt ohnehin.
    const above = button.top - gap - margin;
    const below = window.innerHeight - button.bottom - gap - margin;

    // Die Seite mit mehr Platz gewinnt -- aber unten nur, wenn dort
    // wenigstens etwas Brauchbares hinpasst. Sonst klappt ein Feld
    // nach unten auf, das nur zwei Reihen zeigt, obwohl oben Platz
    // für zehn wäre.
    const openUp = below < 260 && above > below;
    const room = Math.max(160, Math.min(openUp ? above : below, 420));

    const top = openUp ? button.top - gap - room : button.bottom + gap;

    setSpot({ top, left, height: room });
  }, []);

  // Beim Scrollen und bei Größenänderung mitwandern.
  //
  // Ein `fixed` Element bleibt sonst stehen, während die Seite sich
  // bewegt — es hinge dann irgendwo im Nichts statt unter seinem
  // Knopf. `capture` ist nötig, weil der Bildlauf in einem inneren
  // Bereich stattfinden kann und nicht am Fenster.
  useEffect(() => {
    if (!open) return;

    const update = () => place();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open, place]);

  // Erst laden, wenn jemand die Auswahl öffnet. Sie hängt an jedem
  // Textfeld; alle beim Aufbau der Seite laden zu lassen wären ein
  // Dutzend gleicher Abfragen für etwas, das oft nicht gebraucht wird.
  const load = useCallback(async () => {
    if (emojis.length || loading) return;
    setLoading(true);
    try {
      const answer = await api.getBotEmojis();
      setEmojis(answer?.emojis ?? []);
      setError("");
    } catch (err: any) {
      setError(err?.message || "Die Emojis ließen sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [emojis.length, loading]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  // Klick daneben schließt. Ohne das bleibt die Auswahl offen, sobald
  // man woanders weiterarbeitet, und verdeckt das Feld darunter.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;

      // Beide Bereiche prüfen, nicht nur den Knopf.
      //
      // Seit das Feld per Portal an `document.body` hängt, liegt es
      // nicht mehr innerhalb von `boxRef` — ein Klick auf ein Emoji
      // hätte die Auswahl damit sofort geschlossen. Man hätte nach
      // jedem Emoji neu öffnen müssen.
      const inButton = boxRef.current?.contains(target);
      const inPopup = popRef.current?.contains(target);

      if (!inButton && !inPopup) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const shown = needle
      ? emojis.filter(
          (entry) =>
            entry.name.toLowerCase().includes(needle) ||
            entry.key.toLowerCase().includes(needle)
        )
      : emojis;

    const buckets = new Map<string, BotEmoji[]>();
    for (const entry of shown) {
      const list = buckets.get(entry.group) ?? [];
      list.push(entry);
      buckets.set(entry.group, list);
    }
    return [...buckets.entries()];
  }, [emojis, query]);

  return (
    <div className={cn("relative", className)} ref={boxRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((old) => {
            const next = !old;
            if (next) place();
            return next;
          });
        }}
        title={label}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-black uppercase tracking-wider transition-colors",
          open
            ? "border-primary/50 text-primary bg-primary/10"
            : "border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700"
        )}
      >
        <Smile className="h-3.5 w-3.5" />
        Emoji
      </button>

      {open && spot && mounted && createPortal(
        <div
          ref={popRef}
          // Hängt per Portal an `document.body`, nicht in der Karte.
          //
          // Die Karte setzt `isolation: isolate` und ist damit ein
          // Stapelkontext. Siehe oben — ein Kind kommt da nicht heraus,
          // mit einem höheren z-index noch mit `position: fixed`.
          // Beides wurde versucht, beides war wirkungslos. Nur ein
          // Ortswechsel im DOM hilft.
          //
          // `fixed` bleibt trotzdem richtig: hier draussen gibt es
          // keinen positionierten Vorfahren mehr, an dem sich ein
          // `absolute` ausrichten könnte.
          style={{
            top: spot.top,
            left: spot.left,
            // Genau so hoch, wie Platz ist. Vorher stand hier nichts
            // und in der Liste `max-h-[300px]` — auf einem kleinen
            // Fenster lief das Feld deshalb unten hinaus.
            height: spot.height,
          }}
          className={cn(
            "fixed w-[320px] sm:w-[380px] z-[9999]",
            "flex flex-col",
            "rounded-2xl border border-slate-700 bg-[#0d1728]",
            "shadow-2xl shadow-black/50 overflow-hidden"
          )}
        >
          <div className="flex items-center gap-2 p-2.5 border-b border-slate-800 shrink-0">
            <div className="relative flex-1">
              <Search className="h-3.5 w-3.5 text-slate-600 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Suchen"
                className="w-full bg-[#0a1628] border border-slate-800 rounded-lg pl-8 pr-2 py-1.5 text-[12px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-700"
              />
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-lg text-slate-600 hover:text-slate-300"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-2.5">
            {loading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 text-primary animate-spin opacity-50" />
              </div>
            )}

            {error && !loading && (
              <p className="text-[12px] text-red-300/80 py-4 px-1 leading-relaxed">
                {error}
              </p>
            )}

            {!loading && !error && grouped.length === 0 && (
              <p className="text-[12px] text-slate-600 py-6 text-center">
                Nichts gefunden.
              </p>
            )}

            {grouped.map(([group, entries]) => (
              <div key={group} className="mb-3 last:mb-0">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-1.5 px-0.5">
                  {group}
                </p>
                <div className="grid grid-cols-8 gap-1">
                  {entries.map((entry) => (
                    <button
                      key={entry.raw}
                      type="button"
                      title={`:${entry.name}:`}
                      onClick={() => {
                        onPick(entry.raw);
                        // Offen lassen: wer eines einsetzt, setzt oft
                        // gleich noch eines. Zum Schließen gibt es das
                        // Kreuz, Escape und den Klick daneben.
                      }}
                      className="aspect-square grid place-items-center rounded-lg hover:bg-white/[0.06] transition-colors p-1"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={entry.url}
                        alt={`:${entry.name}:`}
                        loading="lazy"
                        className="h-5 w-5 object-contain"
                      />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <p className="text-[10px] text-slate-600 px-3 py-2 border-t border-slate-800 leading-relaxed shrink-0">
            Wird an der Stelle eingefügt, an der der Cursor steht.
          </p>
        </div>,
        document.body
      )}
    </div>
  );
}
