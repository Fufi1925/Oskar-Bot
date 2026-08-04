"use client";

/**
 * Logs — neu gebaut, weil neun gleich aussehende Karten die falsche
 * Antwort auf die Frage waren, die Leute hier stellen.
 *
 * Die Frage ist nicht „welche der neun Ereignisarten will ich?", sondern
 * „ich will mitbekommen, was auf meinem Server los ist". Neun Schalter
 * mit je einem Kanalfeld sind darauf eine Zumutung: man klickt sie
 * einzeln durch, vergisst zwei, und hinterher fehlen genau die Einträge,
 * wegen denen man es eingerichtet hat.
 *
 * Also drei Ebenen, von grob nach fein:
 *
 *   1. **Ein Klick.** Drei Voreinstellungen — das Nötigste, das Übliche,
 *      alles. Wer nur „es soll laufen" will, ist hier fertig.
 *   2. **Gruppen.** Die neun Arten liegen in drei Blöcken (Menschen,
 *      Inhalte, Server). Ein Block lässt sich als Ganzes schalten und in
 *      einen Kanal legen.
 *   3. **Einzeln.** Wie vorher, nur eingeklappt.
 *
 * Was sonst noch anders ist:
 *
 *   * Die Lautstärke steht dran. „Reaktionen" erzeugt bei jedem Klick
 *     auf ein Emoji eine Zeile; das gehört *vor* die Entscheidung, nicht
 *     in eine Fußnote danach.
 *   * Probleme stehen an der Karte, die sie betreffen — nicht gesammelt
 *     oben, wo man sie nicht zuordnen kann.
 *   * Ein Kanal, in den der Bot nicht schreiben darf, sieht aus wie ein
 *     Fehler und nicht wie eine gültige Auswahl.
 */

import React, { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  AtSign,
  Bell,
  Check,
  ChevronDown,
  Hash,
  Mic,
  MessageSquare,
  RefreshCw,
  Send,
  Settings,
  ShieldAlert,
  Smile,
  Sparkles,
  Trash2,
  UserPlus,
  Users,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ChannelPicker,
  MultiChannelPicker,
  MultiRolePicker,
} from "@/components/dashboard/pickers";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";
import {
  Loading,
  StickySaveBar,
  usePanel,
  useSaveGuard,
} from "@/components/dashboard/save-bar";

const ICONS: Record<string, any> = {
  message_events: MessageSquare,
  join_leave_events: UserPlus,
  member_moderation: ShieldAlert,
  voice_events: Mic,
  channel_events: Hash,
  role_events: Users,
  emoji_events: Smile,
  reaction_events: Sparkles,
  system_events: Settings,
};

/**
 * Die neun Arten in drei Blöcken.
 *
 * Nach dem sortiert, wonach jemand sucht — „wer war das?" gegen „was
 * steht da nicht mehr?" gegen „wer hat am Server geschraubt?". Die
 * technische Reihenfolge aus dem Cog hilft dabei niemandem.
 */
const GROUPS = [
  {
    key: "people",
    label: "Menschen",
    hint: "Wer kommt, wer geht, wer wurde bestraft.",
    icon: Users,
    keys: ["join_leave_events", "member_moderation", "voice_events"],
  },
  {
    key: "content",
    label: "Inhalte",
    hint: "Was geschrieben, gelöscht und angeklickt wurde.",
    icon: MessageSquare,
    keys: ["message_events", "reaction_events", "emoji_events"],
  },
  {
    key: "server",
    label: "Server",
    hint: "Änderungen an Kanälen, Rollen und Einstellungen.",
    icon: Settings,
    keys: ["channel_events", "role_events", "system_events"],
  },
];

/**
 * Die drei Voreinstellungen.
 *
 * „Reaktionen" ist absichtlich nur bei „Alles" dabei: der Kanal läuft
 * damit schneller voll als alle acht anderen zusammen, und wer das
 * will, soll es ausdrücklich wählen.
 */
const PRESETS = [
  {
    key: "essential",
    label: "Das Nötigste",
    hint: "Moderation, Beitritte, Serveränderungen. Wenig Rauschen.",
    keys: ["member_moderation", "join_leave_events", "system_events"],
  },
  {
    key: "usual",
    label: "Das Übliche",
    hint: "Dazu Nachrichten, Kanäle, Rollen und Sprachkanäle.",
    keys: [
      "member_moderation",
      "join_leave_events",
      "system_events",
      "message_events",
      "channel_events",
      "role_events",
      "voice_events",
    ],
  },
  {
    key: "everything",
    label: "Alles",
    hint: "Auch Reaktionen und Emojis. Wird viel.",
    keys: null, // null = jede Art
  },
];

/* ── Kleinteile ─────────────────────────────────────────────────── */

function Card({ icon: Icon, title, subtitle, children, onReload }: any) {
  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-black text-white">{title}</p>
          {subtitle && (
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              {subtitle}
            </p>
          )}
        </div>
        {onReload && (
          <button
            onClick={onReload}
            title="Neu laden"
            className="shrink-0 h-8 w-8 rounded-lg grid place-items-center text-slate-500 hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

/** Eine einzelne Log-Art. */
function CategoryRow({ cat, draft, onChange, onTest, busy, guildId }: any) {
  const Icon = ICONS[cat.key] || Bell;

  // Der Entwurf gewinnt, damit eine halbfertige Änderung kein Neuladen
  // wegwirft.
  const value = (field: string) =>
    draft?.[field] !== undefined ? draft[field] : cat[field];

  const enabled = !!value("enabled");
  const channel = value("channel") || "";
  const saved = channel === cat.channel;
  const missing = saved && cat.channel_info?.missing;
  const cannotPost = saved && cat.channel_info?.cannot_post;

  return (
    <div
      className={cn(
        "rounded-2xl border transition-colors",
        enabled && channel && !missing && !cannotPost
          ? "bg-[#0d1b31] border-primary/30"
          : enabled && (missing || cannotPost || !channel)
          ? "bg-[#0d1b31] border-red-500/30"
          : "bg-[#0d1b31]/60 border-slate-800"
      )}
    >
      <div className="flex items-start gap-3 p-3.5">
        <div
          className={cn(
            "h-9 w-9 rounded-xl grid place-items-center shrink-0",
            enabled ? "bg-primary/15" : "bg-white/[0.03]"
          )}
        >
          <Icon
            className={cn("h-4 w-4", enabled ? "text-primary" : "text-slate-600")}
          />
        </div>

        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "font-bold text-sm flex items-center gap-2 flex-wrap",
              enabled ? "text-white" : "text-slate-400"
            )}
          >
            {cat.label}
            {cat.noisy && (
              <span
                title="Diese Art erzeugt viele Einträge."
                className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400/80 text-[9px] font-black uppercase tracking-wider"
              >
                viel
              </span>
            )}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
            {cat.description}
          </p>

          {/* Probleme an der Karte, die sie betreffen -- oben gesammelt
              konnte man sie keiner Zeile zuordnen. */}
          {enabled && !channel && (
            <p className="text-[11px] text-red-400/90 mt-1.5 flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Kein Kanal gewählt — hier landet nichts.
            </p>
          )}
          {missing && (
            <p className="text-[11px] text-red-400/90 mt-1.5 flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Diesen Kanal gibt es nicht mehr.
            </p>
          )}
          {cannotPost && (
            <p className="text-[11px] text-red-400/90 mt-1.5 flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Der Bot darf dort nicht schreiben.
            </p>
          )}
        </div>

        <InlineToggle
          checked={enabled}
          onCheckedChange={(v: boolean) => onChange({ enabled: v })}
          label=""
        />
      </div>

      {enabled && (
        <div className="px-3.5 pb-3.5 space-y-2.5 border-t border-slate-800/70 pt-3">
          <ChannelPicker
            guildId={guildId}
            value={channel}
            onChange={(id: string | null) => onChange({ channel: id })}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
          {channel && saved && (
            <button
              onClick={onTest}
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
            >
              <Send className="h-3.5 w-3.5" />
              Testeintrag posten
            </button>
          )}
          {channel && !saved && (
            <p className="text-[11px] text-slate-600 text-center">
              Erst speichern, dann lässt sich der Kanal testen.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Das Panel ──────────────────────────────────────────────────── */

export function LoggingPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getLogging(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "logging-save-bar");

  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [exceptions, setExceptions] = useState(false);
  const [allChannel, setAllChannel] = useState("");
  const [userId, setUserId] = useState("");

  // Über useMemo, nicht direkt mit ||.
  //
  // `x || []` liefert bei jedem Rendern ein *neues* leeres Array. Als
  // Abhängigkeit eines useMemo heißt das: die Berechnung läuft immer
  // wieder, der Merker bringt nichts. Bei neun Kategorien fällt das
  // nicht auf, aber es ist schlicht falsch -- und Next.js sagt es beim
  // Bauen auch.
  const categories: any[] = useMemo(
    () => p.data?.categories || [],
    [p.data?.categories]
  );
  const catDraft = useMemo(
    () => p.draft.categories || {},
    [p.draft.categories]
  );

  // Der aktuelle Stand einer Art: Entwurf schlägt Gespeichertes.
  const stateOf = useCallback(
    (cat: any) => ({
      enabled:
        catDraft[cat.key]?.enabled !== undefined
          ? catDraft[cat.key].enabled
          : cat.enabled,
      channel:
        catDraft[cat.key]?.channel !== undefined
          ? catDraft[cat.key].channel
          : cat.channel,
    }),
    [catDraft]
  );

  const active = useMemo(
    () => categories.filter((c) => { const s = stateOf(c); return s.enabled && s.channel; }),
    [categories, stateOf]
  );

  // Angeschaltet, aber ohne brauchbaren Kanal. Das ist der Zustand, in
  // dem jemand glaubt zu protokollieren und es nicht tut.
  const broken = useMemo(
    () =>
      categories.filter((c) => {
        const s = stateOf(c);
        if (!s.enabled) return false;
        if (!s.channel) return true;
        return s.channel === c.channel &&
          (c.channel_info?.missing || c.channel_info?.cannot_post);
      }),
    [categories, stateOf]
  );

  if (p.loading) return <Loading />;

  const changeCategory = (key: string, patch: any) =>
    p.set("categories", {
      ...catDraft,
      [key]: { ...(catDraft[key] || {}), ...patch },
    });

  /** Mehrere Arten auf einmal setzen -- für Gruppen und Voreinstellungen. */
  const applyMany = (keys: string[] | null, enabled: boolean, channel?: string) => {
    const affected = keys ?? categories.map((c) => c.key);
    const next = { ...catDraft };
    for (const key of affected) {
      next[key] = {
        ...(next[key] || {}),
        enabled,
        ...(channel !== undefined ? { channel } : {}),
      };
    }
    p.set("categories", next);
  };

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    if (!allChannel) {
      toast.error("Bitte zuerst einen Kanal wählen.");
      return;
    }

    // „Alles" geht über den Server-Endpunkt. Der prüft, ob es den Kanal
    // gibt und ob der Bot dort schreiben darf -- beides kann das
    // Dashboard nicht, und ein Kanal ohne Schreibrecht sieht hier
    // genauso aus wie einer mit.
    if (preset.keys === null) {
      p.act(() => api.setAllLogging(guildId, allChannel, true));
      return;
    }

    // Die anderen beiden schreiben in den Entwurf: sie schalten Arten
    // gezielt *ab*, und dafür gibt es keinen Endpunkt. Gespeichert wird
    // über dieselbe Leiste wie jede andere Änderung, damit man es noch
    // ansehen und verwerfen kann.
    //
    // Erst alles aus, dann die gewählten an -- sonst bleibt stehen, was
    // vorher an war, und „Das Nötigste" wäre nicht das Nötigste.
    const next: Record<string, any> = {};
    for (const cat of categories) {
      const wanted = preset.keys.includes(cat.key);
      next[cat.key] = wanted
        ? { enabled: true, channel: allChannel }
        : { enabled: false };
    }
    p.set("categories", next);
    toast.success(
      `„${preset.label}" vorbereitet — unten speichern, dann gilt es.`
    );
  };

  const ignoreUsers: string[] = p.value("ignore_users") || [];
  const exceptionCount =
    (p.value("ignore_channels") || []).length +
    (p.value("ignore_roles") || []).length +
    ignoreUsers.length;

  return (
    <section className="space-y-5">
      {/* ── Überblick + Schnellstart ───────────────────── */}
      <Card
        icon={Bell}
        title="Logs"
        subtitle="Der Bot schreibt mit, was auf dem Server passiert. Fang mit einer Voreinstellung an — einzeln einstellen kannst du danach immer noch."
        onReload={p.reload}
      >
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {active.length}
              <span className="text-slate-600 text-sm"> / {categories.length}</span>
            </p>
            <p className="text-[11px] text-slate-500">laufen</p>
          </div>
          <div
            className={cn(
              "border rounded-2xl px-4 py-3",
              broken.length
                ? "bg-red-500/[0.06] border-red-500/25"
                : "bg-[#0d1b31] border-slate-800"
            )}
          >
            <p
              className={cn(
                "text-lg font-black",
                broken.length ? "text-red-300" : "text-white"
              )}
            >
              {broken.length}
            </p>
            <p
              className={cn(
                "text-[11px]",
                broken.length ? "text-red-300/70" : "text-slate-500"
              )}
            >
              {broken.length === 1 ? "Problem" : "Probleme"}
            </p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">{exceptionCount}</p>
            <p className="text-[11px] text-slate-500">Ausnahmen</p>
          </div>
        </div>

        {/* Angeschaltet ohne Kanal ist der Zustand, in dem man glaubt zu
            protokollieren und es nicht tut. Der gehört nach oben. */}
        {broken.length > 0 && (
          <div className="rounded-xl bg-red-500/[0.06] border border-red-500/25 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-200/80 leading-relaxed">
              <strong>
                {broken.map((c) => c.label).join(", ")}
              </strong>{" "}
              {broken.length === 1 ? "ist an" : "sind an"}, aber dort landet
              nichts. Kanal fehlt, wurde gelöscht, oder der Bot darf nicht
              hineinschreiben.
            </p>
          </div>
        )}

        <div className="space-y-3">
          <ChannelPicker
            guildId={guildId}
            value={allChannel}
            onChange={(id: string | null) => setAllChannel(id || "")}
            placeholder="Kanal für die Voreinstellung"
            channelTypes={["0", "5"]}
          />
          <div className="grid sm:grid-cols-3 gap-2.5">
            {PRESETS.map((preset) => (
              <button
                key={preset.key}
                onClick={() => applyPreset(preset)}
                disabled={!allChannel}
                className={cn(
                  "text-left rounded-2xl border p-3.5 transition-all",
                  allChannel
                    ? "border-slate-800 bg-[#0d1b31] hover:border-primary/40 hover:-translate-y-0.5"
                    : "border-slate-800/60 bg-[#0d1b31]/60 opacity-50 cursor-not-allowed"
                )}
              >
                <p className="text-sm font-black text-white">{preset.label}</p>
                <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                  {preset.hint}
                </p>
                <p className="text-[10px] text-slate-600 mt-2 font-bold uppercase tracking-wider">
                  {preset.keys === null
                    ? `${categories.length} Arten`
                    : `${preset.keys.length} Arten`}
                </p>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-600 leading-relaxed">
            Eine Voreinstellung setzt alles auf einmal — auch das, was gerade
            an ist. Gespeichert wird erst unten.
          </p>
        </div>
      </Card>

      {/* ── Gruppen ────────────────────────────────────── */}
      <Card
        icon={Zap}
        title="Nach Bereich"
        subtitle="Drei Blöcke statt neun Schalter. Aufklappen für die einzelnen Arten."
      >
        <div className="space-y-2.5">
          {GROUPS.map((group) => {
            const members = categories.filter((c) => group.keys.includes(c.key));
            if (!members.length) return null;

            const on = members.filter((c) => stateOf(c).enabled).length;
            const open = openGroup === group.key;
            const GroupIcon = group.icon;

            return (
              <div
                key={group.key}
                className={cn(
                  "rounded-2xl border transition-colors",
                  on > 0
                    ? "bg-[#0d1b31] border-slate-700"
                    : "bg-[#0d1b31]/60 border-slate-800"
                )}
              >
                <div className="flex items-center gap-3 p-3.5">
                  <div
                    className={cn(
                      "h-9 w-9 rounded-xl grid place-items-center shrink-0",
                      on > 0 ? "bg-primary/15" : "bg-white/[0.03]"
                    )}
                  >
                    <GroupIcon
                      className={cn(
                        "h-4 w-4",
                        on > 0 ? "text-primary" : "text-slate-600"
                      )}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-sm text-white">
                      {group.label}
                      <span className="text-slate-600 font-mono text-[11px] ml-2">
                        {on}/{members.length}
                      </span>
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {group.hint}
                    </p>
                  </div>

                  <button
                    onClick={() =>
                      applyMany(group.keys, on < members.length)
                    }
                    className="shrink-0 px-3 py-1.5 rounded-lg border border-slate-700 text-[10px] font-black uppercase tracking-wider text-slate-400 hover:text-white hover:border-slate-600 transition-colors"
                  >
                    {on < members.length ? "Alle an" : "Alle aus"}
                  </button>

                  <button
                    onClick={() => setOpenGroup(open ? null : group.key)}
                    className="shrink-0 h-8 w-8 rounded-lg grid place-items-center text-slate-500 hover:text-white transition-colors"
                    title={open ? "Zuklappen" : "Einzeln einstellen"}
                  >
                    <ChevronDown
                      className={cn(
                        "h-4 w-4 transition-transform duration-300",
                        open && "rotate-180"
                      )}
                    />
                  </button>
                </div>

                {open && (
                  <div className="px-3.5 pb-3.5 space-y-2.5 border-t border-slate-800/70 pt-3">
                    {members.map((cat) => (
                      <CategoryRow
                        key={cat.key}
                        cat={cat}
                        guildId={guildId}
                        draft={catDraft[cat.key]}
                        busy={p.busy}
                        onChange={(patch: any) => changeCategory(cat.key, patch)}
                        onTest={() =>
                          p.act(() => api.testLogging(guildId, cat.key))
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {active.length > 0 && (
          <button
            onClick={() => applyMany(null, false)}
            className="w-full py-2.5 rounded-xl border border-slate-800 text-[11px] font-black uppercase tracking-widest text-slate-500 hover:text-red-300 hover:border-red-500/30 transition-colors"
          >
            Alles ausschalten
          </button>
        )}
      </Card>

      {/* ── Ausnahmen ──────────────────────────────────── */}
      <Card
        icon={AtSign}
        title="Ausnahmen"
        subtitle="Kanäle, Rollen und Mitglieder, über die nichts protokolliert wird."
      >
        <button
          onClick={() => setExceptions((open) => !open)}
          className="w-full flex items-center gap-2.5 px-4 py-3 rounded-2xl border border-slate-800 bg-[#0d1b31] hover:border-slate-700 transition-colors"
        >
          <span className="text-[11px] font-black uppercase tracking-wider text-slate-400">
            {exceptionCount === 0
              ? "Keine Ausnahmen"
              : `${exceptionCount} ${exceptionCount === 1 ? "Ausnahme" : "Ausnahmen"}`}
          </span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 text-slate-600 ml-auto transition-transform duration-300",
              exceptions && "rotate-180"
            )}
          />
        </button>

        {exceptions && (
          <div className="space-y-4 rounded-2xl border border-slate-800 bg-[#0d1b31] p-4">
            <div className="space-y-2">
              <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                Kanäle
              </span>
              <MultiChannelPicker
                guildId={guildId}
                value={p.value("ignore_channels") || []}
                onChange={(ids: string[]) => p.set("ignore_channels", ids)}
              />
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Die Log-Kanäle selbst gehören hierhin — sonst protokolliert
                jeder Eintrag den nächsten.
              </p>
            </div>

            <div className="space-y-2">
              <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                Rollen
              </span>
              <MultiRolePicker
                guildId={guildId}
                value={p.value("ignore_roles") || []}
                onChange={(ids: string[]) => p.set("ignore_roles", ids)}
              />
            </div>

            <div className="space-y-2">
              <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                Mitglieder
              </span>
              <div className="flex gap-2">
                <div className="flex-1 min-w-0">
                  <UserPicker
                    guildId={guildId}
                    value={userId}
                    onChange={(id: string | null) => setUserId(id || "")}
                  />
                </div>
                <button
                  onClick={() => {
                    if (!userId) return;
                    if (ignoreUsers.includes(userId)) {
                      toast.error("Steht schon auf der Liste.");
                      return;
                    }
                    p.set("ignore_users", [...ignoreUsers, userId]);
                    setUserId("");
                  }}
                  disabled={!userId}
                  className="shrink-0 px-4 rounded-xl bg-primary text-[11px] font-black uppercase tracking-wider disabled:opacity-40 transition-all"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
              </div>
              {ignoreUsers.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {ignoreUsers.map((id) => (
                    <span
                      key={id}
                      className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-slate-800 text-[11px] font-mono text-slate-400"
                    >
                      {id}
                      <button
                        onClick={() =>
                          p.set(
                            "ignore_users",
                            ignoreUsers.filter((x) => x !== id)
                          )
                        }
                        className="text-slate-600 hover:text-red-400 transition-colors"
                        title="Entfernen"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Card>

      <StickySaveBar
        id="logging-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        // Wie in jedem anderen Reiter: act() lädt danach neu, und
        // reload() leert den Entwurf selbst -- ein zusätzliches
        // discard() wäre doppelt gemoppelt.
        onSave={() => p.act(() => api.updateLogging(guildId, p.draft))}
      />
    </section>
  );
}
