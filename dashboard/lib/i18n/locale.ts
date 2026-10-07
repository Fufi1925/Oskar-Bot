"use client";

import { useSyncExternalStore } from "react";

// During hydration use the same default as the server. Afterwards subscribers
// render dates/numbers again whenever the website language changes.
let hydrated = false;
const listeners = new Set<() => void>();
function snapshot() { return typeof document !== "undefined" && document.documentElement.lang === "en" ? "en-GB" : "de-DE"; }
function subscribe(listener: () => void) { hydrated = true; listeners.add(listener); return () => { listeners.delete(listener); }; }
export function notifyLocaleChange() { for (const listener of listeners) listener(); }
export function websiteLocale(): string { return hydrated ? snapshot() : "de-DE"; }
export function useWebsiteLocale(): string { return useSyncExternalStore(subscribe, snapshot, () => "de-DE"); }
