import React from "react";
import Link from "next/link";
import { Bot, ChevronLeft } from "lucide-react";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

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
    <div className="min-h-screen bg-[#071527] text-slate-200 font-sans">
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute bottom-[-10%] left-[-5%] w-[40%] h-[40%] bg-blue-600/[0.03] blur-[120px] rounded-full" />
        <div className="absolute top-[-10%] right-[-5%] w-[35%] h-[35%] bg-blue-600/[0.03] blur-[120px] rounded-full" />
      </div>

      <nav className="fixed top-0 w-full z-50 border-b border-white/[0.03] bg-[#071527]/80 backdrop-blur-3xl px-6 h-20 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-4 group">
          <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center group-hover:rotate-12 transition-transform">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <span className="text-xl font-bold text-white font-outfit uppercase tracking-tighter">
            {BRAND} Engine
          </span>
        </Link>
        <Link
          href="/"
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/[0.04] transition-colors text-sm font-medium"
        >
          <ChevronLeft className="h-4 w-4" />
          Zurück
        </Link>
      </nav>

      <main className="relative z-10 max-w-4xl mx-auto px-6 pt-40 pb-32">
        <header className="mb-16">
          {Icon && (
            <div className="h-14 w-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-8">
              <Icon className="h-7 w-7 text-blue-400" />
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

        <footer className="mt-24 pt-10 border-t border-white/[0.05] flex flex-wrap gap-x-8 gap-y-3 text-[11px] font-black uppercase tracking-widest text-slate-600">
          <Link href="/terms" className="hover:text-blue-500 transition-colors">
            Nutzungsbedingungen
          </Link>
          <Link href="/privacy" className="hover:text-blue-500 transition-colors">
            Datenschutz
          </Link>
          <Link href="/imprint" className="hover:text-blue-500 transition-colors">
            Impressum
          </Link>
          <Link href="/team" className="hover:text-blue-500 transition-colors">
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
