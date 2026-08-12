"use client";

/**
 * Das Befehlsverzeichnis.
 *
 * ── Aufbau ──────────────────────────────────────────────────────────
 *
 *   1. Suchfeld und Kategorie-Filter.
 *   2. Die besten 100 — nach echter Nutzung, sonst nach Rangfolge.
 *   3. Alle übrigen, nach Kategorie gruppiert.
 *
 * ── Warum die Liste vom Bot kommt ───────────────────────────────────
 *
 * Eine von Hand gepflegte Liste ist am Tag nach dem nächsten neuen
 * Befehl falsch. `/commands/` fragt den laufenden Bot: was er
 * anbietet, steht hier — ohne dass jemand daran denken muss.
 *
 * ── Warum „besten 100“ ehrlich beschriftet ist ──────────────────────
 *
 * Solange keine Nutzungszahlen vorliegen (frischer Deploy), ist die
 * Reihenfolge eine handverlesene Rangfolge, keine Rangliste. Genau
 * das steht dann auch da, statt eine Statistik zu behaupten, die es
 * nicht gibt.
 */

import React from "react";
import Link from "next/link";
import {
  ChevronDown, Loader2, Search, Slash, Terminal,
} from "lucide-react";
import { SiteNav } from "@/components/site-nav";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

interface Befehl {
  name: string;
  category: string;
  description: string;
  aliases: string[];
  slash: boolean;
  signature: string;
  uses: number;
}

/** Eine Zeile in der Liste. */
function Zeile({ befehl, prefix }: { befehl: Befehl; prefix: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3 transition-colors hover:border-slate-700">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-[14px] font-semibold text-white">
              {prefix}
              {befehl.name}
            </code>
            {befehl.slash && (
              <span className="inline-flex items-center gap-1 rounded-md bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-bold text-indigo-300">
                <Slash className="h-2.5 w-2.5" />
                Slash
              </span>
            )}
            {befehl.uses > 0 && (
              <span className="text-[11px] text-slate-600">
                {befehl.uses.toLocaleString("de-DE")}&times; benutzt
              </span>
            )}
          </div>

          {befehl.signature && (
            <div className="mt-1 font-mono text-[11px] text-slate-600 truncate">
              {prefix}
              {befehl.name} {befehl.signature}
            </div>
          )}

          {befehl.description && (
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
              {befehl.description}
            </p>
          )}

          {befehl.aliases.length > 0 && (
            <p className="mt-1.5 text-[11px] text-slate-600">
              Auch:{" "}
              {befehl.aliases.map((a) => (
                <code key={a} className="mr-1.5 text-slate-500">
                  {prefix}
                  {a}
                </code>
              ))}
            </p>
          )}
        </div>

        <span className="shrink-0 rounded-md border border-slate-800 px-2 py-0.5 text-[10px] text-slate-500">
          {befehl.category}
        </span>
      </div>
    </div>
  );
}

export default function CommandsPage() {
  const [daten, setDaten] = React.useState<any>(null);
  const [laden, setLaden] = React.useState(true);
  const [fehler, setFehler] = React.useState("");
  const [suche, setSuche] = React.useState("");
  const [kategorie, setKategorie] = React.useState("");
  const [alleZeigen, setAlleZeigen] = React.useState(false);

  React.useEffect(() => {
    api
      .getCommands()
      .then(setDaten)
      .catch((e: any) =>
        setFehler(e?.message || "Die Befehle ließen sich nicht laden."),
      )
      .finally(() => setLaden(false));
  }, []);

  const alle: Befehl[] = daten?.commands || [];
  const prefix: string = daten?.prefix || ">";

  /** Was nach Suche und Filter übrig bleibt. */
  const gefiltert = React.useMemo(() => {
    const q = suche.trim().toLowerCase();
    return alle.filter((c) => {
      if (kategorie && c.category !== kategorie) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.aliases.some((a) => a.toLowerCase().includes(q))
      );
    });
  }, [alle, suche, kategorie]);

  // Wird gesucht oder gefiltert, ergibt eine Aufteilung in „Top 100“
  // und „Rest“ keinen Sinn mehr — dann zählt nur das Ergebnis.
  const sucht = Boolean(suche.trim() || kategorie);
  const top = gefiltert.slice(0, daten?.top_count ?? 100);
  const rest = gefiltert.slice(daten?.top_count ?? 100);

  /** Der Rest, nach Kategorie gruppiert. */
  const gruppen = React.useMemo(() => {
    const map = new Map<string, Befehl[]>();
    for (const c of rest) {
      if (!map.has(c.category)) map.set(c.category, []);
      map.get(c.category)!.push(c);
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [rest]);

  return (
    <div className="min-h-screen overflow-x-clip bg-[#0a0a0c] text-slate-200">
      <SiteNav />

      <main className="mx-auto max-w-[1100px] px-6 lg:px-12 py-16">
        <div className="mb-10">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-[#131318] px-4 py-1.5 text-[13px] text-indigo-300">
            <Terminal className="h-3.5 w-3.5" />
            Befehle
          </span>
          <h1 className="mt-6 text-[38px] sm:text-[44px] font-extrabold tracking-tight text-white">
            Alle Befehle
          </h1>
          <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-slate-400">
            {laden
              ? "Wird geladen …"
              : `${alle.length} Befehle. Standard-Präfix ist „${prefix}“ — im Dashboard änderbar. Befehle mit dem Slash-Zeichen gibt es auch als /-Befehl.`}
          </p>
        </div>

        {/* Suche und Filter */}
        <div className="mb-8 space-y-3">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              value={suche}
              onChange={(e) => setSuche(e.target.value)}
              placeholder="Befehl suchen …"
              className="w-full rounded-xl border border-slate-800 bg-[#131318] py-3 pl-11 pr-4 text-[15px] text-white placeholder:text-slate-600 focus:outline-none focus:border-slate-700 transition-colors"
            />
          </div>

          {daten?.categories?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setKategorie("")}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-[13px] transition-colors",
                  !kategorie
                    ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                    : "border-slate-800 bg-[#131318] text-slate-400 hover:border-slate-700",
                )}
              >
                Alle ({alle.length})
              </button>
              {daten.categories.map((k: any) => (
                <button
                  key={k.name}
                  type="button"
                  onClick={() => setKategorie(kategorie === k.name ? "" : k.name)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-[13px] transition-colors",
                    kategorie === k.name
                      ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                      : "border-slate-800 bg-[#131318] text-slate-400 hover:border-slate-700",
                  )}
                >
                  {k.name} ({k.count})
                </button>
              ))}
            </div>
          )}
        </div>

        {laden && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-60" />
          </div>
        )}

        {fehler && !laden && (
          <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6">
            <p className="text-[15px] text-slate-300">{fehler}</p>
            <p className="mt-2 text-[13px] text-slate-500">
              Der Bot antwortet gerade nicht. Die Befehle stehen auch im
              Discord unter <code className="text-slate-400">{prefix}help</code>.
            </p>
          </div>
        )}

        {!laden && !fehler && (
          <>
            {sucht ? (
              <>
                <h2 className="mb-4 text-[15px] font-bold text-white">
                  {gefiltert.length}{" "}
                  {gefiltert.length === 1 ? "Treffer" : "Treffer"}
                </h2>
                <div className="space-y-2">
                  {gefiltert.map((c) => (
                    <Zeile key={c.name} befehl={c} prefix={prefix} />
                  ))}
                </div>
                {gefiltert.length === 0 && (
                  <p className="py-12 text-center text-[15px] text-slate-500">
                    Nichts gefunden. Andere Schreibweise versuchen?
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="mb-4 flex items-baseline justify-between gap-4">
                  <h2 className="text-[20px] font-bold text-white">
                    Die {top.length} wichtigsten
                  </h2>
                  <span className="text-[12px] text-slate-600">
                    {daten?.ranked_by_usage
                      ? "nach tatsächlicher Nutzung"
                      : "nach Wichtigkeit sortiert"}
                  </span>
                </div>
                <div className="space-y-2">
                  {top.map((c) => (
                    <Zeile key={c.name} befehl={c} prefix={prefix} />
                  ))}
                </div>

                {rest.length > 0 && (
                  <div className="mt-12">
                    <button
                      type="button"
                      onClick={() => setAlleZeigen((a) => !a)}
                      className="flex w-full items-center justify-between gap-4 rounded-xl border border-slate-800 bg-[#131318] px-5 py-4 text-left transition-colors hover:border-slate-700"
                    >
                      <span>
                        <span className="block text-[16px] font-bold text-white">
                          Alle übrigen {rest.length} Befehle
                        </span>
                        <span className="mt-0.5 block text-[13px] text-slate-500">
                          Nach Kategorie geordnet
                        </span>
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-5 w-5 shrink-0 text-indigo-400 transition-transform",
                          alleZeigen && "rotate-180",
                        )}
                      />
                    </button>

                    {alleZeigen && (
                      <div className="mt-6 space-y-8">
                        {gruppen.map(([name, liste]) => (
                          <div key={name}>
                            <h3 className="mb-3 text-[13px] font-bold uppercase tracking-widest text-slate-500">
                              {name} ({liste.length})
                            </h3>
                            <div className="space-y-2">
                              {liste.map((c) => (
                                <Zeile key={c.name} befehl={c} prefix={prefix} />
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </>
        )}

        <div className="mt-16 rounded-2xl border border-slate-800 bg-[#0f0f13] p-6">
          <h3 className="text-[16px] font-bold text-white">
            Etwas nicht gefunden?
          </h3>
          <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
            Im Discord zeigt <code className="text-slate-300">{prefix}help</code>{" "}
            dieselbe Liste, nach Kategorien sortiert. Einstellungen zu den
            Befehlen — Präfix, wer sie ohne Präfix nutzen darf, welche Module
            an sind — stehen im{" "}
            <Link href="/dashboard" className="text-indigo-400 hover:text-indigo-300">
              Dashboard
            </Link>
            .
          </p>
        </div>
      </main>

      <footer className="border-t border-slate-800 px-6 lg:px-12 py-10">
        <div className="mx-auto max-w-[1100px] flex flex-wrap items-center justify-between gap-4">
          <p className="text-[13px] text-slate-600">
            &copy; 2026 {BRAND}
          </p>
          <div className="flex gap-6 text-[13px] text-slate-500">
            <Link href="/" className="hover:text-white transition-colors">Start</Link>
            <Link href="/docs" className="hover:text-white transition-colors">Dokumentation</Link>
            <Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
