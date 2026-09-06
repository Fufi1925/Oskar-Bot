"use client";

import React, { useEffect, useState } from "react";
import { Command, Loader2, Pencil, Plus, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { EmojiText } from "@/components/dashboard/emoji-field";
import { DiscordEmojiText } from "@/components/dashboard/discord-emoji";

interface CustomCommand {
  name: string;
  response: string;
  created_at: number;
  updated_at: number;
  use_prefix: number;
  use_exact: number;
  use_contains: number;
  use_slash: number;
}

export function CustomCommandsPanel({ guildId, prefix }: { guildId: string; prefix: string }) {
  const [commands, setCommands] = useState<CustomCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [response, setResponse] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [modes, setModes] = useState({
    use_prefix: true, use_exact: false, use_contains: false, use_slash: false,
  });
  const limit = 3;

  const load = async () => {
    try {
      const data = await api.getCustomCommands(guildId);
      setCommands(data.commands || []);
    } catch (error: any) {
      toast.error(error?.message || "Custom Commands konnten nicht geladen werden.");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [guildId]); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = () => {
    setName(""); setResponse(""); setEditing(null);
    setModes({ use_prefix: true, use_exact: false, use_contains: false, use_slash: false });
  };
  const edit = (entry: CustomCommand) => {
    setName(entry.name); setResponse(entry.response); setEditing(entry.name);
    setModes({
      use_prefix: Boolean(entry.use_prefix), use_exact: Boolean(entry.use_exact),
      use_contains: Boolean(entry.use_contains), use_slash: Boolean(entry.use_slash),
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const save = async () => {
    const clean = name.trim().toLowerCase().replace(/^[!>?.]+/, "");
    if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(clean)) {
      return toast.error("Der Name darf nur Buchstaben, Zahlen, - und _ enthalten.");
    }
    if (!response.trim()) return toast.error("Schreibe eine Antwort für den Befehl.");
    if (!Object.values(modes).some(Boolean)) return toast.error("Wähle mindestens eine Erkennungsart aus.");
    if (!editing && commands.length >= limit) return toast.error("Du hast bereits alle 3 Plätze benutzt.");
    setBusy(true);
    try {
      await api.saveCustomCommand(guildId, clean, response.trim(), modes);
      toast.success(editing ? "Custom Command aktualisiert." : "Custom Command erstellt.");
      reset(); await load();
    } catch (error: any) { toast.error(error?.message || "Speichern fehlgeschlagen."); }
    finally { setBusy(false); }
  };

  const remove = async (entry: CustomCommand) => {
    setBusy(true);
    try {
      await api.deleteCustomCommand(guildId, entry.name);
      if (editing === entry.name) reset();
      toast.success("Custom Command gelöscht."); await load();
    } catch (error: any) { toast.error(error?.message || "Löschen fehlgeschlagen."); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-800 bg-[#131318] overflow-hidden">
        <div className="p-5 sm:p-7 border-b border-slate-800 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-2xl bg-primary/15 flex items-center justify-center"><Zap className="h-5 w-5 text-primary" /></div>
            <div><h3 className="font-bold text-white">{editing ? `„${editing}“ bearbeiten` : "Neuer Custom Command"}</h3><p className="text-xs text-slate-500 mt-1">{commands.length} von {limit} Plätzen belegt</p></div>
          </div>
          <div className="flex gap-1.5">{[0,1,2].map((slot) => <span key={slot} className={`h-2.5 w-7 rounded-full ${slot < commands.length ? "bg-primary" : "bg-slate-800"}`} />)}</div>
        </div>

        <div className="p-5 sm:p-7 space-y-5">
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">Befehlsname</span>
            <div className="flex rounded-xl border border-slate-800 bg-[#0e0e12] overflow-hidden focus-within:border-primary/50">
              <span className="px-4 flex items-center border-r border-slate-800 text-primary font-mono">{prefix}</span>
              <input value={name} onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s/g, "-"))} disabled={Boolean(editing)} maxLength={32} placeholder="regeln" className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm text-white outline-none disabled:opacity-60" />
            </div>
          </label>

          <div className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">Antwort des Bots</span>
            <EmojiText value={response} onChange={setResponse} rows={4} limit={1900} showCount placeholder="Hier stehen unsere Regeln, {user}!" onLimitReached={() => toast.error("Höchstens 1900 Zeichen.")} />
          </div>

          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">Erkennung – mehrere gleichzeitig möglich</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {[
                ["use_prefix", "Server-Präfix", `${prefix}${name || "code"} Text`],
                ["use_slash", "Echter Slash-Command", `/${name || "code"} args: Text`],
                ["use_exact", "Ohne Präfix, exakt", name || "code"],
                ["use_contains", "Wort im Text erkennen", `Wie lautet der ${name || "code"}?`],
              ].map(([key, title, example]) => {
                const active = modes[key as keyof typeof modes];
                return <button key={key} type="button" onClick={() => setModes((old) => ({ ...old, [key]: !active }))} className={`text-left rounded-xl border p-3 transition-colors ${active ? "border-primary/50 bg-primary/10" : "border-slate-800 bg-white/[0.02]"}`}>
                  <span className={`block text-xs font-bold ${active ? "text-primary" : "text-slate-400"}`}>{active ? "✓ " : ""}{title}</span>
                  <code className="block mt-1 text-[10px] text-slate-600 break-all">{example}</code>
                </button>;
              })}
            </div>
          </div>

          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">Platzhalter</p>
            <div className="flex flex-wrap gap-2">{["{user}","{user_name}","{server}","{channel}","{args}"].map((token) => <button key={token} type="button" onClick={() => setResponse((old) => old + token)} className="px-2.5 py-1.5 rounded-lg border border-slate-800 bg-white/[0.02] text-xs font-mono text-slate-400 hover:text-primary">{token}</button>)}</div>
          </div>

          {response && <div className="rounded-2xl bg-[#313338] p-4"><p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Vorschau</p><p className="text-sm text-[#dbdee1] whitespace-pre-wrap"><DiscordEmojiText text={response.replaceAll("{user}", "@Alex").replaceAll("{user_name}", "Alex").replaceAll("{server}", "Dein Server").replaceAll("{channel}", "#allgemein").replaceAll("{args}", "Beispieltext")} /></p></div>}

          <div className="flex gap-3">
            {editing && <button onClick={reset} className="h-12 px-5 rounded-xl border border-slate-800 text-sm font-semibold text-slate-400 hover:text-white">Abbrechen</button>}
            <button onClick={save} disabled={busy || (!editing && commands.length >= limit)} className="h-12 flex-1 rounded-xl bg-primary text-white font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-40 hover:brightness-110">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}{editing ? "Änderungen speichern" : commands.length >= limit ? "Alle 3 Plätze belegt" : "Custom Command erstellen"}
            </button>
          </div>
        </div>
      </section>

      {loading ? <div className="py-12 flex justify-center"><Loader2 className="h-6 w-6 text-primary animate-spin" /></div> : commands.length === 0 ? <div className="py-12 rounded-3xl border border-dashed border-slate-800 text-center text-sm text-slate-500">Noch kein Custom Command erstellt.</div> : (
        <section className="space-y-3">{commands.map((entry) => (
          <div key={entry.name} className="rounded-2xl border border-slate-800 bg-[#131318] p-4 sm:p-5 flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"><Command className="h-5 w-5 text-primary" /></div>
            <div className="min-w-0 flex-1">
              <code className="text-sm font-bold text-white">{entry.use_prefix ? prefix : entry.use_slash ? "/" : ""}{entry.name}</code>
              <div className="flex flex-wrap gap-1 mt-1.5">
                {entry.use_prefix ? <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">PRÄFIX</span> : null}
                {entry.use_slash ? <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">SLASH</span> : null}
                {entry.use_exact ? <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">EXAKT</span> : null}
                {entry.use_contains ? <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">IM TEXT</span> : null}
              </div>
              <p className="mt-2 text-sm text-slate-400 whitespace-pre-wrap break-words"><DiscordEmojiText text={entry.response} /></p>
            </div>
            <button onClick={() => edit(entry)} disabled={busy} className="p-2 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/10" title="Bearbeiten"><Pencil className="h-4 w-4" /></button>
            <button onClick={() => remove(entry)} disabled={busy} className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-400/10" title="Löschen"><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}</section>
      )}
    </div>
  );
}
