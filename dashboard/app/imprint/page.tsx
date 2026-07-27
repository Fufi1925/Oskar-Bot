import React from "react";
import { FileText } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";

export const metadata = {
  title: "Impressum",
  description: "Anbieterkennzeichnung nach § 5 DDG.",
};

/**
 * Imprint.
 *
 * German law (§ 5 DDG, formerly § 5 TMG) requires a real name and a
 * postal address for anything offered to the public — a Discord tag is not
 * enough. Those details can only come from the operator, so they are read
 * from environment variables and the page says plainly when they are
 * missing rather than inventing something.
 */
const OPERATOR = process.env.NEXT_PUBLIC_IMPRINT_NAME || "";
const ADDRESS = process.env.NEXT_PUBLIC_IMPRINT_ADDRESS || "";
const EMAIL = process.env.NEXT_PUBLIC_IMPRINT_EMAIL || "";
const SUPPORT =
  process.env.NEXT_PUBLIC_SUPPORT_INVITE || "https://discord.gg/MG3rYnUZJV";

function Missing({ what }: { what: string }) {
  return (
    <span className="text-amber-400/90">
      [{what} — bitte in den Umgebungsvariablen hinterlegen]
    </span>
  );
}

export default function ImprintPage() {
  return (
    <LegalPage
      title="Impressum"
      subtitle="Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG)."
      icon={FileText}
      updated="27. Juli 2026"
    >
      <Section title="Diensteanbieter">
        <p>{OPERATOR || <Missing what="Name des Betreibers" />}</p>
        <p className="whitespace-pre-line">
          {ADDRESS || <Missing what="Ladungsfähige Anschrift" />}
        </p>
      </Section>

      <Section title="Kontakt">
        <p>
          E-Mail:{" "}
          {EMAIL ? (
            <a href={`mailto:${EMAIL}`} className="text-blue-400 hover:underline">
              {EMAIL}
            </a>
          ) : (
            <Missing what="E-Mail-Adresse" />
          )}
        </p>
        <p>
          Support:{" "}
          <a
            href={SUPPORT}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Discord-Server
          </a>
        </p>
      </Section>

      <Section title="Verantwortlich für den Inhalt">
        <p>
          {OPERATOR || <Missing what="Name des Betreibers" />}
          {ADDRESS ? `, ${ADDRESS.replace(/\n/g, ", ")}` : ""}
        </p>
      </Section>

      <Section title="Streitbeilegung">
        <p>
          Die Europäische Kommission stellt eine Plattform zur
          Online-Streitbeilegung bereit:{" "}
          <a
            href="https://ec.europa.eu/consumers/odr/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            ec.europa.eu/consumers/odr
          </a>
          .
        </p>
        <p>
          Wir sind nicht bereit und nicht verpflichtet, an
          Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle
          teilzunehmen.
        </p>
      </Section>

      <Section title="Haftung für Inhalte">
        <p>
          Als Diensteanbieter sind wir für eigene Inhalte auf diesen Seiten nach
          den allgemeinen Gesetzen verantwortlich. Wir sind jedoch nicht
          verpflichtet, übermittelte oder gespeicherte fremde Informationen zu
          überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige
          Tätigkeit hinweisen.
        </p>
        <p>
          Inhalte, die Nutzerinnen und Nutzer über den Bot auf ihren eigenen
          Discord-Servern erstellen, sind fremde Inhalte. Verpflichtungen zur
          Entfernung oder Sperrung bei Kenntnis einer konkreten Rechtsverletzung
          bleiben unberührt.
        </p>
      </Section>

      <Section title="Haftung für Links">
        <p>
          Unser Angebot enthält Links zu externen Websites Dritter, auf deren
          Inhalte wir keinen Einfluss haben. Für diese fremden Inhalte ist stets
          der jeweilige Anbieter verantwortlich. Eine permanente inhaltliche
          Kontrolle ist ohne konkrete Anhaltspunkte einer Rechtsverletzung nicht
          zumutbar.
        </p>
      </Section>

      <Section title="Urheberrecht">
        <p>
          Der Quellcode dieses Projekts steht unter der MIT-Lizenz. Marken,
          Logos und Inhalte Dritter — insbesondere von Discord Inc. — unterliegen
          den Rechten der jeweiligen Inhaber. Dieses Projekt steht in keiner
          Verbindung zu Discord Inc.
        </p>
      </Section>
    </LegalPage>
  );
}
