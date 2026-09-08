"use client";

import React from "react";
import {
  CalendarDays,
  Check,
  Globe2,
  Home,
  Languages,
  Loader2,
  Moon,
  Save,
  Sun,
} from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n/LanguageContext";

const DEFAULTS = {
  language: "de",
  theme: "dark",
  timezone: "Europe/Berlin",
  number_format: "de-DE",
  date_format: "medium",
  start_page: "/dashboard",
};
const TIMEZONES = [
  "Europe/Berlin",
  "Europe/London",
  "UTC",
  "America/New_York",
  "America/Los_Angeles",
  "Asia/Tokyo",
];

function applyTheme(theme: string) {
  const value = theme === "light" ? "light" : "dark";
  localStorage.setItem("dashboard-theme", value);
  document.documentElement.dataset.theme = value;
  document.documentElement.style.colorScheme = value;
  window.dispatchEvent(
    new CustomEvent("dashboard-theme-change", { detail: value }),
  );
}

function publishPreferences(value: any) {
  localStorage.setItem("account-timezone", value.timezone);
  localStorage.setItem("account-number-format", value.number_format);
  localStorage.setItem("account-date-format", value.date_format);
  localStorage.setItem("account-start-page", value.start_page);
  window.dispatchEvent(
    new CustomEvent("account-preferences-change", { detail: value }),
  );
}

export function AccountPreferencesPanel({ userId }: { userId: string }) {
  const { setLanguage } = useLanguage();
  const [form, setForm] = React.useState<any>(DEFAULTS);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let active = true;
    api
      .getAccountPreferences(userId)
      .then((data) => {
        if (!active) return;
        const next = { ...DEFAULTS, ...data };
        setForm(next);
        setLanguage(next.language);
        applyTheme(next.theme);
        publishPreferences(next);
      })
      .catch((err: any) => {
        if (active)
          setError(
            err?.message || "Einstellungen konnten nicht geladen werden.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // setLanguage is supplied by context and intentionally not a dependency:
    // its function identity changes when the language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const set = (key: string, value: string) => {
    setSaved(false);
    setForm((old: any) => ({ ...old, [key]: value }));
    if (key === "language") setLanguage(value as "de" | "en");
    if (key === "theme") applyTheme(value);
  };

  const save = async () => {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const value = await api.saveAccountPreferences(userId, form);
      setForm((old: any) => ({ ...old, ...value }));
      publishPreferences(value);
      setSaved(true);
    } catch (err: any) {
      setError(
        err?.message || "Einstellungen konnten nicht gespeichert werden.",
      );
    } finally {
      setSaving(false);
    }
  };

  const now = new Date();
  const datePreview =
    form.date_format === "iso"
      ? new Intl.DateTimeFormat("sv-SE", { timeZone: form.timezone }).format(
          now,
        )
      : new Intl.DateTimeFormat(form.number_format, {
          timeZone: form.timezone,
          dateStyle:
            form.date_format === "short"
              ? "short"
              : form.date_format === "long"
                ? "full"
                : "medium",
          timeStyle: "short",
        }).format(now);
  const numberPreview = new Intl.NumberFormat(form.number_format).format(
    1234567.89,
  );

  return (
    <section
      id="einstellungen"
      className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]"
    >
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-fuchsia-300">
            <Globe2 className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-[0.2em]">
              Persönliche Einstellungen
            </span>
          </div>
          <h2 className="mt-2 text-xl font-bold text-white">
            Darstellung und Startseite
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Diese Auswahl wird mit deinem Konto auf allen Geräten
            synchronisiert.
          </p>
        </div>
        <button
          type="button"
          onClick={save}
          disabled={loading || saving}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-fuchsia-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-fuchsia-500 disabled:opacity-50"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : saved ? (
            <Check className="h-4 w-4" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saved ? "Gespeichert" : "Einstellungen speichern"}
        </button>
      </div>

      {loading ? (
        <div className="grid place-items-center p-10">
          <Loader2 className="h-5 w-5 animate-spin text-fuchsia-400" />
        </div>
      ) : (
        <div className="grid gap-px bg-slate-800 md:grid-cols-2">
          <div className="space-y-5 bg-[#111116] p-5 sm:p-6">
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                <Languages className="h-4 w-4 text-fuchsia-400" />
                Sprache
              </span>
              <select
                value={form.language}
                onChange={(event) => set("language", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b0b0e] px-3 py-2.5 text-sm text-white outline-none focus:border-fuchsia-500"
              >
                <option value="de">Deutsch</option>
                <option value="en">English</option>
              </select>
            </label>
            <fieldset>
              <legend className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                <Moon className="h-4 w-4 text-fuchsia-400" />
                Darstellung
              </legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => set("theme", "dark")}
                  className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-sm ${form.theme === "dark" ? "border-indigo-500 bg-indigo-500/10 text-indigo-200" : "border-slate-700 text-slate-400"}`}
                >
                  <Moon className="h-4 w-4" />
                  Dunkel
                </button>
                <button
                  type="button"
                  onClick={() => set("theme", "light")}
                  className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-sm ${form.theme === "light" ? "border-amber-500 bg-amber-500/10 text-amber-200" : "border-slate-700 text-slate-400"}`}
                >
                  <Sun className="h-4 w-4" />
                  Hell
                </button>
              </div>
            </fieldset>
            <label className="block">
              <span className="text-sm font-semibold text-slate-300">
                Zeitzone
              </span>
              <select
                value={form.timezone}
                onChange={(event) => set("timezone", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b0b0e] px-3 py-2.5 text-sm text-white outline-none focus:border-fuchsia-500"
              >
                {TIMEZONES.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="space-y-5 bg-[#111116] p-5 sm:p-6">
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                <CalendarDays className="h-4 w-4 text-fuchsia-400" />
                Zahlenformat
              </span>
              <select
                value={form.number_format}
                onChange={(event) => set("number_format", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b0b0e] px-3 py-2.5 text-sm text-white outline-none focus:border-fuchsia-500"
              >
                <option value="de-DE">Deutsch – 1.234.567,89</option>
                <option value="en-GB">English UK – 1,234,567.89</option>
                <option value="en-US">English US – 1,234,567.89</option>
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-300">
                Datumsformat
              </span>
              <select
                value={form.date_format}
                onChange={(event) => set("date_format", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b0b0e] px-3 py-2.5 text-sm text-white outline-none focus:border-fuchsia-500"
              >
                <option value="short">Kurz</option>
                <option value="medium">Standard</option>
                <option value="long">Ausführlich</option>
                <option value="iso">ISO – 2026-09-08</option>
              </select>
            </label>
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                <Home className="h-4 w-4 text-fuchsia-400" />
                Bevorzugte Startseite nach dem Login
              </span>
              <select
                value={form.start_page}
                onChange={(event) => set("start_page", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b0b0e] px-3 py-2.5 text-sm text-white outline-none focus:border-fuchsia-500"
              >
                <option value="/dashboard">Dashboard</option>
                <option value="/dashboard/guilds">Serverübersicht</option>
                <option value="/konto">Mein Konto</option>
                <option value="/status">Bot-Status</option>
              </select>
            </label>
            <div className="rounded-xl border border-slate-800 bg-black/20 p-3 text-xs text-slate-500">
              <p>
                <strong className="text-slate-300">Vorschau:</strong>{" "}
                {datePreview}
              </p>
              <p className="mt-1">Zahl: {numberPreview}</p>
            </div>
          </div>
        </div>
      )}
      {error && (
        <p className="border-t border-slate-800 px-5 py-3 text-sm text-rose-300 sm:px-6">
          {error}
        </p>
      )}
    </section>
  );
}
