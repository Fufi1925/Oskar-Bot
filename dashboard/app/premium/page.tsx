"use client";

import Link from "next/link";
import { ArrowRight, BadgeCheck, Bot, Check, Clock3, Crown, Database, LockKeyhole, RefreshCw, Server, ShieldCheck, Sparkles, Users } from "lucide-react";
import { SiteNav } from "@/components/site-nav";
import { SUPPORT_INVITE } from "@/lib/legal";
import { cn } from "@/lib/utils";

const PLANS = [
  { days: 30, title: "30 Tage", text: "Zum Kennenlernen oder für ein einzelnes Projekt." },
  { days: 90, title: "90 Tage", text: "Mehr Zeit für den vollständigen Serverbetrieb.", popular: true },
  { days: 365, title: "365 Tage", text: "Ein ganzes Jahr Premium auf drei festen Servern." },
];

const FEATURES = [
  { icon: Bot, title: "Server-Design", text: "Eigener Bot-Name, Server-Avatar und Banner." },
  { icon: Database, title: "Erweiterte Backups", text: "Bis zu zehn Backups, Automatik und Nachrichten." },
  { icon: Users, title: "Server-Stats", text: "Aktuelle Mitgliederwerte als automatisch gepflegte Kanäle." },
  { icon: RefreshCw, title: "User Pull", text: "Das vollständige, owner-geschützte Pull-System inklusive guilds.join." },
  { icon: Sparkles, title: "Ticket-KI", text: "KI-Assistent und Serverwissen auf ausdrücklich freigeschalteten Servern." },
  { icon: ShieldCheck, title: "Premiumbereiche", text: "Speedrun, Premium-Vorlagen, höhere Limits und kommende Funktionen." },
];

const FAQ = [
  ["Wofür gilt Premium?", "Premium gehört zu deinem Discord-Konto. Du löst anschließend bis zu drei feste Serverplätze ein. Nur diese Server erhalten Premiumfunktionen."],
  ["Kann ich einen belegten Platz wechseln?", "Nein. Ein eingelöster Platz bleibt während der gesamten Laufzeit fest mit diesem Server verbunden."],
  ["Wer darf Premiumfunktionen einstellen?", "Jeder Nutzer mit normalen Dashboard-Rechten des Premiumservers. Funktionen wie User Pull bleiben weiterhin dem tatsächlichen Serverinhaber vorbehalten."],
  ["Wie funktioniert der Kauf?", "Du sendest im Dashboard eine Anfrage für 30, 90 oder 365 Tage. Ein Admin prüft und bestätigt sie anschließend manuell."],
  ["Was passiert nach Ablauf?", "Pro Server wählst du vorher: bestehende Premiumfunktionen eingefroren weiterlaufen lassen oder vollständig deaktivieren. Einstellungen und Daten werden nie gelöscht."],
  ["Bekomme ich eine Discord-Rolle?", "Ja. Ein aktives Premium-Konto erhält das Premium-Badge im Dashboard und die Premiumrolle auf dem Support-Discord."],
];

export default function PremiumPage() {
  return <div className="min-h-screen bg-[#09090c] text-white">
    <SiteNav />
    <main>
      <section className="relative overflow-hidden border-b border-slate-800">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-10%,rgba(251,191,36,0.18),transparent_45%)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-16 text-center sm:px-6 sm:py-24">
          <span className="inline-flex items-center gap-2 rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1.5 text-xs font-bold text-amber-300"><Crown className="h-3.5 w-3.5"/>Ein Konto · drei feste Premiumserver</span>
          <h1 className="mx-auto mt-6 max-w-4xl text-4xl font-black tracking-tight sm:text-6xl">Premium dort, wo dein Server es wirklich braucht.</h1>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-400 sm:text-lg">Wähle ein Laufzeitpaket, lass deine Anfrage bestätigen und verteile drei feste Serverplätze. Transparent, servergebunden und ohne Verlust deiner Konfigurationen.</p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Link href="/dashboard/premium" className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-400 px-6 py-3.5 text-sm font-black text-black hover:brightness-110">Kaufanfrage starten<ArrowRight className="h-4 w-4"/></Link><a href={SUPPORT_INVITE} target="_blank" rel="noreferrer" className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-[#131318] px-6 py-3.5 text-sm font-bold text-slate-200 hover:border-slate-600">Fragen im Support klären</a></div>
          <div className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-3"><Mini icon={Crown} value="3" label="feste Serverplätze"/><Mini icon={Clock3} value="30 / 90 / 365" label="Tage Laufzeit"/><Mini icon={LockKeyhole} value="0" label="gelöschte Einstellungen"/></div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6"><div className="max-w-2xl"><p className="text-xs font-black uppercase tracking-[.2em] text-amber-300">Laufzeit wählen</p><h2 className="mt-2 text-3xl font-black">Drei klare Pakete</h2><p className="mt-2 text-slate-400">Noch keine automatische Zahlung: Jede Anfrage wird vom Team geprüft. Nach der Bestätigung startet deine Laufzeit.</p></div><div className="mt-7 grid gap-4 md:grid-cols-3">{PLANS.map(plan=><article key={plan.days} className={cn("relative rounded-3xl border bg-[#131318] p-6",plan.popular?"border-amber-400/40":"border-slate-800")}>{plan.popular&&<span className="absolute -top-3 left-6 rounded-full bg-amber-400 px-3 py-1 text-[11px] font-black text-black">Beliebteste Laufzeit</span>}<p className="text-sm font-bold text-amber-300">Premium-Paket</p><p className="mt-2 text-3xl font-black">{plan.title}</p><p className="mt-3 min-h-12 text-sm leading-6 text-slate-400">{plan.text}</p><ul className="mt-5 space-y-2 text-sm text-slate-300"><Item>Premium-Badge und Supportrolle</Item><Item>Drei feste Serverplätze</Item><Item>Alle aktiven Premiumfunktionen</Item></ul><Link href="/dashboard/premium" className={cn("mt-6 flex items-center justify-center rounded-xl py-3 text-sm font-black",plan.popular?"bg-amber-400 text-black":"border border-slate-700 text-white")}>Dieses Paket anfragen</Link></article>)}</div></section>

      <section className="border-y border-slate-800 bg-[#0d0d11]"><div className="mx-auto max-w-6xl px-4 py-14 sm:px-6"><p className="text-xs font-black uppercase tracking-[.2em] text-violet-300">Enthalten</p><h2 className="mt-2 text-3xl font-black">Premiumfunktionen auf deinen drei Servern</h2><div className="mt-7 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{FEATURES.map(({icon:Icon,title,text})=><article key={title} className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-500/10"><Icon className="h-5 w-5 text-violet-300"/></span><h3 className="mt-4 font-black">{title}</h3><p className="mt-1 text-sm leading-6 text-slate-400">{text}</p></article>)}</div></div></section>

      <section className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[.8fr_1.2fr]"><div><p className="text-xs font-black uppercase tracking-[.2em] text-emerald-300">Sicherer Ablauf</p><h2 className="mt-2 text-3xl font-black">Deine Daten bleiben bestehen.</h2><p className="mt-3 leading-7 text-slate-400">Vor Ablauf entscheidest du für jeden Premiumserver separat. Beim Einfrieren läuft die bestehende Einrichtung weiter, kann aber nicht verändert werden. Beim Deaktivieren stoppen Premiumfunktionen. In beiden Fällen bleiben Einstellungen und gespeicherte Inhalte erhalten.</p><div className="mt-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.06] p-4 text-sm text-emerald-200"><BadgeCheck className="mr-2 inline h-4 w-4"/>Premium-Ablauf löscht niemals deine Konfiguration.</div></div><div className="grid gap-3 sm:grid-cols-2">{FAQ.map(([q,a])=><article key={q} className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><h3 className="font-black">{q}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{a}</p></article>)}</div></section>
    </main>
  </div>;
}
function Mini({icon:Icon,value,label}:{icon:any,value:string,label:string}){return <div className="rounded-2xl border border-slate-800 bg-black/20 p-4"><Icon className="mx-auto h-4 w-4 text-amber-300"/><p className="mt-2 text-lg font-black">{value}</p><p className="text-xs text-slate-500">{label}</p></div>}
function Item({children}:{children:React.ReactNode}){return <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"/>{children}</li>}
