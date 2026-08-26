"use client";

/**
 * Die öffentliche Premium-Seite.
 *
 * ── Was hier steht ──────────────────────────────────────────────────
 *
 *   1. Ein Hinweis, dass die Testphase läuft.
 *   2. Die drei Preise: Monat, Jahr, Lifetime.
 *   3. Eine Tabelle mit zehn Punkten — was Gratis kann und was
 *      Premium kann.
 *   4. Ein paar Fragen, die sonst im Support landen.
 *
 * ── Warum die Kauf-Knöpfe ausgegraut sind ───────────────────────────
 *
 * Es gibt noch keinen Zahlungsanbieter. Ein Knopf, der zu PayPal
 * führen soll, es aber nicht tut, ist schlimmer als ein Knopf, der
 * ehrlich sagt „kommt nach der Testphase“. Deshalb sind sie
 * `disabled` und tragen den Grund direkt daneben.
 *
 * ── Warum neun der zehn Punkte als „geplant“ stehen ─────────────────
 *
 * Nur das Design ist gebaut und wirkt schon. Die anderen neun sind
 * beschlossen, aber noch nicht scharf geschaltet. Sie hier als
 * fertig zu verkaufen, wäre gelogen — jede Zeile trägt deshalb
 * sichtbar, ob sie schon läuft. Die Wahrheit steht auch in
 * `bot/tests/test_premium_seite.py`: der Test vergleicht die Tabelle
 * mit dem, was der Bot wirklich sperrt.
 */

import React from "react";
import Link from "next/link";
import {
  ArrowRight, BadgeCheck, Check, Clock, Crown, Gem, Minus, Sparkles,
} from "lucide-react";
import { SiteNav } from "@/components/site-nav";
import { SUPPORT_INVITE } from "@/lib/legal";
import { cn } from "@/lib/utils";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

/**
 * Die Preise.
 *
 * Der Jahrespreis ist nicht getippt, sondern gerechnet: zwölf Monate
 * minus zehn Prozent. Eine getippte Zahl läuft beim nächsten
 * Preiswechsel auseinander, und dann steht auf der Seite ein Rabatt,
 * den es nicht gibt.
 */
const PREIS_MONAT = 1.99;
const RABATT_JAHR = 0.1;
const PREIS_JAHR = PREIS_MONAT * 12 * (1 - RABATT_JAHR);
const PREIS_LIFETIME = 20;

/** Deutsche Schreibweise: Komma, nicht Punkt. `toFixed` liefert immer
 *  einen Punkt — deshalb der Umweg über `toLocaleString`. */
function euro(betrag: number): string {
  return betrag.toLocaleString("de-DE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

type Tarif = {
  name: string;
  preis: string;
  einheit: string;
  hinweis: string;
  badge?: string;
  hervor?: boolean;
};

const TARIFE: Tarif[] = [
  {
    name: "Monat",
    preis: `${euro(PREIS_MONAT)} €`,
    einheit: "pro Monat",
    hinweis: "Monatlich kündbar.",
  },
  {
    name: "Jahr",
    preis: `${euro(PREIS_JAHR)} €`,
    einheit: "pro Jahr",
    hinweis: `Statt ${euro(PREIS_MONAT * 12)} € — du sparst ${euro(
      PREIS_MONAT * 12 - PREIS_JAHR
    )} €.`,
    badge: `${Math.round(RABATT_JAHR * 100)} % Rabatt`,
    hervor: true,
  },
  {
    name: "Lifetime",
    preis: `${euro(PREIS_LIFETIME)} €`,
    einheit: "einmalig",
    hinweis: "Einmal zahlen, dauerhaft behalten.",
  },
];

/**
 * Die zehn Punkte.
 *
 * `live` heißt: der Bot sperrt das heute schon wirklich. Genau eine
 * Zeile trägt `live: true` — das Design. Alles andere ist beschlossen
 * und kommt, ist aber noch nicht scharf.
 */
type Zeile = {
  titel: string;
  text: string;
  gratis: string | false;
  premium: string;
  live?: boolean;
};

const VERGLEICH: Zeile[] = [
  {
    titel: "Eigenes Aussehen pro Server",
    text:
      "Der Bot bekommt auf deinem Server einen eigenen Namen, ein eigenes " +
      "Profilbild und ein eigenes Banner. Überall sonst bleibt er, wie er ist.",
    gratis: false,
    premium: "Name, Bild und Banner frei wählbar",
    live: true,
  },
  {
    titel: "Vorlagen pro Server",
    text:
      "Fertige Server-Aufbauten speichern und auf andere Server übertragen.",
    gratis: "10 Vorlagen",
    premium: "50 Vorlagen",
  },
  {
    titel: "Bot-Logs: wie weit zurück",
    text:
      "Wie lange die Ereignisse aus Honeypot, Automod, Verifizierung und " +
      "den anderen Quellen einsehbar bleiben.",
    gratis: "7 Tage",
    premium: "90 Tage",
  },
  {
    titel: "Musik im Warteraum",
    text:
      "Eigene Musik statt der Standardmelodie, während Leute im Warteraum " +
      "sitzen.",
    gratis: "Standardmelodie",
    premium: "Eigene Datei hochladen",
  },
  {
    titel: "Giveaways gleichzeitig",
    text: "Wie viele Gewinnspiele nebeneinander laufen dürfen.",
    gratis: "3 gleichzeitig",
    premium: "25 gleichzeitig",
  },
  {
    titel: "Automatische Antworten",
    text:
      "Feste Antworten auf Stichwörter — für Fragen, die jede Woche " +
      "wiederkommen.",
    gratis: "15 Regeln",
    premium: "100 Regeln",
  },
  {
    titel: "Bewerbungs-Formulare",
    text: "Eigene Formulare für Team-Bewerbungen, direkt auf dem Server.",
    gratis: "2 Formulare",
    premium: "10 Formulare",
  },
  {
    titel: "Anti-Nuke: Rückmeldung",
    text:
      "Wie schnell der Schutz eine Auffälligkeit meldet und wie viele " +
      "Aktionen er rückwirkend prüft.",
    gratis: "Standard-Prüfung",
    premium: "Erweiterte Prüfung + sofortige Meldung",
  },
  {
    titel: "Support",
    text: "Wie schnell wir bei Problemen antworten.",
    gratis: "Normale Warteschlange",
    premium: "Bevorzugt, eigener Kanal",
  },
  {
    titel: "Neues zuerst",
    text:
      "Neue Funktionen ausprobieren, bevor sie für alle freigeschaltet " +
      "werden.",
    gratis: false,
    premium: "Früher Zugang",
  },
];

/** Wie viele davon heute schon wirken. */
const LIVE_ANZAHL = VERGLEICH.filter((z) => z.live).length;

const FRAGEN: { frage: string; antwort: string }[] = [
  {
    frage: "Gilt Premium für mich oder für meinen Server?",
    antwort:
      "Für dein Discord-Konto. Um es auf einem Server einzusetzen, musst du " +
      "dort Inhaber sein.",
  },
  {
    frage: "Kann ich schon kaufen?",
    antwort:
      "Noch nicht. Die Testphase läuft, es ist kein Zahlungsanbieter " +
      "angebunden. Bis dahin kommst du über das Beta-Formular an einen " +
      "Zugang.",
  },
  {
    frage: "Was passiert, wenn Premium ausläuft?",
    antwort:
      "Der Bot behält deine Einstellungen, benutzt aber wieder die Grenzen " +
      "aus der Gratis-Spalte. Gelöscht wird nichts.",
  },
  {
    frage: "Warum stehen neun Punkte auf „geplant“?",
    antwort:
      "Weil sie es sind. Nur das eigene Aussehen wirkt heute schon. Die " +
      "anderen neun sind beschlossen und kommen nach der Testphase — wir " +
      "schreiben sie lieber ehrlich hin, als sie als fertig zu verkaufen.",
  },
];

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl";

export default function PremiumSeite() {
  return (
    <div className="min-h-screen bg-[#0a0a0c] text-white">
      <SiteNav />

      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        {/* ── Kopf ──────────────────────────────────────────────── */}
        <div className="text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-300">
            <Clock className="h-3.5 w-3.5" />
            Testphase — Kauf noch nicht möglich
          </div>

          <h1 className="mt-5 text-3xl font-bold sm:text-4xl">
            {BRAND} Premium
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-slate-400">
            Höhere Grenzen, ein eigenes Aussehen für deinen Server und neue
            Funktionen zuerst. Solange die Testphase läuft, kommst du über das
            Beta-Formular an einen Zugang.
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/dashboard/premium/beta"
              className="inline-flex items-center gap-2 rounded-2xl bg-amber-400 px-5 py-3 text-sm font-bold text-black transition hover:brightness-110"
            >
              <Sparkles className="h-4 w-4" />
              Für die Beta bewerben
            </Link>
            <Link
              href="/dashboard/premium"
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-800 bg-[#131318] px-5 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/[0.04]"
            >
              Key einlösen
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        {/* ── Preise ────────────────────────────────────────────── */}
        <div className="mt-14 grid gap-4 md:grid-cols-3">
          {TARIFE.map((t) => (
            <div
              key={t.name}
              className={cn(
                CARD,
                "relative flex flex-col p-6",
                t.hervor && "border-amber-400/40"
              )}
            >
              {t.badge && (
                <div className="absolute -top-3 left-6 rounded-full bg-amber-400 px-3 py-1 text-xs font-bold text-black">
                  {t.badge}
                </div>
              )}

              <div className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                {t.name}
              </div>

              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-bold text-white">{t.preis}</span>
                <span className="text-sm text-slate-500">{t.einheit}</span>
              </div>

              <p className="mt-2 flex-1 text-sm text-slate-400">{t.hinweis}</p>

              {/* Ausgegraut, mit Begründung daneben. Ein Knopf, der zu
                  einer Zahlung führen soll, es aber nicht tut, ist
                  schlimmer als gar keiner. */}
              <button
                type="button"
                disabled
                title="Zahlung wird nach der Testphase freigeschaltet"
                className="mt-5 w-full cursor-not-allowed rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm font-semibold text-slate-500 opacity-60"
              >
                Mit PayPal kaufen
              </button>
              <p className="mt-2 text-center text-xs text-slate-600">
                Kommt, sobald die Testphase vorbei ist.
              </p>
            </div>
          ))}
        </div>

        {/* ── Die Tabelle ───────────────────────────────────────── */}
        <div className="mt-16">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-bold">Gratis und Premium</h2>
              <p className="mt-1 text-sm text-slate-400">
                Zehn Punkte im Vergleich. Was schon wirkt, ist markiert —{" "}
                {LIVE_ANZAHL} von {VERGLEICH.length}.
              </p>
            </div>

            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-emerald-300">
                <BadgeCheck className="h-3.5 w-3.5" />
                aktiv
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-[#0f0f13] px-2.5 py-1 text-slate-400">
                <Clock className="h-3.5 w-3.5" />
                geplant
              </span>
            </div>
          </div>

          <div className={cn(CARD, "mt-5 overflow-hidden")}>
            {/* Kopfzeile: auf schmalen Geräten ausgeblendet, dort
                trägt jede Karte ihre eigenen Beschriftungen. */}
            <div className="hidden border-b border-slate-800 bg-[#0f0f13] sm:grid sm:grid-cols-[1.6fr_1fr_1fr]">
              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Funktion
              </div>
              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Gratis
              </div>
              <div className="flex items-center gap-1.5 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-amber-400">
                <Crown className="h-3.5 w-3.5" />
                Premium
              </div>
            </div>

            {VERGLEICH.map((z, i) => (
              <div
                key={z.titel}
                className={cn(
                  "grid gap-1 px-5 py-4 sm:grid-cols-[1.6fr_1fr_1fr] sm:gap-0 sm:px-0 sm:py-0",
                  i > 0 && "border-t border-slate-800"
                )}
              >
                {/* Funktion */}
                <div className="sm:px-5 sm:py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-white">{z.titel}</span>
                    {z.live ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-300">
                        <BadgeCheck className="h-3 w-3" />
                        aktiv
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-[#0f0f13] px-2 py-0.5 text-[10px] font-bold uppercase text-slate-500">
                        <Clock className="h-3 w-3" />
                        geplant
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-slate-500">
                    {z.text}
                  </p>
                </div>

                {/* Gratis */}
                <div className="flex items-start gap-2 sm:px-5 sm:py-4">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-600 sm:hidden">
                    Gratis
                  </span>
                  {z.gratis === false ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
                      <Minus className="h-4 w-4" />
                      nicht enthalten
                    </span>
                  ) : (
                    <span className="text-sm text-slate-400">{z.gratis}</span>
                  )}
                </div>

                {/* Premium */}
                <div className="flex items-start gap-2 sm:px-5 sm:py-4">
                  <span className="text-xs font-semibold uppercase tracking-wider text-amber-500/70 sm:hidden">
                    Premium
                  </span>
                  <span className="inline-flex items-start gap-1.5 text-sm font-medium text-amber-200">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                    {z.premium}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-600">
            „Geplant“ heißt: beschlossen, aber noch nicht scharf geschaltet.
            Diese Grenzen gelten heute noch nicht — der Bot behandelt Gratis
            und Premium dort gleich. Wir schreiben es lieber hin, als es als
            fertig zu verkaufen.
          </p>
        </div>

        {/* ── Fragen ────────────────────────────────────────────── */}
        <div className="mt-16">
          <h2 className="text-2xl font-bold">Häufige Fragen</h2>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {FRAGEN.map((f) => (
              <div key={f.frage} className={cn(CARD, "p-5")}>
                <div className="font-semibold text-white">{f.frage}</div>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                  {f.antwort}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Abschluss ─────────────────────────────────────────── */}
        <div
          className={cn(
            CARD,
            "mt-14 flex flex-col items-center gap-4 p-8 text-center"
          )}
        >
          <div className="rounded-2xl bg-amber-400/15 p-3">
            <Gem className="h-6 w-6 text-amber-400" />
          </div>
          <div>
            <div className="text-lg font-bold text-white">
              Noch Fragen offen?
            </div>
            <p className="mt-1 text-sm text-slate-400">
              Schreib uns im Support-Server — wir antworten dort auch zur
              Testphase.
            </p>
          </div>
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110"
          >
            Zum Support-Server
            <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </main>
    </div>
  );
}
