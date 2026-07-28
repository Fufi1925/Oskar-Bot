"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Hash, Link2, Loader2, Lock, LockOpen,
  RefreshCcw, Shield, ShieldAlert, ShieldOff, Sparkles, Timer, Trash2,
  Users, Webhook,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Per-guild server tools.
 *
 * This page used to be twenty toggles that wrote a boolean nobody read —
 * nineteen of the twenty keys did not appear anywhere in the bot's source,
 * so flipping them looked like configuring something and did nothing.
 *
 * Everything here queries the live guild instead: the findings are real,
 * they name the role, bot or webhook they are about, and the one action
 * (deleting a webhook) actually changes the server.
 */

type TabId = "overview" | "security" | "roles" | "channels" | "invites" | "webhooks";

const TABS: Array<{ id: TabId; label: string; icon: any }> = [
  { id: "overview", label: "Übersicht", icon: Shield },
  { id: "security", label: "Sicherheit", icon: ShieldAlert },
  { id: "roles", label: "Rollen", icon: Users },
  { id: "channels", label: "Kanäle", icon: Hash },
  { id: "invites", label: "Einladungen", icon: Link2 },
  { id: "webhooks", label: "Webhooks", icon: Webhook },
];

const SEVERITY = {
  high: { label: "Hoch", cls: "bg-red-500/10 border-red-500/30 text-red-300" },
  medium: { label: "Mittel", cls: "bg-amber-500/10 border-amber-500/30 text-amber-300" },
  low: { label: "Niedrig", cls: "bg-sky-500/10 border-sky-500/30 text-sky-300" },
  // Not a problem — a note. Rendered in grey so it does not read as a warning.
  info: { label: "Info", cls: "bg-white/[0.03] border-white/10 text-slate-400" },
} as const;

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6", className)}>
      {children}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div>
      <p className="text-2xl font-black text-white tabular-nums">{value}</p>
      <p className="text-[10px] uppercase tracking-widest text-slate-500 font-black mt-1">
        {label}
      </p>
      {hint && <p className="text-[11px] text-slate-600 mt-0.5">{hint}</p>}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-center text-slate-500 py-10 text-sm">{text}</p>;
}

export default function ServerToolsPage({ params }: { params: { guildId: string } }) {
  const guildId = params.guildId;
  const [tab, setTab] = useState<TabId>("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const load = useCallback(
    async (which: TabId, force = false) => {
      if (data[which] && !force) return;
      setLoading(true);
      const fetchers: Record<TabId, () => Promise<any>> = {
        overview: () => api.getServerOverview(guildId),
        security: () => api.runSecurityScan(guildId),
        roles: () => api.getRoleAudit(guildId),
        channels: () => api.getChannelAudit(guildId),
        invites: () => api.getInviteAudit(guildId),
        webhooks: () => api.getWebhookAudit(guildId),
      };
      try {
        const result = await fetchers[which]();
        setData((d) => ({ ...d, [which]: result }));
        setErrors((e) => ({ ...e, [which]: "" }));
      } catch (err: any) {
        setErrors((e) => ({ ...e, [which]: err?.message || "Konnte nicht geladen werden." }));
      } finally {
        setLoading(false);
      }
    },
    [guildId, data]
  );

  useEffect(() => {
    load(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  /** Run an action, then refresh the affected views. */
  const act = async (
    label: string,
    fn: () => Promise<any>,
    refresh: TabId[] = [],
    confirmText?: string
  ) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || label);
      // Drop the caches that this action invalidated.
      setData((d) => {
        const next = { ...d };
        for (const t of refresh) delete next[t];
        return next;
      });
      await load(tab, true);
    } catch (err: any) {
      toast.error(err?.message || "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const removeWebhook = async (id: string, name: string) => {
    if (!confirm(`Webhook „${name}" wirklich löschen?`)) return;
    setBusy(true);
    try {
      await api.deleteWebhook(guildId, id);
      toast.success(`Webhook „${name}" gelöscht.`);
      await load("webhooks", true);
      setData((d) => ({ ...d, security: undefined }));
    } catch (err: any) {
      toast.error(err?.message || "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const current = data[tab];
  const error = errors[tab];

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Shield className="h-6 w-6 text-primary" />
            Server-Werkzeuge
          </h2>
          <p className="text-slate-400 mt-1 text-sm">
            Live-Analyse dieses Servers — jede Zahl kommt direkt von Discord.
          </p>
        </div>
        <button
          onClick={() => load(tab, true)}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
        >
          <RefreshCcw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Neu laden
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest border transition-all",
              tab === t.id
                ? "bg-primary/15 border-primary/40 text-primary"
                : "bg-[#10233f] border-slate-800 text-slate-400 hover:text-slate-200"
            )}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {loading && !current ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
        </div>
      ) : error ? (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <div className="flex gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
            <div>
              <p className="font-bold text-white">Nicht verfügbar</p>
              <p className="text-sm text-amber-200/80 mt-1">{error}</p>
            </div>
          </div>
        </Card>
      ) : !current ? null : (
        <>
          {/* ── Übersicht ─────────────────────────────────── */}
          {tab === "overview" && (
            <div className="space-y-4">
              <Card>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <Stat label="Mitglieder" value={current.members.total.toLocaleString("de-DE")}
                        hint={`${current.members.humans} Menschen · ${current.members.bots} Bots`} />
                  <Stat label="Kanäle"
                        value={current.channels.text + current.channels.voice}
                        hint={`${current.channels.text} Text · ${current.channels.voice} Voice`} />
                  <Stat label="Rollen" value={current.roles} />
                  <Stat label="Boosts" value={current.boosts ?? 0}
                        hint={`Stufe ${current.boost_level}`} />
                </div>
              </Card>

              <Card>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="font-black text-white">Notfall-Sperre</p>
                    <p className="text-sm text-slate-400 mt-1">
                      Nimmt @everyone in allen Textkanälen das Schreibrecht — oder
                      gibt es zurück. Ändert echte Kanalrechte.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        act(
                          "Server gesperrt.",
                          () => api.setLockdown(guildId, true),
                          ["channels", "security"],
                          "Wirklich alle Textkanäle sperren?\n\n@everyone kann dann nirgends mehr schreiben."
                        )
                      }
                      disabled={busy}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/15 border border-red-500/30 text-red-300 hover:bg-red-500/25 transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
                    >
                      <Lock className="h-3.5 w-3.5" />
                      Sperren
                    </button>
                    <button
                      onClick={() =>
                        act(
                          "Sperre aufgehoben.",
                          () => api.setLockdown(guildId, false),
                          ["channels", "security"]
                        )
                      }
                      disabled={busy}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
                    >
                      <LockOpen className="h-3.5 w-3.5" />
                      Entsperren
                    </button>
                  </div>
                </div>
              </Card>

              {current.bot_missing_permissions?.length > 0 && (
                <Card className="border-amber-500/30 bg-amber-500/5">
                  <div className="flex gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
                    <div>
                      <p className="font-bold text-white">Dem Bot fehlen Rechte</p>
                      <p className="text-sm text-amber-200/80 mt-1">
                        Ohne diese Berechtigungen funktionieren Teile des Bots nicht:{" "}
                        <span className="font-mono">
                          {current.bot_missing_permissions.join(", ")}
                        </span>
                      </p>
                    </div>
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* ── Sicherheit ────────────────────────────────── */}
          {tab === "security" && (
            <div className="space-y-4">
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-6">
                  <div className="flex items-center gap-5">
                    <div
                      className={cn(
                        "h-20 w-20 rounded-3xl flex items-center justify-center text-2xl font-black border-2",
                        current.score >= 80
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                          : current.score >= 50
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                          : "bg-red-500/10 border-red-500/30 text-red-400"
                      )}
                    >
                      {current.score}
                    </div>
                    <div>
                      <p className="font-black text-white text-lg">Sicherheits-Score</p>
                      <p className="text-sm text-slate-400 mt-0.5">
                        {current.counts.high} hoch · {current.counts.medium} mittel ·{" "}
                        {current.counts.low} niedrig
                        {current.counts.info ? ` · ${current.counts.info} Info` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-6 text-right">
                    <Stat label="Admin-Rollen" value={current.stats.admin_roles} />
                    <Stat label="Webhooks" value={current.stats.webhooks} />
                    <Stat label="Neue Accounts" value={current.stats.new_accounts_7d}
                          hint="letzte 7 Tage" />
                  </div>
                </div>
              </Card>

              {current.findings.length === 0 ? (
                <Card>
                  <div className="flex items-center gap-3 justify-center py-6">
                    <CheckCircle2 className="h-6 w-6 text-emerald-400" />
                    <p className="text-slate-300 font-bold">Keine Auffälligkeiten gefunden.</p>
                  </div>
                </Card>
              ) : (
                <div className="space-y-3">
                  {current.findings.map((f: any, i: number) => {
                    const sev = SEVERITY[f.severity as keyof typeof SEVERITY] ?? SEVERITY.low;
                    return (
                      <div key={i} className={cn("rounded-2xl border p-5", sev.cls)}>
                        <div className="flex items-start gap-3">
                          <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-black/25 shrink-0">
                            {sev.label}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-white">{f.title}</p>
                            <p className="text-sm opacity-80 mt-1">{f.detail}</p>
                          </div>

                          {/* Each finding that can be fixed gets its fix here. */}
                          {f.kind === "admin_role" && f.target_id && (
                            <button
                              onClick={() =>
                                act(
                                  "Administrator entfernt.",
                                  () => api.stripRoleAdmin(guildId, f.target_id),
                                  ["roles"],
                                  "Administrator-Recht von dieser Rolle entfernen?\n\nAlle anderen Rechte bleiben erhalten."
                                )
                              }
                              disabled={busy}
                              className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl bg-black/25 border border-white/10 hover:bg-black/40 transition-all text-[11px] font-black uppercase tracking-widest disabled:opacity-50"
                            >
                              <ShieldOff className="h-3.5 w-3.5" />
                              Admin entziehen
                            </button>
                          )}

                          {f.kind === "verification_level" && (
                            <button
                              onClick={() =>
                                act(
                                  "Verifizierung auf Mittel gesetzt.",
                                  () => api.setVerificationLevel(guildId, "medium"),
                                  ["overview"]
                                )
                              }
                              disabled={busy}
                              className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl bg-black/25 border border-white/10 hover:bg-black/40 transition-all text-[11px] font-black uppercase tracking-widest disabled:opacity-50"
                            >
                              <Shield className="h-3.5 w-3.5" />
                              Auf Mittel setzen
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Rollen ────────────────────────────────────── */}
          {tab === "roles" && (
            <div className="space-y-4">
              <Card>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <Stat label="Rollen" value={current.summary.total} />
                  <Stat label="Mit Admin" value={current.summary.with_admin} />
                  <Stat label="Ungenutzt" value={current.summary.unused} />
                  <Stat label="Über dem Bot" value={current.summary.above_bot}
                        hint="kann der Bot nicht vergeben" />
                </div>

                {current.summary.unused > 0 && (
                  <div className="mt-6 pt-5 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-slate-400">
                      {current.summary.unused} Rolle(n) hat niemand.
                    </p>
                    <button
                      onClick={() =>
                        act(
                          "Ungenutzte Rollen gelöscht.",
                          () => api.cleanupUnusedRoles(guildId),
                          ["security"],
                          `${current.summary.unused} ungenutzte Rolle(n) löschen?\n\nRollen von Integrationen und Rollen über dem Bot bleiben bestehen.`
                        )
                      }
                      disabled={busy}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest disabled:opacity-50"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Aufräumen
                    </button>
                  </div>
                )}
              </Card>

              <div className="space-y-2">
                {current.roles.length === 0 ? (
                  <Empty text="Keine Rollen gefunden." />
                ) : (
                  current.roles.map((r: any) => (
                    <div key={r.id}
                         className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-4 flex items-center gap-4 flex-wrap">
                      <span className="h-3 w-3 rounded-full shrink-0"
                            style={{ background: r.colour }} />
                      <span className="font-bold text-white truncate flex-1 min-w-[120px]">
                        {r.name}
                      </span>
                      <span className="text-xs text-slate-500 tabular-nums">
                        {r.members} Mitglieder
                      </span>
                      {r.dangerous_permissions.includes("administrator") && (
                        <span
                          className={cn(
                            "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg border",
                            r.bot_role
                              ? "bg-white/[0.04] text-slate-400 border-white/10"
                              : "bg-red-500/15 text-red-300 border-red-500/25"
                          )}
                        >
                          Administrator
                        </span>
                      )}
                      {r.bot_role && (
                        <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-sky-500/10 text-sky-300 border border-sky-500/25">
                          Bot-Rolle
                        </span>
                      )}
                      {r.above_bot && (
                        <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/25">
                          Über dem Bot
                        </span>
                      )}
                      {r.unused && (
                        <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-white/[0.04] text-slate-400 border border-white/10">
                          Ungenutzt
                        </span>
                      )}

                      {/* Roles above the bot, and bot/integration roles,
                          cannot be changed from here — so no buttons. */}
                      {!r.above_bot && !r.managed && !r.bot_role && (
                        <div className="flex gap-1.5 shrink-0">
                          {r.dangerous_permissions.includes("administrator") && (
                            <button
                              onClick={() =>
                                act(
                                  "Administrator entfernt.",
                                  () => api.stripRoleAdmin(guildId, r.id),
                                  ["security"],
                                  `Administrator von „${r.name}" entfernen?`
                                )
                              }
                              disabled={busy}
                              className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-amber-400 hover:bg-amber-400/10 transition-all disabled:opacity-40"
                              title="Administrator entziehen"
                            >
                              <ShieldOff className="h-4 w-4" />
                            </button>
                          )}
                          <button
                            onClick={() =>
                              act(
                                "Rolle gelöscht.",
                                () => api.deleteGuildRole(guildId, r.id),
                                ["security"],
                                `Rolle „${r.name}" wirklich löschen?` +
                                  (r.members > 0
                                    ? `\n\n${r.members} Mitglied(er) verlieren sie.`
                                    : "")
                              )
                            }
                            disabled={busy}
                            className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                            title="Rolle löschen"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* ── Kanäle ────────────────────────────────────── */}
          {tab === "channels" && (
            <div className="space-y-4">
              <Card>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <Stat label="Textkanäle" value={current.summary.total} />
                  <Stat label="Öffentlich" value={current.summary.public} />
                  <Stat label="Bot stumm" value={current.summary.bot_cannot_send}
                        hint="Bot darf nicht schreiben" />
                  <Stat label="Slowmode" value={current.summary.with_slowmode} />
                </div>
              </Card>

              <div className="space-y-2">
                {current.channels.map((c: any) => (
                  <div key={c.id}
                       className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-4 flex items-center gap-4 flex-wrap">
                    <Hash className="h-4 w-4 text-slate-500 shrink-0" />
                    <span className="font-bold text-white truncate flex-1 min-w-[120px]">
                      {c.name}
                    </span>
                    {c.category && (
                      <span className="text-xs text-slate-500">{c.category}</span>
                    )}
                    {!c.bot_can_send && (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/25">
                        Bot darf nicht schreiben
                      </span>
                    )}
                    {c.slowmode > 0 && (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-white/[0.04] text-slate-400 border border-white/10">
                        {c.slowmode}s Slowmode
                      </span>
                    )}

                    <select
                      value={c.slowmode}
                      disabled={busy}
                      onChange={(e) =>
                        act(
                          "Slowmode gesetzt.",
                          () =>
                            api.setChannelSlowmode(
                              guildId,
                              c.id,
                              Number(e.target.value)
                            ),
                          []
                        )
                      }
                      className="shrink-0 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-primary/50 disabled:opacity-50"
                      title="Slowmode"
                    >
                      {[0, 5, 10, 30, 60, 300, 900].map((sec) => (
                        <option key={sec} value={sec}>
                          {sec === 0 ? "Kein Slowmode" : `${sec}s`}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Einladungen ───────────────────────────────── */}
          {tab === "invites" && (
            <div className="space-y-2">
              {current.invites.length === 0 ? (
                <Empty text="Keine aktiven Einladungen." />
              ) : (
                current.invites.map((i: any) => (
                  <div key={i.code}
                       className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-4 flex items-center gap-4 flex-wrap">
                    <code className="font-mono font-bold text-white">{i.code}</code>
                    <span className="text-xs text-slate-500 flex-1 min-w-[100px]">
                      {i.channel ? `#${i.channel}` : "—"}
                      {i.inviter ? ` · von ${i.inviter}` : ""}
                    </span>
                    <span className="text-xs text-slate-400 tabular-nums">
                      {i.uses} Nutzungen
                    </span>
                    {i.permanent && (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/25">
                        Läuft nie ab
                      </span>
                    )}
                    <button
                      onClick={() =>
                        act(
                          "Einladung widerrufen.",
                          () => api.revokeInvite(guildId, i.code),
                          ["security"],
                          `Einladung „${i.code}" widerrufen?`
                        )
                      }
                      disabled={busy}
                      className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                      title="Einladung widerrufen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* ── Webhooks ──────────────────────────────────── */}
          {tab === "webhooks" && (
            <div className="space-y-2">
              {current.webhooks.length === 0 ? (
                <Empty text="Keine Webhooks eingerichtet." />
              ) : (
                current.webhooks.map((w: any) => (
                  <div key={w.id}
                       className="bg-[#10233f] border border-slate-800 rounded-2xl px-5 py-4 flex items-center gap-4 flex-wrap">
                    <Webhook className="h-4 w-4 text-slate-500 shrink-0" />
                    <span className="font-bold text-white truncate flex-1 min-w-[120px]">
                      {w.name}
                    </span>
                    <span className="text-xs text-slate-500">
                      {w.channel ? `#${w.channel}` : "—"}
                      {w.created_by ? ` · ${w.created_by}` : ""}
                    </span>
                    <button
                      onClick={() => removeWebhook(w.id, w.name)}
                      disabled={busy}
                      className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                      title="Webhook löschen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
