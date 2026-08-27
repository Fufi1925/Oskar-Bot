"use client";

/**
 * Das Support-Server-Fenster: „Tritt unserem Discord bei.“
 *
 * Erscheint nach der Anmeldung im Dashboard — für jeden, nicht nur
 * für Premium-Konten. Danach sieben Tage Ruhe, dann wieder. Wer auf
 * „Ja, beitreten“ drückt, sieht es gar nicht mehr.
 *
 * ── Warum der Abstand vom Server kommt ──────────────────────────────
 *
 * Ein Cookie hängt am Browser: am Telefon und am Rechner erschiene das
 * Fenster zweimal, nach dem Löschen der Cookies jedes Mal neu. Die
 * Frage hängt aber am Konto, also entscheidet der Bot.
 *
 * ── Warum es nicht sofort erscheint ─────────────────────────────────
 *
 * Eine kurze Verzögerung, damit es nicht in die Ladephase platzt. Wer
 * gerade eine Seite öffnet, will erst sehen, wo er ist — ein Fenster,
 * das über einem halb gerenderten Dashboard aufgeht, wird
 * weggeklickt, ohne gelesen zu werden.
 *
 * ── Warum kein Countdown wie beim Premium-Fenster ───────────────────
 *
 * Dort sagt das Fenster, was freigeschaltet wurde — das soll man
 * lesen. Hier ist es eine Einladung, und wer sie nicht will, soll sie
 * sofort wegklicken können.
 */

import React from "react";
import { usePathname } from "next/navigation";
import { MessageCircle, ArrowRight } from "lucide-react";
import { useSession } from "next-auth/react";

/** Wie lange gewartet wird, bevor es aufgeht. */
const VERZOEGERUNG_MS = 1200;

export function SupportHinweis() {
  const { data: session, status } = useSession();
  const pathname = usePathname();

  // Nur im Dashboard. Auf dem Impressum wäre es Werbung an der
  // falschen Stelle.
  const imDashboard = Boolean(pathname?.startsWith("/dashboard"));

  const [offen, setOffen] = React.useState(false);
  const [invite, setInvite] = React.useState("");
  const knopfRef = React.useRef<HTMLAnchorElement>(null);

  React.useEffect(() => {
    if (status !== "authenticated" || !session?.user?.id) return;
    if (!imDashboard) return;

    let abgebrochen = false;
    let timer: number | undefined;

    (async () => {
      try {
        const antwort = await fetch("/api/bot/beta/support-notice", {
          cache: "no-store",
        });
        if (!antwort.ok) return;
        const daten = await antwort.json();
        if (abgebrochen || !daten?.zeigen) return;

        setInvite(String(daten.invite || ""));
        timer = window.setTimeout(() => {
          if (!abgebrochen) setOffen(true);
        }, VERZOEGERUNG_MS);
      } catch {
        // Ein Aussetzer darf die Seite nicht stören.
      }
    })();

    return () => {
      abgebrochen = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [status, session?.user?.id, imDashboard]);

  // Fokus auf den Hauptknopf, sobald es offen ist.
  React.useEffect(() => {
    if (offen) knopfRef.current?.focus();
  }, [offen]);

  /**
   * Schließen und melden.
   *
   * Erst schließen, dann melden: andersherum hinge das Fenster bei
   * langsamem Netz — und bei einem Serverfehler für immer.
   */
  const schliessen = (beigetreten: boolean) => {
    setOffen(false);
    fetch("/api/bot/beta/support-notice/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ beigetreten }),
    }).catch(() => {
      /* beim nächsten Besuch erscheint es dann noch einmal */
    });
  };

  // Escape schließt — wie bei jedem Dialog erwartet.
  React.useEffect(() => {
    if (!offen) return;
    const aufTaste = (e: KeyboardEvent) => {
      if (e.key === "Escape") schliessen(false);
    };
    window.addEventListener("keydown", aufTaste);
    return () => window.removeEventListener("keydown", aufTaste);
  }, [offen]);

  if (!offen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="support-hinweis-titel"
      className="fixed inset-0 z-[99] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-3xl border border-fuchsia-500/40 shadow-2xl shadow-fuchsia-500/10"
        style={{
          // Der Verlauf aus der Vorlage: fast schwarz mit einem Hauch
          // Magenta in der oberen linken Ecke.
          background:
            "linear-gradient(135deg, #2a0f2b 0%, #17101c 45%, #131318 100%)",
        }}
      >
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className="shrink-0 rounded-2xl bg-fuchsia-500/15 p-3 ring-1 ring-fuchsia-500/30">
              <MessageCircle className="h-6 w-6 text-fuchsia-400" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-fuchsia-400/80">
                Community
              </div>
              <h2
                id="support-hinweis-titel"
                className="mt-1 text-xl font-bold text-white"
              >
                Tritt unserem Discord bei
              </h2>
            </div>
          </div>

          <p className="mt-4 text-sm leading-relaxed text-slate-300">
            Hilfe bei Problemen, Neues zuerst und Mitreden, was als
            Nächstes gebaut wird. Wir sind dort auch der Support.
          </p>

          <div className="mt-5 flex flex-col gap-2 sm:flex-row">
            {/* Ein echtes <a>: Rechtsklick, Mittelklick und
                Link-Vorschau bleiben so erhalten. Ein <button> mit
                window.open verliert alle drei. */}
            <a
              ref={knopfRef}
              href={invite || "#"}
              target="_blank"
              rel="noreferrer"
              onClick={() => schliessen(true)}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-fuchsia-500 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-fuchsia-400"
            >
              Ja, beitreten
              <ArrowRight className="h-4 w-4" />
            </a>

            <button
              onClick={() => schliessen(false)}
              className="inline-flex flex-1 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/[0.08]"
            >
              Nein danke
            </button>
          </div>

          {/* Damit niemand denkt, das kommt jetzt bei jedem Aufruf. */}
          <p className="mt-3 text-center text-[11px] text-slate-500">
            Wir fragen frühestens in 7 Tagen wieder.
          </p>
        </div>
      </div>
    </div>
  );
}
