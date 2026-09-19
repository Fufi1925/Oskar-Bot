"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight, Check, ChevronDown, Crown,
  Headphones, Languages, MessageSquareText,
  PanelsTopLeft, ShieldCheck, Sparkles, Ticket, Users, Zap,
} from "lucide-react";
import { INVITE_URL, SiteNav } from "@/components/site-nav";
import { LegacyHomepage } from "@/components/home/legacy-homepage";
import { InteractiveHomeGlobe } from "@/components/home/interactive-home-globe";
import { FeaturedServerMarquee } from "@/components/home/featured-server-marquee";
import { SUPPORT_INVITE } from "@/lib/legal";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

type HomepageVersion = "new" | "classic";

const FEATURES = [
  { icon: ShieldCheck, title: "Sicherheit", text: "Anti-Nuke, AutoMod, Honeypot und Verifizierung arbeiten zusammen, bevor ein Angriff zum Problem wird." },
  { icon: Ticket, title: "Tickets & Support", text: "Flexible Panels, Kategorien, Teamrechte, Transkripte und Benachrichtigungen in einem vollständigen Workflow." },
  { icon: Users, title: "Community", text: "Level, Rollen, Bewerbungen, Begrüßung, Gewinnspiele und Teamlisten für eine aktive Community." },
  { icon: Zap, title: "Automationen", text: "Eigene Befehle, Reaktionen, Antworten, Logs und wiederkehrende Abläufe ohne Konfigurationsdateien." },
  { icon: Headphones, title: "Voice & Musik", text: "Musik, temporäre Sprachkanäle und geordnete Support-Warteräume direkt auf deinem Server." },
  { icon: PanelsTopLeft, title: "Ein Dashboard", text: "Alle Module zentral konfigurieren, den Zustand sehen und Änderungen nachvollziehbar verwalten." },
];

const LANGUAGES = [["🇩🇪", "Deutsch"], ["🇺🇸", "English"]];

const FAQ = [
  ["Ist der Bot kostenlos?", "Ja. Die wichtigsten Module kannst du kostenlos verwenden. Premium erweitert Limits und schaltet unter anderem Server-Design, User Pull und zusätzliche Backups frei."],
  ["Brauche ich Programmierkenntnisse?", "Nein. Du wählst deinen Server im Dashboard aus und stellst jedes Modul über verständliche Formulare ein."],
  ["Wie sicher ist mein Server?", "Kritische Aktionen sind serverseitig geschützt. Anti-Nuke, AutoMod, Protokolle und rollenbasierte Zugriffe helfen dabei, Risiken früh zu erkennen."],
  ["Kann ich nur einzelne Funktionen nutzen?", "Ja. Jedes Modul ist separat konfigurierbar. Du aktivierst nur, was dein Server wirklich braucht."],
];

function FaqRow({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = React.useState(false);
  return <div className="border-b border-white/[.07]"><button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-5 py-5 text-left"><span className="font-bold text-white">{question}</span><ChevronDown className={`h-5 w-5 shrink-0 text-blue-400 transition ${open ? "rotate-180" : ""}`} /></button>{open && <p className="max-w-3xl pb-5 text-sm leading-7 text-zinc-400">{answer}</p>}</div>;
}

function NewHomepage() {
  const [numbers, setNumbers] = React.useState<any>(null);
  React.useEffect(() => {
    let active = true;
    fetch("/api/bot/bot/numbers").then((res) => res.ok ? res.json() : null).then((data) => { if (active && data) setNumbers(data); }).catch(() => {});
    return () => { active = false; };
  }, []);
  return (
    <main className="new-home min-h-screen overflow-x-clip bg-[#09090b] text-zinc-200 selection:bg-blue-500/30">
      <SiteNav />

      <section
        className="new-home-universe relative flex min-h-[790px] items-center overflow-hidden bg-cover px-4 pb-16 pt-28 sm:px-6 lg:pt-32"
        style={{ backgroundImage: "url('/home-university-universe.jpg')" }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(3,7,18,.92)_0%,rgba(3,7,18,.72)_38%,rgba(3,7,18,.16)_67%,rgba(3,7,18,.05)_100%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(3,7,18,.3),transparent_35%,rgba(9,9,11,.84)_100%)]" />
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <span className="new-home-comet new-home-comet-one" />
          <span className="new-home-comet new-home-comet-two" />
          <span className="new-home-comet new-home-comet-three" />
        </div>

        <div className="relative mx-auto w-full max-w-[1320px]">
          <div className="max-w-[590px]">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-400/25 bg-[#07101f]/55 px-3 py-1.5 text-xs font-bold text-blue-200 backdrop-blur-md"><Sparkles className="h-3.5 w-3.5" />Dein Server. Ein System.</div>
            <h1 className="text-[43px] font-black leading-[1.01] tracking-[-.05em] text-white sm:text-[61px] lg:text-[68px]">
              <span className="text-blue-400">{BRAND}</span> bringt Ordnung in deinen Discord.
            </h1>
            <p className="mt-6 max-w-[540px] text-base leading-8 text-slate-300/75 sm:text-lg">Schutz, Tickets, Community und Automationen greifen zentral ineinander – eingerichtet in einem klaren Dashboard.</p>
            <div className="mt-8 flex flex-wrap gap-3"><a href={INVITE_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-3.5 text-sm font-black text-white shadow-[0_12px_35px_rgba(37,99,235,.28)] transition hover:-translate-y-0.5 hover:bg-blue-500"><Sparkles className="h-4 w-4" />Jetzt einladen<ArrowRight className="h-4 w-4" /></a><a href={SUPPORT_INVITE} target="_blank" rel="noreferrer" className="rounded-xl border border-white/15 bg-black/20 px-6 py-3.5 text-sm font-bold text-slate-200 backdrop-blur-md transition hover:border-blue-400/35 hover:text-white">Support Server</a></div>
            <div className="mt-8"><p className="mb-3 text-[10px] font-black uppercase tracking-[.24em] text-slate-400/60">Verfügbar auf</p><div className="flex flex-wrap gap-2">{LANGUAGES.map(([flag, language]) => <span key={language} className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs font-medium text-slate-300/70 backdrop-blur-md"><span className="text-sm">{flag}</span>{language}</span>)}</div></div>
          </div>
        </div>
      </section>

      <InteractiveHomeGlobe guilds={numbers?.guilds} users={numbers?.users} />
      <FeaturedServerMarquee />

      <section id="features" className="px-4 py-20 sm:px-6 sm:py-28"><div className="mx-auto max-w-[1200px]"><div className="max-w-2xl"><p className="text-xs font-black uppercase tracking-[.24em] text-blue-400">Alles verbunden</p><h2 className="mt-4 text-4xl font-black tracking-tight text-white sm:text-5xl">Ein Bot statt eines ganzen Bot-Ordners.</h2><p className="mt-5 text-base leading-7 text-zinc-400">Die wichtigsten Werkzeuge für Aufbau, Schutz und Betrieb deines Discord-Servers greifen ineinander.</p></div><div className="mt-12 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{FEATURES.map((feature,index)=><article key={feature.title} className={`group relative overflow-hidden rounded-2xl border border-white/[.07] bg-[#100d11] p-6 transition hover:border-blue-400/25 ${index===0||index===5 ? "lg:col-span-1" : ""}`}><div className="absolute -right-12 -top-12 h-32 w-32 rounded-full bg-blue-500/[.06] blur-2xl transition group-hover:bg-blue-500/10"/><span className="grid h-11 w-11 place-items-center rounded-xl border border-blue-400/20 bg-blue-500/10"><feature.icon className="h-5 w-5 text-blue-400"/></span><h3 className="mt-6 text-lg font-black text-white">{feature.title}</h3><p className="mt-3 text-sm leading-7 text-zinc-500">{feature.text}</p><span className="mt-6 inline-flex items-center gap-2 text-xs font-black text-blue-400">Im Dashboard verwalten<ArrowRight className="h-3.5 w-3.5"/></span></article>)}</div></div></section>

      <section id="premium" className="px-4 py-20 sm:px-6 sm:py-28"><div className="relative mx-auto max-w-[1200px] overflow-hidden rounded-[32px] border border-amber-400/20 bg-[#14130d] p-7 sm:p-12"><div className="pointer-events-none absolute -right-28 -top-40 h-96 w-96 rounded-full bg-amber-600/15 blur-3xl"/><div className="relative grid gap-10 lg:grid-cols-[1fr_.8fr] lg:items-center"><div><p className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-amber-400"><Crown className="h-4 w-4"/>Premium</p><h2 className="mt-5 text-4xl font-black tracking-tight text-white sm:text-5xl">Mehr Freiheit für deine wichtigsten Server.</h2><p className="mt-5 max-w-2xl text-base leading-8 text-zinc-400">Drei feste Serverplätze, höhere Limits, individuelles Bot-Design, erweiterte Backups, Statistiken und Premium-Werkzeuge.</p><Link href="/premium" className="mt-8 inline-flex items-center gap-2 rounded-xl bg-amber-600 px-6 py-3.5 text-sm font-black text-white hover:bg-amber-500">Premium ansehen<ArrowRight className="h-4 w-4"/></Link></div><div className="grid gap-3 sm:grid-cols-2">{["3 feste Serverplätze","Eigenes Bot-Design","Erweiterte Backups","Mehr Custom Commands","Server-Statistiken","User Pull für Owner"].map(item=><div key={item} className="flex items-center gap-3 rounded-xl border border-white/[.07] bg-black/20 p-4 text-sm font-bold text-zinc-300"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-amber-500/10"><Check className="h-4 w-4 text-amber-400"/></span>{item}</div>)}</div></div></div></section>

      <section id="faq" className="px-4 py-20 sm:px-6 sm:py-28"><div className="mx-auto grid max-w-[1100px] gap-12 lg:grid-cols-[.65fr_1fr]"><div><p className="text-xs font-black uppercase tracking-[.24em] text-blue-400">FAQ</p><h2 className="mt-4 text-4xl font-black tracking-tight text-white">Noch Fragen?</h2><p className="mt-4 text-sm leading-7 text-zinc-500">Die wichtigsten Antworten kurz und ohne Kleingedrucktes.</p><a href={SUPPORT_INVITE} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-2 text-sm font-black text-blue-400"><MessageSquareText className="h-4 w-4"/>Support kontaktieren</a></div><div className="rounded-2xl border border-white/[.07] bg-[#100d11] px-6">{FAQ.map(([q,a])=><FaqRow key={q} question={q} answer={a}/>)}</div></div></section>

      <section className="px-4 pb-24 sm:px-6"><div className="mx-auto flex max-w-[1200px] flex-col items-center rounded-[30px] border border-blue-400/20 bg-[radial-gradient(circle_at_50%_0%,rgba(96,165,250,.15),transparent_60%),#110d12] px-6 py-16 text-center"><Languages className="h-7 w-7 text-blue-400"/><h2 className="mt-5 text-3xl font-black text-white sm:text-4xl">Dein Server kann einfacher laufen.</h2><p className="mt-4 max-w-xl text-sm leading-7 text-zinc-400">Lade {BRAND} ein und richte genau die Module ein, die du brauchst.</p><a href={INVITE_URL} target="_blank" rel="noreferrer" className="mt-7 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-7 py-3.5 text-sm font-black text-white hover:bg-blue-500">Bot jetzt einladen<ArrowRight className="h-4 w-4"/></a></div></section>

      <style jsx global>{`
        @keyframes newHomeUniverseDrift {
          0%, 100% { background-position: 50% 50%; }
          50% { background-position: 56% 45%; }
        }
        @keyframes newHomeCometFlight {
          0% { transform: translate3d(-360px,-150px,0) rotate(24deg); opacity: 0; }
          8% { opacity: .9; }
          31%, 100% { transform: translate3d(1550px,650px,0) rotate(24deg); opacity: 0; }
        }
        .new-home-universe {
          background-size: 108% 108%;
          animation: newHomeUniverseDrift 26s ease-in-out infinite !important;
        }
        .new-home-comet {
          position: absolute;
          left: 0;
          top: 0;
          width: 220px;
          height: 2px;
          border-radius: 999px;
          background: linear-gradient(90deg,transparent,rgba(147,197,253,.18),rgba(255,255,255,.95));
          box-shadow: 0 0 10px rgba(96,165,250,.7);
          opacity: 0;
          animation: newHomeCometFlight 9s linear infinite !important;
        }
        .new-home-comet::after {
          content: "";
          position: absolute;
          right: -2px;
          top: -2px;
          width: 6px;
          height: 6px;
          border-radius: 999px;
          background: white;
          box-shadow: 0 0 16px 4px rgba(147,197,253,.8);
        }
        .new-home-comet-one { top: 5%; animation-delay: 1s !important; }
        .new-home-comet-two { top: 27%; animation-delay: 4.5s !important; animation-duration: 12s !important; }
        .new-home-comet-three { top: 49%; animation-delay: 8s !important; animation-duration: 15s !important; }
        .new-home .home-glass { border-color: rgba(96,165,250,.16) !important; background: linear-gradient(135deg,rgba(24,14,25,.86),rgba(12,10,13,.9)) !important; }
        body:has(.new-home) .dashboard-theme-toggle { display: none !important; }
        @media (max-width: 639px) {
          .new-home-universe {
            min-height: 690px;
            background-position: 64% center;
            background-size: cover;
            animation: none !important;
          }
          .new-home-comet { display: none; }
        }
      `}</style>
    </main>
  );
}

export default function LandingPage() {
  const [version, setVersion] = React.useState<HomepageVersion>("new");
  React.useEffect(() => {
    const saved = window.localStorage.getItem("homepage-version");
    if (saved === "classic" || saved === "new") setVersion(saved);
  }, []);
  const change = (next: HomepageVersion) => {
    window.localStorage.setItem("homepage-version", next);
    setVersion(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <>
      {version === "classic" ? <LegacyHomepage /> : <NewHomepage />}
      <div className="theme-filter-reset fixed bottom-5 left-4 z-[70] flex items-center rounded-full border border-blue-400/20 bg-[#151118]/95 p-1 shadow-2xl shadow-black/50 backdrop-blur-xl" aria-label="Homepage-Design wählen">
        <button type="button" onClick={() => change("classic")} aria-pressed={version === "classic"} className={`rounded-full px-3 py-2 text-[11px] font-black transition ${version === "classic" ? "bg-blue-600 text-white" : "text-zinc-500 hover:text-white"}`}>Klassisch</button>
        <button type="button" onClick={() => change("new")} aria-pressed={version === "new"} className={`rounded-full px-3 py-2 text-[11px] font-black transition ${version === "new" ? "bg-blue-600 text-white" : "text-zinc-500 hover:text-white"}`}>Neu</button>
      </div>
    </>
  );
}
