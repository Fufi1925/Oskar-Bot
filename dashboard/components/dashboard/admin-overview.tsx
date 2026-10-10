"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React from "react";
import {
  Activity, ArrowRight, Bot, CreditCard, FileText, Lightbulb,
  Server, ShieldCheck, Users,
} from "lucide-react";

export type AdminOverviewData = {
  period_hours: number;
  captured_at: number;
  baseline_at: number;
  totals: { servers: number; users: number; premium_active: number };
  new: {
    servers: number;
    users: number;
    firewall_blocks: number;
    premium_purchases: number;
    ideas: number;
    applications: number;
  };
  pending: { premium_purchases: number; ideas: number; applications: number };
  system: { api_latency_ms: number | null; ready: boolean; guilds_available: boolean };
};

type OpenTab = (tab: string) => void;
const format = (value: number | undefined) => value == null ? "—" : value.toLocaleString(websiteLocale());

export function AdminOverview({ data, loading, onOpen }: { data: AdminOverviewData | null; loading: boolean; onOpen: OpenTab }) {
  useWebsiteLocale();
  const totals = [
    { label: "Verbundene Server", value: data?.totals.servers, icon: Server, tab: "servers", note: "Server-Verwaltung öffnen" },
    { label: "Erreichte Nutzer", value: data?.totals.users, icon: Users, tab: "dashusers", note: "Dashboard-Konten ansehen" },
    { label: "Premium-Konten", value: data?.totals.premium_active, icon: CreditCard, tab: "premium", note: "Premium verwalten" },
  ];
  const activity = [
    { label: "Neue Server", value: data?.new.servers, note: "Netto-Wachstum", icon: Server, tab: "servers" },
    { label: "Neue Nutzer", value: data?.new.users, note: "Netto-Wachstum", icon: Users, tab: "dashusers" },
    { label: "Abgewehrte Anfragen", value: data?.new.firewall_blocks, note: "Durch die Firewall blockiert", icon: ShieldCheck, tab: "firewall" },
    { label: "Premium-Anfragen", value: data?.new.premium_purchases, note: `${format(data?.pending.premium_purchases)} noch offen`, icon: CreditCard, tab: "premium" },
    { label: "Neue Ideen", value: data?.new.ideas, note: `${format(data?.pending.ideas)} zu prüfen`, icon: Lightbulb, tab: "ideas" },
    { label: "Bewerbungen", value: data?.new.applications, note: `${format(data?.pending.applications)} noch offen`, icon: FileText, tab: "webapply" },
  ];
  const inbox = [
    { label: "Premium-Anfragen", value: data?.pending.premium_purchases, tab: "premium", icon: CreditCard },
    { label: "Community-Ideen", value: data?.pending.ideas, tab: "ideas", icon: Lightbulb },
    { label: "Bewerbungen", value: data?.pending.applications, tab: "webapply", icon: FileText },
  ];
  const value = (number: number | undefined) => loading ? "…" : format(number);

  return <div className="cloudtix-admin-overview">
    <div className="cloudtix-admin-overview-status"><strong><i data-online={Boolean(data?.system.ready)} />{loading ? "System wird geladen …" : !data ? "Systemdaten nicht verfügbar" : data.system.ready ? "CloudTIX ist online" : "CloudTIX startet"}</strong><span>{data?.captured_at ? `Aktualisiert um ${new Date(data.captured_at * 1000).toLocaleTimeString(websiteLocale(), { hour: "2-digit", minute: "2-digit" })}` : "Warte auf die erste Aktualisierung"}</span></div>
    <div className="cloudtix-admin-total-grid">{totals.map(metric => <button key={metric.label} type="button" className="cloudtix-admin-total" onClick={() => onOpen(metric.tab)}><metric.icon size={19} /><span>{metric.label}</span><strong>{value(metric.value)}</strong><small>{metric.note}<ArrowRight size={12} /></small></button>)}</div>
    <div className="cloudtix-admin-overview-columns">
      <section><div className="cloudtix-admin-overview-section-heading"><div><h2>Was passiert bei CloudTIX?</h2><p>Aktivität der letzten {data?.period_hours ?? 24} Stunden</p></div><Activity size={16} className="text-slate-500" /></div><div className="cloudtix-admin-activity-grid">{activity.map(card => <button type="button" key={card.label} className="cloudtix-admin-activity-card" onClick={() => onOpen(card.tab)}><card.icon size={17} /><span><strong>{value(card.value)}</strong><span>{card.label}</span><small>{data ? card.note : "Noch keine Daten verfügbar"}</small></span></button>)}</div></section>
      <section className="cloudtix-admin-inbox"><p>DEIN POSTEINGANG</p><h2>Bereit für eine Entscheidung.</h2><small>Öffne die ausstehenden Anfragen und begleite die nächsten Schritte.</small><div className="cloudtix-admin-inbox-items">{inbox.map(item => <button type="button" key={item.label} onClick={() => onOpen(item.tab)}><item.icon size={16} /><span>{item.label}</span><strong>{value(item.value)}</strong><ArrowRight size={13} /></button>)}</div></section>
    </div>
    <section className="cloudtix-admin-system-strip" aria-label="Systemzustand"><div><span><Activity size={14} />API-Antwortzeit</span><strong>{data?.system.api_latency_ms == null ? "Nicht verfügbar" : `${format(data.system.api_latency_ms)} ms`}</strong></div><div><span><Server size={14} />Server-Verbindung</span><strong>{!data ? "Nicht verfügbar" : data.system.guilds_available ? "Verbindung hergestellt" : "Noch nicht bereit"}</strong></div><div><span><ShieldCheck size={14} />Systemkontrolle</span><strong><button type="button" onClick={() => onOpen("health")} className="inline-flex items-center gap-2 hover:text-white">Zustand ansehen<ArrowRight size={12} /></button></strong></div></section>
    <p className="cloudtix-admin-overview-note"><Bot size={12} />Server und Nutzer zeigen das Netto-Wachstum seit dem gespeicherten Vergleichspunkt.</p>
  </div>;
}
