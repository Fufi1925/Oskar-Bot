"use client";

/**
 * Wer beim Erwähnen welche Reaktion bekommt.
 *
 * Bisher stand das fest im Code: die beiden Besitzer, mit vier
 * beziehungsweise drei Emojis. Jeder weitere Name bedeutete eine
 * Codeänderung und ein neues Deploy.
 *
 * Die festen Regeln bleiben — sie stehen hier oben, grau und ohne
 * Knöpfe. Ohne sie sähe die Liste aus, als gäbe es keine, und niemand
 * verstünde, warum der Bot trotzdem reagiert.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AtSign,
  Loader2,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmojiPicker } from "@/components/dashboard/emoji-picker";

const CARD =
  "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface EmojiInfo {
  raw: string;
  name: string;
  id: string;
  animated: boolean;
  url: string | null;
}

interface Rule {
  user_id: string;
  emojis: EmojiInfo[];
  /** Der mitgelieferte Stand — nur bei den eingebauten Regeln gefüllt. */
  default_emojis: EmojiInfo[];
  note: string;
  enabled: boolean;
  builtin: boolean;
  /** Weicht das, was gilt, vom Code-Stand ab? */
  customised: boolean;
  name?: string;
  avatar?: string | null;
}

/** Ein Emoji als Bild — Discord liefert jedes auch so aus. */
function Emoji({ info, onRemove }: { info: EmojiInfo; onRemove?: () => void }) {
  return (
    <span
      className="relative inline-flex items-center justify-center h-8 w-8 rounded-lg bg-white/[0.04] border border-slate-800 group"
      title={`:${info.name}:`}
    >
      {info.url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={info.url} alt={info.name} className="h-5 w-5" />
      ) : (
        <span className="text-[10px] text-slate-500">?</span>
      )}
      {onRemove && (
        <button
          onClick={onRemove}
          className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-red-500/80 hover:bg-red-500 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
          title="Entfernen"
        >
          <X className="h-2.5 w-2.5" />
        </button>
      )}
    </span>
  );
}

export function PingReactionsPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Das Formular für einen neuen oder bearbeiteten Eintrag.
  const [userId, setUserId] = useState("");
  const [picked, setPicked] = useState<EmojiInfo[]>([]);
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState("");
  // Ob der Eintrag, der gerade bearbeitet wird, pausiert ist.
  //
  // Ohne diese Merkung schrieb `save` fest `enabled: true` -- und das
  // Bearbeiten einer pausierten Regel hätte sie stillschweigend wieder
  // eingeschaltet. Beim Ändern der Emojis erwartet das niemand.
  const [editingEnabled, setEditingEnabled] = useState(true);

  const load = useCallback(async () => {
    try {
      setData(await api.pingReactions());
    } catch (err: any) {
      toast.error(err?.message || "Die Liste ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const reset = () => {
    setUserId("");
    setPicked([]);
    setNote("");
    setEditing("");
    setEditingEnabled(true);
  };

  const addEmoji = (raw: string) => {
    // Doppelte bringen nichts: Discord nimmt dieselbe Reaktion nur
    // einmal an.
    if (picked.some((entry) => entry.raw === raw)) {
      toast.info("Das Emoji ist schon dabei.");
      return;
    }
    const max = data?.limits?.max_reactions ?? 20;
    if (picked.length >= max) {
      toast.error(`Discord erlaubt höchstens ${max} Reaktionen.`);
      return;
    }

    // Aus `<a:name:id>` die Anzeige bauen — dieselbe Rechnung wie im
    // Bot, damit die Vorschau stimmt, bevor gespeichert wurde.
    const match = /^<(a?):([A-Za-z0-9_]+):(\d+)>$/.exec(raw);
    if (!match) {
      toast.error("Nur eigene Emojis des Bots.");
      return;
    }
    const animated = Boolean(match[1]);
    setPicked([
      ...picked,
      {
        raw,
        name: match[2],
        id: match[3],
        animated,
        url: `https://cdn.discordapp.com/emojis/${match[3]}.${
          animated ? "gif" : "png"
        }?size=48`,
      },
    ]);
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.pingReactionSave({
        user_id: userId.trim(),
        emojis: picked.map((entry) => entry.raw),
        note,
        enabled: editing ? editingEnabled : true,
      });
      toast.success("Gespeichert.");
      reset();
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await api.pingReactionDelete(id);
      toast.success("Gelöscht.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  /**
   * Eine mitgelieferte Regel auf den Code-Stand zurücksetzen.
   *
   * Technisch dasselbe wie Löschen — es verschwindet nur die
   * Überschreibung, nicht die Regel. Deshalb ein eigener Name und eine
   * eigene Rückmeldung: „Gelöscht" wäre hier schlicht falsch.
   */
  const reset_ = async (rule: Rule) => {
    setBusy(true);
    try {
      const answer = await api.pingReactionDelete(rule.user_id);
      toast.success(answer?.result || "Zurückgesetzt.");
      if (editing === rule.user_id) reset();
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Ging nicht.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (rule: Rule) => {
    setBusy(true);
    try {
      const answer = await api.pingReactionToggle(rule.user_id, !rule.enabled);
      toast.success(answer?.result || "Geändert.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Ging nicht.");
    } finally {
      setBusy(false);
    }
  };

  const edit = (rule: Rule) => {
    setEditing(rule.user_id);
    setEditingEnabled(rule.enabled);
    setUserId(rule.user_id);
    // Eine pausierte Regel hat eine leere Anzeige, aber gespeicherte
    // Emojis -- beim Bearbeiten müssen die mitgelieferten her, sonst
    // steht das Formular leer da.
    setPicked(rule.emojis.length ? rule.emojis : rule.default_emojis);
    setNote(rule.note);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) return null;

  const builtin: Rule[] = data.builtin ?? [];
  const rules: Rule[] = data.rules ?? [];
  const maxReactions = data.limits?.max_reactions ?? 20;

  return (
    <section className="space-y-6">
      {/* Anlegen / Bearbeiten */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-1">
          <Plus className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            {editing ? "Eintrag bearbeiten" : "Neuer Eintrag"}
          </h3>
          {editing && (
            <button
              onClick={reset}
              className="ml-auto text-[11px] font-bold text-slate-500 hover:text-slate-300"
            >
              Abbrechen
            </button>
          )}
        </div>
        <p className="text-[12px] text-slate-500 mb-4 leading-relaxed">
          Wird diese Person irgendwo erwähnt, setzt der Bot die gewählten
          Reaktionen unter die Nachricht.
        </p>

        <label className="text-[11px] font-black uppercase tracking-wider text-slate-500">
          Discord-ID
        </label>
        <input
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          disabled={Boolean(editing)}
          placeholder="z. B. 1303627964734246944"
          className="w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-primary/50 transition-colors mt-2 disabled:opacity-50 font-mono"
        />

        <div className="flex items-center gap-3 mt-5 mb-2">
          <label className="text-[11px] font-black uppercase tracking-wider text-slate-500">
            Reaktionen
          </label>
          <span className="text-[11px] text-slate-600 tabular-nums">
            {picked.length} / {maxReactions}
          </span>
          <div className="ml-auto">
            <EmojiPicker onPick={addEmoji} label="Emoji wählen" />
          </div>
        </div>

        <div
          className={cn(
  "flex flex-wrap gap-2 min-h-[3rem] rounded-xl border p-2.5",
            picked.length
              ? "border-slate-800 bg-[#0e0e12]"
              : "border-dashed border-slate-800 bg-transparent"
          )}
        >
          {picked.length === 0 ? (
            <span className="text-[12px] text-slate-600 self-center px-1">
              Noch nichts gewählt — nur eigene Emojis des Bots.
            </span>
          ) : (
            picked.map((info) => (
              <Emoji
                key={info.raw}
                info={info}
                onRemove={() =>
                  setPicked(picked.filter((entry) => entry.raw !== info.raw))
                }
              />
            ))
          )}
        </div>

        <label className="text-[11px] font-black uppercase tracking-wider text-slate-500 block mt-5">
          Notiz (optional)
        </label>
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Wofür ist das? Nur für euch sichtbar."
          className="w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-primary/50 transition-colors mt-2"
        />

        <button
          onClick={save}
          disabled={busy || !userId.trim() || picked.length === 0}
          className="flex items-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-40 text-white text-sm font-bold px-5 py-2.5 rounded-xl transition-all mt-5"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {editing ? "Änderung speichern" : "Hinzufügen"}
        </button>
      </div>

      {/* Mitgeliefert — jetzt änderbar */}
      {builtin.length > 0 && (
        <div className={CARD}>
          <div className="flex items-center gap-3 mb-1">
            <ShieldCheck className="h-5 w-5 text-primary shrink-0" />
            <h3 className="font-black text-white text-sm uppercase tracking-wider">
              Mitgeliefert
            </h3>
          </div>
          <p className="text-[12px] text-slate-500 mb-4 leading-relaxed">
            Diese Regeln stehen im Code und gelten ohne weiteres Zutun. Eine
            Änderung hier legt sich darüber — „Zurücksetzen“ holt jederzeit
            den Originalstand zurück.
          </p>

          <div className="space-y-2">
            {builtin.map((rule) => (
              <div
                key={rule.user_id}
                className={cn(
  "flex flex-wrap items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
                  rule.enabled
                    ? "bg-[#0e0e12] border-slate-800"
                    : "bg-[#0e0e12]/50 border-slate-800/50 opacity-55"
                )}
              >
                <span className="h-8 w-8 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center text-[10px] font-black text-primary shrink-0 overflow-hidden">
                  {rule.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={rule.avatar} alt="" className="h-full w-full" />
                  ) : (
                    rule.user_id.slice(-2)
                  )}
                </span>

                <div className="min-w-0">
                  <p className="text-sm text-slate-200 truncate flex items-center gap-2">
                    {rule.name || "Unbekannt"}
                    {rule.customised && (
                      <span className="text-[9px] font-black uppercase tracking-wider text-cyan-300/90 bg-cyan-500/10 border border-cyan-500/25 rounded-full px-2 py-0.5">
                        geändert
                      </span>
                    )}
                    {!rule.enabled && (
                      <span className="text-[9px] font-black uppercase tracking-wider text-amber-400/80">
                        pausiert
                      </span>
                    )}
                  </p>
                  <p className="text-[10px] text-slate-600 font-mono">
                    {rule.user_id}
                    {rule.note ? ` · ${rule.note}` : ""}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5 sm:ml-auto">
                  {rule.emojis.length === 0 ? (
                    <span className="text-[11px] text-slate-600 self-center">
                      keine
                    </span>
                  ) : (
                    rule.emojis.map((info) => (
                      <Emoji key={info.raw} info={info} />
                    ))
                  )}
                </div>

                <div className="flex gap-1.5 ml-auto sm:ml-0">
                  <button
                    onClick={() => toggle(rule)}
                    disabled={busy}
                    title={rule.enabled ? "Pausieren" : "Wieder aktivieren"}
                    className="p-2 rounded-lg bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.07] transition-all disabled:opacity-40"
                  >
                    {rule.enabled ? (
                      <Pause className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <Play className="h-3.5 w-3.5 text-emerald-400" />
                    )}
                  </button>
                  <button
                    onClick={() => edit(rule)}
                    disabled={busy}
                    title="Bearbeiten"
                    className="p-2 rounded-lg bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.07] transition-all disabled:opacity-40"
                  >
                    <Save className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                  {/* Zurücksetzen statt Löschen: die Regel verschwindet
                      nicht, sie fällt auf den Code-Stand zurück. Ein
                      Mülleimer-Symbol würde etwas anderes versprechen. */}
                  <button
                    onClick={() => reset_(rule)}
                    disabled={busy || !rule.customised}
                    title={
                      rule.customised
                        ? `Zurücksetzen auf ${rule.default_emojis.length} Emojis`
                        : "Steht schon auf dem Originalstand"
                    }
                    className="p-2 rounded-lg bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.07] transition-all disabled:opacity-25"
                  >
                    <RotateCcw className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Die eigenen Einträge */}
      <div className={CARD}>
        <div className="flex items-center gap-3 mb-4">
          <AtSign className="h-5 w-5 text-primary shrink-0" />
          <h3 className="font-black text-white text-sm uppercase tracking-wider">
            Eigene Einträge
          </h3>
          <span className="ml-auto text-sm font-bold text-primary tabular-nums">
            {rules.length}
          </span>
        </div>

        {rules.length === 0 ? (
          <p className="text-sm text-slate-500">
            Noch keine — oben eine ID eintragen und Emojis wählen.
          </p>
        ) : (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div
                key={rule.user_id}
                className={cn(
  "flex flex-wrap items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
                  rule.enabled
                    ? "bg-[#0e0e12] border-slate-800"
                    : "bg-[#0e0e12]/50 border-slate-800/50 opacity-55"
                )}
              >
                <span className="h-8 w-8 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center text-[10px] font-black text-primary shrink-0 overflow-hidden">
                  {rule.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={rule.avatar} alt="" className="h-full w-full" />
                  ) : (
                    rule.user_id.slice(-2)
                  )}
                </span>

                <div className="min-w-0">
                  <p className="text-sm text-slate-200 truncate">
                    {rule.name || "Unbekannt"}
                    {!rule.enabled && (
                      <span className="ml-2 text-[10px] font-black uppercase tracking-wider text-amber-400/70">
                        pausiert
                      </span>
                    )}
                  </p>
                  <p className="text-[10px] text-slate-600 font-mono">
                    {rule.user_id}
                    {rule.note ? ` · ${rule.note}` : ""}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5 sm:ml-auto">
                  {rule.emojis.map((info) => (
                    <Emoji key={info.raw} info={info} />
                  ))}
                </div>

                <div className="flex gap-1.5 ml-auto sm:ml-0">
                  <button
                    onClick={() => toggle(rule)}
                    disabled={busy}
                    title={rule.enabled ? "Pausieren" : "Wieder aktivieren"}
                    className="p-2 rounded-lg bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.07] transition-all disabled:opacity-40"
                  >
                    {rule.enabled ? (
                      <Pause className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <Play className="h-3.5 w-3.5 text-emerald-400" />
                    )}
                  </button>
                  <button
                    onClick={() => edit(rule)}
                    disabled={busy}
                    title="Bearbeiten"
                    className="p-2 rounded-lg bg-[#0e0e12] border border-slate-800 hover:bg-white/[0.07] transition-all disabled:opacity-40"
                  >
                    <Save className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                  <button
                    onClick={() => remove(rule.user_id)}
                    disabled={busy}
                    title="Löschen"
                    className="p-2 rounded-lg bg-red-500/[0.07] border border-red-500/20 hover:bg-red-500/15 transition-all disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-400" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="text-[11px] text-slate-600 mt-4 leading-relaxed">
          Gilt auf allen Servern, auf denen der Bot ist. Discord nimmt
          höchstens {maxReactions} verschiedene Reaktionen pro Nachricht an —
          werden mehrere Leute auf einmal erwähnt, kommen die ersten
          {" "}{maxReactions} durch.
        </p>
      </div>
    </section>
  );
}
