import React from "react";
import { AlertTriangle, FileText } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
import {
  ADDRESS,
  BRAND,
  EMAIL,
  LEGAL_UPDATED,
  OPERATOR,
  REGISTER,
  SUPPORT_INVITE,
  VAT_ID,
  addressOneLine,
  missingFields,
} from "@/lib/legal";

// Rendered per request, not baked in at build time.
//
// These pages read the operator's details from the environment, and
// those are configured in Railway *after* the image is built. As a
// static page the imprint would freeze whatever was set during the
// docker build -- which is nothing -- and keep reporting every field
// as missing however the deployment is configured.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Impressum",
  description: "Anbieterkennzeichnung nach § 5 DDG.",
};

/**
 * Imprint.
 *
 * § 5 DDG requires a real name and a postal address for anything
 * offered to the public -- a Discord tag is not enough, and neither is
 * an email address on its own. Those details can only come from the
 * operator, so they are read from the environment and the page says
 * plainly when they are missing rather than inventing something.
 *
 * The warning at the top is deliberate and deliberately loud. An
 * incomplete imprint on a publicly reachable site is a real risk in
 * Germany, and a quiet grey "[missing]" in the middle of the page is
 * easy to scroll past for months.
 */
function Missing({ what }: { what: string }) {
  return (
    <span className="text-amber-400/90">
      [{what} — fehlt, bitte in den Umgebungsvariablen hinterlegen]
    </span>
  );
}

export default function ImprintPage() {
  const missing = missingFields();

  return (
    <LegalPage
      title="Impressum"
      subtitle="Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG)."
      icon={FileText}
      updated={LEGAL_UPDATED}
    >
      {missing.length > 0 && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/[0.07] p-5">
          <div className="flex gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-sm leading-relaxed">
              <p className="font-bold text-amber-300">
                Dieses Impressum ist unvollständig.
              </p>
              <p className="text-amber-200/70 mt-1">
                Es fehlt: {missing.join(", ")}. Für ein öffentlich
                erreichbares Angebot verlangt § 5 DDG diese Angaben. Bitte
                die entsprechenden Umgebungsvariablen setzen
                (<code className="text-amber-200">IMPRINT_NAME</code>,{" "}
                <code className="text-amber-200">IMPRINT_ADDRESS</code>,{" "}
                <code className="text-amber-200">IMPRINT_EMAIL</code>) — ohne
                das Präfix <code className="text-amber-200">NEXT_PUBLIC_</code>,
                da diese Seite die Werte beim Aufruf liest und nicht beim Bauen.
              </p>
            </div>
          </div>
        </div>
      )}

      <Section title="Diensteanbieter">
        <p>{OPERATOR || <Missing what="Name des Betreibers" />}</p>
        <p className="whitespace-pre-line">
          {ADDRESS || <Missing what="Ladungsfähige Anschrift" />}
        </p>
        {VAT_ID && <p>USt-IdNr.: {VAT_ID}</p>}
        {REGISTER && <p>{REGISTER}</p>}
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
            href={SUPPORT_INVITE}
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
          {ADDRESS ? `, ${addressOneLine()}` : ""}
        </p>
      </Section>

      <Section title="Art des Angebots">
        <p>
          {BRAND} ist ein privat betriebenes, nicht kommerzielles Projekt.
          Die Nutzung ist kostenlos; es werden keine Zahlungen entgegen­
          genommen und keine Werbung ausgeliefert.
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
          Der Quellcode dieses Projekts ist nicht öffentlich und steht unter
          keiner freien Lizenz. Alle Rechte vorbehalten. Vervielfältigung,
          Weitergabe oder Veröffentlichung — ganz oder in Teilen — sind ohne
          ausdrückliche Zustimmung nicht gestattet.
        </p>
        <p>
          Marken, Logos und Inhalte Dritter — insbesondere von Discord Inc. —
          unterliegen den Rechten der jeweiligen Inhaber. Dieses Projekt steht
          in keiner Verbindung zu Discord Inc. und wird von Discord weder
          betrieben noch geprüft oder unterstützt.
        </p>
      </Section>
    </LegalPage>
  );
}
