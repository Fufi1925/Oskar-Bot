"use client";

import { ModerationTabs } from "@/components/dashboard/moderation-design";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, AtSign, ChevronDown, Hash, Link as LinkIcon, Loader2,
  MessageSquare, RefreshCw, Search, Shield, Smile, Type, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { WebsiteSelect } from "@/components/ui/website-select";
import { filterRules, ruleDefaults, validateRules } from "@/lib/security-rules";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { translateWebsiteText } from "@/lib/i18n/dom-translations";
import { cn } from "@/lib/utils";
import {
  ChannelPicker, MultiChannelPicker, MultiRolePicker,
} from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { LogUmgezogen } from "@/components/dashboard/log-umgezogen";
import {
  Loading, StickySaveBar, usePanel, useSaveGuard,
} from "@/components/dashboard/save-bar";

const INPUT =
  "w-full cloudtix-workspace-field bg-[#18191c] border border-white/[.07] rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

const ICONS: Record<string, any> = {
  spam: Zap,
  caps: Type,
  links: LinkIcon,
  invites: MessageSquare,
  mentions: AtSign,
  emoji: Smile,
};

/** What each punishment actually does, in the order they escalate. */
const PUNISHMENTS: Record<string, { label: string; hint: string }> = {
  delete: { label: "Nur löschen", hint: "Nachricht weg, sonst nichts." },
  warn: { label: "Verwarnen", hint: "Wird notiert, keine Sperre." },
  mute: { label: "Stummschalten", hint: "Timeout für die eingestellte Dauer." },
  kick: { label: "Kicken", hint: "Fliegt raus, darf wiederkommen." },
  ban: { label: "Bannen", hint: "Dauerhaft draußen." },
};

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-xs text-slate-500 leading-relaxed">{hint}</p>}
    </div>
  );
}

function Card({ icon: Icon, title, subtitle, children, onReload, reloadDisabled }: any) {
  return (
    <div className="cloudtix-workspace-card bg-[#202124] border border-white/[.07] rounded-2xl p-4 sm:p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-white">{title}</p>
            {subtitle && (
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {onReload && (
          <button
            onClick={onReload}
            disabled={reloadDisabled}
            title="Status aktualisieren"
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] shrink-0"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Warnings({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-xs text-amber-200/80 leading-relaxed">
        <span className="font-bold">Das läuft so nicht rund:</span>
        <br />
        {items.map((w, i) => (
          <span key={i}>
            • {w}
            <br />
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * One save bar for the whole tab, pinned to the bottom.
 *
 * Turns red and shakes when a navigation is refused -- a browser
 * confirm() cannot be styled and browsers often suppress it.
 */

/** One rule: a switch, and the details folded away behind it. */
function RuleCard({ rule, draft, onChange, master, busy }: any) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[rule.key] || Shield;

  // The draft wins so a half-finished edit is never lost by a reload.
  const value = (field: string) =>
    draft?.[field] !== undefined ? draft[field] : rule[field];

  const enabled = !!value("enabled");
  const punishment = value("punishment") || "mute";

  return (
    <div
      className={cn(
        "rounded-2xl border transition-colors",
        enabled
          ? "cloudtix-workspace-field bg-[#18191c] border-primary/30"
          : "cloudtix-workspace-field bg-[#18191c]/60 border-white/[.07]"
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <div
          className={cn(
            "h-9 w-9 rounded-xl grid place-items-center shrink-0",
            enabled ? "bg-primary/15" : "bg-white/[0.03]"
          )}
        >
          <Icon className={cn("h-4 w-4", enabled ? "text-primary" : "text-slate-500")} />
        </div>

        <div className="min-w-0 flex-1">
          <p className={cn("font-bold text-sm", enabled ? "text-white" : "text-slate-400")}>
            {rule.label}
          </p>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            {rule.description}
          </p>
          {enabled && (
            <p className="text-xs text-slate-500 mt-1.5">
              Ab <span className="text-slate-300 font-bold">{value("threshold")}</span>{" "}
              {rule.threshold_label} →{" "}
              <span className="text-slate-300 font-bold">
                {PUNISHMENTS[punishment]?.label ?? punishment}
              </span>
              {punishment === "mute" && ` (${value("duration")} Min.)`}
            </p>
          )}
        </div>

        <InlineToggle
          ariaLabel={rule.label}
          checked={enabled}
          onCheckedChange={(v: boolean) => onChange({ enabled: v })}
          label=""
          disabled={!master || busy}
        />
      </div>

      {enabled && (
        <>
          <button
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="w-full flex items-center justify-between px-4 py-2.5 border-t border-white/[.05]"
          >
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
              Regel einstellen
            </span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 text-slate-500 transition-transform",
                open && "rotate-180"
              )}
            />
          </button>

          {open && (
            <fieldset disabled={busy} className="px-4 pb-4 space-y-4 disabled:opacity-60">
              <Field label="Strafe">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {Object.entries(PUNISHMENTS).map(([id, spec]) => (
                    <button
                      key={id}
                      onClick={() => onChange({ punishment: id })}
                      title={spec.hint}
                      className={cn(
                        "rounded-xl border px-2 py-2.5 text-xs font-bold transition-all",
                        punishment === id
                          ? "bg-primary/10 border-primary/40 text-white"
                          : "cloudtix-workspace-field bg-[#18191c] border-white/[.07] text-slate-400 hover:border-slate-700"
                      )}
                    >
                      {spec.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  {PUNISHMENTS[punishment]?.hint}
                </p>
              </Field>

              <div className="grid sm:grid-cols-2 gap-4">
                <Field
                  label={`Ab wie vielen ${rule.threshold_label}`}
                  hint={`Erlaubt: ${rule.threshold_min}–${rule.threshold_max}.`}
                >
                  <input
                    type="number"
                    min={rule.threshold_min}
                    max={rule.threshold_max}
                    className={INPUT}
                    value={value("threshold") ?? rule.defaults.threshold}
                    onChange={(e) => onChange({ threshold: Number(e.target.value) })}
                  />
                </Field>

                {punishment === "mute" && (
                  <Field label="Stumm für (Minuten)" hint="1 bis 10.080 Minuten (7 Tage).">
                    <input
                      type="number"
                      min={1}
                      max={10080}
                      className={INPUT}
                      value={value("duration") ?? rule.defaults.duration}
                      onChange={(e) => onChange({ duration: Number(e.target.value) })}
                    />
                  </Field>
                )}

                {rule.has_window && (
                  <Field
                    label="Zeitfenster (Sekunden)"
                    hint="So lange wird mitgezählt."
                  >
                    <input
                      type="number"
                      min={2}
                      max={120}
                      className={INPUT}
                      value={value("window") ?? 10}
                      onChange={(e) => onChange({ window: Number(e.target.value) })}
                    />
                  </Field>
                )}
              </div>

              <button
                onClick={() =>
                  onChange(ruleDefaults(rule))
                }
                className="text-xs text-slate-500 hover:text-slate-300 underline"
              >
                Auf Standard zurücksetzen
              </button>
            </fieldset>
          )}
        </>
      )}
    </div>
  );
}

export function AutomodPanel({ guildId, liveStatus }: { guildId: string; liveStatus?: React.ReactNode }) {
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
  if (!p.data) return <Card icon={AlertTriangle} title="AutoMod konnte nicht geladen werden"><button type="button" onClick={p.reload} className="text-sm text-blue-300">Erneut versuchen</button></Card>;

  const master = !!p.value("enabled");
  const rules: any[] = p.data?.rules || [];
  const ruleDraft = p.draft.rules || {};

  const changeRule = (key: string, patch: any) =>
    p.set("rules", { ...ruleDraft, [key]: { ...(ruleDraft[key] || {}), ...patch } });

  const activeNow = rules.filter((r) =>
    ruleDraft[r.key]?.enabled !== undefined
      ? ruleDraft[r.key].enabled
      : r.enabled
  ).length;

  const refreshLiveStatus = () =>
    window.dispatchEvent(new CustomEvent("automod-saved", { detail: guildId }));

  const visibleRules = filterRules(rules, ruleDraft, query, filter, text => translateWebsiteText(text, language));
  const invalid = validateRules(rules, ruleDraft);

  const save = async () => {
    if (invalid) return toast.error("Bitte prüfe die Grenzwerte deiner Regeln.");
    const result = await p.act(() => api.updateAutomod(guildId, p.draft));
    if (result) refreshLiveStatus();
  };

  const reset = async () => {
    const result = await p.act(
      () => api.resetAutomod(guildId),
      "Automod ausschalten? Deine Regeln bleiben gespeichert."
    );
    if (result) refreshLiveStatus();
  };

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />
      <ModerationTabs value={view} onChange={setView} items={[["rules", "Regeln"], ["exceptions", "Ausnahmen"], ["live", "Live-Status"]]} label="AutoMod-Bereiche" />
      <div hidden={view !== "rules"} className="space-y-5">

      <Card
        icon={Shield}
        title="Automod"
        subtitle="Regeln, die der Bot ohne Nachfragen durchsetzt."
        onReload={p.reload}
        reloadDisabled={p.busy || !!p.dirty}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="cloudtix-workspace-field bg-[#18191c] border border-white/[.07] rounded-2xl px-4 py-3">
            <p className="text-lg font-semibold text-white">
              {master ? "Aktiv" : "Aus"}
            </p>
            <p className="text-xs text-slate-500">Hauptschalter</p>
          </div>
          <div className="cloudtix-workspace-field bg-[#18191c] border border-white/[.07] rounded-2xl px-4 py-3">
            <p className="text-lg font-semibold text-white">{activeNow}</p>
            <p className="text-xs text-slate-500">Eingeschaltete Regeln</p>
          </div>
        </div>

        <InlineToggle
          disabled={p.busy}
          checked={master}
          onCheckedChange={(v: boolean) => p.set("enabled", v)}
          label="Automod aktiv"
          hint="Steht das auf aus, greift keine einzige Regel — egal was unten eingestellt ist."
        />
      </Card>

      <Card
        icon={Zap}
        title="Regeln"
        subtitle="Wähle eine Regel und passe Grenzwerte und Aktionen an. Änderungen werden gemeinsam gespeichert."
      >
        {!master && (
          <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5">
            <p className="text-xs text-slate-500">
              Der Hauptschalter steht auf aus — die Regeln hier sind
              gespeichert, greifen aber nicht.
            </p>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1"><Search className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" /><input aria-label="Regel suchen" placeholder="Regel suchen …" value={query} onChange={e => setQuery(e.target.value)} className={cn(INPUT, "pl-10")} /></div>
          <WebsiteSelect aria-label="Regeln filtern" value={filter} onChange={e => setFilter(e.target.value)} className={cn(INPUT, "sm:w-48")}><option value="all">Alle Regeln</option><option value="enabled">Eingeschaltet</option><option value="disabled">Ausgeschaltet</option></WebsiteSelect>
        </div>
        {visibleRules.length === 0 && <p className="py-6 text-center text-sm text-slate-400">Keine passenden Regeln.</p>}
        <div className="grid lg:grid-cols-2 gap-3 items-start">
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
      </Card>

      </div>
      <div hidden={view !== "exceptions"}>
      <Card icon={Hash} title="Ausnahmen und Log" subtitle="Lege fest, welche Rollen und Kanäle von deinen Regeln ausgenommen sind.">
          <fieldset disabled={p.busy} className="space-y-5 disabled:opacity-60">
            <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5">
              <p className="text-xs text-slate-500 leading-relaxed">
                Serverinhaber und alle mit „Administrator“ oder „Nachrichten
                verwalten“ sind ohnehin ausgenommen — die musst du hier nicht
                eintragen.
              </p>
            </div>

            <Field
              label="Rollen ausnehmen"
              hint="Wer eine dieser Rollen hat, wird von keiner Regel erwischt."
            >
              <MultiRolePicker
                guildId={guildId}
                value={p.value("ignored_roles") || []}
                onChange={(ids) => p.set("ignored_roles", ids)}
                placeholder="Keine"
              />
            </Field>

            <Field
              label="Kanäle ausnehmen"
              hint="In diesen Kanälen greift Automod gar nicht."
            >
              <MultiChannelPicker
                guildId={guildId}
                value={p.value("ignored_channels") || []}
                onChange={(ids) => p.set("ignored_channels", ids)}
                placeholder="Keine"
                channelTypes={["0", "5"]}
              />
            </Field>

            {/* Siehe verify-panel: der Log-Kanal steht jetzt unter
                Bot-Logs, damit es ihn nur einmal gibt. */}
            <LogUmgezogen
              guildId={guildId}
              logKey="automod"
              was="Gelöschte Nachrichten und Strafen"
            />

            <button
              onClick={reset}
              disabled={p.busy}
              className="w-full py-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-xs font-semibold uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
            >
              Automod ausschalten
            </button>
          </fieldset>
      </Card>
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
