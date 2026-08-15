import React from "react";
import { MessageSquare, Users } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
import { SUPPORT_INVITE } from "@/lib/legal";
import { TeamMitglieder, type Mitglied } from "@/components/team-mitglieder";
import { TeamRollen } from "@/components/team-rollen";

export const metadata = {
  title: "Team",
  description: "Die Menschen hinter dem Bot — und wie du mitmachst.",
};

// Pro Aufruf gerendert, nicht beim Bauen: die Avatare kommen vom
// laufenden Bot, und der läuft während des Docker-Builds nicht.
export const dynamic = "force-dynamic";

/**
 * Die Team-Seite.
 *
 * ── Was an der alten Fassung fehlte ─────────────────────────────────
 *
 * Sie beantwortete „wer macht das?" und hörte dann auf. Die Frage
 * „kann ich mitmachen?" beantwortete sie nicht — dass es vier offene
 * Rollen gibt, stand ausschließlich in einem Aufklapp-Menü der
 * Navigationsleiste. Also genau dort, wo niemand sucht, der gerade
 * „Team" angeklickt hat. Eine Seite mit zwei Karten und ohne Weg nach
 * vorn.
 *
 * Dazu kamen zwei kleinere Sachen, die im Bild auffielen:
 *
 *   * Die Discord-ID stand als toter Text da. Achtzehn Ziffern, die
 *     man abschreiben durfte — das tippt niemand fehlerfrei ab.
 *   * Die Karten trugen `bg-white/[0.02]` und `border-white/[0.05]`,
 *     einen Stil, den es sonst nirgends mehr gibt. Der Rest der Seite
 *     ist auf `#131318` mit `border-slate-800` vereinheitlicht.
 *
 * ── Was jetzt drinsteht ─────────────────────────────────────────────
 *
 *   1. Wer dahintersteckt, mit kopierbarer ID.
 *   2. **Die offenen Rollen**, live vom Bot geholt — mit den Fragen
 *      zum Aufklappen und einem Knopf, der direkt ins Formular führt.
 *   3. Wie man uns erreicht.
 *
 * ── Warum die Rollen nicht hier geladen werden ──────────────────────
 *
 * Diese Datei ist eine Server-Komponente und könnte sie mitliefern.
 * Sie tut es nicht: dann würde ein langsamer oder toter Bot die ganze
 * Seite aufhalten, samt Impressum-Fußzeile. So kommt die Seite sofort,
 * und der Rollen-Abschnitt füllt sich nach. Die Namen und Avatare
 * dagegen holt der Server — sie stehen in der ersten Auslieferung
 * drin, mit einer knappen Zeitgrenze.
 */

const API_BASE_URL =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

/**
 * Das Team, als reine Daten.
 *
 * `NEXT_PUBLIC_TEAM_JSON` überschreibt die Liste beim Deploy, ohne dass
 * jemand die Datei anfassen muss.
 *
 * Keine GitHub-Felder: das Repository ist privat und bleibt es. Ein
 * Link auf eine 404-Seite verrät, dass es das Projekt auf GitHub gibt,
 * und lädt zum Suchen ein — das Gegenteil des Zwecks.
 */
const DEFAULT_TEAM: Mitglied[] = [
  {
    id: "1303627964734246944",
    name: "Fufi",
    role: "Entwickler & Betrieb",
    description:
      "Baut und betreibt den Bot und das Dashboard. Kümmert sich um " +
      "Updates, Störungen und den Support.",
  },
  {
    id: "1033826242270609449",
    name: "Vexo",
    role: "Entwickler · Template-Bot",
    description:
      "Von ihm stammt die ursprüngliche Idee zum Projekt. Entwickelt " +
      "den Template-Bot mit den fertigen Server-Vorlagen.",
  },
];

interface Profil {
  id: string;
  name: string | null;
  avatar: string | null;
}

/**
 * Echte Discord-Namen und Avatare.
 *
 * Eine Avatar-Adresse lässt sich aus einer ID nicht bauen: der
 * CDN-Pfad braucht den Avatar-Hash, den nur der Bot kennt. Antwortet
 * er nicht — etwa während eines Deploys —, kommt hier nichts zurück
 * und die Karten zeigen Initialen. Eine Team-Seite ist keinen
 * Serverfehler wert.
 */
async function ladeProfile(ids: string[]): Promise<Record<string, Profil>> {
  try {
    const headers: Record<string, string> = {};
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const antwort = await fetch(
      `${API_BASE_URL}/bot/profiles?ids=${ids.join(",")}`,
      { headers, cache: "no-store", signal: AbortSignal.timeout(4000) },
    );
    if (!antwort.ok) return {};
    const daten = await antwort.json();
    return daten?.profiles || {};
  } catch {
    return {};
  }
}

function ladeTeam(): Mitglied[] {
  const roh = process.env.NEXT_PUBLIC_TEAM_JSON;
  if (!roh) return DEFAULT_TEAM;
  try {
    const gelesen = JSON.parse(roh);
    return Array.isArray(gelesen) && gelesen.length ? gelesen : DEFAULT_TEAM;
  } catch {
    // Eine kaputte Variable darf die Seite nicht mitnehmen.
    return DEFAULT_TEAM;
  }
}

export default async function TeamPage() {
  const team = ladeTeam();
  const profile = await ladeProfile(
    team.map((person) => person.id).filter(Boolean),
  );

  // Die Live-Daten werden hier angehängt, nicht in der Komponente:
  // die Karten sollen in der ersten Auslieferung schon fertig sein.
  const mitgliederMitProfil: Mitglied[] = team.map((person) => ({
    ...person,
    liveName: profile[person.id]?.name ?? null,
    avatar: profile[person.id]?.avatar ?? null,
  }));

  return (
    <LegalPage
      title="Team"
      subtitle="Die Menschen, die den Bot bauen und betreiben — und die Rollen, für die wir Verstärkung suchen."
      icon={Users}
    >
      <Section title="Wer dahintersteckt">
        <TeamMitglieder mitglieder={mitgliederMitProfil} />
      </Section>

      <Section title="Mitmachen">
        <p>
          Das Team ist klein, und deshalb suchen wir Leute. Vorkenntnisse
          in Programmierung braucht keine der Rollen — Zeit und
          Verlässlichkeit schon. Die Bewerbung läuft über ein kurzes
          Formular; du brauchst dafür nur deinen Discord-Login.
        </p>
        <TeamRollen />
      </Section>

      <Section title="Kontakt">
        <p>
          Fehler gefunden, Frage oder ein Vorschlag? Am schnellsten geht es
          über den Support-Server — dort sind wir beide erreichbar. Für
          etwas Persönliches kannst du auch direkt schreiben; die
          Discord-IDs stehen oben auf den Karten zum Kopieren.
        </p>
        <p className="pt-2">
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-[#131318] px-4 py-2.5 text-[14px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
          >
            <MessageSquare className="h-4 w-4 text-indigo-400" />
            Support-Server beitreten
          </a>
        </p>
      </Section>
    </LegalPage>
  );
}
