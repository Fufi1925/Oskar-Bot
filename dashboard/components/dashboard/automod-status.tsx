"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Zap } from "lucide-react";
import { api } from "@/lib/api";
import {
  SecurityCard,
  SecurityWarnings,
} from "@/components/dashboard/security-workspace";

interface ModuleState {
  key: string;
  event: string;
  label: string;
  enabled: boolean;
  punishment: string | null;
  active: boolean;
  listener_loaded: boolean;
  state: "active" | "paused" | "off";
}

const PUNISHMENT_LABELS: Record<string, string> = {
  delete: "Löschen",
  warn: "Verwarnen",
  mute: "Timeout",
  kick: "Kicken",
  ban: "Bannen",
};

interface StatusPayload {
  master_enabled: boolean;
  modules: ModuleState[];
  active_count: number;
  ignored_channels: string[];
  ignored_roles: string[];
  log_channel: string | null;
  missing_permissions: string[];
  live: string;
}

/**
 * Shows what automod is really doing right now.
 *
 * The listeners read their configuration from the database on every single
 * message, so a saved change is live immediately. This reads the same rows
 * they do, which turns "trust me" into something verifiable.
 */
export function AutomodStatus({ guildId }: { guildId: string }) {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getAutomodStatus(guildId));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
    const afterSave = (event: Event) => {
      if ((event as CustomEvent<string>).detail === guildId) load();
    };
    window.addEventListener("automod-saved", afterSave);
    return () => window.removeEventListener("automod-saved", afterSave);
  }, [guildId, load]);

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
        title="Live-Status konnte nicht geladen werden"
      >
        <button
          type="button"
          onClick={load}
          className="cloudtix-workspace-action is-secondary"
        >
          Erneut versuchen
        </button>
      </SecurityCard>
    );

  return (
    <div className="space-y-5">
      <SecurityWarnings
        items={
          data.missing_permissions.length
            ? [
                `Fehlende Discord-Rechte: ${data.missing_permissions.join(", ")}. Die entsprechenden Aktionen können ohne diese Rechte nicht ausgeführt werden.`,
              ]
            : []
        }
      />
      <SecurityCard
        icon={Zap}
        title="Was läuft gerade wirklich?"
        subtitle={
          data.master_enabled
            ? `${data.active_count} von ${data.modules.length} Regeln greifen laut gespeicherter Konfiguration.`
            : "AutoMod ist ausgeschaltet. Keine Regel greift."
        }
        onReload={load}
      >
        <div className="cloudtix-security-rules">
          {data.modules.map((mod) => (
            <div key={mod.key} className="cloudtix-security-live-row">
              <div>
                <span className="cloudtix-settings-badge">
                  <i data-active={mod.active} />
                </span>
                <section>
                  <strong>{mod.label}</strong>
                  <p>
                    {mod.listener_loaded
                      ? "Listener geladen"
                      : "Listener nicht geladen"}
                  </p>
                </section>
              </div>
              <span className="cloudtix-settings-badge">
                {mod.state === "active"
                  ? PUNISHMENT_LABELS[mod.punishment || ""] || mod.punishment
                  : mod.state === "paused"
                    ? "Pausiert"
                    : "Aus"}
              </span>
            </div>
          ))}
        </div>
        {!data.modules.length && (
          <p className="cloudtix-security-note">
            Keine Regeln im Live-Status vorhanden.
          </p>
        )}
        <div className="cloudtix-settings-details">
          <div>
            <dt>Ausgenommene Rollen</dt>
            <dd>{data.ignored_roles.length}</dd>
          </div>
          <div>
            <dt>Ausgenommene Kanäle</dt>
            <dd>{data.ignored_channels.length}</dd>
          </div>
          {data.log_channel && (
            <div>
              <dt>Log-Kanal</dt>
              <dd>#{data.log_channel}</dd>
            </div>
          )}
        </div>
        <p className="cloudtix-security-note">{data.live}</p>
      </SecurityCard>
    </div>
  );
}
