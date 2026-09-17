"use client";

import React from "react";
import Link from "next/link";
import { Check, ExternalLink, LifeBuoy, Loader2, MessageSquare, ShieldCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: "Wartet auf deine Entscheidung", color: "text-amber-300 border-amber-400/20 bg-amber-400/10" },
  accepted: { label: "Support-Zugriff aktiv", color: "text-emerald-300 border-emerald-400/20 bg-emerald-400/10" },
  declined: { label: "Abgelehnt", color: "text-rose-300 border-rose-400/20 bg-rose-400/10" },
  closed: { label: "Geschlossen", color: "text-slate-400 border-slate-700 bg-slate-800/50" },
};

function zeit(value: number) {
  return value ? new Date(value * 1000).toLocaleString("de-DE") : "—";
}

export function GuildSupportPanel({ guildId }: { guildId: string }) {
  const [cases, setCases] = React.useState<any[]>([]);
  const [owner, setOwner] = React.useState<boolean | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState<Record<number, string>>({});

  const laden = React.useCallback(async () => {
    try {
      const data = await api.getGuildSupportCases(guildId);
      setCases(data.cases || []);
      setOwner(true);
    } catch (error: any) {
      if (error?.status === 403) setOwner(false);
      else toast.error(error?.message || "Support-Anfragen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  React.useEffect(() => { laden(); }, [laden]);

  const antworten = async (id: number, decision: "accepted" | "declined") => {
    setBusy(id);
    try {
      await api.respondGuildSupportCase(guildId, id, decision);
      toast.success(decision === "accepted" ? "Support-Zugriff wurde freigegeben." : "Anfrage wurde abgelehnt.");
      await laden();
    } catch (error: any) { toast.error(error?.message || "Aktion fehlgeschlagen."); }
    finally { setBusy(null); }
  };

  const senden = async (id: number) => {
    const text = (message[id] || "").trim();
    if (!text) return;
    setBusy(id);
    try {
      await api.addGuildSupportMessage(guildId, id, text);
      setMessage((old) => ({ ...old, [id]: "" }));
      await laden();
    } catch (error: any) { toast.error(error?.message || "Nachricht konnte nicht gesendet werden."); }
    finally { setBusy(null); }
  };

  const schliessen = async (id: number) => {
    setBusy(id);
    try {
      await api.closeGuildSupportCase(guildId, id);
      toast.success("Supportfall geschlossen. Der Dashboard-Zugriff wurde sofort entzogen.");
      await laden();
    } catch (error: any) { toast.error(error?.message || "Supportfall konnte nicht geschlossen werden."); }
    finally { setBusy(null); }
  };

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-slate-800 bg-[#111116] p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-indigo-500/10 text-indigo-300"><LifeBuoy className="h-5 w-5" /></span>
          <div>
            <h2 className="text-lg font-bold text-white">Hilfe bei Problemen</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              Prüfe zuerst Einstellungen, Bot-Rechte und die Statusseite. Wenn ein University-Supporter helfen möchte, erscheint seine Admin-Anfrage hier. Nur der tatsächliche Discord-Serverinhaber kann Zugriff erlauben.
            </p>
          </div>
        </div>
      </section>

      <div>
        <h2 className="text-lg font-bold text-white">Admin-Anfragen</h2>
        <p className="mt-1 text-sm text-slate-500">Eine Annahme gilt nur bis der Supportfall geschlossen wird.</p>
      </div>

      {loading && <div className="grid min-h-32 place-items-center"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /></div>}
      {!loading && owner === false && (
        <div className="rounded-2xl border border-slate-800 bg-[#111116] p-6 text-sm text-slate-400">
          Support-Anfragen und Freigaben sind ausschließlich für den tatsächlichen Serverinhaber sichtbar.
        </div>
      )}
      {!loading && owner && cases.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">Keine Admin-Anfrage für diesen Server.</div>
      )}

      {owner && cases.map((fall) => {
        const status = STATUS[fall.status] || STATUS.closed;
        return (
          <section key={fall.id} className="overflow-hidden rounded-2xl border border-slate-800 bg-[#111116]">
            <div className="flex flex-wrap items-start justify-between gap-4 p-5 sm:p-6">
              <div className="flex min-w-0 items-center gap-3">
                {fall.supporter_avatar ? <img src={fall.supporter_avatar} alt="" className="h-12 w-12 rounded-full object-cover ring-2 ring-white/10" /> : <span className="grid h-12 w-12 place-items-center rounded-full bg-indigo-500/10"><ShieldCheck className="h-5 w-5 text-indigo-300" /></span>}
                <div className="min-w-0">
                  <p className="truncate font-bold text-white">{fall.supporter_name || `Discord ${fall.supporter_id}`}</p>
                  <p className="text-xs font-semibold" style={{ color: fall.supporter_role_color }}>{fall.supporter_role}</p>
                  <p className="mt-0.5 text-[11px] text-slate-600">Angefragt {zeit(fall.created_at)}</p>
                </div>
              </div>
              <span className={`rounded-full border px-3 py-1 text-xs font-bold ${status.color}`}>{status.label}</span>
            </div>

            <div className="border-t border-slate-800 px-5 py-4 text-sm text-slate-300">
              <strong>{fall.supporter_name || "Dieser Supporter"}</strong> ({fall.supporter_role}) will dir bei einem Problem helfen.
            </div>

            {fall.status === "pending" && (
              <div className="flex flex-wrap gap-3 border-t border-slate-800 p-5">
                <button disabled={busy === fall.id} onClick={() => antworten(fall.id, "accepted")} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-slate-950 disabled:opacity-50"><Check className="h-4 w-4" />Annehmen</button>
                <button disabled={busy === fall.id} onClick={() => antworten(fall.id, "declined")} className="inline-flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-sm font-bold text-rose-300 disabled:opacity-50"><X className="h-4 w-4" />Ablehnen</button>
              </div>
            )}

            {fall.messages?.length > 0 && (
              <div className="space-y-3 border-t border-slate-800 p-5">
                {fall.messages.map((eintrag: any) => (
                  <div key={eintrag.id} className="rounded-xl border border-slate-800 bg-black/20 p-3">
                    <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold text-slate-300">{eintrag.actor_name || eintrag.actor_role} · {eintrag.actor_role}</span><span className="text-[10px] text-slate-600">{zeit(eintrag.created_at)}</span></div>
                    <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-slate-400">{eintrag.message}</p>
                  </div>
                ))}
              </div>
            )}

            {fall.status === "accepted" && (
              <div className="space-y-3 border-t border-slate-800 p-5">
                <div className="flex flex-wrap gap-3">
                  <Link href={`/dashboard/guild/${guildId}/admin-dashboard`} className="inline-flex items-center gap-2 rounded-xl border border-indigo-400/20 bg-indigo-400/10 px-4 py-2.5 text-sm font-semibold text-indigo-200"><ExternalLink className="h-4 w-4" />Server-Werkzeuge und Scan</Link>
                  <button onClick={() => schliessen(fall.id)} disabled={busy === fall.id} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-300 disabled:opacity-50">Fall schließen und Zugriff entziehen</button>
                </div>
                <div className="flex gap-2">
                  <input value={message[fall.id] || ""} onChange={(e) => setMessage((old) => ({ ...old, [fall.id]: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") senden(fall.id); }} placeholder="Notiz oder Rückfrage …" maxLength={2000} className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-[#09090c] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500/50" />
                  <button onClick={() => senden(fall.id)} disabled={busy === fall.id || !(message[fall.id] || "").trim()} className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-500 text-white disabled:opacity-40"><MessageSquare className="h-4 w-4" /></button>
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
