/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved       ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                     ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

/**
 * Die Startseite.
 *
 * ── Aufbau ──────────────────────────────────────────────────────────
 *
 *   1. Hero: zwei Abzeichen, Überschrift, Text, zwei Knöpfe, rechts
 *      ein Kartenstapel, der von selbst weiterblättert.
 *   2. Funktionen: dreispaltiges Raster mit Icon-Kachel je Karte.
 *   3. Zahlen zum Bot.
 *   4. Stimmen aus der Community.
 *   5. FAQ als Ausklapper.
 *   6. Fußzeile.
 *
 * ── Warum schlicht ──────────────────────────────────────────────────
 *
 * Die alte Fassung hatte 10rem-Überschriften, sechs verschiedene
 * Farbverläufe und Text in zwei Sprachen durcheinander. Hier gibt es
 * genau eine Akzentfarbe (Blurple), einen Grundton (fast schwarz mit
 * einem Hauch Blau) und Ränder in einer einzigen Stärke.
 *
 * ── Warum echte Zahlen ──────────────────────────────────────────────
 *
 * Die Zahlen kommen aus `/api/bot/bot/numbers`, nicht aus dem
 * Quelltext. Eine erfundene Zahl auf der Startseite ist genau die
 * Sorte Angabe, die niemand nachpflegt und die dann jahrelang falsch
 * dasteht. Antwortet die Schnittstelle nicht, steht dort ein Strich.
 */

import React from "react";
import Image from "next/image";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  ArrowRight,
  BarChart4,
  ChevronLeft,
  ChevronRight,
  Brain,
  ChevronDown,
  ClipboardList,
  Crown,
  Database,
  Gift,
  KeyRound,
  Lightbulb,
  Lock,
  Mic,
  Music,
  Palette,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Ticket,
  UserCog,
  Users,
  Zap,
} from "lucide-react";
import { SiteNav, INVITE_URL } from "@/components/site-nav";
import { cn } from "@/lib/utils";
import { normalisiereMarke } from "@/lib/brand";

const HomepageWorldMap = dynamic(
  () => import("@/components/home/homepage-world-map").then((modul) => modul.HomepageWorldMap),
  { ssr: false },
);

const BRAND = normalisiereMarke(process.env.NEXT_PUBLIC_BRAND_NAME);

/**
 * Die Karten im Hero, die von selbst weiterblättern.
 *
 * Dreizehn Stück — eine je grosser Funktionsbereich. Sie zeigen,
 * was der Bot kann, ohne dass jemand scrollen muss; die Punkte
 * darunter erlauben das direkte Anspringen.
 */
const HERO_KARTEN = [
  {
    icon: Lock,
    titel: "Verifizierungs-System",
    text: "Halte Raids fern mit Panel, Captcha und harten Admin-Kontrollen wie Reset und Force-Verify.",
  },
  {
    icon: UserCog,
    titel: "Team-Update",
    text: "Befördern, zurückstufen, verwarnen — Rollen umstecken und ankündigen in einem Zug, mit Unterschriften.",
  },
  {
    icon: Ticket,
    titel: "Ticket-System",
    text: "Kategorien, Rechte, DM-Benachrichtigungen und Transkripte — vollständig im Dashboard eingerichtet.",
  },
  {
    icon: ShieldAlert,
    titel: "Anti-Nuke",
    text: "Grenzen, Warnungen und Gegenmaßnahmen für Massenlöschungen, Massenbann und feindliche Bots.",
  },
  {
    icon: ClipboardList,
    titel: "Bewerbungen",
    text: "Eigene Panels und Fragen, Entscheidungen im Dashboard und automatische Rollen bei Annahme.",
  },
  {
    icon: BarChart4,
    titel: "Level-System",
    text: "XP, Ränge und Belohnungen mit eigenem Rangbild — Aktivität sichtbar machen statt behaupten.",
  },
  {
    icon: Music,
    titel: "Musik",
    text: "Wiedergabe, Playlists und Dauerbetrieb im Sprachkanal — auch nach einem Neustart.",
  },
  {
    icon: ShieldCheck,
    titel: "AutoMod",
    text: "Filter, Strafen und Ausnahmen — greift, bevor jemand aus dem Team überhaupt online ist.",
  },
  {
    icon: Sparkles,
    titel: "Server-Vorlagen",
    text: "Struktur als Vorlage sichern und auf dem nächsten Server in Minuten anwenden.",
  },
  {
    icon: Mic,
    titel: "Join to Create",
    text: "Temporäre Sprachkanäle, die sich selbst aufräumen, wenn der Letzte gegangen ist.",
  },
  {
    icon: Gift,
    titel: "Gewinnspiele",
    text: "Teilnahme per Knopf, Bedingungen nach Rolle oder Level, Auslosung durch den Bot.",
  },
  {
    icon: Users,
    titel: "Teamliste",
    text: "Wer im Team ist, nach Rollen geordnet — hält sich selbst aktuell, ohne dass jemand nachträgt.",
  },
  {
    icon: Brain,
    titel: "KI-Funktionen",
    text: "Antworten, Zusammenfassungen und Übersetzungen direkt im Chat deines Servers.",
  },
  {
    icon: ShieldCheck,
    titel: "Application Firewall",
    text: "Schützt Website, Dashboard und API mit Allowlists, Rate-Limits, Audit-Log und sicherem Einzel-Rollback.",
  },
  {
    icon: Users,
    titel: "User Pull",
    text: "Autorisierte Mitglieder kontrolliert auf den eigenen Server holen — verschlüsselt, Premium und owner-only.",
  },
  {
    icon: Zap,
    titel: "Custom Commands",
    text: "Eigene Slash-, Präfix- und Textbefehle mit Antworten, Komponenten und individuellen Auslösern.",
  },
  {
    icon: Database,
    titel: "Server-Backups",
    text: "Rollen, Kanäle, Rechte und Dashboard-Konfigurationen sichern und gezielt wiederherstellen.",
  },
  {
    icon: BarChart4,
    titel: "Server-Statistiken",
    text: "Boosts, Rollen, Kanäle und Online-Aktivität übersichtlich und aktuell im Dashboard verfolgen.",
  },
  {
    icon: Sparkles,
    titel: "Speedrun & Vorlagen",
    text: "Komplette Serverstrukturen geführt aufbauen, sichern, vergleichen und erneut verwenden.",
  },
  {
    icon: Mic,
    titel: "Support-Warteraum",
    text: "Sprachbasierte Support-Warteschlangen mit Teamsteuerung, Reihenfolge und automatischer Bereinigung.",
  },
  {
    icon: Palette,
    titel: "Server-Design",
    text: "Bot-Name, Avatar und Banner passend zum Server gestalten und zentral im Dashboard verwalten.",
  },
];

const HERO_META: Record<string, { wert: string; label: string }> = {
  "Verifizierungs-System": { wert: "SAFE", label: "RAID-SCHUTZ" },
  "Team-Update": { wert: "1×", label: "WORKFLOW" },
  "Ticket-System": { wert: "100%", label: "ANPASSBAR" },
  "Anti-Nuke": { wert: "24/7", label: "ÜBERWACHUNG" },
  Bewerbungen: { wert: "FLOW", label: "ENTSCHEIDUNGEN" },
  "Level-System": { wert: "XP", label: "ENGAGEMENT" },
  Musik: { wert: "HQ", label: "AUDIO" },
  AutoMod: { wert: "99.9%", label: "FILTER" },
  "Server-Vorlagen": { wert: "1:1", label: "STRUKTUR" },
  "Join to Create": { wert: "LIVE", label: "VOICE" },
  Gewinnspiele: { wert: "FAIR", label: "AUSLOSUNG" },
  Teamliste: { wert: "SYNC", label: "ROLLEN" },
  "KI-Funktionen": { wert: "AI", label: "ASSISTENZ" },
  "Application Firewall": { wert: "ZERO", label: "FALSE POSITIVES" },
  "User Pull": { wert: "AES", label: "VERSCHLÜSSELT" },
  "Custom Commands": { wert: "20+", label: "EIGENE FLOWS" },
  "Server-Backups": { wert: "10×", label: "SICHERUNGEN" },
  "Server-Statistiken": { wert: "LIVE", label: "SERVERDATEN" },
  "Speedrun & Vorlagen": { wert: "FAST", label: "SETUP" },
  "Support-Warteraum": { wert: "QUEUE", label: "SUPPORT" },
  "Server-Design": { wert: "100%", label: "DEIN LOOK" },
};

const HERO_FARBEN = [
  { icon: "bg-cyan-500", text: "text-cyan-400" },
  { icon: "bg-violet-500", text: "text-violet-400" },
  { icon: "bg-sky-500", text: "text-sky-400" },
  { icon: "bg-emerald-500", text: "text-emerald-400" },
  { icon: "bg-fuchsia-500", text: "text-fuchsia-400" },
  { icon: "bg-orange-500", text: "text-orange-400" },
];

/** Alle nutzerseitigen Module, gruppiert wie im Dashboard. */
const FUNKTIONS_GRUPPEN = [
  {
    titel: "Design & Daten",
    text: "Aussehen, Sicherungen und messbare Serverdaten.",
    icon: Palette,
    module: [
      [
        "Server-Design",
        "Name, Profilbild und Banner pro Server; diese Anpassung benötigt Premium.",
      ],
      [
        "Backups",
        "Kanäle, Rollen, Rechte und Dashboard-Einstellungen sichern und wiederherstellen.",
      ],
      [
        "Server-Statistiken",
        "Boosts anzeigen; Rollen, Kanäle und Online-Nutzer sind Premium-Statistiken.",
      ],
    ],
  },
  {
    titel: "Schutz & Sicherheit",
    text: "Automatische Regeln und Werkzeuge für kritische Situationen.",
    icon: ShieldCheck,
    module: [
      [
        "Anti-Nuke",
        "Grenzen und Gegenmaßnahmen gegen massenhafte gefährliche Aktionen.",
      ],
      [
        "AutoMod",
        "Spam, Einladungen, Links, Caps, Massen-Erwähnungen und Emoji-Spam filtern.",
      ],
      [
        "Honeypot",
        "Ein sichtbarer Köderkanal erkennt automatisierte oder unerlaubte Zugriffe.",
      ],
      [
        "Verifizierung",
        "Mitglieder über ein konfigurierbares Verifizierungsverfahren freischalten.",
      ],
      [
        "Notfallmodus",
        "Voreingestellte Schutzmaßnahmen in einer akuten Situation auslösen.",
      ],
      [
        "Jail",
        "Mitglieder kontrolliert einschränken und später wieder freigeben.",
      ],
      [
        "Nachtmodus",
        "Kanäle nach Zeitplan beschränken; die Zeitsteuerung läuft automatisch.",
      ],
    ],
  },
  {
    titel: "Mitglieder & Community",
    text: "Vom ersten Beitritt bis zu Rollen, Levels und Bewerbungen.",
    icon: Users,
    module: [
      [
        "Begrüßung",
        "Willkommensnachrichten und Bilder für neue Mitglieder konfigurieren.",
      ],
      [
        "Bewerbungen",
        "Eigene Panels, Fragen und Entscheidungen für Server-Bewerbungen verwalten.",
      ],
      [
        "Abschied",
        "Eine Nachricht senden, wenn ein Mitglied den Server verlässt.",
      ],
      [
        "Beitritts-DM",
        "Neue Mitglieder mit einer privaten Nachricht begrüßen.",
      ],
      ["Auto-Rolle", "Beim Beitritt automatisch festgelegte Rollen vergeben."],
      [
        "Reaktions-Rollen",
        "Mitglieder wählen Rollen über Reaktionen oder Komponenten.",
      ],
      [
        "Eigene Rollen",
        "Persönlich verwaltbare Rollen nach deinen Serverregeln anbieten.",
      ],
      [
        "Vanity-Rollen",
        "Rollen anhand eines eingestellten Vanity- oder Einladungstextes vergeben.",
      ],
      [
        "Nickname",
        "Regeln für automatische oder einheitliche Anzeigenamen festlegen.",
      ],
      [
        "Level-System",
        "XP, Ranglisten, Rollenbelohnungen und Levelkarten aus echter Aktivität.",
      ],
    ],
  },
  {
    titel: "Interaktion & Automatisierung",
    text: "Wiederkehrende Aktionen und Community-Aktivitäten.",
    icon: Zap,
    module: [
      [
        "Giveaways",
        "Gewinnspiele erstellen, Bedingungen prüfen und Gewinner auslosen.",
      ],
      ["Counting", "Einen gemeinsamen Zählkanal mit Regelprüfung betreiben."],
      [
        "Booster",
        "Server-Boosts erkennen und darauf mit Rollen oder Nachrichten reagieren.",
      ],
      [
        "Benachrichtigungen",
        "Neue Inhalte und festgelegte Ereignisse in Discord ankündigen.",
      ],
      [
        "Auto-Reaktion",
        "Auf passende Nachrichten automatisch mit Emojis reagieren.",
      ],
      [
        "Autoresponder",
        "Auf festgelegte Begriffe mit gespeicherten Antworten reagieren.",
      ],
      [
        "Custom Commands",
        "Eigene Slash-, Präfix- und Textauslöser erstellen: Free bis 3, Premium bis 20.",
      ],
      [
        "Anonymer Chat · Beta",
        "Anonyme Nachrichten mit eigenem geschütztem Protokollsystem ermöglichen.",
      ],
    ],
  },
  {
    titel: "Sprache & Audio",
    text: "Sprachkanäle und Musikwiedergabe verwalten.",
    icon: Mic,
    module: [
      [
        "Musik",
        "Titel und Warteschlangen in einem Discord-Sprachkanal wiedergeben.",
      ],
      [
        "Join to Create",
        "Temporäre Sprachkanäle beim Beitritt erstellen und automatisch aufräumen.",
      ],
      [
        "Sprach-Rolle",
        "Beim Aufenthalt in einem Sprachkanal eine festgelegte Rolle vergeben.",
      ],
    ],
  },
  {
    titel: "Nachrichten & Werkzeuge",
    text: "Support, feste Inhalte, Einladungen und Zugriffsregeln.",
    icon: Ticket,
    module: [
      [
        "Tickets",
        "Support-Panels, Kategorien, Teamrechte, Hinweise und Transkripte konfigurieren.",
      ],
      [
        "Eigene Nachricht",
        "Nachrichten und Discord-Komponenten im Dashboard erstellen und senden.",
      ],
      [
        "Sticky-Nachricht",
        "Eine festgelegte Nachricht am unteren Ende eines Kanals halten.",
      ],
      ["Einladungen", "Einladungen und die zugehörige Bestenliste auswerten."],
      [
        "Einladungs-Log",
        "Beitritte und verwendete Einladungen nachvollziehbar protokollieren.",
      ],
      [
        "No Prefix",
        "Ausgewählten Rollen oder Personen Befehle ohne Präfix erlauben.",
      ],
    ],
  },
  {
    titel: "Vorlagen & Verwaltung",
    text: "Serveraufbau, Teamarbeit, Protokolle und delegierter Zugang.",
    icon: Database,
    module: [
      [
        "Speedrun · Premium",
        "Einen Server in einem geführten Durchgang aus einer Vorlage aufsetzen.",
      ],
      [
        "Vorlagen-Upload · Experimentell",
        "Eine vorhandene Serverstruktur für Vorlagen erfassen.",
      ],
      [
        "Vorlagen-Community · Experimentell",
        "Freigegebene Community-Vorlagen durchsuchen und verwenden.",
      ],
      [
        "Teamliste",
        "Mitglieder des Serverteams nach Rollen geordnet anzeigen.",
      ],
      [
        "Team-Update · Beta",
        "Beförderungen, Rückstufungen und Verwarnungen dokumentiert durchführen.",
      ],
      [
        "Logs",
        "Löschungen, Bearbeitungen und andere Serverereignisse protokollieren.",
      ],
      ["Bot-Logs", "Vom Bot erfasste Modulereignisse im Dashboard prüfen."],
      [
        "Server-Werkzeuge",
        "Administrative Schnellaktionen für den eigenen Server bündeln.",
      ],
      [
        "Dashboard Access",
        "Der Serverinhaber kann ausgewählten Personen und Rollen Dashboard-Zugang geben.",
      ],
      [
        "Support-Warteraum · Beta",
        "Eine geordnete Warteschlange in Sprachkanälen betreiben.",
      ],
    ],
  },
] as const;

const MODUL_ANZAHL = FUNKTIONS_GRUPPEN.reduce(
  (sum, gruppe) => sum + gruppe.module.length,
  0,
);

const FAQ = [
  {
    frage: `Wie füge ich ${BRAND} zu meinem Server hinzu?`,
    antwort:
      "Klicke auf „Bot hinzufügen“, wähle bei Discord einen Server aus und bestätige die benötigten Rechte. Danach meldest du dich im Dashboard an, wählst den Server und richtest nur die Module ein, die du verwenden möchtest.",
  },
  {
    frage: `Ist ${BRAND} kostenlos nutzbar?`,
    antwort:
      "Ja, die Grundfunktionen sind kostenlos. Einige Erweiterungen sind Premium vorbehalten, darunter das eigene Bot-Aussehen pro Server, Speedrun, Premium-Vorlagen, zusätzliche Backup-Funktionen sowie erweiterte Statistiken und höhere Limits bei Custom Commands.",
  },
  {
    frage: "Wie bekomme ich Premium?",
    antwort:
      "Im Dashboard kannst du eine Kaufanfrage für 30, 90 oder 365 Tage senden. Nach der manuellen Bestätigung stehen deinem Discord-Konto drei feste Serverplätze zur Verfügung. Eine bereits laufende Premiumzeit kann nicht durch eine weitere Kaufanfrage überlagert werden.",
  },
  {
    frage: "Welche Befehlsarten unterstützt der Bot?",
    antwort:
      "Der Bot besitzt klassische Präfixbefehle und echte Discord-Slash-Commands. Bei eigenen Custom Commands lassen sich Slash-, Präfix- und Textauslöser konfigurieren. Welche Befehle tatsächlich geladen sind, zeigt die öffentliche Befehlsseite.",
  },
  {
    frage: "Wer darf einen Server im Dashboard verwalten?",
    antwort:
      "Discord-Serverinhaber und Personen mit den jeweils erforderlichen Serverrechten können die normalen Bereiche öffnen. Delegierten Dashboard-Zugang für weitere Nutzer oder Rollen darf ausschließlich der tatsächliche Serverinhaber einrichten.",
  },
  {
    frage: "Wie melde ich einen Fehler oder erreiche den Support?",
    antwort:
      "Nutze den verlinkten Discord-Support-Server und eröffne dort ein Ticket. Auf der Statusseite siehst du unabhängig davon, ob der Bot erreichbar ist, ob eine Wartung läuft und welche Zeiträume tatsächlich gemessen wurden.",
  },
  {
    frage: `Unterstützt ${BRAND} Deutsch und Englisch?`,
    antwort:
      "Das Dashboard kann auf Deutsch oder Englisch angezeigt werden. Die Auswahl wird am Konto gespeichert. Einzelne ältere oder von Serveradministratoren selbst geschriebene Bot-Texte können weiterhin nur in der Sprache vorliegen, in der sie eingerichtet wurden.",
  },
  {
    frage: "Welche Daten zeigt das Konto-Dashboard?",
    antwort:
      "Es zeigt gespeicherte Kontokategorien, Datenschutzanträge, Sitzungen, Discord-Berechtigungen und gemessene XP- sowie Nachrichtenaktivität. Tageswerte werden erst seit Einführung der Messung erfasst; frühere Werte werden nicht rückwirkend erfunden.",
  },
];

function ScrollReveal({
  children,
  von = "links",
  className,
}: {
  children: React.ReactNode;
  von?: "links" | "rechts";
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [sichtbar, setSichtbar] = React.useState(false);

  React.useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        // Nicht nur beim ersten Besuch abspielen: Sobald ein Bereich den
        // Bildschirm verlässt, wird er zurückgesetzt. Beim erneuten Hoch-
        // oder Herunterscrollen kommt er wieder von seiner Seite herein.
        setSichtbar(entry.isIntersecting);
      },
      { threshold: 0.14, rootMargin: "0px 0px -7% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn(
        "scroll-reveal transition-[opacity,transform,filter] duration-700 ease-out motion-reduce:transform-none motion-reduce:transition-none",
        sichtbar
          ? "translate-x-0 opacity-100 blur-0"
          : von === "links"
            ? "-translate-x-16 opacity-0 blur-[2px]"
            : "translate-x-16 opacity-0 blur-[2px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Ein einzelner FAQ-Ausklapper. */
function FaqZeile({ frage, antwort }: { frage: string; antwort: string }) {
  const [offen, setOffen] = React.useState(false);
  return (
    <div className="border-b border-slate-800">
      <button
        type="button"
        onClick={() => setOffen((o) => !o)}
        aria-expanded={offen}
        className="w-full flex items-center justify-between gap-6 py-6 text-left"
      >
        <span className="text-[17px] font-semibold text-white">{frage}</span>
        <ChevronDown
          className={cn(
            "h-5 w-5 shrink-0 text-indigo-400 transition-transform duration-200",
            offen && "rotate-180",
          )}
        />
      </button>
      {offen && (
        <p className="pb-6 -mt-1 text-[15px] leading-relaxed text-slate-400 max-w-3xl">
          {antwort}
        </p>
      )}
    </div>
  );
}

export function LegacyHomepage() {
  const [karte, setKarte] = React.useState(0);
  const [zahlen, setZahlen] = React.useState<any>(null);
  const [carouselPause, setCarouselPause] = React.useState(false);
  const [offeneGruppe, setOffeneGruppe] = React.useState<number | null>(null);
  const [alleFaqSichtbar, setAlleFaqSichtbar] = React.useState(false);
  const touchStart = React.useRef<number | null>(null);

  // Schnell genug, damit alle Module sichtbar werden. Beim Überfahren,
  // Fokussieren oder Wischen pausiert der Wechsel automatisch.
  React.useEffect(() => {
    // Auf kleinen Displays bleibt die Bühne ruhig. Die Karten lassen sich
    // weiterhin antippen und wischen, verursachen aber keine Dauer-Updates.
    if (carouselPause || window.matchMedia("(max-width: 639px)").matches) return;
    const t = setInterval(
      () => setKarte((k) => (k + 1) % HERO_KARTEN.length),
      2600,
    );
    return () => clearInterval(t);
  }, [carouselPause]);

  const wechsel = React.useCallback((richtung: number) => {
    setKarte((aktuell) => (aktuell + richtung + HERO_KARTEN.length) % HERO_KARTEN.length);
  }, []);

  // Alle Zahlen aus dem laufenden Bot.
  //
  // Vorher standen Module, Befehle und Dashboard-Reiter fest im
  // Quelltext -- und waren falsch: 608 Befehle behauptet, 623
  // gezaehlt. Eine Zahl, die niemand nachpflegt, steht irgendwann
  // jahrelang falsch da. Antwortet der Bot nicht, bleibt ein Strich.
  React.useEffect(() => {
    let lebt = true;
    fetch("/api/bot/bot/numbers")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (lebt && d) setZahlen(d);
      })
      .catch(() => {});
    return () => {
      lebt = false;
    };
  }, []);

  /** Eine Zahl, oder ein Strich, solange sie nicht da ist. */
  const zeig = (wert: any) =>
    typeof wert === "number" && wert > 0 ? wert.toLocaleString("de-DE") : "—";
  const server = zahlen?.guilds > 0 ? zeig(zahlen.guilds) : null;

  return (
    <div className="min-h-screen overflow-x-clip bg-[#050712] bg-[radial-gradient(circle_at_10%_35%,rgba(79,70,229,.10),transparent_26%),radial-gradient(circle_at_90%_68%,rgba(14,165,233,.08),transparent_28%)] text-slate-200 selection:bg-indigo-500/30">
      <SiteNav />

      {/* ── Immersiver Hero ───────────────────────────────── */}
      <header className="px-3 pt-4 sm:px-6 lg:px-10">
        <div
          className="university-universe relative mx-auto min-h-[680px] max-w-[1500px] overflow-hidden rounded-[24px] border border-white/10 bg-[#050914] bg-cover bg-center shadow-[0_24px_70px_rgba(0,0,0,.45)] sm:min-h-[760px] sm:rounded-[28px] sm:shadow-[0_35px_100px_rgba(0,0,0,.55)]"
          style={{ backgroundImage: "url('/home-university-universe.jpg')" }}
        >
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(3,7,14,.32),rgba(3,7,14,.08)_40%,rgba(3,7,14,.88)_100%)]" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_70%_42%,transparent_0%,rgba(3,7,14,.2)_58%,rgba(3,7,14,.55)_100%)]" />

          <div className="relative flex min-h-[680px] flex-col p-4 sm:min-h-[760px] sm:p-7 lg:p-9">
            <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
              <span className="university-comet university-comet-one" />
              <span className="university-comet university-comet-two" />
              <span className="university-comet university-comet-three" />
            </div>
            <div className="absolute left-5 top-5 z-10 flex items-center gap-3 rounded-2xl border border-white/15 bg-black/25 p-2.5 pr-4 shadow-2xl backdrop-blur-xl sm:left-8 sm:top-8">
              <span className="grid h-11 w-11 place-items-center overflow-hidden rounded-xl border border-white/15 bg-black/45">
                <Image src="/icon-192.png" alt="University Bot Logo" width={44} height={44} className="h-11 w-11 object-cover" priority />
              </span>
              <div><p className="text-sm font-bold text-white">University Bot</p><p className="text-[10px] uppercase tracking-[.16em] text-white/45">Discord neu gedacht</p></div>
            </div>

            <div className="pointer-events-none absolute inset-x-0 top-32 overflow-hidden px-3 text-center sm:top-24">
              <p className="select-none whitespace-nowrap text-[16vw] font-black leading-none tracking-[-.08em] text-white/[.17] sm:text-[14vw] lg:text-[clamp(95px,11vw,168px)]">
                UNIVERSITY
              </p>
            </div>

            <div className="relative mt-auto grid items-end gap-5 pb-2 pt-40 sm:gap-8 sm:pt-52 lg:grid-cols-[1.1fr_.9fr] lg:gap-14 lg:pt-64">
              <div>
                <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-black/25 px-3 py-1.5 text-xs font-medium text-white/80 backdrop-blur-lg">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_12px_#34d399]" />
                  {server ? `Live auf ${server} Servern` : "Live auf Discord"}
                </div>
                <h1 className="max-w-2xl text-[38px] font-semibold leading-[1.03] tracking-[-.04em] text-white sm:text-[52px] lg:text-[64px]">
                  Ein Ort für deinen ganzen Discord-Server.
                </h1>
                <p className="mt-5 max-w-xl text-sm leading-6 text-white/65 sm:text-base">
                  Moderation, Tickets, Bewerbungen und Verifizierung zentral steuern — ohne Konfigurationsdateien und ohne erfundene Versprechen.
                </p>

                <div className="mt-7 flex flex-wrap items-center gap-3">
                  <a href={INVITE_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-bold text-slate-950 transition hover:-translate-y-0.5 hover:bg-indigo-100">
                    Jetzt hinzufügen <ArrowRight className="h-4 w-4" />
                  </a>
                  <Link href="#funktionen" className="rounded-xl border border-white/15 bg-black/20 px-5 py-3 text-sm font-semibold text-white backdrop-blur-xl transition hover:bg-white/10">Module ansehen</Link>
                </div>

                <dl className="mt-9 grid max-w-xl grid-cols-3 gap-3 border-t border-white/15 pt-5">
                  <div><dd className="text-2xl font-semibold tabular-nums text-white sm:text-3xl">{server ?? "—"}</dd><dt className="mt-1 text-[10px] uppercase tracking-[.12em] text-white/45">Server</dt></div>
                  <div><dd className="text-2xl font-semibold tabular-nums text-white sm:text-3xl">{zeig(zahlen?.commands)}</dd><dt className="mt-1 text-[10px] uppercase tracking-[.12em] text-white/45">Befehle</dt></div>
                  <div><dd className="text-2xl font-semibold tabular-nums text-white sm:text-3xl">{zeig(zahlen?.modules)}</dd><dt className="mt-1 text-[10px] uppercase tracking-[.12em] text-white/45">Module</dt></div>
                </dl>
              </div>

              <div
                className="relative min-h-[215px] sm:min-h-[275px]"
                onMouseEnter={() => setCarouselPause(true)}
                onMouseLeave={() => setCarouselPause(false)}
                onTouchStart={(event) => { touchStart.current = event.touches[0]?.clientX ?? null; setCarouselPause(true); }}
                onTouchEnd={(event) => {
                  const start = touchStart.current;
                  const ende = event.changedTouches[0]?.clientX;
                  if (start !== null && typeof ende === "number" && Math.abs(ende - start) > 42) wechsel(ende < start ? 1 : -1);
                  touchStart.current = null;
                  window.setTimeout(() => setCarouselPause(false), 900);
                }}
              >
                {HERO_KARTEN.map((eintrag, index) => {
                  let versatz = (index - karte + HERO_KARTEN.length) % HERO_KARTEN.length;
                  if (versatz > HERO_KARTEN.length / 2) versatz -= HERO_KARTEN.length;
                  if (Math.abs(versatz) > 1) return null;
                  const Icon = eintrag.icon;
                  const farbe = HERO_FARBEN[index % HERO_FARBEN.length];
                  const meta = HERO_META[eintrag.titel] || { wert: "LIVE", label: "MODUL" };
                  return (
                    <button
                      key={eintrag.titel}
                      type="button"
                      onClick={() => setKarte(index)}
                      aria-label={`${eintrag.titel} anzeigen`}
                      className={cn(
                        "absolute bottom-9 right-0 min-h-[190px] w-[94%] overflow-hidden rounded-2xl border border-white/25 bg-[#070b16]/75 p-4 text-left shadow-[0_16px_45px_rgba(0,0,0,.45)] ring-1 ring-white/5 backdrop-blur-2xl transition-[transform,opacity,filter] duration-500 sm:bottom-10 sm:min-h-[235px] sm:w-[86%] sm:rounded-3xl sm:p-6 sm:duration-700",
                        versatz === 0 ? "z-20 opacity-100" : "z-10 opacity-55 blur-[1.5px]",
                      )}
                      style={{ transform: `translateX(${versatz * -18}%) translateY(${Math.abs(versatz) * -12}px) scale(${versatz === 0 ? 1 : .9})` }}
                    >
                      <span className={cn("absolute inset-x-0 top-0 h-0.5 opacity-90", farbe.icon)} />
                      <div className="absolute -right-16 -top-16 h-40 w-40 rounded-full bg-white/[.04] blur-2xl" />
                      <div className="relative flex items-start gap-4">
                        <span className={cn("grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white shadow-lg", farbe.icon)}><Icon className="h-6 w-6" /></span>
                        <div className="min-w-0 flex-1">
                          <p className="text-[10px] font-bold uppercase tracking-[.15em] text-white/45">University Modul</p>
                          <h2 className="mt-1 text-xl font-bold text-white">{eintrag.titel}</h2>
                          <p className="mt-2 text-xs leading-5 text-white/70">{eintrag.text}</p>
                          <div className="mt-3 flex flex-wrap gap-1.5"><span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span><span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-white/55">Dashboard</span></div>
                        </div>
                      </div>
                      <div className="relative mt-5 flex items-end justify-between border-t border-white/10 pt-4">
                        <div><strong className={cn("text-3xl font-black", farbe.text)}>{meta.wert}</strong><span className="ml-2 text-[9px] uppercase tracking-wider text-white/40">{meta.label}</span></div>
                        <span className="text-[10px] tabular-nums text-white/40">{String(index + 1).padStart(2, "0")}/{HERO_KARTEN.length}</span>
                      </div>
                    </button>
                  );
                })}

                <div className="absolute bottom-0 right-0 z-30 flex items-center gap-2">
                  <button type="button" onClick={() => wechsel(-1)} aria-label="Vorheriges Modul" className="grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-black/30 text-white/70 backdrop-blur-xl hover:bg-white/10 hover:text-white"><ChevronLeft className="h-4 w-4" /></button>
                  <div className="flex gap-1.5">{HERO_KARTEN.map((eintrag, index) => <button key={eintrag.titel} type="button" aria-label={eintrag.titel} onClick={() => setKarte(index)} className={cn("h-1.5 rounded-full transition-all", index === karte ? "w-5 bg-white" : "w-1.5 bg-white/30")} />)}</div>
                  <button type="button" onClick={() => wechsel(1)} aria-label="Nächstes Modul" className="grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-black/30 text-white/70 backdrop-blur-xl hover:bg-white/10 hover:text-white"><ChevronRight className="h-4 w-4" /></button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="px-4 py-8 sm:px-6">
        <ScrollReveal von="rechts" className="home-glass mx-auto max-w-6xl rounded-3xl p-6 sm:flex sm:items-center sm:justify-between sm:gap-8 sm:p-8">
          <div className="flex gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-indigo-400/20 bg-indigo-400/10 text-indigo-300 shadow-[inset_0_1px_rgba(255,255,255,.08)]">
              <Lightbulb className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Hilf uns, University Bot besser zu machen</h2>
              <p className="mt-1 text-sm font-medium text-indigo-400">Community Ideen</p>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Reiche deinen Vorschlag ein, diskutiere mit der Community und erhalte bei einer ausgezeichneten Idee 3 Tage Premium für einen Server deiner Wahl.</p>
            </div>
          </div>
          <div className="mt-5 flex shrink-0 flex-wrap gap-3 sm:mt-0">
            <span className="inline-flex items-center gap-2 px-1 py-3 text-sm font-semibold text-slate-300"><Gift className="h-4 w-4 text-indigo-400"/>3 Tage Premium</span>
            <Link href="/ideas/new" className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white hover:bg-indigo-500">Idee einreichen <ArrowRight className="h-4 w-4"/></Link>
          </div>
        </ScrollReveal>
      </section>

      <ScrollReveal von="links">
        <HomepageWorldMap />
      </ScrollReveal>

      {/* ── Funktionen ────────────────────────────────────── */}
      {/*
          Was hier anders ist:

            * **Kein Abzeichen „Funktionen" über der Überschrift
              „Funktionen".** Zweimal dasselbe Wort übereinander, das
              obere in einer Pille -- eine Bauform, die auf jeder
              Landingpage steht und nichts hinzufügt.
            * **Kein Werbesatz.** „Alles was du brauchst" ist eine
              Behauptung über fremde Bedürfnisse. Die Überschrift sagt
              jetzt, was die Liste ist.
            * **Keine 34 gleich lauten Kacheln.** Alle trugen ein
              blaues Quadrat mit weißem Symbol; nebeneinander ergaben
              sie eine Wand aus Blau, in der kein Eintrag heraussticht.
              Das Symbol steht jetzt ruhig neben dem Titel. */}
      <section id="funktionen" className="px-4 py-12 sm:px-6 sm:py-20 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <ScrollReveal von="links" className="max-w-2xl">
            <h2 className="text-[28px] font-bold tracking-tight text-white sm:text-[32px]">
              Alle Module im Überblick
            </h2>
            <p className="mt-3 text-[16px] leading-relaxed text-slate-400">
              {MODUL_ANZAHL} Bereiche aus dem aktuellen Dashboard — nach Aufgabe
              gruppiert und mit ihren tatsächlichen Grenzen beschrieben.
            </p>
          </ScrollReveal>

          <div className="mt-7 space-y-3 sm:mt-10 sm:space-y-5">
            {FUNKTIONS_GRUPPEN.map((gruppe, index) => {
              const GruppenIcon = gruppe.icon;
              return (
                <ScrollReveal key={gruppe.titel} von={index % 2 === 0 ? "links" : "rechts"}>
                <article className="home-glass overflow-hidden rounded-2xl px-4 sm:rounded-3xl sm:px-6">
                  <div className="flex items-center gap-3 py-4 sm:py-6">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-400/20 bg-indigo-400/10 shadow-[inset_0_1px_rgba(255,255,255,.08)]">
                      <GruppenIcon className="h-5 w-5 text-indigo-400" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-[15px] font-bold text-white sm:text-[17px]">
                        {gruppe.titel}
                      </h3>
                      <p className="mt-0.5 line-clamp-1 text-[12px] text-slate-500 sm:line-clamp-none sm:text-[13px]">
                        {gruppe.text}
                      </p>
                    </div>
                    <span className="hidden text-xs tabular-nums text-slate-600 sm:block sm:ml-auto">
                      {gruppe.module.length} Module
                    </span>
                    <button
                      type="button"
                      aria-expanded={offeneGruppe === index}
                      aria-controls={`mobile-module-${index}`}
                      onClick={() => setOffeneGruppe((aktuell) => aktuell === index ? null : index)}
                      className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-indigo-300 sm:hidden"
                    >
                      <span className="sr-only">{gruppe.titel} {offeneGruppe === index ? "schließen" : "öffnen"}</span>
                      <ChevronDown className={cn("h-5 w-5 transition-transform", offeneGruppe === index && "rotate-180")} />
                    </button>
                  </div>
                  <div id={`mobile-module-${index}`} className={cn("gap-x-10 sm:grid sm:grid-cols-2 lg:grid-cols-3", offeneGruppe === index ? "grid" : "hidden")}>
                    {gruppe.module.map(([titel, text]) => (
                      <div
                        key={titel}
                        className="border-t border-slate-800 py-5 transition-colors hover:border-slate-600"
                      >
                        <div className="flex items-center gap-2">
                          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
                          <h4 className="text-[14px] font-semibold text-white">
                            {titel}
                          </h4>
                        </div>
                        <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
                          {text}
                        </p>
                      </div>
                    ))}
                  </div>
                </article>
                </ScrollReveal>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-4 py-10 sm:px-6 sm:py-14 lg:px-12 xl:px-20">
        <ScrollReveal von="rechts" className="home-glass relative mx-auto max-w-[1400px] overflow-hidden rounded-3xl p-6 sm:p-9 lg:p-12">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-amber-400/10 blur-3xl" />
          <div className="relative grid gap-9 lg:grid-cols-[1.05fr_.95fr] lg:items-center">
            <div>
              <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[.14em] text-amber-300"><Crown className="h-3.5 w-3.5" />Premium · drei feste Serverplätze</span>
              <h2 className="mt-5 max-w-2xl text-3xl font-black tracking-tight text-white sm:text-5xl">Premium genau auf deinen wichtigsten Servern.</h2>
              <p className="mt-4 max-w-2xl text-[15px] leading-7 text-slate-400">Sende eine Kaufanfrage für 30, 90 oder 365 Tage. Nach der Bestätigung verteilst du drei feste Serverplätze – mit Server-Design, erweiterten Backups, Server-Stats, User Pull und weiteren Premiumbereichen.</p>
              <div className="mt-7 flex flex-wrap gap-3"><Link href="/dashboard/premium" className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-5 py-3 text-sm font-black text-black hover:bg-amber-300"><Sparkles className="h-4 w-4" />Kaufanfrage starten</Link><Link href="/premium" className="inline-flex items-center gap-2 rounded-xl border border-amber-400/25 px-5 py-3 text-sm font-semibold text-amber-200 hover:bg-amber-400/10">Alles über Premium<ArrowRight className="h-4 w-4" /></Link></div>
              <dl className="mt-8 flex max-w-xl flex-wrap gap-x-10 gap-y-5 border-t border-slate-800 pt-6"><div><dd className="text-xl font-black text-white">3</dd><dt className="text-[11px] text-slate-500">feste Plätze</dt></div><div><dd className="text-xl font-black text-white">365</dd><dt className="text-[11px] text-slate-500">Tage maximal</dt></div><div><dd className="text-xl font-black text-white">Keine</dd><dt className="text-[11px] text-slate-500">Löschung bei Ablauf</dt></div></dl>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:gap-3">{[[Palette,"Eigenes Bot-Aussehen","Name, Avatar und Banner"],[Database,"Erweiterte Backups","10 Plätze und Automatik"],[BarChart4,"Server-Stats","Live gepflegte Statistikkanäle"],[Zap,"User Pull","Vollständig Premium und owner-only"],[KeyRound,"Custom Commands","Bis zu 20 eigene Befehle"],[Server,"Sicherer Ablauf","Einfrieren oder deaktivieren"]].map(([Icon,title,text])=>{const PremiumIcon=Icon as React.ElementType;return <div key={String(title)} className="rounded-2xl border border-white/10 bg-white/[.035] p-3 shadow-[inset_0_1px_rgba(255,255,255,.06)] backdrop-blur-xl transition hover:bg-white/[.06] sm:p-4"><PremiumIcon className="h-5 w-5 text-amber-400"/><p className="mt-3 text-sm font-black text-white">{title as string}</p><p className="mt-1 text-xs text-slate-500">{text as string}</p></div>})}</div>
          </div>
        </ScrollReveal>
      </section>

      {/* ── Zahlen ────────────────────────────────────────── */}
      {/*
          Vorher: vier große Kästen, mittig, unter der Überschrift
          „In Zahlen". Solange der Bot nicht antwortet, standen dort
          vier Striche in 34px -- eine leere Bühne für nichts.

          Jetzt eine schlichte Zeile. Sind die Zahlen da, liest man
          sie; sind sie es nicht, fällt eine Zeile weniger auf als
          eine Kachelwand. Die Aussage „direkt aus dem laufenden Bot"
          bleibt, weil sie den Unterschied zu erfundenen Zahlen
          macht. */}
      <section className="px-4 py-10 sm:px-6 sm:py-16 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <ScrollReveal von="links" className="home-glass flex flex-wrap items-end justify-between gap-x-10 gap-y-8 rounded-3xl p-6 sm:p-8">
            {[
              { wert: server ?? "—", label: "Server" },
              { wert: zeig(zahlen?.modules), label: "Module" },
              { wert: zeig(zahlen?.commands), label: "Befehle" },
              { wert: zeig(zahlen?.users), label: "Mitglieder" },
            ].map((s) => (
              <div key={s.label}>
                <div className="text-[26px] font-bold leading-none tabular-nums text-white">
                  {s.wert}
                </div>
                <div className="mt-1.5 text-[13px] text-slate-500">
                  {s.label}
                </div>
              </div>
            ))}

            <p className="text-[13px] text-slate-500">
              Live aus dem Bot ·{" "}
              <Link
                href="/status"
                className="text-slate-400 underline decoration-slate-700 underline-offset-4 hover:text-white"
              >
                Status
              </Link>
            </p>
          </ScrollReveal>
        </div>
      </section>

      {/* ── Wie es läuft ──────────────────────────────────── */}
      {/*
          Hier standen „Community-Stimmen": drei Zitate unter der
          Überschrift „Warum Teams University Bot nutzen", eingeleitet
          mit „Erfahrungen aus aktiven Discord-Communities".

          Zwei davon stammten von Fufi und Vexo — den beiden
          Entwicklern (siehe app/team/page.tsx). Das dritte von einem
          „Uni-Server", den es so nicht gibt. Eigenlob als Empfehlung
          zu verkleiden ist genau die Sorte Fake, die eine Seite billig
          wirken lässt, und es ist schlicht nicht wahr.

          An die Stelle tritt etwas, das nachprüfbar ist: die drei
          Schritte bis zum laufenden Bot. Sobald es echte Stimmen
          gibt, können sie hier stehen. */}
      <section className="px-4 py-12 sm:px-6 sm:py-20 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,360px)_1fr] lg:gap-20">
            <ScrollReveal von="links">
              <h2 className="text-[28px] font-bold leading-tight tracking-tight text-white sm:text-[32px]">
                In drei Schritten eingerichtet
              </h2>
              <p className="mt-4 max-w-sm text-[16px] leading-relaxed text-slate-400">
                Kein Handbuch, keine Konfigurationsdatei. Was der Bot können
                soll, stellst du im Dashboard ein.
              </p>
            </ScrollReveal>

            <ScrollReveal von="rechts">
            <ol className="grid gap-3 sm:grid-cols-3">
              {[
                {
                  titel: "Hinzufügen",
                  text: "Über Discord autorisieren. Der Bot ist sofort auf dem Server.",
                },
                {
                  titel: "Einstellen",
                  text: "Im Dashboard anmelden und die Module wählen, die du brauchst.",
                },
                {
                  titel: "Läuft",
                  text: "Moderation, Tickets und Verifizierung arbeiten ab dem Speichern.",
                },
              ].map((schritt, i) => (
                <li key={schritt.titel} className="home-glass rounded-2xl p-6 shadow-[inset_0_1px_rgba(255,255,255,.05)]">
                  <span className="text-[13px] font-semibold tabular-nums text-indigo-400">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-3 text-[16px] font-semibold text-white">
                    {schritt.titel}
                  </h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
                    {schritt.text}
                  </p>
                </li>
              ))}
            </ol>
            </ScrollReveal>
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────── */}
      <section className="px-4 py-12 sm:px-6 sm:py-20 lg:px-12 xl:px-20">
        <ScrollReveal von="rechts" className="home-glass mx-auto max-w-[900px] rounded-3xl p-6 sm:p-9">
          {/* Vorher stand hier dreimal dasselbe untereinander: das
              Kürzel „FAQ", die Überschrift „Häufig gestellte Fragen"
              und der Satz „Finde Antworten auf häufig gestellte
              Fragen". Einmal reicht. */}
          <div className="mb-8">
            <h2 className="text-[28px] font-bold tracking-tight text-white sm:text-[32px]">
              Häufige Fragen
            </h2>
          </div>

          <div className="border-t border-slate-800">
            {FAQ.map((f, index) => (
              <div key={f.frage} className={cn(index >= 4 && !alleFaqSichtbar && "hidden sm:block")}>
                <FaqZeile frage={f.frage} antwort={f.antwort} />
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setAlleFaqSichtbar((sichtbar) => !sichtbar)}
            className="mt-5 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-indigo-200 sm:hidden"
          >
            {alleFaqSichtbar ? "Weniger Fragen anzeigen" : `${FAQ.length - 4} weitere Fragen anzeigen`}
          </button>
        </ScrollReveal>
      </section>

      {/* ── Abschluss ─────────────────────────────────────── */}
      {/*
          „Bereit loszulegen?" in 40px, mittig, in einem eigenen
          Kasten -- die Schlussformel jeder Landingpage. Der Satz
          fragt etwas, worauf niemand antwortet, und
          „Einrichtung dauert keine zwei Minuten" ist eine Zusage, die
          niemand gemessen hat.

          Stattdessen eine Zeile mit dem, was man hier tun kann. */}
      <section className="px-4 pb-12 sm:px-6 sm:pb-20 lg:px-12 xl:px-20">
        <ScrollReveal von="links" className="home-glass mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-6 rounded-3xl p-6 sm:p-8">
          <div>
            <h2 className="text-[20px] font-bold tracking-tight text-white">
              {BRAND} zu deinem Server hinzufügen
            </h2>
            <p className="mt-1.5 text-[15px] text-slate-400">
              Kostenlos. Was der Bot tun soll, entscheidest du danach im
              Dashboard.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <a
              href={INVITE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-[#5865f2] px-6 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
            >
              Bot hinzufügen
            </a>
            <Link
              href="/dashboard"
              className="rounded-lg border border-slate-800 px-5 py-3 text-[15px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
            >
              Zum Dashboard
            </Link>
          </div>
        </ScrollReveal>
      </section>

      <style jsx global>{`
        @keyframes heroProgress {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
        @keyframes universeDrift {
          0%, 100% { background-position: 48% 50%; }
          50% { background-position: 54% 46%; }
        }
        @keyframes cometFlight {
          0% { transform: translate3d(-340px,-140px,0) rotate(24deg); opacity: 0; }
          8% { opacity: .9; }
          30%, 100% { transform: translate3d(1500px,640px,0) rotate(24deg); opacity: 0; }
        }
        .university-universe { background-size: 108% 108%; animation: universeDrift 26s ease-in-out infinite; }
        .university-comet { position: absolute; left: 0; top: 0; width: 220px; height: 2px; border-radius: 999px; background: linear-gradient(90deg,transparent,rgba(199,210,254,.2),rgba(255,255,255,.95)); box-shadow: 0 0 10px rgba(165,180,252,.75); opacity: 0; animation: cometFlight 9s linear infinite; }
        .university-comet::after { content: ""; position: absolute; right: -2px; top: -2px; width: 6px; height: 6px; border-radius: 999px; background: white; box-shadow: 0 0 16px 4px rgba(199,210,254,.8); }
        .university-comet-one { top: 6%; animation-delay: 1s; }
        .university-comet-two { top: 28%; animation-delay: 4.5s; animation-duration: 12s; transform: scale(.7); }
        .university-comet-three { top: 50%; animation-delay: 8s; animation-duration: 15s; }
        .home-glass {
          border: 1px solid rgba(255,255,255,.11);
          background: linear-gradient(135deg,rgba(17,24,39,.67),rgba(8,12,24,.52));
          box-shadow: inset 0 1px rgba(255,255,255,.06), 0 22px 65px rgba(0,0,0,.24);
          -webkit-backdrop-filter: blur(22px) saturate(135%);
          backdrop-filter: blur(22px) saturate(135%);
        }
        @media (max-width: 639px) {
          .university-universe {
            animation: none !important;
            background-position: 66% center;
            background-size: cover;
          }
          .university-comet { display: none; animation: none !important; }
          .home-glass {
            box-shadow: inset 0 1px rgba(255,255,255,.05), 0 12px 35px rgba(0,0,0,.18);
            -webkit-backdrop-filter: blur(10px) saturate(115%);
            backdrop-filter: blur(10px) saturate(115%);
          }
          .scroll-reveal {
            filter: none !important;
            transition-property: opacity, transform !important;
          }
          .university-universe [class*="backdrop-blur"] {
            -webkit-backdrop-filter: blur(8px) !important;
            backdrop-filter: blur(8px) !important;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          [class*="heroProgress"], .university-universe, .university-comet { animation: none !important; }
          .university-comet { display: none; }
        }
      `}</style>
    </div>
  );
}
