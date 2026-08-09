"use client";

/**
 * Teamliste: wer im Team ist, nach Rollen geordnet, im Kanal sichtbar.
 *
 * ── Der Ablauf ──────────────────────────────────────────────────────
 *
 *   1. Rollen hinzufügen — je Rolle eine Gruppe, mit eigenem Emoji
 *      und eigener Überschrift.
 *   2. Reihenfolge festlegen: Inhaber oben, Supporter unten.
 *   3. Aussehen einstellen — Zitat-Strich, Zähler, Status.
 *   4. Kanal wählen und senden.
 *
 * Danach hält sich die Liste selbst aktuell: bekommt jemand eine
 * Rolle, schreibt der Bot die Nachricht ein paar Sekunden später neu.
 *
 * ── Warum die Vorschau vom Bot kommt ────────────────────────────────
 *
 * Sie ließe sich hier im Browser bauen. Dann gäbe es das Format
 * zweimal — einmal in Python, einmal in TypeScript — und spätestens
 * bei der dritten Änderung liefen beide auseinander. Die Vorschau
 * zeigt genau das, was gesendet würde, weil es dieselbe Funktion ist.
 *
 * ── Warum keine Namen, sondern Erwähnungen ──────────────────────────
 *
 * `<@111>` zeigt Discord als Anzeigenamen in der Farbe der höchsten
 * Rolle — und es bleibt richtig, wenn jemand sich umbenennt. Ein
 * abgeschriebener Name wäre nach der nächsten Umbenennung falsch.
 * Gepingt wird dabei niemand; das unterbindet der Bot.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, Check, Eye, GripVertical, Hash,
  Loader2, Plus, RefreshCcw, Send, Trash2, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { EmojiOnly, EmojiText } from "@/components/dashboard/emoji-field";
import { Select } from "@/components/ui/select";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";
const SUB = "rounded-2xl bg-[#0a1628] border border-slate-800 p-4";
const INPUT =
  "w-full bg-[#0a1628] border border-slate-800 rounded-xl px-4 py-3 text-sm " +
  "text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";
const LBL =
  "text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 " +
  "flex items-center gap-1.5";

/**
 * Wie eine Mitgliederzeile aussieht.
 *
 * Die Schlüssel müssen zu `STYLES` im Bot passen — ein unbekannter
 * Wert fällt dort still auf „quote" zurück, und der Nutzer sähe eine
 * andere Liste als eingestellt. Ein Test vergleicht beide Seiten.
 */
const STYLES = [
  { id: "quote", label: "Zitat-Strich", sample: "> @Mia" },
  { id: "quote_dash", label: "Zitat mit Strich", sample: "> — @Mia" },
  { id: "bullet", label: "Aufzählung", sample: "• @Mia" },
  { id: "plain", label: "Schlicht", sample: "@Mia" },
  { id: "code", label: "Pfeil", sample: "`»` @Mia" },
];

export function TeamlistPanel({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [config, setConfig] = useState<any>(null);
  const [groups, setGroups] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [limits, setLimits] = useState<any>({});
  const [canStatus, setCanStatus] = useState(false);
  const [preview, setPreview] = useState<any>(null);

  // Welche Rolle als nächstes hinzugefügt wird.
  const [pick, setPick] = useState("");

  const load = useCallback(async () => {
    try {
      const answer = await api.teamlist(guildId);
      setConfig(answer?.config || null);
      setGroups(answer?.groups || []);
      setRoles(answer?.roles || []);
      setChannels(answer?.channels || []);
      setLimits(answer?.limits || {});
      setCanStatus(Boolean(answer?.can_show_status));
    } catch (error: any) {
      toast.error(error?.message || "Die Teamliste ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Die Vorschau holen.
   *
   * Nach jeder Änderung, aber mit kurzer Pause: wer an der Überschrift
   * tippt, löst sonst bei jedem Buchstaben eine Anfrage aus.
   */
  const pullPreview = useCallback(async () => {
    try {
      setPreview(await api.teamlistPreview(guildId));
    } catch {
      // Die Vorschau ist Beiwerk — ein Fehlschlag darf das Einrichten
      // nicht blockieren.
    }
  }, [guildId]);

  useEffect(() => {
    if (loading) return;
    const handle = setTimeout(pullPreview, 400);
    return () => clearTimeout(handle);
  }, [loading, pullPreview, groups, config]);

  /** Eine Einstellung ändern und sichern. */
  const patch = async (change: Record<string, any>) => {
    const next = { ...config, ...change };
    setConfig(next);
    try {
      await api.teamlistSave(guildId, change);
    } catch (error: any) {
      toast.error(error?.message || "Konnte nicht gespeichert werden.");
      // Zurückdrehen: sonst zeigt das Dashboard einen Zustand, den der
      // Bot nicht kennt.
      setConfig(config);
    }
  };

  /** Die Gruppen sichern. */
  const saveGroups = async (next: any[]) => {
    setGroups(next);
    try {
      const answer = await api.teamlistGroups(guildId, next);
      setGroups(answer?.groups || next);
    } catch (error: any) {
      toast.error(error?.message || "Die Gruppen ließen sich nicht sichern.");
      await load();
    }
  };

  const addRole = async () => {
    if (!pick) return;
    if (groups.length >= (limits.max_groups ?? 15)) {
      toast.error(`Mehr als ${limits.max_groups ?? 15} Gruppen gehen nicht.`);
      return;
    }
    const role = roles.find((r) => r.id === pick);
    await saveGroups([
      ...groups,
      { role_id: pick, emoji: "", label: "", role_name: role?.name || "" },
    ]);
    setPick("");
  };

  const move = async (index: number, by: number) => {
    const next = [...groups];
    const target = index + by;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    await saveGroups(next);
  };

  const publish = async () => {
    setBusy("publish");
    try {
      const answer = await api.teamlistPublish(guildId);
      setConfig(answer?.config || config);
      toast.success("Die Teamliste steht im Kanal.");
    } catch (error: any) {
      toast.error(error?.message || "Das Senden schlug fehl.");
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    setBusy("remove");
    try {
      await api.teamlistRemove(guildId, true);
      toast.success("Entfernt.");
      await load();
      setPreview(null);
    } catch (error: any) {
      toast.error(error?.message || "Das ging nicht.");
    } finally {
      setBusy("");
    }
  };

  /** Rollen, die noch nicht als Gruppe drin sind. */
  const free = useMemo(() => {
    const used = new Set(groups.map((g) => String(g.role_id)));
    return roles.filter((role) => !used.has(String(role.id)));
  }, [roles, groups]);

  if (loading) {
    return (
      <div className={cn(CARD, "flex items-center justify-center py-16")}>
        <Loader2 className="h-6 w-6 text-primary animate-spin opacity-50" />
      </div>
    );
  }

  const posted = Boolean(config?.message_id);

  return (
    <div className="space-y-5">
      {/* ── Zustand ───────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <Users className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-bold text-white">Teamliste</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {posted ? (
                <>
                  Steht in{" "}
                  <span className="text-slate-300">
                    #
                    {channels.find((c) => c.id === config.channel_id)?.name ||
                      "unbekannt"}
                  </span>{" "}
                  und hält sich selbst aktuell.
                </>
              ) : (
                "Noch nicht gesendet. Unten einrichten und dann senden."
              )}
            </p>
          </div>
          <button
            onClick={() => {
              load();
              pullPreview();
            }}
            title="Neu laden"
            className="p-2.5 rounded-xl text-slate-600 hover:text-white hover:bg-white/[0.06] transition-all"
          >
            <RefreshCcw className="h-4 w-4" />
          </button>
        </div>

        {posted && (
          <InlineToggle
            checked={Boolean(config?.enabled)}
            onCheckedChange={(v: boolean) => patch({ enabled: v })}
            label="Automatisch aktualisieren"
            hint="Bei jeder Rollenänderung, zusätzlich alle 15 Minuten."
          />
        )}
      </div>

      {/* ── Gruppen ───────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h4 className="font-bold text-white text-[14px]">Rollen</h4>
          <p className="text-[12px] text-slate-500 mt-0.5">
            Je Rolle eine Gruppe. Die Reihenfolge hier ist die Reihenfolge in
            der Nachricht &mdash; {groups.length} von{" "}
            {limits.max_groups ?? 15} belegt.
          </p>
        </div>

        {groups.length === 0 ? (
          <div className={cn(SUB, "py-8 text-center")}>
            <p className="text-[13px] text-slate-600">
              Noch keine Rolle ausgewählt.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {groups.map((group, index) => {
              const role = roles.find((r) => r.id === String(group.role_id));
              return (
                <div key={`${group.role_id}-${index}`} className={SUB}>
                  <div className="flex items-start gap-3 flex-wrap">
                    {/* Reihenfolge */}
                    <div className="flex flex-col gap-0.5 shrink-0">
                      <button
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                        title="Nach oben"
                        className="p-1 rounded text-slate-600 hover:text-white disabled:opacity-25 transition-colors"
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        disabled={index === groups.length - 1}
                        onClick={() => move(index, 1)}
                        title="Nach unten"
                        className="p-1 rounded text-slate-600 hover:text-white disabled:opacity-25 transition-colors"
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    <GripVertical className="h-4 w-4 text-slate-700 shrink-0 mt-2" />

                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className="h-2.5 w-2.5 rounded-full shrink-0"
                          style={{
                            background: role?.colour || "#99aab5",
                          }}
                        />
                        <span className="text-[13.5px] font-bold text-white">
                          {group.role_name || role?.name || "Gelöschte Rolle"}
                        </span>
                        {role ? (
                          <span className="text-[11px] text-slate-600">
                            {role.members}{" "}
                            {role.members === 1 ? "Person" : "Personen"}
                          </span>
                        ) : (
                          /* Eine Rolle, die es nicht mehr gibt, bleibt
                             als leere Gruppe stehen. Das sieht aus wie
                             ein Fehler — also sagen wir, was los ist. */
                          <span className="text-[11px] text-amber-400/80">
                            Rolle gelöscht
                          </span>
                        )}
                      </div>

                      <div className="flex gap-2 flex-wrap items-start">
                        <div>
                          <p className={LBL}>Emoji</p>
                          <EmojiOnly
                            value={group.emoji || ""}
                            onChange={(next) => {
                              const copy = [...groups];
                              copy[index] = { ...copy[index], emoji: next };
                              setGroups(copy);
                            }}
                            placeholder="👑"
                          />
                        </div>
                        <div className="flex-1 min-w-[180px]">
                          <p className={LBL}>Überschrift</p>
                          <input
                            value={group.label || ""}
                            onChange={(event) => {
                              const copy = [...groups];
                              copy[index] = {
                                ...copy[index],
                                label: event.target.value,
                              };
                              setGroups(copy);
                            }}
                            onBlur={() => saveGroups(groups)}
                            placeholder={
                              group.role_name || role?.name || "Rollenname"
                            }
                            maxLength={100}
                            className={INPUT}
                          />
                          <p className="text-[11px] text-slate-600 mt-1.5">
                            Leer lassen: dann steht der Rollenname da.
                          </p>
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() =>
                        saveGroups(groups.filter((_, i) => i !== index))
                      }
                      title="Gruppe entfernen"
                      className="p-2.5 rounded-xl text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all shrink-0"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}

            {/* Ein Klick sichert die getippten Überschriften — ohne
                ihn bliebe eine Änderung liegen, bis man das Feld
                verlässt. */}
            <button
              onClick={() => saveGroups(groups)}
              className="text-[11px] font-black uppercase tracking-widest text-primary/70 hover:text-primary transition-colors"
            >
              Änderungen sichern
            </button>
          </div>
        )}

        {/* Rolle hinzufügen */}
        <div className="flex gap-2 flex-wrap items-end border-t border-slate-800 pt-4">
          <div className="flex-1 min-w-[200px]">
            <p className={LBL}>Rolle hinzufügen</p>
            <Select
              value={pick}
              onValueChange={setPick}
              options={free.map((role) => ({
                value: role.id,
                label: `${role.name} (${role.members})`,
              }))}
              placeholder={
                free.length ? "Rolle wählen …" : "Alle Rollen sind schon drin"
              }
              disabled={free.length === 0}
            />
          </div>
          <button
            disabled={!pick || groups.length >= (limits.max_groups ?? 15)}
            onClick={addRole}
            className="flex items-center gap-2 px-4 py-3 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
          >
            <Plus className="h-3.5 w-3.5" />
            Hinzufügen
          </button>
        </div>
      </div>

      {/* ── Aussehen ──────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h4 className="font-bold text-white text-[14px]">Aussehen</h4>
          <p className="text-[12px] text-slate-500 mt-0.5">
            Überschrift, Zeilenform und was sonst noch dabeisteht.
          </p>
        </div>

        <div>
          <p className={LBL}>Überschrift</p>
          <EmojiText
            value={config?.title || ""}
            onChange={(next) => patch({ title: next })}
            placeholder="Unser Team"
            limit={limits.max_title ?? 200}
          />
        </div>

        <div>
          <p className={LBL}>Text darüber</p>
          <EmojiText
            value={config?.intro || ""}
            onChange={(next) => patch({ intro: next })}
            placeholder="Optional — z. B. »Bei Fragen gern melden.«"
            limit={limits.max_text ?? 1000}
            rows={2}
          />
        </div>

        <div>
          <p className={LBL}>Text darunter</p>
          <EmojiText
            value={config?.footer || ""}
            onChange={(next) => patch({ footer: next })}
            placeholder="Optional — z. B. »Stand: automatisch«"
            limit={limits.max_text ?? 1000}
            rows={2}
          />
        </div>

        <div>
          <p className={LBL}>Zeilenform</p>
          <div className="grid sm:grid-cols-2 gap-2">
            {STYLES.map((style) => {
              const active = (config?.style || "quote") === style.id;
              return (
                <button
                  key={style.id}
                  onClick={() => patch({ style: style.id })}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "rounded-xl border px-4 py-3 text-left transition-all",
                    active
                      ? "bg-primary/10 border-primary/40"
                      : "bg-[#0a1628] border-slate-800 hover:border-slate-700"
                  )}
                >
                  <p className="text-[13px] font-bold text-white">
                    {style.label}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5 font-mono">
                    {style.sample}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        <InlineToggle
          checked={Boolean(config?.show_counts)}
          onCheckedChange={(v: boolean) => patch({ show_counts: v })}
          label="Anzahl je Rolle zeigen"
          hint="Eine kleine Zahl hinter der Überschrift."
        />
        <InlineToggle
          checked={Boolean(config?.show_empty)}
          onCheckedChange={(v: boolean) => patch({ show_empty: v })}
          label="Leere Gruppen zeigen"
          hint="Sonst fällt eine Rolle, die gerade niemand hat, heraus."
        />
        <InlineToggle
          checked={Boolean(config?.show_status)}
          onCheckedChange={(v: boolean) => patch({ show_status: v })}
          disabled={!canStatus}
          label="Online-Status zeigen"
          hint={
            canStatus
              ? "Ein farbiger Punkt hinter jedem Namen."
              : "Dem Bot fehlt die Berechtigung dafür — es stünde bei jedem »offline«."
          }
        />
        <InlineToggle
          checked={Boolean(config?.use_embed)}
          onCheckedChange={(v: boolean) => patch({ use_embed: v })}
          label="Als Embed senden"
          hint="Farbiger Rahmen statt schlichter Nachricht."
        />

        {config?.use_embed && (
          <div>
            <p className={LBL}>Farbe</p>
            <div className="flex gap-2 items-center flex-wrap">
              <input
                type="color"
                value={config?.colour || "#5865f2"}
                onChange={(event) => patch({ colour: event.target.value })}
                className="h-11 w-16 rounded-xl bg-[#0a1628] border border-slate-800 cursor-pointer"
              />
              <span className="text-[12px] text-slate-500 font-mono">
                {config?.colour || "#5865f2"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── Vorschau ──────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-3")}>
        <div className="flex items-center gap-2 flex-wrap">
          <p className={cn(LBL, "mb-0")}>
            <Eye className="h-3 w-3" />
            Vorschau
          </p>
          {preview && (
            <span
              className={cn(
                "ml-auto text-[11px] tabular-nums",
                preview.too_long ? "text-red-400" : "text-slate-600"
              )}
            >
              {preview.length} / {preview.max_length} Zeichen
            </span>
          )}
        </div>

        {/* So sieht es in Discord aus — dunkler Kasten, gleiche
            Schrift, Zitat-Striche als senkrechte Linien. */}
        <div className="rounded-2xl bg-[#313338] border border-black/20 p-4">
          {preview ? (
            <DiscordPreview text={preview.text} />
          ) : (
            <p className="text-[13px] text-slate-500">wird geladen …</p>
          )}
        </div>

        {preview?.too_long && (
          <div className="rounded-xl bg-red-500/[0.07] border border-red-500/25 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-200/85 leading-relaxed">
              Die Nachricht ist zu lang für Discord (Grenze:{" "}
              {preview.max_length} Zeichen) und würde gekürzt. Weniger Gruppen
              oder kürzere Texte helfen.
            </p>
          </div>
        )}

        {(preview?.duplicates || []).length > 0 && (
          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/25 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-amber-200/80 leading-relaxed">
              {preview.duplicates.length}{" "}
              {preview.duplicates.length === 1 ? "Person steht" : "Personen stehen"}{" "}
              in mehreren Gruppen und {preview.duplicates.length === 1 ? "taucht" : "tauchen"}{" "}
              mehrfach auf. Das kann so gewollt sein.
            </p>
          </div>
        )}
      </div>

      {/* ── Senden ────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h4 className="font-bold text-white text-[14px]">Kanal</h4>
          <p className="text-[12px] text-slate-500 mt-0.5">
            Nur Kanäle, in die der Bot schreiben darf.
          </p>
        </div>

        <Select
          value={config?.channel_id || ""}
          onValueChange={(next) => patch({ channel_id: next })}
          options={channels.map((channel) => ({
            value: channel.id,
            label: channel.category
              ? `${channel.category} / #${channel.name}`
              : `#${channel.name}`,
          }))}
          placeholder="Kanal wählen …"
        />

        <div className="flex items-center gap-2 flex-wrap">
          <button
            disabled={
              !config?.channel_id || groups.length === 0 || busy === "publish"
            }
            onClick={publish}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
          >
            {busy === "publish" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : posted ? (
              <RefreshCcw className="h-3.5 w-3.5" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            {posted ? "Jetzt aktualisieren" : "In den Kanal senden"}
          </button>

          {posted && (
            <button
              disabled={busy === "remove"}
              onClick={remove}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs font-black uppercase tracking-widest hover:bg-red-500/20 disabled:opacity-40 transition-all"
            >
              {busy === "remove" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Entfernen
            </button>
          )}
        </div>

        {/* Ein ausgegrauter Knopf ohne Begründung sieht nach einem
            Fehler aus. */}
        {(!config?.channel_id || groups.length === 0) && (
          <p className="text-[11px] text-slate-600">
            {groups.length === 0
              ? "Erst mindestens eine Rolle hinzufügen."
              : "Erst einen Kanal wählen."}
          </p>
        )}

        {posted && (
          <div className={cn(SUB, "flex gap-2.5")}>
            <Check className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-slate-400 leading-relaxed">
              Die Nachricht wird <b>bearbeitet</b>, nicht neu gesendet &mdash;
              sie bleibt also da, wo sie ist, und kann angeheftet werden.
              Gepingt wird dabei niemand.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Der Vorschautext, wie Discord ihn zeigen würde.
 *
 * Ein einfaches `<pre>` wäre ehrlicher, aber unbrauchbar: dann sähe
 * man `## Unser Team` statt einer Überschrift und `> <@111>` statt
 * eines eingerückten Namens — also gerade das nicht, worauf es
 * ankommt.
 *
 * Nachgebildet werden nur die vier Dinge, die die Teamliste benutzt:
 * Überschrift, Fettdruck, Zitat-Strich und Erwähnung. Alles andere
 * bleibt Text — eine halbe Markdown-Umsetzung, die mehr verspricht,
 * als sie hält, wäre schlechter als gar keine.
 */
function DiscordPreview({ text }: { text: string }) {
  const lines = (text || "").split("\n");

  return (
    <div className="space-y-0.5 text-[14px] leading-[1.4] text-[#dbdee1]">
      {lines.map((line, index) => {
        if (!line.trim()) {
          return <div key={index} className="h-2" />;
        }

        if (line.startsWith("## ")) {
          return (
            <p key={index} className="text-[18px] font-bold text-white mt-1">
              {renderInline(line.slice(3))}
            </p>
          );
        }

        if (line.startsWith("> ")) {
          return (
            <div key={index} className="flex gap-2.5 pl-0.5">
              <span className="w-[3px] rounded-full bg-[#4e5058] shrink-0" />
              <span>{renderInline(line.slice(2))}</span>
            </div>
          );
        }

        return <p key={index}>{renderInline(line)}</p>;
      })}
    </div>
  );
}

/** Fettdruck, Erwähnungen, Emojis und Codeschnipsel in einer Zeile. */
function renderInline(line: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // Ein Ausdruck für alles, was Discord anders darstellt als Text.
  const pattern =
    /(\*\*[^*]+\*\*)|(<a?:\w+:\d+>)|(<@!?\d+>)|(`[^`]+`)/g;

  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(line)) !== null) {
    if (match.index > last) out.push(line.slice(last, match.index));
    const token = match[0];

    if (token.startsWith("**")) {
      out.push(
        <b key={key++} className="text-white">
          {token.slice(2, -2)}
        </b>
      );
    } else if (token.startsWith("<a:") || token.startsWith("<:")) {
      // Das Bild lässt sich hier nicht laden (die Vorschau läuft ohne
      // Netz), aber der Name sagt, welches Emoji gemeint ist.
      const name = token.split(":")[1] || "emoji";
      out.push(
        <span
          key={key++}
          className="inline-block px-1 rounded bg-white/10 text-[12px] align-middle"
          title={token}
        >
          :{name}:
        </span>
      );
    } else if (token.startsWith("<@")) {
      out.push(
        <span
          key={key++}
          className="rounded px-1 bg-[#3c4270] text-[#c9cdfb] font-medium"
        >
          @Mitglied
        </span>
      );
    } else {
      out.push(
        <code
          key={key++}
          className="rounded bg-[#1e1f22] px-1 py-0.5 text-[12px] font-mono"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    last = match.index + token.length;
  }

  if (last < line.length) out.push(line.slice(last));
  return out;
}
