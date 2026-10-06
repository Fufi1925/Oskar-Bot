"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Check, Copy, Loader2, X } from "lucide-react";
import { toast } from "sonner";

export const INPUT =
  "w-full min-w-0 rounded-xl border border-[var(--card-border)] bg-[var(--surface)] px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:opacity-50";
export const CARD =
  "rounded-2xl border border-[var(--card-border)] bg-[var(--card)]";
export function timestamp(value?: number | null) {
  if (!value || !Number.isFinite(value)) return "Noch nicht erfasst";
  return new Date(value * 1000).toLocaleString("de-DE");
}
export function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Die Anfrage konnte nicht abgeschlossen werden.";
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium ${tone === "good" ? "bg-emerald-400/10 text-emerald-300" : tone === "warn" ? "bg-amber-400/10 text-amber-300" : tone === "bad" ? "bg-rose-400/10 text-rose-300" : "bg-white/5 text-slate-400"}`}
    >
      {children}
    </span>
  );
}
export function Action({
  children,
  onClick,
  disabled,
  primary,
  danger,
  type = "button",
  label,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  primary?: boolean;
  danger?: boolean;
  type?: "button" | "submit";
  label?: string;
}) {
  return (
    <button
      type={type}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border px-3.5 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-40 ${danger ? "border-rose-400/20 bg-rose-400/10 text-rose-300 hover:bg-rose-400/15" : primary ? "border-primary bg-primary text-white hover:opacity-90" : "border-[var(--card-border)] bg-white/[0.025] text-slate-300 hover:bg-white/5"}`}
    >
      {children}
    </button>
  );
}
export function Section({
  title,
  description,
  children,
  aside,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className={CARD}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--card-border)] p-5">
        <div>
          <h2 className="text-base font-semibold text-slate-100">{title}</h2>
          {description && (
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {description}
            </p>
          )}
        </div>
        {aside}
      </header>
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  );
}
export function Empty({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--card-border)] px-5 py-10 text-center">
      <Check className="mx-auto mb-3 h-5 w-5 text-slate-500" />
      <p className="text-sm text-slate-300">{title}</p>
      {detail && (
        <p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p>
      )}
    </div>
  );
}
export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/5 py-2.5 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="max-w-[65%] break-words text-right text-slate-200">
        {value ?? "–"}
      </span>
    </div>
  );
}
export function CopyButton({
  value,
  label = "Kopieren",
}: {
  value: string;
  label?: string;
}) {
  return (
    <Action
      label={label}
      onClick={() => {
        navigator.clipboard
          .writeText(value)
          .then(() => toast.success("Kopiert."))
          .catch(() => toast.error("Die Zwischenablage ist nicht verfügbar."));
      }}
    >
      <Copy className="h-3.5 w-3.5" />
      {label}
    </Action>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-2">
      <span className="block text-xs font-medium text-slate-400">{label}</span>
      {children}
    </label>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex gap-2 rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-xs leading-5 text-amber-200"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
export type Confirmation = {
  title: string;
  description: string;
  actionLabel?: string;
  note?: boolean;
  run: (note: string) => Promise<unknown>;
};
export function ConfirmDialog({
  confirmation,
  busy,
  onCancel,
  onConfirm,
}: {
  confirmation: Confirmation;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (note: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [note, setNote] = useState("");
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    box.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return createPortal(
    <div
      className="fixed inset-0 z-[11000] flex items-center justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={box}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="owner-confirm-title"
        aria-describedby="owner-confirm-description"
        className={
          CARD + " my-auto w-full max-w-lg p-5 shadow-2xl outline-none sm:p-6"
        }
        onKeyDown={(event) => {
          if (event.key === "Escape" && !busy) onCancel();
          if (event.key === "Tab") {
            const nodes = Array.from(
              box.current?.querySelectorAll<HTMLElement>(
                "button:not([disabled]),textarea:not([disabled])",
              ) || [],
            );
            const first = nodes[0],
              last = nodes[nodes.length - 1];
            if (!first) {
              event.preventDefault();
              return;
            }
            if (
              event.shiftKey &&
              (document.activeElement === first ||
                document.activeElement === box.current)
            ) {
              event.preventDefault();
              last.focus();
            } else if (
              !event.shiftKey &&
              (document.activeElement === last ||
                document.activeElement === box.current)
            ) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <h2
            id="owner-confirm-title"
            className="text-lg font-semibold text-white"
          >
            {confirmation.title}
          </h2>
          <button
            type="button"
            aria-label="Dialog schließen"
            disabled={busy}
            onClick={onCancel}
            className="rounded-lg p-1 text-slate-400 focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p
          id="owner-confirm-description"
          className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-400"
        >
          {confirmation.description}
        </p>
        {confirmation.note && (
          <div className="mt-4">
            <Field label="Notiz für den Verlauf (optional)">
              <textarea
                className={INPUT}
                maxLength={500}
                rows={3}
                value={note}
                disabled={busy}
                onChange={(event) => setNote(event.target.value)}
              />
            </Field>
          </div>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Action disabled={busy} onClick={onCancel}>
            Abbrechen
          </Action>
          <Action primary disabled={busy} onClick={() => onConfirm(note)}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy
              ? "Wird gespeichert …"
              : confirmation.actionLabel || "Änderung bestätigen"}
          </Action>
        </div>
      </div>
    </div>,
    document.body,
  );
}
