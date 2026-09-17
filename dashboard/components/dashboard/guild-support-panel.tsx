"use client";

import React from "react";
import { AlertTriangle, Check, CheckCircle2, LifeBuoy, Loader2, ShieldCheck, Star, X } from "lucide-react";
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
  const [decision, setDecision] = React.useState<{ id: number; type: "accepted" | "declined" } | null>(null);
  const [acceptedName, setAcceptedName] = React.useState("");
  const [closeId, setCloseId] = React.useState<number | null>(null);
  const [rating, setRating] = React.useState(0);
  const [ratingNote, setRatingNote] = React.useState("");

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

  const antworten = async () => {
    if (!decision) return;
    const target = cases.find((fall) => fall.id === decision.id);
    setBusy(decision.id);
    try {
      await api.respondGuildSupportCase(guildId, decision.id, decision.type);
      if (decision.type === "accepted") setAcceptedName(target?.supporter_name || "Ein Admin");
      else toast.success("Die Support-Anfrage wurde abgelehnt.");
      setDecision(null);
      await laden();
    } catch (error: any) { toast.error(error?.message || "Aktion fehlgeschlagen."); }
    finally { setBusy(null); }
  };

  const schliessen = async () => {
    if (!closeId || rating < 1) return;
    setBusy(closeId);
    try {
      await api.closeGuildSupportCase(guildId, closeId, rating, ratingNote);
      toast.success("Supportfall geschlossen. Der Dashboard-Zugriff wurde sofort entzogen.");
      setCloseId(null); setRating(0); setRatingNote("");
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
                <button disabled={busy === fall.id} onClick={() => setDecision({ id: fall.id, type: "accepted" })} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-slate-950 disabled:opacity-50"><Check className="h-4 w-4" />Annehmen</button>
                <button disabled={busy === fall.id} onClick={() => setDecision({ id: fall.id, type: "declined" })} className="inline-flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-sm font-bold text-rose-300 disabled:opacity-50"><X className="h-4 w-4" />Ablehnen</button>
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
              <div className="border-t border-slate-800 p-5">
                <button onClick={() => { setCloseId(fall.id); setRating(0); setRatingNote(""); }} disabled={busy === fall.id} className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-2.5 text-sm font-bold text-rose-200 disabled:opacity-50">Supportfall schließen</button>
              </div>
            )}
            {fall.status === "closed" && fall.rating > 0 && (
              <div className="flex items-center gap-2 border-t border-slate-800 px-5 py-4 text-sm text-amber-300"><Star className="h-4 w-4 fill-amber-300" />Bewertung: {fall.rating}/10</div>
            )}
          </section>
        );
      })}

      {decision && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10050] grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl border border-slate-700 bg-[#131318] p-6 shadow-2xl">
            <span className={`grid h-12 w-12 place-items-center rounded-2xl ${decision.type === "declined" ? "bg-amber-500/10" : "bg-emerald-500/10"}`}>
              {decision.type === "declined" ? <AlertTriangle className="h-6 w-6 text-amber-300" /> : <ShieldCheck className="h-6 w-6 text-emerald-300" />}
            </span>
            <h3 className="mt-4 text-xl font-black text-white">{decision.type === "declined" ? "Support-Anfrage ablehnen?" : "Support-Hilfe annehmen?"}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {decision.type === "declined"
                ? "Bist du sicher? Es kann sich um ein ernstes Problem handeln. Bei einer Ablehnung erhält der Admin keinen Zugriff auf dein Server-Dashboard."
                : "Der Supporter erhält bis zum Schließen dieses Falls Zugriff auf dein Server-Dashboard und darf dort Fehler prüfen und Server-Scans ausführen."}
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button onClick={() => setDecision(null)} className="rounded-xl border border-slate-700 py-3 text-sm font-bold text-slate-300">Abbrechen</button>
              <button onClick={antworten} disabled={busy === decision.id} className={`rounded-xl py-3 text-sm font-black disabled:opacity-50 ${decision.type === "declined" ? "bg-rose-500 text-white" : "bg-emerald-500 text-slate-950"}`}>{decision.type === "declined" ? "Trotzdem ablehnen" : "Hilfe annehmen"}</button>
            </div>
          </div>
        </div>
      )}

      {acceptedName && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10060] grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl border border-emerald-400/25 bg-[#131318] p-6 text-center shadow-2xl">
            <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-500/10"><CheckCircle2 className="h-7 w-7 text-emerald-300" /></span>
            <h3 className="mt-4 text-xl font-black text-white">Du hast die Hilfe angenommen</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400"><strong className="text-white">{acceptedName}</strong> wird sich nun um dein Problem kümmern. Der Admin kann deinen Server scannen, nach Dashboard- und Discord-Problemen suchen und bis zum Schließen auf das Server-Dashboard zugreifen.</p>
            <button onClick={() => setAcceptedName("")} className="mt-6 w-full rounded-xl bg-emerald-500 py-3 text-sm font-black text-slate-950">Verstanden</button>
          </div>
        </div>
      )}

      {closeId !== null && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-[10050] grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-3xl border border-slate-700 bg-[#131318] p-6 shadow-2xl">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-500/10"><Star className="h-6 w-6 text-amber-300" /></span>
            <h3 className="mt-4 text-xl font-black text-white">Diesen Supportfall schließen?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">Der Admin-Zugriff wird sofort entzogen. Bitte bewerte unseren Admin von 1 bis 10 Sternen.</p>
            <div className="mt-5 grid grid-cols-5 gap-2 sm:grid-cols-10">
              {Array.from({ length: 10 }, (_, index) => index + 1).map((stern) => (
                <button key={stern} onClick={() => setRating(stern)} aria-label={`${stern} von 10 Sternen`} className={`grid aspect-square place-items-center rounded-xl border text-sm font-black transition ${stern <= rating ? "border-amber-400/40 bg-amber-400/15 text-amber-300" : "border-slate-700 text-slate-500 hover:border-slate-500"}`}>{stern}</button>
              ))}
            </div>
            <p className="mt-2 text-center text-xs font-bold text-amber-300">{rating ? `${rating}/10 Sterne` : "Bitte Bewertung auswählen"}</p>
            <textarea value={ratingNote} onChange={(e) => setRatingNote(e.target.value)} maxLength={1000} rows={3} placeholder="Optional: Was war gut oder was können wir verbessern?" className="mt-4 w-full resize-none rounded-xl border border-slate-800 bg-[#09090c] px-4 py-3 text-sm text-white outline-none focus:border-amber-500/40" />
            <div className="mt-5 grid grid-cols-2 gap-3">
              <button onClick={() => { setCloseId(null); setRating(0); setRatingNote(""); }} className="rounded-xl border border-slate-700 py-3 text-sm font-bold text-slate-300">Abbrechen</button>
              <button onClick={schliessen} disabled={!rating || busy === closeId} className="rounded-xl bg-rose-500 py-3 text-sm font-black text-white disabled:opacity-40">Bewerten und schließen</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
