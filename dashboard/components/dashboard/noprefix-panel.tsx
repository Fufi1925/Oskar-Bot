"use client";

/**
 * No-prefix: who may run commands without typing the prefix.
 *
 * The page this replaces showed a global list on every server's
 * dashboard, and pressing Save wiped the entries other servers had made.
 * That is fixed in the API; here the important part is being honest
 * about it: entries carried over from before are marked "gilt überall",
 * because they really do, and removing one takes a deliberate second
 * step.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Clock, Globe, Info, Loader2, Plus, RefreshCw, Search,
  Shield, Terminal, Trash2, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RolePicker } from "@/components/dashboard/pickers";
import { UserPicker } from "@/components/dashboard/user-picker";

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

const DURATIONS = [
  { label: "Dauerhaft", days: 0 },
  { label: "7 Tage", days: 7 },
  { label: "30 Tage", days: 30 },
  { label: "90 Tage", days: 90 },
];

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

function when(unix?: number | null) {
  if (!unix) return null;
  return new Date(unix * 1000).toLocaleDateString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

export function NoPrefixPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");

  const [userId, setUserId] = useState("");
  const [days, setDays] = useState(0);
  const [roleId, setRoleId] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.getNoPrefix(guildId));
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

  const users = useMemo(() => {
    const list = data?.users || [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (u: any) => u.name.toLowerCase().includes(q) || u.user_id.includes(q)
    );
  }, [data, query]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {/* ── What this does ───────────────────────────── */}
      <div className="relative bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4">
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Terminal className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">Befehle ohne Prefix</p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Wer hier steht, kann <code className="px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-300">ban @user</code>{" "}
              schreiben statt <code className="px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-300">!ban @user</code>.
            </p>
          </div>
        </div>

        <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
          <Shield className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-amber-200/80 leading-relaxed">
            Gib das nur Leuten, denen du wirklich vertraust. Ohne Prefix wird
            jede beiläufige Nachricht zum möglichen Befehl — ein &bdquo;ban&ldquo; im
            Gespräch reicht.
          </p>
        </div>

        {data?.has_global && (
          <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5 flex gap-2.5">
            <Globe className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Einträge mit &bdquo;gilt überall&ldquo; stammen aus der Zeit, als die Liste
              noch für alle Server gemeinsam war. Sie wirken weiterhin auf
              jedem Server — deshalb wurden sie beim Umstellen nicht einfach
              gelöscht. Entfernen geht über den Globus-Knopf.
            </p>
          </div>
        )}
      </div>

      {/* ── Add a member ─────────────────────────────── */}
      <div className="relative bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Mitglied hinzufügen
          </p>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        </div>

        <div className="grid lg:grid-cols-[1fr_auto_auto] gap-3 items-end">
          <Field label="Mitglied">
            <UserPicker
              guildId={guildId}
              value={userId}
              onChange={(id: string) => setUserId(id || "")}
              placeholder="Mitglied suchen"
            />
          </Field>

          <Field label="Wie lange">
            <div className="flex gap-1.5 flex-wrap">
              {DURATIONS.map((d) => (
                <button
                  key={d.days}
                  onClick={() => setDays(d.days)}
                  className={cn(
                    "px-3 h-[46px] rounded-xl text-xs font-bold border transition-all",
                    days === d.days
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-[#0e0e12] border-slate-800 text-slate-400 hover:text-slate-200"
                  )}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </Field>

          <button
            onClick={() =>
              act(async () => {
                const res = await api.addNoPrefixUser(guildId, {
                  user_id: userId,
                  days: days || undefined,
                });
                setUserId("");
                return res;
              })
            }
            disabled={busy || !userId}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Hinzufügen
          </button>
        </div>
      </div>

      {/* ── Members ──────────────────────────────────── */}
      <div className="relative bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex-1">
            Mitglieder ({data?.users?.length || 0})
          </p>
          {(data?.users?.length || 0) > 5 && (
            <div className="relative min-w-[180px]">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Suchen"
                className={cn(INPUT, "pl-10 py-2")}
              />
            </div>
          )}
        </div>

        {users.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
            {query ? "Niemand gefunden." : "Noch niemand eingetragen."}
          </p>
        ) : (
          <div className="space-y-2">
            {users.map((user: any) => (
              <div
                key={user.user_id}
                className={cn(
                  "flex items-center gap-3 rounded-2xl border px-4 py-3 flex-wrap",
                  user.expired
                    ? "bg-[#0e0e12] border-amber-500/25 opacity-70"
                    : "bg-[#0e0e12] border-slate-800"
                )}
              >
                {user.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar} alt="" className="h-8 w-8 rounded-full shrink-0" />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
                )}

                <div className="min-w-0 flex-1">
                  <p className={cn(
                    "text-sm font-bold truncate flex items-center gap-2 flex-wrap",
                    user.left ? "text-slate-500 italic" : "text-white"
                  )}>
                    {user.name}
                    {user.global && (
                      <span className="px-2 py-0.5 rounded-md bg-slate-700/50 text-slate-400 text-[10px] font-black uppercase flex items-center gap-1">
                        <Globe className="h-2.5 w-2.5" /> gilt überall
                      </span>
                    )}
                    {user.expired && (
                      <span className="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 text-[10px] font-black uppercase">
                        abgelaufen
                      </span>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {user.expires_at
                      ? `läuft ab am ${when(user.expires_at)}`
                      : "dauerhaft"}
                    {user.left && " · nicht mehr auf dem Server"}
                  </p>
                </div>

                <button
                  onClick={() =>
                    act(
                      () =>
                        api.removeNoPrefixUser(
                          guildId, user.user_id, user.global ? "global" : "guild"
                        ),
                      user.global
                        ? `„${user.name}" gilt auf ALLEN Servern. Wirklich überall entfernen?`
                        : undefined
                    )
                  }
                  disabled={busy}
                  className={cn(
                    "p-2.5 rounded-xl transition-all disabled:opacity-40 shrink-0",
                    user.global
                      ? "bg-white/[0.03] border border-white/10 text-slate-400 hover:text-amber-400"
                      : "text-slate-500 hover:text-red-400"
                  )}
                  title={user.global ? "Überall entfernen" : "Entfernen"}
                >
                  {user.global ? <Globe className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Roles ────────────────────────────────────── */}
      <div className="relative bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Ganze Rollen ({data?.roles?.length || 0})
          </p>
          <p className="text-[11px] text-slate-600 mt-1.5">
            Jeder mit dieser Rolle braucht keinen Prefix. Gilt nur auf diesem
            Server.
          </p>
        </div>

        <div className="grid md:grid-cols-[1fr_auto] gap-3 items-end">
          <Field label="Rolle">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
            />
          </Field>
          <button
            onClick={() =>
              act(async () => {
                const res = await api.addNoPrefixRole(guildId, roleId);
                setRoleId("");
                return res;
              })
            }
            disabled={busy || !roleId}
            className="h-[46px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Hinzufügen
          </button>
        </div>

        {!data?.roles?.length ? (
          <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
            Keine Rolle eingetragen.
          </p>
        ) : (
          <div className="space-y-2">
            {data.roles.map((role: any) => (
              <div
                key={role.role_id}
                className="flex items-center gap-3 bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3"
              >
                <span
                  className={cn(
                    "text-sm font-bold flex-1 min-w-0 truncate",
                    role.missing ? "text-red-400 italic" : "text-white"
                  )}
                  style={
                    !role.missing && role.colour
                      ? { color: `#${role.colour.toString(16).padStart(6, "0")}` }
                      : undefined
                  }
                >
                  {role.missing ? "Rolle wurde gelöscht" : `@${role.name}`}
                </span>
                {!role.missing && (
                  <span className="text-[11px] text-slate-500 flex items-center gap-1 shrink-0">
                    <Users className="h-3 w-3" />
                    {role.members}
                  </span>
                )}
                <button
                  onClick={() => act(() => api.removeNoPrefixRole(guildId, role.role_id))}
                  disabled={busy}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 transition-all disabled:opacity-40 shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
