"use client";

import React from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  ArrowRight, BarChart3, Bot, Check, ChevronDown, Crown, Gift, Globe2,
  Grid2X2, Headphones, Languages, LockKeyhole, Menu, MessageSquareText,
  PanelsTopLeft, Server, ShieldCheck, Sparkles, Ticket, Users, X, Zap,
} from "lucide-react";
import { INVITE_URL } from "@/components/site-nav";
import { LegacyHomepage } from "@/components/home/legacy-homepage";
import { SUPPORT_INVITE } from "@/lib/legal";

const HomepageWorldMap = dynamic(
  () => import("@/components/home/homepage-world-map").then((mod) => mod.HomepageWorldMap),
  { ssr: false },
);

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

const LANGUAGES = ["Deutsch", "English", "العربية", "Türkçe", "Español", "Nederlands", "Français"];

const FAQ = [
  ["Ist der Bot kostenlos?", "Ja. Die wichtigsten Module kannst du kostenlos verwenden. Premium erweitert Limits und schaltet unter anderem Server-Design, User Pull und zusätzliche Backups frei."],
  ["Brauche ich Programmierkenntnisse?", "Nein. Du wählst deinen Server im Dashboard aus und stellst jedes Modul über verständliche Formulare ein."],
  ["Wie sicher ist mein Server?", "Kritische Aktionen sind serverseitig geschützt. Anti-Nuke, AutoMod, Protokolle und rollenbasierte Zugriffe helfen dabei, Risiken früh zu erkennen."],
  ["Kann ich nur einzelne Funktionen nutzen?", "Ja. Jedes Modul ist separat konfigurierbar. Du aktivierst nur, was dein Server wirklich braucht."],
];

function BrandMark() {
  return (
    <Link href="/" className="flex min-w-0 items-center gap-3" aria-label={`${BRAND} Startseite`}>
      <span className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl border border-fuchsia-400/25 bg-fuchsia-500/10 shadow-[0_0_24px_rgba(217,70,239,.18)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icon-192.png" alt="" className="h-full w-full object-cover" />
      </span>
      <span className="min-w-0">
        <strong className="block truncate text-sm font-black text-white">{BRAND}</strong>
        <span className="block text-[8px] font-black uppercase tracking-[.3em] text-fuchsia-400">All in one</span>
      </span>
    </Link>
  );
}

function NewNavigation() {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <div className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-6 sm:pt-5">
        <nav className="mx-auto flex h-[66px] max-w-[1320px] items-center rounded-2xl border border-white/10 bg-[#151118]/90 px-4 shadow-[0_18px_60px_rgba(0,0,0,.42)] backdrop-blur-2xl sm:px-6">
          <BrandMark />
          <div className="mx-auto hidden items-center gap-8 lg:flex">
            <Link href="#features" className="text-sm font-semibold text-zinc-400 transition hover:text-white">Features</Link>
            <Link href="#statistics" className="text-sm font-semibold text-zinc-400 transition hover:text-white">Statistiken</Link>
            <Link href="#premium" className="text-sm font-semibold text-zinc-400 transition hover:text-white">Premium</Link>
            <Link href="#faq" className="text-sm font-semibold text-zinc-400 transition hover:text-white">FAQ</Link>
          </div>
          <div className="ml-auto hidden items-center gap-2 sm:flex">
            <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-sm font-bold text-zinc-300 transition hover:border-fuchsia-400/25 hover:text-white"><Grid2X2 className="h-4 w-4" />Dashboard</Link>
            <a href={INVITE_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-fuchsia-600 px-5 py-2.5 text-sm font-black text-white shadow-[0_10px_30px_rgba(192,38,211,.24)] transition hover:bg-fuchsia-500">Bot einladen<ArrowRight className="h-4 w-4" /></a>
          </div>
          <button type="button" onClick={() => setOpen(true)} className="ml-auto grid h-10 w-10 place-items-center rounded-xl border border-white/10 text-zinc-300 sm:hidden" aria-label="Menü öffnen"><Menu className="h-5 w-5" /></button>
        </nav>
      </div>
      {open && <div className="fixed inset-0 z-[80] bg-black/75 p-3 backdrop-blur-md sm:hidden"><div className="ml-auto flex h-full w-[min(88vw,380px)] flex-col rounded-3xl border border-white/10 bg-[#151118] p-5"><div className="flex items-center"><BrandMark /><button onClick={() => setOpen(false)} className="ml-auto grid h-10 w-10 place-items-center rounded-xl border border-white/10 text-zinc-400"><X className="h-5 w-5" /></button></div><div className="mt-8 space-y-2">{[["Features","#features"],["Statistiken","#statistics"],["Premium","#premium"],["FAQ","#faq"]].map(([label,href])=><Link key={href} href={href} onClick={()=>setOpen(false)} className="block rounded-xl border border-white/[.06] px-4 py-4 text-base font-bold text-zinc-300">{label}</Link>)}</div><div className="mt-auto space-y-2"><Link href="/dashboard" className="block rounded-xl border border-white/10 px-4 py-3 text-center font-bold text-white">Dashboard</Link><a href={INVITE_URL} className="block rounded-xl bg-fuchsia-600 px-4 py-3 text-center font-black text-white">Bot einladen</a></div></div></div>}
    </>
  );
}

function FaqRow({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = React.useState(false);
  return <div className="border-b border-white/[.07]"><button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-5 py-5 text-left"><span className="font-bold text-white">{question}</span><ChevronDown className={`h-5 w-5 shrink-0 text-fuchsia-400 transition ${open ? "rotate-180" : ""}`} /></button>{open && <p className="max-w-3xl pb-5 text-sm leading-7 text-zinc-400">{answer}</p>}</div>;
}

function NewHomepage() {
  const [numbers, setNumbers] = React.useState<any>(null);
  React.useEffect(() => {
    let active = true;
    fetch("/api/bot/bot/numbers").then((res) => res.ok ? res.json() : null).then((data) => { if (active && data) setNumbers(data); }).catch(() => {});
    return () => { active = false; };
  }, []);
  const show = (value: unknown) => typeof value === "number" && value > 0 ? value.toLocaleString("de-DE") : "—";

  return (
    <main className="new-home min-h-screen overflow-x-clip bg-[#09090b] text-zinc-200 selection:bg-fuchsia-500/30">
      <NewNavigation />

      <section className="relative flex min-h-[790px] items-center overflow-hidden px-4 pb-16 pt-28 sm:px-6 lg:pt-32">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_73%_45%,rgba(192,38,211,.14),transparent_26%),radial-gradient(circle_at_12%_30%,rgba(236,72,153,.09),transparent_25%)]" />
        <div className="pointer-events-none absolute inset-0 opacity-[.16] [background-image:linear-gradient(rgba(255,255,255,.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.05)_1px,transparent_1px)] [background-size:72px_72px] [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" />
        <div className="relative mx-auto grid w-full max-w-[1320px] items-center gap-14 lg:grid-cols-[1.05fr_.95fr]">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-fuchsia-400/20 bg-fuchsia-500/[.08] px-3 py-1.5 text-xs font-bold text-fuchsia-300"><Sparkles className="h-3.5 w-3.5" />Dein Discord. Ein Bot. Volle Kontrolle.</div>
            <h1 className="max-w-3xl text-[45px] font-black leading-[.98] tracking-[-.055em] text-white sm:text-[65px] lg:text-[76px]">
              <span className="bg-gradient-to-r from-fuchsia-500 to-pink-500 bg-clip-text text-transparent">{BRAND}</span> ist dein ultimativer <span className="bg-gradient-to-r from-pink-500 to-fuchsia-400 bg-clip-text text-transparent">All-in-One Bot.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-base leading-8 text-zinc-400 sm:text-lg">Moderation, Tickets, Verifizierung, Logging, Community und Automationen in einem System. Weniger Bots, weniger Chaos, ein klares Dashboard.</p>
            <div className="mt-8 flex flex-wrap gap-3"><a href={INVITE_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-fuchsia-600 px-6 py-3.5 text-sm font-black text-white shadow-[0_12px_35px_rgba(192,38,211,.28)] transition hover:-translate-y-0.5 hover:bg-fuchsia-500"><Sparkles className="h-4 w-4" />Jetzt einladen<ArrowRight className="h-4 w-4" /></a><a href={SUPPORT_INVITE} target="_blank" rel="noreferrer" className="rounded-xl border border-white/10 bg-white/[.025] px-6 py-3.5 text-sm font-bold text-zinc-300 transition hover:border-fuchsia-400/25 hover:text-white">Support Server</a></div>
            <div className="mt-8"><p className="mb-3 text-[10px] font-black uppercase tracking-[.24em] text-zinc-600">Verfügbar auf</p><div className="flex max-w-2xl flex-wrap gap-2">{LANGUAGES.map((language) => <span key={language} className="rounded-lg border border-white/[.06] bg-white/[.025] px-3 py-1.5 text-xs font-medium text-zinc-500">{language}</span>)}</div></div>
          </div>

          <div className="relative hidden min-h-[560px] lg:block">
            <div className="absolute left-1/2 top-1/2 h-[390px] w-[390px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-fuchsia-500/15 bg-fuchsia-500/[.025] shadow-[0_0_120px_rgba(192,38,211,.16)]"><div className="absolute inset-10 rounded-full border border-dashed border-fuchsia-400/20" /><div className="absolute inset-24 grid place-items-center rounded-[52px] border border-fuchsia-400/25 bg-[#171019] shadow-[0_0_70px_rgba(217,70,239,.18)]"><img src="/icon-192.png" alt="" className="h-28 w-28 rounded-3xl object-cover" /></div></div>
            {[
              ["Moderation", ShieldCheck, "left-0 top-16"], ["Ticket System", Ticket, "right-0 top-28"], ["Leveling", BarChart3, "left-6 bottom-24"], ["Giveaways", Gift, "right-6 bottom-14"],
            ].map(([label, Icon, pos]) => { const FeatureIcon = Icon as React.ElementType; return <div key={String(label)} className={`absolute ${pos} flex min-w-48 items-center gap-3 rounded-2xl border border-fuchsia-400/20 bg-[#171219]/90 p-4 shadow-[0_18px_55px_rgba(0,0,0,.5)] backdrop-blur-xl`}><span className="grid h-11 w-11 place-items-center rounded-xl border border-fuchsia-400/20 bg-fuchsia-500/10"><FeatureIcon className="h-5 w-5 text-fuchsia-400" /></span><div><p className="text-sm font-black text-white">{String(label)}</p><p className="mt-0.5 text-[10px] uppercase tracking-widest text-zinc-600">Live Modul</p></div></div>; })}
          </div>
        </div>
      </section>

      <section id="statistics" className="border-y border-white/[.06] bg-[#0d0b0e] px-4 py-10 sm:px-6"><div className="mx-auto grid max-w-[1200px] grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/[.07] bg-white/[.07] lg:grid-cols-4">{[[Server,"Server",numbers?.guilds],[Users,"Nutzer",numbers?.users],[Bot,"Befehle",numbers?.commands],[Grid2X2,"Module",numbers?.modules]].map(([Icon,label,value])=>{const StatIcon=Icon as React.ElementType;return <div key={String(label)} className="bg-[#100d11] p-6 sm:p-8"><StatIcon className="h-5 w-5 text-fuchsia-400"/><p className="mt-5 text-3xl font-black tabular-nums text-white">{show(value)}</p><p className="mt-1 text-xs font-bold uppercase tracking-widest text-zinc-600">{String(label)}</p></div>})}</div></section>

      <section id="features" className="px-4 py-20 sm:px-6 sm:py-28"><div className="mx-auto max-w-[1200px]"><div className="max-w-2xl"><p className="text-xs font-black uppercase tracking-[.24em] text-fuchsia-400">Alles verbunden</p><h2 className="mt-4 text-4xl font-black tracking-tight text-white sm:text-5xl">Ein Bot statt eines ganzen Bot-Ordners.</h2><p className="mt-5 text-base leading-7 text-zinc-400">Die wichtigsten Werkzeuge für Aufbau, Schutz und Betrieb deines Discord-Servers greifen ineinander.</p></div><div className="mt-12 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{FEATURES.map((feature,index)=><article key={feature.title} className={`group relative overflow-hidden rounded-2xl border border-white/[.07] bg-[#100d11] p-6 transition hover:border-fuchsia-400/25 ${index===0||index===5 ? "lg:col-span-1" : ""}`}><div className="absolute -right-12 -top-12 h-32 w-32 rounded-full bg-fuchsia-500/[.06] blur-2xl transition group-hover:bg-fuchsia-500/10"/><span className="grid h-11 w-11 place-items-center rounded-xl border border-fuchsia-400/20 bg-fuchsia-500/10"><feature.icon className="h-5 w-5 text-fuchsia-400"/></span><h3 className="mt-6 text-lg font-black text-white">{feature.title}</h3><p className="mt-3 text-sm leading-7 text-zinc-500">{feature.text}</p><span className="mt-6 inline-flex items-center gap-2 text-xs font-black text-fuchsia-400">Im Dashboard verwalten<ArrowRight className="h-3.5 w-3.5"/></span></article>)}</div></div></section>

      <div className="pink-map"><HomepageWorldMap tone="pink" /></div>

      <section id="premium" className="px-4 py-20 sm:px-6 sm:py-28"><div className="relative mx-auto max-w-[1200px] overflow-hidden rounded-[32px] border border-fuchsia-400/20 bg-[#130d14] p-7 sm:p-12"><div className="pointer-events-none absolute -right-28 -top-40 h-96 w-96 rounded-full bg-fuchsia-600/15 blur-3xl"/><div className="relative grid gap-10 lg:grid-cols-[1fr_.8fr] lg:items-center"><div><p className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-fuchsia-400"><Crown className="h-4 w-4"/>Premium</p><h2 className="mt-5 text-4xl font-black tracking-tight text-white sm:text-5xl">Mehr Freiheit für deine wichtigsten Server.</h2><p className="mt-5 max-w-2xl text-base leading-8 text-zinc-400">Drei feste Serverplätze, höhere Limits, individuelles Bot-Design, erweiterte Backups, Statistiken und Premium-Werkzeuge.</p><Link href="/premium" className="mt-8 inline-flex items-center gap-2 rounded-xl bg-fuchsia-600 px-6 py-3.5 text-sm font-black text-white hover:bg-fuchsia-500">Premium ansehen<ArrowRight className="h-4 w-4"/></Link></div><div className="grid gap-3 sm:grid-cols-2">{["3 feste Serverplätze","Eigenes Bot-Design","Erweiterte Backups","Mehr Custom Commands","Server-Statistiken","User Pull für Owner"].map(item=><div key={item} className="flex items-center gap-3 rounded-xl border border-white/[.07] bg-black/20 p-4 text-sm font-bold text-zinc-300"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-fuchsia-500/10"><Check className="h-4 w-4 text-fuchsia-400"/></span>{item}</div>)}</div></div></div></section>

      <section id="faq" className="px-4 py-20 sm:px-6 sm:py-28"><div className="mx-auto grid max-w-[1100px] gap-12 lg:grid-cols-[.65fr_1fr]"><div><p className="text-xs font-black uppercase tracking-[.24em] text-fuchsia-400">FAQ</p><h2 className="mt-4 text-4xl font-black tracking-tight text-white">Noch Fragen?</h2><p className="mt-4 text-sm leading-7 text-zinc-500">Die wichtigsten Antworten kurz und ohne Kleingedrucktes.</p><a href={SUPPORT_INVITE} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-2 text-sm font-black text-fuchsia-400"><MessageSquareText className="h-4 w-4"/>Support kontaktieren</a></div><div className="rounded-2xl border border-white/[.07] bg-[#100d11] px-6">{FAQ.map(([q,a])=><FaqRow key={q} question={q} answer={a}/>)}</div></div></section>

      <section className="px-4 pb-24 sm:px-6"><div className="mx-auto flex max-w-[1200px] flex-col items-center rounded-[30px] border border-fuchsia-400/20 bg-[radial-gradient(circle_at_50%_0%,rgba(217,70,239,.15),transparent_60%),#110d12] px-6 py-16 text-center"><Languages className="h-7 w-7 text-fuchsia-400"/><h2 className="mt-5 text-3xl font-black text-white sm:text-4xl">Dein Server kann einfacher laufen.</h2><p className="mt-4 max-w-xl text-sm leading-7 text-zinc-400">Lade {BRAND} ein und richte genau die Module ein, die du brauchst.</p><a href={INVITE_URL} target="_blank" rel="noreferrer" className="mt-7 inline-flex items-center gap-2 rounded-xl bg-fuchsia-600 px-7 py-3.5 text-sm font-black text-white hover:bg-fuchsia-500">Bot jetzt einladen<ArrowRight className="h-4 w-4"/></a></div></section>

      <style jsx global>{`
        .new-home .home-glass { border-color: rgba(217,70,239,.16) !important; background: linear-gradient(135deg,rgba(24,14,25,.86),rgba(12,10,13,.9)) !important; }
        .pink-map section { padding-top: 3rem; padding-bottom: 3rem; }
        .pink-map [class*="bg-[#080b14]"] { background-color: #100d11 !important; }
        body:has(.new-home) .dashboard-theme-toggle { display: none !important; }
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
      <div className="theme-filter-reset fixed bottom-5 left-4 z-[70] flex items-center rounded-full border border-fuchsia-400/20 bg-[#151118]/95 p-1 shadow-2xl shadow-black/50 backdrop-blur-xl" aria-label="Homepage-Design wählen">
        <button type="button" onClick={() => change("classic")} aria-pressed={version === "classic"} className={`rounded-full px-3 py-2 text-[11px] font-black transition ${version === "classic" ? "bg-fuchsia-600 text-white" : "text-zinc-500 hover:text-white"}`}>Klassisch</button>
        <button type="button" onClick={() => change("new")} aria-pressed={version === "new"} className={`rounded-full px-3 py-2 text-[11px] font-black transition ${version === "new" ? "bg-fuchsia-600 text-white" : "text-zinc-500 hover:text-white"}`}>Neu</button>
      </div>
    </>
  );
}
