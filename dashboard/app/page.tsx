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
import Link from "next/link";
import {
  ArrowRight,
  BarChart4,
  Brain,
  ChevronDown,
  ClipboardList,
  Crown,
  Database,
  Gift,
  KeyRound,
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

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

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
    frage: "Kann ich Premium bereits kaufen?",
    antwort:
      "Noch nicht. Es ist derzeit kein Zahlungsanbieter angebunden und die Premium-Testphase läuft. Einen Zugang kannst du über den Beta-Antrag im Dashboard beantragen. Die Preisübersicht zeigt bereits die geplanten Tarife, aber die Kaufknöpfe sind bewusst deaktiviert.",
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

export default function LandingPage() {
  const [karte, setKarte] = React.useState(0);
  const [zahlen, setZahlen] = React.useState<any>(null);

  // Die Karten im Hero weiterblättern. Fünf Sekunden: lang genug, um
  // die drei Zeilen zu lesen, kurz genug, dass man die zweite Karte
  // noch sieht, bevor man weiterscrollt.
  React.useEffect(() => {
    const t = setInterval(
      () => setKarte((k) => (k + 1) % HERO_KARTEN.length),
      4500,
    );
    return () => clearInterval(t);
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

  const Aktiv = HERO_KARTEN[karte].icon;

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-slate-200 selection:bg-indigo-500/30">
      <SiteNav />

      {/* ── Hero ──────────────────────────────────────────── */}
      <header className="relative overflow-x-clip">
        {/* Ein einziger, sehr weicher Schein. Die alte Seite hatte
            zwei pulsierende Flächen; auf einem dunklen Grund sieht man
            davon nur das Rauschen. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 left-1/4 h-[520px] w-[520px] rounded-full bg-indigo-600/[0.07] blur-[140px]"
        />

        <div className="relative mx-auto max-w-[1400px] px-6 lg:px-12 xl:px-20 py-20 lg:py-28">
          <div className="grid lg:grid-cols-2 gap-14 items-center">
            <div>
              {/* EIN Abzeichen, nicht zwei.
                  Vorher standen „Aktiv auf Discord" und „Der
                  Allrounder-Bot" nebeneinander. Das zweite ist eine
                  Selbstbeschreibung ohne Inhalt -- „Allrounder" sagt
                  nichts, was der Absatz darunter nicht besser sagt.
                  Das erste nennt eine Zahl, sobald der Bot sie
                  liefert. */}
              <div className="mb-8">
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-[#131318] px-3.5 py-1.5 text-[13px] text-slate-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  {server ? `Läuft auf ${server} Servern` : "Läuft auf Discord"}
                </span>
              </div>

              {/* Kein Farbwechsel mitten in der Überschrift.
                  „Dein Discord-Server, auf das nächste Level
                  gebracht" -- die halbe Zeile in Indigo -- ist die
                  Bauform, die auf jeder zweiten Landingpage steht.
                  Sie verspricht etwas, das sich nicht prüfen lässt.
                  Der Satz sagt jetzt, was das Ding ist. */}
              <h1 className="text-[40px] sm:text-[52px] lg:text-[58px] font-bold leading-[1.08] tracking-tight text-white">
                Ein Discord-Bot,
                <br />
                der den Server führt
              </h1>

              <p className="mt-6 max-w-lg text-[17px] leading-relaxed text-slate-400">
                Moderation, Tickets, Bewerbungen, Verifizierung — in einem Bot,
                eingerichtet über ein Dashboard statt über Befehle.
              </p>

              <div className="mt-9 flex flex-wrap items-center gap-3">
                {/* Der Aufkleber „KOSTENLOS" über dem Knopf ist weg.
                    Er hing halb darüber hinaus und sah aus wie ein
                    Preisschild im Schlussverkauf. Dass es nichts
                    kostet, steht jetzt als ruhiger Satz daneben --
                    dieselbe Aussage, ohne Marktschreier. */}
                <a
                  href={INVITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center rounded-lg bg-[#5865f2] px-6 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
                >
                  Bot hinzufügen
                </a>
                <Link
                  href="#funktionen"
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-800 px-5 py-3 text-[15px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
                >
                  Funktionen ansehen
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>

              <p className="mt-5 text-[13px] text-slate-500">
                Kostenlos · Keine Anmeldung nötig, um ihn hinzuzufügen
              </p>
            </div>

            {/* Die Karte rechts.
                Drei Dinge sind hier weggefallen:

                  * **Der Stapel.** Zwei angedeutete Karten dahinter
                    sollten Tiefe vortäuschen. Sie zeigten nichts und
                    kosteten nur Kanten.
                  * **Die Farbverlauf-Kachel** für das Symbol. Ein
                    pink-violetter Verlauf auf einer sonst blauen
                    Seite -- die Sorte Farbe, die zufällig wirkt.
                  * **Die 52px große Zahl in Fuchsia.** „24/7" ist
                    keine Messung, sondern eine Behauptung; groß und
                    bunt gesetzt sah sie nach Kennzahl aus.

                Übrig bleibt, was die Karte eigentlich soll: zeigen,
                was der Bot kann, eins nach dem anderen. */}
            <div className="relative hidden lg:block">
              <div className="rounded-2xl border border-slate-800 bg-[#131318] p-7">
                <div className="grid h-11 w-11 place-items-center rounded-xl border border-slate-800 bg-[#0f0f13]">
                  <Aktiv className="h-5 w-5 text-indigo-400" />
                </div>

                <h3 className="mt-5 text-[19px] font-semibold text-white">
                  {HERO_KARTEN[karte].titel}
                </h3>
                <p className="mt-2.5 min-h-[72px] text-[15px] leading-relaxed text-slate-400">
                  {HERO_KARTEN[karte].text}
                </p>

                {/* Die Punkte in die Karte statt darunter: sie
                    gehören zu ihr, und darunter standen sie wie eine
                    zweite, leere Zeile im Layout. */}
                <div className="mt-6 flex items-center gap-3 border-t border-slate-800 pt-5">
                  <div className="flex flex-1 flex-wrap items-center gap-1.5">
                    {HERO_KARTEN.map((k, i) => (
                      <button
                        key={k.titel}
                        type="button"
                        aria-label={k.titel}
                        title={k.titel}
                        onClick={() => setKarte(i)}
                        className={cn(
                          "h-1.5 rounded-full transition-colors",
                          i === karte
                            ? "w-5 bg-indigo-500"
                            : "w-1.5 bg-slate-700 hover:bg-slate-600",
                        )}
                      />
                    ))}
                  </div>
                  <span className="shrink-0 text-[12px] tabular-nums text-slate-600">
                    {karte + 1}/{HERO_KARTEN.length}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

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
      <section id="funktionen" className="px-6 py-20 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <div className="max-w-2xl">
            <h2 className="text-[28px] font-bold tracking-tight text-white sm:text-[32px]">
              Alle Module im Überblick
            </h2>
            <p className="mt-3 text-[16px] leading-relaxed text-slate-400">
              {MODUL_ANZAHL} Bereiche aus dem aktuellen Dashboard — nach Aufgabe
              gruppiert und mit ihren tatsächlichen Grenzen beschrieben.
            </p>
          </div>

          <div className="mt-10 space-y-5">
            {FUNKTIONS_GRUPPEN.map((gruppe) => {
              const GruppenIcon = gruppe.icon;
              return (
                <article
                  key={gruppe.titel}
                  className="overflow-hidden rounded-2xl border border-slate-800 bg-[#0f0f13]"
                >
                  <div className="flex flex-col gap-3 border-b border-slate-800 bg-[#131318] px-5 py-5 sm:flex-row sm:items-center sm:px-6">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/20 bg-indigo-500/10">
                      <GruppenIcon className="h-5 w-5 text-indigo-400" />
                    </span>
                    <div>
                      <h3 className="text-[17px] font-bold text-white">
                        {gruppe.titel}
                      </h3>
                      <p className="mt-0.5 text-[13px] text-slate-500">
                        {gruppe.text}
                      </p>
                    </div>
                    <span className="sm:ml-auto text-xs tabular-nums text-slate-600">
                      {gruppe.module.length} Module
                    </span>
                  </div>
                  <div className="grid gap-px bg-slate-800 sm:grid-cols-2 lg:grid-cols-3">
                    {gruppe.module.map(([titel, text]) => (
                      <div
                        key={titel}
                        className="bg-[#0f0f13] p-5 transition-colors hover:bg-[#131318]"
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
              );
            })}
          </div>
        </div>
      </section>

      {/* Premium steht bewusst in der Mitte: nach dem vollständigen
          Funktionsüberblick, aber vor Kennzahlen und Einrichtung. */}
      <section className="px-6 py-14 lg:px-12 xl:px-20">
        <div className="relative mx-auto max-w-[1400px] overflow-hidden rounded-3xl border border-amber-400/30 bg-[#15120b] px-6 py-9 sm:px-9 lg:px-12 lg:py-11">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-24 -top-32 h-80 w-80 rounded-full bg-amber-400/10 blur-3xl"
          />
          <div className="relative grid gap-8 lg:grid-cols-[1fr_0.9fr] lg:items-center">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1 text-xs font-bold text-amber-300">
                <Crown className="h-3.5 w-3.5" />
                Premium · Testphase
              </span>
              <h2 className="mt-5 text-3xl font-black tracking-tight text-white sm:text-4xl">
                Mehr Möglichkeiten für beide Bots
              </h2>
              <p className="mt-4 max-w-2xl text-[15px] leading-7 text-slate-400">
                Premium hängt an deinem Discord-Konto und gilt für den
                University Bot und den Template-Bot. Kaufen ist während der
                Testphase noch nicht möglich — Zugang gibt es derzeit nur über
                einen Beta-Antrag.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link
                  href="/dashboard/premium/beta"
                  className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-5 py-3 text-sm font-black text-black hover:bg-amber-300"
                >
                  <Sparkles className="h-4 w-4" />
                  Für Premium bewerben
                </Link>
                <Link
                  href="/premium"
                  className="inline-flex items-center gap-2 rounded-xl border border-amber-400/25 px-5 py-3 text-sm font-semibold text-amber-200 hover:bg-amber-400/10"
                >
                  Premium ehrlich vergleichen <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {[
                [Palette, "Eigenes Bot-Aussehen"],
                [Database, "Bis zu 10 Backups und Automatik"],
                [Zap, "Speedrun und Premium-Vorlagen"],
                [BarChart4, "Rollen, Kanäle und Online-Nutzer"],
                [KeyRound, "Bis zu 20 Custom Commands"],
                [Server, "Ein Zugang für beide Bots"],
              ].map(([Icon, text]) => {
                const PremiumIcon = Icon as React.ElementType;
                return (
                  <li
                    key={String(text)}
                    className="flex items-center gap-3 rounded-xl border border-amber-400/15 bg-black/20 p-3 text-sm text-slate-300"
                  >
                    <PremiumIcon className="h-4 w-4 shrink-0 text-amber-400" />
                    {text as string}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
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
      <section className="px-6 py-16 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-8 rounded-2xl border border-slate-800 bg-[#0f0f13] px-7 py-7">
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
          </div>
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
      <section className="border-y border-slate-800/70 px-6 py-20 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,360px)_1fr] lg:gap-20">
            <div>
              <h2 className="text-[28px] font-bold leading-tight tracking-tight text-white sm:text-[32px]">
                In drei Schritten eingerichtet
              </h2>
              <p className="mt-4 max-w-sm text-[16px] leading-relaxed text-slate-400">
                Kein Handbuch, keine Konfigurationsdatei. Was der Bot können
                soll, stellst du im Dashboard ein.
              </p>
            </div>

            <ol className="grid gap-px overflow-hidden rounded-2xl border border-slate-800 bg-slate-800 sm:grid-cols-3">
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
                <li key={schritt.titel} className="bg-[#0f0f13] p-6">
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
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────── */}
      <section className="px-6 py-20 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[900px]">
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
            {FAQ.map((f) => (
              <FaqZeile key={f.frage} frage={f.frage} antwort={f.antwort} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Abschluss ─────────────────────────────────────── */}
      {/*
          „Bereit loszulegen?" in 40px, mittig, in einem eigenen
          Kasten -- die Schlussformel jeder Landingpage. Der Satz
          fragt etwas, worauf niemand antwortet, und
          „Einrichtung dauert keine zwei Minuten" ist eine Zusage, die
          niemand gemessen hat.

          Stattdessen eine Zeile mit dem, was man hier tun kann. */}
      <section className="px-6 pb-20 lg:px-12 xl:px-20">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-6 rounded-2xl border border-slate-800 bg-[#0f0f13] px-7 py-8">
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
        </div>
      </section>
    </div>
  );
}
