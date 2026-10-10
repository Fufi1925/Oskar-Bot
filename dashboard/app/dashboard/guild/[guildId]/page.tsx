"use client";

/** Server overview, setup progress, module cards and configuration transfer. */

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity, ArrowRight, BarChart4, Bot, Check, ChevronRight, Crown, FileJson,
  FileText, Hash, Link2, Loader2, Mic, Settings, Shield, ShieldCheck,
  SmilePlus, Sparkles, Ticket, UserCheck, Users, Volume2, Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ConfigTransferPanel } from "@/components/dashboard/config-transfer-panel";
import { HistoryCharts } from "@/components/dashboard/history-charts";

const MODULE_ICONS: Record<string, any> = {
  welcome: SmilePlus,
  automod: ShieldCheck,
  antinuke: Shield,
  verification: UserCheck,
  leveling: BarChart4,
  tickets: Ticket,
  logging: FileText,
  autorole: Bot,
  reactionroles: Zap,
  vanityroles: Sparkles,
  customroles: Sparkles,
  invcrole: Volume2,
  j2c: Mic,
  nickname: UserCheck,
  noprefix: Hash,
  tracking: Link2,
  counting: Hash,
  design: Sparkles,
  serverstats: BarChart4,
  honeypot: ShieldCheck,
  userpull: Users,
  emergency: Shield,
  jail: Shield,
  nightmode: Activity,
  applications: FileText,
  leave: Users,
  joindm: UserCheck,
  giveaways: Sparkles,
  booster: Sparkles,
  notify: Volume2,
  autoreact: SmilePlus,
  autoresponder: Bot,
  customcommands: Hash,
  anonchat: Shield,
  music: Volume2,
  sticky: FileText,
  teamlist: Users,
  teamupdate: UserCheck,
  supportqueue: Mic,
};

/**
 * Womit man anfangen sollte.
 *
 * Kleinere Zahl heißt wichtiger. Begrüßung und Schutz zuerst — sie
 * wirken vom ersten Tag an; Spitznamen und Vanity-Rollen sind
 * Feinschliff. Module ohne Eintrag landen hinten.
 */
const WICHTIGKEIT: Record<string, number> = {
  antinuke: 0,
  automod: 1,
  verification: 2,
  welcome: 3,
  logging: 4,
  tickets: 5,
  autorole: 6,
  leveling: 7,
  reactionroles: 8,
  j2c: 9,
  counting: 10,
  tracking: 11,
  customroles: 12,
  invcrole: 13,
  noprefix: 14,
  vanityroles: 15,
  nickname: 16,
  honeypot: 17,
  userpull: 18,
  emergency: 19,
  jail: 20,
  nightmode: 21,
  applications: 22,
  leave: 23,
  joindm: 24,
  giveaways: 25,
  booster: 26,
  notify: 27,
  autoreact: 28,
  autoresponder: 29,
  customcommands: 30,
  anonchat: 31,
  music: 32,
  sticky: 33,
  teamlist: 34,
  teamupdate: 35,
  supportqueue: 36,
  serverstats: 37,
  design: 38,
};

/** Ein kurzer Satz, was das Modul bringt. */
const WOZU: Record<string, string> = {
  antinuke: "Schützt vor Massenlöschungen und feindlichen Bots.",
  automod: "Filtert Spam, Links und Beleidigungen automatisch.",
  verification: "Hält Raids fern, bevor sie den Server erreichen.",
  welcome: "Begrüßt neue Mitglieder mit Nachricht und Bild.",
  logging: "Schreibt mit, wer was wann geändert hat.",
  tickets: "Support-Anfragen in eigenen Kanälen, geordnet.",
  autorole: "Gibt neuen Mitgliedern automatisch eine Rolle.",
  leveling: "Belohnt aktive Mitglieder mit XP und Rängen.",
  reactionroles: "Rollen per Klick auf ein Emoji.",
  j2c: "Temporäre Sprachkanäle, die sich selbst aufräumen.",
  counting: "Gemeinsam zählen — ein Spiel für den ganzen Server.",
  tracking: "Zeigt, wer wen eingeladen hat.",
  customroles: "Mitglieder gestalten ihre eigene Rolle.",
  invcrole: "Rolle, solange jemand im Sprachkanal ist.",
  noprefix: "Befehle ohne Präfix für ausgewählte Personen.",
  vanityroles: "Rolle für alle mit deinem Link im Status.",
  nickname: "Regeln für Spitznamen, etwa ein fester Vorsatz.",
  design: "Passt Farben und Erscheinungsbild des Dashboards an.",
  serverstats: "Zeigt aktuelle Serverzahlen in automatisch gepflegten Kanälen.",
  honeypot: "Erkennt verdächtige Bots über einen geschützten Köderkanal.",
  userpull: "Verwaltet ausdrücklich autorisierte Mitglieder für User Pull.",
  emergency: "Bereitet Rollen und Berechtigungen für einen Notfall vor.",
  jail: "Isoliert Regelbrecher, ohne sie direkt zu bannen.",
  nightmode: "Schließt ausgewählte Kanäle automatisch über Nacht.",
  applications: "Erstellt strukturierte Bewerbungsformulare für dein Team.",
  leave: "Verabschiedet Mitglieder beim Verlassen des Servers.",
  joindm: "Sendet neuen Mitgliedern automatisch eine private Nachricht.",
  giveaways: "Veranstaltet und verwaltet Giveaways direkt auf Discord.",
  booster: "Belohnt Server-Booster automatisch mit Rollen und Nachrichten.",
  notify: "Benachrichtigt über neue Videos und Livestreams.",
  autoreact: "Reagiert automatisch auf festgelegte Nachrichten.",
  autoresponder: "Antwortet automatisch auf passende Begriffe und Sätze.",
  customcommands: "Erstellt eigene Befehle und Antworten für den Server.",
  anonchat: "Ermöglicht moderierten anonymen Austausch in ausgewählten Kanälen.",
  music: "Konfiguriert Musikkanal, Wiedergabe und eigene Playlists.",
  sticky: "Hält wichtige Nachrichten dauerhaft am Kanalende sichtbar.",
  teamlist: "Zeigt eine automatisch aktualisierte Übersicht deines Teams.",
  teamupdate: "Veröffentlicht Änderungen und Neuigkeiten aus dem Team.",
  supportqueue: "Organisiert wartende Nutzer in einem Support-Sprachkanal.",
};

const CARD = "rounded-2xl border border-slate-800 cloudtix-workspace-card bg-[#131318]";

interface ModuleState {
  key: string;
  label: string;
  configured: boolean;
  entries: number;
  path: string;
}

interface StatusPayload {
  prefix: string;
  modules: ModuleState[];
  active_count: number;
  total_count: number;
  completion: number;
  guild: {
    member_count: number;
    channel_count: number;
    role_count: number;
    bot_count: number;
    boost_level: number;
    boost_count: number;
    verification_level: string;
    created_at: number;
    owner_id: string | null;
  };
}

function Zeile({ mod, guildId, fertig }: { mod: ModuleState; guildId: string; fertig: boolean }) {
  useWebsiteLocale();
  const Icon = MODULE_ICONS[mod.key] || Settings;
  return <Link href={`/dashboard/guild/${guildId}/${mod.path}`} className="cloudtix-workspace-module-card"><Icon size={19} /><div><strong>{mod.label}</strong><p>{WOZU[mod.key] || "Im Dashboard einstellbar."}</p><small data-active={String(fertig)}>{fertig ? `Eingerichtet${mod.entries > 0 ? ` · ${mod.entries} ${mod.entries === 1 ? "Eintrag" : "Einträge"}` : ""}` : "Einrichtung öffnen"}</small></div>{fertig ? <Check size={14} className="text-emerald-300" /> : <ArrowRight size={14} />}</Link>;
}

export default function GuildOverviewPage({
  params,
}: {
  params: { guildId: string };
}) {
  useWebsiteLocale();
  const [data, setData] = useState<StatusPayload | null>(null);
  const [premium, setPremium] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview" | "backup">("overview");
  const [alleOffenen, setAlleOffenen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    Promise.all([
      api.getModuleStatus(params.guildId).then(setData),
      api.getServerPremium(params.guildId).then(setPremium),
    ]).catch(() => setData(null)).finally(() => setLoading(false));
  }, [params.guildId]);

  const sortiert = useMemo(() => {
    const rang = (m: ModuleState) => WICHTIGKEIT[m.key] ?? 99;
    // Nicht `module` nennen: der Name ist im Bundle reserviert und
    // Next bricht den Build ab (no-assign-module-variable).
    const liste = data?.modules || [];
    return {
      aktiv: liste.filter((m) => m.configured).sort((a, b) => rang(a) - rang(b)),
      offen: liste.filter((m) => !m.configured).sort((a, b) => rang(a) - rang(b)),
    };
  }, [data]);

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={cn(CARD, "p-8 text-center")}>
        <p className="text-[15px] text-slate-300">
          Der Status dieses Servers ließ sich nicht laden.
        </p>
        <p className="mt-2 text-[13px] text-slate-500">
          Der Bot antwortet gerade nicht. Die Einstellungen sind trotzdem
          gespeichert — versuch es in einem Moment erneut.
        </p>
      </div>
    );
  }

  const naechste = sortiert.offen.slice(0, 3);
  const restOffen = sortiert.offen.slice(3);

  const kennzahlen = [
    { label: "Mitglieder", wert: data.guild.member_count.toLocaleString(websiteLocale()), icon: Users },
    { label: "Kanäle", wert: data.guild.channel_count, icon: Hash },
    { label: "Rollen", wert: data.guild.role_count, icon: Shield },
    { label: "Bots", wert: data.guild.bot_count, icon: Bot },
  ];

  const completion = Math.max(0, Math.min(100, data.completion));
  const matches = (mod: ModuleState) => `${mod.label} ${WOZU[mod.key] || ""}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const activeModules = sortiert.aktiv.filter(matches);
  const openModules = (query.trim() ? sortiert.offen : restOffen).filter(matches);

  return <div className="cloudtix-workspace-server-overview">
    <header className="cloudtix-workspace-page-heading"><div><p className="cloudtix-workspace-eyebrow">DEINE SERVERZENTRALE</p><h1>Alles im Überblick.</h1><p>Sieh, wie deine Community wächst, und richte ihre nächsten Module ein.</p></div><div className="cloudtix-workspace-segmented">{([["overview", "Übersicht", Activity], ["backup", "Konfiguration", FileJson]] as const).map(([id, label, Icon]) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}><Icon size={14} />{label}</button>)}</div></header>
    {tab === "backup" ? <ConfigTransferPanel guildId={params.guildId} /> : <>
      <section className="cloudtix-workspace-stat-grid" aria-label="Deine Serverzahlen">{kennzahlen.map(metric => <div key={metric.label} className="cloudtix-workspace-stat"><metric.icon size={18} /><span>{metric.label}</span><strong>{metric.wert}</strong><small>Auf deinem Discord-Server</small></div>)}</section>
      <div className="cloudtix-workspace-setup-grid">
        <section className="cloudtix-workspace-setup-card"><p className="cloudtix-workspace-eyebrow">DEINE EINRICHTUNG</p><h2>Dein Server nimmt Form an.</h2><p>CloudTIX ist so vielseitig wie deine Community. Wähle die Module, die zu ihr passen.</p><div className="cloudtix-workspace-setup-progress"><strong>{Math.round(completion)}%</strong><span>{data.active_count} von {data.total_count} Modulen eingerichtet</span></div><div className="cloudtix-workspace-progress-track" role="progressbar" aria-label="Einrichtung" aria-valuenow={completion} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${completion}%` }} /></div></section>
        <section className="cloudtix-workspace-setup-card"><p className="cloudtix-workspace-eyebrow">DEIN SERVER-TARIF</p><Crown size={24} className="text-slate-300" /><h2>{premium?.frozen ? "Premium pausiert" : premium?.active ? "Premium aktiv" : "CloudTIX Free"}</h2><p>Verwalte den Premiumstatus und die verfügbaren Funktionen für diesen Server.</p><Link href={`/dashboard/guild/${params.guildId}/premium`} className="cloudtix-workspace-action is-secondary mt-5">Premium verwalten<ArrowRight size={14} /></Link></section>
      </div>
      <div className="cloudtix-workspace-note flex flex-wrap items-center gap-x-6 gap-y-2"><span>Präfix <code className="ml-2 text-slate-200">{data.prefix}</code></span><span>Sicherheitsstufe <strong className="ml-2 font-medium capitalize text-slate-300">{data.guild.verification_level}</strong></span>{data.guild.boost_level > 0 && <span>Boost-Stufe <strong className="ml-2 font-medium text-slate-300">{data.guild.boost_level} · {data.guild.boost_count} Boosts</strong></span>}</div>
      {naechste.length > 0 && <section><div className="cloudtix-workspace-section-heading"><div><h2>Deine nächsten Schritte</h2><p>Starte mit diesen Modulen und ergänze später den Rest.</p></div></div><div className="grid gap-4 lg:grid-cols-3">{naechste.map(mod => <Zeile key={mod.key} mod={mod} guildId={params.guildId} fertig={false} />)}</div></section>}
      <HistoryCharts guildId={params.guildId} />
      <section><div className="cloudtix-workspace-section-heading"><div><h2>Deine Module</h2><p>Öffne eine Einrichtung oder passe ein bestehendes Modul an.</p></div><label className="relative w-full sm:w-64"><Settings size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><input value={query} onChange={event => setQuery(event.target.value)} aria-label="Server-Module suchen" placeholder="Modul suchen …" className="w-full rounded-xl border border-white/10 py-2.5 pl-9 pr-3" /></label></div>
        {activeModules.length > 0 && <div className="mb-6"><p className="cloudtix-workspace-eyebrow">EINGERICHTET · {activeModules.length}</p><div className="cloudtix-workspace-module-grid">{activeModules.map(mod => <Zeile key={mod.key} mod={mod} guildId={params.guildId} fertig />)}</div></div>}
        {openModules.length > 0 && <div><p className="cloudtix-workspace-eyebrow">{query.trim() ? "VERFÜGBARE MODULE" : "WEITERE MÖGLICHKEITEN"} · {openModules.length}</p><div className="cloudtix-workspace-module-grid">{(alleOffenen || query.trim() ? openModules : openModules.slice(0, 6)).map(mod => <Zeile key={mod.key} mod={mod} guildId={params.guildId} fertig={false} />)}</div>{!query.trim() && openModules.length > 6 && <button type="button" onClick={() => setAlleOffenen(current => !current)} className="cloudtix-workspace-action is-secondary mt-4">{alleOffenen ? "Weniger anzeigen" : `Alle ${openModules.length} Module anzeigen`}</button>}</div>}
        {query.trim() && !activeModules.length && !openModules.length && <div className="cloudtix-workspace-empty"><Settings size={24} /><h2>Kein passendes Modul</h2><p>Versuche einen anderen Namen oder eine Funktion.</p><button type="button" onClick={() => setQuery("")} className="cloudtix-workspace-action is-secondary">Suche zurücksetzen</button></div>}
      </section>
    </>}
  </div>;
}
