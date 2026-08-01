"use client";

/**
 * Vanity roles: a role for members advertising the server in their status.
 *
 * The old page had three inputs and a list. It could not switch a setup
 * off, show who currently holds a role, run a sync, or tell you that the
 * role you picked sits above the bot and can never be handed out — that
 * last one failed silently forever.
 *
 * It also never explained what the feature does, which mattered because
 * the bot behind it used to do something else entirely.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Check, FlaskConical, Info, Link2, Loader2, Plus,
  RefreshCw, Search, Trash2, Users, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

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

function Stat({ label, value }: any) {
  return (
    <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
      <p className="text-lg font-black text-white">{value}</p>
      <p className="text-[11px] text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

export function VanityPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [holdersOf, setHoldersOf] = useState<string | null>(null);
  const [holders, setHolders] = useState<any[]>([]);

  const [trigger, setTrigger] = useState("");
  const [roleId, setRoleId] = useState("");
  const [logChannel, setLogChannel] = useState("");
  const [enabled, setEnabled] = useState(true);

  // Tester
  const [testFor, setTestFor] = useState<string | null>(null);
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.getVanityRoles(guildId));
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
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const add = () =>
    act(async () => {
      const res = await api.saveVanityRole(guildId, {
        vanity: trigger,
        role_id: roleId,
        log_channel_id: logChannel || null,
        enabled,
      });
      setTrigger("");
      setRoleId("");
      return res;
    });

  const openHolders = async (vanity: string) => {
    setHoldersOf(vanity);
    try {
      const res = await api.getVanityHolders(guildId, vanity);
      setHolders(res.holders || []);
    } catch {
      setHolders([]);
    }
  };

  const runTest = async (vanity: string) => {
    try {
      const res = await api.testVanityRole(guildId, vanity, testText);
      setTestResult(res.matches);
    } catch {
      setTestResult(null);
    }
  };

  // Show what the trigger will be reduced to, so nobody is surprised
  // that ".gg/MeinServer" and "meinserver" are the same thing.
  const normalised = useMemo(() => {
    let value = trigger.trim().toLowerCase();
    for (const prefix of [
      "https://discord.gg/", "http://discord.gg/",
      "https://discord.com/invite/", "http://discord.com/invite/",
      "discord.gg/", "discord.com/invite/", ".gg/",
    ]) {
      if (value.startsWith(prefix)) { value = value.slice(prefix.length); break; }
    }
    return value.split("?")[0].split("/")[0];
  }, [trigger]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const setups = data?.setups || [];

  return (
    <section className="space-y-6">
      {/* ── Holders dialog ───────────────────────────── */}
      {holdersOf && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-md shadow-2xl border-glow-card">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div className="min-w-0">
                <h3 className="font-black text-white truncate">
                  Hat die Rolle ({holders.length})
                </h3>
                <p className="text-[11px] text-slate-500">.gg/{holdersOf}</p>
              </div>
              <button
                onClick={() => setHoldersOf(null)}
                className="text-slate-500 hover:text-white shrink-0"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-5 max-h-[50vh] overflow-y-auto space-y-2">
              {holders.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-6">
                  Gerade niemand.
                </p>
              ) : (
                holders.map((h) => (
                  <div key={h.user_id} className="flex items-center gap-2.5 text-sm">
                    {h.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={h.avatar} alt="" className="h-7 w-7 rounded-full shrink-0" />
                    ) : (
                      <div className="h-7 w-7 rounded-full bg-slate-800 shrink-0" />
                    )}
                    <span className={cn("truncate", h.left ? "text-slate-500 italic" : "text-slate-300")}>
                      {h.name}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── What this does ───────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Link2 className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">Werbung im Status belohnen</p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Wer <code className="px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-300">.gg/dein-server</code>{" "}
              in seinen Discord-Status schreibt, bekommt automatisch eine Rolle.
              Nimmt er den Text wieder raus, ist die Rolle weg.
            </p>
          </div>
        </div>

        {data?.presence_intent === false && (
          <div className="rounded-xl bg-red-500/[0.07] border border-red-500/25 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-200/80 leading-relaxed">
              Der Presence-Intent ist aus. Ohne ihn sieht der Bot keine
              Status-Texte und hier passiert gar nichts. Im Discord Developer
              Portal unter „Bot → Privileged Gateway Intents“ einschalten.
            </p>
          </div>
        )}

        {setups.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat label="Auslöser" value={data.stats?.setups ?? 0} />
            <Stat label="Haben die Rolle" value={data.stats?.holders ?? 0} />
            <Stat label="Insgesamt vergeben" value={data.stats?.granted_total ?? 0} />
          </div>
        )}
      </div>

      {/* ── Add ──────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-center justify-between gap-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Neuer Auslöser
          </p>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
            title="Neu laden"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        </div>

        <div className="grid lg:grid-cols-2 gap-5">
          <Field
            label="Text im Status"
            hint={
              normalised
                ? `Gespeichert wird: .gg/${normalised} — Groß-/Kleinschreibung und Präfix sind egal.`
                : "z. B. .gg/dein-server, discord.gg/dein-server oder nur der Code."
            }
          >
            <input
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
              placeholder=".gg/dein-server"
              className={INPUT}
            />
          </Field>

          <Field label="Rolle" hint="Muss unter der Rolle des Bots stehen.">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
            />
          </Field>

          <Field label="Protokoll-Kanal" hint="Optional. Meldet jedes Vergeben und Entfernen.">
            <ChannelPicker
              guildId={guildId}
              value={logChannel}
              onChange={(id) => setLogChannel(id || "")}
              placeholder="Kein Protokoll"
              channelTypes={["0", "5"]}
            />
          </Field>

          <div className="flex items-end">
            <InlineToggle
              checked={enabled}
              onCheckedChange={setEnabled}
              label="Sofort aktiv"
              hint="Aus: erst anlegen, später scharf schalten."
            />
          </div>
        </div>

        <button
          onClick={add}
          disabled={busy || !normalised || !roleId}
          title={!normalised || !roleId ? "Auslöser eingeben und Rolle wählen" : undefined}
          className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Anlegen
        </button>
      </div>

      {/* ── Existing ─────────────────────────────────── */}
      {setups.length === 0 ? (
        <p className="text-sm text-slate-500 py-10 text-center border border-dashed border-slate-800 rounded-2xl">
          Noch kein Auslöser eingerichtet.
        </p>
      ) : (
        <div className="space-y-3">
          {setups.map((setup: any) => (
            <div
              key={setup.vanity}
              className={cn(
                "bg-[#10233f] border rounded-3xl p-5 space-y-4",
                setup.problem
                  ? "border-red-500/30"
                  : setup.enabled
                    ? "border-slate-800"
                    : "border-slate-800 opacity-60"
              )}
            >
              <div className="flex items-start gap-4 flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="font-black text-white flex items-center gap-2 flex-wrap">
                    <code className="px-2 py-1 rounded-lg bg-white/[0.06] text-sm">
                      {setup.display}
                    </code>
                    <span className="text-slate-600">→</span>
                    <span
                      style={
                        setup.role_colour
                          ? { color: `#${setup.role_colour.toString(16).padStart(6, "0")}` }
                          : undefined
                      }
                      className={cn(!setup.role_name && "text-red-400 italic")}
                    >
                      {setup.role_name ? `@${setup.role_name}` : "Rolle gelöscht"}
                    </span>
                    {!setup.enabled && (
                      <span className="px-2 py-0.5 rounded-md bg-slate-700/50 text-slate-400 text-[10px] font-black uppercase">
                        aus
                      </span>
                    )}
                  </p>
                  <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-500 flex-wrap">
                    <button
                      onClick={() => openHolders(setup.vanity)}
                      className="flex items-center gap-1 hover:text-primary transition-colors"
                    >
                      <Users className="h-3 w-3" />
                      {setup.holders} haben sie gerade
                    </button>
                    <span>{setup.granted_total}× vergeben</span>
                    <span>{setup.removed_total}× entfernt</span>
                    {setup.log_channel_name && <span>#{setup.log_channel_name}</span>}
                  </div>
                </div>

                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => {
                      setTestFor(testFor === setup.vanity ? null : setup.vanity);
                      setTestText(`spiele auf ${setup.display}`);
                      setTestResult(null);
                    }}
                    className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary transition-all"
                    title="Text ausprobieren"
                  >
                    <FlaskConical className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() =>
                      act(
                        () => api.syncVanityRole(guildId, setup.vanity),
                        "Alle Mitglieder jetzt prüfen? Bei großen Servern dauert das einen Moment."
                      )
                    }
                    disabled={busy || !!setup.problem}
                    className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
                    title="Jeden Status einmal durchgehen"
                  >
                    Abgleichen
                  </button>
                  <button
                    onClick={() =>
                      act(
                        () =>
                          api.saveVanityRole(guildId, {
                            vanity: setup.vanity,
                            role_id: setup.role_id,
                            log_channel_id: setup.log_channel_id,
                            enabled: !setup.enabled,
                          }),
                      )
                    }
                    disabled={busy}
                    className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-white disabled:opacity-40 transition-all"
                  >
                    {setup.enabled ? "Aus" : "An"}
                  </button>
                  <button
                    onClick={() =>
                      act(
                        () => api.deleteVanityRole(guildId, setup.vanity),
                        `„${setup.display}" entfernen? Bereits vergebene Rollen bleiben.`
                      )
                    }
                    disabled={busy}
                    className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 transition-all disabled:opacity-40"
                    title="Entfernen"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {setup.problem && (
                <div className="rounded-xl bg-red-500/[0.07] border border-red-500/25 p-3.5 flex gap-2.5">
                  <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                  <p className="text-[12px] text-red-200/80 leading-relaxed">
                    {setup.problem}
                  </p>
                </div>
              )}

              {testFor === setup.vanity && (
                <div className="rounded-2xl bg-[#0b1626] border border-slate-800/70 p-4 space-y-3">
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                    Würde dieser Status zählen?
                  </p>
                  <div className="flex gap-2 flex-wrap">
                    <input
                      value={testText}
                      onChange={(e) => { setTestText(e.target.value); setTestResult(null); }}
                      placeholder="Status-Text eingeben"
                      className={cn(INPUT, "flex-1 min-w-[200px]")}
                    />
                    <button
                      onClick={() => runTest(setup.vanity)}
                      className="px-5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/25 transition-all"
                    >
                      Prüfen
                    </button>
                  </div>
                  {testResult !== null && (
                    <p className={cn(
                      "text-sm font-bold flex items-center gap-2",
                      testResult ? "text-emerald-400" : "text-slate-400"
                    )}>
                      {testResult ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                      {testResult
                        ? "Zählt — diese Person bekäme die Rolle."
                        : "Zählt nicht — der Auslöser kommt so nicht vor."}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="rounded-2xl bg-white/[0.02] border border-white/5 p-4 flex gap-2.5">
        <Info className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Der Bot merkt eine Status-Änderung sofort. „Abgleichen“ ist nur nötig,
          wenn jemand den Text schon vor dem Anlegen im Status hatte — solange
          er ihn nicht ändert, sieht der Bot ihn sonst nicht. Rollen, die
          jemand von Hand bekommen hat, werden nie automatisch entfernt.
        </p>
      </div>
    </section>
  );
}
