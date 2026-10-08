"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { ModerationTabs } from "@/components/dashboard/moderation-design";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { WebsiteSelect } from "@/components/ui/website-select";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Save, Send, ShieldCheck, Users, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { LogUmgezogen } from "@/components/dashboard/log-umgezogen";

const card = "rounded-2xl border border-white/[.07] bg-[#202124] p-5 sm:p-6";
const field = "mt-2 w-full rounded-xl border border-white/10 bg-[#18191c] px-4 py-3 text-sm text-white outline-none focus:border-primary/50";
const action = "inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-50";
const TITLE = "DO NOT SEND MESSAGES IN THIS CHANNEL";

interface Settings {
  enabled: boolean;
  channel_name?: string;
  channel_missing?: boolean;
  kicks: number;
  custom_channel_id?: string;
  delete_days: number;
  whitelist_roles: string[];
  roles: { id: string; name: string }[];
  channels: { id: string; name: string; can_send: boolean }[];
  permissions: { ok: boolean; detail: string };
}

export function HoneypotPanel({ guildId }: { guildId: string }) {
  useWebsiteLocale();
  const [data, setData] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [channel, setChannel] = useState("");
  const [days, setDays] = useState(1);
  const [view, setView] = useState("setup");
  const [roles, setRoles] = useState<string[]>([]);
  const apply = useCallback((result: Settings) => {
    setData(result);
    setChannel(result.custom_channel_id || "");
    setDays(result.delete_days ?? 1);
    setRoles(result.whitelist_roles || []);
  }, []);
  const load = useCallback(async () => {
    setLoading(true);
    try { apply(await api.honeypot(guildId)); }
    catch (error: any) { toast.error(error?.message || "Einstellungen konnten nicht geladen werden."); }
    finally { setLoading(false); }
  }, [guildId, apply]);
  useEffect(() => { load(); }, [load]);
  const run = async (operation: () => Promise<any>, success: string) => {
    setBusy(true);
    try { apply(await operation()); toast.success(success); }
    catch (error: any) { toast.error(error?.message || "Aktion fehlgeschlagen."); }
    finally { setBusy(false); }
  };
  const dirty = !!data && (channel !== (data.custom_channel_id || "") || days !== data.delete_days || JSON.stringify(roles) !== JSON.stringify(data.whitelist_roles || []));
  const guard = useSaveGuard(dirty ? 1 : 0, "honeypot-save-bar");
  if (loading) return <div className={card}><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>;
  if (!data) return <div className={card}><p className="mb-3 text-slate-400">Einstellungen nicht verfügbar.</p><button onClick={load} className={action}>Erneut laden</button></div>;
  if (!data.enabled) return <div className={card}>
    <p className="mb-4 text-sm text-slate-400">Aktiviere den Honeypot, um den Köder-Kanal einzurichten.</p>
    <button className={action} disabled={busy} onClick={() => run(async () => {
      const result = await api.honeypotToggle(guildId, true);
      window.dispatchEvent(new CustomEvent("guild-module-state", { detail: { guildId, module: "honeypot", enabled: result.enabled } }));
      return result;
    }, "Honeypot aktiviert.")}>Honeypot einschalten</button>
  </div>;
  return <div className="space-y-5">
    <section className={card}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400/10"><ShieldCheck className="h-5 w-5 text-emerald-300" /></span>
          <div><h3 className="font-semibold text-white">Schutz aktiv</h3><p className="mt-1 text-sm text-slate-400">#{data.channel_name || "Kanal fehlt"} · {Number(data.kicks || 0).toLocaleString(websiteLocale())} erfolgreiche Softbans</p></div>
        </div>
        <div className="flex gap-2"><button onClick={load} disabled={busy || dirty} className={action} aria-label="Statistik aktualisieren"><RefreshCw className="h-4 w-4" /></button>
          <button disabled={busy || dirty} className={action} onClick={() => run(() => api.honeypotResend(guildId), "Panel aktualisiert.")}><Send className="h-4 w-4" />Panel erneuern</button></div>
      </div>
      {(data.permissions.detail || data.channel_missing) && <div role="status" className="mt-4 flex gap-2 rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-sm text-amber-200"><AlertTriangle className="h-5 w-5 shrink-0" /><span>{data.permissions.detail || "Der Köder-Kanal wurde gelöscht. Mit „Panel erneuern“ wird er wiederhergestellt."}</span></div>}
    </section>

    <ModerationTabs value={view} onChange={setView} items={[["setup", "Einrichtung"], ["exceptions", "Ausnahmen"], ["panel", "Discord-Panel"]]} label="Honeypot-Bereiche" />
    <div hidden={view !== "setup"}>
    <fieldset disabled={busy} className="grid gap-5 lg:grid-cols-2 disabled:opacity-60">
      <section className={card}><h3 className="flex items-center gap-2 font-semibold text-white"><MessageSquare className="h-4 w-4 text-blue-300" />Köder-Kanal</h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">Automatisch steht der Kanal ganz oben. Ein eigener Kanal bleibt an seiner bisherigen Position.</p>
        <label className="mt-5 block text-sm text-slate-300" htmlFor="honeypot-channel">Kanal auswählen</label>
        <WebsiteSelect id="honeypot-channel" value={channel} onChange={event => setChannel(event.target.value)} className={field}>
          <option value="">Automatisch: #dont-sent-here</option>
          {data.channels.map(item => <option key={item.id} value={item.id} disabled={!item.can_send}>#{item.name}{!item.can_send ? " · keine Schreibrechte" : ""}</option>)}
        </WebsiteSelect>
        <p className="mt-3 text-xs text-slate-500">Der Kanal muss für Mitglieder sichtbar und beschreibbar sein.</p>
      </section>
      <section className={card}><h3 className="flex items-center gap-2 font-semibold text-white"><ShieldCheck className="h-4 w-4 text-amber-300" />Softban</h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">Bannen und sofort entbannen entfernt den Spam. Die Person kann anschließend mit einem neuen Einladungslink zurückkommen.</p>
        <label className="mt-5 block text-sm text-slate-300" htmlFor="honeypot-days">Nachrichten löschen</label>
        <WebsiteSelect id="honeypot-days" value={days} onChange={event => setDays(Number(event.target.value))} className={field}>
          {[0,1,2,3,4,5,6,7].map(day => <option key={day} value={day}>{day === 0 ? "Keine Nachrichten löschen" : day === 1 ? "Letzte 24 Stunden" : `Letzte ${day} Tage`}</option>)}
        </WebsiteSelect>
        <p className="mt-3 text-xs text-slate-500">Ohne Bannrecht oder bei zu hoher Rolle kann der Bot keinen Softban ausführen.</p>
      </section>
    </fieldset>
    </div>

    <div hidden={view !== "exceptions"} className="space-y-5">
    <section className={card}><h3 className="flex items-center gap-2 font-semibold text-white"><Users className="h-4 w-4 text-violet-300" />Ausnahmen</h3>
      <p className="mt-2 text-sm text-slate-400">Mitglieder mit diesen Rollen werden nicht bestraft. Server-Inhaber und Bots sind immer geschützt.</p>
      <div className="mt-4 grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2">
        {data.roles.map(role => <label key={role.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/[.07] bg-[#18191c] p-3 text-sm text-slate-300"><input type="checkbox" disabled={busy} checked={roles.includes(role.id)} onChange={event => setRoles(current => event.target.checked ? [...current, role.id] : current.filter(id => id !== role.id))} className="h-4 w-4 accent-primary" /><span className="truncate">{role.name}</span></label>)}
      </div>
      {data.roles.length === 0 && <p className="mt-4 text-sm text-slate-500">Keine zusätzlichen Rollen vorhanden.</p>}
    </section>

    <LogUmgezogen guildId={guildId} logKey="honeypot" was="Wer softgebannt wurde" />
    </div>
    <div hidden={view !== "panel"}>
    <section className={card}><div className="mb-4 flex items-center justify-between"><h3 className="font-semibold text-white">Discord-Panel</h3><span className="rounded-lg bg-white/5 px-2 py-1 text-xs text-slate-500">Fester Warntext</span></div>
      <div className="rounded-xl border border-white/[.07] bg-[#18191c] p-5"><h4 className="text-lg font-bold text-white">{TITLE}</h4><p className="mt-3 text-sm leading-relaxed text-slate-300">This channel is used to catch spam bots. Any messages sent here will result in <strong>a softban</strong>.</p><span className="mt-4 inline-block rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300">Softbans: {data.kicks || 0}</span></div>
      <p className="mt-3 text-xs text-slate-500">Der Knopf öffnet privat Informationen, aktuelle Statistiken und Links zu University Bot. Die Warnung ist nicht bearbeitbar.</p>
    </section>
    </div>
    <StickySaveBar id="honeypot-save-bar" count={dirty ? 1 : 0} busy={busy} shake={guard.shake} onDiscard={() => apply(data)} onSave={() => run(() => api.honeypotSave(guildId, { custom_channel_id: channel || null, delete_days: days, whitelist_roles: roles }), "Einstellungen gespeichert.")} />
  </div>;
}
