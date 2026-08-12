"use client";

/**
 * Team-Update einrichten.
 *
 * ── Was das ist ─────────────────────────────────────────────────────
 *
 * Fünf Befehle, die Rollen umstecken und das Ergebnis ankündigen:
 * `/uprank`, `/downrank`, `/teamkick`, `/teamwarn`, `/teamanfang`.
 * Hier steht, was dabei passiert — Kanäle, Vorlagen, wer sie benutzen
 * darf, die Verwarnungs-Automatik.
 *
 * ── Warum die Vorschau vom Bot kommt ────────────────────────────────
 *
 * Sie ließe sich hier im Browser zusammensetzen. Dann gäbe es das
 * Format zweimal — einmal in Python, einmal in TypeScript — und
 * spätestens bei der dritten Änderung liefen beide auseinander. Die
 * Vorschau benutzt dieselbe Funktion wie das Senden.
 *
 * ── Warum sofort gespeichert wird ───────────────────────────────────
 *
 * Jeder Schalter und jedes Feld ist eine eigene Anfrage. Eine
 * Speicherleiste hätte nichts zu speichern — und wäre irreführend,
 * weil die Änderung ja schon beim Bot ist. Nur die Vorlagen haben
 * einen eigenen Speichern-Knopf: bei einem mehrzeiligen Text wäre
 * eine Anfrage pro Tastendruck unsinnig.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowDownCircle, ArrowUpCircle, Check, Clock, Eye,
  Hash, Loader2, MessageSquare, RefreshCcw, Save, ShieldAlert, Trash2,
  UserCog, UserMinus, UserPlus, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle, SwitchToggle } from "@/components/dashboard/form-elements";
import { ChannelPicker, MultiRolePicker, RolePicker } from "@/components/dashboard/pickers";

const CARD =
  "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";
const SUB = "rounded-2xl bg-[#0e0e12] border border-slate-800 p-4";
const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm " +
  "text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";
const LBL =
  "text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 " +
  "flex items-center gap-1.5";

/**
 * Die fünf Aktionen mit Icon und dem Befehl, der sie auslöst.
 *
 * Die Schlüssel müssen zu `ACTIONS` im Bot passen — ein unbekannter
 * Wert landet dort in keiner Vorlage, und die Ankündigung bliebe
 * stumm. Ein Test vergleicht beide Seiten.
 */
const ACTIONS = [
  {
    key: "uprank",
    label: "Beförderung",
    command: "/uprank",
    icon: ArrowUpCircle,
    tone: "text-emerald-400",
    hint: "Neue Rolle drauf, alte runter.",
  },
  {
    key: "downrank",
    label: "Rückstufung",
    command: "/downrank",
    icon: ArrowDownCircle,
    tone: "text-amber-400",
    hint: "Alte Rolle runter, neue drauf.",
  },
  {
    key: "kick",
    label: "Team-Ausschluss",
    command: "/teamkick",
    icon: UserMinus,
    tone: "text-red-400",
    hint: "Alle Teamrollen runter.",
  },
  {
    key: "warn",
    label: "Verwarnung",
    command: "/teamwarn",
    icon: ShieldAlert,
    tone: "text-orange-400",
    hint: "In die Akte, mit optionaler Folge.",
  },
  {
    key: "join",
    label: "Aufnahme",
    command: "/teamanfang",
    icon: UserPlus,
    tone: "text-blue-400",
    hint: "Rolle drauf, Begrüßung.",
  },
] as const;

function Field({
  label, hint, icon: Icon, children,
}: {
  label: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className={LBL}>
        {Icon && <Icon className="h-3 w-3" />}
        {label}
      </div>
      {children}
      {hint && (
        <p className="text-[11px] text-slate-500 italic mt-1.5">{hint}</p>
      )}
    </div>
  );
}

export function TeamUpdatePanel({ guildId }: { guildId: string }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [settings, setSettings] = useState<any>(null);
  const [templates, setTemplates] = useState<any>({});
  const [channels, setChannels] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [limits, setLimits] = useState<any>({});
  const [counts, setCounts] = useState<any>({});
  const [placeholders, setPlaceholders] = useState<string[]>([]);
  const [memberCount, setMemberCount] = useState(0);

  /** Welche Aktion gerade aufgeklappt ist. */
  const [openAction, setOpenAction] = useState<string>("uprank");
  /** Der Entwurf der Vorlage — erst beim Speichern zum Bot. */
  const [draft, setDraft] = useState<any>(null);
  const [preview, setPreview] = useState<any>(null);

  const [history, setHistory] = useState<any[]>([]);
  const [members, setMembers] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showMembers, setShowMembers] = useState(false);

  const load = useCallback(async () => {
    try {
      const answer = await api.getTeamUpdate(guildId);
      setSettings(answer?.settings || null);
      setTemplates(answer?.templates || {});
      setChannels(answer?.channels || []);
      setRoles(answer?.roles || []);
      setLimits(answer?.limits || {});
      setCounts(answer?.counts || {});
      setPlaceholders(answer?.placeholders || []);
      setMemberCount(answer?.member_count || 0);
    } catch (error: any) {
      toast.error(error?.message || "Das Team-Update ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  /** Beim Wechsel der Aktion den Entwurf neu aus der Vorlage füllen. */
  useEffect(() => {
    if (!templates?.[openAction]) return;
    setDraft({ ...templates[openAction] });
  }, [openAction, templates]);

  /** Die Vorschau holen — mit kurzer Pause, sonst eine Anfrage je Taste. */
  const pullPreview = useCallback(async () => {
    try {
      setPreview(await api.teamUpdatePreview(guildId, openAction));
    } catch {
      // Die Vorschau ist Beiwerk. Ein Fehlschlag darf das Einrichten
      // nicht blockieren.
    }
  }, [guildId, openAction]);

  useEffect(() => {
    if (loading) return;
    const handle = setTimeout(pullPreview, 400);
    return () => clearTimeout(handle);
  }, [loading, pullPreview, templates]);

  /** Eine Einstellung ändern und sofort sichern. */
  const patch = async (change: Record<string, any>) => {
    const before = settings;
    setSettings({ ...settings, ...change });
    try {
      const answer = await api.saveTeamUpdate(guildId, change);
      setSettings(answer?.settings || { ...before, ...change });
    } catch (error: any) {
      toast.error(error?.message || "Konnte nicht gespeichert werden.");
      // Zurückdrehen: sonst zeigt das Dashboard einen Zustand, den der
      // Bot nicht kennt.
      setSettings(before);
    }
  };

  const saveTemplate = async () => {
    if (!draft) return;
    setBusy("template");
    try {
      const answer = await api.saveTeamUpdateTemplate(guildId, openAction, {
        title: draft.title,
        body: draft.body,
        dm_body: draft.dm_body,
        enabled: draft.enabled,
      });
      setTemplates(answer?.templates || templates);
      toast.success("Vorlage gespeichert.");
    } catch (error: any) {
      toast.error(error?.message || "Die Vorlage ließ sich nicht sichern.");
    } finally {
      setBusy("");
    }
  };

  const loadHistory = async () => {
    setBusy("history");
    try {
      const answer = await api.teamUpdateHistory(guildId);
      setHistory(answer?.events || []);
      setShowHistory(true);
    } catch (error: any) {
      toast.error(error?.message || "Der Verlauf ließ sich nicht laden.");
    } finally {
      setBusy("");
    }
  };

  const loadMembers = async () => {
    setBusy("members");
    try {
      const answer = await api.teamUpdateMembers(guildId);
      setMembers(answer?.members || []);
      setShowMembers(true);
    } catch (error: any) {
      toast.error(error?.message || "Das Team ließ sich nicht laden.");
    } finally {
      setBusy("");
    }
  };

  const clearWarns = async (userId: string) => {
    try {
      await api.clearAllTeamWarns(guildId, userId);
      toast.success("Verwarnungen aufgehoben.");
      await loadMembers();
    } catch (error: any) {
      toast.error(error?.message || "Das ging nicht.");
    }
  };

  /** Ob eine Aktion überhaupt irgendwo landet. */
  const targetOf = (key: string) => {
    const own = settings?.[`${key}_channel_id`];
    return own || settings?.channel_id || "";
  };

  const channelName = (id: string) =>
    channels.find((c) => String(c.id) === String(id))?.name || "unbekannt";

  /** Rollen, die der Bot gar nicht vergeben kann. */
  const blocked = useMemo(
    () => roles.filter((r) => !r.assignable).map((r) => r.name),
    [roles],
  );

  if (loading) {
    return (
      <div className={cn(CARD, "flex items-center justify-center py-16")}>
        <Loader2 className="h-6 w-6 text-primary animate-spin opacity-50" />
      </div>
    );
  }

  const on = Boolean(settings?.enabled);
  const total = ACTIONS.reduce((sum, a) => sum + (counts?.[a.key] || 0), 0);

  return (
    <div className="space-y-5">
      {/* ── Ein/Aus ───────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <UserCog className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-bold text-white">Team-Update</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {on ? (
                <>
                  Läuft. Bisher{" "}
                  <span className="text-slate-300">{total} Aktionen</span>,{" "}
                  <span className="text-slate-300">{memberCount}</span> im Team.
                </>
              ) : (
                "Aus. Die fünf Befehle antworten, dass das Modul nicht eingeschaltet ist."
              )}
            </p>
          </div>
          <SwitchToggle
            checked={on}
            onCheckedChange={(v) => patch({ enabled: v })}
            label="Team-Update ein- oder ausschalten"
          />
        </div>

        {!on && (
          <div className={cn(SUB, "flex items-start gap-2.5")}>
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-slate-400">
              Solange das aus ist, antworten <code>/uprank</code>,{" "}
              <code>/downrank</code>, <code>/teamkick</code>,{" "}
              <code>/teamwarn</code> und <code>/teamanfang</code> mit einem
              Hinweis, statt etwas zu tun. Genau das ist der Zustand, den
              man sieht, wenn die Befehle „nicht aktiv“ sind.
            </p>
          </div>
        )}

        {/* Die fünf Befehle mit ihren Zahlen. */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {ACTIONS.map((action) => {
            const Icon = action.icon;
            const ziel = targetOf(action.key);
            return (
              <button
                key={action.key}
                type="button"
                onClick={() => setOpenAction(action.key)}
                className={cn(
                  "rounded-2xl border p-3 text-left transition-colors",
                  openAction === action.key
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0e0e12] border-slate-800 hover:border-slate-700",
                )}
              >
                <Icon className={cn("h-4 w-4 mb-1.5", action.tone)} />
                <div className="text-[11px] font-bold text-white truncate">
                  {action.label}
                </div>
                <div className="text-[10px] text-slate-500 font-mono truncate">
                  {action.command}
                </div>
                <div className="text-[10px] text-slate-600 mt-1">
                  {counts?.[action.key] || 0}×
                  {!ziel && (
                    <span className="text-amber-500"> · kein Kanal</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Kanäle ────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h3 className="font-bold text-white flex items-center gap-2">
            <Hash className="h-4 w-4 text-primary" />
            Wohin die Ankündigungen gehen
          </h3>
          <p className="text-[12px] text-slate-500 mt-0.5">
            Ein Kanal für alles — und wenn eine Aktion woanders hin soll,
            bekommt sie ihren eigenen. Ohne Kanal werden die Rollen
            trotzdem gesetzt, nur eben still.
          </p>
        </div>

        <Field
          label="Hauptkanal"
          hint="Hierhin geht alles, was keinen eigenen Kanal hat."
        >
          <ChannelPicker
            guildId={guildId}
            value={settings?.channel_id || ""}
            onChange={(id) => patch({ channel_id: id })}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <div className="grid sm:grid-cols-2 gap-3">
          {ACTIONS.map((action) => (
            <Field
              key={action.key}
              label={`${action.label} — eigener Kanal`}
              hint={
                settings?.[`${action.key}_channel_id`]
                  ? undefined
                  : settings?.channel_id
                    ? `Leer: geht in #${channelName(settings.channel_id)}.`
                    : "Leer und kein Hauptkanal: keine Ankündigung."
              }
            >
              <ChannelPicker
                guildId={guildId}
                value={settings?.[`${action.key}_channel_id`] || ""}
                onChange={(id) => patch({ [`${action.key}_channel_id`]: id })}
                placeholder="Wie Hauptkanal"
                channelTypes={["0", "5"]}
              />
            </Field>
          ))}
        </div>
      </div>

      {/* ── Wer und wo ────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h3 className="font-bold text-white flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" />
            Wer die Befehle benutzen darf — und wo
          </h3>
        </div>

        <Field
          label="Rollen mit Zugriff"
          hint="Wer den Server verwalten darf, kann die Befehle immer benutzen. Ohne Rolle hier bleibt es bei dieser Regel."
        >
          <MultiRolePicker
            guildId={guildId}
            value={settings?.staff_roles || []}
            onChange={(ids) =>
              patch({ staff_roles: ids.slice(0, limits.staff_roles ?? 15) })
            }
            placeholder="Rollen wählen"
          />
        </Field>

        <Field
          label="Rollen, die zum Team gehören"
          hint="Diese nimmt /teamkick ab. Bleibt das leer, gelten die Rollen mit Zugriff."
        >
          <MultiRolePicker
            guildId={guildId}
            value={settings?.team_roles || []}
            onChange={(ids) =>
              patch({ team_roles: ids.slice(0, limits.staff_roles ?? 15) })
            }
            placeholder="Rollen wählen"
          />
        </Field>

        <div className={SUB}>
          <InlineToggle
            checked={Boolean(settings?.free_channel)}
            onCheckedChange={(v) => patch({ free_channel: v })}
            label="In jedem Kanal benutzbar"
            hint="Aus: nur im Befehlskanal unten. Ist dort keiner gewählt, bleibt es überall erlaubt — sonst wäre der Befehl nirgends benutzbar."
          />
          {!settings?.free_channel && (
            <div className="mt-3">
              <Field label="Befehlskanal">
                <ChannelPicker
                  guildId={guildId}
                  value={settings?.command_channel_id || ""}
                  onChange={(id) => patch({ command_channel_id: id })}
                  placeholder="Kanal wählen"
                  channelTypes={["0", "5"]}
                />
              </Field>
            </div>
          )}
        </div>

        <div className={cn(SUB, "space-y-3")}>
          <InlineToggle
            checked={Boolean(settings?.require_reason)}
            onCheckedChange={(v) => patch({ require_reason: v })}
            label="Grund ist Pflicht"
            hint="Ohne Grund lehnt der Befehl ab, statt eine Ankündigung mit einem Strich zu senden."
          />
          <InlineToggle
            checked={Boolean(settings?.dm_user)}
            onCheckedChange={(v) => patch({ dm_user: v })}
            label="Die betroffene Person bekommt eine DM"
            hint="Geschlossene Direktnachrichten sind kein Fehler — die Aktion läuft trotzdem durch."
          />
          <InlineToggle
            checked={Boolean(settings?.ping_user)}
            onCheckedChange={(v) => patch({ ping_user: v })}
            label="Die Person in der Ankündigung anpingen"
            hint="Aus: sie wird erwähnt, aber nicht benachrichtigt. Rollen und @everyone werden nie gepingt."
          />
        </div>
      </div>

      {/* ── Verwarnungs-Automatik ─────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h3 className="font-bold text-white flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-orange-400" />
            Was nach zu vielen Verwarnungen passiert
          </h3>
          <p className="text-[12px] text-slate-500 mt-0.5">
            Standard ist: nichts. <code>/teamwarn</code> schreibt in die
            Akte und schickt eine DM, mehr nicht.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <Field
            label="Ab wie vielen Verwarnungen"
            hint="0 heißt: die Automatik ist aus."
          >
            <input
              type="number"
              min={0}
              max={50}
              value={settings?.warn_threshold ?? 0}
              onChange={(e) =>
                patch({ warn_threshold: Number(e.target.value) || 0 })
              }
              className={INPUT}
            />
          </Field>

          <Field label="Und dann">
            <select
              value={settings?.warn_action || "none"}
              onChange={(e) => patch({ warn_action: e.target.value })}
              className={INPUT}
            >
              <option value="none">Nichts — nur speichern</option>
              <option value="downrank">Zurückstufen</option>
              <option value="kick">Aus dem Team nehmen</option>
            </select>
          </Field>
        </div>

        {settings?.warn_action === "downrank" && (
          <Field
            label="Auf welche Rolle zurückstufen"
            hint="Ohne Rolle wird nur die bisherige entfernt."
          >
            <RolePicker
              guildId={guildId}
              value={settings?.warn_downrank_role_id || ""}
              onChange={(id) => patch({ warn_downrank_role_id: id })}
              placeholder="Rolle wählen (optional)"
            />
          </Field>
        )}

        <Field
          label="Verwarnungen verfallen nach (Tagen)"
          hint="0 heißt: sie gelten für immer. Verfallene bleiben in der Akte, zählen aber nicht mehr mit."
        >
          <input
            type="number"
            min={0}
            max={3650}
            value={settings?.warn_expire_days ?? 0}
            onChange={(e) =>
              patch({ warn_expire_days: Number(e.target.value) || 0 })
            }
            className={INPUT}
          />
        </Field>

        {(settings?.warn_threshold ?? 0) > 0 &&
          settings?.warn_action !== "none" && (
            <div className={cn(SUB, "flex items-start gap-2.5")}>
              <Check className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-slate-400">
                Ab der <strong>{settings.warn_threshold}.</strong> gültigen
                Verwarnung wird automatisch{" "}
                {settings.warn_action === "kick"
                  ? "aus dem Team genommen"
                  : "zurückgestuft"}
                . Beides steht danach getrennt in der Akte.
              </p>
            </div>
          )}
      </div>

      {/* ── Bewerbungen ───────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h3 className="font-bold text-white flex items-center gap-2">
            <UserPlus className="h-4 w-4 text-blue-400" />
            Angenommene Bewerbung = neu im Team
          </h3>
        </div>

        <div className={SUB}>
          <InlineToggle
            checked={Boolean(settings?.app_enabled)}
            onCheckedChange={(v) => patch({ app_enabled: v })}
            label="Bei einer angenommenen Bewerbung ins Team aufnehmen"
            hint="Der Bot trägt die Person in die Akte ein und kündigt sie als Aufnahme an — genau wie bei /teamanfang. Welche Rollen sie bekommt, steht weiterhin im Reiter »Bewerbungen« bei der jeweiligen Kategorie."
          />
        </div>

        {settings?.app_enabled && (
          <div className={cn(SUB, "flex items-start gap-2.5")}>
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-slate-400">
              In der Ankündigung steht die <strong>erste</strong> Rolle, die
              die Kategorie beim Annehmen vergibt. Hat eine Kategorie keine
              Rolle eingestellt, wird die Aufnahme trotzdem verbucht — dann
              eben ohne Rollennamen.
            </p>
          </div>
        )}
      </div>

      {/* ── Vorlagen ──────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="min-w-0 flex-1">
            <h3 className="font-bold text-white flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-primary" />
              Text der Ankündigung
            </h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              Für{" "}
              <span className="text-slate-300">
                {ACTIONS.find((a) => a.key === openAction)?.label}
              </span>{" "}
              — oben umschalten.
            </p>
          </div>
          {draft && (
            <SwitchToggle
              checked={Boolean(draft.enabled)}
              onCheckedChange={(v) => setDraft({ ...draft, enabled: v })}
              label="Ankündigung für diese Aktion"
            />
          )}
        </div>

        {draft && (
          <>
            <Field label="Überschrift">
              <input
                value={draft.title || ""}
                maxLength={200}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                className={INPUT}
              />
            </Field>

            <Field
              label="Text im Kanal"
              hint="Platzhalter werden ersetzt. Eine geschweifte Klammer im Grund bricht nichts — unbekannte Platzhalter bleiben stehen."
            >
              <textarea
                value={draft.body || ""}
                maxLength={limits.template ?? 1500}
                rows={7}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                className={cn(INPUT, "font-mono text-[12px] leading-relaxed")}
              />
            </Field>

            <Field
              label="Text der DM"
              hint="Leer lassen heißt: keine DM für diese Aktion."
            >
              <textarea
                value={draft.dm_body || ""}
                maxLength={limits.template ?? 1500}
                rows={4}
                onChange={(e) => setDraft({ ...draft, dm_body: e.target.value })}
                className={cn(INPUT, "font-mono text-[12px] leading-relaxed")}
              />
            </Field>

            <div>
              <div className={LBL}>Platzhalter</div>
              <div className="flex flex-wrap gap-1.5">
                {placeholders.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() =>
                      setDraft({ ...draft, body: `${draft.body || ""}${p}` })
                    }
                    className="px-2 py-1 rounded-lg bg-[#0e0e12] border border-slate-800 text-[11px] font-mono text-slate-400 hover:border-primary/40 hover:text-primary transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={saveTemplate}
              disabled={busy === "template"}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white text-sm font-bold hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {busy === "template" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Vorlage speichern
            </button>
          </>
        )}

        {/* Vorschau */}
        {preview && (
          <div className={SUB}>
            <div className={LBL}>
              <Eye className="h-3 w-3" />
              So sähe es aus
            </div>
            <div
              className="rounded-xl bg-[#131318] border-l-4 p-3.5"
              style={{
                borderLeftColor: `#${Number(preview.colour || 0)
                  .toString(16)
                  .padStart(6, "0")}`,
              }}
            >
              <div className="font-bold text-white text-sm mb-1.5">
                {preview.title}
              </div>
              <div className="text-[12px] text-slate-300 whitespace-pre-wrap leading-relaxed">
                {preview.text}
              </div>
            </div>
            <p className="text-[11px] text-slate-500 italic mt-2">
              {preview.enabled
                ? preview.channel_id
                  ? `Geht nach #${channelName(preview.channel_id)}.`
                  : "Kein Kanal eingestellt — wird nicht gesendet."
                : "Diese Ankündigung ist ausgeschaltet."}
            </p>
          </div>
        )}
      </div>

      {/* ── Rollen, die der Bot nicht vergeben kann ───────── */}
      {blocked.length > 0 && (
        <div className={cn(CARD, "flex items-start gap-2.5")}>
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-slate-400">
            Diese Rollen stehen über der Rolle des Bots und lassen sich
            nicht vergeben:{" "}
            <span className="text-slate-300">{blocked.join(", ")}</span>. Wer
            sie im Befehl angibt, bekommt einen Hinweis statt einer halb
            ausgeführten Beförderung.
          </p>
        </div>
      )}

      {/* ── Akte ──────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div>
          <h3 className="font-bold text-white flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" />
            Team und Verlauf
          </h3>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadMembers}
            disabled={busy === "members"}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-sm text-slate-300 hover:border-slate-700 transition-colors disabled:opacity-50"
          >
            {busy === "members" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Users className="h-3.5 w-3.5" />
            )}
            Wer im Team ist
          </button>
          <button
            type="button"
            onClick={loadHistory}
            disabled={busy === "history"}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-sm text-slate-300 hover:border-slate-700 transition-colors disabled:opacity-50"
          >
            {busy === "history" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCcw className="h-3.5 w-3.5" />
            )}
            Verlauf zeigen
          </button>
        </div>

        {showMembers && (
          <div className={cn(SUB, "space-y-2")}>
            {members.length === 0 ? (
              <p className="text-[12px] text-slate-500 italic">
                Noch niemand — die Akte füllt sich mit dem ersten{" "}
                <code>/teamanfang</code> oder <code>/uprank</code>.
              </p>
            ) : (
              members.map((m) => (
                <div
                  key={m.user_id}
                  className="flex items-center gap-3 py-2 border-b border-slate-800/60 last:border-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-white truncate">
                      {m.user_name || `Unbekannt (${m.user_id})`}
                      {!m.in_guild && (
                        <span className="text-[10px] text-amber-500 ml-2">
                          nicht mehr auf dem Server
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {m.role_name || "keine Rolle"}
                      {m.warns > 0 && (
                        <span className="text-orange-400">
                          {" "}
                          · {m.warns} Verwarnung{m.warns === 1 ? "" : "en"}
                        </span>
                      )}
                    </div>
                  </div>
                  {m.warns > 0 && (
                    <button
                      type="button"
                      onClick={() => clearWarns(m.user_id)}
                      title="Alle Verwarnungen aufheben"
                      className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {showHistory && (
          <div className={cn(SUB, "space-y-2")}>
            {history.length === 0 ? (
              <p className="text-[12px] text-slate-500 italic">
                Noch nichts passiert.
              </p>
            ) : (
              history.map((e) => {
                const meta = ACTIONS.find((a) => a.key === e.action);
                const Icon = meta?.icon || UserCog;
                return (
                  <div
                    key={e.id}
                    className="flex items-start gap-2.5 py-2 border-b border-slate-800/60 last:border-0"
                  >
                    <Icon
                      className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", meta?.tone)}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] text-white">
                        <span className="font-bold">{e.label}</span>
                        {" — "}
                        {e.user_name || e.user_id}
                        {e.old_role_name && e.new_role_name && (
                          <span className="text-slate-500">
                            {" "}
                            ({e.old_role_name} → {e.new_role_name})
                          </span>
                        )}
                      </div>
                      {e.reason && (
                        <div className="text-[11px] text-slate-500 truncate">
                          {e.reason}
                        </div>
                      )}
                      <div className="text-[10px] text-slate-600">
                        {new Date(e.created_at * 1000).toLocaleString("de-DE")}
                        {e.source !== "command" && ` · ${e.source}`}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
