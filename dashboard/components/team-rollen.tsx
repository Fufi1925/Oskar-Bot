"use client";

/**
 * Die offenen Rollen — auf der Team-Seite selbst.
 *
 * ── Die Lücke, die das schließt ─────────────────────────────────────
 *
 * Die Seite hieß „Team", zeigte zwei Karten und hörte dann auf. Dass
 * man dem Team beitreten kann, stand ausschließlich in einem
 * Aufklapp-Menü der Navigationsleiste — also genau dort, wo niemand
 * sucht, der gerade „Team" angeklickt hat. Wer die Seite besuchte,
 * bekam die Antwort auf „wer macht das?" und keine auf „kann ich
 * mitmachen?".
 *
 * ── Warum die Rollen live geholt werden ─────────────────────────────
 *
 * Weil sie sich schließen lassen. Im Admin-Bereich lässt sich jede
 * Rolle einzeln zumachen (`webapply/config`), und eine fest
 * einprogrammierte Liste hier würde weiter „Bewirb dich" sagen,
 * während die Bewerbung abgelehnt wird. Die Liste in der
 * Navigationsleiste ist genau deshalb ein Fehler, der irgendwann
 * auffällt — sie steht fest im Quelltext.
 *
 * Fällt der Bot aus, verschwindet der Abschnitt lieber ganz, statt
 * eine erfundene Liste zu zeigen. Ein Bewerbungsformular, das gerade
 * nicht erreichbar ist, hilft niemandem; die Einladung zum
 * Support-Server steht darunter weiterhin.
 *
 * ── Warum die Fragen hier stehen dürfen ─────────────────────────────
 *
 * Sie sind kein Geheimnis — das Formular zeigt sie ohnehin, sobald man
 * eine Rolle anklickt. Vorher zu wissen, was gefragt wird, hält
 * niemanden ab, der die Rolle ernsthaft will, und erspart allen
 * anderen eine halb ausgefüllte Bewerbung.
 */

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  ChevronDown,
  Clock,
  Loader2,
  Shield,
  Sparkles,
  Video,
  Wrench,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Rolle {
  key: string;
  label: string;
  short: string;
  colour: string;
  questions: number;
  question_list: string[];
  open: boolean;
}

/**
 * Ein Symbol je Rolle.
 *
 * Dieselbe Zuordnung wie im Bewerbungsformular. Ein Test vergleicht
 * beide: eine Rolle, die hier ein Symbol hat und dort nicht, sieht auf
 * den zwei Seiten unterschiedlich aus.
 */
const ROLLEN_ICON: Record<string, any> = {
  content: Video,
  designer: Sparkles,
  moderator: Shield,
  tester: Wrench,
};

/** Wie lange das Ausfüllen etwa dauert — grob, aber ehrlich. */
function dauer(fragen: number) {
  // Zweieinhalb Minuten pro Frage, auf fünf gerundet. Die Zahl ist
  // geschätzt und wird als Schätzung ausgewiesen ("etwa"): eine
  // erfundene Minutenangabe auf die Minute genau wäre eine Behauptung.
  const minuten = Math.max(5, Math.round((fragen * 2.5) / 5) * 5);
  return `etwa ${minuten} Minuten`;
}

export function TeamRollen() {
  const [rollen, setRollen] = React.useState<Rolle[] | null>(null);
  const [laedt, setLaedt] = React.useState(true);
  /** Welche Rolle ihre Fragen zeigt. */
  const [offen, setOffen] = React.useState<string>("");

  React.useEffect(() => {
    let abgebrochen = false;

    api
      .getApplyRoles()
      .then((antwort) => {
        if (abgebrochen) return;
        setRollen(antwort?.roles || []);
      })
      .catch(() => {
        // Bot aus, Wartung, kein Netz: alles derselbe Fall. Lieber
        // nichts zeigen als eine Liste, die nicht stimmt.
        if (!abgebrochen) setRollen(null);
      })
      .finally(() => {
        if (!abgebrochen) setLaedt(false);
      });

    return () => {
      abgebrochen = true;
    };
  }, []);

  if (laedt) {
    return (
      <div className="flex items-center justify-center rounded-2xl border border-slate-800 bg-[#131318] p-12">
        <Loader2 className="h-5 w-5 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  // Kein Bot erreichbar, oder gar keine Rollen hinterlegt.
  if (!rollen || rollen.length === 0) return null;

  const wirklichOffen = rollen.filter((r) => r.open);

  // Alle vier zu, und das ist eine eigene Aussage: „gerade niemand
  // gesucht" ist eine Antwort, eine leere Fläche ist keine.
  if (wirklichOffen.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-[#131318] p-6">
        <h3 className="text-[15px] font-bold text-white">
          Gerade suchen wir niemanden
        </h3>
        <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
          Alle Rollen sind im Moment geschlossen. Das ändert sich wieder —
          am besten schaust du gelegentlich vorbei oder fragst im
          Support-Server nach.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {wirklichOffen.map((rolle) => {
        const Icon = ROLLEN_ICON[rolle.key] ?? Sparkles;
        const zeigt = offen === rolle.key;

        return (
          <div
            key={rolle.key}
            className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]"
          >
            <div className="flex flex-wrap items-center gap-4 p-5">
              <span
                className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border"
                style={{
                  // Die Farbe kommt aus dem Bot, damit Formular und
                  // diese Seite dieselbe zeigen. Als Inline-Stil, weil
                  // Tailwind Klassen zur Bauzeit einsammelt und einen
                  // erst zur Laufzeit bekannten Farbwert nicht kennt.
                  borderColor: `${rolle.colour}40`,
                  backgroundColor: `${rolle.colour}1a`,
                }}
              >
                <Icon className="h-5 w-5" style={{ color: rolle.colour }} />
              </span>

              <div className="min-w-[180px] flex-1">
                <h3 className="text-[16px] font-bold text-white">
                  {rolle.label}
                </h3>
                <p className="mt-0.5 text-[13px] text-slate-400">
                  {rolle.short}
                </p>
              </div>

              <span className="flex shrink-0 items-center gap-1.5 text-[12px] text-slate-500">
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                {rolle.questions} Fragen · {dauer(rolle.questions)}
              </span>

              <Link
                href={`/team/apply?rolle=${rolle.key}`}
                className="flex shrink-0 items-center gap-2 rounded-xl bg-[#5865f2] px-4 py-2.5 text-[14px] font-bold text-white transition-colors hover:bg-[#4752c4]"
              >
                Bewerben
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>

            {rolle.question_list?.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => setOffen(zeigt ? "" : rolle.key)}
                  aria-expanded={zeigt}
                  className="flex w-full items-center justify-between border-t border-slate-800 bg-[#0f0f13] px-5 py-3 text-[13px] font-semibold text-slate-400 transition-colors hover:text-white"
                >
                  <span>
                    {zeigt ? "Fragen ausblenden" : "Diese Fragen werden gestellt"}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 shrink-0 transition-transform",
                      zeigt && "rotate-180",
                    )}
                  />
                </button>

                {zeigt && (
                  <ol className="space-y-2.5 border-t border-slate-800 bg-[#0e0e12] px-5 py-4">
                    {rolle.question_list.map((frage, i) => (
                      <li
                        key={i}
                        className="flex gap-3 text-[13px] leading-relaxed text-slate-400"
                      >
                        <span className="shrink-0 font-mono text-[12px] text-slate-600">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        {frage}
                      </li>
                    ))}
                  </ol>
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
