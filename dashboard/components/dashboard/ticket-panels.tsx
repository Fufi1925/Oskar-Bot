"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  BellRing, ChevronDown, Loader2, Plus, Send, Settings2, Ticket, Trash2, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, MultiRolePicker } from "@/components/dashboard/pickers";
import { EmojiPicker } from "@/components/dashboard/emoji-picker";
import { EmojiDraftField } from "@/components/dashboard/emoji-field";
import { TicketNotifyPanel } from "@/components/dashboard/ticket-notify-panel";

interface Category {
  category_id?: number;
  name: string;
  emoji: string;
  staff_roles: string[];
  button_style: number;
  discord_category_id: string | null;
}

interface Panel {
  panel_id: number;
  name: string;
  channel_id: string | null;
  message_id: string | null;
  panel_type: string;
  embed_title: string;
  embed_description: string;
  embed_color: number | null;
  embed_image_url: string;
  embed_thumbnail_url: string;
  staff_roles: string[];
  posted: boolean;
  categories: Category[];
}

const BUTTON_STYLES = [
  { value: 1, label: "Blau" },
  { value: 2, label: "Grau" },
  { value: 3, label: "Grün" },
  { value: 4, label: "Rot" },
];

const PRESET_COLORS = ["#5865f2", "#2ecc71", "#e74c3c", "#f1c40f", "#9b59b6"];

function hexOf(color: number | null) {
  return `#${Number(color ?? 0x5865f2).toString(16).padStart(6, "0")}`;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-black uppercase text-slate-500 tracking-widest">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-slate-600">{hint}</p>}
    </div>
  );
}

/**
 * Ticket panels.
 *
 * The previous tab kept the whole configuration in one form and wrote it
 * through a single PATCH, so leaving a section before hitting save lost
 * the input — and one column in that request did not even exist, which
 * aborted the write halfway through.
 *
 * Here every panel, category and the server settings save on their own,
 * immediately, through their own endpoint. A guild can have as many
 * panels as it wants: support in one channel, applications in another.
 */
export function TicketPanels({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [server, setServer] = useState<any>({});
  const [openTickets, setOpenTickets] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [editing, setEditing] = useState<
    { panelId: number; cat: Category; panelType: string } | null
  >(null);
  // The category as the dialog was opened with it.
  const [editingBase, setEditingBase] = useState<string>("");

  /** Open the editor and record the starting point. */
  const openEditor = (next: {
    panelId: number;
    cat: Category;
    panelType: string;
  }) => {
    setEditingBase(JSON.stringify(next.cat));
    setEditing(next);
  };

  /**
   * Close the editor, but not over an unsaved edit.
   *
   * Cancel and the X used to drop everything typed into the dialog
   * without a word. A modal has nowhere to put a sticky bar, so this is
   * the one place a confirm() is the right tool -- there is no page
   * left to scroll a bar into view on.
   */
  const closeEditor = () => {
    const changed = editing && JSON.stringify(editing.cat) !== editingBase;
    if (
      changed &&
      !confirm("Die Änderungen an dieser Kategorie verwerfen?")
    ) {
      return;
    }
    setEditing(null);
  };

  const load = useCallback(async () => {
    try {
      const data = await api.getTicketPanels(guildId);
      setPanels(data.panels || []);
      setServer(data.server || {});
      setOpenTickets(data.open_tickets || 0);
      if (data.panels?.length && expanded === null) {
        setExpanded(data.panels[0].panel_id);
      }
    } catch (err: any) {
      toast.error(err?.message || "Ticket-Einstellungen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  /** Run a request, show the outcome, reload. */
  const run = async (fn: () => Promise<any>, message: string, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return false;
    setBusy(true);
    try {
      await fn();
      toast.success(message);
      await load();
      return true;
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  /** Patch a single panel field — saved on the spot. */
  const patchPanel = (panelId: number, data: any, message = "Gespeichert.") =>
    run(() => api.updateTicketPanel(guildId, panelId, data), message);

  const patchServer = (data: any) =>
    run(() => api.updateTicketServer(guildId, data), "Gespeichert.");

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Category editor ─────────────────────────────── */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden border-glow-card is-clipped">
            <div className="p-6 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-white">
                {editing.cat.category_id ? "Kategorie bearbeiten" : "Neue Kategorie"}
              </h3>
              <button
                onClick={closeEditor}
                className="text-slate-500 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
              <div className="grid grid-cols-[1fr_100px] gap-4">
                <Field label="Name">
                  <input
                    value={editing.cat.name}
                    onChange={(e) =>
                      setEditing({ ...editing, cat: { ...editing.cat, name: e.target.value } })
                    }
                    placeholder="z. B. Support"
                    maxLength={100}
                    className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50"
                  />
                  <div className="mt-2">
                    <EmojiPicker
                      onPick={(raw) => {
                        const next = editing.cat.name + raw;
                        if (next.length > 100) return;
                        setEditing({
                          ...editing,
                          cat: { ...editing.cat, name: next },
                        });
                      }}
                    />
                  </div>
                </Field>
                <Field label="Emoji">
                  <input
                    value={editing.cat.emoji}
                    onChange={(e) =>
                      setEditing({ ...editing, cat: { ...editing.cat, emoji: e.target.value } })
                    }
                    placeholder="🎫"
                    className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                  />
                  {/* Ersetzen statt anhaengen: eine Kategorie traegt
                      genau ein Symbol, im Dropdown wie auf dem Knopf. */}
                  <div className="mt-2">
                    <EmojiPicker
                      label="Symbol wählen"
                      onPick={(raw) =>
                        setEditing({
                          ...editing,
                          cat: { ...editing.cat, emoji: raw },
                        })
                      }
                    />
                  </div>
                </Field>
              </div>

              <Field
                label="Team-Rollen"
                hint="Diese Rollen sehen Tickets dieser Kategorie und werden benachrichtigt."
              >
                <MultiRolePicker
                  guildId={guildId}
                  value={editing.cat.staff_roles}
                  onChange={(ids) =>
                    setEditing({ ...editing, cat: { ...editing.cat, staff_roles: ids } })
                  }
                  placeholder="Rollen wählen"
                />
              </Field>

              <Field
                label="Kanal-Kategorie"
                hint="Hier werden die Ticket-Kanäle angelegt."
              >
                <ChannelPicker
                  guildId={guildId}
                  value={editing.cat.discord_category_id || ""}
                  onChange={(id) =>
                    setEditing({
                      ...editing,
                      cat: { ...editing.cat, discord_category_id: id },
                    })
                  }
                  placeholder="Kategorie wählen"
                  channelTypes={["4"]}
                />
              </Field>

              {/* A dropdown renders one select, so a per-category button
                  colour would have no effect — hide it instead of showing a
                  control that does nothing. */}
              {editing.panelType !== "dropdown" && (
              <Field label="Knopf-Farbe">
                <div className="flex gap-2">
                  {BUTTON_STYLES.map((s) => (
                    <button
                      key={s.value}
                      onClick={() =>
                        setEditing({
                          ...editing,
                          cat: { ...editing.cat, button_style: s.value },
                        })
                      }
                      className={cn(
                        "px-4 py-2.5 rounded-xl text-xs font-bold border transition-all",
                        editing.cat.button_style === s.value
                          ? "bg-primary/15 border-primary/40 text-primary"
                          : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                      )}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </Field>
              )}
            </div>

            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button
                onClick={closeEditor}
                className="flex-1 px-4 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest"
              >
                Abbrechen
              </button>
              <button
                disabled={busy || !editing.cat.name.trim()}
                onClick={async () => {
                  const ok = await run(
                    () => api.saveTicketCategory(guildId, editing.panelId, editing.cat),
                    "Kategorie gespeichert."
                  );
                  if (ok) setEditing(null);
                }}
                className="flex-1 px-4 py-3 rounded-xl bg-primary text-white text-xs font-black uppercase tracking-widest hover:brightness-110 transition-all disabled:opacity-50"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Intro ───────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-primary/20 rounded-3xl p-4 sm:p-6 border-glow-card">
        <div className="flex items-start gap-4">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary shrink-0">
            <Ticket className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-white">Ticket-Panels</h3>
            <p className="text-sm text-slate-400 mt-1.5 leading-relaxed">
              Ein Panel ist eine Nachricht mit Knöpfen. Klickt jemand darauf,
              bekommt er einen privaten Kanal mit deinem Team. Du kannst mehrere
              Panels anlegen — etwa Support in einem Kanal und Bewerbungen in
              einem anderen.
            </p>
            <p className="text-xs text-slate-500 mt-3">
              Alles wird sofort gespeichert. Nach Änderungen an Text oder Farbe
              das Panel neu senden.
              {openTickets > 0 && (
                <> · Aktuell <span className="text-slate-300 font-bold">{openTickets}</span> offene Tickets.</>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* ── Panels ──────────────────────────────────────── */}
      <div className="space-y-4">
        {panels.map((panel) => {
          const open = expanded === panel.panel_id;
          const ready = Boolean(panel.channel_id) && panel.categories.length > 0;

          return (
            <div
              key={panel.panel_id}
              className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden border-glow-card is-clipped"
            >
              {/* header */}
              <div className="p-5 flex items-center gap-4 flex-wrap">
                <button
                  onClick={() => setExpanded(open ? null : panel.panel_id)}
                  className="flex items-center gap-3 flex-1 min-w-0 text-left"
                >
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 text-slate-500 transition-transform shrink-0",
                      open && "rotate-180"
                    )}
                  />
                  <span className="font-bold text-white truncate">{panel.name}</span>
                  <span className="text-xs text-slate-500 shrink-0">
                    {panel.categories.length} Kategorie
                    {panel.categories.length === 1 ? "" : "n"}
                  </span>
                  {panel.posted ? (
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 shrink-0">
                      Gesendet
                    </span>
                  ) : (
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-white/[0.04] text-slate-400 border border-white/10 shrink-0">
                      Nicht gesendet
                    </span>
                  )}
                </button>

                <div className="flex gap-2 shrink-0">
                  <button
                    disabled={busy || !ready}
                    title={
                      ready
                        ? "Panel in den Kanal senden"
                        : "Erst Kanal wählen und eine Kategorie anlegen"
                    }
                    onClick={() =>
                      run(
                        () => api.postTicketPanel(guildId, panel.panel_id),
                        "Panel gesendet."
                      )
                    }
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-white text-xs font-black uppercase tracking-widest hover:brightness-110 transition-all disabled:opacity-40"
                  >
                    <Send className="h-3.5 w-3.5" />
                    {panel.posted ? "Neu senden" : "Senden"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(
                        () => api.deleteTicketPanel(guildId, panel.panel_id),
                        "Panel gelöscht.",
                        `Panel „${panel.name}" mit ${panel.categories.length} Kategorie(n) löschen?`
                      )
                    }
                    className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* body */}
              {open && (
                <div className="border-t border-slate-800 p-6 space-y-6">
                  <div className="grid md:grid-cols-2 gap-5">
                    <Field label="Panel-Name" hint="Nur für dich, intern.">
                      <input
                        defaultValue={panel.name}
                        onBlur={(e) =>
                          e.target.value !== panel.name &&
                          patchPanel(panel.panel_id, { name: e.target.value })
                        }
                        className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50"
                      />
                    </Field>

                    <Field label="Kanal" hint="Dort erscheint das Panel.">
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

                    <Field label="Überschrift">
                      <EmojiDraftField
                        defaultValue={panel.embed_title}
                        onCommit={(next) =>
                          patchPanel(panel.panel_id, { embed_title: next })
                        }
                        limit={256}
                        placeholder="z. B. Support"
                      />
                    </Field>

                    <Field
                      label="Darstellung"
                      hint={
                        panel.categories.length > 5
                          ? "Bei mehr als 5 Kategorien ist ein Dropdown nötig — Discord erlaubt nur 5 Knöpfe."
                          : "Knöpfe sind direkt sichtbar, ein Dropdown spart Platz."
                      }
                    >
                      <div className="flex gap-2">
                        {[
                          { value: "button", label: "Knöpfe" },
                          { value: "dropdown", label: "Dropdown" },
                        ].map((o) => (
                          <button
                            key={o.value}
                            onClick={() =>
                              patchPanel(panel.panel_id, { panel_type: o.value })
                            }
                            className={cn(
                              "flex-1 px-4 py-3 rounded-xl text-xs font-bold border transition-all",
                              (panel.panel_type || "button") === o.value
                                ? "bg-primary/15 border-primary/40 text-primary"
                                : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                            )}
                          >
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </Field>

                    <Field label="Farbe">
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={hexOf(panel.embed_color)}
                          onChange={(e) =>
                            patchPanel(panel.panel_id, {
                              embed_color: parseInt(e.target.value.slice(1), 16),
                            })
                          }
                          className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1"
                        />
                        <div className="flex gap-1.5">
                          {PRESET_COLORS.map((hex) => (
                            <button
                              key={hex}
                              onClick={() =>
                                patchPanel(panel.panel_id, {
                                  embed_color: parseInt(hex.slice(1), 16),
                                })
                              }
                              style={{ background: hex }}
                              className="h-7 w-7 rounded-lg border border-white/20 hover:scale-110 transition-transform"
                            />
                          ))}
                        </div>
                      </div>
                    </Field>
                  </div>

                  <Field label="Beschreibung">
                    <EmojiDraftField
                      defaultValue={panel.embed_description}
                      onCommit={(next) =>
                        patchPanel(panel.panel_id, { embed_description: next })
                      }
                      limit={4096}
                      rows={3}
                      placeholder="Klicke unten, um ein Ticket zu öffnen."
                    />
                  </Field>

                  {/* categories */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="font-bold text-white text-sm">Kategorien</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Jede Kategorie wird ein Knopf im Panel.
                        </p>
                      </div>
                      <button
                        onClick={() =>
                          openEditor({
                            panelId: panel.panel_id,
                            panelType: panel.panel_type || "button",
                            cat: {
                              name: "",
                              emoji: "🎫",
                              staff_roles: [],
                              button_style: 2,
                              discord_category_id: null,
                            },
                          })
                        }
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Hinzufügen
                      </button>
                    </div>

                    {panel.categories.length === 0 ? (
                      <p className="text-sm text-slate-500 py-6 text-center border border-dashed border-slate-800 rounded-2xl">
                        Noch keine Kategorie — ohne mindestens eine kann das Panel
                        nicht gesendet werden.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {panel.categories.map((cat) => (
                          <div
                            key={cat.category_id}
                            className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3 flex items-center gap-3 flex-wrap"
                          >
                            <span className="text-lg shrink-0">{cat.emoji || "🎫"}</span>
                            <span className="font-bold text-white truncate flex-1 min-w-[100px]">
                              {cat.name}
                            </span>
                            <span className="text-[11px] text-slate-500">
                              {cat.staff_roles.length} Rolle
                              {cat.staff_roles.length === 1 ? "" : "n"}
                            </span>
                            {!cat.discord_category_id && (
                              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/25">
                                Keine Kanal-Kategorie
                              </span>
                            )}
                            <button
                              onClick={() =>
                                openEditor({
                                  panelId: panel.panel_id,
                                  panelType: panel.panel_type || "button",
                                  cat,
                                })
                              }
                              className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary transition-all"
                            >
                              <Settings2 className="h-4 w-4" />
                            </button>
                            <button
                              disabled={busy}
                              onClick={() =>
                                run(
                                  () =>
                                    api.deleteTicketCategory(guildId, cat.category_id!),
                                  "Kategorie gelöscht.",
                                  `Kategorie „${cat.name}" löschen?`
                                )
                              }
                              className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 transition-all disabled:opacity-40"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        <button
          disabled={busy}
          onClick={async () => {
            const name = prompt("Name des Panels (nur intern):", "Support");
            if (name?.trim()) {
              await run(
                () => api.createTicketPanel(guildId, name.trim()),
                "Panel angelegt."
              );
            }
          }}
          className="w-full flex items-center justify-center gap-2 py-5 rounded-3xl border border-dashed border-slate-700 text-slate-400 hover:text-primary hover:border-primary/40 transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          Weiteres Panel anlegen
        </button>
      </div>

      {/* ── Server-wide ─────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div>
          <h3 className="font-bold text-white">Für alle Panels</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Gilt für jedes Ticket, unabhängig vom Panel.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          <Field label="Transkript-Kanal" hint="Dorthin wird der Verlauf geschlossener Tickets geschickt.">
            <ChannelPicker
              guildId={guildId}
              value={server.logging_channel || ""}
              onChange={(id) => patchServer({ logging_channel: id || null })}
              placeholder="Kanal wählen (optional)"
              channelTypes={["0", "5"]}
            />
          </Field>

          <Field label="Archiv-Kategorie" hint="Geschlossene Tickets werden hierhin verschoben.">
            <ChannelPicker
              guildId={guildId}
              value={server.closed_category || ""}
              onChange={(id) => patchServer({ closed_category: id || null })}
              placeholder="Kategorie wählen (optional)"
              channelTypes={["4"]}
            />
          </Field>
        </div>

        <Field label="Team-Rollen" hint="Diese Rollen sehen jedes Ticket, zusätzlich zu den Rollen der Kategorie.">
          <MultiRolePicker
            guildId={guildId}
            value={server.staff_roles || []}
            onChange={(ids) => patchServer({ staff_roles: ids })}
            placeholder="Rollen wählen"
          />
        </Field>
      </div>

      {/* ── Benachrichtigungen ──────────────────────────── */}
      <div>
        <div className="flex items-center gap-2.5 mb-3 px-1">
          <BellRing className="h-4 w-4 text-slate-400" />
          <h2 className="font-black text-white text-sm uppercase tracking-wider">
            Benachrichtigungen
          </h2>
        </div>
        <TicketNotifyPanel guildId={guildId} />
      </div>
    </div>
  );
}
