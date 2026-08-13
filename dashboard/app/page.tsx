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
  Activity, ArrowRight, BarChart4, Bot, Brain, Check, ChevronDown,
  ClipboardList, Gift, Hash, Headphones, Layers, Lock, Mail,
  MessageSquare, Mic, Music, PenLine, ShieldAlert, ShieldCheck,
  Sparkles, Ticket, UserCog, Users, Zap,
} from "lucide-react";
import { SiteNav, INVITE_URL } from "@/components/site-nav";
import { SUPPORT_INVITE } from "@/lib/legal";
import { cn } from "@/lib/utils";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

const CARD =
  "rounded-2xl border border-slate-800 bg-[#0f0f13] p-5 transition-colors hover:border-slate-700";

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
    zahl: "24/7",
    label: "Sicherheit",
    ton: "from-pink-500 to-rose-600",
  },
  {
    icon: UserCog,
    titel: "Team-Update",
    text: "Befördern, zurückstufen, verwarnen — Rollen umstecken und ankündigen in einem Zug, mit Unterschriften.",
    zahl: "5",
    label: "Befehle",
    ton: "from-indigo-500 to-violet-600",
  },
  {
    icon: Ticket,
    titel: "Ticket-System",
    text: "Kategorien, Rechte, DM-Benachrichtigungen und Transkripte — vollständig im Dashboard eingerichtet.",
    zahl: "∞",
    label: "Tickets",
    ton: "from-sky-500 to-blue-600",
  },
  {
    icon: ShieldAlert,
    titel: "Anti-Nuke",
    text: "Massenlöschungen, Massenbann und feindliche Bots werden gestoppt, bevor Schaden entsteht.",
    zahl: "12",
    label: "Wächter",
    ton: "from-red-500 to-rose-700",
  },
  {
    icon: ClipboardList,
    titel: "Bewerbungen",
    text: "Fragen per Direktnachricht, Entscheidung per Knopf, Rollen automatisch — bis zu fünf auf einmal.",
    zahl: "8",
    label: "Kategorien",
    ton: "from-amber-500 to-orange-600",
  },
  {
    icon: BarChart4,
    titel: "Level-System",
    text: "XP, Ränge und Belohnungen mit eigenem Rangbild — Aktivität sichtbar machen statt behaupten.",
    zahl: "100+",
    label: "Level",
    ton: "from-emerald-500 to-teal-600",
  },
  {
    icon: Music,
    titel: "Musik",
    text: "Wiedergabe, Playlists und Dauerbetrieb im Sprachkanal — auch nach einem Neustart.",
    zahl: "24/7",
    label: "Betrieb",
    ton: "from-fuchsia-500 to-purple-600",
  },
  {
    icon: ShieldCheck,
    titel: "AutoMod",
    text: "Filter, Strafen und Ausnahmen — greift, bevor jemand aus dem Team überhaupt online ist.",
    zahl: "9",
    label: "Filter",
    ton: "from-cyan-500 to-sky-600",
  },
  {
    icon: Sparkles,
    titel: "Server-Vorlagen",
    text: "Struktur als Vorlage sichern und auf dem nächsten Server in Minuten anwenden.",
    zahl: "1-Klick",
    label: "Aufbau",
    ton: "from-violet-500 to-indigo-600",
  },
  {
    icon: Mic,
    titel: "Join to Create",
    text: "Temporäre Sprachkanäle, die sich selbst aufräumen, wenn der Letzte gegangen ist.",
    zahl: "Auto",
    label: "Kanäle",
    ton: "from-blue-500 to-indigo-600",
  },
  {
    icon: Gift,
    titel: "Gewinnspiele",
    text: "Teilnahme per Knopf, Bedingungen nach Rolle oder Level, Auslosung durch den Bot.",
    zahl: "∞",
    label: "Preise",
    ton: "from-rose-500 to-pink-600",
  },
  {
    icon: Users,
    titel: "Teamliste",
    text: "Wer im Team ist, nach Rollen geordnet — hält sich selbst aktuell, ohne dass jemand nachträgt.",
    zahl: "Live",
    label: "Übersicht",
    ton: "from-teal-500 to-emerald-600",
  },
  {
    icon: Brain,
    titel: "KI-Funktionen",
    text: "Antworten, Zusammenfassungen und Übersetzungen direkt im Chat deines Servers.",
    zahl: "Neu",
    label: "KI",
    ton: "from-purple-500 to-fuchsia-600",
  },
];

/** Die Funktionen. Jede steht wirklich als Reiter im Dashboard. */
const FUNKTIONEN = [
  { icon: Brain, titel: "KI", text: "Nutze die Kraft der künstlichen Intelligenz in deinem Discord-Server." },
  { icon: ShieldAlert, titel: "AutoMod", text: "Filter, Strafen und Ausnahmen für deinen Server konfigurieren." },
  { icon: Layers, titel: "Befehls-Manager", text: "Module und einzelne Befehle zentral verwalten." },
  { icon: Hash, titel: "Zählen", text: "Ein unterhaltsames Spiel, bei dem Mitglieder gemeinsam zählen können." },
  { icon: Zap, titel: "Anti-Nuke", text: "Schutz vor Massenlöschungen, Massenbann und feindlichen Bots." },
  { icon: MessageSquare, titel: "Spaß", text: "Unterhalte deine Community mit lustigen Spielen und Befehlen." },
  { icon: Gift, titel: "Gewinnspiel", text: "Veranstalte Gewinnspiele für deine Community-Mitglieder." },
  { icon: Users, titel: "Einladungs-Logger", text: "Einladungen nachverfolgen, Statistiken und Bestenlisten." },
  { icon: Music, titel: "Musik", text: "Wiedergabe, Playlists und Dauerbetrieb im Sprachkanal." },
  { icon: BarChart4, titel: "Level-System", text: "Belohne aktive Mitglieder mit einem anpassbaren Level-System." },
  { icon: ShieldCheck, titel: "Moderation", text: "Halte deinen Server sauber und sicher mit starken Werkzeugen." },
  { icon: UserCog, titel: "Team-Update", text: "Beförderungen, Rückstufungen und Verwarnungen mit Akte." },
  { icon: Sparkles, titel: "Server-Vorlagen", text: "Server-Struktur als Vorlage speichern und anwenden." },
  { icon: ClipboardList, titel: "Bewerbungen", text: "Fragen per DM, Entscheidung per Knopf, Rollen automatisch." },
  { icon: Mic, titel: "Join to Create", text: "Temporäre Sprachkanäle für deine Community." },
  { icon: Ticket, titel: "Ticket-System", text: "Support-Tickets mit Kategorien und anpassbaren Einstellungen." },
  { icon: Headphones, titel: "Support-Warteraum", text: "Wartemusik, Ansage und geordnete Reihenfolge im Sprachkanal." },
  { icon: Check, titel: "Verifizierung", text: "Schütze deinen Server mit einem benutzerfreundlichen System." },
  { icon: PenLine, titel: "Eigene Nachricht", text: "Ankündigungen und Panels aus dem Dashboard verschicken." },
  { icon: Mail, titel: "Willkommen", text: "Willkommensnachrichten, Bilder und Abschied für neue Mitglieder." },
];

const STIMMEN = [
  {
    kuerzel: "FU",
    name: "Fufi",
    text: "Das Dashboard nimmt mir die halbe Arbeit ab. Einmal einrichten, danach läuft es — und ich sehe sofort, was der Bot gerade tut.",
  },
  {
    kuerzel: "VX",
    name: "Vexo",
    text: "Tickets, Bewerbungen und das Team-Update greifen ineinander. Wer angenommen wird, ist zwei Klicks später wirklich im Team.",
  },
  {
    kuerzel: "UN",
    name: "Uni-Server",
    text: "Anti-Nuke und Verifizierung liefen vom ersten Tag an ohne Nacharbeit. Genau das wollten wir.",
  },
];

const FAQ = [
  {
    frage: `Wie füge ich ${BRAND} zu meinem Server hinzu?`,
    antwort:
      "Oben auf „Bot hinzufügen“ klicken, den Server auswählen und die Rechte bestätigen. Danach einmal im Dashboard anmelden — dort richtest du alles Weitere ein, ohne einen einzigen Befehl tippen zu müssen.",
  },
  {
    frage: `Ist ${BRAND} kostenlos nutzbar?`,
    antwort:
      "Ja. Alle Module sind ohne Bezahlung nutzbar, es gibt keine Funktion hinter einer Bezahlschranke und keine Werbung in den Nachrichten des Bots.",
  },
  {
    frage: "Wie kann ich alle verfügbaren Befehle sehen?",
    antwort:
      "Mit >help im Chat oder auf der Seite „Alle Befehle“ — dort stehen sie durchsuchbar und mit Beschreibung. Die Hilfe im Discord ist nach Kategorien geordnet, damit man nicht durch eine lange Liste scrollen muss.",
  },
  {
    frage: "Kann ich das Präfix des Bots anpassen?",
    antwort:
      "Ja, im Dashboard unter „Einstellungen“. Standard ist >. Wer den Bot ohne Präfix bedienen darf, lässt sich unter „No Prefix“ je Rolle oder Person festlegen.",
  },
  {
    frage: "Wie melde ich Probleme oder erhalte Support?",
    antwort:
      "Über unseren Support-Server. Dort gibt es ein Ticket-System; Fehler werden meist am selben Tag beantwortet. Der Status aller Systeme steht außerdem auf der Status-Seite.",
  },
  {
    frage: `Unterstützt ${BRAND} mehrere Sprachen?`,
    antwort:
      "Das Dashboard gibt es auf Deutsch und Englisch, umschaltbar oben rechts. Die Sprache lässt sich zusätzlich pro Server festlegen, sodass alle Nachrichten des Bots dazu passen.",
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
  const [stimme, setStimme] = React.useState(0);
  const [zahlen, setZahlen] = React.useState<any>(null);

  // Die Karten im Hero weiterblättern. Fünf Sekunden: lang genug, um
  // die drei Zeilen zu lesen, kurz genug, dass man die zweite Karte
  // noch sieht, bevor man weiterscrollt.
  React.useEffect(() => {
    const t = setInterval(() => setKarte((k) => (k + 1) % HERO_KARTEN.length), 4500);
    return () => clearInterval(t);
  }, []);

  React.useEffect(() => {
    const t = setInterval(() => setStimme((s) => (s + 1) % STIMMEN.length), 6000);
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
              <div className="flex flex-wrap items-center gap-3 mb-9">
                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1.5 text-[13px] text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  {server ? `Von ${server} Servern genutzt` : "Aktiv auf Discord"}
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-4 py-1.5 text-[13px] text-indigo-300">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Der Allrounder-Bot
                </span>
              </div>

              <h1 className="text-[44px] sm:text-[56px] lg:text-[64px] font-extrabold leading-[1.05] tracking-tight text-white">
                Dein Discord-Server,
                <br />
                <span className="text-indigo-400">auf das nächste Level gebracht</span>
              </h1>

              <p className="mt-7 max-w-xl text-[17px] leading-relaxed text-slate-400">
                {BRAND} ist ein vielseitiger Discord-Bot mit Moderations-,
                Team-, Ticket- und KI-Funktionen, der deinen Server
                verbessert und deine Community zusammenhält.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <a
                  href={INVITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative inline-flex items-center rounded-xl bg-[#5865f2] px-7 py-3.5 text-[15px] font-semibold text-white hover:bg-[#4752c4] transition-colors"
                >
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-md bg-emerald-500 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                    Kostenlos
                  </span>
                  Bot hinzufügen
                </a>
                <Link
                  href="#funktionen"
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-[#131318] px-6 py-3.5 text-[15px] text-slate-200 hover:border-slate-700 transition-colors"
                >
                  Funktionen erkunden
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>

            {/* Der Kartenstapel. */}
            <div className="relative hidden lg:block">
              <div className="relative mx-auto h-[430px] max-w-[430px]">
                {/* Zwei angedeutete Karten dahinter, damit es nach
                    einem Stapel aussieht statt nach einer Karte. */}
                <div className="absolute inset-x-8 top-5 bottom-5 rounded-3xl border border-slate-800/50 bg-[#0f0f13]/50" />
                <div className="absolute inset-x-4 top-2.5 bottom-2.5 rounded-3xl border border-slate-800/70 bg-[#0f0f13]/70" />

                <div className="relative rounded-3xl border border-slate-800 bg-[#131318] p-8 h-full">
                  <div
                    className={cn(
                      "h-[68px] w-[68px] rounded-2xl bg-gradient-to-br grid place-items-center mb-7",
                      HERO_KARTEN[karte].ton,
                    )}
                  >
                    <Aktiv className="h-8 w-8 text-white" />
                  </div>

                  <h3 className="text-[22px] font-bold text-white mb-3">
                    {HERO_KARTEN[karte].titel}
                  </h3>
                  <p className="text-[15px] leading-relaxed text-slate-400">
                    {HERO_KARTEN[karte].text}
                  </p>

                  <div className="mt-9 flex items-baseline gap-3">
                    <span className="text-[52px] font-extrabold leading-none text-fuchsia-400">
                      {HERO_KARTEN[karte].zahl}
                    </span>
                    <span className="text-[13px] uppercase tracking-widest text-slate-500">
                      {HERO_KARTEN[karte].label}
                    </span>
                  </div>
                </div>
              </div>

              {/* Dreizehn Punkte, nicht dreizehn Striche: Striche
                  waeren zusammen breiter als die Karte. */}
              <div className="mt-7 flex flex-wrap items-center justify-center gap-1.5">
                {HERO_KARTEN.map((k, i) => (
                  <button
                    key={k.titel}
                    type="button"
                    aria-label={k.titel}
                    title={k.titel}
                    onClick={() => setKarte(i)}
                    className={cn(
                      "h-1.5 rounded-full transition-all",
                      i === karte
                        ? "w-6 bg-indigo-500"
                        : "w-1.5 bg-slate-700 hover:bg-slate-600",
                    )}
                  />
                ))}
              </div>
              <div className="mt-2.5 text-center text-[12px] text-slate-600">
                {karte + 1} von {HERO_KARTEN.length}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── Funktionen ────────────────────────────────────── */}
      <section id="funktionen" className="py-24 px-6 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px]">
          <div className="text-center mb-14">
            <span className="inline-block rounded-full border border-slate-800 bg-[#131318] px-4 py-1.5 text-[13px] text-indigo-300">
              Funktionen
            </span>
            <h2 className="mt-6 text-[38px] sm:text-[44px] font-extrabold tracking-tight text-white">
              Alles was du brauchst
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-[16px] leading-relaxed text-slate-400">
              {BRAND} bietet eine Vielzahl von Funktionen, um deinen
              Discord-Server zu verbessern und zu verwalten.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FUNKTIONEN.map(({ icon: Icon, titel, text }) => (
              <div key={titel} className={CARD}>
                <div className="flex items-start gap-4">
                  <div className="h-11 w-11 shrink-0 rounded-xl bg-[#5865f2] grid place-items-center">
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-[16px] font-bold text-white">{titel}</h3>
                    <p className="mt-1.5 text-[14px] leading-relaxed text-slate-400">
                      {text}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Zahlen ────────────────────────────────────────── */}
      <section className="py-24 px-6 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px] text-center">
          <h2 className="text-[32px] sm:text-[38px] font-extrabold tracking-tight text-white">
            In Zahlen
          </h2>
          <p className="mt-3 text-[16px] text-slate-400">
            Direkt aus dem laufenden Bot — nicht geschätzt.
          </p>

          <div className="mx-auto mt-12 grid max-w-4xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { wert: server ?? "—", label: "Server" },
              { wert: zeig(zahlen?.modules), label: "Module" },
              { wert: zeig(zahlen?.commands), label: "Befehle" },
              { wert: zeig(zahlen?.users), label: "Mitglieder" },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-2xl border border-slate-800 bg-[#0f0f13] px-6 py-8"
              >
                <div className="text-[34px] font-extrabold leading-none text-white">
                  {s.wert}
                </div>
                <div className="mt-2 text-[13px] text-slate-500">
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          {/* Die fünf goldenen Sterne hier sind weg: über echten
              Zahlen sahen sie aus wie eine Bewertung, waren aber
              reine Dekoration. */}
          <p className="mt-10 text-[13px] text-slate-500">
            Zahlen aus dem laufenden Bot &middot;{" "}
            <Link href="/status" className="text-indigo-400 hover:text-indigo-300">
              Status ansehen
            </Link>
          </p>
        </div>
      </section>

      {/* ── Stimmen ───────────────────────────────────────── */}
      <section className="py-24 px-6 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1400px] grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <span className="inline-block rounded-full border border-slate-800 bg-[#131318] px-4 py-1.5 text-[13px] text-slate-300">
              Community-Stimmen
            </span>
            <h2 className="mt-6 text-[38px] sm:text-[44px] font-extrabold leading-tight tracking-tight text-white">
              Warum Teams {BRAND} nutzen
            </h2>
            <p className="mt-4 max-w-md text-[16px] leading-relaxed text-slate-400">
              Erfahrungen aus aktiven Discord-Communities &mdash;
              zuverlässig, schnell und ohne Nacharbeit.
            </p>
          </div>

          <div>
            <div className="space-y-4">
              {[STIMMEN[stimme], STIMMEN[(stimme + 1) % STIMMEN.length]].map((s) => (
                <div key={s.name} className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-5">
                  <div className="flex items-start gap-3">
                    <div className="h-9 w-9 shrink-0 rounded-full bg-emerald-500/15 grid place-items-center text-[12px] font-bold text-emerald-400">
                      {s.kuerzel}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span className="text-[15px] font-bold text-white">
                        {s.name}
                      </span>
                      <p className="mt-1.5 text-[14px] leading-relaxed text-slate-400">
                        {s.text}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 flex items-center justify-center gap-2">
              {STIMMEN.map((s, i) => (
                <button
                  key={s.name}
                  type="button"
                  aria-label={s.name}
                  onClick={() => setStimme(i)}
                  className={cn(
                    "h-1.5 rounded-full transition-all",
                    i === stimme ? "w-7 bg-emerald-500" : "w-1.5 bg-slate-700",
                  )}
                />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────── */}
      <section className="py-24 px-6 lg:px-12 xl:px-20">
        <div className="mx-auto max-w-[1000px]">
          <div className="text-center mb-12">
            <span className="text-[13px] font-semibold uppercase tracking-widest text-indigo-400">
              FAQ
            </span>
            <h2 className="mt-4 text-[38px] sm:text-[44px] font-extrabold tracking-tight text-white">
              Häufig gestellte Fragen
            </h2>
            <p className="mt-4 text-[16px] text-slate-400">
              Finde Antworten auf häufig gestellte Fragen über {BRAND}.
            </p>
          </div>

          <div className="border-t border-slate-800">
            {FAQ.map((f) => (
              <FaqZeile key={f.frage} frage={f.frage} antwort={f.antwort} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Abschluss ─────────────────────────────────────── */}
      <section className="px-6 lg:px-12 xl:px-20 pb-24">
        <div className="mx-auto max-w-[1000px] rounded-3xl border border-slate-800 bg-[#0f0f13] px-8 py-16 text-center">
          <h2 className="text-[32px] sm:text-[40px] font-extrabold tracking-tight text-white">
            Bereit loszulegen?
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[16px] leading-relaxed text-slate-400">
            Bot hinzufügen, im Dashboard anmelden, fertig. Die
            Einrichtung dauert keine zwei Minuten.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <a
              href={INVITE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl bg-[#5865f2] px-7 py-3.5 text-[15px] font-semibold text-white hover:bg-[#4752c4] transition-colors"
            >
              Bot hinzufügen
            </a>
            <Link
              href="/dashboard"
              className="rounded-xl border border-slate-800 bg-[#131318] px-7 py-3.5 text-[15px] text-slate-200 hover:border-slate-700 transition-colors"
            >
              Zum Dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* ── Fußzeile ──────────────────────────────────────── */}
      <footer className="border-t border-slate-800 px-6 lg:px-12 xl:px-20 py-14">
        <div className="mx-auto max-w-[1400px]">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lg:col-span-2">
              <div className="flex items-center gap-2.5">
                <Bot className="h-5 w-5 text-indigo-400" />
                <span className="text-[19px] font-extrabold text-white">
                  {BRAND}
                </span>
              </div>
              <p className="mt-4 max-w-sm text-[14px] leading-relaxed text-slate-500">
                Moderation, Tickets, Bewerbungen und Team-Verwaltung in
                einem Bot &mdash; vollständig über das Dashboard
                einzurichten.
              </p>
            </div>

            <div>
              <h4 className="text-[13px] font-bold uppercase tracking-widest text-slate-400">
                Produkt
              </h4>
              <ul className="mt-4 space-y-3 text-[14px] text-slate-500">
                <li><Link href="/docs" className="hover:text-white transition-colors">Dokumentation</Link></li>
                <li><Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link></li>
                <li><Link href="/status" className="hover:text-white transition-colors">Status</Link></li>
                <li><Link href="/team" className="hover:text-white transition-colors">Team</Link></li>
              </ul>
            </div>

            <div>
              <h4 className="text-[13px] font-bold uppercase tracking-widest text-slate-400">
                Rechtliches
              </h4>
              <ul className="mt-4 space-y-3 text-[14px] text-slate-500">
                <li><Link href="/privacy" className="hover:text-white transition-colors">Datenschutz</Link></li>
                <li><Link href="/terms" className="hover:text-white transition-colors">Nutzungsbedingungen</Link></li>
                <li><Link href="/imprint" className="hover:text-white transition-colors">Impressum</Link></li>
                <li>
                  <a href={SUPPORT_INVITE} target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                    Support-Server
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-slate-800 pt-8 sm:flex-row">
            <p className="text-[13px] text-slate-600">
              &copy; 2026 {BRAND}. Alle Rechte vorbehalten.
            </p>
            <span className="flex items-center gap-2 text-[13px] text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Alle Systeme aktiv
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
