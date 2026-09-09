"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, BrainCircuit, KeyRound, Loader2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Guild = {
  guild_id: string;
  name: string;
  icon: string | null;
  members: number;
  premium: boolean;
  enabled: boolean;
};

export function TicketAiAdmin() {
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [keyReady, setKeyReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Zeitüberschreitung beim Laden der Serverliste.")), 12000);
      });
      const result = await Promise.race([api.getTicketAiAccess(), timeout]);
      setGuilds(result.guilds || []);
      setKeyReady(Boolean(result.api_key_configured));
    } catch (err: any) {
      setError(err?.message || "Serverliste konnte nicht geladen werden.");
    } finally {
      if (timer) clearTimeout(timer);
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return guilds.filter((guild) => !query || guild.name.toLowerCase().includes(query) || guild.guild_id.includes(query));
  }, [guilds, search]);

  const toggle = async (guild: Guild) => {
    setBusy(guild.guild_id);
    try {
      await api.setTicketAiAccess(guild.guild_id, !guild.enabled);
      setGuilds((current) => current.map((item) => item.guild_id === guild.guild_id ? { ...item, enabled: !item.enabled } : item));
      toast.success(!guild.enabled ? `${guild.name} wurde freigeschaltet.` : `${guild.name} wurde gesperrt.`);
    } catch (err: any) {
      toast.error(err?.message || "Freigabe konnte nicht geändert werden.");
    } finally {
      setBusy(null);
    }
  };

  const enabled = guilds.filter((guild) => guild.enabled).length;

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-violet-500/20 bg-[#131318] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><BrainCircuit className="h-5 w-5" /></span>
            <div>
              <h2 className="text-lg font-black text-white">Ticket-KI · Serverfreigaben</h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">Nur freigeschaltete Premium-Server sehen die Wissensdatenbank im Ticket-Dashboard und können automatische Antworten verwenden.</p>
            </div>
          </div>
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:bg-white/[0.04] disabled:opacity-40"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Aktualisieren</button>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-black/20 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Freigeschaltet</p><p className="mt-1 text-2xl font-black text-violet-300">{enabled}</p></div>
          <div className="rounded-xl border border-slate-800 bg-black/20 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Bot-Server</p><p className="mt-1 text-2xl font-black text-white">{guilds.length}</p></div>
          <div className={cn("rounded-xl border p-4", keyReady ? "border-emerald-500/20 bg-emerald-500/[0.05]" : "border-amber-500/20 bg-amber-500/[0.05]")}><p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-slate-500"><KeyRound className="h-3 w-3" /> Google-Key</p><p className={cn("mt-1 text-sm font-black", keyReady ? "text-emerald-300" : "text-amber-300")}>{keyReady ? "Eingerichtet" : "Fehlt"}</p></div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-[#131318] p-4 sm:p-5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Servername oder Server-ID suchen" className="w-full rounded-xl border border-slate-800 bg-[#0e0e12] py-3 pl-10 pr-4 text-sm text-white outline-none focus:border-violet-500/40" />
        </div>

        {loading ? (
          <div className="grid min-h-52 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
        ) : error ? (
          <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/[0.05] p-5 text-center"><p className="text-sm font-bold text-red-200">{error}</p><button onClick={load} className="mt-3 rounded-lg border border-red-400/20 px-3 py-2 text-xs font-bold text-red-200">Erneut versuchen</button></div>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {visible.map((guild) => (
              <div key={guild.guild_id} className={cn("flex items-center gap-3 rounded-xl border p-3", guild.enabled ? "border-violet-500/25 bg-violet-500/[0.05]" : "border-slate-800 bg-[#0e0e12]")}>
                {guild.icon ? <img src={guild.icon} alt="" className="h-10 w-10 rounded-xl object-cover" /> : <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-slate-800 text-slate-400"><Bot className="h-4 w-4" /></span>}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-white">{guild.name}</p>
                  <p className="truncate text-[10px] text-slate-600">{guild.guild_id} · {guild.members.toLocaleString("de-DE")} Mitglieder</p>
                  <div className="mt-1 flex gap-1.5">
                    <span className={cn("rounded px-1.5 py-0.5 text-[8px] font-black uppercase", guild.premium ? "bg-amber-400/12 text-amber-300" : "bg-slate-800 text-slate-500")}>{guild.premium ? "Premium" : "Kein Premium"}</span>
                    {guild.enabled && <span className="rounded bg-violet-500/12 px-1.5 py-0.5 text-[8px] font-black uppercase text-violet-300">KI freigeschaltet</span>}
                  </div>
                </div>
                <button type="button" onClick={() => toggle(guild)} disabled={busy === guild.guild_id} className={cn("relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-40", guild.enabled ? "bg-violet-500" : "bg-slate-700")} aria-label={`Ticket-KI für ${guild.name} ${guild.enabled ? "sperren" : "freischalten"}`}>
                  {busy === guild.guild_id ? <Loader2 className="absolute left-4 top-1.5 h-4 w-4 animate-spin text-white" /> : <span className={cn("absolute left-0 top-1 h-5 w-5 rounded-full bg-white transition-transform", guild.enabled ? "translate-x-6" : "translate-x-1")} />}
                </button>
              </div>
            ))}
            {!visible.length && <p className="col-span-full py-10 text-center text-sm text-slate-500">Kein passender Server gefunden.</p>}
          </div>
        )}
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-blue-500/15 bg-blue-500/[0.04] p-4 text-xs leading-5 text-slate-400"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" /> Eine Admin-Freigabe allein reicht nicht: Ohne aktives Server-Premium bleibt die Ticket-KI serverseitig gesperrt.</div>
    </div>
  );
}
