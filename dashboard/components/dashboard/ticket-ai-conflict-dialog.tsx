"use client";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Loader2, X } from "lucide-react";

export type KnowledgeConflict = { reference: string; version: string; title: string; content: string; source: string };
export function TicketAiConflictDialog({ message, conflicts, language, busy, onResolve, onCancel }: {
  message: string; conflicts: KnowledgeConflict[]; language: string; busy: boolean;
  onResolve: (action: "keep" | "replace") => void; onCancel: () => void;
}) {
  const t = (de: string, en: string) => language === "en" ? en : de;
  const dialog = useRef<HTMLDivElement>(null), keep = useRef<HTMLButtonElement>(null);
  const pending = useRef(busy); pending.current = busy;
  const cancel = useRef(onCancel); cancel.current = onCancel;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; keep.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); if (!pending.current) cancel.current(); }
      if (event.key !== "Tab") return;
      const nodes = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") || []);
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown",key);
    return () => { document.removeEventListener("keydown",key); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return createPortal(<div className="fixed inset-0 z-[11000] flex items-center justify-center overflow-y-auto bg-black/80 p-4 backdrop-blur-sm" onClick={event => { if(event.target === event.currentTarget && !busy) onCancel(); }}>
    <div ref={dialog} role="alertdialog" aria-modal="true" aria-labelledby="ticket-ai-conflict-title" aria-describedby="ticket-ai-conflict-description" className="my-auto w-full max-w-xl rounded-2xl border border-rose-500/45 cloudtix-workspace-card bg-[#202124] p-5 shadow-2xl sm:p-6">
      <div className="flex items-start justify-between gap-3"><AlertTriangle className="h-7 w-7 text-rose-400" /><button type="button" disabled={busy} onClick={onCancel} className="rounded-lg p-2 text-slate-400 hover:bg-white/5" aria-label={t("Schließen", "Close")}><X className="h-5 w-5" /></button></div>
      <h2 id="ticket-ai-conflict-title" className="mt-3 text-lg font-semibold text-white">{t("Diese Information gibt es bereits", "This information already exists")}</h2>
      <p id="ticket-ai-conflict-description" className="mt-2 text-sm leading-relaxed text-slate-400">{t("Ich habe ähnliche Angaben gefunden. Möchtest du das bisherige Wissen behalten oder die angezeigten alten Angaben durch deine neue Information ersetzen?", "I found similar information. Would you like to keep the existing knowledge or replace the older information shown below with your new statement?")}</p>
      <div className="mt-5 max-h-[45vh] space-y-4 overflow-y-auto pr-1">
        <div><h3 className="mb-2 text-xs font-medium text-slate-400">{t("Bisheriges Wissen", "Existing knowledge")}</h3><div className="space-y-2">{conflicts.map(item => <article key={item.reference} className="rounded-xl border border-white/10 cloudtix-workspace-field bg-[#18191c] p-3"><p className="text-[11px] text-slate-500">{item.source === "document" ? t("Wissensdatei", "Knowledge document") : t("Wissenseintrag", "Knowledge entry")} · {item.title}</p><p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-300 [overflow-wrap:anywhere]">{item.content}</p></article>)}</div></div>
        <div><h3 className="mb-2 text-xs font-medium text-rose-300">{t("Deine neue Information", "Your new information")}</h3><p className="whitespace-pre-wrap break-words rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-sm text-slate-200 [overflow-wrap:anywhere]">{message}</p></div>
      </div>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row"><button ref={keep} type="button" disabled={busy} onClick={() => onResolve("keep")} className="flex-1 rounded-xl border border-white/10 px-4 py-3 text-sm text-slate-200 hover:bg-white/5 disabled:opacity-40">{t("Altes Wissen behalten", "Keep existing knowledge")}</button><button type="button" disabled={busy} onClick={() => onResolve("replace")} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-3 text-sm font-medium text-white hover:bg-rose-500 disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{t("Neue Information behalten", "Keep new information")}</button></div>
    </div>
  </div>, document.body);
}
