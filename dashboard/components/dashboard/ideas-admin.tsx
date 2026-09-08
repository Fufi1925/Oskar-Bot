"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Ban, CheckCircle2, Clock3, ExternalLink, Gift, Lightbulb,
  Loader2, MessageCircle, RefreshCw, Search, ShieldBan, Trash2,
  UserRound, XCircle,
} from "lucide-react";
import { api } from "@/lib/api";

const STATUS: Record<string, { label: string; style: string }> = {
  open: { label: "Offen", style: "border-blue-500/25 bg-blue-500/10 text-blue-300" },
  planned: { label: "Geplant", style: "border-violet-500/25 bg-violet-500/10 text-violet-300" },
  working: { label: "In Bearbeitung", style: "border-amber-500/25 bg-amber-500/10 text-amber-300" },
  implemented: { label: "Umgesetzt", style: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300" },
  rejected: { label: "Abgelehnt", style: "border-red-500/25 bg-red-500/10 text-red-300" },
  needs_info: { label: "Infos benötigt", style: "border-orange-500/25 bg-orange-500/10 text-orange-300" },
};
const CARD = "rounded-2xl border border-white/10 bg-[#111116]";

export function IdeasAdmin() {
  const [data, setData] = useState<any>({ ideas: [], counts: {}, blacklisted: [] });
  const [selected, setSelected] = useState<any>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [nextStatus, setNextStatus] = useState("open");
  const [reward, setReward] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set("status", filter);
      if (query.trim()) params.set("q", query.trim());
      const result = await api.ideasAdminOverview(params.toString());
      setData(result);
      if (selected) {
        const fresh = result.ideas?.find((idea: any) => idea.id === selected.id);
        if (fresh) setSelected((old: any) => ({ ...old, ...fresh }));
      }
    } catch (error: any) {
      setNotice(error?.message || "Ideen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [filter, query, selected?.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const open = async (idea: any) => {
    setSelected(idea);
    setNote(idea.admin_note || "");
    setNextStatus(idea.status || "open");
    setReward(Boolean(idea.reward_granted));
    try {
      const detail = await api.getIdea(idea.id);
      setSelected(detail.idea);
      setNote(detail.idea.admin_note || "");
      setNextStatus(detail.idea.status || "open");
      setReward(Boolean(detail.idea.reward_granted));
    } catch {/* list data remains usable */}
  };

  const save = async () => {
    if (!selected) return;
    setBusy(true); setNotice("");
    try {
      const result = await api.decideIdea(selected.id, {
        status: nextStatus, note, reward,
      });
      setSelected(result.idea);
      setNotice(reward
        ? "Status gespeichert, Belohnung angelegt und Discord-DM versendet."
        : "Status gespeichert und Discord-DM versendet.");
      await load();
    } catch (error: any) {
      setNotice(error?.message || "Änderung fehlgeschlagen.");
    } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!selected || !window.confirm("Diese Idee mit Stimmen und Kommentaren endgültig löschen?")) return;
    setBusy(true);
    try {
      await api.deleteIdea(selected.id);
      setSelected(null); setNotice("Idee endgültig gelöscht."); await load();
    } finally { setBusy(false); }
  };

  const block = async (enabled: boolean, userId = selected?.user_id) => {
    if (!userId) return;
    setBusy(true);
    try {
      await api.blacklistIdeaUser({
        target_user_id: userId, enabled,
        reason: enabled ? (note || "Vom Ideen-System ausgeschlossen") : "",
      });
      setNotice(enabled ? "Nutzer für neue Ideen, Votes und Kommentare gesperrt." : "Nutzersperre aufgehoben.");
      await load();
    } finally { setBusy(false); }
  };

  const count = (key: string) => Number(data.counts?.[key] || 0);
  const total = Object.values(data.counts || {}).reduce((sum: number, value: any) => sum + Number(value || 0), 0);
  const cards = [
    ["Gesamt", total, Lightbulb, "text-indigo-400"],
    ["Offen", count("open") + count("needs_info"), Clock3, "text-blue-400"],
    ["In Arbeit", count("planned") + count("working"), RefreshCw, "text-amber-400"],
    ["Umgesetzt", count("implemented"), CheckCircle2, "text-emerald-400"],
    ["Abgelehnt", count("rejected"), XCircle, "text-red-400"],
    ["Gesperrte Nutzer", data.blacklisted?.length || 0, Ban, "text-orange-400"],
  ] as const;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-black text-white">Community Ideen</h2>
          <p className="mt-1 text-sm text-slate-400">Ideen prüfen, beantworten, belohnen und moderieren.</p>
        </div>
        <a href="/ideas" target="_blank" className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-400">
          Öffentliche Seite <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {notice && <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-100">{notice}</div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {cards.map(([label, value, Icon, color]) => (
          <div key={label} className={`${CARD} p-4`}>
            <Icon className={`h-4 w-4 ${color}`} />
            <p className="mt-3 text-2xl font-black text-white">{value}</p>
            <p className="mt-1 text-xs text-slate-500">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_430px]">
        <section className={`${CARD} min-w-0 p-4 sm:p-5`}>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-500" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Titel, Text oder Ideen-ID suchen …" className="h-11 w-full rounded-xl border border-white/10 bg-black/20 pl-10 pr-4 text-sm text-white outline-none focus:border-indigo-500" />
            </div>
            <select value={filter} onChange={(e) => setFilter(e.target.value)} className="h-11 rounded-xl border border-white/10 bg-[#17171d] px-4 text-sm text-white outline-none">
              <option value="">Alle Status</option>
              {Object.entries(STATUS).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
            </select>
          </div>

          {loading ? (
            <div className="grid min-h-72 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-indigo-400" /></div>
          ) : data.ideas?.length ? (
            <div className="mt-4 space-y-2">
              {data.ideas.map((idea: any) => {
                const state = STATUS[idea.status] || STATUS.open;
                return (
                  <button key={idea.id} onClick={() => void open(idea)} className={`w-full rounded-xl border p-4 text-left transition ${selected?.id === idea.id ? "border-indigo-500/50 bg-indigo-500/10" : "border-white/5 bg-black/20 hover:border-white/15"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${state.style}`}>{state.label}</span>
                          {idea.reward_granted ? <span className="text-[10px] font-bold text-emerald-400">BELOHNT</span> : null}
                          <span className="text-[10px] text-slate-600">{idea.id}</span>
                        </div>
                        <h3 className="mt-2 truncate font-bold text-white">{idea.title}</h3>
                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{idea.description}</p>
                      </div>
                      <span className="shrink-0 text-xs text-slate-500">{idea.user_name}</span>
                    </div>
                    <div className="mt-3 flex gap-4 text-[11px] text-slate-600">
                      <span>▲ {idea.upvotes || 0}</span><span>▼ {idea.downvotes || 0}</span>
                      <span><MessageCircle className="mr-1 inline h-3 w-3" />{idea.comment_count || 0}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : <p className="py-24 text-center text-sm text-slate-500">Keine passenden Ideen.</p>}
        </section>

        <aside className={`${CARD} h-fit p-5 xl:sticky xl:top-5`}>
          {!selected ? (
            <div className="py-20 text-center text-slate-500">
              <Lightbulb className="mx-auto h-9 w-9 opacity-40" />
              <p className="mt-3 text-sm">Wähle links eine Idee aus.</p>
            </div>
          ) : (
            <div className="space-y-5">
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div><p className="text-xs text-slate-500">{selected.id}</p><h3 className="mt-1 text-xl font-black text-white">{selected.title}</h3></div>
                  <a href={`/ideas/${selected.id}`} target="_blank" className="rounded-lg border border-white/10 p-2 text-slate-400"><ExternalLink className="h-4 w-4" /></a>
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs text-slate-400"><UserRound className="h-4 w-4" />{selected.user_name} · {selected.user_id}</div>
              </div>

              <p className="max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl bg-black/20 p-4 text-sm leading-6 text-slate-300">{selected.description}</p>
              {selected.images?.length ? <div className="grid grid-cols-3 gap-2">{selected.images.map((image: string) => <img key={image} src={image} alt="Referenz" className="h-20 w-full rounded-lg object-cover" />)}</div> : null}

              <label className="block text-xs font-bold text-slate-400">Status
                <select value={nextStatus} onChange={(e) => setNextStatus(e.target.value)} className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-[#17171d] px-3 text-sm text-white">
                  {Object.entries(STATUS).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
                </select>
              </label>
              <label className="block text-xs font-bold text-slate-400">Öffentliche Admin-Notiz
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} placeholder="Begründung, Rückfrage oder Versionshinweis …" className="mt-2 w-full resize-none rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white outline-none focus:border-indigo-500" />
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
                <input type="checkbox" checked={reward} onChange={(e) => setReward(e.target.checked)} className="mt-1" />
                <span><b className="block text-sm text-emerald-300">3 Tage Premium vergeben</b><span className="text-xs leading-5 text-slate-500">Erstellt eine einmalige Belohnung und sendet den Einlöse-Link per DM.</span></span>
              </label>
              <button disabled={busy} onClick={save} className="min-h-11 w-full rounded-xl bg-indigo-600 text-sm font-bold text-white disabled:opacity-50">
                {busy ? "Wird gespeichert …" : "Entscheidung speichern & DM senden"}
              </button>
              <div className="grid grid-cols-2 gap-2 border-t border-white/10 pt-4">
                <button disabled={busy} onClick={() => block(true)} className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs font-bold text-amber-300"><ShieldBan className="mr-1 inline h-3.5 w-3.5" />Nutzer sperren</button>
                <button disabled={busy} onClick={() => block(false)} className="rounded-xl border border-white/10 px-3 py-2 text-xs font-bold text-slate-300">Entsperren</button>
                <button disabled={busy} onClick={remove} className="col-span-2 rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs font-bold text-red-300"><Trash2 className="mr-1 inline h-3.5 w-3.5" />Idee endgültig löschen</button>
              </div>
            </div>
          )}
        </aside>
      </div>

      {data.blacklisted?.length > 0 && (
        <section className={`${CARD} p-5`}>
          <h3 className="font-bold text-white">Ideen-Blacklist</h3>
          <p className="mt-1 text-xs text-slate-500">Diese Nutzer können weder einreichen noch abstimmen oder kommentieren.</p>
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {data.blacklisted.map((entry: any) => (
              <div key={entry.user_id} className="flex items-center justify-between gap-3 rounded-xl border border-white/5 bg-black/20 p-3">
                <div className="min-w-0"><p className="truncate text-sm font-bold text-white">{entry.user_id}</p><p className="truncate text-xs text-slate-500">{entry.reason || "Keine Begründung"}</p></div>
                <button onClick={() => block(false, entry.user_id)} className="shrink-0 text-xs font-bold text-indigo-400">Entsperren</button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
