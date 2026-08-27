"use client";

/**
 * Das goldene Premium-Fenster.
 *
 * Wer Premium hat, bekommt es zu sehen: „Denk dran — du hast
 * Premium.“ Danach kommt es **alle sieben Tage** wieder. Wird Premium
 * entzogen und später neu vergeben, erscheint es sofort, dann als
 * „Willkommen zurück“.
 *
 * Der Abstand steht im Bot (`premium_notice.ABSTAND_TAGE`), nicht
 * hier. Zwei Stellen mit derselben Zahl laufen auseinander, und die
 * Entscheidung „ist es fällig?“ gehört ohnehin auf den Server: sie
 * hängt am Konto, nicht am Browser.
 *
 * Warum der Knopf fünf Sekunden wartet
 * ------------------------------------
 * So gewünscht — und der Grund liegt auf der Hand: das Fenster sagt,
 * was freigeschaltet wurde. Wer es sofort wegklicken kann, klickt es
 * weg, ohne gelesen zu haben, und fragt zwei Tage später im Support,
 * was Premium eigentlich bringt.
 *
 * Die Wartezeit gilt nur beim **ersten** Mal. Bei einer Rückkehr weiß
 * die Person längst, worum es geht.
 *
 * Warum der Zustand vom Server kommt
 * ----------------------------------
 * Ein Cookie hängt am Browser: am Telefon und am Rechner erschiene das
 * Fenster zweimal, nach dem Löschen der Cookies jedes Mal neu. Und der
 * Fall „nach einem Entzug wieder zeigen“ braucht das Wissen, dass es
 * dazwischen einen Entzug gab — das kann nur der Server.
 */

import React from "react";
import Link from "next/link";
import { Crown, Palette, Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";

/** Wie lange der Knopf beim ersten Mal gesperrt bleibt. */
const WARTEN_SEKUNDEN = 5;

export function PremiumHinweis() {
  const { data: session, status } = useSession();
  const pathname = usePathname();

  // Nur im Dashboard.
  //
  // Auf dem Impressum oder der Startseite nützt der Hinweis nichts --
  // dort gibt es nichts freizuschalten. Ausdrückliche Vorgabe: „immer
  // wenn man im Dashboard ist".
  const imDashboard = Boolean(pathname?.startsWith("/dashboard"));

  const [offen, setOffen] = React.useState(false);
  const [rueckkehr, setRueckkehr] = React.useState(false);
  const [rest, setRest] = React.useState(WARTEN_SEKUNDEN);
  const knopfRef = React.useRef<HTMLButtonElement>(null);

  // Fragen, ob das Fenster fällig ist. Erst wenn die Anmeldung steht —
  // ohne Konto gibt es kein Premium, und ein Aufruf ohne Sitzung
  // bekäme ohnehin nur ein Nein.
  React.useEffect(() => {
    if (status !== "authenticated" || !session?.user?.id) return;
    if (!imDashboard) return;

    let abgebrochen = false;
    (async () => {
      try {
        const antwort = await fetch("/api/bot/beta/notice", {
          cache: "no-store",
        });
        if (!antwort.ok) return;
        const daten = await antwort.json();
        if (abgebrochen || !daten?.zeigen) return;

        setRueckkehr(Boolean(daten.rueckkehr));
        // Bei einer Rückkehr keine Wartezeit.
        setRest(daten.rueckkehr ? 0 : WARTEN_SEKUNDEN);
        setOffen(true);
      } catch {
        // Ein Aussetzer darf die Seite nicht stören.
      }
    })();

    return () => {
      abgebrochen = true;
    };
  }, [status, session?.user?.id, imDashboard]);

  // Der Countdown.
  React.useEffect(() => {
    if (!offen || rest <= 0) return;
    const timer = setTimeout(() => setRest((r) => r - 1), 1000);
    return () => clearTimeout(timer);
  }, [offen, rest]);

  // Fokus auf den Knopf, sobald er benutzbar ist.
  React.useEffect(() => {
    if (offen && rest === 0) knopfRef.current?.focus();
  }, [offen, rest]);

  const schliessen = () => {
    // Erst schließen, dann melden. Andersherum hinge das Fenster bei
    // langsamem Netz — und bei einem Serverfehler für immer.
    setOffen(false);
    fetch("/api/bot/beta/notice/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }).catch(() => {
      /* beim nächsten Besuch erscheint es dann noch einmal */
    });
  };

  if (!offen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="premium-hinweis-titel"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-md overflow-hidden rounded-3xl border-2 border-amber-400 bg-[#131318] shadow-2xl shadow-amber-400/10">
        {/* Goldener Kopf */}
        <div className="bg-gradient-to-br from-amber-400/20 to-amber-600/5 px-6 pb-5 pt-6 text-center">
          <div className="mx-auto mb-3 w-fit rounded-2xl bg-amber-400/20 p-3">
            <Crown className="h-7 w-7 text-amber-400" />
          </div>
          <h2
            id="premium-hinweis-titel"
            className="text-xl font-bold text-amber-400"
          >
            {rueckkehr
              ? "Willkommen zurück — du hast Premium"
              : "Denk dran: du hast Premium"}
          </h2>
        </div>

        <div className="space-y-4 px-6 pb-6">
          <p className="text-sm leading-relaxed text-slate-300">
            {rueckkehr
              ? "Dein Premium ist wieder aktiv. Damit stehen dir diese Möglichkeiten erneut offen:"
              : "Damit ist für dich Folgendes freigeschaltet:"}
          </p>

          <ul className="space-y-2.5">
            <li className="flex gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
              <Palette className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div>
                <div className="text-sm font-medium text-white">
                  Eigenes Aussehen des Bots
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  Name, Profilbild und Banner — pro Server einstellbar, im
                  Reiter „Design“.
                </div>
              </div>
            </li>
            <li className="flex gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
              <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div>
                <div className="text-sm font-medium text-white">
                  Teil der Beta
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  Du siehst neue Funktionen als Erster. Rückmeldungen sind
                  ausdrücklich erwünscht.
                </div>
              </div>
            </li>
          </ul>

          <button
            ref={knopfRef}
            onClick={schliessen}
            disabled={rest > 0}
            className="w-full rounded-2xl bg-amber-400 px-4 py-3 text-sm font-bold text-black transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {rest > 0 ? `Ich hab verstanden (${rest})` : "Ich hab verstanden"}
          </button>

          {rest > 0 && (
            <p className="text-center text-xs text-slate-600">
              Lies kurz mit — der Knopf wird gleich frei.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
