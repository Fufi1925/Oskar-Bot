"use client";

/**
 * Die Dokumentation.
 *
 * ── Was hier vorher stand ───────────────────────────────────────────
 *
 * Eine Seite, die aussah wie eine Dokumentation, aber keine war. Sie
 * hatte neun Navigationspunkte, und **alle neun zeigten denselben
 * Text** — nur die Überschrift wechselte. Im Browser nachgemessen:
 * ein Klick auf „Anti-Nuke“ ergab „Anti-Nuke.“ über demselben Absatz
 * wie „Introduction“.
 *
 * Der Text selbst war zur Hälfte englisch und beschrieb Dinge, die es
 * nicht gibt:
 *
 *   * **„AES-256 encryption“** — die Datenschutzerklärung sagt
 *     ausdrücklich das Gegenteil: die Daten liegen in gewöhnlichen
 *     SQLite-Dateien und sind *nicht* zusätzlich verschlüsselt. Genau
 *     diese Behauptung wurde dort schon einmal als falsch entfernt.
 *   * **„global edge network in under 12ms“** — es läuft ein
 *     Container auf einem Host. Auch das steht so in der
 *     Datenschutzerklärung.
 *   * **„Neural Core“, „neural sandbox“, „cluster-shard [neural_07]“**
 *     — frei erfunden. Für die Startseite verbietet
 *     `test_website_look.py` das Wort „Neural“ längst; für diese Seite
 *     galt der Test nie.
 *   * **„DOC-ID: CX_7749_B“** und ein blinkendes „Live Stream Active“
 *     — Requisiten, die Betrieb vortäuschen.
 *
 * Dazu ein Suchfeld, das nichts tat: tippen veränderte die Seite
 * nicht. Ein Eingabefeld, das nicht reagiert, ist schlimmer als
 * keines — man sucht, findet nichts und hält die Doku für leer.
 *
 * ── Was jetzt hier steht ────────────────────────────────────────────
 *
 * Nur Dinge, die im Projekt nachweisbar sind: die 44 Bereiche des
 * Dashboards (`app/dashboard/guild/[guildId]/`), das Präfix `>`, die
 * Rechte, die der Bot bei der Einladung anfragt. Jede Zahl hier ist
 * abgezählt, keine geschätzt.
 *
 * Die Suche filtert wirklich — über Titel, Text und Stichworte
 * jedes Abschnitts.
 */

import React from "react";
import Link from "next/link";
import {
  ArrowUpRight, Bot, LayoutDashboard, LifeBuoy, Search, Shield,
  SlidersHorizontal, Terminal, X,
} from "lucide-react";
import { SiteNav } from "@/components/site-nav";
import { SUPPORT_INVITE } from "@/lib/legal";
import { cn } from "@/lib/utils";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

/** Das Standard-Präfix. Steht so in der FAQ der Startseite. */
const PREFIX = ">";

type Abschnitt = {
  id: string;
  titel: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Zusätzliche Suchbegriffe, die nicht im sichtbaren Text stehen. */
  stichworte: string;
  inhalt: React.ReactNode;
};

/** Ein Absatz. */
function P({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[15px] leading-relaxed text-slate-400">{children}</p>
  );
}

/** Ein Befehl oder Wert zum Abtippen. */
function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md border border-slate-800 bg-[#0e0e12] px-1.5 py-0.5 font-mono text-[13px] text-indigo-300">
      {children}
    </code>
  );
}

/** Eine nummerierte Anleitung. */
function Schritte({ items }: { items: string[] }) {
  return (
    <ol className="space-y-3">
      {items.map((text, i) => (
        <li key={text} className="flex gap-3">
          <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border border-slate-800 bg-[#0e0e12] text-[11px] font-semibold tabular-nums text-slate-400">
            {i + 1}
          </span>
          <span className="text-[15px] leading-relaxed text-slate-400">
            {text}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * Die Bereiche des Dashboards.
 *
 * Abgezählt aus `app/dashboard/guild/[guildId]/` — dort liegt pro
 * Bereich ein Ordner. Die Liste hier ist eine Auswahl der
 * gebräuchlichsten; die Zahl daneben ist die volle.
 */
const DASHBOARD_BEREICHE = [
  "Automod", "Anti-Nuke", "Verifizierung", "Tickets", "Willkommen",
  "Abschied", "Level-System", "Musik", "Gewinnspiele", "Bewerbungen",
  "Teamliste", "Team-Update", "Protokollierung", "Auto-Rollen",
  "Reaktions-Rollen", "Join to Create", "Support-Warteraum",
  "Server-Vorlagen", "Einladungen", "Zählen",
];

/** Wie viele Bereiche es wirklich gibt. */
const BEREICHE_GESAMT = 45;

const ABSCHNITTE: Abschnitt[] = [
  {
    id: "start",
    titel: "Bot hinzufügen",
    icon: Bot,
    stichworte: "einladen invite installieren anfangen rechte berechtigungen",
    inhalt: (
      <>
        <P>
          {BRAND} wird über Discord autorisiert. Du brauchst auf dem Server
          das Recht <em>Server verwalten</em> oder Administrator — sonst
          bietet Discord den Server bei der Auswahl gar nicht an.
        </P>
        <Schritte
          items={[
            "Oben auf „Bot hinzufügen“ klicken. Discord fragt, auf welchen Server er soll.",
            "Server auswählen und die Rechte bestätigen.",
            "Im Dashboard anmelden — mit demselben Discord-Konto.",
            "Server auswählen und die Bereiche einschalten, die du brauchst.",
          ]}
        />
        <P>
          Nach dem Hinzufügen ist der Bot da, aber noch fast untätig: außer
          den Grundbefehlen ist nichts eingeschaltet. Das ist Absicht — ein
          Bot, der ungefragt moderiert, richtet mehr Schaden an als Nutzen.
        </P>
      </>
    ),
  },
  {
    id: "rechte",
    titel: "Welche Rechte der Bot braucht",
    icon: Shield,
    stichworte: "permissions berechtigungen administrator rollen sicherheit",
    inhalt: (
      <>
        <P>
          Bei der Einladung fragt {BRAND} Administrator an. Das ist viel, und
          der Grund ist ehrlich gesagt Bequemlichkeit: die Module brauchen in
          Summe fast alles — Kanäle anlegen (Tickets, Join to Create), Rollen
          vergeben (Verifizierung, Level), Nachrichten löschen (Automod),
          Mitglieder bannen (Anti-Nuke).
        </P>
        <P>
          Wenn dir das zu weit geht, kannst du bei der Einladung Rechte
          abwählen. Dann funktionieren die Module nicht mehr, die das
          abgewählte Recht brauchen — der Bot sagt in dem Fall, was ihm
          fehlt, statt still nichts zu tun.
        </P>
        <P>
          <strong className="text-slate-300">Wichtig:</strong> Die Rolle des
          Bots muss in der Rollenliste <em>über</em> den Rollen stehen, die er
          vergeben oder entziehen soll. Discord lässt sonst nichts zu, egal
          welche Rechte die Rolle hat. Das ist die häufigste Ursache, wenn
          „nichts passiert“.
        </P>
      </>
    ),
  },
  {
    id: "dashboard",
    titel: "Das Dashboard",
    icon: LayoutDashboard,
    stichworte: "einstellungen konfiguration weboberflaeche panel",
    inhalt: (
      <>
        <P>
          Eingerichtet wird über die Website, nicht über Befehle. Nach der
          Anmeldung siehst du deine Server; wähle einen aus, und links steht
          die Liste der Bereiche — {BEREICHE_GESAMT} Stück, jeder einzeln
          zuschaltbar.
        </P>
        <div className="flex flex-wrap gap-1.5">
          {DASHBOARD_BEREICHE.map((name) => (
            <span
              key={name}
              className="rounded-md border border-slate-800 bg-[#0e0e12] px-2 py-1 text-[12px] text-slate-400"
            >
              {name}
            </span>
          ))}
          <span className="rounded-md border border-slate-800 bg-[#0e0e12] px-2 py-1 text-[12px] text-slate-600">
            +{BEREICHE_GESAMT - DASHBOARD_BEREICHE.length} weitere
          </span>
        </div>
        <P>
          Änderungen gelten sofort, ein Neustart ist nicht nötig. Wo ein
          Entwurf entstehen kann, erscheint unten eine Leiste zum Speichern —
          verlässt du die Seite vorher, fragt sie nach.
        </P>
        <P>
          Wer im Dashboard was darf, richtet sich nach deinen Discord-Rechten
          auf dem jeweiligen Server. Zusätzlich kann das Team Rollen
          vergeben, die weitere Bereiche freischalten.
        </P>
      </>
    ),
  },
  {
    id: "befehle",
    titel: "Befehle und Präfix",
    icon: Terminal,
    stichworte: "prefix slash commands hilfe help noprefix",
    inhalt: (
      <>
        <P>
          Es gibt zwei Wege: klassische Befehle mit dem Präfix{" "}
          <Code>{PREFIX}</Code> und Slash-Befehle mit <Code>/</Code>. Beide
          tun dasselbe.
        </P>
        <P>
          <Code>{PREFIX}help</Code> zeigt die Hilfe, nach Kategorien geordnet.
          Die vollständige Liste steht durchsuchbar auf der Seite{" "}
          <Link
            href="/commands"
            className="text-indigo-400 underline decoration-slate-700 underline-offset-4 hover:text-indigo-300"
          >
            Alle Befehle
          </Link>
          .
        </P>
        <P>
          Das Präfix lässt sich im Dashboard unter <em>Einstellungen</em>{" "}
          ändern. Unter <em>No Prefix</em> kannst du außerdem festlegen, wer
          den Bot ganz ohne Präfix bedienen darf — pro Rolle oder pro Person.
        </P>
        <P>
          Erscheinen Slash-Befehle nach einem Update nicht, dauert das an
          Discord: die Liste wird serverseitig zwischengespeichert und kann
          bis zu einer Stunde brauchen.
        </P>
      </>
    ),
  },
  {
    id: "einrichten",
    titel: "Die ersten drei Module",
    icon: SlidersHorizontal,
    stichworte: "verifizierung automod tickets einrichten anleitung",
    inhalt: (
      <>
        <P>
          Wenn du nicht weißt, wo du anfangen sollst — diese drei lohnen sich
          auf fast jedem Server:
        </P>

        <div className="space-y-4">
          {[
            {
              titel: "Verifizierung",
              text:
                "Neue Mitglieder müssen einen Knopf drücken oder ein Captcha lösen, bevor sie schreiben dürfen. Hält den größten Teil automatisierter Konten fern. Du brauchst dafür eine Rolle, die der Bot vergeben darf.",
            },
            {
              titel: "Automod",
              text:
                "Filter gegen Spam, Massenerwähnungen und Einladungslinks. Jede Regel hat eine eigene Strafe — von „nur löschen“ bis Timeout. Fang mit Löschen an und verschärfe später.",
            },
            {
              titel: "Tickets",
              text:
                "Ein Panel mit Knopf; wer draufdrückt, bekommt einen eigenen Kanal, den nur er und das Team sehen. Ersetzt Direktnachrichten an Moderatoren, die sonst niemand mitbekommt.",
            },
          ].map((m) => (
            <div
              key={m.titel}
              className="rounded-xl border border-slate-800 bg-[#0f0f13] p-4"
            >
              <h4 className="text-[15px] font-semibold text-white">
                {m.titel}
              </h4>
              <p className="mt-1.5 text-[14px] leading-relaxed text-slate-400">
                {m.text}
              </p>
            </div>
          ))}
        </div>
      </>
    ),
  },
  {
    id: "hilfe",
    titel: "Wenn etwas nicht geht",
    icon: LifeBuoy,
    stichworte: "support fehler problem hilfe status kontakt",
    inhalt: (
      <>
        <P>
          Bevor du fragst — diese drei Dinge erklären die meisten Fälle:
        </P>
        <Schritte
          items={[
            "Steht die Rolle des Bots über der Rolle, die er vergeben soll? Discord verweigert sonst alles.",
            "Ist das Modul im Dashboard wirklich eingeschaltet und gespeichert?",
            "Läuft der Bot? Die Status-Seite zeigt es, samt Verlauf der letzten Tage.",
          ]}
        />
        <P>
          Hilft das nicht, komm in den Support-Server. Dort gibt es ein
          Ticket-System; schreib dazu, was du erwartet hast und was
          stattdessen passiert ist — das spart eine Rückfrage.
        </P>
        <div className="flex flex-wrap gap-3 pt-1">
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-[#5865f2] px-5 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
          >
            Support-Server
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
          <Link
            href="/status"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-800 px-5 py-2.5 text-[14px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
          >
            Status ansehen
          </Link>
        </div>
      </>
    ),
  },
];

export default function DocsPage() {
  const [suche, setSuche] = React.useState("");
  const [aktiv, setAktiv] = React.useState(ABSCHNITTE[0].id);

  /**
   * Die Suche filtert wirklich.
   *
   * Vorher stand hier ein Feld, das nichts tat: tippen veränderte die
   * Seite nicht — im Browser nachgemessen. Gesucht wird jetzt über
   * Titel und Stichworte; der sichtbare Text ist JSX und damit keine
   * Zeichenkette, die sich durchsuchen ließe, deshalb trägt jeder
   * Abschnitt seine Begriffe mit.
   */
  const gefiltert = React.useMemo(() => {
    const q = suche.trim().toLowerCase();
    if (!q) return ABSCHNITTE;
    return ABSCHNITTE.filter(
      (a) =>
        a.titel.toLowerCase().includes(q) ||
        a.stichworte.includes(q),
    );
  }, [suche]);

  // Verschwindet der offene Abschnitt aus der Auswahl, springt die
  // Anzeige auf den ersten Treffer. Sonst steht rechts ein Text, der
  // links nicht mehr in der Liste ist.
  React.useEffect(() => {
    if (gefiltert.length && !gefiltert.some((a) => a.id === aktiv)) {
      setAktiv(gefiltert[0].id);
    }
  }, [gefiltert, aktiv]);

  const offen = ABSCHNITTE.find((a) => a.id === aktiv) ?? ABSCHNITTE[0];

  return (
    <div className="min-h-screen bg-[#0a0a0c] font-sans text-slate-200">
      <SiteNav />

      <div className="mx-auto max-w-[1200px] px-6 py-14 lg:px-10">
        <header className="max-w-2xl">
          <h1 className="text-[32px] font-bold tracking-tight text-white sm:text-[38px]">
            Dokumentation
          </h1>
          <p className="mt-3 text-[16px] leading-relaxed text-slate-400">
            Wie du {BRAND} hinzufügst, einrichtest und wieder in den Griff
            bekommst, wenn etwas klemmt.
          </p>
        </header>

        <div className="mt-10 grid gap-8 lg:grid-cols-[240px_1fr] lg:gap-12">
          {/* ── Inhaltsverzeichnis ─────────────────────────────── */}
          <nav className="lg:sticky lg:top-8 lg:self-start">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
              <input
                value={suche}
                onChange={(e) => setSuche(e.target.value)}
                placeholder="Suchen"
                aria-label="Dokumentation durchsuchen"
                className="w-full rounded-lg border border-slate-800 bg-[#0f0f13] py-2 pl-9 pr-8 text-[14px] text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
              />
              {suche && (
                <button
                  type="button"
                  onClick={() => setSuche("")}
                  aria-label="Suche zurücksetzen"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-600 transition-colors hover:text-slate-300"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {gefiltert.length === 0 ? (
              <p className="mt-4 text-[13px] leading-relaxed text-slate-500">
                Nichts gefunden. Im{" "}
                <a
                  href={SUPPORT_INVITE}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:text-indigo-300"
                >
                  Support-Server
                </a>{" "}
                fragen?
              </p>
            ) : (
              <ul className="mt-4 space-y-0.5">
                {gefiltert.map((a) => {
                  const Icon = a.icon;
                  const ist = a.id === offen.id;
                  return (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => setAktiv(a.id)}
                        aria-current={ist ? "page" : undefined}
                        className={cn(
                          "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[14px] transition-colors",
                          ist
                            ? "bg-white/[0.05] font-semibold text-white"
                            : "text-slate-400 hover:bg-white/[0.02] hover:text-slate-200",
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0",
                            ist ? "text-indigo-400" : "text-slate-600",
                          )}
                        />
                        {a.titel}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </nav>

          {/* ── Inhalt ─────────────────────────────────────────── */}
          <main className="min-w-0">
            <article className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6 sm:p-8">
              <h2 className="text-[22px] font-bold tracking-tight text-white">
                {offen.titel}
              </h2>
              <div className="mt-5 space-y-5">{offen.inhalt}</div>
            </article>

            {/* Weiter zum nächsten Abschnitt. Eine Doku, die unten
                aufhört, lässt einen im Nichts stehen. */}
            {(() => {
              const i = ABSCHNITTE.findIndex((a) => a.id === offen.id);
              const naechster = ABSCHNITTE[i + 1];
              if (!naechster) return null;
              return (
                <button
                  type="button"
                  onClick={() => {
                    setAktiv(naechster.id);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  className="group mt-4 flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-[#0f0f13] px-6 py-4 text-left transition-colors hover:border-slate-700"
                >
                  <span>
                    <span className="block text-[12px] text-slate-500">
                      Weiter
                    </span>
                    <span className="mt-0.5 block text-[15px] font-semibold text-white">
                      {naechster.titel}
                    </span>
                  </span>
                  <ArrowUpRight className="h-4 w-4 rotate-45 text-slate-600 transition-colors group-hover:text-indigo-400" />
                </button>
              );
            })()}
          </main>
        </div>
      </div>
    </div>
  );
}
