"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BrainCircuit, CheckCircle2, FileText, Loader2, MessageSquare, Plus, Save, ScanSearch, Search, Send, Settings2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useWebsiteLocale } from "@/lib/i18n/locale";
import { Switch } from "@/components/ui/switch";
import { useSaveGuard } from "@/components/dashboard/save-bar";

type Memory = { id: number; title: string; content: string; source: string; updated_at: number };
type Message = { id: number; role: "user" | "assistant"; content: string };
type Category = { category_id: number; name: string; panel_name: string; enabled: boolean; instructions: string };
type Settings = { enabled: boolean; api_key_configured: boolean; fallback_text: string; categories: Category[]; memories: Memory[]; knowledge: null | { filename: string; content: string; updated_at: number } };
const BOX = "rounded-2xl border border-white/[.07] bg-[#202124] p-5 sm:p-6";
const INPUT = "w-full min-w-0 rounded-xl border border-white/[.08] bg-[#18191c] px-3 py-3 text-sm text-slate-200 outline-none focus:border-indigo-400/60 disabled:opacity-50";
const BUTTON = "inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 disabled:opacity-40";
const settingsKey = (value: Settings) => JSON.stringify([value.enabled, value.fallback_text, value.categories]);

export function TicketAiPanel({ guildId }: { guildId: string }) {
  const locale = useWebsiteLocale(), language = locale === "en-GB" ? "en" : "de";
  const t = (de: string, en: string) => language === "en" ? en : de;
  const [data, setData] = useState<Settings | null>(null), [loading, setLoading] = useState(true), [unavailable, setUnavailable] = useState(false);
  const [loadError, setLoadError] = useState(""), [busy, setBusy] = useState(false), [tab, setTab] = useState("chat");
  const [messages, setMessages] = useState<Message[]>([]), [message, setMessage] = useState(""), [mode, setMode] = useState<"teach" | "ask">("teach");
  const [scan, setScan] = useState<any>(null), [draft, setDraft] = useState(""), [knowledgeText, setKnowledgeText] = useState("");
  const [search, setSearch] = useState(""), [editing, setEditing] = useState<{ id?: number; title: string; content: string } | null>(null);
  const [saved, setSaved] = useState(""), [savedDocument, setSavedDocument] = useState("");
  const fileRef = useRef<HTMLInputElement>(null), endRef = useRef<HTMLDivElement>(null);
  const dirty = !!data && (settingsKey(data) !== saved || knowledgeText !== savedDocument || !!editing);
  const guard = useSaveGuard(dirty ? 1 : 0, `ticket-ai-${guildId}`);
  useEffect(() => {
    if (guard.shake) toast.warning(language === "en" ? "Save or discard your changes in Ticket AI before leaving." : "Speichere oder verwirf deine Änderungen in der Ticket-KI, bevor du diese Seite verlässt.");
  }, [guard.shake, language]);

  const errorText = (error: any) => {
    const code = error?.message || "";
    const labels: Record<string, string> = {
      ai_not_configured: t("Der KI-Dienst ist noch nicht eingerichtet. Wissen kannst du bereits speichern.", "The AI service has not been configured yet. You can already save knowledge."),
      ai_timeout: t("Die KI hat nicht rechtzeitig geantwortet. Bitte versuche es erneut.", "The AI did not respond in time. Please try again."),
      ai_unavailable: t("Der KI-Dienst ist momentan nicht erreichbar. Dein Wissen bleibt gespeichert.", "The AI service is currently unavailable. Your knowledge remains saved."),
      chat_busy: t("Eine Antwort für dein Konto wird bereits verarbeitet.", "A reply for your account is already being processed."),
      memory_not_found: t("Dieser Wissenseintrag wurde bereits gelöscht.", "This knowledge entry has already been deleted."),
      empty_knowledge: t("Bitte gib eine Information ein.", "Please enter some information."),
      memory_too_long: t("Ein Wissenseintrag darf höchstens 4.000 Zeichen enthalten.", "A knowledge entry may contain up to 4,000 characters."),
      knowledge_too_large: t("Die Wissensliste ist voll. Bearbeite oder lösche ältere Einträge.", "The knowledge list is full. Edit or delete older entries."),
      invalid_message: t("Bitte gib eine Nachricht mit höchstens 4.000 Zeichen ein.", "Please enter a message with up to 4,000 characters."),
    };
    return labels[code] || t("Die Anfrage konnte nicht abgeschlossen werden. Bitte versuche es erneut.", "The request could not be completed. Please try again.");
  };
  const load = useCallback(async () => {
    setLoading(true); setLoadError("");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const request = async () => {
        const visibility = await api.getTicketAiAvailability(guildId);
        if (!visibility.available) return null;
        const settings = await api.getTicketAi(guildId);
        const [chat, job] = await Promise.all([api.getTicketAiChat(guildId), api.getTicketAiScan(guildId)]);
        return { settings, chat, job };
      };
      const value = await Promise.race([request(), new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error("load_timeout")), 12000); })]);
      if (!value) { setUnavailable(true); return; }
      setData(value.settings); setSaved(settingsKey(value.settings)); setKnowledgeText(value.settings.knowledge?.content || ""); setSavedDocument(value.settings.knowledge?.content || "");
      setMessages(value.chat.messages); setScan(value.job); setDraft(value.job.draft || ""); setUnavailable(false);
    } catch (error: any) { if (error?.status === 404) setUnavailable(true); else setLoadError(error?.message || "load_failed"); }
    finally { if (timer) clearTimeout(timer); setLoading(false); }
  }, [guildId]);
  useEffect(() => { void load(); }, [load]);
  const scanStatus = scan?.status;
  useEffect(() => {
    if (!["queued", "running", "generating"].includes(scanStatus)) return;
    let alive = true, pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return; pending = true;
      try { const next = await api.getTicketAiScan(guildId); if (alive) { setScan(next); if (next.status === "completed") setDraft(next.draft || ""); } }
      catch { /* Retain the visible status; the next poll can recover. */ }
      finally { pending = false; }
    }, 2500);
    return () => { alive = false; window.clearInterval(timer); };
  }, [guildId, scanStatus]);
  useEffect(() => { if (tab === "chat") endRef.current?.scrollIntoView({ block: "nearest" }); }, [messages, tab]);
  async function run(action: () => Promise<void>) {
    if (busy) return; setBusy(true);
    try { await action(); } catch (error) { toast.error(errorText(error)); } finally { setBusy(false); }
  }
  async function send() {
    if (!message.trim()) return;
    await run(async () => {
      const result = await api.sendTicketAiChat(guildId, message.trim(), mode, language);
      setMessages(result.messages); setMessage(""); setData(current => current && ({ ...current, memories: result.memories }));
    });
  }
  async function saveSettings(enabled = data?.enabled) {
    if (!data) return;
    if (enabled && (!data.knowledge && !data.memories.length)) { toast.error(t("Hinterlege zuerst Wissen im Chat oder lade eine Wissensdatei hoch.", "First add knowledge in the chat or upload a knowledge file.")); return; }
    if (enabled && !data.api_key_configured) { toast.error(errorText({ message: "ai_not_configured" })); return; }
    await run(async () => { const next = { ...data, enabled: !!enabled }; await api.saveTicketAi(guildId, next); setData(next); setSaved(settingsKey(next)); toast.success(t("Ticket-KI gespeichert.", "Ticket AI saved.")); });
  }
  async function refreshKnowledge() {
    const next = await api.getTicketAi(guildId);
    setData(current => current && ({ ...current, memories: next.memories, knowledge: next.knowledge, enabled: next.enabled }));
    setSaved(current => { if (!current) return current; const baseline = JSON.parse(current); baseline[0] = next.enabled; return JSON.stringify(baseline); });
    setKnowledgeText(next.knowledge?.content || ""); setSavedDocument(next.knowledge?.content || "");
  }
  async function storeDocument(text: string, filename?: string) {
    if (!text.trim() || new TextEncoder().encode(text).length > 100_000) { toast.error(t("Bitte verwende eine nicht leere TXT-Datei mit höchstens 100 KB.", "Please use a non-empty TXT file of up to 100 KB.")); return; }
    await run(async () => { await api.uploadTicketAiKnowledge(guildId, filename || data?.knowledge?.filename || "server-wissen.txt", text); await refreshKnowledge(); toast.success(t("Wissensdatei gespeichert.", "Knowledge file saved.")); });
  }
  async function upload(file?: File) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".txt") || file.size > 100_000) { toast.error(t("Nur TXT-Dateien mit höchstens 100 KB sind erlaubt.", "Only TXT files of up to 100 KB are allowed.")); return; }
    try { await storeDocument(await file.text(), file.name); } catch (error) { toast.error(errorText(error)); }
    if (fileRef.current) fileRef.current.value = "";
  }
  function confirm(de: string, en: string) { return window.confirm(t(de, en)); }
  const warnings: Record<string, string> = {
    history_permission: t("Kanalzugriff oder Nachrichtenverlauf fehlt", "Missing channel access or message history permission"),
    history_timeout: t("Nachrichtenabruf hat das Zeitlimit erreicht", "Message retrieval reached its time limit"),
    channel_unavailable: t("Kanal konnte nicht gelesen werden", "Channel could not be read"),
    archive_unavailable: t("Archivierte Threads sind nicht zugänglich", "Archived threads are inaccessible"),
    archive_timeout: t("Thread-Abruf hat das Zeitlimit erreicht", "Thread retrieval reached its time limit"),
    dashboard_unavailable: t("Dashboard-Konfiguration konnte nicht gelesen werden", "Dashboard configuration could not be read"),
    message_content_disabled: t("Der Bot hat keinen Zugriff auf Nachrichteninhalte", "The bot has no access to message content"),
    read_timeout: t("Scan-Zeitlimit erreicht; Entwurf enthält die bisher gelesenen Daten", "Scan time limit reached; the draft contains data read so far"),
    source_limit: t("100-KB-Limit erreicht; weitere Inhalte wurden ausgelassen", "100 KB limit reached; additional content was omitted"),
    no_admin_messages: t("Keine lesbaren Nachrichten des Inhabers oder von Administratoren gefunden", "No readable messages from the owner or administrators found"),
  };
  if (unavailable || (loading && !data && !loadError)) return null;
  if (loadError) return <div className={BOX}><h3 className="font-semibold text-white">{t("Ticket-KI konnte nicht geladen werden", "Ticket AI could not be loaded")}</h3><p className="mt-2 text-sm text-slate-400">{t("Prüfe die Verbindung und versuche es erneut.", "Check the connection and try again.")}</p><button className={`${BUTTON} mt-4`} onClick={load}>{t("Erneut versuchen", "Try again")}</button></div>;
  if (!data) return null;
  const filtered = data.memories.filter(item => `${item.title} ${item.content}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const tabs = [{ id: "chat", name: t("Chat", "Chat"), icon: MessageSquare }, { id: "knowledge", name: t("Gespeichertes Wissen", "Saved knowledge"), icon: FileText }, { id: "scan", name: t("Server lesen", "Read server"), icon: ScanSearch }, { id: "settings", name: t("Ticket-Antworten", "Ticket replies"), icon: Settings2 }];
  return <section className="space-y-5 text-slate-200">
    {dirty && <div id={`ticket-ai-${guildId}`} className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm ${guard.shake ? "border-rose-400/50 text-rose-200" : "border-amber-400/20 text-amber-200"}`}><p>{t("Ungespeicherte Änderungen. Speichere sie im jeweiligen Bereich oder verwirf sie.", "Unsaved changes. Save them in the relevant section or discard them.")}</p><button className={BUTTON} disabled={busy} onClick={() => { const [enabled, fallback_text, categories] = JSON.parse(saved); setData({ ...data, enabled, fallback_text, categories }); setKnowledgeText(savedDocument); setEditing(null); }}>{t("Änderungen verwerfen", "Discard changes")}</button></div>}
    <header className={BOX}><div className="flex items-start justify-between gap-4"><div><h2 className="flex items-center gap-3 text-xl font-semibold text-white"><BrainCircuit className="h-6 w-6 text-indigo-300" />{t("Dein Ticket-Assistent", "Your ticket assistant")}</h2><p className="mt-2 text-sm leading-relaxed text-slate-400">{t("Bringe der KI deinen Server bei. Prüfe ihr Wissen und lege fest, in welchen Tickets sie hilft.", "Teach the AI about your server. Review its knowledge and choose which tickets it helps with.")}</p></div><Switch checked={data.enabled} disabled={busy} onCheckedChange={value => saveSettings(value)} aria-label={t("Ticket-KI aktivieren", "Enable Ticket AI")} /></div><div className="mt-4 flex flex-wrap gap-3 text-xs text-slate-500"><span className={data.enabled ? "text-emerald-300" : "text-slate-400"}>{data.enabled ? t("Ticket-Antworten aktiv", "Ticket replies enabled") : t("Ticket-Antworten pausiert", "Ticket replies paused")}</span><span>{data.memories.length} {t("Wissenseinträge", "knowledge entries")}</span><span>{data.categories.filter(c => c.enabled).length} {t("aktive Kategorien", "active categories")}</span></div></header>
    {!data.api_key_configured && <p role="status" className="rounded-xl border border-amber-400/20 bg-amber-500/5 p-4 text-sm text-amber-200">{t("Der KI-Dienst ist noch nicht eingerichtet. Wissen speichern und den Server lesen kannst du bereits. Für KI-Antworten muss der Betreiber den Dienst einrichten.", "The AI service is not configured yet. You can already save knowledge and read the server. The operator must configure the service before AI replies are available.")}</p>}
    <nav aria-label={t("Ticket-KI-Bereich", "Ticket AI workspace")} className="flex gap-1 overflow-x-auto rounded-2xl border border-white/[.07] bg-[#202124] p-2">{tabs.map(item => <button key={item.id} aria-current={tab === item.id ? "page" : undefined} onClick={() => setTab(item.id)} className={`flex shrink-0 items-center gap-2 rounded-xl px-3 py-2.5 text-sm ${tab === item.id ? "bg-indigo-400/15 text-indigo-200" : "text-slate-400 hover:bg-white/5"}`}><item.icon className="h-4 w-4" />{item.name}</button>)}</nav>
    {tab === "chat" && <div className={BOX}>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{t("Wissen teilen und Antworten testen", "Share knowledge and test replies")}</h3><p className="mt-1 text-xs text-slate-500">{t("Dein Chat ist persönlich. Gespeichertes Wissen gilt für diesen Server.", "Your chat is personal. Saved knowledge applies to this server.")}</p></div><button className={BUTTON} disabled={busy || !messages.length} onClick={() => { if (confirm("Deinen Chatverlauf löschen? Das Serverwissen bleibt erhalten.", "Clear your chat history? Server knowledge will be retained.")) void run(async () => { await api.clearTicketAiChat(guildId); setMessages([]); }); }}><Trash2 className="h-4 w-4" />{t("Chat leeren", "Clear chat")}</button></div>
      <div role="log" aria-live="polite" className="mt-5 max-h-[480px] min-h-60 space-y-4 overflow-y-auto rounded-xl bg-[#18191c] p-4">
        {!messages.length && <div className="py-8 text-center"><BrainCircuit className="mx-auto h-8 w-8 text-indigo-300" /><p className="mt-4 font-medium">{t("Was soll dein Assistent wissen?", "What should your assistant know?")}</p><p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-400">{t('Zum Beispiel: „Premium kostet auf unserem Server 5 Euro und ist im Shop erhältlich.“', 'For example: “Premium costs 5 euros on our server and is available in the shop.”')}</p></div>}
        {messages.map(item => <div key={item.id} className={`max-w-[90%] rounded-xl p-4 ${item.role === "user" ? "ml-auto bg-indigo-400/10" : "border border-white/5 bg-[#202124]"}`}><p className="mb-2 text-[11px] font-medium text-indigo-200">{item.role === "user" ? t("Du", "You") : t("Ticket-Assistent", "Ticket assistant")}</p><p className="whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere]">{item.content}</p></div>)}<div ref={endRef} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{(["teach", "ask"] as const).map(value => <button key={value} onClick={() => setMode(value)} disabled={busy} aria-pressed={mode === value} className={`${BUTTON} ${mode === value ? "border-indigo-400/40 bg-indigo-400/10 text-indigo-200" : ""}`}>{value === "teach" ? t("Wissen merken", "Remember knowledge") : t("Antwort testen", "Test reply")}</button>)}</div>
      <p className="mt-3 text-xs leading-relaxed text-slate-500">{mode === "teach" ? t("Deine nächste Nachricht wird unverändert als Wissenseintrag gespeichert. Unter Gespeichertes Wissen kannst du sie korrigieren oder löschen.", "Your next message will be saved exactly as a knowledge entry. You can correct or delete it in Saved knowledge.") : t("Die KI antwortet aus dem gespeicherten Wissen. Deine Frage wird nicht als Wissenseintrag gespeichert.", "The AI answers from saved knowledge. Your question is not saved as a knowledge entry.")}</p>
      <form onSubmit={event => { event.preventDefault(); void send(); }} className="mt-3 space-y-3"><label className="sr-only" htmlFor={`ai-message-${guildId}`}>{t("Nachricht an die Ticket-KI", "Message to Ticket AI")}</label><textarea id={`ai-message-${guildId}`} className={INPUT} value={message} onChange={event => setMessage(event.target.value)} maxLength={4000} rows={3} disabled={busy} placeholder={mode === "teach" ? t("Premium kostet bei uns 5 Euro …", "Premium costs 5 euros here …") : t("Wie viel kostet Premium?", "How much does Premium cost?")} /><div className="flex items-center justify-between gap-3"><span className="text-xs text-slate-500">{message.length} / 4.000</span><button type="submit" className={`${BUTTON} border-indigo-400/30 bg-indigo-400/10 text-indigo-200`} disabled={busy || !message.trim() || (mode === "ask" && !data.api_key_configured)}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{t("Senden", "Send")}</button></div></form>
    </div>}
    {tab === "knowledge" && <>
      <div className={BOX}><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">{t("Alles, was die KI gespeichert hat", "Everything the AI has saved")}</h3><p className="mt-1 text-xs text-slate-500">{t("Einträge aus dem Chat und manuell ergänztes Wissen. Alle bleiben bearbeitbar.", "Entries from the chat and manually added knowledge. All entries remain editable.")}</p></div><button className={BUTTON} disabled={busy} onClick={() => setEditing({ title: "", content: "" })}><Plus className="h-4 w-4" />{t("Eintrag hinzufügen", "Add entry")}</button></div>
      <label className="mt-5 flex items-center gap-2"><Search className="h-4 w-4 text-slate-500" /><input aria-label={t("Wissen durchsuchen", "Search knowledge")} className={INPUT} value={search} onChange={event => setSearch(event.target.value)} placeholder={t("Wissen durchsuchen …", "Search knowledge …")} /></label>
      {editing && <form className="mt-5 space-y-3 rounded-xl border border-indigo-400/20 bg-[#18191c] p-4" onSubmit={event => { event.preventDefault(); void run(async () => { await api.saveTicketAiMemory(guildId, editing); setEditing(null); await refreshKnowledge(); toast.success(t("Wissenseintrag gespeichert.", "Knowledge entry saved.")); }); }}><label className="block text-xs text-slate-400">{t("Titel", "Title")}<input className={`${INPUT} mt-2`} value={editing.title} maxLength={120} onChange={event => setEditing({ ...editing, title: event.target.value })} disabled={busy} /></label><label className="block text-xs text-slate-400">{t("Information", "Information")}<textarea className={`${INPUT} mt-2`} value={editing.content} maxLength={4000} rows={4} onChange={event => setEditing({ ...editing, content: event.target.value })} disabled={busy} /></label><div className="flex flex-wrap justify-end gap-2"><button type="button" className={BUTTON} disabled={busy} onClick={() => setEditing(null)}>{t("Abbrechen", "Cancel")}</button><button type="submit" className={BUTTON} disabled={busy || !editing.content.trim()}><Save className="h-4 w-4" />{t("Eintrag speichern", "Save entry")}</button></div></form>}
      <div className="mt-5 space-y-3">{filtered.map(item => <article key={item.id} className="rounded-xl border border-white/[.07] bg-[#18191c] p-4"><h4 className="break-words font-medium [overflow-wrap:anywhere]">{item.title}</h4><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-400 [overflow-wrap:anywhere]">{item.content}</p><div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="text-[11px] text-slate-500">{item.source === "chat" ? t("Aus deinem Server-Chat", "From the server coaching chat") : t("Manuell hinterlegt", "Added manually")} · {new Date(item.updated_at * 1000).toLocaleDateString(locale)}</span><div className="flex gap-2"><button className={BUTTON} disabled={busy} onClick={() => setEditing({ id: item.id, title: item.title, content: item.content })}>{t("Bearbeiten", "Edit")}</button><button className={`${BUTTON} text-rose-300`} disabled={busy} aria-label={t("Wissenseintrag löschen", "Delete knowledge entry")} onClick={() => { if (confirm("Diesen Wissenseintrag löschen?", "Delete this knowledge entry?")) void run(async () => { await api.deleteTicketAiMemory(guildId, item.id); await refreshKnowledge(); }); }}><Trash2 className="h-4 w-4" /></button></div></div></article>)}{!filtered.length && <p className="py-7 text-center text-sm text-slate-500">{search ? t("Keine passenden Einträge.", "No matching entries.") : t("Noch kein Wissen gespeichert. Schreibe der KI im Chat oder füge einen Eintrag hinzu.", "No knowledge saved yet. Write to the AI in the chat or add an entry.")}</p>}</div></div>
      <div className={BOX}><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">{t("Importiertes Dokument", "Imported document")}</h3><p className="mt-1 text-xs text-slate-500">{t("TXT-Datei oder geprüfter Server-Entwurf, maximal 100 KB. Ein neuer Import ersetzt nur dieses Dokument.", "TXT file or reviewed server draft, up to 100 KB. A new import replaces only this document.")}</p></div><button className={BUTTON} disabled={busy} onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" />{t("TXT hochladen", "Upload TXT")}</button><input ref={fileRef} type="file" accept=".txt,text/plain" className="hidden" onChange={event => void upload(event.target.files?.[0])} /></div>{data.knowledge && <><p className="mt-4 text-xs text-indigo-200">{data.knowledge.filename}</p><label className="sr-only" htmlFor={`ai-document-${guildId}`}>{t("Wissensdatei bearbeiten", "Edit knowledge document")}</label><textarea id={`ai-document-${guildId}`} className={`${INPUT} mt-3 font-mono text-xs leading-relaxed`} rows={12} value={knowledgeText} disabled={busy} onChange={event => setKnowledgeText(event.target.value)} /><div className="mt-3 flex flex-wrap justify-end gap-2"><button className={`${BUTTON} text-rose-300`} disabled={busy} onClick={() => { if (confirm("Importiertes Dokument löschen? Chat-Wissen bleibt erhalten.", "Delete the imported document? Knowledge from the chat is retained.")) void run(async () => { await api.deleteTicketAiKnowledge(guildId); await refreshKnowledge(); }); }}><Trash2 className="h-4 w-4" />{t("Dokument löschen", "Delete document")}</button><button className={BUTTON} disabled={busy || knowledgeText === savedDocument} onClick={() => storeDocument(knowledgeText)}><Save className="h-4 w-4" />{t("Dokument speichern", "Save document")}</button></div></>}</div>
    </>}
    {tab === "scan" && <div className={BOX}><h3 className="font-semibold">{t("Serverwissen einlesen", "Read server knowledge")}</h3><p className="mt-2 text-sm leading-relaxed text-slate-400">{t("Liest Serverstruktur, Dashboard-Einstellungen und zugängliche Nachrichten von Inhaber und Administratoren aus den letzten 30 Tagen. Ticketkanäle werden ausgelassen. Der Scan erstellt lokal einen Entwurf, ohne Daten an den KI-Anbieter zu senden.", "Reads the server structure, dashboard settings and accessible messages from the owner and administrators from the past 30 days. Ticket channels are excluded. The scan creates a local draft without sending data to the AI provider.")}</p><p className="mt-2 text-xs text-slate-500">{t("Prüfe den Entwurf vor dem Übernehmen. Nur danach darf der Assistent passende Wissensausschnitte für Antworten verwenden.", "Review the draft before accepting it. Only afterwards can the assistant use relevant knowledge excerpts for replies.")}</p><div className="mt-5 flex flex-wrap gap-2"><button className={BUTTON} disabled={busy || ["queued", "running", "generating"].includes(scanStatus)} onClick={() => void run(async () => { const result = await api.startTicketAiScan(guildId); setScan({ status: result.status }); setDraft(""); })}><ScanSearch className="h-4 w-4" />{t("Server lesen lassen", "Read server")}</button>{["queued", "running", "generating"].includes(scanStatus) && <button className={`${BUTTON} text-rose-300`} disabled={busy} onClick={() => void run(async () => { await api.cancelTicketAiScan(guildId); setScan({ status: "cancelled" }); })}>{t("Scan abbrechen", "Cancel scan")}</button>}</div>
      {scan && scan.status !== "idle" && <div role="status" className="mt-5 rounded-xl bg-[#18191c] p-4"><p className="flex items-center gap-2 text-sm font-medium">{["queued", "running", "generating"].includes(scanStatus) && <Loader2 className="h-4 w-4 animate-spin" />}{scanStatus === "completed" ? t("Entwurf bereit", "Draft ready") : scanStatus === "cancelled" ? t("Scan abgebrochen", "Scan cancelled") : scanStatus === "failed" ? t("Scan fehlgeschlagen", "Scan failed") : t("Server wird gelesen …", "Reading server …")}</p><p className="mt-2 text-xs text-slate-400">{scan.progress || 0} / {scan.total_channels || 0} {t("Kanäle", "channels")} · {scan.message_count || 0} {t("Admin-Nachrichten", "admin messages")} · {scan.skipped_channels || 0} {t("übersprungen", "skipped")}</p>{scan.current_channel && scan.current_channel !== "preparing" && <p className="mt-2 break-words text-xs text-indigo-200">#{scan.current_channel}</p>}{scan.total_channels > 0 && <progress className="mt-3 h-2 w-full accent-indigo-400" value={scan.progress || 0} max={scan.total_channels} />}{scanStatus === "failed" && <p className="mt-3 text-xs text-rose-300">{t("Der Bot konnte den Server nicht lesen. Prüfe, ob er verbunden ist und Kanalzugriff hat.", "The bot could not read the server. Check whether it is connected and has channel access.")}</p>}{scan.warnings?.length > 0 && <details className="mt-4 text-xs text-amber-200"><summary className="cursor-pointer">{t("Hinweise zu ausgelassenen Inhalten", "Notes about omitted content")} ({scan.warnings.length})</summary><ul className="mt-3 space-y-2">{scan.warnings.map((warning: any, index: number) => <li key={index} className="break-words">{warning.channel ? `#${warning.channel}: ` : ""}{warnings[warning.code] || t("Ein Teil der Serverdaten konnte nicht gelesen werden.", "Some server data could not be read.")}</li>)}</ul></details>}</div>}
      {scanStatus === "completed" && draft && <div className="mt-5"><label className="mb-3 block text-sm font-medium" htmlFor={`ai-draft-${guildId}`}>{t("Server-Entwurf prüfen und bearbeiten", "Review and edit the server draft")}</label><textarea id={`ai-draft-${guildId}`} className={`${INPUT} font-mono text-xs leading-relaxed`} rows={16} value={draft} disabled={busy} onChange={event => setDraft(event.target.value)} /><button className={`${BUTTON} mt-4 border-emerald-400/20 text-emerald-200`} disabled={busy || !draft.trim()} onClick={() => { if (confirm("Diesen Entwurf speichern? Ein vorhandenes importiertes Dokument wird ersetzt; Chat-Wissen bleibt erhalten.", "Save this draft? An existing imported document will be replaced; knowledge from the chat is retained.")) void storeDocument(draft, "server-scan.txt"); }}><CheckCircle2 className="h-4 w-4" />{t("Geprüften Entwurf übernehmen", "Accept reviewed draft")}</button></div>}
    </div>}
    {tab === "settings" && <div className={BOX}>
      <h3 className="font-semibold">{t("Wo darf die KI antworten?", "Where may the AI reply?")}</h3>
      <p className="mt-2 text-sm text-slate-400">{t("Die KI hilft dem Ticket-Ersteller, bis ein Teammitglied übernimmt. Kategorien werden nach dem zugehörigen Ticket-Panel angezeigt.", "The AI helps the ticket creator until a team member claims the ticket. Categories are shown with their ticket panel.")}</p>
      <div className="mt-5 space-y-4">{data.categories.map((category, index) => <div key={category.category_id} className="rounded-xl border border-white/[.07] bg-[#18191c] p-4">
        <div className="flex items-center justify-between gap-4"><div><p className="text-[11px] text-indigo-200">{category.panel_name === "Legacy" ? t("Bisheriges Ticket-Panel", "Legacy ticket panel") : category.panel_name}</p><label htmlFor={`ai-category-${category.category_id}`} className="mt-1 block font-medium">{category.name}</label></div><Switch id={`ai-category-${category.category_id}`} disabled={busy} checked={category.enabled} onCheckedChange={enabled => setData({ ...data, categories: data.categories.map((c, i) => i === index ? { ...c, enabled } : c) })} /></div>
        <label className="mt-4 block text-xs text-slate-400">{t("Zusätzliche Antwortregeln", "Additional reply rules")}<textarea className={`${INPUT} mt-2`} value={category.instructions} maxLength={1000} rows={2} disabled={busy || !category.enabled} onChange={event => setData({ ...data, categories: data.categories.map((c, i) => i === index ? { ...c, instructions: event.target.value } : c) })} placeholder={t("Zum Beispiel: Nur Fragen zu Premium beantworten, keine Käufe auslösen.", "For example: Answer only questions about Premium; do not perform purchases.")} /></label>
      </div>)}{!data.categories.length && <p className="text-sm text-slate-500">{t("Erstelle zuerst eine Kategorie in deinen Ticket-Panels.", "First create a category in your ticket panels.")}</p>}</div>
      <label className="mt-6 block text-xs text-slate-400">{t("Antwort bei fehlendem Wissen", "Reply when knowledge is missing")}<textarea className={`${INPUT} mt-2`} maxLength={500} rows={3} disabled={busy} value={data.fallback_text} onChange={event => setData({ ...data, fallback_text: event.target.value })} /></label>
      <p className="mt-2 text-xs text-slate-500">{t("Danach wird das zuständige Team der Kategorie informiert. Nutzertexte bleiben so, wie du sie eingibst.", "The category's support team is then notified. Custom text remains exactly as you enter it.")}</p>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-slate-500">{t("Maximal 12 KI-Antworten pro Ticket. Die KI legt keinen eigenen Ticketverlauf an; aktivierte Transkripte bleiben möglich.", "Up to 12 AI replies per ticket. The AI does not create its own ticket history; enabled transcripts can still be stored.")}</p><button className={BUTTON} disabled={busy || settingsKey(data) === saved} onClick={() => saveSettings()}><Save className="h-4 w-4" />{t("Antwortregeln speichern", "Save reply rules")}</button></div>
    </div>}
  </section>;
}
