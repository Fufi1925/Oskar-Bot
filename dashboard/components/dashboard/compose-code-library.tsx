"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Copy, Eye, KeyRound, Loader2, RefreshCw, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useWebsiteLocale } from "@/lib/i18n/locale";
import { DiscordEmojiText } from "./discord-emoji";
import { ComposeMessagePreview } from "./compose-message-preview";

type SavedCode = { code: string; title: string; excerpt: string; kind: string; created_at: number };

function CodePreview({ guildId, code, close }: { guildId: string; code: string; close: () => void }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [payload, setPayload] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    let cancelled = false;
    api.previewComposeCode(guildId, code)
      .then(result => { if (!cancelled) setPayload(result.payload); })
      .catch(error => { if (!cancelled) setError(error.message || t("Vorschau konnte nicht geladen werden.", "Could not load the preview.")); });
    return () => { cancelled = true; };
  }, [guildId, code]);
  return <dialog ref={dialog} data-no-translate aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); close(); }}
    onClick={event => { const box = event.currentTarget.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close(); }}
    className="w-[calc(100%_-_2rem)] max-w-3xl max-h-[90vh] overflow-y-auto rounded-3xl border border-blue-400/25 cloudtix-workspace-card bg-[#131318] p-4 text-white shadow-2xl backdrop:bg-black/80 backdrop:backdrop-blur-sm sm:p-6">
    <div className="mb-4 flex items-center justify-between gap-3"><h3 id={titleId} className="font-bold">{t("Nachrichtenvorschau", "Message preview")} · <span className="font-mono">{code}</span></h3><button type="button" onClick={close} aria-label={t("Schließen", "Close")} className="rounded-lg p-2 text-slate-400 hover:bg-white/5"><X className="h-5 w-5" /></button></div>
    {error ? <p role="alert" className="py-8 text-center text-red-300">{error}</p> : payload ? <ComposeMessagePreview payload={payload} /> : <div role="status" className="grid min-h-40 place-items-center"><Loader2 aria-label={t("Laden", "Loading")} className="h-6 w-6 animate-spin text-blue-300" /></div>}
    <p className="mt-4 text-xs text-slate-500">{t("Die Vorschau verändert deinen Entwurf nicht und sendet keine Nachricht.", "Previewing keeps your draft intact and does not send a message.")}</p>
  </dialog>;
}

export function ComposeCodeLibrary({ guildId, revision, busy, onImport }: { guildId: string; revision: number; busy: boolean; onImport: (code: string) => Promise<void> }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const [codes, setCodes] = useState<SavedCode[]>([]);
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const requestId = useRef(0);
  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true); setError(""); setSelected(null); setCodes([]); setTotal(0); setNextOffset(null);
    api.listComposeCodes(guildId).then(result => {
      if (id !== requestId.current) return;
      setCodes(result.codes); setTotal(result.total); setNextOffset(result.next_offset);
    }).catch(error => { if (id === requestId.current) setError(error.message || t("Codes konnten nicht geladen werden.", "Could not load the codes.")); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { requestId.current++; };
  }, [guildId, revision, refresh]);
  const more = async () => {
    if (nextOffset === null || loading) return;
    const id = requestId.current;
    setLoading(true); setError("");
    try {
      const result = await api.listComposeCodes(guildId, nextOffset);
      if (id !== requestId.current) return;
      setCodes(previous => [...previous, ...result.codes.filter((item: SavedCode) => !previous.some(old => old.code === item.code))]);
      setTotal(result.total); setNextOffset(result.next_offset);
    } catch (error: any) { if (id === requestId.current) setError(error.message || t("Codes konnten nicht geladen werden.", "Could not load the codes.")); }
    finally { if (id === requestId.current) setLoading(false); }
  };
  const copy = async (code: string) => {
    try { await navigator.clipboard.writeText(code); toast.success(t("Code kopiert.", "Code copied.")); }
    catch { toast.error(t("Code konnte nicht kopiert werden. Markiere und kopiere ihn manuell.", "Could not copy the code. Select and copy it manually.")); }
  };
  return <section data-no-translate className="rounded-2xl border border-blue-400/15 cloudtix-workspace-card bg-[#131318] p-4 sm:p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-bold text-white"><KeyRound className="h-4 w-4 text-blue-300" />{t("Codes dieses Servers", "This server's codes")} <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{total}</span></h3><p className="mt-2 text-xs leading-5 text-slate-500">{t("Alle gespeicherten Nachrichtencodes dieses Servers. Beliebig oft verwenden, kopieren oder zuerst ansehen.", "All saved message codes created by this server. Reuse them, copy them or preview them first.")}</p></div><button type="button" disabled={loading} onClick={() => setRefresh(value => value + 1)} aria-label={t("Codes aktualisieren", "Refresh codes")} className="rounded-lg p-2 text-slate-400 hover:bg-white/5 disabled:opacity-40"><RefreshCw className="h-4 w-4" /></button></div>
    {error && <div role="alert" className="mt-4 rounded-xl border border-red-400/20 p-3 text-xs text-red-300">{error}<button type="button" disabled={loading} onClick={() => setRefresh(value => value + 1)} className="ml-3 font-bold underline">{t("Erneut versuchen", "Try again")}</button></div>}
    {!loading && !error && !codes.length && <p className="mt-4 rounded-xl border border-dashed border-slate-800 p-5 text-center text-xs leading-5 text-slate-500">{t("Noch keine Codes. Gestalte eine Nachricht und wähle „Als Code speichern“.", "No codes yet. Design a message and choose “Save as code”.")}</p>}
    <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto">{codes.map(item => <article key={item.code} className="rounded-xl border border-slate-800 cloudtix-workspace-field bg-[#0e0e12] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="select-all font-mono text-base font-bold tracking-widest text-blue-200">{item.code}</span><span className="text-[10px] text-slate-500">{item.kind === "v2" ? "Components V2" : item.kind === "embed" ? "Embed" : t("Text", "Text")} · {new Date(item.created_at * 1000).toLocaleDateString(locale)}</span></div>
      <p className="mt-2 line-clamp-2 break-words text-sm font-semibold text-white [overflow-wrap:anywhere]"><DiscordEmojiText text={item.title || t("Gespeicherte Nachricht", "Saved message")} /></p>
      <p className="mt-1 line-clamp-2 break-words text-xs leading-5 text-slate-500 [overflow-wrap:anywhere]"><DiscordEmojiText text={item.excerpt} /></p>
      <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => setSelected(item.code)} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-400/10 px-3 py-2 text-xs font-bold text-blue-200"><Eye className="h-3.5 w-3.5" />{t("Vorschau", "Preview")}</button><button type="button" onClick={() => void copy(item.code)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 px-3 py-2 text-xs text-slate-400"><Copy className="h-3.5 w-3.5" />{t("Kopieren", "Copy")}</button><button type="button" disabled={busy} onClick={() => void onImport(item.code)} className="rounded-lg border border-slate-800 px-3 py-2 text-xs text-slate-400 disabled:opacity-40">{t("Im Editor öffnen", "Open in editor")}</button></div>
    </article>)}</div>
    {loading && <div role="status" className="mt-4 flex justify-center"><Loader2 aria-label={t("Laden", "Loading")} className="h-5 w-5 animate-spin text-blue-300" /></div>}
    {nextOffset !== null && <button type="button" disabled={loading} onClick={() => void more()} className="mt-4 w-full rounded-xl border border-slate-800 py-2.5 text-xs font-bold text-slate-400 disabled:opacity-40">{t("Weitere Codes laden", "Load more codes")} ({codes.length} / {total})</button>}
    {selected && <CodePreview key={`${guildId}:${selected}`} guildId={guildId} code={selected} close={() => setSelected(null)} />}
  </section>;
}
