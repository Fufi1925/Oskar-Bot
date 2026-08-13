import React from "react";
import Link from "next/link";
import { ArrowLeft, LayoutDashboard, LifeBuoy, Search, Server } from "lucide-react";
import { SUPPORT_INVITE } from "@/lib/legal";

export const metadata = {
  title: "Seite nicht gefunden",
};

/**
 * Die 404-Seite.
 *
 * ── Was vorher nicht stimmte ────────────────────────────────────────
 *
 * Drei Dinge, alle im gerenderten Bild nachgemessen:
 *
 *   1. **Sie war komplett auf Englisch** — „This page does not exist“,
 *      „Back to the dashboard“ — auf einer sonst deutschen Seite.
 *   2. **Sie hatte einen eigenen Hintergrund** (`#070c18`, ein
 *      Marineblau) und eigene Blautöne, die es sonst nirgends gibt.
 *      Der Rest der Seite steht auf `#0a0a0c` mit `#5865f2`.
 *   3. **Die Riesenzahl war das Lauteste auf dem Bildschirm** — 9rem
 *      mit Farbverlauf. Die Zahl 404 ist aber die unwichtigste
 *      Angabe hier: sie sagt niemandem, was zu tun ist.
 *
 * ── Was diese Fassung anders macht ──────────────────────────────────
 *
 * Zuerst der Satz, der die Frage beantwortet („Diese Seite gibt es
 * nicht“), dann **warum** das passiert sein kann, dann die Wege
 * hinaus. Die 404 steht klein darüber, wo sie hingehört.
 *
 * Der häufigste echte Grund steht dabei zuerst: ein Server-Link, bei
 * dem der Bot nicht mehr auf dem Server ist. Genau dann landet man
 * hier, und „Serverliste“ ist dann die richtige Antwort — nicht
 * „Dashboard“.
 */

const WEGE = [
  {
    href: "/dashboard/guilds",
    icon: Server,
    titel: "Deine Server",
    text: "Server auswählen und einrichten",
  },
  {
    href: "/dashboard",
    icon: LayoutDashboard,
    titel: "Dashboard",
    text: "Übersicht und Verlauf",
  },
  {
    href: SUPPORT_INVITE,
    icon: LifeBuoy,
    titel: "Support",
    text: "Frag uns auf Discord",
    extern: true,
  },
];

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0a0a0c] px-6 py-16 text-slate-200">
      <div className="w-full max-w-xl">
        <div className="rounded-3xl border border-slate-800 bg-[#131318] p-6 sm:p-8">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/25 bg-indigo-500/10">
              <Search className="h-[18px] w-[18px] text-indigo-400" />
            </span>
            <div className="min-w-0">
              <p className="text-[12px] font-semibold text-slate-500">
                Fehler 404
              </p>
              <h1 className="text-[22px] font-bold tracking-tight text-white">
                Diese Seite gibt es nicht
              </h1>
            </div>
          </div>

          <p className="mt-4 text-[14px] leading-relaxed text-slate-400">
            Meistens liegt es an einem dieser drei Gründe:
          </p>

          {/* Nicht „irgendwas ist schiefgelaufen“, sondern die
              tatsächlichen Fälle. Wer den Grund liest, weiß sofort,
              welcher davon auf ihn zutrifft. */}
          <ul className="mt-3 space-y-2">
            {[
              "Der Bot ist nicht mehr auf dem Server, den der Link meint.",
              "Die Adresse hat sich geändert oder enthält einen Tippfehler.",
              "Für diese Seite fehlt dir die Berechtigung.",
            ].map((grund) => (
              <li
                key={grund}
                className="flex gap-2.5 rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-3 text-[13px] leading-relaxed text-slate-400"
              >
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-slate-600" />
                {grund}
              </li>
            ))}
          </ul>

          <div className="mt-6 grid gap-2.5 sm:grid-cols-3">
            {WEGE.map((weg) => {
              const inhalt = (
                <>
                  <weg.icon className="mb-2.5 h-[18px] w-[18px] text-slate-600 transition-colors group-hover:text-indigo-400" />
                  <p className="text-[14px] font-semibold text-white">
                    {weg.titel}
                  </p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-slate-500">
                    {weg.text}
                  </p>
                </>
              );
              const klasse =
                "group rounded-xl border border-slate-800 bg-[#0e0e12] p-4 transition-colors hover:border-slate-700";

              return weg.extern ? (
                <a
                  key={weg.href}
                  href={weg.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={klasse}
                >
                  {inhalt}
                </a>
              ) : (
                <Link key={weg.href} href={weg.href} className={klasse}>
                  {inhalt}
                </Link>
              );
            })}
          </div>

          <div className="mt-6 flex flex-wrap gap-2.5 border-t border-slate-800 pt-5">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-xl bg-[#5865f2] px-5 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
            >
              <ArrowLeft className="h-4 w-4" />
              Zum Dashboard
            </Link>
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-[#0e0e12] px-5 py-2.5 text-[14px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
            >
              Zur Startseite
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
