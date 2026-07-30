"use client";

/**
 * Logging.
 *
 * What this replaces: six cards, in English, each saving the moment you
 * touched it. Three of the cog's nine categories were missing entirely
 * (emoji, reaction and server-update logging), the ignore lists were
 * shown as two numbers with no way to change them, and nothing told you
 * that the bot could not post in the channel you had picked.
 *
 * Layout follows the automod and verification tabs: switch a category on,
 * pick a channel, done. Everything else sits behind &bdquo;Erweitert&ldquo;,
 * there is one save bar for the whole page, and leaving with unsaved
 * changes is refused.
 */

import React, { useCallback, useState } from "react";
import {
  AlertTriangle, AtSign, Bell, Hash, Mic, MessageSquare, RefreshCw, Send,
  Settings, Shield, ShieldAlert, Smile, Sparkles, Trash2, UserPlus, Users, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ChannelPicker, MultiChannelPicker, MultiRolePicker,
} from "@/components/dashboard/pickers";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";
import {
  Loading, StickySaveBar, usePanel, useSaveGuard,
} from "@/components/dashboard/save-bar";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

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

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

function Card({ icon: Icon, title, subtitle, children, onReload }: any) {
  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">{title}</p>
            {subtitle && (
              <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {onReload && (
          <button
            onClick={onReload}
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
      <div className="text-[12px] text-amber-200/80 leading-relaxed">
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

/** One category: a switch, a channel, and a test button once it is set. */
function CategoryCard({ cat, draft, onChange, onTest, busy }: any) {
  const Icon = ICONS[cat.key] || Bell;

  // The draft wins so a half-finished edit is never lost by a reload.
  const value = (field: string) =>
    draft?.[field] !== undefined ? draft[field] : cat[field];

  const enabled = !!value("enabled");
  const channel = value("channel") || "";
  // The name only comes back from the server, so a channel just picked in
  // the browser has none yet -- fall back to a neutral label.
  const channelName =
    channel === cat.channel ? cat.channel_info?.name : null;

  return (
    <div
      className={cn(
        "rounded-2xl border transition-colors",
        enabled && channel
          ? "bg-[#0d1b31] border-primary/30"
          : "bg-[#0d1b31]/60 border-slate-800"
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <div
          className={cn(
            "h-9 w-9 rounded-xl grid place-items-center shrink-0",
            enabled ? "bg-primary/15" : "bg-white/[0.03]"
          )}
        >
          <Icon className={cn("h-4 w-4", enabled ? "text-primary" : "text-slate-600")} />
        </div>

        <div className="min-w-0 flex-1">
          <p className={cn("font-bold text-sm", enabled ? "text-white" : "text-slate-400")}>
            {cat.label}
            {cat.noisy && (
              <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400/80 text-[9px] font-black uppercase tracking-wider align-middle">
                viel
              </span>
            )}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
            {cat.description}
          </p>
          {enabled && !channel && (
            <p className="text-[11px] text-red-400/80 mt-1.5">
              Kein Kanal — hier wird nichts gepostet.
            </p>
          )}
          {enabled && channel && cat.channel_info?.missing && (
            <p className="text-[11px] text-red-400/80 mt-1.5">
              Diesen Kanal gibt es nicht mehr.
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
        <div className="px-4 pb-4 space-y-3 border-t border-slate-800/70 pt-3">
          <ChannelPicker
            guildId={cat.guildId}
            value={channel}
            onChange={(id: string | null) => onChange({ channel: id })}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
          {channel && channel === cat.channel && (
            <button
              onClick={onTest}
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
            >
              <Send className="h-3.5 w-3.5" />
              Testeintrag posten
              {channelName ? ` (#${channelName})` : ""}
            </button>
          )}
          {channel && channel !== cat.channel && (
            <p className="text-[11px] text-slate-600 text-center">
              Erst speichern, dann lässt sich der Kanal testen.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function LoggingPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getLogging(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "logging-save-bar");
  const [exceptions, setExceptions] = useState(false);
  const [allChannel, setAllChannel] = useState("");
  const [userId, setUserId] = useState("");

  if (p.loading) return <Loading />;

  const categories: any[] = p.data?.categories || [];
  const catDraft = p.draft.categories || {};

  const changeCategory = (key: string, patch: any) =>
    p.set("categories", {
      ...catDraft,
      [key]: { ...(catDraft[key] || {}), ...patch },
    });

  const activeNow = categories.filter((c) => {
    const enabled =
      catDraft[c.key]?.enabled !== undefined ? catDraft[c.key].enabled : c.enabled;
    const channel =
      catDraft[c.key]?.channel !== undefined ? catDraft[c.key].channel : c.channel;
    return enabled && channel;
  }).length;

  const ignoreUsers: string[] = p.value("ignore_users") || [];

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />

      <Card
        icon={Bell}
        title="Logs"
        subtitle="Der Bot schreibt mit, was auf dem Server passiert. Jede Art von Ereignis kann in einen eigenen Kanal."
        onReload={p.reload}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {activeNow} / {categories.length}
            </p>
            <p className="text-[11px] text-slate-500">Arten werden protokolliert</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {(p.value("ignore_channels") || []).length +
                (p.value("ignore_roles") || []).length +
                ignoreUsers.length}
            </p>
            <p className="text-[11px] text-slate-500">Ausnahmen</p>
          </div>
        </div>

        {activeNow === 0 && (
          <div className="rounded-xl bg-primary/[0.06] border border-primary/25 p-4 space-y-3">
            <p className="text-[12px] text-slate-300 leading-relaxed">
              Noch nichts eingerichtet. Der schnellste Start: einen Kanal
              wählen, dann landet alles dort. Einzeln aufteilen kannst du es
              danach immer noch.
            </p>
            <ChannelPicker
              guildId={guildId}
              value={allChannel}
              onChange={(id: string | null) => setAllChannel(id || "")}
              placeholder="Kanal für alles"
              channelTypes={["0", "5"]}
            />
            <button
              onClick={() => {
                if (!allChannel) return toast.error("Bitte erst einen Kanal wählen.");
                p.act(() => api.setAllLogging(guildId, allChannel));
              }}
              disabled={p.busy || !allChannel}
              className="w-full py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
            >
              Alles hierhin protokollieren
            </button>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Reaktionen bleiben dabei aus — die feuern bei jedem Klick auf
              ein Emoji und fluten den Kanal.
            </p>
          </div>
        )}
      </Card>

      <div className="space-y-3">
        {categories.map((cat) => (
          <CategoryCard
            key={cat.key}
            cat={{ ...cat, guildId }}
            draft={catDraft[cat.key]}
            busy={p.busy}
            onChange={(patch: any) => changeCategory(cat.key, patch)}
            onTest={() => p.act(() => api.testLogging(guildId, cat.key))}
          />
        ))}
      </div>

      {/* ── Exceptions ───────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden">
        <button
          onClick={() => setExceptions((o) => !o)}
          className="w-full flex items-center justify-between gap-4 p-6"
        >
          <div className="flex gap-3 min-w-0 text-left">
            <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="font-black text-white">Erweitert</p>
              <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
                Ausnahmen und automatisches Aufräumen. Für den Anfang nicht
                nötig.
              </p>
            </div>
          </div>
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 shrink-0">
            {exceptions ? "Zu" : "Auf"}
          </span>
        </button>

        {exceptions && (
          <div className="px-6 pb-6 space-y-5">
            <Field
              label="Kanäle ausnehmen"
              hint="Was hier passiert, taucht im Protokoll nicht auf. Praktisch für Spam- oder Bot-Kanäle."
            >
              <MultiChannelPicker
                guildId={guildId}
                value={p.value("ignore_channels") || []}
                onChange={(ids: string[]) => p.set("ignore_channels", ids)}
              />
            </Field>

            <Field
              label="Rollen ausnehmen"
              hint="Mitglieder mit einer dieser Rollen werden nicht protokolliert — zum Beispiel das Team."
            >
              <MultiRolePicker
                guildId={guildId}
                value={p.value("ignore_roles") || []}
                onChange={(ids: string[]) => p.set("ignore_roles", ids)}
              />
            </Field>

            <Field
              label="Einzelne Mitglieder ausnehmen"
              hint="Für Bots, die sonst jede Minute im Protokoll stehen."
            >
              <div className="flex gap-2">
                <div className="flex-1 min-w-0">
                  <UserPicker
                    guildId={guildId}
                    value={userId}
                    onChange={setUserId}
                    label=""
                    placeholder="Mitglied suchen oder ID einfügen"
                  />
                </div>
                <button
                  onClick={() => {
                    if (!userId) return toast.error("Erst ein Mitglied wählen.");
                    if (ignoreUsers.includes(userId)) {
                      return toast.info("Steht schon auf der Liste.");
                    }
                    p.set("ignore_users", [...ignoreUsers, userId]);
                    setUserId("");
                  }}
                  className="px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shrink-0 hover:brightness-110 transition-all"
                >
                  Dazu
                </button>
              </div>

              {ignoreUsers.length > 0 && (
                <div className="space-y-2 pt-2">
                  {ignoreUsers.map((id) => {
                    const info = (p.data?.ignore_users_info || []).find(
                      (u: any) => u.id === id
                    );
                    return (
                      <div
                        key={id}
                        className="flex items-center gap-3 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2.5"
                      >
                        {info?.avatar ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={info.avatar}
                            alt=""
                            className="h-7 w-7 rounded-full shrink-0"
                          />
                        ) : (
                          <div className="h-7 w-7 rounded-full bg-slate-800 shrink-0" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-white truncate">
                            {info?.name || "Nicht mehr auf dem Server"}
                          </p>
                          <p className="text-[11px] text-slate-600 font-mono truncate">
                            {id}
                          </p>
                        </div>
                        <button
                          onClick={() =>
                            p.set(
                              "ignore_users",
                              ignoreUsers.filter((u) => u !== id)
                            )
                          }
                          className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 shrink-0 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </Field>

            <Field
              label="Einträge automatisch löschen nach (Sekunden)"
              hint="0 = bleiben stehen. Höchstens 86400 (ein Tag). Sinnvoll, wenn der Protokoll-Kanal sonst überläuft."
            >
              <input
                type="number"
                min={0}
                max={86400}
                className={INPUT}
                value={p.value("auto_delete_duration") ?? 0}
                onChange={(e) =>
                  p.set("auto_delete_duration", Number(e.target.value) || 0)
                }
              />
            </Field>
          </div>
        )}
      </div>

      <StickySaveBar
        id="logging-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() => p.act(() => api.updateLogging(guildId, p.draft))}
      />
    </section>
  );
}
