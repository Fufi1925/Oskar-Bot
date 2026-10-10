import React from "react";
import { SiteNav } from "@/components/site-nav";

/**
 * Shared shell for the standalone public pages (terms, privacy, imprint,
 * team). Keeps the navigation and background identical to the landing page
 * instead of every page repeating the same 40 lines of markup.
 */
export function LegalPage({
  title,
  subtitle,
  icon: Icon,
  updated,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ComponentType<{ className?: string }>;
  updated?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen overflow-x-clip bg-transparent text-slate-200 font-sans">

      {/* Dieselbe Leiste wie auf der Startseite.
          Vorher stand hier eine zweite, eigene Fassung -- damit sah
          das Impressum anders aus als die Startseite, und jede
          Aenderung musste an zwei Stellen passieren. */}
      <SiteNav />

      <main className="relative z-10 max-w-4xl mx-auto px-6 pt-16 pb-32">
        <header className="mb-16">
          {Icon && (
            <div className="h-14 w-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-8">
              <Icon className="h-7 w-7 text-indigo-400" />
            </div>
          )}
          <h1 className="text-4xl md:text-5xl font-bold text-white font-outfit tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="text-slate-400 mt-4 text-lg leading-relaxed max-w-2xl">
              {subtitle}
            </p>
          )}
          {updated && (
            <p className="text-[11px] uppercase tracking-widest text-slate-600 font-black mt-6">
              Stand: {updated}
            </p>
          )}
        </header>

        <div className="space-y-10">{children}</div>
      </main>
    </div>
  );
}

/** One titled block of a legal page. */
export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-[var(--cloudtix-card)] border border-slate-800 rounded-2xl p-6 sm:p-8">
      <h2 className="text-lg font-bold text-white mb-4">{title}</h2>
      <div className="space-y-3 text-slate-400 leading-relaxed text-[15px]">
        {children}
      </div>
    </section>
  );
}
