import React from "react";
import { ShieldCheck } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
// Die Cookie-Liste steht EINMAL, in `lib/cookie-consent.ts`. Stünde sie
// hier ein zweites Mal, könnte das Hinweisfenster zwei Cookies nennen,
// während diese Seite drei aufzählt -- und beide Angaben wären belegbar
// falsch.
import { COOKIES } from "@/lib/cookie-consent";
import {
  ADDRESS,
  BRAND,
  HOSTER,
  HOSTER_ADDRESS,
  LEGAL_UPDATED,
  OPERATOR,
  PRIVACY_EMAIL,
  SUPPORT_INVITE,
  addressOneLine,
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
  title: "Datenschutzerklärung",
  description: "Welche Daten der Bot speichert, warum, und wie lange.",
};

/**
 * Privacy policy.
 *
 * The version this replaces was English marketing copy on a German
 * site, and two of its claims were simply false:
 *
 *   * "All configuration data is AES-256 encrypted at rest" -- it is
 *     not. The data sits in plain SQLite files. The only thing in the
 *     project called "encryption" is a cog that base64-encodes text on
 *     request, which is not encryption and not applied to stored data.
 *   * "distributed across global edge nodes" -- it runs in one
 *     container on one host.
 *
 * A privacy policy is the one document that has to be literally true:
 * it is a legal statement about what happens to other people's data,
 * and a wrong claim about encryption is exactly the kind that matters
 * after an incident. Everything below was checked against the code --
 * the list of what is stored comes from reading the actual database
 * schemas, not from guessing.
 */
export default function PrivacyPage() {
  const controller = OPERATOR || "der Betreiber dieses Angebots";

  return (
    <LegalPage
      title="Datenschutz"
      subtitle="Welche Daten verarbeitet werden, wozu, und wie du sie wieder loswirst."
      icon={ShieldCheck}
      updated={LEGAL_UPDATED}
    >
      <Section title="Kurzfassung">
        <p>
          {BRAND} speichert so wenig wie möglich: im Wesentlichen
          Discord-IDs (Zahlen) und die Einstellungen, die ihr im Dashboard
          vornehmt. <strong>Nachrichteninhalte werden nicht mitgelesen und
          nicht gespeichert</strong> — mit einer Ausnahme, die ihr selbst
          einrichtet und die weiter unten steht.
        </p>
        <p>
          Es gibt keine Werbung, kein Tracking, keine Analyse-Skripte und
          keine Weitergabe an Dritte.
        </p>
      </Section>

      <Section title="Verantwortlich">
        <p>
          {controller}
          {ADDRESS ? `, ${addressOneLine()}` : ""}
          {PRIVACY_EMAIL ? (
            <>
              {" "}—{" "}
              <a
                href={`mailto:${PRIVACY_EMAIL}`}
                className="text-blue-400 hover:underline"
              >
                {PRIVACY_EMAIL}
              </a>
            </>
          ) : null}
        </p>
        <p>
          Vollständige Anbieterangaben im{" "}
          <a href="/imprint" className="text-blue-400 hover:underline">
            Impressum
          </a>
          .
        </p>
      </Section>

      <Section title="Was der Bot speichert">
        <p>
          Alles unten Genannte liegt in Datenbanken auf dem Server des
          Bots. Gespeichert wird nur, was für die jeweilige Funktion
          gebraucht wird.
        </p>
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          <li>
            <strong className="text-slate-300">Server- und Kanal-IDs</strong> —
            damit Einstellungen dem richtigen Server zugeordnet werden.
          </li>
          <li>
            <strong className="text-slate-300">Benutzer-IDs</strong> — für
            Level-Punkte, Warnungen, Sperren, Ticket-Zuordnung,
            Geburtstage von Kanälen und Ähnliches. Es wird die Zahl
            gespeichert, nicht euer Name.
          </li>
          <li>
            <strong className="text-slate-300">Eure Einstellungen</strong> —
            gewählte Rollen, Kanäle, Schwellenwerte, an/aus-Schalter.
          </li>
          <li>
            <strong className="text-slate-300">Von euch verfasste Texte</strong>{" "}
            — Willkommensnachrichten, Autoresponder-Antworten,
            Sticky-Nachrichten, AFK- und Jail-Begründungen. Das sind Texte,
            die ihr selbst eingebt, keine mitgelesenen Nachrichten.
          </li>
          <li>
            <strong className="text-slate-300">Zähler und Zeitstempel</strong> —
            etwa wann eine Aktion zuletzt ausgeführt wurde, damit
            Wiederholungssperren funktionieren.
          </li>
        </ul>
      </Section>

      <Section title="Was der Bot nicht speichert">
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          <li>Keine Nachrichteninhalte aus euren Kanälen.</li>
          <li>Keine E-Mail-Adressen, Telefonnummern oder Passwörter.</li>
          <li>Keine IP-Adressen zu Werbe- oder Analysezwecken.</li>
          <li>Keine Daten von Servern, auf denen der Bot nicht ist.</li>
        </ul>
        <p>
          <strong className="text-slate-300">Die eine Ausnahme:</strong> Wenn
          ein Server-Administrator die Protokoll-Funktion („Logging“)
          einschaltet, schreibt der Bot Ereignisse wie gelöschte oder
          bearbeitete Nachrichten in einen Kanal <em>auf eurem eigenen
          Server</em>. Diese Nachrichten liegen dann bei Discord in eurem
          Server, nicht in unserer Datenbank. Wer das einschaltet, ist für
          diese Verarbeitung selbst verantwortlich.
        </p>
      </Section>

      <Section title="Anmeldung am Dashboard">
        <p>
          Die Anmeldung läuft über Discord (OAuth2). Dabei erhalten wir von
          Discord eure Benutzer-ID, den Anzeigenamen, das Profilbild und die
          Liste eurer Server mit den jeweiligen Berechtigungen — mehr nicht,
          insbesondere keine E-Mail-Adresse.
        </p>
        <p>
          Diese Angaben stehen in einem Sitzungs-Cookie, das nur der
          Anmeldung dient. Beim Abmelden endet die Sitzung; das Cookie
          läuft spätestens nach 30 Tagen ab. Es findet keine Auswertung
          eures Verhaltens statt.
        </p>
      </Section>

      <Section title="Cookies">
        <p>
          Es werden ausschließlich technisch notwendige Cookies gesetzt —
          keine Werbe-, Tracking- oder Analyse-Cookies. Für solche Cookies
          ist nach § 25 Abs. 2 TDDDG keine Einwilligung nötig; der Hinweis
          beim ersten Besuch ist deshalb eine Information und keine
          Abfrage. Aus demselben Grund gibt es dort keinen
          Ablehnen-Knopf: er könnte nichts abschalten, ohne die Anmeldung
          mit abzuschalten.
        </p>
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          {COOKIES.map((eintrag) => (
            <li key={eintrag.name}>
              <code className="text-slate-300">{eintrag.name}</code> —{" "}
              {eintrag.zweck} <em>Laufzeit: {eintrag.dauer}.</em>
            </li>
          ))}
        </ul>
        <p>
          <strong className="text-slate-300">
            Warum die Bestätigung gespeichert wird:
          </strong>{" "}
          Art. 7 Abs. 1 DSGVO verlangt, dass sich eine Einwilligung
          nachweisen lässt. Festgehalten werden dafür die vom Browser
          erzeugte Zufallskennung, der Zeitpunkt, die Fassung des
          Hinweistextes und die Seite, auf der er stand — sowie eure
          Discord-ID, falls ihr zu dem Zeitpunkt angemeldet wart.{" "}
          <strong className="text-slate-300">
            Keine IP-Adresse, kein Browser-Kennzeichen.
          </strong>{" "}
          Nach 400 Tagen wird der Eintrag automatisch gelöscht, auf Anfrage
          sofort.
        </p>
      </Section>

      <Section title="Wie die Daten gespeichert sind">
        <p>
          Ehrlich gesagt: in gewöhnlichen SQLite-Datenbankdateien auf dem
          Server, auf dem der Bot läuft. Sie sind <strong>nicht zusätzlich
          verschlüsselt</strong>. Geschützt sind sie dadurch, dass niemand
          außer dem Betreiber Zugriff auf den Server hat und das Dashboard
          jede Anfrage gegen eure Discord-Berechtigungen prüft.
        </p>
        <p>
          Wir sagen das so deutlich, weil hier vorher „AES-256-verschlüsselt“
          stand. Das war falsch, und bei einer Datenschutzerklärung ist eine
          bequeme Unwahrheit schlimmer als eine unbequeme Tatsache.
        </p>
        <p>
          Es werden automatisch Sicherungskopien angelegt (einmal täglich,
          nur die jeweils neueste wird aufbewahrt). Sie liegen auf demselben
          Server und unterliegen denselben Löschregeln.
        </p>
      </Section>

      <Section title="Wer die Daten sonst noch sieht">
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          <li>
            <strong className="text-slate-300">Discord Inc.</strong> — ohne
            Discord funktioniert ein Discord-Bot nicht. Für alles, was in
            Discord passiert, gilt deren{" "}
            <a
              href="https://discord.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:underline"
            >
              Datenschutzerklärung
            </a>
            .
          </li>
          <li>
            <strong className="text-slate-300">{HOSTER}</strong> — dort läuft
            der Server ({HOSTER_ADDRESS}). Die Übermittlung in die USA
            erfolgt auf Grundlage der Standardvertragsklauseln.
          </li>
          <li>
            <strong className="text-slate-300">Sonst niemand.</strong> Keine
            Weitergabe, kein Verkauf, keine Werbenetzwerke.
          </li>
        </ul>
      </Section>

      <Section title="Wie lange">
        <ul className="list-disc pl-5 space-y-2 text-slate-400">
          <li>
            Einstellungen bleiben, solange der Bot auf dem Server ist.
          </li>
          <li>
            Wird der Bot von einem Server entfernt, werden die Daten dieses
            Servers bei der nächsten automatischen Bereinigung gelöscht.
          </li>
          <li>
            Sicherungskopien werden täglich überschrieben; es wird nur die
            neueste aufbewahrt.
          </li>
          <li>Auf Anfrage wird sofort gelöscht (siehe unten).</li>
        </ul>
      </Section>

      <Section title="Eure Rechte">
        <p>
          Nach DSGVO habt ihr das Recht auf Auskunft (Art. 15), Berichtigung
          (Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung
          (Art. 18), Datenübertragbarkeit (Art. 20) und Widerspruch
          (Art. 21).
        </p>
        <p>
          In der Praxis am schnellsten:{" "}
          {PRIVACY_EMAIL ? (
            <>
              eine kurze Mail an{" "}
              <a
                href={`mailto:${PRIVACY_EMAIL}`}
                className="text-blue-400 hover:underline"
              >
                {PRIVACY_EMAIL}
              </a>
            </>
          ) : (
            "eine Nachricht an den Betreiber"
          )}{" "}
          oder eine Nachricht im{" "}
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Support-Server
          </a>
          . Bitte die betroffene Benutzer- oder Server-ID mitschicken, sonst
          lässt sich nichts zuordnen.
        </p>
        <p>
          Außerdem besteht ein Beschwerderecht bei einer
          Datenschutz-Aufsichtsbehörde (Art. 77 DSGVO).
        </p>
      </Section>

      <Section title="Rechtsgrundlage">
        <p>
          Die Verarbeitung erfolgt zur Erfüllung des Nutzungsverhältnisses
          (Art. 6 Abs. 1 lit. b DSGVO) sowie auf Grundlage des berechtigten
          Interesses am Betrieb eines funktionsfähigen und missbrauchs­
          sicheren Dienstes (Art. 6 Abs. 1 lit. f DSGVO).
        </p>
      </Section>

      <Section title="Minderjährige">
        <p>
          Für die Nutzung von Discord gilt ein Mindestalter von 13 Jahren
          (in einigen Ländern höher). Wir richten uns an dieselbe
          Zielgruppe und erheben wissentlich keine Daten von jüngeren
          Personen.
        </p>
      </Section>

      <Section title="Änderungen">
        <p>
          Ändert sich etwas Wesentliches, wird diese Seite aktualisiert und
          das Datum oben angepasst. Größere Änderungen kündigen wir im
          Support-Server an.
        </p>
      </Section>
    </LegalPage>
  );
}
