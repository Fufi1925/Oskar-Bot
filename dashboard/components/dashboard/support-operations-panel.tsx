"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { WebsiteSelect } from "@/components/ui/website-select";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Clock3,
  ExternalLink,
  Flag,
  Gauge,
  History,
  KeyRound,
  Loader2,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Siren,
  Ticket,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { useUnsavedGuard } from "@/components/dashboard/save-bar";
import {
  Action,
  Badge,
  CARD,
  Confirmation,
  ConfirmDialog,
  CopyButton,
  Empty,
  Field,
  INPUT,
  Notice,
  Row,
  Section,
  message,
  timestamp,
} from "@/components/dashboard/support-console-ui";

const SUPPORT_GUILD_ID = "1530378233579704370";
type Tab =
  | "overview"
  | "errors"
  | "diagnose"
  | "incidents"
  | "features"
  | "lookup"
  | "access"
  | "audit";
const TABS = [
  { id: "overview", label: "Übersicht", icon: Gauge },
  { id: "errors", label: "Fehler", icon: AlertTriangle },
  { id: "diagnose", label: "Diagnose", icon: Wrench },
  { id: "incidents", label: "Incidents", icon: Siren },
  { id: "features", label: "Funktionen", icon: Flag },
  { id: "lookup", label: "Server & Premium", icon: Server },
  { id: "access", label: "Zugriffe & Vorlagen", icon: KeyRound },
  { id: "audit", label: "Änderungsverlauf", icon: History },
] as const;
const STATUS: Record<string, string> = {
  new: "Neu",
  investigating: "In Untersuchung",
  resolved: "Behoben",
  open: "Offen",
  monitoring: "In Beobachtung",
  accepted: "Akzeptiert",
  pending: "Ausstehend",
  closed: "Geschlossen",
  none: "Kein Supportfall",
  approved: "Genehmigt",
  denied: "Abgelehnt",
};
const SEVERITY: Record<string, string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
  critical: "Kritisch",
};
const AUDIT: Record<string, string> = {
  error_channel_set: "Fehlerkanal geändert",
  error_status: "Fehlerstatus geändert",
  developer_ticket_created: "Entwickler-Ticket erstellt",
  incident_created: "Incident eröffnet",
  incident_updated: "Incident aktualisiert",
  feature_flag_changed: "Funktion geändert",
  support_access_revoked: "Supportzugriff widerrufen",
};
const validId = (value: string) =>
  /^[1-9]\d{0,18}$/.test(value) &&
  (value.length < 19 || value <= "9223372036854775807");
const digits = (value: string) => value.replace(/\D/g, "");
type ErrorEntry = {
  error_id: string;
  status: string;
  feature: string;
  error_type: string;
  bot_instance: string;
  guild_id: string;
  summary: string;
  traceback: string;
  count: number;
  first_seen: number;
  last_seen: number;
  ticket_thread_id?: string;
};
type Timeline = { at: number; actor: string; event: string; note: string };
type Incident = {
  incident_id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  created_at: number;
  updated_at: number;
  timeline_json: string;
};
type Feature = {
  key: string;
  label: string;
  category: string;
  description: string;
  effect: string;
  enabled: boolean;
  active: boolean;
  requires: string[];
  rollout_percent: number;
};
type AuditEntry = {
  id: number;
  actor_id: string;
  action: string;
  target: string;
  detail: string;
  created_at: number;
};
type Overview = {
  global: {
    guilds: number;
    users: number;
    commands: number;
    latency_ms: number | null;
    open_errors: number;
    open_incidents: number;
    total_errors?: number;
    total_incidents?: number;
  };
  deployment: {
    deployment_id: string;
    commit: string;
    instance: string;
    discord_status: string;
    uptime_seconds: number;
    heartbeat: number;
    last_backup_at: number;
    failed_extensions: string[];
    recovered_extensions: string[];
  };
  settings: { error_channel_id: string };
  errors: ErrorEntry[];
  incidents: Incident[];
  features: Feature[];
  audit?: AuditEntry[];
};
type Diagnosis = {
  guild: { id: string; name: string };
  checked: number;
  findings: {
    area: string;
    severity: string;
    problem: string;
    solution: string;
  }[];
};
type GuildResult = {
  id: string;
  name: string;
  owner_name: string;
  owner_id: string;
  members: number;
  channels: number;
  roles: number;
  joined_at: number;
  bot_permissions: Record<string, boolean>;
  premium: PremiumServer;
};
type PremiumServer = {
  guild_id: string;
  active: boolean;
  assigned: boolean;
  frozen?: boolean;
  expires_at?: number;
  account_user_id?: string;
  configurable?: boolean;
  slot_no?: number;
  direct_admin_grant?: boolean;
};
type PremiumAccount = {
  user_id: string;
  premium: boolean;
  lifetime: boolean;
  expires_at?: number;
  source: string;
  note: string;
  slots: { slot_no: number; guild_id: string; expiry_action: string }[];
  purchase_requests: {
    id: number;
    duration_days: number;
    status: string;
    created_at: number;
  }[];
};
type Premium = { server: PremiumServer | null; account: PremiumAccount | null };
type SupportCase = {
  id: number;
  status: string;
  problem: string;
  accepted_at: number;
  closed_at: number;
};
type TemplateResult = {
  template: { name: string; visibility: string; source_guild_id: string };
  inspection: { size: number; modules: string[]; contains_secret: boolean };
};

function StateBadge({ status }: { status: string }) {
  useWebsiteLocale();
  return (
    <Badge
      tone={
        status === "resolved" || status === "accepted"
          ? "good"
          : status === "new" || status === "open"
            ? "bad"
            : "neutral"
      }
    >
      {STATUS[status] || status}
    </Badge>
  );
}
function timeline(value: string): Timeline[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed)
      ? parsed.filter((item) => item && typeof item.event === "string")
      : [];
  } catch {
    return [];
  }
}

export function SupportOperationsPanel({ guildId }: { guildId: string }) {
  useWebsiteLocale();
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const epoch = useRef(0);
  const mounted = useRef(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [errorChannel, setErrorChannel] = useState<string | null>(null);
  const [errorQuery, setErrorQuery] = useState("");
  const [errorStatus, setErrorStatus] = useState("open");
  const [errorSort, setErrorSort] = useState("recent");
  const [lookedUpError, setLookedUpError] = useState<ErrorEntry | null>(null);
  const [targetGuild, setTargetGuild] = useState("");
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [server, setServer] = useState<GuildResult | null>(null);
  const [incidentDraft, setIncidentDraft] = useState({
    title: "",
    severity: "medium",
    description: "",
  });
  const [incidentStatus, setIncidentStatus] = useState("open");
  const [featureQuery, setFeatureQuery] = useState("");
  const [featureStatus, setFeatureStatus] = useState("all");
  const [featureCategory, setFeatureCategory] = useState("all");
  const [premiumIds, setPremiumIds] = useState({ server: "", user: "" });
  const [premium, setPremium] = useState<Premium | null>(null);
  const [accessIds, setAccessIds] = useState({ server: "", user: "" });
  const [accessCase, setAccessCase] = useState<{
    case: SupportCase | null;
    serverId: string;
    userId: string;
  } | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [template, setTemplate] = useState<{
    result: TemplateResult;
    id: string;
  } | null>(null);
  const [auditQuery, setAuditQuery] = useState("");
  const dirtyChannel =
    errorChannel !== null &&
    errorChannel !== (data?.settings.error_channel_id || "");
  const dirtyIncident = Boolean(
    incidentDraft.title || incidentDraft.description,
  );
  useUnsavedGuard(dirtyChannel || dirtyIncident || busy, () =>
    toast.error("Bitte Eingaben zuerst speichern oder verwerfen."),
  );

  const load = useCallback(async () => {
    const version = ++epoch.current;
    setLoading(true);
    setLoadError("");
    try {
      const result: Overview = await api.getSupportOperations(guildId);
      if (mounted.current && epoch.current === version) {
        setData(result);
        setLookedUpError((old) =>
          old
            ? result.errors.find((entry) => entry.error_id === old.error_id) ||
              old
            : null,
        );
        setUpdatedAt(Date.now() / 1000);
      }
      return result;
    } catch (error: unknown) {
      if (mounted.current && epoch.current === version)
        setLoadError(message(error));
      return null;
    } finally {
      if (mounted.current && epoch.current === version) setLoading(false);
    }
  }, [guildId]);
  useEffect(() => {
    mounted.current = true;
    setData(null);
    setErrorChannel(null);
    setLookedUpError(null);
    if (guildId === SUPPORT_GUILD_ID) void load();
    return () => {
      mounted.current = false;
    };
  }, [guildId, load]);

  const perform = async (
    action: () => Promise<unknown>,
    success: string,
    refresh = false,
  ) => {
    if (locked.current) return false;
    locked.current = true;
    setBusy(true);
    try {
      await action();
      if (!mounted.current) return false;
      toast.success(success);
      setConfirmation(null);
      if (refresh) await load();
      return true;
    } catch (error: unknown) {
      if (mounted.current) toast.error(message(error));
      return false;
    } finally {
      locked.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const changeError = async (entry: ErrorEntry, status: string) =>
    perform(
      async () => {
        const result: ErrorEntry = await api.setSupportErrorStatus(
          guildId,
          entry.error_id,
          status,
        );
        setLookedUpError((old) =>
          old?.error_id === result.error_id ? result : old,
        );
      },
      "Fehlerstatus gespeichert.",
      true,
    );
  const refresh = () => {
    if (!locked.current) void load();
  };
  const errorRows = useMemo(() => {
    const rows = (data?.errors || []).map((entry) =>
      lookedUpError?.error_id === entry.error_id ? lookedUpError : entry,
    );
    if (
      lookedUpError &&
      !rows.some((entry) => entry.error_id === lookedUpError.error_id)
    )
      rows.unshift(lookedUpError);
    return rows
      .filter(
        (entry) =>
          (errorStatus === "all" ||
            (errorStatus === "open"
              ? entry.status !== "resolved"
              : entry.status === errorStatus)) &&
          `${entry.error_id} ${entry.feature} ${entry.summary} ${entry.guild_id}`
            .toLowerCase()
            .includes(errorQuery.toLowerCase()),
      )
      .sort((a, b) =>
        errorSort === "frequency"
          ? b.count - a.count
          : b.last_seen - a.last_seen,
      );
  }, [data, lookedUpError, errorStatus, errorQuery, errorSort]);
  const features = useMemo(
    () =>
      (data?.features || []).filter(
        (entry) =>
          `${entry.label} ${entry.key} ${entry.description}`
            .toLowerCase()
            .includes(featureQuery.toLowerCase()) &&
          (featureCategory === "all" || entry.category === featureCategory) &&
          (featureStatus === "all" ||
            (featureStatus === "active"
              ? entry.active
              : featureStatus === "disabled"
                ? !entry.enabled
                : entry.enabled && !entry.active)),
      ),
    [data, featureQuery, featureCategory, featureStatus],
  );
  const audits = (data?.audit || []).filter((entry) =>
    `${AUDIT[entry.action] || entry.action} ${entry.actor_id} ${entry.target} ${entry.detail}`
      .toLowerCase()
      .includes(auditQuery.toLowerCase()),
  );
  const incidentRows = (data?.incidents || []).filter(
    (entry) =>
      incidentStatus === "all" ||
      (incidentStatus === "open"
        ? entry.status !== "resolved"
        : entry.status === incidentStatus),
  );

  if (guildId !== SUPPORT_GUILD_ID)
    return (
      <Empty title="Diese Konsole gehört zum offiziellen Support-Server." />
    );
  if (loading && !data)
    return (
      <div
        role="status"
        className="flex min-h-[360px] items-center justify-center gap-3 text-sm text-slate-400"
      >
        <Loader2 className="h-5 w-5 animate-spin" />
        Owner-Konsole wird geladen …
      </div>
    );
  if (!data)
    return (
      <Section title="Owner-Konsole nicht verfügbar">
        <Notice>{loadError || "Keine Daten verfügbar."}</Notice>
        <div className="mt-4">
          <Action onClick={refresh}>Erneut laden</Action>
        </div>
      </Section>
    );
  const global = data.global,
    deployment = data.deployment;
  const channelValue = errorChannel ?? data.settings.error_channel_id ?? "";
  const selectedTab = TABS.find((entry) => entry.id === tab)!;

  return (
    <div className="mx-auto max-w-7xl space-y-5 pb-16">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--card-border)] pb-5">
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-3 text-primary">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-white">
                Owner-Konsole
              </h1>
              <Badge>Offizieller Support-Server</Badge>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              System prüfen. Fehler bearbeiten. Änderungen nachvollziehen.
            </p>
            <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
              <Clock3 className="h-3.5 w-3.5" />
              Letzter Abruf: {timestamp(updatedAt)}
            </p>
          </div>
        </div>
        <Action disabled={loading || busy} onClick={refresh}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Aktualisieren …" : "Aktualisieren"}
        </Action>
      </header>
      {loadError && (
        <Notice>
          {loadError} Der letzte erfolgreiche Datenstand bleibt sichtbar. Eine
          bereits gespeicherte Aktion wird durch den fehlgeschlagenen Abruf
          nicht zurückgesetzt.
        </Notice>
      )}
      <div className="grid items-start gap-5 lg:grid-cols-[210px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-5">
          <nav
            aria-label="Bereiche der Owner-Konsole"
            className="grid grid-cols-2 gap-1 rounded-2xl border border-[var(--card-border)] bg-[var(--surface)] p-2 sm:grid-cols-4 lg:grid-cols-1"
          >
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                aria-label={label}
                aria-current={tab === id ? "page" : undefined}
                onClick={() => setTab(id)}
                className={`flex min-h-11 items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:text-sm ${tab === id ? "bg-primary/10 text-indigo-300" : "text-slate-500 hover:bg-white/[.03] hover:text-slate-200"}`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="min-w-0 flex-1">{label}</span>
                {id === "errors" && global.open_errors > 0 && (
                  <span className="rounded-md bg-rose-400/10 px-1.5 text-[10px] text-rose-300">
                    {global.open_errors}
                  </span>
                )}
              </button>
            ))}
          </nav>
          <p className="mt-3 hidden px-3 text-xs leading-5 text-slate-600 lg:block">
            Globale Änderungen sind ausschließlich für konfigurierte Owner
            verfügbar.
          </p>
        </aside>
        <main className="min-w-0 space-y-5" aria-label={selectedTab.label}>
          <fieldset
            disabled={busy || Boolean(confirmation)}
            className="min-w-0 space-y-5"
          >
            {tab === "overview" && (
              <>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  {[
                    [
                      "Server",
                      global.guilds.toLocaleString(websiteLocale()),
                      "Verbundene Communities",
                    ],
                    [
                      "Nutzer",
                      global.users.toLocaleString(websiteLocale()),
                      "Mitgliedschaften über alle Server",
                    ],
                    [
                      "Offene Fehler",
                      global.open_errors,
                      "Alle erfassten Fehler",
                    ],
                    [
                      "Offene Incidents",
                      global.open_incidents,
                      "Störungen in Bearbeitung",
                    ],
                  ].map(([label, value, detail]) => (
                    <div key={label} className={CARD + " p-4"}>
                      <p className="text-xs text-slate-500">{label}</p>
                      <p className="mt-2 text-2xl font-semibold text-white">
                        {value}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-600">
                        {detail}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="grid gap-5 xl:grid-cols-2">
                  <Section
                    title="Systemzustand"
                    aside={
                      <Badge
                        tone={
                          /operational|online|connected/i.test(
                            deployment.discord_status,
                          )
                            ? "good"
                            : "warn"
                        }
                      >
                        {deployment.discord_status || "Unbekannt"}
                      </Badge>
                    }
                  >
                    <Row
                      label="Discord-Latenz"
                      value={
                        global.latency_ms === null
                          ? "Noch nicht verfügbar"
                          : `${global.latency_ms} ms`
                      }
                    />
                    <Row
                      label="Laufzeit"
                      value={`${Math.floor(deployment.uptime_seconds / 3600)} h ${Math.floor(deployment.uptime_seconds / 60) % 60} min`}
                    />
                    <Row
                      label="Verwendete Befehle"
                      value={global.commands.toLocaleString(websiteLocale())}
                    />
                    <Row
                      label="Letzter Heartbeat"
                      value={timestamp(deployment.heartbeat)}
                    />
                    <Row
                      label="Letztes Backup"
                      value={timestamp(deployment.last_backup_at)}
                    />
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Badge
                        tone={
                          deployment.failed_extensions?.length ? "bad" : "good"
                        }
                      >
                        {deployment.failed_extensions?.length
                          ? `${deployment.failed_extensions.length} Extensions fehlgeschlagen`
                          : "Alle Extensions geladen"}
                      </Badge>
                      {Boolean(deployment.recovered_extensions?.length) && (
                        <Badge>
                          {deployment.recovered_extensions.length}{" "}
                          wiederhergestellt
                        </Badge>
                      )}
                    </div>
                    {Boolean(deployment.failed_extensions?.length) && (
                      <ul className="mt-3 space-y-1 break-all text-xs text-rose-300">
                        {deployment.failed_extensions.map((entry) => (
                          <li key={entry}>{entry}</li>
                        ))}
                      </ul>
                    )}
                  </Section>
                  <Section
                    title="Deployment"
                    description="Aktuelle Instanz und Veröffentlichungsstand"
                  >
                    <Row label="Instanz" value={deployment.instance} />
                    <Row
                      label="Commit"
                      value={<code>{deployment.commit}</code>}
                    />
                    <Row
                      label="Deployment-ID"
                      value={
                        <code className="break-all text-xs">
                          {deployment.deployment_id}
                        </code>
                      }
                    />
                    <div className="mt-4">
                      <CopyButton
                        value={`Instanz: ${deployment.instance}\nCommit: ${deployment.commit}\nDeployment: ${deployment.deployment_id}\nOffene Fehler: ${global.open_errors}\nOffene Incidents: ${global.open_incidents}`}
                        label="Systemstatus kopieren"
                      />
                    </div>
                  </Section>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    {
                      label: "Fehler bearbeiten",
                      id: "errors",
                      detail: `${global.open_errors} offen`,
                    },
                    {
                      label: "Server prüfen",
                      id: "diagnose",
                      detail: "Diagnose ohne Änderungen",
                    },
                    {
                      label: "Änderungen prüfen",
                      id: "audit",
                      detail: "Wer hat was geändert?",
                    },
                  ].map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() => setTab(item.id as Tab)}
                      className={
                        CARD +
                        " flex items-center justify-between gap-2 p-4 text-left hover:border-primary/40"
                      }
                    >
                      <span>
                        <span className="block text-sm font-medium text-slate-200">
                          {item.label}
                        </span>
                        <span className="mt-1 block text-xs text-slate-500">
                          {item.detail}
                        </span>
                      </span>
                      <ArrowRight className="h-4 w-4 text-slate-500" />
                    </button>
                  ))}
                </div>
                <Section
                  title="Privater Fehlerkanal"
                  description="Automatische Fehlerberichte und Entwickler-Threads im Support-Server"
                >
                  <ChannelPicker
                    guildId={guildId}
                    value={channelValue}
                    onChange={(value) => setErrorChannel(value || "")}
                    placeholder="Privaten Textkanal auswählen …"
                  />
                  <p className="mt-3 text-xs leading-5 text-slate-500">
                    Der Kanal muss für @everyone unsichtbar sein. Der Bot
                    benötigt Nachrichten-, Verlauf- und Threadrechte.
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Action
                      primary
                      disabled={!dirtyChannel || !channelValue}
                      onClick={() =>
                        void perform(
                          async () => {
                            await api.setSupportErrorChannel(
                              guildId,
                              channelValue,
                            );
                            setData((old) =>
                              old
                                ? {
                                    ...old,
                                    settings: {
                                      ...old.settings,
                                      error_channel_id: channelValue,
                                    },
                                  }
                                : old,
                            );
                            setErrorChannel(null);
                          },
                          "Fehlerkanal gespeichert.",
                          true,
                        )
                      }
                    >
                      Fehlerkanal speichern
                    </Action>
                    <Action
                      disabled={!dirtyChannel}
                      onClick={() => setErrorChannel(null)}
                    >
                      Verwerfen
                    </Action>
                    {dirtyChannel && (
                      <span className="text-xs text-amber-300">
                        Ungespeicherte Änderung
                      </span>
                    )}
                  </div>
                </Section>
              </>
            )}

            {tab === "errors" && (
              <Section
                title="Fehlerzentrale"
                description={`Die ${data.errors.length} zuletzt gemeldeten Fehler. Ältere Berichte lassen sich über ihre vollständige Fehler-ID öffnen.`}
                aside={<Badge>{global.open_errors} insgesamt offen</Badge>}
              >
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <Field label="Suchen: Fehler-ID, Funktion, Meldung oder Server">
                    <input
                      className={INPUT}
                      value={errorQuery}
                      onChange={(event) => {
                        setErrorQuery(event.target.value);
                        setLookedUpError(null);
                      }}
                      placeholder="ERR-… oder Suchbegriff"
                    />
                  </Field>
                  <div className="flex items-end">
                    <Action
                      disabled={
                        !/^ERR-\d{8}-[A-F\d]{12}$/i.test(errorQuery.trim())
                      }
                      onClick={() =>
                        void perform(async () => {
                          const result = await api.getSupportOperationError(
                            guildId,
                            errorQuery.trim(),
                          );
                          setLookedUpError(result);
                          setErrorStatus("all");
                        }, "Fehlerbericht geladen.")
                      }
                    >
                      Fehler-ID öffnen
                    </Action>
                  </div>
                </div>
                <div className="my-4 flex flex-wrap items-center gap-3">
                  <Field label="Status">
                    <WebsiteSelect
                      className={INPUT}
                      value={errorStatus}
                      onChange={(event) => setErrorStatus(event.target.value)}
                    >
                      <option value="open">Alle offenen</option>
                      <option value="new">Neu</option>
                      <option value="investigating">In Untersuchung</option>
                      <option value="resolved">Behoben</option>
                      <option value="all">Alle</option>
                    </WebsiteSelect>
                  </Field>
                  <Field label="Sortierung">
                    <WebsiteSelect
                      className={INPUT}
                      value={errorSort}
                      onChange={(event) => setErrorSort(event.target.value)}
                    >
                      <option value="recent">Zuletzt gemeldet</option>
                      <option value="frequency">Am häufigsten</option>
                    </WebsiteSelect>
                  </Field>
                  <span className="ml-auto text-xs text-slate-500">
                    {errorRows.length} Treffer
                  </span>
                </div>
                <div className="space-y-3">
                  {errorRows.map((entry) => (
                    <details
                      key={entry.error_id}
                      className="group overflow-hidden rounded-xl border border-[var(--card-border)] bg-[var(--surface)]"
                    >
                      <summary className="cursor-pointer list-none p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <StateBadge status={entry.status} />
                          <code className="min-w-0 break-all text-[11px] text-slate-500">
                            {entry.error_id}
                          </code>
                          <span className="ml-auto text-xs text-slate-400">
                            {entry.count}×
                          </span>
                        </div>
                        <p className="mt-2 break-words text-sm font-medium text-slate-200">
                          {entry.feature} · {entry.error_type}
                        </p>
                        <p className="mt-1 line-clamp-2 break-words text-xs leading-5 text-slate-500">
                          {entry.summary}
                        </p>
                        <p className="mt-2 text-[11px] text-slate-600">
                          Zuletzt: {timestamp(entry.last_seen)} · Details öffnen
                        </p>
                      </summary>
                      <div className="space-y-4 border-t border-[var(--card-border)] p-4">
                        <div className="grid gap-x-5 sm:grid-cols-2">
                          <Row
                            label="Instanz"
                            value={entry.bot_instance || "Unbekannt"}
                          />
                          <Row
                            label="Server"
                            value={entry.guild_id || "System / DM"}
                          />
                          <Row
                            label="Erstmals"
                            value={timestamp(entry.first_seen)}
                          />
                          <Row
                            label="Zuletzt"
                            value={timestamp(entry.last_seen)}
                          />
                        </div>
                        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-black/20 p-3 text-[11px] leading-5 text-slate-400">
                          {entry.traceback || "Kein Stacktrace vorhanden."}
                        </pre>
                        <div className="flex flex-wrap gap-2">
                          <CopyButton
                            value={`${entry.error_id}\n${entry.feature}\n${entry.summary}\n${entry.traceback}`}
                            label="Fehlerbericht kopieren"
                          />
                          {entry.status !== "investigating" && (
                            <Action
                              onClick={() =>
                                void changeError(entry, "investigating")
                              }
                            >
                              Untersuchen
                            </Action>
                          )}
                          {entry.status !== "resolved" ? (
                            <Action
                              onClick={() =>
                                setConfirmation({
                                  title: "Fehler als behoben markieren?",
                                  description: `${entry.error_id}\n${entry.feature}\nDer Bericht bleibt erhalten. Er wird bei erneutem Auftreten wieder geöffnet.`,
                                  run: async () => {
                                    const result =
                                      await api.setSupportErrorStatus(
                                        guildId,
                                        entry.error_id,
                                        "resolved",
                                      );
                                    setLookedUpError((old) =>
                                      old?.error_id === entry.error_id
                                        ? result
                                        : old,
                                    );
                                  },
                                })
                              }
                            >
                              Als behoben markieren
                            </Action>
                          ) : (
                            <Action
                              onClick={() => void changeError(entry, "new")}
                            >
                              Wieder öffnen
                            </Action>
                          )}
                          {entry.ticket_thread_id ? (
                            <a
                              className="inline-flex items-center gap-2 rounded-xl border border-[var(--card-border)] px-3 py-2 text-sm text-indigo-300"
                              target="_blank"
                              rel="noreferrer"
                              href={`https://discord.com/channels/${guildId}/${entry.ticket_thread_id}`}
                            >
                              <ExternalLink className="h-4 w-4" />
                              Entwickler-Thread
                            </a>
                          ) : (
                            <Action
                              onClick={() =>
                                setConfirmation({
                                  title: "Entwickler-Ticket erstellen?",
                                  description: `Für ${entry.error_id} wird ein Thread im privaten Fehlerkanal angelegt.`,
                                  actionLabel: "Ticket erstellen",
                                  run: async () => {
                                    const result =
                                      await api.createSupportDeveloperTicket(
                                        guildId,
                                        entry.error_id,
                                      );
                                    setLookedUpError((old) =>
                                      old?.error_id === entry.error_id
                                        ? result.error
                                        : old,
                                    );
                                  },
                                })
                              }
                            >
                              <Ticket className="h-4 w-4" />
                              Entwickler-Ticket
                            </Action>
                          )}
                        </div>
                      </div>
                    </details>
                  ))}
                  {errorRows.length === 0 && (
                    <Empty
                      title="Keine passenden Fehler"
                      detail="Ändere den Suchbegriff oder den Statusfilter."
                    />
                  )}
                </div>
              </Section>
            )}

            {tab === "diagnose" && (
              <Section
                title="Server-Diagnose"
                description="Prüft Berechtigungen und Konfigurationen, ohne den Server zu verändern."
              >
                <form
                  className="flex flex-col items-end gap-3 sm:flex-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (validId(targetGuild)) {
                      setDiagnosis(null);
                      void perform(
                        async () =>
                          setDiagnosis(
                            await api.diagnoseSupportServer(
                              guildId,
                              targetGuild,
                            ),
                          ),
                        "Diagnose abgeschlossen.",
                      );
                    }
                  }}
                >
                  <div className="w-full">
                    <Field label="Discord-Server-ID">
                      <input
                        className={INPUT}
                        inputMode="numeric"
                        value={targetGuild}
                        onChange={(event) => {
                          setTargetGuild(digits(event.target.value));
                          setDiagnosis(null);
                          setServer(null);
                        }}
                        placeholder="Server-ID eingeben"
                      />
                    </Field>
                  </div>
                  <Action
                    primary
                    type="submit"
                    disabled={!validId(targetGuild)}
                  >
                    Diagnose starten
                  </Action>
                </form>
                {diagnosis && (
                  <div className="mt-5 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="font-medium text-white">
                          {diagnosis.guild.name}
                        </h3>
                        <p className="text-xs text-slate-500">
                          {diagnosis.guild.id} · {diagnosis.checked}{" "}
                          Konfigurationen geprüft
                        </p>
                      </div>
                      <CopyButton
                        value={`${diagnosis.guild.name} (${diagnosis.guild.id})\n${diagnosis.findings.map((finding) => `${finding.area}: ${finding.problem}\nLösung: ${finding.solution}`).join("\n\n")}`}
                        label="Diagnose kopieren"
                      />
                    </div>
                    {diagnosis.findings.map((finding, index) => (
                      <div
                        key={index}
                        className="rounded-xl border border-[var(--card-border)] bg-[var(--surface)] p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <h4 className="text-sm font-medium text-white">
                            {finding.area}
                          </h4>
                          <Badge
                            tone={
                              finding.severity === "ok"
                                ? "good"
                                : finding.severity === "critical" ||
                                    finding.severity === "high"
                                  ? "bad"
                                  : "warn"
                            }
                          >
                            {finding.severity === "ok"
                              ? "In Ordnung"
                              : SEVERITY[finding.severity] || finding.severity}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm text-slate-400">
                          {finding.problem}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-indigo-300">
                          Lösung: {finding.solution}
                        </p>
                      </div>
                    ))}
                    {diagnosis.findings.length === 0 && (
                      <Empty title="Keine Auffälligkeiten gemeldet" />
                    )}
                  </div>
                )}
              </Section>
            )}

            {tab === "incidents" && (
              <>
                <Section
                  title="Incident eröffnen"
                  description="Titel, Auswirkungen und Schweregrad festhalten."
                >
                  <form
                    className="space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!incidentDraft.title.trim()) return;
                      void perform(
                        async () => {
                          await api.createSupportIncident(guildId, {
                            ...incidentDraft,
                            title: incidentDraft.title.trim(),
                          });
                          setIncidentDraft({
                            title: "",
                            severity: "medium",
                            description: "",
                          });
                        },
                        "Incident eröffnet.",
                        true,
                      );
                    }}
                  >
                    <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
                      <Field label="Titel">
                        <input
                          className={INPUT}
                          maxLength={150}
                          value={incidentDraft.title}
                          onChange={(event) =>
                            setIncidentDraft({
                              ...incidentDraft,
                              title: event.target.value,
                            })
                          }
                          placeholder="Was ist betroffen?"
                        />
                      </Field>
                      <Field label="Schweregrad">
                        <WebsiteSelect
                          className={INPUT}
                          value={incidentDraft.severity}
                          onChange={(event) =>
                            setIncidentDraft({
                              ...incidentDraft,
                              severity: event.target.value,
                            })
                          }
                        >
                          {Object.entries(SEVERITY).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </WebsiteSelect>
                      </Field>
                    </div>
                    <Field label="Auswirkungen und aktueller Stand">
                      <textarea
                        className={INPUT}
                        maxLength={2000}
                        rows={3}
                        value={incidentDraft.description}
                        onChange={(event) =>
                          setIncidentDraft({
                            ...incidentDraft,
                            description: event.target.value,
                          })
                        }
                        placeholder="Welche Funktionen sind betroffen? Was wurde bereits geprüft?"
                      />
                    </Field>
                    <div className="flex gap-2">
                      <Action
                        primary
                        type="submit"
                        disabled={!incidentDraft.title.trim()}
                      >
                        Incident eröffnen
                      </Action>
                      <Action
                        disabled={!dirtyIncident}
                        onClick={() =>
                          setIncidentDraft({
                            title: "",
                            severity: "medium",
                            description: "",
                          })
                        }
                      >
                        Entwurf verwerfen
                      </Action>
                    </div>
                  </form>
                </Section>
                <Section
                  title="Incident-Verlauf"
                  description="Die letzten 25 Incidents mit Status und Zeitlinie."
                  aside={
                    <WebsiteSelect
                      aria-label="Incidents filtern"
                      className={INPUT + " !w-auto"}
                      value={incidentStatus}
                      onChange={(event) =>
                        setIncidentStatus(event.target.value)
                      }
                    >
                      <option value="open">Offene</option>
                      <option value="resolved">Behobene</option>
                      <option value="all">Alle</option>
                    </WebsiteSelect>
                  }
                >
                  <div className="space-y-3">
                    {incidentRows.map((entry) => (
                      <details
                        key={entry.incident_id}
                        className="rounded-xl border border-[var(--card-border)] bg-[var(--surface)]"
                      >
                        <summary className="cursor-pointer list-none p-4">
                          <div className="flex flex-wrap gap-2">
                            <StateBadge status={entry.status} />
                            <Badge
                              tone={
                                entry.severity === "critical" ||
                                entry.severity === "high"
                                  ? "bad"
                                  : "neutral"
                              }
                            >
                              {SEVERITY[entry.severity]}
                            </Badge>
                            <code className="break-all text-[11px] text-slate-500">
                              {entry.incident_id}
                            </code>
                          </div>
                          <p className="mt-2 text-sm font-medium text-white">
                            {entry.title}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            Aktualisiert: {timestamp(entry.updated_at)} ·
                            Verlauf öffnen
                          </p>
                        </summary>
                        <div className="space-y-4 border-t border-[var(--card-border)] p-4">
                          <p className="whitespace-pre-wrap text-sm leading-6 text-slate-400">
                            {entry.description || "Keine Beschreibung."}
                          </p>
                          <ol className="space-y-3 border-l border-[var(--card-border)] pl-4">
                            {timeline(entry.timeline_json).map(
                              (item, index) => (
                                <li key={index}>
                                  <p className="text-xs font-medium text-slate-200">
                                    {item.event}
                                  </p>
                                  <p className="mt-1 text-[11px] text-slate-500">
                                    {timestamp(item.at)} · {item.actor}
                                  </p>
                                  {item.note && (
                                    <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-400">
                                      {item.note}
                                    </p>
                                  )}
                                </li>
                              ),
                            )}
                          </ol>
                          <div className="flex flex-wrap gap-2">
                            {(entry.status === "resolved"
                              ? ["open"]
                              : entry.status === "open"
                                ? ["monitoring", "resolved"]
                                : ["resolved", "open"]
                            ).map((status) => (
                              <Action
                                key={status}
                                onClick={() =>
                                  setConfirmation({
                                    title:
                                      status === "resolved"
                                        ? "Incident abschließen?"
                                        : status === "open"
                                          ? "Incident wieder öffnen?"
                                          : "Incident beobachten?",
                                    description: `${entry.title}\n${entry.incident_id}\nNeuer Status: ${STATUS[status]}`,
                                    note: true,
                                    run: (note) =>
                                      api.updateSupportIncident(
                                        guildId,
                                        entry.incident_id,
                                        { status, note },
                                      ),
                                  })
                                }
                              >
                                {status === "resolved"
                                  ? "Abschließen"
                                  : status === "open"
                                    ? "Wieder öffnen"
                                    : "Beobachten"}
                              </Action>
                            ))}
                          </div>
                        </div>
                      </details>
                    ))}
                    {incidentRows.length === 0 && (
                      <Empty title="Keine Incidents in diesem Filter" />
                    )}
                  </div>
                </Section>
              </>
            )}

            {tab === "features" && (
              <Section
                title="Globale Funktionen"
                description="Aktivierung, Abhängigkeiten und Rollout vor jeder Änderung prüfen."
              >
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Funktion suchen">
                    <input
                      className={INPUT}
                      value={featureQuery}
                      onChange={(event) => setFeatureQuery(event.target.value)}
                      placeholder="Name oder Schlüssel"
                    />
                  </Field>
                  <Field label="Kategorie">
                    <WebsiteSelect
                      className={INPUT}
                      value={featureCategory}
                      onChange={(event) =>
                        setFeatureCategory(event.target.value)
                      }
                    >
                      <option value="all">Alle Kategorien</option>
                      {Array.from(
                        new Set(data.features.map((entry) => entry.category)),
                      )
                        .sort()
                        .map((category) => (
                          <option key={category}>{category}</option>
                        ))}
                    </WebsiteSelect>
                  </Field>
                  <Field label="Zustand">
                    <WebsiteSelect
                      className={INPUT}
                      value={featureStatus}
                      onChange={(event) => setFeatureStatus(event.target.value)}
                    >
                      <option value="all">Alle</option>
                      <option value="active">Wirksam</option>
                      <option value="disabled">Deaktiviert</option>
                      <option value="blocked">Aktiviert, aber blockiert</option>
                    </WebsiteSelect>
                  </Field>
                </div>
                <div className="mt-5 space-y-3">
                  {features.map((entry) => (
                    <div
                      key={`${entry.key}:${entry.enabled}:${entry.rollout_percent}`}
                      className="rounded-xl border border-[var(--card-border)] bg-[var(--surface)] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <h3 className="text-sm font-medium text-white">
                            {entry.label}
                          </h3>
                          <code className="mt-1 block break-all text-[11px] text-slate-500">
                            {entry.key}
                          </code>
                        </div>
                        <Badge
                          tone={
                            entry.active
                              ? "good"
                              : entry.enabled
                                ? "warn"
                                : "neutral"
                          }
                        >
                          {entry.active
                            ? "Wirksam"
                            : entry.enabled
                              ? "Durch Abhängigkeit blockiert"
                              : "Deaktiviert"}
                        </Badge>
                      </div>
                      <p className="mt-3 text-xs leading-5 text-slate-400">
                        {entry.description}
                      </p>
                      {entry.requires?.length > 0 && (
                        <p className="mt-2 break-words text-xs text-slate-500">
                          Benötigt:{" "}
                          {entry.requires
                            .map(
                              (key) =>
                                data.features.find(
                                  (feature) => feature.key === key,
                                )?.label || key,
                            )
                            .join(", ")}
                        </p>
                      )}
                      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
                        <RolloutEditor
                          value={entry.rollout_percent}
                          onSave={(value) =>
                            setConfirmation({
                              title: "Rollout ändern?",
                              description: `${entry.label}\n${entry.rollout_percent}% → ${value}%\n${entry.effect}`,
                              run: () =>
                                api.updateSupportFeature(guildId, entry.key, {
                                  rollout: value,
                                }),
                            })
                          }
                        />
                        <Action
                          onClick={() =>
                            setConfirmation({
                              title: entry.enabled
                                ? "Funktion deaktivieren?"
                                : "Funktion aktivieren?",
                              description: `${entry.label}\n${entry.effect}${entry.requires?.length ? "\nDie Funktion wird nur bei erfüllten Abhängigkeiten wirksam." : ""}`,
                              run: () =>
                                api.updateSupportFeature(guildId, entry.key, {
                                  enabled: !entry.enabled,
                                }),
                            })
                          }
                        >
                          {entry.enabled ? "Deaktivieren" : "Aktivieren"}
                        </Action>
                      </div>
                    </div>
                  ))}
                  {features.length === 0 && (
                    <Empty title="Keine passenden Funktionen" />
                  )}
                </div>
              </Section>
            )}

            {tab === "lookup" && (
              <>
                <Section
                  title="Server-Lookup"
                  description="Serverdetails, Bot-Berechtigungen und Premiumstatus."
                >
                  <form
                    className="flex flex-col items-end gap-3 sm:flex-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (validId(targetGuild)) {
                        setServer(null);
                        void perform(
                          async () =>
                            setServer(
                              await api.lookupSupportServer(
                                guildId,
                                targetGuild,
                              ),
                            ),
                          "Server geladen.",
                        );
                      }
                    }}
                  >
                    <div className="w-full">
                      <Field label="Discord-Server-ID">
                        <input
                          className={INPUT}
                          value={targetGuild}
                          inputMode="numeric"
                          onChange={(event) => {
                            setTargetGuild(digits(event.target.value));
                            setServer(null);
                            setDiagnosis(null);
                          }}
                          placeholder="Server-ID"
                        />
                      </Field>
                    </div>
                    <Action
                      primary
                      type="submit"
                      disabled={!validId(targetGuild)}
                    >
                      <Search className="h-4 w-4" />
                      Server laden
                    </Action>
                  </form>
                  {server && (
                    <div className="mt-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-white">
                            {server.name}
                          </h3>
                          <p className="text-xs text-slate-500">{server.id}</p>
                        </div>
                        <Action
                          onClick={() => {
                            setTargetGuild(server.id);
                            setDiagnosis(null);
                            setTab("diagnose");
                          }}
                        >
                          Diesen Server diagnostizieren
                          <ArrowRight className="h-4 w-4" />
                        </Action>
                      </div>
                      <div className="mt-3 grid gap-x-5 sm:grid-cols-2">
                        <Row
                          label="Inhaber"
                          value={`${server.owner_name} (${server.owner_id})`}
                        />
                        <Row
                          label="Mitglieder"
                          value={server.members.toLocaleString(websiteLocale())}
                        />
                        <Row
                          label="Kanäle / Rollen"
                          value={`${server.channels} / ${server.roles}`}
                        />
                        <Row
                          label="Bot beigetreten"
                          value={timestamp(server.joined_at)}
                        />
                        <Row
                          label="Premium"
                          value={
                            server.premium.active
                              ? "Aktiv"
                              : server.premium.frozen
                                ? "Abgelaufen, Konfiguration eingefroren"
                                : "Inaktiv"
                          }
                        />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {[
                          ["administrator", "Administrator"],
                          ["send_messages", "Nachrichten"],
                          ["manage_roles", "Rollenverwaltung"],
                        ].map(([key, label]) => (
                          <Badge
                            key={key}
                            tone={server.bot_permissions[key] ? "good" : "warn"}
                          >
                            {label}:{" "}
                            {server.bot_permissions[key] ? "Ja" : "Nein"}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </Section>
                <Section
                  title="Premium-Historie"
                  description="Account-, Serverplatz- und Kaufhistorie ohne Änderungen"
                >
                  <form
                    className="space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (
                        (premiumIds.server || premiumIds.user) &&
                        (!premiumIds.server || validId(premiumIds.server)) &&
                        (!premiumIds.user || validId(premiumIds.user))
                      ) {
                        setPremium(null);
                        void perform(
                          async () =>
                            setPremium(
                              await api.getSupportPremiumHistory(
                                guildId,
                                premiumIds.server,
                                premiumIds.user,
                              ),
                            ),
                          "Premium-Historie geladen.",
                        );
                      }
                    }}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Server-ID (optional)">
                        <input
                          className={INPUT}
                          value={premiumIds.server}
                          inputMode="numeric"
                          onChange={(event) => {
                            setPremiumIds({
                              ...premiumIds,
                              server: digits(event.target.value),
                            });
                            setPremium(null);
                          }}
                        />
                      </Field>
                      <Field label="Nutzer-ID (optional)">
                        <input
                          className={INPUT}
                          value={premiumIds.user}
                          inputMode="numeric"
                          onChange={(event) => {
                            setPremiumIds({
                              ...premiumIds,
                              user: digits(event.target.value),
                            });
                            setPremium(null);
                          }}
                        />
                      </Field>
                    </div>
                    <Action
                      primary
                      type="submit"
                      disabled={
                        !(premiumIds.server || premiumIds.user) ||
                        Boolean(
                          premiumIds.server && !validId(premiumIds.server),
                        ) ||
                        Boolean(premiumIds.user && !validId(premiumIds.user))
                      }
                    >
                      Historie laden
                    </Action>
                  </form>
                  {premium && (
                    <div className="mt-5 space-y-5">
                      {premium.server && (
                        <div>
                          <h3 className="text-sm font-medium text-white">
                            Server {premium.server.guild_id}
                          </h3>
                          <Row
                            label="Premiumstatus"
                            value={
                              premium.server.active
                                ? "Aktiv"
                                : premium.server.frozen
                                  ? "Eingefroren"
                                  : "Inaktiv"
                            }
                          />
                          <Row
                            label="Zuweisung"
                            value={
                              premium.server.assigned
                                ? premium.server.direct_admin_grant
                                  ? "Direkte Freischaltung"
                                  : `Serverplatz ${premium.server.slot_no}`
                                : "Kein Serverplatz zugewiesen"
                            }
                          />
                          <Row
                            label="Läuft ab"
                            value={timestamp(premium.server.expires_at)}
                          />
                        </div>
                      )}
                      {premium.account && (
                        <div>
                          <h3 className="text-sm font-medium text-white">
                            Account {premium.account.user_id}
                          </h3>
                          <Row
                            label="Premiumstatus"
                            value={
                              premium.account.premium ? "Aktiv" : "Inaktiv"
                            }
                          />
                          <Row
                            label="Laufzeit"
                            value={
                              premium.account.lifetime
                                ? "Dauerhaft"
                                : timestamp(premium.account.expires_at)
                            }
                          />
                          <Row
                            label="Quelle"
                            value={
                              premium.account.source || "Keine Freischaltung"
                            }
                          />
                          {premium.account.note && (
                            <Row label="Notiz" value={premium.account.note} />
                          )}
                          <h4 className="mb-2 mt-4 text-xs font-medium text-slate-400">
                            Serverplätze
                          </h4>
                          {premium.account.slots.length ? (
                            premium.account.slots.map((slot) => (
                              <Row
                                key={slot.slot_no}
                                label={`Platz ${slot.slot_no}`}
                                value={slot.guild_id}
                              />
                            ))
                          ) : (
                            <p className="text-xs text-slate-500">
                              Keine Serverplätze belegt.
                            </p>
                          )}
                          <h4 className="mb-2 mt-4 text-xs font-medium text-slate-400">
                            Kaufanfragen
                          </h4>
                          {premium.account.purchase_requests.length ? (
                            premium.account.purchase_requests.map((request) => (
                              <Row
                                key={request.id}
                                label={`#${request.id} · ${request.duration_days} Tage`}
                                value={
                                  <span>
                                    {STATUS[request.status] || request.status}
                                    <br />
                                    <span className="text-xs text-slate-500">
                                      {timestamp(request.created_at)}
                                    </span>
                                  </span>
                                }
                              />
                            ))
                          ) : (
                            <p className="text-xs text-slate-500">
                              Keine Kaufanfragen.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </Section>
              </>
            )}

            {tab === "access" && (
              <>
                <Section
                  title="Supportzugriff"
                  description="Aktuellen Supportfall prüfen und Zugriff bei Bedarf gezielt widerrufen."
                >
                  <form
                    className="space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (
                        validId(accessIds.server) &&
                        validId(accessIds.user)
                      ) {
                        setAccessCase(null);
                        void perform(async () => {
                          const result = await api.getSupportAccessCase(
                            guildId,
                            accessIds.server,
                            accessIds.user,
                          );
                          setAccessCase({
                            case: result.case,
                            serverId: accessIds.server,
                            userId: accessIds.user,
                          });
                        }, "Supportfall geprüft.");
                      }
                    }}
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Server-ID">
                        <input
                          className={INPUT}
                          value={accessIds.server}
                          inputMode="numeric"
                          onChange={(event) => {
                            setAccessIds({
                              ...accessIds,
                              server: digits(event.target.value),
                            });
                            setAccessCase(null);
                          }}
                        />
                      </Field>
                      <Field label="Supporter-ID">
                        <input
                          className={INPUT}
                          value={accessIds.user}
                          inputMode="numeric"
                          onChange={(event) => {
                            setAccessIds({
                              ...accessIds,
                              user: digits(event.target.value),
                            });
                            setAccessCase(null);
                          }}
                        />
                      </Field>
                    </div>
                    <Action
                      primary
                      type="submit"
                      disabled={
                        !validId(accessIds.server) || !validId(accessIds.user)
                      }
                    >
                      Zugriff prüfen
                    </Action>
                  </form>
                  {accessCase && (
                    <div className="mt-5">
                      {accessCase.case ? (
                        <>
                          <Row label="Fall" value={`#${accessCase.case.id}`} />
                          <Row
                            label="Server / Supporter"
                            value={
                              <span className="break-all">
                                {accessCase.serverId}
                                <br />
                                {accessCase.userId}
                              </span>
                            }
                          />
                          <Row
                            label="Status"
                            value={
                              <StateBadge status={accessCase.case.status} />
                            }
                          />
                          <Row
                            label="Problem"
                            value={
                              accessCase.case.problem ||
                              "Kein Problem beschrieben"
                            }
                          />
                          <Row
                            label="Akzeptiert"
                            value={timestamp(accessCase.case.accepted_at)}
                          />
                          {["pending", "accepted"].includes(
                            accessCase.case.status,
                          ) && (
                            <div className="mt-4">
                              <Action
                                danger
                                onClick={() => {
                                  const target = accessCase;
                                  setConfirmation({
                                    title: "Supportzugriff widerrufen?",
                                    description: `Fall #${target.case!.id}\nServer: ${target.serverId}\nSupporter: ${target.userId}\nDer Fall wird geschlossen und der Dashboardzugriff endet sofort.`,
                                    actionLabel: "Zugriff widerrufen",
                                    run: async () => {
                                      await api.revokeSupportAccessCase(
                                        guildId,
                                        target.serverId,
                                        target.userId,
                                      );
                                      setAccessCase(null);
                                    },
                                  });
                                }}
                              >
                                Zugriff widerrufen
                              </Action>
                            </div>
                          )}
                        </>
                      ) : (
                        <Empty
                          title="Kein Supportfall gefunden"
                          detail={`Server ${accessCase.serverId} · Supporter ${accessCase.userId}`}
                        />
                      )}
                    </div>
                  )}
                </Section>
                <Section
                  title="Template-Inspektor"
                  description="Sichere Metadaten- und Secret-Prüfung ohne Payload-Ausgabe"
                >
                  <form
                    className="flex flex-col items-end gap-3 sm:flex-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (validId(templateId)) {
                        setTemplate(null);
                        void perform(
                          async () =>
                            setTemplate({
                              result: await api.inspectSupportTemplate(
                                guildId,
                                templateId,
                              ),
                              id: templateId,
                            }),
                          "Vorlage geprüft.",
                        );
                      }
                    }}
                  >
                    <div className="w-full">
                      <Field label="Template-ID">
                        <input
                          className={INPUT}
                          value={templateId}
                          inputMode="numeric"
                          onChange={(event) => {
                            setTemplateId(digits(event.target.value));
                            setTemplate(null);
                          }}
                        />
                      </Field>
                    </div>
                    <Action
                      primary
                      type="submit"
                      disabled={!validId(templateId)}
                    >
                      Vorlage prüfen
                    </Action>
                  </form>
                  {template && (
                    <div className="mt-5">
                      <h3 className="text-sm font-medium text-white">
                        {template.result.template.name} · #{template.id}
                      </h3>
                      <Row
                        label="Sichtbarkeit"
                        value={template.result.template.visibility}
                      />
                      <Row
                        label="Quellserver"
                        value={template.result.template.source_guild_id}
                      />
                      <Row
                        label="Größe"
                        value={`${template.result.inspection.size.toLocaleString(websiteLocale())} Zeichen`}
                      />
                      <Row
                        label="Bereiche"
                        value={
                          template.result.inspection.modules.join(", ") ||
                          "Keine Bereiche"
                        }
                      />
                      <div className="mt-3">
                        <Badge
                          tone={
                            template.result.inspection.contains_secret
                              ? "bad"
                              : "good"
                          }
                        >
                          {template.result.inspection.contains_secret
                            ? "Möglicher geheimer Wert gefunden"
                            : "Secret-Prüfung unauffällig"}
                        </Badge>
                      </div>
                    </div>
                  )}
                </Section>
              </>
            )}

            {tab === "audit" && (
              <Section
                title="Änderungsverlauf"
                description="Die letzten 50 Änderungen an Fehlern, Incidents, Funktionen und Supportzugriffen."
              >
                <Field label="Aktion, Owner-ID oder Ziel suchen">
                  <input
                    className={INPUT}
                    value={auditQuery}
                    onChange={(event) => setAuditQuery(event.target.value)}
                    placeholder="Suchbegriff"
                  />
                </Field>
                <div className="mt-5 space-y-3">
                  {audits.map((entry) => (
                    <div
                      key={entry.id}
                      className="rounded-xl border border-[var(--card-border)] bg-[var(--surface)] p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-medium text-slate-200">
                          {AUDIT[entry.action] || entry.action}
                        </h3>
                        <span className="text-[11px] text-slate-500">
                          {timestamp(entry.created_at)}
                        </span>
                      </div>
                      <p className="mt-2 break-all text-xs text-slate-400">
                        Owner: {entry.actor_id} · Ziel: {entry.target || "–"}
                      </p>
                      {entry.detail && (
                        <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-500">
                          {entry.detail}
                        </p>
                      )}
                    </div>
                  ))}
                  {audits.length === 0 && (
                    <Empty title="Keine passenden Änderungen" />
                  )}
                </div>
              </Section>
            )}
          </fieldset>
          {busy && (
            <div
              role="status"
              className="flex items-center gap-2 text-xs text-indigo-300"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Anfrage wird verarbeitet …
            </div>
          )}
        </main>
      </div>
      {confirmation && (
        <ConfirmDialog
          confirmation={confirmation}
          busy={busy}
          onCancel={() => setConfirmation(null)}
          onConfirm={(note) => {
            const request = confirmation;
            void perform(
              () => request.run(note),
              "Änderung gespeichert.",
              true,
            );
          }}
        />
      )}
    </div>
  );
}

function RolloutEditor({
  value,
  onSave,
}: {
  value: number;
  onSave: (value: number) => void;
}) {
  useWebsiteLocale();
  const [draft, setDraft] = useState(String(value));
  const number = Number(draft);
  const valid =
    draft.trim() !== "" &&
    Number.isInteger(number) &&
    number >= 0 &&
    number <= 100;
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label={`Rollout · gespeichert: ${value}%`}>
        <input
          className={INPUT + " !w-24"}
          type="number"
          min={0}
          max={100}
          step={1}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </Field>
      <Action
        disabled={!valid || number === value}
        onClick={() => {
          onSave(number);
          setDraft(String(value));
        }}
      >
        Rollout prüfen
      </Action>
      {draft !== String(value) && (
        <Action onClick={() => setDraft(String(value))}>Zurücksetzen</Action>
      )}
    </div>
  );
}
