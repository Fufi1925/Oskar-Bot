"use client";

import React, { useCallback, useState } from "react";
import {
  Activity,
  AlertTriangle,
  AtSign,
  ChevronDown,
  Hash,
  Link as LinkIcon,
  Loader2,
  MessageSquare,
  Save,
  Search,
  Shield,
  Smile,
  SlidersHorizontal,
  Type,
  Users,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { WebsiteSelect } from "@/components/ui/website-select";
import { filterRules, ruleDefaults, validateRules } from "@/lib/security-rules";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { translateWebsiteText } from "@/lib/i18n/dom-translations";
import {
  MultiChannelPicker,
  MultiRolePicker,
} from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { LogUmgezogen } from "@/components/dashboard/log-umgezogen";
import {
  Loading,
  StickySaveBar,
  usePanel,
  useSaveGuard,
} from "@/components/dashboard/save-bar";
import {
  SecurityCard as Card,
  SecurityField as Field,
  SecurityMetrics,
  SecurityTabs,
  SecurityWarnings as Warnings,
} from "@/components/dashboard/security-workspace";

const ICONS: Record<string, typeof Shield> = {
  spam: Zap,
  caps: Type,
  links: LinkIcon,
  invites: MessageSquare,
  mentions: AtSign,
  emoji: Smile,
};
const PUNISHMENTS: Record<string, { label: string; hint: string }> = {
  delete: {
    label: "Nachricht löschen",
    hint: "Löscht die Nachricht ohne weitere Sanktion.",
  },
  warn: {
    label: "Verwarnen",
    hint: "Vermerkt eine Verwarnung, ohne das Mitglied zu sperren.",
  },
  mute: {
    label: "Timeout",
    hint: "Schränkt das Mitglied für die eingestellte Dauer ein.",
  },
  kick: {
    label: "Kicken",
    hint: "Entfernt das Mitglied. Ein erneuter Beitritt ist möglich.",
  },
  ban: {
    label: "Bannen",
    hint: "Entfernt das Mitglied und verhindert einen erneuten Beitritt.",
  },
};

function RuleCard({ rule, draft, onChange, master, busy }: any) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[rule.key] || Shield;
  const value = (field: string) =>
    draft?.[field] !== undefined ? draft[field] : rule[field];
  const enabled = !!value("enabled");
  const punishment = value("punishment") || "mute";
  const active = enabled && master;
  return (
    <article
      className={`cloudtix-security-rule ${enabled ? "is-enabled" : ""}`}
    >
      <header className="cloudtix-security-rule-heading">
        <span className="cloudtix-security-rule-icon">
          <Icon size={18} />
        </span>
        <div>
          <h3>{rule.label}</h3>
          <p>{rule.description}</p>
        </div>
        <InlineToggle
          ariaLabel={rule.label}
          label=""
          checked={enabled}
          disabled={!master || busy}
          onCheckedChange={(enabled: boolean) => onChange({ enabled })}
        />
      </header>
      <div className="cloudtix-security-rule-status">
        <span className="cloudtix-settings-badge">
          <i data-active={active} />
          {active ? "Eingeschaltet" : enabled ? "Pausiert" : "Ausgeschaltet"}
        </span>
        {enabled && (
          <span>
            Ab {value("threshold") ?? rule.defaults.threshold}{" "}
            {rule.threshold_label}
          </span>
        )}
        {enabled && (
          <span>
            {PUNISHMENTS[punishment]?.label ?? punishment}
            {punishment === "mute" && ` · ${value("duration")} Min.`}
          </span>
        )}
      </div>
      <button
        type="button"
        className="cloudtix-security-rule-edit"
        aria-expanded={open}
        aria-controls={`automod-rule-${rule.key}`}
        onClick={() => setOpen(!open)}
      >
        <span>Grenzwerte & Aktion</span>
        <ChevronDown size={15} className={open ? "rotate-180" : ""} />
      </button>
      <fieldset
        id={`automod-rule-${rule.key}`}
        hidden={!open}
        disabled={busy}
        className="cloudtix-security-rule-fields"
      >
        <Field
          label="Aktion bei einem Verstoß"
          hint={PUNISHMENTS[punishment]?.hint}
        >
          <WebsiteSelect
            aria-label={`${rule.label}: Aktion`}
            value={punishment}
            onChange={(e) => onChange({ punishment: e.target.value })}
            className="cloudtix-security-input"
          >
            {Object.entries(PUNISHMENTS).map(([id, spec]) => (
              <option key={id} value={id}>
                {spec.label}
              </option>
            ))}
          </WebsiteSelect>
        </Field>
        <div className="cloudtix-security-number-fields">
          <Field
            label={`Grenzwert · ${rule.threshold_label}`}
            hint={`${rule.threshold_min} bis ${rule.threshold_max}`}
          >
            <input
              aria-label={`${rule.label}: Grenzwert`}
              type="number"
              min={rule.threshold_min}
              max={rule.threshold_max}
              step={1}
              className="cloudtix-security-input"
              value={value("threshold") ?? rule.defaults.threshold}
              onChange={(e) => onChange({ threshold: Number(e.target.value) })}
            />
          </Field>
          {punishment === "mute" && (
            <Field label="Timeout · Minuten" hint="Bis zu 7 Tage">
              <input
                aria-label={`${rule.label}: Timeout in Minuten`}
                type="number"
                min={1}
                max={10080}
                step={1}
                className="cloudtix-security-input"
                value={value("duration") ?? rule.defaults.duration}
                onChange={(e) => onChange({ duration: Number(e.target.value) })}
              />
            </Field>
          )}
          {rule.has_window && (
            <Field label="Zeitfenster · Sekunden" hint="2 bis 120 Sekunden">
              <input
                aria-label={`${rule.label}: Zeitfenster in Sekunden`}
                type="number"
                min={2}
                max={120}
                step={1}
                className="cloudtix-security-input"
                value={value("window") ?? 10}
                onChange={(e) => onChange({ window: Number(e.target.value) })}
              />
            </Field>
          )}
        </div>
        <button
          type="button"
          onClick={() => onChange(ruleDefaults(rule))}
          className="cloudtix-security-text-button justify-self-start"
        >
          Standardwerte übernehmen
        </button>
      </fieldset>
    </article>
  );
}

export function AutomodPanel({
  guildId,
  liveStatus,
}: {
  guildId: string;
  liveStatus?: React.ReactNode;
}) {
  const { language } = useLanguage();
  const load = useCallback(() => api.getAutomod(guildId), [guildId]);
  const p = usePanel(load);
  const [view, setView] = useState("rules");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  // Flash the bar red instead of a browser dialog: the dialog cannot
  // be styled, and half the time the browser suppresses it anyway.
  const guard = useSaveGuard(p.dirty, "automod-save-bar");

  if (p.loading) return <Loading />;
  if (!p.data)
    return (
      <Card icon={AlertTriangle} title="AutoMod konnte nicht geladen werden">
        <button
          type="button"
          onClick={p.reload}
          className="text-sm text-blue-300"
        >
          Erneut versuchen
        </button>
      </Card>
    );

  const master = !!p.value("enabled");
  const rules: any[] = p.data?.rules || [];
  const ruleDraft = p.draft.rules || {};

  const changeRule = (key: string, patch: any) =>
    p.set("rules", {
      ...ruleDraft,
      [key]: { ...(ruleDraft[key] || {}), ...patch },
    });

  const activeNow = rules.filter((r) =>
    ruleDraft[r.key]?.enabled !== undefined
      ? ruleDraft[r.key].enabled
      : r.enabled,
  ).length;

  const refreshLiveStatus = () =>
    window.dispatchEvent(new CustomEvent("automod-saved", { detail: guildId }));

  const visibleRules = filterRules(rules, ruleDraft, query, filter, (text) =>
    translateWebsiteText(text, language),
  );
  const invalid = validateRules(rules, ruleDraft);

  const save = async () => {
    if (invalid)
      return toast.error("Bitte prüfe die Grenzwerte deiner Regeln.");
    const result = await p.act(() => api.updateAutomod(guildId, p.draft));
    if (result) refreshLiveStatus();
  };

  const reset = async () => {
    const result = await p.act(
      () => api.resetAutomod(guildId),
      "Automod ausschalten? Deine Regeln bleiben gespeichert.",
    );
    if (result) refreshLiveStatus();
  };

  return (
    <section className="cloudtix-settings-page cloudtix-security-page">
      <header className="cloudtix-settings-heading">
        <div>
          <p className="cloudtix-workspace-eyebrow">MODERATION / AUTOMOD</p>
          <h1>AutoMod</h1>
          <p>
            Fange Spam, unerwünschte Links und Massenpings ab. Du bestimmst die
            Grenzen und die Reaktion.
          </p>
        </div>
        <div className="cloudtix-security-heading-actions">
          <div className="cloudtix-security-master">
            <span>AutoMod aktivieren</span>
            <InlineToggle
              label=""
              ariaLabel="AutoMod aktivieren"
              checked={master}
              disabled={p.busy}
              onCheckedChange={(v: boolean) => p.set("enabled", v)}
            />
          </div>
          <button
            type="button"
            className="cloudtix-workspace-action"
            disabled={!p.dirty || p.busy || !!invalid}
            onClick={save}
          >
            {p.busy ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Save size={15} />
            )}
            Speichern
          </button>
        </div>
      </header>
      <SecurityMetrics
        items={[
          {
            label: "Hauptschalter",
            value: master ? "An" : "Aus",
            icon: Shield,
            note: p.dirty
              ? "Entwurf · noch nicht gespeichert"
              : "Gespeicherte Einstellung",
          },
          {
            label: "Eingeschaltete Regeln",
            value: `${activeNow} / ${rules.length}`,
            icon: SlidersHorizontal,
            note: master
              ? "Regeln nach deiner Konfiguration"
              : "Pausiert, solange AutoMod aus ist",
          },
          {
            label: "Eigene Ausnahmen",
            value:
              (p.value("ignored_roles") || []).length +
              (p.value("ignored_channels") || []).length,
            icon: Users,
            note: "Ausgenommene Rollen und Kanäle",
          },
        ]}
      />
      <Warnings items={p.data?.warnings} />
      <SecurityTabs
        value={view}
        onChange={setView}
        items={[
          ["rules", "Regeln", SlidersHorizontal],
          ["exceptions", "Ausnahmen & Logs", Users],
          ["live", "Live-Status", Activity],
        ]}
        label="AutoMod-Bereiche"
      />
      <div hidden={view !== "rules"} className="space-y-5">
        <div className="cloudtix-security-subheading">
          <div>
            <h2>Nachrichten filtern</h2>
            <p>
              Schalte Regeln einzeln ein und öffne die Einstellungen für
              Grenzwerte und Aktionen.
            </p>
          </div>
          <span className="cloudtix-settings-badge">
            {visibleRules.length} Regeln
          </span>
        </div>
        {!master && (
          <div className="cloudtix-settings-running">
            <Shield size={18} />
            <p>
              AutoMod ist ausgeschaltet. Deine Regeln bleiben gespeichert und
              lassen sich vorbereiten.
            </p>
          </div>
        )}
        <div className="cloudtix-security-toolbar">
          <div className="cloudtix-settings-search">
            <Search size={16} />
            <input
              aria-label="Regel suchen"
              placeholder="Regeln durchsuchen …"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="cloudtix-security-input"
            />
          </div>
          <div>
            <WebsiteSelect
              aria-label="Regeln filtern"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="cloudtix-security-input"
            >
              <option value="all">Alle Regeln</option>
              <option value="enabled">Eingeschaltet</option>
              <option value="disabled">Ausgeschaltet</option>
            </WebsiteSelect>
          </div>
        </div>
        {visibleRules.length ? (
          <div className="cloudtix-security-rules">
            {visibleRules.map((rule) => (
              <RuleCard
                key={rule.key}
                rule={rule}
                draft={ruleDraft[rule.key]}
                master={master}
                busy={p.busy}
                onChange={(patch: any) => changeRule(rule.key, patch)}
              />
            ))}
          </div>
        ) : (
          <div className="cloudtix-settings-empty">
            <Search size={27} />
            <h3>Keine passenden Regeln</h3>
            <p>Ändere den Suchbegriff oder den Filter.</p>
          </div>
        )}
      </div>
      <div hidden={view !== "exceptions"} className="cloudtix-settings-grid">
        <Card
          icon={Users}
          title="Wer wird ausgenommen?"
          subtitle="Ausnahmen gelten für alle AutoMod-Regeln."
        >
          <fieldset disabled={p.busy} className="space-y-5">
            <Field
              label="Rollen ausnehmen"
              hint="Mitglieder mit diesen Rollen werden nicht geprüft."
            >
              <MultiRolePicker
                guildId={guildId}
                value={p.value("ignored_roles") || []}
                onChange={(ids) => p.set("ignored_roles", ids)}
                placeholder="Rollen auswählen"
              />
            </Field>
            <Field
              label="Kanäle ausnehmen"
              hint="In diesen Kanälen greift keine AutoMod-Regel."
            >
              <MultiChannelPicker
                guildId={guildId}
                value={p.value("ignored_channels") || []}
                onChange={(ids) => p.set("ignored_channels", ids)}
                placeholder="Kanäle auswählen"
                channelTypes={["0", "5"]}
              />
            </Field>
          </fieldset>
          <p className="cloudtix-security-note">
            Serverinhaber und Mitglieder mit „Administrator“ oder „Nachrichten
            verwalten“ sind automatisch ausgenommen.
          </p>
        </Card>
        <div className="space-y-5">
          <Card
            icon={Hash}
            title="Moderationsprotokoll"
            subtitle="Nachvollziehen, welche Nachrichten gelöscht und welche Strafen vergeben wurden."
          >
            <LogUmgezogen
              guildId={guildId}
              logKey="automod"
              was="Gelöschte Nachrichten und Strafen"
            />
          </Card>
          <Card
            icon={AlertTriangle}
            title="AutoMod pausieren"
            subtitle="Schaltet die Moderation sofort aus. Deine Regeln bleiben erhalten."
          >
            <button
              type="button"
              className="cloudtix-workspace-action is-secondary"
              onClick={reset}
              disabled={p.busy}
            >
              AutoMod ausschalten
            </button>
          </Card>
        </div>
      </div>
      <div hidden={view !== "live"}>{liveStatus}</div>
      <StickySaveBar
        id="automod-save-bar"
        count={p.dirty}
        busy={p.busy}
        blocked={invalid ? "Bitte prüfe die Grenzwerte deiner Regeln." : null}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={save}
      />
    </section>
  );
}
