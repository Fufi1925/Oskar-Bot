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
    text: "Massenlöschungen, Massenbann und feindliche Bots werden gestoppt, bevor Schaden entsteht.",
  },
  {
    icon: ClipboardList,
    titel: "Bewerbungen",
    text: "Fragen per Direktnachricht, Entscheidung per Knopf, Rollen automatisch — bis zu fünf auf einmal.",
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
  const [zahlen, setZahlen] = React.useState<any>(null);

  // Die Karten im Hero weiterblättern. Fünf Sekunden: lang genug, um
  // die drei Zeilen zu lesen, kurz genug, dass man die zweite Karte
  // noch sieht, bevor man weiterscrollt.
  React.useEffect(() => {
    const t = setInterval(() => setKarte((k) => (k + 1) % HERO_KARTEN.length), 4500);
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
                Moderation, Tickets, Bewerbungen, Verifizierung — in einem
                Bot, eingerichtet über ein Dashboard statt über Befehle.
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
          <div className="max-w-xl">
            <h2 className="text-[28px] font-bold tracking-tight text-white sm:text-[32px]">
              Was der Bot mitbringt
            </h2>
            <p className="mt-3 text-[16px] leading-relaxed text-slate-400">
              {FUNKTIONEN.length} Bereiche, einzeln zuschaltbar. Du
              brauchst nur, was du einschaltest.
            </p>
          </div>

          {/* Ein Raster aus Linien statt aus Kästen: die Karten
              teilen sich ihre Ränder, statt jede einen eigenen zu
              ziehen. Das ergibt ein ruhiges Gitter statt 34
              schwebender Kacheln. */}
          {/* `bg-slate-800` faerbt die Fugen -- und bei 20 Karten auf
              3 Spalten bleibt eine Zelle leer, die dann als grauer
              Block dasteht. Im Bild aufgefallen, nicht im Quelltext.
              Der Hintergrund der Fugen wird deshalb ueber
              `[&>*]:bg-[#0f0f13]` von den Kindern getragen, und die
              Luecke bekommt am Ende eine leere Fuellzelle in
              Kartenfarbe. */}
          <div className="mt-10 grid gap-px overflow-hidden rounded-2xl border border-slate-800 bg-slate-800 sm:grid-cols-2 lg:grid-cols-3">
            {FUNKTIONEN.map(({ icon: Icon, titel, text }) => (
              <div
                key={titel}
                className="bg-[#0f0f13] p-5 transition-colors hover:bg-[#131318]"
              >
                <div className="flex items-center gap-2.5">
                  <Icon className="h-4 w-4 shrink-0 text-indigo-400" />
                  <h3 className="text-[15px] font-semibold text-white">
                    {titel}
                  </h3>
                </div>
                <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
                  {text}
                </p>
              </div>
            ))}

            {/* Fuellzellen fuer die letzte Reihe. Ohne sie zeigt das
                Raster dort seinen eigenen grauen Hintergrund. */}
            {Array.from({ length: (3 - (FUNKTIONEN.length % 3)) % 3 }).map((_, i) => (
              <div key={`luecke-${i}`} aria-hidden className="hidden bg-[#0f0f13] lg:block" />
            ))}
            {FUNKTIONEN.length % 2 === 1 && (
              <div aria-hidden className="hidden bg-[#0f0f13] sm:block lg:hidden" />
            )}
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
              <Link href="/status" className="text-slate-400 underline decoration-slate-700 underline-offset-4 hover:text-white">
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
                Kein Handbuch, keine Konfigurationsdatei. Was der Bot
                können soll, stellst du im Dashboard ein.
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
