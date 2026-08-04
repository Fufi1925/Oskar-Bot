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
  const boxRef = useRef<HTMLDivElement | null>(null);

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
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
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
        onClick={() => setOpen((old) => !old)}
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

      {open && (
        <div className="absolute z-50 mt-2 w-[320px] sm:w-[380px] rounded-2xl border border-slate-700 bg-[#0d1728] shadow-2xl shadow-black/50 overflow-hidden">
          <div className="flex items-center gap-2 p-2.5 border-b border-slate-800">
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

          <div className="max-h-[300px] overflow-y-auto p-2.5">
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

          <p className="text-[10px] text-slate-600 px-3 py-2 border-t border-slate-800 leading-relaxed">
            Wird an der Stelle eingefügt, an der der Cursor steht.
          </p>
        </div>
      )}
    </div>
  );
}
