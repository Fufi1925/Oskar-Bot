"use client";
import React, { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Clock,
  Copy,
  FileText,
  Loader2,
  Plus,
  Send,
  Settings2,
  Ticket,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Select } from "@/components/ui/select";
import { ChannelPicker, MultiRolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { EmojiText } from "@/components/dashboard/emoji-field";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { TicketNotifyPanel } from "@/components/dashboard/ticket-notify-panel";
import { localizedConfirm } from "@/lib/i18n/browser-language";

const BusyContext = React.createContext(false);
const BOX = "rounded-2xl border border-white/[.07] bg-[#202124] p-4 sm:p-6";
const INPUT =
  "w-full min-w-0 rounded-xl border border-white/[.08] bg-[#18191c] px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-400/60";
const BUTTON =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.04] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.08] disabled:opacity-40";
const defaults: Record<string, any> = {
  active: true,
  prefix: "ticket",
  description: "",
  capacity: 50,
  priority: "normal",
  ping_team: true,
  ticket_limit: 3,
  staff_only_close: true,
  allow_participants: false,
  restrict_claimed: false,
  allow_on_behalf: false,
  on_leave: "none",
  name_format: "{prefix}-{ticket_number}-{username}",
  show_capacity: true,
  timezone: "Europe/Berlin",
  opening_hours: [],
  claim_category_id: "",
  rating_enabled: false,
  rating_channel_id: "",
  rating_public_channel_id: "",
  rating_values: ["creator", "category", "duration"],
  snippets: [],
  auto_close: false,
  auto_close_seconds: 86400,
  auto_alert: false,
  auto_alert_seconds: 86400,
  auto_team_alert: false,
  auto_team_alert_seconds: 86400,
  high_priority_seconds: 0,
  auto_unclaim: false,
  auto_unclaim_seconds: 86400,
  close_after_alert: false,
  auto_claim: false,
  close_after_request: false,
  no_auto_close_priority: "off",
  welcome_image_url: "",
  welcome_thumbnail_url: "",
  opening_questions: null,
  closing_questions: [],
  rating_questions: [],
};
const tabs = [
  ["general", "Allgemein"],
  ["messages", "Nachrichten"],
  ["categories", "Kategorien"],
  ["snippets", "Textbausteine"],
  ["rating", "Bewertungen"],
  ["automation", "Automationen"],
  ["logs", "Protokolle"],
  ["claim", "Übernahme"],
];
const categoryTabs = [
  ["general", "Allgemein"],
  ["messages", "Eröffnungsnachricht"],
  ["opening", "Eröffnungsformular"],
  ["closing", "Schließformular"],
  ["rating", "Bewertungsformular"],
  ["automation", "Automationen"],
];
const priorities = [
  { value: "low", label: "Niedrig" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "Hoch" },
  { value: "urgent", label: "Dringend" },
];
const weekdays = [
  "Montag",
  "Dienstag",
  "Mittwoch",
  "Donnerstag",
  "Freitag",
  "Samstag",
  "Sonntag",
];
function Field({ label, hint, children }: any) {
  return (
    <div className="min-w-0 space-y-2">
      <label className="block text-xs font-medium text-slate-300">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-slate-500">{hint}</p>}
    </div>
  );
}
function Section({ title, hint, children }: any) {
  return (
    <section className={BOX}>
      <h3 className="mb-1 font-semibold text-white">{title}</h3>
      {hint && <p className="mb-5 text-sm text-slate-400">{hint}</p>}
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}
function Navigation({ items, value, onChange }: any) {
  return (
    <nav
      aria-label="Ticket-Einstellungen"
      className="flex gap-1 overflow-x-auto rounded-2xl border border-white/[.07] bg-[#202124] p-2"
    >
      {items.map(([id, label]: string[]) => (
        <button
          key={id}
          type="button"
          aria-current={value === id ? "page" : undefined}
          onClick={() => onChange(id)}
          className={`shrink-0 rounded-xl px-3 py-2 text-sm ${value === id ? "bg-indigo-400/15 text-indigo-300" : "text-slate-400 hover:bg-white/5"}`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
function Text({ value, onChange, limit = 4000, placeholder = "" }: any) {
  return (
    <EmojiText
      disabled={React.useContext(BusyContext)}
      value={value || ""}
      onChange={onChange}
      limit={limit}
      rows={4}
      placeholder={placeholder}
    />
  );
}
function FormEditor({
  value,
  onChange,
  maxFields = 5,
  showPublic = false,
}: any) {
  const fields = value || [];
  return (
    <Section
      title="Formularfelder"
      hint={
        maxFields === 4
          ? "Vier zusätzliche Felder neben der Sternebewertung."
          : "Bis zu fünf Felder. Die Antworten werden direkt im Ticket angezeigt."
      }
    >
      {fields.map((field: any, i: number) => (
        <div
          key={i}
          className="space-y-4 rounded-xl border border-white/[.07] bg-[#18191c] p-4"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">
              {field.label || "Neues Feld"}
            </span>
            <button
              aria-label="Feld löschen"
              className={BUTTON}
              onClick={() =>
                onChange(fields.filter((_: any, n: number) => n !== i))
              }
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
          <Field label="Anzeigename">
            <input
              className={INPUT}
              maxLength={45}
              value={field.label}
              onChange={(e) =>
                onChange(
                  fields.map((x: any, n: number) =>
                    n === i ? { ...x, label: e.target.value } : x,
                  ),
                )
              }
            />
          </Field>
          <Field label="Feldtyp">
            <Select
              value={field.type || "short"}
              onValueChange={(type) =>
                onChange(
                  fields.map((x: any, n: number) =>
                    n === i
                      ? {
                          ...x,
                          type,
                          max_length: type === "paragraph" ? 4000 : 200,
                        }
                      : x,
                  ),
                )
              }
              options={[
                { value: "short", label: "Einzeiliger Text" },
                { value: "paragraph", label: "Mehrzeiliger Text" },
                { value: "select", label: "Optionsauswahl" },
                { value: "checkbox", label: "Checkbox" },
                { value: "radio", label: "Einzelauswahl" },
                { value: "file", label: "Datei" },
                { value: "image", label: "Bild" },
              ]}
            />
          </Field>
          <Field label="Beschreibung">
            <input
              className={INPUT}
              maxLength={100}
              value={field.description || ""}
              onChange={(e) =>
                onChange(
                  fields.map((x: any, n: number) =>
                    n === i ? { ...x, description: e.target.value } : x,
                  ),
                )
              }
            />
          </Field>
          <Field label="Platzhalter">
            <input
              className={INPUT}
              maxLength={100}
              value={field.placeholder || ""}
              onChange={(e) =>
                onChange(
                  fields.map((x: any, n: number) =>
                    n === i ? { ...x, placeholder: e.target.value } : x,
                  ),
                )
              }
            />
          </Field>
          {["select", "radio"].includes(field.type) && (
            <Field label="Optionen" hint="Eine Option pro Zeile.">
              <textarea
                className={INPUT}
                value={(field.options || []).join("\n")}
                onChange={(e) =>
                  onChange(
                    fields.map((x: any, n: number) =>
                      n === i
                        ? { ...x, options: e.target.value.split("\n") }
                        : x,
                    ),
                  )
                }
              />
            </Field>
          )}
          {["short", "paragraph"].includes(field.type) && (
            <Field label="Zeichenlimit">
              <input
                type="number"
                min={1}
                max={4000}
                className={INPUT}
                value={field.max_length || 200}
                onChange={(e) =>
                  onChange(
                    fields.map((x: any, n: number) =>
                      n === i
                        ? { ...x, max_length: Number(e.target.value) }
                        : x,
                    ),
                  )
                }
              />
            </Field>
          )}
          <InlineToggle
            label="Erforderlich"
            checked={!!field.required}
            onCheckedChange={(required) =>
              onChange(
                fields.map((x: any, n: number) =>
                  n === i ? { ...x, required } : x,
                ),
              )
            }
          />
          {showPublic && (
            <InlineToggle
              label="In öffentlicher Bewertung anzeigen"
              checked={!!field.public}
              onCheckedChange={(pub) =>
                onChange(
                  fields.map((x: any, n: number) =>
                    n === i ? { ...x, public: pub } : x,
                  ),
                )
              }
            />
          )}
        </div>
      ))}
      <button
        disabled={fields.length >= maxFields}
        className={BUTTON}
        onClick={() =>
          onChange([
            ...fields,
            {
              label: "",
              type: "short",
              required: true,
              placeholder: "",
              description: "",
              max_length: 200,
              options: [],
            },
          ])
        }
      >
        <Plus className="h-4 w-4" />
        Feld hinzufügen
      </button>
    </Section>
  );
}
function Automations({ settings, set, category = false, overrides = {} }: any) {
  return (
    <Section
      title="Automationen"
      hint={
        category
          ? "Übernimm die Panel-Einstellungen oder lege eigene Regeln für diese Kategorie fest."
          : "Automatische Abläufe richten sich nach der letzten Aktivität im Ticket."
      }
    >
      {[
        ["auto_close", "Inaktive Tickets schließen"],
        ["auto_alert", "Ersteller erinnern"],
        ["auto_team_alert", "Team erinnern"],
        ["auto_unclaim", "Übernahme freigeben"],
        ["close_after_alert", "Nach unbeantworteter Erinnerung schließen"],
        ["auto_claim", "Beim Antworten automatisch übernehmen"],
        ["close_after_request", "Nach bestätigter Schließanfrage schließen"],
      ].map(([key, label]) => (
        <div
          key={key}
          className="space-y-3 border-b border-white/[.06] pb-4 last:border-0"
        >
          {category ? (
            <Field label={label}>
              <Select
                value={key in overrides ? String(overrides[key]) : "inherit"}
                onValueChange={(v) => {
                  set(key, v === "inherit" ? undefined : v === "true");
                  if (v === "inherit" && key + "_seconds" in defaults)
                    set(key + "_seconds", undefined);
                }}
                options={[
                  { value: "inherit", label: "Vom Panel übernehmen" },
                  { value: "true", label: "Aktiviert" },
                  { value: "false", label: "Deaktiviert" },
                ]}
              />
            </Field>
          ) : (
            <InlineToggle
              label={label}
              checked={!!settings[key]}
              onCheckedChange={(v) => set(key, v)}
            />
          )}
          <>
            {key + "_seconds" in defaults && settings[key] && (
              <Field
                label="Zeit bis zur Aktion"
                hint="In Stunden. Mindestens eine Minute."
              >
                <input
                  className={INPUT}
                  type="number"
                  min={1 / 60}
                  step="any"
                  value={settings[key + "_seconds"] / 3600}
                  onChange={(e) =>
                    set(
                      key + "_seconds",
                      Math.round(Number(e.target.value) * 3600),
                    )
                  }
                />
              </Field>
            )}
          </>
        </div>
      ))}
      <Field label="Ab dieser Priorität nicht automatisch schließen">
        <Select
          value={settings.no_auto_close_priority}
          onValueChange={(v) => set("no_auto_close_priority", v)}
          options={[{ value: "off", label: "Aus" }, ...priorities]}
        />
      </Field>
      <Field
        label="Team-Erinnerung bei hoher Priorität"
        hint="Stunden; 0 übernimmt die normale Wartezeit."
      >
        <input
          className={INPUT}
          type="number"
          min={0}
          step="any"
          value={settings.high_priority_seconds / 3600}
          onChange={(e) =>
            set(
              "high_priority_seconds",
              Math.round(Number(e.target.value) * 3600),
            )
          }
        />
      </Field>
    </Section>
  );
}

export function TicketPanels({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [draft, setDraft] = useState<any>(null),
    [base, setBase] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState("general"),
    [category, setCategory] = useState<any>(null),
    [categoryBase, setCategoryBase] = useState<any>(null),
    [catTab, setCatTab] = useState("general"),
    [dialog, setDialog] = useState<"panel" | "category" | null>(null),
    [newName, setNewName] = useState(""),
    [newChannel, setNewChannel] = useState(""),
    [copyFrom, setCopyFrom] = useState(""),
    [serverDraft, setServerDraft] = useState<any>(null);
  const load = useCallback(async () => {
    try {
      const result = await api.getTicketPanels(guildId);
      setData(result);
      setServerDraft(result.server);
      setError("");
      return result;
    } catch (e: any) {
      setError(e.message);
      throw e;
    }
  }, [guildId]);
  useEffect(() => {
    load().catch(() => {});
  }, [load]);
  const [preview, setPreview] = useState<any>(null);
  const previewDraft = JSON.stringify(
    draft
      ? {
          ticket_welcome_title:
            category?.ticket_welcome_title || draft.ticket_welcome_title,
          ticket_welcome_message:
            category?.ticket_welcome_message || draft.ticket_welcome_message,
          ticket_created_message: draft.ticket_created_message,
          ticket_questions: draft.ticket_questions,
          category_id: category?.category_id,
        }
      : {},
  );
  useEffect(() => {
    if (!draft) return;
    let alive = true;
    const timer = setTimeout(() => {
      api
        .ticketPanelVorschau(guildId, draft.panel_id, JSON.parse(previewDraft))
        .then((v) => {
          if (alive) setPreview(v);
        })
        .catch(() => {
          if (alive) setPreview(null);
        });
    }, 500);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [guildId, draft?.panel_id, previewDraft]);
  const dirty =
    !!draft &&
    (JSON.stringify(draft) !== JSON.stringify(base) ||
      JSON.stringify(category) !== JSON.stringify(categoryBase) ||
      JSON.stringify(serverDraft) !== JSON.stringify(data?.server));
  const guard = useSaveGuard(dirty ? 1 : 0, "ticket-workspace-save");
  const preferences = {
    ...defaults,
    ...draft?.settings,
    ...category?.settings,
  };
  const set = (key: string, value: any) => {
    if (busy) return;
    const update = (target: any) => {
      const settings = { ...target.settings };
      if (value === undefined) delete settings[key];
      else settings[key] = value;
      return { ...target, settings };
    };
    category ? setCategory(update) : setDraft(update);
  };
  const patch = (key: string, value: any) => {
    if (busy) return;
    return category
      ? setCategory({ ...category, [key]: value })
      : setDraft({ ...draft, [key]: value });
  };
  const safeNavigate = (action: () => void) => {
    if (
      dirty &&
      !localizedConfirm("Ungespeicherte Ticket-Änderungen verwerfen?")
    )
      return;
    if (dirty) {
      setDraft(structuredClone(base));
      setCategory(structuredClone(categoryBase));
      setServerDraft(data.server);
    }
    action();
  };
  const openPanel = (panel: any) =>
    safeNavigate(() => {
      setDraft(structuredClone(panel));
      setBase(structuredClone(panel));
      setCategory(null);
      setCategoryBase(null);
      setTab("general");
      setServerDraft(data.server);
    });
  const run = async (action: () => Promise<any>) => {
    setBusy(true);
    try {
      return await action();
    } catch (e: any) {
      toast.error(e.message || "Speichern fehlgeschlagen.");
      return null;
    } finally {
      setBusy(false);
    }
  };
  const save = () =>
    run(async () => {
      if (category) {
        await api.saveTicketCategory(guildId, draft.panel_id, category);
        setCategoryBase(structuredClone(category));
      } else {
        const { categories, posted, message_id, ...payload } = draft;
        if (!data.premium_configurable) {
          for (const key of [
            "select_placeholder",
            "ticket_welcome_title",
            "ticket_welcome_message",
            "ticket_created_message",
            "ticket_questions",
          ])
            delete payload[key];
        }
        await api.updateTicketPanel(guildId, draft.panel_id, payload);
        setBase(structuredClone(draft));
      }
      if (JSON.stringify(serverDraft) !== JSON.stringify(data.server))
        await api.updateTicketServer(guildId, serverDraft);
      const next = await load();
      const fresh = next.panels.find((x: any) => x.panel_id === draft.panel_id);
      if (fresh) {
        setDraft(structuredClone(fresh));
        setBase(structuredClone(fresh));
        if (category) {
          const c = fresh.categories.find(
            (x: any) => x.category_id === category.category_id,
          );
          setCategory(c);
          setCategoryBase(structuredClone(c));
        }
      }
      toast.success("Ticket-Einstellungen gespeichert.");
      return true;
    });
  const create = () =>
    run(async () => {
      if (!newName.trim()) throw new Error("Bitte gib einen Namen ein.");
      if (dialog === "panel") {
        if (!newChannel) throw new Error("Bitte wähle einen Kanal.");
        const result = await api.createTicketPanel(
          guildId,
          newName.trim(),
          newChannel,
        );
        const next = await load();
        const panel = next.panels.find(
          (x: any) => x.panel_id === result.panel_id,
        );
        setDraft(panel);
        setBase(structuredClone(panel));
      } else {
        const original = draft.categories.find(
          (x: any) => String(x.category_id) === copyFrom,
        );
        const payload = original
          ? {
              ...structuredClone(original),
              category_id: undefined,
              name: newName.trim(),
            }
          : {
              name: newName.trim(),
              emoji: "",
              staff_roles: [],
              button_style: 2,
              discord_category_id: null,
              settings: {},
            };
        const result = await api.saveTicketCategory(
          guildId,
          draft.panel_id,
          payload,
        );
        const next = await load();
        const panel = next.panels.find(
          (x: any) => x.panel_id === draft.panel_id,
        );
        setDraft(panel);
        setBase(structuredClone(panel));
        const c = panel.categories.find(
          (x: any) => x.category_id === result.category_id,
        );
        setCategory(c);
        setCategoryBase(structuredClone(c));
        setCatTab("general");
      }
      setDialog(null);
      setNewName("");
      setNewChannel("");
      setCopyFrom("");
    });
  if (!data)
    return (
      <section className={BOX}>
        {error ? (
          <>
            <p className="text-rose-300">{error}</p>
            <button className={BUTTON} onClick={() => load().catch(() => {})}>
              Erneut laden
            </button>
          </>
        ) : (
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        )}
      </section>
    );
  return (
    <BusyContext.Provider value={busy}>
      <fieldset disabled={busy} className="min-w-0 space-y-5">
        {dialog && (
          <div
            role="dialog"
            aria-modal="true"
            aria-label={
              dialog === "panel"
                ? "Ticket-Panel erstellen"
                : "Ticket-Kategorie erstellen"
            }
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          >
            <section className={`${BOX} w-full max-w-lg space-y-5 shadow-2xl`}>
              <div className="flex justify-between">
                <h2 className="font-semibold text-white">
                  {dialog === "panel"
                    ? "Ticket-Panel erstellen"
                    : "Ticket-Kategorie erstellen"}
                </h2>
                <button
                  disabled={busy}
                  aria-label="Schließen"
                  onClick={() => setDialog(null)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <fieldset disabled={busy} className="space-y-5">
                <Field label="Name">
                  <input
                    autoFocus
                    className={INPUT}
                    maxLength={80}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </Field>
                {dialog === "panel" ? (
                  <Field label="Panel-Kanal">
                    <ChannelPicker
                      guildId={guildId}
                      value={newChannel}
                      onChange={(v) => setNewChannel(v || "")}
                    />
                  </Field>
                ) : (
                  <Field
                    label="Einstellungen kopieren"
                    hint="Optional: Kopiert Einstellungen und Formulare einer vorhandenen Kategorie."
                  >
                    <Select
                      value={copyFrom}
                      onValueChange={setCopyFrom}
                      options={[
                        { value: "", label: "Neue Kategorie ohne Vorlage" },
                        ...draft.categories.map((c: any) => ({
                          value: String(c.category_id),
                          label: c.name,
                        })),
                      ]}
                    />
                  </Field>
                )}
                <button
                  disabled={
                    busy ||
                    !newName.trim() ||
                    (dialog === "panel" && !newChannel)
                  }
                  onClick={create}
                  className={`${BUTTON} bg-indigo-400/15 text-indigo-300`}
                >
                  <Plus className="h-4 w-4" />
                  Hinzufügen
                </button>
              </fieldset>
            </section>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <section className={BOX}>
            <p className="text-xs text-slate-400">Ticket-Panels</p>
            <p className="mt-2 text-2xl font-semibold text-white">
              {data.panels.length}
            </p>
          </section>
          <section className={BOX}>
            <p className="text-xs text-slate-400">Offene Tickets</p>
            <p className="mt-2 text-2xl font-semibold text-white">
              {data.open_tickets}
            </p>
          </section>
        </div>
        {!draft ? (
          <Section
            title="Ticket-Panels"
            hint="Erstelle getrennte Panels für Support, Bewerbungen oder andere Anliegen."
          >
            {data.panels.map((p: any) => (
              <button
                key={p.panel_id}
                className={`${BUTTON} w-full justify-between p-4`}
                onClick={() => openPanel(p)}
              >
                <span data-no-translate>{p.name}</span>
                <span className="flex items-center gap-3 text-xs text-slate-400">
                  {p.categories.length}
                  <Settings2 className="h-4 w-4" />
                </span>
              </button>
            ))}
            <button className={BUTTON} onClick={() => setDialog("panel")}>
              <Plus className="h-4 w-4" />
              Neues Panel erstellen
            </button>
          </Section>
        ) : (
          <>
            <section className={BOX}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <button
                  className={BUTTON}
                  onClick={() =>
                    safeNavigate(() => {
                      if (category) {
                        setCategory(null);
                        setCategoryBase(null);
                        setDraft(structuredClone(base));
                        setServerDraft(data.server);
                      } else {
                        setDraft(null);
                        setBase(null);
                      }
                    })
                  }
                >
                  <ArrowLeft className="h-4 w-4" />
                  {category ? "Zurück zum Panel" : "Alle Panels"}
                </button>
                <h2
                  data-no-translate
                  className="min-w-0 flex-1 truncate text-lg font-semibold text-white"
                >
                  {category?.name || draft.name}
                </h2>
                <button
                  disabled={busy}
                  className={`${BUTTON} text-rose-300`}
                  onClick={() =>
                    run(async () => {
                      if (
                        !localizedConfirm(
                          category
                            ? "Diese Ticket-Kategorie wirklich löschen?"
                            : "Dieses Ticket-Panel wirklich löschen?",
                        )
                      )
                        return;
                      if (category)
                        await api.deleteTicketCategory(
                          guildId,
                          category.category_id,
                        );
                      else await api.deleteTicketPanel(guildId, draft.panel_id);
                      const next = await load();
                      if (category) {
                        const p = next.panels.find(
                          (x: any) => x.panel_id === draft.panel_id,
                        );
                        setDraft(p);
                        setBase(structuredClone(p));
                        setCategory(null);
                        setCategoryBase(null);
                      } else {
                        setDraft(null);
                        setBase(null);
                      }
                    })
                  }
                >
                  <Trash2 className="h-4 w-4" />
                  Löschen
                </button>
              </div>
              {!category && (
                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <Field label="Panel-Name">
                    <input
                      className={INPUT}
                      maxLength={100}
                      value={draft.name}
                      onChange={(e) => patch("name", e.target.value)}
                    />
                  </Field>
                  <Field label="Panel-Kanal">
                    <ChannelPicker
                      guildId={guildId}
                      value={draft.channel_id || ""}
                      onChange={(v) => patch("channel_id", v)}
                    />
                  </Field>
                  <button
                    disabled={busy || dirty}
                    className={BUTTON}
                    onClick={() =>
                      run(async () => {
                        await api.postTicketPanel(guildId, draft.panel_id);
                        await load();
                        toast.success("Ticket-Panel gesendet.");
                      })
                    }
                  >
                    <Send className="h-4 w-4" />
                    Panel senden
                  </button>
                  {dirty && (
                    <p className="self-center text-xs text-amber-300">
                      Speichere deine Änderungen vor dem Senden.
                    </p>
                  )}
                </div>
              )}
            </section>
            <Navigation
              items={category ? categoryTabs : tabs}
              value={category ? catTab : tab}
              onChange={category ? setCatTab : setTab}
            />
            <fieldset disabled={busy} className="min-w-0 space-y-5">
              {(category ? catTab : tab) === "general" && (
                <>
                  <Section
                    title={
                      category
                        ? "Kategorie-Einstellungen"
                        : "Allgemeine Ticket-Einstellungen"
                    }
                  >
                    {category && (
                      <>
                        <InlineToggle
                          label="Kategorie aktiv"
                          checked={preferences.active}
                          onCheckedChange={(v) => set("active", v)}
                        />
                        <Field label="Kategorie-Name">
                          <input
                            className={INPUT}
                            maxLength={80}
                            value={category.name}
                            onChange={(e) => patch("name", e.target.value)}
                          />
                        </Field>
                        <Field label="Symbol">
                          <Text
                            value={category.emoji}
                            onChange={(v: string) => patch("emoji", v)}
                            limit={128}
                          />
                        </Field>
                        <Field label="Discord-Kategorie">
                          <ChannelPicker
                            guildId={guildId}
                            value={category.discord_category_id || ""}
                            channelTypes={["category", "4"]}
                            onChange={(v) => patch("discord_category_id", v)}
                          />
                        </Field>
                        <Field label="Team-Rollen">
                          <MultiRolePicker
                            guildId={guildId}
                            value={category.staff_roles || []}
                            onChange={(v) => patch("staff_roles", v)}
                          />
                        </Field>
                        <Field label="Button-Farbe">
                          <Select
                            value={String(category.button_style || 2)}
                            onValueChange={(v) =>
                              patch("button_style", Number(v))
                            }
                            options={[
                              { value: "1", label: "Blau" },
                              { value: "2", label: "Grau" },
                              { value: "3", label: "Grün" },
                              { value: "4", label: "Rot" },
                            ]}
                          />
                        </Field>
                        <Field label="Präfix">
                          <input
                            className={INPUT}
                            maxLength={20}
                            value={preferences.prefix}
                            onChange={(e) => set("prefix", e.target.value)}
                          />
                        </Field>
                        <Field label="Beschreibung">
                          <input
                            className={INPUT}
                            maxLength={100}
                            value={preferences.description}
                            onChange={(e) => set("description", e.target.value)}
                          />
                        </Field>
                        <Field
                          label="Auslastungsgrenze"
                          hint="0 deaktiviert die Auslastungsanzeige für diese Kategorie."
                        >
                          <input
                            type="number"
                            min={0}
                            max={1000}
                            className={INPUT}
                            value={preferences.capacity}
                            onChange={(e) =>
                              set("capacity", Number(e.target.value))
                            }
                          />
                        </Field>
                        <Field label="Standard-Priorität">
                          <Select
                            value={preferences.priority}
                            onValueChange={(v) => set("priority", v)}
                            options={priorities}
                          />
                        </Field>
                        <InlineToggle
                          label="Tickets im Auftrag öffnen erlauben"
                          hint="Teammitglieder können mit /ticket create ein Ticket für andere Mitglieder eröffnen."
                          checked={preferences.allow_on_behalf}
                          onCheckedChange={(v) => set("allow_on_behalf", v)}
                        />
                        <InlineToggle
                          label="Chat nach Übernahme einschränken"
                          checked={preferences.restrict_claimed}
                          onCheckedChange={(v) => set("restrict_claimed", v)}
                        />
                      </>
                    )}
                    {!category && (
                      <>
                        <InlineToggle
                          label="Team beim Öffnen markieren"
                          checked={preferences.ping_team}
                          onCheckedChange={(v) => set("ping_team", v)}
                        />
                        <Field
                          label="Gleichzeitige Tickets pro Nutzer"
                          hint="0 bedeutet unbegrenzt."
                        >
                          <input
                            type="number"
                            min={0}
                            max={1000}
                            className={INPUT}
                            value={preferences.ticket_limit}
                            onChange={(e) =>
                              set("ticket_limit", Number(e.target.value))
                            }
                          />
                        </Field>
                        <InlineToggle
                          label="Nur das Team darf Tickets schließen"
                          checked={preferences.staff_only_close}
                          onCheckedChange={(v) => set("staff_only_close", v)}
                        />
                        <InlineToggle
                          label="Weitere Personen hinzufügen erlauben"
                          checked={preferences.allow_participants}
                          onCheckedChange={(v) => set("allow_participants", v)}
                        />
                        <Field label="Aktion beim Verlassen des Servers">
                          <Select
                            value={preferences.on_leave}
                            onValueChange={(v) => set("on_leave", v)}
                            options={[
                              { value: "none", label: "Nichts machen" },
                              { value: "delete", label: "Ticket löschen" },
                              {
                                value: "notify",
                                label: "Info-Nachricht senden",
                              },
                            ]}
                          />
                        </Field>
                        <Field
                          label="Kanalname"
                          hint="{prefix}, {ticket_number}, {username}, {user_id}, {display_name}, {case_id}"
                        >
                          <input
                            className={INPUT}
                            maxLength={100}
                            value={preferences.name_format}
                            onChange={(e) => set("name_format", e.target.value)}
                          />
                        </Field>
                        <InlineToggle
                          label="Ticket-Auslastung im Panel anzeigen"
                          checked={preferences.show_capacity}
                          onCheckedChange={(v) => set("show_capacity", v)}
                        />
                        <Field label="Auswahl der Kategorien">
                          <Select
                            value={draft.panel_type || "button"}
                            onValueChange={(v) => patch("panel_type", v)}
                            options={[
                              { value: "button", label: "Buttons" },
                              { value: "dropdown", label: "Dropdown-Menü" },
                            ]}
                          />
                        </Field>
                        <Field label="Team-Rollen des Panels">
                          <MultiRolePicker
                            guildId={guildId}
                            value={draft.staff_roles || []}
                            onChange={(v) => patch("staff_roles", v)}
                          />
                        </Field>
                      </>
                    )}
                  </Section>
                  {!category && (
                    <Section
                      title="Öffnungszeiten"
                      hint="Tickets bleiben jederzeit verfügbar. Außerhalb dieser Zeiten erscheint ein Hinweis und Team-Erinnerungen pausieren."
                    >
                      <Field label="Zeitzone">
                        <Select
                          value={preferences.timezone}
                          onValueChange={(v) => set("timezone", v)}
                          options={[
                            "Europe/Berlin",
                            "Europe/London",
                            "America/New_York",
                            "UTC",
                          ].map((v) => ({ value: v, label: v }))}
                        />
                      </Field>
                      {preferences.opening_hours.map((h: any, i: number) => (
                        <div
                          key={i}
                          className="grid grid-cols-[1fr_auto] gap-3"
                        >
                          <div className="grid gap-3 sm:grid-cols-3">
                            <Select
                              value={String(h.day)}
                              onValueChange={(v) =>
                                set(
                                  "opening_hours",
                                  preferences.opening_hours.map(
                                    (x: any, n: number) =>
                                      n === i ? { ...x, day: Number(v) } : x,
                                  ),
                                )
                              }
                              options={weekdays.map((label, value) => ({
                                value: String(value),
                                label,
                              }))}
                            />
                            <input
                              aria-label="Beginn"
                              className={INPUT}
                              type="time"
                              value={h.start}
                              onChange={(e) =>
                                set(
                                  "opening_hours",
                                  preferences.opening_hours.map(
                                    (x: any, n: number) =>
                                      n === i
                                        ? { ...x, start: e.target.value }
                                        : x,
                                  ),
                                )
                              }
                            />
                            <input
                              aria-label="Ende"
                              className={INPUT}
                              type="time"
                              value={h.end}
                              onChange={(e) =>
                                set(
                                  "opening_hours",
                                  preferences.opening_hours.map(
                                    (x: any, n: number) =>
                                      n === i
                                        ? { ...x, end: e.target.value }
                                        : x,
                                  ),
                                )
                              }
                            />
                          </div>
                          <button
                            aria-label="Öffnungszeit löschen"
                            className={BUTTON}
                            onClick={() =>
                              set(
                                "opening_hours",
                                preferences.opening_hours.filter(
                                  (_: any, n: number) => n !== i,
                                ),
                              )
                            }
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                      <button
                        className={BUTTON}
                        onClick={() =>
                          set("opening_hours", [
                            ...preferences.opening_hours,
                            { day: 0, start: "09:00", end: "17:00" },
                          ])
                        }
                      >
                        <Clock className="h-4 w-4" />
                        Zeit hinzufügen
                      </button>
                    </Section>
                  )}
                </>
              )}
              {(category ? catTab : tab) === "messages" && (
                <>
                  {!category && (
                    <Section title="Panel-Nachricht">
                      <Field label="Titel">
                        <Text
                          value={draft.embed_title}
                          onChange={(v: string) => patch("embed_title", v)}
                          limit={256}
                        />
                      </Field>
                      <Field label="Beschreibung">
                        <Text
                          value={draft.embed_description}
                          onChange={(v: string) =>
                            patch("embed_description", v)
                          }
                          limit={3000}
                        />
                      </Field>
                      <Field label="Farbe">
                        <input
                          aria-label="Farbe"
                          type="color"
                          className="h-10 w-16 rounded-lg bg-transparent"
                          value={`#${Number(draft.embed_color ?? 0x5865f2)
                            .toString(16)
                            .padStart(6, "0")}`}
                          onChange={(e) =>
                            patch(
                              "embed_color",
                              parseInt(e.target.value.slice(1), 16),
                            )
                          }
                        />
                      </Field>
                      {[
                        ["embed_image_url", "Großes Bild"],
                        ["embed_thumbnail_url", "Kleines Bild"],
                      ].map(([key, label]) => (
                        <Field key={key} label={label}>
                          <input
                            className={INPUT}
                            placeholder="https://…"
                            value={draft[key] || ""}
                            onChange={(e) => patch(key, e.target.value)}
                          />
                        </Field>
                      ))}
                    </Section>
                  )}
                  <Section
                    title="Eröffnungsnachricht"
                    hint={
                      category
                        ? "Leere Texte übernehmen die Eröffnungsnachricht des Panels."
                        : "Mit {user}, {category}, {ticket_number}, {server} und {channel}."
                    }
                  >
                    <fieldset
                      disabled={!data.premium_configurable}
                      className="space-y-5"
                    >
                      <BusyContext.Provider
                        value={busy || !data.premium_configurable}
                      >
                        <Field label="Titel">
                          <Text
                            value={(category || draft).ticket_welcome_title}
                            onChange={(v: string) =>
                              patch("ticket_welcome_title", v)
                            }
                            limit={256}
                          />
                        </Field>
                        <Field label="Nachricht">
                          <Text
                            value={(category || draft).ticket_welcome_message}
                            onChange={(v: string) =>
                              patch("ticket_welcome_message", v)
                            }
                            limit={3000}
                          />
                        </Field>
                        {!category && (
                          <>
                            <Field label="Bestätigung nach Erstellung">
                              <Text
                                value={draft.ticket_created_message}
                                onChange={(v: string) =>
                                  patch("ticket_created_message", v)
                                }
                                limit={1900}
                              />
                            </Field>
                            <Field label="Platzhalter im Dropdown">
                              <input
                                className={INPUT}
                                maxLength={150}
                                value={draft.select_placeholder || ""}
                                onChange={(e) =>
                                  patch("select_placeholder", e.target.value)
                                }
                              />
                            </Field>
                          </>
                        )}
                      </BusyContext.Provider>
                    </fieldset>
                    {!data.premium_configurable && (
                      <p className="text-xs text-amber-300">
                        Eigene Eröffnungstexte erfordern Premium.
                      </p>
                    )}
                    {[
                      ["welcome_image_url", "Bild der Eröffnungsnachricht"],
                      [
                        "welcome_thumbnail_url",
                        "Kleines Bild der Eröffnungsnachricht",
                      ],
                    ].map(([key, label]) => (
                      <Field key={key} label={label}>
                        <input
                          className={INPUT}
                          value={preferences[key]}
                          placeholder="https://…"
                          onChange={(e) => set(key, e.target.value)}
                        />
                      </Field>
                    ))}
                  </Section>
                  {!category && (
                    <Section
                      title="Eröffnungsformular"
                      hint="Diese Fragen gelten für alle Kategorien ohne eigenes Formular."
                    >
                      <fieldset disabled={!data.premium_configurable}>
                        <FormEditor
                          value={draft.ticket_questions || []}
                          onChange={(v: any) => patch("ticket_questions", v)}
                        />
                      </fieldset>
                    </Section>
                  )}
                  <Section title="Vorschau">
                    <div
                      data-no-translate
                      className="space-y-3 rounded-xl border-l-4 border-indigo-400 bg-[#18191c] p-4"
                    >
                      <h4 className="font-semibold text-white">
                        {preview?.titel ||
                          (category || draft).ticket_welcome_title ||
                          draft.ticket_welcome_title}
                      </h4>
                      <p className="whitespace-pre-wrap break-words text-sm text-slate-300">
                        {preview?.nachricht ||
                          (category || draft).ticket_welcome_message ||
                          draft.ticket_welcome_message}
                      </p>
                      {preferences.welcome_image_url && (
                        <img
                          alt="Vorschau"
                          src={preferences.welcome_image_url}
                          className="max-h-44 rounded-lg object-contain"
                        />
                      )}
                    </div>
                  </Section>
                </>
              )}
              {!category && tab === "categories" && (
                <Section
                  title="Ticket-Kategorien"
                  hint="Jede Kategorie kann eigene Rollen, Formulare und Automationen verwenden."
                >
                  {draft.categories.map((c: any) => (
                    <button
                      key={c.category_id}
                      className={`${BUTTON} w-full justify-between p-4`}
                      onClick={() =>
                        safeNavigate(() => {
                          setCategory(structuredClone(c));
                          setCategoryBase(structuredClone(c));
                          setCatTab("general");
                        })
                      }
                    >
                      <span data-no-translate>{c.name}</span>
                      <span className="text-xs text-slate-400">
                        {c.open_tickets || 0} /{" "}
                        {
                          { ...defaults, ...draft.settings, ...c.settings }
                            .capacity
                        }
                      </span>
                    </button>
                  ))}
                  <button
                    className={BUTTON}
                    onClick={() => safeNavigate(() => setDialog("category"))}
                  >
                    <Plus className="h-4 w-4" />
                    Kategorie erstellen
                  </button>
                </Section>
              )}
              {category &&
                ["opening", "closing", "rating"].includes(catTab) && (
                  <>
                    {catTab === "opening" && (
                      <InlineToggle
                        disabled={!data.premium_configurable}
                        label="Eigenes Eröffnungsformular verwenden"
                        checked={category.settings?.opening_questions != null}
                        onCheckedChange={(v) =>
                          set("opening_questions", v ? [] : undefined)
                        }
                      />
                    )}{" "}
                    {(catTab !== "opening" ||
                      category.settings?.opening_questions != null) && (
                      <fieldset
                        disabled={
                          catTab === "opening" && !data.premium_configurable
                        }
                      >
                        <FormEditor
                          showPublic={catTab === "rating"}
                          maxFields={catTab === "rating" ? 4 : 5}
                          value={preferences[catTab + "_questions"]}
                          onChange={(v: any) => set(catTab + "_questions", v)}
                        />
                      </fieldset>
                    )}
                  </>
                )}
              {!category && tab === "snippets" && (
                <Section
                  title="Textbausteine"
                  hint="Das Team kann diese Antworten direkt über das Ticket-Menü senden."
                >
                  {preferences.snippets.map((s: any, i: number) => (
                    <div
                      key={i}
                      className="space-y-3 rounded-xl border border-white/10 p-4"
                    >
                      <Field label="Name">
                        <input
                          className={INPUT}
                          maxLength={80}
                          value={s.name}
                          onChange={(e) =>
                            set(
                              "snippets",
                              preferences.snippets.map((x: any, n: number) =>
                                n === i ? { ...x, name: e.target.value } : x,
                              ),
                            )
                          }
                        />
                      </Field>
                      <Text
                        value={s.text}
                        limit={2000}
                        onChange={(text: string) =>
                          set(
                            "snippets",
                            preferences.snippets.map((x: any, n: number) =>
                              n === i ? { ...x, text } : x,
                            ),
                          )
                        }
                      />
                      <button
                        className={BUTTON}
                        onClick={() =>
                          set(
                            "snippets",
                            preferences.snippets.filter(
                              (_: any, n: number) => n !== i,
                            ),
                          )
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                        Entfernen
                      </button>
                    </div>
                  ))}
                  <button
                    disabled={preferences.snippets.length >= 25}
                    className={BUTTON}
                    onClick={() =>
                      set("snippets", [
                        ...preferences.snippets,
                        { name: "", text: "" },
                      ])
                    }
                  >
                    <Plus className="h-4 w-4" />
                    Textbaustein hinzufügen
                  </button>
                </Section>
              )}
              {!category && tab === "rating" && (
                <Section
                  title="Ticket-Bewertungen"
                  hint="Nach dem Schließen kann der Ersteller eine Bewertung abgeben."
                >
                  <InlineToggle
                    label="Bewertungen aktivieren"
                    checked={preferences.rating_enabled}
                    onCheckedChange={(v) => set("rating_enabled", v)}
                  />
                  {preferences.rating_enabled && (
                    <>
                      <Field label="Bewertungskanal">
                        <ChannelPicker
                          guildId={guildId}
                          value={preferences.rating_channel_id}
                          onChange={(v) => set("rating_channel_id", v || "")}
                        />
                      </Field>
                      <Field label="Öffentlicher Bewertungskanal">
                        <ChannelPicker
                          guildId={guildId}
                          value={preferences.rating_public_channel_id}
                          onChange={(v) =>
                            set("rating_public_channel_id", v || "")
                          }
                        />
                      </Field>
                      <div className="space-y-3">
                        <p className="text-sm text-slate-300">
                          Öffentlich angezeigte Werte
                        </p>
                        {[
                          ["supporter", "Supporter"],
                          ["creator", "Ersteller"],
                          ["case", "Case-ID"],
                          ["category", "Kategorie"],
                          ["panel", "Panel"],
                          ["duration", "Bearbeitungszeit"],
                        ].map(([key, label]) => (
                          <InlineToggle
                            key={key}
                            label={label}
                            checked={preferences.rating_values.includes(key)}
                            onCheckedChange={(v) =>
                              set(
                                "rating_values",
                                v
                                  ? [...preferences.rating_values, key]
                                  : preferences.rating_values.filter(
                                      (x: string) => x !== key,
                                    ),
                              )
                            }
                          />
                        ))}
                      </div>
                    </>
                  )}
                </Section>
              )}
              {(category ? catTab : tab) === "automation" && (
                <Automations
                  settings={preferences}
                  set={set}
                  category={!!category}
                  overrides={category?.settings || {}}
                />
              )}
              {!category && tab === "logs" && (
                <>
                  <Section title="Protokolle und Archiv">
                    <Field label="Protokollkanal">
                      <ChannelPicker
                        guildId={guildId}
                        value={serverDraft.logging_channel || ""}
                        onChange={(v) =>
                          setServerDraft({ ...serverDraft, logging_channel: v })
                        }
                      />
                    </Field>
                    <Field label="Archiv-Kategorie">
                      <ChannelPicker
                        guildId={guildId}
                        value={serverDraft.closed_category || ""}
                        channelTypes={["category", "4"]}
                        onChange={(v) =>
                          setServerDraft({ ...serverDraft, closed_category: v })
                        }
                      />
                    </Field>
                    <Field label="Serverweite Team-Rollen">
                      <MultiRolePicker
                        guildId={guildId}
                        value={serverDraft.staff_roles || []}
                        onChange={(v) =>
                          setServerDraft({ ...serverDraft, staff_roles: v })
                        }
                      />
                    </Field>
                    <InlineToggle
                      label="Transkript immer erstellen"
                      checked={!!serverDraft.always_transcript}
                      onCheckedChange={(v) =>
                        setServerDraft({ ...serverDraft, always_transcript: v })
                      }
                    />
                  </Section>
                  <TicketNotifyPanel guildId={guildId} />
                </>
              )}
              {!category && tab === "claim" && (
                <Section
                  title="Ticket-Übernahme"
                  hint="Übernommene Tickets können in eine eigene Discord-Kategorie verschoben werden."
                >
                  <Field label="Kategorie für übernommene Tickets">
                    <ChannelPicker
                      guildId={guildId}
                      value={preferences.claim_category_id}
                      channelTypes={["category", "4"]}
                      onChange={(v) => set("claim_category_id", v || "")}
                    />
                  </Field>
                  <InlineToggle
                    label="Chat nach Übernahme einschränken"
                    checked={preferences.restrict_claimed}
                    onCheckedChange={(v) => set("restrict_claimed", v)}
                  />
                </Section>
              )}
            </fieldset>
            <StickySaveBar
              id="ticket-workspace-save"
              count={dirty ? 1 : 0}
              busy={busy}
              shake={guard.shake}
              onSave={save}
              onDiscard={() => {
                setDraft(structuredClone(base));
                setCategory(structuredClone(categoryBase));
                setServerDraft(data.server);
              }}
            />
          </>
        )}
      </fieldset>
    </BusyContext.Provider>
  );
}
