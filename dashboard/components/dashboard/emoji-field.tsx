"use client";

/**
 * Textfelder mit Emoji-Auswahl.
 *
 * Der Bot bringt rund 140 eigene Emojis mit. Um eines in einen Text zu
 * setzen, musste man bisher seine Schreibweise kennen --
 * `<:name:1530375445785084005>`, achtzehnstellige ID inklusive. Das
 * ging nur im Reiter "Eigene Nachricht"; überall sonst -- Willkommen,
 * Verifizierung, Autoresponder, Gewinnspiele, Tickets -- blieb nur
 * abschreiben.
 *
 * Diese Datei ist die Antwort darauf, und zwar als *ein* Baustein statt
 * als 65 Kopien. Die Rechnerei drumherum ist nämlich jedes Mal
 * dieselbe und jedes Mal leicht falsch zu machen:
 *
 *   * an der Cursorposition einfügen, nicht am Ende
 *   * den Cursor danach hinter das Emoji setzen
 *   * die Zeichengrenze prüfen, *bevor* der Text zu lang wird
 *   * das Feld wiederfinden, in das eingefügt werden soll
 *
 * ── Zwei Sorten Feld ────────────────────────────────────────────────
 *
 * `EmojiText` ist für Fließtext: Nachrichten, Beschreibungen,
 * Überschriften, Fußzeilen. Ein Klick fügt das Emoji dort ein, wo der
 * Cursor steht, und man kann weitertippen.
 *
 * `EmojiOnly` ist für Felder, in die genau *ein* Emoji gehört: das
 * Symbol auf einem Knopf, eine Reaktionsrolle, eine Ticket-Kategorie.
 * Dort wäre Einfügen falsch -- Discord lehnt zwei Emojis auf einem
 * Knopf ab. Ein Klick **ersetzt** deshalb den Inhalt.
 *
 * ── Was hier bewusst *nicht* passiert ───────────────────────────────
 *
 * Felder, deren Inhalt nie in Discord landet, bekommen keine Auswahl:
 * Sicherheitsabfragen ("Servernamen tippen zum Bestätigen"),
 * Suchfelder, das Präfix, Zugangscodes. Ein Emoji darin wäre
 * bestenfalls sinnlos und schlimmstenfalls kaputt -- eine Abfrage, die
 * auf Zeichengleichheit prüft, ginge nicht mehr auf.
 */

import React from "react";
import { cn } from "@/lib/utils";
import { EmojiPicker, insertAtCursor } from "@/components/dashboard/emoji-picker";

/** Der Feldrahmen, wie ihn die Panels benutzen. */
const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 " +
  "text-sm text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";

/**
 * Ein Textfeld mit Emoji-Auswahl darunter.
 *
 * `limit` ist Discords Grenze für dieses Feld -- sie ist je nach Ort
 * verschieden: eine Nachricht 2000, eine Embed-Beschreibung 4096, ein
 * Titel 256, eine Fußzeile 2048. Deshalb wird sie übergeben und nicht
 * hier festgelegt: ein fester Wert wäre für Titel und Beschreibung
 * gleichzeitig falsch.
 */
export function EmojiText({
  value,
  onChange,
  limit,
  rows,
  placeholder,
  className,
  disabled,
  label = "Emoji einfügen",
  showCount,
  onLimitReached,
  onFocus,
}: {
  value: string;
  onChange: (next: string) => void;
  limit: number;
  /** Gesetzt = mehrzeilig. Fehlt = einzeilig. */
  rows?: number;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  label?: string;
  /** Zähler anzeigen. Bei langen Texten hilfreich, bei Titeln Lärm. */
  showCount?: boolean;
  /** Wird gerufen, wenn das Emoji nicht mehr hineinpasst. */
  onLimitReached?: (limit: number) => void;
  /**
   * Durchgereicht, nicht verschluckt.
   *
   * Das Willkommens-Formular merkt sich damit das zuletzt benutzte
   * Feld, damit seine Platzhalter-Knöpfe ({user}, {server_name} …)
   * wissen, wohin sie schreiben sollen. Ohne diese Weitergabe
   * schrieben sie nach dem Umbau ins falsche Feld -- oder in gar
   * keines.
   */
  onFocus?: (event: React.FocusEvent<HTMLTextAreaElement | HTMLInputElement>) => void;
}) {
  // Ein Ref auf das Feld, damit `insertAtCursor` weiß, wo der Cursor
  // steht. Ohne das landet jedes Emoji am Ende -- wer mitten im Satz
  // eines braucht, müsste es von Hand dorthin schieben.
  const fieldRef = React.useRef<HTMLTextAreaElement | HTMLInputElement | null>(
    null
  );

  const insert = (raw: string) => {
    const field = fieldRef.current;
    const { text, caret } = insertAtCursor(field, value, raw);

    // Vorher prüfen, nicht nachher. Schneidet erst Discord ab, trifft
    // es mitten in den Emoji-Code, und übrig bleibt eine kaputte Zahl
    // im Text.
    if (text.length > limit) {
      onLimitReached?.(limit);
      return;
    }

    onChange(text);

    // Den Cursor hinter das Emoji setzen, damit man weitertippen kann.
    // Erst im nächsten Bild -- vorher hat React den neuen Wert noch
    // nicht geschrieben und die Position würde überschrieben.
    requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(caret, caret);
    });
  };

  const shared = {
    value,
    onChange: (event: React.ChangeEvent<HTMLTextAreaElement | HTMLInputElement>) =>
      onChange(event.target.value),
    onFocus,
    maxLength: limit,
    placeholder,
    disabled,
    className: cn(INPUT, rows ? "resize-y" : "", className),
  };

  return (
    <div className="space-y-2">
      {rows ? (
        <textarea
          {...shared}
          ref={(node) => {
            fieldRef.current = node;
          }}
          rows={rows}
        />
      ) : (
        <input
          {...shared}
          ref={(node) => {
            fieldRef.current = node;
          }}
        />
      )}

      <div className="flex items-center gap-2">
        <EmojiPicker onPick={insert} label={label} />
        {showCount && (
          <p className="text-[11px] text-slate-600 ml-auto">
            {value.length} / {limit}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Emoji-Auswahl für ein Feld, das React *nicht* steuert.
 *
 * Die Ticket-Panels arbeiten mit `defaultValue` und speichern erst
 * beim Verlassen des Feldes (`onBlur`). Der Wert lebt dort im DOM,
 * nicht im Zustand -- `setState` hat also nichts, was es ändern
 * könnte.
 *
 * Deshalb wird hier direkt am Element gearbeitet: einfügen, den
 * Cursor setzen und dann selbst melden, dass sich etwas geändert hat.
 * Ohne diese Meldung bliebe die Änderung im Feld stehen und würde nie
 * gespeichert -- der Nutzer sähe sein Emoji und verlöre es beim
 * Neuladen.
 */
export function EmojiDraftField({
  defaultValue,
  onCommit,
  limit,
  rows,
  placeholder,
  className,
  label = "Emoji einfügen",
}: {
  defaultValue: string;
  /** Wird beim Verlassen des Feldes und nach jedem Emoji gerufen. */
  onCommit: (next: string) => void;
  limit: number;
  rows?: number;
  placeholder?: string;
  className?: string;
  label?: string;
}) {
  const fieldRef = React.useRef<HTMLTextAreaElement | HTMLInputElement | null>(
    null
  );

  const shared = {
    defaultValue,
    placeholder,
    maxLength: limit,
    onBlur: (event: React.FocusEvent<HTMLTextAreaElement | HTMLInputElement>) => {
      if (event.target.value !== defaultValue) onCommit(event.target.value);
    },
    className: cn(
      "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3",
      "text-sm text-white focus:outline-none focus:border-primary/50",
      rows ? "resize-y" : "",
      className
    ),
  };

  return (
    <div className="space-y-2">
      {rows ? (
        <textarea
          {...shared}
          ref={(node) => {
            fieldRef.current = node;
          }}
          rows={rows}
        />
      ) : (
        <input
          {...shared}
          ref={(node) => {
            fieldRef.current = node;
          }}
        />
      )}

      <EmojiPicker
        label={label}
        onPick={(raw) => {
          const field = fieldRef.current;
          if (!field) return;

          const { text, caret } = insertAtCursor(field, field.value, raw);
          if (text.length > limit) return;

          // Direkt ins Element schreiben: der Wert lebt hier im DOM,
          // ein `setState` hätte nichts, was es ändern könnte.
          field.value = text;
          // Und selbst melden -- sonst stünde das Emoji im Feld, würde
          // aber nie gespeichert. Beim Neuladen wäre es weg.
          onCommit(text);

          requestAnimationFrame(() => {
            field.focus();
            field.setSelectionRange(caret, caret);
          });
        }}
      />
    </div>
  );
}

/**
 * Ein Feld für genau ein Emoji.
 *
 * Ein Klick in der Auswahl **ersetzt** den Inhalt, statt einzufügen.
 * Auf einem Discord-Knopf ist genau ein Emoji erlaubt; zwei
 * hintereinander lehnt die API ab, und der Fehler käme erst beim
 * Absenden -- lange nach dem Klick, der ihn verursacht hat.
 *
 * Tippen bleibt erlaubt: Standard-Emojis wie 🎉 kommen aus der
 * Tastatur und stehen nicht in der Liste des Bots.
 */
export function EmojiOnly({
  value,
  onChange,
  placeholder = "🎉",
  className,
  disabled,
  label = "Emoji wählen",
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={cn(
          "w-16 bg-[#0b1626] border border-slate-800 rounded-xl px-2 py-3",
          "text-sm text-white text-center focus:outline-none",
          "focus:border-primary/50 transition-colors"
        )}
      />
      <EmojiPicker label={label} onPick={(raw) => onChange(raw)} />
    </div>
  );
}
