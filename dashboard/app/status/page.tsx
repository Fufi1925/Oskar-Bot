import React from "react";
import { Activity } from "lucide-react";
import { LegalPage } from "@/components/legal-page";
import { BRAND } from "@/lib/legal";
import { StatusLive } from "@/components/status-live";

export const metadata = {
  title: "Status",
  description: "Läuft der Bot gerade?",
};

// Nie zwischengespeichert. Eine Statusseite, die einen fünf Minuten
// alten Zustand zeigt, ist schlechter als keine: sie sagt „alles in
// Ordnung" mitten in einer Störung.
export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * Die Status-Seite.
 *
 * ── Warum hier fast nichts mehr steht ───────────────────────────────
 *
 * Vorher holte diese Datei die Zahlen beim Rendern auf dem Server und
 * malte sie als feste Liste hin. Das hatte zwei Nachteile, und beide
 * fielen genau dann auf, wenn die Seite gebraucht wurde:
 *
 *   * **Sie blieb stehen.** Wer sie während einer Störung offen ließ,
 *     las eine halbe Stunde später immer noch „Störung", obwohl längst
 *     alles lief.
 *   * **Sie zeigte nur den Moment.** Keine Antwort auf „war das eben
 *     nur kurz?" oder „wie oft passiert das?".
 *
 * Die Arbeit macht jetzt `StatusLive` im Browser, über `/api/status`.
 * Diese Datei liefert nur noch den Rahmen — denselben wie Impressum
 * und Datenschutz, damit die Seite nicht aus der Reihe fällt.
 */
export default function StatusPage() {
  return (
    <LegalPage
      title="Status"
      subtitle="Läuft der Bot gerade? Diese Seite fragt einen unabhängigen Wächter — nicht den Bot selbst."
      icon={Activity}
    >
      <StatusLive marke={BRAND} />
    </LegalPage>
  );
}
