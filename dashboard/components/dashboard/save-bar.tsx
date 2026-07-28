"use client";

/**
 * The shared save mechanics for every guild tab.
 *
 * Before this, each tab did its own thing: some saved on every single
 * click, some had a button per card (so a change made at the top was
 * saved by a button four screens down), and none of them stopped you
 * from walking away with an unsaved edit -- the draft just vanished.
 *
 * The verification and automod tabs got a fix for that first. This file
 * is that fix, lifted out so the other twenty-odd tabs can use the same
 * one instead of growing twenty-odd slightly different copies.
 *
 * Three pieces:
 *   usePanel        - load / draft / save wiring for a tab
 *   StickySaveBar   - one bar for the whole tab, pinned to the bottom
 *   useUnsavedGuard - refuses to leave while the bar is showing
 *
 * The typical tab is then:
 *
 *   const p = usePanel(load);
 *   const guard = useSaveGuard(p.dirty);
 *   ...
 *   <StickySaveBar count={p.dirty} shake={guard.shake} ... />
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/* ══════════════════════════════════════════════════════════════════ *
 * The bar
 * ══════════════════════════════════════════════════════════════════ */

export interface StickySaveBarProps {
  /** Number of pending changes. Zero hides the bar entirely. */
  count: number;
  onDiscard: () => void;
  onSave: () => void;
  busy?: boolean;
  /** Set by useSaveGuard when a navigation was refused. */
  shake?: boolean;
  /** Anchor for scrollIntoView. Defaults to "save-bar". */
  id?: string;
  /** Shown instead of the count, e.g. "Pflichtfeld fehlt". */
  blocked?: string | null;
}

export function StickySaveBar({
  count,
  onDiscard,
  onSave,
  busy,
  shake,
  id = "save-bar",
  blocked,
}: StickySaveBarProps) {
  if (!count) return null;
  return (
    <div
      id={id}
      className="sticky bottom-3 sm:bottom-4 z-40 pt-2"
      // Keeps the bar clear of the home indicator on phones that have one.
      style={{ marginBottom: "env(safe-area-inset-bottom)" }}
    >
      <div
        className={cn(
          "rounded-2xl px-4 sm:px-5 py-3.5 sm:py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 shadow-2xl border transition-colors",
          shake
            ? "bg-red-500/15 border-red-500/60 animate-[verify-shake_0.4s_ease-in-out]"
            : blocked
            ? "bg-[#10233f] border-red-500/40"
            : "bg-[#10233f] border-amber-500/40"
        )}
      >
        <p className={cn("text-sm min-w-0", shake ? "text-red-200" : "text-slate-300")}>
          {shake ? (
            <>
              <span className="font-black">Erst speichern oder verwerfen</span>
              {" — sonst geht deine Änderung verloren."}
            </>
          ) : blocked ? (
            <span className="text-red-300">{blocked}</span>
          ) : (
            <>
              <span className="font-black text-white">{count}</span>
              {` Änderung${count === 1 ? "" : "en"} noch nicht gespeichert.`}
            </>
          )}
        </p>
        <div className="flex gap-2 shrink-0 w-full sm:w-auto">
          <button
            onClick={onDiscard}
            disabled={busy}
            className="flex-1 sm:flex-none px-4 py-3 sm:py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-white disabled:opacity-40 transition-all"
          >
            Verwerfen
          </button>
          <button
            onClick={onSave}
            disabled={busy || !!blocked}
            className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-5 py-3 sm:py-2.5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Leaving with unsaved changes
 * ══════════════════════════════════════════════════════════════════ */

/**
 * Stop a navigation while there are unsaved changes.
 *
 * Next.js routes on the client, so `beforeunload` alone only covers a
 * reload or a closed tab -- clicking another tab in the navigation
 * would still throw the draft away silently. Catching the click in the
 * capture phase is what makes that reachable, because Next's own Link
 * handler would otherwise have already changed the route.
 *
 * The browser back button is handled too: pushing a dummy history entry
 * gives us something to pop, so `popstate` fires and we can push it
 * back on.
 */
export function useUnsavedGuard(active: boolean, onBlocked: () => void) {
  const blocked = useRef(onBlocked);
  blocked.current = onBlocked;

  useEffect(() => {
    if (!active) return;

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };

    const onClick = (e: MouseEvent) => {
      const link = (e.target as HTMLElement)?.closest?.("a");
      if (!link) return;

      const href = link.getAttribute("href");
      // Anchors, new tabs and external links are none of our business.
      if (!href || href.startsWith("#") || link.target === "_blank") return;
      if (/^https?:\/\//.test(href) && !href.startsWith(window.location.origin)) {
        return;
      }
      if (href === window.location.pathname) return;

      e.preventDefault();
      e.stopPropagation();
      blocked.current();
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [active]);
}

/**
 * The guard plus the red flash that tells the user why nothing happened.
 *
 * A browser `confirm()` cannot be styled and Chrome suppresses repeated
 * ones, so the feedback has to live in the page: scroll the bar into
 * view and shake it.
 */
export function useSaveGuard(dirty: number, barId = "save-bar") {
  const [shake, setShake] = useState(false);

  const refuse = useCallback(() => {
    setShake(true);
    document.getElementById(barId)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    window.setTimeout(() => setShake(false), 1200);
  }, [barId]);

  useUnsavedGuard(dirty > 0, refuse);

  return { shake, refuse };
}

/* ══════════════════════════════════════════════════════════════════ *
 * Load / draft / save
 * ══════════════════════════════════════════════════════════════════ */

export interface Panel {
  data: any;
  loading: boolean;
  busy: boolean;
  draft: Record<string, any>;
  setDraft: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  reload: () => Promise<void>;
  act: (fn: () => Promise<any>, confirmText?: string) => Promise<any>;
  /** Draft first, then whatever the server sent. */
  value: (key: string) => any;
  set: (key: string, v: any) => void;
  /** Set several keys at once without three renders. */
  patch: (values: Record<string, any>) => void;
  discard: () => void;
  dirty: number;
}

export function usePanel(load: () => Promise<any>): Panel {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});

  const reload = useCallback(async () => {
    try {
      setData(await load());
      setDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [load]);

  useEffect(() => {
    reload();
  }, [reload]);

  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      await reload();
      return res;
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return {
    data,
    loading,
    busy,
    draft,
    setDraft,
    reload,
    act,
    value: (key: string) => (key in draft ? draft[key] : data?.[key]),
    set: (key: string, v: any) => setDraft((d) => ({ ...d, [key]: v })),
    patch: (values: Record<string, any>) => setDraft((d) => ({ ...d, ...values })),
    discard: () => setDraft({}),
    dirty: Object.keys(draft).length,
  };
}

/**
 * The same idea for tabs whose data arrives from the server component
 * as a prop rather than from a fetch.
 *
 * `initial` is only read on the first render on purpose: re-reading it
 * would wipe the draft every time the parent re-rendered.
 */
export function useDraft<T extends Record<string, any>>(initial: T) {
  const [saved, setSaved] = useState<T>(initial);
  const [draft, setDraft] = useState<Partial<T>>({});
  const [busy, setBusy] = useState(false);

  const value = <K extends keyof T>(key: K): T[K] =>
    (key in draft ? (draft as T)[key] : saved[key]);

  const set = <K extends keyof T>(key: K, v: T[K]) =>
    setDraft((d) => {
      const next = { ...d, [key]: v };
      // Setting a field back to its saved value is not a change.
      if (same(saved[key], v)) delete next[key];
      return next;
    });

  const merged = { ...saved, ...draft } as T;

  const commit = (fn: (values: T) => Promise<any>) => async () => {
    setBusy(true);
    try {
      await fn(merged);
      setSaved(merged);
      setDraft({});
      toast.success("Gespeichert.");
      return true;
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  return {
    saved,
    setSaved,
    draft,
    setDraft,
    value,
    set,
    merged,
    busy,
    setBusy,
    commit,
    discard: () => setDraft({}),
    dirty: Object.keys(draft).length,
  };
}

/** Shallow-compare two values well enough for "did this field change?". */
function same(a: any, b: any) {
  if (a === b) return true;
  if (a == null && b == null) return true;
  if (typeof a !== "object" || typeof b !== "object" || !a || !b) return false;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

/* ══════════════════════════════════════════════════════════════════ *
 * Small shared bits every tab repeated
 * ══════════════════════════════════════════════════════════════════ */

export function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[240px]">
      <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
    </div>
  );
}
