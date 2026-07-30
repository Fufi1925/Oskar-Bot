import React from "react";
import { Scale } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
import {
  BRAND,
  LEGAL_UPDATED,
  PRIVACY_EMAIL,
  SUPPORT_INVITE,
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
  title: "Nutzungsbedingungen",
  description: "Die Regeln für die Nutzung des Bots und des Dashboards.",
};

/**
 * Terms of service.
 *
 * Replaces English marketing copy ("neural edge clusters", "immediate
 * neural deauthorization") that read like a science-fiction prop. Terms
 * are the document people are held to, so they have to be in the
 * language of the site and describe things that actually exist.
 *
 * Notably removed: the claim of striving for "100% uptime through our
 * neural edge clusters". It is one container on one host, and a hobby
 * project promising uptime in its terms is a promise it cannot keep.
 */
export default function TermsPage() {
  return (
    <LegalPage
      title="Nutzungsbedingungen"
      subtitle={`Die Regeln für die Nutzung von ${BRAND}.`}
      icon={Scale}
      updated={LEGAL_UPDATED}
    >
      <Section title="Worum es geht">
        <p>
          {BRAND} ist ein kostenloser Discord-Bot mit Web-Dashboard, betrieben
          als privates Projekt. Wer den Bot auf einen Server einlädt oder das
          Dashboard benutzt, akzeptiert diese Bedingungen.
        </p>
        <p>
          Zusätzlich gelten die{" "}
          <a
            href="https://discord.com/terms"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Nutzungsbedingungen von Discord
          </a>{" "}
          und deren{" "}
          <a
            href="https://discord.com/guidelines"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Community-Richtlinien
          </a>
          . Wer dort gesperrt ist, kann auch diesen Dienst nicht nutzen.
        </p>
      </Section>

      <Section title="Was erlaubt ist">
        <p>
          Den Bot auf eigenen Servern einsetzen, konfigurieren und benutzen —
          privat wie in Vereinen, Klassen oder Lerngruppen. Es gibt keine
          Nutzerobergrenze und keine kostenpflichtigen Funktionen.
        </p>
      </Section>

      <Section title="Was nicht erlaubt ist">
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          <li>
            Einsatz für Belästigung, Massen-Direktnachrichten (Spam), Raids
            oder das Umgehen von Sperren auf anderen Servern.
          </li>
          <li>
            Verbreitung rechtswidriger Inhalte über die Funktionen des Bots.
          </li>
          <li>
            Automatisiertes Abfragen der API außerhalb der vorgesehenen
            Nutzung, sowie Versuche, Beschränkungen oder Rechteprüfungen zu
            umgehen.
          </li>
          <li>
            Angriffe auf die Verfügbarkeit — Lastspitzen absichtlich
            erzeugen, Endpunkte in Schleife aufrufen und Vergleichbares.
          </li>
          <li>
            Nachbauen, Weitergeben oder Veröffentlichen des Quellcodes. Er
            ist nicht öffentlich und steht unter keiner freien Lizenz.
          </li>
        </ul>
        <p>
          Bei Verstößen können einzelne Nutzer oder ganze Server ohne
          Vorankündigung vom Dienst ausgeschlossen werden.
        </p>
      </Section>

      <Section title="Verantwortung der Server-Administratoren">
        <p>
          Wer den Bot einlädt, entscheidet über seine Konfiguration und ist
          für den Einsatz auf dem eigenen Server verantwortlich. Das gilt
          besonders für die Protokoll-Funktion: Wird sie eingeschaltet,
          landen Ereignisse aus dem Server in einem Kanal — wer das
          aktiviert, muss die Mitglieder darüber informieren.
        </p>
      </Section>

      <Section title="Verfügbarkeit">
        <p>
          Der Dienst wird bereitgestellt, <em>wie er ist</em>. Es gibt keine
          zugesicherte Verfügbarkeit: Wartungen, Updates, Störungen bei
          Discord oder beim Hoster können jederzeit zu Ausfällen führen. Der
          aktuelle Zustand ist im Support-Server einsehbar.
        </p>
        <p>
          Funktionen können sich ändern oder wegfallen. Der Betrieb kann
          eingestellt werden; in dem Fall wird das im Support-Server
          angekündigt, damit Einstellungen exportiert werden können.
        </p>
      </Section>

      <Section title="Haftung">
        <p>
          Für Vorsatz und grobe Fahrlässigkeit wird uneingeschränkt gehaftet,
          ebenso bei Verletzung von Leben, Körper oder Gesundheit. Bei
          einfacher Fahrlässigkeit besteht eine Haftung nur bei Verletzung
          wesentlicher Vertragspflichten und begrenzt auf den typischen,
          vorhersehbaren Schaden.
        </p>
        <p>
          Für Datenverluste, entgangene Konfigurationen oder Folgen von
          Ausfällen wird darüber hinaus nicht gehaftet. Es handelt sich um
          ein kostenloses Angebot — wichtige Konfigurationen sollten
          exportiert und selbst gesichert werden.
        </p>
      </Section>

      <Section title="Eigene Inhalte">
        <p>
          Texte, die ihr eingebt — Willkommensnachrichten, Autoresponder,
          Ankündigungen — bleiben eure. Sie werden ausschließlich verarbeitet,
          um die jeweilige Funktion auszuführen, und nicht anderweitig
          verwendet.
        </p>
      </Section>

      <Section title="Änderungen dieser Bedingungen">
        <p>
          Diese Bedingungen können angepasst werden, etwa wenn neue
          Funktionen hinzukommen. Wesentliche Änderungen werden im
          Support-Server angekündigt. Wer nicht einverstanden ist, kann den
          Bot jederzeit von seinem Server entfernen.
        </p>
      </Section>

      <Section title="Schlussbestimmungen">
        <p>
          Es gilt deutsches Recht. Sollte eine Bestimmung unwirksam sein,
          bleibt der Rest davon unberührt.
        </p>
        <p>
          Fragen? Am schnellsten im{" "}
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Support-Server
          </a>
          {PRIVACY_EMAIL ? (
            <>
              {" "}oder per Mail an{" "}
              <a
                href={`mailto:${PRIVACY_EMAIL}`}
                className="text-blue-400 hover:underline"
              >
                {PRIVACY_EMAIL}
              </a>
            </>
          ) : null}
          .
        </p>
      </Section>
    </LegalPage>
  );
}
