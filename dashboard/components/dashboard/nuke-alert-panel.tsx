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
  AlertTriangle,
  Bell,
  Clock,
  Loader2,
  Send,
  EyeOff,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import {
  SecurityCard,
  SecurityField,
  SecurityWarnings,
} from "@/components/dashboard/security-workspace";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

const OUTCOME = {
  stopped: { label: "Abgewehrt", tone: "text-emerald-400", icon: ShieldCheck },
  // The attack was undone but the attacker got away: a real outcome of
  // its own, previously lumped in with "NICHT gestoppt" and so reported
  // as a failure when it was not one.
  partial: {
    label: "Gestoppt, kein Bann",
    tone: "text-amber-400",
    icon: ShieldAlert,
  },
  no_perms: {
    label: "NICHT gestoppt",
    tone: "text-red-400",
    icon: ShieldAlert,
  },
  // The bot cannot even read the audit log, so nothing is defended.
  blind: { label: "Blind — keine Rechte", tone: "text-red-400", icon: EyeOff },
  disabled: {
    label: "Anti-Nuke war aus",
    tone: "text-amber-400",
    icon: AlertTriangle,
  },
} as const;

function ago(unix: number) {
  const diff = Date.now() - unix * 1000;
  const m = 60_000,
    h = 60 * m,
    d = 24 * h;
  if (diff < m) return "gerade eben";
  if (diff < h) return `vor ${Math.round(diff / m)} Min`;
  if (diff < d) return `vor ${Math.round(diff / h)} Std`;
  return `vor ${Math.round(diff / d)} Tg`;
}

export function NukeAlertPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});

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

  useEffect(() => {
    load();
  }, [load]);

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

  if (loading)
    return (
      <div className="cloudtix-settings-card flex justify-center py-10">
        <Loader2 size={22} className="animate-spin" />
      </div>
    );
  if (!data)
    return (
      <SecurityCard
        icon={AlertTriangle}
        title="Angriffsmeldungen konnten nicht geladen werden"
      >
        <button
          type="button"
          onClick={load}
          className="cloudtix-workspace-action is-secondary"
        >
          Erneut laden
        </button>
      </SecurityCard>
    );

  const missing: string[] = data.missing_permissions || [];
  const settings = [
    [
      "create_channel",
      "Notfall-Kanal anlegen",
      "Wenn kein Kanal mehr übrig ist, legt CloudTIX einen Kanal für den Bot und das Team an.",
    ],
    [
      "clean_channels",
      "Angreifer-Kanäle entfernen",
      "Entfernt nur Kanäle, die laut Audit-Log vom Angreifer erstellt wurden.",
    ],
    [
      "offer_rebuild",
      "Wiederherstellung anbieten",
      "Bietet nach gelöschten Kanälen oder Rollen eine Wiederherstellung an.",
    ],
    [
      "dm_owner",
      "Serverinhaber per DM informieren",
      "Nur bei einem echten Nuke, wenn der Bot einen Angreifer gebannt hat.",
    ],
    [
      "post_incidents",
      "Kleine Vorfälle im Kanal melden",
      "Zum Beispiel Webhooks oder einzelne Banns. Im Verlauf stehen sie auch ohne Kanalnachricht.",
    ],
  ];
  return (
    <section className="space-y-5">
      {missing.length ? (
        <SecurityWarnings
          items={[
            `Der Bot könnte einen Angriff aktuell nicht stoppen. Fehlende Rechte: ${missing.join(", ")}. Prüfe zusätzlich seine Rollenposition.`,
          ]}
        />
      ) : (
        <div className="cloudtix-settings-running">
          <ShieldCheck size={20} />
          <p>
            Alle nötigen Discord-Rechte sind vorhanden. Prüfe zusätzlich, dass
            die Bot-Rolle über den Rollen möglicher Angreifer steht.
          </p>
        </div>
      )}
      <div className="cloudtix-stats-reports">
        <SecurityCard
          icon={Bell}
          title="Alarm & Benachrichtigungen"
          subtitle="Entscheide, wie CloudTIX einen Angriff meldet."
        >
          <fieldset disabled={busy} className="space-y-5">
            <InlineToggle
              checked={!!value("enabled")}
              onCheckedChange={(v: boolean) => set("enabled", v)}
              label="Angriffe melden"
            />
            <SecurityField
              label="Melde-Kanal"
              hint="Ohne Auswahl sucht CloudTIX einen geeigneten Mod-Log- oder System-Kanal."
            >
              <ChannelPicker
                guildId={guildId}
                value={value("channel_id") || ""}
                onChange={(id) => set("channel_id", id || null)}
                placeholder="Automatisch wählen"
                channelTypes={["0", "5"]}
              />
            </SecurityField>
            {settings.map(([key, label, hint]) => (
              <InlineToggle
                key={key}
                checked={!!value(key)}
                onCheckedChange={(v: boolean) => set(key, v)}
                label={label}
                hint={hint}
              />
            ))}
          </fieldset>
          <button
            type="button"
            onClick={test}
            disabled={busy || !!dirtyCount}
            className="cloudtix-workspace-action is-secondary"
          >
            <Send size={15} />
            Testmeldung senden
          </button>
          {dirtyCount > 0 && (
            <p className="cloudtix-security-note">
              Speichere deine Änderungen, bevor du die Testmeldung sendest.
            </p>
          )}
        </SecurityCard>
        <SecurityCard
          icon={ShieldAlert}
          title="Reaktion auf einen Vorfall"
          subtitle="Die aktivierten Optionen bestimmen die Benachrichtigungen."
        >
          <div className="cloudtix-security-system-list">
            <div>
              <section>
                <strong>Kanäle oder Rollen gelöscht</strong>
                <p>
                  Ein echter Nuke kann einen Alarm, ein
                  Wiederherstellungsangebot und nach dem Bann des Angreifers
                  eine DM auslösen.
                </p>
              </section>
            </div>
            <div>
              <section>
                <strong>Einzelne Aktionen</strong>
                <p>
                  Rollenvergaben, Webhooks und einzelne Banns erscheinen im
                  Verlauf. Kanalnachrichten lassen sich zusätzlich aktivieren.
                </p>
              </section>
            </div>
            <div>
              <section>
                <strong>Fehlende Rechte</strong>
                <p>
                  Ohne passende Rechte kann der Bot einen Angriff nicht
                  abwehren. Prüfe die Rechteanzeige und die Rollenposition.
                </p>
              </section>
            </div>
          </div>
        </SecurityCard>
      </div>
      <SecurityCard
        icon={Clock}
        title="Vorfälle"
        subtitle={`${data.incidents?.length || 0} gespeicherte Einträge`}
        onReload={load}
        reloadDisabled={busy || !!dirtyCount}
      >
        {!data.incidents?.length ? (
          <div className="cloudtix-settings-empty">
            <Shield size={29} />
            <h3>Noch keine Vorfälle</h3>
            <p>Erkannte Aktionen und ihre Ergebnisse erscheinen hier.</p>
          </div>
        ) : (
          <div className="space-y-3 max-h-[500px] overflow-y-auto">
            {data.incidents.map((entry: any) => {
              const style = (OUTCOME as any)[entry.outcome] || OUTCOME.no_perms;
              const Icon = style.icon;
              return (
                <article key={entry.id} className="cloudtix-security-live-row">
                  <div>
                    <Icon size={18} className={style.tone} />
                    <section>
                      <strong>{entry.action_label}</strong>
                      <p>
                        {entry.executor_name || "Unbekannt"}
                        {entry.executor_id && ` (${entry.executor_id})`} ·{" "}
                        {ago(entry.at)}
                        {entry.detail && ` · ${entry.detail}`}
                      </p>
                    </section>
                  </div>
                  <span className={`cloudtix-settings-badge ${style.tone}`}>
                    {style.label}
                  </span>
                </article>
              );
            })}
          </div>
        )}
      </SecurityCard>
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
