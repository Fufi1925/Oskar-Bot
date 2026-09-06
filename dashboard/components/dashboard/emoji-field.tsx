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
import { EmojiPicker } from "@/components/dashboard/emoji-picker";
import { DiscordEmoji } from "@/components/dashboard/discord-emoji";

/** Der Feldrahmen, wie ihn die Panels benutzen. */
const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 " +
  "text-sm text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";

const CUSTOM = /<(a?):([A-Za-z0-9_]+):(\d{5,22})>|<emoji:(\d{5,22})>/g;

function serialiseRich(root: HTMLElement): string {
  let out = "";
  for (const node of Array.from(root.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) out += node.textContent || "";
    else if (node instanceof HTMLImageElement && node.dataset.emojiRaw) out += node.dataset.emojiRaw;
    else if (node instanceof HTMLBRElement) out += "\n";
    else if (node instanceof HTMLElement) out += serialiseRich(node);
  }
  return out;
}

function drawRich(root: HTMLElement, raw: string) {
  const fragment = document.createDocumentFragment();
  let cursor = 0;
  let match: RegExpExecArray | null;
  CUSTOM.lastIndex = 0;
  while ((match = CUSTOM.exec(raw)) !== null) {
    if (match.index > cursor) fragment.append(document.createTextNode(raw.slice(cursor, match.index)));
    const img = document.createElement("img");
    const id = match[3] || match[4];
    const name = match[2] || "emoji";
    img.src = `https://cdn.discordapp.com/emojis/${id}.${match[1] === "a" ? "gif" : "png"}?size=48&quality=lossless`;
    img.alt = `:${name}:`;
    img.title = `:${name}:`;
    img.dataset.emojiRaw = match[0];
    img.contentEditable = "false";
    img.draggable = false;
    img.className = "inline-block h-[1.35em] w-[1.35em] object-contain align-[-0.22em] mx-0.5";
    fragment.append(img);
    cursor = match.index + match[0].length;
  }
  if (cursor < raw.length) fragment.append(document.createTextNode(raw.slice(cursor)));
  root.replaceChildren(fragment);
  root.dataset.empty = raw ? "false" : "true";
}

/** A contenteditable field is required here: textarea/input elements can only
 * paint characters, never Discord emoji images. The raw Discord syntax still
 * lives in React state and is what gets saved. */
function RichEmojiEditor({
  value, onChange, limit, rows, placeholder, disabled, className, onLimitReached, onFocus, onBlur,
}: {
  value: string; onChange: (next: string) => void; limit: number; rows?: number;
  placeholder?: string; disabled?: boolean; className?: string;
  onLimitReached?: (limit: number) => void; onFocus?: (event: any) => void;
  onBlur?: (event: React.FocusEvent<HTMLDivElement>) => void;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const range = React.useRef<Range | null>(null);

  React.useLayoutEffect(() => {
    const root = ref.current;
    if (root && serialiseRich(root) !== value) drawRich(root, value);
  }, [value]);

  const remember = () => {
    const selection = window.getSelection();
    if (selection?.rangeCount && ref.current?.contains(selection.anchorNode)) {
      range.current = selection.getRangeAt(0).cloneRange();
    }
  };

  const commit = () => {
    const root = ref.current;
    if (!root) return;
    const raw = serialiseRich(root);
    root.dataset.empty = raw ? "false" : "true";
    if (raw.length > limit) {
      drawRich(root, value);
      onLimitReached?.(limit);
      return;
    }
    onChange(raw);
    remember();
  };

  const insertRaw = React.useCallback((raw: string) => {
    const root = ref.current;
    if (!root || disabled) return;
    root.focus();
    const selection = window.getSelection();
    const saved = range.current;
    if (saved && root.contains(saved.commonAncestorContainer)) {
      selection?.removeAllRanges(); selection?.addRange(saved);
    }
    let active = selection?.rangeCount ? selection.getRangeAt(0) : null;
    if (!active || !root.contains(active.commonAncestorContainer)) {
      active = document.createRange();
      active.selectNodeContents(root);
      active.collapse(false);
      selection?.removeAllRanges();
      selection?.addRange(active);
    }
    const current = serialiseRich(root);
    if (current.length + raw.length > limit) return onLimitReached?.(limit);
    const holder = document.createElement("span");
    drawRich(holder, raw);
    const nodes = Array.from(holder.childNodes);
    if (active) {
      active.deleteContents();
      for (const node of nodes) { active.insertNode(node); active.setStartAfter(node); active.collapse(true); }
      selection?.removeAllRanges(); selection?.addRange(active);
    } else {
      nodes.forEach((node) => root.append(node));
    }
    commit();
  }, [disabled, limit, onLimitReached, value]);

  React.useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const handler = (event: Event) => insertRaw(String((event as CustomEvent).detail || ""));
    root.addEventListener("rich-text-insert", handler);
    return () => root.removeEventListener("rich-text-insert", handler);
  }, [insertRaw]);

  return (
    <div
      ref={ref}
      contentEditable={!disabled}
      role="textbox"
      aria-multiline={Boolean(rows)}
      data-placeholder={placeholder || ""}
      data-empty={value ? "false" : "true"}
      suppressContentEditableWarning
      onFocus={onFocus}
      onInput={commit}
      onKeyUp={remember}
      onMouseUp={remember}
      onBlur={(event) => { remember(); onBlur?.(event); }}
      onPaste={(event) => {
        event.preventDefault();
        insertRaw(event.clipboardData.getData("text/plain"));
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          if (!rows) return event.preventDefault();
          event.preventDefault(); insertRaw("\n");
        }
      }}
      className={cn(
        INPUT,
        "min-h-[46px] h-auto whitespace-pre-wrap break-words cursor-text",
        "[data-empty=true]:before:content-[attr(data-placeholder)] [data-empty=true]:before:text-slate-600",
        rows && "overflow-y-auto",
        disabled && "opacity-50 cursor-not-allowed",
        className
      )}
      style={rows ? { minHeight: `${Math.max(3, rows) * 24 + 26}px` } : undefined}
    />
  );
}

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
  const wrapper = React.useRef<HTMLDivElement>(null);
  const insert = (raw: string) => {
    wrapper.current?.querySelector<HTMLElement>("[contenteditable]")?.dispatchEvent(
      new CustomEvent("rich-text-insert", { detail: raw })
    );
  };

  return (
    <div className="space-y-2" ref={wrapper}>
      <RichEmojiEditor
        value={value}
        onChange={onChange}
        limit={limit}
        rows={rows}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
        onLimitReached={onLimitReached}
        onFocus={onFocus}
      />

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
 * beim Verlassen des Feldes (`onBlur`). Ein lokaler Entwurf hält deshalb
 * den Rich-Text während des Tippens fest; erst beim Verlassen geht der
 * unveränderte Discord-Rohtext an den bisherigen Speicherpfad.
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
  const [draft, setDraft] = React.useState(defaultValue);
  const wrapper = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => setDraft(defaultValue), [defaultValue]);

  return (
    <div className="space-y-2" ref={wrapper}>
      <RichEmojiEditor
        value={draft}
        onChange={setDraft}
        limit={limit}
        rows={rows}
        placeholder={placeholder}
        className={className}
        onBlur={() => { if (draft !== defaultValue) onCommit(draft); }}
      />
      <EmojiPicker
        label={label}
        onPick={(raw) => {
          wrapper.current?.querySelector<HTMLElement>("[contenteditable]")?.dispatchEvent(
            new CustomEvent("rich-text-insert", { detail: raw })
          );
          // The rich editor updates draft synchronously through its input path;
          // committing on blur keeps the previous API behaviour.
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
  const custom = /^(?:<a?:[A-Za-z0-9_]+:\d{5,22}>|<emoji:\d{5,22}>)$/.test(value);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {custom ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange("")}
          title="Emoji entfernen"
          className={cn(
            "relative w-16 h-[46px] bg-[#0b1626] border border-primary/30 rounded-xl",
            "flex items-center justify-center hover:border-primary/60 transition-colors",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <DiscordEmoji value={value} className="h-7 w-7" />
          <span className="absolute right-1 top-0.5 text-[10px] text-slate-600">×</span>
        </button>
      ) : (
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
      )}
      <EmojiPicker label={label} onPick={(raw) => onChange(raw)} />
    </div>
  );
}
