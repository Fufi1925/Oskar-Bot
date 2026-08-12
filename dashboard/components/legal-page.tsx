import React from "react";
import Link from "next/link";
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
    <div className="min-h-screen overflow-x-clip bg-[#0a0a0c] text-slate-200 font-sans">
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute bottom-[-10%] left-[-5%] w-[40%] h-[40%] bg-indigo-600/[0.05] blur-[120px] rounded-full" />
        <div className="absolute top-[-10%] right-[-5%] w-[35%] h-[35%] bg-indigo-600/[0.05] blur-[120px] rounded-full" />
      </div>

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

        <footer className="mt-24 pt-10 border-t border-slate-800 flex flex-wrap gap-x-8 gap-y-3 text-[14px] text-slate-500">
          <Link href="/terms" className="hover:text-white transition-colors">
            Nutzungsbedingungen
          </Link>
          <Link href="/privacy" className="hover:text-white transition-colors">
            Datenschutz
          </Link>
          <Link href="/imprint" className="hover:text-white transition-colors">
            Impressum
          </Link>
          <Link href="/team" className="hover:text-white transition-colors">
            Team
          </Link>
        </footer>
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
    <section className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-8">
      <h2 className="text-lg font-bold text-white mb-4">{title}</h2>
      <div className="space-y-3 text-slate-400 leading-relaxed text-[15px]">
        {children}
      </div>
    </section>
  );
}
