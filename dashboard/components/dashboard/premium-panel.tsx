"use client";

/**
 * Premium — was der Kunde sieht.
 *
 * ── Was hier vorher stand ───────────────────────────────────────────
 *
 * Zwei Kacheln nebeneinander: eine für den Template-Bot, eine für den
 * Hauptbot. Man konnte das eine haben und das andere nicht, und die
 * Seite musste beides gleichzeitig erklären. Dazu ein Eingabefeld für
 * einen 16-stelligen Lizenz-Key.
 *
 * ── Was jetzt hier steht ────────────────────────────────────────────
 *
 * Ein Zustand, eine Aussage: **habe ich Premium, und bis wann?**
 * Dasselbe Premium gilt für beide Bots — es gibt nur noch eins.
 *
 * Das Key-Feld ist weg. Premium bekommt man während der Testphase über
 * den Beta-Antrag; ein Kaufweg über PayPal ist vorgesehen, aber noch
 * nicht angebunden. Ein Eingabefeld für Keys, die niemand mehr
 * ausgibt, wäre eine Sackgasse mit Cursor.
 *
 * Die Konto-ID wird von hier nie mitgeschickt. Der Proxy setzt sie aus
 * der Sitzung ein.
 *
 * Werkzeuge fürs Team liegen in premium-admin.tsx.
 */

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, Bot, Check, Clock, Crown, ExternalLink, Gem, RefreshCw,
  Sparkles,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CountUp, Reveal, useReducedMotion } from "@/components/ui/reveal";

function formatDate(seconds?: number | null): string {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Verbleibende Tage, oder null wenn es nie abläuft. */
function daysLeft(seconds?: number | null): number | null {
  if (!seconds) return null;
  return Math.max(0, Math.ceil((seconds * 1000 - Date.now()) / 86_400_000));
}

/**
 * Was Premium freischaltet.
 *
 * Nur Dinge, die der Bot heute wirklich sperrt. Die Liste der geplanten
 * Funktionen steht auf `/premium` und ist dort als geplant markiert —
 * hier hätte sie nichts zu suchen, weil diese Seite den *eigenen
 * Zustand* zeigt und nicht das Angebot.
 */
const ENTHALTEN = [
  {
    titel: "Eigenes Aussehen pro Server",
    text: "Name, Profilbild und Banner des Bots auf deinem Server.",
  },
  {
    titel: "Speedrun",
    text: "Einen ganzen Server in einem Durchgang aufsetzen.",
  },
  {
    titel: "Premium-Vorlagen",
    text: "Die gesperrten Vorlagen des Template-Bots.",
  },
];

function Skeleton() {
  return (
    <div className="space-y-5">
      <div className="h-40 rounded-3xl border border-slate-800 bg-[#0e0e12]/60 animate-pulse" />
      <div className="h-32 rounded-3xl border border-slate-800 bg-[#0e0e12]/60 animate-pulse" />
    </div>
  );
}

export function PremiumPanel() {
  const { data: session } = useSession();
  const userId = session?.user?.id ?? "";
  const reduced = useReducedMotion();

  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (quiet = false) => {
      if (!userId) return;
      if (quiet) setRefreshing(true);
      try {
        setStatus(await api.getMyPremium(userId));
      } catch (err: any) {
        toast.error(err?.message || "Status konnte nicht geladen werden.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    load();
  }, [load]);

  // Ein Zustand für beide Bots. `premium` ist der neue Schlüssel;
  // `template_bot` steht nur als Rückfalloption da, falls eine ältere
  // Antwort im Zwischenspeicher liegt.
  const zustand = status?.premium ?? status?.template_bot;
  const active = Boolean(zustand?.premium);
  const left = daysLeft(zustand?.expires_at);

  // Läuft es über die kostenlose Probewoche? Dann muss das dastehen:
  // „Premium ist aktiv“ allein liest sich wie etwas Bezahltes, und
  // dann wundert man sich, wenn es nach sieben Tagen weg ist.
  const trial = Boolean(zustand?.via_trial);
  const tester = Boolean(zustand?.via_tester);

  // Wie viel der Laufzeit übrig ist, als Balken. Nur sinnvoll, wenn die
  // Dauer bekannt ist — eine unbefristete Lizenz bekommt gar keinen
  // Balken statt eines vollen, der sich nie bewegt.
  let progress: number | null = null;
  if (active && !zustand?.lifetime && left !== null && zustand?.duration_days) {
    progress = Math.max(
      0,
      Math.min(100, (left / zustand.duration_days) * 100)
    );
  }

  if (loading) return <Skeleton />;

  return (
    <div className="space-y-5">
      {/* ── Eine Karte, zwei mögliche Aussagen ─────────────────── */}
      <Reveal>
        <section
          className={cn(
            "relative overflow-hidden rounded-3xl border p-6 transition-colors duration-700",
            active
              ? "border-amber-500/30 bg-gradient-to-br from-amber-500/[0.12] via-amber-500/[0.03] to-transparent"
              : "border-slate-800 bg-[#0e0e12]/60"
          )}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                "h-14 w-14 rounded-2xl grid place-items-center shrink-0 transition-all duration-700",
                active ? "bg-amber-500/20 scale-100" : "bg-slate-800/60 scale-95"
              )}
            >
              <Gem
                className={cn(
                  "h-7 w-7 transition-colors duration-700",
                  active ? "text-amber-300" : "text-slate-500"
                )}
              />
            </div>

            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-lg font-black transition-colors duration-700",
                  active ? "text-amber-200" : "text-white"
                )}
              >
                {active
                  ? trial
                    ? `${zustand?.trial?.duration_days ?? 7} Tage Premium – kostenlos`
                    : tester
                      ? "Premium über den Tester-Zugang"
                      : "Premium ist aktiv"
                  : "Kein Premium"}
              </p>

              {active ? (
                <p className="text-[13px] text-slate-300 mt-1">
                  {trial ? (
                    <>
                      Deine Probewoche läuft noch bis{" "}
                      <span className="font-bold text-white">
                        {formatDate(zustand?.expires_at)}
                      </span>
                      {left !== null && (
                        <span className="text-slate-400">
                          {" "}
                          &middot;{" "}
                          <CountUp
                            value={left}
                            className="font-bold text-white tabular-nums"
                          />{" "}
                          {left === 1 ? "Tag" : "Tage"} übrig
                        </span>
                      )}
                      . Sie gilt für beide Bots und nur einmal pro Konto.
                    </>
                  ) : zustand?.lifetime ? (
                    <>Unbegrenzt gültig &mdash; läuft nicht ab.</>
                  ) : (
                    <>
                      Gültig bis{" "}
                      <span className="font-bold text-white">
                        {formatDate(zustand?.expires_at)}
                      </span>
                      {left !== null && (
                        <span className="text-slate-400">
                          {" "}
                          &middot;{" "}
                          <CountUp
                            value={left}
                            className="font-bold text-white tabular-nums"
                          />{" "}
                          {left === 1 ? "Tag" : "Tage"} übrig
                        </span>
                      )}
                      .
                    </>
                  )}
                </p>
              ) : (
                <p className="text-[13px] text-slate-400 mt-1 leading-relaxed">
                  Während der Testphase bekommst du Premium über einen
                  Beta-Antrag. Es gilt dann für beide Bots.
                </p>
              )}

              {/* Der Balken nur, wenn er etwas aussagt. */}
              {progress !== null && (
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={cn(
                      "h-full rounded-full bg-amber-400",
                      !reduced && "transition-[width] duration-1000"
                    )}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              )}
            </div>

            <button
              onClick={() => load(true)}
              disabled={refreshing}
              title="Neu laden"
              className="shrink-0 rounded-xl border border-slate-800 bg-[#0e0e12] p-2 text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-40"
            >
              <RefreshCw
                className={cn("h-4 w-4", refreshing && "animate-spin")}
              />
            </button>
          </div>
        </section>
      </Reveal>

      {/* ── Ein Premium, beide Bots ───────────────────────────── */}
      <Reveal>
        <section className="rounded-3xl border border-slate-800 bg-[#0e0e12]/60 p-6">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            <h3 className="font-bold text-white">Gilt für beide Bots</h3>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
            Premium hängt an deinem Discord-Konto — nicht an einem Server
            und nicht an einem der beiden Bots. Es schaltet den University
            Bot und den Template-Bot gleichzeitig frei.
          </p>

          <div className="mt-4 grid gap-2.5 sm:grid-cols-3">
            {ENTHALTEN.map((e) => (
              <div
                key={e.titel}
                className="rounded-2xl border border-slate-800 bg-[#131318] p-3.5"
              >
                <div className="flex items-start gap-2">
                  <Check
                    className={cn(
                      "mt-0.5 h-3.5 w-3.5 shrink-0",
                      active ? "text-amber-400" : "text-slate-600"
                    )}
                  />
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-white">
                      {e.titel}
                    </div>
                    <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                      {e.text}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Link
            href="/premium"
            className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-semibold text-primary transition hover:brightness-125"
          >
            Alle Unterschiede zu Gratis ansehen
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </section>
      </Reveal>

      {/* ── Ohne Premium: der Weg dahin ───────────────────────── */}
      {!active && (
        <Reveal>
          <section className="rounded-3xl border border-amber-500/25 bg-amber-500/[0.04] p-6">
            <div className="flex items-center gap-2">
              <Crown className="h-4 w-4 text-amber-400" />
              <h3 className="font-bold text-white">So bekommst du Premium</h3>
            </div>
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
              Die Testphase läuft, ein Kauf ist noch nicht möglich. Stell
              einen Beta-Antrag — wir schauen ihn uns an und melden uns
              per Direktnachricht.
            </p>

            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <Link
                href="/dashboard/premium/beta"
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-amber-400 px-5 py-3 text-sm font-bold text-black transition hover:brightness-110"
              >
                <Sparkles className="h-4 w-4" />
                Beta-Antrag stellen
              </Link>
              <Link
                href="/premium"
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-800 bg-[#0e0e12] px-5 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/[0.04]"
              >
                Preise ansehen
              </Link>
            </div>
          </section>
        </Reveal>
      )}

      {/* ── Mit Premium: der Template-Bot muss auf den Server ── */}
      {active && status?.template_invite && (
        <Reveal>
          <section className="rounded-3xl border border-slate-800 bg-[#0e0e12]/60 p-6">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" />
              <h3 className="font-bold text-white">Template-Bot einladen</h3>
            </div>
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
              Für die Premium-Vorlagen muss der Template-Bot auf dem Server
              sein. Dein Premium erkennt er sofort — du musst dort nichts
              erneut eingeben.
            </p>
            <a
              href={status.template_invite}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110"
            >
              Template-Bot hinzufügen
              <ExternalLink className="h-4 w-4" />
            </a>
          </section>
        </Reveal>
      )}
    </div>
  );
}
