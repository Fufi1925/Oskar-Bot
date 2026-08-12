"use client";

/**
 * Bewerbungen einrichten.
 *
 * Aufgebaut wie die Ticket-Panels, weil der Ablauf derselbe ist: ein
 * Panel steht in einem Kanal, darin Kategorien, und wer eine auswählt
 * startet etwas. Wer Tickets bedienen kann, findet sich hier sofort
 * zurecht.
 *
 * Der Unterschied steckt in den Fragen: jede Kategorie hat ihre
 * eigenen, mindestens drei und höchstens zwanzig, und die stellt der
 * Bot einzeln per Direktnachricht.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Check, ChevronDown, ClipboardList, GripVertical, Loader2, Plus, Send,
  Trash2, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, MultiRolePicker } from "@/components/dashboard/pickers";
import { SwitchToggle } from "@/components/dashboard/form-elements";

const INPUT =
  "w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500";

interface Category {
  category_id?: number;
  name: string;
  emoji: string;
  description: string;
  questions: string[];
  results_channel_id: string | null;
  /** Bis zu fuenf Rollen, die beim Annehmen vergeben werden. */
  accept_roles: string[];
  staff_roles: string[];
}

interface Panel {
  panel_id: number;
  name: string;
  channel_id: string | null;
  message_id: string | null;
  results_channel_id: string | null;
  embed_title: string;
  embed_description: string;
  embed_color: number;
  placeholder: string;
  deny_cooldown_enabled: boolean;
  deny_cooldown_days: number;
  categories: Category[];
}

function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-black uppercase tracking-wider text-slate-400">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[11px] text-slate-500 italic">{hint}</span>}
    </label>
  );
}

/**
 * Die Fragenliste.
 *
 * Der Entwurf lebt hier oben, nicht in jedem Eingabefeld: sonst
 * verliert das Feld beim Tippen den Fokus, weil React die Liste neu
 * zeichnet. Gespeichert wird erst beim Klick auf Speichern — bei bis
 * zu zwanzig Fragen wäre eine Anfrage pro Tastendruck unsinnig.
 */
function QuestionList({
  questions, onChange, min, max,
}: {
  questions: string[];
  onChange: (next: string[]) => void;
  min: number;
  max: number;
}) {
  const zuwenig = questions.length < min;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-black uppercase tracking-wider text-slate-400">
          Fragen
        </span>
        <span
          className={cn(
            "text-[11px] font-bold",
            zuwenig ? "text-red-400" : "text-slate-500",
          )}
        >
          {questions.length} / {max}
          {zuwenig && ` — mindestens ${min}`}
        </span>
      </div>

      {questions.map((frage, index) => (
        <div key={index} className="flex items-start gap-2">
          <div className="shrink-0 mt-3 text-slate-600">
            <GripVertical className="h-4 w-4" />
          </div>
          <span className="shrink-0 mt-3 text-[11px] font-black text-slate-500 w-5">
            {index + 1}.
          </span>
          <input
            value={frage}
            maxLength={300}
            onChange={(e) => {
              const next = [...questions];
              next[index] = e.target.value;
              onChange(next);
            }}
            placeholder="Warum möchtest du ins Team?"
            className={INPUT}
          />
          <button
            onClick={() => onChange(questions.filter((_, i) => i !== index))}
            className="shrink-0 mt-2.5 text-slate-600 hover:text-red-400 transition-colors"
            aria-label={`Frage ${index + 1} entfernen`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}

      <button
        onClick={() => onChange([...questions, ""])}
        disabled={questions.length >= max}
        className="inline-flex items-center gap-2 text-[11px] font-bold px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors disabled:opacity-40"
      >
        <Plus className="h-3.5 w-3.5" />
        Frage hinzufügen
      </button>
    </div>
  );
}

/** Eine Kategorie zum Aufklappen. */
function CategoryCard({
  guildId, panelId, category, limits, onSaved, onDeleted,
}: {
  guildId: string;
  panelId: number;
  category: Category;
  limits: any;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [offen, setOffen] = useState(!category.category_id);
  const [entwurf, setEntwurf] = useState<Category>(category);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setEntwurf(category);
  }, [category]);

  const speichern = async () => {
    if (!entwurf.name.trim()) return toast.error("Die Kategorie braucht einen Namen.");
    const fragen = entwurf.questions.map((f) => f.trim()).filter(Boolean);
    if (fragen.length < limits.min_questions) {
      return toast.error(
        `Mindestens ${limits.min_questions} Fragen — aktuell ${fragen.length}.`,
      );
    }
    setBusy(true);
    try {
      await api.saveApplicationCategory(guildId, panelId, {
        ...entwurf,
        questions: fragen,
      });
      toast.success("Gespeichert.");
      onSaved();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const loeschen = async () => {
    if (!entwurf.category_id) return onDeleted();
    setBusy(true);
    try {
      await api.deleteApplicationCategory(guildId, entwurf.category_id);
      toast.success("Kategorie gelöscht.");
      onDeleted();
    } catch (err: any) {
      toast.error(err?.message || "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden">
      <button
        onClick={() => setOffen(!offen)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <ChevronDown
          className={cn(
            "h-4 w-4 text-slate-500 transition-transform shrink-0",
            offen && "rotate-180",
          )}
        />
        <span className="text-sm font-bold text-white truncate">
          {entwurf.emoji ? `${entwurf.emoji} ` : ""}
          {entwurf.name || "Neue Kategorie"}
        </span>
        <span className="ml-auto text-[11px] text-slate-500 shrink-0">
          {entwurf.questions.filter(Boolean).length} Fragen
        </span>
      </button>

      {offen && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-800 pt-4">
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2">
              <Field label="Name">
                <input
                  value={entwurf.name}
                  maxLength={80}
                  onChange={(e) => setEntwurf({ ...entwurf, name: e.target.value })}
                  placeholder="Moderator"
                  className={INPUT}
                />
              </Field>
            </div>
            <Field label="Emoji" hint="Steht im Auswahlmenü.">
              <input
                value={entwurf.emoji}
                maxLength={80}
                onChange={(e) => setEntwurf({ ...entwurf, emoji: e.target.value })}
                placeholder="🛡️"
                className={INPUT}
              />
            </Field>
          </div>

          <Field label="Kurzbeschreibung" hint="Erscheint klein unter dem Namen im Menü.">
            <input
              value={entwurf.description}
              maxLength={100}
              onChange={(e) => setEntwurf({ ...entwurf, description: e.target.value })}
              placeholder="Für alle, die im Chat aufpassen wollen"
              className={INPUT}
            />
          </Field>

          <QuestionList
            questions={entwurf.questions}
            onChange={(next) => setEntwurf({ ...entwurf, questions: next })}
            min={limits.min_questions}
            max={limits.max_questions}
          />

          <div className="grid sm:grid-cols-2 gap-4">
            <Field
              label="Bewerbungen landen in"
              hint="Leer lassen für den Kanal des Panels."
            >
              <ChannelPicker
                guildId={guildId}
                value={entwurf.results_channel_id || ""}
                onChange={(id) =>
                  setEntwurf({ ...entwurf, results_channel_id: id || null })
                }
                placeholder="Kanal wählen"
                channelTypes={["0", "5"]}
              />
            </Field>
            <Field
              label={`Rollen beim Annehmen (max. ${limits.accept_roles ?? 5})`}
              hint="Werden automatisch vergeben. Optional."
            >
              <MultiRolePicker
                guildId={guildId}
                value={entwurf.accept_roles || []}
                onChange={(ids) =>
                  // Die Grenze hier UND im Bot: wer sie im Browser
                  // umgeht, wird serverseitig trotzdem gekappt.
                  setEntwurf({
                    ...entwurf,
                    accept_roles: ids.slice(0, limits.accept_roles ?? 5),
                  })
                }
                placeholder="Rollen wählen (optional)"
              />
              {(entwurf.accept_roles || []).length >= (limits.accept_roles ?? 5) && (
                <span className="block text-[11px] text-amber-400 mt-1">
                  Mehr als {limits.accept_roles ?? 5} Rollen gehen nicht.
                </span>
              )}
            </Field>
          </div>

          <Field
            label="Wer darf entscheiden"
            hint="Zusätzlich zu allen, die den Server verwalten dürfen."
          >
            <MultiRolePicker
              guildId={guildId}
              value={entwurf.staff_roles}
              onChange={(ids) => setEntwurf({ ...entwurf, staff_roles: ids })}
              placeholder="Rollen wählen"
            />
          </Field>

          <div className="flex gap-2 pt-1">
            <button
              onClick={speichern}
              disabled={busy}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-500/15 border border-blue-500/30 text-blue-200 font-bold text-xs hover:bg-blue-500/25 transition-colors disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Speichern
            </button>
            <button
              onClick={loeschen}
              disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-red-400 transition-colors text-xs font-bold disabled:opacity-40"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Löschen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ApplicationsPanel({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [limits, setLimits] = useState<any>({
    panels: 2, categories: 8, min_questions: 3, max_questions: 20,
  });
  const [neu, setNeu] = useState<Record<number, Category[]>>({});
  const [eintraege, setEintraege] = useState<any[]>([]);
  const [reiter, setReiter] = useState<"panels" | "entries">("panels");
  const [grund, setGrund] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const daten = await api.getApplicationPanels(guildId);
      setPanels(daten.panels || []);
      setLimits(daten.limits || limits);
      setNeu({});
    } catch (err: any) {
      toast.error(err?.message || "Panels konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const ladeEintraege = useCallback(async () => {
    try {
      const daten = await api.getApplicationEntries(guildId);
      setEintraege(daten.entries || []);
    } catch (err: any) {
      toast.error(err?.message || "Bewerbungen konnten nicht geladen werden.");
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (reiter === "entries") ladeEintraege();
  }, [reiter, ladeEintraege]);

  const patchPanel = async (panelId: number, data: any) => {
    try {
      await api.updateApplicationPanel(guildId, panelId, data);
      setPanels((alt) =>
        alt.map((p) => (p.panel_id === panelId ? { ...p, ...data } : p)),
      );
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
      load();
    }
  };

  const panelAnlegen = async () => {
    setBusy("new");
    try {
      await api.createApplicationPanel(guildId, "Bewerbungen");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Anlegen fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const posten = async (panelId: number) => {
    setBusy(`send${panelId}`);
    try {
      const res = await api.sendApplicationPanel(guildId, panelId);
      toast.success(res?.result || "Panel gepostet.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Posten fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const entscheiden = async (id: number, status: "accepted" | "denied") => {
    const text = (grund[id] || "").trim();
    if (!text) return toast.error("Bitte eine Begründung angeben.");
    setBusy(`d${id}`);
    try {
      const res = await api.decideApplication(guildId, id, status, text);
      toast.success(
        (status === "accepted" ? "Angenommen." : "Abgelehnt.") +
          (res?.dm_delivered ? "" : " (DM konnte nicht zugestellt werden.)"),
      );
      // Rollen, die der Bot nicht vergeben konnte, muss jemand von Hand
      // nachtragen — das darf nicht in einer Erfolgsmeldung untergehen.
      if (res?.roles_failed?.length) {
        toast.error(
          `Nicht vergeben: ${res.roles_failed.join(", ")} — bitte von Hand nachtragen.`,
          { duration: 10000 },
        );
      }
      setGrund({ ...grund, [id]: "" });
      await ladeEintraege();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-slate-600" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* ── Reiter ────────────────────────────────────────────── */}
      <div className="flex gap-2">
        {([["panels", "Einrichten"], ["entries", "Eingegangen"]] as const).map(
          ([id, label]) => (
            <button
              key={id}
              onClick={() => setReiter(id)}
              className={cn(
                "px-5 py-2.5 rounded-xl text-[11px] font-black uppercase tracking-wider border transition-colors",
                reiter === id
                  ? "bg-blue-500/15 border-blue-500/30 text-blue-200"
                  : "bg-white/[0.02] border-white/5 text-slate-500 hover:text-white",
              )}
            >
              {label}
            </button>
          ),
        )}
      </div>

      {reiter === "panels" && (
        <>
          {panels.map((panel) => {
            const entwuerfe = neu[panel.panel_id] || [];
            const gesamt = panel.categories.length + entwuerfe.length;

            return (
              <div
                key={panel.panel_id}
                className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card"
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex gap-3">
                    <div className="shrink-0 h-10 w-10 rounded-2xl bg-blue-500/15 border border-blue-500/25 grid place-items-center">
                      <ClipboardList className="h-5 w-5 text-blue-300" />
                    </div>
                    <div>
                      <h3 className="font-bold text-white">{panel.name}</h3>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {panel.message_id
                          ? "Im Kanal gepostet."
                          : "Noch nicht gepostet."}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => posten(panel.panel_id)}
                      disabled={busy === `send${panel.panel_id}`}
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 font-bold text-xs hover:bg-emerald-500/25 transition-colors disabled:opacity-40"
                    >
                      {busy === `send${panel.panel_id}` ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Send className="h-3.5 w-3.5" />
                      )}
                      {panel.message_id ? "Neu posten" : "Posten"}
                    </button>
                    <button
                      onClick={async () => {
                        await api.deleteApplicationPanel(guildId, panel.panel_id);
                        toast.success("Panel gelöscht.");
                        load();
                      }}
                      className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-500 hover:text-red-400 transition-colors"
                      aria-label="Panel löschen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-5">
                  <Field label="Panel-Name" hint="Nur intern, im Dashboard.">
                    <input
                      defaultValue={panel.name}
                      maxLength={80}
                      onBlur={(e) =>
                        e.target.value !== panel.name &&
                        patchPanel(panel.panel_id, { name: e.target.value })
                      }
                      className={INPUT}
                    />
                  </Field>
                  <Field label="Panel-Kanal" hint="Dorthin kommt das Auswahlmenü.">
                    <ChannelPicker
                      guildId={guildId}
                      value={panel.channel_id || ""}
                      onChange={(id) =>
                        patchPanel(panel.panel_id, { channel_id: id || null })
                      }
                      placeholder="Kanal wählen"
                      channelTypes={["0", "5"]}
                    />
                  </Field>
                </div>

                <div className="grid md:grid-cols-2 gap-5">
                  <Field label="Überschrift">
                    <input
                      defaultValue={panel.embed_title}
                      maxLength={250}
                      onBlur={(e) =>
                        e.target.value !== panel.embed_title &&
                        patchPanel(panel.panel_id, { embed_title: e.target.value })
                      }
                      className={INPUT}
                    />
                  </Field>
                  <Field
                    label="Bewerbungen landen in"
                    hint="Gilt für alle Kategorien ohne eigenen Kanal."
                  >
                    <ChannelPicker
                      guildId={guildId}
                      value={panel.results_channel_id || ""}
                      onChange={(id) =>
                        patchPanel(panel.panel_id, { results_channel_id: id || null })
                      }
                      placeholder="Kanal wählen"
                      channelTypes={["0", "5"]}
                    />
                  </Field>
                </div>

                <Field label="Beschreibung">
                  <textarea
                    defaultValue={panel.embed_description}
                    rows={2}
                    maxLength={4000}
                    onBlur={(e) =>
                      e.target.value !== panel.embed_description &&
                      patchPanel(panel.panel_id, {
                        embed_description: e.target.value,
                      })
                    }
                    placeholder="Wähle unten aus, wofür du dich bewerben möchtest."
                    className={INPUT}
                  />
                </Field>

                <Field label="Text im Auswahlmenü">
                  <input
                    defaultValue={panel.placeholder}
                    maxLength={140}
                    onBlur={(e) =>
                      e.target.value !== panel.placeholder &&
                      patchPanel(panel.panel_id, { placeholder: e.target.value })
                    }
                    placeholder="Wofür möchtest du dich bewerben?"
                    className={INPUT}
                  />
                </Field>

                {/* ── Sperre nach Ablehnung ─────────────────── */}
                <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-4 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-bold text-slate-200">
                        Sperre nach einer Ablehnung
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Wer abgelehnt wurde, kann sich für diese Kategorie eine
                        Weile nicht erneut bewerben. Andere Kategorien bleiben frei.
                      </p>
                    </div>
                    <SwitchToggle
                      checked={panel.deny_cooldown_enabled}
                      onCheckedChange={(v) =>
                        patchPanel(panel.panel_id, { deny_cooldown_enabled: v })
                      }
                      label="Sperre nach Ablehnung"
                    />
                  </div>
                  <div
                    className={cn(
                      "flex items-center gap-2",
                      !panel.deny_cooldown_enabled && "opacity-40",
                    )}
                  >
                    <input
                      type="number"
                      min={1}
                      max={365}
                      defaultValue={panel.deny_cooldown_days}
                      disabled={!panel.deny_cooldown_enabled}
                      onBlur={(e) => {
                        const tage = Math.max(1, Math.min(365, Number(e.target.value) || 7));
                        if (tage !== panel.deny_cooldown_days) {
                          patchPanel(panel.panel_id, { deny_cooldown_days: tage });
                        }
                      }}
                      className="w-24 bg-slate-900/60 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
                    />
                    <span className="text-xs text-slate-500 font-bold">Tage</span>
                  </div>
                </div>

                {/* ── Kategorien ────────────────────────────── */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="font-bold text-white text-sm">Kategorien</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Jede wird ein Eintrag im Auswahlmenü, mit eigenen Fragen.
                      </p>
                    </div>
                    <span className="text-[11px] font-bold text-slate-500">
                      {gesamt} / {limits.categories}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {panel.categories.map((kategorie) => (
                      <CategoryCard
                        key={kategorie.category_id}
                        guildId={guildId}
                        panelId={panel.panel_id}
                        category={kategorie}
                        limits={limits}
                        onSaved={load}
                        onDeleted={load}
                      />
                    ))}

                    {entwuerfe.map((entwurf, index) => (
                      <CategoryCard
                        key={`neu-${index}`}
                        guildId={guildId}
                        panelId={panel.panel_id}
                        category={entwurf}
                        limits={limits}
                        onSaved={load}
                        onDeleted={() =>
                          setNeu({
                            ...neu,
                            [panel.panel_id]: entwuerfe.filter((_, i) => i !== index),
                          })
                        }
                      />
                    ))}
                  </div>

                  <button
                    onClick={() =>
                      setNeu({
                        ...neu,
                        [panel.panel_id]: [
                          ...entwuerfe,
                          {
                            name: "",
                            emoji: "",
                            description: "",
                            questions: ["", "", ""],
                            results_channel_id: null,
                            accept_roles: [],
                            staff_roles: [],
                          },
                        ],
                      })
                    }
                    disabled={gesamt >= limits.categories}
                    className="mt-3 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors text-xs font-bold disabled:opacity-40"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Kategorie hinzufügen
                  </button>
                </div>
              </div>
            );
          })}

          <button
            onClick={panelAnlegen}
            disabled={panels.length >= limits.panels || busy === "new"}
            className="w-full inline-flex items-center justify-center gap-2 px-5 py-4 rounded-3xl bg-white/[0.02] border border-dashed border-white/10 text-slate-400 hover:text-white transition-colors font-bold text-sm disabled:opacity-40"
          >
            <Plus className="h-4 w-4" />
            {panels.length >= limits.panels
              ? `Mehr als ${limits.panels} Panels gehen nicht`
              : "Weiteres Panel anlegen"}
          </button>
        </>
      )}

      {/* ── Eingegangene Bewerbungen ───────────────────────────── */}
      {reiter === "entries" && (
        <div className="space-y-3">
          {eintraege.length === 0 ? (
            <div className="bg-[#131318] border border-slate-800 rounded-3xl p-10 text-center">
              <ClipboardList className="h-10 w-10 text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-500">
                Noch keine Bewerbung eingegangen.
              </p>
            </div>
          ) : (
            eintraege.map((eintrag) => (
              <div
                key={eintrag.id}
                className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card"
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex gap-3 min-w-0">
                    {eintrag.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={eintrag.avatar}
                        alt=""
                        className="h-10 w-10 rounded-2xl shrink-0"
                      />
                    ) : null}
                    <div className="min-w-0">
                      <p className="font-bold text-white truncate">
                        {eintrag.username || eintrag.user_id}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {eintrag.category_name} · #{eintrag.id}
                      </p>
                    </div>
                  </div>
                  <span
                    className={cn(
                      "text-[10px] font-black px-2.5 py-1 rounded-lg shrink-0",
                      eintrag.status === "open" && "bg-blue-500/15 text-blue-300",
                      eintrag.status === "accepted" && "bg-emerald-500/15 text-emerald-300",
                      eintrag.status === "denied" && "bg-red-500/15 text-red-300",
                    )}
                  >
                    {eintrag.status === "open"
                      ? "OFFEN"
                      : eintrag.status === "accepted"
                        ? "ANGENOMMEN"
                        : "ABGELEHNT"}
                  </span>
                </div>

                <div className="space-y-2">
                  {(eintrag.answers || []).map((antwort: string, i: number) => (
                    <div
                      key={i}
                      className="bg-white/[0.02] border border-white/5 rounded-2xl p-3"
                    >
                      <p className="text-[11px] font-bold text-slate-500 mb-1">
                        Antwort {i + 1}
                      </p>
                      <p className="text-sm text-slate-300 break-words whitespace-pre-wrap">
                        {antwort}
                      </p>
                    </div>
                  ))}
                </div>

                {eintrag.status === "open" ? (
                  <div className="space-y-2">
                    <input
                      value={grund[eintrag.id] || ""}
                      onChange={(e) =>
                        setGrund({ ...grund, [eintrag.id]: e.target.value })
                      }
                      placeholder="Begründung (Pflicht) — der Bewerber bekommt sie per DM"
                      maxLength={1000}
                      className={INPUT}
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => entscheiden(eintrag.id, "accepted")}
                        disabled={busy === `d${eintrag.id}`}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 font-bold text-xs hover:bg-emerald-500/25 transition-colors disabled:opacity-40"
                      >
                        <Check className="h-3.5 w-3.5" />
                        Annehmen
                      </button>
                      <button
                        onClick={() => entscheiden(eintrag.id, "denied")}
                        disabled={busy === `d${eintrag.id}`}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500/15 border border-red-500/30 text-red-200 font-bold text-xs hover:bg-red-500/25 transition-colors disabled:opacity-40"
                      >
                        <X className="h-3.5 w-3.5" />
                        Ablehnen
                      </button>
                    </div>
                  </div>
                ) : (
                  eintrag.reason && (
                    <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-3">
                      <p className="text-[11px] font-bold text-slate-500 mb-1">
                        Begründung
                      </p>
                      <p className="text-sm text-slate-300">{eintrag.reason}</p>
                    </div>
                  )
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
