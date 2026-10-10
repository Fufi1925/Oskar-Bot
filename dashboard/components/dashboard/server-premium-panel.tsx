"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BadgeCheck, Bot, Check, Clock3, Crown, Database, Loader2, Lock, Power, RefreshCw, Server, ShieldCheck, Snowflake, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const FEATURES = [
  [Bot, "Server-Design", "Ein eigenes Profil mit Namen, Avatar und Banner.", "design"],
  [Database, "Backups", "Automatisch sichern und weitere Stände aufbewahren.", "backup"],
  [Users, "Server-Statistiken", "Deine Community in aktuellen Statistikkanälen.", "server-stats"],
  [RefreshCw, "User Pull", "Mitglieder mit ausdrücklicher Autorisierung verwalten.", "verification/pull"],
  [Sparkles, "Ticket-KI", "Unterstützung für deine Support-Anfragen.", "tickets"],
  [ShieldCheck, "Weitere Möglichkeiten", "Vorlagen und zusätzliche Premium-Funktionen.", "templates"],
] as const;
const date = (value?: number | null) => value ? new Date(value * 1000).toLocaleString(websiteLocale(), { dateStyle: "medium", timeStyle: "short" }) : "–";
const daysLeft = (value?: number | null) => value ? Math.max(0, Math.ceil((value * 1000 - Date.now()) / 86_400_000)) : 0;

export function ServerPremiumPanel({ guildId }: { guildId: string }) {
  useWebsiteLocale();
  const [state, setState] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setState(await api.getServerPremium(guildId)); setError(""); }
    catch (cause: any) { setError(cause?.message || "Premiumstatus konnte nicht geladen werden."); }
  }, [guildId]);
  useEffect(() => { void load(); }, [load]);
  const choose = async (action: "keep" | "disable") => {
    setBusy(true);
    try { setState(await api.setServerPremiumExpiryAction(guildId, action)); toast.success("Ablaufverhalten gespeichert."); }
    catch (cause: any) { toast.error(cause?.message || "Speichern fehlgeschlagen."); }
    finally { setBusy(false); }
  };
  if (!state && !error) return <div className="grid min-h-64 place-items-center"><Loader2 aria-label="Premium wird geladen" className="h-6 w-6 animate-spin text-neutral-400" /></div>;
  if (!state) return <section className="cloudtix-settings-card text-center"><Crown className="mx-auto h-8 w-8 text-slate-500" /><h2 className="mt-4 text-xl">Premium nicht erreichbar</h2><p className="mt-2 text-sm text-slate-400">{error}</p><button onClick={() => void load()} className="cloudtix-workspace-action mt-5">Erneut laden</button></section>;
  const remaining = daysLeft(state.expires_at);
  const label = state.active ? "Premium aktiv" : state.frozen ? "Konfiguration eingefroren" : "Kein aktives Premium";
  const progress = Math.max(0, Math.min(100, remaining / Math.max(1, state.duration_days || 1) * 100));

  return <div className="cloudtix-settings-page" aria-busy={busy}>
    <header className="cloudtix-settings-heading"><div><p className="cloudtix-workspace-eyebrow">CLOUDTIX PREMIUM</p><h1>Mehr für deinen Server.</h1><p>Dein Zugang, deine Laufzeit und die Möglichkeiten für deine Community.</p></div><button type="button" disabled={busy} onClick={() => void load()} className="cloudtix-workspace-action is-secondary"><RefreshCw size={14} />Aktualisieren</button></header>
    {error && <p role="status" className="cloudtix-settings-warning">{error}</p>}
    <div className="cloudtix-premium-summary">
      <section className="cloudtix-settings-card cloudtix-premium-membership"><span className="cloudtix-premium-emblem"><Crown size={26} /></span><div><p className="cloudtix-workspace-eyebrow">SERVER-MITGLIEDSCHAFT</p><h2>{state.guild_name || "Dein Server"}</h2><span className="cloudtix-settings-badge" data-active={String(Boolean(state.active))}><i />{label}</span><p>{state.active ? "Deine Community hat Zugriff auf die Premium-Funktionen." : state.frozen ? "Deine Einrichtung läuft weiter. Verlängere Premium, um sie wieder zu bearbeiten." : "Schalte zusätzliche Möglichkeiten für deine Community frei."}</p></div><Link href="/dashboard/premium" className="cloudtix-workspace-action">{state.active ? "Premium verwalten" : state.frozen ? "Premium verlängern" : "Premiumplatz zuweisen"}<ArrowRight size={15} /></Link></section>
      <section className="cloudtix-settings-card cloudtix-premium-duration"><Clock3 size={19} /><p>Deine Laufzeit</p><strong>{state.lifetime ? "∞" : state.active ? remaining : "—"}</strong><span>{state.lifetime ? "Lebenslang" : state.active ? "Tage verbleibend" : "Keine aktive Laufzeit"}</span>{state.active && !state.lifetime && <div className="cloudtix-workspace-progress-track" role="progressbar" aria-label="Verbleibende Premium-Laufzeit" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${progress}%` }} /></div>}<small>{state.lifetime ? "Ohne Ablaufdatum" : state.expires_at ? `Bis ${date(state.expires_at)}` : "Einlösen über dein Premium-Konto"}</small></section>
    </div>
    <div className="cloudtix-settings-grid">
      <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Server size={18} /></span><div><h2>Deine Zuweisung</h2><p>Premium gehört zu diesem Server.</p></div></div><dl className="cloudtix-settings-details"><div><dt>Serverplatz</dt><dd>{state.direct_admin_grant ? "Direkte Admin-Freigabe" : state.assigned ? `${state.slot_no} von 3` : "Noch nicht zugewiesen"}</dd></div><div><dt>Premium-Konto</dt><dd data-no-translate>{state.account_user_name || "Nicht zugeordnet"}</dd></div><div><dt>Zugewiesen am</dt><dd>{date(state.assigned_at)}</dd></div><div><dt>Funktionszugang</dt><dd>{state.runtime ? "Verfügbar" : "Noch nicht aktiviert"}</dd></div></dl>{state.account_user_avatar && <img className="mt-4 h-9 w-9 rounded-xl object-cover" src={state.account_user_avatar} alt="Profilbild des Premium-Kontos" />}</section>
      <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><BadgeCheck size={18} /></span><div><h2>Ein Konto. Drei Serverplätze.</h2><p>Verwalte deine Mitgliedschaft an einem Ort.</p></div></div><div className="cloudtix-settings-feature-list"><div><Check size={17} /><span><strong>Serverbezogener Zugang</strong><small>Für alle mit Dashboard-Zugriff. Owner-Berechtigungen gelten weiterhin.</small></span></div><div><Check size={17} /><span><strong>Deine Einrichtung bleibt erhalten</strong><small>Gespeicherte Einstellungen werden bei einem Ablauf nicht gelöscht.</small></span></div><div><Clock3 size={17} /><span><strong>30 Tage Cooldown beim Entfernen</strong><small>Die Sperre gilt für den freigegebenen Platz. Andere Plätze bleiben verfügbar.</small></span></div></div></section>
    </div>
    <section className="cloudtix-settings-card"><div className="cloudtix-settings-list-heading"><div><h2>Für deine Community freigeschaltet.</h2><p>{state.runtime ? "Öffne einen Bereich und passe ihn an deinen Server an." : "Diese Bereiche stehen mit Server-Premium zur Verfügung."}</p></div><span className="cloudtix-settings-badge">{state.runtime ? "Verfügbar" : "Premium erforderlich"}</span></div><div className="cloudtix-premium-features">{FEATURES.map(([Icon, title, description, route]) => <Link key={title} href={`/dashboard/guild/${guildId}/${route}`} className="cloudtix-premium-feature"><span><Icon size={20} /></span><div><h3>{title}</h3><p>{description}</p></div>{state.runtime ? <ArrowRight size={15} /> : <Lock size={14} />}</Link>)}</div></section>
    {state.assigned && <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Power size={18} /></span><div><h2>Was nach Ablauf passiert</h2><p>Wähle das Verhalten deiner Premium-Funktionen. Die Auswahl wird direkt gespeichert.</p></div></div><div className="cloudtix-settings-grid"><Choice active={state.expiry_action === "keep"} busy={busy} onClick={() => void choose("keep")} icon={Snowflake} title="Weiterlaufen lassen" badge="Empfohlen" text="Eingerichtete Funktionen bleiben aktiv. Einstellungen können bis zur Verlängerung nicht bearbeitet werden." /><Choice active={state.expiry_action === "disable"} busy={busy} onClick={() => void choose("disable")} icon={Power} title="Funktionen pausieren" text="Premium-Funktionen stoppen nach dem Ablauf. Deine Einrichtung bleibt für eine spätere Verlängerung gespeichert." /></div>{state.frozen && <div className="cloudtix-settings-running mt-5"><Lock size={16} /><p>Die Konfiguration ist eingefroren. Bestehende Funktionen laufen weiter; Änderungen sind derzeit gesperrt.</p></div>}</section>}
  </div>;
}

function Choice({ active, busy, onClick, icon: Icon, title, text, badge }: { active: boolean; busy: boolean; onClick: () => void; icon: typeof Power; title: string; text: string; badge?: string }) {
  return <button type="button" disabled={busy} aria-pressed={active} onClick={onClick} className="cloudtix-workspace-option cloudtix-premium-choice"><div><Icon size={20} />{active ? <Check size={18} /> : badge ? <span className="cloudtix-settings-badge">{badge}</span> : null}</div><h3>{title}</h3><p>{text}</p></button>;
}
