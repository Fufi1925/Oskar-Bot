"use client";

/**
 * Reaction roles.
 *
 * The page this replaces listed every pair flat and, worse, adding one
 * through the dashboard only wrote a database row — the reaction was
 * never put on the message, so members had nothing to click. The chat
 * command did it correctly, which made the difference easy to miss.
 *
 * Entries are grouped by message here because that is how people think
 * about them ("this post hands out these four roles"), and a dead
 * message shows up immediately instead of hiding in a long list.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Check, ExternalLink, Info, Loader2, MessageSquare, Plus,
  RefreshCw, Smile, Sparkles, Trash2, Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

const COMMON_EMOJI = ["✅", "🎮", "🎨", "🎵", "📢", "🔔", "⭐", "❤️", "🟢", "🔵"];

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

export function ReactionRolesPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<any>(null);

  const [channelId, setChannelId] = useState("");
  const [messageId, setMessageId] = useState("");
  const [emoji, setEmoji] = useState("");
  const [roleId, setRoleId] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.getReactionRolesV2(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      await load();
      return res;
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const res = await api.verifyReactionRoles(guildId);
      setReport(res);
      toast.success(res?.result || "Geprüft.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Prüfung fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const canAdd = channelId && messageId.trim() && emoji.trim() && roleId;

  return (
    <section className="space-y-6">
      {/* ── What this does ───────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-4">
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Smile className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-black text-white">Rolle per Reaktion</p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Wer auf einer Nachricht mit einem bestimmten Emoji reagiert,
              bekommt automatisch die passende Rolle.
            </p>
          </div>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] shrink-0"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        </div>

        <InlineToggle
          checked={data?.dm_enabled}
          onCheckedChange={(v: boolean) =>
            act(() => api.updateReactionRoleSettings(guildId, { dm_enabled: v }))
          }
          label="Mitglied per DM benachrichtigen"
          hint="Aus: die Rolle wird still vergeben."
        />
      </div>

      {/* ── Add ──────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-5">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Neue Reaktions-Rolle
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5 leading-relaxed">
            Rechtsklick auf die Nachricht in Discord → &bdquo;ID kopieren&ldquo;. Dafür muss
            in deinen Discord-Einstellungen der Entwicklermodus an sein.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-5">
          <Field label="Kanal" hint="In dem die Nachricht steht.">
            <ChannelPicker
              guildId={guildId}
              value={channelId}
              onChange={(id) => setChannelId(id || "")}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>

          <Field label="Nachrichten-ID">
            <input
              value={messageId}
              onChange={(e) => setMessageId(e.target.value.trim())}
              placeholder="1234567890123456789"
              className={cn(INPUT, "font-mono")}
            />
          </Field>

          <Field label="Emoji" hint="Server-Emojis gehen nur von Servern, auf denen der Bot ist.">
            <div className="space-y-2">
              <input
                value={emoji}
                onChange={(e) => setEmoji(e.target.value.trim())}
                placeholder="✅"
                className={INPUT}
              />
              <div className="flex flex-wrap gap-1.5">
                {COMMON_EMOJI.map((e) => (
                  <button
                    key={e}
                    onClick={() => setEmoji(e)}
                    className={cn(
                      "h-9 w-9 rounded-lg border text-base transition-all",
                      emoji === e
                        ? "bg-primary/15 border-primary/40"
                        : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                    )}
                  >
                    {e}
                  </button>
                ))}
              </div>
            </div>
          </Field>

          <Field label="Rolle" hint="Muss unter der Rolle des Bots stehen.">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
            />
          </Field>
        </div>

        <button
          onClick={() =>
            act(async () => {
              const res = await api.addReactionRoleV2(guildId, {
                channel_id: channelId,
                message_id: messageId,
                emoji,
                role_id: roleId,
              });
              setEmoji("");
              setRoleId("");
              return res;
            })
          }
          disabled={busy || !canAdd}
          title={canAdd ? undefined : "Kanal, ID, Emoji und Rolle ausfüllen"}
          className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Hinzufügen
        </button>

        <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5 flex gap-2.5">
          <Info className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Der Bot setzt die Reaktion selbst auf die Nachricht — du musst nichts
            von Hand anklicken. Klappt das nicht, sagt er warum, statt einen
            Eintrag anzulegen, der nie funktioniert.
          </p>
        </div>
      </div>

      {/* ── Verify ───────────────────────────────────── */}
      {data?.total > 0 && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-4">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Alles überprüfen
              </p>
              <p className="text-[11px] text-slate-600 mt-1.5 leading-relaxed">
                Nachrichten werden gelöscht, Rollen verschwinden, Reaktionen
                werden abgeräumt — alles drei sieht hier weiter richtig aus und
                tut in Discord nichts. Die Prüfung trägt fehlende Reaktionen
                gleich nach.
              </p>
            </div>
            <button
              onClick={verify}
              disabled={busy}
              className="flex items-center gap-2 px-5 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all shrink-0"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
              Prüfen
            </button>
          </div>

          {report && (
            <div className={cn(
              "rounded-xl border p-3.5 space-y-1.5",
              report.problems?.length
                ? "bg-amber-500/[0.06] border-amber-500/20"
                : "bg-emerald-500/[0.05] border-emerald-500/20"
            )}>
              <p className={cn(
                "text-[12px] font-bold flex items-center gap-1.5",
                report.problems?.length ? "text-amber-300" : "text-emerald-300"
              )}>
                {report.problems?.length ? (
                  <AlertTriangle className="h-3.5 w-3.5" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                {report.checked} geprüft
                {report.repaired > 0 && `, ${report.repaired} repariert`}
              </p>
              {(report.problems || []).map((p: string, i: number) => (
                <p key={i} className="text-[12px] text-amber-200/80">• {p}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Existing, grouped by message ─────────────── */}
      {!data?.messages?.length ? (
        <p className="text-sm text-slate-500 py-10 text-center border border-dashed border-slate-800 rounded-2xl">
          Noch keine Reaktions-Rolle eingerichtet.
        </p>
      ) : (
        <div className="space-y-4">
          {data.messages.map((message: any) => (
            <div
              key={message.message_id}
              className="bg-[#10233f] border border-slate-800 rounded-3xl p-5 space-y-3"
            >
              <div className="flex items-center gap-2.5 flex-wrap">
                <MessageSquare className="h-4 w-4 text-slate-600 shrink-0" />
                <span className="text-sm font-bold text-white">
                  Nachricht
                </span>
                <code className="px-2 py-0.5 rounded bg-white/[0.06] text-[11px] font-mono text-slate-400">
                  {message.message_id}
                </code>
                <span className="text-[11px] text-slate-600">
                  {message.entries.length} Rolle
                  {message.entries.length === 1 ? "" : "n"}
                </span>
              </div>

              <div className="space-y-2">
                {message.entries.map((entry: any) => (
                  <div
                    key={entry.emoji}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl border px-4 py-2.5",
                      entry.missing_role
                        ? "bg-red-500/[0.05] border-red-500/25"
                        : "bg-[#0d1b31] border-slate-800"
                    )}
                  >
                    <span className="text-lg shrink-0">{entry.emoji}</span>
                    <span className="text-slate-600">→</span>
                    <span
                      className={cn(
                        "text-sm font-bold flex-1 min-w-0 truncate",
                        entry.missing_role ? "text-red-400 italic" : "text-white"
                      )}
                      style={
                        !entry.missing_role && entry.role_colour
                          ? { color: `#${entry.role_colour.toString(16).padStart(6, "0")}` }
                          : undefined
                      }
                    >
                      {entry.missing_role
                        ? "Rolle wurde gelöscht"
                        : `@${entry.role_name}`}
                    </span>
                    <button
                      onClick={() =>
                        act(
                          () =>
                            api.removeReactionRoleV2(
                              guildId, message.message_id, entry.emoji, channelId
                            ),
                          `${entry.emoji} → @${entry.role_name} entfernen?`
                        )
                      }
                      disabled={busy}
                      className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all disabled:opacity-40 shrink-0"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
