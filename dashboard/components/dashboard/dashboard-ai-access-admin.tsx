"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React, { useEffect, useState } from "react";
import { Bot, KeyRound, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

export function DashboardAiAccessAdmin() {
  useWebsiteLocale();
  const [users, setUsers] = useState<Array<{ user_id: string; granted_by: string; granted_at: number }>>([]);
  const [userId, setUserId] = useState("");
  const [keyReady, setKeyReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const data = await api.getDashboardAiUsers();
      setUsers(data.users || []);
      setKeyReady(Boolean(data.api_key_configured));
    } catch (error: any) {
      toast.error(error?.message || "KI-Freigaben konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const grant = async () => {
    const clean = userId.trim();
    if (!/^\d{15,20}$/.test(clean)) return toast.error("Gib eine gültige Discord-Nutzer-ID ein.");
    setBusy(true);
    try {
      await api.grantDashboardAiUser(clean);
      setUserId("");
      toast.success("KI-Tab wurde für den Nutzer freigeschaltet.");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Freigabe fehlgeschlagen.");
    } finally { setBusy(false); }
  };

  const revoke = async (id: string) => {
    setBusy(true);
    try {
      await api.revokeDashboardAiUser(id);
      toast.success("KI-Zugriff wurde entfernt.");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Entfernen fehlgeschlagen.");
    } finally { setBusy(false); }
  };

  return (
    <section className="mb-6 rounded-2xl border border-violet-400/20 bg-violet-500/[.045] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-base font-black text-white"><Bot className="h-5 w-5 text-violet-300" /> Dashboard-KI freischalten</p>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">Nur hier eingetragene Discord-IDs sehen auf ihren verwalteten Servern den KI-Tab. Änderungen brauchen immer eine ausdrückliche Bestätigung.</p>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10px] font-black uppercase ${keyReady ? "border-emerald-400/25 text-emerald-300" : "border-amber-400/25 text-amber-300"}`}>
          <KeyRound className="h-3 w-3" /> GROQ_TICKET_AI_KEY {keyReady ? "bereit" : "fehlt"}
        </span>
      </div>
      <div className="mt-4 flex gap-2">
        <input value={userId} onChange={(event) => setUserId(event.target.value.replace(/\D/g, ""))} placeholder="Discord-Nutzer-ID" className="h-11 min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-4 text-sm text-white outline-none focus:border-violet-400/40" />
        <button disabled={busy} onClick={grant} className="inline-flex h-11 items-center gap-2 rounded-xl bg-violet-500 px-4 text-sm font-bold text-white hover:bg-violet-400 disabled:opacity-50"><Plus className="h-4 w-4" /> Freischalten</button>
      </div>
      <div className="mt-4 space-y-2">
        {loading ? <Loader2 className="mx-auto h-5 w-5 animate-spin text-slate-500" /> : users.length ? users.map((user) => (
          <div key={user.user_id} className="flex items-center gap-3 rounded-xl border border-white/[.07] bg-black/15 px-4 py-3">
            <code className="min-w-0 flex-1 truncate text-sm text-slate-200">{user.user_id}</code>
            <span className="hidden text-xs text-slate-600 sm:block">seit {new Date(user.granted_at * 1000).toLocaleDateString(websiteLocale())}</span>
            <button disabled={busy} onClick={() => revoke(user.user_id)} className="rounded-lg p-2 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300" title="KI-Zugriff entfernen"><Trash2 className="h-4 w-4" /></button>
          </div>
        )) : <p className="py-3 text-center text-sm text-slate-600">Noch keine Nutzer freigeschaltet.</p>}
      </div>
    </section>
  );
}
