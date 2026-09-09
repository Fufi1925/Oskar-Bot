"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BrainCircuit, FileText, Loader2, Save, ShieldCheck, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type AiCategory = {
  category_id: number;
  name: string;
  enabled: boolean;
  instructions: string;
};

type AiSettings = {
  api_key_configured: boolean;
  enabled: boolean;
  fallback_text: string;
  knowledge: null | { filename: string; characters: number; updated_at: number };
  categories: AiCategory[];
};

export function TicketAiPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<AiSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Zeitüberschreitung beim Laden der KI-Einstellungen.")), 12000);
      });
      const result = await Promise.race([api.getTicketAi(guildId), timeout]);
      setData(result);
      setUnavailable(false);
    } catch (error: any) {
      setData(null);
      if (error?.status === 404) setUnavailable(true);
      else setLoadError(error?.message || "KI-Einstellungen konnten nicht geladen werden.");
    } finally {
      if (timer) clearTimeout(timer);
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { load(); }, [load]);
  // Until the API confirms access, render nothing: non-enabled servers must
  // not see even a short flash of the private feature.
  if (unavailable || (loading && !data && !loadError)) return null;

  const upload = async (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".txt")) {
      toast.error("Bitte wähle eine .txt-Datei aus.");
      return;
    }
    if (file.size > 100_000) {
      toast.error("Die Datei darf höchstens 100 KB groß sein.");
      return;
    }
    setBusy(true);
    try {
      const content = await file.text();
      if (!content.trim()) throw new Error("Die Datei ist leer.");
      await api.uploadTicketAiKnowledge(guildId, file.name, content);
      toast.success("Wissensdatenbank hochgeladen.");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Upload fehlgeschlagen.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const save = async () => {
    if (!data) return;
    setBusy(true);
    try {
      await api.saveTicketAi(guildId, {
        enabled: data.enabled,
        fallback_text: data.fallback_text,
        categories: data.categories,
      });
      toast.success("KI-Ticketassistent gespeichert.");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const removeKnowledge = async () => {
    if (!confirm("Wissensdatenbank löschen und den KI-Assistenten ausschalten?")) return;
    setBusy(true);
    try {
      await api.deleteTicketAiKnowledge(guildId);
      toast.success("Wissensdatenbank gelöscht.");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-3xl border border-violet-500/25 bg-[#131318]">
      <div className="border-b border-violet-500/15 bg-violet-500/[0.06] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-violet-500/15 text-violet-300"><BrainCircuit className="h-5 w-5" /></span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-black text-white">KI-Ticketassistent</h3>
                <span className="rounded-md bg-amber-400/15 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-amber-300">Privater Premium-Test</span>
              </div>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">Antwortet nur dem Ticket-Ersteller, nur aus deiner Wissensdatei und nur bis ein Teammitglied das Ticket claimt.</p>
            </div>
          </div>
          {data && (
            <button
              type="button"
              disabled={busy || !data.knowledge || !data.api_key_configured}
              onClick={() => setData({ ...data, enabled: !data.enabled })}
              className={cn("relative h-7 w-12 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40", data.enabled ? "bg-violet-500" : "bg-slate-700")}
              aria-label="KI-Ticketassistent ein- oder ausschalten"
            ><span className={cn("absolute left-0 top-1 h-5 w-5 rounded-full bg-white transition-transform", data.enabled ? "translate-x-6" : "translate-x-1")} /></button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid min-h-48 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : loadError ? (
        <div className="p-5 sm:p-6">
          <div className="rounded-2xl border border-red-500/25 bg-red-500/[0.06] p-5 text-center">
            <p className="text-sm font-bold text-red-200">KI-System konnte nicht geladen werden</p>
            <p className="mt-1 text-xs text-slate-400">{loadError}</p>
            <button type="button" onClick={load} className="mt-4 rounded-xl border border-red-400/25 px-4 py-2 text-xs font-bold text-red-200 hover:bg-red-500/10">Erneut versuchen</button>
          </div>
        </div>
      ) : data ? (
        <div className="space-y-6 p-5 sm:p-6">
          {!data.api_key_configured && (
            <div className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-4 text-sm text-amber-200">Railway-Variable <b>GOOGLE_API_TICKET_KEY</b> fehlt. Nach dem Eintragen den Bot-Dienst neu starten.</div>
          )}

          <div className="rounded-2xl border border-slate-800 bg-[#0e0e12] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-violet-300" />
                <div>
                  <p className="text-sm font-bold text-white">Wissensdatenbank</p>
                  <p className="text-[11px] text-slate-500">Eine UTF-8-.txt-Datei, maximal 100 KB. Beim nächsten Upload wird sie ersetzt.</p>
                </div>
              </div>
              <div className="flex gap-2">
                {data.knowledge && <button disabled={busy} onClick={removeKnowledge} className="rounded-xl border border-red-500/20 p-2.5 text-red-300 hover:bg-red-500/10"><Trash2 className="h-4 w-4" /></button>}
                <button disabled={busy} onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-xs font-black text-white hover:bg-violet-400 disabled:opacity-50"><Upload className="h-4 w-4" /> TXT hochladen</button>
                <input ref={fileRef} type="file" accept=".txt,text/plain" className="hidden" onChange={(event) => upload(event.target.files?.[0])} />
              </div>
            </div>
            {data.knowledge && <div className="mt-3 rounded-xl bg-violet-500/[0.07] px-3 py-2 text-xs text-violet-200"><b>{data.knowledge.filename}</b> · {data.knowledge.characters.toLocaleString("de-DE")} Zeichen</div>}
          </div>

          <div>
            <div className="mb-3">
              <p className="text-sm font-bold text-white">Ticket-Kategorien</p>
              <p className="mt-0.5 text-[11px] text-slate-500">Aktiviere die KI gezielt und sage ihr, welche Antworten in dieser Kategorie erlaubt sind.</p>
            </div>
            <div className="space-y-3">
              {data.categories.length ? data.categories.map((category, index) => (
                <div key={category.category_id} className="rounded-2xl border border-slate-800 bg-[#0e0e12] p-4">
                  <label className="flex cursor-pointer items-center justify-between gap-3">
                    <span className="font-bold text-white">{category.name}</span>
                    <input type="checkbox" checked={category.enabled} onChange={(event) => {
                      const categories = [...data.categories];
                      categories[index] = { ...category, enabled: event.target.checked };
                      setData({ ...data, categories });
                    }} className="h-4 w-4 accent-violet-500" />
                  </label>
                  <textarea
                    value={category.instructions}
                    onChange={(event) => {
                      const categories = [...data.categories];
                      categories[index] = { ...category, instructions: event.target.value.slice(0, 1000) };
                      setData({ ...data, categories });
                    }}
                    disabled={!category.enabled}
                    rows={2}
                    placeholder="z. B. Nur Fragen zu Rollen und Verifizierung beantworten. Keine Entscheidungen treffen."
                    className="mt-3 w-full resize-y rounded-xl border border-slate-800 bg-[#15151b] px-3 py-2.5 text-sm text-white outline-none focus:border-violet-500/50 disabled:opacity-40"
                  />
                </div>
              )) : <p className="rounded-2xl border border-dashed border-slate-800 p-5 text-center text-sm text-slate-500">Lege zuerst mindestens eine Ticket-Kategorie an.</p>}
            </div>
          </div>

          <div>
            <label className="text-xs font-black uppercase tracking-widest text-slate-500">Antwort bei fehlendem Wissen</label>
            <textarea value={data.fallback_text} onChange={(event) => setData({ ...data, fallback_text: event.target.value.slice(0, 500) })} rows={2} className="mt-2 w-full rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-3 text-sm text-white outline-none focus:border-violet-500/50" />
            <p className="mt-1 text-[11px] text-slate-500">Danach erwähnt der Bot automatisch die Teamrollen der Ticket-Kategorie.</p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-5">
            <p className="flex items-center gap-2 text-[11px] text-slate-500"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Keine Ticketverläufe gespeichert · maximal 12 KI-Antworten pro Ticket</p>
            <button disabled={busy} onClick={save} className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-xs font-black text-black hover:bg-slate-200 disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Einstellungen speichern</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
