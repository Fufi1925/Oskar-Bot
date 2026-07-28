"use client";

/**
 * Anti-nuke reporting.
 *
 * The seventeen anti-nuke modules used to work in complete silence. On
 * `except discord.Forbidden: return` they gave up without a word, which
 * from outside looks exactly like "nothing happened" and exactly like
 * "anti-nuke is switched off". This panel is where those three become
 * distinguishable.
 *
 * The most important thing on the page is the missing-permissions
 * warning: a bot that can see an attack but not act on it is the worst
 * case, because everything looks configured.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Bell, Check, Clock, Copy, ExternalLink, Loader2, Send,
  EyeOff, Shield, ShieldAlert, ShieldCheck, Trash2, UserPlus, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

const OUTCOME = {
  stopped: { label: "Abgewehrt", tone: "text-emerald-400", icon: ShieldCheck },
  // The attack was undone but the attacker got away: a real outcome of
  // its own, previously lumped in with "NICHT gestoppt" and so reported
  // as a failure when it was not one.
  partial: { label: "Gestoppt, kein Bann", tone: "text-amber-400", icon: ShieldAlert },
  no_perms: { label: "NICHT gestoppt", tone: "text-red-400", icon: ShieldAlert },
  // The bot cannot even read the audit log, so nothing is defended.
  blind: { label: "Blind — keine Rechte", tone: "text-red-400", icon: EyeOff },
  disabled: { label: "Anti-Nuke war aus", tone: "text-amber-400", icon: AlertTriangle },
} as const;

function ago(unix: number) {
  const diff = Date.now() - unix * 1000;
  const m = 60_000, h = 60 * m, d = 24 * h;
  if (diff < m) return "gerade eben";
  if (diff < h) return `vor ${Math.round(diff / m)} Min`;
  if (diff < d) return `vor ${Math.round(diff / h)} Std`;
  return `vor ${Math.round(diff / d)} Tg`;
}

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

export function NukeAlertPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [invite, setInvite] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.getNukeAlerts(guildId));
      setDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  const value = (key: string) => (key in draft ? draft[key] : data?.[key]);
  const set = (key: string, v: any) => setDraft((d) => ({ ...d, [key]: v }));
  const dirtyCount = Object.keys(draft).length;
  // Refuses to leave the tab while something is unsaved.
  const guard = useSaveGuard(dirtyCount, "nukealert-save-bar");

  const save = async () => {
    setBusy(true);
    try {
      const res = await api.updateNukeAlerts(guildId, draft);
      toast.success(res?.result || "Gespeichert.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const res = await api.testNukeAlert(guildId);
      toast.success(res?.result || "Testmeldung gesendet.");
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const fetchInvite = async () => {
    setBusy(true);
    try {
      const res = await api.getPartnerInvite(guildId);
      setInvite(res);
      if (res.warning) toast.warning(res.warning);
    } catch (err: any) {
      toast.error(err?.message || "Link konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const missing: string[] = data?.missing_permissions || [];

  return (
    <section className="space-y-6">
      {/* ── The thing that actually matters ──────────── */}
      {missing.length > 0 ? (
        <div className="bg-red-500/[0.07] border border-red-500/30 rounded-3xl p-4 sm:p-6 space-y-3">
          <div className="flex gap-3">
            <ShieldAlert className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="font-black text-white">
                Der Bot könnte einen Angriff gerade nicht stoppen
              </p>
              <p className="text-[12px] text-red-200/80 mt-1.5 leading-relaxed">
                Ihm fehlen: <b>{missing.join(", ")}</b>
              </p>
              <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
                Er sieht den Angriff, kann aber nichts dagegen tun. Gib ihm
                diese Rechte und schieb seine Rolle in den Server­einstellungen
                möglichst weit nach oben — er kann nur gegen Rollen vorgehen,
                die unter seiner eigenen stehen.
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-emerald-500/[0.05] border border-emerald-500/20 rounded-3xl p-5 flex gap-3">
          <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0" />
          <p className="text-[12px] text-emerald-200/80 leading-relaxed">
            Der Bot hat alle nötigen Rechte und könnte eingreifen. Achte
            zusätzlich darauf, dass seine Rolle weit oben steht.
          </p>
        </div>
      )}

      {/* ── Settings ─────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Bell className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">Meldung bei Angriffen</p>
            <p className="text-[11px] text-slate-500">
              Bisher hat der Bot bei einem Angriff nichts gesagt — weder wenn er
              ihn abwehrte, noch wenn er es nicht konnte.
            </p>
          </div>
        </div>

        <InlineToggle
          checked={value("enabled")}
          onCheckedChange={(v: boolean) => set("enabled", v)}
          label="Angriffe melden"
        />

        <Field
          label="Melde-Kanal"
          hint="Leer lassen: der Bot sucht sich selbst einen (Mod-Log, System-Kanal, …)."
        >
          <ChannelPicker
            guildId={guildId}
            value={value("channel_id") || ""}
            onChange={(id) => set("channel_id", id || null)}
            placeholder="Automatisch wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <div className="space-y-3">
          <InlineToggle
            checked={value("create_channel")}
            onCheckedChange={(v: boolean) => set("create_channel", v)}
            label="Notfall-Kanal anlegen, wenn keiner übrig ist"
            hint="Bei einem echten Nuke sind alle Kanäle weg. Dann legt der Bot einen an, den nur er und das Team sehen."
          />
          <InlineToggle
            checked={value("clean_channels")}
            onCheckedChange={(v: boolean) => set("clean_channels", v)}
            label="Vom Angreifer erstellte Kanäle löschen"
            hint="Nur Kanäle, die laut Audit-Log wirklich von ihm stammen — was ihr kurz vorher angelegt habt, bleibt."
          />
          <InlineToggle
            checked={value("ping_owner")}
            onCheckedChange={(v: boolean) => set("ping_owner", v)}
            label="Server-Inhaber pingen"
            hint="Nur wenn etwas nicht abgewehrt werden konnte — nicht bei jedem Erfolg."
          />
          <InlineToggle
            checked={value("dm_owner")}
            onCheckedChange={(v: boolean) => set("dm_owner", v)}
            label="Zusätzlich per DM benachrichtigen"
            hint="Falls während des Angriffs kein Kanal mehr erreichbar ist."
          />
        </div>

        <div className="flex gap-3 flex-wrap">
          <button
            onClick={test}
            disabled={busy}
            className="flex items-center gap-2 px-5 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
          >
            <Send className="h-4 w-4" />
            Testmeldung senden
          </button>
        </div>
      </div>

      {/* ── Partner bot ──────────────────────────────── */}
      {data?.partner_configured && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4">
          <div className="flex gap-3">
            <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
              <UserPlus className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="font-black text-white">Template-Bot hinzufügen</p>
              <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                Erzeugt einen Einladungslink für den zweiten Bot. Der erkennt
                dann automatisch, dass er von hier kommt, und richtet den Server
                mit seinem Template ein.
              </p>
            </div>
          </div>

          <div className="rounded-xl bg-emerald-500/[0.05] border border-emerald-500/20 p-3.5">
            <p className="text-[11px] text-emerald-200/80 leading-relaxed">
              <b className="text-emerald-300">Fest freigestellt:</b> Der
              Template-Bot ist beim Anti-Nuke dauerhaft ausgenommen — er legt
              beim Wiederherstellen in kurzer Zeit sehr viele Kanäle und Rollen
              an, was sonst wie ein Angriff aussieht. Du musst ihn nirgends
              eintragen, und er lässt sich auch nicht versehentlich aussperren.
            </p>
          </div>

          <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5">
            <p className="text-[11px] text-slate-500 leading-relaxed">
              <b className="text-slate-400">Warum ein Klick nötig ist:</b> Discord
              lässt einen Bot keinen anderen Bot einladen — auch nicht mit
              Admin-Rechten. Das Autorisieren muss ein Mensch im Browser
              bestätigen. Das ist Absicht: sonst könnte ein übernommener Bot
              beliebig viele weitere nachziehen, also genau einen Nuke bauen.
              <br />
              <br />
              Nach einem Angriff schickt der Bot den Startbefehl selbst — fünf
              Sekunden nachdem der Template-Bot beigetreten ist, in den Kanal
              mit der Alarm-Meldung. Du musst nichts tippen.
            </p>
          </div>

          {invite ? (
            <div className="space-y-2">
              <div className="flex gap-2 flex-wrap">
                <a
                  href={invite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 min-w-[180px] flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
                >
                  <ExternalLink className="h-4 w-4" />
                  Jetzt hinzufügen
                </a>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(invite.url);
                    toast.success("Link kopiert.");
                  }}
                  className="px-4 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-slate-400 hover:text-white transition-all"
                >
                  <Copy className="h-4 w-4" />
                </button>
              </div>
              {invite.signed && (
                <p className="text-[11px] text-slate-600">
                  Der Link ist signiert und läuft in{" "}
                  {Math.round((invite.expires_in || 3600) / 60)} Minuten ab.
                </p>
              )}
            </div>
          ) : (
            <button
              onClick={fetchInvite}
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
              Einladungslink erstellen
            </button>
          )}
        </div>
      )}

      {/* ── History ──────────────────────────────────── */}
      <div>
        <h3 className="font-black text-white flex items-center gap-2 mb-3">
          <Clock className="h-5 w-5 text-slate-500" />
          Vorfälle
          <span className="text-xs font-normal text-slate-500">
            ({data?.incidents?.length || 0})
          </span>
        </h3>

        {!data?.incidents?.length ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
            Noch nichts passiert.
          </p>
        ) : (
          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
            {data.incidents.map((entry: any) => {
              // Falling back to `stopped` would show an unknown outcome as a
              // success, which is the safest-looking and least true option.
              const style =
                (OUTCOME as any)[entry.outcome] || OUTCOME.no_perms;
              const Icon = style.icon;
              return (
                <div
                  key={entry.id}
                  className="bg-[#10233f] border border-slate-800 rounded-2xl px-4 py-3 flex items-center gap-3 flex-wrap"
                >
                  <Icon className={cn("h-4 w-4 shrink-0", style.tone)} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white truncate">
                      {entry.action_label}
                      <span className={cn("ml-2 text-[11px] font-black uppercase", style.tone)}>
                        {style.label}
                      </span>
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {entry.executor_name || "unbekannt"}
                      {entry.executor_id && ` (${entry.executor_id})`}
                      {" · "}
                      {ago(entry.at)}
                      {entry.detail && ` · ${entry.detail}`}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <StickySaveBar
        id="nukealert-save-bar"
        count={dirtyCount}
        busy={busy}
        shake={guard.shake}
        onDiscard={() => setDraft({})}
        onSave={save}
      />
    </section>
  );
}
